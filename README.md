# HPC Slurm Job Generator

A lightweight Python/Tkinter application for generating self-contained Slurm job scripts for IMC Steinbock segmentation workflows on HPC systems.

The tool is designed for users who want to configure an IMC analysis run through a simple graphical interface, while still producing a transparent, executable bash script suitable for HPC use. The generated script embeds the stable pipeline logic directly, so it does not require the original launcher script at runtime.

## Purpose

This repository provides a GUI-based job generator for running an IMC Steinbock segmentation pipeline with Slurm resource allocation.

The generated job script can:

- request CPU, GPU, or boost partition resources through Slurm;
- prepare IMC data for Steinbock using `prepare_imc_steinbock.py`;
- load Apptainer on the HPC;
- run Steinbock DeepCell/Mesmer segmentation;
- measure intensities, region properties, and spatial neighbors;
- export final CSV, AnnData, and graph outputs;
- write logs and outputs into a structured project folder.

The application is intended for IMC users who may not want to edit bash scripts manually, but still need reproducible HPC job scripts with explicit resource settings.

## Repository Contents

```text
imc_hpc_job_gui_generator.py
  Python/Tkinter GUI used to generate a self-contained HPC bash script.

prepare_imc_steinbock.py
  Helper script used by the generated bash script to prepare panel.csv,
  images.csv, and stacked Steinbock input images.

run_imc_steinbock_pipeline_slurm_args_v4.sh
  Stable reference pipeline script. The GUI reads this file at generation time
  and embeds its logic into the generated job script.
```

Generated job scripts are not required to call `run_imc_steinbock_pipeline_slurm_args_v4.sh`. They only need `prepare_imc_steinbock.py` in the same folder when run on the HPC.

## How It Works

The workflow has two stages.

First, the GUI is run by the user. The user enters HPC paths and Slurm resource settings, then chooses where to save the generated bash script. The GUI reads the stable v4 pipeline script and writes a new standalone job script.

Second, the generated script is copied or kept on the HPC with `prepare_imc_steinbock.py` in the same directory. When executed, the script requests Slurm resources if needed, then runs the full IMC Steinbock pipeline inside that allocation.

The generated script contains hardcoded settings such as:

```bash
INPUT_DIR="/home/renne/rhussain/inHouseData/test_data"
PROJECT_DIR="/home/renne/rhussain/imcAnalysis/testProject_GPU"
PARTITION="gpu"
NTASKS="1"
MEM="10G"
GPUS="1"
CPUS_PER_TASK="2"
NODELIST="node1"
APPTAINER_MODULE="apptainer/1.2.5"
STEINBOCK_IMAGE="docker://ghcr.io/bodenmillergroup/steinbock:0.16.1"
```

The generated script filename is created automatically using the current date:

```text
jobID_DDMMYY.sh
```

For example:

```text
jobID_260526.sh
```

## Requirements

For the GUI:

- Python 3
- Tkinter
- No external Python packages

For the generated HPC job script:

- Slurm
- Apptainer module available on the HPC
- Steinbock container image:

```text
docker://ghcr.io/bodenmillergroup/steinbock:0.16.1
```

- `prepare_imc_steinbock.py` placed in the same folder as the generated job script
- IMC input data accessible from the HPC filesystem

## Running the GUI

Start the GUI with:

```bash
python imc_hpc_job_gui_generator.py
```

The GUI asks for:

- input data folder on the HPC;
- output project folder on the HPC;
- Slurm partition;
- number of tasks;
- memory;
- CPUs per task;
- number of GPUs for GPU jobs;
- optional node list;
- folder where the generated bash script should be saved.

The input and output paths are HPC filesystem paths, not local laptop paths. They should point to locations that exist or are accessible on the HPC.

Example input path:

```text
/home/renne/rhussain/inHouseData/test_data
```

Example output path:

```text
/home/renne/rhussain/imcAnalysis/testProject_GPU
```

Example save folder:

```text
/home/renne/rhussain/imcAnalysis/jobs
```

If the save folder is selected on May 26, 2026, the generated script path will be:

```text
/home/renne/rhussain/imcAnalysis/jobs/jobID_260526.sh
```

## Running the Generated Job Script

On the HPC, place the generated script and `prepare_imc_steinbock.py` in the same folder.

Example:

```text
/home/renne/rhussain/imcAnalysis/jobs/jobID_260526.sh
/home/renne/rhussain/imcAnalysis/jobs/prepare_imc_steinbock.py
```

Make sure the generated script is executable:

```bash
chmod +x jobID_260526.sh
```

Run it:

```bash
./jobID_260526.sh
```

If the script is launched outside an existing Slurm allocation, it requests the configured resources with `salloc` and then re-runs itself inside the allocated session. If it is already inside a Slurm allocation, it skips the allocation step and runs the pipeline directly.

## Batch Job Behavior

The generated bash script behaves like a self-contained HPC job launcher.

It is not a minimal `sbatch` file with only `#SBATCH` headers. Instead, it uses the stable interactive allocation pattern from the v4 pipeline:

```bash
salloc --partition=... --ntasks=... --mem=... --cpus-per-task=... srun --pty bash ...
```

For GPU jobs, the generated script requests GPU resources using:

```bash
--gres=gpu:N
```

where `N` is the selected number of GPUs.

This design keeps the generated job script portable and explicit: the resource request is visible inside the script, and the same script can detect whether it is already running inside a Slurm job.

## Resource Guidance

For this IMC Steinbock pipeline, the recommended Slurm pattern is:

```text
--ntasks 1
```

The pipeline is not an MPI or multi-node workload. In most cases, increasing `--ntasks` will not make it faster. Scale CPU resources using:

```text
--cpus-per-task
```

### CPU Partition

Recommended for first test runs and general IMC processing.

Suggested settings:

```text
partition: cpu
ntasks: 1
mem: 10G to 20G for small tests
mem: 40G to 80G for normal IMC runs
cpus-per-task: 2 for small tests
cpus-per-task: 4 to 8 for normal runs
```

### GPU Partition

Recommended for DeepCell/Mesmer segmentation when CPU processing is slow.

Suggested settings:

```text
partition: gpu
ntasks: 1
mem: 10G to 20G for small tests
gpus: 1
cpus-per-task: 2 to 4
nodelist: optional, usually node1 or node2
```

GPU nodes are expected to provide NVIDIA Tesla V100 32GB GPUs.

### Boost Partition

The boost partition should be used only if the group has permission to use it.

Known warning:

```text
Job's QOS not permitted to use this partition (boost allows boost not renne)
```

The GUI keeps this warning visible and prevents boost jobs with more than 28 CPUs per task.

## Pipeline Outputs

The generated job script creates a project output structure under:

```text
PROJECT_DIR/steinbock_data
```

Typical outputs include:

```text
panel.csv
images.csv
img/
masks/
intensities/
regionprops/
neighbors/
cells.csv
cells.h5ad
graphs/
```

Logs are written under:

```text
PROJECT_DIR/logs
```

## Important HPC Notes

- Do not run heavy IMC analysis on the frontend node.
- The frontend limit is typically 2 cores and 8 GB RAM.
- The group memory limit is 256G total across running jobs.
- If Slurm memory is not specified, defaults may be very small, such as 1 core and 1G RAM.
- Use absolute HPC paths for input and output folders.
- Keep `prepare_imc_steinbock.py` next to the generated bash script.

## Design Principles

This project intentionally keeps the interface simple and the generated script transparent.

The GUI is responsible for:

- collecting paths and resource choices;
- validating common mistakes;
- warning about risky partition choices;
- embedding the stable pipeline logic;
- writing an executable bash script.

The generated bash script is responsible for:

- requesting Slurm resources;
- preparing Steinbock input files;
- running the containerized Steinbock workflow;
- producing final analysis outputs;
- preserving an execution log.

No external GUI framework or Python package is required.

## Citation and Acknowledgment

This tool is developed for IMC analysis workflows in the Computational Pathology Lab and builds around Steinbock and Apptainer-based HPC execution.

