import os
import logging
from pathlib import Path
from typing import Optional, Union

from sar_pipeline.pipelines.pyrosar_gamma.nci.submission.utils import (
    populate_pbs_template,
)
from sar_pipeline.preparation.downloads.scenes import MissingEnvironmentError

logger = logging.getLogger(__name__)


def submit_job(
    scene: Path,
    spacing: int,
    scaling: str,
    target_crs: str,
    orbit_file: Path,
    etad_dir: Optional[Path],
    output_dir: Path,
    log_dir: Path,
    gamma_lib_dir: Path,
    gamma_env_var: str,
    pbs_parameters: dict[str, str],
    conda_exe: Optional[Union[str, Path]],
    dry_run: bool,
):

    # Create string that will be used to activate the conda environment
    conda_exe = conda_exe or os.getenv("CONDA_EXE")
    if not conda_exe:
        raise MissingEnvironmentError(
            "Path to conda executable is missing. "
            "Please provide the conda_exe argument "
            "or set the CONDA_EXE environment variable."
        )
    conda_exe = Path(conda_exe)
    conda_root_prefix = conda_exe.parent.parent
    conda_shell_script = conda_root_prefix / "etc/profile.d/conda.sh"

    environment_command = (
        "\n"
        f"export CONDA_EXE={conda_exe} \n"
        f"source {conda_shell_script} \n"
        "\n"
        "conda activate sar-pipeline \n"
        "\n"
    )

    # Prepare the pbs script string
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
        str(log_dir),
    )

    # Ensure there is a trailing white space for each line
    job_command = (
        f"nci-pyrosar-gamma-rtc-run-workflow{scene} "
        f"--spacing {spacing} "
        f"--scaling {scaling} "
        f"--target-crs {target_crs} "
        f"--orbit-path {orbit_file} "
        f"--output-dir {output_dir} "
        f"--gamma-lib-dir {gamma_lib_dir} "
        f"--gamma-env-var {gamma_env_var} "
    )
    if etad_dir is not None:
        job_command = job_command + f"--etad-dir {etad_dir} "

    job_script = pbs_script + environment_command + job_command

    # Write updated text to pbs script
    scene_script.write_text(job_script)

    # Submit script
    if dry_run:
        logger.info(f"Script written to {scene_script}, but not submitted")
    else:
        logger.info(f"Submitting script {scene_script}")
        qsub_command = f"qsub {scene_script}"
        os.system(qsub_command)
