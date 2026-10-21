"""
Einrichtungsassistent für die Browser-Anbindung (Tampermonkey + 3CX-Skript).

Chrome erlaubt aus Sicherheitsgründen keine stille Installation von
Erweiterungen und Skripten. Der Assistent öffnet deshalb die richtigen Seiten,
und du bestätigst jeweils mit einem Klick. Zeitzeuge prüft selbst, ob alles läuft.
"""

import glob
import os
import re
import subprocess
import webbrowser

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QGridLayout, QLabel,
                             QLineEdit, QPushButton, QVBoxLayout)

import call_import

TAMPERMONKEY_ID = "dhdgffkkebhmkfjojejmpbldmpobfkfo"
TAMPERMONKEY_STORE = f"https://chromewebstore.google.com/detail/{TAMPERMONKEY_ID}"

CHROME_PATHS = [
    r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe",
    r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe",
    r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
]


def build_userscript(template, pbx_url, port):
    """Skript-Vorlage an 3CX-Adresse und Port anpassen."""
    pbx_url = pbx_url.strip().rstrip("/") or "https://voice.visaas.de:5001"
    own = f"http://127.0.0.1:{port}/zeitzeuge_anrufe.user.js"
    header = (f"// @include      {pbx_url}/*\n"
              f"// @downloadURL  {own}\n"
              f"// @updateURL    {own}\n")
    text = re.sub(r"^// @(match|include|downloadURL|updateURL)\b.*\n", "", template, flags=re.M)
    text = text.replace("// @grant", header + "// @grant", 1)
    return text.replace('"http://127.0.0.1:8765"', f'"http://127.0.0.1:{port}"')


def find_chrome():
    for path in CHROME_PATHS:
        path = os.path.expandvars(path)
        if os.path.exists(path):
            return path
    return None


def open_in_chrome(url):
    chrome = find_chrome()
    if chrome:
        subprocess.Popen([chrome, url])
    else:
        webbrowser.open(url)


def tampermonkey_installed():
    pattern = os.path.expandvars(
        rf"%LOCALAPPDATA%\Google\Chrome\User Data\*\Extensions\{TAMPERMONKEY_ID}"
    )
    return bool(glob.glob(pattern))


class BrowserSetupDialog(QDialog):
    def __init__(self, config, port, save_config, parent=None):
        super().__init__(parent)
        self.config = config
        self.port = port
        self.save_config = save_config
        self.setWindowTitle("Browser-Anbindung einrichten")
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Damit Zeitzeuge deine Anrufe aus dem 3CX-Webclient bekommt, braucht Chrome "
            "die Erweiterung <b>Tampermonkey</b> und das Zeitzeuge-Skript. "
            "Chrome lässt das nicht ohne deine Bestätigung zu, deshalb öffnet jeder "
            "Schritt die passende Seite."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.setVerticalSpacing(14)
        layout.addLayout(grid)

        self.status_labels = []

        def step(row, title, text, button_text, slot):
            state = QLabel("")
            state.setFixedWidth(22)
            state.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
            label = QLabel(f"<b>{row + 1}. {title}</b><br>{text}")
            label.setWordWrap(True)
            button = QPushButton(button_text)
            button.clicked.connect(slot)
            grid.addWidget(state, row, 0)
            grid.addWidget(label, row, 1)
            grid.addWidget(button, row, 2, Qt.AlignTop)
            self.status_labels.append(state)
            return label

        step(0, "Tampermonkey installieren",
             "Im Chrome Web Store auf <i>Hinzufügen</i> klicken.",
             "Web Store öffnen", lambda: open_in_chrome(TAMPERMONKEY_STORE))
        step(1, "Nutzerskripte erlauben",
             "Auf der Seite von Tampermonkey den Schalter <i>Nutzerskripte zulassen</i> "
             "einschalten (nötig ab Chrome 138).",
             "Erweiterung öffnen",
             lambda: open_in_chrome(f"chrome://extensions/?id={TAMPERMONKEY_ID}"))

        pbx_row = QLabel("<b>3. 3CX-Adresse und Skript</b><br>"
                         "Adresse deines 3CX-Webclients, dann <i>Installieren</i> "
                         "und in Tampermonkey bestätigen.")
        pbx_row.setWordWrap(True)
        self.pbx_edit = QLineEdit(self.config.get("calls_3cx_url", "https://voice.visaas.de:5001"))
        self.pbx_edit.setAccessibleName("3CX-Adresse")
        install = QPushButton("Skript installieren")
        install.clicked.connect(self.install_script)
        state = QLabel("")
        state.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.status_labels.append(state)
        box = QVBoxLayout()
        box.addWidget(pbx_row)
        box.addWidget(self.pbx_edit)
        grid.addWidget(state, 2, 0)
        grid.addLayout(box, 2, 1)
        grid.addWidget(install, 2, 2, Qt.AlignTop)

        self.test_label = step(3, "Testen",
                               "Anrufliste öffnen. Sobald das Skript sich meldet, "
                               "erscheint hier ein Haken.",
                               "Anrufliste öffnen", self.open_call_list)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.accept)
        layout.addWidget(buttons)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_status)
        self.timer.start(2000)
        self.update_status()

    def _pbx_url(self):
        url = self.pbx_edit.text().strip().rstrip("/")
        if self.config.get("calls_3cx_url") != url:
            self.config["calls_3cx_url"] = url
            self.save_config(self.config)
        return url

    def install_script(self):
        self._pbx_url()
        open_in_chrome(f"http://127.0.0.1:{self.port}/zeitzeuge_anrufe.user.js")

    def open_call_list(self):
        open_in_chrome(f"{self._pbx_url()}/#/call_history/all")

    def update_status(self):
        ok, unknown = "✅", "–"
        tm = tampermonkey_installed()
        ping = call_import.status["last_ping"]
        post = call_import.status["last_post"]
        script_ok = ping is not None

        states = [ok if tm or script_ok else "❌"] + [ok if script_ok else unknown] * 3
        names = {ok: "erledigt", "❌": "fehlt", unknown: "noch offen"}
        for label, state in zip(self.status_labels, states):
            label.setText(state)
            label.setAccessibleName(names[state])  # Symbole allein liest kein Screenreader sinnvoll

        if script_ok:
            text = (f"Skript Version {call_import.status['script_version'] or '?'} "
                    f"hat sich um {ping:%H:%M:%S} gemeldet.")
            if post:
                text += (f" Letzte Übertragung {post:%H:%M:%S}, "
                         f"{call_import.status['last_count']} Anrufe.")
            self.test_label.setText(f"<b>4. Testen</b><br>{text}")
