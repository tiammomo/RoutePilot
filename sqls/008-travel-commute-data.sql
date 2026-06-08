CREATE TABLE IF NOT EXISTS travel_pois (
  poi_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  city TEXT NOT NULL DEFAULT 'beijing',
  district TEXT,
  area TEXT,
  category TEXT,
  poi_type TEXT,
  poi_kind TEXT NOT NULL DEFAULT 'attraction',
  address TEXT,
  lng DOUBLE PRECISION NOT NULL,
  lat DOUBLE PRECISION NOT NULL,
  rating DOUBLE PRECISION,
  avg_cost DOUBLE PRECISION,
  review_count INTEGER,
  source TEXT NOT NULL DEFAULT 'travel-data/processed',
  raw JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_travel_pois_area ON travel_pois(area);
CREATE INDEX IF NOT EXISTS idx_travel_pois_type ON travel_pois(poi_type);
CREATE INDEX IF NOT EXISTS idx_travel_pois_kind ON travel_pois(poi_kind);
CREATE INDEX IF NOT EXISTS idx_travel_pois_lng_lat ON travel_pois(lng, lat);

CREATE TABLE IF NOT EXISTS travel_commute_edges (
  id TEXT PRIMARY KEY,
  origin_poi_id TEXT NOT NULL REFERENCES travel_pois(poi_id) ON DELETE CASCADE,
  destination_poi_id TEXT NOT NULL REFERENCES travel_pois(poi_id) ON DELETE CASCADE,
  mode TEXT NOT NULL,
  relation_type TEXT NOT NULL DEFAULT 'attraction_attraction',
  provider TEXT NOT NULL DEFAULT 'amap',
  status TEXT NOT NULL DEFAULT 'ok',
  distance_m INTEGER,
  duration_s INTEGER,
  cost_cny DOUBLE PRECISION,
  walking_distance_m INTEGER,
  transfer_count INTEGER,
  route_summary TEXT,
  raw JSONB NOT NULL DEFAULT '{}'::jsonb,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(origin_poi_id, destination_poi_id, mode, provider, relation_type)
);

CREATE INDEX IF NOT EXISTS idx_travel_commute_edges_origin ON travel_commute_edges(origin_poi_id);
CREATE INDEX IF NOT EXISTS idx_travel_commute_edges_destination ON travel_commute_edges(destination_poi_id);
CREATE INDEX IF NOT EXISTS idx_travel_commute_edges_relation ON travel_commute_edges(relation_type);
CREATE INDEX IF NOT EXISTS idx_travel_commute_edges_mode_duration ON travel_commute_edges(mode, duration_s);
CREATE INDEX IF NOT EXISTS idx_travel_commute_edges_status ON travel_commute_edges(status);

CREATE TABLE IF NOT EXISTS travel_commute_fetch_runs (
  id TEXT PRIMARY KEY,
  provider TEXT NOT NULL DEFAULT 'amap',
  mode_list TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  poi_count INTEGER NOT NULL DEFAULT 0,
  pair_count INTEGER NOT NULL DEFAULT 0,
  success_count INTEGER NOT NULL DEFAULT 0,
  failed_count INTEGER NOT NULL DEFAULT 0,
  skipped_count INTEGER NOT NULL DEFAULT 0,
  options JSONB NOT NULL DEFAULT '{}'::jsonb,
  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);
