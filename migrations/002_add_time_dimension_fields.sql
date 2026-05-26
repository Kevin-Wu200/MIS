BEGIN;

-- 新增气象学时间维度相关参数
ALTER TABLE sensor_data
  ADD COLUMN IF NOT EXISTS dew_point REAL,
  ADD COLUMN IF NOT EXISTS heat_index REAL,
  ADD COLUMN IF NOT EXISTS wind_speed REAL,
  ADD COLUMN IF NOT EXISTS wind_direction REAL;

-- 为时间维度查询优化索引（device_id + timestamp 联合索引）
CREATE INDEX IF NOT EXISTS idx_sensor_data_device_timestamp
  ON sensor_data (device_id, timestamp);

COMMIT;
