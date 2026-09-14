#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCANNER-DATEN: die Nachttabelle fuer den Scanner der Heliot-App
===============================================================
Mathias, 14.09.2026: "Wir bauen nun den scanner ein, erreichbar aus dem
web-tool. [...] Wenn wir dazu die historischen Charts sichern muessen,
zumindest 3 Jahre zurueck, mache es, der Scanner braucht zugriff darauf.
Sichere die Charts und speichere sie, so du das nicht schon gemacht hast."

WAS DIESER LAUF BAUT
  scanner_tabelle.parquet  eine Zeile je Stammaktie von Nasdaq, NYSE und
                           NYSE American mit allen Werten, nach denen der
                           Scanner filtert, und den Mustertreffern samt
                           Rating. Der Ablauf legt sie als Release-Anhang
                           "scanner-daten" in dieses Repo (nicht in die
                           Versionsgeschichte: rund vier Megabyte je Nacht
                           wuerden das Repo in einem Jahr um ueber einen
                           Gigabyte wachsen lassen); die App liest sie dort.
  scanner_analysten.parquet  Empfehlungen, Kursziele und Quartals-
                           ueberraschungen von Nasdaq je Aktie. Sie gehen wie
                           der eingefrorene Konsens (F17) in das PRIVATE
                           Datenrepo heliot-daten; die App liest sie nur mit
                           dem Lese-Token DATEN_LESE_TOKEN.
  scanner_stand.json       wann gebaut, Stand der Kurse und jeder Quelle,
                           Zahl der Treffer je Strategie. Liegt im Repo; an
                           ihm erkennt scanner_noetig.py, ob gebaut werden muss.
  scanner_kurse_3j.parquet die Tageskurse der letzten drei Jahre je Aktie
                           (Eroeffnung, Hoch, Tief, Schluss, Volumen). Der
                           Ablauf sichert sie als Release-Anhang im PRIVATEN
                           Datenrepo heliot-daten, nie im oeffentlichen Repo.

KEINE VERNETZUNG mit dem Haupttool (Mathias: "Baue noch keine Vernetzung zu
unserem Haupttool d.h. der Scanner soll noch keinen Einfluss auf die Alarme
etc. nehmen"): Der Lauf sendet nichts, setzt keine Alarme und schreibt keine
Datei, die Waechter, Scanner-Mappe oder Alarmbot lesen.

WOHER DIE WERTE KOMMEN (gemessen 14.09.2026)
  Kurse       Yahoo, die ganze Historie in 100er-Bloecken (400 Aktien in 18
              Sekunden). Allzeithoch, Allzeittief und groesstes Volumen
              jemals aus der ganzen Historie, alles andere aus den letzten
              drei Jahren. Splitbereinigt, nicht dividendenbereinigt, wie im
              RS-Universum.
  Muster      die Detektoren aus pattern_scanner, cup_handle_v2 und
              ema_crossback, einmal streng und einmal mit Toleranz (alle
              zusammen 15 Millisekunden je Aktie).
  RS          rs_universum.json des Nachtscans: RS 1 bis 99, RS-Linie.
  Fundament   SEC-Zahlen aus dem Fundament-Release (Umsatz, Gewinn je Aktie,
              Bruttogewinn, Schulden, Eigenkapital, Bilanzsumme, ausstehende
              Aktien); die Zuordnung Ticker zu CIK kommt aus ibd_ratings.json
              des Nachtscans, dieser Lauf braucht die SEC also nicht.
  Sektor      Nasdaq-Screener: Sektor, Branche, Land, Marktkapitalisierung.
  Termine     Nasdaq-Kalender der kommenden Tage samt Tageszeit; fuer die
              Aktien der Wochenlisten zahlen_termine.json (Yahoo und Nasdaq
              zusammengefuehrt, genauer).
  Analysten   Nasdaq je Aktie: Empfehlungen (Kaufen, Halten, Verkaufen),
              Kursziel und die letzten vier Quartalsueberraschungen. Ein
              Siebtel des Universums je Nacht plus alle, die gerade berichtet
              haben (0,37 Sekunden je Abruf, 200 Abrufe ohne Drosselung).

TOLERANZ (Mathias: "Findet das Muster nichts, kann diese Aktie nicht
vorgeschlagen werden. Wuerde eine Toleranzabweichung von 5% jedoch fuers
erste akzeptieren."). Nach der Recherche vom 14.09.2026 bezieht sich die
Toleranz immer auf die Groesse, die eine Regel misst:
  * Schwellen in Prozent oder als Verhaeltnis: 5 Prozent der Schwelle. Aus
    "mindestens 25 Prozent ueber dem 52-Wochen-Tief" wird 23,75, aus "RS ab
    70" wird 66,5. Nicht als Prozentpunkte: aus 33 wuerde sonst 38, das
    waere eine andere Regel.
  * Lage zu gleitenden Durchschnitten: 5 Prozent der mittleren
    Tagesschwankung (ATR 14). 5 Prozent vom Kurs wuerden die Regel
    aushebeln.
  * Mindest- und Hoechstdauern: 5 Prozent, auf ganze Tage abgerundet.
  * Zaehlregeln, Richtungen (die 200-Tage-Linie steigt) und feste
    Formbedingungen (der Kurs ist noch in der Box) bleiben streng.
Jeder Treffer traegt, ob er streng oder nur mit Toleranz gefunden wurde; nur
mit Toleranz kostet er Rating-Punkte. Fallback-Kaufpunkte gibt es im Scanner
nicht.

HANDELBARKEIT, LANGEWEILE UND RATING (Recherche 14.09.2026, Quellen im
Bericht an Mathias): Handelbar heisst Kurs ab 10 Dollar, Tagesumsatz ab 10
Millionen Dollar, ein Jahr Historie. Eine Darvas Box ist langweilig, wenn das
Jahreshoch nicht mindestens das Doppelte des Jahrestiefs ist (Darvas' eigene
Vorauswahl, 1964), die mittlere Tagesspanne unter 2,5 Prozent liegt, die Box
kaum hoeher als anderthalb Tagesspannen oder tiefer als 25 Prozent ist. Das
Rating ordnet nur, es ersetzt nie ein fehlendes Muster: Bausteine von 0 bis
1 (relative Staerke, Naehe zum Hoch, Vorlauf, Tagesspanne, Liquiditaet,
Austrocknen des Volumens, Enge, Nachfrage, Musterqualitaet), gewichtet je
Muster, dazu die drei staerksten und die zwei schwaechsten Bausteine als
Begruendung.

Aufruf:
  python scanner_daten.py --bauen [--grenze N] [--analysten rotation|alle|aus]
  python scanner_daten.py --selbsttest
"""

import argparse
import copy
import json
import math
import os
import sys
import time
import zlib
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

from config import CFG as ZENTRAL, mind_erreicht

SC = ZENTRAL["scanner"]
TABELLE = "scanner_tabelle.parquet"
ANALYSTEN = "scanner_analysten.parquet"
STAND = "scanner_stand.json"
ARCHIV = os.path.join(".cache", "scanner", "scanner_kurse_3j.parquet")
NASDAQ_KOPF = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept": "application/json"}
SCREENER_URL = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&download=true"
KALENDER_URL = "https://api.nasdaq.com/api/calendar/earnings?date="
KURSZIEL_URL = "https://api.nasdaq.com/api/analyst/{}/targetprice"
UEBERRASCHUNG_URL = "https://api.nasdaq.com/api/company/{}/earnings-surprise"

# Die Strategien des Scanners: Kennung, Anzeige, Toleranz moeglich.
STRATEGIEN = (
    ("darvas", "Darvas Box", True),
    ("trend_template", "Minervini Trend Template", True),
    ("vcp", "VCP", True),
    ("cup_handle", "Cup & Handle", True),
    ("rectangle", "Rectangle Top", True),
    ("htf", "High & Tight Flag", True),
    ("htf_innen", "HTF Innen-Einstieg", True),
    ("ema_crossback", "EMA Crossback", False),
    ("power_gap", "Power-Gap (Lücken-Bestätigungstag)", False),
    ("hoch_52w", "Neues 52-Wochen-Hoch", False),
    ("hoch_allzeit", "Neues Allzeithoch", False),
)
STRATEGIE_NAMEN = {k: n for k, n, _ in STRATEGIEN}

# Zeithorizonte fuer Hoch und Tief in Handelstagen; "allzeit" aus der ganzen Historie.
HORIZONTE = (("1t", 1), ("1w", 5), ("1m", 21), ("3m", 63), ("6m", 126), ("1j", 252), ("3j", 756))

# Welche Musterschwellen die Toleranz lockert: mindestens-Schwellen werden
# kleiner, hoechstens-Schwellen groesser. Zaehlgroessen (Beruehrungen,
# Kontraktionen) bleiben, wie sie sind.
PS_MIN = ("tt_min_above_low", "tt_rs_min", "cup_min_depth", "cup_min_score", "htf_min_rise",
          "htf_min_low_price", "cup_min_len", "handle_min_len")
PS_MAX = ("tt_max_below_high", "cup_max_depth", "cup_rim_tolerance", "handle_max_retrace", "cup_max_len",
          "handle_max_len", "htf_max_pole_days", "htf_max_flag_cal_days", "htf_max_flag_range", "rect_band")
V2_MIN = ("cup_min_len_wochen", "cup_min_depth", "handle_min_position", "min_score", "r2_min", "symmetrie_min")
V2_MAX = ("cup_max_len_wochen", "cup_max_depth", "cup_rim_tolerance", "handle_max_retrace",
          "handle_max_len_obergrenze", "symmetrie_max")
GANZZAHLIG = {"cup_min_len", "handle_min_len", "cup_max_len", "handle_max_len", "htf_max_pole_days",
              "htf_max_flag_cal_days", "cup_min_len_wochen", "cup_max_len_wochen", "handle_max_len_obergrenze",
              "frische_max_tage"}

# Nasdaq nennt die Mitte "Neutral" (gemessen 14.09.2026 an INTC, PFE und F);
# ohne diesen Eintrag fehlte "Halten" in der ganzen Tabelle.
KONSENS_DEUTSCH = {"strong buy": "starker Kauf", "buy": "Kaufen", "outperform": "Kaufen", "hold": "Halten",
                   "neutral": "Halten", "underperform": "Verkaufen", "sell": "Verkaufen",
                   "strong sell": "starker Verkauf"}
KONSENS_WERT = {"starker Kauf": 5, "Kaufen": 4, "Halten": 3, "Verkaufen": 2, "starker Verkauf": 1}
LAGE_NASDAQ = {"time-pre-market": "vorboerslich", "time-after-hours": "nachboerslich",
               "time-not-supplied": "unbekannt"}

FUNDAMENT_KENNZAHLEN = ("umsatz", "umsatzkosten", "bruttogewinn", "eps_verwaessert", "eigenkapital",
                        "bilanzsumme", "verbindlichkeiten", "kurzfristige_schulden", "langfristige_schulden",
                        "aktien_ausstehend", "zinsueberschuss", "provisionsertrag", "praemien_verdient",
                        "mieterloese")


# ---------------------------------------------------------------------------
# Kleine Helfer
# ---------------------------------------------------------------------------

def ny_heute(jetzt=None):
    """Das Datum in New York; der Handelstag des Scanners."""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(ZENTRAL["betrieb"]["zeitzone_boerse"])
        return (jetzt.astimezone(tz) if jetzt else datetime.now(tz)).date()
    except Exception:  # noqa
        return (jetzt or datetime.now()).date()


def _f(x):
    """float oder None; NaN und Unendlich werden None."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _pct(neu, alt):
    """Veraenderung in Prozent, nur bei positiver Basis."""
    neu, alt = _f(neu), _f(alt)
    if neu is None or alt is None or alt <= 0:
        return None
    return round((neu / alt - 1.0) * 100.0, 2)


def _zahl_aus_text(s):
    """'$146.93', '41423806518.00', '1.6', 'NA' -> float oder None."""
    if s is None:
        return None
    t = str(s).replace("$", "").replace(",", "").replace("%", "").strip()
    if not t or t.upper() in ("NA", "N/A", "--"):
        return None
    return _f(t)


def rotation_auswahl(ticker_liste, stichtag, naechte):
    """Die Aktien, die heute an der Reihe sind: jede genau einmal in
    `naechte` Naechten, fest ueber eine Pruefsumme des Kuerzels."""
    tag = stichtag.toordinal() % max(1, int(naechte))
    return [t for t in ticker_liste if zlib.crc32(t.encode("utf-8")) % max(1, int(naechte)) == tag]


# ---------------------------------------------------------------------------
# Toleranz
# ---------------------------------------------------------------------------

def _gelockert(name, wert, toleranz, richtung):
    """Eine Schwelle, um die Toleranz gelockert. Dauern in ganzen Tagen oder
    Wochen: 5 Prozent, abgerundet (35 Tage ergeben einen Tag Spielraum)."""
    if name in GANZZAHLIG:
        spiel = int(math.floor(wert * toleranz + 1e-9))
        return int(wert - spiel) if richtung == "min" else int(wert + spiel)
    return wert * (1.0 - toleranz) if richtung == "min" else wert * (1.0 + toleranz)


@contextmanager
def cfg_toleranz(toleranz):
    """Lockert die einstellbaren Musterschwellen fuer die Dauer des Blocks
    und stellt sie in jedem Fall wieder her. Liefert die gelockerte
    Einstellung der Wochen-Cup-Fassung (die nimmt sie als Argument)."""
    import pattern_scanner as ps
    import cup_handle_v2
    alt_ps = {k: ps.CFG[k] for k in PS_MIN + PS_MAX if k in ps.CFG}
    alt_frische = ZENTRAL["darvas"]["frische_max_tage"]
    v2 = copy.deepcopy(cup_handle_v2.CFG)
    try:
        if toleranz:
            for k in PS_MIN:
                if k in ps.CFG:
                    ps.CFG[k] = _gelockert(k, alt_ps[k], toleranz, "min")
            for k in PS_MAX:
                if k in ps.CFG:
                    ps.CFG[k] = _gelockert(k, alt_ps[k], toleranz, "max")
            ZENTRAL["darvas"]["frische_max_tage"] = _gelockert("frische_max_tage", alt_frische, toleranz, "max")
            for k in V2_MIN:
                if k in v2:
                    v2[k] = _gelockert(k, v2[k], toleranz, "min")
            for k in V2_MAX:
                if k in v2:
                    v2[k] = _gelockert(k, v2[k], toleranz, "max")
        yield v2
    finally:
        for k, w in alt_ps.items():
            ps.CFG[k] = w
        ZENTRAL["darvas"]["frische_max_tage"] = alt_frische


def atr14(d):
    """Wilders mittlere wahre Tagesschwankung ueber 14 Tage, in Dollar."""
    h, lo, c = d["high"].astype(float), d["low"].astype(float), d["close"].astype(float)
    tr = pd.concat([h - lo, (h - c.shift()).abs(), (lo - c.shift()).abs()], axis=1).max(axis=1)
    return _f(tr.ewm(alpha=1.0 / 14.0, adjust=False).mean().iloc[-1]) or 0.0


def trend_template(d, rs, toleranz=0.0):
    """Minervinis acht Kriterien wie pattern_scanner.check_trend_template,
    mit Toleranz. Bei Toleranz 0 rechnet sie Wert fuer Wert dasselbe (der
    Selbsttest vergleicht beide). Rueckgabe (erfuellt, Zahl erfuellt).

    Die Lage zu den Durchschnitten bekommt 5 Prozent der ATR 14 Spielraum,
    die Prozentschwellen 5 Prozent ihres Werts, die Steigung keinen."""
    import pattern_scanner as ps
    last = d.iloc[-1]
    if pd.isna(last["ma200"]):
        return False, 0
    t = float(toleranz or 0.0)
    spiel = t * atr14(d) if t else 0.0
    tage = ps.CFG["tt_ma_slope_days"]
    slope_ok = False
    if len(d) > 200 + tage:
        slope_ok = last["ma200"] > d["ma200"].iloc[-1 - tage]
    checks = (
        last["close"] > last["ma150"] - spiel and last["close"] > last["ma200"] - spiel,
        last["ma150"] > last["ma200"] - spiel,
        bool(slope_ok),
        last["ma50"] > last["ma150"] - spiel and last["ma50"] > last["ma200"] - spiel,
        last["close"] > last["ma50"] - spiel,
        last["close"] >= last["lo52"] * (1 + ps.CFG["tt_min_above_low"] * (1.0 - t)),
        last["close"] >= last["hi52"] * (1 - ps.CFG["tt_max_below_high"] * (1.0 + t)),
        rs is not None and mind_erreicht(rs, ps.CFG["tt_rs_min"] * (1.0 - t)),
    )
    return all(bool(c) for c in checks), int(sum(bool(c) for c in checks))


def power_gap(d):
    """Lücken-Bestätigungstag auf der Tageskerze (Regelwerk Kapitel 7, wie
    der Waechter zum Handelsende): Eroeffnung mindestens gap_min ueber dem
    Vortagesschluss (derzeit 7 Prozent), Tief ueber dem Vortagesschluss,
    Schluss im oberen Fuenftel, Tagesvolumen mindestens gap_and_go_faktor
    mal der 50-Tage-Schnitt (derzeit das Dreifache, config.py).
    Die Fruehregel der ersten halben Stunde ist nur live pruefbar und fehlt
    hier. Kaufpunkt Tageshoch plus 1 Cent."""
    if d is None or len(d) < 52:
        return None
    heute, vortag = d.iloc[-1], d.iloc[-2]
    prev = _f(vortag["close"])
    o, h, l, c, v = (_f(heute[k]) for k in ("open", "high", "low", "close", "volume"))
    if None in (prev, o, h, l, c, v) or prev <= 0:
        return None
    gap = o / prev - 1.0
    if not mind_erreicht(gap, ZENTRAL["gap_and_go"]["gap_min"]):
        return None
    if l <= prev:
        return None
    vol50 = _f(d["volume"].iloc[-51:-1].mean())
    if not vol50 or not mind_erreicht(v / vol50, ZENTRAL["volumen"]["gap_and_go_faktor"]):
        return None
    spanne = h - l
    pos = (c - l) / spanne if spanne > 0 else 1.0
    if not mind_erreicht(pos, ZENTRAL["gap_and_go"]["schluss_position_min"]):
        return None
    return {"strategie": STRATEGIE_NAMEN["power_gap"], "kaufpunkt": round(h + 0.01, 2),
            "stop": round(l - 0.01, 2), "ziel": None,
            "status": f"Lücke {gap * 100:.1f} Prozent, Volumen {v / vol50:.1f} mal der 50-Tage-Schnitt".replace(".", ",")}


def _detektoren(di, tt_pass, toleranz, v2cfg):
    """Alle Muster einer Aktie in einer Tolerenzstufe: {kennung: Treffer}."""
    import pattern_scanner as ps
    import cup_handle_v2
    import ema_crossback
    raus = {}
    liste = [("htf", ps.detect_htf), ("htf_innen", ps.detect_htf_innen),
             ("vcp", lambda x: ps.detect_vcp(x, tt_pass)), ("darvas", ps.detect_darvas),
             ("rectangle", ps.detect_rectangle)]
    for kennung, fn in liste:
        try:
            r = fn(di)
        except Exception:  # noqa
            r = None
        if r:
            raus[kennung] = r
    cups = []
    for fn in (ps.detect_cup_handle, lambda x: cup_handle_v2.detect_cup_handle_v2(x, v2cfg)):
        try:
            r = fn(di)
        except Exception:  # noqa
            r = None
        if r:
            cups.append(r)
    if cups:
        raus["cup_handle"] = max(cups, key=lambda h: h.get("score", 0) or 0)
    if not toleranz:
        for kennung, fn in (("ema_crossback", ema_crossback.detect_ema_crossback), ("power_gap", power_gap)):
            try:
                r = fn(di)
            except Exception:  # noqa
                r = None
            if r:
                raus[kennung] = r
    return raus


# ---------------------------------------------------------------------------
# Kennzahlen je Aktie aus den Kursen
# ---------------------------------------------------------------------------

def extrema(voll):
    """Allzeithoch, Allzeittief und groesstes Volumen aus der ganzen Historie."""
    raus = {"historie_ab": None, "allzeithoch": None, "allzeithoch_datum": None, "allzeittief": None,
            "allzeittief_datum": None, "volumen_max": None, "volumen_max_datum": None,
            "historie_gesamt_tage": int(len(voll))}
    if voll is None or len(voll) == 0:
        return raus
    tage = pd.to_datetime(voll["datetime"])
    raus["historie_ab"] = tage.iloc[0].strftime("%Y-%m-%d")
    h = voll["high"].astype(float)
    lo = voll["low"].astype(float)
    v = voll["volume"].astype(float)
    if h.notna().any():
        i = int(np.nanargmax(h.values))
        raus["allzeithoch"], raus["allzeithoch_datum"] = round(float(h.iloc[i]), 4), tage.iloc[i].strftime("%Y-%m-%d")
    lo_pos = lo.where(lo > 0)
    if lo_pos.notna().any():
        i = int(np.nanargmin(lo_pos.values))
        raus["allzeittief"], raus["allzeittief_datum"] = round(float(lo_pos.iloc[i]), 4), tage.iloc[i].strftime("%Y-%m-%d")
    if v.notna().any() and float(np.nanmax(v.values)) > 0:
        i = int(np.nanargmax(v.values))
        raus["volumen_max"], raus["volumen_max_datum"] = float(v.iloc[i]), tage.iloc[i].strftime("%Y-%m-%d")
    return raus


def kurs_werte(d, ex):
    """Alle Kurs-Kennzahlen des letzten Handelstags aus den letzten drei
    Jahren (d, chronologisch) und den Extrema der ganzen Historie."""
    n = len(d)
    c = d["close"].astype(float)
    h = d["high"].astype(float)
    lo = d["low"].astype(float)
    o = d["open"].astype(float)
    v = d["volume"].astype(float)
    kurs = float(c.iloc[-1])
    raus = {"datum": pd.to_datetime(d["datetime"].iloc[-1]).strftime("%Y-%m-%d"), "kurs": round(kurs, 4),
            "eroeffnung": _f(o.iloc[-1]), "hoch": _f(h.iloc[-1]), "tief": _f(lo.iloc[-1]),
            "vortag": _f(c.iloc[-2]) if n >= 2 else None, "historie_tage": int(n)}
    raus["veraenderung_pct"] = _pct(kurs, raus["vortag"])
    raus["seit_eroeffnung_pct"] = _pct(kurs, raus["eroeffnung"])
    raus["red_to_green"] = bool(raus["vortag"] is not None and raus["eroeffnung"] is not None
                                and raus["eroeffnung"] < raus["vortag"] < kurs)
    spanne = (h / lo - 1.0).where(lo > 0) * 100.0
    raus["tagesspanne_pct"] = _f(round(spanne.iloc[-1], 2)) if n else None
    raus["volatilitaet_5_pct"] = _f(round(spanne.iloc[-5:].mean(), 2)) if n >= 5 else None
    raus["volatilitaet_20_pct"] = _f(round(spanne.iloc[-20:].mean(), 2)) if n >= 20 else None
    for tage in (21, 50, 200):
        if n >= tage:
            ema = float(c.ewm(span=tage, adjust=False).mean().iloc[-1])
            raus[f"ema{tage}"] = round(ema, 4)
            raus[f"abst_ema{tage}_pct"] = _pct(kurs, ema)
        else:
            raus[f"ema{tage}"] = None
            raus[f"abst_ema{tage}_pct"] = None
    for name, tage in HORIZONTE:
        fenster = min(n, tage)
        hoch = float(h.iloc[-fenster:].max())
        tief = float(lo.iloc[-fenster:].min())
        raus[f"abst_hoch_{name}_pct"] = _pct(kurs, hoch)
        raus[f"abst_tief_{name}_pct"] = _pct(kurs, tief) if tief > 0 else None
    raus["abst_hoch_allzeit_pct"] = _pct(kurs, ex.get("allzeithoch"))
    raus["abst_tief_allzeit_pct"] = _pct(kurs, ex.get("allzeittief"))
    raus["volumen"] = _f(v.iloc[-1])
    raus["volumen_50"] = _f(round(v.iloc[-50:].mean(), 0)) if n >= 1 else None
    raus["dollarvolumen_50"] = _f(round((c * v).iloc[-50:].mean(), 0)) if n >= 1 else None
    raus["volumen_max_tage_her"] = None
    if ex.get("volumen_max_datum"):
        tage_liste = list(pd.to_datetime(d["datetime"]).dt.strftime("%Y-%m-%d"))
        if ex["volumen_max_datum"] in tage_liste:
            raus["volumen_max_tage_her"] = n - 1 - tage_liste.index(ex["volumen_max_datum"])
    raus["rendite_3m_pct"] = _pct(kurs, c.iloc[-64]) if n >= 64 else None
    raus["rendite_6m_pct"] = _pct(kurs, c.iloc[-127]) if n >= 127 else None
    raus["hoch_52w"] = bool(n >= 60 and float(h.iloc[-1]) >= float(h.iloc[-min(n, 252):-1].max()))
    raus["hoch_allzeit"] = bool(ex.get("historie_gesamt_tage", 0) >= 252
                                and ex.get("allzeithoch_datum") == raus["datum"])
    # Bausteine des Ratings (Recherche 14.09.2026)
    tief_jahr = float(lo.iloc[-min(n, 252):].min())
    raus["jahresspanne"] = round(float(h.iloc[-min(n, 252):].max()) / tief_jahr, 3) if tief_jahr > 0 and n >= 60 else None
    raus["vdu"] = None
    raus["vol_spitze_10"] = None
    if n >= 60:
        davor = float(v.iloc[-60:-10].mean())
        if davor > 0:
            raus["vdu"] = round(float(v.iloc[-10:].mean()) / davor, 3)
            raus["vol_spitze_10"] = round(float(v.iloc[-10:].max()) / davor, 3)
    tr = pd.concat([h - lo, (h - c.shift()).abs(), (lo - c.shift()).abs()], axis=1).max(axis=1)
    atr50 = float(tr.iloc[-50:].mean()) if n >= 51 else 0.0
    raus["atr_verhaeltnis"] = round(float(tr.iloc[-5:].mean()) / atr50, 3) if atr50 > 0 else None
    raus["ma200_steigt_tage"] = None
    if n >= 201:
        ma200 = c.rolling(200).mean().dropna().values
        tage_steigend = 0
        for i in range(len(ma200) - 1, 0, -1):
            if ma200[i] > ma200[i - 1]:
                tage_steigend += 1
            else:
                break
        raus["ma200_steigt_tage"] = int(tage_steigend)
    return raus


def handelbar(werte, ex):
    """Kurs, Tagesumsatz und Historie reichen fuer einen Handel (config.py)."""
    hb = SC["handelbar"]
    return bool((werte.get("kurs") or 0) >= hb["kurs_min"]
                and (werte.get("dollarvolumen_50") or 0) >= hb["dollarvolumen_min"]
                and (ex.get("historie_gesamt_tage") or 0) >= hb["historie_min_tage"])


def _zahl_deutsch(x, stellen=1):
    return f"{x:.{stellen}f}".replace(".", ",")


def langweilig(werte, box_hoehe_pct):
    """Die Langeweile-Sperre der Darvas Box. Rueckgabe (langweilig, Gruende).
    box_hoehe_pct ist die Boxhoehe in Prozent der Oberkante."""
    lw = SC["langeweile"]
    gruende = []
    js = werte.get("jahresspanne")
    if js is None or js < lw["jahresspanne_min"]:
        gruende.append("Jahreshoch nicht das " + _zahl_deutsch(lw["jahresspanne_min"]) + "-Fache des Jahrestiefs"
                       + (" (" + _zahl_deutsch(js, 2) + ")" if js is not None else ""))
    adr = werte.get("volatilitaet_20_pct")
    if adr is None or adr < lw["adr_min_pct"]:
        gruende.append("mittlere Tagesspanne unter " + _zahl_deutsch(lw["adr_min_pct"]) + " Prozent")
    if box_hoehe_pct is not None:
        if adr and box_hoehe_pct / adr < lw["box_adr_min"]:
            gruende.append("Box kaum höher als " + _zahl_deutsch(lw["box_adr_min"]) + " Tagesspannen")
        if box_hoehe_pct > lw["box_hoehe_max_pct"]:
            gruende.append("Box tiefer als " + _zahl_deutsch(lw["box_hoehe_max_pct"], 0) + " Prozent")
    return bool(gruende), gruende


BAUSTEIN_NAMEN = {"rs": "relative Stärke", "hochnaehe": "Nähe zum Hoch", "vorlauf": "Vorlauf",
                  "jahresspanne": "Jahresspanne", "adr": "Tagesspanne", "liquiditaet": "Liquidität",
                  "austrocknen": "Austrocknen des Volumens", "enge": "Enge", "nachfrage": "Nachfrage",
                  "box": "Boxhöhe", "muster": "Musterqualität", "ma200_steigt": "Anstieg der 200-Tage-Linie"}


def _rampe(wert, von, bis):
    """0 beim Mindestwert, 1 beim Idealwert, linear dazwischen, gedeckelt;
    faellt die Rampe (von groesser als bis), geht es genauso."""
    wert = _f(wert)
    if wert is None or von == bis:
        return None
    return max(0.0, min(1.0, (wert - von) / (bis - von)))


def grund_bausteine(werte, rs):
    """Die Bausteine, die fuer jedes Muster gleich sind, je 0 bis 1."""
    r = SC["rating"]["rampen"]
    b = {"rs": _rampe(rs, *r["rs"]) if rs is not None else None}
    abst = werte.get("abst_hoch_1j_pct")
    if abst is not None:
        ath, drei = werte.get("abst_hoch_allzeit_pct"), werte.get("abst_hoch_3j_pct")
        ath_teil = 1.0 if (ath is not None and ath >= -2.0) else (0.5 if (drei is not None and drei >= -2.0) else 0.0)
        b["hochnaehe"] = 0.5 * _rampe(-abst, *r["hochnaehe"]) + 0.5 * ath_teil
    b["vorlauf"] = _rampe(werte.get("abst_tief_1j_pct"), *r["vorlauf"])
    b["jahresspanne"] = _rampe(werte.get("jahresspanne"), *r["jahresspanne"])
    adr = werte.get("volatilitaet_20_pct")
    if adr is not None:
        b["adr"] = _rampe(adr, *r["adr"]) * (0.8 if adr > r["adr_deckel"] else 1.0)
    dv = werte.get("dollarvolumen_50")
    if dv and dv > 0:
        b["liquiditaet"] = _rampe(math.log(dv), math.log(r["liquiditaet"][0]), math.log(r["liquiditaet"][1]))
    b["austrocknen"] = _rampe(werte.get("vdu"), *r["austrocknen"])
    b["enge"] = _rampe(werte.get("atr_verhaeltnis"), *r["enge"])
    b["nachfrage_volumen"] = _rampe(werte.get("vol_spitze_10"), *r["nachfrage"])
    b["ma200_steigt"] = _rampe(werte.get("ma200_steigt_tage"), *r["ma200_steigt"])
    return b


def _muster_qualitaet(kennung, treffer):
    status = str((treffer or {}).get("status") or "")
    if kennung == "cup_handle":
        return _rampe((treffer or {}).get("score"), *SC["rating"]["rampen"]["cup_score"])
    if kennung in ("htf", "htf_innen"):
        note = (treffer or {}).get("htf_note") or next((n for n in ("A", "B", "C") if f"Note {n}" in status), None)
        return {"A": 1.0, "B": 0.6, "C": 0.3}.get(note)
    if kennung == "vcp":
        if status.startswith("VCP komplett"):
            return 1.0
        return 0.6 if "Toleranz" in status else 0.3
    if kennung == "rectangle":
        return 1.0 if status.startswith("Setup komplett") else 0.5
    return None


def _box_baustein(k):
    """Boxhoehe in Tagesspannen: ideal 2 bis 8, null unter 1,5 und ueber 12."""
    r = SC["rating"]["rampen"]
    if k is None:
        return None
    (ideal_von, ideal_bis), (grenze_von, grenze_bis) = r["box_ideal"], r["box_grenzen"]
    if k < grenze_von or k > grenze_bis:
        return 0.0
    if ideal_von <= k <= ideal_bis:
        return 1.0
    if k < ideal_von:
        return _rampe(k, grenze_von, ideal_von)
    return _rampe(k, grenze_bis, ideal_bis)


def rating_aus(kennung, bausteine, streng):
    """Rating 0 bis 100 und Begruendung (drei staerkste, zwei schwaechste
    Bausteine) aus den Bausteinen und den Gewichten des Musters."""
    gewichte = SC["rating"]["gewichte"].get(kennung) or SC["rating"]["gewichte"]["standard"]
    summe = gewicht = 0.0
    teile = []
    for name, w in gewichte.items():
        v = bausteine.get(name)
        if v is None:
            continue
        summe += float(w) * v
        gewicht += float(w)
        teile.append((v, name))
    if gewicht <= 0:
        return None, None
    wert = 100.0 * summe / gewicht - (0.0 if streng else float(SC["rating"]["toleranz_abzug"]))
    stark = [BAUSTEIN_NAMEN[n] for v, n in sorted(teile, key=lambda x: -x[0])[:3] if v >= 0.6]
    schwach = [BAUSTEIN_NAMEN[n] for v, n in sorted(teile, key=lambda x: x[0])[:2] if v <= 0.4]
    text = "; ".join(x for x in (("stark: " + ", ".join(stark)) if stark else "",
                                 ("schwach: " + ", ".join(schwach)) if schwach else "") if x)
    return int(max(0, min(100, round(wert)))), (text or None)


def muster_werte(d, rs, werte, toleranz=None):
    """Mustertreffer einer Aktie in zwei Stufen: streng und mit Toleranz.
    Rueckgabe dict mit m_<kennung> (0 kein Treffer, 1 nur mit Toleranz,
    2 streng), kp_, stop_, status_, rating_ und grund_ je Strategie, dazu
    tt_count und die Langeweile-Sperre der Darvas Box."""
    import exit_regeln
    import pattern_scanner as ps
    toleranz = SC["toleranz"] if toleranz is None else toleranz
    raus = {}
    for kennung, _n, _t in STRATEGIEN:
        for feld in ("m", "kp", "stop", "status", "rating", "grund"):
            raus[f"{feld}_{kennung}"] = 0 if feld == "m" else None
    raus["tt_count"] = None
    raus["darvas_box_hoehe_pct"] = None
    raus["darvas_langweilig"] = None
    raus["darvas_langweilig_gruende"] = None
    if d is None or len(d) < 60:
        return raus
    di = ps.add_indicators(d.reset_index(drop=True))
    tt_s, tt_n = trend_template(di, rs, 0.0)
    raus["tt_count"] = tt_n
    with cfg_toleranz(0.0) as v2_streng:
        streng = _detektoren(di, tt_s, 0.0, v2_streng)
    locker, tt_t = {}, tt_s
    if toleranz:
        tt_t, _tt_nt = trend_template(di, rs, toleranz)
        with cfg_toleranz(toleranz) as v2_locker:
            locker = _detektoren(di, tt_t, toleranz, v2_locker)
    stufen = {k: (2, t) for k, t in streng.items()}
    for k, t in locker.items():
        stufen.setdefault(k, (1, t))
    if tt_s:
        stufen["trend_template"] = (2, None)
    elif tt_t:
        stufen["trend_template"] = (1, None)
    if werte.get("hoch_52w"):
        stufen["hoch_52w"] = (2, None)
    if werte.get("hoch_allzeit"):
        stufen["hoch_allzeit"] = (2, None)
    kurs = werte.get("kurs")
    grund = grund_bausteine(werte, rs)
    for kennung, (stufe, treffer) in stufen.items():
        raus[f"m_{kennung}"] = stufe
        bausteine = dict(grund)
        kp = None
        if treffer:
            if kennung == "darvas":
                oben, unten = _f(treffer.get("kaufpunkt")), _f(treffer.get("stop"))
                if oben and unten is not None:
                    oben, unten = oben - 0.01, unten + 0.01
                    hoehe = (oben - unten) / oben * 100.0 if oben > 0 else None
                    raus["darvas_box_hoehe_pct"] = round(hoehe, 2) if hoehe is not None else None
                    lw, gruende = langweilig(werte, hoehe)
                    raus["darvas_langweilig"] = lw
                    raus["darvas_langweilig_gruende"] = "; ".join(gruende) if gruende else None
                    adr = werte.get("volatilitaet_20_pct")
                    bausteine["box"] = _box_baustein(hoehe / adr if (hoehe is not None and adr) else None)
            bausteine["muster"] = _muster_qualitaet(kennung, treffer)
            treffer = dict(treffer)
            exit_regeln.deckel_anwenden(treffer)
            kp = _f(treffer.get("kaufpunkt"))
            raus[f"kp_{kennung}"] = kp
            raus[f"stop_{kennung}"] = _f(treffer.get("stop"))
            raus[f"status_{kennung}"] = str(treffer.get("status") or "") or None
        naehe = None
        if kp and kurs:
            naehe = 1.0 if kurs >= kp else _rampe((kp / kurs - 1.0) * 100.0, *SC["rating"]["rampen"]["kaufpunkt_naehe"])
        teile = [x for x in (grund.get("nachfrage_volumen"), naehe) if x is not None]
        bausteine["nachfrage"] = sum(teile) / len(teile) if teile else None
        raus[f"rating_{kennung}"], raus[f"grund_{kennung}"] = rating_aus(kennung, bausteine, stufe == 2)
    return raus


# ---------------------------------------------------------------------------
# Fundament
# ---------------------------------------------------------------------------

def _qreihe(reihe):
    """[(ende, wert)] chronologisch, 14-Wochen-Quartale auf 13 Wochen (W7)."""
    import ibd_ratings as ibd
    raus = []
    for s, e, w, _qu, _tax, *_ in reihe:
        if ZENTRAL["ibd_ratings"].get("wochen_13_umrechnen", True):
            w, _um = ibd.auf_13_wochen(s, e, w)
        raus.append((e, w))
    return raus


def _tage(a, b):
    try:
        return (date.fromisoformat(str(b)[:10]) - date.fromisoformat(str(a)[:10])).days
    except (TypeError, ValueError):
        return None


def _vorjahr(reihe, ende):
    for e, w in reihe:
        t = _tage(e, ende)
        if t is not None and 340 <= t <= 390:
            return w
    return None


def _vorquartal(reihe, ende):
    kandidaten = [(e, w) for e, w in reihe if (_tage(e, ende) or -1) > 0]
    if not kandidaten:
        return None
    e, w = kandidaten[-1]
    t = _tage(e, ende)
    return w if 60 <= t <= 120 else None


def _ttm(reihe, ende):
    """Summe der vier Quartale bis `ende`, nur wenn sie lueckenlos folgen."""
    enden = [e for e, _ in reihe]
    if ende not in enden:
        return None
    i = enden.index(ende)
    if i < 3:
        return None
    teil = reihe[i - 3:i + 1]
    for (e1, _), (e2, _) in zip(teil, teil[1:]):
        t = _tage(e1, e2)
        if t is None or not 60 <= t <= 120:
            return None
    return sum(w for _, w in teil)


def _ttm_vorjahr(reihe, ende):
    for e, _w in reihe:
        t = _tage(e, ende)
        if t is not None and 340 <= t <= 390:
            return _ttm(reihe, e)
    return None


def fundament_werte(reihen, heute=None):
    """Wachstum, Bruttomarge und Bilanz einer Firma aus ihren Reihen
    (ibd_ratings._reihen). q/q heisst wie bei Finviz: juengstes Quartal
    gegen das Vorjahresquartal; sequenziell: gegen das Vorquartal; y/y:
    die letzten vier Quartale gegen die vier Quartale ein Jahr davor."""
    import ibd_ratings as ibd
    heute = heute or date.today()
    grenze = (heute - timedelta(days=3 * 366 + 120)).isoformat()
    raus = {}

    def q(k):
        return [e for e in ((reihen.get(k) or {}).get("Q") or []) if e[1] >= grenze]

    ums_w5, _vermerk = ibd.umsatz_reihe(reihen)
    ums = _qreihe([e for e in ums_w5 if e[1] >= grenze])
    eps = _qreihe(q("eps_verwaessert"))
    for name, reihe in (("umsatz", ums), ("eps", eps)):
        if reihe:
            ende, wert = reihe[-1]
            raus[f"{name}_q_vj_pct"] = _pct(wert, _vorjahr(reihe, ende))
            raus[f"{name}_seq_pct"] = _pct(wert, _vorquartal(reihe, ende))
            raus[f"{name}_ttm_pct"] = _pct(_ttm(reihe, ende), _ttm_vorjahr(reihe, ende))
            raus[f"{name}_quartal_ende"] = ende
        else:
            for teil in ("q_vj_pct", "seq_pct", "ttm_pct", "quartal_ende"):
                raus[f"{name}_{teil}"] = None

    # Bruttomarge nur aus dem gewoehnlichen Umsatz; Banken, Versicherer und
    # REITs weisen keine aus.
    u = dict(_qreihe(q("umsatz")))
    bg = dict(_qreihe(q("bruttogewinn")))
    uk = dict(_qreihe(q("umsatzkosten")))
    marge = []
    for ende in sorted(u):
        if u[ende] and u[ende] > 0:
            if ende in bg:
                marge.append((ende, bg[ende] / u[ende], bg[ende], u[ende]))
            elif ende in uk:
                marge.append((ende, (u[ende] - uk[ende]) / u[ende], u[ende] - uk[ende], u[ende]))
    for teil in ("bruttomarge_pct", "bruttomarge_q_vj_pp", "bruttomarge_seq_pp", "bruttomarge_ttm_pp"):
        raus[teil] = None
    if marge:
        ende, m, _b, _u = marge[-1]
        raus["bruttomarge_pct"] = round(m * 100.0, 2)
        reihe_m = [(e, x) for e, x, _b2, _u2 in marge]
        vj = _vorjahr(reihe_m, ende)
        vq = _vorquartal(reihe_m, ende)
        raus["bruttomarge_q_vj_pp"] = round((m - vj) * 100.0, 2) if vj is not None else None
        raus["bruttomarge_seq_pp"] = round((m - vq) * 100.0, 2) if vq is not None else None
        b_reihe = [(e, b2) for e, _x, b2, _u2 in marge]
        u_reihe = [(e, u2) for e, _x, _b2, u2 in marge]
        b_ttm, u_ttm = _ttm(b_reihe, ende), _ttm(u_reihe, ende)
        b_vj, u_vj = _ttm_vorjahr(b_reihe, ende), _ttm_vorjahr(u_reihe, ende)
        if None not in (b_ttm, u_ttm, b_vj, u_vj) and u_ttm > 0 and u_vj > 0:
            raus["bruttomarge_ttm_pp"] = round((b_ttm / u_ttm - b_vj / u_vj) * 100.0, 2)

    def bestand(k):
        return {e[1]: e[2] for e in ((reihen.get(k) or {}).get("B") or [])}

    bilanz = bestand("bilanzsumme")
    ek, vb = bestand("eigenkapital"), bestand("verbindlichkeiten")
    ks, ls = bestand("kurzfristige_schulden"), bestand("langfristige_schulden")
    for teil in ("schulden_zu_ek", "schulden_zu_vermoegen_pct", "ek_quote_pct", "fk_quote_pct", "bilanz_ende"):
        raus[teil] = None
    if bilanz:
        ende = max(bilanz)
        summe = bilanz[ende]
        raus["bilanz_ende"] = ende
        eigen = ek.get(ende)
        schulden = None
        if ende in ks or ende in ls:
            schulden = (ks.get(ende) or 0.0) + (ls.get(ende) or 0.0)
        if summe and summe > 0:
            if schulden is not None:
                raus["schulden_zu_vermoegen_pct"] = round(schulden / summe * 100.0, 2)
            if eigen is not None:
                raus["ek_quote_pct"] = round(eigen / summe * 100.0, 2)
            fremd = vb.get(ende)
            if fremd is None and eigen is not None:
                fremd = summe - eigen
            if fremd is not None:
                raus["fk_quote_pct"] = round(fremd / summe * 100.0, 2)
        if schulden is not None and eigen is not None and eigen > 0:
            raus["schulden_zu_ek"] = round(schulden / eigen, 3)
    aktien = bestand("aktien_ausstehend")
    raus["aktien_ausstehend"] = aktien[max(aktien)] if aktien else None
    raus["aktien_stand"] = max(aktien) if aktien else None
    return raus


def fundament_tabelle(ciks, heute, kennzahlen=None, leise=True):
    """{cik: fundament_werte} fuer die gewuenschten Firmen. Rueckgabe
    (Werte, Status)."""
    import ibd_ratings as ibd
    if kennzahlen is None:
        jahre = list(range(heute.year - 3, heute.year + 1))
        kennzahlen = ibd.lade_kennzahlen(jahre, leise=leise, auswahl=FUNDAMENT_KENNZAHLEN)
    if kennzahlen is None or len(kennzahlen) == 0:
        return {}, "nicht verfuegbar: kein Fundament-Release erreichbar"
    gesucht = {int(c) for c in ciks if c is not None}
    teil = kennzahlen[kennzahlen["cik"].isin(gesucht)]
    werte = {}
    for cik, reihen_f in ibd._reihen_je_firma(teil).items():
        try:
            werte[cik] = fundament_werte(reihen_f, heute)
        except Exception:  # noqa
            continue
    return werte, "ok"


# ---------------------------------------------------------------------------
# Nasdaq
# ---------------------------------------------------------------------------

def _json_holen(url, timeout=30):
    """(HTTP-Status oder Fehlername, JSON oder None)."""
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=NASDAQ_KOPF), timeout=timeout) as a:
            return a.status, json.loads(a.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:  # noqa
        return type(e).__name__, None


def screener_aus(antwort):
    """{Ticker: {sektor, branche, land, marktkap, name}} aus der Screener-Antwort."""
    zeilen = antwort
    if isinstance(antwort, dict):
        zeilen = ((antwort.get("data") or {}).get("rows")) or []
    raus = {}
    for z in zeilen or []:
        t = str(z.get("symbol") or "").strip().upper().replace("/", ".")
        if not t:
            continue
        mk = _zahl_aus_text(z.get("marketCap"))
        raus[t] = {"sektor": (str(z.get("sector") or "").strip() or None),
                   "branche": (str(z.get("industry") or "").strip() or None),
                   "land": (str(z.get("country") or "").strip() or None),
                   "marktkap": mk if mk and mk > 0 else None,
                   "name_nasdaq": (str(z.get("name") or "").strip() or None)}
    return raus


def kalender_aus(antworten):
    """{Ticker: (Datum, Lage)} aus {Datum: Kalender-Antwort}; der frueheste Termin gewinnt."""
    raus = {}
    for tag in sorted(antworten):
        d = antworten[tag] or {}
        for z in ((d.get("data") or {}).get("rows") or []):
            t = str(z.get("symbol") or "").strip().upper()
            if t and t not in raus:
                raus[t] = (tag, LAGE_NASDAQ.get(z.get("time"), "unbekannt"))
    return raus


def analysten_aus(antwort):
    """Empfehlungen und Kursziel aus /analyst/<T>/targetprice, oder None."""
    d = (antwort or {}).get("data") if isinstance(antwort, dict) else None
    if not d:
        return None
    co = d.get("consensusOverview") or {}
    kaufen, halten, verkaufen = (int(_f(co.get(k)) or 0) for k in ("buy", "hold", "sell"))
    anzahl = kaufen + halten + verkaufen
    ziel = _f(co.get("priceTarget"))
    if anzahl == 0 and not ziel:
        return None
    konsens = None
    for eintrag in reversed(d.get("historicalConsensus") or []):
        k = str(((eintrag or {}).get("z") or {}).get("consensus") or "").strip().lower()
        if k:
            konsens = KONSENS_DEUTSCH.get(k)
            break
    return {"analysten_kaufen": kaufen, "analysten_halten": halten, "analysten_verkaufen": verkaufen,
            "analysten_anzahl": anzahl, "analysten_kauf_anteil_pct": round(kaufen / anzahl * 100.0, 1) if anzahl else None,
            "konsens": konsens, "konsens_wert": KONSENS_WERT.get(konsens),
            "kursziel": ziel, "kursziel_tief": _f(co.get("lowPriceTarget")), "kursziel_hoch": _f(co.get("highPriceTarget"))}


def ueberraschungen_aus(antwort):
    """Die letzten Quartalsueberraschungen aus /company/<T>/earnings-surprise, oder None."""
    d = (antwort or {}).get("data") if isinstance(antwort, dict) else None
    zeilen = (((d or {}).get("earningsSurpriseTable") or {}).get("rows")) or []
    quartale = geschlagen = 0
    for z in zeilen:
        eps, prognose = _zahl_aus_text(z.get("eps")), _zahl_aus_text(z.get("consensusForecast"))
        if eps is None or prognose is None:
            continue
        quartale += 1
        if eps > prognose:
            geschlagen += 1
    if not zeilen:
        return None
    erste = zeilen[0]
    datum = None
    try:
        datum = datetime.strptime(str(erste.get("dateReported") or ""), "%m/%d/%Y").date().isoformat()
    except ValueError:
        pass
    return {"quartale_mit_schaetzung": quartale, "schaetzung_geschlagen": geschlagen,
            "letzte_ueberraschung_pct": _zahl_aus_text(erste.get("percentageSurprise")),
            "letzter_bericht": datum}


def je_aktie_nasdaq(ticker, holen=None):
    """(Abruf gelungen, Analysten, Ueberraschungen) einer Aktie; zwei Abrufe."""
    holen = holen or _json_holen
    s1, a1 = holen(KURSZIEL_URL.format(ticker))
    s2, a2 = holen(UEBERRASCHUNG_URL.format(ticker))
    ok = s1 == 200 and s2 == 200
    return ok, (analysten_aus(a1) if s1 == 200 else None), (ueberraschungen_aus(a2) if s2 == 200 else None)


def viele_abrufe(ticker_liste, fn, faeden, fehlergrenze, mindestproben, leise=True):
    """fn(ticker) -> (ok, ...) fuer viele Aktien in kleinen Wellen. Scheitern
    mehr als `fehlergrenze` der Abrufe, hoert die Nacht auf; das Geholte
    bleibt. Rueckgabe ({Ticker: Ergebnis}, Zahl Fehler, abgebrochen)."""
    raus, fehler, geprueft, abgebrochen = {}, 0, 0, False
    welle = max(1, int(faeden) * 10)
    with ThreadPoolExecutor(max_workers=max(1, int(faeden))) as ex:
        for i in range(0, len(ticker_liste), welle):
            teil = ticker_liste[i:i + welle]
            for t, erg in zip(teil, ex.map(fn, teil)):
                geprueft += 1
                if not erg or not erg[0]:
                    fehler += 1
                raus[t] = erg
            if geprueft >= mindestproben and fehler / geprueft > fehlergrenze:
                abgebrochen = True
                if not leise:
                    print(f"  Nasdaq je Aktie: {fehler} Fehler in {geprueft} Abrufen, fuer heute Schluss")
                break
    return raus, fehler, abgebrochen


# ---------------------------------------------------------------------------
# Kurse
# ---------------------------------------------------------------------------

def universum(leise=True):
    """Alle Stammaktien von Nasdaq, NYSE und NYSE American (wie das RS-Universum)."""
    import rs_universum
    nas, _g = rs_universum.nasdaq_liste(leise=leise)
    andere, _g2 = rs_universum.andere_liste(leise=leise)
    je = {}
    for e in nas + andere:
        je.setdefault(e["symbol"], e)
    return [je[s] for s in sorted(je)]


def _yahoo_block(symbole):
    """Die ganze Tageshistorie eines Blocks von Yahoo: {Symbol: DataFrame}."""
    import rs_universum
    import yfinance as yf
    roh = yf.download(" ".join(rs_universum.yahoo_symbol(s) for s in symbole), period="max", interval="1d",
                      group_by="ticker", progress=False, auto_adjust=False, threads=True, actions=False)
    raus = {}
    for s in symbole:
        try:
            df = roh[rs_universum.yahoo_symbol(s)] if isinstance(roh.columns, pd.MultiIndex) else roh
            df = df.dropna(subset=["Close"])
            if df.empty:
                continue
            idx = pd.to_datetime(df.index)
            if getattr(idx, "tz", None) is not None:
                idx = idx.tz_localize(None)
            raus[s] = pd.DataFrame({"datetime": idx, "open": df["Open"].astype(float).values,
                                    "high": df["High"].astype(float).values,
                                    "low": df["Low"].astype(float).values,
                                    "close": df["Close"].astype(float).values,
                                    "volume": df["Volume"].fillna(0).astype(float).values})
        except Exception:  # noqa
            continue
    return raus


def kurse_bloecke(symbole, download=None, block=None, leise=True):
    """Liefert je Block {Symbol: DataFrame}. Was Yahoo im grossen Block still
    auslaesst (gemessen am 12.09.2026 bei NYSE), wird in 50er-Bloecken
    nachgeholt."""
    download = download or _yahoo_block
    block = int(block or SC["kurs_block"])
    fehlend = []
    for i in range(0, len(symbole), block):
        teil = symbole[i:i + block]
        try:
            erg = download(teil)
        except Exception as e:  # noqa
            if not leise:
                print(f"  Block {i // block + 1}: {type(e).__name__}, zweiter Versuch in 20 s")
            time.sleep(20)
            try:
                erg = download(teil)
            except Exception:  # noqa
                erg = {}
        fehlend.extend(s for s in teil if s not in erg)
        yield erg
    if fehlend and download is _yahoo_block:
        for i in range(0, len(fehlend), 50):
            try:
                yield download(fehlend[i:i + 50])
            except Exception:  # noqa
                continue


# ---------------------------------------------------------------------------
# Bauen
# ---------------------------------------------------------------------------

def _wahr(spalte):
    """True nur fuer echte Wahrheitswerte True; None, NA und alles andere False."""
    return spalte.map(lambda x: bool(x) if isinstance(x, (bool, np.bool_)) else False).astype(bool)


def _lies_json(pfad):
    try:
        with open(pfad, encoding="utf-8-sig") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _alte_tabelle(pfad):
    try:
        alt = pd.read_parquet(pfad)
        return {str(r["ticker"]): r for r in alt.to_dict("records")}
    except Exception:  # noqa
        return {}


ANALYSTEN_FELDER = ("analysten_kaufen", "analysten_halten", "analysten_verkaufen", "analysten_anzahl",
                    "analysten_kauf_anteil_pct", "konsens", "konsens_wert", "kursziel", "kursziel_tief",
                    "kursziel_hoch", "analysten_stand")
UEBERRASCHUNG_FELDER = ("quartale_mit_schaetzung", "schaetzung_geschlagen", "letzte_ueberraschung_pct",
                        "letzter_bericht", "ueberraschung_stand")


def bauen(pfad_tabelle=TABELLE, pfad_stand=STAND, archiv=ARCHIV, grenze=None, analysten="rotation",
          heute=None, universum_liste=None, kurse_download=None, rs_daten=None, ratings=None, termine_listen=None,
          screener=None, kalender=None, je_aktie=None, kennzahlen=None, leise=False, pfad_analysten=ANALYSTEN):
    """Die ganze Nachttabelle. Alle Quellen lassen sich fuer den Selbsttest
    uebergeben; ohne Angabe wird geholt. Die Analystenwerte der Vornacht
    stehen in pfad_analysten (der Ablauf holt sie vorher aus dem privaten
    Datenrepo); fehlt die Datei, beginnt die Rotation von vorn."""
    import rs_universum
    t0 = time.time()
    heute = heute or ny_heute()
    # Mit Zeitzone: Der Ablauf rechnet in UTC, die App zeigt Wiener Zeit.
    stand = {"gebaut_am": datetime.now(timezone.utc).isoformat(timespec="seconds"), "handelstag": None,
             "status": "ok", "toleranz": SC["toleranz"], "quellen": {}, "hinweise": []}

    liste = universum_liste if universum_liste is not None else universum(leise=leise)
    if grenze and int(grenze) < len(liste):
        # Probelauf: gleichmaessig ueber das Alphabet verteilt statt der ersten N.
        schritt = max(1, len(liste) // int(grenze))
        liste = liste[::schritt][:int(grenze)]
    namen = {e["symbol"]: e for e in liste}
    symbole = [e["symbol"] for e in liste]
    stand["universum"] = len(symbole)

    rs_daten = rs_daten if rs_daten is not None else _lies_json(rs_universum.DATEI)
    ratings = ratings if ratings is not None else _lies_json("ibd_ratings.json")
    termine_listen = termine_listen if termine_listen is not None else _lies_json("zahlen_termine.json")
    stand["quellen"]["rs"] = {"stand": rs_daten.get("gebaut_am"), "status": rs_daten.get("status", "fehlt")}
    wochenliste = set((rs_daten.get("listen") or {}).keys())

    # --- Kurse, Kennzahlen und Muster je Block ------------------------------
    zeilen, archiv_teile, ohne_kurse = {}, [], 0
    grenze_archiv = pd.Timestamp(heute - timedelta(days=int(SC["archiv_tage"])))
    for block in kurse_bloecke(symbole, download=kurse_download, leise=leise):
        for s, voll in block.items():
            if s in zeilen or voll is None or len(voll) == 0:
                continue
            voll = voll.sort_values("datetime").reset_index(drop=True)
            ex = extrema(voll)
            d = voll.tail(int(SC["historie_tage"])).reset_index(drop=True)
            werte = kurs_werte(d, ex)
            e_rs = rs_universum.eintrag(s, rs_daten) or {}
            rs = e_rs.get("rs")
            zeile = {"ticker": s, "name": namen.get(s, {}).get("name"), "boerse": namen.get(s, {}).get("boerse"),
                     "in_wochenliste": s in wochenliste, **ex, **werte,
                     "rs": rs, "rs_vorlaeufig": e_rs.get("rs_vorlaeufig"),
                     "rs_linie_hoch": e_rs.get("linie_spy_hoch"), "rs_linie_abst_pct": e_rs.get("linie_spy_abst_pct"),
                     "rs_linie_qqq_hoch": e_rs.get("linie_qqq_hoch"),
                     "rs_linie_qqq_abst_pct": e_rs.get("linie_qqq_abst_pct")}
            zeile["handelbar"] = handelbar(werte, ex)
            zeile.update(muster_werte(d, rs, werte))
            zeilen[s] = zeile
            archiv_teile.append(pd.DataFrame({
                "ticker": s, "datum": pd.to_datetime(voll["datetime"]),
                "open": voll["open"].astype("float32"), "high": voll["high"].astype("float32"),
                "low": voll["low"].astype("float32"), "close": voll["close"].astype("float32"),
                "volume": voll["volume"].astype("float64")}).loc[lambda x: x["datum"] >= grenze_archiv])
        if not leise:
            print(f"  Kurse und Muster: {len(zeilen)} von {len(symbole)} Aktien, {time.time() - t0:.0f} s")
    ohne_kurse = len(symbole) - len(zeilen)
    letzte = pd.Series([z["datum"] for z in zeilen.values()])
    handelstag = letzte.mode().iloc[0] if len(letzte) else None
    stand["handelstag"] = handelstag
    for z in zeilen.values():
        z["kurse_aktuell"] = bool(handelstag and z["datum"] >= handelstag)
    aktuell = sum(1 for z in zeilen.values() if z["kurse_aktuell"])
    abdeckung = aktuell / len(symbole) if symbole else 0.0
    stand["quellen"]["kurse"] = {"status": "ok", "mit_kursen": len(zeilen), "ohne_kurse": ohne_kurse,
                                 "aktuell": aktuell, "abdeckung": round(abdeckung, 4)}
    if abdeckung < SC["mindest_abdeckung"]:
        stand["status"] = "unvollstaendig"
        stand["hinweise"].append(f"Kurse nur fuer {abdeckung * 100:.0f} Prozent des Universums aktuell")

    # --- Sektor und Marktkapitalisierung ----------------------------------------
    if screener is None:
        code, antwort = _json_holen(SCREENER_URL, timeout=60)
        screener = screener_aus(antwort) if code == 200 else {}
        stand["quellen"]["screener"] = {"status": "ok" if screener else f"nicht verfuegbar ({code})"}
    else:
        screener = screener_aus(screener) if isinstance(screener, (list, dict)) and not (
            isinstance(screener, dict) and all(isinstance(v, dict) and "sektor" in v for v in screener.values())) else screener
        stand["quellen"]["screener"] = {"status": "ok"}
    stand["quellen"]["screener"]["anzahl"] = len(screener)
    for s, z in zeilen.items():
        sc = screener.get(s) or screener.get(s.replace(".", "/")) or {}
        z["sektor"] = sc.get("sektor")
        z["branche"] = sc.get("branche")
        z["land"] = sc.get("land")
        z["marktkap_mrd"] = round(sc["marktkap"] / 1e9, 4) if sc.get("marktkap") else None

    # --- Termine ------------------------------------------------------------------
    if kalender is None:
        antworten = {}
        for i in range(0, int(SC["termine_tage"]) + 1):
            tag = heute + timedelta(days=i)
            if tag.weekday() >= 5:
                continue
            code, antwort = _json_holen(KALENDER_URL + tag.isoformat())
            if code == 200:
                antworten[tag.isoformat()] = antwort
        kalender = kalender_aus(antworten)
        stand["quellen"]["kalender"] = {"status": "ok" if antworten else "nicht verfuegbar", "tage": len(antworten)}
    else:
        stand["quellen"]["kalender"] = {"status": "ok"}
    stand["quellen"]["kalender"]["eintraege"] = len(kalender)
    listen_termine = (termine_listen or {}).get("aktien") or {}
    for s, z in zeilen.items():
        lt = listen_termine.get(s)
        if lt and lt.get("datum"):
            z["termin_datum"], z["termin_lage"], z["termin_quelle"] = lt["datum"], lt.get("lage") or "unbekannt", "Wochenliste"
        elif s in kalender:
            z["termin_datum"], z["termin_lage"], z["termin_quelle"] = kalender[s][0], kalender[s][1], "Nasdaq"
        else:
            z["termin_datum"] = z["termin_lage"] = z["termin_quelle"] = None

    # --- Fundament ------------------------------------------------------------------
    ciks = {}
    for s in zeilen:
        cik = ((ratings.get("aktien") or {}).get(s) or {}).get("cik")
        if cik:
            ciks[s] = int(cik)
    werte_f, status_f = fundament_tabelle(set(ciks.values()), heute, kennzahlen=kennzahlen, leise=leise)
    stand["quellen"]["fundament"] = {"status": status_f if ciks else "nicht verfuegbar: keine Zuordnung Ticker zu CIK",
                                     "firmen": len(werte_f), "zuordnung": len(ciks)}
    leer_f = fundament_werte({}, heute)
    for s, z in zeilen.items():
        z.update(werte_f.get(ciks.get(s), leer_f) if ciks.get(s) else leer_f)

    # --- Analysten und Ueberraschungen: Rotation ------------------------------------
    alt = _alte_tabelle(pfad_analysten)
    for s, z in zeilen.items():
        a = alt.get(s) or {}
        for feld in ANALYSTEN_FELDER + UEBERRASCHUNG_FELDER:
            w = a.get(feld)
            z[feld] = None if (isinstance(w, float) and not math.isfinite(w)) else w
    info = {"status": "aus", "abgerufen": 0, "fehler": 0, "abgebrochen": False}
    if analysten != "aus":
        if analysten == "alle":
            auswahl = sorted(zeilen)
        else:
            auswahl = rotation_auswahl(sorted(zeilen), heute, SC["rotation_naechte"])
            frisch = {s for s, z in zeilen.items() if z.get("termin_datum") and 0 <= (_tage(z["termin_datum"], heute.isoformat()) or -1) <= SC["nach_bericht_tage"]}
            noch_nie = [s for s, z in zeilen.items() if not z.get("analysten_stand")]
            auswahl = sorted(set(auswahl) | frisch)
            if len(noch_nie) > len(auswahl):
                info["hinweis"] = f"{len(noch_nie)} Aktien noch nie abgefragt; volle Abdeckung nach {SC['rotation_naechte']} Naechten"
        fn = je_aktie or je_aktie_nasdaq
        erg, fehler, abgebrochen = viele_abrufe(auswahl, fn, SC["abruf_faeden"], SC["abruf_fehlergrenze"],
                                                SC["abruf_mindestproben"], leise=leise)
        for s, (ok, an, ue) in ((s, e) for s, e in erg.items() if e):
            z = zeilen[s]
            if ok or an is not None:
                for feld in ANALYSTEN_FELDER:
                    z[feld] = None
                if an:
                    z.update(an)
                z["analysten_stand"] = heute.isoformat()
            if ok or ue is not None:
                for feld in UEBERRASCHUNG_FELDER:
                    z[feld] = None
                if ue:
                    z.update(ue)
                z["ueberraschung_stand"] = heute.isoformat()
        info = {"status": "abgebrochen" if abgebrochen else "ok", "abgerufen": len(erg), "fehler": fehler,
                "abgebrochen": abgebrochen, **({"hinweis": info["hinweis"]} if info.get("hinweis") else {})}
    info["mit_analysten"] = sum(1 for z in zeilen.values() if z.get("analysten_anzahl"))
    info["mit_stand"] = sum(1 for z in zeilen.values() if z.get("analysten_stand"))
    stand["quellen"]["analysten"] = info

    # --- Schreiben ---------------------------------------------------------------
    for z in zeilen.values():
        if z.get("kursziel") and z.get("kurs"):
            z["kursziel_abst_pct"] = _pct(z["kursziel"], z["kurs"])
        else:
            z["kursziel_abst_pct"] = None
    tabelle = pd.DataFrame(sorted(zeilen.values(), key=lambda z: z["ticker"]))
    if len(tabelle):
        for spalte in tabelle.columns:
            if tabelle[spalte].dtype == object:
                werte_sp = tabelle[spalte].dropna()
                if len(werte_sp) and all(isinstance(w, bool) for w in werte_sp):
                    tabelle[spalte] = tabelle[spalte].astype("boolean")
    # Die Nasdaq-Werte je Aktie in eine eigene Datei (privates Datenrepo),
    # die Tabelle behaelt alles andere.
    privat = [s for s in ("ticker",) + ANALYSTEN_FELDER + UEBERRASCHUNG_FELDER + ("kursziel_abst_pct",)
              if s in tabelle.columns]
    tabelle[privat].to_parquet(pfad_analysten, compression="zstd", index=False)
    tabelle = tabelle.drop(columns=[s for s in privat if s != "ticker"])
    tabelle.to_parquet(pfad_tabelle, compression="zstd", index=False)
    treffer = {}
    if len(tabelle):
        aktuell_t = tabelle[_wahr(tabelle["kurse_aktuell"])]
        handelbar_t = aktuell_t[_wahr(aktuell_t["handelbar"])]
        for kennung, name, tol in STRATEGIEN:
            spalte = f"m_{kennung}"
            treffer[kennung] = {"name": name, "toleranz_moeglich": tol,
                                "streng": int((aktuell_t[spalte] == 2).sum()),
                                "nur_toleranz": int((aktuell_t[spalte] == 1).sum()),
                                "handelbar": int((handelbar_t[spalte] > 0).sum())}
        lw = _wahr(handelbar_t["darvas_langweilig"])
        treffer["darvas"]["handelbar_langweilig"] = int(((handelbar_t["m_darvas"] > 0) & lw).sum())
    stand["strategien"] = treffer
    stand["zeilen"] = int(len(tabelle))
    stand["dauer_s"] = round(time.time() - t0, 1)
    with open(pfad_stand, "w", encoding="utf-8") as f:
        json.dump(stand, f, ensure_ascii=False, indent=1)
    if archiv and archiv_teile:
        os.makedirs(os.path.dirname(archiv) or ".", exist_ok=True)
        kurse = pd.concat(archiv_teile, ignore_index=True)
        kurse["ticker"] = kurse["ticker"].astype("category")
        kurse.to_parquet(archiv, compression="zstd", index=False)
        stand["quellen"]["kurse"]["archiv_zeilen"] = int(len(kurse))
        with open(pfad_stand, "w", encoding="utf-8") as f:
            json.dump(stand, f, ensure_ascii=False, indent=1)
    if not leise:
        print(f"Scanner-Daten: {len(tabelle)} Aktien, Handelstag {handelstag}, Status {stand['status']}, "
              f"{stand['dauer_s']} s")
        for kennung, t in treffer.items():
            print(f"  {t['name']}: {t['streng']} streng, {t['nur_toleranz']} nur mit Toleranz, "
                  f"{t['handelbar']} davon handelbar"
                  + (f", davon langweilig {t['handelbar_langweilig']}" if "handelbar_langweilig" in t else ""))
        print("  Quellen: " + "; ".join(f"{k} {v.get('status')}" for k, v in stand["quellen"].items()))
    return stand


# ---------------------------------------------------------------------------
# Selbsttest (ohne Netz)
# ---------------------------------------------------------------------------

def _kunstreihe(tage=800, start=20.0, schritt=0.0015, seed=1, streuung=0.012, beginn="2023-06-01"):
    rng = np.random.default_rng(seed)
    renditen = schritt + rng.normal(0, streuung, tage)
    close = start * np.cumprod(1 + renditen)
    offen = close * (1 + rng.normal(0, 0.004, tage))
    hoch = np.maximum(close, offen) * (1 + np.abs(rng.normal(0, 0.008, tage)))
    tief = np.minimum(close, offen) * (1 - np.abs(rng.normal(0, 0.008, tage)))
    vol = rng.integers(200_000, 900_000, tage).astype(float)
    tage_idx = pd.bdate_range(beginn, periods=tage)
    return pd.DataFrame({"datetime": tage_idx, "open": offen, "high": hoch, "low": tief, "close": close, "volume": vol})


def selbsttest() -> int:
    import tempfile
    import pattern_scanner as ps
    fehler = []

    def p(name, ok, zusatz=""):
        print(f"  {'ok  ' if ok else 'FEHL'} {name}" + (f"; {zusatz}" if zusatz else ""))
        if not ok:
            fehler.append(name)

    print("Scanner-Daten, Selbsttest")

    # Kurs-Kennzahlen an einer handgebauten Reihe
    tage = pd.bdate_range("2026-01-01", periods=300)
    close = np.linspace(10.0, 40.0, 300)
    d = pd.DataFrame({"datetime": tage, "open": close * 0.99, "high": close * 1.02, "low": close * 0.97,
                      "close": close, "volume": np.full(300, 1000.0)})
    d.loc[299, ["open", "close", "high", "low"]] = [38.0, 41.0, 41.5, 37.5]
    d.loc[298, "close"] = 39.0
    d.loc[150, "volume"] = 99999.0
    ex = extrema(d)
    w = kurs_werte(d, ex)
    p("Veraenderung zum Vortag", w["veraenderung_pct"] == round((41.0 / 39.0 - 1) * 100, 2), str(w["veraenderung_pct"]))
    p("Seit Eroeffnung", w["seit_eroeffnung_pct"] == round((41.0 / 38.0 - 1) * 100, 2), str(w["seit_eroeffnung_pct"]))
    p("Red to Green: unter dem Vortag eroeffnet, darueber geschlossen", w["red_to_green"] is True)
    p("Tagesspanne des letzten Tages", w["tagesspanne_pct"] == round((41.5 / 37.5 - 1) * 100, 2), str(w["tagesspanne_pct"]))
    ema21 = float(d["close"].ewm(span=21, adjust=False).mean().iloc[-1])
    p("EMA 21 und Abstand", abs(w["ema21"] - round(ema21, 4)) < 1e-9 and w["abst_ema21_pct"] == _pct(41.0, ema21))
    p("Abstand zum Hoch eines Tages ist Schluss gegen Tageshoch", w["abst_hoch_1t_pct"] == _pct(41.0, 41.5))
    p("Allzeithoch aus der ganzen Historie", ex["allzeithoch"] == 41.5 and w["hoch_allzeit"] is True)
    p("Groesstes Volumen jemals mit Abstand in Handelstagen",
      ex["volumen_max"] == 99999.0 and w["volumen_max_tage_her"] == 149, str(w["volumen_max_tage_her"]))
    p("Neues 52-Wochen-Hoch erkannt", w["hoch_52w"] is True)
    p("Mittleres Volumen 50 Tage", w["volumen_50"] == 1000.0)

    # Trend Template: ohne Toleranz Wert fuer Wert wie pattern_scanner
    gleich = 0
    for seed in range(40):
        di = ps.add_indicators(_kunstreihe(seed=seed, schritt=0.0004 * (seed % 5) - 0.0003))
        for rs in (None, 40.0, 70.0, 95.0):
            a = trend_template(di, rs, 0.0)
            b = ps.check_trend_template(di, rs)
            gleich += int(a[0] == b[0] and a[1] == b[1])
    p("Trend Template ohne Toleranz gleich pattern_scanner (160 Faelle)", gleich == 160, str(gleich))

    # Toleranz: ein knapp verfehltes Kriterium wird mit 5 Prozent erfuellt
    di = ps.add_indicators(_kunstreihe(seed=3, schritt=0.002, streuung=0.004))
    rs_knapp = ps.CFG["tt_rs_min"] * 0.97
    streng, _n1 = trend_template(di, rs_knapp, 0.0)
    locker, _n2 = trend_template(di, rs_knapp, 0.05)
    p("RS 3 Prozent unter der Schwelle: streng nein, mit Toleranz ja", (not streng) and locker, f"{streng} {locker}")
    vorher = {k: ps.CFG[k] for k in PS_MIN + PS_MAX}
    frische = ZENTRAL["darvas"]["frische_max_tage"]
    try:
        with cfg_toleranz(0.05) as v2:
            gelockert_ok = (ps.CFG["tt_min_above_low"] < vorher["tt_min_above_low"]
                            and ps.CFG["htf_max_pole_days"] == vorher["htf_max_pole_days"] + math.floor(vorher["htf_max_pole_days"] * 0.05)
                            and ZENTRAL["darvas"]["frische_max_tage"] > frische
                            and v2["cup_max_depth"] > 0.6)
            raise RuntimeError("Probe")
    except RuntimeError:
        pass
    p("Toleranz lockert die Schwellen", gelockert_ok)
    p("Toleranz stellt alles wieder her, auch nach einem Fehler",
      all(ps.CFG[k] == v for k, v in vorher.items()) and ZENTRAL["darvas"]["frische_max_tage"] == frische)

    # Power-Gap auf der Tageskerze
    g = _kunstreihe(seed=5, tage=120, streuung=0.003)
    prev = float(g["close"].iloc[-2])
    g.loc[g.index[-1], ["open", "low", "high", "close", "volume"]] = [prev * 1.10, prev * 1.08, prev * 1.20,
                                                                      prev * 1.19, float(g["volume"].iloc[-51:-1].mean()) * 6]
    pg = power_gap(g)
    p("Power-Gap erkannt, Kaufpunkt Tageshoch plus 1 Cent", pg is not None and pg["kaufpunkt"] == round(prev * 1.20 + 0.01, 2))
    g.loc[g.index[-1], "low"] = prev * 0.99
    p("Power-Gap ohne verteidigte Luecke abgelehnt", power_gap(g) is None)

    # Muster und Rating einer Aktie
    werte_m = kurs_werte(_kunstreihe(seed=2), extrema(_kunstreihe(seed=2)))
    m = muster_werte(_kunstreihe(seed=2), 80.0, werte_m)
    p("Mustertabelle hat fuer jede Strategie sechs Felder",
      all(f"{f}_{k}" in m for k, _n, _t in STRATEGIEN for f in ("m", "kp", "stop", "status", "rating", "grund")))
    p("Trefferstufen nur 0, 1 oder 2", all(m[f"m_{k}"] in (0, 1, 2) for k, _n, _t in STRATEGIEN))
    stark_w = {"abst_hoch_1j_pct": -1.0, "abst_hoch_allzeit_pct": -1.0, "abst_tief_1j_pct": 150.0,
               "jahresspanne": 3.2, "volatilitaet_20_pct": 5.0, "dollarvolumen_50": 8e7, "vdu": 0.5,
               "atr_verhaeltnis": 0.45, "vol_spitze_10": 3.0, "ma200_steigt_tage": 120}
    schwach_w = {"abst_hoch_1j_pct": -30.0, "abst_hoch_allzeit_pct": -60.0, "abst_tief_1j_pct": 10.0,
                 "jahresspanne": 1.2, "volatilitaet_20_pct": 1.0, "dollarvolumen_50": 2e6, "vdu": 1.3,
                 "atr_verhaeltnis": 1.2, "vol_spitze_10": 1.0, "ma200_steigt_tage": 0}
    b_stark = {**grund_bausteine(stark_w, 97), "nachfrage": 1.0, "box": 1.0, "muster": 1.0}
    b_schwach = {**grund_bausteine(schwach_w, 40), "nachfrage": 0.0, "box": 0.0, "muster": 0.3}
    r_hoch, grund_hoch = rating_aus("darvas", b_stark, True)
    r_tief, grund_tief = rating_aus("darvas", b_schwach, False)
    p("Rating: starker Treffer oben, schwacher unten, beide im Bereich 0 bis 100",
      0 <= r_tief < r_hoch <= 100 and r_hoch == 100 and r_tief == 0, f"{r_hoch} gegen {r_tief}")
    p("Rating: Begruendung nennt starke und schwache Bausteine",
      (grund_hoch or "").startswith("stark: ") and (grund_tief or "").startswith("schwach: "), f"{grund_hoch}; {grund_tief}")
    mittel = {**grund_bausteine({**stark_w, "vdu": 0.8, "dollarvolumen_50": 2e7}, 80), "nachfrage": 0.5, "muster": 0.6}
    p("Rating: streng schlaegt Toleranz um den Abzug",
      rating_aus("vcp", mittel, True)[0] - rating_aus("vcp", mittel, False)[0] == SC["rating"]["toleranz_abzug"])
    p("Rating: ohne jeden Baustein kein Rating", rating_aus("vcp", {}, True) == (None, None))
    p("Rampe steigt und faellt", abs(_rampe(82.5, 70, 95) - 0.5) < 1e-9 and abs(_rampe(0.8, 1.0, 0.6) - 0.5) < 1e-9
      and _rampe(200, 70, 95) == 1.0 and _rampe(0.2, 1.0, 0.6) == 1.0)
    p("Boxhoehe in Tagesspannen: ideal 2 bis 8, null unter 1,5",
      _box_baustein(4.0) == 1.0 and _box_baustein(1.2) == 0.0 and _box_baustein(1.75) == 0.5 and _box_baustein(13) == 0.0)
    lw, gruende = langweilig({"jahresspanne": 1.4, "volatilitaet_20_pct": 1.5}, 26.0)
    p("Langeweile-Sperre: Jahresspanne, Tagesspanne und zu tiefe Box", lw and len(gruende) == 3, "; ".join(gruende))
    lw3, gruende3 = langweilig({"jahresspanne": 2.5, "volatilitaet_20_pct": 3.0}, 4.0)
    p("Langeweile-Sperre: Box kaum hoeher als anderthalb Tagesspannen", lw3 and len(gruende3) == 1, "; ".join(gruende3))
    lw2, _g = langweilig({"jahresspanne": 2.6, "volatilitaet_20_pct": 4.0}, 12.0)
    p("Lebendige Aktie mit ordentlicher Box ist nicht langweilig", not lw2)
    p("Handelbar erst ab 10 Dollar, 10 Millionen Tagesumsatz und einem Jahr Historie",
      handelbar({"kurs": 12.0, "dollarvolumen_50": 2e7}, {"historie_gesamt_tage": 300})
      and not handelbar({"kurs": 8.0, "dollarvolumen_50": 2e7}, {"historie_gesamt_tage": 300})
      and not handelbar({"kurs": 12.0, "dollarvolumen_50": 2e7}, {"historie_gesamt_tage": 100}))
    p("Mindestdauern: 5 Prozent abgerundet (35 Tage ergeben einen Tag)",
      _gelockert("cup_min_len", 35, 0.05, "min") == 34 and _gelockert("cup_max_len", 130, 0.05, "max") == 136
      and _gelockert("cup_min_len", 3, 0.05, "min") == 3)

    # Fundament
    reihen = {"umsatz": {"Q": []}, "eps_verwaessert": {"Q": []}, "bruttogewinn": {"Q": []}}
    enden = ["2024-06-30", "2024-09-30", "2024-12-31", "2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31",
             "2026-03-31", "2026-06-30"]
    for i, e in enumerate(enden):
        start = (date.fromisoformat(e) - timedelta(days=90)).isoformat()
        reihen["umsatz"]["Q"].append((start, e, 100.0 + 10 * i, "amtlich", "us-gaap"))
        reihen["eps_verwaessert"]["Q"].append((start, e, 1.0 + 0.1 * i, "amtlich", "us-gaap"))
        reihen["bruttogewinn"]["Q"].append((start, e, (100.0 + 10 * i) * (0.40 + 0.01 * i), "amtlich", "us-gaap"))
    reihen["bilanzsumme"] = {"B": [(None, "2026-06-30", 1000.0, "amtlich", "us-gaap")]}
    reihen["eigenkapital"] = {"B": [(None, "2026-06-30", 400.0, "amtlich", "us-gaap")]}
    reihen["langfristige_schulden"] = {"B": [(None, "2026-06-30", 200.0, "amtlich", "us-gaap")]}
    reihen["kurzfristige_schulden"] = {"B": [(None, "2026-06-30", 50.0, "amtlich", "us-gaap")]}
    reihen["aktien_ausstehend"] = {"B": [(None, "2026-07-20", 5e6, "amtlich", "dei")]}
    fw = fundament_werte(reihen, heute=date(2026, 9, 14))
    p("Umsatz q/q: Quartal gegen Vorjahresquartal", fw["umsatz_q_vj_pct"] == _pct(180.0, 140.0), str(fw["umsatz_q_vj_pct"]))
    p("Umsatz sequenziell: gegen das Vorquartal", fw["umsatz_seq_pct"] == _pct(180.0, 170.0), str(fw["umsatz_seq_pct"]))
    p("Umsatz y/y: vier Quartale gegen die vier davor",
      fw["umsatz_ttm_pct"] == _pct(150 + 160 + 170 + 180, 110 + 120 + 130 + 140), str(fw["umsatz_ttm_pct"]))
    p("EPS q/q", fw["eps_q_vj_pct"] == _pct(1.8, 1.4), str(fw["eps_q_vj_pct"]))
    p("Bruttomarge und ihre Entwicklung in Prozentpunkten",
      fw["bruttomarge_pct"] == 48.0 and fw["bruttomarge_q_vj_pp"] == 4.0 and fw["bruttomarge_seq_pp"] == 1.0,
      f"{fw['bruttomarge_pct']} {fw['bruttomarge_q_vj_pp']} {fw['bruttomarge_seq_pp']}")
    p("Bilanz: Schulden zu Eigenkapital, Quoten", fw["schulden_zu_ek"] == 0.625 and fw["ek_quote_pct"] == 40.0
      and fw["fk_quote_pct"] == 60.0 and fw["schulden_zu_vermoegen_pct"] == 25.0,
      f"{fw['schulden_zu_ek']} {fw['ek_quote_pct']} {fw['fk_quote_pct']} {fw['schulden_zu_vermoegen_pct']}")
    p("Ausstehende Aktien", fw["aktien_ausstehend"] == 5e6 and fw["aktien_stand"] == "2026-07-20")
    lang = {"eps_verwaessert": {"Q": [("2025-03-30", "2025-07-05", 1.4, "amtlich", "us-gaap"),
                                      ("2026-03-29", "2026-07-04", 1.4, "amtlich", "us-gaap")]}}
    p("14-Wochen-Quartal wird auf 13 Wochen umgerechnet (W7)",
      fundament_werte(lang, heute=date(2026, 9, 14))["eps_q_vj_pct"] == 0.0)
    p("Leere Reihen ergeben nur leere Werte", all(v is None for v in fundament_werte({}, date(2026, 9, 14)).values()))

    # Nasdaq-Antworten, an echten Antworten vom 14.09.2026 gebaut
    sc = screener_aus({"data": {"rows": [{"symbol": "A", "name": "Agilent", "marketCap": "41423806518.00",
                                          "country": "United States", "industry": "Labs", "sector": "Industrials"},
                                         {"symbol": "BRK/B", "marketCap": "0.00", "sector": ""}]}})
    p("Screener: Sektor und Marktkapitalisierung", sc["A"]["sektor"] == "Industrials" and sc["A"]["marktkap"] == 41423806518.0)
    p("Screener: Schraegstrich wird Punkt, null ist unbekannt", "BRK.B" in sc and sc["BRK.B"]["marktkap"] is None
      and sc["BRK.B"]["sektor"] is None)
    kal = kalender_aus({"2026-09-15": {"data": {"rows": [{"symbol": "ORCL", "time": "time-after-hours"}]}},
                        "2026-09-14": {"data": {"rows": [{"symbol": "ORCL", "time": "time-pre-market"},
                                                         {"symbol": "X", "time": "time-not-supplied"}]}}})
    p("Kalender: der frueheste Termin gewinnt, Tageszeit uebersetzt",
      kal["ORCL"] == ("2026-09-14", "vorboerslich") and kal["X"][1] == "unbekannt")
    an = analysten_aus({"data": {"consensusOverview": {"lowPriceTarget": 245.0, "highPriceTarget": 400.0,
                                                       "priceTarget": 335.87, "buy": 16, "sell": 4, "hold": 10},
                                 "historicalConsensus": [{"z": {"consensus": "Buy"}}]}})
    p("Analysten: Empfehlungen, Anteil, Konsens und Kursziel",
      an["analysten_anzahl"] == 30 and an["analysten_kauf_anteil_pct"] == 53.3 and an["konsens"] == "Kaufen"
      and an["konsens_wert"] == 4 and an["kursziel"] == 335.87, str(an))
    p("Analysten: ohne Abdeckung None", analysten_aus({"data": None}) is None)
    neutral = analysten_aus({"data": {"consensusOverview": {"buy": 6, "hold": 22, "sell": 2, "priceTarget": 116.12},
                                      "historicalConsensus": [{"z": {"consensus": "Buy"}}, {"z": {"consensus": "Neutral"}}]}})
    p("Analysten: Nasdaqs Neutral heisst Halten, der juengste Eintrag gilt",
      neutral["konsens"] == "Halten" and neutral["konsens_wert"] == 3, str(neutral))
    ue = ueberraschungen_aus({"data": {"earningsSurpriseTable": {"rows": [
        {"dateReported": "7/30/2026", "eps": 1.91, "consensusForecast": "1.88", "percentageSurprise": "1.6"},
        {"dateReported": "4/30/2026", "eps": 2.01, "consensusForecast": "1.92", "percentageSurprise": "4.69"},
        {"dateReported": "1/29/2026", "eps": 2.4, "consensusForecast": "2.65", "percentageSurprise": "-9.4"},
        {"dateReported": "10/30/2025", "eps": 1.85, "consensusForecast": "1.73", "percentageSurprise": "6.94"}]}}})
    p("Ueberraschungen: drei von vier geschlagen, juengster Bericht",
      ue["quartale_mit_schaetzung"] == 4 and ue["schaetzung_geschlagen"] == 3 and ue["letzter_bericht"] == "2026-07-30"
      and ue["letzte_ueberraschung_pct"] == 1.6, str(ue))

    # Rotation
    alle = [f"T{i}" for i in range(700)]
    faecher = [set(rotation_auswahl(alle, date(2026, 9, 14) + timedelta(days=k), 7)) for k in range(7)]
    p("Rotation: jede Aktie genau einmal in sieben Naechten",
      sum(len(f) for f in faecher) == 700 and set().union(*faecher) == set(alle))

    # Viele Abrufe: Abbruch bei zu vielen Fehlern
    erg, fe, ab = viele_abrufe([f"T{i}" for i in range(200)], lambda t: (False, None, None), 2, 0.25, 40)
    p("Viele Abrufe hoeren bei zu vielen Fehlern auf", ab and len(erg) < 200, f"{len(erg)} geprueft")

    # Ganzer Lauf ohne Netz
    with tempfile.TemporaryDirectory() as tmp:
        kunst = {"AAA": _kunstreihe(seed=11, schritt=0.002), "BBB": _kunstreihe(seed=12, schritt=-0.001),
                 "CCC": _kunstreihe(seed=13, tage=40)}
        abrufe = []

        def je(t):
            abrufe.append(t)
            return True, analysten_aus({"data": {"consensusOverview": {"buy": 3, "hold": 1, "sell": 0,
                                                                       "priceTarget": 30.0}}}), None

        pfad_a = os.path.join(tmp, "a.parquet")
        st = bauen(pfad_tabelle=os.path.join(tmp, "t.parquet"), pfad_stand=os.path.join(tmp, "s.json"),
                   archiv=os.path.join(tmp, "k.parquet"), analysten="alle", heute=date(2026, 9, 14),
                   universum_liste=[{"symbol": s, "name": s + " Inc", "boerse": "Nasdaq"} for s in kunst],
                   kurse_download=lambda teil: {s: kunst[s] for s in teil if s in kunst},
                   rs_daten={"status": "ok", "aktien": {"AAA": {"rs": 90, "linie_spy_hoch": True,
                                                               "linie_qqq_hoch": False, "linie_qqq_abst_pct": -1.5}},
                             "listen": {"AAA": {"rs": 90, "linie_spy_hoch": True, "linie_qqq_hoch": False,
                                                "linie_qqq_abst_pct": -1.5}}},
                   ratings={"aktien": {}}, termine_listen={"aktien": {"AAA": {"datum": "2026-09-15", "lage": "nachboerslich"}}},
                   screener={"AAA": {"sektor": "Technology", "branche": "Software", "land": "United States", "marktkap": 3e8}},
                   kalender={"BBB": ("2026-09-14", "vorboerslich")}, je_aktie=je, kennzahlen=pd.DataFrame(), leise=True,
                   pfad_analysten=pfad_a)
        t = pd.read_parquet(os.path.join(tmp, "t.parquet"))
        a = pd.read_parquet(pfad_a)
        p("Ganzer Lauf: drei Zeilen, Stand geschrieben", len(t) == 3 and st["zeilen"] == 3)
        aaa = t[t["ticker"] == "AAA"].iloc[0]
        p("Ganzer Lauf: Marktkapitalisierung in Milliarden, Sektor, Wochenliste",
          aaa["marktkap_mrd"] == 0.3 and aaa["sektor"] == "Technology" and bool(aaa["in_wochenliste"]))
        p("Ganzer Lauf: Termin der Wochenliste und Nasdaq-Termin",
          aaa["termin_quelle"] == "Wochenliste" and t[t["ticker"] == "BBB"].iloc[0]["termin_lage"] == "vorboerslich")
        p("Ganzer Lauf: RS-Linien gegen SPY und QQQ in der Tabelle",
          bool(aaa["rs_linie_hoch"]) and not bool(aaa["rs_linie_qqq_hoch"]) and aaa["rs_linie_qqq_abst_pct"] == -1.5)
        a_aaa = a[a["ticker"] == "AAA"].iloc[0]
        p("Ganzer Lauf: Analysten in eigener Datei, Stand heute, Kursziel-Abstand",
          a_aaa["analysten_anzahl"] == 4 and a_aaa["analysten_stand"] == "2026-09-14"
          and a_aaa["kursziel_abst_pct"] is not None and len(a) == 3)
        p("Ganzer Lauf: die oeffentliche Tabelle traegt keine Nasdaq-Werte je Aktie",
          not any(s in t.columns for s in ANALYSTEN_FELDER + UEBERRASCHUNG_FELDER + ("kursziel_abst_pct",)))
        p("Ganzer Lauf: Bauzeit mit Zeitzone", str(st["gebaut_am"]).endswith("+00:00"), str(st["gebaut_am"]))
        p("Ganzer Lauf: Kursarchiv mit Eroeffnung geschrieben",
          os.path.exists(os.path.join(tmp, "k.parquet"))
          and "open" in pd.read_parquet(os.path.join(tmp, "k.parquet")).columns)
        p("Ganzer Lauf: kurze Historie ohne Muster", int(t[t["ticker"] == "CCC"].iloc[0]["m_darvas"]) == 0)
        st2 = bauen(pfad_tabelle=os.path.join(tmp, "t.parquet"), pfad_stand=os.path.join(tmp, "s.json"),
                    archiv=None, analysten="aus", heute=date(2026, 9, 15),
                    universum_liste=[{"symbol": s, "name": s, "boerse": "Nasdaq"} for s in kunst],
                    kurse_download=lambda teil: {s: kunst[s] for s in teil if s in kunst},
                    rs_daten={}, ratings={}, termine_listen={}, screener={}, kalender={}, kennzahlen=pd.DataFrame(),
                    leise=True, pfad_analysten=pfad_a)
        a2 = pd.read_parquet(pfad_a)
        p("Zweite Nacht ohne Abruf behaelt die Analysten der ersten",
          a2[a2["ticker"] == "AAA"].iloc[0]["analysten_anzahl"] == 4 and st2["quellen"]["analysten"]["status"] == "aus")

    quelle = open(__file__, encoding="utf-8").read()
    p("Keine Vernetzung: kein Sendecode, keine Alarmdateien",
      all(x not in quelle for x in ("NTFY_" + "TOPIC", "ntfy." + "sh", "breakout_" + "watcher", "traderfox_" + "alarm",
                                    "kaufpunkte_" + "aktuell")))

    print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles bestanden.")
    return 1 if fehler else 0


def main():
    ap = argparse.ArgumentParser(description="Nachttabelle fuer den Scanner der Heliot-App")
    ap.add_argument("--bauen", action="store_true")
    ap.add_argument("--selbsttest", action="store_true")
    ap.add_argument("--grenze", type=int, default=0, help="nur die ersten N Aktien (Probelauf)")
    ap.add_argument("--analysten", choices=("rotation", "alle", "aus"), default="rotation")
    args = ap.parse_args()
    if args.selbsttest:
        return selbsttest()
    if args.bauen:
        stand = bauen(grenze=args.grenze or None, analysten=args.analysten)
        return 0 if stand.get("zeilen") else 1
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
