from datetime import datetime
from pathlib import Path
from pyroSAR import identify
import shapely
from shapely.geometry import MultiPolygon
import logging

from sar_pipeline.preparation.nci.orbits import find_latest_orbit_covering_window
from sar_pipeline.pipelines.pyrosar_gamma.filesystem import get_orbits_nci, get_dem_nci
from sar_pipeline.utils.antimeridian import (
    check_shape_crosses_antimeridian,
    get_bounds_for_antimeridian_shape,
)

logging.basicConfig(level=logging.INFO)


def get_orbit_and_dem(
    scene_file: Path,
    dem_output_dir: Path,
    orbit_dir: Path = Path("/g/data/fj7/Copernicus/Sentinel-1/"),
    orbit_type: str | None = "POE",
    dem_dir: Path = Path(
        "/g/data/v10/eoancillarydata-2/elevation/copernicus_30m_world/"
    ),
    check_scene_likely_crosses_antimeridian: bool = True,
) -> tuple[Path, Path]:
    """For a given Sentinel-1 scene, find the relevant orbit path and DEM path.
    The DEM will be created if no DEM path is found.

    Parameters
    ----------
    scene_file : Path
        Full path to the scene
        e.g. "path/to/scene/scene_id.zip"
    orbit_dir : Path, optional
        Path to orbit files
        Set to default for NCI: /g/data/fj7/Copernicus/Sentinel-1/
    orbit_type : str, optional
        The orbit type to get. Any of "POE", "RES" or None, by default "POE"
            orbit_dir : Path, optional
    Path to dem files
        Set to default for NCI: /g/data/v10/eoancillarydata-2/elevation/copernicus_30m_world/
    check_scene_likely_crosses_antimeridian : bool, optional
        Check if the scene geometry likely crosses the antimeridian and get the correct
        geometry and bounds from the provided scene geometry.

    Returns
    -------
    tuple[Path, Path]
        A tuple containing the path to the orbit file and a path to the DEM file.
        e.g. ("path/to/orbit/orbit_file.EOF", "path/to/dem/dem_file.tif")
    """

    # Extract metadata
    scene = identify(scene_file)

    # Isolate metadata for finding orbit
    scene_sensor = scene.sensor
    scene_start = datetime.strptime(scene.start, "%Y%m%dT%H%M%S")
    scene_stop = datetime.strptime(scene.stop, "%Y%m%dT%H%M%S")

    # Find orbit
    orbit_files = get_orbits_nci(orbit_type, scene_sensor, orbit_dir)
    orbit_file = find_latest_orbit_covering_window(orbit_files, scene_start, scene_stop)

    # Check if the scene likely crosses the antimeridian
    if check_scene_likely_crosses_antimeridian:
        # get the geometry from the spatialist Vector
        scene_vector = scene.geometry()  # this is a spatialist.Vector

        # list of all features as 2D polygons
        geoms = [
            shapely.wkt.loads(wkt_str)
            for wkt_str in scene_vector.convert2wkt(set3D=False)
        ]

        # combine into a single MultiPolygon if multiple
        if len(geoms) == 1:
            scene_geometry = geoms[0]
        else:
            scene_geometry = MultiPolygon(
                [g if g.geom_type == "Polygon" else list(g.geoms)[0] for g in geoms]
            )

        scene_crosses_antimeridian = check_shape_crosses_antimeridian(scene_geometry)
    else:
        scene_crosses_antimeridian = False  # skip check

    if scene_crosses_antimeridian:
        logging.warning("Scene crosses antimeridian")
        scene_bounds = get_bounds_for_antimeridian_shape(scene_geometry)
    if not scene_crosses_antimeridian:
        # Isolate metadata for creating DEM
        scene_bbox = scene.bbox().extent  # type: ignore
        scene_bounds = (
            scene_bbox["xmin"],
            scene_bbox["ymin"],
            scene_bbox["xmax"],
            scene_bbox["ymax"],
        )

    # Build DEM
    dem_file = get_dem_nci(scene_file, scene_bounds, dem_output_dir, dem_dir)

    return (orbit_file, dem_file)
