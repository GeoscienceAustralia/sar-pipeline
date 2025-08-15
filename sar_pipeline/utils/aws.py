import os
import pandas as pd
import boto3
import logging
from botocore import UNSIGNED
from botocore.config import Config


class S3Util:
    def __init__(
        self,
        aws_access_key_id=None,
        aws_secret_access_key=None,
        aws_session_token=None,
        region_name="ap-southeast-2",
    ):

        if not aws_access_key_id:
            logging.warning(
                f"No credentials provided. Attempting to use environment variables"
            )
            logging.warning(
                f"Attempting unsigned access, set credentials if bucket is not public or credentials are required for upload"
            )
            config = Config(signature_version=UNSIGNED)
        else:
            config = None

        self.client = boto3.client(
            "s3",
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token,
            region_name=region_name,
            config=config,
        )

    def check_file_exists(self, s3_bucket, key):
        try:
            self.client.head_object(Bucket=s3_bucket, Key=key)
            return True
        except:
            return False

    def download_s3_file(
        self, s3_bucket, key, local_path, make_folders=True, replace=False
    ):
        local_folder = os.path.dirname(local_path)
        if local_folder:
            if (not os.path.exists(local_folder)) and make_folders:
                os.makedirs(local_folder)

        if not replace and os.path.exists(local_path):
            print(f"skipping download, local file already exists: {key}")
        else:
            print(f"downloading {key} to {local_path}")
            self.client.download_file(s3_bucket, key, local_path)

    def download_folder(
        self, s3_bucket, s3_prefix, local_folder, preserve_prefix=False
    ):
        """
        Download all objects from a given S3 prefix into a local folder.

        Args:
            s3_bucket (str): Name of the S3 bucket.
            s3_prefix (str): Prefix within the S3 bucket to download.
            local_folder (str): Local folder path to download into.
            preserve_prefix (bool): If True, keeps the full prefix structure inside the local folder.
                                    If False, strips the prefix and only keeps relative paths.
        """
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=s3_bucket, Prefix=s3_prefix):
            if "Contents" not in page:
                continue
            for obj in page["Contents"]:
                key = obj["Key"]
                if key.endswith("/"):  # skip folders
                    continue

                if preserve_prefix:
                    relative_path = key  # full key is preserved
                else:
                    relative_path = os.path.relpath(key, s3_prefix)  # strip prefix

                local_path = os.path.join(local_folder, relative_path)
                os.makedirs(os.path.dirname(local_path), exist_ok=True)

                if not os.path.exists(local_path):
                    print(f"Downloading s3://{s3_bucket}/{key} to {local_path}")
                    self.client.download_file(s3_bucket, key, local_path)
                else:
                    print(f"Skipping existing file: {local_path}")

    def upload_file(self, s3_bucket, key, local_path):
        self.client.upload_file(local_path, s3_bucket, key)
        print(f"Uploaded {local_path} to s3://{s3_bucket}/{key}")

    def upload_files_in_folder(
        self, local_folder, s3_bucket, s3_prefix="", exclude_ext=[]
    ):

        for root, dirs, files in os.walk(local_folder):
            for file in files:
                if exclude_ext:
                    filename, file_extension = os.path.splitext(file)
                    if file_extension in exclude_ext:
                        continue
                local_path = os.path.join(root, file)
                relative_path = os.path.relpath(local_path, local_folder)
                s3_key = os.path.join(s3_prefix, relative_path).replace("\\", "/")
                self.client.upload_file(local_path, s3_bucket, s3_key)
                print(f"Uploaded {local_path} to s3://{s3_bucket}/{s3_key}")

    def get_bucket_df(self, s3_bucket, s3_prefix):
        file_list = []
        params = {"Bucket": s3_bucket, "Prefix": s3_prefix}
        objects = self.client.list_objects_v2(**params)
        if "Contents" in objects:
            file_list.extend(objects["Contents"])

        return pd.DataFrame.from_records(file_list)
