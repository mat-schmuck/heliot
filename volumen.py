#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VOLUMEN — IBD "Volume % Change" mit Intraday-Hochrechnung
==========================================================
Gerhards Fassung vom 28.07.2026, verbindlich fuer das GANZE System:
Scanner, Waechter und Gap-and-Go rechnen ab jetzt hier und nirgends
sonst. Genau darum geht es ihm: Vorher rechnete der Scanner an einer
Stelle mit 20 Tagen, an anderer mit 10, der Waechter mit 10 — solche
stillen Uneinheitlichkeiten sollen weg.

    Volume%Change(t) = ( V_bisher(t) / F(t) / V50 − 1 ) × 100

    V_bisher(t)  heute bis jetzt gehandeltes Volumen
    F(t)         ueblicher Anteil des Tagesvolumens bis zu dieser Uhrzeit
    V50          Durchschnitt des GANZEN Tagesvolumens ueber die 50
                 abgeschlossenen Handelstage VOR heute (IBD-Standard)

Am Handelsschluss ist F(t) = 1, die Formel faellt dann von selbst auf
die reine IBD-Tagesformel zurueck. Ein Weg fuer beide Faelle, kein
Umschalten.

WAS SICH GEGENUEBER DER ALTEN RECHNUNG AENDERT
-----------------------------------------------
1. V50 statt Ø10. IBD-Standard. Gerhard hat das ausdruecklich als
   eigene Entscheidung neben der Formelkorrektur angeordnet — es
   widerruft seine eigene Festlegung vom Vormittag desselben Tages
   (damals 10 Tage, "einheitlich fuer Scanner UND Waechter").
2. F(t) im FUENF-Minuten-Raster aus echten Kursdaten statt der bisher
   fest hinterlegten 14 Stuetzstellen im Halbstundenraster. Der
   Unterschied zaehlt fast nur in der ersten halben Stunde — und genau
   dort entscheidet sich alles. Die alte Kurve stieg zwischen 09:30 und
   10:00 GERADLINIG von 0 auf 21,3 %; in Wahrheit ist der Sprung der
   Eroeffnungsauktion viel steiler. Wer in Minute 2 mit der geraden
   Linie hochrechnet, teilt durch einen viel zu kleinen Anteil und
   erzeugt Fantasiewerte.
3. Ausgegeben wird die IBD-Prozentzahl (+2025 %) statt eines
   Verhaeltnisses (21,3-fach). Verglichen wird weiterhin das
   Verhaeltnis — dieselbe Groesse, nur anders geschrieben, damit sich
   die Zahlen direkt gegen IBD halten lassen.

ZUM FEHLERBEFUND IM UEBERGABEPAPIER (wichtig fuer die Akten)
-------------------------------------------------------------
Gerhard beschreibt den KNSA-Fall so, dass das bestehende System OHNE
jede Hochrechnung vergleiche und deshalb -32 % statt +2000 % gezeigt
habe; sein Modul nennt das selbst "(vermutlich)". Nachgeprueft am
28.07.2026: In DIESEM Code stimmt das nicht — breakout_watcher.py
rechnet seit dem 23.07. mit tagesanteil() hoch. Mit der alten Kurve
haette KNSA rund +1815 % ergeben, nicht -32 %. Die -32 % lassen sich
hier nirgends reproduzieren.

Das entwertet die Korrektur NICHT: Die Fuenf-Minuten-Kurve ist in den
ersten Minuten deutlich genauer als die gerade Linie, V50 ist der
IBD-Standard, und die Vereinheitlichung ueber alle Module war
ueberfaellig. Es heisst nur: Es war eine Verbesserung, keine Reparatur
eines stillen Trade-Killers. Wer spaeter im Protokoll liest, soll das
richtig einordnen koennen.

Aufruf:
    python volumen.py                 Selbsttest (ohne Netzwerk)
    python volumen.py --bauen         Referenzkurve neu aus Kursdaten
"""

import json
import os
import sys
from datetime import datetime

RASTER = 5                      # Minuten je Stuetzstelle
HANDELSMINUTEN = 390            # 09:30 bis 16:00 New Yorker Zeit
KURVE_DATEI = "volumenkurve.json"

# Bewusst NICHT die zu scannenden Aktien, sondern ein stabiler Massstab
# dafuer, wie sich Volumen ueblicherweise ueber den Tag verteilt.
REFERENZ_TICKER = ["SPY", "QQQ", "AAPL", "MSFT", "AMD"]

# RUECKFALL, wenn keine gebaute Kurve vorliegt: die bis 28.07.2026
# verwendete Kurve, gemessen an 8 Aktien ueber 168 Aktien-Tage im
# Halbstundenraster. Schluessel: Minuten SEIT Handelsbeginn am ENDE der
# jeweiligen Halbstunde. Grob, aber gemessen — besser als gar nichts,
# und das System darf nie hart ausfallen.
RUECKFALL_KURVE = {
    0: 0.000, 30: 0.213, 60: 0.314, 90: 0.396, 120: 0.465, 150: 0.523,
    180: 0.581, 210: 0.630, 240: 0.676, 270: 0.721, 300: 0.764,
    330: 0.810, 360: 0.867, 390: 1.000,
}

_kurve = None                   # {minute: anteil}, einmal geladen


# ---------------------------------------------------------------------------
# Kurve laden und bauen
# ---------------------------------------------------------------------------

def lade_kurve(pfad=KURVE_DATEI, leise=False):
    """Holt die Referenzkurve aus der Datei; faellt auf die alte Kurve
    zurueck, wenn nichts da oder etwas kaputt ist."""
    global _kurve
    if _kurve is not None:
        return _kurve
    try:
        with open(pfad, encoding="utf-8") as f:
            roh = json.load(f)
        punkte = {int(k): float(v) for k, v in roh["kurve"].items()}
        if len(punkte) < 10:
            raise ValueError("zu wenige Stützstellen")
        _kurve = punkte
        if not leise:
            print(f"  Volumenkurve geladen: {len(punkte)} Stützstellen, "
                  f"gebaut am {roh.get('gebaut_am', 'unbekannt')} aus "
                  f"{roh.get('tage', '?')} Handelstagen.")
    except Exception as e:
        _kurve = dict(RUECKFALL_KURVE)
        if not leise:
            print(f"  ⚠ Keine gebaute Volumenkurve ({type(e).__name__}) — "
                  f"Rückfall auf die gemessene Halbstundenkurve.")
    return _kurve


def setze_kurve(punkte):
    """Nur fuer Tests: Kurve direkt vorgeben."""
    global _kurve
    _kurve = {int(k): float(v) for k, v in punkte.items()}
    return _kurve


def baue_referenzkurve(tickers=None, tage=50, pfad=KURVE_DATEI):
    """Baut F(t) aus echten Fuenf-Minuten-Kerzen der Referenzwerte.

    Drei Fallen, die hier bewusst behandelt sind:

    1. VERSCHIEBUNG UM EINE KERZE. Die Kerze mit Beginn 09:30 enthaelt
       den Umsatz BIS 09:35. Ihre kumulierte Summe gehoert also an die
       Minute 5, nicht an die Minute 0. Wer das verwechselt, rechnet in
       den ersten Minuten mit einem viel zu grossen Anteil — genau dort,
       wo es am meisten schadet. Bei Minute 0 steht per Definition 0.
    2. HALBE HANDELSTAGE. Vor Feiertagen schliesst die Boerse um 13:00.
       An solchen Tagen sind 100 % des Volumens nach 210 Minuten
       erreicht; mitteln wuerde die Kurve nach vorne verbiegen. Solche
       Tage fliegen raus.
    3. YFINANCE LIEFERT MEHRSTUFIGE SPALTEN. Seit der Umstellung kommt
       auch bei EINEM Ticker ein zweistufiger Spaltenkopf zurueck;
       df["Volume"] ist dann kein Vektor mehr, sondern eine Tabelle.
       Gerhards Fassung scheitert daran mit "truth value of a Series is
       ambiguous" — deshalb wird der Kopf hier eingeebnet."""
    import pandas as pd
    import yfinance as yf

    tickers = tickers or REFERENZ_TICKER
    raster = list(range(0, HANDELSMINUTEN + 1, RASTER))
    kurven = []
    verworfen = 0

    for ticker in tickers:
        try:
            df = yf.download(ticker, period=f"{min(tage, 59)}d",
                             interval="5m", progress=False,
                             auto_adjust=False)
        except Exception as e:
            print(f"  {ticker}: Abruf fehlgeschlagen ({type(e).__name__})")
            continue
        if df is None or df.empty:
            print(f"  {ticker}: keine Daten")
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        try:
            df = df.tz_convert("America/New_York")
        except Exception:
            pass

        df = df[["Volume"]].dropna()
        df["minute"] = [(z.hour * 60 + z.minute) - (9 * 60 + 30)
                        for z in df.index.time]
        df["datum"] = df.index.date
        df = df[(df["minute"] >= 0) & (df["minute"] < HANDELSMINUTEN)]

        for _, tag in df.groupby("datum"):
            tag = tag.sort_index()
            gesamt = float(tag["Volume"].sum())
            if gesamt <= 0:
                continue
            # Halbe Handelstage aussortieren (siehe Falle 2)
            if int(tag["minute"].max()) < HANDELSMINUTEN - 40:
                verworfen += 1
                continue
            kum = tag["Volume"].cumsum() / gesamt
            # Kerzenende statt Kerzenbeginn (siehe Falle 1)
            punkte = {0: 0.0}
            for minute, wert in zip(tag["minute"].values, kum.values):
                punkte[int(minute) + RASTER] = float(wert)
            kurven.append(punkte)

    if not kurven:
        raise RuntimeError("Keine Referenzdaten erhalten — Netzwerk oder "
                           "yfinance prüfen.")

    # Median ueber alle Tage und Ticker: robust gegen einzelne wilde Tage.
    gemittelt = {}
    for m in raster:
        werte = sorted(k[m] for k in kurven if m in k)
        if werte:
            gemittelt[m] = werte[len(werte) // 2]
    # Monoton machen (ein Median kann kleine Dellen erzeugen) und die
    # Enden festnageln.
    letzter = 0.0
    for m in raster:
        if m in gemittelt:
            letzter = gemittelt[m] = max(letzter, gemittelt[m])
    gemittelt[0] = 0.0
    gemittelt[HANDELSMINUTEN] = 1.0

    inhalt = {
        "gebaut_am": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "ticker": tickers,
        "tage": len(kurven),
        "raster_minuten": RASTER,
        "kurve": {str(m): round(a, 6) for m, a in sorted(gemittelt.items())},
    }
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(inhalt, f, ensure_ascii=False, indent=1)
    print(f"  Kurve gebaut aus {len(kurven)} Handelstagen "
          f"({len(tickers)} Referenzwerte, {verworfen} halbe Tage verworfen) "
          f"→ {pfad}")
    setze_kurve(gemittelt)
    return gemittelt


# ---------------------------------------------------------------------------
# Die Formel
# ---------------------------------------------------------------------------

def minute_seit_eroeffnung(jetzt=None):
    """Minuten seit 09:30 New Yorker Zeit. None ausserhalb des Handels
    und wenn die Zeitzone fehlt — dann wird nicht hochgerechnet."""
    try:
        from zoneinfo import ZoneInfo
        ny = ZoneInfo("America/New_York")
    except Exception:
        return None
    jetzt = (jetzt or datetime.now(ny)).astimezone(ny)
    m = jetzt.hour * 60 + jetzt.minute - (9 * 60 + 30)
    if m < 0 or m >= HANDELSMINUTEN:
        return None
    return m


def tagesanteil(minute=None):
    """F(t): Anteil des Tagesvolumens, der bis zu dieser Minute seit
    Handelsbeginn ueblicherweise schon gehandelt ist.

    None (vor Eroeffnung, nach Schluss) ergibt 1,0 — dann ist der Tag
    komplett und es wird nichts hochgerechnet."""
    if minute is None:
        return 1.0
    kurve = lade_kurve(leise=True)
    minute = max(0, min(HANDELSMINUTEN, int(minute)))
    stellen = sorted(kurve)
    if minute <= stellen[0]:
        return max(kurve[stellen[0]], 0.001)
    if minute >= stellen[-1]:
        return 1.0
    for i in range(1, len(stellen)):
        m0, m1 = stellen[i - 1], stellen[i]
        if minute <= m1:
            a0, a1 = kurve[m0], kurve[m1]
            spanne = m1 - m0
            anteil = a0 + (a1 - a0) * ((minute - m0) / spanne) if spanne else a1
            # Nie durch (fast) null teilen. 0,001 entspricht rund den
            # ersten Sekunden nach der Glocke.
            return max(anteil, 0.001)
    return 1.0


def verhaeltnis(v_bisher, v50, minute=None):
    """Das Vielfache des ueblichen Volumens FUER DIESE UHRZEIT.
    1,0 heisst voellig normal, 21,3 heisst 21-faches Tempo.
    None, wenn kein Massstab vorliegt (brandneue Notierung)."""
    if not v50 or v50 <= 0 or v_bisher is None:
        return None
    return (v_bisher / tagesanteil(minute)) / v50


def volume_pct_change(v_bisher, v50, minute=None):
    """Die IBD-Zahl: +2025 % heisst das 21,25-fache des Ueblichen,
    -32 % heisst ein knappes Drittel unter dem Ueblichen."""
    v = verhaeltnis(v_bisher, v50, minute)
    return None if v is None else (v - 1.0) * 100.0


def text(v_bisher, v50, minute=None):
    """Einheitliche Schreibweise fuer Meldungen und Protokoll."""
    p = volume_pct_change(v_bisher, v50, minute)
    if p is None:
        return "Volumen nicht bewertbar, zu wenig Kurshistorie"
    return f"{p:+.0f} % gegenüber dem 50-Tage-Schnitt"


# --- Schreibweise fuer Meldungen ------------------------------------------
# Am 28.07.2026 stand in einer echten Meldung "nötig +0 %". Rechnerisch
# richtig — die Huerde der meisten Muster ist der Faktor 1,0, also null
# Prozent UEBER dem Schnitt — aber es liest sich wie "keine Anforderung"
# oder wie ein Fehler. Mathias hat es sofort bemerkt. Deshalb wird der
# Faktor 1,0 ausgeschrieben statt als Prozentzahl dargestellt, und die
# Lage der Aktie in Worten statt mit Vorzeichen.

# ---------------------------------------------------------------------------
# WEITERE IBD-VOLUMENMASSE (recherchiert am 28.07.2026)
# ---------------------------------------------------------------------------
# IBDs eigene Seite (investors.com) ist fuer uns gesperrt. Belegt sind die
# folgenden Regeln aber aus IBD-Artikeln, die Yahoo Finance und Nasdaq im
# Original nachveroeffentlichen, sowie aus IBDs Bildungsbeitraegen.
#
# WAS IBD VEROEFFENTLICHT:
#   * Massstab ist der 50-Tage-Durchschnitt des Tagesvolumens.
#   * Ausbruch: "Trading should swell at least 40% above the stock's
#     50-day average volume", besser 40 bis 50 Prozent darueber.
#     Geschrieben wird das als "volume X% above average" — genau die
#     Groesse, die volume_pct_change() liefert.
#   * Up/Down Volume Ratio ueber 50 Handelstage: Summe des Volumens an
#     steigenden Tagen geteilt durch die Summe an fallenden Tagen. 1,0 ist
#     ausgeglichen, ueber 1,0 heisst Kaufdruck, 1,5 gilt als stark.
#   * Liquiditaet: unter 400.000 Stueck am Tag (Ø50) gilt als
#     duenn gehandelt; Dollar-Umsatz (Kurs mal Ø-Tagesvolumen) sollte
#     mindestens 20 bis 25 Millionen betragen.
#
# WAS IBD NICHT VEROEFFENTLICHT:
#   * Wie die Prozentzahl WAEHREND des Handelstages hochgerechnet wird.
#     Dazu steht nur, die Plattform berechne sie fortlaufend. Keine
#     Formel, nirgends. Die bekannteste Nachbildung (TradingView) rechnet
#     LINEAR nach verstrichener Zeit hoch — das ist nachweislich schlecht:
#     Um 9:35 waeren erst 1,3 Prozent des Tages verstrichen, tatsaechlich
#     sind im Schnitt 7,5 Prozent des Volumens gehandelt (nachgemessen an
#     245 Handelstagen). Eine voellig normale Aktie zeigte damit +480 %.
#     Deshalb bleibt es bei unserer gemessenen Tageskurve.
#   * Das Accumulation/Distribution Rating. IBD nennt es selbst
#     ausdruecklich eine "proprietary formula" — es ist nicht
#     nachbaubar, nur ratbar. Deshalb ist es hier NICHT eingebaut.


def up_down_verhaeltnis(schluss, volumen_reihe, tage=50):
    """IBDs Up/Down Volume Ratio ueber die letzten 'tage' Handelstage.

    Summe des Volumens an Tagen mit steigendem Schluss, geteilt durch die
    Summe an Tagen mit fallendem Schluss. Unveraenderte Tage zaehlen bei
    IBD nicht mit, weil sie weder Kauf- noch Verkaufsdruck zeigen.

    Liefert None, wenn zu wenig Historie da ist oder es gar keine
    fallenden Tage gab (dann waere das Verhaeltnis unendlich, und eine
    erfundene Zahl waere schlechter als ein ehrliches 'unbekannt')."""
    try:
        s = [float(x) for x in schluss]
        v = [float(x) for x in volumen_reihe]
    except (TypeError, ValueError):
        return None
    if len(s) != len(v) or len(s) < 3:
        return None
    hoch = runter = 0.0
    for i in range(max(1, len(s) - tage), len(s)):
        if s[i] > s[i - 1]:
            hoch += v[i]
        elif s[i] < s[i - 1]:
            runter += v[i]
    if runter <= 0:
        return None
    return hoch / runter


def ud_text(verhaeltnis):
    """IBDs Lesart in Worten: 1,0 ausgeglichen, ab 1,5 stark."""
    if verhaeltnis is None:
        return ""
    if verhaeltnis >= 1.5:
        urteil = "starker Kaufdruck"
    elif verhaeltnis >= 1.0:
        urteil = "mehr Kauf als Verkauf"
    else:
        urteil = "mehr Verkauf als Kauf"
    return f"Auf- zu Abwärtsvolumen {verhaeltnis:.2f}, {urteil}"


def liquiditaet(kurs, schnitt_volumen):
    """IBDs Liquiditaetsuntergrenzen. Liefert (in_ordnung, Begruendung).

    Unter 400.000 Stueck am Tag gilt eine Aktie bei IBD als duenn
    gehandelt; der Dollar-Umsatz sollte mindestens 20 Millionen betragen.
    Beides ist bei IBD eine WARNUNG, kein Ausschluss — deshalb wird hier
    auch nichts verworfen, sondern nur gekennzeichnet."""
    if not kurs or not schnitt_volumen:
        return True, ""
    hinweise = []
    if schnitt_volumen < 400_000:
        hinweise.append(f"dünn gehandelt, Ø{schnitt_volumen:,.0f} Stück")
    umsatz = kurs * schnitt_volumen
    if umsatz < 20_000_000:
        hinweise.append(f"Tagesumsatz nur {umsatz/1e6:.0f} Mio Dollar")
    return (not hinweise), "; ".join(hinweise)


def huerde_text(faktor):
    """Was verlangt wird, in lesbarer Form."""
    if faktor <= 1.0:
        return "nötig wäre mindestens der Schnitt"
    return f"nötig {(faktor - 1) * 100:.0f} % darüber"


def lage_text(pct, fenster=50):
    """Wo die Aktie steht, ohne Vorzeichen-Rätsel."""
    if pct is None:
        return "Volumen nicht bewertbar"
    if pct >= 0:
        return f"{pct:.0f} % über Ø{fenster}"
    return f"{abs(pct):.0f} % unter Ø{fenster}"


# ---------------------------------------------------------------------------
# Selbsttest — ohne Netzwerk
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if "--bauen" in sys.argv:
        baue_referenzkurve()
        sys.exit(0)

    # Eine realistische Kurve von Hand, damit der Test ohne Netz laeuft:
    # steiler Eroeffnungsschub, ruhige Mitte, Schlussauktion.
    test_kurve = {0: 0.0, 5: 0.055, 10: 0.082, 15: 0.101, 30: 0.150,
                  60: 0.232, 120: 0.365, 195: 0.520, 270: 0.665,
                  330: 0.790, 375: 0.930, 390: 1.0}
    setze_kurve(test_kurve)

    print("=" * 66)
    print("TEST 1: Am Handelsschluss muss die reine IBD-Tagesformel stehen")
    print("=" * 66)
    assert abs(volume_pct_change(1_100_000, 700_000) - 57.14) < 0.01
    assert abs(volume_pct_change(700_000, 700_000) - 0.0) < 1e-9
    print("  1,1 Mio gegen Ø50 700.000 → +57 %; genau am Schnitt → 0 %  ✓")

    print("\n" + "=" * 66)
    print("TEST 2: Eine ganz normale Aktie zeigt zu JEDER Uhrzeit rund 0 %")
    print("=" * 66)
    v50 = 700_000
    for m in (5, 15, 60, 195, 330):
        v_normal = tagesanteil(m) * v50
        p = volume_pct_change(v_normal, v50, m)
        print(f"  Minute {m:>3} (F={tagesanteil(m):.3f}): {p:+.1f} %")
        assert abs(p) < 0.5, "eine normale Aktie darf nicht auffällig wirken"
    print("  ✓ Keine Scheinausschläge am Vormittag")

    print("\n" + "=" * 66)
    print("TEST 3: Der KNSA-Fall — echte Auffälligkeit muss sichtbar sein")
    print("=" * 66)
    v50_knsa, v_bisher = 743_000, 0.68 * 743_000
    ohne = (v_bisher / v50_knsa - 1) * 100
    mit = volume_pct_change(v_bisher, v50_knsa, 15)
    print(f"  Ohne Hochrechnung (die Rechnung, die Gerhard vermutet hat): "
          f"{ohne:+.0f} %")
    print(f"  Mit Hochrechnung, Minute 15 (F={tagesanteil(15):.3f}): {mit:+.0f} %")
    assert ohne < 0 and mit > 500
    print("  ✓ Aus einem scheinbaren Minus wird die echte Auffälligkeit")

    print("\n" + "=" * 66)
    print("TEST 4: Ein echtes Signal bleibt den ganzen Tag stabil")
    print("=" * 66)
    for m in (5, 60, 195, 330):
        p = volume_pct_change(tagesanteil(m) * v50 * 4.0, v50, m)
        print(f"  Minute {m:>3}: vierfaches Tempo → {p:+.0f} %")
        assert 299 < p < 301
    print("  ✓ Vierfaches Tempo zeigt durchgehend +300 %, es verläuft nicht")

    print("\n" + "=" * 66)
    print("TEST 5: Die ersten Sekunden dürfen nicht explodieren")
    print("=" * 66)
    p0 = volume_pct_change(1000, v50, 0)
    print(f"  Minute 0, winziges Volumen: {p0:+.0f} % (F={tagesanteil(0):.4f})")
    assert p0 is not None, "darf nicht abstürzen"
    print("  ✓ Kein Sturz durch Division, F wird nie kleiner als 0,001")

    print("\n" + "=" * 66)
    print("TEST 6: Ohne Maßstab wird ehrlich nichts behauptet")
    print("=" * 66)
    assert volume_pct_change(500_000, 0) is None
    assert volume_pct_change(500_000, None) is None
    assert "nicht bewertbar" in text(500_000, 0)
    print("  ✓ Brandneue Notierung ohne Ø50 → 'nicht bewertbar', keine Zahl")

    print("\n" + "=" * 66)
    print("TEST 7: Der Rückfall greift, wenn keine gebaute Kurve da ist")
    print("=" * 66)
    setze_kurve(RUECKFALL_KURVE)
    assert 0.2 < tagesanteil(30) < 0.22
    assert tagesanteil(390) == 1.0
    print(f"  Halbstundenkurve: nach 30 Minuten {tagesanteil(30)*100:.1f} %, "
          f"am Schluss {tagesanteil(390)*100:.0f} %  ✓")

    print("\n" + "=" * 66)
    print("TEST 8: IBDs Up/Down Volume Ratio")
    print("=" * 66)
    # Drei Auf-Tage mit viel Volumen, zwei Ab-Tage mit wenig.
    kurse = [10, 11, 12, 11.5, 13, 12.5]
    vols = [0, 300, 300, 100, 300, 100]
    v = up_down_verhaeltnis(kurse, vols)
    assert abs(v - 4.5) < 1e-9, f"erwartet 900/200 = 4,5, war {v}"
    print(f"  900 Stück an Auf-Tagen, 200 an Ab-Tagen → {v:.2f}  ✓")
    assert "starker Kaufdruck" in ud_text(v)
    assert "mehr Verkauf" in ud_text(0.8)
    print(f"  {ud_text(v)}")
    print(f"  {ud_text(0.8)}")
    # Ohne Ab-Tage gibt es kein Verhaeltnis — ehrlich None statt unendlich
    assert up_down_verhaeltnis([10, 11, 12], [0, 100, 100]) is None
    print("  ✓ Ohne fallende Tage: 'unbekannt' statt einer erfundenen Zahl")

    print("\n" + "=" * 66)
    print("TEST 9: IBDs Liquiditätsuntergrenzen")
    print("=" * 66)
    ok, grund = liquiditaet(60.0, 400_000)
    assert ok, f"400.000 Stück mal 60 Dollar sind 24 Mio, das reicht: {grund}"
    print("  Kurs 60, Ø 400.000 Stück → 24 Mio Umsatz, in Ordnung  ✓")
    ok, grund = liquiditaet(5.0, 300_000)
    assert not ok and "dünn" in grund and "Mio" in grund
    print(f"  Kurs 5, Ø 300.000 Stück → {grund}  ✓")

    print("\nAlle Volumen-Tests bestanden (ohne Netzwerk).")
