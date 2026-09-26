"""Inventory: laptops in stock. Purchase price is only ever shown in Edit."""
from __future__ import annotations

import os

from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QTextEdit, QVBoxLayout, QWidget

from app import csv_import
from app.local_api import APIError, client
from app.ui.components import GlassDialog, card, label, make_button, show_error, show_info
from app.ui.theme import C
from app.ui.widgets.crud import ColumnSpec, EntityListPage, FieldSpec
from app.utils.formatting import format_currency

CONDITIONS = [("NEW", "New"), ("USED", "Used"), ("REFURBISHED", "Refurbished")]

BASE_FIELDS = [
    FieldSpec("brand", "Brand", section="Laptop"),
    FieldSpec("model_name", "Model"),
    FieldSpec("generation", "Generation", required=False),
    FieldSpec("processor", "Processor", required=False),
    FieldSpec("cpu_cores", "CPU cores", kind="int", required=False),
    FieldSpec("ram", "RAM", required=False, default="8 GB"),
    FieldSpec("storage", "Storage", required=False, default="256 GB SSD"),
    FieldSpec("gpu", "Graphics", required=False),
    FieldSpec("screen_size", "Screen size", required=False, default='14"'),
    FieldSpec("condition", "Condition", kind="choice", choices=CONDITIONS, required=False, default="NEW"),
    FieldSpec("serial_number", "Serial number", required=False),
]
PRICE_FIELDS = [
    FieldSpec("purchase_price", "Purchase price (Rs.)", kind="decimal", required=False, section="Pricing & stock",
              hint="Only admins can see this. It is never shown to other logins or printed on bills."),
    FieldSpec("sale_price", "Sale price (Rs.)", kind="decimal"),
    FieldSpec("discount_amount", "Standing discount (Rs.)", kind="decimal", required=False,
              hint="Optional default discount for this laptop. You can still change it per sale."),
    FieldSpec("discount_percent", "or discount (%)", kind="decimal", required=False),
    FieldSpec("quantity", "Quantity in stock", kind="int", required=False, default=1),
    FieldSpec("supplier", "Supplier", required=False),
    FieldSpec("purchase_date", "Purchase date", kind="date", required=False),
    FieldSpec("warranty", "Warranty", required=False),
]
EXTRA_FIELDS = [
    FieldSpec("notes", "Notes", kind="multiline", required=False, section="Notes"),
    FieldSpec("is_archived", "Archived (hide from sale, keep the record)", kind="bool", required=False),
]


def _stock_pill(row):
    if row.get("is_archived"):
        return ("Archived", "muted")
    if row.get("is_out_of_stock"):
        return ("Out of stock", "bad")
    if row.get("is_low_stock"):
        return ("Low stock", "warn")
    return ("In stock", "ok")


class CsvImportDialog(GlassDialog):
    def __init__(self, parent):
        super().__init__(parent, "Import laptops from CSV", "Add many laptops at once from a spreadsheet file.",
                          "upload", width=640)
        intro = label("Pick a CSV file exported from Excel or Google Sheets. The first row must be column "
                      "headings such as Brand, Model, RAM, Storage, Purchase Price, Sale Price, Quantity...",
                      "sub", wrap=True)
        self.body_layout.addWidget(intro)

        row = QHBoxLayout()
        choose = make_button("Choose CSV file...", "file", "primary")
        choose.clicked.connect(self._choose)
        row.addWidget(choose)
        template = make_button("Download CSV template", "download")
        template.clicked.connect(self._template)
        row.addWidget(template)
        row.addStretch(1)
        self.body_layout.addLayout(row)

        self.path_label = label("No file chosen yet.", "hint")
        self.body_layout.addWidget(self.path_label)

        self.preview_box = QTextEdit()
        self.preview_box.setReadOnly(True)
        self.preview_box.setFixedHeight(190)
        self.preview_box.setVisible(False)
        self.body_layout.addWidget(self.preview_box)
        self.body_layout.addStretch(1)

        self.rows: list[dict] = []
        self.ok = self.set_buttons("Add to inventory", "upload")
        self.ok.setEnabled(False)
        self.ok.clicked.connect(self._confirm)
        self.finish()

    def _template(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save CSV template", "WML_inventory_template.csv", "CSV files (*.csv)")
        if path:
            csv_import.write_template(path)
            show_info(self, "Template saved", f"Saved to:\n{path}")

    def _choose(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose CSV file", "", "CSV files (*.csv);;All files (*)")
        if not path:
            return
        self.path_label.setText(os.path.basename(path))
        try:
            preview = csv_import.read_csv(path)
        except ValueError as exc:
            self.rows = []
            self.ok.setEnabled(False)
            self.preview_box.setVisible(True)
            self.preview_box.setPlainText(str(exc))
            return
        self.rows = preview.rows
        lines = [f"Found {preview.total} row(s); {len(preview.rows)} ready to import."]
        if preview.skipped:
            lines.append(f"\n{len(preview.skipped)} row(s) will be skipped:")
            lines += [f"  Row {s['row']}: {s['reason']}" for s in preview.skipped[:12]]
        if preview.no_price:
            lines.append(f"\n{preview.no_price} row(s) have no sale price - you can set it later in Edit.")
        if preview.ignored_headers:
            lines.append(f"\nColumns not recognised (ignored): {', '.join(preview.ignored_headers)}")
        self.preview_box.setVisible(True)
        self.preview_box.setPlainText("\n".join(lines))
        self.ok.setEnabled(bool(self.rows))

    def _confirm(self):
        self.accept()


class InventoryPage(EntityListPage):
    def __init__(self, can_edit: bool = True):
        columns = [
            ColumnSpec("brand", "Brand", compact=True),
            ColumnSpec("model_name", "Model"),
            ColumnSpec("", "Specs", value_fn=lambda r: ", ".join(
                p for p in (r.get("ram"), r.get("storage"), r.get("processor")) if p)),
            ColumnSpec("condition", "Condition", compact=True, value_fn=lambda r: r.get("condition", "").title()),
            ColumnSpec("sale_price", "Sale price", formatter=format_currency, align_right=True, compact=True),
            ColumnSpec("quantity", "Qty", compact=True, align_right=True),
            ColumnSpec("", "Status", compact=True, pill_fn=_stock_pill),
        ]
        fields = BASE_FIELDS + (PRICE_FIELDS if can_edit else PRICE_FIELDS[1:]) + EXTRA_FIELDS
        if not can_edit:
            fields = [f for f in fields if f.name != "purchase_price"]
        import_btn = None
        if can_edit:
            import_btn = make_button("Import CSV", "upload")
        super().__init__("Inventory", "laptops/", columns, fields, subtitle="", icon_name="laptop",
                         can_add=can_edit, can_edit=can_edit, can_delete=can_edit, add_label="Add laptop",
                         entity_name="laptop", form_width=680,
                         delete_warning="If this laptop has ever been sold or given to a shopkeeper, it can't be "
                                        "deleted - tick 'Archived' in Edit to hide it instead.",
                         header_widgets=[import_btn] if import_btn else None)
        if import_btn:
            import_btn.clicked.connect(self._import_csv)

    def _import_csv(self):
        dlg = CsvImportDialog(self)
        if dlg.exec() and dlg.rows:
            try:
                result = client.post_json("laptops/bulk-import/", {"rows": dlg.rows})
            except APIError as exc:
                show_error(self, "Import failed", exc.message)
                return
            self.reload()
            msg = f"Added {result['created']} laptop(s) to inventory."
            if result["skipped"]:
                msg += "\n\nSkipped:\n" + "\n".join(f"Row {s['row']}: {s['reason']}" for s in result["skipped"][:15])
            show_info(self, "Import complete", msg)
