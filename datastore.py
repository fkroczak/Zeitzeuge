"""
Eine verschlüsselte SQLite-Datenbank für alle Nutzdaten (ohne Qt).

Tabellen:
    docs(name, day, data)        ein JSON-Dokument je Ablage und Tag (day "" = ohne Tag)
    rows(id, name, day, data)    angehängte Zeilen (aktive Fenster, alle paar Sekunden)
    meta(key, value)             technische Angaben (Version, Prüfwert, Migrationsstand)
    key_slots(id, kind, label, created, data)   verpackte Datenschlüssel (siehe datakey.py)

Klartext sind nur name (z. B. "anrufe") und day (JJJJ-MM-TT). Alle Inhalte stehen in
data, verschlüsselt mit AES-256-GCM; name und day sind als AAD gebunden.

Die Module behalten ihre bisherigen Pfade (anrufe.json, taetigkeiten/ …). locate(pfad)
liefert dazu den Speicher (Datenordner = Ordner des Pfads) und den Ablagenamen
(Dateiname ohne Endung). Liegt dort noch die alte Datei, wird sie beim ersten Zugriff
übernommen (Migration), geprüft und nach alt-<Datum>/ verschoben.

Mehrere Threads: eine Verbindung, ein Lock, kurze Transaktionen, WAL. Ein Absturz
mitten im Schreiben verliert höchstens die laufende Transaktion.
"""

import json
import os
import shutil
import socket
import sqlite3
import threading
import time
from datetime import date, datetime

import datakey
import safe_io

SCHEMA_VERSION = 1
DB_NAME = "zeitzeuge.db"
CHECK_PLAIN = b"zeitzeuge-pruefwert"
RETRIES, RETRY_WAIT = 5, 0.2

SCHEMA = """
CREATE TABLE IF NOT EXISTS docs (name TEXT NOT NULL, day TEXT NOT NULL, data BLOB NOT NULL,
                                 PRIMARY KEY (name, day)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS rows (id INTEGER PRIMARY KEY, name TEXT NOT NULL, day TEXT NOT NULL,
                                 data BLOB NOT NULL);
CREATE INDEX IF NOT EXISTS rows_day ON rows (name, day);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS key_slots (id INTEGER PRIMARY KEY, kind TEXT NOT NULL,
                                      label TEXT NOT NULL DEFAULT '', created TEXT NOT NULL,
                                      data BLOB NOT NULL);
"""

RECOVERY = "wiederherstellung"


class Locked(Exception):
    """Kein Schlüsselfach passt (anderer PC oder Windows-Benutzer): Daten sind gesperrt.
    Dann nie neu anlegen oder überschreiben, sondern den Wiederherstellungsschlüssel erfragen."""


class Busy(OSError):
    """Datenbank gerade nicht beschreibbar (gesperrt, Platte voll …)."""


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _label():
    """PC und Windows-Benutzer des Fachs (nur zur Anzeige im Schutz-Dialog)."""
    pc = os.environ.get("COMPUTERNAME") or socket.gethostname() or "PC"
    user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    return f"{pc}\\{user}" if user else pc


def _dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=False).encode("utf-8")


class Store:
    def __init__(self, path, data_dir=None):
        self.path = path
        self.data_dir = data_dir or os.path.dirname(path)
        self._lock = threading.RLock()
        self._conn = None
        self._cipher = None
        self.changes = 0  # Zähler für Sicherung und Zwischenspeicher
        self._retry_at = {}  # gesperrte alte Dateien: nicht vor diesem Zeitpunkt erneut
        self._hit_lock = False
        self.migrated = []  # Meldungen der Migration (für Statuszeile/Log)

    # ------------------------------------------------------------ Öffnen

    def open(self):
        """Datei öffnen (oder anlegen) und Tabellen sicherstellen. Busy, wenn gesperrt."""
        with self._lock:
            if self._conn:
                return self
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            last = conn = None
            for attempt in range(RETRIES + 1):
                try:
                    conn = sqlite3.connect(self.path, timeout=10, isolation_level=None,
                                           check_same_thread=False)
                    conn.execute("PRAGMA busy_timeout = 10000")
                    mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()[0]
                    if mode.lower() != "wal":
                        safe_io.log(f"Datenbank: WAL nicht möglich ({mode}), weiter mit {mode}")
                    conn.execute("PRAGMA synchronous = NORMAL")
                    conn.executescript(SCHEMA)
                    self._conn = conn
                    break
                except sqlite3.DatabaseError as e:
                    last = e
                    if conn is not None:
                        conn.close()
                        conn = None
                    if "not a database" in str(e) or "malformed" in str(e):
                        raise Busy(f"{os.path.basename(self.path)} ist beschädigt ({e}). "
                                   "Zeitzeuge ändert daran nichts.") from e
                    time.sleep(RETRY_WAIT)
            if not self._conn:
                raise Busy(f"{os.path.basename(self.path)} lässt sich nicht öffnen ({last})")
            if not self._meta("schema"):
                self._set_meta("schema", str(SCHEMA_VERSION))
            return self

    def close(self):
        with self._lock:
            if self._conn:
                try:
                    self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                except sqlite3.DatabaseError:
                    pass
                self._conn.close()
                self._conn = None

    @property
    def unlocked(self):
        return self._cipher is not None

    def _meta(self, key):
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def _set_meta(self, key, value):
        self._conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))

    def _has_data(self):
        return bool(self._conn.execute("SELECT 1 FROM docs LIMIT 1").fetchone()
                    or self._conn.execute("SELECT 1 FROM rows LIMIT 1").fetchone())

    def _slots(self, kind=None):
        sql = "SELECT id, kind, label, created, data FROM key_slots"
        args = ()
        if kind:
            sql, args = sql + " WHERE kind = ?", (kind,)
        return self._conn.execute(sql + " ORDER BY id", args).fetchall()

    # ------------------------------------------------------------ Schlüssel

    def _use_key(self, key):
        cipher = datakey.Cipher(key)
        check = self._meta("pruefwert")
        if check is not None:
            cipher.decrypt(bytes.fromhex(check), b"pruefwert")  # WrongKey, wenn falsch
        self._cipher = cipher
        self._key = key

    def unlock(self):
        """Mit dem Fach dieses Windows-Benutzers öffnen. Neue, leere Datenbank: Schlüssel
        anlegen. Locked, wenn kein Fach passt."""
        with self._lock:
            self.open()
            if self._cipher:
                return self
            slots = self._slots()
            if not slots:
                if self._has_data() or self._meta("pruefwert"):
                    raise Locked("Die Datenbank hat keine Schlüsselfächer mehr.")
                key = datakey.new_key()
                self._write_tx(lambda c: self._init_key(c, key))
                self._use_key(key)
                return self
            for _id, kind, _lbl, _created, data in slots:
                if kind == RECOVERY:
                    continue
                try:
                    self._use_key(datakey.auto_unwrap(kind, data))
                    return self
                except datakey.WrongKey:
                    continue
            raise Locked("Kein Schlüsselfach passt zu diesem Windows-Benutzer.")

    def _init_key(self, conn, key):
        cipher = datakey.Cipher(key)
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('pruefwert', ?)",
                     (cipher.encrypt(CHECK_PLAIN, b"pruefwert").hex(),))
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('angelegt', ?)", (_now(),))
        conn.execute("INSERT INTO key_slots (kind, label, created, data) VALUES (?, ?, ?, ?)",
                     (datakey.auto_kind(), _label(), _now(), datakey.auto_wrap(key)))

    def unlock_with_code(self, code):
        """Mit dem Wiederherstellungsschlüssel öffnen und ein Fach für diesen
        Windows-Benutzer anlegen (nächster Start ohne Abfrage).
        BadCode bei Tippfehler, WrongKey wenn er nicht passt."""
        datakey.normalize_code(code)
        with self._lock:
            self.open()
            for _id, _kind, _lbl, _created, data in self._slots(RECOVERY):
                try:
                    key = datakey.unwrap_with_code(data, code)
                    self._use_key(key)
                except datakey.WrongKey:
                    continue
                self._write_tx(lambda c: c.execute(
                    "INSERT INTO key_slots (kind, label, created, data) VALUES (?, ?, ?, ?)",
                    (datakey.auto_kind(), _label(), _now(), datakey.auto_wrap(key))))
                return self
            raise datakey.WrongKey("Der Wiederherstellungsschlüssel passt nicht zu diesen Daten.")

    def has_recovery(self):
        with self._lock:
            return bool(self._slots(RECOVERY))

    def new_recovery_code(self):
        """Neuen Wiederherstellungsschlüssel erzeugen. Der alte wird ungültig."""
        self._need_key()
        code = datakey.new_code()
        blob = datakey.wrap_with_code(self._key, code)

        def tx(c):
            c.execute("DELETE FROM key_slots WHERE kind = ?", (RECOVERY,))
            c.execute("INSERT INTO key_slots (kind, label, created, data) VALUES (?, '', ?, ?)",
                      (RECOVERY, _now(), blob))
        self._write_tx(tx)
        return code

    def protection(self):
        """Stand des Schutzes für die Anzeige."""
        with self._lock:
            slots = self._slots()
            auto = [s for s in slots if s[1] != RECOVERY]
            rec = [s for s in slots if s[1] == RECOVERY]
            return {"auto": [(s[1], s[2], s[3]) for s in auto],
                    "recovery": rec[0][3] if rec else None,
                    "created": self._meta("angelegt"),
                    "path": self.path}

    def _need_key(self):
        if not self._cipher:
            raise Locked("Datenbank ist noch gesperrt")

    # ------------------------------------------------------------ Schreiben

    def _write_tx(self, func):
        """func(conn) in einer Transaktion, bei Sperre kurz erneut. Busy, wenn es nicht geht."""
        with self._lock:
            self.open()
            last = None
            for attempt in range(RETRIES + 1):
                try:
                    self._conn.execute("BEGIN IMMEDIATE")
                    try:
                        result = func(self._conn)
                        self._conn.execute("COMMIT")
                    except BaseException:
                        self._conn.execute("ROLLBACK")
                        raise
                    self.changes += 1
                    return result
                except sqlite3.OperationalError as e:
                    last = e
                    if "locked" in str(e) or "busy" in str(e):
                        time.sleep(RETRY_WAIT)
                        continue
                    break
                except sqlite3.DatabaseError as e:
                    last = e
                    break
            raise Busy(f"Datenbank: Schreiben fehlgeschlagen ({last})")

    def _enc(self, table, name, day, obj):
        return self._cipher.encrypt(_dumps(obj), f"{table}|{name}|{day}".encode("utf-8"))

    def _dec(self, table, name, day, blob):
        return json.loads(self._cipher.decrypt(blob, f"{table}|{name}|{day}".encode("utf-8")))

    # ------------------------------------------------------------ Dokumente

    def get(self, name, day="", default=None):
        self._need_key()
        with self._lock:
            row = self._conn.execute("SELECT data FROM docs WHERE name = ? AND day = ?",
                                     (name, day)).fetchone()
        if not row:
            return default
        try:
            return self._dec("docs", name, day, row[0])
        except (datakey.WrongKey, ValueError) as e:
            safe_io.report(f"Datenbank: Eintrag {name}/{day or '-'} ist beschädigt und wird übersprungen ({e})")
            return default

    def put(self, name, day, obj):
        self.put_many(name, {day: obj})

    def put_many(self, name, by_day, delete=()):
        """Mehrere Tage in einer Transaktion schreiben (None löscht den Tag)."""
        self._need_key()
        items = [(d, None if o is None else self._enc("docs", name, d, o)) for d, o in by_day.items()]
        items += [(d, None) for d in delete]

        def tx(c):
            for d, blob in items:
                if blob is None:
                    c.execute("DELETE FROM docs WHERE name = ? AND day = ?", (name, d))
                else:
                    c.execute("INSERT OR REPLACE INTO docs (name, day, data) VALUES (?, ?, ?)",
                              (name, d, blob))
        self._write_tx(tx)

    def delete(self, name, day=""):
        self.put_many(name, {}, delete=[day])

    def clear(self, name):
        self._write_tx(lambda c: (c.execute("DELETE FROM docs WHERE name = ?", (name,)),
                                  c.execute("DELETE FROM rows WHERE name = ?", (name,))))

    def has(self, name, day=""):
        with self._lock:
            self.open()
            return bool(self._conn.execute("SELECT 1 FROM docs WHERE name = ? AND day = ?",
                                           (name, day)).fetchone())

    def days(self, name):
        with self._lock:
            self.open()
            return [r[0] for r in self._conn.execute(
                "SELECT day FROM docs WHERE name = ? ORDER BY day", (name,))]

    def all(self, name):
        """{Tag: Dokument} einer Ablage."""
        self._need_key()
        with self._lock:
            rows = self._conn.execute("SELECT day, data FROM docs WHERE name = ? ORDER BY day",
                                      (name,)).fetchall()
        result = {}
        for d, blob in rows:
            try:
                result[d] = self._dec("docs", name, d, blob)
            except (datakey.WrongKey, ValueError) as e:
                safe_io.report(f"Datenbank: Eintrag {name}/{d or '-'} ist beschädigt und wird übersprungen ({e})")
        return result

    # ------------------------------------------------------------ Zeilen

    def append(self, name, day, obj):
        self.append_many(name, [(day, obj)])

    def append_many(self, name, items):
        self._need_key()
        blobs = [(name, d, self._enc("rows", name, d, o)) for d, o in items]
        self._write_tx(lambda c: c.executemany(
            "INSERT INTO rows (name, day, data) VALUES (?, ?, ?)", blobs))

    def rows(self, name, day):
        self._need_key()
        with self._lock:
            blobs = self._conn.execute("SELECT data FROM rows WHERE name = ? AND day = ? ORDER BY id",
                                       (name, day)).fetchall()
        aad = f"rows|{name}|{day}".encode("utf-8")
        decrypt = self._cipher.decrypt
        result, bad = [], 0
        for (blob,) in blobs:
            try:
                result.append(json.loads(decrypt(blob, aad)))
            except (datakey.WrongKey, ValueError):
                bad += 1
        if bad:
            safe_io.report(f"Datenbank: {bad} beschädigte Zeilen in {name}/{day} übersprungen")
        return result

    def row_count(self, name, day=None):
        with self._lock:
            self.open()
            if day is None:
                return self._conn.execute("SELECT COUNT(*) FROM rows WHERE name = ?", (name,)).fetchone()[0]
            return self._conn.execute("SELECT COUNT(*) FROM rows WHERE name = ? AND day = ?",
                                      (name, day)).fetchone()[0]

    def row_days(self, name):
        with self._lock:
            self.open()
            return [r[0] for r in self._conn.execute(
                "SELECT DISTINCT day FROM rows WHERE name = ? ORDER BY day", (name,))]

    def rows_before(self, name, day):
        """(Anzahl Tage, Anzahl Zeilen) einer Ablage vor day (JJJJ-MM-TT, day selbst nicht)."""
        with self._lock:
            self.open()
            n_days, n_rows = self._conn.execute(
                "SELECT COUNT(DISTINCT day), COUNT(*) FROM rows WHERE name = ? AND day < ?",
                (name, day)).fetchone()
        return n_days, n_rows

    def delete_rows_before(self, name, day, limit=None):
        """Zeilen einer Ablage vor day löschen (day selbst bleibt), in einer Transaktion.
        limit: höchstens so viele Zeilen (die ältesten zuerst), damit ein großer Bestand in
        kurzen Schritten gelöscht werden kann. Gibt die Zahl gelöschter Zeilen zurück.

        Gelöschte Seiten überschreibt SQLite mit Nullen (secure_delete). Die Datei wird
        nicht verkleinert (kein VACUUM): Der Platz wird für neue Zeilen wiederverwendet."""
        def tx(c):
            if limit:
                cur = c.execute("DELETE FROM rows WHERE id IN (SELECT id FROM rows WHERE name = ? "
                                "AND day < ? ORDER BY day, id LIMIT ?)", (name, day, int(limit)))
            else:
                cur = c.execute("DELETE FROM rows WHERE name = ? AND day < ?", (name, day))
            return cur.rowcount
        with self._lock:
            self.open()
            self._conn.execute("PRAGMA secure_delete = ON")
            try:
                return self._write_tx(tx)
            finally:
                try:
                    self._conn.execute("PRAGMA secure_delete = OFF")
                except sqlite3.DatabaseError:
                    pass

    # ------------------------------------------------------------ Übersicht, Sicherung

    def stats(self):
        """Anzahl Tage/Zeilen je Ablage (nur technische Angaben)."""
        with self._lock:
            self.open()
            docs = dict(self._conn.execute("SELECT name, COUNT(*) FROM docs GROUP BY name").fetchall())
            rows = dict(self._conn.execute("SELECT name, COUNT(*) FROM rows GROUP BY name").fetchall())
        return {"docs": docs, "rows": rows}

    def backup(self, target):
        """Vollständige Kopie (ohne WAL-Dateien) nach target schreiben, atomar über .tmp.
        Die Kopie ist genauso verschlüsselt wie das Original."""
        tmp = f"{target}.tmp"
        with self._lock:
            self.open()
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
                dst = sqlite3.connect(tmp)
                try:
                    self._conn.backup(dst)
                    dst.execute("PRAGMA journal_mode = DELETE")
                finally:
                    dst.close()
                for attempt in range(RETRIES + 1):
                    try:
                        os.replace(tmp, target)
                        break
                    except PermissionError:
                        if attempt == RETRIES:
                            raise
                        time.sleep(RETRY_WAIT)
                self.backed_up = self.changes
                return True
            except (OSError, sqlite3.DatabaseError) as e:
                safe_io.report(f"Sicherung der Datenbank fehlgeschlagen: {e}")
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                return False

    backed_up = -1

    # ------------------------------------------------------------ Migration alter Dateien

    def migrate(self, name, path, kind):
        """Alte Datei/alten Ordner übernehmen. kind: siehe LEGACY. Übernommenes wird nach
        alt-<Datum>/ verschoben. Gesperrte Dateien bleiben liegen (nächster Start).
        Gibt die Zahl übernommener Einträge zurück."""
        if not os.path.exists(path):
            return 0
        if kind in ("row_files", "day_files") and not os.path.isdir(path):
            return 0  # an der Stelle eines Tagesordners liegt eine Datei: nicht anfassen
        if os.path.isdir(path):
            total = 0
            for fn in sorted(os.listdir(path)):
                ext = ".jsonl" if kind == "row_files" else ".json"
                if fn.endswith(ext) and len(fn) == 10 + len(ext):
                    total += self._migrate_file(name, os.path.join(path, fn), kind, fn[:10])
            if LEGACY_FILES.get(name) == os.path.basename(path):
                try:  # leerer alter Tagesordner (aktivitaet/ …) verschwindet
                    if not os.listdir(path):
                        os.rmdir(path)
                except OSError:
                    pass
            return total
        return self._migrate_file(name, path, kind)

    def _alt_target(self, path):
        alt = os.path.join(self.data_dir, f"alt-{date.today().isoformat()}")
        rel = os.path.relpath(path, self.data_dir)
        if rel.startswith(".."):
            rel = os.path.basename(path)
        target = os.path.join(alt, rel)
        n = 1
        while os.path.exists(target):
            n += 1
            target = os.path.join(alt, f"{rel}.{n}")
        return target

    def _move_old(self, path):
        target = self._alt_target(path)
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.move(path, target)
        except OSError as e:
            safe_io.log(f"Migration: {os.path.basename(path)} nicht verschoben ({e}), nächster Start")

    def _migrate_file(self, name, path, kind, day=None):
        self._need_key()
        try:
            st = os.stat(path)
        except OSError:
            return 0
        rel = os.path.relpath(path, self.data_dir).replace(os.sep, "/")
        marker = f"migriert:{rel}"
        sig = f"{st.st_size}:{st.st_mtime_ns}"
        with self._lock:
            if self._meta(marker) == sig:
                self._move_old(path)  # schon übernommen, nur das Verschieben fehlte
                return 0
        try:
            docs, rows = _read_legacy(path, kind, day)
        except safe_io.FileLocked:
            self._hit_lock = True
            safe_io.log(f"Migration: {rel} gerade gesperrt, wird später übernommen")
            return 0
        if not os.path.exists(path):  # kaputt: safe_io hat sie beiseitegelegt (.defekt-…)
            return 0
        enc_docs = {d: self._enc("docs", name, d, o) for d, o in docs.items()}
        enc_rows = [(name, d, self._enc("rows", name, d, o)) for d, o in rows]
        kept = []

        def tx(c):
            for d, blob in enc_docs.items():
                old = c.execute("SELECT data FROM docs WHERE name = ? AND day = ?", (name, d)).fetchone()
                if old:
                    # Schon neuere Daten in der DB (Datei war beim ersten Mal gesperrt): DB bleibt,
                    # die alte Datei liegt danach trotzdem in alt-<Datum>/
                    if self._dec("docs", name, d, old[0]) != docs[d]:
                        kept.append(d)
                    continue
                c.execute("INSERT INTO docs (name, day, data) VALUES (?, ?, ?)", (name, d, blob))
            before = {}
            for _n, d, _b in enc_rows:
                if d not in before:
                    before[d] = c.execute("SELECT COUNT(*) FROM rows WHERE name = ? AND day = ?",
                                          (name, d)).fetchone()[0]
            c.executemany("INSERT INTO rows (name, day, data) VALUES (?, ?, ?)", enc_rows)
            # Gegenprobe vor dem Abschluss: alles lesbar und vollständig?
            for d in docs:
                if d in kept:
                    continue
                blob = c.execute("SELECT data FROM docs WHERE name = ? AND day = ?", (name, d)).fetchone()
                if not blob or self._dec("docs", name, d, blob[0]) != docs[d]:
                    raise ValueError(f"Gegenprobe {rel} {d}")
            want = {}
            for _n, d, _b in enc_rows:
                want[d] = want.get(d, 0) + 1
            for d, n in want.items():
                got = c.execute("SELECT COUNT(*) FROM rows WHERE name = ? AND day = ?", (name, d)).fetchone()[0]
                if got != before[d] + n:
                    raise ValueError(f"Gegenprobe {rel} {d}: {got - before[d]} statt {n} Zeilen")
            c.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (marker, sig))
        try:
            self._write_tx(tx)
        except (Busy, ValueError) as e:
            safe_io.report(f"Migration von {rel} fehlgeschlagen ({e}). Die Datei bleibt, wie sie ist.")
            return 0
        count = sum(_count(o) for o in docs.values()) + len(rows)
        if kept:
            safe_io.log(f"Migration: {rel}: {len(kept)} Tage waren schon neuer in der Datenbank, "
                        "dort bleibt der neuere Stand")
        self._move_old(path)
        self.migrated.append((rel, count))
        safe_io.log(f"Migration: {rel} übernommen ({count} Einträge an {len(docs) or len({d for d, _ in rows})} Tagen)")
        return count

    def migrate_if_present(self, name, path, kind):
        """Bei jedem Zugriff: Liegt (wieder) eine alte Datei da, übernehmen. Kostet sonst
        nur ein os.path.exists. War sie gesperrt, erst nach einer Minute erneut versuchen."""
        if not os.path.exists(path):
            return
        if time.time() < self._retry_at.get(path, 0):
            return
        with self._lock:
            self._hit_lock = False
            self.migrate(name, path, kind)
            if self._hit_lock:
                self._retry_at[path] = time.time() + 60


def _count(obj):
    if isinstance(obj, list):
        return len(obj)
    if isinstance(obj, dict) and isinstance(obj.get("items"), list):
        return len(obj["items"])
    return 1


def _day_of(text):
    return text[:10] if isinstance(text, str) and len(text) >= 10 else ""


def _read_legacy(path, kind, day=None):
    """Alte Datei -> ({Tag: Dokument}, [(Tag, Zeile)]). FileLocked, wenn gesperrt."""
    docs, rows = {}, []
    if kind == "row_files":
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except PermissionError as e:
            raise safe_io.FileLocked(str(e)) from e
        for line in lines:
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict):
                rows.append((day or _day_of(obj.get("start")), obj))
        return docs, rows
    data = safe_io.read_json(path, None, raise_locked=True)
    if data is None:
        return docs, rows
    if kind == "day_files":
        if isinstance(data, dict):
            docs[day] = data
    elif kind == "single":
        docs[""] = data
    elif kind == "calls":
        for c in data if isinstance(data, list) else []:
            if isinstance(c, dict) and _day_of(c.get("start")):
                docs.setdefault(_day_of(c["start"]), []).append(c)
    elif kind == "days":
        if isinstance(data, dict):
            docs = {k: v for k, v in data.items() if isinstance(k, str)}
    elif kind == "m42":
        if isinstance(data, dict):
            tage = data.get("tage") if isinstance(data.get("tage"), dict) else {}
            read = data.get("gelesen") if isinstance(data.get("gelesen"), dict) else {}
            for d in set(tage) | set(read):
                docs[d] = {"items": tage.get(d) if isinstance(tage.get(d), list) else [],
                           "gelesen": read.get(d, "")}
    else:
        raise ValueError(f"unbekannte Art {kind}")
    return docs, rows


# ------------------------------------------------------------ Ablagen und Speicher je Ordner

# Bekannte alte Ablagen: Name -> Art. Unbekannte Namen (z. B. in Tests) nehmen die Art,
# die der Aufrufer angibt.
LEGACY = {
    "anrufe": "calls", "anrufe_stand": "single", "vpn_verbindungen": "single",
    "personalzeiten": "days", "m42_buchungen": "m42", "uebernommen": "single",
    "aktivitaet": "row_files", "taetigkeiten": "day_files", "ki_vorschlaege": "day_files",
}
LEGACY_FILES = {"anrufe": "anrufe.json", "anrufe_stand": "anrufe_stand.json",
                "vpn_verbindungen": "vpn_verbindungen.json", "personalzeiten": "personalzeiten.json",
                "m42_buchungen": "m42_buchungen.json", "uebernommen": "uebernommen.json",
                "aktivitaet": "aktivitaet", "taetigkeiten": "taetigkeiten",
                "ki_vorschlaege": "ki_vorschlaege"}
# Ablagen ohne alte Datei (gab es nur in der Datenbank), zur Übersicht:
#   "teamviewer_names" (ein Dokument), "outlook" (je Tag {termine, mails, gelesen},
#   outlook_data.py), "teams_anrufe" (je Tag eine Liste, teams_calls.py)

_stores = {}
_stores_lock = threading.Lock()


def _norm(folder):
    return os.path.normcase(os.path.abspath(folder))


def register(store):
    with _stores_lock:
        _stores[_norm(store.data_dir)] = store
    return store


def unregister(data_dir):
    with _stores_lock:
        store = _stores.pop(_norm(data_dir), None)
    if store:
        store.close()


def registered(data_dir):
    return _stores.get(_norm(data_dir))


def store_for_dir(data_dir):
    """Speicher eines Datenordners. Ist keiner angemeldet (Tests, Hilfsskripte), wird
    <Ordner>/zeitzeuge.db geöffnet und mit dem Fach dieses Benutzers entsperrt."""
    key = _norm(data_dir)
    with _stores_lock:
        store = _stores.get(key)
        if store is None:
            store = Store(os.path.join(data_dir, DB_NAME), data_dir).unlock()
            _stores[key] = store
    return store


def locate(path, kind):
    """Alter Pfad (Datei oder Tagesordner) -> (Speicher, Ablagename). Liegt dort noch die
    alte Datei, wird sie dabei übernommen."""
    path = os.path.abspath(path)
    name = os.path.splitext(os.path.basename(path))[0]
    store = store_for_dir(os.path.dirname(path))
    store.migrate_if_present(name, path, LEGACY.get(name, kind))
    return store, name


def migrate_all(store):
    """Alle bekannten alten Ablagen im Datenordner übernehmen (beim Start)."""
    total = 0
    for name, fn in LEGACY_FILES.items():
        total += store.migrate(name, os.path.join(store.data_dir, fn), LEGACY[name])
    return total
