"""_close_browser läuft beim Beenden aus zwei Threads (stop() und Ende der Lese-Schleife).
Setzt der eine _proc/_tools dazwischen auf None, darf der andere nicht mit AttributeError
abbrechen (fehler.log: „Unbehandelter Fehler im Thread Leser 3CX … _close_browser“)."""
import pbx_reader
from pbx_reader import PbxReader


def test_close_browser_other_thread_clears_in_between(monkeypatch):
    killed = []
    monkeypatch.setattr(pbx_reader, "kill_profile_processes", killed.append)
    reader = PbxReader.__new__(PbxReader)
    reader.profile_dir = "profil"

    class Proc:
        terminated = False

        def poll(self):
            reader._proc = None  # der andere Thread räumt genau jetzt auf
            return None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            return 0

    class Tools:
        closed = 0

        def close(self):
            reader._tools = None  # ebenso mitten im Schließen
            Tools.closed += 1

    proc = Proc()
    reader._proc, reader._tools = proc, Tools()
    reader._close_browser()
    assert proc.terminated and killed == ["profil"] and Tools.closed == 1
    assert reader._proc is None and reader._tools is None
    reader._close_browser()  # zweiter Aufruf (anderer Thread): nichts mehr zu tun
    assert killed == ["profil"] and Tools.closed == 1
