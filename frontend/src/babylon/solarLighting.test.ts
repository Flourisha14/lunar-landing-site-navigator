import { describe, expect, it } from 'vitest';
import type { Direction, GeometryResponse, ScientificMetadata } from '../api/types';
import { matchedSolarGeometry, sunToBabylon } from './solarLighting';

const metadata: ScientificMetadata = {
  api_version: 'v1', reference_frame: 'MOON_ME_DE421', kernel_manifest_id: 'unit-test-fixture',
  terrain_dataset_id: null, mode: 'geometry', aberration: 'NONE', fidelity: 'fixture',
  limitations: ['Unit test; not ephemeris'], latitude_type: 'planetocentric',
  longitude_positive: 'east', angular_unit: 'deg', horizontal_distance_unit: 'km', height_unit: 'm',
};

function sun(e: number, n: number, u: number, az: number | null, el: number): Direction {
  return { body: 'SUN', east_unit: e, north_unit: n, up_unit: u,
    azimuth_deg: az, elevation_deg: el, range_km: 1e8,
    position_moon_fixed_km: [0, 0, 0], geometric_visibility: 'visible' };
}

describe('backend ENU → Babylon light ray direction', () => {
  it.each([
    ['overhead', sun(0, 0, 1, null, 90), [0, -1, 0], true],
    ['east horizon', sun(1, 0, 0, 90, 0), [-1, 0, 0], false],
    ['west horizon', sun(-1, 0, 0, 270, 0), [1, 0, 0], false],
    ['north', sun(0, 1, 0, 0, 0), [0, 0, -1], false],
    ['south', sun(0, -1, 0, 180, 0), [0, 0, 1], false],
    ['nadir', sun(0, 0, -1, null, -90), [0, 1, 0], false],
  ] as const)('%s', (_label, input, expected, illuminated) => {
    const actual = sunToBabylon(input, metadata);
    expected.forEach((component, i) => expect(actual.direction[i]).toBeCloseTo(component, 8));
    expect(actual.aboveHorizon).toBe(illuminated);
  });
  it('rejects incomplete or non-finite vectors', () => {
    expect(() => sunToBabylon({ ...sun(0, 0, 1, null, 90), east_unit: NaN }, metadata)).toThrow();
    expect(() => sunToBabylon({ ...sun(0, 0, 1, null, 90), north_unit: undefined } as unknown as Direction, metadata)).toThrow();
    expect(() => sunToBabylon(sun(0, 0, 0, null, 0), metadata)).toThrow();
  });
  it('rejects invalid angles, mismatched ENU and unsupported frame', () => {
    expect(() => sunToBabylon(sun(0, 0, 1, 400, 90), metadata)).toThrow();
    expect(() => sunToBabylon(sun(0, 0, 1, null, -90), metadata)).toThrow();
    expect(() => sunToBabylon(sun(1, 0, 0, 0, 0), metadata)).toThrow();
    expect(() => sunToBabylon(sun(0, 0, 1, null, 90), { ...metadata, reference_frame: 'EARTH_ITRF' })).toThrow();
  });
});

describe('stale scientific geometry protection', () => {
  const sample = {
    timestamp_utc: '2027-11-15T12:00:00.000000Z', latitude_deg: -89.5, longitude_deg: 45,
    sun: sun(0, 0, 1, null, 90), metadata,
  } as GeometryResponse;
  it('accepts matching epoch with differing equivalent UTC precision', () => {
    expect(matchedSolarGeometry(sample, '-89.5', '45', '2027-11-15T12:00:00Z')?.aboveHorizon).toBe(true);
  });
  it('rejects stale epochs and sites instead of showing outdated sunlight', () => {
    expect(matchedSolarGeometry(sample, '-89.5', '45', '2027-11-15T12:01:00Z')).toBeNull();
    expect(matchedSolarGeometry(sample, '-88.5', '45', '2027-11-15T12:00:00Z')).toBeNull();
    expect(matchedSolarGeometry(sample, '-89.5', '46', '2027-11-15T12:00:00Z')).toBeNull();
    expect(matchedSolarGeometry(null, '-89.5', '45', '2027-11-15T12:00:00Z')).toBeNull();
  });
});
