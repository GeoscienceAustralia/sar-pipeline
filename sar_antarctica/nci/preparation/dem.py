import shapely
from shapely.geometry import box
import numpy as np
import os
from pathlib import Path
import logging
from affine import Affine
from rasterio.crs import CRS
import geopandas as gpd

from .geoid import remove_geoid
from ...utils.raster import (
    expand_raster_to_bounds,
    reproject_raster,
    merge_raster_files,
    bounds_from_profile,
    merge_arrays_with_geometadata,
)
from ...utils.spatial import (
    adjust_bounds,
    get_local_utm,
)

COP30_FOLDER_PATH = Path(
    "/g/data/v10/eoancillarydata-2/elevation/copernicus_30m_world/"
)
GEOID_TIF_PATH = Path(
    "/g/data/yp75/projects/ancillary/geoid/us_nga_egm2008_1_4326__agisoft.tif"
)
COP30_GPKG_PATH = Path("/g/data/yp75/projects/ancillary/dem/copdem_tindex.gpkg")


def get_cop30_dem_for_bounds(
    bounds: tuple,
    save_path: Path,
    ellipsoid_heights: bool = True,
    buffer_pixels: int = 1,
    adjust_for_high_lat_and_buffer=True,
    cop30_index_path: Path = COP30_GPKG_PATH,
    cop30_folder_path: Path = COP30_FOLDER_PATH,
    geoid_tif_path: Path = GEOID_TIF_PATH,
) -> tuple[np.ndarray, dict]:
    """Logic for acquiting the cop30m DEM for a given set of bounds on the NCI. The returned
    dem will fully encompass the specified bounds. There may be additional data outside of
    the bounds as all data from the merged tiles is returned.

    Parameters
    ----------
    bounds : tuple
        the set of bounds (min_lon, min_lat, max_lon, max_lat)
    save_path : Path
        Path where the DEM.tif should be saved
    ellipsoid_heights : bool, optional
        Return ellipsoid referenced heights by subtracting the geoid, by default True
    buffer_pixels : int
        Add a pixel buffer to ensure bounds are fully enclosed. by default 1.
    adjust_for_high_lat_and_buffer: bool.
        adjust for high latitudes to ensure bounds are completely enclosed. Buffer
        scene after conversion. Default buffer is 0.1 degrees.
    cop30_vrt_path : Path
        Path to the .vrt for the COP30 DEM
    geoid_tif_path : Path
        Path to the .tif file for the geoid

    Returns
    -------
    tuple [np.darray, dict]
        dem array and dem rasterio profile
    """

    assert (
        cop30_index_path or cop30_folder_path
    ), "Either a `cop30_index_path` or `cop30_folder_path` must be provided"

    if cop30_index_path and cop30_folder_path:
        logging.info(
            f"both `cop30_index_path` and `cop30_folder_path` provided. `cop30_index_path` used by default"
        )

    logging.info(f"Getting cop30m dem that covers bounds: {bounds}")
    # check if scene crosses the AM
    antimeridian_crossing = check_s1_bounds_cross_antimeridian(
        bounds, max_scene_width=8
    )
    if antimeridian_crossing:
        logging.warning("DEM crosses the dateline/antimeridian")
        logging.info("Finding best crs for area")
        target_crs = get_target_antimeridian_projection(bounds)
        logging.warning(f"Data will be returned in EPSG:{target_crs} projection")
        # split the scene into left and right
        logging.info(f"Splitting bounds into left and right side of antimeridian")
        bounds_left, bounds_right = split_s1_bounds_at_am_crossing(bounds, lat_buff=0)
        logging.info(f"Bounds left: {bounds_left}")
        logging.info(f"Bounds right: {bounds_right}")
        # use recursion to create dems for the left and right side of AM
        # when passed back into the top function, this section will be skipped, creating
        # A valid dem for each side which we can then merge at the desired CRS
        # Add an additional buffer to ensure full coverage over dateline
        left_save_path = (
            ".".join(str(save_path).split(".")[0:-1])
            + "_left."
            + str(save_path).split(".")[-1]
        )
        logging.info(f"Getting tiles for left bounds")
        get_cop30_dem_for_bounds(
            bounds_left,
            left_save_path,
            ellipsoid_heights,
            buffer_pixels=10,
            cop30_index_path=cop30_index_path,
            cop30_folder_path=cop30_folder_path,
            geoid_tif_path=geoid_tif_path,
        )
        right_save_path = (
            ".".join(str(save_path).split(".")[0:-1])
            + "_right."
            + str(save_path).split(".")[-1]
        )
        logging.info(f"Getting tiles for right bounds")
        get_cop30_dem_for_bounds(
            bounds_right,
            right_save_path,
            ellipsoid_heights,
            buffer_pixels=10,
            cop30_index_path=cop30_index_path,
            cop30_folder_path=cop30_folder_path,
            geoid_tif_path=geoid_tif_path,
        )
        # reproject to 3031 and merge
        logging.info(
            f"Reprojecting left and right side of antimeridian to EPGS:{target_crs}"
        )
        l_dem_arr, l_dem_profile = reproject_raster(left_save_path, target_crs) # out_path=left_save_path
        r_dem_arr, r_dem_profile = reproject_raster(right_save_path, target_crs) # out_path=right_save_path
        logging.info(f"Merging across antimeridian")
        dem_arr, dem_profile = merge_arrays_with_geometadata(
            arrays = [l_dem_arr, r_dem_arr],
            profiles = [l_dem_profile, r_dem_profile],
            method = "max",
            output_path=save_path,
        )
        return dem_arr, dem_profile
    else:
        logging.info(f"Getting cop30m dem for bounds: {bounds}")
        if adjust_for_high_lat_and_buffer:
            logging.info(f"Expanding bounds by buffer and for high latitude warping")
            bounds = expand_bounds_at_high_lat_and_buffer(bounds, buffer=0.1)
            logging.info(f"Getting cop30m dem for expanded bounds: {bounds}")
        if cop30_index_path:
            logging.info(f"Finding intersecting DEM files from: {cop30_index_path}")
            dem_paths = find_required_dem_paths_from_index(
                bounds, cop30_index_path=cop30_index_path
            )
        else:
            logging.info(f"Searching for DEM in folder: {cop30_folder_path}")
            dem_paths = find_required_dem_tile_paths_by_filename(
                bounds, cop30_folder_path=cop30_folder_path
            )
        logging.info(f"{len(dem_paths)} tiles found in bounds")
        for p in dem_paths:
            logging.info(p)
        if len(dem_paths) == 0:
            logging.warning(
                "No DEM tiles found, assuming over water and creating zero dem for bounds"
            )
            fill_value = 0
            dem_profile = make_empty_cop30m_profile(bounds)
            dem_arr, dem_profile = expand_raster_to_bounds(
                bounds,
                src_profile=dem_profile,
                save_path=save_path,
                fill_value=fill_value,
                buffer_pixels=buffer_pixels,
            )
        else:
            logging.info(f"Merging tiles and reading data")
            dem_arr, dem_profile = merge_raster_files(
                dem_paths,
                output_path=save_path,
                bounds=bounds,
                buffer_pixels=buffer_pixels,
                vrt_bounds=buffer_bounds(bounds,0.5)
            )
        logging.info(f"Check the dem covers the required bounds")
        dem_bounds = bounds_from_profile(dem_profile)
        logging.info(f"Dem bounds: {dem_bounds}")
        logging.info(f"Target bounds: {bounds}")
        bounds_filled_by_dem = box(*bounds).within(box(*dem_bounds))
        logging.info(f"Dem covers target: {bounds_filled_by_dem}")
        if not bounds_filled_by_dem:
            warn_msg = (
                "The Cop30 DEM bounds do not fully cover the requested bounds. "
                "Try increasing the 'buffer_pixels' value. Note at the antimeridian "
                "This is expected, with bounds being slighly smaller on +ve side. "
                "e.g. max_lon is 179.9999 < 180."
            )
            logging.warning(warn_msg)
        if ellipsoid_heights:
            logging.info(
                f"Subtracting the geoid from the DEM to return ellipsoid heights"
            )
            logging.info(f"Using geoid file: {geoid_tif_path}")
            dem_arr = remove_geoid(
                dem_arr=dem_arr,
                dem_profile=dem_profile,
                geoid_path=geoid_tif_path,
                dem_area_or_point="Point",
                buffer_pixels=2,
                save_path=save_path,
            )
        return dem_arr, dem_profile

def buffer_bounds(bounds: tuple, buffer: float) -> tuple:
    """buffer the tuple bounds by the provided buffer

    Parameters
    ----------
    bounds : tuple
        the set of bounds (min_lon, min_lat, max_lon, max_lat)
    buffer : float
        The buffer to add to the bounds

    Returns
    -------
    tuple
        the buffered bounds (min_lon, min_lat, max_lon, max_lat)
    """
    return tuple(list(box(*bounds).buffer(buffer).bounds))



def expand_bounds_at_high_lat_and_buffer(bounds: tuple, buffer: float) -> tuple:
    """Expand the bounds for high lattitudes, and add a buffer. The
    provided bounds sometimes do not contain the full scene due to
    warping at high latitudes. Solve this by converting bounds to polar
    steriographic, getting bounds, converting back to 4326. At high
    latitudes this will increase the longitude range. A buffer is also
    added where specified.

    Parameters
    ----------
    bounds : tuple
        the set of bounds (min_lon, min_lat, max_lon, max_lat)
    buffer : float
        The buffer to add to the bounds after they have been adjusted
        if at high latitude

    Returns
    -------
    tuple
        the expanded bounds (min_lon, min_lat, max_lon, max_lat)
    """
    min_lat = min(bounds[1], bounds[3])
    if min_lat < -50:
        # adjust the bounds at high southern latitudes
        bounds = adjust_bounds(bounds, src_crs=4326, ref_crs=3031)
    if min_lat > 50:
        # adjust the bounds at high norther latitudes
        bounds = adjust_bounds(bounds, src_crs=4326, ref_crs=3995)
    exp_bounds = list(box(*bounds).buffer(buffer).bounds)
    exp_bounds[0] = (
        bounds[0] if exp_bounds[0] < -180 else exp_bounds[0]
    )  # keep original
    exp_bounds[2] = bounds[2] if exp_bounds[2] > 180 else exp_bounds[2]  # keep original
    return tuple(exp_bounds)


def find_required_dem_tile_paths_by_filename(
    bounds: tuple,
    check_exists: bool = True,
    cop30_folder_path: Path = COP30_FOLDER_PATH,
    search_buffer=0.5,
    tifs_in_subfolder=True,
) -> list[str]:
    """generate a list of the required dem paths based on the bounding coords. The
    function searches the specified folder.

    Parameters
    ----------
    bounds : tuple
        the set of bounds (min_lon, min_lat, max_lon, max_lat)
    check_exists : bool, optional
        Check if the file exists, by default True
    cop30_folder_path : str, optional
        path to the tile folders, by default COP30_FOLDER_PATH

    Returns
    -------
    list[str]
        list of paths for required dem tiles in bounds
    """

    # add a buffer to the search
    bounds = box(*bounds).buffer(search_buffer).bounds

    # logic to find the correct files based on data being stored in each tile folder
    min_lat = np.floor(bounds[1]) if bounds[1] < 0 else np.ceil(bounds[1])
    max_lat = np.ceil(bounds[3]) if bounds[3] < 0 else np.floor(bounds[3]) + 1
    min_lon = np.floor(bounds[0]) if bounds[0] < 0 else np.floor(bounds[0])
    max_lon = np.ceil(bounds[2]) if bounds[2] < 0 else np.ceil(bounds[2])
    lat_range = list(range(int(min_lat), int(max_lat)))
    lon_range = list(range(int(min_lon), int(max_lon)))
    logging.info(f"lat tile range: {lat_range}")
    logging.info(f"lon tile range: {lon_range}")
    dem_paths = []
    dem_folders = []

    for lat in lat_range:
        for lon in lon_range:
            lat_dir = "N" if lat >= 0 else "S"
            lon_dir = "E" if lon >= 0 else "W"
            dem_foldername = f"Copernicus_DSM_COG_10_{lat_dir}{int(abs(lat)):02d}_00_{lon_dir}{int(abs(lon)):03d}_00_DEM"
            if tifs_in_subfolder:
                dem_subpath = f"{dem_foldername}/{dem_foldername}.tif"
            else:
                dem_subpath = f"{dem_foldername}.tif"
            dem_path = os.path.join(cop30_folder_path, dem_subpath)
            if check_exists:
                # check the file exists, e.g. over water will not be a file
                if os.path.exists(dem_path):
                    dem_paths.append(dem_path)
                    dem_folders.append(dem_foldername)
            else:
                dem_paths.append(dem_path)
    return sorted(list(set(dem_paths)))


def find_required_dem_paths_from_index(
    bounds: tuple,
    cop30_index_path=COP30_GPKG_PATH,
    search_buffer=0.5,
) -> list[str]:

    gdf = gpd.read_file(cop30_index_path)
    bounding_box = box(*bounds).buffer(search_buffer)

    if gdf.crs is not None:
        # ensure same crs
        bounding_box = (
            gpd.GeoSeries([bounding_box], crs="EPSG:4326").to_crs(gdf.crs).iloc[0]
        )
    # Find rows that intersect with the bounding box
    intersecting_tiles = gdf[gdf.intersects(bounding_box)]
    if len(intersecting_tiles) > 0:
        return sorted(intersecting_tiles.location.tolist())
    else:
        return []


def check_s1_bounds_cross_antimeridian(
    bounds: tuple, max_scene_width: int = 20
) -> bool:
    """Check if the s1 scene bounds cross the antimeridian. The bounds of a sentinel-1
    are valid at the antimeridian, just very large. By setting a max scene width, we
    can determine if the antimeridian is crossed. Alternate scenario is a bounds
    with a very large width (i.e. close to the width of the earth).

    Parameters
    ----------
    bounds : tuple
        the set of bounds (min_lon, min_lat, max_lon, max_lat)
    max_scene_width : int, optional
        maximum allowable width of the scene bounds, by default 20

    Returns
    -------
    bool
        if the bounds cross the antimeridian
    """

    min_x = -180 + max_scene_width  # -160
    max_x = 180 - max_scene_width  # 160
    if (bounds[0] < min_x) and (bounds[0] > -180):
        if bounds[2] > max_x and bounds[2] < 180:
            return True
    return False


def split_s1_bounds_at_am_crossing(bounds: tuple, lat_buff: float = 0) -> list[tuple]:
    """split the s1 bounds into bounds on the left and
    right of the antimeridian.

    Parameters
    ----------
    bounds : tuple
        the set of bounds (min_lon, min_lat, max_lon, max_lat)
    lat_buff : float, optional
        An additional buffer to subract from lat, by default 0.

    Returns
    -------
    list[tuple]
        a list containing two sets of bounds for the left and right of the antimeridian
    """
    max_negative_x = min([x for x in [bounds[0], bounds[2]] if x < 0])
    min_positive_x = min([x for x in [bounds[0], bounds[2]] if x > 0])
    min_y = min([bounds[1], bounds[3]]) - lat_buff
    max_y = max([bounds[1], bounds[3]]) + lat_buff
    min_y = -90 if min_y < -90 else min_y
    max_y = 90 if max_y > 90 else max_y
    bounds_left = (-180, min_y, max_negative_x, max_y)
    bounds_right = (min_positive_x, min_y, 180, max_y)
    return [tuple(bounds_left), tuple(bounds_right)]


def get_target_antimeridian_projection(bounds: tuple) -> int:
    """depending where were are on the earth, the desired
    crs at the antimeridian will change. e.g. polar stereo
    is desired at high and low lats, local utm zone elsewhere
    (e.g. at the equator).

    Parameters
    ----------
    bounds : tuple
        the set of bounds (min_lon, min_lat, max_lon, max_lat)

    Returns
    -------
    int
        The CRS in integer form: e.g. 3031
    """
    min_lat = min(bounds[1], bounds[3])
    target_crs = (
        3031
        if min_lat < -50
        else 3995 if min_lat > 50 else get_local_utm(bounds, antimeridian=True)
    )
    return target_crs


def make_empty_cop30m_profile(bounds: tuple) -> dict:
    """make an empty cop30m dem rasterio profile based on a set of bounds.
    The desired pixel spacing changes based on lattitude
    see : https://copernicus-dem-30m.s3.amazonaws.com/readme.html

    Parameters
    ----------
    bounds : tuple
        the set of bounds (min_lon, min_lat, max_lon, max_lat)

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

    lat_res = 0.0002777777777777778
    mean_lat = abs((bounds[1] + bounds[3]) / 2)
    if mean_lat < 50:
        lon_res = lat_res
    elif mean_lat < 60:
        lon_res = lat_res * 1.5
    elif mean_lat < 70:
        lon_res = lat_res * 2
    elif mean_lat < 80:
        lon_res = lat_res * 3
    elif mean_lat < 85:
        lon_res = lat_res * 5
    elif mean_lat < 90:
        lon_res = lat_res * 10
    else:
        raise ValueError("cannot resolve cop30m lattitude")

    min_x, min_y, max_x, max_y = bounds
    transform = Affine.translation(min_x, max_y) * Affine.scale(lon_res, -lat_res)

    return {
        "driver": "GTiff",
        "dtype": "float32",
        "nodata": np.nan,
        "width": abs(int((bounds[2] - bounds[0]) / lon_res)),
        "height": abs(int((bounds[3] - bounds[1]) / lat_res)),
        "count": 1,
        "crs": CRS.from_epsg(4326),
        "transform": transform,
        "blockysize": 1,
        "tiled": False,
        "interleave": "band",
    }