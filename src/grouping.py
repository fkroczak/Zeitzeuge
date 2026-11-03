"""
Tagesliste übersichtlicher machen.

RDM schreibt jede Passwort- und OTP-Anzeige als eigene Zeile, VPN-Verbindungen
brechen oft ab und werden neu aufgebaut, TeamViewer ebenso. Hier werden solche
Einträge zusammengefasst:

- group_entries: Verbindungen zum selben Eintrag mit kurzer Pause werden eine
  Zeile. Passwort-/OTP-Anzeigen hängen als Zähler an der passenden Verbindung.
- work_blocks: alles mit kurzer Pause dazwischen wird ein Arbeitsblock,
  z. B. "01:18–02:05 · SSL VPN, EPM, OPNsense" für das Ticket.

Die Originaleinträge bleiben unter "parts" erhalten (Detailansicht).
"""

import re
from collections import Counter
from datetime import datetime, timedelta

TIME_FMT = "%Y-%m-%d %H:%M:%S"

# Anzeigen von Zugangsdaten (aus RDM) und ihr Kurzname im Zähler
CREDENTIAL_TYPES = {
    "OTP-Anzeige": "OTP",
    "Passwortaktion": "Passwort",
    "Benutzername angezeigt": "Benutzername",
    "Eintrag angezeigt": "Eintrag geöffnet",
}
CREDENTIAL_TYPE = "Zugangsdaten"
BLOCK_TYPE = "Arbeitsblock"


def _t(text):
    return datetime.fromisoformat(text)  # Zeiten sind beim Laden schon geprüft


def _protocol(entry):
    """Verbindungsart, nach der zusammengefasst wird, oder None (nie zusammenfassen)."""
    if "app" in entry or entry.get("direction"):  # PC-Verlauf, Telefonate
        return None
    kind = entry.get("type", "")
    if kind == "TeamViewer":
        return "TeamViewer"
    match = re.match(r"^(.+)-(Verbindung|Sitzung)$", kind)
    return match.group(1) if match else None


def _count_text(counter):
    order = list(CREDENTIAL_TYPES.values())
    return ", ".join(f"{counter[k]}× {k}" for k in order if counter.get(k))


def _summary(connections, creds):
    parts = []
    if connections > 1:
        parts.append(f"{connections} Verbindungen")
    if creds:
        parts.append(_count_text(creds))
    return " · ".join(parts)


def group_entries(entries, gap_minutes=5):
    """Verbindungen und Zugangsdaten-Anzeigen zusammenfassen (siehe Moduldoku)."""
    gap = timedelta(minutes=gap_minutes)
    groups, creds, rest = [], [], []

    for entry in sorted(entries, key=lambda e: e["start"]):
        if entry.get("type") in CREDENTIAL_TYPES and "app" not in entry:
            creds.append(entry)
            continue
        proto = _protocol(entry)
        if proto is None:
            rest.append(entry)
            continue
        start, end = _t(entry["start"]), _t(entry["end"])
        key = (proto, entry.get("customer_name", ""))
        last = next((g for g in reversed(groups) if g["key"] == key), None)
        if last is not None and start <= last["end"] + gap:
            last["end"] = max(last["end"], end)
            last["parts"].append(entry)
        else:
            groups.append({"key": key, "start": start, "end": end, "parts": [entry],
                           "creds": Counter()})

    # Zugangsdaten an die Verbindung zum selben Eintrag hängen, sonst eigene Gruppe
    loose = []
    for entry in creds:
        when = _t(entry["start"])
        name = entry.get("customer_name", "")
        target = next((g for g in groups if g["key"][1] == name
                       and g["start"] - gap <= when <= g["end"] + gap), None)
        if target is None:
            target = next((g for g in reversed(loose) if g["key"][1] == name
                           and when <= g["end"] + gap), None)
            if target is None:
                target = {"key": (CREDENTIAL_TYPE, name), "start": when, "end": when,
                          "parts": [], "creds": Counter()}
                loose.append(target)
            target["end"] = max(target["end"], _t(entry["end"]))
        target["creds"][CREDENTIAL_TYPES[entry["type"]]] += 1
        target["parts"].append(entry)

    result = list(rest)
    for g in groups + loose:
        proto, name = g["key"]
        first = g["parts"][0]
        if len(g["parts"]) == 1 and proto != CREDENTIAL_TYPE:
            result.append(first)  # nichts zusammengefasst: Original behalten
            continue
        connections = sum(1 for p in g["parts"] if p.get("type") not in CREDENTIAL_TYPES)
        if proto == CREDENTIAL_TYPE:
            kind = CREDENTIAL_TYPE
        elif proto == "TeamViewer":
            kind = "TeamViewer"
        else:
            kind = f"{proto}-Verbindung"
        merged = {
            "start": g["start"].strftime(TIME_FMT),
            "end": g["end"].strftime(TIME_FMT),
            "type": kind,
            "customer_name": name,
            "details": _summary(connections, g["creds"]),
            "is_suggestion": True,
            "parts": sorted(g["parts"], key=lambda e: e["start"]),
        }
        if "tv_id" in first:
            merged["tv_id"] = first["tv_id"]
        result.append(merged)

    result.sort(key=lambda e: e["start"])
    return result


def work_blocks(entries, gap_minutes=10):
    """Alles mit höchstens gap_minutes Pause zu Arbeitsblöcken zusammenfassen."""
    gap = timedelta(minutes=gap_minutes)
    blocks = []
    for entry in sorted((e for e in entries if "app" not in e), key=lambda e: e["start"]):
        start, end = _t(entry["start"]), _t(entry["end"])
        if blocks and start <= blocks[-1]["end"] + gap:
            blocks[-1]["end"] = max(blocks[-1]["end"], end)
            blocks[-1]["parts"].append(entry)
        else:
            blocks.append({"start": start, "end": end, "parts": [entry]})

    result = []
    for b in blocks:
        # Namen nach Dauer sortiert, wichtigste zuerst
        weight = Counter()
        kinds = []
        for p in b["parts"]:
            name = p.get("customer_name") or p.get("type", "")
            weight[name] += (_t(p["end"]) - _t(p["start"])).total_seconds() + 1
            kind = _protocol(p) or p.get("type", "")
            if kind not in kinds:
                kinds.append(kind)
        count = sum(len(p.get("parts", [p])) for p in b["parts"])
        result.append({
            "start": b["start"].strftime(TIME_FMT),
            "end": b["end"].strftime(TIME_FMT),
            "type": BLOCK_TYPE,
            "customer_name": ", ".join(name for name, _ in weight.most_common()),
            "details": f"{', '.join(kinds)} · {count} Einträge",
            "is_suggestion": True,
            "parts": b["parts"],
        })
    return result


def format_tv_id(tv_id):
    """1076789144 -> '1 076 789 144' (wie TeamViewer die ID anzeigt)."""
    text = str(tv_id)
    groups = []
    while text:
        groups.insert(0, text[-3:])
        text = text[:-3]
    return " ".join(groups)
