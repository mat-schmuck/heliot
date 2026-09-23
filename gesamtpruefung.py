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


def nennen(treffer, hoechstens=6):
    """Nennt die Betroffenen beim Namen statt bloss ihre Anzahl.

    WOZU (Mathias, 07.09.2026): Eine Meldung wie "3 von 419" sagt nicht,
    WELCHE drei, und genau daran ist der CRNX-Befund vorbeigelaufen. Die
    uebernommene Crinetics-Aktie stand mit eingefrorenem Kurs in der
    Mappe und erzeugte drei Kaufpunkte mit hauchduennem Stop; die Zahl
    allein liess offen, ob das drei verschiedene Aktien sind oder
    dreimal dieselbe. Mit den Namen davor sieht man den Fall sofort.

    Sind es sehr viele, wird gekuerzt: Eine Zeile, die ueber den Rand
    laeuft, liest niemand mehr."""
    if len(treffer) <= hoechstens:
        return "; ".join(treffer)
    return ("; ".join(treffer[:hoechstens])
            + f"; und {len(treffer) - hoechstens} weitere")


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
                    "insider_scanner", "insider_edgar", "listen",
                    "earnings_pullback", "kell_zyklus", "ema_crossback",
                    "konsens_einfrieren",
                    # Gerhards Antworten vom 12.09.2026
                    "rs_universum", "sektor_rangliste", "abendbericht",
                    "ibd_ratings",
                    # Nachschlagen (Mathias, 13.09.2026)
                    "nachschlagen",
                    # Wochenputz und Anmeldung (Mathias, 13.09.2026)
                    "wochenputz", "zugang",
                    # Scanner-Reiter (Mathias, 14.09.2026)
                    "scanner_daten", "scanner_ansicht", "scanner_noetig",
                    # Etappe 2, technische Kennzahlen (Gerhard, 13.09.2026)
                    "kennzahlen_technik",
                    # Etappe 3, Marktbreite und Marktphase (Gerhard, 13.09.2026)
                    "marktbreite",
                    # Etappe 4, fundamentale Kennzahlen (Gerhard, 13.09.2026)
                    "kennzahlen_fundament",
                    # Etappe 5, Konsens (Gerhard, 13.09.2026)
                    "kennzahlen_konsens",
                    # Etappe 7, Short-Daten (Gerhard, 13.09.2026)
                    "kennzahlen_short",
                    # Etappe 6, Industry Group RS und Zuordnungsliste (Gerhard, 13.09.2026)
                    "kennzahlen_gruppen", "zuordnung_bauen",
                    # Eigene Module nach einem Push frisch halten (Befund 17.09.2026)
                    "frischhalten",
                    # Knoepfe fuer die Ablaeufe (Gerhard, 20.09.2026, S8)
                    "ablaeufe",
                    # Chartmuster der Etappe 1 (Gerhard, 20.09.2026)
                    "chartmuster",
                    # Die sechs Alarm-Muster (Gerhard, 22.09.2026, O1 bis O10)
                    "alarm_muster",
                    # Die Signale als JSON fuer den degirobot (23.09.2026)
                    "bot_kanal",
                    # Katalog der EODHD-Daten (Gerhard, 20.09.2026, S11)
                    "eodhd_katalog"]
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
        # GESAMMELT WIRD DER FALL, NICHT DIE ZAHL (Mathias, 07.09.2026):
        # Jeder Treffer traegt Ticker, Kaufpunkt-Nummer, Strategie und die
        # Werte, an denen er scheitert. Vorher stand hier nur ein Zaehler,
        # und "3 von 419" verriet nicht, dass alle drei zu CRNX gehoerten.
        ueber, eng, falschherum, ziel_falsch = [], [], [], []
        paare = 0
        for _, r in d.iterrows():
            tick = str(r.get("Ticker", "?"))
            for i in (1, 2, 3):
                kp, st, zl = (r[f"KP{i} Preis"], r[f"KP{i} Stop"],
                              r.get(f"KP{i} Ziel"))
                if pd.isna(kp) or pd.isna(st) or kp <= 0:
                    continue
                paare += 1
                strat = r.get(f"KP{i} Strategie")
                wo = f"{tick} KP{i}"
                if isinstance(strat, str) and strat:
                    wo += f" ({strat})"
                risk = (kp - st) / kp * 100
                if risk > 10 + 1e-6:
                    ueber.append(f"{wo}: {risk:.2f} % Risiko")
                if st >= kp:
                    falschherum.append(
                        f"{wo}: Stop {st:.2f} nicht unter Kaufpunkt {kp:.2f}")
                # NUR positive Risiken (Befund beim Umbau, 07.09.2026):
                # Bei einem Stop UEBER dem Kaufpunkt ist risk negativ und
                # damit ebenfalls kleiner als 0,05 — dieselbe Zeile stand
                # dann unter zwei Namen. Der Fall hat seine eigene
                # Pruefung eine Zeile darueber.
                if 0 <= risk < 0.05:
                    eng.append(f"{wo}: Kaufpunkt {kp:.2f}, Stop {st:.2f}, "
                               f"also nur {risk:.3f} % Risiko")
                if zl is not None and not pd.isna(zl) and zl <= kp:
                    ziel_falsch.append(
                        f"{wo}: Ziel {zl:.2f} nicht ueber Kaufpunkt {kp:.2f}")
        for _name, _treffer in (
                ("Kein Kaufpunkt ueber dem Zehn-Prozent-Deckel", ueber),
                ("Kein Stop ueber oder auf dem Kaufpunkt", falschherum),
                ("Kein Ziel unter dem Kaufpunkt", ziel_falsch),
                ("Kein sinnlos enger Stop (unter 0,05 %)", eng)):
            pruefe("D", _name, not _treffer,
                   f"{len(_treffer)} von {paare}"
                   + (": " + nennen(_treffer) if _treffer else ""))

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

    # ETAPPE 2 (Gerhard, 13.09.2026): Die leere Vorlage des Wochenputzes
    # traegt dieselben Spalten wie die Mappe des Scanners, samt denen der
    # technischen Kennzahlen. Sonst fehlten sie nach jedem Freitagsputz bis
    # zum naechsten Scan, und wer nach Spaltennamen liest, faende sie nicht.
    try:
        from openpyxl import load_workbook as _lw
        _kopf = [c.value for c in _lw(WURZEL / "kaufpunkte_leer.xlsx")["Kaufpunkte"][1]]
        _soll = list(ps.MAPPEN_KOEPFE)
        pruefe("D", "Leere Mappe des Wochenputzes hat dieselben Spalten wie der Scanner",
               _kopf == _soll,
               "" if _kopf == _soll else ("fehlt: " + nennen([k for k in _soll if k not in _kopf])
                                          if any(k not in _kopf for k in _soll) else "Reihenfolge weicht ab"))
    except Exception as e:
        pruefe("D", "Leere Mappe des Wochenputzes lesbar", False, f"{type(e).__name__}: {e}")

    # ---------------------------------------------------------------
    # GERHARDS ANTWORTEN VOM 22.09.2026 (O1 bis O37): jede an einer Stelle
    # ---------------------------------------------------------------
    import alarm_muster as am
    import chartmuster as cm
    import listen as li
    import wochenputz as wp
    from config import CFG

    # O35 bis O37: H Double Bottom ist komplett gestrichen.
    pruefe("D", "O35 bis O37: das Double Bottom ist weg, aus Muster, Spalten und Saetzen",
           not hasattr(cm, "double_bottom") and not any(s.startswith("cm_h") for s in cm.SPALTEN)
           and "cm_h" not in cm.MERKER and not any(k.startswith("h_") for k in cm.QUELLE)
           and not any(k.startswith("h_") for k in cm.FESTLEGUNGEN),
           ", ".join(s for s in cm.SPALTEN if s.startswith("cm_h")))

    # O19: Three Weeks Tight, hoechstens drei enge Wochen.
    pruefe("D", "O19: Three Weeks Tight zaehlt hoechstens drei enge Wochen",
           cm.FESTLEGUNGEN["a_wochen_max"] == 3, str(cm.FESTLEGUNGEN["a_wochen_max"]))

    # L IPO Base samt Erstnotiz-Regel (O14).
    pruefe("D", "L: die IPO Base ist gebaut, mit Erstnotiz und Mantel-Regel (O14)",
           hasattr(cm, "ipo_base") and hasattr(cm, "erstnotiz")
           and "cm_l" in cm.MERKER and "cm_l_mantel" in cm.SPALTEN
           and "cm_l_unsicher" in cm.SPALTEN)

    # O1: die sechs Alarm-Muster sind ein eigener Weg, keine Rangfolge-Plaetze.
    alarm_namen = set(am.NAMEN.values())
    pruefe("D", "O1: die Alarm-Muster stehen in keiner Rangfolge des Nachtscans",
           not (alarm_namen & set(ps.PRIORITY)) and hasattr(ps, "alarm_durchgang"),
           ", ".join(sorted(alarm_namen & set(ps.PRIORITY))))
    pruefe("D", "O1: es sind genau die sechs Muster A, B, D, L, N und S",
           sorted(alarm_namen) == sorted(["Three Weeks Tight", "Inside Day", "Pocket Pivot",
                                          "IPO Base", "Shakeout plus drei", "Wick Play"]),
           ", ".join(sorted(alarm_namen)))

    # O5: dieselben Melderegeln, bei Three Weeks Tight 40 Prozent ueber dem Schnitt.
    ohne = sorted(alarm_namen - set(bw.VOL_FAKTOR))
    pruefe("D", "O5: jedes Alarm-Muster hat seine Volumenhuerde, Three Weeks Tight 40 Prozent",
           not ohne and bw.VOL_FAKTOR["Three Weeks Tight"] == CFG["volumen"]["breakout_faktor_vcp"]
           and bw.VOL_FAKTOR["Inside Day"] == CFG["volumen"]["breakout_faktor"],
           ", ".join(ohne))

    # O6: nur der Inside Day nach drei steigenden Tagen meldet.
    _b = dict(cm.leer(), cm_b=1, cm_b_steigend=False, cm_b_eng_kp=10.0, cm_b_eng_stop=9.2)
    pruefe("D", "O6: ein Inside Day ohne drei steigende Tage loest keinen Alarm aus",
           am.kaufpunkte(_b) == []
           and len(am.kaufpunkte(dict(_b, cm_b_steigend=True))) == 1)

    # O7 und O8: welcher Einstieg ausloest.
    _bb = am.kaufpunkte(dict(_b, cm_b_steigend=True, cm_b_kons_kp=10.5, cm_b_kons_stop=9.6))
    pruefe("D", "O7: beim Inside Day loest der enge Einstieg aus, der konservative steht daneben",
           _bb[0]["kaufpunkt"] == 10.0 and "konservativ" in _bb[0]["zusatz"])
    _n = am.kaufpunkte(dict(cm.leer(), cm_n=1, cm_n_kp5=10.5, cm_n_kp10=11.0, cm_n_stop=10.0))
    pruefe("D", "O8: beim Shakeout plus drei loesen die 10 Prozent aus",
           _n[0]["kaufpunkt"] == 11.0 and "5 Prozent" in _n[0]["zusatz"])

    # O10: die Meldung ist eine Auskunft, kein Alarm in der Handels-App.
    _t = {"ticker": "TEST", "firma": "Probe AG", "strategie": "Inside Day",
          "kaufpunkt": 10.0, "kurs": 10.2, "ueber_pct": 2.0, "stop": 9.2,
          "vol_ok": True, "vol_pct": 30.0, "vol_noetig": 1.0, "zusatz": "Probe"}
    _text = bw.format_alarm(_t)
    pruefe("D", "O10: die Alarm-Meldung traegt INFORMATION und kein Wort, aus dem eine Order wird",
           _text.startswith("INFORMATION: ") and not am.kein_kaufwort(_text),
           ", ".join(am.kein_kaufwort(_text)))
    _quelle = (WURZEL / "breakout_watcher.py").read_text(encoding="utf-8")
    pruefe("D", "O10: push_alarm sendet ohne die Klick-Adresse der Handels-App",
           "def push_alarm" in _quelle
           and "handel_adresse" not in _quelle.split("def push_alarm")[1].split("def format_treffer")[0])

    # O11 bis O13: die einzeln eingetragenen Aktien.
    pruefe("D", "O11: eine einzeln eingetragene Aktie darf alle Strategien, auch Darvas",
           li.darf_darvas.__code__.co_argcount == 3 and "einzel_liste" in li.darf_darvas.__doc__ + str(
               li.darf_darvas.__code__.co_names))
    pruefe("D", "O12: der Freitagsputz beendet die Einzelueberwachung",
           hasattr(wp, "einzel_regel") and "einzel_regel" in wp.putz.__code__.co_names)
    pruefe("D", "O13: der Waechter zieht eine neu eingetragene Aktie im Datentakt nach",
           _quelle.count("einzel_nachziehen(items, firmen, gewuenscht, abruf_ticker") == 2
           and "def einzel_frisch" in _quelle and "def einzel_kaufpunkte" in _quelle,
           str(_quelle.count("einzel_nachziehen(items, firmen, gewuenscht, abruf_ticker")))

    # ---------------------------------------------------------------
    # DER BOT-KANAL (Vertrag degirobot/KANAL.md, 23.09.2026): je Kaufpunkt
    # und je Ausstieg eine JSON-Zeile, neben der unveraenderten Meldung
    # ---------------------------------------------------------------
    import bot_kanal as bk
    from datetime import date as _date

    pruefe("D", "Bot: der Waechter sendet an drei Kauf- und drei Ausstiegs-Stellen",
           "import bot_kanal" in _quelle
           and _quelle.count("bot_kanal.sende_kauf(") == 3
           and _quelle.count("bot_kanal.sende_verkauf(") == 3,
           f"{_quelle.count('bot_kanal.sende_kauf(')} Kauf, "
           f"{_quelle.count('bot_kanal.sende_verkauf(')} Verkauf")
    pruefe("D", "Bot: gesendet wird erst, wenn die lesbare Meldung durch ist",
           "    ok = sende(topic, titel, absaetze,\n" in _quelle
           and _quelle.count("    if ok:\n        # DEM BOT") == 1
           and "if not sende(topic, titel, absaetze, prio):\n        return False\n    # DEM BOT"
           in _quelle)
    _soll = ('{"ticker":"PVLA","name":"Palvella Therapeutics Inc","woche":"2026-W39",'
             '"kaufpunkt":158.01,"stop":142.21}')
    pruefe("D", "Bot: die Kaufzeile ist Zeichen fuer Zeichen die des Vertrags",
           bk.kauf_zeile("PVLA", "Palvella Therapeutics Inc", 158.01, 142.21,
                         _date(2026, 9, 23)) == _soll)
    pruefe("D", "Bot: die Verkaufszeile ebenso, mit Anteil 1",
           bk.verkauf_zeile("PVLA", "Palvella Therapeutics Inc", 1, _date(2026, 9, 23))
           == '{"ticker":"PVLA","name":"Palvella Therapeutics Inc","woche":"2026-W39","anteil":1}')
    pruefe("D", "Bot: Aktienklassen gehen mit Punkt hinaus, wie der Broker sie fuehrt",
           bk.broker_symbol("BRK-B") == "BRK.B")
    pruefe("D", "Bot: ohne Stop kein Kaufsignal, sonst laege die Position ungesichert",
           bk.kauf_zeile("PVLA", "P", 158.01, None, _date(2026, 9, 23)) is None)
    pruefe("D", "Bot: nur die drei ganzen Ausstiege und der halbe Teilverkauf gelten",
           bk.anteil_fuer("stop_raus") == 1 and bk.anteil_fuer("round_trip_raus") == 1
           and bk.anteil_fuer("trail_raus") == 1 and bk.anteil_fuer("teilverkauf") == 0.5
           and bk.anteil_fuer("wedge_drop") is None and bk.anteil_fuer(None) is None)
    pruefe("D", "Bot: O10, die Alarm-Muster kommen nicht in den Kaufkanal",
           bk.sende_kauf([{"ticker": "AAA", "firma": "A", "kaufpunkt": 10.0,
                           "stop": 9.0, "alarm": True}], _date(2026, 9, 23),
                         melder=lambda *_a: None) == 0)
    pruefe("D", "Bot: ohne die zwei Geheimnisse geschieht gar nichts",
           bk.kanal(bk.KAUF) is None and bk.kanal(bk.VERKAUF) is None
           and bk.sende_kauf([{"ticker": "AAA", "firma": "A", "kaufpunkt": 10.0,
                               "stop": 9.0}], melder=lambda *_a: None) == 0)
    _yml = (WURZEL / ".github" / "workflows" / "watcher.yml").read_text(encoding="utf-8")
    pruefe("D", "Bot: der Ablauf gibt beide Kanaele weiter",
           "BOT_KAUFKANAL: ${{ secrets.BOT_KAUFKANAL }}" in _yml
           and "BOT_VERKAUFSKANAL: ${{ secrets.BOT_VERKAUFSKANAL }}" in _yml)
    import beobachtungen as _bo
    import positionen as _po
    _bb = {}
    _bo.oeffnen(_bb, "RNG", "fb", "Flat Base", 80.0, 74.0, firma="RingCentral")
    _m = _po.pruefe_bestand(_bb, {"RNG": 60.0}, 30)
    pruefe("D", "Bot: das Kuerzel eines Ausstiegs traegt nie den Schluessel-Zusatz",
           bool(_m) and _m[0]["kuerzel"] == "RNG" and "|" in _m[0]["symbol"]
           and _po.melde_text(_m[0]).startswith("BEOBACHTUNG: RNG (RingCentral);"),
           str(_m[:1])[:90])
    _kq = (WURZEL / "bot_kanal.py").read_text(encoding="utf-8")
    pruefe("D", "Bot: der Kanalname steht in keiner Meldung und keinem Protokoll",
           "melder(f\"  Bot-{art}kanal nicht erreicht" in _kq
           and "{ziel}" not in _kq and "ziel}" not in _kq)


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
    # Lebenszeichen-Waechter (Mathias, 26.08.2026, nach dem Ausfall)
    import lebenszeichen as lz
    # Seit 12.09.2026 zehn Kapitel: RS-Universum, Sektor-Rangliste, Ratings;
    # seit 21.09.2026 zwoelf: Fundament und Vorabwerte, beide ueber die
    # GitHub-Schnittstelle und deshalb hier ohne Netz (netz=False).
    pruefe("E", "Lebenszeichen prueft alle zwoelf Kapitel",
           len(lz.pruefe(netz=False)) == 12)
    from datetime import date as _dt
    pruefe("E", "Handelstage statt Kalendertage (Montag schlaegt nicht an)",
           # Freitag auf Montag ist EIN Handelstag, nicht drei Kalendertage
           lz._handelstage_her("2026-08-21", _dt(2026, 8, 24)) == 1
           and lz._handelstage_her("2026-08-21", _dt(2026, 8, 26)) == 3)
    _echte = [z for z in lz.pruefe(netz=False) if z[3]]
    pruefe("E", "Am echten Bestand ist derzeit kein Kapitel still",
           not _echte, ", ".join(z[0] for z in _echte))
    pruefe("E", "Bericht kommt ohne Gedankenstrich (Screenreader)",
           all("—" not in z and "–" not in z
               for z in lz.bericht(lz.pruefe(netz=False))))
    _lz_yml = pathlib.Path(".github/workflows/lebenszeichen.yml").read_text(encoding="utf-8")
    pruefe("E", "Lebenszeichen laeuft taeglich als eigener Workflow",
           "lebenszeichen.py --melden" in _lz_yml)
    pruefe("E", "Lebenszeichen bekommt beide Token fuer Fundament und Vorabwerte",
           "DATEN_TOKEN: ${{ secrets.DATEN_TOKEN }}" in _lz_yml
           and "GITHUB_TOKEN: ${{ github.token }}" in _lz_yml)

    # Fundament und Vorabwerte mit nachgebauten Antworten der Schnittstelle
    def _rel(tag, zeit, dateien):
        return {"tag_name": tag, "published_at": zeit, "draft": False, "assets": [{}] * dateien}

    def _fund_holen(liste, latest):
        return lambda pfad: latest if pfad.endswith("/latest") else liste

    _r_neu = _rel("fundament-roh-20260921-2110", "2026-09-21T21:10:00Z", 95)
    _r_alt = _rel("fundament-roh-20260918-2105", "2026-09-18T21:05:00Z", 95)
    _f = lz._fundament(_fund_holen([_r_alt, _r_neu, _rel("scanner-daten", "2026-09-22T05:00:00Z", 4)], _r_neu),
                       heute=_dt(2026, 9, 22))
    pruefe("E", "Fundament: Release vom Vorabend ist gesund", _f[3] is False, str(_f))
    _f = lz._fundament(_fund_holen([_r_alt], _r_alt), heute=_dt(2026, 9, 23))
    pruefe("E", "Fundament: drei Handelstage ohne neues Release sind still", _f[3] is True, str(_f))
    _f = lz._fundament(_fund_holen([_r_alt, _rel("fundament-roh-20260921-2110", "2026-09-21T21:10:00Z", 40)],
                                   _rel("fundament-roh-20260921-2110", "2026-09-21T21:10:00Z", 40)),
                       heute=_dt(2026, 9, 22))
    pruefe("E", "Fundament: deutlich weniger Dateien als davor ist still", _f[3] is True, str(_f))
    _f = lz._fundament(_fund_holen([_r_alt, _r_neu], _rel("scanner-daten", "2026-09-22T05:00:00Z", 4)),
                       heute=_dt(2026, 9, 22))
    pruefe("E", "Fundament: ein anderes Release als neuestes markiert ist still",
           _f[3] is True and "scanner-daten" in _f[2], str(_f))
    _f = lz._fundament(_fund_holen([], {}), heute=_dt(2026, 9, 22))
    pruefe("E", "Fundament: ohne Fundament-Release still", _f[3] is True, str(_f))

    import json as _json
    from datetime import datetime as _dtz, timezone as _tz

    def _vw_holen(laeufe, zuletzt):
        texte = {"vorabwerte/laeufe.jsonl": "\n".join(_json.dumps(x) for x in laeufe) + "\nkaputt\n",
                 "vorabwerte/stand.json": _json.dumps({"zuletzt": zuletzt, "gesehen": {}})}
        return lambda pfad: texte[pfad]

    def _lauf(zeit, **k):
        return {"zeit": zeit, "modus": "strom", "feed": 5, "vorlaeufig": 1, "abbruch": None, **k}

    # Dienstag 22.09.2026 13:00 UTC = 09:00 New York, mitten in den Laufzeiten
    _mitte = _dtz(2026, 9, 22, 13, 0, tzinfo=_tz.utc)
    _v = lz._vorabwerte(_vw_holen([_lauf("2026-09-22T12:30:39+00:00"),
                                   {"zeit": "2026-09-22T12:50:00+00:00", "modus": "abgleich"}],
                                  "2026-09-22T12:24:22+00:00"), jetzt=_mitte)
    pruefe("E", "Vorabwerte: Lauf vor einer halben Stunde ist gesund", _v[3] is False, str(_v))
    _v = lz._vorabwerte(_vw_holen([_lauf("2026-09-22T08:00:00+00:00")], "2026-09-22T07:55:00+00:00"),
                        jetzt=_mitte)
    pruefe("E", "Vorabwerte: fuenf Stunden ohne Lauf in der Laufzeit sind still", _v[3] is True, str(_v))
    _v = lz._vorabwerte(_vw_holen([_lauf("2026-09-22T00:30:00+00:00")], "2026-09-22T00:20:00+00:00"),
                        jetzt=_dtz(2026, 9, 22, 8, 0, tzinfo=_tz.utc))
    pruefe("E", "Vorabwerte: nachts gilt der Lauf vom Abend davor", _v[3] is False, str(_v))
    _v = lz._vorabwerte(_vw_holen([_lauf("2026-09-17T23:30:00+00:00")], "2026-09-17T23:20:00+00:00"),
                        jetzt=_dtz(2026, 9, 22, 8, 0, tzinfo=_tz.utc))
    pruefe("E", "Vorabwerte: zwei Handelstage ohne Lauf sind still", _v[3] is True, str(_v))
    _v = lz._vorabwerte(_vw_holen([_lauf("2026-09-22T12:30:39+00:00", abbruch="SEC-Feed nicht lesbar")],
                                  "2026-09-22T12:24:22+00:00"), jetzt=_mitte)
    pruefe("E", "Vorabwerte: abgebrochener Lauf ist still", _v[3] is True and "abgebrochen" in _v[2], str(_v))
    _v = lz._vorabwerte(_vw_holen([_lauf("2026-09-22T12:30:39+00:00")], "2026-09-16T20:00:00+00:00"),
                        jetzt=_mitte)
    pruefe("E", "Vorabwerte: keine neue 8-K seit Tagen ist still", _v[3] is True, str(_v))

    def _ohne_token(pfad):
        raise lz.TokenFehlt("DATEN_TOKEN")
    _v = lz._vorabwerte(_ohne_token, jetzt=_mitte)
    pruefe("E", "Vorabwerte: ohne DATEN_TOKEN still mit Grund", _v[3] is True and "DATEN_TOKEN" in _v[2], str(_v))

    pruefe("E", "Index-Rueckblick deckt Gerhards Cluster-Fenster ab",
           ie.index_rueckblick({"cluster_fenster_tage": 10,
                                "index_tage_zurueck": 0}) == 10)
    pruefe("E", "Cluster-Fenster geaendert: Rueckblick wandert mit",
           ie.index_rueckblick({"cluster_fenster_tage": 15,
                                "index_tage_zurueck": 0}) == 15)
    pruefe("E", "Eigener Wert ueberstimmt die Rechnung",
           ie.index_rueckblick({"cluster_fenster_tage": 10,
                                "index_tage_zurueck": 3}) == 3)
    import config as _cfgm
    pruefe("E", "Rueckblick der echten Einstellung deckt das Fenster",
           ie.index_rueckblick(_cfgm.CFG["insider"])
           >= _cfgm.CFG["insider"]["cluster_fenster_tage"])
    pruefe("E", "Jede Einreichung wird nur einmal geladen (Zugangsnummer)",
           "einmalig.setdefault(zugangsnummer(p), p)" in
           pathlib.Path("insider_edgar.py").read_text(encoding="utf-8"))
    pruefe("E", "Dieselbe Einreichung unter Firma und Insider ist EINE",
           ie.zugangsnummer("edgar/data/1865107/0001628280-26-058957.txt")
           == ie.zugangsnummer("edgar/data/1200506/0001628280-26-058957.txt"))
    pruefe("E", "Live-Strom filtert auf Insider-Meldungen (owner=only)",
           'sowner=only' .replace("s", "") in
           pathlib.Path("insider_edgar.py").read_text(encoding="utf-8")
           .replace('"owner": "only"', "owner=only"))
    pruefe("E", "Live-Strom ist Vorsprung, kein Ersatz (scan nutzt beides)",
           "live_einreichungen(" in
           pathlib.Path("insider_edgar.py").read_text(encoding="utf-8")
           and "tagesindex(tag, leise)" in
           pathlib.Path("insider_edgar.py").read_text(encoding="utf-8"))
    _q_ie = pathlib.Path("insider_edgar.py").read_text(encoding="utf-8")
    pruefe("E", "403 auf einen vergangenen Werktag wird als FEHLER gemeldet",
           "vergangener_werktag" in _q_ie and "FEHLER: Tagesindex" in _q_ie)

    # KAPITEL 12 — Gewinnzonen (Gerhards Uebergabe vom 28.08.2026)
    import subprocess as _sp
    _lauf = _sp.run([sys.executable, "gewinn_zonen.py"],
                    capture_output=True, timeout=120)
    pruefe("E", "Gerhards gewinn_zonen-Selbsttest besteht (14 Gruppen)",
           _lauf.returncode == 0)
    import beobachtungen as _bb
    import positionen
    pruefe("E", "Klassen: Darvas quellentreu, Tagesgeschaeft, Insider",
           _bb.klasse_fuer(["Darvas Box"]) == "darvas"
           and _bb.klasse_fuer(["Red-to-Green"]) == "tagesgeschaeft"
           and _bb.klasse_fuer(["Gap and Go"]) == "tagesgeschaeft"
           and _bb.klasse_fuer(["Insider-Kauf"]) == "insider"
           and _bb.klasse_fuer(["Rectangle Top"]) == "standard")
    pruefe("E", "Luecken-Tag wird nur mit frischem Termin zur Zahlen-Luecke",
           _bb.klasse_fuer(["Lücken-Bestätigungstag"], termin_tage=-2)
           == "zahlen_luecke"
           and _bb.klasse_fuer(["Lücken-Bestätigungstag"], termin_tage=None)
           == "standard"
           and _bb.klasse_fuer(["Lücken-Bestätigungstag"], termin_tage=-20)
           == "standard")
    _bst = {}
    _k1 = _bb.oeffnen(_bst, "tst", 1, "Rectangle Top", 100.0, 80.0,
                      musterziel=110.0, klasse="standard")
    pruefe("E", "Beobachtung: Schluessel TICKER|Zusatz, Stop gedeckelt",
           _k1 == "TST|1" and _bst["TST|1"]["symbol"] == "TST"
           and _bst["TST|1"]["aktueller_stop"] == 90.0
           and _bst["TST|1"]["beobachtung"] is True
           and _bst["TST|1"]["musterziel"] == 110.0)
    pruefe("E", "Doppelte Oeffnung derselben Beobachtung wird verweigert",
           _bb.oeffnen(_bst, "TST", 1, "Rectangle Top", 101.0, 95.0) is None)
    _bb.schliessen(_bst["TST|1"], "Probe", 120.0)
    pruefe("E", "Schliessen schreibt die Mitschrift (Prozent und R)",
           _bst["TST|1"]["ergebnis_pct"] == 20.0
           and _bst["TST|1"]["status"] == "geschlossen")
    from datetime import date as _dk
    pruefe("E", "Termin-Abstand rechnet deterministisch",
           _bb.termin_abstand_tage("AAA", termine={"AAA": {"datum":
               "2026-09-01"}}, heute=_dk(2026, 8, 28)) == 4
           and _bb.termin_abstand_tage("BBB", termine={},
                                       heute=_dk(2026, 8, 28)) is None)
    import wartung as _wt
    pruefe("E", "Wochenputz fasst Beobachtungen und Befunde nicht an",
           "positionen.json" not in _wt.ZUSTANDSDATEIEN
           and "exit_befunde.json" not in _wt.ZUSTANDSDATEIEN)
    # pruefe_bestand findet den Kurs ueber das Symbol-Feld, nicht den
    # Schluessel (Beobachtungen heissen TICKER|Zusatz)
    _bst2 = {}
    _bb.oeffnen(_bst2, "TST", 2, "Rectangle Top", 100.0, 95.0)
    positionen.pruefe_bestand(_bst2, {"TST": 120.0}, 10)
    pruefe("E", "pruefe_bestand erreicht Beobachtungen mit Zusatz-Schluessel",
           _bst2["TST|2"]["hoechstkurs"] == 120.0)

    # Ende-zu-Ende: der naechtliche Durchgang an drei Beobachtungen
    import gewinnzonen_lauf as _gl
    import tempfile as _tfk
    import os as _osk
    import json as _jsk
    import pandas as _pdk
    _wurzel = _osk.getcwd()
    with _tfk.TemporaryDirectory() as _tmp:
        try:
            _osk.chdir(_tmp)
            _bstE = {}
            _bb.oeffnen(_bstE, "GEW", 1, "Rectangle Top", 100.0, 95.0,
                        musterziel=110.0, klasse="standard",
                        datum="2026-06-01")
            _bb.oeffnen(_bstE, "TAG", "R2G-x", "Red-to-Green", 50.0, 49.0,
                        klasse="tagesgeschaeft", datum="2026-08-28")
            _bb.oeffnen(_bstE, "DRV", 1, "Darvas Box", 30.0, 28.0,
                        klasse="darvas", datum="2026-06-01")
            positionen.speichern(_bstE)
            _tage = _pdk.date_range("2026-01-02", periods=170, freq="B")

            def _df(start, schritt):
                kurse = [start + i * schritt for i in range(len(_tage))]
                return _pdk.DataFrame({
                    "datetime": _tage.astype(str),
                    "close": kurse,
                    "high": [k * 1.01 for k in kurse],
                    "low": [k * 0.99 for k in kurse]})
            _loaded = {"GEW": (_df(90.0, 0.35), "Gewinn AG"),
                       "TAG": (_df(50.0, 0.01), "Tages AG"),
                       "DRV": (_df(28.0, 0.05), "Darvas AG")}
            # Die Pruefungen zum Handelsstart unten laufen am Musterziel-
            # Befund. Der ist seit 11.09.2026 abgeschaltet (Straffungs-
            # Meldungen, Gerhard); fuer diesen Durchgang wird der Schalter
            # deshalb kurz eingeschaltet. Das Abschalten selbst wird weiter
            # unten eigens geprueft.
            _gs = _gl.CFG.setdefault("gewinnseite", {})
            _gs_alt = _gs.get("straffungs_meldungen")

            def _straffung(wert):
                if wert is None:
                    _gs.pop("straffungs_meldungen", None)
                else:
                    _gs["straffungs_meldungen"] = wert

            _straffung(True)
            try:
                _bef = _gl.gewinn_durchgang(_loaded, "gibt_es_nicht.xlsx",
                                            exit_meldungen=[],
                                            heute=_dk(2026, 8, 28))
            finally:
                _straffung(_gs_alt)
            _nach = positionen.laden()
            pruefe("E", "Durchgang: Musterziel-Befund kommt, laut und einzeln",
                   any(b["typ"] == "ziel_erreicht"
                       and b["symbol"] == "GEW"
                       and b["prioritaet"] == "high"
                       and not b["buendeln"] for b in _bef))
            pruefe("E", "Durchgang: Tagesgeschaeft endet am Handelsschluss",
                   _nach["TAG|R2G-x"]["status"] == "geschlossen"
                   and any(b["typ"] == "tagesende" for b in _bef))
            pruefe("E", "Durchgang: Darvas bleibt quellentreu ohne Befund",
                   not any(b.get("symbol") == "DRV" for b in _bef)
                   and _nach["DRV|1"]["status"] == "offen")
            pruefe("E", "Durchgang: Zone wird gefuehrt und gespeichert",
                   _nach["GEW|1"].get("zone") in ("mittel", "stark"))
            _datei = _jsk.load(open("exit_befunde.json", encoding="utf-8"))
            pruefe("E", "Befunde liegen fuer den Waechter bereit",
                   _datei.get("handelstag") == "2026-08-28"
                   and len(_datei.get("befunde", [])) == len(_bef))

            # MELDUNGEN ZUM HANDELSSTART (Mathias, 10.09.2026): "Es darf nie
            # wieder etwas vom Vortag kommen, angezeigte Alarme muessen immer
            # aus den aktuellen Kursen errechnet sein, die zu Handelsstart
            # gelten." Der Nachtlauf legt Kandidaten ab, der Waechter rechnet
            # sie mit dem heutigen Kurs nach.
            _ziel = next((b for b in _bef if b["typ"] == "ziel_erreicht"), {})
            pruefe("E", "Nachtlauf: Musterziel ist ein Kandidat ohne fertigen Text",
                   _ziel.get("art") == _gl.LIVE and not _ziel.get("text")
                   and _datei.get("format") == _gl.FORMAT)
            pruefe("E", "Nachtlauf setzt keinen Melde-Merker mehr",
                   _nach["GEW|1"].get("ziel_gemeldet") is False)
            pruefe("E", "Tagesgeschaeft-Ende wird zurueckgehalten (Schlusskurs)",
                   any(b["typ"] == "tagesende" for b in _bef)
                   and all(b["art"] == _gl.ZURUECK for b in _bef
                           if b["typ"] == "tagesende"))
            _v = _datei.get("verlaeufe", {}).get("GEW|1") or {}
            # Der letzte Tag der Probe-Kursreihe (170 Handelstage ab 02.01.)
            _letzter = str(_loaded["GEW"][0]["datetime"].iloc[-1])[:10]
            pruefe("E", "Kandidat traegt Kursverlauf und Haltedauer mit",
                   len(_v.get("daten", [])) > 150 and _v.get("tage", 0) > 0
                   and bool(_v.get("daten"))
                   and _v["daten"][-1][0] == _letzter, _letzter)
            _eGEW = _nach["GEW|1"]
            _ober = _gl.live_pruefen(_ziel, _eGEW, _v, 111.0, _dk(2026, 8, 31))
            _unter = _gl.live_pruefen(_ziel, _eGEW, _v, 109.0, _dk(2026, 8, 31))
            pruefe("E", "Handelsstart: Ziel gilt nur mit HEUTIGEM Kurs darueber",
                   _ober is not None and _unter is None)
            pruefe("E", "Handelsstart: Meldung nennt den heutigen Kurs",
                   _ober is not None and "Kurs 111,00" in _ober[1]
                   and _ober[2] == {"ziel_gemeldet": True})
            _probe_e = {}
            _gl.merker_anwenden(_probe_e, {"klimax_gemeldet": "4_ma200_abstand"})
            _gl.merker_anwenden(_probe_e, {"klimax_gemeldet": "4_ma200_abstand"})
            pruefe("E", "Klimax-Merker wird einmal gesetzt, ohne Doppel",
                   _probe_e.get("klimax_gemeldet") == ["4_ma200_abstand"])

            # Der Waechter-Schritt selbst, ohne Netz und ohne Push
            _alt_sende, _alt_save = bw.sende, bw.save_state
            _alt_heute, _alt_push = bw.heute_ny, bw._LETZTER_PUSH
            _gesendet_n = []
            try:
                bw.sende = lambda topic, titel, absaetze, prio="default", \
                    klick=None: (_gesendet_n.append((titel, list(absaetze)))
                                 or True)
                bw.save_state = lambda state, sofort=False: None
                bw.heute_ny = lambda: _dk(2026, 8, 31)
                bw._LETZTER_PUSH = None

                from datetime import timedelta as _tdk
                _vortag_ok = _dk.fromisoformat(_letzter)

                def _nacht(basis_kurs, vortag=_vortag_ok):
                    n = {"tag": "2026-08-28", "live": [_ziel], "zurueck": [],
                         "verlaeufe": {"GEW|1": _v}, "radar": {},
                         "insider": [], "offen": [("gewinn", _ziel)]}
                    basis = {"GEW": {"close": basis_kurs, "high": basis_kurs,
                                     "low": basis_kurs, "prev_datum": vortag}}
                    return n, basis

                _n1, _b1 = _nacht(111.0)
                _gem = set()
                _st = {"gemeldet": {}}
                _erg = bw.nachtbefunde_schritt("probe", _n1, _b1, None, _gem,
                                               _st, False)
                pruefe("E", "Waechter meldet den nachgerechneten Befund",
                       _erg is True and _gesendet_n
                       # Punkt 6 (Gerhard, 12.09.2026): INFORMATION-Praefix
                       and _gesendet_n[-1][0] == "INFORMATION: GEWINN-Ziel erreicht: GEW"
                       and not _n1["offen"])
                pruefe("E", "Erst nach dem Senden: Merker in positionen.json "
                       "und Schluessel im Gedaechtnis",
                       positionen.laden()["GEW|1"].get("ziel_gemeldet") is True
                       and "GEWINN|ziel_erreicht|GEW|1|" in _gem)
                _b0 = positionen.laden()
                _b0["GEW|1"]["ziel_gemeldet"] = False
                positionen.speichern(_b0)
                _gesendet_n.clear()
                _n2, _b2 = _nacht(109.0)
                _erg2 = bw.nachtbefunde_schritt("probe", _n2, _b2, None,
                                                set(), {"gemeldet": {}}, False)
                pruefe("E", "Gilt er mit dem heutigen Kurs nicht, kommt nichts",
                       _erg2 is None and not _gesendet_n and not _n2["offen"])
                _n3, _b3 = _nacht(111.0, vortag=_vortag_ok - _tdk(days=1))
                _erg3 = bw.nachtbefunde_schritt("probe", _n3, _b3, None,
                                                set(), {"gemeldet": {}}, False)
                pruefe("E", "Passt der Nachtlauf nicht zum Vortag der Kurse, "
                       "kommt nichts",
                       _erg3 is None and not _gesendet_n and not _n3["offen"])
                _n4, _b4 = _nacht(111.0)
                _erg4 = bw.nachtbefunde_schritt("probe", _n4, {}, None,
                                                set(), {"gemeldet": {}}, False)
                pruefe("E", "Ohne heutige Kurszeile wartet der Befund",
                       _erg4 is None and len(_n4["offen"]) == 1)
                import time as _tmk
                bw._LETZTER_PUSH = _tmk.monotonic()
                _erg5 = bw.nachtbefunde_schritt("probe", _n4, _b4, None,
                                                set(), {"gemeldet": {}}, False)
                pruefe("E", "Nachtbefunde draengeln nicht vor: bei belegtem "
                       "Push-Sammler warten sie",
                       _erg5 is None and len(_n4["offen"]) == 1
                       and not _gesendet_n)
            finally:
                bw.sende, bw.save_state = _alt_sende, _alt_save
                bw.heute_ny, bw._LETZTER_PUSH = _alt_heute, _alt_push

            # STRAFFUNGS-MELDUNGEN ABGESCHALTET (Gerhard, 11.09.2026, bis auf
            # Weiteres): Musterziel erreicht, Wedge Drop und Sektor dreht
            # werden weder abgelegt noch gemeldet; alles andere bleibt.
            pruefe("E", "Straffungs-Meldungen: Schalter in config.py steht auf aus",
                   _gs_alt is False and _gl.straffung_gemeldet() is False)
            _typen = ["ziel_erreicht", "wedge_drop", "sektor_hinweis",
                      "zonenwechsel", "klimax_zeichen", "weinstein",
                      "zeitdeckel", "zahlen_hinweis", "kapitel11", "tagesende"]
            _bleibt, _weg = _gl.abgeschaltete_trennen(
                [{"typ": t} for t in _typen])
            pruefe("E", "Straffungs-Meldungen aus: genau die drei Typen fallen heraus",
                   sorted(b["typ"] for b in _weg) == sorted(_gl.STRAFFUNG)
                   and [b["typ"] for b in _bleibt] == _typen[3:])
            _straffung(True)
            try:
                _bleibt_an, _weg_an = _gl.abgeschaltete_trennen(
                    [{"typ": t} for t in _typen])
            finally:
                _straffung(_gs_alt)
            pruefe("E", "Straffungs-Meldungen an: es faellt nichts heraus",
                   len(_bleibt_an) == len(_typen) and not _weg_an)

            # Derselbe Durchgang mit abgeschaltetem Schalter: Das Musterziel
            # ist erreicht und noch nicht gemeldet, der Befund faellt aber
            # vor dem Ablegen heraus. Die Zone rechnet trotzdem weiter, und
            # der Melde-Merker bleibt unberuehrt fuer das Wiedereinschalten.
            _bef_aus = _gl.gewinn_durchgang(_loaded, "gibt_es_nicht.xlsx",
                                            exit_meldungen=[],
                                            heute=_dk(2026, 8, 28))
            _datei_aus = _jsk.load(open("exit_befunde.json", encoding="utf-8"))
            _nach_aus = positionen.laden()
            pruefe("E", "Straffungs-Meldungen aus: Nachtlauf legt das Musterziel "
                   "nicht ab",
                   not any(b["typ"] in _gl.STRAFFUNG for b in _bef_aus)
                   and not any(b.get("typ") in _gl.STRAFFUNG
                               for b in _datei_aus.get("befunde", []))
                   and len(_datei_aus.get("befunde", [])) == len(_bef_aus))
            pruefe("E", "Straffungs-Meldungen aus: Zone rechnet weiter, Merker "
                   "bleibt frei",
                   _nach_aus["GEW|1"].get("zone") in ("mittel", "stark")
                   and _nach_aus["GEW|1"].get("ziel_gemeldet") is False)
            # M1 (Gerhard, 12.09.2026): JEDE offene Beobachtung traegt ihren
            # Kursverlauf, der Waechter rechnet um 15:45 alle Schlussbefunde
            # nach; ein Verlauf ohne Beobachtung gibt es nicht.
            pruefe("E", "Straffungs-Meldungen aus: Kursverlauf fuer die offene "
                   "Beobachtung liegt bei, keiner ohne Beobachtung (M1)",
                   bool(_datei_aus.get("verlaeufe", {}).get("GEW|1"))
                   and all(k in _nach_aus or any(b.get("key") == k
                                                 for b in _datei_aus.get("befunde", []))
                           for k in _datei_aus.get("verlaeufe", {})))

            # Und der Waechter laesst sie auch aus einer Ablage weg, die noch
            # vor dem Abschalten geschrieben wurde (so lag CNC am 11.09.).
            with open("exit_befunde.json", "w", encoding="utf-8") as _fa:
                _jsk.dump({"format": _gl.FORMAT, "handelstag": "2026-09-10",
                           "befunde": [
                               {"typ": "ziel_erreicht", "art": _gl.LIVE,
                                "symbol": "ZZZ", "key": "ZZZ|1"},
                               {"typ": "wedge_drop", "art": _gl.ZURUECK,
                                "symbol": "CNC", "key": "CNC|1"},
                               {"typ": "sektor_hinweis", "art": _gl.ZURUECK,
                                "symbol": "SEK", "key": "SEK|1"},
                               {"typ": "zonenwechsel", "art": _gl.LIVE,
                                "symbol": "GEW", "key": "GEW|1"},
                               {"typ": "kapitel11", "art": _gl.ZURUECK,
                                "symbol": "WFRD|1"}],
                           "verlaeufe": {}}, _fa)
            _nl = bw.nachtbefunde_laden()
            pruefe("E", "Straffungs-Meldungen aus: der Waechter laesst sie auch "
                   "aus einer aelteren Ablage weg",
                   [b["typ"] for b in _nl["live"]] == ["zonenwechsel"]
                   and [b["typ"] for b in _nl["zurueck"]] == ["kapitel11"]
                   and _nl["abgeschaltet"] == 3
                   and "ZZZ" not in bw.nacht_symbole(_nl))

            # Kapitel 11 (Gerhard: Schlusskurs, nicht Docht)
            _alt_nl = _gl._kurse_nachladen
            _gl._kurse_nachladen = lambda symbole: {}
            try:
                _m11 = {"symbol": "WFRD|1", "firma": "Weatherford",
                        "aktion": "stop_raus",
                        "grund": "Schluss 93.70 unter Stop 94.12",
                        "kurs": 93.70, "beobachtung": True,
                        "gewinn_pct": -2.9}
                _bef11 = _gl.gewinn_durchgang({}, "gibt_es_nicht.xlsx",
                                              exit_meldungen=[_m11],
                                              heute=_dk(2026, 8, 28))
            finally:
                _gl._kurse_nachladen = _alt_nl
            pruefe("E", "Kapitel-11-Exit wird zurueckgehalten, nicht gemeldet",
                   any(b["typ"] == "kapitel11" and b["art"] == _gl.ZURUECK
                       and b.get("grund") == "schlusskurs" for b in _bef11))
        finally:
            _osk.chdir(_wurzel)

    # KLIMAX-ZEICHEN 1 konnte nie ausloesen (behoben 10.09.2026): Lauf und
    # Vorlauf hingen an derselben Zahl, hoechstens 15 und zugleich
    # mindestens 40 Handelstage.
    _t1 = _pdk.date_range("2026-01-02", periods=120, freq="B")
    _k1 = [100.0] * 105 + [100.0 * (1 + 0.02 * i) for i in range(1, 16)]
    _d1 = _pdk.DataFrame({"datetime": _t1.astype(str), "close": _k1,
                          "high": _k1, "low": _k1})
    import gewinn_zonen as _gzk
    pruefe("E", "Klimax-Zeichen 1 loest aus: +30 % in 15 Tagen nach 12 Wochen",
           "1_klimaxlauf" in _gzk.pruefe_klimax_katalog(
               _gl._klimax_eingaben(_d1, 60))["ausgeloeste_zeichen"])
    pruefe("E", "Klimax-Zeichen 1 bleibt still bei nur 6 Wochen Vorlauf",
           "1_klimaxlauf" not in _gzk.pruefe_klimax_katalog(
               _gl._klimax_eingaben(_d1, 30))["ausgeloeste_zeichen"])
    pruefe("E", "Zur Zone am Handelsstart zaehlen nur Klimax 1, 4 und 5",
           _gl.KLIMAX_LIVE == ("1_klimaxlauf", "4_ma200_abstand",
                               "5_kanaluebershooting")
           and "ist_klimax=bool(live_zeichen)" in
           open("gewinnzonen_lauf.py", encoding="utf-8").read())

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
        # SEIT 31.08.2026 VORN statt am Ende (Mathias: "Wenn ein
        # Unternehmen Zahlen bringt, soll dies am Anfang der
        # Push-Mitteilung stehen, nicht wie bisher am Ende").
        mit_ns = bw.format_aktie([kp1, kp2])
        pruefe("E", "Termin-Nachsatz steht im Buendel nur EINMAL, als Zeile 2",
               mit_ns.count("Termin-Probe") == 1
               and mit_ns.split("\n")[1] == "Termin-Probe unsicher")
        einzel_ns = bw.format_treffer(dict(kp1))
        pruefe("E", "Termin-Nachsatz der Einzelmeldung als Zeile 2, nicht am Ende",
               einzel_ns.split("\n")[1] == "Termin-Probe unsicher"
               and einzel_ns.split("\n")[-1] != "Termin-Probe unsicher")
        ueber_ns = bw.format_uebersprungen({**grund, "kurs": 116.0,
                                            "ueber_pct": 6.0})
        pruefe("E", "Auch die Uebersprungen-Meldung traegt ihn als Zeile 2",
               ueber_ns.split("\n")[1] == "Termin-Probe unsicher")
    finally:
        bw.termin_nachsatz = _alt_ns
    # Logbuch-Verdrahtung von Red-to-Green und Gap and Go (Mathias,
    # 31.08.2026: "ja, bitte ins Logbuch eintragen") — vorher waren beide
    # der blinde Fleck jeder Auswertung.
    _bw_quelle = open("breakout_watcher.py", encoding="utf-8").read()
    pruefe("E", "Red-to-Green protokolliert ins Logbuch (waechter/kapitel9)",
           'quelle="waechter/kapitel9"' in _bw_quelle
           and '"strategie": "Red-to-Green",' in _bw_quelle)
    pruefe("E", "Gap and Go protokolliert ins Logbuch (waechter/kapitel7)",
           'quelle="waechter/kapitel7"' in _bw_quelle
           and '"strategie": "Gap and Go",' in _bw_quelle)

    # ZAHLEN-KARENZ, MARKTAMPEL, EARNINGS-PULLBACK (Gerhards Freigabe
    # vom 31.08.2026, Bausteine 1, 2 und 4 des Einbau-Papiers). Alles
    # datumsfest ueber injizierte Termine und Kalender.
    import zahlen_termine as _zt
    from datetime import date as _dtk, timedelta as _tdk
    _term = {"TST": {"datum": "2026-09-02", "lage": "nachboerslich"},
             "ALT": {"datum": "2026-08-20", "lage": "nachboerslich"}}
    pruefe("E", "handelstage_bis zaehlt Handelstage, nie Wochenenden",
           _zt.handelstage_bis("TST", _dtk(2026, 8, 31), _term) == 2
           and _zt.handelstage_bis("TST", _dtk(2026, 8, 28), _term) == 3
           and _zt.handelstage_bis("ALT", _dtk(2026, 8, 31), _term) is None
           and _zt.handelstage_bis("NIX", _dtk(2026, 8, 31), _term) is None)
    _zt_alt = _zt._termine
    try:
        import zoneinfo as _zik
        import datetime as _dtm
        _ny = _dtm.datetime.now(
            _zik.ZoneInfo("America/New_York")).date()
        _morgen = _ny + _tdk(days=1)
        while _morgen.weekday() >= 5:
            _morgen += _tdk(days=1)
        _uebermorgen = _morgen + _tdk(days=1)
        while _uebermorgen.weekday() >= 5:
            _uebermorgen += _tdk(days=1)
        _zt._termine = {"KAR": {"datum": _morgen.isoformat(),
                                "lage": "nachboerslich"},
                        "KA2": {"datum": _uebermorgen.isoformat(),
                                "lage": "unbekannt"}}
        # STUFE A (Gerhard, 31.08.2026 abends): nichts wird mehr
        # gefiltert, das Fenster markiert nur noch.
        pruefe("E", "Karenzfenster markiert, filtert aber nicht mehr",
               bw.im_zahlen_karenzfenster("KAR") is True
               and bw.im_zahlen_karenzfenster("KA2") is True
               and bw.im_zahlen_karenzfenster("OHNE") is False)
        _warn = _zt.karenz_hinweis("KA2", 2)
        pruefe("E", "Uebermorgen-Termin bekommt den harten Warnkopf",
               _warn is not None and _warn.startswith("ACHTUNG: QUARTALSZAHLEN")
               and _zt.karenz_hinweis("OHNE", 2) is None)
    finally:
        _zt._termine = _zt_alt
    pruefe("E", "Stufe A: kein Karenz-Filter mehr im Meldepfad, nur Feld",
           "karenz_ids" not in _bw_quelle
           and "zahlen_karenz_greift" not in _bw_quelle
           and '"zahlen_karenz": bool(t.get("zahlen_karenz"))' in _bw_quelle
           and "karenz_hinweis" in _bw_quelle)
    import marktampel as _ma
    import pandas as _pdm
    _idx = _pdm.date_range("2026-01-02", periods=80, freq="B")
    _steigend = _pdm.DataFrame(
        {"Close": [100 + i for i in range(80)]}, index=_idx)
    _lage = _ma._index_lage(_steigend)
    pruefe("E", "Marktampel: steigende Reihe liegt ueber beiden Linien",
           _lage is not None and _lage["ueber_ema21"]
           and _lage["ueber_sma50"] and _lage["sma50_steigt"])
    _fallend = _pdm.DataFrame(
        {"Close": [200 - i for i in range(80)]}, index=_idx)
    _lage2 = _ma._index_lage(_fallend)
    pruefe("E", "Marktampel: fallende Reihe liegt unter der 50er-Linie",
           _lage2 is not None and not _lage2["ueber_sma50"])
    # ETAPPE 3 (Gerhard, 13.09.2026, Entscheidung 6): je Index die
    # Distribution Days aus demselben Kursrahmen, den die Ampel laedt.
    import marktbreite as _mbm
    _dd_df = _pdm.DataFrame({"Close": [100.0] * 79 + [99.0], "High": [101.0] * 80,
                             "Low": [99.0] * 80, "Volume": [1000.0] * 79 + [2000.0]}, index=_idx)
    _ph_e = _mbm.index_phase(_dd_df)
    pruefe("E", "Marktampel: ein Distribution Day an einer Indexreihe erkannt (Etappe 3)",
           _ph_e is not None and [x["tag"] for x in _ph_e["distribution_days"]] == [_idx[-1].strftime("%Y-%m-%d")]
           and _ph_e["distribution_days"][0]["art"] == "distribution" and "phase" in _ph_e, _ph_e)
    pruefe("E", "Marktampel laedt ein Jahr Indexkurse fuer Distribution Days und Follow-through Day",
           'history(period="1y", auto_adjust=False)' in open("marktampel.py", encoding="utf-8").read())
    pruefe("E", "Logbuch haengt die Ampelfarbe an jede Zeile",
           "eintrag[\"ampel\"] = ampel" in
           open("trigger_logbuch.py", encoding="utf-8").read())
    pruefe("E", "Logbuch nennt dazu den Schluss, fuer den die Farbe gilt",
           "eintrag[\"ampel_tag\"] = ampel_tag" in
           open("trigger_logbuch.py", encoding="utf-8").read())

    # ETAPPE 0, MARKTAMPEL-ZEILE (Gerhard, 13.09.2026): EINE Zeile am Anfang
    # der ERSTEN Meldung des Handelstags, ohne Farbe vom falschen Tag.
    _lage_g = {"ueber_ema21": True, "ueber_sma50": True,
               "ema21_ueber_sma50": True, "sma50_steigt": True}
    _amp = {"farbe": "gelb", "handelstag": "2026-09-11",
            "indizes": {"S&P 500": _lage_g,
                        "Nasdaq": {**_lage_g, "ueber_ema21": False}}}
    _z = _ma.zeile(_amp, "2026-09-11")
    # ETAPPE 3: dahinter in derselben Zeile die Marktbreite
    _mb_e = {"handelstag": "2026-09-11", "steiger": 2310, "faller": 1876, "mcclellan": 45.2,
             "summation_trend": 12.0, "ueber_sma50_pct": 58.4, "ueber_sma200_pct": 61.2,
             "neue_hochs": 85, "neue_tiefs": 40, "stockbee": {"plus4": 180, "minus4": 95, "verh5": 1.6}}
    _z_mb = _ma.zeile(_amp, "2026-09-11", _mb_e)
    pruefe("E", "Marktampel-Zeile samt Marktbreite in derselben Zeile (Etappe 3)",
           _z_mb == (_z + "; Marktbreite 2.310 Steiger und 1.876 Faller; McClellan-Oszillator plus 45, "
                     "Summation Index steigend; 58 Prozent über SMA 50, 61 Prozent über SMA 200; 85 neue "
                     "52-Wochen-Hochs und 40 neue Tiefs; Stockbee 180 Aktien mit plus 4 Prozent und 95 mit "
                     "minus 4 Prozent, Verhältnis über 5 Tage 1,60"), _z_mb)
    _z_mb_alt = _ma.zeile(_amp, "2026-09-11", {**_mb_e, "handelstag": "2026-09-10"})
    pruefe("E", "Marktampel-Zeile: eine Marktbreite vom falschen Schluss zeigt keine Zahl",
           "Marktbreite nicht verfügbar, die letzte Berechnung gilt dem Schluss vom 10.09.2026" in _z_mb_alt
           and "Steiger" not in _z_mb_alt, _z_mb_alt)
    pruefe("E", "Marktampel-Zeile: ohne Marktbreite in der Nachtdatei ehrlich nicht verfuegbar",
           _ma.zeile(_amp, "2026-09-11", {}).endswith("Marktbreite nicht verfügbar, es liegt keine Berechnung vor"))
    pruefe("E", "Marktampel-Zeile: Farbe, Schluss und beide Indizes",
           _z == ("Marktampel gelb, Schluss vom 11.09.2026; S&P 500 über "
                  "EMA 21 und SMA 50, SMA 50 steigt; Nasdaq unter EMA 21, "
                  "über SMA 50, SMA 50 steigt"), _z)
    _z_alt = _ma.zeile(_amp, "2026-09-14")
    pruefe("E", "Marktampel-Zeile: eine Ampel vom falschen Schluss zeigt "
                "keine Farbe", _z_alt.startswith("Marktampel nicht verfügbar")
           and "gelb" not in _z_alt and "11.09.2026" in _z_alt
           and "14.09.2026" in _z_alt, _z_alt)
    pruefe("E", "Marktampel-Zeile: ohne Ablage ehrlich nicht verfuegbar",
           _ma.zeile(None).startswith("Marktampel nicht verfügbar"))
    pruefe("E", "Marktampel-Zeile im Meldungsformat: kein Gedankenstrich, "
                "kein senkrechter Strich",
           not any(ch in s for s in (_z, _z_alt, _ma.zeile(None), _z_mb, _z_mb_alt)
                   for ch in ("—", "–", "|")))
    # Die Handels-App (Repo heliot-daten, alarmeAusText) liest aeltere
    # Meldungen aus dem Text: Ein Absatz zaehlt dort nur als Alarm, wenn
    # hinter Kaufpunkt, Kurs, Stop, Ziel oder Exit-Linie eine Zahl steht.
    # Die Ampel-Zeile darf deshalb keines dieser Wortpaare tragen.
    import re as _re_amp
    pruefe("E", "Marktampel-Zeile wird von der Handels-App nicht als Alarm "
                "gelesen", not any(_re_amp.search(
                    r"(Kaufpunkt|Kurs|Stop|Ziel|Exit-Linie)\s+(\(Folgetag\)\s+)?\d", s)
                    for s in (_z, _z_alt, _ma.zeile(None), _z_mb, _z_mb_alt)))
    _alt_eine, _alt_heute_a, _alt_lese = bw._sende_eine, bw.heute_ny, _ma.lese
    _alt_egal, _alt_amp = bw.HANDELSZEIT_EGAL, dict(bw._AMPEL)
    _alt_zusatz = bw._zusatz_daten
    _bodies, _antwort = [], [True]
    try:
        from datetime import date as _dam
        bw._sende_eine = lambda topic, titel, body, prio, klick=None: (
            _bodies.append(body) or _antwort[0])
        bw.heute_ny = lambda: _dam(2026, 9, 14)
        bw.HANDELSZEIT_EGAL = True
        _ma.lese = lambda pfad=None: _amp
        bw._zusatz_daten = lambda: {"rs": (None, {"marktbreite": _mb_e})}
        bw._AMPEL.update(tag=None, vortag=None)
        bw.kurs_vortag_merken({"A": {"prev_datum": _dam(2026, 9, 11)},
                               "B": {"prev_datum": _dam(2026, 9, 11)},
                               "C": {"prev_datum": _dam(2026, 9, 10)},
                               "D": {}})
        pruefe("E", "Waechter: Vortag der Kurse ist der haeufigste prev_datum",
               bw._AMPEL["vortag"] == "2026-09-11", bw._AMPEL["vortag"])
        _antwort[0] = False
        bw.sende("probe", "Titel", ["1. AAA"], "high")
        pruefe("E", "Waechter: scheitert die erste Meldung, bleibt der Tag "
                    "ohne Ampel-Merker", bw._AMPEL["tag"] is None
               and bool(_bodies) and _bodies[-1].startswith("Marktampel gelb"))
        _antwort[0] = True
        _bodies.clear()
        bw.sende("probe", "Titel", ["1. AAA"], "high")
        bw.sende("probe", "Titel", ["1. BBB"], "high")
        pruefe("E", "Waechter: die erste Meldung des Tages traegt die Ampel "
                    "samt Marktbreite als eigene Zeile vorn, die zweite nicht",
               len(_bodies) == 2
               and _bodies[0] == _z_mb + "\n\n1. AAA" and _bodies[1] == "1. BBB"
               and bw._AMPEL["tag"] == "2026-09-14", _bodies)
        _st_a = {"gemeldet": {}}
        _alt_file, _alt_repo_a = bw.STATE_FILE, bw.REPO_STATE
        _alt_rs = bw._repo_sichern
        import tempfile as _tfa
        with _tfa.TemporaryDirectory() as _oa:
            try:
                bw.STATE_FILE = pathlib.Path(_oa) / "cache.json"
                bw.REPO_STATE = str(pathlib.Path(_oa) / "repo.json")
                bw._repo_sichern = lambda state, sofort=False: None
                bw.save_state(_st_a)
                _gesichert = json.loads(bw.STATE_FILE.read_text())
                pathlib.Path(bw.REPO_STATE).write_text(
                    json.dumps({"gemeldet": {}, "ampel_tag": "2026-09-15"}))
                _geladen = bw.load_state()
            finally:
                bw.STATE_FILE, bw.REPO_STATE = _alt_file, _alt_repo_a
                bw._repo_sichern = _alt_rs
        pruefe("E", "Waechter: der Ampel-Tag steht im gesicherten Zustand, "
                    "und beim Laden gewinnt der juengere beider Quellen",
               _gesichert.get("ampel_tag") == "2026-09-14"
               and _geladen.get("ampel_tag") == "2026-09-15",
               f"{_gesichert.get('ampel_tag')} {_geladen.get('ampel_tag')}")
    finally:
        bw._sende_eine, bw.heute_ny, _ma.lese = _alt_eine, _alt_heute_a, _alt_lese
        bw._zusatz_daten = _alt_zusatz
        bw.HANDELSZEIT_EGAL = _alt_egal
        bw._AMPEL.clear()
        bw._AMPEL.update(_alt_amp)
    import pattern_scanner as _psk
    pruefe("E", "Earnings-Pullback steht in der Muster-PRIORITY",
           "Earnings-Pullback" in _psk.PRIORITY)
    pruefe("E", "Earnings-Pullback wird zur Kapitel-12-Klasse zahlen_luecke",
           _bb.klasse_fuer(["Earnings-Pullback"]) == "zahlen_luecke")
    pruefe("E", "Scanner reicht den Ticker an den Pullback-Detektor",
           "earnings_pullback.detect_earnings_pullback(d, ticker)" in
           open("pattern_scanner.py", encoding="utf-8").read())

    # HTF INNEN-EINSTIEG UND BENOTUNG (Soreide-Ausbau, Gerhards Freigabe
    # 31.08.2026, Baustein 3): synthetische Flagge mit Inside Day.
    import pattern_scanner as ps
    import exit_regeln as ex
    _tage_h = _pdm.bdate_range("2026-05-01", periods=60)
    _mast = [10.0] * 20 + [10.0 + 10.0 * (i + 1) / 15 for i in range(15)]
    _flagge = [19.6, 19.4, 19.6, 19.5, 19.6, 19.4, 19.8, 19.4]
    _kurs_h = _mast + _flagge + [19.4] * (60 - len(_mast) - len(_flagge))
    _kurs_h = _kurs_h[:60]
    _dfh = _pdm.DataFrame({
        "datetime": _tage_h,
        "open": _kurs_h, "close": _kurs_h,
        "high": [k + 0.2 for k in _kurs_h],
        "low": [k - 0.2 for k in _kurs_h],
        "volume": [1_000_000] * 35 + [900_000 - i * 25_000
                                      for i in range(25)],
    })
    # Der letzte Tag wird zum Inside Day des vorletzten.
    _dfh.loc[59, ["high", "low", "close", "open"]] = [19.5, 19.3, 19.4, 19.35]
    _htf = ps.detect_htf(_dfh)
    pruefe("E", "Benotung: die enge, steile, austrocknende Flagge ist Note A",
           _htf is not None and _htf.get("htf_note") == "A"
           and "Note A" in _htf.get("status", ""),
           (_htf or {}).get("status", "kein Fund"))
    _innen = ps.detect_htf_innen(_dfh)
    pruefe("E", "Innen-Einstieg: Inside Day wird zur engeren Marke",
           _innen is not None
           and _innen["strategie"] == "HTF Innen-Einstieg"
           and _innen["kaufpunkt"] < (_htf or {}).get("kaufpunkt", 0)
           and _innen["stop"] > (_htf or {}).get("stop", 99)
           and "Inside Day" in _innen["status"])
    pruefe("E", "Innen-Einstieg: ohne Flagge kein Fund",
           ps.detect_htf_innen(_pdm.DataFrame({
               "datetime": _tage_h, "open": [10.0] * 60,
               "close": [10.0] * 60, "high": [10.2] * 60,
               "low": [9.8] * 60, "volume": [1_000_000] * 60})) is None)
    pruefe("E", "Innen-Einstieg steht in allen Registern",
           "HTF Innen-Einstieg" in ps.PRIORITY
           and "HTF Innen-Einstieg" in bw.VOL_FAKTOR
           and "HTF Innen-Einstieg" in ex.STRUKTURPUNKT
           and "HTF Innen-Einstieg" in
           __import__("config").CFG["volumen"]["unbestaetigt_melden_bei"])
    import kell_zyklus as _kzk
    pruefe("E", "Kell-Phase: Nachtscan klassifiziert und protokolliert",
           "res[\"zyklus\"] = kell_zyklus.klassifiziere(df)" in
           open("pattern_scanner.py", encoding="utf-8").read()
           and "\"zyklus\": r[\"res\"].get(\"zyklus\")" in
           open("pattern_scanner.py", encoding="utf-8").read()
           and _kzk.klassifiziere(None) is None)
    import ema_crossback as _eck
    import exit_regeln as _exk
    _dfb = _eck._basisfall()
    _resb = _eck.detect_ema_crossback(_dfb)
    pruefe("E", "EMA Crossback: Marke ueber dem Umkehrtag-Hoch "
           "(Ausloesung bleibt Ausbruch, G11-Kapselung)",
           _resb is not None
           and _resb["kaufpunkt"] > float(_dfb["close"].iloc[-1])
           and _resb["strategie"] == "EMA Crossback")
    pruefe("E", "EMA Crossback steht in allen Registern",
           "EMA Crossback" in _psk.PRIORITY
           and "EMA Crossback" in bw.VOL_FAKTOR
           and "EMA Crossback" in _exk.STRUKTURPUNKT
           and "EMA Crossback" not in
           __import__("config").CFG["volumen"]["unbestaetigt_melden_bei"])
    pruefe("E", "Kapselung: kein anderes Betriebsmodul importiert die "
           "Ruecksetzer-Logik",
           "import ema_crossback" not in _bw_quelle
           and "ema_crossback" not in
           open("gewinnzonen_lauf.py", encoding="utf-8").read())
    _gzq = open("gewinnzonen_lauf.py", encoding="utf-8").read()
    pruefe("E", "Wedge Drop (G12): nur Zone stark, einmalig, laut",
           'zonen["zone"] == "stark" and not e.get("wedge_drop_gemeldet")'
           in _gzq
           and '"wedge_drop": {"prioritaet": "high", "buendeln": False}'
           in _gzq)
    pruefe("E", "G7: Stop liegt 4 Prozent unter dem Konsolidierungstief",
           "kons[\"tief\"] * (1 - C[\"porosity\"])" in
           open("earnings_pullback.py", encoding="utf-8").read())
    pruefe("E", "Innen-Einstieg bekommt die taegliche HTF-Frist",
           bw.ausbruch_schluessel(
               {"strategien": ["HTF Innen-Einstieg"], "ticker": "T",
                "nr": 2}).startswith(bw.HTF_MARKE)
           and not bw.ausbruch_schluessel(
               {"strategien": ["Rectangle Top"], "ticker": "T",
                "nr": 1}).startswith(bw.HTF_MARKE))
    _gesendet = []
    _alt_sende = bw.sende
    # klick kam mit der Handels-App dazu (07.09.2026); ohne diesen
    # Platzhalter bricht Block E ab, und alles danach wird nicht
    # mehr geprueft.
    bw.sende = lambda topic, titel, absaetze, prio="default", klick=None: (
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
    # Seit 10.09.2026 je Muster ein Schluessel: geprueft wird, ob EINER
    # davon schon im Gedaechtnis steht.
    pruefe("E", "Übersprungen prüft ZUSÄTZLICH das Wochengedächtnis",
           'wechsel == "verlassen"' in quelle_loop
           and "for k in uebersprungen_schluessel_alle(res)" in quelle_loop)
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
    # NICHT das heutige Datum: Am Freitagabend liegt die Putz-Grenze AUF
    # dem heutigen Tag, und Schluessel von heute werden konstruktions-
    # gemaess geputzt — der Test waere jeden Freitagabend rot (gefunden
    # 28.08.2026). Ein Datum NACH der Grenze ueberlebt den Filter an
    # jedem Wochentag.
    heute_s = (_d2.fromisoformat(bw.letzter_putz())
               + _td2(days=1)).isoformat()
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
    pruefe("E", "Die Schlussstunde checkt den neuesten Stand aus, nicht "
           "den beim Anstossen", "ref: ${{ github.ref }}" in quelle_w)

    # DIE STASH-KOLLISION NACHGESTELLT (Befund 10.09.2026, im Repo am
    # 18.08. und am 31.08.2026). Ein Probe-Repo mit Server, einer
    # Schlussstunde auf altem Stand und dem Endkommit der Tagwache
    # dazwischen. Die alte Fassung von _repo_sichern schrieb dabei
    # Konfliktmarken ins Logbuch. Jetzt muessen alle drei Zeilen und alle
    # drei Kennungen sauber drinstehen und das Gedaechtnis am Server liegen.
    import shutil as _sh
    import tempfile as _tf

    def _git(*a, ort=None):
        return subprocess.run(
            ["git", "-c", "user.name=probe", "-c", "user.email=probe",
             "-c", "core.autocrlf=false", *a],
            cwd=ort, capture_output=True, text=True, timeout=60)

    _ort_vorher, _stand_vorher = os.getcwd(), dict(bw._repo_stand)
    _probe = _tf.mkdtemp(prefix="stashprobe_")
    _ok, _befund = False, ""
    try:
        _server = os.path.join(_probe, "server.git")
        _git("init", "-q", "--bare", "-b", "main", _server)
        _start = os.path.join(_probe, "start")
        _git("clone", "-q", _server, _start)
        for _name, _inhalt in (("trigger_logbuch.jsonl", '{"n": 1}\n'),
                               ("ntfy_ids.json", '["a"]'),
                               ("melde_gedaechtnis.json", "{}"),
                               ("positionen.json", "{}")):
            pathlib.Path(_start, _name).write_text(_inhalt, encoding="utf-8")
        _git("add", ".", ort=_start)
        _git("commit", "-q", "-m", "Start", ort=_start)
        _git("push", "-q", "origin", "HEAD:main", ort=_start)
        _teil2 = os.path.join(_probe, "schlussstunde")
        _teil1 = os.path.join(_probe, "tagwache")
        for _ziel in (_teil2, _teil1):
            _git("clone", "-q", _server, _ziel)
        with open(os.path.join(_teil1, "trigger_logbuch.jsonl"), "a",
                  encoding="utf-8") as _f:
            _f.write('{"n": 2}\n')
        pathlib.Path(_teil1, "ntfy_ids.json").write_text('["a", "b"]',
                                                          encoding="utf-8")
        _git("commit", "-q", "-am", "Endkommit der Tagwache", ort=_teil1)
        _git("push", "-q", "origin", "main", ort=_teil1)
        with open(os.path.join(_teil2, "trigger_logbuch.jsonl"), "a",
                  encoding="utf-8") as _f:
            _f.write('{"n": 3}\n')
        pathlib.Path(_teil2, "ntfy_ids.json").write_text('["a", "c"]',
                                                          encoding="utf-8")
        os.chdir(_teil2)
        bw._repo_stand.update({"keys": None, "zeit": 0.0})
        bw._repo_sichern({"fenster_tag": "2026-09-10", "fenster": {},
                          "gemeldet": {"PROBE|Rectangle Top": "2026-09-10"}},
                         sofort=True)
        _log = pathlib.Path("trigger_logbuch.jsonl").read_text(
            encoding="utf-8")
        _zeilen = [z for z in _log.splitlines() if z.strip()]
        _marken = any(z.startswith(("<<<<<<<", ">>>>>>>")) or z == "======="
                      for z in _zeilen)
        _status = _git("status", "--porcelain", ort=_teil2).stdout.strip()
        _stash = _git("stash", "list", ort=_teil2).stdout.strip()
        _am_server = _git("--git-dir", _server, "show",
                          "main:melde_gedaechtnis.json").stdout
        _ids = json.loads(pathlib.Path("ntfy_ids.json").read_text(
            encoding="utf-8"))
        # Seit 21.09.2026 (Luecke eins) liegen Logbuch und Kennungen nach
        # der Sicherung auch schon AM SERVER, nicht erst nach dem Endkommit.
        _log_server = [json.loads(z)["n"] for z in _git(
            "--git-dir", _server, "show",
            "main:trigger_logbuch.jsonl").stdout.splitlines() if z.strip()]
        _ids_server = json.loads(_git("--git-dir", _server, "show",
                                      "main:ntfy_ids.json").stdout or "[]")
        _ok = (not _marken and "UU" not in _status and not _stash
               and sorted(json.loads(z)["n"] for z in _zeilen) == [1, 2, 3]
               and sorted(_ids) == ["a", "b", "c"]
               and "PROBE|Rectangle Top" in _am_server
               and sorted(_log_server) == [1, 2, 3]
               and sorted(_ids_server) == ["a", "b", "c"])
        _befund = (f"{len(_zeilen)} Zeilen, Marken {_marken}, Kennungen "
                   f"{sorted(_ids)}, Stash {_stash!r}, am Server "
                   f"{sorted(_log_server)} und {sorted(_ids_server)}")
    except Exception as _e:
        _befund = f"{type(_e).__name__}: {_e}"
    finally:
        os.chdir(_ort_vorher)
        bw._repo_stand.clear()
        bw._repo_stand.update(_stand_vorher)
        _sh.rmtree(_probe, ignore_errors=True)
    pruefe("E", "Stash-Kollision nachgestellt: Die Sicherung im Lauf legt "
           "keine Konfliktmarken ab und verliert keine Zeile", _ok, _befund)

    # LUECKE EINS (Gerhard, 20.09.2026, C10): Trigger-Logbuch und
    # ntfy-Kennungen gehen seit 21.09.2026 schon IM LAUF ins Repo, nicht
    # erst mit dem Endkommit; am 18.09.2026 fehlten sonst 26 Signale.
    # Nachgestellt in einem eigenen Probe-Repo: Nur das Logbuch waechst und
    # muss ohne neue Meldung an den Server; dann weist der Server einen Push
    # ab, die Zeile muss lokal bleiben und kein Commit haengen bleiben;
    # danach holt der naechste Anlauf sie nach.
    _ort_vorher, _stand_vorher = os.getcwd(), dict(bw._repo_stand)
    _probe = _tf.mkdtemp(prefix="logbuchprobe_")
    _ok, _befund = False, ""
    try:
        _server = os.path.join(_probe, "server.git")
        _git("init", "-q", "--bare", "-b", "main", _server)
        _lauf = os.path.join(_probe, "lauf")
        _git("clone", "-q", "--config", "core.autocrlf=false", _server, _lauf)
        if not os.path.isdir(os.path.join(_lauf, ".git")):
            raise RuntimeError("Probe-Klon fehlt")
        for _name, _inhalt in (("trigger_logbuch.jsonl", '{"n": 1}\n'),
                               ("ntfy_ids.json", '[\n  "a"\n]'),
                               ("melde_gedaechtnis.json", "{}"),
                               ("positionen.json", "{}")):
            pathlib.Path(_lauf, _name).write_text(_inhalt, encoding="utf-8")
        _git("add", ".", ort=_lauf)
        _git("commit", "-q", "-m", "Start", ort=_lauf)
        _git("push", "-q", "origin", "HEAD:main", ort=_lauf)
        os.chdir(_lauf)
        _zustand = {"fenster_tag": "2026-09-21", "fenster": {},
                    "gemeldet": {}}
        # Laufbeginn wie in main(): Was im Checkout steht, gilt als gesichert.
        bw._repo_stand.update({"keys": None, "zeit": 0.0,
                               "dateien": bw._anhang_stand()})
        bw._repo_sichern(_zustand)

        def _dazu(n):
            with open("trigger_logbuch.jsonl", "a", encoding="utf-8") as _f:
                _f.write('{"n": %d}\n' % n)

        def _am_server():
            return sorted(json.loads(z)["n"] for z in _git(
                "--git-dir", _server, "show",
                "main:trigger_logbuch.jsonl").stdout.splitlines()
                if z.strip())

        def _sauber():
            return not _git("status", "--porcelain", ort=_lauf).stdout.strip()

        _dazu(2)
        bw._repo_stand["zeit"] = 0.0
        bw._repo_sichern(_zustand)
        _nur_log = _am_server() == [1, 2] and _sauber()
        _haken = os.path.join(_server, "hooks", "pre-receive")
        with open(_haken, "w", encoding="utf-8", newline="\n") as _f:
            _f.write("#!/bin/sh\nexit 1\n")
        _dazu(3)
        bw._repo_stand["zeit"] = 0.0
        bw._repo_sichern(_zustand)
        _abgewiesen = (_am_server() == [1, 2]
                       and _git("rev-list", "--count", "origin/main..HEAD",
                                ort=_lauf).stdout.strip() == "0"
                       and '{"n": 3}' in pathlib.Path(
                           "trigger_logbuch.jsonl").read_text(encoding="utf-8")
                       and bw._repo_stand["dateien"] != bw._anhang_stand())
        os.remove(_haken)
        bw._repo_stand["zeit"] = 0.0
        bw._repo_sichern(_zustand)
        _nachgeholt = _am_server() == [1, 2, 3] and _sauber()
        _ok = _nur_log and _abgewiesen and _nachgeholt
        _befund = (f"nur Logbuch {_nur_log}, abgewiesen {_abgewiesen}, "
                   f"nachgeholt {_nachgeholt}")
    except Exception as _e:
        _befund = f"{type(_e).__name__}: {_e}"
    finally:
        os.chdir(_ort_vorher)
        bw._repo_stand.clear()
        bw._repo_stand.update(_stand_vorher)
        _sh.rmtree(_probe, ignore_errors=True)
    pruefe("E", "Logbuch im Lauf gesichert: Eine neue Zeile geht ohne neue "
           "Meldung ins Repo, ein abgewiesener Push laesst sie lokal und "
           "nichts haengen, der naechste Anlauf holt sie nach", _ok, _befund)
    pruefe("E", "Der Datenabruf sichert ein gewachsenes Logbuch auch ohne "
           "neue Meldung (Luecke eins)",
           '_anhang_stand() != _repo_stand["dateien"]' in quelle_bw
           and '_repo_stand["dateien"] = _anhang_stand()' in quelle_bw)

    # LUECKEN ZWEI UND DREI (Gerhard, 20.09.2026, C10): Insider-Kaeufe und
    # nachgereichte Volumenbestaetigungen bekommen seit 21.09.2026 je eine
    # eigene Logbuch-Zeile. Geschrieben wird in ein eigenes Verzeichnis;
    # Senden, Zustand und Marktwert sind abgefangen, es geht nichts hinaus.
    import insider_edgar as _ie2
    import trigger_logbuch as _tl2
    _ort_vorher = os.getcwd()
    _probe = _tf.mkdtemp(prefix="logbuchzeilen_")
    _alt = {n: getattr(bw, n) for n in ("_marktwert_heute", "push_frei",
                                        "sende", "save_state",
                                        "beobachtungen_eintragen")}
    _alt_ie = {n: getattr(_ie2, n) for n in ("lies_speicher", "lies_rollen")}
    _ins, _nach, _befund = False, False, ""
    try:
        os.chdir(_probe)
        from datetime import date as _dz
        _heute = _dz.today()
        _kauf = _ie2.isc.InsiderKauf("Probe", 30_000_000.0, _heute, "P",
                                     "Direktor")
        _fund = {"ticker": "PRB", "status": "pfad_a", "marktkap": 5.0e9,
                 "stichtag": _heute.isoformat(), "zeilen": ["Probe"],
                 "kennung": "PRB|pfad_a|0"}
        _gesendet, _gesichert = [], []
        bw._marktwert_heute = lambda s, k, h: 5.0e9
        bw.push_frei = lambda jetzt=None: True
        bw.sende = lambda *a, **k: (_gesendet.append(a) or True)
        bw.save_state = lambda *a, **k: _gesichert.append(k)
        bw.beobachtungen_eintragen = lambda *a, **k: None
        _ie2.lies_speicher = lambda *a, **k: {"PRB": [_kauf]}
        _ie2.lies_rollen = lambda *a, **k: {}
        _erg = bw.nachtbefunde_schritt(
            "probe-kein-thema",
            {"offen": [("insider", _fund)], "live": [], "insider": [_fund],
             "verlaeufe": {}},
            {"PRB": {"close": 50.0, "prev_close": 49.0}}, None, set(),
            {"gemeldet": {}}, dry_run=False)
        _z = _tl2.lies("trigger_logbuch.jsonl")
        _ins = (_erg is True and len(_gesendet) == 1 and len(_z) == 1
                and _z[0].get("quelle") == "waechter/insider"
                and _z[0].get("kaufpunkt") == 50.0
                and _z[0].get("pfad_a") is True
                and _z[0].get("groesster_kauf_dollar") == 30_000_000.0
                and _z[0].get("trockenlauf") is False
                and _tl2.zaehlt_mit(_z[0])
                and _gesichert == [{"sofort": True}])
        _t = {"ticker": "PRB", "strategie": "Rectangle Top",
              "kaufpunkt": 10.0, "kurs": 10.4, "vol_ok": True,
              "vol_ratio": 1.6, "vol_anteil": 0.4,
              "key": "PRB|Rectangle Top|10.0",
              "key_best": "PRB|Rectangle Top|10.0|b"}
        _im = set()
        _n1 = bw.nachtrag_ins_logbuch([_t], _im, trocken=False)
        _n2 = bw.nachtrag_ins_logbuch([_t], _im, trocken=False)
        _zn = [z for z in _tl2.lies("trigger_logbuch.jsonl")
               if z.get("quelle") == "waechter/nachtrag"]
        _nach = (_n1 == 1 and _n2 == 0 and len(_zn) == 1
                 and _zn[0].get("nachtrag") is True
                 and _zn[0].get("vol_bestaetigt") is True
                 and _zn[0].get("kurs") == 10.4
                 and not _tl2.zaehlt_mit(_zn[0]))
        _befund = (f"Insider {_ins} (Rueckgabe {_erg}, {len(_z)} Zeile(n)), "
                   f"Nachtrag {_nach} ({_n1} und {_n2})")
    except Exception as _e:
        _befund = f"{type(_e).__name__}: {_e}"
    finally:
        os.chdir(_ort_vorher)
        for _n, _v in _alt.items():
            setattr(bw, _n, _v)
        for _n, _v in _alt_ie.items():
            setattr(_ie2, _n, _v)
        _sh.rmtree(_probe, ignore_errors=True)
    pruefe("E", "Ein gemeldeter Insider-Kauf steht mit Einstieg und "
           "Signalzahlen im Logbuch (Luecke zwei)", _ins, _befund)
    pruefe("E", "Ein Nachtrag steht genau einmal im Logbuch und zaehlt "
           "nicht als eigenes Signal (Luecke drei)", _nach, _befund)

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

    # MELDESCHLUESSEL NACH MUSTER (Befund 09.09.2026, gebaut 10.09.2026).
    # LITE: Rectangle Top stand am 08.09. auf Platz 1, am 09.09. auf Platz 3.
    _lite = {"ticker": "LITE", "strategie": "Rectangle Top", "nr": 3}
    pruefe("E", "Meldeschluessel nach Muster, nicht nach Platznummer",
           bw.ausbruch_schluessel(_lite) == "LITE|Rectangle Top"
           and bw.ausbruch_schluessel({**_lite, "nr": 1})
           == bw.ausbruch_schluessel(_lite))
    _paar = {"ticker": "CRDX", "strategie": "High & Tight Flag", "nr": 1,
             "strategien": ["High & Tight Flag", "Darvas Box"]}
    pruefe("E", "Zwei Muster auf einem Preis: je Muster ein Schluessel",
           bw.ausbruch_schluessel_alle(_paar)
           == [bw.HTF_MARKE + "CRDX|Darvas Box",
               bw.HTF_MARKE + "CRDX|High & Tight Flag"])
    _rk = {"key": "X", "key_best": "Y", "vol_ok": True,
           "strategie": "Darvas Box",
           "keys": ["LITE|Cup & Handle", "LITE|Rectangle Top"],
           "keys_best": ["BEST|LITE|Cup & Handle", "BEST|LITE|Rectangle Top"]}
    pruefe("E", "Ein gemeldetes Muster genuegt, der Ausbruch gilt als gemeldet",
           bw.melde_stufe(_rk, {"LITE|Rectangle Top"}) == "nachtrag"
           and bw.melde_stufe(_rk, {"LITE|Rectangle Top",
                                    "BEST|LITE|Cup & Handle"}) is None)
    pruefe("E", "Uebersprungen- und Fenster-Schluessel ebenfalls nach Muster",
           bw.uebersprungen_schluessel(_lite)
           == bw.UEBERSPRUNGEN_MARKE + "LITE|Rectangle Top"
           and bw.fenster_schluessel(_lite) == "LITE|Rectangle Top")
    import beobachtungen as _bbk
    _bstk = {}
    _bbk.oeffnen(_bstk, "LITE", 1, "Rectangle Top", 900.0, 850.0)
    pruefe("E", "Alte Beobachtung mit Platznummer verhindert eine zweite",
           _bbk.offen_mit_strategie(_bstk, "lite", ["Rectangle Top"]) == "LITE|1"
           and _bbk.offen_mit_strategie(_bstk, "LITE", ["Cup & Handle"]) is None)

    # NICHTS AUS DER NACHT VOR DEM ERSTEN KURSABRUF (10.09.2026)
    _bwq = pathlib.Path("breakout_watcher.py").read_text(encoding="utf-8")
    _haupt_q = _bwq[_bwq.index("def main():"):]
    pruefe("E", "Waechter: nichts aus der Nacht vor dem ersten Kursabruf",
           "melde_exit_befunde(" not in _bwq
           and "melde_sektor_radar(" not in _haupt_q
           and "melde_insider(" not in _bwq
           and _haupt_q.index("fetch_quotes_yahoo(abruf_ticker)")
           < _haupt_q.index("nachtbefunde_schritt("))

    # EINZELABRUF EINES TICKERS (Befund 09.09.2026): yfinance 1.5 liefert
    # auch dann verschachtelte Spalten. Nachgestellt ohne Netz.
    import types as _tyk
    import pandas as _pdn
    _ixn = _pdn.date_range("2026-09-08", periods=3, freq="B")
    _spn = _pdn.MultiIndex.from_product(
        [["^IXIC"], ["Open", "High", "Low", "Close", "Adj Close", "Volume"]])
    _rohn = _pdn.DataFrame([[1.0, 2.0, 0.5, 1.5, 1.5, 100.0]] * 3,
                           index=_ixn, columns=_spn)
    _alt_yf = sys.modules.get("yfinance")
    sys.modules["yfinance"] = _tyk.SimpleNamespace(
        download=lambda *a, **k: _rohn)
    try:
        _qn = bw.fetch_quotes_yahoo(["^IXIC"])
    finally:
        if _alt_yf is not None:
            sys.modules["yfinance"] = _alt_yf
        else:
            sys.modules.pop("yfinance", None)
    pruefe("E", "Einzelabruf eines Tickers liefert Kurse (Nasdaq-Regime)",
           "^IXIC" in _qn and _qn["^IXIC"].get("open") == 1.0
           and _qn["^IXIC"].get("prev_datum") is not None)

    # RED-TO-GREEN: gestrige Zeile zaehlt nicht, ein Fehlversuch schaltet den
    # Tag nicht stumm (10.09.2026)
    from datetime import date as _dr
    _alt_r = (bw.fetch_quotes_yahoo, bw._r2g_regime,
              bw._r2g_naechster_versuch, bw._r2g_fehlversuche, bw.heute_ny)
    try:
        bw._r2g_regime, bw._r2g_naechster_versuch = None, 0.0
        bw._r2g_fehlversuche = 0
        bw.heute_ny = lambda: _dr(2026, 9, 9)
        bw.fetch_quotes_yahoo = lambda t: {"^IXIC": {
            "open": 100.0, "prev_close": 103.0, "bar_datum": _dr(2026, 9, 8)}}
        _r1 = bw.r2g_regime_pruefen()
        pruefe("E", "Red-to-Green: gestrige Tageszeile zaehlt nicht und "
               "schaltet den Tag nicht stumm",
               _r1 is False and bw._r2g_regime is None)
        bw._r2g_naechster_versuch = 0.0
        bw.fetch_quotes_yahoo = lambda t: {"^IXIC": {
            "open": 100.0, "prev_close": 103.0, "bar_datum": _dr(2026, 9, 9)}}
        bw.r2g_regime_pruefen()
        pruefe("E", "Red-to-Green: mit heutiger Zeile wird entschieden",
               bw._r2g_regime is not None)
    finally:
        (bw.fetch_quotes_yahoo, bw._r2g_regime, bw._r2g_naechster_versuch,
         bw._r2g_fehlversuche, bw.heute_ny) = _alt_r

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
            "[\U0001F000-\U0001FAFF\u2190-\u21FF\u2300-\u27BF"
            "\u2900-\u297F\u2B00-\u2BFF\uFE0F]")
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

    # Push-Sammler (Gerhards Go vom 02.09.2026): Mindestabstand zwischen
    # zwei Pushes, damit Apples Push-Dienst keine Serie mehr verschluckt.
    from config import CFG as _cfg
    abstand = float(_cfg.get("push", {}).get("mindestabstand_s", 0))
    pruefe("E", "Push-Sammler: Mindestabstand in der Konfiguration (mindestens 5 s)",
           abstand >= 5, abstand)
    quelle = (WURZEL / "breakout_watcher.py").read_text(encoding="utf-8")
    sende_eine = quelle[quelle.index("def _sende_eine("):quelle.index("HANDELSZEIT_EGAL = False")]
    pruefe("E", "Push-Sammler: _sende_eine wartet VOR dem Senden und prueft danach die Uhr",
           "push_abstand_warten()" in sende_eine
           and sende_eine.index("push_abstand_warten()") < sende_eine.index("requests.post")
           and sende_eine.index("markt_offen()") < sende_eine.index("requests.post"))
    pruefe("E", "Push-Sammler: der Zeitpunkt wird nur nach angenommenem Push gemerkt",
           "_LETZTER_PUSH = time.monotonic()" in sende_eine
           and sende_eine.index("merke_antwort(r)") < sende_eine.index("_LETZTER_PUSH = time.monotonic()"))
    gewartet = []
    _alt = bw._LETZTER_PUSH
    try:
        bw._LETZTER_PUSH = None
        pruefe("E", "Push-Sammler: vor dem ersten Push kein Warten",
               bw.push_abstand_warten(jetzt=1000.0, schlafe=gewartet.append) == 0.0 and not gewartet)
        bw._LETZTER_PUSH = 1000.0
        w = bw.push_abstand_warten(jetzt=1001.0, schlafe=gewartet.append)
        pruefe("E", "Push-Sammler: eine Sekunde nach dem Push wird der Rest des Abstands gewartet",
               abs(w - (abstand - 1.0)) < 1e-6 and gewartet == [w], w)
        gewartet.clear()
        pruefe("E", "Push-Sammler: nach Ablauf des Abstands kein Warten",
               bw.push_abstand_warten(jetzt=1000.0 + abstand + 0.5, schlafe=gewartet.append) == 0.0
               and not gewartet)
    finally:
        bw._LETZTER_PUSH = _alt


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
    # ETAPPE 0 (Gerhard, 13.09.2026): config.py fuehrt nur Einstellwerte, die
    # ein Modul liest. Ein Wert ohne Leser ist eine Falle: Wer ihn aendert,
    # aendert nichts und glaubt es doch.
    try:
        _ohne = config_ohne_leser(WURZEL)
        pruefe("H", "Jeder Einstellwert in config.py hat einen Leser",
               not _ohne, nennen(_ohne))
    except Exception as e:
        pruefe("H", "Jeder Einstellwert in config.py hat einen Leser", False,
               f"{type(e).__name__}: {e}")
    _wf = WURZEL / ".github" / "workflows"
    pruefe("H", "Nachtscan legt die Marktampel ins Repo (git add und Sicherung)",
           (_wf / "scanner.yml").read_text(encoding="utf-8").count(
               "marktampel.json") >= 2)
    pruefe("H", "Nachschlage-Ablauf kann die Mappe fuer die Listen-Aktien lesen",
           "openpyxl" in (_wf / "nachschlag_daten.yml").read_text(encoding="utf-8"))

    # Datenlage: ist die Mappe frisch genug fuer heute?
    # GEGEN DAS REPO messen, nicht gegen den lokalen Klon. Der kann
    # veraltet sein, und dann meldet die Pruefung einen Ausfall, den es
    # gar nicht gibt — genau so am 11.08.2026 passiert (34,8 Stunden
    # gemeldet, in Wahrheit lief der Nachtscan puenktlich).
    import subprocess as sp
    # ALLE Zweige holen, nicht nur main: Der Listen-Abgleich weiter
    # unten vergleicht die Wochenlisten der Arbeitszweige mit denen von
    # main, und ein zweiter Abruf waere dafuer Verschwendung.
    # --prune: Ein auf GitHub geloeschter Zweig soll unten nicht mehr als
    # Zweig mit Wochenliste auftauchen.
    sp.run(["git", "fetch", "-q", "--prune", "origin"], cwd=WURZEL,
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

    # DIESELBEN WOCHENLISTEN AUF ALLEN ZWEIGEN (Mathias, 08.09.2026).
    # Die Listen sind Nutzerdaten, liegen aber im Code-Repo und damit je
    # Zweig getrennt. Wer sie von Hand auf dem Arbeitszweig einspielt,
    # laesst main mit der alten Liste zurueck (genau so geschehen am
    # 07.09.2026: Der Nachtscan lief noch ueber 159 Aktien, waehrend auf
    # fundament-phase1 laengst 243 standen); wer nur ueber die
    # Heliot-Seite hochlaedt, traf frueher NUR main.
    #
    # Der Upload schreibt seit 08.09.2026 auf jeden Zweig der Liste
    # LISTEN_ZWEIGE (streamlit_app.py). Diese Pruefung ist das Netz
    # darunter. Genannt werden die Ticker, nicht bloss die Zahl.
    #
    # DIE ZWEIGE ZAEHLT SIE SEIT 10.09.2026 SELBST AUF. Bis dahin stand hier
    # dieselbe feste Liste wie im Upload, und die Kommentare behaupteten,
    # ein vergessener neuer Arbeitszweig falle hier auf. Das stimmte nicht:
    # Einen dritten Zweig sah die Pruefung gar nicht an. Jetzt nimmt sie
    # jeden Zweig auf origin ausser den Sicherungszweigen (Name beginnt mit
    # stand-, sicherung oder backup, etwa stand-vor-umbau) und meldet jeden
    # Zweig mit Wochenliste, der in LISTEN_ZWEIGE fehlt.
    import io as _io
    import re as _reh
    import ast as _asth
    import pandas as _pdz
    _refs = sp.run(["git", "for-each-ref", "--format=%(refname)",
                    "refs/remotes/origin"], cwd=WURZEL, capture_output=True,
                   text=True).stdout.split()
    _alle_zweige = sorted({r[len("refs/remotes/origin/"):] for r in _refs
                           if r.startswith("refs/remotes/origin/")
                           and not r.endswith("/HEAD")})
    _sicherung = _reh.compile(r"^(stand-|sicherung|backup)", _reh.IGNORECASE)
    _listen_zweige = [z for z in _alle_zweige if not _sicherung.match(z)]
    if "main" in _listen_zweige:          # verglichen wird gegen main
        _listen_zweige.remove("main")
        _listen_zweige.insert(0, "main")
    _upload = ()
    try:
        for _knoten in _asth.parse((WURZEL / "streamlit_app.py").read_text(
                encoding="utf-8")).body:
            if (isinstance(_knoten, _asth.Assign)
                    and any(getattr(_zi, "id", "") == "LISTEN_ZWEIGE"
                            for _zi in _knoten.targets)):
                _upload = tuple(_asth.literal_eval(_knoten.value))
    except Exception:
        _upload = ()
    _ausgenommen = [z for z in _alle_zweige if z not in _listen_zweige]
    pruefe("H", "Zweige selbst aufgezaehlt, Sicherungszweige ausgenommen",
           "main" in _listen_zweige,
           "geprueft: " + ", ".join(_listen_zweige)
           + ("; ausgenommen: " + ", ".join(_ausgenommen)
              if _ausgenommen else ""))
    _mit_liste = set()
    # einzelaktien.csv seit 21.09.2026 (S7): dieselbe Pflicht wie die beiden
    # Wochenlisten, der Upload-Weg schreibt sie auf jeden Zweig.
    for _datei in ("finviz_3.csv", "darvas.csv", "einzelaktien.csv"):
        _stand = {}
        for _z in _listen_zweige:
            _r = sp.run(["git", "show", f"origin/{_z}:{_datei}"],
                        cwd=WURZEL, capture_output=True)
            if _r.returncode != 0:
                continue          # Dieser Zweig fuehrt die Datei nicht
            _mit_liste.add(_z)
            try:
                _stand[_z] = set(_pdz.read_csv(_io.BytesIO(_r.stdout))
                                 ["Ticker"].astype(str).str.upper())
            except Exception:
                _stand[_z] = None
        if len(_stand) < 2:
            pruefe("H", f"{_datei}: alle Zweige fuehren dieselbe Liste",
                   True, "nur ein Zweig fuehrt diese Datei")
            continue
        _haupt = _listen_zweige[0]
        _abw = []
        for _z, _t in _stand.items():
            if _z == _haupt:
                continue
            if _t is None or _stand.get(_haupt) is None:
                _abw.append(f"{_z}: nicht lesbar")
                continue
            if _t != _stand[_haupt]:
                _teile = []
                _fehlt = sorted(_stand[_haupt] - _t)
                _extra = sorted(_t - _stand[_haupt])
                if _fehlt:
                    _teile.append(f"fehlen auf {_z}: " + nennen(_fehlt))
                if _extra:
                    _teile.append(f"nur auf {_z}: " + nennen(_extra))
                _abw.append(", ".join(_teile))
        _zahlen = "; ".join(
            f"{_z}: {len(_t) if _t is not None else '?'}"
            for _z, _t in _stand.items())
        pruefe("H", f"{_datei}: alle Zweige fuehren dieselbe Liste",
               not _abw,
               _zahlen + ((" | " + " | ".join(_abw)) if _abw else ""))
    _fehlt_upload = sorted(_mit_liste - set(_upload))
    pruefe("H", "Jeder Zweig mit Wochenliste steht in LISTEN_ZWEIGE "
           "(sonst traefe ihn der Upload nicht)",
           bool(_upload) and not _fehlt_upload,
           ("fehlen: " + ", ".join(_fehlt_upload)) if _fehlt_upload
           else "LISTEN_ZWEIGE: " + ", ".join(_upload))

    for datei in ("volumenkurven.json", "fokusliste.json",
                  "shakeout_warteliste.json"):
        pruefe("H", f"{datei} vorhanden und lesbar",
               (WURZEL / datei).exists()
               and isinstance(json.loads((WURZEL / datei).read_text(
                   encoding="utf-8")), (dict, list)))
    # WAS DER LETZTE SCAN AUSGELASSEN HAT (Mathias, 07.09.2026).
    # Der Scanner ueberspringt Aktien ohne lebendige Kurse, ehe ein
    # Detektor sie zu sehen bekommt (siehe pattern_scanner.lebendig).
    # Damit ein stillgelegter Wert nicht bloss unbemerkt aus der Mappe
    # verschwindet, wird hier nachgelesen, WELCHE es waren und warum.
    # Das ist eine Auskunft, kein Mangel: Ausgelassen zu haben ist genau
    # das gewuenschte Verhalten. Ein Mangel waere nur, wenn eine solche
    # Aktie danach trotzdem mit Kaufpunkten in der Mappe stuende, denn
    # dann bewachte der Waechter einen Wert, den der Scanner aufgegeben
    # hat.
    try:
        import pattern_scanner as _psa
        _ausgelassen = WURZEL / _psa.AUSGELASSEN_DATEI
    except Exception:
        _ausgelassen = WURZEL / "ausgelassen.json"
    if _ausgelassen.exists():
        try:
            _a = json.loads(_ausgelassen.read_text(encoding="utf-8"))
            _liste = _a.get("aktien") or []
            _zeilen = [f"{x.get('ticker')} ({x.get('grund')})"
                       for x in _liste]
            pruefe("H", "Ausgelassene Aktien des letzten Scans benannt",
                   True,
                   (f"Stand {_a.get('stand')}, {len(_liste)} von "
                    f"{_a.get('liste')}: " + nennen(_zeilen)) if _liste
                   else f"Stand {_a.get('stand')}, keine ausgelassen")
            _in_mappe = []
            if _liste and (WURZEL / "kaufpunkte_aktuell.xlsx").exists():
                import pandas as _pdh
                _m = _pdh.read_excel(WURZEL / "kaufpunkte_aktuell.xlsx")
                _in_mappe = sorted(
                    {str(x.get("ticker")) for x in _liste}
                    & set(_m["Ticker"].astype(str)))
            pruefe("H", "Keine ausgelassene Aktie steht noch in der Mappe",
                   not _in_mappe, ", ".join(_in_mappe))
        except Exception as e:
            pruefe("H", f"{_ausgelassen.name} lesbar", False,
                   f"{type(e).__name__}: {e}")
    else:
        pruefe("H", "Ausgelassene Aktien des letzten Scans benannt", True,
               f"{_ausgelassen.name} entsteht mit dem naechsten Nachtscan")

    # ETAPPE 2 (Gerhard, 13.09.2026, Entscheidungen 4 und 5): Die Nachtdatei
    # traegt je Aktie die technischen Kennzahlen, das Allzeithoch fuer das
    # ganze Universum und den Stand seines letzten vollen Abrufs.
    _rsd = WURZEL / "rs_universum.json"
    try:
        _rs = json.loads(_rsd.read_text(encoding="utf-8")) if _rsd.exists() else {}
    except Exception as e:
        _rs = {}
        pruefe("H", "rs_universum.json lesbar", False, f"{type(e).__name__}: {e}")
    if _rs and isinstance(_rs.get("allzeithoch"), dict):
        _mit_kurs = [(t, e) for g in ("aktien", "ausserhalb", "listen")
                     for t, e in (_rs.get(g) or {}).items() if isinstance(e, dict) and e.get("kurs") is not None]
        _ohne_tk = [t for t, e in _mit_kurs if not e.get("technik")]
        pruefe("H", "Technische Kennzahlen fuer jede Aktie mit Kurs", not _ohne_tk,
               f"{len(_mit_kurs) - len(_ohne_tk)} von {len(_mit_kurs)}" + (": " + nennen(_ohne_tk) if _ohne_tk else ""))
        _mit_ath = sum(1 for _t, e in _mit_kurs if (e.get("technik") or {}).get("ath") is not None)
        _ath = _rs["allzeithoch"]
        pruefe("H", "Allzeithoch fuer mindestens 95 Prozent der Aktien mit Kurs",
               _mit_kurs and _mit_ath / len(_mit_kurs) >= 0.95,
               f"{_mit_ath} von {len(_mit_kurs)}; voller Abruf am {_ath.get('voll_am')}, heute {_ath.get('abruf_heute')}, "
               f"Quellen {_ath.get('quellen')}")
        try:
            _alter_ath = (datetime.now(timezone.utc).date() - datetime.fromisoformat(str(_ath.get("voll_am"))[:10]).date()).days
        except Exception:
            _alter_ath = None
        pruefe("H", "Voller Abruf des Allzeithochs nicht aelter als seine Frist plus drei Tage",
               _alter_ath is not None and _alter_ath <= int(_ath.get("abruf_tage") or 7) + 3,
               f"{_alter_ath} Tage" if _alter_ath is not None else "noch kein voller Abruf")
    else:
        pruefe("H", "Technische Kennzahlen in rs_universum.json", True,
               "die Datei stammt noch vom Stand vor Etappe 2; der naechste Nachtscan legt sie an")

    # ETAPPE 3 (Gerhard, 13.09.2026, Entscheidung 6): die Marktbreite in der
    # Nachtdatei, die Distribution Days je Index in der Marktampel.
    if _rs and "marktbreite" in _rs:
        _mb_h = _rs.get("marktbreite") or {}
        _titel_h = sum(1 for g in ("aktien", "ausserhalb") for e in (_rs.get(g) or {}).values()
                       if isinstance(e, dict) and e.get("technik"))
        pruefe("H", "Marktbreite gerechnet, zum Handelstag der Nachtdatei und ueber mindestens 90 Prozent "
                    "der Titel mit Kennzahlen",
               not _mb_h.get("fehler") and _mb_h.get("handelstag") == _rs.get("handelstag")
               and _titel_h > 0 and (_mb_h.get("aktien_heute") or 0) >= 0.9 * _titel_h,
               f"{_mb_h.get('aktien_heute')} von {_titel_h} Titeln, Handelstag {_mb_h.get('handelstag')} gegen "
               f"{_rs.get('handelstag')}" + (f", Fehler {_mb_h.get('fehler')}" if _mb_h.get("fehler") else ""))
    else:
        pruefe("H", "Marktbreite in rs_universum.json", True,
               "die Datei stammt noch vom Stand vor Etappe 3; der naechste Nachtscan legt sie an")
    try:
        _amp_h = json.loads((WURZEL / "marktampel.json").read_text(encoding="utf-8"))
    except Exception:
        _amp_h = {}
    _lagen_h = [l for l in ((_amp_h or {}).get("indizes") or {}).values() if isinstance(l, dict)]
    if any("distribution_days" in l for l in _lagen_h):
        pruefe("H", "Marktampel traegt je Index Distribution Days und Marktphase",
               all("distribution_days" in l and isinstance(l.get("phase"), dict) for l in _lagen_h),
               f"{len(_lagen_h)} Indizes")
    else:
        pruefe("H", "Distribution Days in marktampel.json", True,
               "die Datei stammt noch vom Stand vor Etappe 3; der naechste Nachtscan legt sie an")

    # ETAPPE 4 (Gerhard, 13.09.2026, Entscheidungen 7 und 8): je Aktie mit
    # SEC-Zuordnung die fundamentalen Kennzahlen, die SMR-Bausteine und die
    # drei CAN-SLIM-Haekchen.
    try:
        _ibd_h = json.loads((WURZEL / "ibd_ratings.json").read_text(encoding="utf-8"))
    except Exception:
        _ibd_h = {}
    _akt_h = [(t, e) for t, e in ((_ibd_h or {}).get("aktien") or {}).items() if isinstance(e, dict) and e.get("cik")]
    if any("fundament" in e for _t, e in _akt_h):
        _mit_f = [t for t, e in _akt_h if isinstance(e.get("fundament"), dict) and "fehler" not in e["fundament"]]
        _fehl_f = [t for t, e in _akt_h if isinstance(e.get("fundament"), dict) and "fehler" in e["fundament"]]
        pruefe("H", "Fundamentale Kennzahlen fuer mindestens 80 Prozent der Aktien mit SEC-Zuordnung, Rechenfehler "
                    "bei hoechstens einem Prozent",
               _akt_h and len(_mit_f) >= 0.8 * len(_akt_h) and len(_fehl_f) <= 0.01 * len(_akt_h),
               f"{len(_mit_f)} von {len(_akt_h)}, Fehler {len(_fehl_f)}" + (": " + nennen(_fehl_f) if _fehl_f else ""))
        _ohne_cs = [t for t, e in _akt_h if e.get("smr") and not (e.get("smr_bausteine") and e.get("canslim"))]
        pruefe("H", "SMR-Bausteine und CAN-SLIM-Haekchen bei jeder Aktie mit SMR-Note", not _ohne_cs,
               nennen(_ohne_cs) if _ohne_cs else f"{sum(1 for _t, e in _akt_h if e.get('smr'))} Aktien mit SMR-Note")
        _stand_h = (_ibd_h or {}).get("fundament_stand") or {}
        pruefe("H", "Fundament-Stand vermerkt (Firmen, Filer-Typen, Jahre)",
               (_stand_h.get("firmen") or 0) > 0 and (_stand_h.get("filer_typen") or 0) > 0,
               f"{_stand_h}")
    else:
        pruefe("H", "Fundamentale Kennzahlen in ibd_ratings.json", True,
               "die Datei stammt noch vom Stand vor Etappe 4; der naechste Nachtscan legt sie an")

    # ETAPPE 5 (Gerhard, 13.09.2026, Entscheidung 9): Der Bau der Nachttabelle
    # vermerkt je Quelle, ob Konsens und Revisionen da sind. Die Werte selbst
    # liegen im privaten Datenrepo und werden hier nicht gelesen.
    try:
        _sst_h = json.loads((WURZEL / "scanner_stand.json").read_text(encoding="utf-8"))
    except Exception:
        _sst_h = {}
    _q_h = (_sst_h or {}).get("quellen") or {}
    if "konsens" in _q_h:
        _k_h, _r_h = _q_h.get("konsens") or {}, _q_h.get("revisionen") or {}
        pruefe("H", "Nachttabelle: Einfrier-Laeufe gelesen, Konsens fuer mindestens die Haelfte der Aktien, "
                    "juengster Lauf hoechstens vier Tage alt",
               _k_h.get("status") == "ok" and (_k_h.get("mit_konsens") or 0) >= 0.5 * (_sst_h.get("zeilen") or 1)
               and bool(_k_h.get("neuester"))
               and (datetime.now(timezone.utc) - datetime.fromisoformat(str(_k_h["neuester"]).replace("Z", "+00:00"))).days <= 4,
               f"{_k_h.get('status')}, {_k_h.get('mit_konsens')} von {_sst_h.get('zeilen')} Aktien, juengster Lauf "
               f"{_k_h.get('neuester')}, Dateien {len(_k_h.get('dateien') or [])}")
        pruefe("H", "Nachttabelle: Revisionen fuer die Wochenliste abgerufen, hoechstens ein Zehntel Fehler",
               _r_h.get("status") == "ok" and (_r_h.get("fehler") or 0) <= 0.1 * max(1, _r_h.get("wochenliste") or 0)
               and (_r_h.get("mit_stand") or 0) >= 0.9 * (_r_h.get("wochenliste") or 0),
               f"{_r_h}")
        pruefe("H", "Nachttabelle: EPS-Konsens aus dem Nasdaq-Kalender vermerkt",
               "mit_eps_konsens" in (_q_h.get("kalender") or {}), f"{_q_h.get('kalender')}")
    else:
        pruefe("H", "Konsens in der Nachttabelle", True,
               "scanner_stand.json stammt noch vom Stand vor Etappe 5; der naechste Bau legt es an")
    # ETAPPE 7 (Gerhard, 13.09.2026, Entscheidung 12): Short-Volumen laut FINRA
    # mit der Mindestabdeckung des RS-Universums.
    if "short_volumen" in _q_h:
        _s_h = _q_h.get("short_volumen") or {}
        pruefe("H", "Nachttabelle: FINRA-Tagesdateien aller 20 Handelstage verwendbar, juengste Datei ueber der "
                    "Mindestabdeckung, Handelstag der Tabelle",
               _s_h.get("status") == "ok" and _s_h.get("letzter_tag") == _sst_h.get("handelstag")
               and (_s_h.get("abdeckung_letzter_tag") or 0) >= float(_s_h.get("mindest_abdeckung") or 1.0),
               f"{_s_h.get('status')}, letzter Tag {_s_h.get('letzter_tag')} gegen Handelstag {_sst_h.get('handelstag')}, "
               f"Abdeckung {_s_h.get('abdeckung_letzter_tag')}, fehlend {_s_h.get('fehlend')}")
    else:
        pruefe("H", "Short-Volumen in der Nachttabelle", True,
               "scanner_stand.json stammt noch vom Stand vor Etappe 7; der naechste Bau legt es an")
    # ETAPPE 6 (Gerhard, 13.09.2026, Entscheidungen 10 und 11): Industry Group
    # RS. Ohne Zuordnungsliste ist "nicht verfuegbar" der richtige Zustand; mit
    # ihr muessen alle drei Raenge da sein und die meisten Aktien eine Gruppe
    # tragen.
    if "gruppen_rs" in _q_h:
        _g_h = _q_h.get("gruppen_rs") or {}
        if _g_h.get("zuordnung_stand"):
            _anteil_g = (_g_h.get("mit_gruppe") or 0) / max(1, _g_h.get("aktien") or 0)
            pruefe("H", "Nachttabelle: Industry Group RS mit Rang heute und vor drei und sechs Wochen, Stichtag gleich "
                        "Handelstag, mindestens drei Viertel der Aktien mit Gruppe",
                   _g_h.get("status") == "ok" and (_g_h.get("stichtage") or {}).get("heute") == _sst_h.get("handelstag")
                   and _anteil_g >= 0.75,
                   f"{_g_h.get('status')}, Stichtage {_g_h.get('stichtage')}, Handelstag {_sst_h.get('handelstag')}, "
                   f"{_g_h.get('mit_gruppe')} von {_g_h.get('aktien')} mit Gruppe, {_g_h.get('gruppen_heute')} Gruppen, "
                   f"Liste vom {_g_h.get('zuordnung_stand')}")
        else:
            pruefe("H", "Nachttabelle: ohne Zuordnungsliste ist die Industry Group RS ehrlich nicht verfuegbar",
                   str(_g_h.get("status") or "").startswith("nicht verfuegbar") and bool(_g_h.get("grund")),
                   f"{_g_h.get('status')}, {_g_h.get('grund')}")
    else:
        pruefe("H", "Industry Group RS in der Nachttabelle", True,
               "scanner_stand.json stammt noch vom Stand vor Etappe 6; der naechste Bau legt es an")

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

    # DIE WOCHENLISTE STEHT HINTER DER ANMELDUNG (Mathias, 13.09.2026).
    ok, zusatz = anmeldeschranke(WURZEL / "streamlit_app.py")
    pruefe("H", "Wochenliste und Gastpasswoerter nur mit vollem Zugang", ok, zusatz)

    # KEINE BILDZEICHEN (Mathias, 14.09.2026: "Entferne konsequent alle
    # Emojis des Webtools und lass sie entfernt bzw. achte darauf, dass sie
    # nicht wieder erstellt werden, dies gilt für all unsere Tools").
    # Geprueft wird jede versionierte Quelltext- und Textdatei. Wer ein
    # fremdes Symbol erkennen muss, etwa den Schliessen-Knopf einer
    # Webseite, schreibt es als Unicode-Escape, nicht als Zeichen.
    _funde = bildzeichen_im_quelltext(WURZEL)
    pruefe("H", "Keine Emojis oder Bildzeichen im Quelltext", not _funde,
           "; ".join(_funde[:8]) + (f" und {len(_funde) - 8} weitere" if len(_funde) > 8 else ""))
    _app = (WURZEL / "streamlit_app.py").read_text(encoding="utf-8")
    # Das untere Eingabefeld mit dem geschaetzten RS ist entfallen; Muster
    # und Kaufpunkte stehen beim Nachschlagen mit dem echten RS. Geprueft
    # wird der Code, nicht die Kommentare, die davon erzaehlen.
    pruefe("H", "Webtool ohne Seitensymbol, ohne Einzelabfrage und ohne RS-Schaetzung",
           "page_icon=" not in _app and "tab_einzel" not in _app and "tanh(" not in _app
           and '"RS (geschätzt)"' not in _app)
    pruefe("H", "Webtool: Nachschlagen haengt an der Adresse (?aktie=)",
           'key="aktie"' in _app and 'bind="query-params"' in _app)
    # Angemeldet bleiben liest der Browser selbst und meldet es ueber eine
    # Komponente: Streamlit Community Cloud reicht Cookies nicht an die App
    # durch (gemessen 14.09.2026), st.context.cookies ging nur lokal.
    # Geprueft wird der Code ohne Kommentarzeilen, die davon erzaehlen.
    _app_code = "\n".join(z for z in _app.splitlines() if not z.lstrip().startswith("#"))
    pruefe("H", "Webtool: Angemeldet bleiben liest den Browserspeicher, stellt ihn neu aus und loescht ihn beim Abmelden",
           "zugang.bleiben_pruefen(" in _app_code and "zugang.bleiben_ausstellen(" in _app_code
           and "st.components.v2.component(" in _app_code and '_speicher("setzen"' in _app_code
           and '"loeschen"' in _app_code and "on_click=_abmelden_knopf" in _app_code
           and "st.context.cookies" not in _app_code)
    # Skripte baut die App nicht selbst, sondern ueber zugang.speicher_js und
    # nachschlagen.chart_skript; deren Selbsttests pruefen sie.
    pruefe("H", "Webtool: Skripte kommen aus den geprueften Bausteinen",
           "zugang.speicher_js(" in _app and "nachschlagen.chart_skript(" in _app
           and "function(" not in _app and "document.cookie" not in _app and "localStorage" not in _app)
    # NUTZUNG OHNE SCREENREADER (Mathias, 22.09.2026): So heisst die Tabelle
    # im Reiter Aktueller Scan, und RS Nasdaq steht dort als Zahl; den Umbau
    # prueft der Selbsttest von nachschlagen.rs_spalte_als_zahl.
    pruefe("H", "Aktueller Scan: Tabelle heisst Nutzung ohne Screenreader, RS Nasdaq als Zahl",
           'st.expander("Nutzung ohne Screenreader")' in _app_code
           and "st.dataframe(nachschlagen.rs_spalte_als_zahl(df_scan)" in _app_code
           and "st.dataframe(df_scan" not in _app_code)

    # DER SCANNER (Mathias, 14.09.2026): ein Reiter fuer alle, auch fuer
    # Gaeste, "in jeder Hinsicht und absolut mit Screenreader bedienbar",
    # und "noch keine Vernetzung zu unserem Haupttool".
    ok, zusatz = scanner_reiter_pruefen(WURZEL / "streamlit_app.py")
    pruefe("H", "Scanner-Reiter fuer jede Rolle und vor der Anmeldeschranke", ok, zusatz)
    ok, zusatz = scanner_bedienung_pruefen(WURZEL / "streamlit_app.py")
    pruefe("H", "Scanner-Reiter: keine Ausklapper, Ueberschriften ohne Verweis, deutsche Platzhalter, "
           "verborgene Felder behalten ihren Wert", ok, zusatz)
    _scan_wf = (_wf / "scanner_daten.yml")
    try:
        _d = yaml.safe_load(_scan_wf.read_text(encoding="utf-8"))
        _an = _d.get("on") or _d.get(True) or {}
        _nach = ((_an.get("workflow_run") or {}).get("workflows") or [])
        _scanner_name = (yaml.safe_load((_wf / "scanner.yml").read_text(encoding="utf-8")) or {}).get("name")
        _gruppe = (_d.get("concurrency") or {}).get("group")
        _text = _scan_wf.read_text(encoding="utf-8")
        _oeffentlich = next((s.get("run") or "" for s in _d["jobs"]["bauen"]["steps"]
                             if s.get("name") == "Tabelle als Release-Anhang veroeffentlichen"), "")
        pruefe("H", "Scanner-Daten: startet nach dem Nachtscan, eigene Gruppe, von Hand anstossbar",
               _scanner_name in _nach and "workflow_dispatch" in _an and _gruppe == "scanner-daten",
               f"nach {_nach}, Gruppe {_gruppe}")
        pruefe("H", "Scanner-Daten: sendet nichts, Analystenwerte nie im oeffentlichen Release",
               "NTFY" not in _text and "ntfy" not in _text and bool(_oeffentlich)
               and "scanner_analysten" not in _oeffentlich and "scanner_kurse" not in _oeffentlich)
        # ETAPPE 5 (Gerhard, 13.09.2026, Entscheidung 9): Der Bau holt die
        # juengsten Einfrier-Laeufe aus dem privaten Datenrepo, mit dem
        # Datenrepo-Token und nur in einen Arbeitsordner; der Konsens landet nie
        # im oeffentlichen Release.
        _konsens_schritt = next((s for s in _d["jobs"]["bauen"]["steps"]
                                 if s.get("name") == "Eingefrorenen Konsens holen"), {})
        _bau_schritt = next((s for s in _d["jobs"]["bauen"]["steps"] if s.get("name") == "Scanner-Tabelle bauen"), {})
        pruefe("H", "Scanner-Daten: Einfrier-Laeufe nur aus dem privaten Datenrepo, mit dessen Token, "
                    "nie im oeffentlichen Release",
               "heliot-daten/contents/konsens" in (_konsens_schritt.get("run") or "")
               and "DATEN_TOKEN" in str((_konsens_schritt.get("env") or {}).get("GH_TOKEN"))
               and "steps.token.outputs.da == 'ja'" in str(_konsens_schritt.get("if"))
               and "--konsens-ordner" in (_bau_schritt.get("run") or "") and "konsens" not in _oeffentlich)
        # ETAPPE 6: Die Zuordnungsliste kommt nur aus dem privaten Datenrepo, die
        # Rangliste der Gruppen geht nur dorthin.
        _zuordnung_schritt = next((s for s in _d["jobs"]["bauen"]["steps"]
                                   if s.get("name") == "Branchen-Zuordnung holen"), {})
        _privat_schritt = next((s.get("run") or "" for s in _d["jobs"]["bauen"]["steps"]
                                if s.get("name") == "Analystenwerte und Kursarchiv ins private Datenrepo"), "")
        pruefe("H", "Scanner-Daten: Zuordnungsliste nur aus dem privaten Datenrepo, Gruppen-Rangliste nie im "
                    "oeffentlichen Release",
               "heliot-daten/contents/zuordnung" in (_zuordnung_schritt.get("run") or "")
               and "DATEN_TOKEN" in str((_zuordnung_schritt.get("env") or {}).get("GH_TOKEN"))
               and "steps.token.outputs.da == 'ja'" in str(_zuordnung_schritt.get("if"))
               and "--zuordnung" in (_bau_schritt.get("run") or "")
               and "scanner_gruppen" not in _oeffentlich and "zuordnung" not in _oeffentlich
               and "scanner_gruppen.json" in _privat_schritt)
        # Beide Releases sind Vorabversionen und nie "latest": ibd_ratings.py
        # liest vom latest-Release des oeffentlichen Repos, und im Datenrepo
        # verdraengte das Scanner-Release beim ersten Bau am 14.09.2026 den
        # EODHD-Vollabzug von diesem Platz.
        _anlegen = [z for z in _text.splitlines() if "gh release create scanner-daten" in z]
        pruefe("H", "Scanner-Daten: beide Releases als Vorabversion, nie latest",
               len(_anlegen) == 2 and all("--prerelease" in z and "--latest=false" in z for z in _anlegen),
               f"{len(_anlegen)} Anlage-Zeilen")
    except Exception as e:
        pruefe("H", "Scanner-Daten: Ablauf lesbar", False, f"{type(e).__name__}: {e}")
    # ETAPPE 6 (Gerhard, 13.09.2026, Entscheidung 10): Die Zuordnungsliste
    # entsteht nur von Hand aus dem schon abgelegten Vollabzug, ohne
    # EODHD-Schluessel und ohne Abruf, und nur im privaten Datenrepo.
    try:
        _zw_text = (_wf / "zuordnung.yml").read_text(encoding="utf-8")
        _zw = yaml.safe_load(_zw_text)
        _zw_an = _zw.get("on") or _zw.get(True) or {}
        pruefe("H", "Branchen-Zuordnung: nur von Hand, nur mit dem Datenrepo-Token, ohne EODHD-Schluessel, Ablage im "
                    "privaten Datenrepo",
               list(_zw_an.keys()) == ["workflow_dispatch"] and "EODHD_API_KEY" not in _zw_text
               and "secrets.DATEN_TOKEN" in _zw_text and "repository: mat-schmuck/heliot-daten" in _zw_text
               and "git add -A -- zuordnung" in _zw_text and "gh release upload" not in _zw_text,
               f"Ausloeser {list(_zw_an.keys())}")
    except Exception as e:
        pruefe("H", "Branchen-Zuordnung: Ablauf lesbar", False, f"{type(e).__name__}: {e}")
    # S11 (Gerhard, 20.09.2026): Der Katalog der EODHD-Daten entsteht aus dem
    # schon abgelegten Vollabzug, ohne EODHD-Schluessel und ohne Abruf, ohne
    # Artefakt, und liegt nur im privaten Datenrepo, neben dem Register.
    try:
        _ka_text = (_wf / "eodhd_katalog.yml").read_text(encoding="utf-8")
        _ka = yaml.safe_load(_ka_text)
        _ka_an = _ka.get("on") or _ka.get(True) or {}
        _ka_quelle = ((_ka_an.get("workflow_run") or {}).get("workflows") or [None])[0]
        _ka_name = yaml.safe_load((_wf / "eodhd_voll.yml").read_text(encoding="utf-8")).get("name")
        pruefe("H", "EODHD-Katalog: nach dem Vollabzug oder von Hand, nur mit dem Datenrepo-Token, ohne "
                    "EODHD-Schluessel und ohne Artefakt, Ablage im privaten Datenrepo",
               sorted(_ka_an.keys()) == ["workflow_dispatch", "workflow_run"] and _ka_quelle == _ka_name
               and "EODHD_API_KEY" not in _ka_text and "upload-artifact" not in _ka_text
               and "secrets.DATEN_TOKEN" in _ka_text and "repository: mat-schmuck/heliot-daten" in _ka_text
               and "git add -A -- eodhd_voll/katalog.json eodhd_voll/katalog.md" in _ka_text
               and "gh release upload" not in _ka_text,
               f"Ausloeser {sorted(_ka_an.keys())}, nach {_ka_quelle}")
    except Exception as e:
        pruefe("H", "EODHD-Katalog: Ablauf lesbar", False, f"{type(e).__name__}: {e}")
    _vernetzt = []
    for _modul in ("scanner_daten.py", "scanner_ansicht.py", "scanner_noetig.py", "kennzahlen_konsens.py",
                   "kennzahlen_short.py", "kennzahlen_gruppen.py", "zuordnung_bauen.py", "chartmuster.py",
                   "eodhd_katalog.py"):
        _code = "\n".join(z for z in (WURZEL / _modul).read_text(encoding="utf-8").splitlines()
                          if not z.lstrip().startswith("#"))
        for _wort in ("NTFY_" + "TOPIC", "ntfy." + "sh", "requests." + "post(", "traderfox_" + "alarm",
                      "breakout_" + "watcher", "melde_" + "gedaechtnis"):
            if _wort in _code:
                _vernetzt.append(f"{_modul}: {_wort}")
    pruefe("H", "Scanner ohne Vernetzung zum Haupttool (kein Sendecode, keine Alarmdateien)",
           not _vernetzt, ", ".join(_vernetzt))
    _req = (WURZEL / "requirements.txt").read_text(encoding="utf-8-sig")
    pruefe("H", "App-Abhaengigkeiten fuer den Scanner (Parquet, OpenDocument)",
           "pyarrow" in _req and "odfpy" in _req)
    _ign = (WURZEL / ".gitignore").read_text(encoding="utf-8")
    pruefe("H", "Scanner-Tabellen nie im Repo, Analystenwerte nur mit Token aus dem privaten Datenrepo",
           "scanner_analysten.parquet" in _ign and "scanner_tabelle.parquet" in _ign and "scanner_gruppen.json" in _ign
           and '_secret("DATEN_TOKEN")' in _app_code and "heliot-daten" in _app_code)
    # S4 (Gerhard, 20.09.2026): Gaeste sehen nur den Scanner und nichts aus dem
    # privaten Datenrepo.
    ok, zusatz = gast_abschottung(WURZEL / "streamlit_app.py")
    pruefe("H", "Gastzugang abgeschottet: nur der Scanner, kein Nachschlagen, nichts aus dem Datenrepo", ok, zusatz)


def bildzeichen_im_quelltext(wurzel) -> list:
    """'datei:zeile U+XXXX' fuer jedes Bildzeichen in versionierten Quelltext-
    und Textdateien. Die Bereiche stehen in nachschlagen.BILDZEICHEN_BEREICHE.
    Datendateien wie rs_universum.json tragen fremde Firmennamen und bleiben
    aussen vor. Ohne git (Pruefkopie) werden alle Dateien des Ordners gelesen."""
    import nachschlagen
    wurzel = pathlib.Path(wurzel)
    endungen = {".py", ".yml", ".yaml", ".md", ".txt", ".toml", ".cfg", ".ini", ".html", ".js", ".css"}
    try:
        namen = subprocess.run(["git", "ls-files"], cwd=wurzel, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=60).stdout.split("\n")
    except Exception:  # noqa
        namen = []
    if not any(namen):
        namen = [p.relative_to(wurzel).as_posix() for p in wurzel.rglob("*")
                 if p.is_file() and not ({".git", "__pycache__", ".cache"} & set(p.parts))]
    funde = []
    for name in namen:
        p = wurzel / name
        if not name or p.suffix.lower() not in endungen or not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for nr, zeile in enumerate(text.split("\n"), 1):
            for z in nachschlagen.bildzeichen_in(zeile):
                funde.append(f"{name}:{nr} U+{ord(z):04X}")
    return funde


def config_ohne_leser(wurzel) -> list:
    """Bloecke und Schluessel von config.CFG, die kein Modul ausser config.py
    und dieser Pruefung ueber ["name"] oder .get("name") anspricht.

    Etappe 0 (Gerhard, 13.09.2026): Am 13.09.2026 waren es 35, darunter
    ganze Bloecke (bottom_fishing, radar, datenquellen, ntfy, staffelung).
    Die Pruefung liest den Quelltext; ein Schluessel, der nur ueber eine
    Variable angesprochen wird, faellt hier auf und muss dann beim Namen
    gelesen werden."""
    import re as _re
    from config import CFG
    texte = [p.read_text(encoding="utf-8", errors="replace")
             for p in sorted(pathlib.Path(wurzel).glob("*.py"))
             if p.name not in ("config.py", "gesamtpruefung.py")]

    def gelesen(name):
        k = _re.escape(name)
        muster = _re.compile(r'\[\s*["\']' + k + r'["\']\s*\]|\.get\(\s*["\']' + k + r'["\']')
        return any(muster.search(t) for t in texte)
    ohne = []
    for block, inhalt in CFG.items():
        if not gelesen(block):
            ohne.append(block)
        if isinstance(inhalt, dict):
            ohne += [f"{block}.{k}" for k in inhalt if not gelesen(k)]
    return ohne


def anmeldeschranke(pfad) -> tuple:
    """Gaeste duerfen in der Heliot-App nichts veraendern (Mathias,
    13.09.2026). Geprueft wird am Quelltext, auf oberster Ebene:
      * Im Zweig fuer Gaeste (if rolle == "gast") werden weder tab_upload
        noch tab_gast gebaut.
      * Vor dem ersten "with tab_upload:" steht "if tab_upload is None:" mit
        st.stop(), damit der Lauf fuer Gaeste dort endet.
      * Die Seite fuer Gastpasswoerter entsteht nur unter
        "if tab_gast is not None:", nie auf oberster Ebene.
      * Der Reiter Ablaeufe (S8, 21.09.2026) entsteht nur im Zweig
        "rolle == 'voll'" und nur unter "if tab_ablaeufe is not None:"
        hinter der Schranke: Seine Knoepfe stossen Ablaeufe an.
    Liefert (ok, Befund)."""
    import ast as _ast
    try:
        baum = _ast.parse(open(pfad, encoding="utf-8").read())
    except Exception as e:
        return False, f"nicht lesbar: {type(e).__name__}: {e}"
    maengel = []
    schranke = upload = gastseite = ablaufseite = None
    gastzweig = False

    def zugewiesen(koerper):
        return {n.id for s in koerper for n in _ast.walk(s)
                if isinstance(n, _ast.Name) and isinstance(n.ctx, _ast.Store)}

    for i, knoten in enumerate(baum.body):
        if isinstance(knoten, _ast.If):
            test = _ast.unparse(knoten.test)
            if test in ("rolle == 'gast'", 'rolle == "gast"'):
                gastzweig = True
                for name in ("tab_upload", "tab_gast", "tab_ablaeufe"):
                    if name in zugewiesen(knoten.body):
                        maengel.append(f"der Zweig fuer Gaeste baut {name}")
                # Die weiteren Zweige: nur "rolle == 'voll'" darf tab_ablaeufe bauen
                teil = knoten.orelse
                while teil:
                    if len(teil) == 1 and isinstance(teil[0], _ast.If):
                        test_t = _ast.unparse(teil[0].test)
                        if ("tab_ablaeufe" in zugewiesen(teil[0].body)
                                and test_t not in ("rolle == 'voll'", 'rolle == "voll"')):
                            maengel.append(f"der Zweig '{test_t}' baut tab_ablaeufe")
                        teil = teil[0].orelse
                    else:
                        if "tab_ablaeufe" in zugewiesen(teil):
                            maengel.append("der letzte Zweig baut tab_ablaeufe")
                        teil = None
            if (test == "tab_upload is None" and schranke is None
                    and "st.stop()" in _ast.unparse(knoten)):
                schranke = i
            if test == "tab_gast is not None" and gastseite is None:
                gastseite = i
            if test == "tab_ablaeufe is not None" and ablaufseite is None:
                ablaufseite = i
        if isinstance(knoten, _ast.With):
            ziel = _ast.unparse(knoten.items[0].context_expr)
            if ziel == "tab_upload" and upload is None:
                upload = i
            if ziel == "tab_gast":
                maengel.append("die Gastseite steht auf oberster Ebene")
            if ziel == "tab_ablaeufe":
                maengel.append("der Reiter Ablaeufe steht auf oberster Ebene")
    if ablaufseite is not None and schranke is not None and ablaufseite < schranke:
        maengel.append("der Reiter Ablaeufe steht vor der Schranke")
    if not gastzweig:
        maengel.append("kein Zweig fuer Gaeste gefunden")
    if schranke is None:
        maengel.append("keine Schranke 'if tab_upload is None: st.stop()'")
    if upload is None:
        maengel.append("kein 'with tab_upload:' gefunden")
    if schranke is not None and upload is not None and schranke > upload:
        maengel.append("die Schranke steht erst nach der Wochenliste")
    if gastseite is None:
        maengel.append("keine Gastseite unter 'if tab_gast is not None:'")
    elif schranke is not None and gastseite < schranke:
        maengel.append("die Gastseite steht vor der Schranke")
    if maengel:
        return False, "; ".join(maengel)
    return True, "Schranke vor der Wochenliste, Gastseite dahinter"


def scanner_reiter_pruefen(pfad) -> tuple:
    """Der Scanner steht allen offen, auch Gaesten (Mathias, 14.09.2026).
    Geprueft wird am Quelltext, auf oberster Ebene:
      * Jeder Zweig, der die Registerkarten baut (gast, voll, sonst), legt
        tab_scanner an.
      * "with tab_scanner:" steht vor der Schranke "if tab_upload is None:",
        sonst endete der Lauf fuer Gaeste, bevor der Scanner gezeichnet ist.
    Liefert (ok, Befund)."""
    import ast as _ast
    try:
        baum = _ast.parse(open(pfad, encoding="utf-8").read())
    except Exception as e:
        return False, f"nicht lesbar: {type(e).__name__}: {e}"
    maengel = []
    zweige = 0
    reiter = schranke = None
    for i, knoten in enumerate(baum.body):
        if isinstance(knoten, _ast.If) and _ast.unparse(knoten.test) in ("rolle == 'gast'", 'rolle == "gast"'):
            teil = knoten
            while teil is not None:
                zweige += 1
                namen = {n.id for s in teil.body for n in _ast.walk(s)
                         if isinstance(n, _ast.Name) and isinstance(n.ctx, _ast.Store)}
                if "tab_scanner" not in namen:
                    maengel.append(f"der Zweig '{_ast.unparse(teil.test)}' baut keinen Scanner-Reiter"
                                   if isinstance(teil, _ast.If) else "der letzte Zweig baut keinen Scanner-Reiter")
                if isinstance(teil, _ast.If) and len(teil.orelse) == 1 and isinstance(teil.orelse[0], _ast.If):
                    teil = teil.orelse[0]
                elif isinstance(teil, _ast.If) and teil.orelse:
                    teil = _ast.If(test=_ast.Constant(value=True), body=teil.orelse, orelse=[])
                else:
                    teil = None
        if isinstance(knoten, _ast.If) and _ast.unparse(knoten.test) == "tab_upload is None" and schranke is None:
            schranke = i
        if isinstance(knoten, _ast.With) and _ast.unparse(knoten.items[0].context_expr) == "tab_scanner" and reiter is None:
            reiter = i
    if zweige < 3:
        maengel.append(f"nur {zweige} Zweige mit Registerkarten gefunden")
    if reiter is None:
        maengel.append("kein 'with tab_scanner:' auf oberster Ebene")
    if schranke is None:
        maengel.append("keine Schranke 'if tab_upload is None:'")
    if reiter is not None and schranke is not None and reiter > schranke:
        maengel.append("der Scanner steht erst hinter der Anmeldeschranke")
    if maengel:
        return False, "; ".join(maengel)
    return True, f"{zweige} Zweige mit Scanner-Reiter, Scanner vor der Schranke"


def gast_abschottung(pfad) -> tuple:
    """S4 (Gerhard, 20.09.2026): "Der Gastzugang darf keinen Zugriff auf die
    GitHub-Anbindung in Streamlit bekommen. Ein Gast soll wirklich nur den
    Scanner sehen und sonst nichts von dem, was dahinter laeuft."
    Geprueft wird am Quelltext:
      * Der Zweig fuer Gaeste baut keine Registerkarten, setzt tab_liste,
        tab_scan und tab_info auf None und legt tab_scanner an.
      * "if tab_liste is None:" mit st.stop() steht auf oberster Ebene hinter
        "with tab_scanner:" und vor Liste pruefen, Aktueller Scan und Regelwerk.
      * Das Feld des Nachschlagens (key "aktie") entsteht nur unter
        "if rolle != 'gast':".
      * _daten_token gibt den Token nur bei rolle "voll" heraus, und
        lade_scanner_analysten prueft die Rolle, bevor es den fuer alle
        Besucher geteilten Zwischenspeicher fragt.
      * Vorlagen (S1) und Uebergabe (S2) stehen nur unter
        "if rolle == 'voll':", und wochenliste_einspielen rufen genau die
        Uebergabe, die Seite zum Hochladen und das Ein- und Austragen
        einzelner Aktien (S7, _einzel_setzen).
      * S7 (21.09.2026): Die Einzelaktien lesen und schreiben nur Funktionen,
        die ausserhalb ihrer selbst nur unter "if rolle == 'voll':" stehen.
    Liefert (ok, Befund)."""
    import ast as _ast
    try:
        quelle = open(pfad, encoding="utf-8").read()
        baum = _ast.parse(quelle)
    except Exception as e:
        return False, f"nicht lesbar: {type(e).__name__}: {e}"
    maengel = []
    gast_zweig = None
    stelle = {}
    for i, knoten in enumerate(baum.body):
        if isinstance(knoten, _ast.If):
            test = _ast.unparse(knoten.test)
            if test in ("rolle == 'gast'", 'rolle == "gast"') and gast_zweig is None:
                gast_zweig = knoten
            if test == "tab_liste is None" and "st.stop()" in _ast.unparse(knoten):
                stelle.setdefault("schranke", i)
        if isinstance(knoten, _ast.With):
            ziel = _ast.unparse(knoten.items[0].context_expr)
            if ziel in ("tab_scanner", "tab_liste", "tab_scan", "tab_info"):
                stelle.setdefault(ziel, i)
    if gast_zweig is None:
        maengel.append("kein Zweig fuer Gaeste")
    else:
        rumpf = "\n".join(_ast.unparse(s) for s in gast_zweig.body)
        if "st.tabs(" in rumpf:
            maengel.append("der Zweig fuer Gaeste baut Registerkarten")
        none_gesetzt = set()
        for s in gast_zweig.body:
            if isinstance(s, _ast.Assign) and isinstance(s.value, _ast.Constant) and s.value.value is None:
                none_gesetzt |= {t.id for t in s.targets if isinstance(t, _ast.Name)}
        for name in ("tab_liste", "tab_scan", "tab_info"):
            if name not in none_gesetzt:
                maengel.append(f"{name} ist fuer Gaeste nicht None")
        if "tab_scanner =" not in rumpf:
            maengel.append("der Zweig fuer Gaeste legt tab_scanner nicht an")
    if "schranke" not in stelle:
        maengel.append("keine Schranke 'if tab_liste is None: st.stop()'")
    else:
        if stelle.get("tab_scanner", 10 ** 9) > stelle["schranke"]:
            maengel.append("der Scanner steht hinter der Gast-Schranke")
        for ziel in ("tab_liste", "tab_scan", "tab_info"):
            if stelle.get(ziel, -1) < stelle["schranke"]:
                maengel.append(f"'with {ziel}:' steht vor der Gast-Schranke")
    # Das Nachschlagen-Feld nur unter "if rolle != 'gast':"
    feld_geschuetzt = False
    for knoten in baum.body:
        if isinstance(knoten, _ast.If) and _ast.unparse(knoten.test) in ("rolle != 'gast'", 'rolle != "gast"'):
            if "key='aktie'" in _ast.unparse(_ast.Module(body=knoten.body, type_ignores=[])):
                feld_geschuetzt = True
    feld_oben = [k for k in baum.body if not isinstance(k, _ast.If) and "key='aktie'" in _ast.unparse(k)]
    if not feld_geschuetzt or feld_oben:
        maengel.append("das Nachschlagen-Feld steht nicht nur unter 'if rolle != \"gast\":'")
    funktionen = {k.name: _ast.unparse(k) for k in baum.body if isinstance(k, _ast.FunctionDef)}
    dt = funktionen.get("_daten_token", "")
    if not dt or "'voll'" not in dt or "DATEN_TOKEN" not in dt:
        maengel.append("_daten_token prueft die Rolle nicht oder liest DATEN_TOKEN nicht")
    lsa = funktionen.get("lade_scanner_analysten", "")
    if not lsa or "'voll'" not in lsa or lsa.find("'voll'") > lsa.find("_scanner_analysten_holen"):
        maengel.append("lade_scanner_analysten prueft die Rolle nicht vor dem Zwischenspeicher")
    # Die Vorlagen des Scanners (S1, 21.09.2026) liegen im privaten Datenrepo:
    # In scanner_reiter steht alles dazu nur unter "if rolle == 'voll':".
    vorlagen_namen = {"_sc_vorlagen_holen", "_sc_vorlage_laden", "_sc_vorlage_speichern", "_sc_vorlage_loeschen"}
    reiter_f = next((k for k in baum.body if isinstance(k, _ast.FunctionDef) and k.name == "scanner_reiter"), None)

    def offen_verwendet(knoten, geschuetzt, namen=vorlagen_namen):
        if isinstance(knoten, _ast.If) and _ast.unparse(knoten.test) in ("rolle == 'voll'", 'rolle == "voll"'):
            for s in knoten.body:
                yield from offen_verwendet(s, True, namen)
            for s in knoten.orelse:
                yield from offen_verwendet(s, geschuetzt, namen)
            return
        if isinstance(knoten, _ast.Name) and knoten.id in namen and not geschuetzt:
            yield f"{knoten.id} in Zeile {knoten.lineno}"
        for kind in _ast.iter_child_nodes(knoten):
            yield from offen_verwendet(kind, geschuetzt, namen)

    if reiter_f is None:
        maengel.append("Funktion scanner_reiter fehlt")
    else:
        offen = [x for s in reiter_f.body for x in offen_verwendet(s, False)]
        if offen:
            maengel.append("Vorlagen ausserhalb von 'if rolle == \"voll\"': " + ", ".join(offen[:4]))
        if not any(True for s in reiter_f.body for k in _ast.walk(s)
                   if isinstance(k, _ast.Name) and k.id == "_sc_vorlagen_holen"):
            maengel.append("scanner_reiter liest die Vorlagen nicht")
    # Die Uebergabe (S2, 21.09.2026) ersetzt eine Wochen- oder Darvas-Liste: In
    # _sc_ergebnis_zeigen steht sie nur unter "if rolle == 'voll':", und
    # wochenliste_einspielen rufen nur die Uebergabe und die Seite zum Hochladen.
    zeigen_f = next((k for k in baum.body if isinstance(k, _ast.FunctionDef) and k.name == "_sc_ergebnis_zeigen"),
                    None)
    if zeigen_f is None:
        maengel.append("Funktion _sc_ergebnis_zeigen fehlt")
    else:
        offen = [x for s in zeigen_f.body for x in offen_verwendet(s, False, {"_sc_uebergabe"})]
        if offen:
            maengel.append("Uebergabe ausserhalb von 'if rolle == \"voll\"': " + ", ".join(offen[:4]))
        if not any(True for s in zeigen_f.body for k in _ast.walk(s)
                   if isinstance(k, _ast.Name) and k.id == "_sc_uebergabe"):
            maengel.append("_sc_ergebnis_zeigen bietet die Uebergabe nicht an")
    einspieler = set()
    for k in baum.body:
        for n in _ast.walk(k):
            if isinstance(n, _ast.Call) and getattr(n.func, "id", "") == "wochenliste_einspielen":
                if isinstance(k, _ast.FunctionDef):
                    einspieler.add(k.name)
                elif isinstance(k, _ast.With):
                    einspieler.add("with " + _ast.unparse(k.items[0].context_expr))
                else:
                    einspieler.add(f"Zeile {n.lineno}")
    if einspieler != {"_sc_uebergabe_ausfuehren", "with tab_upload", "_einzel_setzen"}:
        maengel.append("wochenliste_einspielen wird nicht genau von Upload, Uebergabe und Einzelaktien gerufen: "
                       + ", ".join(sorted(einspieler)))
    # Einzelaktien (S7, 21.09.2026): Lesen und Schreiben nur im vollen Zugang.
    # Ausserhalb ihrer eigenen Definitionen stehen die Funktionen nur unter
    # "if rolle == 'voll':", und die beiden Anzeigen werden wirklich gerufen.
    einzel_namen = {"einzel_bereich", "einzel_liste_zeigen", "_einzel_setzen", "_einzel_holen", "_einzel_roh"}
    einzel_da = {k.name for k in baum.body if isinstance(k, _ast.FunctionDef) and k.name in einzel_namen}
    if einzel_da != einzel_namen:
        maengel.append("Einzelaktien: es fehlen " + ", ".join(sorted(einzel_namen - einzel_da)))
    ausserhalb = [s for s in baum.body if not (isinstance(s, _ast.FunctionDef) and s.name in einzel_namen)]
    offen = [x for s in ausserhalb for x in offen_verwendet(s, False, einzel_namen)]
    if offen:
        maengel.append("Einzelaktien ausserhalb von 'if rolle == \"voll\"': " + ", ".join(offen[:4]))
    for name in ("einzel_bereich", "einzel_liste_zeigen"):
        if not any(isinstance(n, _ast.Name) and n.id == name for s in ausserhalb for n in _ast.walk(s)):
            maengel.append(f"Einzelaktien: {name} wird nirgends gerufen")
    if maengel:
        return False, "; ".join(maengel)
    return True, ("Gast: nur Scanner ohne Registerkarten, Schranke dahinter, Nachschlagen, Datenrepo, Uebergabe und "
                  "Einzelaktien gesperrt")


def scanner_bedienung_pruefen(pfad) -> tuple:
    """Screenreader-Befunde vom 14.09.2026 als Regel fuer die Funktion
    scanner_reiter in streamlit_app.py:
      * kein st.expander: Streamlit schreibt vor die Beschriftung das
        Symbolwort keyboard_arrow_right, und ein Screenreader liest es vor;
      * jede Ueberschrift aus st.markdown mit anchors=False, sonst haengt
        Streamlit einen Verweis "Link to heading" an;
      * jede Ausklappliste mit deutschem Platzhalter statt "Choose an option";
      * jedes Bedienfeld, das nur unter einer Bedingung gezeichnet wird, mit
        persist_state, sonst verliert es seinen Wert, sobald es verborgen ist,
        und ein angehaktes Merkmal filtert still nicht mehr.
    Liefert (ok, Befund)."""
    import ast as _ast
    try:
        baum = _ast.parse(open(pfad, encoding="utf-8").read())
    except Exception as e:
        return False, f"nicht lesbar: {type(e).__name__}: {e}"
    funktion = next((k for k in _ast.walk(baum) if isinstance(k, _ast.FunctionDef) and k.name == "scanner_reiter"), None)
    if funktion is None:
        return False, "Funktion scanner_reiter fehlt"
    maengel = []
    felder = ("checkbox", "text_input", "selectbox", "radio", "number_input", "multiselect", "toggle", "slider")

    def st_aufruf(knoten):
        f = knoten.func
        return (f.attr if isinstance(f, _ast.Attribute) and isinstance(f.value, _ast.Name)
                and f.value.id == "st" else None)

    def schluessel(knoten, name):
        return next((k.value for k in knoten.keywords if k.arg == name), None)

    def besuchen(knoten, bedingt):
        if isinstance(knoten, _ast.Call):
            art = st_aufruf(knoten)
            zeile = knoten.lineno
            if art == "expander":
                maengel.append(f"Zeile {zeile}: st.expander")
            if art == "markdown" and knoten.args:
                erster = knoten.args[0]
                text = (erster.value if isinstance(erster, _ast.Constant) and isinstance(erster.value, str)
                        else _ast.unparse(erster))
                if text.lstrip("f\"'").startswith("#"):
                    anker = schluessel(knoten, "anchors")
                    if not (isinstance(anker, _ast.Constant) and anker.value is False):
                        maengel.append(f"Zeile {zeile}: Ueberschrift ohne anchors=False")
            if art == "selectbox" and schluessel(knoten, "placeholder") is None:
                maengel.append(f"Zeile {zeile}: Ausklappliste ohne Platzhalter")
            if art in felder and bedingt and schluessel(knoten, "persist_state") is None:
                maengel.append(f"Zeile {zeile}: st.{art} unter einer Bedingung ohne persist_state")
        if isinstance(knoten, _ast.If):
            besuchen(knoten.test, bedingt)
            for s in knoten.body + knoten.orelse:
                besuchen(s, True)
            return
        for kind in _ast.iter_child_nodes(knoten):
            besuchen(kind, bedingt)

    for s in funktion.body:
        besuchen(s, False)
    if maengel:
        return False, "; ".join(maengel[:8]) + (f" und {len(maengel) - 8} weitere" if len(maengel) > 8 else "")
    return True, "geprueft an der Funktion scanner_reiter"


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
