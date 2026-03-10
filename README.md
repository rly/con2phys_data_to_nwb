# con2phys Data to NWB

Convert the [con2phys dataset](https://ibl-brain-wide-map-public.s3.amazonaws.com/index.html#resources/con2phys/)
to [NWB (Neurodata Without Borders)](https://www.nwb.org/) format.

The converted NWB files are published as a draft dataset on the DANDI Sandbox
archive: <https://sandbox.dandiarchive.org/dandiset/218201>

## About the Dataset

The dataset consists of 18 mice with single-unit activity (SUA) and local field
potentials (LFP) recorded using Neuropixels probes during a behavioral task. Each
mouse has data from 3 simultaneously recorded, anonymized brain areas. Recording
lengths vary between 55 and 101 minutes.

- **Original data**: Downloaded from
  <https://ibl-brain-wide-map-public.s3.amazonaws.com/index.html#resources/con2phys/>
- **Reference code snippets**: Downloaded from
  <https://pre-cosyne-brainhack.github.io/hackathon2026/assets/downloads/code-snippets.zip>
- **More information**: <https://pre-cosyne-brainhack.github.io/hackathon2026/posts/con2phys/>

## Source Data Structure (per mouse)

| File | Format | Content |
|------|--------|---------|
| `spikes.npy` | NPY | `[num_spikes]` float spike times (seconds) |
| `clusters.npy` | NPY | `[num_spikes]` int cluster ID per spike |
| `brain_area.npy` | NPY | dict with `cluster_id` and `brain_area` arrays |
| `waveforms.npy` | NPY | `[num_units x 128]` float mean waveforms (30 kHz) |
| `lfp_1.npy` | NPY | `[num_channels x timestamps]` LFP for brain area 1 |
| `lfp_2.npy` | NPY | `[num_channels x timestamps]` LFP for brain area 2 |
| `lfp_3.npy` | NPY | `[num_channels x timestamps]` LFP for brain area 3 |
| `trial_data.csv` | CSV | Trial timing and behavioral variables |

- LFP sampling rate: 500 Hz
- Waveform sampling rate: 30 kHz (128 samples per unit)
- Channels are spaced vertically by 20 µm along each probe

## NWB File Contents

Each NWB file (one per mouse) contains:

- **Device**: A single Neuropixels device entry. The electrode groups for brain
  areas 1, 2, and 3 may come from 1 or more different Neuropixels probes.
- **Electrode groups**: One per brain area (3 total), each a selection of contacts
  from a Neuropixels probe in the corresponding anonymized brain area.
- **Electrodes table**: One row per LFP channel with brain area assignment,
  `rel_x` (0 for all), and `rel_z` (20 µm spacing along probe).
- **LFP**: Three `ElectricalSeries` (one per brain area) at 500 Hz, gzip
  compressed, in an `LFP` container under the `ecephys` processing module.
- **Units table**: Sorted units with spike times, brain area labels (1-3),
  cluster IDs, and mean waveforms (128 samples at 30 kHz).
- **Trials table**: Trial timing (`start_time`, `stop_time`, `stim_start`,
  `outcome`) and behavioral variables (`is_variable_A`, `is_variable_B`,
  `variable_C`).

## Why PyNWB instead of neuroconv?

neuroconv provides interfaces for standard formats (Phy, SpikeGLX, Open Ephys,
etc.). This dataset uses a custom `.npy`/`.csv` format that does not match any
existing interface. Using PyNWB directly is simpler than writing a custom
neuroconv `DataInterface` subclass.

## Setup

Requires Python >= 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

## Configuration

Edit `config.yaml` to set experiment metadata (description, experimenter,
institution, session start times, etc.). Placeholder values are provided and
should be updated before running the conversion.

## Usage

### 1. Download data from S3

Download and extract the Python-format zip files from S3 (public bucket, no
credentials needed):

```bash
# Download all 18 mice
uv run python -m con2phys_to_nwb.download --output-dir original_data/python

# Download a single mouse
uv run python -m con2phys_to_nwb.download --mouse-id 1
```

### 2. Convert to NWB

```bash
# Convert all mice
uv run python -m con2phys_to_nwb.convert \
    --data-dir original_data/python \
    --output-dir output \
    --config config.yaml

# Convert a single mouse
uv run python -m con2phys_to_nwb.convert --mouse-id 1
```

This creates one `.nwb` file per mouse in the `output/` directory.

### 3. Validate

```bash
uv run nwbinspector output/
```

## Validation Results

nwbinspector 0.7.0 reports across all 18 files:
- **0 errors**
- **1 best practice violation**: Mouse 2 has negative spike times (pre-trial
  activity before t=0)
- **18 best practice suggestions**: `session_start_time` is set to
  `1970-01-01T00:00:00+00:00` because the true recording dates are unknown

## Project Structure

```
├── README.md              # This file
├── config.yaml            # User-editable experiment metadata
├── pyproject.toml         # Project dependencies (managed by uv)
├── src/
│   └── con2phys_to_nwb/
│       ├── __init__.py
│       ├── convert.py     # Main conversion logic and CLI
│       ├── download.py    # Download and extract data from S3
│       └── io.py          # Data loading utilities
├── original_data/         # Source data (not in repo)
├── code-snippets/         # Reference notebooks (not in repo)
└── output/                # Generated NWB files (not in repo)
```

## How This Was Generated

The conversion scripts were developed with the assistance of Claude Opus 4.6
(Anthropic) via Claude Code on 2026-03-08.
