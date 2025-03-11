# AWS Pipeline

## Overview
The AWS pipeline runs using a docker container. At runtime, the script `scripts/run_aws_pipeline.sh` is run. The arguments that can be passed to the container are:

```bash
--scene="" (required)
--base_rtc_config="" (required)
--dem="cop_glo30"
--s3_bucket="deant-data-public-dev"
--s3_project_folder="experimental/s1_rtc_c1"
```
- `scene` -> A valid sentinel-1 IW scene (e.g. S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD)
- `base_rtc_config` -> the base RTC/OPERA config for generating the products. Options can be found in `sar_pipeline/configs/ISCE3-RTC`
- `dem` -> The dem to be used in processing. Supported is `cop_glo30`.
- `s3_bucket` -> the bucket to upload the products
- `s3_project_folder` -> The project folder to upload to. Note a unique subpath is appended to this in the pipeline

## Envrionment Variables

At runtime, the pipeline expects the following environment variables to be set. These can be passed in using an environment file like below. NASA earthdata credentials can be created here - https://urs.earthdata.nasa.gov/. The AWS credentials must have write access to the specified bucket location.

env.secret:

```txt
EARTHDATA_LOGIN=
EARTHDATA_PASSWORD=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_DEFAULT_REGION=
```

## Write / processing location

The location for where data is downloaded and written for processing in the container is specified in the `scripts/run_aws_pipeline.sh` file. In the case of AWS processing, an EBS block may be mounted. The mount point must align to the paths specified in the run script for the EBS storage to be used. The values are:

```bash
# set process folders for the container
download_folder="/home/rtc_user/working/downloads"
out_folder="/home/rtc_user/working/results/$scene"
scratch_folder="/home/rtc_user/working/scratch/$scene"
```


## Build the docker image

```bash
docker build -t sar-pipeline -f Docker/Dockerfile .
```

### Test image interactively

```bash
 docker run -it --entrypoint /bin/bash sar-pipeline
```

## Run a scene

```bash
docker run --env-file env.secret -it sar-pipeline --scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD --base_rtc_config IW_20m_antarctica.yaml
```

## Development in the Container

Development within container

```bash

# Start the container interactively and mount folders in the container so changes can be picked up

docker run --env-file env.secret -it --entrypoint /bin/bash -v $(pwd):/home/rtc_user/sar-pipeline -v $(pwd)/scripts:/home/rtc_user/scripts -v /data/working:/home/rtc_user/working sar-pipeline

# activate environment and install code in editable mode

conda activate sar-pipeline

pip install -e /home/rtc_user/sar-pipeline

# run the pipeline script

chmod +x /home/rtc_user/scripts/run_aws_pipeline.sh 

/home/rtc_user/scripts/run_aws_pipeline.sh --scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD --base_rtc_config IW_20m_antarctica.yaml

```

Mount files at runtime

```bash
docker run --env-file env.secret -v $(pwd)/scripts:/home/rtc_user/scripts -v /data/working:/home/rtc_user/working sar-pipeline --scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD --base_rtc_config IW_20m_antarctica.yaml

```