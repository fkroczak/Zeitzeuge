"""Rechtsklick-Menü in Timeline und Tagesliste (timeline_only.build_entry_menu).

Prüft: jeder Befehl mit Linien-Icon, erster Eintrag fett (wie ein Doppelklick), Löschen und
Verwerfen allein ganz unten, „Nicht dokumentieren“ abgetrennt, Befehle unverändert.

Läuft ohne Bildschirm als eigener Prozess (Skript).
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def check():
    from PySide6.QtWidgets import QApplication, QMenu, QWidget
    import timeline_only

    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    parent = QWidget()

    def menu_for(entry):
        menu = QMenu(parent)
        keys = timeline_only.build_entry_menu(menu, parent, entry)
        return menu, keys

    entries = {
        "tv": {"start": "2026-11-11 09:00:00", "end": "2026-11-11 09:40:00", "type": "TeamViewer",
               "customer_name": "Praxis Weber", "tv_id": "123456789"},
        "doc": {"doc": True, "doc_item": {"start": "2026-11-11 09:00:00"}},
        "open": {"open": True},
        "ai": {"ai": True, "start": "2026-11-11 11:00:00", "end": "2026-11-11 11:30:00"},
    }
    for name, entry in entries.items():
        menu, keys = menu_for(entry)
        actions = [a for a in menu.actions() if not a.isSeparator()]
        assert actions and all(not a.icon().isNull() for a in actions), name
        assert menu.defaultAction() is actions[0] and actions[0].font().bold(), name
        assert not any(a.font().bold() for a in actions[1:]), name
        assert set(keys.values()) == {i[1] for i in timeline_only.entry_menu_items(entry) if i}, name

    # Löschen bzw. Verwerfen allein ganz unten, durch eine Linie getrennt
    for name, last in (("doc", "delete"), ("ai", "reject")):
        items = timeline_only.entry_menu_items(entries[name])
        assert items[-1][1] == last and items[-2] is None, (name, items)
    items = timeline_only.entry_menu_items(entries["open"])
    assert [i and i[1] for i in items] == ["add", None, "ignore"], items
    print("Rechtsklick-Menü: OK")


try:
    check()
except Exception:
    traceback.print_exc()
    sys.stdout.flush()
    os._exit(1)
sys.stdout.flush()
os._exit(0)
