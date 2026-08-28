#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
POSITIONSVERWALTUNG — die Luecke, die Gerhard benannt hat
==========================================================
Gerhard am 05.08.2026: "Das System erkennt bisher nur EINSTIEGE. Es
weiss nicht, ob eine Position tatsaechlich gehalten wird, zu welchem
Kurs eingestiegen wurde, an welchem Datum, und wie hoch der Gewinn
aktuell ist. Alle Regeln oben brauchen genau diese Angaben."

Genau das fuehrt dieses Modul: je offener Position den Einstiegskurs,
das Datum, den aktuellen Stop, den bisherigen Hoechstkurs und den
Status. Technisch dasselbe Muster wie die Shakeout-Warteliste — eine
Datei, die ueber Tage ueberlebt.

WAS DIESES MODUL NICHT IST
    Kein Handelsprotokoll und kein Signal-Logbuch. Es fuehrt
    ausschliesslich Positionen, die WIRKLICH gehalten werden, und nur
    solange sie offen sind. Was gemeldet wurde, steht woanders.

ZWEI BETRIEBSARTEN, wie von Gerhard vorgeschlagen
    ECHT        Mathias traegt eine gekaufte Position ein, die
                Exit-Pruefung laeuft taeglich dagegen.
    BEOBACHTUNG Fuer ein gemeldetes Signal wird eine Position nur
                ANGENOMMEN, ohne dass gekauft wurde. So sammelt sich
                Erfahrung, ohne dass zuerst echtes Geld fliesst. Solche
                Eintraege sind als beobachtung=True gekennzeichnet und
                loesen nie eine Handlung aus, nur eine Meldung.

DER STOP KOMMT AUS DEM CHART, nicht aus einem Risikobudget — siehe
exit_regeln.py. Beim Eroeffnen wird deshalb der strukturelle Bruchpunkt
des jeweiligen Musters verlangt; welcher das ist, sagt
exit_regeln.STRUKTURPUNKT.

Aufruf:
    python positionen.py --liste
    python positionen.py --eroeffnen AXGN --strategie "Darvas Box" \
        --einstieg 42.50 --struktur 39.80
    python positionen.py --schliessen AXGN --grund "von Hand verkauft"
    python positionen.py --pruefen          Kurse holen und Regeln anwenden
    python positionen.py --selbsttest
"""

import argparse
import json
import os
import sys
from datetime import date

import exit_regeln
from config import CFG as _ALLE

DATEI = "positionen.json"
CFG = _ALLE["exit"]


# ---------------------------------------------------------------------------
# Datei
# ---------------------------------------------------------------------------

def laden(pfad=DATEI):
    try:
        with open(pfad, encoding="utf-8-sig") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def speichern(bestand, pfad=DATEI):
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(bestand, f, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------------------
# Eroeffnen und schliessen
# ---------------------------------------------------------------------------

def eroeffne(bestand, symbol, strategie, einstieg, struktur_punkt,
             datum=None, index=0, beobachtung=False, firma=""):
    """Eine Position aufnehmen. Der Stop wird dabei nach dem
    Grundprinzip gerechnet: struktureller Punkt, gedeckelt bei zehn
    Prozent."""
    symbol = symbol.upper()
    if symbol in bestand:
        raise SystemExit(f"{symbol} steht bereits im Bestand. Erst "
                         f"schliessen oder einen anderen Namen waehlen.")
    stop, quelle = exit_regeln.berechne_initialen_stop(einstieg,
                                                       struktur_punkt)
    bestand[symbol] = {
        "symbol": symbol, "firma": firma, "strategie": strategie,
        "einstieg": round(float(einstieg), 4),
        "einstieg_datum": datum or date.today().isoformat(),
        "einstieg_index": int(index),
        "struktur_stop": (round(float(struktur_punkt), 4)
                          if struktur_punkt is not None else None),
        "aktueller_stop": stop, "stop_quelle": quelle,
        "hoechstkurs": round(float(einstieg), 4),
        "teilverkauft": False, "halteregel_aktiv": False,
        "beobachtung": bool(beobachtung), "status": "offen",
        "verlauf": [],
    }
    return bestand


def schliesse(bestand, symbol, grund="", kurs=None):
    symbol = symbol.upper()
    if symbol not in bestand:
        raise SystemExit(f"{symbol} steht nicht im Bestand.")
    e = bestand[symbol]
    e["status"] = "geschlossen"
    e["schluss_datum"] = date.today().isoformat()
    e["schluss_grund"] = grund
    if kurs is not None:
        e["schluss_kurs"] = round(float(kurs), 4)
        e["ergebnis_pct"] = round((kurs / e["einstieg"] - 1) * 100, 2)
        abstand = e["einstieg"] - (e["struktur_stop"] or e["aktueller_stop"])
        if abstand > 0:
            e["ergebnis_r"] = round((kurs - e["einstieg"]) / abstand, 2)
    return bestand


# ---------------------------------------------------------------------------
# Die taegliche Pruefung
# ---------------------------------------------------------------------------

def als_position(eintrag):
    """Aus dem Dateieintrag das Objekt bauen, das exit_regeln erwartet."""
    return exit_regeln.Position(
        symbol=eintrag["symbol"], einstieg=eintrag["einstieg"],
        einstieg_index=eintrag["einstieg_index"],
        struktur_stop=(eintrag["struktur_stop"]
                       if eintrag["struktur_stop"] is not None
                       else eintrag["aktueller_stop"]),
        hoechstkurs=eintrag["hoechstkurs"],
        teilverkauft=eintrag["teilverkauft"],
        halteregel_aktiv=eintrag["halteregel_aktiv"],
        aktueller_stop=eintrag["aktueller_stop"],
        strategie=eintrag.get("strategie", ""))


def zurueckschreiben(eintrag, pos):
    eintrag["hoechstkurs"] = round(pos.hoechstkurs, 4)
    eintrag["teilverkauft"] = pos.teilverkauft
    eintrag["halteregel_aktiv"] = pos.halteregel_aktiv
    eintrag["aktueller_stop"] = round(pos.aktueller_stop, 2)


def pruefe_bestand(bestand, kurse, heute_index, ma21=None, ma50=None,
                   markt_im_aufwaertstrend=True):
    """Alle offenen Positionen gegen das Exit-Regelwerk pruefen.

    kurse: {Symbol: Schlusskurs}. ma21/ma50: {Symbol: Wert} oder None.
    Rueckgabe: Liste der Meldungen, je eine je ausgeloester Regel."""
    ma21, ma50 = ma21 or {}, ma50 or {}
    meldungen = []
    for symbol, e in bestand.items():
        if e.get("status") != "offen":
            continue
        # SEIT KAPITEL 12 (28.08.2026): Beobachtungen sind mit
        # 'TICKER|Zusatz' verschluesselt, weil ein Ticker mehrere
        # Kaufpunkte zugleich tragen kann (ASC|1 und ASC|2 am 19.08.).
        # Der Kurs haengt am echten Symbol, nicht am Schluessel.
        kurs = kurse.get(e.get("symbol", symbol))
        if kurs is None:
            continue
        pos = als_position(e)
        aktion, grund, pos = exit_regeln.pruefe_exit(
            pos, float(kurs), heute_index,
            ma21=ma21.get(symbol), ma50=ma50.get(symbol),
            markt_im_aufwaertstrend=markt_im_aufwaertstrend)
        zurueckschreiben(e, pos)
        if aktion != "halten":
            e["verlauf"].append({"datum": date.today().isoformat(),
                                 "aktion": aktion, "grund": grund,
                                 "kurs": round(float(kurs), 4)})
            if aktion in ("stop_raus", "round_trip_raus", "trail_raus"):
                e["status"] = "geschlossen"
                e["schluss_datum"] = date.today().isoformat()
                e["schluss_grund"] = grund
                e["schluss_kurs"] = round(float(kurs), 4)
                e["ergebnis_pct"] = round((kurs / e["einstieg"] - 1) * 100, 2)
            meldungen.append({
                "symbol": symbol, "firma": e.get("firma", ""),
                "aktion": aktion, "grund": grund, "kurs": float(kurs),
                "beobachtung": e.get("beobachtung", False),
                "gewinn_pct": round((kurs / e["einstieg"] - 1) * 100, 1),
            })
    return meldungen


def melde_text(m):
    """Eine Zeile nach denselben Regeln wie ueberall: Kuerzel und Firma
    zuerst, Strichpunkt zwischen verschiedenen Angaben."""
    wortlaut = {"stop_raus": "Stop gerissen, ganz raus",
                "round_trip_raus": "Gewinn verpufft, ganz raus",
                "teilverkauf": "Teilverkauf fällig",
                "trail_raus": "Nachzieh-Linie unterschritten, Rest raus"}
    kopf = f"{m['symbol']}" + (f" ({m['firma']})" if m["firma"] else "")
    vorsatz = "BEOBACHTUNG: " if m["beobachtung"] else ""
    return (f"{vorsatz}{kopf}; {wortlaut.get(m['aktion'], m['aktion'])}; "
            f"Kurs {m['kurs']:.2f}, {m['gewinn_pct']:+.1f} % seit Einstieg; "
            f"{m['grund']}")


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

def selbsttest() -> int:
    fehler = []

    def pruefe(name, bedingung, zusatz=""):
        print(f"  {'ok  ' if bedingung else 'FEHL'} {name}"
              + (f" — {zusatz}" if zusatz else ""))
        if not bedingung:
            fehler.append(name)

    print("Positionsverwaltung, Selbsttest")
    b = {}
    b = eroeffne(b, "AAA", "Darvas Box", 100.0, 95.0, index=0, firma="Alpha AG")
    pruefe("Position wird aufgenommen", "AAA" in b)
    pruefe("Stop kommt aus der Struktur",
           b["AAA"]["aktueller_stop"] == 95.0
           and b["AAA"]["stop_quelle"] == "struktur",
           f"{b['AAA']['aktueller_stop']} ({b['AAA']['stop_quelle']})")

    b = eroeffne(b, "BBB", "Rectangle Top", 100.0, 70.0, index=0)
    pruefe("Weit entfernte Struktur wird gedeckelt",
           b["BBB"]["aktueller_stop"] == 90.0
           and b["BBB"]["stop_quelle"] == "deckel")

    try:
        eroeffne(b, "AAA", "VCP", 50.0, 45.0)
        pruefe("Doppelte Position wird abgelehnt", False)
    except SystemExit:
        pruefe("Doppelte Position wird abgelehnt", True)

    # Der Stop reisst
    m = pruefe_bestand(b, {"AAA": 94.0}, heute_index=5)
    pruefe("Stop-Bruch wird gemeldet",
           len(m) == 1 and m[0]["aktion"] == "stop_raus",
           m[0]["grund"] if m else "nichts")
    pruefe("Die Position ist danach geschlossen",
           b["AAA"]["status"] == "geschlossen")
    pruefe("Das Ergebnis ist festgehalten",
           b["AAA"]["ergebnis_pct"] == -6.0, f"{b['AAA'].get('ergebnis_pct')}")

    # Ein Docht darf nicht ausloesen — es wird nur der Schluss geprueft
    b2 = eroeffne({}, "CCC", "VCP", 100.0, 95.0)
    m = pruefe_bestand(b2, {"CCC": 95.5}, heute_index=3)
    pruefe("Ein Schluss knapp über dem Stop löst nicht aus", not m)

    # Teilverkauf und Halteregel
    b3 = eroeffne({}, "DDD", "Cup & Handle", 100.0, 95.0)
    m = pruefe_bestand(b3, {"DDD": 125.0}, heute_index=10)
    pruefe("Schnellstarter setzt den Teilverkauf aus",
           not m and b3["DDD"]["halteregel_aktiv"] is True)
    m = pruefe_bestand(b3, {"DDD": 130.0}, heute_index=45)
    pruefe("Nach acht Wochen kommt der Teilverkauf",
           len(m) == 1 and m[0]["aktion"] == "teilverkauf")
    pruefe("Die Position bleibt dabei offen",
           b3["DDD"]["status"] == "offen")

    # Beobachtungseintrag
    b4 = eroeffne({}, "EEE", "VCP", 100.0, 95.0, beobachtung=True)
    m = pruefe_bestand(b4, {"EEE": 90.0}, heute_index=4)
    pruefe("Beobachtung wird als solche gekennzeichnet",
           m and m[0]["beobachtung"] is True)
    pruefe("Der Meldetext nennt sie ausdrücklich",
           melde_text(m[0]).startswith("BEOBACHTUNG:"),
           melde_text(m[0])[:60])

    # Datei hin und zurück
    import tempfile
    pfad = os.path.join(tempfile.mkdtemp(), "positionen.json")
    speichern(b3, pfad)
    pruefe("Bestand überlebt Speichern und Laden", laden(pfad) == b3)
    pruefe("Fehlende Datei ergibt leeren Bestand",
           laden(os.path.join(tempfile.mkdtemp(), "gibtsnicht.json")) == {})

    print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles bestanden.")
    return 1 if fehler else 0


# ---------------------------------------------------------------------------
# Befehlszeile
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Offene Positionen führen und gegen das "
                    "Exit-Regelwerk prüfen.")
    ap.add_argument("--liste", action="store_true")
    ap.add_argument("--eroeffnen", metavar="KUERZEL")
    ap.add_argument("--strategie", default="")
    ap.add_argument("--firma", default="")
    ap.add_argument("--einstieg", type=float)
    ap.add_argument("--struktur", type=float,
                    help="Struktureller Bruchpunkt des Musters. Fehlt er, "
                         "greift der Zehn-Prozent-Deckel.")
    ap.add_argument("--beobachtung", action="store_true",
                    help="Nur annehmen, nicht wirklich gekauft.")
    ap.add_argument("--schliessen", metavar="KUERZEL")
    ap.add_argument("--grund", default="von Hand geschlossen")
    ap.add_argument("--kurs", type=float)
    ap.add_argument("--selbsttest", action="store_true")
    args = ap.parse_args()

    if args.selbsttest:
        return selbsttest()

    bestand = laden()

    if args.eroeffnen:
        if args.einstieg is None:
            sys.exit("Bitte --einstieg angeben.")
        if args.strategie and not exit_regeln.strukturpunkt_beschreibung(
                args.strategie):
            print(f"Hinweis: '{args.strategie}' ist kein bekanntes Muster. "
                  f"Bekannt sind: "
                  + ", ".join(sorted(exit_regeln.STRUKTURPUNKT)))
        bestand = eroeffne(bestand, args.eroeffnen, args.strategie,
                           args.einstieg, args.struktur,
                           beobachtung=args.beobachtung, firma=args.firma)
        speichern(bestand)
        e = bestand[args.eroeffnen.upper()]
        print(f"{e['symbol']} aufgenommen: Einstieg {e['einstieg']}, "
              f"Stop {e['aktueller_stop']} ({e['stop_quelle']})"
              + ("  [Beobachtung]" if e["beobachtung"] else ""))
        if args.strategie:
            hinweis = exit_regeln.strukturpunkt_beschreibung(args.strategie)
            if hinweis:
                print(f"  Bruchpunkt bei diesem Muster: {hinweis}")
        return 0

    if args.schliessen:
        bestand = schliesse(bestand, args.schliessen, args.grund, args.kurs)
        speichern(bestand)
        print(f"{args.schliessen.upper()} geschlossen.")
        return 0

    offen = [e for e in bestand.values() if e.get("status") == "offen"]
    print(f"{len(offen)} offene Position(en), {len(bestand)} insgesamt.")
    for e in offen:
        art = " [Beobachtung]" if e.get("beobachtung") else ""
        print(f"  {e['symbol']:6s} {e.get('strategie', ''):26s} "
              f"Einstieg {e['einstieg']:8.2f}  Stop {e['aktueller_stop']:8.2f}  "
              f"seit {e['einstieg_datum']}"
              + ("  teilverkauft" if e["teilverkauft"] else "")
              + ("  Halteregel" if e["halteregel_aktiv"] else "") + art)
    return 0


if __name__ == "__main__":
    sys.exit(main())
