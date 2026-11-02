"""Versionsnummer: Schema, Eintrag im CHANGELOG und Anzeige je Build-Art."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import version  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def with_info(info):
    version._INFO = info


def test_schema_major_minor_patch():
    assert re.fullmatch(r"\d+\.\d+\.\d+", version.VERSION), version.VERSION


def test_changelog_hat_eintrag_zur_version():
    with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as f:
        text = f.read()
    assert f"## {version.VERSION} – " in text, "CHANGELOG.md: Abschnitt zur Version fehlt"


def test_release_zeigt_nur_die_nummer():
    with_info({"channel": "release", "build": 140, "commit": "abc1234", "date": "2026-11-02"})
    assert version.version_label() == version.VERSION
    assert version.version_details() == f"{version.VERSION} · Build 140 · abc1234 · 02.11.2026"
    assert version.file_version()[3] == 140


def test_testversion_mit_buildnummer():
    with_info({"channel": "test", "build": 141, "commit": "abc1234", "date": "2026-11-02",
               "branch": "claude/x"})
    assert version.version_label() == f"{version.VERSION} (Build 141)"
    assert "Testversion" in version.version_details() and "claude/x" in version.version_details()


def test_quelltext_und_ohne_angaben():
    with_info({"channel": "dev", "commit": "abc1234", "date": "2026-11-02"})
    assert version.version_label() == f"{version.VERSION}-dev"
    with_info({})
    assert version.version_label() == version.VERSION
    assert version.version_details() == version.VERSION
    assert version.file_version()[3] == 0
    version._INFO = None
