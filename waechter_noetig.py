#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MUSS EINE WACHE GESTARTET WERDEN?
=================================
Die Bedingung fuer den Waechter-Hueter — als eigene, pruefbare Datei,
genau wie scan_noetig.py fuer den Nachtscan.

DAS PROBLEM, das er loest
    Am 06.08.2026 fiel die Tagwache mitten im Handel aus (GitHub-
    Stoerung, kein Rechner). Bis zum naechsten Morgen wachte niemand,
    und niemand hat es gemerkt. Ein Termin um 09:28 New Yorker Zeit
    genuegt nicht: Faellt er aus, ist der ganze Handelstag blind.

WARUM DER HUETER EIN EIGENER ABLAUF SEIN MUSS
    Mathias' Einwand vom 07.08.2026, und er trifft: Wuerde man einfach
    watcher.yml alle sechs Minuten anstossen, geriete jeder Anstoss in
    dessen concurrency-Gruppe und wuerde dort den WARTENDEN Lauf
    verdraengen. Genau dieser Wartende ist aber die
    Schlussstunden-Wache, die um 15:26 New Yorker Zeit angestossen wird
    und uebernimmt, sobald GitHub die Tagwache nach sechs Stunden
    abschiesst. Der Huerter haette sie also weggeworfen — und zwar
    ausgerechnet im letzten, wichtigsten Handelsabschnitt.

    Deshalb hat der Hueter eine EIGENE concurrency-Gruppe, fasst die des
    Waechters nie an und startet nur dann etwas, wenn dort GAR NICHTS
    ist: kein laufender und kein wartender Lauf. Eine wartende
    Schlussstunden-Wache zaehlt ausdruecklich als "ist da".

Rueckgabe ueber GITHUB_OUTPUT: noetig=ja/nein und dauerwache=<Minuten>.

Aufruf:
    python waechter_noetig.py             im Arbeitsablauf
    python waechter_noetig.py --selbsttest
"""

import argparse
import json
import os
import sys
from datetime import datetime

# Laeufe in diesen Zustaenden gelten als "da" — auch die wartenden.
LEBT = ("queued", "in_progress", "waiting", "requested", "pending")

# Unter so vielen Minuten Restzeit lohnt kein Start mehr.
#
# ZWEI MINUTEN, und die Zahl ist begruendet statt geraten (Mathias'
# Frage vom 07.08.2026: "Warum hoeren wir fuenf Minuten vor Ende auf?").
# Vorher standen hier fuenf, aus dem Bauch. Das war falsch, denn
# ausgerechnet die letzten Minuten sind die wichtigsten: Ab 15:54 New
# Yorker Zeit prueft der Waechter die SCHLUSSBESTAETIGUNG fuer Gap and
# Go (kurz_vor_schluss in breakout_watcher.py), und die Schlussauktion
# allein macht rund sechs Prozent des Tagesvolumens aus. Ein Riegel bei
# fuenf Minuten haette den Neustart genau in diesem Fenster verhindert.
#
# Warum ueberhaupt eine Untergrenze: Ein Lauf braucht gemessene 28
# Sekunden, bis er das erste Mal Kurse prueft (18 s GitHub-Ruestzeit,
# 8,6 s fuer die Tagesdaten aller Aktien, 1 s fuer die Stromverbindungen).
# Unter zwei Minuten bliebe davon zu wenig uebrig, um noch etwas zu
# sehen.
MINDESTREST = 2


def ny_jetzt():
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("America/New_York"))


def handelszeit(jetzt=None):
    """Regulaerer Handel in New York? 09:30 bis 16:00, Montag bis
    Freitag. Feiertage kennt die Pruefung nicht — an einem Feiertag
    startet sie hoechstens eine Wache, die von selbst feststellt, dass
    nichts zu tun ist."""
    j = jetzt or ny_jetzt()
    if j.weekday() >= 5:
        return False
    minuten = j.hour * 60 + j.minute
    return 9 * 60 + 30 <= minuten < 16 * 60


def restminuten(jetzt=None):
    j = jetzt or ny_jetzt()
    return max(0, 16 * 60 - (j.hour * 60 + j.minute))


def wache_da(laeufe):
    """Laeuft oder wartet eine Wache? Der wartende Lauf zaehlt MIT —
    das ist die Schlussstunden-Wache, die nicht verdraengt werden darf."""
    return any(r.get("status") in LEBT for r in laeufe)


def entscheide(laeufe, jetzt=None):
    """Rueckgabe: (noetig, dauerwache, begruendung)."""
    j = jetzt or ny_jetzt()
    if not handelszeit(j):
        return False, 0, "außerhalb der Handelszeit"
    if wache_da(laeufe):
        wieviele = sum(1 for r in laeufe if r.get("status") in LEBT)
        return False, 0, f"{wieviele} Wache(n) laufen oder warten bereits"
    rest = restminuten(j)
    if rest < MINDESTREST:
        return False, 0, f"nur noch {rest} Minuten bis zum Schluss"
    return True, rest, f"KEINE Wache da, {rest} Minuten bis zum Schluss"


def hole_laeufe(repo, anzahl=10):
    """Oeffentliche Schnittstelle, ohne Schluessel."""
    import urllib.request
    url = (f"https://api.github.com/repos/{repo}/actions/workflows/"
           f"watcher.yml/runs?per_page={anzahl}")
    bitte = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "heliot-huter"})
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

    print("Muss eine Wache gestartet werden? Selbsttest")
    mitten = datetime(2026, 8, 7, 11, 0, tzinfo=NY)

    p("11:00 an einem Freitag ist Handelszeit", handelszeit(mitten))
    p("09:29 ist noch keine Handelszeit",
      not handelszeit(datetime(2026, 8, 7, 9, 29, tzinfo=NY)))
    p("16:00 ist keine Handelszeit mehr",
      not handelszeit(datetime(2026, 8, 7, 16, 0, tzinfo=NY)))
    p("Samstag ist keine Handelszeit",
      not handelszeit(datetime(2026, 8, 8, 11, 0, tzinfo=NY)))

    # --- Der Kern: was zaehlt als "Wache ist da"? ------------------------
    laeuft = [{"status": "in_progress", "conclusion": None}]
    n, d, g = entscheide(laeuft, mitten)
    p("Läuft eine Wache, wird nichts gestartet", not n, g)

    # DER FALL, um den es Mathias ging: Die Schlussstunden-Wache wartet
    # hinter der Tagwache. Sie darf NICHT verdraengt werden.
    wartet = [{"status": "in_progress", "conclusion": None},
              {"status": "pending", "conclusion": None}]
    n, d, g = entscheide(wartet, mitten)
    p("Eine WARTENDE Schlussstunden-Wache zählt als vorhanden", not n, g)

    nur_wartend = [{"status": "queued", "conclusion": None}]
    n, d, g = entscheide(nur_wartend, mitten)
    p("Auch ein Lauf, der nur auf einen Rechner wartet, zählt", not n, g)

    fertig = [{"status": "completed", "conclusion": "failure"},
              {"status": "completed", "conclusion": "success"}]
    n, d, g = entscheide(fertig, mitten)
    p("Nur fertige Läufe: es wird gestartet", n, g)
    p("Dauerwache reicht genau bis zum Schluss", d == 300, f"{d} Minuten")

    n, d, g = entscheide([], mitten)
    p("Gar keine Läufe: es wird gestartet", n and d == 300, g)

    # DIE LETZTEN MINUTEN SIND DIE WICHTIGSTEN: Ab 15:54 New Yorker Zeit
    # prueft der Waechter die Schlussbestaetigung fuer Gap and Go. Ein
    # Neustart muss dort noch moeglich sein (Mathias, 07.08.2026).
    n, d, g = entscheide(fertig, datetime(2026, 8, 7, 15, 54, tzinfo=NY))
    p("Um 15:54 wird noch gestartet — Gap-and-Go-Schlussfenster",
      n and d == 6, g)

    n, d, g = entscheide(fertig, datetime(2026, 8, 7, 15, 58, tzinfo=NY))
    p("Zwei Minuten vor Schluss: gerade noch", n and d == 2, g)

    n, d, g = entscheide(fertig, datetime(2026, 8, 7, 15, 59, tzinfo=NY))
    p("Eine Minute vor Schluss lohnt nicht mehr (28 s Rüstzeit)", not n, g)

    n, d, g = entscheide(fertig, datetime(2026, 8, 7, 15, 50, tzinfo=NY))
    p("Zehn Minuten vor Schluss selbstverständlich", n and d == 10, g)

    n, d, g = entscheide(fertig, datetime(2026, 8, 7, 3, 0, tzinfo=NY))
    p("Nachts wird nichts gestartet", not n, g)

    print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles bestanden.")
    return 1 if fehler else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selbsttest", action="store_true")
    args = ap.parse_args()
    if args.selbsttest:
        return selbsttest()

    repo = os.environ.get("GITHUB_REPOSITORY", "mat-schmuck/heliot")
    try:
        laeufe = hole_laeufe(repo)
    except Exception as e:
        # NICHTS TUN im Zweifel. Anders als beim Nachtscan waere ein
        # ueberfluessiger Start hier schaedlich: Er belegte die
        # concurrency-Gruppe des Waechters und koennte die wartende
        # Schlussstunden-Wache verdraengen. In sechs Minuten wird
        # ohnehin wieder nachgesehen.
        print(f"Abfrage fehlgeschlagen ({type(e).__name__}: {e}) — "
              f"es wird NICHTS gestartet, nächster Blick in sechs Minuten.")
        laeufe, noetig, dauer, grund = [], False, 0, "Abfrage fehlgeschlagen"
    else:
        noetig, dauer, grund = entscheide(laeufe)

    print(f"New York {ny_jetzt():%H:%M} — {grund}")
    print("=> " + (f"Wache wird gestartet ({dauer} Minuten)" if noetig
                   else "nichts zu tun"))
    ausgabe = os.environ.get("GITHUB_OUTPUT")
    if ausgabe:
        with open(ausgabe, "a", encoding="utf-8") as f:
            f.write("noetig=" + ("ja" if noetig else "nein") + "\n")
            f.write(f"dauerwache={dauer}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
