import click
import logging
from pathlib import Path
import os

from sar_pipeline import PROJECT_ROOT_PATH

from sar_pipeline.utils.aws import S3Util

from sar_pipeline.analysis.compare_folder import compare_product_folder_files
from sar_pipeline.analysis.compare_metadata import (
    compare_json,
    compare_xml,
    write_diffs_to_json,
    write_diffs_to_xml,
)
from sar_pipeline.analysis.compare_cog import compare_cog_stats

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@click.command()
@click.option(
    "--product",
    required=True,
    type=click.Choice(["RTC_S1", "RTC_S1_STATIC"]),
    help="The product type being compared",
)
@click.option(
    "--local-product-folder-1",
    required=False,
    type=click.Path(file_okay=False, path_type=Path),
    help="Path to the local folder containing the first burst outputs from RTC/opera to compare",
)
@click.option(
    "--local-product-folder-2",
    required=False,
    type=click.Path(file_okay=False, path_type=Path),
    help="Path to the local folder containing the second burst outputs from RTC/opera to compare",
)
@click.option(
    "--s3-product-folder-1",
    required=False,
    type=click.Path(file_okay=False, path_type=Path),
    help="Path to the folder in s3 containing the first burst outputs from RTC/opera to compare."
    " Ensure AWS_ACCESS_KEY_ID, AWS_ACCESS_KEY_SECRET, AWS_DEFAULT_REGION environment variables set if required.",
)
@click.option(
    "--s3-product-folder-2",
    required=False,
    type=click.Path(file_okay=False, path_type=Path),
    help="Path to the folder in s3 containing the second burst outputs from RTC/opera to compare."
    "Ensure AWS_ACCESS_KEY_ID, AWS_ACCESS_KEY_SECRET, AWS_DEFAULT_REGION environment variables set if required.",
)
@click.option(
    "--s3-bucket",
    required=False,
    default="dea-public-data-dev",
    type=str,
    help="S3 where outputs are being stored. Required if s3 folders are set as input",
)
@click.option(
    "--out-folder",
    required=False,
    default=PROJECT_ROOT_PATH / "comparison",
    type=click.Path(file_okay=False, path_type=Path),
    help="Folder to write the outputs of the comparison to",
)
def compare_isce3_products(
    product,
    local_product_folder_1,
    local_product_folder_2,
    s3_product_folder_1,
    s3_product_folder_2,
    s3_bucket,
    out_folder,
):
    """
    Compare two ISCE-RTC products by evaluating differences in file structure, metadata, and raster outputs.
    The function supports both local and S3-hosted product folders, downloading remote inputs as needed.
    It checks for discrepancies in file counts and types, compares JSON metadata
    (and XML metadata for RTC_S1 products), and computes statistics-based differences between corresponding GeoTIFFs.
    All difference summaries are saved to the specified output folder as JSON or XML files,
    providing a concise record of how code updates or pipeline changes have impacted the resulting products.
    """
    logger.info(f"The product being compared is : {product}")
    logger.info(f"The outputs will be written to : {out_folder}")

    if not out_folder.exists():
        raise ValueError(
            f"Specified --out-folder does not exist, please create: {out_folder}"
        )

    if not (s3_product_folder_1 or local_product_folder_1):
        logger.error(
            "Ensure either --local-product-folder-1 or --s3-product-folder-1 set"
        )
        raise ValueError
    elif not (s3_product_folder_2 or local_product_folder_2):
        logger.error(
            "Ensure either --local-product-folder-2 or --s3-product-folder-2 set"
        )
        raise ValueError

    if s3_product_folder_1 or s3_product_folder_2:
        # set up the AWS download util
        S3Downloader = S3Util()

    if s3_product_folder_1:
        # download product folder to local folder
        local_product_folder_1 = out_folder / "folder_1" / s3_product_folder_1
        os.makedirs(local_product_folder_1, exist_ok=True)
        S3Downloader.download_folder(
            s3_bucket, s3_product_folder_1, local_product_folder_1
        )
    if s3_product_folder_2:
        # download product folder to local folder
        local_product_folder_2 = out_folder / "folder_2" / s3_product_folder_2
        os.makedirs(local_product_folder_2, exist_ok=True)
        S3Downloader.download_folder(
            s3_bucket, s3_product_folder_2, local_product_folder_2
        )

    # compare count of files and filetypes in folder
    files_are_different, file_differences = compare_product_folder_files(
        local_product_folder_1, local_product_folder_2
    )
    file_differences_path = out_folder / "file_differences.json"
    if files_are_different:
        logging.warning(
            f"Differences in product files found. Saving summary to : {file_differences_path}"
        )
    else:
        logger.info(
            f"No differences in product files identified. Saving summary to : {file_differences_path}"
        )
    write_diffs_to_json(file_differences, file_differences_path)

    # compare the json files
    json_files_1 = list(local_product_folder_1.glob("*.json"))
    json_files_2 = list(local_product_folder_2.glob("*.json"))
    if len(json_files_1) > 1:
        logging.error("Multiple jsons found for product 1, expecting 1 per product")
        raise ValueError
    if len(json_files_2) > 1:
        logging.error("Multiple jsons found for product 2, expecting 1 per product")
        raise ValueError

    json_differences = compare_json(str(json_files_1[0]), str(json_files_2[0]))
    json_difference_path = out_folder / "json_differences.json"
    if len(json_differences) > 0:
        logging.warning(
            f"Differences in json metadata found. Saving summary to : {json_difference_path}"
        )
    else:
        logger.info(
            f"No differences in json file identified. Saving summary to : {json_difference_path}"
        )
    write_diffs_to_json(json_differences, json_difference_path)

    if product == "RTC_S1":
        # compare the xml files - xml only exits for rtc_s1
        xml_files_1 = list(local_product_folder_1.glob("*.xml"))
        xml_files_2 = list(local_product_folder_2.glob("*.xml"))
        if len(xml_files_1) > 1:
            logging.error("Multiple xmls found in product 1, expecting 1")
            raise ValueError
        if len(xml_files_2) > 1:
            logging.error("Multiple xmls found in product 2, expecting 1")
            raise ValueError

        xml_differences = compare_xml(str(xml_files_1[0]), str(xml_files_2[0]))
        xml_difference_path = out_folder / "xml_differences.xml"
        if len(xml_differences) > 0:
            logging.warning(
                f"Differences in xml metadata found. Saving summary to : {xml_difference_path}"
            )
        else:
            logger.info(
                f"No differences in XML file identified. Saving summary to : {xml_difference_path}"
            )
        write_diffs_to_xml(xml_differences, xml_difference_path)

    # compare the like tifs. e.g. compare mask to mask, HH-gamma0 to HH-gamma0
    # e.g. tif_1 = ga_s1a_nrb_0-1-0_T070-149815-IW3_20211220T124752Z_HH-gamma0.tif # new product created now
    # e.g. tif_2 = ga_s1a_nrb_0-1-0_T070-149815-IW3_20211220T124752Z_HH-gamma0.tif # existing to compare
    logger.info("Comparing the tifs between products")
    tif_files_1 = set(local_product_folder_1.glob("*.tif"))
    tif_files_2 = set(local_product_folder_2.glob("*.tif"))
    tif_comparison_stats = {}
    tif_difference_path = out_folder / "tif_differences.json"
    for tif_1 in tif_files_1:
        filetype = tif_1.stem.split("_")[
            -1
        ]  # i.e. mask, HH-gamma0, local_incidence_angle
        if not files_are_different:
            # we have the exact same tif naming and can compare directly
            tif_2 = local_product_folder_2 / tif_1.name
            logger.info(f"Comparing tif statistics of filetype : {filetype}")
            tifs_are_same, stats = compare_cog_stats(tif_1, tif_2)
            tif_comparison_stats[filetype] = stats
        else:
            tif_2 = [x for x in tif_files_2 if str(filetype) in str(x)]
            if not tif_2:
                logger.warning(
                    f'Could not find tif of same filetype "{filetype}" to compare with {tif_1}'
                )
                continue
            elif len(tif_2) > 1:
                logger.error(
                    f'Multiple tif files found for file type "{filetype}", expecting 1. Skipping comparison'
                )
                continue
            else:
                logger.info(f"Comparing tif statistics of filetype : {filetype}")
                tifs_are_same, stats = compare_cog_stats(tif_1, tif_2[0])
                tif_comparison_stats[filetype] = stats

        if not tifs_are_same:
            logging.warning(
                f"Differences in tif statistics found. Saving summary to : {tif_difference_path}"
            )
        else:
            logger.info(
                f"No differences in tif statistics found. Saving summary to : {tif_difference_path}"
            )
        write_diffs_to_json(tif_comparison_stats, tif_difference_path)
