import type { PlaceRef } from "@routepilot/contracts-generated";

export interface MapMarker {
  id: string;
  label: string;
  place: PlaceRef;
  order: number;
}

export interface MapAdapterProps {
  markers: MapMarker[];
  selectedId?: string;
  onSelect?: (id: string) => void;
}

/**
 * Provider-neutral first paint. AMap can replace this component without exposing
 * its key to a browser API endpoint or changing itinerary components.
 */
export function StaticMapAdapter({ markers, selectedId, onSelect }: MapAdapterProps) {
  const coordinates = markers.map((marker) => ({
    marker,
    latitude: Number(marker.place.location.latitude),
    longitude: Number(marker.place.location.longitude),
  }));
  const valid = coordinates.filter(
    (item) => Number.isFinite(item.latitude) && Number.isFinite(item.longitude),
  );
  const latitudes = valid.map((item) => item.latitude);
  const longitudes = valid.map((item) => item.longitude);
  const minLat = valid.length ? Math.min(...latitudes) : 0;
  const maxLat = valid.length ? Math.max(...latitudes) : 1;
  const minLng = valid.length ? Math.min(...longitudes) : 0;
  const maxLng = valid.length ? Math.max(...longitudes) : 1;
  const rangeLat = maxLat - minLat;
  const rangeLng = maxLng - minLng;

  return (
    <div className="map-adapter" aria-label="行程地点示意图">
      <div className="map-grid" aria-hidden="true" />
      {valid.map(({ marker, latitude, longitude }) => (
        <button
          type="button"
          key={marker.id}
          className="map-marker"
          data-selected={marker.id === selectedId}
          style={{
            left: `${10 + (rangeLng ? (longitude - minLng) / rangeLng : 0.5) * 80}%`,
            top: `${88 - (rangeLat ? (latitude - minLat) / rangeLat : 0.5) * 76}%`,
          }}
          title={marker.label}
          aria-label={`第 ${marker.order} 站：${marker.label}`}
          onClick={() => onSelect?.(marker.id)}
        >
          <span>{marker.order}</span>
        </button>
      ))}
      {!valid.length && (
        <div className="map-empty">
          <span className="map-compass" aria-hidden="true">↗</span>
          <strong>地点会在这里连成路线</strong>
          <span>生成结构化计划后显示坐标与顺序</span>
        </div>
      )}
      <div className="map-caption">RoutePilot MapAdapter · 坐标系随地点数据显式记录</div>
    </div>
  );
}
