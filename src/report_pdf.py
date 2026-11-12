"""Tages- und Wochenbericht als PDF (Qt-Teil zu work_report.py).

collect_day sammelt mit den Daten des Hauptfensters (Personalzeit, Tätigkeiten, Matrix42,
Spuren), write_pdf schreibt das Dokument mit Fußzeile „Seite x von y“, save_report fragt
nach dem Speicherort und öffnet das PDF danach.
"""
import os
from datetime import datetime

from PySide6.QtCore import QDate, QMarginsF, QPointF, QRectF, QSizeF, QStandardPaths, QUrl
from PySide6.QtGui import (QDesktopServices, QFont, QPageLayout, QPageSize, QPainter, QPdfWriter,
                           QTextDocument)
from PySide6.QtWidgets import QFileDialog, QMessageBox

import booking_rate as br
import safe_io
import work_report

MARGIN_MM = 14
FOOTER_PT = 18


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


def write_pdf(html, path, title=""):
    """HTML (work_report.document) als A4-PDF mit Fußzeile schreiben."""
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
        doc.setHtml(html)
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
        write_pdf(work_report.document(days, week, person(window), with_traces, now), path, title)
    except OSError as e:
        QMessageBox.warning(parent, "Bericht als PDF", f"Das PDF ließ sich nicht speichern:\n{e}")
        return None
    if hasattr(window, "statusBar"):
        window.statusBar().showMessage(f"Bericht gespeichert: {path}", 8000)
    if open_after:
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
    return path

