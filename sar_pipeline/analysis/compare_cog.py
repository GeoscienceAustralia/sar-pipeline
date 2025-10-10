import rasterio
import numpy as np
import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_tif_stats(
    tif: str,
    stats_dict: dict = {},
    stat_prefix: str = "",
    mask=False,
    verbose: bool = False,
) -> dict:
    """
    Calculate basic statistics for a GeoTIFF file.

    Computes the following metrics: minimum, maximum, mean, median, standard deviation,
    5th percentile, 95th percentile, and fraction of NoData pixels. Optionally, metrics
    can be computed only within a specified mask region.

    Parameters
    ----------
    tif (str):
        Path to the GeoTIFF file.
    stats_dict (dict, optional):
        Dictionary to store the computed metrics.Defaults to an empty dictionary.
    stat_prefix (str, optional):
        Prefix to prepend to metric keys in the output dictionary (e.g., "rtc_db_1_").
        Defaults to an empty string.
    mask (optional):
        Geometry (e.g., shapely polygon) used to mask the raster. If provided, statistics
        are computed only within this region.
    verbose (bool, optional):
        If True, logs the computed metrics. Defaults to False.

    Returns
    -------
    dict:
        A dictionary containing the computed statistics with key names
        formatted as `<stat_prefix><metric_name>`.
    """

    with rasterio.open(tif) as src:
        if mask:
            data, out_transform = rasterio.mask.mask(
                src, [mask], crop=True, all_touched=True, filled=src.nodata
            )
            data = data[0]
        else:
            data = src.read(1)

    shape = data.shape
    frac_nodata = 1 - (np.isfinite(data).sum() / np.prod(data.shape))
    data = np.array(data)[np.array((np.isfinite(data)))]
    stats_dict[f"{stat_prefix}height"] = int(shape[0])
    stats_dict[f"{stat_prefix}width"] = int(shape[1])
    stats_dict[f"{stat_prefix}min"] = float(data.min())
    stats_dict[f"{stat_prefix}max"] = float(data.max())
    stats_dict[f"{stat_prefix}median"] = float(np.percentile(data, 50))
    stats_dict[f"{stat_prefix}mean"] = float(np.mean(data))
    stats_dict[f"{stat_prefix}std"] = float(np.std(data))
    stats_dict[f"{stat_prefix}5p"] = float(np.percentile(data, 5))
    stats_dict[f"{stat_prefix}95p"] = float(np.percentile(data, 95))
    stats_dict[f"{stat_prefix}frac_nodata"] = float(frac_nodata)

    if verbose:
        for metric in stats_dict.keys():
            if stat_prefix in metric:
                logger.info(f"{metric} : {stats_dict[metric]}")

    return stats_dict


def compare_cog_stats(tif_1, tif_2):
    """
    Compare statistical metrics between two Cloud Optimized GeoTIFF (COG) files.

    Calculates key statistics for each input COG using `get_tif_stats`, compares them
    metric-by-metric, and reports both equality and numerical differences.

    Parameters
    ----------
    tif_1 (str):
        Path to the first GeoTIFF file.
    tif_2 (str):
        Path to the second GeoTIFF file.

    Returns
    -------
    tuple, dict:
        bool: True if all corresponding statistics between the two files are equal,
            otherwise False.
        dict: A dictionary containing:
            - "tif_1" (str): Path to the first file.
            - "tif_2" (str): Path to the second file.
            - "tif_1_stats" (dict): Calculated statistics for the first file.
            - "tif_2_stats" (dict): Calculated statistics for the second file.
            - "stats_are_equal" (dict): Boolean equality results for each metric.
            - "stat_differences" (dict): Numeric differences (`tif_1 - tif_2`) for each metric.
    """

    tif_1_stats = get_tif_stats(tif_1)
    tif_2_stats = get_tif_stats(tif_2)
    is_equal = {}
    diff = {}

    for k in tif_1_stats.keys():
        tif_1_val = tif_1_stats[k]
        tif_2_val = tif_2_stats[k]
        val_equal = tif_1_val == tif_2_val
        val_dif = tif_1_val - tif_2_val
        is_equal[k] = val_equal
        diff[k] = val_dif

    tifs_are_same = all([is_equal[k] for k in is_equal.keys()])

    comparison_stats = {
        "tif_1": str(tif_1),
        "tif_2": str(tif_2),
        "tif_1_stats": tif_1_stats,
        "tif_2_stats": tif_2_stats,
        "stats_are_equal": is_equal,
        "stat_differences": diff,
    }

    return tifs_are_same, comparison_stats


def check_tifs_have_changed(tif_difference_json_path) -> bool:
    """checks the outputs of the tif difference json to see if
    the tif values have changed"""
    with open(tif_difference_json_path, "r") as f:
        data = json.load(f)

    # Loop through the assets that are being compared to see if
    # Any of the tif statistics have changed
    for asset in data.keys():
        stats_are_equal = data[asset]["stats_are_equal"]
        # get the list of equalities (i.e. True or False)
        stats_are_equal = [stats_are_equal[k] for k in stats_are_equal.keys()]
        if any(x is False for x in stats_are_equal):
            return True
    return False
