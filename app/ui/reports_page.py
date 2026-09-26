"""Reports: admin only. Pick a report and a date range, see the numbers, export CSV."""
from __future__ import annotations

import csv

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QComboBox, QDateEdit, QFileDialog, QHBoxLayout, QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.local_api import APIError, client
from app.ui.components import PageHeader, card, field, label, make_button, show_info
from app.utils.formatting import format_currency

REPORTS = {
    "sales": ("Sales", "reports/sales/", [("receipt_no", "Receipt"), ("customer__name", "Customer"),
             ("final_total", "Total"), ("sale_date", "Date")]),
    "profit": ("Profit", "reports/profit/", [("sale__receipt_no", "Receipt"), ("product__brand", "Brand"),
              ("product__model_name", "Model"), ("quantity", "Qty"), ("purchase_price", "Purchase Price"),
              ("sale_price", "Sale Price"), ("profit", "Profit")]),
    "inventory": ("Inventory", "reports/inventory/", None),
    "investment": ("Stock investment", "reports/investment/", None),
    "outstanding": ("Outstanding", "reports/outstanding/", None),
    "payments": ("Payments received", "reports/payments/", [("payment_date", "Date"), ("source", "Source"),
                ("amount", "Amount"), ("method", "Method")]),
}
MONEY_COLS = {"final_total", "profit", "amount", "sale_price", "purchase_price", "investment"}


class ReportsPage(QWidget):
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(18)

        self.header = PageHeader("Reports", "", "chart")
        self.kind = QComboBox()
        for key, (title, _ep, _cols) in REPORTS.items():
            self.kind.addItem(title, key)
        self.kind.currentIndexChanged.connect(self.reload)
        self.header.add_action(self.kind)
        self.date_from = QDateEdit(calendarPopup=True)
        self.date_from.setDisplayFormat("dd MMM yyyy")
        self.date_from.setDate(QDate.currentDate().addMonths(-1))
        self.date_from.dateChanged.connect(self.reload)
        self.header.add_action(self.date_from)
        self.date_to = QDateEdit(calendarPopup=True)
        self.date_to.setDisplayFormat("dd MMM yyyy")
        self.date_to.setDate(QDate.currentDate())
        self.date_to.dateChanged.connect(self.reload)
        self.header.add_action(self.date_to)
        export = make_button("Export CSV", "download")
        export.clicked.connect(self._export)
        self.header.add_action(export)
        outer.addWidget(self.header)

        summary = card(shadow=False)
        sl = QHBoxLayout(summary)
        sl.setContentsMargins(18, 14, 18, 14)
        self.summary_label = label("", "h2")
        sl.addWidget(self.summary_label)
        sl.addStretch(1)
        outer.addWidget(summary)

        box = card(shadow=False)
        box_lay = QVBoxLayout(box)
        box_lay.setContentsMargins(10, 8, 10, 10)
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        box_lay.addWidget(self.table)
        outer.addWidget(box, 1)

        self.rows: list[dict] = []
        self.columns: list[tuple] = []
        self.reload()

    def _params(self):
        return {"date_from": self.date_from.date().toString("yyyy-MM-dd"), "date_to": self.date_to.date().toString("yyyy-MM-dd")}

    def reload(self):
        key = self.kind.currentData()
        title, endpoint, columns = REPORTS[key]
        try:
            data = client.get_json(endpoint, self._params())
        except APIError as exc:
            self.header.set_subtitle(f"Could not load: {exc.message}")
            return
        self.header.set_subtitle(title)
        if columns:
            self.rows = data.get("sales") or data.get("items") or data.get("rows") or []
            self.columns = columns
            total_key = next((k for k in ("total_sales", "total_profit", "total_received") if k in data), None)
            self.summary_label.setText(f"{title}: {format_currency(data[total_key])}" if total_key else
                                       f"{title}: {len(self.rows)} record(s)")
        else:
            self._render_summary_report(key, title, data)
            return
        self._render_table()

    def _render_summary_report(self, key, title, data):
        if key == "inventory":
            self.columns = [("brand", "Brand"), ("model_name", "Model"), ("quantity", "Left")]
            self.rows = data["low_stock_items"]
            self.summary_label.setText(
                f"{data['total_units']} units in stock, worth {format_currency(data['total_stock_value'])} - "
                f"{data['low_stock_count']} low, {data['out_of_stock_count']} out of stock")
        elif key == "investment":
            self.columns = [("brand", "Brand"), ("model_name", "Model"), ("quantity", "Qty"),
                            ("purchase_price", "Purchase Price"), ("investment", "Investment")]
            self.rows = data["items"]
            self.summary_label.setText(f"Money tied up in current stock: {format_currency(data['total_investment'])} "
                                       f"across {data['laptops']} laptop line(s)")
        elif key == "outstanding":
            self.columns = [("person", "Person / receipt"), ("remaining_amount", "Owed")]
            self.rows = data["plans"] + data["sales"] + data["shopkeepers"]
            self.summary_label.setText(f"Total outstanding: {format_currency(data['total_outstanding'])}")
        self._render_table()

    def _render_table(self):
        t = self.table
        t.setColumnCount(len(self.columns))
        t.setHorizontalHeaderLabels([c[1] for c in self.columns])
        t.setRowCount(len(self.rows))
        for r, row in enumerate(self.rows):
            for c, (key, _header) in enumerate(self.columns):
                value = row.get(key, "")
                text = format_currency(value) if key in MONEY_COLS or key == "remaining_amount" else str(value)
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                t.setItem(r, c, item)

    def _export(self):
        if not self.rows:
            show_info(self, "Nothing to export", "There is no data for this report and date range.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export report", f"{self.kind.currentText()}.csv", "CSV files (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.writer(fh)
            writer.writerow([h for _k, h in self.columns])
            for row in self.rows:
                writer.writerow([row.get(k, "") for k, _h in self.columns])
        show_info(self, "Exported", f"Saved to:\n{path}")
