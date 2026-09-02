#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fundament, Phase 1: Laufskript fuer den Actions-Runner (braucht das
Secret SEC_USER_AGENT; die SEC weist Abrufe ohne Kontaktkennung ab).

Zwei Betriebsarten:
  --modus probe   Die Referenzfirmen aus fundament_referenz.json einzeln
                  ueber die companyfacts-API holen, normalisieren, gegen
                  die belegten Werte echter Berichte pruefen und je Firma
                  die Quartals- und Jahresreihen als CSV ablegen. Dazu
                  innere Konsistenzpruefungen (Quartalssumme gegen Jahr,
                  Bruttogewinn gegen Umsatz minus Umsatzkosten, Luecken).
  --modus voll    Das Gesamtarchiv companyfacts.zip (alle Filer) laden,
                  jede Firma normalisieren und als Parquet je Kalenderjahr
                  ablegen: Kennzahlen (fundament_kennzahlen_JJJJ.parquet),
                  Rohdaten aller Felder (fundament_roh_JJJJ.parquet, F2),
                  Metadaten je Firma und einen Abdeckungsbericht.

Ausgabe immer im Ordner fundament_ausgabe (im Runner als Artefakt bzw.
Release-Anhang; nie ins Repo committet)."""

import argparse
import csv
import datetime as dt
import gzip
import io
import json
import os
import sys
import time
import zipfile
from collections import defaultdict

import fundament_normalisieren as fn

UA = os.environ.get("SEC_USER_AGENT", "").strip()
AUSGABE = "fundament_ausgabe"
REFERENZ = "fundament_referenz.json"

KENNZAHL_FELDER = ["cik", "kennzahl", "typ", "start", "end", "fiskaljahr",
                   "fiskalperiode", "kalender", "kalender_quelle", "wert_erst",
                   "filed_erst", "form_erst", "accn_erst", "wert_letzt",
                   "filed_letzt", "form_letzt", "accn_letzt", "restated",
                   "taxonomie", "tag", "einheit", "quelle", "n_einreichungen"]
ROH_FELDER = ["cik", "taxonomie", "tag", "einheit", "start", "end", "val",
              "accn", "fy", "fp", "form", "filed", "frame"]


# ---------------------------------------------------------------------------
# SEC-Abrufe
# ---------------------------------------------------------------------------

def hole(url, versuche=3, timeout=180):
    import urllib.request
    letzter = None
    for i in range(versuche):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                roh = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    roh = gzip.decompress(roh)
                return roh
        except Exception as e:  # noqa
            letzter = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"Abruf gescheitert: {url}: {letzter}")


def ticker_zu_cik():
    d = json.loads(hole("https://www.sec.gov/files/company_tickers.json"))
    return {v["ticker"].upper(): int(v["cik_str"]) for v in d.values()}


def companyfacts(cik):
    return json.loads(hole(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"))


# ---------------------------------------------------------------------------
# Hilfen
# ---------------------------------------------------------------------------

def schreibe_csv(pfad, zeilen, felder):
    with io.open(pfad, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=felder, extrasaction="ignore")
        w.writeheader()
        w.writerows(zeilen)


def _finde(zeilen, kennzahl, ende, typ):
    for z in zeilen:
        if z["kennzahl"] == kennzahl and z["end"] == ende and z["typ"] == typ:
            return z
    return None


def _naechste_zeile(zeilen, kennzahl, ende, typ, toleranz_tage=7):
    """Falls das Periodenende der Referenz um wenige Tage abweicht
    (52/53-Wochen-Jahre), die naechstliegende Zeile."""
    e = dt.date.fromisoformat(ende)
    beste, abstand = None, None
    for z in zeilen:
        if z["kennzahl"] != kennzahl or z["typ"] != typ:
            continue
        d = abs((dt.date.fromisoformat(z["end"]) - e).days)
        if d <= toleranz_tage and (abstand is None or d < abstand):
            beste, abstand = z, d
    return beste


def _fmt(w):
    if w is None:
        return "fehlt"
    if isinstance(w, float) and abs(w) < 1000:
        return f"{w:.4f}".rstrip("0").rstrip(".")
    return f"{w:,.0f}".replace(",", ".")


# ---------------------------------------------------------------------------
# Innere Konsistenz (ohne Referenz)
# ---------------------------------------------------------------------------

def konsistenz(zeilen):
    """Liste von Befundzeilen (Text) und Kennzahlen dazu."""
    befunde = []
    nach = defaultdict(dict)
    for z in zeilen:
        nach[(z["kennzahl"], z["typ"])][z["end"]] = z

    # 1. Quartalssumme gegen Jahreswert (nur amtliche Quartale, additiv)
    geprueft = passt = 0
    for kennzahl, spez in fn.KENNZAHLEN.items():
        if spez["art"] != "dauer" or not spez["additiv"]:
            continue
        fy = nach.get((kennzahl, "FY"), {})
        q = nach.get((kennzahl, "Q"), {})
        for ende, zf in fy.items():
            quartale = [zq for zq in q.values()
                        if zf["start"] <= zq["start"] and zq["end"] <= ende]
            if len(quartale) != 4 or any(x["quelle"] != "amtlich" for x in quartale):
                continue
            summe = sum(x["wert_letzt"] for x in quartale)
            geprueft += 1
            if abs(summe - zf["wert_letzt"]) <= max(1.0, abs(zf["wert_letzt"]) * 0.001):
                passt += 1
            else:
                befunde.append(f"  Abweichung {kennzahl} Jahr bis {ende}: Quartalssumme "
                               f"{_fmt(summe)} gegen Jahr {_fmt(zf['wert_letzt'])}")
    befunde.insert(0, f"  Quartalssumme gegen Jahr: {passt} von {geprueft} stimmen (alle vier Quartale amtlich)")

    # 2. Bruttogewinn = Umsatz minus Umsatzkosten
    g = nach.get(("bruttogewinn", "Q"), {})
    u = nach.get(("umsatz", "Q"), {})
    k = nach.get(("umsatzkosten", "Q"), {})
    geprueft = passt = 0
    for ende, zg in g.items():
        if ende in u and ende in k:
            geprueft += 1
            if abs(u[ende]["wert_letzt"] - k[ende]["wert_letzt"] - zg["wert_letzt"]) <= max(1.0, abs(zg["wert_letzt"]) * 0.001):
                passt += 1
    befunde.append(f"  Bruttogewinn gegen Umsatz minus Umsatzkosten: {passt} von {geprueft} Quartalen stimmen")

    # 3. Luecken in der Umsatz-Quartalsreihe seit 2009
    enden = sorted(u)
    if enden:
        luecken = 0
        for a, b in zip(enden, enden[1:]):
            tage = (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days
            if tage > 100:
                luecken += 1
                befunde.append(f"  Luecke in der Umsatzreihe zwischen {a} und {b} ({tage} Tage)")
        befunde.append(f"  Umsatz-Quartale: {len(enden)} von {enden[0]} bis {enden[-1]}, "
                       f"davon berechnet {sum(1 for z in u.values() if z['quelle']=='berechnet')}, "
                       f"Luecken {luecken}")
    return befunde


def tag_verlauf(zeilen, kennzahl):
    """Welches Konzept trug die Kennzahl in welchem Zeitraum (Kaskaden-Diagnose)."""
    nutzung = defaultdict(list)
    for z in zeilen:
        if z["kennzahl"] == kennzahl and z["typ"] == "Q":
            nutzung[z["tag"]].append(z["end"])
    return ", ".join(f"{tag} ({min(e)[:4]} bis {max(e)[:4]}, {len(e)} Quartale)"
                     for tag, e in sorted(nutzung.items(), key=lambda kv: min(kv[1])))


# ---------------------------------------------------------------------------
# Probe
# ---------------------------------------------------------------------------

def probe():
    os.makedirs(AUSGABE, exist_ok=True)
    with io.open(REFERENZ, encoding="utf-8") as f:
        referenz = json.load(f)
    zuordnung = ticker_zu_cik()
    b = ["# Fundament Phase 1, Probe-Validierung gegen echte Berichte",
         f"Stand {dt.datetime.now(dt.timezone.utc):%d.%m.%Y %H:%M} UTC; "
         f"Ticker-Register der SEC: {len(zuordnung)} Eintraege", ""]
    gesamt = {"vergleiche": 0, "ok": 0, "fehlt": 0, "abweichung": 0}
    ergebnis = []
    for firma_ref in referenz["firmen"]:
        ticker = firma_ref["ticker"].upper()
        cik = firma_ref.get("cik") or zuordnung.get(ticker)
        b.append(f"## {ticker} ({firma_ref.get('name', '')})")
        if not cik:
            b.append("  KEINE CIK im SEC-Register gefunden"); b.append("")
            continue
        try:
            firma = companyfacts(cik)
        except Exception as e:
            b.append(f"  Abruf gescheitert: {e}"); b.append("")
            continue
        time.sleep(0.3)
        meta, zeilen = fn.normalisiere(firma)
        roh = sum(1 for _ in fn.alle_fakten(firma))
        schreibe_csv(f"{AUSGABE}/probe_{ticker}.csv", zeilen, KENNZAHL_FELDER)
        b.append(f"  CIK {cik}, {meta['name']}, Filer-Typ {meta['filer_typ']}, "
                 f"{roh} Rohfakten, {meta['einreichungen']} Einreichungen, "
                 f"{meta['zeilen']} normalisierte Zeilen, Zeitraum {meta['erstes_ende']} bis {meta['letztes_ende']}"
                 + (f", Umsatz-Waehrungen ausser USD: {meta['waehrungen_umsatz']}" if meta["waehrungen_umsatz"] else ""))
        b.append(f"  Umsatz-Konzepte: {tag_verlauf(zeilen, 'umsatz') or 'keine'}")
        b.append(f"  Nettogewinn-Konzepte: {tag_verlauf(zeilen, 'nettogewinn') or 'keine'}")
        kz_mit = sorted({z["kennzahl"] for z in zeilen if z["typ"] in ("Q", "B") and z["end"] >= "2020-01-01"})
        kz_fy = sorted({z["kennzahl"] for z in zeilen if z["typ"] == "FY" and z["end"] >= "2020-01-01"})
        nur_fy = sorted(set(kz_fy) - set(kz_mit))
        b.append(f"  Kennzahlen mit Quartals- oder Stichtagswerten seit 2020: {len(kz_mit)} von {len(fn.KENNZAHLEN)}; "
                 f"fehlend: {', '.join(sorted(set(fn.KENNZAHLEN) - set(kz_mit))) or 'keine'}")
        if nur_fy:
            b.append(f"  Nur als JAHRESWERT vorhanden (kein Quartal): {', '.join(nur_fy)}")
        b.append("  Innere Konsistenz:")
        b.extend(konsistenz(zeilen))
        b.append("  Vergleich mit den belegten Werten:")
        for per in firma_ref.get("perioden", []):
            typ = per.get("typ", "Q")
            for kennzahl, soll in per["werte"].items():
                z = _finde(zeilen, kennzahl, per["end"], typ) or _naechste_zeile(zeilen, kennzahl, per["end"], typ)
                tol = (per.get("toleranz") or {}).get(kennzahl, 0)
                gesamt["vergleiche"] += 1
                if z is None:
                    gesamt["fehlt"] += 1
                    status = "FEHLT"
                    b.append(f"    {per['end']} {kennzahl}: soll {_fmt(soll)}, in den SEC-Daten NICHT gefunden")
                else:
                    ist = z["wert_erst"]
                    ok = ist is not None and abs(ist - soll) <= tol
                    status = "OK" if ok else "ABWEICHUNG"
                    gesamt["ok" if ok else "abweichung"] += 1
                    b.append(f"    {z['end']} {kennzahl}: soll {_fmt(soll)}, Erstfassung {_fmt(ist)}, "
                             f"Letztfassung {_fmt(z['wert_letzt'])} ({z['quelle']}, {z['taxonomie']}:{z['tag']}, "
                             f"{z['form_erst']} vom {z['filed_erst']}, Fiskal {z['fiskaljahr']} {z['fiskalperiode']}, "
                             f"Kalender {z['kalender']}) -> {status}")
                ergebnis.append({"ticker": ticker, "end": per["end"], "kennzahl": kennzahl,
                                 "soll": soll, "ist": None if z is None else z["wert_erst"],
                                 "status": status, "quelle_beleg": per.get("quelle")})
            b.append(f"    Beleg: {per.get('quelle', '')}")
        b.append("")
    b.insert(3, f"ERGEBNIS: {gesamt['ok']} von {gesamt['vergleiche']} belegten Werten stimmen "
                f"innerhalb der Toleranz; {gesamt['abweichung']} Abweichungen; {gesamt['fehlt']} nicht gefunden.")
    b.insert(4, "")
    with io.open(f"{AUSGABE}/validierung.md", "w", encoding="utf-8") as f:
        f.write("\n".join(b) + "\n")
    with io.open(f"{AUSGABE}/validierung.json", "w", encoding="utf-8") as f:
        json.dump({"gesamt": gesamt, "vergleiche": ergebnis}, f, ensure_ascii=False, indent=1)
    print("\n".join(b))
    # Abweichungen stehen im Bericht; der Lauf gilt nur bei Abstuerzen als
    # gescheitert (sonst Fehlschlag-Mails fuer erwartbare Befunde).
    return 0


# ---------------------------------------------------------------------------
# Voll
# ---------------------------------------------------------------------------

def _lade_archiv(pfad):
    import urllib.request
    if os.path.exists(pfad) and os.path.getsize(pfad) > 1e9:
        print(f"Archiv vorhanden: {pfad} ({os.path.getsize(pfad)/1e6:,.0f} MB)")
        return
    url = "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    start = time.time()
    with urllib.request.urlopen(req, timeout=300) as r, open(pfad, "wb") as f:
        n = 0
        while True:
            block = r.read(8 * 1024 * 1024)
            if not block:
                break
            f.write(block); n += len(block)
            if n % (256 * 1024 * 1024) < 8 * 1024 * 1024:
                print(f"  {n/1e6:,.0f} MB nach {time.time()-start:.0f} s", flush=True)
    print(f"Archiv geladen: {n/1e6:,.0f} MB in {time.time()-start:.0f} s")


class JahresParquet:
    """Ein Parquet-Writer je Kalenderjahr des Periodenendes."""

    def __init__(self, praefix, schema, jahr_feld="end"):
        self.praefix, self.schema, self.jahr_feld = praefix, schema, jahr_feld
        self.writer, self.puffer, self.zeilen = {}, defaultdict(list), 0

    def add(self, zeilen):
        for z in zeilen:
            e = z.get(self.jahr_feld) or ""
            jahr = e[:4] if len(e) >= 4 else "0000"
            self.puffer[jahr].append(z)
        self.zeilen += len(zeilen)

    def spuele(self, erzwingen=False):
        import pyarrow as pa
        import pyarrow.parquet as pq
        for jahr, liste in list(self.puffer.items()):
            if not liste or (len(liste) < 200000 and not erzwingen):
                continue
            tabelle = pa.Table.from_pylist(liste, schema=self.schema)
            if jahr not in self.writer:
                self.writer[jahr] = pq.ParquetWriter(
                    f"{AUSGABE}/{self.praefix}_{jahr}.parquet", self.schema, compression="zstd")
            self.writer[jahr].write_table(tabelle)
            self.puffer[jahr] = []

    def schliesse(self):
        self.spuele(erzwingen=True)
        for w in self.writer.values():
            w.close()


def _schemata():
    import pyarrow as pa
    kennzahl = pa.schema([
        ("cik", pa.int64()), ("kennzahl", pa.string()), ("typ", pa.string()),
        ("start", pa.string()), ("end", pa.string()), ("fiskaljahr", pa.int64()),
        ("fiskalperiode", pa.string()), ("kalender", pa.string()),
        ("kalender_quelle", pa.string()), ("wert_erst", pa.float64()),
        ("filed_erst", pa.string()), ("form_erst", pa.string()), ("accn_erst", pa.string()),
        ("wert_letzt", pa.float64()), ("filed_letzt", pa.string()),
        ("form_letzt", pa.string()), ("accn_letzt", pa.string()), ("restated", pa.bool_()),
        ("taxonomie", pa.string()), ("tag", pa.string()), ("einheit", pa.string()),
        ("quelle", pa.string()), ("n_einreichungen", pa.int64())])
    roh = pa.schema([
        ("cik", pa.int64()), ("taxonomie", pa.string()), ("tag", pa.string()),
        ("einheit", pa.string()), ("start", pa.string()), ("end", pa.string()),
        ("val", pa.float64()), ("accn", pa.string()), ("fy", pa.int64()),
        ("fp", pa.string()), ("form", pa.string()), ("filed", pa.string()),
        ("frame", pa.string())])
    return kennzahl, roh


def _als_float(z, felder):
    for f in felder:
        v = z.get(f)
        if v is not None and not isinstance(v, float):
            try:
                z[f] = float(v)
            except (TypeError, ValueError):
                z[f] = None
    return z


def voll(archiv, hoechstens=None):
    os.makedirs(AUSGABE, exist_ok=True)
    _lade_archiv(archiv)
    schema_k, schema_r = _schemata()
    kennzahlen = JahresParquet("fundament_kennzahlen", schema_k)
    rohdaten = JahresParquet("fundament_roh", schema_r)
    metadaten, fehler = [], []
    abdeckung_kz = defaultdict(set)      # kennzahl -> CIKs mit Quartalswert seit 2020
    abdeckung_jahr = defaultdict(set)    # Jahr -> CIKs mit Umsatz-Quartal
    filer_typen = defaultdict(int)
    start = time.time()
    with zipfile.ZipFile(archiv) as zf:
        namen = [n for n in zf.namelist() if n.lower().endswith(".json")]
        print(f"{len(namen)} JSON-Dateien im Archiv", flush=True)
        if hoechstens:
            namen = namen[:hoechstens]
        for i, name in enumerate(namen, 1):
            try:
                with zf.open(name) as f:
                    firma = json.load(f)
                if not (firma.get("facts") or {}):
                    continue
                meta, zeilen = fn.normalisiere(firma)
                for z in zeilen:
                    _als_float(z, ("wert_erst", "wert_letzt"))
                kennzahlen.add(zeilen)
                rohdaten.add([_als_float(r, ("val",)) for r in fn.alle_fakten(firma)])
                cik = firma.get("cik")
                for z in zeilen:
                    if z["typ"] in ("Q", "B") and z["end"] >= "2020-01-01":
                        abdeckung_kz[z["kennzahl"]].add(cik)
                    if z["kennzahl"] == "umsatz" and z["typ"] == "Q":
                        abdeckung_jahr[z["end"][:4]].add(cik)
                filer_typen[meta["filer_typ"]] += 1
                meta["waehrungen_umsatz"] = ";".join(meta["waehrungen_umsatz"])
                metadaten.append(meta)
            except Exception as e:  # noqa
                fehler.append({"datei": name, "fehler": f"{type(e).__name__}: {e}"[:300]})
            if i % 500 == 0:
                kennzahlen.spuele(); rohdaten.spuele()
                print(f"  {i}/{len(namen)} Dateien, {kennzahlen.zeilen:,} Kennzahl-Zeilen, "
                      f"{rohdaten.zeilen:,} Rohfakten, {len(fehler)} Fehler, {time.time()-start:.0f} s", flush=True)
    kennzahlen.schliesse(); rohdaten.schliesse()
    schreibe_csv(f"{AUSGABE}/fundament_firmen.csv", metadaten,
                 ["cik", "name", "filer_typ", "waehrungen_umsatz", "erstes_ende",
                  "letztes_ende", "zeilen", "einreichungen"])
    with io.open(f"{AUSGABE}/fundament_fehler.json", "w", encoding="utf-8") as f:
        json.dump(fehler, f, ensure_ascii=False, indent=1)
    b = ["# Fundament Phase 1, Vollarchiv: Abdeckungsbericht",
         f"Stand {dt.datetime.now(dt.timezone.utc):%d.%m.%Y %H:%M} UTC",
         f"Firmen mit Fakten: {len(metadaten)}; Fehler: {len(fehler)}; "
         f"Kennzahl-Zeilen: {kennzahlen.zeilen:,}; Rohfakten: {rohdaten.zeilen:,}; Dauer {time.time()-start:.0f} s",
         "", "## Filer-Typen (F4)"]
    b += [f"  {k}: {v}" for k, v in sorted(filer_typen.items())]
    b += ["", "## Firmen mit Umsatz-Quartalswert je Kalenderjahr"]
    b += [f"  {j}: {len(s)}" for j, s in sorted(abdeckung_jahr.items())]
    b += ["", "## Firmen mit mindestens einem Wert seit 2020, je Kennzahl"]
    b += [f"  {k}: {len(abdeckung_kz.get(k, ()))}" for k in fn.KENNZAHLEN]
    with io.open(f"{AUSGABE}/abdeckung.md", "w", encoding="utf-8") as f:
        f.write("\n".join(b) + "\n")
    print("\n".join(b))
    return 0


# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--modus", choices=["probe", "voll"], default="probe")
    p.add_argument("--archiv", default="fundament_daten/companyfacts.zip")
    p.add_argument("--hoechstens", type=int, default=None,
                   help="nur die ersten N Dateien des Archivs (Testlauf)")
    a = p.parse_args()
    if not UA:
        print("SEC_USER_AGENT fehlt (Secret im Actions-Lauf).")
        return 1
    if a.modus == "probe":
        return probe()
    os.makedirs(os.path.dirname(a.archiv), exist_ok=True)
    return voll(a.archiv, a.hoechstens)


if __name__ == "__main__":
    sys.exit(main())
