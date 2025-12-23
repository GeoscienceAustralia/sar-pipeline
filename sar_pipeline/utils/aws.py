import os
import boto3
import logging
from botocore import UNSIGNED
from botocore.config import Config
from botocore.exceptions import ClientError
import logging
import mimetypes
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_aws_environment_credentials(verbose=False) -> list[str]:
    """Checks if the required credentials exist

    Returns: list
        A list of the credentials that are missing
    """
    # search for credentials in environment and raise warning if not there
    MISSING_CREDENTIALS = []
    if os.environ.get("AWS_ACCESS_KEY_ID") is None:
        wrn_msg = "AWS_ACCESS_KEY_ID is not set in environment variables. Set if authentication required on bucket"
        if verbose:
            logging.warning(wrn_msg)
        MISSING_CREDENTIALS.append("AWS_ACCESS_KEY_ID")
    if os.environ.get("AWS_SECRET_ACCESS_KEY") is None:
        wrn_msg = "AWS_SECRET_ACCESS_KEY is not set in environment variables. Set if authentication required on bucket"
        if verbose:
            logging.warning(wrn_msg)
        MISSING_CREDENTIALS.append("AWS_SECRET_ACCESS_KEY")
    if os.environ.get("AWS_DEFAULT_REGION") is None:
        wrn_msg = "AWS_DEFAULT_REGION is not set in environment variables. Set if authentication required on bucket"
        if verbose:
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

        check_aws_environment_credentials(verbose=True)

        self.s3 = boto3.client(
            "s3",
        )

    def download_folder(self, bucket_name: str, s3_folder: str | Path, local_dir: Path):
        """
        Download all objects from an S3 folder to a local directory.

        Parameters
        ----------
        bucket_name : str
            Name of the S3 bucket.
        s3_folder : str | Path
            S3 folder (prefix) to download.
        local_dir : Path
            Local folder path to download files into.
            
            Raises
            ------
            ValueError
                If the S3 prefix does not exist or is empty.          
        """
        s3_folder = str(s3_folder).rstrip("/") + "/"
        paginator = self.s3.get_paginator("list_objects_v2")

        # Check prefix exists
        first_page = paginator.paginate(
            Bucket=bucket_name, Prefix=s3_folder
        ).build_full_result()

        if "Contents" not in first_page or len(first_page["Contents"]) == 0:
            raise ValueError(
                f"S3 folder does not exist or is empty: s3://{bucket_name}/{s3_folder}"
            )

        # Download loop
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

    def push_files_in_folder_to_s3(
        self,
        src_folder: str,
        s3_bucket: str,
        s3_prefix: str,
        upload_folder: bool = False,
        exclude_extensions: list[str] = [],
        exclude_files: list[str] = [],
    ):
        """Upload the files in a local folder to an S3 bucket. The subfolder
        structure in the specified folder is maintained in s3.

        Parameters
        ----------
        src_folder : str
            Source folder containing files of interest
        s3_bucket : str
            S3 bucket to push to
        s3_prefix : str
            Prefix within bucket to push to
        upload_folder : bool
            upload the entire folder to the s3_prefix.
            If; src_folder = my/local_folder/ & s3_prefix = s3/s3_folder
            when True, all files uploaded to -> s3/s3_folder/local_folder/...
            when False, all files uploaded to -> s3/s3_folder/...
        exclude_extensions : list[str], optional
            List of file extensions to exclude, by default []
        exclude_files : list[str], optional
            List of files to exclude, by default []
        """

        logging.info(f"Attempting to upload to S3 bucket : {s3_bucket}")

        for root, dirs, files in os.walk(src_folder):
            for file in files:
                if exclude_extensions:
                    filename, file_extension = os.path.splitext(file)
                    if file_extension in exclude_extensions:
                        continue
                if file in exclude_files:
                    continue
                local_path = Path(root) / Path(file)
                relative_path = Path(os.path.relpath(local_path, src_folder))
                if not upload_folder:
                    s3_key = Path(
                        os.path.join(s3_prefix, relative_path).replace("\\", "/")
                    )
                else:
                    folder = Path(src_folder).name
                    s3_key = Path(
                        os.path.join(s3_prefix, folder, relative_path).replace(
                            "\\", "/"
                        )
                    )
                file_mime_type, _ = mimetypes.guess_type(local_path)
                self.s3.upload_file(
                    str(local_path),
                    str(s3_bucket),
                    str(s3_key),
                    ExtraArgs={"ContentType": file_mime_type or "binary/octet-stream"},
                )
                logging.info(f"Uploaded {local_path} to s3://{s3_bucket}/{s3_key}")
