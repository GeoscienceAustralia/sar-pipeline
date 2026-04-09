from sar_pipeline.pipelines.pyrosar_gamma.metadata.stac import GammaNRBtoSTAC

SCENE_ID = "S1A_EW_GRDM_1SDH_20190103T112546_20190103T112656_025312_02CCF2_83F6"
SCENE_DIR = f"sar-processing/s1_rtc/data/processed_scene/{SCENE_ID}"

stac = GammaNRBtoSTAC(
    scene_id=SCENE_ID,
    product_folder=SCENE_DIR,
    backscatter_convention="gamma0",
    collection_number=1,
    s3_bucket="dea-public-data-dev",
    s3_project_folder="experimental/baseline",
)


stac.make_stac_item()
stac.add_properties()
stac.rename_asset_files()
stac.add_assets()
stac.save(f"{SCENE_DIR}/{SCENE_ID}_stac-item.json")
