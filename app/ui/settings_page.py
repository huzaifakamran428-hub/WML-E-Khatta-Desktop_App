"""
Settings: store profile, my password, alert toggles (admin) and the Google
Drive backup / restore panel.
"""
from __future__ import annotations

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QCheckBox, QFileDialog, QGridLayout, QHBoxLayout, QLineEdit, QTextEdit, QVBoxLayout, QWidget

from app import config
from app.drive_backup import BackupError
from app.local_api import APIError, client
from app.ui.components import (
    IntEdit, PageHeader, ask_yes_no, card, divider, field, label, make_button, pill, show_error, show_info,
)
from app.ui.theme import C, icon


class ChangePasswordCard(QWidget):
    def __init__(self):
        super().__init__()
        box = card()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(box)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(22, 20, 22, 20)
        lay.setSpacing(12)
        lay.addWidget(label("My password", "h2"))
        lay.addWidget(label("Change the password for your own login.", "sub"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        self.current = QLineEdit()
        self.current.setEchoMode(QLineEdit.EchoMode.Password)
        grid.addWidget(field("Current password", self.current), 0, 0)
        self.new = QLineEdit()
        self.new.setEchoMode(QLineEdit.EchoMode.Password)
        self.new.setPlaceholderText("At least 6 characters")
        grid.addWidget(field("New password", self.new), 0, 1)
        lay.addLayout(grid)
        self.error = label("", "error", wrap=True)
        self.error.hide()
        lay.addWidget(self.error)
        row = QHBoxLayout()
        row.addStretch(1)
        btn = make_button("Change password", "key", "primary")
        btn.clicked.connect(self._submit)
        row.addWidget(btn)
        lay.addLayout(row)

    def _submit(self):
        if not self.current.text() or len(self.new.text()) < 6:
            self.error.setText("Enter your current password and a new one of at least 6 characters.")
            self.error.show()
            return
        try:
            client.post_json("users/me/change-password/", {"current_password": self.current.text(),
                                                            "new_password": self.new.text()})
        except APIError as exc:
            self.error.setText(exc.message)
            self.error.show()
            return
        self.current.clear()
        self.new.clear()
        self.error.hide()
        show_info(self, "Password changed", "Your password has been updated. Use it next time you log in.")


class StoreProfileCard(QWidget):
    def __init__(self):
        super().__init__()
        box = card()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(box)
        self.lay = QVBoxLayout(box)
        self.lay.setContentsMargins(22, 20, 22, 20)
        self.lay.setSpacing(12)
        self.lay.addWidget(label("Store profile", "h2"))
        self.lay.addWidget(label("Shown on every printed bill.", "sub"))
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(10)
        self.lay.addLayout(self.grid)

        self.inputs = {}
        rows = [("store_name", "Store name", QLineEdit), ("phone_number", "Phone number", QLineEdit),
               ("ceo_name", "Owner / CEO name", QLineEdit), ("ceo_contact_number", "Owner contact number", QLineEdit)]
        for i, (key, text, cls) in enumerate(rows):
            w = cls()
            self.inputs[key] = w
            self.grid.addWidget(field(text, w), i // 2, i % 2)
        addr = QTextEdit()
        addr.setFixedHeight(56)
        self.inputs["address"] = addr
        self.grid.addWidget(field("Address", addr), 2, 0, 1, 2)
        thanks = QLineEdit()
        self.inputs["thank_you_message"] = thanks
        self.grid.addWidget(field("Thank-you message on bill", thanks), 3, 0, 1, 2)

        self.lay.addWidget(divider())
        self.lay.addWidget(label("Alerts", "h2"))
        self.low_stock_cb = QCheckBox("Warn about low stock")
        self.due_today_cb = QCheckBox("Remind when a payment is due today")
        self.due_soon_cb = QCheckBox("Remind 2 days before a payment is due")
        for cb in (self.low_stock_cb, self.due_today_cb, self.due_soon_cb):
            self.lay.addWidget(cb)
        self.threshold = IntEdit(maximum=999, placeholder="2")
        self.lay.addWidget(field("Low stock threshold (units left)", self.threshold))

        row = QHBoxLayout()
        row.addStretch(1)
        save = make_button("Save store settings", "check", "primary")
        save.clicked.connect(self._save)
        row.addWidget(save)
        self.lay.addLayout(row)
        self.reload()

    def reload(self):
        try:
            data = client.get_json("store-settings/")
        except APIError:
            return
        for key, w in self.inputs.items():
            value = data.get(key, "")
            w.setPlainText(value) if isinstance(w, QTextEdit) else w.setText(value)
        self.low_stock_cb.setChecked(data.get("low_stock_alerts_enabled", True))
        self.due_today_cb.setChecked(data.get("due_today_reminder_enabled", True))
        self.due_soon_cb.setChecked(data.get("two_day_reminder_enabled", True))
        self.threshold.setValue(data.get("low_stock_threshold", 2))

    def _save(self):
        payload = {k: (w.toPlainText().strip() if isinstance(w, QTextEdit) else w.text().strip())
                  for k, w in self.inputs.items()}
        payload["low_stock_alerts_enabled"] = self.low_stock_cb.isChecked()
        payload["due_today_reminder_enabled"] = self.due_today_cb.isChecked()
        payload["two_day_reminder_enabled"] = self.due_soon_cb.isChecked()
        try:
            client.patch_json("store-settings/", payload)
            show_info(self, "Saved", "Store settings have been saved.")
        except APIError as exc:
            show_error(self, "Could not save", exc.message)


STATE_LABEL = {"off": "Not connected", "idle": "Connected - waiting for changes", "pending": "Backup queued...",
              "running": "Backing up now...", "ok": "Backed up", "error": "Backup failed"}
STATE_KIND = {"off": "muted", "idle": "ok", "pending": "warn", "running": "info", "ok": "ok", "error": "bad"}


class DriveBackupCard(QWidget):
    def __init__(self, backup):
        super().__init__()
        self.backup = backup
        box = card()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(box)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(22, 20, 22, 20)
        lay.setSpacing(12)
        lay.addWidget(label("Google Drive backup", "h2"))
        lay.addWidget(label("Your data is backed up to your own Google Drive automatically every time you add "
                            "or change something, so you can restore it on any computer.", "sub", wrap=True))

        status_row = QHBoxLayout()
        self.status_pill = pill("", "muted")
        status_row.addWidget(self.status_pill)
        self.status_text = label("", "sub")
        status_row.addWidget(self.status_text)
        status_row.addStretch(1)
        lay.addLayout(status_row)

        self.auto_cb = QCheckBox("Automatically back up after every change")
        self.auto_cb.stateChanged.connect(self._toggle_auto)
        lay.addWidget(self.auto_cb)

        btn_row = QHBoxLayout()
        self.connect_btn = make_button("Connect Google Drive", "cloud", "primary")
        self.connect_btn.clicked.connect(self._connect)
        btn_row.addWidget(self.connect_btn)
        self.backup_now_btn = make_button("Back up now", "upload", "soft")
        self.backup_now_btn.clicked.connect(self._backup_now)
        btn_row.addWidget(self.backup_now_btn)
        self.restore_btn = make_button("Restore from Drive", "download", "soft")
        self.restore_btn.clicked.connect(self._restore_from_drive)
        btn_row.addWidget(self.restore_btn)
        self.disconnect_btn = make_button("Disconnect", "x", "dangerSoft")
        self.disconnect_btn.clicked.connect(self._disconnect)
        btn_row.addWidget(self.disconnect_btn)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)

        lay.addWidget(divider())
        lay.addWidget(label("Local backup file", "h2"))
        lay.addWidget(label("Works without the internet. Good for a quick copy before doing something big.",
                            "sub", wrap=True))
        local_row = QHBoxLayout()
        save_btn = make_button("Save a backup file...", "download", "soft")
        save_btn.clicked.connect(self._save_local)
        local_row.addWidget(save_btn)
        restore_btn = make_button("Restore from a file...", "upload", "soft")
        restore_btn.clicked.connect(self._restore_local)
        local_row.addWidget(restore_btn)
        local_row.addStretch(1)
        lay.addLayout(local_row)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(2000)
        backup.status_changed.connect(self._refresh)
        self._refresh()

    def _refresh(self):
        connected = self.backup.drive.is_connected()
        self.connect_btn.setVisible(not connected)
        for w in (self.backup_now_btn, self.restore_btn, self.disconnect_btn, self.auto_cb):
            w.setVisible(connected)
        if connected:
            self.auto_cb.blockSignals(True)
            self.auto_cb.setChecked(self.backup.auto_enabled)
            self.auto_cb.blockSignals(False)
        state = self.backup.state
        self.status_pill.setText(STATE_LABEL.get(state, state))
        self.status_pill.setProperty("pill", STATE_KIND.get(state, "muted"))
        self.status_pill.style().unpolish(self.status_pill)
        self.status_pill.style().polish(self.status_pill)
        last = self.backup.last_backup
        self.status_text.setText(f"Last backup: {last[:16].replace('T', ' ')}" if last else self.backup.message)

    def _toggle_auto(self, _state):
        self.backup.set_auto_enabled(self.auto_cb.isChecked())

    def _connect(self):
        if not self.backup.drive.credentials_available():
            path, _ = QFileDialog.getOpenFileName(self, "Choose your Google credentials file (client_secret*.json)",
                                                   "", "JSON files (*.json)")
            if not path:
                return
            try:
                self.backup.drive.install_credentials(path)
            except BackupError as exc:
                show_error(self, "Could not use that file", str(exc))
                return
        self.connect_btn.setEnabled(False)
        self.connect_btn.setText("Opening your browser...")
        from app.backup_manager import BackgroundTask
        self._task = BackgroundTask(self.backup.drive.connect)
        self._task.done.connect(self._connect_done)
        self._task.start()

    def _connect_done(self, _result, error):
        self.connect_btn.setEnabled(True)
        self.connect_btn.setText("Connect Google Drive")
        if error:
            show_error(self, "Could not connect", str(error))
        else:
            self.backup.set_auto_enabled(True)
            show_info(self, "Connected", "Google Drive is connected. Your data will now back up automatically.")
        self.backup.refresh_state()
        self._refresh()

    def _backup_now(self):
        try:
            self.backup.backup_now()
        except BackupError as exc:
            show_error(self, "Could not back up", str(exc))

    def _restore_from_drive(self):
        if not ask_yes_no(self, "Restore from Google Drive",
                          "This replaces everything currently on this computer with the backup from Drive.\n"
                          "A safety copy of your current data is kept first, just in case.\n\nContinue?", danger=True):
            return
        from app.backup_manager import BackgroundTask
        self._restore_task = BackgroundTask(self.backup.drive.restore_from_drive)
        self._restore_task.done.connect(self._restore_done)
        self._restore_task.start()

    def _restore_done(self, _result, error):
        if error:
            show_error(self, "Restore failed", str(error))
            return
        show_info(self, "Restored", "Your data has been restored. Please log in again.")
        window = self.window()
        if hasattr(window, "force_logout"):
            window.force_logout()

    def _disconnect(self):
        if ask_yes_no(self, "Disconnect Google Drive", "Automatic backup will stop. Your existing backup in "
                     "Drive is not deleted."):
            self.backup.drive.disconnect()
            self.backup.refresh_state()
            self._refresh()

    def _save_local(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save backup file", config.BACKUP_FILE_NAME, "Backup files (*.db)")
        if not path:
            return
        from app import drive_backup as D
        D.snapshot_to(path)
        show_info(self, "Backup saved", f"Saved to:\n{path}")

    def _restore_local(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a backup file", "", "Backup files (*.db);;All files (*)")
        if not path:
            return
        if not ask_yes_no(self, "Restore backup", "This replaces everything currently on this computer with this "
                          "backup file.\nA safety copy of your current data is kept first.\n\nContinue?", danger=True):
            return
        from app import drive_backup as D
        try:
            D.apply_restore(path)
        except D.BackupError as exc:
            show_error(self, "Restore failed", str(exc))
            return
        show_info(self, "Restored", "Your data has been restored. Please log in again.")
        window = self.window()
        if hasattr(window, "force_logout"):
            window.force_logout()


class SettingsPage(QWidget):
    def __init__(self, on_logout, backup, is_admin: bool):
        super().__init__()
        from PyQt6.QtWidgets import QScrollArea
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(18)
        outer.addWidget(PageHeader("Settings", "", "settings"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        holder = QWidget()
        lay = QVBoxLayout(holder)
        lay.setContentsMargins(2, 2, 12, 12)
        lay.setSpacing(16)
        lay.addWidget(ChangePasswordCard())
        if is_admin:
            lay.addWidget(StoreProfileCard())
            lay.addWidget(DriveBackupCard(backup))
        lay.addStretch(1)
        scroll.setWidget(holder)
        outer.addWidget(scroll, 1)
