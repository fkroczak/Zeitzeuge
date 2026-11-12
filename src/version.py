"""Versionsnummer von Zeitzeuge: eine Stelle für Fenstertitel, Info-Dialog, fehler.log und EXE.

MAJOR.MINOR.PATCH, z. B. 4.1.3. Alles zählt von selbst aus der git-Geschichte von main
(ab ANCHOR = 4.1.0), die Zahlen bleiben klein:
- PATCH: +1 für jeden Merge in main (jeden PR), beginnt mit jeder neuen MINOR bei 0.
- MINOR: +1 mit dem ersten Merge in einem neuen Kalendermonat (höchstens 12 im Jahr),
  oder früher, wenn ein PR-Titel "[minor]" enthält.
- MAJOR: nur wenn ein PR-Titel "[major]" enthält (z. B. ältere Versionen können die Daten
  nicht mehr lesen). MINOR und PATCH beginnen dann bei 0.

Ein Build, der nicht auf main liegt (Branch, PR), trägt die Version seines main-Stands
plus "Test <Buildnummer>", z. B. "4.1.3 · Test 186". Beim Bauen schreibt ZeitZeuge.spec
das in build_info.py; die EXE liest es dort. Aus dem Quelltext gestartet fragt version.py git.

`python version.py` gibt die Version für Dateinamen aus (für die CI), z. B. "4.1.3" oder
"4.1.3-test186", und bricht ab, wenn ein Release-Tag nicht zum Stand passt.
"""
import datetime
import os
import re
import subprocess
import sys

# Startpunkt der Zählung: dieser Commit auf main ist Version 4.1.0 (November 2026)
ANCHOR = "af567babd694d1a2ac95c475aed78184a9dde9ea"
ANCHOR_VERSION, ANCHOR_MONTH = (4, 1, 0), "2026-11"
MAJOR_MARK, MINOR_MARK = "[major]", "[minor]"

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Projektordner (über src/)


def _git(*args):
    try:
        out = subprocess.run(["git", "-C", HERE, *args], capture_output=True, text=True,
                             timeout=5, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def count_version(merges):
    """Version aus den Merges in main nach ANCHOR: Liste (Monat "JJJJ-MM", Text), älteste zuerst."""
    major, minor, patch = ANCHOR_VERSION
    month = ANCHOR_MONTH
    for merge_month, text in merges:
        text = text.lower()
        if MAJOR_MARK in text:
            major, minor, patch = major + 1, 0, 0
        elif MINOR_MARK in text or merge_month > month:
            minor, patch = minor + 1, 0
        else:
            patch += 1
        month = max(month, merge_month)
    return f"{major}.{minor}.{patch}"


def main_state():
    """(Version des main-Stands, liegt HEAD selbst auf main?) aus git; ohne git der Startwert."""
    start = ".".join(map(str, ANCHOR_VERSION))
    main = next((ref for ref in ("origin/main", "main")
                 if _git("rev-parse", "--verify", "--quiet", ref)), "")
    head = _git("rev-parse", "HEAD")
    base = _git("merge-base", "HEAD", main) if main else head
    if not base:
        return start, True
    log = _git("log", "--first-parent", "--reverse", "--format=%cs %s%n%b%x00", f"{ANCHOR}..{base}")
    merges = [(e[:7], e[11:]) for e in (e.strip() for e in log.split("\x00")) if e]
    return count_version(merges), head == base


def collect_build_info(env=None):
    """Herkunft eines Builds: GitHub Actions (main oder Testversion) oder lokal."""
    env = os.environ if env is None else env
    version, on_main = main_state()
    info = {"date": datetime.date.today().isoformat(), "version": version}
    if env.get("GITHUB_ACTIONS") == "true":
        info["build"] = int(env.get("GITHUB_RUN_NUMBER", "0") or 0)
        info["commit"] = env.get("GITHUB_SHA", "")[:7]
        info["channel"] = "main" if on_main else "test"
        if not on_main:
            info["branch"] = env.get("GITHUB_HEAD_REF") or env.get("GITHUB_REF_NAME", "")
        if env.get("GITHUB_REF_TYPE") == "tag":
            info["tag"] = env.get("GITHUB_REF_NAME", "")
    else:
        info["channel"] = "local"
        info["commit"] = _git("rev-parse", "--short", "HEAD")
    return info


def _from_git():
    """Stand des Quelltexts, falls aus einem git-Ordner gestartet (sonst leer)."""
    if not os.path.exists(os.path.join(HERE, ".git")):
        return {}
    parts = _git("log", "-1", "--format=%h %cs").split()
    if len(parts) != 2:
        return {}
    return {"channel": "dev", "commit": parts[0], "date": parts[1], "version": main_state()[0]}


def build_info():
    """Herkunft: channel ("main", "test", "local", "dev"), version, build, commit, date, branch."""
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


def channel():
    """Herkunft dieses Builds: "main", "test", "local" oder "dev" (leer, wenn unbekannt)."""
    return _info().get("channel", "")


def full_version():
    """MAJOR.MINOR.PATCH, z. B. "4.1.3"."""
    return _info().get("version") or ".".join(map(str, ANCHOR_VERSION))


def version_label():
    """Kurz, für den Fenstertitel: "4.1.3", "4.1.3 · Test 186", "4.1.3-dev" oder "4.1.3-local"."""
    info = _info()
    channel = info.get("channel")
    if channel == "test" and info.get("build"):
        return f"{full_version()} · Test {info['build']}"
    if channel in ("dev", "local"):
        return f"{full_version()}-{channel}"
    return full_version()


def file_name_version():
    """Für Dateinamen der Downloads: "4.1.3" oder "4.1.3-test186"."""
    info = _info()
    if info.get("channel") == "test" and info.get("build"):
        return f"{full_version()}-test{info['build']}"
    return full_version()


def build_details():
    """Nur die Herkunft als Liste, z. B. ["Testversion", "Build 186", "claude/x", "a8d4d3e", "02.11.2026"]."""
    info = _info()
    parts = []
    names = {"test": "Testversion", "local": "lokal gebaut", "dev": "aus dem Quelltext"}
    if info.get("channel") in names:
        parts.append(names[info["channel"]])
    if info.get("build"):
        parts.append(f"Build {info['build']}")
    if info.get("branch"):
        parts.append(info["branch"])
    if info.get("commit"):
        parts.append(info["commit"])
    if info.get("date"):
        y, m, d = (info["date"].split("-") + ["", ""])[:3]
        parts.append(f"{d}.{m}.{y}" if d else info["date"])
    return parts


def version_details():
    """Ausführlich, für fehler.log, z. B. "4.1.3 · Testversion · Build 186 · claude/x · a8d4d3e · 02.11.2026"."""
    return " · ".join([full_version()] + build_details())


def file_version():
    """Vier Zahlen für die EXE-Eigenschaften: MAJOR.MINOR.PATCH.Buildnummer."""
    nums = [int(n) % 65536 for n in re.findall(r"\d+", full_version())[:3]]
    nums += [0] * (3 - len(nums))
    return tuple(nums + [int(_info().get("build") or 0) % 65536])


def check_tag(info):
    """Fehlertext, wenn ein Release-Tag nicht zur gezählten Version passt (sonst leer)."""
    tag = info.get("tag")
    if not tag or tag == f"v{info.get('version')}":
        return ""
    return f"Tag {tag} passt nicht zu diesem Stand: erwartet v{info.get('version')}"


if __name__ == "__main__":
    current = collect_build_info()
    problem = check_tag(current)
    if problem:
        print(problem, file=sys.stderr)
        sys.exit(1)
    _INFO = current
    print(file_name_version())
