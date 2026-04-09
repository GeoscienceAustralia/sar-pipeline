#!/usr/bin/env bash
set -e

scene=""
dem_type="best"
download_folder="sar-processing/downloads"
out_folder="sar-processing/s1_rtc"
scene_data_source="AUS_COP_HUB ASF CDSE"
orbit_data_source="AUS_COP_HUB ASF CDSE"
geocode_spacing=20
geocode_scaling="both"
etad=""
target_crs="3031"
backscatter_convention="gamma0"
collection_number=1
s3_bucket="dea-public-data-dev"
s3_project_folder="experimental/baseline"
skip_upload_to_s3=false
make_existing_products=false
validate_stac=true
skip_upload_processed_scene_tracking_file=false
product_version="1-0-0"

# Parse named arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --scene) scene="$2"; shift 2 ;;
        --dem-type) dem_type="$2"; shift 2 ;;
        --download-folder) download_folder="$2"; shift 2 ;;
        --out-folder) out_folder="$2"; shift 2 ;;
        --scene-data-source) scene_data_source="$2"; shift 2 ;;
        --orbit-data-source) orbit_data_source="$2"; shift 2 ;;
        --geocode-spacing) geocode_spacing="$2"; shift 2 ;;
        --geocode-scaling) geocode_scaling="$2"; shift 2 ;;
        --etad) etad="$2"; shift 2 ;;
        --target-crs) target_crs="$2"; shift 2 ;;
        --backscatter-convention) backscatter_convention="$2"; shift 2 ;;
        --collection-number) collection_number="$2"; shift 2 ;;
        --s3-bucket) s3_bucket="$2"; shift 2 ;;
        --s3-project-folder) s3_project_folder="$2"; shift 2 ;;
        --skip-upload-to-s3) skip_upload_to_s3="$2"; shift 2 ;;
        --make-existing-products) make_existing_products="$2"; shift 2 ;;
        --validate-stac) validate_stac="$2"; shift 2 ;;
        --skip-upload-processed-scene-tracking-file) skip_upload_processed_scene_tracking_file="$2"; shift 2 ;;
        --product-version) product_version="$2"; shift 2 ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
done

# Check if 'scene' is provided
if [[ -z "$scene" ]]; then
    echo "Error: --scene is a required parameter."
    exit 1
fi

results_folder="$out_folder/data/processed_scene/$scene"

echo ""
echo The input variables are:
echo scene : "$scene"
echo dem_type : "$dem_type"
echo download_folder : "$download_folder"
echo out_folder : "$out_folder"
echo scene_data_source : "$scene_data_source"
echo orbit_data_source : "$orbit_data_source"
echo geocode_spacing : "$geocode_spacing"
echo geocode_scaling : "$geocode_scaling"
echo etad : "$etad"
echo target_crs : "$target_crs"
echo results_folder : "$results_folder"
echo backscatter_convention : "$backscatter_convention"
echo collection_number : "$collection_number"
echo s3_bucket : "$s3_bucket"
echo s3_project_folder : "$s3_project_folder"
echo skip_upload_to_s3 : "$skip_upload_to_s3"
echo make_existing_products : "$make_existing_products"
echo validate_stac : "$validate_stac"
echo skip_upload_processed_scene_tracking_file : "$skip_upload_processed_scene_tracking_file"
echo product_version : "$product_version"
echo ""


# run the cli with pixi
pixi run pyrosar-gamma-rtc-run-workflow --scene "$scene" \
    --dem-type "$dem_type" \
    --download-folder "$download_folder" \
    --out-folder "$out_folder" \
    --scene-data-source "$scene_data_source" \
    --orbit-data-source "$orbit_data_source" \
    --geocode-spacing "$geocode_spacing" \
    --geocode-scaling "$geocode_scaling" \
    --target-crs "$target_crs" \
    ${etad:+--etad "$etad"}

pixi run pyrosar-gamma-make-metadata-and-upload-product --scene "$scene" \
    --results-folder "$results_folder" \
    --backscatter-convention "$backscatter_convention" \
    --collection-number "$collection_number" \
    --s3-bucket "$s3_bucket" \
    --s3-project-folder "$s3_project_folder" \
    --product-version "$product_version" \
    $([[ "$skip_upload_to_s3" = true ]] && printf -- '--skip-upload-to-s3') \
    $([[ "$make_existing_products" = true ]] && printf -- '--make-existing-products') \
    $([[ "$validate_stac" = true ]] && printf -- '--validate-stac') \
    $([[ "$skip_upload_processed_scene_tracking_file" = true ]] && printf -- '--skip-upload-processed-scene-tracking-file')
