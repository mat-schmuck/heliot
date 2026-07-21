#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PATTERN SCANNER — Kaufpunkte nach Regelwerk (6 bullische Chartmuster)
=====================================================================
Liest eine Finviz-CSV ein, zieht Kurshistorie über die Twelve Data API
und berechnet für jeden Ticker bis zu 3 Kaufpunkte inkl. Strategie-
Kennzeichnung, Stop und Kursziel. Output: farbcodierte Excel-Tabelle.

Muster (gemäß Regelwerk):
  1. Darvas Box
  2. Minervini Trend Template (Filter, kein eigener Kaufpunkt)
  3. Volatility Contraction Pattern (VCP)
  4. Cup & Handle
  5. Rectangle Top
  6. High & Tight Flag

Aufruf:
  export TWELVE_DATA_API_KEY="dein_key"
  python pattern_scanner.py finviz.csv --out kaufpunkte.xlsx
  python pattern_scanner.py finviz.csv --out kaufpunkte.xlsx --ntfy mein-topic

Hinweise:
  - Free-Tier Twelve Data: 8 Calls/min → Script drosselt automatisch
    (--rate 8). 87 Ticker + SPY ≈ 11 Minuten Laufzeit.
  - Zwischenspeicher in ./.cache/ — bei Wiederholung am selben Tag
    werden keine API-Calls verbraucht.
  - RS-Rank wird als Perzentil INNERHALB der eingelesenen Liste plus
    Vergleich gegen SPY berechnet (Näherung an IBD-RS, siehe README).
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, date
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import requests
except ImportError:
    sys.exit("Bitte installieren: pip install requests pandas numpy scipy openpyxl")

from scipy.signal import argrelextrema
from scipy.stats import linregress

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

API_BASE = "https://api.twelvedata.com/time_series"
OUTPUTSIZE = 420          # ~420 Handelstage: reicht für 252d-Rolling + Puffer
CACHE_DIR = Path(".cache")
BENCHMARK = "SPY"

# Regelwerk-Parameter (zentral, damit du sie leicht tunen kannst)
CFG = {
    # Darvas
    "darvas_lookback_52w": 252,
    "darvas_box_days": 3,
    "darvas_vol_avg": 20,
    # Minervini
    "tt_ma_slope_days": 21,          # MA200[t] vs MA200[t-21]
    "tt_min_above_low": 0.25,        # mind. 25 % über 52W-Tief
    "tt_max_below_high": 0.25,       # max. 25 % unter 52W-Hoch
    "tt_rs_min": 70,                 # RS-Perzentil
    # VCP
    "vcp_swing_order": 5,            # Fenster für Swing-Erkennung
    "vcp_min_contractions": 2,
    "vcp_max_contractions": 6,
    "vcp_max_last_depth": 0.12,      # letzte Kontraktion idealerweise eng
    "vcp_vol_breakout": 1.4,         # Breakout-Volumen ≥ 140 % vom Schnitt
    "vcp_stop_pct": 0.08,            # Minervini: 7-8 % unter Einstieg
    # Cup & Handle
    "cup_min_len": 25,               # ~5 Wochen
    "cup_max_len": 130,              # ~6 Monate
    "cup_min_depth": 0.12,
    "cup_max_depth": 0.50,
    "cup_rim_tolerance": 0.06,       # Ränder auf ähnlichem Niveau (±6 %)
    "handle_max_len": 20,
    "handle_min_len": 4,
    "handle_max_retrace": 1 / 3,     # max 1/3 der Cup-Höhe
    "cup_min_score": 80,             # Muster muss zu mind. 80 % erfüllt sein
    # Rectangle
    "rect_lookback": 65,
    "rect_band": 0.02,               # Cluster-Toleranz ±2 %
    "rect_min_touches": 2,
    # Umsatzwachstum (Regelwerk: "Fundamentaldaten-Filter")
    # CAN SLIM (O'Neil) verlangt mindestens 25 % Wachstum im jüngsten Quartal
    # gegenüber dem Vorjahr; Minervini nennt ähnliche Größenordnungen.
    "umsatz_min_wachstum": 0.25,
    # High & Tight Flag
    "htf_min_rise": 0.90,
    "htf_max_pole_days": 42,
    "htf_min_low_price": 1.0,
    "htf_max_flag_cal_days": 35,
    "htf_max_flag_range": 0.25,      # Flag-Range < 25 % der Masthöhe
}


# ---------------------------------------------------------------------------
# Datenabruf (Twelve Data) mit Cache & Rate-Limit
# ---------------------------------------------------------------------------

class RateLimiter:
    def __init__(self, calls_per_min: int):
        self.interval = 60.0 / max(1, calls_per_min)
        self._last = 0.0

    def wait(self):
        delta = time.time() - self._last
        if delta < self.interval:
            time.sleep(self.interval - delta)
        self._last = time.time()


# Ergebnis des Yahoo-Sammelabrufs. Yahoo liefert ALLE Ticker in einem
# einzigen Aufruf (87 Aktien in rund 3 Sekunden), waehrend Twelve Data im
# Gratistarif nur 8 Abfragen je Minute erlaubt und damit rund 11 Minuten
# braucht. Twelve Data bleibt als Rueckfallebene erhalten.
_YAHOO_DATEN: dict = {}
_YAHOO_GELAUFEN = False


def lade_yahoo_sammelabruf(tickers: list[str]) -> int:
    """Holt die Historien aller Ticker in EINEM Abruf von Yahoo.

    Liefert die Anzahl erfolgreich geholter Aktien. Schlaegt der Abruf fehl
    oder fehlt yfinance, bleibt der Speicher leer und jeder Ticker geht
    einzeln ueber Twelve Data — das System laeuft dann langsamer weiter,
    aber es laeuft."""
    global _YAHOO_GELAUFEN
    _YAHOO_GELAUFEN = True
    try:
        import yfinance as yf
    except ImportError:
        print("  yfinance nicht verfügbar — weiche auf Twelve Data aus.")
        return 0

    print(f"  Sammelabruf über Yahoo für {len(tickers)} Aktien …")
    t0 = time.time()
    try:
        roh = yf.download(" ".join(tickers), period="2y", interval="1d",
                          group_by="ticker", progress=False,
                          auto_adjust=False, threads=True)
    except Exception as e:
        print(f"  Yahoo-Sammelabruf fehlgeschlagen ({str(e)[:60]}) — Twelve Data übernimmt.")
        return 0

    for t in tickers:
        try:
            df = roh[t] if len(tickers) > 1 else roh
            df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"]).copy()
            if df.empty:
                continue
            df = df.reset_index()
            # Auf das Format bringen, das der Rest des Programms erwartet
            df = df.rename(columns={"Date": "datetime", "Datetime": "datetime",
                                    "Open": "open", "High": "high", "Low": "low",
                                    "Close": "close", "Volume": "volume"})
            df["datetime"] = pd.to_datetime(df["datetime"]).dt.tz_localize(None)
            for spalte in ("open", "high", "low", "close", "volume"):
                df[spalte] = pd.to_numeric(df[spalte], errors="coerce")
            df = df[["datetime", "open", "high", "low", "close", "volume"]]
            df = df.dropna().sort_values("datetime").reset_index(drop=True)
            if len(df) >= 60:
                _YAHOO_DATEN[t] = df
        except Exception:
            continue

    print(f"  Yahoo lieferte {len(_YAHOO_DATEN)} von {len(tickers)} Aktien "
          f"in {time.time() - t0:.1f} Sekunden.")
    return len(_YAHOO_DATEN)


def hole_fundamentals(tickers: list[str]) -> dict:
    """Holt Umsatz- und Gewinnwachstum je Aktie.

    Das Regelwerk sieht einen Fundamentaldaten-Filter vor ("Umsatzwachstum")
    und nennt dafuer Finnhub. Dessen Gratistarif liefert fuer US-Aktien aber
    keine brauchbaren Fundamentaldaten mehr, waehrend Yahoo sie mitliefert -
    ohne Schluessel und ohne zweiten Anbieter. Geprueft an sechs Aktien:
    alle mit Umsatzwachstum.

    Rueckgabe: {ticker: {"umsatzwachstum": float|None,
                         "gewinnwachstum": float|None}}
    Faellt der Abruf aus, bleibt der Wert None - dann wird nicht gefiltert,
    statt Aktien faelschlich auszuschliessen."""
    try:
        import yfinance as yf
    except ImportError:
        print("  yfinance fehlt — Umsatzfilter übersprungen.")
        return {}

    out = {}
    t0 = time.time()
    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).info
            out[ticker] = {
                "umsatzwachstum": info.get("revenueGrowth"),
                "gewinnwachstum": (info.get("earningsGrowth")
                                   or info.get("earningsQuarterlyGrowth")),
            }
        except Exception:
            out[ticker] = {"umsatzwachstum": None, "gewinnwachstum": None}

    mit_daten = sum(1 for v in out.values() if v["umsatzwachstum"] is not None)
    print(f"  Fundamentaldaten: {mit_daten} von {len(tickers)} Aktien "
          f"in {time.time() - t0:.1f} Sekunden.")
    return out


def yahoo_einzeln(ticker: str) -> pd.DataFrame | None:
    """Einen einzelnen Ticker von Yahoo holen.

    Fuer Aufrufer, die keinen Sammelabruf machen — vor allem die
    Streamlit-App, die immer nur eine Aktie auf einmal anzeigt."""
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        df = yf.download(ticker, period="2y", interval="1d",
                         progress=False, auto_adjust=False)
    except Exception:
        return None
    if df is None or df.empty:
        return None
    # Bei einzelnem Ticker liefert yfinance je nach Fassung mehrstufige Spalten
    if hasattr(df.columns, "levels"):
        df.columns = df.columns.droplevel(1)
    df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"]).reset_index()
    df = df.rename(columns={"Date": "datetime", "Datetime": "datetime",
                            "Open": "open", "High": "high", "Low": "low",
                            "Close": "close", "Volume": "volume"})
    try:
        df["datetime"] = pd.to_datetime(df["datetime"]).dt.tz_localize(None)
    except Exception:
        df["datetime"] = pd.to_datetime(df["datetime"])
    for spalte in ("open", "high", "low", "close", "volume"):
        df[spalte] = pd.to_numeric(df[spalte], errors="coerce")
    df = df[["datetime", "open", "high", "low", "close", "volume"]]
    df = df.dropna().sort_values("datetime").reset_index(drop=True)
    return df if len(df) >= 60 else None


def fetch_history(ticker: str, api_key: str, limiter: RateLimiter) -> pd.DataFrame | None:
    """Tageskurse (OHLCV) holen — mit Tages-Cache, damit Reruns gratis sind.

    Reihenfolge: Tages-Cache, dann Yahoo-Sammelabruf, dann Twelve Data."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / f"{ticker}_{date.today().isoformat()}.csv"
    if cache_file.exists():
        c = pd.read_csv(cache_file); c["datetime"] = pd.to_datetime(c["datetime"]); return c

    # Aus dem Sammelabruf bedienen, falls vorhanden
    if ticker in _YAHOO_DATEN:
        df = _YAHOO_DATEN[ticker]
        df.to_csv(cache_file, index=False)
        return df

    # Kein Sammelabruf gelaufen — etwa in der Streamlit-App, die immer nur
    # eine einzelne Aktie anzeigt. Dann diesen einen Ticker von Yahoo holen.
    df = yahoo_einzeln(ticker)
    if df is not None:
        df.to_csv(cache_file, index=False)
        return df

    # Rueckfallebene: einzeln ueber Twelve Data
    if not api_key:
        return None
    limiter.wait()
    params = {
        "symbol": ticker,
        "interval": "1day",
        "outputsize": OUTPUTSIZE,
        "apikey": api_key,
        "order": "asc",
    }
    try:
        r = requests.get(API_BASE, params=params, timeout=30)
        data = r.json()
    except Exception as e:
        print(f"  [{ticker}] Netzwerkfehler: {e}")
        return None

    if data.get("status") == "error" or "values" not in data:
        print(f"  [{ticker}] API-Fehler: {data.get('message', 'unbekannt')}")
        return None

    df = pd.DataFrame(data["values"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna().sort_values("datetime").reset_index(drop=True)
    if len(df) < 60:
        print(f"  [{ticker}] Zu wenig Historie ({len(df)} Tage) — übersprungen")
        return None
    df.to_csv(cache_file, index=False)
    return df


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    c = df["close"]
    df["ma21"] = c.rolling(21).mean()
    df["ma50"] = c.rolling(50).mean()
    df["ma150"] = c.rolling(150).mean()
    df["ma200"] = c.rolling(200).mean()
    df["vol20"] = df["volume"].rolling(20).mean()
    df["hi52"] = df["high"].rolling(CFG["darvas_lookback_52w"], min_periods=60).max()
    df["lo52"] = df["low"].rolling(CFG["darvas_lookback_52w"], min_periods=60).min()
    return df


def rs_score(df: pd.DataFrame) -> float | None:
    """IBD-ähnlicher RS-Score: gewichtete Returns 3/6/9/12 Monate
    (Gewichtung 2:1:1:1 auf das jüngste Quartal)."""
    c = df["close"]
    if len(c) < 252:
        # so viel nehmen wie da ist, mit gleicher Logik
        if len(c) < 63:
            return None
    def ret(days):
        if len(c) <= days:
            return c.iloc[-1] / c.iloc[0] - 1
        return c.iloc[-1] / c.iloc[-1 - days] - 1
    return 2 * ret(63) + ret(126) + ret(189) + ret(252)


# ---------------------------------------------------------------------------
# Hilfsfunktionen: Swings
# ---------------------------------------------------------------------------

def swing_points(df: pd.DataFrame, order: int):
    """Lokale Swing-Hochs/-Tiefs (Index-Positionen) via argrelextrema."""
    highs = argrelextrema(df["high"].values, np.greater_equal, order=order)[0]
    lows = argrelextrema(df["low"].values, np.less_equal, order=order)[0]
    # doppelte Plateaus entschärfen
    highs = _dedupe(highs)
    lows = _dedupe(lows)
    return highs, lows


def _dedupe(idx: np.ndarray, min_gap: int = 3) -> list[int]:
    out = []
    for i in idx:
        if not out or i - out[-1] >= min_gap:
            out.append(int(i))
    return out


# ---------------------------------------------------------------------------
# 1) DARVAS BOX
# ---------------------------------------------------------------------------

def detect_darvas(df: pd.DataFrame) -> dict | None:
    """52W-Hoch → Box-Top aus 3 Folgetagen → Box-Bottom aus 3 Folgetagen →
    Bestätigung wenn Kurs ≥3 Tage in der Box bleibt.
    Kaufpunkt: Box-Top + 1 Cent (Volumen-Bestätigung als Hinweis)."""
    n = len(df)
    look = min(n, CFG["darvas_lookback_52w"])
    win = df.iloc[-look:]
    hi_pos = int(win["high"].idxmax())          # Position des 52W-Hochs
    bars_after = n - 1 - hi_pos
    if bars_after < 2 * CFG["darvas_box_days"]:
        return None  # Box noch nicht fertig ausgebildet
    if bars_after > 25:
        return None  # 52W-Hoch zu alt — Box muss FRISCH nach neuem Hoch entstehen

    bd = CFG["darvas_box_days"]
    # Box-Top: höchstes Hoch von 52W-Hoch-Tag + 3 Folgetagen
    top_win = df.iloc[hi_pos: hi_pos + 1 + bd]
    box_top = float(top_win["high"].max())
    top_end = hi_pos + bd
    # Box-Bottom: tiefstes Tief der 3 Tage nach Box-Top-Fixierung
    bot_win = df.iloc[top_end + 1: top_end + 1 + bd]
    if len(bot_win) < bd:
        return None
    box_bottom = float(bot_win["low"].min())

    # Bestätigung: seither in der Box geblieben (Schlusskurse)?
    since = df.iloc[top_end + 1:]
    inside = since[(since["close"] <= box_top) & (since["close"] >= box_bottom)]
    last_close = float(since["close"].iloc[-1])
    confirmed = (len(inside) >= bd
                 and len(inside) == len(since)          # KEIN Ausreißer aus der Box
                 and box_bottom <= last_close <= box_top)

    last = df.iloc[-1]
    if not confirmed:
        # Kurs schon ausgebrochen oder Box gerissen → kein frisches Setup
        return None

    return {
        "strategie": "Darvas Box",
        "kaufpunkt": round(box_top + 0.01, 2),
        "stop": round(box_bottom - 0.01, 2),
        "ziel": None,
        "status": "Box bestätigt — auf Breakout mit Volumen warten",
        "notiz": f"Box {box_bottom:.2f}–{box_top:.2f}; Breakout nur mit Vol > Ø20d "
                 f"({last['vol20']:,.0f}) gültig",
    }


# ---------------------------------------------------------------------------
# 2) MINERVINI TREND TEMPLATE (Filter)
# ---------------------------------------------------------------------------

def check_trend_template(df: pd.DataFrame, rs_percentile: float | None) -> tuple[bool, int, list[str]]:
    last = df.iloc[-1]
    if pd.isna(last["ma200"]):
        return False, 0, ["Zu wenig Historie für MA200"]
    slope_ok = False
    if len(df) > 200 + CFG["tt_ma_slope_days"]:
        slope_ok = last["ma200"] > df["ma200"].iloc[-1 - CFG["tt_ma_slope_days"]]
    checks = {
        "Kurs > MA150 & MA200": last["close"] > last["ma150"] and last["close"] > last["ma200"],
        "MA150 > MA200": last["ma150"] > last["ma200"],
        "MA200 steigt (≥1 Monat)": bool(slope_ok),
        "MA50 > MA150 & MA200": last["ma50"] > last["ma150"] and last["ma50"] > last["ma200"],
        "Kurs > MA50": last["close"] > last["ma50"],
        "≥25 % über 52W-Tief": last["close"] >= last["lo52"] * (1 + CFG["tt_min_above_low"]),
        "≤25 % unter 52W-Hoch": last["close"] >= last["hi52"] * (1 - CFG["tt_max_below_high"]),
        "RS-Rank ≥ 70": rs_percentile is not None and rs_percentile >= CFG["tt_rs_min"],
    }
    failed = [k for k, v in checks.items() if not v]
    return len(failed) == 0, sum(checks.values()), failed


# ---------------------------------------------------------------------------
# 3) VCP
# ---------------------------------------------------------------------------

def detect_vcp(df: pd.DataFrame, tt_pass: bool) -> dict | None:
    """Serie abnehmender Kontraktionen + Volume Dry-Up.
    Basisvoraussetzung laut Regelwerk: Trend Template erfüllt."""
    if not tt_pass:
        return None
    sub = df.iloc[-160:].reset_index(drop=True)  # letzte ~7 Monate
    highs, lows = swing_points(sub, CFG["vcp_swing_order"])
    if len(highs) < 2 or len(lows) < 2:
        return None

    # Kontraktionen: Swing-Hoch → nächstes Swing-Tief danach
    contractions = []
    for h in highs:
        nxt = [l for l in lows if l > h]
        if not nxt:
            continue
        l = nxt[0]
        depth = 1 - sub["low"].iloc[l] / sub["high"].iloc[h]
        if 0.005 < depth < 0.40:
            contractions.append({"h": h, "l": l, "depth": depth})

    if len(contractions) < CFG["vcp_min_contractions"]:
        return None
    contractions = contractions[-CFG["vcp_max_contractions"]:]

    depths = [c["depth"] for c in contractions]
    # monoton fallende Tiefen (T1 > T2 > T3 …) — kleine Toleranz von 10 %
    monotone = all(depths[i] > depths[i + 1] * 0.9 for i in range(len(depths) - 1))
    strictly = all(depths[i] > depths[i + 1] for i in range(len(depths) - 1))
    if not monotone:
        return None

    # Volume Dry-Up über die gesamte Formation
    start = contractions[0]["h"]
    vol_seg = sub["volume"].iloc[start:]
    slope = linregress(np.arange(len(vol_seg)), vol_seg.values).slope
    dryup = slope < 0

    pivot = float(sub["high"].iloc[contractions[-1]["h"]:].max())
    last_close = float(sub["close"].iloc[-1])
    if last_close > pivot * 1.02:
        return None  # schon > 2 % über Pivot — Zug abgefahren

    kp = round(pivot + 0.01, 2)
    seq = " → ".join(f"{d*100:.0f}%" for d in depths)
    return {
        "strategie": "VCP",
        "kaufpunkt": kp,
        "stop": round(kp * (1 - CFG["vcp_stop_pct"]), 2),
        "ziel": None,
        "status": ("VCP komplett" if (strictly and dryup)
                   else "VCP (Toleranz)" if dryup
                   else "VCP ohne sauberen Vol-Dry-Up"),
        "notiz": f"Kontraktionen: {seq}; Pivot {pivot:.2f}; "
                 f"Breakout braucht Vol ≥ {CFG['vcp_vol_breakout']*100:.0f}% vom Ø",
    }


# ---------------------------------------------------------------------------
# 4) CUP & HANDLE
# ---------------------------------------------------------------------------

def detect_cup_handle(df: pd.DataFrame) -> dict | None:
    """U-förmiger Cup (quadratischer Fit) + Handle im oberen Drittel.
    Liefert Toleranz-Score statt hartem Ja/Nein (Regelwerk Kap. 4)."""
    sub = df.iloc[-(CFG["cup_max_len"] + CFG["handle_max_len"] + 10):].reset_index(drop=True)
    n = len(sub)
    if n < CFG["cup_min_len"] + CFG["handle_min_len"]:
        return None

    highs, _ = swing_points(sub, 4)
    best = None
    for left in highs:
        if n - left < CFG["cup_min_len"]:
            continue
        left_high = float(sub["high"].iloc[left])
        seg = sub.iloc[left:]
        bot_rel = int(seg["low"].values.argmin())
        bottom = float(seg["low"].iloc[bot_rel])
        depth = 1 - bottom / left_high
        if not (CFG["cup_min_depth"] <= depth <= CFG["cup_max_depth"]):
            continue
        # rechter Rand: erstes Wiedererreichen von ~linkem Rand nach dem Boden
        after_bot = seg.iloc[bot_rel:]
        reach = after_bot[after_bot["high"] >= left_high * (1 - CFG["cup_rim_tolerance"])]
        if reach.empty:
            continue
        right = int(reach.index[0])            # Position in sub
        cup_len = right - left
        if not (CFG["cup_min_len"] <= cup_len <= CFG["cup_max_len"]):
            continue
        # Symmetrie: Boden ungefähr mittig (25–75 % der Cup-Länge)
        bot_abs = left + bot_rel
        sym = (bot_abs - left) / cup_len
        if not (0.2 <= sym <= 0.8):
            continue
        # U-Form: quadratischer Fit über die Cup-Tiefs, Öffnung nach oben
        x = np.arange(cup_len + 1)
        y = sub["low"].iloc[left:right + 1].values
        coef = np.polyfit(x, y, 2)
        fit = np.polyval(coef, x)
        ss_res = float(np.sum((y - fit) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2)) or 1e-9
        r2 = 1 - ss_res / ss_tot
        u_ok = coef[0] > 0 and r2 > 0.55
        # Handle nach rechtem Rand
        handle = sub.iloc[right:]
        if len(handle) < CFG["handle_min_len"] or len(handle) > CFG["handle_max_len"] + 8:
            continue
        h_high = float(handle["high"].iloc[0:3].max())
        h_low = float(handle["low"].min())
        retrace = (h_high - h_low) / (left_high - bottom + 1e-9)
        in_upper_third = h_low >= bottom + (left_high - bottom) * (2 / 3)
        if retrace > CFG["handle_max_retrace"] or not in_upper_third:
            continue

        # VOLUMENVERLAUF — laut Regelwerk Pflichtbestandteil des Musters:
        # "Volumen fällt tendenziell im Verlauf des Cups (besonders am Boden)
        #  und steigt wieder Richtung rechtem Rand."
        # "Volumen sollte während des Handles niedrig/rückläufig sein."
        # Das wurde bisher gar nicht geprüft.
        cup_vol = sub["volume"].iloc[left:right + 1].values
        drittel = max(1, len(cup_vol) // 3)
        vol_links = float(cup_vol[:drittel].mean())
        vol_boden = float(cup_vol[drittel:2 * drittel].mean()) if len(cup_vol) > drittel else vol_links
        vol_rechts = float(cup_vol[-drittel:].mean())
        # Am Boden soll weniger gehandelt werden als am linken Rand
        vol_trocknet = vol_boden < vol_links
        # Richtung rechtem Rand soll es wieder anziehen
        vol_zieht_an = vol_rechts > vol_boden
        # Im Handle soll es ruhig sein — gemessen am Cup-Durchschnitt
        vol_handle = float(handle["volume"].mean())
        vol_cup_schnitt = float(cup_vol.mean()) or 1.0
        handle_ruhig = vol_handle < vol_cup_schnitt

        # Score: 100 Punkte, davon 25 für den Volumenverlauf. Ein Muster ohne
        # passendes Volumen ist nach Regelwerk kein sauberes Cup & Handle.
        vol_punkte = (10 * (1 if vol_trocknet else 0)
                      + 8 * (1 if vol_zieht_an else 0)
                      + 7 * (1 if handle_ruhig else 0))
        score = (
            30 * min(1.0, r2 / 0.85)
            + 15 * (1 - abs(sym - 0.5) * 2)
            + 15 * (1 - retrace / CFG["handle_max_retrace"])
            + 15 * (1 if u_ok else 0.3)
            + vol_punkte
        )
        cand = {"left_high": left_high, "bottom": bottom, "h_high": h_high,
                "depth": depth, "score": score, "cup_len": cup_len,
                "vol_trocknet": vol_trocknet, "vol_zieht_an": vol_zieht_an,
                "handle_ruhig": handle_ruhig}
        if best is None or cand["score"] > best["score"]:
            best = cand

    # Schwelle 80 von 100 (Vorgabe Mathias, 21.07.2026). Vorher stand hier
    # 55 — damit galten auch Formationen als Cup & Handle, die das Muster
    # nur knapp zur Hälfte erfüllten.
    if best is None or best["score"] < CFG["cup_min_score"]:
        return None
    kp = round(best["h_high"] + 0.01, 2)
    ziel = round(kp + (best["left_high"] - best["bottom"]), 2)
    return {
        "strategie": "Cup & Handle",
        "kaufpunkt": kp,
        "stop": round(best["bottom"] + (best["left_high"] - best["bottom"]) * (2 / 3), 2),
        "ziel": ziel,
        "status": f"Score {best['score']:.0f}/100",
        "notiz": (f"Cup-Tiefe {best['depth']*100:.0f} %, Länge {best['cup_len']} Tage; "
                  f"Volumen: {'trocknet am Boden' if best['vol_trocknet'] else 'trocknet NICHT'}, "
                  f"{'zieht rechts an' if best['vol_zieht_an'] else 'zieht rechts nicht an'}, "
                  f"Handle {'ruhig' if best['handle_ruhig'] else 'unruhig'}; "
                  f"Ziel = Breakout + Cup-Höhe"),
    }


# ---------------------------------------------------------------------------
# 5) RECTANGLE TOP
# ---------------------------------------------------------------------------

def detect_rectangle(df: pd.DataFrame) -> dict | None:
    """Horizontale Range: ≥2 Berührungen oben UND unten.
    Kaufstopp 1 Cent über Rectangle-Top, Zusatzfilter Kurs > SMA21."""
    sub = df.iloc[-CFG["rect_lookback"]:].reset_index(drop=True)
    highs, lows = swing_points(sub, 3)
    if len(highs) < 2 or len(lows) < 2:
        return None

    hvals = sub["high"].iloc[highs].values
    lvals = sub["low"].iloc[lows].values
    top = float(np.median(hvals))
    bot = float(np.median(lvals))
    band = CFG["rect_band"]
    top_touch = int(np.sum(np.abs(hvals / top - 1) <= band))
    bot_touch = int(np.sum(np.abs(lvals / bot - 1) <= band))
    if top_touch < CFG["rect_min_touches"] or bot_touch < CFG["rect_min_touches"]:
        return None
    if (top - bot) / top < 0.03 or (top - bot) / top > 0.25:
        return None  # zu flach (Rauschen) oder zu breit (keine Range)

    last = df.iloc[-1]
    if float(last["close"]) > top * 1.02:
        return None  # bereits ausgebrochen
    above_sma21 = float(last["close"]) > float(last["ma21"]) if not pd.isna(last["ma21"]) else False

    kp = round(top + 0.01, 2)
    return {
        "strategie": "Rectangle Top",
        "kaufpunkt": kp,
        "stop": round(bot - 0.01, 2),
        "ziel": round(kp + (top - bot), 2),
        "status": ("Setup komplett (Kurs > SMA21)" if above_sma21
                   else "Range steht — SMA21-Filter noch NICHT erfüllt"),
        "notiz": f"Range {bot:.2f}–{top:.2f}; Berührungen oben {top_touch}, "
                 f"unten {bot_touch}; Ziel = Ausbruch + Rechteckhöhe",
    }


# ---------------------------------------------------------------------------
# 6) HIGH & TIGHT FLAG
# ---------------------------------------------------------------------------

def detect_htf(df: pd.DataFrame) -> dict | None:
    sub = df.iloc[-110:].reset_index(drop=True)
    n = len(sub)
    if n < 50:
        return None
    lows = sub["low"].values
    highs = sub["high"].values

    best = None
    for i in range(n - 10):
        lo = lows[i]
        if lo < CFG["htf_min_low_price"]:
            continue
        j_end = min(n, i + CFG["htf_max_pole_days"] + 1)
        seg = highs[i:j_end]
        j_rel = int(seg.argmax())
        hi = seg[j_rel]
        rise = hi / lo - 1
        if rise >= CFG["htf_min_rise"]:
            cand = {"i": i, "j": i + j_rel, "lo": float(lo), "hi": float(hi), "rise": rise}
            if best is None or cand["rise"] > best["rise"]:
                best = cand
    if best is None:
        return None

    j = best["j"]
    flag = sub.iloc[j:]
    if len(flag) < 3:
        return None
    cal_days = (sub["datetime"].iloc[-1] - sub["datetime"].iloc[j]).days
    if cal_days > CFG["htf_max_flag_cal_days"]:
        return None
    pole_h = best["hi"] - best["lo"]
    flag_range = float(flag["high"].max() - flag["low"].min())
    if flag_range > pole_h * CFG["htf_max_flag_range"]:
        return None
    vol_slope = linregress(np.arange(len(flag)), flag["volume"].values).slope if len(flag) > 3 else -1
    flag_high = float(flag["high"].max())
    if float(sub["close"].iloc[-1]) > flag_high * 1.02:
        return None

    kp = round(flag_high + 0.01, 2)
    return {
        "strategie": "High & Tight Flag",
        "kaufpunkt": kp,
        "stop": round(float(flag["low"].min()) - 0.01, 2),
        "ziel": None,
        "status": ("HTF komplett" if vol_slope < 0 else "HTF, aber Volumen fällt nicht sauber"),
        "notiz": f"Mast +{best['rise']*100:.0f}% in {j - best['i']} Tagen; "
                 f"Flag {cal_days} Kalendertage, Range {flag_range/pole_h*100:.0f}% der Masthöhe",
    }


# ---------------------------------------------------------------------------
# Fallback-Kaufpunkte (wenn < 3 Muster aktiv)
# ---------------------------------------------------------------------------

def fallback_points(df: pd.DataFrame) -> list[dict]:
    """Liefert IMMER >=4 Kandidaten, damit jede Aktie auf 3 Kaufpunkte kommt."""
    last = df.iloc[-1]
    close = float(last["close"])
    out = []
    hi52 = float(last["hi52"])
    out.append({
        "strategie": "Fallback: 52W-Hoch-Breakout",
        "kaufpunkt": round(hi52 * 1.001, 2),
        "stop": round(hi52 * 0.93, 2),
        "ziel": None,
        "status": "Kein Muster — generischer Breakout-Level",
        "notiz": f"52W-Hoch {hi52:.2f}",
    })
    kons_high = float(df["high"].iloc[-20:].max())
    out.append({
        "strategie": "Fallback: 20-Tage-Hoch (Pivot)",
        "kaufpunkt": round(kons_high + 0.01, 2),
        "stop": round(float(df["low"].iloc[-20:].min()) - 0.01, 2),
        "ziel": None,
        "status": "Kein Muster — Konsolidierungs-Pivot",
        "notiz": "Hoch der letzten 20 Handelstage",
    })
    if not pd.isna(last["ma50"]):
        ma50 = float(last["ma50"])
        if close > ma50:
            out.append({
                "strategie": "Fallback: MA50-Pullback",
                "kaufpunkt": round(ma50 * 1.005, 2),
                "stop": round(ma50 * 0.95, 2),
                "ziel": None,
                "status": "Kein Muster — Rücksetzer-Kauf am MA50",
                "notiz": f"MA50 aktuell {ma50:.2f} (nur bei intaktem Trend nutzen)",
            })
        else:
            out.append({
                "strategie": "Fallback: MA50-Rückeroberung",
                "kaufpunkt": round(ma50 * 1.005, 2),
                "stop": round(ma50 * 0.94, 2),
                "ziel": None,
                "status": "Kurs UNTER MA50 — erst bei Reclaim interessant",
                "notiz": f"MA50 aktuell {ma50:.2f}; Kauf erst wenn Schlusskurs drüber",
            })
    hi63 = float(df["high"].iloc[-63:].max())
    out.append({
        "strategie": "Fallback: Quartals-Hoch (63 Tage)",
        "kaufpunkt": round(hi63 + 0.01, 2),
        "stop": round(hi63 * 0.92, 2),
        "ziel": None,
        "status": "Kein Muster — mittelfristiger Widerstand",
        "notiz": "Hoch der letzten 63 Handelstage",
    })
    return out


# ---------------------------------------------------------------------------
# Auswertung je Ticker
# ---------------------------------------------------------------------------

PRIORITY = ["High & Tight Flag", "VCP", "Cup & Handle", "Darvas Box", "Rectangle Top"]


def analyze(df: pd.DataFrame, rs_percentile: float | None) -> dict:
    df = add_indicators(df)
    last = df.iloc[-1]
    tt_pass, tt_count, tt_failed = check_trend_template(df, rs_percentile)

    hits = []
    for fn in (detect_htf, lambda d: detect_vcp(d, tt_pass), detect_cup_handle,
               detect_darvas, detect_rectangle):
        try:
            res = fn(df)
        except Exception as e:
            res = None
            print(f"    Detektor-Fehler ({fn}): {e}")
        if res:
            hits.append(res)

    hits.sort(key=lambda h: PRIORITY.index(h["strategie"]) if h["strategie"] in PRIORITY else 99)
    points = hits[:3]
    if len(points) < 3:
        fbs = fallback_points(df)
        # 1. Pass: nur Levels, die sich von vorhandenen unterscheiden (>0,5 %)
        for fb in fbs:
            if len(points) >= 3:
                break
            if all(abs(fb["kaufpunkt"] - p["kaufpunkt"]) / fb["kaufpunkt"] > 0.005 for p in points):
                points.append(fb)
        # 2. Pass: notfalls trotzdem auffüllen (andere Strategie-Logik, ähnlicher Preis)
        for fb in fbs:
            if len(points) >= 3:
                break
            if all(fb["strategie"] != p["strategie"] for p in points):
                points.append(fb)

    return {
        "close": float(last["close"]),
        "hi52": float(last["hi52"]),
        "lo52": float(last["lo52"]),
        "rs": rs_percentile,
        "tt_pass": tt_pass,
        "tt_count": tt_count,
        "tt_failed": tt_failed,
        "pattern_count": len(hits),
        "points": points,
    }


# ---------------------------------------------------------------------------
# Excel-Output (farbcodiert)
# ---------------------------------------------------------------------------

def write_excel(rows: list[dict], out_path: str):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    GREEN = PatternFill("solid", start_color="C6EFCE")
    YELLOW = PatternFill("solid", start_color="FFEB9C")
    GREY = PatternFill("solid", start_color="EDEDED")
    HEAD = PatternFill("solid", start_color="1F4E78")
    thin = Border(*[Side(style="thin", color="BBBBBB")] * 4)

    wb = Workbook()
    ws = wb.active
    ws.title = "Kaufpunkte"
    headers = ["Ticker", "Firma", "Kurs", "52W-Hoch", "52W-Tief", "Abst. 52W-Hoch",
               "RS-Rank", "Trend Template", "Umsatzwachstum", "Gewinnwachstum",
               "KP1 Strategie", "KP1 Preis", "KP1 Abst.", "KP1 Stop", "KP1 Ziel", "KP1 Status",
               "KP2 Strategie", "KP2 Preis", "KP2 Abst.", "KP2 Stop", "KP2 Ziel", "KP2 Status",
               "KP3 Strategie", "KP3 Preis", "KP3 Abst.", "KP3 Stop", "KP3 Ziel", "KP3 Status",
               "Notizen"]
    ws.append(headers)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = HEAD
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    def dist(kp, close):
        return f"{(kp / close - 1) * 100:+.1f}%" if kp and close else ""

    # Sortierung: echte Muster zuerst, dann Trend-Template-Treffer
    rows_sorted = sorted(rows, key=lambda r: (-r["res"]["pattern_count"],
                                              not r["res"]["tt_pass"],
                                              r["ticker"]))
    for row in rows_sorted:
        r = row["res"]
        line = [row["ticker"], row["company"], round(r["close"], 2),
                round(r["hi52"], 2), round(r["lo52"], 2),
                f"{(r['close'] / r['hi52'] - 1) * 100:+.1f}%",
                round(r["rs"]) if r["rs"] is not None else "n/a",
                f"✓ 8/8" if r["tt_pass"] else f"✗ {r['tt_count']}/8"]

        # Fundamentaldaten laut Regelwerk. Fehlt der Wert, steht "n/a" —
        # das ist etwas anderes als "Wachstum zu gering" und darf nicht
        # verwechselt werden.
        fund = row.get("fundamentals") or {}
        for schluessel, grenze in (("umsatzwachstum", CFG["umsatz_min_wachstum"]),
                                   ("gewinnwachstum", None)):
            wert = fund.get(schluessel)
            if wert is None:
                line.append("n/a")
            else:
                marke = ""
                if grenze is not None:
                    marke = "✓ " if wert >= grenze else "✗ "
                line.append(f"{marke}{wert * 100:+.0f}%")
        notes = []
        for i in range(3):
            if i < len(r["points"]):
                p = r["points"][i]
                line += [p["strategie"], p["kaufpunkt"], dist(p["kaufpunkt"], r["close"]),
                         p["stop"], p["ziel"] if p["ziel"] else "", p["status"]]
                notes.append(f"KP{i+1}: {p['notiz']}")
            else:
                line += [""] * 6
        if not r["tt_pass"] and r["tt_failed"]:
            notes.append("TT fehlt: " + "; ".join(r["tt_failed"][:3]))
        line.append(" | ".join(notes))
        ws.append(line)

        fill = GREEN if r["pattern_count"] >= 1 else (YELLOW if r["tt_pass"] else GREY)
        for c in ws[ws.max_row]:
            c.fill = fill
            c.border = thin

    widths = [8, 26, 9, 10, 10, 12, 8, 12, 15, 15] + [18, 9, 9, 9, 9, 30] * 3 + [60]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w
    ws.freeze_panes = "C2"

    # Legende
    lg = wb.create_sheet("Legende")
    lg.append(["Farbe", "Bedeutung"])
    lg.append(["Grün", "Mindestens 1 echtes Chartmuster aktiv (Kaufpunkte = Muster-Trigger)"])
    lg.append(["Gelb", "Kein Muster, aber Minervini Trend Template 8/8 erfüllt (Fallback-Level)"])
    lg.append(["Grau", "Weder Muster noch Trend Template — Fallback-Level nur zur Orientierung"])
    lg.append([])
    lg.append(["Hinweis", "Alle Breakout-Kaufpunkte gelten nur mit Volumen-Bestätigung "
                          "(Regelwerk). RS-Rank = Perzentil innerhalb der gescannten Liste."])
    lg["A1"].fill = HEAD; lg["B1"].fill = HEAD
    lg["A1"].font = Font(bold=True, color="FFFFFF"); lg["B1"].font = Font(bold=True, color="FFFFFF")
    lg["A2"].fill = GREEN; lg["A3"].fill = YELLOW; lg["A4"].fill = GREY
    lg.column_dimensions["A"].width = 12; lg.column_dimensions["B"].width = 95

    wb.save(out_path)


# ---------------------------------------------------------------------------
# ntfy-Push (optional)
# ---------------------------------------------------------------------------

def push_ntfy(topic: str, rows: list[dict]):
    hot = [r for r in rows if r["res"]["pattern_count"] >= 1]
    if not hot:
        return
    lines = []
    for r in hot[:15]:
        p = r["res"]["points"][0]
        lines.append(f"{r['ticker']}: {p['strategie']} — KP {p['kaufpunkt']}")
    body = "\n".join(lines)
    try:
        requests.post(f"https://ntfy.sh/{topic}", data=body.encode("utf-8"),
                      headers={"Title": f"Pattern-Scanner: {len(hot)} Treffer"}, timeout=15)
        print(f"Push an ntfy.sh/{topic} gesendet ({len(hot)} Treffer).")
    except Exception as e:
        print(f"ntfy-Fehler: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_tickers(csv_path: str) -> list[tuple[str, str]]:
    df = pd.read_csv(csv_path)
    tcol = next((c for c in df.columns if c.strip().lower() == "ticker"), None)
    if tcol is None:
        sys.exit("CSV enthält keine 'Ticker'-Spalte.")
    ccol = next((c for c in df.columns if c.strip().lower() == "company"), None)
    out, seen = [], set()
    for _, row in df.iterrows():
        t = str(row[tcol]).strip().upper()
        if t and t != "NAN" and t not in seen:
            seen.add(t)
            out.append((t, str(row[ccol]) if ccol else ""))
    return out


def main():
    ap = argparse.ArgumentParser(description="Pattern-Scanner nach Regelwerk (6 Muster)")
    ap.add_argument("csv", help="Finviz-CSV mit Ticker-Spalte")
    ap.add_argument("--out", default="kaufpunkte.xlsx", help="Excel-Ausgabedatei")
    ap.add_argument("--rate", type=int, default=8, help="API-Calls pro Minute (Free-Tier: 8)")
    ap.add_argument("--ntfy", default=None, help="ntfy.sh-Topic für Push (optional)")
    ap.add_argument("--limit", type=int, default=None, help="Nur die ersten N Ticker (zum Testen)")
    args = ap.parse_args()

    # Der Schluessel ist nur noch fuer die Rueckfallebene noetig: Hauptquelle
    # ist der Yahoo-Sammelabruf. Ohne Schluessel laeuft alles weiter, solange
    # Yahoo antwortet — faellt Yahoo aus, fehlen dann allerdings die Daten.
    api_key = os.environ.get("TWELVE_DATA_API_KEY")
    if not api_key:
        print("⚠ Kein TWELVE_DATA_API_KEY gesetzt — es gibt dann keine "
              "Rückfallebene, falls Yahoo ausfällt.")

    tickers = load_tickers(args.csv)
    if args.limit:
        tickers = tickers[: args.limit]
    if not tickers:
        sys.exit("Keine Ticker in der CSV gefunden.")
    dauer = len(tickers) / args.rate
    print(f"{len(tickers)} Ticker geladen. Bei {args.rate} Calls/min dauert das "
          f"~{dauer:.0f} Minuten (Cache-Treffer sind gratis).")
    if len(tickers) > 750:
        print("⚠ ACHTUNG: Twelve-Data-Free-Tier erlaubt nur 800 API-Calls pro TAG. "
              f"Bei {len(tickers)} Tickern wird das Limit gerissen — Aktien am Ende der "
              "Liste liefern dann Fehler. Optionen: Liste splitten und an 2 Tagen laufen "
              "lassen (Cache merkt sich Tag 1), oder Twelve-Data-Bezahlplan.")
    if dauer > 170:
        print("⚠ Hinweis: Läuft das in GitHub Actions, muss timeout-minutes im Workflow "
              f"über {dauer:.0f} liegen (Maximum bei GitHub: 360).")

    limiter = RateLimiter(args.rate)

    # Zuerst der Sammelabruf: holt alles auf einmal und macht die Schleife
    # unten praktisch kostenlos. Faellt er aus, geht jeder Ticker einzeln
    # ueber Twelve Data — langsamer, aber es laeuft.
    alle_ticker = [t for t, _ in tickers] + [BENCHMARK]
    lade_yahoo_sammelabruf(alle_ticker)

    # 1. Durchlauf: Daten holen + RS-Rohscore
    loaded, raw_rs = {}, {}
    for i, (ticker, company) in enumerate(tickers, 1):
        print(f"[{i}/{len(tickers)}] {ticker} …")
        df = fetch_history(ticker, api_key, limiter)
        if df is None:
            continue
        loaded[ticker] = (df, company)
        s = rs_score(df)
        if s is not None:
            raw_rs[ticker] = s

    # RS-Perzentile innerhalb der Liste
    rs_pct = {}
    if raw_rs:
        ser = pd.Series(raw_rs)
        rs_pct = (ser.rank(pct=True) * 100).to_dict()

    # Fundamentaldaten laut Regelwerk (Umsatzwachstum-Filter)
    fundamentals = hole_fundamentals(list(loaded.keys()))

    # 2. Durchlauf: Muster analysieren
    rows = []
    for ticker, (df, company) in loaded.items():
        res = analyze(df, rs_pct.get(ticker))
        rows.append({"ticker": ticker, "company": company, "res": res,
                     "fundamentals": fundamentals.get(ticker, {})})
        tag = "🟢" if res["pattern_count"] else ("🟡" if res["tt_pass"] else "⚪")
        pats = ", ".join(p["strategie"] for p in res["points"] if not p["strategie"].startswith("Fallback"))
        print(f"  {tag} {ticker}: {res['pattern_count']} Muster"
              + (f" ({pats})" if pats else ""))

    write_excel(rows, args.out)
    print(f"\nFertig → {args.out}")
    n_green = sum(1 for r in rows if r["res"]["pattern_count"] >= 1)
    n_tt = sum(1 for r in rows if r["res"]["tt_pass"])
    print(f"Treffer: {n_green} mit aktivem Muster, {n_tt} bestehen das Trend Template.")

    if args.ntfy:
        push_ntfy(args.ntfy, rows)


if __name__ == "__main__":
    main()
