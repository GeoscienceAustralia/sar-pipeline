import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from pathlib import Path
import pandas as pd
import os

# Directories
CURRENT_DIR = Path(__file__).parent.resolve()
LOCAL_TEST_OUTPUTS_DIR = f"/data/working"

DOCKER_TAG = "rema-timeseries"

# Log directory
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

REQUIRED_ENV_VARIABLES = [
    "EARTHDATA_LOGIN",
    "EARTHDATA_PASSWORD",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "CDSE_LOGIN",
    "CDSE_PASSWORD",
    "AUS_COP_HUB_LOGIN",
    "AUS_COP_HUB_PASSWORD",
    "AUS_COP_HUB_CLIENT_ID",
    "AUS_COP_HUB_CLIENT_SECRET",
]
# optional env variables to be passed to docker run if existing
OPTIONAL_ENV_VARIABLES = [
    "AWS_SESSION_TOKEN",
    "AWS_CREDENTIAL_EXPIRATION",
    "AWS_SESSION_EXPIRATION",
    "REMA_AWS_ACCESS_KEY_ID",
    "REMA_AWS_SECRET_ACCESS_KEY",
]

# load env vars
loaded_status = load_dotenv(".env")

# set the environment variables as string for docker
# missing optional vars will not be added
ENV_VARS = []
for var in REQUIRED_ENV_VARIABLES + OPTIONAL_ENV_VARIABLES:
    if os.getenv(var):
        ENV_VARS.append("-e")
        ENV_VARS.append(f"{var}={os.getenv(var)}")

def run_job(name, row):
    """Run a single Docker job and write logs."""
    log_file = log_dir / f"{name}.log"
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Starting {name} (param={row}) → {log_file}")
    with log_file.open("w") as lf:
        cmd = [
            "docker",
            "run",
            "-v",
            f"{LOCAL_TEST_OUTPUTS_DIR}:/home/rtc_user/working",
            "--rm",
            *ENV_VARS,
            f"sar-pipeline:{DOCKER_TAG}",
            "--scene",
            row.scene,
            "--burst_id_list",
            row.bursts,
            "--product",
            "RTC_S1",
            "--dem_type",
            row.dem_type,
            "--backscatter_convention",
            "gamma0",
            "--collection_number",
            "0",
            "--s3_bucket",
            "deant-data-public-dev",
            "--s3_project_folder",
            row.s3_folder,
            "--skip_validate_stac"
        ]
        process = subprocess.run(
            cmd,
            stdout=lf,
            stderr=subprocess.STDOUT,
            text=True,
        )
    return name, process.returncode

success = []
failed = []

df_run = pd.read_csv('rema-timeseries-runs.csv')
print(df_run.scene)

# Max number of concurrent jobs
MAX_WORKERS = 10

# Run jobs concurrently with a limit
with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    #futures = {executor.submit(run_job, name, param): name for name, param in jobs}
    futures = {executor.submit(run_job, row.scene, row): row.scene for row in df_run.itertuples(index=False)}

    for future in as_completed(futures):
        name, code = future.result()
        if code == 0:
            success.append(name)
            status = 'SUCCESS'
            print(f'Job Successful : {name}')
        else: 
            failed.append(name)
            print(f'Job Failed : {name}')
            status = 'FAILED'
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {name} finished ({status})")

print(f'{len(success)} jobs succeeded:')
for s in success:
    print(s)
print(f'{len(failed)} jobs failed:')
for s in failed:
    print(s)