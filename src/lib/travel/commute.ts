export type TransferSource = 'commute_edge' | 'coordinate_estimate';

export interface CommuteEdge {
  origin_poi_id: string;
  destination_poi_id: string;
  mode: string;
  provider: string;
  distance_m: number | null;
  duration_s: number;
  walking_distance_m: number | null;
  transfer_count: number | null;
}

export interface CommuteEdgeIndex {
  edgesByPair: Map<string, CommuteEdge[]>;
  loaded: boolean;
  edge_count: number;
  loaded_at: string | null;
  error: string | null;
}

export interface TransferEstimate {
  minutes: number;
  meters: number;
  source: TransferSource;
  mode: string | null;
  provider: string | null;
  duration_s: number | null;
  transfer_count: number | null;
}

export interface CoordinatePoi {
  poi_id: string;
  lat: number;
  lng: number;
}

export function commutePairKey(originPoiId: string, destinationPoiId: string): string {
  return `${originPoiId}->${destinationPoiId}`;
}

export function meters(a: CoordinatePoi, b: CoordinatePoi): number {
  const rad = Math.PI / 180;
  const lat1 = a.lat * rad;
  const lat2 = b.lat * rad;
  const dLat = (b.lat - a.lat) * rad;
  const dLng = (b.lng - a.lng) * rad;
  const s = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 6371000 * 2 * Math.atan2(Math.sqrt(s), Math.sqrt(1 - s));
}

function transferMinutes(distanceMeters: number): number {
  return Math.max(4, Math.round(distanceMeters / 70));
}

function estimateCoordinateFallback(distanceMeters: number) {
  if (distanceMeters <= 800) {
    return {
      minutes: transferMinutes(distanceMeters),
      mode: 'walking_estimate',
    };
  }
  if (distanceMeters <= 3000) {
    return {
      minutes: Math.max(6, Math.round(distanceMeters / 180) + 4),
      mode: 'bike_estimate',
    };
  }
  return {
    minutes: Math.max(10, Math.round(distanceMeters / 260) + 8),
    mode: 'driving_estimate',
  };
}

export function estimateTransfer(a: CoordinatePoi, b: CoordinatePoi, commuteEdges?: CommuteEdgeIndex): TransferEstimate {
  const edge =
    commuteEdges?.edgesByPair.get(commutePairKey(a.poi_id, b.poi_id))?.[0]
    ?? commuteEdges?.edgesByPair.get(commutePairKey(b.poi_id, a.poi_id))?.[0];
  if (edge && Number.isFinite(edge.duration_s) && edge.duration_s > 0) {
    const metersValue = edge.walking_distance_m ?? edge.distance_m ?? meters(a, b);
    return {
      minutes: Math.max(1, Math.round(edge.duration_s / 60)),
      meters: Math.round(Number(metersValue || 0)),
      source: 'commute_edge',
      mode: edge.mode,
      provider: edge.provider,
      duration_s: edge.duration_s,
      transfer_count: edge.transfer_count,
    };
  }
  const distance = meters(a, b);
  const fallback = estimateCoordinateFallback(distance);
  return {
    minutes: fallback.minutes,
    meters: Math.round(distance),
    source: 'coordinate_estimate',
    mode: fallback.mode,
    provider: null,
    duration_s: null,
    transfer_count: null,
  };
}
