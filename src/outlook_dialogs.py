"""Dialog "Outlook und Teams" (Einstellungen → Datenquellen → Einrichten)."""

from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
                               QLineEdit, QPushButton, QSpinBox, QVBoxLayout)

from theme import prose
INTRO_OUTLOOK = ("Zeitzeuge liest aus dem klassischen Outlook deine Termine (auch Teams-Besprechungen) "
                 "und gesendete Mails. Gespeichert werden nur Betreff, Zeit, Ort und die Domains der "
                 "Teilnehmer, z. B. „kunde.de“, keine Adressen und keine Mailtexte. Das neue Outlook "
                 "bietet dafür keine Schnittstelle.")
INTRO_TEAMS = ("Teams-Anrufe erkennt Zeitzeuge daran, dass Teams das Mikrofon benutzt (das merkt "
               "sich Windows), ergänzt um die Teams-Logs. Sie stehen in der Zeile „Tel“ wie 3CX.")
INTRO = INTRO_OUTLOOK + "\n\n" + INTRO_TEAMS
TITLES = {"outlook": "Outlook", "teams": "Teams-Anrufe", None: "Outlook und Teams"}


class OutlookSettingsDialog(QDialog):
    """part: "outlook", "teams" oder None (beides). Jede Quelle hat ihr eigenes Fenster."""

    def __init__(self, config, status="", parent=None, part=None):
        super().__init__(parent)
        self.part = part
        self.setWindowTitle(TITLES.get(part, TITLES[None]))
        self.setMinimumWidth(540)
        layout = QVBoxLayout(self)
        intro = QLabel({"outlook": INTRO_OUTLOOK, "teams": INTRO_TEAMS}.get(part, INTRO))
        intro.setWordWrap(True)
        prose(intro)
        layout.addWidget(intro)

        form = QFormLayout()
        outlook_rows, teams_rows = [], []
        self.outlook = QCheckBox("&Outlook lesen (Termine, gesendete Mails)")
        self.outlook.setChecked(bool(config.get("outlook_enabled")))
        outlook_rows.append(("", self.outlook))
        self.calendar = QCheckBox("&Termine und Teams-Besprechungen aus dem Kalender")
        self.calendar.setChecked(config.get("outlook_calendar_enabled", True))
        outlook_rows.append(("", self.calendar))
        self.mails = QCheckBox("&Gesendete Mails")
        self.mails.setChecked(config.get("outlook_mails_enabled", True))
        outlook_rows.append(("", self.mails))
        self.external = QCheckBox("Nur Mails an &andere Firmen (Kundendomains)")
        self.external.setChecked(config.get("outlook_mails_external_only", True))
        outlook_rows.append(("", self.external))

        domains = config.get("outlook_own_domains") or []
        self.own = QLineEdit(", ".join(domains) if isinstance(domains, list) else str(domains))
        self.own.setPlaceholderText("leer: erkennt Zeitzeuge aus Outlook")
        self.own.setToolTip("Domains deiner Firma, durch Komma getrennt, z. B. itm-gruppe.de. "
                            "Sie zählen nicht als Kunde.")
        outlook_rows.append(("&Domains deiner Firma:", self.own))
        self.mail_minutes = QSpinBox()
        self.mail_minutes.setRange(1, 30)
        self.mail_minutes.setSuffix(" min")
        self.mail_minutes.setValue(int(config.get("outlook_mail_minutes", 3) or 3))
        self.mail_minutes.setToolTip("So breit steht eine gesendete Mail in der Timeline.")
        outlook_rows.append(("Dauer je &Mail:", self.mail_minutes))
        self.days = QSpinBox()
        self.days.setRange(1, 90)
        self.days.setSuffix(" Tage")
        self.days.setValue(int(config.get("outlook_days_back", 14) or 14))
        self.days.setToolTip("Ältere Tage liest Zeitzeuge nach, sobald du sie anzeigst.")
        outlook_rows.append(("&Zurück lesen:", self.days))
        self.interval = QSpinBox()
        self.interval.setRange(1, 120)
        self.interval.setPrefix("alle ")
        self.interval.setSuffix(" min")
        self.interval.setValue(int(config.get("outlook_interval_minutes", 10) or 10))
        outlook_rows.append(("&Lesen:", self.interval))
        self.calendar_folder = QLineEdit(config.get("outlook_calendar_folder", ""))
        self.calendar_folder.setPlaceholderText("leer: Standardkalender")
        self.calendar_folder.setToolTip("Anderer Kalender als Pfad, z. B. \\\\name@firma.de\\Kalender")
        outlook_rows.append(("&Kalender-Ordner:", self.calendar_folder))
        self.sent_folder = QLineEdit(config.get("outlook_sent_folder", ""))
        self.sent_folder.setPlaceholderText("leer: Gesendete Elemente")
        self.sent_folder.setToolTip("Anderer Ordner als Pfad, z. B. \\\\name@firma.de\\Gesendete Elemente")
        outlook_rows.append(("Ordner für gesendete Ma&ils:", self.sent_folder))
        self.start_outlook = QCheckBox("Outlook &starten, wenn es nicht läuft")
        self.start_outlook.setChecked(bool(config.get("outlook_start_if_closed", False)))
        self.start_outlook.setToolTip("Sonst liest Zeitzeuge nur, während Outlook geöffnet ist.")
        outlook_rows.append(("", self.start_outlook))

        self.teams = QCheckBox("Teams-Anr&ufe erkennen")
        self.teams.setChecked(bool(config.get("teams_calls_enabled")))
        teams_rows.append(("", self.teams))
        self.teams_min = QSpinBox()
        self.teams_min.setRange(0, 600)
        self.teams_min.setSuffix(" s")
        self.teams_min.setValue(int(config.get("teams_min_seconds", 30) or 0))
        self.teams_min.setToolTip("Kürzere Mikrofon-Nutzung (z. B. Gerätetest) zählt nicht als Anruf.")
        teams_rows.append(("Teams-Anrufe a&b:", self.teams_min))
        for label, widget in (outlook_rows if part != "teams" else []) + (teams_rows if part != "outlook" else []):
            form.addRow(label, widget)
        layout.addLayout(form)

        self.status = QLabel(status or "Aus")
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.read_button = QPushButton("&Jetzt lesen")
        self.read_button.setToolTip("Einstellungen übernehmen und Outlook gleich lesen")
        self.buttons.addButton(self.read_button, QDialogButtonBox.ActionRole)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        for box in (self.outlook, self.mails):
            box.toggled.connect(self._sync)
        self._sync()

    def _sync(self):
        on = self.outlook.isChecked()
        for w in (self.calendar, self.mails, self.own, self.days, self.interval,
                  self.calendar_folder, self.sent_folder, self.start_outlook):
            w.setEnabled(on)
        for w in (self.external, self.mail_minutes):
            w.setEnabled(on and self.mails.isChecked())

    def values(self):
        own = [d.strip().lstrip("@").lower() for d in self.own.text().replace(";", ",").split(",")]
        return {
            "outlook_enabled": self.outlook.isChecked(),
            "outlook_calendar_enabled": self.calendar.isChecked(),
            "outlook_mails_enabled": self.mails.isChecked(),
            "outlook_mails_external_only": self.external.isChecked(),
            "outlook_own_domains": [d for d in own if d],
            "outlook_mail_minutes": self.mail_minutes.value(),
            "outlook_days_back": self.days.value(),
            "outlook_interval_minutes": self.interval.value(),
            "outlook_calendar_folder": self.calendar_folder.text().strip(),
            "outlook_sent_folder": self.sent_folder.text().strip(),
            "outlook_start_if_closed": self.start_outlook.isChecked(),
            "teams_calls_enabled": self.teams.isChecked(),
            "teams_min_seconds": self.teams_min.value(),
        }
