# sar-pipeline

This repository contains code for running SAR processing pipelines on the NCI and AWS. Currently, this codebase supports two pipelines for generating Sentinel-1 Normalised Radar Backscatter (NRB). 

* [isce3_rtc (Sentinel-1 IW) that can be run locally and on AWS](docs/pipelines/isce3_rtc.md)
* [pyroSAR-GAMMA (Sentinel-1 IW/EW) that can be run on the NCI](docs/pipelines/pyrosar_gamma.md)

For more information see [Pipelines](docs/pipelines/README.md) or the specific workflow docs for usage examples and running tests.

## Development Setup

Detailed documentation for the project setup can be found in the [development documentation](docs/development/README.md). It is highly recommended this be reviewed before contributing to the project. This project utilises [pixi](https://pixi.sh/latest/) for managing packages and running tests.

* [Cloning the project](docs/development/README.md)
* [Developer set up](docs/development/developer_pixi.md)
* [User set up](docs/development/user_conda.md)

## Quick Setup

Clone the repository

```bash
git clone https://github.com/GeoscienceAustralia/sar-pipeline.git
```

### ISCE3 RTC (Docker)

1. Build the container

```bash
docker build -t sar-pipeline -f Docker/isce3_rtc/Dockerfile .
```

2. Test the image interactively (type `exit` to exit)

```bash
docker run -it --entrypoint /bin/bash sar-pipeline
```

1. Set the following minimum environment credentials in a `.env` file. At minimum we require AWS credentials and a set of credentials to download data. Earthdata credentials to download from the Alaska Satelite Facility (ASF) can be created [here](http://urs.earthdata.nasa.gov/).

```text
EARTHDATA_LOGIN=
EARTHDATA_PASSWORD=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_DEFAULT_REGION="ap-southeast-2"
```

4. Generate backscatter data for a test burst. The outputs will be written to a local `data` folder.

```bash
mkdir data
```

```bash
docker run --env-file .env -v ${PWD}/data:/home/rtc_user/working sar-pipeline \
--scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD \
--burst_id_list t070_149815_iw3 \
--skip_upload_to_s3 \
--make_existing_products \
--scene_data_source ASF \
--orbit_data_source ASF 
```

Note if there are permission issues writing to the local `./data` folder, the can be run.

```bash
sudo chmod -R 777 ./data
```


