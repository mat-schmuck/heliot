#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TRIGGER-LOGBUCH — jedes Signal mitschreiben, zum spaeteren Nachmessen
======================================================================
Gerhard setzt dieses Modul im Exit-Dokument vom 05.08.2026 als vorhanden
voraus: "Das Trigger-Logbuch (trigger_logbuch.py) ist dafuer NICHT
gedacht — es protokolliert Signale zur spaeteren Auswertung, unabhaengig
davon, ob wirklich gekauft wurde. Beides bleibt getrennt."

Es gab es nicht. Hier ist es, genau nach dieser Beschreibung.

DIE TRENNUNG, die er meint
    positionen.py fuehrt, was WIRKLICH gehalten wird — mit Einstiegskurs,
    Stop und Status, und nur solange die Position offen ist.
    Dieses Logbuch schreibt JEDES gemeldete Signal mit, ob gekauft wurde
    oder nicht, und behaelt es fuer immer. Nur so laesst sich hinterher
    messen, was die Regeln getaugt haetten — auch die Faelle, die man
    ausgelassen hat.

WOZU DAS GUT IST
    In fast jeder Uebergabe steht "per Mitschreiben verfeinern": bei der
    Fruehphasen-Ausnahme in Kapitel 9, bei der Halte-Pruefung, bei den
    Schwellen des Shakeout, beim Level-Score. Ohne ein Logbuch bleibt das
    ein frommer Wunsch, weil die Signale nach der Meldung verschwinden.

WAS MITGESCHRIEBEN WIRD
    Nicht nur Kuerzel und Kaufpunkt, sondern ALLE Messwerte, die zum
    Zeitpunkt der Meldung bekannt waren — Volumenverhaeltnisse,
    Lueckengroesse, Schlussposition, Basisspanne, Punktzahl. Erst damit
    laesst sich spaeter fragen "was hatten die Gewinner gemeinsam?",
    ohne die Vergangenheit neu rechnen zu muessen.

Die Datei waechst nur; nichts wird je geloescht oder umgeschrieben.

Aufruf:
    python trigger_logbuch.py --liste [Anzahl]
    python trigger_logbuch.py --auswerten          Erfolg nachmessen
    python trigger_logbuch.py --selbsttest
"""

import argparse
import json
import os
import sys
from datetime import date

DATEI = "trigger_logbuch.jsonl"


# ---------------------------------------------------------------------------
# Schreiben und lesen
# ---------------------------------------------------------------------------

def protokolliere(signal, quelle="", pfad=DATEI):
    """Ein Signal anhaengen. Nie ueberschreiben, nie loeschen.

    signal: dict mit mindestens 'ticker'. Alles Weitere wird
    uebernommen, wie es kommt — die Merkmale unterscheiden sich je
    Muster, und genau die will man spaeter auswerten koennen."""
    eintrag = {"datum": date.today().isoformat(), "quelle": quelle}
    # Nur einfache Werte; alles andere waere in JSON nicht haltbar.
    for k, v in signal.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            eintrag[k] = v
    with open(pfad, "a", encoding="utf-8") as f:
        f.write(json.dumps(eintrag, ensure_ascii=False) + "\n")
    return eintrag


def protokolliere_viele(signale, quelle="", pfad=DATEI):
    return [protokolliere(s, quelle, pfad) for s in signale]


def lies(pfad=DATEI):
    """Alle Eintraege. Kaputte Zeilen werden uebersprungen, nicht
    verworfen — eine halb geschriebene Zeile soll den Rest nicht
    unlesbar machen."""
    if not os.path.exists(pfad):
        return []
    eintraege = []
    with open(pfad, encoding="utf-8-sig") as f:
        for zeile in f:
            zeile = zeile.strip()
            if not zeile:
                continue
            try:
                eintraege.append(json.loads(zeile))
            except ValueError:
                continue
    return eintraege


def vereinen(sicherung, pfad=DATEI):
    """Zwei Staende derselben Datei zusammenfuehren.

    Notwendig wegen des Waechter-Laufs in der Cloud: Der legt vor dem
    Hochladen mit 'git reset --hard' den Serverstand hin und wuerfe die
    Zeilen dieses Laufs damit weg. Also vorher sichern, danach vereinen —
    genau wie ntfy_verlauf.py es fuer die Meldungskennungen tut.

    Die Datei wird nur angehaengt, nie umgeschrieben. Zusammenfuehren
    heisst deshalb: Serverstand behalten, alles aus der Sicherung
    anhaengen, was noch nicht Zeile fuer Zeile drinsteht. Rueckgabe:
    Anzahl der neu hinzugekommenen Zeilen."""
    def zeilen(p):
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8-sig") as f:
            return [z.rstrip("\n") for z in f if z.strip()]

    da, meine = zeilen(pfad), zeilen(sicherung)
    bekannt = set(da)
    neu = [z for z in meine if z not in bekannt]
    if neu:
        with open(pfad, "a", encoding="utf-8") as f:
            for z in neu:
                f.write(z + "\n")
    return len(neu)


# ---------------------------------------------------------------------------
# Auswerten
# ---------------------------------------------------------------------------

def auswerten(eintraege, tage=(5, 10, 20), leise=False):
    """Was ist aus den protokollierten Signalen geworden?

    Holt die Kurse ab dem Meldetag und rechnet die Entwicklung. Das ist
    dieselbe Rechnung wie in gapgo_erfolg.py, nur auf ECHTE Meldungen
    angewandt statt auf rueckgerechnete."""
    import pandas as pd
    import yfinance as yf
    from statistics import median

    mit_kaufpunkt = [e for e in eintraege if e.get("ticker")]
    if not mit_kaufpunkt:
        return {}
    ticker = sorted({e["ticker"].upper() for e in mit_kaufpunkt})
    if not leise:
        print(f"{len(mit_kaufpunkt)} Einträge über {len(ticker)} Aktien.")
    roh = yf.download(" ".join(ticker), period="2y", interval="1d",
                      group_by="ticker", progress=False, auto_adjust=False,
                      threads=True)

    je_strategie = {}
    for e in mit_kaufpunkt:
        t = e["ticker"].upper()
        try:
            d = roh[t].dropna(subset=["Close"])
        except Exception:
            continue
        nach = d[d.index >= pd.Timestamp(e["datum"])]
        if len(nach) < 2:
            continue
        start = float(nach["Close"].iloc[0])
        if start <= 0:
            continue
        strat = e.get("strategie") or e.get("quelle") or "ohne Angabe"
        eintrag = je_strategie.setdefault(strat, {n: [] for n in tage})
        for n in tage:
            if len(nach) > n:
                eintrag[n].append(float(nach["Close"].iloc[n]) / start - 1)

    ergebnis = {}
    for strat, werte in sorted(je_strategie.items()):
        ergebnis[strat] = {}
        for n in tage:
            r = werte[n]
            if r:
                ergebnis[strat][n] = {
                    "n": len(r),
                    "treffer": sum(1 for x in r if x > 0) / len(r) * 100,
                    "median": median(r) * 100,
                }
    return ergebnis


def zeige_auswertung(ergebnis, tage=(5, 10, 20)):
    if not ergebnis:
        print("Nichts auszuwerten — das Logbuch ist leer oder zu jung.")
        return
    kopf = f"{'Muster':34s}" + "".join(f"{'n/Tr%/Median':>22s}" for _ in tage)
    print(kopf)
    print(f"{'':34s}" + "".join(f"{f'nach {n} Tagen':>22s}" for n in tage))
    print("-" * len(kopf))
    for strat, werte in ergebnis.items():
        zeile = f"{strat[:33]:34s}"
        for n in tage:
            w = werte.get(n)
            zeile += (f"{w['n']:6d} {w['treffer']:5.0f} {w['median']:+8.1f}"
                      if w else f"{'—':>22s}")
        print(zeile)


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

def selbsttest() -> int:
    import tempfile
    fehler = []

    def pruefe(name, bedingung, zusatz=""):
        print(f"  {'ok  ' if bedingung else 'FEHL'} {name}"
              + (f" — {zusatz}" if zusatz else ""))
        if not bedingung:
            fehler.append(name)

    print("Trigger-Logbuch, Selbsttest")
    pfad = os.path.join(tempfile.mkdtemp(), DATEI)

    pruefe("Fehlende Datei ergibt eine leere Liste", lies(pfad) == [])

    protokolliere({"ticker": "AAA", "strategie": "Darvas Box",
                   "kaufpunkt": 42.5, "vol_ratio": 3.4},
                  quelle="waechter", pfad=pfad)
    protokolliere({"ticker": "BBB", "strategie": "VCP", "kaufpunkt": 10.0},
                  quelle="scanner", pfad=pfad)
    e = lies(pfad)
    pruefe("Zwei Einträge geschrieben und gelesen", len(e) == 2)
    pruefe("Datum und Quelle stehen dabei",
           e[0].get("datum") and e[0].get("quelle") == "waechter")
    pruefe("Die Merkmale bleiben erhalten", e[0].get("vol_ratio") == 3.4)

    # Nichts geht verloren, wenn dieselbe Aktie mehrfach meldet
    protokolliere({"ticker": "AAA", "strategie": "Rectangle Top"},
                  quelle="scanner", pfad=pfad)
    pruefe("Dieselbe Aktie darf mehrfach vorkommen", len(lies(pfad)) == 3)

    # Eine kaputte Zeile darf den Rest nicht unlesbar machen
    with open(pfad, "a", encoding="utf-8") as f:
        f.write("{kaputt\n")
    protokolliere({"ticker": "CCC"}, quelle="test", pfad=pfad)
    pruefe("Eine kaputte Zeile wird übersprungen, der Rest bleibt lesbar",
           len(lies(pfad)) == 4)

    # Nicht darstellbare Werte fliegen raus, statt das Schreiben zu sprengen
    protokolliere({"ticker": "DDD", "objekt": object()}, pfad=pfad)
    letzte = lies(pfad)[-1]
    pruefe("Nicht darstellbare Werte werden ausgelassen",
           letzte["ticker"] == "DDD" and "objekt" not in letzte)

    # --- Zusammenfuehren (Waechter-Lauf in der Cloud) ---------------------
    ordner = os.path.dirname(pfad)
    server = os.path.join(ordner, "server.jsonl")
    meine = os.path.join(ordner, "meine.jsonl")
    protokolliere({"ticker": "SRV", "strategie": "vom Server"}, pfad=server)
    protokolliere({"ticker": "GEM", "strategie": "beide"}, pfad=server)
    with open(server, encoding="utf-8") as f:
        gemeinsam = f.readlines()[-1]
    with open(meine, "w", encoding="utf-8") as f:
        f.write(gemeinsam)
    protokolliere({"ticker": "MEIN", "strategie": "nur bei mir"}, pfad=meine)

    n = vereinen(meine, server)
    ergebnis = lies(server)
    pruefe("Zusammenführen übernimmt genau die neue Zeile", n == 1, f"n={n}")
    pruefe("Der Serverstand bleibt vollständig erhalten",
           [e["ticker"] for e in ergebnis] == ["SRV", "GEM", "MEIN"],
           ", ".join(e["ticker"] for e in ergebnis))
    pruefe("Ein zweiter Durchgang ändert nichts mehr",
           vereinen(meine, server) == 0 and len(lies(server)) == 3)
    pruefe("Fehlende Sicherung ist kein Fehler",
           vereinen(os.path.join(ordner, "gibtsnicht.jsonl"), server) == 0)

    print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles bestanden.")
    return 1 if fehler else 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Signale mitschreiben und später nachmessen.")
    ap.add_argument("--liste", nargs="?", type=int, const=20, metavar="ANZAHL")
    ap.add_argument("--auswerten", action="store_true")
    ap.add_argument("--vereinen", metavar="SICHERUNG",
                    help="Gesicherten Stand in das Logbuch einarbeiten")
    ap.add_argument("--selbsttest", action="store_true")
    args = ap.parse_args()

    if args.selbsttest:
        return selbsttest()

    if args.vereinen:
        n = vereinen(args.vereinen)
        print(f"{n} Zeile(n) aus {args.vereinen} übernommen.")
        return 0

    eintraege = lies()
    if args.auswerten:
        zeige_auswertung(auswerten(eintraege))
        return 0

    print(f"{len(eintraege)} Einträge im Logbuch.")
    for e in eintraege[-(args.liste or 20):]:
        print(f"  {e.get('datum','?')}  {e.get('ticker','?'):6s} "
              f"{str(e.get('strategie',''))[:30]:30s} "
              f"Kaufpunkt {e.get('kaufpunkt','—')}  ({e.get('quelle','')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
