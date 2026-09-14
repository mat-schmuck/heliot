#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IST EINE NEUE NACHTTABELLE FUER DEN SCANNER FAELLIG?
=====================================================
Der Ablauf scanner_daten.yml startet nach JEDEM Lauf des Nachtscans. Der
wird von cron-job.org alle zehn Minuten angestossen und endet meist nach
wenigen Sekunden, weil der faellige Scan laengst gelaufen ist (siehe
scan_noetig.py). Diese Pruefung entscheidet ebenso in Sekunden, ob der
teure Teil laufen muss, und braucht dafuer nur die Standardbibliothek.

DIE REGEL: Die Scanner-Tabelle nimmt ihr RS aus rs_universum.json, das der
Nachtscan baut. Gebaut wird, wenn es noch keine Tabelle gibt oder wenn das
RS-Universum seit dem letzten Bau neu ist. scanner_stand.json merkt sich
dafuer den Bauzeitpunkt des RS-Universums, mit dem sie gerechnet wurde.
Verglichen wird dieser Eintrag Zeichen fuer Zeichen, ohne Zeitzonen.

Rueckgabe ueber GITHUB_OUTPUT: noetig=ja oder noetig=nein.

Aufruf:
    python scanner_noetig.py [--erzwingen]
    python scanner_noetig.py --selbsttest
"""

import argparse
import json
import os
import sys

RS_DATEI = "rs_universum.json"
STAND_DATEI = "scanner_stand.json"


def _lies(pfad):
    try:
        with open(pfad, encoding="utf-8-sig") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def noetig(rs, stand, erzwingen=False):
    """(ja oder nein, Grund) aus dem RS-Universum und dem Stand der Tabelle."""
    if erzwingen:
        return True, "von Hand erzwungen"
    rs_stand = (rs or {}).get("gebaut_am")
    if not rs_stand:
        return False, "kein RS-Universum im Repo, ohne RS wird nicht gebaut"
    if not stand:
        return True, "noch keine Scanner-Tabelle"
    alt = (((stand or {}).get("quellen") or {}).get("rs") or {}).get("stand")
    if alt != rs_stand:
        return True, f"RS-Universum vom {rs_stand} ist neu, die Tabelle rechnete mit {alt}"
    return False, f"die Tabelle rechnete schon mit dem RS-Universum vom {rs_stand}"


def selbsttest() -> int:
    fehler = []

    def p(name, ok, zusatz=""):
        print(f"  {'ok  ' if ok else 'FEHL'} {name}" + (f"; {zusatz}" if zusatz else ""))
        if not ok:
            fehler.append(name)

    print("Scanner-Tabelle faellig, Selbsttest")
    rs = {"gebaut_am": "2026-09-14T22:06:41", "status": "ok"}
    p("Ohne Tabelle wird gebaut", noetig(rs, {})[0] is True)
    p("Neues RS-Universum: bauen", noetig(rs, {"quellen": {"rs": {"stand": "2026-09-13T22:06:41"}}})[0] is True)
    p("Tabelle schon mit diesem RS-Universum: nicht bauen",
      noetig(rs, {"quellen": {"rs": {"stand": "2026-09-14T22:06:41"}}})[0] is False)
    p("Ohne RS-Universum wird nicht gebaut", noetig({}, {})[0] is False)
    p("Erzwingen baut immer", noetig(rs, {"quellen": {"rs": {"stand": "2026-09-14T22:06:41"}}}, erzwingen=True)[0] is True)
    grund = noetig(rs, {"quellen": {"rs": {"stand": "2026-09-13T22:06:41"}}})[1]
    p("Der Grund nennt beide Staende", "2026-09-14T22:06:41" in grund and "2026-09-13T22:06:41" in grund, grund)
    print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles bestanden.")
    return 1 if fehler else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Ist eine neue Scanner-Tabelle faellig?")
    ap.add_argument("--erzwingen", action="store_true")
    ap.add_argument("--selbsttest", action="store_true")
    args = ap.parse_args()
    if args.selbsttest:
        return selbsttest()
    ja, grund = noetig(_lies(RS_DATEI), _lies(STAND_DATEI), args.erzwingen)
    print(("Scanner-Tabelle faellig: " if ja else "Scanner-Tabelle nicht faellig: ") + grund)
    ausgabe = os.environ.get("GITHUB_OUTPUT")
    if ausgabe:
        with open(ausgabe, "a", encoding="utf-8") as f:
            f.write(f"noetig={'ja' if ja else 'nein'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
