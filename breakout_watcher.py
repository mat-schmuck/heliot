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
import base64
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
import red_to_green   # Kapitel 9: Volumen-Signatur an der Kreuzung
import red_to_green_explosive  # Kapitel 11: dreht aus eigenem Antrieb
import exit_regeln    # Exit-Regelwerk: Stops, Gewinnabsicherung
import trigger_logbuch  # schreibt jedes Signal mit, gemeldet oder nicht
import volumen        # IBD Volume % Change
import insider_edgar   # Insider-Kaeufe bei der SEC (Gerhards Kapitel vom 14.08.2026)
import sektor_radar    # Dreht eine ganze Branche? Rechnet der Nachtlauf, meldet der Waechter
import zahlen_termine  # Wer heute Abend berichtet, wird vermerkt — die EINZIGE Volumenrechnung
import positionen      # Kapitel 11/12: Bestand samt Beobachtungen
import beobachtungen   # Kapitel 12: Trigger werden Beobachtungen
import handelskalender  # Fragt den Datenanbieter, ob heute ueberhaupt gehandelt wird
import gewinnzonen_lauf  # Kapitel 12: Nachtbefunde zum Handelsstart mit heutigen Kursen nachrechnen
import gewinn_zonen as gz  # Kapitel 12: Klimax-Katalog fuer die schlussnahen Befunde (M1, 12.09.2026)
from config import CFG, hoechstens, mind_erreicht, pruefe_config
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
TS_URL = "https://api.twelvedata.com/time_series"

# --- Nachladen hohler Tageskerzen (Mathias, 18.08.2026) --------------------
# Yahoo liefert manchmal den juengsten fertigen Handelstag als Zeile MIT
# Datum, aber OHNE Werte (gemessen am 18.08.2026: Montag bei KEYS, UMAC,
# LPG und dutzenden weiteren leer, waehrend SPY und NVDA vollstaendig
# waren; um 00:04 waren die Werte noch da, vormittags rueckwirkend weg).
# Die eingebaute Rueckfallkette griff dabei NICHT, denn sie springt nur
# an, wenn Yahoo GAR NICHTS liefert - eine Zeile ohne Werte hielt sie
# fuer Erfolg. Gemessen ist auch die Loesung: Twelve Data hatte denselben
# Tag fuer alle Pruefkandidaten vollstaendig, auf den Cent gleich mit
# unserer Mappe.
#
# GEZIELT statt breit: nachgeladen wird nur der EINE fehlende Tag je
# Aktie, mit Tages-Zwischenspeicher (jede Luecke wird hoechstens einmal
# angefragt), gedrosselt auf die Gratis-Grenzen (8 je Minute, 800 je
# Tag - unser Deckel liegt mit 300 weit darunter) und hoechstens
# TD_JE_RUNDE Abrufe je Datenrunde, damit der 60-Sekunden-Takt nicht
# aus dem Tritt kommt. Der Rest der Luecken kommt in den Folgerunden
# dran; bis dahin traegt der Mappen-Rueckfall den Vortagesschluss.
_td_kerzen_cache: dict = {}     # (ticker, datum) -> Werte-dict oder None
_td_haushalt = {"tag": None, "gesamt": 0, "letzter": 0.0}
TD_JE_RUNDE = 4
TD_JE_TAG = 300


def td_kerze_nachladen(ticker: str, datum) -> dict | None:
    """Die EINE fehlende Tageskerze von Twelve Data, oder None.

    Zwischenspeicher zuerst: Auch ein Fehlversuch wird gemerkt, damit
    dieselbe Luecke nicht jede Runde neu angefragt wird. Der Schluessel
    kommt aus der Umgebung (TWELVE_DATA_API_KEY, im Workflow gesetzt);
    ohne ihn ist die Antwort still None."""
    kennung = (ticker, str(datum))
    if kennung in _td_kerzen_cache:
        return _td_kerzen_cache[kennung]
    api_key = (os.environ.get("TWELVE_DATA_API_KEY") or "").strip()
    if not api_key:
        return None
    heute = date.today().isoformat()
    if _td_haushalt["tag"] != heute:
        _td_haushalt.update(tag=heute, gesamt=0)
    if _td_haushalt["gesamt"] >= TD_JE_TAG:
        return None                    # Budget erschoepft: NICHT cachen
    warte = 7.6 - (time.time() - _td_haushalt["letzter"])
    if warte > 0:
        time.sleep(warte)              # 8 Abrufe je Minute, Pflichtgrenze
    _td_haushalt["letzter"] = time.time()
    _td_haushalt["gesamt"] += 1
    try:
        r = requests.get(TS_URL, params={
            "symbol": ticker, "interval": "1day", "outputsize": 6,
            "apikey": api_key}, timeout=15)
        d = r.json()
        if d.get("status") != "ok":
            _td_kerzen_cache[kennung] = None
            return None
        for w in d.get("values", []):
            if w.get("datetime") == str(datum):
                werte = {"Open": float(w["open"]), "High": float(w["high"]),
                         "Low": float(w["low"]), "Close": float(w["close"]),
                         "Volume": float(w.get("volume") or 0.0)}
                _td_kerzen_cache[kennung] = werte
                print(f"  {ticker}: hohle Tageskerze {datum} von Twelve "
                      f"Data nachgeladen (Schluss {werte['Close']:.2f}).")
                return werte
        _td_kerzen_cache[kennung] = None
        return None
    except Exception:
        return None                    # Netzfehler: naechste Runde erneut


def hohle_kerze_fuellen(ticker: str, roh_df, budget_frei: int):
    """Fehlt der juengste FERTIGE Handelstag, weil Yahoo ihn leer
    lieferte? Dann von Twelve Data fuellen.

    Rueckgabe: (bereinigtes df, verbrauchte Abrufe). Erkannt wird die
    Luecke daran, dass unter den weggeworfenen Leerzeilen eine liegt,
    die NEUER ist als der letzte gute Vortag - ein Feiertag sieht anders
    aus, fuer den gibt es bei Yahoo gar keine Zeile."""
    df = roh_df.dropna(subset=["Close", "Volume"])
    if len(df) < 2 or budget_frei <= 0:
        return df, 0
    leer = roh_df["Close"].isna()
    if not bool(leer.iloc[:-1].any()):
        return df, 0
    letzte_leere = roh_df.index[:-1][leer.iloc[:-1]][-1]
    vortage = df.iloc[:-1]
    if not len(vortage) or letzte_leere <= vortage.index[-1]:
        return df, 0                   # die Luecke liegt weiter zurueck
    werte = td_kerze_nachladen(ticker, letzte_leere.date())
    if not werte:
        return df, 1
    roh_df = roh_df.copy()
    for spalte, wert in werte.items():
        roh_df.loc[letzte_leere, spalte] = wert
    return roh_df.dropna(subset=["Close", "Volume"]), 1

STATE_FILE = Path("watcher_state.json")
# Dieselbe Struktur, im REPO eingecheckt — die uebergabefeste Fassung
# des Melde-Gedaechtnisses (siehe load_state/_repo_sichern).
REPO_STATE = "melde_gedaechtnis.json"

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
    # DIE WOCHENFASSUNG GEHOERT AUSDRUECKLICH DAZU (gefunden am
    # 11.08.2026 von gesamtpruefung.py, Block D). Der Scanner erzeugt den
    # Namen "Cup & Handle (Wochenbasis)" seit dem 04.08.2026, diese
    # Tabelle kannte ihn nicht — die Huerde fiel still auf
    # VOL_FAKTOR_FALLBACK. Schaden entstand keiner, weil der Rueckfall
    # zufaellig denselben Wert hat. Genau das ist das Gefaehrliche daran:
    # Wer den Faktor fuer Cup & Handle je aendert, aendert ihn fuer die
    # Wochenfassung NICHT mit, und niemand merkt es.
    "Cup & Handle (Wochenbasis)": _VOL["breakout_faktor"],
    "Rectangle Top": _VOL["breakout_faktor"],
    "High & Tight Flag": _VOL["breakout_faktor"],
    # Earnings-Pullback (Gerhards Freigabe 31.08.2026): Ausbruch aus der
    # Konsolidierung nach dem Zahlen-Gap. Die VCP-Huerde (140 Prozent
    # vom Schnitt) statt der Standard-Huerde — der Ausbruch soll zeigen,
    # dass die Nachfrage nach der Ruhephase ZURUECK ist; O'Neils Rahmen
    # fuer solche Fortsetzungen nennt 40 bis 50 Prozent ueber dem
    # Schnitt, genau dieses Band.
    "Earnings-Pullback": _VOL["breakout_faktor_vcp"],
    # HTF Innen-Einstieg (Soreide-Ausbau, 31.08.2026): dieselbe Huerde
    # wie die Flagge selbst — das Volumen steckt im Fahnenmast.
    "HTF Innen-Einstieg": _VOL["breakout_faktor"],
    # EMA Crossback (Gerhard, G11 vom 31.08.2026): Standard-Huerde. Kell
    # verlangt stuetzendes Kaufverhalten, das ist der uebliche
    # Volumen-Massstab, keine Sonderhuerde.
    "EMA Crossback": _VOL["breakout_faktor"],
}
VOL_FAKTOR_FALLBACK = _VOL["breakout_faktor"]

# WER DARF OHNE VOLUMENBESTAETIGUNG MELDEN (Gerhard, 12.08.2026)?
# Nur diese. Bei allen uebrigen Mustern bleibt ein Ausbruch ohne
# Bestaetigung STILL und wird erst gemeldet, wenn das Volumen nachzieht.
UNBESTAETIGT_ERLAUBT = set(_VOL.get("unbestaetigt_melden_bei", []))

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

# Wie weit ueber dem Kaufpunkt gilt ein Ausbruch noch als einsteigbar,
# und was passiert mit dem, was darueber liegt (siehe pruefe_breakout).
NACHLAUF_GRENZE = CFG["betrieb"].get("nachlauf_grenze", 0.05)
# Wie weit UNTER die Grenze der Kurs zurueck muss, damit der Kaufpunkt
# wieder als "im Einstiegsfenster" gilt. Siehe fenster_zustand().
WIEDEREINTRITT_TOTZONE = CFG["betrieb"].get("wiedereintritt_totzone", 0.01)
MELDE_UEBERSPRUNGENE = CFG["betrieb"].get("melde_uebersprungene", True)
# Nur Ausbrueche melden, die HEUTE gerissen wurden (Frage M4 an Gerhard,
# 11.09.2026). Die Begruendung steht bei riss_schon_gestern().
NUR_FRISCHE_AUSBRUECHE = CFG["betrieb"].get("nur_frische_ausbrueche", True)
# GERHARDS ANTWORTEN VOM 12.09.2026 (Werte in config.py):
#   M1  Schlussnahe Befunde ab Minute 945 (15:45 New York) mit Handelskursen.
#   R9  Gruene Minuten je Aktie fuer den Abendbericht ("gruen bei rotem Markt").
#   M6  Die um 15:45 gemeldeten Befunde stehen in einer Datei, der Nachtlauf
#       prueft sie mit dem Schluss nach und der Abendbericht meldet Ruecknahmen.
SCHLUSSNAHE_MINUTE = int(CFG["betrieb"].get("schlussnahe_minute", 945))
GRUEN_DATEI = "gruen_minuten.json"
SCHLUSSNAH_DATEI = "schlussnahe_gemeldet.json"
SCHLUSSNAH_MARKE = "SCHLUSSNAH|"
SEKTORAUF_MARKE = "SEKTORAUF|"
TEIL_MARKE = "TEIL|"
# Eigenes Vorzeichen im Meldeschluessel: Ein uebersprungener Kaufpunkt
# ist ein ANDERES Ereignis als ein sauberer Ausbruch und darf dessen
# Gedaechtnis nicht belegen.
UEBERSPRUNGEN_MARKE = "UEBER|"

# SAMMELFENSTER. Nach der ersten Kursmeldung wird kurz nachgefasst, damit
# gleichzeitig gerissene Kaufpunkte in EINER Push-Meldung landen statt in
# zwanzig einzelnen — das passiert vor allem in den ersten Minuten nach
# der Eroeffnung. Der Preis dafuer ist genau diese halbe Sekunde.

# In den Push-Meldungen werden Strategienamen ausgeschrieben (Mathias,
# 23.07.2026). In Excel und VOL_FAKTOR bleibt die Kurzform bestehen.
STRATEGIE_VOLL = {
    "VCP": "Volatility Contraction Pattern",
}


def meldungskopf(ticker: str, firma: str) -> str:
    """Erste Zeile jeder Meldung: Kürzel zuerst, Firmenname in Klammern."""
    firma = (firma or "").strip()
    return f"{ticker} ({firma})" if firma else ticker


def kopfzeile(ticker: str, firma: str, rest: str) -> str:
    """Die Kopfzeile einer Meldung: Kürzel, Firma, Muster — und ganz
    hinten der Zahlen-Termin, wenn HEUTE welche kommen.

    Mathias am 13.08.2026: "Schreib bitte bei Aktien, die am gleichen Tag
    Quartalszahlen bringen, den Hinweis 'bringt heute Quartalszahlen' in
    den Kopf der Meldung dazu."

    WARUM AM ENDE DER ZEILE und nicht direkt hinter dem Kürzel: Der Satz
    ist beim Vorlesen der Schlusspunkt der Kopfzeile und trennt nicht das
    Kürzel vom Muster, das ja der Grund der Meldung ist. Er steht damit
    trotzdem in der ERSTEN Zeile und wird als eines der ersten Dinge
    angesagt.

    Diese Funktion ist die EINZIGE Stelle, an der eine Kopfzeile gebaut
    wird — sonst trüge sie den Vermerk in der einen Meldungsform und in
    der anderen nicht."""
    zeile = f"{meldungskopf(ticker, firma)}; {rest}"
    vermerk = zahlen_termine.kopf_hinweis(ticker)
    return f"{zeile}; {vermerk}" if vermerk else zeile


def termin_nachsatz(ticker: str) -> str | None:
    """Was die Kopfzeile NICHT schon gesagt hat, oder None.

    Steht heute etwas an, trägt die Kopfzeile es bereits; hier bleibt
    dann nur der Vorbehalt, falls die beiden Quellen uneinig sind.
    Sonst der volle Vermerk — der Termin von MORGEN etwa gehört nach
    unten, nicht in den Kopf.

    So steht keine Angabe zweimal in derselben Meldung."""
    if zahlen_termine.kopf_hinweis(ticker):
        return zahlen_termine.vorbehalt(ticker)
    h = zahlen_termine.hinweis(ticker)
    if h:
        return h
    # STUFE A der Zahlen-Karenz (Gerhards Entscheid 31.08.2026 abends):
    # Auch der Termin UEBERMORGEN (und der Montags-Termin am Freitag)
    # steht als harter Warnkopf vorn in der Meldung. Gefiltert wird
    # nichts mehr; die Warnung traegt das Urteil zu Mathias.
    return zahlen_termine.karenz_hinweis(
        ticker, CFG["zahlen_karenz"]["handelstage"])


def im_zahlen_karenzfenster(ticker) -> bool:
    """Steht der Quartalstermin binnen der Karenz-Handelstage bevor?

    STUFE A (Gerhards Entscheid vom 31.08.2026 abends, ersetzt die
    zuerst gebaute Stufe B): Diese Funktion FILTERT nichts mehr. Sie
    markiert nur noch das Logbuch-Feld zahlen_karenz, damit messbar
    bleibt, wie sich Meldungen im Terminfenster schlagen — und der
    Warnkopf laeuft ueber termin_nachsatz() in jede betroffene
    Meldung. Messgrundlage der Karenz bleibt die Forensik vom 30.08.:
    Signale mit Termin im Fenster minus 3,38 Prozent bei 25 Prozent
    Stopp-Quote gegen minus 0,83 bei 11 ohne."""
    tage = zahlen_termine.handelstage_bis(ticker)
    return (tage is not None
            and tage <= CFG["zahlen_karenz"]["handelstage"])

# --- Gap and Go (Regelwerk Kapitel 7, Power-Gap-Fassung, Juli 2026) --------
# Alle Kriterien sind PFLICHT; die Fassung ist bewusst streng ("Klasse statt
# Masse"). Das Fruehvolumen-Kriterium ist laut Regelwerk NUR live pruefbar
# und gehoert deshalb genau hierher in den Waechter, nicht in den Nachtscan.
_GAP = CFG["gap_and_go"]
GAP_MIN = _GAP["gap_min"]                    # Eroeffnung >= 7 % ueber Vortagesschluss
GAP_VOL_FAKTOR = _VOL["gap_and_go_faktor"]   # Tagesvolumen >= 5x Ø10-Tage
GAP_FRUEH_FAKTOR = 3.0      # erste halbe Stunde: >= 300 % des zeitueblichen
GAP_SCHLUSS_POS = _GAP["schluss_position_min"]
# W2 (Gerhard, 12.09.2026): Der Folgetags-Einstieg gilt nur bis 3 Prozent
# ueber dem Kaufpunkt des Luecken-Tages.
GAP_EINSTIEG_GRENZE = float(_GAP.get("einstieg_grenze", 0.03))

# FLAT BASE — welche Fassung gilt, steht in config.py und NUR dort.
#
# Mathias am 03.08.2026: "Setze bitte Kapitel 7 Original in Kraft, bis
# ggf. etwas anderes beschlossen wird." Damit gilt der aeltere Entwurf
# (63 Tage Fenster, Spanne bis 35 %, keine Bedingung an gleitende
# Durchschnitte). Fassung A vom 28.07.2026 steht unveraendert daneben
# und ist mit einer Zeile wieder scharf zu stellen.
#
# Der Grund steht ausfuehrlich in config.py: Mit Fassung A haette Gap
# and Go in acht Monaten kein einziges Mal ausgeloest, und der Engpass
# war nicht das Volumen, sondern genau diese Basis.
_FASSUNG = _GAP["flat_base"][_GAP["flat_base_fassung"]]
FLAT_BASE_TAGE = int(_FASSUNG["tage"])
FLAT_BASE_MAX_SPANNE = float(_FASSUNG["max_spanne"])
FLAT_BASE_MA = tuple(_FASSUNG["ma"])                 # leer = keine Bedingung


# ---------------------------------------------------------------------------
# Zustand (was wurde schon gemeldet)
# ---------------------------------------------------------------------------

# Die Volumenrechnung liegt seit 28.07.2026 GESCHLOSSEN in volumen.py
# (Gerhards Vorgabe: ein Modul fuer Scanner, Waechter und Gap-and-Go,
# damit nie wieder zwei Stellen mit verschiedenen Fenstern rechnen).
# Diese beiden Huellen bleiben nur, weil der uebrige Waechter sie an
# vielen Stellen aufruft.


def tagesanteil(ticker=None, jetzt=None):
    """Welcher Anteil des Tagesvolumens ist zu dieser Uhrzeit ueblicherweise
    schon gehandelt — nach der EIGENEN Kurve DIESER Aktie?

    Vor Handelsbeginn und nach Schluss 1,0, damit die Hochrechnung dann
    nichts mehr veraendert; dafuer braucht es keine Kurve.
    None heisst: nicht verifizierbar, weil diese Aktie keine eigene Kurve
    hat (seit 06.08.2026, Gerhard — eine geliehene gibt es nicht mehr)."""
    return volumen.tagesanteil(volumen.minute_seit_eroeffnung(jetzt),
                               volumen.kurve_fuer(ticker))


def vol_verhaeltnis(vol, avg, ticker=None, jetzt=None):
    """Das Vielfache des fuer DIESE UHRZEIT ueblichen Volumens.

    None heisst NICHT VERIFIZIERBAR und ist etwas anderes als 'nicht
    bestaetigt': Entweder fehlt der 50-Tage-Schnitt, oder diese Aktie hat
    keine eigene Volumenkurve. Geprueft und zu schwach befunden wurde in
    beiden Faellen NICHTS."""
    return volumen.verhaeltnis(vol, avg, volumen.minute_seit_eroeffnung(jetzt),
                               volumen.kurve_fuer(ticker))


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

    BOERSENFEIERTAGE kennt diese Pruefung seit 07.09.2026, und zwar ueber
    den DATENANBIETER statt ueber eine selbstgepflegte Tabelle (Mathias'
    Entscheid; Modul handelskalender.py). Vorher lief der Waechter am
    Feiertag an, meldete "Boersenstatus offen" und schickte um 09:30 die
    Befunde des Nachtlaufs hinaus, ehe der erste Kursabruf ueberhaupt
    zeigte, dass es keinen Handel gibt (Labor Day, 07.09.2026).

    Sagt der Anbieter nichts, fehlt der Schluessel oder ist er nicht
    erreichbar, bleibt es beim alten Verhalten: Dann faengt
    pruefe_handelstag den Feiertag weiterhin an den fehlenden Tageszeilen
    ab. Ein falsches "geschlossen" kostete einen ganzen Handelstag,
    deshalb wird nur eine EINDEUTIGE Auskunft beachtet."""
    try:
        from zoneinfo import ZoneInfo
        ny = ZoneInfo("America/New_York")
    except Exception:
        return True, "Zeitzone nicht verfügbar — Prüfung übersprungen"

    gestellt = jetzt is not None
    jetzt = (jetzt or datetime.now(ny)).astimezone(ny)
    if jetzt.weekday() >= 5:
        return False, f"Wochenende in New York ({jetzt:%A})"

    # Der Kalender wird NUR im echten Betrieb gefragt. Wer eine Uhrzeit
    # uebergibt, prueft die Uhrenlogik (gesamtpruefung.py) und soll dabei
    # nicht ins Netz greifen. Die Auskunft selbst wird je Tag einmal
    # geholt und danach gemerkt, der Prueftakt von zwei Sekunden kostet
    # also keinen einzigen zusaetzlichen Abruf.
    if not gestellt and handelskalender.handelstag(jetzt) is False:
        return False, handelskalender.kein_handel_text()

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

    Liefert None am Wochenende, nach der Eroeffnung oder ohne Zeitzone —
    und seit 07.09.2026 auch an einem Tag, an dem der Datenanbieter gar
    keinen Handel meldet. Ohne diese Ergaenzung haette der Waechter am
    Feiertag brav auf eine Glocke gewartet, die nie laeutet.
    Gebraucht fuer die Eroeffnungs-Abdeckung: GitHub feuert Zeitplaene oft
    5-15 Minuten verspaetet — ein Lauf, der kurz VOR der Glocke startet,
    wartet damit bis zur Eroeffnung, statt sich schlafen zu legen."""
    try:
        from zoneinfo import ZoneInfo
        ny = ZoneInfo("America/New_York")
    except Exception:
        return None
    gestellt = jetzt is not None
    jetzt = (jetzt or datetime.now(ny)).astimezone(ny)
    if jetzt.weekday() >= 5:
        return None
    if not gestellt and handelskalender.handelstag(jetzt) is False:
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

# Der Sektor-Radar-Befund wird je HANDELSTAG einmal gemeldet; der Tag steht
# im Schluessel, damit er mit dem Freitags-Putz von selbst verfaellt.
SEKTOR_MARKE = "SEKTOR|"

# Insider-Funde tragen ihre eigene Kennung im Schluessel, damit ein
# waechsender Cluster (drei Insider, spaeter vier) erneut gemeldet
# wird, derselbe Stand aber nicht.
INSIDER_MARKE = "INSIDER|"

# LUECKEN-BESTAETIGUNGSTAG: DER KAUF GEHOERT DEM FOLGETAG (Mathias,
# 11.09.2026). Unter diesem Schluessel steht im Zustand die Warteliste der
# gemeldeten Luecken-Tage; die ganze Begruendung steht bei gapgo_vormerken().
GAPGO_WARTEN = "gapgo_warten"
# Der Einstieg am Folgetag ist eine EIGENE Meldung und braucht daher einen
# eigenen Merker im Melde-Gedaechtnis.
GAPGO_EIN_MARKE = "GAPGOIN|"
GAPGO_UEBER_MARKE = "GAPGOUEBER|"   # W2: Einstieg ueber der 3-Prozent-Grenze
# Wie lange ein vorgemerktes Signal hoechstens auf seinen Einstiegstag
# wartet, in Kalendertagen. VIER, damit ein Freitagssignal seinen ersten
# Handelstag auch dann noch findet, wenn der Montag ein Feiertag ist.
# Gehandelt wird ausschliesslich am ERSTEN Wachtag nach dem Signal (Feld
# "pruef"); die Tagezahl ist nur der Schutz gegen Eintraege, die liegen
# bleiben, weil der Waechter einen Tag nicht gelaufen ist.
GAPGO_WARTE_TAGE = 4


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


def _staat_aus(pfad) -> dict:
    """Eine Zustandsdatei lesen, leer bei jedem Fehler."""
    try:
        return json.loads(Path(pfad).read_text())
    except Exception:
        return {}


def _gemeldet_filtern(gemeldet: dict, heute: str) -> dict:
    """Die Fristen des Melde-Gedaechtnisses, an EINER Stelle.

    Drei Fristen, je nach Vorzeichen im Schluessel:
      HTF|      taeglich (Gerhard, 29.07.2026)
      INSIDER|  30 Tage — AUSDRUECKLICH NICHT der Freitags-Putz (Mathias,
                18.08.2026: "bereits erfolgte Meldungen sollen nicht
                wieder angezeigt werden"). Ein Insider-Fund bleibt bis zu
                zehn Handelstage im Fenster; mit der Wochenfrist waere
                derselbe Grosskauf am Montag der Folgewoche wieder
                gemeldet worden. 30 Tage ueberdauern jedes Fenster.
      sonst     Wochenfrist bis zum letzten Freitags-Putz.
    """
    grenze = letzter_putz()
    grenze_htf = htf_grenze()
    grenze_insider = (date.today() - timedelta(days=30)).isoformat()
    raus = {}
    for k, d in gemeldet.items():
        k_s, d_s = str(k), str(d)
        if INSIDER_MARKE in k_s:
            if d_s > grenze_insider:
                raus[k_s] = d_s
        elif HTF_MARKE in k_s:
            if d_s > grenze_htf:
                raus[k_s] = d_s
        elif d_s > grenze:
            raus[k_s] = d_s
    return raus


def _zahl(wert):
    """Eine Zahl aus dem Zustand, oder None."""
    try:
        return float(wert)
    except (TypeError, ValueError):
        return None


def _warten_vereinen(alt, neu: dict) -> dict:
    """Zwei Staende EINES vorgemerkten Luecken-Tages zusammenfuehren.

    Dieselbe Not wie beim Melde-Gedaechtnis (siehe load_state): Cache und
    Repo-Fassung koennen auseinanderlaufen, und Verlieren ist teurer als
    Behalten. Der juengere Luecken-Tag loest den aelteren ab; beim selben
    Tag gilt der HOEHERE Kaufpunkt (er wird im Tagesverlauf nachgezogen),
    der juengere Stop, die erfolgte Schlussbestaetigung und der FRUEHERE
    Pruef-Tag (ein spaeterer wuerde den Verfall hinausschieben)."""
    if not isinstance(neu, dict):
        return alt if isinstance(alt, dict) else {}
    if not isinstance(alt, dict) or not alt:
        return dict(neu)
    a, n = str(alt.get("signal") or ""), str(neu.get("signal") or "")
    if n > a:
        return dict(neu)
    if n < a:
        return dict(alt)
    zus = dict(alt)
    zus.update({k: v for k, v in neu.items() if v is not None})
    kp = [x for x in (_zahl(alt.get("kp")), _zahl(neu.get("kp")))
          if x is not None]
    if kp:
        zus["kp"] = max(kp)
    zus["bestaetigt"] = (bool(alt.get("bestaetigt"))
                         or bool(neu.get("bestaetigt")))
    pruef = sorted(str(p) for p in (alt.get("pruef"), neu.get("pruef")) if p)
    if pruef:
        zus["pruef"] = pruef[0]
    return zus


def _warten_filtern(warten: dict) -> dict:
    """Vorgemerkte Luecken-Tage, die noch handelbar sind.

    Alles, was laenger als GAPGO_WARTE_TAGE Kalendertage her ist, fliegt;
    ein Eintrag aus der ZUKUNFT (Zeitzonen-Wirrwarr) ebenso."""
    heute = heute_ny() or date.today()
    raus = {}
    for t, e in (warten or {}).items():
        if not isinstance(e, dict):
            continue
        try:
            tage = (heute - date.fromisoformat(str(e.get("signal")))).days
        except (TypeError, ValueError):
            continue
        if 0 <= tage <= GAPGO_WARTE_TAGE:
            raus[str(t).upper()] = e
    return raus


def _warten_laden() -> dict:
    """Die Warteliste aus BEIDEN Zustandsquellen, vereint und gefiltert."""
    warten = {}
    for quelle in (REPO_STATE, STATE_FILE):
        for t, e in (_staat_aus(quelle).get(GAPGO_WARTEN) or {}).items():
            k = str(t).upper()
            warten[k] = _warten_vereinen(warten.get(k), e)
    return _warten_filtern(warten)


def gapgo_warte_symbole() -> set:
    """Aktien, die auf ihren Einstiegstag warten.

    Sie brauchen HEUTIGE Kurse, auch wenn die Mappe sie inzwischen nicht
    mehr fuehrt: Der Scanner schreibt sie jede Nacht neu, und ohne Kurs
    gaebe es am Einstiegstag nichts zu pruefen. Dieselbe Vorsorge wie
    nacht_symbole() fuer die Nachtbefunde."""
    return set(_warten_laden())


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
    # ZWEI QUELLEN, VEREINIGT (18.08.2026, nach dem Montags-Befund):
    #   1. Der Actions-Cache (STATE_FILE nach dem Wiederherstellen).
    #   2. Die im Repo eingecheckte Fassung (REPO_STATE) — die schreibt
    #      der laufende Waechter nach jeder Meldung sofort ins Repo.
    #
    # WARUM: Der Cache wird erst am LAUFENDE gesichert. Die Schlussstunde
    # startet um 21:26, die Tagwache sichert um 21:28 — die Schlussstunde
    # bekam also an JEDEM Handelstag den Stand vom Vortag und meldete den
    # halben Tag neu. Am 17.08.2026 nachgewiesen: Beide Laeufe stellten
    # denselben Cache der FREITAG-Schlussstunde wieder her
    # (watcher-state-31833222867); der Insider-Grosskauf RSG und zehn
    # Ausbrueche kamen doppelt. Der Checkout dagegen ist beim Start
    # frisch und enthaelt alles, was der Vorgaenger IM Lauf committet
    # hat. Union statt Vorrang: Verlieren ist teurer als Behalten.
    gemeldet, fenster = {}, {}
    for quelle in (REPO_STATE, STATE_FILE):
        data = _staat_aus(quelle)
        g = data.get("gemeldet", {})
        if isinstance(g, list):        # Altes Tagesformat einmalig
            g = {k: data.get("tag", heute) for k in g}
        gemeldet.update(g)
        # DAS FENSTER-GEDAECHTNIS gilt nur fuer DIESEN Handelstag
        # (Mathias, 13.08.2026) — gestrige Zustaende sagen nichts mehr.
        # M4, MOEGLICHKEIT 2 (Gerhard, 12.09.2026): Der Fensterzustand
        # bleibt UEBER NACHT erhalten, ein Wiedereintritt laeuft nur ueber
        # die Totzone; das erhaelt die acht echten Faelle aus W1. Er
        # verfaellt erst mit dem Freitags-Putz, wie die Meldungen, weil
        # dann die neue Wochenliste gilt. (Bis 12.09.2026 galt er nur fuer
        # den laufenden Handelstag.)
        if str(data.get("fenster_tag") or "") > letzter_putz():
            fenster.update(data.get("fenster", {}))
    # DIE WARTELISTE der Luecken-Bestaetigungstage muss den TAGESWECHSEL
    # ueberleben, denn ihr Einstieg liegt im Folgetag. Sie kommt aus
    # denselben zwei Quellen und wird hier ausdruecklich mitgeladen: Dieses
    # Dict wird frisch gebaut, ein nicht genannter Schluessel waere beim
    # naechsten Speichern weg.
    return {"fenster_tag": heute, "fenster": fenster,
            "gemeldet": _gemeldet_filtern(gemeldet, heute),
            GAPGO_WARTEN: _warten_laden()}


_repo_stand = {"keys": None, "zeit": 0.0}


def _repo_sichern(state: dict, sofort: bool = False):
    """Das Melde-Gedaechtnis SOFORT ins Repo — best effort.

    Der Actions-Cache sichert erst am Laufende und kommt fuer die
    Uebergabe zu spaet (siehe load_state). Deshalb committet der Waechter
    nach jeder Meldung; die Schlussstunde findet den Stand dann im
    Checkout vor. Gedrosselt auf eine Sicherung je 60 Sekunden und nur
    bei veraenderter Meldungsmenge; jeder Fehler ist eine Protokollzeile
    und KEIN Abbruch — im Zweifel greift der Endkommit des Workflows."""
    # DIE WARTELISTE ZAEHLT MIT (11.09.2026): Ein vorgemerkter Luecken-Tag
    # aendert die MELDUNGS-Menge nicht, muss aber ins Repo — sein Einstieg
    # wird erst am Folgetag geprueft, und der Actions-Cache ist zwischen
    # zwei Laeufen desselben Tages veraltet (siehe load_state).
    keys = frozenset(state.get("gemeldet", {})) | frozenset(
        "%s|%s|%s" % (t, e.get("signal"), e.get("kp"))
        for t, e in (state.get(GAPGO_WARTEN) or {}).items()
        if isinstance(e, dict))
    jetzt = time.time()
    # sofort (seit 10.09.2026, Nachtbefunde): ohne die Minutendrossel, weil
    # die Melde-Merker in positionen.json stehen und der Endkommit des
    # Workflows diese Datei nicht sichert.
    # BEI "sofort" ZAEHLT AUCH EINE UNVERAENDERTE MELDUNGS-MENGE (Befund
    # 12.09.2026): Ein EXIT der Tagesgeschaeft-Wache legt keinen neuen
    # Melde-Merker an, er schliesst nur eine Beobachtung in
    # positionen.json. Die Menge blieb damit gleich, der Abbruch hier
    # griff, und der Endkommit des Workflows sichert positionen.json
    # nicht: Der geschlossene Zustand war nach dem Lauf weg. Belegt am
    # Fall RCUS — die Exit-Meldung ging am 11.09.2026 um 15:47 hinaus, die
    # Beobachtung stand danach im Repo weiter OFFEN und haette denselben
    # Ausstieg am naechsten Handelstag erneut gemeldet.
    if (not sofort and (keys == _repo_stand["keys"]
                        or jetzt - _repo_stand["zeit"] < 60)):
        return
    _repo_stand["keys"] = keys
    _repo_stand["zeit"] = jetzt
    try:
        Path(REPO_STATE).write_text(json.dumps(state, indent=2))
        import shutil
        import subprocess
        import tempfile
        g = ["git", "-c", "user.name=breakout-watcher",
             "-c", "user.email=actions@users.noreply.github.com"]
        # R9 und M6 (12.09.2026): gruene Minuten und die um 15:45 gemeldeten
        # Befunde gehen denselben Weg; nur vorhandene Dateien, sonst weist
        # git add den ganzen Aufruf ab.
        dateien = [d for d in (REPO_STATE, "positionen.json", GRUEN_DATEI,
                               SCHLUSSNAH_DATEI) if Path(d).exists()]
        subprocess.run(g + ["add"] + dateien,
                       capture_output=True, timeout=30)
        r = subprocess.run(g + ["commit", "-m",
                                "Melde-Gedächtnis (im Lauf gesichert)"],
                           capture_output=True, timeout=30)
        if r.returncode != 0:
            return                     # nichts zu committen
        # KEINE STASH-KOLLISION MEHR (Befund 10.09.2026, belegt am 18.08.
        # und am 31.08.2026). Logbuch und ntfy-Kennungen haengt der Lauf nur
        # an, ins Repo gehen sie erst mit dem Endkommit. Lagen sie beim Pull
        # veraendert herum, stellte --autostash sie beiseite und spielte sie
        # nach dem Rebase zurueck. Hatte der Serverstand dieselbe Datei
        # inzwischen ebenfalls verlaengert, schrieb Git Konfliktmarken
        # hinein, und zwar OHNE Fehlercode; der Endkommit legte sie ins
        # Repo. Deshalb stehen beide Dateien beim Pull auf dem letzten
        # Commit und werden danach wieder vereint, Zeile fuer Zeile und
        # Kennung fuer Kennung, wie im Endkommit des Workflows.
        ablage = tempfile.mkdtemp(prefix="waechter_sicherung_")
        beiseite = {}
        for datei in (trigger_logbuch.DATEI, str(ntfy_verlauf.VERLAUF_DATEI)):
            if Path(datei).exists():
                beiseite[datei] = shutil.copy(
                    datei, os.path.join(ablage, Path(datei).name))
        try:
            for datei in beiseite:
                subprocess.run(g + ["checkout", "--", datei],
                               capture_output=True, timeout=30)
            pull = subprocess.run(g + ["pull", "--rebase", "--autostash",
                                       "origin", "main"],
                                  capture_output=True, timeout=60)
            if pull.returncode != 0:
                # Ein haengengebliebenes Rebase legte jede weitere
                # Sicherung dieses Laufs lahm. Also zurueck auf den eigenen
                # Commit; den Rest holt der Endkommit nach.
                subprocess.run(g + ["rebase", "--abort"],
                               capture_output=True, timeout=30)
        finally:
            if trigger_logbuch.DATEI in beiseite:
                trigger_logbuch.vereinen(beiseite[trigger_logbuch.DATEI])
            ntfy_datei = str(ntfy_verlauf.VERLAUF_DATEI)
            if ntfy_datei in beiseite:
                ntfy_verlauf.vereine(beiseite[ntfy_datei])
            shutil.rmtree(ablage, ignore_errors=True)
        p = subprocess.run(g + ["push", "origin", "main"],
                           capture_output=True, timeout=60)
        if p.returncode != 0:
            print("  Melde-Gedächtnis: Push ins Repo fehlgeschlagen — "
                  "der Endkommit des Laufs holt es nach.")
    except Exception as e:
        print(f"  Melde-Gedächtnis: Repo-Sicherung übersprungen ({e}).")


_GRUEN: dict = {}


def gruen_laden(heute_s: str) -> dict:
    """R9 (Gerhard, 12.09.2026): Je Aktie, in wie vielen Datenabrufen des
    Tages der Kurs ueber dem Vortagesschluss lag (ein Abruf je Minute). Der
    Abendbericht braucht "mindestens 80 Prozent der Minuten im Plus". Die
    Schlussstunde uebernimmt die Zaehlung der Tagwache aus dem Repo."""
    global _GRUEN
    d = _staat_aus(GRUEN_DATEI)
    if str(d.get("tag") or "") == heute_s and isinstance(d.get("aktien"), dict):
        _GRUEN = d
    else:
        _GRUEN = {"tag": heute_s, "aktien": {}}
    return _GRUEN


def gruen_zaehlen(quotes: dict):
    if not _GRUEN:
        return
    aktien = _GRUEN.setdefault("aktien", {})
    for t, q in quotes.items():
        c, p = q.get("close"), q.get("prev_close")
        if not c or not p or c != c or p != p:
            continue
        z = aktien.setdefault(str(t).upper(), [0, 0])
        z[1] += 1
        if float(c) > float(p):
            z[0] += 1


def gruen_schreiben():
    if not _GRUEN:
        return
    try:
        Path(GRUEN_DATEI).write_text(json.dumps(_GRUEN))
    except Exception as e:
        print(f"Gruene Minuten nicht gespeichert: {e}")


def save_state(state: dict, sofort: bool = False):
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception as e:
        print(f"Zustand konnte nicht gespeichert werden: {e}")
    gruen_schreiben()
    _repo_sichern(state, sofort)


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
            # DER KURS AUS DER MAPPE ist der Schlusskurs des Vortags: Der
            # Nachtlauf rechnet um 00:07 Wiener Zeit, also nach dem New
            # Yorker Schluss. Nachgemessen am 14.08.2026 an fuenf Aktien
            # gegen die echten Schlusskurse: null Abweichung (TEAM 165,98
            # gegen 165,98, ETON 40,80 gegen 40,80 und so weiter), gefuellt
            # bei 235 von 235. Er dient als zweite Quelle fuer
            # kam_von_unten(), siehe vortagesschluss().
            kurs_scan = row.get("Kurs")
            items.append({
                "ticker": ticker,
                "firma": firma,
                "nr": i,
                "strategie": strat,
                "kaufpunkt": float(preis),
                "kurs_scan": (None if kurs_scan is None or pd.isna(kurs_scan)
                              else float(kurs_scan)),
                "stop": None if pd.isna(stop) else float(stop),
                "ziel": None if (ziel is None or pd.isna(ziel) or ziel == "") else float(ziel),
            })
    return _lege_gleiche_preise_zusammen(_deckel_nachziehen(items))


def _deckel_nachziehen(items: list[dict]) -> list[dict]:
    """SCHUTZNETZ: Den Zehn-Prozent-Deckel auf jeden eingelesenen Stop.

    Zustaendig ist eigentlich der Scanner — seit 06.08.2026 deckelt er
    jeden Kaufpunkt, bevor er in die Mappe geht. Der Waechter liest die
    Mappe aber auch dann, wenn sie von einem aelteren Lauf stammt, und
    genau so entstand der Fehler: 344 von 1098 Paaren mit einem Risiko
    ueber dem Deckel, bis zu 73,2 %.

    ABSICHTLICH KORRIGIEREND STATT ABBRECHEND. Gerhard wollte eine
    Assertion, die feuert, bevor eine Meldung rausgeht; die sitzt in
    exit_regeln.risiko_pct() und bleibt scharf. Sie hier hart werfen zu
    lassen haette aber den GANZEN Handelstag fuer ALLE Aktien beendet,
    weil eine einzige alte Zeile in der Mappe steht. Der Waechter zieht
    den Stop deshalb selbst nach, sagt laut, welche Zeilen betroffen
    waren, und meldet weiter. Danach kann risiko_pct() nicht mehr
    ausloesen, ohne dass wirklich etwas kaputt ist."""
    korrigiert = []
    for it in items:
        _, geaendert = exit_regeln.deckel_anwenden(it)
        if geaendert:
            korrigiert.append(it)
    if korrigiert:
        print(f"  ⚠ {len(korrigiert)} Stop(s) aus der Mappe lagen weiter als "
              f"{CFG['exit']['stop_deckel_pct']*100:.0f} % unter dem Kaufpunkt "
              f"und wurden nachgezogen (die Mappe ist älter als der Scanner):")
        for it in sorted(korrigiert,
                         key=lambda x: -(x["kaufpunkt"] - x["stop_struktur"])
                         / x["kaufpunkt"])[:10]:
            alt = (it["kaufpunkt"] - it["stop_struktur"]) / it["kaufpunkt"] * 100
            print(f"      {it['ticker']:6s} {it['strategie'][:24]:24s} "
                  f"Kaufpunkt {it['kaufpunkt']:.2f}; Stop {it['stop_struktur']:.2f} "
                  f"({alt:.1f} %) auf {it['stop']:.2f} nachgezogen")
        if len(korrigiert) > 10:
            print(f"      … und {len(korrigiert) - 10} weitere.")
    return items


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
    td_budget = TD_JE_RUNDE
    for t in unique:
        try:
            # AUCH EIN EINZELNER TICKER kommt verschachtelt (Befund
            # 09.09.2026, nachgemessen mit yfinance 1.5.1): Die Spalten
            # heissen dann (Ticker, Feld). Die fruehere Weiche "nur bei
            # mehreren Tickern auspacken" liess den Einzelabruf des Nasdaq
            # fuer Red-to-Green deshalb IMMER leer ausgehen.
            roh_df = (roh[t] if isinstance(roh.columns, pd.MultiIndex)
                      else roh)
            df, verbraucht = hohle_kerze_fuellen(t, roh_df, td_budget)
            td_budget -= verbraucht
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
            # LEERE KERZEN VERWERFEN (18.08.2026, gemessen): Yahoo
            # lieferte am Dienstag fuer viele mittelgrosse Aktien die
            # Montagszeile MIT Datum, aber ohne Werte (alles NaN) - um
            # 00:04 waren die Werte noch da, vormittags waren sie
            # rueckwirkend leer. Ohne dropna wird prev_close zu NaN, und
            # NaN ist in Python WAHR: Es laeuft als "vorhandener"
            # Vortagesschluss durch, jede Vergleichslogik (Gap,
            # Red-to-Green, kam_von_unten) wird still falsch.
            # Sind ALLE Vortage leer, fehlen nur die Zusatzfelder - die
            # Aktie selbst bleibt beobachtet, und vortagesschluss() greift
            # auf den Kurs aus der Mappe zurueck.
            vortage = (df.iloc[:-1].dropna(subset=["Close"])
                       if len(df) >= 2 else df.head(0))
            if len(vortage):
                eintrag["prev_close"] = float(vortage["Close"].iloc[-1])
                # Von welchem Tag stammt dieser Vortagesschluss? Damit
                # prueft der Waechter, ob die Nachtbefunde zu den heutigen
                # Kursen gehoeren (Mathias, 10.09.2026).
                eintrag["prev_datum"] = vortage.index[-1].date()
                # R18, R19 (Gerhard, 12.09.2026): die 8er- und die 21er-
                # Exponentiallinie auf Tagesbasis bis GESTERN; den heutigen
                # Wert schreibt ema_felder() aus dem Live-Kurs fort.
                if len(vortage) >= 21:
                    eintrag["ema8_vortag"] = float(
                        vortage["Close"].ewm(span=8, adjust=False).mean().iloc[-1])
                    eintrag["ema21_vortag"] = float(
                        vortage["Close"].ewm(span=21, adjust=False).mean().iloc[-1])
                # WAR fest auf 10 verdrahtet, waehrend der Ausbruch schon
                # gegen ein anderes Fenster rechnete. Genau solche stillen
                # Uneinheitlichkeiten sollte Gerhards Umbau vom 28.07.2026
                # beenden — jetzt zieht auch Gap and Go seinen Massstab aus
                # config.py.
                eintrag["vol50"] = float(
                    vortage["Volume"].tail(VOL_FENSTER).mean())
                for feld, spalte in (("open", "Open"), ("high", "High"),
                                     ("low", "Low")):
                    wert = letzte.get(spalte)
                    eintrag[feld] = None if pd.isna(wert) else float(wert)
                # FLAT BASE in der geltenden Fassung (siehe config.py):
                # das Fenster vor dem Gap-Tag, seine hoechstzulaessige
                # Spanne und — nur in Fassung A — die Bedingung, dass der
                # Kurs ueber MA10 und MA21 liegt. Im Original ist die
                # Liste der Durchschnitte leer, die Schleife laeuft dann
                # gar nicht und ueber_ma bleibt True.
                fenster = vortage.tail(FLAT_BASE_TAGE)
                if len(fenster) >= FLAT_BASE_TAGE:
                    tief = float(fenster["Low"].min())
                    if tief > 0:
                        spanne = (float(fenster["High"].max()) - tief) / tief
                        eintrag["base_spanne"] = spanne
                        flach = hoechstens(spanne, FLAT_BASE_MAX_SPANNE)
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

def ema_felder(q: dict) -> dict:
    """R18 (Gerhard, 12.09.2026, NUR ANZEIGE): EMA 8 und 21 auf Tagesbasis,
    heute aus dem Live-Kurs fortgeschrieben (EMA = a mal Kurs plus (1 minus a)
    mal EMA von gestern, a = 2 durch (n plus 1))."""
    try:
        kurs = float(q.get("close") or 0)
        e8, e21 = q.get("ema8_vortag"), q.get("ema21_vortag")
        if not kurs or e8 is None or e21 is None:
            return {}
        return {"ema8": 2.0 / 9.0 * kurs + 7.0 / 9.0 * float(e8),
                "ema21": 2.0 / 22.0 * kurs + 20.0 / 22.0 * float(e21)}
    except (TypeError, ValueError):
        return {}


def ema_lage_text(t: dict) -> str:
    e8, e21 = t.get("ema8"), t.get("ema21")
    if e8 is None or e21 is None:
        return ""
    return ("EMA 8 über 21 auf Tagesbasis" if e8 > e21
            else "EMA 8 unter 21 auf Tagesbasis")


_ZUSATZ: dict = {}


def _zusatz_daten() -> dict:
    """RS-Universum, Sektor-Rangliste und Ratings, einmal je Lauf gelesen
    (die Dateien schreibt der Nachtscan ins Repo)."""
    if not _ZUSATZ:
        import importlib
        for name, modul in (("rs", "rs_universum"), ("sektor", "sektor_rangliste"),
                            ("ratings", "ibd_ratings")):
            try:
                m = importlib.import_module(modul)
                _ZUSATZ[name] = (m, m.lies())
            except Exception as e:
                print(f"  {modul}: nicht verfügbar ({type(e).__name__})")
                _ZUSATZ[name] = None
    return _ZUSATZ


def zusatz_zeile(ticker) -> str:
    """R4 bis R6, R16, R20 (Gerhard, 12.09.2026): RS, Sektorrang und Ratings
    als EINE Zeile in jeder Meldung. Entscheidungshilfe, kein Filter."""
    d = _zusatz_daten()
    teile = []
    try:
        if d.get("rs"):
            z = d["rs"][0].anzeige(ticker, d["rs"][1])
            if z:
                teile.append(z)
        if d.get("sektor"):
            z = d["sektor"][0].sektor_zeile(ticker, d["sektor"][1])
            if z:
                teile.append(z)
        if d.get("ratings"):
            z = d["ratings"][0].zeile(ticker, d["ratings"][1])
            if z:
                teile.append(z)
    except Exception as e:
        print(f"  Zusatzzeile {ticker}: {type(e).__name__}: {e}")
    return "; ".join(teile)


def zusatz_logbuch(ticker) -> dict:
    """Punkt 4 (Gerhard, 12.09.2026): RS-Wert, Sektorrang und Ratings
    wandern mit jedem Signal ins Trigger-Logbuch."""
    d = _zusatz_daten()
    raus = {}
    try:
        if d.get("rs"):
            e = d["rs"][0].eintrag(ticker, d["rs"][1]) or {}
            raus.update({"rs_nasdaq": e.get("rs"),
                         "rs_linie_spy_hoch": e.get("linie_spy_hoch")})
        if d.get("sektor"):
            import listen
            etf = beobachtungen.sektor_etf_fuer(listen.sektor_von(ticker))
            z = next((x for x in (d["sektor"][1].get("liste") or [])
                      if x.get("etf") == etf), None)
            raus.update({"sektor_etf": etf, "sektor_rang": (z or {}).get("rang")})
        if d.get("ratings"):
            e = ((d["ratings"][1].get("aktien") or {})
                 .get(str(ticker or "").upper()) or {})
            raus.update({"ibd_eps": e.get("eps"), "ibd_smr": e.get("smr"),
                         "ibd_ad": e.get("ad"), "ibd_composite": e.get("composite")})
    except Exception:
        pass
    return raus


def pruefe_breakout(item: dict, quote: dict) -> dict | None:
    """Prüft, ob der Kaufpunkt gerissen wurde. Gibt Treffer-Info zurück oder None."""
    kurs = quote["close"]
    kp = item["kaufpunkt"]
    if kurs < kp:
        return None  # Kaufpunkt noch nicht erreicht

    # ZU WEIT DRUEBER: kein sauberer Einstieg mehr.
    #
    # Bis 11.08.2026 endete die Pruefung hier mit None, der Fall war also
    # unsichtbar. Gerhard hat gefragt, warum Sea nichts gemeldet hat: Die
    # Aktie eroeffnete am 11.08. mit 127,87 und damit 10,3 % ueber ihrem
    # Kaufpunkt von 115,91 — keine einzige der 78 Fuenf-Minuten-Kerzen des
    # Tages lag im Meldefenster. Die Aktie ist ueber den Kaufpunkt hinweg
    # eroeffnet worden.
    #
    # Die Grenze bleibt, denn sie ist richtig: Wer bei 127,87 einsteigt,
    # waehrend der Stop bei 104,32 liegt, traegt 18 % Risiko statt der
    # geplanten zehn. Aber STILL bleiben soll der Fall nicht mehr. Er
    # bekommt eine EIGENE Meldung, ausdruecklich kein Kaufsignal, sondern
    # die Auskunft "hier ist etwas passiert, und zwar ohne dich".
    ueber = kurs / kp - 1
    if ueber > NACHLAUF_GRENZE:
        if not MELDE_UEBERSPRUNGENE:
            return None
        return {**item, "kurs": kurs, "ueber_pct": ueber * 100,
                "uebersprungen": True,
                # Fuer kam_von_unten(): Lag der Kurs GESTERN noch unter
                # dem Kaufpunkt? Nur dann ist hier etwas passiert.
                "vortagesschluss": vortagesschluss(item, quote),
                # Kein Volumenurteil: Ob das Volumen stimmt, aendert
                # nichts daran, dass der Einstieg vorbei ist. Eine
                # Volumenzahl wuerde die Meldung wie ein Signal aussehen
                # lassen, und genau das ist sie nicht.
                "vol_ratio": None, "vol_pct": None, "vol_ok": None,
                "vol_noetig": VOL_FAKTOR.get(item["strategie"],
                                             VOL_FAKTOR_FALLBACK),
                "vol_anteil": None, "vol_roh": quote.get("volume"),
                "vol_nicht_verifizierbar": False, **ema_felder(quote)}

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
    #
    # DIE KURVE GEHOERT DER AKTIE (Gerhard, 06.08.2026): F(t) kommt aus
    # der eigenen 50-Tage-Historie GENAU DIESER Aktie. Hat sie keine
    # (unter 40 Handelstagen), ist das Volumen NICHT VERIFIZIERBAR — ein
    # eigener, dritter Status neben bestaetigt und nicht bestaetigt.
    anteil = tagesanteil(item["ticker"])
    vol_ratio = vol_verhaeltnis(vol, avg, item["ticker"])
    if vol_ratio is None:
        # Warum keine Zahl? Fehlt der 50-Tage-Schnitt oder die eigene
        # Kurve? Die Meldung soll das benennen koennen.
        vol_ok = None
        nicht_pruefbar = (volumen.kurve_fuer(item["ticker"]) is None
                          and volumen.minute_seit_eroeffnung() is not None)
    else:
        vol_ok = vol_ratio >= faktor
        nicht_pruefbar = False

    return {
        **item,
        "kurs": kurs,
        "ueber_pct": ueber * 100,
        # FUER riss_schon_gestern() UND fallback_ohne_riss(): Lag der Kurs
        # gestern noch unter dem Kaufpunkt? Bis 12.09.2026 stand der
        # Vortagesschluss NUR am uebersprungenen Treffer (oben), der
        # gewoehnliche trug ihn nicht. fallback_ohne_riss() fragte hier
        # also einen fehlenden Wert ab und hielt damit JEDE Ausweich-Marke
        # fuer "heute nicht gerissen" - sie konnte im Meldefenster gar
        # nicht mehr melden. GEMESSEN am Trigger-Logbuch: Seit dem Einbau
        # der Ausweich-Marken am 19.08.2026 stammen ALLE 37 Fallback-
        # Eintraege aus dem Weg "uebersprungen", kein einziger aus dem
        # gewoehnlichen Ausbruchsweg - genau die Meldungen, die der
        # AEHR-Befund vom 19.08. haben wollte, blieben still.
        "vortagesschluss": vortagesschluss(item, quote),
        "vol_ratio": vol_ratio,
        "vol_pct": None if vol_ratio is None else (vol_ratio - 1) * 100,
        "vol_noetig": faktor,
        "vol_ok": vol_ok,
        "vol_nicht_verifizierbar": nicht_pruefbar,
        "vol_roh": vol,
        "vol_anteil": anteil,
        **ema_felder(quote),
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
    3. Flat Base davor, in der GELTENDEN Fassung (config.py, derzeit
       Kapitel 7 im Original: 63 Handelstage, Spanne bis 35 %, keine
       Bedingung an gleitende Durchschnitte)
    4. Volumen: in der ersten halben Stunde >= 300 % des zeitueblichen
       Werts (Fruehregel, laut Regelwerk NUR live pruefbar); danach
       hochgerechnetes Tagesvolumen >= 5x Ø10-Tage
    5. Zum Handelsende zusaetzlich: Schluss im oberen Fuenftel der
       Tagesspanne UND rohes Tagesvolumen >= 5x Ø10 -> 'BESTÄTIGT'
    Kaufpunkt = Tageshoch + 1 Cent (Einstieg am Folgetag).

    STOP = das WEITERE von Tagestief - 1 Cent und Kaufpunkt x 0,97,
    also min() der beiden. Hier stand bis zum 03.08.2026 "das engere",
    was dem Code widersprach — der Code hatte recht. Gemessen an 105
    echten Gap-and-Go-Handeln aus 24 Monaten: Der Stop liegt so im
    Median 11,5 % unter dem Einstieg, und das ist gut so. Die engere
    Lesart (Kaufpunkt x 0,97, also 3 %) haette 74 % aller Handel
    ausgestoppt und die Trefferquote nach 20 Tagen von 50 auf 25 %
    halbiert. Der Zusatz x 0,97 ist also KEINE Risikodeckelung, sondern
    ein Mindestabstand fuer Tage mit kleiner Spanne."""
    open_, high, low = q.get("open"), q.get("high"), q.get("low")
    prev, vol50 = q.get("prev_close"), q.get("vol50")
    kurs, vol = q.get("close"), q.get("volume")
    if None in (open_, high, low, prev, kurs, vol) or not vol50 or prev <= 0:
        return None
    gap = open_ / prev - 1
    if not mind_erreicht(gap, GAP_MIN):
        return None
    if low <= prev:
        return None                      # Gap-Fill — Luecke nicht verteidigt

    # DIE FLAT BASE SCHLIESST SEIT 05.08.2026 NICHTS MEHR AUS (Gerhard,
    # nach meiner Messung). Sie kostete zwei Drittel der Signale und
    # siebte ausgerechnet die grossen Gewinner weg: Der Anteil der Handel
    # mit mindestens 20 % Gewinn lag ohne Filter bei 15 %, mit Kapitel 7
    # im Original bei 3 %, mit Fassung A bei null — in zwei Jahren kein
    # einziger. Sie laeuft jetzt als VERMERK in der Meldung mit.
    #
    # Gerhards inhaltliche Begruendung dazu: O'Neils eigene
    # Acht-Wochen-Regel sagt, dass genau die Aktien, die explosionsartig
    # aus einer Basis herausschiessen, die spaeteren Vervielfacher sind.
    # Ein Filter, der die wegschneidet, arbeitet gegen die eigene Doktrin.

    anteil = tagesanteil(ticker)
    if anteil is None or anteil <= 0:
        # Keine eigene Volumenkurve: Gap and Go laesst sich fuer diese
        # Aktie nicht pruefen. Frueher sprang hier die geliehene Kurve
        # ein; seit 06.08.2026 gibt es die nicht mehr.
        return None
    # BEIDE Zahlen sind rechnerisch dieselbe Groesse — v/(Ø×F) und
    # (v/F)/Ø. Aufgefallen beim Aufschreiben der Formel fuer Gerhard am
    # 28.07.2026; sie stehen hier getrennt, weil das Regelwerk zwei
    # verschiedene SCHWELLEN kennt (drei- statt fuenffach vor 10:00 NY),
    # nicht zwei verschiedene Messgroessen. Bis Gerhard das klaert, bleibt
    # es so, wie es das Regelwerk beschreibt.
    tages_ratio = volumen.verhaeltnis(vol, vol50,
                                      volumen.minute_seit_eroeffnung(),
                                      volumen.kurve_fuer(ticker))
    if tages_ratio is None:
        return None
    frueh_ratio = tages_ratio

    minuten = ny_minuten()
    in_frueh_phase = minuten is not None and minuten < 600     # vor 10:00 NY
    kurz_vor_schluss = minuten is not None and minuten >= 954  # ab 15:54 NY
    # Schwellenvergleiche ueber die zentrale Hilfsfunktion: Ein Wert, der
    # exakt auf der Schwelle liegt, soll sie ERREICHEN und nicht an einem
    # Gleitkommarest scheitern (config.mind_erreicht, siehe dort).
    if in_frueh_phase:
        if not mind_erreicht(frueh_ratio, GAP_FRUEH_FAKTOR):
            return None
    elif not mind_erreicht(tages_ratio, GAP_VOL_FAKTOR):
        return None

    spanne = high - low
    pos = (kurs - low) / spanne if spanne > 0 else 1.0
    kp = round(high + 0.01, 2)
    # DER STOP NACH DEM NEUEN GRUNDPRINZIP (Gerhard, 05.08.2026): Der
    # strukturelle Bruchpunkt dieses Musters ist das Tief des
    # Luecken-Tages; gedeckelt wird er bei zehn Prozent unter dem
    # Kaufpunkt. Vorher stand hier min(Tagestief, Kaufpunkt x 0,97) —
    # das nahm zwar auch das Tief, kannte aber keine Obergrenze und lag
    # im Median 11,5 % und im Aeussersten 46 % entfernt.
    stop, stop_quelle = exit_regeln.berechne_initialen_stop(kp, low - 0.01)
    bestaetigt = (kurz_vor_schluss and mind_erreicht(pos, GAP_SCHLUSS_POS)
                  and mind_erreicht(vol / vol50, GAP_VOL_FAKTOR))
    return {"ticker": ticker, "gap": gap, "frueh": in_frueh_phase,
            "frueh_ratio": frueh_ratio, "tages_ratio": tages_ratio,
            "roh_ratio": vol / vol50, "pos": pos, "kp": kp, "stop": stop,
            "stop_quelle": stop_quelle,
            "bestaetigt": bestaetigt, "base_spanne": q.get("base_spanne"),
            "flat_base": q.get("flat_base"), "kurs": kurs}


# ---------------------------------------------------------------------------
# Red-to-Green (Regelwerk Kapitel 9, praezisiert am 02.08.2026)
# ---------------------------------------------------------------------------
# ES GAB DAFUER NOCH KEINE WAECHTERSCHLEIFE. Gerhards Uebergabe geht davon
# aus, die bestehende bliebe "strukturell gleich" und nur der Volumen-Check
# werde ausgetauscht — im Code stand bisher aber nur der Eintrag in
# config.py, kein einziger Rechenweg. Der ganze Ablauf ist deshalb neu.
#
# Die Fokusliste kommt aus dem Nachtscan (fokusliste.json): RS ueber 90,
# ueber EMA21 und EMA50, mindestens 50 % ueber dem 52-Wochen-Tief. Der
# Waechter steuert nur bei, was erst am Morgen feststeht — den Gap.

# GitHub schiesst jeden Auftrag auf seinen Rechnern nach sechs Stunden ab.
# Das ist eine harte Grenze; timeout-minutes im Workflow kann sie nicht
# anheben. Sie steht hier, damit das Protokoll ehrlich sagt, wann wirklich
# Schluss ist (Mathias' Frage vom 04.08.2026).
GITHUB_GRENZE_MIN = 360

# DER NEUE NAME FUER KAPITEL 7 (Gerhard, 05.08.2026). "Gap and Go" ist
# besetzt und beschreibt ueblicherweise ein Tagesgeschaeft: kaufen am
# Vormittag, verkaufen am Abend. Gebaut ist aber ein Einstieg am
# FOLGETAG ueber dem Hoch des Luecken-Tages. "Follow Through Day" waere
# ebenfalls falsch — der Begriff ist bei IBD fuer ein MARKTWEITES Signal
# vergeben und haette die naechste Verwechslung gebaut.
GAP_NAME = "Lücken-Bestätigungstag"

R2G_INDEX = "^IXIC"                  # Nasdaq Composite, der Regime-Schalter
_r2g_fokus: dict = {}                # {Ticker: {firma, vortagesschluss, v50}}
_r2g_verlauf: dict = {}              # {Ticker: [Punkte des Tages]}
_r2g_regime = None                   # None = heute noch nicht geprueft
_r2g_naechster_versuch = 0.0         # time.monotonic() des naechsten Abrufs
_r2g_fehlversuche = 0
R2G_MAX_FEHLVERSUCHE = 30            # eine halbe Stunde lang je Minute ein Versuch


def r2g_fokusliste_laden(pfad="fokusliste.json") -> dict:
    """Die nachts vorbereitete Fokusliste holen.

    Fehlt sie oder ist sie von gestern, laeuft Kapitel 9 heute nicht —
    lieber gar nicht melden als gegen veraltete Kennzahlen."""
    try:
        with open(pfad, encoding="utf-8-sig") as f:
            roh = json.load(f)
    except (OSError, ValueError) as e:
        print(f"  Red-to-Green: keine Fokusliste ({type(e).__name__}) — "
              f"Kapitel 9 bleibt heute stumm.")
        return {}
    aktien = roh.get("aktien", {})
    print(f"  Red-to-Green: {len(aktien)} Aktien auf der Fokusliste "
          f"(gebaut am {roh.get('gebaut_am', 'unbekannt')}).")
    return aktien


def r2g_regime_pruefen():
    """Einmal am Tag: Gapt der Nasdaq mindestens 1,5 % nach unten?

    Ohne diesen Markt-Gap gibt es keinen Red-to-Green-Handel — dann
    bleibt die ganze Strategie den Tag ueber stumm. Das Ergebnis wird
    gemerkt, der Index also nicht in jedem Durchlauf neu abgerufen."""
    global _r2g_regime, _r2g_naechster_versuch, _r2g_fehlversuche
    if _r2g_regime is not None:
        return _r2g_regime
    # EIN FEHLVERSUCH SCHALTET NICHT MEHR DEN GANZEN TAG STUMM (Befund
    # 09.09.2026). Bis dahin genuegte ein leerer Abruf, und das Regime
    # stand bis zum Abend auf stumm. Jetzt wird je Datentakt einmal neu
    # gefragt, hoechstens R2G_MAX_FEHLVERSUCHE Mal.
    jetzt = time.monotonic()
    if jetzt < _r2g_naechster_versuch:
        return False
    _r2g_naechster_versuch = jetzt + TAKT
    q = fetch_quotes_yahoo([R2G_INDEX]).get(R2G_INDEX) or {}
    eroeffnung, vortag = q.get("open"), q.get("prev_close")
    # NUR DIE HEUTIGE TAGESZEILE ZAEHLT: Direkt nach der Glocke liefert
    # Yahoo oft noch die gestrige Zeile, und deren Eroeffnung gegen den
    # Schluss von vorgestern ist nicht die Luecke von heute.
    heute = heute_ny()
    von_heute = heute is None or q.get("bar_datum") == heute
    if not eroeffnung or not vortag or not von_heute:
        _r2g_fehlversuche += 1
        grund = ("noch ohne heutige Tageszeile" if eroeffnung and vortag
                 else "nicht abrufbar")
        if _r2g_fehlversuche >= R2G_MAX_FEHLVERSUCHE:
            print(f"  Red-to-Green: Nasdaq-Eröffnung nach "
                  f"{_r2g_fehlversuche} Versuchen {grund} — Regime bleibt "
                  f"heute stumm.")
            _r2g_regime = False
        elif _r2g_fehlversuche == 1:
            print(f"  Red-to-Green: Nasdaq-Eröffnung {grund} — neuer "
                  f"Versuch in {TAKT} Sekunden.")
        return False
    scharf, gap = red_to_green.regime_scharf(eroeffnung, vortag)
    print(f"  Red-to-Green: Nasdaq eröffnet {gap:+.2f} % — "
          f"{'scharf' if scharf else 'stumm'}.")
    _r2g_regime = scharf
    return scharf


def pruefe_red_to_green(ticker: str, q: dict, eintrag: dict):
    """Eine Aktie der Fokusliste, ein Durchlauf.

    Zwei Bedingungen vor der eigentlichen Signatur: Die Aktie muss selbst
    mindestens 5 % nach unten gapen, und der Tagesverlauf wird
    mitgeschrieben (ein Punkt je Minute, siehe punkt_setzen)."""
    vortag = eintrag.get("vortagesschluss") or q.get("prev_close")
    v50 = eintrag.get("v50")
    kurs, vol, eroeffnung = q.get("close"), q.get("volume"), q.get("open")
    if not (vortag and v50 and kurs and vol and eroeffnung):
        return None
    if not red_to_green.aktien_gap(eroeffnung, vortag)[0]:
        return None

    minute = volumen.minute_seit_eroeffnung()
    if minute is None:
        return None                      # ausserhalb der Handelszeit
    verlauf = _r2g_verlauf.setdefault(ticker, [])
    red_to_green.punkt_setzen(verlauf, minute, kurs, vol)
    # Die EIGENE Kurve dieser Aktie (Gerhard, 06.08.2026). Fehlt sie,
    # liefert die Volumen-Signatur None und Kapitel 9 meldet nicht —
    # gerechnet wird nicht mit einer fremden Kurve.
    return red_to_green.pruefe(verlauf, vortag, v50,
                               volumen.kurve_fuer(ticker))


def pruefe_red_to_green_explosive(ticker, q, eintrag):
    """Kapitel 11 (Mathias, 12.08.2026): dieselbe Signatur wie Kapitel 9,
    aber OHNE Nasdaq-Bedingung und mit zwei statt fuenf Prozent Luecke.

    Der Tagesverlauf wird mit Kapitel 9 GETEILT — beide schreiben in
    dieselbe Reihe (_r2g_verlauf), und punkt_setzen haelt je Minute genau
    einen Punkt. Zwei getrennte Reihen zu fuehren waere doppelte Arbeit
    und koennte auseinanderlaufen."""
    vortag = eintrag.get("vortagesschluss") or q.get("prev_close")
    v50 = eintrag.get("v50")
    kurs, vol, eroeffnung = q.get("close"), q.get("volume"), q.get("open")
    if not (vortag and v50 and kurs and vol and eroeffnung):
        return None
    if not red_to_green_explosive.aktien_gap(eroeffnung, vortag)[0]:
        return None

    minute = volumen.minute_seit_eroeffnung()
    if minute is None:
        return None
    verlauf = _r2g_verlauf.setdefault(ticker, [])
    red_to_green_explosive.punkt_setzen(verlauf, minute, kurs, vol)
    return red_to_green_explosive.pruefe(verlauf, vortag, v50,
                                         volumen.kurve_fuer(ticker))


def format_r2g(t: dict) -> str:
    """Meldung nach denselben Regeln wie ueberall: Kuerzel und Firma
    zuerst, Strichpunkt zwischen verschiedenen Angaben, Beistrich
    innerhalb zusammengehoeriger."""
    sig = t["signatur"]
    zeilen = [
        kopfzeile(t["ticker"], t.get("firma", ""), "Red-to-Green"),
        f"Kreuzung {t['kurs']:.2f} über Vortagesschluss "
        f"{t['vortagesschluss']:.2f}; Minute {t['minute']} des Handelstages",
        f"Vol Sprung {sig['sprung_pct']:.0f} % über Ø50"
        + (", Anflug trocken" if sig["anflug_pct"] is not None
           and sig["anflug_pct"] <= 0 else "")
        + ("; erste 30 Minuten, Anflug entfällt" if sig["in_fruehphase"] else ""),
    ]
    return "\n".join(zeilen)


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
    # Die Kopfzeile entsteht unten zusammen mit dem Musternamen, damit
    # der Zahlen-Termin ganz hinten anschliessen kann.
    status = ("BESTÄTIGT (Schluss im oberen Fünftel)" if g["bestaetigt"]
              else "im Aufbau")
    noetig = GAP_FRUEH_FAKTOR if g["frueh"] else GAP_VOL_FAKTOR
    vol = ("Volumen "
           + volumen.lage_text((g["tages_ratio"] - 1) * 100, VOL_FENSTER)
           + ", " + volumen.huerde_text(noetig))
    luecke = f"Lücke +{g['gap']*100:.1f}%"
    # DIE BASIS IST SEIT 05.08.2026 EIN VERMERK, kein Ausschluss mehr.
    # Sie steht deshalb weiterhin in der Meldung, jetzt aber in beiden
    # Richtungen — enge Basis wie weite.
    if g.get("base_spanne") is not None:
        eng = "enge" if g.get("flat_base") else "weite"
        luecke += (f"; {eng} Basis davor, "
                   f"Spanne {g['base_spanne']*100:.0f}%")
    stop_txt = f"Stop {g['stop']:.2f}"
    if g.get("stop_quelle") == "deckel":
        stop_txt += " (Zehn-Prozent-Deckel)"
    zeilen = [kopfzeile(g["ticker"], g.get("firma", ""),
                        f"{GAP_NAME} {status}"),
              luecke,
              vol,
              f"Position in der Tagesspanne {g['pos']*100:.0f}%",
              f"Kaufpunkt (Folgetag) {g['kp']:.2f}, {stop_txt}"]
    if not g["bestaetigt"]:
        zeilen.append(f"Schlussbestätigung (oberes Fünftel + "
                      f"{GAP_VOL_FAKTOR:.0f} mal Volumen) folgt zum "
                      f"Handelsende")
    z = zusatz_zeile(g.get("ticker"))
    if z:
        zeilen.append(z)
    return "\n".join(zeilen)


def _datum_de(iso) -> str:
    """Ein ISO-Datum lesbar, fuer die Meldungstexte."""
    try:
        return date.fromisoformat(str(iso)).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return str(iso or "")


def format_gapgo_einstieg(g: dict) -> str:
    """Der Einstieg am FOLGETAG eines Luecken-Bestaetigungstages.

    BEWUSST EINE EIGENE MELDUNG. Die Meldung des Luecken-Tages ist kein
    Kaufsignal, sie nennt den Kaufpunkt fuer den Folgetag (format_gapgo
    schreibt "Kaufpunkt (Folgetag)"); gekauft wird nach Kapitel 7 erst,
    wenn der Folgetag dieses Hoch ueberschreitet. Zu diesem Ereignis kam
    bis 11.09.2026 GAR KEINE Meldung mehr: Der Waechter legte schon am
    Luecken-Tag eine Beobachtung an und meldete danach nur den Ausstieg."""
    einstieg, stop = float(g["einstieg"]), float(g["stop"])
    zeilen = [kopfzeile(g["ticker"], g.get("firma", ""),
                        f"{GAP_NAME} Einstieg"),
              f"Kaufpunkt {float(g['kaufpunkt']):.2f} vom Lücken-Tag "
              f"{_datum_de(g.get('signal'))} überschritten, Kurs "
              f"{float(g['kurs']):.2f}",
              f"Einstieg {einstieg:.2f}, Stop {stop:.2f}"]
    if einstieg > 0:
        zeilen[-1] += (f"; Risiko bis Stop "
                       f"{(einstieg - stop) / einstieg * 100:.1f}%")
    if not g.get("bestaetigt"):
        zeilen.append("Der Lücken-Tag hatte keine Schlussbestätigung, "
                      "oberes Fünftel und Volumen fehlten zum Handelsende")
    z = zusatz_zeile(g.get("ticker"))
    if z:
        zeilen.append(z)
    vermerk = termin_nachsatz(g.get("ticker"))
    if vermerk:
        zeilen.insert(1, vermerk)
    return "\n".join(zeilen)


def format_gapgo_uebersprungen(g: dict) -> str:
    """W2 (Gerhard, 12.09.2026): Der Folgetag hat das Hoch des Luecken-Tages
    ueberschritten, aber der Einstieg laege ueber der 3-Prozent-Grenze.
    AUSDRUECKLICH KEIN Kaufsignal, wie bei format_uebersprungen."""
    einstieg, kp = float(g["einstieg"]), float(g["kaufpunkt"])
    pct = (einstieg / kp - 1) * 100 if kp else 0.0
    zeilen = [kopfzeile(g["ticker"], g.get("firma", ""),
                        f"{GAP_NAME} Einstieg ÜBERSPRUNGEN"),
              f"Kaufpunkt {kp:.2f} vom Lücken-Tag {_datum_de(g.get('signal'))} "
              f"überschritten, Einstieg wäre {einstieg:.2f} und liegt "
              f"{pct:.1f}% darüber, über der Grenze von "
              f"{GAP_EINSTIEG_GRENZE * 100:.0f}%",
              "Kein Einstieg mehr, daher kein Kaufsignal"]
    z = zusatz_zeile(g.get("ticker"))
    if z:
        zeilen.append(z)
    vermerk = termin_nachsatz(g.get("ticker"))
    if vermerk:
        zeilen.insert(1, vermerk)
    return "\n".join(zeilen)


def format_uebersprungen(t: dict) -> str:
    """Ein Kaufpunkt wurde uebersprungen — AUSDRUECKLICH KEIN Kaufsignal.

    Der Ton ist bewusst anders als bei einem Ausbruch: kein "BESTAETIGT",
    keine Volumenzahl, kein Stop und kein Ziel. Wer hier Zahlen liest,
    die nach Einstieg aussehen, steigt womoeglich hinterher ein — und
    genau davor schuetzt die Grenze.

    Genannt wird stattdessen, was der Einstieg JETZT kosten wuerde: das
    Risiko bis zum Stop des Musters. Bei Sea waeren das am 11.08.2026
    18 % statt der geplanten zehn gewesen.
    """
    namen = t.get("strategien") or [t["strategie"]]
    strategie = ", ".join(STRATEGIE_VOLL.get(n, n) for n in namen)
    zeilen = [kopfzeile(t["ticker"], t.get("firma", ""), strategie),
              f"Kaufpunkt {t['kaufpunkt']:.2f} ÜBERSPRUNGEN, Kurs "
              f"{t['kurs']:.2f} liegt {t['ueber_pct']:.1f}% darüber"]
    stop = t.get("stop")
    if stop:
        # BEWUSST NICHT ueber exit_regeln.risiko_pct: Das wirft ueber dem
        # Deckel, und genau darum geht es hier. Gerechnet wird schlicht.
        jetzt = (t["kurs"] - stop) / t["kurs"] * 100
        geplant = (t["kaufpunkt"] - stop) / t["kaufpunkt"] * 100
        zeilen.append(f"Einstieg jetzt hieße {jetzt:.0f}% Risiko bis Stop "
                      f"{stop:.2f} statt der geplanten {geplant:.0f}%")
    zeilen.append("Kein sauberer Einstieg mehr, daher kein Kaufsignal")
    # Bei uebersprungenen Kaufpunkten ERKLAERT der Termin oft die
    # Luecke: Sea eroeffnete am 11.08.2026 zehn Prozent ueber dem
    # Kaufpunkt, nachdem es um 08:00 Zahlen gebracht hatte. Er steht als
    # zweite Zeile oben (Mathias, 31.08.2026: "Wenn ein Unternehmen
    # Zahlen bringt, soll dies am Anfang der Push-Mitteilung stehen").
    vermerk = termin_nachsatz(t.get("ticker"))
    if vermerk:
        zeilen.insert(1, vermerk)
    return "\n".join(zeilen)


# SEIT 10.09.2026 NICHT MEHR AUFGERUFEN (Mathias' Regel: nichts vom Vortag).
# Der Radar rechnet auf Tagesschlusskursen; wie er regelkonform melden soll,
# ist eine Regelfrage an Gerhard. Die Funktion bleibt fuer seine Antwort.
def melde_sektor_radar(topic: str, befund: dict, schon_gemeldet: set,
                       state: dict) -> bool:
    """Den Befund des Nachtlaufs EINMAL je Handelstag melden.

    WARUM HIER UND NICHT IM NACHTLAUF (Mathias, 27.07.2026, im
    Scanner-Workflow festgehalten): "Gemeldet wird ausschliesslich vom
    Waechter, und zwar erst ab der New Yorker Eroeffnung. Die frueheren
    Mitternachtsnachrichten waren Treffer, die zu diesem Zeitpunkt
    ohnehin niemand handeln konnte." Gerhards Paket sendet direkt aus dem
    Nachtlauf; das waere ein Rueckfall hinter diese Entscheidung.
    Gerechnet wird also nachts, gemeldet am Morgen.

    Die Handelszeit-Sperre braucht es hier nicht eigens: Sie sitzt in
    sende() und gilt fuer JEDE automatische Meldung. Schlaegt sie zu,
    kommt false zurueck und der Befund bleibt offen.

    Rueckgabe: true, wenn er weg ist (oder es nichts zu melden gab)."""
    treffer = befund.get("treffer") or []
    tag = befund.get("handelstag")
    if not treffer or not tag:
        return True
    key = SEKTOR_MARKE + str(tag)
    if key in schon_gemeldet:
        return True
    absaetze = sektor_radar.absaetze(treffer)
    # Priorität "default": Ein Branchendreher ist eine Auskunft, kein
    # Ausbruch — er soll nicht wie ein Kaufsignal klingeln.
    if not sende(topic, sektor_radar.titel(treffer), absaetze, "default"):
        return False
    schon_gemeldet.add(key)
    state["gemeldet"][key] = date.today().isoformat()
    save_state(state)
    print(f"Sektor-Radar gemeldet: {len(treffer)} Dreher vom {tag}.")
    return True


def format_wiedereintritt(t: dict) -> str:
    """Der Kurs ist ins Einstiegsfenster ZURUECKGEKEHRT.

    Mathias am 13.08.2026, als er zwischen zwei Wegen zu waehlen hatte:
    "Ich waere fuer den 2ten Weg mit einer Meldung, die den Wiedereintritt
    zeigt." Also darf ein Kaufpunkt zurueckkommen, und der Wechsel wird
    gemeldet — aber EHRLICH als Wiedereintritt und nicht als frischer
    Ausbruch. Sonst stuende zweimal dasselbe da und man haelt es fuer
    zwei Gelegenheiten.

    Sonst wie ein Ausbruch: Kurs, Volumenlage, Stop, Risiko und Ziel
    stehen dabei, denn der Einstieg ist wieder moeglich."""
    return format_treffer(t, kopfzusatz="wieder im Einstiegsfenster")


def push_wiedereintritt(topic: str, treffer: list[dict]) -> bool:
    if not treffer:
        return False
    absaetze = [f"{i}. {format_wiedereintritt(t)}"
                for i, t in enumerate(treffer, 1)]
    titel = (", ".join(t["ticker"] for t in treffer)
             + ": wieder im Einstiegsfenster" + tagesanteil_titel(treffer))
    return sende(topic, titel, absaetze, "high")


def beobachtungen_eintragen(eintraege, einmal_je_muster=False):
    """Kapitel-12-Fuetterung: Trigger werden Beobachtungen.

    eintraege: Liste von dicts mit ticker, zusatz, strategie, kaufpunkt,
    struktur, ziel, firma, klasse. Fehler brechen NIE die Meldekette —
    die Fuetterung ist Zusatznutzen, kein Meldeweg.

    einmal_je_muster (Ausbrueche, seit 10.09.2026): Steht fuer die Aktie
    schon eine offene Beobachtung mit einem dieser Muster, auch eine aus
    der Zeit der Platznummern, entsteht keine zweite."""
    if not eintraege:
        return
    try:
        bestand = positionen.laden()
        neu = []
        for e in eintraege:
            if einmal_je_muster and beobachtungen.offen_mit_strategie(
                    bestand, e["ticker"],
                    str(e.get("strategie", "")).split(",")):
                continue
            key = beobachtungen.oeffnen(
                bestand, e["ticker"], e["zusatz"], e.get("strategie", ""),
                e.get("kaufpunkt"), e.get("struktur"),
                musterziel=e.get("ziel"), firma=e.get("firma", ""),
                klasse=e.get("klasse", "standard"))
            if key:
                neu.append(key)
        if neu:
            positionen.speichern(bestand)
            print(f"Kapitel 12: {len(neu)} Beobachtung(en) eröffnet: "
                  + ", ".join(neu))
    except Exception as e:
        print(f"Beobachtungs-Fütterung fehlgeschlagen: "
              f"{type(e).__name__}: {e}")


def beobachtungen_aus_breakouts(treffer):
    """Ausbruchs-Treffer in Fuetterungs-Eintraege uebersetzen."""
    eintraege = []
    for t in treffer:
        namen = t.get("strategien") or [t.get("strategie")]
        termin = beobachtungen.termin_abstand_tage(t.get("ticker"))
        eintraege.append({
            # NACH MUSTER statt nach Platznummer (10.09.2026), siehe
            # ausbruch_schluessel_alle.
            "ticker": t.get("ticker"), "zusatz": " + ".join(kp_namen(t)),
            "strategie": ", ".join(str(n) for n in namen if n),
            "kaufpunkt": t.get("kaufpunkt"), "struktur": t.get("stop"),
            "ziel": t.get("ziel"), "firma": t.get("firma", ""),
            "klasse": beobachtungen.klasse_fuer(namen, termin)})
    beobachtungen_eintragen(eintraege, einmal_je_muster=True)


def tagesgeschaeft_wache(topic, quotes, dry_run, state=None):
    """Intraday-Wache der Tagesgeschaeft-Beobachtungen (Kapitel 12):
    Faellt der Kurs zurueck unter die Exit-Linie (bei Red-to-Green der
    Vortagesschluss, bei Gap and Go der Muster-Stop), kommt SOFORT die
    laute Exit-Meldung — nicht erst am Abend. Die Beobachtung wird
    geschlossen und traegt ihr Ergebnis (die Mitschrift)."""
    if dry_run or not quotes:
        return
    try:
        bestand = positionen.laden()
        raus = []
        for key, e in beobachtungen.offene(bestand).items():
            if e.get("klasse") != "tagesgeschaeft":
                continue
            q = quotes.get(e.get("symbol"))
            kurs = q.get("close") if q else None
            if kurs and kurs == kurs and float(kurs) < e["aktueller_stop"]:
                beobachtungen.schliessen(
                    e, "Rückfall unter die Exit-Linie (intraday)",
                    float(kurs))
                raus.append((key, e, float(kurs)))
        if not raus:
            return
        absaetze = []
        for i, (key, e, kurs) in enumerate(raus, 1):
            pct = (kurs / e["einstieg"] - 1) * 100
            absaetze.append(
                f"{i}. {e['symbol']}; {e.get('strategie', '')}; Kurs "
                f"{kurs:.2f} unter der Exit-Linie "
                f"{e['aktueller_stop']:.2f}; seit Trigger "
                + f"{pct:+.1f} %".replace(".", ","))
        titel = ("EXIT Tagesgeschäft: "
                 + ", ".join(e["symbol"] for _, e, _ in raus))
        paket = handel_paket([{"ticker": e["symbol"],
                               "firma": e.get("firma", ""),
                               "strategie": e.get("strategie", ""),
                               "kurs": kurs}
                              for _, e, kurs in raus],
                             art="verkauf", anlass="exit")
        if sende(topic, titel, absaetze, "high", handel_adresse(paket)):
            positionen.speichern(bestand)
            # UND SOFORT INS REPO: Ein geschlossener Exit steht nur in
            # positionen.json; ohne diese Zeile war er nach dem Lauf weg
            # und derselbe Ausstieg kam am naechsten Handelstag erneut
            # (Befund 12.09.2026, siehe _repo_sichern).
            if state is not None:
                save_state(state, sofort=True)
    except Exception as e:
        print(f"Tagesgeschäft-Wache fehlgeschlagen: "
              f"{type(e).__name__}: {e}")


def _handelstage_seit(datum, heute) -> int | None:
    try:
        d = date.fromisoformat(str(datum)[:10])
    except (TypeError, ValueError):
        return None
    n, lauf = 0, d
    while lauf < heute:
        lauf += timedelta(days=1)
        if lauf.weekday() < 5:
            n += 1
    return n


def teilverkauf_wache(topic, quotes, dry_run, state, schon_gemeldet):
    """M2 (Gerhard, 12.09.2026): Der Teilverkauf (Stufe B des Exit-Regelwerks,
    ab plus 20 Prozent seit Einstieg) wird IM HANDEL gemeldet, sobald der
    Kurs die Schwelle erreicht, nicht erst mit dem Schluss. Die Halteregel
    fuer Schnellstarter gilt weiter (solange sie laeuft, kein Teilverkauf).
    Eine REGEL-Meldung, laut; danach traegt die Beobachtung teilverkauft,
    genau wie nach dem Nachtlauf, und zwar einmal je Beobachtung."""
    if dry_run or not quotes:
        return
    try:
        ex = CFG["exit"]
        heute = heute_ny() or date.today()
        bestand = positionen.laden()
        faellig = []
        for key, e in beobachtungen.offene(bestand).items():
            if e.get("klasse") == "darvas" or e.get("teilverkauft"):
                continue
            q = quotes.get(e.get("symbol"))
            kurs = q.get("close") if q else None
            if not kurs or kurs != kurs or not e.get("einstieg"):
                continue
            gewinn = float(kurs) / float(e["einstieg"]) - 1
            if not mind_erreicht(gewinn, ex["teilverkauf_ab_pct"]):
                continue
            if e.get("halteregel_aktiv"):
                seit = _handelstage_seit(e.get("einstieg_datum"), heute)
                if seit is not None and seit < int(ex["halteregel_tage"]):
                    continue
            k = TEIL_MARKE + key
            if k in schon_gemeldet:
                continue
            faellig.append((key, e, float(kurs), gewinn, k))
        if not faellig:
            return
        absaetze = []
        for i, (key, e, kurs, gewinn, k) in enumerate(faellig, 1):
            absaetze.append(
                f"{i}. REGEL: {meldungskopf(e['symbol'], e.get('firma', ''))}; "
                f"{e.get('strategie', '')}; Teilverkauf fällig, "
                + f"{gewinn * 100:+.1f} %".replace(".", ",")
                + f" seit Einstieg im Handel erreicht; "
                f"{ex['teilverkauf_anteil'] * 100:.0f} % verkaufen; "
                f"Kurs {kurs:.2f}, Einstieg {float(e['einstieg']):.2f}")
        titel = "REGEL Teilverkauf: " + ", ".join(e["symbol"] for _, e, _, _, _ in faellig)
        paket = handel_paket([{"ticker": e["symbol"], "firma": e.get("firma", ""),
                               "strategie": e.get("strategie", ""), "kurs": kurs,
                               "key": k} for _, e, kurs, _, k in faellig],
                             art="verkauf", anlass="teilverkauf")
        if sende(topic, titel, absaetze, "high", handel_adresse(paket)):
            heute_s = date.today().isoformat()
            for key, e, kurs, gewinn, k in faellig:
                e["teilverkauft"] = True
                e.setdefault("verlauf", []).append({
                    "datum": heute_s, "aktion": "teilverkauf",
                    "grund": f"+{gewinn * 100:.1f} % im Handel erreicht (M2)",
                    "kurs": round(kurs, 4)})
                schon_gemeldet.add(k)
                state["gemeldet"][k] = heute_s
            positionen.speichern(bestand)
            save_state(state, sofort=True)
    except Exception as e:
        print(f"Teilverkauf-Wache fehlgeschlagen: {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# LUECKEN-BESTAETIGUNGSTAG: DIE BEOBACHTUNG BEGINNT ERST AM FOLGETAG
# (Mathias, 11.09.2026)
# ---------------------------------------------------------------------------
# DER FALL RCUS vom 11.09.2026: Um 15:31 meldete der Waechter den
# Luecken-Bestaetigungstag, und die Kapitel-12-Fuetterung eroeffnete im
# selben Augenblick eine Tagesgeschaeft-Beobachtung mit Einstieg 26,48 und
# Stop 26,14. Gekauft wird nach Kapitel 7 aber erst am FOLGETAG ueber dem
# Hoch des Luecken-Tages. Um 15:47 fiel der Kurs unter 26,14, und es kam
# "EXIT Tagesgeschaeft: RCUS" — ein Ausstieg aus einer Position, die es nie
# gegeben hat.
#
# DIE REGEL IST BELEGT, nicht geschaetzt: gapgo_erfolg.py, die eigene
# Rueckblick-Messung, rechnet mit Kaufpunkt = Hoch des Luecken-Tages plus
# einem Cent, prueft ihn am Tag i + 1 und setzt den Einstieg auf
# max(Eroeffnung des Folgetags, Kaufpunkt). Genau das macht
# gapgo_einstiege_pruefen().
#
# ZWEI FOLGEN DARAUS:
#   1. Die Meldung des Luecken-Tages legt KEINE Beobachtung mehr an,
#      sondern einen Eintrag in der Warteliste des Zustands.
#   2. Kaufpunkt und Stop werden bis zum Handelsschluss NACHGEZOGEN. Sie
#      haengen am Tageshoch und Tagestief, und die wandern: Bei RCUS stand
#      in der Beobachtung der Wert aus der ERSTEN Minute (26,48).
def gapgo_vormerken(state: dict, g: dict, anlegen: bool = True) -> bool:
    """Ein Luecken-Tag wandert in die Warteliste, nicht in die
    Beobachtungen. Rueckgabe: Hat sich der Zustand geaendert?

    anlegen=False zieht einen SCHON vorhandenen Eintrag desselben Tages
    nach und legt keinen neuen an — so gerufen in jedem Durchlauf, damit
    Kaufpunkt und Stop dem Tageshoch und Tagestief folgen. Mit
    anlegen=True entsteht der Eintrag; das geschieht nur nach einer
    erfolgreich verschickten Meldung.

    EIN EINTRAG VON GESTERN WIRD NIE UEBERSCHRIEBEN: Er wartet auf seinen
    Einstieg und bekaeme sonst den Kaufpunkt von heute."""
    warten = state.setdefault(GAPGO_WARTEN, {})
    t = str(g.get("ticker") or "").upper()
    kp, stop = _zahl(g.get("kp")), _zahl(g.get("stop"))
    if not t or kp is None or stop is None:
        return False
    heute = (heute_ny() or date.today()).isoformat()
    e = warten.get(t)
    if not isinstance(e, dict) or str(e.get("signal")) != heute:
        if not anlegen:
            return False
        warten[t] = {"signal": heute, "kp": kp, "stop": stop,
                     "firma": g.get("firma", ""),
                     "bestaetigt": bool(g.get("bestaetigt"))}
        return True
    alt_kp = _zahl(e.get("kp"))
    neu_kp = kp if alt_kp is None else max(alt_kp, kp)
    best = bool(e.get("bestaetigt")) or bool(g.get("bestaetigt"))
    if (neu_kp, stop, best) == (alt_kp, _zahl(e.get("stop")),
                               bool(e.get("bestaetigt"))):
        return False
    e["kp"], e["stop"], e["bestaetigt"] = neu_kp, stop, best
    return True


def gapgo_einstiege_pruefen(state: dict, quotes: dict) -> tuple:
    """AM FOLGETAG: Wer sein Hoch von gestern ueberschreitet, wird JETZT
    gekauft. Rueckgabe: (Einstiege zum Melden, Zustand geaendert).

    Der Einstieg ist max(Eroeffnung, Kaufpunkt) — genau die Rechnung der
    Rueckblick-Messung: Eroeffnet die Aktie ueber dem Kaufpunkt, kauft man
    zur Eroeffnung und nicht zum guenstigeren Wunschpreis.

    VERFALL: Gehandelt wird nur am ERSTEN Wachtag nach dem Signal (die
    Messung prueft genau den Tag i + 1). Wer seinen Kaufpunkt an diesem
    Tag nicht erreicht, verfaellt; ebenso alles, was laenger als
    GAPGO_WARTE_TAGE liegen bleibt.

    ENTFERNT WIRD HIER NUR, WAS VERFAELLT. Einen Einstieg traegt erst der
    Aufrufer aus, und zwar nach erfolgreicher Meldung — sonst waere er bei
    einer Sendesperre still verloren."""
    warten = state.get(GAPGO_WARTEN)
    if not isinstance(warten, dict) or not warten:
        return [], False
    heute = heute_ny() or date.today()
    heute_s = heute.isoformat()
    einstiege, geaendert = [], False
    for t, e in list(warten.items()):
        if not isinstance(e, dict):
            warten.pop(t, None)
            geaendert = True
            continue
        signal = str(e.get("signal") or "")
        if signal == heute_s:
            continue                   # der Luecken-Tag laeuft noch
        try:
            tage = (heute - date.fromisoformat(signal)).days
        except ValueError:
            warten.pop(t, None)
            geaendert = True
            continue
        pruef = str(e.get("pruef") or "")
        if tage > GAPGO_WARTE_TAGE or (pruef and pruef != heute_s):
            kp_txt = _zahl(e.get("kp"))
            kp_txt = "?" if kp_txt is None else f"{kp_txt:.2f}"
            grund = ("am Folgetag nicht erreicht" if pruef
                     else f"seit {tage} Tagen kein Wachtag")
            print(f"  {t}: {GAP_NAME} vom {_datum_de(signal)} verfallen, "
                  f"Kaufpunkt {kp_txt} {grund}.")
            warten.pop(t, None)
            geaendert = True
            continue
        if pruef != heute_s:
            e["pruef"] = heute_s       # heute ist der Einstiegstag
            geaendert = True
        q = quotes.get(t) or {}
        kurs, kp, stop = (_zahl(q.get("close")), _zahl(e.get("kp")),
                          _zahl(e.get("stop")))
        if kurs is None or kp is None or stop is None or kp <= 0:
            continue
        if kurs < kp:
            continue                   # das Hoch von gestern steht noch
        eroeffnung = _zahl(q.get("open"))
        einstieg = max(eroeffnung, kp) if eroeffnung else kp
        # W2 (Gerhard, 12.09.2026): Der Folgetags-Einstieg gilt nur bis
        # 3 Prozent ueber dem Kaufpunkt (config gap_and_go.einstieg_grenze).
        # Darueber ist es KEIN Einstieg, sondern die Auskunft, dass die
        # Aktie davongelaufen ist; der Eintrag verfaellt nach der Meldung.
        ueber = einstieg > kp * (1.0 + GAP_EINSTIEG_GRENZE) + 1e-9
        einstiege.append({
            "ticker": t, "firma": e.get("firma", ""),
            "strategie": "Gap and Go", "signal": signal,
            "kaufpunkt": kp, "einstieg": einstieg, "stop": stop,
            "kurs": kurs, "bestaetigt": bool(e.get("bestaetigt")),
            "uebersprungen": ueber,
            "key": f"{GAPGO_UEBER_MARKE if ueber else GAPGO_EIN_MARKE}{t}|{signal}"})
    return einstiege, geaendert


# ---------------------------------------------------------------------------
# NACHTBEFUNDE ZUM HANDELSSTART (Mathias, 10.09.2026)
# ---------------------------------------------------------------------------
# Woertlich: "Es darf nie wieder etwas vom Vortag kommen, angezeigte Alarme
# muessen immer aus den aktuellen Kursen errechnet sein, die zu Handelsstart
# gelten."
#
# BIS DAHIN verschickte der Waechter beim Start die fertigen Texte des
# Nachtlaufs, NOCH BEVOR er einen einzigen Kurs abgerufen hatte. Am
# 09.09.2026 waren das zehn Meldungen ab 15:30:21, alle mit dem Schluss vom
# 08.09. und ohne Datum; der erste Kursabruf begann deshalb erst gegen
# 15:31:50, die Ausbruchswache war anderthalb Minuten blind.
#
# SEITHER:
#   1. Beim Start geht nichts aus der Nacht hinaus. Zuerst kommen Kursabruf
#      und Ausbrueche.
#   2. Jeder Kandidat des Nachtlaufs wird mit dem heutigen Kurs seiner Aktie
#      nachgerechnet (gewinnzonen_lauf.live_pruefen), sobald es fuer sie
#      eine Kurszeile mit heutigem Datum gibt. Gemeldet wird nur, was dann
#      noch gilt, mit Kurs und Stand von heute. Die Insider-Funde bekommen
#      Marktwert und Einstufung zum heutigen Kurs.
#   3. Hoechstens EINE solche Meldung je Durchlauf und nur bei freiem
#      Push-Sammler: Kein Ausbruch wartet auf sie.
#   4. Was nach Gerhards Regeln einen Schlusskurs braucht (Kapitel-11-Exits,
#      Klimax-Zeichen 2 und 3, Wedge Drop, Sektor-Radar samt Sektor-Hinweis,
#      Tagesgeschaeft beendet), wird bis zu seiner Antwort nicht gemeldet:
#      Aus heutigen Kursen laesst es sich zur Eroeffnung nicht rechnen, und
#      mit dem Schluss von gestern darf es nicht kommen.
#   5. Die Straffungs-Meldungen (Musterziel erreicht, Wedge Drop, Sektor
#      dreht) sind seit 11.09.2026 auf Gerhards Wunsch abgeschaltet
#      (config.py, gewinnseite). Sie fallen schon beim Laden heraus, auch
#      aus einer Ablage, die noch vor dem Abschalten geschrieben wurde.

NACHT_MARKE = "GEWINN|"
INSIDER_MAX_VERSUCHE = 5
_insider_versuche: dict = {}


def nachtbefunde_laden() -> dict:
    """Was Nachtlauf, Sektor-Radar und Insider-Lauf hinterlassen haben,
    getrennt nach 'wird nachgerechnet' und 'bleibt zurueckgehalten'."""
    daten = gewinnzonen_lauf.lies_befunde()
    befunde, abgeschaltet = gewinnzonen_lauf.abgeschaltete_trennen(
        daten.get("befunde") or [])
    try:
        fmt = int(daten.get("format") or 1)
    except (TypeError, ValueError):
        fmt = 1
    alt_format = fmt < gewinnzonen_lauf.FORMAT
    live, zurueck = [], []
    for b in befunde:
        if not alt_format and b.get("art") == gewinnzonen_lauf.LIVE:
            live.append(b)
        else:
            zurueck.append(b)
    radar = sektor_radar.lies() if CFG["sektor_radar"]["melden"] else {}
    insider = (insider_edgar.lies_funde()
               if CFG["insider"].get("melden", True) else [])
    return {"tag": str(daten.get("handelstag") or ""),
            "alt_format": alt_format and bool(befunde),
            "live": live, "zurueck": zurueck,
            "verlaeufe": daten.get("verlaeufe") or {},
            "radar": radar or {}, "insider": list(insider or []),
            "abgeschaltet": len(abgeschaltet),
            "offen": []}


def nachtbefunde_bericht(nacht: dict):
    """Eine Zeile je Quelle ins Protokoll: was nachgerechnet wird und was
    zurueckgehalten bleibt."""
    tag = nacht["tag"] or "unbekannt"
    if nacht["alt_format"]:
        print(f"Nachtbefunde vom {tag}: Ablage im alten Format, also fertige "
              f"Texte mit dem Schlusskurs des Vortags; "
              f"{len(nacht['zurueck'])} Befund(e) werden NICHT gemeldet.")
    elif nacht["live"] or nacht["zurueck"]:
        print(f"Nachtbefunde vom {tag}: {len(nacht['live'])} werden mit den "
              f"heutigen Kursen nachgerechnet, {len(nacht['zurueck'])} "
              f"zurückgehalten (brauchen einen Schlusskurs; Regelfrage an "
              f"Gerhard).")
    else:
        print("Nachtbefunde: keine.")
    if nacht.get("abgeschaltet"):
        print(f"Nachtbefunde vom {tag}: {nacht['abgeschaltet']} "
              f"Straffungs-Befund(e) werden nicht gemeldet, die Meldung ist "
              f"abgeschaltet (Gerhard, bis auf Weiteres).")
    treffer = nacht["radar"].get("treffer") or []
    if treffer:
        print(f"Sektor-Radar: {len(treffer)} Dreher vom "
              f"{nacht['radar'].get('handelstag') or 'unbekannt'} "
              f"zurückgehalten (auf Schlusskursen gerechnet; Regelfrage an "
              f"Gerhard).")
    if nacht["insider"]:
        print(f"Insider-Käufe: {len(nacht['insider'])} Fund(e) liegen vor; "
              f"Marktwert und Einstufung werden mit dem heutigen Kurs "
              f"nachgerechnet.")


def nacht_schluessel(b: dict, merker: dict | None = None) -> str:
    """Der Meldeschluessel eines Nachtbefunds: einmal je Beobachtung und
    Befund, NICHT je Nacht. Erreicht ein Melde-Merker das Repo einmal nicht,
    kaeme derselbe Befund sonst am naechsten Tag wieder. Beim Zonenaufstieg
    zaehlt die erreichte Zone mit: Der spaetere Aufstieg in die naechste
    Zone ist ein neues Ereignis."""
    zusatz = b.get("zeichen") or ""
    if b.get("typ") == "zonenwechsel":
        zusatz = (merker or {}).get("zone_gemeldet") or ""
    return f"{NACHT_MARKE}{b.get('typ')}|{b.get('key')}|{zusatz}"


def nacht_symbole(nacht: dict) -> set:
    """Die Aktien, fuer die der Waechter heutige Kurse braucht."""
    raus = {str(b.get("symbol") or "").upper() for b in nacht["live"]}
    raus |= {str(f.get("ticker") or "").upper() for f in nacht["insider"]}
    raus.discard("")
    return raus


def nachtbefunde_offen(nacht: dict, schon_gemeldet: set) -> list:
    """Was in diesem Lauf noch nachzurechnen ist. Der Zonenaufstieg wird
    erst nach dem Nachrechnen gegen das Gedaechtnis geprueft, weil die
    erreichte Zone zum Schluessel gehoert."""
    offen = []
    for b in nacht["live"]:
        if (b.get("typ") != "zonenwechsel"
                and nacht_schluessel(b) in schon_gemeldet):
            continue
        offen.append(("gewinn", b))
    for f in nacht["insider"]:
        if (INSIDER_MARKE + f.get("kennung", f.get("ticker", "?"))
                in schon_gemeldet):
            continue
        offen.append(("insider", f))
    return offen


def _zahlen_termine() -> dict:
    try:
        with open("zahlen_termine.json", encoding="utf-8-sig") as f:
            return json.load(f).get("aktien", {}) or {}
    except (OSError, ValueError, AttributeError):
        return {}


def _marktwert_heute(sym: str, kurs: float, heute) -> float | None:
    """Der Marktwert zum HEUTIGEN Kurs, oder None.

    Yahoo nennt den Marktwert zusammen mit dem Zeitpunkt seines Kurses;
    der muss von heute sein. Umgerechnet wird auf den Kurs, mit dem der
    Waechter rechnet, damit Marktwert und Kurs zusammenpassen (gemessen am
    10.09.2026 waehrend des Handels: marketCap, regularMarketPrice und
    regularMarketTime kommen fuer RSG und MAIR mit dem Kurs der Minute)."""
    try:
        import yfinance as yf
        info = yf.Ticker(sym).info
    except Exception:
        return None
    mk = info.get("marketCap")
    preis = info.get("regularMarketPrice")
    zeit = info.get("regularMarketTime")
    if not mk or not preis or not zeit:
        return None
    try:
        from zoneinfo import ZoneInfo
        tag = datetime.fromtimestamp(int(zeit),
                                     ZoneInfo("America/New_York")).date()
    except Exception:
        return None
    if heute is not None and tag != heute:
        return None
    return float(mk) * float(kurs) / float(preis)


def _insider_heute(f: dict, sym: str, kurs: float, heute):
    """Einstufung eines Insider-Funds mit dem Marktwert von heute.

    Rueckgabe: die Meldezeilen; None, wenn mit dem heutigen Marktwert kein
    Signal mehr besteht; oder "warten", wenn Yahoo den heutigen Marktwert
    noch nicht nennt (hoechstens INSIDER_MAX_VERSUCHE Mal)."""
    mk = _marktwert_heute(sym, kurs, heute)
    if mk is None:
        _insider_versuche[sym] = _insider_versuche.get(sym, 0) + 1
        if _insider_versuche[sym] >= INSIDER_MAX_VERSUCHE:
            print(f"  Insider-Fund {sym}: kein heutiger Marktwert nach "
                  f"{INSIDER_MAX_VERSUCHE} Versuchen, nicht gemeldet.")
            return None
        return "warten"
    kaeufe = insider_edgar.lies_speicher().get(sym) or []
    if not kaeufe:
        return None
    try:
        stichtag = date.fromisoformat(str(f.get("stichtag"))[:10])
    except ValueError:
        stichtag = None
    isc = insider_edgar.isc
    signal = isc.pruefe_insider_signal(kaeufe, mk, stichtag=stichtag,
                                       cfg=CFG["insider"])
    if signal["status"] in ("kein_signal", "firma_zu_klein"):
        return None
    return isc.meldungszeilen(sym, signal, rollen=insider_edgar.lies_rollen())


def nachtbefunde_schritt(topic, nacht, basis, ws, schon_gemeldet, state,
                         dry_run) -> bool | None:
    """Ein Durchlauf fuer die Nachtbefunde, siehe oben.

    Rueckgabe: None, wenn nichts gesendet wurde; True nach einer Meldung
    (oder ihrer Anzeige im Trockenlauf); False, wenn das Senden scheiterte
    (dann setzt der Aufrufer die Sendesperre)."""
    offen = nacht["offen"]
    if not offen or not basis or not push_frei():
        return None
    heute = heute_ny() or date.today()
    haengend = set(KURSE.stale_liste())
    bestand = positionen.laden()
    termine = None
    laut, leise, insider = [], [], []
    for eintrag in list(offen):
        art, obj = eintrag
        sym = str(obj.get("symbol") if art == "gewinn"
                  else obj.get("ticker") or "").upper()
        # NUR MIT HEUTIGER KURSZEILE: basis fuehrt ausschliesslich Kurse,
        # die pruefe_handelstag als heutig durchgelassen hat.
        q = basis.get(sym)
        if not q or sym in haengend:
            continue
        q = dict(q)
        ws_kurse_einblenden({sym: q}, ws)
        kurs = q.get("close")
        if not kurs or kurs != kurs:
            continue
        kurs = float(kurs)
        if art == "gewinn":
            b = obj
            verlauf = nacht["verlaeufe"].get(b.get("key")) or {}
            daten = verlauf.get("daten") or []
            letzter = str(daten[-1][0])[:10] if daten else None
            vortag = q.get("prev_datum")
            if not letzter or (vortag is not None and str(vortag) != letzter):
                print(f"  Nachtbefund {b.get('typ')} {sym}: Der Kursverlauf "
                      f"der Nacht endet am {letzter or 'unbekannt'}, die "
                      f"heutigen Kurse folgen auf den {vortag}; nicht "
                      f"gemeldet.")
                offen.remove(eintrag)
                continue
            if termine is None:
                termine = _zahlen_termine()
            ergebnis = gewinnzonen_lauf.live_pruefen(
                b, bestand.get(b.get("key")), verlauf, kurs, heute,
                hoch=q.get("high"), tief=q.get("low"), termine=termine,
                schon_symbol=klimax_je_symbol(bestand, sym))
            if ergebnis is None:
                print(f"  Nachtbefund {b.get('typ')} {sym}: gilt mit dem Kurs "
                      f"von heute ({kurs:.2f}) nicht, nicht gemeldet.")
                offen.remove(eintrag)
                continue
            if nacht_schluessel(b, ergebnis[2]) in schon_gemeldet:
                offen.remove(eintrag)
                continue
            (leise if b.get("buendeln") else laut).append(
                (eintrag, b, ergebnis))
        else:
            ergebnis = _insider_heute(obj, sym, kurs, heute)
            if ergebnis == "warten":
                continue
            if ergebnis is None:
                print(f"  Insider-Fund {sym}: mit dem Marktwert von heute "
                      f"kein Signal, nicht gemeldet.")
                offen.remove(eintrag)
                continue
            insider.append((eintrag, obj, ergebnis, sym, kurs))

    # EINE Meldung je Durchlauf: erst die lauten Einzelbefunde, dann die
    # Insider-Kaeufe, zuletzt das Buendel der Zonenaufstiege.
    gesendet_gewinn, gesendet_insider = [], []
    if laut:
        eintrag, b, (titel, text, merker) = laut[0]
        absaetze, prio = [text], b.get("prioritaet", "high")
        gesendet_gewinn = [(eintrag, b, merker)]
    elif insider:
        titel = ("Insider-Käufe: " + ", ".join(i[3] for i in insider)
                 if len(insider) <= 4
                 else f"Insider-Käufe: {len(insider)} Aktien")
        absaetze = [f"{n}. " + "\n".join(i[2])
                    for n, i in enumerate(insider, 1)]
        prio = "default"
        gesendet_insider = insider
    elif leise:
        titel = f"Gewinnzonen: {len(leise)} Hinweis(e)"
        absaetze = [f"{n}. {erg[1]}" for n, (_, _, erg) in enumerate(leise, 1)]
        prio = "default"
        gesendet_gewinn = [(eintrag, b, erg[2]) for eintrag, b, erg in leise]
    else:
        return None

    if dry_run:
        print(f"(Dry-Run) Nachtbefund, heute nachgerechnet: {titel}")
        for a in absaetze:
            print("  " + a.replace("\n", "\n  "))
    elif not sende(topic, titel, absaetze, prio):
        return False
    else:
        heute_s = date.today().isoformat()
        if gesendet_gewinn:
            bestand = positionen.laden()
            for _, b, merker in gesendet_gewinn:
                e = bestand.get(b.get("key"))
                if e is not None:
                    gewinnzonen_lauf.merker_anwenden(e, merker)
                # M5 (Gerhard, 12.09.2026): das Klimax-Zeichen gilt je AKTIE.
                klimax_symbolweit(bestand, b.get("symbol"), merker)
                k = nacht_schluessel(b, merker)
                schon_gemeldet.add(k)
                state["gemeldet"][k] = heute_s
            positionen.speichern(bestand)
        if gesendet_insider:
            for _, f, _, _, _ in gesendet_insider:
                k = INSIDER_MARKE + f.get("kennung", f.get("ticker", "?"))
                schon_gemeldet.add(k)
                state["gemeldet"][k] = heute_s
            # Kapitel 12: Insider-Funde sind marktweit und haben keinen
            # Chart-Kaufpunkt — Einstieg ist der HEUTIGE Kurs (bis
            # 10.09.2026 kam er aus history(period="1d") und war in den
            # ersten Minuten oft noch der Vortagesschluss), Stop der
            # Kapitel-11-Deckel, Klasse insider (Horizont sechs Monate).
            beobachtungen_eintragen([{
                "ticker": sym, "zusatz": "INS-" + heute_s,
                "strategie": "Insider-Kauf", "kaufpunkt": kurs,
                "struktur": None, "ziel": None,
                "firma": f.get("firma", ""), "klasse": "insider"}
                for _, f, _, sym, kurs in gesendet_insider])
        # SOFORT ins Repo, ohne die Minutendrossel: Die Melde-Merker stehen
        # in positionen.json, und die sichert der Endkommit des Laufs nicht.
        save_state(state, sofort=True)
        print(f"Nachtbefund gemeldet: {titel}")
    for eintrag, _, _ in gesendet_gewinn:
        if eintrag in offen:
            offen.remove(eintrag)
    for eintrag, _, _, _, _ in gesendet_insider:
        if eintrag in offen:
            offen.remove(eintrag)
    return True


def klimax_je_symbol(bestand: dict, sym) -> set:
    """M5: alle Klimax-Zeichen, die an irgendeiner Beobachtung der Aktie
    schon als gemeldet stehen."""
    raus = set()
    s = str(sym or "").upper()
    for e in bestand.values():
        if isinstance(e, dict) and str(e.get("symbol") or "").upper() == s:
            raus.update(e.get("klimax_gemeldet") or [])
    return raus


def klimax_symbolweit(bestand: dict, sym, merker: dict):
    """M5: ein gemeldetes Klimax-Zeichen traegt JEDE offene Beobachtung
    der Aktie, nicht nur die, an der es gemeldet wurde."""
    z = (merker or {}).get("klimax_gemeldet")
    if not z:
        return
    s = str(sym or "").upper()
    for e in bestand.values():
        if (isinstance(e, dict) and e.get("status") == "offen"
                and str(e.get("symbol") or "").upper() == s):
            gewinnzonen_lauf.merker_anwenden(e, {"klimax_gemeldet": z})


def sektor_morgen(topic, state, schon_gemeldet, dry_run):
    """R15 (Gerhard, 12.09.2026): JEDEN MORGEN die drei groessten Aufsteiger
    der Sektor-Rangliste, dazu die Eintritte in die ersten fuenf und die
    fruehen Aufsteiger auf Drei-Monats-Basis (R14, getrennt). Einmal je
    Handelstag. Raenge sind Schlusskurs-Raenge des Vortags und werden so
    benannt; das ist kein Kursalarm, sondern eine Rangfolge."""
    heute_s = (heute_ny() or date.today()).isoformat()
    marke = SEKTORAUF_MARKE + heute_s
    if marke in schon_gemeldet or not push_frei():
        return None
    d = _zusatz_daten().get("sektor")
    if not d or not d[1].get("liste"):
        schon_gemeldet.add(marke)
        return None
    modul, sek = d
    absaetze = []
    ga = sek.get("groesste_aufsteiger") or []
    if ga:
        absaetze.append("Größte Aufsteiger in drei Wochen:\n" + "\n".join(
            f"{i}. {modul.text_fuer(z, mit_linie=False)}; plus {z['aenderung_3w']} Ränge"
            for i, z in enumerate(ga, 1)))
    else:
        absaetze.append("Keine Aufsteiger in drei Wochen")
    ereignisse = ([modul.aufsteiger_text(m) for m in (sek.get("aufsteiger") or [])]
                  + [modul.aufsteiger_text(m) for m in (sek.get("frueh") or [])])
    if ereignisse:
        absaetze.append("Neu unter den ersten fünf oder frühe Aufsteiger auf "
                        "Drei-Monats-Basis:\n"
                        + "\n".join(f"{i}. {x}" for i, x in enumerate(ereignisse, 1)))
    top = [z for z in sek["liste"] if z.get("rang")][:5]
    absaetze.append("Spitze nach Faber-Mittel: " + ", ".join(
        f"{z['rang']} {z['etf']} {z.get('name', '')}".strip() for z in top))
    stand = _datum_de(sek.get("handelstag"))
    absaetze.append(f"Anzeige, kein Filter; Ränge nach dem Schluss vom {stand}")
    titel = f"Sektor-Aufsteiger, Stand Schluss {stand}"
    if dry_run:
        print(f"(Dry-Run) {titel}")
        for a in absaetze:
            print("  " + a.replace("\n", "\n  "))
        schon_gemeldet.add(marke)
        return True
    if sende(topic, titel, absaetze, "default"):
        schon_gemeldet.add(marke)
        state["gemeldet"][marke] = heute_s
        save_state(state)
        return True
    return False


def sektor_radar_hochgerechnet(minuten) -> list:
    """M1 (Gerhard, 12.09.2026): der Sektor-Radar gegen 15:45 mit dem auf
    den ganzen Tag HOCHGERECHNETEN Volumen (eigene Kurve je ETF, gebaut vom
    Nachtscan). Ohne Kurve ist ein ETF nicht verifizierbar und bleibt still."""
    import pandas as pd
    daten = sektor_radar.lade_etf_kurse(leise=True)
    heute = heute_ny() or date.today()
    v50_tage = int(getattr(sektor_radar, "V50_TAGE", 50))
    treffer = []
    for etf, df in daten.items():
        try:
            close = sektor_radar._spalte(df, "close")
            vol = sektor_radar._spalte(df, "volume")
            letzter = pd.to_datetime(sektor_radar._datumsspalte(df).iloc[-1]).date()
            if letzter != heute:
                continue                  # keine heutige Zeile
            richtung = sektor_radar.pruefe_umkehr(close)
            if richtung is None:
                continue
            kurve = volumen.kurve_fuer(etf)
            if kurve is None or len(df) < v50_tage + 2:
                continue                  # nicht verifizierbar
            v50 = float(vol.iloc[-(v50_tage + 1):-1].mean())
            pct = volumen.volume_pct_change(float(vol.iloc[-1]), v50, kurve, minuten)
            if pct is None or pct < sektor_radar.VOL_PCT_SCHWELLE:
                continue
            ma = close.rolling(sektor_radar.MA_TAGE).mean()
            i = sektor_radar.BESTAETIGUNG_ABSTAND + 1
            heute_ab = float(close.iloc[-1] - ma.iloc[-1])
            vorher = float(close.iloc[-i] - ma.iloc[-i]) if len(close) >= i else 0.0
            haelt = heute_ab > vorher if richtung == "hoch" else heute_ab < vorher
            if not haelt:
                continue
            treffer.append({"etf": etf, "name": sektor_radar.ETF_UNIVERSE.get(etf, etf),
                            "richtung": richtung, "volumen_pct": round(pct, 1),
                            "kurs": round(float(close.iloc[-1]), 2)})
        except Exception:
            continue
    return treffer


def schlussnahe_befunde(topic, nacht, basis, ws, state, schon_gemeldet,
                        dry_run):
    """M1, VARIANTE A (Gerhard, 12.09.2026): Was nach den Regeln einen
    Schlusskurs braucht, wird ab 15:45 New York mit den Handelskursen
    gerechnet und VOR 16:00 gemeldet, mit dem Vermerk "Schluss noch offen":
    das Exit-Regelwerk (REGEL), die Klimax-Zeichen (alle fuenf, M3 und M5
    beachtet), Wedge Drop (REGEL, nur wenn die Straffungs-Meldungen an
    sind), Weinstein Stufe 3, der 8-EMA-Hinweis (R19, INFORMATION), das
    Ende der Tagesgeschaefte und der Sektor-Radar mit hochgerechnetem
    Volumen. Der Nachtlauf prueft mit dem echten Schluss nach; faellt die
    Bestaetigung, meldet der Abendbericht die RUECKNAHME (M6). Einmal je
    Handelstag; die gemeldeten Befunde stehen in SCHLUSSNAH_DATEI."""
    minuten = ny_minuten()
    if minuten is None or minuten < SCHLUSSNAHE_MINUTE or not basis:
        return None
    heute = heute_ny() or date.today()
    heute_s = heute.isoformat()
    marke = SCHLUSSNAH_MARKE + heute_s
    if marke in schon_gemeldet:
        return None
    bestand = positionen.laden()
    offen = beobachtungen.offene(bestand)
    haengend = set(KURSE.stale_liste())
    kurse = {}
    for key, e in offen.items():
        sym = str(e.get("symbol") or "").upper()
        if sym in kurse or sym in haengend:
            continue
        q = basis.get(sym)
        if not q:
            continue
        q = dict(q)
        ws_kurse_einblenden({sym: q}, ws)
        k = q.get("close")
        if k and k == k:
            kurse[sym] = q
    eintraege = []

    # 1. Exit-Regelwerk an einer KOPIE des Bestands (Buchfuehrung erst nachts)
    try:
        import copy
        kopie = copy.deepcopy(bestand)
        schluss = {s: float(q["close"]) for s, q in kurse.items()}
        idx = 0
        for e in offen.values():
            seit = _handelstage_seit(e.get("einstieg_datum"), heute) or 0
            idx = max(idx, int(e.get("einstieg_index") or 0) + seit)
        for m in positionen.pruefe_bestand(kopie, schluss, idx):
            if m.get("aktion") == "teilverkauf":
                continue                  # M2 meldet den im Handel selbst
            eintraege.append({"praefix": "REGEL", "typ": "kapitel11",
                              "key": m["symbol"], "symbol": m["symbol"],
                              "zeichen": None,
                              "text": "REGEL: " + positionen.melde_text(m)})
    except Exception as ex:
        print(f"  Schlussnah, Exit-Regelwerk: {type(ex).__name__}: {ex}")

    # 2. je Beobachtung mit heutigem Kurs
    verlaeufe = nacht.get("verlaeufe") or {}
    straffung = gewinnzonen_lauf.straffung_gemeldet()
    for key, e in sorted(offen.items()):
        sym = str(e.get("symbol") or "").upper()
        q = kurse.get(sym)
        if not q:
            continue
        kurs = float(q["close"])
        klasse = e.get("klasse", "standard")
        stand = gewinnzonen_lauf._stand_text(e, kurs, mit_kurs=True)
        strategie = e.get("strategie", "")
        if klasse == "tagesgeschaeft":
            eintraege.append({"praefix": "INFORMATION", "typ": "tagesende",
                              "key": key, "symbol": sym, "zeichen": None,
                              "text": f"INFORMATION: {sym}; {strategie}; "
                                      f"Tagesgeschäft endet mit dem Schluss; " + stand})
            continue
        if klasse == "darvas":
            continue
        verlauf = verlaeufe.get(key)
        daten = (verlauf or {}).get("daten") or []
        letzter = str(daten[-1][0])[:10] if daten else None
        vortag = q.get("prev_datum")
        if not letzter or (vortag is not None and str(vortag) != letzter):
            continue                      # Verlauf passt nicht zu heute
        try:
            df = gewinnzonen_lauf._df_live(verlauf, heute, kurs, q.get("high"), q.get("low"))
            tage = int(verlauf.get("tage", 0)) + 1
            ema8 = gewinnzonen_lauf.ema8_aus(df)
            if ema8 is not None and kurs < ema8:
                eintraege.append({"praefix": "INFORMATION", "typ": "ema8_hinweis",
                                  "key": key, "symbol": sym, "zeichen": None,
                                  "text": f"INFORMATION: {sym}; {strategie}; Kurs "
                                          f"{kurs:.2f} unter der 8-Tage-EMA {ema8:.2f}; "
                                          f"reiner Hinweis, kein Ausstiegssignal; " + stand})
            schon = klimax_je_symbol(bestand, sym)
            klimax = gz.pruefe_klimax_katalog(gewinnzonen_lauf._klimax_eingaben(df, tage))
            zone_vorab = gewinnzonen_lauf.zone_ohne_klimax(e, kurs)
            for z in klimax["ausgeloeste_zeichen"]:
                if z in schon or gewinnzonen_lauf.zeichen_2_zu_frueh(z, zone_vorab):
                    continue
                k = nacht_schluessel({"typ": "klimax_zeichen", "key": key, "zeichen": z})
                if k in schon_gemeldet:
                    continue
                wert = klimax["details"][z].get("wert_pct")
                wert_teil = (f" ({wert:+.1f} %)".replace(".", ",") if wert is not None else "")
                eintraege.append({"praefix": "INFORMATION", "typ": "klimax_zeichen",
                                  "key": key, "symbol": sym, "zeichen": z,
                                  "live": z in gewinnzonen_lauf.KLIMAX_LIVE,
                                  "text": f"INFORMATION: {sym}; {strategie}; Klimax-Zeichen "
                                          f"{z.replace('_', ' ')}{wert_teil}; Verkauf in die "
                                          f"Stärke erwägen; " + stand})
            ziel = e.get("musterziel")
            zone = gz.klassifiziere_zone(
                e["einstieg"], e.get("struktur_stop") or e["aktueller_stop"], kurs,
                musterziel_erreicht=bool(ziel) and kurs >= float(ziel),
                ist_klimax=bool(klimax["ausgeloeste_zeichen"]))["zone"]
            if straffung and zone == "stark" and not e.get("wedge_drop_gemeldet"):
                try:
                    import kell_zyklus
                    phase = kell_zyklus.klassifiziere(df)
                except Exception:
                    phase = None
                if phase == "Wedge Drop":
                    eintraege.append({"praefix": "REGEL", "typ": "wedge_drop",
                                      "key": key, "symbol": sym, "zeichen": None,
                                      "text": f"REGEL: {sym}; {strategie}; Kurs unter der "
                                              f"10er- und 20er-Tageslinie nach der Überdehnung "
                                              f"(Kell Wedge Drop); Ausstieg oder harte "
                                              f"Straffung; " + stand})
            if zone == "stark" and not e.get("weinstein_gemeldet"):
                k = nacht_schluessel({"typ": "weinstein", "key": key})
                if k not in schon_gemeldet:
                    w3, _det = gz.pruefe_weinstein_stufe3(gewinnzonen_lauf._ma30w_serie(df))
                    if w3:
                        eintraege.append({"praefix": "INFORMATION", "typ": "weinstein",
                                          "key": key, "symbol": sym, "zeichen": None,
                                          "text": f"INFORMATION: {sym}; {strategie}; 30-Wochen-"
                                                  f"Linie flacht ab (Weinstein Stufe 3); " + stand})
        except Exception as ex:
            print(f"  Schlussnah {sym}: {type(ex).__name__}: {ex}")

    # 3. Sektor-Radar mit hochgerechnetem Volumen
    try:
        for tr in sektor_radar_hochgerechnet(minuten):
            eintraege.append({"praefix": "INFORMATION", "typ": "sektor_radar",
                              "key": tr["etf"], "symbol": tr["etf"], "zeichen": tr["richtung"],
                              "text": f"INFORMATION: Sektor-Radar {tr['etf']} ({tr['name']}) "
                                      f"dreht nach {'oben' if tr['richtung'] == 'hoch' else 'unten'}; "
                                      f"Volumen hochgerechnet {tr['volumen_pct']:+.0f}% gegenüber "
                                      f"dem 50-Tage-Schnitt; Kurs {tr['kurs']:.2f}"})
    except Exception as ex:
        print(f"  Schlussnah, Sektor-Radar: {type(ex).__name__}: {ex}")

    ny = f"{minuten // 60}:{minuten % 60:02d}"          # ny_minuten() zaehlt Tagesminuten
    ablage = {"handelstag": heute_s, "gemeldet_um_ny": ny,
              "befunde": [{k: v for k, v in x.items() if k != "live"} for x in eintraege]}
    if not eintraege:
        print(f"Schlussnahe Befunde ({ny} New York): keine.")
        if not dry_run:
            Path(SCHLUSSNAH_DATEI).write_text(json.dumps(ablage, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
        schon_gemeldet.add(marke)
        state["gemeldet"][marke] = heute_s
        if not dry_run:
            save_state(state, sofort=True)
        return None
    absaetze = [f"{i}. {x['text']}; Schluss noch offen" for i, x in enumerate(eintraege, 1)]
    absaetze.append(f"Gerechnet um {ny} New York mit den Handelskursen; der Nachtlauf "
                    f"prüft mit dem Schluss nach, Rücknahmen kommen im Abendbericht.")
    prio = "high" if any(x["praefix"] == "REGEL" for x in eintraege) else "default"
    titel = f"Schlussnahe Befunde {_datum_de(heute_s)}, Schluss noch offen: {len(eintraege)}"
    if dry_run:
        print(f"(Dry-Run) {titel}")
        for a in absaetze:
            print("  " + a)
        schon_gemeldet.add(marke)
        return True
    if not sende(topic, titel, absaetze, prio):
        return False
    Path(SCHLUSSNAH_DATEI).write_text(json.dumps(ablage, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    for x in eintraege:
        if x["typ"] == "klimax_zeichen" and x.get("live"):
            # Aus dem Kurs rechenbar, also sofort als gemeldet vermerkt
            # (Zeichen 2 und 3 erst nach der Bestaetigung durch den Schluss).
            klimax_symbolweit(bestand, x["symbol"], {"klimax_gemeldet": x["zeichen"]})
            k = nacht_schluessel({"typ": "klimax_zeichen", "key": x["key"], "zeichen": x["zeichen"]})
            schon_gemeldet.add(k)
            state["gemeldet"][k] = heute_s
        elif x["typ"] == "weinstein":
            e = bestand.get(x["key"])
            if e is not None:
                e["weinstein_gemeldet"] = True
            k = nacht_schluessel({"typ": "weinstein", "key": x["key"]})
            schon_gemeldet.add(k)
            state["gemeldet"][k] = heute_s
        elif x["typ"] == "wedge_drop":
            e = bestand.get(x["key"])
            if e is not None:
                e["wedge_drop_gemeldet"] = True
    positionen.speichern(bestand)
    schon_gemeldet.add(marke)
    state["gemeldet"][marke] = heute_s
    save_state(state, sofort=True)
    print(f"Schlussnahe Befunde gemeldet: {titel}")
    return True


def push_uebersprungen(topic: str, treffer: list[dict]) -> bool:
    """Meldet uebersprungene Kaufpunkte, getrennt von den Ausbruechen.

    Eigene Nachricht und niedrige Dringlichkeit: Es ist eine Auskunft,
    kein Signal. Waere sie in dieselbe Meldung gemischt, stuenden
    handelbare und nicht handelbare Zeilen nebeneinander — und am Handy
    liest man das im Zweifel als eine Liste."""
    if not treffer:
        return False
    absaetze = [f"{i}. {format_uebersprungen(t)}"
                for i, t in enumerate(treffer, 1)]
    titel = (f"{len(treffer)} Kaufpunkt(e) übersprungen"
             + tagesanteil_titel(treffer))
    return sende(topic, titel, absaetze, "default")


def format_treffer(t: dict, kopfzusatz: str = "") -> str:
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
    elif t.get("vol_nicht_verifizierbar"):
        # DER DRITTE STATUS (Gerhard, 06.08.2026). Er darf NICHT mit
        # "nicht bestätigt" zusammenfallen: Dort wurde geprüft und für zu
        # schwach befunden, hier konnte gar nicht geprüft werden, weil
        # diese Aktie keine eigene Volumenkurve hat. Wer beides in
        # denselben Topf wirft, lässt eine Aktie ohne genug Historie
        # lautlos in der falschen Kategorie verschwinden.
        vol_txt = ("Vol NICHT VERIFIZIERBAR, keine eigene Volumenkurve; "
                   "unter 40 Handelstagen Historie")
    else:
        # Keine Durchschnittsbasis (brandneue Notierung oder Datenlücke
        # der Kursquelle) — der Wächter rechnet sonst IMMER selbst.
        vol_txt = "Vol nicht bewertbar, zu wenig Kurshistorie"
    # Erfuellt die Aktie mehrere Muster auf DEMSELBEN Kaufpunkt, wurden sie
    # zu einer Meldung zusammengelegt — dann werden auch beide genannt
    # (Fehlerdurchlauf 28.07.2026). Beistrich innerhalb zusammengehoeriger
    # Angaben, wie ueberall.
    namen = t.get("strategien") or [t["strategie"]]
    strategie = ", ".join(STRATEGIE_VOLL.get(n, n) for n in namen)
    if t.get("folgetag") and not kopfzusatz:
        kopfzusatz = "Bestätigung am Folgetag"          # W1
    zeilen = [
        kopfzeile(t["ticker"], t.get("firma", ""),
                  f"{strategie}; {kopfzusatz}" if kopfzusatz else strategie),
        f"Kaufpunkt {t['kaufpunkt']:.2f}, Kurs {t['kurs']:.2f} "
        f"(+{t['ueber_pct']:.1f}%); {vol_txt}",
    ]
    schluss = []
    if t["stop"] is not None:
        # Abstand vom KAUFPUNKT zum Stop, in Prozent des Kaufpunkts.
        # Bis 06.08.2026 stand hier (kurs / stop - 1): falscher Bezugswert
        # UND falscher Nenner. Bei MNPR ergab das 60,7 % statt 37,4 %.
        risiko = exit_regeln.risiko_pct(t["kaufpunkt"], t["stop"])
        schluss.append(f"Stop {t['stop']:.2f}, Risk {risiko:.1f}%")
    if t["ziel"] is not None:
        chance = (t["ziel"] / t["kurs"] - 1) * 100
        schluss.append(f"Ziel {t['ziel']:.2f} (+{chance:.1f}%)")
    if schluss:
        zeilen.append("; ".join(schluss))
    # R18 (nur Anzeige) sowie R4 bis R6, R16 und R20 (Gerhard, 12.09.2026):
    # EMA-Lage, RS, Sektorrang und Ratings. Entscheidungshilfe, kein Filter.
    for z in (ema_lage_text(t), zusatz_zeile(t.get("ticker"))):
        if z:
            zeilen.append(z)
    # ZAHLEN-TERMIN (Gerhard, 12.08.2026). Ein Ausbruch am Nachmittag ist
    # etwas anderes, wenn dieselbe Firma zwei Stunden spaeter berichtet —
    # dann entscheidet ueber Nacht nicht das Muster, sondern die Zahl.
    #
    # SEIT 13.08.2026 steht ein HEUTIGER Termin in der KOPFZEILE (Mathias'
    # Wunsch, siehe kopfzeile()). Was dort nicht hingehoert — der Termin
    # von morgen und der Vorbehalt bei uneinigen Quellen — steht SEIT
    # 31.08.2026 als ZWEITE Zeile direkt unter dem Kopf (Mathias: "Wenn
    # ein Unternehmen Zahlen bringt, soll dies am Anfang der
    # Push-Mitteilung stehen, nicht wie bisher am Ende"). In der letzten
    # Zeile hatte man genau diesen Hinweis ueberhoert.
    vermerk = termin_nachsatz(t.get("ticker"))
    if vermerk:
        zeilen.insert(1, vermerk)
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
    """Zusatz-Kopfzeile, damit ntfy eine Meldung AUCH als E-Mail zustellt.

    NICHT IN BETRIEB, Stand 31.07.2026. Das Secret NTFY_EMAIL ist im
    Repo gar nicht angelegt (in der Secret-Liste nachgesehen; da stehen
    nur FINNHUB_API_KEY, FMP_API_KEY, NTFY_TOPIC, TRADERFOX_USER,
    TRADERFOX_PASS und TWELVE_DATA_API_KEY). Die Workflows reichen
    NTFY_EMAIL zwar durch, es kommt aber leer an — dann wird hier keine
    Kopfzeile gesetzt und ntfy verschickt keine Mail. Mathias liest die
    Meldungen in der ntfy-App.

    DIE FRUEHERE BEGRUENDUNG HIER WAR FALSCH. Sie lautete, die ntfy-App
    fuer iOS sei fehlerhaft und verlange beim Abonnieren ein Kennwort,
    das es fuer oeffentliche Topics gar nicht gebe. Mathias am
    31.07.2026: "Die App auf iOS ist nicht fehlerhaft, sondern man
    erstellt sich einmalig ein Konto, mit dem man dann alle Themen
    abonieren kann, die ntfy-App auf dem iPhone funktioniert bei uns
    beiden problemlos." Das Kennwort war die normale Anmeldung, kein
    Fehler.

    Damit hat der E-Mail-Weg keinen Grund mehr. Er bleibt nur stehen,
    weil er nichts kostet: ohne Secret keine Kopfzeile. Wird NTFY_EMAIL
    eines Tages angelegt, greift er ohne weitere Aenderung. Soll er ganz
    weg, sind es vier Stellen: diese Funktion, ihre beiden Aufrufe und
    die Zeilen NTFY_EMAIL in alarme.yml und watcher.yml."""
    adresse = (os.environ.get("NTFY_EMAIL") or "").strip()
    return {"Email": adresse} if adresse else {}


# ntfy macht aus einer zu langen Nachricht eine ANGEHAENGTE Textdatei
# ("You received a file: attachment.txt"), die erst heruntergeladen
# werden muss. Genau das ist Mathias am 27.07.2026 passiert, als viele
# Treffer auf einmal kamen — und kostete ihn im Handel wertvolle Zeit.
# Darum wird nie mehr als eine Portion auf einmal verschickt.
#
# DIE GRENZE IST AM 30.07.2026 GENAU AUSGEMESSEN, an einem Wegwerf-Thema
# mit Fuelltext, Laenge fuer Laenge:
#     3900, 4000, 4090, 4095 Zeichen -> kommen normal an
#     4096, 4097, 4100, 4200 Zeichen -> werden zur Datei
# Die Marke heisst also "AB 4096", nicht "ueber 4096". Glatt 4096 zu
# setzen haette jede volle Meldung zur Datei gemacht — genau das, was
# vermieden werden soll. 4095 ist das Aeusserste, was durchgeht.
#
# Die Portionierung rechnet je Absatz zwei Zeichen fuer den Abstand mit,
# auch beim letzten — die tatsaechliche Nachricht ist also noch zwei
# Zeichen kuerzer als der hier gepruefte Wert.
NTFY_GRENZE = 4095


def _portionen(absaetze: list[str], grenze: int = NTFY_GRENZE) -> list[list[str]]:
    """Teilt die Absaetze so auf, dass keine Nachricht die Grenze reisst.
    Getrennt wird NUR zwischen Aktien, nie mitten in einer Meldung.

    EINZIGE Grenze ist die Zeichenzahl (Mathias, 30.07.2026). Eine
    zusaetzliche Obergrenze von fuenf Aktien je Meldung stand am selben
    Tag kurz drin und ist wieder heraus: Sie zerschnitt Meldungen, die
    zusammengehoeren — "sonst kommen 2 Nachrichten auf ein Mal, die eig.
    eine sind"."""
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


# Zeitpunkt (time.monotonic) des letzten angenommenen Pushes; None vor dem
# ersten. Traegt den Mindestabstand des Push-Sammlers (CFG["push"]).
_LETZTER_PUSH = None


def push_abstand_warten(jetzt=None, schlafe=time.sleep) -> float:
    """Wartet, bis seit dem letzten Push der Mindestabstand vergangen
    ist, und gibt die gewartete Zeit in Sekunden zurueck.

    PUSH-SAMMLER (Gerhards Go vom 02.09.2026): Fuenf Pushes binnen einer
    Sekunde kamen am 31.08.2026 alle mit HTTP 200 an, das iPhone zeigte
    aber nur einen Teil; Apples Push-Dienst fasst schnelle Serien zusammen.
    Der Abstand entzerrt die Serie, ohne Meldungen zu verschmelzen: Titel,
    Prioritaet und Reihenfolge bleiben, jede Meldung bleibt fuer sich
    lesbar. Der Waechter prueft im Zwei-Sekunden-Takt und Yahoo liefert
    ohnehin mit Verzug; zehn Sekunden je weiterem Push aendern an der
    Handelbarkeit nichts."""
    abstand = float(CFG.get("push", {}).get("mindestabstand_s", 0) or 0)
    if _LETZTER_PUSH is None or abstand <= 0:
        return 0.0
    jetzt = time.monotonic() if jetzt is None else jetzt
    rest = abstand - (jetzt - _LETZTER_PUSH)
    if rest <= 0:
        return 0.0
    print(f"  Push-Sammler: {rest:.1f} s Abstand zum vorigen Push abgewartet")
    schlafe(rest)
    return rest


def push_frei(jetzt=None) -> bool:
    """Ist der Push-Sammler frei, ohne dass gewartet werden muesste?

    Fuer Meldungen, die NICHT vordraengeln sollen (Nachtbefunde, seit
    10.09.2026): Sie gehen nur hinaus, wenn der Mindestabstand ohnehin
    abgelaufen ist, und halten die Schleife damit nie an."""
    abstand = float(CFG.get("push", {}).get("mindestabstand_s", 0) or 0)
    if _LETZTER_PUSH is None or abstand <= 0:
        return True
    jetzt = time.monotonic() if jetzt is None else jetzt
    return jetzt - _LETZTER_PUSH >= abstand


def handel_paket(treffer: list[dict], art: str = "kauf",
                 anlass: str = "neu") -> list[dict]:
    """Die Zahlen eines Alarms so, wie die Handels-App sie braucht.

    Der Text der Meldung bleibt unveraendert; die App bekommt die Werte
    zusaetzlich als Daten, damit sie beim Bauen der Order nicht raten muss.

    DIE KENNUNG "k" (seit 07.09.2026): Heliot bekommt denselben Alarm auf
    zwei Wegen - beim Antippen der Meldung und beim Abruf aus dem Kanal.
    Ohne eine mitgeschickte Kennung vergibt die App je Weg eine eigene,
    und derselbe Alarm steht zweimal in der Liste. Genommen wird der
    Meldeschluessel, den der Waechter ohnehin fuehrt (Aktie plus
    Kaufpunkt-Nummer, ohne Preis), plus der ANLASS: Derselbe Kaufpunkt
    meldet zweimal - erst der Ausbruch, spaeter der Nachtrag, wenn die
    Volumenbestaetigung nachzieht. Das sind zwei Ereignisse und sollen in
    der App auch zwei bleiben.

    Das Datum haelt Alarme derselben Aktie ueber Tage auseinander; der
    Meldeschluessel selbst gilt eine Woche."""
    heute = date.today().isoformat()
    paket = []
    for t in treffer[:8]:
        eintrag = {"art": art, "sym": t.get("ticker")}
        basis = t.get("key") or t.get("ticker") or "?"
        eintrag["k"] = "%s|%s|%s" % (basis, anlass, heute)
        firma = (t.get("firma") or "")[:40]
        if firma:
            eintrag["firma"] = firma
        namen = t.get("strategien") or ([t.get("strategie")] if t.get("strategie") else [])
        if namen:
            eintrag["muster"] = ", ".join(STRATEGIE_VOLL.get(n, n) for n in namen)[:60]
        for feld, schluessel in (("kaufpunkt", "kp"), ("kurs", "kurs"),
                                 ("stop", "stop"), ("ziel", "ziel")):
            wert = t.get(feld)
            if wert is not None:
                eintrag[schluessel] = round(float(wert), 4)
        paket.append(eintrag)
    return paket


def handel_adresse(paket: list[dict]) -> str | None:
    """Die Adresse, die das Antippen der Meldung oeffnet.

    Ohne die Umgebungsvariable HANDEL_URL passiert gar nichts - der
    Waechter verhaelt sich dann Zeichen fuer Zeichen wie vorher."""
    basis = (os.environ.get("HANDEL_URL") or "").strip()
    if not basis or not paket:
        return None
    daten = json.dumps(paket, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    kurz = base64.urlsafe_b64encode(daten).decode("ascii").rstrip("=")
    return basis + "#a=" + kurz


def erster_je_aktie(gruppen: list[list[dict]]) -> list[dict]:
    """Je Aktie den ersten Kaufpunkt - die App legt eine Order je Aktie
    vor, nicht je gerissener Marke."""
    return [g[0] for g in gruppen if g]


def _sende_eine(topic: str, titel: str, body: str, prio: str,
                klick: str | None = None) -> bool:
    global _LETZTER_PUSH
    # KEINE "Tags"-Kopfzeile (Mathias, 13.08.2026: "Entferne bitte alle
    # Emojis aus den Meldungen, Raketen, Diagramme etc. nerven nur").
    # Genau daraus baut ntfy die Bildchen: "rocket" wurde zur Rakete,
    # "chart_with_upwards_trend" zum Diagramm, "fast_forward" zum
    # Vorspul-Zeichen. Ohne die Kopfzeile bleibt die Meldung Text.
    push_abstand_warten()
    if not HANDELSZEIT_EGAL:
        # Nach der Wartezeit noch einmal auf die Uhr sehen: Der Abstand
        # darf keinen Push ueber den Schlussgong schieben.
        offen, grund = markt_offen()
        if not offen:
            print(f"⛔ NICHT gesendet — Börse geschlossen ({grund}), "
                  f"nach dem Warten des Push-Sammlers.")
            return False
    kopf = {"Title": titel.encode("utf-8"), "Priority": prio}
    # Antippen der Meldung oeffnet die Handels-App mit genau diesen
    # Alarmen - aber nur, wenn HANDEL_URL gesetzt ist.
    if klick:
        kopf["Click"] = klick
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
    _LETZTER_PUSH = time.monotonic()
    print(f"Push gesendet an ntfy.sh/{topic} ({len(body)} Zeichen, "
          f"HTTP {r.status_code})")
    return True


# Notbremse fuer die Handelszeit. Wird in main() aus
# --ignoriere-handelszeit gesetzt und gilt NUR fuer Testlaeufe von Hand.
HANDELSZEIT_EGAL = False


def sende(topic: str, titel: str, absaetze: list[str], prio: str,
          klick: str | None = None) -> bool:
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
        if not _sende_eine(topic, kopf, "\n\n".join(teil), prio, klick):
            alle_ok = False
    return alle_ok


def push_text(topic: str, titel: str, body: str) -> bool:
    """Schickt eine frei formulierte Meldung (fuer Gap and Go).

    MIT Titel-Kopfzeile: Der Titel war am 23.07. als 'Wortgeklingel'
    entfernt worden — ohne ihn setzt ntfy aber einen generischen Titel
    (die Themen-Adresse) ein, was schlimmer ist. Am 24.07. auf Mathias'
    Wunsch wiederhergestellt."""
    return sende(topic, titel, body.split("\n\n"), "high")


def tagesanteil_titel(treffer: list[dict]) -> str:
    """Wie viel des Handelstages ueblicherweise schon gelaufen ist —
    als Anhaengsel fuer den Titel (Mathias, 30.07.2026).

    Die Zahl stand frueher im Text jeder einzelnen Meldung
    ("hochgerechnet, 16% des Tages") und war dort in JEDER Zeile
    wortgleich; am 29.07. flog sie deshalb heraus. Im Titel steht sie
    genau einmal und sagt, wie belastbar die Volumenzahlen sind:
    Nachgemessen (volumen_verlaesslichkeit.py) ist ein 'bestaetigt' um
    10:00 New Yorker Zeit zu 36 % bis zum Schluss hinfaellig, um 14:00
    nur noch zu 5 %.

    Vor Handelsbeginn und nach Schluss ist der Anteil 1,0 — dann sagt
    die Angabe nichts und bleibt weg.

    "0% des Tages" IST ABSICHT und wird nicht auf "unter 1 %"
    verschoenert (Mathias, 19.08.2026, ausdruecklich: "lass es auf 0%,
    dann weiss man, dass es quasi noch wertlos ist"). Die Null sagt dem
    Leser ehrlich, dass die Volumen-Hochrechnung zu dieser Uhrzeit noch
    nichts wert ist — genau das soll sie."""
    anteile = [t.get("vol_anteil") for t in treffer
               if t.get("vol_anteil") is not None]
    if not anteile:
        return ""
    anteil = min(anteile)
    if anteil >= 0.99:
        return ""
    return f"; {anteil * 100:.0f}% des Tages"


NACHTRAG_MARKE = "BEST|"


def kp_namen(t: dict) -> list[str]:
    """Die Muster eines Kaufpunkts, sortiert und ohne Doppel. Liegen zwei
    Muster auf demselben Preis, sind es beide (siehe
    _lege_gleiche_preise_zusammen)."""
    namen = t.get("strategien") or [t.get("strategie")]
    return sorted({str(n) for n in namen if n}) or ["?"]


def ausbruch_schluessel_alle(t: dict) -> list[str]:
    """Die Meldeschluessel eines Ausbruchs: Aktie plus MUSTER, je Muster
    einer.

    OHNE Preis (Mathias, 27.07.2026): Der Kaufpunkt wandert taeglich mit
    dem Musterdeckel nach oben; steckte er im Schluessel, galte derselbe
    Ausbruch am naechsten Tag als neu.

    NACH MUSTER statt nach Platznummer (Befund 09.09.2026, gebaut
    10.09.2026): Die Nummer ist nur der Platz in der Mappe, und der
    wandert, sobald der Nachtscan ein Muster davor setzt. LITE trug am
    08.09. Rectangle Top auf Platz 1; am 09.09. stand dort Cup & Handle,
    das Rectangle Top auf Platz 3. Folge in BEIDE Richtungen: Das schon
    gemeldete Rectangle Top kam als "LITE|3" ein zweites Mal, und der
    echte Ausbruch aus Cup & Handle blieb unter dem belegten "LITE|1"
    stumm. Gemessen zeigten am 09.09. 181 von 720 Schluesseln auf einen
    anderen Kaufpunkt als am Vortag.

    JE MUSTER EIN SCHLUESSEL: Liegen zwei Muster auf demselben Preis,
    werden beide gesetzt; getrennt sich die Preise spaeter, ist keiner
    von beiden neu.

    High and Tight Flag traegt ein Vorzeichen, damit load_state() ihr die
    taegliche statt der woechentlichen Frist geben kann."""
    namen = kp_namen(t)
    # Der Innen-Einstieg gehoert zur selben Flagge und bekommt dieselbe
    # TAEGLICHE Frist (Soreide-Ausbau, 31.08.2026) — sonst waere die
    # engere Marke eine Woche lang stumm, waehrend die Flagge selbst
    # jeden Tag neu melden darf.
    marke = (HTF_MARKE if any(n in ("High & Tight Flag",
                                    "HTF Innen-Einstieg")
                              for n in namen) else "")
    return [f"{marke}{t['ticker']}|{n}" for n in namen]


def ausbruch_schluessel(t: dict) -> str:
    """Der erste der Meldeschluessel (fuer Anzeige, Logbuch und die
    Kennung der Handels-App)."""
    return ausbruch_schluessel_alle(t)[0]


def uebersprungen_schluessel_alle(t: dict) -> list[str]:
    """Die Meldeschluessel der Meldung 'Kaufpunkt uebersprungen', je
    Muster einer (siehe ausbruch_schluessel_alle)."""
    return [f"{UEBERSPRUNGEN_MARKE}{t['ticker']}|{n}" for n in kp_namen(t)]


def uebersprungen_schluessel(t: dict) -> str:
    """Der Meldeschluessel der Meldung 'Kaufpunkt uebersprungen'."""
    return uebersprungen_schluessel_alle(t)[0]


def fenster_schluessel(t: dict) -> str:
    """Wo das Einstiegsfenster eines Kaufpunkts im Tageszustand steht:
    Aktie plus Muster, wie die Meldeschluessel."""
    return f"{t['ticker']}|{' + '.join(kp_namen(t))}"


def vortagesschluss(item, quote):
    """Der Schlusskurs des Vortags, aus ZWEI Quellen. Oder None.

    1. prev_close aus dem Kursabruf. Das ist der Normalfall; gemessen am
       14.08.2026 lag er bei 235 von 235 Aktien vor.
    2. Der Kurs aus der Kaufpunkt-Mappe. Der Nachtlauf rechnet nach dem
       New Yorker Schluss, sein Kurs IST der Vortagesschluss; an fuenf
       Aktien gegengeprueft, null Abweichung.

    WARUM ZWEI (Mathias, 14.08.2026): Ohne die zweite Quelle muesste man
    entscheiden, was bei einem fehlenden Vortagesschluss geschieht, und
    beide Antworten waeren schlecht. Schweigen laesst einen echten Fall
    verschwinden, und das Protokoll liest niemand ("Das Protokoll liest
    ausser dir niemand"). Melden dagegen oeffnet eine Hintertuer: Faellt
    der Kursabruf einmal breit aus, gelten schlagartig ALLE
    Ruecksetzer-Marken als unklar, und die 114 Meldungen vom Morgen des
    14.08. waeren zurueck. Die zweite Quelle loest den Streit, statt ihn
    zu entscheiden - sie ist gerade dann da, wenn der Abruf hakt, denn
    sie steht in einer Datei.

    Fallen BEIDE aus, wird geschwiegen (Mathias' Entscheidung: "lasse die
    Meldung bei Doppelausfall ganz weg, sonst passiert das, was du gesagt
    hast")."""
    v = quote.get("prev_close") if quote else None
    # NaN ist wahr - ein leerer Yahoo-Tag (18.08.2026) saehe sonst wie
    # ein vorhandener Vortagesschluss aus. v == v ist nur bei NaN falsch.
    if v and v == v:
        return float(v)
    k = (item or {}).get("kurs_scan")
    return float(k) if (k and k == k) else None


def kam_von_unten(res) -> bool:
    """Wurde dieser Kaufpunkt ueberhaupt von UNTEN gerissen?

    MATHIAS' EINWAND vom 14.08.2026, und er hat den ganzen Fall geklaert:
    "Die Aktien kommen also idealerweise von unter dem Kaufpunkt, oder?"

    Ohne diese Frage meldet der Waechter Unsinn, und zwar massenhaft. Der
    Nachtlauf erzeugt zu jeder Aktie ohne sauberes Muster eine
    RUECKSETZER-Marke ("Fallback: MA50-Pullback") - ein Kurs, auf den man
    warten wuerde, wenn die Aktie zurueckfaellt. So eine Marke liegt
    bauartbedingt UNTER dem Kurs, oft weit: Bei TEAM stand der Kurs am
    14.08.2026 bei 165,98, die Marke bei 98,21, also 69 % darunter. Die
    Pruefung "liegt der Kurs mehr als 5 % ueber dem Kaufpunkt?" ist dort
    jeden Tag wahr, ohne dass irgendetwas geschehen waere.

    GEMESSEN an genau diesem Tag: 114 Kaufpunkte lagen ueber der Grenze,
    davon 108 solche Ruecksetzer-Marken. Nur SECHS kamen wirklich von
    unten. Ohne diese Bedingung waeren 114 Meldungen an einem Morgen
    hinausgegangen.

    NICHT geprueft wird die Musterqualitaet - das war mein erster
    Vorschlag, und Mathias hat ihn zu Recht verworfen: "Bei Sea wissen
    wir nicht, ob er einem Muster entsprochen hat. Genau die wollen wir
    ja eben nicht ausschliessen." Nachgemessen stimmt beides: Sea kam aus
    einem echten Muster (Cup and Handle, Kaufpunkt 115,91; Schluss am
    10.08. 114,80, Eroeffnung am 11.08. 127,87), aber von den sechs
    echten Faellen des 14.08. stammten VIER aus Fallback-Marken - ETON,
    UMAC, AAOI und MP. Ein Ausschluss nach Kategorie haette gerade die
    weggeworfen. Gefragt wird also nicht, woher der Kaufpunkt kommt,
    sondern ob wirklich etwas passiert ist.

    OHNE VORTAGESSCHLUSS gilt der Fall als NICHT von unten gekommen. Das
    ist die stille Richtung, und bei 114 gegen 6 ist sie die richtige;
    die Alternative waere, im Zweifel hundertfach zu melden."""
    vortag = res.get("vortagesschluss")
    kp = res.get("kaufpunkt")
    if vortag is None or kp is None:
        return False
    return float(vortag) < float(kp)


def riss_schon_gestern(res) -> bool:
    """Wurde dieser Kaufpunkt schon GESTERN gerissen? Dann ist die heutige
    Meldung keine neue.

    MATHIAS BEFUND vom 11.09.2026, Frage M4 an Gerhard: Um 15:31 kamen
    MATX, ALSN und OOMA als frische Ausbrueche - bei allen drei lag schon
    der Schlusskurs des Vortags UEBER dem Kaufpunkt. Nachgemessen am
    Trigger-Logbuch traf das auf 12 von 57 Ausbruechen der Tage 09. bis
    11.09.2026 zu, und jeder davon wurde in den ersten Minuten nach der
    Eroeffnung gemeldet. DREI Wege fuehren dorthin: Der Kaufpunkt wurde
    gestern gerissen, blieb ohne Volumenbestaetigung und damit still; der
    Nachtscan setzte einen neuen Kaufpunkt UNTER den Schlusskurs; oder
    dieselbe Aktie kam unter einer zweiten Platznummer noch einmal (das
    ist seit 10.09.2026 behoben).

    Eine solche Meldung ist ein Vortagesalarm in neuem Kleid, und genau
    den soll es nicht geben (Mathias, 10.09.2026: "Es darf nie wieder
    etwas vom Vortag kommen"). Der NACHTRAG bleibt unberuehrt: Wurde der
    Ausbruch am Tag des Risses gemeldet, darf die Volumenbestaetigung
    weiter nachziehen - dort steht der Schluessel schon im Gedaechtnis.

    OHNE VORTAGESSCHLUSS wird GEMELDET, also genau umgekehrt zu
    kam_von_unten(). Dort geht es um Ruecksetzer-Marken, die bauartbedingt
    unter dem Kurs liegen (114 gegen 6 am 14.08.2026) - im Zweifel
    schweigen ist die richtige Richtung. Hier geht es um echte Ausbrueche;
    ein breiter Ausfall des Kursabrufs darf nicht dazu fuehren, dass der
    Waechter ueberhaupt nichts mehr meldet.

    ZWISCHENLOESUNG bis zu Gerhards Antwort auf M4; abschaltbar ueber
    config.py, betrieb.nur_frische_ausbrueche."""
    vortag = res.get("vortagesschluss")
    kp = res.get("kaufpunkt")
    if vortag is None or kp is None:
        return False
    return float(vortag) >= float(kp)


def fallback_ohne_riss(res: dict) -> bool:
    """True, wenn eine reine AUSWEICH-Marke heute gar nicht gerissen
    wurde - dann wird sie in KEINEM Meldeweg angefasst.

    Seit 19.08.2026 laufen die Ausweich-Marken des Nachtscans mit
    (--alle im Workflow; Mathias: "Ich habe den anderen Schalter
    gemeint" - gemeint war nach dem AEHR-Befund, dass Aktien ohne
    Muster an ihren Marken melden sollen). Die Ruecksetzer-Marke
    "Fallback: MA50-Pullback" liegt aber bauartbedingt UNTER dem Kurs:
    GEMESSEN am 19.08.2026 standen 32 der 252 Aktien allein am
    Dienstagsschluss im 0-5-%-Meldefenster ihrer Ruecksetzer-Marke,
    ohne dass dort irgendetwas geschehen waere (die 52-Wochen- und
    20-Tage-Marken dagegen: null - die liegen ueber dem Kurs und
    melden nur echte Durchbrueche). Deshalb gilt hier dasselbe Prinzip
    wie bei den uebersprungenen Kaufpunkten (Mathias, 14.08.2026):
    Gefragt wird nicht, woher der Kaufpunkt kommt, sondern ob wirklich
    etwas passiert ist - der Vortagesschluss muss UNTER der Marke
    liegen. Ohne Vortagesschluss gilt still (114 gegen 6).

    Muster-Kaufpunkte bleiben unberuehrt; deckt ein Kaufpunkt Muster
    UND Marke ab (gleicher Preis), zaehlt das Muster."""
    namen = res.get("strategien") or [res.get("strategie")]
    if not all(str(n or "").startswith("Fallback") for n in namen):
        return False
    return not kam_von_unten(res)


def melde_uebersprungen(res, wechsel, schon_gemeldet) -> bool:
    """Darf dieser uebersprungene Kaufpunkt gemeldet werden? DREI Riegel.

    1. Es muss ein WECHSEL sein (Tageszustand, siehe fenster_wechsel).
    2. Der Kaufpunkt muss von UNTEN gerissen worden sein (kam_von_unten).
    3. Er darf nicht ohnehin schon als draussen angesagt sein
       (Wochengedaechtnis) - sonst meldete derselbe Vorgang taeglich neu.

    Steht als eigene Funktion hier statt verstreut in der Schleife, aus
    demselben Grund wie melde_stufe(): damit man sie pruefen kann."""
    return (wechsel == "verlassen" and kam_von_unten(res)
            and not any(k in schon_gemeldet
                        for k in uebersprungen_schluessel_alle(res)))


DRIN, DRAUSSEN = "drin", "draussen"


def fenster_zustand(ueber: float, vorher: str | None) -> str | None:
    """In welchem Zustand ist das Einstiegsfenster JETZT?

    'ueber' ist der Abstand zum Kaufpunkt als Anteil (0,051 = 5,1 %).
    Rueckgabe: DRIN, DRAUSSEN — oder None, wenn nichts entschieden wird
    und der bisherige Zustand gilt.

    DIE TOTZONE, und warum es sie gibt (gemessen am 13.08.2026 an
    MNDY-Minutendaten, Mathias' Fall): Ohne sie pendelt ein Kurs, der
    genau auf der Grenze liegt, staendig hin und her. MNDY hat die
    Fuenf-Prozent-Linie an diesem Tag sechsmal ueberquert und haette
    NEUN Meldungen in 22 Minuten erzeugt; mit einer Totzone von einem
    Prozentpunkt war es EINE. Und das ist noch geschoent: Gemessen wurde
    an Minutenkerzen, der Waechter prueft alle zwei Sekunden.

    Hinaus geht es also ueber der Grenze, herein erst wieder DEUTLICH
    darunter. Steht die Totzone auf 0, gibt es die Reinform: jede
    Ueberquerung zaehlt.

    WIE GROSS die Totzone ist, hat GERHARD entschieden (13.08.2026, ueber
    Mathias): zwei Prozentpunkte, also hinaus ueber 5 % und wieder herein
    erst bei 3 % oder darunter. Meine Messung hatte einen Prozentpunkt
    nahegelegt, das haette gereicht, um das Zappeln zu beenden; seine
    Fassung verlangt zusaetzlich, dass der Kurs wirklich in die Kaufzone
    zurueckkommt und nicht bloss an ihrem Rand kratzt. Der Wert steht in
    config.py und nur dort."""
    if ueber > NACHLAUF_GRENZE:
        return DRAUSSEN
    if ueber <= NACHLAUF_GRENZE - WIEDEREINTRITT_TOTZONE:
        return DRIN
    return None if vorher else DRIN


def fenster_wechsel(neu: str | None, vorher: str | None) -> str | None:
    """Was ist zu melden? 'verlassen', 'wiedereintritt' oder nichts.

    Der ERSTE Blick auf einen Kaufpunkt ist kein Wechsel — mit einer
    Ausnahme: Liegt der Kurs schon beim ersten Mal ueber der Grenze, ist
    das genau der Fall, fuer den es die Meldung gibt (Gerhards Fall Sea
    am 11.08.2026: 10,3 % Eroeffnungsluecke, der Kaufpunkt wurde nie
    angesagt). Der wird gemeldet."""
    if neu is None or neu == vorher:
        return None
    if neu == DRAUSSEN:
        return "verlassen"
    return "wiedereintritt" if vorher == DRAUSSEN else None


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
    # Je Muster ein Schluessel (seit 10.09.2026); einer genuegt.
    keys = res.get("keys") or [res["key"]]
    keys_best = res.get("keys_best") or [res["key_best"]]
    if not any(k in schon_gemeldet for k in keys):
        # ZWISCHENLOESUNG M4 (Mathias, 11.09.2026): Ein Ausbruch, der
        # schon gestern gerissen wurde, ist heute keine neue Meldung.
        # Steht ausdruecklich VOR der Volumenpruefung: Sonst kaeme
        # derselbe Fall morgen als Nachtrag wieder.
        if riss_schon_gestern(res):
            if NUR_FRISCHE_AUSBRUECHE:
                return None
            # W1 (Gerhard, 12.09.2026): "Bestaetigung am Folgetag" wird
            # GEMELDET, nicht unterdrueckt; aber nur MIT Volumenbestaetigung
            # (sonst ist es keine Bestaetigung) und nur innerhalb des
            # Einstiegsfensters bis 5 Prozent, das der Fensterzustand davor
            # prueft. M4, Moeglichkeit 2: Der Fensterzustand bleibt ueber
            # Nacht (load_state), der Wiedereintritt laeuft ueber die Totzone.
            if res["vol_ok"] is not True:
                return None
            res["folgetag"] = True
        # SEIT 12.08.2026 (Gerhard): Ohne Volumenbestaetigung melden nur
        # noch die Muster, bei denen das Volumen TEIL des Musters ist.
        # Alle uebrigen bleiben still und kommen erst als Nachtrag, wenn
        # die Bestaetigung nachzieht — verloren geht also nichts, es
        # kommt nur spaeter und dafuer belastbar.
        #
        # AUSDRUECKLICH NICHT betroffen ist der dritte Status "nicht
        # verifizierbar" (vol_ok is None). Der heisst "konnte gar nicht
        # geprueft werden" und ist etwas anderes als "geprueft und zu
        # schwach"; ihn mit zu unterdruecken wuerde genau die
        # Unterscheidung aufheben, auf der Gerhard am 06.08.2026
        # bestanden hat.
        if res["vol_ok"] is False and not darf_unbestaetigt_melden(res):
            return None
        return "neu"
    if (res["vol_ok"] is True
            and not any(k in schon_gemeldet for k in keys_best)):
        return "nachtrag"
    return None


def darf_unbestaetigt_melden(res: dict) -> bool:
    """Darf dieser Treffer OHNE Volumenbestaetigung gemeldet werden?

    Deckt ein Kaufpunkt mehrere Muster ab (zusammengelegte gleiche
    Preise), genuegt EINES aus der Liste — sonst verloere die Meldung
    ein Muster, das fuer sich allein melden duerfte."""
    namen = res.get("strategien") or [res.get("strategie")]
    return any(n in UNBESTAETIGT_ERLAUBT for n in namen)


def gruppiere_je_aktie(treffer: list[dict]) -> list[list[dict]]:
    """Treffer nach Aktie buendeln, Reihenfolge des ersten Auftretens."""
    gruppen: dict = {}
    for t in treffer:
        gruppen.setdefault(t["ticker"], []).append(t)
    return list(gruppen.values())


def format_aktie(gruppe: list[dict], nummer: int | None = None) -> str:
    """EINE Meldung je Aktie, egal wie viele Kaufpunkte gerissen sind.

    UNTERNUMMERN seit dem 19.08.2026 (Mathias, gleich nach dem Einbau
    der Buendelung): "Fuege vor den einzelnen Kaufpunkten 1.1 bzw 1.2
    hinzu, dann weiss man gleich, wo der Erste aufhoert und der zweite
    beginnt." `nummer` ist die Blocknummer der Aktie in der Nachricht;
    Kaufpunkt j traegt dann `nummer.j` vor dem Musternamen. Ohne
    Blocknummer (einzelne Aktie im Nachtrag) zaehlt es als Block 1.

    Die KOPFZEILE des Buendels traegt SELBST KEINE Blocknummer (Mathias,
    19.08.2026, gleich danach: "Gib den 1er im Header wieder weg, den
    brauchen wir nicht") - die Nummer des Blocks hoert man ohnehin in
    jeder Unternummer. Aktien mit nur EINEM Kaufpunkt behalten ihre
    schlichte Nummer wie eh und je.

    Mathias am 19.08.2026, nachdem ASC zur Eroeffnung zwei getrennte
    Meldungen bekommen hatte: "Buendeln mehrerer Kaufpunkte in einer
    Meldung pro Aktie ist definitiv sinnvoller." Der Nachtscan vergibt
    je Aktie bis zu drei Kaufpunkte auf verschiedenen Preisen; reisst
    ein Eroeffnungssprung mehrere zugleich, stand dieselbe Aktie
    mehrfach in der Nachricht.

    EIN Kaufpunkt: unveraendert die gewohnte Meldung. MEHRERE: eine
    Kopfzeile ("N Kaufpunkte gerissen", samt Zahlen-Termin), darunter je
    Kaufpunkt seine gewohnten Zeilen, vorangestellt der Mustername mit
    Doppelpunkt - Stop und Ziel sind je Kaufpunkt verschieden und
    bleiben deshalb je Kaufpunkt stehen. Der Termin-Nachsatz steht nur
    EINMAL, seit 31.08.2026 direkt unter der Kopfzeile statt am Ende
    (Mathias: "am Anfang der Push-Mitteilung")."""
    if len(gruppe) == 1:
        text = format_treffer(gruppe[0])
        return f"{nummer}. {text}" if nummer else text
    erster = gruppe[0]
    zeilen = [kopfzeile(erster["ticker"], erster.get("firma", ""),
                        f"{len(gruppe)} Kaufpunkte gerissen")]
    basis = nummer if nummer else 1
    nachsatz = termin_nachsatz(erster.get("ticker"))
    if nachsatz:
        zeilen.append(nachsatz)
    for j, t in enumerate(gruppe, 1):
        koerper = format_treffer(t).split("\n")[1:]
        # format_treffer traegt den Nachsatz als ERSTE Koerperzeile —
        # im Buendel steht er schon oben, also je Kaufpunkt entfernen.
        if nachsatz and koerper and koerper[0] == nachsatz:
            koerper = koerper[1:]
        namen = t.get("strategien") or [t["strategie"]]
        label = ", ".join(STRATEGIE_VOLL.get(n, n) for n in namen)
        if koerper:
            koerper[0] = f"{basis}.{j} {label}: {koerper[0]}"
        zeilen.extend(koerper)
    return "\n".join(zeilen)


def push_nachtrag(topic: str, treffer: list[dict]) -> bool:
    """Meldet, dass ein zuvor UNBESTAETIGT gemeldeter Ausbruch inzwischen
    die Volumenbestaetigung bekommen hat.

    Warum es das gibt (nachgemessen 29.07.2026,
    volumen_verlaesslichkeit.py): Ein 'nicht bestaetigt' um 10:00 New
    Yorker Zeit wird in 14,7 % der Faelle bis zum Handelsschluss doch
    noch bestaetigt. Seit Gerhards Regel vom 12.08.2026 betrifft das nur
    noch die Muster, die unbestaetigt melden duerfen — genau dort sagt
    der eigene Wortlaut "Vol jetzt bestätigt", dass dies die
    Bestaetigung der frueheren Meldung ist und kein neuer Ausbruch.

    ZUR GESCHICHTE, damit das niemand wieder umbaut: Am 18.08.2026
    vormittags auf Mathias' Wunsch in eine gewoehnliche Meldung
    verwandelt, am selben Tag nach seiner Klarstellung zurueckgeholt —
    sein Anliegen war ein Missverstaendnis gewesen (er glaubte, spaeter
    bestaetigte Meldungen wuerden mit den Unbestaetigten unterdrueckt;
    unterdrueckt wird aber nichts, beides kommt an). Wortlaut: "dort hat
    es ja einen Sinn."

    Der Nachtrag ist fuer sich allein handelbar: Kurs, Stop und Ziel
    stehen auf dem AKTUELLEN Stand. Die erste Meldung von vor drei
    Stunden zurueckzusuchen waere umstaendlich, und ihre Zahlen sind
    inzwischen ueberholt."""
    if not treffer:
        return True
    # Nur die KUERZEL in den Titel (Mathias, 30.07.2026). Firmennamen
    # sind dort zu lang und die Push-Vorschau schneidet ab; der Name
    # steht ohnehin in der ersten Zeile jedes Eintrags.
    # Jedes Kuerzel nur einmal im Titel, auch wenn mehrere Kaufpunkte
    # derselben Aktie nachziehen (Buendelung, Mathias 19.08.2026).
    # Ziehen MEHRERE Volumina zugleich nach, sagt der Titel die Zahl
    # ("2 Volumina jetzt bestätigt", Mathias 19.08.2026); bei einem
    # bleibt es beim gewohnten "Vol jetzt bestätigt".
    kuerzel = ", ".join(dict.fromkeys(t["ticker"] for t in treffer))
    wortlaut = ("Vol jetzt bestätigt" if len(treffer) == 1
                else f"{len(treffer)} Volumina jetzt bestätigt")
    titel = f"{kuerzel}: {wortlaut}" + tagesanteil_titel(treffer)
    gruppen = gruppiere_je_aktie(treffer)
    if len(gruppen) == 1:
        absaetze = [format_aktie(gruppen[0])]
    else:
        absaetze = [format_aktie(g, i) for i, g in enumerate(gruppen, 1)]
    return sende(topic, titel, absaetze, "high",
                 handel_adresse(handel_paket(treffer, anlass="nachtrag")))


def push(topic: str, treffer: list[dict]) -> bool:
    """Schickt die Meldung und sagt ehrlich, ob sie angekommen ist.

    Der Rueckgabewert ist wichtig: Frueher wurde der Zustand auch dann als
    'gemeldet' gespeichert, wenn der Push fehlschlug - der Treffer waere
    danach NIE wieder gemeldet worden."""
    # JE AKTIE EIN BLOCK (Mathias, 19.08.2026): Alle gerissenen
    # Kaufpunkte einer Aktie stehen unter einer Nummer. Bestaetigte
    # Aktien zuerst; eine Aktie zaehlt als bestaetigt, sobald EINER
    # ihrer Kaufpunkte die Volumenbestaetigung hat. Auch der Titel
    # zaehlt seither AKTIEN, nicht Kaufpunkte - "2 bestätigt" heisst
    # zwei Aktien, egal wie viele Marken sie gerissen haben.
    gruppen = gruppiere_je_aktie(treffer)
    bestaetigt = [g for g in gruppen
                  if any(t["vol_ok"] is True for t in g)]
    rest = [g for g in gruppen if g not in bestaetigt]
    # Durchlaufende Nummern ueber alle Portionen hinweg — beim Vorlesen
    # soll die zweite Nachricht mit '6.' weitergehen, nicht wieder mit '1.'.
    absaetze = [format_aktie(g, i)
                for i, g in enumerate(bestaetigt + rest, 1)]
    # Titel am 24.07.2026 wiederhergestellt: Ohne Title-Kopfzeile setzt
    # ntfy einen generischen Titel (die Themen-Adresse) ein — das war
    # schlimmer als das am 23.07. beanstandete 'Wortgeklingel'.
    # Seit 29.07. ohne Emoji (Mathias) und kuerzer: Er entscheidet am
    # Titel, ob sich das Oeffnen ueberhaupt lohnt.
    #
    # HIER KOMMT KEIN ZAHLEN-TERMIN HINEIN, und das ist eine Entscheidung,
    # keine Luecke (Mathias, 13.08.2026 — gebaut, vorgefuehrt, verworfen):
    # "Die offenen wollen wir nur bei bestimmten Mustern wissen, d.h.
    # kommt die Sammelmeldung wirklich durcheinander."
    # Der Titel zaehlt bestaetigte und offene AKTIEN. Wie viele 'offen'
    # sind, haengt seit Gerhards Regel vom 12.08.2026 davon ab, welche
    # Muster ueberhaupt unbestaetigt gemeldet werden duerfen — die Zahl
    # ist also schon erklaerungsbeduerftig. Eine dritte, ganz anders
    # geartete Angabe daneben macht aus einer Sammelmeldung ein Raetsel.
    # Der Zahlen-Termin steht deshalb NUR in der ersten Zeile der
    # betroffenen Aktie (siehe kopfzeile()), wo er eindeutig zu ihr
    # gehoert.
    titel = (f"{len(bestaetigt)} bestätigt"
             + (f", {len(rest)} offen" if rest else "")
             + tagesanteil_titel(treffer))
    return sende(topic, titel, absaetze,
                 "high" if bestaetigt else "default",
                 handel_adresse(handel_paket(erster_je_aktie(bestaetigt + rest))))


def testpush(topic: str) -> int:
    """Schickt eine einzelne Testnachricht, damit die Push-Kette einmal
    nachweislich geprueft ist. Ohne Kursdaten, ohne Zustandsaenderung."""
    adresse = (os.environ.get("NTFY_EMAIL") or "").strip()
    weg = f"E-Mail an {adresse}" if adresse else "ntfy-App / Browser"
    # PROBEALARM (Mathias, 05.09.2026): Die Testnachricht traegt seither
    # dieselben Angaben wie ein echter Ausbruch UND die Klick-Adresse der
    # Handels-App - so laesst sich der ganze Weg bis zur Vorschau bei
    # DEGIRO ueben, ohne auf einen echten Alarm zu warten.
    #
    # Die Zahlen sind bewusst so gewaehlt, dass eine versehentlich
    # abgeschickte Order NICHT ausfuehrbar waere: Das Limit liegt weit
    # unter dem Kurs (NBTX stand am 04.09.2026 bei 38,90).
    probe = [{"art": "kauf", "sym": "NBTX", "firma": "PROBE Nanobiotix ADR",
              "muster": "Probealarm", "kp": 12.0, "kurs": 12.05,
              "stop": 10.0, "ziel": 15.0,
              # Eigene Kennung je Probealarm: Zwei Proben hintereinander
              # sind zwei Alarme und sollen in der App auch zwei bleiben.
              "k": "probe|%s" % datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}]
    klick = handel_adresse(probe)
    text = ("PROBEALARM, kein echter Kaufpunkt.\n\n"
            "NBTX (PROBE Nanobiotix ADR); Probealarm\n"
            "Kaufpunkt 12.00, Kurs 12.05 (+0.4%); Vol BESTÄTIGT, Probe\n"
            "Stop 10.00, Risk 16.7%; Ziel 15.00 (+24.5%)\n\n"
            "Das Limit liegt weit unter dem Kurs, die Order wäre also "
            "nicht ausführbar.\n"
            f"Zustellweg: {weg}\n"
            + ("Antippen öffnet die Handels-App.\n" if klick
               else "Ohne HANDEL_URL: Antippen öffnet nichts.\n")
            + f"Gesendet: {datetime.now():%d.%m.%Y %H:%M:%S}")
    kopf = {"Title": "PROBEALARM Breakout-Wächter".encode("utf-8"),
            "Priority": "default"}
    if klick:
        kopf["Click"] = klick
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
                    help=f"Statt einmal zu prüfen alle {PRUEF_TAKT} Sekunden "
                         f"weiterprüfen, "
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

    # Kapitel 9 braucht die nachts gebaute Fokusliste. Ihre Aktien sind
    # eine Teilmenge des Gap-and-Go-Universums, bekommen also ohnehin
    # Kurse — es kommt kein einziger Abruf dazu.
    global _r2g_fokus
    _r2g_fokus = r2g_fokusliste_laden()

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
    # NACHTBEFUNDE ZUM HANDELSSTART (Mathias, 10.09.2026): Ihre Aktien
    # brauchen heutige Kurse, auch wenn sie nicht mehr auf der Liste stehen.
    nacht = nachtbefunde_laden()
    nachtbefunde_bericht(nacht)
    # WER AUF SEINEN EINSTIEGSTAG WARTET, BRAUCHT EBENSO HEUTIGE KURSE
    # (Mathias, 11.09.2026): Die Mappe wird jede Nacht neu geschrieben, ein
    # vorgemerkter Luecken-Tag kann also aus dem Universum gefallen sein.
    abruf_ticker = sorted(gewuenscht | set(gap_universum)
                          | nacht_symbole(nacht) | gapgo_warte_symbole())

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
    # Ueberwachung nicht mehr am Zeitplan: Der Lauf prueft im Prueftakt
    # selbst weiter, bis die Boerse schliesst oder die Zeit ablaeuft. Die
    # Zeitplan-Laeufe bleiben als Rueckfallebene bestehen; die
    # concurrency-Gruppe im Workflow verhindert Doppelmeldungen.
    #
    # ACHTUNG, GITHUBS SECHS-STUNDEN-GRENZE: Ein Auftrag auf GitHubs
    # Rechnern wird nach 360 Minuten abgeschossen, egal was hier steht.
    # Bei --dauerwache 390 endet der Lauf also NICHT nach 390 Minuten,
    # sondern rund 360 Minuten nach dem Start des Auftrags. Deshalb wird
    # unten beides genannt: was verlangt wurde und wann GitHub spaetestens
    # abbricht. Frueher stand hier nur die verlangte Zeit — das Protokoll
    # versprach ein Ende um 15:42, tatsaechlich war um 15:12 Schluss.
    ende_dauerwache = None
    if args.dauerwache > 0:
        ende_dauerwache = datetime.now() + timedelta(minutes=args.dauerwache)
        github_ende = datetime.now() + timedelta(minutes=GITHUB_GRENZE_MIN)
        print(f"Dauerwache aktiv: Prüfung alle {PRUEF_TAKT} Sekunden, für "
              f"bis zu {args.dauerwache} Minuten "
              f"(bis {ende_dauerwache:%H:%M} Serverzeit).")
        if args.dauerwache > GITHUB_GRENZE_MIN:
            print(f"  Hinweis: Auf GitHubs Rechnern ist nach "
                  f"{GITHUB_GRENZE_MIN} Minuten Schluss, also gegen "
                  f"{github_ende:%H:%M} — die zweite Wache übernimmt.")

    state = load_state()
    schon_gemeldet = set(state["gemeldet"])
    gruen_laden((heute_ny() or date.today()).isoformat())      # R9
    # Was in DIESEM Lauf schon im Trigger-Logbuch steht. Getrennt von
    # schon_gemeldet, das erst ein erfolgreicher Push fuellt.
    _im_logbuch = set()

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
    # NACHTBEFUNDE (Mathias, 10.09.2026): Offen ist, was nach dem ersten
    # heutigen Kurs nachgerechnet wird, siehe nachtbefunde_schritt. Einmal
    # beim Start zusammengestellt, nicht in jeder Runde.
    nacht["offen"] = nachtbefunde_offen(nacht, schon_gemeldet)
    quotes = {}              # vor dem ersten Datenabruf leer — die
                             # Tagesgeschäft-Wache prüft sonst ins Leere

    basis = {}                       # letzter Tagesdaten-Stand
    naechster_abruf = 0.0
    sperre_bis = 0.0                 # nach Sendefehler kurz nicht erneut
    geaendert = set()                # Aktien mit frischer Kursmeldung
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
        # BIS 10.09.2026 standen hier Sektor-Radar, Insider-Kaeufe und die
        # Nachtbefunde, und zwar VOR dem ersten Kursabruf. Sie gingen mit
        # den Zahlen vom Vortagesschluss hinaus und hielten die Ausbrueche
        # auf (09.09.2026: zehn Pushes, erster Kursabruf gegen 15:31:50).
        # Seither kommen sie nach den Ausbruechen und aus heutigen Kursen,
        # siehe nachtbefunde_schritt am Ende des Durchlaufs.
        if offen and laut and not args.dry_run:
            tagesgeschaeft_wache(topic, quotes, args.dry_run, state)
            # M2 (Gerhard, 12.09.2026): Teilverkauf im Handel ab plus 20 Prozent.
            teilverkauf_wache(topic, quotes, args.dry_run, state, schon_gemeldet)

        if not laut:
            if not basis:
                time.sleep(PRUEF_TAKT)
                continue
            # Zwischen zwei Abrufen: auf dem letzten Tagesstand arbeiten,
            # aber mit frischen Kursen aus dem Strom. NUR die Aktien, fuer
            # die wirklich eine Kursmeldung kam — alles andere hat sich
            # seit dem letzten Durchlauf nicht bewegt und braucht keine
            # Rechenzeit. Ohne diese Einschraenkung waeren es bei 60
            # Meldungen je Sekunde und 147 Kaufpunkten achttausend
            # Rechnungen je Sekunde.
            quotes = {t: dict(basis[t]) for t in geaendert if t in basis}
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
            geaendert = set(basis)      # beim Abruf alles einmal durchrechnen

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
            gruen_zaehlen(quotes)         # R9: ein Abruf je Minute
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

            treffer, neu, nachtrag, uebersprungen = [], [], [], []
            wiedereintritt = []
            fenster = state.setdefault("fenster", {})
            for item in items:
                q = quotes.get(item["ticker"].upper())
                if not q:
                    continue
                res = pruefe_breakout(item, q)
                if not res:
                    continue
                # DAS EINSTIEGSFENSTER ALS ZUSTAND (Mathias, 13.08.2026,
                # "das Fenster ist das Fenster"). Ein Kaufpunkt ist DRIN
                # oder DRAUSSEN, und JEDER Wechsel wird gemeldet: hinaus
                # als "uebersprungen", herein als "wieder im
                # Einstiegsfenster". Solange er draussen ist, schweigt der
                # gewoehnliche Ausbruchsweg ganz - sonst kaeme, wie bei
                # MNDY am 13.08.2026, zwei Minuten nach "kein Kaufsignal"
                # ein "Vol BESTAETIGT".
                fkey = fenster_schluessel(item)
                vorher = fenster.get(fkey)
                zustand = fenster_zustand(res["ueber_pct"] / 100.0, vorher)
                wechsel = fenster_wechsel(zustand, vorher)
                if zustand:
                    fenster[fkey] = zustand
                if fallback_ohne_riss(res):
                    # Ausweich-Marke, ueber der der Kurs schon gestern
                    # stand: kein Riss, keine Meldung - auf KEINEM der
                    # drei Wege (auch kein "wieder im Einstiegsfenster"
                    # fuer eine Marke, die nie angesagt war). Der
                    # Fensterzustand ist oben trotzdem gepflegt.
                    continue
                if res.get("uebersprungen"):
                    res["keys"] = uebersprungen_schluessel_alle(res)
                    res["key"] = res["keys"][0]
                    if melde_uebersprungen(res, wechsel, schon_gemeldet):
                        uebersprungen.append(res)
                    elif (wechsel == "verlassen"
                          and res.get("vortagesschluss") is None):
                        # BEIDE Quellen ausgefallen. Dann wird geschwiegen
                        # (Mathias, 14.08.2026) - eine Meldung "im Zweifel"
                        # waere die Hintertuer, durch die die 114
                        # Ruecksetzer-Marken zurueckkaemen. Die Zeile ist
                        # reine Diagnose fuer mich und keine Absicherung;
                        # das Protokoll liest sonst niemand.
                        print(f"  {item['ticker']}: über der Nachlaufgrenze, "
                              f"aber weder Vortagesschluss noch Mappen-Kurs "
                              f"— keine Meldung.")
                    continue
                if wechsel == "wiedereintritt":
                    res["key"] = ausbruch_schluessel(res)
                    wiedereintritt.append(res)
                    continue
                if (zustand or vorher) == DRAUSSEN:
                    # Noch in der Totzone auf dem Rueckweg: nichts melden.
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
                # SEIT 10.09.2026 NACH MUSTER statt nach Platznummer, je
                # Muster ein Schluessel (siehe ausbruch_schluessel_alle).
                res["keys"] = ausbruch_schluessel_alle(res)
                res["key"] = res["keys"][0]
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
                res["keys_best"] = [NACHTRAG_MARKE + k for k in res["keys"]]
                res["key_best"] = res["keys_best"][0]
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

            # ZAHLEN-KARENZ, STUFE A (Gerhards Entscheid 31.08.2026
            # abends, ersetzt Stufe B vom selben Tag): Es wird NICHTS
            # mehr zurueckgehalten. Treffer im Karenzfenster werden
            # gemeldet, tragen aber den harten Warnkopf (siehe
            # termin_nachsatz) und das Logbuch-Feld zahlen_karenz, damit
            # ihre Trefferquote messbar bleibt.
            for t in zu_melden:
                if im_zahlen_karenzfenster(t.get("ticker")):
                    t["zahlen_karenz"] = True

            # INS LOGBUCH kommt JEDER erkannte Ausbruch — auch der ohne
            # Volumenbestaetigung, auch der im Trockenlauf, auch der,
            # dessen Push scheitert. Das Logbuch fragt nicht, ob gemeldet
            # oder gekauft wurde, sondern was das Regelwerk gesehen hat;
            # nur so laesst sich spaeter messen, ob die aussortierten
            # Treffer wirklich die schlechteren waren. Eigener Merker,
            # weil schon_gemeldet erst nach erfolgreichem Push gesetzt
            # wird — sonst gaebe es je Fehlversuch einen Eintrag.
            _melde_schluessel = {t["key"] for t in zu_melden}
            for t in neu:
                if t["key"] in _im_logbuch:
                    continue
                _im_logbuch.add(t["key"])
                trigger_logbuch.protokolliere(
                    {"ticker": t.get("ticker"), "firma": t.get("firma", ""),
                     "strategie": t.get("strategie"),
                     "kaufpunkt": t.get("kaufpunkt"), "kurs": t.get("kurs"),
                     "stop": t.get("stop"), "ziel": t.get("ziel"),
                     "vol_ratio": t.get("vol_ratio"),
                     "vol_noetig": t.get("vol_noetig"),
                     "vol_bestaetigt": t.get("vol_ok"),
                     "vol_anteil": t.get("vol_anteil"),
                     "ueber_pct": t.get("ueber_pct"),
                     "gemeldet": t["key"] in _melde_schluessel,
                     "zahlen_karenz": bool(t.get("zahlen_karenz")),
                     "folgetag": bool(t.get("folgetag")),
                     **zusatz_logbuch(t.get("ticker")),
                     "trockenlauf": bool(args.dry_run)},
                    quelle="waechter")

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
                        for k in t.get("keys") or [t["key"]]:
                            schon_gemeldet.add(k)
                            state["gemeldet"][k] = heute_s
                        # War der Ausbruch schon bei der ersten Meldung
                        # bestaetigt, ist der Nachtrag gegenstandslos —
                        # sein Schluessel wird gleich mitgesetzt.
                        if t["vol_ok"] is True:
                            for k in t.get("keys_best") or [t["key_best"]]:
                                schon_gemeldet.add(k)
                                state["gemeldet"][k] = heute_s
                    save_state(state)
                    # Kapitel 12: Jede gemeldete Kaufpunkt-Meldung wird
                    # ab jetzt als Beobachtung im Chart ueberwacht.
                    beobachtungen_aus_breakouts(zu_melden)
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
                    schon_gemeldet.update(t.get("keys") or [t["key"]])
                    if t["vol_ok"] is True:
                        schon_gemeldet.update(t.get("keys_best")
                                              or [t["key_best"]])

            # --- Nachtrag: Volumen hat nachgezogen ---------------------
            # Eigener Wortlaut MIT ABSICHT (Mathias, 18.08.2026, nach
            # kurzem Hin und Her ausdruecklich bestaetigt: "dort hat es
            # ja einen Sinn"): Diese Aktien wurden bereits unbestaetigt
            # gemeldet, und "Vol jetzt bestätigt" sagt, dass dies die
            # Bestaetigung von vorhin ist und kein zweiter Ausbruch.
            if nachtrag and jetzt_s >= sperre_bis:
                print(f"\n{len(nachtrag)} Ausbruch/Ausbrüche haben die "
                      f"Volumenbestätigung nachgereicht:")
                for t in nachtrag:
                    print("  " + format_treffer(t).replace("\n", "\n  ") + "\n")
                if args.dry_run:
                    print("(Dry-Run — kein Nachtrag gesendet)")
                    for t in nachtrag:
                        schon_gemeldet.update(t.get("keys_best")
                                              or [t["key_best"]])
                elif push_nachtrag(topic, nachtrag):
                    heute_s = date.today().isoformat()
                    for t in nachtrag:
                        for k in t.get("keys_best") or [t["key_best"]]:
                            schon_gemeldet.add(k)
                            state["gemeldet"][k] = heute_s
                    save_state(state)
                else:
                    sperre_bis = jetzt_s + TAKT

            # --- Uebersprungene Kaufpunkte ---------------------------
            # Bewusst NACH den Ausbruechen und dem Nachtrag: Was handelbar
            # ist, geht zuerst raus. Diese Meldung ist eine Auskunft.
            if uebersprungen and jetzt_s >= sperre_bis:
                print("")
                print(f"{len(uebersprungen)} Kaufpunkt(e) übersprungen "
                      f"(kein sauberer Einstieg mehr):")
                for t in uebersprungen:
                    for zeile in format_uebersprungen(t).split("\n"):
                        print("  " + zeile)
                    print("")
                trigger_logbuch.protokolliere_viele(
                    [{"ticker": t.get("ticker"), "firma": t.get("firma", ""),
                      "strategie": t.get("strategie"),
                      "kaufpunkt": t.get("kaufpunkt"), "kurs": t.get("kurs"),
                      "stop": t.get("stop"), "ueber_pct": t.get("ueber_pct"),
                      "uebersprungen": True,
                      "trockenlauf": bool(args.dry_run)}
                     for t in uebersprungen], quelle="waechter/uebersprungen")
                if args.dry_run:
                    print("(Dry-Run — nichts gesendet)")
                    for t in uebersprungen:
                        schon_gemeldet.update(t.get("keys") or [t["key"]])
                elif push_uebersprungen(topic, uebersprungen):
                    heute_s = date.today().isoformat()
                    for t in uebersprungen:
                        for k in t.get("keys") or [t["key"]]:
                            schon_gemeldet.add(k)
                            state["gemeldet"][k] = heute_s
                    save_state(state)
                else:
                    sperre_bis = jetzt_s + TAKT

            # --- Wieder im Einstiegsfenster (Mathias, 13.08.2026) ----------
            # Der Kurs war ueber der Nachlaufgrenze und ist zurueckgekommen.
            # Das ist eine ECHTE Gelegenheit und wird deshalb wie ein
            # Ausbruch beziffert, aber ausdruecklich als Wiedereintritt
            # beschriftet - sonst haelt man es fuer eine zweite Chance auf
            # dasselbe und zaehlt die Meldungen doppelt.
            #
            # Das Gedaechtnis ist der ZUSTAND (state["fenster"]), nicht der
            # Meldeschluessel: Ein Kaufpunkt darf an einem Tag mehrmals
            # hinaus und wieder herein, jeder Wechsel zaehlt. Die Totzone
            # in fenster_zustand() haelt das Zappeln an der Grenze fern.
            if wiedereintritt and jetzt_s >= sperre_bis:
                print("")
                print(f"{len(wiedereintritt)} Kaufpunkt(e) wieder im "
                      f"Einstiegsfenster:")
                for t in wiedereintritt:
                    for zeile in format_wiedereintritt(t).split("\n"):
                        print("  " + zeile)
                    print("")
                trigger_logbuch.protokolliere_viele(
                    [{"ticker": t.get("ticker"), "firma": t.get("firma", ""),
                      "strategie": t.get("strategie"),
                      "kaufpunkt": t.get("kaufpunkt"), "kurs": t.get("kurs"),
                      "stop": t.get("stop"), "ueber_pct": t.get("ueber_pct"),
                      "vol_bestaetigt": t.get("vol_ok") is True,
                      "wiedereintritt": True,
                      "trockenlauf": bool(args.dry_run)}
                     for t in wiedereintritt], quelle="waechter/wiedereintritt")
                if args.dry_run:
                    print("(Dry-Run — nichts gesendet)")
                elif push_wiedereintritt(topic, wiedereintritt):
                    # Der Kaufpunkt ist zurueck im Fenster, also gilt er
                    # nicht mehr als angesagt-draussen. Verlaesst er das
                    # Fenster spaeter wirklich noch einmal, ist das ein
                    # neuer Vorgang und wird wieder gemeldet.
                    for t in wiedereintritt:
                        for k in uebersprungen_schluessel_alle(t):
                            schon_gemeldet.discard(k)
                            state["gemeldet"].pop(k, None)
                    save_state(state)
                else:
                    # Nicht angekommen: Der Zustand wird zurueckgedreht,
                    # damit der Wechsel beim naechsten Durchlauf erneut
                    # auffaellt. Sonst gaelte er als erledigt, ohne dass
                    # jemand davon erfahren haette.
                    for t in wiedereintritt:
                        fenster[fenster_schluessel(t)] = DRAUSSEN
                    sperre_bis = jetzt_s + TAKT

            # --- Red-to-Green (Regelwerk Kapitel 9) ------------------------
            # Nur wenn der Nasdaq stark genug nach unten gegapt hat und die
            # Aktie auf der nachts gebauten Fokusliste steht.
            r2g_neu = []
            if _r2g_fokus and r2g_regime_pruefen():
                for rt, eintrag in _r2g_fokus.items():
                    q = quotes.get(rt)
                    if not q:
                        continue
                    treffer = pruefe_red_to_green(rt, q, eintrag)
                    if not treffer:
                        continue
                    treffer["ticker"] = rt
                    treffer["firma"] = eintrag.get("firma") or firmen.get(rt, "")
                    treffer["key"] = f"R2G|{rt}|{date.today().isoformat()}"
                    if treffer["key"] not in schon_gemeldet:
                        r2g_neu.append(treffer)
            if r2g_neu:
                print(f"\nRed-to-Green: {len(r2g_neu)} Meldung(en)")
                for t in r2g_neu:
                    print("  " + format_r2g(t).replace("\n", "\n  ") + "\n")
                if args.dry_run:
                    print("(Dry-Run — kein Red-to-Green-Push)")
                    for t in r2g_neu:       # sonst alle zwei Sekunden erneut
                        schon_gemeldet.add(t["key"])
                elif jetzt_s < sperre_bis:
                    pass                    # Sendesperre nach Fehlschlag
                else:
                    titel = ("Red-to-Green: "
                             + ", ".join(t["ticker"] for t in r2g_neu))
                    if push_text(topic, titel,
                                 nummeriert([format_r2g(t) for t in r2g_neu])):
                        for t in r2g_neu:
                            schon_gemeldet.add(t["key"])
                            state["gemeldet"][t["key"]] = date.today().isoformat()
                        save_state(state)
                        # LOGBUCH (Mathias, 31.08.2026): Red-to-Green war
                        # der blinde Fleck der Auswertung — nur die
                        # Explosive-Variante wurde protokolliert. Der
                        # Eintrag entsteht NUR bei Push-Erfolg, damit je
                        # gemeldetem Signal genau eine Zeile steht.
                        trigger_logbuch.protokolliere_viele(
                            [{"ticker": t["ticker"],
                              "firma": t.get("firma", ""),
                              "strategie": "Red-to-Green",
                              "kurs": t.get("kurs"),
                              "kaufpunkt": t.get("kurs"),
                              "vortagesschluss": t.get("vortagesschluss"),
                              "minute": t.get("minute"),
                              **zusatz_logbuch(t.get("ticker")),
                              "gemeldet": True} for t in r2g_neu],
                            quelle="waechter/kapitel9")
                        beobachtungen_eintragen([{
                            "ticker": t["ticker"],
                            "zusatz": f"R2G-{date.today().isoformat()}",
                            "strategie": "Red-to-Green",
                            "kaufpunkt": t.get("kurs"),
                            "struktur": t.get("vortagesschluss"),
                            "ziel": None, "firma": t.get("firma", ""),
                            "klasse": "tagesgeschaeft"} for t in r2g_neu])
                    else:
                        sperre_bis = jetzt_s + TAKT

            # --- Red-to-Green EXPLOSIVE (Kapitel 11) -----------------------
            # OHNE Marktbedingung: Hier zaehlt nur die Aktie selbst
            # (Mathias, 12.08.2026). Deshalb steht die Schleife bewusst
            # AUSSERHALB der r2g_regime_pruefen-Abfrage von Kapitel 9.
            # Eigener Meldeschluessel, damit beide Kapitel am selben Tag
            # unabhaengig voneinander feuern koennen.
            r2gx_neu = []
            if _r2g_fokus:
                for rt, eintrag in _r2g_fokus.items():
                    q = quotes.get(rt)
                    if not q:
                        continue
                    treffer = pruefe_red_to_green_explosive(rt, q, eintrag)
                    if not treffer:
                        continue
                    treffer["ticker"] = rt
                    treffer["firma"] = eintrag.get("firma") or firmen.get(rt, "")
                    treffer["strategie"] = red_to_green_explosive.NAME
                    treffer["key"] = f"R2GX|{rt}|{date.today().isoformat()}"
                    # Hat Kapitel 9 dieselbe Aktie heute schon gemeldet,
                    # ist das hier kein zweites Ereignis, sondern dasselbe
                    # mit lockererer Schwelle. Dann schweigen.
                    if (treffer["key"] not in schon_gemeldet
                            and f"R2G|{rt}|{date.today().isoformat()}"
                            not in schon_gemeldet):
                        r2gx_neu.append(treffer)
            if r2gx_neu:
                print("")
                print(f"Red-to-Green Explosive: {len(r2gx_neu)} Meldung(en)")
                for t in r2gx_neu:
                    for zeile in format_r2g(t).split("\n"):
                        print("  " + zeile)
                    print("")
                trigger_logbuch.protokolliere_viele(
                    [{"ticker": t.get("ticker"), "firma": t.get("firma", ""),
                      "strategie": red_to_green_explosive.NAME,
                      "kurs": t.get("kurs"),
                      "trockenlauf": bool(args.dry_run)} for t in r2gx_neu],
                    quelle="waechter/kapitel11")
                if args.dry_run:
                    print("(Dry-Run — kein Push)")
                    for t in r2gx_neu:
                        schon_gemeldet.add(t["key"])
                elif jetzt_s < sperre_bis:
                    pass
                else:
                    titel = ("Red-to-Green Explosive: "
                             + ", ".join(t["ticker"] for t in r2gx_neu))
                    if push_text(topic, titel,
                                 nummeriert([format_r2g(t) for t in r2gx_neu])):
                        for t in r2gx_neu:
                            schon_gemeldet.add(t["key"])
                            state["gemeldet"][t["key"]] = date.today().isoformat()
                        save_state(state)
                    else:
                        sperre_bis = jetzt_s + TAKT

            # --- Einstiege am Folgetag (Regelwerk Kapitel 7) ---------------
            # Die Warteliste der gemeldeten Luecken-Tage; die Begruendung
            # steht bei gapgo_vormerken(). Bewusst VOR dem Gap-Block: Wer
            # heute einsteigt, soll seine Meldung vor den neuen Luecken
            # bekommen. Und bewusst eine EIGENE Meldung: Der Luecken-Tag
            # nennt nur den Kaufpunkt fuer morgen, gekauft wird heute.
            gap_ein, gap_ein_neu = gapgo_einstiege_pruefen(state, quotes)
            if gap_ein_neu:
                save_state(state)
            gap_ein = [g for g in gap_ein if g["key"] not in schon_gemeldet]
            gap_ueber = [g for g in gap_ein if g.get("uebersprungen")]
            gap_ein = [g for g in gap_ein if not g.get("uebersprungen")]
            # W2 (Gerhard, 12.09.2026): ueber der 3-Prozent-Grenze ist es kein
            # Einstieg; eine Auskunft, kein Kaufsignal, keine Beobachtung.
            if gap_ueber:
                print(f"\n{GAP_NAME}: {len(gap_ueber)} Einstieg(e) am Folgetag "
                      f"ÜBERSPRUNGEN (über {GAP_EINSTIEG_GRENZE * 100:.0f} %)")
                for g in gap_ueber:
                    print("  " + format_gapgo_uebersprungen(g).replace("\n", "\n  ") + "\n")
                if args.dry_run:
                    for g in gap_ueber:
                        schon_gemeldet.add(g["key"])
                elif jetzt_s < sperre_bis:
                    pass
                else:
                    titel = (f"{GAP_NAME} Einstieg übersprungen: "
                             + ", ".join(g["ticker"] for g in gap_ueber))
                    if sende(topic, titel,
                             [format_gapgo_uebersprungen(g) for g in gap_ueber],
                             "default"):
                        warten = state.get(GAPGO_WARTEN) or {}
                        for g in gap_ueber:
                            schon_gemeldet.add(g["key"])
                            state["gemeldet"][g["key"]] = date.today().isoformat()
                            warten.pop(g["ticker"], None)
                        trigger_logbuch.protokolliere_viele(
                            [{"ticker": g["ticker"], "firma": g.get("firma", ""),
                              "strategie": "Gap and Go",
                              "stufe": "Einstieg am Folgetag übersprungen",
                              "kurs": g.get("kurs"), "kaufpunkt": g.get("kaufpunkt"),
                              "einstieg": g.get("einstieg"), "stop": g.get("stop"),
                              **zusatz_logbuch(g["ticker"]),
                              "gemeldet": True} for g in gap_ueber],
                            quelle="waechter/kapitel7")
                        save_state(state)
                    else:
                        sperre_bis = jetzt_s + TAKT
            if gap_ein:
                print(f"\n🟢 {GAP_NAME}: {len(gap_ein)} Einstieg(e) "
                      f"am Folgetag")
                for g in gap_ein:
                    print("  " + format_gapgo_einstieg(g)
                          .replace("\n", "\n  ") + "\n")
                if args.dry_run:
                    print("(Dry-Run — kein Einstiegs-Push)")
                    for g in gap_ein:   # sonst alle zwei Sekunden erneut
                        schon_gemeldet.add(g["key"])
                elif jetzt_s < sperre_bis:
                    pass                # Sendesperre nach Fehlschlag
                else:
                    titel = (f"Einstieg {GAP_NAME}: "
                             + ", ".join(g["ticker"] for g in gap_ein))
                    # Fuer die Handels-App ist ab jetzt der EINSTIEG der
                    # Kaufpunkt; im Text stehen beide Zahlen.
                    paket = handel_paket([{**g, "kaufpunkt": g["einstieg"]}
                                          for g in gap_ein],
                                         art="kauf", anlass="einstieg")
                    if sende(topic, titel,
                             [format_gapgo_einstieg(g) for g in gap_ein],
                             "high", handel_adresse(paket)):
                        warten = state.get(GAPGO_WARTEN) or {}
                        for g in gap_ein:
                            schon_gemeldet.add(g["key"])
                            state["gemeldet"][g["key"]] = date.today().isoformat()
                            warten.pop(g["ticker"], None)
                        trigger_logbuch.protokolliere_viele(
                            [{"ticker": g["ticker"],
                              "firma": g.get("firma", ""),
                              "strategie": "Gap and Go",
                              "stufe": "Einstieg am Folgetag",
                              "kurs": g.get("kurs"),
                              "kaufpunkt": g.get("einstieg"),
                              "stop": g.get("stop"),
                              **zusatz_logbuch(g["ticker"]),
                              "gemeldet": True} for g in gap_ein],
                            quelle="waechter/kapitel7")
                        # ERST JETZT die Beobachtung: Der Einstieg ist
                        # erfolgt, damit hat die Exit-Wache etwas zu
                        # bewachen. Der Schluessel nennt weiter den
                        # Luecken-Tag, damit beides zusammenfindet.
                        beobachtungen_eintragen([{
                            "ticker": g["ticker"],
                            "zusatz": f"GG-{g['signal']}",
                            "strategie": "Gap and Go",
                            "kaufpunkt": g["einstieg"],
                            "struktur": g.get("stop"),
                            "ziel": None, "firma": g.get("firma", ""),
                            "klasse": "tagesgeschaeft"} for g in gap_ein])
                        # SICHERN GANZ ZULETZT, ohne die Minutendrossel
                        # (Muster der Nachtbefunde): Erst jetzt steht die
                        # frische Beobachtung in positionen.json, und die
                        # sichert der Endkommit des Laufs nicht.
                        save_state(state, sofort=True)
                    else:
                        sperre_bis = jetzt_s + TAKT

            # --- Gap and Go (Regelwerk Kapitel 7) --------------------------
            # Zwei Meldestufen je Aktie und Tag: 'im Aufbau', sobald alle
            # live pruefbaren Pflichtkriterien stehen, und 'BESTÄTIGT' zum
            # Handelsende (Schluss im oberen Fuenftel + 5x Volumen roh).
            gap_neu = []
            gap_geaendert = False
            for gt in gap_universum:
                q = quotes.get(gt)
                if not q:
                    continue
                g = pruefe_gap_and_go(gt, q)
                if not g:
                    continue
                g["firma"] = firmen.get(gt, "")
                # KAUFPUNKT UND STOP NACHZIEHEN, solange der Luecken-Tag
                # laeuft. Legt KEINEN Eintrag an — das tut erst die
                # verschickte Meldung.
                if gapgo_vormerken(state, g, anlegen=False):
                    gap_geaendert = True
                stufe = "GAPGOFIX|" if g["bestaetigt"] else "GAPGO|"
                g["key"] = f"{stufe}{gt}|{date.today().isoformat()}"
                if g["key"] not in schon_gemeldet:
                    gap_neu.append(g)
            if gap_geaendert:
                save_state(state)
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
                    titel = f"{GAP_NAME}: " + ", ".join(g["ticker"]
                                                          for g in gap_neu)
                    if push_text(topic, titel, body):
                        for g in gap_neu:
                            schon_gemeldet.add(g["key"])
                            state["gemeldet"][g["key"]] = date.today().isoformat()
                        save_state(state)
                        # LOGBUCH (Mathias, 31.08.2026): beide Meldestufen
                        # landen im Logbuch, die Stufe als eigenes Feld.
                        # Nur bei Push-Erfolg — eine Zeile je Meldung.
                        trigger_logbuch.protokolliere_viele(
                            [{"ticker": g["ticker"],
                              "firma": g.get("firma", ""),
                              "strategie": "Gap and Go",
                              "stufe": ("bestätigt" if g.get("bestaetigt")
                                        else "im Aufbau"),
                              "kurs": g.get("kurs"),
                              "kaufpunkt": g.get("kp"),
                              "stop": g.get("stop"),
                              **zusatz_logbuch(g["ticker"]),
                              "gemeldet": True} for g in gap_neu],
                            quelle="waechter/kapitel7")
                        # KEINE BEOBACHTUNG AM LUECKEN-TAG (Mathias,
                        # 11.09.2026, Fall RCUS): Bis hierher entstand
                        # sofort eine Tagesgeschaeft-Beobachtung mit
                        # Einstieg zum Kaufpunkt, und ihr Stop schlug am
                        # SELBEN Tag zu — ein Ausstieg aus einer Position,
                        # die es nie gab. Gekauft wird erst am Folgetag,
                        # bis dahin wartet das Signal; die Begruendung
                        # steht bei gapgo_vormerken().
                        for g in gap_neu:
                            gapgo_vormerken(state, g)
                        save_state(state)
                    else:
                        sperre_bis = jetzt_s + TAKT

            # --- R15 (Gerhard, 12.09.2026): morgens die Sektor-Aufsteiger ----
            if offen and laut and basis and jetzt_s >= sperre_bis:
                if sektor_morgen(topic, state, schon_gemeldet, args.dry_run) is False:
                    sperre_bis = jetzt_s + TAKT

            # --- Nachtbefunde, mit den Kursen von heute nachgerechnet ------
            # (Mathias, 10.09.2026). Bewusst ZULETZT: Was handelbar ist, geht
            # zuerst hinaus. Hoechstens eine Meldung je Durchlauf und nur bei
            # freiem Push-Sammler, damit kein Ausbruch auf sie wartet.
            if nacht["offen"] and jetzt_s >= sperre_bis:
                if nachtbefunde_schritt(topic, nacht, basis,
                                        ws if ws_laeuft else None,
                                        schon_gemeldet, state,
                                        args.dry_run) is False:
                    sperre_bis = jetzt_s + TAKT

            # --- M1 (Gerhard, 12.09.2026): schlussnahe Befunde ab 15:45 ----
            if offen and basis and jetzt_s >= sperre_bis:
                if schlussnahe_befunde(topic, nacht, basis,
                                       ws if ws_laeuft else None,
                                       state, schon_gemeldet,
                                       args.dry_run) is False:
                    sperre_bis = jetzt_s + TAKT

        if ende_dauerwache is None:
            break
        if datetime.now() >= ende_dauerwache:
            print("Dauerwache: Zeit abgelaufen — Ende.")
            ws.stop()
            break

        # FESTER TAKT (Mathias, 30.07.2026 bestaetigt): Die Schleife
        # schlaeft die vollen PRUEF_TAKT Sekunden und rechnet dann alles
        # durch. Am 30.07. war das ein paar Stunden lang anders — erst
        # weckte jede Kursmeldung die Pruefung, dann standen 20 Sekunden
        # drin; beides ist zurueckgenommen.
        #
        # Kuerzer zu takten kostet bei Yahoo NICHTS: Der Strom ist eine
        # stehende Verbindung, die von sich aus sendet, und der schwere
        # Tagesdatenabruf laeuft unabhaengig davon im TAKT.
        time.sleep(PRUEF_TAKT)
        geaendert = set(basis)

    # Verbindungen sauber schliessen, damit kein Faden offen bleibt.
    ws.stop()


if __name__ == "__main__":
    main()
