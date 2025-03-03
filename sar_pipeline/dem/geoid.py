"""
inspired by https://github.com/ACCESS-Cloud-Based-InSAR/dem-stitcher/blob/dev/src/dem_stitcher/geoid.py
"""

import os
from typing import Union
from pathlib import Path
import logging

import numpy as np
import rasterio
import rasterio.transform
import shapely.geometry
from rasterio.crs import CRS
from sar_pipeline.utils.raster import read_raster_with_bounds
from sar_pipeline.utils.rio_tools import translate_profile, reproject_arr_to_match_profile


def read_geoid(
    geoid_path: Union[str, Path], bounds: tuple, buffer_pixels: int = 0
) -> tuple[np.ndarray, dict]:
    """Read in the geoid for the bounds provided with a specified buffer.

    Parameters
    ----------
    geoid_path : Union[str, Path]
        Path to the GEOID file
    bounds : tuple
        the set of bounds (min_lon, min_lat, max_lon, max_lat)
    buffer_pixels : int, optional
        additional pixels to buffern around bounds, by default 0

    Returns
    -------
    tuple [np.darray, dict]
        geoid array and geoid rasterio profile

    Raises
    ------
    FileNotFoundError
        If ther GEOID file cannot be found
    """

    if not Path(geoid_path).exists():
        raise FileNotFoundError(f"Geoid file does not exist at path: {geoid_path}")

    geoid_arr, geoid_profile = read_raster_with_bounds(
        geoid_path, bounds, buffer_pixels=buffer_pixels
    )
    geoid_arr = geoid_arr.astype("float32")
    geoid_arr[geoid_profile["nodata"] == geoid_arr] = np.nan
    geoid_profile["nodata"] = np.nan

    return geoid_arr, geoid_profile


def remove_geoid(
    dem_array: np.ndarray,
    dem_profile: dict,
    geoid_path=str | Path,
    buffer_pixels: int = 2,
    save_path: str | Path = "",
):

    dem_transform = dem_profile["transform"]
    dem_res = max(dem_transform.a, abs(dem_transform.e))
    dem_bounds = rasterio.transform.array_bounds(
        dem_profile["height"], dem_profile["width"], dem_transform
    )

    with rasterio.open(geoid_path, "r") as src:

        geoid_array, geoid_transform = rasterio.mask.mask(
            src,
            [shapely.geometry.box(*dem_bounds)],
            all_touched=True,
            crop=True,
            pad=True,
            pad_width=buffer_pixels,
        )

        geoid_profile = src.profile
        geoid_profile.update(
            {
                "height": geoid_array.shape[1],
                "width": geoid_array.shape[2],
                "transform": geoid_transform,
            }
        )

    geoid_res = max(geoid_transform.a, abs(geoid_transform.e))

    if geoid_res * buffer_pixels <= dem_res:
        buffer_recommendation = int(np.ceil(dem_res / geoid_res))
        warning = (
            "The dem resolution is larger than the geoid resolution and its buffer; "
            "Edges resampled with bilinear interpolation will be inconsistent so select larger buffer."
            f"Select a `buffer_pixels = {buffer_recommendation}`"
        )
        logging.warning(warning)

    geoid_reprojected, _ = reproject_arr_to_match_profile(
        geoid_array, geoid_profile, dem_profile, resampling="bilinear"
    )

    dem_arr_offset = dem_array + geoid_reprojected

    if save_path:
        with rasterio.open(save_path, "w", **dem_profile) as dst:
            dst.write(dem_arr_offset)

    return dem_arr_offset
