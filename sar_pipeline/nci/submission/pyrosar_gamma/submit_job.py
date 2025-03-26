import os
import logging
from pathlib import Path

from sar_pipeline.nci.submission.utils import populate_pbs_template

logger = logging.getLogger(__name__)

ENVIRONMENT_COMMAND = """

export MAMBA_EXE=/g/data/yp75/ca6983/micromamba/bin/micromamba
export MAMBA_ROOT_PREFIX=/g/data/yp75/ca6983/micromamba
source $MAMBA_ROOT_PREFIX/etc/profile.d/mamba.sh

micromamba activate sar-pipeline

"""


def submit_job(
    scene: Path,
    spacing: int,
    scaling: str,
    target_crs: str,
    orbit_dir: Path,
    orbit_type: str,
    etad_dir: Path,
    output_dir: Path,
    log_dir: str,
    gamma_lib_dir: Path,
    gamma_env_var: str,
    pbs_parameters: dict[str, str],
    dry_run: bool,
):

    scene_name = scene.stem

    scene_script = log_dir / scene_name / f"{scene_name}.sh"
    scene_script.parent.mkdir(exist_ok=True, parents=True)

    pbs_script = populate_pbs_template(
        pbs_parameters["ncpu"],
        pbs_parameters["mem"],
        pbs_parameters["queue"],
        pbs_parameters["project"],
        pbs_parameters["walltime"],
        scene_name,
        log_dir,
    )

    # Ensure there is a trailing white space for each line
    job_command = (
        f"run-pyrosar-gamma-workflow {scene} "
        f"--spacing {spacing} "
        f"--scaling {scaling} "
        f"--target-crs {target_crs} "
        f"--orbit_dir {orbit_dir} "
        f"--orbit-type {orbit_type} "
        f"--etad-dir {etad_dir} "
        f"--output-dir {output_dir} "
        f"--gamma-lib-dir {gamma_lib_dir} "
        f"--gamma-env-var {gamma_env_var} "
    )

    job_script = pbs_script + ENVIRONMENT_COMMAND + job_command

    # Write updated text to pbs script
    scene_script.write_text(job_script)

    # Submit script
    if dry_run:
        logger.info(f"Script written to {scene_script}, but not submitted")
    else:
        logger.info(f"Submitting script {scene_script}")
        qsub_command = f"qsub {scene_script}"
        os.system(qsub_command)
