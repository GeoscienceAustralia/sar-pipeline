from typing import Union
import os

import numpy as np
import pyproj
from osgeo import gdal
import rasterio
from rasterio.transform import from_origin, array_bounds
from rasterio.warp import calculate_default_transform, reproject
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.merge import merge

def reproject_raster(src_path: str, out_path: str, crs: int):
    """Reproject a raster to the desired crs

    Args:
        src_path (str): path to src raster
        out_path (str): save path of reproj raster
        crs (int): crs e.g. 3031

    Returns:
        str: save path of reproj raster
    """
    # reproject raster to project crs
    with rasterio.open(src_path) as src:
        src_crs = src.crs
        transform, width, height = calculate_default_transform(
            src_crs, crs, src.width, src.height, *src.bounds)
        kwargs = src.meta.copy()

        # get crs proj 
        crs = pyproj.CRS(f"EPSG:{crs}")

        kwargs.update({
            'crs': crs,
            'transform': transform,
            'width': width,
            'height': height})

        with rasterio.open(out_path, 'w', **kwargs) as dst:
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=crs,
                    resampling=Resampling.nearest)
    return out_path

def expand_raster_to_bounds(
    trg_bounds : tuple, 
    src_path : str = '',
    src_profile = None,
    src_array = None,
    fill_value : float = 0,
    save_path : str = ''):
    """Expand the extent of the input array to the target bounds specified
    by the user.
    Parameters

    Tuple[np.ndarray, dict]:
        (expanded_array, expanded_profile) of data.
    """

    assert src_path or (src_profile and src_array), "Either src_path must exist, or both src_profile and src_array must be provided."

    if src_path:
        with rasterio.open(src_path) as src:
            src_array = src.read(1)
            src_profile = src.profile
            src_left, src_bottom, src_right, src_top = src.bounds
    else:
        src_bounds = array_bounds(src_profile['height'], src_profile['width'], src_profile['transform'])
        src_left, src_bottom, src_right, src_top = src_bounds
    # Define the new bounds
    trg_left, trg_bottom, trg_right, trg_top = trg_bounds
    # adjust the new bounds with even pixel multiples of existing
    # this will stop small offsets
    lon_res, lat_res = abs(list(src_profile['transform'])[0]), abs(list(src_profile['transform'])[4])
    trg_left = src_left - int(abs(trg_left-src_left)/lon_res)*lon_res
    trg_right = src_right + int(abs(trg_right-src_right)/lon_res)*lon_res
    trg_bottom = src_bottom - int(abs(trg_bottom-src_bottom)/lat_res)*lat_res
    trg_top = src_top + int(abs(trg_top-src_top)/lat_res)*lat_res
    # Calculate the new width and height, should be integer values
    new_width = int((trg_right - trg_left) / lon_res)
    new_height = int((trg_top - trg_bottom) / lat_res)
    # Define the new transformation matrix
    transform = from_origin(trg_left, trg_top, lon_res, lat_res)
    # Create a new raster dataset with expanded bounds
    fill_profile = src_profile.copy()
    fill_profile.update({
        'width': new_width,
        'height': new_height,
        'transform': transform
    })
    fill_array = np.full((new_height, new_width), fill_value=fill_value, dtype=src_profile['dtype'])
    trg_array, trg_profile = merge_arrays_with_geometadata(
        arrays = [src_array, fill_array],
        profiles = [src_profile, fill_profile],
        resampling='bilinear',
        nodata = src_profile['nodata'],
        dtype = src_profile['dtype'],
        method='first',
    ) 
    if save_path:
        with rasterio.open(save_path, 'w', **trg_profile) as dst:
            dst.write(trg_array)

    return trg_array, trg_profile

def merge_raster_files(paths, output_path, nodata_value=0):
    # Create a virtual raster (in-memory description of the merged DEMs)
    vrt_options = gdal.BuildVRTOptions(srcNodata=nodata_value)
    vrt_path = output_path.replace(".tif", ".vrt")  # Temporary VRT file path
    gdal.BuildVRT(vrt_path, paths, options=vrt_options)

    # Convert the virtual raster to GeoTIFF
    translate_options = gdal.TranslateOptions(noData=nodata_value)
    gdal.Translate(output_path, vrt_path, options=translate_options)

    # Optionally, clean up the temporary VRT file
    os.remove(vrt_path)

def merge_arrays_with_geometadata(
    arrays: list[np.ndarray],
    profiles: list[dict],
    resampling: str = 'bilinear',
    nodata: Union[float, int] = np.nan,
    dtype: str = None,
    method: str = 'first',
) -> tuple[np.ndarray, dict]:
    # https://github.com/ACCESS-Cloud-Based-InSAR/dem-stitcher/blob/dev/src/dem_stitcher/merge.py
    n_dim = arrays[0].shape
    if len(n_dim) not in [2, 3]:
        raise ValueError('Currently arrays must be in BIP format' 'i.e. channels x height x width or flat array')
    if len(set([len(arr.shape) for arr in arrays])) != 1:
        raise ValueError('All arrays must have same number of dimensions i.e. 2 or 3')

    if len(n_dim) == 2:
        arrays_input = [arr[np.newaxis, ...] for arr in arrays]
    else:
        arrays_input = arrays

    if (len(arrays)) != (len(profiles)):
        raise ValueError('Length of arrays and profiles needs to be the same')

    memfiles = [MemoryFile() for p in profiles]
    datasets = [mfile.open(**p) for (mfile, p) in zip(memfiles, profiles)]
    [ds.write(arr) for (ds, arr) in zip(datasets, arrays_input)]

    merged_arr, merged_trans = merge(
        datasets, resampling=Resampling[resampling], method=method, nodata=nodata, dtype=dtype
    )

    prof_merged = profiles[0].copy()
    prof_merged['transform'] = merged_trans
    prof_merged['count'] = merged_arr.shape[0]
    prof_merged['height'] = merged_arr.shape[1]
    prof_merged['width'] = merged_arr.shape[2]
    if nodata is not None:
        prof_merged['nodata'] = nodata
    if dtype is not None:
        prof_merged['dtype'] = dtype

    [ds.close() for ds in datasets]
    [mfile.close() for mfile in memfiles]

    return merged_arr, prof_merged