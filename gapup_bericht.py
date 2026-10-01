#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GAP-UP-BERICHT: vorboersliche Gap-Ups, 20 Minuten vor der US-Eroeffnung
=====================================================================
Gerhards Auftrag vom 29.09.2026, Teil 5; seine Antworten in der Nacht auf
den 30.09.2026 (Fragen 12 und 13); IBD-Sprache seit 30.09.2026 nachmittags.

WANN: um 09:10 New Yorker Zeit, also um 15:10 Wiener Zeit; in den Wochen, in
denen die Zeitumstellung in Europa und den USA auseinanderfaellt (heuer 26.
bis 30. Oktober, im Fruehjahr 15. bis 26. Maerz), um 14:10. "Er kommt also
immer 20 Minuten vor der US-Eroeffnung." Angestossen wird der Lauf nach jedem
Lauf des Scanners im Zehn-Minuten-Takt (berichte.yml); faellig() entscheidet:
Montag bis Freitag zwischen 09:10 und 09:29 New Yorker Zeit, einmal je Tag.

UMFANG (Frage 12): der ganze US-Markt wie im Scanner, also jede Aktie der
Nachttabelle (scanner_tabelle.parquet), nicht nur Wochenlisten und
ueberwachte Aktien. Je Aktie steht dabei, ob sie auf einer Wochenliste steht.

KRITERIEN (Teil 5):
    vorboerslicher Gap-Up ab 5 Prozent zum Schluss des Vortags;
    vorboersliches Volumen mindestens 5 Prozent des 50-Tage-Schnitts des
    Tagesvolumens, in IBD-Sprache mindestens minus 95 Prozent ueber dem
    50-Tage-Schnitt;
    Kurs ab 15 Dollar; Boersenwert ab 700 Millionen Dollar;
    alle, die passen, keine Obergrenze; sortiert nach vorboerslichem
    Dollarvolumen.
Kurs und Gap rechnen mit dem vorboerslichen Kurs; der Boersenwert ist der
der Nachttabelle, also zum Schluss des Vortags.

QUELLEN, am 01.10.2026 um 08:45 New Yorker Zeit gemessen:
    Yahoo liefert vorboersliche Kurse fuer den ganzen Markt gebuendelt
    (5.331 Aktien in 3,3 Sekunden), aber KEIN vorboersliches Volumen: Die
    Minutenkerzen der Vorboerse stehen bei ACN, NVDA und VICR durchweg auf 0.
    Nasdaq liefert das vorboersliche Volumen aller Handelsplaetze zusammen,
    je Aktie ein Abruf von zwei bis drei Sekunden; deshalb nur fuer die
    Kandidaten, die Gap, Kurs und Boersenwert schon erfuellen. Ohne Volumen
    von Nasdaq laesst sich das Kriterium nicht pruefen; solche Aktien stehen
    am Ende des Berichts mit Namen, nicht in der Liste.
    Die Schlagzeilen kommen von Yahoo: die bis zu drei neuesten seit dem
    Schluss des Vortags.

REINER INFO-BERICHT: keine Kaufmeldung, kein Alarm, kein Bot-Signal. Regel 3
betrifft Alarme und Kaeufe, nicht diesen Bericht. Erfuellt keine Aktie die
Kriterien, steht genau das im Bericht.

Aufruf:
    python gapup_bericht.py --faellig        prueft nur, ob der Bericht jetzt faellig ist
                                             (fuer den Ablauf, ohne Zusatzpakete)
    python gapup_bericht.py --bauen          baut und legt ab, wenn faellig
    python gapup_bericht.py --jetzt [--trocken]  baut sofort; trocken heisst nur ausgeben
    python gapup_bericht.py --selbsttest
"""

import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import berichte

try:
    from zoneinfo import ZoneInfo
    NY = ZoneInfo("America/New_York")
except Exception:  # noqa: BLE001
    NY = timezone(timedelta(hours=-4))

REPO = "mat-schmuck/heliot"
TABELLE_URL = f"https://github.com/{REPO}/releases/download/scanner-daten/scanner_tabelle.parquet"
TABELLE_DATEI = "scanner_tabelle.parquet"

GAP_MIN_PCT = 5.0
VOL_MIN_ANTEIL = 0.05          # 5 Prozent des 50-Tage-Schnitts
KURS_MIN = 15.0
MARKTKAP_MIN_MRD = 0.7
FENSTER_START = 9 * 60 + 10    # 09:10 New York
FENSTER_ENDE = 9 * 60 + 30     # bis vor der Eroeffnung
SCHLAGZEILEN = 3

YAHOO_QUOTE = "https://query1.finance.yahoo.com/v7/finance/quote"
YAHOO_FELDER = ("symbol,preMarketPrice,preMarketChangePercent,preMarketTime,regularMarketPrice,"
                "marketState,shortName,longName")
NASDAQ_VORBOERSE = "https://api.nasdaq.com/api/quote/{}/extended-trading?assetclass=stocks&markettype=pre"
NASDAQ_KOPF = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept": "application/json"}

ART = "gapup"


# ---------------------------------------------------------------------------
# Wann
# ---------------------------------------------------------------------------

def ny(jetzt=None) -> datetime:
    return (jetzt or datetime.now(timezone.utc)).astimezone(NY)


def im_fenster(jetzt=None) -> bool:
    t = ny(jetzt)
    minute = t.hour * 60 + t.minute
    return t.weekday() < 5 and FENSTER_START <= minute < FENSTER_ENDE


def heute_schon(berichte_liste, jetzt=None) -> bool:
    """Steht fuer den heutigen New Yorker Tag schon ein Gap-Up-Bericht da?"""
    tag = ny(jetzt).date()
    for e in berichte_liste or []:
        if e.get("art") == ART:
            z = berichte.zeit_lesen(e.get("zeit"))
            if z is not None and z.astimezone(NY).date() == tag:
                return True
    return False


def faellig(jetzt=None, token=None) -> tuple:
    """(faellig ja oder nein, Grund). Ohne Zusatzpakete lauffaehig."""
    if not im_fenster(jetzt):
        return False, "ausserhalb von 09:10 bis 09:29 New Yorker Zeit an einem Werktag"
    token = (token if token is not None else os.environ.get(berichte.TOKEN_ENV) or "").strip()
    if token:
        liste, _sha, fehler = berichte.datei_lesen(token)
        if not fehler and heute_schon(liste, jetzt):
            return False, "der Bericht von heute steht schon im Reiter"
    return True, "faellig"


# ---------------------------------------------------------------------------
# Daten
# ---------------------------------------------------------------------------

def tabelle_laden(pfad=None):
    import pandas as pd
    if pfad and os.path.exists(pfad):
        return pd.read_parquet(pfad)
    import io
    with urllib.request.urlopen(urllib.request.Request(TABELLE_URL, headers=NASDAQ_KOPF), timeout=120) as a:
        return pd.read_parquet(io.BytesIO(a.read()))


def yahoo_vorboerse(ticker_liste, melder=print) -> dict:
    """{Kuerzel: Quote} fuer alle Kuerzel, gebuendelt zu 400 je Abruf."""
    from yfinance.data import YfData
    d = YfData()
    raus = {}
    for i in range(0, len(ticker_liste), 400):
        teil = ticker_liste[i:i + 400]
        for versuch in range(3):
            try:
                r = d.get(YAHOO_QUOTE, params={"symbols": ",".join(teil), "fields": YAHOO_FELDER})
                for q in (r.json().get("quoteResponse") or {}).get("result") or []:
                    if q.get("symbol"):
                        raus[str(q["symbol"]).upper()] = q
                break
            except Exception as e:  # noqa: BLE001
                if versuch == 2:
                    melder(f"  Yahoo: Block ab {i} nicht erhalten ({type(e).__name__}).")
                time.sleep(2)
    return raus


def _zahl_aus(text):
    m = re.search(r"-?[\d,]+(?:\.\d+)?", str(text or ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def nasdaq_deuten(j) -> dict | None:
    """{volumen, kurs} aus der Antwort von extended-trading, oder None."""
    try:
        zeilen = (((j or {}).get("data") or {}).get("infoTable") or {}).get("rows") or []
        if not zeilen:
            return None
        z = zeilen[0]
        vol = _zahl_aus(z.get("volume"))
        kurs = _zahl_aus(str(z.get("consolidated") or "").split(" ")[0].replace("$", ""))
        if vol is None:
            return None
        return {"volumen": int(vol), "kurs": kurs}
    except Exception:  # noqa: BLE001
        return None


def nasdaq_vorboerse(symbol, holen=None) -> dict | None:
    sym = str(symbol).upper().replace("-", ".")
    url = NASDAQ_VORBOERSE.format(urllib.request.quote(sym))
    for versuch in range(2):
        try:
            if holen is not None:
                return nasdaq_deuten(holen(url))
            with urllib.request.urlopen(urllib.request.Request(url, headers=NASDAQ_KOPF), timeout=20) as a:
                return nasdaq_deuten(json.loads(a.read().decode("utf-8")))
        except Exception:  # noqa: BLE001
            time.sleep(1.5)
    return None


def schlagzeilen(symbol, seit: datetime, anzahl=SCHLAGZEILEN) -> list:
    """[(Zeit UTC, Anbieter, Titel)], neueste zuerst, nur seit 'seit'."""
    try:
        import yfinance as yf
        roh = yf.Ticker(symbol).get_news(count=10) or []
    except Exception:  # noqa: BLE001
        return []
    raus = []
    for e in roh:
        c = e.get("content") if isinstance(e.get("content"), dict) else e
        titel = str(c.get("title") or "").strip()
        zeit = c.get("pubDate") or c.get("displayTime")
        try:
            z = datetime.strptime(str(zeit), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
        anbieter = c.get("provider") if isinstance(c.get("provider"), dict) else {}
        if titel and z >= seit:
            raus.append((z, str(anbieter.get("displayName") or "").strip(), titel))
    raus.sort(key=lambda x: x[0], reverse=True)
    return raus[:anzahl]


def listen_je_aktie() -> dict:
    """{Kuerzel: [Namen der Listen]} aus den Dateien im Repo."""
    import listen
    raus = {}

    def dazu(menge, name):
        # Die Listen liefern Paare aus Kuerzel und Firma, die Einzelaktien nur
        # Kuerzel (listen.haupt_liste, listen.einzel_ticker).
        for t in menge or ():
            kuerzel = t[0] if isinstance(t, (tuple, list)) else t
            k = str(kuerzel or "").strip().upper()
            if k and name not in raus.setdefault(k, []):
                raus[k].append(name)
    try:
        dazu(listen.haupt_liste(), "große Liste")
        dazu(listen.darvas_liste(), "Darvas-Liste")
        dazu(listen.weitere_listen([listen.DRITTE_DATEI]), "dritte Liste")
        dazu(listen.weitere_listen([listen.VIERTE_DATEI]), "vierte Liste")
        dazu(listen.einzel_ticker(), "einzeln überwacht")
    except Exception:  # noqa: BLE001, ohne Listen fehlt nur der Vermerk
        pass
    return raus


# ---------------------------------------------------------------------------
# Auswahl und Text
# ---------------------------------------------------------------------------

def _f(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def kandidaten(tabelle_zeilen: dict, quotes: dict) -> tuple:
    """(Kandidaten, Zaehler). Kandidat ist, wer Gap, Kurs und Boersenwert
    erfuellt; das Volumen kommt danach."""
    raus = []
    zaehler = {"mit_vorboerse": 0, "gap": 0, "kurs": 0, "marktkap": 0}
    for sym, z in tabelle_zeilen.items():
        q = quotes.get(sym)
        if not q:
            continue
        pre = _f(q.get("preMarketPrice"))
        vortag = _f(q.get("regularMarketPrice")) or _f(z.get("kurs"))
        if not pre or not vortag:
            continue
        zaehler["mit_vorboerse"] += 1
        gap = (pre / vortag - 1.0) * 100.0
        if gap < GAP_MIN_PCT:
            continue
        zaehler["gap"] += 1
        if pre < KURS_MIN:
            zaehler["kurs"] += 1
            continue
        mk = _f(z.get("marktkap_mrd"))
        if mk is None or mk < MARKTKAP_MIN_MRD:
            zaehler["marktkap"] += 1
            continue
        raus.append({"ticker": sym, "kurs": pre, "vortag": vortag, "gap_pct": gap, "zeile": z, "quote": q})
    return raus, zaehler


def volumen_pruefen(kands: list, vorboerse: dict) -> tuple:
    """(erfuellt, zu wenig Volumen, ohne Volumen). vorboerse: {Kuerzel: {volumen, kurs}}."""
    gut, wenig, ohne = [], [], []
    for k in kands:
        v = vorboerse.get(k["ticker"])
        schnitt = _f(k["zeile"].get("volumen_50"))
        if not v or not schnitt:
            ohne.append(k)
            continue
        k = dict(k, vol=v["volumen"], vol_pct=(v["volumen"] / schnitt - 1.0) * 100.0,
                 dollar=v["volumen"] * k["kurs"])
        (gut if v["volumen"] >= VOL_MIN_ANTEIL * schnitt else wenig).append(k)
    gut.sort(key=lambda k: k["dollar"], reverse=True)
    return gut, wenig, ohne


def _wachstum(z, praefix, wort) -> str:
    """'Umsatz zum Vorjahresquartal plus 23 Prozent, davor plus 18 und plus 15 Prozent'."""
    import nachschlagen as ns
    werte = [_f(z.get(f"{praefix}_q_vj_pct")), _f(z.get(f"{praefix}_q1_vj_pct")), _f(z.get(f"{praefix}_q2_vj_pct"))]
    if werte[0] is None:
        return f"{wort} zum Vorjahresquartal unbekannt"
    satz = f"{wort} zum Vorjahresquartal {ns.prozent(werte[0])}"
    davor = [w for w in werte[1:] if w is not None]
    if davor:
        satz += ", davor " + " und ".join(ns.prozent(w).replace(" Prozent", "") for w in davor) + " Prozent"
    return satz


def firmen_name(k: dict) -> str:
    """Der Firmenname ohne Klammern: zuerst Yahoos Langname, sonst der Name
    der Nachttabelle ohne Wertpapierzusatz."""
    import nachschlagen as ns
    q, z = k.get("quote") or {}, k.get("zeile") or {}
    name = str(q.get("longName") or "").strip() or ns.firmenname(z.get("name")) or str(q.get("shortName") or "")
    name = re.sub(r"\s*\([^)]*\)", "", name)
    name = re.sub(r"\s+", " ", name.replace("(", " ").replace(")", " ")).strip(" ,;")
    return name or k["ticker"]


def abstand_hoch(k: dict):
    """Abstand des vorboerslichen Kurses zum 52-Wochen-Hoch in Prozent:
    die Nachttabelle kennt den Abstand zum Schluss des Vortags
    (abst_hoch_1j_pct), umgerechnet auf den vorboerslichen Kurs."""
    z = k.get("zeile") or {}
    abst, schluss = _f(z.get("abst_hoch_1j_pct")), _f(z.get("kurs"))
    if abst is None or not schluss:
        return None
    return ((1.0 + abst / 100.0) * (k["kurs"] / schluss) - 1.0) * 100.0


def absatz(nr: int, k: dict, listen_map: dict, news: list) -> str:
    """Ein Absatz je Aktie, Strichpunkt zwischen den Angaben, Beistrich
    innerhalb (Meldungsformat), ohne Klammern und Gedankenstrich."""
    import nachschlagen as ns
    import volumen
    z = k["zeile"]
    name = firmen_name(k)
    zeilen = [f"{nr}. {k['ticker']}, {name}; Kurs vorbörslich {ns.zahl(k['kurs'], 2)} Dollar; "
              f"Gap {ns.prozent(k['gap_pct'], 1)}"]
    zeilen.append(f"Vorbörsliches Volumen {ns.zahl(k['vol'])} Stück, {volumen.prozent_text(k['vol_pct'], 'Prozent')}; "
                  f"vorbörslich gehandelt für {ns._dollar_menge(k['dollar'])}")
    rs = _f(z.get("rs"))
    zeilen.append(f"{_wachstum(z, 'umsatz', 'Umsatz')}; {_wachstum(z, 'eps', 'Gewinn je Aktie')}; "
                  f"RS {ns.zahl(rs) if rs is not None else 'unbekannt'}")
    abst = abstand_hoch(k)
    if abst is not None:
        lage = ("über dem bisherigen 52-Wochen-Hoch, um " + ns.zahl(abst, 1) + " Prozent" if round(abst, 1) > 0
                else ("auf dem 52-Wochen-Hoch" if round(abst, 1) == 0
                      else f"{ns.zahl(-abst, 1)} Prozent unter dem 52-Wochen-Hoch"))
    else:
        lage = "Abstand zum 52-Wochen-Hoch unbekannt"
    mk = _f(z.get("marktkap_mrd"))
    zeilen.append(f"{lage}; Börsenwert {ns._dollar_menge(mk * 1e9) if mk else 'unbekannt'}; "
                  f"Sektor {z.get('sektor') or 'unbekannt'}")
    auf = listen_map.get(k["ticker"]) or []
    termin = z.get("termin_datum")
    lage_t = {"vorboerslich": "vorbörslich", "nachboerslich": "nachbörslich",
              "im_handel": "während des Handels"}.get(str(z.get("termin_lage") or ""), "")
    termin_text = (f"Zahlen am {ns.datum_text(termin)}" + (f", {lage_t}" if lage_t else "")) if termin else "Zahlentermin unbekannt"
    zeilen.append(("auf der Wochenliste: " + ", ".join(auf) if auf else "auf keiner Wochenliste") + f"; {termin_text}")
    if news:
        for z_utc, anbieter, titel in news:
            w = z_utc.astimezone(berichte.WIEN)
            zeilen.append(f"Nachricht {w:%d.%m.} {w:%H:%M} Uhr" + (f", {anbieter}" if anbieter else "") + f": {titel}")
    else:
        zeilen.append("Keine Schlagzeile seit dem Schluss des Vortags")
    return "\n".join(zeilen)


def bericht_bauen(jetzt, gut, wenig, ohne, zaehler, listen_map, news_map) -> tuple:
    """(Titel, Absaetze)."""
    import nachschlagen as ns
    t_ny = ny(jetzt)
    t_wien = t_ny.astimezone(berichte.WIEN)
    titel = (f"Gap-Ups vorbörslich: {len(gut)} Aktie" + ("n" if len(gut) != 1 else "")
             if gut else "Gap-Ups vorbörslich: keine Aktie erfüllt die Kriterien")
    kopf = (f"Stand {t_wien:%H:%M} Uhr Wiener Zeit, {t_ny:%H:%M} Uhr in New York; ganzer US-Markt. "
            f"Kriterien: Gap ab {ns.zahl(GAP_MIN_PCT)} Prozent zum Schluss des Vortags; vorbörsliches Volumen "
            f"mindestens minus 95 Prozent über dem 50-Tage-Schnitt; Kurs ab {ns.zahl(KURS_MIN)} Dollar; "
            f"Börsenwert ab 700 Millionen Dollar; sortiert nach vorbörslichem Dollarvolumen.")
    absaetze = [kopf]
    if gut:
        for i, k in enumerate(gut, 1):
            absaetze.append(absatz(i, k, listen_map, news_map.get(k["ticker"]) or []))
    else:
        absaetze.append("Keine Aktie erfüllt heute die Kriterien.")
    rest = (f"Gezählt: {ns.zahl(zaehler['mit_vorboerse'])} Aktien mit vorbörslichem Kurs; "
            f"{ns.zahl(zaehler['gap'])} mit Gap ab {ns.zahl(GAP_MIN_PCT)} Prozent; davon "
            f"{ns.zahl(zaehler['kurs'])} unter {ns.zahl(KURS_MIN)} Dollar, {ns.zahl(zaehler['marktkap'])} unter "
            f"700 Millionen Dollar Börsenwert und {ns.zahl(len(wenig))} mit zu wenig vorbörslichem Volumen.")
    absaetze.append(rest)
    if ohne:
        absaetze.append("Ohne vorbörsliches Volumen von Nasdaq, deshalb nicht prüfbar: "
                        + ", ".join(k["ticker"] for k in ohne) + ".")
    return titel, absaetze


def ohne_gesperrte(zeilen: dict, melder=print) -> dict:
    """DIE BLACKLIST (Gerhard, 30.09.2026, Antworten 8 und 13): Gesperrte Aktien
    fallen vor dem ersten Abruf heraus; ins Protokoll nur die Zahl, das
    Protokoll ist oeffentlich."""
    import blacklist
    raus = blacklist.ohne_je_kuerzel(zeilen)
    if blacklist.fehler():
        melder(f"  ACHTUNG: Blacklist nicht lesbar ({blacklist.fehler()}); es ist keine Aktie gesperrt.")
    elif len(raus) != len(zeilen):
        melder(f"  Blacklist: {len(zeilen) - len(raus)} Aktie(n) gesperrt.")
    return raus


def bauen(jetzt=None, tabelle_pfad=None, melder=print) -> tuple:
    """Rechnet den Bericht; (Titel, Absaetze)."""
    jetzt = jetzt or datetime.now(timezone.utc)
    df = tabelle_laden(tabelle_pfad)
    zeilen = {}
    for z in df.to_dict("records"):
        t = str(z.get("ticker") or "").upper().strip()
        if t:
            zeilen[t] = z
    zeilen = ohne_gesperrte(zeilen, melder)
    t0 = time.time()
    quotes = yahoo_vorboerse(sorted(zeilen), melder)
    melder(f"  Yahoo: {len(quotes)} von {len(zeilen)} Aktien in {time.time() - t0:.1f} s.")
    kands, zaehler = kandidaten(zeilen, quotes)
    melder(f"  Kandidaten nach Gap, Kurs und Börsenwert: {len(kands)}.")
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=6) as pool:
        ergebnisse = list(pool.map(lambda k: (k["ticker"], nasdaq_vorboerse(k["ticker"])), kands))
    vorboerse = {t: v for t, v in ergebnisse if v}
    melder(f"  Nasdaq: Volumen für {len(vorboerse)} von {len(kands)} in {time.time() - t0:.1f} s.")
    gut, wenig, ohne = volumen_pruefen(kands, vorboerse)
    # Schlagzeilen seit dem Schluss des Vortags, 16:00 New York am letzten Werktag
    tag = ny(jetzt).date() - timedelta(days=1)
    while tag.weekday() >= 5:
        tag -= timedelta(days=1)
    seit = datetime(tag.year, tag.month, tag.day, 16, 0, tzinfo=NY).astimezone(timezone.utc)
    news_map = {k["ticker"]: schlagzeilen(k["ticker"], seit) for k in gut}
    return bericht_bauen(jetzt, gut, wenig, ohne, zaehler, listen_je_aktie(), news_map)


# ---------------------------------------------------------------------------
# Selbsttest (ohne Netz)
# ---------------------------------------------------------------------------

def selbsttest() -> int:
    fehler = []

    def p(name, ok, zusatz=""):
        print(f"  {'ok  ' if ok else 'FEHL'} {name}" + (f"; {zusatz}" if zusatz else ""))
        if not ok:
            fehler.append(name)

    print("GAP-UP-BERICHT, Selbsttest")
    u = lambda *a: datetime(*a, tzinfo=timezone.utc)  # noqa: E731
    # Wann: 09:10 New York, im Sommer 13:10 UTC, im Winter 14:10 UTC
    p("Fenster: 09:10 New York im Sommer", im_fenster(u(2026, 10, 7, 13, 10)) and not im_fenster(u(2026, 10, 7, 13, 9)))
    p("Fenster: bis 09:29, um 09:30 nicht mehr", im_fenster(u(2026, 10, 7, 13, 29)) and not im_fenster(u(2026, 10, 7, 13, 30)))
    p("Fenster: in der Umstellwoche 14:10 Wien, also 09:10 New York (13:10 UTC)",
      im_fenster(u(2026, 10, 27, 13, 10)) and u(2026, 10, 27, 13, 10).astimezone(berichte.WIEN).hour == 14)
    p("Fenster: im Winter 14:10 UTC", im_fenster(u(2026, 11, 4, 14, 10)) and not im_fenster(u(2026, 11, 4, 13, 10)))
    p("Fenster: nicht am Samstag", not im_fenster(u(2026, 10, 10, 13, 15)))
    heute = berichte.bericht("gapup", "x", ["y"], u(2026, 10, 7, 13, 10))
    p("Einmal je Tag", heute_schon([heute], u(2026, 10, 7, 13, 20)) and not heute_schon([heute], u(2026, 10, 8, 13, 10)))
    p("Faellig ausserhalb des Fensters: nein", faellig(u(2026, 10, 7, 12, 0), token="")[0] is False)

    # Nasdaq deuten, mit der echten Form vom 01.10.2026
    j = {"data": {"infoTable": {"rows": [{"consolidated": "$214.1 +30.73 (+16.76%)", "volume": "2,593,192"}]}}}
    p("Nasdaq: Volumen und Kurs", nasdaq_deuten(j) == {"volumen": 2593192, "kurs": 214.1}, str(nasdaq_deuten(j)))
    p("Nasdaq: leere Antwort ist None", nasdaq_deuten({"data": None}) is None and nasdaq_deuten({}) is None)

    # Auswahl
    zeilen = {
        "AAA": {"ticker": "AAA", "name": "Alpha Inc. - Common Stock (Ireland)", "kurs": 100.0, "marktkap_mrd": 5.0,
                "volumen_50": 1_000_000, "rs": 91, "abst_hoch_1j_pct": -9.0909, "sektor": "Technology",
                "umsatz_q_vj_pct": 23.4, "umsatz_q1_vj_pct": 18.0, "umsatz_q2_vj_pct": 15.0,
                "eps_q_vj_pct": 40.0, "termin_datum": "2026-10-07", "termin_lage": "vorboerslich"},
        "BBB": {"ticker": "BBB", "name": "Beta", "kurs": 10.0, "marktkap_mrd": 2.0, "volumen_50": 500_000},
        "CCC": {"ticker": "CCC", "name": "Gamma", "kurs": 50.0, "marktkap_mrd": 0.5, "volumen_50": 500_000},
        "DDD": {"ticker": "DDD", "name": "Delta", "kurs": 40.0, "marktkap_mrd": 1.0, "volumen_50": 2_000_000},
        "EEE": {"ticker": "EEE", "name": "Epsilon", "kurs": 30.0, "marktkap_mrd": 1.0, "volumen_50": 100_000},
        "FFF": {"ticker": "FFF", "name": "Phi", "kurs": 30.0, "marktkap_mrd": 1.0, "volumen_50": 100_000},
    }
    quotes = {"AAA": {"preMarketPrice": 108.0, "regularMarketPrice": 100.0},
              "BBB": {"preMarketPrice": 11.0, "regularMarketPrice": 10.0},
              "CCC": {"preMarketPrice": 56.0, "regularMarketPrice": 50.0},
              "DDD": {"preMarketPrice": 44.0, "regularMarketPrice": 40.0},
              "EEE": {"preMarketPrice": 31.0, "regularMarketPrice": 30.0},
              "FFF": {"preMarketPrice": 33.0, "regularMarketPrice": 30.0}}
    kands, zaehler = kandidaten(zeilen, quotes)
    p("Auswahl: Gap ab 5, Kurs ab 15, Boersenwert ab 0,7 Mrd",
      sorted(k["ticker"] for k in kands) == ["AAA", "DDD", "FFF"]
      and zaehler == {"mit_vorboerse": 6, "gap": 5, "kurs": 1, "marktkap": 1}, str(zaehler))
    vb = {"AAA": {"volumen": 80_000, "kurs": 108.0}, "DDD": {"volumen": 90_000, "kurs": 44.0}}
    gut, wenig, ohne = volumen_pruefen(kands, vb)
    p("Volumen: ab minus 95 Prozent ueber dem Schnitt, ohne Nasdaq nicht pruefbar",
      [k["ticker"] for k in gut] == ["AAA"] and [k["ticker"] for k in wenig] == ["DDD"]
      and [k["ticker"] for k in ohne] == ["FFF"])
    p("Volumen in IBD-Sprache: 80.000 bei 1 Mio Schnitt sind minus 92", round(gut[0]["vol_pct"]) == -92)
    vb["DDD"] = {"volumen": 400_000, "kurs": 44.0}
    gut2, _w, _o = volumen_pruefen(kands, vb)
    p("Sortierung nach vorboerslichem Dollarvolumen", [k["ticker"] for k in gut2] == ["DDD", "AAA"],
      str([(k["ticker"], k["dollar"]) for k in gut2]))

    news = {"AAA": [(u(2026, 10, 7, 11, 45), "Barrons.com", "Alpha raises guidance")]}
    titel, absaetze = bericht_bauen(u(2026, 10, 7, 13, 10), gut, wenig, ohne, zaehler,
                                    {"AAA": ["große Liste"]}, news)
    text = "\n".join(absaetze)
    p("Titel nennt die Zahl", titel == "Gap-Ups vorbörslich: 1 Aktie", titel)
    p("Kopf nennt Zeit und Kriterien in IBD-Sprache",
      absaetze[0].startswith("Stand 15:10 Uhr Wiener Zeit, 09:10 Uhr in New York; ganzer US-Markt.")
      and "mindestens minus 95 Prozent über dem 50-Tage-Schnitt" in absaetze[0], absaetze[0])
    a1 = absaetze[1]
    p("Absatz: Nummer, Kuerzel, Name, Kurs und Gap", a1.startswith("1. AAA, Alpha Inc.; Kurs vorbörslich 108,00 Dollar; Gap plus 8,0 Prozent"), a1.split("\n")[0])
    p("Absatz: Volumen in IBD-Sprache und Dollarvolumen",
      "Vorbörsliches Volumen 80.000 Stück, minus 92 Prozent über dem 50-Tage-Schnitt; vorbörslich gehandelt für 8,6 Millionen Dollar" in a1,
      a1.split("\n")[1])
    p("Absatz: Wachstum je Quartal und RS",
      "Umsatz zum Vorjahresquartal plus 23 Prozent, davor plus 18 und plus 15 Prozent" in a1 and "RS 91" in a1, a1.split("\n")[2])
    p("Absatz: Abstand, Boersenwert, Sektor",
      "1,8 Prozent unter dem 52-Wochen-Hoch; Börsenwert 5,0 Milliarden Dollar; Sektor Technology" in a1, a1.split("\n")[3])
    p("Absatz: Wochenliste, Zahlentermin, Schlagzeile",
      "auf der Wochenliste: große Liste; Zahlen am 07.10.2026, vorbörslich" in a1
      and "Nachricht 07.10. 13:45 Uhr, Barrons.com: Alpha raises guidance" in a1, a1)
    p("Zaehlung und nicht pruefbare stehen am Ende",
      "Ohne vorbörsliches Volumen von Nasdaq, deshalb nicht prüfbar: FFF." in absaetze[-1]
      and "1 mit zu wenig vorbörslichem Volumen" in absaetze[-2], absaetze[-2])
    titel0, abs0 = bericht_bauen(u(2026, 10, 7, 13, 10), [], [], [], zaehler, {}, {})
    p("Ohne Treffer: ehrlich im Bericht", titel0 == "Gap-Ups vorbörslich: keine Aktie erfüllt die Kriterien"
      and abs0[1] == "Keine Aktie erfüllt heute die Kriterien.")
    p("Keine Klammer, kein Gedankenstrich, kein senkrechter Strich",
      not re.search(r"[()–—|]", text + titel), re.findall(r"[()–—|]", text)[:5])
    lm = listen_je_aktie()
    import listen as _li
    erster = _li.haupt_liste()[:1]
    p("Wochenlisten: die Paare aus Kuerzel und Firma werden zu Kuerzeln",
      not erster or "große Liste" in lm.get(str(erster[0][0]).upper(), []), str(erster))
    print("\nAlles bestanden." if not fehler else f"\n{len(fehler)} Fehler.")
    return 1 if fehler else 0


def main() -> int:
    a = sys.argv[1:]
    if "--selbsttest" in a:
        return selbsttest()
    if "--faellig" in a:
        ja, grund = faellig()
        print(f"Gap-Up-Bericht: {'fällig' if ja else 'nicht fällig'} ({grund}).")
        ausgabe = os.environ.get("GITHUB_OUTPUT")
        if ausgabe:
            with open(ausgabe, "a", encoding="utf-8") as f:
                f.write(f"noetig={'ja' if ja else 'nein'}\n")
        return 0
    if "--bauen" in a or "--jetzt" in a:
        if "--bauen" in a:
            ja, grund = faellig()
            if not ja:
                print(f"Gap-Up-Bericht nicht fällig: {grund}.")
                return 0
        if "--trocken" in a:
            os.environ[berichte.TROCKEN_ENV] = "1"
        pfad = a[a.index("--tabelle") + 1] if "--tabelle" in a else None
        titel, absaetze = bauen(tabelle_pfad=pfad)
        print(titel)
        for x in absaetze:
            print(x)
            print()
        ok = berichte.ablegen(ART, titel, absaetze)
        return 0 if ok else 1
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
