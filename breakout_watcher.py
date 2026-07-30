#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BREAKOUT-WÄCHTER
================
Prüft die Kaufpunkte aus kaufpunkte.xlsx gegen die aktuellen Kurse und meldet
per ntfy-Push, sobald ein Kaufpunkt gerissen wurde — MIT Volumen-Bestätigung,
so wie das Regelwerk es verlangt.

Das schließt die Lücke des Scanners: der liefert die Trigger-Level, dieser
Wächter prüft, ob ein Ausbruch wirklich stattfindet und ob er gültig ist.

Volumen: GERECHNET WIRD AUSSCHLIESSLICH IN volumen.py (Gerhard,
28.07.2026) — IBD "Volume % Change" mit Hochrechnung über die
Fünf-Minuten-Referenzkurve, Maßstab ist der 50-Tage-Schnitt. Die
Schwellen je Strategie (als Prozent gegenüber dem Üblichen FÜR DIESE
UHRZEIT):
  Darvas Box          0 % (Volumen über dem Schnitt)
  VCP                +40 % (Minervini: 40 bis 50 % über Ø)
  Cup & Handle        0 % (O'Neil: Volumen-Bestätigung)
  Rectangle Top       0 % UND Kurs > SMA21 (Bulkowskis bestes Setup)
  High & Tight Flag   0 %
  Fallback-Level      0 %
  Gap and Go       +400 %, vor 10:00 New Yorker Zeit +200 %

Aufruf:
  export TWELVE_DATA_API_KEY="dein_key"
  export NTFY_TOPIC="dein-topic"
  python breakout_watcher.py kaufpunkte.xlsx
  python breakout_watcher.py kaufpunkte.xlsx --alle       # auch Fallback-Level überwachen
  python breakout_watcher.py kaufpunkte.xlsx --dry-run    # nur anzeigen, kein Push

Zustandsdatei:
  ./watcher_state.json merkt sich, was schon gemeldet wurde — du bekommst
  jeden Treffer genau EINMAL pro Handelstag, nicht alle 15 Minuten aufs Neue.
"""

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

try:
    import requests
except ImportError:
    sys.exit("Bitte installieren: pip install requests pandas openpyxl")

import ntfy_verlauf   # merkt sich jede verschickte Meldung fuer den Freitags-Putz
import volumen        # IBD Volume % Change — die EINZIGE Volumenrechnung
from config import CFG, pruefe_config
from kurs_cache import KursCache, Kurswert
from yahoo_ws import YahooWebSocket

pruefe_config()       # faengt widerspruechliche Schwellwerte sofort ab

# Gemeinsamer Kursspeicher (Gerhards Aufraeumschritt 3). Er haelt fest,
# WOHER jeder Kurs stammt und WANN er geholt wurde — Grundlage fuer die
# Erkennung haengender Quellen. Yahoos Live-Strom schreibt seine
# Meldungen in denselben Speicher, und fuer ihn gilt die strenge
# Schwelle: Bleibt eine Aktie zu lange still, zaehlt wieder der Wert aus
# den Tagesdaten statt eines eingefrorenen Kurses.
KURSE = KursCache(
    ttl_sekunden=60,
    stale_max_sekunden=CFG["betrieb"]["stale_max_sekunden"],
    stale_pro_quelle=CFG["betrieb"]["stale_pro_quelle"],
)


def ws_kurse_einblenden(quotes: dict, ws=None) -> tuple:
    """Legt die LIVE-Werte aus Yahoos Strom ueber die Tagesdaten.
    Liefert (ersetzte Kurse, ersetzte Volumina).

    KURS UND TAGESVOLUMEN, aber sonst nichts. Der Unterschied zum
    frueheren Finnhub-Strom ist wesentlich und nachgemessen: Finnhub
    schickte die Stueckzahl EINES Geschaefts — als Tagesvolumen gelesen
    waere die um Groessenordnungen falsch gewesen, deshalb stand dort
    bewusst 0,0. Yahoo schickt den aufgelaufenen TAGESUMSATZ, und der
    stimmt: Gegenprobe am 28.07.2026 ueber 60 Aktien, mittlere
    Abweichung zur Tageskerze 0,00 %, groesste 0,05 % (volumenprobe.py).

    Damit wird die Volumenbestaetigung live statt im Abruftakt — genau
    das, was bei Ausbruechen zaehlt.

    Durchschnitte, Vortagesschluss und die Tageswerte fuer Gap and Go
    bleiben aus den Tagesdaten; davon weiss eine Kursmeldung nichts.

    'Frisch' entscheidet der Kursspeicher mit der Schwelle FUER DIESE
    QUELLE. Haengt die Leitung, faellt der Wert automatisch auf die
    Tagesdaten zurueck, statt einzufrieren."""
    kurse = volumina = spannen = 0
    for t, q in quotes.items():
        gross = t.upper()
        wert = KURSE._store.get(gross)
        if (wert is None or wert.quelle != "yahoo_ws"
                or not wert.preis or KURSE.ist_stale(gross)):
            continue
        q["close"] = float(wert.preis)
        q["kursquelle"] = "yahoo_ws"
        kurse += 1
        # Das Tagesvolumen nur ANHEBEN, nie senken: Beide Quellen zaehlen
        # denselben Tag, und der hoehere Wert ist der juengere Stand. Ein
        # Ruecksetzer waere immer ein Fehler.
        if wert.volumen and wert.volumen > (q.get("volume") or 0):
            q["volume"] = float(wert.volumen)
            volumina += 1
        # TAGESSPANNE: immer der AEUSSERE Wert aus Tageskerze und Strom.
        # Hoch kann nur steigen, Tief nur fallen — die Vereinigung beider
        # Quellen ist deshalb immer mindestens so genau wie jede allein,
        # nie schlechter. Der Strom ist sekundenfrisch, die Tageskerze
        # holt nach, was zwischen zwei Meldungen durchgerutscht ist.
        if ws is not None:
            hoch, tief = ws.spanne(gross)
            geweitet = False
            if hoch is not None and (q.get("high") is None
                                     or hoch > q["high"]):
                q["high"] = float(hoch)
                geweitet = True
            if tief is not None and (q.get("low") is None
                                     or tief < q["low"]):
                q["low"] = float(tief)
                geweitet = True
            if geweitet:
                spannen += 1
    return kurse, volumina, spannen


def merke_kurse(quotes: dict, quelle: str):
    """Legt die Kurse einer Runde im gemeinsamen Speicher ab.

    ACHTUNG, hier lag ein Fehler, den erst der erste Lauf mit echtem
    WebSocket zeigte (28.07.2026): Der Yahoo-Sammelabruf lief VOR der
    Einblendung der Tickkurse und ueberschrieb dabei jeden Eintrag. Wenn
    danach die Einblendung suchte, fand sie nur noch Yahoo-Werte — es
    wurde KEIN einziger Tickkurs uebernommen, obwohl die Verbindung
    stand und Ticks flossen. Im Protokoll fiel es nur dadurch auf, dass
    die Zeile 'tickfrisch vom WebSocket' fehlte.

    Die Regel lautet deshalb: Ein rund 15 Minuten verzoegerter
    Yahoo-Kurs darf einen sekundenfrischen Tick NICHT verdraengen. Ist
    der Tick alt genug, um als haengend zu gelten, darf Yahoo
    uebernehmen — dann ist der verzoegerte Kurs der bessere."""
    jetzt = time.time()
    for t, q in quotes.items():
        gross = t.upper()
        if quelle != "yahoo_ws":
            vorhanden = KURSE._store.get(gross)
            if (vorhanden is not None and vorhanden.quelle == "yahoo_ws"
                    and not KURSE.ist_stale(gross)):
                continue      # frische Meldung schlaegt verzoegerten Tageskurs
        try:
            KURSE.setze(Kurswert(
                ticker=gross, preis=float(q.get("close") or 0.0),
                zeit=jetzt, volumen=float(q.get("volume") or 0.0),
                quelle=quelle, vortagesschluss=q.get("prev_close")))
        except Exception:
            continue

QUOTE_URL = "https://api.twelvedata.com/quote"
STATE_FILE = Path("watcher_state.json")

# Volumen-Faktor je Strategie (Vielfaches des Ø20-Tage-Volumens)
# Alle Schwellwerte kommen seit 28.07.2026 aus config.py — der EINEN
# Quelle der Wahrheit (Gerhards Aufraeumschritt 2). Vorher standen
# dieselben Zahlen im Scanner UND im Waechter; liefen sie auseinander,
# rechneten zwei Module unbemerkt verschieden.
_VOL = CFG["volumen"]
VOL_FAKTOR = {
    "Darvas Box": _VOL["breakout_faktor"],
    "VCP": _VOL["breakout_faktor_vcp"],
    "Cup & Handle": _VOL["breakout_faktor"],
    "Rectangle Top": _VOL["breakout_faktor"],
    "High & Tight Flag": _VOL["breakout_faktor"],
}
VOL_FAKTOR_FALLBACK = _VOL["breakout_faktor"]

# Volumenfenster: EINHEITLICH 10 Tage (Gerhard, 28.07.2026). Der Waechter
# verglich den Ausbruch bisher gegen den Ø20, waehrend Gap and Go schon
# gegen Ø10 rechnete — genau die stille Uneinheitlichkeit, die config.py
# beseitigt.
VOL_FENSTER = _VOL["fenster_tage"]

# TAKT DES TAGESDATEN-ABRUFS. War 360 Sekunden — eine Zahl aus Vorsicht,
# nicht aus Technik (Mathias, 28.07.2026: "miss bitte nach, bevor wir uns
# selbst limitieren"). Nachgemessen mit yahootakt.py: EIN Abruf ueber alle
# 265 Aktien mit acht Monaten Tagesdaten dauert 5 bis 7 Sekunden und
# liefert jedes Mal alle 265. Auch zehn Abrufe unmittelbar hintereinander
# liefen sauber durch — von GitHub kommt die Grenze ohnehin nicht, dort
# ist nur die GESAMTLAUFZEIT auf sechs Stunden begrenzt.
#
# Trotzdem bleibt es bei einer Minute statt bei fuenf Sekunden, und zwar
# aus einem Grund, den die Messung NICHT abdeckt: Sie umfasste zehn
# Abrufe. Ein Takt von fuenf Sekunden waere ueber den Handelstag etwa
# 4700 Abrufe statt heute 65 — das Zweiundsiebzigfache. Ob Yahoo das
# dauerhaft mitmacht, ist damit nicht gemessen, und an Yahoo haengt die
# ganze Wache.
#
# Wichtiger noch: Es bringt nichts mehr. Kurs UND Tagesvolumen kommen
# jetzt sekundenfrisch aus dem Live-Strom. Der Abruf liefert nur noch,
# was sich einmal am Tag aendert (Vortagesschluss, Ø50, Flat Base) und
# die Tagesspanne fuer Gap and Go. Eine Minute ist dafuer reichlich.
TAKT = CFG["betrieb"].get("takt_sekunden", 60)

# PRUEFTAKT: So oft wird auf gerissene Kaufpunkte geprueft. Getrennt vom
# Datentakt, weil Kurs, Tagesvolumen und Tagesspanne laufend aus dem Strom
# kommen — die Pruefung muss also nicht auf den naechsten schweren Abruf
# warten. Ausfuehrliche Begruendung in der Hauptschleife.
PRUEF_TAKT = CFG["betrieb"].get("pruef_takt_sekunden", 2)

# In den Push-Meldungen werden Strategienamen ausgeschrieben (Mathias,
# 23.07.2026). In Excel und VOL_FAKTOR bleibt die Kurzform bestehen.
STRATEGIE_VOLL = {
    "VCP": "Volatility Contraction Pattern",
}


def meldungskopf(ticker: str, firma: str) -> str:
    """Erste Zeile jeder Meldung: Kürzel zuerst, Firmenname in Klammern."""
    firma = (firma or "").strip()
    return f"{ticker} ({firma})" if firma else ticker

# --- Gap and Go (Regelwerk Kapitel 7, Power-Gap-Fassung, Juli 2026) --------
# Alle Kriterien sind PFLICHT; die Fassung ist bewusst streng ("Klasse statt
# Masse"). Das Fruehvolumen-Kriterium ist laut Regelwerk NUR live pruefbar
# und gehoert deshalb genau hierher in den Waechter, nicht in den Nachtscan.
_GAP = CFG["gap_and_go"]
GAP_MIN = _GAP["gap_min"]                    # Eroeffnung >= 7 % ueber Vortagesschluss
GAP_VOL_FAKTOR = _VOL["gap_and_go_faktor"]   # Tagesvolumen >= 5x Ø10-Tage
GAP_FRUEH_FAKTOR = 3.0      # erste halbe Stunde: >= 300 % des zeitueblichen
GAP_SCHLUSS_POS = _GAP["schluss_position_min"]

# FLAT BASE — Fassung A (Gerhard, 28.07.2026, verbindlich).
# Vorher stand hier der aeltere Entwurf: 63-126 Tage Fenster, Spanne
# < 35 %. Gerhard hat klargestellt, dass die spaeter recherchierte
# O'Neil/IBD-Fassung gilt: mindestens 5 Wochen (rund 25 Handelstage),
# hoechstens 15 % Tiefe, und der Kurs muss ueber MA10 UND MA21 liegen.
# Der Filter ist damit deutlich strenger und kuerzer als zuvor.
FLAT_BASE_TAGE = int(_GAP["flat_base_wochen"] * 5)   # 5 Wochen = 25 Handelstage
FLAT_BASE_MAX_SPANNE = _GAP["flat_base_max_tiefe"]   # 15 %
FLAT_BASE_MA = (10, CFG["ma"]["kurz"])               # MA10 und MA21


# ---------------------------------------------------------------------------
# Zustand (was wurde schon gemeldet)
# ---------------------------------------------------------------------------

# Die Volumenrechnung liegt seit 28.07.2026 GESCHLOSSEN in volumen.py
# (Gerhards Vorgabe: ein Modul fuer Scanner, Waechter und Gap-and-Go,
# damit nie wieder zwei Stellen mit verschiedenen Fenstern rechnen).
# Diese beiden Huellen bleiben nur, weil der uebrige Waechter sie an
# vielen Stellen aufruft.


def tagesanteil(jetzt=None) -> float:
    """Welcher Anteil des Tagesvolumens ist zu dieser Uhrzeit ueblicherweise
    schon gehandelt? Vor Handelsbeginn und nach Schluss 1,0, damit die
    Hochrechnung dann nichts mehr veraendert."""
    return volumen.tagesanteil(volumen.minute_seit_eroeffnung(jetzt))


def vol_verhaeltnis(vol, avg, jetzt=None):
    """Das Vielfache des fuer DIESE UHRZEIT ueblichen Volumens.
    None, wenn kein Massstab vorliegt."""
    return volumen.verhaeltnis(vol, avg, volumen.minute_seit_eroeffnung(jetzt))


def markt_offen(jetzt=None) -> tuple:
    """Handelt die US-Börse gerade? Liefert (offen, Begruendung).

    Richtet sich selbsttaetig nach amerikanischer Sommer- und Winterzeit:
    Python kennt die Umstellungstermine ueber die Zeitzone America/New_York,
    die sich von den europaeischen unterscheiden (USA: zweiter Sonntag im
    Maerz bis erster Sonntag im November; EU: letzter Sonntag im Maerz bis
    letzter Sonntag im Oktober). In den Wochen dazwischen verschiebt sich
    der Handel gegenueber Wiener Zeit um eine Stunde.

    Der Zeitplan im Workflow deckt deshalb den groesseren Bereich ab, und
    diese Pruefung entscheidet, ob wirklich gehandelt wird. So ist immer der
    volle Boersenhandel abgedeckt, ohne dass jemand zweimal im Jahr
    Zeitangaben nachziehen muss.

    Boersenfeiertage kennt diese Pruefung NICHT - an solchen Tagen laeuft
    der Waechter, findet aber unveraenderte Kurse und meldet nichts."""
    try:
        from zoneinfo import ZoneInfo
        ny = ZoneInfo("America/New_York")
    except Exception:
        return True, "Zeitzone nicht verfügbar — Prüfung übersprungen"

    jetzt = (jetzt or datetime.now(ny)).astimezone(ny)
    if jetzt.weekday() >= 5:
        return False, f"Wochenende in New York ({jetzt:%A})"

    beginn = jetzt.replace(hour=9, minute=30, second=0, microsecond=0)
    ende = jetzt.replace(hour=16, minute=0, second=0, microsecond=0)
    zone = "Sommerzeit" if jetzt.dst() else "Winterzeit"
    if jetzt < beginn:
        return False, f"vor Handelsbeginn ({jetzt:%H:%M} New York, {zone})"
    if jetzt > ende:
        return False, f"nach Handelsschluss ({jetzt:%H:%M} New York, {zone})"
    return True, f"{jetzt:%H:%M} New York ({zone})"


def sekunden_bis_eroeffnung(jetzt=None):
    """Sekunden bis zum heutigen Handelsbeginn in New York.

    Liefert None am Wochenende, nach der Eroeffnung oder ohne Zeitzone.
    Gebraucht fuer die Eroeffnungs-Abdeckung: GitHub feuert Zeitplaene oft
    5-15 Minuten verspaetet — ein Lauf, der kurz VOR der Glocke startet,
    wartet damit bis zur Eroeffnung, statt sich schlafen zu legen."""
    try:
        from zoneinfo import ZoneInfo
        ny = ZoneInfo("America/New_York")
    except Exception:
        return None
    jetzt = (jetzt or datetime.now(ny)).astimezone(ny)
    if jetzt.weekday() >= 5:
        return None
    beginn = jetzt.replace(hour=9, minute=30, second=0, microsecond=0)
    diff = (beginn - jetzt).total_seconds()
    return diff if diff > 0 else None


def letzter_putz() -> str:
    """ISO-Datum des juengsten Freitags-Putzes (Freitag 16:02 New York),
    der bereits VORBEI ist. Steht der heutige Putz noch aus, zaehlt der
    der Vorwoche."""
    try:
        from zoneinfo import ZoneInfo
        jetzt = datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        jetzt = datetime.now()
    d = jetzt.date()
    rueck = (d.weekday() - 4) % 7          # Montag=0 … Freitag=4
    freitag = d - timedelta(days=rueck)
    if rueck == 0 and jetzt.hour * 60 + jetzt.minute < 16 * 60 + 2:
        freitag -= timedelta(days=7)
    return freitag.isoformat()


HTF_MARKE = "HTF|"


def htf_grenze() -> str:
    """Grenze fuer das TAEGLICHE Gedaechtnis der High and Tight Flag.

    Gerhard, praezisiert am 29.07.2026: Die Flagge wird JEDEN TAG
    zurueckgesetzt, alles andere bleibt beim Wochentakt des
    Freitags-Putzes. (Der erste Anlauf hatte das als Kalenderwoche ab
    Montag verstanden — ein Missverstaendnis, hier korrigiert.)

    Zurueckgegeben wird der GESTRIGE Tag, damit der bestehende Vergleich
    'Datum groesser als Grenze' unveraendert passt: Nur was HEUTE
    gemeldet wurde, bleibt im Gedaechtnis; ab morgen darf dieselbe Flagge
    wieder melden.

    Bewusst dieselbe Zeitbasis wie beim Speichern (date.today()) und
    NICHT New Yorker Zeit: Sonst laegen Grenze und gespeichertes Datum an
    den Tagesraendern um einen Tag auseinander, und die Flagge verstummte
    einen Tag zu lang oder meldete einen Tag zu frueh."""
    return (date.today() - timedelta(days=1)).isoformat()


def load_state() -> dict:
    """Melde-Gedaechtnis im Wochen-Rhythmus des Freitags-Putzes.

    Ein Kaufpunkt meldet genau EINMAL — nicht jeden Tag erneut, solange
    der Kurs darueber steht (das war Mathias' 'wildes Durcheinander' vom
    24.07.). Die Gueltigkeit endet analog zu den TraderFox-Alarmen mit
    dem Freitags-Putz (Freitag 16:02 New York, Mathias am 25.07.2026):
    Alles, was am oder vor dem juengsten Putz-Freitag gemeldet wurde,
    verfaellt — jede Meldung gilt damit hoechstens eine Woche, und die
    neue Woche beginnt mit leerem Gedaechtnis, passend zur frisch
    eingetragenen Alarm-Liste. Gap-and-Go-Schluessel tragen zusaetzlich
    das Datum im Namen und sind je Tag einmalig."""
    heute = date.today().isoformat()
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
            gemeldet = data.get("gemeldet", {})
            if isinstance(gemeldet, list):
                # Altes Tagesformat einmalig uebernehmen
                gemeldet = {k: data.get("tag", heute) for k in gemeldet}
            grenze = letzter_putz()
            grenze_htf = htf_grenze()
            # Zwei Fristen: High and Tight Flag TAEGLICH (Gerhard,
            # 29.07.2026), alles andere unveraendert im Wochentakt des
            # Freitags-Putzes.
            return {"gemeldet": {
                k: d for k, d in gemeldet.items()
                # HTF_MARKE mit 'in' statt 'startswith': Der Nachtrag-
                # Schluessel lautet 'BEST|HTF|AAPL|1', die Flaggen-Frist
                # muss auch fuer ihn gelten (29.07.2026).
                if str(d) > (grenze_htf if HTF_MARKE in str(k)
                             else grenze)}}
        except Exception:
            pass
    return {"gemeldet": {}}


def save_state(state: dict):
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception as e:
        print(f"Zustand konnte nicht gespeichert werden: {e}")


# ---------------------------------------------------------------------------
# Kaufpunkte aus der Excel
# ---------------------------------------------------------------------------

def load_watchlist(xlsx_path: str, nur_muster: bool) -> list[dict]:
    """Liest alle Kaufpunkte + die für die Prüfung nötigen Kontextwerte."""
    df = pd.read_excel(xlsx_path, sheet_name="Kaufpunkte")
    items = []
    for _, row in df.iterrows():
        ticker = str(row["Ticker"]).strip()
        firma_roh = row.get("Firma", "")
        firma = "" if pd.isna(firma_roh) else str(firma_roh).strip()
        for i in (1, 2, 3):
            strat = str(row.get(f"KP{i} Strategie", "") or "").strip()
            preis = row.get(f"KP{i} Preis")
            if not strat or pd.isna(preis):
                continue
            if nur_muster and strat.startswith("Fallback"):
                continue
            stop = row.get(f"KP{i} Stop")
            ziel = row.get(f"KP{i} Ziel")
            items.append({
                "ticker": ticker,
                "firma": firma,
                "nr": i,
                "strategie": strat,
                "kaufpunkt": float(preis),
                "stop": None if pd.isna(stop) else float(stop),
                "ziel": None if (ziel is None or pd.isna(ziel) or ziel == "") else float(ziel),
            })
    return _lege_gleiche_preise_zusammen(items)


def _lege_gleiche_preise_zusammen(items: list[dict]) -> list[dict]:
    """Erfuellt eine Aktie zwei Muster auf DEMSELBEN Kurs, ist das EIN
    Kursereignis und darf nur EINE Meldung ergeben.

    Gefunden im Fehlerdurchlauf am 28.07.2026 (Gerhards Pruefpunkt 4): In
    der 265er-Liste hatten vier Aktien zwei Muster-Kaufpunkte auf exakt
    demselben Preis — CareDx und Veracyte, Crinetics, Palo Alto, jeweils
    'High & Tight Flag' zusammen mit 'Darvas Box' bzw. VCP mit Darvas. Der
    Waechter haette beim Ueberschreiten zweimal gemeldet. TraderFox setzt
    dort ohnehin nur einen Alarm (doppelte Preise werden erkannt) — durch
    das Zusammenlegen laufen beide Systeme wieder gleich.

    Zusammengelegt wird nur bei GLEICHEM Ticker UND gleichem Preis (auf den
    Cent). Verschiedene Preise bleiben getrennt: das sind zwei echte
    Ereignisse. Beim Volumen gilt der STRENGERE Faktor — wer VCP und Darvas
    zugleich erfuellt, muss die VCP-Huerde nehmen."""
    nach_schluessel: dict[tuple, dict] = {}
    for it in items:
        schluessel = (it["ticker"].upper(), round(it["kaufpunkt"], 2))
        vorhanden = nach_schluessel.get(schluessel)
        if vorhanden is None:
            it = dict(it)
            it["strategien"] = [it["strategie"]]
            nach_schluessel[schluessel] = it
            continue
        if it["strategie"] not in vorhanden["strategien"]:
            vorhanden["strategien"].append(it["strategie"])
        # Strengere Volumenhuerde und die engere Absicherung gewinnen
        if (VOL_FAKTOR.get(it["strategie"], VOL_FAKTOR_FALLBACK)
                > VOL_FAKTOR.get(vorhanden["strategie"], VOL_FAKTOR_FALLBACK)):
            vorhanden["strategie"] = it["strategie"]
        if it.get("stop") is not None:
            if vorhanden.get("stop") is None or it["stop"] > vorhanden["stop"]:
                vorhanden["stop"] = it["stop"]

    zusammen = list(nach_schluessel.values())
    doppelte = len(items) - len(zusammen)
    if doppelte:
        print(f"  {doppelte} Kaufpunkt(e) auf gleichem Preis zusammengelegt — "
              f"ein Kursereignis ergibt eine Meldung.")
    return zusammen


# ---------------------------------------------------------------------------
# Live-Kurse holen (Batch: Twelve Data kann mehrere Symbole pro Call)
# ---------------------------------------------------------------------------

def fetch_quotes_yahoo(tickers: list[str]) -> dict:
    """Holt Kurs, Tagesvolumen und Durchschnittsvolumen fuer ALLE Ticker in
    einem Abruf.

    Vorteil gegenueber Twelve Data: kein Minutenlimit, kein Tageslimit, und
    31 Aktien sind in rund drei Sekunden da statt in vier Minuten.

    Der Volumenschnitt wird hier SELBST aus den Tagesdaten berechnet, ueber
    VOL_FENSTER Tage aus config.py (seit 28.07.2026 einheitlich 10). Bei
    Twelve Data kam er als Feld 'average_volume', dessen Mittelungszeitraum
    nirgends dokumentiert ist — deshalb rechnen wir selbst."""
    try:
        import yfinance as yf
    except ImportError:
        print("  yfinance nicht verfügbar — weiche auf Twelve Data aus.")
        return {}

    unique = sorted(set(t.upper() for t in tickers))
    try:
        # 8 Monate: Gap and Go braucht bis zu 126 Handelstage Vorgeschichte
        # fuer die Flat-Base-Pruefung (vorher reichten 3 Monate fuers Ø20).
        roh = yf.download(" ".join(unique), period="8mo", interval="1d",
                          group_by="ticker", progress=False,
                          auto_adjust=False, threads=True)
    except Exception as e:
        print(f"  Yahoo-Abruf fehlgeschlagen ({str(e)[:60]}) — Twelve Data übernimmt.")
        return {}

    out = {}
    for t in unique:
        try:
            df = roh[t] if len(unique) > 1 else roh
            df = df.dropna(subset=["Close", "Volume"])
            if df.empty:
                continue
            letzte = df.iloc[-1]
            # Ø20 OHNE die letzte Zeile: Die ist waehrend des Handels der
            # heutige, UNFERTIGE Tag (Ø10 und Flat Base rechnen unten schon
            # immer so). Mit dem unfertigen Tag im Durchschnitt war die
            # Messlatte an ruhigen Vormittagen zu niedrig (Bestaetigung zu
            # leicht) und ausgerechnet an starken Ausbruchstagen zu hoch
            # (Bestaetigung zu schwer) — Gerhards Zweifel vom 23.07.2026.
            # Der Vergleich "heutiges Volumen gegen Ø20" braucht die 20
            # Tage DAVOR, sonst steckt der Messwert im Massstab.
            if len(df) >= 2:
                vol_schnitt = float(df["Volume"].iloc[:-1].tail(VOL_FENSTER).mean())
            else:
                vol_schnitt = 0.0  # brandneue Notierung: ehrlich als unbekannt melden
            eintrag = {
                "close": float(letzte["Close"]),
                "volume": float(letzte["Volume"]),
                "avg_volume": vol_schnitt,
                "is_open": False,
                "name": "",
                # Von WELCHEM Handelstag stammt diese Zeile? Ohne diese
                # Angabe kann der Waechter einen Feiertag nicht von einem
                # Handelstag unterscheiden — siehe pruefe_handelstag().
                "bar_datum": df.index[-1].date(),
            }
            # Zusatzfelder fuer Gap and Go (Regelwerk Kapitel 7). Die letzte
            # Zeile ist waehrend des Handels der HEUTIGE, unfertige Tag —
            # Durchschnitt und Flat Base rechnen deshalb ohne ihn.
            if len(df) >= 2:
                vortage = df.iloc[:-1]
                eintrag["prev_close"] = float(vortage["Close"].iloc[-1])
                # WAR fest auf 10 verdrahtet, waehrend der Ausbruch schon
                # gegen ein anderes Fenster rechnete. Genau solche stillen
                # Uneinheitlichkeiten sollte Gerhards Umbau vom 28.07.2026
                # beenden — jetzt zieht auch Gap and Go seinen Massstab aus
                # config.py.
                eintrag["vol10"] = float(
                    vortage["Volume"].tail(VOL_FENSTER).mean())
                for feld, spalte in (("open", "Open"), ("high", "High"),
                                     ("low", "Low")):
                    wert = letzte.get(spalte)
                    eintrag[feld] = None if pd.isna(wert) else float(wert)
                # FLAT BASE, Fassung A: die letzten 25 Handelstage (5 Wochen)
                # vor dem Gap-Tag, Spanne hoechstens 15 %, und der Kurs muss
                # ueber MA10 UND MA21 liegen (Gerhard, 28.07.2026).
                fenster = vortage.tail(FLAT_BASE_TAGE)
                if len(fenster) >= FLAT_BASE_TAGE:
                    tief = float(fenster["Low"].min())
                    if tief > 0:
                        spanne = (float(fenster["High"].max()) - tief) / tief
                        eintrag["base_spanne"] = spanne
                        flach = spanne <= FLAT_BASE_MAX_SPANNE
                        # Ueber den gleitenden Durchschnitten? Beide werden
                        # OHNE den heutigen, unfertigen Tag gerechnet.
                        ueber_ma = True
                        for tage in FLAT_BASE_MA:
                            if len(vortage) < tage:
                                ueber_ma = False
                                break
                            ma = float(vortage["Close"].tail(tage).mean())
                            if float(letzte["Close"]) <= ma:
                                ueber_ma = False
                                break
                        eintrag["ueber_ma"] = ueber_ma
                        eintrag["flat_base"] = bool(flach and ueber_ma)
            out[t] = eintrag
        except Exception:
            continue
    return out


def fetch_quotes(tickers: list[str], api_key: str, batch_size: int = 8,
                 pause: float = 62.0) -> dict:
    """Holt Quotes in Batches. Rückgabe: {ticker: {close, volume, avg_volume, ...}}

    ACHTUNG Rate-Limit: Twelve Data zaehlt JEDES Symbol als eigenen Credit,
    nicht jeden Aufruf. Beim Free-Tier sind das 8 Credits pro Minute. Ein
    Block mit 8 Symbolen schoepft das Minutenkontingent also komplett aus.

    Die urspruengliche Pause von 8 Sekunden war viel zu kurz: Der zweite
    Block lief in derselben Minute und wurde mit HTTP 429 abgewiesen - von
    31 Aktien kamen nur 16 durch, der Rest wurde stillschweigend nicht
    geprueft. Darum jetzt gut 60 Sekunden zwischen den Bloecken."""
    out = {}
    unique = sorted(set(tickers))
    for i in range(0, len(unique), batch_size):
        chunk = unique[i: i + batch_size]
        params = {"symbol": ",".join(chunk), "apikey": api_key}
        try:
            r = requests.get(QUOTE_URL, params=params, timeout=30)
            data = r.json()
        except Exception as e:
            print(f"  Quote-Abruf fehlgeschlagen für {chunk}: {e}")
            continue

        # Bei einem einzelnen Symbol liefert die API das Objekt direkt,
        # bei mehreren ein Dict {symbol: objekt}
        if isinstance(data, dict) and "symbol" in data:
            data = {data["symbol"]: data}
        if not isinstance(data, dict):
            continue

        for sym, q in data.items():
            if not isinstance(q, dict) or q.get("status") == "error":
                print(f"  [{sym}] keine Quote: {q.get('message', 'unbekannt') if isinstance(q, dict) else q}")
                continue
            try:
                out[sym.upper()] = {
                    "close": float(q["close"]),
                    "volume": float(q.get("volume") or 0),
                    "avg_volume": float(q.get("average_volume") or 0),
                    "is_open": bool(q.get("is_market_open", False)),
                    "name": q.get("name", ""),
                }
            except (KeyError, TypeError, ValueError):
                continue

        if i + batch_size < len(unique):
            time.sleep(pause)  # Free-Tier-Rate-Limit respektieren
    return out


# ---------------------------------------------------------------------------
# Breakout-Prüfung
# ---------------------------------------------------------------------------

def pruefe_breakout(item: dict, quote: dict) -> dict | None:
    """Prüft, ob der Kaufpunkt gerissen wurde. Gibt Treffer-Info zurück oder None."""
    kurs = quote["close"]
    kp = item["kaufpunkt"]
    if kurs < kp:
        return None  # Kaufpunkt noch nicht erreicht

    # Zu weit drüber? Dann ist der Zug abgefahren (kein sauberer Einstieg mehr)
    ueber = kurs / kp - 1
    if ueber > 0.05:
        return None

    faktor = VOL_FAKTOR.get(item["strategie"], VOL_FAKTOR_FALLBACK)
    vol, avg = quote["volume"], quote["avg_volume"]

    # RELATIVES VOLUMEN, auf den ganzen Tag hochgerechnet (volumen.py).
    #
    # Ohne Hochrechnung waere die Volumenbestaetigung vormittags nie
    # erfuellbar: Um 16:00 Wiener Zeit sind erst rund 27 % eines normalen
    # Tagesvolumens gehandelt — ein Ausbruch muesste also fast das
    # Vierfache des Ueblichen ziehen, nur um die 100-%-Schwelle zu
    # erreichen.
    #
    # Mit Hochrechnung lautet die Frage richtig: Ist das Volumen FUER DIESE
    # UHRZEIT ungewoehnlich hoch? Verglichen wird das Verhaeltnis, gemeldet
    # wird Gerhards IBD-Prozentzahl — dieselbe Groesse, nur so
    # geschrieben, dass sie sich direkt gegen IBD halten laesst.
    anteil = tagesanteil()
    vol_ratio = vol_verhaeltnis(vol, avg)
    vol_ok = None if vol_ratio is None else vol_ratio >= faktor

    return {
        **item,
        "kurs": kurs,
        "ueber_pct": ueber * 100,
        "vol_ratio": vol_ratio,
        "vol_pct": None if vol_ratio is None else (vol_ratio - 1) * 100,
        "vol_noetig": faktor,
        "vol_ok": vol_ok,
        "vol_roh": vol,
        "vol_anteil": anteil,
    }


def heute_ny():
    """Heutiges Datum in New York — oder None ohne Zeitzone."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York")).date()
    except Exception:
        return None


def pruefe_handelstag(quotes: dict) -> tuple:
    """Trennt Kurse mit HEUTIGER Tageszeile von veralteten.

    Warum das sein muss (Fehlerdurchlauf 28.07.2026, Gerhards Pruefpunkt 3):
    Der Waechter kannte keinen Boersenkalender. An einem US-Feiertag laeuft
    er trotzdem von 15:30 bis 22:00 unserer Zeit — Yahoo liefert dann als
    'letzte Zeile' den VORTAG. Der Waechter hielt dessen VOLLES Tagesvolumen
    fuer den heutigen Zwischenstand und rechnete es zusaetzlich auf den
    ganzen Tag hoch (vormittags Faktor 3 und mehr). Die Volumenbestaetigung
    war damit an einem Feiertag praktisch immer erfuellt — aus einem frisch
    berechneten Kaufpunkt konnte so eine falsche BESTAETIGTE Kaufmeldung
    werden, an einem Tag ohne jeden Handel.

    Statt eines Feiertagskalenders, den jemand pflegen muesste, fragen wir
    die Daten selbst: Gibt es fuer heute eine Tageszeile? Das erschlaegt
    Feiertage, unerwartete Boersenschliessungen UND haengende Kursquellen
    mit einem Griff."""
    heute = heute_ny()
    if heute is None:
        return quotes, {}
    aktuell, veraltet = {}, {}
    for t, q in quotes.items():
        datum = q.get("bar_datum")
        if datum is None or datum == heute:
            aktuell[t] = q          # Twelve Data liefert Live-Kurse ohne Datum
        else:
            veraltet[t] = q
    return aktuell, veraltet


def ny_minuten():
    """Minuten seit Mitternacht New York — oder None ohne Zeitzone."""
    try:
        from zoneinfo import ZoneInfo
        ny = datetime.now(ZoneInfo("America/New_York"))
        return ny.hour * 60 + ny.minute
    except Exception:
        return None


def pruefe_gap_and_go(ticker: str, q: dict):
    """Regelwerk Kapitel 7 (Power-Gap): Live-Pruefung, alle Kriterien Pflicht.

    1. Eroeffnung >= 7 % ueber Vortagesschluss
    2. Luecke verteidigt: Tagestief bleibt ueber dem Vortagesschluss
    3. Flat Base davor, Fassung A (Gerhard, 28.07.2026): mindestens
       5 Wochen (25 Handelstage), hoechstens 15 % Spanne, Kurs ueber
       MA10 und MA21
    4. Volumen: in der ersten halben Stunde >= 300 % des zeitueblichen
       Werts (Fruehregel, laut Regelwerk NUR live pruefbar); danach
       hochgerechnetes Tagesvolumen >= 5x Ø10-Tage
    5. Zum Handelsende zusaetzlich: Schluss im oberen Fuenftel der
       Tagesspanne UND rohes Tagesvolumen >= 5x Ø10 -> 'BESTÄTIGT'
    Kaufpunkt = Tageshoch + 1 Cent (Einstieg am Folgetag), Stop = das
    engere von Tagestief - 1 Cent und Kaufpunkt x 0,97."""
    open_, high, low = q.get("open"), q.get("high"), q.get("low")
    prev, vol10 = q.get("prev_close"), q.get("vol10")
    kurs, vol = q.get("close"), q.get("volume")
    if None in (open_, high, low, prev, kurs, vol) or not vol10 or prev <= 0:
        return None
    gap = open_ / prev - 1
    if gap < GAP_MIN:
        return None
    if low <= prev:
        return None                      # Gap-Fill — Luecke nicht verteidigt
    if q.get("flat_base") is not True:
        return None                      # Flat Base ist Pflicht; unbekannt = nein

    anteil = tagesanteil()
    if anteil <= 0:
        return None
    # BEIDE Zahlen sind rechnerisch dieselbe Groesse — v/(Ø×F) und
    # (v/F)/Ø. Aufgefallen beim Aufschreiben der Formel fuer Gerhard am
    # 28.07.2026; sie stehen hier getrennt, weil das Regelwerk zwei
    # verschiedene SCHWELLEN kennt (drei- statt fuenffach vor 10:00 NY),
    # nicht zwei verschiedene Messgroessen. Bis Gerhard das klaert, bleibt
    # es so, wie es das Regelwerk beschreibt.
    tages_ratio = volumen.verhaeltnis(vol, vol10,
                                      volumen.minute_seit_eroeffnung())
    if tages_ratio is None:
        return None
    frueh_ratio = tages_ratio

    minuten = ny_minuten()
    in_frueh_phase = minuten is not None and minuten < 600     # vor 10:00 NY
    kurz_vor_schluss = minuten is not None and minuten >= 954  # ab 15:54 NY
    if in_frueh_phase:
        if frueh_ratio < GAP_FRUEH_FAKTOR:
            return None
    elif tages_ratio < GAP_VOL_FAKTOR:
        return None

    spanne = high - low
    pos = (kurs - low) / spanne if spanne > 0 else 1.0
    kp = round(high + 0.01, 2)
    stop = round(min(low - 0.01, kp * 0.97), 2)
    bestaetigt = (kurz_vor_schluss and pos >= GAP_SCHLUSS_POS
                  and vol / vol10 >= GAP_VOL_FAKTOR)
    return {"ticker": ticker, "gap": gap, "frueh": in_frueh_phase,
            "frueh_ratio": frueh_ratio, "tages_ratio": tages_ratio,
            "roh_ratio": vol / vol10, "pos": pos, "kp": kp, "stop": stop,
            "bestaetigt": bestaetigt, "base_spanne": q.get("base_spanne"),
            "kurs": kurs}


def format_gapgo(g: dict) -> str:
    """Meldungsregeln (Mathias, 23.07.2026, beide Nutzer blind mit
    iPhone/VoiceOver; ntfy zeigt alles als einen Textblock):
    - Jede Aktie bekommt beim Zusammenbau eine Nummer vorangestellt
      (nummeriert()), damit hoerbar ist, wo die naechste beginnt.
    - Trenner: Strichpunkt zwischen verschiedenen Angaben, Beistrich
      innerhalb; keine Titel, keine Gedankenstriche, kein senkrechter
      Strich.
    - Ø statt "20-Tage-Durchschnitt" (kuerzer); Vielfache mit dem Wort
      "mal" statt dem Kreuz-Symbol ×.
    - Fuellwoerter wie "erst"/"nur" weglassen; die immer wahre Zeile
      "Luecke verteidigt" bleibt draussen.
    - Sonst alle Angaben drin — radikaleres Kuerzen war Mathias zu viel."""
    kopf = meldungskopf(g["ticker"], g.get("firma", ""))
    status = ("BESTÄTIGT (Schluss im oberen Fünftel)" if g["bestaetigt"]
              else "im Aufbau")
    noetig = GAP_FRUEH_FAKTOR if g["frueh"] else GAP_VOL_FAKTOR
    vol = ("Volumen "
           + volumen.lage_text((g["tages_ratio"] - 1) * 100, VOL_FENSTER)
           + ", " + volumen.huerde_text(noetig))
    luecke = f"Lücke +{g['gap']*100:.1f}%"
    if g.get("base_spanne") is not None:
        luecke += f"; Flat Base davor, Spanne {g['base_spanne']*100:.0f}%"
    zeilen = [f"{kopf}; Gap and Go {status}",
              luecke,
              vol,
              f"Position in der Tagesspanne {g['pos']*100:.0f}%",
              f"Kaufpunkt (Folgetag) {g['kp']:.2f}, Stop {g['stop']:.2f}"]
    if not g["bestaetigt"]:
        zeilen.append("Schlussbestätigung (oberes Fünftel + 5 mal Volumen) "
                      "folgt zum Handelsende")
    return "\n".join(zeilen)


def format_treffer(t: dict) -> str:
    """Trenner-Regeln und Hintergrund siehe format_gapgo.

    KURZFASSUNG seit 29.07.2026, mit Mathias Zeile fuer Zeile abgestimmt.
    Weggefallen sind zwei Angaben, die in JEDER Meldung wortgleich
    standen und zusammen 74 Zeichen kosteten:

    1. "noetig waere mindestens der Schnitt". Fuenf der sechs Muster
       haben dieselbe Huerde, und ob sie genommen wurde, sagt das Wort
       BESTAETIGT ohnehin. Nur bei VCP weicht sie ab — dort wird sie
       weiter genannt, sonst waere unverstaendlich, warum +20 % nicht
       reichen.
    2. "(hochgerechnet, 16% des Tages)". Waehrend des Handels ist der
       Wert IMMER hochgerechnet, die Angabe unterscheidet also nichts.
       Sie verschluesselte nur, wie belastbar die Zahl ist — und das
       wurde nachgemessen (volumen_verlaesslichkeit.py): Ein
       'bestaetigt' um 10:00 New Yorker Zeit ist zu 36 % bis zum
       Schluss hinfaellig, um 14:00 nur noch zu 5 %. Das ergibt sich
       aus der Uhrzeit, die Mathias ohnehin kennt.

    "Vol" statt "Volumen" und "Risk" statt "Risiko" auf seinen Wunsch;
    "Vol" bewusst OHNE Punkt, weil manche Screenreader daraus eine
    Satzendepause machen."""
    lage = volumen.lage_text(t.get("vol_pct"), VOL_FENSTER)
    # Die Huerde nur nennen, wo sie vom Ueblichen abweicht (VCP).
    huerde = ("" if t["vol_noetig"] <= 1.0
              else ", " + volumen.huerde_text(t["vol_noetig"]))
    if t["vol_ok"] is True:
        vol_txt = f"Vol BESTÄTIGT, {lage}{huerde}"
    elif t["vol_ok"] is False:
        vol_txt = f"Vol NICHT bestätigt, {lage}{huerde}"
    else:
        # Kommt nur vor, wenn keine Durchschnittsbasis existiert (brandneue
        # Notierung oder Datenluecke der Kursquelle) — der Waechter rechnet
        # sonst IMMER selbst. "Selbst pruefen" hiess frueher missverstaendlich,
        # man muesse rechnen; gemeint ist: Signal ohne Volumenurteil.
        vol_txt = "Vol nicht bewertbar, zu wenig Kurshistorie"
    # Erfuellt die Aktie mehrere Muster auf DEMSELBEN Kaufpunkt, wurden sie
    # zu einer Meldung zusammengelegt — dann werden auch beide genannt
    # (Fehlerdurchlauf 28.07.2026). Beistrich innerhalb zusammengehoeriger
    # Angaben, wie ueberall.
    namen = t.get("strategien") or [t["strategie"]]
    strategie = ", ".join(STRATEGIE_VOLL.get(n, n) for n in namen)
    zeilen = [
        f"{meldungskopf(t['ticker'], t.get('firma', ''))}; {strategie}",
        f"Kaufpunkt {t['kaufpunkt']:.2f}, Kurs {t['kurs']:.2f} "
        f"(+{t['ueber_pct']:.1f}%); {vol_txt}",
    ]
    schluss = []
    if t["stop"] is not None:
        risiko = (t["kurs"] / t["stop"] - 1) * 100
        schluss.append(f"Stop {t['stop']:.2f}, Risk {risiko:.1f}%")
    if t["ziel"] is not None:
        chance = (t["ziel"] / t["kurs"] - 1) * 100
        schluss.append(f"Ziel {t['ziel']:.2f} (+{chance:.1f}%)")
    if schluss:
        zeilen.append("; ".join(schluss))
    return "\n".join(zeilen)


# ---------------------------------------------------------------------------
# Push
# ---------------------------------------------------------------------------

def nummeriert(bloecke: list[str]) -> str:
    """Baut den Nachrichtentext: '1. ' vor der ersten Aktie, '2. ' vor der
    naechsten usw., Bloecke durch Leerzeilen getrennt. Die Nummer steht
    ganz vorn vor dem Kuerzel, damit beim Vorlesen sofort klar ist, wo
    die naechste Aktie beginnt (Mathias, 23.07.2026)."""
    return "\n\n".join(f"{i}. {block}" for i, block in enumerate(bloecke, 1))


def email_kopf() -> dict:
    """Zusatz-Kopfzeile, damit ntfy die Meldung auch als E-Mail zustellt.

    Hintergrund: Die ntfy-App fuer iOS ist laut eigener Dokumentation
    fehlerhaft und verlangte beim Abonnieren ein Kennwort, das es fuer
    oeffentliche Topics gar nicht gibt. Der E-Mail-Weg braucht weder App noch
    Konto - und eine Mail laesst sich mit einem Screenreader problemlos lesen.

    Ist NTFY_EMAIL nicht gesetzt, aendert sich nichts."""
    adresse = (os.environ.get("NTFY_EMAIL") or "").strip()
    return {"Email": adresse} if adresse else {}


# ntfy macht aus jeder Nachricht ueber 4096 Zeichen eine ANGEHAENGTE
# Textdatei ("You received a file: attachment.txt"), die erst
# heruntergeladen werden muss. Am 27.07.2026 an einem Wegwerf-Thema
# nachgemessen: 3900 Zeichen kommen normal an, 4100 werden zur Datei.
# Genau das ist Mathias an diesem Tag passiert, als viele Treffer auf
# einmal kamen — und kostete ihn im Handel wertvolle Zeit. Darum wird
# nie mehr als eine Portion auf einmal verschickt; die Grenze liegt mit
# Sicherheitsabstand deutlich darunter.
NTFY_GRENZE = 3000


def _portionen(absaetze: list[str], grenze: int = NTFY_GRENZE) -> list[list[str]]:
    """Teilt die Absaetze so auf, dass keine Nachricht die Grenze reisst.
    Getrennt wird NUR zwischen Aktien, nie mitten in einer Meldung."""
    portionen, aktuell, laenge = [], [], 0
    for absatz in absaetze:
        if len(absatz.encode("utf-8")) > grenze:      # Notbremse
            absatz = absatz.encode("utf-8")[:grenze - 20].decode("utf-8", "ignore") + " …"
        gr = len(absatz.encode("utf-8")) + 2
        if aktuell and laenge + gr > grenze:
            portionen.append(aktuell)
            aktuell, laenge = [], 0
        aktuell.append(absatz)
        laenge += gr
    if aktuell:
        portionen.append(aktuell)
    return portionen


def _sende_eine(topic: str, titel: str, body: str, prio: str, tag: str) -> bool:
    kopf = {"Title": titel.encode("utf-8"), "Priority": prio, "Tags": tag}
    kopf.update(email_kopf())
    try:
        r = requests.post(f"https://ntfy.sh/{topic}", data=body.encode("utf-8"),
                          headers=kopf, timeout=20)
    except Exception as e:
        print(f"⚠ Push fehlgeschlagen: {e}")
        return False
    if r.status_code >= 400:
        print(f"⚠ Push abgelehnt: HTTP {r.status_code} — {r.text[:200]}")
        return False
    ntfy_verlauf.merke_antwort(r)
    print(f"Push gesendet an ntfy.sh/{topic} ({len(body)} Zeichen, "
          f"HTTP {r.status_code})")
    return True


# Notbremse fuer die Handelszeit. Wird in main() aus
# --ignoriere-handelszeit gesetzt und gilt NUR fuer Testlaeufe von Hand.
HANDELSZEIT_EGAL = False


def sende(topic: str, titel: str, absaetze: list[str], prio: str, tag: str) -> bool:
    """Verschickt die Absaetze in so vielen Nachrichten wie noetig.

    HIER sitzt die Handelszeit-Sperre (Mathias, 27.07.2026: 'Der Wächter
    darf keinesfalls außerhalb der Börsenzeiten melden'). Bewusst an
    dieser einen Stelle, weil jede automatische Meldung durch sie
    hindurchmuss — Breakouts wie Gap and Go.

    Die Luecke, die es vorher gab: Die Boersenpruefung lief VOR der
    Sechs-Minuten-Pause. Stand sie um 15:59 New Yorker Zeit auf 'offen',
    schlief der Waechter sechs Minuten und meldete um 16:05 — nach dem
    Schlussgong. Auch das Holen der Kurse und das Rechnen brauchen Zeit,
    eine Runde kann also ueber den Schluss hinauslaufen. Darum wird
    unmittelbar vor dem Senden noch einmal auf die Uhr gesehen.

    Wird hier abgelehnt, gilt der Treffer NICHT als gemeldet — er wird
    also zum naechsten Handelsbeginn ganz normal gemeldet."""
    if not absaetze:
        return False
    if not HANDELSZEIT_EGAL:
        offen, grund = markt_offen()
        if not offen:
            print(f"⛔ NICHT gesendet — Börse geschlossen ({grund}). "
                  f"Der Treffer bleibt offen und wird zum nächsten "
                  f"Handelsbeginn gemeldet.")
            return False
    portionen = _portionen(absaetze)
    alle_ok = True
    for nr, teil in enumerate(portionen, 1):
        kopf = titel if len(portionen) == 1 else f"{titel} ({nr} von {len(portionen)})"
        if not _sende_eine(topic, kopf, "\n\n".join(teil), prio, tag):
            alle_ok = False
    return alle_ok


def push_text(topic: str, titel: str, body: str) -> bool:
    """Schickt eine frei formulierte Meldung (fuer Gap and Go).

    MIT Titel-Kopfzeile: Der Titel war am 23.07. als 'Wortgeklingel'
    entfernt worden — ohne ihn setzt ntfy aber einen generischen Titel
    (die Themen-Adresse) ein, was schlimmer ist. Am 24.07. auf Mathias'
    Wunsch wiederhergestellt."""
    return sende(topic, titel, body.split("\n\n"), "high", "rocket")


NACHTRAG_MARKE = "BEST|"


def melde_stufe(res: dict, schon_gemeldet: set) -> str | None:
    """Welche Meldung ist faellig — und vor allem: welche NICHT?

    Mathias' Sorge vom 29.07.2026, woertlich: "So lange sie da ist, löst
    sie ja aus, d.h. das könnte mehrere unbestätigte Meldungen geben."
    Genau das darf nicht passieren, und deshalb steht die Entscheidung
    hier als eigene, pruefbare Funktion statt verstreut in der Schleife.

    Zwei GETRENNTE Schluessel, wie bei Gap and Go seit jeher:
      res["key"]      wird beim ERSTEN Melden gesetzt, ob bestaetigt oder
                      nicht. Der Ausbruch ist damit abgehakt.
      res["key_best"] wird gesetzt, sobald die Bestaetigung gemeldet
                      wurde — oder gleich mit, wenn schon die erste
                      Meldung bestaetigt war.

    Daraus folgt zwingend: hoechstens ZWEI Meldungen je Kaufpunkt und
    Woche. Ein Schluessel, der erst bei Bestaetigung schliesst, haette
    bei zwei Sekunden Prueftakt dreissigmal je Minute gemeldet."""
    if res["key"] not in schon_gemeldet:
        return "neu"
    if res["vol_ok"] is True and res["key_best"] not in schon_gemeldet:
        return "nachtrag"
    return None


def push_nachtrag(topic: str, treffer: list[dict]) -> bool:
    """Meldet, dass ein zuvor UNBESTAETIGT gemeldeter Ausbruch inzwischen
    die Volumenbestaetigung bekommen hat.

    Warum es das gibt (nachgemessen 29.07.2026,
    volumen_verlaesslichkeit.py): Ein 'nicht bestaetigt' um 10:00 New
    Yorker Zeit wird in 14,7 % der Faelle bis zum Handelsschluss doch
    noch bestaetigt. Bisher erfuhr das niemand — der Kaufpunkt galt nach
    der ersten Meldung fuer die Woche als erledigt. Rund jeder siebte
    gemeldete Ausbruch verlor so still seine Bestaetigung.

    Der Nachtrag ist fuer sich allein handelbar: Kurs, Stop und Ziel
    stehen auf dem AKTUELLEN Stand. Die erste Meldung von vor drei
    Stunden zurueckzusuchen waere umstaendlich, und ihre Zahlen sind
    inzwischen ueberholt."""
    if not treffer:
        return True
    if len(treffer) == 1:
        t = treffer[0]
        titel = f"{meldungskopf(t['ticker'], t.get('firma', ''))}, " \
                f"Vol jetzt bestätigt"
        absaetze = [format_treffer(t)]
    else:
        # Bei mehreren passt der Firmenname nicht mehr in den Titel
        # (Mathias, 29.07.2026) — er steht dann in jedem Eintrag.
        titel = (", ".join(t["ticker"] for t in treffer)
                 + ": Vol jetzt bestätigt")
        absaetze = [f"{i}. {format_treffer(t)}"
                    for i, t in enumerate(treffer, 1)]
    return sende(topic, titel, absaetze, "high", "chart_with_upwards_trend")


def push(topic: str, treffer: list[dict]) -> bool:
    """Schickt die Meldung und sagt ehrlich, ob sie angekommen ist.

    Der Rueckgabewert ist wichtig: Frueher wurde der Zustand auch dann als
    'gemeldet' gespeichert, wenn der Push fehlschlug - der Treffer waere
    danach NIE wieder gemeldet worden."""
    bestaetigt = [t for t in treffer if t["vol_ok"] is True]
    rest = [t for t in treffer if t["vol_ok"] is not True]
    # Durchlaufende Nummern ueber alle Portionen hinweg — beim Vorlesen
    # soll die zweite Nachricht mit '6.' weitergehen, nicht wieder mit '1.'.
    absaetze = [f"{i}. {block}" for i, block in
                enumerate([format_treffer(t) for t in bestaetigt + rest], 1)]
    # Titel am 24.07.2026 wiederhergestellt: Ohne Title-Kopfzeile setzt
    # ntfy einen generischen Titel (die Themen-Adresse) ein — das war
    # schlimmer als das am 23.07. beanstandete 'Wortgeklingel'.
    # Seit 29.07. ohne Emoji (Mathias) und kuerzer: Er entscheidet am
    # Titel, ob sich das Oeffnen ueberhaupt lohnt.
    titel = (f"{len(bestaetigt)} bestätigt"
             + (f", {len(rest)} offen" if rest else ""))
    return sende(topic, titel, absaetze,
                 "high" if bestaetigt else "default",
                 "chart_with_upwards_trend")


def testpush(topic: str) -> int:
    """Schickt eine einzelne Testnachricht, damit die Push-Kette einmal
    nachweislich geprueft ist. Ohne Kursdaten, ohne Zustandsaenderung."""
    adresse = (os.environ.get("NTFY_EMAIL") or "").strip()
    weg = f"E-Mail an {adresse}" if adresse else "ntfy-App / Browser"
    text = ("Testnachricht vom Breakout-Wächter.\n\n"
            "Wenn diese Meldung ankommt, funktioniert die "
            "Benachrichtigungskette.\n"
            f"Zustellweg: {weg}\n"
            f"Gesendet: {datetime.now():%d.%m.%Y %H:%M:%S}")
    kopf = {"Title": "✅ Testnachricht Breakout-Wächter".encode("utf-8"),
            "Priority": "default",
            "Tags": "white_check_mark"}
    kopf.update(email_kopf())
    print(f"    Zustellweg: {weg}")
    try:
        r = requests.post(f"https://ntfy.sh/{topic}", data=text.encode("utf-8"),
                          headers=kopf, timeout=20)
    except Exception as e:
        print(f"⚠ Testnachricht fehlgeschlagen: {e}")
        return 1
    if r.status_code >= 400:
        print(f"⚠ Testnachricht abgelehnt: HTTP {r.status_code} — {r.text[:200]}")
        return 1
    ntfy_verlauf.merke_antwort(r)
    print(f"✓ Testnachricht gesendet (HTTP {r.status_code}).")
    print("  Kommt sie am Handy an, ist die Push-Kette in Ordnung.")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Live-Wächter für Kaufpunkt-Breakouts")
    ap.add_argument("xlsx", nargs="?", help="kaufpunkte.xlsx vom Pattern-Scanner")
    ap.add_argument("--alle", action="store_true",
                    help="Auch Fallback-Level überwachen (Standard: nur Muster-Treffer)")
    ap.add_argument("--dry-run", action="store_true", help="Nur anzeigen, kein Push")
    ap.add_argument("--dauerwache", type=int, default=0, metavar="MINUTEN",
                    help="Statt einmal zu prüfen alle 6 Minuten weiterprüfen, "
                         "bis MINUTEN abgelaufen sind oder die Börse schließt. "
                         "Macht die Überwachung unabhängig von GitHubs "
                         "unzuverlässigem Zeitplan.")
    ap.add_argument("--auch-unbestaetigt", action="store_true",
                    help="Auch Breakouts ohne Volumen-Bestätigung pushen (Standard: ja, "
                         "aber klar gekennzeichnet)")
    ap.add_argument("--nur-bestaetigt", action="store_true",
                    help="Nur Breakouts MIT Volumen-Bestätigung pushen")
    ap.add_argument("--testpush", action="store_true",
                    help="Nur eine Testnachricht senden (ohne Kursdaten)")
    ap.add_argument("--ignoriere-handelszeit", action="store_true",
                    dest="ignoriere_handelszeit",
                    help="Auch ausserhalb der US-Handelszeit prüfen (zum Testen)")
    args = ap.parse_args()

    topic = os.environ.get("NTFY_TOPIC")

    # Testnachricht braucht weder API-Schluessel noch Kaufpunkte.
    if args.testpush:
        if not topic:
            sys.exit("Bitte NTFY_TOPIC setzen — ohne Topic kein Push möglich.")
        sys.exit(testpush(topic))

    # Nur noch fuer die Rueckfallebene noetig — Hauptquelle ist Yahoo.
    api_key = os.environ.get("TWELVE_DATA_API_KEY")
    if not api_key:
        print("⚠ Kein TWELVE_DATA_API_KEY gesetzt — keine Rückfallebene, "
              "falls Yahoo ausfällt.")
    if not topic and not args.dry_run:
        sys.exit("Bitte NTFY_TOPIC setzen (oder --dry-run benutzen).")
    if not args.xlsx:
        sys.exit("Bitte kaufpunkte.xlsx angeben (oder --testpush benutzen).")

    # Die Sperre in sende() ueber die Ausnahme fuer Handlaeufe informieren.
    global HANDELSZEIT_EGAL
    HANDELSZEIT_EGAL = bool(args.ignoriere_handelszeit)

    # Ausserhalb der Handelszeit gar nicht erst Kurse abrufen. Der Zeitplan
    # im Workflow deckt Sommer- UND Winterzeit ab; welche gerade gilt,
    # entscheidet sich hier.
    offen, grund = markt_offen()
    print(f"Börsenstatus: {'offen' if offen else 'geschlossen'} — {grund}")
    vorlauf = None
    if not offen and not args.ignoriere_handelszeit:
        # Kurz vor der Eroeffnung? Dann bis zur Glocke warten statt aufgeben.
        # GitHub feuert Zeitplaene oft 5-15 Minuten verspaetet; die
        # vorgezogenen Termine im Workflow plus dieses Warten sorgen dafuer,
        # dass die ersten Boersenminuten trotzdem bewacht sind.
        vorlauf = sekunden_bis_eroeffnung()
        if vorlauf is not None and vorlauf <= 20 * 60:
            print(f"Eröffnung in {int(vorlauf // 60)} Min "
                  f"{int(vorlauf % 60)} s.")
        else:
            vorlauf = None
    if vorlauf is None and not offen and not args.ignoriere_handelszeit:
        print("Nichts zu tun. (Mit --ignoriere-handelszeit trotzdem prüfen.)")
        sys.exit(0)

    items = load_watchlist(args.xlsx, nur_muster=not args.alle)
    if not items:
        sys.exit("Keine Kaufpunkte zum Überwachen gefunden.")
    tickers = [i["ticker"] for i in items]
    print(f"{len(items)} Kaufpunkte über {len(set(tickers))} Aktien werden geprüft "
          f"({datetime.now():%H:%M:%S}).")

    gewuenscht = set(t.upper() for t in tickers)

    # (Die Abstandsrechnung je Aktie ist mit der Staffelung entfallen —
    # es gibt keine knappen Plätze mehr zu vergeben.)

    # Gap and Go (Regelwerk Kapitel 7) beobachtet ALLE Aktien der Liste,
    # nicht nur die mit Muster-Kaufpunkten — eine Kursluecke nach einem
    # Katalysator kann jede treffen.
    firmen = {i["ticker"].upper(): i["firma"] for i in items if i.get("firma")}
    try:
        gap_df = pd.read_excel(args.xlsx, sheet_name="Kaufpunkte")
        gap_universum = sorted(set(
            str(t).strip().upper()
            for t in gap_df["Ticker"].dropna()
            if str(t).strip()))
        # Firmennamen fuer die Meldungskoepfe — auch fuer Aktien ohne
        # Muster-Kaufpunkt (Gap and Go beobachtet die ganze Liste).
        if "Firma" in gap_df.columns:
            for _, r in gap_df.iterrows():
                tk = str(r["Ticker"]).strip().upper()
                fi = r.get("Firma", "")
                if tk and not pd.isna(fi) and str(fi).strip():
                    firmen.setdefault(tk, str(fi).strip())
    except Exception as e:
        print(f"  (Gap-and-Go-Universum nicht lesbar: {e})")
        gap_universum = sorted(gewuenscht)
    print(f"Gap and Go wacht zusätzlich über {len(gap_universum)} Aktien.")
    abruf_ticker = sorted(gewuenscht | set(gap_universum))

    # --- Yahoos Live-Strom fuer ALLE Aktien -----------------------------
    # Loest die dreistufige Staffelung ab (Mathias, 28.07.2026). Die war
    # nur noetig, weil Finnhubs Gratis-Zugang genau 51 Symbole auf EINER
    # Verbindung traegt — bei 265 Aktien mussten sie um Plaetze
    # konkurrieren, nach Naehe zum Kaufpunkt sortiert, mit Hysterese
    # gegen Flattern und Nachbesetzung freier Plaetze.
    #
    # Yahoos Strom braucht keinen Schluessel, traegt rund 100 Symbole je
    # Verbindung und erlaubt beliebig viele Verbindungen. Zweimal
    # nachgemessen, von hier und vom GitHub-Server: 265 von 265 gemeldet,
    # keine einzige stumm, jede Meldung mit Tagesvolumen. Damit gibt es
    # nichts mehr zu verteilen — jede Aktie ist live. Die Staffelung ist
    # ersatzlos entfallen, staffelung.py bleibt nur als Beleg liegen.
    ws = YahooWebSocket(KURSE)
    ws_laeuft = ws.start(abruf_ticker)
    if not ws_laeuft:
        print("Live-Strom NICHT verfügbar — alles läuft über die Tagesdaten, "
              "genau wie vor dem Umbau.")

    # GONG-VORLAUF (Mathias, 28.07.2026). Erst JETZT wird auf die Glocke
    # gewartet — die Verbindungen stehen also schon, wenn sie laeutet.
    # Vorher wurde umgekehrt gewartet und danach verbunden; die
    # Anlaufphase fiel damit in die ersten Handelsminuten, also
    # ausgerechnet in die wichtigsten des Tages. Gemessen am 28.07. am
    # ruhigen Nachmittag: dreieinhalb Minuten, bis alle 265 Aktien im
    # Strom waren, weil eine Aktie erst auftaucht, wenn sie zum ersten
    # Mal handelt.
    # Vorboersliche Geschaefte werden dabei verworfen (yahoo_ws.py), sonst
    # stuenden Kurs und Tagesspanne schon vor Handelsbeginn falsch.
    if vorlauf is not None:
        print(f"Warte bis zum Handelsbeginn — die {len(abruf_ticker)} "
              f"Abos stehen bereits.")
        time.sleep(vorlauf + 20)
        offen, grund = markt_offen()
        print(f"Börsenstatus: {'offen' if offen else 'geschlossen'} — {grund}")
        st = ws.statistik()
        if st["ausserhalb"]:
            print(f"  ({st['ausserhalb']} vorbörsliche Meldungen verworfen — "
                  f"sie gehören nicht in die Tagesspanne.)")
        if not offen and not args.ignoriere_handelszeit:
            ws.stop()
            sys.exit("Börse öffnete nicht wie erwartet — Ende.")

    # Dauerwache: EIN Lauf deckt den ganzen Handelstag ab. Hintergrund
    # (22.07.2026): GitHub feuerte die Zeitplaene nach Repo-Umbenennung und
    # Workflow-Aenderungen stundenlang verspaetet — im ersten Boersenfenster
    # kam kein einziger geplanter Lauf. Mit --dauerwache haengt die
    # Ueberwachung nicht mehr am Zeitplan: Der Lauf prueft alle 6 Minuten
    # selbst weiter, bis die Boerse schliesst oder die Zeit ablaeuft. Die
    # Zeitplan-Laeufe bleiben als Rueckfallebene bestehen; die
    # concurrency-Gruppe im Workflow verhindert Doppelmeldungen.
    ende_dauerwache = None
    if args.dauerwache > 0:
        ende_dauerwache = datetime.now() + timedelta(minutes=args.dauerwache)
        print(f"Dauerwache aktiv: alle 6 Minuten, für bis zu {args.dauerwache} "
              f"Minuten (spätestens bis {ende_dauerwache:%H:%M} Serverzeit).")

    state = load_state()
    schon_gemeldet = set(state["gemeldet"])

    # ZWEI TAKTE STATT EINEM (Mathias, 28.07.2026: "Stelle auf Echtzeit um").
    #
    # Bis jetzt lief beides im selben Takt: Daten holen und pruefen. Damit
    # war die Meldung immer so langsam wie der Abruf — zuerst sechs
    # Minuten, dann eine. Das ist unnoetig, weil die beiden Dinge voellig
    # verschiedene Fristen haben:
    #
    #   DATENTAKT (TAKT, 60 s): der schwere Abruf ueber alle 265 Aktien.
    #     Er liefert nur noch, was sich einmal am Tag aendert —
    #     Vortagesschluss, Ø50, Flat Base, Eroeffnung, Datum der Kurszeile.
    #   PRUEFTAKT (2 s): Kurs, Tagesvolumen und Tagesspanne kommen laufend
    #     aus dem Strom. Geprueft wird auf diesem frischen Stand.
    #
    # Bewusst NICHT bei jeder einzelnen Kursmeldung geprueft: Der Strom
    # schickt rund 3600 Meldungen je Minute (nachgemessen), das waeren
    # 3600 vollstaendige Durchlaeufe ueber alle Kaufpunkte fuer einen
    # Gewinn von Sekundenbruchteilen. Zwei Sekunden sind gegenueber den
    # bisherigen sechs Minuten der Faktor 180 — und der Rest waere
    # Rechenarbeit ohne Nutzen.
    basis = {}                       # letzter Tagesdaten-Stand
    naechster_abruf = 0.0
    sperre_bis = 0.0                 # nach Sendefehler kurz nicht erneut
    runde = 0
    while True:
        jetzt_s = time.time()
        # Auf die Uhr sehen, BEVOR geprueft wird — sonst koennte der
        # Schlussgong zwischen zwei Durchlaeufen durchrutschen
        # (Mathias, 27.07.2026).
        offen, grund = markt_offen()
        if runde and not offen and not args.ignoriere_handelszeit:
            print(f"Börse geschlossen ({grund}) — Wache beendet.")
            break

        laut = jetzt_s >= naechster_abruf
        if not laut:
            if not basis:
                time.sleep(PRUEF_TAKT)
                continue
            # Zwischen zwei Abrufen: auf dem letzten Tagesstand arbeiten,
            # aber mit frischen Kursen aus dem Strom. Je Durchlauf eine
            # eigene Kopie, weil die Einblendung sie veraendert.
            quotes = {t: dict(q) for t, q in basis.items()}
            veraltete_quotes = {}
        else:
            runde += 1
            naechster_abruf = jetzt_s + TAKT
            if runde > 1:
                print(f"\n——— Datenabruf {runde} "
                      f"({datetime.now():%H:%M:%S}) ———")

        # Hauptquelle Yahoo (ein Abruf, kein Limit), Twelve Data als Rueckfall.
        if laut:
            quotes = fetch_quotes_yahoo(abruf_ticker)
            merke_kurse(quotes, "yfinance")
            if len(quotes) < len(gewuenscht):
                fehlend_yahoo = sorted(gewuenscht - set(quotes))
                if quotes:
                    print(f"  Yahoo lieferte {len(quotes)} von "
                          f"{len(gewuenscht)} — hole {len(fehlend_yahoo)} "
                          f"über Twelve Data nach.")
                if api_key:
                    nachgeholt = fetch_quotes(fehlend_yahoo, api_key)
                    merke_kurse(nachgeholt, "twelvedata")
                    quotes.update(nachgeholt)
                elif not quotes and ende_dauerwache is None:
                    sys.exit("Yahoo lieferte nichts und kein "
                             "TWELVE_DATA_API_KEY gesetzt.")

            # Stammen die Kurse ueberhaupt von HEUTE? An Feiertagen und bei
            # haengenden Quellen liefert Yahoo die Zeile des Vortags — deren
            # volles Tagesvolumen wuerde hochgerechnet fast jede
            # Volumenbestaetigung erschleichen (Fehlerdurchlauf 28.07.2026).
            quotes, veraltete_quotes = pruefe_handelstag(quotes)
            if veraltete_quotes and not quotes:
                datum = next(iter(veraltete_quotes.values())).get("bar_datum")
                print(f"⛔ Keine einzige Kurszeile von heute (jüngste ist vom "
                      f"{datum}) — es wird nichts geprüft und nichts gemeldet.")
                # NICHT sofort aufgeben: Direkt nach der Eroeffnung kann Yahoo
                # ein paar Minuten brauchen, bis die heutige Tageszeile steht.
                # Wuerde die Wache daraufhin enden, haetten wir uns den
                # Handelstag selbst abgeschaltet — schlimmer als das Problem.
                # Erst wenn die Boerse laengst offen ist und immer noch nichts
                # da ist, ist es wirklich ein Feiertag oder ein Quellenausfall.
                minuten = ny_minuten()
                seit_eroeffnung = ((minuten - 9 * 60 - 30)
                                   if minuten is not None else 0)
                if ende_dauerwache is None:
                    sys.exit(0)
                if seit_eroeffnung >= 45:
                    print("Seit über 45 Minuten keine heutigen Kurse — "
                          "Börsenfeiertag oder Quellenausfall. Wache beendet.")
                    break
                print(f"Möglicherweise hinkt die Kursquelle nach der "
                      f"Eröffnung nach — nächster Versuch in {TAKT} Sekunden.")
                time.sleep(TAKT)
                continue
            if veraltete_quotes:
                namen = sorted(veraltete_quotes)
                print(f"⚠ {len(namen)} Aktien ohne heutige Kurszeile — "
                      f"übersprungen (keine Meldung auf veralteten Daten): "
                      + ", ".join(namen[:15]) + (" …" if len(namen) > 15 else ""))
            # Diesen Stand als Grundlage merken. Die Kopie ist wichtig:
            # Die Einblendung veraendert die Eintraege, und der naechste
            # Durchlauf muss wieder vom unveraenderten Tagesstand ausgehen.
            basis = {t: dict(q) for t, q in quotes.items()}

        # Live-Werte ueber die Tagesdaten legen: Kurs, Tagesvolumen UND die
        # Tagesspanne. Das geschieht in JEDEM Durchlauf, also alle zwei
        # Sekunden — hier entsteht die Echtzeit.
        if ws_laeuft:
            kurse_live, volumina_live, spannen_live = ws_kurse_einblenden(
                quotes, ws)
            st = ws.statistik()
            if laut:
                print(f"  Live-Strom: {kurse_live} Kurse, {volumina_live} "
                      f"Tagesvolumina und {spannen_live} Tagesspannen "
                      f"sekundenfrisch ({st['verbindungen']} Verbindungen, "
                      f"{st['meldungen']} Meldungen bisher).")
                if st["neustarts"]:
                    print(f"  ({st['neustarts']} Verbindungsabrisse bisher, "
                          f"jeweils selbsttätig neu aufgebaut.)")
                ohne = ws.ohne_meldung()
                if ohne:
                    print(f"  Hinweis: {len(ohne)} Aktien haben noch gar "
                          f"nichts geschickt (sie laufen über die "
                          f"Tagesdaten): " + ", ".join(ohne[:12])
                          + (" …" if len(ohne) > 12 else ""))
            if st["verbindungen"] == 0:
                # Das MUSS auffallen, auch zwischen den Abrufen.
                print("  ⚠ Keine Verbindung zum Live-Strom — es zählen "
                      "solange die Tagesdaten.")

        # Haengt eine Quelle? Der Speicher weiss, wann jeder Kurs zuletzt
        # frisch war — je Quelle mit eigener Schwelle.
        haengend = [t for t in KURSE.stale_liste() if t in gewuenscht]
        if haengend:
            if laut:
                print(f"⚠ {len(haengend)} Kurse gelten als hängend und werden "
                      f"NICHT für Auslöser verwendet: "
                      + ", ".join(sorted(haengend)[:15]))
            for t in haengend:
                quotes.pop(t, None)

        if laut:
            print(f"{len(gewuenscht & set(quotes))} von {len(gewuenscht)} "
                  f"Kaufpunkt-Quotes erhalten ({len(quotes)} Aktien gesamt).")
        if not quotes:
            # In der Dauerwache ist ein Aussetzer kein Todesurteil — der
            # naechste Abruf kommt in einer Minute.
            if ende_dauerwache is None:
                sys.exit("Keine Kursdaten erhalten — Abbruch.")
            if laut:
                print(f"⚠ Keine Kursdaten — nächster Versuch in {TAKT} Sekunden.")
        else:
            # Unvollstaendige Abfragen NICHT stillschweigend hinnehmen: Fuer die
            # fehlenden Aktien kann kein Breakout erkannt werden, und ohne
            # Hinweis sieht der Lauf trotzdem erfolgreich aus.
            fehlend = sorted(gewuenscht - set(quotes))
            if fehlend and laut:
                print(f"\n⚠ ACHTUNG: {len(fehlend)} Aktien konnten NICHT geprüft werden:")
                print("  " + ", ".join(fehlend))
                print("  Für diese Werte wird kein Ausbruch erkannt.")

            treffer, neu, nachtrag = [], [], []
            for item in items:
                q = quotes.get(item["ticker"].upper())
                if not q:
                    continue
                res = pruefe_breakout(item, q)
                if not res:
                    continue
                # Kennung am Treffer mitfuehren. Vorgemerkt wird ERST nach
                # einem erfolgreichen Push - siehe unten.
                # OHNE Preis (Mathias, 27.07.2026): Der Kaufpunkt wandert
                # taeglich mit dem Musterdeckel nach oben. Steckte er im
                # Schluessel, galt derselbe Ausbruch am naechsten Tag als
                # neu und wurde erneut gemeldet — genau das 'wilde
                # Durcheinander', das abgestellt werden sollte. Aktie plus
                # Kaufpunkt-Nummer genuegen: einmal gemeldet ist gemeldet,
                # bis der Freitags-Putz das Gedaechtnis leert.
                #
                # AUSNAHME High and Tight Flag (Gerhard, 29.07.2026): Die
                # Flagge bekommt ein Vorzeichen im Schluessel, damit
                # load_state() ihr die TAEGLICHE Frist geben kann statt
                # der woechentlichen. Deckt ein Kaufpunkt mehrere Muster
                # ab, genuegt eines davon — die kuerzere Frist gewinnt,
                # der Ausbruch darf dann taeglich neu melden.
                marke = (HTF_MARKE
                         if "High & Tight Flag" in (res.get("strategien")
                                                    or [res["strategie"]])
                         else "")
                res["key"] = f"{marke}{item['ticker']}|{item['nr']}"
                # ZWEITE STUFE (Mathias, 29.07.2026). Zwei GETRENNTE
                # Schluessel, genau wie Gap and Go es seit jeher macht:
                #   res["key"]      — beim ersten Melden gesetzt, egal ob
                #                     bestaetigt. Der Ausbruch ist damit
                #                     abgehakt und wiederholt sich NICHT.
                #   res["key_best"] — nur gesetzt, wenn die Bestaetigung
                #                     gemeldet wurde.
                # War die erste Meldung schon bestaetigt, werden beide
                # zusammen gesetzt — dann kann der Nachtrag gar nicht mehr
                # feuern. Mehr als zwei Meldungen je Kaufpunkt und Woche
                # sind damit mechanisch unmoeglich. Genau das war Mathias'
                # Sorge: Ein Schluessel, der erst bei Bestaetigung
                # schliesst, wuerde bei zwei Sekunden Takt dreissigmal je
                # Minute melden.
                res["key_best"] = NACHTRAG_MARKE + res["key"]
                treffer.append(res)
                stufe = melde_stufe(res, schon_gemeldet)
                if stufe == "neu":
                    neu.append(res)
                elif stufe == "nachtrag":
                    nachtrag.append(res)

            # Zwischen den Abrufen nur ausgeben, wenn es wirklich etwas
            # Neues gibt — sonst stuende alle zwei Sekunden dieselbe Liste
            # im Protokoll und die echten Ereignisse gingen darin unter.
            if laut or neu:
                if neu and not laut:
                    print(f"\n⚡ {datetime.now():%H:%M:%S} — {len(neu)} neue(r) "
                          f"Kaufpunkt(e) gerissen:")
                else:
                    print(f"\n{len(treffer)} Kaufpunkte aktuell gerissen, "
                          f"davon {len(neu)} neu seit dem letzten Lauf.")
                for t in (treffer if laut else neu):
                    marker = ("🟢" if t["vol_ok"] is True
                              else ("🟡" if t["vol_ok"] is False else "⚪"))
                    neu_marker = " [NEU]" if t in neu else ""
                    print(f"  {marker} {format_treffer(t)}{neu_marker}\n")

            # Erst filtern, dann vormerken. Frueher galten auch Treffer als
            # gemeldet, die wegen --nur-bestaetigt gar nicht gepusht wurden -
            # bekamen sie spaeter die Volumenbestaetigung, wurden sie nie
            # mehr gemeldet.
            zu_melden = neu
            if args.nur_bestaetigt:
                zu_melden = [t for t in neu if t["vol_ok"] is True]
                uebersprungen = len(neu) - len(zu_melden)
                if uebersprungen:
                    print(f"{uebersprungen} Treffer ohne Volumenbestätigung — bleiben "
                          "offen und werden weiter beobachtet.")

            # SENDESPERRE NACH FEHLSCHLAG. Frueher lag zwischen zwei
            # Versuchen die volle Runde; jetzt sind es zwei Sekunden. Ohne
            # Sperre wuerde ein haengender ntfy-Dienst dreissigmal je
            # Minute angeklopft, statt zweimal je Runde — dem Dienst
            # gegenueber unfair und fuer uns nutzlos. Nach einem
            # Fehlschlag also erst beim naechsten Datenabruf wieder.
            if zu_melden and jetzt_s < sperre_bis:
                pass
            elif zu_melden and not args.dry_run:
                if push(topic, zu_melden):
                    heute_s = date.today().isoformat()
                    for t in zu_melden:
                        schon_gemeldet.add(t["key"])
                        state["gemeldet"][t["key"]] = heute_s
                        # War der Ausbruch schon bei der ersten Meldung
                        # bestaetigt, ist der Nachtrag gegenstandslos —
                        # sein Schluessel wird gleich mitgesetzt.
                        if t["vol_ok"] is True:
                            schon_gemeldet.add(t["key_best"])
                            state["gemeldet"][t["key_best"]] = heute_s
                    save_state(state)
                else:
                    sperre_bis = jetzt_s + TAKT
                    print(f"⚠ Zustand NICHT gespeichert — nächster Versuch "
                          f"in {TAKT} Sekunden.")
            elif not zu_melden:
                if laut:
                    print("Nichts Neues zu melden.")
            else:
                print("(Dry-Run — kein Push gesendet, Zustand nicht gespeichert)")
                # Auch im Trockenlauf vormerken, SONST meldet der Lauf
                # dieselben Treffer alle zwei Sekunden erneut. Im Echtlauf
                # besorgt das der erfolgreiche Push; ohne diese Zeile
                # verhielte sich der Trockenlauf anders als der Ernstfall
                # und waere als Probe wertlos (aufgefallen 28.07.2026).
                for t in zu_melden:
                    schon_gemeldet.add(t["key"])
                    if t["vol_ok"] is True:
                        schon_gemeldet.add(t["key_best"])

            # --- Nachtrag: Volumen hat nachgezogen ---------------------
            if nachtrag and jetzt_s >= sperre_bis:
                print(f"\n{len(nachtrag)} Ausbruch/Ausbrüche haben die "
                      f"Volumenbestätigung nachgereicht:")
                for t in nachtrag:
                    print("  " + format_treffer(t).replace("\n", "\n  ") + "\n")
                if args.dry_run:
                    print("(Dry-Run — kein Nachtrag gesendet)")
                    for t in nachtrag:
                        schon_gemeldet.add(t["key_best"])
                elif push_nachtrag(topic, nachtrag):
                    heute_s = date.today().isoformat()
                    for t in nachtrag:
                        schon_gemeldet.add(t["key_best"])
                        state["gemeldet"][t["key_best"]] = heute_s
                    save_state(state)
                else:
                    sperre_bis = jetzt_s + TAKT

            # --- Gap and Go (Regelwerk Kapitel 7) --------------------------
            # Zwei Meldestufen je Aktie und Tag: 'im Aufbau', sobald alle
            # live pruefbaren Pflichtkriterien stehen, und 'BESTÄTIGT' zum
            # Handelsende (Schluss im oberen Fuenftel + 5x Volumen roh).
            gap_neu = []
            for gt in gap_universum:
                q = quotes.get(gt)
                if not q:
                    continue
                g = pruefe_gap_and_go(gt, q)
                if not g:
                    continue
                g["firma"] = firmen.get(gt, "")
                stufe = "GAPGOFIX|" if g["bestaetigt"] else "GAPGO|"
                g["key"] = f"{stufe}{gt}|{date.today().isoformat()}"
                if g["key"] not in schon_gemeldet:
                    gap_neu.append(g)
            if gap_neu:
                print(f"\n🚀 Gap and Go: {len(gap_neu)} Meldung(en)")
                for g in gap_neu:
                    print("  " + format_gapgo(g).replace("\n", "\n  ") + "\n")
                if args.dry_run:
                    print("(Dry-Run — kein Gap-and-Go-Push)")
                    for g in gap_neu:       # sonst alle zwei Sekunden erneut
                        schon_gemeldet.add(g["key"])
                elif jetzt_s < sperre_bis:
                    pass                    # Sendesperre nach Fehlschlag
                else:
                    body = nummeriert([format_gapgo(g) for g in gap_neu])
                    titel = "🚀 Gap and Go: " + ", ".join(g["ticker"]
                                                          for g in gap_neu)
                    if push_text(topic, titel, body):
                        for g in gap_neu:
                            schon_gemeldet.add(g["key"])
                            state["gemeldet"][g["key"]] = date.today().isoformat()
                        save_state(state)
                    else:
                        sperre_bis = jetzt_s + TAKT

        if ende_dauerwache is None:
            break
        if datetime.now() >= ende_dauerwache:
            print("Dauerwache: Zeit abgelaufen — Ende.")
            ws.stop()
            break
        time.sleep(PRUEF_TAKT)

    # Verbindungen sauber schliessen, damit kein Faden offen bleibt.
    ws.stop()


if __name__ == "__main__":
    main()
