import click
import os
from pathlib import Path

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
        with open(scene_source, 'r') as f:
            scene_list = [line.strip() for line in f if line.strip().endswith('.zip')]
    else:
        scene_list = []

    if scene_list is not None:
        return scene_list
    else:
        raise RuntimeError("No valid scenes were found for processing. Expected single .zip file or .txt file containing at least one .zip file.")

def update_pbs_template(pbs_template: str, processing_dir: str, scene_id: str, workflow_id: str, ncpu: int=4, mem:int=32) -> str:
    """For a given PBS jobscript template, replace specified values

    Parameters
    ----------
    pbs_template : str
        A string containing a PBS jobscript
    processing_dir : str
        The directory to store configuration and jobscript files
    scene_id : str
        The scene id, used to name the scene configuration file
    workflow_id : str
        The name of the workflow, used to name the workflow configuration fie
    ncpu : int, optional
        The number of CPU to use in the jobscript, by default 4
    mem : int, optional
        The amount of memory (in GB) to use in the jobscript, by default 32

    Returns
    -------
    str
        The updated PBS jobscript string with specified values replaced
    """
    # Replace PBS Resource variables
    
    pbs_template = pbs_template.replace("<NCPU>", str(ncpu))
    pbs_template = pbs_template.replace("<MEM>", str(mem))
    pbs_template = pbs_template.replace("<PROCESSING_DIR>", processing_dir)
    pbs_template = pbs_template.replace("<SCENE_ID>", scene_id)
    pbs_template = pbs_template.replace("<WORKFLOW_CONFIG>", f"{processing_dir}/config/workflow_config/{workflow_id}.toml")
    pbs_template = pbs_template.replace("<SCENE_CONFIG>", f"{processing_dir}/config/scene_config/{scene_id}.toml")

    return pbs_template


@click.command()
@click.argument("processing_dir", nargs=1)
@click.argument("scene_source", nargs=1)
def pyrosar_gamma_workflow(processing_dir:str , scene_source: str) -> None:
    """Take an input of a single scene or file with multiple scenes and submit pyroSAR+GAMMA jobs

    Parameters
    ----------
    processing_dir : str
        The directory to store configuration and jobscript files
    scene_source : str
        The file to be processed. Either a single .zip or a .txt containing multiple .zip files
    """

    # Get folder structure
    submission_dir = Path(processing_dir) / "submission"
    log_dir = submission_dir / "logs"

    scene_list = get_list_of_scenes(scene_source)

    for scene_path in scene_list:
        # Determine scene ID from command line input and create submission script
        scene_id = Path(scene_path).stem
        scene_script = log_dir / scene_id / f"{scene_id}.sh"
        scene_script.parent.mkdir(exist_ok=True, parents=True)

        # Read the workflow template and replace values
        template_file = Path(f"{WORKFLOW}.txt")
        pbs_template = template_file.read_text()
        pbs_template = update_pbs_template(
            pbs_template, 
            processing_dir, 
            scene_id, 
            WORKFLOW, 
            ncpu=4, 
            mem=64)

        # Write updated text to pbs script
        scene_script.write_text(pbs_template)

        # Submit script
        qsub_command = f"qsub {scene_script}"
        print(qsub_command)
        #os.system(qsub_command)


if __name__ == "__main__":
    pyrosar_gamma_workflow()