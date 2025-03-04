from affine import Affine
from dataclasses import dataclass
import math
import pytest
import rasterio
from pathlib import Path

from sar_pipeline.dem.cop_glo30 import (
    get_cop_glo30_spacing,
    get_cop_glo30_tile_transform,
    make_empty_cop_glo30_profile_for_bounds,
)


@dataclass
class TestDem:
    requested_bounds: tuple[float, float, float, float]
    expanded_bounds: tuple[float, float, float, float]
    expanded_shape: tuple[int, int]
    spacing: tuple[float, float]
    bounds_array_file: str

    @property
    def containing_tiles_bounds(self):
        containing_bounds = (
            math.floor(self.requested_bounds[0]) - 0.5 * self.spacing[0],
            math.floor(self.requested_bounds[1]) + 0.5 * self.spacing[1],
            math.ceil(self.requested_bounds[2]) - 0.5 * self.spacing[0],
            math.ceil(self.requested_bounds[3]) + 0.5 * self.spacing[1],
        )
        return containing_bounds

    @property
    def topleft_tile_transform(self):
        return Affine(
            a=self.spacing[0],
            b=0,
            c=self.containing_tiles_bounds[0],
            d=0,
            e=-self.spacing[1],
            f=self.containing_tiles_bounds[3],
        )

    @property
    def profile(self):
        with rasterio.open(self.bounds_array_file) as src:
            profile = src.profile
        return profile


CURRENT_DIR = Path(__file__).parent.resolve()

TEST_DATA_PATH = CURRENT_DIR / "data/copernicus_30m_world/"
test_single_tile_ocean_in_tile = TestDem(
    (161.00062, -69.00084, 161.002205, -69.00027),
    (161.0001388888889, -69.00097222222223, 161.0023611111111, -69.0001388888889),
    (4, 3),
    (0.0005555555555555556, 0.0002777777777777778),
    str(TEST_DATA_PATH / "cop_dem_ocean_and_land_1_1_4_3.tif"),
)

test_single_tile_land_in_tile = TestDem(
    (162.67257663025052, -70.73588517869858, 162.67516972746182, -70.73474602514219),
    (162.67236111111112, -70.73597222222223, 162.67569444444445, -70.73458333333333),
    (4, 5),
    (0.0008333333333333333, 0.0002777777777777778),
    str(TEST_DATA_PATH / "cop_dem_S71_2007_2645_4_5.tif"),
)

test_dem_three_tiles_and_ocean = TestDem(
    (161.9981536608549, -70.00076846229373, 162.00141174891965, -69.99912324943375),
    (161.99791666666667, -70.00097222222223, 162.00180555555556, -69.99902777777778),
    (7, 7),
    (0.0005555555555555556, 0.0002777777777777778),
    TEST_DATA_PATH / "cop_dem_ocean_and_land_1797_3597_7_7.tif",
)
test_dem_two_tiles_same_latitude = TestDem(
    (161.96252, -70.75924, 162.10388, -70.72293),
    (161.96208333333334, -70.75930555555556, 162.10458333333332, -70.72291666666668),
    (171, 131),
    (0.0008333333333333333, 0.0002777777777777778),
    TEST_DATA_PATH / "cop_dem_S71_1155_2603_171_131.tif",
)

areas = [
    test_single_tile_ocean_in_tile,
    test_single_tile_land_in_tile,
    test_dem_three_tiles_and_ocean,
    test_dem_two_tiles_same_latitude,
]


@pytest.mark.parametrize("area", areas)
def test_get_cop_glo30_spacing(area: TestDem):
    assert get_cop_glo30_spacing(area.requested_bounds) == area.spacing


@pytest.mark.parametrize("area", areas)
def test_get_cop_glo30_tile_transform(area: TestDem):
    assert (
        get_cop_glo30_tile_transform(
            area.requested_bounds[0],
            area.requested_bounds[3],
            area.spacing[0],
            area.spacing[1],
        )
        == area.topleft_tile_transform
    )


@pytest.mark.parametrize("area", areas)
def test_make_empty_cop_glo30_profile_for_bounds(area: TestDem):
    _, profile = make_empty_cop_glo30_profile_for_bounds(area.requested_bounds)

    assert profile["width"] == area.profile["width"]
    assert profile["height"] == area.profile["height"]
    assert profile["driver"] == area.profile["driver"]
    assert profile["transform"].a == pytest.approx(area.profile["transform"].a)
    assert profile["transform"].c == pytest.approx(area.profile["transform"].c)
    assert profile["transform"].e == pytest.approx(area.profile["transform"].e)
    assert profile["transform"].f == pytest.approx(area.profile["transform"].f)
