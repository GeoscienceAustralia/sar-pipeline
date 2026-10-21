## Description

<!-- What does this PR do and why? -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Documentation
- [ ] Other (refactor, chore, etc.)

## Checklist

- [ ] Automated tests pass
- [ ] Related issue linked (if applicable)

## isce3_rtc checklist (if this PR touches the isce3_rtc product)

- [ ] Local docker workflow tests pass (`tests/sar_pipeline/isce3_rtc/test_full_docker_workflow_run.py`). More on testing is provided in the [Developer docs](../docs/development/developer_pixi.md)
- [ ] If product data changes, `product_version` is bumped in `sar_pipeline/configs/isce3_rtc/S1_RTC_IW.yaml` and `sar_pipeline/configs/isce3_rtc/S1_RTC_STATIC_IW.yaml`. This will be reflected in the output products created by the pipeline. E.g. `product_version` is bumped from `1.0.0` to `1.0.1`. 
