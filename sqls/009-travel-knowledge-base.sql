ALTER TABLE travel_pois
  ADD COLUMN IF NOT EXISTS source_poi_id TEXT,
  ADD COLUMN IF NOT EXISTS entity_kind TEXT,
  ADD COLUMN IF NOT EXISTS display_name TEXT,
  ADD COLUMN IF NOT EXISTS normalized_name TEXT,
  ADD COLUMN IF NOT EXISTS alias_names JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS area_key TEXT,
  ADD COLUMN IF NOT EXISTS poi_subtype TEXT,
  ADD COLUMN IF NOT EXISTS tags JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS suggested_duration_min INTEGER,
  ADD COLUMN IF NOT EXISTS open_time TEXT,
  ADD COLUMN IF NOT EXISTS close_time TEXT,
  ADD COLUMN IF NOT EXISTS open_hours JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS meal_type TEXT,
  ADD COLUMN IF NOT EXISTS is_lunch_suitable BOOLEAN,
  ADD COLUMN IF NOT EXISTS is_coffee_stop BOOLEAN,
  ADD COLUMN IF NOT EXISTS is_meal_stop BOOLEAN,
  ADD COLUMN IF NOT EXISTS walk_intensity TEXT;

CREATE INDEX IF NOT EXISTS idx_travel_pois_area_key ON travel_pois(area_key);
CREATE INDEX IF NOT EXISTS idx_travel_pois_poi_subtype ON travel_pois(poi_subtype);
CREATE INDEX IF NOT EXISTS idx_travel_pois_avg_cost ON travel_pois(avg_cost);
CREATE INDEX IF NOT EXISTS idx_travel_pois_rating ON travel_pois(rating);
CREATE INDEX IF NOT EXISTS idx_travel_pois_suggested_duration ON travel_pois(suggested_duration_min);
CREATE INDEX IF NOT EXISTS idx_travel_pois_walk_intensity ON travel_pois(walk_intensity);

CREATE TABLE IF NOT EXISTS travel_poi_features (
  id TEXT PRIMARY KEY,
  poi_id TEXT NOT NULL REFERENCES travel_pois(poi_id) ON DELETE CASCADE,
  feature_key TEXT NOT NULL,
  feature_value TEXT NOT NULL,
  status TEXT,
  confidence TEXT,
  evidence_refs TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  review_count_used INTEGER,
  source_platforms TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  source_weight DOUBLE PRECISION,
  ugc_coverage_level TEXT,
  evidence_quality TEXT,
  extraction_version TEXT,
  last_computed DATE,
  raw JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(poi_id, feature_key)
);

CREATE INDEX IF NOT EXISTS idx_travel_poi_features_poi ON travel_poi_features(poi_id);
CREATE INDEX IF NOT EXISTS idx_travel_poi_features_key_value ON travel_poi_features(feature_key, feature_value);
CREATE INDEX IF NOT EXISTS idx_travel_poi_features_confidence ON travel_poi_features(confidence);

CREATE TABLE IF NOT EXISTS travel_reviews (
  review_id TEXT PRIMARY KEY,
  poi_id TEXT NOT NULL REFERENCES travel_pois(poi_id) ON DELETE CASCADE,
  source_platform TEXT,
  source_review_id TEXT,
  review_text TEXT NOT NULL,
  rating DOUBLE PRECISION,
  review_time DATE,
  author_name TEXT,
  evidence_source JSONB NOT NULL DEFAULT '[]'::jsonb,
  raw JSONB NOT NULL DEFAULT '{}'::jsonb,
  last_updated DATE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_travel_reviews_poi ON travel_reviews(poi_id);
CREATE INDEX IF NOT EXISTS idx_travel_reviews_rating ON travel_reviews(rating);
CREATE INDEX IF NOT EXISTS idx_travel_reviews_review_time ON travel_reviews(review_time);

CREATE TABLE IF NOT EXISTS travel_areas (
  area_key TEXT PRIMARY KEY,
  area_name TEXT NOT NULL,
  city TEXT NOT NULL DEFAULT 'beijing',
  district TEXT,
  poi_count INTEGER NOT NULL DEFAULT 0,
  culture_count INTEGER NOT NULL DEFAULT 0,
  food_count INTEGER NOT NULL DEFAULT 0,
  avg_rating DOUBLE PRECISION,
  avg_cost DOUBLE PRECISION,
  top_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
  raw JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_travel_areas_name ON travel_areas(area_name);
CREATE INDEX IF NOT EXISTS idx_travel_areas_district ON travel_areas(district);

CREATE TABLE IF NOT EXISTS travel_semantic_mappings (
  id TEXT PRIMARY KEY,
  phrase TEXT NOT NULL UNIQUE,
  intent_field TEXT NOT NULL,
  intent_value JSONB NOT NULL,
  category TEXT NOT NULL DEFAULT 'preference',
  priority INTEGER NOT NULL DEFAULT 100,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_travel_semantic_mappings_field ON travel_semantic_mappings(intent_field);
CREATE INDEX IF NOT EXISTS idx_travel_semantic_mappings_category ON travel_semantic_mappings(category);
CREATE INDEX IF NOT EXISTS idx_travel_semantic_mappings_enabled ON travel_semantic_mappings(enabled);

CREATE TABLE IF NOT EXISTS travel_query_logs (
  id TEXT PRIMARY KEY,
  raw_text TEXT NOT NULL,
  intent JSONB NOT NULL DEFAULT '{}'::jsonb,
  query_plan JSONB NOT NULL DEFAULT '{}'::jsonb,
  template_name TEXT,
  elapsed_ms DOUBLE PRECISION,
  result_count INTEGER NOT NULL DEFAULT 0,
  llm_used BOOLEAN NOT NULL DEFAULT FALSE,
  status TEXT NOT NULL DEFAULT 'ok',
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_travel_query_logs_template ON travel_query_logs(template_name);
CREATE INDEX IF NOT EXISTS idx_travel_query_logs_created_at ON travel_query_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_travel_query_logs_llm_used ON travel_query_logs(llm_used);

INSERT INTO travel_semantic_mappings (id, phrase, intent_field, intent_value, category, priority)
VALUES
  ('semantic_low_walk', '少走路', 'walk_preference', '"low"'::jsonb, 'preference', 10),
  ('semantic_not_tired', '别太累', 'walk_preference', '"low"'::jsonb, 'preference', 12),
  ('semantic_avoid_queue', '不想排队', 'avoid_queue', 'true'::jsonb, 'preference', 10),
  ('semantic_low_queue', '少排队', 'avoid_queue', 'true'::jsonb, 'preference', 11),
  ('semantic_senior', '带老人', 'persona', '"senior"'::jsonb, 'persona', 10),
  ('semantic_family', '亲子', 'persona', '"family"'::jsonb, 'persona', 10),
  ('semantic_couple', '情侣', 'persona', '"couple"'::jsonb, 'persona', 10),
  ('semantic_lunch', '中午吃饭', 'needs_meal', 'true'::jsonb, 'meal', 10),
  ('semantic_coffee', '咖啡', 'meal_type', '"coffee"'::jsonb, 'meal', 20),
  ('semantic_indoor', '室内', 'indoor_preferred', 'true'::jsonb, 'preference', 10)
ON CONFLICT (phrase) DO UPDATE SET
  intent_field = EXCLUDED.intent_field,
  intent_value = EXCLUDED.intent_value,
  category = EXCLUDED.category,
  priority = EXCLUDED.priority,
  enabled = TRUE,
  updated_at = NOW();
