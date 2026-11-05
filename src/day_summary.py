"""Kopf der Tagesansicht (Design „Companion“): Kennzahlen und Filter über der Tagesliste.

    Erfasst 5:10 h von 8:00 h   Offen 14 Einträge [Jetzt eintragen]   Vorschläge 3 [Ansehen]
    Nach Kunde  Müller GmbH 2:15 h · Kanzlei Schmidt 1:05 h

Darunter (über der Tagesliste) eine Reihe Chips für die häufigsten Ansichten:
    Einträge  [Alle]  [Offen / Doku 14]  [Vorschläge 3]  [Telefonate]  [Arbeitsblöcke]

Die Zahlen rechnet summary() ohne Qt aus (testbar), die Widgets zeigen sie nur an.
"""
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QProgressBar, QSizePolicy,
                               QToolButton, QVBoxLayout, QWidget)

TIME_FMT = "%Y-%m-%d %H:%M:%S"

# Ansichten, die als Chip über der Liste stehen (Schlüssel aus DayListMixin.VIEWS)
CHIP_VIEWS = [("grouped", "Alle"), ("doc", "Offen / Doku"), ("ai", "Vorschläge"),
              ("calls", "Telefonate"), ("blocks", "Arbeitsblöcke")]


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


def summary(doc_band, ai_entries, target_minutes, top=4):
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


class _Kpi(QFrame):
    """Kennzahl als Karte: Name, Wert, Zusatz und optional ein Knopf."""

    def __init__(self, label, parent=None, action=None):
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
        self.value = QLabel("–", self)
        self.value.setObjectName("kpi_value")
        row.addWidget(self.value)
        self.extra = QLabel("", self)
        self.extra.setObjectName("kpi_label")
        row.addWidget(self.extra, 1)
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
        self.customers = _Kpi("Nach Kunde", self)
        self.customers.value.setObjectName("card_title")
        self.customers.value.setTextFormat(Qt.PlainText)
        # Buchungsquote (Matrix42 ÷ Personalzeit): Knopf kommt aus dem Hauptfenster (attach_rate),
        # week_dialogs.update_rate_button füllt ihn und blendet die Kachel ein oder aus
        self.rate = _Kpi("Buchungsquote", self)
        self.rate.value.hide()
        self.rate.extra.hide()
        self.rate.hide()
        for w, stretch in ((self.booked, 2), (self.opened, 3), (self.suggest, 2), (self.rate, 3),
                           (self.customers, 3)):
            # alle gleich hoch; in schmalen Fenstern dürfen die Karten schrumpfen (Reflow)
            w.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            layout.addWidget(w, stretch)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def attach_rate(self, button):
        """Knopf „Quote heute 64 % · 7 Tage 87 % ✓“ in die Kachel Buchungsquote setzen."""
        button.setParent(self.rate)
        button.setCursor(Qt.PointingHandCursor)
        self.rate.layout().itemAt(1).layout().insertWidget(0, button)

    def show_rate(self, visible):
        self.rate.setVisible(visible)

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
        parts = [f"{name} {hm(sec)}" for name, sec in data["customers"]]
        self.customers.value.setText("  ·  ".join(parts) if parts else "noch nichts eingetragen")
        self.customers.value.setToolTip("\n".join(parts))


class ViewChips(QWidget):
    """Reihe „Einträge [Alle] [Offen / Doku] …“ über der Tagesliste."""

    view_chosen = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 6, 4, 6)
        layout.setSpacing(6)
        title = QLabel("Einträge", self)
        title.setObjectName("section_title")
        layout.addWidget(title)
        layout.addSpacing(6)
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
        layout.addStretch(1)

    def show_state(self, view, counts=None):
        counts = counts or {}
        for key, (button, text) in self.buttons.items():
            n = counts.get(key)
            button.setText(f"{text}  {n}" if n else text)
            button.setChecked(key == view or (key == "grouped" and view == "single"))
