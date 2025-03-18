import os
from typing import Optional

import numpy as np
import pyproj
from osgeo import gdal
from shapely.geometry import box
import rasterio
from pyproj import Transformer
from affine import Affine
from pathlib import Path
from rasterio.transform import from_origin, array_bounds
from rasterio.warp import calculate_default_transform, reproject
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.merge import merge
from rasterio.windows import from_bounds
import math


def adjust_pixel_coordinate_from_point_to_area(
    point_coordinate: tuple[float, float], scaling: tuple[float, float]
) -> tuple:

    point_affine = Affine.translation(*point_coordinate) * Affine.scale(*scaling)
    area_affine = point_affine * Affine.translation(-0.5, -0.5)

    area_coordinate = (area_affine.xoff, area_affine.yoff)

    return area_coordinate


def expand_bounding_box_to_pixel_edges(
    bounding_box_world: tuple[float, float, float, float],
    world_affine: Affine,
):

    # Unpack bounding box
    bbox_min_x, bbox_min_y, bbox_max_x, bbox_max_y = bounding_box_world

    # Create coordinates for top-left and bottom-right of bounding box in world space
    bounding_box_tl_world = (bbox_min_x, bbox_max_y)
    bounding_box_br_world = (bbox_max_x, bbox_min_y)

    # Convert to pixel space
    bounding_box_tl_px = ~world_affine * bounding_box_tl_world
    bounding_box_br_px = ~world_affine * bounding_box_br_world

    # Round bounding box coordinates to pixel edges to produce expanded box
    expanded_box_tl_px = tuple(math.floor(px) for px in bounding_box_tl_px)
    expanded_box_br_px = tuple(math.ceil(px) for px in bounding_box_br_px)

    # Convert expanded box to world space
    expanded_box_tl_world = world_affine * expanded_box_tl_px
    expanded_box_br_world = world_affine * expanded_box_br_px

    # Extract bounds of expanded box
    expbox_min_x = expanded_box_tl_world[0]
    expbox_max_y = expanded_box_tl_world[1]
    expbox_max_x = expanded_box_br_world[0]
    expbox_min_y = expanded_box_br_world[1]

    # Construct a the expanded box tuple (minx, miny, maxx, maxy)
    expanded_box_world = (expbox_min_x, expbox_min_y, expbox_max_x, expbox_max_y)
    # Construct the new transform
    expanded_box_affine_world = Affine.translation(
        expbox_min_x, expbox_max_y
    ) * Affine.scale(world_affine.a, world_affine.e)

    return expanded_box_world, expanded_box_affine_world


def bounds_from_profile(profile):
    # returns the bounds from a rasterio profile dict
    return array_bounds(profile["height"], profile["width"], profile["transform"])


def reproject_raster(
    src_path: str | Path, crs: int, out_path: Optional[str | Path] = None
):
    """Reproject raster to desired crs

    Parameters
    ----------
    src_path : str | Path
        source raster
    out_path : Optional[str | Path]
        where to write reprj raster
    crs : int
        desired crs

    Returns
    -------
    None
    """
    # reproject raster to project crs
    with rasterio.open(src_path) as src:
        src_crs = src.crs
        transform, width, height = calculate_default_transform(
            src_crs, crs, src.width, src.height, *src.bounds
        )
        profile = src.meta.copy()

        # get crs proj
        crs = pyproj.CRS(f"EPSG:{crs}")

        profile.update(
            {"crs": crs, "transform": transform, "width": width, "height": height}
        )

        # Create an empty array for the reprojected raster
        reprojected_array = np.empty((src.count, height, width), dtype=src.dtypes[0])

        for i in range(1, src.count + 1):
            reproject(
                source=rasterio.band(src, i),
                destination=reprojected_array[i - 1],  # Use the in-memory array
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=transform,
                dst_crs=crs,
                resampling=Resampling.nearest,
            )

        if out_path is not None:
            with rasterio.open(out_path, "w", **profile) as dst:
                for i in range(src.count):
                    dst.write(reprojected_array[i], i + 1)

        return reprojected_array, profile


def expand_raster_to_bounds(
    trg_bounds: tuple,
    src_path: str = "",
    src_profile: Optional[dict] = None,
    src_array: Optional[np.ndarray] = None,
    fill_value: float = 0,
    buffer_pixels: int = 0,
    save_path: str = "",
) -> tuple[np.ndarray, dict]:
    """Expand the extent of the input array to the target bounds specified
    by the user. Either a src_path to expand, src_profile to construct a new raster,
    or src_profile and src_array o expand must be provided/

    Parameters
    ----------
    trg_bounds : tuple
        target bounds for the new raster
    src_path : str, optional
        str, path to a source raster ''
    src_profile : dict, optional
        raster profile corresponding to src_array, or a transform to create a new raster
    src_array : np.ndarray, optional
        source array with values to expand, by default None
    fill_value : float, optional
        The fille value when expanding, by default 0
    buffer_pixels : int, optional
        Additional buffer pixels around bounds
    save_path : str, optional
        where to save new raster, by default ''

    Returns
    -------
    -> tuple[np.ndarray, dict]
        new array and rasterio profile
    """

    assert (
        src_path or (src_profile and src_array is not None) or src_profile
    ), "Either src_path, src_array and src_profile, or src_profile must be provided."

    if src_path:
        with rasterio.open(src_path) as src:
            src_array = src.read(1)
            src_profile = src.profile
            src_left, src_bottom, src_right, src_top = src.bounds
    else:
        src_bounds = array_bounds(
            src_profile["height"], src_profile["width"], src_profile["transform"]
        )
        src_left, src_bottom, src_right, src_top = src_bounds

    # Define the new bounds
    trg_left, trg_bottom, trg_right, trg_top = trg_bounds
    lon_res = abs(src_profile["transform"].a)  # Pixel width
    lat_res = abs(src_profile["transform"].e)  # Pixel height

    # determine the number of new pixels in each direction
    new_left_pixels = int(abs(trg_left - src_left) / lon_res) + buffer_pixels
    new_right_pixels = int(abs(trg_right - src_right) / lon_res) + buffer_pixels
    new_bottom_pixels = int(abs(trg_bottom - src_bottom) / lat_res) + buffer_pixels
    new_top_pixels = int(abs(trg_top - src_top) / lat_res) + buffer_pixels

    # adjust the new bounds with even pixel multiples of existing
    new_trg_left = src_left - new_left_pixels * lon_res
    new_trg_right = src_right + new_right_pixels * lon_res
    new_trg_bottom = src_bottom - new_bottom_pixels * lat_res
    new_trg_top = src_top + new_top_pixels * lat_res

    # keep source if they are already greater than the desired bounds
    new_trg_left = src_left if src_left < trg_left else new_trg_left
    new_trg_right = src_right if src_right > trg_right else new_trg_right
    new_trg_bottom = src_bottom if src_bottom < trg_bottom else new_trg_bottom
    new_trg_top = src_top if src_top < trg_top else new_trg_top

    # Calculate the new width and height, should be integer values
    new_width = int((new_trg_right - new_trg_left) / lon_res)
    new_height = int((new_trg_top - new_trg_bottom) / lat_res)

    # Define the new transformation matrix
    transform = from_origin(new_trg_left, new_trg_top, lon_res, lat_res)

    # Create a new raster dataset with expanded bounds
    fill_profile = src_profile.copy()
    fill_profile.update(
        {"width": new_width, "height": new_height, "transform": transform}
    )
    fill_array = np.full(
        (1, new_height, new_width), fill_value=fill_value, dtype=src_profile["dtype"]
    )

    if src_array is not None:
        # if an existing src array (e.g. dem) is provided to expand
        trg_array, trg_profile = merge_arrays_with_geometadata(
            arrays=[src_array, fill_array],
            profiles=[src_profile, fill_profile],
            resampling="bilinear",
            nodata=src_profile["nodata"],
            dtype=src_profile["dtype"],
            method="first",
        )
    else:
        # we are not expanding an existing array
        # return the fill array that has been constructed based on the src_profile
        trg_array, trg_profile = fill_array, fill_profile
    if save_path:
        with rasterio.open(save_path, "w", **trg_profile) as dst:
            dst.write(trg_array)

    return trg_array, trg_profile


def read_vrt_in_bounds(
    vrt_path: str,
    bounds: tuple,
    output_path: str = "",
    return_data: bool = True,
    buffer_pixels: int = 0,
    set_nodata: Optional[float] = None,
):
    """Read in data from a vrt file in the specified bounds

    Parameters
    ----------
    vrt_path : str
        path to vrt describing rasters
    output_path : str
        where to save new raster
    bounds : tuple
        desired bounds. If non full vrt extent returned
    return_data : bool, optional
        return array and profile, else None, by default True
    buffer_pixels : int, optional
        number of pixels to buffer bounds by, by default 0
    set_nodata : float, optional
        set the nodata value in the metadata. Note this does
        not change the value, just the metadata. None will keep
        The original. Default to None.

    Returns
    -------
    tuple[np.ndarray, dict]
        new array and rasterio profile
    """

    # make upper end of the requested integer
    # ensures the bounds are covered with requested pixel buffer
    # buffer_pixels += 0.9

    if bounds is None:
        # get all data in tiles
        if output_path:
            if set_nodata is not None:
                gdal.Translate(output_path, vrt_path, noData=set_nodata)
            else:
                gdal.Translate(output_path, vrt_path)
        if return_data:
            # Open the VRT file
            with rasterio.open(vrt_path) as src:
                # Define the profile for the GeoTIFF
                arr_profile = src.profile
                arr_profile.update(
                    driver="GTiff"
                )  # Ensure the driver is set to GeoTIFF
                arr = src.read()
                if set_nodata is not None:
                    arr_profile["nodata"] = set_nodata
            return arr, arr_profile

    else:
        # Open the VRT file
        with rasterio.open(vrt_path) as src:
            # Extract the spatial resolution, CRS, and transform of the source dataset
            src_transform = src.transform

            # Expand bounds by the buffer
            min_x, min_y, max_x, max_y = bounds

            window = from_bounds(
                min_x, min_y, max_x, max_y, transform=src_transform
            ).round()
            # window_transform = src.window_transform(window) # orig transform

            buffered_window = rasterio.windows.Window(
                window.col_off - buffer_pixels,
                window.row_off - buffer_pixels,
                window.width + buffer_pixels * 2,
                window.height + buffer_pixels * 2,
            )
            buffered_window_transform = src.window_transform(buffered_window)

            # Read data for the specified window
            data = src.read(1, window=buffered_window)  # Read the first band;

            arr_profile = src.profile.copy()
            arr_profile["transform"] = buffered_window_transform
            arr_profile["driver"] = "GTiff"
            arr_profile["count"] = 1
            arr_profile["height"] = data.shape[0]
            arr_profile["width"] = data.shape[1]
            if set_nodata is not None:
                arr_profile["nodata"] = set_nodata

            # Save the extracted data to a new GeoTIFF
            if output_path:
                with rasterio.open(output_path, "w", **arr_profile) as dst:
                    dst.write(data, 1)

            if return_data:
                return data[np.newaxis, :, :], arr_profile


def merge_raster_files(
    paths,
    output_path,
    bounds=None,
    return_data=True,
    buffer_pixels=0,
    vrt_bounds=None,
    delete_vrt=True,
):

    # Create a virtual raster (in-memory description of the merged DEMs)
    vrt_path = str(output_path).replace(".tif", ".vrt")  # Temporary VRT file path
    VRT_options = gdal.BuildVRTOptions(resolution="highest", outputBounds=vrt_bounds)
    gdal.BuildVRT(vrt_path, paths, options=VRT_options)

    res = read_vrt_in_bounds(
        vrt_path=vrt_path,
        bounds=bounds,
        output_path=output_path,
        buffer_pixels=buffer_pixels,
        return_data=return_data,
    )
    if delete_vrt:
        os.remove(vrt_path)
    if return_data:
        arr, arr_profile = res
        return arr, arr_profile


def merge_arrays_with_geometadata(
    arrays: list[np.ndarray],
    profiles: list[dict],
    resampling: str = "bilinear",
    nodata: float | int = np.nan,
    dtype: Optional[str] = None,
    method: str = "first",
    output_path: str = "",
) -> tuple[np.ndarray, dict]:
    # https://github.com/ACCESS-Cloud-Based-InSAR/dem-stitcher/blob/dev/src/dem_stitcher/merge.py
    n_dim = arrays[0].shape
    if len(n_dim) not in [2, 3]:
        raise ValueError(
            "Currently arrays must be in BIP format"
            "i.e. channels x height x width or flat array"
        )
    if len(set([len(arr.shape) for arr in arrays])) != 1:
        raise ValueError("All arrays must have same number of dimensions i.e. 2 or 3")

    if len(n_dim) == 2:
        arrays_input = [arr[np.newaxis, ...] for arr in arrays]
    else:
        arrays_input = arrays

    if (len(arrays)) != (len(profiles)):
        raise ValueError("Length of arrays and profiles needs to be the same")

    memfiles = [MemoryFile() for p in profiles]
    datasets = [mfile.open(**p) for (mfile, p) in zip(memfiles, profiles)]
    [ds.write(arr) for (ds, arr) in zip(datasets, arrays_input)]

    merged_arr, merged_trans = merge(
        datasets,
        resampling=Resampling[resampling],
        method=method,
        nodata=nodata,
        dtype=dtype,
    )

    prof_merged = profiles[0].copy()
    prof_merged["transform"] = merged_trans
    prof_merged["count"] = merged_arr.shape[0]
    prof_merged["height"] = merged_arr.shape[1]
    prof_merged["width"] = merged_arr.shape[2]
    if nodata is not None:
        prof_merged["nodata"] = nodata
    if dtype is not None:
        prof_merged["dtype"] = dtype

    [ds.close() for ds in datasets]
    [mfile.close() for mfile in memfiles]

    if output_path:
        with rasterio.open(output_path, "w", **prof_merged) as dst:
            dst.write(merged_arr)

    return merged_arr, prof_merged


def read_raster_with_bounds(file_path, bounds, buffer_pixels=0):
    """
    Reads a specific region of a raster file defined by bounds and returns the data array and profile.

    Parameters:
        file_path (str): Path to the raster file.
        bounds (tuple): Bounding box (min_x, min_y, max_x, max_y) specifying the region to read.

    Returns:
        tuple: A NumPy array of the raster data in the window and the corresponding profile.
    """

    # TODO allign pixel buffer logic with readvrt function

    with rasterio.open(file_path) as src:
        # Get pixel size from the transform
        transform = src.transform
        pixel_size_x = abs(transform.a)  # Pixel size in x-direction
        pixel_size_y = abs(transform.e)  # Pixel size in y-direction

        # Convert buffer in pixels to geographic units
        buffer_x = buffer_pixels * pixel_size_x
        buffer_y = buffer_pixels * pixel_size_y

        # Expand bounds by the buffer
        min_x, min_y, max_x, max_y = bounds
        buffered_bounds = (
            min_x - buffer_x,
            min_y - buffer_y,
            max_x + buffer_x,
            max_y + buffer_y,
        )

        # Create a window from the buffered bounds
        window = from_bounds(*buffered_bounds, transform=src.transform)

        # Clip the window to the raster's extent to avoid out-of-bounds errors
        window = window.intersection(src.window(*src.bounds))

        # Read the data within the window
        data = src.read(window=window)

        # Adjust the profile for the window
        profile = src.profile.copy()
        profile.update(
            {
                "height": window.height,
                "width": window.width,
                "transform": src.window_transform(window),
            }
        )

    return data, profile
