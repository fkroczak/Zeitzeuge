"""Updates (src/updater.py): Versionen vergleichen, Release lesen, Setup laden und prüfen.

Ohne Netz: urlopen wird durch eine Attrappe ersetzt, die die Anfragen mitschreibt.
"""
import hashlib
import io
import json
import os
import sys
import urllib.error

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import updater  # noqa: E402

SETUP = b"MZ" + b"\x00" * 300_000
SHA = hashlib.sha256(SETUP).hexdigest()


class Resp(io.BytesIO):
    def __init__(self, body, headers=None):
        super().__init__(body)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        self.close()


class FakeGitHub:
    """Antwortet je Adresse; merkt sich die Anfragen (für die Kopfzeilen)."""

    def __init__(self, routes):
        self.routes = routes
        self.requests = []

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        answer = self.routes[req.full_url]
        if isinstance(answer, Exception):
            raise answer
        return answer()


def release(tag="v4.1.9", digest=True, setup=True):
    asset = {"name": "Zeitzeuge-Setup.exe", "url": "https://api.github.com/assets/1", "size": len(SETUP)}
    if digest:
        asset["digest"] = f"sha256:{SHA}"
    assets = [asset] if setup else []
    assets.append({"name": "Zeitzeuge-Setup.exe.sha256", "url": "https://api.github.com/assets/2"})
    return json.dumps({"tag_name": tag, "assets": assets}).encode()


LATEST = f"{updater.API}/repos/o/r/releases/latest"


def test_versionen_vergleichen():
    assert updater.parse_version("v4.1.3") == (4, 1, 3)
    assert updater.parse_version("4.1.3-test186") is None
    assert updater.is_newer("v4.1.10", "4.1.9")
    assert updater.is_newer("v4.2.0", "4.1.30")
    assert not updater.is_newer("v4.1.3", "4.1.3")
    assert not updater.is_newer("v4.1.2", "4.1.3")
    assert not updater.is_newer("kaputt", "4.1.3")


def test_neuestes_release_mit_token():
    gh = FakeGitHub({LATEST: lambda: Resp(release(), {
        "github-authentication-token-expiration": "2099-01-01 00:00:00 UTC"})})
    info = updater.latest("o/r", "geheim", opener=gh)
    assert info["version"] == "4.1.9" and info["sha256"] == SHA
    assert info["url"] == "https://api.github.com/assets/1"
    assert info["token_days"] > 1000
    req = gh.requests[0]
    # Token nur für GitHub selbst, nicht für Umleitungen (Download-Speicher)
    assert req.unredirected_hdrs.get("Authorization") == "Bearer geheim"
    assert "Authorization" not in req.headers


def test_pruefsumme_aus_datei_wenn_github_keine_nennt():
    gh = FakeGitHub({LATEST: lambda: Resp(release(digest=False)),
                     "https://api.github.com/assets/2": lambda: Resp(f"{SHA}  Zeitzeuge-Setup.exe".encode())})
    assert updater.latest("o/r", "t", opener=gh)["sha256"] == SHA


def test_fehler_verstaendlich():
    with pytest.raises(updater.UpdateError, match="nicht eingerichtet"):
        updater.latest("o/r", "")
    gone = urllib.error.HTTPError(LATEST, 401, "Unauthorized", {}, None)
    with pytest.raises(updater.UpdateError, match="abgelaufen"):
        updater.latest("o/r", "t", opener=FakeGitHub({LATEST: gone}))
    with pytest.raises(updater.UpdateError, match="fehlt Zeitzeuge-Setup.exe"):
        updater.latest("o/r", "t", opener=FakeGitHub({LATEST: lambda: Resp(release(setup=False))}))
    offline = urllib.error.URLError("offline")
    with pytest.raises(updater.UpdateError, match="nicht erreichbar"):
        updater.latest("o/r", "t", opener=FakeGitHub({LATEST: offline}))


def test_download_prueft_pruefsumme(tmp_path):
    info = {"version": "4.1.9", "url": "https://api.github.com/assets/1", "size": len(SETUP), "sha256": SHA}
    gh = FakeGitHub({info["url"]: lambda: Resp(SETUP, {"Content-Length": str(len(SETUP))})})
    seen = []
    path = updater.download(info, "t", str(tmp_path), progress=lambda d, t: seen.append((d, t)), opener=gh)
    assert open(path, "rb").read() == SETUP
    assert seen[-1] == (len(SETUP), len(SETUP))
    assert gh.requests[0].get_header("Accept") == "application/octet-stream"

    bad = dict(info, sha256="0" * 64, version="4.1.8")
    with pytest.raises(updater.UpdateError, match="beschädigt"):
        updater.download(bad, "t", str(tmp_path), opener=gh)
    assert not any(n.startswith("Zeitzeuge-Setup-4.1.8") for n in os.listdir(tmp_path))
    with pytest.raises(updater.UpdateError, match="Prüfsumme"):
        updater.download(dict(info, sha256=""), "t", str(tmp_path), opener=gh)

    updater.cleanup(str(tmp_path))
    assert os.listdir(tmp_path) == []


def test_signatur_vom_selben_herausgeber():
    def signer(table):
        return lambda path: table[path]
    same = {"app": ("Valid", "CN=Filip Kroczak"), "setup": ("Valid", "CN=Filip Kroczak")}
    assert updater.signature_ok("setup", "app", signer=signer(same))
    other = dict(same, setup=("Valid", "CN=Jemand anders"))
    assert not updater.signature_ok("setup", "app", signer=signer(other))
    unsigned = dict(same, setup=("NotSigned", ""))
    assert not updater.signature_ok("setup", "app", signer=signer(unsigned))
    # Build ohne Zertifikat: nur die Prüfsumme zählt
    assert updater.signature_ok("setup", "app", signer=signer({"app": ("NotSigned", ""),
                                                                 "setup": ("NotSigned", "")}))


def test_setup_still_mit_neustart():
    args = updater.setup_args(minimized=True)
    assert "/SILENT" in args and "/SUPPRESSMSGBOXES" in args and "/ZZUPDATE=min" in args
    assert "/ZZUPDATE=show" in updater.setup_args(minimized=False)
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "installer", "zeitzeuge.iss"), encoding="utf-8-sig") as f:
        iss = f.read()
    assert "{param:ZZUPDATE|}" in iss and "RestartAs('min')" in iss and "RestartAs('show')" in iss


def test_token_ablauf():
    from datetime import datetime
    now = datetime(2026, 11, 11)
    assert updater.token_days_left("2026-12-01 00:00:00 UTC", now) == 20
    assert updater.token_days_left(None, now) is None
    assert updater.token_days_left("kaputt", now) is None


def test_zugang_aus_umgebung(monkeypatch):
    monkeypatch.setenv("ZEITZEUGE_UPDATE_TOKEN", "abc")
    monkeypatch.delenv("ZEITZEUGE_UPDATE_REPO", raising=False)
    assert updater.settings() == (updater.DEFAULT_REPO, "abc")
