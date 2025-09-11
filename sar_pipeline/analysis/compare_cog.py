import rasterio
import numpy as np


def get_tif_stats(
    tif: str,
    stats_dict: dict = {},
    stat_prefix: str = "",
    mask=False,
    verbose: bool = False,
) -> dict:
    """helper function to save metrics. metrics calculated are :
            min, max, mean, median, std, 5th percentile,
            95th percentile, fraction of nodata.
            Use a mask to only calculate metrics in specific region of tif
    Args:
        tif (str): path to file
        stats_dict (dict): dictionary to save the metrics to
        stat_prefix (str): prefix for metrics in dict e.g. 'rtc_db_1_'
        mask (optional) : shapefile mask, calculate metrics within the mask (e.g. scene bounds)
        verbose (bool) : print the calculated metrics

    Returns:
        dict: returns the
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
                print(f"{metric} : {stats_dict[metric]}")

    return stats_dict


def compare_cog_stats(tif_1, tif_2):

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
