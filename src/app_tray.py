"""Hauptfenster: Aufzeichnung der aktiven Fenster, Infobereich und Beenden.

Teil von TimelineApp (main_timeline.py), nur über main_timeline laden.
"""
from datetime import datetime

from PySide6.QtCore import QDate, QEvent, QObject, QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QMenu, QSystemTrayIcon,
                               QWidget, QWidgetAction)

from activity_tracker import ActivityTracker, tracking_filters
import icons
from settings_dialogs import RulesDialog, TrackingFilterDialog
from prompt_card import animations_enabled
from theme import SPACE_S, theme_for
import main_timeline as mt  # Pfade und save_config zur Laufzeit von dort (Tests ersetzen sie dort)


def tray_menu_pos(icon, size, avail):
    """Feste Stelle für das Menü im Infobereich: mittig über dem Symbol, direkt an der
    Taskleiste (unten, oben, links oder rechts), ganz auf dem Bildschirm. None = Qt entscheidet."""
    if not icon.isValid() or icon.isEmpty():
        return None
    w, h = size.width(), size.height()
    if icon.top() > avail.bottom():  # Taskleiste unten
        x, y = icon.center().x() - w // 2, avail.bottom() - h + 1
    elif icon.bottom() < avail.top():  # oben
        x, y = icon.center().x() - w // 2, avail.top()
    elif icon.left() > avail.right():  # rechts
        x, y = avail.right() - w + 1, icon.center().y() - h // 2
    elif icon.right() < avail.left():  # links
        x, y = avail.left(), icon.center().y() - h // 2
    else:  # Symbol im aufgeklappten Überlauf: direkt darüber
        x, y = icon.center().x() - w // 2, icon.top() - h
    x = max(avail.left(), min(x, avail.right() - w + 1))
    y = max(avail.top(), min(y, avail.bottom() - h + 1))
    return QPoint(x, y)



class _RecDot(QWidget):
    """Roter Punkt „nimmt auf“, blinkt solange das Menü offen ist."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(10, 10)
        self.color = QColor("#DC2626")
        self.on = True

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = QColor(self.color)
        color.setAlphaF(1.0 if self.on else 0.25)
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(1, 1, 8, 8)


class RecordingRow(QWidgetAction):
    """Eintrag Aufzeichnung im Infobereich: links Icon und Text der Aktion (pausieren/fortsetzen),
    rechts der Zustand – blinkender roter Punkt „läuft“ oder grau „pausiert“."""

    def __init__(self, menu, toggle):
        super().__init__(menu)
        self._toggle = toggle
        self.row = QWidget()
        self.row.setObjectName("tray_record")
        self.row.setAttribute(Qt.WA_StyledBackground)
        self.row.setAttribute(Qt.WA_Hover)
        self.row.setFocusPolicy(Qt.StrongFocus)
        self.row.setCursor(Qt.PointingHandCursor)
        box = QHBoxLayout(self.row)
        box.setContentsMargins(1, 6, 12, 6)  # Icon und Text genau unter denen der anderen Einträge
        box.setSpacing(SPACE_S + 2)
        self._text_gap = 5
        self.icon = QLabel()
        self.icon.setFixedSize(16, 16)
        self.label = QLabel()
        self.label.setObjectName("tray_record_text")
        self.dot = _RecDot()
        self.pause = QLabel()
        self.state = QLabel()
        self.state.setObjectName("tray_record_state")
        box.addWidget(self.icon)
        box.addSpacing(self._text_gap)
        box.addWidget(self.label)
        box.addStretch(1)
        box.addSpacing(16)
        for w in (self.dot, self.pause, self.state):
            box.addWidget(w)
        self.setDefaultWidget(self.row)
        self.setText("Aufzeichnung")
        self.row.installEventFilter(self)
        self._blink = QTimer(self)
        self._blink.setInterval(600)
        self._blink.timeout.connect(self._step)
        menu.aboutToShow.connect(self._start)
        menu.aboutToHide.connect(self._blink.stop)
        self.recording = True

    def set_state(self, recording, theme):
        self.recording = recording
        icon = "pause" if recording else "record"  # Icon zeigt, was ein Klick tut
        self.icon.setPixmap(icons.icon(icon, theme["text"]).pixmap(16, 16))
        self.label.setText("Aufzeichnung pausieren" if recording else "Aufzeichnung fortsetzen")
        self.setText(self.label.text())
        self.row.setAccessibleName(("Aufzeichnung läuft. Klicken zum Pausieren" if recording
                                    else "Aufzeichnung pausiert. Klicken zum Fortsetzen"))
        self.dot.color = QColor(theme["now"])
        self.dot.on = True
        self.dot.setVisible(recording)
        self.pause.setPixmap(icons.icon("pause", theme["muted"]).pixmap(11, 11))
        self.pause.setVisible(not recording)
        self.state.setText("läuft" if recording else "pausiert")
        self.dot.update()

    def _start(self):
        self.dot.on = True
        self.dot.update()
        if self.recording and animations_enabled():
            self._blink.start()

    def _step(self):
        self.dot.on = not self.dot.on
        self.dot.update()

    def _activate(self):
        menu = self.parent()
        if isinstance(menu, QMenu):
            menu.close()
        self._toggle()

    def eventFilter(self, obj, event):
        if obj is self.row:
            if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                self._activate()
                return True
            if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
                self._activate()
                return True
        return super().eventFilter(obj, event)

class _TrayMenuPlacer(QObject):
    """Rückt das Menü des Infobereichs beim Öffnen an seine feste Stelle. Windows öffnet es
    sonst dort, wo die Maus gerade steht, also jedes Mal etwas anders."""

    def __init__(self, tray, menu):
        super().__init__(menu)
        self.tray = tray
        menu.installEventFilter(self)

    def eventFilter(self, menu, event):
        if event.type() == QEvent.Show:
            icon = self.tray.geometry()
            screen = QGuiApplication.screenAt(icon.center()) or QGuiApplication.primaryScreen()
            if screen is not None:
                pos = tray_menu_pos(icon, menu.sizeHint(), screen.availableGeometry())
                if pos is not None:
                    menu.move(pos)
        return False


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
            if (self.current_date == QDate.currentDate() and self.isVisible() and not self.isMinimized()
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
        dialog = RulesDialog(self.config, self, sample=self.rule_sample)
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
            self.tray_record.set_state(on, theme_for(self.config))

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
        # Aufzeichnung: ein Eintrag, der sich umstellt; rechts der Zustand (roter Punkt = läuft)
        self.tray_record = RecordingRow(menu, self.tracking_action.toggle)
        menu.addAction(self.tray_record)
        refresh = menu.addAction("&Aktualisieren", self.refresh)
        refresh.setToolTip("Logs neu einlesen")
        menu.addSeparator()
        self.tray_prompts_action = menu.addAction("Offene &Nachfragen", self.show_open_prompts)
        notify = menu.addAction("&Benachrichtigungen …", lambda: self.show_settings("prompts"))
        settings = menu.addAction("&Einstellungen …", self.show_settings)
        menu.addSeparator()
        quit_action = menu.addAction("&Beenden", self.request_quit)
        self._icon_actions += [(open_action, "window"), (refresh, "refresh"), (self.tray_prompts_action, "doc"),
                               (notify, "bell"), (settings, "settings"), (quit_action, "power")]
        self.update_open_prompts_action()
        self.tray.setContextMenu(menu)
        self._tray_menu_placer = _TrayMenuPlacer(self.tray, menu)  # immer an derselben Stelle
        # Klick auf die Meldung "3CX-Anmeldung nötig" öffnet die Anmeldung
        self.tray.messageClicked.connect(self.on_tray_message_clicked)
        self.tray.activated.connect(
            lambda reason: self.show_from_tray()
            if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None
        )
        self.tray.show()

    # ---------------------- Hinweise (notices.py) -------------------------------

    def notify(self, title, text, kind="warn", action="", on_action=None, items=(), card=False,
               timeout=15, balloon=None, flag=None):
        """Hinweis als Karte (card=True) oder Leiste im Stil der Nachfrage, in derselben Ecke und
        über einer offenen Nachfrage. on_action: was die Aktion tut.
        Mit „Als Windows-Benachrichtigung“ (config notify_windows) wie bisher eine Sprechblase:
        balloon = Text dafür, flag = Merker für den Klick darauf (on_tray_message_clicked)."""
        if self.config.get("notify_windows") or not self.tray:
            if not self.tray:
                return None
            if flag:
                setattr(self, flag, True)
            icon = QSystemTrayIcon.Information if kind == "info" else QSystemTrayIcon.Warning
            self.tray.showMessage(title, balloon if balloon is not None else text, icon, timeout * 1000)
            return None
        from notices import NoticeCard, NoticeStrip
        from prompt_card import prompt_position
        for old in list(getattr(self, "_notices", [])):  # gleicher Hinweis nicht doppelt
            if old.windowTitle() == f"Zeitzeuge: {title}":
                old._finish(old.closed)
        if card:
            notice = NoticeCard(title, text, items, action, kind, timeout, self)
        else:
            notice = NoticeStrip(title, text, action, kind, timeout, self)
        if on_action is not None:
            notice.acted.connect(on_action)
        self._notices = [n for n in getattr(self, "_notices", []) if n.isVisible()] + [notice]
        notice.destroyed.connect(lambda _o=None, n=notice: self._notices.remove(n)
                                 if n in getattr(self, "_notices", []) else None)
        notice.position = prompt_position(self.config)
        notice.adjustSize()
        notice.dock_bottom_right(self._notice_margin(notice))
        notice.show()
        return notice

    def _notice_margin(self, notice):
        """Abstand zum Bildschirmrand: über (bzw. unter) einer offenen Nachfrage und älteren Hinweisen."""
        margin = 8
        prompt = getattr(self, "_prompt_window", None)
        others = [prompt] if prompt is not None and prompt.isVisible() else []
        others += [n for n in getattr(self, "_notices", []) if n is not notice and n.isVisible()]
        for other in others:
            margin += other.frameGeometry().height()
        return margin

    def on_tray_message_clicked(self):
        """Klick auf "Anmeldung nötig" öffnet die passende Anmeldung."""
        if getattr(self, "_tray_close_hint", False):  # Feierabend: Tagesabschluss bereit
            self._tray_close_hint = False
            self.show_from_tray()
            self.show_day_close(datetime.now().strftime("%Y-%m-%d"))
        elif getattr(self, "_tray_doc_hint", False):  # Meldung zu offenen Tätigkeiten
            self._tray_doc_hint = False
            self.show_open_docs()
        elif getattr(self, "_tray_week_hint", False):  # Prüfung bei Feierabend: Wochenabschluss
            self._tray_week_hint = False
            self.show_from_tray()
            self.show_week()
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
            self._prompt_window._done = True
            self._prompt_window.close()
        for notice in list(getattr(self, "_notices", [])):  # offene Hinweise mit beenden
            notice.blockSignals(True)
            notice.close()
        self.timeline.shutdown()
        if self.tracker:
            self.tracker.stop()
        for reader in self.all_readers():
            if reader:
                reader.stop()
        self.close_store()
        QApplication.instance().quit()

    def showEvent(self, event):
        """Aus dem Infobereich (oder anders) wieder gezeigt: ausgefallenes Zeichnen nachholen."""
        super().showEvent(event)
        if self.timeline.draw_stale and not self.isMinimized():
            self.timeline.draw_timeline(self.current_date)

    def changeEvent(self, event):
        """Aus der Taskleiste wiederhergestellt: Zeichnen nachholen, das im Hintergrund ausfiel."""
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange and not self.isMinimized() \
                and self.timeline.draw_stale:
            self.timeline.draw_timeline(self.current_date)

    def closeEvent(self, event):
        if self.tray and self.config.get("close_to_tray", True) and not self._quitting:
            event.ignore()
            self.hide()
            if self.config.get("tray_hint_on_close", True) and not getattr(self, "_tray_hint_shown", False):
                self._tray_hint_shown = True
                self.notify("Zeitzeuge läuft weiter",
                            "Zeichnet im Hintergrund auf. Beenden über das Symbol im Infobereich.",
                            kind="info", timeout=6,
                            balloon="Zeitzeuge zeichnet im Hintergrund weiter auf. "
                                    "Beenden über das Symbol im Infobereich.")
            return
        self.quit_app()
        super().closeEvent(event)
