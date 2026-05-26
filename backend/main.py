from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from . import models, schemas, database

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
def create_record(data: schemas.SensorDataCreate, db: Session = Depends(database.get_db)):
    db_record = models.SensorData(**data.dict())
    db.add(db_record)
    db.commit()
    db.refresh(db_record)
    return db_record

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
    return {
        "count": count,
        "avg_temp": round(avg_temp, 2),
        "avg_hum": round(avg_hum, 2)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
