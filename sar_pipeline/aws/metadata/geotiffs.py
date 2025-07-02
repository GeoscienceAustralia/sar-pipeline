import rasterio
from sar_pipeline.aws.metadata.filetypes import UPDATED_METADATA_PARAMETERS

TIF_UPDATED_METADATA_PARAMETERS = {
    "CEOS_ANALYSIS_READY_DATA_DOCUMENT_IDENTIFIER": UPDATED_METADATA_PARAMETERS[
        "CEOS_DOC"
    ],
    "CEOS_ANALYSIS_READY_DATA_PRODUCT_TYPE": UPDATED_METADATA_PARAMETERS[
        "CEOS_ARD_TYPE"
    ],
    "CONTACT_INFORMATION": UPDATED_METADATA_PARAMETERS["CONTACT_INFO"],
    "INSTITUTION": UPDATED_METADATA_PARAMETERS["INSTITUTION"],
    "PROJECT": UPDATED_METADATA_PARAMETERS["PROJECT"],
}

import rasterio
from pathlib import Path


def update_tif_metadata_in_place(tif_path: str | Path):
    """Update or add metadata fields (tags) in-place in a GeoTIFF file.

    Parameters
    ----------
    tif_path : str | Path
        Path to the input .tif file to modify in-place.
    """
    tif_path = Path(tif_path)

    with rasterio.open(tif_path, "r+") as dataset:
        current_tags = dataset.tags()
        current_tags.update(TIF_UPDATED_METADATA_PARAMETERS)
        dataset.update_tags(**current_tags)
