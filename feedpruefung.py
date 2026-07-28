#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DECKT DER GRATIS-STROM ALLE AKTIEN AB?
======================================
Mathias' Verdacht vom 28.07.2026: "Das klingt nach 'bei Ueberlastung kriegen
die Gratiskonten nix bzw. haben Nachrang'."

Anlass ist eine Ungereimtheit aus zwei Messungen: Vodafone (VOD) setzt im
Schnitt 4,68 Millionen Stueck am Tag um und lieferte trotzdem BEIDE Male
null Ticks. Bei dem Umsatz sind null Geschaefte in drei Minuten rechnerisch
unmoeglich — da fehlt etwas, und es liegt nicht an der Aktie.

Finnhubs Regelwerk gibt fuer den Verdacht nichts her (nachgelesen am
28.07.2026): Der Gratis-Zugang unterscheidet sich laut Preisliste NUR in der
Symbolzahl (50 statt unbegrenzt) und im REST-Takt (60 Abrufe/Minute). Kein
Wort von Nachrang, Drosselung oder Teilabdeckung. Bleibt also die Messung.

Drei Quellen fuer DASSELBE Zeitfenster nebeneinander:
  1. Finnhubs eigener Kursabruf (/quote, gratis) — HAT Finnhub die Aktie?
  2. Der WebSocket — SCHICKT Finnhub sie auch?
  3. Yahoos Minutenumsatz — wurde die Aktie ueberhaupt gehandelt?

Daraus folgt das Urteil je Aktie:
  - Ticks da                         -> Strom deckt sie ab
  - keine Ticks, aber Yahoo-Umsatz   -> LUECKE im Strom (der gesuchte Fall)
  - keine Ticks, kein Yahoo-Umsatz   -> die Aktie wurde wirklich nicht gehandelt
Steht dazu ein frischer /quote-Preis, hat Finnhub die Daten sehr wohl und
haelt sie nur aus dem Gratis-Strom heraus.

Der Schluessel kommt aus der Umgebung und wird nie ausgegeben.
Aufruf:  python feedpruefung.py [Sekunden]
"""

import json
import os
import sys
import time
from collections import Counter

import pandas as pd
import requests

try:
    import websocket
except ImportError:
    sys.exit("Bitte installieren: pip install websocket-client")

XLSX = "kaufpunkte_aktuell.xlsx"
GRENZE = 50                      # Symbolgrenze des Gratis-Zugangs
KONTROLLE = ["AAPL", "MSFT", "NVDA"]
NACHLAUF = 90                    # Yahoos Minutenkerzen brauchen Vorsprung


def kandidaten_lesen():
    """Die Ticker mit echtem Muster-Kaufpunkt aus der laufenden Liste."""
    df = pd.read_excel(XLSX, sheet_name="Kaufpunkte")
    ticker = set()
    for _, row in df.iterrows():
        t = str(row["Ticker"]).strip().upper()
        for i in (1, 2, 3):
            strat = str(row.get(f"KP{i} Strategie", "") or "").strip()
            if strat and not strat.startswith("Fallback"):
                ticker.add(t)
    return sorted(ticker)


def main():
    dauer = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    schluessel = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not schluessel:
        sys.exit("Kein FINNHUB_API_KEY gesetzt.")

    import yfinance as yf

    ticker = kandidaten_lesen()
    print(f"{len(ticker)} Aktien mit Muster-Kaufpunkt in der Liste.")

    # Nach UMSATZ auswaehlen, nicht nach Naehe zum Kaufpunkt: Gesucht sind
    # die Faelle, bei denen Schweigen unerklaerlich waere.
    roh = yf.download(" ".join(ticker), period="1mo", interval="1d",
                      group_by="ticker", progress=False, auto_adjust=False,
                      threads=True)
    umsatz = {}
    for t in ticker:
        try:
            d = roh[t].dropna(subset=["Close", "Volume"])
            if not d.empty:
                umsatz[t] = float(d["Volume"].iloc[:-1].tail(10).mean())
        except Exception:
            continue

    gross = sorted(umsatz, key=umsatz.get, reverse=True)[:20]
    # Vodafone ist der Anlassfall — der muss mit, auch wenn er knapp
    # ausserhalb der zwanzig Groessten landet.
    for pflicht in ("VOD",):
        if pflicht in umsatz and pflicht not in gross:
            gross.append(pflicht)
    messliste = gross + [k for k in KONTROLLE if k not in gross]
    if len(messliste) > GRENZE:
        messliste = messliste[:GRENZE]
    print(f"Gemessen werden {len(messliste)} Werte ueber {dauer} Sekunden: "
          f"die umsatzstaerksten eigenen Kandidaten plus die Kontrollgruppe "
          f"{', '.join(KONTROLLE)}.\n")

    # --- 1. Hat Finnhub die Aktie ueberhaupt? (gratis, 60 Abrufe/Minute) ---
    print("--- SCHRITT 1: Finnhubs eigener Kursabruf ---")
    quote = {}
    for t in messliste:
        try:
            r = requests.get("https://finnhub.io/api/v1/quote",
                             params={"symbol": t, "token": schluessel},
                             timeout=15)
            if r.status_code != 200:
                quote[t] = (None, None, f"HTTP {r.status_code}")
            else:
                d = r.json()
                quote[t] = (d.get("c"), d.get("t"), "")
        except Exception as e:
            quote[t] = (None, None, type(e).__name__)
        time.sleep(1.1)          # bleibt klar unter 60 Abrufen je Minute
    jetzt = time.time()
    for t in messliste:
        preis, stempel, fehler = quote[t]
        if fehler:
            print(f"  {t:6s} FEHLER {fehler}")
        elif not stempel:
            print(f"  {t:6s} kein Zeitstempel")
        else:
            alter = (jetzt - stempel) / 60
            print(f"  {t:6s} {preis:9.2f} USD | Stand vor {alter:6.1f} Minuten")

    # --- 2. Schickt der Strom sie auch? ---
    print(f"\n--- SCHRITT 2: WebSocket, {dauer} Sekunden ---")
    start = time.time()
    try:
        ws = websocket.create_connection(
            "wss://ws.finnhub.io?token=" + schluessel, timeout=15)
    except Exception as e:
        sys.exit(f"Verbindung fehlgeschlagen ({type(e).__name__}).")
    for t in messliste:
        ws.send(json.dumps({"type": "subscribe", "symbol": t}))
        time.sleep(0.05)

    ticks = Counter()
    stueck = Counter()
    ws.settimeout(5)
    ende = time.time() + dauer
    while time.time() < ende:
        try:
            roh_nachricht = ws.recv()
        except websocket.WebSocketTimeoutException:
            continue
        except Exception:
            break
        try:
            nachricht = json.loads(roh_nachricht)
        except Exception:
            continue
        if nachricht.get("type") == "trade":
            for handel in nachricht.get("data", []):
                s = handel.get("s")
                if s:
                    ticks[s] += 1
                    stueck[s] += float(handel.get("v") or 0)
    schluss = time.time()
    try:
        ws.close()
    except Exception:
        pass
    print(f"Fenster gemessen: {(schluss - start) / 60:.1f} Minuten.")

    # --- 3. Wurde die Aktie im selben Fenster ueberhaupt gehandelt? ---
    print(f"\n--- SCHRITT 3: Yahoos Minutenumsatz (nach {NACHLAUF} s Nachlauf) ---")
    time.sleep(NACHLAUF)
    von = pd.Timestamp(start, unit="s", tz="UTC")
    bis = pd.Timestamp(schluss, unit="s", tz="UTC")
    minuten = yf.download(" ".join(messliste), period="1d", interval="1m",
                          group_by="ticker", progress=False,
                          auto_adjust=False, threads=True)
    yahoo = {}
    for t in messliste:
        try:
            d = minuten[t].dropna(subset=["Volume"])
            d = d[(d.index >= von) & (d.index <= bis)]
            yahoo[t] = (float(d["Volume"].sum()), len(d))
        except Exception:
            yahoo[t] = (None, 0)
    fehlend = [t for t in messliste if yahoo[t][1] == 0]
    if fehlend:
        print(f"  Ohne Yahoo-Minutenkerzen im Fenster: {', '.join(fehlend)}")

    # --- Urteil ---
    minutenzahl = (schluss - start) / 60
    print("\n--- ERGEBNIS ---")
    zeilen = []
    for t in messliste:
        pro_min = ticks[t] / minutenzahl
        y_vol, y_kerzen = yahoo[t]
        zeilen.append((pro_min, t, y_vol, y_kerzen))
    zeilen.sort(reverse=True)

    luecken = []
    for pro_min, t, y_vol, y_kerzen in zeilen:
        marke = " *** KONTROLLE ***" if t in KONTROLLE and t not in gross else ""
        if pro_min > 0:
            urteil = "Strom deckt sie ab"
        elif y_kerzen == 0:
            urteil = "kein Vergleich moeglich (keine Yahoo-Daten)"
        elif y_vol and y_vol > 0:
            urteil = f"LUECKE — Yahoo zaehlt {y_vol:,.0f} Stueck, Finnhub null"
            luecken.append((t, y_vol))
        else:
            urteil = "wirklich nicht gehandelt"
        y_text = f"{y_vol:12,.0f}" if y_vol is not None else "        n/a"
        print(f"  {t:6s} {pro_min:7.1f} Ticks/Min | Ø-Tagesumsatz "
              f"{umsatz.get(t, 0):12,.0f} | Yahoo im Fenster {y_text} | "
              f"{urteil}{marke}")

    print("\n--- DEUTUNG ---")
    if luecken:
        print(f"{len(luecken)} Aktien wurden nachweislich gehandelt, kamen im "
              f"Gratis-Strom aber NICHT an:")
        for t, v in luecken:
            preis, stempel, fehler = quote[t]
            if stempel:
                alter = (time.time() - stempel) / 60
                zusatz = (f"Finnhubs Kursabruf kennt sie (Stand vor "
                          f"{alter:.0f} Minuten) — die Daten sind also da, "
                          f"nur nicht im Strom.")
            else:
                zusatz = "Finnhubs Kursabruf liefert fuer sie ebenfalls nichts."
            print(f"  {t}: {v:,.0f} Stueck im Fenster. {zusatz}")
        print("\nDas ist der Beleg fuer eine Teilabdeckung: Der Gratis-Strom "
              "traegt nicht alle Handelsplaetze. Fuer die betroffenen Aktien "
              "muss der Waechter bei Yahoo bleiben.")
    else:
        print("Keine Luecke gefunden: Jede Aktie, die im Fenster gehandelt "
              "wurde, kam auch im Strom an. Wer schwieg, wurde wirklich nicht "
              "gehandelt — dann ist es reine Liquiditaet und kein Tarifnachteil.")


if __name__ == "__main__":
    main()
