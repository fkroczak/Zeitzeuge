"""Versionsnummer von Zeitzeuge: eine Stelle für Fenstertitel, Info-Dialog, fehler.log und EXE.

Schema MAJOR.MINOR.PATCH (Semantic Versioning), von Hand erhöht, Einträge in CHANGELOG.md:
- MAJOR: Daten lassen sich mit einer älteren Version nicht mehr lesen (z. B. neues
  Speicherformat), oder Bedienung/Funktionen ändern sich grundlegend.
- MINOR: neue Funktionen, alles Bisherige geht weiter.
- PATCH: nur Fehlerbehebungen.

Dazu kommt die Herkunft des Builds (Buildnummer, Commit, Datum). Die schreibt
ZeitZeuge.spec beim Bauen in build_info.py (nicht im Repository). Beim Start aus
dem Quelltext fragt version.py stattdessen git.
"""
import os
import subprocess
import sys

VERSION = "5.0.0"


def _from_git():
    """Commit des Quelltexts, falls aus einem git-Ordner gestartet (sonst leer)."""
    here = os.path.dirname(os.path.abspath(__file__))
    if not os.path.exists(os.path.join(here, ".git")):
        return {}
    try:
        out = subprocess.run(["git", "-C", here, "log", "-1", "--format=%h %cs"],
                             capture_output=True, text=True, timeout=3,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        commit, date = out.stdout.split()
        return {"channel": "dev", "commit": commit, "date": date}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}


def build_info():
    """Herkunft: channel ("release", "test", "local", "dev"), build, commit, date, branch."""
    if getattr(sys, "frozen", False):  # nur die EXE: aus dem Quelltext zählt git
        try:
            import build_info as info  # beim Bauen erzeugt
            return dict(info.BUILD)
        except ImportError:
            return {}
    return _from_git()


_INFO = None


def _info():
    global _INFO
    if _INFO is None:
        _INFO = build_info()
    return _INFO


def version_label():
    """Kurz, für Fenstertitel und Infobereich: "5.0.0", "5.0.0 (Build 123)" oder "5.0.0-dev"."""
    info = _info()
    channel = info.get("channel")
    if channel == "test" and info.get("build"):
        return f"{VERSION} (Build {info['build']})"
    if channel in ("dev", "local"):
        return f"{VERSION}-{channel}"
    return VERSION


def version_details():
    """Ausführlich, für fehler.log, z. B. "5.0.0 · Testversion · Build 123 · a8d4d3e · 02.11.2026"."""
    return " · ".join([VERSION] + build_details())


def build_details():
    """Nur die Herkunft als Liste, z. B. ["Testversion", "Build 123", "a8d4d3e", "02.11.2026"]."""
    info = _info()
    parts = []
    names = {"test": "Testversion", "local": "lokal gebaut", "dev": "aus dem Quelltext"}
    if info.get("channel") in names:
        parts.append(names[info["channel"]])
    if info.get("build"):
        parts.append(f"Build {info['build']}")
    if info.get("branch") and info.get("channel") == "test":
        parts.append(info["branch"])
    if info.get("commit"):
        parts.append(info["commit"])
    if info.get("date"):
        y, m, d = (info["date"].split("-") + ["", ""])[:3]
        parts.append(f"{d}.{m}.{y}" if d else info["date"])
    return parts


def file_version():
    """Vier Zahlen für die EXE-Eigenschaften: MAJOR.MINOR.PATCH.Buildnummer."""
    nums = [int(n) for n in VERSION.split(".")[:3]]
    build = _info().get("build") or 0
    return tuple(nums + [int(build) % 65536])
