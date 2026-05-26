from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class SensorDataBase(BaseModel):
    device_id: str
    temperature: float
    humidity: float
    pm25: float
    pressure: float
    latitude: float
    longitude: float
    timestamp: Optional[datetime] = None

class SensorDataCreate(SensorDataBase):
    pass

class SensorData(SensorDataBase):
    id: int

    class Config:
        from_attributes = True

class Stats(BaseModel):
    count: int
    avg_temp: float
    avg_hum: float
