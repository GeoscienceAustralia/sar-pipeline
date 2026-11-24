from datetime import datetime, timezone
import json
import logging
import mimetypes
import os
from pathlib import Path

import boto3
from botocore import UNSIGNED
from botocore.config import Config
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CURRENT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = CURRENT_DIR.parents[1]

DOTENV_PATH = PROJECT_ROOT / ".env"

REQUIRED_ENV_VARIABLES = [
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
]

# An upload claim older than this is assumed to belong to a crashed run and
# may be taken over by another run.
UPLOAD_CLAIM_STALE_AFTER_SECONDS = 2 * 60 * 60

# Error codes returned by S3 when a conditional write loses
_CLAIM_CONFLICT_CODES = ("PreconditionFailed", "ConditionalRequestConflict")
_NOT_FOUND_CODES = ("404", "NoSuchKey", "NotFound")


def _client_error_code(e: ClientError) -> str:
    return str(e.response.get("Error", {}).get("Code", ""))


def make_upload_claim_key(s3_project_folder: str | Path, s3_product_folder: str) -> str:
    """Make the s3 key of the upload claim for a product folder. Claims are
    kept outside the product folder, under
    {s3_project_folder}/monitoring/upload_claims/, mirroring the rest of the
    product prefix.

    Parameters
    ----------
    s3_project_folder : str | Path
        The project folder within the bucket. e.g. baseline
    s3_product_folder : str
        The product folder (prefix) within the bucket. e.g.
        baseline/ga_s1_nrb_iw_vv_vh_1/t070_149815_iw3/2022/01/01/20220101T124745

    Returns
    -------
    str
        e.g. baseline/monitoring/upload_claims/ga_s1_nrb_iw_vv_vh_1/t070_149815_iw3/2022/01/01/20220101T124745.json
    """
    project = str(s3_project_folder).strip("/")
    product = str(s3_product_folder).strip("/")
    if product.startswith(project + "/"):
        product = product[len(project) + 1 :]
    return f"{project}/monitoring/upload_claims/{product}.json"


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
    bucket_name: str,
    s3_folder: str,
    suffixes: list,
    warn_credentials=True,
) -> dict:
    """Search a folder within an s3 bucket for files

    Parameters
    ----------
    bucket_name : str
        S3 bucket
    s3_folder : str
        Folder within the bucket
    suffixes : list
        List of suffixes, or ends with to search for. For example
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
        if warn_credentials:
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
    def __init__(self, unsigned=False):
        """
        Utility class for S3 operations.

        Parameters
        ----------
        unsigned : bool
            Don't use credentials in env variables.
        """

        if unsigned:
            self.s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
        else:
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
                    logger.info(f"Downloaded: {key} -> {local_file_path}")
                except ClientError as e:
                    logger.error(f"Failed to download {key}: {e}")

    def push_files_in_folder_to_s3(
        self,
        src_folder: str,
        s3_bucket: str,
        s3_prefix: str,
        upload_folder: bool = False,
        exclude_extensions: list[str] = [],
        exclude_files: list[str] = [],
        last_suffixes: tuple[str, ...] = (),
    ):
        """Upload the files in a local folder to an S3 bucket. The subfolder
        structure in the specified folder is maintained in s3.

        Files whose name ends with one of `last_suffixes` are uploaded after
        all other files, in the order the suffixes are given. This allows a
        file to act as a commit marker: if it exists in s3, every other file
        in the folder was uploaded before it.

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
        last_suffixes : tuple[str, ...], optional
            Filename suffixes to upload after all other files, in the order
            given. By default () and files are uploaded in os.walk order.
        """

        logger.info(f"Attempting to upload to S3 bucket : {s3_bucket}")

        local_paths = []
        for root, dirs, files in os.walk(src_folder):
            for file in files:
                if exclude_extensions:
                    filename, file_extension = os.path.splitext(file)
                    if file_extension in exclude_extensions:
                        continue
                if file in exclude_files:
                    continue
                local_paths.append(Path(root) / Path(file))

        def _upload_rank(local_path: Path) -> int:
            # files not matching any suffix keep rank 0 and are uploaded first
            for i, suffix in enumerate(last_suffixes):
                if local_path.name.endswith(suffix):
                    return i + 1
            return 0

        # sorted is stable, so the os.walk order is kept within each rank
        for local_path in sorted(local_paths, key=_upload_rank):
            relative_path = Path(os.path.relpath(local_path, src_folder))
            if not upload_folder:
                s3_key = Path(os.path.join(s3_prefix, relative_path).replace("\\", "/"))
            else:
                folder = Path(src_folder).name
                s3_key = Path(
                    os.path.join(s3_prefix, folder, relative_path).replace("\\", "/")
                )
            file_mime_type, _ = mimetypes.guess_type(local_path)
            self.s3.upload_file(
                str(local_path),
                str(s3_bucket),
                str(s3_key),
                ExtraArgs={"ContentType": file_mime_type or "binary/octet-stream"},
            )
            logger.info(f"Uploaded {local_path} to s3://{s3_bucket}/{s3_key}")

    def acquire_upload_claim(
        self,
        s3_bucket: str,
        claim_key: str,
        owner: dict,
        stale_after_seconds: float = UPLOAD_CLAIM_STALE_AFTER_SECONDS,
    ) -> str | None:
        """Claim the right to upload a product using an S3 conditional write,
        so concurrent runs do not interleave their uploads to the same keys.

        The claim object is created with `If-None-Match: *`, so only one run can
        create it. If a claim already exists and is older than
        `stale_after_seconds` (e.g. its owner was killed), it is taken over
        with `If-Match: <etag>`, so only one run can take it over.

        Parameters
        ----------
        s3_bucket : str
            S3 bucket
        claim_key : str
            Key of the claim object. See `make_upload_claim_key`.
        owner : dict
            Information about the claiming run, written to the claim body.
        stale_after_seconds : float, optional
            Age after which an existing claim may be taken over.

        Returns
        -------
        str | None
            The ETag of the claim object if the claim was acquired, else None.

        Raises
        ------
        ClientError
            For errors other than losing the conditional write.
        """
        body = json.dumps(
            {**owner, "claimed_at": datetime.now(timezone.utc).isoformat()}
        ).encode("utf-8")
        put_args = dict(
            Bucket=s3_bucket,
            Key=claim_key,
            Body=body,
            ContentType="application/json",
        )

        # two attempts in case the existing claim is deleted while we check it
        for _ in range(2):
            try:
                response = self.s3.put_object(**put_args, IfNoneMatch="*")
                logger.info(f"Acquired upload claim : s3://{s3_bucket}/{claim_key}")
                return response["ETag"]
            except ClientError as e:
                if _client_error_code(e) not in _CLAIM_CONFLICT_CODES:
                    raise

            # the claim exists. Check if it is stale
            try:
                head = self.s3.head_object(Bucket=s3_bucket, Key=claim_key)
            except ClientError as e:
                if _client_error_code(e) in _NOT_FOUND_CODES:
                    logger.info("Upload claim was released while checking it, retrying")
                    continue
                raise

            claim_age = (
                datetime.now(timezone.utc) - head["LastModified"]
            ).total_seconds()
            if claim_age < stale_after_seconds:
                logger.warning(
                    f"Upload claim is held by another run ({claim_age:.0f}s old) : "
                    f"s3://{s3_bucket}/{claim_key}"
                )
                return None

            logger.warning(
                f"Taking over stale upload claim ({claim_age:.0f}s old) : "
                f"s3://{s3_bucket}/{claim_key}"
            )
            try:
                response = self.s3.put_object(**put_args, IfMatch=head["ETag"])
                return response["ETag"]
            except ClientError as e:
                if _client_error_code(e) in _CLAIM_CONFLICT_CODES + _NOT_FOUND_CODES:
                    logger.warning("Another run took over the stale claim first")
                    return None
                raise

        return None

    def release_upload_claim(self, s3_bucket: str, claim_key: str, etag: str):
        """Delete an upload claim if it is still the one we wrote (its ETag
        matches). Errors are logged and not raised, as an unreleased claim
        only delays other runs until it goes stale.

        Parameters
        ----------
        s3_bucket : str
            S3 bucket
        claim_key : str
            Key of the claim object
        etag : str
            ETag returned by `acquire_upload_claim`
        """
        try:
            head = self.s3.head_object(Bucket=s3_bucket, Key=claim_key)
            if head["ETag"] != etag:
                logger.warning(
                    f"Upload claim was taken over by another run, not releasing : "
                    f"s3://{s3_bucket}/{claim_key}"
                )
                return
            self.s3.delete_object(Bucket=s3_bucket, Key=claim_key)
            logger.info(f"Released upload claim : s3://{s3_bucket}/{claim_key}")
        except ClientError as e:
            logger.warning(
                f"Could not release upload claim s3://{s3_bucket}/{claim_key} : {e}"
            )

    @staticmethod
    def s3_bucket_has_public_read_access(s3_bucket: str) -> bool:
        """
        Check if the specified S3 bucket is publicly readable for the given prefixes.

        Parameters:
        -----------
        s3_bucket : str
            The name of the S3 bucket to check.

        Returns:
        --------
        bool
            True if the S3 bucket is publicly readable, False otherwise.
        """
        logger.info("Checking the buckets access for signed S3")
        s3 = boto3.client("s3")

        is_public = False

        # 1. Check Public Access Block``
        try:
            pab = s3.get_public_access_block(Bucket=s3_bucket)
            config = pab["PublicAccessBlockConfiguration"]
            if not all(
                [
                    config.get("BlockPublicAcls"),
                    config.get("IgnorePublicAcls"),
                    config.get("BlockPublicPolicy"),
                    config.get("RestrictPublicBuckets"),
                ]
            ):
                is_public = True
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchPublicAccessBlockConfiguration":
                is_public = True

        # 2. Check Bucket Policy Status
        try:
            policy_status = s3.get_bucket_policy_status(Bucket=s3_bucket)
            if policy_status["PolicyStatus"]["IsPublic"]:
                is_public = True
        except ClientError:
            pass  # No bucket policy exists

        s3.close()  # Close the S3 client after checking each folder

        logger.info(f"Bucket '{s3_bucket}' public status: {is_public}")
        return is_public
