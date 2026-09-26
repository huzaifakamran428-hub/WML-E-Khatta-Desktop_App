"""Main window: glossy sidebar + pages. Shows the login screen until someone logs in."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QIcon, QPixmap, QGuiApplication
from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QScrollArea, QStackedWidget, QVBoxLayout,
    QWidget,
)

from app import config
from app.backup_manager import BackupManager
from app.local_api import APIError, client
from app.ui.components import DevCredit, ask_yes_no, label, make_button
from app.ui.login_page import LoginPage
from app.ui.theme import C, icon, logo_label

ROLE_NAMES = {"ADMIN": "Administrator", "READ_ONLY": "Read-only", "SHOPKEEPER": "Shopkeeper"}


def _page_factories():
    """Imported lazily so start-up is quick."""
    from app.ui.audit_page import AuditLogPage
    from app.ui.credit_page import CreditPlansPage
    from app.ui.customers_page import CustomersPage
    from app.ui.dashboard_page import DashboardPage
    from app.ui.inventory_page import InventoryPage
    from app.ui.notifications_page import NotificationsPage
    from app.ui.reports_page import ReportsPage
    from app.ui.sales_page import SalesPage
    from app.ui.settings_page import SettingsPage
    from app.ui.shopkeepers_page import ShopkeepersPage
    from app.ui.users_page import UsersPage
    return DashboardPage, InventoryPage, CustomersPage, SalesPage, ShopkeepersPage, CreditPlansPage, \
        ReportsPage, UsersPage, AuditLogPage, NotificationsPage, SettingsPage


class MainWindow(QMainWindow):
    def __init__(self, backup: BackupManager):
        super().__init__()
        self.backup = backup
        self.setWindowTitle(config.DISPLAY_NAME)
        self.setWindowIcon(QIcon(config.asset_path("WaqareMedina.ico")))
        self.setMinimumSize(1120, 700)
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.resize(min(1320, int(screen.width() * 0.94)), min(820, int(screen.height() * 0.92)))

        self.root = QStackedWidget()
        self.setCentralWidget(self.root)
        self.login = LoginPage()
        self.login.logged_in.connect(self._build_shell)
        self.root.addWidget(self.login)
        self.shell: QWidget | None = None
        self.pages: dict[str, QWidget] = {}
        self.nav_buttons: dict[str, QPushButton] = {}
        self._badge_timer = QTimer(self)
        self._badge_timer.timeout.connect(self._refresh_badge)
        self.backup.status_changed.connect(self._update_backup_chip)

    # ------------------------------------------------------------------
    def _build_shell(self):
        self._destroy_shell()
        user = client.current_user
        is_admin = user["role"] == "ADMIN"
        is_read_only = user["role"] == "READ_ONLY"
        (Dashboard, Inventory, Customers, Sales, Shopkeepers, Credit, Reports, Users, Audit,
         Notifications, Settings) = _page_factories()

        # key, label, icon, factory, admin-only
        items = [
            ("dashboard", "Dashboard", "dashboard", lambda: Dashboard(self.navigate), False),
            ("inventory", "Inventory", "laptop", lambda: Inventory(can_edit=is_admin), False),
            ("customers", "Customers", "customers", lambda: Customers(can_edit=is_admin), False),
            ("sales", "Sales", "receipt", lambda: Sales(can_edit=is_admin), False),
            ("shopkeepers", "Shopkeepers", "store", lambda: Shopkeepers(can_edit=is_admin), False),
            ("credit", "Credit Plans", "card", lambda: Credit(can_edit=is_admin), False),
            ("reports", "Reports", "chart", lambda: Reports(), True),
            ("users", "Users", "shield", lambda: Users(), True),
            ("audit", "Audit Log", "clipboard", lambda: Audit(), True),
            ("notifications", "Notifications", "bell", lambda: Notifications(), False),
            ("settings", "Settings", "settings", lambda: Settings(on_logout=self.logout, backup=self.backup,
                                                                   is_admin=is_admin), False),
        ]
        if is_read_only:
            # Read-only logins are for checking stock only -- no dashboard totals, no customer/shopkeeper
            # ledgers, nothing else. They can look at Inventory (view-only, enforced by can_edit above) and
            # nowhere else.
            items = [it for it in items if it[0] == "inventory"]
        self._factories = {k: f for k, _l, _i, f, admin_only in items if is_admin or not admin_only}

        shell = QWidget()
        row = QHBoxLayout(shell)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        # ---- sidebar ----
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(258)
        s = QVBoxLayout(side)
        s.setContentsMargins(16, 20, 16, 16)
        s.setSpacing(4)

        brand = QHBoxLayout()
        logo = logo_label("logo.png", 46)
        brand.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(label("E-Khatta", "brandName"))
        names.addWidget(label("Waqare Medina", "brandSub"))
        brand.addLayout(names)
        brand.addStretch(1)
        s.addLayout(brand)
        s.addSpacing(18)

        for key, text, icon_name, _f, admin_only in items:
            if admin_only and not is_admin:
                continue
            btn = QPushButton("  " + text)
            btn.setObjectName("navBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setIcon(icon(icon_name, "#bcd9cb", 20, on_color="#ffffff"))
            btn.setIconSize(QSize(20, 20))
            btn.clicked.connect(lambda _=False, k=key: self.navigate(k))
            s.addWidget(btn)
            self.nav_buttons[key] = btn
        s.addStretch(1)

        if is_admin:
            self.backup_btn = QPushButton("  Drive backup")
            self.backup_btn.setObjectName("sideAction")
            self.backup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.backup_btn.setIconSize(QSize(18, 18))
            self.backup_btn.clicked.connect(lambda: self.navigate("settings"))
            s.addWidget(self.backup_btn)
            self._update_backup_chip()
        s.addSpacing(6)

        who = QHBoxLayout()
        who.setSpacing(10)
        initials = ((user.get("first_name") or user["username"])[:1] + (user.get("last_name") or user["username"][1:2])[:1]).upper()
        avatar = QLabel(initials)
        avatar.setObjectName("avatar")
        avatar.setFixedSize(40, 40)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        who.addWidget(avatar)
        info = QVBoxLayout()
        info.setSpacing(0)
        display = (f"{user.get('first_name', '')} {user.get('last_name', '')}").strip() or user["username"]
        info.addWidget(label(display, "userName"))
        info.addWidget(label(ROLE_NAMES.get(user["role"], user["role"]), "userRole"))
        who.addLayout(info, 1)
        s.addLayout(who)
        out = QPushButton("  Log out")
        out.setObjectName("sideAction")
        out.setCursor(Qt.CursorShape.PointingHandCursor)
        out.setIcon(icon("logout", "#e5f3ec", 18))
        out.setIconSize(QSize(18, 18))
        out.clicked.connect(self.logout)
        s.addWidget(out)
        s.addSpacing(10)
        credit = DevCredit("Developed By Huzaifa", "devCredit", base_pt=11.5)
        credit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s.addWidget(credit)
        row.addWidget(side)

        # ---- content ----
        self.content = QStackedWidget()
        holder = QWidget()
        h = QVBoxLayout(holder)
        h.setContentsMargins(30, 26, 30, 22)
        h.addWidget(self.content)
        row.addWidget(holder, 1)

        self.shell = shell
        self.root.addWidget(shell)
        self.root.setCurrentWidget(shell)
        self.navigate("inventory" if is_read_only else "dashboard")
        self._badge_timer.start(60_000)

    def _destroy_shell(self):
        self._badge_timer.stop()
        if self.shell is not None:
            self.root.removeWidget(self.shell)
            self.shell.deleteLater()
        self.shell = None
        self.pages.clear()
        self.nav_buttons.clear()

    # ------------------------------------------------------------------
    def navigate(self, key: str):
        if key not in self._factories:
            return
        for k, btn in self.nav_buttons.items():
            btn.setChecked(k == key)
        page = self.pages.get(key)
        if page is None:
            try:
                page = self._factories[key]()
            except APIError as exc:
                page = QLabel(f"Could not open this page: {exc.message}")
            self.pages[key] = page
            self.content.addWidget(page)
        elif hasattr(page, "reload"):
            page.reload()
        self.content.setCurrentWidget(page)
        self._refresh_badge()

    def _refresh_badge(self):
        btn = self.nav_buttons.get("notifications")
        if btn is None or not client.is_logged_in():
            return
        try:
            count = client.get_json("notifications/unread-count/")["count"]
        except APIError:
            return
        btn.setText("  Notifications" + (f"   ({count})" if count else ""))

    def _update_backup_chip(self):
        btn = getattr(self, "backup_btn", None)
        if btn is None or self.shell is None:
            return
        state, text = self.backup.state, self.backup.message
        table = {
            "off": ("cloud-off", "Drive backup is off"),
            "idle": ("cloud", "Drive backup is on"),
            "pending": ("cloud", "Backup waiting..."),
            "running": ("refresh", "Backing up..."),
            "ok": ("cloud-check", "Backed up to Drive"),
            "error": ("alert", "Backup failed - tap to fix"),
        }
        icon_name, label_text = table.get(state, ("cloud", text))
        btn.setIcon(icon(icon_name, "#e5f3ec", 18))
        btn.setText("  " + label_text)
        btn.setToolTip(text)

    def logout(self, confirm: bool = True):
        client.logout()
        self._destroy_shell()
        self.login.reset()
        self.root.setCurrentWidget(self.login)

    def force_logout(self, message: str = ""):
        """Used after a restore: the people in the database may have changed."""
        self.logout(confirm=False)

    def closeEvent(self, event):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.backup.flush_before_exit()
        finally:
            QApplication.restoreOverrideCursor()
        client.logout()
        super().closeEvent(event)
