"""Aussehen: Fusion-Stil, deutsche Qt-Texte, Farben (Tokens) und Stylesheet.

Ein neues Design ändert nur die Werte in THEMES und ergänzt bei Bedarf STYLESHEET
($name wird durch den Wert des Tokens ersetzt, siehe apply_style in app_menus.py).
Die Timeline (timeline_only.py) nimmt ihre Grundfarben ebenfalls aus THEMES.
"""
import html
import re

from PySide6.QtCore import QLibraryInfo, QLocale, QSize, Qt, QTranslator
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPen
from PySide6.QtWidgets import (QDialogButtonBox, QHeaderView, QProxyStyle, QRubberBand, QStyle,
                               QStyleFactory)


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

    def polish(self, target):
        # Spaltenköpfe überall linksbündig wie der Text darunter (Qt zentriert sonst)
        if isinstance(target, QHeaderView) and target.orientation() == Qt.Horizontal:
            target.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        return super().polish(target)

    def drawControl(self, element, option, painter, widget=None):
        # Vorschau beim Ziehen der Trennleiste (QSplitter ohne opaqueResize): gestrichelte Linie
        if element == QStyle.CE_RubberBand and isinstance(widget, QRubberBand) \
                and widget.shape() == QRubberBand.Line:
            painter.save()
            pen = QPen(QColor("#8A8A8A"), 2)  # mittelgrau
            pen.setDashPattern([2, 2])  # fein: 4 px Strich, 4 px Lücke
            painter.setPen(pen)
            r = option.rect
            if r.width() >= r.height():
                y = r.center().y()
                painter.drawLine(r.left(), y, r.right(), y)
            else:
                x = r.center().x()
                painter.drawLine(x, r.top(), x, r.bottom())
            painter.restore()
            return
        super().drawControl(element, option, painter, widget)

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

# Design "Metro Klar": Form aus Metro (eckig, volle Balken; Überschriften ohne Großbuchstaben),
# Farben aus "Klar" (ruhige Flächen, tonale Auswahl). Zusätzliche Tokens gegenüber früher:
#   band/bandtext/bandhover/bandpressed  Werkzeugleiste (in "Klar"-Farben: ruhig wie der Hintergrund)
#   sel/seltext                          markierte Zeile (tonal statt Vollton)
#   onaccent                             Schrift auf Akzentfarbe (Standardknopf, "offen"-Knopf)
#   line                                 feine Linie zwischen den Zeilen der Tagesliste
#   now                                  Jetzt-Linie in der Timeline
#   control                              Rahmen von Feldern und Knöpfen (mind. 3 : 1 zum Grund)
THEMES = {
    "dark": {
        "bg": "#12161B", "surface": "#181D23", "bar": "#181D23",
        "border": "#2A323C", "text": "#E6EAF0", "muted": "#9AA4B1",
        "accent": "#4EA1FF", "onaccent": "#06121F", "hover": "#222A33", "pressed": "#2B3440",
        "alt": "#181D23", "handle": "#6B7682", "line": "#20262E", "control": "#6B7682",
        "band": "#12161B", "bandtext": "#E6EAF0", "bandhover": "#222A33", "bandpressed": "#2B3440",
        "sel": "#1F3B5C", "seltext": "#FFFFFF", "now": "#FF6369",
        # Buchungsquote (booking_rate.py): Fläche und Schrift je Stufe
        "rate_low": "#4A1C1F", "rate_low_text": "#FFB4B6", "rate_mid": "#463708", "rate_mid_text": "#FFE08A",
        "rate_ok": "#173D27", "rate_ok_text": "#9BE8B8", "rate_over": "#0E6B34", "rate_over_text": "#FFFFFF",
    },
    "light": {
        "bg": "#F4F6F8", "surface": "#FFFFFF", "bar": "#FFFFFF",
        "border": "#DDE2E8", "text": "#1B1F24", "muted": "#5F6873",
        "accent": "#0067C0", "onaccent": "#FFFFFF", "hover": "#E9EDF2", "pressed": "#DDE3EA",
        "alt": "#FFFFFF", "handle": "#858F9B", "line": "#EEF1F4", "control": "#858F9B",
        "band": "#F4F6F8", "bandtext": "#1B1F24", "bandhover": "#E9EDF2", "bandpressed": "#DDE3EA",
        "sel": "#DCEBFA", "seltext": "#0A3B6B", "now": "#E5484D",
        # Buchungsquote (booking_rate.py): Fläche und Schrift je Stufe
        "rate_low": "#FCE4E4", "rate_low_text": "#9F1D20", "rate_mid": "#FFF1BF", "rate_mid_text": "#6B4E00",
        "rate_ok": "#DDF3E4", "rate_ok_text": "#1E6B3A", "rate_over": "#0F5E2E", "rate_over_text": "#FFFFFF",
    },
}

# Eine Schrift für die ganze Oberfläche (Stylesheet, Timeline, Legende). Nur zwei Schnitte:
# normal und fett. Feste Breite nur für Schlüssel und Beispiele.
FONT_FAMILIES = ["Segoe UI Variable Text", "Segoe UI", "Inter", "Arial", "sans-serif"]
FONT_CSS = ", ".join(f'"{f}"' if " " in f else f for f in FONT_FAMILIES)


def ui_font(point_size, bold=False):
    """Schrift der Oberfläche für selbst gezeichnete Teile (Timeline)."""
    font = QFont(FONT_FAMILIES, point_size)
    font.setBold(bold)
    return font


# Fließtext: Zeilenhöhe 1,5
PROSE_LINE_HEIGHT = 150


def fit_bold(button):
    """Standardknopf ist fett (Stylesheet), Qt misst die Breite aber mit normaler Schrift:
    Platz für den fetten Text, damit er nie abgeschnitten wird. Nach setText aufrufen.
    (min-width im Stylesheet, setMinimumWidth überschriebe das Design beim Polieren)"""
    bold = QFont(button.font())
    bold.setBold(True)
    width = QFontMetrics(bold).horizontalAdvance(button.text().replace("&", "")) + 36
    button.setStyleSheet(f"QPushButton {{ min-width: {width}px; }}")


def prose(label):
    """Längeren Hinweistext gut lesbar setzen: Zeilenabstand 1,5.

    Für feste Einleitungen und Erklärungen in Dialogen. label muss setWordWrap(True) haben.
    """
    text = label.text()
    if not re.search(r"<[a-zA-Z/][^>]*>", text):
        text = html.escape(text, quote=False).replace("\n", "<br>")
    label.setText(f'<p style="line-height:{PROSE_LINE_HEIGHT}%; margin:0">{text}</p>')
    # Zeilenlänge: die Dialoge haben feste, schmale Breiten (480–560 px, etwa 70–80 Zeichen).
    # Keine eigene Begrenzung am Label: setMaximumWidth setzt den Text in breiten Fenstern mittig
    # oder schneidet ihn ab, ein Ereignisfilter stürzt unter Windows beim Beenden ab.
    return label


STYLESHEET = """
QWidget { background-color: $bg; color: $text; font-size: 13px; font-family: $font; }
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
QToolBar#main_toolbar QToolButton:focus { border: 2px solid $accent; }
QToolBar#main_toolbar::separator, QToolBar#main_toolbar QToolBar::separator {
    background: $border; width: 1px; margin: 6px 6px; }
QToolBar#main_toolbar QToolButton#qt_toolbar_ext_button { border: 1px solid $control;
    background-color: $bandhover; color: $bandtext; }
QStatusBar { background-color: $bg; color: $muted; border-top: 1px solid $border; }
QStatusBar QLabel { background: transparent; color: $muted; padding: 3px 8px; }
QStatusBar QToolButton { color: $text; padding: 2px 8px; margin: 2px 4px; }
QStatusBar::item { border: none; }
QDateEdit, QLineEdit, QTextEdit, QComboBox, QSpinBox, QTimeEdit, QListWidget {
    background-color: $surface; color: $text; border: 1px solid $control;
    border-radius: 0; padding: 4px 6px; selection-background-color: $sel;
    selection-color: $seltext; }
QDateEdit, QComboBox { min-height: 22px; }
QDateEdit { font-weight: bold; }
QSpinBox, QTimeEdit { padding-right: 6px; }
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button { width: 0; border: none;
    subcontrol-origin: content; subcontrol-position: center left; } /* sonst Text ohne Rand links (Qt 6.12) */
QDateEdit { min-width: 102px; } /* + 18 px Kalenderpfeil (Qt 6) = 120 px wie bisher */
QComboBox QAbstractItemView { padding: 4px; outline: none; }
QPushButton { background-color: $hover; color: $text; border: 1px solid $control;
              border-radius: 0; padding: 6px 14px; min-width: 80px; }
QPushButton:hover { background-color: $pressed; }
QPushButton:default { background-color: $accent; color: $onaccent; border-color: $accent; font-weight: bold; }
QToolButton:focus, QPushButton:focus { border: 2px solid $accent; }
QToolButton:focus { padding: 3px 5px; }
QPushButton:focus { padding: 5px 13px; }
QPushButton:default:focus { border-color: $text; }
QDateEdit:focus, QTimeEdit:focus, QLineEdit:focus, QTextEdit:focus, QComboBox:focus,
QSpinBox:focus, QListWidget:focus, QTableWidget:focus, QGraphicsView:focus {
    border: 1px solid $accent; }
QToolButton#qt_toolbar_ext_button { border: 1px solid $control; background-color: $hover; }
QLabel#hint { color: $muted; }
QTableWidget QLabel { padding: 2px 8px; }
QLabel#busy_text { color: $bandtext; background: transparent; font-weight: bold; padding: 2px 0; }
QStatusBar QToolButton#cta { background-color: $accent; color: $onaccent; font-weight: bold;
                             border-radius: 0; padding: 2px 12px; }
QStatusBar QToolButton#cta:hover { background-color: $accent; border-color: $text; }
QStatusBar QToolButton#cta_secondary { background: transparent; color: $accent; font-weight: bold;
                                       border: 1px solid $accent; padding: 2px 12px; }
QStatusBar QToolButton#cta_secondary:hover { background-color: $hover; }
QStatusBar QToolButton#rate_low, QLabel#rate_low { background-color: $rate_low; color: $rate_low_text; font-weight: bold; }
QStatusBar QToolButton#rate_mid, QLabel#rate_mid { background-color: $rate_mid; color: $rate_mid_text; font-weight: bold; }
QStatusBar QToolButton#rate_ok, QLabel#rate_ok { background-color: $rate_ok; color: $rate_ok_text; font-weight: bold; }
QStatusBar QToolButton#rate_over, QLabel#rate_over { background-color: $rate_over; color: $rate_over_text; font-weight: bold; }
QPushButton:disabled, QToolButton:disabled, QLineEdit:disabled, QDateEdit:disabled,
QTimeEdit:disabled, QSpinBox:disabled, QCheckBox:disabled { color: $muted; }
QPushButton:disabled { background-color: $surface; }
QGroupBox { border: none; border-radius: 0; margin-top: 1.4em;
            padding: 12px 8px 8px 8px; background-color: $surface; font-weight: bold; }
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
                       border-bottom: 1px solid $border; padding: 6px 8px; font-weight: bold;
                       font-size: 12px; }
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
QMenu#view_menu::item { padding: 4px 28px 4px 12px; }
QLabel#menu_header { color: $muted; background: transparent; font-size: 12px; font-weight: bold;
                     padding: 8px 12px 2px 12px; }
QLabel#example { background-color: $surface; color: $text; padding: 6px 8px;
                 font-family: "Cascadia Mono", Consolas, "DejaVu Sans Mono", monospace; font-size: 12px; }
QLabel#page_title { font-size: 20px; font-weight: bold; }
QLabel#row_title { font-weight: bold; }
QLabel#row_page { color: $muted; font-size: 12px; font-weight: bold; }
QLabel#row_value { color: $text; font-weight: bold; }
QListWidget#settings_nav { border: none; border-right: 1px solid $border; background-color: $surface;
                           padding: 6px 0; outline: none; }
QListWidget#settings_nav::item { padding: 4px 10px; border-left: 3px solid transparent; }
QListWidget#settings_nav::item:selected { background-color: $sel; color: $seltext;
                                          border-left: 3px solid $accent; font-weight: bold; }
QListWidget#settings_nav::item:hover:!selected { background-color: $hover; }
QFrame#tile { background-color: $surface; border: 1px solid $border; }
QFrame#tile QLabel, QFrame#tile QCheckBox { background: transparent; }
QCheckBox#switch { spacing: 6px; font-weight: bold; }
QCheckBox#switch::indicator { width: 30px; height: 16px; border: 2px solid $muted; border-radius: 10px;
                              background-color: $surface; }
QCheckBox#switch::indicator:checked { border-color: $accent; background-color: $accent; }
QCheckBox#switch::indicator:focus { border-color: $text; }
QFrame#setting_row { border: none; border-bottom: 1px solid $line; }
QFrame#setting_row QLabel, QFrame#setting_row QCheckBox { background: transparent; }
QPushButton#result_link { text-align: left; background: transparent; border: 1px solid $control; padding: 8px 12px; }
QToolTip { background-color: #1B1F24; color: #F2F4F7; border: 1px solid #3A424C; border-radius: 0;
           padding: 4px 6px; }
""".replace("$font", FONT_CSS)


def readable_on(color):
    """Schwarz oder Weiß, je nachdem was auf dieser Füllfarbe besser lesbar ist (WCAG)."""
    c = QColor(color)

    def channel(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    lum = 0.2126 * channel(c.red()) + 0.7152 * channel(c.green()) + 0.0722 * channel(c.blue())
    # Kontrast zu Weiß gegen Kontrast zu #14181D (relative Helligkeit 0.009)
    return QColor("#FFFFFF") if 1.05 / (lum + 0.05) >= (lum + 0.05) / 0.059 else QColor("#14181D")

