from dem_stitcher import stitch_dem
from pathlib import Path
import logging
import sys
import rasterio as rio
from shapely.geometry import Polygon
import pyproj
import numpy as np

# Set up logging
# logging.basicConfig(
#     format="%(asctime)s | %(levelname)s : %(message)s",
#     level=logging.INFO,
#     stream=sys.stdout,
# )
# log = logging.getLogger("demstitcher")
# log.setLevel(logging.INFO)

# Set up paths
REPO_DIR = Path(__file__).resolve().parent
PROJ_DIR = REPO_DIR.parent
DATA_DIR = PROJ_DIR.joinpath("data")
CRED_DIR = REPO_DIR.joinpath("credentials")
SCENE_DIR = DATA_DIR.joinpath("scenes")
RESULTS_DIR = DATA_DIR.joinpath("results")
DEM_DIR = DATA_DIR.joinpath("dem")
TEMP_DIR = SCENE_DIR.joinpath("tempdir")
LOG_DIR = SCENE_DIR.joinpath("logs")
ORBIT_DIR = DATA_DIR.joinpath("orbits")

#directories_list = [val for key,val in locals().items() if "DIR" in key]

# Set up info
SCENE_ID = "S1A_EW_GRDM_1SDH_20220117T122010_20220117T122115_041500_04EF6B_6437"
SCENE_SAFE = SCENE_DIR.joinpath(f"{SCENE_ID}.SAFE")
SCENE_TIF = SCENE_SAFE.joinpath("measurement/s1a-ew-grd-hh-20220117t122010-20220117t122115-041500-04ef6b-001.tiff")

# Get scene boundary
# needs to come from the manifest file but will do this later
min_y = -68.882225
max_y = -63.575317
min_x = 108.117691
max_x = 121.132294

scene_bounds = [min_x, min_y, max_x, max_y]

def transform_polygon(src_crs, dst_crs, geometry, always_xy=True):
    src_crs = pyproj.CRS(f"EPSG:{src_crs}")
    dst_crs = pyproj.CRS(f"EPSG:{dst_crs}") 
    transformer = pyproj.Transformer.from_crs(src_crs, dst_crs, always_xy=always_xy)
     # Transform the polygon's coordinates
    transformed_exterior = [
        transformer.transform(x, y) for x, y in geometry.exterior.coords
    ]
    # Create a new Shapely polygon with the transformed coordinates
    transformed_polygon = Polygon(transformed_exterior)
    return transformed_polygon

def adjust_scene_poly_at_extreme_lat(bbox, src_crs, ref_crs, delta=0.1):
    """
    Adjust the bounding box around a scene in src_crs (4326) due to warping at high
    Latitudes. For example, the min and max boudning values for an antarctic scene in
    4326 may not actually be the true min and max due to distortions at high latitudes. 

    Parameters:
    - bbox: Tuple of four coordinates (x_min, y_min, x_max, y_max).
    - src_crs: Source EPSG. e.g. 4326
    - ref_crs: reference crs to create the true bbox. i.e. 3031 in southern 
                hemisphere and 3995 in northern (polar stereographic)
    - delta: distance between generation points along the bounding box sides in
            src_crs. e.g. 0.1 degrees in lat/lon 

    Returns:
    - A polygon bounding box expanded to the true min max
    """
    x_min, y_min, x_max, y_max = bbox
    # Generate points along the top side
    top_side = [(x, y_max) for x in list(np.arange(x_min, x_max, delta)) + [x_max]]    
    # Generate points along the right side
    right_side = [(x_max, y) for y in list(np.arange(y_max - delta, y_min-delta, -delta)) + [y_min]]
    # Generate points along the bottom side
    bottom_side = [(x, y_min) for x in list(np.arange(x_max - delta, x_min-delta, -delta)) + [x_min]]
    list(np.arange(y_min + delta, y_max, delta)) + [y_max]
    # Generate points along the left side
    left_side = [(x_min, y) for y in list(np.arange(y_min + delta, y_max, delta)) + [y_max]]
    # Combine all sides' points
    all_points = top_side + right_side + bottom_side + left_side
    # convert to a polygon 
    polygon = Polygon(all_points)
    # convert polygon to desired crs and get bounds in those coordinates
    trans_bounds = transform_polygon(src_crs, ref_crs, polygon).bounds
    trans_poly = Polygon(
        [(trans_bounds[0], trans_bounds[1]), 
         (trans_bounds[2], trans_bounds[1]), 
         (trans_bounds[2], trans_bounds[3]), 
         (trans_bounds[0], trans_bounds[3])]
        )
    corrected_poly = transform_polygon(ref_crs, src_crs, trans_poly)
    return corrected_poly

print(scene_bounds)

 # if we are at high latitudes we need to correct the bounds due to the skewed box shape
if (scene_bounds[1] < -50) or (scene_bounds[3] < -50):
    # Southern Hemisphere
    print(f'Adjusting scene bounds due to warping at high latitude (Southern Hemisphere)')
    scene_poly = adjust_scene_poly_at_extreme_lat(scene_bounds, 4326, 3031)
    scene_bounds = scene_poly.bounds 
    #logging.info(f'Adjusted scene bounds : {scene_bounds}')
if (scene_bounds[1] > 50) or (scene_bounds[3] > 50):
    # Northern Hemisphere
    print(f'Adjusting scene bounds due to warping at high latitude (Northern Hemisphere)')
    scene_poly = adjust_scene_poly_at_extreme_lat(scene_bounds, 4326, 3995)
    scene_bounds = scene_poly.bounds 
    #logging.info(f'Adjusted scene bounds : {scene_bounds}')

print(scene_bounds)
print("done")

buffer = 0.1
scene_bounds_buf = scene_poly.buffer(buffer).bounds #buffered

# if otf_cfg['dem_path'] is not None:
#     # set the dem to be the one specified if supplied
#     logging.info(f'using DEM path specified : {otf_cfg["dem_path"]}')
#     if not os.path.exists(otf_cfg['dem_path']):
#         raise FileExistsError(f'{otf_cfg["dem_path"]} c')
#     else:
#         DEM_PATH = otf_cfg['dem_path']
#         dem_filename = os.path.basename(DEM_PATH)
#         otf_cfg['dem_folder'] = os.path.dirname(DEM_PATH) # set the dem folder
#         otf_cfg['overwrite_dem'] = False # do not overwrite dem
# else:
# make folders and set filenames
dem_filename = SCENE_ID + '_dem.tif'
dem_file = DEM_DIR.joinpath(dem_filename)

dem_data, dem_meta = stitch_dem(
    scene_bounds_buf,
    dem_name='glo_30',
    dst_ellipsoidal_height=True,
    dst_area_or_point='Point',
    merge_nodata_value=0,
    fill_to_bounds=True,
)

print(f'saving dem to {dem_file}')
with rio.open(dem_file, 'w', **dem_meta) as ds:
    ds.write(dem_data, 1)
    ds.update_tags(AREA_OR_POINT='Point')
del dem_data

# if (otf_cfg['overwrite_dem']) or (not os.path.exists(DEM_PATH)) or (otf_cfg['dem_path'] is None):
#     logging.info(f'Downloding DEM for  bounds : {scene_bounds_buf}')
#     logging.info(f'type of DEM being downloaded : {otf_cfg["dem_type"]}')
#     # get the DEM and geometry information
#     dem_data, dem_meta = stitch_dem(scene_bounds_buf,
#                     dem_name=otf_cfg['dem_type'],
#                     dst_ellipsoidal_height=True,
#                     dst_area_or_point='Point',
#                     merge_nodata_value=0,
#                     fill_to_bounds=True,
#                     )
    
# # save with rasterio
#     logging.info(f'saving dem to {DEM_PATH}')
#     with rasterio.open(DEM_PATH, 'w', **dem_meta) as ds:
#         ds.write(dem_data, 1)
#         ds.update_tags(AREA_OR_POINT='Point')
#     del dem_data
# else:
#     logging.info(f'Using existing DEM : {DEM_PATH}')