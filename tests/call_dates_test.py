"""3CX-Anrufe am richtigen Tag: veraltetes „Heute“ in der 3CX-Liste erkennen und
falsch einsortierte Kopien aufräumen."""
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import pytest  # noqa: E402

from call_import import load_calls, merge_calls  # noqa: E402
from pbx_reader import PARSER_END, PARSER_START  # noqa: E402

# Der Lese-Teil des Skripts in Node, mit fester Uhr (20.11.2026 10:40) und ohne echtes DOM:
# texte() und richtung() werden durch einfache Fassungen ersetzt (spätere Deklaration gewinnt).
NODE = """
const Echt = Date;
const JETZT = new Echt(2026, 10, 20, 10, 40).getTime();
globalThis.Date = class extends Echt {
  constructor(...a) { if (a.length) super(...a); else super(JETZT); }
  static now() { return JETZT; }
};
const eintraege = JSON.parse(process.argv[1]);
globalThis.document = {querySelectorAll: () => eintraege.map((t) => ({t}))};
%s
function texte(item) { return item.t.split(" "); }
function richtung() { return "Eingehend"; }
console.log(JSON.stringify(sammeln().map((a) => a.start)));
"""


def read_list(texts):
    script = open(os.path.join(ROOT, "assets", "zeitzeuge_anrufe.user.js"), encoding="utf-8").read()
    parser = script[script.index(PARSER_START):script.index(PARSER_END)]
    out = subprocess.run(["node", "-e", NODE % parser, json.dumps(texts)],
                         capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])  # davor evtl. console.debug


needs_node = pytest.mark.skipif(not shutil.which("node"), reason="Node.js fehlt")


@needs_node
def test_normale_liste_unveraendert():
    assert read_list(["SB Sara Beispiel 701 Heute 10:33 • 0:04",
                      "GB Gustav Bauer 0251 Gestern 15:37 • 3:50",
                      "AG ABC GmbH 0251 Mo 08:01 • 1:02:03",
                      "MM Max Muster 0170 12.11.2026 11:00 • 5:00"]) == [
        "2026-11-20 10:33:00", "2026-11-19 15:37:00", "2026-11-16 08:01:00", "2026-11-12 11:00:00"]


@needs_node
def test_veraltetes_heute_unter_festem_datum():
    # So zeigte 3CX es beim Kollegen: heutige Anrufe mit Datum, gestrige noch als „Heute“
    assert read_list(["IS Ingo Sareika 025616876340 20.11.2026 10:33 • 0:04",
                      "KV Kevin Veldscholten 334 20.11.2026 10:01 • 31:50",
                      "TB Tobias Böing 0256186558862 Heute 10:15 • 20:13",
                      "AB Anna Berg 0251 Heute 08:05 • 1:00",
                      "CD Carl Dorn 0251 Gestern 16:00 • 2:00",
                      "EF Eva Fink 0251 Di 09:00 • 3:00"]) == [
        "2026-11-20 10:33:00", "2026-11-20 10:01:00", "2026-11-19 10:15:00",
        "2026-11-19 08:05:00", "2026-11-18 16:00:00", "2026-11-17 09:00:00"]


@needs_node
def test_heute_in_der_zukunft():
    # Noch kein Anruf heute, aber ein „Heute“-Anruf nach jetzt (10:40): kann nur gestern sein
    assert read_list(["TB Tobias Böing 0256 Heute 15:20 • 2:00",
                      "AB Anna Berg 0251 Heute 08:05 • 1:00"]) == [
        "2026-11-19 15:20:00", "2026-11-19 08:05:00"]


def call(start, seconds=120, number="0251"):
    return {"start": start, "duration_s": seconds, "name": number, "number": number,
            "direction": "Eingehend", "via": ""}


def test_falsche_kopie_am_folgetag_wird_entfernt(tmp_path):
    path = str(tmp_path / "anrufe.json")
    merge_calls(path, [call("2026-11-20 10:15:00", 1213, "0256"),  # eigentlich gestern
                       call("2026-11-20 10:01:00", 1910, "334"),
                       call("2026-11-20 09:00:00", 0, "0256")])     # verpasst: bleibt
    merge_calls(path, [call("2026-11-19 10:15:00", 1213, "0256"), call("2026-11-19 09:00:00", 0, "0256")])
    assert [c["start"] for c in load_calls(path)] == [
        "2026-11-19 09:00:00", "2026-11-19 10:15:00", "2026-11-20 09:00:00", "2026-11-20 10:01:00"]


def test_echter_anruf_an_beiden_tagen_bleibt(tmp_path):
    path = str(tmp_path / "anrufe.json")
    both = [call("2026-11-19 10:15:00"), call("2026-11-20 10:15:00")]
    merge_calls(path, both)
    merge_calls(path, both)
    assert len(load_calls(path)) == 2
