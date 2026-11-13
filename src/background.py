"""Langsames außerhalb des Fensters erledigen, Ergebnis zurück im Qt-Hauptthread.

Laut haenger.log stand das Fenster vor allem bei Prozesslisten (psutil, alle 30 Sekunden,
nach einem Update bis zu 20 s) und beim Start des Setups still. run(func, on_done) ruft func()
in einem eigenen Thread und danach on_done(ok, wert) im Hauptthread: wert ist das Ergebnis
oder bei ok=False die Ausnahme.
"""
import threading

from PySide6.QtCore import QObject, Qt, Signal


class _Relay(QObject):
    done = Signal(object)


_alive = set()  # Relais leben, bis ihr Ergebnis angekommen ist


def run(func, on_done, name="Hintergrund"):
    """Im Hauptthread aufrufen (dort lebt das Relais, dort kommt on_done an)."""
    relay = _Relay()
    _alive.add(relay)

    def deliver(result):
        _alive.discard(relay)
        relay.deleteLater()
        on_done(*result)
    relay.done.connect(deliver, Qt.QueuedConnection)

    def work():
        try:
            result = (True, func())
        except Exception as e:  # Hintergrund darf nie das Programm beenden
            result = (False, e)
        relay.done.emit(result)
    threading.Thread(target=work, daemon=True, name=name).start()
