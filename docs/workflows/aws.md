# AWS Pipeline

## About 

The AWS sar-pipeline can be used to create two products using the OPERA ISCE3 based workflows. These are:
- **RTC_S1** -> Sentinel-1 Radiometrically Terrain Corrected (RTC) Backscatter [(Specification doc)](https://d2pn8kiwq2w21t.cloudfront.net/documents/ProductSpec_RTC-S1-STATIC.pdf)
- **RTC_S1_STATIC** -> Sentinel-1 Radiometrically Terrain Corrected (RTC) Backscatter [(Specification doc)](https://d2pn8kiwq2w21t.cloudfront.net/documents/ProductSpec_RTC-S1.pdf)

**RTC_S1** products are unique to each acquisition. **RTC_S1_STATIC** products are ancillary layers that can be shared across the same burst_id.


The **RTC_S1** pipeline must be run for every new scene acquired by Sentinel-1. The **RTC_S1_STATIC** product only needs to be run a single time to create static layers that are fixed for each burst. These layers will need to be recreated only if the acquisition scenario or DEM changes. OR if the area of interest for the DE-Australia and DE-Antarctica project changes. Examples of static layers include `local_incidence_angles` and `digital_elevation_models`. Given the highly stable orbital tube of sentinel-1, these layers can be considered STATIC for a given burst.

The static layers can be re-used across a given burst_id, saving the storage required if they were created with each acquisition. For example, every 12 days sentinel 1A will capture the burst `t070_149815_iw3`. The same `local_incidence_angles.tif` can be used for each repeat pass, only the dialectic properties of the surface will change over time. The static layer is therefore referenced in a given **RTC_S1** product STAC metadata.

TODO: Ensure this is how products are structured 

After each run is completed, the files will be uploaded to a specified S3 bucket location. A unique subpath for each product is created in the workflow.

## Examples

Example outputs of the **RTC_S1** and **RTC_S1_STATIC** workflows can be found here:
- **RTC_S1** -> https://deant-data-public-dev.s3.ap-southeast-2.amazonaws.com/index.html?prefix=experimental/s1_rtc_c1/2022/1/1/t070_149815_iw3/
- **RTC_S1_STATIC** -> https://deant-data-public-dev.s3.ap-southeast-2.amazonaws.com/index.html?prefix=experimental/s1_rtc_static_c1/t070_149815_iw3/ 


## Pipeline Overview
The AWS pipeline runs using a docker container. At runtime, the script `scripts/run_aws_pipeline.sh` is run. The arguments that can be passed to the container are:

```bash
--scene="" (required)
--burst_id_list=()
--resolution=20
--output_crs=""
--dem="cop_glo30"
--product="RTC_S1"
--collection="s1_rtc_c1"
--s3_bucket="deant-data-public-dev"
--s3_project_folder="experimental"
```
- `scene` -> A valid sentinel-1 IW scene (e.g. S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD)
- `burst_id_list` -> A list of burst id's corresponding to the scene. If not provided, all will be processed. Can be space separated list or line separated .txt file.
- `resolution` -> The target resolution of the products. Default is 20m.
- `output_crs` -> The target crs of the products. If not specified, the UTM of the scene center will be used. Expects integer values (e.g. 3031)
- `dem` -> The dem to be used in processing. Supported is `cop_glo30`.
- `product` -> The product being created with the workflow. Must be `RTC_S1` or `RTC_S1_STATIC`.
- `collection` -> The collection which the set of products belongs.
- `s3_bucket` -> the bucket to upload the products
- `s3_project_folder` -> The project folder to upload to. Final 
    - **RTC_S1** -> final path will be `s3_bucket/s3_project_folder/collection/burst_year/burst_month/burst_day/burst_id/*files*`
    - **RTC_S1_STATIC** -> final path will be `s3_bucket/s3_project_folder/collection/burst_id/*files*`

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

# Runing the workflow

## RTC_S1 - Sentinel-1 Radiometrically Terrain Corrected (RTC) Backscatter

### Antarctica

Output CRS should be polar stereographic 3031

```bash
docker run --env-file env.secret -it sar-pipeline --scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD --output_crs 3031
```

For a single burst:

```bash
docker run --env-file env.secret -it sar-pipeline --scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD --output_crs 3031 --burst_id_list t070_149815_iw3
```

### Australia

The output CRS will be the UTM zone corresponding to scene/burst centre. This is selected automatically and does not need to be specified.

```bash
docker run --env-file env.secret -it sar-pipeline --scene S1A_IW_SLC__1SDV_20220130T191354_20220130T191421_041694_04F5F9_1AFD 
```

## RTC_S1_STATIC - Static Layers for Sentinel-1 Radiometrically Terrain Corrected (RTC) Backscatter


```bash
docker run --env-file env.secret -it sar-pipeline --scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD --output_crs 3031 --product RTC_S1_STATIC --collection s1_rtc_static_c1 --s3_project_folder "experimental"
```


## Development in the Container

Development is best done from within the container where edited files are tracked and can be run without a new installation. To do this, the sar-pipeline project and run scripts must be mounted at the appropriate location within the container.

```bash
# Start the container interactively and mount folders in the container so changes can be picked up
# Here the /data/working volume is being mounted to the working directory of the container

docker run --env-file env.secret -it --entrypoint /bin/bash -v $(pwd):/home/rtc_user/sar-pipeline -v $(pwd)/scripts:/home/rtc_user/scripts -v /data/working:/home/rtc_user/working sar-pipeline

# activate environment and install code in editable mode

conda activate sar-pipeline

pip install -e /home/rtc_user/sar-pipeline

# run the pipeline script

chmod +x /home/rtc_user/scripts/run_aws_pipeline.sh 

# Antarctic scene (all bursts)

/home/rtc_user/scripts/run_aws_pipeline.sh --scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD --output_crs 3031

# Antarctic scene (single burst)

/home/rtc_user/scripts/run_aws_pipeline.sh --scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD --output_crs 3031 --burst_id_list t070_149815_iw3

# Australia scene

/home/rtc_user/scripts/run_aws_pipeline.sh --scene S1A_IW_SLC__1SDV_20220130T191354_20220130T191421_041694_04F5F9_1AFD

# Antarctica static layers

/home/rtc_user/scripts/run_aws_pipeline.sh --scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD --output_crs 3031 --product RTC_S1_STATIC --collection s1_rtc_static_c1 --s3_project_folder "experimental"


```

### Mount files at runtime

```bash
docker run --env-file env.secret -v $(pwd)/scripts:/home/rtc_user/scripts -v /data/working:/home/rtc_user/working sar-pipeline --scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD --output_crs 3031

```

