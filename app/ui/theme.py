"""
Look and feel of WML E-Khatta: a clean, glossy, iPhone-style theme.

Colours come from the shop logo (emerald green + gold). Everything visual is
in this one file -- change a colour in COLORS and the whole app follows.
"""
from __future__ import annotations

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication, QLabel

from app import config

COLORS = {
    "ink": "#13221b",          # main text
    "ink2": "#56675e",         # secondary text
    "muted": "#93a39a",        # hints
    "line": "#dfe8e3",         # hairlines / borders
    "bg1": "#f5f9f7",          # window gradient (top-left)
    "bg2": "#e3ece7",          # window gradient (bottom-right)
    "green": "#12a05c",
    "green_dark": "#0b7a45",
    "green_soft": "#e4f6ec",
    "gold": "#d9a441",
    "gold_soft": "#fbf1dc",
    "danger": "#e0393e",
    "danger_soft": "#fdecec",
    "warn": "#e69a10",
    "blue": "#2f7cf6",
    "side_top": "#134d38",     # sidebar gradient
    "side_bottom": "#06171a",
}
C = COLORS

# -- icons (24x24 line icons, drawn as vectors so they are always sharp) ----

ICONS = {
    "dashboard": '<rect x="3" y="3" width="7.5" height="9" rx="2"/><rect x="13.5" y="3" width="7.5" height="5" rx="2"/><rect x="13.5" y="11" width="7.5" height="10" rx="2"/><rect x="3" y="15" width="7.5" height="6" rx="2"/>',
    "laptop": '<rect x="4.5" y="4.5" width="15" height="11" rx="2"/><path d="M2 19.5h20"/><path d="M9.5 19.5l.5-2h4l.5 2"/>',
    "customers": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6"/><path d="M16 4.7a3.5 3.5 0 0 1 0 6.6"/><path d="M18.2 14.4c1.9.8 3.3 2.6 3.3 5.6"/>',
    "receipt": '<path d="M5.5 3h13v18l-2.6-1.8L13.3 21l-2.6-1.8L8.1 21 5.5 19.2z"/><path d="M9 8h6M9 12h6"/>',
    "store": '<path d="M3.5 9.5L5 4h14l1.5 5.5"/><path d="M4.5 9.5V20h15V9.5"/><path d="M3.5 9.5a2.8 2.8 0 0 0 5.5 0 2.8 2.8 0 0 0 6 0 2.8 2.8 0 0 0 5.5 0"/><path d="M10 20v-5h4v5"/>',
    "card": '<rect x="2.5" y="5" width="19" height="14" rx="3"/><path d="M2.5 10h19"/><path d="M6.5 15h4"/>',
    "chart": '<path d="M3.5 3.5v17h17"/><path d="M8 16v-5M12.5 16V7M17 16v-8"/>',
    "shield": '<path d="M12 3l7.5 2.8v5.7c0 4.4-3.1 7.9-7.5 9.5-4.4-1.6-7.5-5.1-7.5-9.5V5.8z"/><path d="M9 12l2.2 2.2L15.5 10"/>',
    "clipboard": '<rect x="5" y="4.5" width="14" height="16.5" rx="2.5"/><path d="M9 4.5V3.8A.8.8 0 0 1 9.8 3h4.4a.8.8 0 0 1 .8.8v.7"/><path d="M8.5 11h7M8.5 15h5"/>',
    "bell": '<path d="M6 16v-5a6 6 0 0 1 12 0v5l1.8 2H4.2z"/><path d="M10 21h4"/>',
    "settings": '<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2.3"/><circle cx="9" cy="17" r="2.3"/>',
    "logout": '<path d="M9.5 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h3.5"/><path d="M15.5 8l4 4-4 4M19.5 12H9"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.3-4.3"/>',
    "refresh": '<path d="M20 12a8 8 0 1 1-2.6-5.9"/><path d="M20 4.5V9h-4.5"/>',
    "edit": '<path d="M4 20l1-4.2L16.6 4.2a2.2 2.2 0 0 1 3.1 3.1L8.1 18.9z"/><path d="M14.6 6.2l3.2 3.2"/>',
    "trash": '<path d="M4 7h16"/><path d="M9.5 7V4.5h5V7"/><path d="M6 7l.9 12.5h10.2L18 7"/><path d="M10 11v5M14 11v5"/>',
    "upload": '<path d="M12 16V4.5M7.5 9L12 4.5 16.5 9"/><path d="M4.5 15.5V18a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-2.5"/>',
    "download": '<path d="M12 4v11.5M7.5 11L12 15.5 16.5 11"/><path d="M4.5 15.5V18a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-2.5"/>',
    "cloud": '<path d="M17.5 19H7.2a4.7 4.7 0 0 1-.8-9.3A6 6 0 0 1 18 10.8 4.1 4.1 0 0 1 17.5 19z"/>',
    "cloud-check": '<path d="M17.5 19H7.2a4.7 4.7 0 0 1-.8-9.3A6 6 0 0 1 18 10.8 4.1 4.1 0 0 1 17.5 19z"/><path d="M9.5 13.5l2 2 3.5-3.7"/>',
    "cloud-off": '<path d="M9 5.6A6 6 0 0 1 18 10.8 4.1 4.1 0 0 1 20 17.2M6.4 9.7A4.7 4.7 0 0 0 7.2 19H15"/><path d="M3 3l18 18"/>',
    "printer": '<path d="M7 9V3.5h10V9"/><rect x="3.5" y="9" width="17" height="8" rx="2.5"/><path d="M7 14h10v6.5H7z"/>',
    "eye": '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "eye-off": '<path d="M3 3l18 18"/><path d="M10.6 5.2A9.7 9.7 0 0 1 12 5c6.4 0 10 7 10 7a17 17 0 0 1-3.1 4M6.2 6.6A16.6 16.6 0 0 0 2 12s3.6 7 10 7c1.4 0 2.7-.3 3.8-.8"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/>',
    "wallet": '<rect x="3" y="6" width="18" height="13.5" rx="3"/><path d="M3 10h18"/><path d="M16.5 14.7h1.8"/>',
    "history": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "x": '<path d="M6 6l12 12M18 6L6 18"/>',
    "lock": '<rect x="5" y="11" width="14" height="9.5" rx="2.5"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4.5 20.5c0-3.9 3.4-6.5 7.5-6.5s7.5 2.6 7.5 6.5"/>',
    "key": '<circle cx="8" cy="15" r="4"/><path d="M11 12l8-8M16 7l2.5 2.5"/>',
    "back": '<path d="M14.5 5.5L8 12l6.5 6.5"/>',
    "box": '<path d="M3.5 7.5L12 3l8.5 4.5v9L12 21l-8.5-4.5z"/><path d="M3.5 7.5L12 12l8.5-4.5M12 12v9"/>',
    "trend": '<path d="M3 17l6-6 4 4 7-8"/><path d="M15 7h5v5"/>',
    "alert": '<path d="M12 4l9 16H3z"/><path d="M12 10v4.5M12 17.4v.1"/>',
    "file": '<path d="M6 3h8l4.5 4.5V20a1 1 0 0 1-1 1h-11.5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/><path d="M14 3v5h4.5M9 13h6M9 17h4"/>',
    "tag": '<path d="M3.5 12.2V4.5a1 1 0 0 1 1-1h7.7l8.3 8.3a1.5 1.5 0 0 1 0 2.1l-6.4 6.4a1.5 1.5 0 0 1-2.1 0z"/><circle cx="8.5" cy="8.5" r="1.3"/>',
    "cash": '<rect x="2.5" y="6" width="19" height="12" rx="2.5"/><circle cx="12" cy="12" r="2.8"/><path d="M6 9.5v.1M18 14.5v.1"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.7v.1"/>',
}

_icon_cache: dict = {}


def _render(name: str, color: str, size: int, ratio: int = 2) -> QPixmap:
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pm = QPixmap(size * ratio, size * ratio)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def pixmap(name: str, color: str = "#13221b", size: int = 20) -> QPixmap:
    key = ("pm", name, color, size)
    if key not in _icon_cache:
        _icon_cache[key] = _render(name, color, size)
    return _icon_cache[key]


def icon(name: str, color: str = "#13221b", size: int = 20, on_color: str | None = None) -> QIcon:
    """A crisp vector icon. `on_color` is used when a checkable button is checked."""
    key = ("ic", name, color, size, on_color)
    if key not in _icon_cache:
        ic = QIcon()
        ic.addPixmap(pixmap(name, color, size), QIcon.Mode.Normal, QIcon.State.Off)
        ic.addPixmap(pixmap(name, on_color or color, size), QIcon.Mode.Normal, QIcon.State.On)
        ic.addPixmap(pixmap(name, "#b7c4bd", size), QIcon.Mode.Disabled, QIcon.State.Off)
        _icon_cache[key] = ic
    return _icon_cache[key]


def logo_label(asset_file: str, size: int) -> QLabel:
    """The shop logo (a full circular badge, not a square icon), rendered so it always
    fits its box cleanly -- fixed square label + a pixmap rendered 3x the box size then
    down-scaled with its device-pixel-ratio set, so it stays sharp and never gets cut
    off or stretched oddly on Windows displays running at 125%/150% scaling."""
    lbl = QLabel()
    lbl.setFixedSize(size, size)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    src = QPixmap(config.asset_path(asset_file))
    if not src.isNull():
        hi_res = size * 3
        scaled = src.scaled(hi_res, hi_res, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        scaled.setDevicePixelRatio(3.0)
        lbl.setPixmap(scaled)
    return lbl


# -- the stylesheet ---------------------------------------------------------

QSS = """
* { font-family: "SF Pro Text", "Helvetica Neue", "Segoe UI Variable Text", "Segoe UI", "Inter", "Arial", sans-serif;
    font-size: 13px; color: {{ink}}; outline: 0; }
QMainWindow, QDialog, QMessageBox {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {{bg1}}, stop:1 {{bg2}}); }
QLabel { background: transparent; }
QToolTip { background: #10221a; color: white; border: none; padding: 6px 10px; border-radius: 7px; }

QLabel#h1 { font-size: 26px; font-weight: 700; color: {{ink}}; }
QLabel#h2 { font-size: 17px; font-weight: 700; color: {{ink}}; }
QLabel#dialogTitle { font-size: 20px; font-weight: 700; }
QLabel#sub { color: {{ink2}}; font-size: 13px; }
QLabel#hint { color: {{muted}}; font-size: 12px; }
QLabel#fieldLabel { color: {{ink2}}; font-size: 12px; font-weight: 600; }
QLabel#statValue { font-size: 26px; font-weight: 700; }
QLabel#statTitle { color: {{ink2}}; font-size: 12.5px; font-weight: 600; }
QLabel#statSub { color: {{muted}}; font-size: 11.5px; font-weight: 500; }
QLabel#statSubLink { color: {{green_dark}}; font-size: 14.5px; font-weight: 700; }
QLabel#statSubLink:hover { color: {{green}}; text-decoration: underline; }
QLabel#bigTotal { font-size: 30px; font-weight: 800; color: {{green_dark}}; }
QLabel#error { color: {{danger}}; font-weight: 600; }

/* ---------- glass cards ---------- */
QFrame#card {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #f9fcfa);
    border: 1px solid {{line}}; border-radius: 18px; }
QFrame#summary {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f2fbf6, stop:1 #e5f5ec);
    border: 1px solid #bfe3cf; border-radius: 16px; }
QFrame#divider { background: {{line}}; max-height: 1px; min-height: 1px; border: none; }
QLabel#iconChip {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #34cf83, stop:1 #0e8f50);
    border: 1px solid #0b7a45; border-radius: 13px; }

/* ---------- buttons ---------- */
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:0.5 #f6faf8, stop:1 #e9f0ec);
    border: 1px solid #cfdcd5; border-radius: 11px; padding: 8px 16px;
    font-weight: 600; color: {{ink}}; min-height: 20px; }
QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #dfeae4);
    border-color: #b6c9bf; }
QPushButton:pressed { background: #d5e2db; padding-top: 9px; padding-bottom: 7px; }
QPushButton:disabled { color: #a6b5ad; background: #f0f5f2; border-color: #e2eae6; }
QPushButton:focus { border: 1.5px solid {{green}}; }

QPushButton[variant="primary"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #46dc95, stop:0.48 #18b068, stop:0.52 #12a05c, stop:1 #0c8449);
    border: 1px solid #0a7040; color: white; }
QPushButton[variant="primary"]:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #5ce8a6, stop:0.48 #22bd75, stop:0.52 #16ad66, stop:1 #0e9052); }
QPushButton[variant="primary"]:pressed { background: #0c8449; }
QPushButton[variant="primary"]:disabled { background: #9bd3b6; border-color: #86c2a3; color: #eafaf1; }

QPushButton[variant="gold"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f6cf7d, stop:0.5 #dcaa45, stop:1 #c48f2b);
    border: 1px solid #a9791f; color: #2b1d00; }
QPushButton[variant="danger"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f0686c, stop:0.5 #e0393e, stop:1 #c62a2f);
    border: 1px solid #b0242a; color: white; }
QPushButton[variant="soft"] { background: {{green_soft}}; border: 1px solid #c3e6d2; color: {{green_dark}}; }
QPushButton[variant="soft"]:hover { background: #d5f0e2; }
QPushButton[variant="dangerSoft"] { background: {{danger_soft}}; border: 1px solid #f5cccd; color: #bf2d32; }
QPushButton[variant="dangerSoft"]:hover { background: #fbdcdd; }
QPushButton[variant="mini"] { padding: 4px 11px; border-radius: 9px; font-size: 12px; min-height: 16px; }
QPushButton[variant="icon"] { padding: 6px; min-width: 20px; border-radius: 9px; }
QPushButton[variant="ghost"] { background: transparent; border: none; color: {{ink2}}; }
QPushButton[variant="ghost"]:hover { background: rgba(18,160,92,0.10); }

/* ---------- inputs ---------- */
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QDateEdit {
    background: white; border: 1px solid #d0dcd5; border-radius: 11px; padding: 8px 12px;
    selection-background-color: #bfead2; selection-color: {{ink}}; }
QLineEdit:hover, QComboBox:hover, QDateEdit:hover { border-color: #b3c6bc; }
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QDateEdit:focus {
    border: 1.5px solid {{green}}; }
QLineEdit:read-only { background: #f1f6f3; color: {{ink2}}; }
QLineEdit#search { padding-left: 6px; border-radius: 14px; background: rgba(255,255,255,0.9); }
QLineEdit#money { font-size: 15px; font-weight: 600; padding: 9px 12px; }
QComboBox { padding-right: 30px; min-height: 20px; }
QComboBox::drop-down { border: none; width: 30px; }
QComboBox::down-arrow { image: url({{chevron}}); width: 12px; height: 12px; }
QDateEdit::drop-down { border: none; width: 30px; }
QDateEdit::down-arrow { image: url({{chevron}}); width: 12px; height: 12px; }
QComboBox QAbstractItemView { background: white; border: 1px solid #cfdcd5; border-radius: 10px; padding: 4px;
    selection-background-color: #e1f4ea; selection-color: {{ink}}; }
QCalendarWidget QWidget { background: white; }
QCalendarWidget QAbstractItemView:enabled { selection-background-color: {{green}}; selection-color: white; }

QCheckBox { spacing: 9px; background: transparent; }
QCheckBox::indicator { width: 19px; height: 19px; border-radius: 6px; border: 1.5px solid #b3c6bc; background: white; }
QCheckBox::indicator:hover { border-color: {{green}}; }
QCheckBox::indicator:checked { border: 1px solid #0a7040; image: url({{check}});
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3fd68b, stop:1 #0e8f50); }

/* ---------- tables ---------- */
QTableWidget { background: transparent; border: none; gridline-color: transparent;
    alternate-background-color: #f7fbf9; selection-background-color: #e2f5eb; selection-color: {{ink}}; }
QTableWidget::item { padding: 4px 10px; border-bottom: 1px solid #edf3ef; }
QTableWidget::item:selected { background: #e2f5eb; color: {{ink}}; }
QHeaderView { background: transparent; }
QHeaderView::section { background: transparent; color: {{ink2}}; font-weight: 700; font-size: 12px;
    padding: 11px 10px; border: none; border-bottom: 1px solid {{line}}; }
QTableCornerButton::section { background: transparent; border: none; }

/* ---------- scrollbars ---------- */
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 11px; margin: 3px; }
QScrollBar::handle:vertical { background: #c2d1c9; border-radius: 4px; min-height: 34px; }
QScrollBar::handle:vertical:hover { background: #a3b7ac; }
QScrollBar:horizontal { background: transparent; height: 11px; margin: 3px; }
QScrollBar::handle:horizontal { background: #c2d1c9; border-radius: 4px; min-width: 34px; }
QScrollBar::handle:horizontal:hover { background: #a3b7ac; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* ---------- tabs ---------- */
QTabWidget::pane { border: none; background: transparent; top: 6px; }
QTabBar { background: transparent; }
QTabBar::tab { background: transparent; padding: 9px 20px; margin-right: 6px; border-radius: 12px;
    color: {{ink2}}; font-weight: 600; border: 1px solid transparent; }
QTabBar::tab:selected { background: white; color: {{green_dark}}; border: 1px solid {{line}}; }
QTabBar::tab:hover:!selected { background: rgba(255,255,255,0.65); }

/* ---------- status pills ---------- */
QLabel[pill] { border-radius: 10px; padding: 3px 11px; font-weight: 700; font-size: 12px; }
QLabel[pill="ok"] { background: #dcf5e7; color: #0a7a44; }
QLabel[pill="warn"] { background: #fdf0d3; color: #a86a00; }
QLabel[pill="bad"] { background: #fde3e3; color: #c02d32; }
QLabel[pill="muted"] { background: #eaf0ed; color: #5d6e65; }
QLabel[pill="info"] { background: #e0ecfe; color: #1f5fcf; }

/* ---------- sidebar ---------- */
QFrame#sidebar {
    background: qlineargradient(x1:0, y1:0, x2:0.35, y2:1, stop:0 {{side_top}}, stop:1 {{side_bottom}});
    border-right: 1px solid rgba(255,255,255,0.06); }
QFrame#sidebar QLabel { color: white; }
QLabel#brandName { font-size: 17px; font-weight: 800; color: white; }
QLabel#brandSub { font-size: 11px; color: #9fc7b3; }
QLabel#userName { font-size: 16px; font-weight: 700; color: white; }
QLabel#userRole { font-size: 12.5px; color: #9fc7b3; }
QLabel#avatar { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f6cf7d, stop:1 #c48f2b);
    border-radius: 20px; color: #2b1d00; font-weight: 800; font-size: 15px; }
QPushButton#navBtn { background: transparent; border: 1px solid transparent; border-radius: 13px;
    color: #cfe5da; text-align: left; padding: 11px 14px; font-size: 14px; font-weight: 600; min-height: 22px; }
QPushButton#navBtn:hover { background: rgba(255,255,255,0.08); color: white; }
QPushButton#navBtn:checked {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255,255,255,0.30), stop:0.5 rgba(255,255,255,0.14), stop:0.51 rgba(255,255,255,0.08), stop:1 rgba(255,255,255,0.14));
    border: 1px solid rgba(255,255,255,0.28); color: white; font-weight: 700; }
QPushButton#sideAction { background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.14);
    color: #e5f3ec; border-radius: 12px; padding: 9px 12px; font-weight: 600; }
QPushButton#sideAction:hover { background: rgba(255,255,255,0.16); }
QLabel#backupChip { background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.12);
    border-radius: 11px; padding: 7px 10px; color: #cfe5da; font-size: 11.5px; }
QLabel#devCredit { color: {{gold}}; font-family: "Segoe UI Semibold", "SF Pro Text", "Segoe UI", "Inter", "Arial", sans-serif;
    font-size: 12px; font-weight: 700; letter-spacing: 0.6px; }

/* ---------- login ---------- */
QWidget#loginRoot {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0f4a35, stop:0.55 #0a2f26, stop:1 #06171a); }
QFrame#loginCard { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255,255,255,250), stop:1 rgba(244,250,247,250));
    border: 1px solid rgba(255,255,255,0.7); border-radius: 26px; }
QLabel#devCreditLogin { color: {{green_dark}}; font-family: "Segoe UI Semibold", "SF Pro Text", "Segoe UI", "Inter", "Arial", sans-serif;
    font-size: 12.5px; font-weight: 700; letter-spacing: 0.6px; }
"""


def build_qss() -> str:
    config.UI_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    chevron = config.UI_CACHE_DIR / "chevron.png"
    check = config.UI_CACHE_DIR / "check.png"
    _render("check", "#ffffff", 12, 3).save(str(check))
    chev = _render("back", "#56675e", 12, 3)
    from PyQt6.QtGui import QTransform
    chev.transformed(QTransform().rotate(-90)).save(str(chevron))
    qss = QSS
    tokens = dict(COLORS, chevron=chevron.as_posix(), check=check.as_posix())
    for key, value in tokens.items():
        qss = qss.replace("{{" + key + "}}", value)
    return qss


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    font = QFont()
    font.setFamilies(["SF Pro Text", "Helvetica Neue", "Segoe UI Variable Text", "Segoe UI", "Inter", "Arial"])
    font.setPixelSize(13)
    app.setFont(font)
    app.setStyleSheet(build_qss())
    from PyQt6.QtGui import QPalette
    pal = app.palette()
    pal.setColor(QPalette.ColorRole.Highlight, QColor(C["green"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
    app.setPalette(pal)
