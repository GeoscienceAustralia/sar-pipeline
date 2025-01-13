import shapely
from shapely.geometry import box
import numpy as np
import os
from pathlib import Path
import logging
from affine import Affine
import rasterio
from rasterio.crs import CRS
from rasterio.transform import array_bounds
import geopandas as gpd

from .geoid import remove_geoid
from ...utils.raster import (
    expand_raster_to_bounds, 
    reproject_raster,
    merge_raster_files,
    bounds_from_profile,
    read_vrt_in_bounds
)
from ...utils.spatial import (
    adjust_bounds, 
    get_local_utm,
)

COP30_FOLDER_PATH = Path('/g/data/v10/eoancillarydata-2/elevation/copernicus_30m_world/')
COP30_VRT_PATH = Path('/g/data/yp75/projects/ancillary/dem/copdem_south.vrt')
GEOID_PATH = Path('/g/data/yp75/projects/ancillary/geoid/us_nga_egm2008_1_4326__agisoft.tif')
GPKG_PATH = Path('/g/data/yp75/projects/ancillary/dem/copdem_tindex.gpkg')

def get_cop30_dem_for_bounds(
        bounds: tuple, 
        save_path: Path, 
        ellipsoid_heights: bool = True
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

    Returns
    -------
    tuple [np.darray, dict]
        dem array and dem rasterio profile
    """
    
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
        # use recursion to create dems for the left and right side of AM
        # when passed back into the top function, this section will be skipped, creating
        # A valid dem for each side which we can then merge at the desired CRS
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
        dem_arr, dem_profile = merge_raster_files([left_save_path, right_save_path], output_path=save_path)
        os.remove(left_save_path)
        os.remove(right_save_path)
        return dem_arr, dem_profile
    else:
        # logging.info(f'Expanding bounds') # TODO this should sit outside of this function
        # bounds = expand_bounds(bounds, buffer=0.1)
        logging.info(f'Getting cop30m dem for bounds: {bounds}')
        logging.info(f'Reading tiles from the tile vrt: {COP30_VRT_PATH}')
        dem_arr, dem_profile = read_vrt_in_bounds(COP30_VRT_PATH, save_path, bounds=bounds,buffer_pixels=1)
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
                buffer_pixels = 2,
                save_path=save_path,
            )
        return dem_arr, dem_profile

def expand_bounds(bounds: tuple, buffer: float) -> tuple:
    """Expand the bounds for high lattitudes, and add a buffer. The
    provided bounds sometimes do not contain the full scene due to
    warping at high latitudes.

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
    if min_lat > -50:
        # adjust the bounds at high norther latitudes
        bounds = adjust_bounds(bounds, src_crs=4326, ref_crs=3995)
    exp_bounds = list(box(*bounds).buffer(buffer).bounds)
    exp_bounds[0] = bounds[0] if exp_bounds[0] < -180 else exp_bounds[0] # keep original
    exp_bounds[2] = bounds[2] if exp_bounds[2] > 180 else exp_bounds[2] # keep original
    return tuple(exp_bounds)

def find_required_dem_paths_from_geopackage(
        bounds: tuple, 
        GPKG_PATH = GPKG_PATH,
) -> list[str]: 
    
    gdf = gpd.read_file(GPKG_PATH)
    bounding_box = box(*bounds)
    
    if gdf.crs is not None:
        # ensure same crs
        bounding_box = gpd.GeoSeries([bounding_box], crs="EPSG:4326").to_crs(gdf.crs).iloc[0]

    # Find rows that intersect with the bounding box
    intersecting_tiles = gdf[gdf.intersects(bounding_box)]
    if len(intersecting_tiles) > 0:
        return intersecting_tiles.location.tolist()
    else:
        return []


def find_required_dem_tile_paths_by_filename(
        bounds: tuple, 
        check_exists : bool = True, 
        COP30_FOLDER_PATH: Path = COP30_FOLDER_PATH
        )->list[str]:
    """generate a list of the required dem paths based on the bounding coords. The 
    function searches the specified folder.

    Parameters
    ----------
    bounds : tuple
        the set of bounds (min_lon, min_lat, max_lon, max_lat)
    check_exists : bool, optional
        Check if the file exists, by default True
    COP30_FOLDER_PATH : str, optional
        path to the tile folders, by default COP30_FOLDER_PATH

    Returns
    -------
    list[str]
        list of paths for required dem tiles in bounds
    """
    # logic to find the correct files based on data being stored in each tile folder
    min_lat = np.floor(bounds[1]) if bounds[1] < 0 else np.ceil(bounds[1])
    max_lat = np.ceil(bounds[3]) if bounds[3] < 0 else np.floor(bounds[3])+1
    min_lon = np.floor(bounds[0]) if bounds[0] < 0 else np.floor(bounds[0])
    max_lon = np.ceil(bounds[2]) if bounds[2] < 0 else np.ceil(bounds[2])
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

    min_x = -180 + max_scene_width # -160
    max_x = 180 - max_scene_width # 160
    if (bounds[0] < min_x) and (bounds[0] > -180):
        if bounds[2] > max_x and bounds[2] < 180:
            return True
    return False
        
def split_s1_bounds_at_am_crossing(bounds: tuple, lat_buff : float = 0) -> list[tuple]:
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
    max_negative_x = min([x for x in [bounds[0],bounds[2]] if x < 0])
    min_positive_x = min([x for x in [bounds[0],bounds[2]] if x > 0])
    min_y = min([bounds[1],bounds[3]]) - lat_buff
    max_y = max([bounds[1],bounds[3]]) + lat_buff
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
    target_crs =  3031 if min_lat < -50 else 3995 if min_lat > 50 else get_local_utm(bounds, antimeridian=True)
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
        'height': abs(int((bounds[3] - bounds[1]) / lat_res)), 
        'width': abs(int((bounds[2] - bounds[0]) / lon_res)), 
        'count': 1, 
        'crs': CRS.from_epsg(4326), 
        'transform': transform, 
        'blockysize': 1, 
        'tiled': False, 
        'interleave': 'band'
       }