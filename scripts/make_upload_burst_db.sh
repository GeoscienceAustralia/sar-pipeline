#!/bin/bash

# script to create the burst database used by the RTC and CSLC pipelines
# see more information at docs/workflows/burst-db.md
# requires a local conda install and AWS access keys as environment variables

# Default values for uploading the burst-db file
# Version of the github code to make the burst-db
AWS_S3_BUCKET="deant-data-public-dev" # 
AWS_S3_FOLDER="persistent/burst_db"
BURST_DB_VERSION_TAG="0.9.0" 

# Parse named arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --AWS_S3_BUCKET) AWS_S3_BUCKET="$2"; shift ;;  # Shift moves to next argument
        --AWS_S3_FOLDER) AWS_S3_FOLDER="$2"; shift ;;
        --BURST_DB_VERSION_TAG) BURST_DB_VERSION_TAG="$2"; shift ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
    shift
done

echo The burst db file will be uploaded to:
echo AWS_S3_BUCKET : "$AWS_S3_BUCKET"
echo AWS_S3_FOLDER : "$AWS_S3_FOLDER"
echo Burst-db version tagging:
echo BURST_DB_VERSION_TAG : "$BURST_DB_VERSION_TAG"
echo "WARNING - v$BURST_DB_VERSION_TAG of https://github.com/opera-adt/burst_db.git will be used." 
echo "Update using the BURST_DB_VERSION_TAG input if required"

# Check if conda command exists
if command -v conda &> /dev/null
then
    echo "Conda is installed."
    conda --version  # Print Conda version
else
    echo "Conda could not be found. Please install conda."
    exit 1  # Exit with an error code
fi

# Check if AWS credentials and region are set as environment variables 
echo "Checking AWS Environment variables"
echo "Environment variables must be set with write access to AWS_S3_BUCKET : $AWS_S3_BUCKET"
if [[ -z "$AWS_ACCESS_KEY_ID" ]]; then
    echo "AWS_ACCESS_KEY_ID is not set in environment variables"
    exit 1
fi

if [[ -z "$AWS_SECRET_ACCESS_KEY" ]]; then
    echo "AWS_SECRET_ACCESS_KEY is not set in environment variables"
    exit 1
fi

if [[ -z "$AWS_DEFAULT_REGION" ]]; then
    echo "AWS_DEFAULT_REGION is not set in environment variables"
    exit 1
fi

# If all variables are set
echo "AWS credentials and region are set as environment variables."

# clone the burst-db repository
echo Cloning version "$BURST_DB_VERSION_TAG" from https://github.com/opera-adt/burst_db.git
git clone --branch v"$BURST_DB_VERSION_TAG" https://github.com/opera-adt/burst_db.git
cd burst_db

# Create a new conda environment
conda create --name burst-db-v"$BURST_DB_VERSION_TAG" python=3.10 -y 

# Activate the environment
conda activate burst-db-v"$BURST_DB_VERSION_TAG"

# install the burst db requirements
python -m pip install .

# create the database
opera-db create

if [ $? -ne 0 ]; then
    echo "Process failed: opera-db create"
    exit 1
fi

# upload the database to S3
BURST_DB_FILE="opera-burst-bbox-only.sqlite3"
aws s3 cp $BURST_DB_FILE s3://$AWS_S3_BUCKET/$AWS_S3_FOLDER/$BURST_DB_VERSION_TAG/$BURST_DB_FILE
 
# warn user to update in workflow
# TODO update these suggestions once integrated in code
echo New database uploaded to bucket. Update BURST_DB_URL parameter in required scripts
echo E.g. BURST_DB_URL=https://deant-data-public-dev.s3.ap-southeast-2.amazonaws.com/persistent/burst_db/BURST_DB_VERSION_TAG/opera-burst-bbox-only.sqlite3