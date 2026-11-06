"""Layout prüfen: abgeschnittene Texte und unnötige Scrollleisten bei kleiner Fenstergröße und Hi-DPI.

Aufruf:  python tests/layout_check.py [Zielordner für Bilder] [Skalierung, z. B. 1.5]
Ohne Skalierung läuft das Skript nacheinander für 1.0, 1.5 und 2.0 (je ein eigener Prozess,
QT_SCALE_FACTOR wirkt nur beim Start). Kein Test (läuft nicht in pytest), sondern ein Werkzeug
wie start_bench.py: es meldet Befunde und speichert Bilder, blockiert aber nichts.

Qt rechnet in logischen Pixeln: bei 150/200 % wird alles gleichmäßig größer, der Platz aber
knapper. Deshalb prüft das Skript zusätzlich, ob jedes Fenster auf 960 × 540 logische Pixel passt
(Full HD bei 200 %). Geprüft werden Hauptfenster (groß und klein), alle Seiten der Einstellungen (Mindestgröße)
und die wichtigsten Dialoge in ihrer Startgröße:
  - Label ohne Zeilenumbruch, dessen Text breiter ist als das Label (abgeschnitten),
  - Knopf, dessen Text breiter ist als der Knopf,
  - sichtbare horizontale Scrollleiste in Scrollbereichen und Listen.
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(tempfile.gettempdir(), "zz-layout"))
SCALES = ["1.0", "1.5", "2.0"]
# Kleinster sinnvoller Bildschirm in logischen Pixeln: Full HD mit 200 % Windows-Anzeige
SCREEN = (960, 540)


def run_all():
    total = {}
    for scale in SCALES:
        env = dict(os.environ, QT_SCALE_FACTOR=scale, QT_QPA_PLATFORM="offscreen",
                   PYTHONIOENCODING="utf-8")
        out = subprocess.run([sys.executable, os.path.abspath(__file__), OUT, scale],
                             env=env, capture_output=True, text=True, encoding="utf-8")
        lines = [ln for ln in out.stdout.splitlines() if ln.startswith("{")]
        if out.returncode != 0 or not lines:
            print(f"Skalierung {scale}: Fehler\n{out.stdout}\n{out.stderr}")
            continue
        total[scale] = json.loads(lines[-1])
    for scale, found in total.items():
        print(f"\n== Skalierung {float(scale):.0%} ({sum(len(v) for v in found.values())} Befunde)")
        for area, items in found.items():
            for item in items:
                print(f"  [{area}] {item}")
    print(f"\nBilder: {OUT}")


def run_one(scale):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["ZEITZEUGE_DATA"] = tempfile.mkdtemp(prefix="zz-layout-")
    sys.path.insert(0, os.path.join(ROOT, "src"))
    import main_timeline  # setzt Hi-DPI-Rundung vor QApplication
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtWidgets import (QAbstractButton, QAbstractScrollArea, QApplication, QLabel,
                                   QPushButton, QToolButton)

    app = QApplication(sys.argv)
    app.setStyle(main_timeline.AppStyle())
    found = {}
    folder = os.path.join(OUT, f"{float(scale):.0%}".replace("%", ""))
    os.makedirs(folder, exist_ok=True)

    def check(area, root):
        items = found.setdefault(area, [])
        for w in root.findChildren(QLabel):
            if not w.isVisibleTo(root) or w.wordWrap() or w.width() <= 0:
                continue
            if w.textFormat() == Qt.RichText or "<" in w.text() or not w.text().strip():
                continue
            if w.pixmap() is not None and not w.pixmap().isNull():
                continue
            if type(w).__name__ == "_ElidedLabel":  # kürzt absichtlich mit „…“ und Tooltip
                continue
            need = QFontMetrics(w.font()).horizontalAdvance(w.text().split("\n")[0].replace("&", ""))
            m = w.contentsMargins()
            if need > w.width() - m.left() - m.right() + 1:
                items.append(f"Label abgeschnitten: '{w.text()[:50]}' braucht {need} px, hat {w.width()} px")
        for w in root.findChildren(QAbstractButton):
            if not w.isVisibleTo(root) or not w.text() or not isinstance(w, (QPushButton, QToolButton)):
                continue
            if isinstance(w, QToolButton) and w.toolButtonStyle() == Qt.ToolButtonIconOnly:
                continue
            need = QFontMetrics(w.font()).horizontalAdvance(w.text().replace("&", ""))
            if need > w.width():
                items.append(f"Knopf abgeschnitten: '{w.text()[:40]}' braucht {need} px, hat {w.width()} px")
        for w in root.findChildren(QAbstractScrollArea):
            bar = w.horizontalScrollBar()
            if w.isVisibleTo(root) and bar.isVisible() and bar.maximum() > 0 \
                    and not w.inherits("QGraphicsView"):  # Timeline scrollt absichtlich
                items.append(f"horizontale Scrollleiste in {type(w).__name__} '{w.objectName()}' "
                             f"({bar.maximum()} px zu breit)")
        # Passt das Fenster auf den kleinsten Bildschirm (Full HD bei 200 % = 960 × 540 logische px)?
        hint = root.minimumSizeHint().expandedTo(root.minimumSize())
        if hint.width() > SCREEN[0] or hint.height() > SCREEN[1]:
            items.append(f"Mindestgröße {hint.width()} × {hint.height()} passt nicht auf {SCREEN[0]} × {SCREEN[1]}")
        if not items:
            found.pop(area)

    def settle():
        for _ in range(5):
            app.processEvents()

    def shot(name, widget):
        settle()
        widget.grab().save(os.path.join(folder, f"{name}.png"))

    window = main_timeline.TimelineApp()
    for name, (w, h) in {"hauptfenster_gross": (1440, 900), "hauptfenster_klein": SCREEN}.items():
        window.resize(w, h)
        window.show()
        settle()
        check(name, window)
        shot(name, window)

    window.show_settings()
    sw = window._settings_window
    sw.resize(sw.minimumSize())
    for key in list(sw.pages):
        sw.show_page(key)
        settle()
        check(f"einstellungen/{key}", sw)
        shot(f"einstellungen_{key}", sw)
    sw.hide()

    import journal_dialogs
    import settings_dialogs
    import customers_dialogs
    import week_dialogs
    from datetime import datetime as dt
    config = window.config
    dialogs = {
        "arbeitszeiten": lambda: settings_dialogs.WorkHoursDialog(config, window),
        "regeln": lambda: settings_dialogs.RulesDialog(config, window),
        "fenster_filter": lambda: settings_dialogs.TrackingFilterDialog(config, main_timeline.ACTIVITY_DIR, window),
        "eintragen": lambda: journal_dialogs.EntryDialog(
            dt(2026, 10, 20, 9), dt(2026, 10, 20, 9, 30), ["Musterkunde GmbH"], ["Fernwartung"],
            parent=window),
        "kunden": lambda: customers_dialogs.CustomersDialog(config, window),
        "wochenabschluss": lambda: week_dialogs.WeekDialog(window, window.current_date.toString("yyyy-MM-dd")),
    }
    for name, make in dialogs.items():
        try:
            d = make()
        except Exception as exc:  # noqa: BLE001 – Werkzeug: Befund statt Abbruch
            found.setdefault(name, []).append(f"nicht geöffnet: {exc}")
            continue
        d.show()
        settle()
        check(f"dialog/{name}", d)
        shot(f"dialog_{name}", d)
        d.hide()

    print(json.dumps(found, ensure_ascii=False))
    sys.stdout.flush()
    os._exit(0)  # wie in den Testskripten: Qt räumt unter Windows beim Beenden sporadisch falsch auf


if __name__ == "__main__":
    if len(sys.argv) > 2:
        run_one(sys.argv[2])
    else:
        run_all()
