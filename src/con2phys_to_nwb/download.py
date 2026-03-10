"""Download and extract con2phys Python-format data from S3."""

import argparse
import io
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import boto3
from botocore import UNSIGNED
from botocore.config import Config
from tqdm import tqdm

BUCKET = "ibl-brain-wide-map-public"
PREFIX = "resources/con2phys/dataset_py/"
N_MICE = 18


def download_and_extract(
    mouse_id: int,
    output_dir: Path,
    *,
    skip_existing: bool = True,
    progress_bar: tqdm | None = None,
) -> Path:
    """Download a single mouse zip from S3 and extract it.

    Parameters
    ----------
    mouse_id
        Mouse identifier (1-18).
    output_dir
        Root directory where data will be extracted. Files are placed in
        ``output_dir/{mouse_id}/``.
    skip_existing
        If True, skip download when the target directory already exists and
        contains files.
    progress_bar
        Optional tqdm bar to update on completion.

    Returns
    -------
    Path
        Path to the extracted mouse directory.
    """
    mouse_dir = output_dir / str(mouse_id)
    if skip_existing and mouse_dir.exists() and any(mouse_dir.iterdir()):
        if progress_bar is not None:
            progress_bar.update(1)
        return mouse_dir

    s3_key = f"{PREFIX}{mouse_id}.zip"

    s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))

    # Get file size for per-file progress
    head = s3.head_object(Bucket=BUCKET, Key=s3_key)
    total_bytes = head["ContentLength"]

    # Stream download with progress
    response = s3.get_object(Bucket=BUCKET, Key=s3_key)
    body = response["Body"]
    chunks = []
    downloaded = 0
    per_file_bar = tqdm(
        total=total_bytes,
        unit="B",
        unit_scale=True,
        desc=f"Mouse {mouse_id:>2}",
        leave=False,
    )
    while True:
        chunk = body.read(8 * 1024 * 1024)  # 8 MB chunks
        if not chunk:
            break
        chunks.append(chunk)
        downloaded += len(chunk)
        per_file_bar.update(len(chunk))
    per_file_bar.close()
    zip_bytes = b"".join(chunks)

    mouse_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        # Zip files contain a nested subdirectory (e.g., "1/spikes.npy").
        # Strip the top-level directory so files land directly in mouse_dir.
        for member in zf.infolist():
            if member.is_dir():
                continue
            parts = Path(member.filename).parts
            if len(parts) > 1:
                member.filename = str(Path(*parts[1:]))
            zf.extract(member, mouse_dir)

    if progress_bar is not None:
        progress_bar.update(1)
    return mouse_dir


def download_all(
    output_dir: Path,
    *,
    skip_existing: bool = True,
    max_workers: int = 4,
) -> None:
    """Download and extract all 18 mouse datasets in parallel.

    Parameters
    ----------
    output_dir
        Root directory for extracted data.
    skip_existing
        If True, skip mice whose directories already exist.
    max_workers
        Maximum number of parallel downloads.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    overall = tqdm(total=N_MICE, desc="Overall", unit="mouse")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                download_and_extract,
                mouse_id,
                output_dir,
                skip_existing=skip_existing,
                progress_bar=overall,
            ): mouse_id
            for mouse_id in range(1, N_MICE + 1)
        }
        for future in as_completed(futures):
            mouse_id = futures[future]
            try:
                future.result()
            except Exception as exc:
                tqdm.write(f"Mouse {mouse_id}: FAILED - {exc}")
    overall.close()
    print("All downloads complete.")


def main() -> None:
    """CLI entry point for downloading data."""
    parser = argparse.ArgumentParser(
        description="Download con2phys Python-format data from S3.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("original_data/python"),
        help="Directory to extract data into (default: original_data/python)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if data already exists",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Maximum number of parallel downloads (default: 4)",
    )
    parser.add_argument(
        "--mouse-id",
        type=int,
        default=None,
        help="Download only this mouse ID (1-18). If not set, download all.",
    )
    args = parser.parse_args()
    if args.mouse_id is not None:
        download_and_extract(args.mouse_id, args.output_dir, skip_existing=not args.force)
    else:
        download_all(
            args.output_dir,
            skip_existing=not args.force,
            max_workers=args.max_workers,
        )


if __name__ == "__main__":
    main()
