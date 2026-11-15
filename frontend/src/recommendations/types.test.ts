import { describe, expect, it } from 'vitest';
import { fractionPercent, parseRecommendations, utcFromInput, validateMission } from './types';
import type { RecommendSitesRequest } from './types';

const validRequest: RecommendSitesRequest = {
  start_utc: '2027-11-15T12:00:00Z', duration_hours: 24, sampling_seconds: 3600,
  candidate_count: 8, max_recommendations: 5, observer_height_m: 2,
  terrain: { max_distance_km: 2, step_m: 160, interpolation: 'bilinear' },
  constraints: { min_sun_fraction: .5, min_earth_fraction: .5, min_simultaneous_fraction: .25,
    max_darkness_seconds: null, max_earth_outage_seconds: null },
};
const site = {
  latitude_deg: -89.5, longitude_deg: 45, suitability: 'SUITABLE', score: 1,
  sun_fraction: 1, earth_fraction: 1, simultaneous_fraction: 1,
  longest_darkness_seconds: 0, longest_earth_outage_seconds: 0,
  unknown_sun_samples: 0, unknown_earth_samples: 0,
  unknown_simultaneous_samples: 0, total_samples: 24, checks: {}, explanation: 'Complete',
  terrain_dataset_id: 'NASA LOLA', reference_frame: 'MOON_ME_DE421', kernel_manifest_id: 'manifest',
};
const response = {
  api_version: 'v1', start_utc: validRequest.start_utc, end_utc: '2027-11-16T12:00:00Z', sampling_seconds: 3600,
  constraints: validRequest.constraints, terrain: validRequest.terrain, candidate_count: 8,
  requested_recommendations: 5, generated_count: 8, evaluated_count: 8,
  suitable_count: 1, unsuitable_count: 0, insufficient_count: 0,
  resolution: 'suitable_candidates', candidates: [site], recommendations: [site],
  dataset_id: 'NASA LOLA', reference_frame: 'MOON_ME_DE421', kernel_manifest_id: 'manifest',
  weights: { solar: .4, earth: .35, simultaneous: .25 },
  screening_scope: 'regional DEM', fidelity: 'screening', processing_seconds: 1, limitations: [],
};

describe('backend-authoritative recommendation contracts', () => {
  it('accepts actual backend defaults', () => expect(validateMission(validRequest)).toBeNull());
  it('enforces backend maximum of 24 samples', () => expect(validateMission({ ...validRequest, sampling_seconds: 60 })).toContain('24'));
  it('rejects invalid candidate counts', () => expect(validateMission({ ...validRequest, candidate_count: 13 })).toContain('12'));
  it('prevents recommendations exceeding candidates', () => expect(validateMission({ ...validRequest, max_recommendations: 9 })).toContain('cannot exceed'));
  it('preserves explicit UTC with no timezone conversion', () => expect(utcFromInput('2027-11-15T12:00')).toBe('2027-11-15T12:00:00Z'));
  it('rejects malformed UTC', () => expect(utcFromInput('2027-02-30T12:00')).toBeNull());
  it('keeps equal backend scores unchanged', () => {
    const parsed = parseRecommendations({ ...response, candidates: [site, { ...site, longitude_deg: 44 }], recommendations: [site, { ...site, longitude_deg: 44 }] });
    expect(parsed.recommendations.map(item => item.score)).toEqual([1, 1]);
  });
  it('preserves unknown scientific fractions', () => expect(fractionPercent(null)).toBe('Unknown'));
  it('rejects malformed backend candidate classification', () => {
    expect(() => parseRecommendations({ ...response, candidates: [{ ...site, suitability: 'SAFE' }] })).toThrow();
  });
});
