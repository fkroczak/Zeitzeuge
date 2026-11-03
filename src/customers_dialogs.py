"""
Kundenliste: Dialog „Kundenliste …“ und die Befehle dazu im Hauptfenster.

- CustomersDialog: Kunden anlegen, umbenennen, löschen; je Kunde Spuren (TeamViewer-ID,
  RDM-Eintrag, VPN-Verbindung, Telefonnummer, E-Mail-Domain) hinzufügen und entfernen.
  Oben „Neu entdeckt“: Kunden, die in Matrix42 anders heißen (customer_discovery.py).
- Lernen aus Matrix42: auto_learn_customers übernimmt sichere Spuren von selbst, nach dem
  Start und wenn Matrix42 neue Buchungen gelesen hat.
- CustomersMixin: Teil von TimelineApp (über DocsMixin), Menü „Kundenliste …“,
  Rechtsklick „Kunde zuordnen …“, Index für Vorschläge und Anzeige.

Logik und Ablage in customers.py (ohne Qt).
"""
import copy
from datetime import datetime, timedelta

from PySide6.QtCore import QDate, Qt, QTimer
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QListWidget, QMessageBox,
                               QPushButton, QVBoxLayout)

from theme import prose
import customer_discovery as cdisc
import customers as cl
import main_timeline as mt  # save_config zur Laufzeit von dort (Tests ersetzen es dort)


class CustomersDialog(QDialog):
    """Kunden und ihre Spuren bearbeiten. Übernimmt erst mit OK (apply)."""

    def __init__(self, config, parent=None, suggestions=None):
        super().__init__(parent)
        self.config = config
        self.decisions = []  # (Vorschlag, Status) für customer_discovery.mark beim Übernehmen
        self.auto = {d.get("key") for d in config.get("customers_auto") or []
                     if isinstance(d, dict) and d.get("status") == "gelernt"}
        self.setWindowTitle("Kundenliste")
        self.setMinimumSize(620, 420)
        self.customers = copy.deepcopy(cl.customer_list(config))
        self.customers.sort(key=lambda c: c["name"].lower())

        layout = QVBoxLayout(self)
        info = QLabel("Ordne jedem Kunden seine Spuren zu: TeamViewer-ID, RDM-Eintrag, VPN, "
                      "Telefonnummer, E-Mail-Domain oder Stichwort (Text im Fenstertitel oder "
                      "Betreff). Zeitzeuge schlägt den Kunden dann beim Eintragen vor, zeigt ihn "
                      "in der Tagesliste und nimmt ihn im Tagesabschluss.")
        info.setWordWrap(True)
        prose(info)
        layout.addWidget(info)
        found = suggestions or {}
        self._add_suggestions(layout, (found.get("rename") or []) + (found.get("suggest") or []))

        columns = QHBoxLayout()
        # Links: Kunden
        left = QVBoxLayout()
        label = QLabel("&Kunden:")
        self.customer_list = QListWidget()
        label.setBuddy(self.customer_list)
        left.addWidget(label)
        left.addWidget(self.customer_list, 1)
        row = QHBoxLayout()
        self.new_btn = QPushButton("&Neu …")
        self.rename_btn = QPushButton("&Umbenennen …")
        self.delete_btn = QPushButton("&Löschen")
        for b in (self.new_btn, self.rename_btn, self.delete_btn):
            b.setAutoDefault(False)
            row.addWidget(b)
        left.addLayout(row)
        columns.addLayout(left, 1)

        # Rechts: Spuren des gewählten Kunden
        right = QVBoxLayout()
        label = QLabel("&Spuren des Kunden:")
        self.trace_list = QListWidget()
        label.setBuddy(self.trace_list)
        right.addWidget(label)
        right.addWidget(self.trace_list, 1)
        self.remove_btn = QPushButton("Spur &entfernen")
        self.remove_btn.setAutoDefault(False)
        right.addWidget(self.remove_btn, 0, Qt.AlignLeft)
        form = QFormLayout()
        self.kind_edit = QComboBox()
        for key in cl.KIND_ORDER:
            self.kind_edit.addItem(cl.KINDS[key], key)
        form.addRow("&Art:", self.kind_edit)
        self.value_edit = QLineEdit()
        form.addRow("&Wert:", self.value_edit)
        self.add_btn = QPushButton("Spur &hinzufügen")
        self.add_btn.setAutoDefault(False)
        form.addRow("", self.add_btn)
        right.addLayout(form)
        self.message = QLabel()
        self.message.setObjectName("hint")
        self.message.setWordWrap(True)
        right.addWidget(self.message)
        columns.addLayout(right, 1)
        layout.addLayout(columns, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.customer_list.currentRowChanged.connect(self._show_traces)
        self.trace_list.currentRowChanged.connect(lambda _r: self._update_buttons())
        self.new_btn.clicked.connect(lambda: self.add_customer())
        self.rename_btn.clicked.connect(lambda: self.rename_customer())
        self.delete_btn.clicked.connect(lambda: self.delete_customer())
        self.add_btn.clicked.connect(lambda: self.add_trace())
        self.remove_btn.clicked.connect(self.remove_trace)
        self.kind_edit.currentIndexChanged.connect(self._update_placeholder)
        self.value_edit.textChanged.connect(lambda _t: self._update_buttons())
        self._update_placeholder()
        self._fill(0)

    def _add_suggestions(self, layout, renames):
        """Kasten „Neu entdeckt“: Umbenennen in den Matrix42-Namen, Stichwort übernehmen
        oder ignorieren."""
        self.suggestion_rows = []
        if not renames:
            return
        title = QLabel("<b>Neu entdeckt</b> – aus deinen Matrix42-Buchungen:")
        layout.addWidget(title)
        for item in renames[:6]:
            row = QHBoxLayout()
            text = QLabel(cdisc.describe(item))
            text.setWordWrap(True)
            take = QPushButton("Übernehmen" if "kind" in item else "Umbenennen")
            skip = QPushButton("Ignorieren")
            for b in (take, skip):
                b.setAutoDefault(False)
            row.addWidget(text, 1)
            row.addWidget(take)
            row.addWidget(skip)
            layout.addLayout(row)
            widgets = (text, take, skip)
            self.suggestion_rows.append((item, widgets))
            take.clicked.connect(lambda _c=False, i=item, w=widgets: self.take_suggestion(i, w))
            skip.clicked.connect(lambda _c=False, i=item, w=widgets: self.skip_suggestion(i, w))

    def _close_suggestion(self, widgets, text):
        widgets[0].setText(text)
        for b in widgets[1:]:
            b.hide()

    def take_suggestion(self, item, widgets=None):
        """„Holger Tenbrink“ -> „H.Tenbrink Montage GmbH“ (gibt es den schon: Spuren dorthin).
        Bei einer Spur (Stichwort): dem Kunden geben, den es dafür noch nicht gibt, anlegen."""
        if "kind" in item:
            cl._assign(self.customers, item["kind"], item["value"], item["customer"])
            self.customers.sort(key=lambda c: c["name"].lower())
            self._fill(next(i for i, c in enumerate(self.customers) if c["name"] == item["customer"]))
            self.decisions.append((item, "übernommen"))
            if widgets:
                self._close_suggestion(widgets, f"✓ {cl.display(item['kind'], item['value'])} gehört "
                                                f"jetzt zu „{item['customer']}“.")
            return True
        source = next((c for c in self.customers if c["name"] == item["name"]), None)
        if source is None:
            return False
        target = next((c for c in self.customers if c is not source
                       and c["name"].casefold() == item["to"].casefold()), None)
        if target is None:
            source["name"] = item["to"]
        else:
            target["traces"] += source["traces"]
            self.customers.remove(source)
        self.customers.sort(key=lambda c: c["name"].lower())
        self._fill(next(i for i, c in enumerate(self.customers) if c["name"].casefold() == item["to"].casefold()))
        self.decisions.append((item, "umbenannt"))
        if widgets:
            self._close_suggestion(widgets, f"✓ „{item['name']}“ heißt jetzt „{item['to']}“.")
        return True

    def skip_suggestion(self, item, widgets=None):
        self.decisions.append((item, "ignoriert"))
        if widgets:
            what = cl.display(item["kind"], item["value"]) if "kind" in item else f"„{item['name']}“"
            self._close_suggestion(widgets, f"{what}: ignoriert (kommt nicht wieder).")

    PLACEHOLDERS = {"tv": "z. B. 1 076 789 144", "rdm": "Name des Eintrags in RDM",
                    "vpn": "Name der Verbindung, z. B. in Sophos Connect",
                    "phone": "z. B. +49 711 123456", "mail": "z. B. @kunde.de",
                    "net": "Name des Netzwerks, z. B. Mueller-Gast",
                    "word": "Text im Fenstertitel oder Betreff, z. B. Nordhafen oder SWN-"}

    # ------------------------------------------------------------ Anzeige

    def _current(self):
        row = self.customer_list.currentRow()
        return self.customers[row] if 0 <= row < len(self.customers) else None

    def _fill(self, select=0):
        self.customer_list.blockSignals(True)
        self.customer_list.clear()
        for c in self.customers:
            n = len(c["traces"])
            self.customer_list.addItem(f"{c['name']} ({n} Spur{'en' if n != 1 else ''})")
        self.customer_list.blockSignals(False)
        if self.customers:
            self.customer_list.setCurrentRow(max(0, min(select, len(self.customers) - 1)))
        self._show_traces()

    def _show_traces(self, *_):
        self.trace_list.clear()
        current = self._current()
        for t in (current or {}).get("traces", []):
            auto = cdisc.key({"kind": t["kind"], "value": t["value"]}) in self.auto
            self.trace_list.addItem(cl.display(t["kind"], t["value"])
                                    + (" (aus Matrix42 gelernt)" if auto else ""))
        self._update_buttons()

    def _update_placeholder(self, *_):
        self.value_edit.setPlaceholderText(self.PLACEHOLDERS.get(self.kind_edit.currentData(), ""))
        self._update_buttons()

    def _update_buttons(self):
        has = self._current() is not None
        self.rename_btn.setEnabled(has)
        self.delete_btn.setEnabled(has)
        self.add_btn.setEnabled(has and bool(self.value_edit.text().strip()))
        self.remove_btn.setEnabled(has and self.trace_list.currentRow() >= 0)
        for w in (self.kind_edit, self.value_edit):
            w.setEnabled(has)

    def _say(self, text):
        self.message.setText(text)

    # ------------------------------------------------------------ Kunden

    def _ask_name(self, title, text=""):
        name, ok = QInputDialog.getText(self, title, "Name des Kunden:", text=text)
        return name.strip() if ok else ""

    def _exists(self, name, other_than=None):
        return any(c["name"].casefold() == name.casefold() and c is not other_than
                   for c in self.customers)

    def add_customer(self, name=None):
        name = (name if name is not None else self._ask_name("Neuer Kunde")).strip()
        if not name:
            return False
        if self._exists(name):
            self._say(f"⚠ „{name}“ gibt es schon.")
            return False
        self.customers.append({"name": name, "traces": []})
        self.customers.sort(key=lambda c: c["name"].lower())
        self._fill(next(i for i, c in enumerate(self.customers) if c["name"] == name))
        self._say(f"„{name}“ angelegt. Füge jetzt rechts die Spuren hinzu.")
        self.value_edit.setFocus()
        return True

    def rename_customer(self, name=None):
        current = self._current()
        if current is None:
            return False
        name = (name if name is not None else self._ask_name("Kunde umbenennen", current["name"])).strip()
        if not name or name == current["name"]:
            return False
        if self._exists(name, other_than=current):
            self._say(f"⚠ „{name}“ gibt es schon.")
            return False
        current["name"] = name
        self.customers.sort(key=lambda c: c["name"].lower())
        self._fill(self.customers.index(current))
        self._say(f"Umbenannt in „{name}“.")
        return True

    def delete_customer(self, ask=True):
        current = self._current()
        if current is None:
            return False
        if ask and current["traces"] and QMessageBox.question(
                self, "Kunde löschen",
                f"„{current['name']}“ mit {len(current['traces'])} Spuren löschen? "
                "Deine Tätigkeiten bleiben erhalten.") != QMessageBox.Yes:
            return False
        row = self.customers.index(current)
        del self.customers[row]
        self._fill(row)
        self._say(f"„{current['name']}“ gelöscht.")
        return True

    # ------------------------------------------------------------ Spuren

    def add_trace(self, kind=None, value=None):
        current = self._current()
        if current is None:
            return False
        kind = kind or self.kind_edit.currentData()
        value = self.value_edit.text() if value is None else value
        if not cl.normalize(kind, value):
            hints = {"tv": "nur Ziffern", "phone": "mindestens 3 Ziffern",
                     "mail": "z. B. @kunde.de"}
            self._say(f"⚠ Ungültige {cl.KINDS[kind]} ({hints.get(kind, 'leer')}).")
            return False
        key = cl.normalize(kind, value)
        before = next((c["name"] for c in self.customers if c is not current and any(
            t["kind"] == kind and cl.normalize(kind, t["value"]) == key for t in c["traces"])), "")
        cl._assign(self.customers, kind, value, current["name"])
        self._fill(self.customers.index(current))
        self.value_edit.clear()
        text = f"{cl.display(kind, cl.clean_value(kind, value))} hinzugefügt."
        if before:
            text += f" Sie gehörte bisher zu „{before}“."
        self._say(text)
        return True

    def remove_trace(self):
        current = self._current()
        row = self.trace_list.currentRow()
        if current is None or not 0 <= row < len(current["traces"]):
            return False
        t = current["traces"].pop(row)
        self._fill(self.customers.index(current))
        self.trace_list.setCurrentRow(min(row, self.trace_list.count() - 1))
        self._say(f"{cl.display(t['kind'], t['value'])} entfernt.")
        return True

    def apply(self):
        cl.apply_list(self.config, self.customers)
        for item, status in self.decisions:
            cdisc.mark(self.config, item, status)


class CustomersMixin:
    """Befehle im Hauptfenster (über DocsMixin Teil von TimelineApp)."""

    def customer_index_list(self):
        return cl.customer_list(self.config)

    def customer_index(self):
        """Index der eigenen Kundenliste plus übernommener Daten eines anderen PCs."""
        imported = getattr(self, "imported", None)
        return cl.index(self.config,
                        imported.customers() if imported and hasattr(imported, "customers") else None,
                        imported.teamviewer_names() if imported else None)

    # ------------------------------------------------------------ Lernen aus Matrix42

    DISCOVERY_DAYS = 42      # so viele Tage zurück vergleichen
    DISCOVERY_DELAY_MS = 90_000

    def init_customer_discovery(self):
        """Nach dem Start (verzögert) und nach neuen Matrix42-Buchungen lernen."""
        self._discovery_timer = QTimer(self)
        self._discovery_timer.setSingleShot(True)
        self._discovery_timer.timeout.connect(self.auto_learn_customers)
        self.schedule_customer_discovery()

    def schedule_customer_discovery(self):
        timer = getattr(self, "_discovery_timer", None)
        if timer is not None:
            timer.start(self.DISCOVERY_DELAY_MS)  # Matrix42 liest wochenweise: einmal danach

    def discover_customers(self, now=None):
        """Vorschläge aus den letzten DISCOVERY_DAYS Tagen (customer_discovery.discover)."""
        now = now or datetime.now()
        entries, bookings = [], []
        for back in range(1, self.DISCOVERY_DAYS + 1):
            day = now - timedelta(days=back)
            found = self._m42_bookings(day.strftime("%Y-%m-%d"))
            if not found:
                continue
            bookings += found
            date = QDate(day.year, day.month, day.day)
            entries += self.timeline.activities_for(date)
            entries += self.timeline.pc_entries_for(date, min_seconds=30)  # Stichwörter in Titeln
        self.timeline.activities_for(self.current_date)  # Zwischenstand des angezeigten Tags zurück
        return cdisc.discover(entries, bookings, cl.customer_list(self.config),
                              ignored=cdisc.decided(self.config))

    def auto_learn_customers(self, now=None):
        """Sichere Spuren übernehmen; Umbenennungen bleiben Vorschlag. Gibt die Vorschläge zurück."""
        try:
            found = self.discover_customers(now)
        except Exception:  # Lernen darf nie stören
            import safe_io
            safe_io.report("Kundenliste: Lernen aus Matrix42 ging nicht")
            return {"learn": [], "rename": []}
        self._customer_suggestions = found
        if not self.config.get("customers_auto_learn", True):
            return found
        applied = cdisc.auto_apply(self.config, found)
        if found["learn"]:
            mt.save_config(self.config)
        if applied:
            self.timeline.draw_timeline(self.current_date)
            text = (f"Kundenliste: {len(applied)} Spur{'en' if len(applied) != 1 else ''} aus "
                    f"Matrix42 gelernt, z. B. {cdisc.describe(applied[0])}")
            open_ = len(found["rename"]) + len(found.get("suggest") or [])
            if open_:
                text += f" · {open_} Vorschl{'äge' if open_ != 1 else 'ag'} in der Kundenliste"
            self.statusBar().showMessage(text, 8000)
        return found

    def edit_customers(self):
        dialog = CustomersDialog(self.config, self, getattr(self, "_customer_suggestions", None))
        if dialog.exec() == QDialog.Accepted:
            dialog.apply()
            mt.save_config(self.config)
            self.timeline.draw_timeline(self.current_date)
            self.statusBar().showMessage("Kundenliste gespeichert", 3000)

    def assign_customer(self, entry):
        """Rechtsklick „Kunde zuordnen …“: Spur des Eintrags einem Kunden geben."""
        trace = cl.primary_trace(entry)
        if not trace:
            return
        kind, value = trace
        names = self.known_customers() if hasattr(self, "known_customers") else []
        current = self.customer_index().customer_for(entry)
        items = [current] + [n for n in names if n != current] if current else [""] + names
        name, ok = QInputDialog.getItem(
            self, "Kunde zuordnen", f"Kunde für {cl.display(kind, cl.clean_value(kind, value))}:",
            items, 0, True)
        if not ok or not name.strip():
            return
        cl.learn(self.config, kind, value, name.strip())
        mt.save_config(self.config)
        self.timeline.draw_timeline(self.current_date)
        self.statusBar().showMessage(
            f"{cl.display(kind, cl.clean_value(kind, value))} gehört jetzt zu „{name.strip()}“", 4000)
