CREATE TABLE IF NOT EXISTS travel_precomputed_routes (
  route_id TEXT PRIMARY KEY,
  city_id TEXT NOT NULL DEFAULT 'beijing',
  title TEXT NOT NULL,
  area TEXT,
  route_mode TEXT NOT NULL DEFAULT 'mixed',
  persona_id TEXT NOT NULL DEFAULT 'classic_first_timer',
  walk_preference TEXT NOT NULL DEFAULT 'medium',
  duration_bucket_min INTEGER NOT NULL,
  budget_bucket_cny INTEGER,
  requires_meal BOOLEAN NOT NULL DEFAULT TRUE,
  meal_type TEXT,
  indoor_preferred BOOLEAN NOT NULL DEFAULT FALSE,
  avoid_queue BOOLEAN NOT NULL DEFAULT FALSE,
  tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  poi_ids TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  poi_names TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  total_budget_estimate DOUBLE PRECISION NOT NULL DEFAULT 0,
  total_route_duration_min INTEGER NOT NULL DEFAULT 0,
  score DOUBLE PRECISION NOT NULL DEFAULT 0,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  source TEXT NOT NULL DEFAULT 'travel-data/processed/beijing_route_corpus.json',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_travel_precomputed_routes_city ON travel_precomputed_routes(city_id);
CREATE INDEX IF NOT EXISTS idx_travel_precomputed_routes_area ON travel_precomputed_routes(area);
CREATE INDEX IF NOT EXISTS idx_travel_precomputed_routes_mode ON travel_precomputed_routes(route_mode);
CREATE INDEX IF NOT EXISTS idx_travel_precomputed_routes_persona ON travel_precomputed_routes(persona_id);
CREATE INDEX IF NOT EXISTS idx_travel_precomputed_routes_duration ON travel_precomputed_routes(duration_bucket_min);
CREATE INDEX IF NOT EXISTS idx_travel_precomputed_routes_budget ON travel_precomputed_routes(budget_bucket_cny);
CREATE INDEX IF NOT EXISTS idx_travel_precomputed_routes_tags ON travel_precomputed_routes USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_travel_precomputed_routes_poi_ids ON travel_precomputed_routes USING GIN(poi_ids);
