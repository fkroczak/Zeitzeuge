import os

from PyQt5.QtCore import QTime
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QCheckBox, QColorDialog, QDialog, QDialogButtonBox,
                             QFileDialog, QFormLayout, QGridLayout, QGroupBox,
                             QHBoxLayout, QInputDialog, QLabel, QListWidget,
                             QPushButton, QSpinBox, QTimeEdit, QVBoxLayout)

class ConnectionSettingsDialog(QDialog):
    def __init__(self, config, config_key, default_paths, title, parent=None):
        super().__init__(parent)
        self.config = config
        self.config_key = config_key
        self.default_paths = default_paths
        self.setWindowTitle(title)
        self.setMinimumWidth(400)
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
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
        btn_layout.addWidget(remove_btn)
        path_layout.addLayout(btn_layout)
        path_group.setLayout(path_layout)
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
