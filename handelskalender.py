#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HANDELT DIE NEW YORKER BOERSE HEUTE UEBERHAUPT?
==============================================
Ein Boersenkalender, den niemand pflegen muss: Gefragt wird der
Datenanbieter selbst (Twelve Data, Endpunkt /market_state).

DAS PROBLEM, das dieses Modul loest (Mathias, 07.09.2026, Labor Day)
    Der Waechter kannte bis dahin nur Wochentag und Uhrzeit. Am Labor
    Day startete er deshalb um 09:28 New Yorker Zeit, meldete
    "Boersenstatus: offen" und schickte um 09:30 die Exit-Befunde des
    Nachtlaufs aufs Handy. Erst der erste Kursabruf zeigte, dass es
    keine heutigen Kurse gibt (pruefe_handelstag), also 43 Runden lang
    "Keine einzige Kurszeile von heute", danach Ende. Alles, was NICHT
    an heutigen Kursen haengt, war da laengst hinausgegangen.

    pruefe_handelstag bleibt als zweite Linie bestehen: Sie faengt auch
    haengende Kursquellen, von denen kein Kalender etwas weiss. Dieses
    Modul zieht die Erkenntnis nur VOR die Eroeffnung.

WARUM DER DATENANBIETER UND KEINE EIGENE FEIERTAGSTABELLE
    Mathias' Entscheid vom 07.09.2026. Die neun US-Boersenfeiertage
    liessen sich zwar rechnen, aber die Tabelle waere von Hand zu
    pflegen, sobald ein Staatsbegraebnis, ein Sturm oder eine neue
    Regel dazwischenkommt. Der Anbieter weiss das ohnehin, und der
    Abruf kostet einen einzigen Credit je Tag.

WIE DIE ANTWORT GEDEUTET WIRD (am 07.09.2026 echt gemessen)
    Die Antwort je Boerse:
        {"name": "NYSE", "code": "XNYS", "country": "United States",
         "is_market_open": false, "time_to_open": "18:01:44",
         "time_to_close": "00:00:00", "time_after_open": "00:00:00"}

    Gemessen am Labor Day um 15:28 New Yorker Zeit: time_to_open
    "18:01:44", also bis zur Eroeffnung am naechsten Morgen um 09:30.
    An einem gewoehnlichen Handelstag stuende dort um 09:28 schlicht
    "00:02:00".

    Daraus die Regel:
        offen laut Dienst          -> heute wird gehandelt
        sonst jetzt + time_to_open -> faellt das auf HEUTE, wird heute
                                      noch gehandelt; faellt es auf
                                      einen spaeteren Tag, ist heute
                                      Schluss (Feiertag, oder der
                                      verkuerzte Handel ist vorbei)

    Das Format traegt Stunden ueber 23 hinaus: Eine Abfrage aller 140
    Boersen am selben Tag lieferte als groessten Wert "36:00:59", und
    KEINE einzige Antwort, die sich nicht als HH:MM:SS lesen liess.
    Deshalb genuegt das schlichte Zerlegen in drei Zahlen.

VORSICHT IST DIE GANZE HALTUNG DIESES MODULS
    Es sagt NUR dann "heute kein Handel", wenn die Antwort eindeutig
    ist. Fehlt der Schluessel, antwortet der Dienst nicht, ist die
    Antwort unlesbar oder ist der Handelstag ohnehin schon vorbei,
    kommt None zurueck: keine Aussage, und alles laeuft wie zuvor. Ein
    falsches "geschlossen" waere der teuerste denkbare Fehler — es
    kostete einen ganzen Handelstag.

Aufruf:
    python handelskalender.py                 einmal fragen und zeigen
    python handelskalender.py --selbsttest    Deutung ohne Netz pruefen
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

MARKET_STATE_URL = "https://api.twelvedata.com/market_state"

# New York Stock Exchange nach ISO 10383. Der MIC ist eindeutig — der
# Name "NYSE" liefert drei Eintraege (XNYS, XASE, ARCX), was nur
# unnoetig zu deuten waere. NASDAQ hat dieselben Feiertage, ein
# zweiter Abruf brachte also keine zusaetzliche Sicherheit.
MIC = "XNYS"

# Nach dem Schlussgong sagt "oeffnet erst morgen" nichts mehr darueber,
# ob HEUTE gehandelt wurde. Ab dieser Uhrzeit gibt es deshalb keine
# Aussage mehr.
SCHLUSS_MINUTE = 16 * 60

# Bleibt der Dienst stumm, wird nicht bei jedem Prueftakt neu gefragt
# (der Waechter prueft alle zwei Sekunden), sondern erst nach dieser
# Frist.
NEUVERSUCH_SEKUNDEN = 600

# Gemerkt wird je Prozess und je Tag: Handelstage aendern sich nicht
# im Minutentakt.
_gemerkt = {"tag": None, "antwort": None, "zeitpunkt": 0.0, "grund": ""}


def ny_jetzt():
    """Jetzt in New York — oder None, wenn die Zeitzone fehlt."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        return None


def dauer_sekunden(text):
    """'18:01:44' -> 64904. Stunden ueber 23 sind erlaubt ('36:00:59').

    None bei allem, was nicht genau so aussieht — lieber keine Aussage
    als eine geratene."""
    m = re.fullmatch(r"\s*(\d{1,4}):([0-5]\d):([0-5]\d)\s*", str(text or ""))
    if not m:
        return None
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))


def deute(eintrag: dict, jetzt) -> tuple:
    """Deutet EINEN market_state-Eintrag. Liefert (handelstag, Grund).

    handelstag ist True, False oder None (keine Aussage)."""
    if not isinstance(eintrag, dict):
        return None, "Antwort des Dienstes nicht lesbar"

    if eintrag.get("is_market_open") is True:
        return True, "die Börse ist laut Datenanbieter gerade offen"

    minuten = jetzt.hour * 60 + jetzt.minute
    if minuten >= SCHLUSS_MINUTE:
        return None, "nach Handelsschluss sagt der Datenanbieter nichts über heute"

    rest = dauer_sekunden(eintrag.get("time_to_open"))
    if rest is None:
        return None, "der Datenanbieter nennt keine lesbare Zeit bis zur Eröffnung"

    eroeffnung = jetzt + timedelta(seconds=rest)
    if eroeffnung.date() == jetzt.date():
        return True, (f"die Börse öffnet heute um {eroeffnung:%H:%M} "
                      f"New Yorker Zeit")
    return False, (f"laut Datenanbieter wird heute nicht mehr gehandelt, "
                   f"die nächste Eröffnung ist am {eroeffnung:%d.%m.} um "
                   f"{eroeffnung:%H:%M} New Yorker Zeit")


def _hole(api_key: str, zeitgrenze: int = 15):
    """Rohe Antwort des Dienstes fuer unseren MIC, oder None."""
    url = (MARKET_STATE_URL + "?"
           + urllib.parse.urlencode({"code": MIC, "apikey": api_key}))
    bitte = urllib.request.Request(
        url, headers={"User-Agent": "heliot-handelskalender"})
    with urllib.request.urlopen(bitte, timeout=zeitgrenze) as a:
        d = json.loads(a.read().decode("utf-8"))
    if isinstance(d, list):
        return d[0] if d else None
    if isinstance(d, dict) and d.get("code") and d.get("message"):
        return None                 # Fehlermeldung des Dienstes
    return d if isinstance(d, dict) else None


def handelstag(jetzt=None, api_key=None, hole=None) -> bool:
    """Wird heute in New York gehandelt? True, False oder None.

    Das Ergebnis wird je Tag EINMAL geholt und danach im Speicher
    gemerkt. Kam keine Aussage zustande, wird nach NEUVERSUCH_SEKUNDEN
    noch einmal gefragt — der Dienst kann kurz stolpern, und eine
    fehlende Aussage soll den ganzen Tag nicht festschreiben."""
    jetzt = jetzt or ny_jetzt()
    if jetzt is None:
        return None

    heute = jetzt.date().isoformat()
    frisch = (_gemerkt["tag"] == heute
              and (_gemerkt["antwort"] is not None
                   or time.time() - _gemerkt["zeitpunkt"] < NEUVERSUCH_SEKUNDEN))
    if frisch:
        return _gemerkt["antwort"]

    if api_key is None:
        api_key = (os.environ.get("TWELVE_DATA_API_KEY") or "").strip()
    hole = hole or _hole

    antwort, grund = None, "ohne TWELVE_DATA_API_KEY keine Auskunft"
    if api_key:
        try:
            antwort, grund = deute(hole(api_key), jetzt)
        except Exception as e:
            antwort = None
            grund = f"Datenanbieter nicht erreichbar ({type(e).__name__})"

    _gemerkt.update(tag=heute, antwort=antwort, zeitpunkt=time.time(),
                    grund=grund)
    return antwort


def letzter_grund() -> str:
    """Die Begruendung zur zuletzt geholten Auskunft."""
    return _gemerkt.get("grund") or ""


def kein_handel_text() -> str:
    """Der Satz, den Waechter und Hueter melden, aus EINER Hand.

    Ohne Begruendung bleibt es beim nackten Befund — ein baumelnder
    Gedankenstrich vor dem Nichts liest sich schlecht."""
    g = letzter_grund()
    return "kein Handelstag" + (" \u2014 " + g if g else "")


def vergessen():
    """Gemerkte Auskunft verwerfen (fuer Pruefzweige)."""
    _gemerkt.update(tag=None, antwort=None, zeitpunkt=0.0, grund="")


def selbsttest() -> int:
    """Prueft die Deutung an gerechneten Faellen, ohne Netz."""
    from zoneinfo import ZoneInfo
    ny = ZoneInfo("America/New_York")
    fehler = []

    def p(name, bedingung, zusatz=""):
        print(f"  {'ok  ' if bedingung else 'FEHL'} {name}"
              + (f" — {zusatz}" if zusatz else ""))
        if not bedingung:
            fehler.append(name)

    print("Handelskalender: Selbsttest der Deutung")

    p("18:01:44 sind 64904 Sekunden", dauer_sekunden("18:01:44") == 64904)
    p("36:00:59 wird gelesen (über 24 Stunden)",
      dauer_sekunden("36:00:59") == 36 * 3600 + 59)
    p("00:00:00 ist null", dauer_sekunden("00:00:00") == 0)
    p("Unsinn liefert None", dauer_sekunden("1 day, 18:01:44") is None)
    p("Leer liefert None", dauer_sekunden("") is None)
    p("None liefert None", dauer_sekunden(None) is None)

    # --- Der gemessene Feiertag: Labor Day, 07.09.2026 -------------------
    feiertag = datetime(2026, 9, 7, 15, 28, tzinfo=ny)
    echt = {"name": "NYSE", "code": "XNYS", "is_market_open": False,
            "time_to_open": "18:01:44", "time_to_close": "00:00:00",
            "time_after_open": "00:00:00"}
    a, g = deute(echt, feiertag)
    p("Die echt gemessene Feiertagsantwort heißt: kein Handelstag",
      a is False, g)

    # Dieselbe Lage um 09:28, also zu der Minute, in der der Wächter
    # startet: bis zur Eroeffnung am naechsten Morgen sind es 24:02.
    a, g = deute({"is_market_open": False, "time_to_open": "24:02:00"},
                 datetime(2026, 9, 7, 9, 28, tzinfo=ny))
    p("Feiertag um 09:28 wird erkannt, bevor die erste Meldung ausgeht",
      a is False, g)

    # --- Der gewoehnliche Handelstag -------------------------------------
    a, g = deute({"is_market_open": False, "time_to_open": "00:02:00"},
                 datetime(2026, 9, 8, 9, 28, tzinfo=ny))
    p("Zwei Minuten vor der Glocke ist Handelstag", a is True, g)

    a, g = deute({"is_market_open": True, "time_to_open": "00:00:00"},
                 datetime(2026, 9, 8, 11, 0, tzinfo=ny))
    p("Offene Börse ist Handelstag", a is True, g)

    # DIE MINUTE, AUF DIE ES ANKOMMT (Mathias, 07.09.2026: "diese eine
    # Minute ist genau jene, wo die meisten Alarme kommen"): Um Punkt
    # 09:30 darf NIEMALS "kein Handelstag" herauskommen, auch wenn die
    # Uhr des Dienstes eine Sekunde nachgeht.
    a, g = deute({"is_market_open": False, "time_to_open": "00:00:00"},
                 datetime(2026, 9, 8, 9, 30, tzinfo=ny))
    p("09:30:00 mit stehender Dienst-Uhr bleibt Handelstag", a is True, g)
    a, g = deute({"is_market_open": False, "time_to_open": "00:00:01"},
                 datetime(2026, 9, 8, 9, 29, 59, tzinfo=ny))
    p("Eine Sekunde vor der Glocke bleibt Handelstag", a is True, g)

    # --- Keine Aussage statt einer geratenen -----------------------------
    a, g = deute({"is_market_open": False, "time_to_open": "18:00:00"},
                 datetime(2026, 9, 8, 16, 30, tzinfo=ny))
    p("Nach Handelsschluss keine Aussage", a is None, g)
    a, g = deute({"is_market_open": False, "time_to_open": "morgen früh"},
                 datetime(2026, 9, 8, 9, 28, tzinfo=ny))
    p("Unlesbare Zeitangabe: keine Aussage", a is None, g)
    a, g = deute(None, datetime(2026, 9, 8, 9, 28, tzinfo=ny))
    p("Gar keine Antwort: keine Aussage", a is None, g)
    a, g = deute({"is_market_open": False}, datetime(2026, 9, 8, 9, 28, tzinfo=ny))
    p("Antwort ohne time_to_open: keine Aussage", a is None, g)

    # --- Der verkuerzte Handelstag (Heiligabend, Tag nach Thanksgiving) --
    a, g = deute({"is_market_open": False, "time_to_open": "20:30:00"},
                 datetime(2026, 11, 27, 13, 0, tzinfo=ny))
    p("Verkürzter Handelstag: nach 13 Uhr ist Schluss", a is False, g)
    a, g = deute({"is_market_open": True, "time_to_open": "00:00:00"},
                 datetime(2026, 11, 27, 11, 0, tzinfo=ny))
    p("Verkürzter Handelstag: um 11 Uhr wird gehandelt", a is True, g)

    # --- Das Merken --------------------------------------------------------
    vergessen()
    rufe = {"n": 0}

    def zaehl_hole(api_key):
        rufe["n"] += 1
        return {"is_market_open": True, "time_to_open": "00:00:00"}

    mitten = datetime(2026, 9, 8, 11, 0, tzinfo=ny)
    handelstag(mitten, api_key="x", hole=zaehl_hole)
    handelstag(mitten, api_key="x", hole=zaehl_hole)
    handelstag(mitten, api_key="x", hole=zaehl_hole)
    p("Drei Abfragen, EIN Abruf beim Dienst", rufe["n"] == 1,
      f"{rufe['n']} Abruf(e)")

    vergessen()
    p("Ohne Schlüssel keine Aussage",
      handelstag(mitten, api_key="") is None, letzter_grund())

    vergessen()

    def stolpert(api_key):
        raise TimeoutError("Zeit abgelaufen")

    p("Netzfehler liefert keine Aussage",
      handelstag(mitten, api_key="x", hole=stolpert) is None, letzter_grund())

    print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles bestanden.")
    return 1 if fehler else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selbsttest", action="store_true")
    ap.add_argument("--schluessel", default=None,
                    help="Nur für Prüfläufe; sonst TWELVE_DATA_API_KEY")
    args = ap.parse_args()
    if args.selbsttest:
        return selbsttest()

    jetzt = ny_jetzt()
    if jetzt is None:
        print("Zeitzone nicht verfügbar — keine Aussage.")
        return 0
    antwort = handelstag(api_key=args.schluessel)
    wort = {True: "JA", False: "NEIN", None: "unbekannt"}[antwort]
    print(f"New York {jetzt:%d.%m.%Y %H:%M} — wird heute gehandelt? {wort}")
    print(f"Begründung: {letzter_grund()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
