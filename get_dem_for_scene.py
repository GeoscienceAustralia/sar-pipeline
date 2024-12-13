from dem_stitcher import stitch_dem
from pathlib import Path
import rasterio as rio
from shapely.geometry import Polygon
import tomli
from pyroSAR import identify
from utils import transform_scene_extent

REPO_DIR = Path(__file__).resolve().parent

with open(REPO_DIR.joinpath("config.toml"), "rb") as f:
    config_dict = tomli.load(f)

# Set up paths
data_dir = Path(config_dict["paths"]["data"])
dem_dir = data_dir.joinpath("dem")
scene_path = Path(config_dict["scene"])

# If scene exists, extract metadata
if scene_path.exists():
    scene_id_pyrosar = identify(scene_path)
    scene_name = scene_path.stem

# Extract scene bounds
scene_polygon = Polygon(scene_id_pyrosar.meta["coordinates"])
scene_bounds = scene_polygon.bounds

 # if we are at high latitudes we need to correct the bounds due to the skewed box shape
if (scene_bounds[1] < -50) or (scene_bounds[3] < -50):
    # Southern Hemisphere
    print(f'Adjusting scene bounds due to warping at high latitude (Southern Hemisphere)')
    scene_polygon = transform_scene_extent(scene_polygon, 4326, 3031)
    scene_bounds = scene_polygon.bounds 
    #logging.info(f'Adjusted scene bounds : {scene_bounds}')
if (scene_bounds[1] > 50) or (scene_bounds[3] > 50):
    # Northern Hemisphere
    print(f'Adjusting scene bounds due to warping at high latitude (Northern Hemisphere)')
    scene_polygon = transform_scene_extent(scene_bounds, 4326, 3995)
    scene_bounds = scene_polygon.bounds 
    #logging.info(f'Adjusted scene bounds : {scene_bounds}')

# Buffer scene boundaries
buffer = 0.1
scene_bounds_buffered = scene_polygon.buffer(buffer).bounds #buffered

dem_filename = scene_name + '_dem.tif'
dem_file = dem_dir.joinpath(dem_filename)

dem_data, dem_meta = stitch_dem(
    scene_bounds_buffered,
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