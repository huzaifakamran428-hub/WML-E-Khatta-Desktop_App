"""
Automatic backup to Google Drive.

Every time data is added / changed / deleted, a backup is queued. Changes made
within a few seconds of each other are bundled into one upload. If the internet
is down the backup stays queued and is retried every couple of minutes, and one
last attempt is made when the app is closed.
"""
from __future__ import annotations

import threading

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from app import config
from app.drive_backup import BackupError, DriveBackup

DEBOUNCE_MS = 4000
RETRY_MS = 120_000


class BackgroundTask(QObject):
    """Run a slow function (sign-in, download...) without freezing the window."""
    done = pyqtSignal(object, object)     # result, error

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            result, error = self._fn(), None
        except Exception as exc:          # noqa: BLE001 - reported to the person
            result, error = None, exc
        self.done.emit(result, error)


class BackupManager(QObject):
    status_changed = pyqtSignal()
    _finished = pyqtSignal(bool, str)

    def __init__(self, drive: DriveBackup, client):
        super().__init__()
        self.drive = drive
        self.state = "off"            # off | idle | pending | running | ok | error
        self.message = ""
        self._dirty = False
        self._running = False
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(DEBOUNCE_MS)
        self._debounce.timeout.connect(self._start)
        self._retry = QTimer(self)
        self._retry.setInterval(RETRY_MS)
        self._retry.timeout.connect(self._retry_if_needed)
        self._retry.start()
        self._finished.connect(self._on_finished)
        client.add_change_listener(self.notify_change)
        self.refresh_state()

    # -- settings -----------------------------------------------------------

    @property
    def auto_enabled(self) -> bool:
        return bool(config.load_settings().get("drive_auto_backup", True))

    def set_auto_enabled(self, value: bool):
        settings = config.load_settings()
        settings["drive_auto_backup"] = bool(value)
        config.save_settings(settings)
        self.refresh_state()

    @property
    def last_backup(self) -> str | None:
        return config.load_settings().get("last_drive_backup")

    def is_active(self) -> bool:
        return self.drive.is_connected() and self.auto_enabled

    def refresh_state(self):
        if not self.drive.is_connected():
            self.state, self.message = "off", "Google Drive is not connected"
        elif not self.auto_enabled:
            self.state, self.message = "off", "Automatic backup is turned off"
        elif self.state in ("off",):
            self.state, self.message = "idle", "Automatic backup is on"
        self.status_changed.emit()

    # -- triggers ---------------------------------------------------------------

    def notify_change(self):
        """Called after every successful add / edit / delete."""
        if not self.is_active():
            return
        self._dirty = True
        self.state, self.message = "pending", "Backup waiting..."
        self.status_changed.emit()
        self._debounce.start()

    def backup_now(self):
        if not self.drive.is_connected():
            raise BackupError("Connect Google Drive first.")
        self._dirty = True
        self._start()

    def _retry_if_needed(self):
        if self._dirty and not self._running and self.is_active():
            self._start()

    def _start(self):
        if self._running:
            self._debounce.start()
            return
        self._running, self._dirty = True, False
        self.state, self.message = "running", "Backing up to Google Drive..."
        self.status_changed.emit()
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self):
        try:
            self._finished.emit(True, self.drive.upload_backup())
        except BackupError as exc:
            self._finished.emit(False, str(exc))
        except Exception as exc:          # noqa: BLE001
            self._finished.emit(False, f"Backup failed: {exc}")

    def _on_finished(self, ok: bool, message: str):
        self._running = False
        if ok:
            settings = config.load_settings()
            settings["last_drive_backup"] = message
            config.save_settings(settings)
            self.state, self.message = "ok", "Backed up to Google Drive"
            if self._dirty:                   # more changes arrived meanwhile
                self._debounce.start()
        else:
            self._dirty = True                # try again later
            self.state, self.message = "error", message
        self.status_changed.emit()

    def flush_before_exit(self):
        """Last chance when the window closes: upload anything not yet backed up."""
        if self.is_active() and (self._dirty or self.state in ("pending", "error")) and not self._running:
            try:
                stamp = self.drive.upload_backup()
                settings = config.load_settings()
                settings["last_drive_backup"] = stamp
                config.save_settings(settings)
            except Exception:                 # noqa: BLE001 - closing anyway; retried next time
                pass
