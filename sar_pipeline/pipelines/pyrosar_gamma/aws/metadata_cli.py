import click
import logging
from pathlib import Path
import re
import json

from sar_pipeline.pipelines.pyrosar_gamma.metadata.stac import GammaNRBtoSTAC
from sar_pipeline.utils.aws import find_s3_filepaths_from_suffixes, S3Util
from sar_pipeline.utils.general import log_timing
from sar_pipeline.utils.checksum import PackageChecksum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@click.command()
@click.option(
    "--scene",
    type=str,
    required=True,
    help="scene id. E.g. S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD",
)
@click.option(
    "--results-folder",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Path to the folder containing the product outputs from pyrosar-GAMMA.",
)
@click.option(
    "--orbit-source-folder",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Path to the folder containing the orbit source information.",
)
@click.option(
    "--backscatter-convention",
    required=False,
    default="gamma0",
    type=click.Choice(["gamma0", "sigma0", "beta0"]),
    help="Backscatter convention of the product to be made (gamma0, sigma0 or beta0)",
)
@click.option(
    "--collection-number",
    required=False,
    default=1,
    type=int,
    help="The collection number of the product.",
)
@click.option(
    "--s3-bucket",
    required=False,
    default="dea-public-data-dev",
    type=str,
    help="The bucket to upload the files",
)
@click.option(
    "--s3-project-folder",
    required=False,
    default="experimental/baseline",
    type=click.Path(file_okay=False, path_type=Path),
    help="The folder within the bucket to upload the files. Note the "
    "final path follows the pattern in the description of this function.",
)
@click.option(
    "--skip-upload-to-s3",
    required=False,
    is_flag=True,
    default=False,
    help="If we should upload outputs to S3.",
)
@click.option(
    "--make-existing-products",
    required=False,
    is_flag=True,
    default=False,
    help="Create the product even if it already exists in the desired s3 bucket path. "
    "WARNING - setting this argument may result in duplicate files.",
)
@click.option(
    "--validate-stac",
    required=False,
    is_flag=True,
    default=True,
    help="Whether to validate the stac document within the code. "
    "If the stac is not valid, an error is raised and the products "
    "will not be uploaded.",
)
@click.option(
    "--skip-upload-processed-scene-tracking-file",
    required=False,
    is_flag=True,
    default=False,
    help="Whether to skip uploading a json with very basic information"
    "That can be used to track which scenes have been processed. "
    "By default, it will be uploaded to the following folder: "
    "{s3_project_folder}/monitoring/processed_scenes ",
)
@click.option(
    "--product-version",
    required=False,
    default="1-0-0",
    type=str,
    help="The version of the product.",
)
@log_timing
def make_metadata_and_upload_product(
    results_folder,
    scene,
    backscatter_convention,
    collection_number,
    s3_bucket,
    s3_project_folder,
    skip_upload_to_s3,
    make_existing_products,
    validate_stac,
    skip_upload_processed_scene_tracking_file,
    product_version,
    orbit_source_folder,
):
    """
    Generate STAC metadata for pyroSAR-GAMMA products, reorganise and standardise product filenames,
    build supporting metadata files (STAC JSON, checksums), and optionally upload each product set to an S3 bucket
    following the `GAMMA_RTC_S1_S3_PREFIX_FORMAT` format in `odc.py`.
    The function converts metadata into STAC items, applies optional geometry updates using valid-data masks,
    creates linked assets and metadata references, validates STAC documents if requested, computes checksums,
    and handles overwrite rules for pre‑existing S3 content. It also maintains a processed‑scene tracking record and,
    unless disabled, uploads this summary to a monitoring location within the project’s S3 folder structure.
    """

    # Checking and reading the orbit source folder
    if not orbit_source_folder.is_dir():
        logger.error(f"Orbit source folder does not exist: {orbit_source_folder}")
        raise FileNotFoundError(
            f"Orbit source folder does not exist: {orbit_source_folder}"
        )
    else:
        orbit_source_files = list(Path(orbit_source_folder).glob("*"))
        assert (
            len(orbit_source_files) == 1
        ), f"Expected exactly one file in the orbit source folder, found {len(orbit_source_files)}: {orbit_source_files}"
        orbit_source_file = orbit_source_files[0]
        if "POEORB" in orbit_source_file.name:
            logger.info(
                f"Using precise orbit ephemeris data from file: {orbit_source_file}"
            )
            orbit_source = "POE precise orbit"
        elif "RESORB" in orbit_source_file.name:
            logger.info(
                f"Using restituted orbit ephemeris data from file: {orbit_source_file}"
            )
            orbit_source = "RES restituted orbit"
        else:
            raise ValueError(
                f"Orbit source file name does not contain expected keywords (POEORB or RESORB). "
                f"Please verify that the correct file is being used: {orbit_source_file}"
            )
        logger.info(f"Orbit source information loaded from {orbit_source_file}")

    # tracking file for processed scenes to assist with completion checking
    processed_scene_json = {"scene_id": scene, "stac": []}

    # initialise the S3 utility
    if not skip_upload_to_s3:
        S3UPLOADER = S3Util()

    logger.info(
        f"Making STAC metadata for {results_folder} and uploading to S3 bucket : {s3_bucket} if not already exist or --make-existing-products is set."
    )

    logger.info(
        f"Renaming all files so 'v' is not in the product version number, version is '-' separated, and the platform name is lowercase (e.g s1a)."
    )
    for product_file in results_folder.iterdir():
        if product_file.is_file():
            name = re.sub(
                r"S1[A-Z]",
                lambda m: f"ga_{m.group(0).lower()}_nrb_{product_version}",
                product_file.name,
            )
            new_path = product_file.with_name(name)
            if new_path != product_file:
                logger.info(f"Renaming: {product_file.name} -> {new_path.name}")
                product_file.rename(new_path)

    stac_object = GammaNRBtoSTAC(
        scene_id=scene,
        product_folder=results_folder,
        backscatter_convention=backscatter_convention,
        collection_number=collection_number,
        s3_bucket=s3_bucket,
        orbit_source=orbit_source,
        s3_project_folder=s3_project_folder,
    )

    stac_object.make_stac_item()
    stac_object.add_properties()
    stac_object.rename_asset_files()
    stac_object.add_assets()

    output_file_prefix = stac_object.get_output_filename_prefix()
    stac_filepath = results_folder / f"{output_file_prefix}_stac-item.json"

    stac_object.add_metadata_links(stac_filepath)
    stac_object.add_collection_link()

    stac_object.save(stac_filepath)

    # create a placeholder checksum file to link in stac metadata
    checksum_filepath = results_folder / f"{output_file_prefix}_checksum.sha1"
    Path(checksum_filepath).touch()

    if validate_stac:
        logger.info("Validating STAC document")
        try:
            stac_object.item.validate()
            logger.info("STAC is valid.")
        except Exception as e:
            logger.error(
                f"STAC validation failed, correct error or run without --validate-stac flag.\n{e}"
            )
            raise
    else:
        logger.warning(
            "STAC document is not being validated. set --validate-stac if required."
        )

    # replace the empty checksum file now all required files have been created
    logger.info("Running checksums on product files")
    product_checksum = PackageChecksum()
    checksum_files = [f for f in results_folder.iterdir() if "checksum" not in str(f)]
    product_checksum.add_files(checksum_files)
    product_checksum.write(checksum_filepath.resolve())

    # push folder to S3
    if skip_upload_to_s3:
        logger.info(f"Skipping upload to S3.")
    else:
        # re-check that the files don't already exist in S3. This will help protect against
        # simultaneous runs of the same product. E.g. the product did not exist at the
        # start of the run and was created by another process during this runtime
        logger.info(
            f"Checking if product already exist before uploading files for product : {stac_object.scene_id}"
        )
        logger.info(f"Searching for .json file in : {stac_object.scene_id}")
        product_json_file = find_s3_filepaths_from_suffixes(
            bucket_name=s3_bucket,
            s3_folder=stac_object.s3_product_folder,
            suffixes=[".json"],
        )

        if make_existing_products or len(product_json_file[".json"]) == 0:
            if len(product_json_file[".json"]) > 0:
                logging.warning(
                    "Existing products will be replaced as --make-existing-products is set."
                )

            logger.info(f"uploading files for {stac_object.scene_id} to S3.")
            S3UPLOADER.push_files_in_folder_to_s3(
                results_folder, s3_bucket, stac_object.s3_product_folder
            )

            # add basic info to the processed scene tracking file
            processed_scene_json["stac"].append(
                str(Path(stac_object.s3_product_folder) / Path(stac_filepath).name)
            )
        else:
            logging.info(
                "Skipping upload for existing product. Set --make-existing-products if this is not desired"
            )

    # upload the tracking file to a sub folder where it can be checked
    if not (skip_upload_processed_scene_tracking_file or skip_upload_to_s3):
        monitoring_folder = Path(s3_project_folder) / "monitoring"
        processed_scene_tracking_file_s3_folder = str(
            monitoring_folder / "processed_scenes"
        )

        processed_scene_tracking_file_s3_key = (
            f"{processed_scene_tracking_file_s3_folder}/{scene}.json"
        )
        logger.info(
            f"Uploading processed scene tracking file to S3 : {processed_scene_tracking_file_s3_key}."
        )
        S3UPLOADER.s3.put_object(
            Bucket=s3_bucket,
            Key=processed_scene_tracking_file_s3_key,
            Body=json.dumps(processed_scene_json, indent=2).encode("utf-8"),
            ContentType="application/json",
        )
