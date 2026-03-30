from sar_pipeline.pipelines.pyrosar_gamma.metadata.stac import GammaNRBtoSTAC

scene_id = "S1A_EW_GRDM_1SDH_20190103T112546_20190103T112656_025312_02CCF2_83F6"

stac = GammaNRBtoSTAC(
    scene_id=scene_id,
    product_folder=f"TMP/{scene_id}",
    backscatter_convention="gamma0",
    crs = 3031,
    resolution=40,
    collection_number=1,
    s3_bucket="TMP",
    s3_project_folder="TMP",
)


stac.make_stac_item_from_h5()
stac.add_properties()
stac.rename_asset_files()
stac.add_assets()
stac.save(f"TMP/{scene_id}/{scene_id}_stac-item.json")