"""Startbild der EXE: das Tcl-Skript, das PyInstaller daraus baut, läuft durch.

Bricht das Skript ab (z. B. Schriftname mit Leerzeichen ohne Klammern), bleibt beim Start nur ein
leeres Fenster „tk“ stehen. Der Test baut das Skript wie ZeitZeuge.spec und führt es in Tk aus.
Ohne PyInstaller oder Tk (z. B. Linux ohne Bildschirm) wird er übersprungen.
"""
import os
import re
import sys
import tempfile
import time

import pytest

import splash_screen

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOTAL = 40  # Dateien, die die EXE im Test „entpackt“


def spec_value(name):
    """Wert eines Splash-Arguments aus ZeitZeuge.spec, z. B. text_font."""
    with open(os.path.join(ROOT, "ZeitZeuge.spec"), encoding="utf-8") as f:
        m = re.search(rf"^\s*{name}=(.+?),\s*(#.*)?$", f.read(), re.M)
    assert m, f"{name} fehlt in ZeitZeuge.spec"
    return eval(m.group(1))  # nur Literale aus der eigenen spec


def build_script(assets=None):
    """Tcl-Skript wie beim Bauen (ZeitZeuge.spec → Splash.generate_script)."""
    splash_mod = pytest.importorskip("PyInstaller.building.splash")
    splash_screen.install(TOTAL, assets)
    s = object.__new__(splash_mod.Splash)  # nur generate_script, ohne Tcl/Tk-Suche beim Bauen
    s.text_pos = spec_value("text_pos")
    s.text_size = spec_value("text_size")
    s.text_font = spec_value("text_font")
    s.text_color = spec_value("text_color")
    s.text_default = spec_value("text_default")
    s.always_on_top = spec_value("always_on_top")
    s.minify_script = True
    s.script_name = os.path.join(tempfile.mkdtemp(prefix="zz-splash-"), "splash.tcl")
    return s.generate_script()


def test_font_name_protected():
    font = spec_value("text_font")
    assert " " not in font or (font.startswith("{") and font.endswith("}")), font


@pytest.fixture
def tk_root():
    tkinter = pytest.importorskip("tkinter")
    try:
        root = tkinter.Tk()
    except tkinter.TclError as e:  # kein Bildschirm
        pytest.skip(f"Tk nicht verfügbar: {e}")
    yield root
    root.destroy()


def pump(root, seconds):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.01)


def test_script_runs_with_progress(tk_root):
    tk_root.tk.call("tk", "scaling", 96 / 72)  # 100 %
    script = build_script(os.path.join(ROOT, "assets"))
    w, h = 420, 170
    # Bilddaten wie im Bootloader, hier als weiße Fläche in Bildgröße
    row = "{" + " ".join(["#ffffff"] * w) + "}"
    tk_root.tk.call("set", "_image_data", " ".join([row] * h))
    tk_root.tk.eval(script)  # bricht das Skript ab, gibt es hier einen TclError

    # Ende erreicht: Fenster ohne Rahmen (unter Linux nimmt PyInstaller einen anderen Weg)
    if sys.platform in ("win32", "darwin"):
        assert tk_root.tk.eval("wm overrideredirect .") == "1"
    canvas = ".root.canvas"
    text = lambda: tk_root.tk.eval(f"{canvas} itemcget vartext -text")
    bar_end = lambda: float(tk_root.tk.eval(f"{canvas} coords zz_bar").split()[2])
    x0, _y0, x1, _y1 = splash_screen.BAR
    assert text() == spec_value("text_default")

    # Entpacken: der Bootloader schreibt Dateinamen
    for i in range(TOTAL // 2):
        tk_root.tk.call("set", "status_text", f"datei{i}.dll")
    assert text() == "Programm entpacken …"
    goal = float(tk_root.tk.eval("set zz_goal"))
    assert goal == pytest.approx(splash_screen.EXTRACT_SHARE / 2)
    pump(tk_root, 0.6)
    assert x0 < bar_end() <= x0 + (x1 - x0) * (goal + 8) / 100 + 0.01

    # Schritte von Zeitzeuge: Prozent|Text, der Balken holt auf
    tk_root.tk.call("set", "status_text", "84|Fenster aufbauen …")
    assert text() == "Fenster aufbauen …"
    pump(tk_root, 0.8)
    assert bar_end() >= x0 + (x1 - x0) * 0.84 - 0.01
    assert bar_end() <= x1

    # Ein kleinerer Wert setzt den Balken nicht zurück
    tk_root.tk.call("set", "status_text", "60|Später …")
    assert float(tk_root.tk.eval("set zz_goal")) == 84


def test_bild_je_skalierung(tk_root):
    """Bei 150 % nimmt das Startbild das größere Bild, mittig, Balken und Text wachsen mit."""
    tk_root.tk.call("tk", "scaling", 1.5 * 96 / 72)
    script = build_script(os.path.join(ROOT, "assets"))
    with open(os.path.join(ROOT, "assets", "splash.png"), "rb") as f:
        tk_root.tk.call("set", "_image_data", f.read())  # wie der Bootloader: PNG-Daten
    tk_root.tk.eval(script)
    w, h = splash_screen.SIZE
    assert tk_root.tk.eval("set zz_s") == "150"
    assert (int(tk_root.tk.eval("image width splash_image")),
            int(tk_root.tk.eval("image height splash_image"))) == (round(w * 1.5), round(h * 1.5))
    x0, y0, x1, y1 = splash_screen.BAR
    coords = [float(v) for v in tk_root.tk.eval(".root.canvas coords zz_track").split()]
    assert coords == [round(x0 * 1.5), round(y0 * 1.5), round(x1 * 1.5), round(y1 * 1.5)]
    width = float(tk_root.tk.eval("set display_width"))
    assert float(tk_root.tk.eval("set x_position")) == pytest.approx((width - w * 1.5) / 2, abs=1)


def test_bilder_fuer_alle_skalierungen():
    for scale in splash_screen.SCALES:
        assert os.path.exists(splash_screen.image_path(os.path.join(ROOT, "assets"), scale)), scale


def test_manifest_dpi_bewusst():
    """EXE ist DPI-bewusst wie Qt, sonst springt das Startbild beim Start von Qt."""
    pytest.importorskip("PyInstaller")
    from PyInstaller.utils.win32 import winmanifest
    xml = winmanifest.create_application_manifest(splash_screen.manifest()).decode()
    assert "PerMonitorV2" in xml and "true/pm" in xml and "longPathAware" in xml
    assert "Microsoft.Windows.Common-Controls" in xml
