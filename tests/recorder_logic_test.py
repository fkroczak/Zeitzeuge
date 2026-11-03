"""Mitschnitt ohne Browser: Kürzen und Schwärzen, ungekürzt beim Buchungs-Mitschnitt."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import request_recorder as rr  # noqa: E402

BOOKING = {"Start": "2026-11-02T08:00:00Z", "Activity": "x" * 2000, "Password": "geheim",
           "Positionen": [{"Nr": i} for i in range(20)]}


def test_normal_gekuerzt():
    out = rr.summarize_body(json.dumps(BOOKING))["json"]
    assert len(out["Positionen"]) == rr.MAX_ITEMS + 1  # Rest als Hinweis
    assert "2000 Zeichen" in out["Activity"]
    assert out["Password"]["geschwaerzt"]


def test_buchung_ungekuerzt_aber_geschwaerzt():
    out = rr.summarize_body(json.dumps(BOOKING), full=True)["json"]
    assert len(out["Positionen"]) == 20 and out["Activity"] == "x" * 2000
    assert out["Password"]["geschwaerzt"], "Geheimnisse bleiben geschwärzt"
    form = rr.summarize_body("username=a&password=b", "application/x-www-form-urlencoded", full=True)
    assert "password=%3Cgeschwaerzt%3E" in form["formular"] or "password=<geschwaerzt>" in form["formular"]


def test_nur_speichernde_abfragen_ungekuerzt():
    rec = rr.Recorder.__new__(rr.Recorder)  # ohne Verbindung zum Browser
    rec.full_writes = True
    assert rec._full({"methode": "POST"}) and rec._full({"methode": "put"})
    assert not rec._full({"methode": "GET"})
    rec.full_writes = False
    assert not rec._full({"methode": "POST"})
