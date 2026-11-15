import type { TerrainConfig } from '../api/types';

/** Exact fields in backend/src/lunar_api/recommend_schemas.py. */
export interface RecommendationConstraints {
  min_sun_fraction: number;
  min_earth_fraction: number;
  min_simultaneous_fraction: number;
  max_darkness_seconds: number | null;
  max_earth_outage_seconds: number | null;
}
export interface RecommendSitesRequest {
  start_utc: string;
  duration_hours: number;
  sampling_seconds: number;
  candidate_count: number;
  max_recommendations: number;
  observer_height_m: number;
  terrain: TerrainConfig;
  constraints: RecommendationConstraints;
}
export type Suitability = 'SUITABLE' | 'UNSUITABLE' | 'INSUFFICIENT_DATA';
export interface ScreenedCandidate {
  latitude_deg: number;
  longitude_deg: number;
  suitability: Suitability;
  score: number | null;
  sun_fraction: number | null;
  earth_fraction: number | null;
  simultaneous_fraction: number | null;
  longest_darkness_seconds: number | null;
  longest_earth_outage_seconds: number | null;
  unknown_sun_samples: number | null;
  unknown_earth_samples: number | null;
  unknown_simultaneous_samples: number | null;
  total_samples: number | null;
  checks: Record<string, boolean | null>;
  explanation: string;
  terrain_dataset_id: string;
  reference_frame: string;
  kernel_manifest_id: string | null;
}
export interface RecommendSitesResponse {
  api_version: 'v1';
  start_utc: string;
  end_utc: string;
  sampling_seconds: number;
  constraints: RecommendationConstraints;
  terrain: TerrainConfig;
  candidate_count: number;
  requested_recommendations: number;
  generated_count: number;
  evaluated_count: number;
  suitable_count: number;
  unsuitable_count: number;
  insufficient_count: number;
  resolution: 'suitable_candidates' | 'no_suitable_candidates' | 'insufficient_data';
  candidates: ScreenedCandidate[];
  recommendations: ScreenedCandidate[];
  dataset_id: string;
  reference_frame: string;
  kernel_manifest_id: string | null;
  weights: Record<string, number>;
  screening_scope: string;
  fidelity: string;
  processing_seconds: number;
  limitations: string[];
}
export function parseRecommendations(data: unknown): RecommendSitesResponse {
  if (!data || typeof data !== 'object') throw new Error('Invalid recommendation response.');
  const response = data as Partial<RecommendSitesResponse>;
  if (response.api_version !== 'v1' || !Array.isArray(response.candidates) || !Array.isArray(response.recommendations) ||
      !['suitable_candidates', 'no_suitable_candidates', 'insufficient_data'].includes(response.resolution ?? '') ||
      typeof response.dataset_id !== 'string' || typeof response.reference_frame !== 'string' ||
      typeof response.screening_scope !== 'string' || typeof response.fidelity !== 'string' ||
      !response.constraints || !response.weights || !Array.isArray(response.limitations) ||
      !response.candidates.every(isCandidate) || !response.recommendations.every(isCandidate) ||
      !response.recommendations.every(item => item.suitability === 'SUITABLE')) {
    throw new Error('Scientific API returned an invalid site-screening contract.');
  }
  return response as RecommendSitesResponse;
}
function isCandidate(value: unknown): value is ScreenedCandidate {
  if (!value || typeof value !== 'object') return false;
  const item = value as Partial<ScreenedCandidate>;
  return typeof item.latitude_deg === 'number' && Number.isFinite(item.latitude_deg) &&
    item.latitude_deg >= -90 && item.latitude_deg <= 90 &&
    typeof item.longitude_deg === 'number' && Number.isFinite(item.longitude_deg) &&
    ['SUITABLE', 'UNSUITABLE', 'INSUFFICIENT_DATA'].includes(item.suitability ?? '') &&
    (item.score === null || (typeof item.score === 'number' && Number.isFinite(item.score))) &&
    typeof item.explanation === 'string';
}
export function utcFromInput(value: string): string | null {
  if (!/^\d{4}-\d\d-\d\dT\d\d:\d\d$/.test(value)) return null;
  const time = new Date(`${value}:00Z`);
  return Number.isNaN(time.valueOf()) || time.toISOString().slice(0, 16) !== value ? null : time.toISOString().replace('.000Z', 'Z');
}
export function validateMission(req: RecommendSitesRequest): string | null {
  if (!/^\d{4}-\d\d-\d\dT/.test(req.start_utc) || Number.isNaN(Date.parse(req.start_utc))) return 'Enter a valid mission start UTC.';
  for (const [label, value, min, max] of [
    ['Duration (hours)', req.duration_hours, 1, 2160],
    ['Sampling interval (seconds)', req.sampling_seconds, 1, 7776000],
    ['Candidate count', req.candidate_count, 1, 12],
    ['Recommendations', req.max_recommendations, 1, 12],
  ] as const) if (!Number.isInteger(value) || value < min || value > max) return `${label} must be an integer between ${min} and ${max}.`;
  if (req.max_recommendations > req.candidate_count) return 'Recommendations cannot exceed candidate count.';
  if (req.observer_height_m < 0 || req.observer_height_m > 100000 || !Number.isFinite(req.observer_height_m)) return 'Observer height must be between 0 and 100000 m.';
  if (!(req.terrain.max_distance_km > 0 && req.terrain.max_distance_km <= 20) ||
      !(req.terrain.step_m > 0 && req.terrain.step_m <= 100000)) return 'Use a terrain radius of 0–20 km and positive terrain sampling interval.';
  if (req.terrain.max_distance_km * 1000 / req.terrain.step_m > 2048) return 'Terrain exceeds 2048 samples per ray.';
  for (const fraction of [req.constraints.min_sun_fraction, req.constraints.min_earth_fraction, req.constraints.min_simultaneous_fraction]) {
    if (!Number.isFinite(fraction) || fraction < 0 || fraction > 1) return 'Visibility thresholds must be percentages between 0 and 100.';
  }
  for (const limit of [req.constraints.max_darkness_seconds, req.constraints.max_earth_outage_seconds]) {
    if (limit !== null && (!Number.isFinite(limit) || limit < 0)) return 'Outage limits must be nonnegative seconds.';
  }
  const nSamples = Math.ceil(req.duration_hours * 3600 / req.sampling_seconds);
  if (nSamples > 24) return 'Mission exceeds 24 temporal samples. Increase sampling interval or reduce duration.';
  const raySamples = Math.floor(req.terrain.max_distance_km * 1000 / req.terrain.step_m) + 1;
  if (req.candidate_count * nSamples * 2 * raySamples > 120000) return 'Mission exceeds the backend 120,000 terrain-ray sample budget.';
  return null;
}
export const fractionPercent = (value: number | null): string => value === null ? 'Unknown' : `${(value * 100).toFixed(1)}%`;
export const durationHours = (value: number | null): string => value === null ? 'Unknown' : `${(value / 3600).toFixed(2)} h`;
