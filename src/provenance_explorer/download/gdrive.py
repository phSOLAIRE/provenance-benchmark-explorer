"""
Download and query functions for interacting with the DARPA files hosted at Fivedirections' GDrive.
!!! Run the one-time setup snippet first (see setup.md > Google Drive Setup) !!!
"""
import requests
import requests

from pathlib import Path
from typing import List

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

GDRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
TOKEN_PATH = Path("~/gdrive_token.json").expanduser()

def gdrive_auth(token_path: Path = TOKEN_PATH) -> Credentials:
    """
    Load stored OAuth credentials and refresh if expired.
    !!! Run the one-time setup snippet first (see project setup.md) !!!
    """
    creds = Credentials.from_authorized_user_file(str(token_path))
    if creds.expired:
        creds.refresh(Request())
        token_path.write_text(creds.to_json())
    return creds

def _headers(creds: Credentials) -> dict:
    """Auth headers, for refreshing the token."""
    if creds.expired:
        creds.refresh(Request())
    return {"Authorization": f"Bearer {creds.token}"}

def list_items_in_folder(creds: Credentials, folder_id: str) -> List[List[str]]:
    """Returns list of [name, mimeType, gdrive_id] for items in a folder."""
    items, page_token = [], None
    while True:
        params = {
            "q": f"'{folder_id}' in parents and trashed = false",
            "fields": "nextPageToken, files(id, name, mimeType)",
            "pageSize": 1000,
        }
        if page_token:
            params["pageToken"] = page_token
        resp = requests.get(GDRIVE_FILES_URL, headers=_headers(creds), params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        items.extend([f["name"], f["mimeType"], f["id"]] for f in data.get("files", []))
        if not (page_token := data.get("nextPageToken")):
            break

    return items

def list_items_recursive(creds: Credentials, folder_id: str, prefix: str = "") -> List[List[str]]:
    """Recursively list all files. Returns [relative_path, mimeType, gdrive_id]."""
    result = []
    for name, mime, gid in list_items_in_folder(creds, folder_id):
        path = f"{prefix}/{name}" if prefix else name
        if mime == "application/vnd.google-apps.folder":
            result.extend(list_items_recursive(creds, gid, prefix=path))
        else:
            result.append([path, mime, gid])
    return result

def download_file_to_path(creds: Credentials, file_id: str, download_path: Path, quiet: bool = False) -> None:
    """Download a Drive file by ID. Writes atomically via .part tmp file."""
    download_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"{GDRIVE_FILES_URL}/{file_id}"
 
    meta = requests.get(url, headers=_headers(creds), params={"fields": "id,name,size,mimeType"}, timeout=60)
    meta.raise_for_status()
    if not quiet:
        m = meta.json()
        print(f"Download: {m.get('name')} (id={file_id}, size={m.get('size')}, mime={m.get('mimeType')})")
 
    with requests.get(url, headers=_headers(creds), params={"alt": "media"}, stream=True, timeout=60) as r:
        r.raise_for_status()
        tmp = download_path.with_suffix(download_path.suffix + ".part")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
        tmp.replace(download_path)
