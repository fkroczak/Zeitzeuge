"""Kopf der Tagesansicht (Design „Companion“): Kennzahlen und Filter über der Tagesliste.

    Erfasst 5:10 h von 8:00 h   Offen 14 Einträge [Jetzt eintragen]   Vorschläge 3 [Ansehen]
    Nach Kunde  Müller GmbH 2:15 h · Kanzlei Schmidt 1:05 h

Darunter (über der Tagesliste) eine Reihe Chips für die häufigsten Ansichten:
    Einträge  [Alle]  [Offen / Doku 14]  [Vorschläge 3]  [Telefonate]  [Arbeitsblöcke]

Die Zahlen rechnet summary() ohne Qt aus (testbar), die Widgets zeigen sie nur an.
"""
from datetime import datetime

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QProgressBar, QSizePolicy,
                               QToolButton, QVBoxLayout, QWidget)

from flow_layout import FlowLayout

TIME_FMT = "%Y-%m-%d %H:%M:%S"

# Alle Ansichten der Tagesliste als Chips (Schlüssel aus DayListMixin.VIEWS); das Menü
# „Ansicht“ führt sie nicht noch einmal. Nach „Telefonate“ eine Lücke: Logs | Tätigkeiten.
CHIP_VIEWS = [("grouped", "Alle"), ("single", "Einzeln"), ("blocks", "Arbeitsblöcke"),
              ("calls", "Telefonate"), ("doc", "Dokumentation"), ("rules", "Zuordnung ohne KI"),
              ("ai", "KI-Vorschläge"), ("m42", "Matrix42-Abgleich")]
GROUP_GAP_AFTER = "calls"


def _seconds(entries):
    """Belegte Sekunden ohne Doppelzählung überlappender Einträge."""
    spans = sorted((datetime.strptime(e["start"], TIME_FMT), datetime.strptime(e["end"], TIME_FMT))
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


def summary(doc_band, ai_entries, target_minutes, top=8):
    """Kennzahlen des Tages.

    doc_band:   Einträge der Zeile Dokumentation (doc = eingetragen, open = offen)
    ai_entries: KI-Vorschläge des Tages (status '', 'übernommen' oder 'verworfen')
    target_minutes: Soll des Tages (Personalzeit oder Arbeitszeit), 0 = unbekannt
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


class _CustomerLine(QLabel):
    """Kunden nebeneinander; passt nicht alles, folgen ganze Kunden und „+2“ statt „WiRoPa 0:“."""

    SEP = "  ·  "

    def __init__(self, parent=None):
        super().__init__(parent)
        self._parts, self._empty = [], ""
        self.setTextFormat(Qt.PlainText)
        self.setMinimumWidth(40)

    def set_parts(self, parts, empty):
        self._parts, self._empty = list(parts), empty
        self.setToolTip("\n".join(self._parts))
        self._fit()

    def sizeHint(self):
        hint = super().sizeHint()
        text = self.SEP.join(self._parts) or self._empty
        hint.setWidth(self.fontMetrics().horizontalAdvance(text) + 4)
        return hint

    def minimumSizeHint(self):
        return QSize(40, super().minimumSizeHint().height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()

    def _fit(self):
        if not self._parts:
            self.setText(self._empty)
            return
        fm, room = self.fontMetrics(), self.width() - 4
        for n in range(len(self._parts), 0, -1):
            rest = len(self._parts) - n
            text = self.SEP.join(self._parts[:n]) + (f"{self.SEP}+{rest}" if rest else "")
            if fm.horizontalAdvance(text) <= room:
                break
        else:
            text = fm.elidedText(self._parts[0], Qt.ElideRight, room)
        if text != self.text():
            self.setText(text)


class _Kpi(QFrame):
    """Kennzahl als Karte: Name, Wert, Zusatz und optional ein Knopf."""

    def __init__(self, label, parent=None, action=None, customers=False):
        super().__init__(parent)
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        head = QLabel(label, self)
        head.setObjectName("kpi_label")
        layout.addWidget(head)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.value = _CustomerLine(self) if customers else QLabel("–", self)
        self.value.setObjectName("card_title" if customers else "kpi_value")
        row.addWidget(self.value, 1 if customers else 0)
        self.extra = QLabel("", self)
        self.extra.setObjectName("kpi_label")
        row.addWidget(self.extra, 0 if customers else 1)
        self.button = None
        if action:
            self.button = QToolButton(self)
            self.button.setObjectName("link")
            self.button.setText(action)
            self.button.setCursor(Qt.PointingHandCursor)
            row.addWidget(self.button)
        layout.addLayout(row)
        self.bar = None

    def add_progress(self):
        self.bar = QProgressBar(self)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(4)
        self.bar.setRange(0, 100)
        self.bar.setAccessibleName("Anteil erfasst")
        self.layout().addWidget(self.bar)


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
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        title = QLabel("Buchungsquote", self)  # Überschrift wie bei den anderen Kacheln
        title.setObjectName("kpi_label")
        layout.addWidget(title)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.columns = {}
        for i, key in enumerate(("today", "seven")):
            if i:
                line = QFrame(self)
                line.setObjectName("divider")
                line.setFixedWidth(1)
                row.addSpacing(8)
                row.addWidget(line)
                row.addSpacing(8)
            value = QLabel("–", self)
            value.setObjectName("rate_value_none")
            head = QLabel("heute" if key == "today" else "7 Tage", self)  # klein neben der Zahl
            head.setObjectName("kpi_label")
            row.addWidget(value)
            row.addWidget(head, 0, Qt.AlignBottom)
            self.columns[key] = (head, value)
        row.addStretch(1)
        layout.addLayout(row)

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

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 0)
        layout.setSpacing(8)
        self.booked = _Kpi("Erfasst", self)
        self.booked.add_progress()
        self.opened = _Kpi("Offen", self, "Jetzt eintragen")
        self.opened.button.clicked.connect(self.open_clicked)
        self.opened.button.setAccessibleName("Offene Tätigkeiten jetzt eintragen")
        self.suggest = _Kpi("Vorschläge", self, "Ansehen")
        self.suggest.button.clicked.connect(self.suggestions_clicked)
        self.suggest.button.setAccessibleName("KI-Vorschläge ansehen")
        self.customers = _Kpi("Nach Kunde", self, customers=True)
        # Buchungsquote (Matrix42 ÷ Personalzeit): week_dialogs.update_rate_button füllt die
        # Kachel und blendet sie ohne Matrix42 aus; Klick öffnet den Wochenabschluss
        self.rate = RateKpi(self)
        self.rate.hide()
        # Zahlen-Kacheln so breit wie ihr Inhalt (keine leeren Flächen), „Nach Kunde“ füllt
        # den Rest. Im schmalen Fenster dürfen alle schrumpfen (Reflow, Mindestbreite klein).
        for w in (self.booked, self.rate, self.opened, self.suggest):
            w.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
            w.setMinimumWidth(60)
            layout.addWidget(w, 0)
        self.customers.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout.addWidget(self.customers, 1)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def show_numbers(self, data):
        booked, target = data["booked_s"], data["target_s"]
        self.booked.value.setText(hm(booked))
        self.booked.extra.setText(f"von {hm(target)}" if target else "")
        self.booked.bar.setValue(int(min(100, 100 * booked / target)) if target else 0)
        self.booked.setToolTip("Eingetragene Tätigkeiten des Tages"
                               + (" im Verhältnis zum Soll" if target else ""))
        n = data["open"]
        self.opened.value.setText(str(n))
        self.opened.extra.setText("Eintrag" if n == 1 else "Einträge")
        self.opened.button.setVisible(bool(n))
        s = data["suggestions"]
        self.suggest.value.setText(str(s))
        self.suggest.extra.setText("wartet" if s == 1 else "warten")
        self.suggest.button.setVisible(bool(s))
        self.suggest.setVisible(bool(s))  # „0 warten“ ist nur Rauschen
        parts = [f"{name} {hm(sec)}" for name, sec in data["customers"]]
        self.customers.value.set_parts(parts, "noch nichts eingetragen")


class ViewChips(QWidget):
    """Reihe „Einträge [Alle] [Offen / Doku] …“ über der Tagesliste."""

    view_chosen = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Fließend: im schmalen Fenster rücken die Chips in die nächste Zeile, statt dem
        # ganzen Fenster eine Mindestbreite aufzuzwingen (Reflow)
        layout = FlowLayout(self, spacing=6)
        layout.setContentsMargins(4, 6, 4, 6)
        title = QLabel("Einträge", self)
        title.setObjectName("section_title")
        title.setContentsMargins(0, 0, 6, 0)
        layout.addWidget(title)
        self.buttons = {}
        for key, text in CHIP_VIEWS:
            b = QToolButton(self)
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setText(text)
            b.setCursor(Qt.PointingHandCursor)
            b.setAccessibleName(f"Ansicht {text}")
            b.clicked.connect(lambda _c=False, k=key: self.view_chosen.emit(k))
            layout.addWidget(b)
            self.buttons[key] = (b, text)
            if key == GROUP_GAP_AFTER:  # sichtbare Lücke zwischen den beiden Gruppen
                gap = QWidget(self)
                gap.setFixedWidth(8)
                layout.addWidget(gap)

    def show_state(self, view, counts=None):
        counts = counts or {}
        for key, (button, text) in self.buttons.items():
            n = counts.get(key)
            button.setText(f"{text}  {n}" if n else text)
            button.setChecked(key == view)

    def set_tips(self, tips):
        """Erklärung je Ansicht beim Darüberfahren (view_help.help_text)."""
        for key, (button, _text) in self.buttons.items():
            if key in tips:
                button.setToolTip(tips[key])
