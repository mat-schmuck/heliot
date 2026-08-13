#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TERMINE-VERGLEICH — wie genau ist Finnhub bei Zahlen-Terminen?
===============================================================
Mathias' Auftrag vom 13.08.2026: Finnhub in der Cloud messen. Dort liegt
der Schluessel als Secret; lokal gibt es ihn nicht.

VORGESCHICHTE, damit niemand den alten Irrtum wiederholt
    Ich hatte Finnhub fuer Termine verworfen — aber NICHT gemessen,
    sondern aus einem Befund vom 27.07.2026 abgeleitet. Der betraf
    Finnhubs KURSDATEN: Tageskerzen sind dort ausdruecklich
    kostenpflichtig ("Premium Access Required"). Ueber den
    Termin-Kalender sagt das nichts. Genau diese Verwechslung soll diese
    Messung aufloesen.

WAS GEMESSEN WIRD
    1. ABDECKUNG: Wie viele Aktien der Wochenliste kennt jede Quelle?
    2. UEBEREINSTIMMUNG: Wo sind sich je zwei Quellen einig, wo nicht?
    3. WAHRHEIT: Drei Faelle, deren richtiges Datum an Pressemeldungen
       der Unternehmen geprueft ist (13.08.2026):
         AYA   13.08. nach Boersenschluss
         DY    26.08. vor Boersenoeffnung
         ASND  13.08.
       Das ist der einzige Teil, der wirklich RECHT und UNRECHT misst.
       Alles andere misst nur Einigkeit, und einig sein heisst nicht
       richtig sein.

Aufruf (braucht FINNHUB_API_KEY in der Umgebung):
    python termine_vergleich.py <ausgabedatei>
"""

import json
import os
import sys
import urllib.request
from datetime import date, timedelta

# Die drei Faelle mit belegter Wahrheit. Quelle jeweils die Meldung des
# Unternehmens selbst bzw. dessen Terminankuendigung.
WAHRHEIT = {
    "AYA":  ("2026-08-13", "nachboerslich",
             "Q2-Zahlen 13.08. nach Schluss, Telefonkonferenz erst 14.08."),
    "DY":   ("2026-08-26", "vorboerslich",
             "Dycom berichtet 26.08. vor Eroeffnung"),
    "ASND": ("2026-08-13", "vorboerslich",
             "Ascendis hat am 13.08. berichtet, angekuendigt am 06.08."),
}

LAGE_FINNHUB = {"bmo": "vorboerslich", "amc": "nachboerslich",
                "dmh": "im_handel", "": "unbekannt", None: "unbekannt"}


def hole_finnhub(von, bis, token):
    """Finnhubs Termin-Kalender fuer eine Zeitspanne.

    Rueckgabe: (daten, fehlertext). Bei fehlendem Zugriff sagt der
    Fehlertext, WORAN es lag — genau darum geht es bei dieser Messung."""
    url = (f"https://finnhub.io/api/v1/calendar/earnings?from={von}"
           f"&to={bis}&token={token}")
    bitte = urllib.request.Request(url, headers={"User-Agent": "heliot"})
    try:
        with urllib.request.urlopen(bitte, timeout=40) as a:
            roh = json.loads(a.read().decode("utf-8"))
    except Exception as e:
        code = getattr(e, "code", None)
        leib = ""
        if hasattr(e, "read"):
            try:
                leib = e.read()[:200].decode("utf-8", "replace")
            except Exception:
                pass
        return {}, f"HTTP {code}: {leib or type(e).__name__}"
    out = {}
    for r in roh.get("earningsCalendar", []):
        sym = (r.get("symbol") or "").upper()
        if not sym or sym in out:
            continue
        out[sym] = {"datum": r.get("date"),
                    "lage": LAGE_FINNHUB.get(r.get("hour"), "unbekannt")}
    return out, None


def hole_nasdaq(von, bis):
    lage_aus = {"time-after-hours": "nachboerslich",
                "time-pre-market": "vorboerslich",
                "time-not-supplied": "unbekannt"}
    out = {}
    tag = von
    while tag <= bis:
        if tag.weekday() < 5:
            url = ("https://api.nasdaq.com/api/calendar/earnings?date="
                   + tag.isoformat())
            bitte = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Accept": "application/json"})
            try:
                with urllib.request.urlopen(bitte, timeout=30) as a:
                    d = json.loads(a.read().decode("utf-8"))
                for r in ((d.get("data") or {}).get("rows") or []):
                    sym = (r.get("symbol") or "").upper()
                    if sym and sym not in out:
                        out[sym] = {"datum": tag.isoformat(),
                                    "lage": lage_aus.get(r.get("time"),
                                                         "unbekannt")}
            except Exception:
                pass
        tag += timedelta(days=1)
    return out


def hole_yahoo(tickers, von, bis):
    import yfinance as yf
    out = {}
    for t in tickers:
        try:
            df = yf.Ticker(t).get_earnings_dates(limit=12)
        except Exception:
            continue
        if df is None or len(df) == 0:
            continue
        for stempel in df.index:
            try:
                d = stempel.date()
            except Exception:
                continue
            if von <= d <= bis:
                lage = ("vorboerslich" if stempel.hour * 60 + stempel.minute
                        < 9 * 60 + 30 else
                        "nachboerslich" if stempel.hour >= 16 else "im_handel")
                if t not in out or d < date.fromisoformat(out[t]["datum"]):
                    out[t] = {"datum": d.isoformat(), "lage": lage}
    return out


def main() -> int:
    ziel = sys.argv[1] if len(sys.argv) > 1 else "termine_vergleich.txt"
    token = (os.environ.get("FINNHUB_API_KEY") or "").strip()
    zeilen = []

    def sag(t=""):
        print(t)
        zeilen.append(t)

    import pandas as pd
    liste = sorted(set(pd.read_csv("finviz_3.csv")["Ticker"]
                       .astype(str).str.upper()))
    von = date(2026, 8, 10)
    bis = date(2026, 8, 31)
    sag(f"TERMINE-VERGLEICH  {von} bis {bis}  ueber {len(liste)} Aktien")
    sag("=" * 70)

    if not token:
        sag("FINNHUB_API_KEY fehlt — Finnhub kann nicht gemessen werden.")
        finnhub, fehler = {}, "kein Schluessel"
    else:
        sag(f"Finnhub-Schluessel vorhanden ({len(token)} Zeichen, Wert wird "
            f"nicht ausgegeben).")
        finnhub, fehler = hole_finnhub(von.isoformat(), bis.isoformat(), token)
        if fehler:
            sag(f"FINNHUB NICHT NUTZBAR: {fehler}")
            sag("  Das ist selbst das Ergebnis: Der Kalender liegt dann "
                "nicht im Gratistarif.")
        else:
            sag(f"Finnhub: {len(finnhub)} Firmen im Zeitraum (alle Boersen).")

    nasdaq = hole_nasdaq(von, bis)
    sag(f"Nasdaq : {len(nasdaq)} Firmen im Zeitraum.")
    yahoo = hole_yahoo(liste, von, bis)
    sag(f"Yahoo  : {len(yahoo)} Aktien UNSERER Liste im Zeitraum.")
    sag()

    f_liste = {k: v for k, v in finnhub.items() if k in liste}
    n_liste = {k: v for k, v in nasdaq.items() if k in liste}
    sag("ABDECKUNG in unserer Wochenliste:")
    sag(f"  Yahoo   {len(yahoo):3d}")
    sag(f"  Nasdaq  {len(n_liste):3d}")
    sag(f"  Finnhub {len(f_liste):3d}")
    alle = set(yahoo) | set(n_liste) | set(f_liste)
    sag(f"  zusammen {len(alle)} von {len(liste)}")
    nur_f = sorted(set(f_liste) - set(yahoo) - set(n_liste))
    sag(f"  nur Finnhub kennt: {len(nur_f)}"
        + (f" ({', '.join(nur_f[:10])})" if nur_f else ""))
    sag()

    sag("DIE DREI FAELLE MIT BELEGTER WAHRHEIT:")
    punkte = {"yahoo": 0, "nasdaq": 0, "finnhub": 0}
    moeglich = 0
    for sym, (soll_d, soll_l, warum) in WAHRHEIT.items():
        sag(f"  {sym}: richtig ist {soll_d} ({soll_l}) — {warum}")
        moeglich += 1
        for name, quelle in (("yahoo", yahoo), ("nasdaq", n_liste),
                             ("finnhub", f_liste)):
            e = quelle.get(sym)
            if not e:
                sag(f"      {name:8s} kennt den Termin nicht")
                continue
            datum_ok = e["datum"] == soll_d
            lage_ok = e["lage"] == soll_l or e["lage"] == "unbekannt"
            if datum_ok:
                punkte[name] += 1
            sag(f"      {name:8s} {e['datum']} ({e['lage']})  "
                f"{'DATUM RICHTIG' if datum_ok else 'DATUM FALSCH'}"
                + ("" if lage_ok else ", Tageszeit falsch"))
    sag()
    sag(f"Treffer bei den {moeglich} belegten Faellen:")
    for name, p in sorted(punkte.items(), key=lambda x: -x[1]):
        sag(f"  {name:8s} {p} von {moeglich}")
    sag()

    sag("WO SICH FINNHUB UND YAHOO UNEINIG SIND (nur unsere Liste):")
    uneinig = 0
    for sym in sorted(set(f_liste) & set(yahoo)):
        if f_liste[sym]["datum"] != yahoo[sym]["datum"]:
            uneinig += 1
            sag(f"  {sym:6s} Finnhub {f_liste[sym]['datum']} ({f_liste[sym]['lage']})"
                f" / Yahoo {yahoo[sym]['datum']} ({yahoo[sym]['lage']})")
    einig = len(set(f_liste) & set(yahoo)) - uneinig
    sag(f"  einig {einig}, uneinig {uneinig}")
    sag()

    # -----------------------------------------------------------------
    # IST DAS EIN ZEITZONEN-VERSATZ? (Mathias' Frage vom 13.08.2026)
    # -----------------------------------------------------------------
    # Der Verdacht ist berechtigt: Bei DKS und FIVE lag Finnhub BEIDE
    # MALE genau einen Tag zu frueh, und "genau ein Tag" ist die
    # Handschrift einer Zeitzonen-Umrechnung.
    #
    # Unterscheiden laesst sich das an der FORM der Abweichung, nicht an
    # zwei Einzelfaellen:
    #   Ein Zeitzonen-Fehler ist SYSTEMATISCH. Er trifft jeden Termin,
    #   dessen Uhrzeit in das verschobene Fenster faellt — also eine
    #   ganze KLASSE (etwa alle nachboerslichen), und zwar immer in
    #   dieselbe Richtung.
    #   Schlechte Daten sind ZUFAELLIG verstreut: mal ein Tag, mal eine
    #   Woche, mal in die eine, mal in die andere Richtung.
    #
    # Gemessen wird deshalb ueber den GANZEN Markt (rund 1500 Firmen bei
    # beiden Quellen), nicht nur ueber unsere 238 — nur dort ist die
    # Verteilung aussagekraeftig. Dass Nasdaq selbst Fehler hat (AYA,
    # DY), stoert hier NICHT: Gefragt ist nicht, wer recht hat, sondern
    # ob die Abweichungen eine Schlagseite haben.
    sag("ZEITZONEN-PRUEFUNG: Finnhub gegen Nasdaq ueber den GANZEN Markt")
    gemeinsam = sorted(set(finnhub) & set(nasdaq))
    sag(f"  {len(gemeinsam)} Firmen kennen beide.")
    from collections import Counter
    verteilung = Counter()
    nach_lage = {}
    for sym in gemeinsam:
        try:
            d = (date.fromisoformat(finnhub[sym]["datum"])
                 - date.fromisoformat(nasdaq[sym]["datum"])).days
        except Exception:
            continue
        schub = d if -3 <= d <= 3 else (4 if d > 3 else -4)
        verteilung[schub] += 1
        lage = finnhub[sym]["lage"]
        nach_lage.setdefault(lage, Counter())[schub] += 1
    gesamt = sum(verteilung.values()) or 1
    namen = {-4: "mehr als 3 Tage frueher", -1: "1 Tag frueher",
             0: "gleicher Tag", 1: "1 Tag spaeter",
             4: "mehr als 3 Tage spaeter"}
    for schub in sorted(verteilung):
        sag(f"    {namen.get(schub, str(schub) + ' Tage'):24s} "
            f"{verteilung[schub]:5d}  ({verteilung[schub] / gesamt * 100:5.1f} %)")
    sag()
    sag("  Aufgeschluesselt nach Finnhubs eigener Tageszeit-Angabe:")
    for lage in sorted(nach_lage):
        c = nach_lage[lage]
        n = sum(c.values()) or 1
        sag(f"    {lage:14s} n={n:5d}  gleicher Tag {c[0] / n * 100:5.1f} %, "
            f"1 frueher {c[-1] / n * 100:5.1f} %, "
            f"1 spaeter {c[1] / n * 100:5.1f} %")
    sag()
    einig_anteil = verteilung[0] / gesamt * 100
    schief = (verteilung[-1] + verteilung[1]) / gesamt * 100
    sag(f"  BEFUND: {einig_anteil:.1f} % gleicher Tag, {schief:.1f} % um genau "
        f"einen Tag daneben.")
    sag("  Ein Zeitzonen-Versatz muesste eine ganze Klasse geschlossen "
        "verschieben.")
    sag("  Verstreute Einzelabweichungen sind schlicht falsche Daten.")
    sag()
    sag("  Die beiden Streitfaelle im Rohzustand (Datum und Finnhubs "
        "'hour'-Feld):")
    for sym in ("DKS", "FIVE"):
        f, n, y = finnhub.get(sym), nasdaq.get(sym), yahoo.get(sym)
        sag(f"    {sym}: Finnhub {f} | Nasdaq {n} | Yahoo {y}")

    with open(ziel, "w", encoding="utf-8") as f:
        f.write("\n".join(zeilen) + "\n")
    print(f"\nGeschrieben nach {ziel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
