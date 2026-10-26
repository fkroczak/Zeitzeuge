"""Wochenabschluss: Buchungsquote je Tag, 7-Tage-Wert, Lücken, Offenes und Prüfungen.

Die Rechnung steht in booking_rate.py und day_checks.py (ohne Qt). Hier wird nur
gesammelt (Personalzeit, Matrix42-Buchungen, PC-Aktivität, offene Tätigkeiten aus dem
Hauptfenster) und gezeigt. Dazu gehört der kompakte Hinweis in der Statuszeile.
"""
from datetime import datetime, timedelta

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QHeaderView, QLabel, QListWidget, QListWidgetItem,
                               QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QToolButton,
                               QVBoxLayout)

import booking_rate as br
import day_checks
import icons
import m42_booking
from theme import THEMES
from timeline_only import work_hours

DAY_NAMES = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
TIME_FMT = "%Y-%m-%d %H:%M:%S"


def target(config):
    try:
        value = int(config.get("booking_target_percent", br.TARGET_PERCENT))
    except (TypeError, ValueError):
        return br.TARGET_PERCENT
    return value if 1 <= value <= 200 else br.TARGET_PERCENT


def _bookings(window, date_str):
    getter = getattr(window, "_m42_bookings", None)
    return getter(date_str) if getter else None


def day_inputs(window, date_str, now):
    """Alles, was die Rechnung für einen Tag braucht.

    -> dict(spans, running, from_itm, itm_day, bookings, planned_end)"""
    day = datetime.strptime(date_str, "%Y-%m-%d")
    itm_day = window.personal_day_for(date_str) if hasattr(window, "personal_day_for") else None
    planned = work_hours(window.config, day.weekday())
    planned_end = day + timedelta(minutes=planned[1]) if planned else None
    if itm_day is not None:  # aus ITM gelesen (ohne Zeiten = nicht gestempelt, z. B. Urlaub)
        spans, running = br.itm_spans(itm_day, now)
        from_itm = True
    else:
        spans, running, from_itm = [], False, False
        if planned and planned[1] > planned[0]:
            spans = [(day + timedelta(minutes=planned[0]), day + timedelta(minutes=planned[1]))]
    if date_str == now.strftime("%Y-%m-%d"):
        spans = [(a, min(b, now)) for a, b in spans if min(b, now) > a]
    elif date_str > now.strftime("%Y-%m-%d"):
        spans = []
    return {"spans": spans, "running": running, "from_itm": from_itm, "itm_day": itm_day,
            "bookings": _bookings(window, date_str), "planned_end": planned_end}


def rate_for(window, date_str, now, inputs=None):
    inputs = inputs or day_inputs(window, date_str, now)
    return br.day_rate(date_str, inputs["spans"], inputs["bookings"], now,
                       from_itm=inputs["from_itm"], day=inputs["itm_day"],
                       running=inputs["running"],
                       gap_minutes=window.config.get("m42_gap_minutes", 5))


def seven_for(window, now):
    """7-Tage-Wert: letzte 7 gestempelte Tage ab heute."""
    rates = [rate_for(window, d, now) for d in br.lookback_dates(now.strftime("%Y-%m-%d"))]
    return br.seven_days(rates)


def checks_for(window, date_str, now, inputs=None, rate=None):
    """Prüfungen eines Tages (day_checks) mit den Daten des Hauptfensters."""
    inputs = inputs or day_inputs(window, date_str, now)
    pc = []
    timeline = getattr(window, "timeline", None)
    if timeline is not None and inputs["from_itm"]:
        for e in timeline.pc_entries_for(QDate.fromString(date_str, "yyyy-MM-dd"), min_seconds=60):
            try:
                pc.append((datetime.strptime(e["start"], TIME_FMT), datetime.strptime(e["end"], TIME_FMT)))
            except (KeyError, ValueError):
                continue
    return day_checks.check_day(
        inputs["spans"], pc, inputs["bookings"], rate, target(window.config),
        from_itm=inputs["from_itm"], pc_min_minutes=window.config.get("day_checks_pc_minutes", 10),
        booking_min_minutes=window.config.get("m42_gap_minutes", 5), now=now)


def has_m42(window):
    return bool(getattr(window, "m42_reader", None) or getattr(window, "imported", None))


# ------------------------------------------------------------------ Statuszeile


def status_text(window, now=None):
    """(Text, Stufe, Hinweis) für die Statuszeile oder None, wenn Matrix42 nichts liefert."""
    now = now or datetime.now()
    goal = target(window.config)
    today = rate_for(window, now.strftime("%Y-%m-%d"), now)
    seven = seven_for(window, now)
    if today.percent is None and seven.percent is None:
        return None  # Matrix42 liefert (noch) nichts, das sich rechnen lässt
    parts = []
    if today.percent is not None:
        parts.append(f"Quote heute {br.percent_text(today.percent)}")
    parts.append(f"7 Tage {br.percent_text(seven.percent)}")
    lvl = br.level(seven.percent if seven.percent is not None else today.percent, goal)
    text = " · ".join(parts) + f"  {br.LEVELS[lvl][0]}"
    tip = [f"Ziel: {goal} % der Personalzeit in Matrix42 buchen"]
    if today.percent is not None:
        tip.append(f"Heute: {br.percent_text(today.percent)} – {br.level_text(br.level(today.percent, goal), goal)}")
    elif today.personal_seconds > 0 and not today.m42_read:
        tip.append("Heute: Matrix42 nicht gelesen")
    tip.append(f"Letzte {len(seven.window)} gestempelte Tage: {br.percent_text(seven.percent)} – "
               f"{br.level_text(br.level(seven.percent, goal), goal)}")
    if seven.unread:
        tip.append(f"{len(seven.unread)} Tag(e) ohne Matrix42-Daten zählen nicht mit")
    tip.append("Klick: Wochenabschluss")
    return text, lvl, "\n".join(tip)


def update_rate_button(window):
    """Knopf "Quote heute … · 7 Tage …" in der Statuszeile setzen oder ausblenden."""
    button = getattr(window, "rate_button", None)
    if button is None:
        return
    info = None
    if window.config.get("booking_rate_status", True) and has_m42(window):
        try:
            info = status_text(window)
        except (KeyError, TypeError, ValueError):
            info = None
    button.setVisible(info is not None)
    if info is None:
        return
    text, lvl, tip = info
    button.setText(text)
    button.setToolTip(tip)
    button.setAccessibleName(f"Buchungsquote: {text.rsplit('  ', 1)[0]}, "
                             f"{br.LEVELS[lvl][1]}. Wochenabschluss öffnen")
    name = f"rate_{lvl}" if lvl != "none" else ""
    if button.objectName() != name:
        button.setObjectName(name)
        button.style().unpolish(button)
        button.style().polish(button)


# ------------------------------------------------------------------ Dialog


class WeekDialog(QDialog):
    """Montag bis Freitag (Sa/So, wenn gestempelt oder gebucht) mit Blättern."""

    COLUMNS = ["Tag", "Personalzeit", "Gebucht", "Quote", "Nicht gebucht", "Offen"]

    def __init__(self, window, day=None, now=None):
        super().__init__(window)
        self.window = window
        self.now = now
        self.setWindowTitle("Wochenabschluss")
        self.setMinimumWidth(760)
        self.monday = datetime.strptime(br.week_dates(day or datetime.now().strftime("%Y-%m-%d"))[0],
                                        "%Y-%m-%d")
        self.rows = []  # Datum je Tabellenzeile
        dark = getattr(window, "dark_mode", False)
        self.theme = THEMES["dark" if dark else "light"]
        layout = QVBoxLayout(self)

        nav = QHBoxLayout()
        self.prev_button = QToolButton(self)
        self.prev_button.setIcon(icons.icon("prev", self.theme["text"]))
        self.prev_button.setAccessibleName("Vorherige Woche")
        self.prev_button.setToolTip("Vorherige Woche (Bild auf)")
        self.prev_button.clicked.connect(lambda: self.move_week(-1))
        self.next_button = QToolButton(self)
        self.next_button.setIcon(icons.icon("next", self.theme["text"]))
        self.next_button.setAccessibleName("Nächste Woche")
        self.next_button.setToolTip("Nächste Woche (Bild ab)")
        self.next_button.clicked.connect(lambda: self.move_week(1))
        self.title = QLabel(self)
        font = self.title.font()
        font.setBold(True)
        self.title.setFont(font)
        nav.addWidget(self.prev_button)
        nav.addWidget(self.title, 1, Qt.AlignCenter)
        nav.addWidget(self.next_button)
        layout.addLayout(nav)
        for key, step in ((QKeySequence.MoveToPreviousPage, -1), (QKeySequence.MoveToNextPage, 1)):
            action = QAction(self)
            action.setShortcut(key)
            action.triggered.connect(lambda _c=False, s=step: self.move_week(s))
            self.addAction(action)

        self.table = QTableWidget(0, len(self.COLUMNS), self)
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAccessibleName("Tage der Woche")
        self.table.setAccessibleDescription("Enter oder Doppelklick zeigt den Tag im Hauptfenster.")
        header = self.table.horizontalHeader()
        for col in range(len(self.COLUMNS)):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        self.table.cellDoubleClicked.connect(lambda row, _c: self.open_day(row))
        enter = QAction("&Tag zeigen", self.table)
        enter.setShortcuts([QKeySequence(Qt.Key_Return), QKeySequence(Qt.Key_Enter)])
        enter.setShortcutContext(Qt.WidgetShortcut)
        enter.triggered.connect(lambda: self.open_day(self.table.currentRow()))
        self.table.addAction(enter)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setMinimumHeight(28 * 7 + 40)  # die ganze Woche ohne Blättern
        layout.addWidget(self.table, 2)

        self.seven_label = QLabel(self)
        self.seven_label.setWordWrap(True)
        self.seven_label.setTextFormat(Qt.PlainText)
        layout.addWidget(self.seven_label)

        hints_label = QLabel("&Hinweise der Woche:", self)
        self.hints = QListWidget(self)
        hints_label.setBuddy(self.hints)
        self.hints.itemActivated.connect(self.open_hint)
        layout.addWidget(hints_label)
        self.hints.setMinimumHeight(90)
        layout.addWidget(self.hints, 1)

        form = QFormLayout()
        self.target_spin = QSpinBox(self)
        self.target_spin.setRange(1, 200)
        self.target_spin.setSuffix(" %")
        self.target_spin.setValue(target(window.config))
        self.target_spin.setToolTip("So viel der Personalzeit solltest du in Matrix42 buchen")
        self.target_spin.valueChanged.connect(self.change_target)
        form.addRow("&Ziel je Tag:", self.target_spin)
        layout.addLayout(form)
        legend = QLabel(f"Quote = in Matrix42 gebucht ÷ Personalzeit. Unter {br.RED_BELOW} % rot (✗), "
                        "bis unter Ziel gelb (!), Ziel bis 100 % grün (✓), darüber dunkelgrün (✓✓). "
                        "Heute zählt bis jetzt.", self)
        legend.setObjectName("hint")
        legend.setWordWrap(True)
        layout.addWidget(legend)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        self.book_button = QPushButton("In Matrix42 &buchen (kommt bald)", self)
        self.book_button.setEnabled(m42_booking.AVAILABLE)
        self.book_button.setToolTip(m42_booking.COMING_SOON)
        buttons.addButton(self.book_button, QDialogButtonBox.ActionRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.fill()

    # ---- Daten

    def _now(self):
        return self.now or datetime.now()

    def move_week(self, step):
        self.monday += timedelta(days=7 * step)
        self.fill()

    def change_target(self, value):
        self.window.config["booking_target_percent"] = value
        import main_timeline as mt  # erst hier: main_timeline lädt dieses Modul
        mt.save_config(self.window.config)
        self.fill()

    def fill(self):
        now = self._now()
        goal = target(self.window.config)
        dates = [(self.monday + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
        sunday = datetime.strptime(dates[-1], "%Y-%m-%d")
        self.title.setText(f"Woche {self.monday.isocalendar()[1]} · "
                           f"{self.monday:%d.%m.} – {sunday:%d.%m.%Y}")
        self.next_button.setEnabled(self.monday + timedelta(days=7) <= now)
        for reader in (getattr(self.window, "all_readers", lambda: [])() or []):
            for d in dates:  # fehlende Tage im Hintergrund nachlesen (ITM liest je Tag)
                if d <= now.strftime("%Y-%m-%d"):
                    reader.want(d)
        self.table.setRowCount(0)
        self.hints.clear()
        self.rows = []
        for i, d in enumerate(dates):
            inputs = day_inputs(self.window, d, now)
            rate = rate_for(self.window, d, now, inputs)
            weekend = i >= 5
            if weekend and rate.personal_seconds <= 0 and not (inputs["bookings"] or []):
                continue
            self._add_row(d, inputs, rate, goal, now)
        seven = seven_for(self.window, now)
        text = (f"7-Tage-Wert (letzte {len(seven.window)} gestempelte Tage bis heute): "
                f"{br.percent_text(seven.percent)} – {br.level_text(br.level(seven.percent, goal), goal)}")
        if seven.days:
            text += (f". Gebucht {br.duration(seven.booked_seconds)} von "
                     f"{br.duration(seven.personal_seconds)} Personalzeit")
        if seven.unread:
            names = ", ".join(f"{datetime.strptime(r.date, '%Y-%m-%d'):%d.%m.}" for r in
                              sorted(seven.unread, key=lambda r: r.date))
            text += f". Ohne Matrix42-Daten (zählen nicht): {names}"
        self.seven_label.setText(text if text.endswith(".") else text + ".")
        if not self.hints.count():
            item = QListWidgetItem("Keine Hinweise für diese Woche.")
            item.setFlags(Qt.ItemIsEnabled)
            self.hints.addItem(item)

    def _add_row(self, d, inputs, rate, goal, now):
        day = datetime.strptime(d, "%Y-%m-%d")
        name = DAY_NAMES[day.weekday()]
        future = d > now.strftime("%Y-%m-%d")
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.rows.append(d)
        kind = "Personalzeit" if rate.from_itm else "Arbeitszeit (Einstellungen)"
        personal = br.duration(rate.personal_seconds) if rate.personal_seconds else "–"
        if rate.personal_seconds and not rate.from_itm:
            personal += " (Arbeitszeit lt. Einstellungen)"
        elif rate.running:
            personal += " (eingestempelt)"
        lvl = br.level(rate.percent, goal)
        if future:
            quote, booked, gap = "–", "–", "–"
        elif not rate.m42_read:
            quote, booked, gap = "– Matrix42 nicht gelesen", "–", "–"
        elif rate.personal_seconds <= 0:
            quote, booked, gap = f"– keine {kind}", br.duration(rate.booked_seconds), "–"
        else:
            quote = f"{br.percent_text(rate.percent)}  {br.level_text(lvl, goal)}"
            booked = br.duration(rate.booked_seconds)
            gap = br.duration(rate.gap_seconds) if rate.gaps else "–"
        open_items = []
        if not future:
            candidates = getattr(self.window, "doc_candidates", None)
            open_items = candidates(d) if candidates else []
        cells = [f"{name[:2]} {day:%d.%m.}", personal, booked, quote, gap,
                 f"{len(open_items)} offen" if open_items else "–"]
        for col, text in enumerate(cells):
            self.table.setItem(row, col, QTableWidgetItem(text))
        if lvl != "none" and not future and rate.personal_seconds > 0:
            # Farbige Fläche aus THEMES (Stylesheet QLabel#rate_…); Text bleibt auch in der Zelle
            label = QLabel(quote, self.table)
            label.setTextFormat(Qt.PlainText)
            label.setObjectName(f"rate_{lvl}")
            self.table.setCellWidget(row, 3, label)
            label.ensurePolished()  # fett aus dem Stylesheet, erst dann stimmt die Breite
            header = self.table.horizontalHeader()  # passt sich sonst nur dem Zellentext an
            header.setSectionResizeMode(3, QHeaderView.Interactive)
            self.table.setColumnWidth(3, max(self.table.columnWidth(3), label.sizeHint().width() + 24))
        if future:
            return
        # Hinweise des Tages
        hints = []
        if rate.gaps and rate.gap_seconds:
            hints.append(f"{br.duration(rate.gap_seconds)} nicht gebucht")
        if open_items:
            hints.append(f"{len(open_items)} Tätigkeit{'en' if len(open_items) > 1 else ''} "
                         "nicht dokumentiert")
        if rate.personal_seconds > 0 and not rate.m42_read:
            hints.append("Matrix42 nicht gelesen")
        if self.window.config.get("day_checks_enabled", True):
            hints += [f.text for f in checks_for(self.window, d, now, inputs, rate)
                      if f.kind != "rate"]  # Quote steht schon in der Tabelle
        for text in hints:
            item = QListWidgetItem(f"{name}: {text}")
            item.setData(Qt.UserRole, d)
            self.hints.addItem(item)

    # ---- Springen

    def open_day(self, row):
        if 0 <= row < len(self.rows):
            self._jump(self.rows[row])

    def open_hint(self, item):
        d = item.data(Qt.UserRole)
        if d:
            self._jump(d)

    def _jump(self, d):
        date_edit = getattr(self.window, "date_edit", None)
        if date_edit is not None:
            date_edit.setDate(QDate.fromString(d, "yyyy-MM-dd"))
        self.accept()
