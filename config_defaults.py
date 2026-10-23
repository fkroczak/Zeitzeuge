"""Standardwerte der Einstellungen (zeitzeuge_config.json).

Laden, Ergänzen und Speichern: load_config_with_defaults/save_config in main_timeline.py.
"""
import os

import rules
from log_parsers import VpnParser


def default_config():
    """Neue Standardwerte bei jedem Aufruf (Listen und Dicts werden in die Config übernommen)."""
    return {
        "activity_types": [
            # Remote / Zugänge
            "VPN-Sitzung",
            "RDP-Sitzung",
            "SSH-Sitzung",
            "TeamViewer",
            "RDP-Verbindung",
            "SSH",
            "VPN",
            "Website-Verbindung",

            # Admin-Oberflächen / Dienste
            "Nextcloud-Admin",
            "NAS-Admin",
            "Hosting-Admin",
            "M365-Admin",
            "Mail-Administration",

            # Sicherheits-/Zugangsthemen
            "Passwortaktion",
            "OTP / 2FA",
            "Benutzername angezeigt",
            "Passwort angezeigt",

        ],
        # Typfarben aus dem Design "Metro Klar" (alte Standardwerte stellt
        # load_config_with_defaults in main_timeline.py um, siehe OLD_TYPE_COLORS)
        "type_colors": {
            # Remote / Zugänge
            "VPN-Sitzung":           "#0F9D8A",  # Türkis
            "RDP-Sitzung":           "#D99A00",  # Gelb
            "SSH-Sitzung":           "#E06D10",  # Orange

            # Admin-Oberflächen / Dienste
            "Nextcloud-Admin":       "#3498DB",  # Blau
            "NAS-Admin":             "#16A085",  # Petrol
            "Website-Admin":         "#139FB3",  # Türkisgrün
            "Hosting-Admin":         "#9B59B6",  # Lila (z.B. Netcup/goneo)
            "M365-Admin":            "#2272AD",  # Dunkelblau
            "Mail-Administration":   "#C0392B",  # Rot

            # Sicherheits-/Zugangsthemen
            "Passwortaktion":        "#9B59B6",  # Lila
            "OTP-Anzeige":             "#E84393",  # Pink
            "Benutzername angezeigt": "#9B59B6",  # Grau
            "Passwort angezeigt": "#9B59B6",  # Grau

            # Parser-Typen aus TeamViewer/RDM
            "TeamViewer":            "#3460DB",
            "RDP-Verbindung":        "#D99A00",
            "SSH":                   "#E06D10",
            "VPN":                   "#0F9D8A",
            "Website-Verbindung":    "#139FB3",
        },

        "suggestion_colors": {
            "light": {"background": "#B4B4B4", "text": "#000000"},
            "dark": {"background": "#4A4A4A", "text": "#FFFFFF"},
        },

        "auto_start": True,
        "work_start": "08:00",
        "work_end": "17:00",

        "teamviewer_paths": [
            os.path.expandvars(r"%APPDATA%\TeamViewer\Connections.txt")
        ],
        "rdm_paths": [
            os.path.expandvars(
                r"%LOCALAPPDATA%\Devolutions\RemoteDesktopManager\Connections.log"
            )
        ],
        # Datenquellen, einzeln im Menü "Datenquellen" ein- und ausschaltbar
        "teamviewer_enabled": True,
        "rdm_enabled": True,
        "sophos_enabled": True,
        "forti_enabled": True,
        # Weitere VPN-Clients (OpenVPN usw.) über ihre Logdateien
        "vpn_enabled": True,
        "vpn_paths": VpnParser().default_paths,  # OpenVPN GUI, OpenVPN Connect, Sophos SSL VPN
        "vpn_timezone_correction": 0,  # VPN-Clients schreiben Ortszeit
        # Sophos Connect (scvpn.log, scgui.log, charon.log – charon.log enthält auch FortiClient)
        "sophos_connect_dirs": [
            r"C:\Program Files (x86)\Sophos\Connect",
            r"C:\Program Files\Sophos\Connect",
        ],
        # Eigene VPN-Aufzeichnung: Teil der Adapterbeschreibung -> Quelle
        "vpn_monitor_enabled": True,
        "vpn_adapters": {"Sophos": "Sophos", "Fortinet": "FortiClient"},
        # deine gewünschten Zeitzonen
        "timezone_correction": 0,
        "teamviewer_timezone_correction": 1,
        "rdm_timezone_correction": 0,

        "dark_mode": False,
        "start_minimized": False,

        # Anrufe aus 3CX
        "calls_ignore_missed": True,
        "calls_min_duration": 0,
        "calls_days_back": 14,  # 3CX: so viele Tage zurück lesen
        "calls_3cx_url": "https://voice.visaas.de:5001",

        # Aktivitätsprotokoll (aktives Fenster)
        "tracking_enabled": True,
        "tracking_idle_minutes": 5,
        "tracking_ignore": ["KeePass", "Bitwarden", "1Password", "Online-Banking"],
        # Fenster-Filter: "blacklist" = alles außer Sperrliste, "whitelist" = nur tracking_allow
        "tracking_mode": "blacklist",
        "tracking_skip": [],               # gar nicht aufzeichnen (Lücke)
        "tracking_allow": [],              # Erlaubt-Liste für den Whitelist-Modus
        "tracking_whitelist_other": "mask",  # andere Fenster: "mask" = "(andere)", "skip" = Lücke
        # Klassifizierung ohne KI (rules.py); Reihenfolge = Priorität
        "rules": rules.default_rules(),
        "rules_gap_minutes": 5,
        "rules_min_minutes": 5,
        "show_pc_in_list": False,

        "pbx_reader_enabled": False,  # 3CX direkt über Edge im Hintergrund lesen
        "itm_url": "https://app.itm-gruppe.com",
        "itm_reader_enabled": False,  # Personalzeiten aus der ITM-Zeiterfassung lesen
        "close_to_tray": True,

        # Tagesliste: "grouped" (zusammengefasst), "single" (einzeln), "blocks" (Arbeitsblöcke)
        "list_view": "grouped",
        "merge_gap_minutes": 5,    # Verbindungen mit kürzerer Pause werden eine Zeile
        "block_gap_minutes": 10,   # Einträge mit kürzerer Pause werden ein Arbeitsblock
        "teamviewer_names": {},    # TeamViewer-ID -> Name, z. B. {"1076789144": "Müller GmbH"}

        # KI-Vorschläge (Anthropic). Der API-Schlüssel steht nicht hier, sondern lokal.
        "ai_model": "claude-opus-5-5",
        "ai_effort": "low",
        "ai_send_window_titles": True,
        "ai_auto": False,          # vergangene Tage beim Anzeigen automatisch einordnen

        # Eigene Zeilen oben in der Timeline: Doku (eigene Tätigkeiten), Regeln, KI
        "timeline_rows": {"doc": True, "rule": True, "ai": True},
        # Nachfragen nach erkannten Tätigkeiten ("Was hast du gemacht?")
        "prompt_mode": "window",       # "window" (kleines Fenster), "tray" (nur Meldung), "off"
        "prompt_min_minutes": 5,       # kürzere Tätigkeiten nicht nachfragen
        "prompt_sources": ["connections", "calls"],  # auch "rules" (Blöcke aus den Regeln)
        "prompt_snooze_minutes": 15,   # "Später fragen"
        "prompt_on_quit": True,        # beim Beenden an offene Tätigkeiten erinnern
        "prompt_end_of_day": True,     # nach Feierabend an offene Tätigkeiten erinnern
    }
