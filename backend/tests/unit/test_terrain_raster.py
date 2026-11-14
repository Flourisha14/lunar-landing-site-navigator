"""Independent pixel sampling tests using generated, fully specified lunar GeoTIFF."""

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")
from rasterio.crs import CRS  # noqa: E402
from rasterio.transform import from_origin  # noqa: E402

from lunar_engine.terrain.dem import (  # noqa: E402
    LunarDEM,
    TerrainDataError,
    TerrainMetadata,
    south_polar_stereographic_xy,
)


def test_known_pixels_bilinear_and_nodata(tmp_path):
    # Center near -89 deg lat, 0 lon; synthetic 3x3 values form a known plane.
    x, y = south_polar_stereographic_xy(-89, 0)
    path = tmp_path / "synthetic.tif"
    transform = from_origin(x - 120, y + 120, 80, 80)
    data = np.array([[1, 2, 3], [4, 5, 6], [7, 8, -9999]], dtype=np.float32)
    crs = CRS.from_proj4("+proj=stere +lat_0=-90 +lon_0=0 +k=1 +R=1737400 +units=m +no_defs")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=3,
        width=3,
        count=1,
        dtype="float32",
        crs=crs,
        transform=transform,
        nodata=-9999,
    ) as dst:
        dst.write(data, 1)
    metadata = TerrainMetadata("synthetic", "synthetic.tif", datum_confirmed=True)
    with LunarDEM(path, metadata) as dem:
        center = dem.sample(-89, 0, interpolation="nearest")
        assert center.elevation_m == pytest.approx(5)
        bilinear = dem.sample(-89, 0, interpolation="bilinear")
        assert bilinear.elevation_m == pytest.approx(5)
        assert center.to_moon_fixed().frame == metadata.frame
        with pytest.raises(TerrainDataError):
            dem.sample(-80, 0)
        # Locate synthetic nodata pixel center (row=2,col=2) by projected inverse.
        from lunar_engine.terrain.dem import south_polar_inverse

        lat, lon = south_polar_inverse(x + 80, y - 80)
        with pytest.raises(TerrainDataError):
            dem.sample(lat, lon, interpolation="nearest")
