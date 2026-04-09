from sar_pipeline.pipelines.pyrosar_gamma.metadata.stac import GammaNRBtoSTAC

SCENE_ID = "S1A_EW_GRDM_1SDH_20250303T112244_20250303T112308_058139_072E6F_DB7E"
SCENE_DIR = f"sar-processing/s1_rtc/data/final_product/{SCENE_ID}"
stac_file_path = f"{SCENE_DIR}/{SCENE_ID}_stac-item.json"

stac = GammaNRBtoSTAC(
    scene_id=SCENE_ID,
    product_folder=SCENE_DIR,
    backscatter_convention="gamma0",
    collection_number=1,
    s3_bucket="dea-public-data-dev",
    s3_project_folder="experimental/baseline",
    orbit_source="POE precise orbit",
)


stac.make_stac_item()
stac.add_properties()
stac.rename_asset_files()
stac.add_assets()
stac.add_metadata_links(stac_file_path)
stac.add_collection_link()
stac.save(stac_file_path)
