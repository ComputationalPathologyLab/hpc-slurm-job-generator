#!/usr/bin/env python3

from pathlib import Path
import argparse
import re
import numpy as np
import pandas as pd
import tifffile


def mass_number(filename):
    m = re.match(r"(\d+)", filename)
    return int(m.group(1)) if m else 9999


def is_roi_folder(path):
    return path.is_dir() and any(path.glob("*.ome.tiff"))


def detect_roi_dirs(input_dir):
    if is_roi_folder(input_dir):
        return [input_dir]

    roi_dirs = sorted([p for p in input_dir.iterdir() if is_roi_folder(p)])

    if not roi_dirs:
        raise ValueError(
            f"No ROI folders found in {input_dir}. "
            "Expected either one ROI folder containing *.ome.tiff files, "
            "or a parent folder containing multiple ROI folders."
        )

    return roi_dirs


def parse_channel_marker(path):
    name = path.name.replace(".ome.tiff", "")
    if "_" not in name:
        raise ValueError(f"Invalid channel filename: {path.name}")
    return name.split("_", 1)


def deepcell_group(marker):
    marker_upper = marker.upper()

    nuclear = {"DNA1", "DNA2", "HISTONEH3", "HISTONE", "H3"}

    membrane = {
        "CD45", "CD3", "CD4", "CD8", "CD8A", "CD31",
        "ECAD", "E-CADHERIN", "CDH1", "ASMA", "SMA",
        "PANCK", "KERATIN", "VIMENTIN"
    }

    if marker_upper in nuclear:
        return 1
    if marker_upper in membrane:
        return 2
    return ""


def main():
    parser = argparse.ArgumentParser(
        description="Prepare single-channel IMC OME-TIFF folders for Steinbock."
    )

    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--force", action="store_true")

    args = parser.parse_args()

    input_dir = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()
    img_dir = output_dir / "img"

    if not input_dir.exists():
        raise FileNotFoundError(f"Input path does not exist: {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    img_dir.mkdir(parents=True, exist_ok=True)

    roi_dirs = detect_roi_dirs(input_dir)

    all_channels = {}
    images_rows = []

    for roi_dir in roi_dirs:
        files = sorted(roi_dir.glob("*.ome.tiff"), key=lambda p: mass_number(p.name))

        stack = []
        for f in files:
            channel, marker = parse_channel_marker(f)
            all_channels[channel] = marker

            img = np.squeeze(tifffile.imread(f))

            if img.ndim != 2:
                raise ValueError(f"Expected 2D image but got {img.shape} for {f}")

            stack.append(img)

        if not stack:
            continue

        stacked = np.stack(stack, axis=0)
        out_tiff = img_dir / f"{roi_dir.name}.tiff"

        if out_tiff.exists() and not args.force:
            print(f"Skipping existing image: {out_tiff.name}")
        else:
            tifffile.imwrite(out_tiff, stacked)
            print(f"Created {out_tiff.name} with shape {stacked.shape}")

        images_rows.append({
            "image": out_tiff.name,
            "sample": roi_dir.name
        })

    panel_rows = []

    for channel, marker in sorted(all_channels.items(), key=lambda x: mass_number(x[0])):
        panel_rows.append({
            "channel": channel,
            "name": marker,
            "keep": 1,
            "ilastik": 0,
            "deepcell": deepcell_group(marker),
            "cellpose": ""
        })

    pd.DataFrame(panel_rows).to_csv(output_dir / "panel.csv", index=False)
    pd.DataFrame(images_rows).to_csv(output_dir / "images.csv", index=False)

    print(f"Panel written: {output_dir / 'panel.csv'}")
    print(f"Images metadata written: {output_dir / 'images.csv'}")
    print(f"ROIs detected: {len(images_rows)}")
    print(f"Channels detected: {len(panel_rows)}")


if __name__ == "__main__":
    main()