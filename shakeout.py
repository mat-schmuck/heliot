#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SHAKEOUT-SPRING — Kapitel 10 (Wyckoff), Fassung v2 vom 02.08.2026
==================================================================
Portiert aus Gerhards shakeout_engine.py. Die Logik ist unverändert
übernommen; geändert sind nur die Anbindung (Einstellungen kommen aus
config.py statt aus einem eigenen CFG) und die Kommentare.

DIE IDEE
    Eine Aktie im Aufwärtstrend unterschreitet kurz eine starke
    Unterstützungszone, erobert sie am selben Tag zurück und schließt im
    oberen Drittel der Tagesspanne. Wyckoff nennt das einen "Spring":
    die letzten Zittrigen werden ausgeschüttelt, danach fehlt das
    Angebot.

ZWEI BETRIEBSARTEN
    Sofort-Modus (erkenne_shakeout_setup) meldet am Rückeroberungstag.
    Sekundärtest-Modus wartet zusätzlich auf einen Rücksetzer mit
    GERINGEREM Volumen, der die Zone noch einmal testet und hält.

    GERHARDS EMPFEHLUNG FÜR DEN LIVE-START ist der Sekundärtest-Modus.
    Aus seinem Backtest (182 Aktien, 60/40-Aufteilung ohne Zukunftswissen):
        Signale             31 sofort  gegen  20 mit Test
        Treffer nach  5 Tagen  64,5 %          60,0 %
        Treffer nach 10 Tagen  61,3 %          65,0 %
        Treffer nach 20 Tagen  54,8 %          60,0 %
        Streuung nach 20 Tagen 21,1 %          19,3 %
    Also: ein Drittel weniger Signale, dafür bei zwei von drei Horizonten
    die bessere Trefferquote und durchgehend die geringere Streuung.

WAS GERHARD SELBST EINSCHRÄNKT (wörtlich übernommen, damit es nicht
verlorengeht):
    - Die Stichprobe ist klein und geclustert: bei 20 Signalen stellen
      drei Symbole die Hälfte. "Als vielversprechenden Start behandeln,
      nicht als Beweis." Kleine Positionsgrößen, Mitschreiben Pflicht.
    - Der Level-Score korrelierte im Backtest kaum mit der späteren
      Rendite (Korrelation rund 0). Die Schwelle von 55 ist ein grober
      Vorfilter, kein Qualitätsbeweis.
    - Das Volumenprofil ist vereinfacht: Das Tagesvolumen wird dem
      Schlusskurs zugeschlagen, statt es über die Tagesspanne zu
      verteilen. Für den Score reicht das.

    Ein Befund, der umgekehrt Vertrauen schafft: Von 46 geprüften
    Spring-Ereignissen brachen 7 die Struktur, also 15,2 % — das deckt
    sich fast genau mit dem unabhängig in der Wyckoff-Literatur
    genannten Wert von rund 15 %.

Aufruf:
    python shakeout.py --selbsttest        Rechenwege gegen Kunstdaten
"""

import argparse
import sys

import numpy as np
import pandas as pd

from config import CFG as _ALLE

CFG = _ALLE["shakeout"]


# ---------------------------------------------------------------------------
# Hilfsdaten
# ---------------------------------------------------------------------------

def aus_scanner_df(df):
    """Die Tagesdaten des Scanners in die Form bringen, die diese
    Maschine erwartet.

    Der Scanner führt Spalten klein geschrieben und einen Laufindex,
    Gerhards Vorlage groß geschrieben und einen Datumsindex — den
    braucht sie für die Wochenkerzen (resample) und für das Datum des
    Spring-Tages. Übersetzt wird hier an genau einer Stelle, statt
    beide Seiten aneinander anzupassen."""
    spalten = {"open": "Open", "high": "High", "low": "Low",
               "close": "Close", "volume": "Volume"}
    fehlend = [s for s in spalten if s not in df.columns]
    if fehlend:
        raise KeyError(f"Spalten fehlen: {', '.join(fehlend)}")
    neu = df.rename(columns=spalten)[list(spalten.values())].copy()
    neu.index = pd.to_datetime(df["datetime"])
    return neu


def wochenkurse_aus_tageskursen(df_tage):
    """Tagesdaten zu Wochenkerzen zusammenfassen.

    Der Wochenchart dient nur einem Zweck: Liegt eine Tageszone auch auf
    Wochenebene auf einem Extrempunkt, zählt sie mehr. Eine Zone, die
    zwei Zeitebenen gleichzeitig sehen, ist die belastbarere."""
    return df_tage.resample("W").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum"}).dropna()


# ---------------------------------------------------------------------------
# Trendkontext — drei Pflichtbedingungen
# ---------------------------------------------------------------------------

def pruefe_trendkontext(df):
    """Nur Aktien in einem intakten Aufwärtstrend kommen in Frage.

    Ein Spring unter einer Zone ist im Abwärtstrend kein Ausschütteln,
    sondern schlicht der nächste Abwärtsschritt. Deshalb drei
    Bedingungen zugleich: über dem 200er-Schnitt, mindestens verdoppelt
    seit dem 52-Wochen-Tief, und der 200er-Schnitt selbst steigt."""
    close = df["Close"]
    ma200 = close.rolling(CFG["ma_lang"]).mean()

    kurs = float(close.iloc[-1])
    ma200_heute = float(ma200.iloc[-1])
    ueber_ma200 = (not np.isnan(ma200_heute)) and kurs > ma200_heute

    tief_52w = float(df["Low"].tail(252).min())
    ueber_tief_pct = (kurs / tief_52w - 1) if tief_52w > 0 else 0
    verdoppelt = ueber_tief_pct >= CFG["min_ueber_52w_tief"]

    n = CFG["stage2_min_tage_steigend"]
    ma200_vorher = float(ma200.iloc[-1 - n]) if len(ma200) > n else np.nan
    stage2 = (not np.isnan(ma200_heute) and not np.isnan(ma200_vorher)
              and ma200_heute > ma200_vorher)

    return {
        "ok": bool(ueber_ma200 and verdoppelt and stage2),
        "ueber_ma200": ueber_ma200, "kurs": kurs, "ma200": ma200_heute,
        "ueber_52w_tief_pct": round(ueber_tief_pct * 100, 1),
        "verdoppelt": verdoppelt, "stage2_ma200_steigend": stage2,
    }


# ---------------------------------------------------------------------------
# Swing-Punkte und Zonen
# ---------------------------------------------------------------------------

def finde_swing_punkte(df, order=None):
    """Lokale Hochs und Tiefs. Bewusst ohne scipy — das Paket wäre eine
    weitere Abhängigkeit für eine Handvoll Vergleiche."""
    order = order or CFG["swing_order"]
    highs, lows = [], []
    h, l = df["High"].values, df["Low"].values
    for i in range(order, len(df) - order):
        if h[i] >= h[i - order: i + order + 1].max():
            highs.append((i, float(h[i])))
        if l[i] <= l[i - order: i + order + 1].min():
            lows.append((i, float(l[i])))
    return highs, lows


def cluster_zonen(punkte, toleranz=None):
    """Nahe beieinanderliegende Extrempunkte zu einer Preiszone bündeln.

    Ein Level ist selten ein exakter Preis, sondern ein Bereich. Punkte
    innerhalb der Toleranz gehören zusammen; je mehr Berührungen, desto
    bedeutsamer die Zone."""
    toleranz = toleranz if toleranz is not None else CFG["cluster_toleranz"]
    if not punkte:
        return []
    sortiert = sorted(punkte, key=lambda p: p[1])
    zonen, aktuelle = [], [sortiert[0]]
    for idx, preis in sortiert[1:]:
        zentrum = np.mean([p[1] for p in aktuelle])
        if abs(preis - zentrum) / zentrum <= toleranz:
            aktuelle.append((idx, preis))
        else:
            zonen.append(aktuelle)
            aktuelle = [(idx, preis)]
    zonen.append(aktuelle)

    ergebnis = []
    for z in zonen:
        preise = [p[1] for p in z]
        ergebnis.append({
            "mitte": float(np.mean(preise)), "min": float(min(preise)),
            "max": float(max(preise)), "treffer": len(z),
            "indices": [p[0] for p in z],
        })
    return ergebnis


# ---------------------------------------------------------------------------
# Volumenprofil
# ---------------------------------------------------------------------------

def volumen_profil(df, n_bins=40):
    """Wo im Kursbereich wurde am meisten umgesetzt?

    Vereinfachung, die Gerhard ausdrücklich benennt: Das Tagesvolumen
    wird dem Schlusskurs zugeschlagen, statt es anteilig über die
    Tagesspanne zu verteilen. Für den Level-Score reicht das."""
    lo, hi = float(df["Low"].min()), float(df["High"].max())
    bins = np.linspace(lo, hi, n_bins + 1)
    idx = np.clip(np.digitize(df["Close"].values, bins) - 1, 0, n_bins - 1)
    vol_je_bin = np.zeros(n_bins)
    for i, v in zip(idx, df["Volume"].values):
        vol_je_bin[i] += v
    return pd.DataFrame({"bin_mitte": (bins[:-1] + bins[1:]) / 2,
                         "volumen": vol_je_bin})


def volumen_rang_fuer_preis(vol_profil, preis):
    """Perzentilrang des Volumens auf diesem Preisniveau, 0 bis 100."""
    idx = (vol_profil["bin_mitte"] - preis).abs().idxmin()
    ziel_vol = vol_profil.loc[idx, "volumen"]
    return float((vol_profil["volumen"] <= ziel_vol).mean() * 100)


# ---------------------------------------------------------------------------
# Level-Score aus fünf Faktoren
# ---------------------------------------------------------------------------

def berechne_level_scores(df, df_wochen=None):
    """Kandidatenzonen bauen und jede mit fünf Faktoren bewerten.

    Rückgabe absteigend nach Punktzahl. ACHTUNG bei der Auslegung: Im
    Backtest korrelierte diese Zahl kaum mit der späteren Rendite. Sie
    ist ein grober Vorfilter, kein Qualitätsmaß."""
    highs, lows = finde_swing_punkte(df)
    zonen = cluster_zonen(highs + lows)
    if not zonen:
        return []

    vol_profil = volumen_profil(df)
    ma50 = df["Close"].rolling(50).mean().iloc[-1]
    ma200 = df["Close"].rolling(CFG["ma_lang"]).mean().iloc[-1]

    wochen_zonen = []
    if df_wochen is not None and len(df_wochen) > 2 * CFG["swing_order_wochen"] + 1:
        wh, wl = finde_swing_punkte(df_wochen, order=CFG["swing_order_wochen"])
        wochen_zonen = cluster_zonen(wh + wl, toleranz=CFG["cluster_toleranz"])

    n_treffer_max = max(z["treffer"] for z in zonen)
    gewichte_summe = (CFG["gewicht_beruehrungen"] + CFG["gewicht_volumen"]
                      + CFG["gewicht_alter_extrempunkt"]
                      + CFG["gewicht_wochenchart"] + CFG["gewicht_ma_naehe"])

    ergebnis = []
    for z in zonen:
        # Je später der älteste Berührungspunkt liegt, desto frischer die
        # Zone — alte Zonen sind oft schon abgearbeitet.
        alter_score = min(min(z["indices"]) / max(len(df) - 1, 1), 1.0) * 100
        beruehr_score = (z["treffer"] / n_treffer_max) * 100
        vol_score = volumen_rang_fuer_preis(vol_profil, z["mitte"])

        wochen_bonus = 100 if any(wz["min"] <= z["mitte"] <= wz["max"]
                                  for wz in wochen_zonen) else 0
        ma_bonus = 0
        for ma_wert in (ma50, ma200):
            if (not np.isnan(ma_wert)
                    and abs(z["mitte"] - ma_wert) / ma_wert <= CFG["ma_naehe_toleranz"]):
                ma_bonus = 100
                break

        score = (beruehr_score * CFG["gewicht_beruehrungen"]
                 + vol_score * CFG["gewicht_volumen"]
                 + alter_score * CFG["gewicht_alter_extrempunkt"]
                 + wochen_bonus * CFG["gewicht_wochenchart"]
                 + ma_bonus * CFG["gewicht_ma_naehe"]) / gewichte_summe

        ergebnis.append({**z, "score": round(score, 1), "teilfaktoren": {
            "beruehrungen": round(beruehr_score, 1),
            "volumen": round(vol_score, 1), "alter": round(alter_score, 1),
            "wochenchart_bonus": wochen_bonus, "ma_naehe_bonus": ma_bonus,
        }})
    ergebnis.sort(key=lambda z: -z["score"])
    return ergebnis


# ---------------------------------------------------------------------------
# Der Trigger für einen einzelnen Tag
# ---------------------------------------------------------------------------

def pruefe_shakeout_tag(tag, zone):
    """Ist DIESER Tag ein gültiger Shakeout der Zone?

    Vier Bedingungen: Die Zone wurde unterschritten, aber nicht zu tief
    (sonst ist es ein Bruch und kein Ausschütteln), am Schluss ist sie
    zurückerobert, und der Schluss liegt im oberen Drittel der
    Tagesspanne."""
    tief, hoch = float(tag["Low"]), float(tag["High"])
    schluss = float(tag["Close"])
    zone_min, zone_max = zone["min"], zone["max"]

    unterschritten = tief < zone_min
    tiefe_pct = (zone_min - tief) / zone_min if unterschritten else 0
    nicht_zu_tief = tiefe_pct <= CFG["shakeout_toleranz"]
    zurueckerobert = schluss > zone_max

    spanne = hoch - tief
    schluss_position = (schluss - tief) / spanne if spanne > 0 else 0
    starker_schluss = schluss_position >= CFG["schluss_oberste_pct"]

    ok = bool(unterschritten and nicht_zu_tief and zurueckerobert
              and starker_schluss)
    return {
        "ok": ok, "unterschritten": unterschritten,
        "tiefe_unter_zone_pct": round(tiefe_pct * 100, 2),
        "nicht_zu_tief": nicht_zu_tief, "zurueckerobert": zurueckerobert,
        "schluss_position_pct": round(schluss_position * 100, 1),
        "starker_schluss": starker_schluss,
        "kaufpunkt": round(zone_max, 2) if ok else None,
        "stop": round(tief, 2) if ok else None,
    }


# ---------------------------------------------------------------------------
# Einordnung und Ziele
# ---------------------------------------------------------------------------

def klassifiziere_volumen_typ(tag, df_bis_hier, fenster=None):
    """Wyckoffs Volumentypen am Spring-Tag — reine Einordnung, kein Filter.

    Typ 1 (wenig Volumen) hat laut Literatur die höchste
    Erfolgswahrscheinlichkeit: Es kam gar kein Angebot mehr.
    Typ 3 (viel Volumen) ist aggressiv und sollte den Sekundärtest
    unbedingt abwarten."""
    fenster = fenster or CFG["vol_typ_fenster"]
    vol_avg = float(df_bis_hier["Volume"].tail(fenster).mean())
    if vol_avg <= 0:
        return "unbekannt", None
    verhaeltnis = float(tag["Volume"]) / vol_avg
    if verhaeltnis < CFG["vol_typ1_max"]:
        typ = "Typ 1, wenig Volumen; höchste Erfolgswahrscheinlichkeit"
    elif verhaeltnis > CFG["vol_typ3_min"]:
        typ = "Typ 3, viel Volumen; Sekundärtest unbedingt abwarten"
    else:
        typ = "Typ 2, mittleres Volumen; Test empfohlen"
    return typ, round(verhaeltnis, 2)


def berechne_kursziel(zone):
    """Wyckoffs Zielprojektion: Höhe der Zone auf ihre Oberkante gesetzt."""
    hoehe = zone["max"] - zone["min"]
    return round(zone["max"] + hoehe * CFG["kursziel_faktor"], 2)


def pruefe_exit_invalidierung(df, ab_index, spring_low):
    """Fällt ein SCHLUSSKURS unter das Spring-Tief, ist die Struktur
    entwertet — unabhängig vom gesetzten Stop.

    Bewusst der Schluss und nicht der Docht: Ein kurzer Wisch unter die
    Marke wirft sonst sofort hinaus, obwohl der Tag darüber schließt."""
    for j in range(ab_index, len(df)):
        if float(df["Close"].iloc[j]) < spring_low:
            return True, j
    return False, None


def suche_sekundaertest(df, spring_index, zone, spring_volumen):
    """Den bestätigenden Rücksetzer suchen.

    Gültig ist er, wenn der Kurs noch einmal in die Zone zurückkommt,
    dabei über dem Spring-Tief hält UND das mit weniger Volumen tut als
    am Spring-Tag. Weniger Volumen heißt: Es drängt kein Verkäufer mehr
    nach."""
    spring_low = float(df["Low"].iloc[spring_index])
    grenze = 1 - CFG["sekundaertest_max_zusatz_unterschreitung"]
    max_j = min(spring_index + 1 + CFG["sekundaertest_max_wartetage"], len(df))

    for j in range(spring_index + 1, max_j):
        tag = df.iloc[j]
        if float(tag["Close"]) < spring_low * grenze:
            return {"gefunden": False, "bruch_index": j,
                    "grund": "Struktur gebrochen, Schluss unter dem Spring-Tief"}
        tief = float(tag["Low"])
        if (tief <= zone["max"] and tief >= spring_low * grenze
                and float(tag["Volume"]) < spring_volumen):
            return {
                "gefunden": True, "index": j, "datum": df.index[j],
                "test_tief": tief, "test_schluss": float(tag["Close"]),
                "test_volumen": float(tag["Volume"]),
                "volumen_relativ_zu_spring":
                    round(float(tag["Volume"]) / spring_volumen, 2),
            }
    return {"gefunden": False,
            "grund": "Kein Rücksetzer im Wartefenster, die Aktie lief ohne "
                     "Test davon"}


# ---------------------------------------------------------------------------
# Die drei Einstiegspunkte
# ---------------------------------------------------------------------------

def _starke_zonen(df, df_wochen):
    if df_wochen is None:
        df_wochen = wochenkurse_aus_tageskursen(df.iloc[:-1])
    zonen = berechne_level_scores(df.iloc[:-1], df_wochen)
    return [z for z in zonen if z["score"] >= CFG["level_score_schwelle"]]


def erkenne_shakeout_setup(df, df_wochen=None):
    """Sofort-Modus: meldet am Rückeroberungstag selbst.

    Bleibt verfügbar, ist aber nicht die Empfehlung für den Live-Start."""
    trend = pruefe_trendkontext(df)
    if not trend["ok"]:
        return None
    heute = df.iloc[-1]
    for zone in _starke_zonen(df, df_wochen):
        trigger = pruefe_shakeout_tag(heute, zone)
        if trigger["ok"]:
            return {
                "strategie": "Shakeout an starkem Level (Kapitel 10)",
                "zone": zone, "trigger": trigger, "trend": trend,
                "kaufpunkt": trigger["kaufpunkt"], "stop": trigger["stop"],
            }
    return None


def erkenne_shakeout_mit_sekundaertest(df, df_wochen=None):
    """Einzeltagsicht: Ist HEUTE ein Spring entstanden, der auf seinen
    Test wartet? Noch kein Kaufsignal."""
    trend = pruefe_trendkontext(df)
    if not trend["ok"]:
        return None
    heute_idx = len(df) - 1
    heute = df.iloc[-1]
    for zone in _starke_zonen(df, df_wochen):
        spring = pruefe_shakeout_tag(heute, zone)
        if not spring["ok"]:
            continue
        typ, verhaeltnis = klassifiziere_volumen_typ(heute, df.iloc[:heute_idx])
        return {
            "strategie": "Shakeout-Spring, wartet auf Sekundärtest",
            "status": "SPRING_ERKANNT_WARTE_AUF_TEST",
            "spring_index": heute_idx, "spring_datum": df.index[-1],
            "zone": zone, "spring_trigger": spring,
            "volumen_typ": typ, "volumen_verhaeltnis": verhaeltnis,
            "kursziel": berechne_kursziel(zone),
        }
    return None


def warte_auf_sekundaertest_und_alarmiere(df, warteliste, symbol, df_wochen=None):
    """DIE EMPFOHLENE BETRIEBSART. Einmal täglich nach Handelsschluss je
    Aktie aufrufen.

    Der Sekundärtest kann bis zu 15 Handelstage auf sich warten lassen —
    länger, als ein einzelner Lauf dauert. Deshalb führt diese Funktion
    eine Warteliste, die zwischen den Läufen in einer JSON-Datei liegt.

    Drei Fälle je Aufruf:
      1. Die Aktie wartet schon: nur den heutigen Tag als Test prüfen.
      2. Sie wartet nicht: heute einen neuen Spring suchen.
      3. Die Wartezeit ist abgelaufen: von der Liste nehmen, kein Signal.

    Rückgabe: (aktualisierte Warteliste, Signal oder None)."""
    heute = df.iloc[-1]
    heute_datum = (str(df.index[-1].date()) if hasattr(df.index[-1], "date")
                   else str(df.index[-1]))

    # --- Fall 1: steht schon auf der Warteliste ------------------------
    if symbol in warteliste:
        eintrag = warteliste[symbol]
        zone = {"min": eintrag["zone_min"], "max": eintrag["zone_max"]}
        spring_low = eintrag.get("spring_low", zone["min"])

        # Schluss unter dem Spring-Tief entwertet die Struktur.
        invalidiert, _ = pruefe_exit_invalidierung(
            df.iloc[[-1]].reset_index(drop=True), 0, spring_low)
        if invalidiert:
            del warteliste[symbol]
            return warteliste, None

        tief = float(heute["Low"])
        grenze = 1 - CFG["sekundaertest_max_zusatz_unterschreitung"]
        if (tief <= zone["max"] and tief >= spring_low * grenze
                and float(heute["Volume"]) < eintrag["spring_volumen"]):
            del warteliste[symbol]
            typ, verhaeltnis = klassifiziere_volumen_typ(heute, df.iloc[:-1])
            return warteliste, {
                "strategie": "Shakeout-Spring, Sekundärtest bestätigt",
                "symbol": symbol, "spring_datum": eintrag["spring_datum"],
                "test_datum": heute_datum,
                "kaufpunkt": round(zone["max"], 2),
                "stop": round(min(tief, spring_low), 2),
                "kursziel": berechne_kursziel(zone),
                "volumen_typ": typ, "volumen_verhaeltnis": verhaeltnis,
            }

        eintrag["tage_gewartet"] = eintrag.get("tage_gewartet", 0) + 1
        if eintrag["tage_gewartet"] > CFG["sekundaertest_max_wartetage"]:
            del warteliste[symbol]
        return warteliste, None

    # --- Fall 2: heute ein neuer Spring? -------------------------------
    if not pruefe_trendkontext(df)["ok"]:
        return warteliste, None
    for zone in _starke_zonen(df, df_wochen):
        if pruefe_shakeout_tag(heute, zone)["ok"]:
            warteliste[symbol] = {
                "spring_index": len(df) - 1, "spring_datum": heute_datum,
                "zone_min": zone["min"], "zone_max": zone["max"],
                "spring_low": float(heute["Low"]),
                "spring_volumen": float(heute["Volume"]), "tage_gewartet": 0,
            }
            break
    return warteliste, None


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

def _kunstkurse(tage=600, start=10.0, steigung=0.006, saat=7):
    """Ein sauberer Aufwärtstrend als Prüfgrundlage. Fester Zufallskeim,
    damit derselbe Lauf immer dasselbe Ergebnis bringt."""
    zufall = np.random.default_rng(saat)
    close = start * np.cumprod(1 + steigung + zufall.normal(0, 0.008, tage))
    hoch = close * (1 + abs(zufall.normal(0, 0.006, tage)))
    tief = close * (1 - abs(zufall.normal(0, 0.006, tage)))
    return pd.DataFrame({
        "Open": close, "High": hoch, "Low": tief, "Close": close,
        "Volume": zufall.integers(800_000, 1_200_000, tage).astype(float),
    }, index=pd.date_range("2024-01-01", periods=tage, freq="B"))


def selbsttest() -> int:
    fehler = []

    def pruefe(name, bedingung, zusatz=""):
        print(f"  {'ok  ' if bedingung else 'FEHL'} {name}"
              + (f" — {zusatz}" if zusatz else ""))
        if not bedingung:
            fehler.append(name)

    print("Shakeout-Spring, Selbsttest")
    df = _kunstkurse()

    trend = pruefe_trendkontext(df)
    pruefe("Trendkontext erkennt den Aufwärtstrend", trend["ok"],
           f"über MA200 {trend['ueber_ma200']}, "
           f"{trend['ueber_52w_tief_pct']} % über dem Tief")

    zonen = berechne_level_scores(df.iloc[:-1],
                                  wochenkurse_aus_tageskursen(df.iloc[:-1]))
    pruefe("Zonen gefunden", len(zonen) > 0, f"{len(zonen)} Stück")
    pruefe("Punktzahl bleibt zwischen 0 und 100",
           all(0 <= z["score"] <= 100 for z in zonen))

    # Einen Spring-Tag von Hand bauen: unter die Zone, zurück, Schluss oben.
    zone = {"min": 100.0, "max": 105.0}
    spring = pd.Series({"Low": 97.0, "High": 106.0, "Close": 105.7,
                        "Volume": 3_000_000.0})
    t = pruefe_shakeout_tag(spring, zone)
    pruefe("Spring-Tag wird erkannt", t["ok"],
           f"Schluss bei {t['schluss_position_pct']} % der Spanne")

    # DER FALL, DEN DIE LOCKERUNG VOM 02.08. AUSMACHT: Spanne 97 bis 107,
    # Schluss 105,5 — das sind 85 % der Spanne. Unter der alten Regel
    # (oberste 10 %, also 0,90) wäre der Tag durchgefallen, unter der
    # neuen (oberes Drittel, 0,70) zählt er.
    knapp = pd.Series({"Low": 97.0, "High": 107.0, "Close": 105.5,
                       "Volume": 3_000_000.0})
    t2 = pruefe_shakeout_tag(knapp, zone)
    pruefe("Gelockerte Schwelle 0,70 greift", t2["ok"],
           f"Schluss bei {t2['schluss_position_pct']} % der Spanne")
    pruefe("Derselbe Tag wäre an der alten Schwelle 0,90 gescheitert",
           t2["schluss_position_pct"] < 90.0)

    zu_tief = pd.Series({"Low": 85.0, "High": 106.0, "Close": 105.7,
                         "Volume": 3_000_000.0})
    pruefe("Zu tiefer Einbruch wird verworfen",
           not pruefe_shakeout_tag(zu_tief, zone)["ok"], "15 % unter die Zone")

    schwacher_schluss = pd.Series({"Low": 97.0, "High": 106.0, "Close": 99.0,
                                   "Volume": 3_000_000.0})
    pruefe("Schwacher Schluss wird verworfen",
           not pruefe_shakeout_tag(schwacher_schluss, zone)["ok"])

    pruefe("Kursziel projiziert die Zonenhöhe",
           berechne_kursziel(zone) == 110.0, f"{berechne_kursziel(zone)}")

    typ, verh = klassifiziere_volumen_typ(
        pd.Series({"Volume": 500_000.0}), df)
    pruefe("Volumentyp 1 bei wenig Volumen", typ.startswith("Typ 1"),
           f"{verh} mal Ø")
    typ3, _ = klassifiziere_volumen_typ(
        pd.Series({"Volume": 5_000_000.0}), df)
    pruefe("Volumentyp 3 bei viel Volumen", typ3.startswith("Typ 3"))

    # Warteliste von Ende zu Ende: Spring eintragen, Test bestätigen.
    warteliste = {"TEST": {
        "spring_index": len(df) - 2, "spring_datum": "2026-07-15",
        "zone_min": float(df["Close"].iloc[-1]) * 0.98,
        "zone_max": float(df["Close"].iloc[-1]) * 1.02,
        "spring_low": float(df["Low"].iloc[-1]) * 0.99,
        "spring_volumen": float(df["Volume"].iloc[-1]) * 3,
        "tage_gewartet": 2}}
    warteliste, signal = warte_auf_sekundaertest_und_alarmiere(
        df, warteliste, "TEST")
    pruefe("Sekundärtest bestätigt und meldet", signal is not None,
           f"Kaufpunkt {signal['kaufpunkt']}, Ziel {signal['kursziel']}"
           if signal else "kein Signal")
    pruefe("Bestätigte Aktie fliegt von der Warteliste",
           "TEST" not in warteliste)

    # Abgelaufene Wartezeit
    alt = {"ALT": {"spring_index": 0, "spring_datum": "2026-01-01",
                   "zone_min": 1.0, "zone_max": 2.0, "spring_low": 0.5,
                   "spring_volumen": 1.0,
                   "tage_gewartet": CFG["sekundaertest_max_wartetage"]}}
    alt, sig = warte_auf_sekundaertest_und_alarmiere(df, alt, "ALT")
    pruefe("Abgelaufene Wartezeit räumt den Eintrag weg", "ALT" not in alt)

    print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles bestanden.")
    return 1 if fehler else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Shakeout-Spring, Kapitel 10.")
    ap.add_argument("--selbsttest", action="store_true")
    args = ap.parse_args()
    sys.exit(selbsttest() if args.selbsttest else
             ap.print_help() or 0)
