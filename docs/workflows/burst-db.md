# Burst-db

The burst-db is a sentinel-1 burst database provided by the OPERA ADT that is used to make sure that all RTC-S1 products with the same burst identification (burst ID) are projected over the same geographic grid. The burst-db is used as an input by the backscatter pipeline.

**Codebase** - https://github.com/opera-adt/burst_db.git


# Requirements

- A valid conda environment
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and `AWS_DEFAULT_REGION` as environment variables that can access the desired bucket

# Instructions

## Create the database

The burst database can be created using the script [make_upload_burst_db.sh](../../scripts/make_upload_burst_db.sh)

from the project root run:

```bash
sh scripts/make_upload_burst_db.sh
```
The inputs that can be a passed to the script are:

```bash
--AWS_S3_BUCKET="deant-data-public-dev" 
--AWS_S3_FOLDER="persistent/burst_db"
--BURST_DB_VERSION_TAG="0.9.0"

- `AWS_S3_BUCKET` -> The S3 bucket to upload the database to
- `AWS_S3_FOLDER` -> The folder within the S3 bucket to upload to 
- `BURST_DB_VERSION_TAG` -> The version tag of https://github.com/opera-adt/burst_db.git to build the pipeline
```

With any major change to the acquisition scenario, the burst-db will need to be updated. This can be specified by changing the `BURST_DB_VERSION_TAG` provided to the workflow. At writing, the most recent version is 0.9.0.

By default, the file will be uploaded to:

`https://{AWS_S3_BUCKET}.s3.ap-southeast-2.amazonaws.com/{AWS_S3_FOLDER}/{BURST_DB_VERSION_TAG}/opera-burst-bbox-only.sqlite3`

## Update the references to database

The parameter `BURST_DB_URL` MUST be changed in the following files:

- [Dockerfile](../../Docker/Dockerfile)