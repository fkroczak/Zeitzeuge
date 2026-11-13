"""Tickettabelle: der Betreff bekommt den Platz, Kunde/Melder/Bearbeiter wachsen nur mäßig mit."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

widgets = pytest.importorskip("PySide6.QtWidgets")


def _widths(width):
    from ticket_table import COLUMNS, TicketTable
    app = widgets.QApplication.instance() or widgets.QApplication([])
    table = TicketTable("Tickets")
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


def test_betreff_ist_die_breiteste_spalte():
    sizes, _ = _widths(1000)
    assert sizes["subject"] >= 250, sizes
    assert sizes["subject"] > 2 * sizes["customer"], sizes


def test_schmal_ohne_waagerechte_scrollleiste():
    sizes, viewport = _widths(760)
    assert sum(sizes.values()) <= viewport, (sizes, viewport)
    assert min(sizes[k] for k in ("customer", "initiator", "recipient")) >= 70, sizes
