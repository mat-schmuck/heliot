#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KATALOG DER EODHD-DATEN (Gerhard, 20.09.2026, S11)
==================================================
Gerhard: "wurden diese Daten katalogisiert, also irgendwo so dokumentiert,
dass nicht ich es von Hand nachschlagen muss, sondern Heliot und der Scanner
selbst wissen, was drinsteht und wo es liegt? Wenn ja, wo liegt dieser
Katalog; wenn nein, bitte einen anlegen, den die Systeme selbst nutzen
koennen." Bis zum 21.09.2026 gab es nur die Inventur vom 12.09.2026 und das
LIESMICH des Ordners eodhd, beides zum Lesen, nicht fuer Programme.

Dieses Skript legt den Katalog an, im PRIVATEN Datenrepo heliot-daten:
  eodhd_voll/katalog.json   fuer Programme
  eodhd_voll/katalog.md     zum Lesen
Er beschreibt, WAS in den Daten steht und WO es liegt, nie einen Wert. Die
Daten sind lizenziert (F17) und bleiben, wo sie sind; auch der Katalog liegt
nur im privaten Repo. Gerhards Entscheidung 10 gilt unveraendert: Genutzt
werden nur der Konsens und die einmalige Zuordnung von Branche und Typ. Der
Katalog sagt, was es gibt; er fuehrt nichts davon irgendwo zu.

INHALT
  ablagen     jede EODHD-Ablage des Datenrepos: Ordner, Herkunft, Inhalt
  zugriff     wie ein Programm an die Rohantwort eines Symbols kommt
  stufen      je Stufe des Vollabzugs: Umfang laut Symbolliste, Register
              nach Status, gepackte Groesse, Archive samt Release, und die
              Felder der Rohantworten mit dem Anteil der Symbole, bei denen
              sie gefuellt sind
  reihen      Reihen in den Rohantworten (Bilanz je Quartal, Ergebnisse je
              Meldetag, Besitzer, Bestandteile eines Index ...) mit der Zahl
              der Eintraege je Symbol und dem aeltesten und juengsten
              Stichtag
  konsens     die Konsens-Historie im Ordner eodhd: Zeilenarten und Felder
  dateien     jede Datei der Ordner eodhd_voll, eodhd (ohne die Ordner je
              Firma) und zuordnung: Groesse, Zeilen, Feldnamen

WIE GEZAEHLT WIRD
  Anteil = Symbole mit gefuelltem Feld durch alle gelesenen Symbole der
  Stufe. Leer sind None, leerer Text, NA, N/A, None, null, der Strich,
  leere Liste und leeres Objekt; die Null ist ein Wert. Eine Reihe erkennt
  das Skript an ihren Schluesseln: lauter Stichtage (JJJJ-MM-TT), lauter
  laufende Nummern, oder mindestens acht Namen mit je einem Objekt dahinter
  (Bestaende eines ETF). Je Symbol zaehlt es die Eintraege der Reihe und
  merkt aeltesten und juengsten Stichtag; die Felder darunter zaehlen im
  JUENGSTEN Eintrag (bei Nummern und Namen im ersten), im Pfad steht dann
  <Stichtag>, <Nr> oder <Name>. So bleibt der Katalog klein, und die Frage
  "ist das Feld zuletzt gefuellt?" ist beantwortet.

LIZENZ UND LOG: Das Log des Ablaufs (Repo heliot, oeffentlich) nennt nur
Zahlen, nie Namen, Kuerzel oder Werte.

Aufruf:
  python eodhd_katalog.py --noetig --daten DATENREPO
      "ja", wenn sich das Register seit dem letzten Katalog geaendert hat
  python eodhd_katalog.py --archive-liste --daten DATENREPO
      je benoetigtem Archiv eine Zeile "Release|Archiv"
  python eodhd_katalog.py --bauen --daten DATENREPO --archive ORDNER
  python eodhd_katalog.py --zeigen KATALOG.json [--stufe S] [--suche WORT]
  python eodhd_katalog.py --selbsttest
"""

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import statistics
import sys
import tarfile
from collections import Counter, defaultdict
from datetime import datetime, timezone

DATENREPO = "mat-schmuck/heliot-daten"
ORDNER_VOLL = "eodhd_voll"
ORDNER_KONSENS = "eodhd"
ORDNER_ZUORDNUNG = "zuordnung"
KATALOG_JSON = "katalog.json"
KATALOG_MD = "katalog.md"
FASSUNG = 1

# Wie eodhd_voll.STUFEN (Zweig fundament-phase1), in derselben Vorrangfolge.
STUFEN = [
    ("delisted_stock", "delistete Aktien (Common Stock)"),
    ("stock_boerse", "aktive Aktien an NYSE, Nasdaq, NYSE Arca, NYSE American, Cboe"),
    ("delisted_rest", "delistete Vorzugsaktien, Einheiten, Optionsscheine, Anleihen, ETFs und Fonds"),
    ("stock_otc", "aktive Aktien im Freiverkehr (OTC, Pink Sheets und andere)"),
    ("sonstige", "aktive Vorzugsaktien, Optionsscheine, Einheiten, Rechte, Anleihen"),
    ("etf", "aktive ETFs"),
    ("fund", "aktive Fonds"),
    ("index", "Indizes mit Komponenten und Mitgliedschaftsgeschichte"),
    ("makro", "Makro-Indikatoren je Land"),
]
STUFEN_NAMEN = [s for s, _ in STUFEN]
# Wie eodhd_voll.BOERSEN_HAUPT und die Typen dort.
BOERSEN_HAUPT = {"NYSE", "NASDAQ", "NYSE ARCA", "NYSE MKT", "NYSE AMERICAN", "AMEX", "BATS", "CBOE", "IEX"}
TYP_STAMM = {"common stock"}
TYP_ETF = {"etf"}
TYP_FONDS = {"fund", "mutual fund"}
ERLEDIGT = ("ok", "leer", "unbekannt")

ABLAGEN = [
    {"ordner": ORDNER_VOLL,
     "herkunft": "eodhd_voll.py (Zweig fundament-phase1), Ablauf eodhd_voll.yml, jede Nacht bis zum Ende des Abos "
                 "am 03.10.2026",
     "inhalt": "EODHD-Vollabzug: je Symbol die ungefilterte Antwort des Fundamentals-Endpunkts, als tar-Archive in "
               "den Releases eodhd-voll-*; im Dateibaum das Register stand.json, die Symbollisten, Kalender, "
               "Makro-Proben, Trends, Proben, Inventur, Tarifprobe, das Protokoll je Lauf und dieser Katalog"},
    {"ordner": ORDNER_KONSENS,
     "herkunft": "eodhd_konsens.py, Ablauf eodhd.yml, nur von Hand (Gerhards F7 und F8)",
     "inhalt": "Konsens-Historie: roh/ die auf General und Earnings gefilterte Antwort je Firma, konsens/ dieselben "
               "Daten normalisiert in Zeilen (konsens_trend und eps_history), splits/ die Split-Historie von "
               "Yahoo; Beschreibung in eodhd/LIESMICH.txt"},
    {"ordner": ORDNER_ZUORDNUNG,
     "herkunft": "zuordnung_bauen.py, Ablauf zuordnung.yml, nur von Hand (Entscheidung 10)",
     "inhalt": "eigene Branchen-Zuordnung aus dem einmaligen Abzug: Typ und GICS je Titel der Hauptboersen"},
]

ZUGRIFF = {
    "register": f"{ORDNER_VOLL}/stand.json: je abgerufenem Symbol ein Eintrag unter dem Schluessel <stufe>:<CODE> "
                "mit status (ok, leer, unbekannt, fehler, nicht_gesichert), datum, datei, release und archiv, dazu "
                "Name, Typ, Boerse, Sektor, Branche, GICS, Land und Waehrung",
    "rohantwort": "Release <release> im Datenrepo, Anhang <archiv> (tar, ohne zweite Kompression), darin die "
                  "Datei <stufe>/<datei> (gzip-JSON, die unveraenderte Antwort des Anbieters)",
    "holen": f"gh release download <release> --repo {DATENREPO} --pattern <archiv>",
    "lesen": "tar-Mitglied <stufe>/<datei> entpacken, mit gzip oeffnen, als JSON lesen",
    "code": "eodhd_katalog.wo(register, CODE) liefert Stufe, Release, Archiv und Datei je Fundort",
}

LEER = {"", "NA", "N/A", "NONE", "NULL", "-"}
DATUM = re.compile(r"^\d{4}-\d{2}-\d{2}$")
NR = re.compile(r"^\d+$")
ZAHL = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")
PLATZ = {"Stichtag": "<Stichtag>", "Nummer": "<Nr>", "Name": "<Name>", "Liste": "<Eintrag>"}


# ---------------------------------------------------------------------------
# Werte beschreiben, ohne sie zu behalten
# ---------------------------------------------------------------------------

def leer(w):
    if w is None:
        return True
    if isinstance(w, str):
        return w.strip().upper() in LEER
    if isinstance(w, (list, dict)):
        return len(w) == 0
    return False


def art(w):
    """Die Art eines Werts, nie der Wert selbst."""
    if isinstance(w, bool):
        return "Wahrheitswert"
    if isinstance(w, (int, float)):
        return "Zahl"
    if isinstance(w, str):
        s = w.strip()
        if ZAHL.match(s):
            return "Zahl als Text"
        if DATUM.match(s[:10]):
            return "Datum"
        return "Text"
    if isinstance(w, list):
        return "Liste"
    if isinstance(w, dict):
        return "Objekt"
    return "leer" if w is None else type(w).__name__


def reihe(d):
    """Ist dieses Objekt eine Reihe? Liefert Stichtag, Nummer, Name oder None."""
    if not isinstance(d, dict) or not d:
        return None
    schluessel = list(d)
    if all(DATUM.match(str(k)) for k in schluessel):
        return "Stichtag"
    if all(NR.match(str(k)) for k in schluessel):
        return "Nummer"
    if len(schluessel) >= 8 and all(isinstance(v, dict) for v in d.values()):
        return "Name"
    return None


class Stufe:
    """Gesammelte Beschreibung aller Rohantworten einer Stufe."""

    def __init__(self):
        self.n = 0
        self.felder = {}          # Pfad -> [gefuellt, Counter der Arten, bezug]
        self.reihen = {}          # Pfad -> {art, symbole, anzahl[], aeltester, juengster}

    def _feld(self, pfad, w, bezug):
        f = self.felder.get(pfad)
        if f is None:
            f = self.felder[pfad] = [0, Counter(), bezug]
        if not leer(w):
            f[0] += 1
            f[1][art(w)] += 1

    def _reihe(self, pfad, sorte, eintraege, schluessel):
        r = self.reihen.get(pfad)
        if r is None:
            r = self.reihen[pfad] = {"art": sorte, "symbole": 0, "anzahl": [], "aeltester": None, "juengster": None}
        r["symbole"] += 1
        r["anzahl"].append(eintraege)
        if sorte == "Stichtag" and schluessel:
            lo, hi = min(schluessel), max(schluessel)
            r["aeltester"] = lo if r["aeltester"] is None else min(r["aeltester"], lo)
            r["juengster"] = hi if r["juengster"] is None else max(r["juengster"], hi)

    def aufnehmen(self, d):
        self.n += 1
        self._gehen(d, "", "Symbol")

    def _gehen(self, d, pfad, bezug):
        if isinstance(d, list):
            if not d:
                return
            wurzel = pfad or "(Antwort)"
            self._reihe(wurzel, "Liste", len(d), None)
            erster = d[0]
            if isinstance(erster, (dict, list)):
                self._gehen(erster, f"{wurzel}::{PLATZ['Liste']}", "erster Eintrag")
            else:
                self._feld(f"{wurzel}::{PLATZ['Liste']}", erster, "erster Eintrag")
            return
        if not isinstance(d, dict):
            self._feld(pfad or "(Antwort)", d, bezug)
            return
        sorte = reihe(d) if pfad else None
        if sorte:
            schluessel = [str(k) for k in d]
            self._reihe(pfad, sorte, len(d), schluessel if sorte == "Stichtag" else None)
            if sorte == "Stichtag":
                wahl, neu_bezug = max(schluessel), "juengster Eintrag"
            else:
                wahl, neu_bezug = schluessel[0], "erster Eintrag"
            v = d[wahl]
            ziel = f"{pfad}::{PLATZ[sorte]}"
            if isinstance(v, (dict, list)) and v:
                self._gehen(v, ziel, neu_bezug)
            else:
                self._feld(ziel, v, neu_bezug)
            return
        for k, v in d.items():
            p = f"{pfad}::{k}" if pfad else str(k)
            if isinstance(v, (dict, list)) and v:
                self._feld(p, v, bezug)
                self._gehen(v, p, bezug)
            else:
                self._feld(p, v, bezug)

    def ergebnis(self):
        n = max(self.n, 1)
        felder = []
        for pfad in sorted(self.felder):
            gefuellt, arten, bezug = self.felder[pfad]
            felder.append({"pfad": pfad, "anteil": round(gefuellt / n, 4), "gefuellt": gefuellt,
                           "arten": dict(arten.most_common()), "bezug": bezug})
        reihen = []
        for pfad in sorted(self.reihen):
            r = self.reihen[pfad]
            a = sorted(r["anzahl"])
            reihen.append({"pfad": pfad, "art": r["art"], "symbole": r["symbole"],
                           "eintraege_min": a[0], "eintraege_median": statistics.median(a), "eintraege_max": a[-1],
                           "aeltester": r["aeltester"], "juengster": r["juengster"]})
        return {"gelesen": self.n, "felder": felder, "reihen": reihen}


# ---------------------------------------------------------------------------
# Register, Symbollisten und Archive
# ---------------------------------------------------------------------------

def _json(pfad, vorgabe=None):
    try:
        if pfad.endswith(".gz"):
            with gzip.open(pfad, "rt", encoding="utf-8") as f:
                return json.load(f)
        with io.open(pfad, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa
        return vorgabe


def register_lesen(daten):
    return _json(os.path.join(daten, ORDNER_VOLL, "stand.json"), {}) or {}


def register_kennung(daten):
    """Pruefsumme des Registers: aendert sie sich, ist neu abgerufen worden."""
    pfad = os.path.join(daten, ORDNER_VOLL, "stand.json")
    if not os.path.exists(pfad):
        return None
    h = hashlib.sha256()
    with open(pfad, "rb") as f:
        for stueck in iter(lambda: f.read(1 << 20), b""):
            h.update(stueck)
    return h.hexdigest()


def noetig(daten):
    """Ist der Katalog neu zu bauen? Ja, wenn es ihn nicht gibt, wenn seine
    Fassung aelter ist oder wenn sich das Register seither geaendert hat."""
    alt = _json(os.path.join(daten, ORDNER_VOLL, KATALOG_JSON), None)
    if not isinstance(alt, dict) or alt.get("fassung") != FASSUNG:
        return True
    return (alt.get("grundlage") or {}).get("register_sha256") != register_kennung(daten)


def juengste(daten, praefix):
    ordner = os.path.join(daten, ORDNER_VOLL, "listen")
    if not os.path.isdir(ordner):
        return None, None
    namen = sorted(n for n in os.listdir(ordner) if n.startswith(praefix) and n.endswith(".json.gz"))
    if not namen:
        return None, None
    return os.path.join(ordner, namen[-1]), namen[-1][len(praefix):-len(".json.gz")]


def umfang_laut_listen(daten):
    """{stufe: Zahl der Symbole} laut den juengsten Symbollisten, eingeordnet
    wie eodhd_voll.einordnen; makro bleibt offen (die Liste der Indikatoren
    steht nur im Skript des Vollabzugs)."""
    raus = Counter()
    p_aktiv, _ = juengste(daten, "us_aktiv_")
    p_del, _ = juengste(daten, "us_delisted_")
    p_indx, _ = juengste(daten, "indx_")
    for e in (_json(p_aktiv, []) if p_aktiv else []) or []:
        if not str(e.get("Code") or "").strip():
            continue
        typ = str(e.get("Type") or "").strip().lower()
        boerse = str(e.get("Exchange") or "").strip().upper()
        if typ in TYP_STAMM:
            raus["stock_boerse" if boerse in BOERSEN_HAUPT else "stock_otc"] += 1
        elif typ in TYP_ETF:
            raus["etf"] += 1
        elif typ in TYP_FONDS:
            raus["fund"] += 1
        else:
            raus["sonstige"] += 1
    for e in (_json(p_del, []) if p_del else []) or []:
        if not str(e.get("Code") or "").strip():
            continue
        raus["delisted_stock" if str(e.get("Type") or "").strip().lower() in TYP_STAMM else "delisted_rest"] += 1
    raus["index"] = sum(1 for e in ((_json(p_indx, []) if p_indx else []) or []) if e.get("Code"))
    return dict(raus)


def register_je_stufe(register):
    raus = {}
    for schluessel, e in (register or {}).items():
        if not isinstance(e, dict):
            continue
        s = e.get("stufe") or str(schluessel).split(":", 1)[0]
        z = raus.setdefault(s, {"status": Counter(), "bytes_gz": 0, "archive": Counter(), "erster_tag": None,
                                "letzter_tag": None})
        z["status"][e.get("status") or "ohne Status"] += 1
        z["bytes_gz"] += int(e.get("bytes_gz") or 0)
        if e.get("status") == "ok" and e.get("archiv"):
            z["archive"][(e.get("release") or "", e["archiv"])] += 1
        tag = str(e.get("datum") or "")[:10]
        if tag:
            z["erster_tag"] = tag if z["erster_tag"] is None else min(z["erster_tag"], tag)
            z["letzter_tag"] = tag if z["letzter_tag"] is None else max(z["letzter_tag"], tag)
    return raus


def benoetigte_archive(register):
    """{(Release, Archiv): {Mitglied im Archiv}} aller Symbole mit Status ok.
    Nur das Archiv, das das Register nennt, zaehlt: eine aeltere Kopie
    desselben Symbols in einem anderen Archiv wird nicht doppelt gelesen."""
    raus = defaultdict(set)
    for schluessel, e in (register or {}).items():
        if not isinstance(e, dict) or e.get("status") != "ok":
            continue
        if not (e.get("release") and e.get("archiv") and e.get("datei")):
            continue
        s = e.get("stufe") or str(schluessel).split(":", 1)[0]
        raus[(e["release"], e["archiv"])].add(f"{s}/{e['datei']}")
    return dict(raus)


def archive_lesen(ordner, archive, stufen=None, log=print):
    """Alle Rohantworten aus den heruntergeladenen Archiven in die
    Beschreibung je Stufe. Zurueck ({stufe: Stufe}, Befund)."""
    stufen = stufen if stufen is not None else {}
    befund = Counter()
    for i, ((release, archiv), mitglieder) in enumerate(sorted(archive.items()), 1):
        pfad = os.path.join(ordner, archiv)
        if not os.path.exists(pfad):
            befund["archiv_fehlt"] += 1
            befund["mitglieder_ohne_archiv"] += len(mitglieder)
            continue
        gelesen = 0
        with tarfile.open(pfad) as tf:
            for m in tf:
                if not m.isfile() or m.name not in mitglieder:
                    continue
                try:
                    d = json.loads(gzip.decompress(tf.extractfile(m).read()))
                except Exception:  # noqa  eine kaputte Datei darf den Katalog nicht aufhalten
                    befund["unlesbar"] += 1
                    continue
                stufen.setdefault(m.name.split("/", 1)[0], Stufe()).aufnehmen(d)
                gelesen += 1
        befund["gelesen"] += gelesen
        befund["im_archiv_fehlend"] += len(mitglieder) - gelesen
        log(f"  Archiv {i} von {len(archive)}: {gelesen} Rohantworten gelesen")
    return stufen, dict(befund)


def wo(register, code, stufe=None):
    """Wo liegt die Rohantwort eines Symbols? [{stufe, status, release,
    archiv, datei}] je Fundort; derselbe Code kann aktiv und delistet
    vorkommen."""
    code = str(code or "").strip().upper()
    raus = []
    for s in STUFEN_NAMEN:
        if stufe and s != stufe:
            continue
        e = (register or {}).get(f"{s}:{code}")
        if isinstance(e, dict):
            raus.append({"stufe": s, "status": e.get("status"), "release": e.get("release"),
                         "archiv": e.get("archiv"), "datei": e.get("datei")})
    return raus


# ---------------------------------------------------------------------------
# Die Konsens-Historie (Ordner eodhd) und die uebrigen Dateien
# ---------------------------------------------------------------------------

def konsens_beschreiben(daten):
    """Zeilenarten und Felder der Ordner eodhd/konsens und eodhd/roh."""
    wurzel = os.path.join(daten, ORDNER_KONSENS)
    raus = {"ordner": ORDNER_KONSENS, "dateien": {}}
    if not os.path.isdir(wurzel):
        raus["fehlt"] = True
        return raus
    for unter in ("roh", "konsens", "splits"):
        o = os.path.join(wurzel, unter)
        raus["dateien"][unter] = (sum(1 for n in os.listdir(o) if n.endswith(".json.gz"))
                                  if os.path.isdir(o) else 0)
    zeilen = defaultdict(lambda: {"firmen": 0, "zeilen": 0, "felder": Counter()})
    o = os.path.join(wurzel, "konsens")
    if os.path.isdir(o):
        for n in sorted(os.listdir(o)):
            if not n.endswith(".json.gz"):
                continue
            d = _json(os.path.join(o, n), None)
            reihen = d.get("zeilen") if isinstance(d, dict) else d
            if not isinstance(reihen, list):
                continue
            gesehen = set()
            for z in reihen:
                if not isinstance(z, dict):
                    continue
                a = str(z.get("art") or "ohne art")
                zeilen[a]["zeilen"] += 1
                zeilen[a]["felder"].update(k for k, v in z.items() if not leer(v))
                gesehen.add(a)
            for a in gesehen:
                zeilen[a]["firmen"] += 1
    raus["zeilenarten"] = {a: {"firmen": z["firmen"], "zeilen": z["zeilen"],
                               "felder": {k: round(c / max(z["zeilen"], 1), 4) for k, c in sorted(z["felder"].items())}}
                           for a, z in sorted(zeilen.items())}
    roh = Stufe()
    o = os.path.join(wurzel, "roh")
    if os.path.isdir(o):
        for n in sorted(os.listdir(o)):
            if n.endswith(".json.gz"):
                d = _json(os.path.join(o, n), None)
                if d is not None:
                    roh.aufnehmen(d)
    raus["roh"] = roh.ergebnis()
    return raus


BESCHREIBUNG = [
    (r"^stand\.json$", "Register des Vollabzugs, je Symbol ein Eintrag (siehe zugriff)"),
    (r"^laeufe\.jsonl$", "Protokoll, eine Zeile je Lauf"),
    (r"^inventur\.(json|md)$", "Inventur vom 12.09.2026: Umfang je Stufe und Tarif"),
    (r"^tarif_.*\.(json|md)$", "Tarifprobe: je Endpunkt, ob der Tarif ihn hergibt"),
    (r"^listen/us_aktiv_", "Symbolliste aller aktiven US-Titel des Anbieters"),
    (r"^listen/us_delisted_", "Symbolliste aller delisteten US-Titel des Anbieters"),
    (r"^listen/indx_", "Liste der Indizes des Anbieters"),
    (r"^listen/exchanges_", "Liste der Boersen des Anbieters"),
    (r"^kalender/earnings_", "Ergebniskalender (Meldetage samt Schaetzung und Ist)"),
    (r"^kalender/events_", "Wirtschaftstermine eines Jahres"),
    (r"^kalender/ipos_", "Kalender der Boersengaenge"),
    (r"^kalender/splits_", "Kalender der Splits"),
    (r"^makro/", "Makro-Indikator eines Landes"),
    (r"^trends/", "Konsens-Trends (Earnings::Trend) vieler Aktien je Anfrage"),
    (r"^proben/", "Probe eines einzelnen Abrufs vom 12.09.2026"),
    (r"^LIESMICH", "Beschreibung des Ordners"),
    (r"^gegenprobe_", "Gegenprobe der EPS-History gegen die amtliche Erstfassung"),
    (r"^branchen_", "eigene Branchen-Zuordnung (Typ und GICS je Titel)"),
    (r"^katalog\.", "dieser Katalog"),
]


def _beschreibung(relpfad):
    for muster, text in BESCHREIBUNG:
        if re.search(muster, relpfad):
            return text
    return ""


def datei_beschreiben(pfad, relpfad):
    """Groesse und, wo lesbar, Zeilen und Feldnamen einer Datei; nie Werte."""
    e = {"pfad": relpfad, "bytes": os.path.getsize(pfad), "inhalt": _beschreibung(relpfad.split("/", 1)[-1])}
    name = os.path.basename(pfad)
    if name.startswith("katalog.") or name == "stand.json":
        return e
    try:
        if name.endswith(".jsonl"):
            felder, zeilen = Counter(), 0
            with io.open(pfad, encoding="utf-8") as f:
                for z in f:
                    if z.strip():
                        zeilen += 1
                        try:
                            felder.update(json.loads(z).keys())
                        except Exception:  # noqa
                            pass
            e.update({"zeilen": zeilen, "felder": sorted(felder)})
        elif name.endswith(".json") or name.endswith(".json.gz"):
            d = _json(pfad, None)
            if isinstance(d, list):
                felder = Counter()
                for z in d[:500]:
                    if isinstance(z, dict):
                        felder.update(z.keys())
                e.update({"zeilen": len(d), "felder": sorted(felder)})
            elif isinstance(d, dict):
                e.update({"schluessel": len(d), "felder": sorted(map(str, d))[:60]})
    except Exception:  # noqa
        e["unlesbar"] = True
    return e


def dateien_beschreiben(daten):
    raus = []
    for ordner in (ORDNER_VOLL, ORDNER_KONSENS, ORDNER_ZUORDNUNG):
        wurzel = os.path.join(daten, ordner)
        if not os.path.isdir(wurzel):
            continue
        for grund, unter, namen in os.walk(wurzel):
            rel_grund = os.path.relpath(grund, daten).replace(os.sep, "/")
            # Die Ordner je Firma der Konsens-Historie stehen nur als Zahl im Katalog.
            if rel_grund.startswith(f"{ORDNER_KONSENS}/"):
                unter[:] = []
                continue
            unter.sort()
            for n in sorted(namen):
                rel = f"{rel_grund}/{n}"
                raus.append(datei_beschreiben(os.path.join(grund, n), rel))
    return raus


# ---------------------------------------------------------------------------
# Der Katalog
# ---------------------------------------------------------------------------

def bauen(daten, archive_ordner, jetzt=None, log=print):
    register = register_lesen(daten)
    je_stufe = register_je_stufe(register)
    umfang = umfang_laut_listen(daten)
    archive = benoetigte_archive(register)
    log(f"Register: {len(register)} Eintraege; {len(archive)} Archive noetig")
    stufen, befund = archive_lesen(archive_ordner, archive, log=log)
    stufen_aus = {}
    for s, text in STUFEN:
        z = je_stufe.get(s) or {"status": Counter(), "bytes_gz": 0, "archive": Counter(), "erster_tag": None,
                               "letzter_tag": None}
        erledigt = sum(z["status"].get(x, 0) for x in ERLEDIGT)
        in_liste = umfang.get(s)
        eintrag = {"beschreibung": text, "symbole_laut_liste": in_liste,
                   "im_register": sum(z["status"].values()), "status": dict(z["status"].most_common()),
                   "erledigt": erledigt, "offen": (max(in_liste - erledigt, 0) if in_liste is not None else None),
                   "bytes_gz": z["bytes_gz"], "erster_tag": z["erster_tag"], "letzter_tag": z["letzter_tag"],
                   "archive": [{"release": r, "archiv": a, "symbole": c} for (r, a), c in sorted(z["archive"].items())]}
        if s in stufen:
            eintrag.update(stufen[s].ergebnis())
        else:
            eintrag.update({"gelesen": 0, "felder": [], "reihen": []})
        stufen_aus[s] = eintrag
        log(f"Stufe {s}: {eintrag['gelesen']} gelesen, {len(eintrag['felder'])} Felder, {len(eintrag['reihen'])} Reihen")
    jetzt = jetzt or datetime.now(timezone.utc)
    return {
        "fassung": FASSUNG,
        "erstellt": jetzt.isoformat(timespec="seconds"),
        "zweck": "Was in den EODHD-Daten des privaten Datenrepos steht und wo es liegt (Gerhard, 20.09.2026, S11); "
                 "nie ein Wert. Genutzt werden nach Entscheidung 10 nur Konsens und Zuordnung.",
        "lizenz": "lizenziert (F17): nur im privaten Datenrepo, nie anzeigen oder weitergeben",
        "grundlage": {"register_sha256": register_kennung(daten), "register_eintraege": len(register),
                      "archive": len(archive), **befund},
        "zaehlweise": "Anteil = Symbole mit gefuelltem Feld durch gelesene Symbole der Stufe; leer sind None, leerer "
                      "Text, NA, N/A, None, null, Strich, leere Liste und leeres Objekt, die Null ist ein Wert. "
                      "Unter einer Reihe zaehlen die Felder im juengsten Eintrag (Stichtage) oder im ersten "
                      "(Nummern, Namen, Listen).",
        "ablagen": ABLAGEN,
        "zugriff": ZUGRIFF,
        "stufen": stufen_aus,
        "konsens": konsens_beschreiben(daten),
        "dateien": dateien_beschreiben(daten),
    }


def _pz(anteil):
    return f"{anteil * 100:.0f}".replace(".", ",")


def _zahl(n):
    return f"{int(n):,}".replace(",", ".") if n is not None else "unbekannt"


def markdown(k):
    """Der Katalog zum Lesen: je Stufe Umfang, die Abschnitte und die Reihen;
    alle Felder stehen in katalog.json."""
    z = [f"# Katalog der EODHD-Daten", "",
         f"Erstellt am {k['erstellt'][:10]} um {k['erstellt'][11:16]} UTC. {k['zweck']}",
         f"Lizenz: {k['lizenz']}.", "", "## Ablagen", ""]
    for a in k["ablagen"]:
        z.append(f"1. Ordner {a['ordner']}: {a['inhalt']}. Herkunft: {a['herkunft']}.")
    z += ["", "## Zugriff auf eine Rohantwort", ""]
    for i, (name, text) in enumerate(k["zugriff"].items(), 1):
        z.append(f"{i}. {name}: {text}")
    z += ["", "## Stufen des Vollabzugs", "", k["zaehlweise"], ""]
    for s, e in k["stufen"].items():
        z += [f"### {s}: {e['beschreibung']}", ""]
        umfang = (f"laut Symbolliste {_zahl(e['symbole_laut_liste'])} Symbole, erledigt {_zahl(e['erledigt'])}, "
                  f"offen {_zahl(e['offen'])}" if e["symbole_laut_liste"] is not None
                  else f"erledigt {_zahl(e['erledigt'])}")
        z.append(f"Umfang: {umfang}. Im Register {_zahl(e['im_register'])} Eintraege nach Status: "
                 + ", ".join(f"{st} {_zahl(n)}" for st, n in e["status"].items())
                 + f". Gepackt {e['bytes_gz'] / 1e6:.0f} MB in {len(e['archive'])} Archiven"
                 + (f", abgerufen vom {e['erster_tag']} bis {e['letzter_tag']}" if e["erster_tag"] else "")
                 + f". Gelesen fuer diesen Katalog: {_zahl(e['gelesen'])} Rohantworten.")
        oben = [f for f in e["felder"] if "::" not in f["pfad"]]
        if oben:
            z += ["", "Abschnitte mit Anteil der Symbole, bei denen sie gefuellt sind:"]
            z += [f"1. {f['pfad']}: {_pz(f['anteil'])} Prozent" for f in oben]
        if e["reihen"]:
            z += ["", "Reihen, je Symbol die Zahl der Eintraege (kleinste, Median, groesste) und die Stichtage:"]
            for r in e["reihen"]:
                z.append(f"1. {r['pfad']} ({r['art']}): bei {_zahl(r['symbole'])} Symbolen, "
                         f"{r['eintraege_min']}, {r['eintraege_median']:g}, {r['eintraege_max']} Eintraege"
                         + (f", Stichtage vom {r['aeltester']} bis {r['juengster']}" if r["aeltester"] else ""))
        z.append("")
    kon = k.get("konsens") or {}
    if kon.get("zeilenarten"):
        z += ["## Konsens-Historie im Ordner eodhd", "",
              "Dateien je Unterordner: " + ", ".join(f"{u} {_zahl(n)}" for u, n in kon["dateien"].items()) + "."]
        for a, e in kon["zeilenarten"].items():
            z.append(f"1. Zeilenart {a}: {_zahl(e['firmen'])} Firmen, {_zahl(e['zeilen'])} Zeilen, Felder "
                     + ", ".join(e["felder"]))
        z.append("")
    z += ["## Dateien", ""]
    for d in k["dateien"]:
        teile = [f"{d['bytes'] / 1e6:.1f} MB" if d["bytes"] >= 100_000 else f"{d['bytes'] / 1e3:.0f} KB"]
        if d.get("zeilen") is not None:
            teile.append(f"{_zahl(d['zeilen'])} Zeilen")
        if d.get("inhalt"):
            teile.insert(0, d["inhalt"])
        z.append(f"1. {d['pfad']}: " + ", ".join(teile))
    z += ["", "Alle Felder je Stufe samt Anteil und Art stehen in katalog.json unter stufen, <Stufe>, felder."]
    return "\n".join(z) + "\n"


def schreiben(daten, katalog):
    ziel = os.path.join(daten, ORDNER_VOLL)
    os.makedirs(ziel, exist_ok=True)
    with io.open(os.path.join(ziel, KATALOG_JSON), "w", encoding="utf-8", newline="\n") as f:
        json.dump(katalog, f, ensure_ascii=False, indent=1, sort_keys=False)
        f.write("\n")
    with io.open(os.path.join(ziel, KATALOG_MD), "w", encoding="utf-8", newline="\n") as f:
        f.write(markdown(katalog))


# ---------------------------------------------------------------------------
# Lesen fuer Programme
# ---------------------------------------------------------------------------

def laden(pfad):
    return _json(pfad, None)


def felder(katalog, stufe, suche=None):
    """Die Felder einer Stufe, auf Wunsch nur die mit dem Suchwort im Pfad."""
    e = ((katalog or {}).get("stufen") or {}).get(stufe) or {}
    wort = (suche or "").lower()
    return [f for f in e.get("felder") or [] if wort in f["pfad"].lower()]


def hat_feld(katalog, pfad, stufe=None, mindestens=0.0):
    """Gibt es das Feld (in einer Stufe oder irgendwo) mit mindestens diesem Anteil?"""
    for s, e in ((katalog or {}).get("stufen") or {}).items():
        if stufe and s != stufe:
            continue
        for f in e.get("felder") or []:
            if f["pfad"] == pfad and f["anteil"] >= mindestens:
                return True
    return False


# ---------------------------------------------------------------------------
# Selbsttest (ohne Netz, mit gebauten Archiven)
# ---------------------------------------------------------------------------

def selbsttest() -> int:
    import tempfile
    fehler = []

    def p(name, ok, zusatz=""):
        print(f"  {'ok  ' if ok else 'FEHL'} {name}" + (f"; {zusatz}" if zusatz else ""))
        if not ok:
            fehler.append(name)

    # Reihen erkennen
    p("Reihen: Stichtage, Nummern, Namen", reihe({"2026-06-30": {}, "2026-03-31": {}}) == "Stichtag"
      and reihe({"0": {}, "1": {}}) == "Nummer" and reihe({f"T{i}": {"w": 1} for i in range(8)}) == "Name"
      and reihe({"Code": "A", "Name": "B"}) is None and reihe({f"T{i}": {"w": 1} for i in range(7)}) is None)
    p("Arten: Zahl, Zahl als Text, Datum, Text, leer", art(1.5) == "Zahl" and art("12.3") == "Zahl als Text"
      and art("2026-06-30") == "Datum" and art("Apple") == "Text" and art(True) == "Wahrheitswert")
    p("Leer: NA, Strich, leere Liste; die Null ist ein Wert", leer("NA") and leer("-") and leer([]) and leer(None)
      and not leer(0) and not leer("0"))

    aapl = {"General": {"Code": "AAA", "Name": "Alpha Inc", "Sector": "Technology", "IPODate": "NA",
                        "Officers": {"0": {"Name": "X", "Title": "CEO"}, "1": {"Name": "Y", "Title": "CFO"}}},
            "Highlights": {"MarketCapitalization": 1000, "PERatio": "25.1", "EPS": None},
            "Financials": {"Balance_Sheet": {"currency_symbol": "USD",
                                             "quarterly": {"2026-06-30": {"date": "2026-06-30", "totalAssets": "10"},
                                                           "2025-06-30": {"date": "2025-06-30", "totalAssets": None},
                                                           "2019-03-31": {"date": "2019-03-31", "totalAssets": "7"}}}}}
    bbb = {"General": {"Code": "BBB", "Name": "Beta Inc", "Sector": "NA", "IPODate": "2001-02-03"},
           "Highlights": {"MarketCapitalization": 0, "PERatio": "NA"},
           "Financials": {"Balance_Sheet": {"currency_symbol": "USD",
                                            "quarterly": {"2026-03-31": {"date": "2026-03-31", "totalAssets": None}}}}}
    st = Stufe()
    st.aufnehmen(aapl)
    st.aufnehmen(bbb)
    erg = st.ergebnis()
    fe = {f["pfad"]: f for f in erg["felder"]}
    re_ = {r["pfad"]: r for r in erg["reihen"]}
    p("Anteil: Sector bei einem von zwei gefuellt, die Null zaehlt", fe["General::Sector"]["anteil"] == 0.5
      and fe["Highlights::MarketCapitalization"]["anteil"] == 1.0 and fe["Highlights::EPS"]["anteil"] == 0.0)
    p("Arten je Feld ohne Werte", fe["Highlights::PERatio"]["arten"] == {"Zahl als Text": 1}
      and "25.1" not in json.dumps(erg))
    q = "Financials::Balance_Sheet::quarterly"
    p("Reihe der Quartale: Eintraege, aeltester und juengster Stichtag", re_[q]["art"] == "Stichtag"
      and re_[q]["eintraege_min"] == 1 and re_[q]["eintraege_max"] == 3 and re_[q]["aeltester"] == "2019-03-31"
      and re_[q]["juengster"] == "2026-06-30", str(re_.get(q)))
    p("Felder unter der Reihe zaehlen im juengsten Eintrag",
      fe[f"{q}::<Stichtag>::totalAssets"]["anteil"] == 0.5
      and fe[f"{q}::<Stichtag>::totalAssets"]["bezug"] == "juengster Eintrag")
    p("Nummern-Reihe: erster Eintrag, keine einzelnen Nummern im Pfad",
      "General::Officers::<Nr>::Title" in fe and not any("::0::" in f for f in fe))
    p("Keine Stichtage als Feldnamen", not any(re.search(r"\d{4}-\d{2}-\d{2}", f) for f in fe))
    liste = Stufe()
    liste.aufnehmen([{"Date": "2020-01-01", "Value": 1.0}, {"Date": "2021-01-01", "Value": None}])
    p("Eine Antwort als Liste (Makro)", {r["pfad"] for r in liste.ergebnis()["reihen"]} == {"(Antwort)"}
      and any(f["pfad"] == "(Antwort)::<Eintrag>::Value" for f in liste.ergebnis()["felder"]))

    with tempfile.TemporaryDirectory() as tmp:
        daten = os.path.join(tmp, "daten")
        archive = os.path.join(tmp, "archive")
        os.makedirs(os.path.join(daten, ORDNER_VOLL, "listen"))
        os.makedirs(archive)
        register = {
            "stock_boerse:AAA": {"stufe": "stock_boerse", "status": "ok", "datum": "2026-09-15", "bytes_gz": 100,
                                 "datei": "AAA.json.gz", "release": "eodhd-voll-1", "archiv": "eodhd_stock_boerse_1.tar"},
            "stock_boerse:BBB": {"stufe": "stock_boerse", "status": "ok", "datum": "2026-09-16", "bytes_gz": 90,
                                 "datei": "BBB.json.gz", "release": "eodhd-voll-2", "archiv": "eodhd_stock_boerse_2.tar"},
            "stock_boerse:CCC": {"stufe": "stock_boerse", "status": "unbekannt", "datum": "2026-09-16"},
            "delisted_stock:AAA": {"stufe": "delisted_stock", "status": "ok", "datum": "2026-09-12", "bytes_gz": 50,
                                   "datei": "AAA.json.gz", "release": "eodhd-voll-0",
                                   "archiv": "eodhd_delisted_stock_0.tar"},
        }
        with io.open(os.path.join(daten, ORDNER_VOLL, "stand.json"), "w", encoding="utf-8") as f:
            json.dump(register, f)
        with gzip.open(os.path.join(daten, ORDNER_VOLL, "listen", "us_aktiv_2026-09-12.json.gz"), "wt",
                       encoding="utf-8") as f:
            json.dump([{"Code": "AAA", "Exchange": "NASDAQ", "Type": "Common Stock"},
                       {"Code": "BBB", "Exchange": "NYSE", "Type": "Common Stock"},
                       {"Code": "CCC", "Exchange": "NYSE", "Type": "Common Stock"},
                       {"Code": "DDD", "Exchange": "NYSE", "Type": "Common Stock"},
                       {"Code": "EEE", "Exchange": "PINK", "Type": "Common Stock"},
                       {"Code": "FFF", "Exchange": "NYSE ARCA", "Type": "ETF"}], f)

        def tar_mit(name, inhalt):
            with tarfile.open(os.path.join(archive, name), "w") as tf:
                for mitglied, d in inhalt.items():
                    roh = gzip.compress(json.dumps(d).encode("utf-8"))
                    info = tarfile.TarInfo(mitglied)
                    info.size = len(roh)
                    tf.addfile(info, io.BytesIO(roh))

        tar_mit("eodhd_stock_boerse_1.tar", {"stock_boerse/AAA.json.gz": aapl,
                                             # eine aeltere Kopie, die das Register anders verortet: nicht mitzaehlen
                                             "stock_boerse/BBB.json.gz": aapl})
        tar_mit("eodhd_stock_boerse_2.tar", {"stock_boerse/BBB.json.gz": bbb})
        # eodhd_delisted_stock_0.tar fehlt absichtlich
        p("Archiv-Liste nennt jedes benoetigte Archiv einmal",
          sorted(benoetigte_archive(register)) == [("eodhd-voll-0", "eodhd_delisted_stock_0.tar"),
                                                   ("eodhd-voll-1", "eodhd_stock_boerse_1.tar"),
                                                   ("eodhd-voll-2", "eodhd_stock_boerse_2.tar")])
        p("Neu zu bauen, solange es keinen Katalog gibt", noetig(daten))
        k = bauen(daten, archive, jetzt=datetime(2026, 9, 21, 20, 0, tzinfo=timezone.utc), log=lambda *a: None)
        sb = k["stufen"]["stock_boerse"]
        p("Stufe stock_boerse: Umfang laut Liste, erledigt, offen, Status",
          sb["symbole_laut_liste"] == 4 and sb["erledigt"] == 3 and sb["offen"] == 1
          and sb["status"] == {"ok": 2, "unbekannt": 1} and sb["gelesen"] == 2, str({x: sb[x] for x in (
              "symbole_laut_liste", "erledigt", "offen", "status", "gelesen")}))
        p("Die aeltere Kopie in einem anderen Archiv zaehlt nicht doppelt",
          k["grundlage"]["gelesen"] == 2 and k["grundlage"]["archiv_fehlt"] == 1, str(k["grundlage"]))
        p("Freiverkehr und ETF aus der Liste eingeordnet", k["stufen"]["stock_otc"]["symbole_laut_liste"] == 1
          and k["stufen"]["etf"]["symbole_laut_liste"] == 1)
        p("Wo liegt AAA: zwei Fundorte, aktiv und delistet",
          [x["stufe"] for x in wo(register, "aaa")] == ["delisted_stock", "stock_boerse"]
          and wo(register, "AAA", "stock_boerse")[0]["archiv"] == "eodhd_stock_boerse_1.tar")
        schreiben(daten, k)
        k2 = laden(os.path.join(daten, ORDNER_VOLL, KATALOG_JSON))
        p("Geschrieben und wieder gelesen; danach nicht mehr noetig",
          k2["stufen"]["stock_boerse"]["gelesen"] == 2 and not noetig(daten))
        md = io.open(os.path.join(daten, ORDNER_VOLL, KATALOG_MD), encoding="utf-8").read()
        p("Zum Lesen: Stufen, Abschnitte, Reihen, ohne einen Wert",
          "### stock_boerse" in md and "General: 100 Prozent" in md and "Financials::Balance_Sheet::quarterly" in md
          and "Alpha" not in md and "Technology" not in md, md[:200])
        p("Katalog ohne Werte, nur Namen, Arten und Zahlen",
          all(w not in json.dumps(k2) for w in ("Alpha Inc", "Beta Inc", "Technology", "25.1")))
        p("Felder lesen und suchen", len(felder(k2, "stock_boerse", "totalassets")) == 1
          and hat_feld(k2, "Highlights::MarketCapitalization", "stock_boerse", 0.9)
          and not hat_feld(k2, "Highlights::EPS", mindestens=0.1))
        with io.open(os.path.join(daten, ORDNER_VOLL, "stand.json"), "a", encoding="utf-8") as f:
            f.write(" ")
        p("Nach einer Aenderung des Registers wieder noetig", noetig(daten))

    print("\nAlles bestanden." if not fehler else f"\n{len(fehler)} Fehler.")
    return 1 if fehler else 0


def zeigen(pfad, stufe=None, suche=None):
    k = laden(pfad)
    if not k:
        print("Katalog nicht lesbar.")
        return 1
    for s, e in k["stufen"].items():
        if stufe and s != stufe:
            continue
        print(f"{s}: {e['gelesen']} gelesen, {len(e['felder'])} Felder, {len(e['reihen'])} Reihen")
        for f in felder(k, s, suche):
            print(f"  {f['pfad']}: {_pz(f['anteil'])} Prozent, {', '.join(f['arten'])}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Katalog der EODHD-Daten (S11)")
    ap.add_argument("--selbsttest", action="store_true")
    ap.add_argument("--noetig", action="store_true")
    ap.add_argument("--archive-liste", action="store_true")
    ap.add_argument("--bauen", action="store_true")
    ap.add_argument("--zeigen", metavar="KATALOG")
    ap.add_argument("--daten", default="daten")
    ap.add_argument("--archive", default=".cache/eodhd")
    ap.add_argument("--stufe")
    ap.add_argument("--suche")
    a = ap.parse_args()
    if a.selbsttest:
        return selbsttest()
    if a.noetig:
        print("ja" if noetig(a.daten) else "nein")
        return 0
    if a.archive_liste:
        for release, archiv in sorted(benoetigte_archive(register_lesen(a.daten))):
            print(f"{release}|{archiv}")
        return 0
    if a.bauen:
        k = bauen(a.daten, a.archive)
        schreiben(a.daten, k)
        g = k["grundlage"]
        print(f"Katalog geschrieben: {g['register_eintraege']} Register-Eintraege, {g['archive']} Archive, "
              f"{g.get('gelesen', 0)} Rohantworten gelesen, {g.get('unlesbar', 0)} unlesbar, "
              f"{g.get('archiv_fehlt', 0)} Archive fehlen, {len(k['dateien'])} Dateien beschrieben")
        return 0
    if a.zeigen:
        return zeigen(a.zeigen, a.stufe, a.suche)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
