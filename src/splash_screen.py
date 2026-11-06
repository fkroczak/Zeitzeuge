"""Startbild der EXE mit Ladebalken (ZeitZeuge.spec, PyInstaller-Splash).

PyInstaller zeichnet das Startbild mit Tcl/Tk, schon während sich die EXE entpackt. Von sich aus
kann es nur eine Textzeile ändern. TCL_TEXT ersetzt beim Bauen den Textteil des Tcl-Skripts
(ZeitZeuge.spec) und zeichnet dazu einen Balken:
  - Beim Entpacken schreibt der Bootloader jeden Dateinamen ins Startbild. Daraus wird
    „Programm entpacken …“ und der Balken läuft bis EXTRACT_SHARE Prozent.
  - Danach meldet Zeitzeuge seine Schritte mit step(prozent, text).
Zwischen zwei Meldungen rückt der Balken langsam weiter, damit er nicht stehen bleibt.
Ohne Startbild (Start aus dem Quelltext) tun step und close nichts.
"""

EXTRACT_SHARE = 55  # Anteil des Balkens fürs Entpacken
BAR = (26, 154, 394, 158)  # x0, y0, x1, y1 im Bild (assets/splash.png, 420 × 170)
BAR_COLOR = "#0067C0"  # Blau aus dem Logo
TRACK_COLOR = "#E4E4E7"

# Ersetzt splash_templates.splash_canvas_text. Platzhalter %(…)s füllt PyInstaller,
# {total} und die Balkenmaße kommen aus tcl_text(). Keine Kommentare: PyInstaller kürzt das Skript.
_TCL = r"""
.root.canvas create text %(pad_x)d %(pad_y)d -fill %(color)s -justify left -font myFont -tag vartext -anchor sw
.root.canvas create rectangle {x0} {y0} {x1} {y1} -fill {track} -outline {{}} -tag zz_track
.root.canvas create rectangle {x0} {y0} {x0} {y1} -fill {bar} -outline {{}} -tag zz_bar
set zz_files 0
set zz_goal 0.0
set zz_shown 0.0
proc zz_status {{args}} {{
    global status_text zz_files zz_goal
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
    global zz_goal zz_shown
    if {{$zz_shown < $zz_goal}} {{
        set zz_shown [expr {{min($zz_goal, $zz_shown + max(0.5, ($zz_goal - $zz_shown) / 4.0))}}]
    }} elseif {{$zz_shown < min(97.0, $zz_goal + 8.0)}} {{
        set zz_shown [expr {{$zz_shown + 0.1}}]
    }}
    .root.canvas coords zz_bar {x0} {y0} [expr {{{x0} + ({x1} - {x0}) * $zz_shown / 100.0}}] {y1}
    after 40 zz_tick
}}
trace add variable status_text write zz_status
set status_text "0|%(default_text)s"
zz_tick
"""


def tcl_text(total_files):
    """Tcl-Teil für Text und Balken; total_files = Zahl der Dateien, die die EXE entpackt."""
    x0, y0, x1, y1 = BAR
    return _TCL.format(x0=x0, y0=y0, x1=x1, y1=y1, bar=BAR_COLOR, track=TRACK_COLOR,
                       extract=EXTRACT_SHARE, total=max(1, int(total_files)))


def install(total_files):
    """Beim Bauen (ZeitZeuge.spec) vor Splash(...) aufrufen."""
    from PyInstaller.building import splash_templates
    splash_templates.splash_canvas_text = tcl_text(total_files)


def step(percent, text):
    """Fortschritt im Startbild: Balken auf percent (0–100), darunter text."""
    try:
        import pyi_splash
        if pyi_splash.is_alive():
            pyi_splash.update_text(f"{max(0, min(100, int(percent)))}|{text}")
    except Exception:  # Quelltext-Start oder Startbild schon zu: nicht wichtig
        pass


def close():
    """Startbild schließen: sobald das Fenster steht oder eine Rückfrage kommt."""
    try:
        import pyi_splash
        if pyi_splash.is_alive():
            pyi_splash.close()
    except Exception:
        pass
