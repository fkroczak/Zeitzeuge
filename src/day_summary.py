"""Kopf der Tagesansicht (Design „Companion“): Kennzahlen und Filter über der Tagesliste.

    Erfasst 5:10 h von 8:00 h   Offen 14 Einträge [Jetzt eintragen]   Vorschläge 3 [Ansehen]
    Nach Kunde  [Müller GmbH 2:15] [Kanzlei Schmidt 1:05] [+3 weitere 0:40]   (Chips, höchstens 2 Zeilen)

Darunter (über der Tagesliste) eine Reihe Chips für die häufigsten Ansichten:
    Einträge  [Alle]  [Offen / Doku 14]  [Vorschläge 3]  [Telefonate]  [Arbeitsblöcke]

Die Zahlen rechnet summary() ohne Qt aus (testbar), die Widgets zeigen sie nur an.
"""

import html

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QSizePolicy,
                               QToolButton, QVBoxLayout, QWidget)

from flow_layout import FlowLayout
import skeleton
import timefmt
from theme import SPACE_XS, SPACE_S, SPACE_M, SPACE_L

TIME_FMT = "%Y-%m-%d %H:%M:%S"

# Alle Ansichten der Tagesliste als Chips (Schlüssel aus DayListMixin.VIEWS); das Menü
# „Ansicht“ führt sie nicht noch einmal. Nach „Telefonate“ eine Lücke: Logs | Tätigkeiten.
CHIP_VIEWS = [("grouped", "Alle"), ("single", "Einzeln"), ("blocks", "Arbeitsblöcke"),
              ("calls", "Telefonate"), ("doc", "Dokumentation"), ("rules", "Zuordnung ohne KI"),
              ("ai", "KI-Vorschläge"), ("m42", "Matrix42-Abgleich")]
GROUP_GAP_AFTER = "calls"


def _seconds(entries):
    """Belegte Sekunden ohne Doppelzählung überlappender Einträge."""
    spans = sorted((timefmt.parse(e["start"]), timefmt.parse(e["end"]))
                   for e in entries if e.get("start") and e.get("end"))
    total, cur_s, cur_e = 0.0, None, None
    for s, e in spans:
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                total += (cur_e - cur_s).total_seconds()
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        total += (cur_e - cur_s).total_seconds()
    return total


def hm(seconds):
    """Sekunden als 'h:mm h' (wie im Rest von Zeitzeuge)."""
    minutes = int(round(seconds / 60))
    return f"{minutes // 60}:{minutes % 60:02d} h"


def summary(doc_band, ai_entries, target_minutes, top=None):
    """Kennzahlen des Tages.

    doc_band:   Einträge der Zeile Dokumentation (doc = eingetragen, open = offen)
    ai_entries: KI-Vorschläge des Tages (status '', 'übernommen' oder 'verworfen')
    target_minutes: Bezug des Tages (gestempelte Personalzeit oder Arbeitszeit), 0 = unbekannt
    """
    done = [e for e in doc_band if e.get("doc")]
    opened = [e for e in doc_band if e.get("open")]
    waiting = [e for e in ai_entries if e.get("status") not in ("übernommen", "verworfen")]
    by_customer = {}
    for e in done:
        name = (e.get("customer_name") or "").strip() or "ohne Kunde"
        by_customer.setdefault(name, []).append(e)
    customers = sorted(((name, _seconds(items)) for name, items in by_customer.items()),
                       key=lambda x: -x[1])[:top]
    return {
        "booked_s": _seconds(done),
        "target_s": max(0, target_minutes or 0) * 60,
        "open": len(opened),
        "suggestions": len(waiting),
        "customers": customers,
    }


class _ClickChip(QLabel):
    """Kunden-Chip: Klick, Enter oder Leertaste melden sich über clicked."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(event)


class _CustomerChips(QWidget):
    """Kunden als Chips „Name 1:14“, die größten zuerst, höchstens ROWS Zeilen. Was nicht passt,
    steht im letzten Chip „+3 · 0:45“ (Tooltip: die übrigen Kunden). Ansprechperson hinter
    „ - “ (z. B. „Jugendhilfe Olsberg - Jörg Spiekermann“) nur im Tooltip."""

    ROWS = 2
    GAP = 6
    chosen = Signal(str)  # Kunde angeklickt (voller Name wie in der Dokumentation)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items, self._empty = [], ""
        self._active = ""  # Kunde, auf den die Tagesliste gerade gefiltert ist
        self._chips = []
        self._rows_used = 1
        self.empty_label = QLabel(self)
        self.empty_label.setObjectName("card_title")
        self.empty_label.setProperty("empty", True)
        self.setMinimumWidth(40)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def set_customers(self, items, empty):
        """items: [(Name, Sekunden)], größte zuerst."""
        self._items, self._empty = list(items), empty
        self.setToolTip("")
        self.empty_label.setText(empty)
        self._relayout()

    def set_active(self, name):
        """Gefilterten Kunden hervorheben (leer: kein Filter)."""
        self._active = name or ""
        for i, (full, _sec) in enumerate(self._items):
            if i < len(self._chips):
                self._mark(self._chips[i], full == self._active)

    @staticmethod
    def _mark(chip, on):
        if chip.property("on") != on:
            chip.setProperty("on", on)
            chip.style().unpolish(chip)
            chip.style().polish(chip)

    def parts(self):
        """Sichtbare Chip-Texte (für Tests und Vorlesen)."""
        return [c.accessibleName() for c in self._chips if c.isVisible()]

    def _chip(self, index):
        while len(self._chips) <= index:
            chip = _ClickChip(self)
            chip.setObjectName("customer_chip")
            chip.setTextFormat(Qt.RichText)
            chip.setCursor(Qt.PointingHandCursor)
            chip.clicked.connect(lambda i=len(self._chips): self._clicked(i))
            self._chips.append(chip)
        return self._chips[index]

    def _clicked(self, index):
        if index < len(self._items):
            self.chosen.emit(self._items[index][0])
        else:  # „+N weitere“: kein einzelner Kunde, aufgeklappt im Tooltip
            chip = self._chips[index]
            from PySide6.QtWidgets import QToolTip
            QToolTip.showText(chip.mapToGlobal(chip.rect().bottomLeft()), chip.toolTip(), chip)

    def _set_chip(self, chip, name, time, tip, room):
        fm = chip.fontMetrics()
        bold = QFont(chip.font())
        bold.setBold(True)
        time_w = QFontMetrics(bold).horizontalAdvance(time)
        pad = 2 * 10 + 2 + 8  # Innenabstand links/rechts, Rand, Abstand Name–Zeit
        shown = fm.elidedText(name, Qt.ElideRight, max(20, room - time_w - pad)) if name else ""
        chip.setText(f"{html.escape(shown)}&nbsp;&nbsp;<b>{html.escape(time)}</b>" if shown
                     else f"<b>{html.escape(time)}</b>")
        chip.setToolTip(tip)
        chip.setAccessibleName(f"{name} {time}".strip())
        chip.adjustSize()
        # Nie breiter als der Platz: unter Windows meldet das Etikett mit RichText teils mehr Breite,
        # als der gekürzte Text braucht (startup_skeleton_test auf CI: 230 px Chip in 202 px)
        hint = chip.sizeHint()
        size = QSize(min(hint.width(), max(40, room)), hint.height())
        chip.resize(size)
        return size

    def _relayout(self):
        for chip in self._chips:
            chip.hide()
        self.empty_label.setVisible(not self._items)
        if not self._items:
            self.empty_label.setGeometry(0, 0, self.width(), self.empty_label.sizeHint().height())
            self._set_rows(1)
            return
        width = max(40, self.width())
        n = len(self._items)
        sizes = []
        for i, (full, sec) in enumerate(self._items):
            name = full.split(" - ")[0].strip() or full
            on = full == self._active
            tip = f"{full}: {hm(sec)}\n" + ("Klick: Filter aufheben" if on else "Klick: nur diesen Kunden in der Liste")
            sizes.append(self._set_chip(self._chip(i), name, hm(sec)[:-2], tip, width))
            self._mark(self._chip(i), on)
        # So viele Kunden wie möglich, dahinter „+N weitere“, alles in höchstens ROWS Zeilen
        for k in range(n, 0, -1):
            rest = self._items[k:]
            widths = [sz.width() for sz in sizes[:k]]
            if rest:
                total = sum(sec for _n, sec in rest)
                text = f"+{len(rest)} weitere" if len(rest) > 1 else "+1 weiterer"
                tip = "\n".join(f"{name}: {hm(sec)}" for name, sec in rest)
                widths.append(self._set_chip(self._chip(n), text, hm(total)[:-2], tip, width).width())
                self._mark(self._chip(n), False)
            spots = self._place(widths, width)
            if spots is not None:
                break
        else:  # nicht einmal ein Kunde und „+N“ passen: untereinander
            spots = [(0, 0), (0, 1)][:len(widths)]
        height = sizes[0].height()
        chips = self._chips[:k] + ([self._chips[n]] if k < n else [])
        spots, widths = self._justify(spots, widths, width)
        for chip, (x, row), w in zip(chips, spots, widths):
            chip.setAlignment(Qt.AlignCenter)
            chip.resize(w, height)
            chip.move(x, row * (height + self.GAP))
            chip.show()
        self._set_rows(spots[-1][1] + 1, height)

    JUSTIFY_MAX = 0.25  # höchstens so viel der Breite auf die Chips einer Reihe verteilen

    def _justify(self, spots, widths, room):
        """Bei zwei Reihen beide bündig auf volle Breite (Blocksatz statt Flattersatz rechts).
        Eine Reihe mit viel Luft (z. B. nur ein Chip in Reihe 2) bleibt links, sonst würden die
        Chips riesig. Ergebnis: neue Positionen und Breiten."""
        rows = {}
        for i, (_x, row) in enumerate(spots):
            rows.setdefault(row, []).append(i)
        if len(rows) < 2:
            return spots, widths
        spots, widths = list(spots), list(widths)
        for members in rows.values():
            used = sum(widths[i] for i in members) + self.GAP * (len(members) - 1)
            extra = room - used
            if extra <= 0 or extra > self.JUSTIFY_MAX * room:
                continue
            x = 0
            for j, i in enumerate(members):
                # Rest der Teilung an die letzten Chips, damit die Reihe genau rechts endet
                add = extra // len(members) + (1 if j >= len(members) - extra % len(members) else 0)
                widths[i] += add
                spots[i] = (x, spots[i][1])
                x += widths[i] + self.GAP
        return spots, widths

    def _place(self, widths, room):
        """Positionen (x, Zeile) oder None, wenn es mehr als ROWS Zeilen bräuchte."""
        spots, x, row = [], 0, 0
        for w in widths:
            if x and x + w > room:
                row, x = row + 1, 0
                if row >= self.ROWS:
                    return None
            spots.append((x, row))
            x += w + self.GAP
        return spots

    def _set_rows(self, rows, chip_height=None):
        chip_height = chip_height or self.empty_label.sizeHint().height()
        need = rows * chip_height + (rows - 1) * self.GAP
        if self.minimumHeight() != need:
            self.setMinimumHeight(need)
            self.updateGeometry()

    def sizeHint(self):
        return QSize(400, self.minimumHeight())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if event.size().width() != event.oldSize().width():
            self._relayout()


FOOT_H = 24  # untere Zeile der Zahlen-Kacheln: so hoch wie ein Kunden-Chip


class _Kpi(QFrame):
    """Kennzahl als Karte, zweizeilig wie die Kunden-Chips daneben:

        Erfasst                      Offen
        3:41 h  von 8:34 h           4  Einträge        <- Höhe der ersten Chip-Reihe
        ████░░░░░░░░░░  43 %         [Jetzt eintragen]  <- unten, Höhe der zweiten Chip-Reihe
    """

    def __init__(self, label, parent=None, action=None, customers=False):
        super().__init__(parent)
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_L, SPACE_M, SPACE_L, SPACE_M)
        layout.setSpacing(SPACE_XS)
        head = QLabel(label, self)
        head.setObjectName("kpi_label")
        layout.addWidget(head)
        row = QHBoxLayout()
        row.setSpacing(SPACE_S)
        self.value = _CustomerChips(self) if customers else QLabel("–", self)
        if not customers:
            self.value.setObjectName("kpi_value")
        row.addWidget(self.value, 1 if customers else 0)
        # Bis die Zahlen da sind: Umriss statt „–“ (skeleton.py)
        self.placeholder = skeleton.Bar(160 if customers else 64, 26, self)
        self.value.hide()
        row.addWidget(self.placeholder)
        self._row = row
        self.extra = QLabel("", self)
        self.extra.setObjectName("kpi_label")
        row.addWidget(self.extra, 0 if customers else 1)
        self.button = None
        layout.addLayout(row)
        # Fußzeile unten: keine leere Fläche, wenn „Nach Kunde“ zwei Reihen Chips hat
        self.foot = QHBoxLayout()
        self.foot.setSpacing(SPACE_S)
        if action:
            self.button = QToolButton(self)
            self.button.setObjectName("link")
            self.button.setText(action)
            self.button.setCursor(Qt.PointingHandCursor)
            self.foot.addWidget(self.button)
            self.foot.addStretch(1)
        layout.addStretch(1)  # Überschriften oben auf einer Höhe, Fußzeile unten
        if not customers:
            holder = QWidget(self)
            holder.setFixedHeight(FOOT_H)
            holder.setLayout(self.foot)
            self.foot.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(holder)
        self.bar = None
        self.percent = None

    def loaded(self):
        """Zahlen sind da: Umriss weg, Wert zeigen."""
        if self.placeholder is not None:
            self.placeholder.done()
            self._row.removeWidget(self.placeholder)
            self.placeholder.deleteLater()
            self.placeholder = None
            self.value.show()

    def add_progress(self):
        """Fortschritt in der Fußzeile: Balken und Anteil in Prozent."""
        self.bar = QProgressBar(self)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        self.bar.setRange(0, 100)
        self.bar.setAccessibleName("Anteil erfasst")
        self.percent = QLabel("", self)
        self.percent.setObjectName("kpi_label")
        self.foot.addWidget(self.bar, 1)
        self.foot.addWidget(self.percent)


class RateKpi(QFrame):
    """Kachel Buchungsquote:   Buchungsquote
                              64 % ! heute | 87 % ✓ 7 Tage   (Zahl in der Farbe der Stufe)

    Anklickbar (Maus, Enter, Leertaste) wie ein Knopf: Signal clicked."""

    clicked = Signal()
    SYMBOLS = {"low": "✗", "mid": "!", "ok": "✓", "over": "✓✓", "none": ""}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.level = "none"
        self._text = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_L, SPACE_M, SPACE_L, SPACE_M)
        layout.setSpacing(SPACE_XS)
        title = QLabel("Buchungsquote", self)  # Überschrift wie bei den anderen Kacheln
        title.setObjectName("kpi_label")
        layout.addWidget(title)
        # Zwei Spalten: Zahl oben (Höhe der Werte in den anderen Kacheln), „heute“ / „7 Tage“
        # unten in der Fußzeile (wie „Jetzt eintragen“), dazwischen ein Strich über beide Zeilen
        grid = QGridLayout()
        grid.setHorizontalSpacing(SPACE_M)
        grid.setVerticalSpacing(0)
        grid.setRowStretch(1, 1)
        self.columns = {}
        for i, key in enumerate(("today", "seven")):
            col = 2 * i
            if i:
                line = QFrame(self)
                line.setObjectName("divider")
                line.setFixedWidth(1)
                grid.addWidget(line, 0, col - 1, 3, 1)
            value = QLabel("–", self)
            value.setObjectName("rate_value_none")
            head = QLabel("heute" if key == "today" else "7 Tage", self)
            head.setObjectName("kpi_label")
            head.setFixedHeight(FOOT_H)
            head.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            grid.addWidget(value, 0, col)
            grid.addWidget(head, 2, col)
            self.columns[key] = (head, value)
        grid.setColumnStretch(4, 1)
        layout.addLayout(grid, 1)

    def show_rate(self, info):
        """info: week_dialogs.rate_info (label, today, today_level, seven, seven_level, text, tip)."""
        self._text = info["text"]
        self.level = info["level"]
        for key in ("today", "seven"):
            head, value = self.columns[key]
            percent, lvl = info[key], info[f"{key}_level"]
            if key == "today":
                head.setText(info["label"])
            value.setText(f"{int(round(percent))} % {self.SYMBOLS[lvl]}".strip() if percent is not None else "–")
            name = f"rate_value_{lvl}"
            if value.objectName() != name:
                value.setObjectName(name)
                value.style().unpolish(value)
                value.style().polish(value)
        self.setToolTip(info["tip"])
        self.setAccessibleName(f"Buchungsquote: {info['text']}. Wochenabschluss öffnen")

    def text(self):
        """Ganzer Text, z. B. „Quote heute 64 % · 7 Tage 87 %  ✓“ (Hinweis, Tests)."""
        return self._text

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(event)


class DaySummary(QWidget):
    """Kennzahlen-Leiste über der Timeline."""

    open_clicked = Signal()
    suggestions_clicked = Signal()
    tickets_clicked = Signal()
    customer_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE_S, SPACE_S, SPACE_S, 0)
        layout.setSpacing(SPACE_S)
        self.booked = _Kpi("Erfasst", self)
        self.booked.add_progress()
        self.opened = _Kpi("Offen", self, "Jetzt eintragen")
        self.opened.button.clicked.connect(self.open_clicked)
        self.opened.button.setAccessibleName("Offene Tätigkeiten jetzt eintragen")
        self.suggest = _Kpi("Vorschläge", self, "Ansehen")
        self.suggest.button.clicked.connect(self.suggestions_clicked)
        self.suggest.button.setAccessibleName("KI-Vorschläge ansehen")
        self.customers = _Kpi("Nach Kunde", self, customers=True)
        self.customers.value.chosen.connect(self.customer_clicked)
        # Meine Tickets (Matrix42, Bearbeiter = ich): show_my_tickets füllt die Kachel,
        # ohne Matrix42 bleibt sie aus; Klick öffnet die Liste
        self.tickets = _Kpi("Meine Tickets", self, "Anzeigen")
        self.tickets.button.clicked.connect(self.tickets_clicked)
        self.tickets.button.setAccessibleName("Meine offenen Tickets anzeigen")
        self.tickets.loaded()  # kein Umriss: die Kachel erscheint erst mit Zahlen
        self.tickets.hide()
        # Buchungsquote (Matrix42 ÷ Personalzeit): week_dialogs.update_rate_button füllt die
        # Kachel und blendet sie ohne Matrix42 aus; Klick öffnet den Wochenabschluss
        self.rate = RateKpi(self)
        self.rate.hide()
        # Zahlen-Kacheln so breit wie ihr Inhalt (keine leeren Flächen), „Nach Kunde“ füllt
        # den Rest. Im schmalen Fenster dürfen alle schrumpfen (Reflow, Mindestbreite klein).
        for w in (self.booked, self.rate, self.opened, self.suggest, self.tickets):
            w.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
            w.setMinimumWidth(60)
            layout.addWidget(w, 0)
        self.customers.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout.addWidget(self.customers, 1)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def show_numbers(self, data):
        for kpi in (self.booked, self.opened, self.suggest, self.customers):
            kpi.loaded()
        booked, target = data["booked_s"], data["target_s"]
        self.booked.value.setText(hm(booked))
        basis = data.get("target_basis", "")  # „gestempelt“/„bis jetzt“ (ITM-Personalzeit) oder „Arbeitszeit“
        self.booked.extra.setText(f"von {hm(target)} {basis}".strip() if target else "")
        share = int(min(100, 100 * booked / target)) if target else 0
        self.booked.bar.setValue(share)
        self.booked.percent.setText(f"{round(100 * booked / target)} %" if target else "")
        tips = {"gestempelt": " im Verhältnis zur gestempelten Personalzeit (ITM)",
                "bis jetzt": " im Verhältnis zur Personalzeit bis jetzt (noch eingestempelt, läuft live)",
                "Arbeitszeit": " im Verhältnis zur eingestellten Arbeitszeit"}
        self.booked.setToolTip("Eingetragene Tätigkeiten des Tages" + (tips.get(basis, "") if target else ""))
        n = data["open"]
        self.opened.value.setText(str(n))
        self.opened.extra.setText("Eintrag" if n == 1 else "Einträge")
        self.opened.button.setVisible(bool(n))
        s = data["suggestions"]
        self.suggest.value.setText(str(s))
        self.suggest.extra.setText("wartet" if s == 1 else "warten")
        self.suggest.button.setVisible(bool(s))
        self.suggest.setVisible(bool(s))  # „0 warten“ ist nur Rauschen
        self.customers.value.set_customers(data["customers"],
                                           "Noch nichts eingetragen – hier steht später die Zeit je Kunde")


    def show_my_tickets(self, result):
        """result: M42Reader.my_tickets ({rows, error, at}) oder None (Kachel aus)."""
        if result is None:
            self.tickets.hide()
            return
        rows = result.get("rows")
        self.tickets.value.setText("–" if rows is None else str(len(rows)))
        self.tickets.extra.setText("offen" if rows is not None else "")
        tip = [f"Offene Tickets in Matrix42, bei denen du Bearbeiter bist (Stand {result.get('at', '')})"]
        tip += [f"{r['ticket']} · {r['subject']}" for r in (rows or [])[:10]]
        if rows and len(rows) > 10:
            tip.append(f"… und {len(rows) - 10} weitere")
        if result.get("error"):
            tip.append(f"⚠ {result['error']}")
        self.tickets.setToolTip("\n".join(tip))
        self.tickets.show()


class ViewChips(QWidget):
    """Reihe „Einträge [Alle] [Offen / Doku] …“ über der Tagesliste."""

    view_chosen = Signal(str)
    filter_cleared = Signal()  # „✕ Kunde“ angeklickt: Kundenfilter aufheben

    def __init__(self, parent=None):
        super().__init__(parent)
        # Fließend: im schmalen Fenster rücken die Chips in die nächste Zeile, statt dem
        # ganzen Fenster eine Mindestbreite aufzuzwingen (Reflow)
        layout = FlowLayout(self, spacing=6)
        layout.setContentsMargins(SPACE_XS, SPACE_S, SPACE_XS, SPACE_S)
        title = QLabel("Einträge", self)
        title.setObjectName("section_title")
        title.setContentsMargins(0, 0, SPACE_S, 0)
        layout.addWidget(title)
        self.buttons = {}
        for key, text in CHIP_VIEWS:
            b = QToolButton(self)
            b.setObjectName("chip")
            b.setCheckable(True)
            inner = QHBoxLayout(b)
            inner.setContentsMargins(10, 3, 10, 3)
            inner.setSpacing(6)
            b.chip_text = QLabel(text.replace("&", ""), b)
            b.chip_count = QLabel("", b)
            b.chip_count.setObjectName("chip_count")
            b.chip_count.hide()
            for lab in (b.chip_text, b.chip_count):
                lab.setAttribute(Qt.WA_TransparentForMouseEvents)
                inner.addWidget(lab)
            b.setCursor(Qt.PointingHandCursor)
            b.setAccessibleName(f"Ansicht {text}")
            b.clicked.connect(lambda _c=False, k=key: self.view_chosen.emit(k))
            layout.addWidget(b)
            self.buttons[key] = (b, text)
            if key == GROUP_GAP_AFTER:  # sichtbare Lücke zwischen den beiden Gruppen
                gap = QWidget(self)
                gap.setFixedWidth(8)
                layout.addWidget(gap)
        # Kundenfilter (Chip „Nach Kunde“ oben): angehakt, Klick hebt ihn auf
        self.filter_chip = QToolButton(self)
        self.filter_chip.setObjectName("filter_chip")
        self.filter_chip.setCursor(Qt.PointingHandCursor)
        self.filter_chip.clicked.connect(self.filter_cleared)
        self.filter_chip.hide()
        gap = QWidget(self)
        gap.setFixedWidth(8)
        layout.addWidget(gap)
        layout.addWidget(self.filter_chip)

    def show_filter(self, name):
        """Kundenfilter als Chip „Kunde ✕“ am Ende der Reihe (leer: ausgeblendet)."""
        self.filter_chip.setText(f"{name.split(' - ')[0]}  ✕" if name else "")
        self.filter_chip.setToolTip(f"Nur {name} – Klick zeigt wieder alle Kunden" if name else "")
        self.filter_chip.setAccessibleName(f"Kundenfilter {name} aufheben" if name else "")
        self.filter_chip.setVisible(bool(name))

    def show_state(self, view, counts=None):
        counts = counts or {}
        for key, (button, text) in self.buttons.items():
            n = counts.get(key)
            button.chip_count.setText(str(n) if n else "")
            button.chip_count.setVisible(bool(n))
            button.setChecked(key == view)
            button.setAccessibleName(f"Ansicht {text}" + (f", {n}" if n else ""))
            for lab in (button.chip_text, button.chip_count):
                lab.setProperty("on", key == view)
                lab.style().polish(lab)
            button.setMinimumSize(button.layout().sizeHint())

    def showEvent(self, event):
        # Breite der Chips schon vor den ersten Daten (Fenster mit Umrissen, skeleton.py):
        # erst jetzt gilt die Schrift aus dem Stylesheet
        for button, _text in self.buttons.values():
            for lab in (button.chip_text, button.chip_count):
                lab.ensurePolished()
            button.setMinimumSize(button.layout().sizeHint())
        super().showEvent(event)

    def set_tips(self, tips):
        """Erklärung je Ansicht beim Darüberfahren (view_help.help_text)."""
        for key, (button, _text) in self.buttons.items():
            if key in tips:
                button.setToolTip(tips[key])
