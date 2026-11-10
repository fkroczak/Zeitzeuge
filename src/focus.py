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
from bisect import bisect_right
from functools import lru_cache

import rules as rule_engine
import timefmt
from activity_tracker import app_label

TIME_FMT = "%Y-%m-%d %H:%M:%S"
BLOCK_TYPE = "PC-Arbeitsblock"

JUMP_SECONDS = 120       # kürzer: Sprung, der zur Haupttätigkeit zählen kann
MAX_GAP_SECONDS = 5 * 60  # längere Pause: neuer Block
MIN_BLOCK_SECONDS = 3 * 60  # kürzere Blöcke gehen im Nachbarn auf


def _t(text):
    return timefmt.parse(text)


@lru_cache(maxsize=65536)
def _sec(text):
    """Zeitstempel als Sekundenzahl (ganzzahlig, als float): Differenzen genau wie
    timedelta.total_seconds(), aber ohne datetime-Rechnung (hier Zehntausende Male je Tag)."""
    d = timefmt.parse(text)
    return float(d.toordinal() * 86400 + d.hour * 3600 + d.minute * 60 + d.second)


def _seconds(a, b):
    return _sec(b) - _sec(a)


# (Programm, Titel) -> Tätigkeit, über Aufrufe hinweg: Dieselben Fenster kommen jeden Tag
# und bei jedem Neuzeichnen wieder. Gilt nur für genau diese Regeln und Kundenliste.
_memo = {"rules": None, "keywords": None, "known": {}}
MEMO_MAX = 50000


def _known_for(rules, keywords):
    sig = repr(rules)
    if _memo["rules"] != sig or _memo["keywords"] is not keywords or len(_memo["known"]) > MEMO_MAX:
        _memo.update(rules=sig, keywords=keywords, known={})
    return _memo["known"]


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
    known = _known_for(rules, keywords)  # (Programm, Titel) -> Tätigkeit
    for s in sorted(segments or [], key=lambda s: s["start"]):
        if s["end"] <= s["start"]:
            continue
        app, title = s.get("app", ""), s.get("title", "")
        key = known.get((app, title))
        if key is None:
            key = known[(app, title)] = activity_of(s, compiled, keywords)
        pieces.append({"start": s["start"], "end": s["end"], "app": app,
                       "title": title, "key": key,
                       "seconds": _seconds(s["start"], s["end"])})
    if not pieces:
        return []

    # 2. Kurze Sprünge der Haupttätigkeit zuordnen, wenn sie dazu passen
    _attach_jumps(pieces, jump_seconds, max_gap_seconds)

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
    blocks = _absorb_short(blocks, min_block_seconds, max_gap_seconds)
    return [_finish(b) for b in blocks]


def _attach_jumps(pieces, jump_seconds, max_gap_seconds):
    """Kurze Sprünge der Haupttätigkeit zuordnen: Geht es danach mit derselben Tätigkeit weiter
    (nächstes langes Stück oder nächstes Stück dieser Tätigkeit) oder hat der Sprung denselben
    Kunden, zählt er zur Tätigkeit davor.

    Das „nächste“ Stück steht vorab fest (nächstes langes Stück je Stelle, Stellen je
    Tätigkeit), statt für jeden Sprung den Rest der Liste abzusuchen. Die Stücke hinter der
    aktuellen Stelle sind dabei noch unverändert, darum ist das Ergebnis dasselbe."""
    n = len(pieces)
    next_long = [n] * (n + 1)  # nächstes Stück ab j, das kein Sprung ist
    for j in range(n - 1, -1, -1):
        next_long[j] = j if pieces[j]["seconds"] >= jump_seconds else next_long[j + 1]
    positions = {}  # Tätigkeit -> Stellen (aufsteigend)
    for j, p in enumerate(pieces):
        positions.setdefault(p["key"], []).append(j)
    for i in range(1, n):
        p, prev = pieces[i], pieces[i - 1]
        if p["seconds"] >= jump_seconds or p["key"] == prev["key"]:
            continue
        if _seconds(prev["end"], p["start"]) > max_gap_seconds:
            continue
        k = next_long[i + 1]
        same = positions.get(prev["key"])
        if same:
            m = bisect_right(same, i)
            if m < len(same) and same[m] < k:
                k = same[m]
        nxt = pieces[k] if k < n else None
        returns = (nxt is not None and nxt["key"] == prev["key"]
                   and _seconds(p["end"], nxt["start"]) <= max_gap_seconds)
        same_customer = bool(p["key"][1]) and p["key"][1] == prev["key"][1]
        if returns or same_customer:
            p["key"] = prev["key"]
            p["jump"] = True


class _Node:
    """Block in einer verketteten Liste (Schritt 4): Nachbarn ohne Suchen in der Liste."""
    __slots__ = ("block", "prev", "next", "order", "version", "alive")

    def __init__(self, block, order):
        self.block, self.order, self.version, self.alive = block, order, 0, True
        self.prev = self.next = None


def _absorb_short(blocks, min_block_seconds, max_gap_seconds):
    """Kurze Blöcke (unter min_block_seconds) in den längeren Nachbarn aufnehmen, immer den
    kürzesten zuerst (bei gleicher Dauer den vorderen), danach gleiche Nachbarn verbinden.

    Gleiches Ergebnis wie früher (kürzesten suchen, aufnehmen, ganze Liste neu verbinden), aber
    ohne bei jedem Schritt alle Blöcke anzusehen: Ein Heap liefert den kürzesten, die Blöcke
    sind verkettet, und verbunden werden kann nur rund um den Block, der gerade gewachsen ist
    (der Rest der Liste war schon verbunden). Bei Tausenden kurzer Blöcke (viele Kunden im
    Fenstertitel) waren das vorher Sekunden."""
    import heapq
    nodes = [_Node(b, i) for i, b in enumerate(blocks)]
    for a, b in zip(nodes, nodes[1:]):
        a.next, b.prev = b, a
    head = [nodes[0] if nodes else None]
    count = [len(nodes)]
    heap = []

    def duration(node):
        return _seconds(node.block["start"], node.block["end"])

    def push(node):
        node.version += 1
        dur = duration(node)
        if dur < min_block_seconds and not node.block.get("keep"):
            heapq.heappush(heap, (dur, node.order, node.version, node))

    def remove(node):
        node.alive = False
        count[0] -= 1
        if node.prev:
            node.prev.next = node.next
        else:
            head[0] = node.next
        if node.next:
            node.next.prev = node.prev

    for node in nodes:
        push(node)
    while heap and count[0] >= 2:
        _dur, _order, version, node = heapq.heappop(heap)
        if not node.alive or version != node.version or node.block.get("keep"):
            continue  # veralteter Eintrag
        b = node.block
        candidates = []
        if node.prev and _seconds(node.prev.block["end"], b["start"]) <= max_gap_seconds:
            candidates.append(node.prev)
        if node.next and _seconds(b["end"], node.next.block["start"]) <= max_gap_seconds:
            candidates.append(node.next)
        if not candidates:
            if _seconds(b["start"], b["end"]) < 60:  # allein und unter einer Minute: Rauschen
                remove(node)
            else:
                b["keep"] = True  # allein stehender kurzer Block bleibt
            continue
        target = max(candidates, key=duration)
        _absorb(target.block, b)
        remove(node)
        push(target)
        # Gleiche Nachbarn verbinden (wie _join_same über die ganze Liste): ab dem Block vor
        # dem gewachsenen, bis ein unveränderter Block erreicht ist
        cur = target.prev or target
        while cur.next:
            nxt = cur.next
            if cur.block["key"] == nxt.block["key"] \
                    and _seconds(cur.block["end"], nxt.block["start"]) <= max_gap_seconds:
                _absorb(cur.block, nxt.block)
                remove(nxt)
                push(cur)
                continue
            if nxt is not target:
                break
            cur = nxt
    result, node = [], head[0]
    while node:
        result.append(node.block)
        node = node.next
    return result


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
