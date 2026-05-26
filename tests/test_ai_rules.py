import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import ai
from datetime import datetime


class EmptyQuery:
    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def all(self):
        return []

    def first(self):
        return None

    def count(self):
        return 0

    def __iter__(self):
        return iter([])

    def __len__(self):
        return 0


class EmptyDb:
    def query(self, *args, **kwargs):
        return EmptyQuery()


def analyze(**overrides):
    values = {
        "id": 1,
        "device_id": "TEST-001",
        "timestamp": datetime(2025, 1, 15, 12, 0, 0),
        "temperature": 25.0,
        "humidity": 50.0,
        "pm25": 10.0,
        "pressure": 1013.25,
        "dew_point": None,
        "heat_index": None,
        "wind_speed": None,
        "wind_direction": None,
        "latitude": 31.23,
        "longitude": 121.47,
        "is_anomaly": False,
        "anomaly_score": 0.0,
    }
    values.update(overrides)
    # 确保 timestamp 是 datetime 对象
    if isinstance(values.get("timestamp"), str):
        values["timestamp"] = datetime.fromisoformat(values["timestamp"])
    return ai.analyze_sensor_record(EmptyDb(), SimpleNamespace(**values))


def test_warning_environment_values_are_anomalies():
    for field, value in [
        ("temperature", 0.0),
        ("humidity", 96.0),
        ("pm25", 50.0),
    ]:
        result = analyze(**{field: value})

        assert result["is_anomaly"] is True
        assert result["anomaly_score"] >= 0.75
        assert result["ai_metadata"]["triggered_rules"][field] == "warning"


def test_normal_environment_values_stay_normal():
    result = analyze()

    assert result["is_anomaly"] is False
    assert result["anomaly_score"] == 0.0
    assert result["ai_metadata"]["triggered_rules"] == {}


def test_dew_point_calculation():
    """测试 Magnus 公式计算露点温度"""
    dp = ai.calc_dew_point(25.0, 50.0)
    assert 13.0 < dp < 15.0, f"25°C 50%湿度露点应在~14°C附近，实际计算: {dp}"

    dp2 = ai.calc_dew_point(30.0, 80.0)
    assert 25.0 < dp2 < 28.0, f"30°C 80%湿度露点应在~26°C附近，实际计算: {dp2}"

    dp3 = ai.calc_dew_point(10.0, 30.0)
    assert -8.0 < dp3 < -5.0, f"10°C 30%湿度露点应在~-7°C附近，实际计算: {dp3}"


def test_heat_index_calculation():
    """测试热指数计算"""
    # 温度 <27°C 应返回 None
    hi = ai.calc_heat_index(25.0, 80.0)
    assert hi is None, "25°C 不应计算热指数"

    # 高温高湿应有热指数
    hi2 = ai.calc_heat_index(32.0, 70.0)
    assert hi2 is not None and hi2 > 32.0, f"32°C 70%湿度热指数应 >32°C，实际: {hi2}"


def test_dew_point_spread_fog_risk():
    """测试露点差：温度接近露点应产生浓雾风险告警"""
    result = analyze(
        temperature=15.0,
        humidity=94.0,
        dew_point=ai.calc_dew_point(15.0, 94.0),
    )
    time_alerts = result.get("time_dimension_alerts", [])
    fog_alerts = [a for a in time_alerts if a["type"] == "fog_risk"]
    assert len(fog_alerts) > 0, f"露点差过小应触发浓雾风险告警，实际告警: {time_alerts}"


def test_heat_index_danger_level():
    """测试热指数危险等级"""
    hi = ai.calc_heat_index(38.0, 80.0)
    if hi is not None and hi >= 40.0:
        result = analyze(
            temperature=38.0,
            humidity=80.0,
            heat_index=hi,
        )
        time_alerts = result.get("time_dimension_alerts", [])
        hi_alerts = [a for a in time_alerts if "heat_index" in a["type"]]
        assert len(hi_alerts) > 0, f"热指数危险应产生告警，实际告警: {time_alerts}"


def test_wind_beaufort():
    """测试风速风级转换"""
    result = ai.get_wind_beaufort(15.0)
    assert result["beaufort"] == 7, f"15m/s 应为7级疾风，实际: {result}"
    assert result["description"] == "疾风"

    result2 = ai.get_wind_beaufort(3.0)
    assert result2["beaufort"] == 2, f"3m/s 应为2级轻风，实际: {result2}"


def test_time_dimension_in_metadata():
    """测试 AI 元数据包含时间维度分析结果"""
    result = analyze(
        temperature=25.0,
        humidity=50.0,
        dew_point=ai.calc_dew_point(25.0, 50.0),
    )
    metadata = result["ai_metadata"]
    assert "time_dimension" in metadata
    assert "time_dimension_alerts" in metadata
    assert "pressure_tendency" in metadata["time_dimension"]
    assert "temp_rate_of_change" in metadata["time_dimension"]
    assert "dew_point_spread" in metadata["time_dimension"]
    assert "heat_index_danger" in metadata["time_dimension"]
    assert "multi_param_trend" in metadata["time_dimension"]
    assert "wind_pattern" in metadata["time_dimension"]


def test_model_version_updated():
    """测试模型版本已更新为时间维度版本"""
    result = analyze()
    assert result["ai_metadata"]["model_version"] == "rules-zscore-time-v3"
    assert "time-dimension" in result["ai_metadata"]["algorithm"]
