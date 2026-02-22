"""
Google Drive API service: authentication, list folders/files, copy, resolve names.
"""
import json
import os
import ssl

# Force TLS 1.2+ process-wide to fix [SSL: WRONG_VERSION_NUMBER] (proxy/AV/old OpenSSL).
_orig_create_default_context = ssl.create_default_context
def _create_default_context_tls12():
    ctx = _orig_create_default_context()
    if hasattr(ssl, "TLSVersion") and hasattr(ctx, "minimum_version"):
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx
ssl.create_default_context = _create_default_context_tls12

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

import httplib2
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/drive"]
TOKEN_PATH = "token.json"
CREDENTIALS_PATH = "credentials.json"


class _TLS12Adapter(HTTPAdapter):
    """Force TLS 1.2+ for all HTTPS connections (avoids WRONG_VERSION_NUMBER)."""
    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context()
        if hasattr(ssl, "TLSVersion") and hasattr(ctx, "minimum_version"):
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        kwargs.setdefault("ssl_context", ctx)
        return super().init_poolmanager(*args, **kwargs)


class _RequestsHttpCompat:
    """httplib2-like interface using requests with TLS 1.2 only. For use with AuthorizedHttp."""
    def __init__(self):
        self._session = requests.Session()
        self._session.mount("https://", _TLS12Adapter())
        self._session.mount("http://", _TLS12Adapter())

    def request(self, uri, method="GET", body=None, headers=None, redirections=1, connection_type=None):
        headers = dict(headers or {})
        resp = self._session.request(
            method, uri, data=body, headers=headers, timeout=60, allow_redirects=(redirections > 0)
        )
        # Build httplib2.Response-compatible object
        resp_headers = dict(resp.headers)
        resp_headers["status"] = str(resp.status_code)
        response = httplib2.Response(resp_headers)
        response.status = resp.status_code
        response.reason = resp.reason or ""
        return response, resp.content

    def close(self):
        self._session.close()


def _check_credentials_type():
    """Ensure credentials.json is for a Desktop (installed) app, not Web app."""
    with open(CREDENTIALS_PATH, "r") as f:
        data = json.load(f)
    if "web" in data and "installed" not in data:
        raise ValueError(
            "Your credentials.json is for a 'Web application' OAuth client. "
            "This app needs a 'Desktop application' client. In Google Cloud Console: "
            "APIs & Services → Credentials → Create Credentials → OAuth client ID → "
            "choose 'Desktop application', then download the JSON and replace credentials.json."
        )


def _make_http():
    """
    Use requests with TLS 1.2–only adapter (httplib2-like interface).
    Avoids [SSL: WRONG_VERSION_NUMBER] on some Windows/proxy/AV setups where httplib2 fails.
    """
    return _RequestsHttpCompat()


def get_drive_service():
    """
    Return an authenticated Drive API v3 service.
    Uses token.json if present; otherwise runs OAuth flow and saves token.
    Uses TLS 1.2+ to avoid SSL WRONG_VERSION_NUMBER errors.
    """
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                raise FileNotFoundError(
                    f"Missing {CREDENTIALS_PATH}. Download from Google Cloud Console "
                    "and save in the project root."
                )
            _check_credentials_type()
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
    # Use TLS 1.2+ to avoid [SSL: WRONG_VERSION_NUMBER] on some networks/Python builds
    http = AuthorizedHttp(creds, http=_make_http())
    return build("drive", "v3", http=http)


def list_folders(service):
    """
    List all folders in the user's Drive (paginated, 1000 per page), plus "My Drive (root)".
    Uses supportsAllDrives so shared-drive folders are included.
    """
    folders = [{"id": "root", "name": "My Drive (root)"}]
    page_token = None
    try:
        while True:
            kwargs = {
                "q": "mimeType='application/vnd.google-apps.folder' and trashed=false",
                "pageSize": 1000,
                "fields": "nextPageToken, files(id, name)",
                "supportsAllDrives": True,
                "includeItemsFromAllDrives": False,
            }
            if page_token:
                kwargs["pageToken"] = page_token
            results = service.files().list(**kwargs).execute()
            folders.extend(results.get("files", []))
            page_token = results.get("nextPageToken")
            if not page_token:
                break
    except HttpError as e:
        raise
    return folders


def list_folders_with_parents(service):
    """
    List all folders with parent ids (paginated). Used to build folder tree.
    Returns list of dicts with 'id', 'name', 'parents' (list, may be empty for root).
    """
    folders = []
    page_token = None
    try:
        while True:
            kwargs = {
                "q": "mimeType='application/vnd.google-apps.folder' and trashed=false",
                "pageSize": 1000,
                "fields": "nextPageToken, files(id, name, parents)",
                "supportsAllDrives": True,
                "includeItemsFromAllDrives": False,
            }
            if page_token:
                kwargs["pageToken"] = page_token
            results = service.files().list(**kwargs).execute()
            for f in results.get("files", []):
                if "parents" not in f:
                    f["parents"] = []
                folders.append(f)
            page_token = results.get("nextPageToken")
            if not page_token:
                break
    except HttpError as e:
        raise
    return folders


def build_folder_paths(service):
    """
    Build full folder structure and return a list of (path_label, folder_id).
    Paths look like "My Drive (root)", "My Drive / card2", "My Drive / card2 / subfolder".
    Duplicate path names get a (2), (3) suffix. Sorted by path for stable dropdown.
    """
    raw = list_folders_with_parents(service)
    id_to_folder = {f["id"]: f for f in raw}
    # Virtual root
    id_to_folder["root"] = {"id": "root", "name": "My Drive (root)", "parents": []}

    def get_children(parent_id):
        return [f for f in raw if f.get("parents") and parent_id in f["parents"]]

    def build_tree(parent_id, path_parts):
        node = id_to_folder.get(parent_id)
        name = node["name"] if node else parent_id
        if path_parts:
            current_path = " / ".join(path_parts + [name])
        else:
            current_path = name
        children = get_children(parent_id)
        children.sort(key=lambda f: (f["name"].lower(), f["id"]))
        result = [(current_path, parent_id)]
        for c in children:
            result.extend(build_tree(c["id"], path_parts + [name]))
        return result

    # Start from root; add any folder whose parent isn't in our list as top-level under "My Drive"
    seen = set()
    paths_and_ids = []

    def add_node(folder_id, path_parts):
        if folder_id in seen:
            return
        seen.add(folder_id)
        node = id_to_folder.get(folder_id)
        name = node["name"] if node else folder_id
        current_path = " / ".join(path_parts + [name]) if path_parts else name
        paths_and_ids.append((current_path, folder_id))
        children = get_children(folder_id)
        children.sort(key=lambda f: (f["name"].lower(), f["id"]))
        for c in children:
            add_node(c["id"], path_parts + [name])

    add_node("root", [])
    # Orphans (parent not in list, e.g. shared drive root): attach under "My Drive" by path
    for f in raw:
        if f["id"] in seen:
            continue
        parents = f.get("parents") or []
        if not parents or parents[0] not in id_to_folder:
            paths_and_ids.append(("My Drive (root) / " + f["name"], f["id"]))
            seen.add(f["id"])
            for c in get_children(f["id"]):
                add_node(c["id"], ["My Drive (root)", f["name"]])

    # Uniquify path labels (same path string -> add (2), (3))
    path_count = {}
    unique = []
    for path, fid in sorted(paths_and_ids, key=lambda x: (x[0].lower(), x[1])):
        path_count[path] = path_count.get(path, 0) + 1
        label = path if path_count[path] == 1 else f"{path}  ({path_count[path]})"
        unique.append((label, fid))
    return unique


def list_files_in_folder(service, folder_id):
    """
    List all files (non-folder) in the given folder. Fetches every page (Drive API max 1000 per page).
    Uses supportsAllDrives so shared-drive folders work. Returns list of dicts with 'id', 'name', 'mimeType'.
    """
    files = []
    page_token = None
    query = f"'{folder_id}' in parents and mimeType!='application/vnd.google-apps.folder' and trashed=false"
    try:
        while True:
            kwargs = {
                "q": query,
                "pageSize": 1000,
                "fields": "nextPageToken, files(id, name, mimeType)",
                "orderBy": "name",
                "supportsAllDrives": True,
                "includeItemsFromAllDrives": False,
            }
            if page_token:
                kwargs["pageToken"] = page_token
            results = service.files().list(**kwargs).execute()
            batch = results.get("files", [])
            files.extend(batch)
            page_token = results.get("nextPageToken")
            if not page_token:
                break
    except HttpError as e:
        raise
    return files


def copy_file_to_folder(service, file_id, file_name, dest_folder_id):
    """
    Copy a file into the destination folder. Source file is unchanged.
    Returns the new file's id (or raises).
    """
    body = {"name": file_name, "parents": [dest_folder_id]}
    result = service.files().copy(fileId=file_id, body=body).execute()
    return result.get("id")


def resolve_names_to_file_ids(service, folder_id, names):
    """
    Resolve a list of file names (trimmed) to (file_id, name) for files in the folder.
    - Match is case-insensitive (e.g. 7B1A0431.JPG matches 7b1a0431.jpg on Drive).
    - If no exact match, try matching by base name (e.g. 7B1A0431 matches 7B1A0431.JPG).
    Returns (list of (file_id, name), list of names_not_found).
    """
    requested = [n.strip() for n in names if n.strip()]
    if not requested:
        return [], []

    files = list_files_in_folder(service, folder_id)
    # Key by lowercase name for case-insensitive match
    name_lower_to_ids = {}
    # Also key by lowercase base name (no extension) for "7B1A0431" -> "7B1A0431.JPG"
    base_lower_to_ids = {}
    for f in files:
        n = f["name"]
        key = n.lower()
        if key not in name_lower_to_ids:
            name_lower_to_ids[key] = []
        name_lower_to_ids[key].append((f["id"], n))
        base = key.rsplit(".", 1)[0] if "." in n else key
        if base not in base_lower_to_ids:
            base_lower_to_ids[base] = []
        base_lower_to_ids[base].append((f["id"], n))

    matched = []
    not_found = []
    for n in requested:
        key = n.lower()
        base = key.rsplit(".", 1)[0] if "." in n else key
        if key in name_lower_to_ids:
            for file_id, file_name in name_lower_to_ids[key]:
                matched.append((file_id, file_name))
        elif base in base_lower_to_ids:
            # Match by base name (e.g. 7B1A0431 matches 7B1A0431.JPG)
            for file_id, file_name in base_lower_to_ids[base]:
                matched.append((file_id, file_name))
        else:
            not_found.append(n)
    return matched, not_found
