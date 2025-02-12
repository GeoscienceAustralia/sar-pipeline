from affine import Affine
from dataclasses import dataclass
import math
import numpy as np
import pytest
from rasterio.crs import CRS

from sar_antarctica.nci.preparation.dem_cop_glo30 import (
    get_cop_glo30_spacing,
    get_cop_glo30_tile_transform,
    get_extent_of_cop_glo30_tiles_covering_bounds,
    make_empty_cop_glo30_profile_for_bounds,
)


@dataclass
class CopGlo30Area:
    id: str
    bounds: tuple[float | int, float | int, float | int, float | int]
    spacing: tuple[float | int, float | int]
    expanded_bounds: tuple[float | int, float | int, float | int, float | int]

    @property
    def min_lon(self) -> float | int:
        return self.bounds[0]

    @property
    def min_lat(self) -> float | int:
        return self.bounds[1]

    @property
    def max_lon(self) -> float | int:
        return self.bounds[2]

    @property
    def max_lat(self) -> float | int:
        return self.bounds[3]

    @property
    def spacing_lon(self) -> float | int:
        return self.spacing[0]

    @property
    def spacing_lat(self) -> float | int:
        return self.spacing[1]

    @property
    def expanded_min_lon(self) -> float | int:
        return self.expanded_bounds[0]

    @property
    def expanded_min_lat(self) -> float | int:
        return self.expanded_bounds[1]

    @property
    def expanded_max_lon(self) -> float | int:
        return self.expanded_bounds[2]

    @property
    def expanded_max_lat(self) -> float | int:
        return self.expanded_bounds[3]

    @property
    def expanded_width(self) -> float | int:
        return self.expanded_max_lon - self.expanded_min_lon

    @property
    def expanded_height(self) -> float | int:
        return self.expanded_max_lat - self.expanded_min_lat

    @property
    def expanded_nrows_float(self) -> float:
        return self.expanded_height / self.spacing_lat

    @property
    def expanded_nrows_int(self) -> int:
        return round(self.expanded_nrows_float)

    @property
    def expanded_ncols_float(self) -> float:
        return self.expanded_width / self.spacing_lon

    @property
    def expanded_ncols_int(self) -> int:
        return round(self.expanded_ncols_float)

    @property
    def expanded_transform(self):
        return Affine.translation(
            self.expanded_min_lon, self.expanded_max_lat
        ) * Affine.scale(self.spacing_lon, -self.spacing_lat)

    @property
    def expanded_profile(self):
        profile = {
            "driver": "GTiff",
            "dtype": "float32",
            "nodata": np.nan,
            "width": self.expanded_ncols_int,
            "height": self.expanded_nrows_int,
            "count": 1,
            "crs": CRS.from_epsg(4326),
            "transform": self.expanded_transform,
            "blockysize": 1,
            "tiled": False,
            "interleave": "band",
        }
        return profile

    @property
    def containing_tiles_bounds(self):
        containing_bounds = (
            math.floor(self.min_lon) - 0.5 * self.spacing_lon,
            math.floor(self.min_lat) + 0.5 * self.spacing_lat,
            math.ceil(self.max_lon) - 0.5 * self.spacing_lon,
            math.ceil(self.max_lat) + 0.5 * self.spacing_lat,
        )
        return containing_bounds

    @property
    def containing_tiles_min_lon(self) -> float | int:
        return self.containing_tiles_bounds[0]

    @property
    def containing_tiles_min_lat(self) -> float | int:
        return self.containing_tiles_bounds[1]

    @property
    def containing_tiles_max_lon(self) -> float | int:
        return self.containing_tiles_bounds[2]

    @property
    def containing_tiles_max_lat(self) -> float | int:
        return self.containing_tiles_bounds[3]

    @property
    def containing_tiles_transform(self):
        return Affine.translation(
            self.containing_tiles_min_lon, self.containing_tiles_max_lat
        ) * Affine.scale(self.spacing_lon, -self.spacing_lat)


area_1 = CopGlo30Area(
    id="area_1",
    bounds=(
        -61.99967662233957,
        -63.000374451604344,
        -61.99864212858126,
        -62.9997880997025,
    ),
    spacing=(0.0005555555555555556, 0.0002777777777777778),
    expanded_bounds=(
        -61.9997222222222177,
        -63.0004166666666663,
        -61.9986111111111100,
        -62.9995833333333337,
    ),
)

area_2 = CopGlo30Area(
    id="area_2",
    bounds=(
        -62.001611292056054,
        -63.00063479971352,
        -62.000873552192,
        -63.000002688817396,
    ),
    spacing=(0.0005555555555555556, 0.0002777777777777778),
    expanded_bounds=(
        -62.0019444444444403,
        -63.0006944444444414,
        -62.0008333333333326,
        -62.9998611111111089,
    ),
)

area_3 = CopGlo30Area(
    id="area_3",
    bounds=(
        -62.00070306788411,
        -63.00008409244161,
        -62.00020510951952,
        -62.99993583474064,
    ),
    spacing=(0.0005555555555555556, 0.0002777777777777778),
    expanded_bounds=(
        -62.0008333333333326,
        -63.0001388888888840,
        -61.9997222222222248,
        -62.9998611111111089,
    ),
)

areas = [area_1, area_2, area_3]


@pytest.mark.parametrize("area", areas)
def test_get_cop_glo30_spacing(area: CopGlo30Area):
    assert get_cop_glo30_spacing(area.bounds) == area.spacing


@pytest.mark.parametrize("area", areas)
def test_get_cop_glo30_tile_transform(area: CopGlo30Area):
    assert (
        get_cop_glo30_tile_transform(
            area.min_lon, area.max_lat, area.spacing_lon, area.spacing_lat
        )
        == area.containing_tiles_transform
    )


@pytest.mark.parametrize("area", areas)
def test_get_extent_of_cop_glo30_tiles_covering_bounds(area: CopGlo30Area):
    containing_bounds, containing_transform = (
        get_extent_of_cop_glo30_tiles_covering_bounds(area.bounds)
    )
    assert containing_bounds == pytest.approx(area.containing_tiles_bounds)
    assert containing_transform == area.containing_tiles_transform


@pytest.mark.parametrize("area", areas)
def test_make_empty_cop_glo30_profile_for_bounds(area: CopGlo30Area):
    _, profile = make_empty_cop_glo30_profile_for_bounds(area.bounds)
    assert profile == area.expanded_profile
