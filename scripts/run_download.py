"""
Idempotent DARPA dataset download & extraction runner.

Usage:
    python run_download.py                  # run all steps
    python run_download.py --only e3        # run only E3 steps
    python run_download.py --only e5        # run only E5 steps
    python run_download.py --only optc      # run only OpTC steps
    python run_download.py --workers 8      # E5 conversion parallelism
"""
import argparse
import sys

from provenance_explorer.download.gdrive import gdrive_auth
from provenance_explorer.download.darpa_downloads import (
    # E3
    download_e3_tar_gz_from_gdrive,
    extract_all_e3_tar_gz_to_jsonl,
    check_e3_json_present,
    # E5
    download_e5_bin_gz_from_gdrive,
    convert_all_e5_bin_gz_to_jsonl,
    # OpTC
    download_optc_json_gz_from_gdrive,
    extract_all_optc_json_gz,
)


def run_e3(creds):
    print("=" * 60)
    print("E3: Downloading tar.gz archives...")
    print("=" * 60)
    download_e3_tar_gz_from_gdrive(creds)

    print("=" * 60)
    print("E3: Extracting tar.gz to json...")
    print("=" * 60)
    extract_all_e3_tar_gz_to_jsonl(creds)

    missing = check_e3_json_present()
    if missing:
        print(f"E3 WARNING: {len(missing)} json files still missing after extraction.")
    else:
        print("E3: all json files present.")


def run_e5(creds, max_workers: int):
    print("=" * 60)
    print("E5: Downloading bin.gz files...")
    print("=" * 60)
    download_e5_bin_gz_from_gdrive(creds)

    print("=" * 60)
    print(f"E5: Converting bin.gz to jsonl ({max_workers} workers)...")
    print("=" * 60)
    convert_all_e5_bin_gz_to_jsonl(creds, max_workers=max_workers)


def run_optc(creds):
    print("=" * 60)
    print("OpTC: Downloading json.gz files...")
    print("=" * 60)
    download_optc_json_gz_from_gdrive(creds)

    print("=" * 60)
    print("OpTC: Extracting json.gz to json...")
    print("=" * 60)
    extract_all_optc_json_gz(creds)


def main():
    parser = argparse.ArgumentParser(description="Download and extract DARPA datasets.")
    parser.add_argument(
        "--only",
        choices=["e3", "e5", "optc"],
        default=None,
        help="Run only the specified dataset; defaiult means run all.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of workers for E5 conversion (default: 4).",
    )
    args = parser.parse_args()

    print("Authenticating with Google Drive...")
    creds = gdrive_auth()

    steps = {
        "e3": lambda: run_e3(creds),
        "e5": lambda: run_e5(creds, args.workers),
        "optc": lambda: run_optc(creds),
    }

    targets = [args.only] if args.only else ["e3", "e5", "optc"]
    for target in targets:
        try:
            steps[target]()
        except Exception as exc:
            print(f"\nFATAL: {target.upper()} step failed: {exc}", file=sys.stderr)
            print("Re-run this script to resume from where it left off.\n", file=sys.stderr)
            sys.exit(1)

    print("\n" + "=" * 60)
    print("done.")
    print("=" * 60)


if __name__ == "__main__":
    main()