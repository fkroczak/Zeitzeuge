"""
Mitschnitt: aufzeichnen, welche Abfragen eine Webseite an ihren Server schickt.

Damit lässt sich prüfen, ob Zeitzeuge die Daten (3CX-Anrufe, ITM-Personalzeiten)
später direkt abfragen kann, ohne die Seite in Edge offen zu halten.

Aufgezeichnet werden nur Datenabfragen (XHR/fetch), Seitenaufrufe und Websockets,
keine Bilder, Skripte oder Schriften. Geschwärzt werden:
- Passwörter, Token, Codes und ähnliche Felder in Adressen, Formularen und JSON,
- Werte von Cookies und des Authorization-Kopfs (Name, Länge und Ablauf bleiben),
- alles, was wie ein JWT aussieht (nur Ablaufzeit und Feldnamen bleiben).
Antworten werden gekürzt: Listen auf die ersten Einträge, lange Texte auf 300 Zeichen.
"""

import base64
import json
import re
import time
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import websocket  # Paket websocket-client

SECRET_NAME = re.compile(
    r"pass|pwd|secret|token|otp|code|auth|session|sid|key|cookie|jwt|bearer|credential|pin",
    re.I)
JWT = re.compile(r"eyJ[\w-]{5,}\.[\w-]{5,}\.[\w-]*")
DATA_TYPES = {"XHR", "Fetch", "Document", "EventSource", "Other", "Preflight"}
BODY_TYPES = {"XHR", "Fetch", "Other"}
MAX_TEXT = 300
MAX_ITEMS = 3
MAX_PROTO_ITEMS = 200  # Protobuf-Texte sind maskiert, ganze Listen helfen beim Zuordnen der Felder


def _jwt_info(token):
    """Ablauf und Feldnamen eines JWT, ohne Inhalt."""
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError):
        return None
    if not isinstance(claims, dict):
        return None
    info = {"felder": sorted(claims)}
    for key in ("iat", "nbf", "exp", "auth_time"):
        if isinstance(claims.get(key), (int, float)):
            info[key] = datetime.fromtimestamp(claims[key]).isoformat(timespec="seconds")
    if isinstance(claims.get("exp"), (int, float)) and isinstance(claims.get("iat"), (int, float)):
        info["gueltig_minuten"] = round((claims["exp"] - claims["iat"]) / 60)
    return info


def describe_secret(value):
    """Geheimen Wert durch eine Beschreibung ersetzen (Länge, bei JWT der Ablauf)."""
    text = str(value)
    desc = {"geschwaerzt": True, "laenge": len(text)}
    if text.lower().startswith("bearer "):
        desc["art"] = "Bearer"
        text = text[7:]
    match = JWT.search(text)
    if match:
        desc["jwt"] = _jwt_info(match.group(0))
    return desc


def redact_text(text):
    """JWTs in freiem Text schwärzen."""
    return JWT.sub(lambda m: f"<JWT geschwärzt, {json.dumps(_jwt_info(m.group(0)))}>", text)


def _short(text):
    text = redact_text(text)
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + f" … ({len(text)} Zeichen)"


def redact_json(value, depth=0):
    """JSON verkleinern und Geheimnisse schwärzen. Die Struktur bleibt erkennbar."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if SECRET_NAME.search(str(key)) and isinstance(item, (str, int, float)) and item != "":
                out[key] = describe_secret(item)
            else:
                out[key] = redact_json(item, depth + 1)
        return out
    if isinstance(value, list):
        out = [redact_json(item, depth + 1) for item in value[:MAX_ITEMS]]
        if len(value) > MAX_ITEMS:
            out.append(f"… {len(value) - MAX_ITEMS} weitere (insgesamt {len(value)})")
        return out
    if isinstance(value, str):
        return _short(value)
    return value


def redact_query(query):
    pairs = [(k, "<geschwaerzt>" if SECRET_NAME.search(k) and v else redact_text(v))
             for k, v in parse_qsl(query, keep_blank_values=True)]
    return urlencode(pairs, safe="<>/:,")


def redact_url(url):
    parts = urlsplit(url)
    fragment = parts.fragment
    if "=" in fragment:  # z. B. #access_token=… nach einer Microsoft-Anmeldung
        path, _, query = fragment.partition("?") if "?" in fragment else ("", "", fragment)
        fragment = (path + "?" if path else "") + redact_query(query)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, redact_query(parts.query), fragment))


def _cookie_names(header):
    return [part.split("=", 1)[0].strip() for part in header.split(";") if part.strip()]


def _set_cookie(header):
    """Set-Cookie ohne Wert: Name und Merkmale (Ablauf, HttpOnly …)."""
    result = []
    for line in header.split("\n"):
        parts = [p.strip() for p in line.split(";")]
        if not parts or "=" not in parts[0]:
            continue
        result.append({"name": parts[0].split("=", 1)[0], "merkmale": [
            p for p in parts[1:] if p]})
    return result


def redact_headers(headers):
    out = {}
    for name, value in (headers or {}).items():
        low = name.lower()
        if low == "cookie":
            out[name] = {"cookies": _cookie_names(value)}
        elif low == "set-cookie":
            out[name] = _set_cookie(value)
        elif low.startswith(":"):
            continue  # HTTP/2-Pseudoköpfe wiederholen nur Adresse und Methode
        elif SECRET_NAME.search(low) and low not in ("access-control-allow-credentials",):
            out[name] = describe_secret(value)
        else:
            out[name] = _short(str(value))
    return out


def summarize_body(body, mime=""):
    """Anfrage- oder Antwortinhalt kürzen und schwärzen."""
    if body is None or body == "":
        return None
    text = body.strip() if isinstance(body, str) else str(body)
    if text[:1] in "[{":
        try:
            return {"json": redact_json(json.loads(text))}
        except ValueError:
            pass
    if "x-www-form-urlencoded" in mime or (re.fullmatch(r"[\w.%+\-]+=[^\s]*(&[\w.%+\-]+=[^\s]*)*", text)
                                          and len(text) < 5000):
        return {"formular": redact_query(text)}
    return {"text": _short(text)}


def mask_text(text):
    """Inhalt unkenntlich machen, Form behalten: Buchstaben -> x/X, Ziffern -> 9.
    So bleibt erkennbar, ob ein Feld ein Name, eine Rufnummer oder ein Datum ist."""
    return "".join("9" if c.isdigit() else ("X" if c.isupper() else "x") if c.isalpha() else c
                   for c in text)


def _varint(buf, pos):
    value = shift = 0
    while True:
        if pos >= len(buf) or shift > 63:
            raise ValueError("varint")
        b = buf[pos]
        pos += 1
        value |= (b & 0x7F) << shift
        shift += 7
        if not b & 0x80:
            return value, pos


def _proto_fields(buf, depth):
    """Protobuf ohne Schema zerlegen. Fehler, wenn buf keine gültige Nachricht ist."""
    fields, pos = [], 0
    while pos < len(buf):
        key, pos = _varint(buf, pos)
        field, wire = key >> 3, key & 7
        if field == 0:
            raise ValueError("feld 0")
        if wire == 0:
            value, pos = _varint(buf, pos)
        elif wire == 1:
            if pos + 8 > len(buf):
                raise ValueError("fixed64")
            value, pos = {"fixed64": int.from_bytes(buf[pos:pos + 8], "little")}, pos + 8
        elif wire == 5:
            if pos + 4 > len(buf):
                raise ValueError("fixed32")
            value, pos = {"fixed32": int.from_bytes(buf[pos:pos + 4], "little")}, pos + 4
        elif wire == 2:
            size, pos = _varint(buf, pos)
            if pos + size > len(buf):
                raise ValueError("länge")
            value, pos = _proto_value(buf[pos:pos + size], depth + 1), pos + size
        else:
            raise ValueError("wiretype")
        fields.append((field, value))
    return fields


def _proto_value(data, depth):
    if data and depth < 12:
        try:
            return _proto_group(_proto_fields(data, depth))
        except ValueError:
            pass
    try:
        text = data.decode("utf-8")
        if text.isprintable():
            return {"text": mask_text(text)} if text else ""
    except UnicodeDecodeError:
        pass
    return {"bytes": len(data)}


def _proto_group(fields):
    """Felder nach Nummer zusammenfassen; wiederholte Felder auf die ersten Einträge kürzen."""
    out = {}
    for field, value in fields:
        out.setdefault(str(field), []).append(value)
    for key, values in out.items():
        if len(values) == 1:
            out[key] = values[0]
        elif len(values) > MAX_PROTO_ITEMS:
            out[key] = values[:MAX_PROTO_ITEMS] + [
                f"… {len(values) - MAX_PROTO_ITEMS} weitere (insgesamt {len(values)})"]
    return out


def summarize_binary(data):
    """Binären Inhalt beschreiben. Protobuf wird mit Feldnummern zerlegt, Texte maskiert."""
    if not data:
        return None
    try:
        return {"protobuf": _proto_group(_proto_fields(data, 0)), "bytes": len(data)}
    except ValueError:
        return {"text": f"<{len(data)} Bytes binär>"}


def _post_bytes(req):
    """Binären Anfrageinhalt als Bytes (postDataEntries sind verlustfrei, postData nicht)."""
    entries = req.get("postDataEntries") or []
    if entries and all("bytes" in e for e in entries):
        return b"".join(base64.b64decode(e["bytes"]) for e in entries)
    text = req.get("postData") or ""
    try:
        return text.encode("latin-1")
    except UnicodeEncodeError:
        return text.encode("utf-8")


SKIP_BODY = re.compile(r"wasm|image/|font/|javascript|css", re.I)


class Recorder:
    """Hört über das DevTools-Protokoll an einer Seite mit und sammelt die Abfragen."""

    SNAPSHOT_EVERY = 5  # Sekunden: Cookies und Seitenspeicher festhalten

    def __init__(self, ws_url, start_url, name):
        self.ws = websocket.create_connection(ws_url, timeout=15, suppress_origin=True)
        self.start_url = start_url
        self.name = name
        self.entries = {}       # requestId -> Eintrag (laufend)
        self.done = []          # fertige Einträge in Reihenfolge
        self.extra_req = {}     # requestId -> echte Anfrage-Köpfe (mit Cookie)
        self.extra_resp = {}    # requestId -> echte Antwort-Köpfe (mit Set-Cookie)
        self.others = {}        # Anzahl übriger Dateien je Typ
        self.websockets = []
        self.cookies = []
        self.storage = {}
        self.pages = []
        self._id = 0
        self._pending = {}      # Befehls-ID -> (Art, requestId)
        self._started = time.time()

    # -------------------------------------------------------------- Protokoll

    def _send(self, method, kind=None, ref=None, **params):
        self._id += 1
        self.ws.send(json.dumps({"id": self._id, "method": method, "params": params}))
        if kind:
            self._pending[self._id] = (kind, ref)
        return self._id

    def run(self, stop_event, max_seconds=1800):
        """Aufzeichnen, bis die Seite geschlossen wird, stop_event gesetzt ist oder die Zeit um ist."""
        self._send("Network.enable", maxPostDataSize=65536)
        self._send("Network.setCacheDisabled", cacheDisabled=True)
        self._send("Page.enable")
        self._send("Page.navigate", url=self.start_url)
        self.ws.settimeout(1)
        last_snapshot = 0
        deadline = time.time() + max_seconds
        while not stop_event.is_set() and time.time() < deadline:
            if time.time() - last_snapshot > self.SNAPSHOT_EVERY:
                last_snapshot = time.time()
                self._snapshot()
            try:
                msg = json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException:
                continue
            except (websocket.WebSocketException, OSError, ValueError):
                break  # Fenster geschlossen
            if "id" in msg:
                self._on_reply(msg)
            else:
                self._on_event(msg.get("method"), msg.get("params") or {})
        self._final_snapshot()
        try:
            self.ws.close()
        except Exception:
            pass

    def _snapshot(self):
        try:
            self._send("Network.getAllCookies", kind="cookies")
            self._send("Runtime.evaluate", kind="storage", returnByValue=True, expression=STORAGE_JS)
        except (websocket.WebSocketException, OSError):
            pass

    def _final_snapshot(self):
        """Ein letztes Mal Cookies und Speicher holen (klappt nur, solange die Seite noch offen ist)."""
        try:
            self._snapshot()
            end = time.time() + 3
            self.ws.settimeout(1)
            while self._pending and time.time() < end:
                msg = json.loads(self.ws.recv())
                if "id" in msg:
                    self._on_reply(msg)
                else:
                    self._on_event(msg.get("method"), msg.get("params") or {})
        except Exception:
            pass

    def _on_reply(self, msg):
        kind, ref = self._pending.pop(msg["id"], (None, None))
        result = msg.get("result") or {}
        if kind == "body" and ref in self.entries:
            entry = self.entries.pop(ref)
            body = result.get("body")
            mime = entry.get("typ_inhalt") or ""
            if body is not None and result.get("base64Encoded"):
                entry["antwort"] = summarize_binary(base64.b64decode(body))
            elif body and ("octet-stream" in mime or "protobuf" in mime):
                entry["antwort"] = summarize_binary(body.encode("latin-1", "replace"))
            elif body and ("html" in mime or "javascript" in mime):  # Seiten und Code nicht speichern
                entry["antwort"] = {"text": f"<{mime}, {len(body)} Zeichen>"}
            else:
                entry["antwort"] = summarize_body(body, mime)
            self.done.append(entry)
        elif kind == "cookies" and "cookies" in result:
            self.cookies = [{
                "name": c.get("name"), "domain": c.get("domain"), "pfad": c.get("path"),
                "laeuft_ab": (datetime.fromtimestamp(c["expires"]).isoformat(timespec="seconds")
                              if c.get("expires", -1) > 0 else "Sitzung"),
                "httpOnly": c.get("httpOnly"), "secure": c.get("secure"),
                "sameSite": c.get("sameSite"), "laenge": len(c.get("value") or ""),
                **cookie_shape(c.get("value") or ""),
            } for c in result["cookies"]]
        elif kind == "storage":
            value = (result.get("result") or {}).get("value")
            try:
                data = json.loads(value) if value else None
            except ValueError:
                data = None
            if data:
                self.storage = summarize_storage(data)

    def _entry(self, rid, params):
        req = params.get("request") or {}
        entry = {
            "zeit": datetime.fromtimestamp(params.get("wallTime") or time.time()).isoformat(
                timespec="seconds"),
            "typ": params.get("type"),
            "methode": req.get("method"),
            "adresse": redact_url(req.get("url", "")),
            "anfrage_koepfe": redact_headers(req.get("headers")),
        }
        if req.get("postData") is not None or req.get("hasPostData"):
            ctype = next((v for k, v in (req.get("headers") or {}).items()
                          if k.lower() == "content-type"), "")
            if "octet-stream" in ctype or "protobuf" in ctype:
                entry["anfrage_inhalt"] = summarize_binary(_post_bytes(req)) or "<nicht gelesen>"
            else:
                entry["anfrage_inhalt"] = summarize_body(req.get("postData"), ctype) or "<nicht gelesen>"
        return entry

    def _finish(self, rid, extra=None):
        entry = self.entries.pop(rid, None)
        if entry is None:
            return
        if extra:
            entry.update(extra)
        self._merge_extra(rid, entry)
        self.done.append(entry)

    def _merge_extra(self, rid, entry):
        if rid in self.extra_req:
            entry["anfrage_koepfe"] = {**entry.get("anfrage_koepfe", {}),
                                       **redact_headers(self.extra_req.pop(rid))}
        if rid in self.extra_resp:
            entry["antwort_koepfe"] = {**entry.get("antwort_koepfe", {}),
                                       **redact_headers(self.extra_resp.pop(rid))}

    def _on_event(self, method, params):
        rid = params.get("requestId")
        if method == "Network.requestWillBeSent":
            kind = params.get("type") or "Other"
            redirect = params.get("redirectResponse")
            if redirect and rid in self.entries:  # Weiterleitung: alter Schritt ist fertig
                self._finish(rid, {"status": redirect.get("status"),
                                   "antwort_koepfe": redact_headers(redirect.get("headers")),
                                   "weitergeleitet": True})
            if kind not in DATA_TYPES:
                self.others[kind] = self.others.get(kind, 0) + 1
                return
            self.entries[rid] = self._entry(rid, params)
        elif method == "Network.requestWillBeSentExtraInfo":
            self.extra_req[rid] = params.get("headers") or {}
        elif method == "Network.responseReceivedExtraInfo":
            self.extra_resp[rid] = params.get("headers") or {}
        elif method == "Network.responseReceived" and rid in self.entries:
            resp = params.get("response") or {}
            self.entries[rid].update({
                "status": resp.get("status"),
                "typ_inhalt": resp.get("mimeType"),
                "antwort_koepfe": redact_headers(resp.get("headers")),
            })
        elif method == "Network.loadingFinished" and rid in self.entries:
            entry = self.entries[rid]
            self._merge_extra(rid, entry)
            if entry.get("typ") in BODY_TYPES and not SKIP_BODY.search(entry.get("typ_inhalt") or ""):
                self._send("Network.getResponseBody", kind="body", ref=rid, requestId=rid)
            else:
                self._finish(rid)
        elif method == "Network.loadingFailed" and rid in self.entries:
            self._finish(rid, {"fehler": params.get("errorText")})
        elif method == "Network.webSocketCreated":
            self.websockets.append({"zeit": datetime.now().isoformat(timespec="seconds"),
                                    "adresse": redact_url(params.get("url", ""))})
        elif method == "Page.frameNavigated" and not (params.get("frame") or {}).get("parentId"):
            self.pages.append(redact_url((params.get("frame") or {}).get("url", "")))

    # -------------------------------------------------------------- Ergebnis

    def result(self, browser=""):
        for rid in list(self.entries):  # noch offene Abfragen (z. B. Fenster mittendrin zu)
            self._finish(rid, {"unvollstaendig": True})
        return {
            "mitschnitt": self.name,
            "erstellt": datetime.now().isoformat(timespec="seconds"),
            "dauer_sekunden": round(time.time() - self._started),
            "browser": browser,
            "start_adresse": redact_url(self.start_url),
            "hinweis": "Passwörter, Token und Cookie-Werte sind geschwärzt. Antworten sind gekürzt.",
            "aufgerufene_seiten": self.pages,
            "abfragen": self.done,
            "websockets": self.websockets,
            "andere_dateien": self.others,
            "cookies": self.cookies,
            "seitenspeicher": self.storage,
        }


def cookie_shape(value):
    """Aufbau eines Cookie-Werts ohne Inhalt: JWT-Ablauf oder Feldnamen, falls JSON/Base64-JSON."""
    from urllib.parse import unquote
    match = JWT.search(value)
    if match:
        return {"jwt": _jwt_info(match.group(0))}
    for text in (unquote(value), value):
        candidates = [text]
        try:
            candidates.append(base64.urlsafe_b64decode(text + "=" * (-len(text) % 4)).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            pass
        for cand in candidates:
            try:
                data = json.loads(cand)
            except ValueError:
                continue
            if isinstance(data, dict):
                info = {"json_felder": sorted(data)[:40]}
                inner = JWT.search(cand)
                if inner:
                    info["jwt"] = _jwt_info(inner.group(0))
                return info
    return {}


# Schlüssel aus localStorage/sessionStorage (dort legen viele Web-Apps ihr Token ab)
STORAGE_JS = """JSON.stringify((() => {
  const read = (s) => { const o = {}; try { for (let i = 0; i < s.length; i++) {
    const k = s.key(i); o[k] = s.getItem(k); } } catch (e) {} return o; };
  return {adresse: location.href, localStorage: read(localStorage), sessionStorage: read(sessionStorage)};
})())"""


def summarize_storage(data):
    """Speicherinhalt der Seite ohne Werte: Schlüssel, Länge, bei JSON die Feldnamen, bei JWT der Ablauf."""
    out = {"adresse": redact_url(data.get("adresse", ""))}
    for area in ("localStorage", "sessionStorage"):
        items = {}
        for key, value in (data.get(area) or {}).items():
            value = value or ""
            info = {"laenge": len(value)}
            match = JWT.search(value)
            if match:
                info["jwt"] = _jwt_info(match.group(0))
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    info["felder"] = sorted(parsed)[:40]
                    for k, v in parsed.items():  # Ablaufzeiten sind nützlich und nicht geheim
                        if re.search(r"expir|exp$|valid|until", k, re.I) and isinstance(v, (int, float, str)):
                            info.setdefault("ablauf", {})[k] = v
            except ValueError:
                pass
            items[key] = info
        out[area] = items
    return out
