"""
Textbausteine und zuletzt benutzte Texte für den Eintragen-Dialog (reine Logik, ohne Qt).

Die Bausteine stehen in der Config ("snippets"), die zuletzt benutzten Texte kommen aus
den eingetragenen Tätigkeiten (journal.Journal.recent_items).
"""

# Häufige Sätze bei IT-Dienstleistern. Pflegbar über Einstellungen → Textbausteine.
DEFAULT_SNIPPETS = [
    "Windows-Updates installiert",
    "Neustart durchgeführt, Funktion geprüft",
    "Benutzer angelegt, Rechte vergeben",
    "Passwort zurückgesetzt",
    "Drucker eingerichtet, Treiber aktualisiert",
    "Outlook-Profil neu angelegt",
    "Backup geprüft",
    "Rückruf, Problem besprochen",
    "Fernwartung, Fehler behoben",
    "Mit Kunde abgestimmt, wartet auf Rückmeldung",
]

MAX_LENGTH = 500


def clean(lines):
    """Bausteine aus einer Liste oder einem Text (eine Zeile je Baustein): ohne Leerzeilen
    und Doppelte, Reihenfolge bleibt."""
    if isinstance(lines, str):
        lines = lines.splitlines()
    result, seen = [], set()
    for line in lines or []:
        if not isinstance(line, str):
            continue
        line = line.strip()[:MAX_LENGTH]
        if line and line.lower() not in seen:
            seen.add(line.lower())
            result.append(line)
    return result


def from_config(config):
    """Bausteine aus der Config, sonst die Standardliste."""
    saved = config.get("snippets")
    return clean(saved) if isinstance(saved, list) else list(DEFAULT_SNIPPETS)


def recent_texts(items, customer, limit=8):
    """Die letzten verschiedenen Texte zu einem Kunden, neueste zuerst.

    items: Tätigkeiten (dicts mit customer, text, start), in beliebiger Reihenfolge.
    Kunde ohne Groß-/Kleinschreibung verglichen. Leerer Kunde = keine Vorschläge."""
    customer = (customer or "").strip().lower()
    if not customer:
        return []
    mine = [i for i in items if isinstance(i, dict)
            and (i.get("customer") or "").strip().lower() == customer and (i.get("text") or "").strip()]
    mine.sort(key=lambda i: (i.get("start", ""), i.get("updated", "")), reverse=True)
    result, seen = [], set()
    for item in mine:
        text = item["text"].strip()
        if text.lower() not in seen:
            seen.add(text.lower())
            result.append(text)
        if len(result) >= limit:
            break
    return result


def menu_label(text, width=60):
    """Eine Zeile fürs Menü: erste Zeile, gekürzt, "&" nicht als Alt-Buchstabe."""
    first = text.strip().splitlines()[0] if text.strip() else ""
    more = "\n" in text.strip()
    if len(first) > width:
        first, more = first[:width - 1].rstrip(), True
    return first.replace("&", "&&") + (" …" if more else "")


def insert(text, pos, snippet):
    """Baustein an der Cursorposition einfügen. -> (neuer Text, neue Cursorposition)

    Steht der Cursor am Ende einer nicht leeren Zeile, kommt der Baustein in eine neue Zeile.
    Mitten im Text mit Leerzeichen abgesetzt."""
    pos = max(0, min(pos, len(text)))
    before, after = text[:pos], text[pos:]
    line_before = before.rsplit("\n", 1)[-1]
    if line_before.strip() and (not after or after[0] == "\n"):
        piece = "\n" + snippet
    elif line_before and not line_before[-1].isspace():
        piece = " " + snippet
    else:
        piece = snippet
    if after and not after[0].isspace():
        piece += " "
    return before + piece + after, pos + len(piece)
