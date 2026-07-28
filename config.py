#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CONFIG — zentrale Einstellungen für das GESAMTE System
======================================================
Alle Schwellwerte, Fensterlängen und Parameter an EINER Stelle. Jedes Modul
(Scanner, Wächter, Radar, Live-Staffelung) liest ausschließlich von hier.

Warum das der wichtigste Aufräumschritt ist:
  Vorher standen dieselben Werte an mehreren Stellen im Code — z. B. das
  Volumen-Fenster im Scanner UND im Wächter. Weichen die auseinander, rechnen
  zwei Module unbemerkt mit verschiedenen Zahlen. Das erzeugt Fehler, die
  niemand sieht, weil nichts abstürzt. Ab jetzt gibt es die Wahrheit nur hier.

Benutzung im Code:
  from config import CFG
  fenster = CFG["volumen"]["fenster_tage"]

Überschreiben per Umgebungsvariable (optional, für Tests):
  CFG-Werte lassen sich über ENV übersteuern, z. B. SCANNER_VOL_FENSTER=20
  (siehe _aus_env unten). So muss man zum Testen nichts im Code ändern.
"""

import os

# ---------------------------------------------------------------------------
# Zentrale Konfiguration — die EINZIGE Quelle der Wahrheit
# ---------------------------------------------------------------------------

CFG = {

    # --- Volumen (gilt EINHEITLICH für Scanner UND Wächter!) ---
    "volumen": {
        "fenster_tage": 10,          # Durchschnittsvolumen über N Handelstage
        "breakout_faktor": 1.0,      # Standard: Volumen > Ø
        "breakout_faktor_vcp": 1.4,  # VCP strenger: ≥ 140 % vom Ø
        "gap_and_go_faktor": 5.0,    # Gap-and-Go: ≥ 5× Ø am Gap-Tag
    },

    # --- Gleitende Durchschnitte ---
    "ma": {
        "kurz": 21,                  # EMA21
        "mittel": 50,                # EMA50 / MA50
        "lang_1": 150,               # MA150 (Minervini)
        "lang_2": 200,               # MA200 (Minervini)
        "sma_rectangle": 21,         # SMA21-Zusatzfilter Rectangle Top
    },

    # --- 52-Wochen / Lookbacks ---
    "lookback": {
        "jahr_tage": 252,            # 52 Wochen
        "rs_quartale": [63, 126, 189, 252],   # RS-Rating-Fenster
        "rs_gewichte": [0.40, 0.20, 0.20, 0.20],
        "crash_historie_tage": 1000, # ~4 Jahre für Crash-Strategie
    },

    # --- Trigger-Nähe / Live-Kurs-Staffelung (dreistufig) ---
    "staffelung": {
        "stufe1_max_pct": 0.02,      # bis 2 % → schnelle Liste (WebSocket)
        "stufe1_raus_pct": 0.025,    # Hysterese: erst bei 2,5 % zurückstufen
        "stufe1_max_werte": 30,      # Finnhub-WebSocket-Limit-sicher
        "stufe2_max_pct": 0.04,      # 2–4 % → Vorraum (REST-Batch)
        "stufe2_raus_pct": 0.045,    # Hysterese Vorraum → langsam
        "stufe2_max_werte": 100,
        "stufe2_takt_sek": 20,       # Vorraum alle 15–30 s
        "stufe3_takt_sek": 120,      # über 4 % → alle 2 Min (yfinance)
    },

    # --- Strategie-Schwellen ---
    "gap_and_go": {
        "gap_min": 0.07,             # ≥ 7 %
        "schluss_position_min": 0.80,# oberes Fünftel
        "flat_base_wochen": 5,       # ≥ 5 Wochen (≈ 25 Tage)
        "flat_base_max_tiefe": 0.15, # ≤ 15 %
    },
    "red_to_green": {
        "nasdaq_gap_scharf": -0.015, # Nasdaq ≥ 1,5 % im Minus
        "aktie_gap_min": -0.05,      # Aktie ≥ 5 % runter
        "rs_min": 90,                # RS Rating > 90
        "min_ueber_tief": 0.50,      # ≥ 50 % über 52-Wochen-Tief
        "wächter_takt_sek": 45,      # Live-Wächter-Schleife
    },
    "crash_support": {
        "min_marktkap_mrd": 20,
        "min_umsatzwachstum": 0.15,
        "max_debt_to_equity": 0.5,
        "level_score_schwelle": 60,
        "regime_index_drawdown": -0.10,  # SPY ≥ 10 % unter Hoch
    },
    "bottom_fishing": {
        "rsi_periode": 2,
        "rsi_kaufzone": 10,
        "abstand_sma10": -0.09,
    },
    "darvas": {
        "box_tage": 3,
        "frische_max_tage": 25,
    },

    # --- Sektor-Radar ---
    "radar": {
        "kurz_tage": 3,
        "mittel_tage": 10,
        "min_aktien": 3,
        "schwelle": 0.30,
        "bestaetigung_tage": 2,
    },

    # --- Datenquellen-Priorität (Führungsquelle je Zweck) ---
    "datenquellen": {
        "kurse_haupt": "yfinance",
        "kurse_fallback": "finnhub",
        "kurse_websocket": "finnhub",     # nur Stufe 1
        "kurse_vorraum": "twelvedata",    # Stufe 2 REST-Batch
        "fundamental": "fmp",
        "abstand_fuehrungsquelle": "finnhub",  # EINE Quelle bestimmt Trigger-Abstand
    },

    # --- ntfy Push (getrennte Topics + Prioritäten gegen Abstumpfen) ---
    "ntfy": {
        "topic_trigger": None,       # dringende Trigger — aus ENV NTFY_TOPIC_TRIGGER
        "topic_radar": None,         # Sektor-Radar (leiser)
        "topic_health": None,        # täglicher Gesundheits-Check
        "prio_trigger": "high",
        "prio_radar": "default",
        "prio_health": "low",
    },

    # --- Betrieb ---
    "betrieb": {
        "zeitzone_boerse": "America/New_York",  # ALLES in Börsenzeit rechnen
        "stale_max_sekunden": 120,   # Rückfallwert für unbekannte Quellen
        # Veraltungs-Schwelle PRO QUELLE (Gerhard, 28.07.2026). Eine
        # einheitliche 2-Minuten-Grenze wäre falsch: Der WebSocket liefert
        # tickweise — dort heißt zwei Minuten Stille wirklich "Leitung
        # hängt". yfinance liefert verzögert und wird nur alle sechs
        # Minuten abgefragt; mit 2 Minuten wäre dort STÄNDIG alles stale.
        "stale_pro_quelle": {
            "finnhub_ws": 120,       # tickweise: 2 Min Stille = Leitung hängt
            "finnhub": 300,
            "twelvedata": 600,
            "yfinance": 1200,        # verzögert, 6-Minuten-Takt: 20 Minuten
        },
        "min_historie_tage": 60,     # weniger Historie → Aktie überspringen
        # HINWEIS: Das 2000-Minuten-Limit gilt für PRIVATE Repos. heliot ist
        # öffentlich, dort sind die Actions-Minuten unbegrenzt und kostenlos
        # (nachgeprüft 27.07.2026). Die Warnung bleibt für den Fall, dass das
        # Repo je auf privat gestellt wird. Die Grenze, die wirklich beißt,
        # ist eine andere: Ein einzelner Auftrag darf höchstens 6 Stunden
        # laufen — deshalb die Zweiteilung der Wache.
        "actions_minuten_warnung": 1700,
    },
}


# ---------------------------------------------------------------------------
# Optionales Übersteuern per Umgebungsvariable (für Tests, ohne Code-Änderung)
# ---------------------------------------------------------------------------

def _aus_env():
    """Liest ausgewählte ENV-Variablen und überschreibt CFG-Werte.
    ntfy-Topics kommen IMMER aus der Umgebung (Secrets), nie aus dem Code."""
    CFG["ntfy"]["topic_trigger"] = os.environ.get("NTFY_TOPIC_TRIGGER") or os.environ.get("NTFY_TOPIC")
    CFG["ntfy"]["topic_radar"] = os.environ.get("NTFY_TOPIC_RADAR") or os.environ.get("NTFY_TOPIC")
    CFG["ntfy"]["topic_health"] = os.environ.get("NTFY_TOPIC_HEALTH") or os.environ.get("NTFY_TOPIC")

    # Beispielhafte numerische Übersteuerung
    if "SCANNER_VOL_FENSTER" in os.environ:
        try:
            CFG["volumen"]["fenster_tage"] = int(os.environ["SCANNER_VOL_FENSTER"])
        except ValueError:
            pass


_aus_env()


# ---------------------------------------------------------------------------
# Selbstprüfung: fängt Widersprüche in der Config ab
# ---------------------------------------------------------------------------

def pruefe_config():
    """Wirft AssertionError bei unplausiblen/widersprüchlichen Werten.
    Beim Start jedes Moduls einmal aufrufen — fängt Tippfehler früh."""
    s = CFG["staffelung"]
    assert s["stufe1_max_pct"] < s["stufe1_raus_pct"], \
        "Hysterese Stufe 1: raus-Grenze muss GRÖSSER als rein-Grenze sein (sonst Flattern)"
    assert s["stufe2_max_pct"] < s["stufe2_raus_pct"], \
        "Hysterese Stufe 2: raus-Grenze muss größer als rein-Grenze sein"
    assert s["stufe1_max_pct"] < s["stufe2_max_pct"], \
        "Stufe 1 muss näher am Trigger liegen als Stufe 2"
    assert s["stufe1_max_werte"] <= 50, \
        "Finnhub-Gratis-WebSocket verträgt ~50 Symbole — Stufe 1 darf das nicht sprengen"
    assert abs(sum(CFG["lookback"]["rs_gewichte"]) - 1.0) < 1e-9, \
        "RS-Gewichte müssen in Summe 1,0 ergeben"
    assert len(CFG["lookback"]["rs_quartale"]) == len(CFG["lookback"]["rs_gewichte"]), \
        "RS: gleich viele Quartale wie Gewichte"
    assert CFG["volumen"]["fenster_tage"] > 0
    return True


if __name__ == "__main__":
    pruefe_config()
    print("config.py — Selbstprüfung bestanden. Alle Werte konsistent.")
    print(f"  Volumen-Fenster: {CFG['volumen']['fenster_tage']} Tage (einheitlich)")
    print(f"  Staffelung: Stufe1 ≤{CFG['staffelung']['stufe1_max_pct']*100:.0f}% "
          f"(max {CFG['staffelung']['stufe1_max_werte']}), "
          f"Stufe2 ≤{CFG['staffelung']['stufe2_max_pct']*100:.0f}%, "
          f"Stufe3 alle {CFG['staffelung']['stufe3_takt_sek']}s")
