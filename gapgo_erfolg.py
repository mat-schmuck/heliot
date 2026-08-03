#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GAP AND GO — WELCHER FILTER TRENNT GEWINNER VON VERLIERERN?
============================================================
Mathias' Auftrag vom 03.08.2026: Die bisherigen Messungen zaehlten nur,
WIE VIELE Signale eine Filterfassung erzeugt. Das sagt nichts darueber,
ob die Signale etwas getaugt haben. Dieses Werkzeug misst den Erfolg.

DER ABLAUF, so nah an Kapitel 7 wie moeglich
  Ereignis:  Luecke ab 7 % nach oben, verteidigt (Tagestief bleibt ueber
             dem Vortagesschluss), Schluss im oberen Fuenftel.
  Kaufpunkt: Tageshoch plus einen Cent.
  Einstieg:  am FOLGETAG, sobald der Kaufpunkt erreicht wird. Oeffnet
             die Aktie schon darueber, wird zur Eroeffnung gekauft (das
             ist der schlechtere, also ehrliche Fall). Wird der
             Kaufpunkt am Folgetag gar nicht erreicht, gibt es KEINEN
             Handel - auch das ist ein Ergebnis.
  Stopp:     das engere von Tagestief minus ein Cent und Kaufpunkt mal
             0,97, genau wie im Waechter.
  Ausgang:   nach 5, 10 und 20 Handelstagen, oder frueher am Stopp.

WAS GEMESSEN WIRD, je Ereignis: Lueckengroesse, Schlussposition,
Volumen gegen den Zehn- und den Fuenfzigtageschnitt, Basisspanne ueber
25 und 63 Tage, Abstand zum Fuenfzigtageschnitt, und der Ausgang.
Danach wird jede diskutierte Filterregel auf dieselbe Ereignisliste
angewandt und verglichen.

WAS DIESE MESSUNG NICHT KANN
  Die Aktienliste ist die HEUTIGE Wochenliste. Wer heute im Screener
  steht, hat die letzten Monate ueberstanden; das faerbt die absoluten
  Renditen nach oben. Fuer den VERGLEICH der Filter untereinander ist
  das weniger schlimm, weil alle Filter dieselbe Verzerrung teilen -
  aber die absoluten Zahlen sind zu gut, um sie fuer bare Muenze zu
  nehmen. Ausserdem sind es wenige Ereignisse.

Aufruf:  python gapgo_erfolg.py [Monate]        (Vorgabe 24)
"""

import sys
from statistics import median

XLSX = "kaufpunkte_aktuell.xlsx"
GAP_MIN = 0.07
SCHLUSS_POS = 0.80
HORIZONTE = (5, 10, 20)
STOP_MAX = 0.97              # Kaufpunkt mal 0,97 als weitester Stopp


def ereignisse_sammeln(roh, ticker, start=65):
    """Alle Gap-and-Go-Tage samt Merkmalen und Ausgang."""
    import numpy as np
    ereignisse = []
    for t in ticker:
        try:
            d = roh[t].dropna(subset=["Open", "High", "Low", "Close", "Volume"])
        except Exception:
            continue
        if len(d) <= start + max(HORIZONTE) + 2:
            continue
        o, h, l, c, v = (d["Open"].values, d["High"].values, d["Low"].values,
                         d["Close"].values, d["Volume"].values)
        datum = d.index

        for i in range(start, len(d) - max(HORIZONTE) - 1):
            prev = c[i - 1]
            if prev <= 0 or o[i] / prev - 1 < GAP_MIN:
                continue
            if l[i] <= prev:
                continue                       # Luecke nicht verteidigt
            spanne_tag = h[i] - l[i]
            if spanne_tag <= 0:
                continue
            if (c[i] - l[i]) / spanne_tag < SCHLUSS_POS:
                continue                       # Schluss nicht im oberen Fuenftel

            gap = o[i] / prev - 1
            kaufpunkt = h[i] + 0.01
            stop = min(l[i] - 0.01, kaufpunkt * STOP_MAX)

            # --- Einstieg am Folgetag ---------------------------------
            j = i + 1
            if h[j] < kaufpunkt:
                einstieg = None                # Kaufpunkt nie erreicht
            else:
                einstieg = max(o[j], kaufpunkt)

            merkmale = {
                "datum": str(datum[i].date()), "ticker": t,
                "gap": gap,
                "schlusspos": (c[i] - l[i]) / spanne_tag,
                "r10": v[i] / v[i - 10:i].mean() if v[i - 10:i].mean() > 0 else 0,
                "r50": v[i] / v[i - 50:i].mean() if v[i - 50:i].mean() > 0 else 0,
                "spanne25": ((h[i - 25:i].max() - l[i - 25:i].min())
                             / l[i - 25:i].min()) if l[i - 25:i].min() > 0 else 9,
                "spanne63": ((h[i - 63:i].max() - l[i - 63:i].min())
                             / l[i - 63:i].min()) if l[i - 63:i].min() > 0 else 9,
                "ueber_ma50": (c[i - 1] / c[i - 50:i].mean() - 1)
                              if c[i - 50:i].mean() > 0 else 9,
                "ueber_ma10": c[i] > c[i - 10:i].mean(),
                "ueber_ma21": c[i] > c[i - 21:i].mean(),
                "einstieg": einstieg, "kaufpunkt": kaufpunkt, "stop": stop,
            }

            # --- Ausgang ----------------------------------------------
            if einstieg:
                for n in HORIZONTE:
                    bis = min(j + n, len(d) - 1)
                    tiefs = l[j:bis + 1]
                    ausstieg = c[bis]
                    gestoppt = bool((tiefs <= stop).any())
                    if gestoppt:
                        ausstieg = stop        # zum Stopp verkauft
                    merkmale[f"ret{n}"] = ausstieg / einstieg - 1
                    merkmale[f"stop{n}"] = gestoppt
                    # DASSELBE OHNE STOPP. Der Stopp aus Kapitel 7 liegt
                    # hoechstens 3 % unter dem Kaufpunkt — an einem
                    # Luecken-Tag ist das eng. Nur so laesst sich
                    # trennen, ob ein Filter nichts taugt oder ob der
                    # Stopp die Bewegung abschneidet.
                    merkmale[f"roh{n}"] = c[bis] / einstieg - 1
                bis20 = min(j + 20, len(d) - 1)
                merkmale["hoch20"] = h[j:bis20 + 1].max() / einstieg - 1
                # Fuer die Stoppvarianten: der Tiefstkursverlauf.
                merkmale["tiefs20"] = list(l[j:bis20 + 1])
            ereignisse.append(merkmale)
    return ereignisse


def _mit_stopp(e, grenze):
    """Ergebnis nach 20 Tagen mit einer anderen Stoppmarke.

    Braucht den Tiefstkurs-Verlauf, der beim Sammeln je Ereignis
    mitgeschrieben wurde."""
    for k, tief in enumerate(e["tiefs20"]):
        if tief <= grenze:
            return grenze / e["einstieg"] - 1, True
    return e["roh20"], False


def filter_regeln():
    """Alle diskutierten Regeln als (Name, Funktion auf einem Ereignis)."""
    return [
        ("ohne Basisbedingung", lambda e: True),
        ("Fassung A  (25 T, 15 %, MA10+MA21)",
         lambda e: e["spanne25"] <= 0.15 and e["ueber_ma10"] and e["ueber_ma21"]),
        ("Kapitel 7 Original  (63 T, 35 %)", lambda e: e["spanne63"] <= 0.35),
        ("relativ  (63 T, <= 3x Luecke)",
         lambda e: e["spanne63"] <= 3 * e["gap"]),
        ("relativ  (25 T, <= 3x Luecke)",
         lambda e: e["spanne25"] <= 3 * e["gap"]),
        ("nicht ueberdehnt  (<= 15 % ueber MA50)",
         lambda e: e["ueber_ma50"] <= 0.15),
        ("nicht ueberdehnt  (<= 5 % ueber MA50)",
         lambda e: e["ueber_ma50"] <= 0.05),
        ("relativ 3x UND nicht ueberdehnt 15 %",
         lambda e: e["spanne63"] <= 3 * e["gap"] and e["ueber_ma50"] <= 0.15),
        ("nur Volumen ab 5x O10", lambda e: e["r10"] >= 5.0),
        ("nur Volumen ab 5x O50", lambda e: e["r50"] >= 5.0),
        ("nur Luecke ab 15 %", lambda e: e["gap"] >= 0.15),
    ]


def auswerten(name, teil, gesamt_n):
    """Eine Zeile mit den Kennzahlen einer Teilmenge."""
    gehandelt = [e for e in teil if e["einstieg"]]
    if not gehandelt:
        return (f"{name:38s} {len(teil):4d} {0:6d}" + "      —" * 4)
    r20 = [e["ret20"] for e in gehandelt]
    roh20 = [e["roh20"] for e in gehandelt]
    treffer20 = sum(1 for r in r20 if r > 0) / len(r20) * 100
    treffer_roh = sum(1 for r in roh20 if r > 0) / len(roh20) * 100
    gestoppt = sum(1 for e in gehandelt if e["stop20"]) / len(gehandelt) * 100
    return (f"{name:38s} {len(teil):4d} {len(gehandelt):6d} "
            f"{treffer20:6.0f} {median(r20)*100:7.1f} {gestoppt:6.0f} "
            f"{treffer_roh:7.0f} {median(roh20)*100:8.1f}")


def main():
    monate = int(sys.argv[1]) if len(sys.argv) > 1 else 24

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
    print(f"\n{len(ereignisse)} Gap-and-Go-Tage gefunden "
          f"(Luecke ab 7 %, verteidigt, Schluss im oberen Fuenftel).")
    print(f"Davon am Folgetag wirklich gekauft: {len(gehandelt)} "
          f"({len(gehandelt)/max(len(ereignisse),1)*100:.0f} %) — "
          f"bei den uebrigen wurde der Kaufpunkt nie erreicht.\n")

    if not gehandelt:
        return
    r20 = [e["ret20"] for e in gehandelt]
    print(f"Ohne jeden Filter: Trefferquote nach 20 Tagen "
          f"{sum(1 for r in r20 if r > 0)/len(r20)*100:.0f} %, "
          f"Median {median(r20)*100:+.1f} %, "
          f"ausgestoppt {sum(1 for e in gehandelt if e['stop20'])/len(gehandelt)*100:.0f} %\n")

    print("Links MIT dem Stopp aus Kapitel 7, rechts dasselbe OHNE Stopp.")
    kopf = (f"{'Filter':38s} {'Ereig':>4s} {'gek.':>6s} {'Tr20%':>6s} "
            f"{'Med20':>7s} {'Stop%':>6s} {'ohTr20':>7s} {'ohMed20':>8s}")
    print(kopf)
    print("-" * len(kopf))
    for name, regel in filter_regeln():
        print(auswerten(name, [e for e in ereignisse if regel(e)],
                        len(ereignisse)))

    # --- Der Stopp selbst ---------------------------------------------
    # Der Waechter rechnet min(Tagestief - 1 Cent, Kaufpunkt x 0,97),
    # nimmt also den WEITEREN der beiden. Sein eigener Kommentar sagt
    # "das engere". Der Unterschied ist erheblich, also wird beides
    # gemessen, dazu feste Abstaende.
    abstaende = [e["einstieg"] / e["stop"] - 1 for e in gehandelt]
    print(f"\nWie weit liegt der Stopp wirklich unter dem Einstieg? "
          f"Median {median(abstaende)*100:.1f} %, "
          f"engster {min(abstaende)*100:.1f} %, "
          f"weitester {max(abstaende)*100:.1f} %")
    print("\nWAS BEWIRKT DER STOPP? Dieselben Ereignisse, andere Stoppregel:")
    print(f"  {'Stoppregel':34s} {'Tr20%':>6s} {'Med20':>7s} {'Stop%':>6s}")
    for name, tiefe in (("wie im Code (weiterer)", None),
                        ("wie beschrieben (engerer)", "eng"),
                        ("fest 3 % unter Einstieg", 0.03),
                        ("fest 5 %", 0.05),
                        ("fest 8 %", 0.08),
                        ("fest 12 %", 0.12),
                        # WEITER als der Code rechnet. Ohne diese Zeilen
                        # waere nur belegt, dass enger schlechter ist,
                        # nicht ob es zwischen dem jetzigen Stop und gar
                        # keinem noch etwas Besseres gibt.
                        ("fest 15 %", 0.15),
                        ("fest 20 %", 0.20),
                        ("fest 25 %", 0.25),
                        ("fest 30 %", 0.30),
                        ("gar keiner", 0.0)):
        ergebnis = []
        raus = 0
        for e in gehandelt:
            if tiefe is None:
                r, g = e["ret20"], e["stop20"]
            elif tiefe == "eng":
                # max() statt min(): das engere der beiden Masze
                grenze = max(e["kaufpunkt"] * STOP_MAX,
                             e["stop"])  # stop ist bereits das weitere
                grenze = e["kaufpunkt"] * STOP_MAX
                r, g = _mit_stopp(e, grenze)
            elif tiefe == 0.0:
                r, g = e["roh20"], False
            else:
                r, g = _mit_stopp(e, e["einstieg"] * (1 - tiefe))
            ergebnis.append(r)
            raus += 1 if g else 0
        tr = sum(1 for r in ergebnis if r > 0) / len(ergebnis) * 100
        print(f"  {name:34s} {tr:6.0f} {median(ergebnis)*100:7.1f} "
              f"{raus/len(ergebnis)*100:6.0f}")

    print("\nWORAN LIEGT ES? Merkmale der Gewinner gegen die Verlierer")
    print("(Median ueber alle gehandelten Ereignisse, 20 Tage):")
    gewinner = [e for e in gehandelt if e["ret20"] > 0]
    verlierer = [e for e in gehandelt if e["ret20"] <= 0]
    for feld, txt in (("gap", "Lueckengroesse"),
                      ("schlusspos", "Schlussposition"),
                      ("r10", "Volumen gegen O10"),
                      ("r50", "Volumen gegen O50"),
                      ("spanne25", "Basisspanne 25 Tage"),
                      ("spanne63", "Basisspanne 63 Tage"),
                      ("ueber_ma50", "Abstand zum MA50")):
        g = median([e[feld] for e in gewinner]) if gewinner else 0
        v = median([e[feld] for e in verlierer]) if verlierer else 0
        print(f"  {txt:24s} Gewinner {g:8.2f}   Verlierer {v:8.2f}")
    print(f"\n  {len(gewinner)} Gewinner, {len(verlierer)} Verlierer")


if __name__ == "__main__":
    main()
