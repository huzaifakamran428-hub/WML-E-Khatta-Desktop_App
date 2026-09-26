"""Credit plans: instalment sales for customers, with a quick 'record payment' action."""
from __future__ import annotations

from PyQt6.QtWidgets import QTextEdit

from app.local_api import APIError, client
from app.ui.components import GlassDialog, MoneyEdit, SearchCombo, field, label, make_button, show_error
from app.ui.widgets.crud import ColumnSpec, EntityListPage, FieldSpec, RowAction
from app.utils.formatting import format_currency, format_date


def _status_pill(row):
    if row.get("status") == "CLEARED":
        return ("Cleared", "ok")
    return ("Overdue", "bad") if row.get("is_overdue") else ("Active", "warn")


class RecordPaymentDialog(GlassDialog):
    def __init__(self, parent, plan: dict):
        super().__init__(parent, "Record payment", f"{plan['person_name']} - {format_currency(plan['remaining_amount'])} remaining.",
                         "cash", 480)
        self.plan = plan
        self.amount = MoneyEdit()
        self.amount.setValue(plan["remaining_amount"])
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
        if not (0 < self.amount.value() <= self.plan["remaining_amount"] + 0.01):
            self.error_label.setText(f"Enter an amount between 1 and {format_currency(self.plan['remaining_amount'])}.")
            self.error_label.show()
            return
        self.payload = dict(credit_plan=self.plan["id"], amount=self.amount.value(),
                            method=self.method.currentData(), note=self.note.toPlainText().strip())
        self.accept()


class CreditPlansPage(EntityListPage):
    def __init__(self, can_edit: bool = True):
        columns = [
            ColumnSpec("person_name", "Customer"),
            ColumnSpec("laptop_name", "Laptop"),
            ColumnSpec("total_amount", "Total", formatter=format_currency, align_right=True, compact=True),
            ColumnSpec("remaining_amount", "Remaining", formatter=format_currency, align_right=True, compact=True),
            ColumnSpec("due_date", "Due", formatter=format_date, compact=True),
            ColumnSpec("", "Status", compact=True, pill_fn=_status_pill),
        ]
        fields = [
            FieldSpec("customer", "Customer", kind="fk", fk_loader=lambda: client.list_("customers/")),
            FieldSpec("laptop", "Laptop (optional)", kind="fk", required=False,
                      fk_loader=lambda: [l for l in client.list_("laptops/") if not l.get("is_archived")],
                      fk_display="model_name"),
            FieldSpec("total_amount", "Total amount (Rs.)", kind="decimal"),
            FieldSpec("down_payment", "Down payment (Rs.)", kind="decimal", required=False),
            FieldSpec("installment_amount", "Instalment amount (Rs.)", kind="decimal", required=False),
            FieldSpec("due_date", "Next due date", kind="date"),
            FieldSpec("notes", "Notes", required=False, kind="multiline"),
        ]
        super().__init__("Credit Plans", "credit-plans/", columns, fields, icon_name="card", can_add=can_edit,
                         can_edit=can_edit, can_delete=can_edit, add_label="New credit plan", entity_name="credit plan",
                         extra_actions=[RowAction("Pay", self._pay, "cash", visible=lambda r: r["status"] != "CLEARED")])

    def _pay(self, row):
        dlg = RecordPaymentDialog(self, row)
        if dlg.exec():
            try:
                client.create("payments/", dlg.payload)
                self.reload()
            except APIError as exc:
                show_error(self, "Could not save payment", exc.message)
