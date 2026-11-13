"""Rechtschreibprüfung: Unterkringeln, Vorschläge im Rechtsklick-Menü, Ersetzen, Wörterbuch.
Die Prüfung von Windows ist hier nachgebaut (unter Linux gibt es sie nicht)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QTextCharFormat  # noqa: E402
from PySide6.QtWidgets import QApplication, QPlainTextEdit  # noqa: E402

import spellcheck  # noqa: E402

app = QApplication.instance() or QApplication([])


class FakeChecker:
    """Kennt „Druker“ als falsch (Vorschlag „Drucker“); add/ignore merken sich das Wort."""

    def __init__(self):
        self.known = set()

    def check(self, text):
        found, i = [], text.find("Druker")
        while i >= 0:
            if "Druker" not in self.known:
                found.append((i, 6))
            i = text.find("Druker", i + 1)
        return found

    def suggest(self, word):
        return ["Drucker", "Drücker"] if word == "Druker" else []

    def add(self, word):
        self.known.add(word)

    ignore = add


def test_unterkringeln_und_vorschlaege():
    edit = QPlainTextEdit("Neuen Druker eingerichtet")
    checker = FakeChecker()
    highlighter = spellcheck.attach(edit, {"spellcheck": True}, checker)
    assert highlighter is not None
    highlighter.rehighlight()
    formats = edit.document().firstBlock().layout().formats()
    assert any(f.start == 6 and f.length == 6 and
               f.format.underlineStyle() == QTextCharFormat.SpellCheckUnderline for f in formats), \
        [(f.start, f.length) for f in formats]
    assert highlighter.error_at("Neuen Druker eingerichtet", 8) == (6, 6, "Druker")
    assert highlighter.error_at("Neuen Druker eingerichtet", 1) is None

    # Rechtsklick auf das Wort: Vorschläge oben, dann Wörterbuch, darunter das normale Menü
    cursor = edit.textCursor()
    cursor.setPosition(8)
    edit.setTextCursor(cursor)
    pos = edit.cursorRect(cursor).center()
    menu = spellcheck.suggestion_menu(edit, highlighter, pos)
    texts = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert texts[:4] == ["Drucker", "Drücker", "„Druker“ zum Wörterbuch hinzufügen", "Ignorieren"], texts
    assert len(texts) > 4, "Standardmenü (Kopieren, Einfügen …) bleibt darunter"
    next(a for a in menu.actions() if a.text() == "Drucker").trigger()
    assert edit.toPlainText() == "Neuen Drucker eingerichtet"

    # Zum Wörterbuch hinzufügen: nicht mehr unterkringelt
    edit.setPlainText("Druker")
    menu = spellcheck.suggestion_menu(edit, highlighter, edit.cursorRect(edit.textCursor()).center())
    next(a for a in menu.actions() if "Wörterbuch" in a.text()).trigger()
    assert "Druker" in checker.known and checker.check("Druker") == []


def test_aus_oder_nicht_verfuegbar():
    edit = QPlainTextEdit("Druker")
    assert spellcheck.attach(edit, {"spellcheck": False}, FakeChecker()) is None
    if sys.platform != "win32":
        assert spellcheck.speller() is None
        assert spellcheck.attach(QPlainTextEdit(), {}) is None  # ohne Windows-Prüfung: Feld wie bisher


def test_utf16_positionen():
    # Windows und Qt zählen UTF-16: ein Emoji davor verschiebt um 2
    assert spellcheck._utf16_slice("😀 Druker", 3, 6) == "Druker"


def test_com_aufruf_typisiert_alle_argumente():
    """Jedes Argument bekommt einen Typ – sonst lehnt ctypes stdcall-Aufrufe mit mehr als
    einem Argument ab und die Windows-Prüfung startet nie."""
    import ctypes
    got = {}

    @ctypes.CFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int),
                      ctypes.c_ulong)
    def method(this, text, out, n):
        got["text"], got["n"] = text, n
        out[0] = 7
        return 0

    vtbl = (ctypes.c_void_p * 1)(ctypes.cast(method, ctypes.c_void_p))
    obj = ctypes.pointer(ctypes.pointer(vtbl))  # Objekt -> Vtable-Zeiger -> Vtable
    out = ctypes.c_int()
    types = spellcheck._argtypes([ctypes.c_wchar_p("x"), ctypes.byref(out), ctypes.c_ulong(3)])
    assert types == [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_ulong]
    hr = spellcheck._Com.call(ctypes.cast(obj, ctypes.c_void_p), 0, ctypes.c_long,
                              ctypes.c_wchar_p("Druker"), ctypes.byref(out), ctypes.c_ulong(3))
    assert hr == 0 and out.value == 7 and got == {"text": "Druker", "n": 3}
