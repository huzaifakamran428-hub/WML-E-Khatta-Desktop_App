"""
Reusable "list + add/edit/delete" screen.

Most screens (Inventory, Customers, Users, Credit Plans...) are just a table
of records with a form. This file draws that once, in the glossy style, so each
screen only has to say WHICH columns and WHICH form fields it wants.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any, Callable

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from app.local_api import APIError, client
from app.ui.components import (
    GlassDialog, IntEdit, MoneyEdit, PageHeader, SearchCombo, ask_yes_no, card, field, label, make_button,
    pill, search_box, show_error,
)

NO_DATE = QDate(1900, 1, 1)


@dataclass
class FieldSpec:
    name: str
    label: str
    kind: str = "text"        # text | multiline | int | decimal | choice | bool | date | fk | password
    required: bool = True
    choices: list = dc_field(default_factory=list)          # [(value, label)]
    fk_loader: Callable[[], list] | None = None
    fk_display: str = "name"
    editable_on_update: bool = True
    hint: str = ""
    default: Any = None
    section: str = ""
    full_width: bool = False


@dataclass
class ColumnSpec:
    key: str
    header: str
    formatter: Callable[[Any], str] | None = None
    value_fn: Callable[[dict], str] | None = None
    pill_fn: Callable[[dict], tuple[str, str] | None] | None = None
    align_right: bool = False
    compact: bool = False


@dataclass
class RowAction:
    text: str
    handler: Callable[[dict], None]
    icon: str | None = None
    variant: str = "soft"
    visible: Callable[[dict], bool] | None = None


class FormDialog(GlassDialog):
    def __init__(self, parent, title: str, fields: list[FieldSpec], initial: dict | None = None,
                 is_update: bool = False, subtitle: str = "", icon_name: str = "edit", width: int = 600,
                 ok_text: str = "Save"):
        super().__init__(parent, title, subtitle, icon_name, width)
        self.fields = [f for f in fields if not (is_update and not f.editable_on_update)]
        self.widgets: dict[str, QWidget] = {}
        initial = initial or {}

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        row, col, last_section = 0, 0, ""
        for spec in self.fields:
            if spec.section and spec.section != last_section:
                if col == 1:
                    row, col = row + 1, 0
                grid.addWidget(label(spec.section, "h2"), row, 0, 1, 2)
                row += 1
                last_section = spec.section
            widget = self._make_widget(spec, initial.get(spec.name, spec.default))
            self.widgets[spec.name] = widget
            caption = spec.label + (" *" if spec.required and spec.kind != "bool" else "")
            wide = spec.kind in ("multiline",) or spec.full_width
            if spec.kind == "bool":
                box = widget
            else:
                box = field(caption, widget, spec.hint)
            if wide:
                if col == 1:
                    row, col = row + 1, 0
                grid.addWidget(box, row, 0, 1, 2)
                row += 1
            else:
                grid.addWidget(box, row, col)
                col += 1
                if col == 2:
                    row, col = row + 1, 0
        self.body_layout.addLayout(grid)
        self.body_layout.addStretch(1)

        self.error_label = QLabel("")
        self.error_label.setObjectName("error")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        self.pinned.addWidget(self.error_label)
        self.set_buttons(ok_text).clicked.connect(self._on_save)
        self.finish()

    # -- widget factory ----------------------------------------------------
    def _make_widget(self, spec: FieldSpec, value) -> QWidget:
        kind = spec.kind
        if kind == "multiline":
            w = QTextEdit()
            w.setFixedHeight(76)
            w.setPlainText("" if value is None else str(value))
            w.setTabChangesFocus(True)
            return w
        if kind in ("int", "decimal"):
            w = IntEdit() if kind == "int" else MoneyEdit()
            w.setObjectName("")
            w.setValue(float(value or 0))
            w.returnAdvance.connect(self.focusNextField)
            return w
        if kind == "choice":
            w = QComboBox()
            for val, text in spec.choices:
                w.addItem(text, val)
            idx = w.findData(value)
            w.setCurrentIndex(idx if idx >= 0 else 0)
            return w
        if kind == "bool":
            w = QCheckBox(spec.label)
            w.setChecked(bool(value))
            return w
        if kind == "date":
            w = QDateEdit(calendarPopup=True)
            w.setDisplayFormat("dd MMM yyyy")
            if not spec.required:
                w.setMinimumDate(NO_DATE)
                w.setSpecialValueText("Not set")
            parsed = QDate.fromString(str(value)[:10], "yyyy-MM-dd") if value else QDate()
            w.setDate(parsed if parsed.isValid() else (QDate.currentDate() if spec.required else NO_DATE))
            return w
        if kind == "fk":
            w = SearchCombo()
            if not spec.required:
                w.addItem("- None -", None)
            for item in (spec.fk_loader() if spec.fk_loader else []):
                w.addItem(str(item.get(spec.fk_display, item.get("id"))), item["id"])
            idx = w.findData(value)
            w.setCurrentIndex(idx if idx >= 0 else 0)
            return w
        w = QLineEdit("" if value is None else str(value))
        if kind == "password":
            w.setEchoMode(QLineEdit.EchoMode.Password)
            w.setPlaceholderText("At least 6 characters")
        w.returnPressed.connect(self.focusNextField)
        return w

    # -- reading + validating ---------------------------------------------
    def _read(self, spec: FieldSpec):
        w = self.widgets[spec.name]
        if isinstance(w, QTextEdit):
            return w.toPlainText().strip()
        if isinstance(w, MoneyEdit):
            return w.value()
        if isinstance(w, SearchCombo):
            return w.currentData() if w.has_valid_choice() else None
        if isinstance(w, QComboBox):
            return w.currentData()
        if isinstance(w, QCheckBox):
            return w.isChecked()
        if isinstance(w, QDateEdit):
            return None if w.date() == NO_DATE else w.date().toString("yyyy-MM-dd")
        return w.text().strip()

    def get_data(self) -> dict:
        return {spec.name: self._read(spec) for spec in self.fields}

    def _on_save(self):
        for spec in self.fields:
            if not spec.required or spec.kind in ("bool", "int", "decimal", "choice"):
                continue
            if self._read(spec) in (None, ""):
                self.error_label.setText(f"Please fill in: {spec.label}")
                self.error_label.show()
                self.widgets[spec.name].setFocus()
                return
        self.accept()


class EntityListPage(QWidget):
    def __init__(self, title: str, endpoint: str, columns: list[ColumnSpec], fields: list[FieldSpec], *,
                 subtitle: str = "", icon_name: str = "box", can_add: bool = True, can_edit: bool = True,
                 can_delete: bool = True, extra_actions: list[RowAction] | None = None,
                 add_label: str = "Add", entity_name: str = "record", form_width: int = 600,
                 delete_warning: str = "", list_params: dict | None = None, header_widgets: list | None = None):
        super().__init__()
        self.title, self.endpoint, self.columns, self.fields = title, endpoint, columns, fields
        self.can_add, self.can_edit, self.can_delete = can_add, can_edit, can_delete
        self.extra_actions = extra_actions or []
        self.entity_name, self.form_width = entity_name, form_width
        self.delete_warning = delete_warning
        self.list_params = list_params or {}
        self.rows: list[dict] = []
        self._shown: list[dict] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(18)

        self.header = PageHeader(title, subtitle, icon_name)
        self.search = search_box(f"Search {title.lower()}...")
        self.search.textChanged.connect(self._render)
        self.header.add_action(self.search)
        for w in (header_widgets or []):
            self.header.add_action(w)
        refresh = make_button("", "refresh", "icon", "Refresh")
        refresh.clicked.connect(self.reload)
        self.header.add_action(refresh)
        if can_add:
            add = make_button(add_label, "plus", "primary")
            add.clicked.connect(self._on_add)
            self.header.add_action(add)
        outer.addWidget(self.header)

        box = card(shadow=False)
        box_lay = QVBoxLayout(box)
        box_lay.setContentsMargins(10, 8, 10, 10)
        self.table = QTableWidget()
        self._setup_table()
        box_lay.addWidget(self.table, 1)
        self.empty_label = label("", "sub")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setMinimumHeight(60)
        box_lay.addWidget(self.empty_label)
        outer.addWidget(box, 1)

        self.status_label = label("", "hint")
        outer.addWidget(self.status_label)
        self.reload()

    # -- table ---------------------------------------------------------------
    def _has_actions(self) -> bool:
        return self.can_edit or self.can_delete or bool(self.extra_actions)

    def _action_width(self) -> int:
        width = 0
        if self.can_edit:
            width += 44
        if self.can_delete:
            width += 44
        for a in self.extra_actions:
            width += 44 + len(a.text) * 9 + (24 if a.icon else 0)
        return max(width + 26, 60)

    def _setup_table(self):
        headers = [c.header for c in self.columns] + (["Actions"] if self._has_actions() else [])
        t = self.table
        t.setColumnCount(len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        t.setAlternatingRowColors(True)
        t.setShowGrid(False)
        t.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        t.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        t.verticalHeader().setVisible(False)
        t.verticalHeader().setDefaultSectionSize(54)
        head = t.horizontalHeader()
        head.setHighlightSections(False)
        head.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        for i, c in enumerate(self.columns):
            # Fixed (not ResizeToContents) so our manual resizeColumnToContents() in _render -- which
            # correctly measures pill/cell widgets -- is the one that decides the width and it sticks.
            head.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed if c.compact
                                      else QHeaderView.ResizeMode.Stretch)
        if self._has_actions():
            last = len(self.columns)
            head.setSectionResizeMode(last, QHeaderView.ResizeMode.Fixed)
            t.setColumnWidth(last, self._action_width())

    # -- data ----------------------------------------------------------------
    def load_rows(self) -> list[dict]:
        return client.list_(self.endpoint, self.list_params)

    def reload(self):
        try:
            self.rows = self.load_rows()
            self.status_label.setText("")
        except APIError as exc:
            self.rows = []
            self.status_label.setText(f"Could not load: {exc.message}")
        self._render()

    def _cell_text(self, col: ColumnSpec, row: dict) -> str:
        if col.value_fn:
            return col.value_fn(row)
        value = row.get(col.key)
        if col.formatter:
            return col.formatter(value)
        return "" if value is None else str(value)

    def _render(self):
        query = self.search.text().strip().lower()
        shown = []
        for row in self.rows:
            if not query or any(query in self._cell_text(c, row).lower() for c in self.columns):
                shown.append(row)
        self._shown = shown
        t = self.table
        t.setRowCount(len(shown))
        for r, row in enumerate(shown):
            for c, col in enumerate(self.columns):
                p = col.pill_fn(row) if col.pill_fn else None
                if p:
                    holder = QWidget()
                    lay = QHBoxLayout(holder)
                    lay.setContentsMargins(6, 0, 6, 0)
                    lay.addWidget(pill(*p), 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    lay.addStretch(1)
                    t.setCellWidget(r, c, holder)
                    t.setItem(r, c, QTableWidgetItem(""))
                    continue
                item = QTableWidgetItem(self._cell_text(col, row))
                if col.align_right:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                t.setItem(r, c, item)
            if self._has_actions():
                t.setCellWidget(r, len(self.columns), self._make_actions(row))
        for c, col in enumerate(self.columns):          # pill/compact columns: size to their real content
            if col.compact:
                t.resizeColumnToContents(c)
                t.setColumnWidth(c, max(t.columnWidth(c) + 20, 44))   # buffer so pill/text never clips
        if self._has_actions() and shown:                # actions column: size to the real buttons, not a guess.
            last = len(self.columns)                      # resizeColumnToContents() under-measures cell WIDGETS
            widest = 0                                    # (as opposed to plain text/pills), clipping button
            for r in range(t.rowCount()):                 # labels like "Open" by a character or two -- so measure
                w = t.cellWidget(r, last)                  # the actual widgets' sizeHint() directly instead.
                if w is not None:
                    widest = max(widest, w.sizeHint().width())
            t.setColumnWidth(last, max(widest + 16, self._action_width()))
        if not shown:
            self.empty_label.setText("No matches found." if self.rows else
                                     f"No {self.entity_name}s yet." + (" Click the green button above to add one." if self.can_add else ""))
        else:
            self.empty_label.setText("")
        self.empty_label.setVisible(not shown)
        total = len(self.rows)
        self.header.set_subtitle(f"{total} {self.entity_name}{'' if total == 1 else 's'}")

    def _make_actions(self, row: dict) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(4, 0, 4, 0)
        lay.setSpacing(6)
        for a in self.extra_actions:
            if a.visible and not a.visible(row):
                continue
            btn = make_button(a.text, a.icon, a.variant if a.variant != "soft" else "soft")
            btn.setProperty("variant", "soft")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.clicked.connect(lambda _=False, h=a.handler, r=row: h(r))
            lay.addWidget(btn)
        if self.can_edit:
            b = make_button("", "edit", "icon", f"Edit this {self.entity_name}")
            b.clicked.connect(lambda _=False, r=row: self._on_edit(r))
            lay.addWidget(b)
        if self.can_delete:
            b = make_button("", "trash", "dangerSoft", f"Delete this {self.entity_name}")
            b.setProperty("variant", "dangerSoft")
            b.clicked.connect(lambda _=False, r=row: self._on_delete(r))
            lay.addWidget(b)
        lay.addStretch(1)
        return w

    # -- add / edit / delete -------------------------------------------------
    def new_defaults(self) -> dict:
        return {}

    def _on_add(self):
        dlg = FormDialog(self, f"Add {self.entity_name}", self.fields, self.new_defaults(), False,
                         icon_name="plus", width=self.form_width, ok_text="Save")
        if dlg.exec():
            self.save_new(dlg.get_data())

    def save_new(self, data: dict):
        try:
            client.create(self.endpoint, data)
            self.reload()
        except APIError as exc:
            show_error(self, "Could not save", exc.message)

    def _on_edit(self, row: dict):
        try:
            fresh = client.retrieve(self.endpoint, row["id"])   # newest values incl. private ones
        except APIError:
            fresh = row
        dlg = FormDialog(self, f"Edit {self.entity_name}", self.fields, fresh, True,
                         icon_name="edit", width=self.form_width)
        if dlg.exec():
            self.save_edit(row, dlg.get_data())

    def save_edit(self, row: dict, data: dict):
        try:
            client.update(self.endpoint, row["id"], data)
            self.reload()
        except APIError as exc:
            show_error(self, "Could not save", exc.message)

    def _on_delete(self, row: dict):
        text = f"Delete this {self.entity_name}?"
        if self.delete_warning:
            text += "\n\n" + self.delete_warning
        else:
            text += "\n\nThis cannot be undone."
        if ask_yes_no(self, f"Delete {self.entity_name}", text, danger=True):
            try:
                client.remove(self.endpoint, row["id"])
                self.reload()
            except APIError as exc:
                show_error(self, "Could not delete", exc.message)
