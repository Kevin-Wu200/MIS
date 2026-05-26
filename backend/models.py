from sqlalchemy import Boolean, Column, DateTime, Float, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from .database import Base

class SensorData(Base):
    __tablename__ = "sensor_data"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.now)
    temperature = Column(Float)
    humidity = Column(Float)
    pm25 = Column(Float)
    pressure = Column(Float)
    dew_point = Column(Float)
    heat_index = Column(Float)
    wind_speed = Column(Float)
    wind_direction = Column(Float)
    latitude = Column(Float)
    longitude = Column(Float)
    is_anomaly = Column(Boolean, nullable=False, default=False, index=True)
    anomaly_score = Column(Float, nullable=False, default=0.0)
    ai_summary = Column(Text)
    ai_metadata = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict)
