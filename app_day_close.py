"""Hauptfenster: Tagesabschluss (Spuren einsammeln, Fenster öffnen, Hinweis bei Feierabend).

Teil von TimelineApp (main_timeline.py), nur über main_timeline laden. Die Rechnung steht in
day_close.py (ohne Qt), das Fenster in day_close_dialog.py.
"""
from datetime import datetime, timedelta

from PySide6.QtCore import QDate

import customers as customer_list
import day_close
import learning
import prompt_topics
import week_dialogs
from grouping import group_entries
from timeline_only import OUTLOOK_TYPES


class DayCloseMixin:
    def day_close_internal(self):
        """Internes Ticket für Zeit ohne Kunden (Einstellung day_close_internal) oder None."""
        value = self.config.get("day_close_internal") or {}
        if isinstance(value, dict) and (value.get("customer") or "").strip():
            return {k: (value.get(k) or "").strip() for k in ("customer", "ticket", "category")}
        return None

    def day_close_evidence(self, date_str):
        """Spuren des Tages als [(Stufe, Eintrag)] für day_close.build (siehe dort)."""
        date = QDate.fromString(date_str, "yyyy-MM-dd")
        index = self.customer_index()
        activities = self.timeline.activities_for(date)
        grouped = group_entries([a for a in activities if a.get("type") not in OUTLOOK_TYPES],
                                self.config.get("merge_gap_minutes", 5))
        first = [e for e in grouped if self.prompt_kind(e) in ("connections", "calls")]
        first += self._attended_meetings(date, activities)
        first += [m for m in activities if m.get("type") == "Mail gesendet"
                  and customer_list.customer_for(m, index)]
        # „Nicht dokumentieren“ gilt auch hier
        first = [e for e in first if not self.journal.is_ignored(e)]
        evidence = [(1, e) for e in prompt_topics.build_topics(
            first, index, self.config.get("prompt_topic_gap_minutes", 15))]
        evidence += [(2, e) for e in self.ai_day_entries(date_str)
                     if e.get("status") not in ("verworfen", "übernommen")]
        evidence += [(3, b) for b in self.rule_band(date_str)
                     if not b.get("sources") or any(s.get("type") not in OUTLOOK_TYPES for s in b["sources"])]
        evidence += [(4, b) for b in self._pc_focus_blocks(date) if not self.journal.is_ignored(b)]
        return evidence

    def day_close_plan(self, date_str, now=None):
        """Buchungsvorschläge für einen Tag (day_close.build mit den Daten des Hauptfensters)."""
        now = now or datetime.now()
        inputs = week_dialogs.day_inputs(self, date_str, now)
        index = self.customer_index()
        categories = self.categories()
        hints = {}

        def hint(entry):
            if entry.get("ai"):
                return entry.get("customer_name", ""), entry.get("category", "")
            key = id(entry)
            if key not in hints:
                found = learning.doc_hints(entry, self.config, categories, index)
                customer = found["customer"]
                if not customer and entry.get("rule"):
                    customer = entry.get("customer_name", "")
                category = found["category"]
                if not category and entry.get("category") in categories:
                    category = entry["category"]
                hints[key] = (customer, category or "")
            return hints[key]

        def ticket_for(start, end):
            found = self.ticket_suggestions(start, end)
            return (found[0]["ticket"], ", ".join(found[0]["sources"][:2])) if found else ("", "")

        day = datetime.strptime(date_str, "%Y-%m-%d")
        recent = self.journal.recent_items(days=day_close.HISTORY_DAYS + 1, today=day)
        docs = [i for i in self.journal.items(date_str) if not i.get("von_pc")]
        return day_close.build(
            date_str, inputs["spans"], docs, self.day_close_evidence(date_str),
            inputs["bookings"] or [], hint=hint, ticket_for=ticket_for, recent=recent,
            gap_minutes=self.config.get("day_close_gap_minutes", day_close.GAP_MINUTES),
            min_minutes=self.config.get("day_close_min_minutes", day_close.MIN_MINUTES),
            internal=self.day_close_internal())

    def show_day_close(self, date_str=None, parent=None):
        """Fenster „Tagesabschluss“ für den angezeigten (oder angegebenen) Tag."""
        from day_close_dialog import DayCloseDialog
        date_str = date_str or self.current_date.toString("yyyy-MM-dd")
        dialog = DayCloseDialog(self, date_str, parent or self)
        dialog.exec()
        dialog.deleteLater()  # sonst bliebe es mit booking_done verbunden

    def day_close_hint(self, date_str, now=None):
        """Kurztext für die Meldung bei Feierabend, z. B. „Tagesabschluss: 4 Vorschläge, danach
        92 % der Personalzeit dokumentiert“. '' wenn es nichts vorzuschlagen gibt."""
        if not self.config.get("day_close_end_of_day", True):
            return ""
        # Die Prüfung bei Feierabend läuft jede Minute: ohne Vorschläge erst nach 10 Minuten neu rechnen
        now = now or datetime.now()
        last = getattr(self, "_day_close_hint_empty", None)
        if last and last[0] == date_str and now - last[1] < timedelta(minutes=10):
            return ""
        try:
            plan = self.day_close_plan(date_str, now)
        except Exception:  # der Hinweis darf die Erinnerung nie verhindern
            import safe_io
            safe_io.report("Tagesabschluss: Vorschläge für die Erinnerung gingen nicht")
            return ""
        todo = [r for r in plan["rows"] if r["checked"]]
        if not todo or plan["percent_after"] is None:
            self._day_close_hint_empty = (date_str, now)
            return ""
        return (f"Tagesabschluss: {len(todo)} Vorschl{'äge' if len(todo) != 1 else 'ag'} bereit, "
                f"danach {plan['percent_after']} % der Personalzeit erfasst.")
