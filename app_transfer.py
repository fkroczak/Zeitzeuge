"""Hauptfenster: Daten an einen anderen PC übergeben (Export) und übernehmen (Import).

Gedacht für die PAW: Auf dem Arbeits-PC exportieren, die Datei (oder den Text aus der
Zwischenablage) von Hand auf die PAW bringen und dort übernehmen. Die PAW zeigt dann
ihre eigenen RDM-Verbindungen zusammen mit Anrufen, Personalzeit, Matrix42, VPN,
TeamViewer, Fenstern und Tätigkeiten vom Arbeits-PC.

Teil von TimelineApp (main_timeline.py), nur über main_timeline laden.
"""
import os
from datetime import date, timedelta

from PySide6.QtCore import QDate, QStandardPaths, Qt
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QLabel, QMessageBox, QPushButton, QSpinBox, QVBoxLayout)

import safe_io
import transfer
from activity_tracker import read_segments
from m42_data import load_store
import main_timeline as mt  # Pfade und save_config zur Laufzeit von dort (Tests ersetzen sie dort)

# Was "Als PAW einrichten" ausschaltet: alles außer RDM (Schlüssel, Text für die Rückfrage)
PAW_OFF = [("teamviewer_enabled", "TeamViewer-Logs"), ("sophos_enabled", "Sophos Connect"),
           ("forti_enabled", "FortiClient"), ("vpn_enabled", "weitere VPN-Logs"),
           ("pbx_reader_enabled", "3CX"), ("itm_reader_enabled", "ITM"),
           ("m42_reader_enabled", "Matrix42")]


class TransferMixin:
    # ---------------------- Export --------------------------------------------

    def collect_export(self, days_back, today=None):
        """Eigene Daten der letzten days_back Tage (ohne übernommene) als Export-dict."""
        today = today or date.today()
        # personalzeiten.json direkt lesen (itm_reader würde die Edge-Steuerung mitladen)
        itm_days = {k: v for k, v in safe_io.read_json(mt.ITM_FILE, {}, expect=dict).items()
                    if isinstance(v, dict)} if os.path.exists(mt.ITM_FILE) else {}
        m42_days = load_store(mt.M42_FILE)[0] if os.path.exists(mt.M42_FILE) else {}
        imported, self.timeline.imported = self.timeline.imported, None  # nur eigene Daten
        try:
            days = {}
            for i in range(days_back):
                d = today - timedelta(days=i)
                ds = d.isoformat()
                qd = QDate(d.year, d.month, d.day)
                journal = self.journal.load(ds)
                m42 = self.m42_reader.day(ds) if self.m42_reader else None
                if m42 is None:
                    m42 = m42_days.get(ds)  # [] heißt: gelesen, nichts gebucht
                days[ds] = {
                    "verbindungen": [{k: v for k, v in a.items() if k != "is_suggestion"}
                                     for a in self.timeline.activities_for(qd)],
                    "pc": (self.tracker.segments_for(ds) if self.tracker
                           else read_segments(mt.ACTIVITY_DIR, ds)),
                    "personalzeit": (self.itm_reader.day(ds) if self.itm_reader else None)
                    or itm_days.get(ds),
                    "m42": m42,
                    "taetigkeiten": {"items": journal.get("items", []),
                                     "ignored": journal.get("ignored", [])}
                    if journal.get("items") or journal.get("ignored") else None,
                    # schon erstellte KI-Vorschläge (die PAW kann Claude meist nicht erreichen)
                    "ki": self._ai_export(ds),
                }
        finally:
            self.timeline.imported = imported
        return transfer.make_export(days, self.config.get("teamviewer_names", {}))

    def _ai_export(self, date_str):
        data = self.ai_store.load(date_str)
        if not data or not data.get("items"):
            return None
        return {"items": data["items"], "model": data.get("model", ""),
                "created": data.get("created", "")}

    def export_data(self):
        if self.timeline._tv_index is None:
            QMessageBox.information(self, "Daten exportieren",
                                    "Die Logs werden gerade noch gelesen. Bitte gleich noch einmal.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Daten für einen anderen PC exportieren")
        dialog.setMinimumWidth(520)
        layout = QVBoxLayout(dialog)
        info = QLabel(
            "Zeitzeuge packt deine Daten in eine einzige Datei: Anrufe, Personalzeit, Matrix42, "
            "VPN, TeamViewer, RDM, aktive Fenster, Tätigkeiten und schon erstellte KI-Vorschläge. Auf dem anderen PC (z. B. der PAW) "
            "übernimmst du sie mit „Daten übernehmen“ und siehst dort alles zusammen.\n\n"
            "Geht keine Datei hinüber, nimm „In Zwischenablage kopieren“ und füge den Text dort "
            "über „Aus Zwischenablage“ ein. Der Inhalt ist gepackt, aber nicht verschlüsselt.")
        info.setWordWrap(True)
        layout.addWidget(info)
        form = QFormLayout()
        days = QSpinBox()
        days.setRange(1, 400)
        days.setSuffix(" Tage")
        days.setValue(int(self.config.get("export_days", 31)))
        form.addRow("&Zeitraum (bis heute):", days)
        layout.addLayout(form)
        status = QLabel("")
        status.setObjectName("hint")
        status.setWordWrap(True)
        layout.addWidget(status)

        def build():
            self.config["export_days"] = days.value()
            mt.save_config(self.config)
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                return self.collect_export(days.value())
            finally:
                QApplication.restoreOverrideCursor()

        def save_file():
            export = build()
            folder = QStandardPaths.writableLocation(QStandardPaths.DesktopLocation) or mt.DATA_DIR
            name = f"Zeitzeuge-Export_{export['pc']}_{date.today():%Y-%m-%d}.zeitzeuge"
            path, _ = QFileDialog.getSaveFileName(dialog, "Export speichern", os.path.join(folder, name),
                                                  "Zeitzeuge-Export (*.zeitzeuge)")
            if not path:
                return
            try:
                with open(path, "wb") as f:
                    f.write(transfer.to_bytes(export))
            except OSError as e:
                QMessageBox.warning(dialog, "Export", f"Speichern fehlgeschlagen:\n{e}")
                return
            status.setText(f"Gespeichert ({os.path.getsize(path) // 1024 + 1} KB): {path}\n\n"
                           + transfer.summary(export))

        def copy_clip():
            export = build()
            text = transfer.to_clipboard_text(export)
            QApplication.clipboard().setText(text)
            status.setText(f"In der Zwischenablage ({len(text) // 1024 + 1} KB Text).\n\n"
                           + transfer.summary(export))

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        file_btn = QPushButton("Als &Datei speichern …")
        file_btn.clicked.connect(save_file)
        clip_btn = QPushButton("In &Zwischenablage kopieren")
        clip_btn.clicked.connect(copy_clip)
        buttons.addButton(file_btn, QDialogButtonBox.ActionRole)
        buttons.addButton(clip_btn, QDialogButtonBox.ActionRole)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    # ---------------------- Import --------------------------------------------

    def import_export(self, export, parent=None):
        """Export übernehmen (nach Rückfrage). True, wenn übernommen."""
        answer = QMessageBox.question(parent or self, "Daten übernehmen",
                                      transfer.summary(export) + "\n\nÜbernehmen?")
        if answer != QMessageBox.Yes:
            return False
        try:
            count = self.imported.add(export, own_pc=transfer.pc_name())
        except (transfer.TransferError, OSError) as e:
            QMessageBox.warning(parent or self, "Daten übernehmen", str(e))
            return False
        self._rule_cache.clear()
        self.timeline.draw_timeline(self.current_date)
        self.statusBar().showMessage(f"{count} Tage von {export['pc']} übernommen", 8000)
        return True

    def import_data(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Daten von einem anderen PC übernehmen")
        dialog.setMinimumWidth(520)
        layout = QVBoxLayout(dialog)
        info = QLabel(
            "Übernimm hier einen Export vom anderen PC (Datei oder Text aus der Zwischenablage). "
            "Die Daten erscheinen zusammen mit den Daten dieses PCs in Timeline und Tagesliste. "
            "Ein neuerer Export ersetzt die Tage des älteren.")
        info.setWordWrap(True)
        layout.addWidget(info)
        state = QLabel()
        state.setObjectName("hint")
        state.setWordWrap(True)
        layout.addWidget(state)

        def refresh():
            state.setText("Bisher übernommen:\n" + self.imported.describe() if self.imported
                          else "Bisher nichts übernommen.")
            clear_btn.setEnabled(bool(self.imported))

        def from_file():
            folder = QStandardPaths.writableLocation(QStandardPaths.DesktopLocation) or mt.DATA_DIR
            path, _ = QFileDialog.getOpenFileName(dialog, "Export öffnen", folder,
                                                  "Zeitzeuge-Export (*.zeitzeuge);;Alle Dateien (*)")
            if not path:
                return
            try:
                with open(path, "rb") as f:
                    export = transfer.parse(f.read())
            except (OSError, transfer.TransferError) as e:
                QMessageBox.warning(dialog, "Daten übernehmen", str(e))
                return
            self.import_export(export, dialog)
            refresh()

        def from_clip():
            try:
                export = transfer.parse(QApplication.clipboard().text())
            except transfer.TransferError as e:
                QMessageBox.warning(dialog, "Daten übernehmen", str(e))
                return
            self.import_export(export, dialog)
            refresh()

        def clear():
            if QMessageBox.question(dialog, "Übernommene Daten löschen",
                                    "Alle übernommenen Daten anderer PCs von diesem PC löschen? "
                                    "Die eigenen Daten bleiben.") != QMessageBox.Yes:
                return
            self.imported.clear()
            self._rule_cache.clear()
            self.timeline.draw_timeline(self.current_date)
            refresh()

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        file_btn = QPushButton("&Datei wählen …")
        file_btn.clicked.connect(from_file)
        clip_btn = QPushButton("Aus &Zwischenablage")
        clip_btn.clicked.connect(from_clip)
        clear_btn = QPushButton("Übernommene &löschen")
        clear_btn.clicked.connect(clear)
        for b in (file_btn, clip_btn, clear_btn):
            buttons.addButton(b, QDialogButtonBox.ActionRole)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        refresh()
        dialog.exec()

    # ---------------------- PAW -----------------------------------------------

    def toggle_paw(self, on):
        if on == self.is_paw():
            return
        if on:
            if not self.setup_paw():
                self.paw_action.blockSignals(True)
                self.paw_action.setChecked(False)
                self.paw_action.blockSignals(False)
            return
        self.config["pc_role"] = ""
        mt.save_config(self.config)
        self.statusBar().showMessage("PAW-Modus aus. Datenquellen und Nachfragen kannst du wieder "
                                     "einschalten.", 8000)

    def setup_paw(self):
        """Diesen PC als PAW einrichten: nur RDM sammeln, keine Leser, keine Nachfragen.
        True, wenn eingerichtet."""
        answer = QMessageBox.question(
            self, "Als PAW einrichten",
            "Auf diesem PC sammelt Zeitzeuge dann nur die RDM-Verbindungen. Ausgeschaltet werden: "
            + ", ".join(text for _k, text in PAW_OFF)
            + ", aktive Fenster sowie Nachfragen und Erinnerungen.\n\n"
            "Alles andere übernimmst du vom Arbeits-PC über „Daten übernehmen“. "
            "Zeitzeuge startet hier außerdem nie Edge im Hintergrund und durchsucht oder beendet "
            "keine Prozesse, damit der Virenscanner (z. B. Cortex XDR) nichts Verdächtiges sieht.\n\n"
            "Jede Einstellung lässt sich später wieder einschalten.\n\nJetzt einrichten?")
        if answer != QMessageBox.Yes:
            return False
        if not self.config.get("rdm_enabled", True):
            self.source_actions["rdm_enabled"].setChecked(True)
        for key, _text in PAW_OFF:
            action = self.source_actions.get(key)
            if action and action.isChecked():
                action.setChecked(False)  # schaltet über toggle_source sauber ab
            self.config[key] = False
        self.tracking_action.setChecked(False)
        self.config.update({"pc_role": "paw", "prompt_mode": "off", "prompt_on_quit": False,
                            "prompt_end_of_day": False})
        mt.save_config(self.config)
        self.timeline.refresh()
        self.statusBar().showMessage("Als PAW eingerichtet: Zeitzeuge sammelt hier nur RDM", 8000)
        return True
