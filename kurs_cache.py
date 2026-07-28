#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KURS-CACHE — gemeinsamer Datenspeicher für alle Module
======================================================
Scanner, Wächter und Radar ziehen oft dieselben Kurse mehrfach. Dieser Cache
holt jeden Kurs einmal, hält ihn kurz vor und gibt ihn an alle Module weiter.

Zwei Aufgaben:
  1. REDUNDANZ SPAREN: gleiche Aktie nicht 3× bei der API abfragen.
  2. STALE-DATA-ERKENNUNG: Ein Kurs, der zu alt ist (Quelle hängt), wird als
     "stale" markiert — damit ein eingefrorener Kurs am Trigger keinen
     Fehlalarm auslöst. Das war ein offener Prüfpunkt.

Der Cache ist quellen-agnostisch: Ihm wird eine Abruf-Funktion übergeben
(yfinance / Finnhub / Twelve Data). So bleibt die Datenquelle austauschbar.
"""

import time
import threading
from dataclasses import dataclass, field


@dataclass
class Kurswert:
    ticker: str
    preis: float
    zeit: float                  # Unix-Zeit des Abrufs
    volumen: float = 0.0
    quelle: str = ""
    vortagesschluss: float | None = None

    def alter_sekunden(self, jetzt=None):
        return (jetzt or time.time()) - self.zeit


class KursCache:
    """Thread-sicherer Kurs-Cache mit TTL und Stale-Erkennung."""

    def __init__(self, ttl_sekunden=60, stale_max_sekunden=120,
                 stale_pro_quelle=None):
        self.ttl = ttl_sekunden               # so lange gilt ein Wert als "frisch genug"
        self.stale_max = stale_max_sekunden   # Rückfall für unbekannte Quellen
        # Schwelle PRO QUELLE (Gerhard, 28.07.2026): Der WebSocket liefert
        # tickweise — dort sind zwei Minuten Stille ein Alarmzeichen.
        # yfinance liefert verzögert und wird nur alle sechs Minuten
        # abgefragt; mit derselben Schwelle wäre dort ständig alles "stale"
        # und keine einzige Meldung käme je durch.
        self.stale_pro_quelle = dict(stale_pro_quelle or {})
        self._store: dict[str, Kurswert] = {}
        self._lock = threading.Lock()
        self.treffer = 0                      # Statistik: aus Cache bedient
        self.abrufe = 0                       # Statistik: echt bei der Quelle geholt

    def hole(self, ticker, abruf_fn, force=False):
        """Gibt einen Kurswert zurück. Nutzt den Cache, wenn frisch genug,
        sonst wird abruf_fn(ticker) aufgerufen. abruf_fn liefert ein
        Kurswert-Objekt oder None."""
        ticker = ticker.upper()
        jetzt = time.time()
        with self._lock:
            vorhanden = self._store.get(ticker)
            if vorhanden and not force and vorhanden.alter_sekunden(jetzt) < self.ttl:
                self.treffer += 1
                return vorhanden

        # außerhalb des Locks abrufen (Netzwerk kann dauern)
        neu = abruf_fn(ticker)
        self.abrufe += 1
        if neu is None:
            # Abruf fehlgeschlagen — alten Wert zurückgeben, aber Alter sichtbar lassen
            with self._lock:
                return self._store.get(ticker)
        with self._lock:
            self._store[ticker] = neu
        return neu

    def hole_batch(self, tickers, batch_abruf_fn, force=False):
        """Wie hole(), aber für viele Ticker auf einmal. batch_abruf_fn bekommt
        die Liste der WIRKLICH nötigen (nicht frisch gecachten) Ticker und gibt
        {ticker: Kurswert} zurück. Spart API-Calls maximal."""
        tickers = [t.upper() for t in tickers]
        jetzt = time.time()
        ergebnis = {}
        fehlend = []
        with self._lock:
            for t in tickers:
                v = self._store.get(t)
                if v and not force and v.alter_sekunden(jetzt) < self.ttl:
                    ergebnis[t] = v
                    self.treffer += 1
                else:
                    fehlend.append(t)

        if fehlend:
            neu = batch_abruf_fn(fehlend) or {}
            self.abrufe += len(fehlend)
            with self._lock:
                for t, wert in neu.items():
                    if wert is not None:
                        self._store[t.upper()] = wert
                        ergebnis[t.upper()] = wert
        return ergebnis

    def schwelle_fuer(self, quelle):
        """Wie alt darf ein Kurs DIESER Quelle werden?"""
        return self.stale_pro_quelle.get(quelle or "", self.stale_max)

    def ist_stale(self, ticker):
        """True, wenn der Kurs zu alt ist (Quelle hängt) — dann NICHT für
        Trigger-Entscheidungen verwenden."""
        with self._lock:
            v = self._store.get(ticker.upper())
        if v is None:
            return True
        return v.alter_sekunden() > self.schwelle_fuer(v.quelle)

    def stale_liste(self):
        """Alle Ticker, deren Kurs gerade als stale gilt (für den Health-Check)."""
        jetzt = time.time()
        with self._lock:
            return [t for t, v in self._store.items()
                    if v.alter_sekunden(jetzt) > self.schwelle_fuer(v.quelle)]

    def statistik(self):
        gesamt = self.treffer + self.abrufe
        quote = (self.treffer / gesamt * 100) if gesamt else 0
        return {
            "cache_treffer": self.treffer,
            "echte_abrufe": self.abrufe,
            "trefferquote_pct": round(quote, 1),
            "im_cache": len(self._store),
        }


if __name__ == "__main__":
    # Selbsttest ohne Netzwerk: gemockte Abrufe
    import random
    cache = KursCache(ttl_sekunden=2, stale_max_sekunden=3)

    aufrufe = {"n": 0}
    def fake_abruf(ticker):
        aufrufe["n"] += 1
        return Kurswert(ticker, preis=round(random.uniform(10, 500), 2),
                        zeit=time.time(), volumen=1e6, quelle="fake")

    # 1) Erster Abruf holt echt, zweiter kommt aus dem Cache
    a = cache.hole("AAPL", fake_abruf)
    b = cache.hole("AAPL", fake_abruf)
    assert a.preis == b.preis and aufrufe["n"] == 1
    print(f"✓ Cache spart Abruf: AAPL 2× angefragt, nur {aufrufe['n']}× echt geholt")

    # 2) Nach TTL wird neu geholt
    time.sleep(2.1)
    cache.hole("AAPL", fake_abruf)
    assert aufrufe["n"] == 2
    print("✓ Nach Ablauf der TTL wird frisch geholt")

    # 3) Stale-Erkennung
    time.sleep(3.1)
    assert cache.ist_stale("AAPL"), "Kurs müsste jetzt stale sein"
    print("✓ Stale-Erkennung greift: alter Kurs wird als 'hängend' erkannt")

    # 4) Batch
    def fake_batch(tickers):
        return {t: Kurswert(t, preis=100.0, zeit=time.time(), quelle="batch") for t in tickers}
    res = cache.hole_batch(["MSFT", "NVDA", "AMD"], fake_batch)
    assert len(res) == 3
    res2 = cache.hole_batch(["MSFT", "NVDA", "AMD"], fake_batch)  # jetzt aus Cache
    print(f"✓ Batch-Abruf: 3 geholt, beim 2. Mal aus Cache. Statistik: {cache.statistik()}")

    # 5) Schwelle PRO QUELLE (Gerhard, 28.07.2026)
    c2 = KursCache(ttl_sekunden=1, stale_max_sekunden=120,
                   stale_pro_quelle={"finnhub_ws": 2, "yfinance": 3600})
    jetzt = time.time()
    with c2._lock:
        c2._store["TICK"] = Kurswert("TICK", 10.0, jetzt - 30, quelle="finnhub_ws")
        c2._store["LANGSAM"] = Kurswert("LANGSAM", 10.0, jetzt - 30, quelle="yfinance")
        c2._store["UNBEKANNT"] = Kurswert("UNBEKANNT", 10.0, jetzt - 30, quelle="")
    assert c2.ist_stale("TICK"), "WebSocket: 30 s Stille müssen stale sein"
    assert not c2.ist_stale("LANGSAM"), "yfinance: 30 s dürfen NICHT stale sein"
    assert not c2.ist_stale("UNBEKANNT"), "unbekannte Quelle nutzt den Rückfallwert"
    assert c2.stale_liste() == ["TICK"]
    print("✓ Schwelle je Quelle: derselbe 30 s alte Kurs ist beim WebSocket "
          "stale, bei yfinance frisch")

    print("\nAlle Cache-Tests bestanden.")
