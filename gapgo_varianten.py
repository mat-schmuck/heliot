#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GAP AND GO — WELCHE ANPASSUNG DER BASIS BRINGT WAS?
====================================================
Mathias' Frage vom 03.08.2026: Warum nicht die Nicht-Ueberdehnung
(Moeglichkeit 2)? Und welche Anpassungen vertragen sich miteinander?

Kapitel 7 verlangt vier Dinge am Luecken-Tag und eines davor:
    Luecke ab 7 %, verteidigt, Schluss im oberen Fuenftel, Volumen
    ab dem Fuenffachen, und davor eine Flat Base.
Die Basis und das Volumen arbeiten gegeneinander (nachgemessen am
03.08.2026). Dieses Werkzeug rechnet die vorgeschlagenen Alternativen
durch, einzeln UND in Kombination, ueber dasselbe Universum und
dieselben acht Monate.

DIE VARIANTEN
  A          Fassung A: 25 Tage, Spanne <= 15 %, ueber MA10 und MA21
  original   Kapitel 7 im Original: 63 Tage, Spanne <= 35 %
  relativ    Basisspanne <= Faktor x Lueckengroesse (maszstabsfrei)
  nichtueber Kurs vor der Luecke hoechstens x % ueber dem MA50
  ohne       gar keine Basisbedingung (Basis nur als Guetesiegel)

Gemessen wird immer dieselbe Kette: Luecke, verteidigt, BASIS, Schluss
oben, Volumen. Ausgegeben wird, wie viele Kandidaten jede Stufe
ueberstehen und wie viele davon die drei Volumenmaszstaebe nehmen.

Aufruf:  python gapgo_varianten.py [Monate]
"""

import sys

XLSX = "kaufpunkte_aktuell.xlsx"
GAP_MIN = 0.07
SCHLUSS_POS = 0.80
MA_LANG = 50                 # Bezug fuer die Nicht-Ueberdehnung


def basis_pruefer():
    """Alle zu pruefenden Basis-Varianten als (Name, Funktion).

    Jede Funktion bekommt den ganzen Kursverlauf, den Index des
    Luecken-Tages und die Lueckengroesse und sagt Ja oder Nein."""
    p = []

    def flat(tage, spanne, mas=()):
        def f(h, l, c, i, gap):
            if i < tage or (mas and i < max(mas)):
                return False
            tief = l[i - tage:i].min()
            if tief <= 0:
                return False
            if (h[i - tage:i].max() - tief) / tief > spanne:
                return False
            return all(c[i] > c[i - m:i].mean() for m in mas)
        return f

    def relativ(tage, faktor):
        # Die Basisspanne im Verhaeltnis zur Luecke. Eine 7-Prozent-
        # Luecke aus einer 20-Prozent-Basis ist ein Ausbruch; dieselbe
        # Luecke aus einer 40-Prozent-Basis geht im Rauschen unter.
        def f(h, l, c, i, gap):
            if i < tage:
                return False
            tief = l[i - tage:i].min()
            if tief <= 0:
                return False
            return (h[i - tage:i].max() - tief) / tief <= faktor * gap
        return f

    def nichtueber(grenze):
        # Nicht die Ruhe wird geprueft, sondern ob noch Weg nach oben
        # ist: Der Schluss VOR der Luecke darf hoechstens so weit ueber
        # dem Fuenfzigtageschnitt stehen.
        def f(h, l, c, i, gap):
            if i < MA_LANG + 1:
                return False
            ma = c[i - MA_LANG:i].mean()
            return ma > 0 and (c[i - 1] / ma - 1) <= grenze
        return f

    p.append(("A  (25 T, 15 %, MA10+MA21)", flat(25, 0.15, (10, 21))))
    p.append(("original  (63 T, 35 %)", flat(63, 0.35)))
    for fk in (2.0, 3.0, 4.0, 5.0):
        p.append((f"relativ  (63 T, <= {fk:.0f}x Luecke)", relativ(63, fk)))
    for fk in (2.0, 3.0, 4.0, 5.0):
        p.append((f"relativ  (25 T, <= {fk:.0f}x Luecke)", relativ(25, fk)))
    for g in (0.05, 0.10, 0.15, 0.20, 0.30):
        p.append((f"nichtueber  (<= {g*100:.0f} % ueber MA50)", nichtueber(g)))
    p.append(("ohne  (keine Basisbedingung)", lambda h, l, c, i, gap: True))

    # KOMBINATIONEN. Zwei Bedingungen zugleich sind immer strenger als
    # jede einzelne — die Frage ist, wie viel dabei uebrig bleibt.
    def und(a, b):
        return lambda h, l, c, i, gap: a(h, l, c, i, gap) and b(h, l, c, i, gap)

    p.append(("relativ 3x  UND  nichtueber 15 %",
              und(relativ(63, 3.0), nichtueber(0.15))))
    p.append(("relativ 3x  UND  nichtueber 30 %",
              und(relativ(63, 3.0), nichtueber(0.30))))
    p.append(("original  UND  nichtueber 15 %",
              und(flat(63, 0.35), nichtueber(0.15))))
    p.append(("A  UND  nichtueber 15 %",
              und(flat(25, 0.15, (10, 21)), nichtueber(0.15))))
    return p


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

    varianten = basis_pruefer()
    zaehler = {name: {"basis": 0, "schluss": 0, "o10_5": 0, "o50_5": 0,
                      "o50_425": 0, "treffer": []} for name, _ in varianten}
    gap_gesamt = verteidigt = 0
    handelstage = 0
    # Genug Vorlauf fuer JEDES Fenster: 63 Tage Basis und 50 Tage MA
    # plus einen Tag Abstand.
    START = 65

    for t in ticker:
        try:
            d = roh[t].dropna(subset=["Open", "High", "Low", "Close", "Volume"])
        except Exception:
            continue
        if len(d) <= START:
            continue
        o, h, l, c, v = (d["Open"].values, d["High"].values, d["Low"].values,
                         d["Close"].values, d["Volume"].values)
        handelstage += len(d) - START
        datum = d.index

        for i in range(START, len(d)):
            prev = c[i - 1]
            if prev <= 0:
                continue
            gap = o[i] / prev - 1
            if gap < GAP_MIN:
                continue
            gap_gesamt += 1
            if l[i] <= prev:
                continue                      # Luecke nicht verteidigt
            verteidigt += 1

            spanne_tag = h[i] - l[i]
            schluss_oben = (spanne_tag > 0
                            and (c[i] - l[i]) / spanne_tag >= SCHLUSS_POS)
            o10 = v[i - 10:i].mean()
            o50 = v[i - 50:i].mean()
            r10 = v[i] / o10 if o10 > 0 else 0
            r50 = v[i] / o50 if o50 > 0 else 0

            for name, pruef in varianten:
                if not pruef(h, l, c, i, gap):
                    continue
                z = zaehler[name]
                z["basis"] += 1
                if not schluss_oben:
                    continue
                z["schluss"] += 1
                if r10 >= 5.0:
                    z["o10_5"] += 1
                if r50 >= 5.0:
                    z["o50_5"] += 1
                if r50 >= 4.25:
                    z["o50_425"] += 1
                    z["treffer"].append(
                        f"{str(datum[i].date())} {t:6s} "
                        f"Luecke {gap*100:5.1f} %, {r10:5.2f}x O10, "
                        f"{r50:5.2f}x O50")

    print(f"Untersucht: rund {handelstage:,} Aktien-Tage.")
    print(f"Luecken ab 7 %: {gap_gesamt}, davon verteidigt: {verteidigt}\n")
    print("Je Variante: wie viele ueberstehen die Basis, wie viele davon")
    print("schliessen oben, und wie viele nehmen die Volumenhuerde.\n")
    kopf = (f"{'Variante':36s} {'Basis':>6s} {'Schluss':>8s} "
            f"{'5xO10':>6s} {'5xO50':>6s} {'4,25xO50':>9s}")
    print(kopf)
    print("-" * len(kopf))
    for name, _ in varianten:
        z = zaehler[name]
        print(f"{name:36s} {z['basis']:6d} {z['schluss']:8d} "
              f"{z['o10_5']:6d} {z['o50_5']:6d} {z['o50_425']:9d}")

    print("\nDie Signale je Variante (Massstab 4,25 gegen O50):")
    for name, _ in varianten:
        z = zaehler[name]
        if z["treffer"]:
            print(f"  {name}:")
            for zeile in z["treffer"]:
                print(f"      {zeile}")


if __name__ == "__main__":
    main()
