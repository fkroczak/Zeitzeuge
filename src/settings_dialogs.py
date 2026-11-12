import os

from PySide6.QtCore import QSize, QTime, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QColorDialog,
                               QComboBox, QDialog, QDialogButtonBox, QFrame,
                               QFileDialog, QFormLayout, QGridLayout, QGroupBox,
                               QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
                               QPushButton, QRadioButton, QScrollArea, QSpinBox, QTableWidget,
                               QTableWidgetItem, QTimeEdit, QToolButton, QVBoxLayout, QWidget)

from card_dialog import modernize
from theme import prose, SPACE_3XL, SPACE_M, SPACE_S, SPACE_XL
def scrolling_body(dialog):
    """Inhalt eines hohen Dialogs in einen Scrollbereich, die Knöpfe bleiben unten stehen.
    So bleibt er auch auf kleinen Bildschirmen bedienbar (Full HD mit 200 % = 960 × 540).
    Gibt (Layout für den Inhalt, äußeres Layout für die Knöpfe) zurück."""
    outer = QVBoxLayout(dialog)
    body = QWidget()
    layout = QVBoxLayout(body)
    layout.setContentsMargins(0, 0, SPACE_S, 0)  # rechts Platz für den Scrollbalken
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setWidget(body)
    outer.addWidget(scroll, 1)
    return layout, outer


def fit_screen(widget, width, height):
    """Startgröße, höchstens so groß wie der verfügbare Bildschirm (abzüglich Rand)."""
    screen = widget.screen() or QGuiApplication.primaryScreen()
    if screen is None:
        return QSize(width, height)
    area = screen.availableGeometry()
    return QSize(min(width, area.width() - SPACE_XL), min(height, area.height() - SPACE_3XL))


class ConnectionSettingsDialog(QDialog):
    def __init__(self, config, config_key, default_paths, title, parent=None,
                 enabled_text=None, folders=False, hint=None, paths_key=None,
                 timezone=True, files=True, paths=True, path_title="Logdatei-Pfade",
                 enabled_key=None, checks=(), utc_auto_key=None):
        super().__init__(parent)
        self.utc_auto_key = utc_auto_key  # Schalter „von UTC automatisch umrechnen“ (TeamViewer)
        self.utc_auto_box = None
        self.checks = list(checks)        # weitere Schalter: [(Config-Schlüssel, Text, Standard)]
        self.check_boxes = {}
        self.config = config
        self.config_key = config_key
        self.default_paths = default_paths
        self.enabled_text = enabled_text  # Schalter "auslesen ja/nein"
        self.enabled_key = enabled_key or f"{config_key}_enabled"
        self.folders = folders            # auch ganze Ordner als Pfad erlauben
        self.files = files                # einzelne Dateien erlauben
        self.show_paths = paths           # ohne Pfade: nur Schalter und Hinweis
        self.paths_key = paths_key or f"{config_key}_paths"
        self.path_title = path_title
        self.show_timezone = timezone
        self.hint = hint
        self.enabled_box = None
        self.path_list = None
        self.tz_spinbox = None
        self.setWindowTitle(title)
        self.setMinimumWidth(580)  # lange Pfade lesbar
        self.init_ui()
        from card_dialog import modernize  # Rahmen wie „Tätigkeit nachtragen“
        modernize(self, title, "Ob und woher Zeitzeuge diese Quelle liest.", "plug", intro=False, scroll=True)
    
    def init_ui(self):
        layout = QVBoxLayout()

        if self.enabled_text:
            self.enabled_box = QCheckBox(self.enabled_text)
            self.enabled_box.setChecked(bool(self.config.get(self.enabled_key, True)))
            layout.addWidget(self.enabled_box)
        for key, text, default in self.checks:
            box = QCheckBox(text)
            box.setChecked(bool(self.config.get(key, default)))
            self.check_boxes[key] = box
            layout.addWidget(box)
        if self.hint:
            hint = QLabel(self.hint)
            hint.setWordWrap(True)
            prose(hint)
            layout.addWidget(hint)

        if self.show_paths:
            self._add_paths(layout)
        if self.show_timezone:
            self._add_timezone(layout)

        # Button Box
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def _add_paths(self, layout):
        path_group = QGroupBox(self.path_title)
        path_layout = QVBoxLayout()
        
        self.path_list = QListWidget()
        self.path_list.setAccessibleName(self.path_title)
        # Lade gespeicherte Pfade oder Standardpfade
        saved_paths = self.config.get(self.paths_key, self.default_paths)
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
        
        if self.files:
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

    def _add_timezone(self, layout):
        # Zeitzonenkorrektur
        tz_group = QGroupBox("Zeitzoneneinstellungen")
        tz_layout = QFormLayout()
        
        # Lade gespeicherte Korrektur oder Standardwert
        saved_tz_correction = self.config.get(f'{self.config_key}_timezone_correction', self.config.get('timezone_correction', 2))
        
        self.tz_spinbox = QSpinBox()
        self.tz_spinbox.setRange(-12, 14)
        self.tz_spinbox.setValue(saved_tz_correction)
        
        if self.utc_auto_key:
            auto = self.config.get(self.utc_auto_key)
            self.utc_auto_box = QCheckBox("Sommer- und Winterzeit automatisch (Log in UTC)")
            self.utc_auto_box.setChecked(saved_tz_correction in (1, 2) if auto is None else bool(auto))
            self.tz_spinbox.setEnabled(not self.utc_auto_box.isChecked())
            self.utc_auto_box.toggled.connect(lambda on: self.tz_spinbox.setEnabled(not on))
            tz_layout.addRow(self.utc_auto_box)
        tz_layout.addRow("Zeitzonenkorrektur (Stunden):", self.tz_spinbox)
        tz_group.setLayout(tz_layout)
        layout.addWidget(tz_group)

    def get_paths(self):
        if self.path_list is None:
            return None
        return [self.path_list.item(i).text() for i in range(self.path_list.count())]

    def get_timezone_correction(self):
        return self.tz_spinbox.value() if self.tz_spinbox else None

    def values(self):
        """Geänderte Einstellungen (nur die Teile, die das Fenster zeigt)."""
        result = {}
        if self.path_list is not None:
            result[self.paths_key] = self.get_paths()
        if self.enabled_box:
            result[self.enabled_key] = self.enabled_box.isChecked()
        for key, box in self.check_boxes.items():
            result[key] = box.isChecked()
        if self.tz_spinbox:
            result[f"{self.config_key}_timezone_correction"] = self.get_timezone_correction()
        if self.utc_auto_box:
            result[self.utc_auto_key] = self.utc_auto_box.isChecked()
        return result
    
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
        from card_dialog import modernize
        modernize(self, "Aktivitätstypen", "Typen und ihre Farben in Timeline und Tagesliste.", "type",
                  intro=False)
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Typenliste: Farbpunkt je Typ, Doppelklick ändert die Farbe
        type_group = QGroupBox("Aktivitätstypen")
        type_layout = QVBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Typ suchen …")
        self.search.setAccessibleName("Typ suchen")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.filter_types)
        type_layout.addWidget(self.search)

        self.type_list = QListWidget()
        self.type_list.setObjectName("type_list")
        self.type_list.setAccessibleName("Aktivitätstypen")
        self.type_list.setIconSize(QSize(12, 12))
        for name in self.config.get('activity_types', []):
            self._add_item(name)
        self.type_list.itemDoubleClicked.connect(lambda _i: self.choose_color())
        self.setMinimumHeight(520)
        type_layout.addWidget(self.type_list)
        hint = QLabel("Doppelklick auf einen Typ ändert seine Farbe.")
        hint.setObjectName("hint")
        type_layout.addWidget(hint)
        
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("&Hinzufügen …")
        add_btn.clicked.connect(self.add_type)
        remove_btn = QPushButton("&Entfernen")
        remove_btn.clicked.connect(self.remove_type)
        remove_btn.setEnabled(False)
        self.type_list.currentItemChanged.connect(
            lambda item, _old: remove_btn.setEnabled(item is not None))
        
        btn_layout.addStretch(1)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(remove_btn)
        type_layout.addLayout(btn_layout)
        type_group.setLayout(type_layout)
        layout.addWidget(type_group)
        
        self.color_btn = QPushButton("&Farbe ändern …")
        self.color_btn.clicked.connect(self.choose_color)
        self.type_list.currentItemChanged.connect(self.update_color_button)
        btn_layout.insertWidget(0, self.color_btn)
        
        # Button Box
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.setLayout(layout)
        self.update_color_button()
    
    def _dot(self, name):
        color = QColor(self.config.get('type_colors', {}).get(name, "#4682B4"))
        pix = QPixmap(24, 24)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(2, 2, 20, 20)
        painter.end()
        return QIcon(pix)

    def _add_item(self, name):
        item = QListWidgetItem(self._dot(name), name)
        self.type_list.addItem(item)
        return item

    def filter_types(self, text):
        for i in range(self.type_list.count()):
            item = self.type_list.item(i)
            item.setHidden(text.lower() not in item.text().lower())

    def add_type(self):
        text, ok = QInputDialog.getText(self, 'Neuer Typ', 'Aktivitätstyp:')
        if ok and text:
            self._add_item(text)
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
        item = self.type_list.currentItem()
        self.color_btn.setEnabled(item is not None)
        if item:
            item.setIcon(self._dot(item.text()))
    
    def get_types(self):
        return [self.type_list.item(i).text() for i in range(self.type_list.count())]

class WorkHoursDialog(QDialog):
    """Arbeitszeiten und Pause pro Wochentag festlegen."""

    DAY_NAMES = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

    def __init__(self, config, parent=None):
        super().__init__(parent)
        from timeline_only import WEEKDAYS, work_break, work_hours
        self.weekdays = WEEKDAYS
        self.setWindowTitle("Arbeitszeiten")
        # Breite nach Inhalt: ohne Pausenspalten schmal, mit Pause wächst der Dialog (update_totals)
        self.setMinimumWidth(440)
        self._any_pause = None
        layout = QVBoxLayout(self)
        layout.setSpacing(SPACE_S)

        hint = QLabel("Die Arbeitszeit wird in der Timeline hervorgehoben, die Pause abgedunkelt. "
                      "Freie Tage sind komplett abgedunkelt. Gilt nur, wenn keine ITM-Personalzeit "
                      "da ist.")
        hint.setWordWrap(True)
        prose(hint)
        layout.addWidget(hint)

        grid = QGridLayout()
        grid.setHorizontalSpacing(SPACE_M)
        grid.setVerticalSpacing(SPACE_S)
        self.pause_heads = []  # „Pause von“, „bis“: nur sichtbar, wenn ein Tag eine Pause hat
        for col, text in enumerate(("Tag", "von", "bis", "Pause", "Pause von", "bis", "Stunden")):
            head = QLabel(f"<b>{text}</b>")
            grid.addWidget(head, 0, col)
            if col in (4, 5):
                self.pause_heads.append(head)
        self.rows = []
        for i, name in enumerate(self.DAY_NAMES):
            hours = work_hours(config, i)
            pause = work_break(config, i)
            active = QCheckBox(name)
            active.setChecked(hours is not None)
            start, end = hours or (8 * 60, 17 * 60)
            t_from = QTimeEdit(QTime(start // 60, start % 60))
            t_to = QTimeEdit(QTime(end // 60, end % 60))
            has_pause = QCheckBox()
            has_pause.setAccessibleName(f"{name} Pause")
            has_pause.setChecked(pause is not None)
            p_start, p_end = pause or (12 * 60, 12 * 60 + 30)
            p_from = QTimeEdit(QTime(p_start // 60, p_start % 60))
            p_to = QTimeEdit(QTime(p_end // 60, p_end % 60))
            for t in (t_from, t_to, p_from, p_to):
                t.setDisplayFormat("HH:mm")
                t.setMinimumWidth(72)
            t_from.setAccessibleName(f"{name} von")
            t_to.setAccessibleName(f"{name} bis")
            p_from.setAccessibleName(f"{name} Pause von")
            p_to.setAccessibleName(f"{name} Pause bis")
            total = QLabel()
            total.setMinimumWidth(110)
            for w in (active, has_pause):
                w.toggled.connect(self.update_totals)
            for w in (t_from, t_to, p_from, p_to):
                w.timeChanged.connect(self.update_totals)
            for w in (t_from, t_to, has_pause):  # freie Tage: Spalten bleiben stehen (Pause klappt ganz weg)
                policy = w.sizePolicy()
                policy.setRetainSizeWhenHidden(True)
                w.setSizePolicy(policy)
            for col, w in enumerate((active, t_from, t_to, has_pause, p_from, p_to, total)):
                grid.addWidget(w, i + 1, col)
            self.rows.append((active, t_from, t_to, total, has_pause, p_from, p_to))
        grid.setColumnStretch(6, 1)
        layout.addLayout(grid)

        self.week_total = QLabel()
        layout.addWidget(self.week_total)

        copy_btn = QToolButton()
        copy_btn.setObjectName("link")
        copy_btn.setText("Montag auf alle Arbeitstage übertragen")
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.clicked.connect(self.copy_monday)
        layout.addWidget(copy_btn, 0, Qt.AlignLeft)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.ok_button = buttons.button(QDialogButtonBox.Ok)
        from card_dialog import modernize
        modernize(self, "Arbeitszeiten", "In der Timeline hervorgehoben, Pause und freie Tage abgedunkelt. "
                  "Gilt nur ohne ITM-Personalzeit.", "work_time", intro=hint)
        self.update_totals()

    def copy_monday(self):
        _, mo_from, mo_to, _, mo_pause, mo_p_from, mo_p_to = self.rows[0]
        for active, t_from, t_to, _, has_pause, p_from, p_to in self.rows[1:]:
            if active.isChecked():
                t_from.setTime(mo_from.time())
                t_to.setTime(mo_to.time())
                has_pause.setChecked(mo_pause.isChecked())
                p_from.setTime(mo_p_from.time())
                p_to.setTime(mo_p_to.time())

    @staticmethod
    def _pause_minutes(t_from, t_to, p_from, p_to):
        """Minuten der Pause innerhalb der Arbeitszeit (None = Pause ungültig)."""
        if p_from.time() >= p_to.time():
            return None
        a = max(t_from.time(), p_from.time())
        b = min(t_to.time(), p_to.time())
        return a.secsTo(b) // 60 if a < b else 0

    def update_totals(self):
        any_pause = any(active.isChecked() and has_pause.isChecked()
                        for active, _f, _t, _total, has_pause, _pf, _pt in self.rows)
        for head in self.pause_heads:
            head.setVisible(any_pause)
        if any_pause != self._any_pause:
            changed = self._any_pause is not None
            self._any_pause = any_pause
            if changed:  # Spalten kamen dazu oder fielen weg: Größe nach dem neuen Layout
                QTimer.singleShot(0, lambda: self.isVisible() and self.resize(self.sizeHint()))
        week, errors = 0, 0
        for active, t_from, t_to, total, has_pause, p_from, p_to in self.rows:
            on = active.isChecked()
            t_from.setVisible(on)
            t_to.setVisible(on)
            has_pause.setVisible(on)
            p_from.setVisible(on and has_pause.isChecked())
            p_to.setVisible(on and has_pause.isChecked())
            if not on:
                total.setText("frei")
                continue
            if t_from.time() >= t_to.time():
                # Fehler direkt neben dem Tag zeigen, nicht stumm als "frei" speichern
                errors += 1
                total.setText("⚠ Ende vor Beginn")
                continue
            minutes = t_from.time().secsTo(t_to.time()) // 60
            if has_pause.isChecked():
                pause = self._pause_minutes(t_from, t_to, p_from, p_to)
                if pause is None:
                    errors += 1
                    total.setText("⚠ Pause: Ende vor Beginn")
                    continue
                minutes -= pause
            week += minutes
            total.setText(f"{minutes // 60}:{minutes % 60:02d} h")
        self.week_total.setText(f"Pro Woche: <b>{week // 60}:{week % 60:02d} h</b> (ohne Pausen)")
        if hasattr(self, "ok_button"):
            self.ok_button.setEnabled(errors == 0)

    def get_work_days(self):
        result = {}
        for key, (active, t_from, t_to, *_rest) in zip(self.weekdays, self.rows):
            if active.isChecked() and t_from.time() < t_to.time():
                result[key] = f"{t_from.time().toString('HH:mm')}-{t_to.time().toString('HH:mm')}"
            else:
                result[key] = ""
        return result

    def get_work_breaks(self):
        result = {}
        for key, (active, _f, _t, _total, has_pause, p_from, p_to) in zip(self.weekdays, self.rows):
            if active.isChecked() and has_pause.isChecked() and p_from.time() < p_to.time():
                result[key] = f"{p_from.time().toString('HH:mm')}-{p_to.time().toString('HH:mm')}"
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
            "Zeitzeuge schickt die Einträge eines Tages an Claude (Anthropic). Zurück kommen "
            "Tätigkeiten mit Kunde, Kategorie und einem Satz fürs Ticket: Zeile „KI“ in der "
            "Timeline, „KI-Vorschläge“ in der Tagesliste.\n\n"
            "Gesendet wird nur auf Wunsch (F6) und nur, wenn sich der Tag geändert hat. "
            "Meist wenige Cent pro Tag.")
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
        modernize(self, "KI-Vorschläge", "Claude ordnet einen Tag ein. Nur auf Wunsch (F6), wenige Cent pro Tag.",
                  "spark", scroll=True)
        self.resize(self.width(), 640)

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
        self.resize(fit_screen(self, 620, 820))  # Hinweistexte nicht abschneiden
        layout, outer = scrolling_body(self)

        hint = QLabel("Ein Eintrag pro Zeile. Er passt auf den Programmnamen (z. B. chrome.exe "
                      "oder chrome) oder auf einen Teil des Fenstertitels. Groß und klein ist egal. "
                      "Mit „re:“ davor ist der Eintrag ein regulärer Ausdruck.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        self.intro = hint
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
        outer.addWidget(buttons)
        self.ok_button = buttons.button(QDialogButtonBox.Ok)
        self.white_radio.toggled.connect(self.validate)
        self.validate()
        modernize(self, "Fenster-Filter", "Was Zeitzeuge am PC aufzeichnet. Ein Eintrag pro Zeile: Programm "
                  "oder Teil des Fenstertitels.", "filter", intro=self.intro)

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

    COLUMNS = ["An", "Name", "Feld", "Muster", "Kategorie", "Kunde", "7 Tage"]
    EXTRA = 2  # so viele „und“-Bedingungen je Regel

    def __init__(self, config, parent=None, sample=None):
        super().__init__(parent)
        import rules
        self.rules_mod = rules
        self.config = config
        # sample(): (Einträge, Fenster) der letzten 7 Tage für Treffer und Vorschau
        try:
            self.sample = sample() if sample else None
        except Exception:  # Vorschau ist Beiwerk, der Dialog muss trotzdem aufgehen
            self.sample = None
        self.counts = []
        self.rules = [dict(r) for r in (config.get("rules") or []) if isinstance(r, dict)]
        self._loading = True
        self.setWindowTitle("Zuordnung ohne KI (Regeln)")
        self.setMinimumWidth(720)
        self.resize(fit_screen(self, 900, 760))  # Knöpfe und Hinweise ganz zeigen
        layout, outer = scrolling_body(self)

        hint = QLabel("Feste Regeln ordnen Verbindungen, Telefonate und Fenster einer Kategorie und einem "
                      "Kunden zu, z. B. Outlook → „E-Mail / Kommunikation“. Ergebnis: Zeile „Zuordnung o. KI“. "
                      "Die erste passende Regel gilt, Wichtiges also nach oben. "
                      "Verbindungen und Telefonate gehen vor PC-Fenstern.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        self.intro = hint
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
        self.extra_fields, self.extra_matches = [], []
        for n in range(self.EXTRA):
            line = QHBoxLayout()
            combo = QComboBox()
            for key, label in rules.FIELDS.items():
                combo.addItem(label, key)
            combo.setAccessibleName(f"Feld der Bedingung {n + 2}")
            edit = QLineEdit()
            edit.setPlaceholderText("leer = keine weitere Bedingung")
            edit.setAccessibleName(f"Muster der Bedingung {n + 2}")
            line.addWidget(combo)
            line.addWidget(edit, 1)
            label = QLabel("&und:" if n == 0 else "und:")
            label.setBuddy(combo)
            form.addRow(label, line)
            self.extra_fields.append(combo)
            self.extra_matches.append(edit)
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
        customer_hint = QLabel("Leer: Kunde vom Eintrag oder aus einem Stichwort der Kundenliste "
                               "(bei Telefonaten nur aus der Kundenliste). {1} setzt die erste "
                               "Klammer aus dem regulären Ausdruck der ersten Bedingung ein, "
                               "z. B. den Kunden aus dem Fenstertitel.")
        customer_hint.setObjectName("hint")
        customer_hint.setWordWrap(True)
        form.addRow("", customer_hint)
        self.preview_label = QLabel()
        self.preview_label.setWordWrap(True)
        self.preview_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        form.addRow("", self.preview_label)
        layout.addWidget(self.form_box)

        self.enabled_check.toggled.connect(self.store_form)
        self.name_edit.textEdited.connect(self.store_form)
        self.field_combo.currentIndexChanged.connect(self.store_form)
        self.match_edit.textEdited.connect(self.store_form)
        self.category_combo.currentTextChanged.connect(self.store_form)
        self.customer_edit.textEdited.connect(self.store_form)
        for combo, edit in zip(self.extra_fields, self.extra_matches):
            combo.currentIndexChanged.connect(self.store_form)
            edit.textEdited.connect(self.store_form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)
        self.ok_button = buttons.button(QDialogButtonBox.Ok)

        self._loading = False
        self.fill_table(0)
        modernize(self, "Regeln ohne KI", "Programm oder Verbindung → Kategorie und Kunde. Die erste passende "
                  "Regel gilt, Wichtiges also nach oben.", "rules", intro=self.intro)

    # ----------------------------------------------------------- Tabelle

    def _row_texts(self, rule, count=None):
        match = rule.get("match", "")
        for c in rule.get("and") or []:
            match += f" · und {self.rules_mod.FIELDS.get(c.get('field', 'any'), '?')}: {c.get('match', '')}"
        hits = "" if count is None else (f"{count}×" if rule.get("enabled", True) else "aus")
        return ["", rule.get("name", ""), self.rules_mod.FIELDS.get(rule.get("field", "any"), "?"),
                match, rule.get("category", ""), rule.get("customer", "") or "(vom Eintrag)", hits]

    def _count(self):
        """Treffer je Regel in den letzten 7 Tagen (erste passende Regel zählt)."""
        if self.sample is None:
            self.counts = []
            return
        self.counts = self.rules_mod.hit_counts(self.rules, *self.sample)

    def fill_table(self, select=-1):
        self._count()
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
        count = self.counts[r] if r < len(self.counts) else None
        for c, text in enumerate(self._row_texts(rule, count)):
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
        self._count()
        for r, rule in enumerate(self.rules):
            self._set_row(r, rule)
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
        extra = [c for c in rule.get("and") or [] if isinstance(c, dict)]
        for n, (combo, edit) in enumerate(zip(self.extra_fields, self.extra_matches)):
            c = extra[n] if n < len(extra) else {"field": "title", "match": ""}
            combo.setCurrentIndex(max(0, combo.findData(c.get("field", "any"))))
            edit.setText(c.get("match", ""))
        self._loading = False
        self.update_preview()
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
        extra = [{"field": combo.currentData(), "match": edit.text().strip()}
                 for combo, edit in zip(self.extra_fields, self.extra_matches) if edit.text().strip()]
        if extra:
            self.rules[row]["and"] = extra
        else:
            self.rules[row].pop("and", None)
        self._count()
        for r, rule in enumerate(self.rules):  # eine Regel ändert auch die Treffer der anderen
            self._set_row(r, rule)
        self.validate()
        self.update_preview()

    def update_preview(self):
        """„Passt auf 14 Einträge der letzten 7 Tage, z. B. …“ für die gewählte Regel."""
        row = self.table.currentRow()
        if self.sample is None or not 0 <= row < len(self.rules):
            self.preview_label.setText("")
            return
        rule = self.rules[row]
        if self.rules_mod.rule_errors([rule]):
            self.preview_label.setText("")
            return
        count, examples = self.rules_mod.preview(rule, *self.sample)
        if not count:
            self.preview_label.setText("Passt auf keinen Eintrag der letzten 7 Tage.")
            return
        text = f"✓ Passt auf {count} Eintr{'äge' if count != 1 else 'ag'} der letzten 7 Tage"
        if examples:
            text += ", z. B. " + "; ".join(f"„{e[:60]}“" for e in examples)
        used = self.counts[row] if row < len(self.counts) else count
        if used < count:
            text += f". Davon greift sie bei {used}, sonst gewinnt eine Regel weiter oben."
        self.preview_label.setText(text)

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
