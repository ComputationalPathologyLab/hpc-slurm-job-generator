#!/bin/bash
set -euo pipefail

TOTAL_STEPS=8
IMAGE="docker://ghcr.io/bodenmillergroup/steinbock:0.16.1"

run_with_spinner () {
    local label=$1
    shift

    echo ""
    echo "Running: $label"

    "$@" &
    local pid=$!

    local spin='|/-\'
    local i=0

    while kill -0 "$pid" 2>/dev/null; do
        i=$(( (i+1) %4 ))
        printf "\r[%c] %s is running..." "${spin:$i:1}" "$label"
        sleep 0.2
    done

    wait "$pid"
    local status=$?

    if [ "$status" -eq 0 ]; then
        printf "\r[✓] %s completed successfully.          \n" "$label"
    else
        printf "\r[✗] %s failed.                         \n" "$label"
        exit "$status"
    fi
}

print_step () {
    local step=$1
    local title=$2
    local percent=$(( step * 100 / TOTAL_STEPS ))

    echo ""
    echo "============================================================"
    echo "##### STEP ${step}/${TOTAL_STEPS}: ${title} #####"
    echo "Overall progress: ${percent}%"
    echo "============================================================"
    echo ""
}

check_dir () {
    if [ ! -d "$1" ]; then
        echo "ERROR: Directory does not exist: $1"
        exit 1
    fi
}

usage () {
    cat <<EOF
Usage:
  $(basename "$0") --input INPUT_DIR --output PROJECT_DIR --partition cpu|gpu --ntasks N --mem MEM --cpus-per-task N [options]

Required arguments:
  -i, --input PATH          Absolute input folder containing .ome.tiff files
  -o, --output PATH         Absolute output project folder

Required Slurm resource arguments:
  --partition NAME          Slurm partition to use: cpu or gpu

                            cpu partition
                              Nodes       : node[3-9]
                              Time limit  : 10 days
                              Hardware    : 7 CPU nodes total
                                            - 5 nodes with Intel Xeon R 5220
                                            - 2 nodes with Intel Xeon Platinum 8180
                                            - 768 GB RAM per node
                              Best for    : normal IMC pipeline runs

                            gpu partition
                              Nodes       : node[1-2]
                              Time limit  : 10 days
                              Hardware    : 2 GPU nodes
                                            - 96 CPU cores per node
                                            - 768 GB RAM per node
                                            - 2 NVIDIA Tesla V100 32GB GPUs per node
                              Best for    : DeepCell/Mesmer segmentation when GPU is useful
                              Use with    : --gpus 1 or --gres gpu:1

                            boost partition note
                              The HPC guide lists boost as node[8-9], 7 days,
                              max 1 job/week and max 28 cores/job. However,
                              your current Slurm/QoS message shows:
                                boost allows boost not renne
                              This means the renne group is not permitted to use
                              the boost partition at the moment. Use cpu or gpu,
                              or ask HPC support to enable boost QoS for your group.

  --ntasks N                Number of Slurm tasks.

                            Recommended for this pipeline:
                              Always use : --ntasks 1

                            Why:
                              This Steinbock wrapper runs one pipeline process.
                              It is not an MPI/multi-node pipeline, so increasing
                              --ntasks usually will not make it faster.

                            How many can I add?
                              Technically Slurm may allow more tasks depending on
                              the partition, node availability, and your group QoS.
                              However, for this script, keep --ntasks 1 and increase
                              --cpus-per-task instead.

  --mem MEM                 Memory allocation, for example: 10G, 20G, 50G, 100G, 256G.

                            HPC memory information:
                              RAM per compute node     : 768G
                              Group memory limit       : 256G total across all running jobs
                              Default if not specified : max 1G per job

                            Maximum memory you can request:
                              Absolute group maximum   : 256G total
                              Practical max per job    : less than or equal to 256G,
                                                         only if no other group jobs are
                                                         already using that memory

                            Practical advice:
                              Small test ROI           : 10G to 20G
                              Normal IMC run           : 40G to 80G
                              Large IMC run            : 100G to 200G
                              Avoid asking for 256G unless really needed, because it may
                              fail if other jobs from the group are running.

  --cpus-per-task N         CPUs per Slurm task.

                            Recommended for this pipeline:
                              Small test run           : 2
                              Normal IMC run           : 4 to 8
                              Larger CPU run           : 8 to 16
                              Boost partition maximum  : 28 cores/job only if your group has boost QoS

                            Maximum CPUs you can request:
                              cpu partition            : depends on node availability and
                                                         group QoS. CPU nodes have either
                                                         112 or 240 cores per node.
                              gpu partition            : GPU nodes have 96 CPU cores per node,
                                                         but request only what the job needs.
                              boost partition          : max 28 cores/job according to the guide, but not currently allowed for renne QoS.

                            For this script, --cpus-per-task is the main CPU setting.
                            Prefer increasing this instead of --ntasks.

Optional GPU / node arguments:
  --gres VALUE              Generic resource request for GPU partition, for example: gpu:1
                            Equivalent to: --gres=gpu:1 in salloc.
                            The HPC guide also shows --gres=gpu:tesla:1 for batch jobs.

  --gpus N                  Shortcut for GPU request.
                            Example: --gpus 1 adds --gres=gpu:1
                            GPU nodes have 2 Tesla V100 GPUs per node.
                            Use --gpus 1 for normal testing. Use --gpus 2 only if the workflow
                            can really use two GPUs and resources are available.

  --nodelist NODE           Optional Slurm nodelist, for example: node1
                            Example: --nodelist node1

Optional arguments:
  --image IMAGE             Steinbock Apptainer/Docker image
                            Default: $IMAGE
  --apptainer-module NAME   Apptainer module to load
                            Default: apptainer/1.2.5
  --no-salloc               Do not request Slurm allocation. Use this only if you are
                            already inside an allocated Slurm session.
  -h, --help                Show this help message

Important HPC notes:
  Frontend limit            : max 2 cores and 8G RAM. Do not run heavy analysis on frontend.
  node99                    : dedicated pre/post-processing node. It is useful for checking
                              files and preparing data, but normal compute jobs should use Slurm.
  Default Slurm resources   : if not specified, Slurm gives only 1 core and max 1G memory.
  Group memory limit        : 256G total across all running jobs.
  SSH to compute nodes      : direct login to compute nodes is forbidden. Use salloc/srun.
  Use absolute HPC paths    : recommended for both --input and --output.

Recommended IMC commands:

  CPU, small test:
    $(basename "$0") \
      --input /home/renne/rhussain/inHouseData/test_data \
      --output /home/renne/rhussain/imcAnalysis/testProject_CPU \
      --partition cpu \
      --ntasks 1 \
      --mem 10G \
      --cpus-per-task 2

  CPU, normal run:
    $(basename "$0") \
      --input /absolute/input/path \
      --output /absolute/output/path \
      --partition cpu \
      --ntasks 1 \
      --mem 40G \
      --cpus-per-task 8

  GPU run:
    $(basename "$0") \
      --input /home/renne/rhussain/inHouseData/test_data \
      --output /home/renne/rhussain/imcAnalysis/testProject_GPU \
      --partition gpu \
      --ntasks 1 \
      --mem 10G \
      --gpus 1 \
      --cpus-per-task 2 \
      --nodelist node1

  Boost note:
    Do not use --partition boost unless HPC support confirms that the renne
    group has permission to use the boost QoS. Your current Slurm error was:
      Job's QOS not permitted to use this partition (boost allows boost not renne)

Raw interactive Slurm examples from the HPC guide:

  CPU:
    salloc --partition=cpu --ntasks=1 --mem 10G --cpus-per-task=2 srun --pty bash

  GPU:
    salloc --partition=gpu --ntasks=1 --mem 10G --gres=gpu:1 --cpus-per-task=2 srun --pty bash
    Optional: --nodelist=node1

  Boost, only if your group has permission:
    salloc --partition=boost --ntasks=1 --mem 10G --cpus-per-task=2 srun --pty bash
    If it stays pending with "QOS not permitted", cancel it with scancel JOBID.
EOF
}

INPUT_DIR=""
PROJECT_DIR=""
APPTAINER_MODULE="apptainer/1.2.5"
PARTITION=""
NTASKS=""
MEM=""
CPUS_PER_TASK=""
GRES=""
GPUS=""
NODELIST=""
USE_SALLOC=1

ORIGINAL_ARGS=("$@")

while [ "$#" -gt 0 ]; do
    case "$1" in
        -i|--input)
            INPUT_DIR="${2:-}"
            shift 2
            ;;
        -o|--output)
            PROJECT_DIR="${2:-}"
            shift 2
            ;;
        --partition)
            PARTITION="${2:-}"
            shift 2
            ;;
        --ntasks)
            NTASKS="${2:-}"
            shift 2
            ;;
        --mem)
            MEM="${2:-}"
            shift 2
            ;;
        --cpus-per-task)
            CPUS_PER_TASK="${2:-}"
            shift 2
            ;;
        --gres)
            GRES="${2:-}"
            shift 2
            ;;
        --gpus)
            GPUS="${2:-}"
            shift 2
            ;;
        --nodelist)
            NODELIST="${2:-}"
            shift 2
            ;;
        --image)
            IMAGE="${2:-}"
            shift 2
            ;;
        --apptainer-module)
            APPTAINER_MODULE="${2:-}"
            shift 2
            ;;
        --no-salloc)
            USE_SALLOC=0
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "ERROR: Unknown argument: $1"
            echo ""
            usage
            exit 1
            ;;
    esac
done

if [ -z "$INPUT_DIR" ] || [ -z "$PROJECT_DIR" ]; then
    echo "ERROR: --input and --output are required."
    echo ""
    usage
    exit 1
fi

if [ -z "$PARTITION" ] || [ -z "$NTASKS" ] || [ -z "$MEM" ] || [ -z "$CPUS_PER_TASK" ]; then
    echo "ERROR: Slurm resource arguments are required: --partition, --ntasks, --mem, and --cpus-per-task."
    echo ""
    usage
    exit 1
fi

if [[ "$PARTITION" != "cpu" && "$PARTITION" != "gpu" ]]; then
    echo "ERROR: --partition must be one of: cpu or gpu."
    echo ""
    echo "Note about boost:"
    echo "  The HPC guide lists a boost partition, but your Slurm/QoS message shows:"
    echo "  Job's QOS not permitted to use this partition (boost allows boost not renne)"
    echo "  This means your current group/QoS is not allowed to use boost."
    echo "  Use --partition cpu or --partition gpu, or ask HPC support to enable boost access."
    exit 1
fi

if [ "$PARTITION" = "gpu" ] && [ -n "$GPUS" ] && [ "$GPUS" -gt 2 ] 2>/dev/null; then
    echo "ERROR: GPU nodes have 2 Tesla V100 GPUs per node. Use --gpus 1 or --gpus 2."
    exit 1
fi


if ! [[ "$NTASKS" =~ ^[0-9]+$ ]] || [ "$NTASKS" -lt 1 ]; then
    echo "ERROR: --ntasks must be a positive integer."
    exit 1
fi

if ! [[ "$CPUS_PER_TASK" =~ ^[0-9]+$ ]] || [ "$CPUS_PER_TASK" -lt 1 ]; then
    echo "ERROR: --cpus-per-task must be a positive integer."
    exit 1
fi

if ! [[ "$MEM" =~ ^[0-9]+[GgMm]?$ ]]; then
    echo "ERROR: --mem must look like 10G, 20G, 50000M, or 10000."
    exit 1
fi

if [ -n "$GPUS" ]; then
    if ! [[ "$GPUS" =~ ^[0-9]+$ ]] || [ "$GPUS" -lt 1 ]; then
        echo "ERROR: --gpus must be a positive integer, for example: --gpus 1"
        exit 1
    fi
    if [ -n "$GRES" ]; then
        echo "ERROR: use either --gpus or --gres, not both."
        exit 1
    fi
    GRES="gpu:$GPUS"
fi

if [ "$PARTITION" = "gpu" ] && [ -z "$GRES" ]; then
    echo "ERROR: GPU partition requires --gres gpu:1 or --gpus 1."
    exit 1
fi

if [ "$PARTITION" != "gpu" ] && { [ -n "$GRES" ] || [ -n "$GPUS" ]; }; then
    echo "ERROR: --gres/--gpus should only be used with --partition gpu."
    exit 1
fi

# If the script is launched from the login/frontend node, request Slurm resources
# and re-run the same script inside the allocated session. If you are already
# inside a Slurm job, this block is skipped automatically.
if [ "$USE_SALLOC" -eq 1 ] && [ -z "${SLURM_JOB_ID:-}" ]; then
    echo ""
    echo "Requesting Slurm resources:"
    echo "  partition      : $PARTITION"
    echo "  ntasks         : $NTASKS"
    echo "  mem            : $MEM"
    echo "  cpus-per-task  : $CPUS_PER_TASK"
    if [ -n "$GRES" ]; then
        echo "  gres           : $GRES"
    fi
    if [ -n "$NODELIST" ]; then
        echo "  nodelist       : $NODELIST"
    fi
    echo ""

    SALLOC_CMD=(
      salloc
      --partition="$PARTITION"
      --ntasks="$NTASKS"
      --mem="$MEM"
      --cpus-per-task="$CPUS_PER_TASK"
    )

    if [ -n "$GRES" ]; then
        SALLOC_CMD+=(--gres="$GRES")
    fi

    if [ -n "$NODELIST" ]; then
        SALLOC_CMD+=(--nodelist="$NODELIST")
    fi

    exec "${SALLOC_CMD[@]}" srun --pty bash "$0" "${ORIGINAL_ARGS[@]}" --no-salloc
fi

INPUT_DIR=$(realpath "$INPUT_DIR")
PROJECT_DIR=$(realpath -m "$PROJECT_DIR")

echo ""
echo "============================================================"
echo "          IMC Steinbock Segmentation Pipeline"
echo "============================================================"
echo ""

DATA="$PROJECT_DIR/steinbock_data"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/pipeline_$(date +%Y%m%d_%H%M%S).log"

mkdir -p "$DATA" "$LOG_DIR"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "Start time: $(date)"
echo "Hostname: $(hostname)"
echo "User: $(whoami)"
echo ""
echo "Input folder: $INPUT_DIR"
echo "Project folder: $PROJECT_DIR"
echo "Steinbock data folder: $DATA"
echo "Log file: $LOG_FILE"
echo ""
echo "Slurm resources:"
echo "  SLURM_JOB_ID    : ${SLURM_JOB_ID:-not inside Slurm allocation}"
echo "  partition       : $PARTITION"
echo "  ntasks          : $NTASKS"
echo "  mem             : $MEM"
echo "  cpus-per-task   : $CPUS_PER_TASK"
echo "  gres            : ${GRES:-none}"
echo "  nodelist        : ${NODELIST:-none}"

print_step 1 "VALIDATING INPUT DATA"

check_dir "$INPUT_DIR"

echo "Checking input folder and OME-TIFF files..."

TIFF_COUNT=$(python - "$INPUT_DIR" <<'PY'
from pathlib import Path
import sys

p = Path(sys.argv[1])
files = list(p.rglob("*.ome.tiff"))
print(len(files))
PY
)

echo "OME-TIFF files detected: $TIFF_COUNT"

if [ "$TIFF_COUNT" -eq 0 ]; then
    echo "ERROR: No .ome.tiff files found."
    echo "Please check that the input path contains files ending with .ome.tiff"
    exit 1
fi

print_step 2 "CREATING PANEL.CSV AND STACKED IMAGES"

run_with_spinner "Panel creation and image stacking" \
  python "$(dirname "$0")/prepare_imc_steinbock.py" \
  --input "$INPUT_DIR" \
  --output "$DATA" \
  --force

echo ""
echo "Generated Steinbock input files:"
ls -lh "$DATA"

print_step 3 "LOADING APPTAINER AND TESTING STEINBOCK"

echo "Loading Apptainer module..."
module load "$APPTAINER_MODULE"

run_with_spinner "Testing Steinbock container" \
  apptainer exec "$IMAGE" steinbock --version

print_step 4 "RUNNING DEEPCELL SEGMENTATION"

run_with_spinner "DeepCell whole-cell segmentation" \
  apptainer exec \
  --bind "$DATA":/data \
  "$IMAGE" \
  steinbock segment deepcell \
  --img /data/img \
  --panel /data/panel.csv \
  --type whole-cell \
  -o /data/masks

echo ""
echo "Masks generated:"
ls -lh "$DATA/masks"

print_step 5 "MEASURING INTENSITIES"

run_with_spinner "Measuring object intensities" \
  apptainer exec \
  --bind "$DATA":/data \
  "$IMAGE" \
  steinbock measure intensities \
  --img /data/img \
  --masks /data/masks \
  --panel /data/panel.csv \
  -o /data/intensities

echo ""
echo "Intensity files generated:"
ls -lh "$DATA/intensities"

print_step 6 "MEASURING REGION PROPERTIES"

run_with_spinner "Measuring region properties" \
  apptainer exec \
  --bind "$DATA":/data \
  "$IMAGE" \
  steinbock measure regionprops \
  --img /data/img \
  --masks /data/masks \
  -o /data/regionprops

echo ""
echo "Region property files generated:"
ls -lh "$DATA/regionprops"

print_step 7 "MEASURING NEIGHBORS"

run_with_spinner "Measuring spatial neighbors" \
  apptainer exec \
  --bind "$DATA":/data \
  "$IMAGE" \
  steinbock measure neighbors \
  --masks /data/masks \
  --type centroids \
  --kmax 10 \
  -o /data/neighbors

echo ""
echo "Neighbor files generated:"
ls -lh "$DATA/neighbors"

print_step 8 "EXPORTING FINAL DATA OBJECTS"

run_with_spinner "Exporting combined CSV" \
  apptainer exec \
  --bind "$DATA":/data \
  "$IMAGE" \
  steinbock export csv \
  /data/intensities /data/regionprops \
  -o /data/cells.csv

run_with_spinner "Exporting AnnData object" \
  apptainer exec \
  --bind "$DATA":/data \
  "$IMAGE" \
  steinbock export anndata \
  --intensities /data/intensities \
  --data /data/regionprops \
  --neighbors /data/neighbors \
  -o /data/cells.h5ad

run_with_spinner "Exporting spatial graphs" \
  apptainer exec \
  --bind "$DATA":/data \
  "$IMAGE" \
  steinbock export graphs \
  --format graphml \
  --data /data/intensities \
  --data /data/regionprops \
  --neighbors /data/neighbors \
  -o /data/graphs

echo ""
echo "Exported final files:"
ls -lh "$DATA"/cells.csv "$DATA"/cells.h5ad 2>/dev/null || true
ls -lh "$DATA"/graphs 2>/dev/null || true

echo ""
echo "============================================================"
echo "PIPELINE COMPLETED SUCCESSFULLY"
echo "============================================================"
echo ""
echo "Input folder:"
echo "$INPUT_DIR"
echo ""
echo "Output folder:"
echo "$DATA"
echo ""
echo "Generated outputs:"
echo "  panel.csv"
echo "  images.csv"
echo "  img/"
echo "  masks/"
echo "  intensities/"
echo "  regionprops/"
echo "  neighbors/"
echo "  cells.csv"
echo "  cells.h5ad"
echo "  graphs/"
echo ""
echo "Completion time: $(date)"
echo ""
echo "Log file:"
echo "$LOG_FILE"
echo ""