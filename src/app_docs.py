"""Hauptfenster: KI-Vorschläge, eigene Tätigkeiten (Doku) und Nachfragen.

Teil von TimelineApp (main_timeline.py), nur über main_timeline laden.
"""
import json
import os

from datetime import datetime, timedelta

from PySide6.QtCore import QDate, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QSystemTrayIcon

from ai_classifier import to_entries
from billing import Billing
from journal import (describe, entry_key as journal_key, open_entry, suggest_category,
                     suggest_customer, sub_entries, ticket_line)
from journal_dialogs import (DocPromptDialog, prompt_thresholds, EntryDialog, PromptWindow, default_span,
                             PROMPT_SOURCES)
import snippets
import tickets
from snippets_dialogs import SnippetsDialog
from settings_dialogs import AiSettingsDialog
from customers_dialogs import CustomersMixin
import learning
import rules
import m42_data as m42
import week_dialogs
import booking_rate as br
import day_checks
import idle_watch
from grouping import CREDENTIAL_TYPES, group_entries
import customers as customer_list
import focus
import prompt_topics
import range_context
from timeline_only import (OUTLOOK_TYPES, ROW_NAMES, ActivityViewDialog, ai_copy_text, format_duration, parse_time,
                           row_kind, type_label)
from theme import GERMAN
import main_timeline as mt  # Pfade und save_config zur Laufzeit von dort (Tests ersetzen sie dort)


def _overlap(a, b):
    """Gemeinsame Zeit zweier Einträge (Text "YYYY-MM-DD HH:MM:SS" lässt sich direkt vergleichen)."""
    start, end = max(a["start"], b["start"]), min(a["end"], b["end"])
    return (parse_time(end) - parse_time(start)).total_seconds() if start < end else 0


class DocsMixin(CustomersMixin):
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

    def billing(self):
        """Regeln des Abrechnungstakts aus der Config (billing.py)."""
        return Billing.from_config(self.config)

    def known_customers(self):
        """Kunden zur Auswahl: zuletzt dokumentierte, Kundenliste, benannte TeamViewer-IDs."""
        names = self.journal.customers()
        names += sorted(set(self.config.get("teamviewer_names", {}).values()) - set(names))
        names += sorted({c["name"] for c in self.customer_index_list()} - set(names), key=str.lower)
        return names

    def rule_sample(self, days=7):
        """Einträge und Fenster der letzten Tage für Trefferzahl und Vorschau im Regel-Dialog
        -> (Einträge, Fenster)."""
        entries, pc = [], []
        today = QDate.currentDate()
        for back in range(days):
            date = today.addDays(-back)
            entries += self.timeline.activities_for(date)
            pc += self.timeline.pc_entries_for(date, min_seconds=30)
        self.timeline.activities_for(self.current_date)  # Zwischenstand des angezeigten Tags zurück
        return entries, pc

    def rule_band(self, date_str):
        """Blöcke aus den Regeln (ohne KI), zwischengespeichert bis sich etwas ändert."""
        date = QDate.fromString(date_str, "yyyy-MM-dd")
        entries = self.timeline.activities_for(date)
        pc = self.timeline.pc_entries_for(date, min_seconds=30)
        rule_list = self.config.get("rules") or []
        index = self.customer_index()  # Stichwörter der Kundenliste
        key = (len(entries), entries[-1]["end"] if entries else "", len(pc),
               pc[-1]["end"] if pc else "", json.dumps(rule_list, sort_keys=True), id(index),
               self.config.get("rules_gap_minutes", 5), self.config.get("rules_min_minutes", 5))
        cached = self._rule_cache.get(date_str)
        if cached and cached[0] == key:
            return cached[1]
        blocks = rules.classify(entries, pc, rule_list,
                                gap_minutes=self.config.get("rules_gap_minutes", 5),
                                min_minutes=self.config.get("rules_min_minutes", 5),
                                keywords=index)
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
                "details": " · ".join(t for t in (b.get("ticket"), b.get("subject"), b.get("entry"),
                                                  b.get("activity_type"), b.get("state")) if t),
            })
        date = QDate.fromString(date_str, "yyyy-MM-dd")
        day = datetime.strptime(date_str, "%Y-%m-%d")
        now = datetime.now()
        if day.date() > now.date():
            return result
        spans, from_itm, _open = self.timeline._work_info(date)
        missing = self.timeline.missing_end_idx(date)
        work = []
        for i, (a, b) in enumerate(spans):
            if i == missing:  # Gehen fehlt: Ende unbekannt, keine Lücke ausrechnen
                continue
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
                   if e.get("type") != "Zugangsdaten" and row_kind(e) != "outlook"]
        return [dict(e, m42_unbooked=True)
                for e in m42.unbooked(entries, bookings, self.config.get("m42_gap_minutes", 5))]

    def m42_summary(self, date_str):
        """Kurztext für die Statuszeile, z. B. "Matrix42 gebucht 6:10 h, nicht gebucht 1:35 h"."""
        bookings = self._m42_bookings(date_str)
        if bookings is None:
            return ""
        band = self.m42_band(date_str)
        # wie Matrix42 und die Quote: gerundete Zeiten, jede Buchung voll (booking_rate.py)
        until = datetime.now() if date_str == datetime.now().strftime("%Y-%m-%d") else None
        booked = br.booked_seconds(bookings, until)
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
        """Erkannte, noch nicht dokumentierte Tätigkeiten des Tages, zu Themen zusammengefasst.

        Quellen (Einstellung prompt_sources): Verbindungen, Telefonate, Arbeitsblöcke am PC,
        Teams-Besprechungen mit Teilnahme, Mails an Kunden aus der Kundenliste, angezeigte
        Zugangsdaten, Blöcke der Zuordnung ohne KI. Was zur selben Arbeit gehört (gleicher Kunde,
        gleiche Zeit), wird ein Thema: eine Nachfrage statt mehrerer (prompt_topics.py).
        """
        sources = self.config.get("prompt_sources", PROMPT_SOURCES)
        date = QDate.fromString(date_str, "yyyy-MM-dd")
        index = self.customer_index()
        activities = self.timeline.activities_for(date)
        entries = []
        grouped = group_entries([a for a in activities if a.get("type") not in OUTLOOK_TYPES],
                                self.config.get("merge_gap_minutes", 5))
        for e in grouped:
            kind = self.prompt_kind(e)
            if kind in sources and kind in ("connections", "calls", "credentials"):
                entries.append(e)
        if "meetings" in sources:
            entries += self._attended_meetings(date, activities)
        if "mails" in sources:
            entries += [m for m in activities if m.get("type") == "Mail gesendet"
                        and customer_list.customer_for(m, index)]
        if "pc" in sources:
            skip = set(self.config.get("prompt_pc_skip", ["E-Mail / Kommunikation"]))
            entries += [b for b in self._pc_focus_blocks(date)
                        if b.get("ruled") and b.get("category") not in skip]
        if "rules" in sources:
            # Blöcke nur aus Outlook-Terminen/-Mails nicht nachfragen (geplant ist nicht getan)
            entries += [b for b in self.rule_band(date_str)
                        if not b.get("sources") or any(s.get("type") not in OUTLOOK_TYPES
                                                       for s in b["sources"])]
        opened = self.journal.open_items(entries, date_str, min_minutes=self.prompt_threshold)
        topics = prompt_topics.build_topics(opened, index,
                                            self.config.get("prompt_topic_gap_minutes", 15))
        # Ein Thema, das (als Ganzes) schon beantwortet oder ignoriert ist, nicht wieder anbieten
        return [t for t in topics if not t.get("topic") or not (
            self.journal.is_ignored(t) or self.journal.is_answered(t, date_str))]

    @staticmethod
    def prompt_kind(entry):
        """Art eines erkannten Eintrags für Quellen und Mindestdauer der Nachfragen."""
        kind = entry.get("type", "")
        if entry.get("local") or row_kind(entry) in ("pcstate", "wlan", "files"):
            return "local"  # Spuren vom PC: keine Nachfrage, kein Tagesabschluss
        if entry.get("rule"):
            return "rules"
        if entry.get("pc_block"):
            return "pc"
        if kind in ("Termin", "Teams-Besprechung"):
            return "meetings"
        if kind == "Mail gesendet":
            return "mails"
        if kind == "Zugangsdaten" or kind in CREDENTIAL_TYPES:
            return "credentials"
        return "calls" if row_kind(entry) == "call" else "connections"

    def prompt_threshold(self, entry):
        """Ab wie vielen Minuten nach diesem Eintrag gefragt wird (Einstellung je Art)."""
        return prompt_thresholds(self.config).get(self.prompt_kind(entry), 1)

    def _pc_focus_blocks(self, date):
        """Arbeitsblöcke am PC (focus.py), unabhängig davon, wie die Timeline sie zeigt."""
        raw = self.timeline.pc_entries_for(date, min_seconds=5, max_gap=15)
        if self.config.get("pc_blocks", True):
            return [b for b in self.timeline.pc_blocks_for(date) if b.get("pc_block")]
        segments = [{"start": e["start"], "end": e["end"], "app": e["app"], "title": e["customer_name"]}
                    for e in raw]
        return focus.focus_blocks(segments, self.config.get("rules") or [],
                                  jump_seconds=self.config.get("pc_jump_seconds", focus.JUMP_SECONDS),
                                  keywords=self.customer_index())

    def _attended_meetings(self, date, activities):
        """Teams-Besprechungen und Termine, an denen du erkennbar teilgenommen hast:
        Teams-Anruf oder Teams im Vordergrund während mindestens 30 % der Zeit.
        (Termine ohne Rechner, z. B. vor Ort, fragt die Abwesenheit am PC ab.)"""
        meetings = [a for a in activities if a.get("type") in ("Termin", "Teams-Besprechung")]
        if not meetings:
            return []
        teams = [a for a in activities if a.get("type") == "Teams-Anruf"]
        teams += [p for p in self.timeline.pc_entries_for(date, min_seconds=5, max_gap=15)
                  if "teams" in (p.get("app") or "").lower()]
        result = []
        for m in meetings:
            length = (parse_time(m["end"]) - parse_time(m["start"])).total_seconds()
            if length > 0 and sum(prompt_topics.overlap(m, t) for t in teams) >= 0.3 * length:
                result.append(m)
        return result

    def doc_band(self, date_str):
        """Zeile "Doku": eigene Tätigkeiten und (gestrichelt) was noch offen ist."""
        entries = self.journal.entries(date_str)
        opened = [open_entry(e) for e in self.doc_candidates(date_str)]
        # Zuordnung ohne KI fließt hier ein: offene Einträge ohne Kunden bekommen den Vorschlag
        # der Regel, die sie am meisten überdeckt (eigene Zeile ist standardmäßig aus)
        if any(not e.get("customer_name") for e in opened):
            blocks = [b for b in self.rule_band(date_str) if b.get("customer_name")]
            for e in opened:
                if e.get("customer_name") or e["source_entry"].get("rule"):
                    continue
                best = max(blocks, key=lambda b: _overlap(b, e), default=None)
                if best and _overlap(best, e) > 0:
                    e["customer_name"] = best["customer_name"]
                    e["details"] += f" · Vorschlag (Regel): {best['customer_name']}"
        return sorted(entries + opened, key=lambda e: e["start"])

    def on_doc_request(self, action, entry):
        """Klick in der Timeline (offen: eintragen, Tätigkeit: bearbeiten)."""
        self.on_entry_action(action, entry)

    def on_entry_action(self, key, entry):
        """Befehl aus dem Rechtsklick-Menü (Timeline und Tagesliste gleich)."""
        if key == "add":
            self.add_doc(entry.get("source_entry", entry))
        elif key == "add_at":
            self.add_doc(minute=entry["minute"])
        elif key == "add_range":  # in der Timeline mit links gezogener Zeitraum
            day = datetime.combine(self.current_date.toPython(), datetime.min.time())
            end_min = min(entry["end_min"], 24 * 60 - 1)  # 24:00 gibt es im Zeitfeld nicht
            self.add_doc(span=(day + timedelta(minutes=entry["start_min"]), day + timedelta(minutes=end_min)))
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
        elif key == "assign_customer":
            self.assign_customer(entry)
        elif key == "m42_book":
            self.book_in_m42(entry["doc_item"])
        elif key == "copy":
            if entry.get("doc"):
                text = ticket_line(entry["doc_item"], self.config.get("ticket_format", ""),
                                   self.billing())
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

    def add_doc(self, entry=None, minute=None, span=None):
        """Tätigkeit nachtragen, auf Wunsch vorbelegt aus einem erkannten Eintrag oder Zeitraum."""
        if entry is None and minute is None and span is None and self.table.hasFocus():
            row = self.table.currentRow()
            if 0 <= row < len(self.list_entries):
                return self.doc_for_row()
        categories = self.categories()
        if entry:
            start, end = parse_time(entry["start"]), parse_time(entry["end"])
            info = f"Erkannt: {describe(entry)}"
            hints = learning.doc_hints(entry, self.config, categories, self.customer_index())
            customer, category = hints["customer"], hints["category"]
            text = entry.get("description", "") if entry.get("ai") or entry.get("rule") else ""
        else:
            start, end = span or default_span(self.current_date.toPython(), minute)
            info, customer, category, text = "", "", "", ""
            hints = {}
        context_for = None
        if span:  # Zeitraum in der Timeline gezogen: Spuren dazu zeigen, Termin/Anruf vorschlagen
            date = QDate(start.year, start.month, start.day)
            day_acts = self.timeline.activities_for(date)
            day_pcs = self.timeline.pc_entries_for(date, min_seconds=30)

            def context_for(s, e):
                return range_context.context(s, e, day_acts, day_pcs)
            found = range_context.suggestion(start, end, day_acts, self.customer_index())
            if found:
                customer, text = found
                info = f"Vorschlag aus deinem {'Kalender' if text != 'Telefonat' else 'Anruf'}: {text}"
        dialog = EntryDialog(start, end, self.known_customers(), categories, customer, category,
                             text, tv_id=(entry or {}).get("tv_id"), info=info, parent=self,
                             trace=hints.get("trace"), rule_subject=hints.get("rule_subject"),
                             context_for=context_for, **self.entry_form_options(start, end))
        dialog.form.set_billing(self.billing())
        if dialog.exec() != QDialog.Accepted:
            return
        item = dialog.item()
        if entry:
            item["source"] = "KI" if entry.get("ai") else entry.get("type", "")
        if self._save_doc(item, entry, dialog.remember_tv(), rule=dialog.wants_rule()) \
                and entry and entry.get("ai"):
            if not entry.get("von_pc"):  # übernommene Vorschläge gehören dem anderen PC
                self.ai_store.set_status(entry["start"][:10], entry["ai_id"], "übernommen")
            self.timeline.draw_timeline(self.current_date)

    def _save_doc(self, item, entry=None, remember_tv=False, old=None, rule=False):
        if entry and not old and not entry.get("ai"):
            # Antwort auf ein erkanntes Thema: Zeitraum und Kunde merken, damit nicht noch einmal
            # gefragt wird (auch wenn die eingetragene Zeit kürzer ist als die erkannte)
            source = entry.get("source_entry", entry)
            item = dict(item, answered=prompt_topics.answer_span(source, self.customer_index()))
        try:
            if old:
                self.journal.update(old, item)
            else:
                self.journal.add(item)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Tätigkeit", str(e))
            return False
        # Aus Korrekturen lernen: Kunde zur Spur (Kundenliste), Kategorie als Regel
        learned = learning.apply_corrections(self.config, entry, item, remember_tv, rule)
        if learned:
            mt.save_config(self.config)
        self.timeline.draw_timeline(self.current_date)
        self.statusBar().showMessage(" · ".join(["Tätigkeit gespeichert"] + learned),
                                     6000 if learned else 3000)
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
                             goodwill=item.get("goodwill", False), travel=item.get("travel", False),
                             no_surcharge=item.get("no_surcharge", False),
                             **self.entry_form_options(start, end, item.get("ticket", "")))
        dialog.form.set_billing(self.billing())
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
        """Nachtragen bei markierter Zeile: Tätigkeit dazu eintragen oder bearbeiten."""
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
            if getattr(self, "idle_watch", None):
                self.idle_watch.minutes = self.config.get("idle_prompt_minutes", 15)
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
                "ticket": ticket, "ticket_suggestions": self.ticket_suggestions(start, end),
                "ticket_search": self.search_m42_ticket if getattr(self, "m42_reader", None) else None,
                "ticket_lookup": self.m42_ticket_lookup if getattr(self, "m42_reader", None) else None}

    def m42_ticket_lookup(self, parent):
        """Suche beim Tippen im Feld „Ticket“ (m42_booking_dialogs.TicketLookup) oder None."""
        import m42_booking
        from m42_booking_dialogs import TicketLookup
        reader = getattr(self, "m42_reader", None)
        if reader is None:
            return None
        return TicketLookup(reader, m42_booking.ids(self.config).get("ticket_list"), parent)

    def search_m42_ticket(self, text="", parent=None):
        """Ticket in Matrix42 suchen (Knopf „Suchen …“ beim Ticket). Ticket-dict oder None."""
        import m42_booking
        from m42_booking_dialogs import search_ticket
        reader = getattr(self, "m42_reader", None)
        if reader is None:
            return None
        return search_ticket(reader, text, m42_booking.ids(self.config).get("ticket_list"),
                             parent or self)

    def ticket_suggestions(self, start, end, use_bookings=True):
        """Ticketnummern aus Fenstertiteln und Matrix42-Buchungen rund um die Tätigkeit
        (use_bookings=False: nur Fenstertitel, zum Messen des Tagesabschlusses)."""
        patterns = self.config.get("ticket_patterns", tickets.DEFAULT_PATTERNS)
        if not patterns:
            return []
        date = QDate(start.year, start.month, start.day)
        segments = [{"start": e["start"], "end": e["end"], "title": e.get("customer_name", ""),
                     "app": e.get("type", "")[4:]}  # "PC: Outlook" -> "Outlook"
                    for e in self.timeline.pc_entries_for(date, min_seconds=0)]
        bookings = (self._m42_bookings(start.strftime("%Y-%m-%d")) or []) if use_bookings else []
        return tickets.suggest(start, end, segments, bookings, patterns)

    def edit_snippets(self):
        dialog = SnippetsDialog(self.config, self)
        if dialog.exec() == QDialog.Accepted:
            dialog.apply()
            mt.save_config(self.config)

    # ---- Nachfragen ("Was hast du gemacht?")

    def idle_sample(self, now=None, idle=None):
        """Alle 5 Sekunden: Endet gerade eine lange Abwesenheit am PC, gleich nachfragen."""
        watch = getattr(self, "idle_watch", None)
        if watch is None or self._quitting:
            return
        now = now or datetime.now()
        span = watch.update(now, idle_watch.current_idle_seconds() if idle is None else idle)
        if not span or self.config.get("prompt_mode", "window") == "off":
            return
        entry = idle_watch.idle_entry(span)
        if self.journal.is_ignored(entry):
            return
        self._idle_open.append(entry)
        self._prompt_queue.insert(0, entry)  # vor allem anderen: gerade erst zurück
        self.show_next_prompt()

    def _idle_pending(self, now):
        """Abwesenheiten, nach denen (wieder) gefragt wird: nicht eingetragen, nicht zurückgestellt."""
        def documented(e):
            start, end = parse_time(e["start"]), parse_time(e["end"])
            covered = self.journal.covered_seconds(e["start"][:10], start, end)
            return covered >= (end - start).total_seconds() / 2

        self._idle_open = [e for e in self._idle_open if not documented(e)]
        self._idle_open = [e for e in self._idle_open if not self.journal.is_answered(e)]
        return [e for e in self._idle_open if not self._was_asked(e, now)]

    def _mark_asked(self, entry, until):
        """Nicht vor until wieder fragen: alle Teile des Themas und Zeitraum + Kunde."""
        # Abgelaufene Einträge zählen in _was_asked nicht mehr: wegwerfen, sonst wachsen beide
        # Listen bei tagelanger Laufzeit und _was_asked prüft jede Minute alle alten Zeiträume
        now = datetime.now()
        self._prompt_asked = {k: u for k, u in self._prompt_asked.items() if u > now}
        self._prompt_asked_spans = [(s, u) for s, u in self._prompt_asked_spans if u > now]
        for e in [entry] + sub_entries(entry):
            self._prompt_asked[journal_key(e)] = until
        self._prompt_asked_spans.append((prompt_topics.answer_span(entry, self.customer_index()), until))

    def _was_asked(self, entry, now):
        """Schon gefragt und zurückgestellt (oder als Meldung gezeigt)? Auch wenn sich der Eintrag
        seitdem verändert hat (andere Startzeit, Name nachgeladen, Thema um einen Teil gewachsen)."""
        if any(self._prompt_asked.get(journal_key(e), now) > now
               for e in [entry] + sub_entries(entry)):
            return True
        index = self.customer_index()
        return any(until > now and prompt_topics.matches_span(entry, span, index)
                   for span, until in self._prompt_asked_spans)

    def check_prompts(self):
        """Jede Minute: neu erkannte, noch nicht dokumentierte Tätigkeiten nachfragen."""
        mode = self.config.get("prompt_mode", "window")
        if self._quitting:
            return
        if mode == "off":  # keine Nachfragen, die Prüfung bei Feierabend läuft trotzdem
            self.end_of_day_reminder([], datetime.now())
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
            if self._was_asked(e, now):
                continue
            # Schon in der Warteschlange (auch als ähnliches, inzwischen gewachsenes Thema)?
            queued = [i for i, q in enumerate(self._prompt_queue) if journal_key(q) == key
                      or prompt_topics.matches_span(e, prompt_topics.answer_span(q, self.customer_index()))]
            if queued:
                self._prompt_queue[queued[0]] = e  # neuester Stand des Themas
            else:
                self._prompt_queue.append(e)
        idle = self._idle_pending(now)  # Abwesenheiten am PC
        for e in idle:
            if journal_key(e) not in (journal_key(q) for q in self._prompt_queue):
                self._prompt_queue.append(e)
        # inzwischen dokumentiert: nicht mehr fragen
        keys = {journal_key(e) for e in open_items + idle}
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
        # Abwesenheit immer als Fenster: Du bist gerade zurück und sitzt davor
        if self.config.get("prompt_mode") == "tray" and not force and not entry.get("idle"):
            if self.tray and not self._was_asked(entry, datetime.now()):
                self._mark_asked(entry, datetime.max)
                self._tray_doc_hint = True
                self.tray.showMessage("Was hast du gemacht?",
                                      f"{describe(entry)}\nKlick hier, um es einzutragen.",
                                      QSystemTrayIcon.Information, 10000)
            return
        categories = self.categories()
        hints = learning.doc_hints(entry, self.config, categories, self.customer_index())
        window = PromptWindow(entry, self.known_customers(), categories,
                              self.config.get("teamviewer_names", {}),
                              pending=len(self._prompt_queue) - 1, parent=self,
                              customer=hints["customer"], category=hints["category"],
                              trace=hints["trace"], rule_subject=hints["rule_subject"],
                              **self.entry_form_options(parse_time(entry["start"]),
                                                        parse_time(entry["end"])))
        window.form.set_billing(self.billing())
        window.answered.connect(self.on_prompt_answered)
        self._prompt_window = window
        # unten rechts über dem Infobereich, ohne dir den Fokus wegzunehmen
        window.adjustSize()
        window.dock_bottom_right(24)
        window.show()

    def on_prompt_answered(self, action, entry, item):
        window, self._prompt_window = self._prompt_window, None
        key = journal_key(entry)
        span = prompt_topics.answer_span(entry, self.customer_index())
        # auch ein inzwischen gewachsenes oder verändertes Thema aus der Warteschlange nehmen
        self._prompt_queue = [q for q in self._prompt_queue if journal_key(q) != key
                              and not prompt_topics.matches_span(q, span, self.customer_index())]
        if action in ("save", "ignore") and entry.get("idle"):
            self._idle_open = [e for e in self._idle_open if journal_key(e) != key]
        if action == "save":
            item["source"] = entry.get("type", "")
            if not self._save_doc(item, entry, window.remember_tv() if window else False,
                                  rule=window.wants_rule() if window else False):
                self._prompt_queue.insert(0, entry)
        elif action == "ignore":
            self.journal.ignore(entry)
            self.timeline.draw_timeline(self.current_date)
            self.statusBar().showMessage("Wird nicht mehr nachgefragt", 4000)
        else:  # später
            snooze = self.config.get("prompt_snooze_minutes", 15)
            self._mark_asked(entry, datetime.now() + timedelta(minutes=snooze))
            self.statusBar().showMessage(f"Zeitzeuge fragt in {snooze} Minuten noch einmal", 4000)
        if window:
            window.deleteLater()
        QTimer.singleShot(400, self.show_next_prompt)

    def end_of_day_reminder(self, open_items, now):
        """Nach Feierabend einmal am Tag erinnern: an offene Tätigkeiten und an das, was
        die Prüfung bei Feierabend findet (Pause, Stempelung, Buchungen, Quote)."""
        if not self.config.get("prompt_end_of_day", True):
            open_items = []  # Erinnerung an Offenes aus; die Prüfung hat ihren eigenen Schalter
        checks_on = self.config.get("day_checks_enabled", True)
        close_on = self.config.get("day_close_end_of_day", True) and hasattr(self, "day_close_hint")
        if not (self.tray and (open_items or checks_on or close_on)):
            return
        today = now.strftime("%Y-%m-%d")
        if self._reminded_day == today:
            return
        inputs = week_dialogs.day_inputs(self, today, now)
        if inputs["from_itm"] and inputs["spans"] and not inputs["running"]:
            # ausgestempelt: Feierabend nicht schon in der Mittagspause
            if not day_checks.after_hours(now, inputs["spans"], inputs["running"], inputs["planned_end"]):
                return
        else:
            _start, end = self.timeline._work_minutes(QDate.currentDate())
            if end <= _start or now.hour * 60 + now.minute < end:
                return
        findings = []
        if checks_on:
            rate = week_dialogs.rate_for(self, today, now, inputs)
            findings = week_dialogs.checks_for(self, today, now, inputs, rate)
        # Tagesabschluss (app_day_close.py): Vorschläge bereit? Dann öffnet der Klick ihn
        close_text = self.day_close_hint(today, now) if close_on else ""
        if not (open_items or findings or close_text):
            return
        self._reminded_day = today
        lines = [f"- {f.text}" for f in findings[:4]]
        if len(findings) > 4:
            lines.append(f"- und {len(findings) - 4} weitere (Knopf „Wochenabschluss“)")
        if close_text:  # Klick öffnet den Tagesabschluss; er enthält auch das Offene
            self._tray_close_hint = True
            title = ("Feierabend: noch nicht alles dokumentiert" if open_items else
                     "Feierabend: bitte prüfen" if findings else "Feierabend: Tagesabschluss bereit")
            text = f"Heute sind noch {len(open_items)} Tätigkeiten offen.\n" if open_items else ""
            text += f"{close_text} Klick hier zum Prüfen und Buchen."
            if lines:
                text += "\nAußerdem:\n" + "\n".join(lines)
            self.tray.showMessage(title, text, QSystemTrayIcon.Warning, 15000)
        elif open_items:
            self._tray_doc_hint = True
            text = f"Heute sind noch {len(open_items)} Tätigkeiten offen. Klick hier zum Nachtragen."
            if lines:
                text += "\nAußerdem:\n" + "\n".join(lines)
            self.tray.showMessage("Feierabend: noch nicht alles dokumentiert", text,
                                  QSystemTrayIcon.Warning, 15000)
        else:
            self._tray_week_hint = True
            self.tray.showMessage("Feierabend: bitte prüfen", "\n".join(lines) +
                                  "\nDetails im Wochenabschluss (Knopf in der Werkzeugleiste).", QSystemTrayIcon.Warning, 15000)

    # ---------------------- In Matrix42 buchen (m42_booking.py) -----------------

    def book_in_m42(self, item, parent=None):
        """Tätigkeit prüfen und in Matrix42 buchen. True, wenn gebucht; None bei Abbruch."""
        import m42_booking
        from m42_booking_dialogs import BookingDialog
        if self._foreign_doc(item):
            return None
        reader = getattr(self, "m42_reader", None)
        if reader is None:
            QMessageBox.information(parent or self, "In Matrix42 buchen",
                                    "Schalte zuerst Matrix42 ein: Einstellungen → Datenquellen → "
                                    "Matrix42-Buchungen (Firmennetz).")
            return None
        if item.get("m42_entry"):
            QMessageBox.information(parent or self, "In Matrix42 buchen",
                                    f"Diese Tätigkeit ist schon gebucht ({item['m42_entry']}).")
            return None
        plan = m42_booking.plan(item, self.billing(), self.config.get("ticket_format", ""))
        overlaps = m42_booking.overlaps(self._m42_bookings(plan["start"].strftime("%Y-%m-%d")),
                                        plan["start"], plan["end"], plan["ticket"])
        dialog = BookingDialog(plan, reader, overlaps, reader.activity_types or None,
                               self.config.get("m42_activity_type", m42_booking.DEFAULT_ACTIVITY_TYPE),
                               m42_booking.ids(self.config), parent or self)
        reader.load_activity_types()
        accepted = dialog.exec() == QDialog.Accepted
        entry, chosen = dialog.result_entry, dialog.type_edit.currentData()
        dialog.deleteLater()  # sonst bliebe es mit booking_done verbunden
        if not accepted or not entry:
            return None
        if chosen is not None and chosen != self.config.get("m42_activity_type"):
            self.config["m42_activity_type"] = chosen  # beim nächsten Mal vorbelegt
            mt.save_config(self.config)
        booked = dict(item, m42_entry=entry, m42_booked=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        if not item.get("ticket") and dialog.ticket_info:
            booked["ticket"] = m42_booking.normalize_ticket(dialog.ticket_edit.text())
        try:
            self.journal.update(item, booked)
        except (OSError, ValueError) as e:
            QMessageBox.warning(parent or self, "In Matrix42 buchen",
                                f"Gebucht als {entry}, aber in Zeitzeuge nicht vermerkt: {e}")
        self.timeline.draw_timeline(self.current_date)
        self.statusBar().showMessage(f"In Matrix42 gebucht: {entry}", 6000)
        return True

    def book_day_in_m42(self, date_str, parent=None):
        """Noch nicht gebuchte eigene Tätigkeiten eines Tages nacheinander buchen."""
        todo = [i for i in self.journal.items(date_str)
                if not i.get("m42_entry") and not i.get("von_pc")]
        if not todo:
            QMessageBox.information(parent or self, "In Matrix42 buchen",
                                    "An diesem Tag ist nichts mehr zu buchen.")
            return
        for item in todo:
            if self.book_in_m42(item, parent) is None:
                break  # abgebrochen: nicht weiter fragen

    def show_week(self):
        """Wochenabschluss: Buchungsquote, Lücken, Offenes und Prüfungen der Woche."""
        week_dialogs.WeekDialog(self, self.current_date.toString("yyyy-MM-dd")).exec()

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
