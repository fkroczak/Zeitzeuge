"""
Outlook: Termine (auch Teams-Besprechungen) und gesendete Mails.

Gelesen wird über die COM-Schnittstelle des klassischen Outlook, und zwar in einem
eigenen PowerShell-Prozess (powershell.exe, ohne Fenster, mit Zeitlimit). So braucht
Zeitzeuge kein pywin32, und ein hängendes Outlook blockiert nie das Fenster.

Datensparsam: Das Skript gibt nur Betreff, Zeiten, Ort, "Teams ja/nein" und die
Domains der Teilnehmer bzw. Empfänger zurück (z. B. "kunde.de"). Vollständige
Adressen und Mailtexte verlassen den PowerShell-Prozess nie.

Ablage "outlook" in der Datenbank, je Tag {"termine": [...], "mails": [...], "gelesen": …}.
Jeder Lauf ersetzt die gelesenen Tage ganz (verschobene oder gelöschte Termine verschwinden).

Rein funktional bis auf run_powershell (Unterprozess) und outlook_installed (Registry).
"""

import base64
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta

import datastore
import safe_io

TIME_FMT = "%Y-%m-%d %H:%M:%S"
STORE_NAME = "outlook"

TYPE_APPOINTMENT = "Termin"
TYPE_MEETING = "Teams-Besprechung"
TYPE_MAIL = "Mail gesendet"
TYPES = (TYPE_APPOINTMENT, TYPE_MEETING, TYPE_MAIL)

MAX_ITEMS = 3000          # mehr Einträge je Ordner und Lauf liest das Skript nicht
PS_TIMEOUT = 90           # Sekunden, danach wird PowerShell beendet

# Fehlerkennungen aus dem Skript -> Text für die Statuszeile
ERRORS = {
    "nicht_geoeffnet": "Outlook ist nicht geöffnet. Zeitzeuge liest, sobald Outlook läuft.",
    "kein_outlook": "Klassisches Outlook nicht gefunden. Das neue Outlook hat keine "
                    "Schnittstelle, die Zeitzeuge lesen kann.",
    "zeitlimit": "Outlook hat nicht rechtzeitig geantwortet.",
    "kein_powershell": "PowerShell wurde nicht gefunden.",
    "nur_windows": "Outlook lässt sich nur unter Windows lesen.",
}


# ------------------------------------------------------------------ PowerShell-Skript

_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$inv = [Globalization.CultureInfo]::InvariantCulture
$out = [ordered]@{ ok = $false; fehler = ''; text = ''; eigene_domain = ''
                   termine = [System.Collections.ArrayList]::new()
                   mails = [System.Collections.ArrayList]::new()
                   kalender_fehler = ''; mails_fehler = '' }
function Dom($a) {
  if ($a -and ([string]$a) -match '@([A-Za-z0-9.-]+)\s*>?\s*$') { return $Matches[1].ToLower() }
  return ''
}
function Smtp($r) {
  try { $s = $r.PropertyAccessor.GetProperty('http://schemas.microsoft.com/mapi/proptag/0x39FE001E')
        if ($s) { return [string]$s } } catch {}
  try { $e = $r.AddressEntry
        if ($e -and $e.Type -eq 'EX') { $u = $e.GetExchangeUser(); if ($u) { return [string]$u.PrimarySmtpAddress } } } catch {}
  try { return [string]$r.Address } catch { return '' }
}
function Domains($recips) {
  $d = [ordered]@{}
  try { foreach ($r in $recips) { $x = Dom (Smtp $r); if ($x) { $d[$x] = 1 } } } catch {}
  return ,([string[]]@($d.Keys))
}
function Folder($ns, $path, $default) {
  if (-not $path) { return $ns.GetDefaultFolder($default) }
  $parts = $path.Trim('\').Split('\')
  $f = $ns.Folders.Item($parts[0])
  for ($i = 1; $i -lt $parts.Count; $i++) { $f = $f.Folders.Item($parts[$i]) }
  return $f
}
function T($d) { return $d.ToString('yyyy-MM-dd HH:mm:ss', $inv) }
try {
  $ol = $null
  try { $ol = [Runtime.InteropServices.Marshal]::GetActiveObject('Outlook.Application') } catch {}
  if (-not $ol) {
    if (__START__) {
      try { $ol = New-Object -ComObject Outlook.Application } catch { $out.fehler = 'kein_outlook'; $out.text = $_.Exception.Message }
    } else { $out.fehler = 'nicht_geoeffnet' }
  }
  if ($ol) {
    $ns = $ol.GetNamespace('MAPI')
    try { $me = $ns.CurrentUser.AddressEntry.GetExchangeUser(); if ($me) { $out.eigene_domain = Dom $me.PrimarySmtpAddress } } catch {}
    if (-not $out.eigene_domain) { try { $out.eigene_domain = Dom $ns.Accounts.Item(1).SmtpAddress } catch {} }
    $von = [datetime]::ParseExact('__VON__', 'yyyy-MM-dd HH:mm', $inv)
    $bis = [datetime]::ParseExact('__BIS__', 'yyyy-MM-dd HH:mm', $inv)
    if (__CAL__) {
      try {
        $cal = Folder $ns '__CALPATH__' 9
        $items = $cal.Items
        $items.Sort('[Start]')
        $items.IncludeRecurrences = $true
        $filter = "[Start] < '" + $bis.ToString('g') + "' AND [End] > '" + $von.ToString('g') + "'"
        $sel = $items.Restrict($filter)
        $it = $sel.GetFirst(); $n = 0
        while ($it -ne $null -and $n -lt __MAX__) {
          $n++
          try {
            if ($it.Start -ge $bis) { break }
            $loc = [string]$it.Location
            $teams = $loc -match 'teams'
            if (-not $teams) { try { $u = $it.PropertyAccessor.GetProperty('http://schemas.microsoft.com/mapi/string/{00020329-0000-0000-C000-000000000046}/SkypeTeamsMeetingUrl'); if ($u) { $teams = $true } } catch {} }
            if (-not $teams -and __BODY__) { try { $teams = ([string]$it.Body) -match 'teams\.microsoft\.com/l/meetup-join' } catch {} }
            [void]$out.termine.Add([ordered]@{
              start = T $it.Start; ende = T $it.End; betreff = [string]$it.Subject
              ort = $loc; teams = [bool]$teams; ganztags = [bool]$it.AllDayEvent
              status = [int]$it.MeetingStatus; belegt = [int]$it.BusyStatus
              privat = ([int]$it.Sensitivity -eq 2); domains = (Domains $it.Recipients) })
          } catch {}
          $it = $sel.GetNext()
        }
      } catch { $out.kalender_fehler = $_.Exception.Message }
    }
    if (__MAIL__) {
      try {
        $sent = Folder $ns '__SENTPATH__' 5
        $items = $sent.Items
        $items.Sort('[SentOn]', $true)
        $sel = $items.Restrict("[SentOn] >= '" + $von.ToString('g') + "'")
        $it = $sel.GetFirst(); $n = 0
        while ($it -ne $null -and $n -lt __MAX__) {
          $n++
          try {
            if ([int]$it.Class -eq 43 -and $it.SentOn -lt $bis) {
              $rc = 0; try { $rc = [int]$it.Recipients.Count } catch {}
              [void]$out.mails.Add([ordered]@{
                zeit = T $it.SentOn; betreff = [string]$it.Subject
                empfaenger = $rc; domains = (Domains $it.Recipients) })
            }
          } catch {}
          $it = $sel.GetNext()
        }
      } catch { $out.mails_fehler = $_.Exception.Message }
    }
    $out.ok = $true
  }
} catch { $out.fehler = 'fehler'; $out.text = $_.Exception.Message }
[Console]::Out.Write(($out | ConvertTo-Json -Depth 6 -Compress))
"""


def _ps_text(text):
    """Text für ein PowerShell-Literal in einfachen Anführungszeichen."""
    return str(text or "").replace("'", "''")


def build_script(start, end, calendar=True, mails=True, calendar_path="", sent_path="",
                 start_outlook=False, check_body=True, max_items=MAX_ITEMS):
    """PowerShell-Skript, das Termine und gesendete Mails in [start, end) als JSON ausgibt."""
    values = {
        "__VON__": start.strftime("%Y-%m-%d %H:%M"), "__BIS__": end.strftime("%Y-%m-%d %H:%M"),
        "__CAL__": "$true" if calendar else "$false", "__MAIL__": "$true" if mails else "$false",
        "__START__": "$true" if start_outlook else "$false",
        "__BODY__": "$true" if check_body else "$false",
        "__CALPATH__": _ps_text(calendar_path), "__SENTPATH__": _ps_text(sent_path),
        "__MAX__": str(int(max_items)),
    }
    script = _SCRIPT
    for key, value in values.items():
        script = script.replace(key, value)
    return script


def outlook_installed():
    """Ist das klassische Outlook (COM) registriert? Unter anderen Systemen False."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Outlook.Application\CLSID"):
            return True
    except OSError:
        return False


def run_powershell(script, timeout=PS_TIMEOUT):
    """Skript in powershell.exe ohne Fenster ausführen -> Ausgabe (Text).
    Wirft OSError (kein PowerShell) oder subprocess.TimeoutExpired."""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    exe = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                       r"System32\WindowsPowerShell\v1.0\powershell.exe")
    if not os.path.exists(exe):
        exe = "powershell.exe"
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run([exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                           "-EncodedCommand", encoded],
                          capture_output=True, timeout=timeout, creationflags=flags,
                          stdin=subprocess.DEVNULL)
    return proc.stdout.decode("utf-8", errors="replace")


def read_outlook(start, end, config, runner=None):
    """Outlook lesen (Unterprozess). -> Ergebnis wie parse_output, nie mit Ausnahme."""
    if runner is None:
        if sys.platform != "win32":
            return {"ok": False, "fehler": "nur_windows"}
        if not outlook_installed():
            return {"ok": False, "fehler": "kein_outlook"}
        runner = run_powershell
    script = build_script(
        start, end,
        calendar=config.get("outlook_calendar_enabled", True),
        mails=config.get("outlook_mails_enabled", True),
        calendar_path=config.get("outlook_calendar_folder", ""),
        sent_path=config.get("outlook_sent_folder", ""),
        start_outlook=config.get("outlook_start_if_closed", False),
        check_body=config.get("outlook_check_body", True))
    try:
        text = runner(script)
    except subprocess.TimeoutExpired:
        return {"ok": False, "fehler": "zeitlimit"}
    except OSError as e:
        return {"ok": False, "fehler": "kein_powershell", "text": str(e)}
    return parse_output(text)


# ------------------------------------------------------------------ Ausgabe prüfen

def _time(text):
    try:
        return datetime.strptime(str(text)[:19], TIME_FMT)
    except (TypeError, ValueError):
        return None


def _list(value):
    """PowerShell macht aus Listen mit einem Element gern das Element selbst."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _domains(value):
    result = []
    for d in _list(value):
        d = str(d or "").strip().lower().strip(".")
        if d and re.fullmatch(r"[a-z0-9.-]+\.[a-z0-9-]+", d) and d not in result:
            result.append(d)
    return result


def _text(value, limit=200):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def parse_output(text):
    """JSON-Ausgabe des Skripts -> {"ok", "fehler", "eigene_domain", "termine", "mails", …}.
    Kaputte Einträge fallen weg; unlesbare Ausgabe gibt ok=False."""
    text = (text or "").strip().lstrip("\ufeff")
    # Vor dem JSON können Warnungen stehen: ab der ersten "{" lesen
    if "{" in text:
        text = text[text.index("{"):]
    try:
        data = json.loads(text)
    except ValueError:
        return {"ok": False, "fehler": "fehler", "text": "Antwort von PowerShell unlesbar"}
    if not isinstance(data, dict):
        return {"ok": False, "fehler": "fehler", "text": "Antwort von PowerShell unlesbar"}
    result = {
        "ok": bool(data.get("ok")), "fehler": str(data.get("fehler") or ""),
        "text": _text(data.get("text"), 300),
        "eigene_domain": _domains(data.get("eigene_domain"))[:1],
        "kalender_fehler": _text(data.get("kalender_fehler"), 300),
        "mails_fehler": _text(data.get("mails_fehler"), 300),
        "termine": [], "mails": [],
    }
    for t in _list(data.get("termine")):
        if not isinstance(t, dict):
            continue
        start, end = _time(t.get("start")), _time(t.get("ende"))
        if not start or not end or end < start:
            continue
        result["termine"].append({
            "start": start.strftime(TIME_FMT), "end": end.strftime(TIME_FMT),
            "subject": _text(t.get("betreff")), "location": _location(t.get("ort")),
            "teams": bool(t.get("teams")), "all_day": bool(t.get("ganztags")),
            "canceled": _int(t.get("status")) in (5, 7),  # olMeetingCanceled, ...ReceivedAndCanceled
            "free": _int(t.get("belegt")) == 0,            # olFree
            "private": bool(t.get("privat")),
            "domains": _domains(t.get("domains")),
        })
    for m in _list(data.get("mails")):
        if not isinstance(m, dict):
            continue
        when = _time(m.get("zeit"))
        if not when:
            continue
        result["mails"].append({
            "start": when.strftime(TIME_FMT), "subject": _text(m.get("betreff")),
            "recipients": max(0, _int(m.get("empfaenger"))),
            "domains": _domains(m.get("domains")),
        })
    return result


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def _location(text):
    """Ort ohne Links (Teams-Einwahl, Zoom …), gekürzt."""
    text = re.sub(r"https?://\S+", "", str(text or ""))
    return _text(text.strip(" ;,"), 120)


# ------------------------------------------------------------------ eigene Domains

def own_domains(config, detected=None):
    """Domains der eigenen Firma: Einstellung, sonst die von Outlook erkannte."""
    text = config.get("outlook_own_domains") or []
    if isinstance(text, str):
        text = re.split(r"[\s,;]+", text)
    own = _domains([d.lstrip("@") for d in text])
    if not own and detected:
        own = _domains(detected)
    return own


def external(domains, own):
    """Domains ohne die eigenen (auch Subdomains wie mail.firma.de)."""
    own = [o.lower() for o in own]
    return [d for d in domains if not any(d == o or d.endswith("." + o) for o in own)]


# ------------------------------------------------------------------ Timeline-Einträge

def appointment_entry(item, own):
    """Termin aus der Ablage -> Timeline-Eintrag (oder None, wenn er nicht gezeigt wird)."""
    if item.get("all_day") or item.get("canceled"):
        return None
    domains = external(item.get("domains") or [], own)
    teams = bool(item.get("teams"))
    subject = "Privater Termin" if item.get("private") else (item.get("subject") or "(ohne Betreff)")
    details = []
    if item.get("location") and not item.get("private"):
        details.append(f"Ort: {item['location']}")
    if domains:
        details.append("Teilnehmer: " + ", ".join(domains))
    if item.get("free"):
        details.append("als frei eingetragen")
    return {
        "start": item["start"], "end": item["end"] if item["end"] > item["start"] else item["start"],
        "type": TYPE_MEETING if teams else TYPE_APPOINTMENT,
        "customer_name": subject,
        "details": " · ".join(details),
        "email_domains": [] if item.get("private") else domains,
        "outlook": "meeting" if teams else "appointment",
        "is_suggestion": True,
    }


def mail_entry(item, own, minutes=3, external_only=True):
    """Gesendete Mail -> kurzer Block in der Timeline (oder None)."""
    domains = external(item.get("domains") or [], own)
    if external_only and not domains:
        return None
    start = datetime.strptime(item["start"], TIME_FMT)
    end = start + timedelta(minutes=max(1, int(minutes or 1)))
    n = item.get("recipients") or 0
    target = ", ".join(domains) if domains else "intern"
    details = f"an {target}" + (f" ({n} Empfänger)" if n > 1 else "")
    return {
        "start": item["start"], "end": end.strftime(TIME_FMT),
        "type": TYPE_MAIL,
        "customer_name": item.get("subject") or "(ohne Betreff)",
        "details": details,
        "email_domains": domains,
        "outlook": "mail",
        "is_suggestion": True,
    }


def day_entries(doc, config):
    """Gespeicherter Tag -> Einträge für die Timeline (Termine und Mails)."""
    if not isinstance(doc, dict):
        return []
    own = own_domains(config, doc.get("eigene_domain"))
    result = []
    if config.get("outlook_calendar_enabled", True):
        for item in doc.get("termine") or []:
            try:
                e = appointment_entry(item, own)
            except (KeyError, TypeError, ValueError):
                continue
            if e:
                result.append(e)
    if config.get("outlook_mails_enabled", True):
        for item in doc.get("mails") or []:
            try:
                e = mail_entry(item, own, config.get("outlook_mail_minutes", 3),
                               config.get("outlook_mails_external_only", True))
            except (KeyError, TypeError, ValueError):
                continue
            if e:
                result.append(e)
    return sorted(result, key=lambda e: e["start"])


def split_days(result, start, end, now=None, calendar=True, mails=True):
    """Ergebnis eines Laufs -> {Tag: Dokument} für alle Tage in [start, end).

    Ein Termin über Mitternacht zählt zum Tag seines Beginns (wie bei VPN und Anrufen).
    Ist ein Ordner fehlgeschlagen oder nicht gelesen worden, fehlt sein Teil (None):
    der gespeicherte bleibt dann."""
    now = now or datetime.now()
    days = {}
    d = start.date()
    while datetime.combine(d, datetime.min.time()) < end:
        days[d.isoformat()] = {"termine": [], "mails": []}
        d += timedelta(days=1)
    for t in result.get("termine", []):
        if t["start"][:10] in days:
            days[t["start"][:10]]["termine"].append(t)
    for m in result.get("mails", []):
        if m["start"][:10] in days:
            days[m["start"][:10]]["mails"].append(m)
    stamp = now.strftime(TIME_FMT)
    for doc in days.values():
        doc["gelesen"] = stamp
        doc["eigene_domain"] = result.get("eigene_domain") or []
        if result.get("kalender_fehler") or not calendar:
            doc["termine"] = None
        if result.get("mails_fehler") or not mails:
            doc["mails"] = None
    return days


# ------------------------------------------------------------------ Ablage

def _store(path):
    return datastore.locate(path, "days")


def save_days(path, days):
    """Gelesene Tage ersetzen. Ein fehlender Teil (None) behält den gespeicherten."""
    try:
        store, name = _store(path)
        by_day = {}
        for day, doc in days.items():
            old = store.get(name, day) or {}
            new = dict(doc)
            for part in ("termine", "mails"):
                if new.get(part) is None:
                    new[part] = old.get(part) if isinstance(old, dict) else []
                    new[part] = new[part] if isinstance(new[part], list) else []
            if old != new:
                by_day[day] = new
        if by_day:
            store.put_many(name, by_day)
        return list(by_day)
    except (datastore.Busy, datastore.Locked) as e:
        safe_io.report(f"Outlook: Speichern fehlgeschlagen ({e})")
        return []


def load_day(path, day):
    try:
        store, name = _store(path)
        doc = store.get(name, day)
    except (datastore.Busy, datastore.Locked):
        return None
    return doc if isinstance(doc, dict) else None


def status_text(result, now=None):
    """Kurzer Text für Statuszeile und Dialog."""
    now = now or datetime.now()
    if not result.get("ok"):
        code = result.get("fehler") or "fehler"
        text = ERRORS.get(code) or f"Outlook nicht lesbar: {result.get('text') or 'unbekannter Fehler'}"
        return f"Outlook: {text}" if not text.startswith("Outlook") else text
    parts = [f"Outlook gelesen {now:%H:%M}"]
    parts.append(f"{len(result.get('termine', []))} Termine, {len(result.get('mails', []))} Mails")
    if result.get("kalender_fehler"):
        parts.append("Kalender nicht lesbar")
    if result.get("mails_fehler"):
        parts.append("Gesendete Elemente nicht lesbar")
    return " · ".join(parts)
