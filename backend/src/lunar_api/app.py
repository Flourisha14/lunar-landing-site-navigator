"""FastAPI HTTP adapter; physics remains in lunar_engine."""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from lunar_api.schemas import (
    GeometryRequest,
    GeometryResponse,
    HealthResponse,
    MetadataResponse,
    SiteAnalysisRequest,
    SiteAnalysisResponse,
    TimelineRequest,
    TimelineResponse,
    TerrainMeshResponse,
)
from lunar_api.service import ScientificService, ScientificUnavailable
from lunar_engine.terrain.dem import TerrainDataError
from lunar_engine.terrain.mesh import TerrainOutsideCoverage

logger = logging.getLogger(__name__)


def create_app(
    *,
    service: ScientificService | None = None,
    cors_origins: tuple[str, ...] = ("http://localhost:3000", "http://localhost:5173"),
) -> FastAPI:
    """Application factory; no module-level scientific resource pools."""
    app = FastAPI(title="Lunasolum Scientific API", version="1.0.0")
    origin_setting = os.environ.get("LUNAR_API_CORS_ORIGINS")
    if origin_setting is not None:
        cors_origins = tuple(x.strip() for x in origin_setting.split(",") if x.strip())
    app.state.science = service or ScientificService.from_environment()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(ScientificUnavailable)
    async def unavailable(_request: Request, exc: ScientificUnavailable) -> JSONResponse:
        return JSONResponse(
            status_code=503, content={"detail": str(exc), "code": "scientific_data_unavailable"}
        )

    @app.exception_handler(TerrainOutsideCoverage)
    async def terrain_outside_coverage(_request: Request, exc: TerrainOutsideCoverage) -> JSONResponse:
        return JSONResponse(
            status_code=422, content={"detail": str(exc), "code": "outside_coverage"}
        )
    @app.exception_handler(TerrainDataError)
    async def terrain_error(_request: Request, exc: TerrainDataError) -> JSONResponse:
        return JSONResponse(
            status_code=422, content={"detail": str(exc), "code": "terrain_coverage_error"}
        )

    @app.exception_handler(ValueError)
    async def scientific_value_error(_request: Request, exc: ValueError) -> JSONResponse:
        message = str(exc)
        if "SHA-256" in message or "Kernel" in message or "kernel" in message:
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "Verified SPICE kernel data unavailable",
                    "code": "scientific_data_unavailable",
                },
            )
        return JSONResponse(
            status_code=422, content={"detail": message, "code": "scientific_input_error"}
        )

    @app.exception_handler(FileNotFoundError)
    async def missing_asset(_request: Request, _exc: FileNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Required scientific asset missing",
                "code": "scientific_data_unavailable",
            },
        )

    @app.exception_handler(RuntimeError)
    async def runtime_error(_request: Request, exc: RuntimeError) -> JSONResponse:
        logger.warning("Scientific runtime error: %s", type(exc).__name__)
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Scientific kernels or terrain resources unavailable",
                "code": "scientific_runtime_unavailable",
            },
        )

    @app.exception_handler(Exception)
    async def unexpected(_request: Request, exc: Exception) -> JSONResponse:
        # SPICE-specific exceptions need structured HTTP status and never fabricated data.
        kind = type(exc).__name__
        if "Spicey" in kind or "Spice" in kind:
            if any(
                code in str(exc)
                for code in ("SPKINSUFFDATA", "NOFRAMECONNECT", "FRAMEDATANOTFOUND")
            ):
                return JSONResponse(
                    status_code=422,
                    content={
                        "detail": "Epoch outside supported SPICE kernel/frame coverage",
                        "code": "ephemeris_out_of_coverage",
                    },
                )
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "SPICE scientific resources unavailable",
                    "code": "scientific_runtime_unavailable",
                },
            )
        logger.exception("Unhandled scientific API error")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal scientific service error", "code": "internal_error"},
        )

    @app.get("/api/v1/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return app.state.science.health()  # type: ignore[no-any-return]

    @app.get("/api/v1/metadata", response_model=MetadataResponse)
    def metadata() -> MetadataResponse:
        return app.state.science.metadata()  # type: ignore[no-any-return]

    @app.post("/api/v1/geometry", response_model=GeometryResponse)
    def geometry(request: GeometryRequest) -> GeometryResponse:
        return app.state.science.geometry(request)  # type: ignore[no-any-return]

    @app.post("/api/v1/site-analysis", response_model=SiteAnalysisResponse)
    def site_analysis(request: SiteAnalysisRequest) -> SiteAnalysisResponse:
        return app.state.science.site_analysis(request)  # type: ignore[no-any-return]

    @app.post("/api/v1/timeline", response_model=TimelineResponse)
    def timeline(request: TimelineRequest) -> TimelineResponse:
        return app.state.science.timeline(request)  # type: ignore[no-any-return]

    @app.get("/api/v1/terrain/mesh", response_model=TerrainMeshResponse)
    def terrain_mesh(
        latitude_deg: float = Query(..., ge=-90, le=90, allow_inf_nan=False),
        longitude_deg: float = Query(..., allow_inf_nan=False),
        radius_m: float = Query(5000.0, ge=160, le=5000, allow_inf_nan=False),
        sample_step_m: float = Query(160.0, ge=80, le=640, allow_inf_nan=False),
    ) -> TerrainMeshResponse:
        return app.state.science.terrain_mesh(
            latitude_deg, longitude_deg, radius_m=radius_m,
            sample_step_m=sample_step_m,
        )
    return app


app = create_app()
