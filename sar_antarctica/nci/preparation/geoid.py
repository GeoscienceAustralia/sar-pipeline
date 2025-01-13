"""
inspired by https://github.com/ACCESS-Cloud-Based-InSAR/dem-stitcher/blob/dev/src/dem_stitcher/geoid.py
"""
import os
from typing import Union
from pathlib import Path
import logging

import numpy as np
import rasterio
from rasterio.transform import array_bounds
from rasterio.crs import CRS
from ...utils.raster import read_raster_with_bounds
from ...utils.rio_tools import translate_profile, reproject_arr_to_match_profile

def read_geoid(geoid_path: Union[str, Path], bounds: tuple, buffer_pixels: int = 0) -> tuple[np.ndarray, dict]:
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
    
    if not os.path.exists(geoid_path):
        raise FileNotFoundError(f'Geoid file does not exist at path: {geoid_path}')

    geoid_arr, geoid_profile = read_raster_with_bounds(geoid_path, bounds, buffer_pixels=buffer_pixels)
    geoid_arr = geoid_arr.astype('float32')
    geoid_arr[geoid_profile['nodata'] == geoid_arr] = np.nan
    geoid_profile['nodata'] = np.nan

    return geoid_arr, geoid_profile


def remove_geoid(
    dem_arr: np.ndarray,
    dem_profile: dict,
    geoid_path: Union[str, Path],
    dem_area_or_point: str = 'Point',
    buffer_pixels: int = 2,
    save_path: Union[str, Path] = '',
) -> np.ndarray:
    """Subtract the Geoid from a dem file. Result will be 
    ellipsoid referenced heights for the cop30m dem.

    Parameters
    ----------
    dem_arr : np.ndarray
        dem array values
    dem_profile : dict
        rasterio profile for dem
    geoid_path : Union[str, Path]
        path to the geoid file
    dem_area_or_point : str, optional
        Can be 'Area' or 'Point'. The former means each pixel is referenced with respect to the upper
        left corner. The latter means the pixel is center at its own center. By default 'Point' for cop30.
    buffer_pixels : int, optional
        Additional pixels to buffer with, by default 2
    save_path : Union[str, Path], optional
        Path to save the resulting dem, by default '' (not saved)

    Returns
    -------
    np.ndarray
        original array with the geoid subtracted
    """
    
    assert dem_area_or_point in ['Point', 'Area']

    bounds = array_bounds(dem_profile['height'], dem_profile['width'], dem_profile['transform'])

    geoid_arr, geoid_profile = read_geoid(geoid_path, bounds=tuple(bounds), buffer_pixels=buffer_pixels)

    t_dem = dem_profile['transform']
    t_geoid = geoid_profile['transform']
    res_dem = max(t_dem.a, abs(t_dem.e))
    res_geoid = max(t_geoid.a, abs(t_geoid.e))

    if res_geoid * buffer_pixels <= res_dem:
        buffer_recommendation = int(np.ceil(res_dem / res_geoid))
        warning = (
            'The dem resolution is larger than the geoid resolution and its buffer; '
            'Edges resampled with bilinear interpolation will be inconsistent so select larger buffer.'
            f'Select a `buffer_pixels = {buffer_recommendation}`'
        )
        logging.warning(warning)

    # Translate geoid if necessary as all geoids have Area tag
    if dem_area_or_point == 'Point':
        shift = -0.5
        geoid_profile = translate_profile(geoid_profile, shift, shift)

    geoid_offset, _ = reproject_arr_to_match_profile(geoid_arr, geoid_profile, dem_profile, resampling='bilinear')

    dem_arr_offset = dem_arr + geoid_offset

    if save_path:
        with rasterio.open(save_path, 'w', **dem_profile) as dst:
            dst.write(dem_arr_offset)

    return dem_arr_offset