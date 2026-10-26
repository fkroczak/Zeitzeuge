"""
Abrechnungstakt (ohne Qt): Dauer einer Tätigkeit auf den Takt des Kunden bringen.

Standard: 15-Minuten-Takt, angefangene Viertelstunde wird abgerechnet ("up").
Je Kunde kann ein anderer Takt oder Modus gelten (Config "billing_customers").

Modi:
    "up"       aufrunden: jede angefangene Taktlänge zählt (10 min -> 15 min)
    "nearest"  kaufmännisch auf den nächsten Takt (22 min -> 15, 23 min -> 30)
    "off"      ohne Takt: abgerechnet = echte Dauer (wie bisher)

Gerechnet wird in ganzen Minuten (Sekunden kaufmännisch gerundet, wie bei der Anzeige
der Dauer). Mindesttakt: Jede Tätigkeit mit Dauer > 0 zählt mindestens einen Takt.
Mehrere Tätigkeiten am selben Tag für denselben Kunden werden je Tätigkeit gerundet
(jede Zeile im Ticket steht für sich, die Summe passt zu den Zeilen).

Die Config-Schlüssel:
    "billing_step_minutes": 15,
    "billing_mode": "up",
    "billing_customers": {"Müller GmbH": {"step": 30, "mode": "nearest"}, ...}
"""

import math
from datetime import datetime, timedelta

TIME_FMT = "%Y-%m-%d %H:%M:%S"
MODES = ("up", "nearest", "off")
DEFAULT_STEP = 15
DEFAULT_MODE = "up"
MODE_NAMES = {"up": "angefangener Takt zählt (aufrunden)",
              "nearest": "auf den nächsten Takt runden",
              "off": "ohne Takt (echte Dauer)"}


def _minutes(seconds):
    """Ganze Minuten (kaufmännisch gerundet), nie negativ."""
    if not seconds or seconds <= 0:
        return 0
    return int(math.floor(seconds / 60 + 0.5))


def billed_minutes(seconds, step=DEFAULT_STEP, mode=DEFAULT_MODE):
    """Abzurechnende Minuten für eine Dauer in Sekunden.

    >>> billed_minutes(12 * 60)
    15
    """
    if not seconds or seconds <= 0:
        return 0
    minutes = _minutes(seconds)
    try:
        step = int(step)
    except (TypeError, ValueError):
        step = 0
    if mode not in ("up", "nearest") or step <= 0:
        return max(minutes, 1)  # "off": echte Dauer, wie duration_text mindestens 1 min
    if mode == "up":
        units = -(-minutes // step)  # aufrunden
    else:
        units = (2 * minutes + step) // (2 * step)  # bei genau halb aufrunden
    return max(units, 1) * step


def hours_text(minutes):
    """Minuten als "H:MM h" (abgerechnete Zeit immer in Stunden)."""
    minutes = int(minutes)
    return f"{minutes // 60}:{minutes % 60:02d} h"


def _norm(name):
    return " ".join((name or "").split()).casefold()


def _valid_rule(rule, fallback):
    """(Takt, Modus) aus einem Config-Eintrag, Ungültiges fällt auf fallback zurück."""
    step, mode = fallback
    if isinstance(rule, dict):
        value = rule.get("step", step)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and 1 <= value <= 480:
            step = int(value)
        if rule.get("mode") in MODES:
            mode = rule["mode"]
    return step, mode


class Billing:
    """Regeln für die Abrechnung: Standard-Takt und Ausnahmen je Kunde."""

    def __init__(self, step=DEFAULT_STEP, mode=DEFAULT_MODE, customers=None):
        self.default = _valid_rule({"step": step, "mode": mode}, (DEFAULT_STEP, DEFAULT_MODE))
        self.customers = {}
        self.names = {}  # normierter Name -> Name wie eingegeben
        for name, rule in (customers or {}).items():
            if isinstance(name, str) and name.strip():
                self.customers[_norm(name)] = _valid_rule(rule, self.default)
                self.names[_norm(name)] = name.strip()

    @classmethod
    def from_config(cls, config):
        config = config or {}
        customers = config.get("billing_customers")
        return cls(config.get("billing_step_minutes", DEFAULT_STEP),
                   config.get("billing_mode", DEFAULT_MODE),
                   customers if isinstance(customers, dict) else {})

    def to_config(self, config):
        config["billing_step_minutes"], config["billing_mode"] = self.default
        config["billing_customers"] = {self.names[k]: {"step": s, "mode": m}
                                       for k, (s, m) in self.customers.items()}
        return config

    def rule(self, customer=""):
        """(Takt, Modus) für einen Kunden (groß/klein und Leerzeichen egal)."""
        return self.customers.get(_norm(customer), self.default)

    def active(self, customer=""):
        return self.rule(customer)[1] != "off"

    def minutes(self, seconds, customer=""):
        step, mode = self.rule(customer)
        return billed_minutes(seconds, step, mode)

    def item_minutes(self, item):
        """Abzurechnende Minuten einer Tätigkeit ({start, end, customer})."""
        try:
            seconds = (_t(item["end"]) - _t(item["start"])).total_seconds()
        except (KeyError, TypeError, ValueError):
            return 0
        return self.minutes(seconds, item.get("customer", ""))

    def note(self, seconds, customer=""):
        """Zusatz zur Dauer, z. B. " → abgerechnet 0:15 h" ("" ohne Takt)."""
        if not self.active(customer) or seconds <= 0:
            return ""
        return f" → abgerechnet {hours_text(self.minutes(seconds, customer))}"

    def describe(self, customer=""):
        """Kurzer Text zur Regel, z. B. "15-Minuten-Takt, angefangener Takt zählt"."""
        step, mode = self.rule(customer)
        if mode == "off":
            return "ohne Abrechnungstakt"
        return f"{step}-Minuten-Takt, " + ("angefangener Takt zählt" if mode == "up"
                                          else "auf den nächsten Takt gerundet")

    def total_minutes(self, items):
        """Summe der abgerechneten Minuten (je Tätigkeit gerundet)."""
        return sum(self.item_minutes(i) for i in items)

    def any_active(self):
        return self.default[1] != "off" or any(m != "off" for _s, m in self.customers.values())


def _t(text):
    return datetime.strptime(text, TIME_FMT)


def booking_span(item, billing):
    """Beginn und Ende für eine Buchung (z. B. später in Matrix42): Beginn bleibt (auf die
    Minute), Ende = Beginn + abgerechnete Dauer. Ohne Takt: echte Zeiten (auf die Minute).

    Gibt (start, end) als datetime zurück. Ändert item nicht.
    """
    start, end = _t(item["start"]), _t(item["end"])
    start_min = start.replace(second=0)
    if not billing or not billing.active(item.get("customer", "")):
        return start_min, max(end.replace(second=0), start_min + timedelta(minutes=1))
    minutes = billing.minutes((end - start).total_seconds(), item.get("customer", ""))
    return start_min, start_min + timedelta(minutes=minutes)


def booking_item(item, billing):
    """Kopie der Tätigkeit mit Beginn/Ende im Takt (Zeiten als Text wie im Journal)."""
    start, end = booking_span(item, billing)
    return {**item, "start": start.strftime(TIME_FMT), "end": end.strftime(TIME_FMT)}
