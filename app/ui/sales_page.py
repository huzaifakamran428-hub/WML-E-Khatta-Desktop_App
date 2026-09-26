"""
Sales: New Sale (with live totals) and the sales history list.

The New Sale form recalculates the amount to receive on every keystroke -
subtotal, discount, final total and what is still owed - so you always see
the correct number before typing what was actually received. No more
working it out by hand.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QTextEdit, QVBoxLayout, QWidget

from app.local_api import APIError, client
from app.calc import sale_totals
from app.ui.components import (
    GlassDialog, IntEdit, MoneyEdit, SearchCombo, card, field, label, make_button, pill, show_error, show_info,
)
from app.ui.theme import C, icon
from app.ui.widgets.crud import ColumnSpec, EntityListPage, FormDialog
from app.utils import bill_pdf
from app.utils.formatting import format_currency, format_date

PAYMENT_TYPES = [("CASH", "Cash"), ("BANK", "Bank transfer"), ("OTHER", "Other")]


def _status_pill(row):
    return {"PAID": ("Paid", "ok"), "PARTIAL": ("Partial", "warn"), "UNPAID": ("Unpaid", "bad")}.get(
        row.get("payment_status"), ("-", "muted"))


class NewSaleDialog(GlassDialog):
    def __init__(self, parent):
        super().__init__(parent, "New sale", "Pick the customer and laptop - the total updates as you go.",
                         "receipt", width=620)
        self.laptops: dict[int, dict] = {}

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(12)

        self.customer = SearchCombo()
        self._load_customers()
        cust_row = QHBoxLayout()
        cust_row.setSpacing(8)
        cust_row.addWidget(self.customer, 1)
        add_customer = make_button("", "plus", "soft", "Add a new customer")
        add_customer.clicked.connect(self._add_customer)
        cust_row.addWidget(add_customer, 0)
        cust_wrap = QWidget()
        cust_wrap.setLayout(cust_row)
        grid.addWidget(field("Customer *", cust_wrap), 0, 0, 1, 2)

        self.laptop = SearchCombo()
        self._load_laptops()
        self.laptop.currentIndexChanged.connect(self._laptop_changed)
        self.laptop.activated.connect(self._laptop_changed)
        grid.addWidget(field("Laptop *", self.laptop), 1, 0, 1, 2)

        self.qty = IntEdit(maximum=999, placeholder="1")
        self.qty.setValue(1)
        self.qty.valueChanged.connect(self._recalc)
        grid.addWidget(field("Quantity", self.qty), 2, 0)

        self.price = MoneyEdit()
        self.price.valueChanged.connect(self._recalc)
        grid.addWidget(field("Sale price (Rs.) *", self.price, "Per laptop. Filled in automatically; you can change it."), 2, 1)

        self.discount_amount = MoneyEdit(placeholder="0")
        self.discount_amount.valueChanged.connect(lambda v: self._discount_edited("amount"))
        grid.addWidget(field("Discount (Rs.)", self.discount_amount), 3, 0)

        self.discount_percent = MoneyEdit(placeholder="0")
        self.discount_percent.valueChanged.connect(lambda v: self._discount_edited("percent"))
        grid.addWidget(field("or discount (%)", self.discount_percent, "Use either the rupee amount or the percentage."), 3, 1)

        self.payment_type = SearchCombo()
        self.payment_type.setEditable(False)
        for val, text in PAYMENT_TYPES:
            self.payment_type.addItem(text, val)
        grid.addWidget(field("Payment method", self.payment_type), 4, 0)

        self.received = MoneyEdit(placeholder="0")
        self.received.valueChanged.connect(self._recalc)
        grid.addWidget(field("Amount received now (Rs.)", self.received,
                             "Leave at 0 for fully on credit."), 4, 1)

        self.notes = QTextEdit()
        self.notes.setFixedHeight(60)
        grid.addWidget(field("Notes", self.notes), 5, 0, 1, 2)
        self.body_layout.addLayout(grid)
        self.body_layout.addStretch(1)

        # ---- always-visible live total (never scrolls out of view) ----
        summary = QFrame()
        summary.setObjectName("summary")
        sl = QVBoxLayout(summary)
        sl.setContentsMargins(18, 14, 18, 14)
        sl.setSpacing(6)
        self.row_subtotal = self._summary_row(sl, "Subtotal")
        self.row_discount = self._summary_row(sl, "Discount")
        line = QFrame()
        line.setObjectName("divider")
        sl.addWidget(line)
        total_row = QHBoxLayout()
        total_row.addWidget(label("Total to receive", "h2"))
        total_row.addStretch(1)
        self.total_value = label("Rs. 0", "bigTotal")
        total_row.addWidget(self.total_value)
        sl.addLayout(total_row)
        self.row_remaining = self._summary_row(sl, "Still owed after this payment")
        self.pinned.addWidget(summary)

        self.error_label = label("", "error", wrap=True)
        self.error_label.hide()
        self.pinned.addWidget(self.error_label)

        self.ok = self.set_buttons("Complete sale", "check")
        self.ok.clicked.connect(self._submit)
        self.finish()
        self._laptop_changed()          # pre-fill price for whichever laptop is selected first

    def _summary_row(self, layout: QVBoxLayout, text: str) -> QLabel:
        row = QHBoxLayout()
        row.addWidget(label(text, "sub"))
        row.addStretch(1)
        value = label("Rs. 0", "sub")
        value.setStyleSheet("font-weight: 700; color: %s;" % C["ink"])
        row.addWidget(value)
        layout.addLayout(row)
        return value

    def _load_customers(self):
        try:
            for c in client.list_("customers/"):
                self.customer.addItem(f"{c['name']}" + (f" - {c['phone']}" if c.get("phone") else ""), c["id"])
        except APIError:
            pass

    def _add_customer(self):
        from app.ui.customers_page import FIELDS as CUSTOMER_FIELDS
        dlg = FormDialog(self, "Add customer", CUSTOMER_FIELDS, {}, False, icon_name="plus", width=480, ok_text="Save")
        if not dlg.exec():
            return
        try:
            customer = client.create("customers/", dlg.get_data())
        except APIError as exc:
            show_error(self, "Could not save customer", exc.message)
            return
        text = customer["name"] + (f" - {customer['phone']}" if customer.get("phone") else "")
        self.customer.addItem(text, customer["id"])
        self.customer.select_data(customer["id"])

    def _load_laptops(self):
        try:
            for l in client.list_("laptops/"):
                if l.get("is_archived") or l["quantity"] <= 0:
                    continue
                self.laptops[l["id"]] = l
                specs = ", ".join(p for p in (l.get("ram"), l.get("storage")) if p)
                text = f"{l['brand']} {l['model_name']}" + (f" ({specs})" if specs else "") + f" - {l['quantity']} in stock"
                self.laptop.addItem(text, l["id"])
        except APIError:
            pass

    def _laptop_changed(self):
        lap = self.laptops.get(self.laptop.currentData())
        if lap:
            self.price.setValue(lap["sale_price"])
            self.qty.setValue(1)
            if lap["discount_amount"]:
                self.discount_amount.setValue(lap["discount_amount"])
                self.discount_percent.setValue(0)
            elif lap["discount_percent"]:
                self.discount_percent.setValue(lap["discount_percent"])
                self.discount_amount.setValue(0)
        self._recalc()

    def _discount_edited(self, which: str):
        """Rupee discount and percent discount are mutually exclusive - filling one clears the other."""
        if which == "amount" and self.discount_amount.value() > 0:
            self.discount_percent.blockSignals(True)
            self.discount_percent.setValue(0)
            self.discount_percent.blockSignals(False)
        elif which == "percent" and self.discount_percent.value() > 0:
            self.discount_amount.blockSignals(True)
            self.discount_amount.setValue(0)
            self.discount_amount.blockSignals(False)
        self._recalc()

    def _recalc(self):
        price, qty = self.price.value(), max(self.qty.value(), 1)
        t = sale_totals(price, qty, self.discount_amount.value(), self.discount_percent.value(), self.received.value())
        self.row_subtotal.setText(format_currency(t["subtotal"]))
        self.row_discount.setText(("- " if t["discount_total"] else "") + format_currency(t["discount_total"]))
        self.total_value.setText(format_currency(t["final_total"]))
        self.row_remaining.setText(format_currency(t["remaining_amount"]))
        self.row_remaining.setStyleSheet("font-weight: 700; color: %s;" % (C["danger"] if t["remaining_amount"] else C["green_dark"]))
        return t

    def _submit(self):
        self.error_label.hide()
        if not self.customer.has_valid_choice():
            return self._fail("Please choose a customer.")
        if not self.laptop.has_valid_choice():
            return self._fail("Please choose a laptop.")
        if self.price.value() <= 0:
            return self._fail("Sale price must be more than 0.")
        self.payload = dict(
            customer=self.customer.currentData(), laptop_id=self.laptop.currentData(), quantity=self.qty.value(),
            sale_price=self.price.value(), discount_amount=self.discount_amount.value(),
            discount_percent=self.discount_percent.value(), payment_type=self.payment_type.currentData(),
            amount_received=self.received.value(), notes=self.notes.toPlainText().strip())
        self.accept()

    def _fail(self, text: str):
        self.error_label.setText(text)
        self.error_label.show()


class EditSaleDialog(GlassDialog):
    """Edit an existing bill. The customer and laptop can't be changed here --
    delete the sale and make a new one for that. Everything else (quantity,
    price, discount, payment method, amount received, notes) can be."""

    def __init__(self, parent, sale: dict):
        super().__init__(parent, f"Edit bill - {sale['receipt_no']}",
                         "Quantity, price, discount, payment and notes can be changed. "
                         "To change the customer or laptop, delete this sale and create a new one.",
                         "edit", width=620)
        self.sale = sale

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(12)

        laptop_name = sale["items"][0]["product_display"] if sale.get("items") else ""
        info = label(f"{sale.get('customer_name', '')}  -  {laptop_name}", "sub", wrap=True)
        grid.addWidget(info, 0, 0, 1, 2)

        self.qty = IntEdit(maximum=999, placeholder="1")
        self.qty.setValue(sale["quantity"])
        self.qty.valueChanged.connect(self._recalc)
        grid.addWidget(field("Quantity", self.qty), 1, 0)

        self.price = MoneyEdit()
        self.price.setValue(sale["sale_price"])
        self.price.valueChanged.connect(self._recalc)
        grid.addWidget(field("Sale price (Rs.) *", self.price), 1, 1)

        self.discount_amount = MoneyEdit(placeholder="0")
        self.discount_amount.setValue(sale["discount_amount"])
        self.discount_amount.valueChanged.connect(lambda v: self._discount_edited("amount"))
        grid.addWidget(field("Discount (Rs.)", self.discount_amount), 2, 0)

        self.discount_percent = MoneyEdit(placeholder="0")
        self.discount_percent.setValue(sale["discount_percent"])
        self.discount_percent.valueChanged.connect(lambda v: self._discount_edited("percent"))
        grid.addWidget(field("or discount (%)", self.discount_percent,
                             "Use either the rupee amount or the percentage."), 2, 1)

        self.payment_type = SearchCombo()
        self.payment_type.setEditable(False)
        for val, text in PAYMENT_TYPES:
            self.payment_type.addItem(text, val)
        idx = self.payment_type.findData(sale.get("payment_type", "CASH"))
        if idx >= 0:
            self.payment_type.setCurrentIndex(idx)
        grid.addWidget(field("Payment method", self.payment_type), 3, 0)

        self.received = MoneyEdit(placeholder="0")
        self.received.setValue(sale["amount_received"])
        self.received.valueChanged.connect(self._recalc)
        grid.addWidget(field("Amount received so far (Rs.)", self.received), 3, 1)

        self.notes = QTextEdit()
        self.notes.setFixedHeight(60)
        self.notes.setPlainText(sale.get("notes", ""))
        grid.addWidget(field("Notes", self.notes), 4, 0, 1, 2)
        self.body_layout.addLayout(grid)
        self.body_layout.addStretch(1)

        summary = QFrame()
        summary.setObjectName("summary")
        sl = QVBoxLayout(summary)
        sl.setContentsMargins(18, 14, 18, 14)
        sl.setSpacing(6)
        self.row_subtotal = self._summary_row(sl, "Subtotal")
        self.row_discount = self._summary_row(sl, "Discount")
        line = QFrame()
        line.setObjectName("divider")
        sl.addWidget(line)
        total_row = QHBoxLayout()
        total_row.addWidget(label("Total", "h2"))
        total_row.addStretch(1)
        self.total_value = label("Rs. 0", "bigTotal")
        total_row.addWidget(self.total_value)
        sl.addLayout(total_row)
        self.row_remaining = self._summary_row(sl, "Still owed")
        self.pinned.addWidget(summary)

        self.error_label = label("", "error", wrap=True)
        self.error_label.hide()
        self.pinned.addWidget(self.error_label)

        self.ok = self.set_buttons("Save changes", "check")
        self.ok.clicked.connect(self._submit)
        self.finish()
        self._recalc()

    def _summary_row(self, layout: QVBoxLayout, text: str) -> QLabel:
        row = QHBoxLayout()
        row.addWidget(label(text, "sub"))
        row.addStretch(1)
        value = label("Rs. 0", "sub")
        value.setStyleSheet("font-weight: 700; color: %s;" % C["ink"])
        row.addWidget(value)
        layout.addLayout(row)
        return value

    def _discount_edited(self, which: str):
        if which == "amount" and self.discount_amount.value() > 0:
            self.discount_percent.blockSignals(True)
            self.discount_percent.setValue(0)
            self.discount_percent.blockSignals(False)
        elif which == "percent" and self.discount_percent.value() > 0:
            self.discount_amount.blockSignals(True)
            self.discount_amount.setValue(0)
            self.discount_amount.blockSignals(False)
        self._recalc()

    def _recalc(self):
        price, qty = self.price.value(), max(self.qty.value(), 1)
        t = sale_totals(price, qty, self.discount_amount.value(), self.discount_percent.value(), self.received.value())
        self.row_subtotal.setText(format_currency(t["subtotal"]))
        self.row_discount.setText(("- " if t["discount_total"] else "") + format_currency(t["discount_total"]))
        self.total_value.setText(format_currency(t["final_total"]))
        self.row_remaining.setText(format_currency(t["remaining_amount"]))
        self.row_remaining.setStyleSheet("font-weight: 700; color: %s;" % (C["danger"] if t["remaining_amount"] else C["green_dark"]))
        return t

    def _submit(self):
        self.error_label.hide()
        if self.price.value() <= 0:
            return self._fail("Sale price must be more than 0.")
        if self.qty.value() < 1:
            return self._fail("Quantity must be at least 1.")
        self.payload = dict(
            quantity=self.qty.value(), sale_price=self.price.value(),
            discount_amount=self.discount_amount.value(), discount_percent=self.discount_percent.value(),
            payment_type=self.payment_type.currentData(), amount_received=self.received.value(),
            notes=self.notes.toPlainText().strip())
        self.accept()

    def _fail(self, text: str):
        self.error_label.setText(text)
        self.error_label.show()


class SalesPage(EntityListPage):
    def __init__(self, can_edit: bool = True):
        columns = [
            ColumnSpec("receipt_no", "Receipt", compact=True),
            ColumnSpec("customer_name", "Customer"),
            ColumnSpec("", "Laptop", value_fn=lambda r: r["items"][0]["product_display"] if r.get("items") else ""),
            ColumnSpec("final_total", "Total", formatter=format_currency, align_right=True, compact=True),
            ColumnSpec("remaining_amount", "Owed", formatter=format_currency, align_right=True, compact=True),
            ColumnSpec("", "Status", compact=True, pill_fn=_status_pill),
            ColumnSpec("sale_date", "Date", formatter=format_date, compact=True),
        ]
        from app.ui.widgets.crud import RowAction
        super().__init__("Sales", "sales/", columns, [], icon_name="receipt", can_add=can_edit, can_edit=can_edit,
                         can_delete=can_edit, add_label="New sale", entity_name="sale",
                         delete_warning="The laptop will be put back into stock.",
                         extra_actions=[RowAction("Bill", self._print, "printer")])

    def _on_edit(self, row: dict):
        try:
            sale = client.retrieve(self.endpoint, row["id"])
        except APIError as exc:
            show_error(self, "Could not open bill", exc.message)
            return
        dlg = EditSaleDialog(self, sale)
        if dlg.exec():
            try:
                client.update(self.endpoint, row["id"], dlg.payload)
            except APIError as exc:
                show_error(self, "Could not save changes", exc.message)
                return
            self.reload()

    def _on_add(self):
        dlg = NewSaleDialog(self)
        if dlg.exec():
            try:
                sale = client.create("sales/", dlg.payload)
            except APIError as exc:
                show_error(self, "Could not complete sale", exc.message)
                return
            self.reload()
            show_info(self, "Sale complete", f"Receipt {sale['receipt_no']} - {format_currency(sale['final_total'])}.")
            self._print(sale)

    def _print(self, row: dict):
        try:
            sale = client.retrieve("sales/", row["id"])
            store = client.get_json("store-settings/")
        except APIError as exc:
            show_error(self, "Could not open bill", exc.message)
            return
        default_name = f"Bill_{sale['receipt_no']}.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "Save bill", default_name, "PDF files (*.pdf)")
        if not path:
            return
        try:
            bill_pdf.generate_bill(sale, store, path)
        except OSError as exc:
            show_error(self, "Could not save bill", str(exc))
            return
        show_info(self, "Bill saved", f"Saved to:\n{path}")
