"""Dialoge im Stil der Nachfrage-Karte, ohne ihre Logik neu zu schreiben.

modernize(dialog, title, subtitle, icon) ordnet einen fertig aufgebauten Dialog neu an:

- Kopf: Kachel mit Linien-Icon, Titel als Aufgabe oder Frage, Untertitel in muted
  (ersetzt den einleitenden Text oben im Dialog).
- Inhalt: die vorhandenen Bedienelemente; Formulare mit Beschriftung über dem Feld.
- Fußleiste mit Hintergrund bg: links leise Aktionen (Zurücksetzen, Entfernen …),
  rechts Abbrechen/Schließen und genau eine Hauptaktion.

Die Knöpfe bleiben dieselben Objekte (Signale, Tastenkürzel, Tests greifen weiter), sie
wandern nur in die Fußleiste. Aussehen: theme.py, QDialog[card="true"].
"""
from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import (QAbstractScrollArea, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

import icons
from prompt_card import _detach, _ElidedLabel, source_tile
from theme import SPACE_M, SPACE_S

# Rolle im QDialogButtonBox -> Platz in der Fußleiste
_QUIET_ROLES = (QDialogButtonBox.ResetRole, QDialogButtonBox.DestructiveRole)
_MAIN_ROLES = (QDialogButtonBox.AcceptRole, QDialogButtonBox.YesRole, QDialogButtonBox.ApplyRole)
_CLOSE_ROLES = (QDialogButtonBox.RejectRole, QDialogButtonBox.NoRole)
STANDARD_TEXT = {QDialogButtonBox.Ok: "&Speichern", QDialogButtonBox.Save: "&Speichern",
                 QDialogButtonBox.Cancel: "Abbrechen", QDialogButtonBox.Close: "Schließen"}


def _items(layout):
    while layout.count():
        yield layout.takeAt(0)


def _find(layout, kind):
    """Alle Widgets einer Klasse im Layout (auch verschachtelt), in Reihenfolge."""
    found = []
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item.widget() is not None and isinstance(item.widget(), kind):
            found.append(item.widget())
        elif item.layout() is not None:
            found += _find(item.layout(), kind)
    return found


def labels_above(widget):
    """Formulare: Beschriftung über dem Feld statt links daneben, ohne Doppelpunkt."""
    for form in widget.findChildren(QFormLayout):
        form.setRowWrapPolicy(QFormLayout.WrapAllRows)
        form.setVerticalSpacing(SPACE_S)
        for row in range(form.rowCount()):
            item = form.itemAt(row, QFormLayout.LabelRole)
            label = item.widget() if item else None
            if isinstance(label, QLabel) and label.text().endswith(":"):
                label.setText(label.text()[:-1])
                label.setObjectName("prompt_label")


def _release(box, button, role):
    """Knopf aus dem QDialogButtonBox lösen (der holt seine Knöpfe sonst bei jeder Stiländerung
    zurück) und seine Klicks weiter an die Signale der Box geben, an denen der Dialog hängt."""
    box.removeButton(button)

    def clicked(_checked=False):
        box.clicked.emit(button)
        if role in (QDialogButtonBox.AcceptRole, QDialogButtonBox.YesRole):
            box.accepted.emit()
        elif role in (QDialogButtonBox.RejectRole, QDialogButtonBox.NoRole):
            box.rejected.emit()
        elif role == QDialogButtonBox.HelpRole:
            box.helpRequested.emit()
    button.clicked.connect(clicked)


def _set_default(dialog):
    """Genau eine Hauptaktion: nur sie reagiert auf Enter und ist hervorgehoben."""
    for button in dialog.findChildren(QPushButton):
        button.setAutoDefault(False)
        button.setDefault(button is dialog.card_main)
    if dialog.card_main is not None:
        _fit_bold(dialog.card_main)


def _fit_bold(button):
    """Der Standardknopf ist fett (Stylesheet :default), Qt misst die Breite aber mit der
    normalen Schrift: sonst wird sein Text abgeschnitten."""
    button.ensurePolished()
    text = button.text().replace("&&", "\0").replace("&", "").replace("\0", "&")
    bold = QFont(button.font())
    bold.setBold(True)
    extra = QFontMetrics(bold).horizontalAdvance(text) - button.fontMetrics().horizontalAdvance(text)
    if extra > 0:
        button.setMinimumWidth(max(button.minimumWidth(), button.sizeHint().width() + extra + 4))


class _DefaultGuard(QObject):
    def __init__(self, dialog):
        super().__init__(dialog)
        dialog.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Show:
            QTimer.singleShot(0, lambda: _set_default(obj))
            _set_default(obj)
        return False


def _first_intro(items):
    """Einleitender Text: das erste umbrechende QLabel in den obersten beiden Einträgen."""
    for item in items[:2]:
        widget = item.widget()
        if isinstance(widget, QLabel) and widget.wordWrap():
            return widget
        if item.layout() is not None:
            labels = [w for w in _find(item.layout(), QLabel) if w.wordWrap()]
            if labels:
                return labels[0]
    return None


def modernize(dialog, title, subtitle="", icon="doc", intro=None, scroll=False, primary=None,
              right=(), left=(), head=(), hide=(), subtitle_label=None, below_head=()):
    """Dialog neu anordnen (siehe Modul).

    intro:    einleitendes QLabel, das der Untertitel ersetzt (None = automatisch suchen,
              False = keins). scroll: Inhalt blättert, Kopf und Fuß stehen.
    primary:  die eine Hauptaktion (sonst OK/Speichern aus dem QDialogButtonBox).
    right:    weitere Knöpfe rechts neben Abbrechen (z. B. „Nur dokumentieren“).
    left:     Knöpfe aus dem Inhalt, die als leise Aktionen links in die Fußleiste wandern.
    head:     Widgets rechts in den Kopf (z. B. „+ Neuer Kunde“, ◀ ▶).
    hide:     Widgets, die der neue Kopf ersetzt (alte Überschrift).
    subtitle_label: vorhandenes QLabel als Untertitel; der Dialog setzt seinen Text weiter selbst.
    below_head: Widgets im Kopf unter dem Titel (z. B. die graue Zeitzeile mit Stift)."""
    layout = dialog.layout()
    dialog.setProperty("card", True)
    pal = dialog.palette()
    accent = pal.color(pal.ColorRole.Accent).name()

    boxes = _find(layout, QDialogButtonBox)
    moved = set(head) | set(left) | set(right) | ({primary} if primary is not None else set())
    for widget in moved:  # aus ihren bisherigen Zeilen lösen, bevor die Zeilen umziehen
        if widget.parentWidget() is not None and not isinstance(widget.parentWidget(), QDialogButtonBox):
            _detach(widget, layout)
    if subtitle_label is not None:
        _detach(subtitle_label, layout)
    for widget in hide:
        widget.hide()
    items = list(_items(layout))
    if intro is None:
        intro = _first_intro(items)

    # ---- Kopf
    top = QWidget()
    top.setObjectName("prompt_top")
    top.setAttribute(Qt.WA_StyledBackground)
    head_box = QVBoxLayout(top)
    head_box.setContentsMargins(16, 14, 16, SPACE_M)
    head_box.setSpacing(SPACE_S + 2)
    row_head = QHBoxLayout()
    row_head.setSpacing(SPACE_M)
    head_box.addLayout(row_head)
    row_head.addWidget(source_tile(icon, accent), 0, Qt.AlignVCenter)
    texts = QVBoxLayout()
    texts.setSpacing(2)
    dialog.card_title = _ElidedLabel(title)
    dialog.card_title.setObjectName("prompt_title")
    texts.addWidget(dialog.card_title)
    if subtitle_label is not None:
        dialog.card_subtitle = subtitle_label
    else:
        dialog.card_subtitle = QLabel(subtitle or (intro.text() if intro else ""))
        dialog.card_subtitle.setWordWrap(True)
        dialog.card_subtitle.setVisible(bool(dialog.card_subtitle.text()))
    dialog.card_subtitle.setObjectName("hint")
    texts.addWidget(dialog.card_subtitle)
    row_head.addLayout(texts, 1)
    for widget in head:
        row_head.addWidget(widget, 0, Qt.AlignVCenter)
    for widget in below_head:
        _detach(widget, layout)
        head_box.addWidget(widget)
    dialog.card_head = row_head

    # ---- Inhalt: alles außer Einleitung und Knopfleiste
    body = QWidget()
    body.setObjectName("prompt_body")
    inner = QVBoxLayout(body)
    inner.setContentsMargins(16, SPACE_M, 16, SPACE_M)
    inner.setSpacing(SPACE_S + 2)
    for item in items:
        widget, sub = item.widget(), item.layout()
        if intro and widget is intro:
            widget.hide()
            continue
        if intro and sub is not None and intro in _find(sub, QLabel):
            intro.hide()
        if widget is not None and widget in boxes:
            continue
        if sub is not None:
            sub.setParent(None)
            if sub.count():
                inner.addLayout(sub)
        elif widget is not None:
            # Listen und Tabellen bekommen den freien Platz
            inner.addWidget(widget, 1 if isinstance(widget, QAbstractScrollArea) else 0)
        else:
            inner.addItem(item)
    labels_above(body)
    if intro:
        intro.hide()  # der kurze Untertitel ersetzt sie

    # ---- Fuß: leise Aktionen links, Abbrechen und Hauptaktion rechts
    foot = QWidget()
    foot.setObjectName("prompt_foot")
    foot.setProperty("flat", True)
    foot.setAttribute(Qt.WA_StyledBackground)
    row = QHBoxLayout(foot)
    row.setContentsMargins(16, SPACE_S + 2, 16, SPACE_S + 2)
    row.setSpacing(SPACE_S)
    quiet, close, main = list(left), [], []
    for box in boxes:
        box.hide()  # bleibt als Verteiler für accepted/rejected/clicked bestehen
        for button in box.buttons():
            role = box.buttonRole(button)
            standard = box.standardButton(button)
            _release(box, button, role)
            if button in moved:
                continue
            if standard in STANDARD_TEXT and button.text().replace("&", "") in (
                    "OK", "Save", "Cancel", "Close", "Abbrechen", "Schließen", "Speichern"):
                button.setText(STANDARD_TEXT[standard])
            if role in _QUIET_ROLES:
                button.setObjectName("quiet_button")
                quiet.append(button)
            elif role in _MAIN_ROLES:
                main.append(button)
            elif role in _CLOSE_ROLES:
                close.append(button)
            else:
                quiet.append(button)
    if primary is not None:
        main = [primary] + [b for b in main if b is not primary]
    for button in quiet:
        row.addWidget(button)
    row.addStretch(1)
    for button in close + list(right) + main:
        row.addWidget(button)
        button.show()
    dialog.card_main = main[0] if main else None
    _set_default(dialog)
    # Qt wählt beim Anzeigen selbst einen Standardknopf (QDialogButtonBox): danach wieder festlegen
    dialog._card_guard = _DefaultGuard(dialog)
    dialog.card_foot = row

    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    layout.addWidget(top)
    if scroll:
        area = QScrollArea()
        area.setObjectName("card_scroll")
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.NoFrame)
        area.setWidget(body)
        layout.addWidget(area, 1)
    else:
        layout.addWidget(body, 1)
    layout.addWidget(foot)
    # card="true" kam erst jetzt dazu: Regeln wie „QDialog[card] QLabel#prompt_src“ (Kachel hinter dem
    # Symbol) gelten erst, wenn Qt die Kinder neu gestaltet
    for widget in [dialog, *dialog.findChildren(QWidget)]:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
    return dialog


def move_to_foot(dialog, widgets, side="left", main=None):
    """Knöpfe, die ein Dialog selbst unten anordnet (ohne QDialogButtonBox), in die Fußleiste.
    side: "left" (leise Aktionen) oder "right"; main: die eine Hauptaktion."""
    row = dialog.card_foot
    stretch = next(i for i in range(row.count()) if row.itemAt(i).spacerItem() is not None)
    for widget in widgets:
        parent = widget.parentWidget()
        if parent is not None and parent.layout() is not None:
            _detach(widget, parent.layout())
        if side == "left":
            row.insertWidget(stretch, widget)
            stretch += 1
        else:
            row.addWidget(widget)
    if isinstance(main, QPushButton):
        for button in dialog.findChildren(QPushButton):
            button.setDefault(button is main)


def nav_icons(dialog, prev_button, next_button):
    """◀ ▶ als Linien-Icons (wie in der Nachfrage-Karte); Namen und Tooltips bleiben."""
    pal = dialog.palette()
    muted = pal.color(pal.ColorRole.PlaceholderText).name()
    for button, name in ((prev_button, "prev"), (next_button, "next")):
        button.setText("")
        button.setIcon(icons.icon(name, muted))
        button.setObjectName("prompt_tool")
