# AWS Pipeline

- [AWS Pipeline](#aws-pipeline)
  - [About](#about)
    - [Example outputs](#example-outputs)
  - [Pipeline Overview](#pipeline-overview)
    - [Creating Products](#creating-products)
  - [Environment Variables](#environment-variables)
  - [Container processing location](#container-processing-location)
- [Build the docker image](#build-the-docker-image)
  - [Test image interactively](#test-image-interactively)
- [Running the workflow](#running-the-workflow)
  - [RTC\_S1 - Sentinel-1 Radiometrically Terrain Corrected (RTC) Backscatter](#rtc_s1---sentinel-1-radiometrically-terrain-corrected-rtc-backscatter)
    - [Antarctica (without linking RTC\_S1\_STATIC)](#antarctica-without-linking-rtc_s1_static)
  - [RTC\_S1\_STATIC - Static Layers for Sentinel-1 Radiometrically Terrain Corrected (RTC) Backscatter](#rtc_s1_static---static-layers-for-sentinel-1-radiometrically-terrain-corrected-rtc-backscatter)
- [Examples](#examples)
  - [Make static layers (RTC\_S1\_STATIC) for a burst and link it to a backscatter product (RTC\_S1)](#make-static-layers-rtc_s1_static-for-a-burst-and-link-it-to-a-backscatter-product-rtc_s1)
    - [1. Make the static layers to link to each product:](#1-make-the-static-layers-to-link-to-each-product)
    - [2. Make the RTC Backscatter for the scene and link the metadata to the static layers](#2-make-the-rtc-backscatter-for-the-scene-and-link-the-metadata-to-the-static-layers)
    - [3. Ensure the files are linked in the STAC metadata](#3-ensure-the-files-are-linked-in-the-stac-metadata)
- [Development](#development)
  - [Development in the Container](#development-in-the-container)
    - [Mount files at runtime](#mount-files-at-runtime)


## About 

The AWS sar-pipeline can be used to create two products using the OPERA ISCE3 based workflows. These are:
- **RTC_S1** -> Sentinel-1 Radiometrically Terrain Corrected (RTC) Backscatter [(Specification doc)](https://d2pn8kiwq2w21t.cloudfront.net/documents/ProductSpec_RTC-S1-STATIC.pdf)
- **RTC_S1_STATIC** -> Sentinel-1 Radiometrically Terrain Corrected (RTC) Backscatter [(Specification doc)](https://d2pn8kiwq2w21t.cloudfront.net/documents/ProductSpec_RTC-S1.pdf)

**RTC_S1** products are unique to each acquisition. **RTC_S1_STATIC** products are ancillary layers that can be shared across the same burst_id.


The **RTC_S1** pipeline must be run for every new scene acquired by Sentinel-1. The **RTC_S1_STATIC** product only needs to be run a single time to create static layers that are fixed for each burst. These layers will need to be recreated only if the acquisition scenario or DEM changes. OR if the area of interest for the DE-Australia and DE-Antarctica project changes (this is not expected to happen often). Examples of static layers include `local_incidence_angles` and `digital_elevation_models`. Given the highly stable orbital tube of sentinel-1, these layers can be considered STATIC for a given burst.

The static layers can be 're-used' across a given burst_id, saving the storage required if they were created with each acquisition. For example, every 12 days Sentinel-1A will capture the burst `t070_149815_iw3`. The same `local_incidence_angles.tif` can be used for each repeat pass, as only the dielectric properties of the surface will change over time, and the angle at which the satellite observes the terrain will be the same. The static layer is therefore *linked* to a given **RTC_S1** product in the STAC metadata.

To link a **RTC_S1** product to the appropriate  **RTC_S1_STATIC** layers, the **RTC_S1_STATIC** products **must** exist for the given bursts. The linkage is specified when the workflow is run to create **RTC_S1** products. See the following example on how to [Make static layers (RTC_S1_STATIC) for a burst and link it to a backscatter product (RTC_S1)](#make-static-layers-rtcs1_static-for-a-burst-and-link-it-to-a-backscatter-product-rtcs1)


After each run is completed, the files will be uploaded to a specified S3 bucket location. A unique subpath for each product is created in the workflow.

### Example outputs

Example outputs of the **RTC_S1** and **RTC_S1_STATIC** workflows can be found here:
- **RTC_S1** -> https://deant-data-public-dev.s3.ap-southeast-2.amazonaws.com/index.html?prefix=experimental-linkage/s1_rtc_c1/t070_149815_iw3/2022/1/1/
- **RTC_S1_STATIC** -> https://deant-data-public-dev.s3.ap-southeast-2.amazonaws.com/index.html?prefix=experimental-linkage/s1_rtc_static_c1/t070_149815_iw3/ 


## Pipeline Overview

### Creating Products 
The AWS pipeline runs using a docker container. At runtime, the script [run_aws_pipeline.sh](../../scripts/run_aws_pipeline.sh) is run. The arguments that can be passed to the container are:

```bash
# Basic input for product creation
--scene="" (required)
--burst_id_list=()
--resolution=20
--output_crs=""
--dem_type="cop_glo30"
--product="RTC_S1"
--s3_bucket="deant-data-public-dev"
--s3_project_folder="experimental"
--collection="s1_rtc_c1"
--make_existing_products=false
--skip_upload_to_s3=false
--scene_data_source="CDSE"
--orbit_data_source="CDSE"
--validate_stac=false
# Required inputs for linking RTC_S1_STATIC to RTC_S1
# Assumes that a RTC_S1_STATIC products exist for all RTC_S1 bursts being processed
--link_static_layers=false           
--linked_static_layers_s3_bucket="deant-data-public-dev"
--linked_static_layers_s3_project_folder="experimental" 
--linked_static_layers_collection="s1_rtc_static_c1" 
```
- `scene` -> A valid sentinel-1 IW scene (e.g. S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD)
- `burst_id_list` -> A list of burst id's corresponding to the scene. If not provided, all will be processed. Can be space separated list or line separated .txt file.
- `resolution` -> The target resolution of the products. Default is 20m.
- `output_crs` -> The target crs of the products. If not specified, the UTM of the scene center will be used. Expects integer values (e.g. 3031)
- `dem_type` -> The type of digital elevation model (DEM) to download and use for processing. Supported values: `cop_glo30`, `REMA_32`, `REMA_10`, `REMA_2`.
- `product` -> The product being created with the workflow. Must be `RTC_S1` or `RTC_S1_STATIC`.
- `s3_bucket` -> the bucket to upload the products
- `s3_project_folder` -> The project folder to upload to.
- `collection` -> The collection which the set of products belongs. Must end with 'cX' where X is a valid integer reffering to the collection number of the product. e.g. rtc_s1_c1.
- `make_existing_products` -> Whether to generate products even if they already exist in AWS S3 under the specified product folder path `s3_bucket/s3_project_folder/collection/...`. 
  - **WARNING** - Passing this flag will create duplicate files and overwrite existing metadata, which may affect downstream workflows.
- `skip_upload_to_s3` -> Make the products, but skip uploading them to S3.
- `scene_data_source` -> Where to download the scene slc file. Either `ASF` or `CDSE`. The default is `CDSE`.
- `orbit_data_source` -> Where to download the orbit files. Either `ASF` or `CDSE`. The default is `CDSE`.
- `validate_stac` -> Whether to validate the created STAC doc within the code. If the stac is invalid, products will not be uploaded.
- `link_static_layers` -> Flag to link RTC_S1_STATIC to RTC_S1
- `linked_static_layers_s3_bucket` -> bucket where RTC_S1_STATIC stored
- `linked_static_layers_s3_project_folder` -> folder within bucket where RTC_S1_STATIC stored
- `linked_static_layers_collection` -> collection where RTC_S1_STATIC stored


**Final paths of products**:

- **RTC_S1** -> final path will be `s3_bucket/s3_project_folder/collection/burst_id/burst_year/burst_month/burst_day/*files*`
- **RTC_S1_STATIC** -> final path will be `s3_bucket/s3_project_folder/collection/burst_id/*files*`


## Environment Variables

At runtime, the pipeline expects the following environment variables to be set. These can be passed in using an environment file like below. NASA earthdata credentials can be created here - https://urs.earthdata.nasa.gov/. Credentials for the Copernicus Data Space Ecosystem (CDSE) can be created here - https://dataspace.copernicus.eu/. The AWS credentials must have write access to the specified bucket location.

env.secret:

```txt
EARTHDATA_LOGIN=
EARTHDATA_PASSWORD=
CDSE_LOGIN=
CDSE_PASSWORD=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_DEFAULT_REGION=
```

## Container processing location

The location for where data is downloaded and written for processing in the container is specified in the [run_aws_pipeline.sh](../../scripts/run_aws_pipeline.sh) file. In the case of AWS processing, an EBS block may be mounted. The mount point must align to the paths specified in the run script for the EBS storage to be used. The hardcoded values are:

```bash
# set process folders for the container
download_folder="/home/rtc_user/working/downloads"
out_folder="/home/rtc_user/working/results/$scene"
scratch_folder="/home/rtc_user/working/scratch/$scene"
```


# Build the docker image

```bash
docker build -t sar-pipeline -f Docker/Dockerfile .
```

## Test image interactively

```bash
 docker run -it --entrypoint /bin/bash sar-pipeline
```

# Running the workflow

## RTC_S1 - Sentinel-1 Radiometrically Terrain Corrected (RTC) Backscatter

- Note, remove the `--skip_upload_to_s3` and `--make_existing_products` to make non-existing products and access them from the s3. 

### Antarctica (without linking RTC_S1_STATIC)

Output CRS should be polar stereographic 3031

```bash
docker run --env-file env.secret -it sar-pipeline --scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD --output_crs 3031 --skip_upload_to_s3 --make_existing_products
```

For a single burst:

```bash
docker run --env-file env.secret -it sar-pipeline --scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD --output_crs 3031 --burst_id_list t070_149815_iw3 --skip_upload_to_s3 --make_existing_products
```

Using the REMA 32 metre dem

```bash
docker run --env-file env.secret -it sar-pipeline --scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD --output_crs 3031 --burst_id_list t070_149815_iw3 --dem_type REMA_32 --skip_upload_to_s3 --make_existing_products
```bash

### Australia (without linking RTC_S1_STATIC)

The output CRS will be the UTM zone corresponding to scene/burst centre. This is selected automatically and does not need to be specified.

```bash
docker run --env-file env.secret -it sar-pipeline --scene S1A_IW_SLC__1SDV_20220130T191354_20220130T191421_041694_04F5F9_1AFD --skip_upload_to_s3 --make_existing_products
```


## RTC_S1_STATIC - Static Layers for Sentinel-1 Radiometrically Terrain Corrected (RTC) Backscatter

```bash
docker run --env-file env.secret -it sar-pipeline --scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD --output_crs 3031 --product RTC_S1_STATIC --collection s1_rtc_static_c1 --s3_project_folder "experimental" --skip_upload_to_s3 --make_existing_products
```


# Examples

## Make static layers (RTC_S1_STATIC) for a burst and link it to a backscatter product (RTC_S1)

**Context** - The incoming scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD is a repeat pass acquisition over the burst `t070_149815_iw3`. We want to link the backscatter product (HH.tif) for the given acquisition to the static layers for burst `t070_149815_iw3`. We first begin by creating the static layers for the given burst if they do not exist.


### 1. Make the static layers to link to each product:


```bash
docker run --env-file env.secret -it sar-pipeline \
--scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD \
--burst_id_list t070_149815_iw3 \
--output_crs 3031 \
--product RTC_S1_STATIC \
--s3_bucket deant-data-public-dev \
--collection s1_rtc_static_c1 \
--s3_project_folder experimental/static-layers
```

Note, any scene that covers the given burst could be used. For example, the following scene captured 12 days earlier on the same repeat orbit could be used `S1A_IW_SLC__1SSH_20211220T124745_20211220T124815_041092_04E1C2_0475`

Once the workflow has been completed, you should be able to fine the static layers at:

`https://deant-data-public-dev.s3.ap-southeast-2.amazonaws.com/index.html?prefix=experimental-linkage/s1_rtc_static_c1/t070_149815_iw3/`

### 2. Make the RTC Backscatter for the scene and link the metadata to the static layers

```bash
docker run --env-file env.secret -it sar-pipeline \
--scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD \
--burst_id_list t070_149815_iw3 \
--output_crs 3031 \
--product RTC_S1 \
--s3_bucket deant-data-public-dev \
--collection s1_rtc_c1 \
--s3_project_folder experimental/nrb \
--link_static_layers \
--linked_static_layers_s3_bucket deant-data-public-dev \
--linked_static_layers_collection s1_rtc_static_c1 \
--linked_static_layers_s3_project_folder experimental/static-layers
```

### 3. Ensure the files are linked in the STAC metadata

By opening the metadata file and checking the assets links, you should see the links for auxiliary products reference the static layers. For example, compare the href in the product metadata below. HH data belongs to RTC_S1 and number_of_looks belongs to RTC_S1_STATIC

```json
 "assets": {
        "HH": {
            "href": "https://deant-data-public-dev.s3.ap-southeast-2.amazonaws.com/nrb/s1_rtc_c1/t070_149815_iw3/2022/1/1/OPERA_L2_RTC-S1_T070-149815-IW3_20220101T124752Z_20250408T025401Z_S1A_20_v0.1_HH.tif",
            "type": "image/tiff; application=geotiff; profile=cloud-optimized",
            "title": "HH",
            "description": "HH polarised backscatter",
            "proj:shape": [
                4539,
                2387
            ],
            "proj:transform": [
                20.0,
                0.0,
                241320.0,
                0.0,
                -20.0,
                -1373780.0,
                0.0,
                0.0,
                1.0
            ],
            "proj:epsg": 3031,
            "raster:data_type": "float32",
            "raster:sampling": "Area",
            "raster:nodata": "nan",
            "roles": [
                "data",
                "backscatter"
            ]
        },
        "number_of_looks": {
            "href": "https://deant-data-public-dev.s3.ap-southeast-2.amazonaws.com/static-layers/s1_rtc_static_c1/t070_149815_iw3/OPERA_L2_RTC-S1-STATIC_T070-149815-IW3_20010101_20250408T012421Z_S1A_20_v1.0.2_number_of_looks.tif",
            "type": "image/tiff; application=geotiff; profile=cloud-optimized",
            "title": "number_of_looks",
            "description": "number of looks",
            "proj:shape": [
                4539,
                2387
            ],
            "proj:transform": [
                20.0,
                0.0,
                241320.0,
                0.0,
                -20.0,
                -1373780.0,
                0.0,
                0.0,
                1.0
            ],
            "proj:epsg": 3031,
            "raster:data_type": "float32",
            "raster:sampling": "Area",
            "raster:nodata": "nan",
            "roles": [
                "data",
                "auxiliary"
            ]
        },
 }
```


# Development

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

/home/rtc_user/scripts/run_aws_pipeline.sh --scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD --output_crs 3031 --skip_upload_to_s3 --make_existing_products

# Antarctic scene (single burst)

/home/rtc_user/scripts/run_aws_pipeline.sh --scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD --output_crs 3031 --burst_id_list t070_149815_iw3 --skip_upload_to_s3 --make_existing_products

# Australia scene

/home/rtc_user/scripts/run_aws_pipeline.sh --scene S1A_IW_SLC__1SDV_20220130T191354_20220130T191421_041694_04F5F9_1AFD --skip_upload_to_s3 --make_existing_products

# Antarctica static layers

/home/rtc_user/scripts/run_aws_pipeline.sh --scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD --output_crs 3031 --product RTC_S1_STATIC --collection s1_rtc_static_c1 --s3_project_folder "experimental" --skip_upload_to_s3 --make_existing_products


```

### Mount files at runtime

```bash
docker run --env-file env.secret -v $(pwd)/scripts:/home/rtc_user/scripts -v /data/working:/home/rtc_user/working sar-pipeline --scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD --output_crs 3031 --skip_upload_to_s3 --make_existing_products

```

```bash
docker run --env-file env.secret -v $(pwd)/scripts:/home/rtc_user/scripts -v /data/working:/home/rtc_user/working -it sar-pipeline --scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD --output_crs 3031 --burst_id_list t070_149815_iw3 t070_149821_iw1 --s3_project_folder experimental/REMA_32 --dem_type REMA_32 --skip_upload_to_s3 --make_existing_products
```