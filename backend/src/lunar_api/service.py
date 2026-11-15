"""BE-016: request-scoped adapters to existing lunar_engine scientific functions.

SPICE uses a process-global kernel pool. All scientific requests within this
service instance are serialized; deploy with one worker or coordinate workers
externally. No synthetic fallback geometry/terrain is permitted.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path
from threading import RLock
from typing import Literal, cast

from lunar_api.recommend_schemas import (
    RecommendSitesRequest,
    RecommendSitesResponse,
    ScreenedCandidate,
)
from lunar_api.schemas import (
    BodyAssessment,
    Direction,
    GeometryRequest,
    GeometryResponse,
    HealthResponse,
    MetadataResponse,
    Mode,
    ScientificMetadata,
    SiteAnalysisRequest,
    SiteAnalysisResponse,
    TerrainConfig,
    TerrainMeshResponse,
    TimelineMetrics,
    TimelineRequest,
    TimelineResponse,
    TimelineSample,
    TimelineWindow,
    VisibilityState,
)
from lunar_engine.analysis.timeline import analyze_visibility_timeline
from lunar_engine.analysis.visibility import BodyVisibility, evaluate_terrain_visibility
from lunar_engine.astronomy.geometry import CelestialDirection, CelestialGeometry
from lunar_engine.coordinates.frame_transform import analyze_geometry_in_dem_frame
from lunar_engine.core.conventions import LunarFrame, LunarLocation
from lunar_engine.terrain.dem import DEFAULT_LOLA_METADATA, LunarDEM
from lunar_engine.terrain.horizon import TerrainSource
from lunar_engine.terrain.mesh import generate_terrain_mesh

LIMITATIONS = [
    "Point-center geometric Sun/Earth directions; SPICE aberration NONE.",
    "No partial solar/Earth disc visibility or guaranteed radio link.",
    "The terrain datum assumption is acknowledged, not independently mission-certified.",
    "Terrain obstruction is limited to finite DEM coverage and search radius.",
    "Timeline window boundaries and durations are sample-resolution estimates.",
]


class ScientificUnavailable(RuntimeError):
    """Required scientific assets are not configured or accessible."""


class ScientificService:
    def __init__(
        self,
        repository_root: Path,
        *,
        dem_file: Path | None = None,
        datum_confirmed: bool = False,
    ) -> None:
        self.repository_root = Path(repository_root)
        self.dem_file = Path(dem_file) if dem_file is not None else None
        self.datum_confirmed = datum_confirmed
        self._science_lock = RLock()

    @classmethod
    def from_environment(cls) -> ScientificService:
        # backend/src/lunar_api/service.py -> repo
        root = Path(os.environ.get("LUNAR_REPOSITORY_ROOT", Path(__file__).resolve().parents[3]))
        raw_dem = os.environ.get("LUNAR_DEM_FILE")
        return cls(
            root,
            dem_file=Path(raw_dem) if raw_dem else None,
            datum_confirmed=os.environ.get("LUNAR_DEM_DATUM_CONFIRMED") == "1",
        )

    def kernels_configured(self) -> bool:
        base = self.repository_root / "data" / "spice"
        return (base / "kernel-lock.json").is_file() and (base / "de421-frame-lock.json").is_file()

    def terrain_configured(self) -> bool:
        return self.dem_file is not None and self.dem_file.is_file() and self.datum_confirmed

    def health(self) -> HealthResponse:
        ok = self.kernels_configured()
        return HealthResponse(
            science_available=ok,
            detail="Kernel manifests configured" if ok else "Kernel manifests missing",
        )

    def metadata(self) -> MetadataResponse:
        return MetadataResponse(
            modes=["geometric", "terrain_aware"],
            supported_targets=["SUN", "EARTH"],
            reference_frame=LunarFrame.ME_DE421.value,
            coordinate_convention=(
                "Planetocentric latitude degrees [-90,90]; "
                "east-positive longitude normalized to [-180,180)"
            ),
            terrain_dataset_id=(
                DEFAULT_LOLA_METADATA.dataset_id if self.terrain_configured() else None
            ),
            terrain_configured=self.terrain_configured(),
            kernel_manifests_configured=self.kernels_configured(),
            limitations=list(LIMITATIONS),
        )

    def terrain_mesh(
        self,
        latitude_deg: float,
        longitude_deg: float,
        *,
        radius_m: float = 5000.0,
        sample_step_m: float = 160.0,
    ) -> TerrainMeshResponse:
        """Read-only, bounded DEM mesh. Does not require SPICE kernels."""
        with self._open_dem() as dem:
            mesh = generate_terrain_mesh(
                dem,
                latitude_deg,
                longitude_deg,
                radius_m=radius_m,
                sample_step_m=sample_step_m,
            )
        return TerrainMeshResponse(
            status=mesh.status,
            latitude_deg=mesh.latitude_deg,
            longitude_deg=mesh.longitude_deg,
            center_elevation_m=mesh.center_elevation_m,
            radius_m=mesh.radius_m,
            sample_step_m=mesh.sample_step_m,
            grid_side=mesh.grid_side,
            valid_samples=mesh.valid_samples,
            requested_samples=mesh.requested_samples,
            vertices=mesh.vertices,
            indices=mesh.indices,
            metadata=mesh.metadata,
        )

    def _require_kernels(self) -> None:
        if not self.kernels_configured():
            raise ScientificUnavailable("Verified DE421/DE440 SPICE kernel manifests unavailable")

    @contextmanager
    def _open_dem(self) -> Iterator[LunarDEM]:
        if not self.terrain_configured() or self.dem_file is None:
            raise ScientificUnavailable(
                "Verified NASA LOLA DEM unavailable or datum not acknowledged"
            )
        with LunarDEM(
            self.dem_file, metadata=replace(DEFAULT_LOLA_METADATA, datum_confirmed=True)
        ) as dem:
            yield dem

    @staticmethod
    def _metadata(
        mode: Mode | Literal["geometry"],
        manifest: str,
        dataset: str | None,
        fidelity: str,
        frame: str,
    ) -> ScientificMetadata:
        return ScientificMetadata(
            reference_frame=frame,
            kernel_manifest_id=manifest,
            terrain_dataset_id=dataset,
            mode=mode,
            fidelity=fidelity,
            limitations=list(LIMITATIONS),
        )

    @staticmethod
    def _direction(direction: CelestialDirection) -> Direction:
        position = direction.position_moon_fixed
        return Direction(
            body=cast(Literal["SUN", "EARTH"], direction.body),
            azimuth_deg=direction.azimuth_deg,
            elevation_deg=direction.elevation_deg,
            east_unit=direction.east_unit,
            north_unit=direction.north_unit,
            up_unit=direction.up_unit,
            range_km=direction.range_km,
            position_moon_fixed_km=(position.x_km, position.y_km, position.z_km),
            geometric_visibility=(
                VisibilityState.VISIBLE
                if direction.geometric_visible
                else VisibilityState.OBSTRUCTED
            ),
        )

    def _geometry(
        self, lat: float, lon: float, timestamp: str, altitude_km: float
    ) -> CelestialGeometry:
        return cast(
            CelestialGeometry,
            analyze_geometry_in_dem_frame(
                lat,
                lon,
                timestamp,
                terrain_elevation_km=altitude_km,
                repository_root=self.repository_root,
            ),
        )

    def geometry(self, request: GeometryRequest) -> GeometryResponse:
        self._require_kernels()
        with self._science_lock:
            height = request.reference_surface_elevation_m + request.observer_height_m
            outcome = self._geometry(
                request.latitude_deg, request.longitude_deg, request.timestamp_utc, height / 1000
            )
        return GeometryResponse(
            timestamp_utc=outcome.timestamp_utc,
            latitude_deg=outcome.site.latitude_deg,
            longitude_deg=outcome.site.longitude_deg,
            observer_reference_elevation_m=request.reference_surface_elevation_m,
            observer_height_m=request.observer_height_m,
            sun=self._direction(outcome.sun),
            earth=self._direction(outcome.earth),
            metadata=self._metadata(
                "geometry",
                outcome.kernel_manifest_id,
                None,
                "geometric_point_centers_spice_none_explicit_reference_surface",
                outcome.frame.value,
            ),
        )

    @staticmethod
    def _geometric_assessment(direction: CelestialDirection) -> BodyAssessment:
        state = (
            VisibilityState.VISIBLE if direction.geometric_visible else VisibilityState.OBSTRUCTED
        )
        return BodyAssessment(
            body=cast(Literal["SUN", "EARTH"], direction.body),
            azimuth_deg=direction.azimuth_deg,
            elevation_deg=direction.elevation_deg,
            geometric_visibility=state,
            status=state,
            terrain_horizon_deg=None,
            clearance_deg=None,
            horizon_complete=None,
            horizon_samples_completed=None,
            horizon_samples_requested=None,
            reason=None,
            fidelity="geometric_point_center_reference_sphere",
        )

    def site_analysis(self, request: SiteAnalysisRequest) -> SiteAnalysisResponse:
        self._require_kernels()
        if request.mode == "geometric":
            with self._science_lock:
                geometry = self._geometry(
                    request.latitude_deg,
                    request.longitude_deg,
                    request.timestamp_utc,
                    request.observer_height_m / 1000,
                )
            sun = self._geometric_assessment(geometry.sun)
            earth = self._geometric_assessment(geometry.earth)
            dataset = None
            frame = geometry.frame.value
            manifest = geometry.kernel_manifest_id
            fidelity = "geometric_point_center_reference_sphere_spice_none"
            config = None
        else:
            config = request.terrain or TerrainConfig()
            with self._science_lock, self._open_dem() as dem:
                outcome = evaluate_terrain_visibility(
                    cast(TerrainSource, dem),
                    request.latitude_deg,
                    request.longitude_deg,
                    request.timestamp_utc,
                    observer_height_m=request.observer_height_m,
                    max_distance_km=config.max_distance_km,
                    step_m=config.step_m,
                    interpolation=config.interpolation,
                    repository_root=self.repository_root,
                )
            sun = self._terrain_assessment(outcome.sun)
            earth = self._terrain_assessment(outcome.earth)
            dataset = outcome.terrain_dataset_id
            frame = outcome.frame.value
            manifest = outcome.kernel_manifest_id
            fidelity = outcome.model
        return SiteAnalysisResponse(
            timestamp_utc=request.timestamp_utc,
            latitude_deg=request.latitude_deg,
            longitude_deg=LunarLocation(
                request.latitude_deg, request.longitude_deg, 0, LunarFrame.ME_DE421
            ).longitude_deg,
            observer_height_m=request.observer_height_m,
            sun=sun,
            earth=earth,
            terrain=config,
            metadata=self._metadata(request.mode, manifest, dataset, fidelity, frame),
        )

    @staticmethod
    def _terrain_assessment(body: BodyVisibility) -> BodyAssessment:
        ray = body.horizon
        return BodyAssessment(
            body=body.body,
            azimuth_deg=body.azimuth_deg,
            elevation_deg=body.elevation_deg,
            geometric_visibility=(
                VisibilityState.VISIBLE if body.elevation_deg > 0 else VisibilityState.OBSTRUCTED
            ),
            status=VisibilityState(body.status.value),
            terrain_horizon_deg=body.terrain_horizon_deg,
            clearance_deg=body.clearance_deg,
            horizon_complete=ray.complete if ray is not None else None,
            horizon_samples_completed=ray.samples_completed if ray is not None else None,
            horizon_samples_requested=ray.samples_requested if ray is not None else None,
            reason=body.reason,
            fidelity=body.fidelity,
        )

    def timeline(self, request: TimelineRequest) -> TimelineResponse:
        self._require_kernels()
        config = request.terrain or TerrainConfig()
        with self._science_lock:
            if request.mode == "terrain_aware":
                with self._open_dem() as dem:
                    outcome = analyze_visibility_timeline(
                        request.latitude_deg,
                        request.longitude_deg,
                        request.start_utc,
                        request.end_utc,
                        request.sampling_seconds,
                        observer_height_m=request.observer_height_m,
                        mode="terrain_aware",
                        dem=cast(TerrainSource, dem),
                        max_distance_km=config.max_distance_km,
                        step_m=config.step_m,
                        interpolation=config.interpolation,
                        repository_root=self.repository_root,
                    )
            else:
                outcome = analyze_visibility_timeline(
                    request.latitude_deg,
                    request.longitude_deg,
                    request.start_utc,
                    request.end_utc,
                    request.sampling_seconds,
                    observer_height_m=request.observer_height_m,
                    mode="geometric",
                    repository_root=self.repository_root,
                )
        return TimelineResponse(
            latitude_deg=outcome.observer.latitude_deg,
            longitude_deg=outcome.observer.longitude_deg,
            observer_height_m=outcome.observer_height_m,
            start_utc=outcome.start_utc,
            end_utc=outcome.end_utc,
            sampling_seconds=outcome.sampling_seconds,
            endpoint_semantics=outcome.endpoint_semantics,
            samples=[TimelineSample.model_validate(asdict(sample)) for sample in outcome.samples],
            windows=[TimelineWindow.model_validate(asdict(window)) for window in outcome.windows],
            metrics=TimelineMetrics.model_validate(asdict(outcome.metrics)),
            terrain=config if request.mode == "terrain_aware" else None,
            metadata=self._metadata(
                request.mode,
                outcome.kernel_manifest_id,
                outcome.terrain_dataset_id,
                outcome.fidelity,
                outcome.frame.value,
            ),
            processing_seconds=outcome.processing_seconds,
            terrain_cache_hits=outcome.terrain_cache_hits,
            terrain_cache_misses=outcome.terrain_cache_misses,
        )

    def recommend_sites(self, request: RecommendSitesRequest) -> RecommendSitesResponse:
        """Request-scoped DEM, serialized SPICE and direct BE-013 screening."""
        from dataclasses import asdict
        from typing import cast

        from lunar_engine.analysis.recommendations import recommend_lunar_sites
        from lunar_engine.terrain.horizon import TerrainSource

        self._require_kernels()
        with self._science_lock, self._open_dem() as dem:
            result = recommend_lunar_sites(
                cast(TerrainSource, dem),
                start_utc=request.start_utc,
                end_utc=cast(str, request.end_utc),
                sampling_seconds=request.sampling_seconds,
                candidate_count=request.candidate_count,
                max_recommendations=request.max_recommendations,
                observer_height_m=request.observer_height_m,
                max_distance_km=request.terrain.max_distance_km,
                step_m=request.terrain.step_m,
                interpolation=request.terrain.interpolation,
                constraints=request.constraints.to_engine(),
                repository_root=self.repository_root,
            )
        manifests = sorted(
            {x.kernel_manifest_id for x in result.candidates if x.kernel_manifest_id}
        )
        return RecommendSitesResponse(
            start_utc=request.start_utc,
            end_utc=cast(str, request.end_utc),
            sampling_seconds=request.sampling_seconds,
            constraints=request.constraints,
            terrain=request.terrain,
            candidate_count=request.candidate_count,
            requested_recommendations=request.max_recommendations,
            generated_count=result.generated_count,
            evaluated_count=len(result.candidates),
            suitable_count=result.suitable_count,
            unsuitable_count=result.unsuitable_count,
            insufficient_count=result.insufficient_count,
            resolution=result.resolution,
            candidates=[ScreenedCandidate.model_validate(asdict(x)) for x in result.candidates],
            recommendations=[
                ScreenedCandidate.model_validate(asdict(x)) for x in result.recommendations
            ],
            dataset_id=result.dataset_id,
            reference_frame=result.frame,
            kernel_manifest_id=manifests[0] if len(manifests) == 1 else None,
            weights={"sun": 0.40, "earth": 0.35, "simultaneous": 0.25},
            screening_scope=result.screening_scope,
            fidelity=result.fidelity,
            processing_seconds=result.processing_seconds,
            limitations=[
                *LIMITATIONS,
                "Visibility preferences are not NASA-certified landing safety metrics.",
                "No surface hazards, thermal/power survival, or radio link budgets assessed.",
                "Sampled DEM footprint only, not an exhaustive lunar search.",
            ],
        )
