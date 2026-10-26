"""Hauptfenster: Aufzeichnung der aktiven Fenster, Infobereich und Beenden.

Teil von TimelineApp (main_timeline.py), nur über main_timeline laden.
"""
from datetime import datetime

from PySide6.QtCore import QDate
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QDialog, QMenu, QSystemTrayIcon

from activity_tracker import ActivityTracker, tracking_filters
import icons
from settings_dialogs import RulesDialog, TrackingFilterDialog
from theme import THEMES
import main_timeline as mt  # Pfade und save_config zur Laufzeit von dort (Tests ersetzen sie dort)


class TrayMixin:
    # ---------------------- Aktivitätsprotokoll -------------------------------

    def set_tracking(self, enabled):
        if enabled and not self.tracker:
            self.tracker = ActivityTracker(
                mt.ACTIVITY_DIR,
                idle_limit=self.config.get("tracking_idle_minutes", 5) * 60,
                **tracking_filters(self.config),
            )
            self.track_timer.start(5000)
        elif not enabled and self.tracker:
            self.track_timer.stop()
            self.tracker.stop()
            self.tracker = None
        self.timeline.tracker = self.tracker

    def track_sample(self):
        if self.tracker and self.tracker.sample():
            # Ansicht höchstens alle 30 s neu zeichnen, und nur, wenn heute angezeigt wird
            now = datetime.now()
            last = getattr(self, "_last_track_draw", None)
            if (self.current_date == QDate.currentDate() and self.isVisible()
                    and (last is None or (now - last).total_seconds() > 30)):
                self._last_track_draw = now
                self.timeline.draw_timeline(self.current_date)

    def edit_tracking_filters(self):
        dialog = TrackingFilterDialog(self.config, mt.ACTIVITY_DIR, self)
        if dialog.exec() == QDialog.Accepted:
            dialog.apply()
            mt.save_config(self.config)
            if self.tracker:  # neue Regeln gelten sofort
                self.tracker.set_filters(**tracking_filters(self.config))
            self.timeline.draw_timeline(self.current_date)

    def edit_rules(self):
        dialog = RulesDialog(self.config, self)
        if dialog.exec() == QDialog.Accepted:
            dialog.apply()
            mt.save_config(self.config)
            self.timeline.draw_timeline(self.current_date)

    def toggle_tracking(self, enabled):
        self.config["tracking_enabled"] = enabled
        mt.save_config(self.config)
        self.set_tracking(enabled)
        self.update_tracking_state()
        self.timeline.draw_timeline(self.current_date)

    def update_tracking_state(self):
        """Zustand der Aufzeichnung überall gleich zeigen: Statuszeile, Infobereich, Menüs."""
        on = self.tracker is not None
        text = "Aufzeichnung aktiv" if on else "Aufzeichnung pausiert"
        self.tracking_button.setText(text)
        self.tracking_button.setIcon(icons.state_dot(on))
        self.tracking_button.setToolTip(
            "Aktive Fenster werden aufgezeichnet. Klicken zum Pausieren." if on
            else "Die Aufzeichnung der aktiven Fenster ist pausiert. Klicken zum Fortsetzen.")
        if self.tray:
            self.tray.setIcon(icons.tray_icon(self.logo_svg, on) if self.logo_svg
                              else self.windowIcon())
            self.tray.setToolTip(f"Zeitzeuge – {text}")
            self.tray_state_action.setText(text)
            self.tray_state_action.setIcon(icons.state_dot(on))
            self.tray_toggle_action.setText("Aufzeichnung &pausieren" if on
                                            else "Aufzeichnung &fortsetzen")
            color = THEMES["dark" if self.dark_mode else "light"]["text"]
            self.tray_toggle_action.setIcon(icons.icon("pause" if on else "record", color))

    def toggle_pc_list(self, enabled):
        self.config["show_pc_in_list"] = enabled
        mt.save_config(self.config)
        self.update_pc_list_tip()
        self.update_day_list(self.day_activities, self.pc_activities)

    # ---------------------- Infobereich (Tray) --------------------------------

    def _build_tray(self):
        self.tray = None
        try:
            with open(mt.resource_path("zeitzeuge.svg"), encoding="utf-8") as f:
                self.logo_svg = f.read()
        except OSError:  # ältere Builds ohne SVG: einfach das Logo aus der .ico
            self.logo_svg = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        # Schnellzugriffe; Aufzeichnung, Datenquellen und Datenordner sind dieselben
        # Aktionen wie im Hauptfenster, ihr Zustand ist also überall gleich.
        menu = QMenu(self)
        open_action = menu.addAction("&Zeitzeuge öffnen", self.show_from_tray)
        bold = QFont(open_action.font())
        bold.setBold(True)
        open_action.setFont(bold)
        menu.setDefaultAction(open_action)
        menu.addSeparator()
        # Zustand als eigene Zeile, darunter der passende Befehl (Text wechselt mit dem Zustand)
        self.tray_state_action = menu.addAction("")
        self.tray_state_action.setEnabled(False)
        self.tray_toggle_action = menu.addAction("", self.tracking_action.toggle)
        refresh = menu.addAction("Logs &neu einlesen", self.refresh)
        menu.addSeparator()
        menu.addMenu(self.sources_menu)
        menu.addAction(self.open_folder_action)
        menu.addSeparator()
        quit_action = menu.addAction("&Beenden", self.request_quit)
        self._icon_actions += [(open_action, "window"), (refresh, "refresh"), (quit_action, "power")]
        self.tray.setContextMenu(menu)
        # Klick auf die Meldung "3CX-Anmeldung nötig" öffnet die Anmeldung
        self.tray.messageClicked.connect(self.on_tray_message_clicked)
        self.tray.activated.connect(
            lambda reason: self.show_from_tray()
            if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None
        )
        self.tray.show()

    def on_tray_message_clicked(self):
        """Klick auf "Anmeldung nötig" öffnet die passende Anmeldung."""
        if getattr(self, "_tray_doc_hint", False):  # Meldung zu offenen Tätigkeiten
            self._tray_doc_hint = False
            if self._prompt_queue and self.config.get("prompt_mode") == "tray":
                self.show_next_prompt(force=True)
            else:
                self.show_open_docs()
        elif self.pbx_reader and self.pbx_reader.needs_login:
            self.show_pbx_login()
        elif self.itm_reader and self.itm_reader.needs_login:
            self.itm_reader.show_login(self)
        elif self.m42_reader and self.m42_reader.needs_login:
            self.m42_reader.show_login(self)

    def show_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.timeline.draw_timeline(self.current_date)

    def quit_app(self):
        self._quitting = True
        if self._prompt_window:
            self._prompt_window.blockSignals(True)
            self._prompt_window.close()
        self.timeline.shutdown()
        if self.tracker:
            self.tracker.stop()
        for reader in self.all_readers():
            if reader:
                reader.stop()
        self.close_store()
        QApplication.instance().quit()

    def closeEvent(self, event):
        if self.tray and self.config.get("close_to_tray", True) and not self._quitting:
            event.ignore()
            self.hide()
            if not getattr(self, "_tray_hint_shown", False):
                self._tray_hint_shown = True
                self.tray.showMessage(
                    "Zeitzeuge läuft weiter",
                    "Zeitzeuge zeichnet im Hintergrund weiter auf. "
                    "Beenden über das Symbol im Infobereich.",
                    QSystemTrayIcon.Information, 4000,
                )
            return
        self.quit_app()
        super().closeEvent(event)
