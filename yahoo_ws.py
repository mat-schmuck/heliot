#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YAHOO-LIVE-STROM — Kurse UND Tagesvolumen für die GANZE Liste
==============================================================
Loest den Finnhub-WebSocket ab (Mathias, 28.07.2026: "Wenn das nicht
zuverlaessig funktioniert, wurscht mit wie vielen Aktien, wuerde ich es
generell wieder auf Yahoo zurueckstellen").

Nachgemessen am 28.07.2026, zweimal — einmal von Mathias' Anschluss und
einmal vom GitHub-Server, mit identischem Ergebnis:

  Finnhub, Gratis-Zugang        Yahoo-Strom
  ---------------------------   ------------------------------------
  51 Symbole, harte Grenze      rund 100 je Verbindung, beliebig
                                viele Verbindungen
  EINE Verbindung je Schluessel kein Schluessel, also keine Regel
  Abdeckungsluecken (Vodafone,  265 von 265 Tickern gemeldet,
  Ovintiv, Lowe's: null Ticks)  keine einzige stumm
  KEIN Tagesvolumen             Tagesvolumen in JEDER Meldung
  rund 3400 Ticks/Minute        rund 3300 Meldungen/Minute

Damit faellt die ganze Staffelung weg: Es gibt keinen Grund mehr,
Aktien nach Naehe zum Kaufpunkt um knappe Plaetze konkurrieren zu
lassen, wenn alle 265 gleichzeitig live sein koennen.

DREI DINGE, DIE HIER BEWUSST SO GEBAUT SIND
--------------------------------------------
1. HAUFEN ZU HOECHSTENS 85 SYMBOLEN. Eine Verbindung traegt rund 100
   (gemessen: bei 265 auf einer Verbindung meldeten genau 100). 85
   laesst Luft, ohne die Zahl der Verbindungen aufzublaehen.

2. DAS TAGESVOLUMEN WANDERT MIT IN DEN SPEICHER — anders als beim
   Finnhub-Strom, wo bewusst 0,0 stand. Der Grund fuer den Unterschied:
   Finnhub schickt die Stueckzahl EINES Geschaefts, Yahoo den
   aufgelaufenen TAGESUMSATZ. Das eine waere als Tagesvolumen um
   Groessenordnungen falsch, das andere ist genau das Gesuchte.

3. YAHOOS STROM IST EINE INOFFIZIELLE SCHNITTSTELLE. Es gibt keine
   Zusage, dass es ihn morgen noch gibt. Deshalb bleibt der regelmaessige
   Abruf der Tagesdaten als Netz bestehen: Faellt der Strom aus, ist die
   Wache genau dort, wo sie vorher war, und nicht schlechter.

Aufruf:  python yahoo_ws.py [Sekunden]   Selbsttest mit echten Daten
"""

import threading
import time

from kurs_cache import Kurswert

PRO_VERBINDUNG = 85


class YahooWebSocket:
    """Mehrere Verbindungen, ein gemeinsamer Kursspeicher."""

    def __init__(self, cache, pro_verbindung=PRO_VERBINDUNG, leise=False):
        self.cache = cache
        self.pro_verbindung = pro_verbindung
        self.leise = leise
        self._verbindungen = []
        self._symbole = []
        self._lock = threading.RLock()
        self._laeuft = False
        self.meldungen = 0
        self.letzte_meldung = 0.0
        self._meldung_je = {}
        self.fehler = []
        self.neustarts = 0

    # --- Innereien ------------------------------------------------------

    def _sag(self, text):
        if not self.leise:
            print(f"  [Yahoo-Strom] {text}")

    def _verarbeite(self, msg):
        symbol = msg.get("id")
        preis = msg.get("price")
        if not symbol or preis is None:
            return
        try:
            preis = float(preis)
        except (TypeError, ValueError):
            return
        # Yahoo schickt das Tagesvolumen als Zeichenkette mit.
        try:
            tagesvolumen = float(msg.get("day_volume") or 0.0)
        except (TypeError, ValueError):
            tagesvolumen = 0.0
        jetzt = time.time()
        self.cache.setze(Kurswert(
            ticker=symbol.upper(), preis=preis, zeit=jetzt,
            volumen=tagesvolumen, quelle="yahoo_ws"))
        self.meldungen += 1
        self.letzte_meldung = jetzt
        self._meldung_je[symbol.upper()] = jetzt

    def _starte_haufen(self, teil, nummer):
        """Eine Verbindung, die sich bei Abriss selbst neu aufbaut."""
        import yfinance as yf

        def laufen():
            while self._laeuft:
                ws = None
                try:
                    ws = yf.WebSocket(verbose=False)
                    with self._lock:
                        self._verbindungen.append(ws)
                    ws.subscribe(teil)
                    ws.listen(self._verarbeite)
                except Exception as e:
                    if self._laeuft:
                        self.fehler.append(f"{nummer}:{type(e).__name__}")
                finally:
                    with self._lock:
                        if ws in self._verbindungen:
                            self._verbindungen.remove(ws)
                if not self._laeuft:
                    return
                # Abriss im laufenden Betrieb: kurz warten, neu aufbauen.
                # Ohne diese Schleife waere der Ausfall STILL — die Wache
                # liefe weiter und merkte nur an fehlenden Kursen, dass
                # etwas fehlt.
                self.neustarts += 1
                self._sag(f"Verbindung {nummer} abgerissen, neuer Versuch "
                          f"in 5 Sekunden.")
                time.sleep(5)

        t = threading.Thread(target=laufen, daemon=True)
        t.start()
        return t

    # --- Steuerung ------------------------------------------------------

    def start(self, symbole):
        """Baut die Verbindungen auf. Liefert False, wenn das gar nicht
        geht (yfinance zu alt oder ohne Strom-Unterstuetzung)."""
        try:
            import yfinance as yf
        except ImportError:
            self._sag("yfinance fehlt — kein Live-Betrieb.")
            return False
        if not hasattr(yf, "WebSocket"):
            self._sag(f"yfinance {getattr(yf, '__version__', '?')} kann den "
                      f"Strom nicht (nötig ab 1.5) — kein Live-Betrieb.")
            return False
        if self._laeuft:
            return True

        self._symbole = sorted({s.upper() for s in symbole})
        haufen = [self._symbole[i:i + self.pro_verbindung]
                  for i in range(0, len(self._symbole), self.pro_verbindung)]
        self._laeuft = True
        for i, teil in enumerate(haufen, 1):
            self._starte_haufen(teil, i)

        # Kurz warten, bis wirklich etwas ankommt — der Aufrufer soll
        # wissen, woran er ist, statt blind weiterzumachen.
        for _ in range(60):
            if self.meldungen > 0:
                self._sag(f"{len(self._symbole)} Aktien live auf "
                          f"{len(haufen)} Verbindungen.")
                return True
            time.sleep(0.25)
        self._sag(f"{len(haufen)} Verbindungen aufgebaut, aber in 15 "
                  f"Sekunden kam nichts an. Läuft weiter, die Wache "
                  f"stützt sich solange auf die Tagesdaten.")
        return True

    def stop(self):
        self._laeuft = False
        with self._lock:
            verbindungen = list(self._verbindungen)
        for ws in verbindungen:
            try:
                ws.close()
            except Exception:
                pass

    def ohne_meldung(self, mindestens_sekunden=0):
        """Welche Aktien haben noch gar nichts geschickt? Reines
        Mitschreiben, ohne Folgen — bei Yahoo war die Antwort in beiden
        Messungen 'keine', aber das soll auffallen, wenn es sich aendert."""
        if not self._laeuft:
            return []
        return [s for s in self._symbole if s not in self._meldung_je]

    def statistik(self):
        with self._lock:
            offen = len(self._verbindungen)
        return {
            "verbindungen": offen,
            "symbole": len(self._symbole),
            "meldungen": self.meldungen,
            "mit_kurs": len(self._meldung_je),
            "sekunden_seit_letzter": (
                round(time.time() - self.letzte_meldung, 1)
                if self.letzte_meldung else None),
            "neustarts": self.neustarts,
            "fehler": self.fehler[-3:],
        }


if __name__ == "__main__":
    # Selbsttest MIT Netzwerk: Der Strom laesst sich ohne echte Boerse
    # nicht sinnvoll pruefen. Ausserhalb der Handelszeit kommen wenige
    # oder keine Meldungen — das ist dann kein Fehler.
    import sys
    from kurs_cache import KursCache

    dauer = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    proben = ["AAPL", "MSFT", "NVDA", "VOD", "OVV", "LOW"]

    cache = KursCache()
    ws = YahooWebSocket(cache)
    if not ws.start(proben):
        sys.exit("Strom nicht verfügbar.")
    time.sleep(dauer)
    ws.stop()

    print(f"\nStatistik: {ws.statistik()}")
    for t in proben:
        wert = cache._store.get(t)
        if wert is None:
            print(f"  {t:6s} nichts erhalten")
        else:
            print(f"  {t:6s} {wert.preis:9.2f} | Tagesvolumen "
                  f"{wert.volumen:12,.0f} | Quelle {wert.quelle} | "
                  f"vor {wert.alter_sekunden():.0f} s")
    fehlend = [t for t in proben if t not in cache._store]
    print(f"\nOhne Meldung: {', '.join(fehlend) if fehlend else 'keine'}")
