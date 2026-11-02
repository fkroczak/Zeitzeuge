"""Versionsnummer: Zählung aus den Merges in main, Anzeige je Build-Art, Prüfung von Release-Tags."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import version  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def with_info(info):
    version._INFO = info


def teardown_function(_f):
    version._INFO = None


def test_zaehlung_bleibt_klein():
    count = version.count_version
    assert count([]) == "4.1.0"
    assert count([("2026-11", "Merge pull request #34\n\nLadeanzeige")] * 3) == "4.1.3"
    # Neuer Monat: MINOR +1, PATCH von vorn; viele PRs im Monat nur PATCH
    assert count([("2026-11", "a"), ("2026-12", "b"), ("2026-12", "c")]) == "4.2.1"
    assert count([("2026-11", "a")] * 40 + [("2027-01", "b")]) == "4.2.0"
    # Markierungen im PR-Titel
    assert count([("2026-11", "PR\n\n[minor] Neue Ansicht"), ("2026-11", "Fix")]) == "4.2.1"
    assert count([("2026-11", "a"), ("2026-11", "[MAJOR] Neues Datenformat"), ("2026-12", "b")]) == "5.1.0"


def test_stand_aus_git_ist_gueltig():
    current, _on_main = version.main_state()
    assert re.fullmatch(r"\d+\.\d+\.\d+", current), current


def test_changelog_hat_abschnitt_zur_stufe():
    major_minor = ".".join(version.main_state()[0].split(".")[:2])
    with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as f:
        assert f"## {major_minor} – " in f.read(), "CHANGELOG.md: Abschnitt fehlt"


def test_anzeige_je_build_art():
    with_info({"channel": "test", "version": "4.1.3", "build": 186, "commit": "abc1234",
               "date": "2026-11-02", "branch": "claude/x"})
    assert version.version_label() == "4.1.3 · Test 186"
    assert version.file_name_version() == "4.1.3-test186"
    assert version.version_details() == "4.1.3 · Testversion · Build 186 · claude/x · abc1234 · 02.11.2026"
    assert version.file_version() == (4, 1, 3, 186)
    with_info({"channel": "main", "version": "4.1.4", "build": 190, "commit": "abc1234"})
    assert version.version_label() == "4.1.4" and version.file_name_version() == "4.1.4"
    with_info({"channel": "dev", "version": "4.1.4", "commit": "abc1234", "date": "2026-11-02"})
    assert version.version_label() == "4.1.4-dev"
    with_info({})
    assert version.version_label() == "4.1.0"


def test_build_auf_github():
    env = {"GITHUB_ACTIONS": "true", "GITHUB_RUN_NUMBER": "186", "GITHUB_REF_TYPE": "branch",
           "GITHUB_REF_NAME": "33/merge", "GITHUB_HEAD_REF": "claude/x", "GITHUB_SHA": "abcdef123"}
    info = version.collect_build_info(env)
    assert re.fullmatch(r"\d+\.\d+\.\d+", info["version"]) and info["build"] == 186
    assert info["commit"] == "abcdef1" and version.check_tag(info) == ""


def test_release_tag_muss_passen():
    assert version.check_tag({"version": "4.1.3", "tag": "v4.1.3"}) == ""
    assert "passt nicht" in version.check_tag({"version": "4.1.3", "tag": "v5.0.0"})
