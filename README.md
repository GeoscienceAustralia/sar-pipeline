# sar-pipeline

This repository contains code for running SAR processing pipelines on the NCI and AWS. Currently, this codebase supports two pipelines for generating Sentinel-1 Normalised Radar Backscatter (NRB). Detailed usage docs are provided below:

* [isce3_rtc (Sentinel-1 IW/EW) that can be run locally and on AWS](docs/pipelines/isce3_rtc.md)
* [pyroSAR-GAMMA (Sentinel-1 IW/EW) that can locally and on AWS](docs/pipelines/pyrosar_gamma.md)
* [pyroSAR-GAMMA (Sentinel-1 IW/EW) that can be run on the NCI](docs/pipelines/nci_pyrosar_gamma.md)

For more information see [Pipelines](docs/pipelines/README.md) or the specific workflow docs for usage examples and running tests.

## Development Setup

Detailed documentation for the project setup can be found in the [development documentation](docs/development/README.md). It is highly recommended this be reviewed before contributing to the project. This project utilises [pixi](https://pixi.sh/latest/) for managing packages and running tests.

* [Cloning the project](docs/development/README.md)
* [Developer set up](docs/development/developer_pixi.md)
  
## Quick Setup

Clone the repository

```bash
git clone https://github.com/GeoscienceAustralia/sar-pipeline.git
```

### ISCE3 RTC

The ISCE3 RTC Pipeline can be used to produce [CEOS Approved](https://ceos.org/ard/index.html#datasets)
Analysis Ready Sentinel‑1 Radiometrically Terrain Corrected (RTC) or Normalised Radar Backscatter (NRB) data. 
Sentinel-1 Single Look Complex (SLC) files in the Interferometric Wide (IW) and Extra Wide (EW) mode can be processed.
The pipeline automatically downloads all required inputs and generates NRB outputs at the burst level,
along with the associated metadata files—including STAC JSON and XML—required for
standards‑compliant distribution and downstream use.

1. Build the container

```bash
docker build --platform linux/amd64 -t sar-pipeline-isce3-rtc -f Docker/isce3_rtc/Dockerfile .
```

2. Test the image interactively (type `exit` to exit)

```bash
docker run --platform linux/amd64 -it --entrypoint /bin/bash sar-pipeline-isce3-rtc
```

1. Set the following minimum environment credentials in a `.env` file. At minimum we require earthdata *OR* Coperniucs Space Data Ecosystem (CDSE) credentials to download from the Alaska Satelite Facility (ASF) or CDSE respectively. These can be created here for the [ASF](http://urs.earthdata.nasa.gov/) and [CDSE](https://dataspace.copernicus.eu/).

```text
EARTHDATA_LOGIN=
EARTHDATA_PASSWORD=
```
4. Generate Normalised Radar Backscatter for a test burst. The outputs will be written to a local `data` folder. To process
the all bursts do not specify the burst ids. Note products will be made at the burst level, not the scene level.

```bash
mkdir data
```

```bash
docker run --env-file .env -v ${PWD}/data:/home/rtc_user/working sar-pipeline-isce3-rtc \
--scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD \
--burst-id-list t070_149815_iw3 \
--skip-upload-to-s3 \
--make-existing-products \
--scene-data-source ASF \
--orbit-data-source ASF 
```

Note if there are permission issues writing to the local `./data` folder, the following can be run:

```bash
sudo chmod -R 777 ./data
```

5. See the outputs in the data folder:

```bash
.data/results/
└── baseline
    └── 1
        └── RTC_S1
            └── S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD
                ├── OPERA-RTC_runconfig.yaml
                ├── S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD_burst_geoms.json
                └── t070_149815_iw3
                    ├── ga_s1a_nrb_iw_0-1-0_T070-149815-IW3_20220101T124752Z_HH-gamma0.tif
                    ├── ga_s1a_nrb_iw_0-1-0_T070-149815-IW3_20220101T124752Z_checksum.sha1
                    ├── ga_s1a_nrb_iw_0-1-0_T070-149815-IW3_20220101T124752Z_mask.tif
                    ├── ga_s1a_nrb_iw_0-1-0_T070-149815-IW3_20220101T124752Z_metadata.h5
                    ├── ga_s1a_nrb_iw_0-1-0_T070-149815-IW3_20220101T124752Z_metadata.xml
                    ├── ga_s1a_nrb_iw_0-1-0_T070-149815-IW3_20220101T124752Z_proc-config.yaml
                    ├── ga_s1a_nrb_iw_0-1-0_T070-149815-IW3_20220101T124752Z_stac-item.json
                    └── ga_s1a_nrb_iw_0-1-0_T070-149815-IW3_20220101T124752Z_thumbnail.png
```

6. See the [full docs](docs/pipelines/isce3_rtc.md) to see how static layers can created and used.

7. EW mode requires an SLC input, which CDSE doesn't always produce by default — see
[Special Considerations for EW Mode](docs/pipelines/isce3_rtc.md#36-special-considerations-for-ew-mode)
for checking SLC availability and generating an SLC from L0 when needed.

## Release

GA release information is provided in the [release guide](./docs/development/release_guide.md)

## License

Copyright © 2025 Geoscience Australia.

This project is licensed under the **Apache License, Version 2.0**. See the LICENSE file for details.

## Acknowledgements 

This software distributes a [modified version](https://github.com/GeoscienceAustralia/RTC) of the [opera-adt/RTC](https://github.com/opera-adt/RTC) software originally developed by NASA JPL and distributed under the **Apache License, Version 2.0**. Copyright © 2021 California Institute of Technology (“Caltech”). U.S. Government sponsorship acknowledged. All rights reserved. Modifications have been made by Geoscience Australia.


