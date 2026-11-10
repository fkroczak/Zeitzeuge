"""
Kollegen in der Anrufliste erkennen (ohne Qt).

Ein Anruf von einem Kollegen bleibt ein Telefonat: Er steht in der Timeline, Zeitzeuge fragt
danach (du hilfst ja auch Kollegen). Nur ist der Kollege nie der Kunde. Ohne diese Erkennung
landete „Sven Brüggemann“ als Kunde im Tagesabschluss.

Kollege ist eine Nummer, wenn
- sie eine Durchwahl ist (höchstens SHORT_DIGITS Ziffern, z. B. „787“),
- dieselbe Person auch über eine Durchwahl anruft (Handy des Kollegen),
- sie die Zentrale ist (mehrere Kollegen rufen darüber an): Endet sie auf 0, gilt der
  Anfang als Kopf für alle Durchwahlen („025429179180“ -> „02542917918…“),
- sie in der Einstellung colleague_numbers steht (Nummer oder Anfang mit * am Ende).
"""

from customers import normalize_phone

SHORT_DIGITS = 4
_IGNORE_NAMES = {"", "endcall", "musik", "unbekannt"}


def _short(number):
    text = str(number or "")
    if text.isdecimal() and text.isascii():  # häufigster Fall: nur Ziffern, ohne Umweg
        return 0 < len(text) <= SHORT_DIGITS
    digits = "".join(filter(str.isdigit, text))
    return 0 < len(digits) <= SHORT_DIGITS


class Colleagues:
    """Abfrage: is_colleague(Nummer)."""

    def __init__(self, numbers=(), prefixes=()):
        self.numbers = set(numbers)
        self.prefixes = tuple(sorted(set(prefixes)))

    def is_colleague(self, number):
        if _short(number):
            return True
        key = normalize_phone(number)
        if not key:
            return False
        return key in self.numbers or (bool(self.prefixes) and key.startswith(self.prefixes))

    def __len__(self):
        return len(self.numbers) + len(self.prefixes)


def detect(calls, manual=(), auto=True):
    """Kollegen aus allen Anrufen (Liste von {"name", "number"}) und der Einstellung manual."""
    numbers, prefixes = set(), set()
    for text in manual or []:
        text = str(text or "").strip()
        if text.endswith("*"):
            key = normalize_phone(text[:-1])
            if key:
                prefixes.add(key)
        elif normalize_phone(text):
            numbers.add(normalize_phone(text))
    if not auto:
        return Colleagues(numbers, prefixes)
    by_name = {}
    for c in calls or []:
        name = " ".join(str(c.get("name") or "").split())
        if name.casefold() in _IGNORE_NAMES:
            continue
        by_name.setdefault(name, set()).add(str(c.get("number") or ""))
    colleagues = {n for n, nums in by_name.items() if any(_short(x) for x in nums)}
    users = {}  # lange Nummer -> Kollegen, die darüber anrufen
    for name in colleagues:
        for x in by_name[name]:
            key = normalize_phone(x)
            if key and not _short(x):
                numbers.add(key)
                users.setdefault(key, set()).add(name)
    for key, names in users.items():
        if len(names) >= 2 and len(key) >= 8 and key.endswith("0"):
            prefixes.add(key[:-1])  # Zentrale: alle Durchwahlen dahinter
    return Colleagues(numbers, prefixes)
