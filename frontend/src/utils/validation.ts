import type { GeometryRequest, SiteAnalysisRequest } from '../api/types';
import type { SimulationState } from '../state/simulation';

function numeric(value: string, label: string): number {
  if (value.trim() === '' || !Number.isFinite(Number(value))) throw new Error(`${label} must be a finite number.`);
  return Number(value);
}

export function buildRequests(state: SimulationState): { geometry: GeometryRequest; analysis: SiteAnalysisRequest } {
  const latitude_deg = numeric(state.latitude, 'Latitude');
  const longitude_deg = numeric(state.longitude, 'Longitude');
  const observer_height_m = numeric(state.observerHeight, 'Observer height');
  if (latitude_deg < -90 || latitude_deg > 90) throw new Error('Latitude must be between -90° and 90°.');
  if (observer_height_m < 0 || observer_height_m > 100000) throw new Error('Observer height must be between 0 and 100000 metres.');

  const timestamp_utc = `${state.dateUTC}T${state.timeUTC.length === 5 ? `${state.timeUTC}:00` : state.timeUTC}Z`;
  const utcPattern = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/;
  if (!utcPattern.test(timestamp_utc) || !Number.isFinite(Date.parse(timestamp_utc)) ||
    new Date(timestamp_utc).toISOString().replace('.000Z', 'Z') !== timestamp_utc) {
    throw new Error('Date and time must form a valid UTC timestamp.');
  }

  const instant = { latitude_deg, longitude_deg, timestamp_utc, observer_height_m };
  const geometry: GeometryRequest = {
    ...instant,
    // Geometry endpoint uses the reference sphere, not DEM surface elevation.
    reference_surface_elevation_m: 0,
  };
  const analysis: SiteAnalysisRequest = { ...instant, mode: state.mode };
  if (state.mode === 'terrain_aware') {
    const max_distance_km = numeric(state.maxDistanceKm, 'Terrain distance');
    const step_m = numeric(state.stepM, 'Terrain step');
    if (max_distance_km <= 0 || max_distance_km > 1000) throw new Error('Terrain distance must be greater than 0 and at most 1000 km.');
    if (step_m <= 0 || step_m > 100000) throw new Error('Terrain step must be greater than 0 and at most 100000 m.');
    if (max_distance_km * 1000 / step_m > 2048) throw new Error('Terrain workload exceeds 2048 samples per direction.');
    analysis.terrain = { max_distance_km, step_m, interpolation: state.interpolation };
  }
  return { geometry, analysis };
}

export function formatDegrees(value: number | null | undefined): string {
  return value == null ? 'Not defined' : `${value.toFixed(4)}°`;
}
