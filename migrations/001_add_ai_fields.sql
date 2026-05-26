BEGIN;

ALTER TABLE sensor_data
  ADD COLUMN IF NOT EXISTS is_anomaly BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS anomaly_score DOUBLE PRECISION NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS ai_summary TEXT,
  ADD COLUMN IF NOT EXISTS ai_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_sensor_data_is_anomaly
  ON sensor_data (is_anomaly);

CREATE INDEX IF NOT EXISTS idx_sensor_data_anomaly_score
  ON sensor_data (anomaly_score DESC);

CREATE INDEX IF NOT EXISTS idx_sensor_data_ai_metadata
  ON sensor_data USING GIN (ai_metadata);

COMMIT;
