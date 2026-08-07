#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WIEDERANLAUF — holt nach, was GitHub hat ausfallen lassen
==========================================================
Am 06.08.2026 hatte GitHub Actions von 15:22 UTC an eine schwere
Stoerung. Vier Laeufe scheiterten hintereinander mit derselben Meldung,
"The job was not acquired by Runner of type hosted": die Tagwache, die
Schlussstunden-Wache, der Alarm-Bot und der Nachtscan. Niemand hat es
gemerkt, und niemand hat es nachgeholt — die Kaufpunkte-Mappe war am
naechsten Morgen zwei Tage alt.

WARUM DIESES SKRIPT NICHT AUF GITHUB LAEUFT
    Weil es dann genau dann nicht laeuft, wenn es gebraucht wird. Ein
    Wiederholungsversuch muss von ausserhalb kommen. Er laeuft deshalb
    auf Mathias' Rechner als Windows-Aufgabe alle zehn Minuten und
    benutzt die dort angemeldete GitHub-CLI — kein Zugangsschluessel im
    Code, keiner in einer Datei.

WAS ES TUT UND WAS AUSDRUECKLICH NICHT
    Es startet einen Lauf NUR, wenn wirklich keiner da ist. Steht ein
    Lauf in der Warteschlange, geschieht NICHTS: GitHub arbeitet ihn ab,
    sobald wieder Rechner frei sind. Wer bei jedem Durchgang nachlegt,
    baut einen Stau statt einer Absicherung.

    Der Nachtscan wird nachgeholt, wenn sein TERMIN (18:00 New Yorker
    Zeit) verstrichen ist, ohne dass danach ein Lauf glueckte. Gemessen
    wird gegen den Termin, NICHT gegen ein Alter — sonst entsteht ein
    Loch: Wurde tagsueber von Hand nachgeholt und faellt der Nachtscan
    aus, waere der letzte Erfolg noch "frisch" und der Ausfall bliebe
    stundenlang unbemerkt (Mathias, 07.08.2026).
    Die Tagwache wird gestartet, wenn waehrend der Handelszeit keine
    laeuft.

ZUR VOLUMENFORMEL (Mathias' Einwand, 07.08.2026)
    Ein nachgeholter Scan mitten am Tag darf die Kurven nicht verbiegen.
    Das ist in volumen.py geloest, nicht hier: _kurve_aus_kerzen laesst
    den LAUFENDEN Handelstag grundsaetzlich aus, weil sein
    Gesamtvolumen noch nicht feststeht. Ohne diese Regel waere ein
    Nachzuegler zwischen 15:50 und 16:00 New Yorker Zeit durch die
    Halbtags-Regel geschluepft und haette die Kurve nach vorne verbogen.

Aufruf:
    python wiederanlauf.py              pruefen und notfalls nachstarten
    python wiederanlauf.py --trocken    nur berichten, nichts ausloesen
    python wiederanlauf.py --selbsttest
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

GH = r"C:\Program Files\GitHub CLI\gh.exe"
REPO = "mat-schmuck/heliot"
PROTOKOLL = "wiederanlauf-log.txt"

# Wann der Nachtscan faellig ist: 18:00 New Yorker Zeit, Sonntag bis
# Freitag (cron-job.org, "0 18 * * 0-5" — samstags gibt es keinen Lauf,
# weil freitagabends der letzte Handelstag der Woche abgeschlossen ist).
SCAN_STUNDE_NY = 18


def letzter_faelliger_scan(jetzt=None):
    """Der letzte Zeitpunkt, zu dem ein Nachtscan haette laufen sollen.

    GEGEN DEN NAECHSTEN TERMIN messen, nicht gegen ein Alter. Vorher
    stand hier "letzter Erfolg hoechstens 20 Stunden alt", und das hat
    ein Loch, das Mathias am 07.08.2026 sofort gesehen hat: Wurde ein
    Scan tagsueber von Hand nachgeholt und faellt der naechste
    Nachtscan aus, ist der letzte Erfolg nur 15,5 Stunden alt — die
    Pruefung haette geschwiegen und erst 4,6 Stunden spaeter reagiert.
    Mit dem Termin als Massstab faellt der Ausfall binnen zehn Minuten
    auf, egal was vorher war."""
    from zoneinfo import ZoneInfo
    j = (jetzt or ny_jetzt()).astimezone(ZoneInfo("America/New_York"))
    faellig = j.replace(hour=SCAN_STUNDE_NY, minute=0, second=0, microsecond=0)
    if faellig > j:
        faellig -= timedelta(days=1)
    while faellig.weekday() == 5:            # Samstag: kein Termin
        faellig -= timedelta(days=1)
    return faellig


def ny_jetzt():
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("America/New_York"))


def markt_offen(jetzt=None):
    """Regulaerer Handel? Feiertage kennt diese Pruefung nicht — an
    einem Feiertag startet sie hoechstens einen Lauf, der von selbst
    feststellt, dass nichts zu tun ist."""
    j = jetzt or ny_jetzt()
    if j.weekday() >= 5:
        return False
    minuten = j.hour * 60 + j.minute
    return 9 * 60 + 30 <= minuten < 16 * 60


def minuten_bis_schluss(jetzt=None):
    j = jetzt or ny_jetzt()
    return max(0, 16 * 60 - (j.hour * 60 + j.minute))


def laeufe(workflow, anzahl=8):
    """Die letzten Laeufe eines Arbeitsablaufs — OHNE Anmeldung.

    Bewusst ueber die oeffentliche Schnittstelle statt ueber die
    GitHub-CLI: Das Repo ist oeffentlich, zum LESEN braucht es also
    keinen Schluessel. Und die CLI ist hier nicht verfuegbar — ihre
    Anmeldung liegt in Claudes App-Container (MSIX), eine Windows-
    Aufgabe ausserhalb davon sieht sie nicht (gemessen 07.08.2026:
    dieselbe Adresse, hosts.yml aber nicht vorhanden).

    So funktioniert wenigstens das ERKENNEN immer. Nur das Nachstarten
    braucht Anmeldung — siehe starten()."""
    import urllib.request
    import urllib.error

    url = (f"https://api.github.com/repos/{REPO}/actions/workflows/"
           f"{workflow}/runs?per_page={anzahl}")
    bitte = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "heliot-wiederanlauf"})
    try:
        with urllib.request.urlopen(bitte, timeout=30) as antwort:
            roh = json.loads(antwort.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"
    return [{"databaseId": r["id"], "status": r["status"],
             "conclusion": r["conclusion"], "createdAt": r["created_at"]}
            for r in roh.get("workflow_runs", [])], None


def offen(liste):
    """Laeufe, die noch nicht fertig sind — also laufen oder warten."""
    return [r for r in liste if r["status"] in ("queued", "in_progress",
                                                "waiting", "requested",
                                                "pending")]


def letzter_erfolg(liste):
    for r in liste:
        if r["conclusion"] == "success":
            return datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00"))
    return None


def starten(workflow, felder=None, trocken=False):
    if trocken:
        return True, "(Trockenlauf, nichts ausgelöst)"
    befehl = [GH, "workflow", "run", workflow, "--repo", REPO]
    for k, v in (felder or {}).items():
        befehl += ["-f", f"{k}={v}"]
    try:
        r = subprocess.run(befehl, capture_output=True, text=True, timeout=90,
                           encoding="utf-8", errors="replace")
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    if r.returncode != 0:
        text = (r.stderr or r.stdout or "").strip()
        if "auth login" in text or "not logged" in text.lower():
            # Der haeufigste Fall, und er ist behebbar. Deshalb im Klartext
            # statt als nackte Fehlermeldung.
            return False, ("GitHub-CLI ist außerhalb von Claude nicht "
                           "angemeldet. Einmalig in einem normalen "
                           "Eingabeaufforderungs-Fenster ausführen: "
                           "gh auth login")
        return False, text[:200]
    return True, "ausgelöst"


def pruefe(trocken=False, jetzt=None):
    """Ein Durchgang. Rueckgabe: Liste von Protokollzeilen."""
    j = jetzt or ny_jetzt()
    zeilen = [f"{datetime.now():%d.%m.%Y %H:%M:%S} — New York {j:%H:%M}, "
              f"Markt {'offen' if markt_offen(j) else 'zu'}"]

    # --- Erreichbarkeit -------------------------------------------------
    daten, fehler = laeufe("scanner.yml")
    if fehler:
        zeilen.append(f"  GitHub NICHT erreichbar: {fehler}")
        zeilen.append("  Nichts unternommen — beim nächsten Durchgang wieder.")
        return zeilen

    # --- Nachtscan ------------------------------------------------------
    wartend = offen(daten)
    erfolg = letzter_erfolg(daten)
    if wartend:
        zeilen.append(f"  Nachtscan: {len(wartend)} Lauf/Läufe warten oder "
                      f"laufen — nichts nachgelegt.")
    else:
        faellig = letzter_faelliger_scan(j)
        # Der Termin gilt als erfüllt, wenn NACH ihm ein Lauf glückte.
        erfuellt = erfolg is not None and erfolg >= faellig.astimezone(timezone.utc)
        if erfuellt:
            zeilen.append(f"  Nachtscan: in Ordnung — Termin "
                          f"{faellig:%d.%m. %H:%M} New York erfüllt "
                          f"(Lauf {erfolg.astimezone(timezone.utc):%d.%m. %H:%M} UTC).")
        else:
            zeilen.append(f"  Nachtscan: Termin {faellig:%d.%m. %H:%M} "
                          f"New York NICHT erfüllt"
                          + (f" (letzter Erfolg "
                             f"{erfolg.astimezone(timezone.utc):%d.%m. %H:%M} UTC)."
                             if erfolg else " (gar kein Erfolg gefunden)."))
            ok, wie = starten("scanner.yml", trocken=trocken)
            zeilen.append(f"    nachgestartet: {wie}" if ok
                          else f"    FEHLGESCHLAGEN: {wie}")

    # --- Tagwache -------------------------------------------------------
    if not markt_offen(j):
        zeilen.append("  Wächter: außerhalb der Handelszeit, nichts zu tun.")
        return zeilen

    daten_w, fehler_w = laeufe("watcher.yml")
    if fehler_w:
        zeilen.append(f"  Wächter: Abfrage fehlgeschlagen ({fehler_w})")
        return zeilen
    wartend_w = offen(daten_w)
    if wartend_w:
        zeilen.append(f"  Wächter: {len(wartend_w)} Lauf/Läufe warten oder "
                      f"laufen — nichts nachgelegt.")
        return zeilen

    rest = minuten_bis_schluss(j)
    if rest < 5:
        zeilen.append("  Wächter: weniger als fünf Minuten bis zum Schluss, "
                      "kein Start mehr.")
        return zeilen
    zeilen.append(f"  Wächter: KEINER läuft, obwohl der Markt offen ist "
                  f"({rest} Minuten bis zum Schluss).")
    ok, wie = starten("watcher.yml", {"dauerwache": str(rest)}, trocken)
    zeilen.append(f"    nachgestartet: {wie}" if ok
                  else f"    FEHLGESCHLAGEN: {wie}")
    return zeilen


def selbsttest() -> int:
    fehler = []

    def p(name, bedingung, zusatz=""):
        print(f"  {'ok  ' if bedingung else 'FEHL'} {name}"
              + (f" — {zusatz}" if zusatz else ""))
        if not bedingung:
            fehler.append(name)

    from zoneinfo import ZoneInfo
    NY = ZoneInfo("America/New_York")
    print("Wiederanlauf, Selbsttest")

    p("Freitag 10:00 New York gilt als offen",
      markt_offen(datetime(2026, 8, 7, 10, 0, tzinfo=NY)))
    p("Freitag 09:29 gilt als zu",
      not markt_offen(datetime(2026, 8, 7, 9, 29, tzinfo=NY)))
    p("Freitag 16:00 gilt als zu",
      not markt_offen(datetime(2026, 8, 7, 16, 0, tzinfo=NY)))
    p("Samstag 10:00 gilt als zu",
      not markt_offen(datetime(2026, 8, 8, 10, 0, tzinfo=NY)))
    p("Restzeit um 15:30 sind 30 Minuten",
      minuten_bis_schluss(datetime(2026, 8, 7, 15, 30, tzinfo=NY)) == 30)

    # Ein wartender Lauf darf NIE einen zweiten ausloesen — das ist die
    # Regel, an der sich entscheidet, ob daraus eine Absicherung oder
    # ein Stau wird.
    wartet = [{"databaseId": 1, "status": "queued", "conclusion": None,
               "createdAt": "2026-08-07T06:00:00Z"}]
    p("Ein wartender Lauf zählt als offen", len(offen(wartet)) == 1)
    p("Ein fertiger Lauf zählt nicht als offen",
      len(offen([{"databaseId": 1, "status": "completed",
                  "conclusion": "failure",
                  "createdAt": "2026-08-07T06:00:00Z"}])) == 0)

    mit_erfolg = [
        {"databaseId": 3, "status": "completed", "conclusion": "failure",
         "createdAt": "2026-08-07T06:00:00Z"},
        {"databaseId": 2, "status": "completed", "conclusion": "success",
         "createdAt": "2026-08-06T22:00:00Z"},
    ]
    e = letzter_erfolg(mit_erfolg)
    p("Der letzte ERFOLG wird gefunden, nicht der letzte Lauf",
      e is not None and e.day == 6, str(e))
    p("Ohne Erfolg kommt None",
      letzter_erfolg([{"databaseId": 1, "status": "completed",
                       "conclusion": "failure",
                       "createdAt": "2026-08-07T06:00:00Z"}]) is None)

    # --- Der Termin, nicht das Alter -------------------------------------
    # Freitag 03:00 New York: der letzte Termin war Donnerstag 18:00.
    f = letzter_faelliger_scan(datetime(2026, 8, 7, 3, 0, tzinfo=NY))
    p("Vor dem heutigen Termin gilt der von gestern",
      (f.day, f.hour) == (6, 18), f"{f:%d.%m. %H:%M}")
    # Freitag 19:00 New York: der Termin von heute 18:00 ist durch.
    f = letzter_faelliger_scan(datetime(2026, 8, 7, 19, 0, tzinfo=NY))
    p("Nach dem Termin gilt der von heute",
      (f.day, f.hour) == (7, 18), f"{f:%d.%m. %H:%M}")
    # Sonntag 03:00: Samstag hat keinen Termin, also gilt Freitag 18:00.
    f = letzter_faelliger_scan(datetime(2026, 8, 9, 3, 0, tzinfo=NY))
    p("Samstag hat keinen Termin, es gilt Freitag",
      (f.day, f.hour) == (7, 18), f"{f:%d.%m. %H:%M}")

    # DAS LOCH, das die alte Alters-Regel hatte (Mathias, 07.08.2026):
    # Ein Scan wurde tagsueber von Hand nachgeholt, der Nachtscan faellt
    # aus. Nach Alter waere der Erfolg nur 15,5 Stunden alt und die
    # Pruefung haette geschwiegen. Nach Termin faellt es sofort auf.
    faellig = letzter_faelliger_scan(datetime(2026, 8, 7, 18, 10, tzinfo=NY))
    handlauf = datetime(2026, 8, 7, 6, 38, tzinfo=timezone.utc)
    p("Handlauf von morgens erfüllt den Abendtermin NICHT",
      handlauf < faellig.astimezone(timezone.utc),
      f"Termin {faellig:%d.%m. %H:%M} NY")
    alter_std = (datetime(2026, 8, 7, 18, 10, tzinfo=NY) - handlauf).total_seconds() / 3600
    p("...obwohl er nach altem Maß mit 15,5 Stunden 'frisch' wäre",
      alter_std < 20, f"{alter_std:.1f} Stunden")
    echter = datetime(2026, 8, 7, 22, 0, 30, tzinfo=timezone.utc)
    p("Ein Lauf nach dem Termin erfüllt ihn",
      echter >= faellig.astimezone(timezone.utc))

    print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles bestanden.")
    return 1 if fehler else 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Holt nach, was GitHub hat ausfallen lassen.")
    ap.add_argument("--trocken", action="store_true",
                    help="Nur berichten, nichts auslösen")
    ap.add_argument("--selbsttest", action="store_true")
    args = ap.parse_args()
    if args.selbsttest:
        return selbsttest()

    zeilen = pruefe(trocken=args.trocken)
    for z in zeilen:
        print(z)
    try:
        with open(PROTOKOLL, "a", encoding="utf-8") as f:
            f.write("\n".join(zeilen) + "\n")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
