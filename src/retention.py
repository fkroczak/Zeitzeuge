"""
PC-Verlauf automatisch löschen (ohne Qt).

Gelöscht wird nur der Verlauf der aktiven Fenster: die Zeilen der Ablage "aktivitaet"
in der Datenbank und der von einem anderen PC übernommene Fensterverlauf (ImportStore,
Schlüssel "pc" je Tag). Tätigkeiten, Buchungen, KI-Vorschläge, Anrufe, VPN,
Personalzeiten und übernommene Verbindungen bleiben erhalten.

Config: "pc_history_purge" (an/aus, Standard aus), "pc_history_days" (Standard 90).
Behalten werden heute und die letzten N Tage, gelöscht wird alles davor.
"""

from datetime import date, timedelta

ACTIVITY = "aktivitaet"
DEFAULT_DAYS = 90
MIN_DAYS, MAX_DAYS = 7, 3650
CHUNK = 5000  # Zeilen je Schritt, damit das Fenster nie merklich hängt


def settings(config):
    """(an?, Tage) aus der Config, ungültige Tage werden auf den erlaubten Bereich gesetzt."""
    days = config.get("pc_history_days", DEFAULT_DAYS)
    if not isinstance(days, int) or isinstance(days, bool):
        days = DEFAULT_DAYS
    return bool(config.get("pc_history_purge", False)), max(MIN_DAYS, min(MAX_DAYS, days))


def cutoff(days, today=None):
    """Erster Tag, der erhalten bleibt (JJJJ-MM-TT). Alles davor wird gelöscht."""
    today = today or date.today()
    return (today - timedelta(days=days)).isoformat()


def affected(store, name, imported, before):
    """Was beim Löschen vor before wegfiele: {"days": [...], "rows": n, "imported_days": n}."""
    own_days = [d for d in store.row_days(name) if d < before] if store else []
    rows = store.rows_before(name, before)[1] if store else 0
    other = imported.pc_days_before(before) if imported else []
    return {"days": sorted(set(own_days) | set(other)), "rows": rows,
            "imported_days": len(other)}


def purge_step(store, name, before, chunk=CHUNK):
    """Einen Schritt löschen. Gibt (gelöscht, fertig?) zurück."""
    deleted = store.delete_rows_before(name, before, limit=chunk)
    return deleted, deleted < chunk


def purge(store, name, imported, before, chunk=CHUNK):
    """Alles vor before löschen (in Schritten). Gibt (Zeilen, übernommene Tage) zurück."""
    other = imported.drop_pc_before(before) if imported else 0
    total, done = 0, False
    while store and not done:
        deleted, done = purge_step(store, name, before, chunk)
        total += deleted
    return total, other


def summary(info, before):
    """Text für die Rückfrage, z. B. "12 Tage PC-Verlauf vor dem 28.07.2026"."""
    n = len(info["days"])
    day = f"{before[8:10]}.{before[5:7]}.{before[:4]}"
    if not n:
        return f"Vor dem {day} liegt kein PC-Verlauf."
    first = info["days"][0]
    return (f"{n} Tag{'e' if n != 1 else ''} PC-Verlauf vor dem {day} "
            f"(ab {first[8:10]}.{first[5:7]}.{first[:4]}, {info['rows']} Fensterabschnitte"
            + (f", an {info['imported_days']} Tagen auch Übernommenes von einem anderen PC"
               if info["imported_days"] else "") + ")")
