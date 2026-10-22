"""Aussehen: Fusion-Stil, deutsche Qt-Texte, Farben (Tokens) und Stylesheet.

Ein neues Design ändert nur die Werte in THEMES und ergänzt bei Bedarf STYLESHEET
($name wird durch den Wert des Tokens ersetzt, siehe apply_style in app_menus.py).
"""
from PySide6.QtCore import QLibraryInfo, QLocale, QSize, QTranslator
from PySide6.QtWidgets import QDialogButtonBox, QProxyStyle, QStyle, QStyleFactory


class AppStyle(QProxyStyle):
    """Fusion mit gut sichtbarem Knopf für ausgeblendete Werkzeugleisten-Befehle.

    Ist das Fenster schmal (z. B. Laptop mit 200 % Anzeige), rutschen Knöpfe wie
    "Einstellungen" in diesen Knopf. Standard sind nur 12 px ohne erkennbares Symbol.
    """

    def __init__(self):
        super().__init__(QStyleFactory.create("Fusion"))

    def pixelMetric(self, metric, option=None, widget=None):
        if metric == QStyle.PM_ToolBarExtensionExtent:
            return 26
        return super().pixelMetric(metric, option, widget)

    def sizeFromContents(self, ct, option, size, widget=None):
        # Eingabefelder mit Stylesheet so groß wie unter Qt 5: Rahmen und Abstände rechnet das
        # Stylesheet selbst dazu, Qt 6 zählt sonst noch Platz für die ausgeblendeten Pfeile mit
        if ct == QStyle.CT_SpinBox and widget is not None and widget.style() is not self:
            return QSize(size)
        return super().sizeFromContents(ct, option, size, widget)

    def styleHint(self, hint, option=None, widget=None, data=None):
        # Dialogknöpfe überall wie unter Windows: OK links von Abbrechen, ohne Symbole
        if hint == QStyle.SH_DialogButtonLayout:
            return QDialogButtonBox.ButtonLayout.WinLayout.value  # PySide6 erwartet int
        if hint == QStyle.SH_DialogButtonBox_ButtonsHaveIcons:
            return 0
        return super().styleHint(hint, option, widget, data)


def install_translator(app):
    """Qt-eigene Texte (OK/Abbrechen, Ja/Nein, Kalender) auf Deutsch."""
    translator = QTranslator(app)
    folder = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load(GERMAN, "qtbase", "_", folder):
        app.installTranslator(translator)
    return translator


GERMAN = QLocale(QLocale.German, QLocale.Germany)

THEMES = {
    "dark": {
        "bg": "#1E1E1E", "surface": "#252526", "bar": "#2D2D30",
        "border": "#3C3C3C", "text": "#F3F3F3", "muted": "#A0A0A0",
        "accent": "#007ACC", "hover": "#3A3D41", "pressed": "#33373B",
        "alt": "#2A2A2B", "handle": "#5A5A5A",
    },
    "light": {
        "bg": "#F3F4F6", "surface": "#FFFFFF", "bar": "#FFFFFF",
        "border": "#D5D9DE", "text": "#222222", "muted": "#666666",
        "accent": "#0067C0", "hover": "#E8EBEF", "pressed": "#DADEE3",
        "alt": "#F8F9FA", "handle": "#C2C7CD",
    },
}

STYLESHEET = """
QWidget { background-color: $bg; color: $text; font-size: 13px;
          font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", Arial, sans-serif; }
QToolBar { background-color: $bar; border: none; border-bottom: 1px solid $border;
           padding: 6px 8px; spacing: 4px; }
QToolBar::separator { background: $border; width: 1px; margin: 6px 6px; }
QToolBar#tools, QToolBar#fixed { border: none; padding: 0; background: transparent; }
QToolButton { background: transparent; border: 1px solid transparent;
              border-radius: 6px; padding: 4px 6px; }
QToolButton:hover { background-color: $hover; }
QToolButton:pressed, QToolButton:checked { background-color: $pressed; border-color: $border; }
QToolButton::menu-indicator { image: none; }
QStatusBar { background-color: $bar; color: $muted; border-top: 1px solid $border; }
QStatusBar QLabel { background: transparent; color: $muted; padding: 3px 8px; }
QStatusBar QToolButton { color: $text; padding: 2px 8px; margin: 2px 4px; }
QStatusBar::item { border: none; }
QDateEdit, QLineEdit, QTextEdit, QComboBox, QSpinBox, QTimeEdit, QListWidget {
    background-color: $surface; color: $text; border: 1px solid $border;
    border-radius: 6px; padding: 4px 6px; selection-background-color: $accent;
    selection-color: #FFFFFF; }
QDateEdit, QComboBox { min-height: 22px; }
QSpinBox, QTimeEdit { padding-right: 6px; }
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button { width: 0; border: none;
    subcontrol-origin: content; subcontrol-position: center left; } /* sonst Text ohne Rand links (Qt 6.12) */
QDateEdit { min-width: 102px; } /* + 18 px Kalenderpfeil (Qt 6) = 120 px wie bisher */
QComboBox QAbstractItemView { padding: 4px; outline: none; }
QPushButton { background-color: $hover; color: $text; border: 1px solid $border;
              border-radius: 6px; padding: 6px 14px; min-width: 80px; }
QPushButton:hover { background-color: $pressed; }
QPushButton:default { background-color: $accent; color: #FFFFFF; border-color: $accent; }
QToolButton:focus, QPushButton:focus { border: 2px solid $accent; }
QToolButton:focus { padding: 3px 5px; }
QPushButton:focus { padding: 5px 13px; }
QPushButton:default:focus { border-color: $text; }
QDateEdit:focus, QTimeEdit:focus, QLineEdit:focus, QTextEdit:focus, QComboBox:focus,
QSpinBox:focus, QListWidget:focus, QTableWidget:focus, QGraphicsView:focus {
    border: 1px solid $accent; }
QToolButton#qt_toolbar_ext_button { border: 1px solid $border; background-color: $hover; }
QLabel#hint { color: $muted; }
QPushButton:disabled, QToolButton:disabled, QLineEdit:disabled, QDateEdit:disabled,
QTimeEdit:disabled, QSpinBox:disabled, QCheckBox:disabled { color: $muted; }
QPushButton:disabled { background-color: $surface; }
QGroupBox { border: 1px solid $border; border-radius: 8px; margin-top: 1.2em;
            padding: 12px 8px 8px 8px; background-color: $surface; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; }
QGroupBox QWidget { font-weight: normal; }
QGroupBox QLabel, QGroupBox QCheckBox { background: transparent; }
QCheckBox { spacing: 8px; }
QMenu { background-color: $surface; border: 1px solid $border; border-radius: 8px; padding: 6px; }
QMenu::item { padding: 6px 28px 6px 10px; border-radius: 4px; }
QMenu::item:selected { background-color: $hover; color: $text; }
QMenu::item:disabled { color: $muted; }
QMenu::separator { height: 1px; background: $border; margin: 5px 8px; }
QMenu::icon { padding-left: 6px; }
QGraphicsView { border: 1px solid $border; border-radius: 8px; }
QTableWidget { background-color: $surface; alternate-background-color: $alt;
               border: 1px solid $border; border-radius: 8px; gridline-color: transparent;
               selection-background-color: $accent; selection-color: #FFFFFF; }
QTableWidget::item { padding: 2px 8px; border: none; }
QHeaderView::section { background-color: $bar; color: $muted; border: none;
                       border-bottom: 1px solid $border; padding: 6px 8px; font-weight: 600; }
QTableCornerButton::section { background-color: $bar; border: none; }
QSplitter::handle { background: transparent; }
QSplitter::handle:vertical { height: 8px; }
QScrollBar:horizontal { height: 10px; background: transparent; margin: 0; }
QScrollBar:vertical { width: 10px; background: transparent; margin: 0; }
QScrollBar::handle { background: $handle; border-radius: 4px; min-width: 30px; min-height: 30px; }
QScrollBar::handle:horizontal { margin: 2px 0; }
QScrollBar::handle:vertical { margin: 0 2px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QCalendarWidget QToolButton { color: $text; font-weight: bold; }
QCalendarWidget QWidget#qt_calendar_navigationbar { background-color: $bar; }
QCalendarWidget QAbstractItemView { background-color: $surface; color: $text;
    selection-background-color: $accent; selection-color: #FFFFFF; }
QCalendarWidget QAbstractItemView:disabled { color: $muted; }
QToolTip { background-color: #2b2b2b; color: #f0f0f0; border: 1px solid #555; padding: 4px 6px; }
"""

