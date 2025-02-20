# AWS Pipeline

Build the docker image

```bash
docker build -t sar-pipeline -f Docker/Dockerfile .
```

Test image interactively

```bash
docker run -it sar-pipeline /bin/bash
...
conda run --no-capture-output -n RTC
```
```bash
docker run -it --entrypoint /bin/bash -v $(pwd)/scripts:/home/rtc_user/scratch/scripts sar-pipeline -c 'source scripts/run_aws_pipeline.sh hello'

docker run -it sar-pipeline --scene test_scene --rtc_config IW_20m_antarctica.yaml

```

RTC Command 

```
docker_command = f'rtc_s1.py {opera_config_path}'
```