from datetime import datetime
from pathlib import Path
from pyroSAR import identify

from sar_pipeline.nci.preparation.orbits import find_latest_orbit_covering_window
from sar_pipeline.nci.filesystem import get_orbits_nci, get_dem_nci


def get_orbit_and_dem(
    scene_file: Path,
    dem_output_dir: Path,
    orbit_dir: Path = Path("/g/data/fj7/Copernicus/Sentinel-1/"),
    orbit_type: str | None = "POE",
) -> tuple[Path, Path]:
    """For a given Sentinel-1 scene, find the relevant orbit path and DEM path.
    The DEM will be created if no DEM path is found.

    Parameters
    ----------
    scene_file : Path
        Full path to the scene
        e.g. "path/to/scene/scene_id.zip"
    orbit_type : str, optional
        The orbit type to get. Any of "POE", "RES" or None, by default "POE"

    Returns
    -------
    tuple[Path, Path]
        A tuple containing the path to the orbit file and a path to the DEM file.
        e.g. ("path/to/orbit/orbitfile.EOF", "path/to/dem/demfile.tif")
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

    # Isolate metadata for creating DEM
    scene_bbox = scene.bbox().extent
    scene_bounds = (
        scene_bbox["xmin"],
        scene_bbox["ymin"],
        scene_bbox["xmax"],
        scene_bbox["ymax"],
    )

    # Build DEM
    dem_file = get_dem_nci(scene_file, scene_bounds, dem_output_dir)

    return (orbit_file, dem_file)
