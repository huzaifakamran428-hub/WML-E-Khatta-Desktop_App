"""Users: admin-only. Create / edit logins, activate, deactivate, reset password."""
from __future__ import annotations

from app.local_api import APIError, client
from app.ui.components import GlassDialog, MoneyEdit, ask_yes_no, field, label, make_button, show_error, show_info
from app.ui.widgets.crud import ColumnSpec, EntityListPage, FieldSpec, FormDialog, RowAction
from PyQt6.QtWidgets import QLineEdit

ROLE_CHOICES = [("ADMIN", "Administrator - full access"), ("READ_ONLY", "Read-only - view everything, change nothing"),
               ("SHOPKEEPER", "Shopkeeper login - limited")]

FIELDS = [
    FieldSpec("username", "Username", editable_on_update=False),
    FieldSpec("password", "Password", kind="password", editable_on_update=False,
              hint="They will use this to log in. They can change it later from Settings."),
    FieldSpec("first_name", "First name", required=False),
    FieldSpec("last_name", "Last name", required=False),
    FieldSpec("role", "Role", kind="choice", choices=ROLE_CHOICES),
    FieldSpec("phone_number", "Phone number", required=False),
]


def _role_pill(row):
    return {"ADMIN": ("Administrator", "info"), "READ_ONLY": ("Read-only", "muted"),
            "SHOPKEEPER": ("Shopkeeper", "warn")}.get(row.get("role"), ("-", "muted"))


def _status_pill(row):
    return ("Active", "ok") if row.get("is_active") else ("Deactivated", "bad")


class SetPasswordDialog(GlassDialog):
    def __init__(self, parent, user: dict):
        super().__init__(parent, f"Reset password for {user['username']}", "", "key", 440)
        self.user = user
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw.setPlaceholderText("At least 6 characters")
        self.body_layout.addWidget(field("New password", self.pw))
        self.body_layout.addStretch(1)
        self.error_label = label("", "error", wrap=True)
        self.error_label.hide()
        self.pinned.addWidget(self.error_label)
        self.set_buttons("Set password", "check").clicked.connect(self._submit)
        self.finish()

    def _submit(self):
        if len(self.pw.text()) < 6:
            self.error_label.setText("Password must be at least 6 characters.")
            self.error_label.show()
            return
        self.password = self.pw.text()
        self.accept()


class UsersPage(EntityListPage):
    def __init__(self):
        columns = [
            ColumnSpec("username", "Username"),
            ColumnSpec("", "Name", value_fn=lambda r: f"{r.get('first_name', '')} {r.get('last_name', '')}".strip() or "-"),
            ColumnSpec("", "Role", compact=True, pill_fn=_role_pill),
            ColumnSpec("phone_number", "Phone", compact=True),
            ColumnSpec("", "Status", compact=True, pill_fn=_status_pill),
        ]
        super().__init__("Users", "users/", columns, FIELDS, icon_name="shield", can_add=True, can_edit=True,
                         can_delete=False, add_label="Add user", entity_name="user", form_width=560,
                         extra_actions=[
                             RowAction("Reset password", self._reset_pw, "key"),
                             RowAction("Deactivate", self._deactivate, "x", "dangerSoft",
                                       visible=lambda r: r["is_active"]),
                             RowAction("Activate", self._activate, "check", "soft",
                                       visible=lambda r: not r["is_active"]),
                         ])

    def _reset_pw(self, row):
        dlg = SetPasswordDialog(self, row)
        if dlg.exec():
            try:
                client.post_json(f"users/{row['id']}/set-password/", {"password": dlg.password})
                show_info(self, "Password changed", f"{row['username']}'s password has been reset.")
            except APIError as exc:
                show_error(self, "Could not reset password", exc.message)

    def _deactivate(self, row):
        if ask_yes_no(self, "Deactivate user", f"Stop {row['username']} from logging in?"):
            try:
                client.post_json(f"users/{row['id']}/deactivate/", {})
                self.reload()
            except APIError as exc:
                show_error(self, "Could not deactivate", exc.message)

    def _activate(self, row):
        try:
            client.post_json(f"users/{row['id']}/activate/", {})
            self.reload()
        except APIError as exc:
            show_error(self, "Could not activate", exc.message)
