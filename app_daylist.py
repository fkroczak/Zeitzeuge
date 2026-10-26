"""Hauptfenster: Tagesliste, Statuszeile und Blättern zwischen den Tagen.

Teil von TimelineApp (main_timeline.py), nur über main_timeline laden.
"""
from PySide6.QtCore import QDate, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QInputDialog, QHeaderView, QTableWidgetItem

from vpn_reader import vpn_sources
from billing import hours_text
from journal import describe, ticket_line
from grouping import format_tv_id, work_blocks
from timeline_only import (ActivityViewDialog, ai_copy_text, entry_color, exec_entry_menu,
                           format_duration, parse_time, type_label)
import icons
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
            entries = self.ai_day_entries(date_str)
        elif self.config.get("list_view") == "doc":
            entries = self.doc_band(date_str)
        elif self.config.get("list_view") == "rules":
            entries = self.rule_band(date_str)
        elif self.config.get("list_view") == "m42":
            entries = self.m42_band(date_str) + self.m42_unbooked(date_str)
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
        # Ansicht "Dokumentation": abgerechnete Zeit neben der Dauer (Abrechnungstakt)
        billing = self.billing() if self.config.get("list_view") == "doc" else None
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
                QTableWidgetItem(format_duration((end - start).total_seconds())
                                 + (billing.note((end - start).total_seconds(), a.get("customer_name", ""))
                                    if billing and a.get("doc") else "")),
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
             ("doc", "Dokumentation"), ("rules", "Zuordnung ohne KI"), ("ai", "KI-Vorschläge"),
             ("m42", "Matrix42-Abgleich")]

    def change_view(self, key):
        self.config["list_view"] = key
        mt.save_config(self.config)
        self.update_view_button()
        self.timeline.draw_timeline(self.current_date)

    def name_teamviewer_id(self, entry):
        tv_id = entry.get("tv_id")
        if not tv_id:
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
        self.statusBar().showMessage(f"TeamViewer-ID {format_tv_id(tv_id)} heißt jetzt „{name.strip()}“"
                                     if name.strip() else "Name entfernt", 4000)

    def table_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if not 0 <= row < len(self.list_entries):
            return
        self.table.selectRow(row)
        entry = self.list_entries[row]
        key = exec_entry_menu(self, entry, self.table.viewport().mapToGlobal(pos))
        if key:
            self.on_entry_action(key, entry)

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
                lines.append(ticket_line(entry["doc_item"],  # fertige Ticketzeile
                                         self.config.get("ticket_format", ""), self.billing()))
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
        if self.pc_activities:
            parts.append(f"am PC aktiv {format_duration(mt.merged_seconds(self.pc_activities))}")
        doc = self.doc_band(self.current_date.toString("yyyy-MM-dd"))
        done = [e for e in doc if e.get("doc")]
        open_count = len(doc) - len(done)
        if done or open_count:
            text = f"dokumentiert {format_duration(mt.merged_seconds(done))}" if done else "nichts dokumentiert"
            billing = self.billing()
            if done and billing.any_active():
                text += f", abgerechnet {hours_text(billing.total_minutes([e['doc_item'] for e in done]))}"
            parts.append(text)
        self.open_docs_button.setVisible(bool(open_count))
        if open_count:
            self.open_docs_button.setText(f"{open_count} offen – jetzt eintragen")
            self.open_docs_button.setToolTip("Erste noch nicht dokumentierte Tätigkeit eintragen (F7)")
            self.open_docs_button.setAccessibleName(f"{open_count} Tätigkeiten offen, jetzt eintragen")
        itm_day = self.personal_day_for(self.current_date.toString("yyyy-MM-dd"))
        if itm_day and itm_day.get("gewertet") is not None:
            text = f"Personalzeit {format_duration(itm_day['gewertet'] * 60)}"
            if itm_day.get("soll"):
                text += f" (Soll {format_duration(itm_day['soll'] * 60)})"
            parts.append(text)
        m42 = self.m42_summary(self.current_date.toString("yyyy-MM-dd"))
        if m42:
            parts.append(m42)
        self.info_label.setText("   ·   ".join(parts))
        self.update_source_indicators()

    def update_busy_bar(self):
        """Ladeanzeige oben: alles, was gerade im Hintergrund lädt."""
        bar = getattr(self, "busy_bar", None)
        if bar is None:
            return
        items, urgent = [], False
        if self.timeline.loading:
            items.append("Logs (TeamViewer, RDM, VPN)")
            urgent = True
        for name, reader in (("3CX-Anrufe", getattr(self, "pbx_reader", None)),
                             ("ITM-Zeiterfassung", getattr(self, "itm_reader", None)),
                             ("Matrix42-Buchungen", getattr(self, "m42_reader", None))):
            if reader and getattr(reader, "busy", None) and reader.busy():
                items.append(name)
                urgent = urgent or reader.first_load()
        for date_str in sorted(getattr(self, "_ai_busy", ())):
            items.append(f"KI-Vorschläge (Claude ordnet {date_str[8:10]}.{date_str[5:7]}. ein)")
            urgent = True
        # Kurze Lesevorgänge im Hintergrund (jede Minute) erst nach 1,5 s zeigen, sonst flackert es
        bar.set_items(items, delay=0 if urgent else 1500)

    def update_source_indicators(self):
        """Anzeigen der Datenquellen in der Statuszeile auf den neuesten Stand bringen."""
        self.update_busy_bar()
        if not hasattr(self, "source_buttons"):
            return
        states = {}
        missing = [] if self.timeline.loading else self.timeline.missing_sources()
        if missing:
            states["logs"] = ("warn", f"Logs: {', '.join(missing)} fehlt",
                              f"Keine Logdatei gefunden: {', '.join(missing)}.\n"
                              "Klicken, um den Pfad einzustellen.")
        for kind, name in (("pbx", "3CX"), ("itm", "ITM"), ("m42", "M42")):
            reader = getattr(self, {"pbx": "pbx_reader", "itm": "itm_reader", "m42": "m42_reader"}[kind], None)
            if not reader:
                continue
            state, why = reader.health()
            hint = {"warn": "Klicken, um dich anzumelden." if reader.needs_login
                    else "Klicken für die Einstellungen.",
                    "ok": "Läuft. Klicken für die Einstellungen.",
                    "busy": "Liest gerade."}[state]
            text = f"{name} {why}" if state == "ok" else f"{name}: {why}"
            states[kind] = (state, text, f"{reader.status}\n{hint}")
        for kind, button in self.source_buttons.items():
            if kind not in states:
                button.hide()
                continue
            state, text, tip = states[kind]
            button.setIcon(icons.source_icon(state))
            button.setText(text)
            button.setToolTip(tip)
            label = {"ok": "läuft", "warn": "Problem", "busy": "liest"}[state]
            button.setAccessibleName(f"{text} ({label})")
            button.show()

    def on_source_clicked(self, kind):
        """Klick auf eine Datenquelle: direkt zur Lösung."""
        if kind == "logs":
            missing = self.timeline.missing_sources()
            (self.edit_rdm_settings if missing == ["RDM"] else self.edit_teamviewer_settings)()
        elif kind == "pbx":
            if self.pbx_reader and self.pbx_reader.needs_login:
                self.show_pbx_login()
            else:
                self.open_pbx_settings()
        elif kind == "itm":
            if self.itm_reader and self.itm_reader.needs_login:
                self.itm_reader.show_login(self)
            else:
                self.open_itm_settings()
        elif kind == "m42":
            if self.m42_reader and self.m42_reader.needs_login:
                self.m42_reader.show_login(self)
            else:
                self.open_m42_settings()

    # ---------------------- Datum / Navigation --------------------------------

    def date_changed(self, date: QDate):
        self.current_date = date
        self.timeline.draw_timeline(self.current_date)
        # Fehlende Daten für diesen Tag im Hintergrund nachlesen
        for reader in self.all_readers():
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
