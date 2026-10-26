"""Dialoge zum Schutz der Daten: Schlüssel zeigen, Schlüssel eingeben, gesperrte Daten öffnen.

Ziffernschlüssel (Wiederherstellung, Übertragung) haben 8 Blöcke à 6 Ziffern, siehe datakey.py.
Sie gehören in RDM (Eintrag „Zeitzeuge“), nie in eine Befehlszeile: Cortex XDR protokolliert
Befehlszeilen zentral.
"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
                               QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout)

import datakey

CLIPBOARD_CLEAR_MS = 2 * 60 * 1000  # kopierten Schlüssel danach aus der Zwischenablage nehmen


def _code_font():
    font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    font.setPointSizeF(max(font.pointSizeF(), 10) * 1.3)
    font.setWeight(QFont.DemiBold)
    return font


def copy_secret(text):
    """In die Zwischenablage, nach 2 Minuten wieder heraus (falls noch derselbe Text)."""
    clip = QApplication.clipboard()
    clip.setText(text)
    QTimer.singleShot(CLIPBOARD_CLEAR_MS, lambda: clip.text() == text and clip.clear())


class CodeDialog(QDialog):
    """Neuen Schlüssel einmal zeigen. „Fertig“ erst nach dem Haken „in RDM abgelegt“."""

    def __init__(self, title, intro, code, rdm_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        text = QLabel(intro)
        text.setWordWrap(True)
        layout.addWidget(text)
        self.code = QLineEdit(code)
        self.code.setReadOnly(True)
        self.code.setFont(_code_font())
        self.code.setAlignment(Qt.AlignCenter)
        self.code.setAccessibleName(title)
        self.code.setMinimumHeight(self.code.sizeHint().height() + 12)
        layout.addWidget(self.code)
        hint = QLabel(f"So geht es: In RDM einen Eintrag „{rdm_name}“ anlegen (Typ „Zugangsdaten“ "
                      "oder „Kennwort“) und den Schlüssel als Kennwort einfügen. "
                      "Die Zwischenablage leert sich nach 2 Minuten von selbst.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.saved = QCheckBox(f"Ich habe den Schlüssel in RDM unter „{rdm_name}“ abgelegt")
        layout.addWidget(self.saved)
        buttons = QDialogButtonBox()
        copy = QPushButton("&Kopieren")
        copy.clicked.connect(lambda: (copy_secret(code), copy.setText("&Kopiert")))
        buttons.addButton(copy, QDialogButtonBox.ActionRole)
        self.done_button = buttons.addButton("&Fertig", QDialogButtonBox.AcceptRole)
        self.done_button.setEnabled(False)
        self.saved.toggled.connect(self.done_button.setEnabled)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
        copy.setFocus()

    def reject(self):
        # Esc/Schließen: nur nach dem Haken, sonst ginge der Schlüssel ungesehen verloren
        if self.saved.isChecked():
            super().reject()
            return
        answer = QMessageBox.question(
            self, self.windowTitle(),
            "Hast du den Schlüssel gesichert? Er wird nicht noch einmal angezeigt.\n\n"
            "Ohne ihn kommst du auf einem neuen PC nicht mehr an deine Daten.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            super().reject()


class EnterCodeDialog(QDialog):
    """Ziffernschlüssel eingeben. check(code) wirft BadCode/WrongKey mit Text für den Nutzer."""

    def __init__(self, title, intro, label, check, ok_text="Ö&ffnen", cancel_text="Abbrechen",
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(560)
        self._check = check
        layout = QVBoxLayout(self)
        text = QLabel(intro)
        text.setWordWrap(True)
        layout.addWidget(text)
        form = QFormLayout()
        self.field = QLineEdit()
        self.field.setFont(_code_font())
        self.field.setPlaceholderText("000000-000000-000000-000000-000000-000000-000000-000000")
        form.addRow(label, self.field)
        self.error = QLabel("")
        self.error.setWordWrap(True)
        self.error.hide()
        form.addRow("", self.error)
        layout.addLayout(form)
        buttons = QDialogButtonBox()
        self.ok = buttons.addButton(ok_text, QDialogButtonBox.AcceptRole)
        buttons.addButton(cancel_text, QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self._try)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.field.textChanged.connect(lambda _t: self.error.hide())
        self.code = ""

    def _try(self):
        code = self.field.text()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self._check(code)
        except (datakey.BadCode, datakey.WrongKey, ValueError) as e:
            self.error.setText(str(e))
            self.error.show()
            self.field.setFocus()
            self.field.selectAll()
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.code = datakey.normalize_code(code)
        self.accept()


def ask_unlock(store, parent=None):
    """Daten gesperrt (anderer PC oder Windows-Konto): Wiederherstellungsschlüssel erfragen.
    True, wenn entsperrt. Abbrechen ändert nichts an den Daten."""
    if not store.has_recovery():
        QMessageBox.critical(
            parent, "Daten sind gesperrt",
            "Zeitzeuge kann deine Daten mit dieser Windows-Anmeldung nicht öffnen, und es gibt "
            "keinen Wiederherstellungsschlüssel.\n\n"
            f"Die Daten bleiben unverändert in\n{store.path}\n\n"
            "Starte Zeitzeuge wieder mit dem Windows-Konto, mit dem du es eingerichtet hast.")
        return False
    dialog = EnterCodeDialog(
        "Daten sind gesperrt",
        "Daten sind gesperrt – Wiederherstellungsschlüssel aus RDM eingeben.\n\n"
        "Zeitzeuge kann deine Daten mit dieser Windows-Anmeldung nicht öffnen (neuer PC oder "
        "anderes Windows-Konto). Mit dem Wiederherstellungsschlüssel geht es. Danach startet "
        "Zeitzeuge hier wieder ohne Abfrage.\n\nAbbrechen beendet Zeitzeuge, die Daten bleiben unverändert.",
        "&Wiederherstellungsschlüssel:", store.unlock_with_code, ok_text="Ö&ffnen",
        cancel_text="Zeitzeuge &beenden", parent=parent)
    return dialog.exec() == QDialog.Accepted


RECOVERY_INTRO = (
    "Das ist dein Wiederherstellungsschlüssel. Mit ihm öffnest du deine Daten auf einem neuen "
    "PC oder mit einem anderen Windows-Konto. Zeitzeuge zeigt ihn nur jetzt.\n\n"
    "Lege ihn jetzt in RDM ab. Gib ihn nie in eine Befehlszeile oder Verknüpfung ein.")

TRANSFER_INTRO = (
    "Das ist dein Übertragungsschlüssel. Er verschlüsselt den Export für den anderen PC "
    "(z. B. die PAW). Dort gibst du ihn einmal beim ersten Übernehmen ein.\n\n"
    "Lege ihn jetzt in RDM ab, damit du ihn auf beiden PCs hast.")


def show_recovery_code(code, parent=None):
    CodeDialog("Wiederherstellungsschlüssel", RECOVERY_INTRO, code,
               "Zeitzeuge Wiederherstellung", parent).exec()


def show_transfer_code(code, parent=None):
    CodeDialog("Übertragungsschlüssel", TRANSFER_INTRO, code,
               "Zeitzeuge Übertragung", parent).exec()
