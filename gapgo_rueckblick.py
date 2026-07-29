#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HAETTE GAP AND GO JE AUSGELOEST — UND MIT WELCHEM MASSSTAB?
============================================================
Mathias' Frage vom 29.07.2026: Was spricht gegen den Zehntageschnitt,
und haette das Muster damit bisher schon ausgeloest?

Der Waechter hat seit dem 23.07. keine einzige Gap-and-Go-Meldung
verschickt. Sechs Handelstage sind aber zu wenig, um daraus etwas zu
schliessen. Also wird zurueckgerechnet: acht Monate Tagesdaten, alle
Aktien der laufenden Liste, dieselben fuenf Pflichtkriterien aus
Kapitel 7 wie im Waechter.

Geprueft werden drei Massstaebe fuer dasselbe Volumenkriterium:
  * Faktor 5 gegen den 10-Tage-Schnitt   (Kapitel 7 im Wortlaut)
  * Faktor 5 gegen den 50-Tage-Schnitt   (was jetzt im Code steht)
  * Faktor 4,25 gegen den 50-Tage-Schnitt (die Umrechnung, mein
    Vorschlag: gleiche Strenge wie im Wortlaut, aber ein Massstab)

Bewusst auf ABGESCHLOSSENEN Tagen: Die Fruehvolumen-Regel der ersten
halben Stunde laesst sich rueckblickend nicht pruefen, das sagt Kapitel
7 selbst. Gerechnet wird deshalb die Tagesregel, die auch der
naechtliche Scanner sieht.

Aufruf:  python gapgo_rueckblick.py [Monate]
"""

import sys

XLSX = "kaufpunkte_aktuell.xlsx"
GAP_MIN = 0.07
FLAT_TAGE = 25
FLAT_SPANNE = 0.15
FLAT_MA = (10, 21)
SCHLUSS_POS = 0.80


def main():
    monate = int(sys.argv[1]) if len(sys.argv) > 1 else 8

    import pandas as pd
    import yfinance as yf

    df = pd.read_excel(XLSX, sheet_name="Kaufpunkte")
    ticker = sorted({str(t).strip().upper() for t in df["Ticker"]})
    print(f"{len(ticker)} Aktien, {monate} Monate Tagesdaten.\n")

    roh = yf.download(" ".join(ticker), period=f"{monate}mo", interval="1d",
                      group_by="ticker", progress=False, auto_adjust=False,
                      threads=True)

    global KANDIDATEN, SPANNEN
    KANDIDATEN = []
    SPANNEN = []
    treffer = {"o10_5": [], "o50_5": [], "o50_425": []}
    # Gegenprobe: Wie viele Kandidaten haette die URSPRUENGLICHE Flat-Base
    # aus Kapitel 7 durchgelassen (63 bis 126 Tage, Spanne bis 35 %)?
    # Gerhard hat sie am 28.07. durch Fassung A ersetzt (25 Tage, 15 %,
    # ueber MA10 und MA21). Falls das Muster nie ausloest, ist die Frage,
    # ob die neue Fassung zu eng ist.
    alt_flat = 0
    kreuz = {"vol5_o10": 0, "vol5_o50": 0, "flat_und_vol": 0,
             "eng": 0, "eng_und_vol": 0, "ma": 0, "ma_und_vol": 0}
    # Wie weit kommen die Kandidaten? Zeigt, WORAN es scheitert.
    stufen = {"gap": 0, "verteidigt": 0, "flat_base": 0, "schluss": 0,
              "volumen_egal": 0}
    handelstage = 0

    for t in ticker:
        try:
            d = roh[t].dropna(subset=["Open", "High", "Low", "Close", "Volume"])
        except Exception:
            continue
        if len(d) < 60:
            continue
        o, h, l, c, v = (d["Open"].values, d["High"].values, d["Low"].values,
                         d["Close"].values, d["Volume"].values)
        handelstage += len(d) - 55
        for i in range(55, len(d)):
            prev = c[i - 1]
            if prev <= 0:
                continue
            if o[i] / prev - 1 < GAP_MIN:
                continue
            stufen["gap"] += 1
            if l[i] <= prev:
                continue                      # Luecke nicht verteidigt
            stufen["verteidigt"] += 1

            # KREUZPROBE (29.07.2026): Die Kriterien einzeln zaehlen, nicht
            # nur hintereinander. Sonst sieht man nie, ob das Volumen
            # ueberhaupt je erreicht wird oder ob ein frueheres Kriterium
            # genau die Faelle wegsiebt, die es erreicht haetten.
            o10x = v[i - 10:i].mean()
            o50x = v[i - 50:i].mean()
            vol5_10 = o10x > 0 and v[i] / o10x >= 5.0
            vol5_50 = o50x > 0 and v[i] / o50x >= 5.0
            if vol5_10:
                kreuz["vol5_o10"] += 1
            if vol5_50:
                kreuz["vol5_o50"] += 1

            # Gegenprobe mit der urspruenglichen Fassung aus Kapitel 7
            if i >= 63:
                a_l, a_h = l[i - 63:i], h[i - 63:i]
                a_tief = a_l.min()
                if a_tief > 0 and (a_h.max() - a_tief) / a_tief <= 0.35:
                    alt_flat += 1

            # Flat Base der 25 Tage VOR dem Gap-Tag
            f_l, f_h = l[i - FLAT_TAGE:i], h[i - FLAT_TAGE:i]
            tief = f_l.min()
            if tief <= 0:
                continue
            spanne = (f_h.max() - tief) / tief
            eng = spanne <= FLAT_SPANNE
            ueber_ma = all(c[i] > c[i - tage:i].mean() for tage in FLAT_MA)
            # WELCHER TEIL von Fassung A siebt? Beide Halbkriterien
            # einzeln zaehlen, jeweils auch zusammen mit dem Volumen.
            # Fuer die Schwellen-Reihe unten: jeden verteidigten Gap mit
            # seiner Basis-Spanne festhalten.
            SPANNEN.append((spanne, ueber_ma, vol5_10))
            if eng:
                kreuz["eng"] += 1
                if vol5_10:
                    kreuz["eng_und_vol"] += 1
            if ueber_ma:
                kreuz["ma"] += 1
                if vol5_10:
                    kreuz["ma_und_vol"] += 1
            if not eng or not ueber_ma:
                continue
            stufen["flat_base"] += 1
            if vol5_10:
                kreuz["flat_und_vol"] += 1

            spanne_tag = h[i] - l[i]
            pos = (c[i] - l[i]) / spanne_tag if spanne_tag > 0 else 1.0
            if pos < SCHLUSS_POS:
                continue
            stufen["schluss"] += 1
            stufen["volumen_egal"] += 1

            o10 = v[i - 10:i].mean()
            o50 = v[i - 50:i].mean()
            datum = str(d.index[i].date())
            r10 = v[i] / o10 if o10 > 0 else 0
            r50 = v[i] / o50 if o50 > 0 else 0
            KANDIDATEN.append((datum, t, r10, r50, o[i] / prev - 1, pos))
            if r10 >= 5.0:
                treffer["o10_5"].append((datum, t, r10, r50))
            if r50 >= 5.0:
                treffer["o50_5"].append((datum, t, r10, r50))
            if r50 >= 4.25:
                treffer["o50_425"].append((datum, t, r10, r50))

    print(f"Untersucht: rund {handelstage:,} Aktien-Tage.\n")
    print("Wo die Kandidaten haengenbleiben (vor dem Volumenkriterium):")
    print(f"  Lücke ab 7 %:            {stufen['gap']:6,}")
    print(f"  davon Lücke verteidigt:  {stufen['verteidigt']:6,}")
    print(f"  davon mit Flat Base:     {stufen['flat_base']:6,}"
          f"   (Fassung A: 25 Tage, 15 %, über MA10 und MA21)")
    print(f"    zum Vergleich, Kapitel 7 im Original "
          f"(63 Tage, 35 %):  {alt_flat:5,}")
    print(f"  davon Schluss oben:      {stufen['schluss']:6,}")
    print(f"  → so viele Kandidaten kommen überhaupt bis zum Volumen: "
          f"{stufen['volumen_egal']}\n")

    print("KREUZPROBE — die Kriterien EINZELN, nicht hintereinander:")
    print(f"  verteidigte Lücken gesamt:                 "
          f"{stufen['verteidigt']:5,}")
    print(f"  davon mit Volumen ab 5× Ø10:               "
          f"{kreuz['vol5_o10']:5,}")
    print(f"  davon mit Volumen ab 5× Ø50:               "
          f"{kreuz['vol5_o50']:5,}")
    print(f"  davon mit Flat Base UND Volumen ab 5× Ø10: "
          f"{kreuz['flat_und_vol']:5,}\n")

    print("Fassung A besteht aus ZWEI Bedingungen — einzeln betrachtet:")
    print(f"  Spanne der 25 Tage höchstens 15 %:         {kreuz['eng']:5,}")
    print(f"    davon zugleich Volumen ab 5× Ø10:        "
          f"{kreuz['eng_und_vol']:5,}")
    print(f"  Kurs über MA10 UND MA21:                   {kreuz['ma']:5,}")
    print(f"    davon zugleich Volumen ab 5× Ø10:        "
          f"{kreuz['ma_und_vol']:5,}\n")

    print("WIE VIEL BRINGT EINE WEITERE SPANNE? (25 Tage, mit MA-Bedingung)")
    print("  Spanne bis   Kandidaten   davon mit Volumen ab 5× Ø10")
    for grenze in (0.15, 0.20, 0.25, 0.30, 0.35, 0.50):
        passt = [s for s in SPANNEN if s[0] <= grenze and s[1]]
        mit_vol = [s for s in passt if s[2]]
        print(f"    {grenze*100:4.0f} %      {len(passt):6,}            "
              f"{len(mit_vol):5,}")
    print()

    if KANDIDATEN:
        print("Die Kandidaten, die bis zum Volumen kamen:")
        for datum, t, r10, r50, gap, pos in sorted(KANDIDATEN):
            print(f"  {datum}  {t:6s}  Lücke {gap*100:5.1f} %, "
                  f"Schluss bei {pos*100:3.0f} % der Spanne, "
                  f"Volumen {r10:5.2f}× Ø10 und {r50:5.2f}× Ø50")
        print()

    print("Wie viele davon nehmen die Volumenhürde:")
    print(f"  Faktor 5,00 gegen Ø10  (Kapitel 7):     "
          f"{len(treffer['o10_5']):3d}")
    print(f"  Faktor 5,00 gegen Ø50  (jetzt im Code): "
          f"{len(treffer['o50_5']):3d}")
    print(f"  Faktor 4,25 gegen Ø50  (Umrechnung):    "
          f"{len(treffer['o50_425']):3d}")

    alle = {}
    for art, liste in treffer.items():
        for datum, t, r10, r50 in liste:
            alle.setdefault((datum, t), (r10, r50, set()))[2].add(art)
    if alle:
        print("\nDie Treffer im Einzelnen:")
        for (datum, t), (r10, r50, arten) in sorted(alle.items()):
            wer = []
            if "o10_5" in arten:
                wer.append("Ø10×5")
            if "o50_5" in arten:
                wer.append("Ø50×5")
            if "o50_425" in arten:
                wer.append("Ø50×4,25")
            print(f"  {datum}  {t:6s}  Volumen {r10:5.1f}× Ø10, "
                  f"{r50:5.1f}× Ø50   →  {', '.join(wer)}")
    else:
        print("\nKein einziger Treffer in diesem Zeitraum, mit keinem "
              "der drei Maßstäbe.")


if __name__ == "__main__":
    main()
