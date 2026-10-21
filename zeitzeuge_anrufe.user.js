// ==UserScript==
// @name         Zeitzeuge – Anrufliste übertragen
// @namespace    zeitzeuge
// @version      1.2
// @description  Liest die Anrufliste im 3CX-Webclient aus und schickt sie an Zeitzeuge (127.0.0.1:8765)
// @include      https://voice.visaas.de:5001/*
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// ==/UserScript==

(function () {
  "use strict";

  const ZEITZEUGE = "http://127.0.0.1:8765";
  const ZEITZEUGE_URL = ZEITZEUGE + "/anrufe";
  const INTERVALL_MS = 60 * 1000; // jede Minute
  const WOCHENTAGE = ["sonntag", "montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag"];

  const pad = (n) => String(n).padStart(2, "0");
  const fmt = (d) =>
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:00`;

  // "Heute", "Gestern", "Montag"/"Mo", "21.10.2026", "21.10." -> Date (nur Tag)
  function parseTag(text) {
    const heute = new Date();
    heute.setHours(0, 0, 0, 0);
    const t = text.trim().toLowerCase();
    if (t === "heute") return heute;
    if (t === "gestern") return new Date(heute.getTime() - 864e5);
    const wt = WOCHENTAGE.findIndex((w) => w === t || w.slice(0, 2) === t.replace(".", ""));
    if (wt >= 0) {
      let diff = (heute.getDay() - wt + 7) % 7 || 7;
      return new Date(heute.getTime() - diff * 864e5);
    }
    const m = t.match(/^(\d{1,2})\.(\d{1,2})\.(\d{2,4})?$/);
    if (m) {
      let jahr = m[3] ? Number(m[3]) : heute.getFullYear();
      if (jahr < 100) jahr += 2000;
      return new Date(jahr, Number(m[2]) - 1, Number(m[1]));
    }
    return null;
  }

  // "9:12" -> 552, "1:02:03" -> 3723
  function parseDauer(text) {
    if (!text) return 0;
    return text.split(":").map(Number).reduce((s, v) => s * 60 + v, 0);
  }

  function richtung(item) {
    // Richtung steckt im Icon (Klasse/Name/aria-label). Rote Icons = verpasst.
    const icon = item.querySelector("svg, i, img, [class*='icon']");
    const info = icon
      ? (icon.outerHTML.slice(0, 400) + " " + (icon.getAttribute("aria-label") || "")).toLowerCase()
      : "";
    if (/missed|verpasst|unanswered|nicht.?angenommen/.test(info)) return "Verpasst";
    if (/outgoing|outbound|ausgehend/.test(info)) return "Ausgehend";
    if (/incoming|inbound|eingehend/.test(info)) return "Eingehend";
    return "Anruf";
  }

  function leseEintrag(item) {
    const zeilen = item.innerText
      .split("\n")
      .map((z) => z.trim())
      .filter((z) => z && z !== "CRM" && !/^[A-ZÄÖÜ]{1,3}$/.test(z)); // Avatar-Initialen weg

    // Zeile mit Datum: "Heute 10:55 • 9:12 • via Max Muster 700"
    const metaIdx = zeilen.findIndex((z) => /^\S+\s+\d{1,2}:\d{2}\b/.test(z) && parseTag(z.split(/\s+/)[0]));
    if (metaIdx < 0) return null;
    const teile = zeilen[metaIdx].split("•").map((t) => t.trim());
    const [tagText, uhrzeit] = teile[0].split(/\s+/);
    const tag = parseTag(tagText);
    const [hh, mm] = uhrzeit.split(":").map(Number);
    tag.setHours(hh, mm, 0, 0);

    const dauerText = teile.slice(1).find((t) => /^\d+:\d{2}(:\d{2})?$/.test(t));
    const viaText = teile.slice(1).find((t) => t.startsWith("via "));

    // Name + Nummer stehen vor der Datumszeile (eine oder zwei Zeilen)
    const kopf = zeilen.slice(0, metaIdx).join(" ").trim();
    const nr = kopf.match(/(\+?\d[\d ]{2,})$/);
    const nummer = nr ? nr[1].replace(/\s/g, "") : "";
    const name = (nr ? kopf.slice(0, nr.index) : kopf).trim() || nummer;

    return {
      start: fmt(tag),
      duration_s: parseDauer(dauerText),
      name,
      number: nummer,
      direction: dauerText ? richtung(item) : "Verpasst",
      via: viaText ? viaText.slice(4) : "",
    };
  }

  function sammeln() {
    const items = document.querySelectorAll("app-call-history-item, [data-qa='call-history-item']");
    const anrufe = [];
    items.forEach((it) => {
      try {
        const a = leseEintrag(it);
        if (a) anrufe.push(a);
        else console.debug("[Zeitzeuge] Eintrag nicht erkannt:", it.innerText);
      } catch (e) {
        console.debug("[Zeitzeuge] Fehler:", e, it.innerText);
      }
    });
    return anrufe;
  }

  // Als TK-Admin "als Benutzer angemeldet": 3CX zeigt dann einen Banner an.
  // Das Element gibt es immer, sichtbar/gefüllt ist es nur bei fremder Nebenstelle.
  function alsAndererAngemeldet() {
    const banner = document.querySelector("app-impersonation-banner");
    return !!banner && banner.offsetHeight > 0 && banner.innerText.trim() !== "";
  }

  function senden(manuell) {
    if (!location.hash.includes("call_history")) return;
    if (alsAndererAngemeldet()) {
      console.log("[Zeitzeuge] Angemeldet als andere Nebenstelle – nichts gesendet");
      if (manuell) knopf.textContent = "✗ Andere Nebenstelle – nicht gesendet";
      return;
    }
    const anrufe = sammeln();
    if (!anrufe.length) return;
    GM_xmlhttpRequest({
      method: "POST",
      url: ZEITZEUGE_URL,
      headers: { "Content-Type": "application/json" },
      data: JSON.stringify(anrufe),
      onload: (r) => {
        const neu = r.status === 200 ? JSON.parse(r.responseText).neu : "?";
        console.log(`[Zeitzeuge] ${anrufe.length} Anrufe gesendet, ${neu} neu`);
        if (manuell) knopf.textContent = `✓ ${anrufe.length} gesendet, ${neu} neu`;
      },
      onerror: () => {
        console.warn("[Zeitzeuge] nicht erreichbar – läuft Zeitzeuge?");
        if (manuell) knopf.textContent = "✗ Zeitzeuge nicht erreichbar";
      },
    });
  }

  // Kleiner Knopf unten rechts zum manuellen Senden
  const knopf = document.createElement("button");
  knopf.textContent = "→ Zeitzeuge";
  Object.assign(knopf.style, {
    position: "fixed", right: "12px", bottom: "12px", zIndex: 99999,
    padding: "6px 10px", borderRadius: "6px", border: "1px solid #888",
    background: "#fff", color: "#222", cursor: "pointer", fontSize: "12px",
  });
  knopf.onclick = () => senden(true);
  document.body.appendChild(knopf);

  // Bei Zeitzeuge melden (für die Statusanzeige im Einrichtungsassistenten)
  GM_xmlhttpRequest({ method: "GET", url: `${ZEITZEUGE}/ping?v=${GM_info.script.version}` });

  setTimeout(() => senden(false), 5000);
  setInterval(() => senden(false), INTERVALL_MS);
})();
