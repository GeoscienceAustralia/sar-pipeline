#!/bin/bash

# Default values for the continer
scene=""
base_rtc_config=""
dem="glo_30"
s3_bucket="deant-data-public-dev"
s3_project_folder="experimental/s1_rtc_c1"

# Parse named arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --scene) scene="$2"; shift ;;  # Shift moves to next argument
        --base_rtc_config) base_rtc_config="$2"; shift ;;
        --dem) dem="$2"; shift ;;
        --s3_bucket) s3_bucket="$2"; shift ;;
        --s3_project_folder) s3_project_folder="$2"; shift ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
    shift
done

# Check if 'scene' is provided
if [[ -z "$scene" || -z "$base_rtc_config" ]]; then
    echo "Error: Both --scene and --base_rtc_config are required parameters."
    exit 1
fi

echo The input variables are:
echo scene : "$scene"
echo base_rtc_config : "$base_rtc_config"
echo dem : "$dem"
echo s3_bucket : "$s3_bucket"
echo s3_project_folder : "$s3_project_folder"

# set process folders for the container
download_folder="/home/rtc_user/working/downloads"
out_folder="/home/rtc_user/working/results/$scene"
scratch_folder="/home/rtc_user/working/scratch/$scene"

echo The container will use these paths for processing:
echo download_folder : "$out_folder"
echo scratch_folder : "$scratch_folder"
echo out_folder : "$out_folder"

# activate conda 
source ~/.bashrc

# activate the sar-pipeline environment 
conda activate sar-pipeline

# search and download all the required ancillery/src files 
# make the rtc config that will be used by the RTC processor
# set the config path to be in the out_folder so it can be uploaded with products
RUN_CONFIG_PATH="$out_folder/OPERA-RTC_CONFIG.yaml"

get-data-for-scene-and-make-run-config \
"$scene" \
"$base_rtc_config" \
"$dem" \
"$download_folder" \
"$scratch_folder" \
"$out_folder" \
"$RUN_CONFIG_PATH"

if [ $? -ne 0 ]; then
    echo "Process failed: get-data-for-scene-and-make-run-config"
    exit 1
fi

# activate the ISCE3 envrionment and make products
conda activate RTC
rtc_s1.py $RUN_CONFIG_PATH

if [ $? -ne 0 ]; then
    echo "Process failed: rtc_s1.py $RUN_CONFIG_PATH"
    exit 1
fi

# activate the sar-pipeline environment 
conda activate sar-pipeline

# point at the out product directory and make STAC metdata
# note storage pattern is assumed to be s3_bucket / s3_project_folder / year / month / day / burstid / *files
make-rtc-opera-stac-and-upload-bursts "$out_folder" "$RUN_CONFIG_PATH" "$s3_bucket" "$s3_project_folder"

if [ $? -ne 0 ]; then
    echo "Process failed: make-rtc-opera-stac-and-upload-bursts"
    exit 1
fi




