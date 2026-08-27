"""Lebenszeichen aller Kapitel: Sieht jedes Werkzeug noch echte Daten?

WARUM ES DAS GIBT (26.08.2026, Mathias' Auftrag nach dem Insider-Ausfall):
Der Insider-Scanner hat zwoelf Tage lang taeglich gemeldet, er habe null
Kaeufe gefunden. Das stimmte auch - er hat aber nie einen einzigen
Datensatz zu sehen bekommen, weil er den Tagesindex des laufenden Tages
abfragte, den es noch gar nicht gibt. Von aussen war "nichts gefunden"
nicht von "gar nicht hingesehen" zu unterscheiden. Genau diese
Unterscheidung ist die Aufgabe dieser Datei.

GEPRUEFT WIRD DESHALB NICHT, ob eine Datei frisch geschrieben wurde -
das war sie jeden Tag. Gefragt wird, wann zuletzt ECHTE DATEN
hereinkamen: Kaufpunkte in der Mappe, Kurven im Volumenspeicher,
Kaeufe im Insider-Speicher, geladene ETFs im Sektor-Radar.

Die Fristen sind bewusst grosszuegig: Ein Werkzeug, das an einem ruhigen
Tag nichts findet, ist gesund. Erst wenn es TAGELANG nichts sieht,
stimmt etwas nicht. Gezaehlt wird in HANDELSTAGEN, sonst schluege jeder
Montag Alarm.

Aufruf:
  python lebenszeichen.py                 nur anzeigen
  python lebenszeichen.py --melden        bei Befund ans ntfy-Thema
"""

import argparse
import json
import os
import sys
from datetime import datetime, date, timedelta


def _json(pfad, vorgabe=None):
    try:
        with open(pfad, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return vorgabe if vorgabe is not None else {}


def _alter_stunden(pfad):
    """Wie alt ist die Datei in Stunden? None, wenn es sie nicht gibt."""
    try:
        return (datetime.now()
                - datetime.fromtimestamp(os.path.getmtime(pfad))).total_seconds() / 3600
    except OSError:
        return None


def _handelstage_her(tag, bis=None):
    """Wie viele HANDELSTAGE liegt ein Datum zurueck?

    Ohne diese Umrechnung schluege jeder Montag Alarm: Zwischen Freitag
    und Montag liegen drei Kalendertage, aber nur ein Handelstag.

    `bis` gibt es, damit die Rechnung pruefbar ist, ohne vom heutigen
    Datum abzuhaengen - eine Pruefung, die morgen anders ausgeht, ist
    keine Pruefung."""
    if not tag:
        return None
    try:
        d = date.fromisoformat(str(tag)[:10])
    except ValueError:
        return None
    ziel = bis or date.today()
    n, lauf = 0, d
    while lauf < ziel:
        lauf += timedelta(days=1)
        if lauf.weekday() < 5:
            n += 1
    return n


# ---------------------------------------------------------------------------
# Je Kapitel: was heisst hier "echte Daten"?
# ---------------------------------------------------------------------------

def _nachtscan():
    import pandas as pd
    pfad = "kaufpunkte_aktuell.xlsx"
    alter = _alter_stunden(pfad)
    if alter is None:
        return "Nachtscan", None, "Mappe fehlt ganz", True
    try:
        d = pd.read_excel(pfad)
        aktien = len(d)
        kp = 0
        for _, r in d.iterrows():
            for k in (1, 2, 3):
                s = r.get(f"KP{k} Strategie")
                if isinstance(s, str) and s.strip():
                    kp += 1
    except Exception as e:
        return "Nachtscan", None, f"Mappe unlesbar ({type(e).__name__})", True
    # Der Scan laeuft nach dem New Yorker Schluss; 80 Stunden decken auch
    # ein Wochenende ab (Freitagnacht bis Montagfrueh).
    krank = alter > 80 or aktien == 0 or kp == 0
    return ("Nachtscan", f"vor {alter:.0f} Stunden",
            f"{aktien} Aktien, {kp} Kaufpunkte", krank)


def _volumenkurven():
    d = _json("volumenkurven.json")
    kurven = d.get("aktien") or d.get("kurven") or {}
    alter = _alter_stunden("volumenkurven.json")
    krank = not kurven or (alter or 0) > 80
    stand = f"vor {alter:.0f} Stunden" if alter is not None else None
    return "Volumenkurven", stand, f"{len(kurven)} Kurven", krank


def _waechter():
    d = _json("melde_gedaechtnis.json")
    gemeldet = d.get("gemeldet", {})
    if not gemeldet:
        # Der Freitags-Putz leert das Gedaechtnis; am Montagfrueh ist es
        # regulaer leer. Das allein ist noch kein Befund.
        return "Breakout-Waechter", None, "Gedaechtnis leer (nach dem Putz normal)", False
    juengste = max(str(v)[:10] for v in gemeldet.values())
    her = _handelstage_her(juengste)
    krank = her is not None and her > 3
    return ("Breakout-Waechter", f"zuletzt {juengste}",
            f"{len(gemeldet)} Schluessel im Gedaechtnis", krank)


def _sektor():
    d = _json("sektor_radar.json")
    geladen = d.get("geladen", 0)
    gebaut = str(d.get("gebaut_am", ""))[:10]
    her = _handelstage_her(gebaut)
    # Treffer sind selten und sollen es sein (gemessen: an 26 von 60
    # Handelstagen einer). Krank ist nicht "kein Treffer", sondern
    # "keine ETFs geladen" oder "seit Tagen nicht gerechnet".
    krank = geladen < 20 or (her is not None and her > 2)
    return ("Sektor-Radar", f"gerechnet {gebaut or 'nie'}",
            f"{geladen} ETFs geladen, {len(d.get('treffer', []))} Dreher", krank)


def _insider():
    d = _json("insider_kaeufe.json")
    kaeufe = d.get("kaeufe", {})
    anzahl = sum(len(v) for v in kaeufe.values())
    juengster = None
    for liste in kaeufe.values():
        for e in liste:
            tag = str(e.get("datum", ""))[:10]
            if tag and (juengster is None or tag > juengster):
                juengster = tag
    her = _handelstage_her(juengster)
    # HIER SASS DER AUSFALL: Der Scanner schrieb taeglich brav seine
    # Datei, aber es kam nie ein Kauf herein. Gefragt wird deshalb nach
    # dem juengsten KAUF, nicht nach dem Dateidatum. Marktweit gibt es
    # taeglich rund 1.100 Form-4-Einreichungen; zwei Handelstage ohne
    # einen einzigen Kauf sind praktisch unmoeglich.
    krank = anzahl == 0 or her is None or her > 2
    return ("Insider-Scanner", f"juengster Kauf {juengster or 'keiner'}",
            f"{anzahl} Kaeufe von {len(kaeufe)} Aktien", krank)


def _termine():
    d = _json("zahlen_termine.json")
    aktien = d.get("aktien") or {}
    alter = _alter_stunden("zahlen_termine.json")
    krank = not aktien or (alter or 0) > 200
    stand = f"vor {alter:.0f} Stunden" if alter is not None else None
    return "Zahlen-Termine", stand, f"{len(aktien)} Aktien", krank


PRUEFUNGEN = [_nachtscan, _volumenkurven, _waechter, _sektor, _insider, _termine]


def pruefe():
    """Alle Kapitel durchgehen. Rueckgabe: Liste (Name, Stand, Lage, krank)."""
    raus = []
    for f in PRUEFUNGEN:
        try:
            raus.append(f())
        except Exception as e:
            raus.append((f.__name__.strip("_"), None,
                         f"Pruefung selbst gescheitert ({type(e).__name__})", True))
    return raus


def bericht(zeilen):
    """Menschenlesbar, ohne Gedankenstriche (Screenreader)."""
    text = []
    for name, stand, lage, krank in zeilen:
        marke = "STILL" if krank else "ok"
        teile = [t for t in (stand, lage) if t]
        text.append(f"{marke}: {name}; " + "; ".join(teile))
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--melden", action="store_true",
                    help="Bei Befund ans ntfy-Thema schicken")
    args = ap.parse_args()

    zeilen = pruefe()
    for z in bericht(zeilen):
        print(z)
    krank = [z for z in zeilen if z[3]]
    print(f"\n{len(krank)} von {len(zeilen)} Kapiteln ohne frische Daten.")

    if krank and args.melden:
        topic = (os.environ.get("NTFY_TOPIC") or "").strip()
        if not topic:
            print("Kein NTFY_TOPIC gesetzt, nichts geschickt.")
            return 1
        import requests
        namen = ", ".join(z[0] for z in krank)
        absaetze = []
        for i, (n, s, l, k) in enumerate(krank, 1):
            teile = [t for t in (s, l) if t]
            absaetze.append(f"{i}. {n}; " + "; ".join(teile))
        koerper = ("Diese Kapitel sehen keine frischen Daten mehr:\n"
                   + "\n".join(absaetze))
        try:
            requests.post(
                f"https://ntfy.sh/{topic}",
                data=koerper.encode("utf-8"),
                headers={"Title": f"Lebenszeichen fehlt: {namen}".encode("utf-8"),
                         "Priority": "high"}, timeout=20)
            print("Befund gemeldet.")
        except Exception as e:
            print(f"Meldung fehlgeschlagen: {e}")
            return 1
    return 1 if krank else 0


if __name__ == "__main__":
    sys.exit(main())
