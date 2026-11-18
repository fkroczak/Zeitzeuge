"""Rechtschreibprüfung in Textfeldern (Tätigkeit, Buchungstext, Ticket) über die Prüfung von
Windows (Spell Checking API, dieselbe wie in Edge und Notepad). Kein eigenes Wörterbuch nötig:
Windows bringt es mit dem deutschen Sprachpaket mit. Unter Linux oder ohne Sprachpaket ist die
Prüfung einfach aus (speller() liefert None), die Felder bleiben normal.

- attach(edit, config): Falsche Wörter rot unterkringeln (QSyntaxHighlighter), Rechtsklick auf
  ein Wort zeigt Vorschläge, „Zum Wörterbuch hinzufügen“ und „Ignorieren“.
- Autokorrektur: Nach Leertaste, Satzzeichen oder Enter ersetzt Zeitzeuge das eben getippte Wort,
  wenn Windows dafür eine feste Korrektur kennt (CORRECTIVE_ACTION_REPLACE, z. B. eigene Paare
  aus „Immer automatisch ersetzen“ im Rechtsklick-Menü). Bei bloßen Vorschlägen wird nur
  unterkringelt. Strg+Z direkt danach nimmt die Korrektur zurück, das Wort bleibt dann im Feld.
- Schalter: Einstellungen → Darstellung → Rechtschreibprüfung (config "spellcheck", Standard an),
  Autokorrektur (config "autocorrect", Standard an, braucht die Rechtschreibprüfung).

Die API zählt Positionen in UTF-16-Einheiten wie Qt (QString); darum passen die Positionen
direkt zu setFormat. Für Python-Strings (Wort für die Vorschläge) rechnet _utf16_slice um.
"""
import ctypes
import re
import sys

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QColor, QKeySequence, QSyntaxHighlighter, QTextCharFormat, QTextCursor

LANGUAGE = "de-DE"
MAX_SUGGESTIONS = 5
CORRECTIVE_ACTION_REPLACE = 2
AUTOCORRECT_KEYS = " .,;:!?)\r\n\t"  # nach diesen Zeichen wird das Wort davor korrigiert
_MODIFIER_KEYS = {Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta, Qt.Key_AltGr}
_WORD_BEFORE = re.compile(r"[^\W\d_][\w'-]*$")

_speller = None
_tried = False
_config = {}  # Config des Hauptfensters (use_config): Schalter "spellcheck" gilt für neue Fenster


def use_config(config):
    global _config
    _config = config


def _utf16_slice(text, start, length):
    data = text.encode("utf-16-le")
    return data[2 * start:2 * (start + length)].decode("utf-16-le", errors="ignore")


_FUNCTYPE = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)  # COM = stdcall (nur Windows)


def _argtypes(args):
    return [type(a) if isinstance(a, ctypes._SimpleCData) else ctypes.c_void_p for a in args]


class _Com:
    """Kleine Hilfe für COM-Aufrufe über die Vtable (ohne comtypes)."""

    @staticmethod
    def call(obj, index, restype, *args):
        vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        # Jedes Argument braucht einen Typ: ctypes lässt bei stdcall (WINFUNCTYPE) keine
        # zusätzlichen, untypisierten Argumente zu („takes 1 argument (3 given)“), dann schlug
        # schon der Start der Prüfung fehl. byref(...) und Zeiger gehen als c_void_p.
        proto = _FUNCTYPE(restype, ctypes.c_void_p, *_argtypes(args))
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

    def autocorrect(self, word):
        """Feste Korrektur für word (Windows-Autokorrekturliste) oder None."""
        errors = ctypes.c_void_p()
        _Com.call(self._checker, 4, ctypes.HRESULT, ctypes.c_wchar_p(word), ctypes.byref(errors))
        try:
            error = ctypes.c_void_p()
            if _Com.call(errors, 3, ctypes.c_long, ctypes.byref(error)) != 0 or not error:
                return None
            try:
                start, length, action = ctypes.c_ulong(), ctypes.c_ulong(), ctypes.c_int()
                _Com.call(error, 3, ctypes.HRESULT, ctypes.byref(start))
                _Com.call(error, 4, ctypes.HRESULT, ctypes.byref(length))
                _Com.call(error, 5, ctypes.HRESULT, ctypes.byref(action))
                if (action.value != CORRECTIVE_ACTION_REPLACE or start.value != 0
                        or length.value != len(word.encode("utf-16-le")) // 2):
                    return None
                text = ctypes.c_void_p()
                _Com.call(error, 6, ctypes.HRESULT, ctypes.byref(text))
                try:
                    return ctypes.wstring_at(text.value) if text.value else None
                finally:
                    self._free(text)
            finally:
                _Com.release(error)
        finally:
            _Com.release(errors)

    def learn(self, word, replacement):
        """Paar in die Autokorrekturliste von Windows (bleibt gespeichert)."""
        _Com.call(self._checker, 8, ctypes.HRESULT, ctypes.c_wchar_p(word), ctypes.c_wchar_p(replacement))

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


class AutoCorrector(QObject):
    """Ersetzt beim Tippen das Wort vor Leertaste/Satzzeichen, wenn checker.autocorrect(wort)
    eine feste Korrektur liefert. Ersetzen und Zeichen sind ein Rückgängig-Schritt; Strg+Z
    direkt danach stellt das Wort wieder her und lässt es in diesem Feld künftig in Ruhe."""

    def __init__(self, edit, checker):
        super().__init__(edit)
        self.edit, self.checker = edit, checker
        self.last = None  # (Original, Korrektur, Position danach) der letzten Ersetzung
        self.keep = set()  # per Strg+Z zurückgenommen: nicht wieder ersetzen
        edit.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.edit and event.type() == QEvent.KeyPress:
            if event.matches(QKeySequence.Undo):
                if self.last and self.edit.textCursor().position() == self.last[2]:
                    self.keep.add(self.last[0])
                self.last = None
                return False
            text = event.text()
            if (len(text) == 1 and text in AUTOCORRECT_KEYS
                    and not event.modifiers() & (Qt.ControlModifier | Qt.AltModifier)):
                return self.correct(text)
            if event.key() not in _MODIFIER_KEYS:  # Strg allein (vor Strg+Z) zählt nicht
                self.last = None
        return False

    def correct(self, typed):
        """Wort vor dem Cursor ersetzen. True: Zeichen schon eingefügt (Taste verbraucht)."""
        cursor = self.edit.textCursor()
        if cursor.hasSelection():
            return False
        before = cursor.block().text()[:cursor.positionInBlock()]
        match = _WORD_BEFORE.search(before)
        if not match or match.group() in self.keep:
            return False
        word = match.group()
        try:
            new = self.checker.autocorrect(word)
        except Exception:  # Prüfung darf das Tippen nie stören
            return False
        if not new or new == word:
            return False
        length = len(word.encode("utf-16-le")) // 2
        cursor.beginEditBlock()
        cursor.setPosition(cursor.position() - length, QTextCursor.KeepAnchor)
        cursor.insertText(new)
        printable = typed not in "\r\n\t"  # Enter/Tab macht das Feld selbst (evtl. Speichern)
        if printable:
            cursor.insertText(typed)
        cursor.endEditBlock()
        self.edit.setTextCursor(cursor)
        self.last = (word, new, cursor.position())
        return printable


def attach(edit, config=None, checker=None):
    """Rechtschreibprüfung und Autokorrektur an ein QPlainTextEdit/QTextEdit hängen (nichts tun,
    wenn aus oder nicht verfügbar). Gibt den Highlighter zurück oder None."""
    config = config if config is not None else _config
    if not config.get("spellcheck", True):
        return None
    checker = checker or speller()
    if checker is None:
        return None
    highlighter = SpellHighlighter(edit.document(), checker)
    edit.setContextMenuPolicy(Qt.CustomContextMenu)
    edit.customContextMenuRequested.connect(lambda pos: _menu(edit, highlighter, pos))
    edit._spell = highlighter  # am Feld halten (sonst räumt Python ihn weg)
    if config.get("autocorrect", True) and hasattr(checker, "autocorrect"):
        edit._autocorrect = AutoCorrector(edit, checker)
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
    if suggestions and hasattr(highlighter.checker, "learn"):
        always = menu.addMenu("Immer automatisch ersetzen")

        def learn(new):
            try:
                highlighter.checker.learn(word, new)
            except Exception as e:
                print(f"Autokorrektur: Merken ging nicht: {e}")
            replace(new)

        for text in suggestions:
            always.addAction(f"„{word}“ → „{text}“").triggered.connect(
                lambda _c=False, t=text: learn(t))
        actions.append(always.menuAction())
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
