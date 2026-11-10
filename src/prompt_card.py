"""Nachfrage nach einer erkannten Tätigkeit: Karte (Standard), Kompakt und Leiste.

- PromptWindow: Karte unten rechts ohne Windows-Rahmen. Kopf mit offenen Nachfragen
  (Punkte, anklickbar), Anheften und Schließen; darunter die Frage, eine feste Zeile für
  Datum und Uhrzeit (Stift zum Bearbeiten), Kunde, Kategorie, Tätigkeit und Chips für
  Ticket, Kulanz, Reise, Zuschlag und Textbausteine. „Kompakt“ ist dieselbe Karte, kleiner.
- PromptStrip: schmale Leiste mit Zahl der offenen Nachfragen und ✕. Klick öffnet die Karte.

Beide blenden nach der eingestellten Dauer aus (0 = dauerhaft). Solange die Maus darüber ist,
du tippst oder die Karte angeheftet ist, läuft die Zeit nicht ab.
Die Felder kommen aus journal_dialogs._EntryForm; die Karte ordnet sie nur neu an.
"""
from datetime import datetime

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractSpinBox, QDialog, QFrame, QGraphicsDropShadowEffect, QGridLayout,
                               QHBoxLayout, QLabel, QLayout, QPushButton, QSizePolicy, QToolButton,
                               QVBoxLayout, QWidget)

import icons
import prompt_topics
from flow_layout import FlowLayout
from grouping import format_tv_id
from journal import TIME_FMT, suggest_category, suggest_customer
from theme import SPACE_M, SPACE_S, SPACE_XS

# Darstellung (config["prompt_mode"]); "tray" ist der alte Name der Leiste
STYLES = [("window", "Karte"), ("compact", "Kompakt"), ("strip", "Leiste"), ("off", "Aus")]
STYLE_HINTS = {"window": "Alle Felder, übersichtlich (Standard)", "compact": "Alle Felder, kleiner",
               "strip": "Eine Zeile, Klick öffnet die Karte", "off": "Nur in der Zeile „Doku“ zeigen"}
# Anzeigedauer in Sekunden, 0 = dauerhaft; Vorgabe beim Wechsel der Darstellung
TIMEOUTS = [(10, "10 Sekunden"), (30, "30 Sekunden"), (60, "1 Minute"), (300, "5 Minuten"), (0, "Dauerhaft")]
DEFAULT_TIMEOUT = {"window": 0, "compact": 10, "strip": 10, "off": 0}
SHADOW = 14  # Rand für den Schatten um Karte und Leiste (durchsichtig)


def style_preview(style, tokens, width=96, height=60):
    """Kleines Bild für die Kacheln der Darstellung: Bildschirm mit Taskleiste und darauf Karte,
    kompakte Karte, Leiste oder (Aus) nur die Zeile „Doku“. Farben aus den Tokens des Designs."""
    pixmap = QPixmap(width * 2, height * 2)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    w, h = width, height
    p.setPen(QPen(QColor(tokens["border"]), 1))
    p.setBrush(QColor(tokens["bg"]))
    p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 6, 6)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(tokens["border"]))
    p.drawRect(QRectF(1, h - 9, w - 2, 8))  # Taskleiste
    line = QColor(tokens["muted"])
    line.setAlpha(140)
    accent = QColor(tokens["accent"])

    def card(x, y, cw, ch, rows):
        p.setPen(QPen(QColor(tokens["control"]), 1))
        p.setBrush(QColor(tokens["surface"]))
        p.drawRoundedRect(QRectF(x, y, cw, ch), 4, 4)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(tokens["text"]))
        p.drawRoundedRect(QRectF(x + 5, y + 5, cw * 0.55, 3), 1.5, 1.5)
        p.setBrush(line)
        for i in range(rows):
            p.drawRoundedRect(QRectF(x + 5, y + 12 + i * 6, cw - 10 - (i % 2) * 8, 3), 1.5, 1.5)
        p.setBrush(accent)
        p.drawRoundedRect(QRectF(x + cw - 18, y + ch - 8, 13, 4), 2, 2)

    if style == "window":
        card(w - 58, h - 57, 52, 44, 4)
    elif style == "compact":
        card(w - 44, h - 46, 38, 33, 2)
    elif style == "strip":
        p.setPen(QPen(QColor(tokens["control"]), 1))
        p.setBrush(QColor(tokens["surface"]))
        p.drawRoundedRect(QRectF(w - 62, h - 24, 56, 11), 5.5, 5.5)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(tokens["text"]))
        p.drawRoundedRect(QRectF(w - 55, h - 20, 26, 3), 1.5, 1.5)
        p.setBrush(accent)
        p.drawEllipse(QRectF(w - 20, h - 22, 7, 7))
    else:  # Aus: nur die Zeile „Doku“ im Hauptfenster
        p.setPen(QPen(line, 1, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(10, 14, w - 20, 10), 3, 3)
        p.setPen(Qt.NoPen)
        p.setBrush(line)
        p.drawRoundedRect(QRectF(14, 18, 18, 3), 1.5, 1.5)
    p.end()
    return pixmap


def prompt_style(config):
    mode = (config or {}).get("prompt_mode", "window")
    if mode == "tray":
        return "strip"
    return mode if mode in dict(STYLES) else "window"


def prompt_timeout(config):
    return max(0, int((config or {}).get("prompt_timeout_seconds", 0) or 0))


def source_icon_name(entry):
    """Icon für die Quelle einer Nachfrage (icons.PATHS)."""
    if entry.get("idle"):
        return "clock"
    if entry.get("pc_block"):
        return "monitor"
    kind = (entry.get("type") or "").lower()
    if entry.get("direction") or "telefon" in kind or "anruf" in kind:
        return "phone"
    if "vpn" in kind:
        return "network"
    if any(w in kind for w in ("rdp", "remote", "ssh")):
        return "screen_share"
    if "teamviewer" in kind:
        return "monitor"
    return "doc"


def _minutes(entry):
    start = datetime.strptime(entry["start"], TIME_FMT)
    end = datetime.strptime(entry["end"], TIME_FMT)
    return int(round((end - start).total_seconds() / 60))


def entry_kind(entry):
    """„TeamViewer“, „Telefonat eingehend“, „Am PC: M365-Admin“ …"""
    if entry.get("idle"):
        return "Abwesenheit am PC"
    if entry.get("pc_block"):
        return f"Am PC: {entry.get('category', '')}".strip()
    if entry.get("rule"):
        return entry.get("category") or entry.get("type", "Tätigkeit")
    kind = entry.get("type") or "Tätigkeit"
    if entry.get("direction") and entry.get("direction") != "Anruf":
        kind = f"{kind} {entry['direction'].lower()}"
    return kind


def entry_title(entry, customer=""):
    if entry.get("idle"):
        return f"Du warst {_minutes(entry)} Min. nicht am Rechner. Was war los?"
    who = (customer or entry.get("customer_name") or "").strip()
    kind = (entry.get("type") or "").split(" ")[0].lower()
    if kind and who.lower().startswith(kind):  # „TeamViewer 123 …“: noch kein Name, steht darunter
        who = (customer or "").strip()
    return f"Was hast du bei {who} gemacht?" if who else "Was hast du gemacht?"


def entry_subtitle(entry):
    parts = [entry_kind(entry)]
    if entry.get("tv_id"):
        parts.append(f"ID {format_tv_id(entry['tv_id'])}")
    elif entry.get("customer_name") and not entry.get("idle"):
        parts.append(entry["customer_name"])
    extra = prompt_topics.parts_text(entry)
    if extra:
        parts.append(extra)
    return " · ".join(p for p in parts if p)


def entry_label(entry):
    """Kurz für Punkte und Leiste: „TeamViewer · Beispiel AG · 10:05–10:42“."""
    start = datetime.strptime(entry["start"], TIME_FMT)
    end = datetime.strptime(entry["end"], TIME_FMT)
    who = "" if entry.get("idle") else (entry.get("customer_name") or "").strip()
    head = entry_kind(entry) + (f" · {who}" if who and not who.startswith(entry_kind(entry)) else "")
    return f"{head} · {start:%H:%M}–{end:%H:%M}"


def animations_enabled():
    """Windows: Animationen in den Einstellungen für Barrierefreiheit aus? Dann nichts blinken lassen."""
    try:
        import ctypes
        value = ctypes.c_int(1)
        ok = ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(value), 0)
        return bool(value.value) if ok else True
    except (AttributeError, OSError):
        return True


class _ElidedLabel(QLabel):
    """Eine Zeile, bei Platzmangel mit „…“ gekürzt, voller Text als Tooltip. Bleibt so hoch wie
    eine Zeile: Titel und Quelle schieben die Zeitzeile darunter nie nach unten."""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full = ""
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.set_full_text(text)

    def set_full_text(self, text):
        self._full = text or ""
        self.setText(self._full)
        self.setAccessibleName(self._full)
        self._update()

    def full_text(self):
        return self._full

    def minimumSizeHint(self):
        return QSize(40, super().minimumSizeHint().height())

    def sizeHint(self):
        return QSize(min(super().sizeHint().width(), 400), super().sizeHint().height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update()

    def _update(self):
        shown = self.fontMetrics().elidedText(self._full, Qt.ElideRight, max(0, self.width()))
        if shown != self.text():
            self.setText(shown)
        self.setToolTip(self._full if shown != self._full else "")


class _TimerBar(QWidget):
    """Dünner Balken unten: wie viel Zeit bis zum Ausblenden bleibt."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(3)
        self.fraction = 1.0
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def set_fraction(self, value):
        value = max(0.0, min(1.0, value))
        if abs(value - self.fraction) > 0.002:
            self.fraction = value
            self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(QRectF(0, 0, self.width() * self.fraction, self.height()),
                         self.palette().color(self.palette().ColorRole.Accent))


class _AutoHide:
    """Ausblenden nach timeout Sekunden (0 = nie). Hält an, solange gehalten oder die Maus darüber ist."""

    TICK_MS = 100

    def _setup_autohide(self, timeout, keep_while_active, bar):
        self._timeout_ms = int(timeout) * 1000
        self._left_ms = self._timeout_ms
        self._keep_while_active = keep_while_active
        self._held = False   # getippt oder Stift benutzt: bleibt stehen
        self._pinned = False
        self._bar = bar
        bar.setVisible(self._timeout_ms > 0)
        self._hide_timer = QTimer(self)
        self._hide_timer.setInterval(self.TICK_MS)
        self._hide_timer.timeout.connect(self._tick)
        if self._timeout_ms > 0:
            self._hide_timer.start()

    def hold(self):
        if self._keep_while_active:
            self._held = True
            self._sync_bar()

    def set_pinned(self, on):
        self._pinned = bool(on)
        self._sync_bar()

    def _sync_bar(self):
        stopped = self._pinned or self._held
        self._bar.setVisible(self._timeout_ms > 0 and not stopped)

    def _paused(self):
        return self._pinned or self._held or (self._keep_while_active and self.underMouse())

    def _tick(self):
        if self._paused():
            return
        self._left_ms -= self.TICK_MS
        self._bar.set_fraction(self._left_ms / self._timeout_ms)
        if self._left_ms <= 0:
            self._hide_timer.stop()
            self._timed_out()


def _shadow(widget):
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(28)
    effect.setOffset(0, 6)
    effect.setColor(QColor(0, 0, 0, 70))
    widget.setGraphicsEffect(effect)


def _detach(widget, layout):
    """Widget aus dem Layout (auch verschachtelt) nehmen, damit es woanders hinkann."""
    if layout is None:
        return False
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item.widget() is widget:
            layout.takeAt(i)
            return True
        if item.layout() and _detach(widget, item.layout()):
            return True
    return False


def _icon_label(name, color, size=16, name_for_a11y=""):
    label = QLabel()
    label.setPixmap(icons.icon(name, color).pixmap(size, size))
    label.setFixedSize(size, size)
    label.setObjectName("prompt_icon")
    if name_for_a11y:
        label.setAccessibleName(name_for_a11y)
    return label


def _theme_colors(widget):
    pal = widget.palette()
    return pal.color(pal.ColorRole.WindowText).name(), pal.color(pal.ColorRole.Accent).name(), \
        pal.color(pal.ColorRole.PlaceholderText).name()


class _Dock:
    def dock_bottom_right(self, margin=8):
        """Unten rechts über der Taskleiste halten, mit Abstand – auch wenn das Fenster wächst."""
        self._dock_margin = margin
        self._dock()

    def _dock(self):
        margin = getattr(self, "_dock_margin", None)
        screen = QGuiApplication.primaryScreen()
        if margin is None or screen is None:
            return
        area = screen.availableGeometry()  # Bildschirm ohne Taskleiste
        frame = self.frameGeometry()
        x = max(area.x(), area.x() + area.width() - frame.width() - margin)
        y = max(area.y(), area.y() + area.height() - frame.height() - margin)
        if (x, y) != (frame.x(), frame.y()):
            self.move(x, y)


class CardParts:
    """Gemeinsame Teile von Nachfrage-Karte und Dialog „Tätigkeit nachtragen“: feste Zeitzeile
    mit Stift, Kunde/Kategorie/Tätigkeit mit Beschriftung darüber, Chips und Ticket als Chip.
    Die Felder kommen aus journal_dialogs._EntryForm (form) und werden nur umgehängt (old)."""

    def hold(self):
        """Karte: nicht mehr automatisch ausblenden (_AutoHide). Im Dialog nichts zu tun."""

    # ---- Zeitzeile

    def _build_time_row(self, form, old, muted):
        self.time_row = QFrame()
        self.time_row.setObjectName("prompt_time")
        self.time_row.setProperty("editing", False)
        time = QHBoxLayout(self.time_row)
        time.setContentsMargins(SPACE_S + 2, 3, 4, 3)
        time.setSpacing(SPACE_XS + 2)
        for w in (form.date_edit, form.start_edit, form.end_edit, form.duration):
            _detach(w, old)
        form.date_edit.show()
        time.addWidget(_icon_label("calendar", muted, 14))
        time.addWidget(form.date_edit)
        time.addSpacing(SPACE_S)
        time.addWidget(_icon_label("clock", muted, 14))
        time.addWidget(form.start_edit)
        dash = QLabel("–")
        dash.setObjectName("hint")
        time.addWidget(dash)
        time.addWidget(form.end_edit)
        form.duration.setWordWrap(False)
        form.duration.setObjectName("hint")
        time.addWidget(form.duration, 1)
        self.time_btn = QToolButton()
        self.time_btn.setObjectName("prompt_tool")
        self.time_btn.setAccessibleName("Datum und Uhrzeit bearbeiten")
        self.time_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.time_btn.clicked.connect(lambda: self.set_time_editing(not self.time_editing()))
        time.addWidget(self.time_btn)
        for w in (form.date_edit, form.start_edit, form.end_edit):
            w.setObjectName("prompt_time_field")
            w.installEventFilter(self)
        self.set_time_editing(False)
        return self.time_row

    def time_editing(self):
        return bool(self.time_row.property("editing"))

    def set_time_editing(self, on):
        form = self.form
        for w in (form.date_edit, form.start_edit, form.end_edit):
            w.setReadOnly(not on)
            w.setButtonSymbols(QAbstractSpinBox.UpDownArrows if on and w is not form.date_edit
                               else QAbstractSpinBox.NoButtons)
            w.setFocusPolicy(Qt.StrongFocus if on else Qt.NoFocus)
        form.date_edit.setCalendarPopup(on)
        self.time_row.setProperty("editing", on)
        self.time_btn.setText("Fertig" if on else "")
        self.time_btn.setToolTip("Fertig" if on else "Datum und Uhrzeit bearbeiten")
        _text, accent, muted = _theme_colors(self.parent() or self)
        self.time_btn.setIcon(icons.icon("check_mark" if on else "edit", accent if on else muted))
        for w in (self.time_row, form.date_edit, form.start_edit, form.end_edit):
            w.style().unpolish(w)
            w.style().polish(w)
        if on:
            self.hold()
            form.start_edit.setFocus()

    # ---- Kunde, Kategorie, Tätigkeit, Chips, Ticket

    def _build_fields(self, body_box, form, old, compact=False, text_height=64):
        grid = QGridLayout()
        grid.setHorizontalSpacing(SPACE_M)
        grid.setVerticalSpacing(SPACE_XS)
        for col, (name, w) in enumerate((("&Kunde", form.customer_edit), ("Kate&gorie", form.category_edit))):
            _detach(w, old)
            if compact:
                w.lineEdit().setPlaceholderText(name.replace("&", ""))
                grid.addWidget(w, 0, col)
            else:
                label = QLabel(name)
                label.setObjectName("prompt_label")
                label.setBuddy(w)
                grid.addWidget(label, 0, col)
                grid.addWidget(w, 1, col)
            grid.setColumnStretch(col, 1)
        body_box.addLayout(grid)

        _detach(form.text_edit, old)
        if not compact:
            label = QLabel("&Tätigkeit")
            label.setObjectName("prompt_label")
            label.setBuddy(form.text_edit)
            body_box.addSpacing(2)
            body_box.addWidget(label)
        form.text_edit.setFixedHeight(text_height)
        body_box.addWidget(form.text_edit)

        # Chips: + Ticket, Merken, Kulanz, Reise, Zuschlag, Text einfügen
        chips_host = QWidget()
        chips_host.setObjectName("chips")
        chips = FlowLayout(chips_host, spacing=6)
        self.ticket_add = QToolButton()
        self.ticket_add.setObjectName("chip_add")
        self.ticket_add.setText("+ T&icket")
        self.ticket_add.setToolTip("Ticketnummer eintragen oder in Matrix42 suchen")
        self.ticket_add.clicked.connect(self._open_ticket)
        self.ticket_chip = QToolButton()
        self.ticket_chip.setObjectName("ticket_chip")
        self.ticket_chip.setToolTip("Ticket entfernen")
        self.ticket_chip.clicked.connect(self._remove_ticket)
        chips.addWidget(self.ticket_add)
        chips.addWidget(self.ticket_chip)
        for w in (form.remember_tv, form.learn_rule):
            if w is not None:
                _detach(w, old)
                w.setObjectName("chip_check")
                chips.addWidget(w)
        for w in (form.goodwill_box, form.travel_box, form.surcharge_box):
            _detach(w, old)
            w.setObjectName("chip_check")
            chips.addWidget(w)
        form.travel_box.setText("&Reise")
        form.surcharge_box.setText("Kein &Zuschlag")
        _detach(form.insert_button, old)
        form.insert_button.setObjectName("chip_button")
        form.insert_button.setText("Text &einfügen")
        chips.addWidget(form.insert_button)
        body_box.addWidget(chips_host)

        # Ticket: Feld erst nach „+ Ticket“, danach als Chip; Vorschlag darunter als Link
        self.ticket_row = QWidget()
        self.ticket_row.setObjectName("chips")
        ticket_box = QHBoxLayout(self.ticket_row)
        ticket_box.setContentsMargins(0, 0, 0, 0)
        ticket_box.setSpacing(SPACE_S)
        for w in (form.ticket_edit, form.ticket_search_button):
            if w is not None:
                _detach(w, old)
                ticket_box.addWidget(w, 1 if w is form.ticket_edit else 0)
        form.ticket_edit.show()
        form.ticket_edit.lineEdit().returnPressed.connect(self._close_ticket)
        body_box.addWidget(self.ticket_row)
        for w in (form.ticket_status, form.ticket_take, form.error):
            _detach(w, old)
            body_box.addWidget(w)
        if form.ticket_suggestions:
            top_label = form.ticket_suggestions[0]["label"]
            form.ticket_take.setText(f"Vorschlag: {top_label.replace('&', '&&')}")
        form.ticket_take.setObjectName("link_button")
        form.ticket_take.setCursor(Qt.PointingHandCursor)
        form.ticket_take.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        form.text_edit.installEventFilter(self)
        self._sync_ticket(collapse=True)
        form.ticket_edit.currentTextChanged.connect(lambda _t: self._sync_ticket())

    def _sync_ticket(self, collapse=False):
        ticket = self.form.ticket_edit.currentText().strip()
        open_row = self.ticket_row.isVisibleTo(self) and not collapse
        self.ticket_row.setVisible(open_row)
        self.ticket_chip.setText(f"{ticket}  ✕")
        self.ticket_chip.setAccessibleName(f"Ticket {ticket} entfernen")
        self.ticket_chip.setVisible(bool(ticket) and not open_row)
        self.ticket_add.setVisible(not ticket and not open_row)
        if not open_row:
            self.form.ticket_status.hide()

    def _open_ticket(self):
        self.hold()
        self.ticket_row.show()
        self._sync_ticket()
        self.form.ticket_edit.setFocus()

    def _close_ticket(self):
        if self.form._lookup is not None and self.form._completer.popup().isVisible():
            return
        self._sync_ticket(collapse=True)
        self.form.text_edit.setFocus()

    def _remove_ticket(self):
        self.form.ticket_edit.setCurrentText("")
        self._sync_ticket(collapse=True)

    def _card_event(self, obj, event):
        """Für eventFilter: Ticket nach Verlassen als Chip zeigen, Doppelklick öffnet die Zeit."""
        form = self.form
        if obj is form.text_edit and event.type() == QEvent.FocusIn \
                and form.ticket_edit.currentText().strip() and self.ticket_row.isVisibleTo(self):
            QTimer.singleShot(0, lambda: self._sync_ticket(collapse=True))  # Ticket übernommen
        if obj in (form.date_edit, form.start_edit, form.end_edit) and not self.time_editing() \
                and event.type() == QEvent.MouseButtonDblClick:
            self.set_time_editing(True)
            return True
        return False


def source_tile(icon_name, color, size=36):
    """Kachel links im Kopf mit Linien-Icon (Quelle bzw. Aufgabe)."""
    tile = QLabel()
    tile.setObjectName("prompt_src")
    tile.setFixedSize(size, size)
    tile.setAlignment(Qt.AlignCenter)
    tile.setPixmap(icons.icon(icon_name, color).pixmap(20, 20))
    return tile


class PromptWindow(_AutoHide, _Dock, CardParts, QDialog):
    """Nachfrage als Karte. Bleibt oben, nimmt aber nicht den Fokus weg.

    Signal answered(action, entry, item): action = "save" | "later" | "ignore" | "timeout".
    Signal jump(index): Punkt oben rechts angeklickt, zur Nachfrage index wechseln.
    """
    answered = Signal(str, dict, dict)
    jump = Signal(int)

    def __init__(self, entry, customers, categories, tv_names=None, pending=0, parent=None,
                 customer=None, category=None, trace=None, rule_subject=None, style="window",
                 timeout=0, queue=None, dots_clickable=True, keep_while_active=True, draft="",
                 **form_options):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        from journal_dialogs import _EntryForm  # hier: journal_dialogs lädt dieses Modul
        self.entry = entry
        self.style = "compact" if style == "compact" else "window"
        compact = self.style == "compact"
        self.setWindowTitle("Zeitzeuge: Was hast du gemacht?")
        self.setObjectName("prompt_window")
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._done = False
        text_color, accent, muted = _theme_colors(parent or self)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(SHADOW, SHADOW, SHADOW, SHADOW)
        outer.setSizeConstraint(QLayout.SetFixedSize)
        self.card = QFrame()
        self.card.setObjectName("prompt_card")
        self.card.setProperty("compact", compact)
        self.card.setFixedWidth(440 if compact else 580)
        _shadow(self.card)
        outer.addWidget(self.card)
        box = QVBoxLayout(self.card)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)

        start = datetime.strptime(entry["start"], TIME_FMT)
        end = datetime.strptime(entry["end"], TIME_FMT)
        self.form = _EntryForm(
            start, end, customers, categories,
            customer=suggest_customer(entry, tv_names) if customer is None else customer,
            category=suggest_category(entry, categories) if category is None else category,
            tv_id=entry.get("tv_id"), parent=self.card, trace=trace, rule_subject=rule_subject,
            **{"show_ticket": False, **form_options})
        form = self.form
        old = form.layout()
        form.hide()  # nur noch Hülle; die Felder wandern in die Karte
        if draft:
            form.text_edit.setPlainText(draft)

        # ---- Kopf: App, offene Nachfragen, Anheften, Schließen
        top = QWidget()
        top.setObjectName("prompt_top")
        top.setAttribute(Qt.WA_StyledBackground)
        head_box = QVBoxLayout(top)
        pad = SPACE_M if compact else 16
        head_box.setContentsMargins(pad, SPACE_M, pad, SPACE_M)
        head_box.setSpacing(SPACE_S + 2)
        app_row = QHBoxLayout()
        app_row.setSpacing(SPACE_S)
        logo = QLabel()
        logo.setObjectName("prompt_icon")
        app_icon = (parent.windowIcon() if parent else self.windowIcon())
        if not app_icon.isNull():
            logo.setPixmap(app_icon.pixmap(16, 16))
            app_row.addWidget(logo)
        app_name = QLabel("Zeitzeuge")
        app_name.setObjectName("hint")
        app_row.addWidget(app_name)
        app_row.addStretch(1)
        self.dots = QWidget()
        self.dots.setObjectName("prompt_dots")
        self.dots_row = QHBoxLayout(self.dots)
        self.dots_row.setContentsMargins(0, 0, 0, 0)
        self.dots_row.setSpacing(0)
        app_row.addWidget(self.dots)
        self.dots_clickable = dots_clickable
        self.pin_btn = QToolButton()
        self.pin_btn.setObjectName("prompt_tool")
        self.pin_btn.setCheckable(True)
        self.pin_btn.setIcon(icons.icon("pin", muted))
        self.pin_btn.setToolTip("Anheften: nicht automatisch ausblenden")
        self.pin_btn.setAccessibleName("Anheften")
        self.pin_btn.toggled.connect(self.set_pinned)
        app_row.addWidget(self.pin_btn)
        close = QToolButton()
        close.setObjectName("prompt_tool")
        close.setIcon(icons.icon("close", muted))
        close.setToolTip("Schließen: später noch einmal fragen (Esc)")
        close.setAccessibleName("Schließen, später fragen")
        close.clicked.connect(lambda: self._answer("later"))
        app_row.addWidget(close)
        head_box.addLayout(app_row)

        head = QHBoxLayout()
        head.setSpacing(SPACE_M)
        head.addWidget(source_tile(source_icon_name(entry), accent), 0, Qt.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.title = _ElidedLabel(entry_title(entry, form.customer_edit.currentText()))
        self.title.setObjectName("prompt_title")
        self.subtitle = _ElidedLabel(entry_subtitle(entry))
        self.subtitle.setObjectName("hint")
        texts.addWidget(self.title)
        texts.addWidget(self.subtitle)
        head.addLayout(texts, 1)
        head_box.addLayout(head)
        # Kunde gewählt: Frage nennt ihn
        if not entry.get("idle"):
            form.customer_edit.currentTextChanged.connect(
                lambda t: self.title.set_full_text(entry_title(entry, t)))

        head_box.addWidget(self._build_time_row(form, old, muted))
        box.addWidget(top)

        # ---- Inhalt: Kunde, Kategorie, Tätigkeit, Chips
        body = QWidget()
        body.setObjectName("prompt_body")
        body_box = QVBoxLayout(body)
        body_box.setContentsMargins(pad, SPACE_M, pad, SPACE_M)
        body_box.setSpacing(SPACE_S + 2)
        self.quick_buttons = []
        if entry.get("idle"):
            body_box.addLayout(self._quick_choices())
        self._build_fields(body_box, form, old, compact=compact, text_height=52 if compact else 64)
        form.text_edit.textChanged.connect(self.hold)

        if entry.get("idle"):
            note = QLabel("Bleibt verschlüsselt auf diesem PC.")
            note.setObjectName("hint")
            body_box.addWidget(note)
        box.addWidget(body)

        # ---- Fuß: Nicht dokumentieren | Später | Speichern
        foot = QWidget()
        foot.setObjectName("prompt_foot")
        foot.setAttribute(Qt.WA_StyledBackground)
        foot_box = QHBoxLayout(foot)
        foot_box.setContentsMargins(pad, SPACE_S + 2, pad, SPACE_S + 2)
        foot_box.setSpacing(SPACE_S)
        ignore = QPushButton("&Nicht dokumentieren")
        ignore.setObjectName("quiet_button")
        ignore.setAutoDefault(False)
        ignore.setToolTip("Für diesen Eintrag nicht mehr fragen (z. B. privat oder intern)")
        foot_box.addWidget(ignore)
        foot_box.addStretch(1)
        later = QPushButton("S&päter")
        later.setAutoDefault(False)
        later.setToolTip("Später noch einmal fragen")
        foot_box.addWidget(later)
        self.save_btn = QPushButton("&Speichern")
        self.save_btn.setDefault(True)
        foot_box.addWidget(self.save_btn)
        self.save_btn.clicked.connect(lambda: self._answer("save"))
        later.clicked.connect(lambda: self._answer("later"))
        ignore.clicked.connect(lambda: self._answer("ignore"))
        box.addWidget(foot)
        bar = _TimerBar()
        box.addWidget(bar)

        form.validate_hook = self.save_btn.setEnabled
        form.validate()
        self.set_queue(queue or [], 0, pending)
        self._setup_autohide(timeout, keep_while_active, bar)
        form.text_edit.setFocus()  # gleich losschreiben

    # ---- Offene Nachfragen (Punkte)

    def set_queue(self, labels, current=0, pending=None):
        """labels: Kurztext je offener Nachfrage, current: welche diese Karte zeigt."""
        while self.dots_row.count():
            item = self.dots_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not labels and pending:
            labels = [entry_label(self.entry)] + [""] * pending
        self.pending = max(0, len(labels) - 1)
        self.dots.setVisible(len(labels) > 1)
        if len(labels) < 2:
            return
        pos = QLabel(f"{current + 1} von {len(labels)}")
        pos.setObjectName("hint")
        pos.setContentsMargins(0, 0, SPACE_XS, 0)
        self.dots_row.addWidget(pos)
        for i, text in enumerate(labels[:9]):
            dot = QToolButton()
            dot.setObjectName("prompt_dot")
            dot.setProperty("current", i == current)
            dot.setToolTip(text)
            dot.setAccessibleName(f"Nachfrage {i + 1}: {text}" if text else f"Nachfrage {i + 1}")
            dot.setFixedSize(26 if i == current else 16, 20)
            dot.setEnabled(self.dots_clickable and i != current and bool(text))
            dot.setCursor(Qt.PointingHandCursor)
            dot.clicked.connect(lambda _c=False, i=i: self.jump.emit(i))
            self.dots_row.addWidget(dot)

    def set_pending(self, pending):
        """Älterer Weg: nur die Zahl der weiteren offenen Nachfragen."""
        self.set_queue([], 0, pending)

    # ---- Abwesenheit: Schnellauswahl

    def _quick_choices(self):
        """Abwesenheit: typische Tätigkeiten mit einem Klick (idle_watch.QUICK_CHOICES)."""
        from idle_watch import QUICK_CHOICES
        row = QHBoxLayout()
        row.setSpacing(SPACE_S)
        for label, category, text, flags in QUICK_CHOICES:
            button = QToolButton()  # Chip; gewählt = gefüllt
            button.setObjectName("chip")
            button.setText(label)
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(f"{category}: {text}" + (" (gleich speichern)" if flags.get("save") else ""))
            button.clicked.connect(lambda _c=False, a=(category, text, flags): self.quick_choice(*a))
            row.addWidget(button)
            self.quick_buttons.append(button)
        row.addStretch(1)
        return row

    def quick_choice(self, category, text, flags=None):
        flags = flags or {}
        self.hold()
        self.form.category_edit.setCurrentText(category)
        # Eigenen Text nicht überschreiben, den einer anderen Schnellauswahl schon
        current = self.form.text_edit.toPlainText().strip()
        if not current or current == getattr(self, "_quick_text", None):
            self.form.text_edit.setPlainText(text)
            self._quick_text = text
        self.form.travel_box.setChecked(bool(flags.get("travel")))
        if flags.get("save"):
            self._answer("save")
        else:
            self.form.text_edit.setFocus()
            self.form.text_edit.selectAll()

    # ---- Fenster

    def eventFilter(self, obj, event):
        if self._card_event(obj, event):
            return True
        return super().eventFilter(obj, event)

    def showEvent(self, event):
        super().showEvent(event)
        self._dock()
        QTimer.singleShot(0, self._dock)  # Größe steht erst nach dem Anzeigen sicher

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._dock()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._answer("later")
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and event.modifiers() & Qt.ControlModifier:
            self._answer("save")
            return
        super().keyPressEvent(event)

    def _timed_out(self):
        self._answer("timeout")

    def draft(self):
        return self.form.text_edit.toPlainText()

    def _answer(self, action):
        if self._done:
            return
        if action == "save" and not self.form.validate():
            return
        self._done = True
        self._hide_timer.stop()
        self.answered.emit(action, self.entry, self.form.item() if action == "save" else {})
        self.close()

    def item(self):
        return self.form.item()

    def remember_tv(self):
        """Kunde zur Spur merken (Name stammt aus der Zeit, als es nur TeamViewer gab)."""
        return self.form.remember_customer()

    def wants_rule(self):
        return self.form.wants_rule()

    def reject(self):  # Esc oder Fenster schließen = später fragen
        if not self._done:
            self._done = True
            self.answered.emit("later", self.entry, {})
        super().reject()

    def closeEvent(self, event):
        if not self._done:
            self._done = True
            self.answered.emit("later", self.entry, {})
        super().closeEvent(event)


class PromptStrip(_AutoHide, _Dock, QWidget):
    """Schmale Leiste unten rechts: vorne die erste offene Nachfrage, dahinter angedeutet die
    weiteren, die Zahl und ✕. Signale: opened (Klick), dismissed (✕), timed_out (Zeit um)."""
    opened = Signal()
    dismissed = Signal()
    timed_out = Signal()

    WIDTH = 400

    def __init__(self, entry, count=1, parent=None, timeout=0, keep_while_active=True, close_all=False):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.entry = entry
        self.setObjectName("prompt_strip_window")
        self.setWindowTitle("Zeitzeuge: offene Nachfrage")
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        _text, accent, muted = _theme_colors(parent or self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(SHADOW, SHADOW, SHADOW, SHADOW)
        outer.setSpacing(0)
        outer.setSizeConstraint(QLayout.SetFixedSize)
        self.strip = QFrame()
        self.strip.setObjectName("prompt_strip")
        self.strip.setFixedWidth(self.WIDTH)
        self.strip.setCursor(Qt.PointingHandCursor)
        self.strip.setFocusPolicy(Qt.StrongFocus)
        self.strip.setAccessibleName("Nachfrage öffnen")
        self.strip.installEventFilter(self)
        _shadow(self.strip)
        outer.addWidget(self.strip, 0, Qt.AlignHCenter)
        col = QVBoxLayout(self.strip)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        row = QHBoxLayout()
        row.setContentsMargins(SPACE_M, SPACE_S + 2, SPACE_S, SPACE_S + 2)
        row.setSpacing(SPACE_M)
        self.tile = QLabel()
        self.tile.setObjectName("prompt_src_round")
        self.tile.setFixedSize(30, 30)
        self.tile.setAlignment(Qt.AlignCenter)
        row.addWidget(self.tile)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        self.title = _ElidedLabel()
        self.title.setObjectName("prompt_strip_title")
        self.subtitle = _ElidedLabel()
        self.subtitle.setObjectName("hint")
        texts.addWidget(self.title)
        texts.addWidget(self.subtitle)
        row.addLayout(texts, 1)
        self.badge = QLabel()
        self.badge.setObjectName("prompt_badge")
        self.badge.setAlignment(Qt.AlignCenter)
        row.addWidget(self.badge)
        self.close_btn = QToolButton()
        self.close_btn.setObjectName("prompt_tool")
        self.close_btn.setIcon(icons.icon("close", muted))
        self.close_btn.setAccessibleName("Schließen, später fragen")
        self.close_btn.setToolTip("Alle schließen, später fragen" if close_all
                                  else "Diese Nachfrage schließen, später fragen")
        self.close_btn.clicked.connect(lambda: self.dismissed.emit())
        row.addWidget(self.close_btn)
        col.addLayout(row)
        bar = _TimerBar()
        bar_row = QHBoxLayout()
        bar_row.setContentsMargins(24, 0, 24, 2)  # innerhalb der runden Enden
        bar_row.addWidget(bar)
        col.addLayout(bar_row)
        # angedeutete weitere Nachfragen dahinter
        self.peeks = []
        for inset in (14, 28):
            peek = QFrame()
            peek.setObjectName("prompt_peek")
            peek.setFixedSize(self.WIDTH - 2 * inset, 6)
            outer.addWidget(peek, 0, Qt.AlignHCenter)
            self.peeks.append(peek)
        self._accent = accent
        self.set_entry(entry, count)
        self._setup_autohide(timeout, keep_while_active, bar)

    def set_entry(self, entry, count):
        self.entry = entry
        self.tile.setPixmap(icons.icon(source_icon_name(entry), self._accent).pixmap(16, 16))
        label = entry_label(entry)
        head, _sep, when = label.rpartition(" · ")
        self.title.set_full_text(head or label)
        self.subtitle.set_full_text(f"{when} · Klicken zum Eintragen")
        self.badge.setText(str(count))
        self.badge.setVisible(count > 1)
        self.badge.setAccessibleName(f"{count} offene Nachfragen")
        for i, peek in enumerate(self.peeks):
            peek.setVisible(count > i + 1)
        self.adjustSize()

    def eventFilter(self, obj, event):
        if obj is self.strip:
            if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                self.opened.emit()
                return True
            if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
                self.opened.emit()
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.dismissed.emit()
            return
        super().keyPressEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self._dock()
        QTimer.singleShot(0, self._dock)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._dock()

    def _timed_out(self):
        self.timed_out.emit()

    def close_silently(self):
        self._hide_timer.stop()
        self.blockSignals(True)
        self.close()
        self.deleteLater()
