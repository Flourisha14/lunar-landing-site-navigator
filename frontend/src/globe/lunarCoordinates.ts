/** Renderer-only coordinate validation; the Python backend remains authoritative. */
export const LUNAR_REFERENCE_RADIUS_M = 1_737_400;

export interface LunarSite {
  latitudeDeg: number;
  longitudeDeg: number;
}

export function normalizeLongitude(longitudeDeg: number): number {
  return ((longitudeDeg + 180) % 360 + 360) % 360 - 180;
}

export function normalizeLunarSite(latitudeDeg: number, longitudeDeg: number): LunarSite | null {
  if (!Number.isFinite(latitudeDeg) || !Number.isFinite(longitudeDeg) || Math.abs(latitudeDeg) > 90) {
    return null;
  }
  return {
    latitudeDeg,
    // Canonical longitude is zero at the poles in the scientific API.
    longitudeDeg: Math.abs(latitudeDeg) === 90 ? 0 : normalizeLongitude(longitudeDeg),
  };
}
