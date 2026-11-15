import { describe, expect, it } from 'vitest';
import { LUNAR_REFERENCE_RADIUS_M, normalizeLunarSite } from './lunarCoordinates';

describe('renderer-only lunar coordinate adapter', () => {
  it('uses the scientific reference sphere radius in metres', () => {
    expect(LUNAR_REFERENCE_RADIUS_M).toBe(1_737_400);
  });
  it('normalizes east-positive longitude into [-180, 180)', () => {
    expect(normalizeLunarSite(0, 450)).toEqual({ latitudeDeg: 0, longitudeDeg: 90 });
    expect(normalizeLunarSite(0, 180)?.longitudeDeg).toBe(-180);
    expect(normalizeLunarSite(0, -181)?.longitudeDeg).toBe(179);
  });
  it('canonicalizes longitude at the poles', () => {
    expect(normalizeLunarSite(-90, 45)).toEqual({ latitudeDeg: -90, longitudeDeg: 0 });
  });
  it('rejects invalid latitude or non-finite coordinates', () => {
    expect(normalizeLunarSite(91, 0)).toBeNull();
    expect(normalizeLunarSite(0, Number.NaN)).toBeNull();
  });
});
