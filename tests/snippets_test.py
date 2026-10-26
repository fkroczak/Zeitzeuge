"""Textbausteine und zuletzt benutzte Texte je Kunde (ohne Oberfläche)."""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config_defaults  # noqa: E402
import snippets  # noqa: E402
from journal import Journal  # noqa: E402


def test_standardliste_und_config():
    assert "Windows-Updates installiert" in snippets.DEFAULT_SNIPPETS
    assert snippets.from_config({}) == snippets.DEFAULT_SNIPPETS
    assert snippets.from_config({"snippets": []}) == []  # bewusst geleert bleibt leer
    assert snippets.from_config({"snippets": [" A ", "a", "", 5, "B"]}) == ["A", "B"]
    defaults = config_defaults.default_config()
    assert defaults["snippets"] == snippets.DEFAULT_SNIPPETS
    assert defaults["snippets"] is not snippets.DEFAULT_SNIPPETS  # Änderungen bleiben in der Config
    assert defaults["ticket_format"] == ""  # Standard: Kopieren wie bisher


def test_clean_aus_text():
    assert snippets.clean("Updates\n\n  Neustart \nupdates\n") == ["Updates", "Neustart"]


def test_einfuegen():
    ins = snippets.insert
    assert ins("", 0, "Updates") == ("Updates", 7)
    # Am Ende einer Zeile: neue Zeile
    assert ins("Drucker geprüft", 15, "Updates") == ("Drucker geprüft\nUpdates", 23)
    # Leere neue Zeile: direkt
    assert ins("Drucker\n", 8, "Updates") == ("Drucker\nUpdates", 15)
    # Mitten im Text: mit Leerzeichen abgesetzt
    text, pos = ins("Erst dann", 5, "Updates,")
    assert text == "Erst Updates, dann" and text[:pos] == "Erst Updates, "
    text, pos = ins("Erstdann", 4, "X")
    assert text == "Erst X dann"
    # Cursor außerhalb wird begrenzt
    assert ins("A", 99, "B")[0] == "A\nB"


def test_menu_label():
    assert snippets.menu_label("Kurz") == "Kurz"
    assert snippets.menu_label("A & B") == "A && B"
    assert snippets.menu_label("Zeile 1\nZeile 2") == "Zeile 1 …"
    assert snippets.menu_label("x" * 100, width=20).endswith(" …")


def test_recent_texts():
    items = [
        {"start": "2026-10-20 09:00:00", "customer": "Müller GmbH", "text": "Updates"},
        {"start": "2026-10-21 09:00:00", "customer": "müller gmbh ", "text": "Drucker"},
        {"start": "2026-10-22 09:00:00", "customer": "Müller GmbH", "text": "updates"},
        {"start": "2026-10-22 10:00:00", "customer": "Andere AG", "text": "Backup"},
        {"start": "2026-10-23 10:00:00", "customer": "Müller GmbH", "text": ""},
    ]
    assert snippets.recent_texts(items, "Müller GmbH") == ["updates", "Drucker"]
    assert snippets.recent_texts(items, "Andere AG") == ["Backup"]
    assert snippets.recent_texts(items, "") == []
    assert snippets.recent_texts(items, "Müller GmbH", limit=1) == ["updates"]


def test_recent_items_aus_journal(tmp_path):
    j = Journal(str(tmp_path))
    j.add({"start": "2026-10-20 09:00:00", "end": "2026-10-20 09:30:00",
           "customer": "Müller GmbH", "text": "Updates"})
    j.add({"start": "2026-08-01 09:00:00", "end": "2026-08-01 09:30:00",  # älter als 60 Tage
           "customer": "Müller GmbH", "text": "Alt"})
    j2 = Journal(str(tmp_path))  # neu laden, ohne Zwischenspeicher
    items = j2.recent_items(today=datetime(2026, 10, 26))
    assert snippets.recent_texts(items, "Müller GmbH") == ["Updates"]
