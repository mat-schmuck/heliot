#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WELCHE EURER AKTIEN SIND LIQUIDE GENUG FUER ECHTZEIT?
=====================================================
Mathias' Frage vom 28.07.2026: Welche Werte sind gross genug, um sich
eine Echtzeit-Ueberwachung ueberhaupt zu lohnen?

Die Frage ist berechtigt, weil die erste Verdrahtung genau das zeigte:
Von 50 abonnierten Werten lieferten nur 7 bis 8 einen frischen Tick. Der
WebSocket lief einwandfrei — die Aktien wurden schlicht nicht gehandelt.
Ein Nebenwert bringt in zwei Minuten vielleicht zwei Ticks, Apple 890.

Statt zu schaetzen wird gemessen: Die Kandidaten aus der laufenden
Kaufpunkt-Liste werden abonniert und ihre Ticks gezaehlt. Danebengestellt
wird das durchschnittliche Tagesvolumen — daraus laesst sich eine
Faustregel ableiten, ab welcher Groesse sich Echtzeit lohnt.

Der Schluessel kommt aus der Umgebung und wird nie ausgegeben.
Aufruf:  python liquiditaet.py [Sekunden]
"""

import json
import os
import sys
import time
from collections import Counter

import pandas as pd

try:
    import websocket
except ImportError:
    sys.exit("Bitte installieren: pip install websocket-client")

XLSX = "kaufpunkte_aktuell.xlsx"
GRENZE = 50          # so viele traegt der Gratis-Zugang (nachgemessen)


def main():
    dauer = int(sys.argv[1]) if len(sys.argv) > 1 else 180
    schluessel = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not schluessel:
        sys.exit("Kein FINNHUB_API_KEY gesetzt.")

    df = pd.read_excel(XLSX, sheet_name="Kaufpunkte")
    kandidaten = {}
    for _, row in df.iterrows():
        t = str(row["Ticker"]).strip().upper()
        for i in (1, 2, 3):
            strat = str(row.get(f"KP{i} Strategie", "") or "").strip()
            preis = row.get(f"KP{i} Preis")
            if strat and not strat.startswith("Fallback") and pd.notna(preis):
                kandidaten.setdefault(t, []).append(float(preis))
    print(f"{len(kandidaten)} Aktien mit Muster-Kaufpunkt in der Liste.")

    import yfinance as yf
    roh = yf.download(" ".join(sorted(kandidaten)), period="1mo", interval="1d",
                      group_by="ticker", progress=False, auto_adjust=False,
                      threads=True)

    bewertet = []
    for t, kps in kandidaten.items():
        try:
            d = roh[t].dropna(subset=["Close", "Volume"])
            if d.empty:
                continue
            kurs = float(d["Close"].iloc[-1])
            vol_schnitt = float(d["Volume"].iloc[:-1].tail(10).mean())
            abstand = min(max(0.0, (kp - kurs) / kp) for kp in kps)
            bewertet.append((abstand, t, kurs, vol_schnitt))
        except Exception:
            continue
    bewertet.sort()

    # KONTROLLGRUPPE (28.07.2026): Der erste Durchgang ergab, dass 46 von
    # 50 Werten fast keine Ticks lieferten — darunter Vodafone und
    # Ovintiv mit ueber vier Millionen Stueck Tagesumsatz. Bei dem Umsatz
    # sind null Geschaefte in drei Minuten rechnerisch unmoeglich. Also
    # laufen jetzt drei Schwergewichte MIT: Bleiben auch die stumm, liegt
    # es an der Leitung oder am Tarif, nicht an den Aktien. Nur wenn die
    # Kontrolle sprudelt und die eigenen Werte schweigen, ist das Ergebnis
    # echte Liquiditaet.
    KONTROLLE = ["AAPL", "MSFT", "NVDA"]
    messliste = bewertet[:GRENZE - len(KONTROLLE)]
    for k in KONTROLLE:
        messliste.append((-1.0, k, 0.0, 0.0))     # Abstand -1 = Kontrolle
    print(f"Gemessen werden {len(messliste)} Werte, {dauer} Sekunden lang: "
          f"{len(messliste) - len(KONTROLLE)} eigene Kandidaten plus die "
          f"Kontrollgruppe {', '.join(KONTROLLE)}.\n")

    try:
        ws = websocket.create_connection("wss://ws.finnhub.io?token="
                                         + schluessel, timeout=15)
    except Exception as e:
        sys.exit(f"Verbindung fehlgeschlagen ({type(e).__name__}).")
    for _, t, _, _ in messliste:
        ws.send(json.dumps({"type": "subscribe", "symbol": t}))
        time.sleep(0.05)

    ticks = Counter()
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
                if handel.get("s"):
                    ticks[handel["s"]] += 1
    try:
        ws.close()
    except Exception:
        pass

    minuten = dauer / 60
    print("--- ERGEBNIS (nach Ticks je Minute sortiert) ---")
    zeilen = []
    for abstand, t, kurs, vol in messliste:
        pro_min = ticks[t] / minuten
        zeilen.append((pro_min, t, abstand, kurs, vol))
    zeilen.sort(reverse=True)
    for pro_min, t, abstand, kurs, vol in zeilen:
        if abstand < 0:
            print(f"  {t:6s} {pro_min:7.1f} Ticks/Min | *** KONTROLLE ***")
            continue
        urteil = ("ECHTZEIT lohnt" if pro_min >= 10 else
                  "grenzwertig" if pro_min >= 2 else "zu ruhig")
        print(f"  {t:6s} {pro_min:7.1f} Ticks/Min | Abstand {abstand*100:4.1f} % "
              f"| Ø-Volumen {vol:12,.0f} | {urteil}")

    kontrolle = [z for z in zeilen if z[2] < 0]
    eigene = [z for z in zeilen if z[2] >= 0]
    k_summe = sum(z[0] for z in kontrolle)
    print(f"\nKontrollgruppe zusammen: {k_summe:.1f} Ticks/Min")
    if k_summe < 20:
        print("  ⚠ ACHTUNG: Auch die Schwergewichte liefern kaum etwas. Dann "
              "liegt es NICHT an euren Aktien, sondern an der Leitung oder am "
              "Tarif — das Ergebnis unten ist dann NICHT verwertbar.")
    else:
        print("  ✓ Die Kontrolle sprudelt — die Leitung ist in Ordnung, das "
              "Ergebnis unten misst echte Liquidität.")

    zeilen = eigene
    lohnt = [z for z in zeilen if z[0] >= 10]
    grenz = [z for z in zeilen if 2 <= z[0] < 10]
    ruhig = [z for z in zeilen if z[0] < 2]
    print(f"\n--- DEUTUNG ---")
    print(f"Echtzeit lohnt (ab 10 Ticks/Min): {len(lohnt)} Aktien")
    print(f"Grenzwertig (2 bis 10):           {len(grenz)}")
    print(f"Zu ruhig (unter 2):               {len(ruhig)}")
    if lohnt and ruhig:
        v_lohnt = sorted(z[4] for z in lohnt)
        v_ruhig = sorted(z[4] for z in ruhig)
        print(f"\nØ-Tagesvolumen der lebhaften: Mitte "
              f"{v_lohnt[len(v_lohnt)//2]:,.0f}, kleinste {v_lohnt[0]:,.0f}")
        print(f"Ø-Tagesvolumen der ruhigen:   Mitte "
              f"{v_ruhig[len(v_ruhig)//2]:,.0f}, groesste {v_ruhig[-1]:,.0f}")
        print("\nFaustregel: Ab welchem Tagesvolumen sich Echtzeit lohnt, "
              "laesst sich an der Grenze zwischen diesen beiden Gruppen "
              "ablesen.")


if __name__ == "__main__":
    main()
