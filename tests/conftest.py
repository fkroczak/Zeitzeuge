"""Gemeinsame Einstellungen für pytest.

Zwei Arten von Tests:
- Reine Logik-Tests (Regeln, Zusammenfassen, Parser, VPN, Fenster-Filter, 3CX direkt, Ablage)
  sind normale pytest-Funktionen und laufen im pytest-Prozess.
- Tests mit Oberfläche, Browser oder Prozessen (Start, Infobereich, Bedienbarkeit, Robustheit,
  KI, Tempo, ITM, 3CX, Mitschnitt …) sind Skripte ohne test_-Funktionen. Jedes Skript läuft
  als ein pytest-Test in einem eigenen Python-Prozess: eine QApplication pro Prozess, eigener
  Datenordner, eigene Umgebungsvariablen, und os._exit am Ende stört pytest nicht
  (Qt räumt beim Interpreter-Ende unter Windows sporadisch falsch auf, siehe docs/).
  Endet das Skript nicht mit Code 0, schlägt der Test fehl und zeigt die ganze Ausgabe
  (auch die ::error-Zeilen für GitHub).
"""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")
sys.path.insert(0, ROOT)

# Ohne Bildschirm testen, auch lokal ohne export
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Nie den echten Datenordner anfassen (Skripte setzen bei Bedarf ihren eigenen)
os.environ.setdefault("ZEITZEUGE_DATA", tempfile.mkdtemp(prefix="zeitzeuge-test-"))

SCRIPT_TIMEOUT = 300  # Sekunden je Skript
BROWSER_SCRIPTS = {"itm_test.py", "pbx_test.py", "recorder_test.py", "m42_test.py"}  # brauchen Edge/Chrome
HAS_TEST_FUNC = re.compile(r"^(async\s+)?def test_|^class Test", re.M)


def is_script(path):
    """Ein *_test.py ohne test_-Funktionen ist ein eigenständiges Skript."""
    path = Path(path)
    if not path.name.endswith("_test.py") or not os.path.samefile(path.parent, TESTS):
        return False
    with open(path, encoding="utf-8") as f:
        return not HAS_TEST_FUNC.search(f.read())


@pytest.hookimpl(tryfirst=True)
def pytest_pycollect_makemodule(module_path, parent):
    # Skripte nicht importieren (sie laufen beim Import los), sondern im Unterprozess starten
    if is_script(module_path):
        return ScriptFile.from_parent(parent, path=module_path)
    return None


class ScriptFile(pytest.File):
    def collect(self):
        item = ScriptItem.from_parent(self, name="skript")
        item.add_marker(pytest.mark.skript)
        if self.path.name in BROWSER_SCRIPTS:
            item.add_marker(pytest.mark.browser)
        yield item


class ScriptFailed(Exception):
    pass


class ScriptItem(pytest.Item):
    def setup(self):
        if self.get_closest_marker("browser"):
            from pbx_reader import find_browser  # gleiche Suche wie die App
            if not find_browser():
                if os.environ.get("CI"):
                    pytest.fail("Kein Edge/Chrome gefunden (pbx_reader.find_browser), "
                                "auf CI muss der Browser-Test laufen", pytrace=False)
                pytest.skip("Kein Edge/Chrome gefunden (ZEITZEUGE_BROWSER setzen)")

    def runtest(self):
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        # Ausgabe in eine Datei statt in eine Pipe: Browser-Kindprozesse halten sonst
        # die Pipe offen und das Warten hängt nach einem Timeout.
        with tempfile.TemporaryFile() as out:
            proc = subprocess.Popen([sys.executable, str(self.path)], cwd=ROOT, env=env,
                                    stdout=out, stderr=subprocess.STDOUT)
            try:
                code = proc.wait(timeout=SCRIPT_TIMEOUT)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                code = f"Zeitüberschreitung nach {SCRIPT_TIMEOUT} s"
            out.seek(0)
            text = out.read().decode("utf-8", errors="replace")
        if code != 0:
            raise ScriptFailed(f"{self.path.name}: Ende mit {code}", text)
        sys.stdout.write(text)  # mit -s oder -rA sichtbar

    def repr_failure(self, excinfo):
        if isinstance(excinfo.value, ScriptFailed):
            head, text = excinfo.value.args
            # Zeilen unverändert ausgeben, damit GitHub ::error-Zeilen als Annotation zeigt
            return f"{head}\n----- Ausgabe -----\n{text.rstrip()}\n----- Ende der Ausgabe -----"
        return super().repr_failure(excinfo)

    def reportinfo(self):
        return self.path, None, f"{self.path.name} (Skript)"


class Checker:
    """Weiche Prüfung wie in den alten Skripten: alle Prüfungen laufen, Fehler am Ende gesammelt."""

    def __init__(self):
        self.failures = []

    def __call__(self, cond, text):
        if not cond:
            self.failures.append(text)
            print("FEHLER:", text)
        return cond


@pytest.fixture
def check():
    return Checker()


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    result = yield
    checker = getattr(item, "funcargs", {}).get("check")
    if isinstance(checker, Checker) and checker.failures:
        pytest.fail(f"{len(checker.failures)} Fehler:\n" + "\n".join(checker.failures), pytrace=False)
    return result


def pytest_runtest_logreport(report):
    """Auf GitHub jeden Fehlschlag als Annotation melden (Skripte schreiben eigene ::error-Zeilen dazu)."""
    if not report.failed or not os.environ.get("GITHUB_ACTIONS"):
        return
    crash = getattr(report.longrepr, "reprcrash", None)
    text = crash.message if crash else str(report.longrepr).splitlines()[0]
    text = text[:2000].replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    # Direkt auf die Konsole, an pytests Ausgabe-Umleitung vorbei
    line = f"\n::error title=Test {report.nodeid} ({report.when})::{text}\n"
    out = sys.__stdout__
    out.write(line.encode(out.encoding or "utf-8", errors="replace").decode(out.encoding or "utf-8"))
    out.flush()
