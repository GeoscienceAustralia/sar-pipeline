import click
import os
from pathlib import Path
import tomli
from typing import Any

WORKFLOW = "pyrosar_gamma"
PROCESSING_DIR = "/g/data/yp75/projects/sar-antractica-processing"


def get_list_of_scenes(scene_source: str) -> list[str]:
    """Convert script input to list.
    If a .zip file, produce a list with that.
    If a .txt file, open the file, and produce a list of all .zip files.

    Parameters
    ----------
    scene_source : str
        The file to be processed. Either a single .zip or a .txt containing multiple .zip files

    Returns
    -------
    list[str]
        List of files to process
    """

    # Process a single .zip file
    if scene_source.endswith(".zip"):
        scene_list = [scene_source]
    # Process a .txt file containing .zip files
    elif scene_source.endswith(".txt"):
        with open(scene_source, "r") as f:
            scene_list = [line.strip() for line in f if line.strip().endswith(".zip")]
    else:
        scene_list = []

    if scene_list is not None:
        return scene_list
    else:
        raise RuntimeError(
            "No valid scenes were found for processing. Expected single .zip file or .txt file containing at least one .zip file."
        )


def update_pbs_template(
    pbs_template: str, scene_id: str, job_config: dict[str, str | dict[str, Any]]
) -> str:
    """_summary_

    Parameters
    ----------
    pbs_template : str
        A string containing a PBS jobscript
    scene_id : str
        The scene ID for the job
    job_config : dict[str, str  |  dict[str, Any]]
        Dictionary containing information on the job, main keys are
        root, submission, configuration, and settings

    Returns
    -------
    str
        The updated PBS jobscript string with specified values replaced
    """

    """For a given PBS jobscript template, replace specified values with jobscript settings

    Parameters
    ----------
    pbs_template : str
        A string containing a PBS jobscript
    jobscript_settings: dict


    Returns
    -------
    str
        The updated PBS jobscript string with specified values replaced
    """

    processing_path = Path(job_config["root"])
    log_path = (
        processing_path
        / job_config["submission"]["root"]
        / job_config["submission"]["logs"]
    )
    config_path = processing_path / job_config["configuration"]["root"]

    job_configuration = job_config["configuration"]
    job_settings = job_config["settings"]

    workflow_config = job_settings["workflow_config"]
    # Dictionary to replace placeholders in PBS text with values from configurations
    replace_dict = {
        "<SCENE_ID>": scene_id,
        "<NCPU>": job_settings["ncpu"],
        "<MEM>": job_settings["mem"],
        "<QUEUE>": job_settings["queue"],
        "<PROJECT>": job_settings["project"],
        "<WALLTIME>": job_settings["walltime"],
        "<STORAGE>": job_settings["storage"],
        "<LOG_DIR>": log_path,
        "<WORKFLOW_CONFIG>": config_path
        / job_configuration["workflow"]
        / f"{workflow_config}.toml",
        "<SCENE_CONFIG>": config_path / job_configuration["scene"] / f"{scene_id}.toml",
    }

    for key, value in replace_dict.items():
        pbs_template = pbs_template.replace(
            key, value if isinstance(value, str) else str(value)
        )

    return pbs_template


@click.command()
@click.argument("config_file", nargs=1)
@click.argument("scene_source", nargs=1)
def pyrosar_gamma_workflow(
    config_file: str | os.PathLike, scene_source: str | os.PathLike
) -> None:
    """Take an input of a single scene or file with multiple scenes and submit pyroSAR+GAMMA jobs

    Parameters
    ----------
    processing_dir : str
        The directory to store configuration and jobscript files
    scene_source : str
        The file to be processed. Either a single .zip or a .txt containing multiple .zip files
    """

    current_file_directory = Path(__file__).resolve().parent

    with open(config_file, "rb") as f:
        config = tomli.load(f)

    # Extract specific configuration dictionaries
    job_config = config["job"]
    submission_config = job_config["submission"]
    configuration_config = job_config["configuration"]
    settings_config = job_config["settings"]

    # Get folder structure
    processing_dir = Path(job_config["root"])
    log_dir = processing_dir / submission_config["root"] / submission_config["logs"]

    # Get scenes from source
    scene_list = get_list_of_scenes(scene_source)

    for scene_path in scene_list:
        # Determine scene ID from command line input and create submission script
        scene_id = Path(scene_path).stem
        scene_script = log_dir / scene_id / f"{scene_id}.sh"
        scene_script.parent.mkdir(exist_ok=True, parents=True)

        # Read the workflow template and replace values
        workflow_name = settings_config["workflow_config"]
        template_file = current_file_directory / f"{workflow_name}.txt"
        print(template_file)
        pbs_template = template_file.read_text()
        pbs_template = update_pbs_template(pbs_template, scene_id, job_config)

        # Write updated text to pbs script
        scene_script.write_text(pbs_template)

        # Submit script
        qsub_command = f"qsub {scene_script}"
        os.system(qsub_command)


if __name__ == "__main__":
    pyrosar_gamma_workflow()
