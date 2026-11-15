import type { Direction, GeometryResponse, ScientificMetadata } from '../api/types';
import { normalizeLunarSite } from '../globe/lunarCoordinates';

/** Babylon is left-handed here: +X=local East, +Y=Up, +Z=North.
 * The backend's east/north/up_unit vector points FROM observer TO Sun.
 * Babylon DirectionalLight.direction points in the direction rays TRAVEL,
 * thus each component is negated. No solar ephemeris is computed here.
 */
export interface SolarLightVector {
  direction: readonly [number, number, number];
  aboveHorizon: boolean;
  elevationDeg: number;
  azimuthDeg: number | null;
}

const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);

export function sunToBabylon(sun: Direction, metadata: ScientificMetadata): SolarLightVector {
  if (sun.body !== 'SUN') throw new Error('Solar direction must target SUN.');
  if (!/^MOON_ME_/i.test(metadata.reference_frame) || metadata.latitude_type !== 'planetocentric' ||
      metadata.longitude_positive !== 'east' || metadata.angular_unit !== 'deg') {
    throw new Error('Unsupported lunar scientific reference-frame or angular conventions.');
  }
  const { east_unit: east, north_unit: north, up_unit: up, elevation_deg: elevation, azimuth_deg: azimuth } = sun;
  if (![east, north, up, elevation].every(finite) || elevation < -90 || elevation > 90 ||
      (azimuth !== null && (!finite(azimuth) || azimuth < 0 || azimuth >= 360))) {
    throw new Error('Invalid or missing scientific Sun direction.');
  }
  const norm = Math.hypot(east, north, up);
  if (norm < 0.98 || norm > 1.02) throw new Error('Scientific Sun ENU vector is not unit length.');
  const normalizedUp = up / norm;
  if (Math.abs(normalizedUp - Math.sin(elevation * Math.PI / 180)) > 0.005) {
    throw new Error('Solar elevation and ENU up-component disagree.');
  }
  // Azimuth is clockwise from local North toward East. It is undefined at the zenith/nadir.
  if (azimuth !== null && Math.hypot(east, north) > 0.01) {
    const vectorAzimuth = (Math.atan2(east, north) * 180 / Math.PI + 360) % 360;
    const difference = Math.abs(((vectorAzimuth - azimuth + 540) % 360) - 180);
    if (difference > 0.5) throw new Error('Solar azimuth and ENU vector disagree.');
  }
  return {
    direction: [-east / norm, -up / norm, -north / norm],
    aboveHorizon: elevation > 0,
    elevationDeg: elevation,
    azimuthDeg: azimuth,
  };
}

/** Prevent stale responses from lighting a newly selected site or timestamp. */
export function matchedSolarGeometry(
  geometry: GeometryResponse | null,
  latitude: string,
  longitude: string,
  timestampUTC: string | null,
): SolarLightVector | null {
  if (!geometry || !timestampUTC || !Number.isFinite(Date.parse(timestampUTC)) ||
      Date.parse(geometry.timestamp_utc) !== Date.parse(timestampUTC)) return null;
  const site = normalizeLunarSite(Number(latitude), Number(longitude));
  const returned = normalizeLunarSite(geometry.latitude_deg, geometry.longitude_deg);
  if (!site || !returned || Math.abs(site.latitudeDeg - returned.latitudeDeg) > 1e-7 ||
      Math.abs(site.longitudeDeg - returned.longitudeDeg) > 1e-7) return null;
  return sunToBabylon(geometry.sun, geometry.metadata);
}
