import geopandas as gpd
import pandas as pd
import pooch

# Where data will be stored within the operating system's cache directory
CACHE_DIR = "s1_nrb"

# Base URL for data on AWS
BASE_URL = "https://data.dev.dea.ga.gov.au/projects/s1_nrb/"


# BURST DATABASE
S1_NRB_BURST_DB = pooch.create(
    path=pooch.os_cache(CACHE_DIR),
    base_url=BASE_URL + "burst_db/0.9.0/",
    registry={
        "opera-burst-bbox-only.sqlite3": None,
    },
)


def fetch_burst_db() -> str:
    return S1_NRB_BURST_DB.fetch("opera-burst-bbox-only.sqlite3")


# PRODUCTION AOIS
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


# HISTORIC SCENE COVERAGE AOIS
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


# STATIC LAYER INFORMATION
S1_NRB_PROD_STATIC = pooch.create(
    path=pooch.os_cache(CACHE_DIR),
    base_url=BASE_URL + "production_static_layer_scene_lists/",
    registry={
        "australia_static_layer_source_scenes.geojson": None,
        "australia_static_layer_source_scene_ids.txt": None,
        "antarctica_static_layer_source_scenes.geojson": None,
        "antarctica_static_layer_source_scene_ids.txt": None,
    },
)


def fetch_australia_static_layer_info() -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    """
    Load static layer scene information for Australia

    Returns
    -------
    tuple[gpd.GeoDataFrame, pd.DataFrame]
        A GeoDataFrame with the scene distribution, and a DataFrame with the scene IDs
    """

    spatial_path = S1_NRB_PROD_STATIC.fetch(
        "australia_static_layer_source_scenes.geojson"
    )

    spatial_data = gpd.read_file(spatial_path)

    id_path = S1_NRB_PROD_STATIC.fetch("australia_static_layer_source_scene_ids.txt")
    id_data = pd.read_csv(id_path, header=None)

    return spatial_data, id_data


def fetch_antarctica_static_layer_info() -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    """
    Load static layer scene information for Antarctica

    Returns
    -------
    tuple[gpd.GeoDataFrame, pd.DataFrame]
        A GeoDataFrame with the scene distribution, and a DataFrame with the scene IDs
    """

    spatial_path = S1_NRB_PROD_STATIC.fetch(
        "antarctica_static_layer_source_scenes.geojson"
    )
    spatial_data = gpd.read_file(spatial_path)

    id_path = S1_NRB_PROD_STATIC.fetch("antarctica_static_layer_source_scene_ids.txt")
    id_data = pd.read_csv(id_path, header=None)

    return spatial_data, id_data
