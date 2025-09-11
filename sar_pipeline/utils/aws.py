import os
import boto3
import logging
from botocore import UNSIGNED
from botocore.config import Config
from botocore.exceptions import ClientError
import logging
from pathlib import Path

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


class S3Util:
    def __init__(
        self,
        aws_access_key_id: str,
        aws_secret_access_key: str,
        region_name: str = "ap-southeast-2",
    ):
        """
        Utility class for S3 operations.

        Parameters
        ----------
        aws_access_key_id : str
            AWS access key ID.
        aws_secret_access_key : str
            AWS secret access key.
        region_name : str, optional
            AWS region name, by default "ap-southeast-2".
        """
        self.s3 = boto3.client(
            "s3",
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region_name,
        )

    def download_folder(self, bucket_name: str, s3_folder: str, local_dir: Path):
        """
        Download all objects from an S3 folder to a local directory.

        Parameters
        ----------
        bucket_name : str
            Name of the S3 bucket.
        s3_folder : str
            S3 folder (prefix) to download.
        local_dir : Path
            Local folder path to download files into.
        """
        s3_folder = s3_folder.rstrip("/") + "/"
        paginator = self.s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket_name, Prefix=s3_folder):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                relative_path = Path(key).relative_to(s3_folder)
                local_file_path = local_dir / relative_path
                os.makedirs(local_file_path.parent, exist_ok=True)
                try:
                    self.s3.download_file(bucket_name, key, str(local_file_path))
                    print(f"Downloaded: {key} -> {local_file_path}")
                except ClientError as e:
                    print(f"Failed to download {key}: {e}")
