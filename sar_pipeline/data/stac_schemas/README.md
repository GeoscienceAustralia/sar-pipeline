# Vendored STAC schemas

Local copies of the STAC extension schemas declared by the isce3_rtc burst products
(`STAC_EXTENSIONS` and `RTC_S1_STAC_EXTENSIONS` in
`sar_pipeline/pipelines/isce3_rtc/metadata/stac.py`), plus the remote schemas they
`$ref` (projjson and the storage platform schemas). They are loaded by
`sar_pipeline.utils.stac_schemas.use_local_stac_schemas` so STAC validation does not
download schemas at runtime. The core STAC 1.1.0 and GeoJSON schemas are bundled with
pystac and are not duplicated here.

`index.json` maps each schema URI to its file. Files were downloaded unmodified from
their URIs. When an extension version changes in `stac.py`, add the new schema (and
any new remote `$ref` targets) here and update `index.json`;
`tests/sar_pipeline/test_offline_stac_validation.py` fails if a declared schema is
missing or a schema would still be fetched over the network.
