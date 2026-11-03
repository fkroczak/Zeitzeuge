"""
Einstellungen → Textbausteine: Bausteine pflegen, zuletzt benutzte Texte, Ticket-Format
und Muster für Ticketnummern. Logik in snippets.py und tickets.py.
"""
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
                               QPlainTextEdit, QPushButton, QVBoxLayout)

import snippets
import tickets


class SnippetsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Textbausteine und Ticket")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        info = QLabel("Häufige Sätze fügst du beim Eintragen mit „Text einfügen“ ein. "
                      "Ein Baustein je Zeile.")
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        self.snippets_edit = QPlainTextEdit("\n".join(snippets.from_config(config)))
        self.snippets_edit.setTabChangesFocus(True)
        self.snippets_edit.setMinimumHeight(160)
        form.addRow("&Bausteine:", self.snippets_edit)
        reset = QPushButton("&Standardliste einsetzen")
        reset.setAutoDefault(False)
        reset.setToolTip("Bausteine durch die mitgelieferte Liste ersetzen")
        reset.clicked.connect(
            lambda: self.snippets_edit.setPlainText("\n".join(snippets.DEFAULT_SNIPPETS)))
        form.addRow("", reset)

        self.recent = QCheckBox("&Zuletzt benutzte Texte zum gewählten Kunden anbieten")
        self.recent.setChecked(config.get("snippets_recent", True))
        form.addRow("", self.recent)
        self.dash = QCheckBox("Beim &Kopieren als Ticket-Doku gliedern: erste Zeile „- “, "
                              "weitere „-- “")
        self.dash.setChecked(config.get("ticket_format", "") == "dash")
        form.addRow("", self.dash)

        self.patterns_edit = QPlainTextEdit("\n".join(config.get("ticket_patterns",
                                                                 tickets.DEFAULT_PATTERNS)))
        self.patterns_edit.setTabChangesFocus(True)
        self.patterns_edit.setFixedHeight(70)
        self.patterns_edit.setToolTip("Regulärer Ausdruck je Zeile, z. B. TCK\\d+ oder "
                                      "Ticket #(\\d+). Leer = keine Vorschläge.")
        form.addRow("&Ticketnummern erkennen:", self.patterns_edit)
        hint = QLabel("Zeitzeuge sucht sie in den Fenstertiteln und Matrix42-Buchungen der "
                      "Tätigkeit und schlägt sie vor. Leer = aus.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        form.addRow("", hint)
        self.error = QLabel()
        self.error.setObjectName("hint")
        self.error.setWordWrap(True)
        form.addRow("", self.error)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok_button = buttons.button(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.patterns_edit.textChanged.connect(self.validate)
        self.validate()

    def patterns(self):
        return [p.strip() for p in self.patterns_edit.toPlainText().splitlines() if p.strip()]

    def validate(self):
        _compiled, errors = tickets.compile_patterns(self.patterns_edit.toPlainText().splitlines())
        text = "; ".join(f"Zeile {no}: {msg}" for no, msg in errors)
        self.error.setText(f"⚠ Fehler im Muster: {text}" if errors else "")
        self.error.setVisible(bool(errors))
        self.ok_button.setEnabled(not errors)
        return not errors

    def apply(self):
        self.config["snippets"] = snippets.clean(self.snippets_edit.toPlainText())
        self.config["snippets_recent"] = self.recent.isChecked()
        self.config["ticket_format"] = "dash" if self.dash.isChecked() else ""
        self.config["ticket_patterns"] = self.patterns()
