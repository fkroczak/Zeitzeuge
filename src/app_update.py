"""Updates im Hauptfenster: im Hintergrund suchen, Hinweis zeigen, laden, still installieren.

Die Logik (GitHub, Prüfsumme, Signatur, Setup starten) steht in updater.py. Hier nur:
- Suche 2 Minuten nach dem Start und dann alle 6 Stunden (Einstellung update_check), nur in
  gebauten Versionen (main oder Testversion) mit eingebautem Update-Zugang.
- Neue Version: Hinweis „Update auf x.y.z“ mit „Jetzt aktualisieren“ (je Version einmal pro Sitzung).
- Einstellungen → Info → „Nach Updates suchen“: dasselbe von Hand, mit Rückmeldung.
- Aktualisieren: Setup im Hintergrund laden, prüfen, starten, Zeitzeuge beenden; das Setup
  installiert still und startet Zeitzeuge wieder (installer/zeitzeuge.iss, /ZZUPDATE).
"""
import os
import threading

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QMessageBox

import safe_io
import storage
import updater
import version
from theme import fit_bold


class _Signals(QObject):
    """Ergebnisse aus dem Hintergrund-Thread in den Qt-Thread bringen."""
    checked = Signal(object, object, bool)   # info, Fehlertext, von Hand
    progress = Signal(int, int)              # geladen, gesamt (Bytes)
    loaded = Signal(object, object)          # Pfad des Setups, Fehlertext
    step = Signal(str)                       # nächster Schritt (Text fürs Update-Fenster)


def _notes_text(notes, limit=8):
    """Kurzes Changelog für die Rückfrage: höchstens limit Punkte, Rest unter „Details“."""
    lines = ["Neu:"] + [f"• {n}" for n in notes[:limit]]
    if len(notes) > limit:
        lines.append(f"… und {len(notes) - limit} weitere (Details anzeigen)")
    return "\n".join(lines)


def update_folder():
    return os.path.join(storage.local_dir(), "updates")


class UpdateMixin:
    def init_updates(self):
        self.update_info = None       # neueste gefundene Version (dict aus updater.latest)
        self.update_message = ""      # letzter Stand für die Einstellungen
        self._update_busy = False
        self._update_notified = set()
        self._update_signals = _Signals(self)
        self._update_signals.checked.connect(self._update_checked)
        self._update_signals.progress.connect(self._update_progress)
        self._update_signals.loaded.connect(self._update_loaded)
        self._update_signals.step.connect(self._update_step)
        self._update_window = None
        self._update_cancel = False
        # Merker vom letzten Update jetzt lesen, gemeldet wird kurz nach dem Start
        self._finished_update = self.config.pop("update_pending", None)
        if self._finished_update:
            QTimer.singleShot(3000, self._report_finished_update)
        if not self.updates_possible():
            return
        updater.cleanup(update_folder())  # Setup vom letzten Update
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._update_tick)
        self.update_timer.start(updater.CHECK_HOURS * 3600 * 1000)
        QTimer.singleShot(2 * 60 * 1000, self._update_tick)

    def updates_possible(self):
        """Nur gebaute Versionen mit eingebautem Zugang; aus dem Quelltext oder lokal gebaut nie."""
        return version.channel() in ("main", "test") and bool(updater.settings()[1])

    def _update_tick(self):
        if self.config.get("update_check", True) and not self._quitting:
            self.check_for_update(manual=False)

    def check_for_update(self, manual=False):
        if not self.updates_possible():
            if manual:
                QMessageBox.information(self._update_parent(), "Nach Updates suchen",
                                        "Updates gibt es nur in der installierten Version von Zeitzeuge "
                                        "(nicht aus dem Quelltext oder lokal gebaut).")
            return
        if self._update_busy:
            if manual:
                self.statusBar().showMessage("Update läuft schon …", 3000)
            return
        self._update_busy = True
        if manual:
            self.statusBar().showMessage("Suche nach Updates …", 3000)
        repo, token = updater.settings()

        def work():
            try:
                info = updater.latest(repo, token)
                if updater.is_newer(info["version"], version.full_version()):
                    info["changes"] = updater.change_lines(
                        updater.changes(repo, token, version.full_version()))
                self._update_signals.checked.emit(info, None, manual)
            except updater.UpdateError as e:
                self._update_signals.checked.emit(None, str(e), manual)

        threading.Thread(target=work, daemon=True, name="Update-Suche").start()

    def check_update_now(self):
        """Einstellungen → Info → Nach Updates suchen."""
        self.check_for_update(manual=True)

    def update_state_text(self):
        return self.update_message or f"Version {version.full_version()}"

    def _update_parent(self):
        window = getattr(self, "_settings_window", None)
        return window if window is not None and window.isVisible() else self

    def _update_checked(self, info, error, manual):
        self._update_busy = False
        if error:
            self.update_message = error
            if manual:
                QMessageBox.warning(self._update_parent(), "Nach Updates suchen", error)
            return
        days = info.get("token_days")
        if days is not None and days < updater.TOKEN_WARN_DAYS:
            safe_io.log(f"Update-Zugang läuft in {days} Tagen ab: neues Lese-Token als Secret "
                        "UPDATE_READ_TOKEN hinterlegen und ein Release bauen.")
        if not updater.is_newer(info["version"], version.full_version()):
            self.update_info = None
            self.update_message = f"Aktuell (Version {version.full_version()})"
            if manual:
                QMessageBox.information(self._update_parent(), "Nach Updates suchen",
                                        f"Zeitzeuge ist aktuell (Version {version.full_version()}).")
            return
        self.update_info = info
        self.update_message = f"Version {info['version']} ist da"
        notes = info.get("changes") or []
        if manual:
            box = QMessageBox(QMessageBox.Question, "Nach Updates suchen",
                              f"Zeitzeuge {info['version']} ist da (installiert: {version.full_version()}).\n\n"
                              + (_notes_text(notes) + "\n\n" if notes else "")
                              + "Jetzt aktualisieren? Zeitzeuge beendet sich, installiert das Update und "
                              "startet neu. Deine Daten bleiben erhalten.", parent=self._update_parent())
            if len(notes) > 8:
                box.setDetailedText("\n".join(f"• {n}" for n in notes))
            yes = box.addButton("Jetzt &aktualisieren", QMessageBox.AcceptRole)
            box.addButton("&Später", QMessageBox.RejectRole)
            fit_bold(yes)
            box.setDefaultButton(yes)
            box.exec()
            if box.clickedButton() is yes:
                self.install_update()
            return
        if info["version"] in self._update_notified:
            return
        self._update_notified.add(info["version"])
        self.notify(f"Update auf {info['version']}",
                    "Zeitzeuge installiert es und startet danach neu. Neu darin:" if notes else
                    "Zeitzeuge installiert es und startet danach neu. Deine Daten bleiben erhalten.",
                    kind="info", action="Jetzt aktualisieren", on_action=self.install_update,
                    items=notes, card=bool(notes), timeout=60,
                    balloon=f"Zeitzeuge {info['version']} ist da. Einstellungen → Info → "
                                        "Nach Updates suchen.")

    def install_update(self):
        info = self.update_info
        if not info or self._update_busy:
            return
        self._update_busy = True
        self._update_cancel = False
        from update_dialog import UpdateProgress
        self._update_window = UpdateProgress(info["version"], self._update_parent())
        self._update_window.cancelled.connect(self._cancel_update)
        self._update_window.show()
        self._update_window.raise_()
        token = updater.settings()[1]
        folder = update_folder()
        signals = self._update_signals

        def work():
            try:
                path = updater.download(info, token, folder,
                                        progress=lambda done, total: signals.progress.emit(done, total),
                                        cancelled=lambda: self._quitting or self._update_cancel)
                signals.step.emit("Setup wird geprüft …")
                if not updater.signature_ok(path):
                    os.remove(path)
                    raise updater.UpdateError("Das Setup ist nicht von Filip Kroczak signiert. "
                                              "Update abgebrochen.")
                signals.loaded.emit(path, None)
            except (updater.UpdateError, OSError) as e:
                signals.loaded.emit(None, str(e))

        threading.Thread(target=work, daemon=True, name="Update-Download").start()

    def _cancel_update(self):
        self._update_cancel = True

    def _update_progress(self, done, total):
        if self._update_window is not None:
            self._update_window.set_progress(done, total)

    def _update_step(self, text):
        if self._update_window is not None:
            self._update_window.set_step(text)

    def _close_update_window(self):
        if self._update_window is not None:
            self._update_window.hide()
            self._update_window.deleteLater()
            self._update_window = None

    def _update_loaded(self, path, error):
        self._update_busy = False
        if error:
            self._close_update_window()
            if self._update_cancel:
                self.statusBar().showMessage("Update abgebrochen.", 5000)
                return
            self.update_message = error
            safe_io.log(f"Update fehlgeschlagen: {error}")
            QMessageBox.warning(self._update_parent(), "Update", error)
            return
        if self._quitting:
            return
        minimized = not self.isVisible() or self.isMinimized()
        info = self.update_info
        try:
            updater.start_setup(path, minimized=minimized)
        except OSError as e:
            self._close_update_window()
            safe_io.log(f"Setup nicht gestartet: {e}")
            QMessageBox.warning(self._update_parent(), "Update", f"Setup ließ sich nicht starten:\n{e}")
            return
        safe_io.log(f"Update auf {info['version']} gestartet (von {version.version_details()})")
        # Nach dem Neustart bestätigen (oder melden, dass es nicht geklappt hat)
        import main_timeline as mt
        self.config["update_pending"] = {"from": version.full_version(), "to": info["version"],
                                         "notes": list(info.get("changes") or [])[:20]}
        mt.save_config(self.config)
        if self._update_window is not None:
            self._update_window.set_step("Zeitzeuge wird beendet, danach wird installiert …")
            self._update_window.allow_close = True  # sonst lehnt es das Beenden ab (Qt 6)
        # Erst zeichnen lassen, dann beenden (das Beenden hält die Oberfläche kurz an)
        QTimer.singleShot(400, self.quit_app)  # das Setup wartet, bis Zeitzeuge beendet ist

    def _report_finished_update(self):
        """Erster Start nach einem Update: kurz bestätigen, was neu ist (oder dass es nicht klappte)."""
        pending, self._finished_update = self._finished_update, None
        if not pending or self._quitting:
            return
        import main_timeline as mt
        mt.save_config(self.config)  # Merker ist schon aus der Config genommen
        current = version.full_version()
        if current == pending.get("to") or updater.is_newer(current, pending.get("from", "")):
            notes = pending.get("notes") or []
            self.notify(f"Aktualisiert auf {current}",
                        "Neu darin:" if notes else "Deine Daten und Einstellungen sind unverändert.",
                        kind="info", items=notes, card=bool(notes), timeout=20,
                        balloon=f"Zeitzeuge wurde auf {current} aktualisiert.")
        else:
            safe_io.log(f"Update auf {pending.get('to')} nicht installiert (läuft weiter {current})")
            self.notify("Update nicht installiert",
                        f"Zeitzeuge läuft weiter mit {current}. Bitte noch einmal über "
                        "Einstellungen → Info → Nach Updates suchen versuchen.",
                        kind="warn", timeout=30)

