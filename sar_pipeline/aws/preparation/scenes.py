import asf_search
from asf_search import ASFSearchResults
import os
from pathlib import Path
import logging
import zipfile
from cdsetool.query import query_features, FeatureQuery
from cdsetool.credentials import Credentials
from cdsetool.download import download_features
from cdsetool.monitor import StatusMonitor

from sar_pipeline.utils.general import log_timing
from sar_pipeline.utils.sentinel1 import extract_metadata_from_s1_id

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MissingCredentialsError(Exception):
    """Exception raised when no credentials are supplied."""

    pass


def query_scene_from_asf(scene: str) -> ASFSearchResults:

    logger.info(f"Searching ASF for scene")

    # Extract metadata from scene ID
    scene_metadata = extract_metadata_from_s1_id(scene)

    # Determine the asf_search product type to search: https://github.com/asfadmin/Discovery-asf_search/blob/master/asf_search/constants/PRODUCT_TYPE.py
    # GRD processingly level query cannot currently be determined from product type alone, so list all GRD and assume it is one of these five.
    # The list is sufficient to distinguish metadata files from data files
    if scene_metadata["product_type"] == "GRD":
        processing_level_query = ["GRD_HD", "GRD_MD", "GRD_MS", "GRD_HS", "GRD_FD"]
    elif scene_metadata["product_type"] in ["SLC", "OCN", "RAW"]:
        processing_level_query = scene_metadata["product_type"]
    else:
        raise ValueError(
            f"Product type {scene_metadata["product_type"]} not recognised. Should be one of GRD, SLC, OCN, or RAW"
        )

    # Run the search
    search_results = asf_search.granule_search(
        [scene], asf_search.ASFSearchOptions(processingLevel=processing_level_query)
    )

    return search_results


@log_timing
def download_scene_from_asf(
    scene: str,
    download_folder: Path,
    make_folder: bool = True,
    unzip: bool = True,
    asf_login: str | None = None,
    asf_pass: str | None = None,
):

    # Search for scene on ASF
    search_results = query_scene_from_asf(scene)

    # ensure only one slc found
    if len(search_results) != 1:
        raise ValueError(
            f"Expected 1 SLC, found {len(search_results)} for scene : {scene}"
        )
    asf_scene_metadata = search_results[0]
    scene_name = asf_scene_metadata.properties["sceneName"]

    # Authenticate. If credentials not supplied search the environment variables
    if asf_login is None and asf_pass is None:
        asf_login = os.environ["EARTHDATA_LOGIN"]
        asf_pass = os.environ["EARTHDATA_PASSWORD"]
        if not asf_login or asf_pass:
            err_string = (
                "No credentials supplied. Please provide a asf_login and asf_pass "
                "or set the EARTHDATA_LOGIN and EARTHDATA_PASSWORD environment variables"
            )
            MissingCredentialsError(err_string)

    session = asf_search.ASFSession()
    session.auth_with_creds(asf_login, asf_pass)

    if make_folder:
        os.makedirs(download_folder, exist_ok=True)

    logger.info(f"Downloading : {scene_name}")
    scene_zip_path = Path(download_folder) / f"{scene_name}.zip"
    scene_safe_path = scene_zip_path.with_suffix(".SAFE")

    if scene_safe_path.exists() and unzip:
        logger.info(f"Skipping download, unzipped scene exists at : {scene_safe_path}")
    elif scene_zip_path.exists():
        logger.info(f"Skipping download, zipped scene exists at : {scene_zip_path}")
    else:
        asf_scene_metadata.download(path=download_folder, session=session)

    if unzip and not scene_safe_path.exists():
        logger.info(f"unzipping scene to {scene_safe_path}")
        with zipfile.ZipFile(scene_zip_path, "r") as zip_ref:
            zip_ref.extractall(download_folder)
        return scene_safe_path, asf_scene_metadata
    elif scene_safe_path.exists() and unzip:
        return scene_safe_path, asf_scene_metadata
    else:
        return scene_zip_path, asf_scene_metadata


def query_scene_from_cdse(scene: str) -> FeatureQuery:

    logger.info(f"Searching CDSE for scene")

    features = query_features(
        "Sentinel1",
        {
            "productIdentifier": scene,
        },
    )

    return features


@log_timing
def download_scene_from_cdse(
    scene: str,
    download_folder: Path,
    make_folder: bool = True,
    unzip: bool = True,
    cdse_login: str | None = None,
    cdse_pass: str | None = None,
):

    # Authenticate. If credentials not supplied search the envrionment variables
    if cdse_login is None and cdse_pass is None:
        cdse_login = os.environ["CDSE_LOGIN"]
        cdse_pass = os.environ["CDSE_PASSWORD"]
        if not cdse_login or cdse_pass:
            err_string = (
                "No credentials supplied. Please provide a cdse_login and cdse_pass "
                "or set the CDSE_LOGIN and CDSE_PASSWORD environment variables"
            )
            MissingCredentialsError(err_string)

    if make_folder:
        os.makedirs(download_folder, exist_ok=True)

    # search for scene on CDSE
    features = query_scene_from_cdse(scene)

    if len(features) != 1:
        raise ValueError(
            f"Expected 1 scene, found {len(features)} for scene id : {scene}"
        )

    scene_zip_path = Path(download_folder) / f"{scene}.SAFE.zip"
    scene_safe_path = scene_zip_path.with_suffix("")

    # download zip if safe file doesn't exist or zip doesn't exist
    if scene_safe_path.exists() and unzip:
        logger.info(f"Skipping download, unzipped scene exists at : {scene_safe_path}")
    elif scene_zip_path.exists():
        logger.info(f"Skipping download, zipped scene exists at : {scene_zip_path}")
    else:
        logger.info(f"Downloading : {scene}.zip")
        list(
            download_features(
                features,
                download_folder,
                {
                    "concurrency": 1,
                    "monitor": StatusMonitor(),
                    "credentials": Credentials(cdse_login, cdse_pass),
                },
            )
        )

    if unzip and not os.path.exists(scene_safe_path):
        logger.info(f"unzipping scene to {scene_safe_path}")
        with zipfile.ZipFile(scene_zip_path, "r") as zip_ref:
            zip_ref.extractall(download_folder)
        return scene_safe_path, features[0]
    elif scene_safe_path.exists() and unzip:
        return scene_safe_path, features[0]
    else:
        return scene_zip_path, features[0]
