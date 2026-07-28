#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BRAUCHEN WIR DIE SECHS MINUTEN WIRKLICH?
=========================================
Mathias' Frage vom 28.07.2026: "Schaue, ob wir wirklich die 6 Min
Mindestabstand brauchen — wenn ja, erklaers mir nocheinmal genauer,
sonst miss bitte nach, bevor wir uns selbst limitieren."

Die sechs Minuten stammen NICHT von GitHub. GitHub begrenzt nur die
Gesamtlaufzeit eines Auftrags auf sechs Stunden (daher die zweiteilige
Wache); wie schnell die Schleife innerhalb eines Laufs dreht, ist ihm
gleich. Die sechs Minuten haben wir uns selbst gesetzt, aus Sorge vor
einer Drosselung durch Yahoo: Jede Runde laedt acht Monate Tagesdaten
fuer alle 265 Aktien in einem Rutsch.

Gemessen wird deshalb genau das — und zwar VORSICHTIG, mit immer
kuerzerem Abstand, und beim ersten Anzeichen einer Drosselung wird
abgebrochen. Der Grund fuer die Vorsicht: An Yahoo haengt der laufende
Waechter. Wer hier blind draufhaelt und sich eine Sperre einfaengt,
legt die Ueberwachung lahm — die Messung darf nicht teurer werden als
die Antwort wert ist.

Aufruf:  python yahootakt.py [Runden je Stufe]
"""

import sys
import time

XLSX = "kaufpunkte_aktuell.xlsx"
STUFEN = [180, 90, 45, 20, 0]      # Pause zwischen den Abrufen, Sekunden


def hole(ticker):
    """Ein Abruf wie im Waechter: acht Monate Tagesdaten fuer ALLE."""
    import yfinance as yf
    beginn = time.time()
    try:
        roh = yf.download(" ".join(ticker), period="8mo", interval="1d",
                          group_by="ticker", progress=False,
                          auto_adjust=False, threads=True)
    except Exception as e:
        return None, time.time() - beginn, type(e).__name__
    if roh is None or roh.empty:
        return 0, time.time() - beginn, "leer"
    da = 0
    for t in ticker:
        try:
            teil = roh[t].dropna(subset=["Close", "Volume"])
            if not teil.empty:
                da += 1
        except Exception:
            pass
    return da, time.time() - beginn, ""


def main():
    runden = int(sys.argv[1]) if len(sys.argv) > 1 else 3

    import pandas as pd
    df = pd.read_excel(XLSX, sheet_name="Kaufpunkte")
    ticker = sorted({str(t).strip().upper() for t in df["Ticker"]})
    print(f"{len(ticker)} Ticker, acht Monate Tagesdaten je Abruf.\n")

    # Erst einmal ohne Zeitdruck: Wie lange dauert EIN Abruf ueberhaupt?
    # Das ist die harte Untergrenze — schneller als das geht nie.
    da, dauer, fehler = hole(ticker)
    if fehler:
        sys.exit(f"Schon der erste Abruf scheiterte ({fehler}). "
                 f"Messung abgebrochen, ohne etwas zu belasten.")
    print(f"Einzelner Abruf: {dauer:.1f} Sekunden, {da} von {len(ticker)} "
          f"Aktien geliefert.")
    print(f"Damit sind rechnerisch hoechstens {60/dauer:.1f} Abrufe je "
          f"Minute moeglich, selbst ohne jede Pause.\n")
    vollstaendig = da

    ergebnisse = []
    for pause in STUFEN:
        print(f"--- Stufe: {pause} Sekunden Pause, {runden} Abrufe ---")
        stufe_ok = True
        for i in range(runden):
            if pause:
                time.sleep(pause)
            da, dauer, fehler = hole(ticker)
            takt = dauer + pause
            if fehler:
                print(f"  Abruf {i+1}: FEHLER ({fehler}) nach {dauer:.1f} s")
                stufe_ok = False
                break
            fehlend = vollstaendig - da
            marke = "" if fehlend <= 2 else f"  ⚠ {fehlend} Aktien fehlen"
            print(f"  Abruf {i+1}: {dauer:5.1f} s, {da} Aktien, "
                  f"Takt {takt:.0f} s{marke}")
            if fehlend > 2:
                stufe_ok = False
                break
        ergebnisse.append((pause, stufe_ok))
        if not stufe_ok:
            print(f"  → Bei {pause} Sekunden Pause bricht es. Abbruch, damit "
                  f"wir uns keine Sperre einfangen.\n")
            break
        print(f"  → {pause} Sekunden Pause: sauber durchgelaufen.\n")

    print("=" * 62)
    print("ERGEBNIS")
    print("=" * 62)
    geschafft = [p for p, ok in ergebnisse if ok]
    if not geschafft:
        print("Schon die langsamste Stufe machte Probleme — die sechs "
              "Minuten sind berechtigt.")
        return
    schnellste = min(geschafft)
    print(f"Sauber gelaufen bis hinunter zu {schnellste} Sekunden Pause "
          f"zwischen den Abrufen.")
    print(f"Mit den {dauer:.0f} Sekunden Abrufdauer ergibt das einen Takt von "
          f"rund {dauer + schnellste:.0f} Sekunden statt 360.")
    if schnellste <= 45:
        print("\nDie sechs Minuten sind damit NICHT technisch begruendet, "
              "sondern reine Vorsicht. Sie liessen sich deutlich verkuerzen.")
    else:
        print("\nViel Luft ist nicht — die sechs Minuten sind grosszuegig, "
              "aber nicht absurd.")
    print("\nZur Einordnung: Mit Yahoos Live-Strom fuer Kurs UND Tagesvolumen "
          "spielt dieser Takt fuer die Alarmgeschwindigkeit ohnehin keine "
          "Rolle mehr. Der schwere Abruf liefert dann nur noch Dinge, die "
          "sich einmal am Tag aendern: Vortagesschluss, Ø50 und Flat Base.")


if __name__ == "__main__":
    main()
