import os

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import *

DEBUG = False

# In settings_dialogs.py
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
        # Lade gespeicherte Pfade oder Standardpfade
        saved_paths = self.config.get(f'{self.config_key}_paths', self.default_paths)
        self.path_list.addItems(saved_paths)
        path_layout.addWidget(self.path_list)
        
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Hinzufügen")
        add_btn.clicked.connect(self.add_path)
        remove_btn = QPushButton("Entfernen")
        remove_btn.clicked.connect(self.remove_path)
        
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
        text, ok = QInputDialog.getText(self, 'Neuer Pfad', 'Logdatei-Pfad:')
        if ok and text:
            self.path_list.addItem(text)
    
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
        self.type_list.addItems(self.config.get('activity_types', []))
        type_layout.addWidget(self.type_list)
        
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Hinzufügen")
        add_btn.clicked.connect(self.add_type)
        remove_btn = QPushButton("Entfernen")
        remove_btn.clicked.connect(self.remove_type)
        
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(remove_btn)
        type_layout.addLayout(btn_layout)
        type_group.setLayout(type_layout)
        layout.addWidget(type_group)
        
        # Farbauswahl
        color_group = QGroupBox("Farbzuordnung")
        color_layout = QFormLayout()
        
        self.color_btn = QPushButton("Farbe wählen")
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
        if self.type_list.currentItem():
            type_name = self.type_list.currentItem().text()
            color = self.config['type_colors'].get(type_name, "#FFFFFF")
            self.color_btn.setStyleSheet(f"background-color: {color};")
            self.color_btn.setText(type_name)
    
    def get_types(self):
        return [self.type_list.item(i).text() for i in range(self.type_list.count())]

class TapiSettingsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Telefonie-Einstellungen")
        self.setMinimumWidth(400)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        
        # Aktivierung
        enable_group = QGroupBox("Telefonie-Integration")
        enable_layout = QVBoxLayout()
        self.enable_check = QCheckBox("Telefonie-Integration aktivieren")
        self.enable_check.setChecked(self.config.get('tapi_enabled', True))
        enable_layout.addWidget(self.enable_check)
        enable_group.setLayout(enable_layout)
        layout.addWidget(enable_group)
        
        # Automatische Übernahme
        auto_add_group = QGroupBox("Anrufverarbeitung")
        auto_add_layout = QVBoxLayout()  # Diese Variable wurde hinzugefügt
        
        self.auto_add_check = QCheckBox("Anrufe automatisch als Aktivitäten speichern")
        self.auto_add_check.setChecked(self.config.get('tapi_auto_add', False))
        auto_add_layout.addWidget(self.auto_add_check)
        
        self.ignore_missed = QCheckBox("Verpasste Anrufe ignorieren (kürzer als Mindestdauer)")
        self.ignore_missed.setChecked(self.config.get('tapi_ignore_missed', True))
        auto_add_layout.addWidget(self.ignore_missed)
        
        min_duration_layout = QHBoxLayout()
        min_duration_layout.addWidget(QLabel("Minimale Anrufdauer (Sekunden):"))
        self.min_duration = QSpinBox()
        self.min_duration.setRange(0, 300)
        self.min_duration.setValue(self.config.get('tapi_min_duration', 10))
        min_duration_layout.addWidget(self.min_duration)
        auto_add_layout.addLayout(min_duration_layout)
        
        auto_add_group.setLayout(auto_add_layout)
        layout.addWidget(auto_add_group)

        error_group = QGroupBox("Fehlerbehandlung")
        error_layout = QFormLayout()

        self.max_errors = QSpinBox()
        self.max_errors.setRange(1, 100)
        self.max_errors.setValue(self.config.get('tapi_max_errors', 5))
        error_layout.addRow("Maximale Fehler vor Deaktivierung:", self.max_errors)

        error_group.setLayout(error_layout)
        layout.addWidget(error_group)
        
        # Polling-Einstellungen
        polling_group = QGroupBox("Abfrageeinstellungen")
        polling_layout = QFormLayout()
        
        self.poll_interval = QSpinBox()
        self.poll_interval.setRange(1, 60)
        self.poll_interval.setValue(self.config.get('tapi_poll_interval', 5))
        self.poll_interval.setSuffix(" Sekunden")
        polling_layout.addRow("Abfrageintervall:", self.poll_interval)
        
        polling_group.setLayout(polling_layout)
        layout.addWidget(polling_group)
        
        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.setLayout(layout)

    def get_settings(self):
        return {
            'tapi_enabled': self.enable_check.isChecked(),
            'tapi_auto_add': self.auto_add_check.isChecked(),
            'tapi_ignore_missed': self.ignore_missed.isChecked(),
            'tapi_min_duration': self.min_duration.value(),
            'tapi_poll_interval': self.poll_interval.value()
        }