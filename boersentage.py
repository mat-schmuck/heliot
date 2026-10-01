#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BOERSENTAGE: an welchen Tagen die New Yorker Boerse handelt
===========================================================
Gerhards Antwort 1 vom 01.10.2026: "An US-Boersenfeiertagen wird der Reiter
Berichte NICHT geleert. Der letzte Handelstag bleibt lesbar bis zum naechsten
Handelstag um 14 Uhr, genau wie uebers Wochenende."

Der Reiter Berichte braucht dafuer auch Tage in der Zukunft und in der
Vergangenheit, nicht nur das Heute, das handelskalender.py beim Datenanbieter
erfragt (Mathias' Entscheid vom 07.09.2026 gilt dem Waechter am Morgen; daran
aendert sich nichts). Die Feiertage werden deshalb hier nach den Regeln der
NYSE GERECHNET, nicht in einer Tabelle gepflegt: Es gibt nichts nachzutragen,
solange die Regeln gelten.

DIE REGELN (NYSE Rule 7.2, Stand 2026)
    Neujahr               1. Jaenner; faellt er auf einen Sonntag, ist der
                          Montag frei; auf einen Samstag: KEIN Ersatztag
                          (der 31. Dezember schliesst das Geschaeftsjahr)
    Martin Luther King    dritter Montag im Jaenner
    Washington            dritter Montag im Februar
    Karfreitag            Freitag vor dem Ostersonntag
    Memorial Day          letzter Montag im Mai
    Juneteenth            19. Juni, seit 2022
    Unabhaengigkeitstag   4. Juli
    Labor Day             erster Montag im September
    Thanksgiving          vierter Donnerstag im November
    Weihnachten           25. Dezember
    Faellt ein Feiertag (ausser Neujahr) auf einen Samstag, ist der Freitag
    davor frei, faellt er auf einen Sonntag, der Montag danach.

WAS SICH NICHT RECHNEN LAESST: ausserplanmaessige Schliessungen, etwa ein
Staatstrauertag (zuletzt am 09.01.2025) oder ein Sturm. An so einem Tag haelt
dieses Modul den Tag fuer einen Handelstag; der Reiter Berichte wird dann wie
an jedem Handelstag um 14:00 Uhr geleert. Verkuerzte Handelstage (13:00 Uhr
New Yorker Zeit) sind Handelstage.

Aufruf:
    python boersentage.py --selbsttest
    python boersentage.py 2026           die Feiertage eines Jahres zeigen
"""

import sys
from datetime import date, timedelta


def ostersonntag(jahr: int) -> date:
    """Der Ostersonntag nach dem gregorianischen Kalender (Algorithmus nach
    Gauss in der Form von Meeus, Jones und Butcher)."""
    a = jahr % 19
    b, c = divmod(jahr, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    monat, tag = divmod(h + l - 7 * m + 114, 31)
    return date(jahr, monat, tag + 1)


def _nter_wochentag(jahr: int, monat: int, wochentag: int, n: int) -> date:
    """Der n-te Wochentag (0 = Montag) eines Monats; n = -1 heisst der letzte."""
    if n > 0:
        erster = date(jahr, monat, 1)
        return erster + timedelta(days=(wochentag - erster.weekday()) % 7 + 7 * (n - 1))
    folgemonat = date(jahr + (monat == 12), monat % 12 + 1, 1)
    letzter = folgemonat - timedelta(days=1)
    return letzter - timedelta(days=(letzter.weekday() - wochentag) % 7)


def _beobachtet(tag: date) -> date:
    """Samstag wird zum Freitag davor, Sonntag zum Montag danach."""
    if tag.weekday() == 5:
        return tag - timedelta(days=1)
    if tag.weekday() == 6:
        return tag + timedelta(days=1)
    return tag


def feiertage(jahr: int) -> dict:
    """{Datum: Name} der Tage, an denen die NYSE im Jahr geschlossen ist,
    ohne Wochenenden."""
    raus = {}
    neujahr = date(jahr, 1, 1)
    if neujahr.weekday() == 6:
        raus[neujahr + timedelta(days=1)] = "Neujahr"
    elif neujahr.weekday() < 5:
        raus[neujahr] = "Neujahr"
    raus[_nter_wochentag(jahr, 1, 0, 3)] = "Martin Luther King Day"
    raus[_nter_wochentag(jahr, 2, 0, 3)] = "Washington's Birthday"
    raus[ostersonntag(jahr) - timedelta(days=2)] = "Karfreitag"
    raus[_nter_wochentag(jahr, 5, 0, -1)] = "Memorial Day"
    if jahr >= 2022:
        raus[_beobachtet(date(jahr, 6, 19))] = "Juneteenth"
    raus[_beobachtet(date(jahr, 7, 4))] = "Unabhängigkeitstag"
    raus[_nter_wochentag(jahr, 9, 0, 1)] = "Labor Day"
    raus[_nter_wochentag(jahr, 11, 3, 4)] = "Thanksgiving"
    raus[_beobachtet(date(jahr, 12, 25))] = "Weihnachten"
    return raus


_CACHE: dict = {}


def feiertag(tag: date) -> str | None:
    """Der Name des Feiertags oder None."""
    if tag.year not in _CACHE:
        _CACHE[tag.year] = feiertage(tag.year)
    return _CACHE[tag.year].get(tag)


def ist_handelstag(tag: date) -> bool:
    """Montag bis Freitag und kein Feiertag der NYSE."""
    return tag.weekday() < 5 and feiertag(tag) is None


def naechster_handelstag(tag: date) -> date:
    """Der erste Handelstag NACH dem Tag."""
    t = tag + timedelta(days=1)
    while not ist_handelstag(t):
        t += timedelta(days=1)
    return t


def letzter_handelstag(tag: date) -> date:
    """Der Tag selbst, wenn er ein Handelstag ist, sonst der letzte davor."""
    t = tag
    while not ist_handelstag(t):
        t -= timedelta(days=1)
    return t


# ---------------------------------------------------------------------------
# Selbsttest (ohne Netz)
# ---------------------------------------------------------------------------

def selbsttest() -> int:
    fehler = []

    def p(name, ok, zusatz=""):
        print(f"  {'ok  ' if ok else 'FEHL'} {name}" + (f"; {zusatz}" if zusatz else ""))
        if not ok:
            fehler.append(name)

    print("BOERSENTAGE, Selbsttest")
    # Ostern gegen bekannte Daten
    for jahr, ostern in ((2024, date(2024, 3, 31)), (2025, date(2025, 4, 20)), (2026, date(2026, 4, 5)),
                         (2027, date(2027, 3, 28)), (2028, date(2028, 4, 16)), (2038, date(2038, 4, 25)),
                         (2285, date(2285, 3, 22))):
        p(f"Ostersonntag {jahr}", ostersonntag(jahr) == ostern, str(ostersonntag(jahr)))
    # Die Feiertage der NYSE, wie die Boerse sie veroeffentlicht hat
    soll = {
        2025: [date(2025, 1, 1), date(2025, 1, 20), date(2025, 2, 17), date(2025, 4, 18), date(2025, 5, 26),
               date(2025, 6, 19), date(2025, 7, 4), date(2025, 9, 1), date(2025, 11, 27), date(2025, 12, 25)],
        2026: [date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3), date(2026, 5, 25),
               date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7), date(2026, 11, 26), date(2026, 12, 25)],
        2027: [date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15), date(2027, 3, 26), date(2027, 5, 31),
               date(2027, 6, 18), date(2027, 7, 5), date(2027, 9, 6), date(2027, 11, 25), date(2027, 12, 24)],
        2028: [date(2028, 1, 17), date(2028, 2, 21), date(2028, 4, 14), date(2028, 5, 29), date(2028, 6, 19),
               date(2028, 7, 4), date(2028, 9, 4), date(2028, 11, 23), date(2028, 12, 25)],
    }
    for jahr, tage in soll.items():
        ist = sorted(feiertage(jahr))
        p(f"Feiertage {jahr} wie von der NYSE veroeffentlicht", ist == tage,
          ", ".join(str(t) for t in sorted(set(ist) ^ set(tage))))
    p("Neujahr auf einem Samstag: kein Ersatztag am 31. Dezember",
      ist_handelstag(date(2027, 12, 31)) and date(2028, 1, 1) not in feiertage(2028))
    p("Neujahr auf einem Sonntag: der Montag ist frei", feiertag(date(2034, 1, 2)) == "Neujahr")
    p("Juneteenth erst seit 2022", date(2021, 6, 18) not in feiertage(2021) and feiertag(date(2022, 6, 20)) == "Juneteenth")
    # Handelstage und Nachbarn
    p("Labor Day 2026 ist kein Handelstag, der Dienstag danach schon",
      not ist_handelstag(date(2026, 9, 7)) and ist_handelstag(date(2026, 9, 8)))
    p("Wochenende ist kein Handelstag", not ist_handelstag(date(2026, 10, 3)) and not ist_handelstag(date(2026, 10, 4)))
    p("Naechster Handelstag nach Freitag ist Montag", naechster_handelstag(date(2026, 10, 2)) == date(2026, 10, 5))
    p("Naechster Handelstag nach dem Mittwoch vor Thanksgiving ist der Freitag",
      naechster_handelstag(date(2026, 11, 25)) == date(2026, 11, 27))
    p("Naechster Handelstag nach dem Donnerstag vor Karfreitag ist der Ostermontag",
      naechster_handelstag(date(2026, 4, 2)) == date(2026, 4, 6))
    p("Letzter Handelstag am Labor Day ist der Freitag davor",
      letzter_handelstag(date(2026, 9, 7)) == date(2026, 9, 4))
    p("Letzter Handelstag an einem Handelstag ist er selbst", letzter_handelstag(date(2026, 10, 1)) == date(2026, 10, 1))
    print("\nAlles bestanden." if not fehler else f"\n{len(fehler)} Fehler.")
    return 1 if fehler else 0


if __name__ == "__main__":
    if "--selbsttest" in sys.argv:
        sys.exit(selbsttest())
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        for t, n in sorted(feiertage(int(sys.argv[1])).items()):
            print(f"{t:%d.%m.%Y}; {n}")
        sys.exit(0)
    print(__doc__)
