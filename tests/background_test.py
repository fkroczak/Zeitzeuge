"""Langsames außerhalb des Fensters (haenger.log): background.run und seltenere Dateiprüfung."""
import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

widgets = pytest.importorskip("PySide6.QtWidgets")


def _app():
    return widgets.QApplication.instance() or widgets.QApplication([])


def _wait(done, ms=2000):
    from PySide6.QtTest import QTest
    for _ in range(ms // 10):
        if done():
            return True
        QTest.qWait(10)
    return done()


def test_ergebnis_kommt_im_hauptthread_an():
    import background
    _app()
    got = []
    main = threading.get_ident()
    background.run(lambda: threading.get_ident(), lambda ok, value: got.append((ok, value, threading.get_ident())))
    assert _wait(lambda: got)
    ok, worker, receiver = got[0]
    assert ok and worker != main and receiver == main


def test_fehler_kommt_als_ausnahme_an():
    import background
    _app()
    got = []

    def boom():
        raise OSError("Zugriff verweigert")
    background.run(boom, lambda ok, value: got.append((ok, value)))
    assert _wait(lambda: got)
    assert got[0][0] is False and isinstance(got[0][1], OSError)


def test_fehlende_alte_datei_nur_selten_suchen(tmp_path, monkeypatch):
    """migrate_if_present: os.path.exists hing im OneDrive-Ordner sekundenlang. Fehlt die alte
    Datei, wird höchstens alle ABSENT_SECONDS erneut nachgesehen."""
    import datastore
    store = datastore.Store.__new__(datastore.Store)
    store._absent_until, store._retry_at = {}, {}
    calls = []
    real = os.path.exists
    path = str(tmp_path / "anrufe.json")
    monkeypatch.setattr(datastore.os.path, "exists", lambda p: (p == path and calls.append(p)) or real(p))
    for _ in range(5):
        store.migrate_if_present("anrufe", path, "list")
    assert calls == [path]
    store._absent_until[path] = 0  # Minute vorbei
    store.migrate_if_present("anrufe", path, "list")
    assert len(calls) == 2
