from affine import Affine
import math
import numpy as np
from rasterio.crs import CRS
from sar_pipeline.dem.utils.raster import (
    adjust_pixel_coordinate_from_point_to_area,
    expand_bounding_box_to_pixel_edges,
)
from pathlib import Path
import shapely.geometry
import logging

logger = logging.getLogger(__name__)

from sar_pipeline.dem.utils.spatial import BoundingBox


def buffer_bounds_cop_glo30(
    bounds: BoundingBox | tuple[float | int, float | int, float | int, float | int],
    pixel_buffer: int | None = None,
    degree_buffer: float | int | None = None,
) -> BoundingBox:
    """Buffer a bounding box by a fixed number of pixels or distance in decimal degrees

    Parameters
    ----------
    bounds : BoundingBox | tuple[float  |  int, float  |  int, float  |  int, float  |  int]
        The set of bounds (min_lon, min_lat, max_lon, max_lat)
    pixel_buffer : int | None, optional
        Number of pixels to buffer, by default None
    degree_buffer : float | int | None, optional
        Distance (in decimal degrees) to buffer by, by default None

    Returns
    -------
    BoundingBox
        Buffered bounds
    """

    if isinstance(bounds, tuple):
        bounds = BoundingBox(*bounds)

    lon_spacing, lat_spacing = get_cop_glo30_spacing(bounds)

    if not pixel_buffer and not degree_buffer:
        logger.warning("No buffer has been provided.")
        return bounds

    if degree_buffer and pixel_buffer:
        logger.warning(
            "Both pixel and degree buffer provided. Degree buffer will be used."
        )
        pixel_buffer = None

    if pixel_buffer:

        buffer = (pixel_buffer * lon_spacing, pixel_buffer * lat_spacing)

    if degree_buffer:
        buffer = (degree_buffer, degree_buffer)

    new_xmin = max(bounds.xmin - buffer[0], -180.0)
    new_ymin = max(bounds.ymin - buffer[1], -90.0)
    new_xmax = min(bounds.xmax + buffer[0], 180 - 0.5 * lon_spacing)
    new_ymax = min(bounds.ymax + buffer[1], 90.0)

    return BoundingBox(new_xmin, new_ymin, new_xmax, new_ymax)


def get_cop_glo30_files_covering_bounds(
    bounds: BoundingBox | tuple[float | int, float | int, float | int, float | int],
    cop30_folder_path: Path,
    check_exists: bool = True,
    search_buffer=0.3,
    tifs_in_subfolder=True,
) -> list[str]:
    """Generate a list of the required dem paths based on the bounding coords. The
    function searches the specified folder.

    Parameters
    ----------
    bounds : tuple
        The set of bounds (min_lon, min_lat, max_lon, max_lat)
    check_exists : bool, optional
        Check if the file exists, by default True
    cop30_folder_path : str, optional
        Path to the tile folders, by default COP30_FOLDER_PATH

    Returns
    -------
    list[str]
        List of paths for required dem tiles in bounds
    """
    if isinstance(bounds, tuple):
        bounds = BoundingBox(*bounds)

    # add a buffer to the search
    bounds = BoundingBox(
        *shapely.geometry.box(*bounds.bounds).buffer(search_buffer).bounds
    )
    # logic to find the correct files based on data being stored in each tile folder
    min_lat = math.floor(bounds.ymin) if bounds.ymin < 0 else math.ceil(bounds.ymin)
    max_lat = math.ceil(bounds.ymax) if bounds.ymax < 0 else math.floor(bounds.ymax) + 1
    min_lon = math.floor(bounds.xmin) if bounds.xmin < 0 else math.floor(bounds.xmin)
    max_lon = math.ceil(bounds.xmax) if bounds.xmax < 0 else math.ceil(bounds.xmax)

    lat_range = list(range(min_lat, max_lat))
    lon_range = list(range(min_lon, max_lon))

    logger.info(f"lat tile range: {lat_range}")
    logger.info(f"lon tile range: {lon_range}")
    dem_paths = []
    dem_folders = []

    for lat in lat_range:
        for lon in lon_range:
            lat_dir = "N" if lat >= 0 else "S"
            lon_dir = "E" if lon >= 0 else "W"
            dem_foldername = f"Copernicus_DSM_COG_10_{lat_dir}{abs(lat):02d}_00_{lon_dir}{abs(lon):03d}_00_DEM"
            if tifs_in_subfolder:
                dem_subpath = f"{dem_foldername}/{dem_foldername}.tif"
            else:
                dem_subpath = f"{dem_foldername}.tif"
            dem_path = cop30_folder_path.joinpath(dem_subpath)
            if check_exists:
                # check the file exists, e.g. over water will not be a file
                if dem_path.exists:
                    dem_paths.append(dem_path)
                    dem_folders.append(dem_foldername)
            else:
                dem_paths.append(dem_path)
    return sorted(list(set(dem_paths)))


def get_cop_glo30_spacing(
    bounds: BoundingBox | tuple[float | int, float | int, float | int, float | int],
) -> tuple[float, float]:
    """Get the longitude and latitude spacing for the Copernicus GLO30 DEM at the centre of the bounds

    Parameters
    ----------
    bounds : BoundingBox | tuple[float  |  int, float  |  int, float  |  int, float  |  int]
        The set of bounds (min_lon, min_lat, max_lon, max_lat)

    Returns
    -------
    tuple[float, float]
        A tuple of the longitude and latitude spacing

    Raises
    ------
    ValueError
        If the absolute latitude of bounds does not fall within expected range (<90)
    """

    if isinstance(bounds, tuple):
        bounds = BoundingBox(*bounds)

    mean_latitude = abs((bounds.ymin + bounds.ymax) / 2)

    minimum_pixel_spacing = 0.0002777777777777778

    # Latitude spacing
    latitude_spacing = minimum_pixel_spacing

    # Longitude spacing
    if mean_latitude < 50:
        longitude_spacing = minimum_pixel_spacing
    elif mean_latitude < 60:
        longitude_spacing = minimum_pixel_spacing * 1.5
    elif mean_latitude < 70:
        longitude_spacing = minimum_pixel_spacing * 2
    elif mean_latitude < 80:
        longitude_spacing = minimum_pixel_spacing * 3
    elif mean_latitude < 85:
        longitude_spacing = minimum_pixel_spacing * 5
    elif mean_latitude < 90:
        longitude_spacing = minimum_pixel_spacing * 10
    else:
        raise ValueError("cannot resolve cop30m lattitude")

    return (longitude_spacing, latitude_spacing)


def get_cop_glo30_tile_transform(
    origin_lon: float, origin_lat: float, spacing_lon: float, spacing_lat: float
) -> Affine:
    """Generates an Affine transform with the origin in the top-left of the Copernicus GLO30 DEM
    containing the provided origin.

    Parameters
    ----------
    origin_lon : float
        Origin longitude
    origin_lat : float
        Origin latitude
    spacing_lon : float
        Pixel spacing in longitude
    spacing_lat : float
        Pixel spacing in latitude

    Returns
    -------
    Affine
        An Affine transform with the origin at the top-left pixel of the tile containing the supplied origin
    """

    # Find whole degree value containing the origin
    whole_degree_origin_lon = math.floor(origin_lon)
    whole_degree_origin_lat = math.ceil(origin_lat)

    # Create the scaling from spacing
    scaling = (spacing_lon, -spacing_lat)

    # Adjust to the required 0.5 pixel offset
    adjusted_origin = adjust_pixel_coordinate_from_point_to_area(
        (whole_degree_origin_lon, whole_degree_origin_lat), scaling
    )

    transfrom = Affine.translation(*adjusted_origin) * Affine.scale(*scaling)

    return transfrom


def make_empty_cop_glo30_profile_for_bounds(
    bounds: BoundingBox | tuple[float | int, float | int, float | int, float | int],
) -> tuple[tuple, dict]:
    """make an empty cop30m dem rasterio profile based on a set of bounds.
    The desired pixel spacing changes based on lattitude
    see : https://copernicus-dem-30m.s3.amazonaws.com/readme.html

    Parameters
    ----------
    bounds : BoundingBox | tuple[float | int, float | int, float | int, float | int]
        The set of bounds (min_lon, min_lat, max_lon, max_lat)
    pixel_buffer | int
        The number of pixels to add as a buffer to the profile

    Returns
    -------
    dict
        A rasterio profile

    Raises
    ------
    ValueError
        If the latitude of the supplied bounds cannot be
        associated with a target pixel size
    """
    if isinstance(bounds, tuple):
        bounds = BoundingBox(*bounds)

    spacing_lon, spacing_lat = get_cop_glo30_spacing(bounds)

    glo30_transform = get_cop_glo30_tile_transform(
        bounds.xmin, bounds.ymax, spacing_lon, spacing_lat
    )

    # Expand the bounds to the edges of pixels
    expanded_bounds, expanded_transform = expand_bounding_box_to_pixel_edges(
        bounds.bounds, glo30_transform
    )
    if isinstance(expanded_bounds, tuple):
        expanded_bounds = BoundingBox(*expanded_bounds)

    # Convert bounds from world to pixel to get width and height
    left_px, top_px = ~expanded_transform * expanded_bounds.top_left
    right_px, bottom_px = ~expanded_transform * expanded_bounds.bottom_right

    width = abs(round(right_px) - round(left_px))
    height = abs(round(bottom_px) - round(top_px))

    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "nodata": np.nan,
        "width": width,
        "height": height,
        "count": 1,
        "crs": CRS.from_epsg(4326),
        "transform": expanded_transform,
        "blockysize": 1,
        "tiled": False,
        "interleave": "band",
    }

    return (expanded_bounds, profile)
