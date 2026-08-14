#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DIE AKTIENLISTEN — welche Strategie darf auf welche Liste?
============================================================
Gerhards Regel vom 14.08.2026, woertlich: "Die Darvas-Tradingstrategie
bekommt eine eigene Liste. Das Tradingmuster Darvas soll in Zukunft
ausschliesslich auf diese Liste angewandt werden. Die Darvasliste soll
fuer die anderen Strategien herangezogen werden, jedoch nicht umgekehrt.
Du bekommst in Zukunft also 2 Listen, die 2te, grosse Liste steht fuer
alle Strategien zur Verfuegung, ausser fuer Darvas."

DARAUS GENAU ZWEI SAETZE, und sie stehen NUR hier:

    DARVAS-LISTE  -> ALLE Strategien, auch Darvas
    GROSSE LISTE  -> alle Strategien AUSSER Darvas

Steht eine Aktie in beiden, gilt die grosszuegigere Seite: Sie ist in der
Darvas-Liste, also darf Darvas. Alles andere darf ohnehin ueberall.

WARUM EIN EIGENES MODUL: Weil "alle Tools sollen weiterhin alle Listen
ueberwachen" (Gerhard) sonst eine Sammlung von Stellen waere, die man
einzeln vergisst. Bisher stand `pd.read_csv("finviz_3.csv")` an sechs
Stellen verstreut. Jetzt fragt jedes Werkzeug hier nach, und eine dritte
Liste waere eine Zeile.

DATEIEN
    finviz_3.csv  die grosse Woechentliche (Name unveraendert, damit die
                  bestehenden Ablaeufe und der Upload weiterlaufen)
    darvas.csv    die Darvas-Liste

FEHLT DIE DARVAS-LISTE, gibt es KEINE Darvas-Kaufpunkte. Das ist die
woertliche Umsetzung von "ausschliesslich auf diese Liste" — aber es ist
ein stiller Verlust, und deshalb sagt fehlende_liste() es laut, statt es
nur ins Protokoll zu schreiben.

Aufruf:
    python listen.py --zeigen        was gerade in den Listen steht
    python listen.py --selbsttest
"""

import os
import sys

HAUPT_DATEI = "finviz_3.csv"
DARVAS_DATEI = "darvas.csv"

# Das Muster, das ausschliesslich auf der Darvas-Liste laufen darf. Der
# Name ist der, den der Scanner erzeugt (pattern_scanner.detect_darvas).
NUR_DARVAS_LISTE = ("Darvas Box",)


def _lies(pfad):
    """Ticker und Firma aus einer CSV. Fehlt die Datei, kommt eine leere
    Liste — kein Absturz, denn eine der beiden kann fehlen."""
    if not pfad or not os.path.exists(pfad):
        return []
    import pandas as pd
    try:
        df = pd.read_csv(pfad)
    except Exception:
        return []
    tsp = next((c for c in df.columns if c.strip().lower() == "ticker"), None)
    if tsp is None:
        return []
    fsp = next((c for c in df.columns if c.strip().lower() == "company"), None)
    raus, gesehen = [], set()
    for _, zeile in df.iterrows():
        t = str(zeile[tsp]).strip().upper()
        if not t or t == "NAN" or t in gesehen:
            continue
        gesehen.add(t)
        raus.append((t, str(zeile[fsp]) if fsp else ""))
    return raus


def darvas_liste(pfad=None):
    """Die Aktien, auf denen Darvas laufen darf."""
    return _lies(pfad or DARVAS_DATEI)


def haupt_liste(pfad=None):
    """Die grosse Liste. Fuer alles ausser Darvas."""
    return _lies(pfad or HAUPT_DATEI)


def alle_ticker(haupt=None, darvas=None):
    """ALLE Aktien aus BEIDEN Listen, ohne Doppelte.

    Das ist der Umfang, den jedes Werkzeug ueberwachen soll (Gerhard:
    "dass alle tools weiterhin alle Listen ueberwachen, die ich
    hochlade"). Die Darvas-Liste kommt zuerst, damit ihre Firmennamen
    gewinnen, falls sie sich unterscheiden."""
    raus, gesehen = [], set()
    for t, firma in darvas_liste(darvas) + haupt_liste(haupt):
        if t in gesehen:
            continue
        gesehen.add(t)
        raus.append((t, firma))
    return raus


def darf_darvas(ticker, darvas=None):
    """Darf auf dieser Aktie ein Darvas-Kaufpunkt entstehen?

    Nur, wenn sie in der Darvas-Liste steht. Steht sie zusaetzlich in der
    grossen, aendert das nichts — die Darvas-Liste ist die Erlaubnis."""
    return (ticker or "").strip().upper() in {t for t, _ in darvas_liste(darvas)}


def erlaubte_muster(ticker, alle_muster, darvas=None):
    """Aus einer Liste von Musternamen die, die auf dieser Aktie erlaubt
    sind. Die eine Stelle, an der die Regel angewandt wird."""
    if darf_darvas(ticker, darvas):
        return list(alle_muster)
    return [m for m in alle_muster if m not in NUR_DARVAS_LISTE]


def fehlende_liste(haupt=None, darvas=None):
    """Fehlt eine der beiden Listen? Rueckgabe: Klartext oder None.

    Wird beim Scan ausgegeben UND in die Mappe geschrieben, damit ein
    stiller Ausfall auffaellt. Mathias am 14.08.2026: "Das Protokoll
    liest ausser dir niemand.\""""
    d, h = darvas_liste(darvas), haupt_liste(haupt)
    if not d and not h:
        return "KEINE Aktienliste gefunden — der Scan hat nichts zu tun."
    if not d:
        return ("Die Darvas-Liste fehlt. Darvas-Kaufpunkte entstehen "
                "deshalb KEINE; alle anderen Muster laufen normal.")
    if not h:
        return ("Die große Liste fehlt. Es wird nur die Darvas-Liste "
                "gescannt, dort aber mit allen Mustern.")
    return None


def uebersicht(haupt=None, darvas=None):
    """Eine Zeile je Liste, fuer Meldungen und Protokoll."""
    d, h = darvas_liste(darvas), haupt_liste(haupt)
    zusammen = alle_ticker(haupt, darvas)
    beide = {t for t, _ in d} & {t for t, _ in h}
    return (f"{len(d)} Aktien in der Darvas-Liste, {len(h)} in der großen, "
            f"{len(zusammen)} zusammen ({len(beide)} in beiden)")


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

def selbsttest() -> int:
    import tempfile
    import pathlib
    fehler = []

    def p(name, bedingung, zusatz=""):
        print(f"  {'ok  ' if bedingung else 'FEHL'} {name}"
              + (f" — {zusatz}" if zusatz else ""))
        if not bedingung:
            fehler.append(name)

    with tempfile.TemporaryDirectory() as ordner:
        o = pathlib.Path(ordner)
        (o / "gross.csv").write_text("Ticker,Company\nAAA,Alpha\nBBB,Beta\n",
                                     encoding="utf-8")
        (o / "darv.csv").write_text("Ticker,Company\nBBB,Beta\nCCC,Gamma\n",
                                    encoding="utf-8")
        g, d = str(o / "gross.csv"), str(o / "darv.csv")

        p("Beide Listen zusammen, ohne Doppelte",
          [t for t, _ in alle_ticker(g, d)] == ["BBB", "CCC", "AAA"],
          [t for t, _ in alle_ticker(g, d)])
        # DIE REGEL, in beide Richtungen geprueft.
        p("Eine Aktie NUR in der Darvas-Liste darf Darvas",
          darf_darvas("CCC", d))
        p("Eine Aktie NUR in der großen Liste darf Darvas NICHT",
          not darf_darvas("AAA", d))
        p("Eine Aktie in BEIDEN darf Darvas", darf_darvas("BBB", d))
        p("Groß- und Kleinschreibung ist egal", darf_darvas("ccc", d))

        MUSTER = ["High & Tight Flag", "VCP", "Cup & Handle", "Darvas Box",
                  "Rectangle Top", "Cup & Handle (Wochenbasis)"]
        p("Auf der großen Liste laufen alle Muster AUSSER Darvas",
          erlaubte_muster("AAA", MUSTER, d) == [m for m in MUSTER
                                                if m != "Darvas Box"])
        p("Auf der Darvas-Liste laufen ALLE Muster",
          erlaubte_muster("CCC", MUSTER, d) == MUSTER)
        p("Die große Liste verliert kein anderes Muster",
          len(erlaubte_muster("AAA", MUSTER, d)) == len(MUSTER) - 1)

        # Fehlende Dateien duerfen nichts umwerfen.
        p("Fehlt die Darvas-Liste, darf niemand Darvas",
          not darf_darvas("AAA", str(o / "gibtsnicht.csv")))
        p("Fehlt die Darvas-Liste, wird das laut gesagt",
          "Darvas-Liste fehlt" in (fehlende_liste(
              g, str(o / "gibtsnicht.csv")) or ""))
        p("Fehlt die große Liste, wird auch das gesagt",
          "große Liste fehlt" in (fehlende_liste(
              str(o / "gibtsnicht.csv"), d) or ""))
        p("Sind beide da, gibt es nichts zu melden",
          fehlende_liste(g, d) is None)
        p("Fehlen beide, sagt es das deutlich",
          "KEINE Aktienliste" in (fehlende_liste(
              str(o / "x.csv"), str(o / "y.csv")) or ""))
        p("Ohne jede Liste stürzt nichts ab",
          alle_ticker(str(o / "x.csv"), str(o / "y.csv")) == [])
        # Eine CSV ohne Ticker-Spalte ist keine Liste.
        (o / "falsch.csv").write_text("Name,Wert\nx,1\n", encoding="utf-8")
        p("Eine CSV ohne Ticker-Spalte ergibt eine leere Liste",
          _lies(str(o / "falsch.csv")) == [])
        p("Die Übersicht nennt beide Listen und die Schnittmenge",
          "1 in beiden" in uebersicht(g, d), uebersicht(g, d))

    print("\n" + ("Alles bestanden." if not fehler
                  else f"{len(fehler)} FEHLER: " + ", ".join(fehler)))
    return 1 if fehler else 0


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Die Aktienlisten")
    ap.add_argument("--zeigen", action="store_true")
    ap.add_argument("--selbsttest", action="store_true")
    a = ap.parse_args()
    if a.selbsttest:
        return selbsttest()
    print(uebersicht())
    hinweis = fehlende_liste()
    if hinweis:
        print("  " + hinweis)
    if a.zeigen:
        d = {t for t, _ in darvas_liste()}
        for t, firma in alle_ticker():
            print(f"  {t:8s} {'Darvas erlaubt' if t in d else '':16s} {firma[:40]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
