"""Hilfe zu den Ansichten der Tagesliste: was „Zusammengefasst“, „Einzeln“ usw. zeigen.

VIEW_HELP liefert je Ansicht Symbol, Kurztext (Hinweis im Menü) und ein kleines Beispiel.
ViewHelpDialog zeigt alles auf einer Seite (Menü Ansicht → „Was zeigen die Ansichten?“).
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFrame, QGridLayout, QLabel,
                               QScrollArea, QVBoxLayout, QWidget)

from theme import prose
import icons

# Ansicht -> (Symbol, Kurz-Erklärung, Beispielzeilen). {merge} und {block} sind die Pausen
# aus der Config (merge_gap_minutes, block_gap_minutes).
VIEW_HELP = {
    "grouped": ("layers",
                "Gleiche Verbindungen mit weniger als {merge} Minuten Pause werden eine Zeile. "
                "Passwort-, Benutzer- und OTP-Anzeigen aus RDM stehen als Zähler dabei. "
                "Gut für den Überblick.",
                ["09:02–10:15  RDP  srv-dc01  · 3 Verbindungen · 2× OTP",
                 "10:20–10:48  TeamViewer  Müller GmbH"]),
    "single": ("list",
               "Jede Zeile genau so, wie sie in den Logs steht, ohne Zusammenfassen. "
               "Gut zum Nachprüfen, wenn etwas fehlt oder komisch aussieht.",
               ["09:02–09:31  RDP  srv-dc01", "09:33–09:58  RDP  srv-dc01",
                "09:41  Passwort angezeigt  srv-dc01", "10:01–10:15  RDP  srv-dc01"]),
    "blocks": ("blocks",
               "Alles mit weniger als {block} Minuten Pause dazwischen wird ein Arbeitsblock, "
               "egal welche Quelle. Praktisch, um einen Block als Ticket zu schreiben.",
               ["09:02–10:48  SSL VPN, srv-dc01, TeamViewer Müller GmbH",
                "11:30–12:05  Telefonat, OPNsense"]),
    "calls": ("phone",
              "Nur Telefonate: Anrufe aus 3CX (eingehend, ausgehend, verpasst) und Teams-Anrufe, "
              "jeder einzeln mit Dauer. Gut, um Telefonate nachzutragen.",
              ["08:05–08:09  Telefonat eingehend  Kanzlei Schmidt (0251 123456)",
               "11:30–11:45  Teams-Anruf  Müller GmbH"]),
    "doc": ("doc",
            "Deine eingetragenen Tätigkeiten und gestrichelt, was noch nicht dokumentiert ist.",
            ["✓ 09:00–10:45  Müller GmbH · Fernwartung: Drucker eingerichtet",
             "? 11:30–11:45  Telefonat eingehend"]),
    "rules": ("rules",
              "Tätigkeiten, die Zeitzeuge über feste Regeln erkannt hat, ohne KI "
              "(z. B. Outlook → E-Mail, TeamViewer → Fernwartung).",
              ["08:10–08:40  E-Mail / Kommunikation  (Outlook)"]),
    "ai": ("spark",
           "Vorschläge von Claude: Kunde, Kategorie und ein Satz fürs Ticket. Erst nach F6.",
           ["09:00–10:45  Müller GmbH · Fernwartung: Druckerproblem am Server gelöst"]),
    "m42": ("gauge",
            "Abgleich mit Matrix42: was gebucht ist, Personalzeit ohne Buchung und "
            "Verbindungen, die noch nicht gebucht sind.",
            ["09:00–10:45  gebucht  TCK0000049374", "13:10–13:55  nicht gebucht"]),
}


def help_text(key, config=None):
    """Kurz-Erklärung einer Ansicht mit den Pausen aus der Config."""
    config = config or {}
    _icon, text, _example = VIEW_HELP[key]
    return text.format(merge=config.get("merge_gap_minutes", 5),
                       block=config.get("block_gap_minutes", 10))


class ViewHelpDialog(QDialog):
    """Alle Ansichten der Tagesliste mit Erklärung und Beispiel."""

    def __init__(self, views, config, icon_color, current=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ansichten der Tagesliste")
        self.setMinimumSize(620, 560)
        layout = QVBoxLayout(self)
        intro = QLabel("Die Tagesliste unter der Timeline kann dieselben Daten unterschiedlich "
                       "zeigen. Umschalten im Menü <b>Ansicht</b>.")
        intro.setWordWrap(True)
        prose(intro)
        layout.addWidget(intro)

        body = QWidget()
        grid = QGridLayout(body)
        grid.setColumnStretch(1, 1)
        grid.setVerticalSpacing(14)
        for row, (key, name) in enumerate(views):
            if key not in VIEW_HELP:
                continue
            icon_name, _text, example = VIEW_HELP[key]
            pic = QLabel()
            pic.setPixmap(icons.icon(icon_name, icon_color).pixmap(24, 24))
            pic.setAlignment(Qt.AlignTop)
            grid.addWidget(pic, row, 0)
            box = QVBoxLayout()
            title = QLabel(f"<b>{name}</b>" + ("  · aktuell" if key == current else ""))
            text = QLabel(help_text(key, config))
            text.setWordWrap(True)
            prose(text)
            sample = QLabel("\n".join(example))
            sample.setObjectName("example")
            sample.setTextInteractionFlags(Qt.TextSelectableByMouse)
            sample.setFrameShape(QFrame.StyledPanel)
            box.addWidget(title)
            box.addWidget(text)
            box.addWidget(sample)
            grid.addLayout(box, row, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Close).setText("Schließen")
        layout.addWidget(buttons)
