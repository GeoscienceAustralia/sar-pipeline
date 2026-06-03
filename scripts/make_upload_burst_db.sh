#!/bin/bash

# script to create the IW and EW burst databases used by the RTC and CSLC pipelines
# see more information at docs/workflows/burst-db.md
# requires a local conda install and AWS access keys as environment variables

# Default values
AWS_S3_BUCKET="dea-public-data-dev"
AWS_S3_FOLDER="projects/s1_nrb/burst_db"
BURST_DB_VERSION_TAG="0.18.0"
BURST_DB_REPO="https://github.com/abradley60/burst_db.git"
BURST_DB_BRANCH="enable_ew_processing"

# Parse named arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --AWS_S3_BUCKET) AWS_S3_BUCKET="$2"; shift ;;
        --AWS_S3_FOLDER) AWS_S3_FOLDER="$2"; shift ;;
        --BURST_DB_VERSION_TAG) BURST_DB_VERSION_TAG="$2"; shift ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
    shift
done

echo "The burst db files will be uploaded to:"
echo "  AWS_S3_BUCKET        : $AWS_S3_BUCKET"
echo "  AWS_S3_FOLDER        : $AWS_S3_FOLDER"
echo "  BURST_DB_VERSION_TAG : $BURST_DB_VERSION_TAG"
echo "  Repo                 : $BURST_DB_REPO (branch: $BURST_DB_BRANCH)"

# Check if conda command exists
if command -v conda &> /dev/null; then
    echo "Conda is installed."
    conda --version
else
    echo "Conda could not be found. Please install conda."
    exit 1
fi

# Check AWS credentials
echo "Checking AWS environment variables (must have write access to $AWS_S3_BUCKET)"
if [[ -z "$AWS_ACCESS_KEY_ID" ]]; then
    echo "AWS_ACCESS_KEY_ID is not set in environment variables"; exit 1
fi
if [[ -z "$AWS_SECRET_ACCESS_KEY" ]]; then
    echo "AWS_SECRET_ACCESS_KEY is not set in environment variables"; exit 1
fi
if [[ -z "$AWS_DEFAULT_REGION" ]]; then
    echo "AWS_DEFAULT_REGION is not set in environment variables"; exit 1
fi
echo "AWS credentials and region are set."

# Set S3 destination before any cd so variables are guaranteed in scope
S3_DEST="s3://$AWS_S3_BUCKET/$AWS_S3_FOLDER/$BURST_DB_VERSION_TAG"
echo "S3 destination : $S3_DEST"

# Clone the EW-enabled fork of burst-db
echo "Cloning branch '$BURST_DB_BRANCH' from $BURST_DB_REPO"
git clone --branch "$BURST_DB_BRANCH" "$BURST_DB_REPO" burst_db
cd burst_db
BURST_DB_REPO_DIR=$(pwd)  # root of the cloned repo — returned to between runs

# Create conda environment - note the solve may take a while...
CONDA_ENV="burst-db-$BURST_DB_VERSION_TAG"
conda env create --name "$CONDA_ENV" -f environment.yml python=3.10

# Install burst-db into the isolated environment
conda run -n "$CONDA_ENV" python -m pip install .

# --- IW ---
echo "Creating IW burst database..."
mkdir -p iw_run && cd iw_run
conda run --no-capture-output -n "$CONDA_ENV" opera-db create --sensor-mode IW
if [ $? -ne 0 ]; then
    echo "ERROR: opera-db create --sensor-mode IW failed"; exit 1
fi
IW_FILE="opera-iw-burst-bbox-only.sqlite3"
mv opera-burst-bbox-only.sqlite3 "$IW_FILE"
echo "Uploading $IW_FILE to $S3_DEST/$IW_FILE"
aws s3 cp "$IW_FILE" "$S3_DEST/$IW_FILE"
if [ $? -ne 0 ]; then
    echo "ERROR: upload of $IW_FILE failed"; exit 1
fi
cd "$BURST_DB_REPO_DIR"

# --- EW ---
echo "Creating EW burst database..."
mkdir -p ew_run && cd ew_run
conda run --no-capture-output -n "$CONDA_ENV" opera-db create --sensor-mode EW
if [ $? -ne 0 ]; then
    echo "ERROR: opera-db create --sensor-mode EW failed"; exit 1
fi
EW_FILE="opera-ew-burst-bbox-only.sqlite3"
mv opera-burst-bbox-only.sqlite3 "$EW_FILE"
echo "Uploading $EW_FILE to $S3_DEST/$EW_FILE"
aws s3 cp "$EW_FILE" "$S3_DEST/$EW_FILE"
if [ $? -ne 0 ]; then
    echo "ERROR: upload of $EW_FILE failed"; exit 1
fi
cd "$BURST_DB_REPO_DIR"

# Summary
echo ""
echo "Both databases uploaded. Update BURST_DB_BASE_URL in required scripts:"
echo "  IW: https://$AWS_S3_BUCKET.s3.ap-southeast-2.amazonaws.com/$AWS_S3_FOLDER/$BURST_DB_VERSION_TAG/$IW_FILE"
echo "  EW: https://$AWS_S3_BUCKET.s3.ap-southeast-2.amazonaws.com/$AWS_S3_FOLDER/$BURST_DB_VERSION_TAG/$EW_FILE"
echo "Files to update:"
echo "  Docker/isce3_rtc/Dockerfile_EW"