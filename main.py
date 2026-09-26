"""
WML E-Khatta -- entry point.

Everything now runs on this computer: there is no server to start, and
nothing about who is logged in is ever written to disk.
"""
from __future__ import annotations

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from app import config, db
from app.backup_manager import BackupManager
from app.drive_backup import DriveBackup
from app.local_api import client
from app.ui.main_window import MainWindow
from app.ui.theme import apply_theme


def _fix_windows_taskbar_icon() -> None:
    """Without this, Windows groups the app under the generic Python icon in
    the taskbar instead of using our own -- this tells Windows it's a
    distinct app so it uses the .exe's icon everywhere (taskbar, Alt+Tab)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"WaqareMedina.{config.APP_NAME}")
    except Exception:
        pass


def main() -> int:
    _fix_windows_taskbar_icon()
    if hasattr(Qt.ApplicationAttribute, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv)
    app.setApplicationName(config.DISPLAY_NAME)
    app.setWindowIcon(QIcon(config.asset_path("WaqareMedina.ico")))
    apply_theme(app)

    db.init_db()
    backup = BackupManager(DriveBackup(), client)

    window = MainWindow(backup)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
