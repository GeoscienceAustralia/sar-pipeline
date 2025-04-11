import asf_search
from datetime import datetime, timedelta
import boto3
import os
import logging

from sar_pipeline.aws.metadata.filetypes import REQUIRED_ASSET_FILETYPES
from sar_pipeline.nci.preparation.scenes import parse_scene_file_dates

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def find_s3_filepaths_from_suffixes(bucket_name, s3_folder, suffixes) -> dict:
    """Search a folder within an s3 bucket for files

    Parameters
    ----------
    bucket_name : str
        S3 bucket
    s3_folder : str
        Folder within the bucket
    suffixes : list
        List of suffixes, or endswiths to search for. For example
        ['.png','.tif'] to find files which end with .png and .tif respectively

    Returns
    -------
    dict
        Dictionary relating the suffix in the list provided to a list of
        files in the bucket and folder. E.g.
        {
            '.png' : ['bucket_name/s3_folder/cat.png','bucket_name/s3_folder/dog.png'],
            '.tif' : ['bucket_name/s3_folder/red.tif','bucket_name/s3_folder/blue.tif']
        }
    """

    # search for credentials in environment and raise warning if not there
    if os.environ.get("AWS_ACCESS_KEY_ID") is None:
        wrn_msg = "AWS_ACCESS_KEY_ID is not set in environment variables. Set if authentication required on bucket"
        logging.warning(wrn_msg)
    if os.environ.get("AWS_SECRET_ACCESS_KEY") is None:
        wrn_msg = "AWS_ACCESS_KEY_ID is not set in environment variables. Set if authentication required on bucket"
        logging.warning(wrn_msg)
    if os.environ.get("AWS_DEFAULT_REGION") is None:
        wrn_msg = "AWS_DEFAULT_REGION is not set in environment variables. Set if authentication required on bucket"
        logging.warning(wrn_msg)

    s3 = boto3.client("s3")

    response = s3.list_objects_v2(Bucket=bucket_name, Prefix=s3_folder)
    if "Contents" not in response:
        # folder does not exist, all required files missing
        return {s: [] for s in suffixes}

    # Extract filenames from S3 keys
    existing_files = [obj["Key"] for obj in response["Contents"]]

    # Check if all required suffixes have at least one match
    suffix_to_s3path = {}
    for s in suffixes:
        suffix_to_s3path[s] = [f for f in existing_files if f.endswith(s)]

    return suffix_to_s3path


def get_burst_ids_for_scene(
    scene: str, burst_prefix: str = "t", lowercase=True
) -> list[str]:
    """Get the list of burst_ids corresponding to a scene

    Parameters
    ----------
    scene : str
        the scene id. e.g. S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD
    burst_prefix : str
        A prefix to add to the burst string. default 't'. For example:
        070_149822_IW3 -> t070_149822_IW3 with burst_prefix = 't'.
    lowercase: bool
        convert the burst to lowercase. default to True to match workflow output.

    Returns
    -------
    list[str]
        List of burst ids. e.g. ['t070_149822_IW3','t070_149822_IW2' ....]
    """

    st, et = parse_scene_file_dates(scene)

    results = asf_search.search(
        platform=[asf_search.PLATFORM.SENTINEL1],
        maxResults=100,
        processingLevel="BURST",
        start=st - timedelta(seconds=1),
        end=et + timedelta(seconds=1),
    )

    burst_ids = [
        f"{burst_prefix}{b.properties['burst']['fullBurstID']}"
        for b in results
        if scene in b.properties["url"]
    ]
    if lowercase:
        burst_ids = [b.lower() for b in burst_ids]

    return burst_ids


def make_static_layer_base_url(
    static_layers_s3_bucket: str,
    static_layers_collection: str,
    static_layers_s3_project_folder: str,
    s3_region: str = "ap-southeast-2",
) -> str:
    """Make the base url to the static layers from the paths provided

    Parameters
    ----------
    static_layers_s3_bucket : str
        Bucket containing static layer
    static_layers_collection : str
        collection static layers belong to
    static_layers_s3_project_folder : str
        project folder within bucket if exists
    s3_region : str, optional
        aws region code, by default "ap-southeast-2"

    Returns
    -------
    str
        The url where burst static layers are kept
    """
    return (
        f"https://{static_layers_s3_bucket}.s3.{s3_region}.amazonaws.com"
        f"/{static_layers_s3_project_folder}/{static_layers_collection}"
    )


def check_static_layers_in_s3(
    scene: str,
    static_layers_s3_bucket: str,
    static_layers_collection: str,
    static_layers_s3_project_folder: str,
    burst_id_list=[],
):
    """Check AWS S3 bucket to ensure static layers exist for the required bursts

    Parameters
    ----------
    scene : str
        the scene id. e.g. S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD
    static_layers_s3_bucket : str
        s3 bucket
    static_layers_collection : str
        collection folder for the static layers
    static_layers_s3_project_folder : str
        project folder for static layers
    burst_id_list : list, optional
        List of specific bursts to see if static layers exist. by default [] and the bursts associated with the scene will be searched for.

    Returns
    -------
    bool
        True if all required static layer files exist.

    Raises
    ------
    FileExistsError
        If any of the required static layer files are missing for a burst.
    """

    if not burst_id_list:
        # only scene provided, need to search and find the related bursts
        logger.info(f"Searching ASF for burst ids associated with scene")
        burst_id_list = get_burst_ids_for_scene(scene)
        logger.info(f"\n{len(burst_id_list)} Bursts found")

    n_bursts = len(burst_id_list)
    raise_missing_file_error = False
    missing_burst_files = {}

    for burst_id in burst_id_list:
        static_layers_s3_folder = (
            f"{static_layers_s3_project_folder}/{static_layers_collection}/{burst_id}"
        )
        filetype_to_s3paths = find_s3_filepaths_from_suffixes(
            static_layers_s3_bucket,
            static_layers_s3_folder,
            suffixes=REQUIRED_ASSET_FILETYPES["RTC_S1_STATIC"],
        )
        # find the filetypes that are missing from the static layer folder
        missing_burst_files[burst_id] = [
            filetype
            for filetype, s3paths in filetype_to_s3paths.items()
            if len(s3paths) == 0
        ]
        if len(missing_burst_files[burst_id]) > 0:
            # we have a burst missing files, flag to raise an error below
            raise_missing_file_error = True

    if not raise_missing_file_error:
        logger.info(
            f"All {n_bursts} of {n_bursts} required static layers exist for bursts in scene : {scene}"
        )
        return True
    else:
        n_missing = len(
            [x for x in missing_burst_files if len(missing_burst_files[x]) > 0]
        )
        missing_info = "\n".join(
            f" Burst ID: {burst_id} -> Missing Filetypes: {', '.join(missing_files)}"
            for burst_id, missing_files in missing_burst_files.items()
            if missing_files  # only include bursts with missing files
        )
        raise FileExistsError(
            f"\nMissing static layers for bursts in scene : {scene}\n"
            f"{n_missing} of {n_bursts} required bursts missing\n"
            f"Missing Bursts and static layer filetypes:\n"
            f"{missing_info}\n"
            f"Example path searched : {static_layers_s3_folder}\n"
            f"Check S3 linked location settings or create static layers using --product RTC_S1_STATIC. See workflow docs for details."
        )
