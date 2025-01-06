import shapely
import numpy as np
import os
import logging
from osgeo import gdal

COP30_FOLDER_PATH = '/path/to/cop30m_root'
GEOID_PATH = '/path/to/geoid'

def merge_cop30_tiles_for_bounds(bounds: tuple, ellipsoid_heights: True, save_path: str = ''): 
    ...
    # check if scene crosses the AM
    antimeridian_crossing = check_bounds_cross_antimeridian(bounds, max_scene_width=8)
    if antimeridian_crossing:
        logging.warning('scene crosses the antimeridian/dateline')
        logging.warning('Data will be returned in 3031 projection') # assumes only here is requested
        # split the scene into left and right
        bounds_left, bounds_right = split_bounds_at_am_crossing(bounds, lat_buff=0)
        # use recursion like a legend to create dems for the left and right side
        left_save_path = '.'.join(save_path.split('.')[0:-1]) + "_left." + save_path.split('.')[-1]
        merge_cop30_tiles_for_bounds(bounds_left, ellipsoid_heights, left_save_path)
        right_save_path = '.'.join(save_path.split('.')[0:-1]) + "_right." + save_path.split('.')[-1]
        merge_cop30_tiles_for_bounds(bounds_right, ellipsoid_heights, right_save_path)
        # reproject to 3031 and merge 
        # reproject_raster(left_save_path, 3031, left_save_path)
        # reproject_raster(right_save_path, 3031, right_save_path)
        # merge_dems(left_save_path, right_save_path)
    else:
        # get a list of the required dem paths
        dem_paths = find_required_dem_tile_paths(bounds)
        if len(dem_paths) == 0:
            logging.warning('No DEM files found, scene is over water or paths cannot be found')
            # generate raster of zeros covering area
            # merged_dem = tif_from_bounds()
        else:
            merged_dem = merge_dems(dem_paths, 'merged_tmp.tif', nodata_value=np.nan)
            # check the dem covers the required bounds
            # if not, fill the raster to the desired bounds
            # https://github.com/ACCESS-Cloud-Based-InSAR/dem-stitcher/commit/6f1ce30b3b3b5e5fd95d1a5f4a15ac67652bfb45
        if ellipsoid_heights:
            # subtract the geoid from the DEM
            ...

def merge_dems(dem_paths, output_path, nodata_value=0):
    # Create a virtual raster (in-memory description of the merged DEMs)
    vrt_options = gdal.BuildVRTOptions(srcNodata=nodata_value)
    vrt_path = output_path.replace(".tif", ".vrt")  # Temporary VRT file path
    gdal.BuildVRT(vrt_path, dem_paths, options=vrt_options)

    # Convert the virtual raster to GeoTIFF
    translate_options = gdal.TranslateOptions(noData=nodata_value)
    gdal.Translate(output_path, vrt_path, options=translate_options)

    # Optionally, clean up the temporary VRT file
    os.remove(vrt_path)

def find_required_dem_tile_paths(bounds: tuple, check_exists : bool = True)->list[str]:
    """ generate a list of the required dem paths based on the bounding coords
    """
    lat_range = list(range(int(np.floor(bounds[1])), int(np.ceil(bounds[3]+1))))
    lon_range = list(range(int(np.floor(bounds[0])), int(np.ceil(bounds[2]+1))))
    dem_paths = []

    for lat in lat_range:
        for lon in lon_range:
            lat_dir = "N" if lat >= 0 else "S"
            lon_dir = "E" if lon >= 0 else "W"
            dem_subpath = f"Copernicus_DSM_COG_10_{lat_dir}{int(abs(lat)):02d}_00_{lon_dir}{int(abs(lon)):03d}_00_DEM/Copernicus_DSM_COG_10_{lat_dir}{int(abs(lat)):02d}_00_{lon_dir}{int(abs(lon)):03d}_00_DEM.tif"
            dem_path = os.path.join(COP30_FOLDER_PATH, dem_subpath)
            if check_exists:
                # check the file exists, e.g. over water will not be a file
                if os.path.exists(dem_path):
                    dem_paths.append(dem_path)
            else:
                dem_paths.append(dem_path)
    return list(set(dem_paths))

def check_bounds_cross_antimeridian(bounds : tuple, max_scene_width : int =20) -> bool:
    """Check if the bounds cross the antimeridian. We set a max
    scene width of 10. if the scene is greater than this either side
    of the dateline, we assume it crosses the dateline as the
    alternate scenario is a bounds with a very large width.

    e.g. [-178.031982, -71.618958, 178.577438, -68.765755]

    Args:
        bounds (list or tuple): Bounds in 4326
        max_scene_width (int, optional): maxumum width of bounds in 
        lon degrees. Defaults to 20.

    Returns:
        bool: True if crosses the antimeridian
    """

    min_x = -180 + max_scene_width # -160
    max_x = 180 - max_scene_width # 160
    if (bounds[0] < min_x) and (bounds[0] > -180):
        if bounds[2] > max_x and bounds[2] < 180:
            return True
    return False
        
def split_bounds_at_am_crossing(bounds: tuple, lat_buff : float = 0) -> list[tuple]:
    """split the polygon into bounds on the left and
    right of the antimeridian.

    Args:
        scene_polygon (shapely.polygon): polygon of the scene from asf
        lat_buff (float): A lattitude degrees buffer to add/subtract from
                            max and min lattitudes 

    Returns:
    list(tuple) : a list containing two sets of bounds for the left
                    and right of the antimeridian
    """
    max_negative_x = max([x for x in [bounds[0],bounds[2]] if x < 0])
    min_positive_x = min([x for x in [bounds[0],bounds[2]] if x < 0])
    min_y = min([bounds[1],bounds[3]]) - lat_buff
    max_y = max([bounds[1],bounds[3]]) + lat_buff
    min_y = -90 if min_y < -90 else min_y
    max_y = 90 if max_y > 90 else max_y
    bounds_left = (-180, min_y, max_negative_x, max_y)
    bounds_right = (min_positive_x, min_y, 180, max_y)
    return [tuple(bounds_left), tuple(bounds_right)]