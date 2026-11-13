"""Ladeanzeige: Animation läuft nur, solange sie zu sehen ist (kein Wecken im Infobereich)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

widgets = pytest.importorskip("PySide6.QtWidgets")


def _app():
    return widgets.QApplication.instance() or widgets.QApplication([])


def _running(bar):
    return bar.spinner._timer.isActive(), bar.stripe._timer.isActive()


def test_animation_pausiert_bei_verstecktem_fenster():
    import busy_bar
    app = _app()
    window = widgets.QWidget()
    bar = busy_bar.BusyBar(window, stripe_parent=window)
    window.resize(600, 100)
    window.show()
    bar.set_items(["3CX-Anrufe"], delay=0)
    app.processEvents()
    assert _running(bar) == (True, True)

    window.hide()  # Fenster in den Infobereich
    app.processEvents()
    assert _running(bar) == (False, False)

    window.show()  # wieder geöffnet, lädt noch: läuft weiter
    app.processEvents()
    assert _running(bar) == (True, True)

    bar.set_items([])
    assert _running(bar) == (False, False)
    window.close()
