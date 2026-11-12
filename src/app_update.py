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
        self.statusBar().showMessage(f"Update {info['version']} wird geladen …")
        token = updater.settings()[1]
        folder = update_folder()

        def work():
            try:
                path = updater.download(info, token, folder,
                                        progress=lambda done, total: self._update_signals.progress.emit(
                                            done, total),
                                        cancelled=lambda: self._quitting)
                if not updater.signature_ok(path):
                    os.remove(path)
                    raise updater.UpdateError("Das Setup ist nicht von Filip Kroczak signiert. "
                                              "Update abgebrochen.")
                self._update_signals.loaded.emit(path, None)
            except (updater.UpdateError, OSError) as e:
                self._update_signals.loaded.emit(None, str(e))

        threading.Thread(target=work, daemon=True, name="Update-Download").start()

    def _update_progress(self, done, total):
        if total:
            self.statusBar().showMessage(f"Update wird geladen … {done * 100 // total} %")

    def _update_loaded(self, path, error):
        self._update_busy = False
        if error:
            self.statusBar().clearMessage()
            self.update_message = error
            safe_io.log(f"Update fehlgeschlagen: {error}")
            QMessageBox.warning(self._update_parent(), "Update", error)
            return
        if self._quitting:
            return
        minimized = not self.isVisible() or self.isMinimized()
        try:
            updater.start_setup(path, minimized=minimized)
        except OSError as e:
            safe_io.log(f"Setup nicht gestartet: {e}")
            QMessageBox.warning(self._update_parent(), "Update", f"Setup ließ sich nicht starten:\n{e}")
            return
        safe_io.log(f"Update auf {self.update_info['version']} gestartet (von {version.version_details()})")
        self.quit_app()  # das Setup wartet, bis Zeitzeuge beendet ist

