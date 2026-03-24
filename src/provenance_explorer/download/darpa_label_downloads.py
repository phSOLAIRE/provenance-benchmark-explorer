import io
import tarfile
import zipfile
import requests
from pathlib import Path

from provenance_explorer.registry.registry_all import DARPA_LABEL_PATH

def _download_file(url: str, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(url, stream=True)
    r.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

def _extract_tar_gz(content: bytes, dest: Path):
    dest.mkdir(parents=True, exist_ok=True)

    fileobj = io.BytesIO(content)

    try:
        with tarfile.open(fileobj=fileobj, mode="r:gz") as tar:
            tar.extractall(dest)
            return
    except tarfile.ReadError:
        pass

    fileobj.seek(0)
    try:
        with tarfile.open(fileobj=fileobj, mode="r:") as tar:
            tar.extractall(dest)
            return
    except tarfile.ReadError:
        pass

    raise RuntimeError()

def _extract_zip(content: bytes, dest: Path):
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        z.extractall(dest)

def _github_raw(url: str) -> str:
    return url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")

def _bitbucket_raw(url: str) -> str:
    return url.replace("/src/", "/raw/")

def download_pidsmaker_orthrus():
    save_path = DARPA_LABEL_PATH / "pidsmaker"

    urls = [
        # E3 CADETS
        "https://github.com/ubc-provenance/PIDSMaker/blob/main/Ground_Truth/orthrus/E3-CADETS/node_Nginx_Backdoor_06.csv",
        "https://github.com/ubc-provenance/PIDSMaker/blob/main/Ground_Truth/orthrus/E3-CADETS/node_Nginx_Backdoor_11.csv",
        "https://github.com/ubc-provenance/PIDSMaker/blob/main/Ground_Truth/orthrus/E3-CADETS/node_Nginx_Backdoor_12.csv",
        "https://github.com/ubc-provenance/PIDSMaker/blob/main/Ground_Truth/orthrus/E3-CADETS/node_Nginx_Backdoor_13.csv",

        # E3 CLEARSCOPE
        "https://github.com/ubc-provenance/PIDSMaker/blob/main/Ground_Truth/orthrus/E3-CLEARSCOPE/node_clearscope_e3_firefox_0411.csv",
        "https://github.com/ubc-provenance/PIDSMaker/blob/main/Ground_Truth/orthrus/E3-CLEARSCOPE/node_clearscope_e3_firefox_0412.csv",

        # E3 FIVEDIRECTIONS
        "https://github.com/ubc-provenance/PIDSMaker/blob/main/Ground_Truth/orthrus/E3-FIVEDIRECTIONS/node_fivedirections_e3_browser_0412.csv",
        "https://github.com/ubc-provenance/PIDSMaker/blob/main/Ground_Truth/orthrus/E3-FIVEDIRECTIONS/node_fivedirections_e3_excel_0409.csv",
        "https://github.com/ubc-provenance/PIDSMaker/blob/main/Ground_Truth/orthrus/E3-FIVEDIRECTIONS/node_fivedirections_e3_firefox_0411.csv",

        # E3 THEIA
        "https://github.com/ubc-provenance/PIDSMaker/blob/main/Ground_Truth/orthrus/E3-THEIA/node_Browser_Extension_Drakon_Dropper.csv",
        "https://github.com/ubc-provenance/PIDSMaker/blob/main/Ground_Truth/orthrus/E3-THEIA/node_Firefox_Backdoor_Drakon_In_Memory.csv",

        # E3 TRACE
        "https://github.com/ubc-provenance/PIDSMaker/blob/main/Ground_Truth/orthrus/E3-TRACE/node_trace_e3_firefox_0410.csv",
        "https://github.com/ubc-provenance/PIDSMaker/blob/main/Ground_Truth/orthrus/E3-TRACE/node_trace_e3_phishing_executable_0413.csv",
        "https://github.com/ubc-provenance/PIDSMaker/blob/main/Ground_Truth/orthrus/E3-TRACE/node_trace_e3_pine_0413.csv",

        # E5 CADETS
        "https://github.com/ubc-provenance/PIDSMaker/blob/main/Ground_Truth/orthrus/E5-CADETS/node_Nginx_Drakon_APT.csv",
        "https://github.com/ubc-provenance/PIDSMaker/blob/main/Ground_Truth/orthrus/E5-CADETS/node_Nginx_Drakon_APT_17.csv",

        # E5 CLEARSCOPE
        "https://github.com/ubc-provenance/PIDSMaker/blob/main/Ground_Truth/orthrus/E5-CLEARSCOPE/node_clearscope_e5_appstarter_0515.csv",
        "https://github.com/ubc-provenance/PIDSMaker/blob/main/Ground_Truth/orthrus/E5-CLEARSCOPE/node_clearscope_e5_firefox_0517.csv",
        "https://github.com/ubc-provenance/PIDSMaker/blob/main/Ground_Truth/orthrus/E5-CLEARSCOPE/node_clearscope_e5_lockwatch_0517.csv",
        "https://github.com/ubc-provenance/PIDSMaker/blob/main/Ground_Truth/orthrus/E5-CLEARSCOPE/node_clearscope_e5_tester_0517.csv",

        # E5 FIVEDIRECTIONS
        "https://github.com/ubc-provenance/PIDSMaker/blob/main/Ground_Truth/orthrus/E5-FIVEDIRECTIONS/node_fivedirections_e5_bits_0515.csv",
        "https://github.com/ubc-provenance/PIDSMaker/blob/main/Ground_Truth/orthrus/E5-FIVEDIRECTIONS/node_fivedirections_e5_copykatz_0509.csv",
        "https://github.com/ubc-provenance/PIDSMaker/blob/main/Ground_Truth/orthrus/E5-FIVEDIRECTIONS/node_fivedirections_e5_dns_0517.csv",
        "https://github.com/ubc-provenance/PIDSMaker/blob/main/Ground_Truth/orthrus/E5-FIVEDIRECTIONS/node_fivedirections_e5_drakon_0517.csv",

        # E5 THEIA
        "https://github.com/ubc-provenance/PIDSMaker/blob/main/Ground_Truth/orthrus/E5-THEIA/node_THEIA_1_Firefox_Drakon_APT_BinFmt_Elevate_Inject.csv",

        # E5 TRACE
        "https://github.com/ubc-provenance/PIDSMaker/blob/main/Ground_Truth/orthrus/E5-TRACE/node_Trace_Firefox_Drakon.csv",

        # OpTC
        "https://github.com/ubc-provenance/PIDSMaker/blob/main/Ground_Truth/orthrus/h051/node_h051_0925.csv",
        "https://github.com/ubc-provenance/PIDSMaker/blob/main/Ground_Truth/orthrus/h201/node_h201_0923.csv",
        "https://github.com/ubc-provenance/PIDSMaker/blob/main/Ground_Truth/orthrus/h501/node_h501_0924.csv",
    ]

    for url in urls:
        raw_url = _github_raw(url)
        filename = raw_url.split("/")[-1]
        _download_file(raw_url, save_path / filename)

def download_flash_threatrace():
    save_path = DARPA_LABEL_PATH / "flash"

    urls = [
        "https://github.com/DART-Laboratory/Flash-IDS/blob/main/data_files/cadets.json",
        "https://github.com/DART-Laboratory/Flash-IDS/blob/main/data_files/fivedirections.json",
        "https://github.com/DART-Laboratory/Flash-IDS/blob/main/data_files/theia.json",
        "https://github.com/DART-Laboratory/Flash-IDS/blob/main/data_files/trace.json",
        "https://github.com/DART-Laboratory/Flash-IDS/blob/main/data_files/optc.txt",
    ]

    for url in urls:
        raw_url = _github_raw(url)
        filename = raw_url.split("/")[-1]
        _download_file(raw_url, save_path / filename)

def downlaod_and_extract_wwtawwtal_reapr():
    save_path = DARPA_LABEL_PATH / "wwtawwtal"

    files = [
        # CSVs
        "https://bitbucket.org/sts-lab/reapr-ground-truth/src/main/darpa-tc-engagement3/cadets_labels.csv",
        "https://bitbucket.org/sts-lab/reapr-ground-truth/src/main/darpa-tc-engagement3/fivedirections_labels.csv",
        "https://bitbucket.org/sts-lab/reapr-ground-truth/src/main/darpa-tc-engagement3/theia_labels.csv",
        "https://bitbucket.org/sts-lab/reapr-ground-truth/src/main/darpa-tc-engagement3/trace_labels.csv",

        # TAR.GZ
        "https://bitbucket.org/sts-lab/reapr-ground-truth/src/main/darpa-tc-engagement3/cadets_edge_labels.tar.gz",
        "https://bitbucket.org/sts-lab/reapr-ground-truth/src/main/darpa-tc-engagement3/fivedirections_edge_labels.tar.gz",
        "https://bitbucket.org/sts-lab/reapr-ground-truth/src/main/darpa-tc-engagement3/theia_edge_labels.tar.gz",
    ]

    for url in files:
        raw_url = _bitbucket_raw(url)
        filename = url.split("/")[-1]

        r = requests.get(raw_url)
        r.raise_for_status()

        if filename.endswith(".tar.gz"):
            _extract_tar_gz(r.content, save_path)
        else:
            _download_file(raw_url, save_path / filename)

def downlaod_and_extract_revisiting():
    save_path = DARPA_LABEL_PATH / "revisiting_optc"

    url = "https://github.com/AT03380/optc-labels/blob/main/labels/malicious.zip"
    raw_url = _github_raw(url)

    r = requests.get(raw_url)
    r.raise_for_status()

    _extract_zip(r.content, save_path)