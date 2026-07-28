#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MESSUNG: Was leistet der Finnhub-WebSocket im Gratis-Tarif wirklich?
====================================================================
Bevor die dreistufige Live-Staffelung darauf gebaut wird, muss belegt
sein, was der Zugang hergibt. Gemessen wird dreierlei:

  1. Kommen ueberhaupt Handelsdaten an? (Die Doku sagt ja — der
     Trades-WebSocket traegt keinen Premium-Vermerk, anders als die
     Tageskerzen. Behauptung ist aber kein Beleg.)
  2. Wie viele Ticks pro Minute? (Reicht das fuer eine Live-Stufe?)
  3. WIE VIELE SYMBOLE GLEICHZEITIG? Gerhards Entwurf rechnet mit rund
     50 (30 schnelle Liste + 20 oberer Vorraum). Diese Zahl steht
     NIRGENDS in der Doku — genau deshalb wird sie hier gemessen.

Verfahren fuer Punkt 3: Es werden bewusst MEHR Symbole abonniert, als
erlaubt sein sollten, und zwar ausschliesslich sehr liquide Werte, die
waehrend des Handels im Sekundentakt Umsaetze haben. Liefert ein
solcher Wert in mehreren Minuten keinen einzigen Tick, wurde sein Abo
stillschweigend verworfen — die Zahl der versorgten Symbole ist dann
die tatsaechliche Obergrenze.

Der Schluessel kommt aus der Umgebung (FINNHUB_API_KEY) und wird NIE
ausgegeben — auch nicht in Fehlermeldungen.

Aufruf:  python finnhub_messung.py [Sekunden] [Symbolzahl]
"""

import json
import os
import sys
import time
from collections import Counter

try:
    import websocket           # Paket: websocket-client
except ImportError:
    sys.exit("Bitte installieren: pip install websocket-client")

# Sehr liquide US-Werte: handeln waehrend der Boersenzeit praktisch
# ununterbrochen. Nur so ist "kein Tick" ein Beleg fuer ein verworfenes
# Abo und nicht bloss fuer einen ruhigen Wert.
SYMBOLE = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO",
    "JPM", "V", "UNH", "XOM", "LLY", "JNJ", "WMT", "MA", "PG", "HD",
    "CVX", "ABBV", "MRK", "COST", "PEP", "KO", "ADBE", "CRM", "BAC",
    "NFLX", "AMD", "TMO", "CSCO", "ACN", "LIN", "MCD", "ABT", "DHR",
    "WFC", "TXN", "VZ", "DIS", "INTC", "PM", "CAT", "NEE", "IBM", "GE",
    "QCOM", "NOW", "ORCL", "AMGN", "SPY", "QQQ", "IWM", "DIA", "XLK",
    "XLF", "XLE", "XLV", "XLI", "GLD", "TLT", "SLV", "EEM", "HYG", "F",
]


def main():
    dauer = int(sys.argv[1]) if len(sys.argv) > 1 else 150
    anzahl = int(sys.argv[2]) if len(sys.argv) > 2 else len(SYMBOLE)
    symbole = SYMBOLE[:anzahl]

    schluessel = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not schluessel:
        sys.exit("Kein FINNHUB_API_KEY gesetzt.")

    print(f"=== Finnhub-WebSocket messen ===")
    print(f"Abonniert werden {len(symbole)} sehr liquide Symbole, "
          f"Messdauer {dauer} Sekunden.\n")

    try:
        ws = websocket.create_connection("wss://ws.finnhub.io?token="
                                         + schluessel, timeout=15)
    except Exception as e:
        # Schluessel koennte in der URL der Fehlermeldung stecken — deshalb
        # nur den Ausnahmetyp zeigen, nie den Text.
        sys.exit(f"Verbindung fehlgeschlagen ({type(e).__name__}).")
    print("✓ Verbindung steht.")

    for s in symbole:
        ws.send(json.dumps({"type": "subscribe", "symbol": s}))
        time.sleep(0.05)
    print(f"✓ {len(symbole)} Abos verschickt.\n")

    ticks = Counter()
    volumen = Counter()
    letzter_preis = {}
    nachrichten = 0
    fehler = []
    ws.settimeout(5)
    ende = time.time() + dauer
    while time.time() < ende:
        try:
            roh = ws.recv()
        except websocket.WebSocketTimeoutException:
            continue
        except Exception as e:
            fehler.append(type(e).__name__)
            break
        nachrichten += 1
        try:
            nachricht = json.loads(roh)
        except Exception:
            continue
        art = nachricht.get("type")
        if art == "trade":
            for handel in nachricht.get("data", []):
                s = handel.get("s")
                if s:
                    ticks[s] += 1
                    volumen[s] += handel.get("v", 0) or 0
                    letzter_preis[s] = handel.get("p")
        elif art == "error":
            fehler.append(str(nachricht.get("msg"))[:120])
        elif art and art != "ping":
            fehler.append(f"unbekannte Art: {art}")

    try:
        ws.close()
    except Exception:
        pass

    versorgt = [s for s in symbole if ticks[s] > 0]
    stumm = [s for s in symbole if ticks[s] == 0]
    gesamt = sum(ticks.values())

    print("--- ERGEBNIS ---")
    print(f"Nachrichten empfangen: {nachrichten}")
    print(f"Einzelne Handelsticks: {gesamt}"
          + (f"  ({gesamt / dauer * 60:.0f} pro Minute)" if dauer else ""))
    print(f"Symbole MIT Ticks:     {len(versorgt)} von {len(symbole)}")
    print(f"Symbole OHNE Ticks:    {len(stumm)}")
    if stumm:
        print("  stumm geblieben: " + ", ".join(stumm))
    if fehler:
        print(f"Meldungen des Servers: {sorted(set(fehler))[:5]}")

    print("\nDie zehn aktivsten Symbole:")
    for s, n in ticks.most_common(10):
        print(f"  {s:6s} {n:6d} Ticks, letzter Kurs {letzter_preis.get(s)}")

    print("\n--- DEUTUNG ---")
    if not versorgt:
        print("Es kam KEIN einziger Handelstick. Entweder ist die Börse zu, "
              "oder der Gratis-Zugang liefert keine Trades.")
    elif len(versorgt) == len(symbole):
        print(f"ALLE {len(symbole)} Symbole wurden versorgt — die Obergrenze "
              f"liegt also bei mindestens {len(symbole)}.")
    else:
        print(f"Versorgt wurden {len(versorgt)} Symbole, {len(stumm)} blieben "
              f"stumm. Da ausschließlich sehr liquide Werte abonniert wurden, "
              f"ist das die tatsächliche Obergrenze des Zugangs.")
        print(f"Gerhards Entwurf rechnet mit ~50 (30 schnelle Liste + 20 "
              f"oberer Vorraum) — das ist damit "
              + ("gedeckt." if len(versorgt) >= 50 else
                 "NICHT gedeckt und muss angepasst werden."))


if __name__ == "__main__":
    main()
