import geopandas as gpd
import pandas as pd
import pooch

# Where data will be stored within the operating system's cache directory
CACHE_DIR = "sar_pipeline"

# Base URL for data on AWS
BASE_URL = "https://data.dev.dea.ga.gov.au/projects/s1_nrb/"


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
