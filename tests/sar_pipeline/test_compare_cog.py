import numpy as np
import rasterio
from rasterio.transform import from_origin

from sar_pipeline.analysis.compare_cog import compare_cog_stats, get_tif_stats


def write_constant_tif(path, value):
    """Write a small single-band tif filled with `value` and return its path."""
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=4,
        height=4,
        count=1,
        dtype="float32",
        crs="EPSG:3031",
        transform=from_origin(0, 0, 20, 20),
    ) as dst:
        dst.write(np.full((4, 4), value, dtype="float32"), 1)
    return path


def test_get_tif_stats_returns_a_new_dict_each_call(tmp_path):
    """Each call to get_tif_stats should return its own stats dict."""
    stats_1 = get_tif_stats(write_constant_tif(tmp_path / "a.tif", 1.0))
    stats_2 = get_tif_stats(write_constant_tif(tmp_path / "b.tif", 2.0))

    assert stats_1 is not stats_2
    assert stats_1["mean"] == 1.0
    assert stats_2["mean"] == 2.0


def test_compare_cog_stats_reports_different_tifs_as_different(tmp_path):
    """Tifs with different values should be reported as different."""
    tifs_are_same, comparison = compare_cog_stats(
        write_constant_tif(tmp_path / "a.tif", 1.0),
        write_constant_tif(tmp_path / "b.tif", 2.0),
    )

    assert not tifs_are_same
    assert comparison["tif_1_stats"]["mean"] == 1.0
    assert comparison["tif_2_stats"]["mean"] == 2.0
    assert comparison["stat_differences"]["mean"] == -1.0


def test_compare_cog_stats_reports_identical_tifs_as_same(tmp_path):
    """Tifs with identical values should be reported as the same."""
    tifs_are_same, _ = compare_cog_stats(
        write_constant_tif(tmp_path / "a.tif", 1.0),
        write_constant_tif(tmp_path / "b.tif", 1.0),
    )

    assert tifs_are_same
