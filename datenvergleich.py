#!/usr/bin/env python3
"""Stellt die Kurs- und VOLUMENDATEN von Yahoo und FMP gegenueber.

Mathias' Auftrag vom 27.07.2026: nachweisen, ob beide Quellen dasselbe
liefern — bevor wir die Volumenbestaetigung auf eine zweite Quelle
stuetzen. Verglichen wird nicht irgendwas, sondern genau das, woran das
Regelwerk haengt:

    letzter Schlusskurs, letztes Tagesvolumen,
    Ø10 und Ø20 des Volumens (jeweils OHNE den letzten Tag, so wie
    fetch_quotes_yahoo() im Waechter rechnet).

Der Schluessel kommt aus der Umgebung (FMP_API_KEY) und wird nie
ausgegeben. Aufruf:

    python datenvergleich.py [TICKER ...]
"""

import os
import sys
from datetime import date, timedelta

import pandas as pd
import requests

STANDARD = ["AAPL", "LLY", "VCYT", "GBCI", "LEVI", "CDNA", "AMN", "SPFI"]


def fmp_historie(ticker: str, schluessel: str, tage: int = 90):
    """Tageskurse von FMP. Probiert erst die neue, dann die alte Adresse."""
    von = (date.today() - timedelta(days=tage)).isoformat()
    bis = date.today().isoformat()
    versuche = [
        ("stable", "https://financialmodelingprep.com/stable/historical-price-eod/full",
         {"symbol": ticker, "from": von, "to": bis, "apikey": schluessel}),
        ("v3", f"https://financialmodelingprep.com/api/v3/historical-price-full/{ticker}",
         {"from": von, "to": bis, "apikey": schluessel}),
    ]
    for name, url, params in versuche:
        try:
            r = requests.get(url, params=params, timeout=30)
        except Exception as e:
            print(f"    FMP ({name}) Netzfehler: {str(e)[:70]}")
            continue
        if r.status_code >= 400:
            print(f"    FMP ({name}) HTTP {r.status_code}: {r.text[:120]}")
            continue
        try:
            daten = r.json()
        except Exception:
            print(f"    FMP ({name}) keine lesbare Antwort: {r.text[:120]}")
            continue
        if isinstance(daten, dict) and "Error Message" in daten:
            print(f"    FMP ({name}) abgelehnt: {str(daten['Error Message'])[:120]}")
            continue
        zeilen = daten.get("historical", daten) if isinstance(daten, dict) else daten
        if not zeilen:
            print(f"    FMP ({name}) lieferte keine Zeilen.")
            continue
        df = pd.DataFrame(zeilen)
        if "date" not in df.columns or "volume" not in df.columns:
            print(f"    FMP ({name}) unerwartete Felder: {list(df.columns)[:8]}")
            continue
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df = df.sort_values("date").set_index("date")
        print(f"    FMP-Adresse '{name}' liefert {len(df)} Tage.")
        return df
    return None


def kennzahlen(schluss: pd.Series, volumen: pd.Series) -> dict:
    """Die vier Zahlen, an denen das Regelwerk haengt."""
    ohne_letzten = volumen.iloc[:-1]
    return {
        "schluss": float(schluss.iloc[-1]),
        "volumen": float(volumen.iloc[-1]),
        "vol10": float(ohne_letzten.tail(10).mean()),
        "vol20": float(ohne_letzten.tail(20).mean()),
    }


def abweichung(a: float, b: float) -> float:
    return abs(a - b) / a * 100 if a else 0.0


def main():
    schluessel = os.environ.get("FMP_API_KEY", "").strip()
    if not schluessel:
        sys.exit("Kein FMP_API_KEY gesetzt.")
    tickers = [t.upper() for t in sys.argv[1:]] or STANDARD

    import yfinance as yf
    print(f"Yahoo-Sammelabruf für {len(tickers)} Aktien …")
    roh = yf.download(" ".join(tickers), period="6mo", interval="1d",
                      group_by="ticker", progress=False,
                      auto_adjust=False, threads=True)

    schlimmste_vol, schlimmste_kurs = 0.0, 0.0
    geprueft = 0
    for t in tickers:
        print(f"\n=== {t} ===")
        try:
            y = roh[t] if len(tickers) > 1 else roh
            y = y.dropna(subset=["Close", "Volume"])
            y.index = [d.date() for d in y.index]
        except Exception as e:
            print(f"    Yahoo lieferte nichts ({str(e)[:60]}).")
            continue
        f = fmp_historie(t, schluessel)
        if f is None or y.empty:
            continue

        # Nur Tage vergleichen, die BEIDE Quellen kennen — sonst
        # vergleicht man Feiertage und unfertige Tage gegeneinander.
        gemeinsam = sorted(set(y.index) & set(f.index))
        if len(gemeinsam) < 21:
            print(f"    Nur {len(gemeinsam)} gemeinsame Tage — zu wenig für Ø20.")
            continue
        gemeinsam = gemeinsam[-40:]
        yk = kennzahlen(y.loc[gemeinsam, "Close"], y.loc[gemeinsam, "Volume"])
        fk = kennzahlen(f.loc[gemeinsam, "close"], f.loc[gemeinsam, "volume"])
        print(f"    {len(gemeinsam)} gemeinsame Handelstage, letzter: {gemeinsam[-1]}")

        for feld, beschriftung in (("schluss", "Schlusskurs"), ("volumen", "Tagesvolumen"),
                                   ("vol10", "Ø10 Volumen"), ("vol20", "Ø20 Volumen")):
            ab = abweichung(yk[feld], fk[feld])
            marke = "  <-- ABWEICHUNG" if ab > 1.0 else ""
            print(f"    {beschriftung:14s} Yahoo {yk[feld]:>15,.2f}   "
                  f"FMP {fk[feld]:>15,.2f}   {ab:5.2f} %{marke}")
            if feld == "schluss":
                schlimmste_kurs = max(schlimmste_kurs, ab)
            else:
                schlimmste_vol = max(schlimmste_vol, ab)

        # Tag-für-Tag: Wo genau laufen die Volumina auseinander?
        streit = []
        for d in gemeinsam[-12:]:
            yv, fv = float(y.loc[d, "Volume"]), float(f.loc[d, "volume"])
            ab = abweichung(yv, fv)
            if ab > 1.0:
                streit.append(f"{d}: Yahoo {yv:,.0f} gegen FMP {fv:,.0f} ({ab:.1f} %)")
        if streit:
            print("    Abweichende Einzeltage (letzte 12):")
            for z in streit:
                print(f"      {z}")
        else:
            print("    Einzeltage der letzten 12: durchgehend deckungsgleich.")
        geprueft += 1

    print(f"\n=== Gesamt: {geprueft} Aktien geprüft ===")
    print(f"größte Kursabweichung:   {schlimmste_kurs:.2f} %")
    print(f"größte Volumenabweichung: {schlimmste_vol:.2f} %")


if __name__ == "__main__":
    main()
