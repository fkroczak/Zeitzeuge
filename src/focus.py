"""PC-Aktivität zu ruhigen Arbeitsblöcken zusammenfassen.

Die Fensteraufzeichnung liefert viele kurze Stücke (Outlook 40 s, Teams 15 s, Outlook 3 min …).
In der Timeline wird daraus ein bunter Flickenteppich. Hier entstehen Blöcke wie
„E-Mail / Kommunikation, 25 min“ mit den Anteilen der Programme.

So geht es:
1. Jedes Fenster bekommt eine Tätigkeit: die Kategorie (und den Kunden) der ersten passenden
   Regel aus der Zuordnung ohne KI, sonst den Programmnamen.
2. Kurze Sprünge (unter JUMP_SECONDS) zählen zur Haupttätigkeit, wenn sie dazu passen:
   - danach geht es mit derselben Tätigkeit weiter (Outlook – kurz Teams – Outlook), oder
   - der Sprung hat denselben Kunden wie die Tätigkeit davor.
3. Aufeinanderfolgende Stücke derselben Tätigkeit werden ein Block; Pausen über MAX_GAP_SECONDS
   trennen Blöcke.
4. Blöcke unter MIN_BLOCK_SECONDS gehen im Nachbarblock auf (keine Splitter). Ihre Zeit bleibt in
   den Anteilen des Nachbarn sichtbar.

Rein funktional, ohne Qt; Zeiten als Text "JJJJ-MM-TT hh:mm:ss".
"""
from datetime import datetime

import rules as rule_engine
from activity_tracker import app_label

TIME_FMT = "%Y-%m-%d %H:%M:%S"
BLOCK_TYPE = "PC-Arbeitsblock"

JUMP_SECONDS = 120       # kürzer: Sprung, der zur Haupttätigkeit zählen kann
MAX_GAP_SECONDS = 5 * 60  # längere Pause: neuer Block
MIN_BLOCK_SECONDS = 3 * 60  # kürzere Blöcke gehen im Nachbarn auf


def _t(text):
    return datetime.strptime(text, TIME_FMT)


def _seconds(a, b):
    return (_t(b) - _t(a)).total_seconds()


def activity_of(segment, compiled, keywords=None):
    """(Tätigkeit, Kunde) eines Fensters: Regel aus der Zuordnung ohne KI, sonst das Programm.
    Der Kunde kommt aus der Regel, sonst aus einem Stichwort der Kundenliste im Titel."""
    entry = {"app": segment.get("app", ""), "customer_name": segment.get("title", ""),
             "type": "PC", "details": ""}
    hit = rule_engine.match_entry(entry, compiled, is_pc=True, keywords=keywords) if compiled else None
    if hit:
        _index, rule, customer = hit
        return rule["category"].strip(), (customer or "").strip()
    return (app_label(segment.get("app", "") or "Unbekannt"),
            rule_engine.keyword_customer(entry, keywords, is_pc=True))


def block_label(key):
    activity, customer = key
    return f"{customer} · {activity}" if customer else activity


def focus_blocks(segments, rules=None, jump_seconds=JUMP_SECONDS, max_gap_seconds=MAX_GAP_SECONDS,
                 min_block_seconds=MIN_BLOCK_SECONDS, keywords=None):
    """Fensterstücke [{start, end, app, title}] -> Arbeitsblöcke (Timeline-Format, nach Zeit)."""
    compiled = rule_engine._compile_rules(rules) if rules else []
    pieces = []
    for s in sorted(segments or [], key=lambda s: s["start"]):
        if s["end"] <= s["start"]:
            continue
        pieces.append({"start": s["start"], "end": s["end"], "app": s.get("app", ""),
                       "title": s.get("title", ""), "key": activity_of(s, compiled, keywords),
                       "seconds": _seconds(s["start"], s["end"])})
    if not pieces:
        return []

    # 2. Kurze Sprünge der Haupttätigkeit zuordnen, wenn sie dazu passen
    for i in range(1, len(pieces)):
        p, prev = pieces[i], pieces[i - 1]
        if p["seconds"] >= jump_seconds or p["key"] == prev["key"]:
            continue
        if _seconds(prev["end"], p["start"]) > max_gap_seconds:
            continue
        nxt = next((q for q in pieces[i + 1:] if q["seconds"] >= jump_seconds or q["key"] == prev["key"]),
                   None)
        returns = (nxt is not None and nxt["key"] == prev["key"]
                   and _seconds(p["end"], nxt["start"]) <= max_gap_seconds)
        same_customer = bool(p["key"][1]) and p["key"][1] == prev["key"][1]
        if returns or same_customer:
            p["key"] = prev["key"]
            p["jump"] = True

    # 3. Blöcke derselben Tätigkeit
    blocks = []
    for p in pieces:
        last = blocks[-1] if blocks else None
        if last and last["key"] == p["key"] and _seconds(last["end"], p["start"]) <= max_gap_seconds:
            last["end"] = max(last["end"], p["end"])
            last["pieces"].append(p)
        else:
            blocks.append({"start": p["start"], "end": p["end"], "key": p["key"], "pieces": [p]})

    # 4. Splitter in den Nachbarn: erst den kürzesten, dann neu prüfen
    while True:
        short = [b for b in blocks if not b.get("keep")
                 and _seconds(b["start"], b["end"]) < min_block_seconds]
        if not short or len(blocks) < 2:
            break
        b = min(short, key=lambda b: _seconds(b["start"], b["end"]))
        i = blocks.index(b)
        candidates = []
        if i > 0 and _seconds(blocks[i - 1]["end"], b["start"]) <= max_gap_seconds:
            candidates.append(blocks[i - 1])
        if i + 1 < len(blocks) and _seconds(b["end"], blocks[i + 1]["start"]) <= max_gap_seconds:
            candidates.append(blocks[i + 1])
        if not candidates:
            if _seconds(b["start"], b["end"]) < 60:  # allein und unter einer Minute: Rauschen
                blocks.pop(i)
            else:
                b["keep"] = True  # allein stehender kurzer Block bleibt
            continue
        target = max(candidates, key=lambda c: _seconds(c["start"], c["end"]))
        _absorb(target, b)
        blocks.pop(i)
        blocks = _join_same(blocks, max_gap_seconds)

    return [_finish(b) for b in blocks]


def _absorb(target, other):
    target["start"] = min(target["start"], other["start"])
    target["end"] = max(target["end"], other["end"])
    target["pieces"] = sorted(target["pieces"] + other["pieces"], key=lambda p: p["start"])


def _join_same(blocks, max_gap_seconds):
    """Benachbarte Blöcke derselben Tätigkeit (nach dem Aufnehmen eines Splitters) verbinden."""
    joined = []
    for b in blocks:
        if joined and joined[-1]["key"] == b["key"] \
                and _seconds(joined[-1]["end"], b["start"]) <= max_gap_seconds:
            _absorb(joined[-1], b)
        else:
            joined.append(b)
    return joined


def _finish(block):
    pieces = block["pieces"]
    by_key, by_app = {}, {}
    for p in pieces:
        by_key[p["key"]] = by_key.get(p["key"], 0) + p["seconds"]
        label = app_label(p["app"] or "Unbekannt")
        by_app[label] = by_app.get(label, 0) + p["seconds"]
    key = max(by_key, key=by_key.get)  # Haupttätigkeit: meiste Zeit
    total = sum(by_app.values()) or 1
    parts = sorted(by_app.items(), key=lambda kv: -kv[1])
    main_app = max(pieces, key=lambda p: p["seconds"] if p["key"] == key else 0)["app"]
    switches = sum(1 for a, b in zip(pieces, pieces[1:]) if a["app"] != b["app"])
    share = by_key[key] / total
    details = " · ".join(f"{name} {round(sec * 100 / total)} %" for name, sec in parts[:4])
    if len(parts) > 4:
        details += f" · +{len(parts) - 4} weitere"
    return {
        "start": block["start"], "end": block["end"],
        "type": f"PC: {key[0]}",
        "customer_name": key[1],   # Kunde (aus der Regel) für Eintragen und Tagesliste
        "label": block_label(key),  # Beschriftung in der Timeline
        # kürzere Beschriftungen für schmale Blöcke, die längste passende wird genommen
        "short_labels": [s for s in dict.fromkeys([key[1], key[0].split(" / ")[0],
                                                    app_label(main_app or "")]) if s],
        "category": key[0],         # Kategorie wird beim Eintragen vorgeschlagen
        "details": details,
        "app": main_app,
        "pc_block": True,
        "parts": parts,
        "switches": switches,
        "focus": share,
        # Tätigkeit kommt aus einer Regel (nicht nur der Programmname): Grundlage fürs Nachfragen
        "ruled": key[0] not in {app_label(p["app"] or "Unbekannt") for p in pieces},
        "windows": [{"start": p["start"], "end": p["end"], "app": p["app"], "title": p["title"]}
                    for p in pieces],
        "is_suggestion": True,
    }
