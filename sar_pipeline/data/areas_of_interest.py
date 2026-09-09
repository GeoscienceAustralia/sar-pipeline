import geopandas as gpd
import pooch

# Where data will be stored within the operating system's cache directory
CACHE_DIR = "sar_pipeline"

# Base URL for data on AWS
BASE_URL = "https://data.dev.dea.ga.gov.au/projects/s1_nrb/"


# PRODUCTION AREAS OF INTEREST (AOIS)
S1_NRB_PROD_AOIS = pooch.create(
    path=pooch.os_cache(CACHE_DIR),
    base_url=BASE_URL + "production_aois/",
    registry={
        "antarctica_aoi_excl_antimeridian_polygon.geojson": None,
        "aus_aoi_polygon.geojson": None,
    },
)


def fetch_antarctic_prod_aoi() -> gpd.GeoDataFrame:
    path = S1_NRB_PROD_AOIS.fetch("antarctica_aoi_excl_antimeridian_polygon.geojson")
    return gpd.read_file(path)


def fetch_australia_prod_aoi() -> gpd.GeoDataFrame:
    path = S1_NRB_PROD_AOIS.fetch("aus_aoi_polygon.geojson")
    return gpd.read_file(path)


# HISTORIC SCENE COVERAGE AREAS OF INTEREST (AOIS)
S1_NRB_HIST_AOIS = pooch.create(
    path=pooch.os_cache(CACHE_DIR),
    base_url=BASE_URL + "historical_scene_coverage_aois/",
    registry={
        "merged_antartctic_aoi_sentinel_1_iw_grd_scenes_footprint_2014_to_2023.geojson": None,
    },
)


def fetch_antarctic_historical_coverage_aoi() -> gpd.GeoDataFrame:
    path = S1_NRB_HIST_AOIS.fetch(
        "merged_antartctic_aoi_sentinel_1_iw_grd_scenes_footprint_2014_to_2023.geojson"
    )
    return gpd.read_file(path)
