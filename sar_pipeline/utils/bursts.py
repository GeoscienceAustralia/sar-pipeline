import click
import logging
from pathlib import Path
import shapely


from sar_pipeline.preparation.downloads.scenes import (
    query_scene_from_cdse,
    query_scene_from_asf,
    NonSingleSceneResultError,
)
from sar_pipeline.pipelines.isce3_rtc.utils.burst_utils import (
    get_burst_info_for_scene_from_cdse,
)

from sar_pipeline.utils.spatial import (
    write_burst_geometries_to_geojson,
)
from sar_pipeline.utils.antimeridian import (
    check_shape_crosses_antimeridian,
    get_bounds_for_antimeridian_shape,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def find_burst_ids_for_scene(
    scene,
    save_geometries,
):
    """Retrieve all burst IDs associated with a given Sentinel‑1 scene by querying CDSE,
    falling back to ASF when needed, and inspecting the scene’s spatial footprint,
    including special handling for antimeridian‑crossing geometries. The function logs
    scene metadata, lists all bursts returned by the CDSE burst‑info API, and optionally
    saves the burst geometries to a GeoJSON file for diagnostic or visualisation purposes.
    """

    logger.info(f"Finding burst ids for scene : {scene}")

    try:
        # Query the CDSE to make sure the scene exists
        logger.info(f"Searching CDSE for scene metadata : {scene}")
        scene_results, metadata_src = (
            query_scene_from_cdse(scene, expand_attributes=True),
            "CDSE",
        )
    except Exception as e:
        # Fallback to ASF
        logger.error(f"CDSE Query failed. Error : {e}")
        logger.info(f"Falling back to ASF search for scene metadata : {scene}")
        logger.warning(f"ASF may not have the most recent data available from the CDSE")
        scene_results, metadata_src = query_scene_from_asf(scene), "ASF"

    if len(scene_results) != 1:
        raise NonSingleSceneResultError(
            f"Expected 1 scene, found {len(scene_results)} results for scene id : {scene}. Check input scene."
        )
    else:
        logger.info(f"Scene metadata successfully retrieved from {metadata_src}")
        scene_metadata = scene_results[0]
        if metadata_src == "CDSE":
            scene_polygon = shapely.geometry.shape(scene_metadata["GeoFootprint"])
        elif metadata_src == "ASF":
            scene_polygon = shapely.geometry.shape(scene_metadata.geometry)

        else:
            raise ValueError(
                f"metadata_src: {metadata_src} not recognised, should be either CDSE or ASF"
            )
        # show the original scene shape and bounds
        logger.info(f"The original scene shape is : {scene_polygon}")
        logger.info(f"The original scene bounds are : {scene_polygon.bounds}")

    if check_shape_crosses_antimeridian(scene_polygon):
        logger.warning("The scene crosses the antimeridian")
        # use the full scene bounds for an antimeridian scene
        scene_bounds = get_bounds_for_antimeridian_shape(scene_polygon)
        logger.info(
            f"Getting the corrected scene bounds crossing the antimeridian : {scene_bounds}"
        )

    # The burst ids, times and geometries can be acquired from the CDSE.
    # We can therefore check if desired products already exist before needing to download the scene
    logger.info(f"Querying CDSE for scene burst ids and metadata")
    all_scene_burst_info = get_burst_info_for_scene_from_cdse(scene)
    fnd_str = f"{len(all_scene_burst_info)} burst ids found for scene from CDSE API:"
    logger.info(f"{fnd_str}\n" + "\n".join(list(sorted(all_scene_burst_info.keys()))))

    # write the geometries to a geojson. Useful for debugging if needed
    if save_geometries:
        logger.info(
            f"Saving burst geometries to : {save_geometries}/{scene}_burst_geoms.json"
        )
        _burst_id_list = all_scene_burst_info.keys()
        _burst_geoms_list = [
            all_scene_burst_info[b]["geometry"] for b in _burst_id_list
        ]
        write_burst_geometries_to_geojson(
            _burst_id_list,
            _burst_geoms_list,
            save_geometries / f"{scene}_burst_geoms.json",
        )
    else:
        logger.info(
            "To save burst geometries to a file pass --save-geometries <FOLDER_PATH>"
        )
