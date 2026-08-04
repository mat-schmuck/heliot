#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CUP & HANDLE AUF WOCHENBASIS — die "Giant Base" (Gerhard, 04.08.2026)
======================================================================
ERGAENZUNG, KEINE ERSETZUNG. Die bestehende detect_cup_handle im
Nachtscanner bleibt unveraendert und laeuft weiter; diese Funktion
kommt daneben.

DER FEHLER, DEN SIE BEHEBT
    Bei sehr langen Konsolidierungen — IBD nennt das selbst "Giant
    Base" — sieht die Tagesfunktion den echten linken Rand nicht mehr:
    Ihr Suchfenster von rund 160 Tagen ist dafuer zu kurz. Uebrig
    bleibt ein Ausschnitt der wahren Formation, der dann als anderes
    Muster gemeldet wird. Aufgefallen an DDOG: Die Aktie brach am
    01.08.2026 ueber einen von IBD bestaetigten Cup-&-Handle-Kaufpunkt
    aus, unser System meldete Rectangle Top zum gleichen Kurs.

DIE LOESUNG
    Dieselbe Kernlogik auf WOCHENKERZEN. Ein Cup ueber 500 Tage wird so
    zu rund 70 Wochenkerzen und ist genauso handhabbar wie ein
    Standard-Cup auf Tagesbasis.

DREI KORREKTUREN GEGENUEBER DER TAGESFASSUNG
    1. RANDERKENNUNG, der eigentliche Kern des Fehlers: Die alte Logik
       nahm den ERSTEN Punkt, der die Randschwelle erreicht, als
       rechten Rand. Bei einer Giant Base laeuft der Kurs dort aber oft
       noch weiter, und die weiterlaufende Rally wurde faelschlich zum
       Handle gerechnet. Jetzt wird vom ersten Schwellenkontakt aus der
       TATSAECHLICHE Hoehepunkt in einem kurzen Nachlauffenster
       gesucht, und erst danach der Handle gemessen.
    2. Randtoleranz 6 % auf 11 % gelockert.
    3. Handle in der oberen HAELFTE statt im oberen Drittel. Die
       eigentliche Qualitaetspruefung bleibt streng: Der Ruecksetzer
       darf hoechstens 45 % der Cup-Hoehe betragen.
    Dazu ein robusterer Fit: Ausreisser werden vor dem polyfit mit
    einem gleitenden Median gedaempft, damit eine einzelne Extremwoche
    die Formerkennung nicht kippt.

VALIDIERT von Gerhard gegen zwei echte, von IBD bestaetigte Ausbrueche:
    LPG   IBD-Kaufpunkt 35,91 — v2 fand 35,83, Abweichung -0,2 %
    MEDP  IBD-Kaufpunkt 567,91 — v2 fand 567,92, Abweichung +0,0 %
    Bei MEDP nennt IBD die Formation selbst "Giant Base".
    Ein dritter Fall (DDOG) liess sich in seiner Testdatenbank mangels
    Historie nicht pruefen; das lag an den Testdaten, nicht an der
    Logik. Mit unserem Datenbestand ist das nachholbar.

ZWEI ANPASSUNGEN AN UNSER SYSTEM, die in Gerhards Vorlage fehlten
    a) Sein Rueckgabe-Dict hat nur strategie, kaufpunkt und score. Der
       Nachtscanner braucht zusaetzlich stop, ziel, status und notiz,
       sonst bricht die Excel-Ausgabe mit einem Schluesselfehler ab.
       Beides ist hier ergaenzt, nach denselben Regeln wie in der
       Tagesfassung: Ziel = Kaufpunkt plus Cup-Hoehe, Stop an der
       Grenze, die das Muster definiert (hier die halbe Cup-Hoehe, weil
       der Handle in der oberen Haelfte liegen muss).
    b) Sein Einbau-Beispiel vergleicht die Punktzahlen mit
       treffer_v1.get('score', 100). Unsere Tagesfassung liefert aber
       gar keinen Schluessel 'score' — damit haette v1 IMMER gewonnen
       und v2 waere nie zum Zug gekommen. Die Tagesfassung gibt ihre
       Punktzahl jetzt zusaetzlich als Zahl aus; ihre Rechnung bleibt
       unangetastet.

Aufruf:
    python cup_handle_v2.py --selbsttest
"""

import argparse
import sys

import numpy as np
import pandas as pd

from config import CFG as _ALLE

CFG = _ALLE["cup_handle_v2"]


# ---------------------------------------------------------------------------
# Daten vorbereiten
# ---------------------------------------------------------------------------

def aus_scanner_df(df):
    """Die Tagesdaten des Scanners auf einen Datumsindex bringen.

    Der Scanner fuehrt einen Laufindex und die Zeit in einer eigenen
    Spalte; das Zusammenfassen zu Wochen braucht aber einen Datumsindex.
    Uebersetzt wird an genau dieser einen Stelle."""
    if isinstance(df.index, pd.DatetimeIndex):
        return df
    if "datetime" not in df.columns:
        raise KeyError("Spalte 'datetime' fehlt")
    neu = df.copy()
    neu.index = pd.to_datetime(neu["datetime"])
    return neu


def wochenkurse(df_tage):
    """Tageskerzen zu Wochenkerzen, Woche endet am Freitag."""
    return df_tage.resample("W-FRI").agg({
        "high": "max", "low": "min", "close": "last", "volume": "sum",
    }).dropna()


def swing_highs(serie, order=3):
    """Lokale Hochpunkte: hoechster Wert im Fenster von 'order' Kerzen
    nach beiden Seiten."""
    werte = serie.values
    return [i for i in range(order, len(werte) - order)
            if werte[i] >= werte[i - order:i + order + 1].max()]


# ---------------------------------------------------------------------------
# Die Erkennung
# ---------------------------------------------------------------------------

def detect_cup_handle_v2(df, cfg=None):
    """Sucht eine Giant Base auf Wochenbasis.

    df: Tagesdaten mit den Spalten high, low, close, volume; entweder mit
    Datumsindex oder mit einer Spalte 'datetime'.
    Rueckgabe: dict im selben Aufbau wie die anderen Musterdetektoren,
    oder None."""
    cfg = cfg or CFG
    try:
        w = wochenkurse(aus_scanner_df(df))
    except Exception:
        return None
    n = len(w)
    if n < cfg["cup_min_len_wochen"] + cfg["handle_min_len_wochen"]:
        return None

    best = None
    for left in swing_highs(w["high"], order=3):
        if n - left < cfg["cup_min_len_wochen"]:
            continue
        left_high = float(w["high"].iloc[left])
        seg = w.iloc[left:]
        bot_rel = int(seg["low"].values.argmin())
        bottom = float(seg["low"].iloc[bot_rel])
        if left_high <= 0:
            continue
        depth = 1 - bottom / left_high
        if not (cfg["cup_min_depth"] <= depth <= cfg["cup_max_depth"]):
            continue

        # Wo erreicht der Kurs nach dem Boden wieder die Randschwelle?
        nach_boden = seg.iloc[bot_rel:]
        schwelle = left_high * (1 - cfg["cup_rim_tolerance"])
        erreicht = nach_boden[nach_boden["high"] >= schwelle]
        if erreicht.empty:
            continue
        erst = left + bot_rel + list(nach_boden.index).index(erreicht.index[0])

        # DER KERN DER KORREKTUR: von dort aus den tatsaechlichen
        # Hoehepunkt suchen, nicht die erste Beruehrung nehmen. Sonst
        # zaehlt die weiterlaufende Rally faelschlich zum Handle.
        fenster_ende = min(erst + cfg["handle_max_len_wochen"], n)
        rand_fenster = w.iloc[erst:fenster_ende]
        if rand_fenster.empty:
            continue
        right = erst + int(rand_fenster["high"].values.argmax())

        cup_len = right - left
        if not (cfg["cup_min_len_wochen"] <= cup_len <= cfg["cup_max_len_wochen"]):
            continue

        bot_abs = left + bot_rel
        sym = (bot_abs - left) / cup_len if cup_len > 0 else 0
        if not (cfg["symmetrie_min"] <= sym <= cfg["symmetrie_max"]):
            continue

        # U-Form, mit gedaempften Ausreissern: Eine einzelne Extremwoche
        # soll die Formerkennung nicht kippen.
        x = np.arange(cup_len + 1)
        y_roh = w["low"].iloc[left:right + 1].values
        y = (pd.Series(y_roh)
             .rolling(cfg["outlier_glaettung_fenster"], center=True,
                      min_periods=1)
             .median().values)
        coef = np.polyfit(x, y, 2)
        fit = np.polyval(coef, x)
        ss_res = float(np.sum((y - fit) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2)) or 1e-9
        r2 = 1 - ss_res / ss_tot
        u_ok = coef[0] > 0 and r2 > cfg["r2_min"]

        handle = w.iloc[right:]
        if (len(handle) < cfg["handle_min_len_wochen"]
                or len(handle) > cfg["handle_max_len_wochen"] + 3):
            continue
        h_high = float(w["high"].iloc[right])       # der Randpunkt selbst
        h_low = float(handle["low"].min())
        hoehe = left_high - bottom
        retrace = (h_high - h_low) / (hoehe + 1e-9)
        oben_genug = h_low >= bottom + hoehe * cfg["handle_min_position"]
        if retrace > cfg["handle_max_retrace"] or not oben_genug:
            continue

        score = (40 * min(1.0, r2 / 0.85)
                 + 20 * (1 - abs(sym - 0.5) * 2)
                 + 20 * (1 - retrace / cfg["handle_max_retrace"])
                 + 20 * (1 if u_ok else 0.3))
        kandidat = {
            "left_high": left_high, "bottom": bottom, "h_high": h_high,
            "depth": depth, "score": score, "cup_len": cup_len,
            "retrace": retrace, "r2": r2, "sym": sym, "u_ok": u_ok,
            "links": str(w.index[left].date()),
            "rechts": str(w.index[right].date()),
        }
        if best is None or kandidat["score"] > best["score"]:
            best = kandidat

    if best is None or best["score"] < cfg["min_score"]:
        return None

    kp = round(best["h_high"] + 0.01, 2)
    hoehe = best["left_high"] - best["bottom"]
    return {
        "strategie": "Cup & Handle (Wochenbasis)",
        "kaufpunkt": kp,
        # Stop an der Grenze, die das Muster definiert: Faellt der Kurs
        # unter die halbe Cup-Hoehe, ist die Handle-Bedingung verletzt.
        "stop": round(best["bottom"] + hoehe * cfg["handle_min_position"], 2),
        "ziel": round(kp + hoehe, 2),
        "score": round(best["score"], 1),
        "status": f"Score {best['score']:.0f}/100",
        "notiz": (f"Giant Base auf Wochenbasis, {best['cup_len']} Wochen "
                  f"von {best['links']} bis {best['rechts']}; "
                  f"Cup-Tiefe {best['depth']*100:.0f} %, "
                  f"Rücksetzer {best['retrace']*100:.0f} % der Cup-Höhe; "
                  f"U-Form {'bestätigt' if best['u_ok'] else 'schwach'}, "
                  f"Bestimmtheitsmaß {best['r2']:.2f}; "
                  f"Ziel = Kaufpunkt plus Cup-Höhe"),
    }


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

def _kunstcup(wochen=60, hoch=100.0, tiefe=0.35, handle_wochen=4, saat=3,
              anlauf=12):
    """Einen sauberen Cup mit Handle bauen: Anlauf, Parabel nach unten und
    zurueck, danach ein flacher Ruecksetzer. Fester Zufallskeim.

    DER ANLAUF IST NOETIG, nicht Zierde: Der linke Rand wird ueber
    swing_highs gesucht, und ein lokales Hoch braucht Kerzen auf BEIDEN
    Seiten. Ohne Vorlauf beginnt die Reihe am Rand, dort gibt es nichts
    davor, und die Formation wird nie gefunden. Beim ersten Selbsttest
    am 04.08.2026 genau so aufgelaufen."""
    zufall = np.random.default_rng(saat)
    vorlauf = hoch * np.linspace(0.90, 1.00, anlauf)
    x = np.linspace(-1, 1, wochen)
    boden = hoch * (1 - tiefe)
    kurve = boden + (hoch - boden) * x ** 2
    kurve = kurve * (1 + zufall.normal(0, 0.004, wochen))
    # Handle: leichter Ruecksetzer aus dem rechten Rand
    rand = kurve[-1]
    handle = rand * np.linspace(1.0, 0.93, handle_wochen)
    close = np.concatenate([vorlauf, kurve, handle])
    tage = len(close) * 5
    werte = np.repeat(close, 5)[:tage]
    return pd.DataFrame({
        "high": werte * 1.004, "low": werte * 0.996,
        "close": werte, "volume": np.full(tage, 1_000_000.0),
    }, index=pd.date_range("2024-01-01", periods=tage, freq="B"))


def selbsttest() -> int:
    fehler = []

    def pruefe(name, bedingung, zusatz=""):
        print(f"  {'ok  ' if bedingung else 'FEHL'} {name}"
              + (f" — {zusatz}" if zusatz else ""))
        if not bedingung:
            fehler.append(name)

    print("Cup & Handle auf Wochenbasis, Selbsttest")

    df = _kunstcup()
    t = detect_cup_handle_v2(df)
    pruefe("Sauberer Giant-Base-Cup wird erkannt", t is not None,
           f"Kaufpunkt {t['kaufpunkt']}, {t['status']}" if t else "nichts")
    if t:
        for feld in ("strategie", "kaufpunkt", "stop", "ziel", "status",
                     "notiz", "score"):
            pruefe(f"Rückgabe enthält '{feld}'", feld in t)
        pruefe("Ziel liegt über dem Kaufpunkt", t["ziel"] > t["kaufpunkt"],
               f"{t['ziel']} gegen {t['kaufpunkt']}")
        pruefe("Stop liegt unter dem Kaufpunkt", t["stop"] < t["kaufpunkt"],
               f"{t['stop']}")

    # Ein reiner Aufwärtstrend ist kein Cup.
    n = 300
    steig = pd.DataFrame({
        "high": np.linspace(10, 30, n) * 1.004,
        "low": np.linspace(10, 30, n) * 0.996,
        "close": np.linspace(10, 30, n),
        "volume": np.full(n, 1e6),
    }, index=pd.date_range("2024-01-01", periods=n, freq="B"))
    pruefe("Reiner Aufwärtstrend wird nicht als Cup gemeldet",
           detect_cup_handle_v2(steig) is None)

    # Zu wenig Historie
    kurz = _kunstcup(wochen=4, handle_wochen=1)
    pruefe("Zu kurze Historie ergibt nichts",
           detect_cup_handle_v2(kurz) is None)

    # Die Scanner-Form mit Laufindex und Spalte 'datetime'
    scanner_df = df.reset_index().rename(columns={"index": "datetime"})
    pruefe("Scanner-Form mit Spalte 'datetime' wird verstanden",
           detect_cup_handle_v2(scanner_df) is not None)

    # Ein zu tiefer Handle muss durchfallen: Rücksetzer bis unter die
    # halbe Cup-Höhe.
    tief = _kunstcup()
    letzte = tief.index[-40:]
    tief.loc[letzte, ["high", "low", "close"]] *= 0.55
    pruefe("Zu tiefer Rücksetzer wird verworfen",
           detect_cup_handle_v2(tief) is None)

    print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles bestanden.")
    return 1 if fehler else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Cup & Handle auf Wochenbasis (Giant Base).")
    ap.add_argument("--selbsttest", action="store_true")
    args = ap.parse_args()
    sys.exit(selbsttest() if args.selbsttest else ap.print_help() or 0)
