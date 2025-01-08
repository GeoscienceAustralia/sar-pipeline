import shapely
from shapely.geometry import box
import numpy as np
import os
import logging
from affine import Affine
import rasterio
from rasterio.crs import CRS

from ...utils.raster import (
    expand_raster_to_bounds, 
    reproject_raster,
    merge_raster_files
)
from .geoid import remove_geoid

COP30_FOLDER_PATH = '/g/data/v10/eoancillarydata-2/elevation/copernicus_30m_world/'
GEOID_PATH = '/g/data/yp75/projects/ancillary/geoid/us_nga_egm2008_1_4326__agisoft.tif'

def get_cop30_dem_for_bounds(bounds: tuple, save_path: str, ellipsoid_heights: bool = True): 
    
    logging.info(f'Getting cop30m dem for bounds: {bounds}')
    # check if scene crosses the AM
    antimeridian_crossing = check_s1_bounds_cross_antimeridian(bounds, max_scene_width=8)
    if antimeridian_crossing:
        logging.warning('Scene crosses the dateline/antimeridian')
        # TODO assumes only antarctic data (3031). Elsewhere the local UTM zone should be used
        logging.warning('Data will be returned in 3031 projection') 
        # split the scene into left and right
        logging.info(f'Splitting bounds into left and right side of antimeridian')
        bounds_left, bounds_right = split_s1_bounds_at_am_crossing(bounds, lat_buff=0)
        logging.info(f'Bounds left: {bounds_left}')
        logging.info(f'Bounds left: {bounds_right}')
        # use recursion like a legend to create dems for the left and right side
        left_save_path = '.'.join(save_path.split('.')[0:-1]) + "_left." + save_path.split('.')[-1]
        logging.info(f'Getting tiles for left bounds')
        get_cop30_dem_for_bounds(bounds_left, left_save_path, ellipsoid_heights)
        right_save_path = '.'.join(save_path.split('.')[0:-1]) + "_right." + save_path.split('.')[-1]
        logging.info(f'Getting tiles for right bounds')
        get_cop30_dem_for_bounds(bounds_right, right_save_path, ellipsoid_heights)
        # reproject to 3031 and merge
        logging.info(f'Reprojecting left and right side of antimeridian to polar stereographic EPGS:3031')
        reproject_raster(left_save_path, left_save_path, 3031)
        reproject_raster(right_save_path, right_save_path, 3031)
        logging.info(f'Merging across antimeridian')
        merge_raster_files([left_save_path, right_save_path], output_path=save_path, nodata_value=np.nan)
        os.remove(left_save_path)
        os.remove(right_save_path)
        with rasterio.open(save_path) as dem:
                dem_profile = dem.profile
                dem_arr = dem.read()
        return dem_arr, dem_profile
    else:
        # get a list of the required dem paths
        logging.info(f'Searching folder for dem tiles covering scene: {COP30_FOLDER_PATH}')
        dem_paths = find_required_dem_tile_paths(bounds)
        logging.info(f'Dem tiles found: {len(dem_paths)}')
        if len(dem_paths) == 0:
            logging.warning('No DEM files found, scene is over water or paths cannot be found')
            logging.info('Creating an empty profile for cop30m DEM')
            dem_profile = make_empty_cop30m_profile(bounds)
            logging.info('Filling dem with zero values based on profile')
            expand_raster_to_bounds(bounds, src_profile=dem_profile, save_path=save_path, fill_value=0)
        else:
            logging.info(f'Merging dem tiles and saving to: {save_path}')
            merge_raster_files(dem_paths, save_path, nodata_value=np.nan)
        logging.info(f'Check the dem covers the required bounds')
        with rasterio.open(save_path) as dem:
            dem_bounds = tuple(dem.bounds)
        logging.info(f'Dem bounds: {dem_bounds}')
        logging.info(f'Target bounds: {bounds}')
        bounds_filled_by_dem = box(*dem_bounds).contains(box(*bounds)) # TODO write test
        logging.info(f'Dem covers target: {bounds_filled_by_dem}')
        if not bounds_filled_by_dem:
            fill_value = 0
            logging.info(f'Expanding bounds with fill value: {fill_value}')
            expand_raster_to_bounds(bounds, src_path=save_path, save_path=save_path, fill_value=0)
            with rasterio.open(save_path) as dem:
                dem_bounds = tuple(dem.bounds)
            logging.info(f'Expanded dem bounds: {dem_bounds}')
        with rasterio.open(save_path) as dem:
                dem_profile = dem.profile
                dem_arr = dem.read()
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
            dem_foldername = f"Copernicus_DSM_COG_10_{lat_dir}{int(abs(lat)):02d}_00_{lon_dir}{int(abs(lon)):03d}_00_DEM"
            dem_subpath = f"{dem_foldername}/{dem_foldername}.tif"
            dem_path = os.path.join(COP30_FOLDER_PATH, dem_subpath)
            if check_exists:
                # check the file exists, e.g. over water will not be a file
                if os.path.exists(dem_path):
                    dem_paths.append(dem_path)
            else:
                dem_paths.append(dem_path)
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