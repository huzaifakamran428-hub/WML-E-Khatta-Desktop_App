"""
Central configuration for WML E-Khatta.

Everything now runs on this computer: the data lives in one local database
file (SQLite) inside the user's application-data folder. There is no remote
server any more.
"""
import json
import os
import sys
from pathlib import Path

APP_NAME = "WML_EKhatta"            # folder name used for local data
DISPLAY_NAME = "WML E-Khatta"       # name shown to people
STORE_TAGLINE = "Waqare Medina Computers & Laptop"


def _data_dir() -> Path:
    override = os.environ.get("WML_DATA_DIR")     # used for testing / portable installs
    if override:
        path = Path(override)
    elif sys.platform == "win32":
        base = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        path = Path(base) / APP_NAME
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        base = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
        path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


DATA_DIR = _data_dir()
DB_FILE = DATA_DIR / "wml_ekhatta.db"
SETTINGS_FILE = DATA_DIR / "settings.json"       # non-sensitive preferences only
DRIVE_TOKEN_FILE = DATA_DIR / "drive_token.json"
DRIVE_CREDENTIALS_FILE = DATA_DIR / "google_credentials.json"
BACKUP_DIR = DATA_DIR / "backups"
UI_CACHE_DIR = DATA_DIR / "ui_cache"

BACKUP_FILE_NAME = "WML_E-Khatta_backup.db"


def app_root() -> Path:
    """Folder that contains the `assets` folder (works when packaged too)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def asset_path(name: str) -> str:
    return str(app_root() / "assets" / name)


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_settings(data: dict) -> None:
    try:
        SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


class Endpoint:
    """Names of the data 'endpoints' the screens talk to (same names as before)."""
    USERS = "users/"
    LAPTOPS = "laptops/"
    CUSTOMERS = "customers/"
    SHOPKEEPERS = "shopkeepers/"
    SHOPKEEPER_LAPTOPS = "shopkeeper-laptops/"
    SHOPKEEPER_EXTRA_MONEY = "shopkeeper-extra-money/"
    SHOPKEEPER_PAYMENTS = "shopkeeper-payments/"
    SALES = "sales/"
    CREDIT_PLANS = "credit-plans/"
    PAYMENTS = "payments/"
    NOTIFICATIONS = "notifications/"
    REPORT_SALES = "reports/sales/"
    REPORT_PROFIT = "reports/profit/"
    REPORT_INVENTORY = "reports/inventory/"
    REPORT_INVESTMENT = "reports/investment/"
    REPORT_OUTSTANDING = "reports/outstanding/"
    REPORT_PAYMENTS = "reports/payments/"
    DASHBOARD = "dashboard/"
    STORE_SETTINGS = "store-settings/"
    AUDIT_LOGS = "audit-logs/"
