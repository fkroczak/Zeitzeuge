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
  // Angemeldete Abfragen der Seite an ihre Schnittstelle beobachten. Klappt eine, merkt sich
  // Zeitzeuge ihre Köpfe (vor allem die Anmeldung) und fragt genauso an; __zzAuthOk sagt, ob die
  // Anmeldung gilt. Ein altes Token im Profil gilt nicht: Matrix42 antwortet darauf mit 406.
  function norm(headers) {
    const h = {};
    try {
      if (headers && typeof headers.forEach === "function") headers.forEach(function (v, k) { h[String(k).toLowerCase()] = v; });
      else if (headers) Object.keys(headers).forEach(function (k) { h[k.toLowerCase()] = headers[k]; });
    } catch (e) {}
    return h;
  }
  function answered(url, h, status) {
    if (!/\/m42Services\/api\//i.test(String(url || "")) || !h.authorization) return;
    if (status >= 200 && status < 300) { window.__zzHeaders = h; window.__zzAuthOk = true; }
    else if (status === 401 || status === 406) window.__zzAuthOk = false;
  }
  const origFetch = window.fetch;
  window.__zzFetch = origFetch;  // für Zeitzeuges eigene Abfragen (zählen nicht als die der Seite)
  if (origFetch) window.fetch = function (input, init) {
    window.__zzPending++; window.__zzLast = Date.now();
    const url = input && input.url || input;
    const h = norm((init && init.headers) || (input && input.headers));
    return origFetch.apply(this, arguments).then(function (r) { done(); answered(url, h, r.status); return r; },
                                                 function (e) { done(); throw e; });
  };
  const open = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url) {
    this.__zzUrl = url; this.__zzH = {};
    return open.apply(this, arguments);
  };
  const setHeader = XMLHttpRequest.prototype.setRequestHeader;
  XMLHttpRequest.prototype.setRequestHeader = function (k, v) {
    if (this.__zzH) this.__zzH[k] = v;
    return setHeader.apply(this, arguments);
  };
  const send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function () {
    window.__zzPending++; window.__zzLast = Date.now();
    const xhr = this;
    this.addEventListener("loadend", function () { done(); answered(xhr.__zzUrl, norm(xhr.__zzH), xhr.status); });
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
  // Woche war schon zu sehen: FullCalendar hält die Einträge im Speicher, darum neu holen,
  // sonst fehlen neue Buchungen, bis die Seite selbst nachlädt
  if (!moved && api) { try { api.fullCalendar("refetchEvents"); } catch (e) {} }
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

# Gemeinsame Helfer für API_JS und FETCH_JS (im Rumpf der async-Funktion): Anmeldung wie die
# Seite selbst, Köpfe ihrer eigenen Abfragen, Erkennen der Anmeldeseite
_JS_HELPERS = r"""  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const isLogin = () => !!document.querySelector("input[type=password]") || /\/(wm\/)?login\b/i.test(location.pathname);
  // Anmeldung: wie die Seite selbst (gemerkte Köpfe), sonst das Token aus dem localStorage
  const token = () => {
    let t = null;
    try { t = localStorage.getItem("mx.auth.session.token"); } catch (e) {}
    if (t && t.charAt(0) === '"') { try { t = JSON.parse(t); } catch (e) {} }
    return t || null;
  };
  const auth = () => (window.__zzHeaders || {}).authorization || (token() ? "Bearer " + token() : null);
  const apiHeaders = extra => {
    const h = {"accept": "application/json, text/plain, */*"};
    const page = window.__zzHeaders || {};
    Object.keys(page).forEach(k => { if (k !== "content-type" && k !== "content-length") h[k] = page[k]; });
    h.authorization = auth();
    Object.keys(extra || {}).forEach(k => { h[k.toLowerCase()] = extra[k]; });
    return h;
  };
  const apiFetch = (url, opts) => (window.__zzFetch || fetch).call(window, url, opts);
"""

# Woche direkt über die Schnittstelle lesen (wie die Kalenderseite selbst, siehe
# Mitschnitt): POST /m42Services/api/WidgetList/GetData/<Widget> mit Datumsfilter, Anmeldung
# über das Token, das die Seite im localStorage hält. Gibt JSON zurück:
# {state: "ok" | "login" | "notoken" | "error", status, widget, total, items: [...]}
DEFAULT_WIDGET = "05d8b58d-5764-ef11-debc-0050569e2f05"  # Kalender-Widget laut Mitschnitt
API_JS = r"""
(async function (monday, widgetDefault) {
""" + _JS_HELPERS + r"""  // Auf die fertige Seite warten (Anmeldung im Firmennetz läuft oft von selbst). Nicht nur
  // aufs Token: nach dem Start liegt oft noch ein abgelaufenes im Profil (Fehler 406), und die
  // Seite leitet gleich zur Anmeldung weiter. Ohne Kalender nach 30 s das Token nehmen, wenn da.
  for (let i = 0; i < 60; i++) {
    if (window.__zzAuthOk === true && window.__zzHeaders) break;  // Seite ist angemeldet
    if (isLogin() && (document.querySelector("input[type=password]") || i >= 40)) break;
    if (document.querySelector(".fc-view") && (auth() || i >= 4)) break;
    await sleep(500);
  }
  if (!auth()) return JSON.stringify({state: isLogin() ? "login" : "notoken", url: location.href});
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
                "Start", "End", "WorktimeRounded", "WorktimeNominal", "Anwender", "Anwender_Value"];
  let last = {state: "error", status: 0, url: location.href};
  for (const widget of widgets) {
    let r;
    try {
      r = await apiFetch("/m42Services/api/WidgetList/GetData/" + widget, {
        method: "POST", credentials: "include",
        headers: apiHeaders({"Content-Type": "application/json;charset=UTF-8"}),
        body: JSON.stringify(filter)});
    } catch (e) { last = {state: "error", status: 0, error: String(e)}; continue; }
    if (r.status === 401) return JSON.stringify({state: "login", status: 401});
    if (!r.ok) {
      let detail = "";
      try { detail = (await r.text()).slice(0, 200); } catch (e) {}
      last = {state: "error", status: r.status, widget: widget, page_auth: !!window.__zzHeaders, detail: detail};
      continue;
    }
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


# Eine Abfrage an die Schnittstelle aus der angemeldeten Seite (zum Buchen). Gibt JSON zurück:
# {state: "ok" | "login" | "notoken" | "error", status, data, user}
# user: Kennung des eigenen Benutzers aus den Abfragen der Seite (AutoTimeTracking/Settings/<id>)
FETCH_JS = r"""
(async function (method, path, body, contentType, fresh) {
""" + _JS_HELPERS + r"""  // fresh: Seite eben neu geladen, auf ihre eigene angemeldete Abfrage warten (höchstens 30 s)
  for (let i = 0; i < 60 && (!auth() || (fresh && !window.__zzHeaders)); i++) {
    if (isLogin() && (document.querySelector("input[type=password]") || i >= 40)) break;
    await sleep(500);
  }
  if (!auth()) return JSON.stringify({state: isLogin() ? "login" : "notoken"});
  let user = null;
  try {
    for (const e of performance.getEntriesByType("resource")) {
      const m = /\/AutoTimeTracking\/Settings\/([0-9a-f-]{36})/i.exec(e.name);
      if (m) user = m[1];
    }
  } catch (e) {}
  const extra = {"Explicit-Language": "de-DE"};
  if (body !== null) extra["Content-Type"] = contentType || "application/json;charset=UTF-8";
  const headers = apiHeaders(extra);
  let r;
  try {
    r = await apiFetch(path, {method: method, credentials: "include", headers: headers,
                           body: body === null ? undefined : body});
  } catch (e) { return JSON.stringify({state: "error", status: 0, error: String(e), user: user}); }
  if (r.status === 401) return JSON.stringify({state: "login", status: 401});
  const text = await r.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (e) { data = text.slice(0, 500); }
  return JSON.stringify({state: r.ok ? "ok" : "error", status: r.status, data: data, user: user});
})(%s, %s, %s, %s, %s)
"""


# Anmeldefenster: angemeldet? Erst wenn die Seite (auf dem Matrix42-Server, keine Anmeldeseite)
# eine angemeldete Abfrage erfolgreich gemacht hat. Ein Token im localStorage allein reicht
# nicht: nach dem Start liegt dort oft noch ein abgelaufenes, und das Fenster ging zu, bevor
# Matrix42 zur Anmeldung weiterleiten konnte.
LOGIN_DONE_JS = r"""
(function (host) {
  if (host && location.hostname !== host) return false;
  if (document.querySelector("input[type=password]") || /\/(wm\/)?login\b/i.test(location.pathname)) return false;
  return window.__zzAuthOk === true;
})(%s)
"""


class M42Reader(BrowserReader):
    day_read = Signal(str)  # Tag (YYYY-MM-DD), dessen Buchungen neu sind
    booking_done = Signal(object)  # Ergebnis von book(): {ok, entry | error, request}
    activity_types_loaded = Signal(object)  # [(Wert, Name)] der Tätigkeitsarten
    tickets_found = Signal(object)  # Ergebnis von search_tickets(): {text, rows, error}
    my_tickets_loaded = Signal(object)  # Meine Tickets: {rows (None = unbekannt), error, at}
    ticket_task_done = Signal(object)  # Ergebnis von ticket_task(): {kind, ok, data | error, unclear}

    NAME = "Matrix42"
    READ_INTERVAL = 10 * 60   # aktuelle Woche so oft neu lesen
    LOAD_TIMEOUT = 60         # so lange darf das Lesen einer Woche dauern
    # Matrix42 leitet nach dem Start oft über die Anmeldung weiter (altes Token, Windows-
    # Anmeldung): das Lesen dann auf der neuen Seite wiederholen statt Edge neu zu starten
    NAVIGATION_RETRIES = 3
    # Abfragen, die etwas speichern: nie wiederholen (könnte doppelt buchen/anlegen/schließen)
    NO_RETRY = ("UpdateData", "/ticket/Close", "/activity/TakeOver")

    def __init__(self, url, data_file, profile_dir, parent=None, weeks_back=4, use_api=True,
                 widget_id="", own_name=""):
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
        self._api_wanted = use_api  # Einstellung: bei Aktualisieren die Schnittstelle erneut versuchen
        self._refresh_count = 0     # zählt Aktualisieren (F5), siehe _read_week
        self.widget_id = (widget_id or "").strip() or DEFAULT_WIDGET
        self.source = ""       # "Schnittstelle" oder "Seite": womit zuletzt gelesen wurde
        self.user_id = ""      # eigener Matrix42-Benutzer (aus gelesenen Buchungen), zum Buchen
        self.activity_types = []  # [(Wert, Name)], beim ersten Buchen geholt
        # Meine Tickets (Bearbeiter = ich): Name aus der Einstellung, sonst aus den eigenen Buchungen
        self.own_name = (own_name or "").strip()
        self.user_name = ""
        self.my_tickets = None  # letzte Antwort von my_tickets_loaded
        self.ticket_list = ""   # Ticketliste (Widget-ID), leer = m42_booking.DEFAULT_IDS
        self.ticket_ids = {}    # Kennungen für Anlegen/Schließen, leer = m42_tickets.DEFAULT_IDS
        self._me_checked = False  # eigener Benutzer schon bei Matrix42 nachgefragt (/userinfo)
        self._tickets_read = 0
        self._booking = False

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

    def refresh(self, date_str):
        """Woche mit diesem Tag sofort neu lesen (Aktualisieren, F5), auch wenn sie in dieser
        Sitzung schon gelesen ist."""
        if date_str > date.today().isoformat():
            return
        monday = week_start(date_str)
        self.use_api = self._api_wanted  # nach einem Aussetzer wieder über die Schnittstelle
        self._refresh_count += 1
        self._checked.discard(monday)
        if monday == week_start(date.today().isoformat()):
            self._week_read = 0  # aktuelle Woche: beim nächsten Durchlauf gleich lesen
        else:
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
        if time.time() - self._tickets_read > self.READ_INTERVAL - 10 and not self._stop.is_set():
            self._read_my_tickets()  # Lese-Thread hält _browser_lock schon
        self._set_status(f"Matrix42 gelesen {datetime.now():%H:%M}")

    def _read_week(self, monday):
        """Eine Woche lesen und speichern. False, wenn eine Anmeldung nötig ist."""
        count = self._refresh_count
        ok = self._read_week_once(monday)
        # Während des Lesens Aktualisieren gedrückt: die aktuelle Woche gleich nochmal lesen,
        # sonst gälte sie für 10 Minuten als frisch, obwohl sie vor dem Klick gelesen wurde
        if count != self._refresh_count and monday == week_start(date.today().isoformat()):
            self._week_read = 0
            self._checked.discard(monday)
            self._wake.set()
        return ok

    def _read_week_once(self, monday):
        self._set_status(f"Matrix42: lese Woche ab {monday[8:10]}.{monday[5:7]}. …")
        if self.use_api:
            done = self._read_week_api(monday)
            if done is not None:
                return done
        raw = self._evaluate(READ_JS % json.dumps(monday), timeout=self.LOAD_TIMEOUT,
                             retries=self.NAVIGATION_RETRIES)
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
        js = API_JS % (json.dumps(monday), json.dumps(self.widget_id))
        try:
            raw = self._evaluate(js, timeout=self.LOAD_TIMEOUT, retries=self.NAVIGATION_RETRIES)
            data = json.loads(raw) if raw else {}
            if data.get("status") == 406:  # Anmeldung abgelehnt (altes Token): Seite neu laden, nochmal
                self._tools.call("Page.navigate", url=self.start_url())
                time.sleep(2)
                raw = self._evaluate(js, timeout=self.LOAD_TIMEOUT, retries=self.NAVIGATION_RETRIES)
                data = json.loads(raw) if raw else {}
                if data.get("status") == 406:  # Anmeldung gilt nicht mehr: neu anmelden
                    data = {"state": "login"}
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
            users = {i.get("Anwender_Value") for i in items if isinstance(i, dict) and i.get("Anwender_Value")}
            if len(users) == 1:  # eigene Buchungen: das ist dein Benutzer (zum Buchen)
                self.user_id = users.pop()
                names = {i.get("Anwender") for i in items if isinstance(i, dict) and i.get("Anwender")}
                if len(names) == 1:  # und dein Name (für „Meine Tickets“)
                    self.user_name = names.pop()
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

    # ---- Buchen (m42_booking.py)

    @property
    def booking(self):
        return self._booking

    def book(self, request):
        """Tätigkeit in Matrix42 buchen (im Hintergrund). request: dict mit ticket, start, end
        (datetime), minutes, text, activity_type, ids (m42_booking.ids). Ergebnis über
        booking_done. False, wenn gerade schon gebucht wird."""
        if self._booking or self._login_open:
            return False
        self._booking = True
        threading.Thread(target=self._book, args=(request,), daemon=True,
                         name="Matrix42 buchen").start()
        return True

    def search_tickets(self, text, ticket_list=None):
        """Tickets suchen (im Hintergrund): Kunde, Benutzer, Ticketnummer oder Titel enthält
        text. Ergebnis über tickets_found."""
        threading.Thread(target=self._search_tickets, args=(text, ticket_list), daemon=True,
                         name="Matrix42 Tickets suchen").start()

    def _search_tickets(self, text, ticket_list=None):
        import m42_booking as mb
        text = (text or "").strip()
        word, fields = mb.search_plan(text)
        found, errors = [], []
        try:
            with self._browser_lock:
                for field in fields:
                    path = (f"{mb.API}/WidgetList/GetData/{ticket_list or mb.DEFAULT_IDS['ticket_list']}"
                            f"?orderBy=CreatedDate+desc&pageSize={mb.SEARCH_LIMIT}&page=0")
                    try:
                        data = self._fetch("POST", path, mb.search_query(field, word))
                        found.append(data if isinstance(data, list) else [])
                    except mb.BookingError as e:
                        errors.append(f"{field}: {e}")
                        if "anmelden" in str(e):
                            raise
            rows = mb.merge_tickets(*found, text=text)
            error = "" if found else (errors[0] if errors else "keine Antwort")
            if errors:
                safe_io.log(f"Matrix42: Ticketsuche, nicht jedes Feld ging ({'; '.join(errors)})")
        except Exception as e:
            rows, error = [], str(e)
        self.tickets_found.emit({"text": text, "rows": rows, "error": error})

    def load_my_tickets(self):
        """Meine Tickets sofort neu lesen (im Hintergrund), Ergebnis über my_tickets_loaded."""
        def run():
            with self._browser_lock:
                self._read_my_tickets()
        threading.Thread(target=run, daemon=True, name="Matrix42 meine Tickets").start()

    def _read_my_tickets(self):
        """Offene Tickets lesen, bei denen ich Bearbeiter bin. Nur mit gehaltenem _browser_lock."""
        import m42_booking as mb
        try:
            self._me()
        except Exception as e:  # z. B. Anmeldung nötig: dann scheitert gleich auch die Liste
            safe_io.log(f"Matrix42: eigener Benutzer nicht gelesen ({e})")
        name = self.own_name or self.user_name
        result = {"rows": None, "error": "", "at": datetime.now().strftime("%H:%M"), "name": name}
        word = mb.my_tickets_word(name)
        if not word:
            result["error"] = ("Eigener Name noch unbekannt. Er kommt aus deinen Buchungen in Matrix42 "
                               "oder aus der Einstellung „m42_own_name“.")
        else:
            items = []
            try:
                for page in range(mb.MY_TICKETS_PAGES):
                    data = self._fetch("POST", f"{mb.API}/WidgetList/GetData/"
                                       f"{self.ticket_list or mb.DEFAULT_IDS['ticket_list']}"
                                       f"?orderBy=CreatedDate+desc&pageSize={mb.MY_TICKETS_PAGE_SIZE}&page={page}",
                                       mb.search_query("Recipient", word))
                    data = data if isinstance(data, list) else []
                    items.extend(data)
                    if len(data) < mb.MY_TICKETS_PAGE_SIZE:
                        break
                result["rows"] = mb.my_open_tickets(items, name, "" if self.own_name else self.user_id)
                self._tickets_read = time.time()
            except Exception as e:
                result["error"] = str(e)
                safe_io.log(f"Matrix42: meine Tickets nicht gelesen ({e})")
        if result["rows"] is not None or self.my_tickets is None:
            self.my_tickets = result
        else:  # Fehler: alte Liste behalten, Fehler dazuschreiben
            self.my_tickets = dict(self.my_tickets, error=result["error"])
        self.my_tickets_loaded.emit(self.my_tickets)

    def _me(self):
        """Eigenen Benutzer (Kennung und Name) einmal pro Sitzung bei Matrix42 nachfragen.
        Nur mit gehaltenem _browser_lock."""
        import m42_tickets
        if self._me_checked:
            return
        me = m42_tickets.own_user(self._fetch("GET", "/m42Services/api/userinfo"))
        self._me_checked = True
        if me:
            self.user_id = me["id"]
            self.user_name = me["name"] or self.user_name

    # ---- Tickets anlegen und schließen (m42_tickets.py)

    def ticket_task(self, kind, **args):
        """Im Hintergrund: "users" (text), "user_details" (user), "categories", "create" (request),
        "load" (id), "edit" (request), "close_info" (id, type), "close" (request).
        Ergebnis über ticket_task_done. False, wenn gerade ein Anmeldefenster offen ist."""
        if self._login_open:
            return False
        threading.Thread(target=self._ticket_task, args=(kind, args), daemon=True,
                         name=f"Matrix42 Ticket {kind}").start()
        return True

    def _ticket_task(self, kind, args):
        import m42_tickets as mt
        result = {"kind": kind, "ok": False, "args": args}
        state = {"sent": False}
        try:
            self._wake.set()
            with self._browser_lock:
                ids = dict(mt.DEFAULT_IDS, **{k: v for k, v in self.ticket_ids.items() if v})
                if kind == "users":
                    data = self._fetch("POST", "/m42Services/api/entity/fragments/forControl",
                                       mt.user_query(ids["ticket_dialog"], args.get("text", "")))
                    result["data"] = mt.users_from_fragments(data)
                elif kind == "user_details":
                    user = args["user"]
                    result["data"] = self._fetch("GET", f"/m42Services/api/activity/UserDetails/{user}/?userId={user}")
                elif kind == "categories":
                    data = self._fetch("POST", "/m42Services/api/entity/tree", mt.tree_query(ids["ticket_dialog"]))
                    result["data"] = mt.categories_from_tree(data)
                elif kind == "create":
                    result["data"] = self._create_ticket(args["request"], ids, state)
                elif kind == "load":
                    data = self._fetch("GET", mt.edit_data_path(ids["ticket_edit_dialog"], args["id"]))
                    result["data"] = mt.ticket_view(mt.loaded_entity(data))
                elif kind == "edit":
                    result["data"] = self._edit_ticket(args["request"], ids, state)
                elif kind == "close_info":
                    result["data"] = self._close_info(args["id"], args.get("type"), ids)
                elif kind == "close":
                    result["data"] = self._close_ticket(args["request"], state)
                else:
                    raise ValueError(kind)
            result["ok"] = True
        except Exception as e:
            result["error"] = str(e)
            if state["sent"]:  # z. B. Zeitüberschreitung: Matrix42 kann es trotzdem gespeichert haben
                result["unclear"] = True
                result["error"] = f"unklar, ob es geklappt hat ({e}). Bitte in Matrix42 nachsehen."
            safe_io.log(f"Matrix42: Ticket {kind} fehlgeschlagen ({e!r})")
        if result["ok"] and kind in ("create", "edit", "close"):
            self._tickets_read = 0  # Meine Tickets beim nächsten Durchlauf neu lesen
            threading.Thread(target=self.load_my_tickets, daemon=True).start()
        self.ticket_task_done.emit(result)

    def _create_ticket(self, request, ids, state):
        """Ticket anlegen (und übernehmen). Nur mit gehaltenem _browser_lock.
        -> {"ticket", "id", "type", "taken_over", "warning"}"""
        import m42_tickets as mt
        api, dialog = "/m42Services/api", ids["ticket_dialog"]
        self._me()
        self._set_status("Matrix42: lege Ticket an …")
        template = (self._fetch("POST", f"{api}/WidgetDialog/GetNewData/{dialog}", mt.new_ticket_body(),
                                "text/plain;charset=UTF-8") or {}).get("Entity")
        category, initiator, kind = request["category"], request["initiator"], int(request["type"])
        defaults = self._fetch("GET", f"{api}/activity/category/{category}/?categoryId={category}") or {}
        impact, urgency = defaults.get("Impact"), defaults.get("Urgency")
        sla = (self._fetch("GET", mt.sla_path(category, initiator, kind, impact)) or {}).get("TightestItem")
        try:
            callback = (self._fetch("GET", f"{api}/activity/UserDetails/{initiator}/?userId={initiator}")
                        or {}).get("Phone")
        except Exception:  # nur der Rückruf fehlt dann
            callback = None
        entity = mt.ticket_entity(template, kind, request.get("subject", ""), request.get("description", ""),
                                  category, initiator, self.user_id, sla, impact, urgency, callback)
        state["sent"] = True
        created = mt.created_ticket(self._fetch("POST", f"{api}/WidgetDialog/UpdateData/{dialog}", mt.wrap(entity)))
        state["sent"] = False  # angelegt: was jetzt schiefgeht, ist nur noch ein Hinweis
        created["taken_over"], created["warning"] = False, ""
        if created["type"] and created["type"] != mt.ENTITY_OF_TYPE[kind]:
            created["warning"] = (f"Matrix42 hat das Ticket als {created['type'].replace('SPSActivityType', '')} "
                                  "angelegt. Bitte die Art in Matrix42 prüfen.")
        if request.get("take_over", True):
            try:
                self._fetch("POST", f"{api}/activity/TakeOver",
                            mt.take_over_body(created["id"], created["type"] or mt.ENTITY_OF_TYPE[kind]))
                created["taken_over"] = True
            except Exception as e:
                created["warning"] = (created["warning"] + " " if created["warning"] else "") + \
                    f"Übernehmen ging nicht ({e}). Bitte in Matrix42 übernehmen."
        self._set_status(f"Matrix42: Ticket {created['ticket']} angelegt")
        return created

    def _edit_ticket(self, request, ids, state):
        """Betreff ändern und Beschreibung ergänzen. Nur mit gehaltenem _browser_lock.
        Lädt das Ticket frisch; hat es inzwischen jemand gespeichert (andere Versionsmarke als beim
        Öffnen), wird nichts geschickt."""
        import m42_tickets as mt
        dialog, ticket_id = ids["ticket_edit_dialog"], request["id"]
        name = request.get("ticket") or "Ticket"
        self._set_status(f"Matrix42: speichere {name} …")
        entity = mt.loaded_entity(self._fetch("GET", mt.edit_data_path(dialog, ticket_id)))
        if request.get("stamp") and mt.stamp(entity) != request["stamp"]:
            raise mt.BookingError(f"{name} wurde inzwischen in Matrix42 geändert. "
                                  "Bitte das Fenster schließen und neu öffnen.")
        body = mt.edited_entity(entity, request.get("subject", ""), request.get("addition", ""))
        state["sent"] = True
        saved = mt.saved_ticket(self._fetch("POST", f"/m42Services/api/WidgetDialog/UpdateData/{dialog}",
                                            mt.wrap(body)), ticket_id)
        self._set_status(f"Matrix42: {saved['ticket'] or name} gespeichert")
        return dict(saved, subject=body["SPSActivityClassBase"]["Subject"])

    def _close_info(self, ticket_id, kind, ids):
        """Vor dem Schließen: Lösungstext, den das Ticket schon hat (wieder eröffnet). -> {"solution"}"""
        import m42_tickets as mt
        api = "/m42Services/api"
        kind = kind or "SPSActivityTypeTicket"
        initial = self._fetch("POST", f"{api}/ticket/CloseWizardInitialData/?ticketType={kind}", [ticket_id]) or {}
        solution = mt.previous_solution(initial)
        if not solution:
            entity = mt.loaded_entity(self._fetch("GET", mt.edit_data_path(ids["ticket_edit_dialog"], ticket_id)))
            solution = mt.previous_solution(initial, entity)
        return {"solution": solution}

    def _close_ticket(self, request, state):
        """Ticket mit Lösungstext schließen. Nur mit gehaltenem _browser_lock."""
        import m42_tickets as mt
        api = "/m42Services/api"
        ticket_id, kind = request["id"], request.get("type") or "SPSActivityTypeTicket"
        self._set_status(f"Matrix42: schließe {request.get('ticket', 'Ticket')} …")
        initial = self._fetch("POST", f"{api}/ticket/CloseWizardInitialData/?ticketType={kind}", [ticket_id]) or {}
        body = mt.close_body(ticket_id, request.get("solution", ""), initial.get("TicketCategory"),
                             notify_initiator=request.get("notify", True),
                             close_related=initial.get("CloseRelatedIncidents", True))
        state["sent"] = True
        self._fetch("POST", f"{api}/ticket/Close", body)
        self._set_status(f"Matrix42: {request.get('ticket', 'Ticket')} geschlossen")
        return {"ticket": request.get("ticket", "")}

    def load_activity_types(self):
        """Tätigkeitsarten aus Matrix42 holen (im Hintergrund), Ergebnis über activity_types_loaded."""
        if self.activity_types:
            self.activity_types_loaded.emit(list(self.activity_types))
            return
        threading.Thread(target=self._load_activity_types, daemon=True).start()

    def _fetch(self, method, path, body=None, content_type=None):
        """Abfrage aus der angemeldeten Seite. Aufruf nur mit gehaltenem _browser_lock.
        -> data (JSON). LoginRequired/BookingError bei Problemen."""
        import m42_booking
        if not self._tools:
            self._start_browser()
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False)
        result = self._fetch_once(method, path, body, content_type)
        if result.get("status") == 406:
            # Matrix42 lehnt die Anmeldung ab (meist altes Token im Profil): Seite neu laden,
            # damit sie sich frisch anmeldet, und einmal mit ihren Köpfen wiederholen.
            # 406 heißt "nicht ausgeführt", darum ist das auch beim Buchen ungefährlich.
            safe_io.log(f"Matrix42: Fehler 406 bei {path.split('?')[0]}, lade Seite neu und versuche es nochmal")
            self._tools.call("Page.navigate", url=self.start_url())
            time.sleep(2)
            result = self._fetch_once(method, path, body, content_type, fresh=True)
            if result.get("status") == 406:  # Anmeldung gilt nicht mehr: neu anmelden
                result = {"state": "login"}
        if result.get("user"):
            self.user_id = self.user_id or result["user"]
        if result.get("state") in ("login", "notoken"):
            self._need_login()
            raise m42_booking.BookingError("Bitte zuerst bei Matrix42 anmelden (Einstellungen → "
                                           "Datenquellen → Einrichten → Matrix42 …).")
        if result.get("state") != "ok":
            detail = result.get("data")
            if detail is not None and not isinstance(detail, str):
                detail = json.dumps(detail, ensure_ascii=False)
            raise m42_booking.BookingError(f"Matrix42 antwortet mit Fehler {result.get('status')}"
                                           f"{': ' + detail[:200] if detail else ''}")
        return result.get("data")

    def _fetch_once(self, method, path, body, content_type, fresh=False):
        raw = self._evaluate(FETCH_JS % (json.dumps(method), json.dumps(path), json.dumps(body),
                                         json.dumps(content_type), json.dumps(fresh)),
                             # Speichern nie wiederholen (könnte doppelt buchen)
                             timeout=self.LOAD_TIMEOUT,
                             retries=self.NAVIGATION_RETRIES
                             if fresh and not any(w in path for w in self.NO_RETRY) else 0)
        return json.loads(raw) if raw else {"state": "error", "status": 0}

    def _load_activity_types(self):
        import m42_booking
        try:
            with self._browser_lock:
                data = self._fetch("GET", f"{m42_booking.API}/entity/enumeration/ITMTimeEntryPickupActivityType")
            self.activity_types = m42_booking.activity_types(data)
        except Exception as e:
            safe_io.log(f"Matrix42: Tätigkeitsarten nicht geladen ({e})")
            self.activity_types = []
        self.activity_types_loaded.emit(list(self.activity_types or m42_booking.ACTIVITY_TYPES))

    def _book(self, request):
        import m42_booking as mb
        self._wake.set()
        result = {"ok": False, "request": request}
        sent = False  # Buchung abgeschickt: danach ist bei einem Fehler unklar, ob sie angekommen ist
        try:
            ids = request.get("ids") or mb.DEFAULT_IDS
            number = mb.normalize_ticket(request.get("ticket", ""))
            if not number:
                raise mb.BookingError("Bitte eine Ticketnummer (TCK…) angeben.")
            with self._browser_lock:
                self._set_status(f"Matrix42: buche auf {number} …")
                found = self._fetch("POST", f"{mb.API}/WidgetList/GetData/{ids['ticket_list']}"
                                    "?pageSize=50&page=0", mb.ticket_query(number))
                ticket = mb.ticket_from_search(found if isinstance(found, list) else [], number)
                template = self._fetch("POST", f"{mb.API}/WidgetDialog/GetNewData/{ids['dialog']}",
                                       mb.new_data_body(ticket["id"]), "text/plain;charset=UTF-8")
                target, sla = mb.target_from_response(self._fetch(
                    "POST", f"{mb.API}/WidgetCommon/{ids['dialog']}/{ids['target_source']}"
                            "/custom_Target.ITMTimeEntryClassTarget", mb.target_body(ticket["id"])))
                entry = mb.time_entry((template or {}).get("Entity"), target, sla, self.user_id,
                                      request["start"], request["end"], request["minutes"],
                                      request.get("text", ""),
                                      request.get("activity_type", mb.DEFAULT_ACTIVITY_TYPE),
                                      goodwill=request.get("goodwill", False),
                                      travel=request.get("travel", False),
                                      goodwill_reason=request.get("goodwill_reason", ""),
                                      no_surcharge=request.get("no_surcharge", False),
                                      surcharge_reason=request.get("surcharge_reason", ""),
                                      goodwill_minutes=request.get("goodwill_minutes", 0),
                                      km_there=request.get("travel_km_there", 0),
                                      km_back=request.get("travel_km_back", 0))
                sent = True
                saved = self._fetch("POST", f"{mb.API}/WidgetDialog/UpdateData/{ids['dialog']}",
                                    mb.wrap(entry))
                result.update(ok=True, entry=mb.saved_entry(saved), ticket=ticket)
            self._set_status(f"Matrix42: gebucht ({result['entry']} auf {number})")
        except Exception as e:
            result["error"] = str(e)
            if sent:  # z. B. Zeitüberschreitung: Matrix42 kann trotzdem gebucht haben
                result["unclear"] = True
                result["error"] = f"unklar, ob gebucht wurde ({e}). Bitte zuerst in Matrix42 nachsehen."
            safe_io.log(f"Matrix42: Buchen fehlgeschlagen ({e!r})")
            self._set_status(f"Matrix42: Buchen fehlgeschlagen ({e})")
        finally:
            self._booking = False
        if sent:
            # Woche neu lesen, damit Zeile „Matrix42“ und Buchungsquote die Buchung zeigen
            day = request["start"].strftime("%Y-%m-%d")
            self._checked.discard(week_start(day))
            if week_start(day) == week_start(date.today().isoformat()):
                self._week_read = 0
            else:
                with self._lock:
                    self._wanted.add(week_start(day))
            self._wake.set()
        self.booking_done.emit(result)

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
        """Angemeldet, sobald die Matrix42-Seite ihr Anmelde-Token hat oder den Kalender zeigt.
        Nur "keine Anmeldeseite" reicht nicht: Während die Seite lädt oder zur Firmen-Anmeldung
        weiterleitet, sieht sie kurz so aus, und das Fenster ging zu, bevor man sich anmelden konnte."""
        try:
            return bool(self._evaluate(LOGIN_DONE_JS % json.dumps(urlsplit(self.page_url).hostname or ""),
                                       timeout=5))
        except Exception:
            return False
