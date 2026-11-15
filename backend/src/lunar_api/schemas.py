"""BE-015: renderer-neutral, versioned Pydantic v2 scientific contracts.

Coordinates are planetocentric degrees; longitudes east-positive and normalized
by the scientific engine to [-180, 180). All timestamps require ISO UTC-Z.
All fields with explicit _deg/_km/_m/_seconds suffixes carry those units.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from lunar_engine.analysis.timeline import MAX_MISSION_DAYS, MAX_SAMPLES, sample_utc_interval
from lunar_engine.astronomy.ephemeris import canonical_utc

Latitude = Annotated[float, Field(ge=-90.0, le=90.0, allow_inf_nan=False)]
Longitude = Annotated[float, Field(allow_inf_nan=False)]
Height = Annotated[float, Field(ge=0, le=100_000, allow_inf_nan=False)]
PositiveLength = Annotated[float, Field(gt=0, le=1000, allow_inf_nan=False)]
Step = Annotated[float, Field(gt=0, le=100_000, allow_inf_nan=False)]
Mode = Literal["geometric", "terrain_aware"]
Interpolation = Literal["nearest", "bilinear"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


def validate_utc(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Timestamp must be an ISO 8601 UTC string ending in Z")
    try:
        return canonical_utc(value)
    except (ValueError, TypeError) as exc:
        raise ValueError("Timestamp must be a valid ISO 8601 UTC string ending in Z") from exc


class Site(Contract):
    latitude_deg: Latitude
    longitude_deg: Longitude


class ObserverRequest(Site):
    observer_height_m: Height = 2.0


class InstantRequest(ObserverRequest):
    timestamp_utc: str

    @field_validator("timestamp_utc")
    @classmethod
    def check_timestamp(cls, value: str) -> str:
        return validate_utc(value)


class TerrainConfig(Contract):
    max_distance_km: PositiveLength = 30.0
    step_m: Step = 160.0
    interpolation: Interpolation = "bilinear"

    @model_validator(mode="after")
    def bound_ray_samples(self) -> TerrainConfig:
        if self.max_distance_km * 1000.0 / self.step_m > 2048:
            raise ValueError("Terrain workload exceeds 2048 samples per direction")
        return self


class GeometryRequest(InstantRequest):
    # Explicit radial elevation of reference surface; 0 means reference sphere,
    # NOT a claim that the local DEM elevation is 0.
    reference_surface_elevation_m: Annotated[
        float, Field(ge=-1_000_000, le=1_000_000, allow_inf_nan=False)
    ] = 0.0


class SiteAnalysisRequest(InstantRequest):
    mode: Mode = "terrain_aware"
    terrain: TerrainConfig | None = None

    @model_validator(mode="after")
    def require_terrain(self) -> SiteAnalysisRequest:
        if self.mode == "geometric" and self.terrain is not None:
            raise ValueError("terrain configuration is valid only in terrain_aware mode")
        return self


class TimelineRequest(ObserverRequest):
    start_utc: str
    end_utc: str
    sampling_seconds: StrictInt = Field(gt=0)
    mode: Mode = "terrain_aware"
    terrain: TerrainConfig | None = None

    @field_validator("start_utc", "end_utc")
    @classmethod
    def check_timestamp(cls, value: str) -> str:
        return validate_utc(value)

    @model_validator(mode="after")
    def valid_time_grid(self) -> TimelineRequest:
        if self.mode == "geometric" and self.terrain is not None:
            raise ValueError("terrain configuration is valid only in terrain_aware mode")
        try:
            sample_utc_interval(self.start_utc, self.end_utc, self.sampling_seconds)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return self


class VisibilityState(StrEnum):
    VISIBLE = "visible"
    OBSTRUCTED = "obstructed"
    UNKNOWN = "unknown"


class ScientificMetadata(Contract):
    api_version: Literal["v1"] = "v1"
    reference_frame: str
    kernel_manifest_id: str
    terrain_dataset_id: str | None = None
    mode: Mode | Literal["geometry"]
    aberration: Literal["NONE"] = "NONE"
    fidelity: str
    limitations: list[str]
    latitude_type: Literal["planetocentric"] = "planetocentric"
    longitude_positive: Literal["east"] = "east"
    angular_unit: Literal["deg"] = "deg"
    horizontal_distance_unit: Literal["km"] = "km"
    height_unit: Literal["m"] = "m"


class Direction(Contract):
    body: Literal["SUN", "EARTH"]
    azimuth_deg: float | None
    elevation_deg: float
    east_unit: float
    north_unit: float
    up_unit: float
    range_km: float
    position_moon_fixed_km: tuple[float, float, float]
    geometric_visibility: VisibilityState


class GeometryResponse(Contract):
    timestamp_utc: str
    latitude_deg: float
    longitude_deg: float
    observer_reference_elevation_m: float
    observer_height_m: float
    sun: Direction
    earth: Direction
    metadata: ScientificMetadata


class BodyAssessment(Contract):
    body: Literal["SUN", "EARTH"]
    azimuth_deg: float | None
    elevation_deg: float
    geometric_visibility: VisibilityState
    status: VisibilityState
    terrain_horizon_deg: float | None
    clearance_deg: float | None
    horizon_complete: bool | None
    horizon_samples_completed: int | None
    horizon_samples_requested: int | None
    reason: str | None
    fidelity: str


class SiteAnalysisResponse(Contract):
    timestamp_utc: str
    latitude_deg: float
    longitude_deg: float
    observer_height_m: float
    sun: BodyAssessment
    earth: BodyAssessment
    terrain: TerrainConfig | None
    metadata: ScientificMetadata


class TimelineSample(Contract):
    timestamp_utc: str
    sun: VisibilityState
    earth: VisibilityState
    simultaneous: VisibilityState
    sun_geometric: VisibilityState
    earth_geometric: VisibilityState
    sun_azimuth_deg: float | None
    sun_elevation_deg: float
    earth_azimuth_deg: float | None
    earth_elevation_deg: float
    sun_terrain_horizon_deg: float | None
    earth_terrain_horizon_deg: float | None
    kernel_manifest_id: str
    fidelity: str


class TimelineWindow(Contract):
    category: Literal["sunlight", "earth_visible", "simultaneous", "darkness", "earth_outage"]
    state: VisibilityState
    start_utc: str
    end_utc: str
    estimated_duration_seconds: float
    sampling_seconds: int
    sample_count: int
    is_left_censored: bool
    is_right_censored: bool
    boundary_uncertainty_seconds: int


class TimelineMetrics(Contract):
    sampled_sun_fraction: float
    sampled_earth_fraction: float
    sampled_simultaneous_fraction: float
    sun_unknown_samples: int
    earth_unknown_samples: int
    simultaneous_unknown_samples: int
    sun_unknown_duration_seconds: float
    earth_unknown_duration_seconds: float
    simultaneous_unknown_duration_seconds: float
    illuminated_duration_seconds: float
    earth_visible_duration_seconds: float
    simultaneous_duration_seconds: float
    longest_illumination_seconds: float
    longest_earth_visibility_seconds: float
    longest_simultaneous_seconds: float


class TimelineResponse(Contract):
    latitude_deg: float
    longitude_deg: float
    observer_height_m: float
    start_utc: str
    end_utc: str
    sampling_seconds: int
    endpoint_semantics: str
    samples: list[TimelineSample]
    windows: list[TimelineWindow]
    metrics: TimelineMetrics
    terrain: TerrainConfig | None
    metadata: ScientificMetadata
    processing_seconds: float = Field(ge=0)
    terrain_cache_hits: int = Field(ge=0)
    terrain_cache_misses: int = Field(ge=0)


class HealthResponse(Contract):
    status: Literal["ok"] = "ok"
    api_version: Literal["v1"] = "v1"
    science_available: bool
    detail: str


class MetadataResponse(Contract):
    api_version: Literal["v1"] = "v1"
    modes: list[Mode]
    supported_targets: list[Literal["SUN", "EARTH"]]
    reference_frame: str
    coordinate_convention: str
    terrain_dataset_id: str | None
    terrain_configured: bool
    kernel_manifests_configured: bool
    max_timeline_samples: int = MAX_SAMPLES
    max_timeline_days: int = MAX_MISSION_DAYS
    limitations: list[str]


class TerrainMeshResponse(Contract):
    """LOLA-derived visual geometry, independent of SPICE visibility results."""

    status: Literal["complete", "partial_coverage"]
    coordinate_frame: Literal["local_east_up_north"] = "local_east_up_north"
    latitude_deg: Latitude
    longitude_deg: Longitude
    center_elevation_m: float
    radius_m: float
    sample_step_m: float
    grid_side: int
    valid_samples: int
    requested_samples: int
    vertices: list[tuple[float, float, float]]
    indices: list[int]
    metadata: dict[str, object]
