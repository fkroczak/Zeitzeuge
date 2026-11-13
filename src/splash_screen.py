"""Startbild der EXE mit Ladebalken (ZeitZeuge.spec, PyInstaller-Splash).

PyInstaller zeichnet das Startbild mit Tcl/Tk, schon während sich die EXE entpackt. Von sich aus
kann es nur eine Textzeile ändern. TCL_TEXT ersetzt beim Bauen den Textteil des Tcl-Skripts
(ZeitZeuge.spec) und zeichnet dazu einen Balken:
  - Beim Entpacken schreibt der Bootloader jeden Dateinamen ins Startbild. Daraus wird
    „Programm entpacken …“ und der Balken läuft bis EXTRACT_SHARE Prozent.
  - Danach meldet Zeitzeuge seine Schritte mit step(prozent, text).
  - Zum Schluss hält close_when_painted(fenster) das Startbild im Vordergrund, bis das Hauptfenster
    gezeichnet ist und wieder flüssig reagiert. Bis dahin ist das Fenster durchsichtig: Statt eines
    weißen Fensters „(Keine Rückmeldung)“ sieht man das Startbild mit laufendem Balken.
Zwischen zwei Meldungen rückt der Balken langsam weiter, damit er nicht stehen bleibt.
Ohne Startbild (Start aus dem Quelltext) tun step und close nichts.

Bildschirmskalierung (z. B. 125 %): Die EXE meldet sich bei Windows als DPI-bewusst (manifest()).
Ohne das vergrößerte Windows das Startbild unscharf, und sobald Qt startete und auf echte Pixel
umschaltete, sprang es klein in die linke obere Ecke. Jetzt wählt das Startbild selbst das Bild
zur Skalierung (assets/splash_125.png …, tests/make_splash.py) und rechnet Text und Balken mit.
"""
import base64
import os

EXTRACT_SHARE = 55  # Anteil des Balkens fürs Entpacken
SIZE = (420, 170)  # assets/splash.png bei 100 %
BAR = (26, 154, 394, 158)  # x0, y0, x1, y1 im Bild bei 100 %
TEXT_POS = (26, 146)  # Text unten links (wie text_pos in ZeitZeuge.spec)
TEXT_PX = 13  # Schrift des Schritts in Pixeln bei 100 %
SCALES = (100, 125, 150, 175, 200, 250, 300)  # Bildschirmskalierungen mit eigenem Bild
BAR_COLOR = "#0067C0"  # Blau aus dem Logo
TRACK_COLOR = "#E4E4E7"

# Ersetzt splash_templates.splash_canvas_text. Platzhalter %(…)s füllt PyInstaller,
# {total} und die Balkenmaße kommen aus tcl_text(). Keine Kommentare: PyInstaller kürzt das Skript.
_TCL = r"""
{images}
set zz_s 100
set zz_want [expr {{[tk scaling] * 75.0}}]
foreach zz_k [array names zz_img] {{
    if {{abs($zz_k - $zz_want) < abs($zz_s - $zz_want)}} {{ set zz_s $zz_k }}
}}
if {{$zz_s != 100}} {{
    image create photo zz_photo -data $zz_img($zz_s)
    splash_image blank
    splash_image copy zz_photo -shrink
    image delete zz_photo
    set image_width [image width splash_image]
    set image_height [image height splash_image]
    .root.canvas configure -width $image_width -height $image_height
    .root.canvas coords [lindex [.root.canvas find all] 0] [expr {{$image_width / 2}}] [expr {{$image_height / 2}}]
    set x_position [expr {{int($display_x + 0.5*($display_width - $image_width))}}]
    set y_position [expr {{int($display_y + 0.5*($display_height - $image_height))}}]
}}
array unset zz_img
set zz_x0 [expr {{round({x0} * $zz_s / 100.0)}}]
set zz_y0 [expr {{round({y0} * $zz_s / 100.0)}}]
set zz_x1 [expr {{round({x1} * $zz_s / 100.0)}}]
set zz_y1 [expr {{round({y1} * $zz_s / 100.0)}}]
font configure myFont -size [expr {{-round({text_px} * $zz_s / 100.0)}}]
.root.canvas create text [expr {{round({tx} * $zz_s / 100.0)}}] [expr {{round({ty} * $zz_s / 100.0)}}] -fill %(color)s -justify left -font myFont -tag vartext -anchor sw
.root.canvas create rectangle $zz_x0 $zz_y0 $zz_x1 $zz_y1 -fill {track} -outline {{}} -tag zz_track
.root.canvas create rectangle $zz_x0 $zz_y0 $zz_x0 $zz_y1 -fill {bar} -outline {{}} -tag zz_bar
set zz_files 0
set zz_goal 0.0
set zz_shown 0.0
proc zz_status {{args}} {{
    global status_text zz_files zz_goal
    if {{[regexp {{^[!]([0-9]+[|].*)$}} $status_text -> rest]}} {{
        catch {{wm attributes . -topmost 1}}
        set status_text $rest
        return
    }}
    if {{[regexp {{^([0-9]+)[|](.*)$}} $status_text -> pct text]}} {{
        set goal $pct
    }} else {{
        incr zz_files
        set goal [expr {{{extract} * min(1.0, double($zz_files) / {total})}}]
        set text "Programm entpacken …"
    }}
    if {{$goal > $zz_goal}} {{ set zz_goal $goal }}
    .root.canvas itemconfigure vartext -text $text
}}
proc zz_tick {{}} {{
    global zz_goal zz_shown zz_x0 zz_y0 zz_x1 zz_y1
    if {{$zz_shown < $zz_goal}} {{
        set zz_shown [expr {{min($zz_goal, $zz_shown + max(0.5, ($zz_goal - $zz_shown) / 4.0))}}]
    }} elseif {{$zz_shown < min(97.0, $zz_goal + 8.0)}} {{
        set zz_shown [expr {{$zz_shown + 0.1}}]
    }}
    .root.canvas coords zz_bar $zz_x0 $zz_y0 [expr {{$zz_x0 + ($zz_x1 - $zz_x0) * $zz_shown / 100.0}}] $zz_y1
    after 40 zz_tick
}}
trace add variable status_text write zz_status
set status_text "0|%(default_text)s"
zz_tick
"""


def image_path(assets, scale):
    """Startbild für eine Skalierung: splash.png (100 %), sonst splash_<prozent>.png."""
    return os.path.join(assets, "splash.png" if scale == 100 else f"splash_{scale}.png")


def tcl_images(assets):
    """Tcl-Zeilen mit den Bildern je Skalierung (Base64-PNG), fehlende werden ausgelassen."""
    lines = []
    for scale in SCALES[1:]:
        path = image_path(assets, scale)
        if os.path.exists(path):
            with open(path, "rb") as f:
                lines.append(f"set zz_img({scale}) {{{base64.b64encode(f.read()).decode()}}}")
    return "\n".join(lines) or "array set zz_img {}"


def tcl_text(total_files, assets=None):
    """Tcl-Teil für Text und Balken; total_files = Zahl der Dateien, die die EXE entpackt,
    assets = Ordner mit den Startbildern je Skalierung (None: nur 100 %)."""
    x0, y0, x1, y1 = BAR
    images = tcl_images(assets) if assets else "array set zz_img {}"
    return _TCL.format(images=images, x0=x0, y0=y0, x1=x1, y1=y1, tx=TEXT_POS[0], ty=TEXT_POS[1],
                       text_px=TEXT_PX, bar=BAR_COLOR, track=TRACK_COLOR,
                       extract=EXTRACT_SHARE, total=max(1, int(total_files)))


def install(total_files, assets=None):
    """Beim Bauen (ZeitZeuge.spec) vor Splash(...) aufrufen."""
    from PyInstaller.building import splash_templates
    splash_templates.splash_canvas_text = tcl_text(total_files, assets)


_DPI_SETTINGS = (
    '<dpiAware xmlns="http://schemas.microsoft.com/SMI/2005/WindowsSettings">true/pm</dpiAware>'
    '<dpiAwareness xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">'
    'PerMonitorV2, PerMonitor</dpiAwareness>')


def manifest():
    """Manifest der EXE: wie PyInstallers Standard, dazu DPI-bewusst pro Bildschirm (wie Qt 6).

    So gilt von Anfang an dieselbe Einstellung für Startbild und Qt; nichts schaltet mehr um."""
    from PyInstaller.utils.win32 import winmanifest
    xml = winmanifest._DEFAULT_MANIFEST_XML.decode("utf-8")
    marker = "<windowsSettings>"
    assert marker in xml, "PyInstaller-Manifest ohne windowsSettings"
    return xml.replace(marker, marker + _DPI_SETTINGS, 1)


def step(percent, text):
    """Fortschritt im Startbild: Balken auf percent (0–100), darunter text."""
    try:
        import pyi_splash
        if pyi_splash.is_alive():
            pyi_splash.update_text(f"{max(0, min(100, int(percent)))}|{text}")
    except Exception:  # Quelltext-Start oder Startbild schon zu: nicht wichtig
        pass


def step_on_top(percent, text):
    """Wie step, und das Startbild kommt in den Vordergrund (über das Hauptfenster)."""
    step(percent, text)
    try:
        import pyi_splash
        if pyi_splash.is_alive():
            pyi_splash.update_text(f"!{max(0, min(100, int(percent)))}|{text}")
    except Exception:
        pass


def close_when_painted(window, calm_ms=600, fallback_ms=20000):
    """Startbild erst schließen, wenn das Hauptfenster sein erstes Bild gemalt hat und Qt danach
    calm_ms lang ohne Stocken Ereignisse verarbeitet. Bis dahin bleibt das Fenster durchsichtig.
    Spätestens nach fallback_ms ist alles sichtbar. Ohne Startbild (Quelltext) wird nur gezeigt."""
    import time
    from PySide6.QtCore import QEvent, QObject, QTimer
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    state = {"done": False, "calm": 0.0, "last": None}
    try:
        import pyi_splash
        has_splash = pyi_splash.is_alive()
    except Exception:
        has_splash = False

    def finish():
        if state["done"]:
            return
        state["done"] = True
        app.removeEventFilter(watch)
        ticker.stop()
        window.setWindowOpacity(1.0)
        close()

    def tick():
        now = time.monotonic()
        if state["last"] is not None:
            gap = now - state["last"]
            state["calm"] = state["calm"] + gap if gap < 0.25 else 0.0  # gestockt: neu zählen
        state["last"] = now
        if state["calm"] * 1000 >= calm_ms:
            finish()

    class _Painted(QObject):
        def eventFilter(self, obj, event):
            if event.type() == QEvent.Paint and obj.isWidgetType() and obj.window() is window:
                app.removeEventFilter(self)
                ticker.start()
            return False
    watch = _Painted(window)
    ticker = QTimer(window)
    ticker.setInterval(50)
    ticker.timeout.connect(tick)
    if not has_splash:
        window.show()
        return
    step_on_top(97, "Fenster zeichnen …")
    window.setWindowOpacity(0.0)
    app.installEventFilter(watch)
    QTimer.singleShot(fallback_ms, finish)
    window.show()


def close():
    """Startbild schließen: sobald das Fenster steht oder eine Rückfrage kommt."""
    try:
        import pyi_splash
        if pyi_splash.is_alive():
            pyi_splash.close()
    except Exception:
        pass
