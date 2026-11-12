"""Updates: neue Version suchen, Setup laden, prüfen und still installieren (ohne Qt).

Die Setups kommen aus den Releases des (privaten) Repos fkroczak/Zeitzeuge, die die CI bei
jedem Merge in main anlegt (.github/workflows/build.yml).

Die EXE bringt ein Lese-Token mit: ZeitZeuge.spec schreibt es beim Bauen aus dem Secret
UPDATE_READ_TOKEN in build_info.py (UPDATE = {"repo": ..., "token": ...}). Es darf das Repo nur
lesen. Wer es aus der EXE holt, kann damit auch den Quellcode lesen (bewusst in Kauf genommen:
Zeitzeuge wird nur intern genutzt). Sperren lässt es sich jederzeit auf GitHub.
Aus dem Quelltext: ZEITZEUGE_UPDATE_REPO und ZEITZEUGE_UPDATE_TOKEN.

Ablauf: latest() fragt das neueste Release ab, download() lädt Zeitzeuge-Setup.exe und prüft
SHA-256, signature_ok() die Signatur (nur wenn die laufende EXE selbst signiert ist),
start_setup() startet das Setup still; Zeitzeuge beendet sich danach und das Setup startet es neu.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

API = "https://api.github.com"
DEFAULT_REPO = "fkroczak/Zeitzeuge"
ASSET = "Zeitzeuge-Setup.exe"
CHECK_HOURS = 6          # so oft sucht Zeitzeuge im Hintergrund
TOKEN_WARN_DAYS = 30     # so lange vor Ablauf des Tokens warnt Zeitzeuge


class UpdateError(Exception):
    """Fehler mit einem Satz für die Anzeige (ohne Token, ohne Adressen mit Zugangsdaten)."""


def settings():
    """(Repo, Token) aus build_info.py bzw. der Umgebung; Token leer = nicht eingerichtet."""
    repo = os.environ.get("ZEITZEUGE_UPDATE_REPO", "").strip()
    token = os.environ.get("ZEITZEUGE_UPDATE_TOKEN", "").strip()
    if not token:
        try:
            import build_info  # beim Bauen erzeugt (ZeitZeuge.spec)
            update = getattr(build_info, "UPDATE", {}) or {}
            repo = repo or str(update.get("repo") or "").strip()
            token = str(update.get("token") or "").strip()
        except ImportError:
            pass
    return repo or DEFAULT_REPO, token


def parse_version(text):
    """"v4.1.3" oder "4.1.3" -> (4, 1, 3); sonst None."""
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", (text or "").strip())
    return tuple(int(n) for n in m.groups()) if m else None


def is_newer(remote, local):
    """True, wenn remote (z. B. "v4.1.9") neuer ist als local ("4.1.3")."""
    r, l = parse_version(remote), parse_version(local)
    return bool(r and l and r > l)


def _request(url, token, accept="application/vnd.github+json"):
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "Zeitzeuge-Updater",
                                               "X-GitHub-Api-Version": "2022-11-28"})
    # Nicht weiterreichen: GitHub leitet Downloads auf einen Speicher um, der ein zweites
    # Anmeldeverfahren ablehnt (und dort hat das Token nichts zu suchen)
    req.add_unredirected_header("Authorization", f"Bearer {token}")
    return req


def _http_error(e):
    if e.code == 401:
        return UpdateError("Update-Zugang abgelaufen oder gesperrt. Bitte das neueste Setup von Hand holen.")
    if e.code in (403, 429):
        return UpdateError("GitHub lässt gerade keine Abfrage zu. Später noch einmal versuchen.")
    if e.code == 404:
        return UpdateError("Noch kein Update veröffentlicht (oder kein Zugriff auf das Repository).")
    return UpdateError(f"GitHub antwortet mit Fehler {e.code}.")


def token_days_left(header, now=None):
    """Tage bis zum Ablauf des Tokens aus dem Kopf github-authentication-token-expiration
    ("2027-01-01 00:00:00 UTC"); None, wenn es nicht abläuft oder der Kopf fehlt."""
    if not header:
        return None
    try:
        when = datetime.strptime(header.replace(" UTC", "").strip()[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    return (when - now).days


def latest(repo, token, timeout=15, opener=urllib.request.urlopen):
    """Neuestes Release: {"version", "tag", "url", "size", "sha256", "token_days"}.
    UpdateError bei Fehlern, auch wenn das Setup im Release fehlt."""
    if not token:
        raise UpdateError("Updates sind in dieser Version nicht eingerichtet.")
    try:
        with opener(_request(f"{API}/repos/{repo}/releases/latest", token), timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            expires = resp.headers.get("github-authentication-token-expiration")
    except urllib.error.HTTPError as e:
        raise _http_error(e) from None
    except (urllib.error.URLError, OSError, ValueError):
        raise UpdateError("GitHub nicht erreichbar.") from None
    tag = str(data.get("tag_name") or "")
    if not parse_version(tag):
        raise UpdateError(f"Unbekannte Versionsangabe im Release: {tag[:30]!r}")
    assets = {a.get("name"): a for a in data.get("assets") or []}
    setup = assets.get(ASSET)
    if not setup:
        raise UpdateError(f"Im Release {tag} fehlt {ASSET}.")
    # SHA-256: GitHub nennt sie selbst ("digest"), sonst die Datei .sha256 aus der CI
    sha = str(setup.get("digest") or "")
    sha = sha.split(":", 1)[1] if sha.startswith("sha256:") else ""
    side = assets.get(ASSET + ".sha256")
    if not sha and side:
        try:
            with opener(_request(side["url"], token, "application/octet-stream"), timeout=timeout) as resp:
                sha = resp.read(200).decode("ascii", "replace").split()[0]
        except (urllib.error.URLError, OSError, IndexError, KeyError):
            sha = ""
    return {"version": tag.lstrip("v"), "tag": tag, "url": setup.get("url", ""),
            "size": int(setup.get("size") or 0), "sha256": sha.lower(),
            "token_days": token_days_left(expires)}


def download(info, token, folder, progress=None, cancelled=None, timeout=30,
             opener=urllib.request.urlopen):
    """Setup nach folder laden und SHA-256 prüfen; Pfad zurück. progress(geladen, gesamt)."""
    if not re.fullmatch(r"[0-9a-f]{64}", info.get("sha256") or ""):
        raise UpdateError("Prüfsumme des Setups fehlt, Update abgebrochen.")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"Zeitzeuge-Setup-{info['version']}.exe")
    part = path + ".part"
    digest = hashlib.sha256()
    done = 0
    try:
        with opener(_request(info["url"], token, "application/octet-stream"), timeout=timeout) as resp, \
                open(part, "wb") as f:
            total = int(resp.headers.get("Content-Length") or info.get("size") or 0)
            while True:
                if cancelled and cancelled():
                    raise UpdateError("Abgebrochen.")
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    except urllib.error.HTTPError as e:
        _remove(part)
        raise _http_error(e) from None
    except UpdateError:
        _remove(part)
        raise
    except (urllib.error.URLError, OSError):
        _remove(part)
        raise UpdateError("Download abgebrochen (Verbindung oder Speicherplatz).") from None
    if digest.hexdigest() != info["sha256"]:
        _remove(part)
        raise UpdateError("Das geladene Setup ist beschädigt (Prüfsumme passt nicht).")
    os.replace(part, path)
    return path


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _signer(path):
    """Windows: (Status, Aussteller-Name) der Authenticode-Signatur einer Datei."""
    script = ("$s = Get-AuthenticodeSignature -LiteralPath $env:ZZ_FILE; "
              "Write-Output $s.Status; Write-Output $s.SignerCertificate.Subject")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                             capture_output=True, text=True, timeout=60,
                             env=dict(os.environ, ZZ_FILE=path),
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return "", ""
    lines = (out.stdout or "").splitlines() + ["", ""]
    return lines[0].strip(), lines[1].strip()


def signature_ok(setup, reference=None, signer=_signer):
    """Ist das Setup gültig signiert, vom selben Herausgeber wie die laufende EXE?
    Ist die laufende EXE selbst nicht signiert (Build ohne Zertifikat), zählt nur die Prüfsumme."""
    if sys.platform != "win32" and signer is _signer:
        return True
    reference = reference or sys.executable
    ref_status, ref_subject = signer(reference)
    if ref_status != "Valid":
        return True
    status, subject = signer(setup)
    return status == "Valid" and subject == ref_subject


def setup_args(minimized):
    """Befehlszeile des Setups: still, ohne Rückfragen; danach startet es Zeitzeuge neu."""
    return ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
            f"/ZZUPDATE={'min' if minimized else 'show'}"]


def start_setup(path, minimized=False):
    """Setup unabhängig von Zeitzeuge starten (es wartet, bis Zeitzeuge beendet ist)."""
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([path, *setup_args(minimized)], close_fds=True, creationflags=flags)


def cleanup(folder, keep=None):
    """Alte geladene Setups löschen (nach einem Update liegen sie sonst ewig herum)."""
    try:
        names = os.listdir(folder)
    except OSError:
        return
    for name in names:
        if name.startswith("Zeitzeuge-Setup-") and os.path.join(folder, name) != keep:
            _remove(os.path.join(folder, name))
