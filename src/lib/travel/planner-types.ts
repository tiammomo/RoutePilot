export type JsonRecord = Record<string, any>;
export type RouteMode = 'culture' | 'mixed';
export type WalkPreference = 'low' | 'medium' | 'high';
export type Pace = 'relaxed' | 'balanced' | 'compact';
export type Strategy = 'balanced' | 'budget' | 'efficient';
export type MealType = 'meal' | 'snack' | 'coffee' | 'dessert' | 'hotel_dining' | 'invalid' | 'non_food';

export interface TravelPlanningRequest {
  goal?: string;
  route_mode?: RouteMode;
  area?: string | null;
  categories?: string[];
  start_time?: string;
  max_budget?: number | null;
  max_total_pois?: number;
  max_duration_min?: number | null;
  day_count?: number;
  pace?: Pace;
  walk_preference?: WalkPreference;
  persona_id?: string;
  must_include_names?: string[];
  exclude_names?: string[];
  must_include_poi_ids?: string[];
  exclude_poi_ids?: string[];
  route_order_poi_ids?: string[];
  accommodation_names?: string[];
  preference_signals?: Record<string, boolean>;
  replan_acceleration_cache?: TravelReplanAccelerationCache | null;
}

export interface TravelReplanPoiHint {
  poi_id: string;
  name: string;
  area?: string | null;
  district?: string | null;
  poi_type?: string | null;
  category?: string | null;
  source: string;
  semantic_keys: string[];
}

export interface TravelReplanAccelerationCache {
  source: string;
  created_at: string;
  poi_hints: TravelReplanPoiHint[];
}

export interface TravelCandidateBuckets {
  request: TravelPlanningRequest;
  resolved_area: string;
  cultureCandidates: Poi[];
  mealCandidates: Poi[];
  snackCandidates: Poi[];
  indoorCandidates: Poi[];
}

export interface Poi extends JsonRecord {
  poi_id: string;
  name: string;
  district?: string;
  area?: string;
  category?: string;
  poi_type?: string;
  address?: string;
  lng: number;
  lat: number;
  rating?: number;
  avg_cost?: number;
  review_count?: number;
  open_time?: string;
  close_time?: string;
  suggested_duration_min?: number;
  planning_tags?: string[];
  evidence_tags?: string[];
  queue_risk?: string;
  value_for_money?: string;
  family_friendliness?: string;
  environment_quality?: string;
  meal_type?: MealType;
  is_lunch_suitable?: boolean;
  is_coffee_stop?: boolean;
  is_meal_stop?: boolean;
}

export interface ReviewAggregate extends JsonRecord {
  poi_id: string;
  feature_key: string;
  feature_value: string;
  status: string;
  confidence?: number;
  evidence_refs?: string[];
  review_count_used?: number;
}

export interface ReviewRecord extends JsonRecord {
  review_id: string;
  poi_id: string;
  review_text: string;
}

export interface TravelData {
  culturePois: Poi[];
  mixedPois: Poi[];
  plannerEntities: Poi[];
  hotels: Poi[];
  reviewAggregates: ReviewAggregate[];
  reviewRecordsById: Map<string, ReviewRecord>;
  poiById: Map<string, Poi>;
  reviewAggregatesByPoiId: Map<string, ReviewAggregate[]>;
}
