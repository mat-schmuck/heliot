#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KAPITEL 8 — CRASH-SUPPORT (REKONSTRUKTION, nicht Gerhards Original)
====================================================================
LIES DIESEN KOPF, BEVOR DU DEM MODUL GLAUBST.

Ein Kapitel 8 hat es nie gegeben. Was es gibt, ist an drei Stellen
verstreut und umfasst SECHS Angaben:

  aus der Uebergabe vom 28.07.2026, Block "crash_support" —
     min_marktkap_mrd:        20        Grossunternehmen
     min_umsatzwachstum:      0.15      Umsatz waechst noch
     max_debt_to_equity:      0.5       wenig Schulden
     level_score_schwelle:    60        starke Unterstuetzungszone
     regime_index_drawdown:  -0.10      "SPY >= 10 % unter Hoch"

  aus dem Exit-Dokument vom 05.08.2026, Stopp-Tabelle —
     "Kap. 8 Crash-Support -> Unterkante der Unterstuetzungszone"

Aus diesen sechs Angaben ergibt sich der Sinn eindeutig: Waehrend einer
Marktkorrektur werden auch gesunde Grossunternehmen mit nach unten
gerissen. Wo so eine Aktie auf eine starke Unterstuetzungszone trifft,
wird gekauft, und die Unterkante dieser Zone traegt den Stopp.

WAS DAVON GEGEBEN IST und was ich ableiten musste
--------------------------------------------------
GEGEBEN sind die vier Filter, die Zonen-Schwelle, der Regime-Schalter
und der Stopp. Sie stehen unten unwidersprochen im Code.

ABGELEITET habe ich alles, was einen Zeitpunkt betrifft — die sechs
Angaben sagen WELCHE Aktie und WO der Stopp liegt, aber nicht WANN
gekauft wird. Jede dieser Stellen ist im Code mit "ABGELEITET"
gekennzeichnet, damit Gerhard sie einzeln bestaetigen oder umwerfen
kann, statt sie unbemerkt zu erben:

  1. Der Ausloeser. Ein Schlusskurs IN der Zone (Vorgabe "zone_schluss"):
     Die Aktie ist unten angekommen und die Unterstuetzung hat auf
     Schlusskursbasis gehalten. Die Alternative "rueckeroberung"
     (Schluss wieder ueber der Oberkante nach einem Unterschreiten)
     ist als Schalter eingebaut, aber nicht die Vorgabe — sie waere
     nahezu deckungsgleich mit Kapitel 10, und dann braeuchte es
     Kapitel 8 nicht.
  2. Der Kaufpunkt. Der Schlusskurs des Ausloesetags.
  3. Das Kursziel. Wyckoffs Zielprojektion wie in Kapitel 10 — Hoehe
     der Zone auf ihre Oberkante gesetzt.
  4. Der Bezug des Rueckgangs. Das 52-Wochen-Hoch des SPY auf
     Schlusskursbasis.
  5. Die Einheit von debtToEquity. Yahoo liefert PROZENT (29.1 heisst
     0.29). Gerhards 0.5 ist ein Verhaeltnis. Ohne Umrechnung wuerde
     der Filter nie greifen, weil 29.1 <= 0.5 nie zutrifft.

WAS DAS MODUL NICHT TUT
     Es erzeugt keine Kaufpunkte in der Excel-Liste. Seine Funde gehen
     ins Trigger-Logbuch, bis Gerhard die fuenf abgeleiteten Punkte
     bestaetigt hat. Rekonstruiertes Regelwerk gehoert nicht
     stillschweigend in den Echtbetrieb.

GEMESSEN AM 06.08.2026 — der Stopp passt nicht zum Einstieg
------------------------------------------------------------
16 Grossunternehmen, fuenf Jahre, alle Tage mit scharfem Regime
(Baerenmarkt 2022 und der Einbruch im April 2025): 44 Signale.

Die RICHTUNG stimmt. Ohne Stopp 40 Tage gehalten: 73 % im Plus,
Median +10,4 %. Qualitaetsaktien an starker Unterstuetzung steigen
nach einer Korrektur also tatsaechlich.

Der STOPP zerstoert das. Er liegt auf der Unterkante der Zone, und
die Zonen sind schmal: Median 1,16 % unter dem Einstieg, der engste
0,01 %. Das ist normales Tagesrauschen. 36 der 44 Signale werden
binnen 40 Tagen ausgestoppt (82 %), uebrig bleiben 18 % Treffer und
ein Median von -1,0 %.

Mit einem Mindestabstand statt der Zonenkante (Schlusskursbasis,
40 Tage, sonst alles gleich):
     ohne  36 von 44 ausgestoppt, 18 % Treffer, Median -1,0 %
     3 %   30 von 44,              32 % Treffer, Median -3,0 %
     5 %   28 von 44,              36 % Treffer, Median -5,0 %
     7 %   24 von 44,              45 % Treffer, Median -7,0 %
    10 %   20 von 44,              52 % Treffer, Median +4,6 %

Der 10-%-Deckel des Exit-Regelwerks allein waere also besser als
Gerhards Strukturstopp. Die Rueckeroberungs-Variante loest das nicht
(Median 2,49 % Abstand, 83 % ausgestoppt, und nur 6 Signale).

DAS IST EINE LUECKE IM EXIT-REGELWERK, nicht nur in Kapitel 8:
berechne_initialen_stop() deckelt den Stopp nach UNTEN (nie mehr als
10 % Risiko), aber nichts haelt ihn davon ab, zu NAH zu liegen. Wo
der Strukturpunkt beim Einstieg liegt, ist der Stopp wertlos. Das
betrifft jedes Muster mit einem nahen Strukturpunkt und gehoert
Gerhard vorgelegt, bevor hier ein Mindestabstand erfunden wird.

Aufruf:
    python crash_support.py --selbsttest
    python crash_support.py --regime            Ist die Strategie scharf?
    python crash_support.py AAPL MSFT NVDA      einzelne Aktien pruefen
"""

import argparse
import sys

from config import CFG, mind_erreicht, hoechstens
from shakeout import berechne_level_scores, wochenkurse_aus_tageskursen

NAME = "Crash-Support"          # muss zu exit_regeln.STRUKTURPUNKT passen
INDEX = "SPY"


def cfg():
    return CFG["crash_support"]


# ---------------------------------------------------------------------------
# Der Regime-Schalter: nur im Rueckgang scharf
# ---------------------------------------------------------------------------

def index_rueckgang(df_index):
    """Wie weit steht der Index unter seinem 52-Wochen-Hoch?

    ABGELEITET: Schlusskursbasis und 52 Wochen. Gerhard nennt nur
    'SPY >= 10 % unter Hoch' ohne Zeitraum; 52 Wochen ist der
    uebliche Bezug und deckt sich mit dem Rest des Regelwerks."""
    if df_index is None or len(df_index) < 2:
        return None
    fenster = df_index["Close"].tail(252)
    hoch = float(fenster.max())
    if hoch <= 0:
        return None
    return float(fenster.iloc[-1]) / hoch - 1


def regime_scharf(df_index):
    """Ist die Strategie ueberhaupt anwendbar?

    GEGEBEN: regime_index_drawdown -0.10. Der Rueckgang ist negativ,
    die Schwelle auch — 'mindestens 10 % unter Hoch' heisst deshalb
    'Rueckgang HOECHSTENS -0.10'."""
    r = index_rueckgang(df_index)
    if r is None:
        return False, None
    return hoechstens(r, cfg()["regime_index_drawdown"]), r


# ---------------------------------------------------------------------------
# Die Fundamentalfilter
# ---------------------------------------------------------------------------

def verhaeltnis_schulden(wert):
    """Yahoos debtToEquity in ein Verhaeltnis umrechnen.

    ABGELEITET, aber zwingend: Yahoo liefert 29.118 fuer ein
    Verhaeltnis von 0.29. Gemessen an MSFT am 06.08.2026. Werte ueber
    3 koennen kein Verhaeltnis mehr sein und werden als Prozent
    gelesen; darunter bleibt der Wert, wie er kommt."""
    if wert is None:
        return None
    return wert / 100.0 if wert > 3 else wert


def pruefe_fundamentals(fund):
    """Vier Filter. Rueckgabe: (bestanden, Liste der Gruende).

    Fehlende Werte schliessen NICHT aus — dieselbe Linie wie in
    hole_fundamentals(): lieber nicht filtern als faelschlich
    aussortieren. Was fehlte, steht im Grund."""
    c = cfg()
    gruende, fehlt = [], []

    kap = fund.get("marktkapitalisierung")
    if kap is None:
        fehlt.append("Marktkapitalisierung")
    elif not mind_erreicht(kap / 1e9, c["min_marktkap_mrd"]):
        gruende.append(f"Marktkapitalisierung {kap/1e9:.1f} Mrd "
                       f"unter {c['min_marktkap_mrd']} Mrd")

    ums = fund.get("umsatzwachstum")
    if ums is None:
        fehlt.append("Umsatzwachstum")
    elif not mind_erreicht(ums, c["min_umsatzwachstum"]):
        gruende.append(f"Umsatzwachstum {ums*100:.1f} % unter "
                       f"{c['min_umsatzwachstum']*100:.0f} %")

    ver = verhaeltnis_schulden(fund.get("debt_to_equity"))
    if ver is None:
        fehlt.append("Verschuldungsgrad")
    elif not hoechstens(ver, c["max_debt_to_equity"]):
        gruende.append(f"Verschuldungsgrad {ver:.2f} über "
                       f"{c['max_debt_to_equity']}")

    if fehlt:
        gruende.append("ohne Angabe: " + ", ".join(fehlt))
    return not any(g for g in gruende if not g.startswith("ohne Angabe")), gruende


# ---------------------------------------------------------------------------
# Die Zone und der Ausloeser
# ---------------------------------------------------------------------------

def starke_zone(df, df_wochen=None):
    """Die beste Unterstuetzungszone UNTER oder AM aktuellen Kurs.

    GEGEBEN: level_score_schwelle 60. Der Level-Score kommt aus
    Kapitel 10 — dieselbe Maschinerie, dieselben Gewichte."""
    kurs = float(df["Close"].iloc[-1])
    for z in berechne_level_scores(df, df_wochen):
        if not mind_erreicht(z["score"], cfg()["level_score_schwelle"]):
            continue
        if z["min"] <= kurs * 1.02:          # Zone liegt nicht weit über dem Kurs
            return z
    return None


def ausloeser(df, zone, art=None):
    """Ist HEUTE der Tag? Rueckgabe: (ja, Beschreibung).

    ABGELEITET — siehe Kopf, Punkt 1."""
    art = art or cfg().get("trigger", "zone_schluss")
    schluss = float(df["Close"].iloc[-1])
    tief = float(df["Low"].iloc[-1])

    if art == "rueckeroberung":
        # Unterschritten und am Schluss ueber der Oberkante zurueck.
        if tief < zone["min"] and schluss > zone["max"]:
            return True, (f"Zone {zone['min']:.2f} bis {zone['max']:.2f} "
                          f"unterschritten und zurückerobert")
        return False, "keine Rückeroberung der Zone"

    # Vorgabe: Der Schluss liegt IN der Zone — die Unterstützung hat
    # auf Schlusskursbasis gehalten.
    if zone["min"] <= schluss <= zone["max"]:
        return True, (f"Schluss {schluss:.2f} in der Zone "
                      f"{zone['min']:.2f} bis {zone['max']:.2f}")
    if schluss < zone["min"]:
        return False, (f"Schluss {schluss:.2f} UNTER der Zone "
                       f"(ab {zone['min']:.2f}) — Unterstützung gebrochen")
    return False, f"Schluss {schluss:.2f} noch über der Zone"


def kursziel(zone):
    """ABGELEITET: Wyckoffs Zielprojektion wie in Kapitel 10."""
    hoehe = zone["max"] - zone["min"]
    return round(zone["max"] + hoehe * cfg()["kursziel_faktor"], 2)


# ---------------------------------------------------------------------------
# Der ganze Durchgang fuer EINE Aktie
# ---------------------------------------------------------------------------

def pruefe(df, fund, df_index, df_wochen=None, ticker="", firma=""):
    """Alle Stufen der Reihe nach. Rueckgabe: dict oder None.

    Die Reihenfolge ist nach Aufwand gewaehlt: erst der Index (einmal
    fuer alle), dann die Fundamentaldaten (schon geholt), zuletzt die
    Zonenrechnung (teuer)."""
    scharf, rueck = regime_scharf(df_index)
    if not scharf:
        return None

    ok, gruende = pruefe_fundamentals(fund or {})
    if not ok:
        return None

    if df is None or len(df) < CFG["shakeout"]["ma_lang"]:
        return None
    if df_wochen is None:
        df_wochen = wochenkurse_aus_tageskursen(df)

    zone = starke_zone(df, df_wochen)
    if zone is None:
        return None

    ja, beschreibung = ausloeser(df, zone)
    if not ja:
        return None

    einstieg = float(df["Close"].iloc[-1])
    from exit_regeln import berechne_initialen_stop
    stop, herkunft = berechne_initialen_stop(einstieg, zone["min"])

    return {
        "ticker": ticker, "firma": firma, "strategie": NAME,
        "kaufpunkt": round(einstieg, 2),
        "stop": stop, "stop_herkunft": herkunft,
        "ziel": kursziel(zone),
        "zone_min": round(zone["min"], 2), "zone_max": round(zone["max"], 2),
        "level_score": zone["score"],
        "index_rueckgang": round(rueck * 100, 1),
        "marktkap_mrd": round((fund or {}).get("marktkapitalisierung", 0) / 1e9, 1),
        "umsatzwachstum": (fund or {}).get("umsatzwachstum"),
        "verschuldungsgrad": verhaeltnis_schulden((fund or {}).get("debt_to_equity")),
        "beschreibung": beschreibung,
        "hinweis": "REKONSTRUIERT — Auslöser, Kaufpunkt und Ziel sind abgeleitet",
        "fundamental_hinweise": "; ".join(gruende) if gruende else "",
    }


def hole_kennzahlen(tickers):
    """Marktkapitalisierung, Umsatzwachstum und Verschuldungsgrad.

    Ergaenzt hole_fundamentals() im Scanner um die beiden Werte, die
    Kapitel 8 zusaetzlich braucht."""
    try:
        import yfinance as yf
    except ImportError:
        return {}
    out = {}
    for t in tickers:
        try:
            i = yf.Ticker(t).info
            out[t] = {"marktkapitalisierung": i.get("marketCap"),
                      "umsatzwachstum": i.get("revenueGrowth"),
                      "debt_to_equity": i.get("debtToEquity")}
        except Exception:
            out[t] = {}
    return out


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

def selbsttest() -> int:
    import numpy as np
    import pandas as pd
    fehler = []

    def pruefe_(name, bedingung, zusatz=""):
        print(f"  {'ok  ' if bedingung else 'FEHL'} {name}"
              + (f" — {zusatz}" if zusatz else ""))
        if not bedingung:
            fehler.append(name)

    print(f"{NAME} (Kapitel 8, Rekonstruktion), Selbsttest")

    def index(verlauf):
        return pd.DataFrame({"Close": verlauf})

    # --- Regime -----------------------------------------------------------
    steigend = index(list(np.linspace(100, 130, 300)))
    scharf, r = regime_scharf(steigend)
    pruefe_("Steigender Index: Strategie NICHT scharf", not scharf, f"{r*100:.1f} %")

    gefallen = index(list(np.linspace(100, 130, 250)) + list(np.linspace(130, 112, 50)))
    scharf, r = regime_scharf(gefallen)
    pruefe_("Index 14 % unter Hoch: scharf", scharf, f"{r*100:.1f} %")

    knapp = index(list(np.linspace(100, 130, 250)) + list(np.linspace(130, 121, 50)))
    scharf, r = regime_scharf(knapp)
    pruefe_("Index 6,9 % unter Hoch: nicht scharf", not scharf, f"{r*100:.1f} %")

    genau = index([100.0] * 250 + [90.0])
    scharf, r = regime_scharf(genau)
    pruefe_("Genau 10 % unter Hoch: scharf (Gleitkomma)", scharf, f"{r*100:.1f} %")

    pruefe_("Leerer Index sperrt die Strategie", not regime_scharf(None)[0])

    # --- Verschuldungsgrad ------------------------------------------------
    pruefe_("Yahoos 29.118 wird als 0.29 gelesen",
            abs(verhaeltnis_schulden(29.118) - 0.29118) < 1e-9)
    pruefe_("Ein echtes Verhältnis 0.45 bleibt 0.45",
            verhaeltnis_schulden(0.45) == 0.45)
    pruefe_("Fehlender Wert bleibt None", verhaeltnis_schulden(None) is None)

    # --- Fundamentalfilter ------------------------------------------------
    gut = {"marktkapitalisierung": 50e9, "umsatzwachstum": 0.22,
           "debt_to_equity": 29.1}
    ok, g = pruefe_fundamentals(gut)
    pruefe_("Grosse, wachsende, schuldenarme Aktie besteht", ok)

    ok, g = pruefe_fundamentals({**gut, "marktkapitalisierung": 8e9})
    pruefe_("8 Mrd Marktkapitalisierung fällt durch", not ok, g[0])

    ok, g = pruefe_fundamentals({**gut, "umsatzwachstum": 0.05})
    pruefe_("5 % Umsatzwachstum fällt durch", not ok, g[0])

    ok, g = pruefe_fundamentals({**gut, "debt_to_equity": 180.0})
    pruefe_("Verschuldungsgrad 1,8 fällt durch", not ok, g[0])

    ok, _ = pruefe_fundamentals({**gut, "marktkapitalisierung": 20e9})
    pruefe_("Genau 20 Mrd besteht (Gleitkomma)", ok)
    ok, _ = pruefe_fundamentals({**gut, "umsatzwachstum": 0.15})
    pruefe_("Genau 15 % Umsatzwachstum besteht (Gleitkomma)", ok)
    ok, _ = pruefe_fundamentals({**gut, "debt_to_equity": 50.0})
    pruefe_("Genau 0,50 Verschuldungsgrad besteht (Gleitkomma)", ok)

    ok, g = pruefe_fundamentals({"umsatzwachstum": 0.22})
    pruefe_("Fehlende Angaben schliessen nicht aus, werden aber genannt",
            ok and "ohne Angabe" in g[-1])

    # --- Ausloeser --------------------------------------------------------
    zone = {"min": 100.0, "max": 104.0, "score": 72.0}

    def tag(schluss, tief):
        return pd.DataFrame({"Close": [110.0, schluss], "Low": [108.0, tief]})

    ja, txt = ausloeser(tag(102.0, 99.5), zone)
    pruefe_("Schluss in der Zone löst aus", ja, txt)
    ja, txt = ausloeser(tag(97.0, 96.0), zone)
    pruefe_("Schluss unter der Zone löst NICHT aus", not ja, txt)
    ja, _ = ausloeser(tag(112.0, 109.0), zone)
    pruefe_("Schluss über der Zone löst nicht aus", not ja)
    ja, _ = ausloeser(tag(100.0, 99.0), zone)
    pruefe_("Schluss genau auf der Unterkante löst aus", ja)
    ja, _ = ausloeser(tag(106.0, 98.0), zone, art="rueckeroberung")
    pruefe_("Variante Rückeroberung: unterschritten und zurück", ja)
    ja, _ = ausloeser(tag(102.0, 99.0), zone, art="rueckeroberung")
    pruefe_("Variante Rückeroberung: Schluss in der Zone reicht nicht", not ja)

    # --- Stopp und Ziel ---------------------------------------------------
    from exit_regeln import berechne_initialen_stop
    stop, herkunft = berechne_initialen_stop(102.0, zone["min"])
    pruefe_("Stopp liegt auf der Unterkante der Zone",
            stop == 100.0 and herkunft == "struktur", f"{stop} ({herkunft})")

    stop, herkunft = berechne_initialen_stop(200.0, zone["min"])
    pruefe_("Weit entfernte Zone: der 10-%-Deckel greift",
            herkunft == "deckel" and stop == 180.0, f"{stop} ({herkunft})")

    pruefe_("Kursziel projiziert die Zonenhöhe nach oben",
            kursziel(zone) > zone["max"], f"{kursziel(zone)}")

    # --- Ganzer Durchgang -------------------------------------------------
    n = 300
    kurse = list(np.linspace(140, 101, n))
    df = pd.DataFrame({
        "Open": kurse, "High": [k * 1.01 for k in kurse],
        "Low": [k * 0.99 for k in kurse], "Close": kurse,
        "Volume": [1_000_000] * n,
    }, index=pd.date_range("2025-01-01", periods=n, freq="B"))

    treffer = pruefe(df, gut, steigend, ticker="TEST")
    pruefe_("Ohne Marktkorrektur kein Signal — auch bei guter Aktie",
            treffer is None)

    treffer = pruefe(df, {**gut, "umsatzwachstum": 0.01}, gefallen, ticker="TEST")
    pruefe_("Mit Korrektur, aber schwachem Umsatz: kein Signal",
            treffer is None)

    # Der ganze Weg MUSS einmal bis zur Zonenrechnung durchlaufen. Ohne
    # diese Prüfung bleibt alles dahinter ungetestet, weil die früheren
    # Fälle vorher aussteigen — so blieb ein falscher Konfigurations-
    # zugriff (CFG["ma_lang"] statt CFG["shakeout"]["ma_lang"]) stehen,
    # bis er am 06.08.2026 an echten Kursen aufflog.
    try:
        pruefe(df, gut, gefallen, ticker="TEST")
        durchgelaufen, grund = True, ""
    except Exception as e:
        durchgelaufen, grund = False, f"{type(e).__name__}: {e}"
    pruefe_("Korrektur und gute Aktie: läuft bis zur Zonenrechnung durch",
            durchgelaufen, grund)

    kurz = df.head(100)
    pruefe_("Zu wenig Kurshistorie ergibt kein Signal statt eines Fehlers",
            pruefe(kurz, gut, gefallen, ticker="TEST") is None)

    print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles bestanden.")
    return 1 if fehler else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=f"{NAME} — Kapitel 8 (Rekonstruktion)")
    ap.add_argument("tickers", nargs="*")
    ap.add_argument("--selbsttest", action="store_true")
    ap.add_argument("--regime", action="store_true")
    args = ap.parse_args()

    if args.selbsttest:
        return selbsttest()

    import yfinance as yf
    idx = yf.download(INDEX, period="2y", interval="1d", progress=False,
                      auto_adjust=False)
    if hasattr(idx.columns, "levels"):
        idx.columns = idx.columns.droplevel(1)
    scharf, r = regime_scharf(idx)
    print(f"{INDEX} steht {r*100:+.1f} % unter dem 52-Wochen-Hoch — "
          f"Kapitel 8 ist {'SCHARF' if scharf else 'nicht scharf'} "
          f"(Schwelle {cfg()['regime_index_drawdown']*100:.0f} %).")
    if args.regime or not args.tickers:
        return 0

    kennz = hole_kennzahlen(args.tickers)
    for t in args.tickers:
        daten = yf.download(t, period="2y", interval="1d", progress=False,
                            auto_adjust=False)
        if hasattr(daten.columns, "levels"):
            daten.columns = daten.columns.droplevel(1)
        ok, gruende = pruefe_fundamentals(kennz.get(t, {}))
        print(f"\n{t}: Fundamentaldaten {'bestanden' if ok else 'durchgefallen'}"
              + (f" — {'; '.join(gruende)}" if gruende else ""))
        if not scharf:
            continue
        treffer = pruefe(daten, kennz.get(t, {}), idx, ticker=t)
        print(f"  {treffer['beschreibung']}, Kauf {treffer['kaufpunkt']}, "
              f"Stopp {treffer['stop']}, Ziel {treffer['ziel']}"
              if treffer else "  kein Signal")
    return 0


if __name__ == "__main__":
    sys.exit(main())
