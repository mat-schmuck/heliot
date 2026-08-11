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
import pathlib
import subprocess
import sys
import warnings
from datetime import datetime, timedelta, timezone

warnings.filterwarnings("ignore")

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
                    "red_to_green", "scan_noetig", "waechter_noetig"]
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
    import pandas as pd
    import pattern_scanner as ps
    import cup_handle_v2
    import shakeout

    liste = pd.read_csv(WURZEL / "finviz_3.csv")["Ticker"].astype(str).tolist()
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
    liste = set(pd.read_csv(WURZEL / "finviz_3.csv")["Ticker"]
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
