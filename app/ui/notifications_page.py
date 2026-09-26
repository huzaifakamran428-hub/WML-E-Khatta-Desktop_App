"""Notifications: low stock, payments due, overdue. Click one to mark it read."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from app.local_api import APIError, client
from app.ui.components import PageHeader, card, icon_chip, label, make_button
from app.ui.theme import C
from app.utils.formatting import format_date

KIND_ICON = {"LOW_STOCK": "alert", "DUE_TODAY": "wallet", "DUE_SOON": "bell", "OVERDUE": "alert"}
KIND_TONE = {"OVERDUE": "danger", "LOW_STOCK": "gold"}


class NotificationRow(QWidget):
    def __init__(self, note: dict, on_click):
        super().__init__()
        box = card(shadow=False)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(box)
        lay = QHBoxLayout(box)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(14)
        tone = KIND_TONE.get(note["type"])
        chip = icon_chip(KIND_ICON.get(note["type"], "bell"), 40, 19)
        if tone == "danger":
            chip.setStyleSheet(f"background: {C['danger']}; border-color: #b0242a; border-radius: 12px;")
        elif tone == "gold":
            chip.setStyleSheet(f"background: {C['gold']}; border-color: #a9791f; border-radius: 12px;")
        lay.addWidget(chip)
        text = QVBoxLayout()
        text.setSpacing(2)
        t = label(note["title"], "h2")
        t.setStyleSheet("font-size: 14px;")
        text.addWidget(t)
        text.addWidget(label(note["message"], "sub", wrap=True))
        text.addWidget(label(format_date(note["created_at"], "%d %b %Y, %I:%M %p"), "hint"))
        lay.addLayout(text, 1)
        if not note.get("read_at"):
            dot = label("●")
            dot.setStyleSheet(f"color: {C['green']}; font-size: 18px;")
            lay.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
            btn = make_button("Mark read", "check", "soft")
            btn.clicked.connect(lambda: on_click(note))
            lay.addWidget(btn, 0, Qt.AlignmentFlag.AlignTop)


class NotificationsPage(QWidget):
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(18)
        self.header = PageHeader("Notifications", "", "bell")
        refresh = make_button("Refresh", "refresh")
        refresh.clicked.connect(self.reload)
        self.header.add_action(refresh)
        outer.addWidget(self.header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(self.scroll.Shape.NoFrame)
        self.holder = QWidget()
        self.list_layout = QVBoxLayout(self.holder)
        self.list_layout.setSpacing(10)
        self.list_layout.addStretch(1)
        self.scroll.setWidget(self.holder)
        outer.addWidget(self.scroll, 1)
        self.reload()

    def reload(self):
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        try:
            notes = client.list_("notifications/")
        except APIError as exc:
            self.header.set_subtitle(f"Could not load: {exc.message}")
            return
        unread = sum(1 for n in notes if not n.get("read_at"))
        self.header.set_subtitle(f"{unread} unread" if unread else "You're all caught up")
        if not notes:
            self.list_layout.insertWidget(0, label("No notifications yet.", "sub"))
        for note in notes:
            self.list_layout.insertWidget(self.list_layout.count() - 1, NotificationRow(note, self._mark_read))

    def _mark_read(self, note):
        try:
            client.post_json(f"notifications/{note['id']}/read/", {})
        except APIError:
            pass
        self.reload()
