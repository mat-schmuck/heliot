#!/usr/bin/env python3
"""Gedaechtnis fuer verschickte ntfy-Nachrichten — damit der Freitags-Putz
sie auch wieder wegraeumen kann.

Warum ueberhaupt: Am 27.07.2026 hat Mathias in der ntfy-App alte Signale
der Vorwoche vorgefunden und danach versehentlich gehandelt. Alte
Meldungen sind in einem Woechentlichen Zyklus also nicht nur Unordnung,
sondern ein echtes Geldrisiko.

Wie es geht (am 27.07.2026 an einem Wegwerf-Thema nachgemessen):
  * ntfy.sh kennt DELETE /<thema>/<kennung> — Antwort HTTP 200 mit einem
    Ereignis {"event": "message_delete", "sequence_id": ...}, das an alle
    Abonnenten geschickt wird. Die App entfernt die Nachricht daraufhin
    auch auf dem Geraet.
  * Der Server prueft die Kennung NICHT: Auch fuer laengst abgelaufene
    (der Zwischenspeicher haelt nur 12 Stunden) oder voellig erfundene
    Kennungen kommt HTTP 200 und das Loesch-Ereignis. Genau deshalb
    funktioniert dieses Verfahren: Wir merken uns die Kennungen selbst
    und koennen die ganze Woche noch am Freitag raeumen.
  * DELETE /<thema>/all wird ebenfalls angenommen (Rundumschlag). Ob die
    App das als "alles loeschen" versteht, ist nicht verbuergt — darum
    wird es nur ZUSAETZLICH geschickt, nie als einziger Weg.

Aufruf von aussen:
  python ntfy_verlauf.py --putz <thema>     alle gemerkten Nachrichten weg
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests

VERLAUF_DATEI = Path("ntfy_ids.json")


def merke(msg_id: str):
    """Kennung einer gerade verschickten Nachricht aufheben."""
    if not msg_id:
        return
    ids = _lies(VERLAUF_DATEI)
    if msg_id not in ids:
        ids.append(msg_id)
    try:
        VERLAUF_DATEI.write_text(json.dumps(ids, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"    ntfy-Verlauf nicht speicherbar: {e}")


def merke_antwort(antwort) -> str:
    """Kennung aus der Antwort von ntfy.sh ziehen und merken."""
    try:
        msg_id = (antwort.json() or {}).get("id", "")
    except Exception:
        return ""
    merke(msg_id)
    return msg_id


def putz(topic: str) -> int:
    """Loescht alle gemerkten Nachrichten des Themas. Liefert die Anzahl."""
    if not topic:
        print("⚠ Kein ntfy-Thema angegeben — nichts zu räumen.")
        return 0
    ids = _lies(VERLAUF_DATEI)

    weg, fehler = 0, 0
    for msg_id in ids:
        try:
            r = requests.delete(f"https://ntfy.sh/{topic}/{msg_id}", timeout=20)
            if r.status_code < 400:
                weg += 1
            else:
                fehler += 1
        except Exception:
            fehler += 1

    # Rundumschlag obendrauf: erwischt womoeglich auch Meldungen aus der
    # Zeit vor diesem Gedaechtnis (z. B. Mathias' Altbestand vom 27.07.).
    try:
        requests.delete(f"https://ntfy.sh/{topic}/all", timeout=20)
    except Exception:
        pass

    try:
        VERLAUF_DATEI.write_text("[]")
    except Exception as e:
        print(f"⚠ ntfy-Verlauf nicht leerbar: {e}")

    print(f"ntfy-Putz: {weg} von {len(ids)} Meldungen gelöscht"
          + (f", {fehler} Fehlschläge" if fehler else "")
          + "; Verlauf geleert.")
    return weg


def _lies(pfad) -> list:
    # utf-8-sig statt der Standardkodierung: Auf Windows schreiben viele
    # Werkzeuge eine Byte-Reihenfolge-Marke an den Anfang, und json.loads
    # scheitert daran wortlos — die Liste waere dann still leer, und die
    # Kennungen des Laufs verschwaenden unbemerkt. Aufgefallen beim Test
    # der Vereinigung am 28.07.2026.
    try:
        daten = json.loads(Path(pfad).read_text(encoding="utf-8-sig"))
        return daten if isinstance(daten, list) else []
    except Exception:
        return []


def vereine(sicherung) -> int:
    """Kennungen aus einer Sicherung mit der Datei im Repo VEREINEN.

    Gebaut nach dem Ausfall vom 28.07.2026: Die Abendwache hatte ihre
    Meldungen sauber verschickt, scheiterte am Ende aber beim
    Zurueckschreiben — 'git pull --rebase' fand einen Konflikt in
    ntfy_ids.json, weil waehrend des Laufs von anderer Stelle ins Repo
    geschrieben worden war. Der ganze Lauf wurde rot gemeldet, und die
    Kennungen des Abends waren weg. Folge: Der Freitags-Putz haette
    genau diese Meldungen NICHT vom Handy raeumen koennen — und alte
    Signale in der App sind kein Schoenheitsfehler, sondern das, wonach
    Mathias am 27.07. versehentlich gehandelt hat.

    Ein Konflikt ist hier ohnehin unsinnig: Die Datei ist eine LISTE von
    Kennungen. Beide Seiten haben angehaengt, also gehoeren beide Seiten
    hinein. Genau das macht diese Funktion, und der Workflow braucht
    danach kein Rebase mehr."""
    im_repo = _lies(VERLAUF_DATEI)
    meine = _lies(sicherung)
    zusammen = list(im_repo)
    neu = 0
    for kennung in meine:
        if kennung not in zusammen:
            zusammen.append(kennung)
            neu += 1
    try:
        VERLAUF_DATEI.write_text(json.dumps(zusammen, indent=2))
    except Exception as e:
        print(f"⚠ ntfy-Verlauf nicht schreibbar: {e}")
        return 0
    print(f"ntfy-Verlauf vereint: {len(im_repo)} im Repo, {len(meine)} aus "
          f"diesem Lauf, {neu} davon neu, jetzt {len(zusammen)} gesamt.")
    return neu


def main():
    ap = argparse.ArgumentParser(description="ntfy-Meldungen der Woche wegräumen")
    ap.add_argument("--putz", metavar="THEMA", default=None,
                    help="Alle gemerkten Meldungen dieses Themas löschen")
    ap.add_argument("--vereinen", metavar="DATEI", default=None,
                    help="Kennungen aus dieser Sicherung mit ntfy_ids.json "
                         "vereinen (konfliktfreies Zurückschreiben)")
    args = ap.parse_args()
    if args.vereinen:
        vereine(args.vereinen)
        return
    if not args.putz:
        sys.exit("Bitte --putz <thema> oder --vereinen <datei> angeben.")
    putz(args.putz)


if __name__ == "__main__":
    main()
