"""Dialoge zum Schutz der Daten: Schlüssel zeigen, Schlüssel eingeben, gesperrte Daten öffnen.

Ziffernschlüssel (Wiederherstellung, Übertragung) haben 8 Blöcke à 6 Ziffern, siehe datakey.py.
Sie gehören in RDM (Eintrag „Zeitzeuge“), nie in eine Befehlszeile: Cortex XDR protokolliert
Befehlszeilen zentral.
"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
                               QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout)

from theme import prose
import datakey
import datastore
import winhello

CLIPBOARD_CLEAR_MS = 2 * 60 * 1000  # kopierten Schlüssel danach aus der Zwischenablage nehmen


def _code_font():
    font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    font.setPointSizeF(max(font.pointSizeF(), 10) * 1.3)
    font.setBold(True)
    return font


def copy_secret(text):
    """In die Zwischenablage, nach 2 Minuten wieder heraus (falls noch derselbe Text)."""
    clip = QApplication.clipboard()
    clip.setText(text)
    QTimer.singleShot(CLIPBOARD_CLEAR_MS, lambda: clip.text() == text and clip.clear())


def _card(dialog, title, subtitle=""):
    """Rahmen wie „Tätigkeit nachtragen“ (card_dialog.py). Der erklärende Text bleibt im Inhalt:
    Bei Schlüssel und PIN zählt jedes Wort."""
    from card_dialog import modernize
    modernize(dialog, title, subtitle, "lock", intro=False)


class CodeDialog(QDialog):
    """Neuen Schlüssel einmal zeigen. „Fertig“ erst nach dem Haken „in RDM abgelegt“."""

    def __init__(self, title, intro, code, rdm_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        text = QLabel(intro)
        text.setWordWrap(True)
        prose(text)
        layout.addWidget(text)
        self.code = QLineEdit(code)
        self.code.setReadOnly(True)
        self.code.setFont(_code_font())
        self.code.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.code.setAccessibleName(title)
        self.code.setMinimumHeight(self.code.sizeHint().height() + 12)
        layout.addWidget(self.code)
        hint = QLabel(f"So geht es: In RDM einen Eintrag „{rdm_name}“ anlegen (Typ „Zugangsdaten“ "
                      "oder „Kennwort“) und den Schlüssel als Kennwort einfügen. "
                      "Die Zwischenablage leert sich nach 2 Minuten von selbst.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        prose(hint)
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
        _card(self, title, "Wird nur dieses eine Mal angezeigt.")
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
        prose(text)
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
        _card(self, title)

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
        prose(text)
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
        _card(self, title)
        text.setMinimumHeight(text.heightForWidth(self.minimumWidth() - 32))

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


def _hwnd(parent):
    try:
        return int(parent.window().winId()) if parent else None
    except (AttributeError, RuntimeError):
        return None


def _ask_hello(store, parent):
    """Windows Hello beim Start. True = geöffnet, False = beenden, None = weiter (PIN oder
    Wiederherstellungsschlüssel). Bei Abbruch oder Fehler fragt ein Hinweis, wie es weitergeht."""
    while True:
        try:
            store.unlock_with_hello(_hwnd(parent))
            return True
        except winhello.HelloCancelled:
            text = "Windows Hello wurde abgebrochen."
        except winhello.HelloMissing:
            text = ("Der Windows-Hello-Schlüssel von Zeitzeuge fehlt auf diesem PC (z. B. Windows Hello "
                    "oder das TPM wurde zurückgesetzt).")
        except (winhello.HelloError, datakey.WrongKey) as e:
            text = str(e)
        box = QMessageBox(QMessageBox.Warning, "Zeitzeuge entsperren", text, parent=parent)
        again = box.addButton("&Nochmal versuchen", QMessageBox.AcceptRole)
        other = box.addButton("&PIN eingeben …" if store.pin_required() else "&Wiederherstellungsschlüssel …",
                              QMessageBox.ActionRole)
        box.addButton("Zeitzeuge &beenden", QMessageBox.RejectRole)
        box.setDefaultButton(again)
        box.exec()
        if box.clickedButton() is other:
            return None
        if box.clickedButton() is not again:
            return False


def ask_unlock(store, parent=None):
    """Daten gesperrt: Windows Hello bzw. PIN erfragen (wenn eingeschaltet) oder den
    Wiederherstellungsschlüssel (anderer PC oder Windows-Konto, PIN vergessen, Hello weg).
    True, wenn entsperrt. Abbrechen ändert nichts an den Daten."""
    hello = store.hello_required()
    rdp = winhello.remote_session()
    if hello and not rdp and store.has_own_hello():
        answer = _ask_hello(store, parent)
        if answer is not None:
            return answer
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
    why = ("In einer Remotedesktop-Sitzung geht Windows Hello nicht. Melde dich direkt am PC an "
           "oder nimm den Wiederherstellungsschlüssel."
           if hello and rdp and not store.pin_required() else
           "Zeitzeuge kann deine Daten mit dieser Windows-Anmeldung nicht öffnen (neuer PC, "
           "anderes Windows-Konto oder Windows Hello zurückgesetzt). Mit dem "
           "Wiederherstellungsschlüssel geht es.")
    dialog = EnterCodeDialog(
        "Daten sind gesperrt",
        "Daten sind gesperrt – Wiederherstellungsschlüssel aus RDM eingeben.\n\n"
        f"{why}\n\nAbbrechen beendet Zeitzeuge, die Daten bleiben unverändert.",
        "&Wiederherstellungsschlüssel:", store.unlock_with_code, ok_text="Ö&ffnen",
        cancel_text="Zeitzeuge &beenden", parent=parent)
    if dialog.exec() != QDialog.Accepted:
        return False
    if hello and not rdp and not store.has_own_hello():
        _offer_hello(store, parent)
    if store.pin_required():
        pin = ask_new_pin(parent, "Neue PIN für dieses Windows-Konto",
                          "Deine Daten sind offen. Lege für dieses Windows-Konto eine PIN fest; "
                          "beim nächsten Start fragt Zeitzeuge danach.\n\nOhne PIN brauchst du beim "
                          "nächsten Start wieder den Wiederherstellungsschlüssel.")
        if pin:
            store.set_pin(pin)
    return True


def _offer_hello(store, parent):
    """Nach dem Wiederherstellungsschlüssel: Windows Hello für dieses Konto/diesen PC neu einrichten."""
    answer = QMessageBox.question(
        parent, "Windows Hello einrichten",
        "Deine Daten sind offen. Windows Hello für dieses Windows-Konto einrichten? Windows Hello "
        "fragt dabei einmal nach.\n\nOhne Windows Hello brauchst du beim nächsten Start wieder "
        "den Wiederherstellungsschlüssel" + (" oder deine PIN." if store.pin_required() else "."),
        QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
    if answer != QMessageBox.Yes:
        return
    try:
        store.enable_hello(_hwnd(parent))
    except winhello.HelloCancelled:
        pass
    except (winhello.HelloError, datakey.WrongKey, ValueError, datastore.Busy) as e:
        QMessageBox.warning(parent, "Windows Hello einrichten", f"Ging nicht:\n{e}")


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
