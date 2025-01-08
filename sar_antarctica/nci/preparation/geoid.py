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

def read_geoid(geoid_path: Union[str, Path], bounds: Union[list, None], buffer_pixels: int = 0) -> tuple:
    
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
    dem_area_or_point: str = 'Area',
    res_buffer: int = 2,
    save_path: str = '',
) -> np.ndarray:
    
    assert dem_area_or_point in ['Point', 'Area']

    bounds = array_bounds(dem_profile['height'], dem_profile['width'], dem_profile['transform'])

    geoid_arr, geoid_profile = read_geoid(geoid_path, bounds=tuple(bounds), buffer_pixels=res_buffer)

    t_dem = dem_profile['transform']
    t_geoid = geoid_profile['transform']
    res_dem = max(t_dem.a, abs(t_dem.e))
    res_geoid = max(t_geoid.a, abs(t_geoid.e))

    if res_geoid * res_buffer <= res_dem:
        buffer_recommendation = int(np.ceil(res_dem / res_geoid))
        warning = (
            'The dem resolution is larger than the geoid resolution and its buffer; '
            'Edges resampled with bilinear interpolation will be inconsistent so select larger buffer.'
            f'Select a `res_buffer = {buffer_recommendation}`'
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