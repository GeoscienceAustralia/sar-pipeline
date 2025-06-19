#!/bin/bash

# See docs/workflows/aws.md for instructions and argument descriptions
## -- WORKFLOW INPUTS FOR PRODUCT CREATION -> RTC_S1 or RTC_S1_STATIC --
scene=""
burst_id_list=()
resolution=20
output_crs="UTM"
dem_type="cop_glo30"
product="RTC_S1"
s3_bucket="deant-data-public-dev"
s3_project_folder="experimental"
collection="s1_rtc_c1"
make_existing_products=false
skip_upload_to_s3=false
scene_data_source="ASF"
orbit_data_source="ASF"
validate_stac=false
## -- WORKFLOW INPUTS TO LINK RTC_S1_STATIC in RTC_S1 metadata--
# Assumes that a RTC_S1_STATIC products exist for all RTC_S1 bursts being processed
link_static_layers=false
linked_static_layers_s3_bucket="deant-data-public-dev"
linked_static_layers_s3_project_folder="experimental"
linked_static_layers_collection="s1_rtc_static_c1"

# Final product output paths follow the following structure
# RTC_S1 -> s3_bucket/s3_project_folder/collection/burst_id/year/month/day/*files
# RTC_S1_STATIC -> s3_bucket/s3_project_folder/collection/burst_id/*files

# Parse named arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --scene) scene="$2"; shift 2 ;;
        --resolution) resolution="$2"; shift 2 ;;
        --output_crs) output_crs="$2"; shift 2 ;;
        --dem_type) dem_type="$2"; shift 2 ;;
        --product) product="$2"; shift 2 ;;
        --s3_bucket) s3_bucket="$2"; shift 2 ;;
        --s3_project_folder) s3_project_folder="$2"; shift 2 ;;
        --collection) collection="$2"; shift 2 ;;
        --make_existing_products) make_existing_products=true; shift ;;
        --skip_upload_to_s3) skip_upload_to_s3=true; shift ;;
        --link_static_layers) link_static_layers=true; shift ;;
        --linked_static_layers_s3_bucket) linked_static_layers_s3_bucket="$2"; shift 2 ;;
        --linked_static_layers_collection) linked_static_layers_collection="$2"; shift 2 ;;
        --linked_static_layers_s3_project_folder) linked_static_layers_s3_project_folder="$2"; shift 2 ;;
        --scene_data_source) scene_data_source="$2"; shift 2 ;;
        --orbit_data_source) orbit_data_source="$2"; shift 2 ;;
        --validate_stac) validate_stac=true; shift ;;
        --burst_id_list)
            shift
            if [[ $# -eq 1 && -f "$1" ]]; then
                burst_id_list=($(cat "$1"))
                shift
            else
                while [[ $# -gt 0 && ! $1 =~ ^-- ]]; do
                    burst_id_list+=("$1")
                    shift
                done
            fi
            ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
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

if [[ -z "$output_crs" || "${output_crs,,}" == "utm" ]]; then
    epsg_code_msg="default UTM for scene center"
elif [[ "$output_crs" =~ ^[0-9]+$ ]]; then
    epsg_code_msg="EPSG:$output_crs"
else
    echo "Error: --output_crs must be empty, 'UTM', 'utm', or an integer corresponding to an EPSG code (e.g. 3031)."
    exit 1
fi

# Ensure the specified product is valid
if [[ "$product" != "RTC_S1" && "$product" != "RTC_S1_STATIC" ]]; then
  echo "Error: Invalid product '$product'."
  echo "Allowed values: RTC_S1, RTC_S1_STATIC"
  exit 1
fi

echo ""
echo The input variables are:
echo scene : "$scene"
echo burst_id_list : ${burst_id_list[*]}
echo resolution : "$resolution"
echo output_crs : "$epsg_code_msg"
echo dem_type : "$dem_type"
echo product : "$product"
echo s3_bucket : "$s3_bucket"
echo s3_project_folder : "$s3_project_folder"
echo collection : "$collection"
echo make_existing_products : "$make_existing_products"
echo skip_upload_to_s3 : "$skip_upload_to_s3"
echo scene_data_source : "$scene_data_source"
echo orbit_data_source : "$orbit_data_source"
echo validate_stac : "$validate_stac"

# warn the user about linking static layers
if [[ "$link_static_layers" = true && "$product" = "RTC_S1" ]]; then
    echo linked_static_layers_s3_bucket : "$linked_static_layers_s3_bucket"
    echo linked_static_layers_collection : "$linked_static_layers_collection"
    echo linked_static_layers_s3_project_folder : "$linked_static_layers_s3_project_folder"
    echo ""
    echo 'WARNING: RTC_S1_STATIC layers are being linked to the RTC_S1 products in STAC metadata'
    echo 'For more information, see the workflow documentation'
fi

## -- CONTAINER PROCESSING SETTINGS --

# set process folders for the container
download_folder="/home/rtc_user/working/downloads"
out_folder="/home/rtc_user/working/results/$s3_project_folder/$collection/$scene"
scratch_folder="/home/rtc_user/working/scratch/$s3_project_folder/$collection/$scene"

echo ""
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

## -- DOWNLOAD DATA AND MAKE THE RUN CONFIG --

cmd=(
    get-data-for-scene-and-make-run-config \
    --scene "$scene" \
    --resolution "$resolution" \
    --output-crs "$output_crs" \
    --dem-type "$dem_type" \
    --product "$product" \
    --s3-bucket "$s3_bucket" \
    --s3-project-folder "$s3_project_folder" \
    --collection "$collection" \
    --download-folder "$download_folder" \
    --scratch-folder "$scratch_folder" \
    --out-folder "$out_folder" \
    --run-config-save-path "$RUN_CONFIG_PATH" \
    --scene-data-source "$scene_data_source" \
    --orbit-data-source "$orbit_data_source" \
)

if [ "$make_existing_products" = true ] ; then
    # make the product even if it already exists
    # WARNING - this may result in duplicates
    cmd+=( --make-existing-products )
fi
if [ "$link_static_layers" = true ] ; then
    # Static layers ARE being linked in the stac metadata
    # A url to the RTC_S1_STATIC product will be added to the RUN_CONFIG
    cmd+=(
        --link-static-layers \
        --linked-static-layers-s3-bucket "$linked_static_layers_s3_bucket" \
        --linked-static-layers-collection "$linked_static_layers_collection" \
        --linked-static-layers-s3-project-folder "$linked_static_layers_s3_project_folder" 
    )
fi

# Conditionally add --burst_id_list only if burst_id_list is non-empty
if [[ ${#burst_id_list[@]} -gt 0 ]]; then
    cmd+=(--burst-id-list "${burst_id_list[*]}")
fi

# Execute the command
"${cmd[@]}"
exit_code=$?

if [ $exit_code -eq 100 ]; then
    echo "Early exit: products already exist for all bursts."
    exit 0  # Graceful exit
fi
if [ $exit_code -ne 0 ]; then
    echo "Process failed: get-data-for-scene-and-make-run-config"
    exit 1
fi

## -- RUN THE WORKFLOW TO PRODUCE RTC_S1 or RTC_S1_STATIC --

conda activate RTC
rtc_s1.py $RUN_CONFIG_PATH

if [ $? -ne 0 ]; then
    echo "Process failed: rtc_s1.py $RUN_CONFIG_PATH"
    exit 1
fi

## -- MAKE THE METADATA FOR PRODUCTS AND UPLOAD TO S3 --

conda activate sar-pipeline

cmd=(
    make-rtc-opera-stac-and-upload-bursts \
    --results-folder "$out_folder" \
    --run-config-path "$RUN_CONFIG_PATH" \
    --product "$product" \
    --collection "$collection" \
    --s3-bucket "$s3_bucket" \
    --s3-project-folder "$s3_project_folder" 
)

if [ "$skip_upload_to_s3" = true ] ; then
    cmd+=( --skip-upload-to-s3)
fi
if [ "$link_static_layers" = true ] ; then
    # Static layers are to be linked to RTC_S1 in the stac metadata
    # The url link to static layers is read in from results .h5 file
    cmd+=( --link-static-layers)
fi
if [ "$validate_stac" = true ] ; then
    # validate the stac doc within the code
    cmd+=( --validate-stac)
fi

# Execute the command
"${cmd[@]}" || { 
    echo "make-rtc-opera-stac-and-upload-bursts"
    exit 1
}
