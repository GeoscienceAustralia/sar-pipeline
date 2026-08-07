#!/bin/bash
set -euo pipefail

rema_years="" # single string or comma separated list of years to process, e.g. "2020-02,2020-03,2020-04"
scenes_file=""
product="RTC_S1"
dem_type="REMA_30_TIMESERIES"
orbit_source="CDSE"
s3_project_folder="experimental/rema_v0.5.1"
output_crs="3031"
skip_upload_to_s3="true"
working_dir="/home/rtc_user"


while [[ "$#" -gt 0 ]]; do
    case $1 in
        --product) product="$2"; shift 2 ;;
        --rema-years) rema_years="$2"; shift 2 ;;
        --scenes-file) scenes_file="$2"; shift 2 ;;
        --dem-type) dem_type="$2"; shift 2 ;;
        --orbit-source) orbit_source="$2"; shift 2 ;;
        --s3-project-folder) s3_project_folder="$2"; shift 2 ;;
        --output-crs) output_crs="$2"; shift 2 ;;
        --working-dir) working_dir="$2"; shift 2 ;;
        --skip-upload-to-s3) skip_upload_to_s3="true"; shift ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
done

if [[ -z "$rema_years" ]]; then
    echo "Error: --rema-years is required"
    exit 1
fi

if [[ -z "$scenes_file" ]]; then
    echo "Error: --scenes-file is required"
    exit 1
fi

YEARS=()
IFS=',' read -ra YEARS <<< "$rema_years"

SCENES=()
while IFS= read -r line; do
    SCENES+=("$line")
done < "$scenes_file"

for year in "${YEARS[@]}"; do
    echo "Processing REMA year: $year"
    for scene in "${SCENES[@]}"; do
        echo "Processing scene: $scene"
        RUN_CMD="$working_dir/scripts/run_isce3_rtc_pipeline.sh --output_crs $output_crs --s3_project_folder $s3_project_folder --dem_type $dem_type --orbit_data_source $orbit_source"
        if [[ "$skip_upload_to_s3" == "true" ]]; then
            RUN_CMD+=" --skip_upload_to_s3"
        fi
        RUN_CMD+=" --rema_year $year --product $product --scene $scene"
        echo "Running command: $RUN_CMD"
        eval "$RUN_CMD"
    done
done