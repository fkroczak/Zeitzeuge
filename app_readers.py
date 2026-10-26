"""Hauptfenster: Hintergrund-Leser für 3CX und ITM, Wächter und Fehleranzeige.

Teil von TimelineApp (main_timeline.py), nur über main_timeline laden.
"""
import os
import threading
import time

from datetime import datetime

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QInputDialog, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QSpinBox, QSystemTrayIcon,
                               QVBoxLayout)

import safe_io
import main_timeline as mt  # Pfade und save_config zur Laufzeit von dort (Tests ersetzen sie dort)


class ReadersMixin:
    def is_paw(self):
        """PAW-Modus: nur RDM sammeln. Dort startet Zeitzeuge nie Edge, sucht keine Prozesse
        und beendet keine (verträgt sich so mit EDR wie Cortex XDR)."""
        return self.config.get("pc_role") == "paw"

    def _paw_blocks(self, name):
        if not self.is_paw():
            return False
        self.statusBar().showMessage(
            f"{name}: auf der PAW aus (kein Edge im Hintergrund). Daten kommen über „Daten übernehmen“.", 8000)
        return True

    def personal_day_for(self, date_str):
        """Personalzeit eines Tages: aus ITM, sonst von einem anderen PC übernommen."""
        day = self.itm_reader.day(date_str) if getattr(self, "itm_reader", None) else None
        if day is None and getattr(self, "imported", None):
            day = self.imported.personal(date_str)
        return day

    def all_readers(self):
        """Laufende Hintergrund-Leser (3CX, ITM, Matrix42)."""
        return [r for r in (getattr(self, "pbx_reader", None), getattr(self, "itm_reader", None),
                            getattr(self, "m42_reader", None)) if r]

    # ---------------------- 3CX direkt auslesen -------------------------------

    def start_pbx_reader(self):
        if self.pbx_reader or self._paw_blocks("3CX"):
            return
        from pbx_reader import PbxReader  # Edge-Steuerung nur laden, wenn sie gebraucht wird
        self.pbx_reader = PbxReader(
            self.config.get("calls_3cx_url", ""), mt.CALLS_FILE, mt.PBX_PROFILE_DIR,
            open(mt.resource_path("zeitzeuge_anrufe.user.js"), encoding="utf-8").read(), self,
            days_back=self.config.get("calls_days_back", 14),
        )
        self.pbx_reader.status_changed.connect(self.calls_label.setText)
        self.pbx_reader.status_changed.connect(lambda _t: self.update_source_indicators())
        self.pbx_reader.busy_changed.connect(self.update_busy_bar)
        self.pbx_reader.calls_added.connect(
            lambda _n: self.timeline.draw_timeline(self.current_date)
        )
        self.pbx_reader.login_required.connect(self.on_pbx_login_required)
        self.pbx_reader.recording_done.connect(self.on_recording_done)
        self.pbx_reader.check_done.connect(self.on_pbx_check_done)
        self._watch_reader(self.pbx_reader)
        self.pbx_reader.start()
        self.calls_label.setText("3CX: wird geladen …")
        self.update_source_indicators()

    def stop_pbx_reader(self):
        if self.pbx_reader:
            self.pbx_reader.stop()
            self.pbx_reader.deleteLater()
            self.pbx_reader = None
            self.update_source_indicators()

    def on_pbx_login_required(self):
        if self.tray:
            self.tray.showMessage(
                "3CX-Anmeldung nötig",
                "Zeitzeuge kann die Anrufliste nicht lesen. Klick hier, um dich anzumelden.",
                QSystemTrayIcon.Warning, 8000,
            )

    def show_pbx_login(self):
        if not self.pbx_reader:
            self.start_pbx_reader()
        if self.pbx_reader:
            self.pbx_reader.show_login(self)

    # Texte und Schlüssel der beiden Hintergrund-Leser (für den gemeinsamen Dialog)
    READER_DIALOGS = {
        "pbx": dict(
            title="3CX direkt auslesen",
            text="Zeitzeuge öffnet den 3CX-Webclient unsichtbar mit Microsoft Edge (eigenes Profil) "
                 "und liest jede Minute die Anrufliste. Es hält die eingestellten Tage vollständig, "
                 "ältere Tage beim Blättern. Tampermonkey wird dafür nicht gebraucht.\n\n"
                 "Zum Anmelden öffnet sich ein Edge-Fenster: anmelden und das Fenster schließen. "
                 "Die Anmeldung bleibt gespeichert. Ton, Mikrofon und Benachrichtigungen sind gesperrt.",
            url_label="3CX-Adresse:", url_key="calls_3cx_url", enabled_key="pbx_reader_enabled",
            enabled_text="Anrufliste automatisch im Hintergrund lesen",
            login_text="Bei 3CX anmelden …", attr="pbx_reader",
            record_text="Ein Edge-Fenster mit dem 3CX-Webclient öffnet sich.\n\n"
                        "1. Falls nötig anmelden.\n"
                        "2. Die Anrufliste öffnen und ein Stück nach unten scrollen, "
                        "damit ältere Anrufe nachladen.\n"
                        "3. Das Fenster schließen.\n\n"
                        "Zeitzeuge speichert dann die Mitschnitt-Datei im Datenordner.",
        ),
        "m42": dict(
            title="Matrix42-Buchungen",
            text="Zeitzeuge liest deine gebuchten Zeiten aus dem Matrix42-Kalender (Service Desk → "
                 "Kalender) und vergleicht sie mit Personalzeit, Verbindungen und Telefonaten. "
                 "In der Timeline steht dann eine Zeile „Matrix42“: graue Blöcke sind gebucht, "
                 "rot gestrichelte Lücken sind Personalzeit ohne Buchung.\n\n"
                 "Matrix42 ist nur im Firmennetz (oder VPN) erreichbar. Außerhalb wartet Zeitzeuge "
                 "einfach und liest weiter, sobald du wieder im Netz bist.\n\n"
                 "Adresse: Öffne in Matrix42 den Kalender und kopiere die Adresse aus der Adresszeile. "
                 "Die Windows-Anmeldung klappt meist von selbst; sonst einmal „Bei Matrix42 anmelden“.",
            url_label="Kalenderseite:", url_key="m42_url", enabled_key="m42_reader_enabled",
            enabled_text="Gebuchte Zeiten automatisch im Hintergrund lesen",
            login_text="Bei Matrix42 anmelden …", attr="m42_reader",
            record_text="Ein Edge-Fenster mit dem Matrix42-Kalender öffnet sich.\n\n"
                        "1. Falls nötig anmelden.\n"
                        "2. Im Kalender zwei oder drei Wochen vor- und zurückblättern.\n"
                        "3. Das Fenster schließen.\n\n"
                        "Zeitzeuge speichert dann die Mitschnitt-Datei im Datenordner.",
        ),
        "itm": dict(
            title="ITM-Personalzeiten",
            text="Zeitzeuge liest deine Personalzeiten aus der ITM-Zeiterfassung: heute alle 5 Minuten, "
                 "andere Tage beim Blättern. Die Timeline hebt dann deine gestempelte Arbeitszeit hervor, "
                 "Pausen sind abgedunkelt. Offene oder fehlerhafte Buchungen meldet Zeitzeuge.\n\n"
                 "Anmelden: Mit Benutzername und Mandant fragt Zeitzeuge einmal nach dem Passwort und "
                 "braucht kein Edge. Ohne Benutzername öffnet sich ein Edge-Fenster zum Anmelden. "
                 "Die Anmeldung erneuert Zeitzeuge selbst; sie hält, solange es mindestens einmal "
                 "pro Woche läuft. Das Passwort wird nie gespeichert.",
            url_label="ITM-Adresse:", url_key="itm_url", enabled_key="itm_reader_enabled",
            enabled_text="Personalzeiten automatisch im Hintergrund lesen",
            login_text="Bei ITM anmelden …", attr="itm_reader",
            record_text="Ein Edge-Fenster mit der ITM-Zeiterfassung öffnet sich.\n\n"
                        "1. Falls nötig anmelden.\n"
                        "2. Zwei oder drei andere Tage in der Tagesübersicht aufrufen.\n"
                        "3. Das Fenster schließen.\n\n"
                        "Zeitzeuge speichert dann die Mitschnitt-Datei im Datenordner.",
        ),
    }

    def open_pbx_settings(self):
        self._open_reader_settings("pbx")

    def open_m42_settings(self):
        self._open_reader_settings("m42")

    def open_itm_settings(self):
        self._open_reader_settings("itm")

    def build_pbx_dialog(self):
        return self.build_reader_dialog("pbx")

    def build_itm_dialog(self):
        return self.build_reader_dialog("itm")

    def _open_reader_settings(self, kind):
        from pbx_reader import find_browser
        if kind in ("pbx", "m42") and not find_browser():  # ITM geht auch mit Passwort ohne Edge
            QMessageBox.warning(self, self.READER_DIALOGS[kind]["title"],
                                "Microsoft Edge oder Google Chrome wurde nicht gefunden.")
            return
        self.build_reader_dialog(kind).exec()

    def build_reader_dialog(self, kind):
        """Einstellungen für einen Hintergrund-Leser (3CX oder ITM)."""
        spec = self.READER_DIALOGS[kind]
        attr, url_key, enabled_key = spec["attr"], spec["url_key"], spec["enabled_key"]
        start = {"pbx": self.start_pbx_reader, "itm": self.start_itm_reader,
                 "m42": self.start_m42_reader}[kind]
        stop = {"pbx": self.stop_pbx_reader, "itm": self.stop_itm_reader,
                "m42": self.stop_m42_reader}[kind]

        dialog = QDialog(self)
        dialog.setWindowTitle(spec["title"])
        dialog.setMinimumWidth(520)
        layout = QVBoxLayout(dialog)
        info = QLabel(spec["text"])
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        url_edit = QLineEdit(self.config.get(url_key, ""))
        form.addRow(spec["url_label"], url_edit)
        enabled = QCheckBox(spec["enabled_text"])
        enabled.setChecked(self.config.get(enabled_key, False))
        form.addRow("", enabled)
        days = None
        if kind == "pbx":
            days = QSpinBox()
            days.setRange(1, 365)
            days.setSuffix(" Tage")
            days.setValue(self.config.get("calls_days_back", 14))
            days.setToolTip("Ältere Tage liest Zeitzeuge nach, sobald du sie anzeigst.")
            form.addRow("Anrufe zurück lesen:", days)
        if kind == "m42":
            url_edit.setPlaceholderText("https://…/wm/… (Kalenderseite aus der Adresszeile kopieren)")
            days = QSpinBox()
            days.setRange(0, 52)
            days.setSuffix(" Wochen")
            days.setValue(self.config.get("m42_weeks_back", 4))
            days.setToolTip("So viele Wochen zurück liest Zeitzeuge einmal pro Sitzung. "
                            "Ältere Wochen liest es, sobald du sie anzeigst.")
            form.addRow("Wochen zurück lesen:", days)
        user_edit = mandant = None
        if kind == "itm":
            user_edit = QLineEdit(self.config.get("itm_user", ""))
            user_edit.setPlaceholderText("leer: Anmeldung im Edge-Fenster")
            form.addRow("Benutzername:", user_edit)
            mandant = QSpinBox()
            mandant.setRange(0, 999999)
            mandant.setValue(int(self.config.get("itm_mandant") or 0))
            form.addRow("Mandant:", mandant)
        layout.addLayout(form)

        status = QLabel("Aus")
        status.setObjectName("hint")
        layout.addWidget(status)

        def apply():
            url = url_edit.text().strip()
            if kind != "m42":  # bei Matrix42 gehört die ganze Adresse (mit # …) zur Seite
                url = url.rstrip("/")
            changed = url != self.config.get(url_key)
            days_key, days_default = ("m42_weeks_back", 4) if kind == "m42" else ("calls_days_back", 14)
            if days and days.value() != self.config.get(days_key, days_default):
                self.config[days_key] = days.value()
                changed = True  # Leser mit der neuen Zahl neu starten
            if user_edit is not None:
                user = user_edit.text().strip()
                changed = changed or (user, mandant.value()) != (
                    self.config.get("itm_user", ""), self.config.get("itm_mandant", 0))
                self.config["itm_user"], self.config["itm_mandant"] = user, mandant.value()
            self.config[url_key] = url
            self.config[enabled_key] = enabled.isChecked()
            mt.save_config(self.config)
            if changed or not enabled.isChecked():
                stop()
            if enabled.isChecked():
                start()
            self.sync_source_actions()
            return getattr(self, attr)

        def follow_status():
            # Status im Dialog live mitlaufen lassen
            reader = getattr(self, attr)
            if reader:
                status.setText(reader.status)
                reader.status_changed.connect(status.setText)

        def login():
            if user_edit is not None and user_edit.text().strip() and not mandant.value():
                QMessageBox.warning(dialog, spec["title"], "Bitte auch den Mandanten eintragen.")
                return
            enabled.setChecked(True)
            reader = apply()
            if reader:
                follow_status()
                reader.show_login(dialog)

        def record():
            enabled.setChecked(True)
            reader = apply()
            if not reader:
                return
            follow_status()
            path = os.path.join(mt.DATA_DIR, f"mitschnitt_{kind}_{datetime.now():%Y-%m-%d_%H%M}.json")
            if reader.record(path):
                QMessageBox.information(dialog, "Abfragen mitschneiden", spec["record_text"])

        follow_status()

        login_btn = QPushButton(spec["login_text"])
        login_btn.clicked.connect(login)
        record_btn = QPushButton("Abfragen &mitschneiden …")
        record_btn.setToolTip("Aufzeichnen, welche Abfragen die Seite an ihren Server schickt "
                              "(Passwörter und Token werden geschwärzt).")
        record_btn.clicked.connect(record)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.addButton(login_btn, QDialogButtonBox.ActionRole)
        buttons.addButton(record_btn, QDialogButtonBox.ActionRole)
        if kind == "pbx":
            def check():
                enabled.setChecked(True)
                reader = apply()
                if reader:
                    follow_status()
                    path = os.path.join(mt.DATA_DIR, f"3cx_pruefung_{datetime.now():%Y-%m-%d_%H%M}.json")
                    reader.check_direct(path)
            check_btn = QPushButton("Direkt-Abfrage &prüfen")
            check_btn.setToolTip("Anrufe ohne Webseite direkt vom 3CX-Server holen und mit "
                                 "der gespeicherten Anrufliste vergleichen")
            check_btn.clicked.connect(check)
            buttons.addButton(check_btn, QDialogButtonBox.ActionRole)
        if kind == "itm":
            def forget():
                reader = getattr(self, attr)
                if reader:
                    reader.auth.forget()
                else:
                    from itm_auth import ItmAuth
                    ItmAuth("", mt.ITM_AUTH_FILE).forget()
                status.setText("ITM: gespeicherte Anmeldung gelöscht")
            forget_btn = QPushButton("Anmeldung &löschen")
            forget_btn.setToolTip("Gespeicherte Anmeldung (refreshToken) auf diesem PC löschen")
            forget_btn.clicked.connect(forget)
            buttons.addButton(forget_btn, QDialogButtonBox.ActionRole)
        buttons.accepted.connect(lambda: (apply(), dialog.accept()))
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        return dialog

    def on_pbx_check_done(self, path, text):
        if not path:
            QMessageBox.warning(self, "3CX-Direkt-Abfrage", text)
            return
        box = QMessageBox(QMessageBox.Information, "3CX-Direkt-Abfrage",
                          f"{text}\n\nBericht: {path}\n\nNamen und Nummern sind maskiert.",
                          parent=self)
        open_btn = box.addButton("Ordner öffnen", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        box.exec()
        if box.clickedButton() is open_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))

    def on_recording_done(self, path):
        if not path:
            QMessageBox.warning(self, "Abfragen mitschneiden",
                                "Der Mitschnitt hat nicht geklappt. Details stehen in der Statuszeile.")
            return
        box = QMessageBox(QMessageBox.Information, "Mitschnitt gespeichert",
                          f"Gespeichert unter:\n{path}\n\n"
                          "Passwörter, Token und Cookie-Werte sind geschwärzt, Antworten gekürzt. "
                          "Die Datei kann trotzdem Namen und Nummern aus der Anrufliste enthalten. "
                          "Schau sie vor dem Weitergeben kurz durch.", parent=self)
        open_btn = box.addButton("Ordner öffnen", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        box.exec()
        if box.clickedButton() is open_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))

    # ---------------------- ITM-Personalzeiten --------------------------------

    def start_itm_reader(self):
        if self.itm_reader or self._paw_blocks("ITM"):
            return
        from itm_reader import ItmReader
        self.itm_reader = ItmReader(self.config.get("itm_url", ""), mt.ITM_FILE, mt.ITM_PROFILE_DIR, self,
                                    auth_file=mt.ITM_AUTH_FILE, auth_url=self.config.get("itm_auth_url", ""))
        self.itm_reader.username = (self.config.get("itm_user") or "").strip()
        self.itm_reader.mandant = self.config.get("itm_mandant") or 0
        self.itm_reader.password_prompt = self.ask_itm_password
        self.itm_reader.issues_found.connect(self.on_itm_issues)
        self.itm_reader.login_finished.connect(
            lambda error: error and QMessageBox.warning(self, "ITM-Anmeldung",
                                                        f"Anmeldung fehlgeschlagen:\n{error}"))
        self.itm_reader.status_changed.connect(lambda _t: self.update_source_indicators())
        self.itm_reader.busy_changed.connect(self.update_busy_bar)
        self.itm_reader.day_read.connect(
            lambda d: self.timeline.draw_timeline(self.current_date)
            if d == self.current_date.toString("yyyy-MM-dd") else None
        )
        self.itm_reader.login_required.connect(
            lambda: self.tray and self.tray.showMessage(
                "ITM-Anmeldung nötig",
                "Zeitzeuge kann die Personalzeiten nicht lesen. Klick hier, um dich anzumelden.",
                QSystemTrayIcon.Warning, 8000,
            )
        )
        self.itm_reader.recording_done.connect(self.on_recording_done)
        self._watch_reader(self.itm_reader)
        self.itm_reader.start()
        self.itm_reader.want(self.current_date.toString("yyyy-MM-dd"))

    def ask_itm_password(self, parent=None):
        """Passwort für die ITM-Anmeldung abfragen (wird nicht gespeichert)."""
        reader = self.itm_reader
        if not reader or not reader.username:
            return
        password, ok = QInputDialog.getText(
            parent or self, "ITM-Anmeldung",
            f"Passwort für {reader.username} (Mandant {reader.mandant}):\n"
            "Zeitzeuge speichert das Passwort nicht, nur die Anmeldung für 7 Tage.",
            QLineEdit.Password)
        if ok and password:
            reader.login_password(reader.username, password, reader.mandant)

    def on_itm_issues(self, texts):
        """Fehlerhafte Buchungen in ITM (je Buchung einmal)."""
        text = "\n".join(texts[:3]) + (f"\n(und {len(texts) - 3} weitere)" if len(texts) > 3 else "")
        self.statusBar().showMessage("ITM: " + texts[0], 30000)
        if self.tray:
            self.tray.showMessage("ITM-Zeiterfassung prüfen", text, QSystemTrayIcon.Warning, 10000)

    def stop_itm_reader(self):
        if self.itm_reader:
            self.itm_reader.stop()
            self.itm_reader.deleteLater()
            self.itm_reader = None
            self.update_source_indicators()  # zieht auch die Ladeanzeige mit

    # ---------------------- Matrix42-Buchungen ---------------------------------

    def start_m42_reader(self):
        if self._paw_blocks("Matrix42"):
            return
        if self.m42_reader or not self.config.get("m42_url"):
            if not self.config.get("m42_url"):
                self.statusBar().showMessage(
                    "Matrix42: Bitte zuerst die Adresse der Kalenderseite eintragen "
                    "(Einstellungen → Datenquellen → Einrichten → Matrix42 …)", 8000)
            return
        from m42_reader import M42Reader
        self.m42_reader = M42Reader(self.config.get("m42_url", ""), mt.M42_FILE, mt.M42_PROFILE_DIR,
                                    self, weeks_back=self.config.get("m42_weeks_back", 4))
        self.m42_reader.status_changed.connect(lambda _t: self.update_source_indicators())
        self.m42_reader.busy_changed.connect(self.update_busy_bar)
        self.m42_reader.day_read.connect(
            lambda d: self.timeline.draw_timeline(self.current_date)
            if d == self.current_date.toString("yyyy-MM-dd") else None
        )
        self.m42_reader.login_required.connect(
            lambda: self.tray and self.tray.showMessage(
                "Matrix42-Anmeldung nötig",
                "Zeitzeuge kann die gebuchten Zeiten nicht lesen. Klick hier, um dich anzumelden.",
                QSystemTrayIcon.Warning, 8000,
            )
        )
        self.m42_reader.recording_done.connect(self.on_recording_done)
        self._watch_reader(self.m42_reader)
        self.m42_reader.start()
        self.m42_reader.want(self.current_date.toString("yyyy-MM-dd"))
        self.update_source_indicators()

    def stop_m42_reader(self):
        if self.m42_reader:
            self.m42_reader.stop()
            self.m42_reader.deleteLater()
            self.m42_reader = None
            self.update_source_indicators()

    # ---------------------- Absicherung gegen Fehler und Aussetzer -------------

    WATCH_INTERVAL = 60 * 1000     # Wächter für die Hintergrund-Leser
    PROBLEM_INTERVAL = 15 * 1000   # Meldungen aus safe_io anzeigen
    TRAY_PROBLEM_GAP = 10 * 60     # Probleme höchstens so oft im Infobereich melden (Sekunden)

    def _init_robustness(self):
        """Wächter für die Leser, Anzeige von Problemen, Edge-Reste aufräumen."""
        self._last_tray_problem = 0
        self.watch_timer = QTimer(self)
        self.watch_timer.timeout.connect(self._watch_readers)
        self.watch_timer.start(self.WATCH_INTERVAL)
        self.problem_timer = QTimer(self)
        self.problem_timer.timeout.connect(self.show_problems)
        self.problem_timer.start(self.PROBLEM_INTERVAL)
        # Probleme beim Start (z. B. kaputte Config) gleich nach dem Anzeigen einmal sagen
        QTimer.singleShot(1500, lambda: self.show_problems(startup=True))
        if not self.is_paw():  # PAW: keine Prozesse durchsuchen oder beenden
            threading.Thread(target=self._kill_orphans, daemon=True, name="Edge-Reste").start()

    def _watch_reader(self, reader):
        reader.trouble.connect(self.on_reader_trouble)

    def _watch_readers(self):
        """Tote Lese-Threads neu starten, hängende Durchläufe abbrechen."""
        for reader in self.all_readers():
            if not reader or reader.stopped:
                continue
            try:
                reader.check_hung()
                if not reader.alive():
                    safe_io.log(f"{reader.NAME}: Lese-Thread war beendet, Wächter startet ihn neu")
                    reader.start()
            except Exception as e:
                safe_io.log(f"Wächter: {reader.NAME} nicht neu gestartet: {e!r}")

    def _kill_orphans(self):
        """Edge-Reste mit Zeitzeuge-Profilen nach einem Absturz beenden (nie dein normaler Edge).
        Für eingeschaltete Leser macht das der Leser selbst, bevor er Edge startet."""
        try:
            for key, profile in (("pbx_reader_enabled", mt.PBX_PROFILE_DIR),
                                 ("itm_reader_enabled", mt.ITM_PROFILE_DIR),
                                 ("m42_reader_enabled", mt.M42_PROFILE_DIR)):
                if self.config.get(key) or not os.path.isdir(profile):
                    continue
                from pbx_reader import kill_profile_processes
                count = kill_profile_processes(profile)
                if count:
                    safe_io.log(f"{count} übrig gebliebene Edge-Prozesse ({os.path.basename(profile)}) beendet")
        except Exception as e:
            safe_io.log(f"Edge-Reste nicht beendet: {e!r}")

    def on_reader_trouble(self, text):
        """Ein Leser hat mehrmals hintereinander nichts lesen können (einmal pro Störung)."""
        self.statusBar().showMessage(text, 30000)
        if self.tray:
            self.tray.showMessage("Zeitzeuge", text, QSystemTrayIcon.Warning, 8000)

    def show_problems(self, startup=False):
        """Gemerkte Probleme (kaputte Dateien, Fehler) in Statuszeile und Infobereich zeigen."""
        problems = safe_io.take_problems()
        if not problems:
            return
        text = problems[-1] if len(problems) == 1 else \
            f"{problems[-1]} (und {len(problems) - 1} weitere, siehe fehler.log)"
        self.statusBar().showMessage(text, 30000)
        now = time.time()
        if self.tray and (startup or (not self.isVisible()
                                      and now - self._last_tray_problem > self.TRAY_PROBLEM_GAP)):
            self._last_tray_problem = now
            self.tray.showMessage("Zeitzeuge", "\n".join(problems[-3:]), QSystemTrayIcon.Warning, 10000)
