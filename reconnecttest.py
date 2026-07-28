#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GREIFT DIE WIEDERVERBINDUNG WIRKLICH?
======================================
Mathias' Auftrag vom 28.07.2026: Die Wiederverbindung von yahoo_ws.py ist
gebaut, wurde aber in keinem Testlauf gebraucht — sie ist damit unbelegt.
Also wird ein Abriss KUENSTLICH herbeigefuehrt.

Geht das auch bei geschlossener Boerse? Ja. Der entscheidende Kniff:
Yahoo schickt auch nachboerslich weiter Meldungen. Der Client verwirft sie
fuer den Kursspeicher (market_hours ungleich 1 gehoert nicht in die
Tagesspanne), zaehlt sie aber im Feld 'ausserhalb' mit. Genau dieser
Zaehler ist hier das Lebenszeichen: Steigt er nach dem erzwungenen Abriss
wieder, steht die Verbindung nachweislich erneut — ganz ohne Handel.

Der Abriss wird so erzeugt, wie er im Ernstfall aussieht: Die offenen
Verbindungen werden von aussen geschlossen, waehrend der Client weiter
laufen WILL. stop() waere etwas anderes — das ist das geordnete Ende.

Aufruf:  python reconnecttest.py
"""

import sys
import time

from kurs_cache import KursCache
from yahoo_ws import YahooWebSocket

PROBEN = ["AAPL", "MSFT", "NVDA", "TSLA", "AMD", "SPY"]


def lebenszeichen(ws):
    """Alles, was belegt, dass Daten fliessen — im Handel wie danach."""
    st = ws.statistik()
    return st["meldungen"] + st["ausserhalb"]


def warte_auf_daten(ws, sekunden, ab=0):
    """Wartet, bis der Zaehler ueber 'ab' steigt. Liefert den Stand."""
    ende = time.time() + sekunden
    while time.time() < ende:
        jetzt = lebenszeichen(ws)
        if jetzt > ab:
            return jetzt
        time.sleep(0.5)
    return lebenszeichen(ws)


def main():
    cache = KursCache()
    ws = YahooWebSocket(cache)
    print(f"Verbinde mit {len(PROBEN)} Aktien …")
    if not ws.start(PROBEN):
        sys.exit("Strom nicht verfügbar — Test nicht durchführbar.")

    print("\n--- SCHRITT 1: Kommen überhaupt Daten? ---")
    vorher = warte_auf_daten(ws, 30)
    st = ws.statistik()
    print(f"  {st['verbindungen']} Verbindung(en), {st['meldungen']} Meldungen "
          f"im Handel, {st['ausserhalb']} ausserhalb der Handelszeit.")
    if vorher == 0:
        ws.stop()
        sys.exit("In 30 Sekunden kam nichts an — ohne Datenfluss lässt sich "
                 "die Wiederverbindung nicht belegen. Bitte während oder "
                 "kurz nach der Handelszeit wiederholen.")
    print(f"  ✓ Daten fliessen (Zaehler {vorher}).")

    print("\n--- SCHRITT 2: Abriss erzwingen ---")
    neustarts_vorher = ws.statistik()["neustarts"]
    with ws._lock:
        offen = list(ws._verbindungen)
    print(f"  Schliesse {len(offen)} Verbindung(en) von aussen, "
          f"während der Client weiterlaufen will.")
    for verbindung in offen:
        try:
            verbindung.close()
        except Exception as e:
            print(f"  (Schliessen meldete {type(e).__name__} — das ist in "
                  f"Ordnung, es geht um den Abriss.)")
    time.sleep(2)
    st = ws.statistik()
    print(f"  Direkt danach: {st['verbindungen']} offene Verbindung(en).")

    print("\n--- SCHRITT 3: Baut er sich selbst wieder auf? ---")
    print("  (Der Client wartet nach einem Abriss 5 Sekunden.)")
    stand = lebenszeichen(ws)
    ende = time.time() + 60
    erfolg = False
    while time.time() < ende:
        st = ws.statistik()
        if st["neustarts"] > neustarts_vorher and st["verbindungen"] > 0:
            neu = warte_auf_daten(ws, 30, ab=stand)
            if neu > stand:
                erfolg = True
                print(f"  ✓ Nach {int(60 - (ende - time.time()))} Sekunden: "
                      f"{st['verbindungen']} Verbindung(en) wieder offen, "
                      f"{st['neustarts'] - neustarts_vorher} Neuaufbau(ten), "
                      f"Zaehler von {stand} auf {neu} gestiegen.")
                break
        time.sleep(1)

    st = ws.statistik()
    ws.stop()

    print("\n" + "=" * 60)
    print("URTEIL")
    print("=" * 60)
    if erfolg:
        print("Die Wiederverbindung GREIFT: Nach dem erzwungenen Abriss hat "
              "sich der Client von selbst neu verbunden, die Symbole erneut "
              "abonniert, und es kamen wieder Daten an. Kein Eingriff nötig.")
    elif st["neustarts"] > neustarts_vorher:
        print(f"Der Client hat den Abriss BEMERKT und "
              f"{st['neustarts'] - neustarts_vorher} Mal neu aufgebaut, aber "
              f"innerhalb der Frist kamen keine neuen Daten. Bei "
              f"geschlossener Börse kann das schlicht daran liegen, dass "
              f"gerade nichts gehandelt wird — dann bitte im Handel "
              f"wiederholen.")
    else:
        print("Der Client hat den Abriss NICHT bemerkt. Das ist ein Fehler: "
              "Im Ernstfall stünde die Wache still, ohne dass es auffällt.")
    print(f"\nStatistik am Ende: {st}")


if __name__ == "__main__":
    main()
