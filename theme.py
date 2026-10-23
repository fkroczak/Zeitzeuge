"""Aussehen: Fusion-Stil, deutsche Qt-Texte, Farben (Tokens) und Stylesheet.

Ein neues Design ändert nur die Werte in THEMES und ergänzt bei Bedarf STYLESHEET
($name wird durch den Wert des Tokens ersetzt, siehe apply_style in app_menus.py).
Die Timeline (timeline_only.py) nimmt ihre Grundfarben ebenfalls aus THEMES.
"""
from PySide6.QtCore import QLibraryInfo, QLocale, QSize, QTranslator
from PySide6.QtGui import QColor
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

# Design "Metro Klar": Form aus Metro (eckig, blaues Band oben, Großbuchstaben, volle Balken),
# Farben aus "Klar" (ruhige Flächen, tonale Auswahl). Zusätzliche Tokens gegenüber früher:
#   band/bandtext/bandhover/bandpressed  Werkzeugleiste als farbiges Band
#   sel/seltext                          markierte Zeile (tonal statt Vollton)
#   onaccent                             Schrift auf Akzentfarbe (Standardknopf, "offen"-Knopf)
#   line                                 feine Linie zwischen den Zeilen der Tagesliste
#   now                                  Jetzt-Linie in der Timeline
THEMES = {
    "dark": {
        "bg": "#12161B", "surface": "#181D23", "bar": "#181D23",
        "border": "#2A323C", "text": "#E6EAF0", "muted": "#9AA4B1",
        "accent": "#4EA1FF", "onaccent": "#06121F", "hover": "#222A33", "pressed": "#2B3440",
        "alt": "#181D23", "handle": "#3E4854", "line": "#20262E",
        "band": "#0B4F8F", "bandtext": "#FFFFFF", "bandhover": "#165FA6", "bandpressed": "#083D70",
        "sel": "#1F3B5C", "seltext": "#FFFFFF", "now": "#FF6369",
    },
    "light": {
        "bg": "#F4F6F8", "surface": "#FFFFFF", "bar": "#FFFFFF",
        "border": "#DDE2E8", "text": "#1B1F24", "muted": "#5F6873",
        "accent": "#0067C0", "onaccent": "#FFFFFF", "hover": "#E9EDF2", "pressed": "#DDE3EA",
        "alt": "#FFFFFF", "handle": "#C2CAD3", "line": "#EEF1F4",
        "band": "#0067C0", "bandtext": "#FFFFFF", "bandhover": "#1A79CC", "bandpressed": "#00508F",
        "sel": "#DCEBFA", "seltext": "#0A3B6B", "now": "#E5484D",
    },
}

STYLESHEET = """
QWidget { background-color: $bg; color: $text; font-size: 13px;
          font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", Arial, sans-serif; }
QToolBar { background-color: $bar; border: none; padding: 6px 8px; spacing: 4px; }
QToolBar::separator { background: $border; width: 1px; margin: 6px 6px; }
QToolBar#tools, QToolBar#fixed { border: none; padding: 0; background: transparent; }
QToolButton { background: transparent; border: 1px solid transparent;
              border-radius: 0; padding: 4px 6px; }
QToolButton:hover { background-color: $hover; }
QToolButton:pressed, QToolButton:checked { background-color: $pressed; border-color: $border; }
QToolButton::menu-indicator { image: none; }
QToolBar#main_toolbar { background-color: $band; padding: 6px 8px; }
QToolBar#main_toolbar QToolBar { background-color: $band; } /* auch als Überlauf-Fenster (») */
QToolBar#main_toolbar QToolButton { color: $bandtext; }
QToolBar#main_toolbar QToolButton:hover { background-color: $bandhover; }
QToolBar#main_toolbar QToolButton:pressed, QToolBar#main_toolbar QToolButton:checked {
    background-color: $bandpressed; border-color: $bandpressed; }
QToolBar#main_toolbar QToolButton:focus { border: 2px solid $bandtext; }
QToolBar#main_toolbar::separator, QToolBar#main_toolbar QToolBar::separator {
    background: $bandhover; width: 1px; margin: 6px 6px; }
QToolBar#main_toolbar QToolButton#qt_toolbar_ext_button { border: 1px solid $bandhover;
    background-color: $bandpressed; color: $bandtext; }
QToolBar#main_toolbar QDateEdit { background-color: $bandpressed; color: $bandtext;
    border: 1px solid $bandpressed; selection-background-color: $bandtext; selection-color: $band; }
QToolBar#main_toolbar QDateEdit:hover { background-color: $bandhover; }
QToolBar#main_toolbar QDateEdit:focus { border: 1px solid $bandtext; }
QStatusBar { background-color: $bg; color: $muted; border-top: 1px solid $border; }
QStatusBar QLabel { background: transparent; color: $muted; padding: 3px 8px; }
QStatusBar QToolButton { color: $text; padding: 2px 8px; margin: 2px 4px; }
QStatusBar::item { border: none; }
QDateEdit, QLineEdit, QTextEdit, QComboBox, QSpinBox, QTimeEdit, QListWidget {
    background-color: $surface; color: $text; border: 1px solid $border;
    border-radius: 0; padding: 4px 6px; selection-background-color: $sel;
    selection-color: $seltext; }
QDateEdit, QComboBox { min-height: 22px; }
QDateEdit { font-weight: 600; }
QSpinBox, QTimeEdit { padding-right: 6px; }
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button { width: 0; border: none;
    subcontrol-origin: content; subcontrol-position: center left; } /* sonst Text ohne Rand links (Qt 6.12) */
QDateEdit { min-width: 102px; } /* + 18 px Kalenderpfeil (Qt 6) = 120 px wie bisher */
QComboBox QAbstractItemView { padding: 4px; outline: none; }
QPushButton { background-color: $hover; color: $text; border: 1px solid $border;
              border-radius: 0; padding: 6px 14px; min-width: 80px; }
QPushButton:hover { background-color: $pressed; }
QPushButton:default { background-color: $accent; color: $onaccent; border-color: $accent; font-weight: 600; }
QToolButton:focus, QPushButton:focus { border: 2px solid $accent; }
QToolButton:focus { padding: 3px 5px; }
QPushButton:focus { padding: 5px 13px; }
QPushButton:default:focus { border-color: $text; }
QDateEdit:focus, QTimeEdit:focus, QLineEdit:focus, QTextEdit:focus, QComboBox:focus,
QSpinBox:focus, QListWidget:focus, QTableWidget:focus, QGraphicsView:focus {
    border: 1px solid $accent; }
QToolButton#qt_toolbar_ext_button { border: 1px solid $border; background-color: $hover; }
QLabel#hint { color: $muted; }
QStatusBar QToolButton#cta { background-color: $accent; color: $onaccent; font-weight: 600;
                             border-radius: 0; padding: 2px 12px; }
QStatusBar QToolButton#cta:hover { background-color: $accent; border-color: $text; }
QPushButton:disabled, QToolButton:disabled, QLineEdit:disabled, QDateEdit:disabled,
QTimeEdit:disabled, QSpinBox:disabled, QCheckBox:disabled { color: $muted; }
QPushButton:disabled { background-color: $surface; }
QGroupBox { border: 1px solid $border; border-radius: 0; margin-top: 1.2em;
            padding: 12px 8px 8px 8px; background-color: $surface; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; }
QGroupBox QWidget { font-weight: normal; }
QGroupBox QLabel, QGroupBox QCheckBox { background: transparent; }
QCheckBox { spacing: 8px; }
QMenu { background-color: $surface; border: 1px solid $border; border-radius: 0; padding: 4px 0; }
QMenu::item { padding: 6px 28px 6px 12px; border-radius: 0; }
QMenu::item:selected { background-color: $sel; color: $seltext; }
QMenu::item:disabled { color: $muted; }
QMenu::separator { height: 1px; background: $border; margin: 4px 0; }
QMenu::icon { padding-left: 6px; }
QGraphicsView { border: none; border-radius: 0; }
QTableWidget { background-color: $surface; alternate-background-color: $alt;
               border: none; border-radius: 0; gridline-color: transparent;
               selection-background-color: $sel; selection-color: $seltext; }
QTableWidget::item { padding: 2px 8px; border: none; border-bottom: 1px solid $line; }
QTableWidget::item:selected { background-color: $sel; color: $seltext; }
QHeaderView::section { background-color: $bar; color: $muted; border: none;
                       border-bottom: 2px solid $border; padding: 6px 8px; font-weight: 600;
                       font-size: 11px; }
QTableCornerButton::section { background-color: $bar; border: none; }
QSplitter::handle { background: transparent; }
QSplitter::handle:vertical { height: 8px; }
QScrollBar:horizontal { height: 10px; background: transparent; margin: 0; }
QScrollBar:vertical { width: 10px; background: transparent; margin: 0; }
QScrollBar::handle { background: $handle; border-radius: 0; min-width: 30px; min-height: 30px; }
QScrollBar::handle:horizontal { margin: 2px 0; }
QScrollBar::handle:vertical { margin: 0 2px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QCalendarWidget QToolButton { color: $bandtext; font-weight: bold; }
QCalendarWidget QToolButton:hover { background-color: $bandhover; }
QCalendarWidget QWidget#qt_calendar_navigationbar { background-color: $band; }
QCalendarWidget QAbstractItemView { background-color: $surface; color: $text;
    selection-background-color: $accent; selection-color: $onaccent; }
QCalendarWidget QAbstractItemView:disabled { color: $muted; }
QToolTip { background-color: #1B1F24; color: #F2F4F7; border: 1px solid #3A424C; border-radius: 0;
           padding: 4px 6px; }
"""


def readable_on(color):
    """Schwarz oder Weiß, je nachdem was auf dieser Füllfarbe besser lesbar ist (WCAG)."""
    c = QColor(color)

    def channel(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    lum = 0.2126 * channel(c.red()) + 0.7152 * channel(c.green()) + 0.0722 * channel(c.blue())
    # Kontrast zu Weiß gegen Kontrast zu #14181D (relative Helligkeit 0.009)
    return QColor("#FFFFFF") if 1.05 / (lum + 0.05) >= (lum + 0.05) / 0.059 else QColor("#14181D")

