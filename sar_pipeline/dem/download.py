import os
import boto3
from botocore import UNSIGNED
from botocore.config import Config
from pathlib import Path
import rasterio
from rasterio.mask import mask
from shapely.geometry import box
import numpy as np

from sar_pipeline.dem.utils.spatial import BoundingBox

import logging
logger = logging.getLogger(__name__)

EGM_08_URL = 'https://aria-geoid.s3.us-west-2.amazonaws.com/us_nga_egm2008_1_4326__agisoft.tif'

def download_dem_tile_from_aws(
        tile_filename: str, 
        save_folder: Path,
        make_folders=True
        ) -> None:
    """Download a dem tile from AWS and save to specified folder

    Parameters
    ----------
    tile_filename : str
        Copernicus 30m tile filename. e.g. Copernicus_DSM_COG_10_S78_00_E166_00_DEM.tif
    save_folder : Path
        Folder to save the downloaded tif
    make_folders: bool
        Make the save folder if it does not exist
    """
    s3 = boto3.resource('s3', config=Config(signature_version=UNSIGNED,region_name = 'eu-central-1',))
    bucket_name = "copernicus-dem-30m"
    bucket = s3.Bucket(bucket_name)
    s3_path = str(Path(tile_filename).stem / Path(tile_filename))
    save_path = save_folder / Path(tile_filename)
    logger.info(f'Downloading cop30m tile : {s3_path}, save location : {save_path}')

    if make_folders:
        os.makedirs(save_folder, exist_ok=True)

    try:
        bucket.download_file(s3_path, save_path)
    except Exception as e:
        raise(e)

def download_egm_08_geoid_from_aws(
        save_path : Path, 
        bounds: BoundingBox, 
        geoid_url : str =EGM_08_URL):
    """Download the egm_2008 geoid for AWS for the specified bounds. 

    Parameters
    ----------
    save_path : Path
        Where to save tif. e.g. my/geoid/folder/geoid.tif
    bounds : BoundingBox
        Bounding box to download data
    geoid_url : str, optional
        URL, by default EGM_08_URL=
        https://aria-geoid.s3.us-west-2.amazonaws.com/us_nga_egm2008_1_4326__agisoft.tif

    Returns
    -------
    tuple(np.array, dict)
        geoid array and geoid rasterio profile 
    """

    logger.info(f'Downloading egm_08 geoid for bounds {bounds} from {geoid_url}')

    if bounds is None:
        with rasterio.open(geoid_url) as ds:
            geoid_arr = ds.read()
            geoid_profile = ds.profile

    else:
         with rasterio.open(geoid_url) as ds:
            geom = [box(*bounds)]

            # Clip the raster to the bounding box
            geoid_arr, clipped_transform = mask(ds, geom, crop=True, all_touched=True)
            geoid_profile = ds.profile.copy()
            geoid_profile.update({
                "height": geoid_arr.shape[1],  # Rows
                "width": geoid_arr.shape[2],   # Columns
                "transform": clipped_transform
            })

    # Transform nodata to nan
    geoid_arr = geoid_arr.astype('float32')
    geoid_arr[geoid_profile['nodata'] == geoid_arr] = np.nan
    geoid_profile['nodata'] = np.nan

    # Write to file
    with rasterio.open(save_path, "w", **geoid_profile) as dst:
        dst.write(geoid_arr)

    return geoid_arr, geoid_profile