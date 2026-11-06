"""Startbild der EXE (assets/splash.png und splash_<prozent>.png) aus dem Logo erzeugen.

Aufruf:  python tests/make_splash.py
Je Bildschirmskalierung (splash_screen.SCALES, z. B. 125 %, 150 %) ein eigenes, scharfes Bild:
Die EXE ist DPI-bewusst, Windows vergrößert das Startbild also nicht mehr selbst.
PyInstaller zeigt das Bild sofort beim Start der EXE, noch während sie sich entpackt
(ZeitZeuge.spec, Splash). Unten zeichnet das Startbild Text und Ladebalken
(src/splash_screen.py), deshalb bleibt dort Platz.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPen
from PySide6.QtSvg import QSvgRenderer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import splash_screen  # noqa: E402

W, H = splash_screen.SIZE


def render(scale):
    """Startbild für eine Skalierung in Prozent (100 = 420 × 170)."""
    s = scale / 100
    img = QImage(round(W * s), round(H * s), QImage.Format_RGB32)
    img.fill(QColor("#FFFFFF"))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    p.scale(s, s)
    p.setPen(QPen(QColor("#E4E4E7"), 2))
    p.drawRect(QRectF(1, 1, W - 2, H - 2))
    QSvgRenderer(os.path.join(ROOT, "assets", "zeitzeuge.svg")).render(p, QRectF(26, 26, 72, 72))
    title = QFont("Inter", 22)
    title.setBold(True)
    p.setFont(title)
    p.setPen(QColor("#18181B"))
    p.drawText(QRectF(118, 30, W - 130, 36), Qt.AlignLeft | Qt.AlignVCenter, "Zeitzeuge")
    p.setFont(QFont("Inter", 10))
    p.setPen(QColor("#62626B"))
    p.drawText(QRectF(118, 66, W - 130, 24), Qt.AlignLeft | Qt.AlignVCenter,
               "Tages-Timeline deiner Arbeitsspuren")
    p.setPen(QPen(QColor("#E4E4E7"), 1))
    p.drawLine(26, 120, W - 26, 120)
    p.end()
    return img


def main():
    app = QGuiApplication(sys.argv)  # noqa: F841 (Schriften brauchen eine Anwendung)
    for scale in splash_screen.SCALES:
        out = splash_screen.image_path(os.path.join(ROOT, "assets"), scale)
        render(scale).save(out)
        print(out)


if __name__ == "__main__":
    main()
