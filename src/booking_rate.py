"""Buchungsquote: wie viel der Personalzeit in Matrix42 gebucht ist.

Rein funktional, ohne Qt. Das Hauptfenster (week_dialogs.py) sammelt je Tag die
Personalzeit (ITM, sonst Arbeitszeit aus den Einstellungen) und die Matrix42-Buchungen
und gibt sie hier hinein.

Quote eines Tages = gebuchte Zeit (Buchungen zusammengeführt, Überschneidungen nur
einmal) ÷ Personalzeit. Heute zählt nur bis jetzt.

7-Tage-Wert = die letzten 7 Tage mit Personalzeit (gestempelt), rückwärts ab heute.
Tage, für die Matrix42 nicht gelesen ist, zählen nicht mit (weder gebucht noch
Personalzeit) und werden als „Matrix42 nicht gelesen“ gekennzeichnet – sonst sähe es
aus, als hättest du nichts gebucht.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta

TIME_FMT = "%Y-%m-%d %H:%M:%S"

# Farbstufen (Prozent). Ziel ist einstellbar (config "booking_target_percent").
TARGET_PERCENT = 80
RED_BELOW = 50     # darunter rot
FULL_PERCENT = 100  # darüber dunkelgrün
SEVEN_DAYS = 7
LOOKBACK_DAYS = 31  # so weit zurück werden gestempelte Tage für den 7-Tage-Wert gesucht

# Stufe -> (Symbol, Text). Der Zustand steht so immer auch als Zeichen und Wort da.
LEVELS = {
    "low": ("✗", "unter 50 %"),
    "mid": ("!", "unter Ziel"),
    "ok": ("✓", "Ziel erreicht"),
    "over": ("✓✓", "über 100 %"),
    "none": ("–", "Matrix42 nicht gelesen"),
}


def level(percent, target=TARGET_PERCENT):
    """Farbstufe zu einer Quote: "low" (< 50), "mid" (bis unter Ziel), "ok" (Ziel bis 100),
    "over" (> 100), "none" (keine Quote)."""
    if percent is None:
        return "none"
    red = min(RED_BELOW, target)
    if percent < red:
        return "low"
    if percent < target:
        return "mid"
    if percent <= FULL_PERCENT:
        return "ok"
    return "over"


def level_text(lvl, target=TARGET_PERCENT):
    """Kurzer Text zur Stufe, z. B. "unter Ziel (80 %)"."""
    symbol, text = LEVELS[lvl]
    if lvl == "mid":
        text = f"unter Ziel ({target} %)"
    elif lvl == "low" and target < RED_BELOW:
        text = f"unter {target} %"
    return f"{symbol} {text}"


def percent_text(percent):
    return "–" if percent is None else f"{int(round(percent))} %"


def _dt(text):
    return datetime.strptime(text, TIME_FMT)


def merge(spans):
    """[(start, end)] zusammenführen, sortiert, ohne Überschneidungen."""
    out = []
    for a, b in sorted(s for s in spans if s[1] > s[0]):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def seconds(spans):
    return sum((b - a).total_seconds() for a, b in merge(spans))


def booking_spans(bookings, until=None):
    """Buchungen -> [(start, end)] als datetime, auf Wunsch nur bis until (heute: jetzt)."""
    spans = []
    for b in bookings or []:
        try:
            a, e = _dt(b["start"]), _dt(b["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if until is not None:
            e = min(e, until)
        if e > a:
            spans.append((a, e))
    return spans


def itm_spans(day, now):
    """Personalzeiten aus ITM ({"zeiten": [{start, end}]}) -> ([(start, end)], eingestempelt?).
    Ein offener Abschnitt (noch eingestempelt) zählt bis jetzt."""
    spans, running = [], False
    for t in (day or {}).get("zeiten") or []:
        try:
            a = _dt(t["start"])
            e = _dt(t["end"]) if t.get("end") else None
        except (KeyError, TypeError, ValueError):
            continue
        if e is None:
            running = True
            e = max(a, now)
        if e > a:
            spans.append((a, e))
    return spans, running


@dataclass
class DayRate:
    date: str
    personal_seconds: float = 0
    booked_seconds: float = 0
    m42_read: bool = False   # Matrix42-Daten für diesen Tag vorhanden
    from_itm: bool = False   # Personalzeit aus ITM (sonst Arbeitszeit aus den Einstellungen)
    running: bool = False    # noch eingestempelt
    gaps: list = field(default_factory=list)  # [(start, end)] Personalzeit ohne Buchung

    @property
    def stamped(self):
        """Zählt als gearbeiteter Tag für den 7-Tage-Wert."""
        if self.personal_seconds <= 0:
            return False
        # Ohne ITM wissen wir nicht, ob du gearbeitet hast (Urlaub, krank). Ein Tag mit
        # Arbeitszeit aus den Einstellungen zählt nur, wenn es Buchungen gibt.
        return self.from_itm or self.booked_seconds > 0

    @property
    def percent(self):
        if not self.m42_read or self.personal_seconds <= 0:
            return None
        return 100.0 * self.booked_seconds / self.personal_seconds

    @property
    def gap_seconds(self):
        return sum((b - a).total_seconds() for a, b in self.gaps)


def personal_seconds(spans, day=None, running=False):
    """Personalzeit in Sekunden. ITM liefert "gewertet" (Minuten, z. B. nach Abzug der Pause):
    das gilt, solange du ausgestempelt bist. Eingestempelt (heute) zählen die Abschnitte bis jetzt."""
    gewertet = (day or {}).get("gewertet")
    if not running and isinstance(gewertet, (int, float)) and gewertet > 0:
        return float(gewertet) * 60
    return seconds(spans)


def day_rate(date_str, spans, bookings, now, from_itm=False, day=None, running=False,
             gap_minutes=5):
    """Quote eines Tages.

    spans: Personalzeit [(start, end)] als datetime (heute schon bis jetzt gekürzt).
    bookings: Matrix42-Buchungen des Tages oder None (= nicht gelesen).
    day: ITM-Tag (für "gewertet"), sonst None.
    """
    until = now if date_str == now.strftime("%Y-%m-%d") else None
    if until is not None:
        spans = [(a, min(b, until)) for a, b in spans if min(b, until) > a]
    rate = DayRate(date_str, from_itm=from_itm, running=running, m42_read=bookings is not None)
    if date_str > now.strftime("%Y-%m-%d"):
        return rate
    rate.personal_seconds = personal_seconds(spans, day if from_itm else None, running)
    if bookings is not None:
        booked = booking_spans(bookings, until)
        rate.booked_seconds = seconds(booked)
        rate.gaps = gaps(spans, booked, gap_minutes)
    return rate


def gaps(work_spans, booked_spans, min_minutes=5):
    """Teile der Personalzeit ohne Buchung (kürzer als min_minutes zählen nicht)."""
    booked = merge(booked_spans)
    result = []
    for ws, we in merge(work_spans):
        cur = ws
        for bs, be in booked:
            if be <= cur or bs >= we:
                continue
            if bs > cur:
                result.append((cur, bs))
            cur = max(cur, be)
            if cur >= we:
                break
        if cur < we:
            result.append((cur, we))
    return [(a, b) for a, b in result if (b - a).total_seconds() >= min_minutes * 60]


@dataclass
class SevenDays:
    percent: float = None
    days: list = field(default_factory=list)      # gezählte Tage (DayRate)
    unread: list = field(default_factory=list)    # gestempelt, aber Matrix42 nicht gelesen
    personal_seconds: float = 0
    booked_seconds: float = 0

    @property
    def window(self):
        """Alle Tage des Zeitraums (gezählt und nicht gelesen), neueste zuerst."""
        return sorted(self.days + self.unread, key=lambda r: r.date, reverse=True)


def seven_days(rates, count=SEVEN_DAYS):
    """7-Tage-Wert aus DayRates (beliebige Reihenfolge, auch Tage ohne Personalzeit).

    Nimmt die letzten count Tage mit Personalzeit. Davon zählen nur die, für die
    Matrix42 gelesen ist: Summe gebucht ÷ Summe Personalzeit."""
    stamped = sorted((r for r in rates if r.stamped), key=lambda r: r.date, reverse=True)[:count]
    result = SevenDays()
    for r in stamped:
        (result.days if r.m42_read else result.unread).append(r)
    result.personal_seconds = sum(r.personal_seconds for r in result.days)
    result.booked_seconds = sum(r.booked_seconds for r in result.days)
    if result.personal_seconds > 0:
        result.percent = 100.0 * result.booked_seconds / result.personal_seconds
    return result


def lookback_dates(today, days=LOOKBACK_DAYS):
    """Tage ab heute rückwärts (YYYY-MM-DD) für die Suche nach gestempelten Tagen."""
    d = datetime.strptime(today, "%Y-%m-%d") if isinstance(today, str) else today
    return [(d - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]


def week_dates(day):
    """Montag bis Sonntag der Woche von day (YYYY-MM-DD)."""
    d = datetime.strptime(day, "%Y-%m-%d")
    monday = d - timedelta(days=d.weekday())
    return [(monday + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]


def duration(secs):
    """Sekunden -> "1:20 h" / "45 min" / "0 min"."""
    minutes = int(round(secs / 60))
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60}:{minutes % 60:02d} h"
