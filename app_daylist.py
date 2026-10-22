"""Hauptfenster: Tagesliste, Statuszeile und Blättern zwischen den Tagen.

Teil von TimelineApp (main_timeline.py), nur über main_timeline laden.
"""
from PySide6.QtCore import QDate, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QInputDialog, QHeaderView, QTableWidgetItem

from vpn_reader import vpn_sources
from journal import describe, ticket_line
from grouping import format_tv_id, work_blocks
from timeline_only import (ActivityViewDialog, ai_copy_text, entry_color, format_duration,
                           parse_time, type_label)
from theme import GERMAN
import main_timeline as mt  # Pfade und save_config zur Laufzeit von dort (Tests ersetzen sie dort)


class DayListMixin:
    # ---------------------- Tagesliste ----------------------------------------

    def update_day_list(self, activities, pc_activities=None):
        self.day_activities = activities
        self.pc_activities = pc_activities or []
        entries = list(activities)
        date_str = self.current_date.toString("yyyy-MM-dd")
        if self.config.get("list_view") == "ai":
            entries = self.ai_store.entries(date_str)
        elif self.config.get("list_view") == "doc":
            entries = self.doc_band(date_str)
        elif self.config.get("list_view") == "rules":
            entries = self.rule_band(date_str)
        elif self.config.get("list_view") == "blocks":
            entries = work_blocks(entries, self.config.get("block_gap_minutes", 10))
        elif self.config.get("show_pc_in_list", False):
            entries += self.pc_activities
        entries.sort(key=lambda a: a["start"])
        self.list_entries = entries

        # Spaltenbreiten beim Befüllen einfrieren: Mit "an Inhalt anpassen" misst Qt sonst nach
        # jeder Zelle alle Zeilen neu (bei vollem PC-Verlauf über 20 s, Fenster hängt)
        header = self.table.horizontalHeader()
        self.table.setUpdatesEnabled(False)
        for col in range(4):
            header.setSectionResizeMode(col, QHeaderView.Fixed)
        self.table.setRowCount(len(entries))
        for row, a in enumerate(entries):
            start, end = parse_time(a["start"]), parse_time(a["end"])
            pix = QPixmap(10, 10)
            if "app" in a:
                pix.fill(self.timeline.app_color(a["app"]))
            else:
                pix.fill(entry_color(a, self.config))
            type_item = QTableWidgetItem(QIcon(pix), type_label(a))
            values = [
                QTableWidgetItem(f"{start:%H:%M}"),
                QTableWidgetItem(f"{end:%H:%M}"),
                QTableWidgetItem(format_duration((end - start).total_seconds())),
                type_item,
                QTableWidgetItem(a.get("customer_name", "")),
                QTableWidgetItem(a.get("details", "")),
            ]
            for col, item in enumerate(values):
                item.setToolTip(item.text())
                self.table.setItem(row, col, item)
        for col in range(4):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)  # einmal messen
        self.table.setUpdatesEnabled(True)
        self.update_status_text()

    VIEWS = [("grouped", "Zusammengefasst"), ("single", "Einzeln"), ("blocks", "Arbeitsblöcke"),
             ("doc", "Dokumentation"), ("rules", "Regeln (ohne KI)"), ("ai", "KI-Vorschläge")]

    def change_view(self, key):
        self.config["list_view"] = key
        mt.save_config(self.config)
        self.update_view_button()
        self.timeline.draw_timeline(self.current_date)

    def name_teamviewer_id(self):
        row = self.table.currentRow()
        if not 0 <= row < len(self.list_entries):
            return
        tv_id = self.list_entries[row].get("tv_id")
        if not tv_id:
            self.statusBar().showMessage("Die markierte Zeile ist keine TeamViewer-Verbindung", 4000)
            return
        names = self.config.setdefault("teamviewer_names", {})
        name, ok = QInputDialog.getText(
            self, "TeamViewer-ID benennen",
            f"Name für TeamViewer-ID {format_tv_id(tv_id)} (leer = Name entfernen):",
            text=names.get(tv_id, ""))
        if not ok:
            return
        if name.strip():
            names[tv_id] = name.strip()
        else:
            names.pop(tv_id, None)
        mt.save_config(self.config)
        self.timeline.draw_timeline(self.current_date)

    def open_details(self, row):
        if 0 <= row < len(self.list_entries):
            ActivityViewDialog(self.list_entries[row], self).exec()

    def copy_selection(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        if not rows:
            rows = range(self.table.rowCount())
        lines = []
        for row in rows:
            entry = self.list_entries[row] if row < len(self.list_entries) else {}
            if entry.get("doc"):
                lines.append(ticket_line(entry["doc_item"]))  # fertige Ticketzeile
                continue
            if entry.get("open"):
                lines.append(f"OFFEN: {describe(entry['source_entry'])}")
                continue
            if entry.get("ai") or entry.get("rule"):
                lines.append(ai_copy_text(entry))
                continue
            cells = [self.table.item(row, c).text() for c in range(self.table.columnCount())]
            lines.append(f"{cells[0]}–{cells[1]}\t" + "\t".join(cells[2:]).rstrip())
        QApplication.clipboard().setText("\n".join(lines))
        self.statusBar().showMessage(f"{len(lines)} Zeile(n) kopiert", 3000)

    def update_status_text(self):
        day = GERMAN.toString(self.current_date, "dddd, dd.MM.yyyy")
        parts = [day]
        n = len(self.day_activities)
        if n:
            parts.append(f"{n} Einträge")
            parts.append(f"belegt {format_duration(mt.merged_seconds(self.day_activities))}")
        elif self.timeline.loading:
            parts.append("Logs werden gelesen …")
        else:
            parts.append("keine Einträge")
            missing = self.timeline.missing_sources()
            if missing:
                parts.append(f"keine Logdatei gefunden: {', '.join(missing)} "
                             "(Pfade unter Einstellungen → Datenquellen → Einrichten)")
        if self.pc_activities:
            parts.append(f"am PC aktiv {format_duration(mt.merged_seconds(self.pc_activities))}")
        doc = self.doc_band(self.current_date.toString("yyyy-MM-dd"))
        done = [e for e in doc if e.get("doc")]
        open_count = len(doc) - len(done)
        if done or open_count:
            text = f"dokumentiert {format_duration(mt.merged_seconds(done))}" if done else "nichts dokumentiert"
            if open_count:
                text += f", {open_count} offen (F7)"
            parts.append(text)
        itm_day = self.itm_reader.day(self.current_date.toString("yyyy-MM-dd")) if self.itm_reader else None
        if itm_day and itm_day.get("gewertet") is not None:
            text = f"Personalzeit {format_duration(itm_day['gewertet'] * 60)}"
            if itm_day.get("soll"):
                text += f" (Soll {format_duration(itm_day['soll'] * 60)})"
            parts.append(text)
        self.info_label.setText("   ·   ".join(parts))

    # ---------------------- Datum / Navigation --------------------------------

    def date_changed(self, date: QDate):
        self.current_date = date
        self.timeline.draw_timeline(self.current_date)
        # Fehlende Daten für diesen Tag im Hintergrund nachlesen
        for reader in (self.pbx_reader, self.itm_reader):
            if reader:
                reader.want(date.toString("yyyy-MM-dd"))
        # Vergangene Tage auf Wunsch automatisch einordnen (nur ohne vorhandene Vorschläge)
        if (self.config.get("ai_auto") and date < QDate.currentDate()
                and not self.ai_store.load(date.toString("yyyy-MM-dd"))):
            self.classify_day(quiet=True)

    def show_previous_day(self):
        self.date_edit.setDate(self.current_date.addDays(-1))

    def show_next_day(self):
        self.date_edit.setDate(self.current_date.addDays(1))

    def show_today(self):
        self.date_edit.setDate(QDate.currentDate())

    def refresh(self):
        self.timeline.refresh()
        self.statusBar().showMessage("Logs werden neu eingelesen …", 2000)

    def auto_refresh(self):
        try:
            if vpn_sources(self.config):
                self.timeline.vpn_reader.update_from_logs()  # Sophos-Logs sichern, bevor sie überschrieben werden
        except Exception as e:
            print(f"Fehler beim Lesen der VPN-Logs: {e}")
        if self.current_date == QDate.currentDate():
            self.timeline.refresh()

    def apply_vpn_monitor(self):
        """Eigene VPN-Aufzeichnung nur, wenn Sophos Connect oder FortiClient eingeschaltet ist."""
        if vpn_sources(self.config) and self.config.get("vpn_monitor_enabled", True):
            if not self.vpn_timer.isActive():
                self.vpn_timer.start(30 * 1000)
                QTimer.singleShot(0, self.vpn_sample)
        else:
            self.vpn_timer.stop()

    def vpn_sample(self):
        if self.timeline.vpn_reader.sample() and self.current_date == QDate.currentDate() and self.isVisible():
            self.timeline.refresh()
