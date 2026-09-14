#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KENNZAHLEN AUS DEM KONSENS (Etappe 5, Gerhards Entscheidung 9)
==============================================================
Gerhard, 13.09.2026, woertlich: "BEIDES. Forward-KGV und erwartetes Wachstum
aus dem eingefrorenen Yahoo-Konsens, EPS-Konsens aus dem Nasdaq-Kalender (die
Felder epsForecast, noOfEsts und lastYearEPS holst Du ohnehin schon und
wirfst sie weg), Revisionen und Herauf-Herabstufungen nur fuer die
Wochenliste."

Alles ist Anzeige, nichts filtert (Grundsatz der Entscheidungen 1 bis 13).
Die Werte liegen wie die Analystenwerte im PRIVATEN Datenrepo heliot-daten
(scanner_analysten.parquet); die App liest sie nur mit DATEN_LESE_TOKEN.

DREI QUELLEN
  1. Der eingefrorene Yahoo-Konsens (konsens_einfrieren.py, zweimal je
     Handelstag): je Firma und Periode (0q laufendes Quartal, +1q naechstes,
     0y laufendes Geschaeftsjahr, +1y naechstes) Mittel, Tief, Hoch und
     Analystenzahl fuer Umsatz und Gewinn je Aktie, seit 15.09.2026 auch der
     Vorjahreswert, gegen den Yahoo sein Wachstum rechnet (yearAgoEps,
     yearAgoRevenue). Der Scanner-Bau liest die juengsten Laeufe; je Firma
     gilt der juengste Lauf, der sie fuehrt.
  2. Der Nasdaq-Kalender der naechsten Tage: epsForecast, noOfEsts,
     lastYearEPS, lastYearRptDt und fiscalQuarterEnding je Termin. Gemessen
     am 14.09.2026: Betraege als "$0.84", negative in Klammern "($0.26)",
     fehlende als "N/A" oder leer; noOfEsts steht auch ohne epsForecast
     ("3" bei LEN.B am 16.09.2026).
  3. Nur fuer die Wochenliste, ein Abruf je Aktie bei Yahoo (Module
     earningsTrend und upgradeDowngradeHistory in einer Anfrage): die Zahl
     der Anhebungen und Senkungen des EPS-Konsens in 7 und 30 Tagen je
     Periode, der EPS-Konsens heute und vor 7, 30, 60 und 90 Tagen, dazu die
     Herauf- und Herabstufungen samt Kursziel.

WAS GERECHNET WIRD
  Forward-KGV   Schlusskurs der Nacht geteilt durch das EPS-Mittel des
                naechsten Geschaeftsjahres (+1y), wie Finviz "Forward P/E";
                daneben das KGV auf das laufende Geschaeftsjahr (0y). Nur bei
                einem Konsens in Dollar und positivem EPS: Auslaendische
                Firmen melden ihren Konsens oft in ihrer Waehrung (Lauf vom
                11.09.2026: 709 Zeilen in CAD, 527 in EUR, 517 in JPY, 964
                ohne Angabe), und ein Hinterlegungsschein bildet nicht eine
                Aktie ab.
  Wachstum      je Periode Mittel gegen Vorjahreswert in Prozent, nur bei
                positivem Vorjahreswert. Fuer +1y ist der Vorjahreswert das
                Mittel des laufenden Jahres; so rechnet auch Yahoo (gemessen
                an NVDA, KRYS und ANF am 14.09.2026: yearAgoEps von +1y ist
                das Mittel von 0y). Die Vorjahreswerte fuer 0q, +1q und 0y
                bringt erst der erweiterte Einfrier-Lauf.
  Revisionen    wie geliefert. Yahoo zaehlt teils widerspruechlich (NVDA am
                14.09.2026, laufendes Quartal: drei Senkungen in 7 Tagen,
                eine in 30); die Anzeige nennt die Zahlen und rechnet nichts
                daraus. Der Schluessel heisst bei Yahoo "downLast7Days" mit
                grossem D, die yfinance-Doku schreibt "downLast7days"; beide
                werden gelesen.
  Stufen        Heraufstufungen (action up), Herabstufungen (down),
                Erstbewertungen (init), angehobene und gesenkte Kursziele
                (priceTargetAction Raises und Lowers) in den Fenstern aus
                config.py, dazu die juengsten Einstufungen.

DROSSEL (Befund 02.09.2026 in konsens_einfrieren.py): yfinance verbirgt
HTTP-Fehler und liefert still Leeres. Deshalb werden die Meldungen des
yfinance-Protokolls je Abfrage mitgelesen; Drossel-Meldungen fuehren zu
Warten und Wiederholen, ein leeres Ergebnis ohne erkennbaren Grund gilt als
Fehler und nie als "keine Revisionen". Die Muster sind dieselben wie dort;
der Selbsttest prueft das.

KEINE VERNETZUNG: Das Modul sendet nichts und schreibt keine Datei, die
Waechter, Scanner-Mappe oder Alarmbot lesen.

Aufruf:
  python kennzahlen_konsens.py --selbsttest
"""

import argparse
import gzip
import json
import logging
import math
import os
import sys
import threading
import time
from datetime import date, datetime, timezone

from config import CFG

KK = CFG["konsens_kennzahlen"]

# Yahoos Periodenkennung und unsere Kurzform in den Feldnamen.
PERIODEN = (("0q", "0q"), ("+1q", "1q"), ("0y", "0y"), ("+1y", "1y"))
# Yahoos Namen (Current Qtr., Next Qtr., Current Year, Next Year); das
# Nachschlagen nennt die Perioden lieber nach ihrem Ende.
PERIODE_NAME = {"0q": "Aktuelles Quartal", "1q": "Nächstes Quartal", "0y": "Aktuelles Geschäftsjahr",
                "1y": "Nächstes Geschäftsjahr"}
STUFEN_FENSTER = tuple(int(n) for n in KK["stufen_fenster_tage"])

DROSSEL_MUSTER = ("429", "invalid crumb", "unauthorized", "too many requests", "rate-limit", "rate limit")
LEGITIM_MUSTER = ("no fundamentals data found", "quote not found")


def _konsens_felder():
    f = ["konsens_stand", "konsens_waehrung", "konsens_termin", "konsens_fwd_kgv", "konsens_kgv_0y"]
    for _y, k in PERIODEN:
        f += [f"konsens_ende_{k}",
              f"konsens_eps_{k}", f"konsens_eps_tief_{k}", f"konsens_eps_hoch_{k}", f"konsens_eps_vj_{k}",
              f"konsens_eps_wachstum_{k}_pct", f"konsens_eps_analysten_{k}",
              f"konsens_umsatz_{k}", f"konsens_umsatz_tief_{k}", f"konsens_umsatz_hoch_{k}", f"konsens_umsatz_vj_{k}",
              f"konsens_umsatz_wachstum_{k}_pct", f"konsens_umsatz_analysten_{k}"]
    return tuple(f)


def _revision_felder():
    f = ["rev_stand"]
    for _y, k in PERIODEN:
        f += [f"rev_hoch_7t_{k}", f"rev_hoch_30t_{k}", f"rev_runter_7t_{k}", f"rev_runter_30t_{k}",
              f"rev_eps_jetzt_{k}", f"rev_eps_7t_{k}", f"rev_eps_30t_{k}", f"rev_eps_60t_{k}", f"rev_eps_90t_{k}"]
    for n in STUFEN_FENSTER:
        f += [f"stufen_hoch_{n}t", f"stufen_runter_{n}t", f"stufen_neu_{n}t",
              f"stufen_ziel_rauf_{n}t", f"stufen_ziel_runter_{n}t"]
    f.append("stufen_liste")
    return tuple(f)


KONSENS_FELDER = _konsens_felder()
TERMIN_KONSENS_FELDER = ("termin_konsens_datum", "termin_quartal", "termin_eps_konsens", "termin_eps_schaetzungen",
                         "termin_eps_vorjahr", "termin_vorjahr_datum")
REVISION_FELDER = _revision_felder()


# ---------------------------------------------------------------------------
# Kleine Helfer
# ---------------------------------------------------------------------------

def _zahl(x):
    """float oder None; Yahoos {"raw": ...} wird ausgepackt, NaN wird None."""
    if isinstance(x, dict):
        x = x.get("raw")
    if isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _ganz(x):
    v = _zahl(x)
    return int(round(v)) if v is not None else None


def _erster(d, *schluessel):
    """Der erste Schluessel mit einer Zahl."""
    for s in schluessel:
        v = _zahl((d or {}).get(s))
        if v is not None:
            return v
    return None


def schluessel(ticker):
    """Einheitliche Schreibweise: Das SEC-Register schreibt BRK-B, das
    Universum BRK.B, der Nasdaq-Screener BRK/B."""
    return str(ticker or "").strip().upper().replace("-", ".").replace("/", ".")


def wachstum_pct(neu, alt):
    """Veraenderung in Prozent, nur bei positiver Basis; eine Stelle."""
    neu, alt = _zahl(neu), _zahl(alt)
    if neu is None or alt is None or alt <= 0:
        return None
    return round((neu / alt - 1.0) * 100.0, 1)


# ---------------------------------------------------------------------------
# 1. Eingefrorener Yahoo-Konsens
# ---------------------------------------------------------------------------

def schnappschuesse_lesen(pfade):
    """({Ticker: {"stand": zeit_utc, "zeilen": {Periode: Zeile}}}, Befund).
    Die Dateien heissen nach ihrer Kennung (2026-09-11_1930Z.jsonl.gz) und
    werden in dieser Reihenfolge gelesen; je Firma gilt der juengste Lauf,
    der sie fuehrt. Eine unlesbare Datei faellt ganz weg, auch wenn sie bis
    zum Fehler Zeilen lieferte."""
    je, gelesen, unlesbar = {}, [], []
    perioden = dict(PERIODEN)
    for pfad in sorted(pfade or [], key=lambda p: os.path.basename(str(p))):
        teil = {}
        try:
            with gzip.open(pfad, "rt", encoding="utf-8") as f:
                for zeile in f:
                    zeile = zeile.strip()
                    if not zeile:
                        continue
                    d = json.loads(zeile)
                    t = schluessel(d.get("ticker"))
                    per = d.get("periode")
                    if not t or per not in perioden:
                        continue
                    e = teil.setdefault(t, {"stand": d.get("zeit_utc"), "zeilen": {}})
                    e["zeilen"][per] = d
                    if str(d.get("zeit_utc") or "") > str(e.get("stand") or ""):
                        e["stand"] = d.get("zeit_utc")
        except (OSError, ValueError, EOFError) as fehler:
            unlesbar.append(f"{os.path.basename(str(pfad))}: {type(fehler).__name__}")
            continue
        je.update(teil)
        gelesen.append(os.path.basename(str(pfad)))
    staende = [e["stand"] for e in je.values() if e.get("stand")]
    return je, {"dateien": gelesen, "unlesbar": unlesbar, "firmen": len(je),
                "neuester": max(staende) if staende else None, "aeltester": min(staende) if staende else None}


def konsens_werte(eintrag, kurs=None):
    """Die Felder KONSENS_FELDER einer Firma aus ihrem Eintrag in
    schnappschuesse_lesen und dem Schlusskurs der Nacht."""
    raus = dict.fromkeys(KONSENS_FELDER)
    zeilen = (eintrag or {}).get("zeilen") or {}
    if not zeilen:
        return raus
    raus["konsens_stand"] = eintrag.get("stand")
    for y, _k in PERIODEN:
        z = zeilen.get(y) or {}
        if not raus["konsens_waehrung"] and z.get("waehrung"):
            raus["konsens_waehrung"] = str(z["waehrung"]).strip().upper() or None
        if not raus["konsens_termin"] and z.get("naechster_termin"):
            raus["konsens_termin"] = str(z["naechster_termin"])[:10]
    for y, k in PERIODEN:
        z = zeilen.get(y) or {}
        raus[f"konsens_ende_{k}"] = (str(z["periodenende"])[:10] if z.get("periodenende") else None)
        for art, avg, vj_feld in (("eps", "eps_avg", "eps_vorjahr"), ("umsatz", "umsatz_avg", "umsatz_vorjahr")):
            mittel = _zahl(z.get(avg))
            vj = _zahl(z.get(vj_feld))
            if vj is None and k == "1y":
                # Yahoo rechnet +1y gegen das Mittel des laufenden Jahres.
                vj = _zahl((zeilen.get("0y") or {}).get(avg))
            raus[f"konsens_{art}_{k}"] = mittel
            raus[f"konsens_{art}_tief_{k}"] = _zahl(z.get(f"{art}_low"))
            raus[f"konsens_{art}_hoch_{k}"] = _zahl(z.get(f"{art}_high"))
            raus[f"konsens_{art}_vj_{k}"] = vj
            raus[f"konsens_{art}_wachstum_{k}_pct"] = wachstum_pct(mittel, vj)
            raus[f"konsens_{art}_analysten_{k}"] = _ganz(z.get(f"{art}_analysten"))
    return kgv_setzen(raus, kurs)


def kgv_setzen(werte, kurs):
    """Forward-KGV (+1y) und KGV auf das laufende Geschaeftsjahr (0y) in
    werte eintragen, nur bei einem Konsens in Dollar, positivem EPS und
    positivem Kurs; sonst None. Auch fuer die Werte der Vornacht mit dem Kurs
    dieser Nacht."""
    k_ = _zahl(kurs)
    for feld, eps_feld in (("konsens_fwd_kgv", "konsens_eps_1y"), ("konsens_kgv_0y", "konsens_eps_0y")):
        eps = _zahl(werte.get(eps_feld))
        gueltig = (k_ is not None and k_ > 0 and werte.get("konsens_waehrung") == "USD"
                   and eps is not None and eps > 0)
        werte[feld] = round(k_ / eps, 2) if gueltig else None
    return werte


# ---------------------------------------------------------------------------
# 2. Nasdaq-Kalender
# ---------------------------------------------------------------------------

def nasdaq_betrag(s):
    """'$0.84' -> 0.84, '($0.26)' -> -0.26, '$2' -> 2.0, 'N/A' und '' -> None."""
    if s is None:
        return None
    t = str(s).strip()
    if not t or t.upper() in ("N/A", "NA", "--", "-"):
        return None
    negativ = t.startswith("(") and t.endswith(")")
    t = t.strip("()").replace("$", "").replace(",", "").strip()
    v = _zahl(t)
    if v is None:
        return None
    return -abs(v) if negativ else v


def nasdaq_datum(s):
    """'8/27/2025' -> '2025-08-27'; 'N/A' -> None."""
    try:
        return datetime.strptime(str(s or "").strip(), "%m/%d/%Y").date().isoformat()
    except ValueError:
        return None


def kalender_konsens(zeile):
    """Die Felder TERMIN_KONSENS_FELDER ohne das Datum aus einer Zeile des
    Nasdaq-Kalenders."""
    z = zeile or {}
    n = str(z.get("noOfEsts") or "").strip()
    return {"termin_quartal": (str(z.get("fiscalQuarterEnding") or "").strip() or None),
            "termin_eps_konsens": nasdaq_betrag(z.get("epsForecast")),
            "termin_eps_schaetzungen": int(n) if n.isdigit() else None,
            "termin_eps_vorjahr": nasdaq_betrag(z.get("lastYearEPS")),
            "termin_vorjahr_datum": nasdaq_datum(z.get("lastYearRptDt"))}


# ---------------------------------------------------------------------------
# 3. Revisionen und Einstufungen (nur Wochenliste)
# ---------------------------------------------------------------------------

def _tag_aus_epoche(x):
    try:
        return datetime.fromtimestamp(int(x), tz=timezone.utc).date()
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def revisionen_aus(trend, historie, heute):
    """Die Felder REVISION_FELDER aus Yahoos earningsTrend (Liste je Periode)
    und upgradeDowngradeHistory (Liste der Einstufungen). historie None heisst
    nicht abgefragt; eine leere Liste heisst abgefragt, keine Einstufungen."""
    raus = dict.fromkeys(REVISION_FELDER)
    raus["rev_stand"] = heute.isoformat()
    je = {e.get("period"): e for e in (trend or []) if isinstance(e, dict)}
    for y, k in PERIODEN:
        e = je.get(y) or {}
        rv = e.get("epsRevisions") or {}
        tr = e.get("epsTrend") or {}
        for ziel, quellen in ((f"rev_hoch_7t_{k}", ("upLast7days", "upLast7Days")),
                              (f"rev_hoch_30t_{k}", ("upLast30days", "upLast30Days")),
                              (f"rev_runter_7t_{k}", ("downLast7Days", "downLast7days")),
                              (f"rev_runter_30t_{k}", ("downLast30days", "downLast30Days"))):
            v = _erster(rv, *quellen)
            raus[ziel] = int(round(v)) if v is not None else None
        for quelle, ziel in (("current", "jetzt"), ("7daysAgo", "7t"), ("30daysAgo", "30t"),
                             ("60daysAgo", "60t"), ("90daysAgo", "90t")):
            raus[f"rev_eps_{ziel}_{k}"] = _zahl(tr.get(quelle))
    if historie is None:
        return raus
    for n in STUFEN_FENSTER:
        for art in ("hoch", "runter", "neu", "ziel_rauf", "ziel_runter"):
            raus[f"stufen_{art}_{n}t"] = 0
    liste = []
    laengstes = max(STUFEN_FENSTER)
    for h in historie:
        if not isinstance(h, dict):
            continue
        tag = _tag_aus_epoche(h.get("epochGradeDate"))
        if tag is None:
            continue
        alter = (heute - tag).days
        aktion = str(h.get("action") or "").strip().lower()
        ziel_aktion = str(h.get("priceTargetAction") or "").strip().lower()
        for n in STUFEN_FENSTER:
            if 0 <= alter <= n:
                if aktion == "up":
                    raus[f"stufen_hoch_{n}t"] += 1
                elif aktion == "down":
                    raus[f"stufen_runter_{n}t"] += 1
                elif aktion == "init":
                    raus[f"stufen_neu_{n}t"] += 1
                if ziel_aktion == "raises":
                    raus[f"stufen_ziel_rauf_{n}t"] += 1
                elif ziel_aktion == "lowers":
                    raus[f"stufen_ziel_runter_{n}t"] += 1
        if 0 <= alter <= laengstes:
            ziel, vorher = _zahl(h.get("currentPriceTarget")), _zahl(h.get("priorPriceTarget"))
            liste.append({"datum": tag.isoformat(), "firma": (str(h.get("firm") or "").strip() or None),
                          "von": (str(h.get("fromGrade") or "").strip() or None),
                          "zu": (str(h.get("toGrade") or "").strip() or None),
                          "aktion": aktion or None, "ziel_aktion": (str(h.get("priceTargetAction") or "").strip() or None),
                          "ziel": ziel if ziel else None, "ziel_vorher": vorher if vorher else None})
    liste.sort(key=lambda x: x["datum"], reverse=True)
    raus["stufen_liste"] = json.dumps(liste[:int(KK["stufen_liste_anzahl"])], ensure_ascii=False)
    return raus


class YahooDrossel(Exception):
    """Yahoo drosselt die Adresse; warten und wiederholen."""


_MELDUNGEN = threading.local()
_HANDLER = {"da": False}
_BREMSE = {"lock": threading.Lock(), "zuletzt": 0.0}


class _YahooMeldungen(logging.Handler):
    """Sammelt die Meldungen des yfinance-Protokolls je Faden."""

    def emit(self, record):
        liste = getattr(_MELDUNGEN, "liste", None)
        if liste is not None:
            try:
                liste.append(record.getMessage())
            except Exception:  # noqa
                pass


def _meldungen_einhaengen():
    if _HANDLER["da"]:
        return
    lg = logging.getLogger("yfinance")
    lg.addHandler(_YahooMeldungen())
    if lg.level == logging.NOTSET or lg.level > logging.WARNING:
        lg.setLevel(logging.WARNING)
    _HANDLER["da"] = True


def _bremse(rate):
    if not rate or rate <= 0:
        return
    with _BREMSE["lock"]:
        warte = _BREMSE["zuletzt"] + 1.0 / float(rate) - time.monotonic()
        if warte > 0:
            time.sleep(warte)
        _BREMSE["zuletzt"] = time.monotonic()


def ergebnis_pruefen(ticker, trend, historie, meldungen, ausnahme=None):
    """Wirft YahooDrossel bei Drossel-Meldungen oder einer RateLimit-Ausnahme
    (auch wenn Daten kamen), RuntimeError bei einem leeren Ergebnis ohne
    erkennbaren Grund. Ein leeres Ergebnis mit Yahoos 'No fundamentals data'
    oder 'Quote not found' ist legitim."""
    if ausnahme is not None and "RateLimit" in type(ausnahme).__name__:
        raise YahooDrossel(f"{ticker}: {ausnahme}"[:160])
    for m in meldungen or []:
        if any(k in str(m).lower() for k in DROSSEL_MUSTER):
            raise YahooDrossel(f"{ticker}: {str(m)[:120]}")
    if trend or historie:
        return
    if ausnahme is None and any(any(k in str(m).lower() for k in LEGITIM_MUSTER) for m in meldungen or []):
        return
    if ausnahme is None and trend is not None and historie is not None:
        return
    grund = f"{type(ausnahme).__name__}: {ausnahme}"[:120] if ausnahme is not None else "keine Meldung"
    raise RuntimeError(f"{ticker}: leeres Ergebnis ohne erkennbaren Grund ({grund})")


def _ueber_schnittstelle(tk):
    """Rueckfall ueber die oeffentlichen yfinance-Eigenschaften, falls sich das
    Innenleben aendert; kostet zwei Anfragen statt einer."""
    trend = []
    et, er = tk.eps_trend, tk.eps_revisions
    for y, _k in PERIODEN:
        e = {"period": y, "epsTrend": {}, "epsRevisions": {}}
        if et is not None and len(et) and y in et.index:
            e["epsTrend"] = {c: et.loc[y, c] for c in et.columns if c != "currency"}
        if er is not None and len(er) and y in er.index:
            e["epsRevisions"] = {c: er.loc[y, c] for c in er.columns if c != "currency"}
        trend.append(e)
    historie = []
    try:
        ud = tk.upgrades_downgrades
    except Exception:  # noqa  yfinance wirft bei leerer Historie
        ud = None
    if ud is not None and len(ud):
        for idx, zeile in ud.iterrows():
            try:
                epoche = int(idx.timestamp())
            except Exception:  # noqa
                continue
            historie.append({"epochGradeDate": epoche, "firm": zeile.get("Firm"), "toGrade": zeile.get("ToGrade"),
                             "fromGrade": zeile.get("FromGrade"), "action": zeile.get("Action"),
                             "priceTargetAction": zeile.get("priceTargetAction"),
                             "currentPriceTarget": zeile.get("currentPriceTarget"),
                             "priorPriceTarget": zeile.get("priorPriceTarget")})
    return trend, historie


def hole_revisionen(ticker):
    """(trend, historie) einer Aktie von Yahoo in einer Anfrage. Nur im Lauf
    des Scanner-Baus aufrufen."""
    import yfinance as yf
    _meldungen_einhaengen()
    _bremse(KK["rev_abfragen_je_sekunde"])
    _MELDUNGEN.liste = []
    tk = yf.Ticker(str(ticker).strip().upper().replace(".", "-"))
    trend = historie = None
    ausnahme = None
    try:
        roh = tk._analysis._fetch(["earningsTrend", "upgradeDowngradeHistory"])
        ergebnis = (((roh or {}).get("quoteSummary") or {}).get("result") or [None])[0] or {}
        if roh is not None:
            trend = (ergebnis.get("earningsTrend") or {}).get("trend") or []
            historie = (ergebnis.get("upgradeDowngradeHistory") or {}).get("history") or []
    except AttributeError:
        try:
            trend, historie = _ueber_schnittstelle(tk)
        except Exception as e:  # noqa
            ausnahme = e
    except Exception as e:  # noqa
        ausnahme = e
    ergebnis_pruefen(ticker, trend, historie, list(getattr(_MELDUNGEN, "liste", None) or []), ausnahme)
    return trend or [], historie or []


def revisionen_viele(ticker_liste, heute, holen=None, schlafen=None, leise=True):
    """({Ticker: Felder}, {Ticker: Grund}, abgebrochen) fuer die Aktien der
    Wochenliste, eine nach der anderen im Takt der Bremse. Drosselt Yahoo,
    wird gewartet und bis zu dreimal wiederholt; nach KK["rev_notbremse"]
    gedrosselten Aktien in Folge ist fuer die Nacht Schluss."""
    holen = holen or hole_revisionen
    schlafen = schlafen or time.sleep
    raus, fehler, folge = {}, {}, 0
    for i, t in enumerate(ticker_liste, 1):
        versuch = 0
        while True:
            try:
                trend, historie = holen(t)
                raus[t] = revisionen_aus(trend, historie, heute)
                folge = 0
                break
            except YahooDrossel as e:
                versuch += 1
                if versuch <= 3:
                    schlafen(float(KK["rev_warten_s"]) * versuch)
                    continue
                fehler[t] = f"Drossel: {e}"[:160]
                folge += 1
                break
            except Exception as e:  # noqa
                fehler[t] = f"{type(e).__name__}: {e}"[:160]
                break
        if folge >= int(KK["rev_notbremse"]):
            if not leise:
                print(f"  Revisionen: Yahoo drosselt, nach {i} von {len(ticker_liste)} Aktien Schluss fuer heute")
            return raus, fehler, True
    return raus, fehler, False


# ---------------------------------------------------------------------------
# Selbsttest (ohne Netz)
# ---------------------------------------------------------------------------

def _trend_nvda():
    """Die Antwort fuer NVDA vom 14.09.2026 (earningsTrend), gekuerzt auf die
    Felder, die hier gelesen werden."""
    def r(x):
        return {"raw": x, "fmt": str(x)}
    return [
        {"period": "0q", "endDate": "2026-10-31",
         "epsTrend": {"current": r(2.47269), "7daysAgo": r(2.46983), "30daysAgo": r(2.34527),
                      "60daysAgo": r(2.33909), "90daysAgo": r(2.33883), "epsTrendCurrency": "USD"},
         "epsRevisions": {"upLast7days": r(34), "upLast30days": r(35), "downLast30days": r(1),
                          "downLast7Days": r(3), "downLast90days": {}, "epsRevisionsCurrency": "USD"}},
        {"period": "+1q", "endDate": "2027-01-31",
         "epsTrend": {"current": r(2.74328), "30daysAgo": r(2.66044)},
         "epsRevisions": {"upLast7days": r(23), "upLast30days": r(26), "downLast30days": r(9),
                          "downLast7Days": {}, "downLast7days": r(13)}},
        {"period": "0y", "endDate": "2027-01-31", "epsTrend": {}, "epsRevisions": {}},
        {"period": "+1y", "endDate": "2028-01-31",
         "epsTrend": {"current": r(15.56753), "90daysAgo": r(12.67184)},
         "epsRevisions": {"upLast7days": r(41), "upLast30days": r(41), "downLast30days": r(0),
                          "downLast7Days": r(0)}},
    ]


def _zeile(ticker, per, zeit, eps, vj=None, umsatz=None, uvj=None, waehrung="USD", analysten=10, ende="2026-10-31",
           alt=False):
    z = {"zeit_utc": zeit, "ticker": ticker, "periode": per, "periodenende": ende, "umsatz_avg": umsatz,
         "umsatz_low": None if umsatz is None else umsatz * 0.9, "umsatz_high": None if umsatz is None else umsatz * 1.1,
         "umsatz_analysten": analysten, "eps_avg": eps, "eps_low": None if eps is None else eps - 0.1,
         "eps_high": None if eps is None else eps + 0.1, "eps_analysten": analysten, "waehrung": waehrung,
         "naechster_termin": "2026-11-19", "quelle": "yahoo"}
    if not alt:
        z["eps_vorjahr"], z["umsatz_vorjahr"] = vj, uvj
    return z


def selbsttest() -> int:
    import tempfile
    fehler = []

    def p(name, ok, zusatz=""):
        print(f"  {'ok  ' if ok else 'FEHL'} {name}" + (f"; {zusatz}" if zusatz else ""))
        if not ok:
            fehler.append(name)

    print("Kennzahlen aus dem Konsens, Selbsttest (ohne Netz)")
    alle = KONSENS_FELDER + TERMIN_KONSENS_FELDER + REVISION_FELDER
    p("Feldnamen eindeutig", len(alle) == len(set(alle)), f"{len(alle)} Felder")
    try:
        import scanner_daten as sd
        andere = set(sd.ANALYSTEN_FELDER + sd.UEBERRASCHUNG_FELDER + ("ticker", "kursziel_abst_pct", "termin_datum",
                                                                     "termin_lage", "termin_quelle"))
        p("Keine Kollision mit den Feldern der Nachttabelle", not (set(alle) & andere), str(set(alle) & andere))
    except Exception as e:  # noqa
        p("Keine Kollision mit den Feldern der Nachttabelle", False, f"{type(e).__name__}: {e}")
    try:
        import konsens_einfrieren as ke
        p("Drossel- und Legitim-Muster wie in konsens_einfrieren.py",
          DROSSEL_MUSTER == ke.DROSSEL_MUSTER and LEGITIM_MUSTER == ke.LEGITIM_MUSTER)
        p("Die Periodenkennungen sind die des Einfrierens", tuple(y for y, _k in PERIODEN) == ke.PERIODEN)
    except Exception as e:  # noqa
        p("Drossel- und Legitim-Muster wie in konsens_einfrieren.py", False, f"{type(e).__name__}: {e}")

    # Schreibweise
    p("Schreibweise: BRK-B, BRK/B und brk.b werden BRK.B",
      schluessel("BRK-B") == schluessel("BRK/B") == schluessel(" brk.b ") == "BRK.B")

    # --- Schnappschuesse lesen -----------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        def schreibe(name, zeilen, kaputt=False):
            pfad = os.path.join(tmp, name)
            with gzip.open(pfad, "wt", encoding="utf-8") as f:
                for z in zeilen:
                    f.write(json.dumps(z) + "\n")
            if kaputt:
                roh = open(pfad, "rb").read()
                open(pfad, "wb").write(roh[: len(roh) // 2])
            return pfad

        alt = schreibe("2026-09-11_0900Z.jsonl.gz", [
            _zeile("AAA", "0q", "2026-09-11T09:00:41Z", 1.0, alt=True),
            _zeile("AAA", "0y", "2026-09-11T09:00:41Z", 4.0, alt=True),
            _zeile("BRK-B", "0q", "2026-09-11T09:00:42Z", 5.0, vj=4.0, alt=False),
            _zeile("PFX", "-1y", "2026-09-11T09:00:42Z", 1.0)])
        neu = schreibe("2026-09-11_1930Z.jsonl.gz", [
            _zeile("AAA", "0q", "2026-09-11T19:30:43Z", 2.0, vj=1.5),
            _zeile("AAA", "+1y", "2026-09-11T19:30:43Z", 6.0)])
        kaputt = schreibe("2026-09-12_0900Z.jsonl.gz", [_zeile("AAA", "0q", "2026-09-12T09:00:40Z", 9.9)] * 400,
                          kaputt=True)
        je, befund = schnappschuesse_lesen([kaputt, neu, alt])
        p("Schnappschuesse: je Firma gilt der juengste Lauf, der sie fuehrt",
          je["AAA"]["stand"] == "2026-09-11T19:30:43Z" and set(je["AAA"]["zeilen"]) == {"0q", "+1y"}
          and je["BRK.B"]["stand"] == "2026-09-11T09:00:42Z", str({t: e["stand"] for t, e in je.items()}))
        p("Schnappschuesse: unbekannte Perioden fallen weg, die abgebrochene Datei ganz",
          "PFX" not in je and befund["unlesbar"] and befund["dateien"] == ["2026-09-11_0900Z.jsonl.gz",
                                                                            "2026-09-11_1930Z.jsonl.gz"],
          str(befund))
        p("Schnappschuesse: Befund nennt Firmen und juengsten Stand",
          befund["firmen"] == 2 and befund["neuester"] == "2026-09-11T19:30:43Z")
        leer, befund_leer = schnappschuesse_lesen([])
        p("Schnappschuesse: ohne Datei leer", leer == {} and befund_leer["firmen"] == 0)

    # --- Konsenswerte an den Zahlen von NVDA am 14.09.2026 -------------------
    t = "2026-09-14T19:30:00Z"
    nvda = {"stand": t, "zeilen": {
        "0q": _zeile("NVDA", "0q", t, 2.47269, vj=1.3, umsatz=108988683310, uvj=57006000000, analysten=42),
        "+1q": _zeile("NVDA", "+1q", t, 2.74328, vj=1.62, umsatz=124266648840, uvj=68127000000, ende="2027-01-31"),
        "0y": _zeile("NVDA", "0y", t, 9.30456, vj=4.77, umsatz=411292753830, uvj=215938000000, ende="2027-01-31"),
        "+1y": _zeile("NVDA", "+1y", t, 15.56753, vj=9.30456, umsatz=677919776510, uvj=411292753830,
                      ende="2028-01-31")}}
    w = konsens_werte(nvda, kurs=180.0)
    p("Wachstum laufendes Quartal wie Yahoo (EPS 90,2, Umsatz 91,2 Prozent)",
      w["konsens_eps_wachstum_0q_pct"] == 90.2 and w["konsens_umsatz_wachstum_0q_pct"] == 91.2,
      f"{w['konsens_eps_wachstum_0q_pct']}, {w['konsens_umsatz_wachstum_0q_pct']}")
    p("Wachstum naechstes Geschaeftsjahr wie Yahoo (EPS 67,3, Umsatz 64,8 Prozent)",
      w["konsens_eps_wachstum_1y_pct"] == 67.3 and w["konsens_umsatz_wachstum_1y_pct"] == 64.8,
      f"{w['konsens_eps_wachstum_1y_pct']}, {w['konsens_umsatz_wachstum_1y_pct']}")
    p("Forward-KGV und KGV auf das laufende Jahr",
      w["konsens_fwd_kgv"] == round(180.0 / 15.56753, 2) and w["konsens_kgv_0y"] == round(180.0 / 9.30456, 2),
      f"{w['konsens_fwd_kgv']}, {w['konsens_kgv_0y']}")
    p("Stand, Waehrung, Termin, Periodenende, Spanne und Analysten",
      w["konsens_stand"] == t and w["konsens_waehrung"] == "USD" and w["konsens_termin"] == "2026-11-19"
      and w["konsens_ende_1y"] == "2028-01-31" and w["konsens_eps_analysten_0q"] == 42
      and abs(w["konsens_eps_tief_0q"] - 2.37269) < 1e-9)
    # Alte Einfrier-Laeufe ohne Vorjahreswert
    alt_e = {"stand": t, "zeilen": {"0q": _zeile("X", "0q", t, 2.0, alt=True),
                                    "0y": _zeile("X", "0y", t, 8.0, alt=True),
                                    "+1y": _zeile("X", "+1y", t, 10.0, alt=True)}}
    w = konsens_werte(alt_e, kurs=50.0)
    p("Alter Lauf ohne Vorjahreswert: Quartal ohne Wachstum, naechstes Jahr gegen das laufende",
      w["konsens_eps_wachstum_0q_pct"] is None and w["konsens_eps_vj_0q"] is None
      and w["konsens_eps_wachstum_1y_pct"] == 25.0 and w["konsens_eps_vj_1y"] == 8.0)
    p("Fehlende Periode bleibt leer", w["konsens_eps_1q"] is None and w["konsens_ende_1q"] is None)
    # Negativer Vorjahreswert, fremde Waehrung, negativer Konsens
    neg = {"stand": t, "zeilen": {"0q": _zeile("N", "0q", t, 0.2, vj=-0.35),
                                  "+1y": _zeile("N", "+1y", t, -0.5, vj=0.1)}}
    w = konsens_werte(neg, kurs=20.0)
    p("Negativer Vorjahreswert: kein Prozentwert", w["konsens_eps_wachstum_0q_pct"] is None
      and w["konsens_eps_vj_0q"] == -0.35)
    p("Negativer Konsens: Wachstum negativ, kein Forward-KGV",
      w["konsens_eps_wachstum_1y_pct"] == -600.0 and w["konsens_fwd_kgv"] is None, str(w["konsens_eps_wachstum_1y_pct"]))
    eur = {"stand": t, "zeilen": {"+1y": _zeile("E", "+1y", t, 3.0, vj=2.0, waehrung="EUR")}}
    w = konsens_werte(eur, kurs=30.0)
    p("Konsens in Euro: Wachstum ja, Forward-KGV nein", w["konsens_waehrung"] == "EUR"
      and w["konsens_eps_wachstum_1y_pct"] == 50.0 and w["konsens_fwd_kgv"] is None)
    ohne = {"stand": t, "zeilen": {"+1y": _zeile("O", "+1y", t, 3.0, waehrung=None)}}
    p("Konsens ohne Waehrungsangabe: kein Forward-KGV", konsens_werte(ohne, kurs=30.0)["konsens_fwd_kgv"] is None)
    p("Ohne Kurs: kein KGV", konsens_werte(nvda, kurs=None)["konsens_fwd_kgv"] is None)
    p("Ohne Eintrag: alle Felder leer", all(v is None for v in konsens_werte(None, 10.0).values())
      and set(konsens_werte(None).keys()) == set(KONSENS_FELDER))

    # --- Nasdaq-Kalender, Zeilen wie am 14.09.2026 gemessen -----------------
    tcom = kalender_konsens({"lastYearRptDt": "8/27/2025", "lastYearEPS": "$0.90", "time": "time-after-hours",
                             "symbol": "TCOM", "fiscalQuarterEnding": "Jun/2026", "epsForecast": "$0.84",
                             "noOfEsts": "2"})
    p("Kalender: Konsens, Schaetzungen, Vorjahr und Quartal",
      tcom == {"termin_quartal": "Jun/2026", "termin_eps_konsens": 0.84, "termin_eps_schaetzungen": 2,
               "termin_eps_vorjahr": 0.9, "termin_vorjahr_datum": "2025-08-27"}, str(tcom))
    vfs = kalender_konsens({"lastYearRptDt": "9/04/2025", "lastYearEPS": "($0.35)", "epsForecast": "($0.26)",
                            "noOfEsts": "1", "fiscalQuarterEnding": "Jun/2026"})
    p("Kalender: negative Betraege in Klammern",
      vfs["termin_eps_konsens"] == -0.26 and vfs["termin_eps_vorjahr"] == -0.35
      and vfs["termin_vorjahr_datum"] == "2025-09-04", str(vfs))
    htlm = kalender_konsens({"lastYearRptDt": "N/A", "lastYearEPS": "N/A", "epsForecast": "", "noOfEsts": "N/A"})
    p("Kalender: N/A und leere Felder werden leer",
      all(htlm[k] is None for k in ("termin_eps_konsens", "termin_eps_schaetzungen", "termin_eps_vorjahr",
                                     "termin_vorjahr_datum", "termin_quartal")), str(htlm))
    p("Kalender: ganze Dollar und Tausender", nasdaq_betrag("$2") == 2.0 and nasdaq_betrag("$1,234.50") == 1234.5
      and nasdaq_betrag("-$0.12") == -0.12)

    # --- Revisionen und Einstufungen ----------------------------------------
    heute = date(2026, 9, 14)

    def epoche(tag):
        return int(datetime(tag.year, tag.month, tag.day, 15, 0, tzinfo=timezone.utc).timestamp())

    historie = [
        {"epochGradeDate": epoche(date(2026, 9, 12)), "firm": "Piper Sandler", "toGrade": "Overweight", "fromGrade": "",
         "action": "init", "priceTargetAction": "Announces", "currentPriceTarget": 300.0, "priorPriceTarget": 0.0},
        {"epochGradeDate": epoche(date(2026, 9, 5)), "firm": "Rosenblatt", "toGrade": "Buy", "fromGrade": "Buy",
         "action": "main", "priceTargetAction": "Raises", "currentPriceTarget": 390.0, "priorPriceTarget": 350.0},
        {"epochGradeDate": epoche(date(2026, 8, 20)), "firm": "Needham", "toGrade": "Buy", "fromGrade": "Hold",
         "action": "up", "priceTargetAction": "Raises", "currentPriceTarget": 300.0, "priorPriceTarget": 250.0},
        {"epochGradeDate": epoche(date(2026, 7, 1)), "firm": "Mizuho", "toGrade": "Neutral", "fromGrade": "Buy",
         "action": "down", "priceTargetAction": "Lowers", "currentPriceTarget": 200.0, "priorPriceTarget": 240.0},
        {"epochGradeDate": epoche(date(2026, 5, 1)), "firm": "Alt", "toGrade": "Buy", "fromGrade": "Hold",
         "action": "up", "priceTargetAction": "Raises", "currentPriceTarget": 1.0, "priorPriceTarget": 0.5},
        {"epochGradeDate": "kaputt", "firm": "X", "action": "up"},
    ]
    r = revisionen_aus(_trend_nvda(), historie, heute)
    p("Revisionen: Anhebungen und Senkungen wie geliefert, beide Schreibweisen von downLast7days",
      r["rev_hoch_7t_0q"] == 34 and r["rev_hoch_30t_0q"] == 35 and r["rev_runter_7t_0q"] == 3
      and r["rev_runter_30t_0q"] == 1 and r["rev_runter_7t_1q"] == 13 and r["rev_runter_30t_1y"] == 0,
      f"{r['rev_runter_7t_0q']}, {r['rev_runter_7t_1q']}")
    p("Revisionen: EPS-Konsens heute und vor 7 bis 90 Tagen",
      r["rev_eps_jetzt_0q"] == 2.47269 and r["rev_eps_30t_0q"] == 2.34527 and r["rev_eps_90t_1y"] == 12.67184
      and r["rev_eps_7t_1q"] is None and r["rev_eps_jetzt_0y"] is None)
    p("Stufen in 30 Tagen: eine Erstbewertung, eine Heraufstufung vor 25 Tagen, zwei Kursziele angehoben",
      r["stufen_neu_30t"] == 1 and r["stufen_hoch_30t"] == 1 and r["stufen_runter_30t"] == 0
      and r["stufen_ziel_rauf_30t"] == 2 and r["stufen_ziel_runter_30t"] == 0,
      str({k: r[k] for k in r if "30t" in k and k.startswith("stufen")}))
    p("Stufen in 90 Tagen: eine Herauf-, eine Herabstufung, zwei Kursziele rauf, eines runter",
      r["stufen_hoch_90t"] == 1 and r["stufen_runter_90t"] == 1 and r["stufen_neu_90t"] == 1
      and r["stufen_ziel_rauf_90t"] == 2 and r["stufen_ziel_runter_90t"] == 1)
    liste = json.loads(r["stufen_liste"])
    p("Juengste Einstufungen: nur 90 Tage, neueste zuerst, Kursziel 0 wird leer",
      [x["firma"] for x in liste] == ["Piper Sandler", "Rosenblatt", "Needham", "Mizuho"]
      and liste[0]["ziel_vorher"] is None and liste[0]["von"] is None and liste[1]["ziel_vorher"] == 350.0,
      str([x["firma"] for x in liste]))
    r0 = revisionen_aus([], [], heute)
    p("Abgefragt ohne Einstufungen: Zaehler null, Liste leer, Stand gesetzt",
      r0["stufen_hoch_30t"] == 0 and r0["stufen_liste"] == "[]" and r0["rev_stand"] == "2026-09-14")
    rn = revisionen_aus(None, None, heute)
    p("Nicht abgefragte Einstufungen bleiben leer", rn["stufen_hoch_30t"] is None and rn["stufen_liste"] is None)

    # --- Drossel und Ergebnispruefung -----------------------------------------
    m401 = ['HTTP Error 401: {"finance":{"error":{"code":"Unauthorized","description":"Invalid Crumb"}}}']
    m404 = ['HTTP Error 404: {"quoteSummary":{"error":{"description":"No fundamentals data found for symbol: VXX"}}}']
    try:
        ergebnis_pruefen("X", _trend_nvda(), [], m401)
        p("Drossel wird auch bei gelieferten Daten erkannt", False)
    except YahooDrossel:
        p("Drossel wird auch bei gelieferten Daten erkannt", True)

    class YFRateLimitError(Exception):
        pass

    try:
        ergebnis_pruefen("X", None, None, [], YFRateLimitError("Too Many Requests"))
        p("RateLimit-Ausnahme gilt als Drossel", False)
    except YahooDrossel:
        p("RateLimit-Ausnahme gilt als Drossel", True)
    try:
        ergebnis_pruefen("X", None, None, [], None)
        p("Leeres Ergebnis ohne Grund ist ein Fehler", False)
    except RuntimeError:
        p("Leeres Ergebnis ohne Grund ist ein Fehler", True)
    try:
        ergebnis_pruefen("VXX", None, None, m404)
        ergebnis_pruefen("NEU", [], [], [])
        p("Legitim leer: keine Fundamentaldaten, oder Antwort mit leeren Listen", True)
    except Exception as e:  # noqa
        p("Legitim leer: keine Fundamentaldaten, oder Antwort mit leeren Listen", False, f"{type(e).__name__}: {e}")

    # --- Viele Aktien: Warten, Wiederholen, Notbremse ---------------------------
    geschlafen = []
    versuche = {"A": 0}

    def holen_a(tk):
        if tk == "A":
            versuche["A"] += 1
            if versuche["A"] <= 2:
                raise YahooDrossel("A: 429")
            return _trend_nvda(), historie
        if tk == "B":
            raise RuntimeError("B: leeres Ergebnis ohne erkennbaren Grund")
        return [], []

    erg, fe, ab = revisionen_viele(["A", "B", "C"], heute, holen=holen_a, schlafen=geschlafen.append)
    p("Viele Aktien: Drossel wartet 30 und 60 Sekunden und holt dann, Fehler wird vermerkt",
      set(erg) == {"A", "C"} and set(fe) == {"B"} and not ab
      and geschlafen == [float(KK["rev_warten_s"]), float(KK["rev_warten_s"]) * 2], f"{geschlafen}, {fe}")
    geschlafen.clear()

    def immer_drossel(tk):
        raise YahooDrossel(f"{tk}: Invalid Crumb")

    liste_n = [f"T{i}" for i in range(20)]
    erg, fe, ab = revisionen_viele(liste_n, heute, holen=immer_drossel, schlafen=geschlafen.append)
    p("Viele Aktien: Notbremse nach gedrosselten Aktien in Folge",
      ab and not erg and len(fe) == int(KK["rev_notbremse"]), f"{len(fe)} Fehler")

    # --- Keine Vernetzung -----------------------------------------------------------
    quelle = open(__file__, encoding="utf-8").read()
    p("Keine Vernetzung: kein Sendecode, keine Alarmdateien",
      all(x not in quelle for x in ("NTFY_" + "TOPIC", "ntfy." + "sh", "requests." + "post(", "breakout_" + "watcher",
                                    "traderfox_" + "alarm", "kaufpunkte_" + "aktuell")))

    print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles bestanden.")
    return 1 if fehler else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Kennzahlen aus dem Konsens (Etappe 5)")
    ap.add_argument("--selbsttest", action="store_true")
    args = ap.parse_args()
    if args.selbsttest:
        return selbsttest()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
