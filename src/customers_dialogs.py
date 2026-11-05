"""
Kunden: Fenster „Kunden & Erkennung“ und die Befehle dazu im Hauptfenster.

- CustomersDialog (Aufbau wie „Companion“): links die Kunden mit Suche, Kürzel, Zahl der
  Merkmale und Stunden der letzten 7 Tage; rechts Name, Kundennummer und „Woran Zeitzeuge
  diesen Kunden erkennt“: je Art (Stichwort, Domain, Telefon, Ordner, Host, IP, TeamViewer,
  RDM, VPN, Netzwerk) die Merkmale als Chips, „+ Hinzufügen“ und wie oft sie in den letzten
  7 Tagen gegriffen haben. Dazu der Schalter „Kalendertermine“.
  Oben „Neu entdeckt“: Vorschläge aus Matrix42 (customer_discovery.py).
- Lernen aus Matrix42: auto_learn_customers übernimmt sichere Spuren von selbst, nach dem
  Start und wenn Matrix42 neue Buchungen gelesen hat.
- CustomersMixin: Teil von TimelineApp (über DocsMixin), Menü „Kundenliste …“,
  Rechtsklick „Kunde zuordnen …“, Index für Vorschläge und Anzeige.

Logik und Ablage in customers.py (ohne Qt).
"""
import copy
from datetime import datetime, timedelta

from PySide6.QtCore import QDate, QSize, Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFrame, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox, QPushButton, QScrollArea, QToolButton, QVBoxLayout,
                               QWidget)

from flow_layout import FlowLayout
from theme import THEMES, prose
import customer_discovery as cdisc
import customers as cl
import icons
import main_timeline as mt  # save_config zur Laufzeit von dort (Tests ersetzen es dort)

# Abschnitte rechts: Art, Überschrift, Erklärung, Symbol (Reihenfolge wie in Companion)
SECTIONS = [
    ("word", "Stichwörter in Fenstertitel und Betreff", "Groß-/Kleinschreibung und Umlaute egal", "type"),
    ("mail", "E-Mail- und Web-Domains", "Absender, Empfänger, Kalender-Teilnehmer und Browser", "globe"),
    ("phone", "Telefonnummern", "Abgleich mit der Anrufliste (3CX, Teams) · jede Schreibweise", "phone"),
    ("path", "Ordner und Dateipfade", "Ordner- und Dateinamen im Fenstertitel", "folder"),
    ("host", "Rechnernamen und Hosts", "Auch Muster, z. B. *.kunde.local · RDP, SSH, RDM und Fenstertitel",
     "server"),
    ("ip", "IP-Adressen und -Bereiche", "Einzelne Adressen oder Bereiche (CIDR), z. B. 10.20.0.0/16",
     "network"),
    ("tv", "TeamViewer-IDs", "ID der Gegenstelle einer TeamViewer-Sitzung", "screen_share"),
    ("rdm", "RDM-Einträge", "Name der Verbindung im Remote Desktop Manager", "plug"),
    ("vpn", "VPN-Verbindungen", "Name in Sophos Connect, FortiClient oder OpenVPN", "shield"),
    ("net", "Netzwerke", "Netzwerkprofil oder WLAN beim Kunden, z. B. Mueller-Gast", "wifi"),
]


def initials(name):
    """„Kanzlei Schmidt“ -> „KS“, „Avangard“ -> „AV“."""
    words = [w for w in name.replace("-", " ").split() if w[:1].isalnum()]
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    return (words[0][:2] if words else "?").upper()


def _hours(seconds):
    minutes = int(round(seconds / 60))
    return f"{minutes // 60}:{minutes % 60:02d} h"


class _Section(QFrame):
    """Eine Art von Merkmalen: Kopf, Chips und „+ Hinzufügen“ mit Eingabefeld."""

    def __init__(self, dialog, kind, title, desc, icon_name, color):
        super().__init__()
        self.dialog, self.kind = dialog, kind
        self.setObjectName("card_row")
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(12)
        symbol = QLabel()
        symbol.setPixmap(icons.icon(icon_name, color).pixmap(QSize(16, 16)))
        symbol.setFixedWidth(20)
        symbol.setAlignment(Qt.AlignTop)
        row.addWidget(symbol)
        body = QVBoxLayout()
        body.setSpacing(4)
        head = QLabel(title)
        head.setObjectName("card_title")
        body.addWidget(head)
        hint = QLabel(desc)
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        body.addWidget(hint)
        self.chips_box = QWidget()
        self.chips_box.setObjectName("chips")
        self.flow = FlowLayout(self.chips_box)
        body.addWidget(self.chips_box)
        row.addLayout(body, 1)
        self.count = QLabel("")
        self.count.setObjectName("count")
        self.count.setAlignment(Qt.AlignTop)
        row.addWidget(self.count)
        self.add_button = QToolButton()
        self.add_button.setObjectName("chip_add")
        self.add_button.setText("+ Hinzufügen")
        self.add_button.setAccessibleName(f"{cl.KINDS[kind]} hinzufügen")
        self.add_button.setCursor(Qt.PointingHandCursor)
        self.add_button.clicked.connect(self.start_edit)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(dialog.PLACEHOLDERS.get(kind, ""))
        self.edit.setAccessibleName(f"Neue {cl.KINDS[kind]}")
        self.edit.setMinimumWidth(220)
        self.edit.hide()
        self.edit.returnPressed.connect(self.finish_edit)
        self.edit.editingFinished.connect(self._edit_left)

    def show_traces(self, traces, hits):
        while self.flow.count():
            item = self.flow.takeAt(0)
            w = item.widget()
            if w is not None and w not in (self.add_button, self.edit):
                w.hide()
                w.deleteLater()  # bleibt bis dahin Kind von chips_box, kein eigenes Fenster
        total = 0
        for t in traces:
            n = hits.get((t["kind"], cl.normalize(t["kind"], t["value"])), 0)
            total += n
            chip = QToolButton(self.chips_box)
            chip.setObjectName("chip")
            shown = cl.display(t["kind"], t["value"]) if t["kind"] == "tv" else t["value"]
            if t["kind"] == "tv":
                shown = shown.replace(cl.KINDS["tv"] + " ", "")
            chip.setText(f"{shown}  ×")
            chip.setToolTip(f"{cl.display(t['kind'], t['value'])}\n"
                            f"{n}× in den letzten 7 Tagen erkannt · Klicken entfernt das Merkmal")
            chip.setAccessibleName(f"{cl.display(t['kind'], t['value'])} entfernen")
            chip.setCursor(Qt.PointingHandCursor)
            chip.clicked.connect(lambda _c=False, v=t["value"]: self.dialog.remove_trace(self.kind, v))
            self.flow.addWidget(chip)
        self.flow.addWidget(self.add_button)
        self.flow.addWidget(self.edit)
        self.add_button.setParent(self.chips_box)
        self.edit.setParent(self.chips_box)
        self.add_button.show()
        self.edit.hide()
        self.count.setText(f"{total}×" if traces else "")
        self.count.setToolTip("Treffer in den letzten 7 Tagen")
        self.chips_box.updateGeometry()

    def start_edit(self):
        self.add_button.hide()
        self.edit.show()
        self.edit.setFocus()

    def finish_edit(self):
        text = self.edit.text().strip()
        if text and self.dialog.add_trace(self.kind, text):
            return  # show_traces baut neu auf
        if not text:
            self._edit_left()

    def _edit_left(self):
        if not self.edit.text().strip() and self.edit.isVisible():
            self.edit.hide()
            self.add_button.show()


class CustomersDialog(QDialog):
    """Kunden und ihre Merkmale bearbeiten. Übernimmt erst mit OK (apply)."""

    PLACEHOLDERS = {"tv": "z. B. 1 076 789 144", "rdm": "Name des Eintrags in RDM",
                    "vpn": "Name der Verbindung, z. B. in Sophos Connect",
                    "phone": "z. B. +49 711 123456", "mail": "z. B. kunde.de",
                    "net": "Name des Netzwerks, z. B. Mueller-Gast",
                    "word": "z. B. Nordhafen oder SWN-",
                    "path": "z. B. E:\\Kundenprojekte\\Avangard",
                    "host": "z. B. srv01 oder *.kunde.local",
                    "ip": "z. B. 10.20.0.0/16"}

    def __init__(self, config, parent=None, suggestions=None, hits=None, hours=None):
        super().__init__(parent)
        self.config = config
        self.hits = hits or {}
        self.hours = hours or {}
        self.decisions = []  # (Vorschlag, Status) für customer_discovery.mark beim Übernehmen
        self.auto = {d.get("key") for d in config.get("customers_auto") or []
                     if isinstance(d, dict) and d.get("status") == "gelernt"}
        theme = THEMES["dark" if getattr(parent, "dark_mode", False) else "light"]
        self.setWindowTitle("Kunden & Erkennung")
        self.setMinimumSize(980, 680)
        self.customers = copy.deepcopy(cl.customer_list(config))
        self.customers.sort(key=lambda c: c["name"].lower())
        self._shown = []  # Kunden in der Reihenfolge der Liste (nach Suche)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)
        top = QHBoxLayout()
        title = QLabel("Kunden & Erkennung")
        title.setObjectName("page_title")
        top.addWidget(title)
        top.addStretch(1)
        self.new_btn = QPushButton("+ Neuer Kunde")
        self.new_btn.setAutoDefault(False)
        top.addWidget(self.new_btn)
        layout.addLayout(top)
        found = suggestions or {}
        self._add_suggestions(layout, (found.get("rename") or []) + (found.get("suggest") or []))

        columns = QHBoxLayout()
        columns.setSpacing(12)
        # ---- Links: Kunden
        left = QFrame()
        left.setObjectName("card")
        left.setFixedWidth(280)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(8, 8, 8, 8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Kunden suchen")
        self.search.setAccessibleName("Kunden suchen")
        self.search.setClearButtonEnabled(True)
        left_layout.addWidget(self.search)
        self.customer_list = QListWidget()
        self.customer_list.setObjectName("nav_list")
        self.customer_list.setAccessibleName("Kunden")
        left_layout.addWidget(self.customer_list, 1)
        foot = QLabel("Stunden: letzte 7 Tage (eingetragen)")
        foot.setObjectName("hint")
        left_layout.addWidget(foot)
        columns.addWidget(left)

        # ---- Rechts: Kunde
        right = QFrame()
        right.setObjectName("card")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        inner.setObjectName("customer_detail")
        detail = QVBoxLayout(inner)
        detail.setContentsMargins(16, 14, 16, 14)
        detail.setSpacing(10)
        head = QHBoxLayout()
        self.avatar = QLabel("")
        self.avatar.setObjectName("avatar")
        self.avatar.setFixedSize(40, 40)
        self.avatar.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.avatar.setIndent(9)
        head.addWidget(self.avatar)
        name_box = QVBoxLayout()
        name_label = QLabel("&Name")
        name_label.setObjectName("hint")
        self.name_edit = QLineEdit()
        name_label.setBuddy(self.name_edit)
        name_box.addWidget(name_label)
        name_box.addWidget(self.name_edit)
        head.addLayout(name_box, 3)
        number_box = QVBoxLayout()
        number_label = QLabel("Kunden&nummer")
        number_label.setObjectName("hint")
        self.number_edit = QLineEdit()
        self.number_edit.setPlaceholderText("z. B. K-10234")
        number_label.setBuddy(self.number_edit)
        number_box.addWidget(number_label)
        number_box.addWidget(self.number_edit)
        head.addLayout(number_box, 1)
        detail.addLayout(head)

        caption = QLabel("Woran Zeitzeuge diesen Kunden erkennt")
        caption.setObjectName("section_title")
        detail.addWidget(caption)
        sub = QLabel("Ein Treffer genügt. Genauere Merkmale (Telefon, TeamViewer, Domain) gehen vor "
                     "IP, Host, Ordner und Stichwort. Klick auf ein Merkmal entfernt es.")
        sub.setObjectName("hint")
        sub.setWordWrap(True)
        detail.addWidget(sub)
        box = QFrame()
        box.setObjectName("card")
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(0, 0, 0, 0)
        box_layout.setSpacing(0)
        self.sections = {}
        for kind, head_text, desc, icon_name in SECTIONS:
            section = _Section(self, kind, head_text, desc, icon_name, theme["muted"])
            self.sections[kind] = section
            box_layout.addWidget(section)
        cal = QFrame()
        cal.setObjectName("card_row")
        cal_row = QHBoxLayout(cal)
        cal_row.setContentsMargins(12, 10, 12, 10)
        cal_icon = QLabel()
        cal_icon.setPixmap(icons.icon("today", theme["muted"]).pixmap(QSize(16, 16)))
        cal_icon.setFixedWidth(20)
        cal_row.addWidget(cal_icon)
        cal_text = QVBoxLayout()
        cal_head = QLabel("Kalendertermine")
        cal_head.setObjectName("card_title")
        cal_text.addWidget(cal_head)
        cal_hint = QLabel("Termine und Teams-Besprechungen mit Teilnehmern aus den Domains oben "
                          "zählen für diesen Kunden.")
        cal_hint.setObjectName("hint")
        cal_hint.setWordWrap(True)
        cal_text.addWidget(cal_hint)
        cal_row.addLayout(cal_text, 1)
        self.calendar_check = QCheckBox("An")
        self.calendar_check.setObjectName("switch")
        self.calendar_check.setAccessibleName("Kalendertermine zuordnen")
        cal_row.addWidget(self.calendar_check)
        box_layout.addWidget(cal)
        detail.addWidget(box)

        bottom = QHBoxLayout()
        self.delete_btn = QPushButton("Kunde &löschen")
        self.delete_btn.setIcon(icons.icon("trash", theme["now"]))
        self.delete_btn.setAutoDefault(False)
        bottom.addWidget(self.delete_btn)
        bottom.addStretch(1)
        detail.addLayout(bottom)
        self.message = QLabel()
        self.message.setObjectName("hint")
        self.message.setWordWrap(True)
        detail.addWidget(self.message)
        detail.addStretch(1)
        scroll.setWidget(inner)
        right_layout.addWidget(scroll)
        self.empty = QLabel("Noch keine Kunden. Lege mit „+ Neuer Kunde“ den ersten an.")
        self.empty.setObjectName("hint")
        self.empty.setContentsMargins(16, 16, 16, 16)
        right_layout.addWidget(self.empty)
        columns.addWidget(right, 1)
        layout.addLayout(columns, 1)

        footer = QHBoxLayout()
        privacy = QLabel("🔒 Kundenliste und Abgleich bleiben verschlüsselt auf diesem PC. "
                         "Sie gehen nie an KI-Dienste.")
        privacy.setObjectName("hint")
        footer.addWidget(privacy, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        footer.addWidget(buttons)
        layout.addLayout(footer)

        self.customer_list.currentRowChanged.connect(lambda _r: self._show_customer())
        self.search.textChanged.connect(lambda _t: self._fill(self._current()))
        self.new_btn.clicked.connect(lambda: self.add_customer())
        self.delete_btn.clicked.connect(lambda: self.delete_customer())
        self.name_edit.editingFinished.connect(self._name_edited)
        self.number_edit.textEdited.connect(self._number_edited)
        self.calendar_check.toggled.connect(self._calendar_toggled)
        self._fill(self.customers[0] if self.customers else None)

    def _add_suggestions(self, layout, renames):
        """Kasten „Neu entdeckt“: Umbenennen in den Matrix42-Namen, Stichwort übernehmen
        oder ignorieren."""
        self.suggestion_rows = []
        if not renames:
            return
        box = QFrame()
        box.setObjectName("notice")
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(14, 10, 14, 10)
        title = QLabel("✦ Neu entdeckt – aus deinen Matrix42-Buchungen")
        title.setObjectName("card_title")
        box_layout.addWidget(title)
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
            box_layout.addLayout(row)
            widgets = (text, take, skip)
            self.suggestion_rows.append((item, widgets))
            take.clicked.connect(lambda _c=False, i=item, w=widgets: self.take_suggestion(i, w))
            skip.clicked.connect(lambda _c=False, i=item, w=widgets: self.skip_suggestion(i, w))
        layout.addWidget(box)

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
            self._fill(next(c for c in self.customers if c["name"] == item["customer"]))
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
            target = source
        else:
            target["traces"] += source["traces"]
            self.customers.remove(source)
        self.customers.sort(key=lambda c: c["name"].lower())
        self._fill(target)
        self.decisions.append((item, "umbenannt"))
        if widgets:
            self._close_suggestion(widgets, f"✓ „{item['name']}“ heißt jetzt „{item['to']}“.")
        return True

    def skip_suggestion(self, item, widgets=None):
        self.decisions.append((item, "ignoriert"))
        if widgets:
            what = cl.display(item["kind"], item["value"]) if "kind" in item else f"„{item['name']}“"
            self._close_suggestion(widgets, f"{what}: ignoriert (kommt nicht wieder).")

    # ------------------------------------------------------------ Anzeige

    def _current(self):
        row = self.customer_list.currentRow()
        return self._shown[row] if 0 <= row < len(self._shown) else None

    def _fill(self, select=None):
        """Liste neu aufbauen (Suche beachten) und select (Kunde) markieren."""
        query = cl.fold(self.search.text())
        self._shown = [c for c in self.customers if not query or query in cl.fold(c["name"])
                       or query in cl.fold(c.get("number", ""))]
        self.customer_list.blockSignals(True)
        self.customer_list.clear()
        for c in self._shown:
            n = len(c["traces"])
            item = QListWidgetItem(self.customer_list)
            item.setText("")
            item.setData(Qt.AccessibleTextRole, f"{c['name']}, {n} Merkmale")
            item.setSizeHint(QSize(240, 46))
            self.customer_list.setItemWidget(item, self._row_widget(c))
        self.customer_list.blockSignals(False)
        if self._shown:
            row = self._shown.index(select) if select in self._shown else 0
            self.customer_list.setCurrentRow(row)
        self._show_customer()

    def _row_widget(self, c):
        w = QWidget()
        w.setObjectName("chips")  # durchsichtig, die Auswahlfarbe der Liste bleibt sichtbar
        w.setAttribute(Qt.WA_TransparentForMouseEvents)
        row = QHBoxLayout(w)
        row.setContentsMargins(4, 2, 4, 2)
        row.setSpacing(8)
        av = QLabel(initials(c["name"]))
        av.setObjectName("avatar")
        av.setFixedSize(30, 30)
        av.setIndent(5)
        row.addWidget(av)
        text = QVBoxLayout()
        text.setSpacing(0)
        name = QLabel(c["name"])
        name.setObjectName("card_title")
        text.addWidget(name)
        n = len(c["traces"])
        meta = QLabel(f"{n} Merkmal{'e' if n != 1 else ''}" + (f" · {c['number']}" if c.get("number") else ""))
        meta.setObjectName("count")
        text.addWidget(meta)
        row.addLayout(text, 1)
        hours = QLabel(_hours(self.hours.get(c["name"], 0)))
        hours.setObjectName("count")
        row.addWidget(hours)
        return w

    def _refresh_row(self, current):
        row = self._shown.index(current) if current in self._shown else -1
        if row >= 0:
            self.customer_list.setItemWidget(self.customer_list.item(row), self._row_widget(current))

    def _show_customer(self):
        current = self._current()
        has = current is not None
        self.empty.setVisible(not self.customers)
        for w in (self.name_edit, self.number_edit, self.delete_btn, self.calendar_check):
            w.setEnabled(has)
        for section in self.sections.values():
            section.setEnabled(has)
        current = current or {"name": "", "traces": []}
        self.avatar.setText(initials(current["name"]) if has else "")
        self.name_edit.setText(current["name"])
        self.number_edit.setText(current.get("number", ""))
        self.calendar_check.blockSignals(True)
        self.calendar_check.setChecked(current.get("calendar", True))
        self.calendar_check.blockSignals(False)
        for kind, section in self.sections.items():
            section.show_traces([t for t in current["traces"] if t["kind"] == kind], self.hits)

    def _say(self, text):
        self.message.setText(text)

    def _name_edited(self):
        current = self._current()
        if current is not None and self.name_edit.text().strip() != current["name"]:
            if not self.rename_customer(self.name_edit.text()):
                self.name_edit.setText(current["name"])

    def _number_edited(self, text):
        current = self._current()
        if current is None:
            return
        if text.strip():
            current["number"] = text.strip()
        else:
            current.pop("number", None)
        self._refresh_row(current)

    def _calendar_toggled(self, on):
        current = self._current()
        if current is None:
            return
        if on:
            current.pop("calendar", None)
        else:
            current["calendar"] = False

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
        new = {"name": name, "traces": []}
        self.customers.append(new)
        self.customers.sort(key=lambda c: c["name"].lower())
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self._fill(new)
        self._say(f"„{name}“ angelegt. Füge jetzt die Merkmale hinzu.")
        self.sections["word"].start_edit()
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
        self._fill(current)
        self._say(f"Umbenannt in „{name}“.")
        return True

    def delete_customer(self, ask=True):
        current = self._current()
        if current is None:
            return False
        if ask and current["traces"] and QMessageBox.question(
                self, "Kunde löschen",
                f"„{current['name']}“ mit {len(current['traces'])} Merkmalen löschen? "
                "Deine Tätigkeiten bleiben erhalten.") != QMessageBox.Yes:
            return False
        row = self._shown.index(current)
        self.customers.remove(current)
        self._fill(None)
        if self._shown:
            self.customer_list.setCurrentRow(min(row, len(self._shown) - 1))
        self._say(f"„{current['name']}“ gelöscht.")
        return True

    # ------------------------------------------------------------ Merkmale

    def add_trace(self, kind, value):
        current = self._current()
        if current is None:
            return False
        if not cl.normalize(kind, value):
            hints = {"tv": "nur Ziffern", "phone": "mindestens 3 Ziffern",
                     "mail": "z. B. kunde.de", "ip": "z. B. 10.0.0.5 oder 10.0.0.0/24",
                     "host": "Buchstaben, Ziffern, . - _ und * ?"}
            self._say(f"⚠ Ungültige {cl.KINDS[kind]} ({hints.get(kind, 'mindestens 3 Zeichen')}).")
            return False
        key = cl.normalize(kind, value)
        before = next((c["name"] for c in self.customers if c is not current and any(
            t["kind"] == kind and cl.normalize(kind, t["value"]) == key for t in c["traces"])), "")
        cl._assign(self.customers, kind, value, current["name"])
        self._refresh_row(current)
        self._show_customer()
        text = f"{cl.display(kind, cl.clean_value(kind, value))} hinzugefügt."
        if before:
            text += f" Sie gehörte bisher zu „{before}“."
        self._say(text)
        return True

    def remove_trace(self, kind, value):
        current = self._current()
        if current is None:
            return False
        key = cl.normalize(kind, value)
        kept = [t for t in current["traces"] if not (t["kind"] == kind and cl.normalize(kind, t["value"]) == key)]
        if len(kept) == len(current["traces"]):
            return False
        current["traces"] = kept
        self._refresh_row(current)
        self._show_customer()
        self._say(f"{cl.display(kind, value)} entfernt.")
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

    HITS_DAYS = 7  # Treffer und Stunden im Kundenfenster: so viele Tage zurück

    def customer_stats(self, now=None):
        """(Treffer je Merkmal, eingetragene Sekunden je Kunde) der letzten HITS_DAYS Tage."""
        now = now or datetime.now()
        index = cl.index(self.config)
        entries, pcs, hours = [], [], {}
        try:
            for back in range(self.HITS_DAYS):
                day = now - timedelta(days=back)
                date = QDate(day.year, day.month, day.day)
                entries += self.timeline.activities_for(date)
                pcs += self.timeline.pc_entries_for(date, min_seconds=30)
                for e in self.journal.entries(day.strftime("%Y-%m-%d")):
                    name = e.get("customer_name") or ""
                    seconds = (datetime.strptime(e["end"], "%Y-%m-%d %H:%M:%S")
                               - datetime.strptime(e["start"], "%Y-%m-%d %H:%M:%S")).total_seconds()
                    if name:
                        hours[name] = hours.get(name, 0) + max(0, seconds)
            self.timeline.activities_for(self.current_date)  # Zwischenstand des angezeigten Tags zurück
        except Exception:  # Zahlen sind nur eine Hilfe
            import safe_io
            safe_io.report("Kundenliste: Treffer zählen ging nicht")
        return cl.count_hits(index, entries, pcs), hours

    def edit_customers(self):
        hits, hours = self.customer_stats()
        dialog = CustomersDialog(self.config, self, getattr(self, "_customer_suggestions", None),
                                 hits=hits, hours=hours)
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
