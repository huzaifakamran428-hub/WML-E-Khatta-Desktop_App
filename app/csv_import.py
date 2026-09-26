"""
Bulk-add laptops to Inventory from a CSV file (e.g. saved from Excel).

The first row must be column headings. Headings are matched loosely --
"Model", "model name", "MODEL_NAME" all work -- and columns we don't know are
simply ignored. Only Brand and Model are required for a row to be imported.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

from dateutil import parser as date_parser

# canonical field -> accepted headings (already lower-case, letters+digits only)
ALIASES = {
    "brand": ["brand", "make", "manufacturer", "company"],
    "model_name": ["model", "modelname", "modelno", "laptop", "name", "product"],
    "generation": ["generation", "gen", "coregeneration"],
    "processor": ["processor", "cpu", "processortype", "corei"],
    "cpu_cores": ["cpucores", "cores", "corecount", "nocores"],
    "ram": ["ram", "memory", "ramsize"],
    "storage": ["storage", "hdd", "ssd", "disk", "harddisk", "harddrive", "storagesize", "rom"],
    "gpu": ["gpu", "graphics", "graphiccard", "graphicscard", "videocard"],
    "screen_size": ["screensize", "screen", "display", "displaysize", "size"],
    "condition": ["condition", "state", "type", "status"],
    "serial_number": ["serialnumber", "serial", "serialno", "sn", "serialnum", "imei"],
    "purchase_price": ["purchaseprice", "purchase", "cost", "costprice", "buyingprice", "buyprice", "purchasecost"],
    "sale_price": ["saleprice", "price", "sellingprice", "sellprice", "retailprice", "sale", "mrp"],
    "discount_amount": ["discountamount", "discount", "discountrs"],
    "discount_percent": ["discountpercent", "discountpercentage", "discountpct"],
    "quantity": ["quantity", "qty", "stock", "units", "count", "instock"],
    "supplier": ["supplier", "vendor", "boughtfrom", "purchasedfrom"],
    "purchase_date": ["purchasedate", "dateofpurchase", "boughton", "date"],
    "warranty": ["warranty", "warrantyperiod"],
    "notes": ["notes", "note", "remarks", "comments", "description"],
}
_LOOKUP = {alias: field for field, names in ALIASES.items() for alias in names}

TEMPLATE_HEADERS = ["brand", "model_name", "generation", "processor", "cpu_cores", "ram", "storage", "gpu",
                    "screen_size", "condition", "serial_number", "purchase_price", "sale_price", "quantity",
                    "supplier", "purchase_date", "warranty", "notes"]
TEMPLATE_ROWS = [
    ["Dell", "Latitude 7490", "8th Gen", "Core i5-8350U", "4", "8 GB", "256 GB SSD", "Intel UHD 620", '14"',
     "USED", "SN-D7490-001", "38000", "48500", "3", "Karachi Traders", "2026-08-15", "3 months", "Backlit keyboard"],
    ["HP", "EliteBook 840 G5", "8th Gen", "Core i7-8650U", "4", "16 GB", "512 GB SSD", "Intel UHD 620", '14"',
     "REFURBISHED", "SN-HP840-002", "52000", "64000", "1", "Lahore Imports", "2026-09-02", "6 months", ""],
]


@dataclass
class ImportPreview:
    rows: list[dict] = field(default_factory=list)          # ready to send to the backend
    skipped: list[dict] = field(default_factory=list)       # {"row": n, "reason": str}
    ignored_headers: list[str] = field(default_factory=list)
    found_headers: list[str] = field(default_factory=list)
    total: int = 0
    no_price: int = 0


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _number(text: str) -> float | None:
    cleaned = re.sub(r"(?i)\b(rs\.?|pkr|rupees?)\b", "", text or "")
    cleaned = cleaned.replace(",", "").replace(" ", "")
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    return float(match.group()) if match else None


def _condition(text: str) -> str:
    low = (text or "").strip().lower()
    if low.startswith("refurb") or "renew" in low:
        return "REFURBISHED"
    if low.startswith(("used", "second", "old", "pre")):
        return "USED"
    return "NEW"


def read_csv(path: str | Path) -> ImportPreview:
    text = _decode(Path(path).read_bytes())
    if not text.strip():
        raise ValueError("That file is empty.")
    # Normalize line endings first -- files saved with old Mac-style "\r"
    # only (or a stray "\r" inside a cell) otherwise trip up csv.reader
    # with "new-line character seen in unquoted field".
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    try:
        header = next(reader)
    except StopIteration:
        raise ValueError("That file is empty.")
    except csv.Error:
        raise ValueError(
            "That file doesn't look like a valid CSV. Make sure any text with "
            "commas or line breaks in it (e.g. in Notes) is wrapped in quotes, "
            "then try again."
        )

    mapping: dict[int, str] = {}
    preview = ImportPreview()
    for idx, heading in enumerate(header):
        field_name = _LOOKUP.get(_norm(heading))
        if field_name and field_name not in mapping.values():
            mapping[idx] = field_name
            preview.found_headers.append(f"{heading.strip()} -> {field_name}")
        elif heading.strip():
            preview.ignored_headers.append(heading.strip())
    if "brand" not in mapping.values() or "model_name" not in mapping.values():
        raise ValueError("The file needs at least two columns: Brand and Model. "
                         "Use 'Download CSV template' to see the layout.")

    try:
        rows_iter = list(enumerate(reader, start=2))
    except csv.Error:
        raise ValueError(
            "That file doesn't look like a valid CSV. Make sure any text with "
            "commas or line breaks in it (e.g. in Notes) is wrapped in quotes, "
            "then try again."
        )
    for line_no, cells in rows_iter:
        if not any(c.strip() for c in cells):
            continue                       # blank line
        preview.total += 1
        row: dict = {"_row": line_no}
        for idx, field_name in mapping.items():
            raw = cells[idx].strip() if idx < len(cells) else ""
            if raw == "":
                continue
            if field_name in ("purchase_price", "sale_price", "discount_amount", "discount_percent"):
                value = _number(raw)
                if value is not None:
                    row[field_name] = max(value, 0)
            elif field_name in ("quantity", "cpu_cores"):
                value = _number(raw)
                if value is not None:
                    row[field_name] = max(int(value), 0)
            elif field_name == "condition":
                row[field_name] = _condition(raw)
            elif field_name == "purchase_date":
                try:
                    row[field_name] = date_parser.parse(raw, dayfirst=True).date().isoformat()
                except (ValueError, OverflowError):
                    pass
            else:
                row[field_name] = raw
        if not row.get("brand"):
            preview.skipped.append({"row": line_no, "reason": "Brand is empty"})
            continue
        if not row.get("model_name"):
            preview.skipped.append({"row": line_no, "reason": "Model is empty"})
            continue
        row.setdefault("quantity", 1)
        row.setdefault("condition", "NEW")
        if not row.get("sale_price"):
            preview.no_price += 1
        preview.rows.append(row)
    if preview.total == 0:
        raise ValueError("The file has headings but no laptops in it.")
    return preview


def write_template(path: str | Path) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:      # BOM so Excel shows symbols correctly
        writer = csv.writer(fh)
        writer.writerow(TEMPLATE_HEADERS)
        writer.writerows(TEMPLATE_ROWS)
