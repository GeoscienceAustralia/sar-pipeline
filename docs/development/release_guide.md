# ISCE3-RTC Pipeline (s1-nrb-pipeline)

### Steps

1. Branch off from main to develop new features for a planned release.
2. Run the end-to-end tests locally on the branch with proposed changes. Note the local run requires sufficient compute and credentials to be set. 

```bash
# tests that don't require credentials
pixi run test-pipeline-no-creds
# tests to download data from sources. Requires credentials in .env
pixi run test-scene-data-source-queries
# full test of isce3 rtc pipeline. Note may take a few hours as the docker image is
# built and run for a few products. Requires credentials in .env
pixi run test-isce3-rtc
```

3. If successful raise a PR for review and merge branch into main
4. Create new release on GitHub and increment the tag: 
      - Images prior to an initial release should be of for, `v0.X.X`.
      - Test images should be of form `vX.X.X_betaX` 
      - For small changes the tag should be incremented by `0.0.1`. For example, `v1.0.1` -> `v1.0.2`. 
      - Major changes should increment the first or second number, depending on the impact of the change. 
5. The release should trigger the workflow [push-image-to-ecr](../../.github/workflows/push-image-to-ecr.yaml) that will build and push the updated image to the AWS ECR repository.
6. If the automated build and push fails, manually tag and upload the docker image to the ECR repository:

```bash
# set credentials with write to the ECR repo, or use access tool 
# like granted / assume to set credentials
export AWS_ACCESS_KEY_ID=
export AWS_SECRET_ACCESS_KEY=
export AWS_SESSION_TOKEN=

docker build -t sar-pipeline-isce3-rtc -f Docker/isce3_rtc/Dockerfile .

# NOTE - following instructions are for dev account - 451924316694

# tag the local image with the appropriate ECR account tag
docker tag sar-pipeline-isce3-rtc:vX-X-X 451924316694.dkr.ecr.ap-southeast-2.amazonaws.com/dea-dev-s1-nrb-pipeline:vX-X-X

aws ecr get-login-password \
    --region ap-southeast-2 | docker login \
    --username AWS \
    --password-stdin 451924316694.dkr.ecr.ap-southeast-2.amazonaws.com

docker push 451924316694.dkr.ecr.ap-southeast-2.amazonaws.com/dea-dev-s1-nrb-pipeline:vX.X.X
```