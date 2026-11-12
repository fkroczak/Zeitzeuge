"""Tages- und Wochenbericht als Selbstauskunft (PDF, zum Ausdrucken).

Fehlt eine Buchung in Matrix42 (z. B. „Mittwoch Vormittag Jahresgespräch mit Vor- und
Nachbereitung, knapp 4 Stunden“), zeigt der Bericht, was zu der Zeit gemacht wurde:
- die eigenen Tätigkeiten mit Uhrzeit, Kunde, Text und ob sie in Matrix42 gebucht sind,
- die Personalzeit ohne Matrix42-Buchung, je Lücke mit dem, was sie belegt,
- die Buchungen aus Matrix42 zum Vergleich,
- die automatisch aufgezeichneten Spuren (Termine, Telefonate, Verbindungen, PC-Arbeit),
- oben der Zeitgraph des Tages (chart), in der Woche eine Zeile je Tag (week_chart).

Rein funktional, ohne Qt: build_day sammelt die Daten eines Tages, html baut daraus das
Dokument. Das PDF schreibt report_pdf.py.
"""
import html as _html
from datetime import datetime, timedelta

import booking_rate as br

# Gemeinsame Farben von Bericht und Timeline (Standard der type_colors in main_timeline.py):
# kräftig genug für 3 : 1 auf hellem und dunklem Grund. Das PDF füllt die Balken heller und
# nimmt diese Farbe als Rand (report_pdf.STYLES), die Timeline füllt mit ihr.
STATUS_COLORS = {
    "personal": "#808080",     # Personalzeit / Arbeitszeit: grau
    "booking": "#3D6E9E",      # in Matrix42 gebucht: blau
    "gap": "#C0392B",          # Personalzeit ohne Buchung: rot
    "doc_booked": "#2F7A4A",   # Tätigkeit dokumentiert (und gebucht): grün
    "doc_missing": "#AE5F10",  # offen / nicht gebucht: orange
}
# Timeline-Zeile Dokumentation: eingetragen, aber (noch) nicht in Matrix42 gebucht -> orange wie im PDF
DOC_UNBOOKED_TYPE = "Dokumentiert, nicht in Matrix42"
TYPE_STATUS = {"Personalzeit": "personal", "Arbeitszeit": "personal", "Matrix42-Buchung": "booking",
               "Nicht gebucht": "gap", "Dokumentiert": "doc_booked", "Undokumentiert": "doc_missing",
               DOC_UNBOOKED_TYPE: "doc_missing"}

CHART_PREFIX = "zeitgraph-"  # Bildname im HTML; report_pdf.py zeichnet das Bild dazu

TIME_FMT = "%Y-%m-%d %H:%M:%S"
DAY_NAMES = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
# Spuren, die als Beleg nichts beitragen (die Matrix42-Zeile steht eigens im Bericht)
SKIP_TYPES = ("Matrix42-Buchung", "Undokumentiert", "Dokumentiert", "Dokumentiert, nicht in Matrix42")
# Viele kurze Einträge derselben Art (Dateien, Browser) werden zu einer Zeile zusammengefasst
MERGE_TYPES = ("Datei geöffnet", "Browser")
MERGE_GAP = timedelta(minutes=10)
DETAILS_MAX = 140
BOOKED_SHARE = 0.5  # ab diesem Anteil gilt eine Tätigkeit als gebucht (wie m42_data.unbooked)


def _dt(text):
    return datetime.strptime(text, TIME_FMT)


def hm(seconds):
    """Dauer als „3:45 h“ (unter einer Stunde „25 min“)."""
    minutes = int(round(max(seconds, 0) / 60))
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60}:{minutes % 60:02d} h"


def _overlap(a1, e1, a2, e2):
    return max(0.0, (min(e1, e2) - max(a1, a2)).total_seconds())


def _short(text, limit=DETAILS_MAX):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


# ------------------------------------------------------------------ Daten eines Tages


def booking_state(item, bookings):
    """(Kurztext, Stufe) einer eigenen Tätigkeit gegenüber Matrix42.

    Stufe: "booked", "partly", "missing" oder "unknown" (Matrix42 für den Tag nicht gelesen)."""
    if item.get("m42_entry"):
        return f"gebucht ({item['m42_entry']})", "booked"
    if bookings is None:
        return "Matrix42 nicht gelesen", "unknown"
    a, e = _dt(item["start"]), _dt(item["end"])
    length = (e - a).total_seconds()
    spans = br.merge(br.booking_spans(bookings))
    covered = sum(_overlap(a, e, s, t) for s, t in spans)
    if length > 0 and covered >= BOOKED_SHARE * length:
        return "gebucht", "booked"
    if covered > 0:
        return f"nur {hm(covered)} gebucht", "partly"
    return "nicht gebucht", "missing"


def merge_traces(traces):
    """Spuren nach Beginn, Matrix42 weg, Dateien/Browser dicht hintereinander als ein Eintrag."""
    result = []
    for t in sorted(traces, key=lambda x: x.get("start", "")):
        kind = t.get("type") or "Aktivität"
        if kind in SKIP_TYPES or t.get("m42"):
            continue
        try:
            a, e = _dt(t["start"]), _dt(t["end"])
        except (KeyError, TypeError, ValueError):
            continue
        name = (t.get("customer_name") or "").strip()
        last = result[-1] if result else None
        if (kind in MERGE_TYPES and last and last["type"] == kind
                and a - last["_end"] <= MERGE_GAP):
            last["_end"] = max(last["_end"], e)
            if name and name not in last["_names"]:
                last["_names"].append(name)
            continue
        result.append({"type": kind, "_start": a, "_end": max(a, e), "_names": [name] if name else [],
                       "details": t.get("details") or "", "row": chart_row(t)})
    out = []
    for r in result:
        names = r["_names"]
        what = ", ".join(names[:4]) + (f" (+{len(names) - 4} weitere)" if len(names) > 4 else "")
        details = r["details"] if len(names) <= 1 else ""
        out.append({"start": r["_start"], "end": r["_end"], "type": r["type"], "row": r["row"],
                    "what": _short(what), "details": _short(details)})
    return out


def _label(kind):
    return kind[4:] if kind.startswith("PC: ") else kind


def evidence_in(start, end, docs, traces, limit=6):
    """Was die Zeit start–end belegt: eigene Tätigkeiten zuerst, dann die längsten Spuren."""
    found = []
    for d in docs:
        if _overlap(start, end, d["start"], d["end"]) > 0:
            text = " · ".join(t for t in (d["customer"], d["what"]) if t)
            found.append(f"Tätigkeit {d['start']:%H:%M}–{d['end']:%H:%M}: {text}")
    spans = []
    for t in traces:
        share = _overlap(start, end, t["start"], t["end"])
        if share > 0 or (t["start"] == t["end"] and start <= t["start"] < end):
            spans.append((share, t))
    spans.sort(key=lambda x: -x[0])
    for _share, t in spans[:max(limit - len(found), 2)]:
        text = " · ".join(x for x in (_label(t["type"]), t["what"]) if x)
        found.append(f"{t['start']:%H:%M}–{t['end']:%H:%M} {text}")
    return found


def build_day(date_str, spans, docs, bookings, traces, from_itm=False, now=None, gap_minutes=5,
              itm_day=None, running=False):
    """Alles für den Bericht eines Tages.

    spans: Personalzeit [(Beginn, Ende)] (aus ITM, sonst Arbeitszeit lt. Einstellungen);
    docs: eigene Tätigkeiten (journal); bookings: Matrix42-Buchungen oder None (nicht gelesen);
    traces: Spuren des Tages im Timeline-Format ({start, end, type, customer_name, details})."""
    now = now or datetime.now()
    day = datetime.strptime(date_str, "%Y-%m-%d")
    spans = sorted((a, e) for a, e in spans if e > a)
    rate = br.day_rate(date_str, spans, bookings, now, from_itm=from_itm, day=itm_day,
                       running=running, gap_minutes=gap_minutes)
    items = []
    for i in sorted(docs, key=lambda x: x.get("start", "")):
        try:
            a, e = _dt(i["start"]), _dt(i["end"])
        except (KeyError, TypeError, ValueError):
            continue
        state, level = booking_state(i, bookings)
        what = " · ".join(t for t in (i.get("category"), (i.get("text") or "").strip()) if t)
        flags = [n for k, n in (("goodwill", "Kulanz"), ("travel", "Reise")) if i.get(k)]
        items.append({"start": a, "end": e, "seconds": (e - a).total_seconds(),
                      "customer": (i.get("customer") or "").strip(), "what": what,
                      "label": (i.get("text") or "").strip() or i.get("category") or "",
                      "ticket": (i.get("ticket") or "").strip(), "flags": flags,
                      "state": state, "level": level, "from_pc": i.get("von_pc") or ""})
    trace_rows = merge_traces(traces)
    gaps = []
    if bookings is not None:
        for a, e in rate.gaps:
            gaps.append({"start": a, "end": e, "seconds": (e - a).total_seconds(),
                         "evidence": evidence_in(a, e, items, trace_rows)})
    pauses = [(spans[k][1], spans[k + 1][0]) for k in range(len(spans) - 1)
              if spans[k + 1][0] > spans[k][1]]
    booking_rows = []
    for b in sorted(bookings or [], key=lambda x: x.get("start", "")):
        try:
            a, e = _dt(b["start"]), _dt(b["end"])
        except (KeyError, TypeError, ValueError):
            continue
        booking_rows.append({"start": a, "end": e, "seconds": (e - a).total_seconds(),
                             "customer": b.get("customer", ""), "ticket": b.get("ticket", ""),
                             "what": _short(" · ".join(t for t in (b.get("subject"), b.get("entry")) if t))})
    return {
        "date": date_str, "day": day, "name": DAY_NAMES[day.weekday()],
        "spans": spans, "pauses": pauses, "from_itm": from_itm,
        "personal_seconds": rate.personal_seconds,
        "doc_seconds": br.seconds(br.merge([(i["start"], i["end"]) for i in items])),
        "m42_read": bookings is not None, "booked_seconds": rate.booked_seconds,
        "gap_seconds": rate.gap_seconds if bookings is not None else 0,
        "unbooked_doc_seconds": sum(i["seconds"] for i in items if i["level"] in ("missing", "partly")),
        "items": items, "gaps": gaps, "bookings": booking_rows, "traces": trace_rows,
    }


def has_content(day):
    return bool(day["personal_seconds"] > 0 or day["items"] or day["bookings"] or day["traces"])


# ------------------------------------------------------------------ Zeitgraph

CALL_TYPES = ("Telefonat", "Teams-Anruf")
MEETING_TYPES = ("Termin", "Teams-Besprechung", "Mail gesendet", "Mail beantwortet", "Teams-Chat",
                 "Fahrt (vermutet)")
LOCAL_TYPES = ("PC gesperrt", "Ruhezustand", "PC aus", "Abgemeldet", "WLAN", "Netzwerk",
               "Datei geöffnet", "Browser")
# Zeilen des Zeitgraphs von oben nach unten (Personalzeit, Matrix42, Tätigkeiten stehen immer da)
ROWS = ("Personalzeit", "Matrix42", "Tätigkeiten", "Termine & Mail", "Telefon", "Verbindungen",
        "PC-Arbeit", "PC & Dateien")
MIN_BAR = timedelta(minutes=2)  # Punkte (Mail, Datei) bekommen eine sichtbare Breite


def chart_row(trace):
    """Zeile im Zeitgraph für eine Spur (Timeline-Format)."""
    kind = trace.get("type") or ""
    if kind in CALL_TYPES or "Anruf" in kind:
        return "Telefon"
    if kind in MEETING_TYPES:
        return "Termine & Mail"
    if kind.startswith("PC: "):
        return "PC-Arbeit"
    if kind in LOCAL_TYPES or trace.get("local"):
        return "PC & Dateien"
    return "Verbindungen"


def _bar(a, e, text, style):
    return {"start": a, "end": max(e, a + MIN_BAR), "text": text, "style": style}


def chart_range(day, pad=timedelta(minutes=30)):
    """Gezeigter Zeitraum: Personalzeit, Tätigkeiten und Buchungen (± 30 min) auf volle Stunden,
    ohne diese die Spuren; nichts da: 7–17 Uhr."""
    base = day["day"]
    core = [(a, e) for a, e in day["spans"]]
    core += [(i["start"], i["end"]) for i in day["items"]] + [(b["start"], b["end"]) for b in day["bookings"]]
    if not core:
        core = [(t["start"], t["end"]) for t in day["traces"]]
    if not core:
        return base + timedelta(hours=7), base + timedelta(hours=17)
    first = max(base, min(a for a, _e in core) - pad)
    last = min(base + timedelta(days=1), max(e for _a, e in core) + pad)
    first = first.replace(minute=0, second=0, microsecond=0)
    if last.minute or last.second:
        last = last.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    if last - first < timedelta(hours=4):  # mindestens 4 Stunden, sonst wird es unleserlich breit
        last = min(base + timedelta(days=1), first + timedelta(hours=4))
    return first, last


def chart(day):
    """Zeitgraph eines Tages: {start, end, rows: [(Name, [Balken])]}.

    Balken: {start, end, text, style}; style: personal, booking, gap, doc_booked, doc_missing,
    doc_unknown, trace. Leere Spur-Zeilen fallen weg."""
    start, end = chart_range(day)
    rows = {name: [] for name in ROWS}
    rows["Personalzeit"] = [_bar(a, e, "", "personal") for a, e in day["spans"]]
    rows["Matrix42"] = [_bar(b["start"], b["end"], b["customer"] or b["ticket"], "booking")
                        for b in day["bookings"]]
    rows["Matrix42"] += [_bar(g["start"], g["end"], "ohne Buchung", "gap") for g in day["gaps"]]
    styles = {"booked": "doc_booked", "missing": "doc_missing", "partly": "doc_missing"}
    rows["Tätigkeiten"] = [_bar(i["start"], i["end"], i["label"] or i["customer"],
                                styles.get(i["level"], "doc_unknown")) for i in day["items"]]
    for t in day["traces"]:
        if t["end"] > start and t["start"] < end:
            rows[t["row"]].append(_bar(t["start"], t["end"], t["what"] or _label(t["type"]), "trace"))
    keep = ROWS[:3]
    return {"start": start, "end": end,
            "rows": [(name, rows[name]) for name in ROWS if name in keep or rows[name]]}


def week_chart(days):
    """Woche: eine Zeile je Tag mit Personalzeit, Buchungen (oben) und Tätigkeiten (unten),
    gemeinsamer Zeitraum aller Tage auf volle Stunden."""
    starts, ends = [], []
    for d in days:
        if d["spans"] or d["items"] or d["bookings"]:
            a, e = chart_range(d, pad=timedelta(0))
            starts.append(a - d["day"])
            ends.append(e - d["day"])
    first = min(starts) if starts else timedelta(hours=7)
    last = max(ends) if ends else timedelta(hours=17)
    rows = []
    styles = {"booked": "doc_booked", "missing": "doc_missing", "partly": "doc_missing"}
    for d in days:
        bars = [dict(_bar(a, e, "", "personal"), lane="full") for a, e in d["spans"]]
        bars += [dict(_bar(b["start"], b["end"], "", "booking"), lane="top") for b in d["bookings"]]
        bars += [dict(_bar(g["start"], g["end"], "", "gap"), lane="top") for g in d["gaps"]]
        bars += [dict(_bar(i["start"], i["end"], "", styles.get(i["level"], "doc_unknown")), lane="bottom")
                 for i in d["items"]]
        # gleicher Uhrzeit-Bereich für jeden Tag: Balken auf einen Bezugstag verschieben
        shift = days[0]["day"] - d["day"]
        for b in bars:
            b["start"] += shift
            b["end"] += shift
        rows.append((f"{d['name'][:2]} {d['day']:%d.%m.}", bars))
    base = days[0]["day"]
    return {"start": base + first, "end": base + last, "rows": rows, "week": True}


def chart_img(name):
    """Platzhalter für das Bild; report_pdf.py setzt die Breite in Pixeln ein."""
    return f'<p><img src="{CHART_PREFIX}{name}" width="__CHART_WIDTH__"/></p>'


# ------------------------------------------------------------------ HTML


CSS = """
body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 8.5pt; color: #000; }
h1 { font-size: 15pt; margin: 0 0 2px 0; }
h2 { font-size: 11pt; margin: 12px 0 4px 0; }
p { margin: 2px 0; }
.sub { color: #444; }
.note { color: #444; font-size: 7.5pt; }
table.t { border-collapse: collapse; width: 100%; margin-top: 2px; }
table.t th { background: #e6e6e6; text-align: left; font-weight: bold; }
table.t th, table.t td { border: 1px solid #999; padding: 2px 4px; vertical-align: top; }
td.num { white-space: nowrap; }
.missing { font-weight: bold; }
.gap { background: #f2f2f2; }
"""


def _e(text):
    return _html.escape(str(text or ""))


def _span_text(spans):
    return ", ".join(f"{a:%H:%M}–{e:%H:%M}" for a, e in spans) or "–"


NUM = ' class="num"'


def _table(headers, rows, widths=None):
    out = ['<table class="t" cellspacing="0" cellpadding="3" width="100%"><tr>']
    for k, h in enumerate(headers):
        w = f' width="{widths[k]}%"' if widths else ""
        out.append(f"<th{w}>{_e(h)}</th>")
    out.append("</tr>")
    for cells, cls in rows:
        out.append(f'<tr class="{cls}">' if cls else "<tr>")
        out += [f'<td{NUM if k < 3 else ""}>{c}</td>' for k, c in enumerate(cells)]
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)


def day_html(day, person="", with_traces=True, charts=False):
    """Ein Tag als HTML-Abschnitt (ohne <html>). charts: Platz für den Zeitgraph (report_pdf.py)."""
    parts = [f"<h1>Tagesbericht {day['name']}, {day['day']:%d.%m.%Y}</h1>",
             '<p class="sub">Selbstauskunft aus eigenen Einträgen und aufgezeichneten Spuren</p>']
    if person:
        parts.append(f'<p class="sub">{_e(person)}</p>')
    kind = "Personalzeit (Zeiterfassung)" if day["from_itm"] else "Arbeitszeit lt. Einstellungen"
    first = [f"<b>{kind}:</b> {_e(_span_text(day['spans']))} = {hm(day['personal_seconds'])}"]
    if day["pauses"]:
        first.append(f"<b>Pausen:</b> {_e(_span_text(day['pauses']))}")
    parts.append("<p>" + " &nbsp;·&nbsp; ".join(first) + "</p>")
    facts = [f"<b>Selbst dokumentiert:</b> {hm(day['doc_seconds'])}"]
    if day["m42_read"]:
        facts.append(f"<b>In Matrix42 gebucht:</b> {hm(day['booked_seconds'])}")
        facts.append(f"<b>Ohne Matrix42-Buchung:</b> {hm(day['gap_seconds'])}")
    else:
        facts.append("<b>Matrix42:</b> für diesen Tag nicht gelesen")
    parts.append("<p>" + " &nbsp;·&nbsp; ".join(facts) + "</p>")
    if charts:
        parts.append("<h2>Zeitgraph</h2>" + chart_img(day["date"]))

    parts.append("<h2>Tätigkeiten (selbst dokumentiert)</h2>")
    if day["items"]:
        rows = []
        for i in day["items"]:
            what = _e(i["what"]) or "–"
            extra = [x for x in ([f"Ticket {i['ticket']}"] if i["ticket"] else []) + i["flags"]]
            if i["from_pc"]:
                extra.append(f"von {i['from_pc']}")
            if extra:
                what += f'<br/><span class="note">{_e(" · ".join(extra))}</span>'
            state = _e(i["state"])
            if i["level"] in ("missing", "partly"):
                state = f'<span class="missing">✗ {state}</span>'
            elif i["level"] == "booked":
                state = f"✓ {state}"
            rows.append(([f"{i['start']:%H:%M}", f"{i['end']:%H:%M}", hm(i["seconds"]),
                          _e(i["customer"]) or "–", what, state],
                         "gap" if i["level"] in ("missing", "partly") else ""))
        parts.append(_table(["Von", "Bis", "Dauer", "Kunde", "Tätigkeit", "Matrix42"], rows,
                            [6, 6, 7, 17, 46, 18]))
    else:
        parts.append("<p>Keine Tätigkeiten eingetragen.</p>")

    if day["m42_read"]:
        parts.append("<h2>Personalzeit ohne Matrix42-Buchung</h2>")
        if day["gaps"]:
            rows = [([f"{g['start']:%H:%M}", f"{g['end']:%H:%M}", hm(g["seconds"]),
                      "<br/>".join(_e(t) for t in g["evidence"]) or "keine Spuren aufgezeichnet"], "")
                    for g in day["gaps"]]
            parts.append(_table(["Von", "Bis", "Dauer", "Was zu der Zeit gemacht wurde (laut Aufzeichnung)"], rows,
                                [6, 6, 7, 81]))
        else:
            parts.append("<p>Keine – die Personalzeit ist vollständig gebucht.</p>")

        parts.append("<h2>Buchungen in Matrix42 (zum Vergleich)</h2>")
        if day["bookings"]:
            rows = [([f"{b['start']:%H:%M}", f"{b['end']:%H:%M}", hm(b["seconds"]), _e(b["customer"]) or "–",
                      _e(b["ticket"]) or "–", _e(b["what"]) or "–"], "") for b in day["bookings"]]
            parts.append(_table(["Von", "Bis", "Dauer", "Kunde", "Ticket", "Beschreibung"], rows,
                                [6, 6, 7, 18, 13, 50]))
        else:
            parts.append("<p>Keine Buchungen.</p>")

    if with_traces:
        parts.append("<h2>Aufgezeichnete Spuren</h2>")
        if day["traces"]:
            rows = []
            for t in day["traces"]:
                same = t["start"] == t["end"] or (t["end"] - t["start"]) < timedelta(minutes=1)
                what = _e(t["what"]) or "–"
                if t["details"] and t["details"] != t["what"]:
                    what += f'<br/><span class="note">{_e(t["details"])}</span>'
                rows.append(([f"{t['start']:%H:%M}", "" if same else f"{t['end']:%H:%M}",
                              "" if same else hm((t["end"] - t["start"]).total_seconds()),
                              _e(_label(t["type"])), what], ""))
            parts.append(_table(["Von", "Bis", "Dauer", "Quelle", "Was"], rows, [6, 6, 7, 18, 63]))
        else:
            parts.append("<p>Keine Spuren aufgezeichnet.</p>")
    return "".join(parts)


def week_html(days, person="", charts=False):
    """Übersicht einer Woche als HTML-Abschnitt."""
    first, last = days[0]["day"], days[-1]["day"]
    parts = [f"<h1>Wochenbericht KW {first.isocalendar()[1]} · {first:%d.%m.} – {last:%d.%m.%Y}</h1>",
             '<p class="sub">Selbstauskunft aus eigenen Einträgen und aufgezeichneten Spuren</p>']
    if person:
        parts.append(f'<p class="sub">{_e(person)}</p>')
    rows = []
    totals = [0.0, 0.0, 0.0, 0.0]
    for d in days:
        vals = [d["personal_seconds"], d["doc_seconds"], d["booked_seconds"], d["gap_seconds"]]
        totals = [a + b for a, b in zip(totals, vals)]
        booked = hm(d["booked_seconds"]) if d["m42_read"] else "nicht gelesen"
        gap = hm(d["gap_seconds"]) if d["m42_read"] else "–"
        open_items = sum(1 for i in d["items"] if i["level"] in ("missing", "partly"))
        rows.append(([f"{d['name'][:2]} {d['day']:%d.%m.}", _e(_span_text(d["spans"])),
                      hm(d["personal_seconds"]), hm(d["doc_seconds"]), booked,
                      f'<span class="missing">{gap}</span>' if d["gap_seconds"] else gap,
                      str(open_items) if open_items else "–"], ""))
    rows.append((["<b>Summe</b>", "", f"<b>{hm(totals[0])}</b>", f"<b>{hm(totals[1])}</b>",
                  f"<b>{hm(totals[2])}</b>", f"<b>{hm(totals[3])}</b>", ""], "gap"))
    parts.append(_table(["Tag", "Personalzeit", "Stunden", "Dokumentiert", "In Matrix42",
                         "Ohne Buchung", "Tätigkeiten ungebucht"], rows,
                        [10, 24, 10, 13, 13, 13, 17]))
    if charts:
        parts.append("<h2>Zeitgraph der Woche</h2>" + chart_img("woche"))
    gaps = [(d, g) for d in days for g in d["gaps"]]
    if gaps:
        parts.append("<h2>Zeit ohne Matrix42-Buchung</h2>")
        parts.append(_table(["Tag", "Von–Bis", "Dauer", "Was zu der Zeit gemacht wurde (laut Aufzeichnung)"],
                            [([f"{d['name'][:2]} {d['day']:%d.%m.}",
                               f"{g['start']:%H:%M}–{g['end']:%H:%M}", hm(g["seconds"]),
                               "<br/>".join(_e(t) for t in g["evidence"][:3]) or "–"], "")
                             for d, g in gaps], [9, 13, 8, 70]))
    parts.append('<p class="note">Details je Tag auf den folgenden Seiten.</p>')
    return "".join(parts)


def signature_html(created):
    return (f'<p class="note" style="margin-top:14px">Selbstauskunft, erstellt am {created:%d.%m.%Y um %H:%M} '
            "mit Zeitzeuge aus den eigenen Einträgen und den auf diesem PC aufgezeichneten Spuren.</p>"
            '<table width="100%" style="margin-top:28px"><tr>'
            '<td width="45%" style="border-top:1px solid #000">Ort, Datum</td><td width="10%"></td>'
            '<td width="45%" style="border-top:1px solid #000">Unterschrift</td></tr></table>')


def document(days, week=False, person="", with_traces=True, created=None, charts=False):
    """Ganzes HTML-Dokument: Tagesbericht (ein Tag) oder Wochenbericht (Übersicht + je Tag).

    charts: Zeitgraphen als Bilder einbinden (Namen siehe charts_for, zeichnet report_pdf.py)."""
    created = created or datetime.now()
    body = []
    if week:
        body.append(week_html(days, person, charts))
        body.append(signature_html(created))
    for k, d in enumerate(days):
        brk = ' style="page-break-before: always"' if (week or k) else ""
        body.append(f"<div{brk}>{day_html(d, person, with_traces, charts)}"
                    f"{'' if week else signature_html(created)}</div>")
    return (f"<html><head><meta charset='utf-8'><style>{CSS}</style></head>"
            f"<body>{''.join(body)}</body></html>")


def charts_for(days, week=False):
    """{Bildname: Zeitgraph} passend zu document(..., charts=True)."""
    found = {CHART_PREFIX + d["date"]: chart(d) for d in days}
    if week:
        found[CHART_PREFIX + "woche"] = week_chart(days)
    return found


def file_name(days, week=False):
    first = days[0]["day"]
    if week:
        return f"Wochenbericht_KW{first.isocalendar()[1]:02d}_{first:%Y}.pdf"
    return f"Tagesbericht_{first:%Y-%m-%d}.pdf"
