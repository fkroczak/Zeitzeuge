import os

from PyQt5.QtCore import QTime
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QColorDialog,
                             QComboBox, QDialog, QDialogButtonBox,
                             QFileDialog, QFormLayout, QGridLayout, QGroupBox,
                             QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
                             QPushButton, QRadioButton, QSpinBox, QTableWidget,
                             QTableWidgetItem, QTimeEdit, QVBoxLayout)

class ConnectionSettingsDialog(QDialog):
    def __init__(self, config, config_key, default_paths, title, parent=None,
                 enabled_text=None, folders=False, hint=None):
        super().__init__(parent)
        self.config = config
        self.config_key = config_key
        self.default_paths = default_paths
        self.enabled_text = enabled_text  # Schalter "auslesen ja/nein" (z. B. VPN)
        self.folders = folders            # auch ganze Ordner als Pfad erlauben
        self.hint = hint
        self.enabled_box = None
        self.setWindowTitle(title)
        self.setMinimumWidth(400)
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()

        if self.enabled_text:
            self.enabled_box = QCheckBox(self.enabled_text)
            self.enabled_box.setChecked(self.config.get(f"{self.config_key}_enabled", True))
            layout.addWidget(self.enabled_box)
        if self.hint:
            hint = QLabel(self.hint)
            hint.setWordWrap(True)
            layout.addWidget(hint)

        # Pfadeinstellungen
        path_group = QGroupBox("Logdatei-Pfade")
        path_layout = QVBoxLayout()
        
        self.path_list = QListWidget()
        self.path_list.setAccessibleName("Logdatei-Pfade")
        # Lade gespeicherte Pfade oder Standardpfade
        saved_paths = self.config.get(f'{self.config_key}_paths', self.default_paths)
        self.path_list.addItems(saved_paths)
        path_layout.addWidget(self.path_list)
        
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("&Hinzufügen …")
        add_btn.clicked.connect(self.add_path)
        remove_btn = QPushButton("&Entfernen")
        remove_btn.clicked.connect(self.remove_path)
        remove_btn.setEnabled(False)
        self.path_list.currentItemChanged.connect(
            lambda item, _old: remove_btn.setEnabled(item is not None))
        
        btn_layout.addWidget(add_btn)
        if self.folders:
            folder_btn = QPushButton("&Ordner hinzufügen …")
            folder_btn.clicked.connect(self.add_folder)
            btn_layout.addWidget(folder_btn)
        btn_layout.addWidget(remove_btn)
        path_layout.addLayout(btn_layout)
        path_group.setLayout(path_layout)
        if self.enabled_box:
            path_group.setEnabled(self.enabled_box.isChecked())
            self.enabled_box.toggled.connect(path_group.setEnabled)
        layout.addWidget(path_group)
        
        # Zeitzonenkorrektur
        tz_group = QGroupBox("Zeitzoneneinstellungen")
        tz_layout = QFormLayout()
        
        # Lade gespeicherte Korrektur oder Standardwert
        saved_tz_correction = self.config.get(f'{self.config_key}_timezone_correction', self.config.get('timezone_correction', 2))
        
        self.tz_spinbox = QSpinBox()
        self.tz_spinbox.setRange(-12, 14)
        self.tz_spinbox.setValue(saved_tz_correction)
        
        tz_layout.addRow("Zeitzonenkorrektur (Stunden):", self.tz_spinbox)
        tz_group.setLayout(tz_layout)
        layout.addWidget(tz_group)
        
        # Button Box
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.setLayout(layout)
    
    def get_paths(self):
        return [self.path_list.item(i).text() for i in range(self.path_list.count())]
    
    def get_timezone_correction(self):
        return self.tz_spinbox.value()
    
    def add_path(self):
        # Datei auswählen statt Pfad abtippen (vermeidet Tippfehler)
        start = os.path.dirname(os.path.expandvars(self.default_paths[0])) if self.default_paths else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Logdatei auswählen", start, "Logdateien (*.txt *.log);;Alle Dateien (*)")
        if path:
            self.path_list.addItem(os.path.normpath(path))
    
    def add_folder(self):
        start = os.path.expandvars(self.default_paths[0]) if self.default_paths else ""
        path = QFileDialog.getExistingDirectory(self, "Ordner mit Logdateien auswählen", start)
        if path:
            self.path_list.addItem(os.path.normpath(path))

    def remove_path(self):
        if self.path_list.currentItem():
            self.path_list.takeItem(self.path_list.currentRow())

class ActivityTypeSettingsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Aktivitätstypen verwalten")
        self.setMinimumWidth(400)
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Typenliste
        type_group = QGroupBox("Aktivitätstypen")
        type_layout = QVBoxLayout()
        
        self.type_list = QListWidget()
        self.type_list.setAccessibleName("Aktivitätstypen")
        self.type_list.addItems(self.config.get('activity_types', []))
        type_layout.addWidget(self.type_list)
        
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("&Hinzufügen …")
        add_btn.clicked.connect(self.add_type)
        remove_btn = QPushButton("&Entfernen")
        remove_btn.clicked.connect(self.remove_type)
        remove_btn.setEnabled(False)
        self.type_list.currentItemChanged.connect(
            lambda item, _old: remove_btn.setEnabled(item is not None))
        
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(remove_btn)
        type_layout.addLayout(btn_layout)
        type_group.setLayout(type_layout)
        layout.addWidget(type_group)
        
        # Farbauswahl
        color_group = QGroupBox("Farbzuordnung")
        color_layout = QFormLayout()
        
        self.color_btn = QPushButton("Erst oben einen Typ wählen")
        self.color_btn.clicked.connect(self.choose_color)
        self.type_list.currentItemChanged.connect(self.update_color_button)
        color_layout.addRow("Aktueller Typ:", self.color_btn)
        
        color_group.setLayout(color_layout)
        layout.addWidget(color_group)
        
        # Button Box
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.setLayout(layout)
        self.update_color_button()
    
    def add_type(self):
        text, ok = QInputDialog.getText(self, 'Neuer Typ', 'Aktivitätstyp:')
        if ok and text:
            self.type_list.addItem(text)
            if 'type_colors' not in self.config:
                self.config['type_colors'] = {}
            if text not in self.config['type_colors']:
                self.config['type_colors'][text] = "#4682B4"  # Default color
    
    def remove_type(self):
        if self.type_list.currentItem():
            type_name = self.type_list.currentItem().text()
            if type_name in self.config.get('type_colors', {}):
                del self.config['type_colors'][type_name]
            self.type_list.takeItem(self.type_list.currentRow())
    
    def choose_color(self):
        if self.type_list.currentItem():
            type_name = self.type_list.currentItem().text()
            current_color = QColor(self.config['type_colors'].get(type_name, "#FFFFFF"))
            color = QColorDialog.getColor(current_color, self)
            if color.isValid():
                self.config['type_colors'][type_name] = color.name()
                self.update_color_button()
    
    def update_color_button(self):
        self.color_btn.setEnabled(self.type_list.currentItem() is not None)
        if self.type_list.currentItem():
            type_name = self.type_list.currentItem().text()
            color = self.config['type_colors'].get(type_name, "#FFFFFF")
            # Schrift schwarz oder weiß, je nachdem was auf der Farbe lesbar ist
            text = "#000000" if QColor(color).lightness() > 140 else "#FFFFFF"
            self.color_btn.setStyleSheet(f"background-color: {color}; color: {text};")
            self.color_btn.setText(f"{type_name}: Farbe ändern …")
    
    def get_types(self):
        return [self.type_list.item(i).text() for i in range(self.type_list.count())]

class WorkHoursDialog(QDialog):
    """Arbeitszeiten pro Wochentag festlegen."""

    DAY_NAMES = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

    def __init__(self, config, parent=None):
        super().__init__(parent)
        from timeline_only import WEEKDAYS, work_hours
        self.weekdays = WEEKDAYS
        self.setWindowTitle("Arbeitszeiten")
        layout = QVBoxLayout(self)

        hint = QLabel("Die Arbeitszeit wird in der Timeline hervorgehoben. "
                      "Freie Tage sind komplett abgedunkelt.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        grid = QGridLayout()
        grid.addWidget(QLabel("<b>Tag</b>"), 0, 0)
        grid.addWidget(QLabel("<b>von</b>"), 0, 1)
        grid.addWidget(QLabel("<b>bis</b>"), 0, 2)
        grid.addWidget(QLabel("<b>Stunden</b>"), 0, 3)
        self.rows = []
        for i, name in enumerate(self.DAY_NAMES):
            hours = work_hours(config, i)
            active = QCheckBox(name)
            active.setChecked(hours is not None)
            start, end = hours or (8 * 60, 17 * 60)
            t_from = QTimeEdit(QTime(start // 60, start % 60))
            t_to = QTimeEdit(QTime(end // 60, end % 60))
            for t in (t_from, t_to):
                t.setDisplayFormat("HH:mm")
            t_from.setAccessibleName(f"{name} von")
            t_to.setAccessibleName(f"{name} bis")
            total = QLabel()
            for w in (active, t_from, t_to):
                (w.toggled if w is active else w.timeChanged).connect(self.update_totals)
            grid.addWidget(active, i + 1, 0)
            grid.addWidget(t_from, i + 1, 1)
            grid.addWidget(t_to, i + 1, 2)
            grid.addWidget(total, i + 1, 3)
            self.rows.append((active, t_from, t_to, total))
        layout.addLayout(grid)

        self.week_total = QLabel()
        layout.addWidget(self.week_total)

        copy_btn = QPushButton("Montag auf alle Arbeitstage übertragen")
        copy_btn.clicked.connect(self.copy_monday)
        layout.addWidget(copy_btn)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.ok_button = buttons.button(QDialogButtonBox.Ok)
        self.update_totals()

    def copy_monday(self):
        _, mo_from, mo_to, _ = self.rows[0]
        for active, t_from, t_to, _ in self.rows[1:]:
            if active.isChecked():
                t_from.setTime(mo_from.time())
                t_to.setTime(mo_to.time())

    def update_totals(self):
        week, errors = 0, 0
        for active, t_from, t_to, total in self.rows:
            t_from.setEnabled(active.isChecked())
            t_to.setEnabled(active.isChecked())
            if active.isChecked() and t_from.time() >= t_to.time():
                # Fehler direkt neben dem Tag zeigen, nicht stumm als "frei" speichern
                errors += 1
                total.setText("⚠ Ende vor Beginn")
                continue
            minutes = t_from.time().secsTo(t_to.time()) // 60 if active.isChecked() else 0
            week += minutes
            total.setText(f"{minutes // 60}:{minutes % 60:02d} h" if minutes else "frei")
        self.week_total.setText(f"Pro Woche: <b>{week // 60}:{week % 60:02d} h</b>")
        if hasattr(self, "ok_button"):
            self.ok_button.setEnabled(errors == 0)

    def get_work_days(self):
        result = {}
        for key, (active, t_from, t_to, _) in zip(self.weekdays, self.rows):
            if active.isChecked() and t_from.time() < t_to.time():
                result[key] = f"{t_from.time().toString('HH:mm')}-{t_to.time().toString('HH:mm')}"
            else:
                result[key] = ""
        return result


class AiSettingsDialog(QDialog):
    """Einstellungen für die KI-Vorschläge (Anthropic-API)."""

    def __init__(self, config, spent_usd=0.0, parent=None):
        super().__init__(parent)
        import ai_classifier as ai  # erst hier, damit der Dialog auch ohne Paket aufgeht
        self.ai = ai
        self.config = config
        self.setWindowTitle("KI-Vorschläge")
        self.setMinimumWidth(540)
        layout = QVBoxLayout(self)

        info = QLabel(
            "Zeitzeuge schickt die Einträge eines Tages an Claude von Anthropic. Zurück kommen "
            "Tätigkeiten mit Kunde, Kategorie und einem Satz fürs Ticket. Sie stehen in der "
            "Timeline in der Zeile „KI“ und in der Tagesliste unter „KI-Vorschläge“.\n\n"
            "Gesendet wird nur, wenn du es anstößt (F6), und nur, wenn sich der Tag geändert hat. "
            "Ein Tag kostet meist wenige Cent.")
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        self.key_edit = QLineEdit(ai.api_key())
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("sk-ant-…")
        if ai.key_from_env():
            self.key_edit.setEnabled(False)
            self.key_edit.setToolTip("Kommt aus der Umgebungsvariable ANTHROPIC_API_KEY")
        form.addRow("API-Schlüssel:", self.key_edit)
        key_hint = QLabel("Liegt nur auf diesem PC unter %LOCALAPPDATA%\\Zeitzeuge, "
                          "nicht im Datenordner.")
        key_hint.setObjectName("hint")
        key_hint.setWordWrap(True)
        form.addRow("", key_hint)

        self.model_combo = QComboBox()
        for mid, name, price_in, price_out in ai.MODELS:
            self.model_combo.addItem(name, mid)
        self.model_combo.setCurrentIndex(
            max(0, self.model_combo.findData(config.get("ai_model", ai.DEFAULT_MODEL))))
        form.addRow("Modell:", self.model_combo)

        self.titles_check = QCheckBox("Fenstertitel mitsenden (genauere Vorschläge)")
        self.titles_check.setChecked(config.get("ai_send_window_titles", True))
        form.addRow("", self.titles_check)
        self.auto_check = QCheckBox("Vergangene Tage beim Anzeigen automatisch einordnen")
        self.auto_check.setChecked(config.get("ai_auto", False))
        form.addRow("", self.auto_check)

        self.categories_edit = QPlainTextEdit("\n".join(config.get("ai_categories")
                                                       or ai.DEFAULT_CATEGORIES))
        self.categories_edit.setAccessibleName("Kategorien, eine pro Zeile")
        self.categories_edit.setMaximumHeight(150)
        form.addRow("Kategorien\n(eine pro Zeile):", self.categories_edit)
        layout.addLayout(form)

        spent = QLabel(f"Bisher ausgegeben: ca. {spent_usd:.2f} $".replace(".", ","))
        spent.setObjectName("hint")
        layout.addWidget(spent)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def apply(self):
        """Eingaben in die Config übernehmen und den Schlüssel lokal speichern."""
        if not self.ai.key_from_env():
            self.ai.save_api_key(self.key_edit.text().strip())
        self.config["ai_model"] = self.model_combo.currentData()
        self.config["ai_send_window_titles"] = self.titles_check.isChecked()
        self.config["ai_auto"] = self.auto_check.isChecked()
        cats = [c.strip() for c in self.categories_edit.toPlainText().splitlines() if c.strip()]
        self.config["ai_categories"] = list(dict.fromkeys(cats)) or list(self.ai.DEFAULT_CATEGORIES)


def _lines(edit):
    return [line.strip() for line in edit.toPlainText().splitlines() if line.strip()]


class TrackingFilterDialog(QDialog):
    """Fenster-Filter fürs Aktivitätsprotokoll: Sperrliste (zwei Stufen) und Erlaubt-Liste."""

    LISTS = [  # Config-Schlüssel, Beschriftung, Name für Screenreader
        ("tracking_ignore", "Titel aus&blenden:", "Titel ausblenden, ein Eintrag pro Zeile"),
        ("tracking_skip", "Gar nicht auf&zeichnen:", "Gar nicht aufzeichnen, ein Eintrag pro Zeile"),
        ("tracking_allow", "Er&laubt (Whitelist):", "Erlaubte Fenster, ein Eintrag pro Zeile"),
    ]

    def __init__(self, config, activity_dir=None, parent=None):
        super().__init__(parent)
        import activity_tracker
        self.at = activity_tracker
        self.config = config
        self.setWindowTitle("Fenster-Filter")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)

        hint = QLabel("Ein Eintrag pro Zeile. Er passt auf den Programmnamen (z. B. chrome.exe "
                      "oder chrome) oder auf einen Teil des Fenstertitels. Groß und klein ist egal. "
                      "Mit „re:“ davor ist der Eintrag ein regulärer Ausdruck.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        mode_box = QGroupBox("Was soll aufgezeichnet werden?")
        mode_layout = QVBoxLayout(mode_box)
        self.black_radio = QRadioButton("&Alles, außer der Sperrliste (Blacklist)")
        self.white_radio = QRadioButton("Nur &Erlaubtes (Whitelist)")
        self.mode_group = QButtonGroup(self)
        for radio in (self.black_radio, self.white_radio):
            self.mode_group.addButton(radio)
            mode_layout.addWidget(radio)
        (self.white_radio if config.get("tracking_mode") == "whitelist"
         else self.black_radio).setChecked(True)
        layout.addWidget(mode_box)

        form = QFormLayout()
        self.edits, self.error_labels = {}, {}
        for key, label, name in self.LISTS:
            edit = QPlainTextEdit("\n".join(config.get(key, [])))
            edit.setAccessibleName(name)
            edit.setMaximumHeight(90)
            edit.setTabChangesFocus(True)
            edit.textChanged.connect(self.validate)
            error = QLabel()
            error.setWordWrap(True)
            error.setVisible(False)
            form.addRow(label, edit)
            form.addRow("", error)
            self.edits[key], self.error_labels[key] = edit, error
        stage_hint = QLabel("„Titel ausblenden“: Die Zeit zählt weiter, der Titel heißt „(ausgeblendet)“. "
                            "„Gar nicht aufzeichnen“: Die Zeit bleibt leer, z. B. für private Programme. "
                            "Die Sperrliste gilt auch im Whitelist-Modus.")
        stage_hint.setObjectName("hint")
        stage_hint.setWordWrap(True)
        form.addRow("", stage_hint)
        self.other_combo = QComboBox()
        self.other_combo.addItem("als „(andere)“ zählen, Titel nicht speichern", "mask")
        self.other_combo.addItem("gar nicht aufzeichnen", "skip")
        self.other_combo.setCurrentIndex(
            max(0, self.other_combo.findData(config.get("tracking_whitelist_other", "mask"))))
        form.addRow("Andere &Fenster:", self.other_combo)
        self.empty_hint = QLabel("Die Erlaubt-Liste ist leer. Dann wird kein Fenster mit Titel "
                                 "aufgezeichnet.")
        self.empty_hint.setObjectName("hint")
        self.empty_hint.setWordWrap(True)
        form.addRow("", self.empty_hint)
        layout.addLayout(form)

        # Häufige Programme der letzten 7 Tage zum schnellen Übernehmen
        top_box = QGroupBox("Häufige Programme der letzten 7 Tage")
        top_layout = QVBoxLayout(top_box)
        self.top_list = QListWidget()
        self.top_list.setAccessibleName("Häufige Programme der letzten 7 Tage")
        self.top_list.setMaximumHeight(120)
        for app, seconds in (activity_tracker.top_apps(activity_dir) if activity_dir else []):
            minutes = int(seconds // 60)
            item = QListWidgetItem(f"{app}  –  {minutes // 60}:{minutes % 60:02d} h")
            item.setData(Qt.UserRole, app)
            self.top_list.addItem(item)
        if not self.top_list.count():
            self.top_list.addItem("Noch nichts aufgezeichnet")
            self.top_list.setEnabled(False)
        top_layout.addWidget(self.top_list)
        buttons_row = QHBoxLayout()
        self.add_buttons = []
        for text, key in [("&Titel ausblenden", "tracking_ignore"),
                          ("&Nicht aufzeichnen", "tracking_skip"), ("E&rlauben", "tracking_allow")]:
            btn = QPushButton(text)
            btn.setToolTip("Gewähltes Programm in diese Liste übernehmen")
            btn.clicked.connect(lambda _=False, k=key: self.add_selected(k))
            btn.setEnabled(False)
            buttons_row.addWidget(btn)
            self.add_buttons.append(btn)
        self.top_list.currentItemChanged.connect(self.update_add_buttons)
        top_layout.addLayout(buttons_row)
        layout.addWidget(top_box)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.ok_button = buttons.button(QDialogButtonBox.Ok)
        self.white_radio.toggled.connect(self.validate)
        self.validate()

    def update_add_buttons(self, item=None, _old=None):
        for btn in self.add_buttons:
            btn.setEnabled(item is not None and bool(item.data(Qt.UserRole)))

    def add_selected(self, key):
        item = self.top_list.currentItem()
        app = item.data(Qt.UserRole) if item else None
        if not app:
            return
        edit = self.edits[key]
        if app.lower() not in (line.lower() for line in _lines(edit)):
            edit.setPlainText("\n".join(_lines(edit) + [app]))

    def errors(self):
        """{Schlüssel: [(Zeile, Eintrag, Meldung)]} der ungültigen Einträge."""
        result = {}
        for key, edit in self.edits.items():
            _, errs = self.at.compile_list(edit.toPlainText().splitlines())
            if errs:
                result[key] = errs
        return result

    def validate(self, *_):
        """Fehler neben dem Feld zeigen und OK sperren, solange es welche gibt."""
        whitelist = self.white_radio.isChecked()
        self.edits["tracking_allow"].setEnabled(whitelist)
        self.other_combo.setEnabled(whitelist)
        self.empty_hint.setVisible(whitelist and not _lines(self.edits["tracking_allow"]))
        errors = self.errors()
        for key, label in self.error_labels.items():
            errs = errors.get(key, [])
            label.setText("\n".join(f"⚠ Zeile {no}: {msg}" for no, _item, msg in errs))
            label.setVisible(bool(errs))
        self.ok_button.setEnabled(not errors)
        return not errors

    def apply(self):
        """Eingaben in die Config übernehmen."""
        for key, edit in self.edits.items():
            self.config[key] = list(dict.fromkeys(_lines(edit)))
        self.config["tracking_mode"] = "whitelist" if self.white_radio.isChecked() else "blacklist"
        self.config["tracking_whitelist_other"] = self.other_combo.currentData()


class RulesDialog(QDialog):
    """Regeln für die Klassifizierung ohne KI. Reihenfolge = Priorität."""

    COLUMNS = ["An", "Name", "Feld", "Muster", "Kategorie", "Kunde"]

    def __init__(self, config, parent=None):
        super().__init__(parent)
        import rules
        self.rules_mod = rules
        self.config = config
        self.rules = [dict(r) for r in (config.get("rules") or []) if isinstance(r, dict)]
        self._loading = True
        self.setWindowTitle("Regeln (ohne KI)")
        self.setMinimumWidth(720)
        layout = QVBoxLayout(self)

        hint = QLabel("Die Regeln ordnen Verbindungen, Telefonate und Fenster einer Kategorie und "
                      "einem Kunden zu. Die erste passende Regel gewinnt, Wichtiges steht also oben. "
                      "Verbindungen und Telefonate gehen immer vor PC-Fenstern.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setAccessibleName("Regeln, oberste zuerst")
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setMinimumHeight(220)
        self.table.currentCellChanged.connect(lambda row, *_: self.load_form(row))
        self.table.itemChanged.connect(self.on_item_changed)
        layout.addWidget(self.table)

        self.table_error = QLabel()
        self.table_error.setWordWrap(True)
        self.table_error.setVisible(False)
        layout.addWidget(self.table_error)

        row = QHBoxLayout()
        self.add_btn = QPushButton("&Hinzufügen")
        self.remove_btn = QPushButton("&Entfernen")
        self.up_btn = QPushButton("Nach &oben")
        self.down_btn = QPushButton("Nach &unten")
        self.reset_btn = QPushButton("&Standardregeln wiederherstellen …")
        for btn, slot in [(self.add_btn, self.add_rule), (self.remove_btn, self.remove_rule),
                          (self.up_btn, lambda: self.move_rule(-1)), (self.down_btn, lambda: self.move_rule(1)),
                          (self.reset_btn, self.reset_rules)]:
            btn.clicked.connect(slot)
            row.addWidget(btn)
        row.insertStretch(4)
        layout.addLayout(row)

        self.form_box = QGroupBox("Ausgewählte Regel")
        form = QFormLayout(self.form_box)
        self.enabled_check = QCheckBox("Regel &aktiv")
        form.addRow("", self.enabled_check)
        self.name_edit = QLineEdit()
        form.addRow("&Name:", self.name_edit)
        self.field_combo = QComboBox()
        for key, label in rules.FIELDS.items():
            self.field_combo.addItem(label, key)
        form.addRow("&Feld:", self.field_combo)
        self.match_edit = QLineEdit()
        self.match_edit.setPlaceholderText("z. B. outlook  oder  re:^Ticket (\\d+)")
        form.addRow("&Muster:", self.match_edit)
        self.match_error = QLabel()
        self.match_error.setWordWrap(True)
        self.match_error.setVisible(False)
        form.addRow("", self.match_error)
        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        self.category_combo.addItems(rules.categories(config))
        self.category_combo.lineEdit().setAccessibleName("Kategorie")
        form.addRow("&Kategorie:", self.category_combo)
        self.customer_edit = QLineEdit()
        self.customer_edit.setPlaceholderText("leer = Kunde vom Eintrag")
        form.addRow("Kun&de:", self.customer_edit)
        customer_hint = QLabel("Leer: Kunde vom Eintrag (bei Telefonaten der Anrufer). "
                               "{1} setzt die erste Klammer aus dem regulären Ausdruck ein, "
                               "z. B. den Kunden aus dem Fenstertitel.")
        customer_hint.setObjectName("hint")
        customer_hint.setWordWrap(True)
        form.addRow("", customer_hint)
        layout.addWidget(self.form_box)

        self.enabled_check.toggled.connect(self.store_form)
        self.name_edit.textEdited.connect(self.store_form)
        self.field_combo.currentIndexChanged.connect(self.store_form)
        self.match_edit.textEdited.connect(self.store_form)
        self.category_combo.currentTextChanged.connect(self.store_form)
        self.customer_edit.textEdited.connect(self.store_form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.ok_button = buttons.button(QDialogButtonBox.Ok)

        self._loading = False
        self.fill_table(0)

    # ----------------------------------------------------------- Tabelle

    def _row_texts(self, rule):
        return ["", rule.get("name", ""), self.rules_mod.FIELDS.get(rule.get("field", "any"), "?"),
                rule.get("match", ""), rule.get("category", ""),
                rule.get("customer", "") or "(vom Eintrag)"]

    def fill_table(self, select=-1):
        self._loading = True
        self.table.setRowCount(len(self.rules))
        for r, rule in enumerate(self.rules):
            self._set_row(r, rule)
        self._loading = False
        if 0 <= select < len(self.rules):
            self.table.setCurrentCell(select, 1)
        self.load_form(self.table.currentRow())

    def _set_row(self, r, rule):
        was, self._loading = self._loading, True
        for c, text in enumerate(self._row_texts(rule)):
            item = self.table.item(r, c)
            if item is None:
                item = QTableWidgetItem()
                self.table.setItem(r, c, item)
            item.setText(text)
            if c == 0:
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if rule.get("enabled", True) else Qt.Unchecked)
                item.setToolTip("Regel an oder aus")
        self._loading = was

    def on_item_changed(self, item):
        if self._loading or item.column() != 0 or item.row() >= len(self.rules):
            return
        self.rules[item.row()]["enabled"] = item.checkState() == Qt.Checked
        if item.row() == self.table.currentRow():
            self.load_form(item.row())
        self.validate()

    # ----------------------------------------------------------- Formular

    def load_form(self, row):
        has = 0 <= row < len(self.rules)
        rule = self.rules[row] if has else {}
        self._loading = True
        self.form_box.setEnabled(has)
        self.enabled_check.setChecked(rule.get("enabled", True))
        self.name_edit.setText(rule.get("name", ""))
        self.field_combo.setCurrentIndex(max(0, self.field_combo.findData(rule.get("field", "any"))))
        self.match_edit.setText(rule.get("match", ""))
        self.category_combo.setCurrentText(rule.get("category", ""))
        self.customer_edit.setText(rule.get("customer", ""))
        self._loading = False
        self.remove_btn.setEnabled(has)
        self.up_btn.setEnabled(has and row > 0)
        self.down_btn.setEnabled(has and row < len(self.rules) - 1)
        self.validate()

    def store_form(self, *_):
        row = self.table.currentRow()
        if self._loading or not 0 <= row < len(self.rules):
            return
        self.rules[row].update({
            "enabled": self.enabled_check.isChecked(),
            "name": self.name_edit.text().strip(),
            "field": self.field_combo.currentData(),
            "match": self.match_edit.text().strip(),
            "category": self.category_combo.currentText().strip(),
            "customer": self.customer_edit.text().strip(),
        })
        self._set_row(row, self.rules[row])
        self.validate()

    def validate(self):
        """Fehler neben dem Feld und unter der Tabelle als Text zeigen, OK sperren."""
        errors = self.rules_mod.rule_errors(self.rules)
        row = self.table.currentRow()
        own = [msg for i, msg in errors if i == row]
        self.match_error.setText(f"⚠ {own[0]}" if own else "")
        self.match_error.setVisible(bool(own))
        self.table_error.setText("\n".join(
            f"⚠ Regel {i + 1} „{self.rules[i].get('name') or 'ohne Namen'}“: {msg}"
            for i, msg in errors[:3]))
        self.table_error.setVisible(bool(errors))
        self.ok_button.setEnabled(not errors)
        return not errors

    # ----------------------------------------------------------- Knöpfe

    def add_rule(self):
        self.rules.append({"name": "Neue Regel", "field": "title", "match": "",
                           "category": self.rules_mod.categories(self.config)[0],
                           "customer": "", "enabled": True})
        self.fill_table(len(self.rules) - 1)
        self.match_edit.setFocus()

    def remove_rule(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.rules):
            del self.rules[row]
            self.fill_table(min(row, len(self.rules) - 1))

    def move_rule(self, step):
        row = self.table.currentRow()
        new = row + step
        if 0 <= row < len(self.rules) and 0 <= new < len(self.rules):
            self.rules[row], self.rules[new] = self.rules[new], self.rules[row]
            self.fill_table(new)

    def reset_rules(self):
        answer = QMessageBox.question(
            self, "Standardregeln wiederherstellen",
            "Alle Regeln durch die Standardregeln ersetzen? Eigene Regeln gehen dabei verloren.")
        if answer == QMessageBox.Yes:
            self.rules = self.rules_mod.default_rules()
            self.fill_table(0)

    def apply(self):
        """Regeln in die Config übernehmen."""
        self.config["rules"] = [dict(r) for r in self.rules]
