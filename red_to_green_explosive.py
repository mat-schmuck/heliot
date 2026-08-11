#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KAPITEL 11 — RED-TO-GREEN EXPLOSIVE (Mathias, 12.08.2026)
==========================================================
Die Aktie eroeffnet rot und dreht AUS EIGENEM ANTRIEB, ohne dass der
Markt etwas damit zu tun haette.

DER ANLASS, gemessen
    Fastly am 10.08.2026: Eroeffnung 22,45, das sind 2,2 % UNTER dem
    Vortagesschluss. Schluss 27,75, also 20,9 % im Plus; von der
    Eroeffnung bis zum Schluss 23,6 %. Gemeldet wurde nichts.

    Warum keine der zehn bestehenden Strategien griff:
      * KEINE BASIS. Darvas, Rectangle, beide Cup-Fassungen, VCP und die
        Flagge setzen alle eine vorherige Beruhigung voraus. Die zwoelf
        Tage davor hatten eine Spanne von 43,8 % — am 4.8. plus 8,3 %,
        am 5.8. plus 4,3 %, am 6.8. minus 12,9 %.
      * KEINE LUECKE. Gap and Go verlangt sieben Prozent nach OBEN.
      * NICHT DIE PANIK. Kapitel 9 verlangt zwei Dinge gleichzeitig, und
        beide fehlten: Der Nasdaq haette mindestens 1,5 % nach unten
        aufmachen muessen (er eroeffnete mit -0,04 %), und die Aktie
        selbst mindestens 5 % (es waren 2,2).

WAS DIESES KAPITEL ANDERS MACHT — genau zwei Dinge
    1. KEIN NASDAQ-SCHALTER. Mathias' ausdrueckliche Vorgabe. Die
       Marktlage spielt keine Rolle.
    2. Die Aktie muss nur 2 % statt 5 % rot eroeffnen.

    ALLES UEBRIGE ist wortgleich Kapitel 9 und wird von dort benutzt:
    dieselbe Fokusliste, dieselbe Volumen-Signatur (Anflug, Sprung,
    haelt der Sprung an), dieselbe Kreuzung des Vortagesschlusses,
    derselbe Strukturpunkt fuer den Stop.

WARUM EIN EIGENES KAPITEL UND KEINE AUFWEICHUNG VON KAPITEL 9
    Gerhard hat dessen Bedingungen mit Bedacht so eng gefasst: Es ist
    eine Regel fuer den Tag, an dem der ganze Markt einbricht und eine
    starke Aktie sich als Erste wieder aufrappelt. Wer dort den
    Nasdaq-Teil herausnimmt, macht aus einer Panik-Regel etwas anderes
    und merkt es spaeter nicht mehr. Kapitel 9 bleibt deshalb
    unangetastet; beide koennen nebeneinander feuern.

WAS MAN WISSEN MUSS, BEVOR MAN DANACH HANDELT
    Dieses Kapitel kauft in eine laufende Bewegung hinein, an der es
    keine Struktur gibt, an der ein Stop haengen koennte — der
    Strukturpunkt ist der Vortagesschluss. Dieselbe Aktie ist am
    6.8.2026 an einem Tag um 12,9 % GEFALLEN. Solche Bewegungen gehen in
    beide Richtungen, und gemessen ist dieses Kapitel noch nicht.

Aufruf:
    python red_to_green_explosive.py --selbsttest
"""

import argparse
import sys

import red_to_green
from config import CFG as _ALLE, hoechstens

CFG = _ALLE["red_to_green_explosive"]
NAME = "Red-to-Green Explosive"      # muss zu exit_regeln.STRUKTURPUNKT passen


def aktien_gap(aktie_open, aktie_vortagesschluss):
    """Eroeffnet die Aktie rot genug? Zwei Prozent statt fuenf.

    Rueckgabe: (erfuellt, gap in Prozent). Bewusst dieselbe Bauart wie
    red_to_green.aktien_gap, nur mit eigener Schwelle — damit beide
    Kapitel gleich gelesen werden koennen."""
    if not aktie_vortagesschluss or aktie_vortagesschluss <= 0:
        return False, 0.0
    gap = aktie_open / aktie_vortagesschluss - 1
    return hoechstens(gap, CFG["aktie_gap_min"]), round(gap * 100, 2)


# Die uebrigen Bausteine kommen UNVERAENDERT aus Kapitel 9. Sie hier
# nachzubauen waere die sicherste Art, die beiden Kapitel unbemerkt
# auseinanderlaufen zu lassen.
punkt_setzen = red_to_green.punkt_setzen
pruefe = red_to_green.pruefe
fokuslisten_kandidat = red_to_green.fokuslisten_kandidat


def selbsttest() -> int:
    fehler = []

    def p(name, bedingung, zusatz=""):
        print(f"  {'ok  ' if bedingung else 'FEHL'} {name}"
              + (f" — {zusatz}" if zusatz else ""))
        if not bedingung:
            fehler.append(name)

    print(f"{NAME} (Kapitel 11), Selbsttest")

    # --- Die eine gelockerte Schwelle -----------------------------------
    ok, gap = aktien_gap(22.45, 22.96)          # Fastly, 10.08.2026
    p("Fastly am 10.08.2026 erfüllt die Lücke", ok, f"{gap} %")
    p("Kapitel 9 haette ihn NICHT erfüllt",
      not red_to_green.aktien_gap(22.45, 22.96)[0],
      f"{red_to_green.aktien_gap(22.45, 22.96)[1]} % gegen -5 % gefordert")

    ok, gap = aktien_gap(100.0, 100.0)
    p("Unveränderte Eröffnung erfüllt nichts", not ok, f"{gap} %")
    ok, gap = aktien_gap(98.0, 100.0)
    p("Genau -2,0 % erfüllt gerade noch (Gleitkomma)", ok, f"{gap} %")
    ok, gap = aktien_gap(98.5, 100.0)
    p("-1,5 % reicht nicht", not ok, f"{gap} %")
    ok, gap = aktien_gap(101.0, 100.0)
    p("Grün eröffnet erfüllt nichts", not ok, f"{gap} %")
    p("Ohne Vortagesschluss kein Signal", not aktien_gap(98.0, None)[0])
    p("Vortagesschluss null kein Signal", not aktien_gap(98.0, 0)[0])

    # --- Was ausdruecklich FEHLT ----------------------------------------
    p("Kapitel 11 kennt KEINEN Nasdaq-Schalter",
      "nasdaq_gap_scharf" not in CFG)
    p("Kapitel 9 hat ihn weiterhin",
      "nasdaq_gap_scharf" in _ALLE["red_to_green"])

    # --- Was gleich sein MUSS -------------------------------------------
    gleich = [k for k in CFG if k != "aktie_gap_min"]
    abweichend = [k for k in gleich
                  if _ALLE["red_to_green"].get(k) != CFG[k]]
    p("Alle übrigen Werte sind wortgleich mit Kapitel 9",
      not abweichend, ", ".join(abweichend))
    p("Die Bausteine kommen aus Kapitel 9, nicht nachgebaut",
      pruefe is red_to_green.pruefe
      and punkt_setzen is red_to_green.punkt_setzen)

    # --- Der ganze Weg, mit fester Kurve ---------------------------------
    import volumen
    testkurve = {m: m / volumen.HANDELSMINUTEN
                 for m in range(0, volumen.HANDELSMINUTEN + 1, 5)}
    v50 = 1_000_000.0
    vortag = 100.0
    verlauf = []
    # Rot eroeffnet, ruhiger Anflug, dann Sprung ueber den Vortagesschluss
    for minute, kurs, anteil in ((35, 98.0, 0.5), (40, 99.0, 0.8),
                                 (45, 101.0, 2.5), (50, 101.5, 3.0)):
        punkt_setzen(verlauf, minute,
                     kurs, anteil * v50 * (minute / volumen.HANDELSMINUTEN))
    treffer = pruefe(verlauf, vortag, v50, testkurve)
    p("Der ganze Weg läuft durch und liefert ein Ergebnis",
      treffer is None or isinstance(treffer, dict),
      "Treffer" if treffer else "kein Treffer (Signatur nicht erfüllt)")

    print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles bestanden.")
    return 1 if fehler else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=f"{NAME} — Kapitel 11")
    ap.add_argument("--selbsttest", action="store_true")
    args = ap.parse_args()
    if args.selbsttest:
        return selbsttest()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
