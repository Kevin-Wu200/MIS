from sqlalchemy import Column, Integer, String, Float, DateTime
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
    latitude = Column(Float)
    longitude = Column(Float)
