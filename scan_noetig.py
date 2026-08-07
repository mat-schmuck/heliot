#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IST DER FAELLIGE NACHTSCAN SCHON ERLEDIGT?
===========================================
Die Bedingung fuer den Wiederanlauf des Nachtscans — als eigene Datei,
nicht als eingebettetes Skript im Arbeitsablauf. Grund: Ein Python-Block
in einer YAML-Datei ist weder pruefbar noch lesbar, und beim ersten
Versuch am 07.08.2026 hat er die YAML-Struktur zerlegt.

WOZU DAS GEBRAUCHT WIRD
    Am 06.08.2026 hatte GitHub Actions eine schwere Stoerung. Der
    Nachtscan um 18:00 New Yorker Zeit bekam keinen Rechner und fiel
    aus; am naechsten Morgen war die Kaufpunkte-Mappe zwei Tage alt.
    Bei EINEM Termin am Tag heisst ein Ausfall: 24 Stunden blind.

    cron-job.org kann selbst nichts pruefen — es schickt eine Anfrage
    und sieht die Antwort nicht an. Also wird der Ablauf oefter
    angestossen, und DIESE Pruefung entscheidet in wenigen Sekunden, ob
    der teure Teil ueberhaupt laufen muss.

GEMESSEN WIRD GEGEN DEN TERMIN, NICHT GEGEN EIN ALTER. Eine Regel wie
"letzter Erfolg hoechstens 20 Stunden alt" hat ein Loch: Wurde tagsueber
von Hand nachgeholt, gilt der naechste Ausfall stundenlang als frisch
(Mathias, 07.08.2026).

Rueckgabe ueber GITHUB_OUTPUT: noetig=ja oder noetig=nein.

Aufruf:
    python scan_noetig.py                     im Arbeitsablauf
    python scan_noetig.py --selbsttest
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

SCAN_STUNDE_NY = 18


def letzter_termin(jetzt=None):
    """Der letzte Zeitpunkt, zu dem ein Nachtscan faellig war.
    18:00 New York, Sonntag bis Freitag — samstags gibt es keinen."""
    from zoneinfo import ZoneInfo
    ny = ZoneInfo("America/New_York")
    j = (jetzt or datetime.now(ny)).astimezone(ny)
    t = j.replace(hour=SCAN_STUNDE_NY, minute=0, second=0, microsecond=0)
    if t > j:
        t -= timedelta(days=1)
    while t.weekday() == 5:
        t -= timedelta(days=1)
    return t


def termin_erfuellt(laeufe, termin, eigener_lauf=""):
    """Gab es NACH dem Termin einen geglueckten Lauf? Der eigene zaehlt
    nicht mit — er laeuft ja gerade und ist noch ohne Ergebnis."""
    grenze = termin.astimezone(timezone.utc)
    for r in laeufe:
        if str(r.get("id")) == str(eigener_lauf):
            continue
        if r.get("conclusion") != "success":
            continue
        wann = datetime.fromisoformat(
            str(r.get("created_at")).replace("Z", "+00:00"))
        if wann >= grenze:
            return True
    return False


def hole_laeufe(repo, anzahl=15):
    """Oeffentliche Schnittstelle, ohne Schluessel — das Repo ist
    oeffentlich, zum Lesen braucht es keine Anmeldung."""
    import urllib.request
    url = (f"https://api.github.com/repos/{repo}/actions/workflows/"
           f"scanner.yml/runs?per_page={anzahl}")
    bitte = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "heliot-pruefung"})
    with urllib.request.urlopen(bitte, timeout=30) as a:
        return json.loads(a.read().decode("utf-8")).get("workflow_runs", [])


def selbsttest() -> int:
    from zoneinfo import ZoneInfo
    NY = ZoneInfo("America/New_York")
    fehler = []

    def p(name, bedingung, zusatz=""):
        print(f"  {'ok  ' if bedingung else 'FEHL'} {name}"
              + (f" — {zusatz}" if zusatz else ""))
        if not bedingung:
            fehler.append(name)

    print("Ist der fällige Scan erledigt? Selbsttest")

    t = letzter_termin(datetime(2026, 8, 7, 3, 0, tzinfo=NY))
    p("Vor 18:00 gilt der Termin von gestern", (t.day, t.hour) == (6, 18),
      f"{t:%d.%m. %H:%M}")
    t = letzter_termin(datetime(2026, 8, 7, 19, 0, tzinfo=NY))
    p("Nach 18:00 gilt der von heute", (t.day, t.hour) == (7, 18),
      f"{t:%d.%m. %H:%M}")
    t = letzter_termin(datetime(2026, 8, 9, 3, 0, tzinfo=NY))
    p("Samstag hat keinen Termin, es gilt Freitag", (t.day, t.hour) == (7, 18),
      f"{t:%d.%m. %H:%M}")

    termin = letzter_termin(datetime(2026, 8, 7, 18, 10, tzinfo=NY))
    nachher = [{"id": 1, "conclusion": "success",
                "created_at": "2026-08-07T22:00:30Z"}]
    p("Ein geglückter Lauf nach dem Termin erfüllt ihn",
      termin_erfuellt(nachher, termin))

    # GENAU DAS LOCH der alten Alters-Regel: Handlauf am Morgen.
    vorher = [{"id": 1, "conclusion": "success",
               "created_at": "2026-08-07T06:38:00Z"}]
    p("Ein Handlauf von morgens erfüllt den Abendtermin NICHT",
      not termin_erfuellt(vorher, termin))

    gescheitert = [{"id": 1, "conclusion": "failure",
                    "created_at": "2026-08-07T22:00:30Z"}]
    p("Ein gescheiterter Lauf erfüllt nichts",
      not termin_erfuellt(gescheitert, termin))

    p("Der eigene Lauf zählt nicht mit",
      not termin_erfuellt(nachher, termin, eigener_lauf="1"))
    p("Ein fremder Lauf mit anderer Kennung zählt",
      termin_erfuellt(nachher, termin, eigener_lauf="999"))
    p("Ohne Läufe ist nichts erfüllt", not termin_erfuellt([], termin))
    laufend = [{"id": 2, "conclusion": None,
                "created_at": "2026-08-07T22:00:30Z"}]
    p("Ein noch laufender Lauf erfüllt den Termin nicht",
      not termin_erfuellt(laufend, termin))

    print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles bestanden.")
    return 1 if fehler else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selbsttest", action="store_true")
    args = ap.parse_args()
    if args.selbsttest:
        return selbsttest()

    repo = os.environ.get("GITHUB_REPOSITORY", "mat-schmuck/heliot")
    eigener = os.environ.get("GITHUB_RUN_ID", "")
    erzwingen = os.environ.get("ERZWINGEN", "").strip().lower() in (
        "ja", "true", "1")

    termin = letzter_termin()
    try:
        laeufe = hole_laeufe(repo)
        erledigt = termin_erfuellt(laeufe, termin, eigener)
    except Exception as e:
        # Im Zweifel SCANNEN. Ein ueberfluessiger Scan kostet Minuten,
        # ein ausgelassener kostet einen ganzen Handelstag.
        print(f"Abfrage fehlgeschlagen ({type(e).__name__}: {e}) — "
              f"im Zweifel wird gescannt.")
        erledigt = False

    noetig = erzwingen or not erledigt
    print(f"Termin: {termin:%d.%m. %H:%M} New York")
    print(f"schon erledigt: {erledigt}; erzwungen: {erzwingen}")
    print("=> " + ("wird gescannt" if noetig else "nichts zu tun, Ende"))

    ausgabe = os.environ.get("GITHUB_OUTPUT")
    if ausgabe:
        with open(ausgabe, "a", encoding="utf-8") as f:
            f.write("noetig=" + ("ja" if noetig else "nein") + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
