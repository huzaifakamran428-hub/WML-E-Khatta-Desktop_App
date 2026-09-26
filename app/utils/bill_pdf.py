"""
A6 sale bill -- small, printable receipt (~105 x 148 mm).

Kept intentionally simple to print cleanly on an A6 sheet or a small receipt
printer: one laptop per bill, a clear total, and the shop's own details.
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A6
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app import config
from app.utils.formatting import format_currency, format_date

_LOGO_CACHE: ImageReader | None = None
_LOGO_TRIED = False


def _logo() -> ImageReader | None:
    """The shop logo, loaded once and reused for every bill."""
    global _LOGO_CACHE, _LOGO_TRIED
    if not _LOGO_TRIED:
        _LOGO_TRIED = True
        try:
            _LOGO_CACHE = ImageReader(config.asset_path("waqare_medina_logo.png"))
        except OSError:
            _LOGO_CACHE = None
    return _LOGO_CACHE

GREEN = (0x0b / 255, 0x7a / 255, 0x45 / 255)
GREEN_DARK = (0x0a / 255, 0x50 / 255, 0x30 / 255)
INK = (0x18 / 255, 0x24 / 255, 0x1e / 255)
MUTED = (0x6b / 255, 0x7c / 255, 0x74 / 255)
LINE = (0xdc / 255, 0xe6 / 255, 0xe0 / 255)
SOFT = (0xea / 255, 0xf6 / 255, 0xef / 255)

W, H = A6            # 297.6 x 419.5 pt portrait
MARGIN = 12 * mm


def _wrap(c: canvas.Canvas, text: str, x: float, y: float, max_width: float, font: str, size: float,
         color, leading: float | None = None) -> float:
    """Draw wrapped text; return the y position after the last line."""
    leading = leading or size * 1.28
    c.setFont(font, size)
    c.setFillColorRGB(*color)
    words = (text or "").split()
    line = ""
    for word in words:
        trial = f"{line} {word}".strip()
        if c.stringWidth(trial, font, size) > max_width and line:
            c.drawString(x, y, line)
            y -= leading
            line = word
        else:
            line = trial
    if line:
        c.drawString(x, y, line)
        y -= leading
    return y


def generate_bill(sale: dict, store: dict, out_path: str | Path) -> Path:
    out_path = Path(out_path)
    c = canvas.Canvas(str(out_path), pagesize=A6)
    x0, x1 = MARGIN, W - MARGIN
    width = x1 - x0
    y = H - MARGIN

    # ---- header band ----
    band_h = 30 * mm
    c.setFillColorRGB(*GREEN_DARK)
    c.rect(0, H - band_h, W, band_h, stroke=0, fill=1)

    logo = _logo()
    text_x0 = x0
    if logo:
        logo_size = 21 * mm
        logo_y = H - band_h + (band_h - logo_size) / 2
        c.saveState()
        p = c.beginPath()                       # round white plate behind the badge, so it reads
        p.roundRect(x0, logo_y, logo_size, logo_size, 4)   # cleanly against the dark green band
        c.clipPath(p, stroke=0, fill=0)
        c.setFillColorRGB(1, 1, 1)
        c.roundRect(x0, logo_y, logo_size, logo_size, 4, stroke=0, fill=1)
        c.drawImage(logo, x0, logo_y, width=logo_size, height=logo_size, mask="auto", preserveAspectRatio=True)
        c.restoreState()
        text_x0 = x0 + logo_size + 3.5 * mm

    text_width = x1 - text_x0
    c.setFillColorRGB(1, 1, 1)
    name = store.get("store_name") or "Waqare Medina Computers & Laptop"
    name_size = 15.0
    while name_size > 9.5 and c.stringWidth(name, "Helvetica-Bold", name_size) > text_width:
        name_size -= 0.5
    c.setFont("Helvetica-Bold", name_size)
    c.drawString(text_x0, H - 11 * mm, name)
    c.setFont("Helvetica", 8.3)
    addr = store.get("address", "")
    phone = store.get("phone_number", "")
    line2 = addr + ("   |   " + phone if phone else "")
    c.drawString(text_x0, H - 16.6 * mm, line2[:70])
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(text_x0, H - 22.5 * mm, "SALE RECEIPT")
    c.setFont("Helvetica", 8.5)
    c.drawRightString(x1, H - 22.5 * mm, sale["receipt_no"])
    c.setFont("Helvetica", 7.6)
    c.drawRightString(x1, H - 26.7 * mm, format_date(sale["sale_date"], "%d %b %Y, %I:%M %p"))

    y = H - 34 * mm

    # ---- customer ----
    c.setFillColorRGB(*MUTED)
    c.setFont("Helvetica-Bold", 7.3)
    c.drawString(x0, y, "BILLED TO")
    y -= 4.6 * mm
    c.setFillColorRGB(*INK)
    c.setFont("Helvetica-Bold", 10.5)
    c.drawString(x0, y, sale.get("customer_name", "") or "Walk-in customer")
    y -= 4.6 * mm
    if sale.get("customer_phone"):
        c.setFont("Helvetica", 8.6)
        c.setFillColorRGB(*MUTED)
        c.drawString(x0, y, sale["customer_phone"])
        y -= 5.5 * mm
    else:
        y -= 1 * mm

    c.setStrokeColorRGB(*LINE)
    c.setLineWidth(0.7)
    c.line(x0, y, x1, y)
    y -= 6 * mm

    # ---- item(s) ----
    for item in sale.get("items") or []:
        c.setFillColorRGB(*INK)
        y = _wrap(c, item["product_display"], x0, y, width - 18 * mm, "Helvetica-Bold", 9.6, INK)
        if item.get("specs_display"):
            c.setFont("Helvetica", 7.6)
            c.setFillColorRGB(*MUTED)
            c.drawString(x0, y + 1, item["specs_display"])
        c.setFont("Helvetica", 8.6)
        c.setFillColorRGB(*INK)
        c.drawRightString(x1, y + 1 + 4.2 * mm, format_currency(item["sale_price"]))
        qty = item.get("quantity", 1)
        if qty != 1:
            c.setFont("Helvetica", 7.4)
            c.setFillColorRGB(*MUTED)
            c.drawRightString(x1, y - 3.2 * mm, f"Qty {qty}")
            y -= 3.6 * mm
        y -= 6.4 * mm

    c.setStrokeColorRGB(*LINE)
    c.line(x0, y, x1, y)
    y -= 6 * mm

    # ---- totals ----
    def total_row(text: str, value: str, bold: bool = False, color=INK, size: float = 8.8):
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.setFillColorRGB(*color)
        c.drawString(x0, y, text)
        c.drawRightString(x1, y, value)
        y -= 5.2 * mm

    total_row("Subtotal", format_currency(sale["subtotal"]))
    if sale.get("discount_total"):
        total_row("Discount", "- " + format_currency(sale["discount_total"]), color=GREEN)

    y -= 1 * mm
    box_top = y + 3.6 * mm
    c.setFillColorRGB(*SOFT)
    c.roundRect(x0 - 2, y - 4.6 * mm, width + 4, 10.4 * mm, 3, stroke=0, fill=1)
    c.setFont("Helvetica-Bold", 11.5)
    c.setFillColorRGB(*GREEN_DARK)
    c.drawString(x0 + 2, y, "TOTAL")
    c.drawRightString(x1 - 2, y, format_currency(sale["final_total"]))
    y -= 9.6 * mm

    total_row("Amount received", format_currency(sale["amount_received"]))
    total_row("Payment method", (sale.get("payment_type") or "CASH").title())
    if sale.get("remaining_amount"):
        total_row("Balance due", format_currency(sale["remaining_amount"]), bold=True, color=(0xc0 / 255, 0x2d / 255, 0x32 / 255))
    else:
        total_row("Status", "PAID IN FULL", bold=True, color=GREEN)

    if sale.get("notes"):
        y -= 2 * mm
        y = _wrap(c, sale["notes"], x0, y, width, "Helvetica-Oblique", 7.6, MUTED)

    # ---- footer ----
    foot_y = 16 * mm
    c.setStrokeColorRGB(*LINE)
    c.line(x0, foot_y + 7 * mm, x1, foot_y + 7 * mm)
    thanks = store.get("thank_you_message") or "Thank you for choosing us!"
    c.setFont("Helvetica-Bold", 8.6)
    c.setFillColorRGB(*GREEN_DARK)
    c.drawCentredString(W / 2, foot_y + 2.4 * mm, thanks[:60])
    who = " / ".join(p for p in (store.get("ceo_name"), store.get("ceo_contact_number")) if p)
    if who:
        c.setFont("Helvetica", 6.8)
        c.setFillColorRGB(*MUTED)
        c.drawCentredString(W / 2, foot_y - 2 * mm, who)

    c.showPage()
    c.save()
    return out_path
