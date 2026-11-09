"""Aussehen: Fusion-Stil, deutsche Qt-Texte, Farben (Tokens) und Stylesheet.

Ein neues Design ändert nur die Werte in THEMES und ergänzt bei Bedarf STYLESHEET
($name wird durch den Wert des Tokens ersetzt, siehe apply_style in app_menus.py;
$checkmark ist der Pfad zum Haken-Bild aus icons.check_mark_file).
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
        # Layouts ohne eigene Werte: Rand und Abstand aus der Token-Skala statt Fusion (9–11 / 6 px)
        if metric in (QStyle.PM_LayoutLeftMargin, QStyle.PM_LayoutTopMargin,
                      QStyle.PM_LayoutRightMargin, QStyle.PM_LayoutBottomMargin):
            return SPACE_M
        if metric in (QStyle.PM_LayoutHorizontalSpacing, QStyle.PM_LayoutVerticalSpacing):
            return SPACE_S
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
            pen = QPen(QColor(85, 85, 85, 179), 2)  # dunkelgrau, 30 % durchsichtig
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

# Design "Companion": ruhige Zink-Grautöne wie shadcn/ui, runde Ecken, Karten mit feinem Rand.
# Hauptknopf in Textfarbe (hell auf dunkel, dunkel auf hell), Windows-Blau für Bedienbares, Fokus
# und Vorschläge. Tokens:
#   band/bandtext/bandhover/bandpressed  Werkzeugleiste (ruhig wie der Hintergrund)
#   sel/seltext                          markierte Zeile (tonal statt Vollton)
#   accent/onaccent                      Fokus, Häkchen, Links, Vorschläge (Windows-Blau)
#   primary/onprimary                    Hauptknopf (Standardknopf, „Neuer Kunde“)
#   line                                 feine Linie zwischen den Zeilen der Tagesliste
#   now                                  Jetzt-Linie in der Timeline
#   control                              Rahmen von Feldern und Knöpfen (mind. 3 : 1 zum Grund)
#   chip/chiptext                        Merkmal-Chips (Kundenerkennung), Filter-Chips
#   good                                 „gilt“, „bleibt auf diesem Gerät“ (Grün)
#   tip/tiptext/tipborder                Hinweise (QToolTip, Timeline-Tooltip), in beiden Designs dunkel
THEMES = {
    # Dunkel wie Google Chrome im dunklen Modus (Grautöne #1F1F1F / #282828 / #3C3C3C),
    # Akzent Windows-Blau für dunkle Flächen
    "dark": {
        "bg": "#1F1F1F", "surface": "#282828", "bar": "#282828",
        "border": "#444746", "text": "#E3E3E3", "muted": "#C4C7C5",
        "accent": "#4CC2FF", "onaccent": "#00243D", "hover": "#353535", "pressed": "#474747",
        "alt": "#282828", "handle": "#8E918F", "line": "#323232", "control": "#8E918F",
        "band": "#3C3C3C", "bandtext": "#E3E3E3", "bandhover": "#474747", "bandpressed": "#545454",
        "sel": "#004A77", "seltext": "#C2E7FF", "now": "#F28B82",
        # Grund der Timeline: etwas dunkler als die Flächen, damit die farbigen Balken abheben
        "canvas": "#1A1A1A",
        "primary": "#4CC2FF", "onprimary": "#00243D",
        "chip": "#3C3C3C", "chiptext": "#E3E3E3", "good": "#6DD58C",
        "tip": "#3C3C3C", "tiptext": "#E3E3E3", "tipborder": "#5E5E5E",
        # Buchungsquote (booking_rate.py): Fläche und Schrift je Stufe
        "rate_low": "#4A1C1F", "rate_low_text": "#FFB4B6", "rate_mid": "#463708", "rate_mid_text": "#FFE08A",
        "rate_ok": "#173D27", "rate_ok_text": "#9BE8B8", "rate_over": "#0E6B34", "rate_over_text": "#FFFFFF",
        # Kachel Buchungsquote: farbige Zahl direkt auf der Karte
        "rate_value_low": "#FF8A8E", "rate_value_mid": "#FACC15", "rate_value_ok": "#6DD58C",
    },
    "light": {
        "bg": "#F7F7F8", "surface": "#FFFFFF", "bar": "#FFFFFF",
        "border": "#E4E4E7", "text": "#18181B", "muted": "#62626B",
        "accent": "#005FB8", "onaccent": "#FFFFFF", "hover": "#F1F1F3", "pressed": "#E6E6EA",
        "alt": "#FFFFFF", "handle": "#85858D", "line": "#F0F0F2", "control": "#85858D",
        "band": "#F7F7F8", "bandtext": "#18181B", "bandhover": "#ECECEF", "bandpressed": "#E2E2E6",
        "sel": "#E0EEF9", "seltext": "#003A70", "now": "#E11D48",
        "canvas": "#FFFFFF",
        "primary": "#18181B", "onprimary": "#FAFAFA",
        "chip": "#F4F4F5", "chiptext": "#27272A", "good": "#15803D",
        "tip": "#18181B", "tiptext": "#F4F4F5", "tipborder": "#3F3F46",
        # Buchungsquote (booking_rate.py): Fläche und Schrift je Stufe
        "rate_low": "#FCE4E4", "rate_low_text": "#9F1D20", "rate_mid": "#FFF1BF", "rate_mid_text": "#6B4E00",
        "rate_ok": "#DDF3E4", "rate_ok_text": "#1E6B3A", "rate_over": "#0F5E2E", "rate_over_text": "#FFFFFF",
        # Kachel Buchungsquote: farbige Zahl direkt auf der Karte (große Schrift 20 px fett: mind. 3 : 1)
        "rate_value_low": "#DC2626", "rate_value_mid": "#D97706", "rate_value_ok": "#16A34A",
    },
}

# ---- Eigene Farben (Menü Ansicht → Design). Gespeichert in config["custom_colors"], aktiv mit
# config["custom_theme"]. Man wählt nur diese Grundfarben, alle übrigen Tokens werden abgeleitet.
CUSTOM_KEYS = [
    ("bg", "Hintergrund"),
    ("surface", "Flächen (Listen, Menüs, Karten)"),
    ("band", "Kopfleiste oben"),
    ("text", "Schrift"),
    ("accent", "Akzent (Auswahl, Schalter, Häkchen)"),
]

# Akzentfarben zum schnellen Wählen im Dialog „Eigene Farben“: (Name, hell, dunkel)
ACCENT_PRESETS = [
    ("Windows-Blau", "#005FB8", "#4CC2FF"),
    ("Dunkelblau", "#003E92", "#99C3FF"),
    ("Hellgrau", "#5F6368", "#C4C7C5"),
    ("Lila", "#6D28D9", "#A78BFA"),
]


# Farbvorschläge im Menü beim Klick auf einen Bereich der Vorschau („Eigene Farben“):
# je Grundlage und Grundfarbe; die erste ist die des Standard-Designs.
SWATCHES = {
    "dark": {
        "bg": ["#1F1F1F", "#121212", "#202124", "#1E1E2E", "#1B2430", "#0F172A", "#1C1917", "#14201A"],
        "surface": ["#282828", "#2D2D2D", "#303134", "#252536", "#1F2A37", "#1E293B", "#292524", "#1D2B24"],
        "band": ["#3C3C3C", "#2D2D2D", "#35363A", "#313244", "#243447", "#334155", "#44403C", "#004A77"],
        "text": ["#E3E3E3", "#FFFFFF", "#D4D4D4", "#CDD6F4", "#E2E8F0", "#F5F5F4", "#C2E7FF", "#D9F99D"],
        "accent": ["#4CC2FF", "#99C3FF", "#C4C7C5", "#A78BFA", "#6DD58C", "#FFB74D", "#F28B82", "#5EEAD4"],
    },
    "light": {
        "bg": ["#F7F7F8", "#FFFFFF", "#F3F4F6", "#F5F3EF", "#EEF2F7", "#F4F1FA", "#EFF6F1", "#FDF6EC"],
        "surface": ["#FFFFFF", "#FAFAFA", "#F9FAFB", "#FFFDF8", "#F8FAFC", "#FCFAFF", "#F7FCF9", "#FFFBF5"],
        "band": ["#F7F7F8", "#E9ECEF", "#DCE6F2", "#EDE7F6", "#E3F1E8", "#1F2937", "#005FB8", "#3F3F46"],
        "text": ["#18181B", "#0A0A0A", "#374151", "#1E293B", "#3F3F46", "#27272A", "#1E3A5F", "#14532D"],
        "accent": ["#005FB8", "#003E92", "#5F6368", "#6D28D9", "#15803D", "#C2410C", "#BE123C", "#0F766E"],
    },
}


def _mix(a, b, t):
    """Farbe zwischen a (t = 0) und b (t = 1) als Hex-String."""
    ca, cb = QColor(a), QColor(b)
    return QColor(round(ca.red() + (cb.red() - ca.red()) * t),
                  round(ca.green() + (cb.green() - ca.green()) * t),
                  round(ca.blue() + (cb.blue() - ca.blue()) * t)).name().upper()


def default_custom_colors(base="dark"):
    """Startwerte für eigene Farben: die Grundfarben des gewählten Standard-Designs."""
    t = THEMES[base]
    return {"base": base, **{k: t[k] for k, _ in CUSTOM_KEYS}}


def custom_theme(colors):
    """Vollständiges Token-dict aus den wenigen eigenen Grundfarben."""
    colors = colors or {}
    base = "dark" if colors.get("base") == "dark" else "light"
    t = dict(THEMES[base])
    for key, _ in CUSTOM_KEYS:
        if QColor.isValidColorName(str(colors.get(key, ""))):
            t[key] = QColor(colors[key]).name().upper()
    bg, surface, band, text, accent = (t[k] for k in ("bg", "surface", "band", "text", "accent"))
    band_text = text if contrast(text, band) >= 4.5 else readable_on(band).name().upper()
    t.update({
        "bar": surface, "alt": surface, "canvas": surface,
        "border": _mix(surface, text, 0.16), "line": _mix(surface, text, 0.07),
        "handle": _mix(surface, text, 0.45), "control": _mix(surface, text, 0.45),
        "muted": _mix(text, surface, 0.3),
        "hover": _mix(surface, text, 0.07), "pressed": _mix(surface, text, 0.14),
        "bandtext": band_text, "bandhover": _mix(band, band_text, 0.1),
        "bandpressed": _mix(band, band_text, 0.17),
        "sel": _mix(surface, accent, 0.22), "seltext": text,
        "onaccent": readable_on(accent).name().upper(),
        "chip": _mix(surface, text, 0.07), "chiptext": text,
    })
    if base == "dark":
        t["primary"], t["onprimary"] = accent, t["onaccent"]
    return t


def theme_for(config):
    """Aktuelle Farben für diese Config: eigene Farben, sonst Hell oder Dunkel nach dark_mode.

    Eigene Farben gelten nur, solange ihre Grundlage zu dark_mode passt (Vorschau im
    Einstellungsfenster schaltet dark_mode probeweise um)."""
    config = config or {}
    dark = bool(config.get("dark_mode"))
    colors = config.get("custom_colors") or {}
    if config.get("custom_theme") and (colors.get("base") == "dark") == dark:
        return custom_theme(colors)
    return THEMES["dark" if dark else "light"]


# ---- Design-Tokens (docs/DESIGN-TOKENS.md). Qt kennt keine CSS-Variablen: Python nutzt die
# Konstanten, das Stylesheet die Platzhalter $space_*, $fs_*, $radius* (SIZE_TOKENS, beim Import ersetzt).

# Abstände (px), feste Skala: Ränder, Abstände zwischen Elementen, Lücken zwischen Gruppen
SPACE_XS = 4     # Titel → Beschreibung, eng zusammengehörig
SPACE_S = 8      # Elemente einer Gruppe, Zeilen
SPACE_M = 12     # Gruppen, Innenrand kleiner Karten, Standard-Rand von Layouts
SPACE_L = 16     # Innenrand von Dialogen und Karten
SPACE_XL = 24    # Abstand zwischen Bereichen, Seitenrand oben/unten
SPACE_2XL = 32   # Seitenrand links/rechts (Einstellungen)
SPACE_3XL = 48   # leere Zustände, große Lücken

# Schriftgrößen (px): nur diese vier, Zeilenhöhe Fließtext 1,5 (PROSE_LINE_HEIGHT)
FONT_SM = 12     # Spaltenköpfe, Beschriftungen von Kennzahlen, Zähler, Menü-Überschriften
FONT_BASE = 13   # Grundschrift
FONT_LG = 14     # Abschnittsüberschriften
FONT_XL = 20     # Seitentitel, große Kennzahlen

# Rundungen (px): klein (Häkchen, Menüzeilen), Felder und Knöpfe, Karten/Menüs/Tabellen, Chips
RADIUS_SM = 4
RADIUS = 6
RADIUS_CARD = 10
RADIUS_CHIP = 11

SIZE_TOKENS = {
    "space_xs": SPACE_XS, "space_s": SPACE_S, "space_m": SPACE_M, "space_l": SPACE_L,
    "space_xl": SPACE_XL, "space_2xl": SPACE_2XL, "space_3xl": SPACE_3XL,
    "fs_sm": FONT_SM, "fs_base": FONT_BASE, "fs_lg": FONT_LG, "fs_xl": FONT_XL,
    "radius_sm": RADIUS_SM, "radius": RADIUS, "radius_card": RADIUS_CARD, "radius_chip": RADIUS_CHIP,
}

# Eine Schrift für die ganze Oberfläche (Stylesheet, Timeline, Legende). Nur zwei Schnitte:
# normal und fett. Feste Breite nur für Schlüssel und Beispiele.
FONT_FAMILIES = ["Segoe UI Variable Text", "Segoe UI", "Geist", "Inter", "Arial", "sans-serif"]
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


def fit_text(button):
    """Knopf nie schmaler als sein Text in der Schrift des Stylesheets ($fs_base). Qt misst sonst,
    bevor das Stylesheet greift, und das Layout darf den Knopf bis auf min-width 80 quetschen."""
    font = QFont(button.font())
    font.setPixelSize(FONT_BASE)
    width = QFontMetrics(font).horizontalAdvance(button.text().replace("&", "")) + SPACE_XS
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
QWidget { background-color: $bg; color: $text; font-size: $fs_basepx; font-family: $font; }
QToolBar { background-color: $bar; border: none; padding: 6px 8px; spacing: 4px; }
QToolBar::separator { background: $border; width: 1px; margin: 6px 6px; }
QToolBar#tools, QToolBar#fixed { border: none; padding: 0; background: transparent; }
QToolButton { background: transparent; border: 1px solid transparent;
              border-radius: $radiuspx; padding: 4px 8px; }
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
QDateEdit, QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QTimeEdit, QListWidget {
    background-color: $surface; color: $text; border: 1px solid $control;
    border-radius: $radiuspx; padding: 5px 8px; selection-background-color: $sel;
    selection-color: $seltext; }
QDateEdit, QComboBox { min-height: 22px; }
QDateEdit { font-weight: bold; }
QSpinBox, QTimeEdit { padding-right: 6px; }
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button { width: 0; border: none;
    subcontrol-origin: content; subcontrol-position: center left; } /* sonst Text ohne Rand links (Qt 6.12) */
QDateEdit { min-width: 102px; } /* + 18 px Kalenderpfeil (Qt 6) = 120 px wie bisher */
QComboBox QAbstractItemView { padding: 4px; outline: none; }
QPushButton { background-color: $surface; color: $text; border: 1px solid $control;
              border-radius: $radiuspx; padding: 6px 14px; min-width: 80px; }
QPushButton:hover { background-color: $hover; }
QPushButton:default { background-color: $primary; color: $onprimary; border-color: $primary; font-weight: bold; }
QPushButton:default:hover { background-color: $muted; border-color: $muted; }
QToolButton:focus, QPushButton:focus { border: 2px solid $accent; }
QToolButton:focus { padding: 3px 5px; }
QPushButton:focus { padding: 5px 13px; }
QPushButton:default:focus { border-color: $accent; }
QDateEdit:focus, QTimeEdit:focus, QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QComboBox:focus,
QSpinBox:focus, QListWidget:focus, QTableWidget:focus {
    border: 1px solid $accent; }
QGraphicsView:focus { border: 1px solid $muted; }  /* Timeline ausgewählt: dunkelgrau statt Akzent */
QToolButton#qt_toolbar_ext_button { border: 1px solid $control; background-color: $hover; }
QLabel#hint { color: $muted; }
QTableWidget QLabel { padding: 2px 8px; }
QLabel#busy_text { color: $bandtext; background: transparent; font-weight: bold; padding: 2px 0; }
QStatusBar QToolButton#cta { background-color: $primary; color: $onprimary; font-weight: bold;
                             border-radius: $radiuspx; padding: 2px 12px; }
QStatusBar QToolButton#cta:hover { background-color: $primary; border-color: $accent; }
QStatusBar QToolButton#cta_secondary { background: transparent; color: $accent; font-weight: bold;
                                       border: 1px solid $accent; padding: 2px 12px; }
QStatusBar QToolButton#cta_secondary:hover { background-color: $hover; }
QToolButton#rate_low, QLabel#rate_low { background-color: $rate_low; color: $rate_low_text; font-weight: bold; }
QToolButton#rate_mid, QLabel#rate_mid { background-color: $rate_mid; color: $rate_mid_text; font-weight: bold; }
QToolButton#rate_ok, QLabel#rate_ok { background-color: $rate_ok; color: $rate_ok_text; font-weight: bold; }
QToolButton#rate_over, QLabel#rate_over { background-color: $rate_over; color: $rate_over_text; font-weight: bold; }
/* Kachel Buchungsquote: Zahl groß in der Farbe der Stufe (Text-Farbe der Stufe) */
QLabel#rate_value_low, QLabel#rate_value_mid, QLabel#rate_value_ok, QLabel#rate_value_over,
QLabel#rate_value_none { background: transparent; font-size: $fs_xlpx; font-weight: bold; }
QLabel#rate_value_low { color: $rate_value_low; }
QLabel#rate_value_mid { color: $rate_value_mid; }
QLabel#rate_value_ok, QLabel#rate_value_over { color: $rate_value_ok; }
QLabel#rate_value_none { color: $muted; }
QFrame#divider { background-color: $border; border: none; }
QFrame#card:focus { border: 2px solid $accent; }
QToolButton#rate_low, QToolButton#rate_mid, QToolButton#rate_ok, QToolButton#rate_over {
    border-radius: $radiuspx; padding: 3px 10px; }
QPushButton:disabled, QToolButton:disabled, QLineEdit:disabled, QDateEdit:disabled,
QTimeEdit:disabled, QSpinBox:disabled, QCheckBox:disabled { color: $muted; }
QPushButton:disabled { background-color: $surface; }
QGroupBox { border: 1px solid $border; border-radius: $radius_cardpx; margin-top: 1.4em;
            padding: 12px 8px 8px 8px; background-color: $surface; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; }
QGroupBox QWidget { font-weight: normal; }
QGroupBox QLabel, QGroupBox QCheckBox, QGroupBox QRadioButton { background: transparent; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid $control;
                       background-color: $surface; border-radius: $radius_smpx; }
QCheckBox::indicator:hover, QCheckBox::indicator:focus { border-color: $accent; }
QCheckBox::indicator:checked { border-color: $accent; background-color: $accent;
                               image: url($checkmark); }
QCheckBox::indicator:disabled { border-color: $border; }
QCheckBox::indicator:checked:disabled { background-color: $border; border-color: $border; }
QMenu { background-color: $surface; border: 1px solid $border; border-radius: $radius_cardpx; padding: 4px; }
QMenu::item { padding: 6px 28px 6px 12px; border-radius: $radius_smpx; }
QMenu::item:selected { background-color: $sel; color: $seltext; }
QMenu::item:disabled { color: $muted; }
QMenu::separator { height: 1px; background: $border; margin: 4px 0; }
QMenu::icon { padding-left: 6px; }
QGraphicsView { border: 1px solid $border; border-radius: $radius_cardpx; }  /* sichtbares Ende der Timeline */
QTableWidget { background-color: $surface; alternate-background-color: $alt;
               border: 1px solid $border; border-radius: $radius_cardpx; gridline-color: transparent;
               selection-background-color: $sel; selection-color: $seltext; }
QTableWidget::item { padding: 2px 8px; border: none; border-bottom: 1px solid $line; }
QTableWidget::item:selected { background-color: $sel; color: $seltext; }
QHeaderView::section { background-color: $bar; color: $muted; border: none;
                       border-bottom: 1px solid $border; padding: 6px 8px; font-weight: bold;
                       font-size: $fs_smpx; }
QTableCornerButton::section { background-color: $bar; border: none; }
QSplitter::handle { background: transparent; }
QSplitter::handle:vertical { height: 8px; }
QScrollBar:horizontal { height: 10px; background: transparent; margin: 0; }
QScrollBar:vertical { width: 10px; background: transparent; margin: 0; }
QScrollBar::handle { background: $handle; border-radius: 3px; min-width: 30px; min-height: 30px; }
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
QLabel#menu_header { color: $muted; background: transparent; font-size: $fs_smpx; font-weight: bold;
                     padding: 8px 12px 2px 12px; }
QLabel#example { background-color: $surface; color: $text; padding: 6px 8px;
                 font-family: "Cascadia Mono", Consolas, "DejaVu Sans Mono", monospace; font-size: $fs_smpx; }
QLabel#page_title { font-size: $fs_xlpx; font-weight: bold; }
QLabel#row_title { font-weight: bold; }
QLabel#row_page { color: $muted; font-size: $fs_smpx; font-weight: bold; }
QLabel#row_value { color: $text; font-weight: bold; }
QListWidget#settings_nav { border: none; border-right: 1px solid $border; background-color: $surface;
                           padding: 6px 0; outline: none; }
QListWidget#settings_nav::item { padding: 6px 10px; margin: 1px 6px; border-radius: $radiuspx; border-left: 3px solid transparent; }
QListWidget#settings_nav::item:selected { background-color: $sel; color: $seltext;
                                          border-left: 3px solid $accent; font-weight: bold; }
QListWidget#settings_nav::item:hover:!selected { background-color: $hover; }
QFrame#tile { background-color: $surface; border: 1px solid $border; border-radius: $radius_cardpx; }
QFrame#tile QLabel, QFrame#tile QCheckBox { background: transparent; }
QCheckBox#switch { spacing: 6px; font-weight: bold; }
QCheckBox#switch::indicator { width: 30px; height: 16px; border: 2px solid $muted; border-radius: $radius_cardpx;
                              background-color: $surface; }
QCheckBox#switch::indicator:checked { border-color: $accent; background-color: $accent; image: none; }
QCheckBox#switch::indicator:focus { border-color: $text; }
QFrame#setting_row { border: none; border-bottom: 1px solid $line; }
QFrame#setting_row QLabel, QFrame#setting_row QCheckBox { background: transparent; }
QPushButton#result_link { text-align: left; background: transparent; border: 1px solid $control; border-radius: $radiuspx; padding: 8px 12px; }
/* Hinweise (auch der Timeline-Tooltip): in beiden Designs dunkel, wie unter Windows 11 */
QToolTip, QLabel#timeline_tip { background-color: $tip; color: $tiptext; border: 1px solid $tipborder;
           border-radius: $radiuspx; padding: $space_spx $space_mpx; }
/* Companion-Bausteine: Karten, Chips, Kennzahlen, Hinweisboxen */
QFrame#card { background-color: $surface; border: 1px solid $border; border-radius: $radius_cardpx; }
QFrame#card QLabel, QFrame#card QCheckBox { background: transparent; }
QFrame#card_row { background: transparent; border: none; border-bottom: 1px solid $line; }
QFrame#card_row QLabel { background: transparent; }
QLabel#card_title { font-weight: bold; }
QLabel#section_title { font-weight: bold; font-size: $fs_lgpx; }
QLabel#kpi_label { color: $muted; background: transparent; font-size: $fs_smpx; }
QLabel#kpi_value { color: $text; background: transparent; font-size: $fs_xlpx; font-weight: bold; }
QLabel#avatar { background-color: $chip; color: $chiptext; border: 1px solid $border;
                border-radius: $radius_cardpx; font-size: $fs_smpx; font-weight: bold; padding: 0; }
QLabel#count { color: $muted; background: transparent; font-size: $fs_smpx; }
QLabel#good { color: $good; background: transparent; }
QToolButton#chip { background-color: $chip; color: $chiptext; border: 1px solid $border;
                   border-radius: $radius_chippx; padding: 2px 10px; }
QToolButton#chip:hover { border-color: $control; }
QToolButton#chip:checked { background-color: $primary; color: $onprimary; border-color: $primary; }
QToolButton#chip:focus { border: 2px solid $accent; padding: 1px 9px; }
QToolButton#chip_add { background: transparent; color: $muted; border: 1px dashed $control;
                       border-radius: $radius_chippx; padding: 2px 10px; }
QToolButton#chip_add:hover { color: $text; }
QToolButton#chip_add:focus { border: 2px solid $accent; padding: 1px 9px; }
QToolButton#link { background: transparent; color: $accent; border: none; padding: 2px 4px; }
QToolButton#link:hover { text-decoration: underline; }
QToolButton#link:focus { border: 1px solid $accent; padding: 1px 3px; }
QFrame#notice { background-color: $chip; border: 1px solid $border; border-radius: $radius_cardpx; }
QFrame#notice QLabel { background: transparent; }
QProgressBar { background-color: $chip; border: none; border-radius: 2px; }
QProgressBar::chunk { background-color: $good; border-radius: 2px; }
QWidget#chips, QWidget#band_row { background: transparent; }
QWidget#customer_detail { background-color: $surface; }
QScrollArea { background: transparent; border: none; }
QListWidget#nav_list { border: none; background: transparent; outline: none; padding: 4px; }
QListWidget#nav_list::item { border-radius: $radiuspx; padding: 6px 8px; margin: 1px 0; }
QListWidget#nav_list::item:selected { background-color: $sel; color: $seltext; }
QListWidget#nav_list::item:hover:!selected { background-color: $hover; }
""".replace("$font", FONT_CSS)
for _key in sorted(SIZE_TOKENS, key=len, reverse=True):  # $radius_card vor $radius ersetzen
    STYLESHEET = STYLESHEET.replace(f"${_key}px", f"{SIZE_TOKENS[_key]}px")


def _luminance(color):
    c = QColor(color)

    def channel(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(c.red()) + 0.7152 * channel(c.green()) + 0.0722 * channel(c.blue())


def contrast(a, b):
    """Kontrastverhältnis zweier Farben nach WCAG (1 bis 21)."""
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def readable_on(color):
    """Schwarz oder Weiß, je nachdem was auf dieser Füllfarbe besser lesbar ist (WCAG)."""
    c = QColor(color)

    def channel(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    lum = 0.2126 * channel(c.red()) + 0.7152 * channel(c.green()) + 0.0722 * channel(c.blue())
    # Kontrast zu Weiß gegen Kontrast zu #14181D (relative Helligkeit 0.009)
    return QColor("#FFFFFF") if 1.05 / (lum + 0.05) >= (lum + 0.05) / 0.059 else QColor("#14181D")

