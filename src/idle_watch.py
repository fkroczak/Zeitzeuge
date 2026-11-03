"""Abwesenheit am PC erkennen: ab X Minuten ohne Maus und Tastatur nachfragen.

Rein funktional, ohne Qt. Das Hauptfenster ruft update() alle paar Sekunden mit der
Leerlaufzeit (activity_tracker.idle_seconds) auf. Kommt nach mindestens `minutes` Minuten
ohne Eingabe die erste Eingabe, liefert update() den Zeitraum der Abwesenheit. Dann fragt
Zeitzeuge „Was war in der Zeit?“ (Telefonat, Besprechung, Vor Ort, Pause …).

Gemessen wird von der letzten Eingabe vor der Pause bis zur ersten danach. Das klappt auch,
wenn der PC dazwischen gesperrt war oder geschlafen hat: Die letzte Eingabe wird in Uhrzeit
gemerkt, nicht in Systemticks.
"""
from datetime import timedelta

TIME_FMT = "%Y-%m-%d %H:%M:%S"
IDLE_TYPE = "Abwesend vom PC"
ACTIVE_SECONDS = 30  # so kurz her muss die letzte Eingabe sein, damit "wieder da" gilt

# Schnellauswahl im Nachfrage-Fenster: (Knopftext, Kategorie, Text, Merker)
# Merker "travel" setzt den Haken „Reise“. "save": sofort speichern, ohne Text.
QUICK_CHOICES = [
    ("&Telefonat", "Telefonsupport", "Telefonat", {}),
    ("&Besprechung", "Beratung / Abstimmung", "Besprechung", {}),
    ("&Vor Ort", "Vor-Ort-Einsatz", "Vor Ort beim Kunden", {}),
    ("&Fahrt / Reise", "Fahrt / Reise", "Fahrt zum Kunden", {"travel": True}),
    ("&Pause", "Pause / Privat", "Pause", {"save": True}),
]


class IdleWatch:
    def __init__(self, minutes=15):
        self.minutes = minutes
        self.last_input = None  # Uhrzeit der letzten bekannten Eingabe

    def update(self, now, idle_seconds):
        """Einmal prüfen. Gibt {"start", "end"} zurück, wenn gerade eine lange Abwesenheit
        endete (erste Eingabe danach), sonst None."""
        if not self.minutes or self.minutes <= 0:
            self.last_input = None
            return None
        idle_seconds = max(0.0, float(idle_seconds or 0))
        latest = now - timedelta(seconds=idle_seconds)
        previous, self.last_input = self.last_input, max(latest, self.last_input or latest)
        if previous is None or idle_seconds > ACTIVE_SECONDS:
            return None
        if latest - previous >= timedelta(minutes=self.minutes):
            return {"start": previous.strftime(TIME_FMT), "end": latest.strftime(TIME_FMT)}
        return None


def idle_entry(span):
    """Eintrag für die Nachfrage (wie ein erkannter Eintrag aus den Logs)."""
    return {"start": span["start"], "end": span["end"], "type": IDLE_TYPE,
            "customer_name": "", "details": "Keine Eingabe an Maus und Tastatur",
            "idle": True}


def current_idle_seconds():
    """Leerlaufzeit von Windows, 0 auf anderen Systemen oder bei Fehlern."""
    try:
        from activity_tracker import idle_seconds
        return idle_seconds() or 0
    except Exception:
        return 0
