import type { AnalysisMode, TerrainInterpolation } from '../api/types';

export interface SimulationState {
  latitude: string;
  longitude: string;
  dateUTC: string;
  timeUTC: string;
  observerHeight: string;
  mode: AnalysisMode;
  maxDistanceKm: string;
  stepM: string;
  interpolation: TerrainInterpolation;
}

// Example UTC epoch from docs/scientific-api-v1.md; editable and never treated as live telemetry.
export const initialSimulation: SimulationState = {
  latitude: '-89.5',
  longitude: '45',
  dateUTC: '2027-11-15',
  timeUTC: '12:00',
  observerHeight: '2',
  mode: 'terrain_aware',
  maxDistanceKm: '10',
  stepM: '80',
  interpolation: 'bilinear',
};
