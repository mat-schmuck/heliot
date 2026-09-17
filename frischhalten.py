#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EIGENE MODULE FRISCH HALTEN (Befund 17.09.2026)
===============================================
Streamlit Community Cloud holt bei einem Push nur den neuen Code und fuehrt
das Hauptskript neu aus; der Python-Prozess bleibt dabei stehen ("Pulling
code changes from Github ... Updated app!"). Importierte EIGENE Module
bleiben deshalb in der Fassung von vorher im Speicher. Ruft das frische
Hauptskript dann eine Funktion auf, die es in der alten Fassung noch nicht
gibt, bricht der Lauf ab.

GEMESSEN am 17.09.2026 in den Cloud-Protokollen der App, drei Tage nach dem
Push vom 14.09. und zwei nach dem vom 15.09.:
  AttributeError: module 'nachschlagen' has no attribute 'analysten_zeile'
  AttributeError: module 'scanner_ansicht' has no attribute 'wirksame_einstellung'
  AttributeError: 'Feld' object has no attribute 'eingabe_hinweis'
Fuer den Nutzer hiess das: Das Feld "Aktie nachschlagen" nahm keine Aktie
mehr an, und der Scanner-Reiter brach ab. Ein Neustart der App in der
Streamlit-Verwaltung behebt es sofort, aber nur bis zum naechsten Push.

DIESES MODUL prueft bei jedem Lauf, ob eine eigene Moduldatei neuer ist als
ihr geladener Stand. Ist eine neuer, werden ALLE eigenen Module neu geladen,
und zwar zweimal: erst die geaenderten, dann alle. Der zweite Durchgang ist
noetig, weil ein Modul mit "from config import CFG" den Wert beim Laden
bindet; nach dem ersten Durchgang zeigt es sonst weiter auf den alten.
importlib.reload behaelt das Modulobjekt und ersetzt nur seine Inhalte, also
sehen alle Stellen, die das Modul schon importiert haben, danach den neuen
Stand, ohne dass irgendwo ein Import wiederholt werden muesste.

WAS ES NICHT TUT: Es laedt keine fremden Pakete neu (nur Dateien im eigenen
Ordner), es faengt jeden Fehler ab und meldet ihn als Text, damit die App
auch bei einer kaputten Datei weiterlaeuft, und es ruehrt nichts an, solange
sich keine Datei geaendert hat (je Lauf nur ein Blick auf die Zeitstempel).

Aufruf:
  python frischhalten.py --selbsttest
"""

import argparse
import importlib
import os
import sys

# Zeitstempel je Modulname, wie er beim letzten Laden auf der Platte stand.
_STAND = {}
_FEHLT = object()


def eigene_module(ordner, ausser=()):
    """[(Name, Modul, Datei)] aller geladenen Module aus diesem Ordner."""
    ordner = os.path.abspath(ordner)
    ausser = set(ausser) | {"__main__"}
    raus = []
    for name, modul in list(sys.modules.items()):
        if name in ausser or modul is None:
            continue
        datei = getattr(modul, "__file__", None)
        if not datei:
            continue
        try:
            if os.path.dirname(os.path.abspath(datei)) == ordner:
                raus.append((name, modul, datei))
        except (OSError, ValueError):
            continue
    return sorted(raus)


def _zeit(datei):
    try:
        return os.path.getmtime(datei)
    except OSError:
        return None


def prozess_start():
    """Wann dieser Python-Prozess gestartet ist, oder None.

    Unter Linux, und damit in der Cloud, traegt /proc/self die Startzeit des
    Prozesses als Aenderungszeit. Der ERSTE Lauf braucht sie: Holt die Cloud
    bei einem Push neue Dateien und fuehrt danach das Hauptskript aus, sind
    die Dateien auf der Platte schon neu, waehrend die Module im Speicher noch
    alt sind. Ohne diese Referenz wuerde der erste Lauf die neuen Zeitstempel
    einfach als Ausgangsstand merken und die alten Module stehen lassen.
    Unter Windows gibt es /proc nicht; dort wird beim Entwickeln ohnehin neu
    gestartet, und der erste Lauf merkt sich nur die Staende."""
    try:
        return os.stat("/proc/self").st_mtime
    except OSError:
        return None


def auffrischen(ordner, ausser=(), stand=None, referenz=_FEHLT):
    """Prueft die Zeitstempel und laedt bei Bedarf neu.
    referenz: Zeitpunkt, gegen den ein noch unbekanntes Modul geprueft wird;
    Vorgabe ist der Start des Prozesses (siehe prozess_start).
    -> ([Namen der geaenderten Module], [Fehlertexte])."""
    stand = _STAND if stand is None else stand
    if referenz is _FEHLT:
        referenz = prozess_start()
    module = eigene_module(ordner, ausser)
    geaendert = []
    for name, _modul, datei in module:
        z = _zeit(datei)
        if z is None:
            continue
        bekannt = stand.get(name, referenz)
        if bekannt is not None and z > bekannt:
            geaendert.append(name)
        else:
            stand[name] = z
    if not geaendert:
        return [], []
    fehler = []
    namen_alle = [n for n, _m, _d in module]
    for runde in (geaendert, namen_alle):
        for name in runde:
            modul = sys.modules.get(name)
            if modul is None:
                continue
            try:
                importlib.reload(modul)
            except Exception as e:  # noqa  eine kaputte Datei darf die App nicht toeten
                text = f"{name}: {type(e).__name__}: {e}"
                if text not in fehler:
                    fehler.append(text)
    for name, _modul, datei in eigene_module(ordner, ausser):
        z = _zeit(datei)
        if z is not None:
            stand[name] = z
    return geaendert, fehler


# --- Selbsttest -------------------------------------------------------------

def selbsttest() -> int:
    import shutil
    import tempfile
    import textwrap
    fehler = []

    def p(name, ok, zusatz=""):
        print(f"  {'ok  ' if ok else 'FEHL'} {name}" + (f"; {zusatz}" if zusatz and not ok else ""))
        if not ok:
            fehler.append(name)

    print("Eigene Module frisch halten, Selbsttest (ohne Netz)")
    ordner = tempfile.mkdtemp(prefix="frisch_")
    vorher_pfad = list(sys.path)
    try:
        def schreiben(name, text, alter=0):
            pfad = os.path.join(ordner, name)
            with open(pfad, "w", encoding="utf-8", newline="\n") as f:
                f.write(textwrap.dedent(text))
            if alter:
                os.utime(pfad, (os.path.getatime(pfad) - alter, os.path.getmtime(pfad) - alter))
            return pfad

        schreiben("fh_a.py", '''
            WERT = "alt"

            def gruss():
                return "alt"
            ''', alter=10)
        schreiben("fh_b.py", '''
            from fh_a import WERT

            def gruss_b():
                return "b sagt " + WERT
            ''', alter=10)
        sys.path.insert(0, ordner)
        a = importlib.import_module("fh_a")
        b = importlib.import_module("fh_b")
        stand = {}
        p("Erster Lauf merkt die Staende und laedt nichts neu",
          auffrischen(ordner, stand=stand) == ([], []) and set(stand) == {"fh_a", "fh_b"}, str(stand))
        p("Ohne Aenderung passiert nichts", auffrischen(ordner, stand=stand) == ([], []))

        schreiben("fh_a.py", '''
            WERT = "neu"

            def gruss():
                return "neu"

            def ganz_neu():
                return "da"
            ''')
        geaendert, fhl = auffrischen(ordner, stand=stand)
        p("Geaenderte Datei wird erkannt und neu geladen", geaendert == ["fh_a"] and not fhl, f"{geaendert} {fhl}")
        p("Das schon importierte Modulobjekt traegt den neuen Stand",
          a.gruss() == "neu" and hasattr(a, "ganz_neu") and sys.modules["fh_a"] is a, a.gruss())
        p("Ein Modul mit from-import bekommt den neuen Wert mit", b.gruss_b() == "b sagt neu", b.gruss_b())
        p("Danach ist wieder Ruhe", auffrischen(ordner, stand=stand) == ([], []))

        schreiben("fh_a.py", '''
            WERT = "kaputt"
            def gruss(:
            ''')
        geaendert, fhl = auffrischen(ordner, stand=stand)
        p("Eine kaputte Datei wirft nicht, sondern wird als Fehlertext gemeldet",
          geaendert == ["fh_a"] and any(x.startswith("fh_a: SyntaxError") for x in fhl), f"{geaendert} {fhl}")
        p("Nach dem Fehler laeuft die alte Fassung weiter statt gar keiner", a.gruss() == "neu", a.gruss())

        schreiben("fh_a.py", '''
            WERT = "wieder gut"

            def gruss():
                return "wieder gut"
            ''')
        geaendert, fhl = auffrischen(ordner, stand=stand)
        p("Ist die Datei wieder heil, greift der naechste Lauf",
          geaendert == ["fh_a"] and not fhl and a.gruss() == "wieder gut", f"{geaendert} {fhl}")

        # Erster Lauf nach einem Push: Die Dateien sind schon neu, die Module
        # im Speicher noch alt. Dann gilt der Prozessstart als Referenz.
        stand_neu = {}
        vor_start = min(os.path.getmtime(os.path.join(ordner, n)) for n in ("fh_a.py", "fh_b.py")) - 5
        geaendert, fhl = auffrischen(ordner, stand=stand_neu, referenz=vor_start)
        p("Erster Lauf laedt alles neu, was juenger ist als der Prozessstart",
          set(geaendert) == {"fh_a", "fh_b"} and not fhl, f"{geaendert} {fhl}")
        stand_teil = {}
        zwischen = os.path.getmtime(os.path.join(ordner, "fh_b.py")) + 1
        geaendert2, _f2 = auffrischen(ordner, stand=stand_teil, referenz=zwischen)
        p("Erster Lauf laesst aeltere Dateien in Ruhe", geaendert2 == ["fh_a"], str(geaendert2))
        stand_alt = {}
        nach_start = os.path.getmtime(os.path.join(ordner, "fh_a.py")) + 5
        p("Erster Lauf laedt nichts, wenn die Dateien aelter sind als der Prozessstart",
          auffrischen(ordner, stand=stand_alt, referenz=nach_start) == ([], []) and len(stand_alt) == 2)
        p("Ohne Referenz gilt nur der gemerkte Stand",
          auffrischen(ordner, stand=dict(stand_alt), referenz=None) == ([], []))
        p("Unter Linux ist der Prozessstart bekannt, sonst None",
          (prozess_start() is None) == (not os.path.exists("/proc/self")))
        p("Fremde Pakete bleiben unangetastet",
          all(n in ("fh_a", "fh_b") for n, _m, _d in eigene_module(ordner))
          and "os" not in [n for n, _m, _d in eigene_module(ordner)])
        p("Ausgenommene Module bleiben draussen",
          [n for n, _m, _d in eigene_module(ordner, ausser=("fh_b",))] == ["fh_a"])
        # Der echte Ordner der App: das Modul selbst darf sich nicht neu laden
        hier = os.path.dirname(os.path.abspath(__file__))
        p("Im eigenen Ordner laesst sich frischhalten selbst ausnehmen",
          "frischhalten" not in [n for n, _m, _d in eigene_module(hier, ausser=("frischhalten",))])
    finally:
        sys.path[:] = vorher_pfad
        for name in ("fh_a", "fh_b"):
            sys.modules.pop(name, None)
        shutil.rmtree(ordner, ignore_errors=True)

    print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles bestanden.")
    return 1 if fehler else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Eigene Module nach einem Push frisch halten")
    ap.add_argument("--selbsttest", action="store_true")
    args = ap.parse_args()
    if args.selbsttest:
        return selbsttest()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
