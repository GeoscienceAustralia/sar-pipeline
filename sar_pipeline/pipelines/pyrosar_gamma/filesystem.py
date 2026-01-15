from pathlib import Path
import logging

from dem_handler.dem.cop_glo30 import get_cop30_dem_for_bounds

logging.basicConfig(level=logging.INFO)


def get_orbits_nci(
    orbit_type: str | None,
    sensor: str,
    nci_orbit_dir: Path = Path("/g/data/fj7/Copernicus/Sentinel-1/"),
) -> list[Path]:
    """For a given orbit type and sensor, compile the relevant orbit files

    Parameters
    ----------
    orbit_type : str | None
        One of 'POE', 'RES', or "either". If "either", both POE and RES orbits will be included
    sensor : str
        Sensor (e.g. S1A or S1B) to search. Typically extracted from the scene ID
    nci_orbit_dir : Path, optional
        The path containing orbit files on the NCI, by default Path("/g/data/fj7/Copernicus/Sentinel-1/")
    Returns
    -------
    list[Path]
        List of orbit files on NCI matching search criteria

    Raises
    ------
    ValueError
        Invalid orbit type. Must be one of 'POE', 'RES' or None
    """

    # Constants for NCI
    POE_DIR = "POEORB"
    RES_DIR = "RESORB"

    if orbit_type == "POE":
        orbit_type_directories = [POE_DIR]
    elif orbit_type == "RES":
        orbit_type_directories = [RES_DIR]
    elif orbit_type == "either":
        orbit_type_directories = [RES_DIR, POE_DIR]
    else:
        raise ValueError("orbit_type must be one of 'POE', 'RES', or either")

    nci_orbit_directories = [
        nci_orbit_dir / orbit_dir / sensor for orbit_dir in orbit_type_directories
    ]

    logging.info(nci_orbit_directories)

    matching_files = []
    extension = ".EOF"
    for directory in nci_orbit_directories:
        if directory.is_dir():
            matching_files.extend(directory.glob(f"*{extension}"))

    return matching_files


def get_dem_nci(
    scene: Path,
    scene_bounds: tuple[float, float, float, float],
    output_dir: Path,
    nci_dem_dir: Path = Path(
        "/g/data/v10/eoancillarydata-2/elevation/copernicus_30m_world/"
    ),
    nci_geoid: Path = Path(
        "/g/data/yp75/projects/ancillary/geoid/us_nga_egm2008_1_4326__agisoft.tif"
    ),
) -> Path:
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
    dem_file = output_dir / f"{scene.stem}.tif"

    if not dem_file.exists():
        _, _, _ = get_cop30_dem_for_bounds(
            scene_bounds,
            dem_file,
            ellipsoid_heights=True,
            adjust_at_high_lat=True,
            buffer_pixels=10,
            cop30_folder_path=nci_dem_dir,
            geoid_tif_path=nci_geoid,
        )

    return dem_file
