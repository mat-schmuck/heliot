#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LIEGT ES AN DER GRENZE ODER AN DER ABDECKUNG?
==============================================
Mathias' Frage vom 28.07.2026: "Kann das Erreichen des Limits von 50
Aktien ohne Puffer nicht zu solchen Totalausfaellen wie vorher gefuehrt
haben, oder sind das 2 versch. Dinge?"

Die Frage ist gut, denn beide Messungen davor liefen mit GENAU 50
abonnierten Symbolen — also punktgenau an der harten Grenze. Wenn der
Server am Rand unsauber arbeitet, waere das eine voellig andere Ursache
als eine Luecke in der Abdeckung, und die Gegenmassnahme waere eine
andere.

Vier Abschnitte, jeder beantwortet genau eine Frage:

  A  Fuenf Symbole, weit weg von jeder Grenze. Schweigen Vodafone und
     Ovintiv AUCH hier, kann die Grenze nicht schuld sein.
  B  Genau 50 sehr liquide Werte. Liefern alle 50, ist die Grenze im
     Dauerbetrieb unbedenklich. Fallen welche aus, war der fehlende
     Puffer sehr wohl ein Problem.
  C  Der Listenwechsel AN der Grenze: 10 abmelden, 10 neue anmelden.
     Genau das macht die Staffelung staendig. Kommen die Neuen an?
  D  Bewusst darueber: 5 zusaetzlich ohne Abmeldung. Sagt der Server
     etwas, kennen wir die Obergrenze aus erster Hand.

Der Schluessel kommt aus der Umgebung und wird nie ausgegeben.
Aufruf:  python grenztest.py
"""

import json
import os
import sys
import time
from collections import Counter

try:
    import websocket
except ImportError:
    sys.exit("Bitte installieren: pip install websocket-client")

# Die Verdaechtigen aus den bisherigen Messungen.
VERDAECHTIG = ["VOD", "OVV"]
KONTROLLE = ["AAPL", "MSFT", "NVDA"]

# Sehr liquide Standardwerte. Bewusst NUR Schwergewichte: Schweigt hier
# eines, kann es nicht an der Liquiditaet liegen — dann war es die Grenze.
LIQUIDE = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO",
    "JPM", "V", "UNH", "XOM", "MA", "PG", "JNJ", "HD", "COST", "ABBV",
    "MRK", "CVX", "ADBE", "PEP", "KO", "WMT", "CRM", "BAC", "AMD",
    "NFLX", "TMO", "LIN", "ACN", "MCD", "CSCO", "ABT", "ORCL", "DHR",
    "WFC", "TXN", "VZ", "INTC", "NEE", "PM", "CMCSA", "COP", "INTU",
    "RTX", "AMGN", "HON", "UNP", "LOW",
    # ab hier die Reserve fuer den Listenwechsel in Abschnitt C
    "SPGI", "CAT", "BA", "GS", "T", "PFE", "ELV", "BLK", "DE", "AXP",
    "SBUX", "GILD", "MDT", "ADI", "PLD",
]


class Zaehler:
    """Sammelt Ticks und Serverantworten einer offenen Verbindung."""

    def __init__(self, ws):
        self.ws = ws
        self.ticks = Counter()
        self.fehler = []

    def hoere(self, sekunden):
        self.ws.settimeout(3)
        ende = time.time() + sekunden
        while time.time() < ende:
            try:
                roh = self.ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            except Exception:
                break
            try:
                n = json.loads(roh)
            except Exception:
                continue
            if n.get("type") == "trade":
                for h in n.get("data", []):
                    if h.get("s"):
                        self.ticks[h["s"]] += 1
            elif n.get("type") == "error":
                m = str(n.get("msg"))[:150]
                if m not in self.fehler:
                    self.fehler.append(m)
                    print(f"    Server meldet: {m}")

    def an(self, symbole):
        for s in symbole:
            self.ws.send(json.dumps({"type": "subscribe", "symbol": s}))
            time.sleep(0.05)

    def ab(self, symbole):
        for s in symbole:
            self.ws.send(json.dumps({"type": "unsubscribe", "symbol": s}))
            time.sleep(0.05)


def bericht(z, symbole, dauer, ueberschrift):
    minuten = dauer / 60
    still = [s for s in symbole if z.ticks[s] == 0]
    aktiv = [s for s in symbole if z.ticks[s] > 0]
    print(f"  {ueberschrift}")
    print(f"    {len(aktiv)} von {len(symbole)} lieferten Ticks.")
    for s in sorted(symbole, key=lambda x: -z.ticks[x]):
        print(f"      {s:6s} {z.ticks[s] / minuten:7.1f} Ticks/Min")
    if still:
        print(f"    STUMM: {', '.join(still)}")
    return aktiv, still


def nachpruefung(schluessel, tickers, dauer=180):
    """NUR Abschnitt A, mit frei gewaehlten Verdaechtigen.

    Gebraucht, weil der erste Durchgang am 28.07.2026 eine Frage offen
    liess: Bei 50 abonnierten Schwergewichten schwieg Lowe's als einziges.
    Das koennte an der Grenze liegen — oder schlicht daran, dass das
    Ende des Feldes duenn war (Home Depot brachte in drei Minuten ganze
    zwei Ticks). Die einzige saubere Antwort ist, denselben Wert OHNE
    Grenzennaehe zu messen. Genau dafuer ist dieser Modus da."""
    liste = [t.upper() for t in tickers] + KONTROLLE
    try:
        ws = websocket.create_connection("wss://ws.finnhub.io?token="
                                         + schluessel, timeout=15)
    except Exception as e:
        sys.exit(f"Verbindung fehlgeschlagen ({type(e).__name__}).")
    z = Zaehler(ws)
    print(f"\n=== NACHPRUEFUNG: {len(liste)} Symbole, {dauer} Sekunden ===")
    print(f"    Geprueft werden {', '.join(tickers)} — weit weg von jeder "
          f"Grenze, mit Kontrollgruppe.")
    z.an(liste)
    z.hoere(dauer)
    aktiv, still = bericht(z, liste, dauer, "Ergebnis:")
    try:
        ws.close()
    except Exception:
        pass

    if not all(k in aktiv for k in KONTROLLE):
        print("\nDie Kontrollgruppe schwieg — Leitung gestoert, nicht "
              "verwertbar.")
        return
    verdaechtig_still = [t for t in tickers if t.upper() in still]
    print("\nURTEIL")
    if verdaechtig_still:
        print(f"  {', '.join(verdaechtig_still)} schweigen auch bei nur "
              f"{len(liste)} Symbolen.")
        print("  -> Abdeckungsluecke, NICHT die Grenze. Ein Puffer haette "
              "daran nichts geaendert.")
    else:
        print(f"  {', '.join(tickers)} liefern hier Ticks, schwiegen aber bei "
              f"50 abonnierten Werten.")
        print("  -> Dann geht punktgenau an der Grenze sehr wohl etwas "
              "verloren, und der Puffer ist die richtige Massnahme.")


def main():
    schluessel = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not schluessel:
        sys.exit("Kein FINNHUB_API_KEY gesetzt.")

    if len(sys.argv) > 2 and sys.argv[1].lower() == "nachpruefung":
        nachpruefung(schluessel, sys.argv[2:])
        return

    try:
        ws = websocket.create_connection("wss://ws.finnhub.io?token="
                                         + schluessel, timeout=15)
    except Exception as e:
        sys.exit(f"Verbindung fehlgeschlagen ({type(e).__name__}).")
    z = Zaehler(ws)

    # --- A: weit weg von der Grenze -----------------------------------
    klein = VERDAECHTIG + KONTROLLE
    print(f"\n=== A: nur {len(klein)} Symbole, 120 Sekunden ===")
    print("    Frage: Schweigen Vodafone und Ovintiv auch OHNE jede "
          "Grenzennaehe?")
    z.an(klein)
    z.hoere(120)
    a_aktiv, a_still = bericht(z, klein, 120, "Ergebnis A:")
    z.ab(klein)
    time.sleep(2)

    # --- B: genau an der Grenze ---------------------------------------
    fuenfzig = LIQUIDE[:50]
    print(f"\n=== B: genau {len(fuenfzig)} sehr liquide Werte, 180 Sekunden ===")
    print("    Frage: Arbeitet der Zugang punktgenau an der Grenze sauber?")
    z.ticks.clear()
    z.an(fuenfzig)
    z.hoere(180)
    b_aktiv, b_still = bericht(z, fuenfzig, 180, "Ergebnis B:")

    # --- C: Listenwechsel AN der Grenze -------------------------------
    raus = fuenfzig[-10:]
    rein = LIQUIDE[50:60]
    print(f"\n=== C: Listenwechsel an der Grenze, 120 Sekunden ===")
    print(f"    {len(raus)} abmelden, {len(rein)} neue anmelden — genau das "
          f"macht die Staffelung staendig.")
    z.ab(raus)                       # ZUERST ab, wie im echten Client
    time.sleep(1)
    z.an(rein)
    z.ticks.clear()
    z.hoere(120)
    c_aktiv, c_still = bericht(z, rein, 120, "Ergebnis C (nur die Neuen):")

    # --- D: bewusst darueber ------------------------------------------
    drueber = LIQUIDE[60:65]
    print(f"\n=== D: bewusst ueber die Grenze, {len(drueber)} zusaetzlich ===")
    print("    Frage: Wo genau sagt der Server Stopp?")
    z.an(drueber)
    z.ticks.clear()
    z.hoere(60)
    d_aktiv, d_still = bericht(z, drueber, 60, "Ergebnis D (nur die Zusaetzlichen):")

    try:
        ws.close()
    except Exception:
        pass

    # --- Urteil --------------------------------------------------------
    print("\n" + "=" * 60)
    print("URTEIL")
    print("=" * 60)

    kontrolle_ok = all(s in a_aktiv for s in KONTROLLE)
    verdaechtig_still = [s for s in VERDAECHTIG if s in a_still]

    if not kontrolle_ok:
        print("Die Kontrollgruppe schwieg schon in Abschnitt A — die Leitung "
              "war gestoert. Das Ergebnis ist NICHT verwertbar, bitte "
              "wiederholen.")
        return

    if verdaechtig_still:
        print(f"ABSCHNITT A: {', '.join(verdaechtig_still)} schwiegen auch bei "
              f"nur {len(klein)} Symbolen, also meilenweit von der Grenze "
              f"entfernt, waehrend die Kontrolle sprudelte.")
        print("  -> Es sind ZWEI VERSCHIEDENE DINGE. Die Grenze kann diese "
              "Ausfaelle nicht erklaeren; es ist eine Luecke in der "
              "Abdeckung.")
    else:
        print(f"ABSCHNITT A: {', '.join(VERDAECHTIG)} lieferten diesmal Ticks, "
              f"obwohl sie bei 50 Symbolen zweimal schwiegen.")
        print("  -> Dann war sehr wohl die GRENZE schuld, nicht die "
              "Abdeckung. Der Puffer war die richtige Massnahme.")

    print(f"\nABSCHNITT B: {len(b_aktiv)} von 50 Schwergewichten lieferten "
          f"Ticks.")
    if b_still:
        print(f"  Stumm geblieben: {', '.join(b_still)}")
        print("  -> Bei lauter Schwergewichten kann das nicht an der "
              "Liquiditaet liegen. Punktgenau an der Grenze gehen also "
              "Werte verloren — der Puffer ist noetig.")
    else:
        print("  -> Alle 50 kamen an. Die Grenze ist im Dauerbetrieb "
              "unbedenklich, ein Puffer waere dafuer nicht noetig.")

    print(f"\nABSCHNITT C: {len(c_aktiv)} von {len(rein)} neu angemeldeten "
          f"Werten kamen nach dem Listenwechsel an.")
    if c_still:
        print(f"  Nicht angekommen: {', '.join(c_still)}")
        print("  -> Der Wechsel an der Grenze verliert Werte. GENAU dagegen "
              "hilft der Puffer.")
    else:
        print("  -> Der Listenwechsel an der Grenze klappt sauber, auch ohne "
              "Puffer.")

    print(f"\nABSCHNITT D: {len(d_aktiv)} von {len(drueber)} ueberzaehligen "
          f"Werten kamen an.")
    if z.fehler:
        print(f"  Serverantworten: {'; '.join(z.fehler)}")
    print(f"  -> Damit liegt die belegte Obergrenze bei {50 + len(d_aktiv)} "
          f"gleichzeitigen Symbolen.")


if __name__ == "__main__":
    main()
