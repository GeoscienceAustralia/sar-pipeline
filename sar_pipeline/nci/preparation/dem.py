import os
import geopandas as gpd
import numpy as np
from osgeo import gdal
from pathlib import Path
import rasterio
import rasterio.mask
import shapely.geometry
import logging

logger = logging.getLogger(__name__)

from sar_pipeline.utils.spatial import BoundingBox, get_local_utm, adjust_bounds
from sar_pipeline.utils.raster import reproject_raster, merge_arrays_with_geometadata
from sar_pipeline.nci.preparation.dem_cop_glo30 import (
    get_cop_glo30_files_covering_bounds,
    buffer_bounds_cop_glo30,
    make_empty_cop_glo30_profile_for_bounds,
)
from sar_pipeline.nci.preparation.geoid import remove_geoid
from sar_pipeline.nci.preparation.download import (
    download_dem_tile_from_aws, 
    download_egm_08_geoid_from_aws
    )

# Create a custom type that allows use of BoundingBox or tuple(xmin, ymin, xmax, ymax)
BBox = BoundingBox | tuple[float | int, float | int, float | int, float | int]


COP30_FOLDER_PATH = Path(
    "/g/data/v10/eoancillarydata-2/elevation/copernicus_30m_world/"
)
GEOID_TIF_PATH = Path(
    "/g/data/yp75/projects/ancillary/geoid/us_nga_egm2008_1_4326__agisoft.tif"
)

DATA_DIR = Path(os.path.dirname(os.path.realpath(__file__))).parent.parent / Path('data')
COP30_GPKG_PATH = DATA_DIR / Path('copdem_tindex_filename.gpkg')
#COP30_GPKG_PATH = Path("/g/data/yp75/projects/ancillary/dem/copdem_tindex.gpkg")


def get_cop30_dem_for_bounds(
    bounds: BBox,
    save_path: Path,
    ellipsoid_heights: bool = True,
    adjust_at_high_lat: bool = True,
    buffer_pixels: int | None = 10,
    buffer_world: int | float | None = None,
    cop30_index_path: Path = COP30_GPKG_PATH,
    cop30_folder_path: Path = COP30_FOLDER_PATH,
    geoid_tif_path: Path = GEOID_TIF_PATH,
    download_dem_tiles: bool = False,
    download_geoid: bool =  False,
):

    # Convert bounding box to built-in bounding box type
    if isinstance(bounds, tuple):
        bounds = BoundingBox(*bounds)

    # Check if bounds cross the antimeridian
    antimeridian_crossing = check_s1_bounds_cross_antimeridian(
        bounds, max_scene_width=8
    )

    if antimeridian_crossing:
        logger.warning(
            "DEM crosses the dateline/antimeridian. Bounds will be split and processed."
        )

        target_crs = get_target_antimeridian_projection(bounds)

        logger.info(f"Splitting bounds into left and right side of antimeridian")
        bounds_eastern, bounds_western = split_s1_bounds_at_am_crossing(bounds)

        # Use recursion to process each side of the AM. The function is rerun
        # This time, antimeridian_crossing will be False enabling each side to be
        # independantly processed
        logger.info("Producing raster for Eastern Hemisphere bounds")
        eastern_save_path = save_path.parent.joinpath(
            save_path.stem + "_eastern" + save_path.suffix
        )
        get_cop30_dem_for_bounds(
            bounds_eastern,
            eastern_save_path,
            ellipsoid_heights,
            adjust_at_high_lat=True,
            buffer_pixels=buffer_pixels,
            cop30_index_path=cop30_index_path,
            cop30_folder_path=cop30_folder_path,
            geoid_tif_path=geoid_tif_path,
        )

        logger.info("Producing raster for Western Hemisphere bounds")
        western_save_path = save_path.parent.joinpath(
            save_path.stem + "_western" + save_path.suffix
        )
        get_cop30_dem_for_bounds(
            bounds_western,
            western_save_path,
            ellipsoid_heights,
            adjust_at_high_lat=True,
            buffer_pixels=buffer_pixels,
            cop30_index_path=cop30_index_path,
            cop30_folder_path=cop30_folder_path,
            geoid_tif_path=geoid_tif_path,
        )

        # reproject to 3031 and merge
        logging.info(
            f"Reprojecting Eastern and Western hemisphere rasters to EPGS:{target_crs}"
        )
        eastern_dem, eastern_profile = reproject_raster(eastern_save_path, target_crs)
        western_dem, western_profile = reproject_raster(western_save_path, target_crs)

        logging.info(f"Merging across antimeridian")
        dem_array, dem_profile = merge_arrays_with_geometadata(
            arrays=[eastern_dem, western_dem],
            profiles=[eastern_profile, western_profile],
            method="max",
            output_path=save_path,
        )

        return dem_array, dem_profile

    else:
        logger.info(f"Getting cop30m dem for bounds: {bounds.bounds}")

        # Adjust bounds at high latitude if requested
        if adjust_at_high_lat:
            adjusted_bounds = adjust_bounds_at_high_lat(bounds)
            logger.info(
                f"Getting cop30m dem for adjusted bounds: {adjusted_bounds.bounds}"
            )
        else:
            adjusted_bounds = bounds

        # Buffer bounds if reqeuested
        if buffer_pixels or buffer_world:
            logger.info(f"Buffering bounds by requested value")
            adjusted_bounds = buffer_bounds_cop_glo30(
                adjusted_bounds,
                pixel_buffer=buffer_pixels,
                world_buffer=buffer_world,
            )

        # Before continuing, check that the new bounds for the dem cover the original bounds
        adjusted_bounds_polygon = shapely.geometry.box(*adjusted_bounds.bounds)
        bounds_polygon = shapely.geometry.box(*bounds.bounds)
        bounds_filled_by_dem = bounds_polygon.within(adjusted_bounds_polygon)
        print(bounds_polygon.bounds)
        if not bounds_filled_by_dem:
            warn_msg = (
                "The Cop30 DEM bounds do not fully cover the requested bounds. "
                "Try increasing the 'buffer_pixels' value. Note at the antimeridian "
                "This is expected, with bounds being slighly smaller on +ve side. "
                "e.g. max_lon is 179.9999 < 180."
            )
            logging.warning(warn_msg)

        # Adjust bounds further to be at full resolution pixel values
        # This function will expand the requested bounds to produce an integer number of pixels,
        # aligned with the cop glo30 pixel grid, in area-convention (top-left of pixel) coordinates.
        adjusted_bounds, adjusted_bounds_profile = (
            make_empty_cop_glo30_profile_for_bounds(adjusted_bounds)
        )
        print(adjusted_bounds.bounds)
        # Find cop glo30 paths for bounds
        logger.info(f"Finding intersecting DEM files from: {cop30_index_path}")
        dem_paths = find_required_dem_paths_from_index(
            adjusted_bounds, 
            cop30_folder_path=cop30_folder_path,
            dem_index_path=cop30_index_path,
            tifs_in_subfolder=True,
            download_missing=download_dem_tiles,
        )

        # Display dem tiles to the user
        logger.info(f"{len(dem_paths)} tiles found in bounds")
        for p in dem_paths:
            logger.info(p)

        # Produce raster of zeros if no tiles are found
        if len(dem_paths) == 0:
            logger.warning(
                "No DEM tiles found. Assuming that the bounds are over water and creating a DEM containing all zeros."
            )

            dem_profile = adjusted_bounds_profile
            # Construct an array of zeros the same shape as the adjusted bounds profile
            dem_array = 0 * np.ones((dem_profile["height"], dem_profile["width"]))

            if save_path:
                with rasterio.open(save_path, "w", **dem_profile) as dst:
                    dst.write(dem_array, 1)
        # Create and read from VRT if tiles are found
        else:
            logger.info(f"Creating VRT")
            vrt_path = str(save_path).replace(".tif", ".vrt")  # Temporary VRT file path
            logger.info(f"VRT path = {vrt_path}")
            VRT_options = gdal.BuildVRTOptions(
                resolution="highest",
                outputBounds=adjusted_bounds.bounds,
                VRTNodata=0,
            )
            gdal.BuildVRT(vrt_path, dem_paths, options=VRT_options)

            with rasterio.open(vrt_path, "r", count=1) as src:
                dem_array, dem_transform = rasterio.mask.mask(
                    src,
                    [shapely.geometry.box(*adjusted_bounds.bounds)],
                    all_touched=True,
                    crop=True,
                )
                # Using the masking adds an extra dimension from the read
                # Remove this by squeezing before writing
                dem_array = dem_array.squeeze()
                logger.info(f"Dem array shape = {dem_array.shape}")

                dem_profile = src.profile
                dem_profile.update(
                    {
                        "driver": "GTiff",
                        "height": dem_array.shape[0],
                        "width": dem_array.shape[1],
                        "transform": dem_transform,
                        "count": 1,
                        "nodata": np.nan,
                    }
                )

                if save_path:
                    with rasterio.open(save_path, "w", **dem_profile) as dst:
                        dst.write(dem_array, 1)

        if ellipsoid_heights:
            logging.info(
                f"Subtracting the geoid from the DEM to return ellipsoid heights"
            )
            if not download_geoid and not os.path.exists(geoid_tif_path):
                raise FileExistsError(f'Geoid file does not exist: {geoid_tif_path}. '\
                                      'correct path or set download_geoid = True'
                                      )
            elif download_geoid and not os.path.exists(geoid_tif_path):
                logging.info(f'Downloading the egm_08 geoid')
                download_egm_08_geoid_from_aws(geoid_tif_path, bounds=adjusted_bounds.bounds)
            
            logging.info(f"Using geoid file: {geoid_tif_path}")
            dem_array = remove_geoid(
                dem_array=dem_array,
                dem_profile=dem_profile,
                geoid_path=geoid_tif_path,
                buffer_pixels=2,
                save_path=save_path,
            )

        return dem_array, dem_profile


def check_s1_bounds_cross_antimeridian(bounds: BBox, max_scene_width: int = 20) -> bool:
    """Check if the s1 scene bounds cross the antimeridian. The bounds of a sentinel-1
    are valid at the antimeridian, just very large. By setting a max scene width, we
    can determine if the antimeridian is crossed. Alternate scenario is a bounds
    with a very large width (i.e. close to the width of the earth).

    Parameters
    ----------
    bounds : BoundingBox
        the set of bounds (xmin, ymin, xmax, ymax)
    max_scene_width : int, optional
        maximum allowable width of the scene bounds in degrees, by default 20

    Returns
    -------
    bool
        if the bounds cross the antimeridian
    """

    antimeridian_xmin = -180
    bounding_xmin = antimeridian_xmin + max_scene_width  # -160 by default

    antimeridian_xmax = 180
    bounding_xmax = antimeridian_xmax - max_scene_width  # 160 by default

    if (bounds.xmin < bounding_xmin) and (bounds.xmin > antimeridian_xmin):
        if bounds.xmax > bounding_xmax and bounds.xmax < antimeridian_xmax:
            return True
    return False


def get_target_antimeridian_projection(bounds: BoundingBox) -> int:
    """depending where were are on the earth, the desired
    crs at the antimeridian will change. e.g. polar stereo
    is desired at high and low lats, local utm zone elsewhere
    (e.g. at the equator).

    Parameters
    ----------
    bounds : BoundingBox
        The set of bounds (min_lon, min_lat, max_lon, max_lat)

    Returns
    -------
    int
        The CRS in integer form (e.g. 3031 for Polar Stereographic)
    """
    min_lat = min(bounds.ymin, bounds.ymax)
    target_crs = (
        3031
        if min_lat < -50
        else 3995 if min_lat > 50 else get_local_utm(bounds.bounds, antimeridian=True)
    )
    logger.warning(f"Data will be returned in EPSG:{target_crs} projection")
    return target_crs


def split_s1_bounds_at_am_crossing(
    bounds: BBox, lat_buff: float = 0
) -> tuple[BoundingBox]:
    """Split the s1 bounds at the antimeridian, producing one set of bounds for the
    Eastern Hemisphere (left of the antimeridian) and one set for the Western
    Hemisphere (right of the antimeridian)

    Parameters
    ----------
    bounds : BBox (BoundingBox | tuple[float | int, float | int, float | int, float | int])
        The set of bounds (xmin, ymin, xmax, ymax)
    lat_buff : float, optional
        An additional buffer to subract from lat, by default 0.

    Returns
    -------
    tuple[BoundingBox]
        A tuple containing two sets of bounds, one for the Eastern Hemisphere, one for
        the Western Hemisphere.
    """
    if isinstance(bounds, tuple):
        bounds = BoundingBox(*bounds)

    eastern_hemisphere_x = min([x for x in [bounds.xmin, bounds.xmax] if x > 0])
    if eastern_hemisphere_x > 180:
        raise ValueError(
            f"Eastern Hemisphere coordinate of {eastern_hemisphere_x} is more than 180 degrees, but should be less."
        )

    western_hemisphere_x = max([x for x in [bounds.xmin, bounds.xmax] if x < 0])
    if western_hemisphere_x < -180:
        raise ValueError(
            f"Western Hemisphere coordinate of {western_hemisphere_x} is less than -180 degrees, but should be greater."
        )

    min_y = max(-90, bounds.ymin - lat_buff)
    max_y = min(90, bounds.ymax + lat_buff)

    bounds_western_hemisphere = BoundingBox(-180, min_y, western_hemisphere_x, max_y)
    bounds_eastern_hemisphere = BoundingBox(eastern_hemisphere_x, min_y, 180, max_y)

    logger.info(f"Eastern Hemisphere bounds: {bounds_eastern_hemisphere.bounds}")
    logger.info(f"Western Hemisphere bounds: {bounds_western_hemisphere.bounds}")

    return (bounds_eastern_hemisphere, bounds_western_hemisphere)


def adjust_bounds_at_high_lat(bounds: BBox) -> tuple:
    """Expand the bounds for high lattitudes. The
    provided bounds sometimes do not contain the full scene due to
    warping at high latitudes. Solve this by converting bounds to polar
    steriographic, getting bounds, converting back to 4326. At high
    latitudes this will increase the longitude range.

    Parameters
    ----------
    bounds : BBox (BoundingBox | tuple[float | int, float | int, float | int, float | int])
        The set of bounds (min_lon, min_lat, max_lon, max_lat)

    Returns
    -------
    BoundingBox
        The expanded bounds (min_lon, min_lat, max_lon, max_lat)
    """
    if isinstance(bounds, tuple):
        bounds = BoundingBox(*bounds)

    if bounds.ymin < -50:
        logging.info(f"Adjusting bounds at high sourthern latitudes")
        bounds = adjust_bounds(bounds, src_crs=4326, ref_crs=3031)
    if bounds.ymin > 50:
        logging.info(f"Adjusting bounds at high northern latitudes")
        bounds = adjust_bounds(bounds, src_crs=4326, ref_crs=3995)

    return bounds


def find_required_dem_paths_from_index(
    bounds: BBox,
    cop30_folder_path: Path | None,
    dem_index_path=COP30_GPKG_PATH,
    search_buffer=0.3,
    tifs_in_subfolder=True,
    download_missing=False
) -> list[str]:

    if isinstance(bounds, tuple):
        bounds = BoundingBox(*bounds)

    gdf = gpd.read_file(dem_index_path)
    bounding_box = shapely.geometry.box(*bounds.bounds).buffer(search_buffer)

    if gdf.crs is not None:
        # ensure same crs
        bounding_box = (
            gpd.GeoSeries([bounding_box], crs="EPSG:4326").to_crs(gdf.crs).iloc[0]
        )
    # Find rows that intersect with the bounding box
    intersecting_tiles = gdf[gdf.intersects(bounding_box)]
    logger.info(f'Number of cop30 files found intersecting bounds : {len(intersecting_tiles)}')
    if len(intersecting_tiles) == 0:
        # no intersecting tiles
        return []
    else:
        dem_tiles = sorted(intersecting_tiles.location.tolist())
        local_dem_paths = []
        missing_dems = []
        for i,t_filename in enumerate(dem_tiles):
            t_folder = Path(cop30_folder_path) if not tifs_in_subfolder else Path(cop30_folder_path) / Path(t_filename).stem
            t_path = t_folder / t_filename
            t_exists = os.path.exists(t_path)
            local_dem_paths.append(t_path) if t_exists else missing_dems.append(t_path)
        logger.info(f'Local cop30m directory: {cop30_folder_path}')
        logger.info(f'Number of tiles existing locally : {len(local_dem_paths)}')
        logger.info(f'Number of tiles missing locally : {len(missing_dems)}')
        if download_missing and len(missing_dems)>0:
            for t_path in missing_dems:
                download_dem_tile_from_aws(tile_filename=t_path.name, save_folder=t_path.parent)
                local_dem_paths.append(t_path)
        local_dem_paths.append(t_path)
            
    return local_dem_paths
