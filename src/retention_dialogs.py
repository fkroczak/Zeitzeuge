"""PC-Verlauf automatisch löschen: Einstellung und Ausführung im Hauptfenster.

Logik in retention.py. Die Ausführung läuft in kleinen Schritten über QTimer im
Hauptthread (die Datenbank hat eine Verbindung mit Lock), so hängt das Fenster nie merklich.
"""
import threading
from datetime import date

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                               QMessageBox, QSpinBox, QVBoxLayout)

from theme import prose
import datastore
import retention
import safe_io

START_DELAY_MS = 60 * 1000       # beim Start erst nach einer Minute (Start bleibt schnell)
CHECK_EVERY_MS = 60 * 60 * 1000  # jede Stunde prüfen, ob heute schon gelöscht wurde


class RetentionDialog(QDialog):
    """Einstellung: PC-Verlauf nach N Tagen automatisch löschen (Standard aus)."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PC-Verlauf automatisch löschen")
        self.setMinimumWidth(480)
        on, days = retention.settings(config)
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.enabled = QCheckBox("PC-Verlauf &automatisch löschen nach")
        self.enabled.setChecked(on)
        self.days = QSpinBox()
        self.days.setRange(retention.MIN_DAYS, retention.MAX_DAYS)
        self.days.setSuffix(" Tagen")
        self.days.setValue(days)
        self.days.setAccessibleName("Aufbewahrung des PC-Verlaufs in Tagen")
        self.days.setEnabled(on)
        self.enabled.toggled.connect(self.days.setEnabled)
        row.addWidget(self.enabled)
        row.addWidget(self.days)
        row.addStretch(1)
        layout.addLayout(row)
        hint = QLabel("Gelöscht werden nur die aufgezeichneten aktiven Fenster (auch von einem "
                      "anderen PC übernommene). Deine Tätigkeiten, Buchungen, KI-Vorschläge, "
                      "Anrufe und Verbindungen bleiben erhalten. Zeitzeuge löscht beim Start "
                      "und einmal am Tag.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        prose(hint)
        layout.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self):
        return self.enabled.isChecked(), self.days.value()


class RetentionRunner(QObject):
    """Löscht alten PC-Verlauf beim Start (verzögert) und einmal am Tag, wenn eingeschaltet."""

    def __init__(self, window, activity_dir, save_config):
        super().__init__(window)
        self.window = window
        self.activity_dir = activity_dir
        self.save_config = save_config
        self.last_day = None   # Tag des letzten vollständigen Laufs
        self._running = None   # (Speicher, Name, Stichtag, bisher gelöscht) während eines Laufs
        self._traces_done = None  # (Tag, Tage) des letzten Kürzens des Spuren-Verlaufs
        self._compacted = None     # Tag des letzten Verdichtens (compact)
        self._compact_thread = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check)
        QTimer.singleShot(START_DELAY_MS, self.check)
        self.timer.start(CHECK_EVERY_MS)

    def _target(self):
        """(Speicher, Ablagename) des Fensterverlaufs oder (None, Name), wenn nicht erreichbar."""
        try:
            return datastore.locate(self.activity_dir, "row_files")
        except (datastore.Busy, datastore.Locked, OSError) as e:
            safe_io.log(f"PC-Verlauf löschen: Datenbank gerade nicht erreichbar ({e})")
            return None, retention.ACTIVITY

    def prune_traces(self):
        """Spuren-Verlauf (Spuren vom PC, Remotedesktop, VPN) auf trace_history_days Tage kürzen:
        einmal am Tag und nach einer Änderung der Tage (spätestens nach einer Stunde)."""
        days = retention.trace_days(self.window.config)
        if self._traces_done == (date.today(), days):
            return
        self._traces_done = (date.today(), days)
        before = retention.cutoff(days)
        timeline = getattr(self.window, "timeline", None)
        removed = 0
        for name in ("local_reader", "rdp_reader", "vpn_reader"):
            reader = getattr(timeline, name, None)
            if reader is None:
                continue
            try:
                removed += reader.prune(before)
            except Exception as e:  # Aufräumen darf die App nie stören
                safe_io.log(f"Spuren-Verlauf kürzen ({name}): {e}")
        if removed:
            safe_io.log(f"Spuren-Verlauf vor dem {before} gekürzt: {removed} Einträge")
            timeline._local_index = timeline._rdp_index = timeline._sophos_index = None
            timeline._remote_cache.clear()

    def compact(self):
        """Fensterverlauf vergangener Tage verdichten (einmal am Tag, im Hintergrund)."""
        today = date.today()
        if self._compacted == today or (self._compact_thread and self._compact_thread.is_alive()):
            return
        self._compacted = today

        def run():
            try:
                import activity_tracker
                timeline = getattr(self.window, "timeline", None)
                activity_tracker.compact_days(self.activity_dir,
                                              stop=lambda: bool(getattr(timeline, "_closing", False)))
            except (datastore.Busy, datastore.Locked, OSError) as e:
                safe_io.log(f"PC-Verlauf verdichten: {e}")
                self._compacted = None  # in einer Stunde erneut
        self._compact_thread = threading.Thread(target=run, daemon=True, name="PC-Verlauf verdichten")
        self._compact_thread.start()

    def check(self, force=False):
        self.prune_traces()
        self.compact()
        on, days = retention.settings(self.window.config)
        today = date.today()
        if not on or self._running or (self.last_day == today and not force):
            return
        store, name = self._target()
        if store is None:
            return
        before = retention.cutoff(days, today)
        imported = getattr(self.window, "imported", None)
        try:
            dropped = imported.drop_pc_before(before) if imported else 0
        except OSError as e:
            safe_io.report(f"PC-Verlauf löschen: {e}")
            dropped = 0
        self._running = (store, name, before, 0, dropped)
        QTimer.singleShot(0, self._step)

    def _step(self):
        store, name, before, total, dropped = self._running
        try:
            deleted, done = retention.purge_step(store, name, before)
        except (datastore.Busy, datastore.Locked) as e:
            safe_io.report(f"PC-Verlauf löschen: {e}. Nächster Versuch in einer Stunde.")
            self._running = None
            return
        total += deleted
        if not done:
            self._running = (store, name, before, total, dropped)
            QTimer.singleShot(50, self._step)  # Fenster zwischendurch bedienen
            return
        self._running = None
        self.last_day = date.today()
        if total or dropped:
            day = f"{before[8:10]}.{before[5:7]}.{before[:4]}"
            safe_io.log(f"PC-Verlauf vor dem {day} gelöscht: {total} Fensterabschnitte"
                        + (f", übernommener Verlauf an {dropped} Tagen" if dropped else ""))
            try:
                self.window.statusBar().showMessage(f"PC-Verlauf vor dem {day} gelöscht", 6000)
                if self.window.current_date.toString("yyyy-MM-dd") < before:
                    self.window.timeline.draw_timeline(self.window.current_date)
            except (AttributeError, RuntimeError):
                pass

    def edit(self):
        """Dialog zeigen. Beim Einschalten (oder kürzerer Frist) erst bestätigen lassen."""
        config = self.window.config
        was_on, was_days = retention.settings(config)
        dialog = RetentionDialog(config, self.window)
        if dialog.exec() != QDialog.Accepted:
            return
        on, days = dialog.values()
        if on and (not was_on or days < was_days):
            store, name = self._target()
            before = retention.cutoff(days)
            info = retention.affected(store, name, getattr(self.window, "imported", None), before)
            if info["days"] and QMessageBox.question(
                    self.window, "PC-Verlauf löschen",
                    f"Jetzt werden {retention.summary(info, before)} gelöscht.\n\n"
                    "Deine Tätigkeiten, Buchungen, KI-Vorschläge, Anrufe und Verbindungen "
                    "bleiben erhalten. Das Löschen lässt sich nicht rückgängig machen.\n\n"
                    "Fortfahren?") != QMessageBox.Yes:
                return
        config["pc_history_purge"], config["pc_history_days"] = on, days
        self.save_config(config)
        if on:
            self.check(force=True)
