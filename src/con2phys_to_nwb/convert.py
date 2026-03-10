"""Convert con2phys data to NWB format."""

import argparse
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from pynwb import NWBHDF5IO, NWBFile
from hdmf.backends.hdf5 import H5DataIO
from pynwb.ecephys import ElectricalSeries, LFP
from pynwb.file import Subject

from con2phys_to_nwb.io import load_mouse_data

LFP_RATE = 500.0  # Hz
WAVEFORM_RATE = 30_000.0  # Hz
N_MICE = 18


def load_config(config_path: Path) -> dict[str, Any]:
    """Load the YAML configuration file.

    Parameters
    ----------
    config_path
        Path to the config YAML file.

    Returns
    -------
    dict
        Parsed configuration.
    """
    with open(config_path) as f:
        return yaml.safe_load(f)


def create_nwb_file(mouse_id: int, data: dict[str, Any], config: dict[str, Any]) -> NWBFile:
    """Build an NWBFile from loaded mouse data and config.

    Parameters
    ----------
    mouse_id
        Mouse identifier (1-18).
    data
        Dictionary returned by ``load_mouse_data``.
    config
        Parsed YAML configuration.

    Returns
    -------
    NWBFile
        Populated NWB file object ready to be written.
    """
    # Resolve per-session overrides
    session_config = config.get("sessions", {}).get(mouse_id, {})
    session_description = session_config.get(
        "session_description",
        f"con2phys mouse {mouse_id}",
    )
    session_start_time = datetime.fromisoformat(
        session_config.get("session_start_time", config["session_start_time"])
    )

    nwbfile = NWBFile(
        session_description=session_description,
        identifier=f"con2phys_mouse_{mouse_id}",
        session_start_time=session_start_time,
        experiment_description=config.get("experiment_description", ""),
        experimenter=config.get("experimenter"),
        institution=config.get("institution", ""),
        lab=config.get("lab", ""),
        keywords=config.get("keywords", []),
    )

    # -- Subject --
    subject_config = session_config.get("subject", config.get("subject", {}))
    nwbfile.subject = Subject(
        subject_id=subject_config.get("subject_id", f"mouse_{mouse_id}"),
        species=subject_config.get("species", "Mus musculus"),
        sex=subject_config.get("sex", "U"),
        age=subject_config.get("age"),
        description=subject_config.get("description", f"Mouse {mouse_id}"),
    )

    # -- Device and electrode groups --
    device = nwbfile.create_device(
        name="Neuropixels",
        description=(
            "Neuropixels probe(s). The electrode groups for brain areas 1, 2, and 3 "
            "may come from 1 or more different Neuropixels probes."
        ),
    )

    electrode_groups: dict[int, Any] = {}
    for area_id in (1, 2, 3):
        eg = nwbfile.create_electrode_group(
            name=f"area_{area_id}",
            description=(
                f"Selection of contacts from a Neuropixels probe in anonymized brain area {area_id}"
            ),
            location=f"brain_area_{area_id}",
            device=device,
        )
        electrode_groups[area_id] = eg

    # -- Electrodes table (one row per LFP channel) --
    # Channels are spaced vertically by 20 µm along the probe
    nwbfile.add_electrode_column(name="brain_area", description="Anonymized brain area (1-3)")
    nwbfile.add_electrode_column(name="rel_x", description="Relative x position along probe (µm)")
    nwbfile.add_electrode_column(name="rel_z", description="Relative depth along probe (µm)")

    electrode_indices: dict[int, list[int]] = {1: [], 2: [], 3: []}
    global_electrode_idx = 0
    for area_id in (1, 2, 3):
        lfp_data = data[f"lfp_{area_id}"]
        n_channels = lfp_data.shape[0]
        for ch in range(n_channels):
            nwbfile.add_electrode(
                group=electrode_groups[area_id],
                brain_area=area_id,
                location=f"brain_area_{area_id}",
                rel_x=0.0,
                rel_z=float(ch * 20),
            )
            electrode_indices[area_id].append(global_electrode_idx)
            global_electrode_idx += 1

    # -- LFP --
    ecephys_module = nwbfile.create_processing_module(
        name="ecephys",
        description="Extracellular electrophysiology processing",
    )
    lfp_container = LFP(name="LFP")
    ecephys_module.add(lfp_container)

    for area_id in (1, 2, 3):
        lfp_data = data[f"lfp_{area_id}"]
        electrode_table_region = nwbfile.create_electrode_table_region(
            region=electrode_indices[area_id],
            description=f"LFP channels for brain area {area_id}",
        )
        lfp_container.create_electrical_series(
            name=f"lfp_area_{area_id}",
            data=H5DataIO(lfp_data.T, compression="gzip"),  # NWB expects [timestamps x channels]
            electrodes=electrode_table_region,
            rate=LFP_RATE,
            description=f"LFP from anonymized brain area {area_id}",
        )

    # -- Units table --
    nwbfile.add_unit_column(name="brain_area", description="Anonymized brain area (1-3)")
    nwbfile.add_unit_column(name="cluster_id", description="Original cluster ID")
    nwbfile.add_unit_column(
        name="waveform_mean",
        description="Mean waveform (128 samples at 30 kHz)",
    )

    brain_area_info = data["brain_area"]
    cluster_ids_all = brain_area_info["cluster_id"]
    brain_areas_all = brain_area_info["brain_area"]
    brain_area_map = dict(zip(cluster_ids_all, brain_areas_all))

    # Get unique cluster IDs in order
    unique_clusters = cluster_ids_all
    waveforms = data["waveforms"]

    # Build spike times per cluster
    spikes = data["spikes"]
    clusters = data["clusters"]
    spikes_by_cluster: dict[int, list[float]] = {}
    for cid, spike_time in zip(clusters, spikes):
        spikes_by_cluster.setdefault(int(cid), []).append(float(spike_time))

    for i, cid in enumerate(unique_clusters):
        cid_int = int(cid)
        spike_times = np.array(spikes_by_cluster.get(cid_int, []))
        nwbfile.add_unit(
            spike_times=spike_times,
            brain_area=int(brain_area_map[cid]),
            cluster_id=cid_int,
            waveform_mean=waveforms[i],
        )

    # -- Trials table --
    trials = data["trials"]
    nwbfile.add_trial_column(name="stim_start", description="Stimulus presentation time (s)")
    nwbfile.add_trial_column(name="outcome", description="Reward or punishment time (s)")
    nwbfile.add_trial_column(name="is_variable_A", description="Binary categorical behavioral variable A")
    nwbfile.add_trial_column(name="is_variable_B", description="Binary categorical behavioral variable B")
    nwbfile.add_trial_column(name="variable_C", description="Categorical behavioral variable C (1-3)")

    for _, row in trials.iterrows():
        nwbfile.add_trial(
            start_time=float(row["trial_start"]),
            stop_time=float(row["trial_end"]),
            stim_start=float(row["stim_start"]),
            outcome=float(row["outcome"]),
            is_variable_A=bool(row["variable_A"]),
            is_variable_B=bool(row["variable_B"]),
            variable_C=int(row["variable_C"]),
        )

    return nwbfile


def convert_mouse(
    mouse_id: int,
    data_dir: Path,
    output_dir: Path,
    config: dict[str, Any],
) -> Path:
    """Convert a single mouse to NWB.

    Parameters
    ----------
    mouse_id
        Mouse identifier (1-18).
    data_dir
        Root directory containing per-mouse subdirectories.
    output_dir
        Directory where the NWB file will be written.
    config
        Parsed YAML configuration.

    Returns
    -------
    Path
        Path to the written NWB file.
    """
    mouse_dir = data_dir / str(mouse_id)
    print(f"Mouse {mouse_id}: loading data from {mouse_dir} ...")
    data = load_mouse_data(mouse_dir)

    print(f"Mouse {mouse_id}: building NWB file ...")
    nwbfile = create_nwb_file(mouse_id, data, config)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"mouse_{mouse_id}.nwb"
    print(f"Mouse {mouse_id}: writing {output_path} ...")
    with NWBHDF5IO(str(output_path), "w") as io:
        io.write(nwbfile)

    print(f"Mouse {mouse_id}: done.")
    return output_path


def convert_all(
    data_dir: Path,
    output_dir: Path,
    config_path: Path,
) -> list[Path]:
    """Convert all 18 mice to NWB.

    Parameters
    ----------
    data_dir
        Root directory containing per-mouse subdirectories.
    output_dir
        Directory where NWB files will be written.
    config_path
        Path to the YAML configuration file.

    Returns
    -------
    list[Path]
        Paths to all written NWB files.
    """
    config = load_config(config_path)
    output_paths = []
    for mouse_id in range(1, N_MICE + 1):
        path = convert_mouse(mouse_id, data_dir, output_dir, config)
        output_paths.append(path)
    print(f"Conversion complete. {len(output_paths)} NWB files written to {output_dir}")
    return output_paths


def main() -> None:
    """CLI entry point for converting data to NWB."""
    parser = argparse.ArgumentParser(
        description="Convert con2phys data to NWB format.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("original_data/python"),
        help="Directory containing per-mouse subdirectories (default: original_data/python)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Directory for output NWB files (default: output)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="Path to YAML config file (default: config.yaml)",
    )
    parser.add_argument(
        "--mouse-id",
        type=int,
        default=None,
        help="Convert only this mouse ID (1-18). If not set, convert all.",
    )
    args = parser.parse_args()

    if args.mouse_id is not None:
        config = load_config(args.config)
        convert_mouse(args.mouse_id, args.data_dir, args.output_dir, config)
    else:
        convert_all(args.data_dir, args.output_dir, args.config)


if __name__ == "__main__":
    main()
