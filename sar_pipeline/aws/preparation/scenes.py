import asf_search
import os
from pathlib import Path
import logging
import zipfile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MissingCredentialsError(Exception):
    """Exception raised when no credentials are supplied."""
    pass

def download_slc_from_asf(
        scene : str, 
        download_folder : Path, 
        make_folder : bool = True,
        unzip : bool = True, 
        asf_login : str | None = None, 
        asf_pass : str | None = None
    ):

    search_results = asf_search.granule_search(
        [scene], 
        asf_search.ASFSearchOptions(processingLevel='SLC')
    )

    # ansure only one slc found
    assert len(search_results) == 1, f'Expected 1 SLC, found {len(search_results)} for scene : {scene}'
    asf_scene_metadata = search_results[0] 
    scene_name = asf_scene_metadata.properties['sceneName']

    # Authenticate. If credentials not supplied search the envrionment variables
    if asf_login is None and asf_pass is None:
        asf_login = os.environ['EARTHDATA_LOGIN']
        asf_pass = os.environ['EARTHDATA_PASSWORD']
        if not asf_login or asf_pass:
            err_string = "No credentials supplied. Please provide a asf_login and asf_pass " \
            "or set the EARTHDATA_LOGIN and EARTHDATA_PASSWORD environment variables" 
            MissingCredentialsError(err_string) 

    session = asf_search.ASFSession()
    session.auth_with_creds(asf_login,asf_pass)

    if make_folder:
        os.makedirs(download_folder, exist_ok=True)

    logger.info(f'Downloading : {scene_name}')
    asf_scene_metadata.download(path=download_folder, session=session)
    scene_zip_path = os.path.join(download_folder, f'{scene_name}.zip')

    scene_safe_path = scene_zip_path.replace(".zip",".SAFE")
    if unzip and not os.path.exists(scene_safe_path): 
        logger.info(f'unzipping scene to {scene_safe_path}')     
        with zipfile.ZipFile(scene_zip_path, 'r') as zip_ref:
            zip_ref.extractall(download_folder)
        return scene_safe_path, asf_scene_metadata
    else:
        return scene_zip_path, asf_scene_metadata
    

    
