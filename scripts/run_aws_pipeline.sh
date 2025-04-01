#!/bin/bash

# Default values for the container
scene=""
burst_ids=() # list of burst_ids or line separated .txt file
resolution=20
output_crs=""
dem="cop_glo30"
product="RTC_S1" # RTC_S1_STATIC or RTC_S1
collection="s1_rtc_c1" # e.g. s1_rtc_c1 or s1_rtc_static_c1
s3_bucket="deant-data-public-dev"
s3_project_folder="experimental"

# Parse named arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --scene) scene="$2"; shift ;;  # Shift moves to next argument
        --resolution) resolution="$2"; shift ;; 
        --output_crs) output_crs="$2"; shift ;; 
        --dem) dem="$2"; shift ;;
        --product) product="$2"; shift ;;
        --collection) collection="$2"; shift ;;
        --s3_bucket) s3_bucket="$2"; shift ;;
        --s3_project_folder) s3_project_folder="$2"; shift ;;
        --burst_id_list)
            shift  # Move past the flag
            if [[ $# -eq 1 && -f "$1" ]]; then
                # If only one argument remains and it's a file, read burst IDs from it
                burst_ids=($(cat "$1"))
                shift
            else
                # Otherwise, treat remaining arguments as burst IDs
                while [[ $# -gt 0 && ! "$1" =~ ^-- ]]; do
                    burst_ids+=("$1")
                    shift
                done
            fi
            ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
    shift
done

# Check if 'scene' is provided
if [[ -z "$scene" ]]; then
    echo "Error: --scene is a required parameter."
    exit 1
fi

# check the resolution is an integer
if ! [[ "$resolution" =~ ^[0-9]+$ ]]; then
    echo "Error: --resolution must be an integer."
    exit 1
fi

# The output resolution can be empty or an integer corresponding
# to the desired EPSG code. Eg. 3031 for EPSG:3031
# If empty, the CRS corresponding to the center of the scene is used
# OR, the CRS from the burst_db is used if provided.

if [[ -z "$output_crs" ]]; then
    epsg_code_msg="default UTM for scene center"
else
    # Check if the parameter is an integer using regex
    if ! [[ "$output_crs" =~ ^[0-9]+$ ]]; then
        echo "Error: --output_crs must be an integer corresponding to a CRS code (e.g. 3031) or empty."
        exit 1
    else
        epsg_code_msg="EPSG:$output_crs"
    fi
fi

# Ensure the specified product is valud
if [[ "$product" != "RTC_S1" && "$product" != "RTC_S1_STATIC" ]]; then
  echo "Error: Invalid product '$product'."
  echo "Allowed values: RTC_S1, RTC_S1_STATIC"
  exit 1
fi

echo ""
echo The input variables are:
echo scene : "$scene"
echo burst_ids : ${burst_ids[*]}
echo resolution : "$resolution"
echo output_crs : "$epsg_code_msg"
echo dem : "$dem"
echo product : "$product"
echo collection : "$collection"
echo s3_bucket : "$s3_bucket"
echo s3_project_folder : "$s3_project_folder"
echo ""

# set process folders for the container
download_folder="/home/rtc_user/working/downloads"
out_folder="/home/rtc_user/working/results/$collection/$scene"
scratch_folder="/home/rtc_user/working/scratch/$collection/$scene"

echo The container will use these paths for processing:
echo download_folder : "$out_folder"
echo scratch_folder : "$scratch_folder"
echo out_folder : "$out_folder"
echo ""

# activate conda 
source ~/.bashrc

# activate the sar-pipeline environment 
conda activate sar-pipeline

# search and download all the required ancillary/src files 
# make the rtc config that will be used by the RTC processor
# set the config path to be in the out_folder so it can be uploaded with products
RUN_CONFIG_PATH="$out_folder/OPERA-RTC_runconfig.yaml"

get-data-for-scene-and-make-run-config \
--scene "$scene" \
--burst_id_list ${burst_ids[*]} \
--resolution "$resolution" \
--output-crs "$output_crs" \
--dem "$dem" \
--product "$product" \
--download-folder "$download_folder" \
--scratch-folder "$scratch_folder" \
--out-folder "$out_folder" \
--run-config-save-path "$RUN_CONFIG_PATH"

if [ $? -ne 0 ]; then
    echo "Process failed: get-data-for-scene-and-make-run-config"
    exit 1
fi

# activate the ISCE3 environment and make products
conda activate RTC
rtc_s1.py $RUN_CONFIG_PATH

if [ $? -ne 0 ]; then
    echo "Process failed: rtc_s1.py $RUN_CONFIG_PATH"
    exit 1
fi

# activate the sar-pipeline environment 
conda activate sar-pipeline

# point at the out product directory and make STAC metadata
# note storage pattern is assumed to be s3_bucket / s3_project_folder / year / month / day / burst_id / *files
make-rtc-opera-stac-and-upload-bursts \
--results-folder "$out_folder" \
--run-config-path "$RUN_CONFIG_PATH" \
--product "$product" \
--collection "$collection" \
--s3-bucket "$s3_bucket" \
--s3-project-folder "$s3_project_folder" 

if [ $? -ne 0 ]; then
    echo "Process failed: make-rtc-opera-stac-and-upload-bursts"
    exit 1
fi
