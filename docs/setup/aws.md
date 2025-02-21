# AWS Pipeline

Build the docker image

```bash
docker build -t sar-pipeline -f Docker/Dockerfile .
```

Test image interactively

```bash
 docker run -it --entrypoint /bin/bash sar-pipeline
...
conda run --no-capture-output -n RTC
```
```bash

docker run --env-file env.secret -it sar-pipeline --scene S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD --base_rtc_config IW_20m_antarctica.yaml

```

RTC Command 

```
docker_command = f'rtc_s1.py {opera_config_path}'
```