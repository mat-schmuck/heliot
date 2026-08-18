#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KERZENVERGLEICH — hat Twelve Data die Tageskerzen, die Yahoo aushöhlt?
=======================================================================
Mathias' Auftrag vom 18.08.2026: "Wir haben doch Fallback-Ebenen
eingebaut — kannst Du das jetzt manuell bitte überprüfen gegen
Twelvedata?"

ANLASS, gemessen am selben Vormittag: Yahoo lieferte für viele
mittelgrosse Aktien die Montagszeile MIT Datum, aber ALLE Werte leer —
um 00:04 waren die Werte noch da (die Kaufpunkt-Mappe traegt die
Montagsschluesse auf den Cent), vormittags waren sie rueckwirkend weg.
Die Frage hier: Haette die Rueckfallebene den Tag gehabt?

Laeuft in der Cloud, weil TWELVE_DATA_API_KEY dort als Secret liegt.
Fuenf Kuerzel, bewusst gemischt: drei betroffene von der Liste (KEYS,
UMAC, LPG), eine betroffene AUSSERHALB der Listen (AXTI — wird von uns
nie abgefragt; ist sie trotzdem hohl, liegt es an Yahoo, nicht an
unserer Abfragelast) und SPY als gesunde Kontrolle.

Aufruf: python kerzenvergleich.py
"""

import json
import os
import sys
import time
import urllib.request

KUERZEL = ["KEYS", "UMAC", "LPG", "AXTI", "SPY"]
# Twelve-Data-Gratis: 8 Abrufe je Minute. Fuenf Abrufe mit Pause bleiben
# klar darunter; die Pause NICHT entfernen.
TD_PAUSE_SEK = 8.5


def yahoo_kerzen(t):
    import warnings
    warnings.filterwarnings("ignore")
    import yfinance as yf
    h = yf.download(t, period="7d", interval="1d", progress=False,
                    auto_adjust=False)
    raus = []
    for i, r in h.iterrows():
        c = r["Close"] if "Close" in r else r.get(("Close", t))
        leer = c != c                    # NaN erkennt man an NaN != NaN
        raus.append((f"{i:%a %d.%m.}", "LEER" if leer else f"{float(c):.2f}"))
    return raus


def td_kerzen(t, schluessel):
    url = (f"https://api.twelvedata.com/time_series?symbol={t}"
           f"&interval=1day&outputsize=5&apikey={schluessel}")
    with urllib.request.urlopen(url, timeout=30) as a:
        d = json.loads(a.read().decode("utf-8"))
    if d.get("status") != "ok":
        return None, d.get("message", "unbekannter Fehler")[:120]
    raus = []
    for w in reversed(d.get("values", [])):
        raus.append((w["datetime"], f"{float(w['close']):.2f}",
                     w.get("volume", "?")))
    return raus, None


def main() -> int:
    schluessel = (os.environ.get("TWELVE_DATA_API_KEY") or "").strip()
    if not schluessel:
        print("TWELVE_DATA_API_KEY fehlt — Abbruch.")
        return 1
    print(f"Schlüssel vorhanden ({len(schluessel)} Zeichen, Wert wird nie "
          f"ausgegeben).\n")
    for t in KUERZEL:
        print(f"=== {t} ===")
        try:
            y = yahoo_kerzen(t)
            print("  Yahoo      : " + " | ".join(f"{d} {c}" for d, c in y[-4:]))
        except Exception as e:
            print(f"  Yahoo      : Fehler {type(e).__name__}")
        td, fehler = td_kerzen(t, schluessel)
        if fehler:
            print(f"  Twelve Data: FEHLER {fehler}")
        else:
            print("  Twelve Data: " + " | ".join(
                f"{d} {c} (Vol {v})" for d, c, v in td[-4:]))
            hat_montag = any(d.startswith("2026-08-17") for d, _, _ in td)
            print(f"  Montag 17.08. bei Twelve Data: "
                  f"{'JA, mit Werten' if hat_montag else 'FEHLT'}")
        time.sleep(TD_PAUSE_SEK)
    return 0


if __name__ == "__main__":
    sys.exit(main())
