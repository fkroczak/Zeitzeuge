"""
Dialoge zum Eintragen von Tätigkeiten.

- EntryDialog: Tätigkeit nachtragen oder ändern (Zeit, Kunde, Kategorie, Text).
- PromptWindow, PromptStrip (prompt_card.py): Nachfrage nach einer erkannten Tätigkeit
  als Karte, kompakt oder als schmale Leiste ("Was hast du bei Beispiel AG gemacht?").
"""

from datetime import datetime, timedelta

import re

from PySide6.QtCore import QDate, QEvent, QLocale, QModelIndex, QSize, Qt, QTime, QTimer, Signal
from PySide6.QtGui import QIcon, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QCompleter, QDateEdit, QDialog,
                               QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenu, QPlainTextEdit,
                               QPushButton, QSpinBox, QTimeEdit, QToolButton, QVBoxLayout,
                               QWidget)

from theme import theme_for, SPACE_M, SPACE_S, SPACE_XS
from flow_layout import FlowLayout
import icons
from billing import hours_text
import customers as customer_list
from grouping import format_tv_id
from journal import TIME_FMT
import range_context
import snippets as snippet_logic
from m42_booking import ticket_label as mb_ticket_label
from tickets import format_ticket_text
from prompt_card import CardParts, _ElidedLabel, _icon_label, source_tile


class _EntryForm(QWidget):
    """Gemeinsame Felder: Datum, Von, Bis, Kunde, Kategorie, Text."""

    def __init__(self, start, end, customers, categories, customer="", category="", text="",
                 tv_id=None, parent=None, show_date=True, snippets=(), recent_texts=None,
                 ticket="", ticket_suggestions=(), show_ticket=True, trace=None, rule_subject=None,
                 goodwill=False, travel=False, no_surcharge=False, ticket_search=None,
                 ticket_lookup=None, flag_details=None, travel_guess=None):
        super().__init__(parent)
        # flag_details: gespeicherte Angaben zu Kulanz/Reise (goodwill_minutes, goodwill_reason,
        # travel_location, travel_departure, travel_km). travel_guess(start, end) -> dict mit
        # location/departure/km aus der vermuteten Fahrt oder None (füllt beim Anhaken vor).
        self.travel_guess = travel_guess
        # ticket_search: Funktion (Suchtext, Fenster) -> Ticket-dict oder None (Matrix42-Suche)
        # ticket_lookup: Funktion (Elternobjekt) -> TicketLookup, Suche beim Tippen im Feld Ticket
        self.ticket_search = ticket_search
        self.ticket_lookup = ticket_lookup
        # trace: (Art, Wert) der Spur, zu der der Kunde gemerkt werden kann (customers.py).
        # rule_subject: Name, zu dem eine geänderte Kategorie als Regel gemerkt werden kann.
        if trace is None and tv_id:
            trace = ("tv", tv_id)
        self.trace = trace
        self.rule_subject = rule_subject
        self._suggested_customer = (customer or "").strip()
        self._suggested_category = (category or "").strip()
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        form.setVerticalSpacing(SPACE_S)  # kompakt: Nachfrage-Fenster nicht höher als nötig

        self.date_edit = QDateEdit(QDate(start.year, start.month, start.day))
        self.date_edit.setLocale(QLocale(QLocale.German, QLocale.Germany))  # "Mi" statt "Wed"
        self.date_edit.setDisplayFormat("ddd dd.MM.yyyy")
        self.date_edit.setCalendarPopup(True)
        if not show_date:
            self.date_edit.hide()

        times = QHBoxLayout()
        times.setSpacing(SPACE_S)
        self.start_edit = QTimeEdit(QTime(start.hour, start.minute))
        self.end_edit = QTimeEdit(QTime(end.hour, end.minute) if end.date() == start.date()
                                  else QTime(23, 59))
        for edit in (self.start_edit, self.end_edit):
            edit.setDisplayFormat("HH:mm")
        self.start_edit.setAccessibleName("Von")
        self.end_edit.setAccessibleName("Bis")
        bis = QLabel("&bis")
        bis.setBuddy(self.end_edit)
        von = QLabel("&von" if show_date else "&Von:")
        von.setBuddy(self.start_edit)
        if show_date:  # Datum und Uhrzeit in einer Zeile
            times.addWidget(self.date_edit)
            times.addWidget(von)
        times.addWidget(self.start_edit)
        times.addWidget(bis)
        times.addWidget(self.end_edit)
        self.duration = QLabel()
        self.duration.setObjectName("hint")
        self.duration.setWordWrap(True)
        times.addWidget(self.duration, 1)
        if show_date:
            date_label = QLabel("&Datum:")
            date_label.setBuddy(self.date_edit)
            form.addRow(date_label, times)
        else:
            form.addRow(von, times)

        self.customer_edit = QComboBox()
        self.customer_edit.setEditable(True)
        self.customer_edit.setInsertPolicy(QComboBox.NoInsert)
        self.customer_edit.addItems([""] + [c for c in customers if c])
        self.customer_edit.setCurrentText(customer)
        self.customer_edit.lineEdit().setPlaceholderText(
            f"Kunde für {customer_list.display(*trace)}" if trace else "Kunde oder System")
        self.customer_edit.lineEdit().setAccessibleName("Kunde")
        form.addRow("&Kunde:", self.customer_edit)

        # Kunde zur Spur merken (Kundenliste). TeamViewer wie bisher immer sichtbar,
        # andere Spuren erst, wenn du den vorgeschlagenen Kunden änderst.
        self.remember_tv = None
        if trace:
            label = (f"Name für TeamViewer-ID {format_tv_id(trace[1])} merken" if trace[0] == "tv"
                     else f"Kunde für {customer_list.display(*trace)} &merken")
            self.remember_tv = QCheckBox(label)
            self.remember_tv.setChecked(True)
            form.addRow("", self.remember_tv)
            if trace[0] != "tv":
                self.customer_edit.currentTextChanged.connect(self._update_learning)

        self.category_edit = QComboBox()
        self.category_edit.setEditable(True)
        self.category_edit.addItems([""] + list(categories))
        self.category_edit.setCurrentText(category)
        self.category_edit.lineEdit().setAccessibleName("Kategorie")
        form.addRow("Kate&gorie:", self.category_edit)

        # Kategorie geändert: als Regel für die Zuordnung ohne KI merken (nur wenn angehakt)
        self.learn_rule = None
        if rule_subject:
            self.learn_rule = QCheckBox()
            self.learn_rule.setChecked(False)
            self.learn_rule.setToolTip("Legt eine Regel in „Zuordnung ohne KI“ an. "
                                       "Zeitzeuge schlägt die Kategorie dann selbst vor.")
            form.addRow("", self.learn_rule)
            self.category_edit.currentTextChanged.connect(self._update_learning)
        self._update_learning()

        # Wie in der Matrix42-Zeiterfassung: Kulanz (nicht berechnen) und Reise (Anfahrt)
        self.goodwill_box = QCheckBox("K&ulanz")
        self.goodwill_box.setToolTip("Nicht berechnen. Wird beim Buchen in Matrix42 als Kulanz übernommen.")
        self.goodwill_box.setChecked(bool(goodwill))
        self.travel_box = QCheckBox("&Reise / Anfahrt")
        self.travel_box.setToolTip("Fahrzeit. Wird beim Buchen in Matrix42 als Reise übernommen.")
        self.travel_box.setChecked(bool(travel))
        self.surcharge_box = QCheckBox("&Zuschlag ignorieren")
        self.surcharge_box.setToolTip("Keine Zuschläge (z. B. außerhalb der Servicezeit). "
                                      "Wird beim Buchen in Matrix42 übernommen.")
        self.surcharge_box.setChecked(bool(no_surcharge))
        flags = QHBoxLayout()
        flags.addWidget(self.goodwill_box)
        flags.addWidget(self.travel_box)
        flags.addWidget(self.surcharge_box)
        flags.addStretch(1)
        self._flags_row = flags  # rechts daneben „Text einfügen“ (_add_text_helpers)
        form.addRow("", flags)
        self._build_flag_details(form, flag_details or {})

        self.text_edit = QPlainTextEdit(text)
        self.text_edit.setPlaceholderText("Was hast du gemacht? z. B. „Drucker neu eingerichtet, "
                                          "Treiber aktualisiert“")
        self.text_edit.setTabChangesFocus(True)
        self.text_edit.setFixedHeight(64)
        form.addRow("&Tätigkeit:", self.text_edit)
        self._add_text_helpers(form, snippets, recent_texts, ticket, ticket_suggestions, show_ticket)

        self.error = QLabel()
        self.error.setObjectName("hint")
        self.error.setWordWrap(True)
        self.error.hide()  # nur mit Fehler eine eigene Zeile
        form.addRow("", self.error)

        for edit in (self.start_edit, self.end_edit):
            edit.timeChanged.connect(self.validate)
        self.validate_hook = None
        self.billing = None  # billing.Billing: "abgerechnet …" neben der Dauer (set_billing)
        self.customer_edit.currentTextChanged.connect(lambda _t: self.validate())
        self.validate()

    # ---- Angaben zu Kulanz und Reise (erscheinen erst, wenn angehakt)

    def _build_flag_details(self, form, details):
        def field(grid, col, name, widget):
            label = QLabel(name)
            label.setObjectName("prompt_label")
            label.setBuddy(widget)
            grid.addWidget(label, 0, col)
            grid.addWidget(widget, 1, col)

        def panel():
            host = QWidget()
            host.setObjectName("flag_details")
            grid = QGridLayout(host)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(SPACE_M)
            grid.setVerticalSpacing(SPACE_XS)
            return host, grid

        # Kulanz: wie viel der Zeit nicht berechnet wird und warum (Matrix42 will einen Grund)
        self.goodwill_panel, grid = panel()
        self.goodwill_minutes = QSpinBox()
        self.goodwill_minutes.setRange(1, 24 * 60)
        self.goodwill_minutes.setSuffix(" min")
        self.goodwill_minutes.setAccessibleName("Kulanzzeit in Minuten")
        self.goodwill_minutes.setToolTip("So viel der Zeit wird nicht berechnet (Standard: alles)")
        self._goodwill_minutes_set = bool(details.get("goodwill_minutes"))
        self.goodwill_minutes.setValue(int(details.get("goodwill_minutes") or 0) or self._minutes())
        self.goodwill_minutes.valueChanged.connect(lambda _v: setattr(self, "_goodwill_minutes_set", True))
        self.goodwill_reason = QLineEdit(str(details.get("goodwill_reason") or ""))
        self.goodwill_reason.setPlaceholderText("z. B. Nacharbeit, eigener Fehler, Kundenbindung")
        self.goodwill_reason.setAccessibleName("Grund für die Kulanz")
        field(grid, 0, "Kulanz&zeit", self.goodwill_minutes)
        field(grid, 1, "Kulanz&grund", self.goodwill_reason)
        grid.setColumnStretch(1, 1)
        form.addRow("", self.goodwill_panel)

        # Reise: wohin, wann los, wie weit (aus der vermuteten Fahrt vorbelegt)
        self.travel_panel, grid = panel()
        self.travel_location = QLineEdit(str(details.get("travel_location") or ""))
        self.travel_location.setPlaceholderText("Ort oder Adresse beim Kunden")
        self.travel_location.setAccessibleName("Reiseziel")
        self.travel_departure = QTimeEdit()
        self.travel_departure.setDisplayFormat("HH:mm")
        self.travel_departure.setAccessibleName("Abfahrt")
        departure = QTime.fromString(str(details.get("travel_departure") or ""), "HH:mm")
        self.travel_departure.setTime(departure if departure.isValid() else self.start_edit.time())
        self.travel_km = QSpinBox()
        self.travel_km.setRange(0, 2000)
        self.travel_km.setSuffix(" km")
        self.travel_km.setSpecialValueText("– km")
        self.travel_km.setAccessibleName("Anfahrt in Kilometern")
        self.travel_km.setValue(int(details.get("travel_km") or 0))
        self.travel_note = QLabel()
        self.travel_note.setObjectName("hint")
        self.travel_note.hide()
        field(grid, 0, "Reise&ziel", self.travel_location)
        field(grid, 1, "&Abfahrt", self.travel_departure)
        field(grid, 2, "Anfahrt", self.travel_km)
        grid.addWidget(self.travel_note, 2, 0, 1, 3)
        grid.setColumnStretch(0, 1)
        form.addRow("", self.travel_panel)

        self.goodwill_box.toggled.connect(self._goodwill_toggled)
        self.travel_box.toggled.connect(self._travel_toggled)
        self.goodwill_panel.setVisible(self.goodwill_box.isChecked())
        self.travel_panel.setVisible(self.travel_box.isChecked())

    def _minutes(self):
        start, end = self.times()
        return max(1, int((end - start).total_seconds() // 60))

    def _goodwill_toggled(self, on):
        self.goodwill_panel.setVisible(on)
        if on:
            if not self._goodwill_minutes_set:  # noch nicht verändert: die ganze Zeit
                self.goodwill_minutes.blockSignals(True)
                self.goodwill_minutes.setValue(self._minutes())
                self.goodwill_minutes.blockSignals(False)
            if not self.goodwill_reason.text().strip():
                self.goodwill_reason.setFocus()

    def _travel_toggled(self, on):
        self.travel_panel.setVisible(on)
        if on and not self.travel_location.text().strip() and not self.travel_km.value():
            self.prefill_travel()

    def prefill_travel(self):
        """Ziel, Abfahrt und Kilometer aus der vermuteten Fahrt (travel.py), wenn es eine gibt."""
        guess = None
        if self.travel_guess is not None:
            try:
                guess = self.travel_guess(*self.times())
            except Exception as e:  # Vorbelegen darf das Eintragen nie stören
                print(f"Reise vorbelegen ging nicht: {e}")
        if not guess:
            self.travel_note.setText("Keine vermutete Fahrt in dieser Zeit. Bitte selbst eintragen.")
            self.travel_note.show()
            return
        if guess.get("location"):
            self.travel_location.setText(guess["location"])
        departure = QTime.fromString(guess.get("departure") or "", "HH:mm")
        if departure.isValid():
            self.travel_departure.setTime(departure)
        if guess.get("km"):
            self.travel_km.setValue(int(guess["km"]))
        self.travel_note.setText(f"Vorbelegt aus der vermuteten Fahrt ({guess.get('label') or 'Fahrt'}).")
        self.travel_note.show()

    def flag_details(self):
        """Angaben zu Kulanz und Reise, nur für angehakte Merker."""
        result = {}
        if self.goodwill_box.isChecked():
            result["goodwill_minutes"] = min(self.goodwill_minutes.value(), self._minutes())
            result["goodwill_reason"] = self.goodwill_reason.text().strip() or "Kulanz"
        if self.travel_box.isChecked():
            result["travel_location"] = self.travel_location.text().strip()
            result["travel_departure"] = self.travel_departure.time().toString("HH:mm")
            if self.travel_km.value():
                result["travel_km"] = self.travel_km.value()
        return result

    def set_billing(self, billing):
        self.billing = billing
        self.validate()

    # ---- Textbausteine, zuletzt benutzte Texte, Ticket (snippets.py, tickets.py)

    def _add_text_helpers(self, form, snippets, recent_texts, ticket, suggestions, show_ticket):
        self.snippets = list(snippets or [])
        self.recent_texts = recent_texts  # Funktion Kunde -> [Texte] oder None
        self.insert_button = QPushButton("Text &einfügen")
        self.insert_button.setAutoDefault(False)
        self.insert_button.setAccessibleName("Textbaustein oder zuletzt benutzten Text einfügen")
        self.insert_button.setToolTip("Textbaustein oder zuletzt benutzten Text zum Kunden "
                                      "an der Cursorposition einfügen")
        self.insert_menu = QMenu(self.insert_button)
        self.insert_menu.aboutToShow.connect(self._fill_insert_menu)
        self.insert_button.setMenu(self.insert_menu)
        # In der Zeile Kulanz / Reise / Zuschlag, direkt über dem Textfeld: spart eine Zeile
        self._flags_row.addWidget(self.insert_button)

        # Ticket: nur Vorschläge, nie automatisch eingesetzt
        self.ticket_suggestions = list(suggestions or [])
        self.ticket_edit = QComboBox()
        self.ticket_edit.setEditable(True)
        self.ticket_edit.setInsertPolicy(QComboBox.NoInsert)
        self.ticket_edit.addItem("")
        for s in self.ticket_suggestions:
            self.ticket_edit.addItem(s["ticket"])
            self.ticket_edit.setItemData(self.ticket_edit.count() - 1, s["label"], Qt.ToolTipRole)
        self.ticket_edit.setCurrentText(ticket)
        self.ticket_edit.setAccessibleName("Ticket")
        self.ticket_edit.lineEdit().setAccessibleName("Ticket")
        top = self.ticket_suggestions[0]["label"] if self.ticket_suggestions else ""
        self.ticket_edit.lineEdit().setPlaceholderText(f"Gefunden: {top}" if top
                                                       else "Ticketnummer, z. B. TCK0000049374")
        self.ticket_take = QPushButton("&Übernehmen")
        self.ticket_take.setAutoDefault(False)
        self.ticket_take.setAccessibleName("Gefundenes Ticket übernehmen")
        self.ticket_take.setToolTip(f"{top} ins Feld „Ticket“ übernehmen" if top else "")
        self.ticket_take.clicked.connect(self._take_ticket)
        self.ticket_edit.currentTextChanged.connect(self._update_ticket_take)
        ticket_row = QHBoxLayout()
        ticket_row.addWidget(self.ticket_edit, 1)
        ticket_row.addWidget(self.ticket_take)
        self.ticket_search_button = None
        if self.ticket_search:
            self.ticket_search_button = QPushButton("Su&chen …")
            self.ticket_search_button.setAutoDefault(False)
            self.ticket_search_button.setAccessibleName("Ticket in Matrix42 suchen")
            self.ticket_search_button.setToolTip("Ticket in Matrix42 nach Kunde, Benutzer, "
                                                 "Ticketnummer oder Titel suchen")
            self.ticket_search_button.clicked.connect(self._search_ticket)
            ticket_row.addWidget(self.ticket_search_button)
        self.ticket_status = QLabel()
        self.ticket_status.setObjectName("hint")
        self.ticket_status.setWordWrap(True)
        self.ticket_status.hide()
        self._setup_ticket_lookup()
        self._lookup_suggested_ticket()
        if show_ticket or ticket or self.ticket_suggestions or self.ticket_search:
            label = QLabel("T&icket:")
            label.setBuddy(self.ticket_edit)
            form.addRow(label, ticket_row)
            form.addRow("", self.ticket_status)
        else:  # kleines Nachfrage-Fenster: ohne Vorschlag keine Zeile
            self.ticket_edit.hide()
        self._update_ticket_take()

    # Suche beim Tippen: „Lesana Telefon“ ins Feld Ticket, Treffer aus Matrix42 darunter
    LOOKUP_DELAY_MS = 500
    TICKET_NUMBER = re.compile(r"^[A-Za-z]{2,5}\d{4,}$")

    def _setup_ticket_lookup(self):
        self._lookup = self.ticket_lookup(self) if self.ticket_lookup else None
        if self._lookup is None:
            return
        self.ticket_edit.lineEdit().setPlaceholderText(
            self.ticket_edit.lineEdit().placeholderText() + " · oder Kunde/Titel tippen (Matrix42)")
        self._lookup_model = QStandardItemModel(self)
        self._completer = QCompleter(self._lookup_model, self)
        self._completer.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
        self._completer.setWidget(self.ticket_edit.lineEdit())
        self._completer.activated[QModelIndex].connect(self._pick_lookup)
        self._lookup_timer = QTimer(self)
        self._lookup_timer.setSingleShot(True)
        self._lookup_timer.setInterval(self.LOOKUP_DELAY_MS)
        self._lookup_timer.timeout.connect(self._start_lookup)
        self._lookup.found.connect(self._on_lookup)
        self.ticket_edit.lineEdit().textEdited.connect(self._ticket_typed)

    def _lookup_suggested_ticket(self):
        """Vorgeschlagenes Ticket in Matrix42 nachschlagen: Titel und Kunde im Vorschlag zeigen."""
        self._details_for = None
        self.ticket_details = None  # Matrix42-Zeile zum Vorschlag (ticket, subject, customer, …)
        if self._lookup is None or not self.ticket_suggestions:
            return
        self._details_for = self.ticket_suggestions[0]["ticket"]
        self._lookup.lookup(self._details_for)

    def _on_details(self, rows):
        number = (self._details_for or "").upper()
        row = next((r for r in rows if (r.get("ticket") or "").upper() == number), None)
        if row is None:
            return
        self.ticket_details = row
        self.render_ticket_take()

    DETAIL_MAX = 50  # Zeichen für Titel und Kunde im Vorschlag, der Rest im Tooltip

    def suggestion_text(self):
        """'TCK… · Titel · Kunde (Matrix42, 11 min)' oder nur das Label ohne Matrix42-Daten."""
        if not self.ticket_suggestions:
            return ""
        top = self.ticket_suggestions[0]
        row = self.ticket_details
        if not row:
            return top["label"]
        parts = [(row.get(k) or "").strip() for k in ("subject", "customer")]
        parts = [p if len(p) <= self.DETAIL_MAX else p[:self.DETAIL_MAX - 1] + "…" for p in parts if p]
        rest = top["label"][len(top["ticket"]):]  # " (Matrix42, 11 min)"
        return " · ".join([top["ticket"], *parts]) + rest

    def render_ticket_take(self):
        """Text, Tooltip und Platzhalter zum Vorschlag (auch nach dem Nachschlagen in Matrix42)."""
        text = self.suggestion_text()
        if not text:
            return
        full = mb_ticket_label(self.ticket_details) if self.ticket_details else text
        self.ticket_take.setToolTip(f"{full}\nins Feld „Ticket“ übernehmen")
        if self.ticket_take.objectName() == "link_button":  # Nachfrage-Karte: Vorschlag als Link
            self.ticket_take.setText(f"Vorschlag: {text.replace('&', '&&')}")
        placeholder = self.ticket_edit.lineEdit().placeholderText()
        tail = placeholder[placeholder.find(" · oder "):] if " · oder " in placeholder else ""
        self.ticket_edit.lineEdit().setPlaceholderText(f"Gefunden: {text}{tail}")

    def _ticket_typed(self, text):
        text = text.strip()
        if len(text) < 3 or self.TICKET_NUMBER.match(text):  # Nummer: nichts zu suchen
            self._lookup_timer.stop()
            self._completer.popup().hide()
            self.ticket_status.hide()
            return
        self._lookup_timer.start()

    def _start_lookup(self):
        text = self.ticket_edit.currentText().strip()
        self.ticket_status.setText(f"Suche „{text}“ in Matrix42 …")
        self.ticket_status.show()
        self._lookup.lookup(text)

    def _on_lookup(self, text, rows, error):
        if self._details_for and text == self._details_for:
            self._on_details(rows)  # Nachschlagen des Vorschlags, keine Suche beim Tippen
            return
        if text != self.ticket_edit.currentText().strip():
            return  # inzwischen weitergetippt: die neuere Suche kommt noch
        self._lookup_model.clear()
        for row in rows:
            item = QStandardItem(mb_ticket_label(row))
            item.setData(row, Qt.UserRole)
            item.setToolTip(mb_ticket_label(row))
            self._lookup_model.appendRow(item)
        if rows:
            self.ticket_status.setText(f"{len(rows)} Ticket{'s' if len(rows) != 1 else ''} in Matrix42. "
                                       "Auswählen übernimmt die Nummer.")
            self._completer.complete()
        else:
            self.ticket_status.setText(f"Kein Ticket in Matrix42 gefunden{': ' + error if error else '.'}")

    def _pick_lookup(self, index):
        row = index.data(Qt.UserRole) or {}
        if not row.get("ticket"):
            return
        # erst nach dem Completer setzen, der sonst den ganzen Eintrag ins Feld schreibt
        QTimer.singleShot(0, lambda: self._take_found_ticket(row))

    def _take_found_ticket(self, row):
        self.ticket_edit.setCurrentText(row["ticket"])
        if not self.customer_edit.currentText().strip() and row.get("customer"):
            self.customer_edit.setCurrentText(row["customer"])
        self.ticket_status.hide()
        self.text_edit.setFocus()

    def _update_ticket_take(self, *_args):
        self.ticket_take.setVisible(bool(self.ticket_suggestions)
                                    and not self.ticket_edit.currentText().strip())

    def _take_ticket(self):
        if self.ticket_suggestions:
            self.ticket_edit.setCurrentText(self.ticket_suggestions[0]["ticket"])
            customer = (self.ticket_details or {}).get("customer")
            if customer and not self.customer_edit.currentText().strip():
                self.customer_edit.setCurrentText(customer)
            self.text_edit.setFocus()

    def _search_ticket(self):
        """Matrix42-Suche öffnen, vorbelegt mit dem Kunden; gewähltes Ticket übernehmen."""
        typed = self.ticket_edit.currentText().strip()
        text = typed if typed and not self.TICKET_NUMBER.match(typed) else ""
        row = self.ticket_search(text or self.customer_edit.currentText().strip(), self.window())
        if not row or not row.get("ticket"):
            return
        self.ticket_edit.setCurrentText(row["ticket"])
        if not self.customer_edit.currentText().strip() and row.get("customer"):
            self.customer_edit.setCurrentText(row["customer"])
        self.text_edit.setFocus()

    def _fill_insert_menu(self):
        """Menü beim Öffnen neu füllen: Bausteine und die letzten Texte zum gewählten Kunden."""
        menu = self.insert_menu
        menu.clear()
        number = 0

        def add(text, group_size):
            nonlocal number
            if group_size and group_size % 5 == 0:
                menu.addSeparator()  # höchstens 5 Einträge je Gruppe
            number += 1
            mark = f"&{number} " if number < 10 else ""
            menu.addAction(mark + snippet_logic.menu_label(text), lambda t=text: self.insert_text(t))

        if self.snippets:
            menu.addSection("Textbausteine")
            for i, text in enumerate(self.snippets):
                add(text, i)
        customer = self.customer_edit.currentText().strip()
        recent = self.recent_texts(customer) if self.recent_texts and customer else []
        if recent:
            menu.addSection(f"Zuletzt zu {customer.replace('&', '&&')}")
            for i, text in enumerate(recent[:5]):
                add(text, i)
        if not self.snippets and not recent:
            menu.addAction("Keine Textbausteine (Einstellungen → Textbausteine)").setEnabled(False)
        menu.addSeparator()
        menu.addAction("Als Ticket-Doku &gliedern („- “ / „-- “)", self.outline_text)

    def insert_text(self, snippet):
        """Baustein an der Cursorposition bzw. als neue Zeile einfügen."""
        cursor = self.text_edit.textCursor()
        text, pos = snippet_logic.insert(self.text_edit.toPlainText(), cursor.position(), snippet)
        self.text_edit.setPlainText(text)
        cursor = self.text_edit.textCursor()
        cursor.setPosition(pos)
        self.text_edit.setTextCursor(cursor)
        self.text_edit.setFocus()

    def outline_text(self):
        """Erste Zeile „- “, weitere „-- “ (Format der Ticket-Dokumentation)."""
        self.text_edit.setPlainText(format_ticket_text(self.text_edit.toPlainText(), "dash"))
        self.text_edit.moveCursor(self.text_edit.textCursor().MoveOperation.End)
        self.text_edit.setFocus()

    def _customer_changed(self):
        text = self.customer_edit.currentText().strip()
        return bool(text) and text != self._suggested_customer

    def _category_changed(self):
        text = self.category_edit.currentText().strip()
        return bool(text) and text != self._suggested_category

    def _update_learning(self, *_):
        if self.remember_tv and self.trace and self.trace[0] != "tv":
            self.remember_tv.setVisible(self._customer_changed())
        if self.learn_rule:
            category = self.category_edit.currentText().strip()
            self.learn_rule.setText(f"Als &Regel merken: „{self.rule_subject}“ → {category}")
            self.learn_rule.setVisible(self._category_changed())

    def remember_customer(self):
        """Kunde zur Spur merken? (TeamViewer: Haken; sonst nur, wenn der Kunde geändert ist)"""
        if not (self.remember_tv and self.remember_tv.isChecked()):
            return False
        return self.trace[0] == "tv" or self._customer_changed()

    def wants_rule(self):
        """Geänderte Kategorie als Regel merken? (Haken, standardmäßig aus)"""
        return bool(self.learn_rule and self.learn_rule.isChecked() and self._category_changed())

    def times(self):
        day = self.date_edit.date().toPython()
        start = datetime.combine(day, self.start_edit.time().toPython().replace(second=0))
        end = datetime.combine(day, self.end_edit.time().toPython().replace(second=0))
        return start, end

    def validate(self):
        start, end = self.times()
        ok = end > start
        self.error.setText("" if ok else "⚠ Fehler: „Bis“ muss nach „Von“ liegen.")
        self.error.setVisible(not ok)
        self.error.setVisible(not ok)
        minutes = int((end - start).total_seconds() // 60)
        text = f"{minutes // 60}:{minutes % 60:02d} h" if ok else ""
        customer = self.customer_edit.currentText().strip()
        if ok and self.billing and self.billing.active(customer):
            text += f", abgerechnet {hours_text(self.billing.minutes(minutes * 60, customer))}"
        self.duration.setText(text)
        if self.validate_hook:
            self.validate_hook(ok)
        return ok

    def item(self):
        start, end = self.times()
        return {
            "start": start.strftime(TIME_FMT),
            "end": end.strftime(TIME_FMT),
            "customer": self.customer_edit.currentText().strip(),
            "category": self.category_edit.currentText().strip(),
            "text": self.text_edit.toPlainText().strip(),
            "ticket": self.ticket_edit.currentText().strip(),
            "goodwill": self.goodwill_box.isChecked(),
            "travel": self.travel_box.isChecked(),
            "no_surcharge": self.surcharge_box.isChecked(),
            **self.flag_details(),
        }


class EntryDialog(CardParts, QDialog):
    """Tätigkeit nachtragen oder ändern, aufgebaut wie die Nachfrage-Karte (prompt_card.py):
    Kopf mit Aufgabe, feste Zeitzeile mit Stift, Felder mit Beschriftung darüber, Chips,
    darunter die Spuren in dieser Zeit und die Fußleiste (Löschen | Abbrechen, Speichern).

    edit_time: Zeitzeile gleich offen (Nachtragen ohne gezogenen Zeitraum)."""

    def __init__(self, start, end, customers, categories, customer="", category="", text="",
                 tv_id=None, title="Tätigkeit nachtragen", info="", can_delete=False, parent=None,
                 trace=None, rule_subject=None, context_for=None, guess_for=None, edit_time=False,
                 **form_options):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setObjectName("entry_dialog")
        self.setFixedWidth(600)  # wie die Karte: passt auch bei 200 % auf Full HD
        self.deleted = False
        pal = (parent or self).palette()
        accent = pal.color(pal.ColorRole.Accent).name()
        muted = pal.color(pal.ColorRole.PlaceholderText).name()
        self.form = form = _EntryForm(start, end, customers, categories, customer, category, text,
                                      tv_id, self, trace=trace, rule_subject=rule_subject,
                                      **{"show_ticket": False, **form_options})
        old = form.layout()
        form.hide()  # nur noch Hülle; die Felder wandern in den Dialog
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- Kopf: Aufgabe, Vorschlag oder Kunde, Zeitzeile
        top = QWidget()
        top.setObjectName("prompt_top")
        top.setAttribute(Qt.WA_StyledBackground)
        head_box = QVBoxLayout(top)
        head_box.setContentsMargins(16, 14, 16, SPACE_M)
        head_box.setSpacing(SPACE_S + 2)
        head = QHBoxLayout()
        head.setSpacing(SPACE_M)
        head.addWidget(source_tile("edit" if can_delete else "doc", accent), 0, Qt.AlignVCenter)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.title = _ElidedLabel(title)
        self.title.setObjectName("prompt_title")
        self.subtitle = _ElidedLabel(info or (customer if can_delete else ""))
        self.subtitle.setObjectName("hint")
        self.subtitle.setVisible(bool(self.subtitle.full_text()))
        texts.addWidget(self.title)
        texts.addWidget(self.subtitle)
        head.addLayout(texts, 1)
        head_box.addLayout(head)
        head_box.addWidget(self._build_time_row(form, old, muted))
        outer.addWidget(top)

        # ---- Inhalt
        body = QWidget()
        body.setObjectName("prompt_body")
        self.body_box = QVBoxLayout(body)
        self.body_box.setContentsMargins(16, SPACE_M, 16, SPACE_M)
        self.body_box.setSpacing(SPACE_S + 2)
        self._build_fields(self.body_box, form, old, text_height=84)
        outer.addWidget(body)

        # Zeitraum nachtragen (Companion): was die Quellen in dieser Zeit sagen, Feinjustieren
        # guess_for(start, end, text): range_context.estimate, vermuteter Kunde und Kategorie
        self.context_for = context_for
        self.guess_for = guess_for
        self.context_rows = None
        self._auto_category = category  # vorbelegt, darf beim Tippen nachgeführt werden
        if context_for:
            self.body_box.addSpacing(SPACE_XS)
            self.body_box.addWidget(self._context_card(muted))
            form.start_edit.timeChanged.connect(lambda _t: self.update_context())
            form.end_edit.timeChanged.connect(lambda _t: self.update_context())
            form.date_edit.dateChanged.connect(lambda _d: self.update_context())
            if guess_for:  # beim Tippen neu schätzen, aber erst nach einer kurzen Pause
                self._text_timer = QTimer(self)
                self._text_timer.setSingleShot(True)
                self._text_timer.setInterval(400)
                self._text_timer.timeout.connect(self.update_context)
                form.text_edit.textChanged.connect(self._text_timer.start)
            self.update_context()

        # ---- Fuß: Löschen | Abbrechen, Speichern
        foot = QWidget()
        foot.setObjectName("prompt_foot")
        foot.setProperty("flat", True)  # im Fenster ohne runde Ecken
        foot.setAttribute(Qt.WA_StyledBackground)
        foot_box = QHBoxLayout(foot)
        foot_box.setContentsMargins(16, SPACE_S + 2, 16, SPACE_S + 2)
        foot_box.setSpacing(SPACE_S)
        self.delete_btn = None
        if can_delete:
            self.delete_btn = QPushButton("&Löschen")
            self.delete_btn.setObjectName("quiet_button")
            self.delete_btn.setIcon(icons.icon("trash", muted))
            self.delete_btn.setAutoDefault(False)
            self.delete_btn.setToolTip("Diese Tätigkeit löschen")
            self.delete_btn.clicked.connect(self._delete)
            foot_box.addWidget(self.delete_btn)
        foot_box.addStretch(1)
        self.cancel_btn = QPushButton("Abbrechen")
        self.cancel_btn.setAutoDefault(False)
        self.cancel_btn.clicked.connect(self.reject)
        foot_box.addWidget(self.cancel_btn)
        self.save_btn = QPushButton("&Speichern")
        self.save_btn.setDefault(True)
        self.save_btn.setToolTip("Speichern (Strg+Enter)")
        self.save_btn.clicked.connect(self.accept)
        foot_box.addWidget(self.save_btn)
        outer.addWidget(foot)

        form.validate_hook = self.save_btn.setEnabled
        form.validate()
        if edit_time:
            self.set_time_editing(True)  # Fokus auf „Von“
        else:
            form.text_edit.setFocus()

    def _context_card(self, muted):
        card = QFrame()
        card.setObjectName("entry_context")
        box = QVBoxLayout(card)
        box.setContentsMargins(SPACE_M, SPACE_S + 2, SPACE_M, SPACE_S + 2)
        box.setSpacing(SPACE_XS + 2)
        head = QHBoxLayout()
        head.setSpacing(SPACE_S)
        head.addWidget(_icon_label("eye", muted, 14))
        title = QLabel("In dieser Zeit")
        title.setObjectName("prompt_label")
        title.setToolTip("Was die Quellen in dieser Zeit sagen")
        head.addWidget(title)
        head.addStretch(1)
        box.addLayout(head)
        self.context_rows = QFormLayout()
        self.context_rows.setHorizontalSpacing(SPACE_M)
        self.context_rows.setVerticalSpacing(SPACE_XS)
        box.addLayout(self.context_rows)
        return card

    def eventFilter(self, obj, event):
        if self._card_event(obj, event):
            return True
        return super().eventFilter(obj, event)

    def event(self, event):
        result = super().event(event)
        if event.type() == QEvent.LayoutRequest:
            self._fit()  # Chips umgebrochen, Ticketfeld auf/zu: Höhe nachführen
        return result

    def _fit(self):
        layout = self.layout()
        if layout is None or not layout.hasHeightForWidth():
            return
        height = max(layout.totalMinimumSize().height(), layout.totalHeightForWidth(self.width()))
        if height != self.height():
            self.setFixedHeight(height)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and event.modifiers() & Qt.ControlModifier:
            if self.save_btn.isEnabled():
                self.accept()
            return
        super().keyPressEvent(event)

    def update_context(self):
        if self.context_rows is None:
            return
        while self.context_rows.rowCount():
            self.context_rows.removeRow(0)
        start, end = self.form.times()
        rows = list(self.context_for(start, end)) if end > start else []
        if self.guess_for and end > start:
            guess = self.guess_for(start, end, self.form.text_edit.toPlainText())
            rows += range_context.estimate_rows(guess)
            self._follow_category(guess)
        for source, text in rows or [("", "Keine Spuren in dieser Zeit.")]:
            name = QLabel(source)
            name.setObjectName("hint")
            value = QLabel(text)
            value.setWordWrap(True)
            self.context_rows.addRow(name, value)

    def _follow_category(self, guess):
        """Vermutete Kategorie eintragen, solange du keine andere gewählt hast."""
        edit = self.form.category_edit
        if edit.currentText().strip() not in ("", self._auto_category):
            return  # selbst gewählt: bleibt
        cats = guess.get("categories") or []
        if cats and cats[0][1] >= 30 and cats[0][0] != edit.currentText().strip():
            self._auto_category = cats[0][0]
            edit.setCurrentText(cats[0][0])

    def _delete(self):
        self.deleted = True
        self.accept()

    def item(self):
        return self.form.item()

    def remember_tv(self):
        """Kunde zur Spur merken (Name stammt aus der Zeit, als es nur TeamViewer gab)."""
        return self.form.remember_customer()

    def wants_rule(self):
        return self.form.wants_rule()


def default_span(date, minute=None):
    """Startwerte für "Tätigkeit nachtragen": heute die letzte halbe Stunde, sonst 30 min ab minute."""
    if minute is None:
        now = datetime.now()
        if date == now.date():
            end = now.replace(second=0, microsecond=0)
            return end - timedelta(minutes=30), end
        minute = 9 * 60
    minute = max(0, min(int(minute) // 5 * 5, 23 * 60 + 25))
    start = datetime.combine(date, datetime.min.time()) + timedelta(minutes=minute)
    return start, start + timedelta(minutes=30)


PROMPT_THRESHOLDS = {"connections": 1, "calls": 1, "pc": 15, "meetings": 5, "mails": 0,
                     "credentials": 0, "rules": 1}
# Standard: wonach gefragt wird (Zugangsdaten und Regel-Blöcke nur auf Wunsch)
PROMPT_SOURCES = ["connections", "calls", "pc", "meetings", "mails"]


def prompt_thresholds(config):
    """Mindestdauer (Minuten) fürs Nachfragen je Art: Verbindungen, Telefonate, Regel-Blöcke."""
    saved = config.get("prompt_thresholds")
    result = dict(PROMPT_THRESHOLDS)
    if isinstance(saved, dict):
        for key, value in saved.items():
            if key in result and isinstance(value, (int, float)) and value >= 0:
                result[key] = value
    return result


class PromptSettings(QWidget):
    """Seite „Nachfragen“ im Einstellungsfenster: Darstellung (Vorschau-Kacheln), Anzeigedauer,
    wonach ab welcher Dauer gefragt wird, „Später“ und Erinnerungen. Jede Änderung schreibt sofort
    in config und meldet sich über changed (das Einstellungsfenster speichert)."""

    changed = Signal()

    SOURCES = [("connections", "&Verbindungen", "TeamViewer, RDP, SSH, VPN"),
               ("calls", "&Telefonaten", "3CX, Teams"),
               ("pc", "Arbeitsblöcken am PC", "M365-Admin, Ticketsystem …"),
               ("meetings", "Teams-Besprechungen", "an denen du teilgenommen hast"),
               ("mails", "&Mails an Kunden", "aus der Kundenliste"),
               ("credentials", "Zugangs&daten", "in RDM angezeigt"),
               ("rules", "Blöcken aus &Regeln", "Zuordnung ohne KI")]
    STYLE_KEYS = {"window": "&Karte", "compact": "K&ompakt", "strip": "&Leiste", "off": "A&us"}

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setObjectName("prompt_settings")
        tokens = theme_for(config)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(SPACE_S)

        def label(text, buddy=None):
            widget = QLabel(text)
            widget.setObjectName("prompt_label")
            if buddy is not None:
                widget.setBuddy(buddy)
            return widget

        # ---- Darstellung: vier Kacheln mit Vorschau
        box.addWidget(label("Darstellung"))
        tiles_host = QWidget()
        tiles_host.setObjectName("chips")
        tiles = FlowLayout(tiles_host, spacing=SPACE_S)  # bricht in schmalen Fenstern um
        self.style_group = QButtonGroup(self)
        self.style_buttons = {}
        current = prompt_style(config)
        for key, text in STYLES:
            button = QToolButton()
            button.setObjectName("style_tile")
            button.setCheckable(True)
            button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            button.setIcon(QIcon(style_preview(key, tokens)))
            button.setIconSize(QSize(96, 60))
            button.setFixedWidth(132)
            button.setText(self.STYLE_KEYS[key])
            button.setToolTip(STYLE_HINTS[key])
            button.setAccessibleName(f"{text}: {STYLE_HINTS[key]}")
            button.setChecked(key == current)
            button.clicked.connect(lambda _c=False, k=key: self.set_style(k))
            self.style_group.addButton(button)
            self.style_buttons[key] = button
            tiles.addWidget(button)
        box.addWidget(tiles_host)
        self.style_hint = QLabel()
        self.style_hint.setObjectName("hint")
        box.addWidget(self.style_hint)

        grid = QGridLayout()
        grid.setHorizontalSpacing(SPACE_M)
        grid.setVerticalSpacing(SPACE_XS)
        self.timeout = QComboBox()
        for seconds, text in TIMEOUTS:
            self.timeout.addItem(text, seconds)
        self.timeout.setCurrentIndex(max(0, self.timeout.findData(prompt_timeout(config))))
        self.timeout.setToolTip("Danach blendet die Nachfrage aus und bleibt unter „Offene Nachfragen“ "
                                "im Infobereich. „Dauerhaft“: bleibt stehen, bis du antwortest.")
        self.strip_close = QComboBox()
        self.strip_close.addItem("Schließt die vorderste", "front")
        self.strip_close.addItem("Schließt alle", "all")
        self.strip_close.setCurrentIndex(max(0, self.strip_close.findData(
            config.get("prompt_strip_close", "front"))))
        self.strip_close.setToolTip("✕ an der Leiste: nur die vorderste oder alle offenen Nachfragen schließen")
        self.position = QComboBox()
        for key, text in POSITIONS:
            self.position.addItem(text, key)
        self.position.setCurrentIndex(max(0, self.position.findData(prompt_position(config))))
        self.position.setToolTip("Wo Karte und Kompakt erscheinen. Die Leiste bleibt unten rechts.")
        self.position.setAccessibleName("Position der Nachfrage")
        # Position (Karte, Kompakt) und ✕ an der Leiste (nur Leiste) teilen sich die rechte Spalte:
        # Sichtbar ist immer nur, was zur gewählten Darstellung passt (_sync_style).
        self.option_labels = {}
        for col, name, widget in ((0, "Ausblenden &nach", self.timeout), (1, "Position", self.position),
                                  (1, "✕ an der Le&iste", self.strip_close)):
            self.option_labels[widget] = label(name, widget)
            grid.addWidget(self.option_labels[widget], 0, col)
            grid.addWidget(widget, 1, col)
        for col in (0, 1):
            grid.setColumnStretch(col, 1)
        for combo in (self.timeout, self.position, self.strip_close):  # schmal werden dürfen (200 %)
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(8)
        box.addLayout(grid)
        chips_host = QWidget()
        chips_host.setObjectName("chips")
        chips = FlowLayout(chips_host, spacing=6)
        self.keep_active = QCheckBox("St&ehen lassen, solange ich tippe")
        self.keep_active.setToolTip("Nicht ausblenden, solange du tippst oder die Maus darüber ist")
        self.keep_active.setChecked(config.get("prompt_keep_while_active", True))
        self.dots = QCheckBox("&Punkte anklickbar")
        self.dots.setToolTip("Punkte oben rechts in der Karte: zwischen offenen Nachfragen wechseln")
        self.dots.setChecked(config.get("prompt_dots_clickable", True))
        for widget in (self.keep_active, self.dots):
            widget.setObjectName("chip_check")
            chips.addWidget(widget)
        box.addWidget(chips_host)
        box.addSpacing(SPACE_M)

        # ---- Fragen bei: je Art an/aus und ab welcher Dauer
        box.addWidget(label("Fragen bei"))
        listing = QFrame()
        listing.setObjectName("source_list")
        rows = QVBoxLayout(listing)
        rows.setContentsMargins(SPACE_M, 2, SPACE_S, 2)
        rows.setSpacing(0)
        self.sources, self.thresholds = {}, {}
        sources = config.get("prompt_sources", PROMPT_SOURCES)
        limits = prompt_thresholds(config)
        idle_minutes = int(config.get("idle_prompt_minutes", 15) or 0)
        self.idle_box = QCheckBox("&Abwesenheit am PC")
        self.idle_box.setToolTip("Bei der ersten Eingabe danach fragen, was in der Zeit war, "
                                 "z. B. Telefonat, Besprechung, Vor Ort, Pause")
        self.idle_box.setChecked(idle_minutes > 0)
        self.idle_spin = QSpinBox()
        self.idle_spin.setRange(5, 240)
        self.idle_spin.setValue(idle_minutes if idle_minutes > 0 else 15)
        entries = []
        for key, text, detail in self.SOURCES:
            check = QCheckBox(text)
            check.setChecked(key in sources)
            spin = QSpinBox()
            spin.setRange(0, 240)
            spin.setSpecialValueText("immer")
            spin.setValue(int(limits[key]))
            self.sources[key], self.thresholds[key] = check, spin
            entries.append((check, detail, spin))
        entries.append((self.idle_box, "keine Maus und Tastatur", self.idle_spin))
        for i, (check, detail, spin) in enumerate(entries):
            spin.setPrefix("ab ")
            spin.setSuffix(" min")
            spin.setFixedWidth(96)
            spin.setToolTip("Kürzere Tätigkeiten dieser Art nicht nachfragen")
            spin.setAccessibleName(f"Mindestdauer für {check.text().replace('&', '')}")
            spin.setEnabled(check.isChecked())
            check.toggled.connect(spin.setEnabled)
            row = QFrame()
            row.setObjectName("source_row")
            row.setProperty("last", i == len(entries) - 1)
            line = QHBoxLayout(row)
            line.setContentsMargins(0, SPACE_XS + 1, 0, SPACE_XS + 1)
            line.setSpacing(SPACE_S)
            line.addWidget(check)
            hint = QLabel(detail)
            hint.setObjectName("hint")
            hint.setWordWrap(True)
            hint.setMinimumWidth(30)  # umbrechen statt die Seite zu verbreitern
            line.addWidget(hint, 1)
            line.addWidget(spin)
            rows.addWidget(row)
        box.addWidget(listing)
        box.addSpacing(SPACE_M)

        # ---- Später und Erinnern
        self.snooze = QSpinBox()
        self.snooze.setRange(1, 480)
        self.snooze.setSuffix(" min")
        self.snooze.setValue(config.get("prompt_snooze_minutes", 15))
        self.snooze.setToolTip("So lange wartet eine Nachfrage, die du auf später gestellt hast")
        self.snooze.setFixedWidth(160)
        box.addWidget(label("„&Später“ fragt wieder nach", self.snooze))
        box.addWidget(self.snooze)
        box.addSpacing(SPACE_M)
        box.addWidget(label("Erinnern"))
        chips_host = QWidget()
        chips_host.setObjectName("chips")
        chips = FlowLayout(chips_host, spacing=6)
        self.end_of_day = QCheckBox("Nach &Feierabend an Offenes")
        self.end_of_day.setChecked(config.get("prompt_end_of_day", True))
        self.on_quit = QCheckBox("Beim &Beenden an Offenes")
        self.on_quit.setChecked(config.get("prompt_on_quit", True))
        self.close_hint = QCheckBox("Hinweis „Zeitzeuge läuft &weiter“")
        self.close_hint.setToolTip("Windows-Meldung, wenn du das Fenster schließt und Zeitzeuge "
                                   "im Infobereich weiter aufzeichnet (einmal je Start)")
        self.close_hint.setChecked(config.get("tray_hint_on_close", True))
        self.windows_notes = QCheckBox("Als Windows-Benac&hrichtigung")
        self.windows_notes.setToolTip("Hinweise (Feierabend, Anmeldung nötig, Störungen) als Sprechblase von "
                                      "Windows statt als Karte oder Leiste wie die Nachfrage")
        self.windows_notes.setChecked(config.get("notify_windows", False))
        for widget in (self.end_of_day, self.on_quit, self.close_hint, self.windows_notes):
            widget.setObjectName("chip_check")
            chips.addWidget(widget)
        box.addWidget(chips_host)

        self._sync_style(current)
        for widget in (self.keep_active, self.dots, self.idle_box, self.end_of_day, self.on_quit,
                       self.close_hint, self.windows_notes, *self.sources.values()):
            widget.toggled.connect(self.apply)
        for widget in (self.idle_spin, self.snooze, *self.thresholds.values()):
            widget.valueChanged.connect(self.apply)
        for widget in (self.timeout, self.position, self.strip_close):
            widget.activated.connect(self.apply)
        self.timeout.activated.connect(lambda *_: self._sync_style(self.current_style()))

    def retheme(self, tokens):
        for key, button in self.style_buttons.items():
            button.setIcon(QIcon(style_preview(key, tokens)))

    def current_style(self):
        return next((k for k, b in self.style_buttons.items() if b.isChecked()), "window")

    def set_style(self, key):
        """Andere Darstellung: passende Anzeigedauer vorschlagen (Karte dauerhaft, sonst 10 s)."""
        self.style_buttons[key].setChecked(True)
        if key in DEFAULT_TIMEOUT:
            self.timeout.setCurrentIndex(max(0, self.timeout.findData(DEFAULT_TIMEOUT[key])))
        self._sync_style(key)
        self.apply()

    def _sync_style(self, key):
        """Nur zeigen, was bei dieser Darstellung wirkt: Position bei Karte und Kompakt, ✕ und
        Leiste nur bei der Leiste, Punkte nur in der Karte, „Stehen lassen“ nur mit Ausblenden."""
        self.style_hint.setText(STYLE_HINTS[key])
        on = key != "off"
        shown = {self.timeout: on, self.position: key in ("window", "compact"),
                 self.strip_close: key == "strip", self.dots: key in ("window", "compact"),
                 self.keep_active: on and self.timeout.currentData() != 0}
        for widget, visible in shown.items():
            widget.setVisible(visible)
            if widget in self.option_labels:
                self.option_labels[widget].setVisible(visible)

    def apply(self, *_):
        self.config["prompt_mode"] = self.current_style()
        self.config["prompt_timeout_seconds"] = self.timeout.currentData()
        self.config["prompt_position"] = self.position.currentData()
        self.config["prompt_keep_while_active"] = self.keep_active.isChecked()
        self.config["prompt_dots_clickable"] = self.dots.isChecked()
        self.config["prompt_strip_close"] = self.strip_close.currentData()
        self.config["prompt_sources"] = [k for k, box in self.sources.items() if box.isChecked()]
        self.config["prompt_thresholds"] = {k: spin.value() for k, spin in self.thresholds.items()}
        self.config["prompt_snooze_minutes"] = self.snooze.value()
        self.config["idle_prompt_minutes"] = self.idle_spin.value() if self.idle_box.isChecked() else 0
        self.config["prompt_end_of_day"] = self.end_of_day.isChecked()
        self.config["prompt_on_quit"] = self.on_quit.isChecked()
        self.config["tray_hint_on_close"] = self.close_hint.isChecked()
        self.config["notify_windows"] = self.windows_notes.isChecked()
        self.changed.emit()


# Nachfrage als Karte/Leiste: eigenes Modul, braucht _EntryForm von hier (daher am Ende geladen)
from prompt_card import (DEFAULT_TIMEOUT, POSITIONS, STYLE_HINTS, STYLES, TIMEOUTS,  # noqa: E402,F401
                         PromptStrip, PromptWindow, prompt_position, prompt_style, prompt_timeout,
                         style_preview)
