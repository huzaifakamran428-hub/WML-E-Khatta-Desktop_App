"""Login screen. Nothing is remembered: every person types their own details every time."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from app import config
from app.local_api import APIError, client
from app.ui.components import DevCredit, card, field, label, make_button
from app.ui.theme import C, icon, logo_label


class LoginPage(QWidget):
    logged_in = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setObjectName("loginRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.card = card(name="loginCard")
        self.card.setFixedWidth(430)
        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(38, 34, 38, 30)
        lay.setSpacing(12)

        logo = logo_label("logo.png", 104)
        lay.addWidget(logo, 0, Qt.AlignmentFlag.AlignHCenter)
        self.title = label(config.DISPLAY_NAME, "h1")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.title)
        self.subtitle = label(config.STORE_TAGLINE, "sub")
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle.setWordWrap(True)
        lay.addWidget(self.subtitle)
        lay.addSpacing(10)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Your name (optional)")
        self.name_field = field("Your name", self.name_input)
        lay.addWidget(self.name_field)

        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("Username")
        self.user_input.addAction(icon("user", C["muted"], 17), QLineEdit.ActionPosition.LeadingPosition)
        self.user_input.setTextMargins(4, 0, 0, 0)
        lay.addWidget(field("Username", self.user_input))

        self.pass_input = QLineEdit()
        self.pass_input.setPlaceholderText("Password")
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_input.addAction(icon("lock", C["muted"], 17), QLineEdit.ActionPosition.LeadingPosition)
        self.pass_input.setTextMargins(4, 0, 0, 0)
        self._eye = self.pass_input.addAction(icon("eye", C["muted"], 17), QLineEdit.ActionPosition.TrailingPosition)
        self._eye.triggered.connect(self._toggle_password)
        self._eye.setToolTip("Show / hide password")
        lay.addWidget(field("Password", self.pass_input))

        self.confirm_input = QLineEdit()
        self.confirm_input.setPlaceholderText("Type the password again")
        self.confirm_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_field = field("Confirm password", self.confirm_input)
        lay.addWidget(self.confirm_field)

        self.error = label("", "error", wrap=True)
        self.error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error.hide()
        lay.addWidget(self.error)

        self.go = make_button("Log in", "lock", "primary")
        self.go.setMinimumHeight(44)
        self.go.clicked.connect(self._submit)
        lay.addSpacing(4)
        lay.addWidget(self.go)

        note = label("For your safety, this app never saves passwords.\nType your login every time.", "hint", wrap=True)
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(note)

        lay.addSpacing(6)
        credit = DevCredit("Developed By Huzaifa", "devCreditLogin", base_pt=12.0)
        credit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(credit)

        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.card)
        row.addStretch(1)
        outer.addLayout(row)

        self.user_input.returnPressed.connect(self.pass_input.setFocus)
        self.pass_input.returnPressed.connect(self._enter_pressed)
        self.confirm_input.returnPressed.connect(self._submit)
        self.name_input.returnPressed.connect(self.user_input.setFocus)
        self._setup_mode = False
        self.reset()

    def _enter_pressed(self):
        if self._setup_mode:
            self.confirm_input.setFocus()
        else:
            self._submit()

    def _toggle_password(self):
        hidden = self.pass_input.echoMode() == QLineEdit.EchoMode.Password
        mode = QLineEdit.EchoMode.Normal if hidden else QLineEdit.EchoMode.Password
        self.pass_input.setEchoMode(mode)
        self._eye.setIcon(icon("eye-off" if hidden else "eye", C["muted"], 17))

    def reset(self):
        """Wipe everything typed and show the right form (login, or first-time setup)."""
        for box in (self.name_input, self.user_input, self.pass_input, self.confirm_input):
            box.clear()
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._eye.setIcon(icon("eye", C["muted"], 17))
        self.error.hide()
        self._setup_mode = client.needs_setup()
        self.name_field.setVisible(self._setup_mode)
        self.confirm_field.setVisible(self._setup_mode)
        if self._setup_mode:
            self.title.setText("Welcome!")
            self.subtitle.setText("First time here. Create the administrator account for this computer.")
            self.go.setText("Create account and start")
            self.pass_input.setPlaceholderText("At least 6 characters")
        else:
            self.title.setText(config.DISPLAY_NAME)
            self.subtitle.setText(config.STORE_TAGLINE)
            self.go.setText("Log in")
            self.pass_input.setPlaceholderText("Password")
        (self.name_input if self._setup_mode else self.user_input).setFocus()

    def _fail(self, text: str):
        self.error.setText(text)
        self.error.show()

    def _submit(self):
        username, password = self.user_input.text().strip(), self.pass_input.text()
        if not username or not password:
            return self._fail("Please type your username and password.")
        try:
            if self._setup_mode:
                if password != self.confirm_input.text():
                    return self._fail("The two passwords do not match.")
                client.create_first_admin(username, password, self.name_input.text())
            else:
                client.login(username, password)
        except APIError as exc:
            self.pass_input.clear()
            self.confirm_input.clear()
            return self._fail(exc.message)
        for box in (self.name_input, self.user_input, self.pass_input, self.confirm_input):
            box.clear()                       # the password never lingers in the box
        self.error.hide()
        self.logged_in.emit()
