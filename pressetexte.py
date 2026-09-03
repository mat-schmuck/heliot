# -*- coding: utf-8 -*-
"""Pressetext-Archiv fuer Gerhards KI-Abfrage (Vorstufe zu "Quartal ueber
Quartal"): die Ergebnis-Pressemitteilungen (Anhang 99.1 der 8-Ks mit
Item 2.02) der Firmen mit Konsens, je Firma die juengsten QUARTALE Stueck,
als gepackter Klartext im privaten Datenrepo.

Ablage (Ordner pressetexte im Datenrepo):
  <CIK10>/<accession>.txt.gz   Klartext samt Tabellenzeilen (Zellen mit
                               ' | ' getrennt), auf TEXT_DECKEL Zeichen
                               begrenzt
  index.jsonl                  eine Zeile je Text: cik, ticker, accession,
                               filed, report, exhibit, zeichen, quelle, zeit
  stand.json                   je CIK: Ticker, gepruefte Accessions, Zeit
                               (Fortsetzung ueber mehrere Laeufe)
  laeufe.jsonl                 eine Zeile je Lauf

Der Abzug laeuft in Portionen (hoechstens N Firmen je Lauf); Firmen mit
frischem Stand werden uebersprungen. Der 8-K-Strom (vorabwerte_8k.py)
speichert jeden neu gelesenen Text ueber speichern() mit. SEC-Abrufe nur im
Actions-Lauf (Secret SEC_USER_AGENT), hoechstens rund acht je Sekunde.
"""
import argparse
import datetime as dt
import gzip
import io
import json
import os
import re
import sys
import time

QUARTALE = 8
TEXT_DECKEL = 80000
PAUSE_S = 0.13
FRISCH_TAGE = 20
ORDNER = "pressetexte"


# ---------------------------------------------------------------------------
# Ablage
# ---------------------------------------------------------------------------

def _jetzt():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def text_pfad(daten, cik, accession):
    return os.path.join(daten, ORDNER, f"{int(cik):010d}", f"{accession}.txt.gz")


def vorhanden(daten, cik, accession):
    return os.path.exists(text_pfad(daten, cik, accession))


def text_lesen(daten, cik, accession):
    p = text_pfad(daten, cik, accession)
    if not os.path.exists(p):
        return None
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return f.read()


def speichern(daten, cik, ticker, accession, filed, report, exhibit, text, quelle="archiv"):
    """Legt einen Text ab und schreibt die Index-Zeile; gibt die Metadaten zurueck."""
    text = (text or "").strip()
    gekuerzt = len(text) > TEXT_DECKEL
    if gekuerzt:
        text = text[:TEXT_DECKEL] + "\n[... gekuerzt auf " + str(TEXT_DECKEL) + " Zeichen ...]"
    p = text_pfad(daten, cik, accession)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    # mtime 0: derselbe Text ergibt immer dieselben Bytes; sonst legen Strom und Archiv-Portion
    # dieselbe Datei byte-verschieden an, und Git meldet beim Zusammenfuehren einen add/add-Konflikt
    with open(p, "wb") as roh:
        with gzip.GzipFile(fileobj=roh, mode="wb", mtime=0) as gz:
            gz.write(text.encode("utf-8"))
    meta = {"zeit": _jetzt(), "cik": int(cik), "ticker": ticker, "accession": accession, "filed": filed,
            "report": report, "exhibit": exhibit, "zeichen": len(text), "gekuerzt": gekuerzt, "quelle": quelle}
    os.makedirs(os.path.join(daten, ORDNER), exist_ok=True)
    with io.open(os.path.join(daten, ORDNER, "index.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")
    return meta


def index_lesen(daten):
    p = os.path.join(daten, ORDNER, "index.jsonl")
    if not os.path.exists(p):
        return []
    raus = []
    with io.open(p, encoding="utf-8") as f:
        for zeile in f:
            zeile = zeile.strip()
            if zeile:
                raus.append(json.loads(zeile))
    return raus


def texte_der_firma(daten, cik, hoechstens=QUARTALE):
    """[(meta, text)] der juengsten Texte einer Firma, juengste zuerst."""
    metas = {}
    for m in index_lesen(daten):
        if int(m.get("cik", -1)) == int(cik):
            metas[m["accession"]] = m
    liste = sorted(metas.values(), key=lambda m: (m.get("filed") or "", m["accession"]), reverse=True)[:hoechstens]
    raus = []
    for m in liste:
        t = text_lesen(daten, cik, m["accession"])
        if t:
            raus.append((m, t))
    return raus


def stand_laden(daten):
    p = os.path.join(daten, ORDNER, "stand.json")
    if not os.path.exists(p):
        return {}
    with io.open(p, encoding="utf-8") as f:
        return json.load(f)


def stand_schreiben(daten, stand):
    os.makedirs(os.path.join(daten, ORDNER), exist_ok=True)
    p = os.path.join(daten, ORDNER, "stand.json")
    tmp = p + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(stand, f, ensure_ascii=False, indent=0, sort_keys=True)
    os.replace(tmp, p)


# ---------------------------------------------------------------------------
# SEC
# ---------------------------------------------------------------------------

def submissions(cik, hole):
    return json.loads(hole(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"))


def exhibit(cik, accession, hole):
    """(Dateiname, Klartext) des Anhangs 99.1, sonst (None, None); Logik wie
    messung_8k.exhibit_text, aber mit uebergebenem Abruf (pruefbar ohne Netz)."""
    import messung_8k as m8k
    ordner = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}"
    index = json.loads(hole(ordner + "/index.json"))
    dateien = [d for d in index.get("directory", {}).get("item", [])
               if d.get("name", "").lower().endswith((".htm", ".html"))]
    kandidaten = [d for d in dateien if re.search(r"ex[-_]?99", d["name"].lower())]
    if not kandidaten:
        kandidaten = [d for d in dateien if not d["name"].lower().startswith("0")]
    if not kandidaten:
        return None, None
    kandidaten.sort(key=lambda d: int(d.get("size") or 0), reverse=True)
    name = kandidaten[0]["name"]
    roh = hole(ordner + "/" + name)
    try:
        html_roh = roh.decode("utf-8")
    except UnicodeDecodeError:
        html_roh = roh.decode("latin-1")
    return name, m8k.html_zu_text(html_roh)


def firmen(daten, ticker_zu_cik, nur=None):
    """[(cik, ticker)] der Firmen mit Konsens, je Firma der Haupt-Ticker,
    nach Ticker sortiert; nur = Liste gewuenschter Ticker."""
    import konsens_einfrieren as ke
    import vorabwerte_8k as va
    bestand = ke._json(os.path.join(daten, "konsens", "firmen_mit_konsens.json"), {})
    if nur:
        gewuenscht = {t.strip().upper() for t in nur if t.strip()}
        bestand = {t: v for t, v in bestand.items() if str(t).upper() in gewuenscht}
        for t in gewuenscht:
            if t not in {str(b).upper() for b in bestand}:
                bestand[t] = {}
    raus = va.hauptticker(bestand, ticker_zu_cik)
    return sorted(raus.items(), key=lambda kv: kv[1])


# ---------------------------------------------------------------------------
# Lauf
# ---------------------------------------------------------------------------

def lauf(daten, hoechstens=1200, quartale=QUARTALE, nur=None, hole=None, ticker_zu_cik=None,
         log=print, jetzt=None, warte=True, frisch_tage=FRISCH_TAGE):
    if hole is None or ticker_zu_cik is None:
        import fundament_lauf as fl
        if not fl.UA:
            raise RuntimeError("SEC_USER_AGENT fehlt (Secret im Actions-Lauf).")
        hole = hole or fl.hole
        ticker_zu_cik = ticker_zu_cik or fl.ticker_zu_cik()
    jetzt = jetzt or dt.datetime.now(dt.timezone.utc)
    stand = stand_laden(daten)
    liste = firmen(daten, ticker_zu_cik, nur)
    bilanz = {"zeit": jetzt.replace(microsecond=0).isoformat(), "firmen_gesamt": len(liste), "firmen": 0,
              "uebersprungen": 0, "texte_neu": 0, "texte_da": 0, "ohne_exhibit": 0, "fehler": 0, "abbruch": None}
    log(f"Firmen mit Konsens: {len(liste)}; je Firma die juengsten {quartale} Ergebnis-8-Ks; hoechstens {hoechstens or 'alle'} Firmen in diesem Lauf")

    def pause():
        if warte:
            time.sleep(PAUSE_S)

    try:
        for cik, ticker in liste:
            if hoechstens and bilanz["firmen"] >= hoechstens:
                bilanz["abbruch"] = "Portion voll"
                break
            s = stand.get(str(cik))
            if s and not nur:
                try:
                    alter = (jetzt - dt.datetime.fromisoformat(s["zeit"])).days
                except (KeyError, ValueError):
                    alter = 10 ** 6
                if s.get("vollstaendig") and alter < frisch_tage:
                    bilanz["uebersprungen"] += 1
                    continue
            try:
                sub = submissions(cik, hole)
                pause()
            except Exception as e:  # noqa
                bilanz["fehler"] += 1
                log(f"  {ticker} {cik}: Einreichungen nicht lesbar: {str(e)[:120]}")
                continue
            import messung_8k as m8k
            achtks = m8k.ergebnis_8ks(sub)[:quartale]
            geprueft = list((s or {}).get("accessions") or [])
            neu = da = leer = 0
            for fd, rd, acc, prim in achtks:
                if vorhanden(daten, cik, acc):
                    da += 1
                    continue
                if acc in geprueft and (s or {}).get("leer", {}).get(acc):
                    leer += 1
                    continue
                try:
                    name, text = exhibit(cik, acc, hole)
                    pause()
                except Exception as e:  # noqa
                    bilanz["fehler"] += 1
                    log(f"  {ticker} {acc}: Anhang nicht lesbar: {str(e)[:120]}")
                    continue
                if not text:
                    leer += 1
                    s = s or {}
                    s.setdefault("leer", {})[acc] = True
                    continue
                speichern(daten, cik, ticker, acc, fd, rd, name, text, quelle="archiv")
                neu += 1
            stand[str(cik)] = {"ticker": ticker, "zeit": jetzt.replace(microsecond=0).isoformat(),
                               "accessions": [a[2] for a in achtks], "vollstaendig": True,
                               "leer": (s or {}).get("leer", {})}
            bilanz["firmen"] += 1
            bilanz["texte_neu"] += neu
            bilanz["texte_da"] += da
            bilanz["ohne_exhibit"] += leer
            log(f"  {ticker} {cik}: {len(achtks)} Ergebnis-8-Ks, {neu} neu, {da} vorhanden, {leer} ohne Anhang")
            if bilanz["firmen"] % 100 == 0:
                stand_schreiben(daten, stand)
    except KeyboardInterrupt:
        bilanz["abbruch"] = "unterbrochen"
    stand_schreiben(daten, stand)
    os.makedirs(os.path.join(daten, ORDNER), exist_ok=True)
    with io.open(os.path.join(daten, ORDNER, "laeufe.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(bilanz, ensure_ascii=False) + "\n")
    log(f"Ergebnis: {bilanz}")
    return bilanz


# ---------------------------------------------------------------------------
# Selbsttest (ohne Netz)
# ---------------------------------------------------------------------------

def selbsttest() -> int:
    import tempfile
    import konsens_einfrieren as ke
    fehler = 0

    def p(name, ok, extra=""):
        nonlocal fehler
        print(f"  {'ok  ' if ok else 'FEHL'} {name}{(' ' + str(extra)) if extra else ''}")
        if not ok:
            fehler += 1

    def sub_json(cik, n):
        accs = [f"{cik:010d}-26-{i:06d}" for i in range(n)]
        return json.dumps({"filings": {"recent": {
            "form": ["8-K"] * n + ["10-Q"], "filingDate": [f"2026-{(i % 12) + 1:02d}-15" for i in range(n)] + ["2026-05-01"],
            "reportDate": [f"2026-{(i % 12) + 1:02d}-01" for i in range(n)] + [""],
            "accessionNumber": accs + [f"{cik:010d}-26-999999"], "primaryDocument": ["a.htm"] * (n + 1),
            "items": ["2.02,9.01"] * n + [""]}}}).encode("utf-8")

    html = ("<html><body><p>Apple today announced results.</p><table><tr><td>Net sales</td><td>94,036</td>"
            "</tr></table><p>Outlook: we expect growth.</p></body></html>").encode("utf-8")
    aufrufe = []

    def hole(url):
        aufrufe.append(url)
        if "submissions" in url:
            cik = int(re.search(r"CIK(\d+)", url).group(1))
            return sub_json(cik, 10 if cik == 320193 else 2)
        if url.endswith("index.json"):
            if "000001472426000001" in url.replace("-", ""):
                return json.dumps({"directory": {"item": [{"name": "0001.htm", "size": 10}]}}).encode("utf-8")
            return json.dumps({"directory": {"item": [{"name": "a-ex99_1.htm", "size": 5000},
                                                       {"name": "0001.htm", "size": 100}]}}).encode("utf-8")
        return html

    with tempfile.TemporaryDirectory() as tmp:
        ke._schreibe_json(os.path.join(tmp, "konsens", "firmen_mit_konsens.json"),
                          {"AAPL": {}, "BF-B": {}, "BF-A": {}, "XYZ": {}})
        tzc = {"AAPL": 320193, "BF-B": 14693, "BF-A": 14693}
        f = firmen(tmp, tzc)
        p("Firmen: Haupt-Ticker je CIK (BF-B vor BF-A), Unbekanntes faellt weg",
          f == [(320193, "AAPL"), (14693, "BF-B")], f)
        b = lauf(tmp, hoechstens=0, quartale=8, hole=hole, ticker_zu_cik=tzc, log=lambda *_: None,
                 jetzt=dt.datetime(2026, 9, 3, tzinfo=dt.timezone.utc), warte=False)
        p("Lauf: Apple bekommt die juengsten 8 von 10 Ergebnis-8-Ks, Brown-Forman seine 2",
          b["firmen"] == 2 and b["texte_neu"] == 10 and b["texte_da"] == 0, b)
        idx = index_lesen(tmp)
        p("Index: 10 Zeilen mit Ticker, Datum, Anhang und Zeichenzahl",
          len(idx) == 10 and idx[0]["ticker"] == "AAPL" and idx[0]["exhibit"] == "a-ex99_1.htm" and idx[0]["zeichen"] > 30, idx[:1])
        t = text_lesen(tmp, 320193, idx[0]["accession"])
        p("Text: Klartext mit Tabellenzeile und Ausblick", "Net sales | 94,036" in t and "Outlook" in t, t)
        juengste = texte_der_firma(tmp, 320193, 3)
        p("Texte der Firma: juengste zuerst, hoechstens 3",
          len(juengste) == 3 and juengste[0][0]["filed"] >= juengste[1][0]["filed"] >= juengste[2][0]["filed"],
          [m["filed"] for m, _ in juengste])
        n1 = len(aufrufe)
        b2 = lauf(tmp, hoechstens=0, quartale=8, hole=hole, ticker_zu_cik=tzc, log=lambda *_: None,
                  jetzt=dt.datetime(2026, 9, 4, tzinfo=dt.timezone.utc), warte=False)
        p("Zweiter Lauf am naechsten Tag: beide Firmen frisch, uebersprungen, kein Abruf",
          b2["uebersprungen"] == 2 and b2["firmen"] == 0 and len(aufrufe) == n1, b2)
        b3 = lauf(tmp, hoechstens=0, quartale=8, hole=hole, ticker_zu_cik=tzc, log=lambda *_: None,
                  jetzt=dt.datetime(2026, 10, 3, tzinfo=dt.timezone.utc), warte=False)
        p("Dritter Lauf nach 30 Tagen: geprueft, alles schon da, nichts neu geholt",
          b3["firmen"] == 2 and b3["texte_da"] == 10 and b3["texte_neu"] == 0, b3)
        b4 = lauf(tmp, hoechstens=0, quartale=8, nur=["AAPL"], hole=hole, ticker_zu_cik=tzc, log=lambda *_: None,
                  jetzt=dt.datetime(2026, 9, 3, tzinfo=dt.timezone.utc), warte=False)
        p("Gezielt: nur Apple, trotz frischem Stand geprueft", b4["firmen"] == 1 and b4["texte_da"] == 8, b4)
        ke._schreibe_json(os.path.join(tmp, "konsens", "firmen_mit_konsens.json"), {"LEER": {}})
        b5 = lauf(tmp, hoechstens=0, quartale=8, hole=hole, ticker_zu_cik={"LEER": 14724}, log=lambda *_: None,
                  jetzt=dt.datetime(2026, 9, 3, tzinfo=dt.timezone.utc), warte=False)
        st = stand_laden(tmp)
        p("Ohne Anhang: das 8-K ohne Anhang 99.1 wird gezaehlt und im Stand als leer gemerkt, das andere abgelegt",
          b5["ohne_exhibit"] == 1 and b5["texte_neu"] == 1 and list(st["14724"]["leer"]) == ["0000014724-26-000001"]
          and not vorhanden(tmp, 14724, "0000014724-26-000001") and vorhanden(tmp, 14724, "0000014724-26-000000"), b5)
        b5b = lauf(tmp, hoechstens=0, quartale=8, hole=hole, ticker_zu_cik={"LEER": 14724}, log=lambda *_: None,
                   jetzt=dt.datetime(2026, 10, 3, tzinfo=dt.timezone.utc), warte=False)
        p("Ohne Anhang, spaeterer Lauf: das leere 8-K wird nicht erneut abgerufen",
          b5b["ohne_exhibit"] == 1 and b5b["texte_da"] == 1 and b5b["texte_neu"] == 0, b5b)
        ke._schreibe_json(os.path.join(tmp, "konsens", "firmen_mit_konsens.json"), {"AAPL": {}, "BF-B": {}})
        m = speichern(tmp, 1, "T", "0000000001-26-000001", "2026-01-01", "2025-12-31", "x.htm", "A" * (TEXT_DECKEL + 500))
        speichern(tmp, 2, "T2", "0000000002-26-000001", "2026-01-01", "2025-12-31", "x.htm", "gleicher Text")
        b1 = open(text_pfad(tmp, 2, "0000000002-26-000001"), "rb").read()
        speichern(tmp, 2, "T2", "0000000002-26-000001", "2026-01-01", "2025-12-31", "x.htm", "gleicher Text")
        b2 = open(text_pfad(tmp, 2, "0000000002-26-000001"), "rb").read()
        p("Ablage ist byte-gleich bei gleichem Text (kein Zeitstempel im gzip)", b1 == b2 and text_lesen(tmp, 2, "0000000002-26-000001") == "gleicher Text")
        p("Deckel: langer Text wird gekuerzt und als gekuerzt vermerkt",
          m["gekuerzt"] and m["zeichen"] < TEXT_DECKEL + 100 and text_lesen(tmp, 1, "0000000001-26-000001").endswith("Zeichen ...]"), m)
        b6 = lauf(tmp, hoechstens=1, quartale=8, hole=hole, ticker_zu_cik=tzc, log=lambda *_: None,
                  jetzt=dt.datetime(2026, 11, 3, tzinfo=dt.timezone.utc), warte=False)
        p("Portion: hoechstens eine Firma je Lauf, Abbruchgrund genannt",
          b6["firmen"] == 1 and b6["abbruch"] == "Portion voll", b6)
    print("Alles bestanden." if fehler == 0 else f"{fehler} Fehler.")
    return fehler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--daten", default="daten")
    ap.add_argument("--hoechstens", type=int, default=1200)
    ap.add_argument("--quartale", type=int, default=QUARTALE)
    ap.add_argument("--ticker", default="", help="nur diese Ticker, mit Beistrich getrennt")
    ap.add_argument("--selbsttest", action="store_true")
    a = ap.parse_args()
    if a.selbsttest:
        return selbsttest()
    nur = [t for t in a.ticker.split(",") if t.strip()] or None
    b = lauf(a.daten, hoechstens=a.hoechstens, quartale=a.quartale, nur=nur)
    return 1 if b["fehler"] and not b["firmen"] else 0


if __name__ == "__main__":
    sys.exit(main())
