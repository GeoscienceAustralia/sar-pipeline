## Description

Add description here

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

- [ ] Local tests pass `pixi run test-isce3-rtc`. More on testing is provided in the [testing section of isce3_rtc.md](../docs/pipelines/isce3_rtc.md#51-running-tests)
- [ ] No changes to products when compared to benchmark / golden burst products (i.e. `pixi run test-isce3-rtc-full-docker-workflow-run` passes)

### Product Versioning (Product Data has Changed)

If product data changes (for example, a bugfix in the ISCE3 software changes pixel locations), `product_version` should be bumped in [S1_RTC_IW.yaml](../sar_pipeline/configs/isce3_rtc/S1_RTC_IW.yaml) and [S1_RTC_STATIC_IW.yaml](../sar_pipeline/configs/isce3_rtc/S1_RTC_STATIC_IW.yaml). E.g. `product_version` is bumped from `1.0.0` to `1.0.1`. This will be reflected in the output product filenames and metadata created by the pipeline. 
- [ ] S1_RTC_IW and S1_RTC_STATIC_IW versions have been bumped.
- [ ] Benchmark data for tests have been updated (see [Updating Test Data in isce3_rtc.md](../docs/pipelines/isce3_rtc.md#52-updating-test-data))
- [ ] Versions do not need to be changed.