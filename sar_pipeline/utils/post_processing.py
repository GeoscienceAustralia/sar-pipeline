from osgeo import gdal
from pathlib import Path
import typing

GdalWarpResampleAlgType = typing.Literal[
    "near",
    "bilinear",
    "cubic",
    "cubicspline",
    "lanczos",
    "average",
    "rms",
    "mode",
    "min",
    "max",
    "med",
    "q1",
    "q3",
    "sum",
]
GDAL_WARP_RESAMPLE_ALGORITHMS: tuple[str, ...] = typing.get_args(
    GdalWarpResampleAlgType
)


# GDAL Warp - reproject
def gdal_reproject(
    src_file: Path | str,
    dst_file: Path | str,
    dst_epsg: int,
    dst_resolution: float | int,
    resample_algorithm: GdalWarpResampleAlgType = "bilinear",
) -> None:
    """Wrapper for gdalwarp designed for reprojection from one CRS to another

    Parameters
    ----------
    src_file : Path | str
        Location of the source file
    dst_file : Path | str
        Location of the destination file
    dst_epsg : int
        Numeric EPSG code for the reprojection (e.g. 3031 for polar sterographic)
    dst_resolution : float | int
        Resolution for pixels in the destination CRS
    resample_algorithm : GdalWarpResampleAlgType, optional
        The resampling algorithm. Any of "near", "bilinear", "cubic", "cubicspline", "lanczos", "average",
        "rms", "mode", "min", "max", "med", "q1", "q3", "sum", by default "bilinear"

    Raises
    ------
    ValueError
        If provided resanpling algorithm is not one of those listed.
    """

    # Check resampling algorithm is valid
    if resample_algorithm not in GDAL_WARP_RESAMPLE_ALGORITHMS:
        raise ValueError(
            f"Provided resampling algorithm, '{resample_algorithm}', is invalid. Valid options are {GDAL_WARP_RESAMPLE_ALGORITHMS}"
        )

    warp_options = gdal.WarpOptions(
        dstSRS=f"EPSG:{dst_epsg}",
        xRes=dst_resolution,
        yRes=dst_resolution,
        resampleAlg=resample_algorithm,
    )

    gdal.Warp(dst_file, src_file, options=warp_options)


# GDAL update nodata
def gdal_update_nodata(
    src_file: Path | str,
    dst_file: Path | str,
    dst_nodata: typing.Literal["nan"] | float | int,
) -> None:
    """Wrapper for gdalwarp designed to update the nodata value

    Parameters
    ----------
    src_file : Path | str
        Location of the source file
    dst_file : Path | str
        Location of the destination file
    dst_nodata : "nan" | float | int
        Desired nodata value
    """

    warp_options = gdal.WarpOptions(dstNodata=dst_nodata)

    gdal.Warp(dst_file, src_file, options=warp_options)


GdalBuildOverviewsResampleAlgType = typing.Literal[
    "nearest",
    "average",
    "rms",
    "gauss",
    "bilinear",
    "cubic",
    "cubicspline",
    "lanczos",
    "average_magphase",
    "mode",
]
GDAL_BUILD_OVERVIEWS_RESAMPLE_ALGORITHMS: tuple[str, ...] = typing.get_args(
    GdalBuildOverviewsResampleAlgType
)


# GDAL Add Overviews
def gdal_add_overviews(
    file: Path | str,
    overviews: list[int] = [4, 16, 64, 128],
    resample_algorithm: GdalBuildOverviewsResampleAlgType = "cubicspline",
) -> None:
    """Wrapper for gdal build overviews

    Parameters
    ----------
    file : Path | str
        Location of the source file. It will be updated in place.
    overviews : list[int], optional
        A list of overview levels (decimation factors) to build,
        or an empty list to clear existing overviews, by default [4, 16, 64, 128]
    resample_algorithm : GdalBuildOverviewsResampleAlgType, optional
        The resampling algorithm. Any of "nearest", "average", "rms", "gauss", "bilinear",
        "cubic", "cubicspline", "lanczos", "average_magphase", "mode", by default "cubicspline"
    """

    # Open the dataset in update mode
    dataset: gdal.Dataset = gdal.Open(file, gdal.GA_Update)

    # Build overviews
    dataset.BuildOverviews(resample_algorithm, overviews)

    del dataset
