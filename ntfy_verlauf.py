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
    try:
        ids = json.loads(VERLAUF_DATEI.read_text()) if VERLAUF_DATEI.exists() else []
        if not isinstance(ids, list):
            ids = []
    except Exception:
        ids = []
    if msg_id not in ids:
        ids.append(msg_id)
    try:
        VERLAUF_DATEI.write_text(json.dumps(ids, indent=2))
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
    try:
        ids = json.loads(VERLAUF_DATEI.read_text()) if VERLAUF_DATEI.exists() else []
    except Exception:
        ids = []

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


def main():
    ap = argparse.ArgumentParser(description="ntfy-Meldungen der Woche wegräumen")
    ap.add_argument("--putz", metavar="THEMA", default=None,
                    help="Alle gemerkten Meldungen dieses Themas löschen")
    args = ap.parse_args()
    if not args.putz:
        sys.exit("Bitte --putz <thema> angeben.")
    putz(args.putz)


if __name__ == "__main__":
    main()
