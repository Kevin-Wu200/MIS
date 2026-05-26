import os
import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

class DatabaseManager:
    def __init__(self):
        self.engine = create_engine(os.getenv("DATABASE_URL"))
        self._create_table()

    def _create_table(self):
        """初始化表结构（如果不存在）"""
        query = text("""
        CREATE TABLE IF NOT EXISTS sensor_data (
            id SERIAL PRIMARY KEY,
            device_id TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            temperature REAL,
            humidity REAL,
            pm25 REAL,
            pressure REAL,
            latitude REAL,
            longitude REAL
        )
        """)
        with self.engine.begin() as conn:
            conn.execute(query)

    def fetch_all_data(self):
        """获取所有数据并返回 DataFrame"""
        query = text("SELECT * FROM sensor_data ORDER BY timestamp DESC")
        with self.engine.connect() as conn:
            return pd.read_sql_query(query, conn)

    def add_record(self, device_id, temperature, humidity, pm25, pressure, latitude, longitude, timestamp=None):
        """添加一条新记录"""
        if timestamp is None:
            timestamp = datetime.now()
        
        query = text("""
        INSERT INTO sensor_data (device_id, timestamp, temperature, humidity, pm25, pressure, latitude, longitude)
        VALUES (:device_id, :timestamp, :temperature, :humidity, :pm25, :pressure, :latitude, :longitude)
        """)
        
        params = {
            "device_id": device_id,
            "timestamp": timestamp,
            "temperature": temperature,
            "humidity": humidity,
            "pm25": pm25,
            "pressure": pressure,
            "latitude": latitude,
            "longitude": longitude
        }
        
        with self.engine.begin() as conn:
            conn.execute(query, params)

    def delete_record(self, record_id):
        """根据 ID 删除记录"""
        query = text("DELETE FROM sensor_data WHERE id = :id")
        with self.engine.begin() as conn:
            conn.execute(query, {"id": record_id})

    def get_stats(self):
        """获取简单的统计信息"""
        query = text("SELECT COUNT(*) as count, AVG(temperature) as avg_temp, AVG(humidity) as avg_hum FROM sensor_data")
        with self.engine.connect() as conn:
            return pd.read_sql_query(query, conn).iloc[0]
