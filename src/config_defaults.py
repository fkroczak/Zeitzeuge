"""Standardwerte der Einstellungen (zeitzeuge_config.json).

Laden, Ergänzen und Speichern: load_config_with_defaults/save_config in main_timeline.py.
"""
import os

import rules
import snippets
import tickets
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
            "RDP-Sitzung":           "#BB8400",  # Gelb
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
            "RDP-Verbindung":        "#BB8400",
            "SSH":                   "#E06D10",
            "VPN":                   "#0F9D8A",
            "Website-Verbindung":    "#139FB3",
        },

        "suggestion_colors": {
            "light": {"background": "#B4B4B4", "text": "#14181D"},
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
        # FortiClient: eigene Trace-Logs (sonst Adapter-Meldungen aus charon.log von Sophos)
        "forti_paths": [r"C:\Program Files\Fortinet\FortiClient\logs\trace\FortiVPN_*.log"],
        # RDM Better: Starts aus launcher.log (UTC), das Ende kommt aus der mstsc-Aufzeichnung
        "rdmbetter_enabled": True,
        "rdmbetter_paths": [r"%LOCALAPPDATA%\RDM Better\launcher.log"],
        # Remotedesktop (mstsc): offene Verbindungen alle 30 Sekunden selbst aufzeichnen
        "mstsc_enabled": True,
        "mstsc_events_enabled": True,  # zusätzlich RDPClient-Ereignisprotokoll lesen
        # Spuren vom PC (local_sources.py)
        "pcstate_enabled": True,        # gesperrt, Ruhezustand, aus, abgemeldet
        "shell_enabled": True,          # SSH (ssh, PuTTY, KiTTY, plink, WinSCP) und PowerShell-Fernsitzungen
        "wlan_enabled": True,           # verbundenes WLAN (SSID)
        "recent_files_enabled": True,   # zuletzt geöffnete Dateien (Recent-Ordner von Windows)
        "recent_files_dirs": [r"%APPDATA%\Microsoft\Windows\Recent"],
        "travel_enabled": True,         # vermutete Fahrten zu Terminen mit Ort und zu Kundennetzen
        "travel_ignore_locations": [],  # Orte, die keine Fahrt sind (z. B. Besprechungsraum, Büro)
        "travel_max_minutes": 90,       # längste Fahrt vor oder nach einem Termin
        "travel_home_address": "",     # Startadresse (Büro) für berechnete Fahrzeiten zu Kunden
        "travel_places": [],            # bekannte Orte: [{"name": "Besprechungsraum", "minutes": 0}, …]
        "browser_enabled": True,        # Browser-Verlauf: nur Domain und Ticketnummer
        "browser_paths": [
            r"%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\History",
            r"%LOCALAPPDATA%\Google\Chrome\User Data\Default\History",
        ],
        "browser_ignore_domains": ["google.com", "google.de", "bing.com", "duckduckgo.com",
                                   "login.microsoftonline.com", "login.live.com", "localhost"],
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
        # Design „Wie Windows“ (Menü Ansicht): Hell/Dunkel folgt dem App-Modus von Windows
        "theme_follow_system": False,
        # Timeline: Zeilen abwechselnd grau hinterlegen statt feiner Linien (Ansicht → Zeilen der Timeline)
        "timeline_stripes": False,
        # Aktivitätsdetails: Werte in schreibgeschützten Textfeldern statt als Text (zum Kopieren)
        "detail_text_fields": False,
        # Eigene Farben (Menü Ansicht → Design, theme.custom_theme): Grundlage und Grundfarben
        "custom_theme": False,
        "custom_colors": {},
        "start_minimized": False,

        # Anrufe aus 3CX
        "calls_ignore_missed": True,
        "calls_min_duration": 0,
        "calls_days_back": 14,  # 3CX: so viele Tage zurück lesen
        "calls_3cx_url": "https://voice.visaas.de:5001",
        # Kollegen (colleagues.py): Durchwahlen, Handys von Kollegen und die Zentrale erkennt
        # Zeitzeuge selbst; weitere Nummern hier, Anfang mit * („02542917918*“)
        "colleagues_auto": True,
        "colleague_numbers": [],
        # Kundenliste aus den Matrix42-Buchungen lernen: sichere Spuren (Telefonnummer,
        # TeamViewer-ID, RDM, VPN) von selbst übernehmen (customer_discovery.py)
        "customers_auto_learn": True,

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
        # Anmeldung ohne Edge: Benutzer und Mandant (Passwort wird nie gespeichert)
        "itm_user": "",
        "itm_mandant": 0,
        "itm_auth_url": "",  # leer: Anmeldedienst aus den Einstellungen der App (ApiUri)
        # Matrix42 (nur im Firmennetz): gebuchte Zeiten aus dem Service-Desk-Kalender
        # Adresse der Kalenderseite (Service Desk → Kalender, aus der Adresszeile kopieren)
        "m42_url": "https://support.itm-gruppe.com/wm/app-ServiceDesk/search-page/"
                   "c2b533af-5764-ef11-debc-0050569e2f05",
        "m42_reader_enabled": False,
        "m42_weeks_back": 4,          # so viele Wochen zurück einmal pro Sitzung lesen
        "m42_gap_minutes": 5,         # kürzere Lücken ohne Buchung zählen nicht
        # Buchungen über die Schnittstelle lesen (wie die Kalenderseite selbst); geht das
        # nicht, liest Zeitzeuge sie wie bisher aus der Seite. Widget: aus dem Mitschnitt,
        # die Seite verrät ihr eigenes meist selbst.
        "m42_api": True,
        "m42_widget_id": "05d8b58d-5764-ef11-debc-0050569e2f05",
        # In Matrix42 buchen: zuletzt gewählte Tätigkeitsart (10 = Administration) und, falls
        # Matrix42 sie ändert, die Kennungen aus dem Buchungs-Mitschnitt (m42_booking.DEFAULT_IDS)
        "m42_activity_type": 10,
        "m42_booking_ids": {},
        # Zwei PCs (z. B. Arbeits-PC und PAW): "paw" = nur RDM sammeln, kein Edge, keine Nachfragen
        "pc_role": "",
        "export_days": 31,            # Zeitraum beim Export für den anderen PC
        "close_to_tray": True,
        "tray_hint_on_close": True,   # Meldung „Zeitzeuge läuft weiter“ beim Schließen des Fensters

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

        # Zeilen der Timeline, jede einzeln aus- und einblendbar (timeline_only.TIMELINE_ROWS)
        "timeline_rows": {"pc": True, "work": True, "doc": True, "m42": True, "rule": False, "ai": True,
                          "call": True, "outlook": True, "vpn": True, "tv": True, "pcstate": True,
                          "wlan": True, "files": True, "other": True},
        # Nachfragen nach erkannten Tätigkeiten ("Was hast du gemacht?")
        "prompt_mode": "window",       # "window" (kleines Fenster), "tray" (nur Meldung), "off"
        # Erst ab dieser Dauer (Minuten) nachfragen, je Art der Tätigkeit
        "prompt_thresholds": {"connections": 1, "calls": 1, "pc": 15, "meetings": 5, "mails": 0,
                              "credentials": 0, "rules": 1},
        # Wonach gefragt wird; auch "credentials" (Zugangsdaten) und "rules" (Blöcke aus den Regeln)
        "prompt_sources": ["connections", "calls", "pc", "meetings", "mails"],
        "prompt_pc_skip": ["E-Mail / Kommunikation"],  # Arbeitsblöcke dieser Kategorien nicht nachfragen
        "prompt_topic_gap_minutes": 15,  # gleicher Kunde mit kürzerem Abstand: eine Nachfrage
        "prompt_snooze_minutes": 15,   # "Später fragen"
        # Nach so vielen Minuten ohne Maus/Tastatur bei der ersten Eingabe fragen,
        # was in der Zeit war (Telefonat, Besprechung, Vor Ort …). 0 = aus. (idle_watch.py)
        "idle_prompt_minutes": 15,
        "prompt_on_quit": True,        # beim Beenden an offene Tätigkeiten erinnern
        "prompt_end_of_day": True,     # nach Feierabend an offene Tätigkeiten erinnern

        # Eintragen: Textbausteine, zuletzt benutzte Texte, Ticket-Format, Ticketnummern
        # (snippets.py, tickets.py, Dialog snippets_dialogs.py)
        "snippets": list(snippets.DEFAULT_SNIPPETS),  # Textbausteine im Eintragen-Dialog
        "snippets_recent": True,       # zuletzt benutzte Texte zum gewählten Kunden anbieten
        "ticket_format": "",           # Kopieren: "" = wie eingegeben, "dash" = "- " / "-- "
        "ticket_patterns": list(tickets.DEFAULT_PATTERNS),  # Ticketnummern vorschlagen (Regex)

        # --- Abrechnung und Datenschutz (billing.py, retention.py) ---
        # Abrechnungstakt: angefangene Viertelstunde zählt. Modus "up" (aufrunden),
        # "nearest" (auf den nächsten Takt), "off" (echte Dauer wie früher)
        "billing_step_minutes": 15,
        "billing_mode": "up",
        "billing_customers": {},       # Ausnahmen: Kunde -> {"step": 30, "mode": "nearest"}
        # Spuren-Verlauf (Spuren vom PC, Remotedesktop, VPN): Einträge älter als so viele Tage
        # löschen (Einstellungen → Daten & Schutz, 30–3650). Tätigkeiten bleiben immer erhalten.
        "trace_history_days": 365,
        # PC-Verlauf (aktive Fenster) nach so vielen Tagen automatisch löschen. Standard: aus.
        # Tätigkeiten, Buchungen, KI-Vorschläge, Anrufe usw. bleiben immer erhalten.
        "pc_history_purge": False,
        "pc_blocks": True,          # PC-Aktivität als Arbeitsblöcke (focus.py)
        "pc_jump_seconds": 120,     # kürzere Fensterwechsel zählen zur Haupttätigkeit
        "pc_history_days": 90,

        # --- Kunden: Kundenliste und Lernen aus Korrekturen (customers.py, learning.py)
        # Kunde -> Spuren (TeamViewer-ID, RDM, VPN, Telefon, E-Mail-Domain). Nutzdaten:
        # steht verschlüsselt in der Datenbank (Ablage "kunden"), nicht in dieser Datei.
        "customers": [],
        # Beim Eintragen „Kunde für … merken“ auch für RDM, VPN, Telefon, E-Mail anbieten
        # (TeamViewer wie bisher immer)
        "customers_learn": True,
        # Beim Eintragen „Als Regel merken“ anbieten, wenn du die Kategorie änderst
        "rules_learn_offer": True,

        # Buchungsquote und Prüfung bei Feierabend (booking_rate.py, day_checks.py, week_dialogs.py)
        "booking_target_percent": 80,  # Ziel: so viel der Personalzeit in Matrix42 buchen
        "booking_rate_status": True,   # Quote heute / 7 Tage in der Statuszeile zeigen
        "day_checks_enabled": True,    # bei Feierabend Pausen, Stempelung und Buchungen prüfen
        "day_checks_pc_minutes": 10,   # ab so vielen Minuten "PC aktiv, aber ausgestempelt"
        # Tagesabschluss (day_close.py, app_day_close.py, day_close_dialog.py)
        "day_close_end_of_day": True,  # Feierabend-Meldung nennt den Tagesabschluss, Klick öffnet ihn
        "day_close_gap_minutes": 10,   # kürzere Lücken in der Personalzeit gehören zum Nachbarblock
        "day_close_min_minutes": 5,    # kürzere Blöcke gehen im Nachbarn auf
        # Zeit ohne Kunden (E-Mail, Excel …) auf ein internes Ticket: {"customer", "ticket", "category"}
        "day_close_internal": {},

        # Outlook und Teams (outlook_data.py, teams_calls.py, outlook_reader.py, app_outlook.py).
        # Standardmäßig aus: Zeitzeuge steuert Outlook nicht ungefragt an.
        "outlook_enabled": False,           # Termine und gesendete Mails aus dem klassischen Outlook
        "outlook_calendar_enabled": True,   # Kalender (Termine, Teams-Besprechungen)
        "outlook_mails_enabled": True,      # Gesendete Elemente
        "outlook_mails_external_only": True,  # nur Mails mit Empfängern außerhalb der eigenen Firma
        "outlook_own_domains": [],          # eigene Firmendomains; leer: aus Outlook erkannt
        "outlook_mail_minutes": 3,          # so breit steht eine gesendete Mail in der Timeline
        "outlook_days_back": 14,            # so viele Tage zurück regelmäßig lesen
        "outlook_interval_minutes": 10,     # so oft Outlook lesen
        "outlook_calendar_folder": "",      # leer: Standardkalender, sonst z. B. \\name@firma.de\Kalender
        "outlook_sent_folder": "",          # leer: Gesendete Elemente
        "outlook_start_if_closed": False,   # Outlook starten, wenn es nicht läuft (sonst warten)
        "outlook_check_body": True,         # Teams-Link auch im Text der Einladung suchen
        "teams_calls_enabled": False,       # Teams-Anrufe (Mikrofon-Nutzung von Teams, Teams-Logs)
        "teams_logs_enabled": True,         # zusätzlich die Logs des neuen Teams auswerten
        "teams_min_seconds": 30,            # kürzere Mikrofon-Nutzung zählt nicht als Anruf
        "outlook_replies_enabled": True,    # eingegangene Mails, auf die du geantwortet hast
        "teams_chats_enabled": False,       # Teams-Chats aus dem Postfach (über Outlook), nur Zeit und Domains
        "teams_chats_external_only": True,  # nur Chats mit anderen Firmen
    }
