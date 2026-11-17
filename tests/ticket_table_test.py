"""Tickettabelle: der Betreff bekommt den Platz, Kunde/Melder/Bearbeiter wachsen nur mäßig mit."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

widgets = pytest.importorskip("PySide6.QtWidgets")


def _widths(width, font_scale=1.0):
    """font_scale > 1 stellt Windows nach: dort sind Art, Status und Ticket fast doppelt so breit."""
    from ticket_table import COLUMNS, TicketTable
    app = widgets.QApplication.instance() or widgets.QApplication([])
    table = TicketTable("Tickets")
    if font_scale != 1.0:
        font = table.font()
        font.setPointSizeF(font.pointSizeF() * font_scale)
        table.setFont(font)
        table.horizontalHeader().setFont(font)
    table.set_rows([{"ticket": "TCK0000050902", "subject": "Meldung ploppt beim Start auf",
                     "customer": "Ärzte - Dienstleistungs GmbH", "initiator": "Max Mustermann",
                     "type": "Serviceanfrage", "state": "In Bearbeitung", "recipient": "Filip Beispiel",
                     "created": "2026-11-12 09:00:00", "id": "1"}])
    table.resize(width, 400)
    table.show()
    app.processEvents()
    header = table.horizontalHeader()
    sizes = {key: header.sectionSize(c) for c, (_n, key) in enumerate(COLUMNS)}
    viewport = table.viewport().width()
    table.close()
    return sizes, viewport


# Die Ticketnummer wird nie gekürzt; bei sehr breiter Schrift (1.6 auf Windows: 254 px) zählt
# darum der Platz neben ihr.
@pytest.mark.parametrize("font_scale", [1.0, 1.6])
def test_betreff_ist_die_breiteste_spalte(font_scale):
    sizes, viewport = _widths(1000, font_scale)
    assert sizes["subject"] >= 0.33 * (viewport - sizes["ticket"]), (sizes, viewport)
    if font_scale == 1.0:  # normale Schrift: ein Drittel der ganzen Breite
        assert sizes["subject"] >= 0.33 * viewport, (sizes, viewport)
    assert sizes["subject"] > 2 * sizes["customer"], sizes
    assert sum(sizes.values()) <= viewport, (sizes, viewport)


@pytest.mark.parametrize("font_scale", [1.0, 1.6])
def test_schmal_ohne_waagerechte_scrollleiste(font_scale):
    sizes, viewport = _widths(760, font_scale)
    assert sum(sizes.values()) <= viewport, (sizes, viewport)
    assert min(sizes[k] for k in ("customer", "initiator", "recipient")) >= 70, sizes
    assert sizes["subject"] >= 0.25 * (viewport - sizes["ticket"]), (sizes, viewport)


@pytest.fixture
def ini(tmp_path, monkeypatch):
    """Gezogene Breiten in eine eigene Datei statt in die echten Einstellungen."""
    import ticket_table
    from PySide6.QtCore import QSettings
    path = str(tmp_path / "zz.ini")
    monkeypatch.setattr(ticket_table, "settings", lambda: QSettings(path, QSettings.IniFormat))
    return path


def test_gezogene_breite_bleibt_und_wird_gemerkt(ini):
    from ticket_table import COLUMNS, TicketTable
    app = widgets.QApplication.instance() or widgets.QApplication([])
    col = [key for _n, key in COLUMNS].index("customer")
    table = TicketTable("Tickets")
    table.resize(1000, 400)
    table.show()
    app.processEvents()
    table.horizontalHeader().resizeSection(col, 240)  # wie Ziehen im Kopf
    table.resize(1100, 400)  # Größe und Inhalt ändern: Breite bleibt
    table.set_rows([])
    app.processEvents()
    assert table.horizontalHeader().sectionSize(col) == 240
    table.close()

    again = TicketTable("Tickets")  # neues Fenster: gemerkte Breite
    again.resize(1000, 400)
    again.show()
    app.processEvents()
    assert again.horizontalHeader().sectionSize(col) == 240
    other = TicketTable("Gefundene Tickets")  # andere Tabelle: eigene Breiten
    other.resize(1000, 400)
    other.show()
    app.processEvents()
    assert other.horizontalHeader().sectionSize(col) != 240
    again.reset_widths()
    assert again.horizontalHeader().sectionSize(col) != 240
    again.close()
    other.close()


def test_farbe_nur_bei_ampel_rot_gelb_ausser_eingeschaltet():
    from ticket_table import CLOSED_COLOR, SLA_COLORS, STATE_COLORS, row_color
    assert row_color({"state": "Neu"}) is None  # Standard: ohne Ampel keine Farbe
    assert row_color({"state": "Neu", "sla": "red"})[0] == SLA_COLORS["red"]
    assert row_color({"state": "In Bearbeitung", "sla": "yellow"}, True)[0] == SLA_COLORS["yellow"]  # Ampel vor Status
    assert row_color({"state": "Gelöst", "sla": "red"}) is None  # erledigt: keine Warnung mehr
    assert row_color({"state": "Neu"}, True)[0] == STATE_COLORS["neu"]
    assert row_color({"state": "Geschlossen"}, True)[0] == CLOSED_COLOR
    assert row_color({"state": "Unbekannt"}, True) is None


def test_tabelle_merkt_farbe_an_der_ticketnummer():
    from PySide6.QtWidgets import QWidget
    from ticket_table import MARK_ROLE, SLA_COLORS, TicketTable
    widgets.QApplication.instance() or widgets.QApplication([])
    rows = [{"ticket": f"TCK000000000{i}", "subject": "x", "customer": "", "initiator": "", "recipient": "",
             "type": "", "state": "Neu", "created": f"2026-11-1{i}", "id": str(i), "sla": sla}
            for i, sla in enumerate(["", "red"])]
    host = QWidget()
    host.config = {}
    table = TicketTable("Tickets", host)
    table.set_rows(rows)
    marks = {table.row_at(r)["id"]: table.item(r, 0).data(MARK_ROLE) for r in range(2)}
    assert marks["0"] is None and marks["1"][0] == SLA_COLORS["red"]
    host.config["ticket_state_colors"] = True
    table.set_rows(rows)
    assert all(table.item(r, 0).data(MARK_ROLE) for r in range(2))


def test_neue_nachricht_blau():
    from ticket_table import MESSAGE_COLOR, SLA_COLORS, row_color
    assert row_color({"state": "In Bearbeitung", "new_message": True})[0] == MESSAGE_COLOR
    assert row_color({"state": "In Bearbeitung", "new_message": True, "sla": "red"})[0] == SLA_COLORS["red"]
    assert row_color({"state": "Gelöst", "new_message": True}) is None


def test_als_gelesen_markieren(ini):
    """Rechtsklick „Als gelesen markieren“: blau weg, bis Matrix42 das Kennzeichen zurücknimmt und neu setzt."""
    from ticket_table import MARK_ROLE, MESSAGE_COLOR, TicketTable, read_marks
    widgets.QApplication.instance() or widgets.QApplication([])
    table = TicketTable("Tickets")
    row = {"ticket": "TCK1", "id": "t1", "subject": "x", "customer": "", "initiator": "", "recipient": "", "type": "", "state": "Angehalten", "created": "", "new_message": True}
    table.set_rows([row])
    assert table.item(0, 0).data(MARK_ROLE)[0] == MESSAGE_COLOR and table.is_unread(row)
    table.mark_read(row)
    assert table.item(0, 0).data(MARK_ROLE) is None and not table.is_unread(row)
    table.set_rows([row])  # neu gelesen, Kennzeichen noch da: bleibt gelesen
    assert table.item(0, 0).data(MARK_ROLE) is None
    table.set_rows([dict(row, new_message=False)])  # Matrix42 hat es zurückgesetzt
    assert read_marks() == set()
    table.set_rows([row])  # nächste Nachricht: wieder blau
    assert table.item(0, 0).data(MARK_ROLE)[0] == MESSAGE_COLOR
    table.mark_read(row)
    table.mark_read(row, False)
    assert table.item(0, 0).data(MARK_ROLE)[0] == MESSAGE_COLOR
