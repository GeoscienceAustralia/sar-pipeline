from pathlib import Path

from sar_antarctica.nci.preparation.orbits import find_orbits


def get_orbits_nci(orbit_type: str | None, sensor: str) -> list[Path]:
    """For a given orbit type and sensor, compile the relevant orbit files

    Parameters
    ----------
    orbit_type : str | None
        One of 'POE', 'RES', or None. If None, both POE and RES orbits will be included
    sensor : str
        Sensor (e.g. S1A or S1B) to search. Typically extracted from the scene ID

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
    S1_DIR = Path("/g/data/fj7/Copernicus/Sentinel-1/")
    POE_DIR = "POEORB"
    RES_DIR = "RESORB"

    if orbit_type == "POE":
        orbit_type_directories = [POE_DIR]
    elif orbit_type == "RES":
        orbit_type_directories = [RES_DIR]
    elif orbit_type is None:
        orbit_type_directories = [RES_DIR, POE_DIR]
    else:
        raise ValueError("orbit_type must be one of 'POE', 'RES', or None")

    nci_orbit_directories = [
        S1_DIR / orbit_dir / sensor for orbit_dir in orbit_type_directories
    ]

    orbits = find_orbits(nci_orbit_directories)

    return orbits
