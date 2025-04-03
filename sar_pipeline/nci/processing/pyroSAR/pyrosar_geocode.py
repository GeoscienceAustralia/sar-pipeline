import click
import logging
from pathlib import Path
from pyroSAR import identify
from pyroSAR.gamma import geocode
from pyroSAR.gamma.dem import dem_import
import shutil
import sys
import tarfile
import zipfile

from sar_pipeline.preparation.etad import apply_etad_correction
from sar_pipeline.nci.processing.GAMMA.GAMMA_utils import set_gamma_env_variables

logging.basicConfig(
    format="%(asctime)s | %(levelname)s : %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


def prepare_directories(processing_root: Path, scene_full_name: str, scene_outname):

    # Set directories under the processing root
    SCENE_DIR = f"data/processed_scene/{scene_full_name}"
    TEMP_DIR = f"data/temp/{scene_outname}"
    LOG_DIR = f"data/temp/{scene_outname}/logfiles"

    # Construct a dictionary for use
    processing_directories = {
        "scene": processing_root / SCENE_DIR,
        "temp": processing_root / TEMP_DIR,
        "logs": processing_root / LOG_DIR,
    }

    # Create directories if not exist
    log.info("Setting directories:")
    for dir_name, dir_path in processing_directories.items():
        log.info(f"    {dir_name}: {dir_path}")
        dir_path.mkdir(parents=True, exist_ok=True)

    return processing_directories


def prepare_dem_for_gamma(dem_tif: Path, temp_dir: Path, log_dir: Path) -> Path:

    dem_dir = dem_tif.parent
    dem_name = dem_tif.stem
    dem_gamma = temp_dir / dem_name

    if dem_gamma.exists():
        log.info("DEM exists")
    else:
        log.info("running DEM")

        dem_import(
            src=str(dem_tif),
            dst=str(dem_gamma),
            geoid=None,
            logpath=str(log_dir),
            outdir=str(dem_dir),
        )

        log.info("finished DEM")

    return dem_gamma


def run_pyrosar_gamma_geocode(
    scene: Path,
    orbit: Path,
    dem: Path,
    output: Path,
    gamma_library: Path,
    gamma_env: str,
    geocode_spacing: int,
    geocode_scaling: str,
    etad: Path | None = None,
) -> Path:
    """
    Returns
    -------
    Path
        Path to the output files
    """

    # Set up environment variables for GAMMA
    set_gamma_env_variables(str(gamma_library), gamma_env)

    # Identify scene
    scene_name = scene.stem
    pyrosar_scene_id = identify(scene)

    # Create processing directories if required
    processing_directories = prepare_directories(
        output, scene_name, pyrosar_scene_id.outname_base(extensions=None)
    )

    # Unpack the scene into the temporary directory
    if pyrosar_scene_id.compression is not None:
        pyrosar_scene_id.unpack(
            directory=str(processing_directories["temp"]), exist_ok=False
        )

    # Apply ETAD file if provided
    if etad is not None:
        if pyrosar_scene_id.product == "SLC":
            log.info("Correcting SLC with ETAD product.")

            # Set up required paths
            uncorrected_scene = Path(pyrosar_scene_id.scene)
            uncorrected_scene_dir = uncorrected_scene.parent
            corrected_scene_dir = uncorrected_scene.parent / "etad_corrected"

            if not (etad.is_dir() and etad.suffix == ".SAFE"):
                logging.info("Atte")
                if zipfile.is_zipfile(etad):
                    archive = tarfile.open(etad, "r")
                elif tarfile.is_tarfile(etad):
                    archive = zipfile.ZipFile(etad, "r")
                else:
                    raise RuntimeError(
                        f"ETAD file must be one of .SAFE, .zip, or .tar. Supplied ETAD file: {etad}"
                    )
                archive.extractall(uncorrected_scene_dir)
                archive.close()

                # Update variable to use extracted etad
                etad = uncorrected_scene_dir / etad.name.with_suffix(".SAFE")

            corrected_scene = apply_etad_correction(
                uncorrected_scene, etad, outdir=corrected_scene_dir, nthreads=4
            )

            # Update pyrosar scene to point at the corrected file
            pyrosar_scene_id = identify(corrected_scene)

        else:
            log.warning(
                f"ETAD can only be applied to SLC, but a {pyrosar_scene_id.product} has been provided. ETAD correction will be skipped."
            )

    # Prepare orbit file
    # Copy to temp dir to prevent pyroSAR modifying in-place
    orbit_dir = processing_directories["temp"]
    shutil.copy(orbit, orbit_dir / orbit.name)

    dem_gamma = prepare_dem_for_gamma(
        dem, processing_directories["temp"], processing_directories["logs"]
    )

    log.info("running geocode")

    # Set the border removal step to pyroSAR for GRD products. Ignore otherwise
    if pyrosar_scene_id.product == "GRD":
        border_removal_method = "pyroSAR"
    else:
        border_removal_method = None

    # If both linear and db scaling requested, construct the appropriate input for geocode
    if geocode_scaling == "both":
        geocode_scaling = ["linear", "db"]

    geocode(
        scene=pyrosar_scene_id,
        dem=str(dem_gamma),
        tmpdir=str(processing_directories["temp"]),
        outdir=str(processing_directories["scene"]),
        spacing=geocode_spacing,
        scaling=geocode_scaling,
        func_geoback=1,
        nodata=(0, -99),
        update_osv=False,
        osvdir=str(orbit_dir),
        allow_RES_OSV=False,
        cleanup=False,
        export_extra=[
            "inc_geo",
            "dem_seg_geo",
            "ls_map_geo",
            "pix_area_gamma0_geo",
            "pix_ratio_geo",
        ],
        basename_extensions=None,
        removeS1BorderNoiseMethod=border_removal_method,
        refine_lut=False,
        rlks=None,
        azlks=None,
        s1_osv_url_option=1,
    )

    log.info("finished geocode")

    return processing_directories["scene"]
