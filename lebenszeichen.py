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

ZWEI KAPITEL MIT NETZ (21.09.2026, Mathias: "ja, baue bitte" auf die Frage,
ob das Lebenszeichen auch den Fundament-Lauf und den Strom der Vorabwerte
pruefen soll): Beide liegen nicht im Repo, sondern als Release
(fundament-roh) und im privaten Datenrepo (vorabwerte). Der Fundament-Lauf
meldet einen Ausfall gar nicht; der Strom meldet nur Stoerungen INNERHALB
eines Laufs (SEC-Feed nicht lesbar, Modellkette ohne Antwort), nicht aber
einen Lauf, der gar nicht erst startet. Beides faengt dieses Lebenszeichen.
Ohne Netz (--ohne-netz, Gesamtpruefung) werden die zwei Kapitel nicht
geprueft und sagen das.

Aufruf:
  python lebenszeichen.py                 nur anzeigen
  python lebenszeichen.py --melden        bei Befund ans ntfy-Thema
  python lebenszeichen.py --ohne-netz     nur die Kapitel aus dem Repo
"""

import argparse
import json
import os
import sys
from datetime import datetime, date, timedelta, timezone


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


def _gewinnzonen():
    """Kapitel 12: rechnet der Nachtscan die Beobachtungen durch?

    Die Befunde-Datei wird JEDE Nacht neu geschrieben, auch wenn kein
    Befund anfaellt (leere Liste) - genau daran erkennt man den
    Unterschied zwischen 'nichts zu melden' und 'gar nicht gerechnet'."""
    b = _json("positionen.json")
    beob = sum(1 for e in (b or {}).values()
               if isinstance(e, dict) and e.get("beobachtung")
               and e.get("status") == "offen")
    d = _json("exit_befunde.json")
    if not d:
        return ("Gewinnzonen (Kapitel 12)", None,
                f"{beob} Beobachtung(en); noch nie gerechnet", beob > 0)
    her = _handelstage_her(str(d.get("gebaut_am", ""))[:10])
    krank = her is None or her > 2
    return ("Gewinnzonen (Kapitel 12)",
            f"gerechnet {str(d.get('gebaut_am', ''))[:10]}",
            f"{beob} offene Beobachtung(en), "
            f"{len(d.get('befunde', []))} Befund(e)", krank)


def _rs_universum():
    """Teil 6, Regel 2 (Gerhard, 12.09.2026): Meldung, wenn an einem
    Handelstag nicht gerechnet wurde. Dazu Regel 1 (Abdeckung) und Regel 3
    (Plausibilitaet), die das Modul selbst in die Datei schreibt."""
    d = _json("rs_universum.json")
    if not d:
        return ("RS-Universum", None, "noch nie gerechnet", True)
    tag = str(d.get("handelstag") or "")[:10]
    her = _handelstage_her(tag)
    u = d.get("universum") or {}
    pl = d.get("plausibilitaet") or {}
    lage = (f"{u.get('im_universum', 0)} Aktien im Universum, Abdeckung "
            f"{round((u.get('abdeckung') or 0) * 100, 1)} Prozent, Status {d.get('status')}"
            + ("" if pl.get("ok") else "; Plausibilitaet nicht bestanden"))
    krank = (her is None or her > 1 or d.get("status") != "ok" or not pl.get("ok"))
    return ("RS-Universum", f"Handelstag {tag or 'unbekannt'}", lage, krank)


def _sektor_rangliste():
    d = _json("sektor_rangliste.json")
    if not d:
        return ("Sektor-Rangliste", None, "noch nie gerechnet", True)
    tag = str(d.get("handelstag") or "")[:10]
    her = _handelstage_her(tag)
    n = len(d.get("liste") or [])
    krank = her is None or her > 1 or n < 30
    return ("Sektor-Rangliste", f"Handelstag {tag or 'unbekannt'}", f"{n} ETFs gereiht", krank)


def _ratings():
    d = _json("ibd_ratings.json")
    if not d:
        return ("IBD-Ratings", None, "noch nie gerechnet", True)
    gebaut = str(d.get("gebaut_am") or "")[:10]
    her = _handelstage_her(gebaut)
    a = d.get("aktien") or {}
    mit = sum(1 for e in a.values() if isinstance(e, dict) and e.get("composite") is not None)
    krank = her is None or her > 1 or d.get("status") != "ok" or mit == 0
    return ("IBD-Ratings", f"gerechnet {gebaut or 'nie'}",
            f"{len(a)} Ticker, {mit} mit Composite, Status {d.get('status')}"
            + (f" ({d.get('grund')})" if d.get("grund") else ""), krank)


# ---------------------------------------------------------------------------
# Kapitel ausserhalb des Repos (brauchen die GitHub-Schnittstelle)
# ---------------------------------------------------------------------------

GITHUB_API = "https://api.github.com/"
REPO = "mat-schmuck/heliot"
DATEN_REPO = "mat-schmuck/heliot-daten"
FUNDAMENT_NAME = "Fundament (amtliche Quartalszahlen)"
VORABWERTE_NAME = "Vorabwerte (8-K-Strom)"


class TokenFehlt(Exception):
    """Das Secret fuer ein privates Repo ist nicht gesetzt."""


def _github(pfad, token_name="GITHUB_TOKEN", roh=False, pflicht=False):
    """Ein Aufruf der GitHub-Schnittstelle. Der Token kommt aus der Umgebung
    und wird nie ausgegeben; ohne Token geht es bei oeffentlichen Repos auch,
    dann mit dem kleinen Kontingent ohne Anmeldung."""
    import requests
    token = (os.environ.get(token_name) or "").strip()
    if pflicht and not token:
        raise TokenFehlt(token_name)
    kopf = {"Accept": "application/vnd.github.raw" if roh else "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        kopf["Authorization"] = f"Bearer {token}"
    r = requests.get(GITHUB_API + pfad, headers=kopf, timeout=30)
    r.raise_for_status()
    return r.text if roh else r.json()


def _fundament(holen=None, heute=None):
    """Das amtliche Fundament (Gerhard, S3 vom 20.09.2026): Seit dem 21.09.2026
    baut fundament_phase1.yml es Montag bis Freitag abends nach dem Schluss in
    New York neu und veroeffentlicht es als Release fundament-roh-<Zeit>, das
    zugleich das als neuestes markierte Release sein muss, weil
    ibd_ratings.lade_kennzahlen releases/latest liest.
    Krank ist das Kapitel, wenn das juengste Fundament-Release mehr als einen
    Handelstag alt ist, wenn es deutlich weniger Dateien hat als das davor
    (unter 90 Prozent), oder wenn ein anderes Release als neuestes markiert ist.
    holen: Funktion(pfad) -> JSON, fuer die Pruefung ohne Netz."""
    holen = holen or (lambda pfad: _github(pfad))
    alle = holen(f"repos/{REPO}/releases?per_page=30") or []
    fund = sorted([r for r in alle if str(r.get("tag_name") or "").startswith("fundament-roh-")
                   and not r.get("draft") and r.get("published_at")],
                  key=lambda r: str(r["published_at"]), reverse=True)
    if not fund:
        return (FUNDAMENT_NAME, None, "kein veroeffentlichtes Fundament-Release gefunden", True)
    neu = fund[0]
    tag = str(neu["tag_name"])
    tag_datum = str(neu["published_at"])[:10]
    her = _handelstage_her(tag_datum, heute)
    dateien = len(neu.get("assets") or [])
    davor = len(fund[1].get("assets") or []) if len(fund) > 1 else None
    latest = holen(f"repos/{REPO}/releases/latest") or {}
    maengel = []
    if her is None or her > 1:
        maengel.append(f"seit {her} Handelstagen kein neues Fundament")
    if davor and dateien < 0.9 * davor:
        maengel.append(f"nur {dateien} Dateien statt {davor} wie im Release davor")
    if str(latest.get("tag_name") or "") != tag:
        maengel.append(f"als neuestes Release ist {latest.get('tag_name') or 'keines'} markiert, "
                       "die Ratings lesen dann nicht das Fundament")
    lage = f"Release {tag}, {dateien} Dateien" + ("; " + "; ".join(maengel) if maengel else "")
    return (FUNDAMENT_NAME, f"veroeffentlicht {tag_datum}", lage, bool(maengel))


def _vorabwerte(holen=None, jetzt=None):
    """Der Strom der Vorabwerte aus Ergebnis-8-Ks (Gerhard F15; vorabwerte_8k.py
    auf fundament-phase1, von cron-job.org werktags 06:00 bis 20:00 New York
    alle 30 Minuten angestossen). Er schreibt ins private Datenrepo:
    vorabwerte/laeufe.jsonl (eine Bilanz je Lauf) und vorabwerte/stand.json
    ("zuletzt" = juengste gesehene 8-K-Einreichung).
    Krank ist das Kapitel,
      * wenn waehrend der Laufzeiten (werktags 06:30 bis 20:30 New York) der
        letzte Lauf des Stroms mehr als drei Stunden zurueckliegt, sonst wenn er
        mehr als einen Handelstag zurueckliegt (ein Lauf, der gar nicht
        startet, meldet sich nicht selbst);
      * wenn der letzte Lauf abgebrochen ist;
      * wenn die juengste gesehene Einreichung mehr als zwei Handelstage alt
        ist (die SEC nimmt jeden Werktag Hunderte 8-Ks an).
    holen: Funktion(pfad) -> Text, fuer die Pruefung ohne Netz."""
    holen = holen or (lambda pfad: _github(f"repos/{DATEN_REPO}/contents/{pfad}",
                                           "DATEN_TOKEN", roh=True, pflicht=True))
    try:
        laeufe_text = holen("vorabwerte/laeufe.jsonl")
        stand = json.loads(holen("vorabwerte/stand.json") or "{}")
    except TokenFehlt:
        return (VORABWERTE_NAME, None, "nicht pruefbar, das Secret DATEN_TOKEN fehlt", True)
    stroeme = []
    for zeile in (laeufe_text or "").splitlines():
        try:
            d = json.loads(zeile)
        except ValueError:
            continue
        if isinstance(d, dict) and d.get("modus") == "strom" and d.get("zeit"):
            stroeme.append(d)
    jetzt = jetzt or datetime.now(timezone.utc)
    if not stroeme:
        return (VORABWERTE_NAME, None, "noch kein Lauf des Stroms verzeichnet", True)
    letzter = max(stroeme, key=lambda d: str(d["zeit"]))
    zeit = datetime.fromisoformat(str(letzter["zeit"]))
    if zeit.tzinfo is None:
        zeit = zeit.replace(tzinfo=timezone.utc)
    alter_h = (jetzt - zeit).total_seconds() / 3600
    from zoneinfo import ZoneInfo
    ny = jetzt.astimezone(ZoneInfo("America/New_York"))
    laufzeit = ny.weekday() < 5 and (6, 30) <= (ny.hour, ny.minute) <= (20, 30)
    maengel = []
    if laufzeit:
        if alter_h > 3:
            maengel.append(f"letzter Lauf vor {alter_h:.0f} Stunden, obwohl er alle 30 Minuten laufen soll")
    else:
        her_lauf = _handelstage_her(zeit.date().isoformat(), jetzt.date())
        if her_lauf is None or her_lauf > 1:
            maengel.append(f"letzter Lauf vor {her_lauf} Handelstagen")
    if letzter.get("abbruch"):
        maengel.append(f"letzter Lauf abgebrochen: {str(letzter['abbruch'])[:120]}")
    zuletzt = str(stand.get("zuletzt") or "")[:10]
    her_8k = _handelstage_her(zuletzt, jetzt.date()) if zuletzt else None
    if her_8k is None or her_8k > 2:
        maengel.append(f"seit {her_8k} Handelstagen keine neue 8-K" if her_8k is not None
                       else "noch nie eine 8-K gesehen")
    heute = jetzt.date().isoformat()
    heute_laeufe = [d for d in stroeme if str(d["zeit"])[:10] == heute]
    vorl = sum(int(d.get("vorlaeufig") or 0) + int(d.get("unsicher") or 0) for d in heute_laeufe)
    wien = zeit.astimezone(ZoneInfo("Europe/Vienna"))
    n_heute = len(heute_laeufe)
    lage = (f"juengste gesehene 8-K vom {zuletzt or 'nie'}, heute {n_heute} "
            f"{'Lauf' if n_heute == 1 else 'Laeufe'} mit {vorl} Vorabwerten"
            + ("; " + "; ".join(maengel) if maengel else ""))
    return (VORABWERTE_NAME, f"letzter Lauf {wien:%d.%m.%Y %H:%M} Wiener Zeit", lage, bool(maengel))


PRUEFUNGEN = [_nachtscan, _volumenkurven, _waechter, _sektor, _insider,
              _termine, _gewinnzonen, _rs_universum, _sektor_rangliste, _ratings]
NETZ_PRUEFUNGEN = [_fundament, _vorabwerte]


def pruefe(netz=True):
    """Alle Kapitel durchgehen. Rueckgabe: Liste (Name, Stand, Lage, krank).
    netz=False laesst die zwei Kapitel aus, die die GitHub-Schnittstelle
    brauchen; sie stehen dann als nicht geprueft da und gelten nicht als still."""
    raus = []
    for f in PRUEFUNGEN:
        try:
            raus.append(f())
        except Exception as e:
            raus.append((f.__name__.strip("_"), None,
                         f"Pruefung selbst gescheitert ({type(e).__name__})", True))
    for f, name in zip(NETZ_PRUEFUNGEN, (FUNDAMENT_NAME, VORABWERTE_NAME)):
        if not netz:
            raus.append((name, None, "ohne Netz nicht geprueft", False))
            continue
        try:
            raus.append(f())
        except Exception as e:
            raus.append((name, None, f"Pruefung selbst gescheitert ({type(e).__name__})", True))
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
    ap.add_argument("--ohne-netz", action="store_true",
                    help="Fundament und Vorabwerte auslassen (brauchen die GitHub-Schnittstelle)")
    args = ap.parse_args()

    zeilen = pruefe(netz=not args.ohne_netz)
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
