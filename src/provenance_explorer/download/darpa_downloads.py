"""
Most functions require a set up gdrive access token in the home directory; see setup.md
"""
from typing import List, Any
import re
import os
import json
import glob
from pathlib import Path
import gzip
import tarfile
import shutil
import subprocess
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from google.oauth2.credentials import Credentials

import provenance_explorer.registry.darpa_registry as darpa_registry
from provenance_explorer.download.gdrive import list_items_recursive, download_file_to_path
from provenance_explorer.registry.repo_paths import DATA_RAW


# ============================================
# tooling for E5 for avro-to-json conversion
# ============================================

_BBN_CONSUMER_JAR = DATA_RAW / ".tools" / "bbn-consumer.jar"
_BBN_SCHEMA = DATA_RAW / ".tools" / "TCCDMDatum.avsc"

def _check_bbn_consumer_present() -> None:
    """verify the BBN consumer jar and avro schema are in place."""
    missing = []
    if not _BBN_CONSUMER_JAR.exists():
        missing.append(str(_BBN_CONSUMER_JAR))
    if not _BBN_SCHEMA.exists():
        missing.append(str(_BBN_SCHEMA))
    if missing:
        raise FileNotFoundError(
            "BBN FileConsumer artefacts not found:\n"
            + "\n".join(f"  - {m}" for m in missing)
            + "See instructions in setup.md"
        )

def _bbn_convert_bin_to_jsonl(bin_path: Path, out_path: Path) -> None:
    """
    Convert a single (uncompressed) E5 AVRO .bin file to .jsonl using the BBN FileConsumer.
    FileConsumer flags matching tjhe ones in ta3-java-cosumer/tc-bbn-kafka/json_consumer.sh):
    """
    tmp_work = tempfile.mkdtemp(prefix="e5_bbn_")
    schema = str(_BBN_SCHEMA.resolve())
    jar = str(_BBN_CONSUMER_JAR.resolve())
    abs_bin = str(bin_path.resolve())

    try:
        cmd = [
            "java",
            "-cp", f".:{jar}",
            "com.bbn.tc.services.kafka.FileConsumer",
            f"file:///{abs_bin}",
            "-np",
            "-psf", schema,
            "-csf", schema,
            "-rg",
            "-call",
            "-co", "earliest",
            "-cdm",
            "-c",
            "-roll", "5000000",     # roll output every 5M records, as done in original json_consumer.sh
            "-wj",
            "-d",  "10000000",      # 10 000 s timeout to keep consumer alive until EOF
        ]

        result = subprocess.run(
            cmd,
            cwd=tmp_work,
            capture_output=True,
            text=True,
            timeout=14400,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"BBN FileConsumer failed (rc={result.returncode}) for {bin_path}:\n"
                f"stderr: {result.stderr[:2000]}"
            )

        # Collect all .json* output files the consumer wrote.
        out_files = glob.glob(os.path.join(tmp_work, "*.json*"))
        # Exclude non-json artefacts (e.g. .json_metadata) and sort by roll index
        out_files = [f for f in out_files if re.search(r"\.json(\.\d+)?$", f)]
        out_files.sort(key=lambda f: (
            int(m.group(1)) if (m := re.search(r"\.json\.(\d+)$", f)) else -1
        ))
        if not out_files:
            raise RuntimeError(
                f"BBN FileConsumer produced no output files for {bin_path}.\n"
                f"stdout: {result.stdout[:2000]}\n"
                f"stderr: {result.stderr[:2000]}"
            )

        # Concatenate into a single .jsonl, writing via .part
        tmp_out = Path(str(out_path) + ".part")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        written = 0
        with open(tmp_out, "w", encoding="utf-8") as fout:
            for json_file in out_files:
                with open(json_file, "r", encoding="utf-8") as fin:
                    for line in fin:
                        line = line.rstrip("\n")
                        if not line:
                            continue
                        fout.write(line + "\n")
                        written += 1

        tmp_out.replace(out_path)
        print(f"E5 converted ({written} records): {out_path}")

    finally:
        shutil.rmtree(tmp_work, ignore_errors=True)

# ==============================================================================
# E3 — tar.gz from GDrive, extract to jsonl
# ==============================================================================

def generate_darpa_e3_files_list(creds: Credentials) -> List[List[str]]:
    """
    Returns list of TC E3 files used in this repository, fetched from official
    Fivedirections' GDrive.  As list of [path, gid].
    """
    files = list_items_recursive(creds, "1fOCY3ERsEmXmvDekG-LUUSjfWs6TRdp-")
    return [[f[0], f[2]] for f in files if not re.search(r".bin", f[0])]

def check_e3_tar_gz_present(creds: Credentials) -> List:
    """
    Check whether un-extracted E3 files are found where expected.
    Return missing files list as [expected_path, gid].
    """
    missing_files = []
    expected_files = generate_darpa_e3_files_list(creds)
    for file in expected_files:
        expected_path = DATA_RAW / "Engagement3" / file[0]
        if not os.path.exists(expected_path):
            missing_files.append([expected_path, file[1]])
    return missing_files

def check_e3_json_present() -> List:
    """
    Check whether extracted E3 files are found where expected.
    Return missing files.
    """
    missing_files = []
    registries = [
        getattr(darpa_registry, "e3_cadets_file_info"),
        getattr(darpa_registry, "e3_clearscope_file_info"),
        getattr(darpa_registry, "e3_fivedirections_file_info"),
        getattr(darpa_registry, "e3_theia_file_info"),
        getattr(darpa_registry, "e3_trace_file_info"),
    ]
    for registry in registries:
        for file in registry:
            if not os.path.exists(DATA_RAW / file["path"]):
                missing_files.append(file["path"])
    return missing_files

def download_e3_tar_gz_from_gdrive(creds: Credentials):
    missing_files = check_e3_tar_gz_present(creds)
    for file in missing_files:
        # try:
        download_file_to_path(creds, file[1], file[0])
        # except:
        #     raise

def extract_all_e3_tar_gz_to_jsonl(creds: Credentials):
    """
    Extract E3 tar.gz archives. 
    skips archives whose expected outputs exist; as per regsitry
    """
    missing_json = set(check_e3_json_present())
    if not missing_json:
        print("E3: all extracted json files already present, nothing to do.")
        return

    tar_gz_files_list = generate_darpa_e3_files_list(creds)
    for file in tar_gz_files_list:
        path = DATA_RAW / "Engagement3" / file[0]
        parent_str = str(path.parent)
        relevant_missing = [m for m in missing_json if parent_str in str(DATA_RAW / m)]
        if not relevant_missing:
            print(f"E3 skip (already extracted): {path}")
            continue
        if not path.exists():
            print(f"E3 skip (archive not downloaded): {path}")
            continue
        print(f"E3 extracting: {path}")
        with tarfile.open(path, "r:gz") as tar:
            tar.extractall(str(path.parent))

# ==============================================================================
# E5 — avro bin.gz from GDrive, convert to jsonl via BBN FileConsumer
# ==============================================================================

def generate_darpa_e5_files_list(creds: Credentials) -> List[List[str]]:
    """
    Returns list of TC E5 files used in this repository, fetched from official
    Fivedirections' GDrive.  As list of [path, file_id].
    """
    files = list_items_recursive(creds, "1GVlHQwjJte3yz0n1a1y4H4TfSe8cu6WJ")
    files = [[f[0], f[2]] for f in files if re.search(r"bin.*\.gz$", f[0])]
    return files

def check_e5_bin_gz_present(creds: Credentials) -> List:
    """
    Check whether un-extracted E5 files are found where expected.
    Return missing files list as [expected_path, gid].
    """
    missing_files = []
    expected_files = generate_darpa_e5_files_list(creds)
    for file in expected_files:
        expected_path = DATA_RAW / "Engagement5" / file[0]
        if not os.path.exists(expected_path):
            missing_files.append([expected_path, file[1]])
        else:
            print(f"found: {expected_path}")
    return missing_files

def download_e5_bin_gz_from_gdrive(creds: Credentials):
    missing_files = check_e5_bin_gz_present(creds)
    for file in missing_files:
        try:
            download_file_to_path(creds, file[1], file[0])
        except:
            raise

def convert_single_e5_bin_gz_to_jsonl(bin_gz_path: Path, out_path: Path):
    """
    Convert a single E5 avro .bin[.N].gz to .jsonl using the BBN FileConsumer.
    skips if out_path already exists.

    Steps:
      1. Check BBN consumer artefacts are present
      2. gunzip to a temp file, so the consumer can read uncompressed AVRO containers
      3. Run BBN FileConsumer; produces .json files
      4. Concatenate output into a single .jsonl at out_path
      5. Clean up temp files
    """
    if out_path.exists():
        print(f"E5 skip (already converted): {out_path}")
        return

    _check_bbn_consumer_present()

    # gunzip to a temporary .bin file
    tmp_dir = tempfile.mkdtemp(prefix="e5_gunzip_")
    tmp_bin = Path(tmp_dir) / bin_gz_path.stem
    try:
        with gzip.open(bin_gz_path, "rb") as fin, open(tmp_bin, "wb") as fout:
            shutil.copyfileobj(fin, fout)

        _bbn_convert_bin_to_jsonl(tmp_bin, out_path)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _e5_convert_worker(args: tuple) -> str:
    """worker for ProcessPoolExecutor"""
    bin_gz_path, out_path = Path(args[0]), Path(args[1])
    convert_single_e5_bin_gz_to_jsonl(bin_gz_path, out_path)
    return str(out_path)

def convert_all_e5_bin_gz_to_jsonl(creds: Credentials, max_workers: int = 4):
    """
    Convert all E5 bin.gz files to jsonl using multiple processes.
    skips files whose .jsonl output already exists.
    """
    # Fail fast if the BBN consumer is not installed
    _check_bbn_consumer_present()

    bin_gz_files_list = generate_darpa_e5_files_list(creds)
    jobs = []
    for file in bin_gz_files_list:
        bin_path = DATA_RAW / "Engagement5" / file[0]
        out_name = re.sub(r"\.bin(\.\d+)?\.gz$", r".jsonl\1", file[0])
        out_path = DATA_RAW / "Engagement5" / out_name
        if out_path.exists():
            print(f"E5 found: {out_path}")
            continue
        if not bin_path.exists():
            print(f"E5 skip (bin.gz not downloaded): {bin_path}")
            continue
        jobs.append((str(bin_path), str(out_path)))

    if not jobs:
        print("E5: all jsonl files already present, nothing to convert.")
        return

    print(f"E5: converting {len(jobs)} files with {max_workers} workers...")
    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_e5_convert_worker, job): job for job in jobs}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                print(f"E5 conversion failed for {futures[future]}: {exc}")


# ==============================================================================
# OpTC — json.gz from GDrive, extract to json
# ==============================================================================
def generate_optc_files_list(creds: Credentials) -> List[List[str]]:
    """
    For OpTC only subsets containing major parts of the attacks and are  the Host-Level 
    ecar files are considered for now.
    """
    big_list = list_items_recursive(creds, "1NwaCWRyr_coyPbF2SvScbani5O9MXp7_")

    pat_ecar_head_51to75 = r".*/AIA-51-75/.*"
    pat_ecar_head_951to975 = r".*/AIA-951-975/.*"
    pat_ecar_head_501 = r".*/AIA-501-525/.*"
    pat_ecar_head_201 = r".*/AIA-201-225/.*"

    out = []
    for item in big_list:
        if not (
            re.search(pat_ecar_head_51to75, item[0])
            or re.search(pat_ecar_head_951to975, item[0])
            or re.search(pat_ecar_head_501, item[0])
            or re.search(pat_ecar_head_201, item[0])
        ):
            continue
        out.append([item[0], item[2]])
    return out 


def check_optc_json_gz_present(creds: Credentials) -> List:
    """
    Check whether un-extracted OpTC json.gz files are found where expected.
    Return missing files list as [expected_path, gid].
    """
    missing_files = []
    expected_files = generate_optc_files_list(creds)
    for file in expected_files:
        expected_path = DATA_RAW / "OpTC" / file[0]
        if not os.path.exists(expected_path):
            missing_files.append([expected_path, file[1]])
        else:
            # print(f"OpTC found: {expected_path}")
            continue
    return missing_files


def download_optc_json_gz_from_gdrive(creds: Credentials):
    """Download missing OpTC json.gz files."""
    missing_files = check_optc_json_gz_present(creds)
    if not missing_files:
        print("OpTC: all json.gz files already downloaded.")
        return
    print(f"OpTC: downloading {len(missing_files)} files...")
    for file in missing_files:
        try:
            download_file_to_path(creds, file[1], file[0])
        except:
            raise

def extract_single_optc_json_gz(gz_path: Path, out_path: Path):
    """
    Extract a single OpTC json.gz to json.
    """
    if out_path.exists():
        return

    tmp_out_path = Path(str(out_path) + ".part")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with gzip.open(gz_path, "rb") as fin, open(tmp_out_path, "wb") as fout:
        while True:
            chunk = fin.read(1024 * 1024)
            if not chunk:
                break
            fout.write(chunk)

    tmp_out_path.replace(out_path)
    print(f"OpTC extracted: {out_path}")

def extract_all_optc_json_gz(creds: Credentials):
    """
    Extract all OpTC json.gz files to json.
    """
    file_list = generate_optc_files_list(creds)
    extracted, skipped = 0, 0

    for file in file_list:
        gz_path = DATA_RAW / "OpTC" / file[0]
        out_path = gz_path.with_suffix("")

        if out_path.exists():
            skipped += 1
            continue
        if not gz_path.exists():
            print(f"OpTC skip (not downloaded): {gz_path}")
            continue

        extract_single_optc_json_gz(gz_path, out_path)
        extracted += 1

    print(f"OpTC extraction done: {extracted} extracted, {skipped} already present.")