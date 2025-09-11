# AWS ISCE3 RTC Pipeline (Sentinel-1 IW NRB)

- [AWS ISCE3 RTC Pipeline (Sentinel-1 IW NRB)](#aws-isce3-rtc-pipeline-sentinel-1-iw-nrb)
  - [About](#about)
  - [Example outputs](#example-outputs)
  - [Pipeline Overview](#pipeline-overview)
    - [Environment Variables](#environment-variables)
    - [Creating Products](#creating-products)
  - [Container processing location](#container-processing-location)
- [Build the docker image](#build-the-docker-image)
  - [Test image interactively](#test-image-interactively)
- [Quick Start](#quick-start)
- [Running the workflow](#running-the-workflow)
  - [RTC\_S1 - Sentinel-1 Radiometrically Terrain Corrected (RTC) Backscatter](#rtc_s1---sentinel-1-radiometrically-terrain-corrected-rtc-backscatter)
    - [Antarctica (without linking RTC\_S1\_STATIC)](#antarctica-without-linking-rtc_s1_static)
    - [Australia (without linking RTC\_S1\_STATIC)](#australia-without-linking-rtc_s1_static)
  - [RTC\_S1\_STATIC - Static Layers for Sentinel-1 Radiometrically Terrain Corrected (RTC) Backscatter](#rtc_s1_static---static-layers-for-sentinel-1-radiometrically-terrain-corrected-rtc-backscatter)
- [Examples](#examples)
  - [Make static layers (RTC\_S1\_STATIC) and link it to a backscatter product (RTC\_S1)](#make-static-layers-rtc_s1_static-and-link-it-to-a-backscatter-product-rtc_s1)
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


The **RTC_S1** pipeline must be run for every new scene acquired by Sentinel-1. The **RTC_S1_STATIC** product only needs to be run a single time to create static layers that are fixed for each burst. These layers only need to be recreated if the acquisition scenario or DEM changes. OR if the area of interest for the DE-Australia and DE-Antarctica project changes (either of these is not expected to happen often). Examples of static layers include `local_incidence_angles` and `gamma_to_beta0` files. Given the highly stable orbital tube of sentinel-1, these layers can be considered STATIC for a given burst.

For example, every 12 days Sentinel-1A will capture the burst `t070_149815_iw3`. The same single `local_incidence_angles.tif` can be used for each repeat pass, as only the dielectric properties of the surface will change over time, and the angle at which the satellite observes the terrain will be the same. The static layer is therefore *linked* to a given **RTC_S1** product in the STAC metadata. To link a **RTC_S1** product to the corresponding **RTC_S1_STATIC** layers, the **RTC_S1_STATIC** products **must** be created first. 

After each run is completed, the files will be uploaded to a specified S3 bucket location. A unique subpath for each product is created in the workflow.

## Example outputs

Example outputs of the **RTC_S1** and **RTC_S1_STATIC** workflows can be found at the links below. If you look at the assets of metadata.json file, you can see the static layers have been linked.
- **RTC_S1** -> https://deant-data-public-dev.s3.ap-southeast-2.amazonaws.com/index.html?prefix=persistent/repositories/sar-pipeline/examples/gamma0/ga_s1_nrb_iw_hh_c1/t070_149815_iw3/2022/1/1/
- **RTC_S1_STATIC** -> https://deant-data-public-dev.s3.ap-southeast-2.amazonaws.com/index.html?prefix=persistent/repositories/sar-pipeline/examples/gamma0/ga_s1_nrb_iw_static_c1/t070_149815_iw3/


## Pipeline Overview

### Environment Variables

At runtime, the pipeline expects the following environment variables to be set. These can be passed in using an environment file. NASA earthdata credentials can be created here - https://urs.earthdata.nasa.gov/. Credentials for the Copernicus Data Space Ecosystem (CDSE) can be created here - https://dataspace.copernicus.eu/. The AWS credentials must have write access to the specified bucket location.

[env.secret.example](../../env.secret.example)

```txt
EARTHDATA_LOGIN=
EARTHDATA_PASSWORD=
CDSE_LOGIN=
CDSE_PASSWORD=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_DEFAULT_REGION=
AUS_COP_HUB_LOGIN=
AUS_COP_HUB_PASSWORD=
AUS_COP_HUB_CLIENT_ID=odata
AUS_COP_HUB_CLIENT_SECRET=
```

### Creating Products 
The AWS pipeline runs using a docker container. At runtime, the script [run_aws_pipeline.sh](../../scripts/run_aws_pipeline.sh) is run. The arguments that can be passed to the container are as follows:

```bash
# Basic input for product creation
--scene="" (required)
--burst_id_list=()
--resolution=20
--output_crs="UTM"
--dem_type=("REMA_32" "cop_glo30") # order of preference, if data available for scene
--product="RTC_S1"
--backscatter_convention=gamma0 # gamma0, sigma0 or beta0
--s3_bucket="deant-data-public-dev"
--s3_project_folder="baseline"
--collection_number=0
--make_existing_products=false
--skip_upload_to_s3=false
--scene_data_source=("AUS_COP_HUB" "ASF" "CDSE")
--orbit_data_source=("ASF" "CDSE")
--skip_validate_stac=false
# Required inputs for linking RTC_S1_STATIC to RTC_S1
# Assumes that a RTC_S1_STATIC products exist for all RTC_S1 bursts being processed
--link_static_layers=false           
--linked_static_layers_s3_bucket="deant-data-public-dev"
--linked_static_layers_s3_project_folder="baseline" 
--linked_static_layers_collection_number=0 
```
- `scene` -> A valid sentinel-1 IW scene (e.g. S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD)
- `burst_id_list` -> A list of burst id's corresponding to the scene. If not provided, all will be processed. Can be space separated list or line separated .txt file.
- `resolution` -> The target resolution of the products. Default is 20m.
- `output_crs` -> The target crs of the products. If not specified, the UTM of the scene center will be used or polar stereographic coordinates will be used for high latitudes above 60 degrees. Expects integer values (e.g. `3031`)
- `dem_type` -> The preference of digital elevation model (DEM) to download and use for processing. Can be passed as a string or list of preferences separated by a space. If DEM data does not exist in the area of the first preference, the next will be used. E.g. `--dem-type REMA_32 cop_glo30` will first look for the Antarctic specific REMA DEM @32m before settling on the cop_glo30. Values must be one of: `cop_glo30`, `REMA_32`, `REMA_10`, `REMA_2`.
- `product` -> The product being created with the workflow. Must be `RTC_S1` or `RTC_S1_STATIC`.
- `backscatter_convention` -> the output backscatter convention from the workflow. Note sigma0 data is referenced to the DEM. To create sigma0 ellipsoid referenced data, the beta0 layer and static incidence_angle layer is required; sigma0_ellipsoid = beta0*sin(incidence_angle).
- `s3_bucket` -> the bucket to upload the products
- `s3_project_folder` -> The project folder to upload to.
- `collection_number` -> The collection number of the product as an integer.
- `make_existing_products` -> Whether to generate products even if they already exist in AWS S3 under the specified product folder path `s3_bucket/s3_project_folder/collection/...`. 
  - **WARNING** - Passing this flag will create duplicate files and overwrite existing metadata, which may affect downstream workflows.
- `skip_upload_to_s3` -> Make the products, but skip uploading them to S3.
- `scene_data_source` -> Where to download the scene slc file. Can be single string or a list of preferences separated by a space. Supported values are any of `AUS_COP_HUB`, `ASF` or `CDSE`. The default is (`AUS_COP_HUB` `ASF` `CDSE`).
- `orbit_data_source` -> Where to download the orbit files.  Can be single string or a list of preferences separated by a space. Can be any of `ASF` or `CDSE`. The default is (`ASF` `CDSE`).
- `skip_validate_stac` -> To skip validation of the created STAC doc within the code. If the stac is invalid, products will not be uploaded.
- `link_static_layers` -> Flag to link RTC_S1_STATIC to RTC_S1
- `linked_static_layers_s3_bucket` -> bucket where RTC_S1_STATIC stored
- `linked_static_layers_s3_project_folder` -> folder within bucket where RTC_S1_STATIC stored
- `linked_static_layers_collection_number` -> The collection number of the linked RTC_S1_STATIC product.


**Final Paths of Products**:

Final product output paths have the following structure

**RTC_S1**
- s3_bucket/s3_project_folder/odc_product_name/burst_id/year/month/day/*files
- odc_product_name is determined by the polarisation and collection_number for RTC_S1 products.
- It will be one of ga_s1_nrb_iw_vv_vh_X, ga_s1_nrb_iw_vv_X, ga_s1_nrb_iw_hh_hv_X, ga_s1_nrb_iw_hh_X, where X is the collection_number
- example -> https://deant-data-public-dev.s3.ap-southeast-2.amazonaws.com/index.html?prefix=persistent/repositories/sar-pipeline/examples/gamma0/ga_s1_nrb_iw_hh_c1/t070_149815_iw3/2022/1/1/
**RTC_S1_STATIC**
- e.g. s3_bucket/s3_project_folder/odc_product_name/burst_id/*files
- odc_product_name = ga_s1_nrb_iw_static_X, where X is the collection_number
- example -> https://deant-data-public-dev.s3.ap-southeast-2.amazonaws.com/index.html?prefix=persistent/repositories/sar-pipeline/examples/gamma0/ga_s1_nrb_iw_static_c1/t070_149815_iw3/

## Container processing location

The location for where data is downloaded and written for processing in the container is specified in the [run_aws_pipeline.sh](../../scripts/run_aws_pipeline.sh) file. In the case of AWS processing, an EBS block may be mounted. The mount point must align to the paths specified in the run script for the EBS storage to be used. The hardcoded values are:

```bash
# set process folders for the container
download_folder="/home/rtc_user/working/downloads"
out_folder="/home/rtc_user/working/results/$s3_project_folder/$collection_number/$product/$scene"
scratch_folder="/home/rtc_user/working/scratch/$s3_project_folder/$collection_number/$product/$scene"
```


# Build the docker image

```bash
docker build -t sar-pipeline -f Docker/Dockerfile .
```

## Test image interactively

```bash
 docker run -it --entrypoint /bin/bash sar-pipeline
```

# Quick Start

Build and test the docker image using pixi:

```bash
pixi run test-full-aws-docker-run
```

This will 1) build and tag the sar-pipeline docker image, 2) create static layers (RTC_S1_STATIC) and 3) create backscatter (RTC_S1) and link the products to the static layers. Outputs will be generated locally to `../../tests/sar_pipeline/data/isce3_rtc/results`

# Running the workflow

## RTC_S1 - Sentinel-1 Radiometrically Terrain Corrected (RTC) Backscatter

- Note, the `--skip_upload_to_s3` and `--make_existing_products` flags are set so existing products will be made, and no uploads to S3 will occur. 

### Antarctica (without linking RTC_S1_STATIC)

Output CRS should be polar stereographic 3031

```bash
docker run --env-file env.secret -it sar-pipeline --scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD --s3_project_folder TMP --skip_upload_to_s3 --make_existing_products
```

For a single burst:

```bash
docker run --env-file env.secret -it sar-pipeline --scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD --s3_project_folder TMP --burst_id_list t070_149815_iw3 --skip_upload_to_s3 --make_existing_products
```

### Australia (without linking RTC_S1_STATIC)

The output CRS will be the UTM zone corresponding to scene/burst centre. This is selected automatically and does not need to be specified.

```bash
docker run --env-file env.secret -it sar-pipeline --scene S1A_IW_SLC__1SDV_20220130T191354_20220130T191421_041694_04F5F9_1AFD --s3_project_folder TMP --skip_upload_to_s3 --make_existing_products
```

## RTC_S1_STATIC - Static Layers for Sentinel-1 Radiometrically Terrain Corrected (RTC) Backscatter

```bash
docker run --env-file env.secret -it sar-pipeline --scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD --output_crs 3031 --product RTC_S1_STATIC --collection s1_rtc_static_c1 --s3_project_folder "TMP" --skip_upload_to_s3 --make_existing_products
```

# Examples

## Make static layers (RTC_S1_STATIC) and link it to a backscatter product (RTC_S1)

**Context** - The incoming scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD is a repeat pass acquisition over the burst `t070_149815_iw3`. We want to link the backscatter product (HH.tif) for the given acquisition to the static layers for burst `t070_149815_iw3`. We first begin by creating the static layers for the given burst if they do not exist.


### 1. Make the static layers to link to each product:


```bash
docker run --env-file env.secret -it sar-pipeline \
--scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD \
--burst_id_list t070_149815_iw3 \
--product RTC_S1_STATIC \
--s3_bucket deant-data-public-dev \
--collection_number 1 \
--s3_project_folder TMP/static-layers \
--make_existing_products
```

Note, any scene that covers the given burst could be used. For example, the following scene captured 12 days earlier on the same repeat orbit could be used `S1A_IW_SLC__1SSH_20211220T124745_20211220T124815_041092_04E1C2_0475`

Once the workflow has been completed, you should be able to fine the static layers at:

`https://deant-data-public-dev.s3.ap-southeast-2.amazonaws.com/index.html?prefix=TMP/ga_s1_nrb_iw_static_c1/t070_149815_iw3/`

### 2. Make the RTC Backscatter for the scene and link the metadata to the static layers

```bash
docker run --env-file env.secret -it sar-pipeline \
--scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD \
--burst_id_list t070_149815_iw3 \
--product RTC_S1 \
--s3_bucket deant-data-public-dev \
--collection_number 1 \
--s3_project_folder TMP/gamma0 \
--link_static_layers \
--linked_static_layers_s3_bucket deant-data-public-dev \
--linked_static_layers_collection_number 1 \
--linked_static_layers_s3_project_folder TMP/static-layers
--make_existing_products
```

### 3. Ensure the files are linked in the STAC metadata

By opening the metadata file and checking the assets links, you should see the links for auxiliary products reference the static layers. For example, compare the href in the product metadata below. HH data belongs to `RTC_S1` and number_of_looks belongs to `RTC_S1_STATIC`

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

chmod +x /home/rtc_user/scripts/run_aws_pipeline.sh 

# Antarctic scene (all bursts)

/home/rtc_user/scripts/run_aws_pipeline.sh --scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD --skip_upload_to_s3 --make_existing_products --s3_project_folder "TMP"

# Antarctic scene (single burst)

/home/rtc_user/scripts/run_aws_pipeline.sh --scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD --burst_id_list t070_149815_iw3 --skip_upload_to_s3 --make_existing_products --s3_project_folder "TMP"

# Australia scene

/home/rtc_user/scripts/run_aws_pipeline.sh --scene S1A_IW_SLC__1SDV_20220130T191354_20220130T191421_041694_04F5F9_1AFD --skip_upload_to_s3 --make_existing_products --s3_project_folder "TMP"

# Antarctica static layers

/home/rtc_user/scripts/run_aws_pipeline.sh --scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD --product RTC_S1_STATIC --collection_number 1 --s3_project_folder "TMP" --skip_upload_to_s3 --make_existing_products


```

### Mount files at runtime

```bash
docker run --env-file env.secret -v $(pwd)/scripts:/home/rtc_user/scripts -v /data/working:/home/rtc_user/working sar-pipeline --scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD --skip_upload_to_s3 --make_existing_products --s3_project_folder "TMP"

```

```bash
docker run --env-file env.secret -v $(pwd)/scripts:/home/rtc_user/scripts -v /data/working:/home/rtc_user/working -it sar-pipeline --scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD --burst_id_list t070_149815_iw3 t070_149821_iw1 --s3_project_folder TMP --skip_upload_to_s3 --make_existing_products
```