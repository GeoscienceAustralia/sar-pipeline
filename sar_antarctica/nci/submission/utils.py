from pathlib import Path


SUBMISSION_DIR = Path(__file__).resolve().parent
SUBMISSION_TEMPLATE = SUBMISSION_DIR / "pbs_template.txt"
STORAGE = "gdata/yp75+gdata/dg9+gdata/fj7+gdata/v10"


def populate_pbs_template(
    ncpu: int,
    mem: int,
    queue: str,
    project: str,
    walltime: str,
    jobname: str,
    log_dir: str,
):
    pbs_template = SUBMISSION_TEMPLATE.read_text()

    replace_dict = {
        "<NCPU>": ncpu,
        "<MEM>": mem,
        "<QUEUE>": queue,
        "<PROJECT>": project,
        "<WALLTIME>": walltime,
        "<STORAGE>": STORAGE,
        "<LOGDIR>": log_dir,
        "<JOBNAME>": jobname,
    }

    for key, value in replace_dict.items():
        pbs_template = pbs_template.replace(
            key, value if isinstance(value, str) else str(value)
        )

    return pbs_template
