# Project set up

Our project is currently designed to be installed from source.
We may offer alternatives in future.

## From source
The first step is to clone the source code.
Navigate to the place you want to keep your development. 

> **_NOTE:_** On the NCI, our suggestions are:
> - home directory: `~/`
> - user directory in project: `/g/data/<project>/<nci-username>/`

Clone the repository into the chosen directory using
```bash
git clone https://github.com/GeoscienceAustralia/sar-pipeline.git
```

### Installing the package
We have different recommendations for how you install from source depending on whether you are using the package, or developing it. 

- If you are a developer, see [developer set up](developer_pixi.md)
- If you want to use the package, without modifying the code, see [user set up](user_conda.md)

## Alternatives

On the NCI, we are in the process of developing a way of accessing this package via a module. 
> **_NOTE:_** NCI module approach is still under development.
> See [NCI Module set up](nci.md)