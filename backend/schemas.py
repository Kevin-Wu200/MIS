from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any, Dict, List, Optional

class SensorDataBase(BaseModel):
    device_id: str
    temperature: float
    humidity: float
    pm25: float
    pressure: float
    dew_point: Optional[float] = None
    heat_index: Optional[float] = None
    wind_speed: Optional[float] = None
    wind_direction: Optional[float] = None
    latitude: float
    longitude: float
    timestamp: Optional[datetime] = None

class SensorDataCreate(SensorDataBase):
    pass

class SensorData(SensorDataBase):
    id: int
    is_anomaly: bool = False
    anomaly_score: float = 0.0
    ai_summary: Optional[str] = None
    ai_metadata: Dict[str, Any] = Field(default_factory=dict)
    time_dimension_alerts: List[Dict[str, Any]] = Field(default_factory=list)

    class Config:
        from_attributes = True

class Stats(BaseModel):
    count: int
    avg_temp: float
    avg_hum: float
    anomaly_count: int = 0
    avg_pm25: float = 0.0
    avg_pressure: float = 0.0
    avg_dew_point: float = 0.0
    avg_heat_index: float = 0.0
    avg_wind_speed: float = 0.0

class AIInsights(BaseModel):
    summary: str
    anomaly_count: int
    avg_anomaly_score: float
    latest_anomaly: Optional[SensorData] = None
    time_dimension_alerts: list = Field(default_factory=list)
