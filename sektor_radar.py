#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SEKTOR-RADAR — dreht gerade eine ganze Branche?
================================================
Gerhards Paket vom 13.08.2026 ("Sektor Radar v2"), von Mathias zum Einbau
gegeben. Es ersetzt eine erste Fassung, die es in diesem Repo nie gab —
gesucht und nicht gefunden, es gibt hier also nichts abzuloesen.

WAS ES TUT, und mehr tut es ausdruecklich nicht
    Fuer jeden der 36 Branchen-ETFs, einmal am Tag auf Tagesschlusskursen:
      1) UMKEHR: Der Schlusskurs kreuzt von unter dem eigenen
         10-Tage-Schnitt nach darueber (Dreher nach oben) oder umgekehrt.
      2) VOLUMEN: Am selben Tag zeigt UNSERE Volumenformel (IBD Volume %
         Change, dieselbe wie ueberall sonst) mindestens +50 %.
      3) BESTAETIGUNG gegen Zufallsrauschen: Der Abstand zum
         10-Tage-Schnitt muss sich in dieselbe Richtung entwickelt haben
         wie zwei Tage zuvor. Ein einzelner Wackler direkt nach einer
         Kreuzung zaehlt damit nicht.

    Keine Aktienliste, kein Finviz, keine Industrie-Ebene, kein Median,
    keine neu erfundene Kennzahl. Jeder ETF wird fuer sich betrachtet.

DREI ABWEICHUNGEN VOM REFERENZ-CODE, alle absichtlich
    1. KURSQUELLE. Gerhards Fassung ruft yfinance selbst. Sein LIES_MICH
       sagt aber ausdruecklich: "Datenabruf an die bestehende Kursquelle
       des Systems anhaengen, keine eigene neue Anbindung bauen." Also
       laeuft es ueber pattern_scanner.fetch_history — mit Tages-Cache,
       Sammelabruf und dem Ausweichweg ueber Twelve Data. Dessen Spalten
       heissen klein (close, volume), Gerhards Referenzcode erwartet
       Yahoos Grossschreibung; _spalte() nimmt beides.
    2. UNFERTIGER HANDELSTAG. Der Referenzcode nimmt immer die letzte
       Zeile als "heute". Waehrend des Handels ist die aber eine halbe
       Kerze: Am 13.08.2026 um 20:30 Wiener Zeit stand bei XLK ein
       Tagesvolumen von 3,42 Mio gegen 5,88 Mio am Vortag — die
       Volumenpruefung haette also systematisch zu niedrig gerechnet und
       jeden echten Dreher verschluckt. Deshalb prueft tag_fertig(), ob
       die letzte Zeile ein ABGESCHLOSSENER Handelstag ist; sonst gibt es
       kein Signal, sondern einen Vermerk. Im Nachtlauf ist das immer
       erfuellt.
    3. GESENDET WIRD NICHT AUS DEM NACHTLAUF. Mathias am 27.07.2026, im
       Scanner-Workflow festgehalten: "KEIN Push mehr. Gemeldet wird
       ausschliesslich vom Waechter, und zwar erst ab der New Yorker
       Eroeffnung. Die frueheren Mitternachtsnachrichten waren Treffer,
       die zu diesem Zeitpunkt ohnehin niemand handeln konnte." Gerhards
       Paket sendet direkt aus dem Nachtlauf; das waere ein Rueckfall.
       Deshalb: Der Nachtlauf RECHNET und legt sektor_radar.json ab, der
       Waechter MELDET daraus einmal zur Eroeffnung.

EINE UNSTIMMIGKEIT IM PAKET, hier nicht stillschweigend uebergangen
    Gerhards CFG enthaelt "bestaetigung_tage": 2, sein Code liest den
    Wert aber nirgends — die Bestaetigung geschieht ueber den Vergleich
    der Abstaende (Punkt 3 oben) und haengt an der festen Spanne von zwei
    Tagen. Ein Einstellwert, den niemand liest, ist eine Falle: Wer ihn
    auf 3 stellt, aendert nichts und glaubt es doch. Er steht deshalb
    NICHT in config.py; die Zwei-Tage-Spanne ist fest verdrahtet und hier
    benannt. Wenn sie einstellbar sein soll, ist das eine bewusste
    Erweiterung und keine Uebernahme.

Aufruf:
    python sektor_radar.py --bauen         rechnen und sektor_radar.json ablegen
    python sektor_radar.py --zeigen        rechnen und nur anzeigen
    python sektor_radar.py --selbsttest
"""

import json
import sys
from datetime import date, datetime

import config
import volumen

DATEI = "sektor_radar.json"

_CFG = config.CFG["sektor_radar"]
MA_TAGE = int(_CFG["ma_tage"])
VOL_PCT_SCHWELLE = float(_CFG["vol_pct_schwelle"])
V50_TAGE = int(_CFG["v50_tage"])

# Die Spanne der Bestaetigung: heute gegen VORGESTERN. Fest, siehe oben.
BESTAETIGUNG_ABSTAND = 2

# Die 36 Branchen-ETFs, Kuerzel auf Klartext. Die einzige Liste in diesem
# Modul, woertlich aus Gerhards Paket uebernommen.
ETF_UNIVERSE = {
    "XLK": "Technology", "XLF": "Financials", "XLV": "Health Care",
    "XLE": "Energy", "XLI": "Industrials", "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples", "XLU": "Utilities", "XLB": "Materials",
    "XLRE": "Real Estate", "XLC": "Communication Services",
    "SMH": "Semiconductors", "SOXX": "Semiconductors alt", "IGV": "Software",
    "XBI": "Biotech", "IHI": "Medical Devices", "KRE": "Regional Banks",
    "KBE": "Banks", "XOP": "Oil & Gas E&P", "OIH": "Oil Services",
    "XME": "Metals & Mining", "XRT": "Retail", "XHB": "Homebuilders",
    "ITB": "Home Construction", "JETS": "Airlines", "TAN": "Solar",
    "LIT": "Lithium & Battery", "ARKK": "Innovation/Growth",
    "IBB": "Biotech large", "GDX": "Gold Miners",
    "ITA": "Aerospace & Defense", "PAVE": "Infrastructure",
    "HACK": "Cybersecurity", "FINX": "Fintech", "SKYY": "Cloud",
    "BOTZ": "Robotics & AI",
}


# ---------------------------------------------------------------------------
# Spalten und Handelstag
# ---------------------------------------------------------------------------

def _spalte(df, name):
    """Eine Spalte holen, gleich ob sie 'close' oder 'Close' heisst.

    Unsere Kursquelle schreibt klein, Yahoo gross. Gerhards Referenzcode
    und seine Testreihen verwenden die grosse Schreibweise; beides muss
    hier durchgehen, sonst laufen entweder seine Tests nicht oder unsere
    echten Daten nicht."""
    for k in (name.lower(), name.capitalize(), name.upper()):
        if k in df.columns:
            return df[k]
    raise KeyError(f"Spalte {name} fehlt (vorhanden: {list(df.columns)})")


def _datumsspalte(df):
    """Die Datumswerte einer Kurstabelle, egal ob als Spalte oder Index."""
    for k in ("datetime", "date", "Date", "Datetime"):
        if k in df.columns:
            return df[k]
    return df.index.to_series()


def tag_fertig(df, jetzt=None) -> bool:
    """Ist die LETZTE Zeile ein abgeschlossener Handelstag?

    Waehrend des Handels ist sie es nicht: Kurs und Volumen wachsen noch.
    Genau deshalb rechnet dieses Modul im Nachtlauf und nicht nebenbei —
    siehe Abweichung 2 im Kopf. Laesst sich die Zeitzone nicht bestimmen,
    gilt der Tag vorsichtshalber als UNFERTIG; lieber kein Signal als ein
    falsches."""
    try:
        import pandas as pd
        letzter = pd.to_datetime(_datumsspalte(df).iloc[-1]).date()
    except Exception:
        return False
    heute_ny, nach_schluss = volumen._ny_tag_und_schluss(jetzt)
    if heute_ny is None:
        return False
    if letzter < heute_ny:
        return True                      # ein vergangener Tag ist fertig
    if letzter == heute_ny:
        return nach_schluss
    return False                         # Zeile aus der Zukunft: nicht deuten


# ---------------------------------------------------------------------------
# Die zwei Bedingungen
# ---------------------------------------------------------------------------

def pruefe_umkehr(close_serie, ma_tage=None):
    """Kreuzt der Schlusskurs HEUTE den eigenen Schnitt?

    Rueckgabe: 'hoch', 'runter' oder None. Gestern auf der einen Seite,
    heute auf der anderen — mehr ist es nicht, und mehr soll es auch
    nicht sein."""
    ma_tage = ma_tage or MA_TAGE
    if len(close_serie) < ma_tage + 2:
        return None
    ma = close_serie.rolling(ma_tage).mean()
    heute_ueber = close_serie.iloc[-1] > ma.iloc[-1]
    gestern_ueber = close_serie.iloc[-2] > ma.iloc[-2]
    if heute_ueber and not gestern_ueber:
        return "hoch"
    if not heute_ueber and gestern_ueber:
        return "runter"
    return None


def pruefe_volumen_dreher(df):
    """Volume % Change des letzten Tages, mit UNSERER Formel.

    Der EOD-Fall: ohne Uhrzeit und ohne Kurve rechnet
    volumen.volume_pct_change die reine Tagesformel. Der Durchschnitt
    nimmt die 50 Tage VOR dem letzten — der zu bewertende Tag darf nicht
    in seinem eigenen Vergleichswert stecken."""
    if len(df) < V50_TAGE + 2:
        return None
    vol = _spalte(df, "volume")
    v50 = float(vol.iloc[-(V50_TAGE + 1):-1].mean())
    v_heute = float(vol.iloc[-1])
    return volumen.volume_pct_change(v_heute, v50)


def pruefe_etf_dreher(df, jetzt=None):
    """Beide Bedingungen samt Bestaetigung fuer EINEN ETF.

    Rueckgabe: dict mit richtung und volumen_pct, oder None."""
    if not tag_fertig(df, jetzt):
        return None
    close = _spalte(df, "close")
    richtung = pruefe_umkehr(close)
    if richtung is None:
        return None
    vol_pct = pruefe_volumen_dreher(df)
    if vol_pct is None or vol_pct < VOL_PCT_SCHWELLE:
        return None

    # Bestaetigung: Der Abstand zum Schnitt muss sich in die Richtung des
    # Drehers entwickelt haben. Ohne das zaehlt ein einzelner Wackler
    # direkt nach der Kreuzung schon als Umkehr.
    ma = close.rolling(MA_TAGE).mean()
    abstand_heute = float(close.iloc[-1] - ma.iloc[-1])
    i = BESTAETIGUNG_ABSTAND + 1
    abstand_vorher = float(close.iloc[-i] - ma.iloc[-i]) if len(close) >= i else 0.0
    haelt = (abstand_heute > abstand_vorher if richtung == "hoch"
             else abstand_heute < abstand_vorher)
    if not haelt:
        return None
    return {"richtung": richtung, "volumen_pct": round(vol_pct, 1)}


# ---------------------------------------------------------------------------
# Lauf ueber alle 36
# ---------------------------------------------------------------------------

def lade_etf_kurse(leise=False):
    """Tageskurse aller 36 ETFs — ueber die BESTEHENDE Kursquelle.

    Keine eigene Anbindung (Gerhards ausdrueckliche Vorgabe): derselbe
    Sammelabruf, derselbe Tages-Cache und derselbe Ausweichweg, die der
    Scanner ohnehin benutzt."""
    import pattern_scanner as ps
    kuerzel = list(ETF_UNIVERSE)
    ps.lade_yahoo_sammelabruf(kuerzel)
    limiter = ps.RateLimiter(8)
    daten = {}
    for etf in kuerzel:
        try:
            df = ps.fetch_history(etf, None, limiter)
        except Exception as e:
            if not leise:
                print(f"  {etf}: kein Kurs ({type(e).__name__})")
            continue
        if df is not None and len(df):
            daten[etf] = df
    return daten


def scanne_etfs(etf_daten, jetzt=None):
    """Rueckgabe: (treffer, unfertig). Treffer nach Volumenstaerke sortiert.

    'unfertig' zaehlt die ETFs, deren letzte Kurszeile noch laeuft — das
    ist keine Fehlermeldung, sondern die Auskunft, dass es zu frueh ist."""
    treffer, unfertig = [], []
    for etf, df in etf_daten.items():
        if not tag_fertig(df, jetzt):
            unfertig.append(etf)
            continue
        erg = pruefe_etf_dreher(df, jetzt)
        if erg:
            treffer.append({
                "etf": etf, "name": ETF_UNIVERSE.get(etf, etf),
                "richtung": erg["richtung"],
                "volumen_pct": erg["volumen_pct"],
                "kurs": round(float(_spalte(df, "close").iloc[-1]), 2),
            })
    treffer.sort(key=lambda t: -t["volumen_pct"])
    return treffer, unfertig


# ---------------------------------------------------------------------------
# Meldung
# ---------------------------------------------------------------------------

def absaetze(treffer):
    """Die Meldung als LISTE von Absaetzen, einer je Richtung.

    Der Waechter verschickt Absatzweise (sende() portioniert danach),
    deshalb liefert das Modul sie gleich getrennt — statt sie zu einem
    Text zu fuegen, den der Waechter wieder auseinanderschneiden muss."""
    hoch = [t for t in treffer if t["richtung"] == "hoch"]
    runter = [t for t in treffer if t["richtung"] == "runter"]
    raus = []
    for ueberschrift, gruppe in (("Dreht nach oben", hoch),
                                 ("Dreht nach unten", runter)):
        if not gruppe:
            continue
        zeilen = [f"{ueberschrift}:"]
        for i, t in enumerate(gruppe, 1):
            zeilen.append(f"{i}. {t['etf']} ({t['name']}); Kurs "
                          f"{t['kurs']:.2f}; Volumen {t['volumen_pct']:+.0f}% "
                          f"gegenüber dem 50-Tage-Schnitt")
        raus.append("\n".join(zeilen))
    return raus


def baue_meldung(treffer):
    """Derselbe Text am Stueck, fuer Anzeige und Protokoll.

    Trennzeichen wie im uebrigen System: Strichpunkt zwischen
    verschiedenen Angaben, Beistrich innerhalb zusammengehoeriger, kein
    Gedankenstrich. Je ETF eine Zeile mit Nummer, damit beim Vorlesen
    hoerbar ist, wo der naechste beginnt."""
    return "\n\n".join(absaetze(treffer))


def titel(treffer):
    """Die ntfy-Kopfzeile. Sie sagt, ob sich das Öffnen lohnt."""
    hoch = sum(1 for t in treffer if t["richtung"] == "hoch")
    runter = len(treffer) - hoch
    teile = []
    if hoch:
        teile.append(f"{hoch} nach oben")
    if runter:
        teile.append(f"{runter} nach unten")
    return "Sektor-Radar: " + (", ".join(teile) if teile else "kein Dreher")


# ---------------------------------------------------------------------------
# Ablegen und lesen
# ---------------------------------------------------------------------------

def bauen(pfad=DATEI, leise=False, jetzt=None):
    """Rechnen und ablegen. Laeuft im Nachtlauf, sendet NICHTS."""
    if not leise:
        print(f"Sektor-Radar: lade {len(ETF_UNIVERSE)} Branchen-ETFs …")
    daten = lade_etf_kurse(leise=leise)
    if not leise:
        print(f"  {len(daten)} von {len(ETF_UNIVERSE)} geladen.")
    treffer, unfertig = scanne_etfs(daten, jetzt)
    inhalt = {
        "gebaut_am": datetime.now().isoformat(timespec="seconds"),
        "handelstag": _letzter_handelstag(daten),
        "geladen": len(daten), "unfertig": sorted(unfertig),
        "treffer": treffer,
    }
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(inhalt, f, ensure_ascii=False, indent=1)
    if not leise:
        print(f"  {len(treffer)} Dreher; nach {pfad} geschrieben.")
        if unfertig:
            print(f"  {len(unfertig)} ETFs mit noch laufendem Handelstag: "
                  + ", ".join(unfertig[:10]))
    return inhalt


def _letzter_handelstag(daten):
    """Auf welchen Tag sich der Befund bezieht. Steht in der Datei, damit
    der Waechter am naechsten Morgen sieht, ob sie von gestern ist."""
    import pandas as pd
    tage = []
    for df in daten.values():
        try:
            tage.append(pd.to_datetime(_datumsspalte(df).iloc[-1]).date())
        except Exception:
            pass
    return max(tage).isoformat() if tage else None


def lies(pfad=DATEI):
    """Was der Nachtlauf abgelegt hat, oder ein leerer Befund."""
    try:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"treffer": [], "handelstag": None}


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

def selbsttest() -> int:
    import numpy as np
    import pandas as pd
    fehler = []

    def p(name, bedingung, zusatz=""):
        print(f"  {'ok  ' if bedingung else 'FEHL'} {name}"
              + (f" — {zusatz}" if zusatz else ""))
        if not bedingung:
            fehler.append(name)

    # Ein Datum in der Vergangenheit, damit tag_fertig() immer wahr ist.
    def reihe(kurse, volumen_werte, ende=date(2026, 8, 12)):
        idx = pd.bdate_range(end=pd.Timestamp(ende), periods=len(kurse))
        return pd.DataFrame({"datetime": idx, "close": kurse,
                             "volume": volumen_werte})

    # --- Gerhards fuenf Testfaelle, unveraendert in der Sache ---
    kurs = [100] * 15 + [98, 96, 94, 92, 90, 89, 88, 87, 86, 85] + [95]
    idx = pd.bdate_range("2026-05-01", periods=len(kurs))
    p("Kreuzung nach oben wird erkannt",
      pruefe_umkehr(pd.Series(kurs, index=idx)) == "hoch")
    kurs_ab = [100] * 15 + [102, 104, 106, 108, 110, 111, 112, 113, 114, 115] + [105]
    p("Kreuzung nach unten wird erkannt",
      pruefe_umkehr(pd.Series(kurs_ab, index=idx)) == "runter")
    p("Ohne Kreuzung kein Signal",
      pruefe_umkehr(pd.Series([100] * 30, index=pd.bdate_range(
          "2026-05-01", periods=30))) is None)

    n = 60
    vol = np.full(n, 1_000_000.0)
    vol[-1] = 6_000_000.0
    pct = pruefe_volumen_dreher(reihe([100] * n, vol))
    p("Sechsfaches Volumen ergibt einen hohen Ausschlag",
      pct is not None and pct > 400, f"{pct:+.0f} %" if pct else "")

    pad = 40
    kurs_voll = [100] * pad + kurs
    n3 = len(kurs_voll)
    ohne = np.full(n3, 1_000_000.0)
    p("Kursdreher OHNE Volumen wird verworfen",
      pruefe_etf_dreher(reihe(kurs_voll, ohne)) is None)
    mit = ohne.copy()
    mit[-1] = 5_500_000.0
    erg = pruefe_etf_dreher(reihe(kurs_voll, mit))
    p("Kursdreher MIT Volumen wird gemeldet",
      erg is not None and erg["richtung"] == "hoch")

    p("Es sind genau 36 ETFs", len(ETF_UNIVERSE) == 36, len(ETF_UNIVERSE))
    import inspect
    quelltext = "\n".join(inspect.getsource(f) for f in (
        lade_etf_kurse, pruefe_umkehr, pruefe_volumen_dreher,
        pruefe_etf_dreher, scanne_etfs, absaetze, baue_meldung, bauen))
    p("Keine Finviz-, Median- oder CSV-Nutzung im Produktionscode",
      not any(v in quelltext for v in ("median(", "read_csv(", ".csv",
                                       "load_universe(", "cluster_zonen(")))

    # --- Was bei uns dazukommt ---
    # 1. Spaltennamen: Gerhards Testreihen sind gross geschrieben, unsere
    #    Kursquelle klein. Beides muss laufen.
    gross = reihe(kurs_voll, mit).rename(
        columns={"close": "Close", "volume": "Volume", "datetime": "Date"})
    p("Grosse Spaltennamen (Yahoo) werden genauso verstanden",
      (pruefe_etf_dreher(gross) or {}).get("richtung") == "hoch")

    # 2. Der unfertige Handelstag. Genau hier lag die Falle im
    #    Referenzcode: waehrend des Handels ist die letzte Zeile halb.
    heute_ny, _ = volumen._ny_tag_und_schluss()
    laufend = reihe(kurs_voll, mit, ende=heute_ny)
    mittags = datetime(heute_ny.year, heute_ny.month, heute_ny.day, 12, 0)
    try:
        from zoneinfo import ZoneInfo
        mittags = mittags.replace(tzinfo=ZoneInfo("America/New_York"))
        abends = mittags.replace(hour=17)
    except Exception:
        abends = mittags
    p("Waehrend des Handels gibt es KEIN Signal",
      pruefe_etf_dreher(laufend, jetzt=mittags) is None)
    p("Nach Boersenschluss zaehlt derselbe Tag",
      (pruefe_etf_dreher(laufend, jetzt=abends) or {}).get("richtung") == "hoch")
    p("Ein vergangener Tag gilt immer als fertig",
      tag_fertig(reihe(kurs_voll, mit), jetzt=mittags))

    # 3. Der zu bewertende Tag darf nicht im eigenen Durchschnitt stecken.
    #    ACHTUNG beim Pruefen: 'wert or 99' faellt hier auf die Nase, weil
    #    0.0 in Python falsch ist und der Ersatzwert einspringt. Genau
    #    daran ist dieser Test beim ersten Lauf gescheitert.
    gleichauf = pruefe_volumen_dreher(reihe([100] * 60, np.full(60, 1e6)))
    p("Gleichbleibendes Volumen ergibt null Prozent",
      gleichauf is not None and abs(gleichauf) < 0.001, gleichauf)

    # 4. Zu kurze Historie darf nichts behaupten.
    p("Zu wenig Historie ergibt kein Volumenurteil",
      pruefe_volumen_dreher(reihe([100] * 20, np.full(20, 1e6))) is None)
    p("Zu wenig Historie ergibt kein Signal",
      pruefe_etf_dreher(reihe([100] * 20, np.full(20, 1e6))) is None)

    # 5. Meldungstext: Trennzeichen und kein Gedankenstrich.
    t = [{"etf": "XLE", "name": "Energy", "richtung": "hoch",
          "volumen_pct": 128.4, "kurs": 91.2},
         {"etf": "XLU", "name": "Utilities", "richtung": "runter",
          "volumen_pct": 61.0, "kurs": 82.5}]
    text = baue_meldung(t)
    p("Meldung nennt beide Richtungen",
      "Dreht nach oben" in text and "Dreht nach unten" in text)
    p("Je Richtung ein eigener Absatz fuer den Versand",
      len(absaetze(t)) == 2, len(absaetze(t)))
    p("Ohne Treffer keine Absaetze", absaetze([]) == [])
    p("Meldung enthaelt keinen Gedankenstrich", "—" not in text and "–" not in text)
    p("Titel zaehlt beide Richtungen",
      titel(t) == "Sektor-Radar: 1 nach oben, 1 nach unten", titel(t))
    p("Ohne Treffer bleibt der Text leer", baue_meldung([]) == "")

    # 6. Sortierung nach Volumenstaerke.
    daten = {"A": reihe(kurs_voll, mit), "B": reihe(kurs_voll, ohne)}
    tr, unf = scanne_etfs(daten)
    p("Nur der ETF mit Volumen wird gemeldet",
      [x["etf"] for x in tr] == ["A"], [x["etf"] for x in tr])
    p("Unfertige werden gezaehlt, nicht gemeldet",
      unf == [] and len(tr) == 1)

    print("\n" + ("Alles bestanden." if not fehler
                  else f"{len(fehler)} FEHLER: " + ", ".join(fehler)))
    return 1 if fehler else 0


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Sektor-Radar über die 36 ETFs")
    ap.add_argument("--bauen", action="store_true",
                    help="rechnen und sektor_radar.json ablegen")
    ap.add_argument("--zeigen", action="store_true",
                    help="rechnen und nur anzeigen, nichts schreiben")
    ap.add_argument("--selbsttest", action="store_true")
    a = ap.parse_args()
    if a.selbsttest:
        return selbsttest()
    if a.zeigen:
        daten = lade_etf_kurse()
        treffer, unfertig = scanne_etfs(daten)
        print(f"\n{titel(treffer)}")
        print(baue_meldung(treffer) or "Kein Dreher.")
        if unfertig:
            print(f"\n{len(unfertig)} ETFs mit noch laufendem Handelstag "
                  f"(zu früh am Tag): " + ", ".join(unfertig[:12]))
        return 0
    if a.bauen:
        bauen()
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
