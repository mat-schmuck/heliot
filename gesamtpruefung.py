#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GESAMTPRUEFUNG — das ganze Regelwerk auf einmal
================================================
Auf Mathias' Auftrag vom 10.08.2026: "voll umfaenglicher Test des
gesamten Regelwerks, wirklich alles inkl. aller Bausteine, Muster und
Strategien".

Die einzelnen Module haben ihre eigenen Selbsttests. Was dort NICHT
geprueft werden kann, sind die Stellen ZWISCHEN den Modulen — und genau
dort sassen bisher die teuersten Fehler:

  * Der Scanner erzeugte Stops, die niemand deckelte (344 von 1098).
  * Die Risiko-Anzeige teilte durch den falschen Wert.
  * Der Waechter kannte einen Strategienamen nicht, den der Scanner
    erzeugt — die Volumenhuerde fiel still auf den Rueckfallwert.

Diese Pruefung geht deshalb quer durch: Sie nimmt die Namen, die der
Scanner wirklich erzeugt, und haelt sie gegen die Tabellen, die der
Waechter und das Exit-Regelwerk fuehren.

ACHT BLOECKE
    A  Statik: laesst sich jedes Modul laden?
    B  Selbsttests aller Module
    C  Muster-Detektoren gegen ECHTE Kursdaten
    D  Invarianten des Regelwerks (die Naht zwischen den Modulen)
    E  Wege des Waechters
    F  Exit-Regelwerk: sind alle Ausgaenge erreichbar?
    G  Volumenformel
    H  Betrieb: Ablaeufe, Einstellungen, Datenlage

Aufruf:
    python gesamtpruefung.py              alles, mit Netz
    python gesamtpruefung.py --ohne-netz  Bloecke C entfaellt
"""

import argparse
import json
import os
import pathlib
import subprocess
import sys
import warnings
from datetime import datetime, timedelta, timezone

warnings.filterwarnings("ignore")

# AUSGABE AUF UTF-8 ZWINGEN (13.08.2026, hier selbst hineingelaufen).
# In der Cloud laeuft alles unter UTF-8, auf einem deutschen Windows aber
# unter cp1252 — und dort fehlen Zeichen, die die Module in ihren
# Protokoll- und Pruefzeilen verwenden: das Warnzeichen U+26A0 in
# breakout_watcher.py, der Pfeil U+2192 im Selbsttest von volumen.py.
# Der Lauf ist daran zweimal gestorben, und zwar an der unguenstigsten
# Stelle: mitten drin, sobald eine Zeile etwas zu MELDEN hatte.
#
# ZWEI Dinge sind noetig, und das erste allein reicht nicht:
#   1. os.environ — damit erben die UNTERPROZESSE die Einstellung. Block
#      B ruft jeden Selbsttest als eigenen Prozess auf; genau dort ist
#      volumen.py gescheitert, waehrend die Pruefung selbst schon lief.
#   2. reconfigure — die eigenen Stroeme stehen beim Programmstart schon
#      fest, an die kommt die Umgebungsvariable nicht mehr heran.
os.environ["PYTHONIOENCODING"] = "utf-8"
for _strom in (sys.stdout, sys.stderr):
    try:
        _strom.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

WURZEL = pathlib.Path(__file__).parent
ERGEBNISSE = []          # (block, name, bestanden, zusatz)


def pruefe(block, name, bedingung, zusatz=""):
    ERGEBNISSE.append((block, name, bool(bedingung), str(zusatz)))
    zeichen = "ok  " if bedingung else "FEHL"
    print(f"  {zeichen} {name}" + (f" — {zusatz}" if zusatz else ""))
    return bool(bedingung)


def ueberschrift(text):
    print(f"\n{'=' * 72}\n{text}\n{'=' * 72}")


# ---------------------------------------------------------------------------
# A — Statik
# ---------------------------------------------------------------------------

# Module, die im Betrieb laufen. Messwerkzeuge und Einmal-Skripte sind
# absichtlich nicht dabei — sie duerfen ruhig veralten.
BETRIEB = ["config", "volumen", "kurs_cache", "pattern_scanner",
           "breakout_watcher", "cup_handle_v2", "shakeout", "red_to_green",
           "crash_support", "exit_regeln", "positionen", "trigger_logbuch",
           "red_to_green_explosive", "zahlen_termine", "sektor_radar",
           "insider_scanner", "insider_edgar", "listen",
           "scan_noetig", "waechter_noetig", "wartung", "ntfy_verlauf",
           "yahoo_ws", "staffelung", "traderfox_alarm_bot"]


def block_a():
    ueberschrift("A — STATIK: laesst sich jedes Betriebsmodul laden?")
    for name in BETRIEB:
        try:
            __import__(name)
            pruefe("A", f"{name} laedt", True)
        except Exception as e:
            pruefe("A", f"{name} laedt", False, f"{type(e).__name__}: {e}")

    r = subprocess.run([sys.executable, "-m", "pyflakes"]
                       + [str(p) for p in sorted(WURZEL.glob("*.py"))],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    # Bekannte, harmlose Warnungen aus Altbestand.
    egal = ("f-string is missing placeholders",
            "'config.mind_erreicht' imported but unused",
            "'dataclasses.field' imported but unused",
            "'playwright.sync_api.TimeoutError as PWTimeout' imported but unused",
            "local variable 'stand' is assigned",
            "local variable 'e' is assigned",
            "'os' imported but unused", "'time' imported but unused")
    zeilen = [z for z in (r.stdout or "").splitlines()
              if z.strip() and not any(w in z for w in egal)]
    pruefe("A", "pyflakes ohne neue Beanstandung", not zeilen,
           "; ".join(zeilen[:3]))


# ---------------------------------------------------------------------------
# B — Selbsttests
# ---------------------------------------------------------------------------

def block_b():
    ueberschrift("B — SELBSTTESTS aller Module")
    mit_schalter = ["exit_regeln", "positionen", "crash_support",
                    "trigger_logbuch", "cup_handle_v2", "shakeout",
                    "red_to_green", "red_to_green_explosive", "zahlen_termine",
                    "scan_noetig", "waechter_noetig", "sektor_radar",
                    "insider_scanner", "insider_edgar", "listen"]
    for name in mit_schalter:
        r = subprocess.run([sys.executable, f"{name}.py", "--selbsttest"],
                           capture_output=True, text=True, cwd=WURZEL,
                           encoding="utf-8", errors="replace", timeout=300)
        letzte = (r.stdout or "").strip().splitlines()[-1:] or [""]
        pruefe("B", f"{name}", r.returncode == 0 and "bestanden" in letzte[0],
               letzte[0][:60])
    # volumen.py prueft sich ohne Schalter
    r = subprocess.run([sys.executable, "volumen.py"], capture_output=True,
                       text=True, cwd=WURZEL, encoding="utf-8",
                       errors="replace", timeout=300)
    pruefe("B", "volumen", r.returncode == 0 and "bestanden" in (r.stdout or ""),
           (r.stdout or "").strip().splitlines()[-1][:60] if r.stdout else "")


# ---------------------------------------------------------------------------
# C — Muster gegen echte Kursdaten
# ---------------------------------------------------------------------------

def block_c(anzahl=40):
    ueberschrift(f"C — MUSTER-DETEKTOREN gegen echte Kursdaten ({anzahl} Aktien)")
    import pattern_scanner as ps
    import cup_handle_v2
    import shakeout

    # BEIDE Listen (Gerhard, 14.08.2026): "dass alle tools weiterhin
    # alle Listen ueberwachen, die ich hochlade".
    import listen
    liste = [t for t, _ in listen.alle_ticker(
        haupt=str(WURZEL / "finviz_3.csv"),
        darvas=str(WURZEL / "darvas.csv"))]
    proben = liste[:anzahl]
    ps.lade_yahoo_sammelabruf(proben)

    detektoren = {
        "High & Tight Flag": lambda d: ps.detect_htf(d),
        "VCP": lambda d: ps.detect_vcp(d, True),
        "Cup & Handle": lambda d: ps.detect_cup_handle(d),
        "Darvas Box": lambda d: ps.detect_darvas(d),
        "Rectangle Top": lambda d: ps.detect_rectangle(d),
        "Cup & Handle (Wochenbasis)": lambda d: cup_handle_v2.detect_cup_handle_v2(d),
    }
    treffer = {k: 0 for k in detektoren}
    treffer["Shakeout-Spring"] = 0
    fehler = {}
    geladen = 0
    namen_erzeugt = set()

    for t in proben:
        df = ps.fetch_history(t, None, ps.RateLimiter(8))
        if df is None or len(df) < 250:
            continue
        # WIE IM ECHTBETRIEB: Die Detektoren erwarten die berechneten
        # Kennzahlen (ma21, ma50, hi52 ...). Ohne diesen Schritt wirft
        # Rectangle Top einen KeyError — gefunden am 11.08.2026, und zwar
        # als Fehler dieser Pruefung, nicht des Scanners.
        df = ps.add_indicators(df)
        geladen += 1
        for name, fn in detektoren.items():
            try:
                res = fn(df)
                if res:
                    treffer[name] += 1
                    namen_erzeugt.add(res["strategie"])
            except Exception as e:
                fehler.setdefault(name, f"{type(e).__name__}: {e}")
        try:
            kurse = shakeout.aus_scanner_df(df)
            s = shakeout.erkenne_shakeout_setup(kurse)
            if s:
                treffer["Shakeout-Spring"] += 1
        except Exception as e:
            fehler.setdefault("Shakeout-Spring", f"{type(e).__name__}: {e}")

    pruefe("C", "Kursdaten geladen", geladen >= anzahl * 0.5,
           f"{geladen} von {len(proben)} Aktien mit genug Historie")
    for name in list(detektoren) + ["Shakeout-Spring"]:
        if name in fehler:
            pruefe("C", f"{name} laeuft fehlerfrei", False, fehler[name])
        else:
            pruefe("C", f"{name} laeuft fehlerfrei", True,
                   f"{treffer[name]} Treffer")
    return namen_erzeugt


# ---------------------------------------------------------------------------
# D — Invarianten des Regelwerks
# ---------------------------------------------------------------------------

def block_d(namen_aus_c=None):
    ueberschrift("D — INVARIANTEN: die Naht zwischen den Modulen")
    import pandas as pd
    import pattern_scanner as ps
    import breakout_watcher as bw
    import exit_regeln as ex

    # Alle Strategienamen, die im System entstehen koennen.
    erzeugbar = set(ps.PRIORITY) | {"Lücken-Bestätigungstag", "Red-to-Green",
                                    "Red-to-Green Explosive",
                                    "Shakeout-Spring", "Crash-Support"}
    if namen_aus_c:
        erzeugbar |= namen_aus_c

    ohne_struktur = sorted(erzeugbar - set(ex.STRUKTURPUNKT))
    pruefe("D", "Jede Strategie hat einen Strukturpunkt fuer den Stop",
           not ohne_struktur, ", ".join(ohne_struktur))

    # Die Volumenhuerde: Muster-Kaufpunkte laufen ueber VOL_FAKTOR. Gap and
    # Go, Red-to-Green und Shakeout haben eigene Wege und sind ausgenommen.
    ueber_volfaktor = set(ps.PRIORITY)
    ohne_huerde = sorted(ueber_volfaktor - set(bw.VOL_FAKTOR))
    pruefe("D", "Jede Muster-Strategie hat eine EIGENE Volumenhuerde",
           not ohne_huerde,
           (", ".join(ohne_huerde) + f" -> Rueckfall {bw.VOL_FAKTOR_FALLBACK}")
           if ohne_huerde else "")

    # Die Mappe: keine Ausreisser
    mappe = WURZEL / "kaufpunkte_aktuell.xlsx"
    if mappe.exists():
        d = pd.read_excel(mappe)
        ueber = eng = falschherum = ziel_falsch = 0
        paare = 0
        for _, r in d.iterrows():
            for i in (1, 2, 3):
                kp, st, zl = (r[f"KP{i} Preis"], r[f"KP{i} Stop"],
                              r.get(f"KP{i} Ziel"))
                if pd.isna(kp) or pd.isna(st) or kp <= 0:
                    continue
                paare += 1
                risk = (kp - st) / kp * 100
                if risk > 10 + 1e-6:
                    ueber += 1
                if st >= kp:
                    falschherum += 1
                if risk < 0.05:
                    eng += 1
                if zl is not None and not pd.isna(zl) and zl <= kp:
                    ziel_falsch += 1
        pruefe("D", "Kein Kaufpunkt ueber dem Zehn-Prozent-Deckel",
               ueber == 0, f"{ueber} von {paare}")
        pruefe("D", "Kein Stop ueber oder auf dem Kaufpunkt",
               falschherum == 0, f"{falschherum} von {paare}")
        pruefe("D", "Kein Ziel unter dem Kaufpunkt",
               ziel_falsch == 0, f"{ziel_falsch} von {paare}")
        pruefe("D", "Kein sinnlos enger Stop (unter 0,05 %)",
               eng == 0, f"{eng} von {paare}")

    # Die Namen in der Mappe muessen der Waechter und das Exit-Regelwerk kennen
    if mappe.exists():
        d = pd.read_excel(mappe)
        namen = set()
        for _, r in d.iterrows():
            for i in (1, 2, 3):
                s = r[f"KP{i} Strategie"]
                if isinstance(s, str) and not s.startswith("Fallback"):
                    namen.add(s)
        unbekannt = sorted(namen - set(ex.STRUKTURPUNKT))
        pruefe("D", "Jeder Name IN DER MAPPE ist dem Exit-Regelwerk bekannt",
               not unbekannt, ", ".join(unbekannt))


# ---------------------------------------------------------------------------
# E — Wege des Waechters
# ---------------------------------------------------------------------------

def block_e():
    ueberschrift("E — WEGE DES WAECHTERS")
    import breakout_watcher as bw

    item = {"ticker": "TEST", "firma": "Testfirma AG", "strategie": "Darvas Box",
            "kaufpunkt": 100.0, "stop": 92.0, "ziel": 130.0}
    quote = {"close": 104.0, "volume": 3_000_000, "avg_volume": 1_000_000}
    t = bw.pruefe_breakout(item, quote)
    pruefe("E", "Ausbruch wird erkannt", t is not None)
    pruefe("E", "Kurs unter dem Kaufpunkt ergibt keinen Treffer",
           bw.pruefe_breakout(item, {**quote, "close": 99.0}) is None)
    # Weit darueber ist SEIT 11.08.2026 kein None mehr, sondern eine
    # eigene Meldung. Kein Kaufsignal bleibt es trotzdem.
    weit = bw.pruefe_breakout(item, {**quote, "close": 130.0})
    pruefe("E", "Kurs zu weit darueber ist KEIN Ausbruch",
           weit is not None and weit.get("uebersprungen") is True)

    # Die drei Volumen-Zustaende muessen SICHTBAR verschieden sein
    grund = {**item, "kurs": 101.0, "ueber_pct": 1.0, "vol_ratio": None,
             "vol_pct": None, "vol_noetig": 1.0, "vol_ok": None,
             "vol_anteil": None, "strategien": ["Darvas Box"]}
    texte = {
        "bestaetigt": bw.format_treffer({**grund, "vol_ratio": 2.0,
                                         "vol_pct": 100.0, "vol_ok": True}),
        "nicht bestaetigt": bw.format_treffer({**grund, "vol_ratio": 0.6,
                                               "vol_pct": -40.0, "vol_ok": False}),
        "nicht verifizierbar": bw.format_treffer(
            {**grund, "vol_nicht_verifizierbar": True}),
        "nicht bewertbar": bw.format_treffer(grund),
    }
    pruefe("E", "Vier Volumen-Zustaende ergeben vier verschiedene Texte",
           len({v.splitlines()[1] for v in texte.values()}) == 4)
    pruefe("E", "'NICHT VERIFIZIERBAR' steht woertlich in der Meldung",
           "NICHT VERIFIZIERBAR" in texte["nicht verifizierbar"])
    pruefe("E", "'nicht verifizierbar' faellt nicht mit 'nicht bestaetigt' zusammen",
           texte["nicht verifizierbar"] != texte["nicht bestaetigt"])

    # Insider: mehrere Handelstage je Lauf (Befund 26.08.2026 - der
    # Scanner fragte nur den heutigen Index ab, den es nie gibt)
    import insider_edgar as ie
    from datetime import date as _d
    _tage = ie.indextage(_d(2026, 8, 26), 5)
    pruefe("E", "Insider-Lauf nimmt mehrere Handelstage, alt nach neu",
           len(_tage) == 5 and _tage[-1] == _d(2026, 8, 26)
           and _tage == sorted(_tage))
    pruefe("E", "Insider-Lauf ueberspringt Wochenenden",
           all(t.weekday() < 5 for t in ie.indextage(_d(2026, 8, 24), 5)))
    pruefe("E", "Montag blickt ueber das Wochenende zurueck",
           ie.indextage(_d(2026, 8, 24), 2) == [_d(2026, 8, 21), _d(2026, 8, 24)])
    _q_ie = pathlib.Path("insider_edgar.py").read_text(encoding="utf-8")
    pruefe("E", "403 auf einen vergangenen Werktag wird als FEHLER gemeldet",
           "vergangener_werktag" in _q_ie and "FEHLER: Tagesindex" in _q_ie)

    # Shakeout-Warteliste ohne Listen-Altlasten (Mathias, 24.08.2026)
    import shakeout as sk
    _wl = {"WEG": {"tage_gewartet": 3}, "BLEIBT": {"tage_gewartet": 3}}
    _rest, _weg = sk.warteliste_bereinigen(_wl, {"BLEIBT"})
    pruefe("E", "Warteliste: Aktien ohne Listenplatz werden entfernt",
           _weg == ["WEG"] and set(_rest) == {"BLEIBT"})
    pruefe("E", "Warteliste: aktive Positionen gelisteter Aktien bleiben",
           _rest.get("BLEIBT", {}).get("tage_gewartet") == 3)
    quelle_ps = pathlib.Path("pattern_scanner.py").read_text(encoding="utf-8")
    pruefe("E", "Nachtscan ruft die Warteliste-Bereinigung",
           "warteliste_bereinigen" in quelle_ps)

    # Ausweich-Marken laufen mit (Mathias, 19.08.2026: "Ich habe den
    # anderen Schalter gemeint") - samt Von-unten-Riegel gegen die
    # Ruecksetzer-Marken (gemessen: 32 Mitlaeufer im Fenster).
    pruefe("E", "watcher.yml ueberwacht die Ausweich-Marken (--alle)",
           "--alle" in pathlib.Path(".github/workflows/watcher.yml")
           .read_text(encoding="utf-8"))
    def _fb(strategie, vortag, kp=100.0, strategien=None):
        return bw.fallback_ohne_riss(
            {"strategie": strategie, "strategien": strategien,
             "vortagesschluss": vortag, "kaufpunkt": kp})
    pruefe("E", "Marke von unten gerissen: wird gemeldet",
           _fb("Fallback: 52W-Hoch-Breakout", 99.0) is False)
    pruefe("E", "Marke, ueber der der Kurs schon gestern stand: still",
           _fb("Fallback: MA50-Pullback", 102.0) is True)
    pruefe("E", "Marke ohne Vortagesschluss: still (114 gegen 6)",
           _fb("Fallback: MA50-Pullback", None) is True)
    pruefe("E", "Muster-Kaufpunkte bleiben vom Riegel unberuehrt",
           _fb("Darvas Box", 102.0) is False)
    pruefe("E", "Muster neben Marke am selben Preis: das Muster zaehlt",
           _fb("Fallback: 20-Tage-Hoch (Pivot)", 102.0,
               strategien=["Fallback: 20-Tage-Hoch (Pivot)",
                           "Rectangle Top"]) is False)

    # Buendelung je Aktie (Mathias, 19.08.2026: "Buendeln mehrerer
    # Kaufpunkte in einer Meldung pro Aktie ist definitiv sinnvoller",
    # nachdem ASC zur Eroeffnung zwei getrennte Meldungen bekam)
    kp1 = {**grund, "vol_ratio": 2.0, "vol_pct": 100.0, "vol_ok": True}
    kp2 = {**grund, "strategie": "VCP", "strategien": ["VCP"],
           "kaufpunkt": 111.2, "kurs": 111.3, "ueber_pct": 0.1,
           "stop": 101.0, "ziel": 130.0,
           "vol_ratio": 0.8, "vol_pct": -20.0, "vol_ok": False}
    fremd = {**grund, "ticker": "ZWEI", "vol_ok": False}
    gr = bw.gruppiere_je_aktie([kp1, fremd, kp2])
    pruefe("E", "Gruppierung: gleiche Aktie zusammen, Reihenfolge bleibt",
           len(gr) == 3 - 1 and len(gr[0]) == 2
           and gr[0][0] is kp1 and gr[0][1] is kp2 and gr[1][0] is fremd)
    pruefe("E", "Ein Kaufpunkt: Meldung unveraendert",
           bw.format_aktie([kp1]) == bw.format_treffer(kp1))
    buendel = bw.format_aktie([kp1, kp2])
    bz = buendel.split("\n")
    pruefe("E", "Buendel-Kopf sagt '2 Kaufpunkte gerissen', Kuerzel einmal",
           "2 Kaufpunkte gerissen" in bz[0] and bz[0].count(grund["ticker"]) == 1)
    pruefe("E", "Jeder Kaufpunkt traegt Unternummer und Musternamen",
           any(z.startswith("1.1 Darvas Box: Kaufpunkt") for z in bz)
           and any(z.startswith("1.2 Volatility Contraction Pattern: Kaufpunkt")
                   for z in bz))
    pruefe("E", "Unternummern folgen der Blocknummer (Block 3: 3.1, 3.2)",
           "3.1 Darvas Box: Kaufpunkt" in bw.format_aktie([kp1, kp2], 3)
           and "3.2 Volatility" in bw.format_aktie([kp1, kp2], 3))
    pruefe("E", "Stop und Ziel stehen je Kaufpunkt (zweimal)",
           sum(1 for z in bz if z.startswith("Stop ")) == 2)
    _alt_ns = bw.termin_nachsatz
    bw.termin_nachsatz = lambda tk: "Termin-Probe unsicher"
    try:
        mit_ns = bw.format_aktie([kp1, kp2])
        pruefe("E", "Termin-Nachsatz steht im Buendel nur EINMAL, am Ende",
               mit_ns.count("Termin-Probe") == 1
               and mit_ns.split("\n")[-1] == "Termin-Probe unsicher")
    finally:
        bw.termin_nachsatz = _alt_ns
    _gesendet = []
    _alt_sende = bw.sende
    bw.sende = lambda topic, titel, absaetze, prio="default": (
        _gesendet.append((titel, list(absaetze))) or True)
    try:
        bw.push("probe", [fremd, kp2, kp1])
        titel_p, abs_p = _gesendet[-1]
        pruefe("E", "push: je Aktie ein Block, bestaetigte Aktie zuerst",
               len(abs_p) == 2 and abs_p[0].startswith(grund["ticker"])
               and abs_p[1].startswith("2. ZWEI"))
        pruefe("E", "Buendel-Kopf OHNE Blocknummer (Mathias: '1er weg')",
               not abs_p[0].startswith("1.")
               and "2 Kaufpunkte gerissen" in abs_p[0].splitlines()[0])
        pruefe("E", "push: Unternummern im Buendel, keine beim Einzel-KP",
               "1.1 " in abs_p[0] and "1.2 " in abs_p[0]
               and "2.1 " not in abs_p[1])
        pruefe("E", "push-Titel zaehlt AKTIEN, nicht Kaufpunkte",
               titel_p.startswith("1 bestätigt, 1 offen"), titel_p)
        _gesendet.clear()
        bw.push_nachtrag("probe", [kp1, kp2])
        titel_n, abs_n = _gesendet[-1]
        pruefe("E", "Nachtrag mehrerer Volumina: Titel nennt die Zahl",
               titel_n.startswith(grund["ticker"]
                                  + ": 2 Volumina jetzt bestätigt")
               and len(abs_n) == 1)
        pruefe("E", "Nachtrag-Buendel traegt die Unternummern 1.1/1.2",
               "1.1 " in abs_n[0] and "1.2 " in abs_n[0])
        _gesendet.clear()
        bw.push_nachtrag("probe", [kp1])
        titel_n1, abs_n1 = _gesendet[-1]
        pruefe("E", "Nachtrag EINES Volumens: gewohntes 'Vol jetzt bestätigt'",
               titel_n1.startswith(grund["ticker"] + ": Vol jetzt bestätigt")
               and "1.1 " not in abs_n1[0])
    finally:
        bw.sende = _alt_sende

    # Risiko-Formel
    import exit_regeln as ex
    r = ex.risiko_pct(100.0, 92.0)
    pruefe("E", "Risiko rechnet vom Kaufpunkt (8 % bei 100/92)",
           abs(r - 8.0) < 1e-9, f"{r:.2f} %")
    try:
        ex.risiko_pct(152.78, 92.47)
        geworfen = False
    except ValueError:
        geworfen = True
    pruefe("E", "Risiko ueber dem Deckel wirft einen Fehler", geworfen)

    # Zusammenlegen gleicher Preise
    zwei = [dict(item), dict(item, strategie="VCP")]
    zusammen = bw._lege_gleiche_preise_zusammen(zwei)
    pruefe("E", "Zwei Muster auf demselben Preis werden zusammengelegt",
           len(zusammen) == 1 and len(zusammen[0]["strategien"]) == 2)
    pruefe("E", "Dabei gewinnt die STRENGERE Volumenhuerde",
           zusammen[0]["strategie"] == "VCP")

    # Schutznetz: zu weiter Stop wird nachgezogen
    weit = [dict(item, stop=50.0)]
    bw._deckel_nachziehen(weit)
    pruefe("E", "Zu weiter Stop aus der Mappe wird nachgezogen",
           abs(weit[0]["stop"] - 90.0) < 0.011, f"Stop {weit[0]['stop']}")

    # UEBERSPRUNGENE KAUFPUNKTE (Gerhard, 11.08.2026, Fall Sea)
    se = {"ticker": "SE", "firma": "Sea Ltd ADR",
          "strategie": "Cup & Handle (Wochenbasis)", "kaufpunkt": 115.91,
          "stop": 104.32, "ziel": None, "nr": 1}
    t = bw.pruefe_breakout(se, {"close": 127.87, "volume": 5e6,
                                "avg_volume": 1.2e6})
    pruefe("E", "Uebersprungener Kaufpunkt wird erkannt statt verschluckt",
           t is not None and t.get("uebersprungen") is True)
    knapp = bw.pruefe_breakout(se, {"close": 120.0, "volume": 5e6,
                                    "avg_volume": 1.2e6})
    pruefe("E", "Knapp darueber (3,5 %) bleibt ein normaler Ausbruch",
           knapp is not None and not knapp.get("uebersprungen"))
    text = bw.format_uebersprungen(t)
    pruefe("E", "Die Meldung sagt ausdruecklich, dass es kein Kaufsignal ist",
           "kein Kaufsignal" in text)
    pruefe("E", "Sie nennt KEIN Volumenurteil (waere ein Signal-Anschein)",
           "BESTÄTIGT" not in text and "Vol " not in text)
    pruefe("E", "Sie nennt das Risiko eines Einstiegs JETZT",
           "18% Risiko" in text, text.splitlines()[2][:60])
    pruefe("E", "Uebersprungene bekommen ein eigenes Schluessel-Vorzeichen",
           bw.UEBERSPRUNGEN_MARKE and bw.UEBERSPRUNGEN_MARKE != bw.NACHTRAG_MARKE)

    # KAPITEL 11 — Red-to-Green Explosive (Mathias, 12.08.2026)
    import red_to_green_explosive as k11
    import red_to_green as k9
    pruefe("E", "Kapitel 11 erkennt Fastly vom 10.08.2026",
           k11.aktien_gap(22.45, 22.96)[0], f"{k11.aktien_gap(22.45, 22.96)[1]} %")
    pruefe("E", "Kapitel 9 haette Fastly NICHT erkannt",
           not k9.aktien_gap(22.45, 22.96)[0])
    pruefe("E", "Kapitel 11 laeuft OHNE Nasdaq-Bedingung",
           "nasdaq_gap_scharf" not in k11.CFG
           and "nasdaq_gap_scharf" in k9.CFG)
    pruefe("E", "Kapitel 11 teilt die Bausteine mit Kapitel 9",
           k11.pruefe is k9.pruefe and k11.punkt_setzen is k9.punkt_setzen)
    pruefe("E", "Der Waechter hat einen eigenen Weg fuer Kapitel 11",
           hasattr(bw, "pruefe_red_to_green_explosive"))
    import exit_regeln as ex11
    pruefe("E", "Kapitel 11 hat einen Strukturpunkt fuer den Stop",
           ex11.STRUKTURPUNKT.get(k11.NAME) is not None,
           str(ex11.STRUKTURPUNKT.get(k11.NAME))[:40])

    # ZWEI NEUE REGELN VON GERHARD (12.08.2026)
    # (1) Unbestaetigtes Volumen melden nur noch drei Muster.
    def stufe(strategie, vol_ok):
        return bw.melde_stufe({"key": "K", "key_best": "B",
                               "vol_ok": vol_ok, "strategie": strategie}, set())
    still = [x for x in ("Darvas Box", "Rectangle Top", "VCP",
                         "Cup & Handle", "Cup & Handle (Wochenbasis)")
             if stufe(x, False) is not None]
    pruefe("E", "Ohne Volumenbestaetigung schweigen die uebrigen Muster",
           not still, ", ".join(still))
    laut = [x for x in ("Red-to-Green", "Red-to-Green Explosive",
                        "High & Tight Flag", "Lücken-Bestätigungstag")
            if stufe(x, False) is None]
    pruefe("E", "Die drei erlaubten melden weiterhin unbestaetigt",
           not laut, ", ".join(laut))
    pruefe("E", "MIT Bestaetigung meldet jedes Muster",
           stufe("Darvas Box", True) == "neu")
    pruefe("E", "'nicht verifizierbar' wird NICHT mitunterdrueckt",
           stufe("Darvas Box", None) == "neu")
    # Unterdrueckt heisst NICHT abgehakt: kommt das Volumen nach, meldet er.
    r = {"key": "K", "key_best": "B", "vol_ok": False, "strategie": "Darvas Box"}
    gemeldet = set()
    bw.melde_stufe(r, gemeldet)
    pruefe("E", "Ein unterdrueckter Ausbruch gilt NICHT als gemeldet",
           "K" not in gemeldet)

    # DAS EINSTIEGSFENSTER ALS ZUSTAND (Mathias, 13.08.2026, Fall MNDY).
    # Er hat sich fuer "das Fenster ist das Fenster" entschieden: Der Kurs
    # darf zurueckkommen, und jeder Wechsel wird gemeldet - hinaus als
    # "uebersprungen", herein als "wieder im Einstiegsfenster".
    #
    # DER FALL, der dazu gefuehrt hat: MNDY stand um 20:59 bei 93,00 und
    # damit 5,10 % ueber dem Kaufpunkt 88,49, zwei Minuten spaeter bei
    # 92,91 und damit 4,99 %. Ergebnis waren zwei einander
    # widersprechende Meldungen ("kein Kaufsignal", dann "Vol
    # BESTAETIGT") fuer neun Cent Kursbewegung.
    D, A = bw.DRIN, bw.DRAUSSEN
    pruefe("E", "Über der Grenze heißt draußen",
           bw.fenster_zustand(0.051, D) == A)
    pruefe("E", "Deutlich darunter heißt drin",
           bw.fenster_zustand(0.030, A) == D)
    # DIE TOTZONE: gemessen an MNDY-Minutendaten haette die Reinform NEUN
    # Meldungen in 22 Minuten erzeugt, mit einem Prozentpunkt Totzone EINE.
    pruefe("E", "In der Totzone bleibt es beim bisherigen Zustand",
           bw.fenster_zustand(0.045, A) is None
           and bw.fenster_zustand(0.045, D) is None)
    pruefe("E", "Beim ERSTEN Blick gilt die Totzone als drin",
           bw.fenster_zustand(0.045, None) == D)
    pruefe("E", "Der genaue Grenzwert zählt noch als drin",
           bw.fenster_zustand(bw.NACHLAUF_GRENZE, D) is not A)

    pruefe("E", "Hinausgehen wird gemeldet",
           bw.fenster_wechsel(A, D) == "verlassen")
    pruefe("E", "Zurückkommen wird gemeldet",
           bw.fenster_wechsel(D, A) == "wiedereintritt")
    pruefe("E", "Gleicher Zustand meldet nichts",
           bw.fenster_wechsel(D, D) is None and bw.fenster_wechsel(A, A) is None)
    pruefe("E", "Ohne Entscheidung (Totzone) meldet nichts",
           bw.fenster_wechsel(None, A) is None)
    # Der Fall Sea (Gerhard, 11.08.2026): 10,3 % Eroeffnungsluecke, der
    # Kaufpunkt wurde NIE angesagt. Der erste Blick ist schon draussen.
    pruefe("E", "Erster Blick schon über der Grenze wird gemeldet (Fall Sea)",
           bw.fenster_wechsel(A, None) == "verlassen")
    pruefe("E", "Erster Blick im Fenster meldet keinen Wiedereintritt",
           bw.fenster_wechsel(D, None) is None)

    # Der ECHTE Tagesverlauf von MNDY, auf die Minute nachgespielt.
    verlauf = [0.004, 0.017, 0.036, 0.049, 0.051, 0.046, 0.050, 0.0489,
               0.051, 0.0457, 0.0535, 0.0489, 0.0507, 0.030]
    zustand, meldungen = None, []
    for u in verlauf:
        neu_z = bw.fenster_zustand(u, zustand)
        w = bw.fenster_wechsel(neu_z, zustand)
        if neu_z:
            zustand = neu_z
        if w:
            meldungen.append(w)
    pruefe("E", "MNDY-Tagesverlauf ergibt genau zwei Meldungen statt neun",
           meldungen == ["verlassen", "wiedereintritt"], meldungen)

    # DER WOCHENRIEGEL, teuer erkauft (13.08.2026, beim Umbau selbst
    # hineingelaufen): Beim ersten Blick eines Tages hat ein Kaufpunkt
    # keinen Vorzustand. Steht der Kurs dann schon ueber der Grenze, gilt
    # das als Wechsel - und OHNE zweiten Riegel meldete jeder Kaufpunkt,
    # der seit Tagen weit oben steht, an jedem Morgen aufs Neue. Gemessen
    # an der echten Mappe waeren das 131 Meldungen an einem Morgen.
    quelle_loop = pathlib.Path("breakout_watcher.py").read_text(encoding="utf-8")
    pruefe("E", "Übersprungen prüft ZUSÄTZLICH das Wochengedächtnis",
           'wechsel == "verlassen"' in quelle_loop
           and 'res["key"] not in schon_gemeldet' in quelle_loop)
    pruefe("E", "Ein Wiedereintritt löst den Wochenriegel wieder",
           "schon_gemeldet.discard(k)" in quelle_loop)

    # DAS UEBERGABEFESTE MELDE-GEDAECHTNIS (18.08.2026, Fall RSG/CRNX):
    # Die Schlussstunde stellte an jedem Handelstag den Cache vom VORTAG
    # wieder her (gesichert wird erst am Laufende) und meldete den halben
    # Tag neu — am 17.08. nachgewiesen an zehn doppelten Ausbruechen und
    # dem doppelten Insider-Grosskauf. Jetzt: Union aus Repo-Datei und
    # Cache, Sicherung ins Repo nach jeder Meldung.
    import tempfile as _tf2
    import pathlib as _pl2
    import json as _json2
    from datetime import date as _d2, timedelta as _td2
    heute_s = _d2.today().isoformat()
    alt_cache, alt_repo = bw.STATE_FILE, bw.REPO_STATE
    with _tf2.TemporaryDirectory() as _o2:
        _op2 = _pl2.Path(_o2)
        bw.STATE_FILE = _op2 / "cache.json"
        bw.REPO_STATE = str(_op2 / "repo.json")
        try:
            # Cache alt (kennt A), Repo frisch (kennt B) -> beide bleiben.
            bw.STATE_FILE.write_text(_json2.dumps(
                {"gemeldet": {"AAA|1": heute_s}}))
            _pl2.Path(bw.REPO_STATE).write_text(_json2.dumps(
                {"gemeldet": {"BBB|1": heute_s}}))
            st = bw.load_state()
            pruefe("E", "Melde-Gedächtnis vereinigt Cache und Repo-Datei",
                   set(st["gemeldet"]) == {"AAA|1", "BBB|1"},
                   sorted(st["gemeldet"]))
            # Insider-Schluessel ueberleben den Freitags-Putz (30 Tage).
            vor10 = (_d2.today() - _td2(days=10)).isoformat()
            vor40 = (_d2.today() - _td2(days=40)).isoformat()
            bw.STATE_FILE.write_text(_json2.dumps({"gemeldet": {
                bw.INSIDER_MARKE + "RSG|pfad_a|0": vor10,
                bw.INSIDER_MARKE + "ALT|pfad_a|0": vor40,
                "AAA|1": vor10}}))
            _pl2.Path(bw.REPO_STATE).write_text("{}")
            st = bw.load_state()
            pruefe("E", "Insider-Meldung überlebt den Freitags-Putz",
                   bw.INSIDER_MARKE + "RSG|pfad_a|0" in st["gemeldet"])
            pruefe("E", "Insider-Meldung verfällt nach 30 Tagen",
                   bw.INSIDER_MARKE + "ALT|pfad_a|0" not in st["gemeldet"])
            pruefe("E", "Gewöhnliche Schlüssel behalten die Wochenfrist",
                   "AAA|1" not in st["gemeldet"])
        finally:
            bw.STATE_FILE, bw.REPO_STATE = alt_cache, alt_repo
    # LEERE YAHOO-KERZEN (18.08.2026): Datum da, Werte NaN — und NaN ist
    # in Python WAHR. Der Vortagesschluss muss dann auf die Mappe
    # zurueckfallen statt NaN weiterzureichen.
    nan = float("nan")
    pruefe("E", "NaN-Vortagesschluss fällt auf den Mappen-Kurs zurück",
           bw.vortagesschluss({"kurs_scan": 361.15}, {"prev_close": nan})
           == 361.15)
    pruefe("E", "NaN in beiden Quellen ergibt None statt NaN",
           bw.vortagesschluss({"kurs_scan": nan}, {"prev_close": nan}) is None)
    pruefe("E", "kam_von_unten mit NaN meldet nicht",
           not bw.kam_von_unten({"kaufpunkt": 100.0, "vortagesschluss": None}))

    # TWELVE-DATA-NACHLADEN hohler Kerzen (Mathias, 18.08.2026) und
    # NACHTRAG ALS NORMALE MELDUNG.
    import pandas as _pd2
    _n = float("nan")
    _idx = _pd2.to_datetime(["2026-08-13", "2026-08-14", "2026-08-17",
                             "2026-08-18"])
    _roh = _pd2.DataFrame({"Open": [1, 1, _n, 1], "High": [1, 1, _n, 1],
                           "Low": [1, 1, _n, 1],
                           "Close": [10.0, 11.0, _n, 13.0],
                           "Volume": [100, 100, _n, 100]}, index=_idx)
    _echt = bw.td_kerze_nachladen
    try:
        bw.td_kerze_nachladen = lambda t, d: {
            "Open": 11.5, "High": 12.5, "Low": 11.4, "Close": 12.0,
            "Volume": 150.0}
        _neu, _v = bw.hohle_kerze_fuellen("ZZ", _roh, 4)
        pruefe("E", "Hohle Kerze wird von Twelve Data gefüllt",
               float(_neu["Close"].iloc[-2]) == 12.0 and _v == 1)
        bw.td_kerze_nachladen = lambda t, d: None
        _neu2, _ = bw.hohle_kerze_fuellen("ZZ", _roh, 4)
        pruefe("E", "Liefert Twelve Data nichts, bleibt der Tag weg "
               "(Mappe übernimmt)", len(_neu2) == 3)
        _, _v3 = bw.hohle_kerze_fuellen("ZZ", _roh, 0)
        pruefe("E", "Ohne Rundenbudget wird nicht abgerufen", _v3 == 0)
        _, _v4 = bw.hohle_kerze_fuellen("ZZ", _roh.dropna(), 4)
        pruefe("E", "Ein Feiertag (Tag fehlt ganz) löst KEIN Nachladen aus",
               _v4 == 0)
    finally:
        bw.td_kerze_nachladen = _echt
    bw._td_kerzen_cache[("PRUEF", "2026-08-17")] = {"Close": 9.99}
    pruefe("E", "Der Tages-Zwischenspeicher kommt vor jedem Netzabruf",
           bw.td_kerze_nachladen("PRUEF", "2026-08-17") == {"Close": 9.99})
    quelle_bw = pathlib.Path("breakout_watcher.py").read_text(encoding="utf-8")
    # ENDSTAND nach Mathias' Klarstellung vom 18.08.2026 ("dort hat es
    # ja einen Sinn"): Der Nachtrag behaelt seinen eigenen Wortlaut,
    # denn er kennzeichnet die Bestaetigung einer schon gemeldeten
    # unbestaetigten Meldung. Wer das aendern will, braucht einen neuen
    # Beschluss von Mathias oder Gerhard.
    pruefe("E", "Der Nachtrag behält seinen eigenen Wortlaut (18.08.)",
           "Vol jetzt best" in quelle_bw
           and "def push_nachtrag" in quelle_bw)

    quelle_w = pathlib.Path(".github/workflows/watcher.yml").read_text(
        encoding="utf-8")
    pruefe("E", "Der Endkommit des Laufs sichert das Melde-Gedächtnis mit",
           "melde_gedaechtnis.json" in quelle_w)

    # DIE EINTRITTSKARTE: kam der Kaufpunkt von UNTEN? (Mathias,
    # 14.08.2026). Ohne sie meldet der Waechter Ruecksetzer-Marken, unter
    # denen der Kurs seit Wochen gar nicht war. Gemessen an diesem Tag:
    # 114 Kaufpunkte lagen ueber der Grenze, 108 davon waren
    # "Fallback: MA50-Pullback", und nur SECHS kamen wirklich von unten.
    #
    # DER FALL SEA (Gerhard, 11.08.2026), mit den echten Zahlen: Schluss
    # am 10.08. 114,80, Kaufpunkt 115,91, Eroeffnung am 11.08. 127,87.
    sea = {"ticker": "SE", "nr": 1, "strategie": "Cup & Handle (Wochenbasis)",
           "kaufpunkt": 115.91, "kurs": 127.87, "vortagesschluss": 114.80}
    pruefe("E", "Sea kam von unten und wird gemeldet",
           bw.kam_von_unten(sea) and bw.melde_uebersprungen(sea, "verlassen", set()))
    # DER FALL TEAM, ebenfalls echt: Kurs 165,98, Ruecksetzer-Marke 98,21.
    team = {"ticker": "TEAM", "nr": 3, "strategie": "Fallback: MA50-Pullback",
            "kaufpunkt": 98.21, "kurs": 167.40, "vortagesschluss": 165.98}
    pruefe("E", "Eine Rücksetzer-Marke, unter der der Kurs nie war, "
           "meldet NICHTS",
           not bw.kam_von_unten(team)
           and not bw.melde_uebersprungen(team, "verlassen", set()))
    # NICHT nach Muster ausgeschlossen: ETON kam am 14.08. aus einer
    # Fallback-Marke und war trotzdem ein echter Fall (gestern 40,80,
    # Kaufpunkt 50,23, heute 58,12).
    eton = {"ticker": "ETON", "nr": 1,
            "strategie": "Fallback: 52W-Hoch-Breakout",
            "kaufpunkt": 50.23, "kurs": 58.12, "vortagesschluss": 40.80}
    pruefe("E", "Auch eine Fallback-Marke wird gemeldet, wenn sie von "
           "unten kam",
           bw.melde_uebersprungen(eton, "verlassen", set()))
    pruefe("E", "Ohne Vortagesschluss wird nicht gemeldet",
           not bw.kam_von_unten({**sea, "vortagesschluss": None}))
    # ZWEI QUELLEN fuer den Vortagesschluss (Mathias, 14.08.2026). Die
    # Mappe traegt ihn selbst mit: Der Nachtlauf rechnet nach dem New
    # Yorker Schluss, sein Kurs IST der Vortagesschluss. Gegengeprueft an
    # TEAM: Mappe 165,98, echter Schluss 165,98.
    pruefe("E", "Der Kursabruf ist die erste Quelle",
           bw.vortagesschluss({"kurs_scan": 99.0}, {"prev_close": 165.98})
           == 165.98)
    pruefe("E", "Fehlt er, springt der Kurs aus der Mappe ein",
           bw.vortagesschluss({"kurs_scan": 165.98}, {}) == 165.98)
    pruefe("E", "Fallen BEIDE aus, wird geschwiegen statt gemeldet",
           bw.vortagesschluss({}, {}) is None
           and not bw.kam_von_unten({**sea, "vortagesschluss": None}))
    # Der Sinn der zweiten Quelle: Auch bei ausgefallenem Kursabruf bleibt
    # die Ruecksetzer-Marke stumm, statt durch die Hintertür zu melden.
    pruefe("E", "Rücksetzer-Marke bleibt auch ohne Kursabruf stumm",
           not bw.kam_von_unten(
               {"kaufpunkt": 98.21,
                "vortagesschluss": bw.vortagesschluss({"kurs_scan": 165.98}, {})}))
    pruefe("E", "Die Mappe wird mit dem Kurs eingelesen",
           "kurs_scan" in pathlib.Path("breakout_watcher.py").read_text(
               encoding="utf-8"))
    pruefe("E", "Genau auf dem Kaufpunkt geschlossen zählt nicht als "
           "von unten",
           not bw.kam_von_unten({**sea, "vortagesschluss": 115.91}))
    pruefe("E", "Ohne Wechsel keine Meldung",
           not bw.melde_uebersprungen(sea, None, set()))
    pruefe("E", "Schon angesagt heißt nicht noch einmal",
           not bw.melde_uebersprungen(
               sea, "verlassen", {bw.uebersprungen_schluessel(sea)}))
    # Mathias ausdruecklich am 14.08.2026: "Die Uebersprungenmeldung
    # stoert uns nicht, im Gegenteil, genau so wollen wir es haben." Ein
    # bereits gemeldeter AUSBRUCH darf sie also NICHT unterdruecken.
    pruefe("E", "Ein bereits gemeldeter Ausbruch unterdrückt sie NICHT",
           bw.melde_uebersprungen(sea, "verlassen",
                                  {bw.ausbruch_schluessel(sea)}))

    # Die Meldung sagt, dass es ein Wiedereintritt ist und KEIN Ausbruch.
    probe_w = {"ticker": "AAA", "firma": "Alpha AG", "strategie": "Darvas Box",
               "kaufpunkt": 10.0, "kurs": 10.3, "ueber_pct": 3.0, "stop": 9.0,
               "ziel": 12.0, "vol_ok": True, "vol_pct": 60.0, "vol_noetig": 1.0}
    erste = bw.format_wiedereintritt(probe_w).splitlines()[0]
    pruefe("E", "Wiedereintritt ist als solcher beschriftet",
           "wieder im Einstiegsfenster" in erste, erste[:70])
    pruefe("E", "Die gewöhnliche Meldung trägt den Zusatz NICHT",
           "wieder im Einstiegsfenster"
           not in bw.format_treffer(probe_w).splitlines()[0])
    pruefe("E", "Der Wiedereintritt nennt Kurs, Stop und Risiko",
           "Kaufpunkt" in bw.format_wiedereintritt(probe_w)
           and "Stop" in bw.format_wiedereintritt(probe_w))

    # ZWEI LISTEN (Gerhard, 14.08.2026): Darvas ausschliesslich auf der
    # Darvas-Liste, alle anderen Muster auf beiden. An echten Kursdaten
    # gegengeprueft: INCY liefert in der grossen Liste nur Cup and Handle,
    # in der Darvas-Liste zusaetzlich die Darvas Box.
    import listen as _li
    import tempfile as _tf
    import pathlib as _pl
    with _tf.TemporaryDirectory() as _o:
        _op = _pl.Path(_o)
        (_op / "g.csv").write_text("\n".join(["Ticker", "AAA", "BBB", ""]),
                                   encoding="utf-8")
        (_op / "d.csv").write_text("\n".join(["Ticker", "BBB", "CCC", ""]),
                                   encoding="utf-8")
        _g, _d = str(_op / "g.csv"), str(_op / "d.csv")
        pruefe("E", "Beide Listen werden zusammen überwacht",
               {t for t, _ in _li.alle_ticker(_g, _d)} == {"AAA", "BBB", "CCC"})
        pruefe("E", "Darvas NUR auf der Darvas-Liste",
               _li.darf_darvas("CCC", _d) and not _li.darf_darvas("AAA", _d))
        pruefe("E", "Eine Aktie in beiden Listen darf Darvas",
               _li.darf_darvas("BBB", _d))
        MU = ["VCP", "Darvas Box", "Rectangle Top"]
        pruefe("E", "Die große Liste verliert NUR Darvas",
               _li.erlaubte_muster("AAA", MU, _d) == ["VCP", "Rectangle Top"])
        pruefe("E", "Auf der Darvas-Liste laufen alle Muster",
               _li.erlaubte_muster("CCC", MU, _d) == MU)
        pruefe("E", "Fehlende Darvas-Liste wird gemeldet, nicht verschwiegen",
               "Darvas-Liste fehlt" in (_li.fehlende_liste(
                   _g, str(_op / "weg.csv")) or ""))
    # Der Scanner muss die Erlaubnis wirklich durchreichen.
    import inspect as _in
    import pattern_scanner as _ps
    pruefe("E", "Der Scanner ruft den Darvas-Detektor nur bei Erlaubnis",
           "darvas_erlaubt" in _in.signature(_ps.analyze).parameters
           and "if darvas_erlaubt" in _in.getsource(_ps.analyze))

    # (2) Zahlen-Termine
    import zahlen_termine as zt
    from datetime import date as _d
    proben = {"AAA": {"datum": "2026-08-12", "uhrzeit": "16:00",
                      "lage": "nachboerslich"}}
    pruefe("E", "Zahlen heute Abend werden vermerkt",
           "HEUTE nach Börsenschluss" in (zt.hinweis("AAA", _d(2026, 8, 12),
                                                     proben) or ""))
    pruefe("E", "Ohne Termin kein Vermerk",
           zt.hinweis("ZZZ", _d(2026, 8, 12), proben) is None)
    # DER VERMERK IN DER KOPFZEILE (Mathias, 13.08.2026).
    # Vorher stand hier eine Pruefung, die nur im Bytecode nachsah, ob ein
    # Name vorkommt. Die haette JEDE Umstellung ueberlebt, ohne etwas zu
    # merken — und genau das ist beim Umbau dann auch passiert. Jetzt wird
    # die Meldung wirklich gebaut und nachgesehen, WO der Satz steht.
    _kopf, _hin, _vor = zt.kopf_hinweis, zt.hinweis, zt.vorbehalt
    zt.kopf_hinweis = lambda t, h=None, te=None: (
        "Quartalszahlen nach Börsenschluss" if t == "AAA" else None)
    zt.hinweis = lambda t, h=None, te=None: None
    zt.vorbehalt = lambda t, te=None: None
    try:
        probe = {"ticker": "AAA", "firma": "Alpha AG", "strategie": "Darvas Box",
                 "kaufpunkt": 10.0, "kurs": 10.4, "ueber_pct": 4.0,
                 "stop": 9.0, "ziel": 12.0, "vol_ok": True, "vol_pct": 60.0,
                 "vol_noetig": 1.0}
        formen = {
            "Ausbruch": bw.format_treffer(probe),
            "uebersprungen": bw.format_uebersprungen(probe),
            "Red-to-Green": bw.format_r2g(
                {"ticker": "AAA", "firma": "Alpha AG", "kurs": 10.4,
                 "vortagesschluss": 10.1, "minute": 60,
                 "signatur": {"sprung_pct": 200.0, "anflug_pct": -3.0,
                              "in_fruehphase": False}}),
            "Gap and Go": bw.format_gapgo(
                {"ticker": "AAA", "firma": "Alpha AG", "bestaetigt": True,
                 "frueh": False, "tages_ratio": 5.4, "gap": 0.08,
                 "base_spanne": 0.2, "flat_base": True, "pos": 0.9,
                 "kp": 11.0, "stop": 9.9, "stop_quelle": "struktur"}),
        }
        for name, text in formen.items():
            erste = text.splitlines()[0]
            pruefe("E", f"'Quartalszahlen' in der ersten Zeile: {name}",
                   "Quartalszahlen" in erste, erste[:70])
        pruefe("E", "Kein 'bringt heute' mehr (Mathias: frisst Platz)",
               all("bringt heute" not in t for t in formen.values()))
        # DER NTFY-TITEL BLEIBT FREI DAVON (Mathias, 13.08.2026: die
        # Sammelmeldung kommt sonst durcheinander). Das wird hier
        # ausdruecklich geprueft, damit es niemand versehentlich
        # wieder einbaut.
        titel = (f"{1} bestätigt" + bw.tagesanteil_titel([probe]))
        pruefe("E", "Der ntfy-Titel nennt KEINE Zahlen-Termine",
               "Quartalszahlen" not in titel, titel)
        # Und er darf NICHT zusaetzlich weiter unten stehen.
        rest = "\n".join(formen["Ausbruch"].splitlines()[1:])
        pruefe("E", "Der Vermerk steht nur EINMAL in der Meldung",
               "Quartalszahlen" not in rest)
        # KEINE EMOJIS IN MELDUNGEN (Mathias, 13.08.2026: "Raketen,
        # Diagramme etc. nerven nur"). Zwei Quellen, beide geprueft:
        #   a) buchstaebliche Zeichen in Titel und Text
        #   b) die ntfy-Kopfzeile "Tags" - daraus baut ntfy die Bildchen,
        #      im Quelltext sieht man dort nur harmlose Woerter wie
        #      "rocket". Genau deshalb faellt das beim Lesen nicht auf
        #      und gehoert geprueft.
        import re as _re
        bildzeichen = _re.compile(
            "[🀀-🫿←-⇿⌀-➿"
            "⤀-⥿⬀-⯿️]")
        alle_texte = list(formen.values()) + [
            bw.format_gapgo({"ticker": "AAA", "firma": "Alpha AG",
                             "bestaetigt": False, "frueh": True,
                             "tages_ratio": 3.0, "gap": 0.09,
                             "base_spanne": None, "flat_base": False,
                             "pos": 0.5, "kp": 11.0, "stop": 9.9,
                             "stop_quelle": "struktur"})]
        gefunden = [t[:40] for t in alle_texte if bildzeichen.search(t)]
        pruefe("E", "Keine Bildzeichen im Meldungstext", not gefunden,
               "; ".join(gefunden))
        quelle = (pathlib.Path("breakout_watcher.py").read_text(encoding="utf-8")
                  + pathlib.Path("wartung.py").read_text(encoding="utf-8"))
        # Gesucht wird '"Tags":' MIT Doppelpunkt: So steht es nur im
        # echten Kopfzeilen-Verzeichnis. Ohne ihn fand die Pruefung ihre
        # eigenen Kommentare wieder und schlug grundlos an.
        pruefe("E", 'Keine "Tags"-Kopfzeile an ntfy (daraus entstehen Emojis)',
               '"Tags":' not in quelle)

        # Ohne Termin bleibt die Kopfzeile unveraendert.
        ohne = bw.format_treffer(dict(probe, ticker="ZZZ"))
        pruefe("E", "Ohne Termin kein Zusatz im Kopf",
               "Quartalszahlen" not in ohne)
    finally:
        zt.kopf_hinweis, zt.hinweis, zt.vorbehalt = _kopf, _hin, _vor

    # Handelszeit-Sperre
    from datetime import datetime as dt
    from zoneinfo import ZoneInfo
    NY = ZoneInfo("America/New_York")
    offen, _ = bw.markt_offen(dt(2026, 8, 10, 11, 0, tzinfo=NY))
    zu, _ = bw.markt_offen(dt(2026, 8, 10, 16, 30, tzinfo=NY))
    we, _ = bw.markt_offen(dt(2026, 8, 8, 11, 0, tzinfo=NY))
    pruefe("E", "Handelszeit-Sperre: offen/zu/Wochenende",
           offen and not zu and not we)


# ---------------------------------------------------------------------------
# F — Exit-Regelwerk
# ---------------------------------------------------------------------------

def block_f():
    ueberschrift("F — EXIT-REGELWERK: sind alle Ausgaenge erreichbar?")
    import exit_regeln as ex

    def pos(**kw):
        grund = dict(symbol="T", einstieg=100.0, einstieg_index=0,
                     struktur_stop=95.0, hoechstkurs=100.0,
                     aktueller_stop=95.0, strategie="Darvas Box")
        grund.update(kw)
        return ex.Position(**grund)

    faelle = {
        "halten": (pos(), 102.0, 5),
        "stop_raus": (pos(), 94.0, 5),
        "teilverkauf": (pos(hoechstkurs=120.0), 120.0, 30),
    }
    # pruefe_exit liefert (aktion, begruendung, position).
    for erwartet, (p, kurs, tag) in faelle.items():
        aktion, grund, _ = ex.pruefe_exit(p, kurs, tag)
        pruefe("F", f"Ausgang '{erwartet}' erreichbar", aktion == erwartet,
               f"kam: {aktion} — {grund[:50]}")

    # Round-Trip: ein Gewinn von ueber 20 % verpufft wieder
    # ist_round_trip verlangt schlusskurs <= einstieg — 'zurueck auf den
    # Einstieg'. Mit 100,5 lag mein erster Versuch knapp darueber.
    p = pos(hoechstkurs=125.0, halteregel_aktiv=True)
    aktion, grund, _ = ex.pruefe_exit(p, 100.0, 10)
    pruefe("F", "Ausgang 'round_trip_raus' erreichbar",
           aktion == "round_trip_raus", f"kam: {aktion} — {grund[:50]}")

    # Trail: nach Teilverkauf laeuft der Rest unter dem MA
    p = pos(hoechstkurs=130.0, teilverkauft=True, aktueller_stop=100.0)
    aktion, grund, _ = ex.pruefe_exit(p, 108.0, 40, ma21=112.0, ma50=105.0)
    pruefe("F", "Ausgang 'trail_raus' erreichbar",
           aktion == "trail_raus", f"kam: {aktion} — {grund[:50]}")

    # Der Deckel
    s, q = ex.berechne_initialen_stop(100.0, 82.0)
    pruefe("F", "Deckel greift bei weitem Strukturpunkt",
           q == "deckel" and s == 90.0, f"{s} ({q})")
    s, q = ex.berechne_initialen_stop(100.0, 96.0)
    pruefe("F", "Struktur gewinnt innerhalb des Deckels",
           q == "struktur" and s == 96.0, f"{s} ({q})")

    # Die Invariante ueber viele Kurse
    schlecht = []
    for cent in range(50, 200000, 271):
        kp = cent / 100
        for stru in (None, kp * 0.4, kp * 0.9, kp * 0.97):
            st, _ = ex.berechne_initialen_stop(kp, stru)
            try:
                ex.risiko_pct(kp, st)
            except ValueError:
                schlecht.append((kp, stru, st))
    pruefe("F", "Kein Kurs erzeugt einen Stop ueber dem Deckel",
           not schlecht, f"{len(schlecht)} Faelle")


# ---------------------------------------------------------------------------
# G — Volumenformel
# ---------------------------------------------------------------------------

def block_g():
    ueberschrift("G — VOLUMENFORMEL")
    import volumen

    volumen.lade_kurven(leise=True)
    kurven = volumen._kurven or {}
    pruefe("G", "Kurvenspeicher ist gefuellt", len(kurven) > 50,
           f"{len(kurven)} Aktien")

    # Monotonie und Randwerte fuer JEDE Kurve
    kaputt = []
    for t, k in kurven.items():
        stellen = sorted(k)
        if k[stellen[0]] != 0.0 or abs(k[stellen[-1]] - 1.0) > 1e-9:
            kaputt.append((t, "Rand"))
            continue
        if any(k[a] > k[b] + 1e-9 for a, b in zip(stellen, stellen[1:])):
            kaputt.append((t, "nicht monoton"))
    pruefe("G", "Jede Kurve faengt bei 0 an, endet bei 1 und steigt monoton",
           not kaputt, f"{len(kaputt)} kaputt: {kaputt[:3]}")

    beispiel = next(iter(kurven.values()))
    pruefe("G", "EOD ohne Kurve rechnet (F=1)",
           volumen.volume_pct_change(150_000, 100_000, None, None) is not None)
    pruefe("G", "Intraday OHNE Kurve ergibt None (nicht verifizierbar)",
           volumen.volume_pct_change(70_000, 100_000, None, 30) is None)
    pruefe("G", "Intraday MIT Kurve rechnet",
           volumen.volume_pct_change(70_000, 100_000, beispiel, 30) is not None)
    pruefe("G", "Eine Aktie im ueblichen Tempo zeigt rund 0 %",
           abs(volumen.volume_pct_change(
               volumen.tagesanteil(120, beispiel) * 1e6, 1e6, beispiel, 120)) < 1.0)

    # Der laufende Tag darf nie in eine Kurve
    from zoneinfo import ZoneInfo
    tag, zu = volumen._ny_tag_und_schluss(
        datetime(2026, 8, 10, 15, 55, tzinfo=ZoneInfo("America/New_York")))
    pruefe("G", "15:55 New York gilt NICHT als Handelsschluss", not zu)
    _, zu2 = volumen._ny_tag_und_schluss(
        datetime(2026, 8, 10, 16, 5, tzinfo=ZoneInfo("America/New_York")))
    pruefe("G", "16:05 New York gilt als Handelsschluss", zu2)

    # Deckt der Speicher die Wochenliste ab?
    import pandas as pd
    import listen as _listen
    liste = set(t for t, _ in _listen.alle_ticker(
        haupt=str(WURZEL / "finviz_3.csv"),
        darvas=str(WURZEL / "darvas.csv"))) | set(pd.read_csv(
            WURZEL / "finviz_3.csv")["Ticker"]
                .astype(str).str.upper())
    datei = json.loads((WURZEL / "volumenkurven.json").read_text(encoding="utf-8"))
    ohne = liste - set(datei["aktien"]) - set(datei["nicht_verifizierbar"])
    pruefe("G", "Jede Aktie der Liste hat eine Kurve oder gilt als nicht pruefbar",
           not ohne, f"{len(ohne)} offen: {sorted(ohne)[:5]}")


# ---------------------------------------------------------------------------
# H — Betrieb
# ---------------------------------------------------------------------------

def block_h():
    ueberschrift("H — BETRIEB: Ablaeufe, Einstellungen, Datenlage")
    import yaml

    for p in sorted((WURZEL / ".github" / "workflows").glob("*.yml")):
        try:
            d = yaml.safe_load(p.read_text(encoding="utf-8"))
            grp = (d.get("concurrency") or {})
            hat = bool(grp.get("group") if isinstance(grp, dict) else grp)
            pruefe("H", f"{p.name}: gueltig und mit Doppellauf-Sperre",
                   bool(d) and hat, "" if hat else "KEINE concurrency-Gruppe")
        except Exception as e:
            pruefe("H", f"{p.name}: gueltig", False, f"{type(e).__name__}: {e}")

    try:
        from config import pruefe_config
        pruefe("H", "Einstellungen in sich stimmig", pruefe_config() is True)
    except Exception as e:
        pruefe("H", "Einstellungen in sich stimmig", False,
               f"{type(e).__name__}: {e}")

    # Datenlage: ist die Mappe frisch genug fuer heute?
    # GEGEN DAS REPO messen, nicht gegen den lokalen Klon. Der kann
    # veraltet sein, und dann meldet die Pruefung einen Ausfall, den es
    # gar nicht gibt — genau so am 11.08.2026 passiert (34,8 Stunden
    # gemeldet, in Wahrheit lief der Nachtscan puenktlich).
    import subprocess as sp
    sp.run(["git", "fetch", "-q", "origin", "main"], cwd=WURZEL,
           capture_output=True, text=True)
    r = sp.run(["git", "log", "-1", "--format=%ct", "origin/main", "--",
                "kaufpunkte_aktuell.xlsx"],
               capture_output=True, text=True, cwd=WURZEL)
    try:
        alter = (datetime.now(timezone.utc)
                 - datetime.fromtimestamp(int(r.stdout.strip()), timezone.utc))
        pruefe("H", "Kaufpunkte-Mappe hoechstens 24 Stunden alt",
               alter < timedelta(hours=24),
               f"{alter.total_seconds()/3600:.1f} Stunden")
    except Exception:
        pruefe("H", "Alter der Kaufpunkte-Mappe feststellbar", False)

    for datei in ("volumenkurven.json", "fokusliste.json",
                  "shakeout_warteliste.json"):
        pruefe("H", f"{datei} vorhanden und lesbar",
               (WURZEL / datei).exists()
               and isinstance(json.loads((WURZEL / datei).read_text(
                   encoding="utf-8")), (dict, list)))
    # positionen.json DARF fehlen, solange keine Position offen ist —
    # die Datei entsteht erst beim ersten Einstieg. Geprueft wird
    # deshalb, ob das Laden sauber durchlaeuft, nicht ob die Datei da ist.
    try:
        import positionen
        bestand = positionen.laden()
        pruefe("H", "Positionsverwaltung laedt (Datei darf fehlen)",
               isinstance(bestand, (dict, list)),
               f"{len(bestand)} offene Position(en)")
    except Exception as e:
        pruefe("H", "Positionsverwaltung laedt (Datei darf fehlen)", False,
               f"{type(e).__name__}: {e}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Das ganze Regelwerk pruefen.")
    ap.add_argument("--ohne-netz", action="store_true",
                    help="Block C (echte Kursdaten) auslassen")
    ap.add_argument("--aktien", type=int, default=40,
                    help="Wie viele Aktien fuer Block C (Vorgabe 40)")
    args = ap.parse_args()

    print(f"GESAMTPRUEFUNG — {datetime.now():%d.%m.%Y %H:%M}")
    block_a()
    block_b()
    namen = block_c(args.aktien) if not args.ohne_netz else None
    block_d(namen)
    block_e()
    block_f()
    block_g()
    block_h()

    ueberschrift("ZUSAMMENFASSUNG")
    fehler = [(b, n, z) for b, n, ok, z in ERGEBNISSE if not ok]
    je_block = {}
    for b, n, ok, z in ERGEBNISSE:
        a, g = je_block.get(b, (0, 0))
        je_block[b] = (a + (1 if ok else 0), g + 1)
    for b in sorted(je_block):
        ok, ges = je_block[b]
        print(f"  Block {b}: {ok} von {ges} bestanden"
              + ("" if ok == ges else "   <-- FEHLER"))
    print(f"\n{len(ERGEBNISSE)} Pruefungen, {len(fehler)} Fehler.")
    if fehler:
        print("\nWAS NICHT STIMMT:")
        for b, n, z in fehler:
            print(f"  [{b}] {n}" + (f" — {z}" if z else ""))
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
