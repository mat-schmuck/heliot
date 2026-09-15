#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TECHNISCHE KENNZAHLEN JE AKTIE (Etappe 2, Entscheidungen 4 und 5)
=================================================================
Gerhard, 13.09.2026, woertlich: "ALLE 17 aus Gruppe A, ABER OHNE PUNKT 17.
Die neuen Kurs-Setups nach Minervini und Qullamaggie sind keine Kennzahlen
sondern neue Kaufmuster ... Also 16 Kennzahlen." Und zu Entscheidung 5:
"NUR ANZEIGEN. Keine der neuen Kennzahlen filtert, auch ADR nicht, obwohl es
bei Qullamaggie ein Filter ist. Filtern bleibt Regelwerk."

Dieses Modul RECHNET NUR, auf einfachen Listen, chronologisch (aelteste
zuerst), in der Form von rs_universum.kurse_holen: {"daten", "open", "high",
"low", "close", "volume"}. Es liest keine Datei, holt nichts aus dem Netz und
filtert nichts. Grundlage ist das Recherche-Papier vom 13.09.2026, Teil 4.1;
die Nummern unten sind die dortigen.

DIE 16 KENNZAHLEN
   1  ADR nach Qullamaggie: fuer jeden der letzten 20 Tage Hoch geteilt durch
      Tief, davon das Mittel, minus 1, mal 100.
   2  ATR 14 nach Wilder: wahre Tagesspanne (groesster Wert aus Hoch minus
      Tief, Betrag Hoch minus Vortagsschluss, Betrag Tief minus
      Vortagsschluss), geglaettet nach Wilder ueber 14 Tage, in Dollar; die
      Anzeige nennt dazu den Anteil am Kurs.
   3  Up/Down Volume Ratio nach IBD: Volumen der Plus-Tage der letzten 50
      Handelstage geteilt durch das Volumen der Minus-Tage.
   4  A/D-Naeherung, verbessert: je Tag (Schluss minus Tief minus (Hoch minus
      Schluss)) geteilt durch (Hoch minus Tief), mal Tagesvolumen, ueber 65
      Tage summiert und durch das Gesamtvolumen geteilt (Chaikin). Ersetzt in
      rs_universum die reine Plus-Minus-Zaehlung; ad_roh und ad_rang bleiben.
   5  Mansfield RS nach Weinstein, woechentlich gegen SPY: Relation Kurs zu
      Index, geteilt durch ihren 52-Wochen-Schnitt, minus 1, mal 100.
      Steigend heisst hoeher als vor vier Wochen.
   6  Weinstein-Stufe 1 bis 4 nach festen Regeln, siehe weinstein().
   7  Momentum Burst nach Stockbee (Schluss mindestens 4 Prozent ueber dem
      Vortag, Volumen ueber dem Vortag und mindestens 100.000 Stueck; die
      Schlusslage in der Tagesspanne und der Vortag stehen als Zahlen dabei)
      und Episodic Pivot (Eroeffnungsluecke ab 10 Prozent, der
      Volumenfaktor steht als Zahl dabei).
   8  Wertentwicklung ueber 1 Woche, 1, 3, 6 und 12 Monate und seit
      Jahresbeginn, wie bei Finviz. GEMESSEN 14.09.2026 an AAPL, NVDA, MSFT,
      IBM und AAOI: Finviz nimmt fuer Woche, Monat, Quartal und Halbjahr den
      Schluss vor 5, 21, 63 und 126 Handelstagen, fuer das Jahr den letzten
      Schluss am oder vor demselben Kalendertag ein Jahr frueher (25 von 25
      Bezugskursen gleich; mit 252 Handelstagen fuer das Jahr nur 20).
   9  Volatilitaet wie bei Finviz: dieselbe Rechnung wie die ADR (Punkt 1),
      ueber 5 und 21 Tage. GEMESSEN 14.09.2026 an denselben fuenf Aktien:
      Woche und Monat stimmen auf die Hundertstel, der Monat aber nur mit 21
      Tagen; die ADR nach Qullamaggie bleibt bei 20 Tagen.
  10  Abstand zu SMA 20, 50 und 200; Abstand zum 50-Tage-Hoch und -Tief;
      Abstand zum 52-Wochen-Tief.
  11  Eroeffnungsluecke und Veraenderung seit Eroeffnung am letzten Tag.
  12  Beta gegen SPY ueber 252 Tagesrenditen.
  13  RSI 14 und RSI 2 nach Wilder.
  14  Durchschnittsvolumen ueber 63 Tage und Dollarvolumen ueber 20 Tage.
  15  RS-Aenderung ueber eine und vier Wochen aus dem RS-Verlauf
      (rs_aenderung, gerechnet in rs_universum.bauen nach dem Ranking).
  16  Allzeithoch fuer das ganze Universum (allzeithoch, der Abruf der
      ganzen Historie steht in rs_universum).

Fehlt eine Grundlage (zu kurze Historie, fehlender Index, kein Volumen),
steht der Wert als None da; geschaetzt wird nichts.

UNBEREINIGTER SPLIT (Befund am echten Lauf vom 14.09.2026): Yahoo rechnet
einen Split oder Reverse-Split mitunter erst einen Tag spaeter in die
Historie ein. Am Tag selbst steht dann der neue Kurs neben lauter alten; bei
OPTT sprang der Schluss von 0,196 auf 2,605 Dollar, die "Eroeffnungsluecke"
betrug 1.548 Prozent. Yahoo selbst fuehrte fuer alle sechs betroffenen Titel
einen Split mit Datum 14.09.2026 (OPTT 1 zu 30, NRSN 1 zu 20, CPOP 1 zu 15,
IPDN 1 zu 30, HUBC 1 zu 25, NXXT 1 zu 10). Solche Tage erkennt
split_verdacht(); technik() nennt dann nur den Verdacht und keine Kennzahl,
lieber nicht verfuegbar als falsch.

Aufruf:
  python kennzahlen_technik.py --selbsttest     ohne Netz
"""

import argparse
import sys
from datetime import date

from config import CFG

CFGT = CFG["technik"]


# ---------------------------------------------------------------------------
# Hilfen
# ---------------------------------------------------------------------------

def _ok(x):
    """Eine brauchbare Zahl: nicht None und nicht NaN."""
    return x is not None and x == x


def _pct(neu, alt, stellen=1):
    """Veraenderung in Prozent, gerundet; None ohne Grundlage."""
    if not (_ok(neu) and _ok(alt)) or alt <= 0:
        return None
    return round((neu / alt - 1.0) * 100.0, stellen)


def _dollar(x):
    """Betraege unter 10 Dollar mit vier Stellen (Pennystocks), sonst zwei."""
    if not _ok(x):
        return None
    return round(x, 4) if abs(x) < 10 else round(x, 2)


_WOCHE = {}


def _woche(tag):
    """(Jahr, Kalenderwoche) nach ISO fuer '2026-09-11'; zwischengespeichert,
    weil alle Aktien dieselben Tage tragen."""
    w = _WOCHE.get(tag)
    if w is None:
        j, kw, _ = date.fromisoformat(str(tag)[:10]).isocalendar()
        w = _WOCHE[tag] = (j, kw)
    return w


def _tage_zwischen(a, b):
    return (date.fromisoformat(str(b)[:10]) - date.fromisoformat(str(a)[:10])).days


# ---------------------------------------------------------------------------
# Die Kennzahlen
# ---------------------------------------------------------------------------

def adr(highs, lows, tage):
    """Punkte 1 und 9: Mittel von Hoch durch Tief ueber die letzten tage
    Handelstage, minus 1, in Prozent. Tage ohne brauchbares Hoch und Tief
    zaehlen nicht; fehlt mehr als ein Viertel davon, gibt es keinen Wert."""
    if len(highs) < tage or len(lows) < tage:
        return None
    q = [h / l for h, l in zip(highs[-tage:], lows[-tage:]) if _ok(h) and _ok(l) and l > 0]
    if len(q) < tage * 0.75:
        return None
    return round((sum(q) / len(q) - 1.0) * 100.0, 2)


def atr(highs, lows, closes, tage):
    """Punkt 2: ATR nach Wilder in Dollar. Der erste Wert ist das Mittel der
    ersten tage wahren Spannen, danach (vorher mal (tage minus 1) plus neu)
    geteilt durch tage. Braucht tage plus einen Schlusskurs."""
    n = len(closes)
    if n < tage + 1:
        return None
    tr = []
    for i in range(1, n):
        h, l, c1 = highs[i], lows[i], closes[i - 1]
        if not (_ok(h) and _ok(l) and _ok(c1)):
            continue
        tr.append(max(h - l, abs(h - c1), abs(l - c1)))
    if len(tr) < tage:
        return None
    wert = sum(tr[:tage]) / tage
    for x in tr[tage:]:
        wert = (wert * (tage - 1) + x) / tage
    return _dollar(wert)


def updown(closes, volumes, tage):
    """Punkt 3: Volumen der Plus-Tage geteilt durch Volumen der Minus-Tage
    ueber die letzten tage Handelstage. Ohne einen einzigen Minus-Tag gibt es
    keinen Quotienten (None)."""
    if len(closes) < tage + 1:
        return None
    plus = minus = 0.0
    c, v = closes[-tage - 1:], volumes[-tage:]
    for i in range(1, len(c)):
        vol = v[i - 1] if _ok(v[i - 1]) else 0.0
        if not (_ok(c[i]) and _ok(c[i - 1])):
            continue
        if c[i] > c[i - 1]:
            plus += vol
        elif c[i] < c[i - 1]:
            minus += vol
    if minus <= 0:
        return None
    return round(plus / minus, 2)


def ad_chaikin(closes, highs, lows, volumes, tage):
    """Punkt 4: Akkumulation und Distribution nach Chaikin als Anteil, minus 1
    bis plus 1. Ein Tag ohne Spanne (Hoch gleich Tief) traegt nichts bei,
    sein Volumen zaehlt aber zum Gesamtvolumen."""
    if len(closes) < tage:
        return None
    gesamt = saldo = 0.0
    for c, h, l, v in zip(closes[-tage:], highs[-tage:], lows[-tage:], volumes[-tage:]):
        if not _ok(v) or v <= 0:
            continue
        gesamt += v
        if _ok(c) and _ok(h) and _ok(l) and h > l:
            saldo += ((c - l) - (h - c)) / (h - l) * v
    if gesamt <= 0:
        return None
    return saldo / gesamt


def wochenschluesse(daten, closes):
    """Letzter Schlusskurs je Kalenderwoche nach ISO, chronologisch: Liste von
    (Woche, letzter Tag, Schluss). Die laufende Woche zaehlt mit ihrem
    bisherigen Schluss."""
    raus = []
    for t, c in zip(daten, closes):
        if not _ok(c):
            continue
        w = _woche(t)
        if raus and raus[-1][0] == w:
            raus[-1] = (w, t, c)
        else:
            raus.append((w, t, c))
    return raus


def mansfield(daten, closes, v_daten, v_closes, wochen, zurueck):
    """Punkt 5: (Mansfield RS heute, Mansfield RS vor zurueck Wochen), je auf
    zwei Stellen. Die Relation Kurs zu Index entsteht nur an Tagen, die beide
    haben; ihr Wochenschluss ist der letzte gemeinsame Tag der Woche."""
    if not v_daten:
        return None, None
    idx = {t: c for t, c in zip(v_daten, v_closes) if _ok(c) and c > 0}
    rel_d, rel_c = [], []
    for t, c in zip(daten, closes):
        i = idx.get(t)
        if i and _ok(c):
            rel_d.append(t)
            rel_c.append(c / i)
    ws = [x[2] for x in wochenschluesse(rel_d, rel_c)]

    def bei(ende):
        if ende < wochen:
            return None
        teil = ws[ende - wochen:ende]
        schnitt = sum(teil) / wochen
        return round((teil[-1] / schnitt - 1.0) * 100.0, 2) if schnitt > 0 else None
    return bei(len(ws)), bei(len(ws) - zurueck)


def weinstein(daten, closes, linie, zurueck, flach_pct, vorlauf):
    """Punkt 6: die Stufe nach Weinstein, nach festen Regeln. Rueckgabe
    {"stufe", "linie_abst", "linie_steig"}:
      linie_steig  Veraenderung der 30-Wochen-Linie ueber zurueck Wochen in
                   Prozent; steigend ueber plus flach_pct, fallend unter minus
                   flach_pct, dazwischen flach.
      Stufe 2      Linie steigend, die letzten zwei Wochenschluesse ueber
                   der Linie ihrer Woche.
      Stufe 4      spiegelbildlich: Linie fallend, zwei Schluesse darunter.
      Stufe 3      Linie flach, davor (vorlauf Wochen) gestiegen.
      Stufe 1      Linie flach, davor gefallen.
      0            keine eindeutige Stufe: Die Linie steigt oder faellt, aber
                   der Kurs bestaetigt es nicht, oder die Linie war auch davor
                   flach.
    Gerhard, 15.09.2026, Nachfrage N3: "Stufe 2 und Stufe 4 nur noch aus
    30-Wochen-Linie und Kurs." Bis dahin verlangten beide zusaetzlich eine
    Mansfield RS ueber beziehungsweise unter null, steigend beziehungsweise
    fallend; am Schluss vom 14.09.2026 war damit mehr als die Haelfte der
    Aktien ohne eindeutige Stufe. Die Mansfield RS steht als eigene Zahl
    daneben.
    Ohne 30 plus zurueck Wochen gibt es keine Stufe (None)."""
    ws = [x[2] for x in wochenschluesse(daten, closes)]
    n = len(ws)
    leer = {"stufe": None, "linie_abst": None, "linie_steig": None}

    def sma(ende):
        if ende < linie:
            return None
        return sum(ws[ende - linie:ende]) / linie
    jetzt, vorwoche, vorher = sma(n), sma(n - 1), sma(n - zurueck)
    if jetzt is None or vorwoche is None or vorher is None or vorher <= 0 or jetzt <= 0:
        return leer
    steig = (jetzt / vorher - 1.0) * 100.0
    abst = (ws[-1] / jetzt - 1.0) * 100.0
    if steig > flach_pct:
        stufe = 2 if (ws[-1] > jetzt and ws[-2] > vorwoche) else 0
    elif steig < -flach_pct:
        stufe = 4 if (ws[-1] < jetzt and ws[-2] < vorwoche) else 0
    else:
        frueher = sma(n - zurueck - vorlauf)
        if frueher is None or frueher <= 0:
            stufe = 0
        else:
            davor = (vorher / frueher - 1.0) * 100.0
            stufe = 3 if davor > flach_pct else (1 if davor < -flach_pct else 0)
    return {"stufe": stufe, "linie_abst": round(abst, 1), "linie_steig": round(steig, 2)}


def momentum_burst(closes, highs, lows, volumes, burst_pct, mindestvolumen):
    """Punkt 7, erster Teil: {"burst", "schlusslage", "vortag_pct",
    "vortag_spanne"}. burst verlangt die drei harten Bedingungen nach
    Stockbee; Schlusslage (0 am Tief, 100 am Hoch) und der Vortag stehen nur
    als Zahlen dabei."""
    raus = {"burst": None, "schlusslage": None, "vortag_pct": None, "vortag_spanne": None}
    if len(closes) < 3:
        return raus
    c, c1, c2 = closes[-1], closes[-2], closes[-3]
    v, v1 = volumes[-1], volumes[-2]
    pct = _pct(c, c1, 2)
    if pct is not None and _ok(v) and _ok(v1):
        raus["burst"] = bool(pct >= burst_pct and v > v1 and v >= mindestvolumen)
    h, l = highs[-1], lows[-1]
    if _ok(h) and _ok(l) and h > l and _ok(c):
        raus["schlusslage"] = int(round(max(0.0, min(1.0, (c - l) / (h - l))) * 100))
    raus["vortag_pct"] = _pct(c1, c2)
    h1, l1 = highs[-2], lows[-2]
    if _ok(h1) and _ok(l1) and l1 > 0:
        raus["vortag_spanne"] = round((h1 / l1 - 1.0) * 100.0, 1)
    return raus


def luecke(opens, closes, volumes, pivot_pct, schnitt_tage):
    """Punkt 7, zweiter Teil, und Punkt 11: {"luecke", "seit_eroeffnung",
    "vol_faktor", "pivot"}. Der Volumenfaktor ist das Volumen des letzten
    Tages geteilt durch den Schnitt der schnitt_tage davor (mindestens zehn
    Tage). pivot heisst Eroeffnungsluecke ab pivot_pct Prozent."""
    raus = {"luecke": None, "seit_eroeffnung": None, "vol_faktor": None, "pivot": None}
    if len(closes) < 2:
        return raus
    o = opens[-1] if opens and len(opens) == len(closes) else None
    raus["luecke"] = _pct(o, closes[-2])
    raus["seit_eroeffnung"] = _pct(closes[-1], o)
    if raus["luecke"] is not None:
        raus["pivot"] = bool(raus["luecke"] >= pivot_pct)
    davor = [x for x in volumes[-schnitt_tage - 1:-1] if _ok(x)]
    if len(davor) >= min(10, schnitt_tage) and _ok(volumes[-1]):
        schnitt = sum(davor) / len(davor)
        if schnitt > 0:
            raus["vol_faktor"] = round(volumes[-1] / schnitt, 2)
    return raus


def _vor_einem_jahr(tag):
    """Derselbe Kalendertag ein Jahr frueher; aus dem 29. Februar wird der 28."""
    t = date.fromisoformat(str(tag)[:10])
    try:
        return t.replace(year=t.year - 1)
    except ValueError:
        return t.replace(year=t.year - 1, day=28)


def wertentwicklung(daten, closes, tage_je):
    """Punkt 8: {"perf_1w", ..., "perf_12m", "perf_ytd"} in Prozent. Die
    Zeitraeume aus der Einstellung: eine Zahl heisst so viele Handelstage
    zurueck, "jahr" heisst gegen den letzten Schluss am oder vor demselben
    Kalendertag ein Jahr frueher; seit Jahresbeginn heisst gegen den letzten
    Schluss des Vorjahres."""
    raus = {}
    n = len(closes)
    for name, t in tage_je.items():
        if t == "jahr":
            raus[f"perf_{name}"] = None
            if n >= 2 and daten:
                stichtag = _vor_einem_jahr(daten[-1]).isoformat()
                if str(daten[0])[:10] <= stichtag:
                    for i in range(n - 2, -1, -1):
                        if str(daten[i])[:10] <= stichtag:
                            raus[f"perf_{name}"] = _pct(closes[-1], closes[i])
                            break
            continue
        raus[f"perf_{name}"] = _pct(closes[-1], closes[-int(t) - 1]) if n > int(t) else None
    raus["perf_ytd"] = None
    if n >= 2 and daten:
        jahr = str(daten[-1])[:4]
        for i in range(n - 2, -1, -1):
            if str(daten[i])[:4] < jahr:
                raus["perf_ytd"] = _pct(closes[-1], closes[i])
                break
    return raus


def sma_abstaende(closes, tage_liste):
    """Punkt 10, erster Teil: {"sma20_abst", ...} Abstand des Schlusskurses
    zum einfachen Durchschnitt in Prozent."""
    raus = {}
    for t in tage_liste:
        teil = [x for x in closes[-t:] if _ok(x)]
        raus[f"sma{t}_abst"] = (_pct(closes[-1], sum(teil) / t)
                                if len(closes) >= t and len(teil) == t else None)
    return raus


def hoch_tief(highs, lows, closes, tage, jahr_tage=252, mindest_tage=60):
    """Punkt 10, zweiter Teil: Abstand zum Hoch und Tief der letzten tage
    Handelstage und zum 52-Wochen-Tief, je in Prozent. Das 52-Wochen-Tief
    braucht wie das 52-Wochen-Hoch in rs_universum mindestens 60 Tage."""
    raus = {"hoch50_abst": None, "tief50_abst": None, "tief52_abst": None}
    kurs = closes[-1] if closes else None
    if len(closes) >= tage:
        hs = [x for x in highs[-tage:] if _ok(x)]
        ls = [x for x in lows[-tage:] if _ok(x) and x > 0]
        if hs:
            raus["hoch50_abst"] = _pct(kurs, max(hs))
        if ls:
            raus["tief50_abst"] = _pct(kurs, min(ls))
    if len(closes) >= mindest_tage:
        ls = [x for x in lows[-jahr_tage:] if _ok(x) and x > 0]
        if ls:
            raus["tief52_abst"] = _pct(kurs, min(ls))
    return raus


def beta(daten, closes, v_daten, v_closes, tage):
    """Punkt 12: Kovarianz der Tagesrenditen von Aktie und Index geteilt durch
    die Varianz der Indexrenditen, ueber die letzten tage Renditen an Tagen,
    die beide haben."""
    if not v_daten:
        return None
    idx = {t: c for t, c in zip(v_daten, v_closes) if _ok(c) and c > 0}
    paare = [(c, idx[t]) for t, c in zip(daten, closes) if t in idx and _ok(c) and c > 0]
    if len(paare) < tage + 1:
        return None
    paare = paare[-(tage + 1):]
    ra = [paare[i][0] / paare[i - 1][0] - 1.0 for i in range(1, len(paare))]
    rb = [paare[i][1] / paare[i - 1][1] - 1.0 for i in range(1, len(paare))]
    ma, mb = sum(ra) / tage, sum(rb) / tage
    cov = sum((a - ma) * (b - mb) for a, b in zip(ra, rb))
    var = sum((b - mb) ** 2 for b in rb)
    return round(cov / var, 2) if var > 0 else None


def rsi(closes, tage):
    """Punkt 13: RSI nach Wilder. Erster Durchschnitt ueber die ersten tage
    Veraenderungen, danach (vorher mal (tage minus 1) plus neu) geteilt durch
    tage. Ohne jede Bewegung 50, nur Gewinne 100."""
    c = [x for x in closes if _ok(x)]
    if len(c) < tage + 1:
        return None
    gew = verl = 0.0
    for i in range(1, tage + 1):
        d = c[i] - c[i - 1]
        gew += max(d, 0.0)
        verl += max(-d, 0.0)
    gew, verl = gew / tage, verl / tage
    for i in range(tage + 1, len(c)):
        d = c[i] - c[i - 1]
        gew = (gew * (tage - 1) + max(d, 0.0)) / tage
        verl = (verl * (tage - 1) + max(-d, 0.0)) / tage
    if verl == 0:
        return 100.0 if gew > 0 else 50.0
    return round(100.0 - 100.0 / (1.0 + gew / verl), 1)


def volumen_schnitte(closes, volumes, volumen_tage, dollar_tage):
    """Punkt 14: {"vol63", "dv20"}; Stueck je Tag ueber volumen_tage und Dollar
    je Tag ueber dollar_tage. Beide brauchen das volle Fenster."""
    raus = {"vol63": None, "dv20": None}
    if len(volumes) >= volumen_tage:
        teil = [x for x in volumes[-volumen_tage:] if _ok(x)]
        if teil:
            raus["vol63"] = int(round(sum(teil) / volumen_tage))
    if len(volumes) >= dollar_tage:
        teil = [c * v for c, v in zip(closes[-dollar_tage:], volumes[-dollar_tage:]) if _ok(c) and _ok(v)]
        if teil:
            raus["dv20"] = int(round(sum(teil) / dollar_tage))
    return raus


def rs_aenderung(verlauf, mindest_tage):
    """Punkt 15: RS heute minus RS am juengsten Tag, der mindestens
    mindest_tage Kalendertage zurueckliegt (dieselbe Regel wie 'vor einer
    Woche' im Nachschlagen). None ohne passenden Eintrag oder ohne Wert."""
    if not verlauf or not isinstance(verlauf[-1], (list, tuple)) or len(verlauf[-1]) != 2:
        return None
    heute_tag, heute_rs = verlauf[-1]
    if heute_rs is None:
        return None
    for eintrag in reversed(verlauf[:-1]):
        if not isinstance(eintrag, (list, tuple)) or len(eintrag) != 2:
            continue
        tag, wert = eintrag
        try:
            if _tage_zwischen(tag, heute_tag) >= mindest_tage:
                return int(heute_rs) - int(wert) if wert is not None else None
        except (TypeError, ValueError):
            continue
    return None


def historie_im_fenster(daten, fenster_tage, reserve=25):
    """Liegt die ganze Historie im geladenen Fenster? Ja, wenn der erste Tag
    juenger ist als das Fenster abzueglich einer Reserve fuer Wochenenden,
    Feiertage und den Abstand zwischen Handelsschluss und Abruf. Wer so
    beginnt, hat vorher nicht gehandelt: Yahoo liefert sonst Kurse bis an
    den Anfang des verlangten Zeitraums."""
    if not daten:
        return False
    return _tage_zwischen(daten[0], daten[-1]) < fenster_tage - reserve


def allzeithoch(k, frisch=None, alt=None, toleranz=0.005, fenster_tage=426):
    """Punkt 16: (Allzeithoch, Datum, Quelle) oder (None, None, None).

    k      die Tageskurse von heute (Hoch des Fensters).
    frisch (Hoch, Monat 'JJJJ-MM') aus Yahoos Monatskerzen der ganzen
           Historie oder None. GEMESSEN 14.09.2026: Das hoechste Monatshoch
           ist bei 100 von 100 Aktien gleich dem hoechsten Tageshoch.
    alt    der Eintrag der Vornacht mit technik.ath, technik.ath_datum,
           letzter_tag, kurs und vortag, oder None.

    Reihenfolge: frischer Abruf; sonst die Kette aus der Vornacht, SPLITFEST:
    Der Schlusskurs, den die Vornacht an ihrem letzten Tag gespeichert hat,
    wird mit dem Schlusskurs verglichen, den die heutigen Kurse fuer
    denselben Tag nennen. Yahoo rechnet Splits rueckwirkend ein; weicht der
    Kurs um mehr als die Toleranz ab, wird das gespeicherte Hoch mit
    demselben Faktor umgerechnet. Derselbe Vergleich laeuft fuer den Vortag
    (Schluss vortag der Vornacht): Rechnet Yahoo einen Split erst einen Tag
    spaeter ein, stimmt der letzte Tag, der Vortag aber nicht. Widersprechen
    sich die beiden Faktoren, traegt die Kette nicht, und das Allzeithoch
    wird frisch geholt. Fehlt der Tag, gibt es ebenfalls keine Kette. Zuletzt
    das Fenster, aber nur, wenn die ganze Historie darin liegt. Das Hoch des
    Fensters gilt immer mit, falls es hoeher ist; es traegt den genauen Tag,
    der Abruf nur den Monat."""
    daten, highs = k.get("daten") or [], k.get("high") or []
    paare = [(h, t) for h, t in zip(highs, daten) if _ok(h)]
    if not paare:
        return None, None, None
    w_hoch, w_tag = paare[0]
    for h, t in paare:
        if h >= w_hoch:
            w_hoch, w_tag = h, t

    def mit_fenster(hoch, datum, quelle):
        if w_hoch >= hoch:
            return _dollar(w_hoch), w_tag, quelle
        return _dollar(hoch), datum, quelle

    if frisch and _ok(frisch[0]) and frisch[0] > 0:
        return mit_fenster(frisch[0], frisch[1], "abruf")
    tk = (alt or {}).get("technik") or {}
    a_hoch, a_tag, a_kurs = tk.get("ath"), (alt or {}).get("letzter_tag"), (alt or {}).get("kurs")
    if _ok(a_hoch) and a_hoch > 0 and a_tag and _ok(a_kurs) and a_kurs > 0:
        closes = k.get("close") or []
        try:
            j = daten.index(a_tag)
        except ValueError:
            j = None
        if j is not None and j < len(closes) and _ok(closes[j]) and closes[j] > 0:
            faktor = closes[j] / a_kurs
            a_vortag = (alt or {}).get("vortag")
            if j >= 1 and _ok(a_vortag) and a_vortag > 0 and _ok(closes[j - 1]) and closes[j - 1] > 0:
                if abs(faktor / (closes[j - 1] / a_vortag) - 1.0) > toleranz:
                    faktor = None
            if faktor is not None:
                if abs(faktor - 1.0) <= toleranz:
                    faktor = 1.0
                return mit_fenster(a_hoch * faktor, tk.get("ath_datum"), "kette")
    if historie_im_fenster(daten, fenster_tage):
        return _dollar(w_hoch), w_tag, "fenster"
    return None, None, None


# ---------------------------------------------------------------------------
# Alles fuer eine Aktie
# ---------------------------------------------------------------------------

def _sprung_rund(sprung):
    return round(sprung, 4) if sprung < 1 else round(sprung, 2)


def split_verdacht(closes, volumes, faktor, dv_spanne, daten=None, splits=None, ereignis_tage=5):
    """Steht in den Kursen ein Split, den die Kursquelle noch nicht in die
    aelteren Kurse eingerechnet hat? Zwei Wege, der erste zuerst:

    1. Yahoos eigene Split-Meldung (splits, {Tag: Verhaeltnis}, 0,0333 heisst
       1 zu 30) an einem der letzten ereignis_tage Handelstage: Liegt der
       Kurssprung an diesem Tag naeher am Kehrwert des Verhaeltnisses als an
       1, ist die Historie davor noch nicht umgerechnet. Nach der Umrechnung
       liegt der Sprung wieder nahe 1, dann gilt nichts mehr.
    2. Ohne Meldung: Der Schlusskurs des letzten Tages springt auf das
       faktor-fache oder mehr (oder faellt auf den Kehrwert), das
       Dollarvolumen bleibt aber hoechstens dv_spanne-fach auseinander, weil
       sich die Stueckzahl im Gegenzug teilt. Ein echter Kurssprung dieser
       Groesse bringt ein Vielfaches an Dollarvolumen.

    Rueckgabe der Kurssprung (neuer durch alter Schluss) oder None."""
    import math
    if splits and daten and len(closes) >= 2:
        for i in range(max(1, len(closes) - int(ereignis_tage)), len(closes)):
            r = splits.get(str(daten[i])[:10]) if i < len(daten) else None
            c, c1 = closes[i], closes[i - 1]
            if not (r and _ok(r) and r > 0 and _ok(c) and _ok(c1) and c > 0 and c1 > 0):
                continue
            sprung = c / c1
            if abs(math.log(sprung) - math.log(1.0 / r)) < abs(math.log(sprung)):
                return _sprung_rund(sprung)
    if len(closes) < 2 or len(volumes) < 2:
        return None
    c, c1, v, v1 = closes[-1], closes[-2], volumes[-1], volumes[-2]
    if not all(_ok(x) and x > 0 for x in (c, c1, v, v1)):
        return None
    sprung = c / c1
    if 1.0 / faktor < sprung < faktor:
        return None
    dv = (c * v) / (c1 * v1)
    if 1.0 / dv_spanne <= dv <= dv_spanne:
        return _sprung_rund(sprung)
    return None


def technik(k, vergleich=None, cfg=None):
    """Alle Kennzahlen einer Aktie ausser RS-Aenderung und Allzeithoch; die
    brauchen den RS-Verlauf beziehungsweise den Abruf der ganzen Historie
    und entstehen in rs_universum.bauen. k und vergleich (der Index fuer
    Mansfield RS und Beta) in der Form von rs_universum.kurse_holen.
    Rueckgabe dict; fehlende Werte als None."""
    cfg = cfg or CFGT
    d = k.get("daten") or []
    c = k.get("close") or []
    h = k.get("high") or []
    lo = k.get("low") or []
    v = k.get("volume") or []
    o = k.get("open") or []
    if not c:
        return {}
    sv = split_verdacht(c, v, float(cfg["split_verdacht_faktor"]), float(cfg["split_verdacht_dollarvolumen"]),
                        d, k.get("splits"), int(cfg["split_ereignis_tage"]))
    if sv is not None:
        return {"split_verdacht": sv}
    vd = (vergleich or {}).get("daten") or []
    vc = (vergleich or {}).get("close") or []
    vola_woche, vola_monat = cfg["volatilitaet_tage"]
    raus = {"adr20": adr(h, lo, int(cfg["adr_tage"])),
            "vola5": adr(h, lo, int(vola_woche)), "vola21": adr(h, lo, int(vola_monat)),
            "atr14": atr(h, lo, c, int(cfg["atr_tage"])),
            "ud50": updown(c, v, int(cfg["updown_tage"]))}
    mrs, mrs_vorher = mansfield(d, c, vd, vc, int(cfg["mansfield_wochen"]), int(cfg["vergleich_wochen"]))
    raus["mrs"], raus["mrs_vorher"] = mrs, mrs_vorher
    raus.update(weinstein(d, c, int(cfg["weinstein_linie_wochen"]),
                          int(cfg["vergleich_wochen"]), float(cfg["weinstein_flach_pct"]),
                          int(cfg["weinstein_vorlauf_wochen"])))
    raus.update(momentum_burst(c, h, lo, v, float(cfg["burst_pct"]), float(cfg["burst_mindestvolumen"])))
    raus.update(luecke(o, c, v, float(cfg["pivot_luecke_pct"]), int(cfg["volumen_schnitt_tage"])))
    raus.update(wertentwicklung(d, c, cfg["wertentwicklung_tage"]))
    raus.update(sma_abstaende(c, cfg["sma_tage"]))
    raus.update(hoch_tief(h, lo, c, int(cfg["hoch_tief_tage"])))
    raus["beta"] = beta(d, c, vd, vc, int(cfg["beta_tage"]))
    rsi_lang, rsi_kurz = cfg["rsi_tage"]
    raus["rsi14"], raus["rsi2"] = rsi(c, int(rsi_lang)), rsi(c, int(rsi_kurz))
    raus.update(volumen_schnitte(c, v, int(cfg["volumen_tage"]), int(cfg["dollarvolumen_kurz_tage"])))
    return raus


# ---------------------------------------------------------------------------
# Selbsttest (ohne Netz)
# ---------------------------------------------------------------------------

def _handelstage(anzahl, beginn=date(2025, 1, 6)):
    """Wochentage ab beginn, ohne Wochenenden, als ISO-Texte."""
    tage, i = [], 0
    while len(tage) < anzahl:
        t = date.fromordinal(beginn.toordinal() + i)
        i += 1
        if t.weekday() < 5:
            tage.append(t.isoformat())
    return tage


def selbsttest() -> int:
    fehler = []

    def p(name, ok, zusatz=""):
        print(f"  {'ok  ' if ok else 'FEHL'} {name}" + (f": {zusatz}" if zusatz and not ok else ""))
        if not ok:
            fehler.append(name)

    print("Technische Kennzahlen, Selbsttest (ohne Netz)")
    # 1 und 9: ADR
    p("ADR: Hoch 11 zu Tief 10 an jedem Tag ergibt 10 Prozent, zu kurze Reihe nichts",
      adr([11.0] * 20, [10.0] * 20, 20) == 10.0 and adr([11.0] * 19, [10.0] * 19, 20) is None
      and adr([11.0] * 25 + [12.0] * 5, [10.0] * 30, 5) == 20.0)
    # 2: ATR
    p("ATR: gleichbleibende wahre Spanne 1 ergibt 1; der Vortagsschluss zaehlt mit",
      atr([11.0] * 30, [10.0] * 30, [10.5] * 30, 14) == 1.0
      and atr([11.0] * 15 + [12.5], [10.0] * 15 + [12.0], [10.5] * 15 + [12.2], 14) == round(15.0 / 14.0, 4)
      and atr([11.0] * 10, [10.0] * 10, [10.5] * 10, 14) is None)
    wilder = atr([10.0 + (i % 3) for i in range(20)], [9.0 + (i % 3) for i in range(20)],
                 [9.5 + (i % 3) for i in range(20)], 14)
    tr = [max(1.0, abs((10.0 + i % 3) - (9.5 + (i - 1) % 3)), abs((9.0 + i % 3) - (9.5 + (i - 1) % 3)))
          for i in range(1, 20)]
    erwartet = sum(tr[:14]) / 14
    for x in tr[14:]:
        erwartet = (erwartet * 13 + x) / 14
    p("ATR: Glaettung nach Wilder, von Hand nachgerechnet", abs(wilder - erwartet) < 1e-3, f"{wilder} gegen {erwartet}")
    # 3: Up/Down
    closes = [100.0]
    vols = [0.0]
    for i in range(50):
        closes.append(closes[-1] + (1.0 if i % 2 == 0 else -0.5))
        vols.append(200.0 if i % 2 == 0 else 100.0)
    p("Up/Down: Plus-Tage mit 200, Minus-Tage mit 100 Stueck ergibt 2,0; ohne Minus-Tag nichts",
      updown(closes, vols, 50) == 2.0 and updown([float(i) for i in range(60)], [1.0] * 60, 50) is None)
    # 4: A/D nach Chaikin
    p("A/D nach Chaikin: Schluss am Hoch plus 1, am Tief minus 1, in der Mitte null, ohne Spanne null",
      ad_chaikin([11.0] * 65, [11.0] * 65, [10.0] * 65, [5.0] * 65, 65) == 1.0
      and ad_chaikin([10.0] * 65, [11.0] * 65, [10.0] * 65, [5.0] * 65, 65) == -1.0
      and abs(ad_chaikin([10.5] * 65, [11.0] * 65, [10.0] * 65, [5.0] * 65, 65)) < 1e-12
      and ad_chaikin([10.0] * 65, [10.0] * 65, [10.0] * 65, [5.0] * 65, 65) == 0.0
      and ad_chaikin([10.0] * 10, [10.0] * 10, [10.0] * 10, [5.0] * 10, 65) is None)
    p("A/D nach Chaikin: das Volumen gewichtet, 3 Teile oben gegen 1 Teil unten ergibt 0,5",
      abs(ad_chaikin([11.0, 10.0] * 33, [11.0] * 66, [10.0] * 66, [3.0, 1.0] * 33, 66) - 0.5) < 1e-12)
    # 5 und 6: Mansfield und Weinstein an Wochenreihen
    tage = _handelstage(300)
    index = [100.0] * 300
    p("Mansfield: Aktie gleich Index mal 2 ergibt null",
      mansfield(tage, [200.0] * 300, tage, index, 52, 4) == (0.0, 0.0))
    import math
    # Beschleunigter Anstieg: Die Relation zum flachen Index waechst immer
    # schneller, also steigt die Mansfield RS. Bei gleichbleibendem Tempo
    # bliebe sie gleich, weil sich Kurs und 52-Wochen-Schnitt im selben
    # Verhaeltnis bewegen.
    steigend = [50.0 * math.exp(0.001 * i + 0.000005 * i * i) for i in range(300)]
    m_jetzt, m_vorher = mansfield(tage, steigend, tage, index, 52, 4)
    ws = [x[2] / 100.0 for x in wochenschluesse(tage, steigend)]
    von_hand = round((ws[-1] / (sum(ws[-52:]) / 52) - 1.0) * 100.0, 2)
    p("Mansfield: steigende Relation ueber null und hoeher als vor vier Wochen, von Hand nachgerechnet",
      m_jetzt is not None and m_jetzt > 0 and m_vorher is not None and m_jetzt > m_vorher and m_jetzt == von_hand,
      f"{m_jetzt} {m_vorher} {von_hand}")
    p("Mansfield: ohne Index oder mit zu kurzer Reihe nichts",
      mansfield(tage, steigend, [], [], 52, 4) == (None, None)
      and mansfield(tage[:200], steigend[:200], tage, index, 52, 4)[0] is None)
    w2 = weinstein(tage, steigend, 30, 4, 0.5, 13)
    p("Weinstein: stetiger Anstieg, Kurs zwei Wochen ueber der steigenden Linie, ist Stufe 2", w2["stufe"] == 2, w2)
    fallend = [200.0 * math.exp(-0.001 * i - 0.000005 * i * i) for i in range(300)]
    mf, mfv = mansfield(tage, fallend, tage, index, 52, 4)
    w4 = weinstein(tage, fallend, 30, 4, 0.5, 13)
    p("Weinstein: stetiger Rueckgang, Kurs zwei Wochen unter der fallenden Linie, ist Stufe 4", w4["stufe"] == 4, w4)
    # N3 vom 15.09.2026: Die Mansfield RS entscheidet nicht mehr mit. Dieselbe
    # steigende Reihe gegen einen noch schneller steigenden Index hat eine
    # fallende Mansfield RS unter null und bleibt trotzdem Stufe 2.
    index_schneller = [100.0 * math.exp(0.003 * i + 0.00001 * i * i) for i in range(300)]
    mrs_neg, mrs_neg_v = mansfield(tage, steigend, tage, index_schneller, 52, 4)
    p("Weinstein: Stufe 2 auch bei Mansfield RS unter null und fallend, seit Nachfrage N3",
      mrs_neg is not None and mrs_neg < 0 and mrs_neg_v is not None and mrs_neg < mrs_neg_v
      and weinstein(tage, steigend, 30, 4, 0.5, 13)["stufe"] == 2, f"{mrs_neg} {mrs_neg_v}")
    knick = list(steigend)
    knick[-5:] = [steigend[-6] * 0.7] * 5
    wk = weinstein(tage, knick, 30, 4, 0.5, 13)
    p("Weinstein: steigende Linie, der letzte Wochenschluss faellt unter die Linie, ist keine eindeutige Stufe",
      wk["stufe"] == 0 and wk["linie_steig"] > 0.5 and wk["linie_abst"] < 0, wk)
    oben = [50.0 * 1.004 ** i for i in range(150)] + [50.0 * 1.004 ** 149] * 150
    w3 = weinstein(tage, oben, 30, 4, 0.5, 13)
    p("Weinstein: flache Linie nach einem Anstieg ist Stufe 3", w3["stufe"] == 3, w3)
    unten = [200.0 * 0.996 ** i for i in range(150)] + [200.0 * 0.996 ** 149] * 150
    w1 = weinstein(tage, unten, 30, 4, 0.5, 13)
    p("Weinstein: flache Linie nach einem Rueckgang ist Stufe 1", w1["stufe"] == 1, w1)
    p("Weinstein: ganz flach ohne Vorlauf ist keine eindeutige Stufe, zu kurz gar keine",
      weinstein(tage, [100.0] * 300, 30, 4, 0.5, 13)["stufe"] == 0
      and weinstein(tage[:100], [100.0] * 100, 30, 4, 0.5, 13)["stufe"] is None)
    # 7: Momentum Burst und Episodic Pivot
    mb = momentum_burst([100.0, 99.0, 104.0], [101.0, 100.0, 104.5], [99.0, 98.0, 99.0],
                        [150000.0, 120000.0, 300000.0], 4.0, 100000)
    p("Momentum Burst: plus 5,1 Prozent bei hoeherem Volumen ueber 100.000 Stueck; Schlusslage 91, Vortag minus 1",
      mb["burst"] is True and mb["schlusslage"] == 91 and mb["vortag_pct"] == -1.0 and mb["vortag_spanne"] == 2.0, mb)
    p("Momentum Burst: plus 3 Prozent, weniger Volumen oder unter 100.000 Stueck ist keiner",
      momentum_burst([100.0, 100.0, 103.0], [1.0] * 3, [1.0] * 3, [1.0, 1.0, 9e5], 4.0, 100000)["burst"] is False
      and momentum_burst([100.0, 100.0, 105.0], [1.0] * 3, [1.0] * 3, [1.0, 5e5, 4e5], 4.0, 100000)["burst"] is False
      and momentum_burst([100.0, 100.0, 105.0], [1.0] * 3, [1.0] * 3, [1.0, 5e4, 9e4], 4.0, 100000)["burst"] is False)
    lk = luecke([0.0] * 50 + [110.0], [100.0] * 50 + [99.0], [100.0] * 50 + [300.0], 10.0, 50)
    p("Luecke: Eroeffnung 110 nach Schluss 100 heisst plus 10 Prozent, Pivot; seit Eroeffnung minus 10; Volumen 3 mal",
      lk == {"luecke": 10.0, "seit_eroeffnung": -10.0, "vol_faktor": 3.0, "pivot": True}, lk)
    p("Luecke: ohne Eroeffnungskurs nichts, der Volumenfaktor bleibt",
      luecke([], [100.0] * 51, [100.0] * 50 + [200.0], 10.0, 50)
      == {"luecke": None, "seit_eroeffnung": None, "vol_faktor": 2.0, "pivot": None})
    # 8: Wertentwicklung
    daten_j = _handelstage(60, date(2025, 10, 6)) + _handelstage(200, date(2026, 1, 2))
    kurse_j = [80.0] * 59 + [90.0] + [100.0 + i for i in range(200)]
    we = wertentwicklung(daten_j, kurse_j, {"1w": 5, "1m": 21, "3m": 63, "6m": 126, "12m": 252})
    p("Wertentwicklung: gegen den Schluss vor 5, 63 und 252 Tagen, seit Jahresbeginn gegen den letzten Schluss 2025",
      daten_j[59] == "2025-12-26" and daten_j[-1][:4] == "2026"
      and we["perf_1w"] == _pct(299.0, 294.0) and we["perf_12m"] == _pct(299.0, 80.0)
      and we["perf_ytd"] == _pct(299.0, 90.0) and we["perf_3m"] == _pct(299.0, 236.0), we)
    d_jahr = _handelstage(270, date(2025, 9, 1))
    k_jahr = [float(i) for i in range(1, 271)]
    wj = wertentwicklung(d_jahr, k_jahr, {"12m": "jahr"})
    p("Wertentwicklung Jahr wie bei Finviz: gegen den letzten Schluss am oder vor demselben Kalendertag, "
      "nicht gegen 252 Handelstage; zu kurz nichts; 29. Februar wird 28.",
      d_jahr[-1] == "2026-09-11" and d_jahr[8] == "2025-09-11" and wj["perf_12m"] == _pct(270.0, 9.0)
      and wj["perf_12m"] != _pct(270.0, k_jahr[-253])
      and wertentwicklung(d_jahr[100:], k_jahr[100:], {"12m": "jahr"})["perf_12m"] is None
      and _vor_einem_jahr("2028-02-29") == date(2027, 2, 28), wj)
    p("Wertentwicklung: zu kurze Reihe nichts, ohne Vorjahr kein Wert seit Jahresbeginn",
      wertentwicklung(_handelstage(10, date(2026, 1, 5)), [1.0] * 10, {"1m": 21})
      == {"perf_1m": None, "perf_ytd": None})
    # 10: SMA, 50-Tage-Hoch und Tief, 52-Wochen-Tief
    sa = sma_abstaende([100.0] * 199 + [110.0], [20, 50, 200])
    p("SMA-Abstand: 19 mal 100 und einmal 110 ergibt SMA 20 von 100,5, also plus 9,5 Prozent",
      sa["sma20_abst"] == 9.5 and sa["sma200_abst"] == _pct(110.0, (199 * 100.0 + 110.0) / 200)
      and sma_abstaende([1.0] * 10, [20])["sma20_abst"] is None, sa)
    ht = hoch_tief([100.0] * 99 + [120.0] + [110.0] * 50, [90.0] * 100 + [100.0] * 50, [105.0] * 150, 50)
    p("Hoch und Tief: 50-Tage-Hoch 110 heisst minus 4,5 Prozent, Tief 100 plus 5; 52-Wochen-Tief 90 plus 16,7",
      ht == {"hoch50_abst": -4.5, "tief50_abst": 5.0, "tief52_abst": 16.7}, ht)
    # 12: Beta
    import random
    r = random.Random(7)
    renditen = [r.gauss(0, 0.01) for _ in range(300)]
    idx_k, akt_k = [100.0], [50.0]
    for x in renditen:
        idx_k.append(idx_k[-1] * (1 + x))
        akt_k.append(akt_k[-1] * (1 + 2 * x))
    t301 = _handelstage(301)
    p("Beta: Aktie mit doppelter Tagesrendite des Index ergibt 2,0; zu kurz nichts",
      beta(t301, akt_k, t301, idx_k, 252) == 2.0 and beta(t301[:100], akt_k[:100], t301, idx_k, 252) is None,
      beta(t301, akt_k, t301, idx_k, 252))
    # 13: RSI
    p("RSI 2 von Hand: 10, 11, 10, 12 ergibt 83,3; nur Gewinne 100; ohne Bewegung 50",
      rsi([10.0, 11.0, 10.0, 12.0], 2) == 83.3 and rsi([float(i) for i in range(30)], 14) == 100.0
      and rsi([5.0] * 30, 14) == 50.0 and rsi([1.0] * 5, 14) is None)
    # 14: Volumen
    p("Volumen: Schnitt ueber 63 Tage, Dollarvolumen ueber 20 Tage",
      volumen_schnitte([10.0] * 70, [1000.0] * 7 + [2000.0] * 63, 63, 20) == {"vol63": 2000, "dv20": 20000})
    # 15: RS-Aenderung
    verlauf = [["2026-08-10", 50], ["2026-08-20", 55], ["2026-09-04", 60], ["2026-09-08", 66], ["2026-09-11", 70]]
    p("RS-Aenderung: eine Woche gegen den 04.09., vier Wochen gegen den 10.08.; ohne Eintrag nichts",
      rs_aenderung(verlauf, 5) == 10 and rs_aenderung(verlauf, 26) == 20
      and rs_aenderung(verlauf[-2:], 26) is None and rs_aenderung([["2026-09-11", None]], 5) is None)
    # 16: Allzeithoch
    kd = _handelstage(300)
    k = {"daten": kd, "high": [100.0] * 299 + [120.0], "close": [95.0] * 300}
    p("Allzeithoch: frischer Abruf hoeher als das Fenster gilt mit Monat",
      allzeithoch(k, frisch=(150.0, "2021-03")) == (150.0, "2021-03", "abruf"))
    p("Allzeithoch: Fenster hoeher als der Abruf gilt mit genauem Tag",
      allzeithoch(k, frisch=(110.0, "2021-03")) == (120.0, kd[-1], "abruf"))
    alt = {"letzter_tag": kd[-2], "kurs": 190.0, "technik": {"ath": 300.0, "ath_datum": "2020-01"}}
    p("Allzeithoch: Kette nach einem Split 2 zu 1 rechnet das gespeicherte Hoch um",
      allzeithoch(k, alt=alt) == (150.0, "2020-01", "kette"), allzeithoch(k, alt=alt))
    alt2 = {"letzter_tag": kd[-2], "kurs": 95.3, "technik": {"ath": 300.0, "ath_datum": "2020-01"}}
    p("Allzeithoch: kleine Abweichung innerhalb der Toleranz aendert nichts",
      allzeithoch(k, alt=alt2) == (300.0, "2020-01", "kette"))
    k_vor = {"daten": kd, "high": [100.0] * 299 + [120.0], "close": [95.0] * 298 + [96.0, 95.0]}
    alt_v = {"letzter_tag": kd[-2], "kurs": 192.0, "vortag": 190.0, "technik": {"ath": 300.0, "ath_datum": "2020-01"}}
    p("Allzeithoch: Split in beiden Tagen eingerechnet, die Kette traegt mit dem gemeinsamen Faktor",
      allzeithoch(k_vor, alt=alt_v) == (150.0, "2020-01", "kette"), allzeithoch(k_vor, alt=alt_v))
    alt_spaet = {"letzter_tag": kd[-2], "kurs": 96.0, "vortag": 190.0, "technik": {"ath": 300.0, "ath_datum": "2020-01"}}
    p("Allzeithoch: Split nur im Vortag eingerechnet (Yahoo einen Tag spaeter), die Kette traegt nicht",
      allzeithoch(k_vor, alt=alt_spaet) == (None, None, None))
    alt3 = {"letzter_tag": "2019-01-02", "kurs": 95.0, "technik": {"ath": 300.0, "ath_datum": "2020-01"}}
    p("Allzeithoch: fehlt der Tag der Vornacht, gibt es keine Kette und ohne ganze Historie keinen Wert",
      allzeithoch(k, alt=alt3) == (None, None, None))
    jung = {"daten": _handelstage(200), "high": [10.0] * 199 + [12.0], "close": [10.0] * 200}
    p("Allzeithoch: junge Aktie mit ganzer Historie im Fenster nimmt das Fensterhoch",
      allzeithoch(jung) == (12.0, jung["daten"][-1], "fenster") and historie_im_fenster(jung["daten"], 426)
      and not historie_im_fenster(kd, 426))
    # Alles zusammen
    k_voll = {"daten": tage, "open": steigend, "high": [x * 1.01 for x in steigend],
              "low": [x * 0.99 for x in steigend], "close": steigend, "volume": [1e6] * 300}
    alles = technik(k_voll, {"daten": tage, "close": index})
    erwartet_felder = {"adr20", "vola5", "vola21", "atr14", "ud50", "mrs", "mrs_vorher", "stufe", "linie_abst", "linie_steig",
                       "burst", "schlusslage", "vortag_pct", "vortag_spanne", "luecke", "seit_eroeffnung",
                       "vol_faktor", "pivot", "perf_1w", "perf_1m", "perf_3m", "perf_6m", "perf_12m", "perf_ytd",
                       "sma20_abst", "sma50_abst", "sma200_abst", "hoch50_abst", "tief50_abst", "tief52_abst",
                       "beta", "rsi14", "rsi2", "vol63", "dv20"}
    p("Alle Kennzahlen einer Aktie: jedes Feld da, Stufe 2, ADR und Volatilitaet 2 Prozent",
      set(alles) == erwartet_felder and alles["stufe"] == 2 and alles["adr20"] == 2.02 and alles["vola21"] == 2.02
      and alles["ud50"] is None,
      sorted(set(alles) ^ erwartet_felder) or alles)
    p("Alle Kennzahlen ohne Kurse: leer", technik({"close": []}) == {})
    # Unbereinigter Split (Befund 14.09.2026 an OPTT: 0,196 auf 2,605 Dollar)
    p("Split-Verdacht: Kurs mal 13 bei gleichem Dollarvolumen ja, auch umgekehrt; echter Sprung mit viel Umsatz nein",
      split_verdacht([0.2, 0.196, 2.605], [2e6, 6.2e6, 6.0e5], 3.0, 5.0) == 13.29
      and split_verdacht([3.0, 2.6, 0.2], [1e5, 4e5, 5.5e6], 3.0, 5.0) == 0.0769
      and split_verdacht([1.0, 1.0, 3.2], [1e6, 1e6, 2e7], 3.0, 5.0) is None
      and split_verdacht([1.0, 1.0, 2.5], [1e6, 1e6, 4e5], 3.0, 5.0) is None
      and split_verdacht([1.0, 4.58, 6.92], [1.0, 0.0, 3e7], 3.0, 5.0) is None)
    t6 = _handelstage(6)
    c30 = [0.2, 0.21, 0.2, 0.22, 0.21, 6.3]
    p("Split-Verdacht aus Yahoos Meldung: 1 zu 30 heute, Historie nicht umgerechnet, auch ohne Volumen erkannt",
      split_verdacht(c30, [0.0] * 6, 3.0, 5.0, t6, {t6[-1]: 1 / 30}, 5) == 30.0)
    p("Split-Verdacht aus Yahoos Meldung: Historie schon umgerechnet, dann nichts; ebenso ein alter Split",
      split_verdacht([6.0, 6.3, 6.0, 6.6, 6.3, 6.3], [1.0] * 6, 3.0, 5.0, t6, {t6[-1]: 1 / 30}, 5) is None
      and split_verdacht(c30, [0.0] * 6, 3.0, 5.0, t6, {"2020-01-02": 1 / 30}, 5) is None)
    p("Split-Verdacht aus Yahoos Meldung: 2 zu 1 vor drei Tagen, noch nicht umgerechnet, wird erkannt; "
      "ein echter Rueckgang um ein Viertel nach umgerechnetem Split nicht",
      split_verdacht([100.0, 101.0, 50.5, 51.0, 50.0, 49.0], [1.0] * 6, 3.0, 5.0, t6, {t6[2]: 2.0}, 5) == 0.5
      and split_verdacht([50.0, 50.5, 37.9, 38.0, 37.0, 36.0], [1.0] * 6, 3.0, 5.0, t6, {t6[2]: 2.0}, 5) is None)
    k_split = {**k_voll, "close": k_voll["close"][:-1] + [k_voll["close"][-2] * 13.0],
               "volume": k_voll["volume"][:-1] + [k_voll["volume"][-2] / 13.0]}
    p("Split-Verdacht: technik() nennt nur den Verdacht und keine Kennzahl",
      technik(k_split, {"daten": tage, "close": index}) == {"split_verdacht": 13.0},
      technik(k_split, {"daten": tage, "close": index}))

    print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles bestanden.")
    return 1 if fehler else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Technische Kennzahlen je Aktie (Etappe 2).")
    ap.add_argument("--selbsttest", action="store_true")
    args = ap.parse_args()
    if args.selbsttest:
        return selbsttest()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
