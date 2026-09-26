"""
Local database (SQLite) -- the single place where all shop data lives.

One file on this computer: <app data folder>/wml_ekhatta.db
Passwords are never stored; only a salted PBKDF2 hash is kept.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from app import config

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS shopkeepers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reference_number TEXT UNIQUE,
    name TEXT NOT NULL,
    phone TEXT NOT NULL DEFAULT '',
    cnic TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    email TEXT NOT NULL DEFAULT '',
    first_name TEXT NOT NULL DEFAULT '',
    last_name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'READ_ONLY',
    phone_number TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    shopkeeper INTEGER REFERENCES shopkeepers(id) ON DELETE SET NULL,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS laptops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand TEXT NOT NULL,
    model_name TEXT NOT NULL,
    generation TEXT NOT NULL DEFAULT '',
    processor TEXT NOT NULL DEFAULT '',
    cpu_cores INTEGER NOT NULL DEFAULT 0,
    ram TEXT NOT NULL DEFAULT '',
    storage TEXT NOT NULL DEFAULT '',
    gpu TEXT NOT NULL DEFAULT '',
    screen_size TEXT NOT NULL DEFAULT '',
    condition TEXT NOT NULL DEFAULT 'NEW',
    serial_number TEXT NOT NULL DEFAULT '',
    purchase_price REAL NOT NULL DEFAULT 0,
    sale_price REAL NOT NULL DEFAULT 0,
    discount_amount REAL NOT NULL DEFAULT 0,
    discount_percent REAL NOT NULL DEFAULT 0,
    quantity INTEGER NOT NULL DEFAULT 0,
    supplier TEXT NOT NULL DEFAULT '',
    purchase_date TEXT,
    warranty TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    is_archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_no TEXT NOT NULL UNIQUE,
    customer INTEGER NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    sale_price REAL NOT NULL DEFAULT 0,
    discount_amount REAL NOT NULL DEFAULT 0,
    discount_percent REAL NOT NULL DEFAULT 0,
    payment_type TEXT NOT NULL DEFAULT 'CASH',
    amount_received REAL NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    sale_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sale_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
    product INTEGER NOT NULL REFERENCES laptops(id) ON DELETE RESTRICT,
    quantity INTEGER NOT NULL DEFAULT 1,
    sale_price REAL NOT NULL DEFAULT 0,
    purchase_cost_snapshot REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS shopkeeper_laptops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shopkeeper INTEGER NOT NULL REFERENCES shopkeepers(id) ON DELETE CASCADE,
    inventory_laptop INTEGER NOT NULL REFERENCES laptops(id) ON DELETE RESTRICT,
    brand TEXT NOT NULL DEFAULT '',
    model_name TEXT NOT NULL DEFAULT '',
    core_generation TEXT NOT NULL DEFAULT '',
    price REAL NOT NULL DEFAULT 0,
    seq INTEGER NOT NULL DEFAULT 1,
    item_reference TEXT NOT NULL DEFAULT '',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS shopkeeper_extra_money (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shopkeeper INTEGER NOT NULL REFERENCES shopkeepers(id) ON DELETE CASCADE,
    amount REAL NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    seq INTEGER NOT NULL DEFAULT 1,
    item_reference TEXT NOT NULL DEFAULT '',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS shopkeeper_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shopkeeper INTEGER NOT NULL REFERENCES shopkeepers(id) ON DELETE CASCADE,
    laptop_item INTEGER REFERENCES shopkeeper_laptops(id) ON DELETE CASCADE,
    extra_money INTEGER REFERENCES shopkeeper_extra_money(id) ON DELETE CASCADE,
    amount REAL NOT NULL DEFAULT 0,
    method TEXT NOT NULL DEFAULT 'CASH',
    note TEXT NOT NULL DEFAULT '',
    payment_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS credit_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer INTEGER NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    laptop INTEGER REFERENCES laptops(id) ON DELETE SET NULL,
    total_amount REAL NOT NULL DEFAULT 0,
    down_payment REAL NOT NULL DEFAULT 0,
    installment_amount REAL NOT NULL DEFAULT 0,
    due_date TEXT,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    credit_plan INTEGER NOT NULL REFERENCES credit_plans(id) ON DELETE CASCADE,
    amount REAL NOT NULL DEFAULT 0,
    method TEXT NOT NULL DEFAULT 'CASH',
    note TEXT NOT NULL DEFAULT '',
    payment_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL DEFAULT 'INFO',
    title TEXT NOT NULL DEFAULT '',
    message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    read_at TEXT,
    dedupe_key TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    user_display TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL DEFAULT '',
    entity TEXT NOT NULL DEFAULT '',
    entity_id TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS store_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    store_name TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    phone_number TEXT NOT NULL DEFAULT '',
    ceo_name TEXT NOT NULL DEFAULT '',
    ceo_contact_number TEXT NOT NULL DEFAULT '',
    thank_you_message TEXT NOT NULL DEFAULT '',
    low_stock_alerts_enabled INTEGER NOT NULL DEFAULT 1,
    due_today_reminder_enabled INTEGER NOT NULL DEFAULT 1,
    two_day_reminder_enabled INTEGER NOT NULL DEFAULT 1,
    low_stock_threshold INTEGER NOT NULL DEFAULT 2
);

CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(sale_date);
CREATE INDEX IF NOT EXISTS idx_items_sale ON sale_items(sale);
CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_logs(timestamp);
"""

DEFAULT_STORE = {
    "store_name": "Waqare Medina Computers & Laptop",
    "address": "PF Road, Waqare Medina, Mianwali, Pakistan",
    "phone_number": "",
    "ceo_name": "M Yasir",
    "ceo_contact_number": "03288621265",
    "thank_you_message": "Thank you for choosing us!",
}


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def connect(path=None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path or config.DB_FILE), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaction(path=None):
    """Open, run, commit -- or roll everything back if anything fails."""
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(path=None) -> None:
    with transaction(path) as conn:
        conn.executescript(SCHEMA)
        row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        if row is None:
            conn.execute("INSERT INTO meta (key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
        if conn.execute("SELECT 1 FROM store_settings WHERE id=1").fetchone() is None:
            cols = ", ".join(DEFAULT_STORE)
            marks = ", ".join("?" for _ in DEFAULT_STORE)
            conn.execute(f"INSERT INTO store_settings (id, {cols}) VALUES (1, {marks})", tuple(DEFAULT_STORE.values()))


def next_counter(conn: sqlite3.Connection, key: str) -> int:
    """Ever-increasing counter (receipt numbers, references) that never reuses a number."""
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    value = (int(row["value"]) if row else 0) + 1
    conn.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (key, str(value)))
    return value


# -- passwords ---------------------------------------------------------

_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        _ITERATIONS, base64.b64encode(salt).decode(), base64.b64encode(digest).decode())


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iters, salt_b64, digest_b64 = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iters))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False
