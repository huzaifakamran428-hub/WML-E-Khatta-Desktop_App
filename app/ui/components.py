"""Small reusable pieces used by every screen."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, pyqtProperty, QSize, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QColor, QDoubleValidator, QRegularExpressionValidator
from PyQt6.QtCore import QRegularExpression
from PyQt6.QtWidgets import (
    QComboBox, QCompleter, QDialog, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget, QApplication,
)

from app.ui.theme import C, icon, pixmap


# -- basic widgets ----------------------------------------------------------

def make_button(text: str = "", icon_name: str | None = None, variant: str | None = None,
                tooltip: str | None = None) -> QPushButton:
    btn = QPushButton(text)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setAutoDefault(False)
    btn.setDefault(False)
    if variant:
        btn.setProperty("variant", variant)
    if icon_name:
        color = "#ffffff" if variant in ("primary", "danger") else (
            C["green_dark"] if variant == "soft" else "#bf2d32" if variant == "dangerSoft" else C["ink"])
        size = 16 if variant in ("mini", "icon") else 18
        btn.setIcon(icon(icon_name, color, size))
        btn.setIconSize(QSize(size, size))
    if tooltip:
        btn.setToolTip(tooltip)
    return btn


def pill(text: str, kind: str = "muted") -> QLabel:
    lab = QLabel(text)
    lab.setProperty("pill", kind)
    lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lab


def label(text: str, name: str | None = None, wrap: bool = False) -> QLabel:
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    return lab


class ClickableLabel(QLabel):
    """A QLabel that acts like a link: pointing-hand cursor, emits clicked."""

    clicked = pyqtSignal()

    def __init__(self, text: str = "", name: str | None = None):
        super().__init__(text)
        if name:
            self.setObjectName(name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


class DevCredit(QLabel):
    """A small "developed by" credit that grows clearly larger on hover.

    Kept modern and understated at rest; on hover the text scales up
    smoothly and gets a touch heavier so it's easy to read.
    """

    def __init__(self, text: str, object_name: str, base_pt: float = 11.5, grow_pt: float = 4.0):
        super().__init__(f"\u2726  {text}")
        self.setObjectName(object_name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Crafted by Huzaifa")
        self._base_pt = base_pt
        self._pt = base_pt
        self._grow_pt = grow_pt
        self._apply_point_size(bold=False)

        self._size_anim = QPropertyAnimation(self, b"pointSize", self)
        self._size_anim.setDuration(170)
        self._size_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._size_anim.valueChanged.connect(self._on_size_step)

    def _apply_point_size(self, bold: bool):
        f = self.font()
        f.setPointSizeF(self._pt)
        f.setBold(bold)
        self.setFont(f)

    def _on_size_step(self, value):
        self._pt = value
        self._apply_point_size(bold=value > self._base_pt + 0.5)

    def get_point_size(self) -> float:
        return self._pt

    def set_point_size(self, value: float):
        self._pt = value
        self._apply_point_size(bold=value > self._base_pt + 0.5)

    pointSize = pyqtProperty(float, get_point_size, set_point_size)

    def enterEvent(self, event):
        self._size_anim.stop()
        self._size_anim.setStartValue(self._pt)
        self._size_anim.setEndValue(self._base_pt + self._grow_pt)
        self._size_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._size_anim.stop()
        self._size_anim.setStartValue(self._pt)
        self._size_anim.setEndValue(self._base_pt)
        self._size_anim.start()
        super().leaveEvent(event)


def card(shadow: bool = True, name: str = "card") -> QFrame:
    frame = QFrame()
    frame.setObjectName(name)
    if shadow:
        fx = QGraphicsDropShadowEffect(frame)
        fx.setBlurRadius(28)
        fx.setOffset(0, 6)
        fx.setColor(QColor(15, 60, 40, 38))
        frame.setGraphicsEffect(fx)
    return frame


def divider() -> QFrame:
    line = QFrame()
    line.setObjectName("divider")
    return line


def icon_chip(name: str, size: int = 46, icon_px: int = 24) -> QLabel:
    chip = QLabel()
    chip.setObjectName("iconChip")
    chip.setFixedSize(size, size)
    chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
    chip.setPixmap(pixmap(name, "#ffffff", icon_px))
    return chip


class PageHeader(QWidget):
    """Big heading + short description on the left, action buttons on the right."""

    def __init__(self, title: str, subtitle: str = "", icon_name: str | None = None):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(14)
        if icon_name:
            row.addWidget(icon_chip(icon_name), 0, Qt.AlignmentFlag.AlignVCenter)
        text = QVBoxLayout()
        text.setSpacing(1)
        self.title_label = label(title, "h1")
        text.addWidget(self.title_label)
        self.sub_label = label(subtitle, "sub")
        self.sub_label.setVisible(bool(subtitle))
        text.addWidget(self.sub_label)
        row.addLayout(text)
        row.addStretch(1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(10)
        row.addLayout(self.actions)

    def add_action(self, widget: QWidget):
        self.actions.addWidget(widget)

    def set_subtitle(self, text: str):
        self.sub_label.setText(text)
        self.sub_label.setVisible(bool(text))


def search_box(placeholder: str = "Search...", width: int = 240) -> QLineEdit:
    box = QLineEdit()
    box.setObjectName("search")
    box.setPlaceholderText(placeholder)
    box.setFixedWidth(width)
    box.setClearButtonEnabled(True)
    box.addAction(icon("search", C["muted"], 16), QLineEdit.ActionPosition.LeadingPosition)
    return box


# -- typing-friendly number boxes -------------------------------------------

class MoneyEdit(QLineEdit):
    """A number box that behaves like you expect: type digits, clear it, paste.

    Replaces Qt's spin boxes (whose arrows and fixed '0.00' made typing awkward).
    Empty means 0. Whole click selects everything so typing replaces the old value.
    """
    valueChanged = pyqtSignal(float)
    returnAdvance = pyqtSignal()

    def __init__(self, decimals: int = 2, maximum: float = 999_999_999, placeholder: str = "0"):
        super().__init__()
        self.setObjectName("money")
        self._decimals = decimals
        self._maximum = maximum
        pattern = r"^\d{0,12}$" if decimals == 0 else rf"^\d{{0,12}}(\.\d{{0,{decimals}}})?$"
        self.setValidator(QRegularExpressionValidator(QRegularExpression(pattern)))
        self.setPlaceholderText(placeholder)
        self.setInputMethodHints(Qt.InputMethodHint.ImhFormattedNumbersOnly)
        self.textChanged.connect(lambda _t: self.valueChanged.emit(self.value()))
        self.returnPressed.connect(self.returnAdvance.emit)

    def value(self) -> float:
        text = self.text().strip()
        if not text or text == ".":
            return 0.0
        try:
            return min(float(text), self._maximum)
        except ValueError:
            return 0.0

    def setValue(self, value: float):
        value = float(value or 0)
        if value == 0:
            self.setText("")
        elif self._decimals == 0 or abs(value - round(value)) < 0.005:
            self.setText(str(int(round(value))))
        else:
            self.setText(f"{value:.{self._decimals}f}".rstrip("0").rstrip("."))

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.selectAll()

    def mousePressEvent(self, event):
        had_focus = self.hasFocus()
        super().mousePressEvent(event)
        if not had_focus:
            self.selectAll()


class IntEdit(MoneyEdit):
    def __init__(self, maximum: int = 999_999, placeholder: str = "0"):
        super().__init__(decimals=0, maximum=maximum, placeholder=placeholder)

    def value(self) -> int:           # type: ignore[override]
        return int(super().value())


class SearchCombo(QComboBox):
    """Drop-down you can also type into to filter a long list."""

    def __init__(self):
        super().__init__()
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        completer = self.completer()
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.lineEdit().setPlaceholderText("Type to search...")

    def has_valid_choice(self) -> bool:
        idx = self.findText(self.currentText(), Qt.MatchFlag.MatchExactly)
        if idx >= 0 and idx != self.currentIndex():
            self.setCurrentIndex(idx)
        return idx >= 0 and self.currentData() is not None

    def select_data(self, data) -> None:
        idx = self.findData(data)
        if idx >= 0:
            self.setCurrentIndex(idx)


def field(label_text: str, widget: QWidget, hint: str = "") -> QWidget:
    """A form row: small caption above the input (iPhone-settings style)."""
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(5)
    lay.addWidget(label(label_text, "fieldLabel"))
    lay.addWidget(widget)
    if hint:
        lay.addWidget(label(hint, "hint", wrap=True))
    return box


# -- message boxes ------------------------------------------------------------

def show_error(parent, title: str, text: str):
    QMessageBox.critical(parent, title, text)


def show_info(parent, title: str, text: str):
    QMessageBox.information(parent, title, text)


def ask_yes_no(parent, title: str, text: str, danger: bool = False) -> bool:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning if danger else QMessageBox.Icon.Question)
    box.setWindowTitle(title)
    box.setText(text)
    yes = box.addButton("Yes, continue", QMessageBox.ButtonRole.AcceptRole)
    no = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    if danger:
        yes.setProperty("variant", "danger")
    else:
        yes.setProperty("variant", "primary")
    box.setDefaultButton(no)
    box.exec()
    return box.clickedButton() is yes


# -- dialogs that always fit the screen -----------------------------------

class GlassDialog(QDialog):
    """Title on top, scrolling body, buttons pinned at the bottom.

    Because the body scrolls, nothing is ever cut off on a small laptop screen,
    and the buttons (and any always-visible summary) never scroll away.
    """

    def __init__(self, parent, title: str, subtitle: str = "", icon_name: str | None = None, width: int = 540):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self._width = width
        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 24, 26, 22)
        outer.setSpacing(16)

        head = QHBoxLayout()
        head.setSpacing(14)
        if icon_name:
            head.addWidget(icon_chip(icon_name, 44, 22), 0, Qt.AlignmentFlag.AlignTop)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        titles.addWidget(label(title, "dialogTitle"))
        if subtitle:
            titles.addWidget(label(subtitle, "sub", wrap=True))
        head.addLayout(titles, 1)
        outer.addLayout(head)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.body.setObjectName("dialogBody")
        self.body.setStyleSheet("QWidget#dialogBody { background: transparent; }")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(2, 2, 8, 2)
        self.body_layout.setSpacing(14)
        self.scroll.setWidget(self.body)
        outer.addWidget(self.scroll, 1)

        self.pinned = QVBoxLayout()          # always-visible area (e.g. live totals)
        self.pinned.setSpacing(10)
        outer.addLayout(self.pinned)

        self.button_row = QHBoxLayout()
        self.button_row.setSpacing(10)
        self.button_row.addStretch(1)
        outer.addLayout(self.button_row)

    def set_buttons(self, ok_text: str = "Save", ok_icon: str | None = "check", cancel_text: str = "Cancel",
                    ok_variant: str = "primary") -> QPushButton:
        cancel = make_button(cancel_text)
        cancel.clicked.connect(self.reject)
        ok = make_button(ok_text, ok_icon, ok_variant)
        ok.setMinimumWidth(130)
        self.button_row.addWidget(cancel)
        self.button_row.addWidget(ok)
        self.ok_button = ok
        return ok

    def finish(self):
        """Call after the body is filled: size the dialog to its content, capped to the screen."""
        screen = QApplication.primaryScreen().availableGeometry() if QApplication.primaryScreen() else None
        max_h = int(screen.height() * 0.92) if screen else 800
        max_w = int(screen.width() * 0.96) if screen else 1200
        self.body.adjustSize()
        chrome = 24 + 22 + 16 * 3 + 64 + self._pinned_height() + 56
        wanted = self.body.sizeHint().height() + chrome
        self.resize(min(self._width, max_w), min(max(wanted, 320), max_h))
        self.setMinimumWidth(min(self._width - 60, max_w))

    def _pinned_height(self) -> int:
        total = 0
        for i in range(self.pinned.count()):
            item = self.pinned.itemAt(i)
            w = item.widget()
            if w is not None:
                total += w.sizeHint().height() + 10
            elif item.layout() is not None:
                total += item.layout().sizeHint().height() + 10
        return total

    def focusNextField(self):
        self.focusNextChild()
