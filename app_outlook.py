"""Hauptfenster: Outlook (Termine, gesendete Mails) und Teams-Anrufe.

Teil von TimelineApp (main_timeline.py), nur über main_timeline laden.
Standardmäßig aus; eingeschaltet über Einstellungen → Datenquellen.
"""
from PySide6.QtWidgets import QDialog

import safe_io
import main_timeline as mt  # Pfade und save_config zur Laufzeit von dort (Tests ersetzen sie dort)
from outlook_dialogs import OutlookSettingsDialog

SOURCE_KEYS = ("outlook_enabled", "teams_calls_enabled")


class OutlookMixin:
    def _init_outlook(self):
        self.outlook_reader = None
        self._outlook_cache = {}
        self._outlook_shown = ""  # zuletzt in der Statuszeile gemeldeter Fehler
        self.timeline.outlook_entries = self.outlook_day_entries
        self.apply_outlook_reader()

    def outlook_wanted(self):
        return any(self.config.get(k) for k in SOURCE_KEYS)

    def apply_outlook_reader(self):
        """Leser starten oder anhalten, wie es die Einstellungen sagen (PAW: nie)."""
        self._outlook_cache.clear()
        if self.outlook_wanted() and not self.is_paw():
            self.start_outlook_reader()
        else:
            self.stop_outlook_reader()

    def start_outlook_reader(self):
        if self.outlook_reader:
            self.outlook_reader.read_now()
            return
        from outlook_reader import OutlookReader
        self.outlook_reader = OutlookReader(self.config, mt.OUTLOOK_FILE, mt.TEAMS_CALLS_FILE, self)
        self.outlook_reader.day_read.connect(self.on_outlook_day)
        self.outlook_reader.status_changed.connect(self.on_outlook_status)
        self._watch_reader(self.outlook_reader)
        self.outlook_reader.start()

    def stop_outlook_reader(self):
        if self.outlook_reader:
            self.outlook_reader.stop()
            self.outlook_reader.deleteLater()
            self.outlook_reader = None

    def on_outlook_day(self, date_str):
        self._outlook_cache.pop(date_str, None)
        if date_str == self.current_date.toString("yyyy-MM-dd"):
            self.timeline.draw_timeline(self.current_date)

    def on_outlook_status(self, text):
        """Probleme (Outlook zu, nicht gefunden …) einmal in der Statuszeile zeigen."""
        if " gelesen " in f"{text} ":
            self._outlook_shown = ""
        elif text != self._outlook_shown:
            self._outlook_shown = text
            self.statusBar().showMessage(text, 15000)

    def outlook_day_entries(self, date_str):
        """Termine, Mails und Teams-Anrufe eines Tages (für die Timeline, zwischengespeichert)."""
        if not self.outlook_wanted():
            return []
        if date_str not in self._outlook_cache:
            from outlook_reader import day_entries
            try:
                self._outlook_cache[date_str] = day_entries(
                    self.config, mt.OUTLOOK_FILE, mt.TEAMS_CALLS_FILE, date_str)
            except Exception as e:  # Anzeige darf nie an Outlook scheitern
                safe_io.log(f"Outlook: Tag {date_str} nicht lesbar: {e!r}")
                return []
            if len(self._outlook_cache) > 60:
                self._outlook_cache.pop(next(iter(self._outlook_cache)))
        # Kopien: Timeline und Gruppierung ergänzen Felder
        return [dict(e) for e in self._outlook_cache[date_str]]

    def build_outlook_dialog(self):
        status = self.outlook_reader.status if self.outlook_reader else (
            "Auf der PAW aus." if self.is_paw() else "Aus")
        dialog = OutlookSettingsDialog(self.config, status, self)
        connected = [None]

        def apply():
            self.config.update(dialog.values())
            mt.save_config(self.config)
            self.apply_outlook_reader()
            self.sync_source_actions()
            self.timeline.refresh()
            reader = self.outlook_reader
            if reader:
                dialog.status.setText(reader.status)
                if connected[0] is not reader:  # je Leser nur einmal verbinden
                    reader.status_changed.connect(dialog.status.setText)
                    connected[0] = reader

        def read_now():
            if not dialog.outlook.isChecked() and not dialog.teams.isChecked():
                dialog.outlook.setChecked(True)
            apply()

        dialog.read_button.clicked.connect(read_now)
        dialog.accepted.connect(apply)
        return dialog

    def open_outlook_settings(self):
        dialog = self.build_outlook_dialog()
        dialog.exec()
        if dialog.result() != QDialog.Accepted:
            self.sync_source_actions()
        dialog.deleteLater()  # sonst sammeln sich Dialoge samt Verbindungen an
