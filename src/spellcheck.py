"""Rechtschreibprüfung in Textfeldern (Tätigkeit, Buchungstext, Ticket) über die Prüfung von
Windows (Spell Checking API, dieselbe wie in Edge und Notepad). Kein eigenes Wörterbuch nötig:
Windows bringt es mit dem deutschen Sprachpaket mit. Unter Linux oder ohne Sprachpaket ist die
Prüfung einfach aus (speller() liefert None), die Felder bleiben normal.

- attach(edit, config): Falsche Wörter rot unterkringeln (QSyntaxHighlighter), Rechtsklick auf
  ein Wort zeigt Vorschläge, „Zum Wörterbuch hinzufügen“ und „Ignorieren“.
- Schalter: Einstellungen → Darstellung → Rechtschreibprüfung (config "spellcheck", Standard an).

Die API zählt Positionen in UTF-16-Einheiten wie Qt (QString); darum passen die Positionen
direkt zu setFormat. Für Python-Strings (Wort für die Vorschläge) rechnet _utf16_slice um.
"""
import ctypes
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat, QTextCursor

LANGUAGE = "de-DE"
MAX_SUGGESTIONS = 5

_speller = None
_tried = False
_config = {}  # Config des Hauptfensters (use_config): Schalter "spellcheck" gilt für neue Fenster


def use_config(config):
    global _config
    _config = config


def _utf16_slice(text, start, length):
    data = text.encode("utf-16-le")
    return data[2 * start:2 * (start + length)].decode("utf-16-le", errors="ignore")


class _Com:
    """Kleine Hilfe für COM-Aufrufe über die Vtable (ohne comtypes)."""

    @staticmethod
    def call(obj, index, restype, *args):
        vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        # Nur „this“ ist typisiert, die übrigen Argumente (byref, c_wchar_p, c_ulong) gibt ctypes
        # unverändert weiter
        proto = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p)
        return proto(vtbl[index])(obj, *args)

    @staticmethod
    def release(obj):
        if obj:
            _Com.call(obj, 2, ctypes.c_ulong)


class WindowsSpeller:
    """ISpellChecker für eine Sprache. check(text) -> [(Start, Länge)], suggest(wort) -> [Wörter]."""

    CLSID_FACTORY = "{7AB36653-1796-484B-BDFA-E74F1DB7C1DC}"
    IID_FACTORY = "{8E018A9D-2415-4677-BF08-794EA61F94BB}"

    def __init__(self, language=LANGUAGE):
        ole = ctypes.oledll.ole32
        try:
            ole.CoInitializeEx(None, 2)  # STA; schon initialisiert (Qt) ist kein Fehler
        except OSError:
            pass
        clsid, iid = _guid(self.CLSID_FACTORY), _guid(self.IID_FACTORY)
        factory = ctypes.c_void_p()
        ole.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(factory))
        try:
            supported = ctypes.c_int()
            _Com.call(factory, 4, ctypes.HRESULT, ctypes.c_wchar_p(language), ctypes.byref(supported))
            if not supported.value:
                raise OSError(f"Sprache {language} nicht installiert")
            checker = ctypes.c_void_p()
            _Com.call(factory, 5, ctypes.HRESULT, ctypes.c_wchar_p(language), ctypes.byref(checker))
            self._checker = checker
        finally:
            _Com.release(factory)
        self._free = ole.CoTaskMemFree
        self._free.argtypes = [ctypes.c_void_p]

    def check(self, text):
        if not text.strip():
            return []
        errors = ctypes.c_void_p()
        _Com.call(self._checker, 4, ctypes.HRESULT, ctypes.c_wchar_p(text), ctypes.byref(errors))
        found = []
        try:
            while True:
                error = ctypes.c_void_p()
                hr = _Com.call(errors, 3, ctypes.c_long, ctypes.byref(error))
                if hr != 0 or not error:
                    break
                start, length = ctypes.c_ulong(), ctypes.c_ulong()
                _Com.call(error, 3, ctypes.HRESULT, ctypes.byref(start))
                _Com.call(error, 4, ctypes.HRESULT, ctypes.byref(length))
                _Com.release(error)
                found.append((start.value, length.value))
        finally:
            _Com.release(errors)
        return found

    def suggest(self, word):
        strings = ctypes.c_void_p()
        _Com.call(self._checker, 5, ctypes.HRESULT, ctypes.c_wchar_p(word), ctypes.byref(strings))
        result = []
        try:
            while len(result) < MAX_SUGGESTIONS:
                item, fetched = ctypes.c_void_p(), ctypes.c_ulong()
                hr = _Com.call(strings, 3, ctypes.c_long, ctypes.c_ulong(1), ctypes.byref(item),
                               ctypes.byref(fetched))
                if hr != 0 or not fetched.value:
                    break
                result.append(ctypes.wstring_at(item.value))
                self._free(item)
        finally:
            _Com.release(strings)
        return result

    def add(self, word):
        _Com.call(self._checker, 6, ctypes.HRESULT, ctypes.c_wchar_p(word))

    def ignore(self, word):
        _Com.call(self._checker, 7, ctypes.HRESULT, ctypes.c_wchar_p(word))


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8)]


def _guid(text):
    guid = _GUID()
    ctypes.oledll.ole32.CLSIDFromString(ctypes.c_wchar_p(text), ctypes.byref(guid))
    return guid


def speller():
    """Die Prüfung von Windows (einmal angelegt) oder None (kein Windows, keine Sprache)."""
    global _speller, _tried
    if not _tried:
        _tried = True
        if sys.platform == "win32":
            try:
                _speller = WindowsSpeller()
            except Exception as e:  # ältere Windows-Versionen, Sprachpaket fehlt …
                print(f"Rechtschreibprüfung nicht verfügbar: {e}")
                _speller = None
    return _speller


class SpellHighlighter(QSyntaxHighlighter):
    """Falsche Wörter rot unterkringeln (wie in Word). checker: Objekt mit check(text)."""

    def __init__(self, document, checker):
        super().__init__(document)
        self.checker = checker
        self.fmt = QTextCharFormat()
        self.fmt.setUnderlineStyle(QTextCharFormat.SpellCheckUnderline)
        self.fmt.setUnderlineColor(QColor("#D13438"))

    def highlightBlock(self, text):
        try:
            errors = self.checker.check(text)
        except Exception:  # Prüfung darf das Tippen nie stören
            return
        for start, length in errors:
            self.setFormat(start, length, self.fmt)

    def error_at(self, block_text, position):
        """(Start, Länge, Wort) des Fehlers an position im Absatz oder None."""
        try:
            errors = self.checker.check(block_text)
        except Exception:
            return None
        for start, length in errors:
            if start <= position <= start + length:
                return start, length, _utf16_slice(block_text, start, length)
        return None


def attach(edit, config=None, checker=None):
    """Rechtschreibprüfung an ein QPlainTextEdit/QTextEdit hängen (nichts tun, wenn aus oder
    nicht verfügbar). Gibt den Highlighter zurück oder None."""
    if not (config if config is not None else _config).get("spellcheck", True):
        return None
    checker = checker or speller()
    if checker is None:
        return None
    highlighter = SpellHighlighter(edit.document(), checker)
    edit.setContextMenuPolicy(Qt.CustomContextMenu)
    edit.customContextMenuRequested.connect(lambda pos: _menu(edit, highlighter, pos))
    edit._spell = highlighter  # am Feld halten (sonst räumt Python ihn weg)
    return highlighter


def suggestion_menu(edit, highlighter, pos):
    """Kontextmenü mit Vorschlägen oben, darunter das normale Menü (Kopieren, Einfügen …)."""
    menu = edit.createStandardContextMenu(pos)
    cursor = edit.cursorForPosition(pos)
    block = cursor.block()
    found = highlighter.error_at(block.text(), cursor.positionInBlock())
    if not found:
        return menu
    start, length, word = found
    first = menu.actions()[0] if menu.actions() else None

    def replace(new):
        c = QTextCursor(block)
        c.setPosition(block.position() + start)
        c.setPosition(block.position() + start + length, QTextCursor.KeepAnchor)
        c.insertText(new)

    def remember(action):
        try:
            getattr(highlighter.checker, action)(word)
        except Exception as e:
            print(f"Rechtschreibprüfung: {action} ging nicht: {e}")
        highlighter.rehighlight()

    try:
        suggestions = highlighter.checker.suggest(word)
    except Exception:
        suggestions = []
    actions = []
    for text in suggestions:
        action = menu.addAction(text)
        font = action.font()
        font.setBold(True)
        action.setFont(font)
        action.triggered.connect(lambda _c=False, t=text: replace(t))
        actions.append(action)
    if not suggestions:
        none = menu.addAction("Keine Vorschläge")
        none.setEnabled(False)
        actions.append(none)
    add = menu.addAction(f"„{word}“ zum Wörterbuch hinzufügen")
    add.triggered.connect(lambda: remember("add"))
    ignore = menu.addAction("Ignorieren")
    ignore.triggered.connect(lambda: remember("ignore"))
    actions += [add, ignore]
    for action in actions:  # nach oben, vor Rückgängig/Kopieren …
        menu.removeAction(action)
    menu.insertActions(first, actions)
    if first is not None:
        menu.insertSeparator(first)
    return menu


def _menu(edit, highlighter, pos):
    suggestion_menu(edit, highlighter, pos).exec(edit.mapToGlobal(pos))
