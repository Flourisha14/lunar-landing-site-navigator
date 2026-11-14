"""Scientific subsystem package."""

from .visibility import (
    BodyVisibility,
    TerrainVisibilityResult,
    VisibilityStatus,
    evaluate_terrain_visibility,
)

__all__ = [
    "BodyVisibility",
    "TerrainVisibilityResult",
    "VisibilityStatus",
    "evaluate_terrain_visibility",
    "VisibilityMetrics",
    "VisibilitySample",
    "VisibilityTimeline",
    "VisibilityWindow",
    "analyze_visibility_timeline",
    "extract_visibility_windows",
    "sample_utc_interval",
    "summarize_visibility",
]

from .timeline import (
    VisibilityMetrics,
    VisibilitySample,
    VisibilityTimeline,
    VisibilityWindow,
    analyze_visibility_timeline,
    extract_visibility_windows,
    sample_utc_interval,
    summarize_visibility,
)
