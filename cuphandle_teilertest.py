#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CUP & HANDLE: WELCHER TEILER FUER DAS HANDLE-FENSTER?
======================================================
Gerhard am 05.08.2026: "Bitte gegen alle drei Faelle UND gegen den
breiteren Datenbestand messen, nicht nur gegen die drei. Wenn die Formel
nur die drei trifft und sonst Unsinn produziert, ist sie genauso
Kurvenanpassung wie eine feste 16."

Genau das macht dieses Werkzeug. Geprueft wird die Formel
    Handle-Fenster = begrenzt(Cup-Laenge / Teiler, unten, oben)
fuer mehrere Teiler, jeweils gegen:
  a) die drei von IBD bestaetigten Faelle (LPG, MEDP, DDOG)
  b) ALLE Aktien der laufenden Wochenliste

Bei (b) zaehlt nicht nur, WIE VIELE erkannt werden, sondern auch die
Punktzahl: Ein Teiler, der viele Formationen mit schwacher Punktzahl
durchlaesst, ist ein schlechteres Geschaeft als einer mit wenigen guten.

Aufruf:  python cuphandle_teilertest.py
"""

import copy
import sys
from statistics import median

import cup_handle_v2 as v2

FAELLE = (("LPG", "2026-02-24", 35.91),
          ("MEDP", "2026-07-22", 567.91),
          ("DDOG", "2026-07-31", 276.70))

TEILER = (2.0, 2.5, 3.0, 4.0)


def hole(sym, jahre=5):
    import yfinance as yf
    d = yf.download(sym, period=f"{jahre}y", interval="1d",
                    progress=False, auto_adjust=False)
    if hasattr(d.columns, "levels"):
        d.columns = d.columns.droplevel(1)
    d = d.dropna().reset_index()
    return d.rename(columns={"Date": "datetime", "Open": "open", "High": "high",
                             "Low": "low", "Close": "close", "Volume": "volume"})


def mit_teiler(teiler):
    cfg = copy.deepcopy(v2.CFG)
    cfg["handle_teiler"] = teiler
    return cfg


def main():
    import pandas as pd
    import yfinance as yf

    print("TEIL A — die drei von IBD bestaetigten Faelle\n")
    print(f"{'Teiler':>7s}  " + "  ".join(f"{s:>14s}" for s, _, _ in FAELLE))
    daten = {s: hole(s) for s, _, _ in FAELLE}
    for teiler in TEILER:
        cfg = mit_teiler(teiler)
        zellen = []
        for sym, stichtag, ibd in FAELLE:
            d = daten[sym]
            bis = d[d["datetime"] <= stichtag].reset_index(drop=True)
            t = v2.detect_cup_handle_v2(bis, cfg)
            zellen.append(f"{(t['kaufpunkt']/ibd-1)*100:+8.1f} %" if t
                          else "  nichts    ")
        print(f"{teiler:7.1f}  " + "  ".join(f"{z:>14s}" for z in zellen))

    print("\n\nTEIL B — die ganze Wochenliste\n")
    df = pd.read_excel("kaufpunkte_aktuell.xlsx", sheet_name="Kaufpunkte")
    ticker = sorted({str(t).strip().upper() for t in df["Ticker"]})
    print(f"{len(ticker)} Aktien, fuenf Jahre Tagesdaten werden geholt …")
    roh = yf.download(" ".join(ticker), period="5y", interval="1d",
                      group_by="ticker", progress=False, auto_adjust=False,
                      threads=True)

    vorbereitet = {}
    for t in ticker:
        try:
            d = roh[t].dropna(subset=["Open", "High", "Low", "Close", "Volume"])
        except Exception:
            continue
        if len(d) < 300:
            continue
        d = d.reset_index().rename(columns={
            "Date": "datetime", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume"})
        vorbereitet[t] = d
    print(f"{len(vorbereitet)} Aktien mit genug Historie.\n")

    print(f"{'Teiler':>7s} {'Treffer':>8s} {'Median-Punkte':>14s} "
          f"{'schwach (<60)':>14s} {'Median Cup':>11s} {'Median Handle':>14s}")
    for teiler in TEILER:
        cfg = mit_teiler(teiler)
        punkte, cups, fenster = [], [], []
        for t, d in vorbereitet.items():
            try:
                erg = v2.detect_cup_handle_v2(d, cfg)
            except Exception:
                continue
            if erg:
                punkte.append(erg["score"])
                import re
                m = re.search(r"(\d+) Wochen von", erg["notiz"])
                if m:
                    cup = int(m.group(1))
                    cups.append(cup)
                    fenster.append(v2.handle_fenster_wochen(cup, cfg))
        schwach = sum(1 for p in punkte if p < 60)
        print(f"{teiler:7.1f} {len(punkte):8d} "
              f"{median(punkte) if punkte else 0:14.1f} {schwach:14d} "
              f"{median(cups) if cups else 0:11.0f} "
              f"{median(fenster) if fenster else 0:14.0f}")

    print("\nLesehilfe: Mehr Treffer sind nur dann besser, wenn die Punktzahl")
    print("nicht faellt. Steigt die Zahl der schwachen Formationen stark,")
    print("kauft der lockerere Teiler die Treffer mit Qualitaet.")


if __name__ == "__main__":
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__.strip())
        sys.exit(0)
    main()
