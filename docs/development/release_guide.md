# AWS Opera/iSCE3 Pipeline

### Steps

1. Branch off from main to develop new features for a planned release.
2. Run the end-to-end tests locally on the branch with proposed changes. Note the local run requires sufficient compute and credentials to be set. 

```bash
# test command line tools
pixi run test-aws-cli 

# test docker image build and test run
pixi run test-full-aws-docker-run
```
3. If successful raise a PR for review and merge branch into main
4. Create new release on GitHub and increment the tag: 
      - Images prior to an initial release should be of for, `v0.X.X`.
      - Test images should be of form `vX.X.X_betaX` 
      - For small changes the tag should be incremented by `0.0.1`. For example, `v1.0.1` -> `v1.0.2`. 
      - Major changes should increment the first or second number, depending on the impact of the change. 
5. When the release made, the `push-image-to-ecr.yaml` github action will be run. A new image will be built, tagged and pushed to ECR according to the release tag. E.g. `sar_pipeline:v1.0,1`