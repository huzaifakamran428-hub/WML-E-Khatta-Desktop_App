"""
Backups for WML E-Khatta.

* Snapshot / restore of the local database (works with plain files too).
* Google Drive upload / download using Google's official OAuth "installed app"
  flow (browser sign-in, PKCE) and the Drive REST API. It only ever touches the
  ONE backup file this app created (scope: drive.file) -- it cannot see or
  change any other file in the person's Drive.

Nothing here knows about the screens, so it can be tested on its own.
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import secrets
import shutil
import sqlite3
import tempfile
import threading
import time
import urllib.parse
import webbrowser
from datetime import datetime
from pathlib import Path

import requests

from app import config, db

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
FILES_URL = "https://www.googleapis.com/drive/v3/files"
UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
SCOPE = "https://www.googleapis.com/auth/drive.file"

REQUIRED_TABLES = {"meta", "users", "laptops", "customers", "sales", "store_settings"}


class BackupError(Exception):
    """Something went wrong; the message is written for the shop owner."""


# ======================================================================
# database snapshot / restore (local, no internet)
# ======================================================================

def snapshot_to(dest: str | Path) -> Path:
    """Write a consistent copy of the live database to `dest`."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    src = sqlite3.connect(str(config.DB_FILE), timeout=15)
    out = sqlite3.connect(str(dest))
    try:
        src.backup(out)
    finally:
        out.close()
        src.close()
    return dest


def validate_backup_file(path: str | Path) -> None:
    """Refuse anything that is not a healthy WML E-Khatta backup."""
    try:
        conn = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    except sqlite3.Error:
        raise BackupError("That file is not a valid backup.")
    try:
        try:
            ok = conn.execute("PRAGMA integrity_check").fetchone()[0]
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        except sqlite3.DatabaseError:
            raise BackupError("That file is not a valid backup.")
        if ok != "ok":
            raise BackupError("The backup file is damaged, so it was not restored. Your current data is untouched.")
        if not REQUIRED_TABLES <= tables:
            raise BackupError("That file is not a WML E-Khatta backup.")
        admins = conn.execute("SELECT COUNT(*) FROM users WHERE role='ADMIN' AND is_active=1").fetchone()[0]
        if admins == 0:
            raise BackupError("That backup has no administrator account, so it was not restored.")
    finally:
        conn.close()


def apply_restore(path: str | Path) -> Path:
    """Replace ALL current data with the backup. A safety copy of the current
    data is kept first. Returns the safety copy's path."""
    validate_backup_file(path)
    config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    safety = config.BACKUP_DIR / f"before_restore_{datetime.now():%Y%m%d_%H%M%S}.db"
    snapshot_to(safety)
    _prune_safety_copies()
    src = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    live = sqlite3.connect(str(config.DB_FILE), timeout=15)
    try:
        src.backup(live)
    finally:
        live.close()
        src.close()
    db.init_db()       # bring an older backup up to date if needed
    return safety


def _prune_safety_copies(keep: int = 5) -> None:
    files = sorted(config.BACKUP_DIR.glob("before_restore_*.db"))
    for old in files[:-keep]:
        try:
            old.unlink()
        except OSError:
            pass


# ======================================================================
# Google Drive
# ======================================================================

def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (name required by http.server)
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        self.server.result = {k: v[0] for k, v in query.items()}   # type: ignore[attr-defined]
        ok = "code" in query
        body = (
            "<html><body style='font-family:sans-serif;text-align:center;padding-top:15vh'>"
            f"<h2>{'Google Drive connected' if ok else 'Google Drive was not connected'}</h2>"
            "<p>You can close this tab and go back to WML E-Khatta.</p></body></html>"
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):   # keep the console quiet
        pass


class DriveBackup:
    def __init__(self, http=None):
        self.http = http or requests.Session()
        self._cancel = threading.Event()
        self._access: tuple[str, float] | None = None

    # -- credentials (the Google "Desktop app" client from Google Cloud) --

    @staticmethod
    def credentials_path() -> Path | None:
        for candidate in (config.DRIVE_CREDENTIALS_FILE, Path(config.asset_path("google_credentials.json"))):
            if candidate.exists():
                return candidate
        return None

    def credentials_available(self) -> bool:
        return self.credentials_path() is not None

    def install_credentials(self, source: str | Path) -> None:
        try:
            data = json.loads(Path(source).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise BackupError("That is not a valid Google credentials file.")
        block = data.get("installed")
        if not block:
            raise BackupError("This credentials file is for a website. In Google Cloud, create an OAuth client "
                              "of type 'Desktop app' and download that file instead.")
        if not block.get("client_id") or not block.get("client_secret"):
            raise BackupError("The credentials file is missing the client id or secret.")
        shutil.copyfile(source, config.DRIVE_CREDENTIALS_FILE)

    def _client(self) -> tuple[str, str]:
        path = self.credentials_path()
        if path is None:
            raise BackupError("Google Drive is not set up on this computer yet. Choose your Google credentials file first.")
        try:
            block = json.loads(path.read_text(encoding="utf-8"))["installed"]
            return block["client_id"], block["client_secret"]
        except (OSError, ValueError, KeyError):
            raise BackupError("The Google credentials file could not be read.")

    # -- sign-in ---------------------------------------------------------

    def _read_token(self) -> dict:
        try:
            return json.loads(config.DRIVE_TOKEN_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def is_connected(self) -> bool:
        return bool(self._read_token().get("refresh_token"))

    def cancel_connect(self):
        self._cancel.set()

    def connect(self, timeout: int = 240) -> None:
        """Open the browser, let the person sign in to Google, save the permission."""
        client_id, client_secret = self._client()
        self._cancel.clear()
        verifier = _b64url(secrets.token_bytes(48))
        challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
        state = secrets.token_urlsafe(16)

        server = http.server.HTTPServer(("127.0.0.1", 0), _CallbackHandler)
        server.result = None            # type: ignore[attr-defined]
        server.timeout = 0.5
        redirect = f"http://127.0.0.1:{server.server_port}"
        url = AUTH_URL + "?" + urllib.parse.urlencode({
            "client_id": client_id, "redirect_uri": redirect, "response_type": "code", "scope": SCOPE,
            "access_type": "offline", "prompt": "consent", "state": state,
            "code_challenge": challenge, "code_challenge_method": "S256",
        })
        webbrowser.open(url)
        deadline = time.time() + timeout
        try:
            while server.result is None:     # type: ignore[attr-defined]
                if self._cancel.is_set():
                    raise BackupError("Sign-in cancelled.")
                if time.time() > deadline:
                    raise BackupError("Sign-in took too long. Please try again.")
                server.handle_request()
        finally:
            server.server_close()
        result = server.result               # type: ignore[attr-defined]
        if result.get("state") != state or "code" not in result:
            raise BackupError("Google did not confirm the sign-in. Nothing was connected.")
        resp = self.http.post(TOKEN_URL, data={
            "client_id": client_id, "client_secret": client_secret, "code": result["code"],
            "code_verifier": verifier, "redirect_uri": redirect, "grant_type": "authorization_code",
        }, timeout=30)
        payload = self._json(resp)
        if not payload.get("refresh_token"):
            raise BackupError("Google did not give permission for backups. Please try connecting again.")
        self._save_token({"refresh_token": payload["refresh_token"]})
        self._access = (payload["access_token"], time.time() + int(payload.get("expires_in", 3000)) - 60)

    def disconnect(self):
        self._access = None
        try:
            config.DRIVE_TOKEN_FILE.unlink()
        except OSError:
            pass

    @staticmethod
    def _save_token(data: dict):
        config.DRIVE_TOKEN_FILE.write_text(json.dumps(data), encoding="utf-8")
        try:
            os.chmod(config.DRIVE_TOKEN_FILE, 0o600)
        except OSError:
            pass

    @staticmethod
    def _json(resp) -> dict:
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if resp.status_code >= 400:
            message = ""
            err = data.get("error")
            if isinstance(err, dict):
                message = err.get("message", "")
            elif isinstance(err, str):
                message = data.get("error_description") or err
            raise BackupError(f"Google Drive said: {message or resp.status_code}")
        return data

    def _token(self) -> str:
        if self._access and self._access[1] > time.time():
            return self._access[0]
        refresh = self._read_token().get("refresh_token")
        if not refresh:
            raise BackupError("Google Drive is not connected.")
        client_id, client_secret = self._client()
        try:
            resp = self.http.post(TOKEN_URL, data={
                "client_id": client_id, "client_secret": client_secret,
                "refresh_token": refresh, "grant_type": "refresh_token"}, timeout=30)
        except requests.RequestException:
            raise BackupError("Could not reach Google. Check the internet connection.")
        if resp.status_code in (400, 401):
            self.disconnect()
            raise BackupError("Google Drive permission expired. Please connect again.")
        payload = self._json(resp)
        self._access = (payload["access_token"], time.time() + int(payload.get("expires_in", 3000)) - 60)
        return self._access[0]

    def _auth(self) -> dict:
        return {"Authorization": f"Bearer {self._token()}"}

    def _call(self, method: str, url: str, **kwargs):
        kwargs.setdefault("timeout", 60)
        try:
            return getattr(self.http, method)(url, headers={**self._auth(), **kwargs.pop("headers", {})}, **kwargs)
        except requests.RequestException:
            raise BackupError("Could not reach Google Drive. Check the internet connection.")

    # -- the one backup file ---------------------------------------------

    def _find(self) -> dict | None:
        resp = self._call("get", FILES_URL, params={
            "q": f"name = '{config.BACKUP_FILE_NAME}' and trashed = false",
            "fields": "files(id,name,modifiedTime,size)", "orderBy": "modifiedTime desc",
            "pageSize": 1, "spaces": "drive"})
        files = self._json(resp).get("files", [])
        return files[0] if files else None

    def remote_info(self) -> dict | None:
        """{'modifiedTime': ..., 'size': ...} of the backup in Drive, or None if there isn't one."""
        return self._find()

    def upload_backup(self) -> str:
        """Snapshot the live database and upload it, replacing the previous backup."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = snapshot_to(Path(tmp) / config.BACKUP_FILE_NAME)
            data = snap.read_bytes()
        existing = self._find()
        if existing:
            resp = self._call("patch", f"{UPLOAD_URL}/{existing['id']}", params={"uploadType": "media"},
                              data=data, headers={"Content-Type": "application/octet-stream"})
        else:
            boundary = "wml" + secrets.token_hex(8)
            meta = json.dumps({"name": config.BACKUP_FILE_NAME, "mimeType": "application/octet-stream"})
            body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n"
                    f"--{boundary}\r\nContent-Type: application/octet-stream\r\n\r\n").encode() + data + \
                   f"\r\n--{boundary}--".encode()
            resp = self._call("post", UPLOAD_URL, params={"uploadType": "multipart"}, data=body,
                              headers={"Content-Type": f"multipart/related; boundary={boundary}"})
        self._json(resp)
        return datetime.now().isoformat(timespec="seconds")

    def download_backup(self, dest: str | Path) -> Path:
        info = self._find()
        if not info:
            raise BackupError("No backup was found in your Google Drive yet.")
        resp = self._call("get", f"{FILES_URL}/{info['id']}", params={"alt": "media"})
        if resp.status_code >= 400:
            self._json(resp)
        Path(dest).write_bytes(resp.content)
        return Path(dest)

    def restore_from_drive(self) -> Path:
        with tempfile.TemporaryDirectory() as tmp:
            downloaded = self.download_backup(Path(tmp) / "restore.db")
            return apply_restore(downloaded)
