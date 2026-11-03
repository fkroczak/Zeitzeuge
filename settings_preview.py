"""Vorschau im Einstellungsfenster (Seite „Ansicht“): ein erfundener Beispieltag.

Zeigt Timeline und Tagesliste so, wie Zeitzeuge sie mit den aktuellen Einstellungen
zeichnen würde, auch an Tagen ohne eigene Daten. Fährt die Maus über eine Einstellung,
zeigt die Vorschau schon den Zustand nach dem Umschalten (Variante), ohne etwas zu speichern.

Keine echten Daten, keine Logs, kein Netz: alles kommt aus DEMO_* unten.
"""
from datetime import datetime, timedelta

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel,
                               QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout)

import rules as rule_engine
from activity_tracker import app_label
from grouping import group_entries, work_blocks
from journal import open_entry
from timeline_only import TimelineView, type_label

DEMO_DAY = datetime(2026, 10, 21)  # Mittwoch
DEMO_DATE = QDate(2026, 10, 21)
FMT = "%Y-%m-%d %H:%M:%S"


def _t(hm, sec=0):
    h, m = map(int, hm.split(":"))
    return DEMO_DAY + timedelta(hours=h, minutes=m, seconds=sec)


def _e(a, b, kind, who, details="", **extra):
    return {"start": f"{_t(a):{FMT}}", "end": f"{_t(b):{FMT}}", "type": kind,
            "customer_name": who, "details": details, "is_suggestion": True, **extra}


def demo_activities(config):
    """Verbindungen, Telefonate, VPN, Zugangsdaten und eine gesendete Mail des Beispieltags."""
    mail_end = (_t("11:40") + timedelta(minutes=config.get("outlook_mail_minutes", 5))).strftime("%H:%M")
    return [
        _e("08:05", "08:09", "Telefonat", "Kanzlei Schmidt (0251 123456)", "Eingehend, Dauer 4:00",
           direction="Eingehend"),
        # zweimal TeamViewer mit 4 min Pause: „Zusammenfassen bis Pause“ macht daraus eine Zeile
        _e("08:12", "08:40", "TeamViewer", "Müller GmbH", "TeamViewer-ID 1 076 789 144", tv_id="1076789144"),
        _e("08:44", "08:58", "TeamViewer", "Müller GmbH", "TeamViewer-ID 1 076 789 144", tv_id="1076789144"),
        _e("09:00", "10:05", "VPN-Verbindung", "Kanzlei Schmidt - SSL VPN"),
        _e("09:02", "09:58", "RDP-Verbindung", "Kanzlei Schmidt - DC01"),
        _e("09:03", "09:04", "Passwort angezeigt", "Kanzlei Schmidt - DC01"),
        _e("10:20", "11:05", "SSH-Verbindung", "Praxis Weber - Firewall"),
        _e("11:40", mail_end, "Mail gesendet", "Praxis Weber", "AW: Firewall-Update"),
        _e("12:40", "12:47", "Telefonat", "Praxis Dr. Weber (0521 987654)", "Ausgehend, Dauer 7:00",
           direction="Ausgehend"),
        _e("14:10", "15:20", "RDP-Verbindung", "Müller GmbH - TS01"),
    ]


def demo_segments():
    """Aktive Fenster: Haupttätigkeiten mit kurzen Sprüngen (wie an einem echten Tag)."""
    mains = [("08:00", "08:40", "outlook.exe", "Posteingang - Outlook"),
             ("08:40", "10:05", "mstsc.exe", "DC01 - Remotedesktopverbindung"),
             ("10:05", "11:10", "putty.exe", "root@fw-weber: ~"),
             ("11:10", "12:00", "outlook.exe", "Posteingang - Outlook"),
             ("13:00", "14:05", "teams.exe", "Chat | Microsoft Teams"),
             ("14:05", "15:25", "mstsc.exe", "TS01 - Remotedesktopverbindung"),
             ("15:25", "16:30", "excel.exe", "Stundenzettel.xlsx - Excel")]
    jumps = [("teams.exe", "Chat | Microsoft Teams"), ("chrome.exe", "Google - Chrome"),
             ("outlook.exe", "Posteingang - Outlook")]
    segments, n = [], 0
    for a, b, app, title in mains:
        cur, end = _t(a), _t(b)
        while cur < end:
            n += 1
            run = min(cur + timedelta(seconds=90 + (n * 137) % 330), end)
            segments.append({"start": f"{cur:{FMT}}", "end": f"{run:{FMT}}", "app": app, "title": title})
            cur = run
            if cur < end and n % 3:
                ja, jt = [j for j in jumps if j[0] != app][n % 2]
                jump = min(cur + timedelta(seconds=10 + (n * 29) % 70), end)
                segments.append({"start": f"{cur:{FMT}}", "end": f"{jump:{FMT}}", "app": ja, "title": jt})
                cur = jump
    return segments


def demo_docs(activities):
    """Zeile Dokumentation: eine erledigte Tätigkeit und offene Einträge."""
    done = {"start": f"{_t('08:12'):{FMT}}", "end": f"{_t('08:58'):{FMT}}", "type": "Dokumentiert",
            "doc": True, "customer_name": "Müller GmbH", "category": "Fernwartung",
            "description": "Updates eingespielt", "doc_item": {}}
    opened = [open_entry(a) for a in activities
              if a["type"] in ("RDP-Verbindung", "SSH-Verbindung", "Telefonat") and a["start"] > done["end"]]
    return sorted([done] + opened, key=lambda e: e["start"])


class _DemoTracker:
    def __init__(self, segments):
        self._segments = segments

    def segments_for(self, _date_str):
        return [dict(s) for s in self._segments]


class PreviewTimeline(TimelineView):
    """Timeline mit Beispieltag: zeichnet wie das Original, liest aber keine Logs."""

    def __init__(self, config, parent=None):
        super().__init__([], config, parent)
        self.setMinimumHeight(0)
        # Die Vorschau ist niedriger als die Timeline: untere Zeilen über die Scrollleiste erreichbar
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setAccessibleName("Vorschau der Timeline mit Beispieldaten")
        self.current_date = DEMO_DATE
        self.tracker = _DemoTracker(demo_segments())
        self.doc_entries = lambda _d: demo_docs(self.activities_for(DEMO_DATE))
        self.rule_entries = lambda _d: rule_engine.classify(
            self.activities_for(DEMO_DATE), self.pc_entries_for(DEMO_DATE),
            self.config.get("rules") or [])

    def activities_for(self, date):
        return [dict(a) for a in demo_activities(self.config)]

    def load_remote_connections(self, date):
        self.remote_suggestions = []

    def refresh(self):  # keine Logs
        pass

    # Nur ansehen: Klicks und Menüs tun in der Vorschau nichts, der Hinweis beim Darüberfahren bleibt
    def mousePressEvent(self, event):
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()

    def mouseDoubleClickEvent(self, event):
        event.accept()

    def contextMenuEvent(self, event):
        event.accept()


def list_entries(timeline, config):
    """Zeilen der Tagesliste für die Vorschau (Ansichten aus den Logs; andere wie „Zusammengefasst“)."""
    view = config.get("list_view", "grouped")
    entries = timeline.activities_for(DEMO_DATE)
    if view == "single":
        pass
    elif view == "blocks":
        entries = work_blocks(entries, config.get("block_gap_minutes", 10))
    else:
        entries = group_entries(entries, config.get("merge_gap_minutes", 5))
    if config.get("show_pc_in_list", False) and view in ("grouped", "single"):
        entries += (timeline.pc_blocks_for(DEMO_DATE) if config.get("pc_blocks", True)
                    else timeline.pc_entries_for(DEMO_DATE))
    return sorted(entries, key=lambda e: e["start"])


class PreviewPane(QFrame):
    """Kasten „Vorschau“: Satz, was gezeigt wird, darunter Timeline und Tagesliste."""

    LIST_ROWS = 3
    TIMELINE_HEIGHT = 170

    def __init__(self, main, parent=None):
        super().__init__(parent)
        self.setObjectName("tile")
        self.main = main
        self.variant = None  # ({Schlüssel: Wert}, Satz) beim Darüberfahren
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(6)
        head = QHBoxLayout()
        title = QLabel("Vorschau")
        title.setObjectName("row_title")
        head.addWidget(title)
        self.caption = QLabel()
        self.caption.setObjectName("hint")
        self.caption.setWordWrap(True)
        head.addWidget(self.caption, 1)
        # Ein- und ausklappen, damit die Einstellungen darunter Platz haben (wird gemerkt)
        self.toggle = QToolButton()
        self.toggle.setAutoRaise(True)
        self.toggle.clicked.connect(lambda: self.set_open(not self.timeline.isVisible()))
        head.addWidget(self.toggle, 0, Qt.AlignTop)
        layout.addLayout(head)
        self.timeline = PreviewTimeline(dict(main.config), self)
        self.timeline.setFixedHeight(self.TIMELINE_HEIGHT)
        layout.addWidget(self.timeline)
        self.table = QTableWidget(0, 5, self)
        self.table.setAccessibleName("Vorschau der Tagesliste mit Beispieldaten")
        self.table.setHorizontalHeaderLabels(["Von", "Bis", "Typ", "Kunde / Verbindung", "Details"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setFixedHeight(26 + self.LIST_ROWS * 24 + 4)
        layout.addWidget(self.table)
        open_ = bool(main.config.get("settings_preview_open", True))
        self.set_open(open_)
        self.refresh()

    def set_open(self, on):
        """Vorschau zeigen oder auf die Kopfzeile einklappen."""
        self.timeline.setVisible(on)
        self.table.setVisible(on)
        self.toggle.setText("Ausblenden" if on else "Einblenden")
        self.toggle.setToolTip("Vorschau ausblenden, um mehr Einstellungen zu sehen" if on
                               else "Vorschau mit Beispieltag zeigen")
        if bool(self.main.config.get("settings_preview_open", True)) != on:
            import main_timeline as mt
            self.main.config["settings_preview_open"] = on
            mt.save_config(self.main.config)

    def config(self):
        """Aktuelle Einstellungen, bei einer Variante mit den geänderten Werten."""
        cfg = dict(self.main.config)
        if self.variant:
            cfg.update(self.variant[0])
        return cfg

    def show_variant(self, changes=None, text=""):
        """changes = {Schlüssel: Wert}: so zeigen, als wäre es umgestellt; None = aktueller Stand."""
        self.variant = (changes, text) if changes else None
        self.refresh()

    def refresh(self):
        cfg = self.config()
        tl = self.timeline
        tl.config = cfg
        tl._block_cache = None
        if tl.dark_mode != bool(cfg.get("dark_mode")):
            tl.dark_mode = bool(cfg.get("dark_mode"))
            tl.init_timeline_colors()
        if cfg.get("timeline_range", "work") == "work":
            tl.show_work_time()
        else:
            tl.show_whole_day()
        self.caption.setText(self.variant[1] if self.variant
                             else "Beispieltag. Fahr über eine Einstellung, um die Änderung vorab zu sehen.")
        self._fill_list(cfg)

    def _fill_list(self, cfg):
        from app_daylist import new_details  # erst hier: app_daylist lädt das Hauptfenster
        entries = list_entries(self.timeline, cfg)
        self.table.setRowCount(len(entries))
        for row, a in enumerate(entries):
            start, end = datetime.strptime(a["start"], FMT), datetime.strptime(a["end"], FMT)
            kind = type_label(a) if "app" not in a or a.get("pc_block") else f"PC: {app_label(a['app'])}"
            who = a.get("label") or a.get("customer_name", "")
            values = [f"{start:%H:%M}", f"{end:%H:%M}", kind, who,
                      new_details(a.get("details", ""), kind, who)]
            for col, text in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(text))
