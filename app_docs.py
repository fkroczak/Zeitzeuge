"""Hauptfenster: KI-Vorschläge, eigene Tätigkeiten (Doku) und Nachfragen.

Teil von TimelineApp (main_timeline.py), nur über main_timeline laden.
"""
import json
import os

from datetime import datetime, timedelta

from PySide6.QtCore import QDate, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QSystemTrayIcon

from ai_classifier import to_entries
from journal import (describe, entry_key as journal_key, open_entry, suggest_category,
                     suggest_customer, ticket_line)
from journal_dialogs import DocPromptDialog, prompt_thresholds, EntryDialog, PromptWindow, default_span
import snippets
import tickets
from snippets_dialogs import SnippetsDialog
from settings_dialogs import AiSettingsDialog
import rules
import m42_data as m42
from grouping import group_entries
from timeline_only import (ROW_NAMES, ActivityViewDialog, ai_copy_text, format_duration, parse_time,
                           row_kind, type_label)
from theme import GERMAN
import main_timeline as mt  # Pfade und save_config zur Laufzeit von dort (Tests ersetzen sie dort)


class DocsMixin:
    # ---------------------- KI-Vorschläge -------------------------------------

    def ai_input(self, date):
        """Einträge des Tages für die KI: zusammengefasst, damit es kurz bleibt."""
        entries = group_entries(self.timeline.activities_for(date),
                                self.config.get("merge_gap_minutes", 5))
        return entries, self.timeline.pc_entries_for(date, min_seconds=60)

    def classify_day(self, quiet=False):
        date = self.current_date
        date_str = date.toString("yyyy-MM-dd")
        if date_str in self.ai.running:
            self.statusBar().showMessage("KI-Vorschläge werden schon erstellt …", 3000)
            return
        entries, pc = self.ai_input(date)
        if not quiet and self.ai_store.is_current(date_str, self.ai.input_hash(self.ai.input_text(entries, pc))):
            answer = QMessageBox.question(
                self, "KI-Vorschläge",
                "Für diesen Tag gibt es schon Vorschläge, und die Einträge haben sich nicht geändert.\n"
                "Trotzdem neu erstellen? Das kostet einen weiteren Aufruf.")
            if answer != QMessageBox.Yes:
                return
            started = self.ai.start(date_str, entries, pc, force=True)
        else:
            started = self.ai.start(date_str, entries, pc)
        if started:
            self.ai_button_action.setEnabled(False)
            self._ai_busy.add(date_str)
            self.update_busy_bar()
            self.statusBar().showMessage(
                f"Claude ordnet {GERMAN.toString(date, 'dd.MM.')} ein …", 60000)

    def on_ai_finished(self, date_str, count, cost):
        self.ai_button_action.setEnabled(True)
        self._ai_busy.discard(date_str)
        self.update_busy_bar()
        cost_text = f"{cost:.3f}".replace(".", ",")
        self.statusBar().showMessage(
            f"KI: {count} Vorschläge für {date_str[8:10]}.{date_str[5:7]}., "
            f"Kosten ca. {cost_text} $", 8000)
        if date_str == self.current_date.toString("yyyy-MM-dd"):
            self.timeline.draw_timeline(self.current_date)

    def on_ai_failed(self, date_str, message):
        self.ai_button_action.setEnabled(True)
        self._ai_busy.discard(date_str)
        self.update_busy_bar()
        self.statusBar().showMessage(f"KI-Vorschläge: {message}", 10000)
        if not self.isVisible() or self.config.get("ai_auto"):
            return
        QMessageBox.warning(self, "KI-Vorschläge", message)

    def ai_day_entries(self, date_str):
        """KI-Vorschläge des Tages: eigene und von einem anderen PC übernommene (nur lesen).
        Ein übernommener Vorschlag gilt als übernommen, sobald hier eine Tätigkeit genau
        zu seiner Zeit eingetragen ist."""
        entries = self.ai_store.entries(date_str)
        if getattr(self, "imported", None):
            own = {(e["start"], e["end"]) for e in entries}
            docs = {(i["start"], i["end"]) for i in self.journal.items(date_str)}
            for pc, items in self.imported.ai(date_str):
                for e in to_entries(date_str, items):
                    if e["status"] == "verworfen" or (e["start"], e["end"]) in own:
                        continue
                    e["von_pc"] = pc
                    e["details"] += f" (von {pc})"
                    if (e["start"], e["end"]) in docs:
                        e["status"] = "übernommen"
                    entries.append(e)
            entries.sort(key=lambda e: e["start"])
        return entries

    def on_ai_action(self, entry, action):
        status = "übernommen" if action == "übernehmen" else "verworfen"
        if entry.get("von_pc"):  # von einem anderen PC: hier nur als Tätigkeit eintragen
            if status == "verworfen":
                self.statusBar().showMessage(f"Vorschlag kommt von {entry['von_pc']}, "
                                             "verwerfen geht nur dort", 6000)
                return
        else:
            self.ai_store.set_status(entry["start"][:10], entry["ai_id"], status)
        if status == "übernommen":  # übernommen = dokumentiert, steht dann in der Zeile "Doku"
            try:
                self.journal.add({"start": entry["start"], "end": entry["end"],
                                  "customer": entry.get("customer_name", ""),
                                  "category": entry.get("category", ""),
                                  "text": entry.get("description", ""), "source": "KI"})
            except (OSError, ValueError) as e:
                self.statusBar().showMessage(str(e), 8000)
        self.timeline.draw_timeline(self.current_date)
        self.statusBar().showMessage("KI-Vorschlag übernommen und als Tätigkeit gespeichert"
                                     if status == "übernommen" else "KI-Vorschlag verworfen", 4000)

    def ai_spent(self):
        """Summe der bisherigen Kosten aus allen gespeicherten Tagen."""
        total = 0.0
        try:
            names = os.listdir(mt.AI_DIR)
        except OSError:
            return total
        for name in names:
            if name.endswith(".json"):
                data = self.ai_store.load(name[:-5]) or {}
                total += data.get("cost_usd", 0) + data.get("earlier_cost_usd", 0)
        return total

    def edit_ai_settings(self):
        dialog = AiSettingsDialog(self.config, self.ai_spent(), self)
        if dialog.exec() == QDialog.Accepted:
            dialog.apply()
            mt.save_config(self.config)

    # ---------------------- Dokumentation: eigene Tätigkeiten -----------------

    def categories(self):
        return self.ai.categories()

    def known_customers(self):
        """Kunden zur Auswahl: zuletzt dokumentierte, benannte TeamViewer-IDs."""
        names = self.journal.customers()
        names += sorted(set(self.config.get("teamviewer_names", {}).values()) - set(names))
        return names

    def rule_band(self, date_str):
        """Blöcke aus den Regeln (ohne KI), zwischengespeichert bis sich etwas ändert."""
        date = QDate.fromString(date_str, "yyyy-MM-dd")
        entries = self.timeline.activities_for(date)
        pc = self.timeline.pc_entries_for(date, min_seconds=30)
        rule_list = self.config.get("rules") or []
        key = (len(entries), entries[-1]["end"] if entries else "", len(pc),
               pc[-1]["end"] if pc else "", json.dumps(rule_list, sort_keys=True),
               self.config.get("rules_gap_minutes", 5), self.config.get("rules_min_minutes", 5))
        cached = self._rule_cache.get(date_str)
        if cached and cached[0] == key:
            return cached[1]
        blocks = rules.classify(entries, pc, rule_list,
                                gap_minutes=self.config.get("rules_gap_minutes", 5),
                                min_minutes=self.config.get("rules_min_minutes", 5))
        self._rule_cache[date_str] = (key, blocks)
        return blocks

    # ---------------------- Matrix42: gebucht / nicht gebucht -----------------

    def _m42_bookings(self, date_str):
        """Buchungen aus Matrix42, sonst die von einem anderen PC übernommenen."""
        reader = getattr(self, "m42_reader", None)
        found = reader.day(date_str) if reader else None
        if found is None and getattr(self, "imported", None):
            found = self.imported.m42(date_str)
        return found

    def m42_band(self, date_str):
        """Zeile "Matrix42": Buchungen und (rot gestrichelt) Personalzeit ohne Buchung."""
        bookings = self._m42_bookings(date_str)
        if bookings is None:  # Tag (noch) nicht gelesen: nichts behaupten
            return []
        result = []
        for b in bookings:
            result.append({
                "start": b["start"], "end": b["end"], "type": "Matrix42-Buchung", "m42": True,
                "customer_name": b.get("customer", ""), "category": b.get("ticket", ""),
                "description": b.get("subject", ""),
                "details": " · ".join(t for t in (b.get("ticket"), b.get("subject"), b.get("entry")) if t),
            })
        date = QDate.fromString(date_str, "yyyy-MM-dd")
        day = datetime.strptime(date_str, "%Y-%m-%d")
        now = datetime.now()
        if day.date() > now.date():
            return result
        spans, from_itm, _open = self.timeline._work_info(date)
        work = []
        for a, b in spans:
            start, end = day + timedelta(minutes=a), day + timedelta(minutes=b)
            end = min(end, now)  # heute nur bis jetzt
            if end > start:
                work.append((start, end))
        name = "Personalzeit" if from_itm else "Arbeitszeit"
        for a, b in m42.gaps(work, bookings, self.config.get("m42_gap_minutes", 5)):
            result.append({
                "start": a.strftime("%Y-%m-%d %H:%M:%S"), "end": b.strftime("%Y-%m-%d %H:%M:%S"),
                "type": "Nicht gebucht", "m42_gap": True, "customer_name": "nicht gebucht",
                "details": f"{name} ohne Buchung in Matrix42",
                "minute": a.hour * 60 + a.minute,  # für "Tätigkeit ab … eintragen"
            })
        return sorted(result, key=lambda e: e["start"])

    def m42_unbooked(self, date_str):
        """Verbindungen und Telefonate, die (fast) keine Buchung abdeckt."""
        bookings = self._m42_bookings(date_str)
        if bookings is None:
            return []
        date = QDate.fromString(date_str, "yyyy-MM-dd")
        entries = [e for e in group_entries(self.timeline.activities_for(date),
                                            self.config.get("merge_gap_minutes", 5))
                   if e.get("type") != "Zugangsdaten"]
        return [dict(e, m42_unbooked=True)
                for e in m42.unbooked(entries, bookings, self.config.get("m42_gap_minutes", 5))]

    def m42_summary(self, date_str):
        """Kurztext für die Statuszeile, z. B. "Matrix42 gebucht 6:10 h, nicht gebucht 1:35 h"."""
        bookings = self._m42_bookings(date_str)
        if bookings is None:
            return ""
        band = self.m42_band(date_str)
        booked = mt.merged_seconds([e for e in band if e.get("m42")])
        missing = sum((parse_time(e["end"]) - parse_time(e["start"])).total_seconds()
                      for e in band if e.get("m42_gap"))
        text = f"Matrix42 gebucht {format_duration(booked)}"
        if missing:
            text += f", nicht gebucht {format_duration(missing)}"
        unbooked = len(self.m42_unbooked(date_str))
        if unbooked:
            text += f", {unbooked} Verbindung{'en' if unbooked > 1 else ''} ohne Buchung"
        return text

    def doc_candidates(self, date_str):
        """Erkannte Tätigkeiten des Tages, die noch nicht dokumentiert sind."""
        sources = self.config.get("prompt_sources", ["connections", "calls"])
        date = QDate.fromString(date_str, "yyyy-MM-dd")
        entries = []
        if "connections" in sources or "calls" in sources:
            grouped = group_entries(self.timeline.activities_for(date),
                                    self.config.get("merge_gap_minutes", 5))
            for e in grouped:
                is_call = row_kind(e) == "call"
                if is_call and "calls" in sources:
                    entries.append(e)
                elif not is_call and "connections" in sources and e.get("type") != "Zugangsdaten":
                    entries.append(e)
        if "rules" in sources:
            entries += self.rule_band(date_str)
        return self.journal.open_items(entries, date_str, min_minutes=self.prompt_threshold)

    def prompt_threshold(self, entry):
        """Ab wie vielen Minuten nach diesem Eintrag gefragt wird (Einstellung je Art)."""
        kind = "rules" if entry.get("rule") else "calls" if row_kind(entry) == "call" else "connections"
        return prompt_thresholds(self.config)[kind]

    def doc_band(self, date_str):
        """Zeile "Doku": eigene Tätigkeiten und (gestrichelt) was noch offen ist."""
        entries = self.journal.entries(date_str)
        entries += [open_entry(e) for e in self.doc_candidates(date_str)]
        return sorted(entries, key=lambda e: e["start"])

    def on_doc_request(self, action, entry):
        """Klick in der Timeline (offen: eintragen, Tätigkeit: bearbeiten)."""
        self.on_entry_action(action, entry)

    def on_entry_action(self, key, entry):
        """Befehl aus dem Rechtsklick-Menü (Timeline und Tagesliste gleich)."""
        if key == "add":
            self.add_doc(entry.get("source_entry", entry))
        elif key == "add_at":
            self.add_doc(minute=entry["minute"])
        elif key == "edit":
            self.edit_doc(entry["doc_item"])
        elif key == "delete":
            self.delete_doc(entry["doc_item"])
        elif key == "ignore":
            self.journal.ignore(entry.get("source_entry", entry))
            self.timeline.draw_timeline(self.current_date)
            self.statusBar().showMessage("Wird nicht mehr nachgefragt", 4000)
        elif key == "reject":
            self.on_ai_action(entry, "verwerfen")
        elif key == "details":
            ActivityViewDialog(entry, self).exec()
        elif key == "name_tv":
            self.name_teamviewer_id(entry)
        elif key == "copy":
            if entry.get("doc"):
                text = ticket_line(entry["doc_item"], self.config.get("ticket_format", ""))
            elif entry.get("ai") or entry.get("rule"):
                text = ai_copy_text(entry)
            else:
                start, end = parse_time(entry["start"]), parse_time(entry["end"])
                text = (f"{start:%H:%M}–{end:%H:%M}\t{type_label(entry)}\t"
                        f"{entry.get('customer_name', '')}\t{entry.get('details', '')}").rstrip()
            QApplication.clipboard().setText(text)
            self.statusBar().showMessage("In die Zwischenablage kopiert", 3000)

    def document_next_open(self):
        """Knopf „… offen – jetzt eintragen“: erste offene Tätigkeit des Tages eintragen."""
        open_items = self.doc_candidates(self.current_date.toString("yyyy-MM-dd"))
        if open_items:
            self.add_doc(open_items[0])

    def add_doc(self, entry=None, minute=None):
        """Tätigkeit nachtragen, auf Wunsch vorbelegt aus einem erkannten Eintrag."""
        if entry is None and minute is None and self.table.hasFocus():
            row = self.table.currentRow()
            if 0 <= row < len(self.list_entries):
                return self.doc_for_row()
        categories = self.categories()
        if entry:
            start, end = parse_time(entry["start"]), parse_time(entry["end"])
            info = f"Erkannt: {describe(entry)}"
            customer = suggest_customer(entry, self.config.get("teamviewer_names", {}))
            category = suggest_category(entry, categories)
            text = entry.get("description", "") if entry.get("ai") or entry.get("rule") else ""
        else:
            start, end = default_span(self.current_date.toPython(), minute)
            info, customer, category, text = "", "", "", ""
        dialog = EntryDialog(start, end, self.known_customers(), categories, customer, category,
                             text, tv_id=(entry or {}).get("tv_id"), info=info, parent=self,
                             **self.entry_form_options(start, end))
        if dialog.exec() != QDialog.Accepted:
            return
        item = dialog.item()
        if entry:
            item["source"] = "KI" if entry.get("ai") else entry.get("type", "")
        if self._save_doc(item, entry, dialog.remember_tv()) and entry and entry.get("ai"):
            if not entry.get("von_pc"):  # übernommene Vorschläge gehören dem anderen PC
                self.ai_store.set_status(entry["start"][:10], entry["ai_id"], "übernommen")
            self.timeline.draw_timeline(self.current_date)

    def _save_doc(self, item, entry=None, remember_tv=False, old=None):
        try:
            if old:
                self.journal.update(old, item)
            else:
                self.journal.add(item)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Tätigkeit", str(e))
            return False
        tv_id = (entry or {}).get("tv_id")
        if tv_id and remember_tv and item.get("customer"):
            self.config.setdefault("teamviewer_names", {})[tv_id] = item["customer"]
            mt.save_config(self.config)
        self.timeline.draw_timeline(self.current_date)
        self.statusBar().showMessage("Tätigkeit gespeichert", 3000)
        return True

    def _foreign_doc(self, item):
        """Übernommene Tätigkeit eines anderen PCs: hier nur ansehen, ändern geht dort."""
        if not item.get("von_pc"):
            return False
        QMessageBox.information(self, "Tätigkeit", f"Diese Tätigkeit wurde von {item['von_pc']} "
                                "übernommen. Ändern oder löschen kannst du sie nur dort.")
        return True

    def edit_doc(self, item):
        if self._foreign_doc(item):
            return
        start, end = parse_time(item["start"]), parse_time(item["end"])
        dialog = EntryDialog(start, end, self.known_customers(), self.categories(),
                             item.get("customer", ""), item.get("category", ""),
                             item.get("text", ""), title="Tätigkeit bearbeiten",
                             can_delete=True, parent=self,
                             **self.entry_form_options(start, end, item.get("ticket", "")))
        if dialog.exec() != QDialog.Accepted:
            return
        if dialog.deleted:
            self.delete_doc(item, ask=False)
        else:
            self._save_doc(dialog.item(), old=item)

    def delete_doc(self, item, ask=True):
        if self._foreign_doc(item):
            return
        if ask and QMessageBox.question(
                self, "Tätigkeit löschen",
                f"Diese Tätigkeit löschen?\n\n{ticket_line(item)}") != QMessageBox.Yes:
            return
        try:
            self.journal.delete(item)
        except OSError as e:
            QMessageBox.warning(self, "Tätigkeit löschen", str(e))
            return
        self.timeline.draw_timeline(self.current_date)
        self.statusBar().showMessage("Tätigkeit gelöscht", 4000)

    def doc_for_row(self):
        """F7 bei markierter Zeile: Tätigkeit dazu eintragen oder bearbeiten."""
        row = self.table.currentRow()
        if not 0 <= row < len(self.list_entries):
            return None
        entry = self.list_entries[row]
        if entry.get("doc"):
            self.edit_doc(entry["doc_item"])
        else:
            self.add_doc(entry.get("source_entry", entry))

    def show_open_docs(self):
        """Fenster zeigen, heute, Ansicht "Dokumentation"."""
        self.show_from_tray()
        self.show_today()
        self.change_view("doc")

    def toggle_row(self, key, on):
        self.config.setdefault("timeline_rows", {})[key] = on
        mt.save_config(self.config)
        self.timeline.draw_timeline(self.current_date)
        name = ROW_NAMES.get(key, key)
        self.statusBar().showMessage(f"Zeile „{name}“ {'eingeblendet' if on else 'ausgeblendet'}", 3000)

    def show_all_rows(self):
        for action in self.row_actions.values():
            action.setChecked(True)  # löst toggle_row aus

    def edit_prompt_settings(self):
        dialog = DocPromptDialog(self.config, self)
        if dialog.exec() == QDialog.Accepted:
            dialog.apply()
            mt.save_config(self.config)
            self.timeline.draw_timeline(self.current_date)

    # ---- Eintragen: Textbausteine, zuletzt benutzte Texte, Ticket (snippets.py, tickets.py)

    def entry_form_options(self, start, end, ticket=""):
        """Zusätze für den Eintragen-Dialog: Bausteine, letzte Texte je Kunde, Ticket-Vorschläge."""
        recent = None
        if self.config.get("snippets_recent", True):
            items = None

            def recent(customer):
                nonlocal items
                if items is None:  # erst beim Öffnen des Menüs lesen
                    items = self.journal.recent_items()
                return snippets.recent_texts(items, customer)
        return {"snippets": snippets.from_config(self.config), "recent_texts": recent,
                "ticket": ticket, "ticket_suggestions": self.ticket_suggestions(start, end)}

    def ticket_suggestions(self, start, end):
        """Ticketnummern aus Fenstertiteln und Matrix42-Buchungen rund um die Tätigkeit."""
        patterns = self.config.get("ticket_patterns", tickets.DEFAULT_PATTERNS)
        if not patterns:
            return []
        date = QDate(start.year, start.month, start.day)
        segments = [{"start": e["start"], "end": e["end"], "title": e.get("customer_name", ""),
                     "app": e.get("type", "")[4:]}  # "PC: Outlook" -> "Outlook"
                    for e in self.timeline.pc_entries_for(date, min_seconds=0)]
        bookings = self._m42_bookings(start.strftime("%Y-%m-%d")) or []
        return tickets.suggest(start, end, segments, bookings, patterns)

    def edit_snippets(self):
        dialog = SnippetsDialog(self.config, self)
        if dialog.exec() == QDialog.Accepted:
            dialog.apply()
            mt.save_config(self.config)

    # ---- Nachfragen ("Was hast du gemacht?")

    def check_prompts(self):
        """Jede Minute: neu erkannte, noch nicht dokumentierte Tätigkeiten nachfragen."""
        mode = self.config.get("prompt_mode", "window")
        if mode == "off" or self._quitting:
            return
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        open_items = self.doc_candidates(today)
        for e in open_items:
            key = journal_key(e)
            # Nur frisch beendete fragen (seit dem Start von Zeitzeuge oder in der letzten
            # Stunde). Ältere stehen gestrichelt in der Zeile "Doku" und in der Liste.
            ended = parse_time(e["end"])
            if ended < min(self._started_at, now) - timedelta(hours=1):
                continue
            if key in self._prompt_asked and self._prompt_asked[key] > now:
                continue
            if key not in (journal_key(q) for q in self._prompt_queue):
                self._prompt_queue.append(e)
        keys = {journal_key(e) for e in open_items}  # inzwischen dokumentiert: nicht mehr fragen
        self._prompt_queue = [q for q in self._prompt_queue if journal_key(q) in keys]
        if self._prompt_queue:
            self.show_next_prompt()
        self.end_of_day_reminder(open_items, now)

    def show_next_prompt(self, force=False):
        if self._prompt_window or not self._prompt_queue:
            if self._prompt_window:
                self._prompt_window.set_pending(len(self._prompt_queue) - 1)
            return
        entry = self._prompt_queue[0]
        if self.config.get("prompt_mode") == "tray" and not force:
            if self.tray and journal_key(entry) not in self._prompt_asked:
                self._prompt_asked[journal_key(entry)] = datetime.max
                self._tray_doc_hint = True
                self.tray.showMessage("Was hast du gemacht?",
                                      f"{describe(entry)}\nKlick hier, um es einzutragen.",
                                      QSystemTrayIcon.Information, 10000)
            return
        window = PromptWindow(entry, self.known_customers(), self.categories(),
                              self.config.get("teamviewer_names", {}),
                              pending=len(self._prompt_queue) - 1, parent=self,
                              **self.entry_form_options(parse_time(entry["start"]),
                                                        parse_time(entry["end"])))
        window.answered.connect(self.on_prompt_answered)
        self._prompt_window = window
        # unten rechts über dem Infobereich, ohne dir den Fokus wegzunehmen
        screen = QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            window.adjustSize()
            window.move(area.right() - window.width() - 24, area.bottom() - window.height() - 24)
        window.show()

    def on_prompt_answered(self, action, entry, item):
        window, self._prompt_window = self._prompt_window, None
        key = journal_key(entry)
        self._prompt_queue = [q for q in self._prompt_queue if journal_key(q) != key]
        if action == "save":
            item["source"] = entry.get("type", "")
            if not self._save_doc(item, entry, window.remember_tv() if window else False):
                self._prompt_queue.insert(0, entry)
        elif action == "ignore":
            self.journal.ignore(entry)
            self.timeline.draw_timeline(self.current_date)
            self.statusBar().showMessage("Wird nicht mehr nachgefragt", 4000)
        else:  # später
            snooze = self.config.get("prompt_snooze_minutes", 15)
            self._prompt_asked[key] = datetime.now() + timedelta(minutes=snooze)
            self.statusBar().showMessage(f"Zeitzeuge fragt in {snooze} Minuten noch einmal", 4000)
        if window:
            window.deleteLater()
        QTimer.singleShot(400, self.show_next_prompt)

    def end_of_day_reminder(self, open_items, now):
        """Nach Feierabend einmal am Tag an offene Tätigkeiten erinnern."""
        if not (self.config.get("prompt_end_of_day", True) and open_items and self.tray):
            return
        today = now.strftime("%Y-%m-%d")
        if self._reminded_day == today:
            return
        _start, end = self.timeline._work_minutes(QDate.currentDate())
        if end <= _start or now.hour * 60 + now.minute < end:
            return
        self._reminded_day = today
        self._tray_doc_hint = True
        self.tray.showMessage(
            "Feierabend: noch nicht alles dokumentiert",
            f"Heute sind noch {len(open_items)} Tätigkeiten offen. Klick hier zum Nachtragen.",
            QSystemTrayIcon.Warning, 15000)

    def request_quit(self):
        """Beenden über Menü/Infobereich: vorher an offene Tätigkeiten von heute erinnern."""
        if self.config.get("prompt_on_quit", True) and self.config.get("prompt_mode") != "off":
            open_items = self.doc_candidates(datetime.now().strftime("%Y-%m-%d"))
            if open_items and self.ask_document_first(len(open_items)):
                self.show_open_docs()
                return
        self.quit_app()

    def ask_document_first(self, count):
        """Rückfrage beim Beenden. True = erst nachtragen, nicht beenden."""
        box = QMessageBox(QMessageBox.Question, "Zeitzeuge beenden",
                          f"Heute sind noch {count} Tätigkeiten nicht dokumentiert. "
                          "Jetzt nachtragen?", parent=self)
        later = box.addButton("&Nachtragen", QMessageBox.AcceptRole)
        box.addButton("Trotzdem &beenden", QMessageBox.DestructiveRole)
        box.setDefaultButton(later)
        box.exec()
        return box.clickedButton() is later
