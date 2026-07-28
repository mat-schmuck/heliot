#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STIMMT DAS TAGESVOLUMEN AUS DEM STROM?
=======================================
Bevor die Volumenbestaetigung auf Yahoos Live-Strom umgestellt wird,
muss die Zahl geprueft sein. Die Volumenformel entscheidet, ob ein
Ausbruch gemeldet wird — sie darf nicht auf einer ungepruefte Quelle
stehen (Mathias' Auflage sinngemaess: erst messen, dann bauen).

Verglichen wird fuer DENSELBEN Augenblick:
  * day_volume aus dem Strom
  * Volume der heutigen Tageskerze aus dem gewohnten Abruf

Erwartung: Beides sind aufgelaufene Tagesumsaetze, sie sollten eng
beieinanderliegen. Weicht der Strom systematisch ab, oder haengt er
hinterher, muss die Volumenbestaetigung bei der Tageskerze bleiben —
dann liefert der Strom nur den Kurs.

Aufruf:  python volumenprobe.py [Sekunden] [Anzahl Aktien]
"""

import sys
import time

XLSX = "kaufpunkte_aktuell.xlsx"


def main():
    dauer = int(sys.argv[1]) if len(sys.argv) > 1 else 90
    anzahl = int(sys.argv[2]) if len(sys.argv) > 2 else 60

    import pandas as pd
    import yfinance as yf
    from kurs_cache import KursCache
    from yahoo_ws import YahooWebSocket

    df = pd.read_excel(XLSX, sheet_name="Kaufpunkte")
    ticker = sorted({str(t).strip().upper() for t in df["Ticker"]})[:anzahl]
    print(f"{len(ticker)} Aktien, {dauer} Sekunden Strom.\n")

    cache = KursCache()
    ws = YahooWebSocket(cache, leise=True)
    if not ws.start(ticker):
        sys.exit("Strom nicht verfügbar.")
    time.sleep(dauer)

    # Tageskerze GENAU JETZT holen, waehrend der Strom noch laeuft.
    roh = yf.download(" ".join(ticker), period="5d", interval="1d",
                      group_by="ticker", progress=False, auto_adjust=False,
                      threads=True)
    stand = time.time()
    ws.stop()

    zeilen = []
    for t in ticker:
        wert = cache._store.get(t)
        if wert is None or wert.volumen <= 0:
            zeilen.append((t, None, None, "kein Strom-Volumen"))
            continue
        try:
            teil = roh[t].dropna(subset=["Volume"])
            kerze = float(teil["Volume"].iloc[-1])
        except Exception:
            zeilen.append((t, wert.volumen, None, "keine Tageskerze"))
            continue
        if kerze <= 0:
            zeilen.append((t, wert.volumen, kerze, "Kerze leer"))
            continue
        abweichung = (wert.volumen / kerze - 1) * 100
        zeilen.append((t, wert.volumen, kerze, abweichung))

    print("--- VERGLEICH (Strom gegen Tageskerze) ---")
    gute = [z for z in zeilen if isinstance(z[3], float)]
    for t, strom, kerze, abw in zeilen[:25]:
        if isinstance(abw, float):
            print(f"  {t:6s} Strom {strom:12,.0f} | Kerze {kerze:12,.0f} | "
                  f"{abw:+6.2f} %")
        else:
            print(f"  {t:6s} {abw}")

    if not gute:
        print("\nKein einziger Vergleich moeglich — Messung nicht verwertbar.")
        return

    abw = sorted(z[3] for z in gute)
    mitte = abw[len(abw) // 2]
    schlimmste = max(abw, key=abs)
    innerhalb1 = sum(1 for a in abw if abs(a) <= 1)
    innerhalb5 = sum(1 for a in abw if abs(a) <= 5)

    print(f"\n--- ERGEBNIS ({len(gute)} von {len(ticker)} vergleichbar) ---")
    print(f"Mittlere Abweichung: {mitte:+.2f} %")
    print(f"Innerhalb 1 Prozent: {innerhalb1} von {len(gute)}")
    print(f"Innerhalb 5 Prozent: {innerhalb5} von {len(gute)}")
    print(f"Groesste Abweichung: {schlimmste:+.2f} %")

    print("\n--- URTEIL ---")
    if innerhalb5 >= len(gute) * 0.9 and abs(mitte) <= 2:
        print("Die beiden Quellen stimmen ueberein. Das Tagesvolumen aus dem "
              "Strom ist als Grundlage der Volumenbestaetigung brauchbar — "
              "und es ist AKTUELLER als die Tageskerze, die nur beim "
              "regelmaessigen Abruf nachgezogen wird.")
    elif mitte < -5:
        print(f"Der Strom hinkt systematisch nach ({mitte:+.1f} %). Die "
              f"Volumenbestaetigung muss bei der Tageskerze bleiben; der "
              f"Strom liefert dann nur den Kurs.")
    else:
        print(f"Die Quellen weichen zu stark voneinander ab (Mitte "
              f"{mitte:+.1f} %, schlimmster Fall {schlimmste:+.1f} %). "
              f"Volumenbestaetigung bleibt bei der Tageskerze.")


if __name__ == "__main__":
    main()
