"""Lesbarkeit von README und Oberflächentexten (warnt nur, blockiert nicht).

Verfahren für deutsche Texte:
  - Flesch-Lesbarkeitsindex nach Amstad: 180 - Satzlänge - 58,5 * Silben pro Wort.
    0-30 sehr schwer, 30-50 schwer, 50-60 mittelschwer, 60-70 mittel, > 70 leicht.
  - Wiener Sachtextformel 1 (WSTF): ungefähre Schulstufe, 4 = leicht, 15 = sehr schwer.

Grenzen: Silben werden nur geschätzt (Vokalgruppen), Listenpunkte zählen als
Sätze. Die Werte zeigen Trends, sie ersetzen kein Gegenlesen.

Aufruf: python tests/readability_check.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Untergrenzen (Ratchet): nur anheben, nie senken. Stand der Baseline 21.10.2026:
# README Flesch-Amstad 61, UI-Texte 55.
MIN_FLESCH = {"README.md": 55, "UI-Texte": 50}
UI_FILES = ["main_timeline.py", "settings_dialogs.py", "browser_setup.py",
            "timeline_only.py", "pbx_reader.py"]


def syllables(word):
    word = re.sub(r"(ei|ie|au|eu|äu|ai|aa|ee|oo)", "a", word.lower())
    return max(1, len(re.findall(r"[aeiouyäöü]+", word)))


def score(text):
    sentences = [s for s in re.split(r"[.!?:]\s+|\n\n", text) if re.search(r"\w", s)]
    words = re.findall(r"[A-Za-zÄÖÜäöüß]+", text)
    syl = [syllables(w) for w in words]
    asl = len(words) / len(sentences)
    asw = sum(syl) / len(words)
    flesch = 180 - asl - 58.5 * asw
    ms = sum(1 for s in syl if s >= 3) / len(words) * 100
    iw = sum(1 for w in words if len(w) > 6) / len(words) * 100
    es = sum(1 for s in syl if s == 1) / len(words) * 100
    wstf = 0.1935 * ms + 0.1672 * asl + 0.1297 * iw - 0.0327 * es - 0.875
    return len(words), asl, flesch, wstf


def readme_text():
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
        t = f.read()
    t = re.sub(r"```.*?```", "", t, flags=re.S)
    t = re.sub(r"`[^`]*`", "", t)
    t = re.sub(r"\|.*\|", "", t)
    t = re.sub(r"\(http[^)]*\)", "", t)
    return re.sub(r"[#*>\-]+", " ", t)


def ui_text():
    """Deutsche Sätze aus Zeichenketten im Code (Dialoge, Hinweise, Status)."""
    out = []
    for path in UI_FILES:
        with open(os.path.join(ROOT, path), encoding="utf-8") as f:
            for m in re.findall(r'"([^"\n]{25,})"', f.read()):
                if re.search(r"[äöüÄÖÜß]|\b(und|die|der|das|nicht|wird|du)\b", m):
                    out.append(re.sub(r"<[^>]+>", "", m))
    return "\n\n".join(out)


warn = False
for name, text in [("README.md", readme_text()), ("UI-Texte", ui_text())]:
    words, asl, flesch, wstf = score(text)
    print(f"{name}: {words} Wörter, Ø {asl:.1f} Wörter/Satz, "
          f"Flesch-Amstad {flesch:.0f}, WSTF {wstf:.1f}")
    if flesch < MIN_FLESCH[name]:
        warn = True
        msg = f"{name}: Flesch-Amstad {flesch:.0f} unter {MIN_FLESCH[name]}. Kürzere Sätze, einfachere Wörter?"
        print(f"::warning title=Lesbarkeit::{msg}" if os.environ.get("GITHUB_ACTIONS") else "WARNUNG: " + msg)
sys.exit(0)  # nur Hinweis, blockiert den Build nicht
