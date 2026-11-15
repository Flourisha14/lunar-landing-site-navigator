/** Mirrors backend/src/lunar_api/schemas.py (Scientific REST API v1). */
export type AnalysisMode = 'geometric' | 'terrain_aware';
export type VisibilityState = 'visible' | 'obstructed' | 'unknown';
export type TargetBody = 'SUN' | 'EARTH';
export type TerrainInterpolation = 'nearest' | 'bilinear';

export interface TerrainConfig {
  max_distance_km: number;
  step_m: number;
  interpolation: TerrainInterpolation;
}

export interface InstantRequest {
  latitude_deg: number;
  longitude_deg: number;
  timestamp_utc: string;
  observer_height_m: number;
}

export interface GeometryRequest extends InstantRequest {
  reference_surface_elevation_m?: number;
}

export interface SiteAnalysisRequest extends InstantRequest {
  mode: AnalysisMode;
  terrain?: TerrainConfig | null;
}

export interface ScientificMetadata {
  api_version: 'v1';
  reference_frame: string;
  kernel_manifest_id: string;
  terrain_dataset_id: string | null;
  mode: AnalysisMode | 'geometry';
  aberration: 'NONE';
  fidelity: string;
  limitations: string[];
  latitude_type: 'planetocentric';
  longitude_positive: 'east';
  angular_unit: 'deg';
  horizontal_distance_unit: 'km';
  height_unit: 'm';
}

export interface Direction {
  body: TargetBody;
  azimuth_deg: number | null;
  elevation_deg: number;
  east_unit: number;
  north_unit: number;
  up_unit: number;
  range_km: number;
  position_moon_fixed_km: [number, number, number];
  geometric_visibility: VisibilityState;
}

export interface GeometryResponse extends InstantRequest {
  observer_reference_elevation_m: number;
  sun: Direction;
  earth: Direction;
  metadata: ScientificMetadata;
}

export interface BodyAssessment {
  body: TargetBody;
  azimuth_deg: number | null;
  elevation_deg: number;
  geometric_visibility: VisibilityState;
  status: VisibilityState;
  terrain_horizon_deg: number | null;
  clearance_deg: number | null;
  horizon_complete: boolean | null;
  horizon_samples_completed: number | null;
  horizon_samples_requested: number | null;
  reason: string | null;
  fidelity: string;
}

export interface SiteAnalysisResponse extends InstantRequest {
  sun: BodyAssessment;
  earth: BodyAssessment;
  terrain: TerrainConfig | null;
  metadata: ScientificMetadata;
}

export interface HealthResponse {
  status: 'ok';
  api_version: 'v1';
  science_available: boolean;
  detail: string;
}

export interface MetadataResponse {
  api_version: 'v1';
  modes: AnalysisMode[];
  supported_targets: TargetBody[];
  reference_frame: string;
  coordinate_convention: string;
  terrain_dataset_id: string | null;
  terrain_configured: boolean;
  kernel_manifests_configured: boolean;
  max_timeline_samples: number;
  max_timeline_days: number;
  limitations: string[];
}

/** Read-only backend DEM mesh: metre-scale ENU geometry for visualization only. */
export interface TerrainMeshResponse {
  status: 'complete' | 'partial_coverage';
  coordinate_frame: 'local_east_up_north';
  latitude_deg: number;
  longitude_deg: number;
  center_elevation_m: number;
  radius_m: number;
  sample_step_m: number;
  grid_side: number;
  valid_samples: number;
  requested_samples: number;
  vertices: [number, number, number][];
  indices: number[];
  metadata: {
    dataset_id: string;
    reference_frame: string;
    datum_confirmed: boolean;
    pixel_size_m: number;
    vertical_exaggeration: number;
    coordinate_frame: string;
    center_is_local_origin: boolean;
    frame_alignment_note: string;
    visual_only: boolean;
  };
}
export interface ApiErrorBody {
  detail?: string | Array<{ loc?: Array<string | number>; msg?: string; type?: string }>;
  code?: string;
}
