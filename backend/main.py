from fastapi import BackgroundTasks, FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from . import ai, database, models, schemas

# 初始化数据库表
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="MIS Field Survey API")

# 配置 CORS，允许 Vue 前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/data", response_model=List[schemas.SensorData])
def get_all_data(db: Session = Depends(database.get_db)):
    return db.query(models.SensorData).order_by(models.SensorData.timestamp.desc()).all()

@app.post("/api/data", response_model=schemas.SensorData)
def create_record(
    data: schemas.SensorDataCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(database.get_db),
):
    # 自动计算衍生气象参数
    dew_point = data.dew_point
    heat_index = data.heat_index
    if dew_point is None and data.temperature is not None and data.humidity is not None:
        dew_point = round(ai.calc_dew_point(data.temperature, data.humidity), 2)
    if heat_index is None and data.temperature is not None and data.humidity is not None:
        heat_index = ai.calc_heat_index(data.temperature, data.humidity)

    db_record = models.SensorData(
        **data.dict(),
        dew_point=dew_point,
        heat_index=heat_index,
    )
    db.add(db_record)
    db.flush()
    ai_result = ai.analyze_sensor_record(db, db_record)
    db_record.is_anomaly = ai_result["is_anomaly"]
    db_record.anomaly_score = ai_result["anomaly_score"]
    db_record.ai_metadata = ai_result["ai_metadata"]
    db_record.ai_summary = ai.build_local_summary(db_record)
    db_record.ai_metadata = {**db_record.ai_metadata, "summary_provider": "local"}
    db.commit()
    db.refresh(db_record)
    background_tasks.add_task(ai.enrich_record_ai, db_record.id)

    # 在响应中包含时间维度告警
    response_data = schemas.SensorData.from_orm(db_record)
    response_data.time_dimension_alerts = ai_result.get("time_dimension_alerts", [])
    return response_data

@app.delete("/api/data/{record_id}")
def delete_record(record_id: int, db: Session = Depends(database.get_db)):
    record = db.query(models.SensorData).filter(models.SensorData.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    db.delete(record)
    db.commit()
    return {"message": "Success"}

@app.get("/api/stats", response_model=schemas.Stats)
def get_stats(db: Session = Depends(database.get_db)):
    count = db.query(func.count(models.SensorData.id)).scalar()
    avg_temp = db.query(func.avg(models.SensorData.temperature)).scalar() or 0
    avg_hum = db.query(func.avg(models.SensorData.humidity)).scalar() or 0
    avg_pm25 = db.query(func.avg(models.SensorData.pm25)).scalar() or 0
    avg_pressure = db.query(func.avg(models.SensorData.pressure)).scalar() or 0
    avg_dew_point = db.query(func.avg(models.SensorData.dew_point)).scalar() or 0
    avg_heat_index = db.query(func.avg(models.SensorData.heat_index)).scalar() or 0
    avg_wind_speed = db.query(func.avg(models.SensorData.wind_speed)).scalar() or 0
    anomaly_count = db.query(func.count(models.SensorData.id)).filter(models.SensorData.is_anomaly.is_(True)).scalar()
    return {
        "count": count,
        "avg_temp": round(avg_temp, 2),
        "avg_hum": round(avg_hum, 2),
        "avg_pm25": round(avg_pm25, 2),
        "avg_pressure": round(avg_pressure, 2),
        "avg_dew_point": round(avg_dew_point, 2),
        "avg_heat_index": round(avg_heat_index, 2),
        "avg_wind_speed": round(avg_wind_speed, 2),
        "anomaly_count": anomaly_count or 0,
    }

@app.get("/api/ai/insights", response_model=schemas.AIInsights)
def get_ai_insights(db: Session = Depends(database.get_db)):
    anomaly_count = db.query(func.count(models.SensorData.id)).filter(models.SensorData.is_anomaly.is_(True)).scalar() or 0
    avg_anomaly_score = db.query(func.avg(models.SensorData.anomaly_score)).scalar() or 0
    latest_anomaly = (
        db.query(models.SensorData)
        .filter(models.SensorData.is_anomaly.is_(True))
        .order_by(models.SensorData.timestamp.desc())
        .first()
    )

    # 收集最近时间维度告警
    time_dimension_alerts = []
    recent_anomalies = (
        db.query(models.SensorData)
        .filter(models.SensorData.is_anomaly.is_(True))
        .order_by(models.SensorData.timestamp.desc())
        .limit(10)
        .all()
    )
    seen_alerts = set()
    for record in recent_anomalies:
        alerts = (record.ai_metadata or {}).get("time_dimension_alerts", [])
        for alert in alerts:
            alert_key = alert.get("type", "")
            if alert_key and alert_key not in seen_alerts:
                seen_alerts.add(alert_key)
                time_dimension_alerts.append(alert)

    if latest_anomaly:
        summary = latest_anomaly.ai_summary or ai.build_local_summary(latest_anomaly)
    elif anomaly_count == 0:
        summary = "当前数据未发现明显异常，环境指标整体处于可接受范围。"
    else:
        summary = "已检测到异常记录，建议查看异常明细并复核现场采样条件。"

    return {
        "summary": summary,
        "anomaly_count": anomaly_count,
        "avg_anomaly_score": round(avg_anomaly_score, 4),
        "latest_anomaly": latest_anomaly,
        "time_dimension_alerts": time_dimension_alerts,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
