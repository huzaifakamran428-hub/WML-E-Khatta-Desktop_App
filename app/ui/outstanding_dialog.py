"""
Outstanding payments: one place to see everyone who still owes money -
customers (credit plans + unpaid sale balances) and shopkeepers - instead of
hunting through three separate pages.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QHBoxLayout, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget

from app.calc import EPS
from app.local_api import APIError, client
from app.ui.components import GlassDialog, card, label, make_button, show_error
from app.ui.theme import C
from app.utils.formatting import format_currency, format_date


def _style_table(t: QTableWidget):
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(44)
    t.setShowGrid(False)
    t.setAlternatingRowColors(True)
    t.horizontalHeader().setStretchLastSection(True)
    t.setMinimumHeight(120)


def _action_cell(button: QWidget | None) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(4, 2, 4, 2)
    if button is not None:
        lay.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    lay.addStretch(1)
    return w


class OutstandingDialog(GlassDialog):
    """Read-only breakdown, with a shortcut to each person's own page for action."""

    def __init__(self, parent, navigate=None):
        super().__init__(parent, "Outstanding payments", "Everyone who still owes money, in one place.",
                         "wallet", 780)
        self.navigate = navigate

        totals = QHBoxLayout()
        totals.setSpacing(12)
        self.total_all = self._total_card(totals, "Total outstanding")
        self.total_customers = self._total_card(totals, "Customers owe")
        self.total_shopkeepers = self._total_card(totals, "Shopkeepers owe")
        self.body_layout.addLayout(totals)

        self.tabs = QTabWidget()
        self.customers_tab = QTableWidget(0, 4)
        self.customers_tab.setHorizontalHeaderLabels(["Customer", "For", "Owed", ""])
        _style_table(self.customers_tab)
        self.shopkeepers_tab = QTableWidget(0, 4)
        self.shopkeepers_tab.setHorizontalHeaderLabels(["Shopkeeper", "Ref", "Owed", ""])
        _style_table(self.shopkeepers_tab)
        self.tabs.addTab(self.customers_tab, "Customers")
        self.tabs.addTab(self.shopkeepers_tab, "Shopkeepers")
        self.body_layout.addWidget(self.tabs)

        self.error_label = label("", "error", wrap=True)
        self.error_label.hide()
        self.body_layout.addWidget(self.error_label)

        close = make_button("Close", "x")
        close.clicked.connect(self.accept)
        self.button_row.addStretch(1)
        self.button_row.addWidget(close)

        self._fill()
        self.finish()

    def _total_card(self, layout: QHBoxLayout, title: str) -> QWidget:
        box = card(shadow=False)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.addWidget(label(title, "hint"))
        value = label("-", "h2")
        lay.addWidget(value)
        layout.addWidget(box, 1)
        return value

    # -- data --------------------------------------------------------------

    def _fill(self):
        try:
            plans = [p for p in client.list_("credit-plans/") if p["remaining_amount"] > EPS]
            sales = [s for s in client.list_("sales/") if s["remaining_amount"] > EPS]
            shopkeepers = [sk for sk in client.list_("shopkeepers/") if sk["remaining_amount"] > EPS]
        except APIError as exc:
            self.error_label.setText(f"Could not load: {exc.message}")
            self.error_label.show()
            return

        customer_total = sum(p["remaining_amount"] for p in plans) + sum(s["remaining_amount"] for s in sales)
        shopkeeper_total = sum(sk["remaining_amount"] for sk in shopkeepers)
        self.total_all.setText(format_currency(customer_total + shopkeeper_total))
        self.total_customers.setText(format_currency(customer_total))
        self.total_shopkeepers.setText(format_currency(shopkeeper_total))
        self.tabs.setTabText(0, f"Customers ({len(plans) + len(sales)})")
        self.tabs.setTabText(1, f"Shopkeepers ({len(shopkeepers)})")

        rows = [(p["remaining_amount"], "plan", p) for p in plans] + [(s["remaining_amount"], "sale", s) for s in sales]
        rows.sort(key=lambda r: r[0], reverse=True)
        self.customers_tab.setRowCount(len(rows))
        for r, (_amt, kind, row) in enumerate(rows):
            if kind == "plan":
                name, owed = row["person_name"], row["remaining_amount"]
                detail = f"Due {format_date(row['due_date'])}" if row.get("due_date") else "Credit plan"
                self.customers_tab.setItem(r, 0, QTableWidgetItem(name))
                if row.get("is_overdue"):
                    detail += "  •  Overdue"
                self.customers_tab.setItem(r, 1, QTableWidgetItem(detail))
                self.customers_tab.setItem(r, 2, QTableWidgetItem(format_currency(owed)))
                pay = make_button("Pay", "cash", "soft")
                pay.clicked.connect(lambda _=False, plan=row: self._pay_plan(plan))
                self.customers_tab.setCellWidget(r, 3, _action_cell(pay))
                if row.get("is_overdue"):
                    for c in range(3):
                        item = self.customers_tab.item(r, c)
                        if item:
                            item.setForeground(QColor(C["danger"]))
            else:
                name, owed = row["customer_name"], row["remaining_amount"]
                self.customers_tab.setItem(r, 0, QTableWidgetItem(name))
                self.customers_tab.setItem(r, 1, QTableWidgetItem(f"Sale {row['receipt_no']}"))
                self.customers_tab.setItem(r, 2, QTableWidgetItem(format_currency(owed)))
                open_btn = make_button("Open sales", "receipt", "soft")
                open_btn.clicked.connect(lambda _=False: self._go("sales"))
                self.customers_tab.setCellWidget(r, 3, _action_cell(open_btn))
        self.customers_tab.resizeRowsToContents()

        shopkeepers.sort(key=lambda r: r["remaining_amount"], reverse=True)
        self.shopkeepers_tab.setRowCount(len(shopkeepers))
        for r, sk in enumerate(shopkeepers):
            self.shopkeepers_tab.setItem(r, 0, QTableWidgetItem(sk["name"]))
            self.shopkeepers_tab.setItem(r, 1, QTableWidgetItem(sk.get("reference_number", "")))
            self.shopkeepers_tab.setItem(r, 2, QTableWidgetItem(format_currency(sk["remaining_amount"])))
            open_btn = make_button("Open", "eye", "soft")
            open_btn.clicked.connect(lambda _=False, sid=sk["id"]: self._open_shopkeeper(sid))
            self.shopkeepers_tab.setCellWidget(r, 3, _action_cell(open_btn))
        self.shopkeepers_tab.resizeRowsToContents()

    # -- actions -------------------------------------------------------------

    def _pay_plan(self, plan: dict):
        from app.ui.credit_page import RecordPaymentDialog
        dlg = RecordPaymentDialog(self, plan)
        if dlg.exec():
            try:
                client.create("payments/", dlg.payload)
                self._fill()
            except APIError as exc:
                show_error(self, "Could not save payment", exc.message)

    def _open_shopkeeper(self, shopkeeper_id: int):
        from app.ui.shopkeepers_page import ShopkeeperDetailDialog
        dlg = ShopkeeperDetailDialog(self, shopkeeper_id)
        dlg.exec()
        self._fill()

    def _go(self, page_key: str):
        if self.navigate:
            self.accept()
            self.navigate(page_key)
