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
  python rs_universum.py --bauen            im Nachtscan, schreibt rs_universum.json
                                            (rund sechs Minuten fuer rund 6.600 Symbole)
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
import red_to_green

CFGU = CFG["rs_universum"]
DATEI = "rs_universum.json"

# Titel, die keine Stammaktien sind (R2: ETFs und Fonds draussen, SPACs
# erst nach der Uebernahme). ADRs ("American Depositary Shares") bleiben
# ausdruecklich drin.
AUSSCHLUSS = re.compile(
    r"warrant|\brights?\b|\bunits?\b|preferred|\bnotes?\b|debenture|subordinated|"
    r"\bbonds?\b|acquisition (corp|co\b|company|holdings)|\bSPAC\b|trust preferred|"
    r"capital securities|\bETN\b", re.I)


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
        liste.append({"symbol": sym, "name": name, "boerse": boerse,
                      "markt": str(z.get("Market Category") or "").strip()})
    if not leise:
        print(f"  {titel}: {len(zeilen)} Zeilen, {len(liste)} Stammaktien; "
              + "; ".join(f"{k} {v}" for k, v in gruende.items()))
    return liste, gruende


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
    block = block or int(CFGU["abruf_block"])
    zeitraum = zeitraum or CFGU["abruf_zeitraum"]
    raus = {}
    t0 = time.time()
    for i in range(0, len(symbole), block):
        teil = symbole[i:i + block]
        if download is not None:
            raus.update(download(teil))
            continue
        try:
            raus.update(_yahoo_block(teil, zeitraum))
        except Exception as e:  # noqa
            if not leise:
                print(f"  Block {i // block + 1}: Abruf gescheitert ({type(e).__name__}), "
                      f"zweiter Versuch in 20 s")
            time.sleep(20)
            try:
                raus.update(_yahoo_block(teil, zeitraum))
            except Exception as e2:  # noqa
                if not leise:
                    print(f"  Block {i // block + 1}: erneut gescheitert ({type(e2).__name__})")
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
                    raus.update(_yahoo_block(fehlend[i:i + 50], zeitraum))
                except Exception:  # noqa
                    continue
            if not leise:
                print(f"  Nachgeladen: {len(raus) - vorher} von {len(fehlend)} zunaechst fehlenden Symbolen")
    if not leise:
        print(f"  Kurse fuer {len(raus)} von {len(symbole)} Symbolen in {time.time() - t0:.0f} s")
    return raus


def _yahoo_block(symbole, zeitraum):
    import pandas as pd
    import yfinance as yf
    # SPLITBEREINIGT, NICHT dividendenbereinigt (auto_adjust=False):
    # Yahoos "Close" traegt die Splits, nur "Adj Close" auch Dividenden.
    roh = yf.download(" ".join(yahoo_symbol(s) for s in symbole), period=zeitraum,
                      interval="1d", group_by="ticker", progress=False,
                      auto_adjust=False, threads=True)
    raus = {}
    for s in symbole:
        try:
            df = roh[yahoo_symbol(s)] if isinstance(roh.columns, pd.MultiIndex) else roh
            df = df.dropna(subset=["Close"])
            if df.empty:
                continue
            raus[s] = {"daten": [d.strftime("%Y-%m-%d") for d in df.index],
                       "close": [float(x) for x in df["Close"].values],
                       "high": [float(x) for x in df["High"].values],
                       "low": [float(x) for x in df["Low"].values],
                       "volume": [float(x) if x == x else 0.0 for x in df["Volume"].values]}
        except Exception:  # noqa
            continue
    return raus


def aus_scanner_df(df):
    """Der Kursrahmen des Nachtscans (Spalten datetime, open, high, low,
    close, volume) in dieselbe Form wie kurse_holen."""
    return {"daten": [str(d)[:10] for d in df["datetime"]],
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


def kennzahlen(k, indizes, cfg=None):
    """Alle Groessen einer Aktie fuer Anzeige und Berichte."""
    cfg = cfg or CFGU
    n = len(k["close"])
    kurs = k["close"][-1] if n else None
    vortag = k["close"][-2] if n >= 2 else None
    roh = red_to_green.rs_rohwert(k["close"]) if n >= int(cfg["historie_tage"]) + 1 else None
    dvt = int(cfg["dollarvolumen_tage"])
    dv = (sum(c * v for c, v in zip(k["close"][-dvt:], k["volume"][-dvt:])) / min(n, dvt)) if n else None
    hoch52 = _hoch(k["high"], 252)
    hoch20 = _hoch(k["high"], int(CFG["abendbericht"]["hoch_20_tage"]))
    ad = ad_naeherung(k["close"], k["volume"])
    abst = (kurs / max(k["high"][-252:]) - 1) if n >= 60 and kurs else None
    e = {"kurs": round(kurs, 4) if kurs is not None else None,
         "vortag": round(vortag, 4) if vortag is not None else None,
         "pct": round((kurs / vortag - 1) * 100, 2) if (kurs and vortag) else None,
         "tage": n, "roh": roh, "dv50": round(dv) if dv is not None else None,
         "ad_roh": round(ad, 4) if ad is not None else None,
         "kurs_52w_hoch": hoch52, "kurs_20t_hoch": hoch20,
         "abst_52w_hoch_pct": round(abst * 100, 1) if abst is not None else None,
         "letzter_tag": k["daten"][-1] if n else None}
    for name, idx in (indizes or {}).items():
        linie = _linie(k, idx)
        kurz = name.lstrip("^").lower()
        e[f"linie_{kurz}_hoch"] = _hoch(linie, 252)
        # Aenderung der Linie ueber eine Woche, fuer die Sortierung der Berichte
        e[f"linie_{kurz}_1w"] = (round((linie[-1] / linie[-6] - 1) * 100, 2)
                                if len(linie) >= 6 and linie[-6] > 0 else None)
    return e


def ad_naeherung(closes, volumes, tage=65):
    """A/D als NAEHERUNG (R20, Gerhard): Ueber 13 Wochen das Volumen an
    Plus-Tagen gegen das Volumen an Minus-Tagen, minus 1 bis plus 1. IBD
    rechnet Akkumulation und Distribution aus Kurs und Volumen; genauer
    laesst es sich ohne deren Daten nicht nachbauen, und das steht in
    jeder Zeile dabei."""
    if len(closes) < tage + 1:
        return None
    c, v = closes[-tage - 1:], volumes[-tage:]
    gesamt = sum(x for x in v if x)
    if not gesamt:
        return None
    saldo = 0.0
    for i in range(1, len(c)):
        vol = v[i - 1] or 0.0
        if c[i] > c[i - 1]:
            saldo += vol
        elif c[i] < c[i - 1]:
            saldo -= vol
    return saldo / gesamt


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


def rs_text(rs, cfg=None):
    """Die Anzeige in Meldungen (R4, R6): 'RS 93, sehr gut', 'RS 62' oder
    'RS nicht verfuegbar'."""
    cfg = cfg or CFGU
    if rs is None:
        return "RS nicht verfügbar"
    zusatz = ", sehr gut" if rs >= int(cfg["sehr_gut_ab"]) else ""
    return f"RS {int(rs)}{zusatz}"


def linien_text(e):
    """R5: die RS-Linie gegen beide Indizes, kurz. Nur wenn die Werte da sind."""
    teile = []
    for kurz, name in (("spy", "SPY"), ("qqq", "QQQ")):
        h = e.get(f"linie_{kurz}_hoch")
        if h is None:
            continue
        teile.append(f"RS-Linie gegen {name} auf 52-Wochen-Hoch" if h else f"RS-Linie gegen {name} kein Hoch")
    return "; ".join(teile)


# ---------------------------------------------------------------------------
# Bauen
# ---------------------------------------------------------------------------

def _verlauf_fortschreiben(alt_eintrag, tag, rs, hoechstens):
    verlauf = [v for v in (alt_eintrag or {}).get("rs_verlauf", []) if isinstance(v, list) and len(v) == 2 and v[0] != tag]
    verlauf.append([tag, rs])
    return verlauf[-hoechstens:]


def bauen(loaded=None, pfad=DATEI, holen_liste=None, holen_kurse=None, leise=False, alt=None,
          liste_text=None, liste_text_andere=None, jetzt=None):
    """Der naechtliche Lauf. loaded: {Ticker: (df, Firma)} des Nachtscans,
    dessen Aktien GEGEN den Bezug gerechnet werden (Luecke 5)."""
    cfg = CFGU
    t0 = time.time()
    liste, gruende = nasdaq_liste(text=liste_text, holen=holen_liste, leise=leise)
    liste2, gruende2 = andere_liste(text=liste_text_andere, holen=holen_liste, leise=leise)
    bekannt = {e["symbol"] for e in liste}
    liste = liste + [e for e in liste2 if e["symbol"] not in bekannt]
    symbole = [e["symbol"] for e in liste]
    boerse_von = {e["symbol"]: e["boerse"] for e in liste}
    indizes_namen = list(cfg["indizes"]) + [cfg["markt_index"]]
    kurse = (holen_kurse or kurse_holen)(symbole + indizes_namen, leise=leise) if holen_kurse is None \
        else holen_kurse(symbole + indizes_namen)
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
    bezug = {s: kz for gruppe in (aktien, ausserhalb) for s, kz in gruppe.items() if kz.get("roh") is not None}
    rohwerte = [kz["roh"] for kz in bezug.values()]
    roh_bezug = {s: kz["roh"] for s, kz in bezug.items()}
    ad_bezug = {s: kz["ad_roh"] for s, kz in bezug.items() if kz.get("ad_roh") is not None}
    probe = selbsttest_kuenstlich(rohwerte) if rohwerte else {"ok": False, "grund": "keine Rohwerte"}
    if status == "ok" and not probe.get("ok"):
        status, grund = "nicht verfuegbar", "Selbsttest der kuenstlichen Aktie fehlgeschlagen"
    tag = (jetzt or date.today()).isoformat()
    handelstag = max((kz["letzter_tag"] for kz in bezug.values() if kz.get("letzter_tag")), default=None)
    alt = alt if alt is not None else lies(pfad)
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
        kz["roh"] = round(kz["roh"], 6)
    plaus = plausibilitaet([kz["rs"] for kz in bezug.values()]) if status == "ok" else {"ok": False, "grund": status, "dezile": []}
    if status == "ok" and not plaus["ok"]:
        # Kein Grund, die Werte zu verwerfen (das waere eine Vermutung), aber
        # ein Befund, der gemeldet wird.
        grund = "Plausibilitaet: " + plaus["grund"]

    # Listen-Aktien GEGEN den Bezug (Luecke 5)
    listen_ergebnis = {}
    sortiert = sorted(rohwerte)
    ad_sortiert = sorted(ad_bezug.values())
    for t, wert in (loaded or {}).items():
        try:
            df = wert[0] if isinstance(wert, tuple) else wert
            firma = wert[1] if isinstance(wert, tuple) and len(wert) > 1 else ""
            k = aus_scanner_df(df)
        except Exception:  # noqa
            continue
        kz = kennzahlen(k, indizes, cfg)
        kz["firma"] = firma
        kz["im_universum"] = t in aktien
        kz["im_bezug"] = t in bezug
        kz["boerse"] = boerse_von.get(t)
        if status == "ok" and kz["roh"] is not None and sortiert:
            kz["rs"] = _perzentil_ohne(sortiert, roh_bezug.get(t), kz["roh"])
        else:
            kz["rs"] = None
        if kz["roh"] is not None:
            kz["roh"] = round(kz["roh"], 6)
        kz["ad_rang"] = (_perzentil_ohne(ad_sortiert, ad_bezug.get(t), kz["ad_roh"])
                         if (status == "ok" and kz.get("ad_roh") is not None and ad_sortiert) else None)
        alt_l = ((alt or {}).get("listen", {}) if isinstance(alt, dict) else {}).get(t)
        kz["rs_verlauf"] = _verlauf_fortschreiben(alt_l, handelstag or tag, kz["rs"], int(cfg["rs_verlauf_tage"]))
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
                    f"eine Kennzeichnung, keine Vergleichsbasis. Kurse splitbereinigt, nicht dividendenbereinigt."),
        "universum": {"quelle": cfg["quelle"], "quelle_andere": cfg["quelle_andere"], "verzeichnis": len(liste),
                      "ausgeschlossen": gruende, "ausgeschlossen_andere": gruende2,
                      "geladen": len(geladen), "abdeckung": round(abdeckung, 4),
                      "mindest_abdeckung": float(cfg["mindest_abdeckung"]),
                      "bezug_anzahl": len(bezug), "je_boerse": je_boerse, "kappung": kap,
                      "im_universum": len(aktien), "ausserhalb": len(ausserhalb),
                      "gruende_ausserhalb": _zaehle(v.get("grund") for v in ausserhalb.values()),
                      "dauer_s": round(time.time() - t0)},
        "selbsttest": probe, "plausibilitaet": plaus,
        "markt": markt_info,
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
    return a if (a and a.get("rs") is not None) else None


def anzeige(ticker, daten=None):
    """Eine Zeile fuer Meldungen: RS und RS-Linien (R4, R5, R6). Leer, wenn
    die Aktie nirgends gerechnet ist."""
    d = daten if daten is not None else lies()
    e = eintrag(ticker, d)
    if not e:
        return ""
    if d.get("status") != "ok":
        return "RS nicht verfügbar (" + str(d.get("grund") or d.get("status")) + ")"
    teile = [rs_text(e.get("rs"))]
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
            "File Creation Time: 0911202621:31|||||||\n")
    liste, gruende = nasdaq_liste(text=text)
    p("Verzeichnis: ETF, Test-Titel, Optionsschein und SPAC fallen, ADR und Stammaktie bleiben",
      [e["symbol"] for e in liste] == ["AAPL", "AACG", "BRK.B"] and gruende.get("ETF") == 1
      and gruende.get("Test-Titel") == 1, f"{[e['symbol'] for e in liste]} {gruende}")
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
                   "File Creation Time: 0911202621:31|||||||\n")
    liste2, gruende2 = andere_liste(text=text_andere)
    p("NYSE-Verzeichnis: Stammaktien von NYSE und NYSE American bleiben, Arca, ETF, Vorzug, Optionsschein, Test fallen",
      [(e["symbol"], e["boerse"]) for e in liste2] == [("IBM", "NYSE"), ("BRK.B", "NYSE"), ("BE", "NYSE"), ("LODE", "NYSE American")]
      and gruende2.get("andere Boerse") == 1 and gruende2.get("ETF") == 1 and gruende2.get("Test-Titel") == 1
      and gruende2.get("kein Stammtitel (Symbol: Vorzug, Optionsschein, Einheit, Recht)") == 2,
      f"{[e['symbol'] for e in liste2]} {gruende2}")
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
    kurz = {"daten": kd["daten"][:100], "close": k[:100], "high": kd["high"][:100], "low": kd["low"][:100], "volume": [1e6] * 100}
    kz2 = kennzahlen(kurz, {})
    p("Zu kurze Historie: kein Rohwert, kein 52-Wochen-Hoch", kz2["roh"] is None and kz2["kurs_52w_hoch"] is None)
    p("A/D-Naeherung: nur steigende Tage ergibt plus 1, nur fallende minus 1, Wechsel null",
      ad_naeherung([1.0 * 1.01 ** i for i in range(70)], [100.0] * 70) == 1.0
      and ad_naeherung([100.0 * 0.99 ** i for i in range(70)], [100.0] * 70) == -1.0
      and abs(ad_naeherung([100.0 + (i % 2) for i in range(71)], [100.0] * 71)) < 0.02
      and ad_naeherung([1.0] * 10, [1.0] * 10) is None)

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
    p("Eintrag fuer Anzeigen findet auch Titel unter den Schwellen, aber keine ohne Wert",
      eintrag("BILLIG", inhalt) is not None and eintrag("JUNG", inhalt) is None and eintrag("FEHLT", inhalt) is None)
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
    ap.add_argument("--selbsttest", action="store_true")
    args = ap.parse_args()
    if args.selbsttest:
        return selbsttest()
    if args.bauen:
        bauen(pfad=args.ausgabe)
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
