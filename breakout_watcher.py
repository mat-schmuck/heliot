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

Volumen-Regeln je Strategie (aus dem Regelwerk):
  Darvas Box        Volumen > Ø20-Tage-Volumen
  VCP               Volumen ≥ 140 % vom Ø20-Tage-Volumen (Minervini: 40-50 % über Ø)
  Cup & Handle      Volumen > Ø20-Tage-Volumen (O'Neil: Volumen-Bestätigung)
  Rectangle Top     Volumen > Ø20d UND Kurs > SMA21 (Bulkowskis bestes Setup)
  High & Tight Flag Volumen > Ø20-Tage-Volumen
  Fallback-Level    Volumen > Ø20-Tage-Volumen

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

QUOTE_URL = "https://api.twelvedata.com/quote"
STATE_FILE = Path("watcher_state.json")

# Volumen-Faktor je Strategie (Vielfaches des Ø20-Tage-Volumens)
VOL_FAKTOR = {
    "Darvas Box": 1.0,
    "VCP": 1.4,
    "Cup & Handle": 1.0,
    "Rectangle Top": 1.0,
    "High & Tight Flag": 1.0,
}
VOL_FAKTOR_FALLBACK = 1.0

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
GAP_MIN = 0.07              # Eroeffnung >= 7 % ueber Vortagesschluss
GAP_VOL_FAKTOR = 5.0        # Tagesvolumen >= 5x Ø10-Tage
GAP_FRUEH_FAKTOR = 3.0      # erste halbe Stunde: >= 300 % des zeitueblichen
GAP_SCHLUSS_POS = 0.80      # Schluss im oberen Fuenftel der Tagesspanne
FLAT_BASE_MAX_SPANNE = 0.35 # "flach" = Spanne < 35 % (Startwert 30-40 %,
                            # laut Regelwerk per Backtest zu justieren)
FLAT_BASE_TAGE = (63, 126)  # 3-6 Monate vor dem Gap-Tag
# Hinweis fuer Gerhard: Das Kapitel verlangt das 10-Tage-Volumenfenster und
# nennt es "dasselbe wie beim Breakout-Waechter" — die Ausbruchsbestaetigung
# rechnet aber laut Kapitel 1-6 mit Ø20. Hier gilt fuer Gap and Go die 10,
# wie im Kriterium ausdruecklich gefordert; die Breakouts bleiben bei Ø20.


# ---------------------------------------------------------------------------
# Zustand (was wurde schon gemeldet)
# ---------------------------------------------------------------------------

# Wie sich das Handelsvolumen ueber den Boersentag verteilt.
# Gemessen an acht Aktien ueber 168 Aktien-Tage (30-Minuten-Kerzen,
# nur regulaerer Handel). Schluessel: Minuten seit Mitternacht New Yorker
# Zeit am ENDE der jeweiligen Halbstunde; Wert: bis dahin gehandelter
# Anteil am Tagesvolumen.
#
# Wichtig: Die Verteilung ist NICHT gleichmaessig. Allein die erste halbe
# Stunde macht 21 % aus, linear waeren es 7,7 %. Wer linear hochrechnet,
# ueberschaetzt den Vormittag um ein Vielfaches und erzeugt Fehlsignale.
VOLUMENKURVE = [
    (570, 0.000),   # 09:30 NY — Eroeffnung, noch nichts gehandelt
    (600, 0.213),   # 10:00
    (630, 0.314),   # 10:30
    (660, 0.396),   # 11:00
    (690, 0.465),   # 11:30
    (720, 0.523),   # 12:00
    (750, 0.581),   # 12:30
    (780, 0.630),   # 13:00
    (810, 0.676),   # 13:30
    (840, 0.721),   # 14:00
    (870, 0.764),   # 14:30
    (900, 0.810),   # 15:00
    (930, 0.867),   # 15:30
    (960, 1.000),   # 16:00 — Handelsschluss
]


def tagesanteil(jetzt=None) -> float:
    """Welcher Anteil des Tagesvolumens ist zu dieser Uhrzeit ueblicherweise
    schon gehandelt? Zwischen den Stuetzstellen wird linear interpoliert.

    Vor Handelsbeginn und nach Schluss: 1.0 (voller Tag), damit die
    Hochrechnung dann nichts mehr veraendert."""
    try:
        from zoneinfo import ZoneInfo
        ny = ZoneInfo("America/New_York")
    except Exception:
        return 1.0
    jetzt = (jetzt or datetime.now(ny)).astimezone(ny)
    minuten = jetzt.hour * 60 + jetzt.minute
    if minuten <= VOLUMENKURVE[0][0]:
        return 1.0                      # vor Eroeffnung
    if minuten >= VOLUMENKURVE[-1][0]:
        return 1.0                      # nach Schluss: Tag ist komplett
    for i in range(1, len(VOLUMENKURVE)):
        m0, a0 = VOLUMENKURVE[i - 1]
        m1, a1 = VOLUMENKURVE[i]
        if minuten <= m1:
            spanne = m1 - m0
            anteil = a0 + (a1 - a0) * ((minuten - m0) / spanne) if spanne else a1
            return max(anteil, 0.01)    # nie durch (fast) null teilen
    return 1.0


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


def load_state() -> dict:
    """Melde-Gedaechtnis, dauerhaft ueber Tage hinweg.

    Frueher galt der Zustand nur fuer den laufenden Handelstag — ein am
    Dienstag gemeldeter Ausbruch kam am Mittwoch erneut aufs Handy, solange
    der Kurs ueber dem Kaufpunkt stand (Mathias am 24.07.2026: 'wildes
    Durcheinander'). Jetzt wird jede Meldung mit Datum gemerkt: Ein
    Kaufpunkt meldet genau EINMAL. Rechnet der Scanner neue Level, ergibt
    der neue Preis von selbst einen neuen Schluessel; nach 30 Tagen
    verfallen alte Eintraege. Gap-and-Go-Schluessel tragen das Datum im
    Namen und sind damit bewusst je Tag einmalig."""
    heute = date.today().isoformat()
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
            gemeldet = data.get("gemeldet", {})
            if isinstance(gemeldet, list):
                # Altes Tagesformat einmalig uebernehmen
                gemeldet = {k: data.get("tag", heute) for k in gemeldet}
            grenze = (date.today() - timedelta(days=30)).isoformat()
            return {"gemeldet": {k: d for k, d in gemeldet.items()
                                 if str(d) >= grenze}}
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
    return items


# ---------------------------------------------------------------------------
# Live-Kurse holen (Batch: Twelve Data kann mehrere Symbole pro Call)
# ---------------------------------------------------------------------------

def fetch_quotes_yahoo(tickers: list[str]) -> dict:
    """Holt Kurs, Tagesvolumen und Ø20-Volumen fuer ALLE Ticker in einem Abruf.

    Vorteil gegenueber Twelve Data: kein Minutenlimit, kein Tageslimit, und
    31 Aktien sind in rund drei Sekunden da statt in vier Minuten.

    Das Ø20-Volumen wird hier SELBST aus den Tagesdaten berechnet. Bei Twelve
    Data kam es als Feld 'average_volume', dessen Mittelungszeitraum nirgends
    dokumentiert ist — das Regelwerk verlangt aber ausdruecklich 20 Tage."""
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
                vol20 = float(df["Volume"].iloc[:-1].tail(20).mean())
            else:
                vol20 = 0.0  # brandneue Notierung: ehrlich als unbekannt melden
            eintrag = {
                "close": float(letzte["Close"]),
                "volume": float(letzte["Volume"]),
                "avg_volume": vol20,
                "is_open": False,
                "name": "",
            }
            # Zusatzfelder fuer Gap and Go (Regelwerk Kapitel 7). Die letzte
            # Zeile ist waehrend des Handels der HEUTIGE, unfertige Tag —
            # Durchschnitt und Flat Base rechnen deshalb ohne ihn.
            if len(df) >= 2:
                vortage = df.iloc[:-1]
                eintrag["prev_close"] = float(vortage["Close"].iloc[-1])
                vol10 = float(vortage["Volume"].tail(10).mean())
                eintrag["vol10"] = vol10
                for feld, spalte in (("open", "Open"), ("high", "High"),
                                     ("low", "Low")):
                    wert = letzte.get(spalte)
                    eintrag[feld] = None if pd.isna(wert) else float(wert)
                fenster = vortage.tail(FLAT_BASE_TAGE[1])
                if len(fenster) >= FLAT_BASE_TAGE[0]:
                    tief = float(fenster["Low"].min())
                    if tief > 0:
                        spanne = (float(fenster["High"].max()) - tief) / tief
                        eintrag["flat_base"] = spanne < FLAT_BASE_MAX_SPANNE
                        eintrag["base_spanne"] = spanne
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

    # RELATIVES VOLUMEN, auf den ganzen Tag hochgerechnet.
    #
    # Ohne Hochrechnung waere die Volumenbestaetigung vormittags nie
    # erfuellbar: Um 16:00 Wiener Zeit sind erst rund 31 % eines normalen
    # Tagesvolumens gehandelt — ein Ausbruch muesste also das Dreifache des
    # Ueblichen ziehen, nur um die 100-%-Schwelle zu erreichen.
    #
    # Mit Hochrechnung lautet die Frage richtig: Ist das Volumen FUER DIESE
    # UHRZEIT ungewoehnlich hoch? Ergebnis kann 180 %, 640 % oder 3200 %
    # sein — je staerker der Andrang, desto hoeher.
    anteil = tagesanteil()
    vol_hochgerechnet = vol / anteil if anteil > 0 else vol
    if avg > 0:
        vol_ratio = vol_hochgerechnet / avg
        vol_ok = vol_ratio >= faktor
    else:
        vol_ratio = None
        vol_ok = None  # unbekannt — wir melden trotzdem, aber gekennzeichnet

    return {
        **item,
        "kurs": kurs,
        "ueber_pct": ueber * 100,
        "vol_ratio": vol_ratio,
        "vol_noetig": faktor,
        "vol_ok": vol_ok,
        "vol_roh": vol,
        "vol_anteil": anteil,
    }


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
    3. Flat Base in den 3-6 Monaten davor (Spanne < 35 %)
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
    frueh_ratio = vol / (vol10 * anteil)
    tages_ratio = (vol / anteil) / vol10

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
    vol = ((f"Frühvolumen {g['frueh_ratio']*100:.0f}% des Zeitüblichen, "
            f"nötig {GAP_FRUEH_FAKTOR*100:.0f}%") if g["frueh"] else
           (f"Volumen hochgerechnet {g['tages_ratio']:.1f} mal Ø10, "
            f"nötig {GAP_VOL_FAKTOR:.0f} mal"))
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
    """Trenner-Regeln und Hintergrund siehe format_gapgo. Alle Angaben
    drin (Mathias, 23.07.2026: erst radikal gekuerzt, dann fehlte zu
    viel); Fuellwoerter wie "erst"/"nur" bleiben draussen. Die
    Volumen-Prozente sind die HOCHRECHNUNG auf den ganzen Tag (siehe
    pruefe_breakout), die Klammer nennt den ueblichen Tagesanteil."""
    anteil = t.get("vol_anteil", 1.0)
    zusatz = ""
    if anteil < 0.99:
        zusatz = f" (hochgerechnet, {anteil*100:.0f}% des Tages)"
    if t["vol_ok"] is True:
        vol_txt = (f"Volumen BESTÄTIGT, {t['vol_ratio']*100:.0f}% von Ø, "
                   f"nötig {t['vol_noetig']*100:.0f}%{zusatz}")
    elif t["vol_ok"] is False:
        vol_txt = (f"Volumen NICHT bestätigt, {t['vol_ratio']*100:.0f}% "
                   f"von nötigen {t['vol_noetig']*100:.0f}%{zusatz}")
    else:
        # Kommt nur vor, wenn keine Durchschnittsbasis existiert (brandneue
        # Notierung oder Datenluecke der Kursquelle) — der Waechter rechnet
        # sonst IMMER selbst. "Selbst pruefen" hiess frueher missverstaendlich,
        # man muesse rechnen; gemeint ist: Signal ohne Volumenurteil.
        vol_txt = "Volumen nicht bewertbar, zu wenig Kurshistorie"
    strategie = STRATEGIE_VOLL.get(t["strategie"], t["strategie"])
    zeilen = [
        f"{meldungskopf(t['ticker'], t.get('firma', ''))}; {strategie}",
        f"Kaufpunkt {t['kaufpunkt']:.2f}, Kurs {t['kurs']:.2f} "
        f"(+{t['ueber_pct']:.1f}%); {vol_txt}",
    ]
    schluss = []
    if t["stop"] is not None:
        risiko = (t["kurs"] / t["stop"] - 1) * 100
        schluss.append(f"Stop {t['stop']:.2f}, Risiko {risiko:.1f}%")
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


def push_text(topic: str, titel: str, body: str) -> bool:
    """Schickt eine frei formulierte Meldung (fuer Gap and Go).

    MIT Titel-Kopfzeile: Der Titel war am 23.07. als 'Wortgeklingel'
    entfernt worden — ohne ihn setzt ntfy aber einen generischen Titel
    (die Themen-Adresse) ein, was schlimmer ist. Am 24.07. auf Mathias'
    Wunsch wiederhergestellt."""
    kopf = {"Title": titel.encode("utf-8"), "Priority": "high",
            "Tags": "rocket"}
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
    print(f"Push gesendet an ntfy.sh/{topic} (HTTP {r.status_code})")
    return True


def push(topic: str, treffer: list[dict]) -> bool:
    """Schickt die Meldung und sagt ehrlich, ob sie angekommen ist.

    Der Rueckgabewert ist wichtig: Frueher wurde der Zustand auch dann als
    'gemeldet' gespeichert, wenn der Push fehlschlug - der Treffer waere
    danach NIE wieder gemeldet worden."""
    bestaetigt = [t for t in treffer if t["vol_ok"] is True]
    rest = [t for t in treffer if t["vol_ok"] is not True]
    body = nummeriert([format_treffer(t) for t in bestaetigt + rest])
    # Titel am 24.07.2026 wiederhergestellt: Ohne Title-Kopfzeile setzt
    # ntfy einen generischen Titel (die Themen-Adresse) ein — das war
    # schlimmer als das am 23.07. beanstandete 'Wortgeklingel'.
    titel = (f"🚀 {len(bestaetigt)} bestätigt"
             + (f", {len(rest)} ohne Vol-Bestätigung" if rest else ""))
    kopf = {"Title": titel.encode("utf-8"),
            "Priority": "high" if bestaetigt else "default",
            "Tags": "chart_with_upwards_trend"}
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
    print(f"Push gesendet an ntfy.sh/{topic} (HTTP {r.status_code})")
    return True


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

    # Ausserhalb der Handelszeit gar nicht erst Kurse abrufen. Der Zeitplan
    # im Workflow deckt Sommer- UND Winterzeit ab; welche gerade gilt,
    # entscheidet sich hier.
    offen, grund = markt_offen()
    print(f"Börsenstatus: {'offen' if offen else 'geschlossen'} — {grund}")
    if not offen and not args.ignoriere_handelszeit:
        # Kurz vor der Eroeffnung? Dann bis zur Glocke warten statt aufgeben.
        # GitHub feuert Zeitplaene oft 5-15 Minuten verspaetet; die
        # vorgezogenen Termine im Workflow plus dieses Warten sorgen dafuer,
        # dass die ersten Boersenminuten trotzdem bewacht sind.
        warte = sekunden_bis_eroeffnung()
        if warte is not None and warte <= 20 * 60:
            print(f"Eröffnung in {int(warte // 60)} Min {int(warte % 60)} s — "
                  "ich warte bis zum Handelsbeginn.")
            time.sleep(warte + 20)
            offen, grund = markt_offen()
            print(f"Börsenstatus: {'offen' if offen else 'geschlossen'} — {grund}")
    if not offen and not args.ignoriere_handelszeit:
        print("Nichts zu tun. (Mit --ignoriere-handelszeit trotzdem prüfen.)")
        sys.exit(0)

    items = load_watchlist(args.xlsx, nur_muster=not args.alle)
    if not items:
        sys.exit("Keine Kaufpunkte zum Überwachen gefunden.")
    tickers = [i["ticker"] for i in items]
    print(f"{len(items)} Kaufpunkte über {len(set(tickers))} Aktien werden geprüft "
          f"({datetime.now():%H:%M:%S}).")

    gewuenscht = set(t.upper() for t in tickers)

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
    runde = 0
    while True:
        runde += 1
        if runde > 1:
            print(f"\n——— Runde {runde} ({datetime.now():%H:%M:%S}) ———")

        # Hauptquelle Yahoo (ein Abruf, kein Limit), Twelve Data als Rueckfall.
        quotes = fetch_quotes_yahoo(abruf_ticker)
        if len(quotes) < len(gewuenscht):
            fehlend_yahoo = sorted(gewuenscht - set(quotes))
            if quotes:
                print(f"  Yahoo lieferte {len(quotes)} von {len(gewuenscht)} — "
                      f"hole {len(fehlend_yahoo)} über Twelve Data nach.")
            if api_key:
                quotes.update(fetch_quotes(fehlend_yahoo, api_key))
            elif not quotes and ende_dauerwache is None:
                sys.exit("Yahoo lieferte nichts und kein TWELVE_DATA_API_KEY gesetzt.")

        print(f"{len(gewuenscht & set(quotes))} von {len(gewuenscht)} "
              f"Kaufpunkt-Quotes erhalten ({len(quotes)} Aktien gesamt).")
        if not quotes:
            # In der Dauerwache ist ein Aussetzer kein Todesurteil — die
            # naechste Runde kommt in 6 Minuten.
            if ende_dauerwache is None:
                sys.exit("Keine Kursdaten erhalten — Abbruch.")
            print("⚠ Keine Kursdaten in dieser Runde — nächster Versuch in 6 Minuten.")
        else:
            # Unvollstaendige Abfragen NICHT stillschweigend hinnehmen: Fuer die
            # fehlenden Aktien kann kein Breakout erkannt werden, und ohne
            # Hinweis sieht der Lauf trotzdem erfolgreich aus.
            fehlend = sorted(gewuenscht - set(quotes))
            if fehlend:
                print(f"\n⚠ ACHTUNG: {len(fehlend)} Aktien konnten NICHT geprüft werden:")
                print("  " + ", ".join(fehlend))
                print("  Für diese Werte wird in dieser Runde kein Ausbruch erkannt.")

            treffer, neu = [], []
            for item in items:
                q = quotes.get(item["ticker"].upper())
                if not q:
                    continue
                res = pruefe_breakout(item, q)
                if not res:
                    continue
                # Kennung am Treffer mitfuehren. Vorgemerkt wird ERST nach
                # einem erfolgreichen Push - siehe unten.
                res["key"] = f"{item['ticker']}|{item['nr']}|{item['kaufpunkt']:.2f}"
                treffer.append(res)
                if res["key"] not in schon_gemeldet:
                    neu.append(res)

            print(f"\n{len(treffer)} Kaufpunkte aktuell gerissen, davon {len(neu)} "
                  f"neu seit dem letzten Lauf.")
            for t in treffer:
                marker = "🟢" if t["vol_ok"] is True else ("🟡" if t["vol_ok"] is False else "⚪")
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

            if zu_melden and not args.dry_run:
                if push(topic, zu_melden):
                    for t in zu_melden:
                        schon_gemeldet.add(t["key"])
                        state["gemeldet"][t["key"]] = date.today().isoformat()
                    save_state(state)
                else:
                    print("⚠ Zustand NICHT gespeichert — der nächste Lauf versucht es erneut.")
            elif not zu_melden:
                print("Nichts Neues zu melden.")
            else:
                print("(Dry-Run — kein Push gesendet, Zustand nicht gespeichert)")

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
                else:
                    body = nummeriert([format_gapgo(g) for g in gap_neu])
                    titel = "🚀 Gap and Go: " + ", ".join(g["ticker"]
                                                          for g in gap_neu)
                    if push_text(topic, titel, body):
                        for g in gap_neu:
                            schon_gemeldet.add(g["key"])
                            state["gemeldet"][g["key"]] = date.today().isoformat()
                        save_state(state)

        if ende_dauerwache is None:
            break
        if datetime.now() >= ende_dauerwache:
            print("Dauerwache: Zeit abgelaufen — Ende.")
            break
        offen, grund = markt_offen()
        if not offen:
            print(f"Dauerwache: Börse geschlossen ({grund}) — Ende.")
            break
        time.sleep(360)


if __name__ == "__main__":
    main()
