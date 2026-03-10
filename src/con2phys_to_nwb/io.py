"""Load con2phys data from extracted .npy and .csv files."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def load_mouse_data(mouse_dir: Path) -> dict[str, Any]:
    """Load all data for a single mouse from its extracted directory.

    Parameters
    ----------
    mouse_dir
        Path to the mouse directory containing .npy and .csv files.

    Returns
    -------
    dict
        Dictionary with keys: ``spikes``, ``clusters``, ``brain_area``,
        ``waveforms``, ``lfp_1``, ``lfp_2``, ``lfp_3``, ``trials``.
    """
    # Spike times: [num_spikes] float array
    spikes = np.load(mouse_dir / "spikes.npy")

    # Cluster IDs per spike: [num_spikes] int array
    clusters = np.load(mouse_dir / "clusters.npy")

    # Brain area info: dict with 'cluster_id' and 'brain_area' arrays
    brain_area = np.load(mouse_dir / "brain_area.npy", allow_pickle=True).item()

    # Mean waveforms: [num_units x 128] float array
    waveforms = np.load(mouse_dir / "waveforms.npy")

    # LFP: [num_channels x timestamps] float arrays
    lfp_1 = np.load(mouse_dir / "lfp_1.npy")
    lfp_2 = np.load(mouse_dir / "lfp_2.npy")
    lfp_3 = np.load(mouse_dir / "lfp_3.npy")

    # Trial data
    trial_file = mouse_dir / "trial_data.csv"
    if not trial_file.exists():
        # Fall back to xlsx if csv not present
        trial_file = mouse_dir / "trial_data.xlsx"
        trials = pd.read_excel(trial_file)
    else:
        trials = pd.read_csv(trial_file)

    # Drop unnamed index column if present
    trials = trials.drop(columns="Unnamed: 0", errors="ignore")

    return {
        "spikes": spikes,
        "clusters": clusters,
        "brain_area": brain_area,
        "waveforms": waveforms,
        "lfp_1": lfp_1,
        "lfp_2": lfp_2,
        "lfp_3": lfp_3,
        "trials": trials,
    }
