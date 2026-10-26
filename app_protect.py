"""Hauptfenster: Schutz der Daten (Einstellungen → Datenspeicher → Schutz …).

- Stand anzeigen: Windows-Anmeldung, Wiederherstellungsschlüssel, Übertragungsschlüssel,
  Speicherort von Datenbank und Sicherung.
- Wiederherstellungsschlüssel neu erzeugen (der alte wird ungültig) und prüfen.
- Übertragungsschlüssel für den Export an die PAW erzeugen oder eingeben.
- Fehlt der Wiederherstellungsschlüssel, zeigt die Statuszeile einen Knopf zum Einrichten.
- Sicherung der Datenbank in den Datenordner alle 2 Stunden (wenn sich etwas geändert hat)
  und beim Beenden.

Teil von TimelineApp (main_timeline.py), nur über main_timeline laden.
"""
import os
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QGridLayout, QLabel, QMessageBox,
                               QPushButton, QToolButton, QVBoxLayout)

import datakey
import datastore
import protect_dialogs
import safe_io
import main_timeline as mt

BACKUP_INTERVAL = 2 * 60 * 60 * 1000  # die Sicherung geht über OneDrive: nicht zu oft
TRANSFER_DOC = "uebertragungsschluessel"


def _de(stamp):
    """'2026-10-26 08:00:00' -> '26.10.2026'"""
    return f"{stamp[8:10]}.{stamp[5:7]}.{stamp[:4]}" if stamp and len(stamp) >= 10 else "?"


class ProtectMixin:
    def _init_protection(self):
        self.backup_timer = QTimer(self)
        self.backup_timer.timeout.connect(lambda: mt.backup_store())
        self.backup_timer.start(BACKUP_INTERVAL)
        self.recovery_button = QToolButton(self)
        self.recovery_button.setObjectName("cta")
        self.recovery_button.setText("Wiederherstellungsschlüssel einrichten")
        self.recovery_button.setToolTip("Ohne ihn kommst du auf einem neuen PC nicht an deine Daten")
        self.recovery_button.clicked.connect(self.new_recovery_code)
        self.statusBar().addPermanentWidget(self.recovery_button)
        self.update_protection_hint()
        # Erste Einrichtung: Schlüssel gleich anbieten (nicht in Tests/Hilfsskripten mit eigenem Datenordner)
        if not self.data_store.has_recovery() and not os.environ.get("ZEITZEUGE_DATA"):
            QTimer.singleShot(1200, self._offer_recovery)

    def update_protection_hint(self):
        self.recovery_button.setVisible(not self.data_store.has_recovery())

    def _offer_recovery(self):
        if self.data_store.has_recovery() or not self.isVisible():
            return
        # Nicht blockierend: Zeitzeuge zeichnet weiter auf, während die Frage offen ist
        box = QMessageBox(
            QMessageBox.Question, "Daten verschlüsselt",
            "Zeitzeuge speichert deine Daten jetzt verschlüsselt in einer Datenbank. "
            "Auf diesem PC öffnet sie deine Windows-Anmeldung ohne Abfrage.\n\n"
            "Für einen neuen PC oder ein anderes Windows-Konto brauchst du einen "
            "Wiederherstellungsschlüssel. Jetzt erzeugen und in RDM ablegen?",
            QMessageBox.Yes | QMessageBox.No, self)
        box.setDefaultButton(QMessageBox.Yes)
        box.setAttribute(Qt.WA_DeleteOnClose)
        box.finished.connect(lambda result: result == QMessageBox.Yes and self.new_recovery_code())
        box.open()

    # ---------------------- Wiederherstellungsschlüssel ------------------------

    def new_recovery_code(self, parent=None):
        parent = parent or self
        if self.data_store.has_recovery():
            answer = QMessageBox.question(
                parent, "Wiederherstellungsschlüssel neu erzeugen",
                "Der bisherige Wiederherstellungsschlüssel wird dabei ungültig. "
                "Ersetze danach den Eintrag in RDM.\n\nNeu erzeugen?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return False
        try:
            code = self.data_store.new_recovery_code()
        except (datastore.Busy, datastore.Locked) as e:
            QMessageBox.warning(parent, "Wiederherstellungsschlüssel", f"Ging gerade nicht:\n{e}")
            return False
        protect_dialogs.show_recovery_code(code, parent)
        mt.backup_store(force=True)  # Sicherung soll das neue Fach gleich enthalten
        self.update_protection_hint()
        return True

    def check_recovery_code(self, parent=None):
        store = self.data_store

        def check(code):
            datakey.normalize_code(code)
            probe = datastore.Store(store.path, store.data_dir).open()
            try:  # eigenes Objekt: prüft nur, legt kein Fach an
                for _id, _kind, _lbl, _created, data in probe._slots(datastore.RECOVERY):
                    datakey.unwrap_with_code(data, code)
                    return
                raise datakey.WrongKey("Es gibt noch keinen Wiederherstellungsschlüssel.")
            finally:
                probe.close()
        dialog = protect_dialogs.EnterCodeDialog(
            "Wiederherstellungsschlüssel prüfen",
            "Gib den Schlüssel aus RDM ein. Zeitzeuge prüft nur, ob er passt, und ändert nichts.",
            "&Wiederherstellungsschlüssel:", check, ok_text="&Prüfen", parent=parent or self)
        if dialog.exec() == QDialog.Accepted:
            QMessageBox.information(parent or self, "Wiederherstellungsschlüssel",
                                    "Der Schlüssel passt. Bewahre ihn weiter in RDM auf.")

    # ---------------------- Übertragungsschlüssel ------------------------------

    def transfer_code(self):
        try:
            doc = self.data_store.get(TRANSFER_DOC, "", {}) or {}
        except (datastore.Busy, datastore.Locked):
            return ""
        return doc.get("code", "") if isinstance(doc, dict) else ""

    def _save_transfer_code(self, code):
        self.data_store.put(TRANSFER_DOC, "", {"code": datakey.normalize_code(code),
                                               "seit": f"{datetime.now():%Y-%m-%d %H:%M:%S}"})

    def ensure_transfer_code(self, parent=None, reason=""):
        """Übertragungsschlüssel holen; fehlt er, erzeugen oder eingeben lassen. "" bei Abbruch."""
        code = self.transfer_code()
        if code:
            return code
        return self.setup_transfer_code(parent, reason)

    def setup_transfer_code(self, parent=None, reason=""):
        parent = parent or self
        box = QMessageBox(parent)
        box.setWindowTitle("Übertragungsschlüssel")
        box.setIcon(QMessageBox.Question)
        box.setText((reason + "\n\n" if reason else "")
                    + "Der Übertragungsschlüssel verschlüsselt den Export für den anderen PC. "
                    "Er muss auf beiden PCs gleich sein.\n\n"
                    "Hast du schon einen (in RDM unter „Zeitzeuge Übertragung“)? Dann gib ihn ein. "
                    "Sonst erzeuge hier einen neuen.")
        enter = box.addButton("Vorhandenen &eingeben …", QMessageBox.AcceptRole)
        new = box.addButton("&Neu erzeugen", QMessageBox.ActionRole)
        box.addButton("Abbrechen", QMessageBox.RejectRole)
        box.setDefaultButton(enter)
        box.exec()
        if box.clickedButton() is new:
            code = datakey.new_code()
            protect_dialogs.show_transfer_code(code, parent)
        elif box.clickedButton() is enter:
            dialog = protect_dialogs.EnterCodeDialog(
                "Übertragungsschlüssel eingeben",
                "Gib den Übertragungsschlüssel aus RDM ein. Er ist auf beiden PCs gleich.",
                "Ü&bertragungsschlüssel:", datakey.normalize_code, ok_text="&Speichern",
                parent=parent)
            if dialog.exec() != QDialog.Accepted:
                return ""
            code = dialog.code
        else:
            return ""
        try:
            self._save_transfer_code(code)
        except (datastore.Busy, datastore.Locked) as e:
            QMessageBox.warning(parent, "Übertragungsschlüssel", f"Nicht gespeichert:\n{e}")
        return code

    # ---------------------- Stand ----------------------------------------------

    def protection_state(self):
        """Stand als Texte: (Windows-Anmeldung, Wiederherstellung, Übertragung, Speicherort)."""
        info = self.data_store.protection()
        me = datastore._label()
        auto = info["auto"]
        if os.name != "nt":
            win = "Schlüsseldatei (nur zum Testen, ohne Windows-Schutz)"
        elif any(label == me for _kind, label, _c in auto):
            win = f"öffnet ohne Abfrage für {me}"
        else:
            win = "für dieses Konto noch nicht eingerichtet"
        others = len([1 for _k, label, _c in auto if label != me])
        if others:
            win += f" (dazu {others} weitere PCs oder Konten)"
        recovery = f"angelegt am {_de(info['recovery'])}" if info["recovery"] else "fehlt noch"
        pin = "an" if info["pin"] else "aus"
        transfer = "hinterlegt" if self.transfer_code() else "nicht hinterlegt"
        where = f"Datenbank: {info['path']}\nSicherung: " + (
            mt.BACKUP_FILE if mt.BACKUP_FILE else "keine (Datenbank liegt im Datenordner)")
        return win, pin, recovery, transfer, where

    def protection_text(self):
        win, pin, recovery, transfer, where = self.protection_state()
        return (f"Windows-Anmeldung: {win}\nPIN beim Start: {pin}\nWiederherstellungsschlüssel: {recovery}\n"
                f"Übertragungsschlüssel: {transfer}\n\n{where}")

    # ---------------------- PIN ------------------------------------------------

    def pin_on(self, parent=None):
        """PIN einschalten oder ändern."""
        parent = parent or self
        store = self.data_store
        if store.pin_required():
            pin = protect_dialogs.ask_new_pin(parent, "PIN ändern")
            if pin:
                store.set_pin(pin)
                self.statusBar().showMessage("PIN geändert", 6000)
            return bool(pin)
        if not store.has_recovery():
            QMessageBox.information(parent, "PIN beim Start",
                                    "Lege zuerst einen Wiederherstellungsschlüssel an. "
                                    "Ohne ihn wären deine Daten bei vergessener PIN verloren.")
            if not self.new_recovery_code(parent):
                return False
        pin = protect_dialogs.ask_new_pin(parent)
        if not pin:
            return False
        try:
            store.enable_pin(pin)
        except (ValueError, datastore.Busy, datastore.Locked) as e:
            QMessageBox.warning(parent, "PIN beim Start", str(e))
            return False
        mt.backup_store(force=True)  # Sicherung ohne Fach ohne PIN
        self.statusBar().showMessage("PIN eingeschaltet: Zeitzeuge fragt beim nächsten Start danach", 8000)
        return True

    def pin_off(self, parent=None):
        parent = parent or self
        if not self.data_store.pin_required():
            return False
        answer = QMessageBox.question(
            parent, "PIN ausschalten",
            "Dann öffnet wieder die Windows-Anmeldung allein die Daten, ohne Abfrage. "
            "Domänen-Admins könnten dann wieder herankommen.\n\nPIN ausschalten?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return False
        self.data_store.disable_pin()
        mt.backup_store(force=True)
        return True

    def show_protection(self):
        self.build_protection_dialog().exec()
        self.update_protection_hint()

    def build_protection_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Schutz der Daten")
        dialog.setMinimumWidth(600)
        layout = QVBoxLayout(dialog)
        intro = QLabel("Deine Daten sind verschlüsselt gespeichert (AES-256). "
                       "Schlüssel gehören in RDM, nie in eine Befehlszeile oder Verknüpfung.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(12)
        labels, row_buttons = {}, {}
        rows = [("Windows-Anmeldung:", "win", []),
                ("PIN beim Start:", "pin",
                 [("&Einschalten …", "PIN beim Start einschalten oder ändern", lambda: self.pin_on(dialog)),
                  ("&Ausschalten", "PIN beim Start ausschalten", lambda: self.pin_off(dialog))]),
                ("Wiederherstellungsschlüssel:", "recovery",
                 [("&Neu erzeugen …", "Wiederherstellungsschlüssel neu erzeugen",
                   lambda: self.new_recovery_code(dialog)),
                  ("&Prüfen …", "Wiederherstellungsschlüssel prüfen",
                   lambda: self.check_recovery_code(dialog))]),
                ("Übertragungsschlüssel:", "transfer",
                 [("Än&dern …", "Übertragungsschlüssel erzeugen oder eingeben",
                   lambda: self.setup_transfer_code(dialog))])]
        for row, (title, key, actions) in enumerate(rows):
            head = QLabel(title)
            value = QLabel()
            value.setWordWrap(True)
            head.setBuddy(value)
            grid.addWidget(head, row, 0)
            grid.addWidget(value, row, 1, 1, 1 if actions else 3)
            labels[key] = value
            for col, (text, name, func) in enumerate(actions, 2):
                button = QPushButton(text)
                button.setAccessibleName(name)
                button.setToolTip(name)
                button.clicked.connect(lambda _c=False, f=func: (f(), refresh()))
                grid.addWidget(button, row, col)
                row_buttons.setdefault(key, []).append(button)
        layout.addLayout(grid)
        where = QLabel()
        where.setObjectName("hint")
        where.setWordWrap(True)
        where.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(where)

        def refresh():
            win, pin, recovery, transfer, path = self.protection_state()
            on = self.data_store.pin_required()
            pin_set, pin_clear = row_buttons["pin"]
            pin_set.setText("&Ändern …" if on else "&Einschalten …")
            pin_clear.setEnabled(on)
            labels["pin"].setText(pin)
            labels["win"].setText(win)
            labels["recovery"].setText(recovery)
            labels["transfer"].setText(transfer)
            where.setText(path)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        refresh()
        return dialog

    def close_store(self):
        """Beim Beenden: Sicherung schreiben, Datenbank schließen."""
        try:
            mt.backup_store()
        except Exception as e:  # Beenden darf daran nie scheitern
            safe_io.log(f"Sicherung beim Beenden fehlgeschlagen: {e}")
