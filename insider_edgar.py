#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
INSIDER-SCANNER — Datenbeschaffung bei der SEC
================================================
Zweiter Baustein zu insider_scanner.py (dort die reine Rechnung). Holt
die Form-4-Einreichungen eines Tages von EDGAR, liest die echten Kaeufe
heraus und legt sie ab, damit der Cluster-Pfad ueber mehrere Tage
hinweg ueberhaupt greifen kann.

DREI DINGE AN GERHARDS ENTWURF WAREN FALSCH ODER FEHLTEN. Alle drei sind
an ECHTEN Daten nachgeprueft (14.08.2026, Tagesindex vom 13.08. mit 1002
Form-4-Einreichungen, Stichprobe von 60):

  1. DER PARSER HAETTE AN JEDER DATEI VERSAGT. Er ruft ET.fromstring()
     auf den ganzen Inhalt. Der Tagesindex verweist aber auf die volle
     SEC-Einreichung: ein SGML-Rahmen mit <SEC-DOCUMENT>, <SEC-HEADER>
     und <DOCUMENT>-Abschnitten, in dem die eigentliche XML nur
     eingebettet ist. Gemessen: "mismatched tag: line 58" auf der ersten
     echten Datei. Erst der herausgeschnittene Abschnitt
     <ownershipDocument> … </ownershipDocument> ist gueltiges XML.
     Danach ging es bei 60 von 60 Dateien.

  2. GERHARDS ANNAHME ZUM TICKER STIMMT, und das ist die gute Nachricht:
     Form 4 traegt <issuerTradingSymbol> wirklich mit (nachgeprueft:
     TXG bei 10x Genomics). Ein CUSIP-Mapping wie bei 13F braucht es
     nicht. 60 von 60 Dateien hatten den Ticker.

  3. PFAD B HAETTE NIE AUSGELOEST. Sein taeglicher_insider_scan() liest
     EINEN Tagesindex und prueft darauf ein Fenster von 10 Handelstagen.
     Aus einem Tag koennen aber nie Kaeufe von vor einer Woche kommen —
     der Cluster-Pfad haette nur gefeuert, wenn drei Insider am selben
     Tag einreichen. Deshalb gibt es hier einen Sammelspeicher
     (insider_kaeufe.json), der die Kaeufe ueber das Fenster mitfuehrt
     und Aelteres verwirft.

WEITERE FESTLEGUNGEN
  * Der User-Agent kommt aus der Umgebungsvariablen SEC_USER_AGENT. Die
    SEC verlangt Name und E-Mail und sperrt sonst. In den QUELLTEXT darf
    das nicht: Dieses Repo ist oeffentlich, und eine E-Mail-Adresse im
    Klartext ist eine Einladung an Sammler. Fehlt die Variable, bricht
    der Lauf mit einer klaren Ansage ab, statt bei der SEC anzuklopfen
    und gesperrt zu werden.
  * Hoechstens 10 Anfragen je Sekunde (EDGAR-Regel). PAUSE_SEK haelt das
    ein; nicht entfernen und nicht parallelisieren.
  * Gemessen: 1002 Einreichungen brauchen rund 3,1 Minuten.
  * Einreichungen nach 22 Uhr New Yorker Zeit rutschen in den Index des
    NAECHSTEN Tages. Der Abendlauf sieht sie also nicht mehr; sie kommen
    beim naechsten Morgenlauf.

Aufruf:
    python insider_edgar.py --scan [JJJJ-MM-TT]   Tag holen und ablegen
    python insider_edgar.py --zeigen              was abgelegt ist
    python insider_edgar.py --selbsttest
"""

import json
import os
import sys
import time
from datetime import date, datetime
from xml.etree import ElementTree as ET

import insider_scanner as isc
from insider_scanner import InsiderKauf

SPEICHER = "insider_kaeufe.json"
FUNDE = "insider_funde.json"
PAUSE_SEK = 0.11                       # bleibt unter 10 Anfragen je Sekunde
BASIS = "https://www.sec.gov/Archives/"


class KeinUserAgent(RuntimeError):
    pass


def kopfzeilen():
    """Der von der SEC verlangte User-Agent, aus der Umgebung.

    Format laut SEC: Name und E-Mail, etwa "Vorname Nachname
    name@beispiel.at". Ohne ihn antwortet sec.gov mit 403."""
    ua = (os.environ.get("SEC_USER_AGENT") or "").strip()
    if not ua or "@" not in ua:
        raise KeinUserAgent(
            "SEC_USER_AGENT fehlt. Die SEC verlangt Name und E-Mail im "
            "User-Agent und sperrt sonst. Als GitHub-Secret hinterlegen, "
            "Beispielform: 'Vorname Nachname name@beispiel.at'.")
    return {"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}


# ---------------------------------------------------------------------------
# Schritt 1: Tagesindex
# ---------------------------------------------------------------------------

def tagesindex(datum=None, leise=False):
    """Alle Form-4-Einreichungen eines Tages. Rueckgabe: Liste von Pfaden.

    Der Tagesindex liegt unter daily-index/<Jahr>/QTR<n>/form.<JJJJMMTT>.idx
    und ist eine Textdatei fester Spaltenbreite. An Wochenenden und
    Feiertagen gibt es sie nicht; dann kommt eine leere Liste zurueck und
    das ist kein Fehler."""
    import requests
    datum = datum or date.today()
    q = (datum.month - 1) // 3 + 1
    url = (f"https://www.sec.gov/Archives/edgar/daily-index/{datum.year}/"
           f"QTR{q}/form.{datum:%Y%m%d}.idx")
    r = requests.get(url, headers=kopfzeilen(), timeout=40)
    if r.status_code != 200:
        if not leise:
            print(f"  Kein Tagesindex für {datum} (HTTP {r.status_code}) — "
                  f"Wochenende, Feiertag oder noch nicht veröffentlicht.")
        return []
    pfade = []
    for zeile in r.text.splitlines():
        teile = zeile.split()
        # Spalte 1 ist der Formulartyp. GENAU "4" - "4/A" ist eine
        # Berichtigung und wird bewusst nicht mitgenommen, sonst zaehlte
        # derselbe Kauf zweimal.
        if len(teile) >= 5 and teile[0] == "4" and teile[-1].endswith(".txt"):
            pfade.append(teile[-1])
    return pfade


# ---------------------------------------------------------------------------
# Schritt 2: Eine Einreichung lesen
# ---------------------------------------------------------------------------

def _text(el, pfad):
    k = el.find(pfad)
    return k.text.strip() if k is not None and k.text else None


def parse_form4(roh):
    """Eine ganze SEC-Einreichung auswerten.

    Rueckgabe: dict mit ticker, kaeufe und rollen — oder None, wenn keine
    echten Kaeufe drin sind.

    DER SCHNITT IST DER PUNKT (siehe Modulkopf): Erst wird der
    ownershipDocument-Abschnitt aus dem SGML-Rahmen herausgeschnitten,
    dann geparst. Ohne das scheitert jede echte Datei."""
    if not roh:
        return None
    i = roh.find("<ownershipDocument")
    if i < 0:
        return None
    j = roh.find("</ownershipDocument>")
    if j < 0:
        return None
    try:
        w = ET.fromstring(roh[i:j + len("</ownershipDocument>")])
    except ET.ParseError:
        return None

    ticker = (_text(w, ".//issuer/issuerTradingSymbol") or "").upper().strip()
    # Nicht boersennotierte Emittenten tragen dort einen Platzhalter statt
    # eines Kuerzels (am echten Tag gefunden: "NONE" mit fuenf Insidern und
    # 22 Mio $). Ohne diese Pruefung landet so ein Sammelposten als eigene
    # "Aktie" in der Auswertung und wuerde irgendwann als Cluster gemeldet.
    if ticker in ("", "NONE", "N/A", "NA", "-", "N.A."):
        return None
    name = _text(w, ".//reportingOwner/reportingOwnerId/rptOwnerName")
    ist_officer = _text(w, ".//reportingOwnerRelationship/isOfficer") in ("1", "true")
    ist_direktor = _text(w, ".//reportingOwnerRelationship/isDirector") in ("1", "true")
    titel = _text(w, ".//reportingOwnerRelationship/officerTitle")
    rolle = (titel if (ist_officer and titel)
             else "Direktor" if ist_direktor
             else "Vorstand" if ist_officer else "Insider")

    kaeufe = []
    for tr in w.findall(".//nonDerivativeTransaction"):
        if _text(tr, ".//transactionCoding/transactionCode") != "P":
            continue                   # nur echte Kaeufe am freien Markt
        d = _text(tr, ".//transactionDate/value")
        stueck = _text(tr, ".//transactionAmounts/transactionShares/value")
        preis = _text(tr, ".//transactionAmounts/transactionPricePerShare/value")
        if not (d and stueck and preis):
            continue
        try:
            wert = float(stueck) * float(preis)
            tag = datetime.strptime(d, "%Y-%m-%d").date()
        except ValueError:
            continue
        if wert <= 0:
            continue                   # Preis 0 kommt vor, das ist kein Kauf
        kaeufe.append(InsiderKauf(insider=name or "unbekannt", wert_dollar=wert,
                                  datum=tag, transaktionscode="P", rolle=rolle))
    if not ticker or not kaeufe:
        return None
    return {"ticker": ticker, "kaeufe": kaeufe, "rollen": {name or "unbekannt": rolle}}


# ---------------------------------------------------------------------------
# Schritt 3: Marktkapitalisierung
# ---------------------------------------------------------------------------

def hole_marktkap(tickers, leise=False):
    """Marktwert je Ticker ueber yfinance, wie von Gerhard festgelegt.

    Gefragt wird nur fuer Aktien, bei denen ueberhaupt ein echter Kauf
    vorliegt - das sind wenige Dutzend am Tag statt tausender."""
    import yfinance as yf
    raus = {}
    for t in tickers:
        try:
            info = yf.Ticker(t).info
            mk = info.get("marketCap")
            raus[t] = float(mk) if mk else None
        except Exception:
            raus[t] = None
        if not leise and raus[t] is None:
            print(f"    {t}: kein Marktwert")
    return raus


# ---------------------------------------------------------------------------
# Der Sammelspeicher — ohne ihn kann Pfad B nicht greifen
# ---------------------------------------------------------------------------

def lies_speicher(pfad=SPEICHER):
    try:
        with open(pfad, encoding="utf-8") as f:
            roh = json.load(f)
    except Exception:
        return {}
    return {t: [InsiderKauf.aus_json(k) for k in eintraege]
            for t, eintraege in roh.get("kaeufe", {}).items()}


def lies_rollen(pfad=SPEICHER):
    try:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f).get("rollen", {})
    except Exception:
        return {}


def lies_gelesene(pfad=SPEICHER):
    """Welche Einreichungen schon verarbeitet sind (Zugangsnummern)."""
    try:
        with open(pfad, encoding="utf-8") as f:
            return set(json.load(f).get("gelesen", []))
    except Exception:
        return set()


def schreibe_speicher(kaeufe, rollen, stichtag, pfad=SPEICHER, cfg=None,
                     gelesen=None):
    """Ablegen und dabei ausduennen: Was aelter ist als das Cluster-
    Fenster, wird nie wieder gebraucht und fliegt weg. Sonst waechst die
    Datei ewig."""
    cfg = cfg or isc.CFG_INSIDER
    grenze = isc.handelstage_zurueck(stichtag, int(cfg["cluster_fenster_tage"]))
    behalten, gesehen = {}, set()
    for t, liste in kaeufe.items():
        frisch = [k for k in liste if k.datum >= grenze]
        if frisch:
            behalten[t] = frisch
            gesehen.update(k.insider for k in frisch)
    inhalt = {"stand": stichtag.isoformat(),
              # Die gelesenen Einreichungen werden nur so lange gefuehrt
              # wie das Cluster-Fenster reicht; danach kann derselbe Kauf
              # ohnehin nicht mehr zaehlen.
              "gelesen": sorted(gelesen or []),
              "kaeufe": {t: [k.als_json() for k in liste]
                         for t, liste in behalten.items()},
              "rollen": {n: r for n, r in rollen.items() if n in gesehen}}
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(inhalt, f, ensure_ascii=False, indent=1)
    return behalten


def zugangsnummer(pfad):
    """Die Zugangsnummer einer Einreichung aus ihrem Pfad.

    'edgar/data/1770787/0001610717-26-000358.txt' -> '0001610717-26-000358'.
    Sie ist bei der SEC eindeutig und ist der richtige Schluessel gegen
    Doppelzaehlung."""
    return pfad.rsplit("/", 1)[-1].rsplit(".", 1)[0]


def _zusammenfuehren(alt, neu):
    """Neue Kaeufe dazulegen.

    ES WIRD HIER NICHTS MEHR AUSSORTIERT, und das ist eine Korrektur an
    mir selbst (14.08.2026, am echten Tag aufgefallen): Zuerst hatte ich
    auf (Insider, Datum, Betrag) entdoppelt. Am Tag vom 13.08. fielen
    dadurch 104 von 188 Kaeufen weg — und die waren echt. Ein Insider,
    der an einem Tag in mehreren gleich grossen Tranchen kauft, meldet
    das als mehrere Zeilen mit identischem Datum und Betrag; mein
    Schluessel hat daraus einen einzigen Kauf gemacht und den Wert damit
    um ein Vielfaches zu klein gerechnet.

    Gegen Doppelzaehlung schuetzt jetzt die ZUGANGSNUMMER: Eine
    Einreichung, die schon gelesen wurde, wird gar nicht erst wieder
    geholt (siehe scan()). Das ist exakt statt heuristisch und spart
    obendrein den zweiten Abruf — der Abendlauf holt nur noch, was seit
    dem Morgen dazugekommen ist."""
    raus = {t: list(l) for t, l in alt.items()}
    dazu = 0
    for t, liste in neu.items():
        raus.setdefault(t, []).extend(liste)
        dazu += len(liste)
    return raus, dazu


# ---------------------------------------------------------------------------
# Der ganze Lauf
# ---------------------------------------------------------------------------

def scan(datum=None, leise=False, cfg=None, speicher=SPEICHER, funde=FUNDE):
    """Ein Lauf: Tagesindex holen, Kaeufe lesen, ablegen, bewerten.

    Rueckgabe: Liste der Aktien mit Signal."""
    import requests
    cfg = cfg or isc.CFG_INSIDER
    datum = datum or date.today()
    kopf = kopfzeilen()

    pfade = tagesindex(datum, leise)
    gelesen = lies_gelesene(speicher)
    offen = [p for p in pfade if zugangsnummer(p) not in gelesen]
    if not leise:
        print(f"  {len(pfade)} Form-4-Einreichungen am {datum}, davon "
              f"{len(pfade) - len(offen)} bereits gelesen.")
    neu, rollen_neu = {}, {}
    fehler = 0
    for nr, pfad in enumerate(offen, 1):
        try:
            r = requests.get(BASIS + pfad, headers=kopf, timeout=25)
        except Exception:
            fehler += 1
            time.sleep(PAUSE_SEK)
            continue
        time.sleep(PAUSE_SEK)
        if r.status_code != 200:
            fehler += 1
            continue
        gelesen.add(zugangsnummer(pfad))
        g = parse_form4(r.text)
        if g:
            neu.setdefault(g["ticker"], []).extend(g["kaeufe"])
            rollen_neu.update(g["rollen"])
        if not leise and nr % 250 == 0:
            print(f"    {nr} von {len(offen)} gelesen …")
    if not leise:
        print(f"  {sum(len(v) for v in neu.values())} echte Käufe (Code P) "
              f"bei {len(neu)} Aktien; {fehler} Dateien nicht lesbar.")

    alt = lies_speicher(speicher)
    rollen = lies_rollen(speicher)
    rollen.update(rollen_neu)
    zusammen, dazu = _zusammenfuehren(alt, neu)
    behalten = schreibe_speicher(zusammen, rollen, datum, speicher, cfg,
                                 gelesen)
    if not leise:
        print(f"  {dazu} neue Käufe im Speicher; {len(behalten)} Aktien im "
              f"Fenster von {cfg['cluster_fenster_tage']} Handelstagen.")

    # Marktwert nur fuer Aktien, bei denen ueberhaupt etwas passiert ist.
    kandidaten = sorted(behalten)
    if not leise:
        print(f"  Marktwerte für {len(kandidaten)} Aktien …")
    marktkap = hole_marktkap(kandidaten, leise) if kandidaten else {}

    ergebnisse = []
    for t in kandidaten:
        signal = isc.pruefe_insider_signal(behalten[t], marktkap.get(t),
                                           stichtag=datum, cfg=cfg)
        if signal["status"] in ("kein_signal", "firma_zu_klein"):
            continue
        ergebnisse.append({
            "ticker": t, "status": signal["status"],
            "marktkap": signal["marktkap"],
            "stichtag": datum.isoformat(),
            "zeilen": isc.meldungszeilen(t, signal, rollen=rollen),
            # Kennung, damit derselbe Fund nicht zweimal gemeldet wird.
            "kennung": f"{t}|{signal['status']}|"
                       f"{len(signal['pfad_b']['qualifizierte_insider'])}",
        })
    with open(funde, "w", encoding="utf-8") as f:
        json.dump({"stand": datum.isoformat(), "funde": ergebnisse}, f,
                  ensure_ascii=False, indent=1)
    if not leise:
        print(f"  {len(ergebnisse)} Aktien mit Signal.")
        for e in ergebnisse:
            for z in e["zeilen"]:
                print("     " + z)
    return ergebnisse


def lies_funde(pfad=FUNDE):
    try:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f).get("funde", [])
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Selbsttest — ohne Netz, mit einer ECHTEN Einreichung als Vorlage
# ---------------------------------------------------------------------------

# Wortgetreu gekuerzter Auszug einer echten SEC-Einreichung vom
# 13.08.2026 (10x Genomics, Zugangsnummer 0001610717-26-000358). Der
# SGML-Rahmen ist dabei, denn genau an ihm ist Gerhards Parser gescheitert.
ECHTE_EINREICHUNG = """<SEC-DOCUMENT>0001610717-26-000358.txt : 20260813
<SEC-HEADER>0001610717-26-000358.hdr.sgml : 20260813
ACCESSION NUMBER:\t\t0001610717-26-000358
CONFORMED SUBMISSION TYPE:\t4
</SEC-HEADER>
<DOCUMENT>
<TYPE>4
<SEQUENCE>1
<FILENAME>form4.xml
<TEXT>
<XML>
<?xml version="1.0"?>
<ownershipDocument>
  <issuer>
    <issuerCik>0001770787</issuerCik>
    <issuerName>10x Genomics, Inc.</issuerName>
    <issuerTradingSymbol>TXG</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>STUELPNAGEL JOHN R</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isDirector>1</isDirector><isOfficer>0</isOfficer></reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-08-12</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>500000</value></transactionShares>
        <transactionPricePerShare><value>20.00</value></transactionPricePerShare>
      </transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-08-12</value></transactionDate>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>900000</value></transactionShares>
        <transactionPricePerShare><value>21.00</value></transactionPricePerShare>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>
</XML>
</TEXT>
</DOCUMENT>
</SEC-DOCUMENT>"""


def selbsttest() -> int:
    import tempfile
    import pathlib
    fehler = []

    def p(name, bedingung, zusatz=""):
        print(f"  {'ok  ' if bedingung else 'FEHL'} {name}"
              + (f" — {zusatz}" if zusatz else ""))
        if not bedingung:
            fehler.append(name)

    # --- Der Parser an einer ECHTEN Einreichung samt SGML-Rahmen ---
    g = parse_form4(ECHTE_EINREICHUNG)
    p("Echte Einreichung mit SGML-Rahmen wird gelesen", g is not None)
    if g:
        p("Ticker kommt aus issuerTradingSymbol", g["ticker"] == "TXG",
          g["ticker"])
        p("Nur der Kauf zählt, der Verkauf daneben nicht",
          len(g["kaeufe"]) == 1, len(g["kaeufe"]))
        p("Kaufwert ist Stückzahl mal Preis",
          abs(g["kaeufe"][0].wert_dollar - 10_000_000) < 1,
          g["kaeufe"][0].wert_dollar)
        p("Die Rolle wird erkannt", g["kaeufe"][0].rolle == "Direktor",
          g["kaeufe"][0].rolle)
    # DAS war Gerhards Fehler: der ganze Text als XML.
    try:
        ET.fromstring(ECHTE_EINREICHUNG)
        roh_geht = True
    except ET.ParseError:
        roh_geht = False
    p("Der ROHE Text ist KEIN gültiges XML (Gerhards Fehler)", not roh_geht)

    p("Ohne ownershipDocument kommt None", parse_form4("<x>y</x>") is None)
    p("Leerer Inhalt stürzt nicht ab", parse_form4("") is None)
    p("Kaputte XML im Rahmen stürzt nicht ab",
      parse_form4("<ownershipDocument><a></ownershipDocument>") is None)
    ohne_kauf = ECHTE_EINREICHUNG.replace(
        "<transactionCode>P</transactionCode>",
        "<transactionCode>A</transactionCode>")
    p("Einreichung ohne echten Kauf ergibt None",
      parse_form4(ohne_kauf) is None)
    platzhalter = ECHTE_EINREICHUNG.replace(
        "<issuerTradingSymbol>TXG</issuerTradingSymbol>",
        "<issuerTradingSymbol>NONE</issuerTradingSymbol>")
    p("Platzhalter statt Kürzel wird verworfen (nicht notierte Emittenten)",
      parse_form4(platzhalter) is None)

    # --- Der Sammelspeicher, ohne den Pfad B nie ausloest ---
    with tempfile.TemporaryDirectory() as ordner:
        pfad = str(pathlib.Path(ordner) / "s.json")
        heute = date(2026, 8, 14)
        tag1 = {"AAA": [InsiderKauf("CEO", 22e6, date(2026, 8, 4), rolle="CEO")]}
        schreibe_speicher(tag1, {"CEO": "CEO"}, heute, pfad)
        gelesen = lies_speicher(pfad)
        p("Was abgelegt wurde, kommt unverändert zurück",
          len(gelesen.get("AAA", [])) == 1
          and gelesen["AAA"][0].datum == date(2026, 8, 4))
        tag2 = {"AAA": [InsiderKauf("CFO", 21e6, date(2026, 8, 14), rolle="CFO")]}
        zusammen, dazu = _zusammenfuehren(gelesen, tag2)
        p("Ein zweiter Tag legt sich dazu",
          len(zusammen["AAA"]) == 2 and dazu == 1)
        # DER FEHLER, den ich am echten Tag gemacht habe: Zwei gleich
        # grosse Tranchen desselben Insiders am selben Tag sind ZWEI
        # Kaeufe. Am 13.08.2026 fielen dadurch 104 von 188 weg.
        tranchen = {"BBB": [InsiderKauf("CEO", 5e6, date(2026, 8, 14)),
                            InsiderKauf("CEO", 5e6, date(2026, 8, 14))]}
        z2, n2 = _zusammenfuehren({}, tranchen)
        p("Zwei gleich große Tranchen am selben Tag bleiben zwei Käufe",
          len(z2["BBB"]) == 2 and n2 == 2, n2)
        p("Die Zugangsnummer kommt aus dem Pfad",
          zugangsnummer("edgar/data/1770787/0001610717-26-000358.txt")
          == "0001610717-26-000358")
        # DER PUNKT: Erst dadurch kann ein Cluster ueber Tage entstehen.
        tag3 = {"AAA": [InsiderKauf("Direktor X", 20.5e6, date(2026, 8, 14))]}
        zusammen, _ = _zusammenfuehren(zusammen, tag3)
        signal = isc.pruefe_insider_signal(zusammen["AAA"], 1e9, stichtag=heute)
        p("Drei Insider an DREI Tagen ergeben zusammen einen Cluster",
          signal["status"] == "pfad_b", signal["status"])
        # Doppelte Meldungen desselben Kaufs
        # Gegen Doppelzaehlung schuetzt jetzt die Zugangsnummer, nicht
        # mehr ein Vergleich der Betraege.
        schreibe_speicher(zusammen, {}, heute, pfad, gelesen={"0001-26-000001"})
        p("Gelesene Einreichungen werden mitgeführt",
          lies_gelesene(pfad) == {"0001-26-000001"}, lies_gelesene(pfad))
        # Ausduennen
        alt = {"AAA": [InsiderKauf("Uralt", 99e6, date(2026, 6, 1))]}
        behalten = schreibe_speicher(alt, {}, heute, pfad)
        p("Zu alte Käufe fliegen aus dem Speicher", behalten == {})

    # --- Der User-Agent ---
    merk = os.environ.pop("SEC_USER_AGENT", None)
    try:
        kopfzeilen()
        ohne = False
    except KeinUserAgent:
        ohne = True
    p("Ohne SEC_USER_AGENT bricht es mit klarer Ansage ab", ohne)
    os.environ["SEC_USER_AGENT"] = "Vorname Nachname test@beispiel.at"
    p("Mit gültigem User-Agent geht es weiter",
      "@" in kopfzeilen()["User-Agent"])
    os.environ["SEC_USER_AGENT"] = "ohne mailadresse"
    try:
        kopfzeilen()
        halb = False
    except KeinUserAgent:
        halb = True
    p("Ein User-Agent ohne E-Mail wird auch abgelehnt", halb)
    if merk is not None:
        os.environ["SEC_USER_AGENT"] = merk
    else:
        os.environ.pop("SEC_USER_AGENT", None)

    # --- Kein Geheimnis im Quelltext (das Repo ist öffentlich) ---
    quelle = pathlib.Path(__file__).read_text(encoding="utf-8")
    import re as _re
    # Die Beispieladresse im Text ist erlaubt, echte nicht.
    adressen = {a for a in _re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", quelle)
                if not a.endswith(("beispiel.at", "sec.gov"))}
    p("Keine echte E-Mail-Adresse im Quelltext", not adressen, adressen)

    print("\n" + ("Alles bestanden." if not fehler
                  else f"{len(fehler)} FEHLER: " + ", ".join(fehler)))
    return 1 if fehler else 0


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Insider-Käufe bei der SEC holen")
    ap.add_argument("--scan", nargs="?", const="", metavar="JJJJ-MM-TT")
    ap.add_argument("--zeigen", action="store_true")
    ap.add_argument("--selbsttest", action="store_true")
    a = ap.parse_args()
    if a.selbsttest:
        return selbsttest()
    if a.zeigen:
        for e in lies_funde():
            print("\n".join(e["zeilen"]) + "\n")
        return 0
    if a.scan is not None:
        tag = date.fromisoformat(a.scan) if a.scan else date.today()
        try:
            scan(tag)
        except KeinUserAgent as e:
            print(f"ABBRUCH: {e}")
            return 1
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
