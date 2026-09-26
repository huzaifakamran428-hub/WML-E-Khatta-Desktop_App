"""Dashboard: at-a-glance numbers, with a Reports/Users shortcut row for admins."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.local_api import APIError, client
from app.ui.components import ClickableLabel, GlassDialog, PageHeader, card, icon_chip, label, make_button
from app.ui.theme import C
from app.utils.formatting import format_currency, format_date


class SoldLaptopsDialog(GlassDialog):
    """Every laptop sold across all sales, newest first."""

    def __init__(self, parent, sold_items: list[dict]):
        super().__init__(parent, "Laptops sold", f"{len(sold_items)} laptop{'s' if len(sold_items) != 1 else ''} sold in total.",
                         "receipt", 720)
        table = QTableWidget(0, 6)
        table.setHorizontalHeaderLabels(["Receipt", "Customer", "Laptop", "Qty", "Sale price", "Date"])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(44)
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setStretchLastSection(True)
        table.setMinimumHeight(320)
        table.setRowCount(len(sold_items))
        for r, item in enumerate(sold_items):
            table.setItem(r, 0, QTableWidgetItem(item["receipt_no"]))
            table.setItem(r, 1, QTableWidgetItem(item["customer_name"]))
            table.setItem(r, 2, QTableWidgetItem(f"{item['brand']} {item['model_name']}".strip()))
            qty_item = QTableWidgetItem(str(item["quantity"]))
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(r, 3, qty_item)
            price_item = QTableWidgetItem(format_currency(item["sale_price"]))
            price_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(r, 4, price_item)
            table.setItem(r, 5, QTableWidgetItem(format_date(item["sale_date"])))
        table.resizeRowsToContents()
        self.body_layout.addWidget(table)

        close = make_button("Close", "x")
        close.clicked.connect(self.accept)
        self.button_row.addStretch(1)
        self.button_row.addWidget(close)
        self.finish()


class StatCard(QWidget):
    def __init__(self, icon_name: str, title: str, value: str, tone: str = "green", on_view=None, subtitle: str = "",
                 on_subtitle_click=None):
        super().__init__()
        box = card()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(box)
        inner = QVBoxLayout(box)
        inner.setContentsMargins(20, 18, 20, 18)
        inner.setSpacing(10)
        top = QHBoxLayout()
        top.addWidget(icon_chip(icon_name, 42, 21))
        top.addStretch(1)
        if on_view is not None:
            view_btn = make_button("View", "eye", "ghost", "See who still owes money")
            view_btn.clicked.connect(on_view)
            top.addWidget(view_btn)
        inner.addLayout(top)
        self.value_label = label(value, "statValue")
        if tone == "danger":
            self.value_label.setStyleSheet(f"color: {C['danger']};")
        elif tone == "gold":
            self.value_label.setStyleSheet(f"color: {C['gold']};")
        inner.addWidget(self.value_label)
        inner.addWidget(label(title, "statTitle"))
        if on_subtitle_click is not None:
            self.subtitle_label = ClickableLabel(subtitle, "statSubLink")
            self.subtitle_label.setToolTip("Click to see the sold laptops")
            self.subtitle_label.clicked.connect(on_subtitle_click)
        else:
            self.subtitle_label = label(subtitle, "statSub")
        self.subtitle_label.setVisible(bool(subtitle))
        inner.addWidget(self.subtitle_label)

    def set_value(self, text: str):
        self.value_label.setText(text)

    def set_subtitle(self, text: str):
        self.subtitle_label.setText(text)
        self.subtitle_label.setVisible(bool(text))


class DashboardPage(QWidget):
    def __init__(self, navigate):
        super().__init__()
        self.navigate = navigate
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(18)

        self.header = PageHeader("Dashboard", "", "dashboard")
        refresh = make_button("Refresh", "refresh")
        refresh.clicked.connect(self.reload)
        self.header.add_action(refresh)
        outer.addWidget(self.header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        holder = QWidget()
        self.grid = QGridLayout(holder)
        self.grid.setContentsMargins(2, 2, 2, 2)
        self.grid.setSpacing(16)
        scroll.setWidget(holder)
        outer.addWidget(scroll, 1)

        self.cards: dict[str, StatCard] = {}
        self._sold_items: list[dict] = []
        self.reload()

    def _ensure_cards(self, is_admin: bool):
        if self.cards:
            return
        specs = [
            ("total_units", "box", "Laptops in stock"),
            ("low_stock_count", "alert", "Low stock items"),
            ("out_of_stock_count", "x", "Out of stock"),
            ("total_sales", "trend", "Total sales"),
            ("total_outstanding", "wallet", "Outstanding to collect"),
        ]
        if is_admin:
            specs += [("total_profit", "cash", "Total profit"), ("total_investment", "tag", "Stock investment"),
                     ("total_purchase_cost", "receipt", "Purchase cost of sold stock")]
        for i, (key, ic, title) in enumerate(specs):
            on_view = self._view_outstanding if key == "total_outstanding" else None
            on_sub = self._view_sold_laptops if key == "total_purchase_cost" else None
            c = StatCard(ic, title, "-", on_view=on_view, on_subtitle_click=on_sub)
            self.cards[key] = c
            self.grid.addWidget(c, i // 3, i % 3)
        for col in range(3):
            self.grid.setColumnStretch(col, 1)

    def reload(self):
        try:
            data = client.get_json("dashboard/")
        except APIError as exc:
            self.header.set_subtitle(f"Could not load: {exc.message}")
            return
        self._ensure_cards("total_profit" in data)
        for key, c in self.cards.items():
            value = data.get(key, 0)
            money_keys = ("total_sales", "total_outstanding", "total_profit", "total_investment", "total_purchase_cost")
            c.set_value(format_currency(value) if key in money_keys else str(int(value)))
            if key == "total_outstanding":
                c.value_label.setStyleSheet(f"color: {C['danger'] if value else C['ink']};" if value else "")
            if key == "total_purchase_cost":
                units = int(data.get("units_sold", 0))
                self._sold_items = data.get("sold_items", [])
                c.set_subtitle(f"{units} laptop{'s' if units != 1 else ''} sold" if units else "No laptops sold yet")
        self.header.set_subtitle("Store overview, updated just now")

    def _view_outstanding(self):
        from app.ui.outstanding_dialog import OutstandingDialog
        dlg = OutstandingDialog(self, navigate=self.navigate)
        dlg.exec()
        self.reload()

    def _view_sold_laptops(self):
        if not self._sold_items:
            return
        SoldLaptopsDialog(self, self._sold_items).exec()
