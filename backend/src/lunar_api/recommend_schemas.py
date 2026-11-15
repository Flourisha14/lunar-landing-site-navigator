"""Versioned Pydantic contracts for DEM-scoped, point-center site screening."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StrictInt, field_validator, model_validator

from lunar_api.schemas import Contract, Height, TerrainConfig, validate_utc
from lunar_engine.analysis.recommendations import (
    MAX_CANDIDATES,
    MAX_TIME_SAMPLES,
    MAX_TOTAL_RAY_SAMPLES,
    MissionConstraints,
)
from lunar_engine.analysis.timeline import sample_utc_interval

Fraction = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class RecommendationConstraints(Contract):
    min_sun_fraction: Fraction = 0.50
    min_earth_fraction: Fraction = 0.50
    min_simultaneous_fraction: Fraction = 0.25
    max_darkness_seconds: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    max_earth_outage_seconds: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None

    def to_engine(self) -> MissionConstraints:
        return MissionConstraints(**self.model_dump())


class RecommendSitesRequest(Contract):
    start_utc: str
    end_utc: str | None = None
    duration_hours: StrictInt | None = Field(default=None, gt=0, le=90 * 24)
    sampling_seconds: StrictInt = Field(default=3600, gt=0)
    candidate_count: StrictInt = Field(default=8, ge=1, le=MAX_CANDIDATES)
    max_recommendations: StrictInt = Field(default=5, ge=1, le=MAX_CANDIDATES)
    observer_height_m: Height = 2.0
    terrain: TerrainConfig = Field(
        default_factory=lambda: TerrainConfig(max_distance_km=2, step_m=160)
    )
    constraints: RecommendationConstraints = Field(default_factory=RecommendationConstraints)

    @field_validator("start_utc", "end_utc")
    @classmethod
    def valid_timestamp(cls, value: str | None) -> str | None:
        return validate_utc(value) if value is not None else None

    @model_validator(mode="after")
    def validate_mission(self) -> RecommendSitesRequest:
        from datetime import datetime, timedelta

        if self.end_utc is not None and self.duration_hours is not None:
            raise ValueError("Provide end_utc OR duration_hours, not both")
        if self.end_utc is None:
            start = datetime.fromisoformat(self.start_utc.replace("Z", "+00:00"))
            end = start + timedelta(hours=self.duration_hours or 24)
            object.__setattr__(
                self, "end_utc", end.isoformat(timespec="microseconds").replace("+00:00", "Z")
            )
        if self.max_recommendations > self.candidate_count:
            raise ValueError("max_recommendations must be <= candidate_count")

        # The model validator resolves end_utc from duration_hours
        # when an explicit end timestamp was not supplied.
        end_utc = self.end_utc

        if end_utc is None:
            raise ValueError("Mission end timestamp could not be resolved")

        try:
            times = sample_utc_interval(
                self.start_utc,
                end_utc,
                self.sampling_seconds,
                max_samples=MAX_TIME_SAMPLES,
            )
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        per_ray = int(self.terrain.max_distance_km * 1000 / self.terrain.step_m) + 1
        if self.candidate_count * len(times) * 2 * per_ray > MAX_TOTAL_RAY_SAMPLES:
            raise ValueError("Recommendation workload exceeds bounded terrain-ray budget")
        if self.terrain.max_distance_km > 20:
            raise ValueError("Recommendation terrain radius cannot exceed 20 km")
        return self


class ScreenedCandidate(Contract):
    latitude_deg: float
    longitude_deg: float
    suitability: Literal["SUITABLE", "UNSUITABLE", "INSUFFICIENT_DATA"]
    score: float | None
    sun_fraction: float | None
    earth_fraction: float | None
    simultaneous_fraction: float | None
    longest_darkness_seconds: float | None
    longest_earth_outage_seconds: float | None
    unknown_sun_samples: int | None
    unknown_earth_samples: int | None
    unknown_simultaneous_samples: int | None
    total_samples: int | None
    checks: dict[str, bool | None]
    explanation: str
    terrain_dataset_id: str
    reference_frame: str
    kernel_manifest_id: str | None


class RecommendSitesResponse(Contract):
    api_version: Literal["v1"] = "v1"
    start_utc: str
    end_utc: str
    sampling_seconds: int
    constraints: RecommendationConstraints
    terrain: TerrainConfig
    candidate_count: int
    requested_recommendations: int
    generated_count: int
    evaluated_count: int
    suitable_count: int
    unsuitable_count: int
    insufficient_count: int
    resolution: Literal["suitable_candidates", "no_suitable_candidates", "insufficient_data"]
    candidates: list[ScreenedCandidate]
    recommendations: list[ScreenedCandidate]
    dataset_id: str
    reference_frame: str
    kernel_manifest_id: str | None
    weights: dict[str, float]
    screening_scope: str
    fidelity: str
    processing_seconds: float
    limitations: list[str]
