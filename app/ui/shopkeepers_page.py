"""
Shopkeepers: people who take laptops or cash from the shop and pay it off over
time. Each shopkeeper's detail view lists their laptops, extra money and
payments, and lets you record a new item or a payment against it.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget

from app.local_api import APIError, client
from app.ui.components import (
    GlassDialog, MoneyEdit, PageHeader, SearchCombo, ask_yes_no, card, divider, field, label, make_button,
    pill, show_error, show_info,
)
from app.ui.theme import C
from app.ui.widgets.crud import ColumnSpec, EntityListPage, FieldSpec, RowAction
from app.utils.formatting import format_currency, format_date

FIELDS = [
    FieldSpec("name", "Shopkeeper name"),
    FieldSpec("phone", "Phone number"),
    FieldSpec("cnic", "CNIC", required=False),
    FieldSpec("address", "Address", required=False, kind="multiline"),
    FieldSpec("notes", "Notes", required=False, kind="multiline"),
]


def _status_pill(row):
    return {"CLEARED": ("Cleared", "ok"), "PENDING": ("Pending", "warn"),
            "NO_ITEMS": ("No items yet", "muted")}.get(row.get("status"), ("-", "muted"))


class GiveLaptopDialog(GlassDialog):
    def __init__(self, parent, shopkeeper_id: int):
        super().__init__(parent, "Give a laptop", "Pick a laptop from stock to give to this shopkeeper.", "laptop", 520)
        self.shopkeeper_id = shopkeeper_id
        self.laptops = {}
        self.laptop = SearchCombo()
        for l in client.list_("laptops/"):
            if not l.get("is_archived") and l["quantity"] > 0:
                self.laptops[l["id"]] = l
                specs = ", ".join(p for p in (l.get("ram"), l.get("storage")) if p)
                self.laptop.addItem(f"{l['brand']} {l['model_name']} ({specs}) - {l['quantity']} in stock", l["id"])
        self.laptop.currentIndexChanged.connect(self._fill_price)
        self.body_layout.addWidget(field("Laptop", self.laptop))
        self.price = MoneyEdit()
        self.body_layout.addWidget(field("Price owed for this laptop (Rs.)", self.price))
        self.body_layout.addStretch(1)
        self.error_label = label("", "error", wrap=True)
        self.error_label.hide()
        self.pinned.addWidget(self.error_label)
        self.set_buttons("Give laptop", "check").clicked.connect(self._submit)
        self.finish()
        self._fill_price()

    def _fill_price(self):
        lap = self.laptops.get(self.laptop.currentData())
        if lap:
            self.price.setValue(lap["sale_price"])

    def _submit(self):
        if not self.laptop.has_valid_choice():
            self.error_label.setText("Please choose a laptop.")
            self.error_label.show()
            return
        self.payload = dict(shopkeeper=self.shopkeeper_id, inventory_laptop=self.laptop.currentData(),
                            price=self.price.value())
        self.accept()


class ExtraMoneyDialog(GlassDialog):
    def __init__(self, parent, shopkeeper_id: int):
        super().__init__(parent, "Add extra money", "Cash given to the shopkeeper, outside of a laptop.", "wallet", 480)
        self.shopkeeper_id = shopkeeper_id
        self.amount = MoneyEdit()
        self.body_layout.addWidget(field("Amount (Rs.)", self.amount))
        self.note = QTextEdit()
        self.note.setFixedHeight(60)
        self.body_layout.addWidget(field("Note", self.note))
        self.body_layout.addStretch(1)
        self.error_label = label("", "error", wrap=True)
        self.error_label.hide()
        self.pinned.addWidget(self.error_label)
        self.set_buttons("Add", "check").clicked.connect(self._submit)
        self.finish()

    def _submit(self):
        if self.amount.value() <= 0:
            self.error_label.setText("Enter an amount more than 0.")
            self.error_label.show()
            return
        self.payload = dict(shopkeeper=self.shopkeeper_id, amount=self.amount.value(), note=self.note.toPlainText().strip())
        self.accept()


class PayDialog(GlassDialog):
    def __init__(self, parent, shopkeeper_id: int, target: dict, is_laptop: bool):
        label_text = target.get("item_reference", "")
        super().__init__(parent, "Record payment", f"Against {label_text} - Rs. {target['remaining_amount']:,.0f} remaining.",
                         "cash", 480)
        self.shopkeeper_id, self.target, self.is_laptop = shopkeeper_id, target, is_laptop
        self.amount = MoneyEdit()
        self.amount.setValue(target["remaining_amount"])
        self.body_layout.addWidget(field("Amount received (Rs.)", self.amount))
        self.method = SearchCombo()
        self.method.setEditable(False)
        for val, text in [("CASH", "Cash"), ("BANK", "Bank transfer"), ("OTHER", "Other")]:
            self.method.addItem(text, val)
        self.body_layout.addWidget(field("Method", self.method))
        self.note = QTextEdit()
        self.note.setFixedHeight(50)
        self.body_layout.addWidget(field("Note", self.note))
        self.body_layout.addStretch(1)
        self.error_label = label("", "error", wrap=True)
        self.error_label.hide()
        self.pinned.addWidget(self.error_label)
        self.set_buttons("Record payment", "check").clicked.connect(self._submit)
        self.finish()

    def _submit(self):
        if not (0 < self.amount.value() <= self.target["remaining_amount"] + 0.01):
            self.error_label.setText(f"Enter an amount between 1 and Rs. {self.target['remaining_amount']:,.0f}.")
            self.error_label.show()
            return
        self.payload = dict(shopkeeper=self.shopkeeper_id, amount=self.amount.value(),
                            method=self.method.currentData(), note=self.note.toPlainText().strip())
        if self.is_laptop:
            self.payload["laptop_item"] = self.target["id"]
        else:
            self.payload["extra_money"] = self.target["id"]
        self.accept()


class ShopkeeperDetailDialog(GlassDialog):
    def __init__(self, parent, shopkeeper_id: int):
        self.shopkeeper_id = shopkeeper_id
        data = client.retrieve("shopkeepers/", shopkeeper_id)
        super().__init__(parent, data["name"], f"{data['reference_number']}  •  {data.get('phone', '')}", "store", 720)
        self.data = data

        top = QHBoxLayout()
        total = card(shadow=False)
        tl = QVBoxLayout(total)
        tl.setContentsMargins(16, 12, 16, 12)
        tl.addWidget(label("Total owed", "hint"))
        self.total_value = label(format_currency(data["remaining_amount"]), "h2")
        tl.addWidget(self.total_value)
        top.addWidget(total, 1)
        give = make_button("Give laptop", "laptop", "soft")
        give.clicked.connect(self._give_laptop)
        top.addWidget(give, 0, Qt.AlignmentFlag.AlignBottom)
        extra = make_button("Add extra money", "wallet", "soft")
        extra.clicked.connect(self._add_extra)
        top.addWidget(extra, 0, Qt.AlignmentFlag.AlignBottom)
        self.body_layout.addLayout(top)

        self.body_layout.addWidget(label("Laptops given", "h2"))
        self.laptop_table = QTableWidget(0, 4)
        self.laptop_table.setHorizontalHeaderLabels(["Laptop", "Price", "Remaining", ""])
        self._style_table(self.laptop_table)
        self.body_layout.addWidget(self.laptop_table)

        self.body_layout.addWidget(label("Extra money", "h2"))
        self.extra_table = QTableWidget(0, 4)
        self.extra_table.setHorizontalHeaderLabels(["Note", "Amount", "Remaining", ""])
        self._style_table(self.extra_table)
        self.body_layout.addWidget(self.extra_table)

        self.body_layout.addWidget(label("Payment history", "h2"))
        self.pay_table = QTableWidget(0, 4)
        self.pay_table.setHorizontalHeaderLabels(["Date", "Amount", "Method", "Note"])
        self._style_table(self.pay_table)
        self.body_layout.addWidget(self.pay_table)
        self.body_layout.addStretch(1)

        close = make_button("Close", "x")
        close.clicked.connect(self.accept)
        self.button_row.addStretch(1)
        self.button_row.addWidget(close)
        self._fill()
        self.finish()

    def _style_table(self, t: QTableWidget):
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t.verticalHeader().setVisible(False)
        t.verticalHeader().setDefaultSectionSize(46)   # tall enough for the "Pay" button; default row was too
        t.setShowGrid(False)                            # short and clipped/overlapped it into the row below.
        t.setAlternatingRowColors(True)
        t.setMinimumHeight(90)
        t.setMaximumHeight(180)
        t.horizontalHeader().setStretchLastSection(True)

    def _fill(self):
        self.data = client.retrieve("shopkeepers/", self.shopkeeper_id)
        d = self.data
        self.total_value.setText(format_currency(d["remaining_amount"]))

        self.laptop_table.setRowCount(len(d["laptops"]))
        for r, item in enumerate(d["laptops"]):
            self.laptop_table.setItem(r, 0, QTableWidgetItem(f"{item['brand']} {item['model_name']}"))
            self.laptop_table.setItem(r, 1, QTableWidgetItem(format_currency(item["price"])))
            self.laptop_table.setItem(r, 2, QTableWidgetItem(format_currency(item["remaining_amount"])))
            if item["is_cleared"]:
                self.laptop_table.setCellWidget(r, 3, self._pill_widget("Cleared", "ok"))
            else:
                self.laptop_table.setCellWidget(r, 3, self._pay_btn(item, True))

        self.extra_table.setRowCount(len(d["extra_money"]))
        for r, item in enumerate(d["extra_money"]):
            self.extra_table.setItem(r, 0, QTableWidgetItem(item.get("note") or "-"))
            self.extra_table.setItem(r, 1, QTableWidgetItem(format_currency(item["amount"])))
            self.extra_table.setItem(r, 2, QTableWidgetItem(format_currency(item["remaining_amount"])))
            if item["is_cleared"]:
                self.extra_table.setCellWidget(r, 3, self._pill_widget("Cleared", "ok"))
            else:
                self.extra_table.setCellWidget(r, 3, self._pay_btn(item, False))

        self.pay_table.setRowCount(len(d["payments"]))
        for r, p in enumerate(d["payments"]):
            self.pay_table.setItem(r, 0, QTableWidgetItem(format_date(p["payment_date"])))
            self.pay_table.setItem(r, 1, QTableWidgetItem(format_currency(p["amount"])))
            self.pay_table.setItem(r, 2, QTableWidgetItem(p["method"].title()))
            self.pay_table.setItem(r, 3, QTableWidgetItem(p.get("note") or ""))

        for t in (self.laptop_table, self.extra_table, self.pay_table):
            t.resizeRowsToContents()

    def _pill_widget(self, text, kind):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.addWidget(pill(text, kind))
        lay.addStretch(1)
        return w

    def _pay_btn(self, item, is_laptop):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(4, 2, 4, 2)
        btn = make_button("Pay", "cash", "soft")
        btn.clicked.connect(lambda _=False, it=item, lp=is_laptop: self._pay(it, lp))
        lay.addWidget(btn, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        lay.addStretch(1)          # keep the button its natural size instead of stretching
        return w                   # to fill the whole (auto-stretched) last column

    def _pay(self, target, is_laptop):
        dlg = PayDialog(self, self.shopkeeper_id, target, is_laptop)
        if dlg.exec():
            try:
                client.create("shopkeeper-payments/", dlg.payload)
                self._fill()
            except APIError as exc:
                show_error(self, "Could not save payment", exc.message)

    def _give_laptop(self):
        dlg = GiveLaptopDialog(self, self.shopkeeper_id)
        if dlg.exec():
            try:
                client.create("shopkeeper-laptops/", dlg.payload)
                self._fill()
            except APIError as exc:
                show_error(self, "Could not save", exc.message)

    def _add_extra(self):
        dlg = ExtraMoneyDialog(self, self.shopkeeper_id)
        if dlg.exec():
            try:
                client.create("shopkeeper-extra-money/", dlg.payload)
                self._fill()
            except APIError as exc:
                show_error(self, "Could not save", exc.message)


class ShopkeepersPage(EntityListPage):
    def __init__(self, can_edit: bool = True):
        columns = [
            ColumnSpec("reference_number", "Ref", compact=True),
            ColumnSpec("name", "Name"),
            ColumnSpec("phone", "Phone", compact=True),
            ColumnSpec("total_amount", "Total", formatter=format_currency, align_right=True, compact=True),
            ColumnSpec("remaining_amount", "Owed", formatter=format_currency, align_right=True, compact=True),
            ColumnSpec("", "Status", compact=True, pill_fn=_status_pill),
        ]
        super().__init__("Shopkeepers", "shopkeepers/", columns, FIELDS, icon_name="store", can_add=can_edit,
                         can_edit=can_edit, can_delete=can_edit, add_label="Add shopkeeper", entity_name="shopkeeper",
                         delete_warning="Any laptops still with them will be returned to stock.",
                         extra_actions=[RowAction("Open", self._open, "eye")])

    def _open(self, row):
        dlg = ShopkeeperDetailDialog(self, row["id"])
        dlg.exec()
        self.reload()
