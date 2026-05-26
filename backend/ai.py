import json
import math
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from statistics import mean, pstdev
from typing import Iterable

from sqlalchemy.orm import Session

from . import models

AI_MODEL_VERSION = "rules-zscore-time-v3"

ENVIRONMENT_RULES = {
    "temperature": {"warning": (5, 35), "critical": (-20, 50), "label": "温度"},
    "humidity": {"warning": (20, 90), "critical": (0, 100), "label": "湿度"},
    "pm25": {"warning": (0, 35), "critical": (0, 75), "label": "PM2.5"},
    "pressure": {"warning": (950, 1050), "critical": (900, 1100), "label": "气压"},
    "dew_point": {"warning": (-10, 25), "critical": (-20, 30), "label": "露点温度"},
    "heat_index": {"warning": (0, 40), "critical": (0, 54), "label": "热指数"},
    "wind_speed": {"warning": (0, 10.8), "critical": (0, 20.8), "label": "风速"},
    "latitude": {"warning": (-90, 90), "critical": (-90, 90), "label": "纬度"},
    "longitude": {"warning": (-180, 180), "critical": (-180, 180), "label": "经度"},
}

# 气象学时间维度阈值（基于联网研究资料）
TIME_DIMENSION_RULES = {
    "pressure_tendency": {
        "label": "气压倾向",
        "timeframe_hours": 3,
        "rapid_drop_hpa": 2.0,    # 3小时内下降超过2hPa → 风暴/冷锋逼近
        "rapid_rise_hpa": 3.0,    # 3小时内上升超过3hPa → 天气转晴（注意突变）
        "sustained_low_hpa": 990, # 持续低于990hPa → 风暴系统
    },
    "temp_rate_of_change": {
        "label": "温度变化率",
        "timeframe_hours": 1,
        "rapid_drop_c": 5.0,      # 1小时内下降超过5°C → 冷锋过境/寒潮
        "rapid_rise_c": 4.0,      # 1小时内上升超过4°C → 暖锋逼近/焚风
    },
    "dew_point_spread": {
        "label": "露点差",
        "fog_risk_spread_c": 2.0, # 温度-露点 <2°C → 浓雾/凝结风险
        "high_dew_point_c": 20.0, # 露点 >20°C → 高湿热不适
        "frost_risk_c": 0.0,      # 露点 <0°C 且温度接近露点 → 霜冻风险
    },
    "heat_index": {
        "label": "热指数危险",
        "danger_hi": 40.0,        # 热指数 >40°C → 危险
        "extreme_danger_hi": 54.0,# 热指数 >54°C → 极度危险
    },
    "consecutive_anomaly": {
        "label": "连续异常模式",
        "lookback_hours": 24,
        "min_consecutive": 3,     # 同一设备连续3条异常 → 持续性风险
        "min_window_count": 5,    # 24小时内出现5条以上异常 → 系统性问题
    },
    "multi_param_trend": {
        "label": "多参数协同趋势",
        "warming_pressure_drop": "升温+降压 → 暖锋/低压系统逼近",
        "cooling_pressure_rise": "降温+升压 → 冷锋过境后/高压控制",
        "temp_rise_humidity_drop": "升温+降湿 → 干燥热风/焚风效应",
    },
}

# 风速 Beaufort 风级参考
WIND_BEAUFORT = [
    (0.3, 0, "无风"),
    (1.6, 1, "软风"),
    (3.4, 2, "轻风"),
    (5.5, 3, "微风"),
    (8.0, 4, "和风"),
    (10.8, 5, "清风"),
    (13.9, 6, "强风"),
    (17.2, 7, "疾风"),
    (20.8, 8, "大风"),
    (24.5, 9, "烈风"),
    (28.5, 10, "狂风"),
    (32.7, 11, "暴风"),
    (float("inf"), 12, "飓风"),
]


# ---------- 气象学派生参数计算 ----------

def calc_dew_point(temperature: float, humidity: float) -> float:
    """使用 Magnus 公式计算露点温度。
    参考: https://en.wikipedia.org/wiki/Dew_point
    """
    a, b = 17.27, 237.7
    gamma = (a * temperature) / (b + temperature) + math.log(humidity / 100.0)
    return (b * gamma) / (a - gamma)


def calc_heat_index(temperature: float, humidity: float) -> float | None:
    """使用 Steadman 公式计算热指数（体感温度）。
    参考: https://en.wikipedia.org/wiki/Heat_index
    仅在温度 >= 27°C 且湿度 >= 40% 时有意义。
    """
    if temperature < 27.0 or humidity < 40.0:
        return None
    T = temperature * 1.8 + 32  # 转华氏度
    R = humidity
    HI_F = (
        -42.379
        + 2.04901523 * T
        + 10.14333127 * R
        - 0.22475541 * T * R
        - 6.83783e-3 * T * T
        - 5.481717e-2 * R * R
        + 1.22874e-3 * T * T * R
        + 8.5282e-4 * T * R * R
        - 1.99e-6 * T * T * R * R
    )
    return round((HI_F - 32) / 1.8, 2)  # 转回摄氏度


def get_wind_beaufort(wind_speed: float | None) -> dict:
    """获取风速对应的 Beaufort 风级。"""
    if wind_speed is None:
        return {"beaufort": None, "description": "未知"}
    for limit, bf, desc in WIND_BEAUFORT:
        if wind_speed <= limit:
            return {"beaufort": bf, "description": desc}
    return {"beaufort": 12, "description": "飓风"}


# ---------- 工具函数 ----------

def _zscore(value: float | None, values: Iterable[float | None]) -> float:
    clean_values = [float(item) for item in values if item is not None]
    if value is None or len(clean_values) < 5:
        return 0.0

    std = pstdev(clean_values)
    if std == 0:
        return 0.0

    return abs((float(value) - mean(clean_values)) / std)


def _range_status(value: float | None, warning_range: tuple[float, float], critical_range: tuple[float, float]) -> str:
    if value is None:
        return "missing"

    low_critical, high_critical = critical_range
    low_warning, high_warning = warning_range
    if value < low_critical or value > high_critical:
        return "critical"
    if value < low_warning or value > high_warning:
        return "warning"
    return "normal"


def _rate_of_change(current: float | None, previous: float | None, hours: float) -> float | None:
    """计算单位小时变化率。"""
    if current is None or previous is None or hours <= 0:
        return None
    return (current - previous) / hours


# ---------- 时间维度分析 ----------

def _analyze_pressure_tendency(db: Session, record: models.SensorData) -> dict:
    """气压倾向分析：检测气压骤变和持续低压。"""
    alerts = []
    score = 0.0

    if record.pressure is None:
        return {"alerts": alerts, "score": score, "details": {}}

    rules = TIME_DIMENSION_RULES["pressure_tendency"]

    # 查询同设备时间窗口内的历史记录
    cutoff_3h = record.timestamp - timedelta(hours=rules["timeframe_hours"]) if record.timestamp else datetime.now(timezone.utc) - timedelta(hours=3)
    recent = (
        db.query(models.SensorData)
        .filter(
            models.SensorData.device_id == record.device_id,
            models.SensorData.timestamp < record.timestamp,
            models.SensorData.timestamp >= cutoff_3h,
        )
        .order_by(models.SensorData.timestamp.asc())
        .all()
    )

    earliest_pressure = recent[0].pressure if recent else None
    pressure_change = None
    if earliest_pressure is not None and record.pressure is not None:
        pressure_change = round(record.pressure - earliest_pressure, 2)

    details = {
        "window_hours": rules["timeframe_hours"],
        "historical_count": len(recent),
        "pressure_change_hpa": pressure_change,
    }

    # 气压骤降检测
    if pressure_change is not None and pressure_change <= -rules["rapid_drop_hpa"]:
        alerts.append({
            "type": "pressure_rapid_drop",
            "level": "warning",
            "message": f"气压在{rules['timeframe_hours']}小时内骤降 {abs(pressure_change):.1f} hPa，可能预示风暴或冷锋逼近，建议关注天气变化。",
        })
        score = max(score, 0.75)

    # 气压骤升检测
    if pressure_change is not None and pressure_change >= rules["rapid_rise_hpa"]:
        alerts.append({
            "type": "pressure_rapid_rise",
            "level": "warning",
            "message": f"气压在{rules['timeframe_hours']}小时内骤升 {pressure_change:.1f} hPa，天气将转晴但需注意气压突变带来的不适。",
        })
        score = max(score, 0.5)

    # 持续低压检测
    if record.pressure is not None and record.pressure < rules["sustained_low_hpa"]:
        # 检查是否持续：取最近6小时记录
        cutoff_6h = record.timestamp - timedelta(hours=6) if record.timestamp else datetime.now(timezone.utc) - timedelta(hours=6)
        sustained_count = (
            db.query(models.SensorData)
            .filter(
                models.SensorData.device_id == record.device_id,
                models.SensorData.timestamp >= cutoff_6h,
                models.SensorData.pressure < rules["sustained_low_hpa"],
            )
            .count()
        )
        details["sustained_low_count"] = sustained_count
        if sustained_count >= 2:
            alerts.append({
                "type": "pressure_sustained_low",
                "level": "critical",
                "message": f"气压持续低于 {rules['sustained_low_hpa']} hPa，可能处于风暴系统中，建议采取防护措施。",
            })
            score = max(score, 0.9)

    return {"alerts": alerts, "score": score, "details": details}


def _analyze_temp_rate_of_change(db: Session, record: models.SensorData) -> dict:
    """温度变化率分析：检测气温骤变。"""
    alerts = []
    score = 0.0

    if record.temperature is None:
        return {"alerts": alerts, "score": score, "details": {}}

    rules = TIME_DIMENSION_RULES["temp_rate_of_change"]

    cutoff_1h = record.timestamp - timedelta(hours=rules["timeframe_hours"]) if record.timestamp else datetime.now(timezone.utc) - timedelta(hours=1)
    prev_record = (
        db.query(models.SensorData)
        .filter(
            models.SensorData.device_id == record.device_id,
            models.SensorData.timestamp < record.timestamp,
            models.SensorData.timestamp >= cutoff_1h,
        )
        .order_by(models.SensorData.timestamp.desc())
        .first()
    )

    temp_change = None
    if prev_record and prev_record.temperature is not None:
        hours_diff = (record.timestamp - prev_record.timestamp).total_seconds() / 3600 if record.timestamp and prev_record.timestamp else 1.0
        temp_change = _rate_of_change(record.temperature, prev_record.temperature, max(hours_diff, 0.1))

    details = {
        "window_hours": rules["timeframe_hours"],
        "temp_change_per_hour": round(temp_change, 2) if temp_change is not None else None,
    }

    if temp_change is not None:
        # 气温骤降 → 冷锋过境/寒潮
        if temp_change <= -rules["rapid_drop_c"]:
            alerts.append({
                "type": "temp_rapid_drop",
                "level": "warning",
                "message": f"温度在1小时内骤降 {abs(temp_change):.1f}°C，可能为冷锋过境或寒潮，注意防寒保暖。",
            })
            score = max(score, 0.7)
        # 气温骤升 → 暖锋逼近/焚风
        elif temp_change >= rules["rapid_rise_c"]:
            alerts.append({
                "type": "temp_rapid_rise",
                "level": "warning",
                "message": f"温度在1小时内骤升 {temp_change:.1f}°C，可能为暖锋逼近或焚风效应，注意防暑降温。",
            })
            score = max(score, 0.6)

    return {"alerts": alerts, "score": score, "details": details}


def _analyze_dew_point_spread(record: models.SensorData) -> dict:
    """露点差分析：检测雾/霜冻/高湿热风险。"""
    alerts = []
    score = 0.0

    if record.temperature is None or record.dew_point is None:
        return {"alerts": alerts, "score": score, "details": {}}

    rules = TIME_DIMENSION_RULES["dew_point_spread"]
    spread = round(record.temperature - record.dew_point, 2)

    details = {
        "dew_point": record.dew_point,
        "spread_c": spread,
    }

    # 露点差过小 → 浓雾/凝结风险
    if spread <= rules["fog_risk_spread_c"]:
        alerts.append({
            "type": "fog_risk",
            "level": "warning",
            "message": f"露点差仅 {spread:.1f}°C（温度 {record.temperature:.1f}°C，露点 {record.dew_point:.1f}°C），存在浓雾或凝结风险，注意能见度降低。",
        })
        score = max(score, 0.7)
        # 叠加霜冻风险
        if record.dew_point < rules["frost_risk_c"]:
            alerts.append({
                "type": "frost_risk",
                "level": "critical",
                "message": f"露点温度 {record.dew_point:.1f}°C 低于冰点且接近气温，存在霜冻风险。",
            })
            score = max(score, 0.85)

    # 高露点 → 高湿热不适
    if record.dew_point > rules["high_dew_point_c"]:
        alerts.append({
            "type": "high_dew_point",
            "level": "warning",
            "message": f"露点温度 {record.dew_point:.1f}°C (>20°C)，空气湿热黏腻，体感不适。",
        })
        score = max(score, 0.5)

    return {"alerts": alerts, "score": score, "details": details}


def _analyze_heat_index_danger(record: models.SensorData) -> dict:
    """热指数危险分析：检测高温高湿危险条件。"""
    alerts = []
    score = 0.0

    if record.heat_index is None:
        return {"alerts": alerts, "score": score, "details": {}}

    rules = TIME_DIMENSION_RULES["heat_index"]
    details = {"heat_index": record.heat_index}

    if record.heat_index >= rules["extreme_danger_hi"]:
        alerts.append({
            "type": "heat_index_extreme_danger",
            "level": "critical",
            "message": f"热指数 {record.heat_index:.1f}°C 达到极度危险级别，中暑风险极高，建议立即停止野外作业并采取降温措施。",
        })
        score = max(score, 0.95)
    elif record.heat_index >= rules["danger_hi"]:
        alerts.append({
            "type": "heat_index_danger",
            "level": "warning",
            "message": f"热指数 {record.heat_index:.1f}°C 达到危险级别，中暑风险较高，建议减少户外活动并注意补水。",
        })
        score = max(score, 0.8)

    return {"alerts": alerts, "score": score, "details": details}


def _analyze_consecutive_anomaly(db: Session, record: models.SensorData, current_is_anomaly: bool) -> dict:
    """连续异常模式分析：检测持续性风险和系统性问题。"""
    alerts = []
    score = 0.0

    rules = TIME_DIMENSION_RULES["consecutive_anomaly"]

    cutoff_time = record.timestamp - timedelta(hours=rules["lookback_hours"]) if record.timestamp else datetime.now(timezone.utc) - timedelta(hours=24)

    # 查询同设备24h内所有异常记录
    anomaly_records = (
        db.query(models.SensorData)
        .filter(
            models.SensorData.device_id == record.device_id,
            models.SensorData.timestamp >= cutoff_time,
            models.SensorData.is_anomaly.is_(True),
        )
        .order_by(models.SensorData.timestamp.desc())
        .all()
    )

    total_anomalies = len(anomaly_records)
    if current_is_anomaly and record.id not in {r.id for r in anomaly_records}:
        total_anomalies += 1

    # 检测连续异常
    consecutive_count = 0
    sorted_anomalies = sorted(anomaly_records, key=lambda r: r.timestamp, reverse=True)
    for anom in sorted_anomalies:
        if consecutive_count == 0:
            consecutive_count = 1
        elif anom.timestamp and sorted_anomalies[consecutive_count - 1].timestamp:
            diff_hours = abs((anom.timestamp - sorted_anomalies[consecutive_count - 1].timestamp).total_seconds()) / 3600
            if diff_hours <= 2:  # 相邻异常间隔2h内视为连续
                consecutive_count += 1
            else:
                break

    details = {
        "lookback_hours": rules["lookback_hours"],
        "total_window_anomalies": total_anomalies,
        "consecutive_anomaly_count": consecutive_count,
    }

    # 连续异常判定
    if consecutive_count >= rules["min_consecutive"]:
        alerts.append({
            "type": "consecutive_anomaly",
            "level": "critical",
            "message": f"设备 {record.device_id} 已连续出现 {consecutive_count} 条异常记录，可能存在持续性环境风险或传感器故障，建议现场排查。",
        })
        score = max(score, 0.9)

    # 窗口内高频异常判定
    if total_anomalies >= rules["min_window_count"]:
        alerts.append({
            "type": "frequent_anomaly",
            "level": "warning",
            "message": f"设备 {record.device_id} 在 {rules['lookback_hours']} 小时内出现 {total_anomalies} 条异常，可能存在系统性问题。",
        })
        score = max(score, 0.75)

    return {"alerts": alerts, "score": score, "details": details}


def _analyze_multi_param_trend(db: Session, record: models.SensorData) -> dict:
    """多参数协同趋势分析：检测气象学经典模式。"""
    alerts = []
    score = 0.0

    rules = TIME_DIMENSION_RULES["multi_param_trend"]

    cutoff_3h = record.timestamp - timedelta(hours=3) if record.timestamp else datetime.now(timezone.utc) - timedelta(hours=3)
    prev_record = (
        db.query(models.SensorData)
        .filter(
            models.SensorData.device_id == record.device_id,
            models.SensorData.timestamp < record.timestamp,
            models.SensorData.timestamp >= cutoff_3h,
        )
        .order_by(models.SensorData.timestamp.asc())
        .first()
    )

    if not prev_record:
        return {"alerts": alerts, "score": score, "details": {}}

    details = {}
    temp_change = None
    pressure_change = None
    humidity_change = None

    if record.temperature is not None and prev_record.temperature is not None:
        temp_change = round(record.temperature - prev_record.temperature, 2)
        details["temp_change"] = temp_change

    if record.pressure is not None and prev_record.pressure is not None:
        pressure_change = round(record.pressure - prev_record.pressure, 2)
        details["pressure_change"] = pressure_change

    if record.humidity is not None and prev_record.humidity is not None:
        humidity_change = round(record.humidity - prev_record.humidity, 2)
        details["humidity_change"] = humidity_change

    # 模式1: 升温+降压 → 暖锋/低压系统逼近
    if temp_change is not None and pressure_change is not None:
        if temp_change >= 2.0 and pressure_change <= -1.5:
            alerts.append({
                "type": "warming_pressure_drop",
                "level": "warning",
                "message": f"检测到升温(+{temp_change:.1f}°C)伴随降压({pressure_change:.1f}hPa)趋势，符合暖锋或低压系统逼近的典型气象模式，可能出现降水或强对流天气。",
            })
            score = max(score, 0.75)

        # 模式2: 降温+升压 → 冷锋过境后/高压控制
        if temp_change <= -3.0 and pressure_change >= 2.0:
            alerts.append({
                "type": "cooling_pressure_rise",
                "level": "warning",
                "message": f"检测到降温({temp_change:.1f}°C)伴随升压(+{pressure_change:.1f}hPa)趋势，符合冷锋过境后的高压控制模式，天气转晴但气温偏低。",
            })
            score = max(score, 0.5)

    # 模式3: 升温+降湿 → 干燥热风/焚风效应
    if temp_change is not None and humidity_change is not None:
        if temp_change >= 2.0 and humidity_change <= -10.0:
            alerts.append({
                "type": "hot_dry_wind",
                "level": "warning",
                "message": f"检测到升温(+{temp_change:.1f}°C)伴随湿度骤降({humidity_change:.1f}%)，符合干燥热风或焚风效应的气象特征，注意防火和保湿。",
            })
            score = max(score, 0.65)

    return {"alerts": alerts, "score": score, "details": details}


def _analyze_wind_pattern(record: models.SensorData) -> dict:
    """风速风向分析。"""
    alerts = []
    score = 0.0

    if record.wind_speed is None:
        return {"alerts": alerts, "score": score, "details": {}}

    beaufort = get_wind_beaufort(record.wind_speed)
    details = {
        "wind_speed": record.wind_speed,
        "wind_direction": record.wind_direction,
        "beaufort_scale": beaufort["beaufort"],
        "beaufort_desc": beaufort["description"],
    }

    # 大风预警（≥6级强风）
    if beaufort["beaufort"] is not None and beaufort["beaufort"] >= 6:
        level = "warning" if beaufort["beaufort"] < 8 else "critical"
        alerts.append({
            "type": "high_wind",
            "level": level,
            "message": f"当前风速 {record.wind_speed:.1f} m/s，达到 {beaufort['description']}（{beaufort['beaufort']}级），{'影响野外作业安全' if beaufort['beaufort'] < 8 else '可能造成破坏性影响'}。",
        })
        score = max(score, 0.7 if beaufort["beaufort"] < 8 else 0.9)

    return {"alerts": alerts, "score": score, "details": details}


# ---------- 主分析函数 ----------

def analyze_sensor_record(db: Session, record: models.SensorData) -> dict:
    """基于历史分布、环境阈值和时间维度生成综合异常评分。"""

    # ---- 基础：z-score + 环境阈值 ----
    recent_records = (
        db.query(models.SensorData)
        .filter(models.SensorData.device_id == record.device_id)
        .order_by(models.SensorData.timestamp.desc())
        .limit(100)
        .all()
    )

    zscore_features = ("temperature", "humidity", "pm25", "pressure")
    zscores = {
        feature: _zscore(getattr(record, feature), [getattr(item, feature) for item in recent_records])
        for feature in zscore_features
    }
    rule_statuses = {
        feature: _range_status(
            getattr(record, feature),
            tuple(rule["warning"]),
            tuple(rule["critical"]),
        )
        for feature, rule in ENVIRONMENT_RULES.items()
    }
    rule_hits = {feature: status in {"warning", "critical"} for feature, status in rule_statuses.items()}
    triggered_rules = {
        feature: status
        for feature, status in rule_statuses.items()
        if status in {"warning", "critical"}
    }

    max_zscore = max(zscores.values(), default=0.0)
    if "critical" in triggered_rules.values():
        rule_score = 1.0
    elif "warning" in triggered_rules.values():
        rule_score = 0.8
    else:
        rule_score = 0.0
    base_score = min(1.0, max(max_zscore / 4.0, rule_score))
    base_is_anomaly = base_score >= 0.75

    # ---- 时间维度分析 ----
    time_analyses = {}
    all_time_alerts = []
    time_score = 0.0

    # 气压倾向
    pres_result = _analyze_pressure_tendency(db, record)
    time_analyses["pressure_tendency"] = pres_result
    all_time_alerts.extend(pres_result["alerts"])
    time_score = max(time_score, pres_result["score"])

    # 温度变化率
    temp_result = _analyze_temp_rate_of_change(db, record)
    time_analyses["temp_rate_of_change"] = temp_result
    all_time_alerts.extend(temp_result["alerts"])
    time_score = max(time_score, temp_result["score"])

    # 露点差
    dew_result = _analyze_dew_point_spread(record)
    time_analyses["dew_point_spread"] = dew_result
    all_time_alerts.extend(dew_result["alerts"])
    time_score = max(time_score, dew_result["score"])

    # 热指数
    hi_result = _analyze_heat_index_danger(record)
    time_analyses["heat_index_danger"] = hi_result
    all_time_alerts.extend(hi_result["alerts"])
    time_score = max(time_score, hi_result["score"])

    # 风速风向
    wind_result = _analyze_wind_pattern(record)
    time_analyses["wind_pattern"] = wind_result
    all_time_alerts.extend(wind_result["alerts"])
    time_score = max(time_score, wind_result["score"])

    # 多参数协同趋势
    trend_result = _analyze_multi_param_trend(db, record)
    time_analyses["multi_param_trend"] = trend_result
    all_time_alerts.extend(trend_result["alerts"])
    time_score = max(time_score, trend_result["score"])

    # ---- 综合评分 ----
    # 基础评分和时间维度评分取最大值，时间维度可提升整体评分
    anomaly_score = round(max(base_score, time_score, (base_score + time_score) / 2), 4)
    is_anomaly = anomaly_score >= 0.75

    # 连续异常分析（需要知道最终 is_anomaly 状态）
    consec_result = _analyze_consecutive_anomaly(db, record, is_anomaly)
    time_analyses["consecutive_anomaly"] = consec_result
    all_time_alerts.extend(consec_result["alerts"])
    if consec_result["score"] > anomaly_score:
        anomaly_score = round(max(anomaly_score, consec_result["score"]), 4)
        is_anomaly = anomaly_score >= 0.75

    metadata = {
        "model_version": AI_MODEL_VERSION,
        "algorithm": "zscore+environment-threshold+time-dimension",
        "features": list(ENVIRONMENT_RULES.keys()),
        "zscores": {key: round(value, 3) for key, value in zscores.items()},
        "rule_hits": rule_hits,
        "rule_statuses": rule_statuses,
        "triggered_rules": triggered_rules,
        "time_dimension": time_analyses,
        "time_dimension_alerts": all_time_alerts,
        "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
    }

    return {
        "is_anomaly": is_anomaly,
        "anomaly_score": anomaly_score,
        "ai_metadata": metadata,
        "time_dimension_alerts": all_time_alerts,
    }


def build_local_summary(record: models.SensorData) -> str:
    status = "存在异常风险" if record.is_anomaly else "未发现明显异常"
    triggered_rules = (record.ai_metadata or {}).get("triggered_rules") or {}
    reasons = []
    for feature, level in triggered_rules.items():
        label = ENVIRONMENT_RULES.get(feature, {}).get("label", feature)
        level_text = "严重越界" if level == "critical" else "超出建议范围"
        reasons.append(f"{label}{level_text}")

    # 加入时间维度告警
    time_alerts = (record.ai_metadata or {}).get("time_dimension_alerts") or []
    for alert in time_alerts:
        reasons.append(alert.get("message", ""))

    reason_text = f"触发规则：{'、'.join(reasons)}。" if reasons else ""

    dew_str = f"，露点温度 {record.dew_point:.1f}°C" if record.dew_point is not None else ""
    hi_str = f"，热指数 {record.heat_index:.1f}°C" if record.heat_index is not None else ""
    wind_str = f"，风速 {record.wind_speed:.1f} m/s" if record.wind_speed is not None else ""

    return (
        f"{record.device_id} 在 {record.timestamp:%Y-%m-%d %H:%M} 的监测数据显示："
        f"温度 {record.temperature:.1f}°C，湿度 {record.humidity:.1f}%，PM2.5 {record.pm25:.1f}，"
        f"气压 {record.pressure:.1f} hPa{dew_str}{hi_str}{wind_str}。"
        f"AI 判定{status}，异常评分 {record.anomaly_score:.2f}。{reason_text}"
    )


def generate_llm_summary(record: models.SensorData) -> str:
    """优先调用兼容 OpenAI 协议的 LLM；未配置时使用本地摘要。"""
    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("AI_LLM_BASE_URL", "https://api.deepseek.com/v1")
    model = os.getenv("AI_LLM_MODEL", "deepseek-chat")
    if not api_key:
        return build_local_summary(record)

    prompt = (
        "请用一句中文调查报告风格文字总结这条野外传感器数据，"
        "包含异常状态、主要环境指标、时间维度气象分析结论和现场建议。"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是野外环境调查数据分析助手，精通气象学时间维度分析。"},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "device_id": record.device_id,
                        "timestamp": record.timestamp.isoformat(),
                        "temperature": record.temperature,
                        "humidity": record.humidity,
                        "pm25": record.pm25,
                        "pressure": record.pressure,
                        "dew_point": record.dew_point,
                        "heat_index": record.heat_index,
                        "wind_speed": record.wind_speed,
                        "wind_direction": record.wind_direction,
                        "is_anomaly": record.is_anomaly,
                        "anomaly_score": record.anomaly_score,
                        "time_dimension_alerts": (record.ai_metadata or {}).get("time_dimension_alerts", []),
                    },
                    ensure_ascii=False,
                )
                + "\n"
                + prompt,
            },
        ],
        "temperature": 0.2,
        "max_tokens": 250,
    }

    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        return f"{build_local_summary(record)} LLM 摘要生成失败，已回退到本地规则摘要：{exc}"


def enrich_record_ai(record_id: int) -> None:
    from .database import SessionLocal

    db = SessionLocal()
    try:
        record = db.query(models.SensorData).filter(models.SensorData.id == record_id).first()
        if not record:
            return

        has_llm_key = bool(os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY"))
        summary_provider = (record.ai_metadata or {}).get("summary_provider")
        if not record.ai_summary or (has_llm_key and summary_provider != "llm"):
            record.ai_summary = generate_llm_summary(record)
            metadata = dict(record.ai_metadata or {})
            metadata["summary_provider"] = "llm" if has_llm_key else "local"
            record.ai_metadata = metadata
            db.commit()
    finally:
        db.close()
