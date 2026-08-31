"""Marktampel: gruen, gelb oder rot — der Zustand des Gesamtmarkts.

WOZU (Gerhards Freigabe vom 31.08.2026, Baustein 4 des Einbau-Papiers,
Regelfrage G10 nach bestem Wissen entschieden): Leif Soreide steuert
seine Aggressivitaet ueber eine Marktampel, Oliver Kell handelt gross
nur, wenn S&P 500 und Nasdaq selbst im Aufwaertstrend sind. Bei uns gab
es bisher keine Marktzustands-Groesse ausser dem Red-to-Green-Gap.

WAS SIE TUT UND WAS NICHT: Die Ampel INFORMIERT nur. Sie unterdrueckt
keine Meldung und filtert nichts — erst wenn das Logbuch nach einigen
Wochen zeigt, wie die Trefferquote je Farbe aussieht, lohnt die
Diskussion ueber Konsequenzen. Deshalb schreibt trigger_logbuch die
Farbe in JEDE Zeile.

DIE DEFINITION (IBD-Konvention, zu Soreides CANSLIM-Wurzeln passend):
je Index der Schluss gegen die 21-Tage-Exponentiallinie und die
50-Tage-Durchschnittslinie.
  gruen: BEIDE Indizes schliessen ueber beiden Linien, die 21er liegt
         ueber der 50er, und die 50er steigt (hoeher als vor 10
         Handelstagen).
  rot:   mindestens ein Index schliesst UNTER seiner 50-Tage-Linie.
  gelb:  alles dazwischen.

Aufruf:
  python marktampel.py            berechnen, drucken, marktampel.json schreiben
"""

import json
import sys
from datetime import datetime

DATEI = "marktampel.json"
INDIZES = {"^GSPC": "S&P 500", "^IXIC": "Nasdaq"}


def _index_lage(df):
    """Schluss, Linienlage und Richtung fuer EINEN Index."""
    schluss = df["Close"].dropna()
    if len(schluss) < 65:
        return None
    ema21 = float(schluss.ewm(span=21, adjust=False).mean().iloc[-1])
    sma50_reihe = schluss.rolling(50).mean()
    sma50 = float(sma50_reihe.iloc[-1])
    sma50_vor10 = float(sma50_reihe.iloc[-11])
    letzter = float(schluss.iloc[-1])
    return {
        "schluss": round(letzter, 2),
        "ema21": round(ema21, 2),
        "sma50": round(sma50, 2),
        "ueber_ema21": letzter > ema21,
        "ueber_sma50": letzter > sma50,
        "ema21_ueber_sma50": ema21 > sma50,
        "sma50_steigt": sma50 > sma50_vor10,
        "handelstag": schluss.index[-1].strftime("%Y-%m-%d"),
    }


def berechnen():
    """Beide Indizes laden und die Farbe bestimmen. None bei Datenmangel."""
    import yfinance as yf
    lagen = {}
    for symbol, name in INDIZES.items():
        try:
            df = yf.Ticker(symbol).history(period="6mo", auto_adjust=False)
        except Exception as e:
            print(f"  Marktampel: {name} nicht ladbar ({type(e).__name__})")
            return None
        lage = _index_lage(df)
        if lage is None:
            print(f"  Marktampel: {name} mit zu wenig Historie")
            return None
        lagen[name] = lage

    if any(not l["ueber_sma50"] for l in lagen.values()):
        farbe = "rot"
    elif all(l["ueber_ema21"] and l["ema21_ueber_sma50"]
             and l["sma50_steigt"] for l in lagen.values()):
        farbe = "gruen"
    else:
        farbe = "gelb"
    return {
        "farbe": farbe,
        "handelstag": max(l["handelstag"] for l in lagen.values()),
        "gebaut_am": datetime.now().isoformat(timespec="seconds"),
        "indizes": lagen,
    }


def aktualisieren():
    """Berechnen und ablegen; bei Datenmangel bleibt der alte Stand
    liegen (eine veraltete Farbe ist im Logbuch als solche erkennbar,
    ein geloeschter Stand waere gar keine Information)."""
    d = berechnen()
    if d is None:
        return None
    with open(DATEI, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    return d


def lese_farbe():
    """Die abgelegte Farbe samt Handelstag, oder (None, None)."""
    try:
        with open(DATEI, encoding="utf-8-sig") as f:
            d = json.load(f)
        return d.get("farbe"), d.get("handelstag")
    except (OSError, ValueError):
        return None, None


def main():
    d = aktualisieren()
    if d is None:
        print("Marktampel: keine Daten, nichts geschrieben.")
        return 1
    print(f"Marktampel: {d['farbe'].upper()} (Handelstag {d['handelstag']})")
    for name, l in d["indizes"].items():
        print(f"  {name}: Schluss {l['schluss']}, EMA21 {l['ema21']} "
              f"({'darüber' if l['ueber_ema21'] else 'darunter'}), "
              f"SMA50 {l['sma50']} "
              f"({'darüber' if l['ueber_sma50'] else 'darunter'}, "
              f"{'steigend' if l['sma50_steigt'] else 'nicht steigend'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
