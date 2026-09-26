from __future__ import annotations
from app.ui.widgets.crud import ColumnSpec, EntityListPage, FieldSpec

FIELDS = [
    FieldSpec("name", "Full name"),
    FieldSpec("phone", "Phone number", required=False),
    FieldSpec("address", "Address", required=False, kind="multiline"),
    FieldSpec("notes", "Notes", required=False, kind="multiline"),
]

class CustomersPage(EntityListPage):
    def __init__(self, can_edit: bool = True):
        columns = [
            ColumnSpec("name", "Name"),
            ColumnSpec("phone", "Phone", compact=True),
            ColumnSpec("address", "Address"),
        ]
        super().__init__("Customers", "customers/", columns, FIELDS, icon_name="customers",
                         can_add=can_edit, can_edit=can_edit, can_delete=can_edit, add_label="Add customer",
                         entity_name="customer",
                         delete_warning="Customers with sales or credit plans can't be deleted.")
