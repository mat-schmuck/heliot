#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YAHOOS EIGENER LIVE-STROM — TRAEGT ER DIE GANZE LISTE?
=======================================================
Mathias' Frage vom 28.07.2026: "Wenn das nicht zuverlaessig funktioniert,
wurscht mit wie vielen Aktien, wuerde ich es generell wieder auf Yahoo
zurueckstellen. Kann man dort auch in Realtime messen, also ohne die
6-Min-Sperre? Oder war die durch Github begruendet?"

Zur zweiten Frage vorweg, weil sie oft falsch erinnert wird: Die sechs
Minuten haben mit GitHub NICHTS zu tun. GitHub begrenzt nur die
Gesamtlaufzeit eines Auftrags auf 6 Stunden — deshalb die zweiteilige
Wache. Innerhalb eines Laufs darf die Schleife so schnell drehen, wie
sie will. Die sechs Minuten sind SELBST GESETZT: Jede Runde laedt acht
Monate Tagesdaten fuer alle 265 Aktien in einem Rutsch. Das alle 20
Sekunden zu tun, wuerde eine Drosselung durch Yahoo riskieren.

Yahoo hat aber einen eigenen Datenstrom (wss://streamer.finance.yahoo.com,
in yfinance ab 1.5 als yf.WebSocket). Der schickt Kurse von selbst,
ganz ohne Abfragetakt. Zu Hause gemessen am 28.07.2026:

  * eine Verbindung traegt rund 100 Symbole, danach ist Schluss
  * MEHRERE Verbindungen sind erlaubt (Yahoo braucht keinen Schluessel,
    also gibt es auch keine Ein-Verbindung-Regel wie bei Finnhub)
  * auf vier Verbindungen verteilt meldeten 265 von 265 Tickern
  * JEDE Meldung bringt day_volume mit — das Tagesvolumen, das Finnhubs
    Strom gar nicht liefert
  * die drei Werte, die Finnhub nicht traegt (Vodafone, Ovintiv,
    Lowe's), kamen bei Yahoo sauber an

Offen war nur, ob das vom GitHub-Server aus genauso laeuft — Yahoo
behandelt Rechenzentrums-Adressen manchmal anders als Privatanschluesse.
Genau dafuer ist dieses Skript da.

Aufruf:  python yahoo_strom.py [Sekunden] [Ticker je Verbindung]
"""

import collections
import sys
import threading
import time

XLSX = "kaufpunkte_aktuell.xlsx"


def main():
    dauer = int(sys.argv[1]) if len(sys.argv) > 1 else 180
    pro_verbindung = int(sys.argv[2]) if len(sys.argv) > 2 else 85

    import yfinance as yf
    print(f"yfinance {yf.__version__}, WebSocket vorhanden: "
          f"{hasattr(yf, 'WebSocket')}")
    if not hasattr(yf, "WebSocket"):
        sys.exit("Diese yfinance-Fassung kann den Strom nicht — bitte "
                 "aktualisieren (ab 1.5).")

    import pandas as pd
    df = pd.read_excel(XLSX, sheet_name="Kaufpunkte")
    SYM = sorted({str(t).strip().upper() for t in df["Ticker"]})
    print(f"{len(SYM)} Ticker aus der laufenden Liste.")

    zaehler = collections.Counter()
    letzter = {}
    sperre = threading.Lock()
    verbindungen = []
    start = time.time()

    haufen = [SYM[i:i + pro_verbindung]
              for i in range(0, len(SYM), pro_verbindung)]

    def baue(teil):
        ws = yf.WebSocket(verbose=False)
        verbindungen.append(ws)

        def handler(msg):
            s = msg.get("id")
            if not s:
                return
            with sperre:
                zaehler[s] += 1
                letzter[s] = msg

        def laufen():
            try:
                ws.subscribe(teil)
                ws.listen(handler)
            except Exception:
                pass          # sauberes Schliessen wirft hier ebenfalls

        threading.Thread(target=laufen, daemon=True).start()

    print(f"Verteilt auf {len(haufen)} Verbindungen zu je hoechstens "
          f"{pro_verbindung} Tickern, {dauer} Sekunden.\n")
    for teil in haufen:
        baue(teil)
    time.sleep(dauer)
    for ws in verbindungen:
        try:
            ws.close()
        except Exception:
            pass
    time.sleep(2)

    minuten = (time.time() - start) / 60
    gemeldet = [s for s in SYM if zaehler[s] > 0]
    stumm = [s for s in SYM if zaehler[s] == 0]

    print(f"--- ERGEBNIS nach {minuten:.1f} Minuten ---")
    print(f"{len(gemeldet)} von {len(SYM)} Tickern haben gemeldet.")
    print(f"Meldungen gesamt: {sum(zaehler.values())}, "
          f"{sum(zaehler.values()) / minuten:.0f} pro Minute.")

    if gemeldet:
        alter = []
        for s in gemeldet:
            t = letzter[s].get("time")
            if t:
                try:
                    alter.append(time.time() - int(t) / 1000)
                except Exception:
                    pass
        alter.sort()
        if alter:
            print(f"Alter des letzten Kurses: Mitte "
                  f"{alter[len(alter)//2]:.0f} s, drei Viertel unter "
                  f"{alter[int(len(alter)*0.75)]:.0f} s, schlechtester "
                  f"{alter[-1]:.0f} s")
        mit_vol = sum(1 for s in gemeldet if letzter[s].get("day_volume"))
        print(f"Mit Tagesvolumen: {mit_vol} von {len(gemeldet)}")
        raten = sorted((zaehler[s] / minuten, s) for s in gemeldet)
        print("Lebhafteste: "
              + ", ".join(f"{s} {r:.0f}" for r, s in raten[-5:][::-1]))

    print(f"\nStumm ({len(stumm)}): "
          + (", ".join(stumm[:50]) if stumm else "keine")
          + (" …" if len(stumm) > 50 else ""))

    print("\n--- URTEIL ---")
    if not gemeldet:
        print("Vom GitHub-Server kommt GAR NICHTS an. Yahoo blockt die "
              "Rechenzentrums-Adresse — der Strom ist dort nicht nutzbar.")
    elif len(stumm) == 0:
        print(f"Alle {len(SYM)} Aktien kommen live an, auch vom "
              f"GitHub-Server. Damit braucht es weder Staffelung noch "
              f"Platzvergabe noch Puffer: Jede Aktie der Liste bekommt "
              f"Echtzeit, und das Tagesvolumen gleich mit.")
    else:
        anteil = len(gemeldet) / len(SYM) * 100
        print(f"{anteil:.0f} Prozent kommen an, {len(stumm)} fehlen. Vom "
              f"GitHub-Server laeuft es also SCHLECHTER als zu Hause — "
              f"das muss geklaert werden, bevor darauf gebaut wird.")


if __name__ == "__main__":
    main()
