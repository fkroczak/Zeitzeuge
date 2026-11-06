"""Startbild der EXE (assets/splash.png) aus dem Logo erzeugen.

Aufruf:  python tests/make_splash.py
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
W, H = 420, 170


def main():
    app = QGuiApplication(sys.argv)  # noqa: F841 (Schriften brauchen eine Anwendung)
    img = QImage(W, H, QImage.Format_RGB32)
    img.fill(QColor("#FFFFFF"))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
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
    out = os.path.join(ROOT, "assets", "splash.png")
    img.save(out)
    print(out)


if __name__ == "__main__":
    main()
