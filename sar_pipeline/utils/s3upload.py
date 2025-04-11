import boto3
from pathlib import Path
import os
import logging


def push_files_in_folder_to_s3(
    src_folder: str,
    s3_bucket: str,
    s3_bucket_folder: str,
    upload_folder: bool = False,
    exclude_extensions: list[str] = [],
    exclude_files: list[str] = [],
    region_name: str = "ap-southeast-2",
):
    """Upload the files in a local folder to an S3 bucket. The subfolder
    structure in the specified folder is maintained in s3.

    Parameters
    ----------
    src_folder : str
        Source folder containing files of interest
    s3_bucket : str
        S3 bucket to push to
    s3_bucket_folder : str
        Folder within bucket to push to
    upload_folder : bool
        upload the entire folder to the s3_bucket_folder.
        If; src_folder = my/local_folder/ & s3_bucket_folder = s3/s3_folder
        when True, all files uploaded to -> s3/s3_folder/local_folder/...
        when False, all files uploaded to -> s3/s3_folder/...
    exclude_extensions : list[str], optional
        List of file extensions to exclude, by default []
    exclude_files : list[str], optional
        List of files to exclude, by default []
    region_name : str, optional
        _description_, by default 'ap-southeast-2'
    """

    # search for credentials in envrionment and raise warning if not there
    if os.environ.get("AWS_ACCESS_KEY_ID") is None:
        wrn_msg = "AWS_ACCESS_KEY_ID is not set in envrionment variables. Set if authenticaiton required on bucket"
        logging.warning(wrn_msg)
    if os.environ.get("AWS_SECRET_ACCESS_KEY") is None:
        wrn_msg = "AWS_ACCESS_KEY_ID is not set in envrionment variables. Set if authenticaiton required on bucket"
        logging.warning(wrn_msg)

    S3_CLIENT = boto3.client("s3", region_name=region_name)

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
                    os.path.join(s3_bucket_folder, relative_path).replace("\\", "/")
                )
            else:
                folder = Path(src_folder).name
                s3_key = Path(
                    os.path.join(s3_bucket_folder, folder, relative_path).replace(
                        "\\", "/"
                    )
                )
            S3_CLIENT.upload_file(str(local_path), str(s3_bucket), str(s3_key))
            logging.info(f"Uploaded {local_path} to s3://{s3_bucket}/{s3_key}")
