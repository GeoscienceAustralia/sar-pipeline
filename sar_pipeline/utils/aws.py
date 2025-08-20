import os
import boto3
import logging
from botocore import UNSIGNED
from botocore.config import Config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_aws_environment_credentials() -> list[str]:
    """Checks if the required credentials exist

    Returns: list
        A list of the credentials that are missing
    """
    # search for credentials in environment and raise warning if not there
    MISSING_CREDENTIALS = []
    if os.environ.get("AWS_ACCESS_KEY_ID") is None:
        wrn_msg = "AWS_ACCESS_KEY_ID is not set in environment variables. Set if authentication required on bucket"
        logging.warning(wrn_msg)
        MISSING_CREDENTIALS.append("AWS_ACCESS_KEY_ID")
    if os.environ.get("AWS_SECRET_ACCESS_KEY") is None:
        wrn_msg = "AWS_SECRET_ACCESS_KEY is not set in environment variables. Set if authentication required on bucket"
        logging.warning(wrn_msg)
        MISSING_CREDENTIALS.append("AWS_SECRET_ACCESS_KEY")
    if os.environ.get("AWS_DEFAULT_REGION") is None:
        wrn_msg = "AWS_DEFAULT_REGION is not set in environment variables. Set if authentication required on bucket"
        logging.warning(wrn_msg)
        MISSING_CREDENTIALS.append("AWS_DEFAULT_REGION")
    return MISSING_CREDENTIALS


def find_s3_filepaths_from_suffixes(
    bucket_name: str, s3_folder: str, suffixes: list
) -> dict:
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

    MISSING_CREDENTIALS = check_aws_environment_credentials()
    if MISSING_CREDENTIALS:
        # attempt to connect without authentication
        logger.info(
            f"Attempting to search bucket without complete credentials. Missing credentials : {MISSING_CREDENTIALS}"
        )
        s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    else:
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
