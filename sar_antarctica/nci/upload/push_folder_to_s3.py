import boto3
from pathlib import Path
import os
import click
import logging

@click.command()
@click.argument('src_folder', type=click.Path(exists=True, file_okay=False))
@click.argument('s3_bucket')
@click.argument('s3_bucket_folder')
@click.option('--exclude-extensions', '-e', multiple=True, help="File extensions to exclude, e.g., '.txt', '.log'")
@click.option('--exclude-files', '-f', multiple=True, help="Specific files to exclude, e.g., 'config.json'")
@click.option('--region-name', default='ap-southeast-2', show_default=True, help="AWS region name")
def push_files_in_folder_to_s3(
        src_folder : str,
        s3_bucket : str,
        s3_bucket_folder : str,
        exclude_extensions : list[str] = [],
        exclude_files : list[str] = [],
        region_name : str = 'ap-southeast-2',
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
    exclude_extensions : list[str], optional
        List of file extensions to exclude, by default []
    exclude_files : list[str], optional
        List of files to exclude, by default []
    region_name : str, optional
        _description_, by default 'ap-southeast-2'
    """

    # search for credentials in envrionment and raise warning if not there
    if os.environ.get('AWS_ACCESS_KEY_ID') is None:
         wrn_msg = 'AWS_ACCESS_KEY_ID is not set in envrionment variables. Set if authenticaiton required on bucket'
         logging.warning(wrn_msg)
    if os.environ.get('AWS_SECRET_ACCESS_KEY') is None:
        wrn_msg = 'AWS_ACCESS_KEY_ID is not set in envrionment variables. Set if authenticaiton required on bucket'
        logging.warning(wrn_msg)


    S3_CLIENT = boto3.client(
        's3', 
        region_name=region_name
    )

    logging.info(f'Attempting to upload to S3 bucket : {s3_bucket}')

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
                s3_key = Path(os.path.join(s3_bucket_folder, relative_path).replace("\\", "/"))
                S3_CLIENT.upload_file(str(local_path), str(s3_bucket), str(s3_key))
                logging.info(f"Uploaded {local_path} to s3://{s3_bucket}/{s3_key}")

if __name__ == "__main__":

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    push_files_in_folder_to_s3()