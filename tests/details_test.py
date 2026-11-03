"""Tagesliste: Spalte Details zeigt nur, was Typ, Kunde und Dauer nicht schon sagen."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

import main_timeline  # noqa: E402,F401  (lädt app_daylist in der richtigen Reihenfolge)
from app_daylist import new_details  # noqa: E402


@pytest.mark.parametrize("details, kind, customer, expected", [
    # Wiederholt Typ und Kunde
    ("VPN-Verbindung Kanzlei Schmidt - SSL VPN", "VPN-Verbindung", "Kanzlei Schmidt - SSL VPN", ""),
    ("RDP-Verbindung Müller GmbH - TS01", "RDP-Verbindung", "Müller GmbH - TS01", ""),
    # Richtung steht im Typ, Dauer in der Spalte Dauer
    ("Eingehend, Dauer 4:00", "Telefonat eingehend", "Kanzlei Schmidt (0251 123456)", ""),
    # TeamViewer-ID: neu, wenn der Kunde einen Namen hat, doppelt, wenn die Nummer schon dasteht
    ("TeamViewer-ID 1 076 789 144", "TeamViewer", "Müller GmbH", "TeamViewer-ID 1 076 789 144"),
    ("TeamViewer-ID 1 123 456 789", "TeamViewer", "TeamViewer 1 123 456 789", ""),
    # Neues bleibt
    ("2 Verbindungen · 1× OTP", "SSH-Verbindung", "Praxis Weber - Firewall", "2 Verbindungen · 1× OTP"),
    ("1× Passwort", "RDP-Verbindung", "Kanzlei Schmidt - DC01", "1× Passwort"),
    ("", "Telefonat", "", ""),
])
def test_new_details(details, kind, customer, expected):
    assert new_details(details, kind, customer) == expected
