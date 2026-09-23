#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MARKTBREITE UND MARKTPHASE (Etappe 3, Entscheidung 6)
=====================================================
Gerhard, 13.09.2026, woertlich: "JA BAUEN. Distribution Days, Follow-through
Day, Steiger und Faller, McClellan, Anteil ueber SMA 50 und 200, neue Hochs
und Tiefs, Stockbee-Zaehler. Die Ampel filtert weiterhin NICHTS." Grundlage
ist das Recherche-Papier vom 13.09.2026, Teil 4.4 (Punkte 1 bis 8) und
Etappe 6.4.

Dieses Modul rechnet nur, auf einfachen Listen in der Form von
rs_universum.kurse_holen, und baut die Saetze fuer Meldung und Bericht. Es
holt nichts aus dem Netz und filtert nichts.

WO GERECHNET WIRD: Distribution Days und Follow-through Day brauchen nur die
beiden Indizes und haengen an marktampel.py (Papier 4.4 Punkt 6: "Anbau an
marktampel.py"). Die Breite braucht die Kursreihen des ganzen Universums;
die holt rs_universum.bauen ohnehin jede Nacht, dort wird sie gerechnet und
als "marktbreite" in rs_universum.json abgelegt. Beides erscheint zusammen
in EINER Zeile am Anfang der ersten Waechter-Meldung des Handelstags
(Papier 4.4 Punkt 8) und ausfuehrlich im Abendbericht.

AUS DEN INDIZES (je S&P 500 und Nasdaq, Yahoo mit Volumen)
  Distribution Day (Papier 4.4 Punkt 6, IBD): Schluss mindestens 0,2 Prozent
      unter dem Vortag bei hoeherem Volumen als am Vortag.
  Stalling Day (ebenda): hoeheres Volumen als am Vortag und ein Gewinn unter
      0,2 Prozent; ein Tag ohne Veraenderung zaehlt mit. Ebenso ein Verlust
      unter 0,2 Prozent bei hoeherem Volumen: Gerhard, 15.09.2026, Nachfrage
      N5, "JA, ein kleiner Verlust bei hoeherem Volumen zaehlt als Stalling
      Day"; er ist schwaecher als ein kleiner Gewinn bei hoeherem Volumen, der
      schon zaehlt. Bis dahin zaehlte er nirgends.
  Beide zaehlen 25 Sitzungen lang, heute eingeschlossen, und verfallen
      frueher, sobald der Index danach 5 Prozent ueber dem Schluss dieses
      Tages handelt (Tageshoch). Die Zaehlung nennt beide zusammen; ab 4 heisst
      sie nach IBD unter Druck, ab 6 Korrektur (Papier, ebenda).
  Follow-through Day (Papier 4.4 Punkt 7, IBD): Nach einem Tief beginnt mit
      dem ersten hoeheren Schluss der Erholungsversuch (Tag 1). Ab Tag 4
      zaehlt ein Anstieg von mindestens 1,25 Prozent bei hoeherem Volumen als
      am Vortag. Unterschreitet der Index vorher das Tagestief des Tiefs,
      beginnt die Zaehlung neu; ein tieferer Schluss allein beendet den
      Versuch nicht. Der Follow-through Day ist ungueltig, sobald der Index
      sein Tagestief unterschreitet.
      WANN EIN TIEF ZAEHLT, nennt IBD nicht in Zahlen. Gerhard, 15.09.2026,
      Nachfrage N6, "JA, so gilt es": ein Schluss unter der 50-Tage-Linie,
      der zugleich der tiefste Schluss der letzten 25 Sitzungen ist. Die
      50-Tage-Linie ist dieselbe wie in der Marktampel.
      NACH EINEM GESCHEITERTEN FOLLOW-THROUGH DAY: Gerhard, 15.09.2026,
      Nachfrage N7, "JA, nach einem gescheiterten Follow-through Day zaehlt
      schon vor einem neuen Tief ein neuer Erholungsversuch." Der Tag, an dem
      der Index das Tagestief des Follow-through Day unterschreitet, tritt an
      die Stelle des Tiefs: Mit dem ersten hoeheren Schluss danach beginnt
      der neue Erholungsversuch (Tag 1), und wieder beginnt die Zaehlung neu,
      sobald der Index das Tagestief dieses Tages unterschreitet. Bis dahin
      kam ein neuer Erholungsversuch erst nach einem neuen Tief.

AUS DEM UNIVERSUM (die Stammaktien des RS-Bezugs; Titel mit unbereinigtem
Split zaehlen nicht mit)
  Steiger und Faller je Tag; Veraenderung der A/D-Linie ueber zehn Tage (die
      Hoehe der Linie haengt vom Beginn der Reihe ab und wird nicht genannt).
  McClellan-Oszillator, ratio-adjusted: je Tag (Steiger minus Faller) durch
      (Steiger plus Faller) mal 1000; davon EMA 19 minus EMA 39 mit den
      Glaettungskonstanten 0,10 und 0,05, jede EMA mit dem einfachen
      Durchschnitt ihrer ersten Werte gestartet (StockCharts ChartSchool).
      Der Summation Index ist die laufende Summe des Oszillators; seine Hoehe
      haengt vom Beginn der Reihe ab, und unsere Reihe reicht nur 14 Monate
      zurueck. Genannt wird deshalb nur seine Richtung ueber fuenf Tage.
  Anteil der Aktien ueber SMA 20, 50 und 200.
  Neue 52-Wochen-Hochs und Tiefs je Tag: Tageshoch UEBER dem hoechsten Hoch
      der 251 Sitzungen davor, Tagestief unter dem tiefsten Tief; Differenz
      und ihr Schnitt ueber zehn Tage. Anders als beim Kennzeichen je Titel
      in rs_universum (auf dem Hoch, Gleichstand zaehlt) zaehlt hier ein
      Gleichstand nicht, sonst stuende ein stillstehender Titel zugleich bei
      den Hochs und bei den Tiefs. Titel mit kuerzerer Historie zaehlen nicht.
  Stockbee Market Monitor, Formeln aus Stockbees Beitrag "How I get the
      Market Monitor Numbers" (TC2000, August 2014):
        plus 4 Prozent: (C minus C1) durch C1 mal 100 mindestens 4, V mindestens
          100.000 und V ueber V1; minus 4 Prozent spiegelbildlich;
        Verhaeltnis 5 und 10 Tage: Summe der Plus-4-Zaehler durch Summe der
          Minus-4-Zaehler;
        25 Prozent im Quartal: Schluss mindestens 25 Prozent ueber dem
          tiefsten Schluss der 65 Tage (MINC65), fallend spiegelbildlich
          gegen MAXC65, beides mit 0,01 Dollar Zuschlag wie im Original;
          AVGC20 mal AVGV20 mindestens 250.000;
        25 und 50 Prozent im Monat: gegen den Schluss vor 20 Tagen (C20), C20
          mindestens 5 Dollar, AVGC20 mal AVGV20 mindestens 250.000;
        13 Prozent in 34 Tagen: gegen MINC34 und MAXC34, dieselbe
          Umsatzgrenze.
Ein Tag, an dem weniger als die Haelfte der ueblichen Zahl an Aktien Kurse
hat, gilt als unvollstaendig (etwa ein Abruf waehrend des Handels bei einem
Teil der Titel); gerechnet wird dann bis zum letzten vollstaendigen Tag, und
der Tag steht unter "unvollstaendige_tage".

Aufruf:
  python marktbreite.py --selbsttest     ohne Netz
"""

import argparse
import sys
from bisect import bisect_right
from datetime import date

from config import CFG

CFGB = CFG["marktbreite"]


def _ok(x):
    return x is not None and x == x


# ---------------------------------------------------------------------------
# Indizes: Distribution Days, Stalling Days und Follow-through Day
# ---------------------------------------------------------------------------

def distribution_days(daten, highs, closes, volumes, fenster=None, verlust_pct=None, verfall_pct=None,
                      stall_pct=None):
    """Die gueltigen Distribution Days und Stalling Days der letzten fenster
    Sitzungen (heute eingeschlossen), aelteste zuerst:
    [(Tag, Veraenderung in Prozent, "distribution" oder "stalling")]."""
    fenster = int(fenster or CFGB["dd_fenster"])
    verlust_pct = float(CFGB["dd_verlust_pct"] if verlust_pct is None else verlust_pct)
    verfall_pct = float(CFGB["dd_verfall_pct"] if verfall_pct is None else verfall_pct)
    stall_pct = float(CFGB["stalling_gewinn_pct"] if stall_pct is None else stall_pct)
    n = len(closes)
    raus = []
    for t in range(max(1, n - fenster), n):
        c, c1, v, v1 = closes[t], closes[t - 1], volumes[t], volumes[t - 1]
        if not all(_ok(x) for x in (c, c1, v, v1)) or c1 <= 0 or not v > v1:
            continue
        pct = round((c / c1 - 1.0) * 100.0, 6)
        if pct <= -verlust_pct:
            art = "distribution"
        elif pct < stall_pct:
            # Gewinn unter stall_pct oder, seit Nachfrage N5, Verlust unter
            # verlust_pct; beides bei hoeherem Volumen.
            art = "stalling"
        else:
            continue
        spaeter = [h for h in highs[t + 1:] if _ok(h)]
        if spaeter and max(spaeter) >= c * (1.0 + verfall_pct / 100.0):
            continue
        raus.append((str(daten[t])[:10], round(pct, 2), art))
    return raus


def _sma_reihe(werte, laenge):
    raus = [None] * len(werte)
    summe = 0.0
    for i, w in enumerate(werte):
        summe += w
        if i >= laenge:
            summe -= werte[i - laenge]
        if i >= laenge - 1:
            raus[i] = summe / laenge
    return raus


def follow_through(daten, lows, closes, volumes, linie=None, tief_fenster=None, ab_tag=None, gewinn_pct=None,
                   tiefs=None):
    """Zustand der Marktphase am letzten Tag, nach den Regeln im Kopf der
    Datei. tiefs: eine Liste, in die jedes bestaetigte Tief der ganzen Reihe
    kommt (Tag als Text), also das Tief jeder Korrektur, deren
    Erholungsversuch ein Follow-through Day bestaetigt hat. Die
    Stufenzaehlung der Chartmuster (M) zaehlt ab diesen Markttiefs neu
    (Gerhard, 23.09.2026, Frage 3). Rueckgabe dict:
      zustand       "bestaetigt" (Follow-through Day nach dem letzten Tief),
                    "erholungsversuch", "korrektur" (Tief ohne
                    Erholungsversuch) oder "keine" (kein Tief in der Reihe)
      korrektur_tag Tag des letzten Tiefs; nach einem gescheiterten
                    Follow-through Day der Tag, an dem er scheiterte, oder ein
                    spaeterer Tag mit tieferem Tagestief
      versuch_grund "tief" (der Zyklus beginnt mit einem Tief) oder
                    "ftd_gescheitert" (er beginnt mit dem Scheitern des
                    Follow-through Day, Nachfrage N7); None ohne Zyklus
      tag1          Tag 1 des laufenden Erholungsversuchs; versuch_tag dessen
                    Zaehler heute
      ftd_tag, ftd_pct, ftd_gescheitert, ftd_gescheitert_tag  der juengste
                    Follow-through Day der Reihe"""
    linie = int(linie or CFGB["ftd_linie_tage"])
    tief_fenster = int(tief_fenster or CFGB["ftd_tief_fenster"])
    ab_tag = int(ab_tag or CFGB["ftd_ab_tag"])
    gewinn_pct = float(CFGB["ftd_gewinn_pct"] if gewinn_pct is None else gewinn_pct)
    n = len(closes)
    raus = {"zustand": "keine", "korrektur_tag": None, "versuch_grund": None, "tag1": None, "versuch_tag": None,
            "ftd_tag": None, "ftd_pct": None, "ftd_gescheitert": None, "ftd_gescheitert_tag": None}
    if n < linie + 1 or any(not _ok(x) for x in closes) or any(not _ok(x) for x in lows):
        return raus
    sma = _sma_reihe(closes, linie)
    korr = None        # (Index, Tagestief) des Tiefs
    grund = None       # "tief" oder "ftd_gescheitert"
    tag1 = None
    zyklus_ftd = None  # Follow-through Day seit diesem Tief
    ftd = None         # (Index, Tagestief, Prozent) des juengsten
    gescheitert = None
    for t in range(max(linie, tief_fenster), n):
        c = closes[t]
        neues_tief = sma[t] is not None and c < sma[t] and c <= min(closes[t - tief_fenster + 1:t + 1])
        if ftd is not None and gescheitert is None and t > ftd[0] and lows[t] < ftd[1]:
            gescheitert = t
            if zyklus_ftd is not None:
                # Nachfrage N7: Scheitert der Follow-through Day des
                # laufenden Zyklus, beginnt von diesem Tag an ein neuer.
                korr, tag1, zyklus_ftd = (t, lows[t]), None, None
                grund = "tief" if neues_tief else "ftd_gescheitert"
                continue
        if korr is None or zyklus_ftd is not None:
            if neues_tief:
                korr, tag1, zyklus_ftd, grund = (t, lows[t]), None, None, "tief"
            continue
        if lows[t] < korr[1]:
            korr, tag1 = (t, lows[t]), None
            if neues_tief:
                grund = "tief"
            continue
        if tag1 is None:
            if c > closes[t - 1]:
                tag1 = t
            continue
        if (t - tag1 + 1) >= ab_tag:
            pct = (c / closes[t - 1] - 1.0) * 100.0
            if round(pct, 6) >= gewinn_pct and _ok(volumes[t]) and _ok(volumes[t - 1]) and volumes[t] > volumes[t - 1]:
                zyklus_ftd = t
                ftd = (t, lows[t], round(pct, 2))
                gescheitert = None
                if tiefs is not None:
                    tiefs.append(str(daten[korr[0]])[:10])
    if korr is not None:
        raus["korrektur_tag"] = str(daten[korr[0]])[:10]
        raus["versuch_grund"] = grund
        if zyklus_ftd is not None:
            raus["zustand"] = "bestaetigt"
        elif tag1 is not None:
            raus["zustand"] = "erholungsversuch"
            raus["tag1"] = str(daten[tag1])[:10]
            raus["versuch_tag"] = n - tag1
        else:
            raus["zustand"] = "korrektur"
    if ftd is not None:
        raus["ftd_tag"] = str(daten[ftd[0]])[:10]
        raus["ftd_pct"] = ftd[2]
        raus["ftd_gescheitert"] = gescheitert is not None
        raus["ftd_gescheitert_tag"] = str(daten[gescheitert])[:10] if gescheitert is not None else None
    return raus


def markttiefs(df):
    """Alle Markttiefs eines Index ueber die ganze Reihe (yfinance history
    mit Low, Close, Volume), aelteste zuerst, als Tage 'JJJJ-MM-TT': das
    Tief jeder Korrektur, deren Erholungsversuch ein Follow-through Day
    bestaetigt hat. Ohne Volumen gibt es keinen Follow-through Day und
    deshalb keine Markttiefs; Tage ohne Volumen (fruehe Indexjahre) zaehlen
    so von selbst nicht."""
    df = df.dropna(subset=["Close"])
    if "Volume" not in df.columns or len(df) < 2:
        return []
    daten = [d.strftime("%Y-%m-%d") for d in df.index]
    closes = [float(x) for x in df["Close"].values]
    lows = [float(x) if x == x else c for x, c in zip(df["Low"].values, closes)] if "Low" in df.columns else closes
    volumes = [float(x) if x == x else 0.0 for x in df["Volume"].values]
    raus = []
    follow_through(daten, lows, closes, volumes, tiefs=raus)
    return raus


def index_phase(df):
    """Distribution Days, Stalling Days und Follow-through Day aus dem
    Kursrahmen eines Index (yfinance history mit High, Low, Close, Volume).
    None ohne Volumen."""
    df = df.dropna(subset=["Close"])
    if "Volume" not in df.columns or len(df) < 2:
        return None
    daten = [d.strftime("%Y-%m-%d") for d in df.index]
    closes = [float(x) for x in df["Close"].values]
    highs = [float(h) if h == h else c for h, c in zip(df["High"].values, closes)] if "High" in df.columns else closes
    lows = [float(x) if x == x else c for x, c in zip(df["Low"].values, closes)] if "Low" in df.columns else closes
    volumes = [float(x) if x == x else 0.0 for x in df["Volume"].values]
    if sum(volumes) <= 0:
        return None
    dd = distribution_days(daten, highs, closes, volumes)
    return {"distribution_days": [{"tag": t, "pct": p, "art": a} for t, p, a in dd],
            "dd_fenster": int(CFGB["dd_fenster"]),
            "volumen_letzter_tag": volumes[-1] > 0,
            "phase": follow_through(daten, lows, closes, volumes)}


# ---------------------------------------------------------------------------
# Universum: Breite
# ---------------------------------------------------------------------------

def _ema_reihe(werte, laenge, alpha):
    """EMA mit fester Glaettungskonstante, gestartet mit dem einfachen
    Durchschnitt der ersten laenge Werte. Liste gleicher Laenge, davor None."""
    raus = [None] * len(werte)
    if len(werte) < laenge:
        return raus
    wert = sum(werte[:laenge]) / laenge
    raus[laenge - 1] = wert
    for i in range(laenge, len(werte)):
        wert = (werte[i] - wert) * alpha + wert
        raus[i] = wert
    return raus


def mcclellan(rana, kurz=None, lang=None, alpha_kurz=None, alpha_lang=None):
    """Oszillator-Reihe aus der Reihe der ratio-adjusted Net Advances:
    EMA kurz minus EMA lang, None solange eine der beiden fehlt."""
    kurz = int(kurz or CFGB["mcclellan_kurz"])
    lang = int(lang or CFGB["mcclellan_lang"])
    ak = float(alpha_kurz or CFGB["mcclellan_alpha_kurz"])
    al = float(alpha_lang or CFGB["mcclellan_alpha_lang"])
    e1, e2 = _ema_reihe(rana, kurz, ak), _ema_reihe(rana, lang, al)
    return [a - b if (a is not None and b is not None) else None for a, b in zip(e1, e2)]


def breite(reihen, cfg=None):
    """Die Breite ueber alle Kursreihen (rs_universum.kurse_holen). Rueckgabe
    dict oder {} ohne Grundlage. Reihen, deren letzter Tag nicht der
    Handelstag der Rechnung ist, zaehlen fuer die Werte dieses Tages nicht
    mit (kein Handel, veraltete Kurse)."""
    cfg = cfg or CFGB
    reihen = [k for k in reihen if k and len(k.get("close") or []) >= 2]
    if not reihen:
        return {}
    ds_je = [[str(x)[:10] for x in k["daten"]] for k in reihen]
    ad = {}
    for k, ds in zip(reihen, ds_je):
        c = k["close"]
        for i in range(1, len(c)):
            a, b = c[i], c[i - 1]
            if not (_ok(a) and _ok(b)):
                continue
            z = ad.get(ds[i])
            if z is None:
                z = ad[ds[i]] = [0, 0, 0]
            z[0 if a > b else (1 if a < b else 2)] += 1
    if not ad:
        return {}
    summen = sorted(sum(z) for z in ad.values())
    median = summen[len(summen) // 2]
    tage = [t for t in sorted(ad) if sum(ad[t]) >= median * float(cfg["min_anteil_tag"])]
    if not tage:
        return {}
    heute = tage[-1]

    # Jede Reihe endet am Handelstag der Rechnung.
    sichten = []
    for k, ds in zip(reihen, ds_je):
        ende = bisect_right(ds, heute)
        if ende < 2:
            continue
        c = k["close"]
        h = k.get("high") or c
        lo = k.get("low") or c
        v = k.get("volume") or [0.0] * len(c)
        if ende < len(ds):
            ds, c, h, lo, v = ds[:ende], c[:ende], h[:ende], lo[:ende], v[:ende]
        sichten.append((ds, c, h, lo, v))

    rana = [(ad[t][0] - ad[t][1]) / (ad[t][0] + ad[t][1]) * 1000.0 if (ad[t][0] + ad[t][1]) else 0.0 for t in tage]
    osz = mcclellan(rana, cfg["mcclellan_kurz"], cfg["mcclellan_lang"], cfg["mcclellan_alpha_kurz"],
                    cfg["mcclellan_alpha_lang"])
    raus = {"handelstag": heute, "steiger": ad[heute][0], "faller": ad[heute][1], "unveraendert": ad[heute][2],
            "reihen": len(sichten), "unvollstaendige_tage": sorted(t for t in ad if t > heute)}
    zehn = int(cfg["mittel_tage"])
    raus["ad_netto_10t"] = sum(ad[t][0] - ad[t][1] for t in tage[-zehn:])
    raus["mcclellan"] = round(osz[-1], 1) if osz[-1] is not None else None
    raus["mcclellan_vortag"] = round(osz[-2], 1) if len(osz) >= 2 and osz[-2] is not None else None
    trend = int(cfg["summation_trend_tage"])
    letzte = [o for o in osz[-trend:] if o is not None]
    raus["summation_trend"] = round(sum(letzte), 1) if len(letzte) == trend else None

    aktuell = [s for s in sichten if s[0][-1] == heute]
    raus["aktien_heute"] = len(aktuell)
    for laenge in cfg["sma_tage"]:
        laenge = int(laenge)
        geeignet = [s for s in aktuell if len(s[1]) >= laenge]
        ueber = sum(1 for s in geeignet if s[1][-1] > sum(s[1][-laenge:]) / laenge)
        raus[f"ueber_sma{laenge}_pct"] = round(ueber / len(geeignet) * 100.0, 1) if geeignet else None
        raus[f"sma{laenge}_basis"] = len(geeignet)

    # Neue Hochs und Tiefs sowie die Stockbee-Tageszaehler der letzten zehn Tage
    fenster_tage = tage[-zehn:]
    im_fenster = set(fenster_tage)
    hochs = {t: 0 for t in fenster_tage}
    tiefs = {t: 0 for t in fenster_tage}
    plus4 = {t: 0 for t in fenster_tage}
    minus4 = {t: 0 for t in fenster_tage}
    jahr = int(cfg["hoch_tief_tage"])
    b4 = float(cfg["stockbee_tages_pct"])
    minvol = float(cfg["stockbee_min_volumen"])
    for ds, c, h, lo, v in sichten:
        n = len(c)
        for i in range(max(1, n - zehn), n):
            t = ds[i]
            if t not in im_fenster:
                continue
            if i >= jahr:
                vorher_h = [x for x in h[i - jahr:i] if _ok(x)]
                vorher_l = [x for x in lo[i - jahr:i] if _ok(x)]
                if vorher_h and _ok(h[i]) and h[i] > max(vorher_h):
                    hochs[t] += 1
                if vorher_l and _ok(lo[i]) and lo[i] < min(vorher_l):
                    tiefs[t] += 1
            if _ok(c[i]) and _ok(c[i - 1]) and c[i - 1] > 0 and _ok(v[i]) and _ok(v[i - 1]):
                if v[i] >= minvol and v[i] > v[i - 1]:
                    pct = (c[i] - c[i - 1]) / c[i - 1] * 100.0
                    if pct >= b4:
                        plus4[t] += 1
                    elif pct <= -b4:
                        minus4[t] += 1
    raus["neue_hochs"], raus["neue_tiefs"] = hochs[heute], tiefs[heute]
    diffs = [hochs[t] - tiefs[t] for t in fenster_tage]
    raus["hochs_tiefs_mittel"] = round(sum(diffs) / len(diffs), 1) if len(diffs) == zehn else None
    sb = {"plus4": plus4[heute], "minus4": minus4[heute]}
    for tage_n in cfg["stockbee_verhaeltnis_tage"]:
        tage_n = int(tage_n)
        teil = tage[-tage_n:]
        if len(teil) < tage_n or tage_n > zehn:
            sb[f"verh{tage_n}"] = None
            continue
        auf, ab = sum(plus4[t] for t in teil), sum(minus4[t] for t in teil)
        sb[f"verh{tage_n}"] = round(auf / ab, 2) if ab else None

    # Stockbee: Quartal, Monat, 34 Tage (nur Reihen mit Kursen vom Handelstag)
    q_tage, m_tage, t34 = int(cfg["stockbee_quartal_tage"]), int(cfg["stockbee_monat_tage"]), int(cfg["stockbee_34_tage"])
    min_dv = float(cfg["stockbee_min_dollarvolumen"])
    min_c20 = float(cfg["stockbee_min_kurs_monat"])
    for name in ("plus25_quartal", "minus25_quartal", "plus25_monat", "minus25_monat", "plus50_monat",
                 "minus50_monat", "plus13_34t", "minus13_34t"):
        sb[name] = 0
    for ds, c, h, lo, v in aktuell:
        n = len(c)
        if n < 20 or not _ok(c[-1]):
            continue
        c20 = [x for x in c[-20:] if _ok(x)]
        v20 = [x for x in v[-20:] if _ok(x)]
        if len(c20) < 20 or len(v20) < 20 or (sum(c20) / 20) * (sum(v20) / 20) < min_dv:
            continue
        kurs = c[-1] + 0.01
        if n >= q_tage:
            teil = [x for x in c[-q_tage:] if _ok(x)]
            if teil:
                if 100.0 * (kurs - (min(teil) + 0.01)) / (min(teil) + 0.01) >= 25:
                    sb["plus25_quartal"] += 1
                if 100.0 * (kurs - (max(teil) + 0.01)) / (max(teil) + 0.01) <= -25:
                    sb["minus25_quartal"] += 1
        if n > m_tage and _ok(c[-m_tage - 1]) and c[-m_tage - 1] >= min_c20:
            m = 100.0 * (c[-1] - c[-m_tage - 1]) / c[-m_tage - 1]
            sb["plus25_monat"] += m >= 25
            sb["minus25_monat"] += m <= -25
            sb["plus50_monat"] += m >= 50
            sb["minus50_monat"] += m <= -50
        if n >= t34:
            teil = [x for x in c[-t34:] if _ok(x)]
            if teil:
                if 100.0 * (kurs - (min(teil) + 0.01)) / (min(teil) + 0.01) >= 13:
                    sb["plus13_34t"] += 1
                if 100.0 * (kurs - (max(teil) + 0.01)) / (max(teil) + 0.01) <= -13:
                    sb["minus13_34t"] += 1
    raus["stockbee"] = sb
    return raus


# ---------------------------------------------------------------------------
# Saetze
# ---------------------------------------------------------------------------

def _datum_de(iso):
    teile = str(iso or "")[:10].split("-")
    return f"{teile[2]}.{teile[1]}.{teile[0]}" if len(teile) == 3 else str(iso or "unbekannt")


def _zahl(x, stellen=0):
    if x is None:
        return "unbekannt"
    s = f"{abs(float(x)):,.{stellen}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    null = float(s.replace(".", "").replace(",", ".")) == 0
    return ("minus " if float(x) < 0 and not null else "") + s


def _vz(x, stellen=0):
    if x is None:
        return "unbekannt"
    s = _zahl(abs(float(x)), stellen)
    if float(s.replace(".", "").replace(",", ".")) == 0:
        return s
    return ("plus " if float(x) > 0 else "minus ") + s


def phase_text(info):
    """Distribution Days und Marktphase eines Index als Teil der Ampel-Zeile,
    ohne den Indexnamen, Angaben mit Beistrich getrennt. Leer ohne Daten."""
    if not isinstance(info, dict):
        return ""
    teile = []
    dd = info.get("distribution_days")
    if isinstance(dd, list):
        n = len(dd)
        stall = sum(1 for x in dd if isinstance(x, dict) and x.get("art") == "stalling")
        fenster = int(info.get("dd_fenster") or CFGB["dd_fenster"])
        s = (f"kein Distribution Day in {fenster} Sitzungen" if n == 0 else
             f"{n} Distribution Day{'' if n == 1 else 's'} in {fenster} Sitzungen")
        if stall:
            s += f", davon {stall} Stalling Day{'' if stall == 1 else 's'}"
        if n >= int(CFGB["dd_korrektur_ab"]):
            s += ", nach IBD-Zählung Korrektur"
        elif n >= int(CFGB["dd_druck_ab"]):
            s += ", nach IBD-Zählung unter Druck"
        teile.append(s)
        if info.get("volumen_letzter_tag") is False:
            teile.append("Volumen des letzten Tages fehlt")
    ph = info.get("phase") or {}
    z = ph.get("zustand")
    if z == "bestaetigt" and ph.get("ftd_tag"):
        if ph.get("ftd_gescheitert"):
            teile.append(f"Follow-through Day vom {_datum_de(ph['ftd_tag'])} gescheitert am "
                         f"{_datum_de(ph.get('ftd_gescheitert_tag'))}")
        else:
            teile.append(f"Follow-through Day am {_datum_de(ph['ftd_tag'])} mit {_vz(ph.get('ftd_pct'), 2)} Prozent")
    elif z in ("erholungsversuch", "korrektur") and ph.get("versuch_grund") == "ftd_gescheitert" and ph.get("ftd_tag"):
        # Nachfrage N7: der neue Zyklus beginnt mit dem Scheitern.
        s = (f"Follow-through Day vom {_datum_de(ph['ftd_tag'])} gescheitert am "
             f"{_datum_de(ph.get('ftd_gescheitert_tag'))}")
        spaeter = ph.get("korrektur_tag") and ph.get("korrektur_tag") != ph.get("ftd_gescheitert_tag")
        if z == "erholungsversuch":
            s += (f", neuer Erholungsversuch am Tag {int(ph.get('versuch_tag') or 0)} seit dem Tagestief vom "
                  f"{_datum_de(ph.get('korrektur_tag'))}")
        else:
            s += (f", tieferes Tagestief am {_datum_de(ph['korrektur_tag'])}" if spaeter else "")
            s += ", noch kein neuer Erholungsversuch"
        teile.append(s)
    elif z == "erholungsversuch":
        teile.append(f"Erholungsversuch am Tag {int(ph.get('versuch_tag') or 0)} seit dem Tief vom "
                     f"{_datum_de(ph.get('korrektur_tag'))}")
    elif z == "korrektur":
        teile.append(f"Tief vom {_datum_de(ph.get('korrektur_tag'))}, noch kein Erholungsversuch")
    return ", ".join(teile)


def breite_angaben(daten):
    """Die Breite knapp, je Angabe ein Eintrag; der erste ohne Vorwort."""
    sb = daten.get("stockbee") or {}
    teile = [f"{_zahl(daten.get('steiger'))} Steiger und {_zahl(daten.get('faller'))} Faller"]
    if daten.get("mcclellan") is not None:
        s = f"McClellan-Oszillator {_vz(daten['mcclellan'])}"
        if daten.get("summation_trend") is not None:
            s += ", Summation Index " + ("steigend" if daten["summation_trend"] > 0 else "fallend")
        teile.append(s)
    anteile = [f"{_zahl(daten[f'ueber_sma{n}_pct'])} Prozent über SMA {n}" for n in (50, 200)
               if daten.get(f"ueber_sma{n}_pct") is not None]
    if anteile:
        teile.append(", ".join(anteile))
    teile.append(f"{_zahl(daten.get('neue_hochs'))} neue 52-Wochen-Hochs und {_zahl(daten.get('neue_tiefs'))} neue Tiefs")
    if sb:
        s = f"Stockbee {_zahl(sb.get('plus4'))} Aktien mit plus 4 Prozent und {_zahl(sb.get('minus4'))} mit minus 4 Prozent"
        if sb.get("verh5") is not None:
            s += f", Verhältnis über 5 Tage {_zahl(sb['verh5'], 2)}"
        teile.append(s)
    return teile


def _nicht_verfuegbar(daten):
    """Der ehrliche Satz ohne Zahlen: keine Ablage oder eine gescheiterte
    Rechnung (rs_universum legt dann nur "fehler" ab)."""
    if isinstance(daten, dict) and daten.get("fehler"):
        return "Marktbreite nicht verfügbar, die letzte Berechnung ist gescheitert"
    return "Marktbreite nicht verfügbar, es liegt keine Berechnung vor"


def breite_teil(daten, tag_soll=None, mit_datum=False):
    """Die Breite als Angaben fuer die Ampel-Zeile. tag_soll: der Schluss, dem
    die Zeile gilt. Gilt die Rechnung einem anderen Schluss, steht keine Zahl
    da, sondern der Hinweis. mit_datum nennt den Schluss selbst (wenn die
    Ampel davor ihn nicht nennt)."""
    if not isinstance(daten, dict) or daten.get("steiger") is None:
        return [_nicht_verfuegbar(daten)]
    tag = str(daten.get("handelstag") or "")[:10]
    if tag_soll and tag != str(tag_soll)[:10]:
        return [f"Marktbreite nicht verfügbar, die letzte Berechnung gilt dem Schluss vom {_datum_de(tag)}"]
    a = breite_angaben(daten)
    a[0] = (f"Marktbreite zum Schluss vom {_datum_de(tag)}, " if mit_datum else "Marktbreite ") + a[0]
    return a


def breite_zeile(daten, vortag=None):
    """Die Breite als eigene Zeile, im Meldungsformat. Die Zeile traegt nie die
    Wortpaare, an denen die Handels-App einen Alarm erkennt (Kaufpunkt, Kurs,
    Stop, Ziel, Exit-Linie mit einer Zahl)."""
    return "; ".join(breite_teil(daten, vortag, mit_datum=True))


def bericht_zeilen(daten):
    """Die ganze Breite fuer den Abendbericht, je Zeile eine Angabe."""
    d = daten if isinstance(daten, dict) else {}
    if d.get("steiger") is None:
        return [_nicht_verfuegbar(daten)]
    zeilen = [f"Marktbreite: {_zahl(d['steiger'])} Steiger, {_zahl(d['faller'])} Faller, "
              f"{_zahl(d.get('unveraendert'))} unverändert; A/D-Linie über 10 Tage {_vz(d.get('ad_netto_10t'))}"]
    if d.get("mcclellan") is not None:
        s = f"McClellan-Oszillator {_vz(d['mcclellan'])}"
        if d.get("mcclellan_vortag") is not None:
            s += f", am Vortag {_vz(d['mcclellan_vortag'])}"
        if d.get("summation_trend") is not None:
            s += ("; Summation Index über 5 Tage " + ("steigend" if d["summation_trend"] > 0 else "fallend")
                  + ", seine Höhe hängt vom Beginn der 14 Monate langen Reihe ab und wird nicht genannt")
        zeilen.append(s)
    anteile = [f"über SMA {n} {_zahl(d.get(f'ueber_sma{n}_pct'), 1)} Prozent" for n in (20, 50, 200)
               if d.get(f"ueber_sma{n}_pct") is not None]
    if anteile:
        zeilen.append("Anteil der Aktien " + ", ".join(anteile))
    zeilen.append(f"Neue 52-Wochen-Hochs {_zahl(d.get('neue_hochs'))}, neue Tiefs {_zahl(d.get('neue_tiefs'))}"
                  + (f", Differenz im Schnitt von 10 Tagen {_vz(d['hochs_tiefs_mittel'], 1)}"
                     if d.get("hochs_tiefs_mittel") is not None else ""))
    sb = d.get("stockbee") or {}
    if sb:
        v5 = _zahl(sb["verh5"], 2) if sb.get("verh5") is not None else "nicht berechenbar"
        v10 = _zahl(sb["verh10"], 2) if sb.get("verh10") is not None else "nicht berechenbar"
        zeilen.append(f"Stockbee: plus 4 Prozent {_zahl(sb.get('plus4'))}, minus 4 Prozent {_zahl(sb.get('minus4'))}, "
                      f"Verhältnis 5 Tage {v5}, 10 Tage {v10}; im Quartal plus 25 Prozent "
                      f"{_zahl(sb.get('plus25_quartal'))}, minus 25 Prozent {_zahl(sb.get('minus25_quartal'))}; im Monat "
                      f"plus 25 Prozent {_zahl(sb.get('plus25_monat'))}, minus 25 Prozent {_zahl(sb.get('minus25_monat'))}, "
                      f"plus 50 Prozent {_zahl(sb.get('plus50_monat'))}, minus 50 Prozent {_zahl(sb.get('minus50_monat'))}; "
                      f"in 34 Tagen plus 13 Prozent {_zahl(sb.get('plus13_34t'))}, minus 13 Prozent "
                      f"{_zahl(sb.get('minus13_34t'))}")
    return zeilen


# ---------------------------------------------------------------------------
# Selbsttest (ohne Netz)
# ---------------------------------------------------------------------------

def _handelstage(anzahl, beginn=date(2025, 1, 6)):
    tage, i = [], 0
    while len(tage) < anzahl:
        t = date.fromordinal(beginn.toordinal() + i)
        i += 1
        if t.weekday() < 5:
            tage.append(t.isoformat())
    return tage


def selbsttest() -> int:
    import re
    import marktampel
    fehler = []

    def p(name, ok, zusatz=""):
        print(f"  {'ok  ' if ok else 'FEHL'} {name}" + (f": {zusatz}" if zusatz and not ok else ""))
        if not ok:
            fehler.append(name)

    print("Marktbreite, Selbsttest (ohne Netz)")
    # Distribution Days und Stalling Days
    t30 = _handelstage(30)
    c = [100.0] * 30
    v = [1000.0] * 30
    h = [101.0] * 30
    c[10], v[10] = 99.7, 1200.0          # minus 0,3 Prozent, mehr Volumen: Distribution Day
    c[12], v[12] = 99.5, 900.0           # weniger Volumen: nichts
    c[18], v[18] = 100.1, 1100.0         # plus 0,1 Prozent, mehr Volumen: Stalling Day
    c[20], v[20] = 99.85, 1300.0         # minus 0,15 Prozent, mehr Volumen: seit Nachfrage N5 Stalling Day
    c[25], v[25] = 99.0, 1500.0          # Distribution Day
    dd = distribution_days(t30, h, c, v, fenster=25, verlust_pct=0.2, verfall_pct=5.0, stall_pct=0.2)
    p("Distribution Days ab minus 0,2 Prozent und Stalling Days unter plus 0,2 Prozent, beide bei hoeherem "
      "Volumen, nur in 25 Sitzungen; minus 0,15 Prozent ist seit Nachfrage N5 ein Stalling Day",
      dd == [(t30[10], -0.3, "distribution"), (t30[18], 0.1, "stalling"), (t30[20], -0.15, "stalling"),
             (t30[25], -1.0, "distribution")], dd)
    h2 = list(h)
    h2[15] = 99.7 * 1.051
    p("Distribution Days: verfallen, sobald ein Tageshoch danach 5 Prozent ueber dem Schluss liegt",
      [x[0] for x in distribution_days(t30, h2, c, v, 25, 0.2, 5.0, 0.2)] == [t30[18], t30[20], t30[25]])
    p("Distribution Days: aelter als das Fenster zaehlt nicht",
      [x[0] for x in distribution_days(t30, h, c, v, 12, 0.2, 5.0, 0.2)] == [t30[18], t30[20], t30[25]]
      and [x[0] for x in distribution_days(t30, h, c, v, 11, 0.2, 5.0, 0.2)] == [t30[20], t30[25]]
      and [x[0] for x in distribution_days(t30, h, c, v, 9, 0.2, 5.0, 0.2)] == [t30[25]])
    # Follow-through Day
    n = 120
    tage = _handelstage(n)
    closes = [100.0 + i * 0.2 for i in range(60)]
    for _ in range(20):
        closes.append(closes[-1] * 0.985)
    tief = len(closes) - 1
    closes += [closes[-1] * 1.004]
    closes += [closes[-1] * 1.006]
    closes += [closes[-1] * 1.007]
    closes += [closes[-1] * 1.003]
    ftd_i = len(closes)
    closes.append(closes[-1] * 1.016)
    while len(closes) < n:
        closes.append(closes[-1] * 1.002)
    lows = [x * 0.995 for x in closes]
    vols = [1000.0] * n
    vols[ftd_i] = 1500.0
    ph = follow_through(tage, lows, closes, vols, 50, 25, 4, 1.25)
    p("Follow-through Day: Tief unter der 50-Tage-Linie, Tag 1 danach, Anstieg ab 1,25 Prozent mit mehr "
      "Volumen an Tag 5",
      ph["zustand"] == "bestaetigt" and ph["korrektur_tag"] == tage[tief] and ph["ftd_tag"] == tage[ftd_i]
      and ph["ftd_pct"] == 1.6 and ph["ftd_gescheitert"] is False, ph)
    vols_ohne = list(vols)
    vols_ohne[ftd_i] = 900.0
    ph2 = follow_through(tage, lows, closes, vols_ohne, 50, 25, 4, 1.25)
    p("Follow-through Day: ohne hoeheres Volumen keiner, der Erholungsversuch laeuft weiter",
      ph2["zustand"] == "erholungsversuch" and ph2["ftd_tag"] is None and ph2["versuch_tag"] == n - (tief + 1), ph2)
    lows_bruch = list(lows)
    lows_bruch[ftd_i + 3] = lows[ftd_i] * 0.99
    ph3 = follow_through(tage, lows_bruch, closes, vols, 50, 25, 4, 1.25)
    p("Follow-through Day: gescheitert, sobald der Index das Tagestief des Tages unterschreitet",
      ph3["ftd_gescheitert"] is True and ph3["ftd_gescheitert_tag"] == tage[ftd_i + 3], ph3)
    p("Follow-through Day gescheitert: ohne neues Tief beginnt mit dem naechsten hoeheren Schluss ein neuer "
      "Erholungsversuch (Nachfrage N7)",
      ph3["zustand"] == "erholungsversuch" and ph3["versuch_grund"] == "ftd_gescheitert"
      and ph3["korrektur_tag"] == tage[ftd_i + 3] and ph3["tag1"] == tage[ftd_i + 4]
      and ph3["versuch_tag"] == n - (ftd_i + 4), ph3)
    closes_neu = list(closes)
    for i in range(ftd_i + 8, n):
        closes_neu[i] = closes[i] * 1.016
    vols_neu = list(vols)
    vols_neu[ftd_i + 8] = 1600.0
    ph3b = follow_through(tage, lows_bruch, closes_neu, vols_neu, 50, 25, 4, 1.25)
    p("Follow-through Day gescheitert: im neuen Erholungsversuch zaehlt ab Tag 4 ein neuer Follow-through Day",
      ph3b["zustand"] == "bestaetigt" and ph3b["ftd_tag"] == tage[ftd_i + 8] and ph3b["ftd_gescheitert"] is False
      and ph3b["versuch_grund"] == "ftd_gescheitert", ph3b)
    lows_zweimal = list(lows_bruch)
    lows_zweimal[ftd_i + 6] = lows_bruch[ftd_i + 3] * 0.99
    ph3c = follow_through(tage[:ftd_i + 7], lows_zweimal[:ftd_i + 7], closes[:ftd_i + 7], vols[:ftd_i + 7],
                          50, 25, 4, 1.25)
    p("Follow-through Day gescheitert: unterschreitet der Index danach das Tagestief des Scheiterns, beginnt die "
      "Zaehlung neu",
      ph3c["zustand"] == "korrektur" and ph3c["korrektur_tag"] == tage[ftd_i + 6]
      and ph3c["versuch_grund"] == "ftd_gescheitert", ph3c)
    closes_frueh = list(closes)
    closes_frueh[tief + 3] = closes[tief + 2] * 1.02
    vols_frueh = [1000.0] * n
    vols_frueh[tief + 3] = 1500.0
    ph4 = follow_through(tage, lows, closes_frueh[:tief + 4], vols_frueh[:tief + 4], 50, 25, 4, 1.25)
    p("Follow-through Day: an Tag 3 zaehlt ein grosser Anstieg noch nicht",
      ph4["zustand"] == "erholungsversuch" and ph4["ftd_tag"] is None and ph4["versuch_tag"] == 3, ph4)
    lows_unter = list(lows)
    lows_unter[tief + 2] = lows[tief] * 0.98
    ph5 = follow_through(tage[:tief + 3], lows_unter[:tief + 3], closes[:tief + 3], vols[:tief + 3], 50, 25, 4, 1.25)
    p("Follow-through Day: unterschreitet der Index das Tagestief des Tiefs, beginnt die Zaehlung neu",
      ph5["zustand"] == "korrektur" and ph5["korrektur_tag"] == tage[tief + 2], ph5)
    closes_tiefer = list(closes)
    lows_tiefer = list(lows)
    closes_tiefer[tief + 2] = closes[tief] * 0.999
    lows_tiefer[tief + 2] = lows[tief] * 1.001
    ph6 = follow_through(tage, lows_tiefer, closes_tiefer, vols, 50, 25, 4, 1.25)
    p("Follow-through Day: ein tieferer Schluss ohne unterschrittenes Tagestief beendet den Versuch nicht",
      ph6["zustand"] == "bestaetigt" and ph6["ftd_tag"] == tage[ftd_i], ph6)
    gesammelt = []
    follow_through(tage, lows_bruch, closes_neu, vols_neu, 50, 25, 4, 1.25, tiefs=gesammelt)
    p("Markttiefs fuer die Stufenzaehlung: das Tief vor dem ersten Follow-through Day und der Tag, an dem er "
      "scheiterte, weil ihn ein neuer Follow-through Day bestaetigt (Nachfrage N7)",
      gesammelt == [tage[tief], tage[ftd_i + 3]], gesammelt)
    gesammelt = []
    follow_through(tage, lows, closes, vols_ohne, 50, 25, 4, 1.25, tiefs=gesammelt)
    p("Markttiefs: ein Tief ohne Follow-through Day ist keines", gesammelt == [], gesammelt)
    p("Follow-through Day: ohne Tief kein Zustand",
      follow_through(tage, [x * 0.99 for x in range(100, 220)], [float(x) for x in range(100, 220)],
                     [1.0] * 120, 50, 25, 4, 1.25)["zustand"] == "keine")
    # McClellan
    osz = mcclellan([100.0] * 60, 19, 39, 0.10, 0.05)
    p("McClellan: gleichbleibende Net Advances ergeben null, vor 39 Werten nichts",
      osz[37] is None and abs(osz[-1]) < 1e-9)
    rana = [0.0] * 40 + [500.0] * 20
    osz2 = mcclellan(rana, 19, 39, 0.10, 0.05)
    e19 = sum(rana[:19]) / 19
    e39 = sum(rana[:39]) / 39
    for x in rana[19:]:
        e19 = (x - e19) * 0.10 + e19
    for x in rana[39:]:
        e39 = (x - e39) * 0.05 + e39
    p("McClellan: Sprung nach oben ergibt einen positiven Oszillator, von Hand nachgerechnet",
      osz2[-1] > 0 and abs(osz2[-1] - (e19 - e39)) < 1e-9, osz2[-1])
    # Breite an einem kleinen Universum
    tage300 = _handelstage(300)

    def reihe(start, schritt, volumen=200000.0, tage_r=None):
        tage_r = tage_r or tage300
        cc = [start * (1 + schritt) ** i for i in range(len(tage_r))]
        return {"daten": list(tage_r), "close": cc, "high": [x * 1.01 for x in cc], "low": [x * 0.99 for x in cc],
                "volume": [volumen + i for i in range(len(tage_r))]}
    auf = [reihe(20.0, 0.002) for _ in range(6)]
    ab = [reihe(50.0, -0.002) for _ in range(3)]
    sprung = reihe(20.0, 0.0)
    sprung["close"][-1] = sprung["close"][-2] * 1.05
    sprung["high"][-1] = sprung["close"][-1] * 1.01
    alt = reihe(30.0, 0.001, tage_r=tage300[:-1])
    b = breite(auf + ab + [sprung, alt])
    p("Breite: Steiger und Faller vom Handelstag, eine veraltete Reihe zaehlt dort nicht",
      b["handelstag"] == tage300[-1] and b["steiger"] == 7 and b["faller"] == 3 and b["aktien_heute"] == 10
      and b["reihen"] == 11 and b["unvollstaendige_tage"] == [], b)
    p("Breite: Anteil ueber SMA 50 und 200, Basis sind die Reihen vom Handelstag",
      b["ueber_sma50_pct"] == 70.0 and b["sma200_basis"] == 10, b)
    p("Breite: neue 52-Wochen-Hochs und Tiefs, ein Gleichstand zaehlt nicht",
      b["neue_hochs"] == 7 and b["neue_tiefs"] == 3, (b["neue_hochs"], b["neue_tiefs"]))
    p("Breite: Stockbee plus 4 Prozent verlangt mehr Volumen als am Vortag und mindestens 100.000 Stueck",
      b["stockbee"]["plus4"] == 1 and b["stockbee"]["minus4"] == 0 and b["stockbee"]["verh5"] is None, b["stockbee"])
    p("Breite: McClellan vorhanden, bei gleichbleibendem Verhaeltnis nahe null",
      b["mcclellan"] is not None and abs(b["mcclellan"]) <= 1.0, b["mcclellan"])
    tage301 = _handelstage(301)
    extra = reihe(20.0, 0.002, tage_r=tage301)
    b2 = breite(auf + ab + [sprung, alt, extra])
    p("Breite: ein Tag, den nur ein Bruchteil der Aktien hat, gilt als unvollstaendig; gerechnet wird bis "
      "zum letzten vollstaendigen Tag",
      b2["handelstag"] == tage300[-1] and b2["unvollstaendige_tage"] == [tage301[-1]] and b2["steiger"] == 8
      and b2["aktien_heute"] == 11, b2)
    quartal = reihe(10.0, 0.0)
    quartal["close"] = [10.0] * 235 + [10.0 + 0.05 * i for i in range(65)]
    q = breite([quartal] + auf)["stockbee"]
    p("Breite: Stockbee 25 Prozent im Quartal gegen den tiefsten Schluss der 65 Tage",
      q["plus25_quartal"] == 1 and q["plus25_monat"] == 0 and q["plus13_34t"] >= 1, q)
    # Saetze
    probe = {**b, "stockbee": {"plus4": 180, "minus4": 95, "verh5": 1.6}, "steiger": 2310, "faller": 1876,
             "mcclellan": 45.2, "summation_trend": 12.0, "ueber_sma50_pct": 58.4, "ueber_sma200_pct": 61.2,
             "neue_hochs": 85, "neue_tiefs": 40}
    z = breite_zeile(probe, tage300[-1])
    p("Zeile: Steiger, Faller, McClellan, Anteile, Hochs und Tiefs, Stockbee; Meldungsformat",
      z == (f"Marktbreite zum Schluss vom {_datum_de(tage300[-1])}, 2.310 Steiger und 1.876 Faller; "
            "McClellan-Oszillator plus 45, Summation Index steigend; 58 Prozent über SMA 50, "
            "61 Prozent über SMA 200; 85 neue 52-Wochen-Hochs und 40 neue Tiefs; Stockbee 180 Aktien mit "
            "plus 4 Prozent und 95 mit minus 4 Prozent, Verhältnis über 5 Tage 1,60")
      and not any(ch in z for ch in ("—", "–", "|")), z)
    p("Zeile: vom falschen Schluss keine Zahl, ohne Daten ehrlich nicht verfuegbar",
      breite_zeile(b, "2020-01-02").startswith("Marktbreite nicht verfügbar, die letzte Berechnung gilt")
      and breite_zeile(None).startswith("Marktbreite nicht verfügbar")
      and breite_zeile({"fehler": "KeyError: 'daten'"}) == "Marktbreite nicht verfügbar, die letzte Berechnung ist gescheitert"
      and bericht_zeilen({"fehler": "x"}) == ["Marktbreite nicht verfügbar, die letzte Berechnung ist gescheitert"])
    pt = phase_text({"distribution_days": [{"tag": "2026-09-01", "pct": -0.5, "art": "distribution"}] * 3
                     + [{"tag": "2026-09-02", "pct": 0.1, "art": "stalling"}], "dd_fenster": 25,
                     "volumen_letzter_tag": True,
                     "phase": {"zustand": "bestaetigt", "ftd_tag": "2026-08-20", "ftd_pct": 1.62, "ftd_gescheitert": False}})
    p("Phase: Distribution Days samt Stalling Day, Zaehlung nach IBD, Follow-through Day",
      pt == "4 Distribution Days in 25 Sitzungen, davon 1 Stalling Day, nach IBD-Zählung unter Druck, "
            "Follow-through Day am 20.08.2026 mit plus 1,62 Prozent", pt)
    pt2 = phase_text({"distribution_days": [{"tag": "2026-09-01", "pct": -0.5, "art": "distribution"}],
                      "dd_fenster": 25, "phase": {"zustand": "erholungsversuch", "versuch_tag": 3,
                                                  "korrektur_tag": "2026-09-08"}})
    p("Phase: ein Distribution Day, Erholungsversuch",
      pt2 == "1 Distribution Day in 25 Sitzungen, Erholungsversuch am Tag 3 seit dem Tief vom 08.09.2026", pt2)
    pt3 = phase_text({"distribution_days": [], "dd_fenster": 25, "volumen_letzter_tag": False,
                      "phase": {"zustand": "korrektur", "korrektur_tag": "2026-09-08"}})
    p("Phase: keiner, fehlendes Volumen, Tief ohne Erholungsversuch",
      pt3 == "kein Distribution Day in 25 Sitzungen, Volumen des letzten Tages fehlt, Tief vom 08.09.2026, "
             "noch kein Erholungsversuch", pt3)
    gesch = {"ftd_tag": "2026-08-27", "ftd_pct": 1.4, "ftd_gescheitert": True, "ftd_gescheitert_tag": "2026-08-31",
             "versuch_grund": "ftd_gescheitert"}
    pt4 = phase_text({"distribution_days": [], "dd_fenster": 25,
                      "phase": dict(gesch, zustand="erholungsversuch", versuch_tag=5, korrektur_tag="2026-08-31")})
    pt5 = phase_text({"distribution_days": [], "dd_fenster": 25,
                      "phase": dict(gesch, zustand="korrektur", korrektur_tag="2026-09-03")})
    p("Phase: neuer Erholungsversuch nach gescheitertem Follow-through Day, und noch keiner (Nachfrage N7)",
      pt4 == "kein Distribution Day in 25 Sitzungen, Follow-through Day vom 27.08.2026 gescheitert am 31.08.2026, "
             "neuer Erholungsversuch am Tag 5 seit dem Tagestief vom 31.08.2026"
      and pt5 == "kein Distribution Day in 25 Sitzungen, Follow-through Day vom 27.08.2026 gescheitert am 31.08.2026, "
                 "tieferes Tagestief am 03.09.2026, noch kein neuer Erholungsversuch", f"{pt4} / {pt5}")
    bz = bericht_zeilen({**b, "hochs_tiefs_mittel": 12.5})
    p("Bericht: Breite je Zeile, Stockbee ganz",
      bz[0].startswith("Marktbreite: 7 Steiger, 3 Faller, 0 unverändert; A/D-Linie über 10 Tage plus")
      and any("im Quartal plus 25 Prozent" in x and "in 34 Tagen plus 13 Prozent" in x for x in bz), bz)
    # Die Ampel-Zeile samt Breite (marktampel.zeile) und der Abendbericht-Absatz
    lage = {"ueber_ema21": True, "ueber_sma50": True, "ema21_ueber_sma50": True, "sma50_steigt": True,
            "distribution_days": [{"tag": "2026-09-10", "pct": -0.4, "art": "distribution"}], "dd_fenster": 25,
            "volumen_letzter_tag": True, "phase": {"zustand": "keine"}}
    amp = {"farbe": "gruen", "handelstag": tage300[-1], "indizes": {"S&P 500": lage, "Nasdaq": lage}}
    za = marktampel.zeile(amp, tage300[-1], probe)
    p("Ampel-Zeile: Farbe, je Index Linien und Distribution Days, dahinter die Breite in derselben Zeile",
      za == (f"Marktampel grün, Schluss vom {_datum_de(tage300[-1])}; S&P 500 über EMA 21 und SMA 50, SMA 50 "
             "steigt, 1 Distribution Day in 25 Sitzungen; Nasdaq über EMA 21 und SMA 50, SMA 50 steigt, "
             "1 Distribution Day in 25 Sitzungen; Marktbreite 2.310 Steiger und 1.876 Faller; McClellan-Oszillator "
             "plus 45, Summation Index steigend; 58 Prozent über SMA 50, 61 Prozent über SMA 200; 85 neue "
             "52-Wochen-Hochs und 40 neue Tiefs; Stockbee 180 Aktien mit plus 4 Prozent und 95 mit minus 4 "
             "Prozent, Verhältnis über 5 Tage 1,60"), za)
    zb = marktampel.zeile(amp, "2030-01-02", probe)
    p("Ampel-Zeile: eine alte Ampel und eine alte Breite zeigen keine Zahl",
      zb.startswith("Marktampel nicht verfügbar; die letzte Berechnung gilt dem Schluss vom")
      and "Marktbreite nicht verfügbar, die letzte Berechnung gilt" in zb and "Steiger" not in zb, zb)
    zc = marktampel.zeile(None, tage300[-1], probe)
    p("Ampel-Zeile: ohne Ampel, aber mit frischer Breite nennt die Breite ihren Schluss selbst",
      zc.startswith("Marktampel nicht verfügbar; es liegt keine Berechnung vor; Marktbreite zum Schluss vom"), zc)
    absatz = marktampel.bericht_absatz(amp, probe, tage300[-1])
    p("Abendbericht: nummerierte Zeilen, Farbe, je Index, Breite",
      absatz.startswith("Marktampel und Marktbreite, reine Anzeige, die Ampel filtert nichts:\n1. Marktampel grün\n"
                        "2. S&P 500 über EMA 21 und SMA 50, SMA 50 steigt, 1 Distribution Day in 25 Sitzungen\n"
                        "3. Nasdaq ") and "\n4. Marktbreite: 2.310 Steiger" in absatz, absatz)
    absatz2 = marktampel.bericht_absatz({**amp, "handelstag": "2026-01-02"}, probe, tage300[-1])
    p("Abendbericht: eine Ampel von einem anderen Schluss steht nicht als Farbe da",
      "1. Marktampel nicht verfügbar, die letzte Berechnung gilt dem Schluss vom 02.01.2026" in absatz2
      and "grün" not in absatz2, absatz2)
    app = re.compile(r"(Kaufpunkt|Kurs|Stop|Ziel|Exit-Linie)\s+(\(Folgetag\)\s+)?\d")
    p("Keine Zeile traegt ein Wortpaar, an dem die Handels-App einen Alarm erkennt",
      not any(app.search(s) for s in (z, pt, pt2, pt3, za, zb, zc, absatz, absatz2, breite_zeile(None))))
    p("Keine Zeile traegt einen Gedankenstrich oder senkrechten Strich",
      not any(ch in s for s in (z, pt, pt2, pt3, za, zb, zc, absatz, absatz2) for ch in ("—", "–", "|")))

    print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles bestanden.")
    return 1 if fehler else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Marktbreite und Marktphase (Etappe 3).")
    ap.add_argument("--selbsttest", action="store_true")
    args = ap.parse_args()
    if args.selbsttest:
        return selbsttest()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
