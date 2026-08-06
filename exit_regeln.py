#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EXIT-REGELWERK — systemweit, fuer alle Muster (Gerhard, 05.08.2026)
====================================================================
Portiert aus seinem exit_regeln.py. Die Logik ist unveraendert; geaendert
sind die Anbindung (Einstellungen und Schwellenvergleich aus config.py)
und die Kommentare. Dazu kommt die Zuordnung der strukturellen
Bruchpunkte je Muster, die bei ihm nur als Tabelle im Dokument stand.

DAS GRUNDPRINZIP, und es dreht die bisherige Denkweise um
    Der Stop kommt NICHT aus einem Risikobudget. Er steht aus dem CHART
    fest, an dem Punkt, wo das Muster strukturell gebrochen ist — dort
    also, wo die These widerlegt ist, die den Einstieg begruendet hat.

        stop = max(struktureller Bruchpunkt, Einstieg × 0,90)

    Die zehn Prozent sind eine Obergrenze, nie das Ziel. Sie greifen
    nur, wenn der Strukturpunkt weiter weg liegt oder das Muster keinen
    liefert.

    Warum so herum: Ein prozentualer Stop ist willkuerlich, er hat mit
    der Aktie nichts zu tun. Der Strukturpunkt sagt etwas aus. Wird er
    unterschritten, war die Annahme falsch — egal ob das drei oder neun
    Prozent kostet. Bulkowski beschreibt genau dieses Vorgehen, Darvas'
    ganze Methode beruht darauf.

ZWEI PRAEZISIERUNGEN
    SCHLUSSKURS, nicht Docht: Ein Bruch zaehlt erst, wenn ein
    Schlusskurs unter dem Strukturpunkt liegt. Sonst wirft normales
    Tagesrauschen saubere Positionen hinaus.
    Der Stop wandert MIT, aber nur nach oben: Bildet sich eine neue,
    hoehere Struktur, wird deren Unterkante zum neuen Stop. Nie zurueck
    (Darvas' Box-Stacking).

DIE DREI EBENEN
    1  Stop = struktureller Bruchpunkt, gedeckelt bei zehn Prozent
    2  A) Stop auf Einstand  B) Teilverkauf bei 20 %  C) Rest trailen
    3  Ausnahme: 20 % in unter drei Wochen, dann acht Wochen halten und
       Stufe B aussetzen

    Die Verzahnung von Stufe B und Ebene 3 bleibt in Prosa mehrdeutig —
    deshalb steht sie hier als Code.

QUELLEN DER ZAHLEN: Minervini (Stop 6 bis 8 %, nie ueber 10 %; Trail
ueber MA21 und MA50), O'Neil und IBD (20 bis 25 % Gewinnmitnahme,
8-Wochen-Halteregel, Round-Trip-Verbot), Bulkowski, Darvas, Weinstein.
Alles Ausgangswerte fuer die Messung, keine gemessenen Optima.

Aufruf:
    python exit_regeln.py --selbsttest
"""

import argparse
import sys
from dataclasses import dataclass

from config import CFG as _ALLE, mind_erreicht

CFG = _ALLE["exit"]


# ---------------------------------------------------------------------------
# Der strukturelle Bruchpunkt je Muster (Gerhards Tabelle, Ebene 1)
# ---------------------------------------------------------------------------

# Welcher Wert aus dem Musterfund ist der Bruchpunkt? Der Schluessel ist
# die Bezeichnung, wie sie in den Meldungen steht.
STRUKTURPUNKT = {
    "Darvas Box":                  "Boxboden; wandert mit jeder neuen, höheren Box nach oben",
    "Rectangle Top":               "Unterkante der Range",
    "Cup & Handle":                "Tief des Handles",
    "Cup & Handle (Wochenbasis)":  "Tief des Handles",
    "VCP":                         "Tief der letzten, engsten Kontraktion",
    "High & Tight Flag":           "Tief der Flagge nach dem Fahnenmast",
    "Lücken-Bestätigungstag":      "Tief des Lücken-Tages",
    "Crash-Support":               "Unterkante der Unterstützungszone",
    "Red-to-Green":                "Schlusskurs fällt unter den Vortagesschluss",
    "Shakeout-Spring":             "Spring-Tief",
}


def strukturpunkt_beschreibung(strategie):
    """Wo sitzt der Bruchpunkt bei diesem Muster? Nur Text, fuer Meldungen
    und Protokoll. Unbekannte Muster liefern None — dann greift der
    Zehn-Prozent-Deckel."""
    return STRUKTURPUNKT.get(strategie)


# ---------------------------------------------------------------------------
# Der Zustand, den die Regeln brauchen
# ---------------------------------------------------------------------------

@dataclass
class Position:
    """Genau die Felder, die eine Positionsverwaltung liefern muss."""
    symbol: str
    einstieg: float                    # Kaufpunkt
    einstieg_index: int                # Handelstag-Zaehler beim Einstieg
    struktur_stop: float               # Bruchpunkt aus dem Muster
    hoechstkurs: float = 0.0
    teilverkauft: bool = False
    halteregel_aktiv: bool = False
    aktueller_stop: float = 0.0
    strategie: str = ""


# ---------------------------------------------------------------------------
# Ebene 1: der Stop
# ---------------------------------------------------------------------------

def berechne_initialen_stop(einstieg, struktur_bruchpunkt):
    """Der Strukturpunkt gewinnt, solange er innerhalb des Deckels liegt.

    Rueckgabe: (stop, quelle) mit quelle 'struktur' oder 'deckel'."""
    deckel = einstieg * (1 - CFG["stop_deckel_pct"])
    if struktur_bruchpunkt is None or struktur_bruchpunkt < deckel:
        return round(deckel, 2), "deckel"
    return round(struktur_bruchpunkt, 2), "struktur"


def ist_stop_gebrochen(schlusskurs, stop):
    """Nur ein SCHLUSSKURS darunter loest aus, kein Docht."""
    return schlusskurs < stop


def ziehe_stop_nach(aktueller_stop, neuer_struktur_punkt):
    """Box-Stacking: mit neuen, hoeheren Strukturen mitwandern, nie zurueck."""
    if neuer_struktur_punkt is None:
        return aktueller_stop
    return max(aktueller_stop, round(neuer_struktur_punkt, 2))


# ---------------------------------------------------------------------------
# Ebene 3: die Halteregel
# ---------------------------------------------------------------------------

def pruefe_halteregel(pos, kurs, aktueller_index, markt_im_aufwaertstrend=True):
    """Die Acht-Wochen-Regel. Steigt eine Aktie binnen drei Wochen um
    20 %, zeigt das laut O'Neil, dass Institutionelle einsammeln — genau
    diese Titel machen spaeter das Vielfache. Dann wird der Teilverkauf
    ausgesetzt.

    Ausdrueckliche Einschraenkung aus den Quellen: gilt nur im
    Marktaufwaertstrend."""
    if pos.halteregel_aktiv:
        return True
    if not markt_im_aufwaertstrend:
        return False
    if aktueller_index - pos.einstieg_index > CFG["schnellstarter_tage"]:
        return False                   # Fenster vorbei
    return mind_erreicht(kurs / pos.einstieg - 1, CFG["schnellstarter_pct"])


def halteregel_laeuft_noch(pos, aktueller_index):
    if not pos.halteregel_aktiv:
        return False
    return (aktueller_index - pos.einstieg_index) < CFG["halteregel_tage"]


def ist_round_trip(pos, schlusskurs):
    """Auch waehrend der Halteregel darf ein dicker Gewinn nicht komplett
    verpuffen. Zurueck auf den Einstieg ist selbst ein Verkaufssignal."""
    if not pos.halteregel_aktiv:
        return False
    hatte_gewinn = mind_erreicht(
        pos.hoechstkurs, pos.einstieg * (1 + CFG["schnellstarter_pct"]))
    return hatte_gewinn and schlusskurs <= pos.einstieg


# ---------------------------------------------------------------------------
# Alles zusammen
# ---------------------------------------------------------------------------

def pruefe_exit(pos, schlusskurs, aktueller_index, ma21=None, ma50=None,
                neuer_struktur_punkt=None, markt_im_aufwaertstrend=True,
                trail_schnell=True):
    """Eine offene Position gegen ALLE Regeln pruefen, in der richtigen
    Reihenfolge.

    Rueckgabe: (aktion, begruendung, Position). Die Aktion ist eine von
      'halten', 'stop_raus', 'round_trip_raus', 'teilverkauf',
      'trail_raus'."""
    pos.hoechstkurs = max(pos.hoechstkurs, schlusskurs)

    if neuer_struktur_punkt is not None:
        pos.aktueller_stop = ziehe_stop_nach(pos.aktueller_stop,
                                             neuer_struktur_punkt)

    gewinn = schlusskurs / pos.einstieg - 1
    r_abstand = pos.einstieg - pos.struktur_stop
    gewinn_in_r = ((schlusskurs - pos.einstieg) / r_abstand
                   if r_abstand > 0 else 0)

    # 1. Der Stop hat immer Vorrang.
    if ist_stop_gebrochen(schlusskurs, pos.aktueller_stop):
        return ("stop_raus",
                f"Schluss {schlusskurs:.2f} unter Stop {pos.aktueller_stop:.2f}",
                pos)

    # 2. Halteregel pruefen und gegebenenfalls scharf stellen.
    if not pos.halteregel_aktiv and pruefe_halteregel(
            pos, schlusskurs, aktueller_index, markt_im_aufwaertstrend):
        pos.halteregel_aktiv = True

    # 3. Round Trip greift auch WAEHREND der Halteregel.
    if ist_round_trip(pos, schlusskurs):
        return ("round_trip_raus",
                "Gewinn auf den Einstieg zurückgefallen", pos)

    # 4. Stufe A: Stop auf Einstand.
    if (mind_erreicht(gewinn_in_r, CFG["breakeven_ab_r"])
            or mind_erreicht(gewinn, CFG["breakeven_ab_pct"])):
        if pos.aktueller_stop < pos.einstieg:
            pos.aktueller_stop = round(pos.einstieg, 2)

    # 5. Stufe B: Teilverkauf — ausgesetzt, solange die Halteregel laeuft.
    if not pos.teilverkauft and mind_erreicht(gewinn,
                                              CFG["teilverkauf_ab_pct"]):
        if not halteregel_laeuft_noch(pos, aktueller_index):
            pos.teilverkauft = True
            return ("teilverkauf",
                    f"+{gewinn*100:.1f} % erreicht, "
                    f"{CFG['teilverkauf_anteil']*100:.0f} % verkaufen", pos)

    # 6. Stufe C: den Rest ueber die gleitende Linie trailen.
    trail_ma = ma21 if trail_schnell else ma50
    tage = (CFG["trail_ma_schnell"] if trail_schnell
            else CFG["trail_ma_langsam"])
    if pos.teilverkauft and trail_ma is not None and schlusskurs < trail_ma:
        return "trail_raus", f"Schluss unter dem {tage}-Tage-Schnitt", pos

    return "halten", "keine Exit-Bedingung erfüllt", pos


# ---------------------------------------------------------------------------
# Selbsttest — Gerhards acht Tests, plus zwei eigene
# ---------------------------------------------------------------------------

def selbsttest() -> int:
    fehler = []

    def pruefe(name, bedingung, zusatz=""):
        print(f"  {'ok  ' if bedingung else 'FEHL'} {name}"
              + (f" — {zusatz}" if zusatz else ""))
        if not bedingung:
            fehler.append(name)

    print("Exit-Regelwerk, Selbsttest")

    # 1 — Stop mit Deckel
    s, q = berechne_initialen_stop(100.0, 95.0)
    pruefe("Struktur gewinnt innerhalb der zehn Prozent",
           s == 95.0 and q == "struktur", f"Stop {s} ({q})")
    s, q = berechne_initialen_stop(100.0, 82.0)
    pruefe("Deckel greift bei weit entferntem Strukturpunkt",
           s == 90.0 and q == "deckel", f"Stop {s} ({q})")
    s, q = berechne_initialen_stop(100.0, None)
    pruefe("Ohne Strukturpunkt greift der Deckel",
           s == 90.0 and q == "deckel")

    # 2 — Schlusskurs statt Docht
    pruefe("Ein Docht darüber löst nicht aus",
           not ist_stop_gebrochen(95.5, 95.0))
    pruefe("Ein Schluss darunter löst aus", ist_stop_gebrochen(94.9, 95.0))

    # 3 — Box-Stacking
    pruefe("Stop wandert mit der höheren Box mit",
           ziehe_stop_nach(95.0, 103.0) == 103.0)
    pruefe("Stop geht nie zurück nach unten",
           ziehe_stop_nach(103.0, 98.0) == 103.0)

    # 4 — normaler Verlauf
    pos = Position("NORMAL", 100.0, 0, 95.0, aktueller_stop=95.0)
    aktion, _, pos = pruefe_exit(pos, 120.0, 30, ma21=112.0)
    pruefe("Teilverkauf bei plus 20 Prozent, langsam erreicht",
           aktion == "teilverkauf", aktion)
    pruefe("Stufe A hat den Stop auf Einstand gezogen",
           pos.aktueller_stop == 100.0, f"{pos.aktueller_stop}")

    # 5 — Schnellstarter
    pos = Position("SCHNELL", 100.0, 0, 95.0, aktueller_stop=95.0)
    aktion, _, pos = pruefe_exit(pos, 125.0, 10, ma21=115.0)
    pruefe("Halteregel wird scharf", pos.halteregel_aktiv is True)
    pruefe("Teilverkauf ist dadurch ausgesetzt",
           aktion == "halten" and not pos.teilverkauft, aktion)
    aktion, _, pos = pruefe_exit(pos, 130.0, 45, ma21=120.0)
    pruefe("Nach acht Wochen greift der Teilverkauf nach",
           aktion == "teilverkauf", aktion)

    # 6 — Round Trip
    pos = Position("ROUNDTRIP", 100.0, 0, 95.0, aktueller_stop=95.0)
    pruefe_exit(pos, 125.0, 8, ma21=115.0)
    aktion, _, pos = pruefe_exit(pos, 100.0, 20, ma21=105.0)
    pruefe("Verpuffter Gewinn wirft trotz Halteregel hinaus",
           aktion == "round_trip_raus", aktion)

    # 7 — Abwärtsmarkt
    pos = Position("BAER", 100.0, 0, 95.0, aktueller_stop=95.0)
    aktion, _, pos = pruefe_exit(pos, 125.0, 10, ma21=115.0,
                                 markt_im_aufwaertstrend=False)
    pruefe("Im Abwärtsmarkt greift die Halteregel nicht",
           pos.halteregel_aktiv is False)
    pruefe("Dann verkauft Stufe B ganz normal",
           aktion == "teilverkauf", aktion)

    # 8 — Stop hat Vorrang
    pos = Position("STOPP", 100.0, 0, 95.0, aktueller_stop=95.0)
    aktion, _, _ = pruefe_exit(pos, 94.0, 5, ma21=98.0)
    pruefe("Der Stop wird zuerst geprüft", aktion == "stop_raus", aktion)

    # 9 — der Gleitkomma-Grenzfall, um den es ging
    pos = Position("GRENZE", 100.0, 0, 95.0, aktueller_stop=95.0)
    aktion, _, _ = pruefe_exit(pos, 120.0, 30, ma21=112.0)
    pruefe("Exakt plus 20 Prozent löst den Teilverkauf aus",
           aktion == "teilverkauf",
           f"120/100-1 = {120.0/100.0-1!r}")

    # 10 — jedes Muster hat einen Bruchpunkt
    fehlend = [s for s in ("Darvas Box", "Rectangle Top", "VCP",
                           "High & Tight Flag", "Cup & Handle",
                           "Cup & Handle (Wochenbasis)",
                           "Lücken-Bestätigungstag", "Red-to-Green",
                           "Shakeout-Spring", "Crash-Support")
               if not strukturpunkt_beschreibung(s)]
    pruefe("Für jedes Muster ist ein Bruchpunkt hinterlegt",
           not fehlend, ", ".join(fehlend) if fehlend else "alle zehn")

    print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles bestanden.")
    return 1 if fehler else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Exit-Regelwerk, Ebene 1 bis 3.")
    ap.add_argument("--selbsttest", action="store_true")
    args = ap.parse_args()
    sys.exit(selbsttest() if args.selbsttest else ap.print_help() or 0)
