"""Kundenliste (customers.py) und Lernen aus Korrekturen (learning.py), ohne Qt."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import customers as cl  # noqa: E402
import journal  # noqa: E402
import learning  # noqa: E402
import rules  # noqa: E402
import transfer  # noqa: E402

D = "2026-10-20"


def e(**kw):
    return {"start": f"{D} 09:00:00", "end": f"{D} 09:30:00", **kw}


TV = e(type="TeamViewer", customer_name="TeamViewer 123 456 789", tv_id="123456789")
RDM = e(type="RDP-Verbindung", customer_name="SRV01.kunde.local")
VPN = e(type="VPN-Verbindung", customer_name="Müller VPN", vpn_source="Sophos")
CALL = e(type="Telefonat", customer_name="Max Muster (+49 711 123456)", phone="+49 711 123456",
         direction="Eingehend")
MAIL = e(type="E-Mail", customer_name="Angebot", email_domains=["mail.mueller.de"])


def test_normalisierung():
    assert cl.normalize_phone("+49 711 123456") == "0711123456"
    assert cl.normalize_phone("0049 (711) 12-34-56") == "0711123456"
    assert cl.normalize_phone("0711 / 123456") == "0711123456"
    assert cl.normalize_phone("+43 1 234") == "00431234"
    assert cl.normalize_phone("12") == ""
    assert cl.normalize_domain("Max@Kunde.DE") == "kunde.de"
    assert cl.normalize_domain("@kunde.de") == "kunde.de"
    assert cl.normalize_domain("kein domain") == ""
    assert cl.normalize("tv", "1 076 789 144") == "1076789144"
    assert cl.normalize("tv", "abc") == ""
    assert cl.normalize("rdm", "  SRV01   Kunde ") == "srv01 kunde"


def test_spuren_der_eintraege():
    assert cl.traces_of(TV) == [("tv", "123456789")]
    assert cl.traces_of(RDM) == [("rdm", "SRV01.kunde.local")]
    assert cl.traces_of(VPN) == [("vpn", "Müller VPN")]
    # VPN aus RDM (ohne vpn_source) kann beides sein
    assert cl.traces_of(e(type="VPN-Verbindung", customer_name="X")) == [("vpn", "X"), ("rdm", "X")]
    assert cl.traces_of(CALL)[0] == ("phone", "+49 711 123456")
    # alte Anrufe ohne Feld phone: Nummer aus "Name (Nummer)"
    assert cl.traces_of(e(type="Telefonat", customer_name="Max (0711 123456)")) == [("phone", "0711 123456")]
    assert cl.traces_of(MAIL) == [("mail", "mail.mueller.de")]
    assert cl.traces_of(e(type="Zugangsdaten", customer_name="srv01")) == [("rdm", "srv01")]
    # Eigene Tätigkeiten, KI, PC-Fenster: keine Spur
    for other in (e(doc=True, customer_name="x"), e(ai=True, customer_name="x"),
                  e(type="PC: Outlook", app="outlook.exe", customer_name="x")):
        assert cl.traces_of(other) == []


def test_zuordnung_aller_spuren():
    config = {"customers": [], "teamviewer_names": {}}
    assert cl.learn(config, "rdm", "srv01.KUNDE.local", "Müller GmbH")
    assert cl.learn(config, "vpn", "müller vpn", "Müller GmbH")
    assert cl.learn(config, "phone", "0711 123456", "Müller GmbH")
    assert cl.learn(config, "mail", "@mueller.de", "Müller GmbH")
    assert cl.learn(config, "tv", "123 456 789", "Müller GmbH")
    assert not cl.learn(config, "phone", "+49711123456", "Müller GmbH"), "gleiche Nummer, nichts neu"
    index = cl.index(config)
    for entry in (TV, RDM, VPN, CALL, MAIL):
        assert index.customer_for(entry) == "Müller GmbH", entry
    assert cl.customer_for(e(type="E-Mail", email_domains=["andere.de"]), index) == ""
    assert cl.customer_for(e(type="E-Mail", email="max@mueller.de"), config) == "Müller GmbH"
    assert config["teamviewer_names"] == {"123456789": "Müller GmbH"}, "TeamViewer gespiegelt"
    assert len(config["customers"]) == 1 and len(config["customers"][0]["traces"]) == 5


def test_spur_gehoert_nur_einem_kunden():
    config = {}
    cl.learn(config, "rdm", "srv01", "A")
    cl.learn(config, "rdm", "SRV01", "B")
    assert cl.customer_for(RDM | {"customer_name": "srv01"}, config) == "B"
    a = next(c for c in config["customers"] if c["name"] == "A")
    assert a["traces"] == [], "von A nach B verschoben, A bleibt"
    cl.forget(config, "rdm", "srv01")
    assert cl.customer_for(RDM | {"customer_name": "srv01"}, config) == ""


def test_alte_teamviewer_names_bleiben():
    """Alte Config: nur teamviewer_names. Wird mitgelesen, nichts geht verloren."""
    config = {"teamviewer_names": {"123456789": "Müller GmbH", "987": "Meier"}}
    listed = cl.customer_list(config)
    assert {c["name"] for c in listed} == {"Müller GmbH", "Meier"}
    assert cl.customer_for(TV, config) == "Müller GmbH"
    assert config["teamviewer_names"] == {"123456789": "Müller GmbH", "987": "Meier"}
    # „TeamViewer-ID benennen“ auf anderem Weg (alte Version): teamviewer_names gewinnt
    config["teamviewer_names"]["123456789"] = "Neu AG"
    assert cl.customer_for(TV, config) == "Neu AG"
    # Bisherige Funktion suggest_customer unverändert, mit Liste zusätzlich die anderen Spuren
    assert journal.suggest_customer(TV, {"123456789": "Müller GmbH"}) == "Müller GmbH"
    cl.learn(config, "rdm", "srv01.kunde.local", "Müller GmbH")
    assert journal.suggest_customer(RDM) == "SRV01.kunde.local"
    assert journal.suggest_customer(RDM, None, cl.index(config)) == "Müller GmbH"


def test_dialog_liste_uebernehmen():
    config = {"teamviewer_names": {"111": "Alt"}}
    working = cl.customer_list(config)
    working[0]["name"] = "Neu"  # umbenannt
    working.append({"name": "B", "traces": [{"kind": "tv", "value": "222"},
                                            {"kind": "tv", "value": "111"}]})  # doppelt
    cl.apply_list(config, working)
    assert config["teamviewer_names"] == {"111": "Neu", "222": "B"}
    cl.apply_list(config, [])  # alles gelöscht
    assert config["teamviewer_names"] == {} and cl.customer_list(config) == []


def test_anzeige_kunde_in_der_liste():
    config = {}
    cl.learn(config, "rdm", "srv01", "Müller GmbH")
    index = cl.index(config)
    assert cl.with_customer(RDM | {"customer_name": "srv01"}, index) == "Müller GmbH · srv01"
    assert cl.with_customer(RDM, index) == "SRV01.kunde.local", "unbekannt: wie bisher"
    assert cl.with_customer(e(type="Telefonat", customer_name="Müller GmbH (0711)"), index) \
        == "Müller GmbH (0711)"


def test_regel_vorschlag():
    rule = learning.rule_for(RDM, "Server-/Netzwerkadministration", "Müller GmbH")
    assert rule["field"] == "customer" and rule["category"] == "Server-/Netzwerkadministration"
    assert rule["customer"] == "Müller GmbH" and rule["learned"]
    assert rules.pattern_error(rule["match"]) is None
    compiled = rules._compile_rules([rule])
    assert rules.match_entry(RDM, compiled) is not None
    assert rules.match_entry(RDM | {"customer_name": "srv01.kunde.local.x"}, compiled) is None, "genau"
    # Reine Nummer oder unbenannte TeamViewer-ID: auf den Typ
    assert learning.rule_for(e(type="Telefonat", customer_name="+49 711"), "Beratung")["field"] == "type"
    assert learning.rule_for(TV, "Beratung")["match"] == "re:^TeamViewer$"
    # Nicht lernbar
    assert learning.rule_for(RDM, "") is None
    assert learning.rule_for(e(doc=True, customer_name="x"), "Beratung") is None
    # Klammern im Kunden würden als Platzhalter gelesen
    assert "{" not in learning.rule_for(RDM, "X", "A {1}")["customer"]


def test_regel_vor_den_standardregeln_ohne_duplikate():
    defaults = rules.default_rules()
    custom = {"name": "Eigene", "field": "title", "match": "foo", "category": "X", "enabled": True}
    start = [custom] + defaults
    rule = learning.rule_for(RDM, "Beratung / Abstimmung")
    result, status = learning.add_rule(start, rule)
    assert status == "added" and result[1]["match"] == rule["match"], "nach eigenen, vor Standard"
    assert result[2]["name"] == defaults[0]["name"] and len(result) == len(start) + 1
    assert start[1] is defaults[0] and len(start) == len(defaults) + 1, "Eingabe unverändert"
    again, status = learning.add_rule(result, rule)
    assert status == "exists" and len(again) == len(result)
    changed, status = learning.add_rule(result, dict(rule, category="Fernwartung"))
    assert status == "updated" and len(changed) == len(result) and changed[1]["category"] == "Fernwartung"
    # Die gelernte Regel greift vor der Standardregel „Fernwartung“
    blocks = rules.classify([RDM], [], result, min_minutes=0)
    assert blocks and blocks[0]["category"] == "Beratung / Abstimmung"
    # und schlägt im Dialog die Kategorie vor; Standardregeln ändern den Vorschlag nicht
    assert learning.learned_category(RDM, result) == "Beratung / Abstimmung"
    assert learning.learned_category(RDM, defaults) == ""
    # Leere Regelliste
    only, status = learning.add_rule([], rule)
    assert status == "added" and only == [rule]


def test_korrekturen_anwenden_und_vorschlaege():
    config = {"rules": rules.default_rules()}
    cats = ["Fernwartung", "Beratung / Abstimmung"]
    hints = learning.doc_hints(RDM, config, cats)
    assert hints["customer"] == "SRV01.kunde.local" and hints["category"] == "Fernwartung"
    assert hints["trace"] == ("rdm", "SRV01.kunde.local") and hints["rule_subject"] == "SRV01.kunde.local"
    item = {"customer": "Müller GmbH", "category": "Beratung / Abstimmung"}
    done = learning.apply_corrections(config, RDM, item, remember=True, make_rule=True)
    assert len(done) == 2, done
    hints = learning.doc_hints(RDM, config, cats)
    assert hints["customer"] == "Müller GmbH" and hints["category"] == "Beratung / Abstimmung"
    assert learning.apply_corrections(config, RDM, item, remember=True, make_rule=True) == [], \
        "zweimal: nichts doppelt"
    # Nicht angehakt: nichts gemerkt
    config2 = {"rules": rules.default_rules()}
    assert learning.apply_corrections(config2, RDM, item) == []
    assert config2["rules"] == rules.default_rules() and not config2.get("customers")
    # Abschaltbar
    off = {"customers_learn": False, "rules_learn_offer": False}
    hints = learning.doc_hints(RDM, off, cats)
    assert hints["trace"] is None and hints["rule_subject"] is None
    assert learning.doc_hints(TV, off, cats)["trace"] == ("tv", "123456789"), "TeamViewer wie bisher"


def test_export_nimmt_kundenliste_mit(tmp_path):
    kunden = [{"name": "Müller GmbH", "traces": [{"kind": "rdm", "value": "srv01"}]}]
    export = transfer.make_export({D: {"verbindungen": [RDM]}}, {"1": "A"}, pc="ARBEITS-PC",
                                  customers=kunden)
    assert export["kunden"] == kunden
    store = transfer.ImportStore(str(tmp_path / "uebernommen.json"))
    store.add(export, own_pc="PAW")
    assert store.customers() == kunden
    index = cl.index({}, store.customers(), store.teamviewer_names())
    assert index.customer_for(RDM | {"customer_name": "SRV01"}) == "Müller GmbH"
    # alter Export ohne Kundenliste: geht weiter
    old = transfer.make_export({D: {"verbindungen": [RDM]}}, {}, pc="ALT")
    old.pop("kunden")
    store.add(old, own_pc="PAW")
    assert store.customers() == kunden
