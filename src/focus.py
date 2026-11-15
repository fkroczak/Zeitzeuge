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


_sec = timefmt.seconds  # Zeitstempel als Sekundenzahl (float), hier Zehntausende Male je Tag


def _seconds(a, b):
    return _sec(b) - _sec(a)


# (Programm, Titel) -> Tätigkeit, über Aufrufe hinweg: Dieselben Fenster kommen jeden Tag
# und bei jedem Neuzeichnen wieder. Gilt nur für genau diese Regeln und Kundenliste.
_memo = {"rules": None, "keywords": None, "known": {}}
MEMO_MAX = 50000


def _known_for(rules, keywords):
    sig = repr(rules)
    if _memo["rules"] != sig or _memo["keywords"] is not keywords:
        _memo.update(rules=sig, keywords=keywords, known={})
    known = _memo["known"]
    if len(known) > MEMO_MAX:  # voll: die älteste Hälfte vergessen statt alles (Fenster von heute bleiben)
        for old in list(known)[:len(known) // 2]:
            del known[old]
    return known


# Felder, die bei einem Fenster immer gleich sind (rules._fields mit is_pc=True)
PC_CONSTANTS = {"type": "PC", "customer": "", "details": ""}


def activity_of(segment, compiled, keywords=None):
    """(Tätigkeit, Kunde) eines Fensters: Regel aus der Zuordnung ohne KI, sonst das Programm.
    Der Kunde kommt aus der Regel, sonst aus einem Stichwort der Kundenliste im Titel."""
    entry = {"app": segment.get("app", ""), "customer_name": segment.get("title", ""),
             "type": PC_CONSTANTS["type"], "details": PC_CONSTANTS["details"]}
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
    # Typ, Kunde und Details sind bei Fenstern immer gleich (siehe activity_of)
    compiled = rule_engine.drop_impossible(compiled, PC_CONSTANTS)
    pieces = []
    known = _known_for(rules, keywords)  # (Programm, Titel) -> Tätigkeit
    for s in sorted(segments or [], key=lambda s: s["start"]):
        if s["end"] <= s["start"]:
            continue
        app, title = s.get("app", ""), s.get("title", "")
        key = known.get((app, title))
        if key is None:
            key = known[(app, title)] = activity_of(s, compiled, keywords)
        a, b = _sec(s["start"]), _sec(s["end"])
        pieces.append({"start": s["start"], "end": s["end"], "app": app,
                       "title": title, "key": key, "seconds": b - a, "_s": a, "_e": b})
    if not pieces:
        return []

    # 2. Kurze Sprünge der Haupttätigkeit zuordnen, wenn sie dazu passen
    _attach_jumps(pieces, jump_seconds, max_gap_seconds)

    # 3. Blöcke derselben Tätigkeit
    blocks = []
    last = None
    last_end = 0.0  # Ende von last in Sekunden
    for p in pieces:
        if last is not None and last["key"] == p["key"] and p["_s"] - last_end <= max_gap_seconds:
            if p["end"] > last["end"]:
                last["end"], last_end = p["end"], p["_e"]
            last["pieces"].append(p)
            last["_e"] = last_end
        else:
            last = {"start": p["start"], "end": p["end"], "key": p["key"], "pieces": [p], "_s": p["_s"]}
            last["_e"] = last_end = p["_e"]
            blocks.append(last)

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
    # Zeiten einmal als Sekunden (focus_blocks hat sie schon ausgerechnet)
    starts = [p["_s"] if "_s" in p else _sec(p["start"]) for p in pieces]
    ends = [p["_e"] if "_e" in p else _sec(p["end"]) for p in pieces]
    keys = [p["key"] for p in pieces]
    short = [p["seconds"] < jump_seconds for p in pieces]
    next_long = [n] * (n + 1)  # nächstes Stück ab j, das kein Sprung ist
    for j in range(n - 1, -1, -1):
        next_long[j] = next_long[j + 1] if short[j] else j
    positions = {}  # Tätigkeit -> Stellen (aufsteigend)
    for j, key in enumerate(keys):
        positions.setdefault(key, []).append(j)
    for i in range(1, n):
        key, prev_key = keys[i], keys[i - 1]
        if not short[i] or key == prev_key:
            continue
        if starts[i] - ends[i - 1] > max_gap_seconds:
            continue
        k = next_long[i + 1]
        same = positions.get(prev_key)
        if same:
            m = bisect_right(same, i)
            if m < len(same) and same[m] < k:
                k = same[m]
        # keys[k] ist noch unverändert (nur Stücke vor i wurden umgehängt)
        returns = k < n and keys[k] == prev_key and starts[k] - ends[i] <= max_gap_seconds
        if returns or (bool(key[1]) and key[1] == prev_key[1]):
            p = pieces[i]
            p["key"] = keys[i] = prev_key
            p["jump"] = True


class _Node:
    """Block in einer verketteten Liste (Schritt 4): Nachbarn ohne Suchen in der Liste."""
    __slots__ = ("block", "prev", "next", "order", "version", "alive", "s", "e")

    def __init__(self, block, order):
        self.block, self.order, self.version, self.alive = block, order, 0, True
        self.prev = self.next = None
        # Beginn und Ende in Sekunden (focus_blocks gibt sie mit)
        self.s = block["_s"] if "_s" in block else _sec(block["start"])
        self.e = block["_e"] if "_e" in block else _sec(block["end"])


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
        return node.e - node.s

    def absorb(target, other):  # wie _absorb, Sekunden mitführen
        _absorb(target.block, other.block)
        # Aus dem Text wie früher (min/max der Zeitstempel als Text), nicht aus den Zahlen:
        # gleich auch bei ungewöhnlich geschriebenen Zeiten, deren Textfolge abweicht
        target.s, target.e = _sec(target.block["start"]), _sec(target.block["end"])

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
        if node.prev and node.s - node.prev.e <= max_gap_seconds:
            candidates.append(node.prev)
        if node.next and node.next.s - node.e <= max_gap_seconds:
            candidates.append(node.next)
        if not candidates:
            if node.e - node.s < 60:  # allein und unter einer Minute: Rauschen
                remove(node)
            else:
                b["keep"] = True  # allein stehender kurzer Block bleibt
            continue
        target = max(candidates, key=duration)
        absorb(target, node)
        remove(node)
        push(target)
        # Gleiche Nachbarn verbinden (wie _join_same über die ganze Liste): ab dem Block vor
        # dem gewachsenen, bis ein unveränderter Block erreicht ist
        cur = target.prev or target
        while cur.next:
            nxt = cur.next
            if cur.block["key"] == nxt.block["key"] and nxt.s - cur.e <= max_gap_seconds:
                absorb(cur, nxt)
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
    mine, theirs = target["pieces"], other["pieces"]
    # Beide Listen sind nach Beginn sortiert: meist hängt die eine glatt an die andere
    # (gleiches Ergebnis wie das stabile sorted, ohne jedes Stück anzufassen)
    if not theirs or (mine and theirs[0]["start"] >= mine[-1]["start"]):
        target["pieces"] = mine + theirs
    elif not mine or theirs[-1]["start"] < mine[0]["start"]:
        target["pieces"] = theirs + mine
    else:
        target["pieces"] = sorted(mine + theirs, key=lambda p: p["start"])


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
