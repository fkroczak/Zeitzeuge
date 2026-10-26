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
import datastore

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
                 parent=None, secret=False, extra=None):
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
        self.secret = secret
        if secret:  # PIN: verdeckt, keine Vorgabe
            self.field.setEchoMode(QLineEdit.Password)
        else:
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
        self.extra_chosen = False
        if extra:  # z. B. „PIN vergessen? Wiederherstellungsschlüssel …“
            other = buttons.addButton(extra, QDialogButtonBox.ActionRole)
            other.clicked.connect(lambda: (setattr(self, "extra_chosen", True), self.reject()))
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
        except (datakey.BadCode, datakey.WrongKey, ValueError, LookupError) as e:
            self.error.setText(str(e))
            self.error.show()
            self.field.setFocus()
            self.field.selectAll()
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.code = code if self.secret else datakey.normalize_code(code)
        self.accept()


class NewPinDialog(QDialog):
    """Neue PIN zweimal eingeben. Fehler stehen als Text neben dem Feld, OK erst, wenn alles passt."""

    def __init__(self, title, intro, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        text = QLabel(intro)
        text.setWordWrap(True)
        layout.addWidget(text)
        form = QFormLayout()
        self.pin = QLineEdit()
        self.pin.setEchoMode(QLineEdit.Password)
        self.again = QLineEdit()
        self.again.setEchoMode(QLineEdit.Password)
        form.addRow("&PIN:", self.pin)
        form.addRow("PIN &wiederholen:", self.again)
        self.error = QLabel("")
        self.error.setWordWrap(True)
        form.addRow("", self.error)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok = buttons.button(QDialogButtonBox.Ok)
        self.ok.setText("PIN &speichern")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.pin.textChanged.connect(self.validate)
        self.again.textChanged.connect(self.validate)
        self.validate()
        text.setMinimumHeight(text.heightForWidth(self.minimumWidth() - 24))

    def validate(self):
        pin, again = self.pin.text(), self.again.text()
        error = ""
        if len(pin) < datakey.PIN_MIN:
            error = f"Mindestens {datakey.PIN_MIN} Zeichen. Länger ist sicherer, z. B. ein kurzer Satz."
        elif again and again != pin:
            error = "Die beiden Eingaben sind verschieden."
        self.error.setText(error)
        self.ok.setEnabled(not error and again == pin)
        return not error

    def value(self):
        return self.pin.text()


PIN_INTRO = (
    "Mit PIN reicht die Windows-Anmeldung allein nicht: Zeitzeuge fragt beim Start danach. "
    "So kommen auch Domänen-Admins nicht an deine Daten.\n\n"
    "Nimm 10 Zeichen oder mehr, z. B. einen kurzen Satz. Eine kurze PIN lässt sich mit einer "
    "Kopie der Datei durchprobieren. Leg sie nicht in RDM ab. Vergisst du sie, hilft der "
    "Wiederherstellungsschlüssel.")


def ask_new_pin(parent=None, title="PIN festlegen", intro=PIN_INTRO):
    """Neue PIN erfragen. "" bei Abbruch."""
    dialog = NewPinDialog(title, intro, parent)
    return dialog.value() if dialog.exec() == QDialog.Accepted else ""


def _ask_pin(store, parent):
    """PIN beim Start. True = geöffnet, False = beenden, None = Wiederherstellungsschlüssel nehmen."""
    def check(pin):
        try:
            store.unlock_with_pin(pin)
        except datastore.Locked as e:  # dieses Konto hat kein PIN-Fach
            raise LookupError(f"{e} Nimm den Wiederherstellungsschlüssel.") from e
    dialog = EnterCodeDialog(
        "Zeitzeuge entsperren",
        "Deine Daten sind mit Windows-Anmeldung und PIN geschützt. Gib deine PIN ein.",
        "&PIN:", check, ok_text="Ö&ffnen", cancel_text="Zeitzeuge &beenden", parent=parent,
        secret=True, extra="PIN &vergessen …")
    if dialog.exec() == QDialog.Accepted:
        return True
    return None if dialog.extra_chosen else False


def ask_unlock(store, parent=None):
    """Daten gesperrt: PIN erfragen (wenn eingeschaltet) oder den Wiederherstellungsschlüssel
    (anderer PC oder Windows-Konto, PIN vergessen). True, wenn entsperrt.
    Abbrechen ändert nichts an den Daten."""
    if store.pin_required():
        answer = _ask_pin(store, parent)
        if answer is not None:
            return answer
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
    if dialog.exec() != QDialog.Accepted:
        return False
    if store.pin_required():
        pin = ask_new_pin(parent, "Neue PIN für dieses Windows-Konto",
                          "Deine Daten sind offen. Lege für dieses Windows-Konto eine PIN fest; "
                          "beim nächsten Start fragt Zeitzeuge danach.\n\nOhne PIN brauchst du beim "
                          "nächsten Start wieder den Wiederherstellungsschlüssel.")
        if pin:
            store.set_pin(pin)
    return True


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
