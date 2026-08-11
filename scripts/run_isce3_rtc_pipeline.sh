#!/bin/bash

# See docs/pipelines/isce3.md for instructions and argument descriptions
## -- WORKFLOW INPUTS FOR PRODUCT CREATION -> RTC_S1 or RTC_S1_STATIC --
scene=""
scene_path="" # url or path to local scene. If None scene is downloaded using scene_data_source
burst_id_list=()
resolution=20
output_crs="UTM"
dem_type="best" # logic to chose best DEM between REMA_32 and glo_cop30
product="RTC_S1"
backscatter_convention=gamma0 # gamma0, sigma0 or beta0
static_layer_validity_start_date=20140403 
s3_bucket="dea-public-data-dev"
s3_project_folder="baseline"
collection_number=1
make_existing_products=false
skip_upload_to_s3=false
scene_data_source=("AUS_COP_HUB" "ASF" "CDSE")
orbit_data_source=("ASF" "CDSE")
skip_validate_stac=false
skip_upload_processed_scene_tracking_file=false
skip_rtc=false
processed_scene_tracking_file_s3_folder="projects/s1_nrb/monitoring"
## -- WORKFLOW INPUTS TO LINK RTC_S1_STATIC in RTC_S1 metadata--
# if link_static_layers, RTC_S1_STATIC products must exist for all RTC_S1 bursts being processed
link_static_layers=false
linked_static_layers_s3_bucket="dea-public-data-dev"
linked_static_layers_s3_project_folder="baseline"
linked_static_layers_collection_number=1

# Final product output paths have the following structure
# RTC_S1
#   - s3_bucket/s3_project_folder/odc_product_name/burst_id/year/month/day/datetime/*files
#   - odc_product_name is determined by the polarisation and collection_number for RTC_S1 products.
#   - the dates in the path refer to the azimuth_time of the burst
#   - It will be one of ga_s1_nrb_iw_vv_vh_X, ga_s1_nrb_iw_vv_X, ga_s1_nrb_iw_hh_hv_X, ga_s1_nrb_iw_hh_X, where X is the collection_number
# RTC_S1_STATIC
#   - e.g. s3_bucket/s3_project_folder/odc_product_name/burst_id/static_layer_validity_start_date/dem_type/*files
#   - odc_product_name = ga_s1_nrb_iw_static_X, where X is the collection_number
#   - if dem type is 'best', it will be replaced by the most suitable DEM in the workflow. e.g. cop_glo30 or REMA_32

# Parse named arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --scene) scene="$2"; shift 2 ;;
        --scene-path) scene_path="$2"; shift 2 ;;
        --resolution) resolution="$2"; shift 2 ;;
        --output-crs) output_crs="$2"; shift 2 ;;
        --dem-type) dem_type="$2"; shift 2 ;;
        --product) product="$2"; shift 2 ;;
        --backscatter-convention) backscatter_convention="$2"; shift 2 ;;
        --static-layer-validity-start-date) static_layer_validity_start_date="$2"; shift 2 ;;
        --s3-bucket) s3_bucket="$2"; shift 2 ;;
        --s3-project-folder) s3_project_folder="$2"; shift 2 ;;
        --collection-number) collection_number="$2"; shift 2 ;;
        --make-existing-products) make_existing_products=true; shift ;;
        --skip-upload-to-s3) skip_upload_to_s3=true; shift ;;
        --link-static-layers) link_static_layers=true; shift ;;
        --linked-static-layers-s3-bucket) linked_static_layers_s3_bucket="$2"; shift 2 ;;
        --linked-static-layers-collection-number) linked_static_layers_collection_number="$2"; shift 2 ;;
        --linked-static-layers-s3-project-folder) linked_static_layers_s3_project_folder="$2"; shift 2 ;;
        --processed-scene-tracking-file-s3-folder) processed_scene_tracking_file_s3_folder="$2"; shift 2 ;;
        --scene-data-source) 
            scene_data_source=()  # clear the default
            shift
            if [[ $# -eq 1 && -f "$1" ]]; then
                scene_data_source=($(cat "$1"))
                shift
            else
                while [[ $# -gt 0 && ! $1 =~ ^-- ]]; do
                    scene_data_source+=("$1")
                    shift
                done
            fi
            ;;
        --orbit-data-source)
            orbit_data_source=()  # clear the default
            shift
            if [[ $# -eq 1 && -f "$1" ]]; then
                orbit_data_source=($(cat "$1"))
                shift
            else
                while [[ $# -gt 0 && ! $1 =~ ^-- ]]; do
                    orbit_data_source+=("$1")
                    shift
                done
            fi
            ;;
        --skip-validate-stac) skip_validate_stac=true; shift ;;
        --skip-rtc) skip_rtc=true; shift ;;
        --burst-id-list)
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
    epsg_code_msg="default UTM for scene center / polar stereographic at latitudes above 60 degrees"
elif [[ "$output_crs" =~ ^[0-9]+$ ]]; then
    epsg_code_msg="EPSG:$output_crs"
else
    echo "Error: --output-crs must be empty, 'UTM', 'utm', or an integer corresponding to an EPSG code (e.g. 3031)."
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
echo scene-path : "$scene_path"
echo burst-id-list : ${burst_id_list[*]}
echo resolution : "$resolution"
echo output-crs : "$epsg_code_msg"
echo dem-type :  "$dem_type"
echo product : "$product"
echo backscatter-convention : "$backscatter_convention"
echo static-layer-validity-start-date : "$static_layer_validity_start_date"
echo s3-bucket : "$s3_bucket"
echo s3-project-folder : "$s3_project_folder"
echo collection-number : "$collection_number"
echo make-existing-products : "$make_existing_products"
echo skip-upload-to-s3 : "$skip_upload_to_s3"
echo scene-data-source : ${scene_data_source[*]}
echo orbit-data-source : ${orbit_data_source[*]}
echo skip-validate-stac : "$skip_validate_stac"
echo processed-scene-tracking-file-s3-folder : "$processed_scene_tracking_file_s3_folder"
echo skip-rtc : "$skip_rtc"

# warn the user about linking static layers
if [[ "$link_static_layers" = true && "$product" = "RTC_S1" ]]; then
    echo linked-static-layers-s3-bucket : "$linked_static_layers_s3_bucket"
    echo linked-static-layers-collection-number : "$linked_static_layers_collection_number"
    echo linked-static-layers-s3-project-folder : "$linked_static_layers_s3_project_folder"
    echo ""
    echo 'WARNING: RTC_S1_STATIC layers are being linked to the RTC_S1 products in STAC metadata'
    echo 'For more information, see the workflow documentation'
fi

## -- CONTAINER PROCESSING SETTINGS --

# set process folders for the container
download_folder="/home/rtc_user/working/downloads"
out_folder="/home/rtc_user/working/results/$s3_project_folder/$collection_number/$product/$scene"
scratch_folder="/home/rtc_user/working/scratch/$s3_project_folder/$collection_number/$product/$scene"

echo ""
echo The container will use these paths for processing:
echo download-folder : "$out_folder"
echo scratch-folder : "$scratch_folder"
echo out-folder : "$out_folder"
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
    isce3-rtc-get-data-for-scene-and-make-run-config \
    --scene "$scene" \
    --scene-path "$scene_path" \
    --resolution "$resolution" \
    --output-crs "$output_crs" \
    --product "$product" \
    --backscatter-convention "$backscatter_convention" \
    --static-layer-validity-start-date "$static_layer_validity_start_date" \
    --s3-bucket "$s3_bucket" \
    --s3-project-folder "$s3_project_folder" \
    --collection-number "$collection_number" \
    --download-folder "$download_folder" \
    --scratch-folder "$scratch_folder" \
    --out-folder "$out_folder" \
    --run-config-save-path "$RUN_CONFIG_PATH" \
)

# Conditionally add --dem-type as a list of preferences
if [[ ${#dem_type[@]} -gt 0 ]]; then
    cmd+=(--dem-type "${dem_type[*]}")
fi
# Conditionally add --scene-data-source as a list of preferences
if [[ ${#scene_data_source[@]} -gt 0 ]]; then
    cmd+=(--scene-data-source "${scene_data_source[*]}")
fi
# Conditionally add --orbit-data-source as a list of preferences
if [[ ${#orbit_data_source[@]} -gt 0 ]]; then
    cmd+=(--orbit-data-source "${orbit_data_source[*]}")
fi


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
        --linked-static-layers-collection-number "$linked_static_layers_collection_number" \
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
    echo "Success (100): Early exit, products already exist for all bursts. Product: $product. Scene: $scene."
    exit 0  # Graceful exit with success code 0 
fi
if [ $exit_code -eq 101 ]; then
    echo "Process failed (101): Required Static Layers are missing. Product: $product. Scene: $scene."
    exit 101
fi
if [ $exit_code -eq 102 ]; then
    echo "Process failed (102): SceneDownloadTimeout. Scene could not be downloaded in allowed time. Check "--scene_data_source" preferences. Product: $product. Scene: $scene."
    exit 102
fi
if [ $exit_code -ne 0 ]; then
    echo "Process failed (1): Error in isce3-rtc-get-data-for-scene-and-make-run-config process. Product: $product. Scene: $scene."
    exit 1
fi

## -- RUN THE WORKFLOW TO PRODUCE RTC_S1 or RTC_S1_STATIC --

if [ "$skip_rtc" = true ]; then
    echo "Skipping RTC step as skip_rtc=true"
else
    conda activate RTC
    rtc_s1.py "$RUN_CONFIG_PATH"

    if [ $? -ne 0 ]; then
        echo "Process failed (2): Error in rtc_s1.py $RUN_CONFIG_PATH process. Product: $product. Scene: $scene."
        exit 2
    fi
fi

## -- MAKE THE METADATA FOR PRODUCTS AND UPLOAD TO S3 --

conda activate sar-pipeline

cmd=(
    isce3-rtc-make-metadata-and-upload-bursts \
    --results-folder "$out_folder" \
    --run-config-path "$RUN_CONFIG_PATH" \
    --scene "$scene" \
    --product "$product" \
    --backscatter-convention "$backscatter_convention" \
    --collection-number "$collection_number" \
    --s3-bucket "$s3_bucket" \
    --s3-project-folder "$s3_project_folder" \
    --processed-scene-tracking-file-s3-folder "$processed_scene_tracking_file_s3_folder"
)

if [ "$skip_upload_to_s3" = true ] ; then
    cmd+=( --skip-upload-to-s3)
fi
if [ "$make_existing_products" = true ] ; then
    # make the product even if it already exists
    # WARNING - this may result in duplicates
    cmd+=( --make-existing-products )
fi
if [ "$link_static_layers" = true ] ; then
    # Static layers are to be linked to RTC_S1 in the stac metadata
    # We get the path to the static layer folder from the .h5 metadata
    cmd+=( --link-static-layers)
fi
if [ "$skip_validate_stac" != true ] ; then
    # validate the stac doc within the code
    cmd+=( --validate-stac)
fi
if [ "$skip_upload_processed_scene_tracking_file" = true ] ; then
    # upload a light {scene}.json file to a monitoring folder that
    # can be easily parsed to check for which scene have been processed
    cmd+=( --skip-upload-processed-scene-tracking-file)
fi

# Execute the command
"${cmd[@]}"
exit_code=$?

if [ $exit_code -ne 0 ]; then
    echo "Process failed (3): Error in isce3-rtc-make-metadata-and-upload-bursts process. Product: $product. Scene: $scene."
    exit 3
else
    echo "Success (0): Required burst products have been created. Product: $product. Scene: $scene."
    exit 0
fi