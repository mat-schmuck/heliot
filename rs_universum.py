#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RS-UNIVERSUM: relative Staerke gegen den ganzen US-Markt
=========================================================
Gerhards Antworten vom 12.09.2026 auf die Recherche (R1 bis R6, Teil 5,
Teil 6, Luecken 1, 3, 5 und 6), am selben Abend ergaenzt um drei Antworten
auf den IBD-Abgleich (ueber Mathias): Vergleichsbasis ist der GANZE
US-Markt, die Schwellen sind nur noch Kennzeichnung, jede Einzelrendite
wird nach oben gekappt. Grundsatz, woertlich: "Die relative
Staerke, die Sektor-Raenge und die IBD-Ratings sind ENTSCHEIDUNGSHILFEN,
keine Filter." Dieses Modul rechnet, es filtert nichts; die einzige
Ausnahme bleibt die Fokusliste von Kapitel 9 (red_to_green, RS ueber 90).

WAS GERECHNET WIRD
  R1  Universum: alle Stammaktien der Nasdaq (nasdaqlisted.txt) und seit
      12.09.2026 abends auch von NYSE und NYSE American (otherlisted.txt,
      Exchange N und A; ETFs und Test-Titel sind in beiden Verzeichnissen
      gekennzeichnet). Optionsscheine, Einheiten, Rechte, Vorzugsaktien,
      Anleihen und SPACs bleiben draussen (Namensfilter; Vorzugsaktien
      tragen bei NYSE ein Dollarzeichen im Symbol, Optionsscheine,
      Einheiten und Rechte enden auf .W, .U und .R); ADRs bleiben drin
      (Antwort 8: Auslaender laufen ueberall voll mit).
      E3 (Gerhard, 13.09.2026, Entscheidung 3, bestaetigt am 15.09.2026 mit
      Antwort N2 "JA, nur Cboe Global Markets"): dazu die Cboe (Exchange Z).
      Von ihren 1.639 Zeilen bleibt nach den Filtern genau Cboe Global
      Markets uebrig; die uebrigen sind ETFs, ETNs, ein Goldtrust und
      Einheiten. Kommt dort eine Stammaktie dazu, laeuft sie kuenftig mit,
      und die Zahl je Boerse im Befund zeigt es.
  E2 (Gerhard, 13.09.2026, Entscheidung 2, bestaetigt am 15.09.2026 mit
      Antwort N1): Fondsvehikel und Mantelgesellschaften gehoeren nicht in
      den Bezug, auch wenn das Verzeichnis sie als Stammaktie fuehrt. Zwei
      Wege, beide zaehlen: der NAME (der Nasdaq-Zusatz "Closed End Fund"
      sowie die Woerter "Fund" und "Acquisition", siehe E2_NAME) und der
      TYP aus der eigenen Zuordnungsliste (Entscheidung 10, siehe
      typ_filter). Gemessen am 21.09.2026: von 5.666 Titeln fallen 317
      heraus, 214 ueber beide Wege, 81 nur ueber den Namen, 22 nur ueber
      den Typ. Gerhard nimmt in Kauf, dass Business Development Companies
      ohne diese Woerter im Namen weiter mitlaufen. Ohne Zuordnungsliste
      greift nur der Name, und der Befund sagt es.
  R2  Schwellen: Mindestkurs 15 Dollar und Tagesumsatz von 10 Millionen
      Dollar im 50-Tage-Schnitt. Seit 12.09.2026 abends NUR KENNZEICHNUNG
      ("im Universum"): Die Vergleichsbasis fuer das Perzentil sind ALLE
      Stammaktien mit voller Historie, auch die unter den Schwellen; sie
      stehen mit Grund unter "ausserhalb", bekommen aber ebenso einen RS.
  R3  Klassische IBD-Formel: 40 Prozent auf die juengsten drei Monate,
      je 20 Prozent auf die drei davor (config.lookback); der Rohwert
      kommt aus red_to_green.rs_rohwert, die EINE Stelle dieser Formel.
      Seit 12.09.2026 abends wird jede Einzelrendite nach oben bei plus 50
      Prozent gekappt (config.lookback.rs_kappung). GEMESSEN: Ohne
      Kappung stand AAOI bei RS 97 und SNDK bei 99, IBD nannte 55 und 87;
      mit Kappung und dem ganzen US-Markt als Bezug liegen dreizehn
      oeffentliche IBD-Werte innerhalb von 5 Punkten (mittlerer Fehler
      1,3); ohne NYSE im Bezug waren es bis zu 13 Punkte daneben.
  R4  Anzeige schlicht "RS 93"; R6 mit dem Zusatz "sehr gut" ab 85.
  R5  Dazu die RS-Linie (Kurs geteilt durch SPY beziehungsweise QQQ) mit
      dem Hinweis, ob sie auf einem 52-Wochen-Hoch steht.
  Teil 5  Zwei Stufen getrennt: RS-Linien-Hoch WAEHREND eines Kurs-Hochs
      und RS-Linien-Hoch OBWOHL der Kurs keines hat (IBDs blauer Punkt).
  Luecke 5  Listen-Aktien bekommen IMMER einen RS-Wert, GEGEN den Bezug
      gerechnet, nicht als Teil davon: Der Wert ist der Anteil der
      Bezugsaktien mit kleinerem Rohwert; steht die Listenaktie selbst im
      Bezug, wird sie fuer ihren eigenen Rang ausgenommen (das gilt seit
      12.09.2026 abends fuer JEDE Aktie: Rang ohne sich selbst). So aendert
      keine Listenaktie die Verteilung des Bezugs.

DIE VIER ZUVERLAESSIGKEITSREGELN (Teil 6)
  1. Mindestabdeckung: Liefert der Kursabruf fuer weniger als 95 Prozent
     des Universums Daten, gibt es KEIN RS, sondern "nicht verfuegbar".
  2. Lebenszeichen: lebenszeichen.py meldet, wenn an einem Handelstag
     nicht gerechnet wurde (Datei mit Handelstag).
  3. Plausibilitaet: Die Perzentile 1 bis 99 muessen ungefaehr
     gleichverteilt sein (je Dezil zwischen 5 und 15 Prozent).
  4. Selbsttest mit einer kuenstlichen Aktie, die 1 Prozent je Tag
     steigt: Ihr Rohwert muss exakt dem vorgerechneten Wert entsprechen
     und ihr Perzentil im echten Universum ganz oben liegen.
  Schlaegt Regel 1 oder 4 an, tragen ALLE Aktien "nicht verfuegbar".

FESTLEGUNGEN (Luecke 6)
  Zu kurze Historie (unter 253 Schlusskursen): "nicht verfuegbar".
  Gleichstand beim Perzentil: Der Rang ist der Anteil der Aktien mit
  STRIKT kleinerem Rohwert; gleiche Rohwerte bekommen denselben Rang
  (die niedrigere Stufe), niemand bekommt einen halben Punkt geschenkt.
  Kurse: Yahoo mit auto_adjust=False, also SPLITBEREINIGT, aber NICHT
  dividendenbereinigt (Luecke 1); dasselbe gilt fuer die Indizes und
  fuer die Sektor-ETFs (sektor_radar, pattern_scanner.fetch_history).

Aufruf:
  python rs_universum.py --bauen            ohne Nachtscan (nachschlag_daten.yml), schreibt
                                            rs_universum.json samt der Aktien der Mappe
                                            kaufpunkte_aktuell.xlsx als "listen"
                                            (rund sechs Minuten fuer rund 6.600 Symbole);
                                            im Nachtscan ruft pattern_scanner bauen() selbst
  python rs_universum.py --selbsttest       ohne Netz
"""

import argparse
import bisect
import csv
import io
import json
import os
import re
import sys
import time
from datetime import date, datetime

from config import CFG
import kennzahlen_technik
import marktbreite
import red_to_green

CFGU = CFG["rs_universum"]
DATEI = "rs_universum.json"
# Die Zuordnungsliste der Branchen und Typen (Entscheidung 10) liegt im
# PRIVATEN Datenrepo; die Ablaeufe holen sie mit dem Datenrepo-Token hierher.
# Fehlt sie, greift von E2 nur der Namensteil, und der Befund sagt es.
ZUORDNUNG = os.path.join(".cache", "zuordnung", "branchen.json")
# Die Mappe des letzten Nachtscans; ihre Aktien sind die "listen" eines
# Baus ohne Scan (Etappe 0, Punkt 2).
MAPPE = "kaufpunkte_aktuell.xlsx"

# Titel, die keine Stammaktien sind (R2: ETFs und Fonds draussen, SPACs
# erst nach der Uebernahme). ADRs ("American Depositary Shares") bleiben
# ausdruecklich drin.
AUSSCHLUSS = re.compile(
    r"warrant|\brights?\b|\bunits?\b|preferred|\bnotes?\b|debenture|subordinated|"
    r"\bbonds?\b|\bSPAC\b|trust preferred|"
    r"capital securities|\bETN\b", re.I)

# E2, der Namensteil (Gerhard, Antwort N1 vom 15.09.2026): "Der Zusatz Closed
# End Fund und die Woerter Fund und Acquisition im Namen duerfen einen Titel
# aus dem Bezug nehmen, zusaetzlich zum Typ." Die Wortgrenzen halten
# Firmennamen wie Fundamental oder Refund draussen; gegengelesen am
# 21.09.2026 an allen 81 Titeln, die NUR ueber den Namen herausfallen: lauter
# Closed-End-Fonds, BDCs mit diesem Zusatz und Mantelgesellschaften.
E2_NAME = re.compile(r"closed end fund|\bfunds?\b|\bacquisitions?\b", re.I)


# ---------------------------------------------------------------------------
# Universum
# ---------------------------------------------------------------------------

def nasdaq_liste(text=None, holen=None, leise=True):
    """Alle Stammaktien der Nasdaq aus dem amtlichen Symbolverzeichnis.

    Rueckgabe: (Liste von {symbol, name, markt, boerse}, {Grund: Anzahl}).
    Der Text kann uebergeben werden (Selbsttest); sonst wird er geholt."""
    if text is None:
        text = (holen or _text_holen)(CFGU["quelle"])
    return _verzeichnis(text, "Symbol", lambda z: "Nasdaq", leise, "Nasdaq-Verzeichnis")


def andere_liste(text=None, holen=None, leise=True):
    """Alle Stammaktien von NYSE und NYSE American aus otherlisted.txt
    (Exchange N und A laut config; Arca, BATS und IEX bleiben draussen).
    Vorzugsaktien tragen dort ein Dollarzeichen im Symbol, Optionsscheine,
    Einheiten und Rechte enden auf .W, .U und .R."""
    if text is None:
        text = (holen or _text_holen)(CFGU["quelle_andere"])
    boersen = dict(CFGU["andere_boersen"])
    return _verzeichnis(text, "ACT Symbol",
                        lambda z: boersen.get(str(z.get("Exchange") or "").strip()),
                        leise, "NYSE-Verzeichnis")


_SYMBOL = re.compile(r"[A-Z]{1,6}(\.[A-Z])?")


def _verzeichnis(text, symbol_spalte, boerse_von, leise, titel):
    zeilen = list(csv.DictReader(io.StringIO(text), delimiter="|"))
    liste, gruende = [], {}

    def raus(grund):
        gruende[grund] = gruende.get(grund, 0) + 1

    for z in zeilen:
        sym = str(z.get(symbol_spalte) or "").strip()
        if not sym or sym.startswith("File Creation"):
            continue
        boerse = boerse_von(z)
        if not boerse:
            raus("andere Boerse"); continue
        name = str(z.get("Security Name") or "").strip()
        if str(z.get("ETF") or "").strip().upper() == "Y":
            raus("ETF"); continue
        if str(z.get("Test Issue") or "").strip().upper() == "Y":
            raus("Test-Titel"); continue
        if "$" in sym or re.search(r"\.(W|U|R)$", sym) or not _SYMBOL.fullmatch(sym):
            raus("kein Stammtitel (Symbol: Vorzug, Optionsschein, Einheit, Recht)"); continue
        if AUSSCHLUSS.search(name):
            raus("kein Stammtitel (Optionsschein, Einheit, Recht, Vorzug, Anleihe, SPAC)"); continue
        if E2_NAME.search(name):
            raus("Fondsvehikel oder Mantel laut Name (Entscheidung 2)"); continue
        liste.append({"symbol": sym, "name": name, "boerse": boerse,
                      "markt": str(z.get("Market Category") or "").strip()})
    if not leise:
        print(f"  {titel}: {len(zeilen)} Zeilen, {len(liste)} Stammaktien; "
              + "; ".join(f"{k} {v}" for k, v in gruende.items()))
    return liste, gruende


def typ_filter(liste, zuordnung_pfad=None, zuordnung=None, befund=None):
    """E2, der Typ-Teil: Was die eigene Zuordnungsliste (Entscheidung 10)
    nicht als Stammaktie fuehrt, gehoert nicht in den Bezug.
    -> (gefilterte Liste, Befund). Der Befund nennt NUR Zahlen: Die Liste
    stammt aus dem lizenzierten EODHD-Abzug, rs_universum.json ist
    oeffentlich.
    Ohne Liste bleibt die Liste unveraendert, und der Befund sagt warum."""
    import kennzahlen_gruppen as kg
    if zuordnung is None and zuordnung_pfad:
        zuordnung, befund = kg.zuordnung_lesen(zuordnung_pfad)
    befund = befund or {}
    if not zuordnung:
        return liste, {"status": "nicht verfuegbar",
                       "grund": befund.get("grund") or "die eigene Zuordnungsliste der Branchen liegt nicht vor"}
    bleibt, raus, ohne_eintrag = [], 0, 0
    for e in liste:
        typ = str((zuordnung.get(kg.schluessel(e["symbol"])) or {}).get("typ") or "").strip()
        if not typ:
            ohne_eintrag += 1
            bleibt.append(e)
        elif typ.lower() == "common stock":
            bleibt.append(e)
        else:
            raus += 1
    return bleibt, {"status": "ok", "stand": befund.get("stand"), "eintraege": befund.get("eintraege"),
                    "geprueft": len(liste), "raus": raus, "ohne_eintrag": ohne_eintrag}


def _text_holen(url):
    import requests
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.text


def yahoo_symbol(sym):
    """Nasdaq schreibt Klassen mit Punkt (BRK.B), Yahoo mit Bindestrich."""
    return str(sym).strip().upper().replace(".", "-")


def kurse_holen(symbole, block=None, zeitraum=None, download=None, leise=True):
    """Tageskurse aller Symbole in Bloecken ueber Yahoo. Rueckgabe:
    {symbol: {"daten": [...], "close": [...], "high": [...], "low": [...],
    "volume": [...]}}, chronologisch, ohne leere Kerzen.

    download(symbolliste) ersetzt yfinance im Selbsttest und muss ein
    dict derselben Form liefern."""
    zeitraum = zeitraum or CFGU["abruf_zeitraum"]
    return _in_bloecken(symbole, lambda teil: _yahoo_block(teil, zeitraum), block, download, leise, "Kurse")


def _in_bloecken(symbole, abruf, block=None, download=None, leise=True, titel="Kurse"):
    """Ruft abruf(teil) je Block auf und sammelt die Ergebnisse. Ein
    gescheiterter Block bekommt nach 20 Sekunden einen zweiten Versuch.
    download ersetzt den Abruf im Selbsttest (ohne Nachladen)."""
    block = block or int(CFGU["abruf_block"])
    raus = {}
    t0 = time.time()
    for i in range(0, len(symbole), block):
        teil = symbole[i:i + block]
        if download is not None:
            raus.update(download(teil))
            continue
        try:
            raus.update(abruf(teil))
        except Exception as e:  # noqa
            if not leise:
                print(f"  {titel}, Block {i // block + 1}: Abruf gescheitert ({type(e).__name__}), "
                      f"zweiter Versuch in 20 s")
            time.sleep(20)
            try:
                raus.update(abruf(teil))
            except Exception as e2:  # noqa
                if not leise:
                    print(f"  {titel}, Block {i // block + 1}: erneut gescheitert ({type(e2).__name__})")
    if download is None:
        fehlend = [s for s in symbole if s not in raus]
        # Yahoo laesst in grossen Bloecken gelegentlich STILL Symbole aus
        # (gemessen 12.09.2026: 45 Prozent eines NYSE-Abrufs in 300er-
        # Bloecken, ohne Fehlermeldung). Fehlendes einmal in kleinen
        # Bloecken nachholen; was dann noch fehlt, ist wirklich nicht da.
        # Fehlt ALLES, ist Yahoo weg, dann wird nicht verdoppelt.
        if fehlend and len(fehlend) < len(symbole):
            vorher = len(raus)
            for i in range(0, len(fehlend), 50):
                try:
                    raus.update(abruf(fehlend[i:i + 50]))
                except Exception:  # noqa
                    continue
            if not leise:
                print(f"  {titel}: nachgeladen {len(raus) - vorher} von {len(fehlend)} zunaechst fehlenden Symbolen")
    if not leise:
        print(f"  {titel} fuer {len(raus)} von {len(symbole)} Symbolen in {time.time() - t0:.0f} s")
    return raus


def allzeithochs_holen(symbole, block=None, download=None, leise=True):
    """Punkt 16 der Etappe 2: das Allzeithoch je Symbol aus Yahoos
    Monatskerzen ueber die ganze Historie. Rueckgabe {Symbol: (Hoch, Monat
    'JJJJ-MM')}. Splitbereinigt wie die Tageskurse (auto_adjust=False).
    GEMESSEN 14.09.2026 an denselben 100 Aktien: Das hoechste Monatshoch
    ist bei allen 100 gleich dem hoechsten Tageshoch aus period=max, der
    Abruf dauert 2,5 statt 8,9 Sekunden je Block."""
    return _in_bloecken(symbole, _yahoo_allzeit_block, block, download, leise, "Allzeithoch")


def _yahoo_allzeit_block(symbole):
    import pandas as pd
    import yfinance as yf
    roh = yf.download(" ".join(yahoo_symbol(s) for s in symbole), period="max", interval="1mo",
                      group_by="ticker", progress=False, auto_adjust=False, threads=True, actions=False)
    raus = {}
    for s in symbole:
        try:
            df = roh[yahoo_symbol(s)] if isinstance(roh.columns, pd.MultiIndex) else roh
            h = df["High"].dropna()
            if h.empty:
                continue
            raus[s] = (float(h.max()), str(h.idxmax())[:7])
        except Exception:  # noqa
            continue
    return raus


def _yahoo_block(symbole, zeitraum):
    import pandas as pd
    import yfinance as yf
    # SPLITBEREINIGT, NICHT dividendenbereinigt (auto_adjust=False):
    # Yahoos "Close" traegt die Splits, nur "Adj Close" auch Dividenden.
    # actions=True liefert Yahoos Split-Meldungen mit (Etappe 2: Erkennung
    # eines Splits, den Yahoo noch nicht in die aelteren Kurse eingerechnet
    # hat, siehe kennzahlen_technik.split_verdacht).
    roh = yf.download(" ".join(yahoo_symbol(s) for s in symbole), period=zeitraum,
                      interval="1d", group_by="ticker", progress=False,
                      auto_adjust=False, threads=True, actions=True)
    raus = {}
    for s in symbole:
        try:
            df = roh[yahoo_symbol(s)] if isinstance(roh.columns, pd.MultiIndex) else roh
            df = df.dropna(subset=["Close"])
            if df.empty:
                continue
            raus[s] = {"daten": [d.strftime("%Y-%m-%d") for d in df.index],
                       # Seit Etappe 2 auch die Eroeffnung (Luecke, seit Eroeffnung)
                       "open": [float(x) for x in df["Open"].values],
                       "close": [float(x) for x in df["Close"].values],
                       "high": [float(x) for x in df["High"].values],
                       "low": [float(x) for x in df["Low"].values],
                       "volume": [float(x) if x == x else 0.0 for x in df["Volume"].values]}
            if "Stock Splits" in df.columns:
                raus[s]["splits"] = {d.strftime("%Y-%m-%d"): float(x)
                                     for d, x in zip(df.index, df["Stock Splits"].values) if x == x and x}
        except Exception:  # noqa
            continue
    return raus


def aus_scanner_df(df):
    """Der Kursrahmen des Nachtscans (Spalten datetime, open, high, low,
    close, volume) in dieselbe Form wie kurse_holen."""
    return {"daten": [str(d)[:10] for d in df["datetime"]],
            "open": [float(x) for x in df["open"]] if "open" in df.columns else [],
            "close": [float(x) for x in df["close"]],
            "high": [float(x) for x in df["high"]],
            "low": [float(x) for x in df["low"]],
            "volume": [float(x) if x == x else 0.0 for x in df["volume"]]}


# ---------------------------------------------------------------------------
# Kennzahlen je Aktie
# ---------------------------------------------------------------------------

def _linie(k, index):
    """Die RS-Linie: Kurs geteilt durch den Index, auf gleiche Tage
    ausgerichtet. Rueckgabe Liste, chronologisch."""
    if not index:
        return []
    idx = dict(zip(index["daten"], index["close"]))
    return [c / idx[d] for d, c in zip(k["daten"], k["close"]) if d in idx and idx[d] > 0]


def _hoch(werte, fenster):
    """Steht der letzte Wert auf dem Hoch der letzten fenster Werte? None,
    wenn die Reihe kuerzer ist als das Fenster."""
    if len(werte) < fenster:
        return None
    teil = werte[-fenster:]
    return teil[-1] >= max(teil)


def _abstand(werte, fenster):
    """Abstand des letzten Werts zum Hoch der letzten fenster Werte in
    Prozent, auf eine Stelle gerundet, 0,0 auf dem Hoch, negativ darunter.
    None, wenn die Reihe kuerzer ist als das Fenster (dieselbe Regel wie
    _hoch, damit Text und Kennzeichen nie auseinanderlaufen)."""
    if len(werte) < fenster:
        return None
    teil = werte[-fenster:]
    hoch = max(teil)
    if hoch <= 0:
        return None
    return round((teil[-1] / hoch - 1) * 100, 1) or 0.0


def kennzahlen(k, indizes, cfg=None):
    """Alle Groessen einer Aktie fuer Anzeige und Berichte."""
    cfg = cfg or CFGU
    n = len(k["close"])
    kurs = k["close"][-1] if n else None
    vortag = k["close"][-2] if n >= 2 else None
    roh = red_to_green.rs_rohwert(k["close"]) if n >= int(cfg["historie_tage"]) + 1 else None
    # Etappe 1, Entscheidung 1: junge Titel bekommen den Rohwert aus den
    # vorhandenen Quartalen, gekennzeichnet und NICHT Teil des Bezugs.
    roh_v, quartale_v = red_to_green.rs_rohwert_vorlaeufig(k["close"]) if roh is None else (None, 0)
    dvt = int(cfg["dollarvolumen_tage"])
    dv = (sum(c * v for c, v in zip(k["close"][-dvt:], k["volume"][-dvt:])) / min(n, dvt)) if n else None
    hoch52 = _hoch(k["high"], 252)
    hoch20 = _hoch(k["high"], int(CFG["abendbericht"]["hoch_20_tage"]))
    ad = ad_naeherung(k["close"], k.get("high"), k.get("low"), k["volume"])
    abst = (kurs / max(k["high"][-252:]) - 1) if n >= 60 and kurs else None
    e = {"kurs": round(kurs, 4) if kurs is not None else None,
         "vortag": round(vortag, 4) if vortag is not None else None,
         "pct": round((kurs / vortag - 1) * 100, 2) if (kurs and vortag) else None,
         "tage": n, "roh": roh, "dv50": round(dv) if dv is not None else None,
         "ad_roh": round(ad, 4) if ad is not None else None,
         "kurs_52w_hoch": hoch52, "kurs_20t_hoch": hoch20,
         "abst_52w_hoch_pct": round(abst * 100, 1) if abst is not None else None,
         "letzter_tag": k["daten"][-1] if n else None}
    if roh_v is not None:
        e["roh_vorlaeufig"] = round(roh_v, 6)
        e["rs_quartale"] = quartale_v
    for name, idx in (indizes or {}).items():
        linie = _linie(k, idx)
        kurz = name.lstrip("^").lower()
        e[f"linie_{kurz}_hoch"] = _hoch(linie, 252)
        # Abstand zum Linienhoch in Prozent (Gerhard, 13.09.2026): 'kein Hoch'
        # sagte nicht, wie knapp die Linie darunter steht
        e[f"linie_{kurz}_abst_pct"] = _abstand(linie, 252)
        # Aenderung der Linie ueber eine Woche, fuer die Sortierung der Berichte
        e[f"linie_{kurz}_1w"] = (round((linie[-1] / linie[-6] - 1) * 100, 2)
                                if len(linie) >= 6 and linie[-6] > 0 else None)
    # ETAPPE 2 (Gerhard, 13.09.2026, Entscheidungen 4 und 5): die 16
    # technischen Kennzahlen, nur zur Anzeige. RS-Aenderung und Allzeithoch
    # kommen in bauen() dazu, weil sie Verlauf und Abruf brauchen.
    e["technik"] = kennzahlen_technik.technik(k, (indizes or {}).get(CFG["technik"]["vergleich_index"]))
    return e


def ad_naeherung(closes, highs, lows, volumes, tage=None):
    """A/D als NAEHERUNG (R20, Gerhard), minus 1 bis plus 1. Seit Etappe 2
    (Entscheidung 4, Punkt 4 des Recherche-Papiers) nach Chaikin: ueber 13
    Wochen je Tag die Lage des Schlusskurses in der Tagesspanne, mit dem
    Tagesvolumen gewichtet und durch das Gesamtvolumen geteilt. Bis dahin
    zaehlte nur das Volumen an Plus- gegen Minus-Tagen; die Schlusslage in
    der Spanne nennt IBD in seiner Beschreibung ausdruecklich. Die genaue
    IBD-Formel ist nicht veroeffentlicht, deshalb bleibt die Kennzeichnung
    Naeherung in jeder Zeile. Ohne Hoch und Tief gibt es keinen Wert."""
    return kennzahlen_technik.ad_chaikin(closes, highs or [], lows or [], volumes,
                                         int(tage or CFG["technik"]["ad_tage"]))


def perzentil(rohwerte, eigener):
    """Anteil der Rohwerte, die STRIKT kleiner sind, mal 100, geklemmt auf
    1 bis 99 und gerundet. Gleiche Rohwerte bekommen denselben Wert (die
    Festlegung zum Gleichstand aus Luecke 6). Dieselbe Rechnung wie
    red_to_green.rs_rating_perzentil, dort fuer die Fokusliste."""
    return red_to_green.rs_rating_perzentil(rohwerte, eigener)


def _perzentile(werte):
    """{Rohwert: Perzentil} fuer alle Werte des Bezugs, jeder Wert gegen
    die anderen (ohne sich selbst): Anteil der strikt kleineren mal 100,
    geklemmt auf 1 bis 99, gerundet. Dieselbe Festlegung wie perzentil,
    nur in einem Durchgang fuer tausende Werte."""
    s = sorted(werte)
    n = len(s) - 1
    if n <= 0:
        return {}
    return {v: round(max(1, min(99, bisect.bisect_left(s, v) / n * 100))) for v in set(s)}


def _perzentil_ohne(sortiert, eigener, x):
    """Rang von x gegen die sortierten Rohwerte des Bezugs; steht die Aktie
    selbst im Bezug (eigener = ihr Bezugswert), zaehlt der nicht mit."""
    n = len(sortiert)
    kleinere = bisect.bisect_left(sortiert, x)
    if eigener is not None:
        n -= 1
        if eigener < x:
            kleinere -= 1
    if n <= 0:
        return None
    return round(max(1, min(99, kleinere / n * 100)))


def plausibilitaet(perzentile):
    """Sind die Perzentile 1 bis 99 ungefaehr gleichverteilt? Je Dezil
    sollen zwischen 5 und 15 Prozent der Aktien liegen."""
    werte = [p for p in perzentile if p is not None]
    if len(werte) < 100:
        return {"ok": False, "grund": f"nur {len(werte)} Werte", "dezile": []}
    dezile = []
    for d in range(10):
        lo, hi = d * 10, d * 10 + 9
        anteil = sum(1 for p in werte if lo <= p <= hi + (1 if d == 9 else 0)) / len(werte)
        dezile.append(round(anteil * 100, 1))
    ok = all(5.0 <= a <= 15.0 for a in dezile)
    return {"ok": ok, "dezile": dezile, "anzahl": len(werte),
            "grund": "" if ok else "ein Dezil liegt ausserhalb von 5 bis 15 Prozent"}


def kuenstliche_aktie(tage=None, schritt=0.01):
    """Eine Aktie, die jeden Tag um schritt steigt; 253 Schlusskurse."""
    tage = tage or int(CFGU["historie_tage"]) + 1
    return [100.0 * (1.0 + schritt) ** i for i in range(tage)]


def selbsttest_kuenstlich(rohwerte_universum, schritt=0.01):
    """Regel 4: Der Rohwert der kuenstlichen Aktie muss exakt dem
    vorgerechneten Wert entsprechen, ihr Perzentil im Universum ganz oben
    liegen. Rueckgabe dict mit ok, erwartet, ist, perzentil."""
    closes = kuenstliche_aktie(schritt=schritt)
    ist = red_to_green.rs_rohwert(closes)
    kap = red_to_green.RS_KAPPUNG

    def rendite(t):
        r = (1.0 + schritt) ** t - 1.0
        return min(kap, r) if kap is not None else r
    erwartet = sum(g * rendite(t)
                   for t, g in zip(CFG["lookback"]["rs_quartale"], CFG["lookback"]["rs_gewichte"]))
    rechnung_ok = ist is not None and abs(ist - erwartet) < 1e-9
    p = perzentil(rohwerte_universum, ist) if rohwerte_universum and ist is not None else None
    rang_ok = p is not None and p >= 95
    return {"ok": bool(rechnung_ok and rang_ok), "erwartet": erwartet, "ist": ist,
            "perzentil": p, "rechnung_ok": rechnung_ok, "rang_ok": rang_ok}


def rs_text(rs, cfg=None, quartale=None):
    """Die Anzeige in Meldungen (R4, R6): 'RS 93, sehr gut', 'RS 62' oder
    'RS nicht verfuegbar'. Mit quartale (Etappe 1, Entscheidung 1) die
    Kennzeichnung des vorlaeufigen Werts: 'RS 91 vorläufig, drei Quartale'."""
    cfg = cfg or CFGU
    if rs is None:
        return "RS nicht verfügbar"
    zusatz = ", sehr gut" if rs >= int(cfg["sehr_gut_ab"]) else ""
    if quartale:
        wort = {1: "ein Quartal", 2: "zwei Quartale", 3: "drei Quartale"}.get(
            int(quartale), f"{int(quartale)} Quartale")
        return f"RS {int(rs)} vorläufig, {wort}{zusatz}"
    return f"RS {int(rs)}{zusatz}"


def rs_anzeige(e, cfg=None):
    """Der RS-Text eines Eintrags: der volle Wert, sonst der vorlaeufige
    samt Kennzeichnung, sonst 'RS nicht verfügbar'."""
    e = e or {}
    if e.get("rs") is None and e.get("rs_vorlaeufig") is not None:
        return rs_text(e["rs_vorlaeufig"], cfg, quartale=e.get("rs_quartale"))
    return rs_text(e.get("rs"), cfg)


def linien_text(e):
    """R5: die RS-Linie gegen beide Indizes, kurz. Nur wenn die Werte da sind.
    Seit 13.09.2026 steht statt 'kein Hoch' der Abstand zum Linienhoch in
    Prozent (Gerhard: bitte bauen); eine Ablage ohne das Feld, etwa vor dem
    naechsten Nachtlauf, bekommt den alten Wortlaut."""
    teile = []
    for kurz, name in (("spy", "SPY"), ("qqq", "QQQ")):
        h = e.get(f"linie_{kurz}_hoch")
        if h is None:
            continue
        if h:
            teile.append(f"RS-Linie gegen {name} auf 52-Wochen-Hoch")
            continue
        a = e.get(f"linie_{kurz}_abst_pct")
        if a is None:
            teile.append(f"RS-Linie gegen {name} kein Hoch")
            continue
        z = f"{abs(float(a)):.1f}".replace(".", ",")
        teile.append(f"RS-Linie gegen {name} {z} Prozent unter dem 52-Wochen-Hoch")
    return "; ".join(teile)


# ---------------------------------------------------------------------------
# Bauen
# ---------------------------------------------------------------------------

def _zeitraum_tage(text):
    """Ein Yahoo-Zeitraum in Kalendertagen: '14mo' wird 426, '2y' 730. Fuer
    die Frage, ob die ganze Historie einer Aktie im geladenen Fenster liegt;
    Unbekanntes gilt als 14 Monate."""
    m = re.fullmatch(r"(\d+)\s*(mo|y|wk|d)", str(text or "").strip())
    if not m:
        return 426
    return int(round(int(m.group(1)) * {"mo": 30.44, "y": 365.25, "wk": 7, "d": 1}[m.group(2)]))


def _alte_eintraege(alt):
    """{Symbol: Eintrag der Vornacht} fuer die Kette des Allzeithochs, aus
    allen drei Gruppen; ein Eintrag mit Allzeithoch schlaegt einen ohne."""
    raus = {}
    if not isinstance(alt, dict):
        return raus
    for gruppe in ("ausserhalb", "aktien", "listen"):
        for s, e in (alt.get(gruppe) or {}).items():
            if isinstance(e, dict) and (s not in raus or (e.get("technik") or {}).get("ath") is not None):
                raus[s] = e
    return raus


def _allzeithoch_abruf(paare, alt_je, alt, tag, holen_kurse, holen_allzeit, leise):
    """Entscheidet, fuer welche Symbole heute die ganze Historie geholt wird,
    und holt sie. paare: [(Symbol, Tageskurse)]. Faellig ist der volle Abruf
    fuer alle, wenn der letzte volle Abruf allzeithoch_abruf_tage oder mehr
    zurueckliegt; sonst nur fuer die, deren Kette nicht traegt. Ein voller
    Abruf zaehlt erst als erledigt, wenn er die Mindestabdeckung des
    Universums erreicht, sonst wird er in der naechsten Nacht wiederholt.
    Rueckgabe (frisch {Symbol: (Hoch, Monat)}, Stand fuer den Kopf)."""
    tcfg = CFG["technik"]
    fenster = _zeitraum_tage(CFGU["abruf_zeitraum"])
    toleranz = float(tcfg["allzeithoch_split_toleranz"])
    stand_alt = alt.get("allzeithoch") if isinstance(alt, dict) else None
    voll_am = stand_alt.get("voll_am") if isinstance(stand_alt, dict) else None
    try:
        alter = (date.fromisoformat(tag) - date.fromisoformat(str(voll_am)[:10])).days if voll_am else None
    except ValueError:
        alter = None
    faellig = alter is None or alter >= int(tcfg["allzeithoch_abruf_tage"])
    if faellig:
        brauchen = sorted({s for s, _ in paare})
    else:
        brauchen = sorted({s for s, k in paare
                           if kennzahlen_technik.allzeithoch(k, None, alt_je.get(s), toleranz, fenster)[0] is None})
    abruf = holen_allzeit
    if abruf is None and holen_kurse is None:
        def abruf(symbole):
            return allzeithochs_holen(symbole, leise=leise)
    frisch = {}
    if brauchen and abruf is not None:
        try:
            frisch = abruf(brauchen) or {}
        except Exception as e:  # noqa
            if not leise:
                print(f"  Allzeithoch: Abruf gescheitert ({type(e).__name__}), heute nur die Kette")
    erhalten = sum(1 for s in brauchen if s in frisch)
    voll_ok = bool(faellig and brauchen and erhalten / len(brauchen) >= float(CFGU["mindest_abdeckung"]))
    return frisch, {"voll_am": tag if voll_ok else voll_am,
                    "abruf_heute": "voll" if faellig else ("nachgeholt" if brauchen else "keiner"),
                    "angefragt": len(brauchen), "erhalten": erhalten}


def _allzeithoch_setzen(kz, k, frisch, alt_e, zaehler):
    """Allzeithoch, Datum und Abstand in kz['technik']; zaehlt die Quelle.
    Bei Verdacht auf einen unbereinigten Split bleibt es weg wie alle anderen
    Kennzahlen des Tages; die naechste Nacht holt es frisch."""
    tk = kz.setdefault("technik", {})
    if tk.get("split_verdacht") is not None:
        zaehler["split_verdacht"] = zaehler.get("split_verdacht", 0) + 1
        return
    ath, datum, quelle = kennzahlen_technik.allzeithoch(
        k, frisch, alt_e, float(CFG["technik"]["allzeithoch_split_toleranz"]), _zeitraum_tage(CFGU["abruf_zeitraum"]))
    tk["ath"], tk["ath_datum"] = ath, datum
    kurs = kz.get("kurs")
    tk["ath_abst"] = round((kurs / ath - 1) * 100, 1) if (ath and kurs) else None
    zaehler[quelle or "fehlt"] = zaehler.get(quelle or "fehlt", 0) + 1


def _rs_aenderung_setzen(kz):
    """Punkt 15: RS-Aenderung ueber eine und vier Wochen aus dem Verlauf."""
    tk = kz.get("technik")
    if tk is None:
        return
    for name, tage in CFG["technik"]["rs_aenderung_tage"].items():
        tk[f"rs_{name}"] = kennzahlen_technik.rs_aenderung(kz.get("rs_verlauf"), int(tage))


def _listen_kurse(loaded, listen_ticker, kurse):
    """[(Ticker, Tageskurse, Firma)] der Listen-Aktien: aus dem Nachtscan
    (loaded) oder, bei einem Bau ohne Scan, aus dem Abruf des Universums."""
    raus = []
    for t, wert in (loaded or {}).items():
        try:
            df = wert[0] if isinstance(wert, tuple) else wert
            firma = wert[1] if isinstance(wert, tuple) and len(wert) > 1 else ""
            raus.append((t, aus_scanner_df(df), firma))
        except Exception:  # noqa
            continue
    # ETAPPE 0, PUNKT 2 (Gerhard, 13.09.2026): Ein Bau ohne Nachtscan liess
    # "listen" LEER, bis der naechste Scan lief; die Berichte fanden die
    # Aktien der Wochenliste dann nicht (belegt an drei Laeufen von
    # nachschlag_daten.yml am 13.09.2026, jeweils 0 statt 232 Eintraege).
    # Jetzt kommen sie aus demselben Abruf wie das Universum.
    if loaded is None:
        for t, firma in (listen_ticker or {}).items():
            k = kurse.get(t)
            if k and k.get("close"):
                raus.append((t, k, firma or ""))
    return raus


def _verlauf_fortschreiben(alt_eintrag, tag, rs, hoechstens):
    verlauf = [v for v in (alt_eintrag or {}).get("rs_verlauf", []) if isinstance(v, list) and len(v) == 2 and v[0] != tag]
    verlauf.append([tag, rs])
    return verlauf[-hoechstens:]


def _marktbreite_rechnen(gruppen, kurse, leise=True):
    """ETAPPE 3, ENTSCHEIDUNG 6 (Gerhard, 13.09.2026): die Marktbreite ueber
    alle Stammaktien mit Kursen (dieselben Reihen, aus denen die technischen
    Kennzahlen stammen). Titel mit Verdacht auf einen unbereinigten Split
    zaehlen nicht mit: Ihr Sprung waere ein falscher Steiger oder Faller und
    ein falsches Hoch oder Tief. Ein Fehler hier darf den Bau des RS nie
    verhindern; dann steht nur der Fehler unter "marktbreite"."""
    t0 = time.time()
    try:
        reihen, ohne = [], 0
        for gruppe in gruppen:
            for s, kz in gruppe.items():
                if "technik" not in kz or not kurse.get(s):
                    continue
                if (kz.get("technik") or {}).get("split_verdacht") is not None:
                    ohne += 1
                    continue
                reihen.append(kurse[s])
        mb = marktbreite.breite(reihen)
        if not mb:
            return {"fehler": "keine Kursreihen"}
        mb["ohne_split_verdacht"] = ohne
        mb["dauer_s"] = round(time.time() - t0, 1)
        if not leise:
            print(f"  {marktbreite.breite_zeile(mb)}; {len(reihen)} Reihen, "
                  f"{ohne} wegen Split-Verdacht nicht gezaehlt, {mb['dauer_s']} s")
        return mb
    except Exception as e:  # noqa
        print(f"  Marktbreite: nicht berechenbar ({type(e).__name__}: {e})")
        return {"fehler": f"{type(e).__name__}: {e}"}


def bauen(loaded=None, pfad=DATEI, holen_liste=None, holen_kurse=None, leise=False, alt=None,
          liste_text=None, liste_text_andere=None, jetzt=None, listen_ticker=None, holen_allzeit=None,
          zuordnung_pfad=None, zuordnung=None):
    """Der naechtliche Lauf. loaded: {Ticker: (df, Firma)} des Nachtscans,
    dessen Aktien GEGEN den Bezug gerechnet werden (Luecke 5).

    listen_ticker: {Ticker: Firma} fuer einen Lauf OHNE Nachtscan (etwa
    nachschlag_daten.yml). Dann kommen die Kurse der Listen-Aktien aus
    demselben Abruf wie das Universum; wer nicht im Verzeichnis steht, wird
    eigens mitgeholt. Gilt nur, wenn loaded fehlt: Der Nachtscan bringt
    seine eigenen Kurse mit.

    holen_allzeit(symbolliste) ersetzt den Abruf der ganzen Historie fuer
    das Allzeithoch (Selbsttest); wer holen_kurse ersetzt und holen_allzeit
    nicht, bekommt keinen Abruf, nur Kette und Fenster."""
    cfg = CFGU
    t0 = time.time()
    liste, gruende = nasdaq_liste(text=liste_text, holen=holen_liste, leise=leise)
    liste2, gruende2 = andere_liste(text=liste_text_andere, holen=holen_liste, leise=leise)
    bekannt = {e["symbol"] for e in liste}
    liste = liste + [e for e in liste2 if e["symbol"] not in bekannt]
    # E2, Typ-Teil: nach dem Namensfilter der Verzeichnisse.
    if zuordnung is None and not zuordnung_pfad and os.path.exists(ZUORDNUNG):
        zuordnung_pfad = ZUORDNUNG
    liste, typ_befund = typ_filter(liste, zuordnung_pfad=zuordnung_pfad, zuordnung=zuordnung)
    if not leise:
        print(f"  Typ laut Zuordnungsliste: {typ_befund.get('status')}"
              + (f", {typ_befund['raus']} von {typ_befund['geprueft']} Titeln nicht als Stammaktie gefuehrt, "
                 f"{typ_befund['ohne_eintrag']} ohne Eintrag" if typ_befund.get("status") == "ok"
                 else f" ({typ_befund.get('grund')})"))
    symbole = [e["symbol"] for e in liste]
    boerse_von = {e["symbol"]: e["boerse"] for e in liste}
    indizes_namen = list(cfg["indizes"]) + [cfg["markt_index"]]
    im_verzeichnis = set(symbole) | set(indizes_namen)
    zusatz = ([t for t in (listen_ticker or {}) if t not in im_verzeichnis]
              if loaded is None else [])
    kurse = (holen_kurse or kurse_holen)(symbole + indizes_namen + zusatz, leise=leise) if holen_kurse is None \
        else holen_kurse(symbole + indizes_namen + zusatz)
    indizes = {n: kurse.get(n) for n in cfg["indizes"] if kurse.get(n)}
    markt = kurse.get(cfg["markt_index"])
    min_tage = int(CFG["betrieb"]["min_historie_tage"])
    geladen = [s for s in symbole if s in kurse and len(kurse[s]["close"]) >= min_tage]
    abdeckung = len(geladen) / len(symbole) if symbole else 0.0
    status, grund = "ok", ""
    if abdeckung < float(cfg["mindest_abdeckung"]):
        status, grund = "nicht verfuegbar", (f"Abdeckung {abdeckung * 100:.1f} Prozent unter "
                                             f"{float(cfg['mindest_abdeckung']) * 100:.0f} Prozent")

    # Kennzahlen. "aktien" = ueber den Schwellen (Kennzeichnung R2),
    # "ausserhalb" = darunter oder ohne Historie. Zum BEZUG des Perzentils
    # gehoeren beide Gruppen, sobald ein Rohwert da ist.
    aktien, ausserhalb = {}, {}
    for e in liste:
        s = e["symbol"]
        k = kurse.get(s)
        if not k or len(k["close"]) < min_tage:
            ausserhalb[s] = {"grund": "keine Kurse", "name": e["name"], "boerse": e["boerse"], "roh": None}
            continue
        kz = kennzahlen(k, indizes, cfg)
        kz["name"] = e["name"]
        kz["boerse"] = e["boerse"]
        if kz["kurs"] is None or kz["kurs"] < float(cfg["mindestkurs"]):
            kz["grund"] = f"Kurs unter {float(cfg['mindestkurs']):.0f} Dollar"
            ausserhalb[s] = kz
            continue
        if kz["dv50"] is None or kz["dv50"] < float(cfg["mindest_dollarvolumen"]):
            kz["grund"] = "Tagesumsatz unter 10 Millionen Dollar im 50-Tage-Schnitt"
            ausserhalb[s] = kz
            continue
        if kz["roh"] is None:
            kz["grund"] = f"zu kurze Historie ({kz['tage']} Tage)"
            ausserhalb[s] = kz
            continue
        aktien[s] = kz

    # ETAPPE 2, PUNKT 16 (Gerhard, 13.09.2026): das Allzeithoch fuer das
    # ganze Universum und die Listen-Aktien. Die ganze Historie kommt alle
    # allzeithoch_abruf_tage Tage als Monatskerzen; dazwischen wird das Hoch
    # jede Nacht splitfest fortgeschrieben (kennzahlen_technik.allzeithoch).
    # Wer keine Kette hat (neu im Verzeichnis, Tag der Vornacht fehlt), wird
    # noch in derselben Nacht nachgeholt.
    alt = alt if alt is not None else lies(pfad)
    alt_je = _alte_eintraege(alt)
    tag = (jetzt or date.today()).isoformat()
    listen_kurse = _listen_kurse(loaded, listen_ticker, kurse)
    ath_paare = [(s, kurse[s]) for gruppe in (aktien, ausserhalb) for s, kz in gruppe.items()
                 if "technik" in kz and kurse.get(s)] + [(t, k) for t, k, _ in listen_kurse]
    ath_frisch, ath_stand = _allzeithoch_abruf(ath_paare, alt_je, alt, tag, holen_kurse, holen_allzeit, leise)
    ath_quellen = {}
    for gruppe in (aktien, ausserhalb):
        for s, kz in gruppe.items():
            if "technik" in kz and kurse.get(s):
                _allzeithoch_setzen(kz, kurse[s], ath_frisch.get(s), alt_je.get(s), ath_quellen)

    breite = _marktbreite_rechnen((aktien, ausserhalb), kurse, leise)

    bezug = {s: kz for gruppe in (aktien, ausserhalb) for s, kz in gruppe.items() if kz.get("roh") is not None}
    rohwerte = [kz["roh"] for kz in bezug.values()]
    roh_bezug = {s: kz["roh"] for s, kz in bezug.items()}
    ad_bezug = {s: kz["ad_roh"] for s, kz in bezug.items() if kz.get("ad_roh") is not None}
    probe = selbsttest_kuenstlich(rohwerte) if rohwerte else {"ok": False, "grund": "keine Rohwerte"}
    if status == "ok" and not probe.get("ok"):
        status, grund = "nicht verfuegbar", "Selbsttest der kuenstlichen Aktie fehlgeschlagen"
    handelstag = max((kz["letzter_tag"] for kz in bezug.values() if kz.get("letzter_tag")), default=None)
    alt_aktien = (alt or {}).get("aktien", {}) if isinstance(alt, dict) else {}
    raenge = _perzentile(rohwerte) if status == "ok" else {}
    ad_raenge = _perzentile(list(ad_bezug.values())) if status == "ok" else {}
    for s, kz in bezug.items():
        rs = raenge.get(kz["roh"]) if status == "ok" else None
        kz["rs"] = rs
        kz["ad_rang"] = ad_raenge.get(kz["ad_roh"]) if (status == "ok" and s in ad_bezug) else None
        if s in aktien:
            # Der Verlauf (Aenderung zur Vorwoche in den Berichten) nur fuer
            # die Titel ueber den Schwellen; sonst wuechse die Datei um das
            # Sechsfache, und die Berichte nennen nur diese Titel.
            kz["rs_verlauf"] = _verlauf_fortschreiben(alt_aktien.get(s), handelstag or tag, rs, int(cfg["rs_verlauf_tage"]))
            _rs_aenderung_setzen(kz)
        kz["roh"] = round(kz["roh"], 6)
    plaus = plausibilitaet([kz["rs"] for kz in bezug.values()]) if status == "ok" else {"ok": False, "grund": status, "dezile": []}
    if status == "ok" and not plaus["ok"]:
        # Kein Grund, die Werte zu verwerfen (das waere eine Vermutung), aber
        # ein Befund, der gemeldet wird.
        grund = "Plausibilitaet: " + plaus["grund"]

    sortiert = sorted(rohwerte)
    # ETAPPE 1, ENTSCHEIDUNG 1 (Gerhard, 13.09.2026): Titel mit 64 bis 252
    # Schlusskursen bekommen ein VORLAEUFIGES RS, gerechnet gegen den vollen
    # Bezug; selbst gehen sie nicht in den Bezug ein. Es steht in einem
    # eigenen Feld (rs_vorlaeufig samt rs_quartale), damit nichts, was heute
    # auf "rs" filtert (Fokusliste, Composite), stillschweigend mitfiltert.
    vorlaeufig = 0
    if status == "ok" and sortiert:
        for kz in ausserhalb.values():
            if kz.get("roh") is None and kz.get("roh_vorlaeufig") is not None:
                kz["rs_vorlaeufig"] = _perzentil_ohne(sortiert, None, kz["roh_vorlaeufig"])
                vorlaeufig += 1

    # Listen-Aktien GEGEN den Bezug (Luecke 5)
    listen_ergebnis = {}
    ad_sortiert = sorted(ad_bezug.values())
    for t, k, firma in listen_kurse:
        kz = kennzahlen(k, indizes, cfg)
        # Die Kurse des Nachtscans tragen keine Split-Meldungen; hat der
        # Universumsabruf fuer dasselbe Kuerzel einen unbereinigten Split
        # erkannt, gilt das auch hier.
        uni_tk = ((aktien.get(t) or ausserhalb.get(t) or {}).get("technik") or {})
        if uni_tk.get("split_verdacht") is not None and (uni_tk.get("split_verdacht") != (kz.get("technik") or {}).get("split_verdacht")):
            kz["technik"] = {"split_verdacht": uni_tk["split_verdacht"]}
        _allzeithoch_setzen(kz, k, ath_frisch.get(t), alt_je.get(t), ath_quellen)
        kz["firma"] = firma
        kz["im_universum"] = t in aktien
        kz["im_bezug"] = t in bezug
        kz["boerse"] = boerse_von.get(t)
        if status == "ok" and kz["roh"] is not None and sortiert:
            kz["rs"] = _perzentil_ohne(sortiert, roh_bezug.get(t), kz["roh"])
        else:
            kz["rs"] = None
        if (kz["rs"] is None and status == "ok" and sortiert
                and kz.get("roh_vorlaeufig") is not None):
            kz["rs_vorlaeufig"] = _perzentil_ohne(sortiert, None, kz["roh_vorlaeufig"])
        if kz["roh"] is not None:
            kz["roh"] = round(kz["roh"], 6)
        kz["ad_rang"] = (_perzentil_ohne(ad_sortiert, ad_bezug.get(t), kz["ad_roh"])
                         if (status == "ok" and kz.get("ad_roh") is not None and ad_sortiert) else None)
        alt_l = ((alt or {}).get("listen", {}) if isinstance(alt, dict) else {}).get(t)
        kz["rs_verlauf"] = _verlauf_fortschreiben(alt_l, handelstag or tag, kz["rs"], int(cfg["rs_verlauf_tage"]))
        _rs_aenderung_setzen(kz)
        listen_ergebnis[t] = kz

    markt_info = {}
    if markt and len(markt["close"]) >= 2:
        pct = markt["close"][-1] / markt["close"][-2] - 1
        markt_info = {"symbol": cfg["markt_index"], "schluss": round(markt["close"][-1], 2),
                      "vortag": round(markt["close"][-2], 2), "pct": round(pct * 100, 2),
                      "rot": bool(pct <= -float(cfg["rot_ab_pct"])), "tag": markt["daten"][-1]}
    for n, idx in indizes.items():
        if len(idx["close"]) >= 2:
            markt_info[n.lower() + "_pct"] = round((idx["close"][-1] / idx["close"][-2] - 1) * 100, 2)

    je_boerse = {}
    for e in liste:
        je_boerse.setdefault(e["boerse"], {"verzeichnis": 0, "geladen": 0, "im_bezug": 0, "im_universum": 0})
        je_boerse[e["boerse"]]["verzeichnis"] += 1
    for s in geladen:
        je_boerse[boerse_von[s]]["geladen"] += 1
    for s in bezug:
        je_boerse[boerse_von[s]]["im_bezug"] += 1
    for s in aktien:
        je_boerse[boerse_von[s]]["im_universum"] += 1
    kap = red_to_green.RS_KAPPUNG
    inhalt = {
        "gebaut_am": datetime.now().isoformat(timespec="seconds"),
        "handelstag": handelstag,
        "status": status, "grund": grund,
        "bezug": "US-Markt",
        "hinweis": (f"RS-Werte beziehen sich auf alle {len(bezug)} Stammaktien von Nasdaq, NYSE und "
                    f"NYSE American mit mindestens 253 Schlusskursen"
                    + (f"; jede Einzelrendite ist nach oben bei plus {kap * 100:.0f} Prozent gekappt" if kap else "")
                    + f". 'Im Universum' heisst nur: Kurs ab {float(cfg['mindestkurs']):.0f} Dollar und Tagesumsatz "
                    f"ab {float(cfg['mindest_dollarvolumen']) / 1e6:.0f} Millionen Dollar im 50-Tage-Schnitt, das ist "
                    f"eine Kennzeichnung, keine Vergleichsbasis. Titel mit 64 bis 252 Schlusskursen tragen ein "
                    f"vorläufiges RS aus den vorhandenen Quartalen, gekennzeichnet und nicht Teil des Bezugs. "
                    f"Kurse splitbereinigt, nicht dividendenbereinigt."),
        "universum": {"quelle": cfg["quelle"], "quelle_andere": cfg["quelle_andere"], "typ_filter": typ_befund,
                      "verzeichnis": len(liste),
                      "ausgeschlossen": gruende, "ausgeschlossen_andere": gruende2,
                      "geladen": len(geladen), "abdeckung": round(abdeckung, 4),
                      "mindest_abdeckung": float(cfg["mindest_abdeckung"]),
                      "bezug_anzahl": len(bezug), "je_boerse": je_boerse, "kappung": kap,
                      "vorlaeufig": vorlaeufig,
                      "im_universum": len(aktien), "ausserhalb": len(ausserhalb),
                      "gruende_ausserhalb": _zaehle(v.get("grund") for v in ausserhalb.values()),
                      "dauer_s": round(time.time() - t0)},
        "selbsttest": probe, "plausibilitaet": plaus,
        "markt": markt_info,
        # Etappe 2, Punkt 16: Stand des Allzeithochs; quellen zaehlt je
        # Eintrag, woher der Wert kam (abruf, kette, fenster, fehlt).
        "allzeithoch": {**ath_stand, "quellen": ath_quellen,
                        "abruf_tage": int(CFG["technik"]["allzeithoch_abruf_tage"])},
        # Etappe 3, Entscheidung 6: Marktbreite, reine Anzeige (marktbreite.py).
        "marktbreite": breite,
        "aktien": aktien, "ausserhalb": ausserhalb, "listen": listen_ergebnis,
    }
    _schreiben(pfad, inhalt)
    if not leise:
        print(f"RS-Universum: Bezug {len(bezug)} Stammaktien ("
              + ", ".join(f"{b} {z['im_bezug']}" for b, z in je_boerse.items())
              + f"), {len(aktien)} ueber den Schwellen, {len(ausserhalb)} darunter oder ohne Historie, "
              f"Abdeckung {abdeckung * 100:.1f} Prozent, Status {status}"
              + (f" ({grund})" if grund else "") + f"; Listen {len(listen_ergebnis)}; "
              f"Selbsttest {'ok' if probe.get('ok') else 'FEHL'}; Plausibilitaet "
              f"{'ok' if plaus.get('ok') else 'FEHL'} {plaus.get('dezile')}; {round(time.time() - t0)} s")
    return inhalt


def _zaehle(gruende):
    raus = {}
    for g in gruende:
        raus[g] = raus.get(g, 0) + 1
    return raus


def _schreiben(pfad, inhalt):
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(inhalt, f, ensure_ascii=False, separators=(",", ":"))


def lies(pfad=DATEI):
    try:
        with open(pfad, encoding="utf-8-sig") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def listen_aus_mappe(pfad=MAPPE):
    """Die Aktien der geltenden Wochenliste samt Firma, aus der Mappe des
    letzten Nachtscans (Blatt "Kaufpunkte"). Fuer einen Bau ohne Scan.

    Die Mappe fuehrt genau die Aktien, die der Nachtscan als "listen"
    rechnet (am 13.09.2026 verglichen: 232 gegen 232, alle gleich). Nach
    dem Wochenputz ist sie leer, dann gibt es auch keine Listen-Aktien.
    Ist sie nicht lesbar, bleibt "listen" leer, wie vor dem 13.09.2026."""
    try:
        import pandas as pd
        df = pd.read_excel(pfad, sheet_name="Kaufpunkte")
    except Exception as e:  # noqa
        print(f"  Listen: {pfad} nicht lesbar ({type(e).__name__}), die Listen bleiben leer")
        return {}
    raus = {}
    if "Ticker" not in df.columns:
        return raus
    firmen = df["Firma"] if "Firma" in df.columns else [None] * len(df)
    for t, f in zip(df["Ticker"], firmen):
        s = str(t).strip().upper() if t == t and t is not None else ""
        if not s or s == "NAN":
            continue
        raus.setdefault(s, str(f).strip() if (f == f and f is not None) else "")
    return raus


def eintrag(ticker, daten=None):
    """Der Eintrag einer Aktie fuer Anzeigen: erst die Listen, dann die
    Titel ueber den Schwellen, dann die darunter (die haben seit 12.09.2026
    abends ebenfalls einen RS); None, wenn unbekannt oder ohne Wert."""
    d = daten if daten is not None else lies()
    t = str(ticker or "").upper()
    e = (d.get("listen") or {}).get(t) or (d.get("aktien") or {}).get(t)
    if e:
        return e
    a = (d.get("ausserhalb") or {}).get(t)
    # Auch ein vorlaeufiges RS ist ein Wert fuer Anzeigen (Etappe 1); wer
    # filtert, liest weiter nur "rs".
    return a if (a and (a.get("rs") is not None or a.get("rs_vorlaeufig") is not None)) else None


def anzeige(ticker, daten=None):
    """Eine Zeile fuer Meldungen: RS und RS-Linien (R4, R5, R6). Leer, wenn
    die Aktie nirgends gerechnet ist."""
    d = daten if daten is not None else lies()
    e = eintrag(ticker, d)
    if not e:
        return ""
    if d.get("status") != "ok":
        return "RS nicht verfügbar (" + str(d.get("grund") or d.get("status")) + ")"
    teile = [rs_anzeige(e)]
    lt = linien_text(e)
    if lt:
        teile.append(lt)
    return "; ".join(teile)


# ---------------------------------------------------------------------------
# Selbsttest (ohne Netz)
# ---------------------------------------------------------------------------

def _reihe(seed, tage=300, drift=0.0003, streuung=0.02, start=50.0):
    import random
    r = random.Random(seed)
    closes, highs, lows, vols, daten = [], [], [], [], []
    k = start
    d0 = date(2025, 6, 1)
    i = 0
    while len(closes) < tage:
        dd = date.fromordinal(d0.toordinal() + i)
        i += 1
        if dd.weekday() >= 5:
            continue
        k = max(0.5, k * (1 + drift + r.gauss(0, streuung)))
        closes.append(k); highs.append(k * 1.01); lows.append(k * 0.99)
        vols.append(1_000_000 + r.randint(0, 500_000)); daten.append(dd.isoformat())
    return {"daten": daten, "close": closes, "high": highs, "low": lows, "volume": vols}


def selbsttest() -> int:
    fehler = []

    def p(name, ok, zusatz=""):
        print(f"  {'ok  ' if ok else 'FEHL'} {name}" + (f" — {zusatz}" if zusatz else ""))
        if not ok:
            fehler.append(name)

    print("RS-Universum, Selbsttest (ohne Netz)")
    text = ("Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\n"
            "AAPL|Apple Inc. - Common Stock|Q|N|N|100|N|N\n"
            "QQQ|Invesco QQQ Trust|G|N|N|100|Y|N\n"
            "ZTEST|Test Title|Q|Y|N|100|N|N\n"
            "AACIW|Armada Acquisition Corp. III - Warrant|G|N|N|100|N|N\n"
            "AACI|Armada Acquisition Corp. III - Class A Ordinary Share|G|N|N|100|N|N\n"
            "AACG|ATA Creativity Global - American Depositary Shares|S|N|N|100|N|N\n"
            "BRK.B|Berkshire Class B - Common Stock|Q|N|N|100|N|N\n"
            "ARCC|Ares Capital Corporation - Closed End Fund|Q|N|N|100|N|N\n"
            "FUNDA|Beispiel Income Fund Inc. - Common Stock|Q|N|N|100|N|N\n"
            "FUNDX|Fundamental Systems Inc. - Common Stock|Q|N|N|100|N|N\n"
            "File Creation Time: 0911202621:31|||||||\n")
    liste, gruende = nasdaq_liste(text=text)
    p("Verzeichnis: ETF, Test-Titel, Optionsschein und SPAC fallen, ADR und Stammaktie bleiben",
      [e["symbol"] for e in liste] == ["AAPL", "AACG", "BRK.B", "FUNDX"] and gruende.get("ETF") == 1
      and gruende.get("Test-Titel") == 1, f"{[e['symbol'] for e in liste]} {gruende}")
    p("E2, Namensteil: Closed End Fund, Fund und Acquisition fallen; Fundamental bleibt",
      gruende.get("Fondsvehikel oder Mantel laut Name (Entscheidung 2)") == 3
      and "FUNDX" in [e["symbol"] for e in liste] and "ARCC" not in [e["symbol"] for e in liste]
      and "FUNDA" not in [e["symbol"] for e in liste], f"{[e['symbol'] for e in liste]} {gruende}")
    p("Yahoo-Schreibweise: BRK.B wird BRK-B", yahoo_symbol("BRK.B") == "BRK-B")
    text_andere = ("ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol\n"
                   "IBM|International Business Machines Corporation Common Stock|N|IBM|N|100|N|IBM\n"
                   "BRK.B|Berkshire Hathaway Inc. Class B|N|BRK.B|N|100|N|BRK=B\n"
                   "SPY|SPDR S&P 500 ETF Trust|P|SPY|Y|100|N|SPY\n"
                   "ETFX|Irgendein Fonds|N|ETFX|Y|100|N|ETFX\n"
                   "AHT$D|Ashford Hospitality Trust Inc 8.45% Series D Cumulative Preferred Stock|N|AHTpD|N|100|N|AHT-D\n"
                   "ACHR.W|Archer Aviation Inc. Warrants|N|ACHR.WS|N|100|N|ACHR+\n"
                   "BE|Bloom Energy Corporation Class A Common Stock|N|BE|N|100|N|BE\n"
                   "LODE|Comstock Inc. Common Stock|A|LODE|N|100|N|LODE\n"
                   "ZTST|Test Title|N|ZTST|N|100|Y|ZTST\n"
                   "CBOE|Cboe Global Markets, Inc. Common Stock|Z|CBOE|N|100|N|CBOE\n"
                   "MLPB|ETRACS Alerian MLP Index ETN|Z|MLPB|N|100|N|MLPB\n"
                   "BAR|GraniteShares Gold Trust|Z|BAR|Y|100|N|BAR\n"
                   "ESRT.U|Empire State Realty OP Units|Z|ESRT.U|N|100|N|ESRT=U\n"
                   "File Creation Time: 0911202621:31|||||||\n")
    liste2, gruende2 = andere_liste(text=text_andere)
    p("NYSE-Verzeichnis: Stammaktien von NYSE und NYSE American bleiben, Arca, ETF, Vorzug, Optionsschein, Test fallen",
      [(e["symbol"], e["boerse"]) for e in liste2][:4] == [("IBM", "NYSE"), ("BRK.B", "NYSE"), ("BE", "NYSE"), ("LODE", "NYSE American")]
      and gruende2.get("andere Boerse") == 1 and gruende2.get("ETF") == 2 and gruende2.get("Test-Titel") == 1
      and gruende2.get("kein Stammtitel (Symbol: Vorzug, Optionsschein, Einheit, Recht)") == 3,
      f"{[e['symbol'] for e in liste2]} {gruende2}")
    p("E3: von der Cboe bleibt Cboe Global Markets, ETN, Goldtrust und Einheiten fallen (Entscheidung 3, Antwort N2)",
      [(e["symbol"], e["boerse"]) for e in liste2 if e["boerse"] == "Cboe"] == [("CBOE", "Cboe")],
      f"{[(e['symbol'], e['boerse']) for e in liste2]}")
    # E2, Typ-Teil (Gerhard, Entscheidung 2, Antwort N1)
    zu_probe = {"AAPL": {"typ": "Common Stock"}, "BRK.B": {"typ": "FUND"}, "BE": {"typ": "Preferred Stock"}}
    bleibt_t, bf_t = typ_filter([{"symbol": s, "name": s} for s in ("AAPL", "BRK.B", "BE", "NEUX")],
                                zuordnung=zu_probe, befund={"stand": "2026-09-21", "eintraege": 3})
    p("E2, Typteil: was die Zuordnungsliste nicht als Stammaktie fuehrt, faellt; wer fehlt, bleibt",
      [e["symbol"] for e in bleibt_t] == ["AAPL", "NEUX"] and bf_t["raus"] == 2 and bf_t["ohne_eintrag"] == 1
      and bf_t["geprueft"] == 4 and bf_t["stand"] == "2026-09-21", f"{[e['symbol'] for e in bleibt_t]} {bf_t}")
    bleibt_o, bf_o = typ_filter([{"symbol": "AAPL", "name": "AAPL"}], zuordnung=None,
                                befund={"grund": "die Liste liegt nicht vor"})
    p("E2, Typteil: ohne Zuordnungsliste bleibt die Liste, der Befund nennt den Grund",
      [e["symbol"] for e in bleibt_o] == ["AAPL"] and bf_o["status"] == "nicht verfuegbar"
      and bf_o["grund"] == "die Liste liegt nicht vor", str(bf_o))
    p("E2, Typteil: der Befund nennt nur Zahlen, nie Kuerzel oder Typen",
      not any(isinstance(v, (list, dict)) for v in bf_t.values())
      and all(k in ("status", "stand", "eintraege", "geprueft", "raus", "ohne_eintrag") for k in bf_t), str(bf_t))
    flach = [100.0] * 253
    hoch = flach[:-1] + [400.0]
    mittel = flach[:-1] + [130.0]
    p("Kappung: jede Einzelrendite zaehlt hoechstens plus 50 Prozent, darunter bleibt sie wie sie ist",
      red_to_green.RS_KAPPUNG == 0.5 and abs(red_to_green.rs_rohwert(hoch) - 0.5) < 1e-12
      and abs(red_to_green.rs_rohwert(mittel) - 0.3) < 1e-12,
      f"{red_to_green.rs_rohwert(hoch)} {red_to_green.rs_rohwert(mittel)}")

    p("Gleichstand: gleiche Rohwerte bekommen denselben Rang, der Anteil zaehlt nur strikt kleinere",
      perzentil([0.1, 0.2, 0.2, 0.3], 0.2) == perzentil([0.1, 0.2, 0.2, 0.3], 0.2) == 25
      and perzentil([0.1, 0.2, 0.3], 0.3) == 67 and perzentil([0.5, 0.6], 0.1) == 1)
    probe = selbsttest_kuenstlich([0.1, 0.2, 0.3])
    p("Kuenstliche Aktie: Rohwert exakt vorgerechnet (mit Kappung 0,5), Perzentil oben",
      probe["ok"] and abs(probe["ist"] - probe["erwartet"]) < 1e-9 and probe["perzentil"] == 99
      and abs(probe["erwartet"] - 0.5) < 1e-12,
      f"{probe['ist']:.6f} gegen {probe['erwartet']:.6f}, Perzentil {probe['perzentil']}")
    p("Kuenstliche Aktie faellt durch, wenn das Universum staerker ist",
      not selbsttest_kuenstlich([5.0, 6.0, 7.0])["ok"])
    p("Plausibilitaet: Gleichverteilung ok, Haeufung nicht",
      plausibilitaet(list(range(1, 100)) * 2)["ok"] and not plausibilitaet([50] * 200)["ok"])
    p("Text: sehr gut ab 85, schlicht darunter, nicht verfuegbar ohne Wert",
      rs_text(93) == "RS 93, sehr gut" and rs_text(84) == "RS 84" and rs_text(None) == "RS nicht verfügbar")

    # Kennzahlen an einer steigenden Reihe
    k = kuenstliche_aktie(300)
    kd = {"daten": [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(300)][-300:], "close": k,
          "high": [x * 1.001 for x in k], "low": [x * 0.999 for x in k], "volume": [1e6] * 300}
    idx = {"daten": kd["daten"], "close": [100.0] * 300}
    kz = kennzahlen(kd, {"SPY": idx})
    p("Kennzahlen: 52-Wochen-Hoch, 20-Tage-Hoch, RS-Linie auf Hoch, Dollarvolumen",
      kz["kurs_52w_hoch"] is True and kz["kurs_20t_hoch"] is True and kz["linie_spy_hoch"] is True
      and kz["dv50"] > 0 and kz["roh"] is not None and kz["tage"] == 300, kz)
    kz3 = kennzahlen({**kd, "close": k[:250] + [k[249] * 0.9] * 50}, {"SPY": idx})
    kz4 = kennzahlen({"daten": kd["daten"][:100], "close": k[:100], "high": kd["high"][:100],
                      "low": kd["low"][:100], "volume": [1e6] * 100}, {"SPY": idx})
    p("RS-Linie: Abstand null auf dem Hoch, minus 10 Prozent nach einem Rueckgang, kein Wert bei kurzer Reihe",
      kz["linie_spy_abst_pct"] == 0.0 and kz3["linie_spy_abst_pct"] == -10.0 and kz3["linie_spy_hoch"] is False
      and kz4["linie_spy_abst_pct"] is None and kz4["linie_spy_hoch"] is None,
      f"{kz['linie_spy_abst_pct']} {kz3['linie_spy_abst_pct']} {kz4['linie_spy_abst_pct']}")
    p("Linientext: Hoch, Abstand mit Beistrich, alter Wortlaut ohne Feld, leer ohne Wert",
      linien_text({"linie_spy_hoch": True, "linie_qqq_hoch": False, "linie_qqq_abst_pct": -1.5})
      == "RS-Linie gegen SPY auf 52-Wochen-Hoch; RS-Linie gegen QQQ 1,5 Prozent unter dem 52-Wochen-Hoch"
      and linien_text({"linie_spy_hoch": False}) == "RS-Linie gegen SPY kein Hoch"
      and linien_text({"linie_spy_hoch": False, "linie_spy_abst_pct": 0.0}) == "RS-Linie gegen SPY 0,0 Prozent unter dem 52-Wochen-Hoch"
      and linien_text({}) == "",
      linien_text({"linie_spy_hoch": True, "linie_qqq_hoch": False, "linie_qqq_abst_pct": -1.5}))
    kurz = {"daten": kd["daten"][:100], "close": k[:100], "high": kd["high"][:100], "low": kd["low"][:100], "volume": [1e6] * 100}
    kz2 = kennzahlen(kurz, {})
    p("Zu kurze Historie: kein Rohwert, kein 52-Wochen-Hoch", kz2["roh"] is None and kz2["kurs_52w_hoch"] is None)
    p("A/D-Naeherung nach Chaikin (Etappe 2): Schluss am Hoch plus 1, am Tief minus 1, in der Mitte null, "
      "ohne Hoch und Tief oder zu kurz kein Wert",
      ad_naeherung([11.0] * 70, [11.0] * 70, [10.0] * 70, [100.0] * 70) == 1.0
      and ad_naeherung([10.0] * 70, [11.0] * 70, [10.0] * 70, [100.0] * 70) == -1.0
      and abs(ad_naeherung([10.5] * 70, [11.0] * 70, [10.0] * 70, [100.0] * 70)) < 1e-12
      and ad_naeherung([10.5] * 70, None, None, [100.0] * 70) is None
      and ad_naeherung([1.0] * 10, [1.0] * 10, [1.0] * 10, [1.0] * 10) is None)
    p("Zeitraum in Kalendertagen: 14 Monate 426, zwei Jahre 730, Unbekanntes 426",
      _zeitraum_tage("14mo") == 426 and _zeitraum_tage("2y") == 730 and _zeitraum_tage("max") == 426)

    # Ganzer Lauf mit synthetischem Universum: 240 Nasdaq- und 60 NYSE-Titel
    import tempfile

    def nam(vorne, i):
        return f"{vorne}{chr(65 + i // 26)}{chr(65 + i % 26)}"
    zeilen = ["Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares"]
    reihen = {}
    for i in range(240):
        s = nam("S", i)
        zeilen.append(f"{s}|Firma {i} - Common Stock|Q|N|N|100|N|N")
        reihen[s] = _reihe(i, drift=0.0002 + (i % 12) * 0.0002)
    zeilen.append("BILLIG|Billig - Common Stock|Q|N|N|100|N|N")
    reihen["BILLIG"] = _reihe(999, start=2.0)
    zeilen.append("JUNG|Jung - Common Stock|Q|N|N|100|N|N")
    reihen["JUNG"] = _reihe(998, tage=120)
    zeilen.append("FEHLT|Fehlt - Common Stock|Q|N|N|100|N|N")
    for n in ("SPY", "QQQ", "^IXIC"):
        reihen[n] = _reihe(1000 + len(n), drift=0.0003)
    text2 = "\n".join(zeilen) + "\n"
    zeilen3 = ["ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol"]
    for i in range(60):
        s = nam("N", i)
        zeilen3.append(f"{s}|Firma NYSE {i} Common Stock|{'A' if i % 10 == 0 else 'N'}|{s}|N|100|N|{s}")
        reihen[s] = _reihe(500 + i, drift=0.0002 + (i % 12) * 0.0002)
    text3 = "\n".join(zeilen3) + "\n"
    saf = nam("S", 5)

    def holen(symbole):
        return {s: reihen[s] for s in symbole if s in reihen}

    import pandas as pd
    df_liste = pd.DataFrame({"datetime": reihen[saf]["daten"], "open": reihen[saf]["close"],
                             "high": reihen[saf]["high"], "low": reihen[saf]["low"],
                             "close": reihen[saf]["close"], "volume": reihen[saf]["volume"]})
    df_fremd = pd.DataFrame({"datetime": reihen["BILLIG"]["daten"], "open": reihen["BILLIG"]["close"],
                             "high": reihen["BILLIG"]["high"], "low": reihen["BILLIG"]["low"],
                             "close": reihen["BILLIG"]["close"], "volume": reihen["BILLIG"]["volume"]})
    pfad = os.path.join(tempfile.mkdtemp(), "rs.json")
    inhalt = bauen(loaded={saf: (df_liste, "Firma 5"), "BILLIG": (df_fremd, "Billig")}, pfad=pfad,
                   holen_kurse=holen, liste_text=text2, liste_text_andere=text3, leise=True, alt={},
                   jetzt=date(2026, 9, 12))
    u = inhalt["universum"]
    p("Lauf: 300 Titel ueber den Schwellen (240 Nasdaq, 60 NYSE); Billig, Jung und Fehlt darunter; "
      "Abdeckung zaehlt Fehlt als nicht geladen",
      inhalt["status"] == "ok" and u["im_universum"] == 300 and "BILLIG" in inhalt["ausserhalb"]
      and "JUNG" in inhalt["ausserhalb"] and inhalt["ausserhalb"]["FEHLT"]["grund"] == "keine Kurse"
      and abs(u["abdeckung"] - round(302 / 303, 4)) < 1e-9
      and u["je_boerse"]["NYSE"]["im_universum"] == 54 and u["je_boerse"]["NYSE American"]["im_universum"] == 6,
      f"{inhalt['status']} {u}")
    p("Bezug: Titel unter den Schwellen zaehlen mit und bekommen einen RS, ohne Historie nicht",
      u["bezug_anzahl"] == 301 and inhalt["ausserhalb"]["BILLIG"]["rs"] is not None
      and inhalt["ausserhalb"]["JUNG"].get("rs") is None and u["kappung"] == 0.5,
      f"{u['bezug_anzahl']} {inhalt['ausserhalb']['BILLIG'].get('rs')}")
    rs_werte = [a["rs"] for a in inhalt["aktien"].values()]
    p("A/D-Rang je Aktie im Universum und fuer die Listenaktien vorhanden",
      all(1 <= a["ad_rang"] <= 99 for a in inhalt["aktien"].values())
      and inhalt["listen"][saf]["ad_rang"] is not None and inhalt["listen"]["BILLIG"]["ad_rang"] is not None)
    p("Perzentile liegen zwischen 1 und 99, Plausibilitaet ok, Selbsttest ok",
      min(rs_werte) >= 1 and max(rs_werte) <= 99 and inhalt["plausibilitaet"]["ok"] and inhalt["selbsttest"]["ok"],
      f"{inhalt['plausibilitaet']} {inhalt['selbsttest']['perzentil']}")
    p("Rang ohne sich selbst: die beste Aktie des Bezugs bekommt 99, die schlechteste 1",
      max(rs_werte) == 99 and min(a["rs"] for a in inhalt["ausserhalb"].values() if a.get("rs") is not None) >= 1)
    l = inhalt["listen"]
    p("Listen-Aktie im Bezug: eigener Wert ohne sich selbst gerechnet, gleich dem Bezugswert",
      l[saf]["im_universum"] is True and l[saf]["im_bezug"] is True and l[saf]["rs"] is not None
      and l[saf]["rs"] == inhalt["aktien"][saf]["rs"] and l[saf]["boerse"] == "Nasdaq",
      f"{l[saf]['rs']} gegen {inhalt['aktien'][saf]['rs']}")
    p("Listen-Aktie unter der Schwelle bekommt einen Wert gegen den Bezug, gleich ihrem Wert unter 'ausserhalb' (Luecke 5)",
      l["BILLIG"]["im_universum"] is False and l["BILLIG"]["im_bezug"] is True and l["BILLIG"]["rs"] is not None
      and l["BILLIG"]["rs"] == inhalt["ausserhalb"]["BILLIG"]["rs"], l["BILLIG"].get("rs"))
    p("Eintrag fuer Anzeigen findet auch Titel unter den Schwellen und junge mit vorlaeufigem RS, aber keine ohne Wert",
      eintrag("BILLIG", inhalt) is not None and eintrag("JUNG", inhalt) is not None
      and eintrag("FEHLT", inhalt) is None)
    # ETAPPE 1, ENTSCHEIDUNG 1: vorlaeufiges RS fuer junge Titel
    jung = inhalt["ausserhalb"]["JUNG"]
    bezug_roh = sorted(a["roh"] for g in ("aktien", "ausserhalb") for a in inhalt[g].values()
                       if a.get("roh") is not None)
    p("Vorlaeufiges RS: junger Titel mit 120 Kurstagen, ein Quartal, gegen den vollen Bezug, nicht selbst im Bezug",
      jung.get("rs") is None and jung.get("rs_quartale") == 1 and jung.get("rs_vorlaeufig") is not None
      and jung["rs_vorlaeufig"] == _perzentil_ohne(bezug_roh, None, jung["roh_vorlaeufig"])
      and u["bezug_anzahl"] == 301 and u["vorlaeufig"] == 1, jung.get("rs_vorlaeufig"))
    p("Vorlaeufiges RS: die Anzeige kennzeichnet den Wert",
      anzeige("JUNG", inhalt).startswith(f"RS {jung['rs_vorlaeufig']} vorläufig, ein Quartal"),
      anzeige("JUNG", inhalt))
    p("Vorlaeufiges RS: Fokusliste und Composite lesen es nicht, weil sie auf 'rs' schauen",
      eintrag("JUNG", inhalt).get("rs") is None)
    p("Markt: Nasdaq mit Tagesveraenderung und Rot-Kennzeichen",
      "rot" in inhalt["markt"] and "spy_pct" in inhalt["markt"])
    p("Anzeige aus der Datei: RS und Linien", anzeige(saf, lies(pfad)).startswith("RS "))
    p("Verlauf wird fortgeschrieben, nur fuer Titel ueber den Schwellen",
      len(l[saf]["rs_verlauf"]) == 1 and "rs_verlauf" in inhalt["aktien"][saf]
      and "rs_verlauf" not in inhalt["ausserhalb"]["BILLIG"])
    inhalt2 = bauen(loaded={}, pfad=pfad, holen_kurse=holen, liste_text=text2, liste_text_andere=text3, leise=True,
                    alt=lies(pfad), jetzt=date(2026, 9, 13))
    p("Zweiter Lauf am selben Handelstag ersetzt den Tageswert statt ihn zu verdoppeln",
      len(inhalt2["aktien"][saf]["rs_verlauf"]) == 1)

    # ETAPPE 2 (Gerhard, 13.09.2026, Entscheidungen 4 und 5): technische
    # Kennzahlen, RS-Aenderung und Allzeithoch
    tk = inhalt["aktien"][saf]["technik"]
    p("Technik: jede Aktie mit Kursen traegt die Kennzahlen, auch unter den Schwellen und in den Listen; "
      "ohne Kurse keine",
      all("adr20" in a.get("technik", {}) and "rsi14" in a["technik"] for a in inhalt["aktien"].values())
      and "technik" in inhalt["ausserhalb"]["BILLIG"] and "technik" in l[saf]
      and "technik" not in inhalt["ausserhalb"]["FEHLT"]
      and tk["adr20"] is not None and tk["beta"] is not None and tk["mrs"] is not None and tk["stufe"] is not None,
      tk)
    mb = inhalt["marktbreite"]
    p("Marktbreite (Etappe 3): ueber alle Titel mit Kursen am Handelstag des Universums; Steiger, Faller und "
      "Unveraenderte ergeben die Titel des Tages",
      mb.get("handelstag") == inhalt["handelstag"] and mb.get("reihen") == 302 and mb.get("aktien_heute", 0) > 0
      and mb["steiger"] + mb["faller"] + mb["unveraendert"] == mb["aktien_heute"]
      and mb.get("ohne_split_verdacht") == 0 and mb.get("mcclellan") is not None and "stockbee" in mb, mb)
    k_a, k_b = reihen[nam("S", 1)], reihen[nam("S", 2)]
    mb_split = _marktbreite_rechnen(({"A": {"technik": {"adr20": 1.0}}, "B": {"technik": {"split_verdacht": 30.0}},
                                      "C": {"grund": "keine Kurse"}},), {"A": k_a, "B": k_b})
    p("Marktbreite: ein Titel mit Split-Verdacht zaehlt nicht mit, ein Titel ohne Kennzahlen ebenso wenig",
      mb_split.get("reihen") == 1 and mb_split.get("ohne_split_verdacht") == 1, mb_split)
    p("Marktbreite: ein Fehler verhindert den Bau nicht, er steht nur unter marktbreite",
      "fehler" in _marktbreite_rechnen(({"A": {"technik": {}}},), {"A": {"close": [1.0, 2.0]}}))
    p("Technik: ohne Abruf der ganzen Historie gibt es das Allzeithoch nur fuer junge Titel mit ganzer Historie",
      tk["ath"] is None and inhalt["ausserhalb"]["JUNG"]["technik"]["ath"] == round(max(reihen["JUNG"]["high"]), 2)
      and inhalt["allzeithoch"]["abruf_heute"] == "voll" and inhalt["allzeithoch"]["erhalten"] == 0
      and inhalt["allzeithoch"]["voll_am"] is None and inhalt["allzeithoch"]["quellen"].get("fenster") == 1,
      inhalt["allzeithoch"])
    reihen_ath = dict(reihen)
    ath_abgefragt = []

    def holen_reihen(symbole):
        return {s: reihen_ath[s] for s in symbole if s in reihen_ath}

    def holen_ath(symbole):
        ath_abgefragt.append(sorted(symbole))
        return {s: (max(reihen_ath[s]["high"]) * 1.5, "2020-01") for s in symbole if s in reihen_ath}
    pfad_ath = os.path.join(tempfile.mkdtemp(), "rs_ath.json")
    i1 = bauen(loaded={saf: (df_liste, "Firma 5")}, pfad=pfad_ath, holen_kurse=holen_reihen, holen_allzeit=holen_ath,
               liste_text=text2, liste_text_andere=text3, leise=True, alt={}, jetzt=date(2026, 9, 12))
    e1 = i1["aktien"][saf]["technik"]
    p("Allzeithoch, erster Lauf: voller Abruf fuer alle mit Kursen samt Listen, Wert mit Monat, Stand gemerkt",
      len(ath_abgefragt) == 1 and i1["allzeithoch"]["voll_am"] == "2026-09-12"
      and i1["allzeithoch"]["abruf_heute"] == "voll" and "FEHLT" not in ath_abgefragt[0]
      and e1["ath"] == round(max(reihen[saf]["high"]) * 1.5, 2) and e1["ath_datum"] == "2020-01"
      and i1["listen"][saf]["technik"]["ath"] == e1["ath"]
      and e1["ath_abst"] == round((i1["aktien"][saf]["kurs"] / e1["ath"] - 1) * 100, 1),
      f"{i1['allzeithoch']} {e1.get('ath')}")
    # Zweiter Lauf am Folgetag: ein neuer Titel im Verzeichnis und ein Split 2 zu 1
    gespalten = nam("S", 7)
    alt_split = reihen_ath[gespalten]
    reihen_ath[gespalten] = {**alt_split, "close": [x / 2 for x in alt_split["close"]],
                             "high": [x / 2 for x in alt_split["high"]], "low": [x / 2 for x in alt_split["low"]]}
    reihen_ath["NEUX"] = _reihe(555)
    # Yahoo rechnet einen Split erst einen Tag spaeter ein: Die Tage vor dem
    # letzten Tag der Vornacht sind halbiert, der letzte Tag selbst nicht.
    spaet = reihen_ath["SAI"]
    halb_bis = len(spaet["close"]) - 1
    reihen_ath["SAI"] = {**spaet, "close": [x / 2 for x in spaet["close"][:halb_bis]] + spaet["close"][halb_bis:],
                         "high": [x / 2 for x in spaet["high"][:halb_bis]] + spaet["high"][halb_bis:],
                         "low": [x / 2 for x in spaet["low"][:halb_bis]] + spaet["low"][halb_bis:]}
    text2_neu = text2 + "NEUX|Neu - Common Stock|Q|N|N|100|N|N\n"
    i2 = bauen(loaded={saf: (df_liste, "Firma 5")}, pfad=pfad_ath, holen_kurse=holen_reihen, holen_allzeit=holen_ath,
               liste_text=text2_neu, liste_text_andere=text3, leise=True, alt=lies(pfad_ath), jetzt=date(2026, 9, 13))
    vor = eintrag(gespalten, i1)["technik"]["ath"]
    nach = eintrag(gespalten, i2)["technik"]["ath"]
    p("Allzeithoch, Folgetag: kein voller Abruf, nur der neue Titel ohne Kette wird nachgeholt",
      len(ath_abgefragt) == 2 and ath_abgefragt[1] == ["NEUX", "SAI"] and i2["allzeithoch"]["abruf_heute"] == "nachgeholt"
      and i2["allzeithoch"]["voll_am"] == "2026-09-12" and eintrag("NEUX", i2)["technik"]["ath"] is not None
      and i2["aktien"][saf]["technik"]["ath"] == e1["ath"], f"{ath_abgefragt[-1:]} {i2['allzeithoch']}")
    p("Allzeithoch, Folgetag: nach einem Split 2 zu 1 halbiert die Kette das gespeicherte Hoch",
      vor is not None and nach is not None and abs(nach - vor / 2) <= 0.011, f"{vor} {nach}")
    reihen_ath[gespalten] = alt_split
    reihen_ath["SAI"] = spaet

    def holen_halb(symbole):
        ath_abgefragt.append(sorted(symbole))
        return {s: (max(reihen_ath[s]["high"]) * 1.5, "2020-01") for s in list(symbole)[: len(symbole) // 2]}
    i3 = bauen(loaded={saf: (df_liste, "Firma 5")}, pfad=pfad_ath, holen_kurse=holen_reihen, holen_allzeit=holen_halb,
               liste_text=text2_neu, liste_text_andere=text3, leise=True, alt=lies(pfad_ath), jetzt=date(2026, 9, 19))
    p("Allzeithoch, voller Abruf nach sieben Tagen unter der Mindestabdeckung: Stand bleibt, die Kette traegt weiter",
      i3["allzeithoch"]["abruf_heute"] == "voll" and i3["allzeithoch"]["voll_am"] == "2026-09-12"
      and i3["allzeithoch"]["erhalten"] < i3["allzeithoch"]["angefragt"]
      and all(a["technik"]["ath"] is not None for a in i3["aktien"].values()), i3["allzeithoch"])
    # RS-Aenderung aus dem Verlauf der Vornaechte
    alt_v = lies(pfad_ath)
    ht = date.fromisoformat(inhalt["handelstag"])
    vor13 = date.fromordinal(ht.toordinal() - 13).isoformat()
    vor30 = date.fromordinal(ht.toordinal() - 30).isoformat()
    alt_v["aktien"][saf]["rs_verlauf"] = [[vor30, 40], [vor13, 50]]
    alt_v["listen"][saf]["rs_verlauf"] = [[vor30, 40], [vor13, 50]]
    i4 = bauen(loaded={saf: (df_liste, "Firma 5")}, pfad=pfad_ath, holen_kurse=holen_reihen, liste_text=text2,
               liste_text_andere=text3, leise=True, alt=alt_v, jetzt=date(2026, 9, 14))
    rs4 = i4["aktien"][saf]["rs"]
    p("RS-Aenderung: eine Woche gegen den Wert von vor 13 Tagen, vier Wochen gegen den von vor 30 Tagen, "
      "fuer Universum und Listen",
      i4["aktien"][saf]["technik"]["rs_1w"] == rs4 - 50 and i4["aktien"][saf]["technik"]["rs_4w"] == rs4 - 40
      and i4["listen"][saf]["technik"]["rs_4w"] == i4["listen"][saf]["rs"] - 40
      and i4["ausserhalb"]["BILLIG"]["technik"].get("rs_1w") is None,
      f"{rs4} {i4['aktien'][saf]['technik'].get('rs_1w')} {i4['aktien'][saf]['technik'].get('rs_4w')}")
    p("Allzeithoch: Split nur im Vortag eingerechnet, die Kette traegt nicht und der Titel wird nachgeholt",
      "SAI" in ath_abgefragt[1], ath_abgefragt[1])
    p("Eroeffnung: der Kursrahmen des Nachtscans bringt sie mit",
      aus_scanner_df(df_liste)["open"] == [float(x) for x in reihen[saf]["close"]])

    # ETAPPE 0, PUNKT 2 (13.09.2026): Bau OHNE Nachtscan, die Listen kommen
    # aus der Mappe und ihre Kurse aus demselben Abruf wie das Universum.
    reihen["ADRX"] = _reihe(777, drift=0.0004)
    abgerufen = []

    def holen_merken(symbole):
        abgerufen.extend(symbole)
        return {s: reihen[s] for s in symbole if s in reihen}
    inhalt4 = bauen(pfad=pfad, holen_kurse=holen_merken, liste_text=text2, liste_text_andere=text3, leise=True,
                    alt={}, jetzt=date(2026, 9, 13),
                    listen_ticker={saf: "Firma 5", "BILLIG": "Billig", "ADRX": "Fremd ADR", "FEHLT": "Fehlt"})
    l4 = inhalt4["listen"]
    p("Bau ohne Nachtscan: Listen aus der Mappe, Kurse aus dem Universumsabruf, gleiche Werte wie im Universum",
      set(l4) == {saf, "BILLIG", "ADRX"} and l4[saf]["rs"] == inhalt4["aktien"][saf]["rs"]
      and l4[saf]["firma"] == "Firma 5" and l4["BILLIG"]["rs"] == inhalt4["ausserhalb"]["BILLIG"]["rs"],
      sorted(l4))
    p("Bau ohne Nachtscan: eine Listen-Aktie ausserhalb des Verzeichnisses wird eigens mitgeholt und gegen den Bezug gerechnet",
      abgerufen.count("ADRX") == 1 and l4["ADRX"]["im_universum"] is False and l4["ADRX"]["im_bezug"] is False
      and l4["ADRX"]["rs"] is not None and l4["ADRX"]["boerse"] is None, l4.get("ADRX", {}).get("rs"))
    inhalt5 = bauen(loaded={}, pfad=pfad, holen_kurse=holen_merken, liste_text=text2, liste_text_andere=text3,
                    leise=True, alt={}, listen_ticker={saf: "Firma 5"})
    p("Nachtscan ohne Listen (loaded leer) bleibt ohne Listen, auch wenn eine Mappe da waere",
      inhalt5["listen"] == {})
    mappe = os.path.join(tempfile.mkdtemp(), "kp.xlsx")
    pd.DataFrame({"Ticker": ["aaa", "BBB", None, "AAA"], "Firma": ["Alpha", None, "Leer", "Doppelt"]}).to_excel(
        mappe, sheet_name="Kaufpunkte", index=False)
    aus_mappe = listen_aus_mappe(mappe)
    p("Mappe: Ticker gross, ohne Leerzeilen und Doppel, Firma dabei; fehlende Mappe ergibt keine Listen",
      aus_mappe == {"AAA": "Alpha", "BBB": ""} and listen_aus_mappe(mappe + ".fehlt") == {}, aus_mappe)

    def holen_luecke(symbole):
        return {s: reihen[s] for s in symbole if s in reihen and s[1:2] not in "DEFG"}
    inhalt3 = bauen(loaded={}, pfad=pfad, holen_kurse=holen_luecke, liste_text=text2, liste_text_andere=text3,
                    leise=True, alt={})
    p("Regel 1: unter 95 Prozent Abdeckung gibt es kein RS, sondern 'nicht verfuegbar'",
      inhalt3["status"] == "nicht verfuegbar" and all(a["rs"] is None for a in inhalt3["aktien"].values())
      and "Abdeckung" in inhalt3["grund"], inhalt3["grund"])
    p("Anzeige nennt den Grund", "nicht verfügbar" in anzeige(saf, inhalt3))
    p("Hinweis fuer die App nennt den US-Markt, NYSE und die Kappung",
      inhalt["bezug"] == "US-Markt" and "NYSE" in inhalt["hinweis"] and "gekappt" in inhalt["hinweis"])

    print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles bestanden.")
    return 1 if fehler else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="RS-Universum (Nasdaq, NYSE, NYSE American) rechnen.")
    ap.add_argument("--bauen", action="store_true")
    ap.add_argument("--ausgabe", default=DATEI)
    ap.add_argument("--mappe", default=MAPPE,
                    help="Kaufpunkte-Mappe, deren Aktien als Listen gerechnet werden")
    ap.add_argument("--zuordnung", default=None,
                    help="Zuordnungsliste der Branchen und Typen; Vorgabe " + ZUORDNUNG + ", falls vorhanden")
    ap.add_argument("--selbsttest", action="store_true")
    args = ap.parse_args()
    if args.selbsttest:
        return selbsttest()
    if args.bauen:
        bauen(pfad=args.ausgabe, listen_ticker=listen_aus_mappe(args.mappe), zuordnung_pfad=args.zuordnung)
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
