import os
from pathlib import Path
from sar_pipeline.nci.submission.utils import populate_pbs_template


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
    pbs_parameters: dict[str, str],
    log_dir: str,
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

    job_command = (
        f"run-pyrosar-gamma-workflow {scene} --spacing {spacing} --scaling {scaling}"
    )

    job_script = pbs_script + ENVIRONMENT_COMMAND + job_command

    # Write updated text to pbs script
    scene_script.write_text(job_script)

    # Submit script
    qsub_command = f"qsub {scene_script}"
    os.system(qsub_command)
