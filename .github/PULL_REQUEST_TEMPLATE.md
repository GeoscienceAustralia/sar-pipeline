## Description

<!-- What does this PR do and why? -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Documentation
- [ ] Other (refactor, chore, etc.)

## General Checklist

- [ ] Automated tests pass
- [ ] Related issue linked (if applicable)

## isce3_rtc checklist (if this PR touches the isce3_rtc product)

- [ ] Applicable
- [ ] Not Applicable

### Tests

- [ ] Local tests pass `pixi run test-isce3-rtc`. More on testing is provided in the [Developer docs](../docs/development/developer_pixi.md)
- [ ] No changes to products (i.e. `pixi run test-isce3-rtc-full-docker-workflow-run` passes)

### Product Versioning

If product data changes, `product_version` is bumped in `sar_pipeline/configs/isce3_rtc/S1_RTC_IW.yaml` and `sar_pipeline/configs/isce3_rtc/S1_RTC_STATIC_IW.yaml`. E.g. `product_version` is bumped from `1.0.0` to `1.0.1`. This will be reflected in the output product filenames and metadata created by the pipeline. It is not expected to be a common change.
- [ ] S1_RTC_IW and S1_RTC_STATIC_IW versions have been bumped.
- [ ] Versions do not need to be changed.