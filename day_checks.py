"""Prüfung bei Feierabend: Auffälligkeiten eines Tages finden.

Rein funktional, ohne Qt. Eingaben sind Zeitspannen als datetime:
- Personalzeit (gestempelte Abschnitte aus ITM),
- PC-Aktivität (aktive Fenster, timeline.pc_entries_for),
- Matrix42-Buchungen ({start, end, ...} als Text "JJJJ-MM-TT hh:mm:ss").

Fehler der Stempelungen selbst (offen seit 12 Stunden, Ende vor Start) meldet schon
der ITM-Leser (itm_auth.booking_issues). Die stehen hier bewusst nicht noch einmal.
"""
from dataclasses import dataclass
from datetime import datetime

import booking_rate as br

# Arbeitszeitgesetz § 4: mehr als 6 h -> 30 min Pause, mehr als 9 h -> 45 min.
# Pausen zählen ab 15 Minuten am Stück. Länger als 6 h am Stück ohne Pause ist nicht erlaubt.
PAUSE_RULES = [(9 * 3600, 45 * 60), (6 * 3600, 30 * 60)]
PAUSE_MIN_BLOCK = 15 * 60
MAX_BLOCK = 6 * 3600

PC_MIN_MINUTES = 10       # so lange am PC aktiv, aber ausgestempelt, bevor es auffällt
PC_JOIN_SECONDS = 5 * 60  # PC-Aktivität mit kürzerer Lücke gilt als ein Stück
BOOKING_MIN_MINUTES = 5   # so viel einer Buchung muss außerhalb liegen
OVERLAP_MIN_MINUTES = 1


@dataclass
class Finding:
    kind: str    # "pause", "pc_outside", "booking_outside", "overlap", "rate"
    text: str
    start: datetime = None


def _hm(t):
    return t.strftime("%H:%M")


def _dur(secs):
    return br.duration(secs)


def pause_findings(spans):
    """Pausen nach ArbZG prüfen. spans: gestempelte Abschnitte [(start, end)]."""
    spans = br.merge(spans)
    if not spans:
        return []
    worked = sum((b - a).total_seconds() for a, b in spans)
    findings = []
    # Pausen = Lücken zwischen den Abschnitten; nur Blöcke ab 15 Minuten zählen
    breaks = [(spans[i][1], spans[i + 1][0]) for i in range(len(spans) - 1)]
    counted = sum((b - a).total_seconds() for a, b in breaks
                  if (b - a).total_seconds() >= PAUSE_MIN_BLOCK)
    for limit, needed in PAUSE_RULES:
        if worked > limit:
            if counted < needed:
                hours = limit // 3600
                findings.append(Finding(
                    "pause",
                    f"Mehr als {hours} Stunden gearbeitet ({_dur(worked)}), aber nur "
                    f"{_dur(counted)} Pause gestempelt (nötig {needed // 60} min, Blöcke ab 15 min)",
                    spans[0][0]))
            break
    if findings:  # zu wenig Pause insgesamt: das reicht als Hinweis
        return findings
    # Länger als 6 Stunden am Stück: Stücke zwischen Pausen ab 15 Minuten
    block_start, block_end = spans[0]
    for a, b in spans[1:]:
        if (a - block_end).total_seconds() >= PAUSE_MIN_BLOCK:
            findings += _long_block(block_start, block_end)
            block_start = a
        block_end = b
    findings += _long_block(block_start, block_end)
    return findings


def _long_block(a, b):
    if (b - a).total_seconds() > MAX_BLOCK:
        return [Finding("pause", f"{_hm(a)}–{_hm(b)} mehr als 6 Stunden am Stück ohne Pause "
                                 f"({_dur((b - a).total_seconds())})", a)]
    return []


def _outside(spans, inside):
    """Teile von spans, die nicht in inside liegen. -> [(start, end)]"""
    return br.gaps(spans, inside, min_minutes=0)


def pc_outside_findings(personal, pc, min_minutes=PC_MIN_MINUTES, now=None):
    """PC aktiv, aber ausgestempelt. pc: [(start, end)] der aktiven Fenster."""
    if not personal:
        return []  # ganz ohne Stempelung (frei, Urlaub) nichts melden
    # Kurze Lücken zwischen Fenstern überbrücken, damit Stücke zusammenhängen
    joined = []
    for a, b in sorted(pc):
        if now is not None:
            b = min(b, now)
        if b <= a:
            continue
        if joined and (a - joined[-1][1]).total_seconds() <= PC_JOIN_SECONDS:
            joined[-1] = (joined[-1][0], max(joined[-1][1], b))
        else:
            joined.append((a, b))
    findings = []
    for a, b in _outside(joined, personal):
        if (b - a).total_seconds() >= min_minutes * 60:
            findings.append(Finding("pc_outside", f"PC aktiv {_hm(a)}–{_hm(b)} "
                                                  f"({_dur((b - a).total_seconds())}), aber ausgestempelt", a))
    return findings


def booking_outside_findings(personal, bookings, min_minutes=BOOKING_MIN_MINUTES):
    """Matrix42-Buchung (ganz oder teilweise) außerhalb der Personalzeit."""
    if not personal:
        return []
    findings = []
    for b in bookings or []:
        span = br.booking_spans([b])
        if not span:
            continue
        outside = sum((e - a).total_seconds() for a, e in _outside(span, personal))
        if outside >= min_minutes * 60:
            a, e = span[0]
            what = " · ".join(t for t in (b.get("customer"), b.get("ticket")) if t)
            findings.append(Finding(
                "booking_outside",
                f"Buchung {_hm(a)}–{_hm(e)}{f' ({what})' if what else ''}: "
                f"{_dur(outside)} außerhalb der Personalzeit", a))
    return findings


def overlap_findings(bookings, min_minutes=OVERLAP_MIN_MINUTES):
    """Matrix42-Buchungen, die sich überschneiden (doppelt gebucht?)."""
    items = []
    for b in bookings or []:
        span = br.booking_spans([b])
        if span:
            items.append((span[0][0], span[0][1], b))
    items.sort(key=lambda x: x[0])
    findings = []
    for i, (a1, e1, _b1) in enumerate(items):
        for a2, e2, _b2 in items[i + 1:]:
            if a2 >= e1:
                break
            overlap = (min(e1, e2) - a2).total_seconds()
            if overlap >= min_minutes * 60:
                findings.append(Finding(
                    "overlap", f"Buchungen {_hm(a1)}–{_hm(e1)} und {_hm(a2)}–{_hm(e2)} "
                               f"überschneiden sich ({_dur(overlap)})", a2))
    return findings


def rate_finding(rate, target=br.TARGET_PERCENT):
    """Quote unter Ziel (nur, wenn Matrix42 gelesen ist)."""
    percent = rate.percent if rate is not None else None
    if percent is None or percent >= target:
        return []
    return [Finding("rate", f"Buchungsquote {br.percent_text(percent)} – "
                            f"{br.level_text(br.level(percent, target), target)}, "
                            f"{_dur(rate.gap_seconds)} nicht gebucht")]


def check_day(personal, pc=(), bookings=None, rate=None, target=br.TARGET_PERCENT, from_itm=True,
              pc_min_minutes=PC_MIN_MINUTES, booking_min_minutes=BOOKING_MIN_MINUTES, now=None):
    """Alle Prüfungen eines Tages, nach Uhrzeit sortiert.

    Ohne ITM (from_itm=False) ist die Personalzeit nur die geplante Arbeitszeit aus den
    Einstellungen: Pausen, PC außerhalb und Buchungen außerhalb lassen sich dann nicht
    sinnvoll prüfen und entfallen."""
    findings = []
    if from_itm:
        findings += pause_findings(personal)
        findings += pc_outside_findings(personal, pc, pc_min_minutes, now)
        findings += booking_outside_findings(personal, bookings, booking_min_minutes)
    findings += overlap_findings(bookings)
    findings += rate_finding(rate, target)
    return sorted(findings, key=lambda f: (f.start is None, f.start or datetime.min))


def after_hours(now, spans, running, planned_end=None):
    """Ist jetzt Feierabend? spans: Personalzeit des Tages [(start, end)].

    Eingestempelt: nein. Ausgestempelt: ab dem geplanten Ende (Arbeitszeit aus den
    Einstellungen), ohne Plan eine Stunde nach dem letzten Ausstempeln – so zählt die
    Mittagspause nicht als Feierabend."""
    if running or not spans:
        return False
    last = max(b for _a, b in spans)
    if now < last:
        return False
    if planned_end is not None:
        return now >= max(planned_end, last)
    return (now - last).total_seconds() >= 3600
