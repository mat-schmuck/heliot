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
    # GERECHNET WIRD AUSSCHLIESSLICH IN volumen.py — IBD "Volume % Change"
    # mit Hochrechnung über die Fünf-Minuten-Referenzkurve. Hier stehen nur
    # noch die Schwellen.
    "volumen": {
        # 50 STATT 10 TAGE (Gerhard, 28.07.2026 nachmittags). IBD-Standard.
        # ACHTUNG für die Akten: Das widerruft seine eigene Festlegung vom
        # Vormittag desselben Tages ("einheitlich 10 Tage für Scanner UND
        # Wächter"). Er hat den Wechsel im Übergabepapier ausdrücklich als
        # eigene, bewusste Entscheidung neben der Formelkorrektur benannt.
        "fenster_tage": 50,          # Durchschnittsvolumen über N Handelstage
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
    # AUSSER BETRIEB seit 28.07.2026. Die Staffelung war nur nötig, solange
    # Finnhubs Gratis-Zugang genau 51 Symbole auf EINER Verbindung trug —
    # dann müssen 265 Aktien um Plätze konkurrieren. Yahoos Live-Strom
    # trägt alle 265 gleichzeitig, also gibt es nichts mehr zu verteilen.
    # Der Block bleibt samt Messwerten stehen, falls jemals wieder eine
    # Quelle mit harter Symbolgrenze dazukommt.
    "staffelung": {
        "stufe1_max_pct": 0.02,      # bis 2 % → schnelle Liste (WebSocket)
        "stufe1_raus_pct": 0.025,    # Hysterese: erst bei 2,5 % zurückstufen
        "stufe1_max_werte": 30,      # Finnhub-WebSocket-Limit-sicher
        "stufe2_max_pct": 0.04,      # 2–4 % → Vorraum (REST-Batch)
        "stufe2_raus_pct": 0.045,    # Hysterese Vorraum → langsam
        "stufe2_max_werte": 100,
        # Gerhards überarbeitete Aufteilung vom 28.07.2026. Der erste
        # Entwurf (100 Werte alle 20 s per REST) sprengt jeden Gratis-Tarif
        # um Größenordnungen — Twelve Data erlaubt 800 Abrufe pro TAG,
        # Finnhub 60 pro Minute, gebraucht würden 300 pro Minute. Statt
        # dessen werden die freien WebSocket-Plätze ausgenutzt: Der Zugang
        # trägt rund 50 Symbole, die schnelle Liste belegt 30, die
        # restlichen ~20 bekommt der OBERE Vorraum — also die Werte knapp
        # über 2 %, die am ehesten gleich hochkommen. Damit gibt es an der
        # 2-%-Grenze keinen blinden Fleck, und alles bleibt gratis.
        # NACHGEMESSEN am 28.07.2026 im laufenden Handel (finnhub_messung.py):
        # 65 sehr liquide Werte abonniert, GENAU 50 lieferten Ticks, die
        # übrigen 15 blieben stumm — und der Server sagte es ausdrücklich:
        # "Subscribing to too many symbols". Die Grenze liegt also exakt bei
        # 50, nicht ungefähr. Tempo war reichlich: 8552 Ticks in 150
        # Sekunden, rund 3400 pro Minute über 50 Symbole.
        # 40 STATT 50 — Mathias' Vorgabe vom 28.07.2026, als BEWUSSTE
        # Reserve, NICHT als Fehlerbehebung. Die Unterscheidung ist wichtig,
        # damit später niemand die Zahl mit einer Messung begründet, die es
        # nicht gibt. Was tatsächlich gemessen wurde (grenztest.py, im
        # laufenden Handel):
        #   - Die harte Grenze liegt bei 51: Beim 52. Symbol antwortet der
        #     Server "Subscribing to too many symbols".
        #   - Bei GENAU 50 abonnierten Schwergewichten lieferten 49
        #     Ticks. Der eine Ausfall (Lowe's) schwieg in der Nachprüfung
        #     auch bei nur 6 Symbolen — also keine Grenzenwirkung.
        #   - Der Listenwechsel an der Grenze (10 ab, 10 an) klappte
        #     vollständig: 10 von 10 Neuen kamen an.
        # Punktgenau an der Grenze zu fahren ginge also technisch. Die
        # Reserve von zehn Plätzen ist eine Entscheidung für Sicherheits-
        # abstand, keine Reparatur. Sie liegt damit zwischen Gerhards
        # Vorgabe (30 am WebSocket, "genug Sicherheitsabstand", Übergabe
        # vom 28.07.2026) und den 50, die beim Umbau daraus geworden waren,
        # weil der Vorraum mangels bezahlbarer REST-Abrufe mit auf den
        # Strom musste.
        #
        # DAVON GETRENNT zu sehen sind die Abdeckungslücken: Der
        # Gratis-Strom trägt nicht jede Aktie. Vodafone, Ovintiv und Lowe's
        # wurden nachweislich gehandelt und kamen selbst bei fünf
        # abonnierten Symbolen mit null Ticks an, während Finnhubs eigener
        # Kursabruf frische Preise lieferte. Das hat mit der Symbolzahl
        # nichts zu tun und lässt sich mit keiner Platzgrenze beheben.
        # Betroffen war rund jeder zwanzigste bis zehnte Wert. Diese Werte
        # laufen über Yahoo weiter und stehen im Protokoll.
        "websocket_max_werte": 40,
        "stufe2_takt_sek": 120,      # restlicher Vorraum: REST alle 2 Min
        "stufe3_takt_sek": 600,      # über 4 %: yfinance alle 10 Min
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
            # Yahoos Live-Strom. NICHT so streng wie beim früheren
            # Finnhub-Strom (2 Minuten): Gemessen am 28.07.2026 lag der
            # letzte Kurs im Mittel 36 Sekunden zurück, drei Viertel unter
            # 102 Sekunden — aber der schlechteste Wert bei 22 Minuten,
            # schlicht weil manche Aktien so selten gehandelt werden. Mit
            # 2 Minuten würde genau dieser Bodensatz ständig als "hängend"
            # verworfen, obwohl der Kurs stimmt. 15 Minuten trennen
            # sauber: Eine echte Störung fällt auf, eine ruhige Aktie nicht.
            "yahoo_ws": 900,
            "finnhub_ws": 120,       # tickweise: 2 Min Stille = Leitung hängt
            "finnhub": 300,
            "twelvedata": 600,
            "yfinance": 1200,        # verzögert, Minutentakt: 20 Minuten
        },
        # Takt des schweren Tagesdaten-Abrufs. Begründung ausführlich in
        # breakout_watcher.py bei TAKT — kurz: nachgemessen, ein Abruf
        # dauert 5 bis 7 Sekunden, zehn hintereinander liefen sauber, und
        # seit Kurs und Volumen live kommen, muss dieser Abruf gar nicht
        # mehr schnell sein.
        "takt_sekunden": 60,
        # Prüftakt: So oft wird auf gerissene Kaufpunkte geprüft. Getrennt
        # vom Datentakt (Mathias, 28.07.2026: "Stelle auf Echtzeit um").
        # Kurs, Tagesvolumen und Tagesspanne kommen laufend aus dem Strom,
        # die Prüfung muss also nicht auf den schweren Abruf warten.
        # Bewusst 2 Sekunden und nicht "bei jeder Kursmeldung": Der Strom
        # schickt rund 3600 Meldungen je Minute — das wären 3600 volle
        # Durchläufe für einen Gewinn von Sekundenbruchteilen. Gegenüber
        # den ursprünglichen sechs Minuten ist das der Faktor 180.
        # FESTER TAKT von 2 Sekunden (Mathias, 30.07.2026 bestätigt):
        # Die Schleife schläft die vollen zwei Sekunden und rechnet dann
        # alles durch. Am 30.07. war das kurzzeitig anders — erst weckte
        # jede Kursmeldung die Prüfung, dann standen 20 Sekunden drin;
        # beides ist zurückgenommen.
        #
        # Die Last bei Yahoo hängt NICHT daran: Der Strom ist eine
        # stehende Verbindung, die von sich aus sendet, und der schwere
        # Tagesdatenabruf läuft unabhängig davon im takt_sekunden.
        # Zwischen 2 und 20 Sekunden liegt dort kein einziger Zugriff
        # Unterschied.
        "pruef_takt_sekunden": 2,
        # Weckuhr und Sammelfenster gab es nur am 30.07.2026 für ein paar
        # Stunden; mit dem festen Zwei-Sekunden-Takt sind sie wieder
        # heraus. Ebenso die Obergrenze von fünf Aktien je Push: Sie
        # zerschnitt Meldungen, die zusammengehören (Mathias: "sonst
        # kommen 2 Nachrichten auf ein Mal, die eig. eine sind").
        # Geteilt wird ausschließlich nach der Zeichenzahl, siehe
        # NTFY_GRENZE in breakout_watcher.py.
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

def letzter_putz_tag():
    """ISO-Datum des jüngsten Freitags-Putzes (Freitag 16:02 New York),
    der bereits VORBEI ist. Steht der heutige Putz noch aus, zählt der
    der Vorwoche.

    Das ist die WOCHENGRENZE des ganzen Systems: Alarme, Melde-Gedächtnis
    des Wächters und das Gesetzt-Gedächtnis des Bots gelten jeweils bis
    hierher. Die Berechnung stand vorher dreimal im Code — genau die Art
    stiller Uneinheitlichkeit, die config.py beseitigen soll."""
    from datetime import datetime, timedelta
    try:
        from zoneinfo import ZoneInfo
        jetzt = datetime.now(ZoneInfo(CFG["betrieb"]["zeitzone_boerse"]))
    except Exception:
        jetzt = datetime.now()
    d = jetzt.date()
    rueck = (d.weekday() - 4) % 7          # Montag=0 … Freitag=4
    freitag = d - timedelta(days=rueck)
    if rueck == 0 and jetzt.hour * 60 + jetzt.minute < 16 * 60 + 2:
        freitag -= timedelta(days=7)
    return freitag.isoformat()


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
        "Finnhub-Gratis-WebSocket verträgt exakt 50 Symbole — Stufe 1 darf das nicht sprengen"
    assert s["stufe1_max_werte"] <= s["websocket_max_werte"], \
        ("Stufe 1 passt nicht in die WebSocket-Liste — die überzähligen Werte "
         "würden stillschweigend gekappt, ausgerechnet die nächsten am Kaufpunkt")
    assert s["websocket_max_werte"] <= 50, \
        "über 50 Symbole weist Finnhub ab ('Subscribing to too many symbols')"
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
