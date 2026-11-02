"""
Gebuchte Zeiten aus Matrix42 (Service Desk → Kalender) lesen und abgleichen.

Matrix42 ist nur aus dem Firmennetz erreichbar. Wie beim 3CX- und ITM-Auslesen läuft
Edge unsichtbar mit eigenem Profil (Ordner m42_profil). Zeitzeuge öffnet die
Kalenderseite, schaltet auf die Wochenansicht und liest die Einträge direkt aus der
Seite (FullCalendar). Anmeldung: Windows-Anmeldung (Kerberos/NTLM) klappt im Firmennetz
meist von selbst; sonst einmal im Edge-Fenster anmelden.

Ein Eintrag im Kalender sieht so aus:
    08:10 - 08:55
    Systems - TCK0000049374 - Praktikanten / Azubi Oktober 2026
    TE0000087192
also Zeit, "Kunde - Ticket - Betreff" und die Nummer des Zeiterfassungseintrags.

Seit dem Mitschnitt vom 02.11.2026 liest Zeitzeuge die Woche zuerst direkt über die
Schnittstelle, die auch die Kalenderseite nutzt (API_JS: WidgetList/GetData mit Datumsfilter,
Anmeldung über das Token der Seite). Das liefert zusätzlich Status (Neu/Freigegeben),
Tätigkeitsart und gerundete Minuten. Klappt das nicht, liest es wie bisher aus der Seite.

Gelesene Tage landen in m42_buchungen.json. Die aktuelle Woche liest Zeitzeuge alle
10 Minuten, die letzten Wochen einmal pro Sitzung, ältere Wochen beim Blättern.

Umwandeln und Abgleich (ohne Qt) stehen in m42_data.py.
"""

import json
import threading
import time
from datetime import date, datetime, timedelta
from urllib.parse import urlsplit

from PySide6.QtCore import Signal

import safe_io
from m42_data import (api_bookings_by_day, bookings_by_day, load_store, save_days,  # noqa: F401
                      week_start)
from pbx_reader import BrowserReader


# Läuft vor dem Code der Seite: zählt offene Abfragen, damit Zeitzeuge weiß,
# wann die Einträge einer Woche fertig geladen sind
PENDING_JS = r"""
(function () {
  if (window.__zzPending !== undefined) return;
  window.__zzPending = 0;
  window.__zzLast = Date.now();
  function done() { window.__zzPending = Math.max(0, window.__zzPending - 1); window.__zzLast = Date.now(); }
  const origFetch = window.fetch;
  if (origFetch) window.fetch = function () {
    window.__zzPending++; window.__zzLast = Date.now();
    return origFetch.apply(this, arguments).then(function (r) { done(); return r; },
                                                 function (e) { done(); throw e; });
  };
  const send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function () {
    window.__zzPending++; window.__zzLast = Date.now();
    this.addEventListener("loadend", done);
    return send.apply(this, arguments);
  };
})();
"""

# Woche mit dem Tag %s zeigen und alle Einträge lesen. Gibt JSON zurück:
# {state: "ok" | "login" | "loading", url, days: [YYYY-MM-DD …], events: [{date, time, title, description}]}
READ_JS = r"""
(async function (target) {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  function state() {
    if (document.querySelector("input[type=password]")) return "login";
    if (/\/(wm\/)?login\b/i.test(location.pathname)) return "login";  // Matrix42-Anmeldeseite
    return document.querySelector(".fc-view") ? "ok" : "loading";
  }
  function days() {
    return Array.from(document.querySelectorAll(".fc-head th.fc-day-header[data-date]"))
      .map(th => th.getAttribute("data-date"));
  }
  async function settle() {
    // offene Abfragen abwarten (höchstens 20 s), dann kurz Ruhe
    const end = Date.now() + 20000;
    await sleep(300);
    while (Date.now() < end) {
      const pending = window.__zzPending || 0;
      const quiet = Date.now() - (window.__zzLast || 0);
      if (!pending && quiet > 700 && !document.querySelector(".fc-loading, .loading-indicator:not(.ng-hide)")) break;
      await sleep(200);
    }
  }
  // Auf die Kalenderseite warten. Die Anmeldeseite (/wm/login?…autoLogin=true) leitet im
  // Firmennetz oft von selbst weiter (Windows-Anmeldung): ohne Passwortfeld 20 s abwarten
  for (let i = 0; i < 60; i++) {
    const s = state();
    if (s === "ok") break;
    if (s === "login" && (document.querySelector("input[type=password]") || i >= 40)) break;
    await sleep(500);
  }
  if (state() !== "ok") return JSON.stringify({state: state(), url: location.href});

  const el = document.querySelector(".fc");
  const $ = window.jQuery;
  const api = $ && el && $(el).data && $(el).data("fullCalendar") ? $(el) : null;
  // Wochenansicht
  if (!document.querySelector(".fc-agendaWeek-view")) {
    if (api) { try { api.fullCalendar("changeView", "agendaWeek"); } catch (e) {} }
    if (!document.querySelector(".fc-agendaWeek-view")) {
      const b = document.querySelector(".fc-agendaWeek-button");
      if (b) b.click();
    }
    await settle();
  }
  // Zur Woche mit target blättern
  let moved = false;
  if (api && !days().includes(target)) {
    try { api.fullCalendar("gotoDate", target); moved = true; } catch (e) {}
    await settle();
  }
  for (let i = 0; i < 120 && !days().includes(target); i++) {
    const d = days();
    if (!d.length) break;
    const b = document.querySelector(target < d[0] ? ".fc-prev-button" : ".fc-next-button");
    if (!b) break;
    b.click(); moved = true;
    await sleep(150);
    if (days().includes(target)) await settle();
  }
  if (!days().includes(target)) return JSON.stringify({state: "ok", url: location.href, days: days(), missing: true});
  if (!moved) await settle();

  // Einträge lesen: Spalte i der Tabelle gehört zum Tag i im Kopf
  const head = days();
  const cols = Array.from(document.querySelectorAll(".fc-time-grid .fc-content-skeleton > table > tbody > tr > td"))
    .filter(td => !td.classList.contains("fc-axis"));
  const events = [];
  cols.forEach(function (td, i) {
    td.querySelectorAll(".fc-time-grid-event").forEach(function (a) {
      if (a.closest(".fc-helper-container")) return;  // Vorschau beim Ziehen
      const t = a.querySelector(".fc-time");
      events.push({
        date: head[i] || null,
        time: t ? (t.getAttribute("data-full") || t.textContent || "").trim() : "",
        title: ((a.querySelector(".fc-title") || {}).textContent || "").trim(),
        description: ((a.querySelector(".fc-description") || {}).textContent || "").trim()
      });
    });
  });
  return JSON.stringify({state: "ok", url: location.href, days: head, events: events});
})(%s)
"""

# Woche direkt über die Schnittstelle lesen (wie die Kalenderseite selbst, siehe
# Mitschnitt): POST /m42Services/api/WidgetList/GetData/<Widget> mit Datumsfilter, Anmeldung
# über das Token, das die Seite im localStorage hält. Gibt JSON zurück:
# {state: "ok" | "login" | "notoken" | "error", status, widget, total, items: [...]}
DEFAULT_WIDGET = "05d8b58d-5764-ef11-debc-0050569e2f05"  # Kalender-Widget laut Mitschnitt
API_JS = r"""
(async function (monday, widgetDefault) {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const isLogin = () => !!document.querySelector("input[type=password]") || /\/(wm\/)?login\b/i.test(location.pathname);
  const token = () => { try { return localStorage.getItem("mx.auth.session.token"); } catch (e) { return null; } };
  // Auf Token oder fertige Seite warten (Anmeldung im Firmennetz läuft oft von selbst)
  for (let i = 0; i < 60 && !token(); i++) {
    if (isLogin() && (document.querySelector("input[type=password]") || i >= 40)) break;
    if (document.querySelector(".fc-view") && i >= 4) break;  // Seite da, aber ohne Token
    await sleep(500);
  }
  if (!token()) return JSON.stringify({state: isLogin() ? "login" : "notoken", url: location.href});
  // Widget der Kalenderseite: aus den Abfragen der Seite, sonst der eingestellte
  const widgets = [];
  try {
    for (const e of performance.getEntriesByType("resource")) {
      const m = /\/WidgetList\/GetData\/([0-9a-f-]{36})(?:[?#]|$)/i.exec(e.name);
      if (m && !widgets.includes(m[1])) widgets.push(m[1]);
    }
  } catch (e) {}
  if (widgetDefault && !widgets.includes(widgetDefault)) widgets.push(widgetDefault);
  const from = new Date(monday + "T00:00:00"), to = new Date(from.getTime());
  to.setDate(to.getDate() + 7);
  const a = from.toISOString(), b = to.toISOString();
  const range = (p, q) => ({Groups: [], LogicalOperator: 1, Conditions: [
    {Property: p, Operator: 12, Value: [a, ""]}, {Property: q, Operator: 12, Value: ["", b]}]});
  const filter = {Conditions: [], LogicalOperator: 1, Groups: [
    {Groups: [], Conditions: [], LogicalOperator: 1},
    {Conditions: [], LogicalOperator: 2, Groups: [range("Start", "Start"), range("End", "End"),
      {Groups: [], LogicalOperator: 1, Conditions: [
        {Property: "Start", Operator: 12, Value: ["", a]}, {Property: "End", Operator: 12, Value: [b, ""]}]}]},
    {Groups: [], Conditions: [], LogicalOperator: 1}]};
  const keep = ["Sys-Entity", "ObjectId", "Customer", "Activity", "TicketInfo", "State", "ActivityType",
                "Start", "End", "WorktimeRounded", "WorktimeNominal"];
  let last = {state: "error", status: 0, url: location.href};
  for (const widget of widgets) {
    let r;
    try {
      r = await fetch("/m42Services/api/WidgetList/GetData/" + widget, {
        method: "POST", credentials: "include",
        headers: {"Authorization": "Bearer " + token(), "Content-Type": "application/json;charset=UTF-8",
                  "Accept": "application/json, text/plain, */*"},
        body: JSON.stringify(filter)});
    } catch (e) { last = {state: "error", status: 0, error: String(e)}; continue; }
    if (r.status === 401) return JSON.stringify({state: "login", status: 401});
    if (!r.ok) { last = {state: "error", status: r.status, widget: widget}; continue; }
    let data;
    try { data = await r.json(); } catch (e) { last = {state: "error", status: r.status, widget: widget}; continue; }
    if (!Array.isArray(data)) { last = {state: "error", status: r.status, widget: widget}; continue; }
    if (data.some(x => x && x["Sys-Entity"] && x["Sys-Entity"] !== "ITMTimeEntryType")) {
      last = {state: "error", status: r.status, widget: widget, reason: "keine Zeiterfassung"}; continue;
    }
    const items = data.map(x => Object.fromEntries(keep.filter(k => k in (x || {})).map(k => [k, x[k]])));
    return JSON.stringify({state: "ok", widget: widget, total: r.headers.get("TotalCount"), items: items});
  }
  return JSON.stringify(last);
})(%s, %s)
"""


class M42Reader(BrowserReader):
    day_read = Signal(str)  # Tag (YYYY-MM-DD), dessen Buchungen neu sind

    NAME = "Matrix42"
    READ_INTERVAL = 10 * 60   # aktuelle Woche so oft neu lesen
    LOAD_TIMEOUT = 60         # so lange darf das Lesen einer Woche dauern

    def __init__(self, url, data_file, profile_dir, parent=None, weeks_back=4, use_api=True,
                 widget_id=""):
        url = (url or "").strip()
        super().__init__(url, profile_dir, parent)
        self.page_url = url  # die Kalenderseite selbst (base_url ist ohne / am Ende)
        self.data_file = data_file
        self.weeks_back = max(0, int(weeks_back or 0))
        self.days, self.read_at = load_store(data_file)
        self._lock = threading.Lock()
        self._wanted = set()   # Montage der Wochen, die gelesen werden sollen
        self._checked = set()  # in dieser Sitzung gelesene Wochen
        self._week_read = 0    # Zeitpunkt, zu dem die aktuelle Woche zuletzt gelesen wurde
        # Erst über die Schnittstelle lesen; klappt das nicht, aus der Seite (wie bisher)
        self.use_api = use_api
        self.widget_id = (widget_id or "").strip() or DEFAULT_WIDGET
        self.source = ""       # "Schnittstelle" oder "Seite": womit zuletzt gelesen wurde

    def start_url(self):
        return self.page_url

    def _on_browser_started(self):
        self._tools.call("Page.enable")
        self._tools.call("Page.addScriptToEvaluateOnNewDocument", source=PENDING_JS)
        self._tools.call("Page.navigate", url=self.start_url())

    def _browser_args(self, mode, debug=True, url=None):
        """Windows-Anmeldung (Kerberos/NTLM) auch im unsichtbaren Edge erlauben."""
        args = super()._browser_args(mode, debug, url)
        host = urlsplit(self.page_url).hostname
        if host:
            args.insert(1, f"--auth-server-allowlist={host}")
            args.insert(1, f"--auth-negotiate-delegate-allowlist={host}")
        return args

    def health(self):
        if self._offline:
            return "warn", "nicht im Firmennetz"
        return super().health()

    def _failed_step(self, error):
        """Außerhalb des Firmennetzes ist "nicht erreichbar" normal: nicht melden."""
        if error is None:
            self._failed = True
            self._backoff.fail()
            self.next_try = None
            self._set_status("Matrix42: nicht erreichbar (nur im Firmennetz)")
            return
        super()._failed_step(error)

    # ---- Daten

    def day(self, date_str):
        """Buchungen eines Tages, None = noch nie gelesen."""
        return self.days.get(date_str)

    def want(self, date_str):
        """Woche mit diesem Tag lesen (einmal pro Sitzung), z. B. weil er angezeigt wird."""
        if date_str > date.today().isoformat():
            return
        monday = week_start(date_str)
        if monday == week_start(date.today().isoformat()) or monday in self._checked:
            return
        with self._lock:
            self._wanted.add(monday)
        if not self.needs_login:
            self._wake.set()

    def _todo(self):
        this_week = week_start(date.today().isoformat())
        with self._lock:
            todo = sorted(self._wanted, reverse=True)
            self._wanted.clear()
        for i in range(1, self.weeks_back + 1):  # die letzten Wochen einmal pro Sitzung
            monday = (date.fromisoformat(this_week) - timedelta(weeks=i)).isoformat()
            if monday not in self._checked and monday not in todo:
                todo.append(monday)
        if time.time() - self._week_read > self.READ_INTERVAL - 10 or this_week not in self._checked:
            todo.insert(0, this_week)
        return todo

    def _tick(self):
        if not self.page_url:
            raise RuntimeError("keine Adresse der Kalenderseite eingestellt")
        if not self._tools:
            self._start_browser()
        todo = self._todo()
        for i, monday in enumerate(todo):
            if self._stop.is_set() or self._login_open:
                break
            try:
                ok = self._read_week(monday)
            except Exception:
                this_week = week_start(date.today().isoformat())
                with self._lock:  # später nachholen
                    self._wanted.update(m for m in todo[i:] if m != this_week)
                raise
            if not ok:  # Anmeldung nötig: offene Wochen danach lesen
                this_week = week_start(date.today().isoformat())
                with self._lock:
                    self._wanted.update(m for m in todo[i:] if m != this_week)
                return
        self._set_status(f"Matrix42 gelesen {datetime.now():%H:%M}")

    def _read_week(self, monday):
        """Eine Woche lesen und speichern. False, wenn eine Anmeldung nötig ist."""
        self._set_status(f"Matrix42: lese Woche ab {monday[8:10]}.{monday[5:7]}. …")
        if self.use_api:
            done = self._read_week_api(monday)
            if done is not None:
                return done
        raw = self._evaluate(READ_JS % json.dumps(monday), timeout=self.LOAD_TIMEOUT)
        data = json.loads(raw) if raw else {}
        state = data.get("state")
        if state == "login" or (data.get("url") and urlsplit(data["url"]).hostname
                                and urlsplit(data["url"]).hostname != urlsplit(self.page_url).hostname):
            self._need_login()
            return False
        if state != "ok":
            # Seite noch nicht da (z. B. Startseite statt Kalender): neu laden, später nochmal
            self._tools.call("Page.navigate", url=self.start_url())
            raise RuntimeError("Kalender nicht gefunden – stimmt die Adresse der Kalenderseite?")
        if data.get("missing"):
            raise RuntimeError(f"Woche ab {monday} ließ sich im Kalender nicht anzeigen")
        self.needs_login = False
        self.source = "Seite"
        self._save(bookings_by_day(data.get("days") or [], data.get("events") or []))
        self._checked.add(monday)
        if monday == week_start(date.today().isoformat()):
            self._week_read = time.time()
        return True

    def _read_week_api(self, monday):
        """Woche über die Schnittstelle lesen. True = gelesen, False = Anmeldung nötig,
        None = Schnittstelle geht nicht (dann für diese Sitzung aus der Seite lesen)."""
        try:
            raw = self._evaluate(API_JS % (json.dumps(monday), json.dumps(self.widget_id)),
                                 timeout=self.LOAD_TIMEOUT)
            data = json.loads(raw) if raw else {}
        except Exception as e:  # Seite hängt o. Ä.: wie bisher aus der Seite lesen
            data = {"state": "error", "error": str(e)}
        state = data.get("state")
        if state == "login":
            self._need_login()
            return False
        items = data.get("items")
        total = str(data.get("total") or "")
        if state == "ok" and isinstance(items, list) and not (total.isdigit() and int(total) > len(items)):
            self.needs_login = False
            self.source = "Schnittstelle"
            if data.get("widget") and data["widget"] != self.widget_id:
                self.widget_id = data["widget"]
            self._save(api_bookings_by_day(monday, items))
            self._checked.add(monday)
            if monday == week_start(date.today().isoformat()):
                self._week_read = time.time()
            return True
        if state == "ok":
            data = {"state": "error", "reason": f"nur {len(items or [])} von {total} Einträgen"}
        self.use_api = False  # für diese Sitzung aus der Seite lesen
        safe_io.log(f"Matrix42: Schnittstelle geht nicht ({data}), lese aus der Seite")
        return None

    def _save(self, by_day):
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        changed = [d for d, items in by_day.items() if self.days.get(d) != items]
        for d, items in by_day.items():
            self.days[d] = items
            self.read_at[d] = now
        save_days(self.data_file, by_day, self.read_at)
        for d in changed:
            self.day_read.emit(d)

    def _login_done(self):
        """Angemeldet, sobald der Kalender (oder eine andere Seite als /wm/login) da ist."""
        try:
            return bool(self._evaluate(
                "!!document.querySelector('.fc-view') || (!/login/i.test(location.pathname)"
                " && !document.querySelector('input[type=password]') && location.pathname.length > 4)",
                timeout=5))
        except Exception:
            return False
