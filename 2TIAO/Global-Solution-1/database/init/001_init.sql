CREATE TABLE IF NOT EXISTS communities (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  location TEXT,
  scenario TEXT,
  expected_risk TEXT
);

CREATE TABLE IF NOT EXISTS water_readings (
  id SERIAL PRIMARY KEY,
  community_id INTEGER REFERENCES communities(id),
  device_id TEXT NOT NULL,
  ph NUMERIC,
  turbidity NUMERIC,
  temperature NUMERIC,
  hardness NUMERIC,
  solids NUMERIC,
  chloramines NUMERIC,
  sulfate NUMERIC,
  conductivity NUMERIC,
  organic_carbon NUMERIC,
  trihalomethanes NUMERIC,
  ml_turbidity NUMERIC,
  network_switch TEXT,
  ml_potability_prediction INTEGER,
  ml_potability_probability NUMERIC,
  ml_quality_label TEXT,
  ml_model_name TEXT,
  edge_risk TEXT,
  source TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE water_readings ADD COLUMN IF NOT EXISTS hardness NUMERIC;
ALTER TABLE water_readings ADD COLUMN IF NOT EXISTS solids NUMERIC;
ALTER TABLE water_readings ADD COLUMN IF NOT EXISTS chloramines NUMERIC;
ALTER TABLE water_readings ADD COLUMN IF NOT EXISTS sulfate NUMERIC;
ALTER TABLE water_readings ADD COLUMN IF NOT EXISTS conductivity NUMERIC;
ALTER TABLE water_readings ADD COLUMN IF NOT EXISTS organic_carbon NUMERIC;
ALTER TABLE water_readings ADD COLUMN IF NOT EXISTS trihalomethanes NUMERIC;
ALTER TABLE water_readings ADD COLUMN IF NOT EXISTS ml_turbidity NUMERIC;
ALTER TABLE water_readings ADD COLUMN IF NOT EXISTS network_switch TEXT;
ALTER TABLE water_readings ADD COLUMN IF NOT EXISTS ml_potability_prediction INTEGER;
ALTER TABLE water_readings ADD COLUMN IF NOT EXISTS ml_potability_probability NUMERIC;
ALTER TABLE water_readings ADD COLUMN IF NOT EXISTS ml_quality_label TEXT;
ALTER TABLE water_readings ADD COLUMN IF NOT EXISTS ml_model_name TEXT;

CREATE TABLE IF NOT EXISTS visual_analyses (
  id SERIAL PRIMARY KEY,
  community_id INTEGER REFERENCES communities(id),
  device_id TEXT NOT NULL,
  image_name TEXT,
  visual_class TEXT,
  visual_turbidity_score NUMERIC,
  particles_detected INTEGER,
  dominant_color TEXT,
  model_name TEXT,
  model_class TEXT,
  model_confidence NUMERIC,
  pollution_score NUMERIC,
  source TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE visual_analyses ADD COLUMN IF NOT EXISTS model_name TEXT;
ALTER TABLE visual_analyses ADD COLUMN IF NOT EXISTS model_class TEXT;
ALTER TABLE visual_analyses ADD COLUMN IF NOT EXISTS model_confidence NUMERIC;
ALTER TABLE visual_analyses ADD COLUMN IF NOT EXISTS pollution_score NUMERIC;

CREATE TABLE IF NOT EXISTS alerts (
  id SERIAL PRIMARY KEY,
  community_id INTEGER REFERENCES communities(id),
  severity TEXT NOT NULL,
  message TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO communities (id, name, location, scenario, expected_risk)
VALUES
  (1, 'Comunidade Aurora', 'Regiao ribeirinha', 'Captacao de agua superficial', 'Turbidez e sedimentos'),
  (2, 'Comunidade Horizonte', 'Regiao rural', 'Poco artesiano comunitario', 'pH fora da faixa ideal'),
  (3, 'Comunidade Vega', 'Abrigo temporario', 'Reservatorio compartilhado', 'Variacao de temperatura e alerta operacional')
ON CONFLICT (id) DO NOTHING;
