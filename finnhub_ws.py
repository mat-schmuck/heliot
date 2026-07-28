#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FINNHUB-WEBSOCKET — tickweise Kurse fuer die schnelle Liste
============================================================
Teil 2 von Gerhards Ausbauplan (Uebergabe vom 28.07.2026). Grundlage der
dreistufigen Staffelung: Nur die Aktien nahe am Kaufpunkt bekommen echte
Ticks, alle anderen laufen sparsam ueber REST beziehungsweise yfinance.

Was dieses Modul leistet:
  * Verbindung zu wss://ws.finnhub.io, Schluessel aus FINNHUB_API_KEY
  * Symbole DYNAMISCH an- und abmelden (die schnelle Liste aendert sich
    staendig, sobald sich eine Aktie dem Kaufpunkt naehert)
  * jeden Handelstick in den GEMEINSAMEN Kursspeicher schreiben
    (kurs_cache.py) — dieselbe Ablage, aus der auch der Waechter liest
  * bei Verbindungsabbruch selbsttaetig neu verbinden UND alle aktiven
    Symbole neu abonnieren
  * bei dauerhaftem Ausfall NICHT stillschweigend verstummen, sondern
    das melden, damit die betroffenen Aktien auf REST zurueckfallen

Drei Dinge, die beim Bau Kopfschmerzen gemacht haetten und deshalb hier
festgehalten sind:

1. EIN SCHLUESSEL, EINE VERBINDUNG. Die Finnhub-Doku sagt woertlich:
   "1 API key can only open 1 connection at a time." Es darf also nie
   zwei Verbindungen gleichzeitig geben — Tagwache und Schlussstunden-
   Wache muessen sich abwechseln, nicht ueberlappen. Darum ist dieses
   Modul als EIN Client gebaut, den sich alles teilt.

2. DIE OBERGRENZE STEHT NIRGENDS. Gerhards Entwurf rechnet mit rund 50
   gleichzeitigen Symbolen (30 schnelle Liste + 20 oberer Vorraum). Die
   Zahl ist in der Doku nicht zu finden; sie wird mit finnhub_messung.py
   im laufenden Handel nachgemessen. Bis dahin gilt der Wert aus
   config.py, und der Client haelt sich strikt daran, statt blind zu
   abonnieren.

3. TICK-VOLUMEN IST NICHT TAGESVOLUMEN. Ein Trade-Tick bringt die
   Stueckzahl GENAU DIESES Geschaefts mit, nicht das Tagesvolumen. Wer
   das verwechselt, bekommt eine Volumenbestaetigung, die um Faktor
   Tausend danebenliegt. Die Volumenpruefung bleibt deshalb bei den
   Tagesdaten; der WebSocket liefert ausschliesslich den PREIS.
"""

import json
import os
import threading
import time

from kurs_cache import Kurswert

try:
    import websocket           # Paket: websocket-client
except ImportError:            # pragma: no cover
    websocket = None

URL = "wss://ws.finnhub.io"


class FinnhubWebSocket:
    """Ein einziger Client fuer den gesamten Lauf (siehe Punkt 1 oben)."""

    def __init__(self, cache, max_symbole=30, schluessel=None, leise=False):
        self.cache = cache
        self.max_symbole = max_symbole
        self._schluessel = (schluessel
                            or os.environ.get("FINNHUB_API_KEY", "")).strip()
        self.leise = leise
        self._ws = None
        self._thread = None
        self._aktiv = set()          # aktuell abonnierte Symbole
        self._abo_seit = {}          # Symbol -> wann abonniert
        self._tick_je = {}           # Symbol -> letzter Tick
        self._lock = threading.RLock()
        self._laeuft = False
        self.verbunden = False
        self.ticks = 0
        self.letzter_tick = 0.0
        self.verbindungen = 0        # wie oft (neu) verbunden
        self.fehler = []

    # --- Innereien ------------------------------------------------------

    def _sag(self, text):
        if not self.leise:
            print(f"  [WebSocket] {text}")

    def _senden(self, art, symbol):
        if self._ws is None:
            return False
        try:
            self._ws.send(json.dumps({"type": art, "symbol": symbol}))
            return True
        except Exception:
            return False

    def _bei_oeffnen(self, _ws):
        self.verbunden = True
        self.verbindungen += 1
        # Nach jedem Neuverbinden ALLE aktiven Symbole erneut abonnieren —
        # der Server vergisst die Abos mit der Verbindung.
        with self._lock:
            symbole = sorted(self._aktiv)
        for s in symbole:
            self._senden("subscribe", s)
            time.sleep(0.03)
        self._sag(f"verbunden, {len(symbole)} Symbole (neu) abonniert.")

    def _bei_nachricht(self, _ws, roh):
        try:
            nachricht = json.loads(roh)
        except Exception:
            return
        art = nachricht.get("type")
        if art == "trade":
            jetzt = time.time()
            for handel in nachricht.get("data", []):
                symbol = handel.get("s")
                preis = handel.get("p")
                if not symbol or preis is None:
                    continue
                # NUR der Preis wandert in den gemeinsamen Speicher. Die
                # Stueckzahl des einzelnen Geschaefts steht bewusst NICHT
                # als "volumen" drin (siehe Punkt 3 oben) — sie wuerde mit
                # dem Tagesvolumen verwechselt.
                self.cache.setze(Kurswert(
                    ticker=symbol.upper(), preis=float(preis), zeit=jetzt,
                    volumen=0.0, quelle="finnhub_ws"))
                self.ticks += 1
                self.letzter_tick = jetzt
                self._tick_je[symbol.upper()] = jetzt
        elif art == "error":
            meldung = str(nachricht.get("msg"))[:150]
            self.fehler.append(meldung)
            self._sag(f"Server meldet Fehler: {meldung}")

    def _bei_fehler(self, _ws, fehler):
        # Der Schluessel steckt in der URL — deshalb NIE den Fehlertext
        # ausgeben, nur die Art.
        self.verbunden = False
        self.fehler.append(type(fehler).__name__)
        self._sag(f"Verbindungsfehler ({type(fehler).__name__}).")

    def _bei_schliessen(self, _ws, *_):
        self.verbunden = False
        self._sag("Verbindung geschlossen.")

    # --- Steuerung ------------------------------------------------------

    def start(self):
        """Startet die Verbindung im Hintergrund. Liefert False, wenn das
        gar nicht moeglich ist (kein Paket, kein Schluessel)."""
        if websocket is None:
            self._sag("Paket websocket-client fehlt — kein Live-Betrieb.")
            return False
        if not self._schluessel:
            self._sag("Kein FINNHUB_API_KEY gesetzt — kein Live-Betrieb.")
            return False
        if self._laeuft:
            return True

        self._ws = websocket.WebSocketApp(
            f"{URL}?token={self._schluessel}",
            on_open=self._bei_oeffnen,
            on_message=self._bei_nachricht,
            on_error=self._bei_fehler,
            on_close=self._bei_schliessen,
        )
        self._laeuft = True

        def laufen():
            # reconnect: bei Abbruch nach 5 s neu verbinden; on_open
            # abonniert dann alles erneut.
            while self._laeuft:
                try:
                    self._ws.run_forever(ping_interval=30, ping_timeout=10,
                                         reconnect=5)
                except Exception as e:
                    self.fehler.append(type(e).__name__)
                if self._laeuft:
                    time.sleep(5)

        self._thread = threading.Thread(target=laufen, daemon=True)
        self._thread.start()

        # Kurz auf die Verbindung warten, damit der Aufrufer weiss, woran
        # er ist, statt blind weiterzumachen.
        for _ in range(50):
            if self.verbunden:
                return True
            time.sleep(0.2)
        self._sag("Verbindung kam nicht zustande — es bleibt bei REST.")
        return False

    def stop(self):
        self._laeuft = False
        try:
            if self._ws is not None:
                self._ws.close()
        except Exception:
            pass
        self.verbunden = False

    def setze_symbole(self, symbole):
        """Bringt die Abos auf genau diese Liste — meldet Neue an, Alte ab.

        Genau hier lebt die Staffelung: Naehert sich eine Aktie dem
        Kaufpunkt, kommt sie herein; entfernt sie sich, fliegt sie raus
        und macht Platz."""
        gewuenscht = {s.upper() for s in symbole}
        if len(gewuenscht) > self.max_symbole:
            # Strikt kappen statt blind abonnieren: Was ueber der Grenze
            # liegt, wuerde ohnehin stillschweigend verworfen — dann lieber
            # bewusst und sichtbar.
            gewuenscht = set(sorted(gewuenscht)[:self.max_symbole])
            self._sag(f"Auf {self.max_symbole} Symbole gekappt "
                      f"(Grenze aus config.py).")
        jetzt = time.time()
        with self._lock:
            dazu = gewuenscht - self._aktiv
            weg = self._aktiv - gewuenscht
            self._aktiv = gewuenscht
            # Die Abo-Uhr laeuft je Symbol: Nur wer LANGE genug abonniert
            # ist und trotzdem schweigt, gilt als stumm. Wer eben erst
            # dazukam, hatte noch keine Gelegenheit.
            for s in dazu:
                self._abo_seit[s] = jetzt
            for s in weg:
                self._abo_seit.pop(s, None)
        for s in sorted(weg):
            self._senden("unsubscribe", s)
        for s in sorted(dazu):
            self._senden("subscribe", s)
        if dazu or weg:
            self._sag(f"{len(dazu)} neu abonniert, {len(weg)} abgemeldet, "
                      f"jetzt {len(gewuenscht)} aktiv.")
        return sorted(gewuenscht)

    @property
    def aktive_symbole(self):
        with self._lock:
            return sorted(self._aktiv)

    def ohne_tick(self, mindestens_sekunden):
        """NUR ZUM MITSCHREIBEN: Welche abonnierten Symbole haben seit dem
        Abo keinen EINZIGEN Tick geliefert?

        Das Ergebnis wird bewusst NICHT verwertet — es wandert allein ins
        Protokoll. Eine Regel, die solche Werte hinauswirft und ihren Platz
        neu vergibt, war am 28.07.2026 kurz gebaut und wurde auf Mathias'
        Ansage wieder entfernt: Die dafuer noetige Wartefrist ist im
        normalen Handel viel zu lang, um zu helfen. Stattdessen bleiben
        zehn der 50 Plaetze frei (config: websocket_max_werte = 40).

        Warum es trotzdem gemessen wird: Nachgemessen mit feedpruefung.py
        traegt der Gratis-Strom nicht jede Aktie — Vodafone und Ovintiv
        wurden nachweislich gehandelt und kamen mit null Ticks an. Wie oft
        das vorkommt, ist die Grundlage fuer die naechste Entscheidung, und
        die Zahl kostet nichts.

        Gezaehlt wird ab dem ABO, nicht ab Programmstart, und nur solange
        die Verbindung steht. Nach einem Abriss waere sonst schlagartig die
        halbe Liste auffaellig, obwohl nur die Leitung weg war."""
        if not self.verbunden:
            return []
        jetzt = time.time()
        with self._lock:
            symbole = sorted(self._aktiv)
            seit = dict(self._abo_seit)
        stumm = []
        for s in symbole:
            start = seit.get(s)
            if start is None or jetzt - start < mindestens_sekunden:
                continue
            letzter = self._tick_je.get(s)
            if letzter is None or letzter < start:
                stumm.append(s)
        return stumm

    def statistik(self):
        return {
            "verbunden": self.verbunden,
            "aktive_symbole": len(self._aktiv),
            "ticks": self.ticks,
            "sekunden_seit_letztem_tick": (
                round(time.time() - self.letzter_tick, 1)
                if self.letzter_tick else None),
            "verbindungen": self.verbindungen,
            "fehler": self.fehler[-3:],
        }


if __name__ == "__main__":
    # Selbsttest OHNE Netzwerk: prueft die Abo-Verwaltung und die Kappung.
    from kurs_cache import KursCache

    cache = KursCache()
    ws = FinnhubWebSocket(cache, max_symbole=3, schluessel="nur-test", leise=True)

    # Ohne Verbindung duerfen Abos trotzdem verwaltet werden (sie werden
    # beim naechsten Verbinden nachgeholt).
    assert ws.setze_symbole(["AAPL", "MSFT"]) == ["AAPL", "MSFT"]
    assert ws.aktive_symbole == ["AAPL", "MSFT"]
    print("✓ Abos werden geführt, auch ohne Verbindung")

    ws.setze_symbole(["MSFT", "NVDA"])
    assert ws.aktive_symbole == ["MSFT", "NVDA"], "AAPL hätte abgemeldet werden müssen"
    print("✓ Wechsel der schnellen Liste: alt abgemeldet, neu abonniert")

    gekappt = ws.setze_symbole(["A", "B", "C", "D", "E"])
    assert len(gekappt) == 3, "Grenze aus config.py muss strikt gelten"
    print(f"✓ Kappung greift: 5 gewünscht, {len(gekappt)} abonniert")

    # Ein eingehender Tick muss im gemeinsamen Speicher landen — und zwar
    # als Preis, NICHT als Tagesvolumen.
    ws._bei_nachricht(None, json.dumps(
        {"type": "trade", "data": [{"s": "AAPL", "p": 123.45, "v": 100,
                                    "t": int(time.time() * 1000)}]}))
    wert = cache._store.get("AAPL")
    assert wert is not None and wert.preis == 123.45 and wert.quelle == "finnhub_ws"
    assert wert.volumen == 0.0, "Tick-Stückzahl darf NICHT als Tagesvolumen gelten"
    print("✓ Tick landet als Preis im gemeinsamen Speicher (ohne Volumen)")

    ws._bei_nachricht(None, json.dumps({"type": "error", "msg": "Testfehler"}))
    assert ws.fehler and "Testfehler" in ws.fehler[-1]
    print("✓ Serverfehler werden festgehalten")

    # Tickfreie Werte fürs Protokoll erkennen — der Fall Vodafone/Ovintiv
    # vom 28.07.2026. Ohne stehende Verbindung darf NIEMAND auffallen
    # (sonst wäre nach jedem Leitungsabriss die halbe Liste verdächtig).
    ws2 = FinnhubWebSocket(cache, max_symbole=5, schluessel="nur-test", leise=True)
    ws2.setze_symbole(["LAUT", "STUMM"])
    ws2._abo_seit = {"LAUT": time.time() - 3600, "STUMM": time.time() - 3600}
    assert ws2.ohne_tick(60) == [], "ohne Verbindung darf nichts auffallen"
    ws2.verbunden = True
    assert ws2.ohne_tick(60) == ["LAUT", "STUMM"]
    ws2._bei_nachricht(None, json.dumps(
        {"type": "trade", "data": [{"s": "LAUT", "p": 10.0, "v": 5}]}))
    assert ws2.ohne_tick(60) == ["STUMM"], \
        "ein einziger Tick belegt, dass der Strom die Aktie trägt"
    print("✓ Tickfreie Werte erkannt: ein Tick genügt als Nachweis der Abdeckung")

    # Frisch abonniert heißt: noch keine Gelegenheit gehabt.
    ws2.setze_symbole(["LAUT", "STUMM", "NEU"])
    assert "NEU" not in ws2.ohne_tick(60), "frische Abos brauchen erst ihre Frist"
    print("✓ Frisch abonnierte Werte werden nicht vorschnell gezählt")
    print(f"\nStatistik: {ws.statistik()}")
    print("\nAlle WebSocket-Tests bestanden (ohne Netzwerk).")
