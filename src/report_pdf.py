"""Tages- und Wochenbericht als PDF (Qt-Teil zu work_report.py).

collect_day sammelt mit den Daten des Hauptfensters (Personalzeit, Tätigkeiten, Matrix42,
Spuren), draw_chart zeichnet den Zeitgraph (druckfreundlich, helle Flächen, auch in
Graustufen unterscheidbar), write_pdf schreibt das Dokument mit Fußzeile „Seite x von y“,
save_report fragt nach dem Speicherort und öffnet das PDF danach.
"""
import os
from datetime import datetime

from PySide6.QtCore import QDate, QMarginsF, QPointF, QRectF, QSizeF, QStandardPaths, Qt, QUrl
from PySide6.QtGui import (QBrush, QColor, QDesktopServices, QFont, QFontMetricsF, QImage,
                           QPageLayout, QPageSize, QPainter, QPdfWriter, QPen, QTextDocument)
from PySide6.QtWidgets import QFileDialog, QMessageBox

import booking_rate as br
import safe_io
import work_report

MARGIN_MM = 14
FOOTER_PT = 18
CHART_DPI = 300
# Balken im Zeitgraph: (Füllung, Rand, Schrift, gestrichelt). Hell genug für Text, in Graustufen
# unterscheidbar: Personalzeit hellgrau, Buchung blau, Lücke weiß mit rotem Strichrand,
# Tätigkeit gebucht grün, nicht gebucht orange mit dunklem Rand
# Ränder = work_report.STATUS_COLORS, dieselben Farben wie in der Timeline
_C = work_report.STATUS_COLORS
STYLES = {
    "personal": ("#e3e3e3", _C["personal"], "#000000", False),
    "booking": ("#9cc3e6", _C["booking"], "#0b2740", False),
    "gap": ("#ffffff", _C["gap"], "#a0281c", True),
    "doc_booked": ("#a8d5b5", _C["doc_booked"], "#0d3a1e", False),
    "doc_missing": ("#f5c58f", _C["doc_missing"], "#4a2600", False),
    "doc_unknown": ("#dddddd", "#777777", "#000000", False),
    "trace": ("#cfd8e3", "#7d8fa3", "#1c2733", False),
}
LEGEND = (("personal", "Personalzeit"), ("booking", "In Matrix42 gebucht"),
          ("gap", "Ohne Matrix42-Buchung"), ("doc_booked", "Tätigkeit in Matrix42 gebucht"),
          ("doc_missing", "Tätigkeit nicht in Matrix42 gebucht"), ("trace", "Aufgezeichnete Spur"))


def _font(points, bold=False):
    font = QFont("Segoe UI")
    font.setPointSizeF(points)
    font.setBold(bold)
    return font


def image_device():
    """Ein Bild mit CHART_DPI, damit Schriftmaße beim Planen so sind wie beim Zeichnen."""
    image = QImage(4, 4, QImage.Format_ARGB32)
    image.setDotsPerMeterX(int(CHART_DPI / 0.0254))
    image.setDotsPerMeterY(int(CHART_DPI / 0.0254))
    return image


def _legend_lines(metrics, avail, px, week=False):
    """Legende auf Zeilen verteilt: [[(x, Stil oder None, Text)]]."""
    items = [(style, text) for style, text in LEGEND if not (week and style == "trace")]
    if week:
        items.append((None, "Woche: oben Matrix42, unten Tätigkeiten"))
    lines, line, x = [], [], 0.0
    for style, text in items:
        need = (11 * px if style else 0) + metrics.horizontalAdvance(text)
        if line and x + need > avail:
            lines.append(line)
            line, x = [], 0.0
        line.append((x, style, text))
        x += need + 8 * px
    if line:
        lines.append(line)
    return lines


def draw_chart(data, width):
    """Zeitgraph (work_report.chart / week_chart) als Bild, width Pixel bei CHART_DPI."""
    px = CHART_DPI / 72  # Pixel je Punkt
    week = data.get("week")
    label_w = width * (0.11 if week else 0.15)
    row_h = (17 if week else 15) * px
    head_h = 12 * px
    rows = data["rows"]
    p_font = _font(6.5)
    legend_lines = _legend_lines(QFontMetricsF(p_font, image_device()), width - label_w,
                                 px, data.get("week"))
    legend_h = (4 + 10 * len(legend_lines)) * px
    height = int(head_h + row_h * len(rows) + legend_h + 4 * px)
    image = QImage(int(width), height, QImage.Format_ARGB32)
    image.setDotsPerMeterX(int(CHART_DPI / 0.0254))
    image.setDotsPerMeterY(int(CHART_DPI / 0.0254))
    image.fill(QColor("#ffffff"))
    p = QPainter(image)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    start, end = data["start"], data["end"]
    total = max((end - start).total_seconds(), 60)
    plot_w = width - label_w - 12 * px  # rechts Platz für die letzte Stundenbeschriftung

    def x_of(when):
        return label_w + max(0.0, min(1.0, (when - start).total_seconds() / total)) * plot_w

    # Stunden: Beschriftung oben, feine Linien über alle Zeilen
    p.setFont(_font(6.5))
    hours = int(total // 3600)
    step = 1 if hours <= 12 else 2
    first_hour = start.replace(minute=0, second=0)
    for k in range(0, hours + 1, step):
        when = first_hour.__class__.fromtimestamp(first_hour.timestamp() + k * 3600)
        if when < start or when > end:
            continue
        x = x_of(when)
        p.setPen(QPen(QColor("#c8c8c8"), 0.5 * px))
        p.drawLine(QPointF(x, head_h - 2 * px), QPointF(x, head_h + row_h * len(rows)))
        p.setPen(QColor("#444444"))
        p.drawText(QRectF(x - 20 * px, 0, 40 * px, head_h - 3 * px), Qt.AlignHCenter | Qt.AlignBottom,
                   f"{when:%H}:00")

    for n, (name, bars) in enumerate(rows):
        top = head_h + n * row_h
        if n % 2:
            p.fillRect(QRectF(0, top, width, row_h), QColor("#f7f7f7"))
        p.setPen(QPen(QColor("#dddddd"), 0.5 * px))
        p.drawLine(QPointF(0, top + row_h), QPointF(width, top + row_h))
        p.setPen(QColor("#000000"))
        p.setFont(_font(7, bold=name in ("Matrix42", "Tätigkeiten")))
        p.drawText(QRectF(1 * px, top, label_w - 3 * px, row_h), Qt.AlignVCenter | Qt.AlignLeft, name)
        for bar in sorted(bars, key=lambda b: b["style"] != "personal"):  # Personalzeit zuunterst
            lane = bar.get("lane", "full")
            pad = 2 * px
            y, h = top + pad, row_h - 2 * pad
            if lane == "top":
                h = (row_h - 2 * pad) / 2 - 0.5 * px
                y = top + pad
            elif lane == "bottom":
                h = (row_h - 2 * pad) / 2 - 0.5 * px
                y = top + row_h / 2 + 0.5 * px
            elif week and bar["style"] == "personal":
                y, h = top + 1 * px, row_h - 2 * px
            x1, x2 = x_of(bar["start"]), x_of(bar["end"])
            if x2 - x1 < 1.2 * px:
                x2 = x1 + 1.2 * px
            fill, border, ink, dashed = STYLES.get(bar["style"], STYLES["trace"])
            rect = QRectF(x1, y, x2 - x1, h)
            pen = QPen(QColor(border), (0.9 if dashed else 0.6) * px)
            if dashed:
                pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.setBrush(QBrush(QColor(fill)))
            p.drawRoundedRect(rect, 1.2 * px, 1.2 * px)
            text = bar.get("text") or ""
            if text and lane == "full" and not week:
                p.setFont(_font(6))
                metrics = QFontMetricsF(p.font())
                inner = rect.adjusted(1.5 * px, 0, -1.5 * px, 0)
                if inner.width() > metrics.horizontalAdvance("Abc"):
                    p.setPen(QColor(ink))
                    p.drawText(inner, Qt.AlignVCenter | Qt.AlignLeft,
                               metrics.elidedText(text, Qt.ElideRight, inner.width()))

    # Legende, bei Bedarf in mehreren Zeilen
    p.setFont(p_font)
    y = head_h + row_h * len(rows) + 4 * px
    for line in legend_lines:
        for x, style, text in line:
            if style:
                fill, border, _ink, dashed = STYLES[style]
                pen = QPen(QColor(border), 0.7 * px)
                if dashed:
                    pen.setStyle(Qt.DashLine)
                p.setPen(pen)
                p.setBrush(QBrush(QColor(fill)))
                p.drawRoundedRect(QRectF(label_w + x, y + 1.5 * px, 9 * px, 6 * px), 1 * px, 1 * px)
                x += 11 * px
            p.setPen(QColor("#333333"))
            p.drawText(QPointF(label_w + x, y + 7 * px), text)
        y += 10 * px
    p.end()
    return image


def _traces(window, date):
    """Spuren des Tages: alle Quellen der Timeline und die Arbeitsblöcke am PC."""
    found = []
    timeline = getattr(window, "timeline", None)
    if timeline is not None:
        try:
            found += timeline.activities_for(date)
        except Exception:  # eine kaputte Quelle darf den Bericht nicht verhindern
            safe_io.report("Bericht: Spuren nicht lesbar")
    blocks = getattr(window, "_pc_focus_blocks", None)
    if blocks is not None:
        try:
            found += [dict(b, customer_name=b.get("customer_name") or b.get("label") or "") for b in blocks(date)]
        except Exception:
            safe_io.report("Bericht: PC-Arbeitsblöcke nicht lesbar")
    return found


def collect_day(window, date_str, now=None, with_traces=True):
    """Bericht eines Tages (work_report.build_day) mit den Daten des Hauptfensters."""
    import week_dialogs  # lädt main_timeline-Teile; erst hier
    now = now or datetime.now()
    inputs = week_dialogs.day_inputs(window, date_str, now)
    journal = getattr(window, "journal", None)
    docs = journal.items(date_str) if journal is not None else []
    traces = _traces(window, QDate.fromString(date_str, "yyyy-MM-dd")) if with_traces else []
    return work_report.build_day(
        date_str, inputs["spans"], docs, inputs["bookings"], traces, from_itm=inputs["from_itm"],
        now=now, gap_minutes=window.config.get("m42_gap_minutes", 5),
        itm_day=inputs["itm_day"], running=inputs["running"])


def collect_week(window, date_str, now=None, with_traces=True):
    """Montag bis Freitag der Woche von date_str, Samstag/Sonntag nur mit Inhalt; nichts nach heute."""
    now = now or datetime.now()
    today = now.strftime("%Y-%m-%d")
    days = []
    for k, d in enumerate(br.week_dates(date_str)):
        if d > today:
            break
        day = collect_day(window, d, now, with_traces)
        if k < 5 or work_report.has_content(day):
            days.append(day)
    return days


def person(window):
    return (window.config.get("report_name") or window.config.get("m42_own_name") or "").strip()


def write_pdf(html, path, title="", charts=None):
    """HTML (work_report.document) als A4-PDF mit Fußzeile schreiben.

    charts: {Bildname: Zeitgraph} aus work_report.charts_for, als Bilder in voller Breite."""
    writer = QPdfWriter(path)
    writer.setTitle(title)
    writer.setCreator("Zeitzeuge")
    writer.setPageLayout(QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Portrait,
                                     QMarginsF(MARGIN_MM, MARGIN_MM, MARGIN_MM, MARGIN_MM),
                                     QPageLayout.Millimeter))
    writer.setResolution(300)
    painter = QPainter()
    if not painter.begin(writer):
        raise OSError(f"PDF lässt sich nicht schreiben: {path}")
    try:
        dpi = writer.resolution()
        page = writer.pageLayout().paintRectPixels(dpi)
        footer = FOOTER_PT * dpi / 72
        doc = QTextDocument()
        doc.documentLayout().setPaintDevice(writer)  # Schrift in Punkt passend zur Auflösung
        font = QFont("Segoe UI")
        font.setPointSizeF(8.5)
        doc.setDefaultFont(font)
        width = int(page.width() - 2 * doc.documentMargin() - 2)  # Bild in voller Textbreite
        for name, data in (charts or {}).items():
            doc.addResource(QTextDocument.ImageResource, QUrl(name), draw_chart(data, width))
        # <img width> zählt in Pixeln bei 96 dpi, gezeichnet wird mit der Auflösung des PDF
        doc.setHtml(html.replace("__CHART_WIDTH__", str(int(width * 96 / dpi))))
        doc.setPageSize(QSizeF(page.width(), page.height() - footer))
        count = doc.pageCount()
        height = doc.pageSize().height()
        small = QFont("Segoe UI")
        small.setPointSizeF(7)
        for n in range(count):
            if n:
                writer.newPage()
            painter.save()
            painter.translate(0, -n * height)
            doc.drawContents(painter, QRectF(0, n * height, page.width(), height))
            painter.restore()
            painter.setFont(small)
            text = f"{title} · Seite {n + 1} von {count}" if title else f"Seite {n + 1} von {count}"
            painter.drawText(QPointF(0, page.height() - footer * 0.25), text)
    finally:
        painter.end()
    return path


def _default_dir(window):
    folder = window.config.get("report_dir") or ""
    if folder and os.path.isdir(folder):
        return folder
    return QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation) or os.path.expanduser("~")


def save_report(window, date_str=None, week=False, parent=None, path=None, open_after=True):
    """Bericht erstellen, Speicherort wählen (oder path), PDF schreiben und öffnen. -> Pfad oder None."""
    parent = parent or window
    if date_str is None:
        date_str = window.current_date.toString("yyyy-MM-dd")
    now = datetime.now()
    with_traces = window.config.get("report_traces", True)
    days = collect_week(window, date_str, now, with_traces) if week else \
        [collect_day(window, date_str, now, with_traces)]
    if not days:
        QMessageBox.information(parent, "Bericht als PDF", "Für diese Woche gibt es noch keine Tage.")
        return None
    name = work_report.file_name(days, week)
    if path is None:
        path, _filter = QFileDialog.getSaveFileName(
            parent, "Wochenbericht speichern" if week else "Tagesbericht speichern",
            os.path.join(_default_dir(window), name), "PDF (*.pdf)")
        if not path:
            return None
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        window.config["report_dir"] = os.path.dirname(path)
        try:
            import main_timeline as mt
            mt.save_config(window.config)
        except Exception:  # Ordner merken ist nur Komfort
            pass
    title = name[:-4].replace("_", " ")
    try:
        write_pdf(work_report.document(days, week, person(window), with_traces, now, charts=True), path,
                  title, work_report.charts_for(days, week))
    except OSError as e:
        QMessageBox.warning(parent, "Bericht als PDF", f"Das PDF ließ sich nicht speichern:\n{e}")
        return None
    if hasattr(window, "statusBar"):
        window.statusBar().showMessage(f"Bericht gespeichert: {path}", 8000)
    if open_after:
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
    return path

