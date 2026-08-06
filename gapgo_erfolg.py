#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GAP AND GO — DIE VOLLSTAENDIGE ERFOLGSMESSUNG
==============================================
Mathias' Auftrag vom 03.08.2026: alles messen, was interessant sein
koennte, samt der Frage nach der Positionsgroesse, die ich selbst
aufgeworfen hatte.

DER ABLAUF, so nah an Kapitel 7 wie moeglich
  Ereignis:  Luecke ab 7 % nach oben, verteidigt (Tagestief bleibt ueber
             dem Vortagesschluss), Schluss im oberen Fuenftel.
  Kaufpunkt: Tageshoch plus einen Cent.
  Einstieg:  am FOLGETAG, sobald der Kaufpunkt erreicht wird. Oeffnet
             die Aktie schon darueber, wird zur Eroeffnung gekauft (der
             schlechtere, also ehrliche Fall). Wird der Kaufpunkt nie
             erreicht, gibt es keinen Handel; auch das ist ein Ergebnis
             und wird eigens ausgewertet.
  Stop:      min(Tagestief - 1 Cent, Kaufpunkt x 0,97), wie im Waechter.

WAS GEMESSEN WIRD
  1. Wie gut ist das Einstiegssignal ueberhaupt?
  2. Was bringen die diskutierten Einstiegsfilter?
  3. Was bewirkt der Stop, eng wie weit?
  4. RISIKOGEWICHTET: Was bringt jede Stopregel je riskiertem Euro?
     Das ist die Frage, die der reine Renditevergleich offenlaesst.
  5. Zeitausstieg, Zielverkauf, nachziehender Stop.
  6. Einstiegsvarianten, samt der Faelle ohne Ausloesung.
  7. Die rechte Flanke: Wer bringt die grossen Gewinne?
  8. Lueckengroesse in Klassen.

WAS DIESE MESSUNG NICHT KANN
  Die Aktienliste ist die HEUTIGE Wochenliste. Wer heute im Screener
  steht, hat die letzten Monate ueberstanden; das faerbt die absoluten
  Zahlen nach oben. Fuer den VERGLEICH der Regeln untereinander ist das
  weniger schlimm, weil alle dieselbe Verzerrung teilen. Und es sind
  wenige Ereignisse; Unterschiede von wenigen Prozentpunkten sind
  Rauschen.

Aufruf:  python gapgo_erfolg.py [Monate]        (Vorgabe 24)
"""

import sys
from statistics import mean, median

XLSX = "kaufpunkte_aktuell.xlsx"
GAP_MIN = 0.07
SCHLUSS_POS = 0.80
STOP_MAX = 0.97
TAGE_MAX = 40                # so weit wird der Verlauf mitgeschrieben


# ---------------------------------------------------------------------------
# Ereignisse sammeln
# ---------------------------------------------------------------------------

def ereignisse_sammeln(roh, ticker, start=65):
    ereignisse = []
    for t in ticker:
        try:
            d = roh[t].dropna(subset=["Open", "High", "Low", "Close", "Volume"])
        except Exception:
            continue
        if len(d) <= start + TAGE_MAX + 2:
            continue
        o, h, l, c, v = (d["Open"].values, d["High"].values, d["Low"].values,
                         d["Close"].values, d["Volume"].values)
        datum = d.index

        for i in range(start, len(d) - TAGE_MAX - 1):
            prev = c[i - 1]
            if prev <= 0 or o[i] / prev - 1 < GAP_MIN:
                continue
            if l[i] <= prev:
                continue
            spanne_tag = h[i] - l[i]
            if spanne_tag <= 0 or (c[i] - l[i]) / spanne_tag < SCHLUSS_POS:
                continue

            gap = o[i] / prev - 1
            kaufpunkt = h[i] + 0.01
            j = i + 1
            ausgeloest = h[j] >= kaufpunkt
            einstieg = max(o[j], kaufpunkt) if ausgeloest else None

            e = {
                "datum": str(datum[i].date()), "ticker": t, "gap": gap,
                "schlusspos": (c[i] - l[i]) / spanne_tag,
                "r10": v[i] / v[i - 10:i].mean() if v[i - 10:i].mean() > 0 else 0,
                "r50": v[i] / v[i - 50:i].mean() if v[i - 50:i].mean() > 0 else 0,
                "spanne25": ((h[i - 25:i].max() - l[i - 25:i].min())
                             / l[i - 25:i].min()) if l[i - 25:i].min() > 0 else 9,
                "spanne63": ((h[i - 63:i].max() - l[i - 63:i].min())
                             / l[i - 63:i].min()) if l[i - 63:i].min() > 0 else 9,
                "ueber_ma50": (c[i - 1] / c[i - 50:i].mean() - 1)
                              if c[i - 50:i].mean() > 0 else 9,
                "ueber_ma10": bool(c[i] > c[i - 10:i].mean()),
                "ueber_ma21": bool(c[i] > c[i - 21:i].mean()),
                "kaufpunkt": kaufpunkt, "ausgeloest": ausgeloest,
                "einstieg": einstieg,
                "stop_code": min(l[i] - 0.01, kaufpunkt * STOP_MAX),
                # Vergleichs-Einstiege
                "schluss_luecke": c[i],          # Kauf am Luecken-Tag selbst
                "open_folgetag": o[j],           # Kauf zur Eroeffnung
                # Der Weg danach, ab dem Folgetag
                "hochs": list(h[j:j + TAGE_MAX + 1]),
                "tiefs": list(l[j:j + TAGE_MAX + 1]),
                "schluss": list(c[j:j + TAGE_MAX + 1]),
            }
            ereignisse.append(e)
    return ereignisse


# ---------------------------------------------------------------------------
# Ausstiegsregeln — jede liefert (Rendite, wurde_gestoppt)
# ---------------------------------------------------------------------------

def mit_stop(e, marke, tage=20, einstieg=None):
    """Halten bis Tag N, ausser der Kurs faellt auf die Marke."""
    ein = einstieg or e["einstieg"]
    for k in range(min(tage, len(e["tiefs"])) ):
        if e["tiefs"][k] <= marke:
            return marke / ein - 1, True
    n = min(tage, len(e["schluss"]) - 1)
    return e["schluss"][n] / ein - 1, False


def mit_ziel(e, marke, ziel_pct, tage=20):
    """Erst wer zuerst kommt: Ziel erreicht oder Stop gerissen."""
    ein = e["einstieg"]
    ziel = ein * (1 + ziel_pct)
    for k in range(min(tage, len(e["tiefs"]))):
        # Innerhalb eines Tages ist die Reihenfolge unbekannt. Im Zweifel
        # zuungunsten des Handels: Stop vor Ziel.
        if e["tiefs"][k] <= marke:
            return marke / ein - 1, "gestoppt"
        if e["hochs"][k] >= ziel:
            return ziel_pct, "Ziel"
    n = min(tage, len(e["schluss"]) - 1)
    return e["schluss"][n] / ein - 1, "Zeit"


def nachziehend(e, abstand, tage=20):
    """Nachziehender Stop: Ausstieg, wenn der Schluss um 'abstand' unter
    den hoechsten Schluss seit Einstieg faellt."""
    ein = e["einstieg"]
    hoch = ein
    for k in range(min(tage, len(e["schluss"]))):
        hoch = max(hoch, e["schluss"][k])
        if e["schluss"][k] <= hoch * (1 - abstand):
            return e["schluss"][k] / ein - 1, True
    n = min(tage, len(e["schluss"]) - 1)
    return e["schluss"][n] / ein - 1, False


# ---------------------------------------------------------------------------
# Filter
# ---------------------------------------------------------------------------

def filter_regeln():
    return [
        ("ohne Basisbedingung", lambda e: True),
        ("Fassung A  (25 T, 15 %, MA10+MA21)",
         lambda e: e["spanne25"] <= 0.15 and e["ueber_ma10"] and e["ueber_ma21"]),
        ("Kapitel 7 Original  (63 T, 35 %)", lambda e: e["spanne63"] <= 0.35),
        ("relativ  (63 T, <= 3x Luecke)", lambda e: e["spanne63"] <= 3 * e["gap"]),
        ("nicht ueberdehnt  (<= 15 % ueber MA50)",
         lambda e: e["ueber_ma50"] <= 0.15),
        # GERHARDS GEGENPROBE ZU ANTWORT 2 (05.08.2026): Er senkt von 5x
        # auf 3x, weil keine publizierte Quelle das Fuenffache verlangt
        # (Weinstein 2 bis 3x). Gefragt ist, ob 3x besser abschneidet als
        # 5x UND als gar kein Filter.
        ("Volumen ab 2x O10", lambda e: e["r10"] >= 2.0),
        ("Volumen ab 3x O10  (NEU)", lambda e: e["r10"] >= 3.0),
        ("Volumen ab 3x O50  (NEU)", lambda e: e["r50"] >= 3.0),
        ("Volumen ab 4x O10", lambda e: e["r10"] >= 4.0),
        ("Volumen ab 5x O10  (alt)", lambda e: e["r10"] >= 5.0),
        ("Volumen ab 5x O50  (alt)", lambda e: e["r50"] >= 5.0),
        ("Volumen UNTER 3x O10", lambda e: e["r10"] < 3.0),
        ("Schluss im obersten Zehntel", lambda e: e["schlusspos"] >= 0.90),
    ]


# ---------------------------------------------------------------------------
# Auswertung
# ---------------------------------------------------------------------------

def monate_aus_argumenten(vorgabe):
    """Die Monatszahl aus der Befehlszeile holen.

    Ohne argparse, weil diese Werkzeuge nur EIN Argument kennen — aber
    mit Anstand: "--help" oder etwas Unlesbares brach vorher mit einem
    Rueckverfolgungsprotokoll ab (am 04.08.2026 im Fehlerdurchlauf
    aufgefallen)."""
    for arg in sys.argv[1:]:
        if arg in ("-h", "--help", "/?"):
            print(__doc__.strip())
            sys.exit(0)
        if arg.startswith("-"):
            continue                     # gehoert einem anderen Schalter
        try:
            return int(arg)
        except ValueError:
            sys.exit(f"'{arg}' ist keine Monatszahl. Aufruf: "
                     f"python {sys.argv[0]} [Monate]")
    return vorgabe


def kennzahlen(renditen):
    if not renditen:
        return None
    treffer = sum(1 for r in renditen if r > 0) / len(renditen) * 100
    gross = sum(1 for r in renditen if r >= 0.20) / len(renditen) * 100
    return {"n": len(renditen), "treffer": treffer, "median": median(renditen),
            "mittel": mean(renditen), "gross": gross}


def zeile(name, k, breite=34):
    if not k:
        return f"{name:{breite}s}      —"
    return (f"{name:{breite}s} {k['n']:4d} {k['treffer']:6.0f} "
            f"{k['median']*100:7.1f} {k['mittel']*100:7.1f} {k['gross']:6.0f}")


KOPF = (f"{'':34s} {'n':>4s} {'Tr%':>6s} {'Median':>7s} {'Mittel':>7s} "
        f"{'+20%':>6s}")


def main():
    monate = monate_aus_argumenten(24)

    import pandas as pd
    import yfinance as yf

    df = pd.read_excel(XLSX, sheet_name="Kaufpunkte")
    ticker = sorted({str(t).strip().upper() for t in df["Ticker"]})
    print(f"{len(ticker)} Aktien, {monate} Monate Tagesdaten.")

    roh = yf.download(" ".join(ticker), period=f"{monate}mo", interval="1d",
                      group_by="ticker", progress=False, auto_adjust=False,
                      threads=True)
    ereignisse = ereignisse_sammeln(roh, ticker)
    gehandelt = [e for e in ereignisse if e["einstieg"]]
    ohne = [e for e in ereignisse if not e["einstieg"]]
    print(f"\n{len(ereignisse)} Gap-and-Go-Tage. Am Folgetag ausgeloest: "
          f"{len(gehandelt)} ({len(gehandelt)/len(ereignisse)*100:.0f} %), "
          f"nicht ausgeloest: {len(ohne)}.")
    print("\n'Tr%' = Anteil mit Gewinn, '+20%' = Anteil mit mindestens "
          "20 % Gewinn.\nAlles nach 20 Handelstagen, wenn nicht anders "
          "vermerkt.\n")

    def roh20(e):
        n = min(20, len(e["schluss"]) - 1)
        return e["schluss"][n] / e["einstieg"] - 1

    # --- 1. Das Signal ohne alles ------------------------------------
    print("=" * 74)
    print("1. DAS EINSTIEGSSIGNAL OHNE JEDEN AUSSTIEGSSTOP")
    print("=" * 74)
    print(KOPF)
    for tage in (5, 10, 20, 40):
        r = [e["schluss"][min(tage, len(e["schluss"]) - 1)] / e["einstieg"] - 1
             for e in gehandelt]
        print(zeile(f"halten {tage} Tage", kennzahlen(r)))

    # --- 2. Filter ----------------------------------------------------
    print("\n" + "=" * 74)
    print("2. WAS BRINGEN DIE EINSTIEGSFILTER? (20 Tage, ohne Stop)")
    print("=" * 74)
    print(KOPF)
    for name, regel in filter_regeln():
        teil = [e for e in gehandelt if regel(e)]
        print(zeile(name, kennzahlen([roh20(e) for e in teil])))

    # --- 3. Stop, ungewichtet ----------------------------------------
    print("\n" + "=" * 74)
    print("3. WAS BEWIRKT DER STOP? (Rendite je Handel)")
    print("=" * 74)
    print(KOPF + "  Stop%")
    stops = ([("wie im Code", None), ("eng gelesen (KP x 0,97)", "eng")]
             + [(f"fest {p:.0f} %", p / 100) for p in (3, 5, 8, 12, 15, 20, 25)]
             + [("gar keiner", 0.0)])
    for name, art in stops:
        werte, raus = [], 0
        for e in gehandelt:
            if art is None:
                r, g = mit_stop(e, e["stop_code"])
            elif art == "eng":
                r, g = mit_stop(e, e["kaufpunkt"] * STOP_MAX)
            elif art == 0.0:
                r, g = roh20(e), False
            else:
                r, g = mit_stop(e, e["einstieg"] * (1 - art))
            werte.append(r)
            raus += 1 if g else 0
        k = kennzahlen(werte)
        print(zeile(name, k) + f" {raus/len(werte)*100:6.0f}")

    # --- 4. RISIKOGEWICHTET ------------------------------------------
    print("\n" + "=" * 74)
    print("4. RISIKOGEWICHTET — die Frage nach der Positionsgroesse")
    print("=" * 74)
    print("Wer je Handel denselben Betrag riskiert, kauft bei weitem Stop")
    print("eine kleinere Position. Gerechnet wird deshalb in R, dem")
    print("Vielfachen des riskierten Betrags: R = Rendite geteilt durch den")
    print("Stopabstand. Ein ausgestoppter Handel ist genau minus 1 R.")
    print("'Summe R' ist der Gewinn ueber alle Handel in riskierten")
    print("Einheiten; das ist die Zahl, die fuers Depot zaehlt.\n")
    print(f"{'':34s} {'n':>4s} {'Med R':>7s} {'Mittel R':>9s} "
          f"{'Summe R':>9s} {'Abstand':>8s}")
    for name, art in stops:
        if art == 0.0:
            continue                      # ohne Stop gibt es kein R
        rs, abstaende = [], []
        for e in gehandelt:
            if art is None:
                marke = e["stop_code"]
            elif art == "eng":
                marke = e["kaufpunkt"] * STOP_MAX
            else:
                marke = e["einstieg"] * (1 - art)
            abstand = (e["einstieg"] - marke) / e["einstieg"]
            if abstand <= 0:
                continue
            r, _ = mit_stop(e, marke)
            rs.append(r / abstand)
            abstaende.append(abstand)
        if not rs:
            continue
        print(f"{name:34s} {len(rs):4d} {median(rs):7.2f} {mean(rs):9.2f} "
              f"{sum(rs):9.1f} {median(abstaende)*100:7.1f} %")

    # --- 5. Andere Ausstiege -----------------------------------------
    print("\n" + "=" * 74)
    print("5. ANDERE AUSSTIEGE (jeweils mit dem Stop aus dem Code)")
    print("=" * 74)
    print(KOPF)
    for ziel in (0.10, 0.15, 0.20, 0.30):
        werte = [mit_ziel(e, e["stop_code"], ziel)[0] for e in gehandelt]
        anteil = sum(1 for e in gehandelt
                     if mit_ziel(e, e["stop_code"], ziel)[1] == "Ziel")
        print(zeile(f"Ziel +{ziel*100:.0f} % ({anteil} mal erreicht)",
                    kennzahlen(werte)))
    for ab in (0.08, 0.12, 0.15, 0.20):
        werte = [nachziehend(e, ab)[0] for e in gehandelt]
        print(zeile(f"nachziehend {ab*100:.0f} % unter Hoch",
                    kennzahlen(werte)))

    # --- 6. Einstiegsvarianten ---------------------------------------
    print("\n" + "=" * 74)
    print("6. EINSTIEGSVARIANTEN (20 Tage, ohne Stop)")
    print("=" * 74)
    print(KOPF)
    print(zeile("Kaufpunkt am Folgetag (Kapitel 7)",
                kennzahlen([roh20(e) for e in gehandelt])))
    r = []
    for e in gehandelt:
        n = min(20, len(e["schluss"]) - 1)
        r.append(e["schluss"][n] / e["open_folgetag"] - 1)
    print(zeile("Eroeffnung des Folgetags", kennzahlen(r)))
    r = []
    for e in ereignisse:
        n = min(20, len(e["schluss"]) - 1)
        r.append(e["schluss"][n] / e["schluss_luecke"] - 1)
    print(zeile("Schluss des Luecken-Tages (alle)", kennzahlen(r)))
    # DER SAUBERE VERGLEICH ZUR FOLGETAGS-REGEL (Mathias, 05.08.2026:
    # "Gap and Go ist eigentlich Follow Through Day"). Beide Gruppen ab
    # DEMSELBEN Einstieg, dem Schluss des Luecken-Tages — nur so misst
    # man die Regel selbst und nicht den unterschiedlichen Einstiegskurs.
    print("\nDie Folgetags-Regel als reiner Filter, beide ab dem Schluss")
    print("des Luecken-Tages gerechnet:")
    print(KOPF)
    for name, menge in (("Kaufpunkt am Folgetag ERREICHT", gehandelt),
                        ("Kaufpunkt NICHT erreicht", ohne)):
        r = []
        for e in menge:
            n = min(20, len(e["schluss"]) - 1)
            r.append(e["schluss"][n] / e["schluss_luecke"] - 1)
        print(zeile("  " + name, kennzahlen(r)))

    # --- 7. Lueckengroesse -------------------------------------------
    print("\n" + "=" * 74)
    print("7. NACH LUECKENGROESSE (20 Tage, ohne Stop)")
    print("=" * 74)
    print(KOPF)
    for unten, oben in ((0.07, 0.10), (0.10, 0.15), (0.15, 0.25), (0.25, 9)):
        teil = [e for e in gehandelt if unten <= e["gap"] < oben]
        name = (f"Luecke {unten*100:.0f} bis {oben*100:.0f} %"
                if oben < 9 else f"Luecke ueber {unten*100:.0f} %")
        print(zeile(name, kennzahlen([roh20(e) for e in teil])))

    # --- 8. Was trennt Gewinner von Verlierern? ----------------------
    print("\n" + "=" * 74)
    print("8. MERKMALE: GEWINNER GEGEN VERLIERER (20 Tage, ohne Stop)")
    print("=" * 74)
    gew = [e for e in gehandelt if roh20(e) > 0]
    ver = [e for e in gehandelt if roh20(e) <= 0]
    for feld, txt in (("gap", "Lueckengroesse"),
                      ("schlusspos", "Schlussposition"),
                      ("r10", "Volumen gegen O10"),
                      ("r50", "Volumen gegen O50"),
                      ("spanne25", "Basisspanne 25 Tage"),
                      ("spanne63", "Basisspanne 63 Tage"),
                      ("ueber_ma50", "Abstand zum MA50")):
        g = median([e[feld] for e in gew]) if gew else 0
        v = median([e[feld] for e in ver]) if ver else 0
        print(f"  {txt:24s} Gewinner {g:8.2f}   Verlierer {v:8.2f}")
    print(f"\n  {len(gew)} Gewinner, {len(ver)} Verlierer")


if __name__ == "__main__":
    main()
