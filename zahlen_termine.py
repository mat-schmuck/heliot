#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZAHLEN-TERMINE — wer heute Abend berichtet, bekommt einen Vermerk
==================================================================
Gerhards Auftrag vom 12.08.2026: "Baue ein Tool ein, damit bei einem
Unternehmen, das am gleichen Abend Zahlen bringt, das eindeutig vermerkt
wird."

WARUM DAS ZAEHLT, und zwar mit einem Beleg von gestern
    Sea hat am 11.08.2026 um 08:00 New Yorker Zeit Zahlen gebracht, also
    vor der Eroeffnung. Die Aktie eroeffnete daraufhin bei 127,87 und
    damit 10,3 % ueber ihrem Kaufpunkt von 115,91 — genau der Fall, der
    zur Meldung "Kaufpunkt uebersprungen" gefuehrt hat. Wer den Termin
    gekannt haette, haette den Ausbruch anders eingeordnet.

    Umgekehrt gilt dasselbe: Ein sauberer Ausbruch am Nachmittag ist
    etwas anderes, wenn dieselbe Firma zwei Stunden spaeter berichtet.
    Ueber Nacht entscheidet dann nicht das Muster, sondern die Zahl.

WAS GEMELDET WIRD
    Drei Faelle, alle in New Yorker Zeit gerechnet:
      * Zahlen HEUTE nach Boersenschluss  — die Position traegt das
        Ergebnis ueber Nacht.
      * Zahlen MORGEN vor Eroeffnung      — dasselbe Risiko, nur anders
        herum aufgeschrieben.
      * Zahlen HEUTE vor Eroeffnung       — schon geschehen; erklaert
        eine Luecke, statt vor einer zu warnen.

WOHER DIE DATEN KOMMEN — ZWEI QUELLEN, und das ist noetig
    1. yfinance, Ticker.get_earnings_dates().
    2. Der oeffentliche Kalender der Nasdaq
       (api.nasdaq.com/api/calendar/earnings?date=...). Ohne Schluessel,
       ohne Anmeldung, alle US-Boersen; das Feld 'time' liefert genau
       die Einordnung, die hier gebraucht wird.

    WARUM ZWEI (gemessen am 13.08.2026 an der echten Wochenliste ueber
    fuenf Handelstage): Von den Terminen, die beide kannten, stimmten
    acht ueberein und ZWEI nicht. Und zwei Aktien, die an diesem Tag
    berichteten, kannte Yahoo GAR NICHT: fuer ASND und IDR hatte es
    ueberhaupt keinen kommenden Termin.

    WER RECHT HATTE, an echten Nachrichten nachgeprueft:
      AYA  Yahoo 13.08. nach Schluss / Nasdaq 14.08. vorboerslich.
           RICHTIG: 13.08. nach Schluss. Nasdaq hatte offenbar den
           Termin der Telefonkonferenz am 14.08. genommen.
      DY   Yahoo 26.08. vorboerslich / Nasdaq 19.08.
           RICHTIG: 26.08. vorboerslich. Nasdaq lag eine Woche zu frueh.
      ASND Nur Nasdaq. RICHTIG: hat am 13.08. berichtet.

    Daraus die Arbeitsteilung: NASDAQ BRINGT ABDECKUNG, YAHOO BRINGT
    GENAUIGKEIT. Bei Uneinigkeit gewinnt deshalb Yahoo — aber die
    Uneinigkeit steht im Vermerk, denn zwei Faelle sind eine duenne
    Grundlage.

    Eine Quelle allein haette also an genau dem Tag geschwiegen, an dem
    gewarnt werden sollte. Deshalb gilt: Meldet EINE der beiden einen
    Termin, wird vermerkt. Sind sie uneinig, gewinnt Yahoo und die
    Uneinigkeit steht im Vermerk — ein Hinweis, dem man ansieht, wie
    sicher er ist, ist mehr wert als einer, der Sicherheit vortaeuscht.

    UND WARUM NICHT FINNHUB ALS DRITTE? Weil es gemessen ist, nicht
    vermutet (13.08.2026, Lauf 31724479175 in der Cloud, wo der
    Schluessel liegt; Werkzeug termine_vergleich.py, Modus
    'terminvergleich' in alarme.yml). Der Kalender IST im Gratistarif
    zugaenglich — die alte Ablehnung stuetzte sich auf einen Befund zu
    Finnhubs KURSDATEN und war insofern unbegruendet. Nur nuetzt er
    nichts:

      ABDECKUNG unserer 238 Aktien im Zeitraum 10. bis 31.08.:
        Nasdaq 37, Yahoo 35, Finnhub 25. Und entscheidend: Finnhub
        kannte KEINE EINZIGE Aktie, die die beiden anderen nicht schon
        hatten (nur-Finnhub: 0). Als dritte Quelle braechte es also
        keinen einzigen zusaetzlichen Termin.

      GENAUIGKEIT an den Faellen mit belegter Wahrheit:
        Yahoo 2 von 3, Nasdaq 1 von 3, Finnhub 1 von 3 — AYA und ASND
        kannte es gar nicht, und beide haben an diesem Tag berichtet.

      WO ES ABWEICHT, LIEGT ES FALSCH: Von 22 Terminen, die Finnhub und
        Yahoo beide kannten, waren sie bei 20 einig und bei 2 uneinig —
        DKS (Finnhub 24.08., Yahoo 25.08.) und FIVE (Finnhub 25.08.,
        Yahoo 26.08.). Beide Male ist Finnhub genau EINEN TAG ZU FRUEH,
        und beide Male hat Yahoo recht: DICK'S Sporting Goods hat am
        04.08.2026 selbst den 25.08. vor Boersenoeffnung angekuendigt
        (bei FIVE deckt sich Yahoo mit dem Termin, den auch Nasdaq
        nennt; die Firma selbst hat ihn noch nicht angekuendigt).
        Ein Tag zu frueh ist genau der Fehler, der hier weh tut — die
        Warnung kaeme am falschen Abend.

    FOLGE: Es bleibt bei zwei Quellen. Finnhub wird nicht eingebaut,
    weil es weniger kennt und beim Abweichen falsch liegt. Das ist
    jetzt gemessen; wer es wieder aufgreifen will, nimmt
    termine_vergleich.py und misst neu.

    Zum Ausgangsstand: yfinance, Ticker.get_earnings_dates(). Der Zeitstempel traegt die
    Uhrzeit mit, und daran haengt die ganze Einordnung: 16:00 heisst
    nach Schluss, 07:00 oder 08:00 heisst davor. Gemessen am 12.08.2026
    an vier Aktien: NVDA 26.08. 16:00, FSLY 04.11. 15:00, SE 10.11.
    07:00, AAOI 05.11. 15:00.

    ACHTUNG BEI DER VERLAESSLICHKEIT: Termine verschieben sich, und
    Yahoo weiss das nicht immer sofort. Ein FEHLENDER Vermerk ist
    deshalb KEIN Beweis, dass keine Zahlen kommen. Der Vermerk ist ein
    Hinweis, keine Garantie — und genau so ist er formuliert.

GEBAUT WIRD EINMAL AM TAG im Nachtlauf, wie die Volumenkurven. Der
Waechter liest nur.

Aufruf:
    python zahlen_termine.py --bauen        Termine holen und ablegen
    python zahlen_termine.py --zeigen       was abgelegt ist
    python zahlen_termine.py --selbsttest
"""

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta

DATEI = "zahlen_termine.json"

# Vor 09:30 New Yorker Zeit gilt als vorboerslich, ab 16:00 als
# nachboerslich. Dazwischen berichtet praktisch niemand; kommt es doch
# vor, wird es als 'waehrend des Handels' gefuehrt statt geraten.
OEFFNUNG_MIN = 9 * 60 + 30
SCHLUSS_MIN = 16 * 60

_termine = None


def _lage(stunde, minute):
    """vorboerslich, nachboerslich oder waehrend des Handels."""
    m = stunde * 60 + minute
    if m < OEFFNUNG_MIN:
        return "vorboerslich"
    if m >= SCHLUSS_MIN:
        return "nachboerslich"
    return "im_handel"


def hole_termine(tickers, leise=False):
    """Naechster Zahlen-Termin je Aktie. Braucht Netzwerk.

    Rueckgabe: {ticker: {"datum": "YYYY-MM-DD", "lage": ..., "uhrzeit": "HH:MM"}}
    Aktien ohne Termin fehlen einfach — das ist kein Fehler, viele
    Firmen haben schlicht keinen angekuendigten Termin in Reichweite."""
    import yfinance as yf

    heute = date.today()
    out, ohne = {}, []
    for i, t in enumerate(sorted({x.upper() for x in tickers if x}), 1):
        try:
            tk = yf.Ticker(t)
            df = tk.get_earnings_dates(limit=8)
        except Exception:
            ohne.append(t)
            continue
        if df is None or len(df) == 0:
            ohne.append(t)
            continue
        # Der naechste Termin ab heute. Die Reihe ist absteigend
        # sortiert, deshalb wird sie ganz durchgesehen.
        kandidat = None
        for stempel in df.index:
            try:
                d = stempel.date()
            except Exception:
                continue
            if d >= heute and (kandidat is None or d < kandidat.date()):
                kandidat = stempel
        if kandidat is None:
            ohne.append(t)
            continue
        out[t] = {"datum": kandidat.date().isoformat(),
                  "uhrzeit": f"{kandidat.hour:02d}:{kandidat.minute:02d}",
                  "lage": _lage(kandidat.hour, kandidat.minute)}
        if not leise and i % 50 == 0:
            print(f"    {i} Aktien abgefragt …")
    return out, ohne


def hole_nasdaq(tage=10, leise=False):
    """Der oeffentliche Kalender der Nasdaq. Kein Schluessel noetig.

    Gefragt wird Tag fuer Tag, Wochenenden ausgelassen. Faellt ein Tag
    aus, fehlt er einfach — diese Quelle ist eine Ergaenzung, kein
    Ersatz, und darf den Lauf nie aufhalten."""
    import urllib.request

    lage_aus = {"time-after-hours": "nachboerslich",
                "time-pre-market": "vorboerslich",
                "time-not-supplied": "unbekannt"}
    out = {}
    heute = date.today()
    geprueft = 0
    for i in range(0, tage + 6):
        if geprueft >= tage:
            break
        tag = heute + timedelta(days=i)
        if tag.weekday() >= 5:
            continue
        geprueft += 1
        url = ("https://api.nasdaq.com/api/calendar/earnings?date="
               + tag.isoformat())
        bitte = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "application/json"})
        try:
            with urllib.request.urlopen(bitte, timeout=30) as a:
                d = json.loads(a.read().decode("utf-8"))
        except Exception as e:
            if not leise:
                print(f"    Nasdaq {tag}: nicht erreichbar ({type(e).__name__})")
            continue
        for r in ((d.get("data") or {}).get("rows") or []):
            sym = (r.get("symbol") or "").upper()
            if not sym or sym in out:       # der frueheste Termin gewinnt
                continue
            out[sym] = {"datum": tag.isoformat(), "uhrzeit": "",
                        "lage": lage_aus.get(r.get("time"), "unbekannt")}
    return out


def _zusammenfuehren(yahoo, nasdaq, tickers):
    """Beide Quellen zu einem Eintrag je Aktie.

    REGEL, an echten Nachrichten geprueft (13.08.2026):

      * Meldet nur EINE der beiden einen Termin, wird er uebernommen.
        Das ist der Fall, in dem die zweite Quelle ihr Geld verdient:
        ASND hat am 13.08.2026 berichtet, und Yahoo kannte den Termin
        ueberhaupt nicht (nachgeprueft an der Pressemeldung des
        Unternehmens vom 06.08.2026).

      * Sind BEIDE da und uneinig, gewinnt YAHOO. Das war zuerst anders
        gebaut ("der fruehere Termin gewinnt"), und die Nachpruefung hat
        es widerlegt:
          AYA — Yahoo 13.08. nach Schluss, Nasdaq 14.08. vorboerslich.
                Richtig war der 13.08. nach Schluss; Nasdaq hatte
                offenbar den Termin der TELEFONKONFERENZ (14.08.,
                10 Uhr) genommen.
          DY  — Yahoo 26.08. vorboerslich, Nasdaq 19.08.
                Richtig war der 26.08.; Nasdaq lag eine Woche zu frueh.
        In beiden gepruefen Faellen lag Yahoo richtig und Nasdaq falsch.

      * Die Uneinigkeit wird trotzdem VERMERKT. Zwei Faelle sind eine
        duenne Grundlage fuer eine Regel; wer die Meldung liest, soll
        sehen, dass hier etwas offen ist.

    KURZ: Nasdaq bringt Abdeckung, Yahoo bringt Genauigkeit."""
    zusammen = {}
    for t in sorted({x.upper() for x in tickers if x}):
        y, n = yahoo.get(t), nasdaq.get(t)
        if not y and not n:
            continue
        if y and not n:
            zusammen[t] = {**y, "quellen": ["yahoo"]}
        elif n and not y:
            zusammen[t] = {**n, "quellen": ["nasdaq"]}
        elif y["datum"] == n["datum"]:
            # Gleicher Tag: Yahoo gewinnt, weil es die Uhrzeit kennt.
            eintrag = dict(y)
            eintrag["quellen"] = ["yahoo", "nasdaq"]
            if n["lage"] != "unbekannt" and n["lage"] != y["lage"]:
                eintrag["uneinig"] = ("Tageszeit uneinig: Nasdaq "
                                      + n["lage"] + ", Yahoo " + y["lage"])
            zusammen[t] = eintrag
        else:
            # YAHOO GEWINNT das Datum (siehe oben, an AYA und DY
            # nachgeprueft). Nasdaq bleibt trotzdem im Vermerk stehen.
            zusammen[t] = {**y, "quellen": ["yahoo", "nasdaq"],
                           "uneinig": ("Quellen uneinig: " + y["datum"]
                                       + " (Yahoo, hier bevorzugt) gegen "
                                       + n["datum"] + " (Nasdaq)")}
    return zusammen


def baue(tickers, pfad=DATEI, leise=False):
    """Termine holen und ablegen — aus BEIDEN Quellen."""
    termine, ohne = hole_termine(tickers, leise)
    try:
        from zoneinfo import ZoneInfo
        stempel = (datetime.now(ZoneInfo("Europe/Vienna"))
                   .strftime("%Y-%m-%d %H:%M") + " Wien")
    except Exception:
        stempel = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        nasdaq = hole_nasdaq(leise=leise)
    except Exception as e:
        nasdaq = {}
        if not leise:
            print(f"    Nasdaq-Kalender nicht nutzbar ({type(e).__name__}) — "
                  f"es gilt allein Yahoo.")
    zusammen = _zusammenfuehren(termine, nasdaq, tickers)
    nur_nasdaq = sorted(set(zusammen) - set(termine))
    uneinig = sorted(k for k, v in zusammen.items() if v.get("uneinig"))
    if not leise:
        print(f"  Nasdaq kannte {len(nasdaq)} Termine; davon {len(nur_nasdaq)} "
              f"in unserer Liste, die Yahoo NICHT hatte"
              + (": " + ", ".join(nur_nasdaq[:8]) if nur_nasdaq else ""))
        if uneinig:
            print(f"  Quellen uneinig bei {len(uneinig)}: "
                  + ", ".join(uneinig[:8]))
    inhalt = {"gebaut_am": stempel, "ohne_termin": sorted(ohne),
              "nur_nasdaq": nur_nasdaq, "uneinig": uneinig,
              "aktien": zusammen}
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(inhalt, f, ensure_ascii=False, indent=1)
    if not leise:
        print(f"  Zahlen-Termine: {len(termine)} Aktien mit Termin, "
              f"{len(ohne)} ohne → {pfad}")
    setze(inhalt)
    return inhalt


def lade(pfad=DATEI, leise=True):
    global _termine
    if _termine is not None:
        return _termine
    try:
        with open(pfad, encoding="utf-8") as f:
            _termine = json.load(f).get("aktien", {})
    except Exception:
        _termine = {}
        if not leise:
            print("  Keine Zahlen-Termine abgelegt — es wird nichts vermerkt.")
    return _termine


def setze(inhalt):
    global _termine
    _termine = (inhalt.get("aktien", inhalt) if isinstance(inhalt, dict)
                else {})
    return _termine


def hinweis(ticker, heute=None, termine=None):
    """Der Vermerk fuer die Meldung, oder None.

    heute: Datum in NEW YORKER Zeit. Wichtig, weil der Handelstag daran
    haengt und nicht am Wiener Kalender — um 23:00 Wien ist in New York
    noch derselbe Tag."""
    t = (termine if termine is not None else lade()).get(
        (ticker or "").upper())
    if not t:
        return None
    if heute is None:
        try:
            from zoneinfo import ZoneInfo
            heute = datetime.now(ZoneInfo("America/New_York")).date()
        except Exception:
            heute = date.today()
    try:
        tag = date.fromisoformat(t["datum"])
    except Exception:
        return None

    lage, uhr = t.get("lage"), t.get("uhrzeit", "")
    # Woher der Vermerk kommt und wie sicher er ist, gehoert dazu.
    zusatz = ""
    if t.get("uneinig"):
        zusatz = "; " + t["uneinig"]
    elif t.get("quellen") == ["nasdaq"]:
        zusatz = "; nur laut Nasdaq-Kalender"
    # Nasdaq liefert keine Uhrzeit. Dann faellt die Klammer ganz weg,
    # statt eine Zeitangabe zu erfinden, die keine ist.
    wann = f" ({uhr} New York)" if uhr else ""
    if tag == heute and lage == "nachboerslich":
        return f"ZAHLEN HEUTE nach Börsenschluss{wann}{zusatz}"
    if tag == heute and lage == "vorboerslich":
        return f"Zahlen heute VOR Eröffnung gebracht{wann}{zusatz}"
    # Nasdaq kennt oft nur den Tag, nicht die Uhrzeit. Dann wird trotzdem
    # gewarnt — "Zeit unbekannt" ist eine ehrliche Auskunft, Schweigen
    # waere die falsche.
    if tag == heute and lage == "unbekannt":
        return f"ZAHLEN HEUTE, Tageszeit unbekannt{zusatz}"
    if tag == heute + timedelta(days=1) and lage == "unbekannt":
        return f"ZAHLEN MORGEN, Tageszeit unbekannt{zusatz}"
    if tag == heute and lage == "im_handel":
        return f"ZAHLEN HEUTE während des Handels{wann}{zusatz}"
    if tag == heute + timedelta(days=1) and lage == "vorboerslich":
        return f"ZAHLEN MORGEN vor Eröffnung{wann}{zusatz}"
    return None


def selbsttest() -> int:
    fehler = []

    def p(name, bedingung, zusatz=""):
        print(f"  {'ok  ' if bedingung else 'FEHL'} {name}"
              + (f" — {zusatz}" if zusatz else ""))
        if not bedingung:
            fehler.append(name)

    print("Zahlen-Termine, Selbsttest")

    p("16:00 gilt als nachbörslich", _lage(16, 0) == "nachboerslich")
    p("15:59 gilt noch nicht als nachbörslich",
      _lage(15, 59) == "im_handel")
    p("08:00 gilt als vorbörslich", _lage(8, 0) == "vorboerslich")
    p("09:29 gilt als vorbörslich", _lage(9, 29) == "vorboerslich")
    p("09:30 gilt als im Handel", _lage(9, 30) == "im_handel")

    heute = date(2026, 8, 12)
    t = {"ABC": {"datum": "2026-08-12", "uhrzeit": "16:00",
                 "lage": "nachboerslich"},
         "DEF": {"datum": "2026-08-13", "uhrzeit": "07:00",
                 "lage": "vorboerslich"},
         "GHI": {"datum": "2026-08-12", "uhrzeit": "08:00",
                 "lage": "vorboerslich"},
         "JKL": {"datum": "2026-08-20", "uhrzeit": "16:00",
                 "lage": "nachboerslich"},
         "MNO": {"datum": "2026-08-12", "uhrzeit": "11:00",
                 "lage": "im_handel"}}

    h = hinweis("ABC", heute, t)
    p("Zahlen HEUTE nach Schluss werden vermerkt",
      h and "HEUTE nach Börsenschluss" in h, h)
    h = hinweis("DEF", heute, t)
    p("Zahlen MORGEN früh werden vermerkt",
      h and "MORGEN vor Eröffnung" in h, h)
    h = hinweis("GHI", heute, t)
    p("Zahlen von heute früh werden als geschehen vermerkt",
      h and "VOR Eröffnung gebracht" in h, h)
    h = hinweis("MNO", heute, t)
    p("Zahlen mitten im Handel werden vermerkt",
      h and "während des Handels" in h, h)
    p("Ein Termin in acht Tagen wird NICHT vermerkt",
      hinweis("JKL", heute, t) is None)
    p("Eine Aktie ohne Termin ergibt nichts",
      hinweis("XYZ", heute, t) is None)
    p("Kein Kürzel ergibt nichts", hinweis(None, heute, t) is None)
    p("Kleinschreibung wird gefunden",
      hinweis("abc", heute, t) is not None)

    # WAS BEWUSST NICHT VERMERKT WIRD, und warum:
    # Zahlen MORGEN NACH Schluss sind heute noch kein Uebernacht-Risiko.
    # Wer heute kauft, hat morgen einen ganzen Handelstag Zeit — und
    # morgen steht der Vermerk dann als "ZAHLEN HEUTE nach Boersenschluss"
    # da. Nur der Termin morgen FRUEH trifft eine heute eroeffnete
    # Position ueber Nacht, und genau der wird vermerkt.
    p("Zahlen morgen NACH Schluss sind heute noch kein Vermerk",
      hinweis("ABC", date(2026, 8, 11), t) is None)
    p("Am Tag selbst steht der Vermerk dann",
      "HEUTE nach Börsenschluss" in (hinweis("ABC", date(2026, 8, 12), t) or ""))
    p("Am Tag danach ist er wieder still",
      hinweis("ABC", date(2026, 8, 13), t) is None)

    # --- DIE DREI FAELLE, an echten Nachrichten geprueft (13.08.2026) ---
    # Sie stehen hier, damit die Zusammenfuehr-Regel nicht wieder kippt.
    # Quellen: Pressemeldungen der Unternehmen bzw. deren Ankuendigungen.
    y = {"AYA": {"datum": "2026-08-13", "uhrzeit": "16:00",
                 "lage": "nachboerslich"},
         "DY": {"datum": "2026-08-26", "uhrzeit": "08:00",
                "lage": "vorboerslich"}}
    n = {"AYA": {"datum": "2026-08-14", "uhrzeit": "", "lage": "vorboerslich"},
         "DY": {"datum": "2026-08-19", "uhrzeit": "", "lage": "unbekannt"},
         "ASND": {"datum": "2026-08-13", "uhrzeit": "",
                  "lage": "vorboerslich"}}
    z = _zusammenfuehren(y, n, ["AYA", "DY", "ASND"])

    p("AYA: Yahoo hatte recht (13.08. nach Schluss, nicht 14.08.)",
      z["AYA"]["datum"] == "2026-08-13"
      and z["AYA"]["lage"] == "nachboerslich", z["AYA"]["datum"])
    p("DY: Yahoo hatte recht (26.08., nicht 19.08.)",
      z["DY"]["datum"] == "2026-08-26", z["DY"]["datum"])
    p("ASND: nur Nasdaq kannte den Termin, er wird uebernommen",
      z["ASND"]["datum"] == "2026-08-13"
      and z["ASND"]["quellen"] == ["nasdaq"])
    p("Bei Uneinigkeit steht der Widerspruch im Eintrag",
      z["AYA"].get("uneinig") and z["DY"].get("uneinig"))
    p("Der Vermerk nennt die Uneinigkeit",
      "uneinig" in (hinweis("AYA", date(2026, 8, 13), z) or "").lower())
    p("Ein Termin nur von Nasdaq wird als solcher gekennzeichnet",
      "nur laut Nasdaq" in (hinweis("ASND", date(2026, 8, 13), z) or ""))

    # Kaputte Daten duerfen nichts umwerfen
    p("Unlesbares Datum ergibt nichts",
      hinweis("X", heute, {"X": {"datum": "kaputt", "lage": "nachboerslich"}})
      is None)

    print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles bestanden.")
    return 1 if fehler else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Zahlen-Termine je Aktie.")
    ap.add_argument("--bauen", action="store_true")
    ap.add_argument("--zeigen", action="store_true")
    ap.add_argument("--tickers", help="Komma-Liste; sonst aus finviz_3.csv")
    ap.add_argument("--selbsttest", action="store_true")
    args = ap.parse_args()

    if args.selbsttest:
        return selbsttest()

    if args.bauen:
        if args.tickers:
            liste = [t.strip() for t in args.tickers.split(",") if t.strip()]
        else:
            import pandas as pd
            liste = pd.read_csv("finviz_3.csv")["Ticker"].astype(str).tolist()
        baue(liste)
        return 0

    if args.zeigen:
        if not os.path.exists(DATEI):
            print("Noch nichts abgelegt.")
            return 0
        d = json.loads(open(DATEI, encoding="utf-8").read())
        print(f"Gebaut am {d.get('gebaut_am')}: {len(d.get('aktien', {}))} "
              f"Aktien mit Termin, {len(d.get('ohne_termin', []))} ohne.")
        heute = date.today()
        bald = [(k, v) for k, v in d.get("aktien", {}).items()
                if date.fromisoformat(v["datum"]) <= heute + timedelta(days=7)]
        print(f"In den naechsten sieben Tagen: {len(bald)}")
        for k, v in sorted(bald, key=lambda x: x[1]["datum"]):
            print(f"  {k:6s} {v['datum']}  {v['uhrzeit']}  {v['lage']}")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
