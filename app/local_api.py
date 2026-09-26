"""
Local backend for WML E-Khatta.

This replaces the old remote (Render) server. It exposes the same small
"client" interface the screens already use -- list_(), create(), update(),
remove(), get_json() ... -- but everything is answered from the local SQLite
database on this computer.

Rules that used to live on the server live here now:
  * Only ADMIN accounts can change data or open Reports / Users / Audit Log.
  * Purchase prices are never sent to non-admin accounts.
  * Stock goes down when something is sold and back up when a sale is removed.
  * Nothing about the logged-in person is saved to disk: the session lives
    only in memory, so closing the app or logging out forgets it completely.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from datetime import date, datetime, timedelta

from app import db
from app.calc import EPS, final_price, sale_totals
from app.local_reports import Reports

ROLES = ("ADMIN", "READ_ONLY", "SHOPKEEPER")
METHODS = ("CASH", "BANK", "OTHER")
CONDITIONS = ("NEW", "USED", "REFURBISHED")
ADMIN_ONLY_HEADS = {"users", "audit-logs", "reports"}
MAX_FAILED_LOGINS = 5
LOCKOUT_SECONDS = 30


class APIError(Exception):
    """A problem with a request, with a message that is safe to show to people."""

    def __init__(self, message: str, status_code: int | None = None, payload=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.payload = payload


# -- small helpers -------------------------------------------------------

def _num(value, default=0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        raise ValueError("A valid number is required.")


def _clean(spec: dict, data: dict, creating: bool) -> dict:
    """Validate + convert incoming fields. spec: name -> (kind, required)."""
    out, errors = {}, []
    for name, (kind, required) in spec.items():
        if name not in data:
            if creating and required:
                errors.append(f"{name}: This field is required.")
            continue
        raw = data[name]
        try:
            if kind == "str":
                value = "" if raw is None else str(raw).strip()
                if required and not value:
                    raise ValueError("This field may not be blank.")
            elif kind == "int":
                value = int(_num(raw))
                if value < 0:
                    raise ValueError("Must be 0 or more.")
            elif kind == "float":
                value = round(_num(raw), 2)
                if value < 0:
                    raise ValueError("Must be 0 or more.")
            elif kind == "bool":
                value = 1 if raw in (True, 1, "1", "true", "True", "yes") else 0
            elif kind == "date":
                if not raw:
                    if required:
                        raise ValueError("This field is required.")
                    value = None
                else:
                    value = date.fromisoformat(str(raw)[:10]).isoformat()
            elif kind.startswith("choice:"):
                choices = kind[7:].split("|")
                value = str(raw or "").strip().upper()
                if value not in choices:
                    raise ValueError(f"'{raw}' is not a valid choice.")
            else:
                value = raw
        except ValueError as exc:
            errors.append(f"{name}: {exc}")
        else:
            out[name] = value
    if errors:
        raise APIError("; ".join(errors), 400)
    return out


LAPTOP_SPEC = {
    "brand": ("str", True), "model_name": ("str", True), "generation": ("str", False),
    "processor": ("str", False), "cpu_cores": ("int", False), "ram": ("str", False),
    "storage": ("str", False), "gpu": ("str", False), "screen_size": ("str", False),
    "condition": (f"choice:{'|'.join(CONDITIONS)}", False), "serial_number": ("str", False),
    "purchase_price": ("float", False), "sale_price": ("float", False),
    "discount_amount": ("float", False), "discount_percent": ("float", False),
    "quantity": ("int", False), "supplier": ("str", False), "purchase_date": ("date", False),
    "warranty": ("str", False), "notes": ("str", False), "is_archived": ("bool", False),
}
CUSTOMER_SPEC = {"name": ("str", True), "phone": ("str", False), "address": ("str", False), "notes": ("str", False)}
SHOPKEEPER_SPEC = {"name": ("str", True), "phone": ("str", True), "cnic": ("str", False),
                   "address": ("str", False), "notes": ("str", False)}
SALE_SPEC = {
    "sale_price": ("float", False), "discount_amount": ("float", False), "discount_percent": ("float", False),
    "payment_type": (f"choice:{'|'.join(METHODS)}", False), "amount_received": ("float", False),
    "notes": ("str", False),
}
CREDIT_SPEC = {
    "total_amount": ("float", True), "down_payment": ("float", False), "installment_amount": ("float", False),
    "due_date": ("date", True), "notes": ("str", False),
}
STORE_SPEC = {
    "store_name": ("str", False), "address": ("str", False), "phone_number": ("str", False),
    "ceo_name": ("str", False), "ceo_contact_number": ("str", False), "thank_you_message": ("str", False),
    "low_stock_alerts_enabled": ("bool", False), "due_today_reminder_enabled": ("bool", False),
    "two_day_reminder_enabled": ("bool", False),
}


def _rows(cursor) -> list[dict]:
    return [dict(r) for r in cursor.fetchall()]


class LocalClient:
    def __init__(self):
        db.init_db()
        self.current_user: dict | None = None
        self.on_session_expired = None       # kept for screens that still set it
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.RLock()
        self._listeners = []
        self._failed: dict[str, tuple[int, float]] = {}

    # ==================================================================
    # session (memory only -- never written to disk)
    # ==================================================================

    def is_logged_in(self) -> bool:
        return self.current_user is not None

    @property
    def is_admin(self) -> bool:
        return bool(self.current_user and self.current_user.get("role") == "ADMIN")

    def needs_setup(self) -> bool:
        with db.transaction() as conn:
            return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0

    def create_first_admin(self, username: str, password: str, first_name: str = "") -> dict:
        username = username.strip()
        if not username:
            raise APIError("Choose a username.")
        self._check_password_strength(password)
        with db.transaction() as conn:
            if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] != 0:
                raise APIError("An administrator already exists. Please log in.")
            conn.execute(
                "INSERT INTO users (username, first_name, role, password_hash, is_active, created_at) "
                "VALUES (?, ?, 'ADMIN', ?, 1, ?)",
                (username, first_name.strip(), db.hash_password(password), db.now_iso()),
            )
        self._fire_change()
        return self.login(username, password)

    def login(self, username: str, password: str) -> dict:
        key = username.strip().lower()
        count, locked_until = self._failed.get(key, (0, 0.0))
        if locked_until > time.time():
            wait = int(locked_until - time.time()) + 1
            raise APIError(f"Too many wrong attempts. Try again in {wait} seconds.", 429)
        with db.transaction() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username.strip(),)).fetchone()
            ok = bool(row) and db.verify_password(password, row["password_hash"])
            if not ok:
                count += 1
                if count >= MAX_FAILED_LOGINS:
                    self._failed[key] = (0, time.time() + LOCKOUT_SECONDS)
                else:
                    self._failed[key] = (count, 0.0)
                raise APIError("Wrong username or password.", 401)
            if not row["is_active"]:
                raise APIError("This account has been deactivated. Ask an administrator.", 403)
            self._failed.pop(key, None)
            user = self._user_out(conn, row)
            self.current_user = user
            self._conn = conn
            try:
                self._audit("LOGIN", "user", user["id"], f"{user['username']} logged in")
                self._run_reminders()
            finally:
                self._conn = None
        return user

    def logout(self):
        user = self.current_user
        if user:
            try:
                with db.transaction() as conn:
                    self._conn = conn
                    self._audit("LOGOUT", "user", user["id"], f"{user['username']} logged out")
            except Exception:
                pass
            finally:
                self._conn = None
        self.current_user = None

    def add_change_listener(self, fn):
        self._listeners.append(fn)

    def _fire_change(self):
        for fn in list(self._listeners):
            try:
                fn()
            except Exception:
                pass

    @staticmethod
    def _check_password_strength(password: str):
        if len(password or "") < 6:
            raise APIError("Password must be at least 6 characters.")

    # ==================================================================
    # generic entry points used by the screens
    # ==================================================================

    def get_json(self, path: str, params: dict | None = None):
        return self._request("GET", path, None, params or {})

    def post_json(self, path: str, data: dict):
        return self._request("POST", path, data or {}, {})

    def patch_json(self, path: str, data: dict):
        return self._request("PATCH", path, data or {}, {})

    def delete(self, path: str):
        self._request("DELETE", path, None, {})

    def list_(self, endpoint: str, params: dict | None = None) -> list:
        return self.get_json(endpoint, params)

    def retrieve(self, endpoint: str, obj_id) -> dict:
        return self.get_json(f"{endpoint}{obj_id}/")

    def create(self, endpoint: str, data: dict) -> dict:
        return self.post_json(endpoint, data)

    def update(self, endpoint: str, obj_id, data: dict) -> dict:
        return self.patch_json(f"{endpoint}{obj_id}/", data)

    def remove(self, endpoint: str, obj_id):
        self.delete(f"{endpoint}{obj_id}/")

    # ==================================================================
    # request pipeline: permission check -> one database transaction
    # ==================================================================

    def _request(self, method: str, path: str, data, params):
        if self.current_user is None:
            raise APIError("Please log in first.", 401)
        parts = [p for p in path.strip("/").split("/") if p]
        if not parts:
            raise APIError("Not found.", 404)
        head = parts[0]
        is_admin = self.is_admin
        own_account = head == "users" and len(parts) > 1 and parts[1] == "me"
        mark_read = head == "notifications" and len(parts) == 3 and parts[2] == "read"

        if head in ADMIN_ONLY_HEADS and not is_admin and not own_account:
            raise APIError("Only an administrator can open this.", 403)
        if method != "GET" and not is_admin and not (own_account or mark_read):
            raise APIError("This account is read-only. Ask an administrator to make changes.", 403)

        with self._lock:
            try:
                with db.transaction() as conn:
                    self._conn = conn
                    result = self._route(method, parts, data or {}, params or {})
            except sqlite3.IntegrityError as exc:
                raise APIError(f"That change conflicts with existing records. ({exc})", 400)
            except sqlite3.Error as exc:
                raise APIError(f"Database problem: {exc}", 500)
            finally:
                self._conn = None
        if method != "GET":
            self._fire_change()
        return result

    def _route(self, method, parts, data, params):
        head = parts[0]
        n = len(parts)
        if head == "laptops":
            if n == 2 and parts[1] == "bulk-import" and method == "POST":
                return self._laptops_bulk(data)
            return self._crud(method, parts, data, params, self._laptop_list, self._laptop_get,
                              self._laptop_create, self._laptop_update, self._laptop_delete)
        if head == "customers":
            return self._crud(method, parts, data, params, self._customer_list, self._customer_get,
                              self._customer_create, self._customer_update, self._customer_delete)
        if head == "sales":
            if n == 3 and parts[1] == "receipt" and method == "GET":
                return self._sale_by_receipt(parts[2])
            return self._crud(method, parts, data, params, self._sale_list, self._sale_get,
                              self._sale_create, self._sale_update, self._sale_delete)
        if head == "shopkeepers":
            return self._crud(method, parts, data, params, self._sk_list, self._sk_get,
                              self._sk_create, self._sk_update, self._sk_delete)
        if head == "shopkeeper-laptops":
            return self._crud(method, parts, data, params, None, None,
                              self._skl_create, self._skl_update, self._skl_delete)
        if head == "shopkeeper-extra-money":
            return self._crud(method, parts, data, params, None, None,
                              self._ske_create, None, self._ske_delete)
        if head == "shopkeeper-payments":
            return self._crud(method, parts, data, params, None, None, self._skp_create, None, None)
        if head == "credit-plans":
            return self._crud(method, parts, data, params, self._plan_list, self._plan_get,
                              self._plan_create, self._plan_update, self._plan_delete)
        if head == "payments":
            return self._crud(method, parts, data, params, self._payment_list, None, self._payment_create, None, None)
        if head == "notifications":
            return self._notifications(method, parts)
        if head == "users":
            return self._users(method, parts, data)
        if head == "audit-logs" and method == "GET":
            return _rows(self._conn.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 1500"))
        if head == "store-settings":
            return self._store_settings(method, data)
        if head == "dashboard" and method == "GET":
            return Reports(self).dashboard(self.is_admin)
        if head == "reports" and method == "GET" and n == 2:
            return Reports(self).report(parts[1], params)
        raise APIError("Not found.", 404)

    def _crud(self, method, parts, data, params, f_list, f_get, f_create, f_update, f_delete):
        n = len(parts)
        try:
            if n == 1:
                if method == "GET" and f_list:
                    return f_list(params)
                if method == "POST" and f_create:
                    return f_create(data)
            elif n == 2:
                oid = int(parts[1])
                if method == "GET" and f_get:
                    return f_get(oid)
                if method in ("PATCH", "PUT") and f_update:
                    return f_update(oid, data)
                if method == "DELETE" and f_delete:
                    return f_delete(oid)
        except ValueError:
            raise APIError("Not found.", 404)
        raise APIError("That action is not allowed here.", 405)

    # ==================================================================
    # shared helpers
    # ==================================================================

    def _audit(self, action, entity, entity_id, detail=""):
        u = self.current_user
        who = f"{u['username']} ({u['role']})" if u else "system"
        self._conn.execute(
            "INSERT INTO audit_logs (timestamp, user_display, action, entity, entity_id, detail) VALUES (?,?,?,?,?,?)",
            (db.now_iso(), who, action, entity, str(entity_id), detail),
        )

    def _threshold(self) -> int:
        conn = self._conn or db.connect()
        try:
            row = conn.execute("SELECT low_stock_threshold FROM store_settings WHERE id=1").fetchone()
            return int(row[0]) if row else 2
        finally:
            if self._conn is None:
                conn.close()

    def _one(self, sql, args=(), what="Record"):
        row = self._conn.execute(sql, args).fetchone()
        if row is None:
            raise APIError(f"{what} not found.", 404)
        return row

    def _notify(self, kind, title, message, key):
        self._conn.execute(
            "INSERT OR IGNORE INTO notifications (type, title, message, created_at, dedupe_key) VALUES (?,?,?,?,?)",
            (kind, title, message, db.now_iso(), key),
        )

    @staticmethod
    def _laptop_name(row) -> str:
        return f"{row['brand']} {row['model_name']}".strip()

    # ==================================================================
    # laptops (inventory)
    # ==================================================================

    def _laptop_out(self, row) -> dict:
        d = dict(row)
        d["is_archived"] = bool(d["is_archived"])
        d["final_price"] = final_price(d["sale_price"], d["discount_amount"], d["discount_percent"])
        threshold = self._threshold()
        d["is_out_of_stock"] = d["quantity"] <= 0
        d["is_low_stock"] = 0 < d["quantity"] <= threshold
        if not self.is_admin:                      # buying cost stays private
            d.pop("purchase_price", None)
            d.pop("supplier", None)
        return d

    def _laptop_list(self, params):
        rows = self._conn.execute("SELECT * FROM laptops ORDER BY id DESC").fetchall()
        return [self._laptop_out(r) for r in rows]

    def _laptop_get(self, lid):
        return self._laptop_out(self._one("SELECT * FROM laptops WHERE id=?", (lid,), "Laptop"))

    def _check_serial(self, serial: str, exclude_id: int | None = None):
        if not serial:
            return
        row = self._conn.execute(
            "SELECT id FROM laptops WHERE serial_number = ? AND serial_number != '' AND id != ?",
            (serial, exclude_id or -1)).fetchone()
        if row:
            raise APIError(f"serial_number: A laptop with serial number {serial} already exists.", 400)

    def _laptop_create(self, d):
        f = _clean(LAPTOP_SPEC, d, True)
        if f.get("discount_percent", 0) > 100:
            raise APIError("discount_percent: Cannot be more than 100.", 400)
        self._check_serial(f.get("serial_number", ""))
        f["created_at"] = db.now_iso()
        cols = ", ".join(f)
        cur = self._conn.execute(f"INSERT INTO laptops ({cols}) VALUES ({', '.join('?' for _ in f)})", tuple(f.values()))
        self._audit("CREATE", "laptop", cur.lastrowid, f"{f['brand']} {f['model_name']}")
        return self._laptop_get(cur.lastrowid)

    def _laptop_update(self, lid, d):
        row = self._one("SELECT * FROM laptops WHERE id=?", (lid,), "Laptop")
        f = _clean(LAPTOP_SPEC, d, False)
        if f.get("discount_percent", 0) > 100:
            raise APIError("discount_percent: Cannot be more than 100.", 400)
        if "serial_number" in f:
            self._check_serial(f["serial_number"], lid)
        if f:
            sets = ", ".join(f"{k}=?" for k in f)
            self._conn.execute(f"UPDATE laptops SET {sets} WHERE id=?", (*f.values(), lid))
        self._audit("UPDATE", "laptop", lid, self._laptop_name(row))
        return self._laptop_get(lid)

    def _laptop_delete(self, lid):
        row = self._one("SELECT * FROM laptops WHERE id=?", (lid,), "Laptop")
        try:
            self._conn.execute("DELETE FROM laptops WHERE id=?", (lid,))
        except sqlite3.IntegrityError:
            raise APIError("This laptop appears in sales or shopkeeper records, so it can't be deleted. "
                           "Tick 'Archived' in Edit to hide it instead.", 400)
        self._audit("DELETE", "laptop", lid, self._laptop_name(row))

    def _laptops_bulk(self, d):
        """CSV import: every valid row becomes an inventory entry; bad rows are reported."""
        rows = d.get("rows") or []
        created, skipped, seen = 0, [], set()
        for idx, raw in enumerate(rows, start=1):
            try:
                f = _clean(LAPTOP_SPEC, raw, True)
                if f.get("discount_percent", 0) > 100:
                    raise APIError("discount_percent: Cannot be more than 100.")
                serial = f.get("serial_number", "")
                if serial and serial in seen:
                    raise APIError(f"serial_number: {serial} appears twice in this file.")
                self._check_serial(serial)
                if serial:
                    seen.add(serial)
                f.setdefault("quantity", 1)
                f["created_at"] = db.now_iso()
                self._conn.execute(
                    f"INSERT INTO laptops ({', '.join(f)}) VALUES ({', '.join('?' for _ in f)})", tuple(f.values()))
                created += 1
            except APIError as exc:
                skipped.append({"row": raw.get("_row", idx), "reason": exc.message})
        self._audit("IMPORT", "laptop", "-", f"CSV import: {created} added, {len(skipped)} skipped")
        return {"created": created, "skipped": skipped}

    # ==================================================================
    # customers
    # ==================================================================

    def _customer_list(self, params):
        return _rows(self._conn.execute("SELECT * FROM customers ORDER BY name COLLATE NOCASE"))

    def _customer_get(self, cid):
        return dict(self._one("SELECT * FROM customers WHERE id=?", (cid,), "Customer"))

    def _customer_create(self, d):
        f = _clean(CUSTOMER_SPEC, d, True)
        f["created_at"] = db.now_iso()
        cur = self._conn.execute(f"INSERT INTO customers ({', '.join(f)}) VALUES ({', '.join('?' for _ in f)})",
                                 tuple(f.values()))
        self._audit("CREATE", "customer", cur.lastrowid, f["name"])
        return self._customer_get(cur.lastrowid)

    def _customer_update(self, cid, d):
        self._one("SELECT id FROM customers WHERE id=?", (cid,), "Customer")
        f = _clean(CUSTOMER_SPEC, d, False)
        if f:
            self._conn.execute(f"UPDATE customers SET {', '.join(k + '=?' for k in f)} WHERE id=?", (*f.values(), cid))
        self._audit("UPDATE", "customer", cid, f.get("name", ""))
        return self._customer_get(cid)

    def _customer_delete(self, cid):
        row = self._one("SELECT * FROM customers WHERE id=?", (cid,), "Customer")
        try:
            self._conn.execute("DELETE FROM customers WHERE id=?", (cid,))
        except sqlite3.IntegrityError:
            raise APIError("This customer has sales or credit plans, so they can't be deleted.", 400)
        self._audit("DELETE", "customer", cid, row["name"])

    # ==================================================================
    # sales
    # ==================================================================

    def _sale_items(self, sale_ids=None) -> dict[int, list[dict]]:
        sql = ("SELECT i.*, l.brand, l.model_name, l.generation, l.processor, l.ram, l.storage, l.condition "
               "FROM sale_items i JOIN laptops l ON l.id = i.product")
        args = ()
        if sale_ids is not None:
            sql += f" WHERE i.sale IN ({', '.join('?' for _ in sale_ids)})" if sale_ids else " WHERE 0"
            args = tuple(sale_ids)
        out: dict[int, list[dict]] = {}
        for r in self._conn.execute(sql, args).fetchall():
            out.setdefault(r["sale"], []).append(dict(r))
        return out

    def _sale_out(self, row, items, customers=None) -> dict:
        d = dict(row)
        item = items[0] if items else {"quantity": 1, "sale_price": d["sale_price"], "purchase_cost_snapshot": 0}
        qty = int(item["quantity"])
        t = sale_totals(d["sale_price"], qty, d["discount_amount"], d["discount_percent"], d["amount_received"])
        d.update(t)
        d["quantity"] = qty
        cust = (customers or {}).get(d["customer"])
        if cust is None:
            r = self._conn.execute("SELECT * FROM customers WHERE id=?", (d["customer"],)).fetchone()
            cust = dict(r) if r else {}
        d["customer_name"] = cust.get("name", "")
        d["customer_phone"] = cust.get("phone", "")
        cost = float(item.get("purchase_cost_snapshot") or 0)
        full_items = []
        for it in items:
            gen = " ".join(p for p in (it.get("generation"), it.get("processor")) if p)
            entry = {
                "id": it["id"], "product": it["product"], "quantity": it["quantity"],
                "sale_price": it["sale_price"],
                "product_display": f"{it['brand']} {it['model_name']}" + (f" - {gen}" if gen else ""),
                "specs_display": ", ".join(b for b in (it.get("ram"), it.get("storage")) if b),
                "condition_display": it.get("condition", ""),
            }
            if self.is_admin:
                entry["purchase_cost_snapshot"] = it["purchase_cost_snapshot"]
                entry["profit"] = round(t["final_total"] - cost * qty, 2)
            full_items.append(entry)
        d["items"] = full_items
        return d

    def _sale_list(self, params):
        sales = self._conn.execute("SELECT * FROM sales ORDER BY id DESC").fetchall()
        items = self._sale_items()
        customers = {r["id"]: dict(r) for r in self._conn.execute("SELECT * FROM customers")}
        return [self._sale_out(s, items.get(s["id"], []), customers) for s in sales]

    def _sale_get(self, sid):
        row = self._one("SELECT * FROM sales WHERE id=?", (sid,), "Sale")
        return self._sale_out(row, self._sale_items([sid]).get(sid, []))

    def _sale_by_receipt(self, receipt):
        text = receipt.strip()
        row = self._conn.execute("SELECT id FROM sales WHERE upper(receipt_no)=upper(?)", (text,)).fetchone()
        if row is None and text.isdigit():
            row = self._conn.execute("SELECT id FROM sales WHERE receipt_no=?", (f"WML-{int(text):05d}",)).fetchone()
        if row is None:
            raise APIError(f"No sale found with receipt number {text}.", 404)
        return self._sale_get(row["id"])

    def _sale_create(self, d):
        c = self._conn
        try:
            cust_id = int(d.get("customer") or 0)
            laptop_id = int(d.get("laptop_id") or d.get("laptop") or 0)
            qty = int(d.get("quantity") or 1)
        except (TypeError, ValueError):
            raise APIError("Please choose a customer and a laptop.")
        if not c.execute("SELECT 1 FROM customers WHERE id=?", (cust_id,)).fetchone():
            raise APIError("customer: Please choose a customer.")
        lap = c.execute("SELECT * FROM laptops WHERE id=?", (laptop_id,)).fetchone()
        if lap is None:
            raise APIError("laptop_id: Please choose a laptop.")
        if lap["is_archived"]:
            raise APIError("This laptop is archived and can't be sold.")
        if qty < 1:
            raise APIError("quantity: Must be at least 1.")
        if lap["quantity"] < qty:
            raise APIError(f"Only {lap['quantity']} of {self._laptop_name(lap)} in stock.")
        f = _clean(SALE_SPEC, d, False)
        price = f.get("sale_price", lap["sale_price"])
        amount, percent = f.get("discount_amount", 0.0), f.get("discount_percent", 0.0)
        received = f.get("amount_received", 0.0)
        if percent > 100:
            raise APIError("discount_percent: Cannot be more than 100.")
        t = sale_totals(price, qty, amount, percent, received)
        if amount > round(price * qty, 2) + EPS:
            raise APIError("Discount can't be more than the sale price.")
        if received > t["final_total"] + EPS:
            raise APIError(f"Amount received (Rs. {received:,.0f}) is more than the total (Rs. {t['final_total']:,.0f}).")
        receipt = f"WML-{db.next_counter(c, 'receipt_seq'):05d}"
        cur = c.execute(
            "INSERT INTO sales (receipt_no, customer, sale_price, discount_amount, discount_percent, payment_type, "
            "amount_received, notes, sale_date) VALUES (?,?,?,?,?,?,?,?,?)",
            (receipt, cust_id, price, amount, percent, f.get("payment_type", "CASH"), received,
             f.get("notes", ""), db.now_iso()))
        sid = cur.lastrowid
        c.execute("INSERT INTO sale_items (sale, product, quantity, sale_price, purchase_cost_snapshot) VALUES (?,?,?,?,?)",
                  (sid, laptop_id, qty, price, lap["purchase_price"]))
        c.execute("UPDATE laptops SET quantity = quantity - ? WHERE id=?", (qty, laptop_id))
        self._audit("CREATE", "sale", sid, f"{receipt} - {self._laptop_name(lap)} x{qty} - Rs. {t['final_total']:,.0f}")
        self._low_stock_check(laptop_id)
        return self._sale_get(sid)

    def _sale_update(self, sid, d):
        c = self._conn
        sale = self._one("SELECT * FROM sales WHERE id=?", (sid,), "Sale")
        item = self._one("SELECT * FROM sale_items WHERE sale=?", (sid,), "Sale item")
        lap = self._one("SELECT * FROM laptops WHERE id=?", (item["product"],), "Laptop")
        f = _clean(SALE_SPEC, d, False)
        try:
            new_qty = int(d["quantity"]) if "quantity" in d else int(item["quantity"])
        except (TypeError, ValueError):
            raise APIError("quantity: A whole number is required.")
        if new_qty < 1:
            raise APIError("quantity: Must be at least 1.")
        delta = new_qty - int(item["quantity"])
        if delta > 0 and lap["quantity"] < delta:
            raise APIError(f"Only {lap['quantity']} more of {self._laptop_name(lap)} in stock.")
        price = f.get("sale_price", sale["sale_price"])
        amount = f.get("discount_amount", sale["discount_amount"])
        percent = f.get("discount_percent", sale["discount_percent"])
        received = f.get("amount_received", sale["amount_received"])
        t = sale_totals(price, new_qty, amount, percent, received)
        if received > t["final_total"] + EPS:
            raise APIError(f"Amount received (Rs. {received:,.0f}) is more than the total (Rs. {t['final_total']:,.0f}).")
        f.update({"sale_price": price, "discount_amount": amount, "discount_percent": percent,
                  "amount_received": received})
        c.execute(f"UPDATE sales SET {', '.join(k + '=?' for k in f)} WHERE id=?", (*f.values(), sid))
        c.execute("UPDATE sale_items SET quantity=?, sale_price=? WHERE id=?", (new_qty, price, item["id"]))
        if delta:
            c.execute("UPDATE laptops SET quantity = quantity - ? WHERE id=?", (delta, item["product"]))
            self._low_stock_check(item["product"])
        self._audit("UPDATE", "sale", sid, sale["receipt_no"])
        return self._sale_get(sid)

    def _sale_delete(self, sid):
        sale = self._one("SELECT * FROM sales WHERE id=?", (sid,), "Sale")
        for it in self._conn.execute("SELECT * FROM sale_items WHERE sale=?", (sid,)).fetchall():
            self._conn.execute("UPDATE laptops SET quantity = quantity + ? WHERE id=?", (it["quantity"], it["product"]))
        self._conn.execute("DELETE FROM sales WHERE id=?", (sid,))
        self._audit("DELETE", "sale", sid, f"{sale['receipt_no']} (stock restored)")

    def _low_stock_check(self, laptop_id):
        st = self._conn.execute("SELECT * FROM store_settings WHERE id=1").fetchone()
        lap = self._conn.execute("SELECT * FROM laptops WHERE id=?", (laptop_id,)).fetchone()
        if not st or not lap or not st["low_stock_alerts_enabled"] or lap["is_archived"]:
            return
        if lap["quantity"] <= st["low_stock_threshold"]:
            state = "Out of stock" if lap["quantity"] <= 0 else f"Only {lap['quantity']} left"
            self._notify("LOW_STOCK", f"Low stock: {self._laptop_name(lap)}", state,
                         f"low:{laptop_id}:{lap['quantity']}")

    # ==================================================================
    # shopkeepers (accounts, laptops given on credit, extra money, payments)
    # ==================================================================

    def _sk_totals(self) -> dict[int, tuple[float, float]]:
        c = self._conn
        total: dict[int, float] = {}
        for r in c.execute("SELECT shopkeeper, SUM(price) s FROM shopkeeper_laptops GROUP BY shopkeeper"):
            total[r["shopkeeper"]] = total.get(r["shopkeeper"], 0) + (r["s"] or 0)
        for r in c.execute("SELECT shopkeeper, SUM(amount) s FROM shopkeeper_extra_money GROUP BY shopkeeper"):
            total[r["shopkeeper"]] = total.get(r["shopkeeper"], 0) + (r["s"] or 0)
        paid = {r["shopkeeper"]: r["s"] or 0 for r in
                c.execute("SELECT shopkeeper, SUM(amount) s FROM shopkeeper_payments GROUP BY shopkeeper")}
        return {sid: (total.get(sid, 0.0), paid.get(sid, 0.0)) for sid in set(total) | set(paid)}

    @staticmethod
    def _sk_status(total, remaining) -> str:
        if total <= EPS:
            return "NO_ITEMS"
        return "CLEARED" if remaining <= EPS else "PENDING"

    def _sk_base(self, row, totals) -> dict:
        d = dict(row)
        total, received = totals.get(row["id"], (0.0, 0.0))
        d["total_amount"] = round(total, 2)
        d["total_received"] = round(received, 2)
        d["remaining_amount"] = round(max(total - received, 0.0), 2)
        d["status"] = self._sk_status(total, total - received)
        return d

    def _sk_list(self, params):
        totals = self._sk_totals()
        rows = self._conn.execute("SELECT * FROM shopkeepers ORDER BY id DESC").fetchall()
        return [self._sk_base(r, totals) for r in rows]

    def _sk_get(self, sid):
        row = self._one("SELECT * FROM shopkeepers WHERE id=?", (sid,), "Shopkeeper")
        d = self._sk_base(row, self._sk_totals())
        c = self._conn
        laptops = []
        for r in c.execute(
                "SELECT l.*, COALESCE((SELECT SUM(amount) FROM shopkeeper_payments p WHERE p.laptop_item = l.id),0) paid "
                "FROM shopkeeper_laptops l WHERE l.shopkeeper=? ORDER BY l.seq", (sid,)):
            e = dict(r)
            e["remaining_amount"] = round(max(e["price"] - e.pop("paid"), 0.0), 2)
            e["is_cleared"] = e["remaining_amount"] <= EPS
            laptops.append(e)
        extras = []
        for r in c.execute(
                "SELECT m.*, COALESCE((SELECT SUM(amount) FROM shopkeeper_payments p WHERE p.extra_money = m.id),0) paid "
                "FROM shopkeeper_extra_money m WHERE m.shopkeeper=? ORDER BY m.seq", (sid,)):
            e = dict(r)
            e["remaining_amount"] = round(max(e["amount"] - e.pop("paid"), 0.0), 2)
            e["is_cleared"] = e["remaining_amount"] <= EPS
            extras.append(e)
        d["laptops"], d["extra_money"] = laptops, extras
        d["payments"] = _rows(c.execute(
            "SELECT * FROM shopkeeper_payments WHERE shopkeeper=? ORDER BY payment_date DESC, id DESC", (sid,)))
        return d

    def _sk_create(self, d):
        f = _clean(SHOPKEEPER_SPEC, d, True)
        n = db.next_counter(self._conn, "shopkeeper_seq")
        f["reference_number"] = f"SK-{n:04d}"
        f["created_at"] = db.now_iso()
        cur = self._conn.execute(f"INSERT INTO shopkeepers ({', '.join(f)}) VALUES ({', '.join('?' for _ in f)})",
                                 tuple(f.values()))
        self._audit("CREATE", "shopkeeper", cur.lastrowid, f"{f['name']} ({f['reference_number']})")
        return self._sk_get(cur.lastrowid)

    def _sk_update(self, sid, d):
        self._one("SELECT id FROM shopkeepers WHERE id=?", (sid,), "Shopkeeper")
        f = _clean(SHOPKEEPER_SPEC, d, False)
        if f:
            self._conn.execute(f"UPDATE shopkeepers SET {', '.join(k + '=?' for k in f)} WHERE id=?", (*f.values(), sid))
        self._audit("UPDATE", "shopkeeper", sid, f.get("name", ""))
        return self._sk_get(sid)

    def _sk_delete(self, sid):
        row = self._one("SELECT * FROM shopkeepers WHERE id=?", (sid,), "Shopkeeper")
        for it in self._conn.execute("SELECT * FROM shopkeeper_laptops WHERE shopkeeper=?", (sid,)).fetchall():
            self._conn.execute("UPDATE laptops SET quantity = quantity + 1 WHERE id=?", (it["inventory_laptop"],))
        self._conn.execute("DELETE FROM shopkeepers WHERE id=?", (sid,))
        self._audit("DELETE", "shopkeeper", sid, f"{row['name']} (laptops returned to stock)")

    def _sk_owner(self, sid) -> sqlite3.Row:
        return self._one("SELECT * FROM shopkeepers WHERE id=?", (sid,), "Shopkeeper")

    def _skl_create(self, d):
        try:
            sid, lid = int(d.get("shopkeeper")), int(d.get("inventory_laptop"))
        except (TypeError, ValueError):
            raise APIError("Please choose a laptop.")
        sk = self._sk_owner(sid)
        lap = self._one("SELECT * FROM laptops WHERE id=?", (lid,), "Laptop")
        price = _clean({"price": ("float", True)}, d, True)["price"]
        if lap["is_archived"] or lap["quantity"] < 1:
            raise APIError(f"{self._laptop_name(lap)} is not in stock.")
        seq = (self._conn.execute("SELECT COALESCE(MAX(seq),0) FROM shopkeeper_laptops WHERE shopkeeper=?", (sid,))
               .fetchone()[0]) + 1
        gen = " ".join(p for p in (lap["generation"], lap["processor"]) if p)
        cur = self._conn.execute(
            "INSERT INTO shopkeeper_laptops (shopkeeper, inventory_laptop, brand, model_name, core_generation, price, "
            "seq, item_reference, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (sid, lid, lap["brand"], lap["model_name"], gen, price, seq, f"{sk['reference_number']}-L{seq}", db.now_iso()))
        self._conn.execute("UPDATE laptops SET quantity = quantity - 1 WHERE id=?", (lid,))
        self._audit("CREATE", "shopkeeper-laptop", cur.lastrowid, f"{sk['name']}: {self._laptop_name(lap)} @ Rs. {price:,.0f}")
        self._low_stock_check(lid)
        return dict(self._one("SELECT * FROM shopkeeper_laptops WHERE id=?", (cur.lastrowid,)))

    def _skl_update(self, iid, d):
        item = self._one("SELECT * FROM shopkeeper_laptops WHERE id=?", (iid,), "Laptop item")
        price = _clean({"price": ("float", True)}, d, True)["price"]
        paid = self._conn.execute("SELECT COALESCE(SUM(amount),0) FROM shopkeeper_payments WHERE laptop_item=?",
                                  (iid,)).fetchone()[0]
        if price < paid - EPS:
            raise APIError(f"price: Can't be lower than the Rs. {paid:,.0f} already paid for this laptop.")
        self._conn.execute("UPDATE shopkeeper_laptops SET price=? WHERE id=?", (price, iid))
        self._audit("UPDATE", "shopkeeper-laptop", iid, f"{item['item_reference']} price Rs. {price:,.0f}")
        return dict(self._one("SELECT * FROM shopkeeper_laptops WHERE id=?", (iid,)))

    def _skl_delete(self, iid):
        item = self._one("SELECT * FROM shopkeeper_laptops WHERE id=?", (iid,), "Laptop item")
        self._conn.execute("UPDATE laptops SET quantity = quantity + 1 WHERE id=?", (item["inventory_laptop"],))
        self._conn.execute("DELETE FROM shopkeeper_laptops WHERE id=?", (iid,))
        self._audit("DELETE", "shopkeeper-laptop", iid, f"{item['item_reference']} (returned to stock)")

    def _ske_create(self, d):
        try:
            sid = int(d.get("shopkeeper"))
        except (TypeError, ValueError):
            raise APIError("Shopkeeper is missing.")
        sk = self._sk_owner(sid)
        f = _clean({"amount": ("float", True), "note": ("str", False)}, d, True)
        if f["amount"] <= 0:
            raise APIError("amount: Must be more than 0.")
        seq = (self._conn.execute("SELECT COALESCE(MAX(seq),0) FROM shopkeeper_extra_money WHERE shopkeeper=?", (sid,))
               .fetchone()[0]) + 1
        cur = self._conn.execute(
            "INSERT INTO shopkeeper_extra_money (shopkeeper, amount, note, seq, item_reference, created_at) VALUES (?,?,?,?,?,?)",
            (sid, f["amount"], f.get("note", ""), seq, f"{sk['reference_number']}-E{seq}", db.now_iso()))
        self._audit("CREATE", "shopkeeper-extra-money", cur.lastrowid, f"{sk['name']}: Rs. {f['amount']:,.0f}")
        return dict(self._one("SELECT * FROM shopkeeper_extra_money WHERE id=?", (cur.lastrowid,)))

    def _ske_delete(self, mid):
        row = self._one("SELECT * FROM shopkeeper_extra_money WHERE id=?", (mid,), "Extra money entry")
        self._conn.execute("DELETE FROM shopkeeper_extra_money WHERE id=?", (mid,))
        self._audit("DELETE", "shopkeeper-extra-money", mid, row["item_reference"])

    def _skp_create(self, d):
        try:
            sid = int(d.get("shopkeeper"))
        except (TypeError, ValueError):
            raise APIError("Shopkeeper is missing.")
        sk = self._sk_owner(sid)
        f = _clean({"amount": ("float", True), "method": (f"choice:{'|'.join(METHODS)}", False),
                    "note": ("str", False)}, d, True)
        if f["amount"] <= 0:
            raise APIError("amount: Must be more than 0.")
        lap_id, extra_id = d.get("laptop_item"), d.get("extra_money")
        if bool(lap_id) == bool(extra_id):
            raise APIError("Choose exactly one laptop or extra-money entry to clear.")
        if lap_id:
            target = self._one("SELECT * FROM shopkeeper_laptops WHERE id=? AND shopkeeper=?", (lap_id, sid), "Laptop item")
            total = target["price"]
            paid = self._conn.execute("SELECT COALESCE(SUM(amount),0) FROM shopkeeper_payments WHERE laptop_item=?",
                                      (lap_id,)).fetchone()[0]
        else:
            target = self._one("SELECT * FROM shopkeeper_extra_money WHERE id=? AND shopkeeper=?", (extra_id, sid),
                               "Extra money entry")
            total = target["amount"]
            paid = self._conn.execute("SELECT COALESCE(SUM(amount),0) FROM shopkeeper_payments WHERE extra_money=?",
                                      (extra_id,)).fetchone()[0]
        remaining = round(total - paid, 2)
        if f["amount"] > remaining + EPS:
            raise APIError(f"amount: Rs. {f['amount']:,.0f} is more than the Rs. {remaining:,.0f} still due on "
                           f"{target['item_reference']}.")
        cur = self._conn.execute(
            "INSERT INTO shopkeeper_payments (shopkeeper, laptop_item, extra_money, amount, method, note, payment_date) "
            "VALUES (?,?,?,?,?,?,?)",
            (sid, lap_id or None, extra_id or None, f["amount"], f.get("method", "CASH"), f.get("note", ""), db.now_iso()))
        self._audit("CREATE", "shopkeeper-payment", cur.lastrowid,
                    f"{sk['name']} paid Rs. {f['amount']:,.0f} on {target['item_reference']}")
        return dict(self._one("SELECT * FROM shopkeeper_payments WHERE id=?", (cur.lastrowid,)))

    # ==================================================================
    # credit plans (customer instalments)
    # ==================================================================

    def _plan_out(self, row, paid_map) -> dict:
        d = dict(row)
        cust = self._conn.execute("SELECT name FROM customers WHERE id=?", (d["customer"],)).fetchone()
        lap = (self._conn.execute("SELECT brand, model_name FROM laptops WHERE id=?", (d["laptop"],)).fetchone()
               if d["laptop"] else None)
        d["customer_name"] = cust["name"] if cust else ""
        d["person_name"] = d["customer_name"]
        d["laptop_name"] = f"{lap['brand']} {lap['model_name']}" if lap else ""
        received = round(d["down_payment"] + paid_map.get(d["id"], 0.0), 2)
        d["total_received"] = received
        d["remaining_amount"] = round(max(d["total_amount"] - received, 0.0), 2)
        cleared = d["remaining_amount"] <= EPS
        d["status"] = "CLEARED" if cleared else "ACTIVE"
        d["is_overdue"] = bool(not cleared and d["due_date"] and d["due_date"] < date.today().isoformat())
        return d

    def _paid_map(self) -> dict[int, float]:
        return {r["credit_plan"]: r["s"] or 0.0 for r in
                self._conn.execute("SELECT credit_plan, SUM(amount) s FROM payments GROUP BY credit_plan")}

    def _plan_list(self, params):
        paid = self._paid_map()
        rows = self._conn.execute("SELECT * FROM credit_plans ORDER BY id DESC").fetchall()
        return [self._plan_out(r, paid) for r in rows]

    def _plan_get(self, pid):
        row = self._one("SELECT * FROM credit_plans WHERE id=?", (pid,), "Credit plan")
        return self._plan_out(row, self._paid_map())

    def _plan_common(self, d, creating):
        f = _clean(CREDIT_SPEC, d, creating)
        for key in ("customer", "laptop"):
            if key in d:
                f[key] = int(d[key]) if d[key] not in (None, "", 0) else None
        if creating and not f.get("customer"):
            raise APIError("customer: Please choose a customer.")
        if f.get("customer") and not self._conn.execute("SELECT 1 FROM customers WHERE id=?", (f["customer"],)).fetchone():
            raise APIError("customer: Customer not found.")
        return f

    def _plan_create(self, d):
        f = self._plan_common(d, True)
        if f["total_amount"] <= 0:
            raise APIError("total_amount: Must be more than 0.")
        if f.get("down_payment", 0) > f["total_amount"] + EPS:
            raise APIError("down_payment: Can't be more than the total amount.")
        f["created_at"] = db.now_iso()
        cur = self._conn.execute(f"INSERT INTO credit_plans ({', '.join(f)}) VALUES ({', '.join('?' for _ in f)})",
                                 tuple(f.values()))
        plan = self._plan_get(cur.lastrowid)
        self._audit("CREATE", "credit-plan", cur.lastrowid, f"{plan['person_name']} - Rs. {plan['total_amount']:,.0f}")
        return plan

    def _plan_update(self, pid, d):
        old = self._plan_get(pid)
        f = self._plan_common(d, False)
        total = f.get("total_amount", old["total_amount"])
        down = f.get("down_payment", old["down_payment"])
        paid = old["total_received"] - old["down_payment"]
        if down + paid > total + EPS:
            raise APIError("Total amount can't be less than what has already been received.")
        if f:
            self._conn.execute(f"UPDATE credit_plans SET {', '.join(k + '=?' for k in f)} WHERE id=?", (*f.values(), pid))
        self._audit("UPDATE", "credit-plan", pid, old["person_name"])
        return self._plan_get(pid)

    def _plan_delete(self, pid):
        plan = self._plan_get(pid)
        n = self._conn.execute("SELECT COUNT(*) FROM payments WHERE credit_plan=?", (pid,)).fetchone()[0]
        self._conn.execute("DELETE FROM credit_plans WHERE id=?", (pid,))
        self._audit("DELETE", "credit-plan", pid, f"{plan['person_name']} (with {n} payment(s))")

    def _payment_list(self, params):
        sql, args = "SELECT * FROM payments", ()
        if params.get("credit_plan"):
            sql, args = sql + " WHERE credit_plan=?", (int(params["credit_plan"]),)
        return _rows(self._conn.execute(sql + " ORDER BY payment_date DESC, id DESC", args))

    def _payment_create(self, d):
        try:
            pid = int(d.get("credit_plan"))
        except (TypeError, ValueError):
            raise APIError("credit_plan: Choose a credit plan.")
        plan = self._plan_get(pid)
        f = _clean({"amount": ("float", True), "method": (f"choice:{'|'.join(METHODS)}", False),
                    "note": ("str", False)}, d, True)
        if f["amount"] <= 0:
            raise APIError("amount: Must be more than 0.")
        if f["amount"] > plan["remaining_amount"] + EPS:
            raise APIError(f"amount: Rs. {f['amount']:,.0f} is more than the Rs. {plan['remaining_amount']:,.0f} still due.")
        cur = self._conn.execute(
            "INSERT INTO payments (credit_plan, amount, method, note, payment_date) VALUES (?,?,?,?,?)",
            (pid, f["amount"], f.get("method", "CASH"), f.get("note", ""), db.now_iso()))
        self._audit("CREATE", "payment", cur.lastrowid, f"{plan['person_name']} paid Rs. {f['amount']:,.0f}")
        return dict(self._one("SELECT * FROM payments WHERE id=?", (cur.lastrowid,)))

    # ==================================================================
    # notifications, users, store settings
    # ==================================================================

    def _notifications(self, method, parts):
        if len(parts) == 1 and method == "GET":
            return _rows(self._conn.execute("SELECT * FROM notifications ORDER BY id DESC LIMIT 500"))
        if len(parts) == 2 and parts[1] == "unread-count" and method == "GET":
            return {"count": self._conn.execute("SELECT COUNT(*) FROM notifications WHERE read_at IS NULL").fetchone()[0]}
        if len(parts) == 3 and parts[2] == "read" and method == "POST":
            self._conn.execute("UPDATE notifications SET read_at=? WHERE id=? AND read_at IS NULL",
                               (db.now_iso(), int(parts[1])))
            return {"ok": True}
        raise APIError("Not found.", 404)

    def _run_reminders(self):
        c = self._conn
        st = c.execute("SELECT * FROM store_settings WHERE id=1").fetchone()
        if st is None:
            return
        if st["low_stock_alerts_enabled"]:
            for lap in c.execute("SELECT * FROM laptops WHERE is_archived=0 AND quantity <= ?",
                                 (st["low_stock_threshold"],)).fetchall():
                state = "Out of stock" if lap["quantity"] <= 0 else f"Only {lap['quantity']} left"
                self._notify("LOW_STOCK", f"Low stock: {self._laptop_name(lap)}", state, f"low:{lap['id']}:{lap['quantity']}")
        today = date.today()
        for plan in self._plan_list({}):
            if plan["status"] == "CLEARED" or not plan["due_date"]:
                continue
            due = date.fromisoformat(plan["due_date"])
            who, left = plan["person_name"], f"Rs. {plan['remaining_amount']:,.0f}"
            if due == today and st["due_today_reminder_enabled"]:
                self._notify("DUE_TODAY", f"Payment due today: {who}", f"{left} is due today.", f"due0:{plan['id']}:{due}")
            elif due - today == timedelta(days=2) and st["two_day_reminder_enabled"]:
                self._notify("DUE_SOON", f"Payment due in 2 days: {who}", f"{left} is due on {due:%d %b %Y}.",
                             f"due2:{plan['id']}:{due}")
            elif due < today:
                self._notify("OVERDUE", f"Overdue: {who}", f"{left} was due on {due:%d %b %Y}.", f"over:{plan['id']}:{due}")

    def _user_out(self, conn, row) -> dict:
        d = {k: row[k] for k in ("id", "username", "email", "first_name", "last_name", "role", "phone_number", "shopkeeper")}
        d["is_active"] = bool(row["is_active"])
        sk = conn.execute("SELECT name FROM shopkeepers WHERE id=?", (row["shopkeeper"],)).fetchone() if row["shopkeeper"] else None
        d["shopkeeper_name"] = sk["name"] if sk else ""
        return d

    def _active_admins(self, excluding: int | None = None) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM users WHERE role='ADMIN' AND is_active=1 AND id != ?", (excluding or -1,)).fetchone()[0]

    def _users(self, method, parts, data):
        c = self._conn
        if len(parts) == 3 and parts[1] == "me" and parts[2] == "change-password" and method == "POST":
            row = self._one("SELECT * FROM users WHERE id=?", (self.current_user["id"],), "User")
            if not db.verify_password(str(data.get("current_password", "")), row["password_hash"]):
                raise APIError("current_password: That is not your current password.", 400)
            self._check_password_strength(str(data.get("new_password", "")))
            c.execute("UPDATE users SET password_hash=? WHERE id=?", (db.hash_password(data["new_password"]), row["id"]))
            self._audit("UPDATE", "user", row["id"], "changed own password")
            return {"ok": True}
        if len(parts) == 1 and method == "GET":
            return [self._user_out(c, r) for r in c.execute("SELECT * FROM users ORDER BY username COLLATE NOCASE")]
        if len(parts) == 1 and method == "POST":
            return self._user_create(data)
        try:
            uid = int(parts[1])
        except (ValueError, IndexError):
            raise APIError("Not found.", 404)
        row = self._one("SELECT * FROM users WHERE id=?", (uid,), "User")
        if len(parts) == 2 and method == "GET":
            return self._user_out(c, row)
        if len(parts) == 2 and method in ("PATCH", "PUT"):
            return self._user_update(row, data)
        if len(parts) == 3 and method == "POST":
            action = parts[2]
            if action == "activate":
                c.execute("UPDATE users SET is_active=1 WHERE id=?", (uid,))
            elif action == "deactivate":
                self._guard_last_admin(row, deactivating=True)
                c.execute("UPDATE users SET is_active=0 WHERE id=?", (uid,))
            elif action == "set-password":
                self._check_password_strength(str(data.get("password", "")))
                c.execute("UPDATE users SET password_hash=? WHERE id=?", (db.hash_password(data["password"]), uid))
            else:
                raise APIError("Not found.", 404)
            self._audit("UPDATE", "user", uid, f"{row['username']}: {action}")
            return self._user_out(c, self._one("SELECT * FROM users WHERE id=?", (uid,)))
        raise APIError("That action is not allowed here.", 405)

    def _guard_last_admin(self, row, deactivating=False, new_role=None):
        losing = (deactivating or (new_role and new_role != "ADMIN")) and row["role"] == "ADMIN" and row["is_active"]
        if losing and self._active_admins(excluding=row["id"]) == 0:
            raise APIError("There must always be at least one active administrator.", 400)
        if deactivating and row["id"] == self.current_user["id"]:
            raise APIError("You can't deactivate the account you are using.", 400)

    def _user_fields(self, data, creating):
        spec = {"username": ("str", True), "email": ("str", False), "first_name": ("str", False),
                "last_name": ("str", False), "role": (f"choice:{'|'.join(ROLES)}", True),
                "phone_number": ("str", False)}
        f = _clean(spec, data, creating)
        if "shopkeeper" in data:
            f["shopkeeper"] = int(data["shopkeeper"]) if data["shopkeeper"] not in (None, "", 0) else None
        if f.get("role") == "SHOPKEEPER" and creating and not f.get("shopkeeper"):
            raise APIError("shopkeeper: Choose which shopkeeper this login belongs to.")
        return f

    def _user_create(self, data):
        f = self._user_fields(data, True)
        password = str(data.get("password", ""))
        self._check_password_strength(password)
        f["password_hash"] = db.hash_password(password)
        f["created_at"] = db.now_iso()
        cur = self._conn.execute(f"INSERT INTO users ({', '.join(f)}) VALUES ({', '.join('?' for _ in f)})", tuple(f.values()))
        self._audit("CREATE", "user", cur.lastrowid, f"{f['username']} ({f['role']})")
        return self._user_out(self._conn, self._one("SELECT * FROM users WHERE id=?", (cur.lastrowid,)))

    def _user_update(self, row, data):
        f = self._user_fields(data, False)
        if "role" in f:
            self._guard_last_admin(row, new_role=f["role"])
        if f:
            self._conn.execute(f"UPDATE users SET {', '.join(k + '=?' for k in f)} WHERE id=?", (*f.values(), row["id"]))
        self._audit("UPDATE", "user", row["id"], row["username"])
        return self._user_out(self._conn, self._one("SELECT * FROM users WHERE id=?", (row["id"],)))

    def _store_settings(self, method, data):
        c = self._conn
        if method == "GET":
            r = dict(c.execute("SELECT * FROM store_settings WHERE id=1").fetchone())
        else:
            f = _clean(STORE_SPEC, data, False)
            if f:
                c.execute(f"UPDATE store_settings SET {', '.join(k + '=?' for k in f)} WHERE id=1", tuple(f.values()))
            self._audit("UPDATE", "store-settings", 1, "Store profile saved")
            r = dict(c.execute("SELECT * FROM store_settings WHERE id=1").fetchone())
        for k in ("low_stock_alerts_enabled", "due_today_reminder_enabled", "two_day_reminder_enabled"):
            r[k] = bool(r[k])
        return r


# One shared instance for the whole app.
client = LocalClient()
