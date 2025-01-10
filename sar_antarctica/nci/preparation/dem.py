import shapely
from shapely.geometry import box
import numpy as np
import os
import logging
from affine import Affine
import rasterio
from rasterio.crs import CRS
from rasterio.transform import array_bounds

from .geoid import remove_geoid
from ...utils.raster import (
    expand_raster_to_bounds, 
    reproject_raster,
    merge_raster_files,
    bounds_from_profile
)
from ...utils.spatial import (
    adjust_bounds, 
    get_local_utm,
)

# paths
COP30_FOLDER_PATH = '/g/data/v10/eoancillarydata-2/elevation/copernicus_30m_world/'
GEOID_PATH = '/g/data/yp75/projects/ancillary/geoid/us_nga_egm2008_1_4326__agisoft.tif'

def get_cop30_dem_for_bounds(bounds: tuple, save_path: str, ellipsoid_heights: bool = True): 
    
    logging.info(f'Getting cop30m dem that covers bounds: {bounds}')
    # check if scene crosses the AM
    antimeridian_crossing = check_s1_bounds_cross_antimeridian(bounds, max_scene_width=8)
    if antimeridian_crossing:
        logging.warning('DEM crosses the dateline/antimeridian')
        logging.info('Finding best crs for area')
        target_crs = get_target_antimeridian_projection(bounds)
        logging.warning(f'Data will be returned in EPSG:{target_crs} projection') 
        # split the scene into left and right
        logging.info(f'Splitting bounds into left and right side of antimeridian')
        bounds_left, bounds_right = split_s1_bounds_at_am_crossing(bounds, lat_buff=0)
        logging.info(f'Bounds left: {bounds_left}')
        logging.info(f'Bounds right: {bounds_right}')
        # use recursion like a legend to create dems for the left and right side using
        # when passed back into the top function, these will be created and then merged
        left_save_path = '.'.join(save_path.split('.')[0:-1]) + "_left." + save_path.split('.')[-1]
        logging.info(f'Getting tiles for left bounds')
        get_cop30_dem_for_bounds(bounds_left, left_save_path, ellipsoid_heights)
        right_save_path = '.'.join(save_path.split('.')[0:-1]) + "_right." + save_path.split('.')[-1]
        logging.info(f'Getting tiles for right bounds')
        get_cop30_dem_for_bounds(bounds_right, right_save_path, ellipsoid_heights)
        # reproject to 3031 and merge
        logging.info(f'Reprojecting left and right side of antimeridian to EPGS:{target_crs}')
        reproject_raster(left_save_path, left_save_path, target_crs)
        reproject_raster(right_save_path, right_save_path, target_crs)
        logging.info(f'Merging across antimeridian')
        dem_arr, dem_profile = merge_raster_files([left_save_path, right_save_path], output_path=save_path, nodata_value=np.nan)
        #os.remove(left_save_path)
        #os.remove(right_save_path)
        return dem_arr, dem_profile
    else:
        # logging.info(f'Expanding bounds') # TODO this should sit outside of this function
        # bounds = expand_bounds(bounds, buffer=0.1)
        logging.info(f'Getting cop30m dem for bounds: {bounds}')
        logging.info(f'Searching folder for dem tiles covering scene: {COP30_FOLDER_PATH}')
        dem_paths = find_required_dem_tile_paths(bounds)
        logging.info(f'Dem tiles found: {len(dem_paths)}')
        if len(dem_paths) == 0:
            logging.warning('No DEM files found, scene is over water or paths cannot be found')
            logging.info('Creating an empty profile for cop30m DEM')
            dem_profile = make_empty_cop30m_profile(bounds)
            logging.info('Filling dem with zero values based on profile')
            dem_arr, dem_profile = expand_raster_to_bounds(bounds, src_profile=dem_profile, save_path=save_path, fill_value=0)
        else:
            logging.info(f'Merging dem tiles and saving to: {save_path}')
            dem_arr, dem_profile = merge_raster_files(dem_paths, save_path, nodata_value=np.nan)
        logging.info(f'Check the dem covers the required bounds')
        dem_bounds = bounds_from_profile(dem_profile)
        logging.info(f'Dem bounds: {dem_bounds}')
        logging.info(f'Target bounds: {bounds}')
        bounds_filled_by_dem = box(*bounds).within(box(*dem_bounds))
        logging.info(f'Dem covers target: {bounds_filled_by_dem}')
        if not bounds_filled_by_dem:
            fill_value = 0
            logging.info(f'Expanding bounds with fill value: {fill_value}')
            dem_arr, dem_profile = expand_raster_to_bounds(
                bounds, 
                src_profile=dem_profile, 
                src_array=dem_arr, 
                save_path=save_path, 
                fill_value=0)
            dem_bounds = bounds_from_profile(dem_profile)
            logging.info(f'Expanded dem bounds: {dem_bounds}')
        if ellipsoid_heights:
            logging.info(f'Subtracting the geoid from the DEM to return ellipsoid heights')
            logging.info(f'Using geoid file: {GEOID_PATH}')
            dem_arr = remove_geoid(
                dem_arr = dem_arr,
                dem_profile=dem_profile,
                geoid_path = GEOID_PATH,
                dem_area_or_point = 'Point',
                res_buffer = 2,
                save_path=save_path,
            )
        return dem_arr, dem_profile

def expand_bounds(bounds: tuple, buffer: float):
    """
    """
    min_lat = min(bounds[1], bounds[3])
    if min_lat < -50:
        # adjust the bounds at high southern latitudes
        bounds = adjust_bounds(bounds, src_crs=4326, ref_crs=3031)
    if min_lat > -50:
        # adjust the bounds at high norther latitudes
        bounds = adjust_bounds(bounds, src_crs=4326, ref_crs=3995)
    exp_bounds = list(box(*bounds).buffer(buffer).bounds)
    exp_bounds[0] = bounds[0] if exp_bounds[0] < -180 else exp_bounds[0] # keep original
    exp_bounds[2] = bounds[2] if exp_bounds[2] > 180 else exp_bounds[2] # keep original
    return tuple(exp_bounds)

def find_required_dem_tile_paths(bounds: tuple, check_exists : bool = True)->list[str]:
    """ generate a list of the required dem paths based on the bounding coords
    """
    # handle negatives, i.e. if value is -77.6 we want to start at ceiling -77
    # if value is 77.6 we want to start at floor -77
    min_lat = np.floor(bounds[1]) if bounds[1] < 0 else np.ceil(bounds[1])
    max_lat = np.ceil(bounds[3]) if bounds[3] < 0 else np.floor(bounds[3])+1
    min_lon = np.floor(bounds[0]) if bounds[0] < 0 else np.floor(bounds[0])
    max_lon = np.ceil(bounds[2]) if bounds[2] < 0 else np.ceil(bounds[2])
    logging.info(f'lat min: {min_lat}, lat max: {max_lat}')
    logging.info(f'lon min: {min_lon}, lon max: {max_lon}')
    lat_range = list(range(int(min_lat), int(max_lat)))
    lon_range = list(range(int(min_lon), int(max_lon)))
    logging.info(f'lat tile range: {lat_range}')
    logging.info(f'lon tile range: {lon_range}')
    dem_paths = []
    dem_folders = []

    for lat in lat_range:
        for lon in lon_range:
            lat_dir = "N" if lat >= 0 else "S"
            lon_dir = "E" if lon >= 0 else "W"
            dem_foldername = f"Copernicus_DSM_COG_10_{lat_dir}{int(abs(lat)):02d}_00_{lon_dir}{int(abs(lon)):03d}_00_DEM"
            dem_subpath = f"{dem_foldername}/{dem_foldername}.tif"
            dem_path = os.path.join(COP30_FOLDER_PATH, dem_subpath)
            if check_exists:
                # check the file exists, e.g. over water will not be a file
                if os.path.exists(dem_path):
                    dem_paths.append(dem_path)
                    dem_folders.append(dem_foldername)
            else:
                dem_paths.append(dem_path)
    for p in set(dem_folders):
        logging.info(p)
    return list(set(dem_paths))

def check_s1_bounds_cross_antimeridian(bounds : tuple, max_scene_width : int =20) -> bool:
    """Check if the s1 scene bounds cross the antimeridian. The bounds are valid, just very
    large so we set a max scene width of 10. if the scene is greater than this either side
    of the dateline, we assume it crosses the dateline. Alternate scenario is a bounds 
    with a very large width (close to earths width).

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
        
def split_s1_bounds_at_am_crossing(bounds: tuple, lat_buff : float = 0) -> list[tuple]:
    """split the s1 bounds into bounds on the left and
    right of the antimeridian.

    Args:
        scene_polygon (shapely.polygon): polygon of the scene from asf
        lat_buff (float): A lattitude degrees buffer to add/subtract from
                            max and min lattitudes 

    Returns:
    list(tuple) : a list containing two sets of bounds for the left
                    and right of the antimeridian
    """
    max_negative_x = min([x for x in [bounds[0],bounds[2]] if x < 0])
    min_positive_x = min([x for x in [bounds[0],bounds[2]] if x > 0])
    min_y = min([bounds[1],bounds[3]]) - lat_buff
    max_y = max([bounds[1],bounds[3]]) + lat_buff
    min_y = -90 if min_y < -90 else min_y
    max_y = 90 if max_y > 90 else max_y
    bounds_left = (-180, min_y, max_negative_x, max_y)
    bounds_right = (min_positive_x, min_y, 180, max_y)
    return [tuple(bounds_left), tuple(bounds_right)]

def get_target_antimeridian_projection(bounds):
    """depending where were are on the earth, the desired
    crs at the antimeridian will change. e.g. polar stereo
    is desired at high and low lats, local utm zone elsewhere
    (e.g. at the equator)"""
    min_lat = min(bounds[1], bounds[3])
    target_crs =  3031 if min_lat < -50 else 3995 if min_lat > 50 else get_local_utm(bounds, antimeridian=True)
    return target_crs

def make_empty_cop30m_profile(bounds):

    # the pixel spacing changes based on lattitude
    # https://copernicus-dem-30m.s3.amazonaws.com/readme.html
    lon_res = -0.0002777777777777778
    mean_lat = abs((bounds[1] + bounds[3])/2)
    if mean_lat < 50:
        lat_res = lon_res
    elif mean_lat < 60:
        lat_res = lon_res*1.5
    elif mean_lat < 70:
        lat_res = lon_res*2
    elif mean_lat < 80:
        lat_res = lon_res*3
    elif mean_lat < 85:
        lat_res = lon_res*5
    elif mean_lat < 90:
        lat_res = lon_res*10
    else:
        raise ValueError('cannot resolve cop30m lattitude')

    min_x, min_y, max_x, max_y = bounds
    transform = Affine.translation(min_x, max_y) * Affine.scale(lon_res, -lat_res)

    return {
        'driver': 'GTiff', 
        'dtype': 'float32', 
        'nodata': np.nan, 
        'height': int((bounds[3] - bounds[1]) / lat_res), 
        'width': int((bounds[2] - bounds[0]) / lon_res), 
        'count': 1, 
        'crs': CRS.from_epsg(4326), 
        'transform': transform, 
        'blockysize': 1, 
        'tiled': False, 
        'interleave': 'band'
       }