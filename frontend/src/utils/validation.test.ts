import { describe, expect, it } from 'vitest';
import { initialSimulation } from '../state/simulation';
import { buildRequests, formatDegrees } from './validation';

describe('mission request construction (not scientific computation)', () => {
  it('preserves backend-contract input values and strict UTC', () => {
    const result = buildRequests(initialSimulation);
    expect(result.geometry.timestamp_utc).toBe('2027-11-15T12:00:00Z');
    expect(result.analysis.latitude_deg).toBe(-89.5);
    expect(result.analysis.terrain).toEqual({ max_distance_km: 10, step_m: 80, interpolation: 'bilinear' });
    expect(result.geometry.reference_surface_elevation_m).toBe(0);
  });
  it('never adds terrain options in geometric mode', () => {
    expect(buildRequests({ ...initialSimulation, mode: 'geometric' }).analysis.terrain).toBeUndefined();
  });
  it('rejects out-of-range coordinates', () => {
    expect(() => buildRequests({ ...initialSimulation, latitude: '91' })).toThrow(/Latitude/);
  });
  it('rejects invalid timestamps', () => {
    expect(() => buildRequests({ ...initialSimulation, dateUTC: '2027-02-30' })).toThrow(/timestamp/);
  });
  it('rejects invalid terrain sample workload', () => {
    expect(() => buildRequests({ ...initialSimulation, stepM: '1' })).toThrow(/2048/);
  });
  it('preserves undefined azimuth and zero degree direction', () => {
    expect(formatDegrees(null)).toBe('Not defined');
    expect(formatDegrees(0)).toBe('0.0000°');
  });
});
