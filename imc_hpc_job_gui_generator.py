#!/usr/bin/env python3
"""
IMC HPC Job GUI Generator

README-style usage
------------------
Run this GUI on a machine with Python/Tkinter:

  python imc_hpc_job_gui_generator.py

Fill in the IMC input folder, output project folder, Slurm resources,
and the folder where the generated bash script should be saved. Click
"Refresh preview" to inspect the selected HPC paths and embedded resource
settings, then click "Generate bash script".

The generated bash script:
  - contains the selected settings hardcoded at the top;
  - embeds the stable v4 pipeline source for traceability;
  - runs the same stable v4 pipeline logic directly;
  - does not call run_imc_steinbock_pipeline_slurm_args_v4.sh externally;
  - only requires prepare_imc_steinbock.py in the same folder at runtime.

No external Python dependencies are needed. This file uses only the standard
library and Tkinter.
"""

from __future__ import annotations

import re
import stat
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

APP_TITLE = "IMC Steinbock HPC Job Generator"
PIPELINE_SCRIPT = "run_imc_steinbock_pipeline_slurm_args_v4.sh"
PREPARE_SCRIPT = "prepare_imc_steinbock.py"
DEFAULT_APPTAINER_MODULE = "apptainer/1.2.5"
DEFAULT_STEINBOCK_IMAGE = "docker://ghcr.io/bodenmillergroup/steinbock:0.16.1"

PARTITION_HELP = {
    "cpu": (
        "CPU partition selected\n"
        "Nodes: node[3-9]\n"
        "Time limit: 10 days\n"
        "Good default for IMC pipeline\n"
        "Recommended for first test runs\n\n"
        "Suggested resources:\n"
        "  --ntasks 1\n"
        "  --mem 10G to 20G for small tests\n"
        "  --mem 40G to 80G for normal IMC runs\n"
        "  --cpus-per-task 2 for small tests\n"
        "  --cpus-per-task 4 to 8 for normal runs\n\n"
        "Increase cpus-per-task rather than ntasks for this pipeline."
    ),
    "gpu": (
        "GPU partition selected\n"
        "Nodes: node[1-2]\n"
        "Time limit: 10 days\n"
        "Each GPU node has 2 NVIDIA Tesla V100 32GB GPUs\n"
        "Use for DeepCell/Mesmer segmentation if CPU is slow\n\n"
        "Suggested resources:\n"
        "  --ntasks 1\n"
        "  --mem 10G to 20G for small tests\n"
        "  --gpus 1\n"
        "  --cpus-per-task 2 to 4\n"
        "  Optional nodelist can be node1 or node2.\n\n"
        "The generated Slurm request uses --gres=gpu:N, matching the stable v4 --gpus shortcut."
    ),
    "boost": (
        "Boost partition selected\n"
        "Nodes: node[8-9]\n"
        "Time limit: 7 days\n"
        "Max 28 cores per job\n"
        "Max 1 job per week\n\n"
        "Important warning:\n"
        "Our group may not be permitted to use boost. We previously saw:\n"
        "  Job's QOS not permitted to use this partition (boost allows boost not renne)\n\n"
        "The GUI will ask you to confirm before generating a boost script."
    ),
}

GENERAL_HELP = (
    "General HPC limits\n"
    "Frontend node should not be used for heavy computation.\n"
    "Frontend limit: 2 cores and 8 GB RAM.\n"
    "Group memory limit: 256G total across all running jobs.\n"
    "If memory is not specified by Slurm, default may be only 1 core and 1G RAM.\n"
    "For this IMC pipeline, normally use --ntasks 1 and scale using --cpus-per-task."
)

MEMORY_HELP = (
    "Memory guidance\n"
    "Small tests: 10G to 20G\n"
    "Normal IMC runs: 40G to 80G\n"
    "Large runs: 100G to 200G\n"
    "Group memory limit: 256G total across all running jobs."
)

TASKS_HELP = (
    "Tasks guidance\n"
    "For this Steinbock pipeline, normally use ntasks = 1.\n"
    "This pipeline is not an MPI/multi-node workflow.\n"
    "If you need more CPU power, increase cpus-per-task rather than ntasks."
)

CPU_HELP = (
    "CPUs per task guidance\n"
    "Small test: 2\n"
    "Normal IMC run: 4 to 8\n"
    "Boost partition maximum: 28 cores per job."
)


def sh_quote(value: str) -> str:
    """Return a safe single-quoted shell string."""
    return "'" + value.replace("'", "'\"'\"'") + "'"


def memory_to_gb(memory: str) -> float | None:
    """Parse simple Slurm memory strings like 10G or 50000M into GB."""
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)([GgMm]?)\s*", memory)
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2).upper()
    if unit == "M":
        return amount / 1024
    return amount


class JobGenerator(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1100x780")
        self.minsize(980, 680)

        self.input_dir = tk.StringVar(value="/home/renne/rhussain/inHouseData/test_data")
        self.output_dir = tk.StringVar(value="/home/renne/rhussain/imcAnalysis/testProject_GPU")
        self.partition = tk.StringVar(value="gpu")
        self.ntasks = tk.StringVar(value="1")
        self.mem = tk.StringVar(value="10G")
        self.cpus_per_task = tk.StringVar(value="2")
        self.gpus = tk.StringVar(value="1")
        self.nodelist = tk.StringVar(value="node1")
        self.save_folder = tk.StringVar(value=str(Path.cwd()))

        self._build_ui()
        self._update_partition_ui()
        self._refresh_preview()

    def _build_ui(self) -> None:
        main = ttk.Frame(self, padding=12)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text=APP_TITLE, font=("TkDefaultFont", 16, "bold")).pack(anchor="w")
        ttk.Label(
            main,
            text=(
                "Generate one self-contained HPC bash script for the IMC Steinbock pipeline. "
                "The generated script embeds the stable v4 logic and does not call v4 externally."
            ),
            wraplength=1040,
        ).pack(anchor="w", pady=(4, 12))

        body = ttk.PanedWindow(main, orient="horizontal")
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body, padding=(0, 0, 10, 0))
        right = ttk.Frame(body, padding=(10, 0, 0, 0))
        body.add(left, weight=3)
        body.add(right, weight=2)

        form = ttk.LabelFrame(left, text="Job settings", padding=10)
        form.pack(fill="x")

        self._path_row(form, 0, "Input data folder on HPC", self.input_dir, self._browse_input)
        self._hint_row(form, 1, "Example: /home/renne/rhussain/inHouseData/test_data")
        self._path_row(form, 2, "Output project folder on HPC", self.output_dir, self._browse_output)
        self._hint_row(form, 3, "Example: /home/renne/rhussain/imcAnalysis/testProject_GPU")
        self._hint_row(
            form,
            4,
            "These paths must exist or be accessible on the HPC. They are not local laptop paths.",
        )

        ttk.Label(form, text="Partition").grid(row=5, column=0, sticky="w", pady=4)
        part_box = ttk.Combobox(
            form,
            textvariable=self.partition,
            values=("cpu", "gpu", "boost"),
            state="readonly",
            width=18,
        )
        part_box.grid(row=5, column=1, sticky="ew", pady=4)
        part_box.bind("<<ComboboxSelected>>", lambda _event: self._update_partition_ui())
        ttk.Button(
            form,
            text="Help",
            command=lambda: self._show_help("Partition guidance", PARTITION_HELP[self.partition.get()]),
        ).grid(row=5, column=2, padx=4)

        self._entry_row(form, 6, "Number of tasks", self.ntasks, TASKS_HELP)
        self._entry_row(form, 7, "Memory", self.mem, MEMORY_HELP)
        self._entry_row(form, 8, "CPUs per task", self.cpus_per_task, CPU_HELP)

        self.gpu_row_label = ttk.Label(form, text="Number of GPUs")
        self.gpu_row_entry = ttk.Entry(form, textvariable=self.gpus, width=20)
        self.gpu_row_help = ttk.Button(
            form,
            text="Help",
            command=lambda: self._show_help(
                "GPU guidance",
                "Normally use 1 GPU. GPU nodes are node1 and node2. Each GPU node has 2 NVIDIA Tesla V100 32GB GPUs.",
            ),
        )
        self.gpu_row_label.grid(row=9, column=0, sticky="w", pady=4)
        self.gpu_row_entry.grid(row=9, column=1, sticky="ew", pady=4)
        self.gpu_row_help.grid(row=9, column=2, padx=4)

        self.node_row_label = ttk.Label(form, text="Optional nodelist")
        self.node_row_entry = ttk.Entry(form, textvariable=self.nodelist, width=20)
        self.node_row_help = ttk.Button(
            form,
            text="Help",
            command=lambda: self._show_help(
                "Node list guidance",
                "Optional. For GPU jobs, node1 or node2 can be useful. Leave blank if Slurm should choose.",
            ),
        )
        self.node_row_label.grid(row=10, column=0, sticky="w", pady=4)
        self.node_row_entry.grid(row=10, column=1, sticky="ew", pady=4)
        self.node_row_help.grid(row=10, column=2, padx=4)

        self._path_row(form, 11, "Save generated bash script in folder", self.save_folder, self._browse_save_folder)
        self.generated_name_label = ttk.Label(form, text="", foreground="#555555")
        self.generated_name_label.grid(row=12, column=1, sticky="w", pady=(0, 4))
        self._hint_row(
            form,
            13,
            f"Apptainer and Steinbock image are fixed internally: {DEFAULT_APPTAINER_MODULE}; {DEFAULT_STEINBOCK_IMAGE}",
        )

        form.columnconfigure(1, weight=1)

        buttons = ttk.Frame(left)
        buttons.pack(fill="x", pady=10)
        ttk.Button(buttons, text="Validate fields", command=self._validate_and_report).pack(side="left")
        ttk.Button(buttons, text="Refresh preview", command=self._refresh_preview).pack(side="left", padx=6)
        ttk.Button(buttons, text="Generate bash script", command=self._generate_script).pack(side="right")

        preview_frame = ttk.LabelFrame(left, text="Generated script preview", padding=8)
        preview_frame.pack(fill="both", expand=True)
        self.preview = tk.Text(preview_frame, height=18, wrap="none")
        self.preview.pack(side="left", fill="both", expand=True)
        yscroll = ttk.Scrollbar(preview_frame, orient="vertical", command=self.preview.yview)
        yscroll.pack(side="right", fill="y")
        xscroll = ttk.Scrollbar(preview_frame, orient="horizontal", command=self.preview.xview)
        xscroll.pack(side="bottom", fill="x")
        self.preview.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        help_frame = ttk.LabelFrame(right, text="HPC guidance", padding=8)
        help_frame.pack(fill="both", expand=True)
        self.help_text = tk.Text(help_frame, wrap="word", height=25)
        self.help_text.pack(side="left", fill="both", expand=True)
        help_scroll = ttk.Scrollbar(help_frame, orient="vertical", command=self.help_text.yview)
        help_scroll.pack(side="right", fill="y")
        self.help_text.configure(yscrollcommand=help_scroll.set)

        for var in (
            self.input_dir,
            self.output_dir,
            self.partition,
            self.ntasks,
            self.mem,
            self.cpus_per_task,
            self.gpus,
            self.nodelist,
            self.save_folder,
        ):
            var.trace_add("write", lambda *_args: self._refresh_preview())

    def _path_row(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar, command) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=4)
        ttk.Button(parent, text="Browse", command=command).grid(row=row, column=2, padx=4)

    def _hint_row(self, parent: ttk.Frame, row: int, text: str) -> None:
        ttk.Label(parent, text=text, foreground="#555555", wraplength=560).grid(
            row=row,
            column=1,
            columnspan=2,
            sticky="w",
            pady=(0, 4),
        )

    def _entry_row(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar, help_text: str) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=variable, width=20).grid(row=row, column=1, sticky="ew", pady=4)
        ttk.Button(parent, text="Help", command=lambda: self._show_help(label, help_text)).grid(row=row, column=2, padx=4)

    def _browse_input(self) -> None:
        selected = filedialog.askdirectory(title="Select input data folder on HPC, if mounted/browsable")
        if selected:
            self.input_dir.set(selected)

    def _browse_output(self) -> None:
        selected = filedialog.askdirectory(title="Select output project folder on HPC, if mounted/browsable")
        if selected:
            self.output_dir.set(selected)

    def _browse_save_folder(self) -> None:
        selected = filedialog.askdirectory(title="Select folder for generated bash script")
        if selected:
            self.save_folder.set(selected)

    def _show_help(self, title: str, text: str) -> None:
        self.help_text.delete("1.0", "end")
        self.help_text.insert("1.0", f"{title}\n{'=' * len(title)}\n\n{text}\n\n{GENERAL_HELP}")

    def _update_partition_ui(self) -> None:
        part = self.partition.get().strip()
        if part == "gpu":
            self.gpu_row_label.grid()
            self.gpu_row_entry.grid()
            self.gpu_row_help.grid()
            if not self.gpus.get().strip():
                self.gpus.set("1")
            if not self.nodelist.get().strip():
                self.nodelist.set("node1")
        else:
            self.gpu_row_label.grid_remove()
            self.gpu_row_entry.grid_remove()
            self.gpu_row_help.grid_remove()
            self.gpus.set("")
            if part == "cpu" and self.nodelist.get().strip() in {"node1", "node2"}:
                self.nodelist.set("")
        self._show_help("Partition guidance", PARTITION_HELP.get(part, ""))
        self._refresh_preview()

    def _v4_path(self) -> Path:
        return Path(__file__).resolve().with_name(PIPELINE_SCRIPT)

    def _read_v4_source(self) -> str:
        path = self._v4_path()
        if not path.exists():
            raise FileNotFoundError(
                f"Cannot find {PIPELINE_SCRIPT} beside this GUI. "
                "It is needed only while generating, so its stable logic can be embedded."
            )
        return path.read_text(encoding="utf-8")

    def _extract_v4_runtime_sections(self, source: str) -> tuple[str, str]:
        lines = source.splitlines()
        try:
            definitions_start = next(i for i, line in enumerate(lines) if line.startswith("TOTAL_STEPS="))
            config_start = next(i for i, line in enumerate(lines) if line == 'INPUT_DIR=""')
            runtime_start = next(i for i, line in enumerate(lines) if line.startswith("# If the script is launched"))
        except StopIteration as exc:
            raise ValueError(f"{PIPELINE_SCRIPT} does not look like the expected stable v4 script.") from exc

        definitions = "\n".join(lines[definitions_start:config_start]).rstrip()
        runtime = "\n".join(lines[runtime_start:]).rstrip()
        return definitions, runtime

    def _settings(self) -> dict[str, str]:
        return {
            "input": self.input_dir.get().strip(),
            "output": self.output_dir.get().strip(),
            "partition": self.partition.get().strip(),
            "ntasks": self.ntasks.get().strip(),
            "mem": self.mem.get().strip(),
            "cpus": self.cpus_per_task.get().strip(),
            "gpus": self.gpus.get().strip(),
            "nodelist": self.nodelist.get().strip(),
            "apptainer": DEFAULT_APPTAINER_MODULE,
            "image": DEFAULT_STEINBOCK_IMAGE,
            "save_folder": self.save_folder.get().strip(),
        }

    def _generated_filename(self) -> str:
        return datetime.now().strftime("jobID_%d%m%y.sh")

    def _target_path(self) -> Path:
        save_folder = Path(self.save_folder.get().strip()).expanduser()
        if not save_folder.is_absolute():
            save_folder = Path.cwd() / save_folder
        return save_folder / self._generated_filename()

    def _render_preview(self) -> str:
        settings = self._settings()
        target = self._target_path()
        gpu_line = settings["gpus"] if settings["partition"] == "gpu" else "not used"
        return f"""Selected HPC paths and generated script
=======================================

Selected HPC input folder:
  {settings["input"]}

Selected HPC output folder:
  {settings["output"]}

Selected save folder:
  {settings["save_folder"]}

Automatically generated bash filename:
  {self._generated_filename()}

Full generated script path:
  {target}

Final embedded resource settings:
  PARTITION={settings["partition"]}
  NTASKS={settings["ntasks"]}
  MEM={settings["mem"]}
  CPUS_PER_TASK={settings["cpus"]}
  GPUS={gpu_line}
  NODELIST={settings["nodelist"] or "none"}
  APPTAINER_MODULE={DEFAULT_APPTAINER_MODULE}
  STEINBOCK_IMAGE={DEFAULT_STEINBOCK_IMAGE}

Generated script behavior:
  The bash script embeds the stable v4 pipeline logic.
  It does not call {PIPELINE_SCRIPT} externally.
  At runtime it only requires {PREPARE_SCRIPT} in the same folder as the generated bash script.
"""

    def _render_script(self) -> str:
        settings = self._settings()
        source = self._read_v4_source()
        definitions, runtime = self._extract_v4_runtime_sections(source)
        original_v4_reference = "\n".join(f"# {line}" if line else "#" for line in source.splitlines())

        return f"""#!/bin/bash
set -euo pipefail

# Generated by imc_hpc_job_gui_generator.py
# This is a single self-contained IMC Steinbock HPC script.
# It does not call {PIPELINE_SCRIPT} externally.
# Runtime dependency: keep {PREPARE_SCRIPT} in the same folder as this script.

INPUT_DIR={sh_quote(settings["input"])}
PROJECT_DIR={sh_quote(settings["output"])}
PARTITION={sh_quote(settings["partition"])}
NTASKS={sh_quote(settings["ntasks"])}
MEM={sh_quote(settings["mem"])}
GPUS={sh_quote(settings["gpus"])}
CPUS_PER_TASK={sh_quote(settings["cpus"])}
NODELIST={sh_quote(settings["nodelist"])}
APPTAINER_MODULE={sh_quote(settings["apptainer"])}
STEINBOCK_IMAGE={sh_quote(settings["image"])}

# ---------------------------------------------------------------------------
# Embedded original stable v4 source for traceability.
# The executable block below adapts the same v4 logic to hardcoded settings.
# ---------------------------------------------------------------------------
{original_v4_reference}

# ---------------------------------------------------------------------------
# Executable embedded v4 pipeline logic starts here.
# ---------------------------------------------------------------------------
{definitions}

IMAGE="$STEINBOCK_IMAGE"
GRES=""
USE_SALLOC=1
ORIGINAL_ARGS=()

for arg in "$@"; do
    case "$arg" in
        --no-salloc)
            USE_SALLOC=0
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "ERROR: This generated script uses hardcoded settings and does not accept runtime arguments."
            echo "Unknown argument: $arg"
            exit 1
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
PREPARE_SCRIPT="$SCRIPT_DIR/{PREPARE_SCRIPT}"

if [ ! -f "$PREPARE_SCRIPT" ]; then
    echo "ERROR: Helper Python script not found: $PREPARE_SCRIPT"
    echo "Place {PREPARE_SCRIPT} in the same folder as this generated script."
    exit 1
fi

if [ -z "$INPUT_DIR" ] || [ -z "$PROJECT_DIR" ]; then
    echo "ERROR: INPUT_DIR and PROJECT_DIR are required."
    exit 1
fi

if [[ "$PARTITION" != "cpu" && "$PARTITION" != "gpu" && "$PARTITION" != "boost" ]]; then
    echo "ERROR: PARTITION must be one of: cpu, gpu, or boost."
    exit 1
fi

if ! [[ "$NTASKS" =~ ^[0-9]+$ ]] || [ "$NTASKS" -lt 1 ]; then
    echo "ERROR: NTASKS must be a positive integer."
    exit 1
fi

if ! [[ "$CPUS_PER_TASK" =~ ^[0-9]+$ ]] || [ "$CPUS_PER_TASK" -lt 1 ]; then
    echo "ERROR: CPUS_PER_TASK must be a positive integer."
    exit 1
fi

if ! [[ "$MEM" =~ ^[0-9]+[GgMm]?$ ]]; then
    echo "ERROR: MEM must look like 10G, 20G, 50000M, or 10000."
    exit 1
fi

if [ "$PARTITION" = "boost" ]; then
    echo "WARNING: boost may not be available for the current group/QoS."
    echo "Previous Slurm message: Job's QOS not permitted to use this partition (boost allows boost not renne)"
    if [ "$CPUS_PER_TASK" -gt 28 ]; then
        echo "ERROR: boost partition allows maximum 28 cpus-per-task per job."
        exit 1
    fi
fi

if [ -n "$GPUS" ]; then
    if ! [[ "$GPUS" =~ ^[0-9]+$ ]] || [ "$GPUS" -lt 1 ]; then
        echo "ERROR: GPUS must be a positive integer, for example 1."
        exit 1
    fi
    if [ "$GPUS" -gt 2 ] 2>/dev/null; then
        echo "ERROR: GPU nodes have 2 Tesla V100 GPUs per node. Use 1 or 2 GPUs."
        exit 1
    fi
    GRES="gpu:$GPUS"
fi

if [ "$PARTITION" = "gpu" ] && [ -z "$GRES" ]; then
    echo "ERROR: GPU partition requires GPUS=1 or another positive GPU count."
    exit 1
fi

if [ "$PARTITION" != "gpu" ] && [ -n "$GPUS" ]; then
    echo "ERROR: GPUS should only be set with PARTITION=gpu."
    exit 1
fi

echo "Launching self-contained IMC Steinbock HPC job"
echo "Input    : $INPUT_DIR"
echo "Output   : $PROJECT_DIR"
echo "Partition: $PARTITION"
echo "Memory   : $MEM"
echo "CPUs/task: $CPUS_PER_TASK"
echo "GPUs     : ${{GPUS:-none}}"
echo "Nodelist : ${{NODELIST:-none}}"
echo ""

{runtime}
"""

    def _validate(self) -> tuple[list[str], list[str]]:
        errors: list[str] = []
        warnings: list[str] = []
        settings = self._settings()

        if not settings["input"]:
            errors.append("Input folder is required.")
        if not settings["output"]:
            errors.append("Output project folder is required.")
        if settings["partition"] not in {"cpu", "gpu", "boost"}:
            errors.append("Partition must be cpu, gpu, or boost.")

        for label, value in (("Number of tasks", settings["ntasks"]), ("CPUs per task", settings["cpus"])):
            if not value.isdigit() or int(value) < 1:
                errors.append(f"{label} must be a positive integer.")

        if not settings["mem"]:
            errors.append("Memory is required, for example 10G.")
        else:
            mem_gb = memory_to_gb(settings["mem"])
            if mem_gb is not None and mem_gb > 256:
                warnings.append("Memory is greater than 256G. The group memory limit is 256G total across running jobs.")

        if settings["partition"] == "gpu":
            if not settings["gpus"].isdigit() or int(settings["gpus"]) < 1:
                errors.append("For GPU partition, number of GPUs must be a positive integer.")

        if settings["partition"] == "boost":
            warnings.append("Boost may not be available for the current group/QoS.")
            if settings["cpus"].isdigit() and int(settings["cpus"]) > 28:
                errors.append("Boost partition allows maximum 28 cpus-per-task per job.")

        if not settings["save_folder"]:
            errors.append("Save generated bash script in folder is required.")

        try:
            self._read_v4_source()
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

        return errors, warnings

    def _validate_and_report(self) -> None:
        errors, warnings = self._validate()
        if errors:
            messagebox.showerror("Validation failed", "\n".join(errors))
            return
        if warnings:
            messagebox.showwarning("Validation warnings", "\n".join(warnings))
            return
        messagebox.showinfo("Validation passed", "All fields look valid. You can generate the bash script now.")

    def _refresh_preview(self) -> None:
        if not hasattr(self, "preview"):
            return
        self.preview.delete("1.0", "end")
        try:
            if hasattr(self, "generated_name_label"):
                self.generated_name_label.configure(text=f"Generated filename: {self._generated_filename()}")
            self.preview.insert("1.0", self._render_preview())
        except Exception as exc:  # noqa: BLE001
            self.preview.insert("1.0", f"Preview unavailable:\n{exc}")

    def _generate_script(self) -> None:
        errors, warnings = self._validate()
        if errors:
            messagebox.showerror("Cannot generate script", "\n".join(errors))
            return

        if warnings:
            proceed = messagebox.askyesno(
                "Warnings",
                "\n".join(warnings) + "\n\nDo you still want to generate the script?",
            )
            if not proceed:
                return

        if self.partition.get().strip() == "boost":
            proceed = messagebox.askyesno(
                "Boost warning",
                "Boost may not be available for the current group/QoS.\n\n"
                "Previous Slurm message:\n"
                "Job's QOS not permitted to use this partition (boost allows boost not renne)\n\n"
                "Generate the boost script anyway?",
            )
            if not proceed:
                return

        target = self._target_path()

        try:
            target.write_text(self._render_script(), encoding="utf-8")
            current_mode = target.stat().st_mode
            target.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Failed to write script", str(exc))
            return

        messagebox.showinfo(
            "Script generated",
            f"Generated executable bash script:\n{target}\n\n"
            f"Keep {PREPARE_SCRIPT} in the same folder on the HPC.\n"
            f"Run it with:\n./{target.name}",
        )


def main() -> None:
    app = JobGenerator()
    app.mainloop()


if __name__ == "__main__":
    main()
