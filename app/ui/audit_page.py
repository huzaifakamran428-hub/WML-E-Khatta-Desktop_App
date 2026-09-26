"""Audit log: read-only history of every change, admin only."""
from __future__ import annotations
from app.ui.widgets.crud import ColumnSpec, EntityListPage
from app.utils.formatting import format_date

class AuditLogPage(EntityListPage):
    def __init__(self):
        columns = [
            ColumnSpec("timestamp", "When", formatter=lambda v: format_date(v, "%d %b %Y, %I:%M %p"), compact=True),
            ColumnSpec("user_display", "Who", compact=True),
            ColumnSpec("action", "Action", compact=True),
            ColumnSpec("entity", "On", compact=True),
            ColumnSpec("detail", "Detail"),
        ]
        super().__init__("Audit Log", "audit-logs/", columns, [], icon_name="clipboard", can_add=False,
                         can_edit=False, can_delete=False, entity_name="entry")
