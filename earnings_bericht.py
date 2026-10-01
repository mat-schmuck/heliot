# -*- coding: utf-8 -*-
"""
EARNINGS-BERICHT: Quartalszahlen im Reiter Berichte der App
===========================================================
Gerhards Auftrag vom 30.09.2026 (ueber Mathias, "neue Anweisungen") und seine
Antworten vom selben Abend (1 bis 5 und 12):

  "Es beginnt die Quartalssaison, daher zukuenftig ein Bericht, ich moechte ab
  jetzt jeden Abend einen Earningsbericht haben von:
  - Unternehmen, die die Analystenschaetzungen geschlagen haben
  - Umsatz q/q und EPS q/q bei Aktien, die eine Wachstumsbeschleunigung
    erfahren
  - nur Aktien mit mindestens 20 Prozent Umsatzwachstum q/q, ueber 15 Dollar
    und ueber 700 Millionen Dollar Marktkapitalisierung
  - klar erkennen, was sich um wie viel verbessert oder verschlechtert hat
  - Aktien mit einer Jahresvolatilitaet unter 10 Prozent ausschliessen
  - bis 8 Uhr Wiener Zeit des naechsten Tages geliefert; vorboersliche
    Quartalsberichte vor Boerseneroeffnung
  - der projizierte Ausblick und inwiefern er die Analystenschaetzungen
    ueberbietet
  - genau aufgeschluesselt, wie sehr die Quartalszahlen den Konsens desselben
    Quartals unter- oder ueberboten haben.
  Ich moechte keine Berichtsflut haben, meine Kriterien sind klar definiert."

  1  Konsens geschlagen: EPS mindestens plus 3 Prozent ODER Umsatz mindestens
     plus 4 Prozent ueber dem EINGEFRORENEN Konsens; eine reicht; beide Werte
     zeigen und markieren, welche erfuellt ist.
  2  Beschleunigung: ab 5 Prozentpunkten mehr als im Vorquartal (30 auf 35).
  3  Umsatzwachstum 20 Prozent gegen das Vorjahresquartal, wie im Scanner.
  4  Jahresvolatilitaet: Schwankung der Tageskurse ueber 252 Handelstage, aufs
     Jahr hochgerechnet; Ausschluss unter 10 Prozent.
  5  Ausblick: Umsatz und EPS fuer das naechste Quartal und das Gesamtjahr,
     jeweils gegen den eingefrorenen Konsens; bei einer Spanne die Mitte.
  12 Ausblick per Mistral; jeder KI-Wert "KI, vorlaeufig"; kein Alarm, keine
     Bot-Zeile.
  Zusatzlauf vor der Eroeffnung; die Zahl der Aktien je Tag nachmessen.

WIE ES LAEUFT: nach jedem Lauf des Vorabwerte-Stroms (vorabwerte.yml, werktags
06:00 bis 20:00 New York alle 30 Minuten, dazu der Zusatzlauf um 09:20 New
York, den berichte.yml auf main anstoesst). Jede Vorabwert-Datei wird genau
einmal bewertet.

EIN TAGESBERICHT (Gerhards Antworten 13 und 14 vom 01.10.2026): "EIN
Earnings-Tagesbericht, der laufend ergaenzt wird. Neue Treffer stehen oben mit
Uhrzeit, und der Zaehler ungelesen springt bei neuen Treffern wieder an."
"Jeden Handelstag eine Meldung im Unterreiter Earnings, auch wenn keine
Quartalszahlen kamen oder keine Aktie die Kriterien erfuellt hat. Dann steht
dort kurz, ob und wie viele Zahlen gelesen wurden und dass keine Aktie die
Kriterien erfuellt hat." Je New Yorker Tag gibt es deshalb EINEN Bericht mit
dem Schluessel earnings-JJJJ-MM-TT, der sich im Reiter selbst ersetzt
(berichte.py). Seine Kennung entsteht aus den Treffern: Ein neuer Treffer macht
ihn wieder ungelesen, eine neue Zahl gelesener Meldungen nicht. Er steht bis zum
naechsten Handelstag um 14:00 Uhr Wiener Zeit, auch wenn er vor der Leerung um
14:00 begonnen hat. Die Treffer stehen im Stand (stand.json, tage) samt Text,
damit jeder Lauf den Bericht neu bauen kann. Nach dem letzten Lauf des Abends,
ab 19:30 New York, steht an jedem Handelstag der New Yorker Boerse
(boersentage.py) der Stand des Abends da, ohne Treffer als Meldung, dass keine
Aktie die Kriterien erfuellt hat. Faellt der Abendlauf aus, holt der naechste
Lauf das nach, solange der Bericht noch stehen wuerde.

AUSWAHL (Antwort 10 vom 01.10.2026: "Eines von beiden reicht, wie gebaut.
Aktien, die beides erfuellen, stehen oben und sind markiert."): eine Aktie kommt
in den Bericht, wenn sie alle Filter besteht (Umsatzwachstum, Kurs,
Boersenwert, Volatilitaet) und Konsens geschlagen ODER Beschleunigung gilt;
markiert ist, was davon erfuellt ist. Innerhalb eines Laufs stehen die Aktien
mit beiden Bedingungen zuerst, als "beide Bedingungen erfuellt" markiert, dann
nach der Abweichung beim Umsatz; die Laeufe stehen neueste zuerst.

DATEN:
  * Zahlen des Quartals und Abweichung vom Konsens: die Vorabwert-Datei
    (vorabwerte_8k.py, KI aus der Pressemitteilung, gegen den letzten
    Konsens-Schnappschuss vor der Meldung);
  * Vorjahresquartal und Vorquartal: SEC companyfacts, Erstfassung;
  * Kurs und Boersenwert: die Scanner-Tabelle der letzten Nacht;
  * Volatilitaet: Tagesschluesse von Yahoo;
  * Ausblick: Mistral liest die Pressemitteilung aus dem Pressetext-Archiv,
    verglichen mit den Perioden +1q und 0y oder +1y desselben Schnappschusses.

VORLAEUFIG UNSICHER: Die Plausibilitaetspruefung der Vorabwerte nennt einen
Umsatz unsicher, der mehr als 50 Prozent vom Vorjahresquartal abweicht; das
trifft gerade die stark wachsenden Firmen, um die es hier geht. Eine Datei, die
NUR aus diesem Grund unsicher ist, wird deshalb bewertet und im Bericht
vermerkt; aus jedem anderen Grund unsichere bleiben draussen.

Aufruf (nur im Actions-Lauf: SEC_USER_AGENT, MISTRAL_API_KEY, DATEN_TOKEN):
  python earnings_bericht.py --daten daten [--trocken]
  python earnings_bericht.py --daten daten --messen 10
  python earnings_bericht.py --selbsttest
"""

import argparse
import datetime as dt
import glob
import gzip
import io
import json
import math
import os
import re
import sys
import time
import urllib.request

ART = "earnings"
KONSENS_EPS_MIN = 3.0          # Prozent ueber dem eingefrorenen Konsens (Antwort 1)
KONSENS_UMSATZ_MIN = 4.0
BESCHLEUNIGUNG_MIN = 5.0       # Prozentpunkte ueber dem Wachstum im Vorquartal (Antwort 2)
UMSATZ_WACHSTUM_MIN = 20.0     # Prozent gegen das Vorjahresquartal (Antwort 3)
KURS_MIN = 15.0                # Dollar, wie beim Gap-Up-Bericht
MARKTKAP_MIN_MRD = 0.7         # Milliarden Dollar
VOLA_MIN = 10.0                # Prozent, Jahresvolatilitaet (Antwort 4)
VOLA_TAGE = 252
STAND = os.path.join("earnings", "stand.json")
TABELLE_URL = "https://github.com/mat-schmuck/heliot/releases/download/scanner-daten/scanner_tabelle.parquet"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{}?range=2y&interval=1d"
KOPF = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept": "application/json"}
NUR_UMSATZ_UNSICHER = re.compile(r"^Umsatz \d+ Prozent neben dem Vorjahresquartal$")
ABEND_SCHLUSS_NY = 19 * 60 + 30   # der letzte Stromlauf des Abends beginnt um 20:00 New York
NACHHOLEN_TAGE = 4                # so lange holt ein Lauf einen ausgefallenen Abend nach
TREFFER_TAGE = 6                  # so lange behaelt der Stand die Texte der Treffer
KI = "KI, vorläufig"

try:
    from zoneinfo import ZoneInfo
    NY, WIEN = ZoneInfo("America/New_York"), ZoneInfo("Europe/Vienna")
except Exception:  # noqa: BLE001
    NY = dt.timezone(dt.timedelta(hours=-4))
    WIEN = dt.timezone(dt.timedelta(hours=2))


# ---------------------------------------------------------------------------
# Zahlen und Worte
# ---------------------------------------------------------------------------

def _f(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def rel(ist, soll):
    """Prozent ueber soll; nur bei positivem soll (sonst nicht berechenbar)."""
    ist, soll = _f(ist), _f(soll)
    if ist is None or soll is None or soll <= 0:
        return None
    return (ist / soll - 1.0) * 100.0


def zahl(x, stellen=1):
    v = _f(x)
    if v is None:
        return "unbekannt"
    s = f"{v:,.{stellen}f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    return s


def vz(x, stellen=1, einheit="Prozent"):
    """plus 4,0 Prozent, minus 2,5 Prozent, 0 Prozent."""
    v = _f(x)
    if v is None:
        return "nicht berechenbar"
    r = round(v, stellen)
    if r == 0:
        return f"0 {einheit}"
    return f"{'plus' if r > 0 else 'minus'} {zahl(abs(r), stellen)} {einheit}"


def dollar(x):
    """Ein Betrag in Worten: 1,25 Milliarden Dollar, 820 Millionen Dollar."""
    v = _f(x)
    if v is None:
        return "unbekannt"
    a = abs(v)
    vorz = "minus " if v < 0 else ""
    if a >= 1e9:
        return f"{vorz}{zahl(a / 1e9, 2)} Milliarden Dollar"
    if a >= 1e6:
        return f"{vorz}{zahl(a / 1e6, 1)} Millionen Dollar"
    return f"{vorz}{zahl(a, 0)} Dollar"


def je_aktie(x):
    v = _f(x)
    return "unbekannt" if v is None else f"{zahl(v, 2)} Dollar"


def _datum(iso):
    try:
        d = dt.date.fromisoformat(str(iso)[:10])
    except ValueError:
        return str(iso or "unbekannt")
    return f"{d:%d.%m.%Y}"


def _utc(s):
    try:
        z = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return z if z.tzinfo else z.replace(tzinfo=dt.timezone.utc)


def _wien(s):
    z = _utc(s)
    return f"{z.astimezone(WIEN):%d.%m. %H:%M} Uhr Wiener Zeit" if z else "Zeit unbekannt"


# ---------------------------------------------------------------------------
# Wachstum, Vorquartal, Volatilitaet
# ---------------------------------------------------------------------------

def quartalswert(zeilen, kennzahl, ende, toleranz_tage=20):
    """Erstfassung einer Quartalszahl, deren Ende hoechstens toleranz_tage von
    ende abweicht (52/53-Wochen-Jahre)."""
    for z in zeilen or []:
        if z.get("typ") != "Q" or z.get("kennzahl") != kennzahl or z.get("wert_erst") is None:
            continue
        try:
            e = dt.date.fromisoformat(z["end"])
        except (ValueError, TypeError, KeyError):
            continue
        if abs((e - ende).days) <= toleranz_tage:
            return z["wert_erst"]
    return None


def vorquartal_wachstum(zeilen, periodenende, kennzahl):
    """Wachstum des Quartals VOR dem gemeldeten gegen sein Vorjahresquartal, in
    Prozent; None, wenn eine der zwei Zahlen fehlt oder die Basis nicht positiv
    ist."""
    try:
        pe = dt.date.fromisoformat(str(periodenende))
    except (TypeError, ValueError):
        return None
    vorq = pe - dt.timedelta(days=91)
    jetzt = quartalswert(zeilen, kennzahl, vorq)
    vorjahr = quartalswert(zeilen, kennzahl, vorq - dt.timedelta(days=364))
    return rel(jetzt, vorjahr)


def jahresvola(schluesse, tage=VOLA_TAGE):
    """Schwankung der Tageskurse ueber die letzten tage Handelstage, aufs Jahr
    hochgerechnet, in Prozent: Standardabweichung der logarithmischen
    Tagesrenditen mal Wurzel aus 252."""
    s = [v for v in (_f(x) for x in schluesse or []) if v is not None and v > 0]
    if len(s) < tage + 1:
        return None
    s = s[-(tage + 1):]
    r = [math.log(b / a) for a, b in zip(s, s[1:])]
    m = sum(r) / len(r)
    var = sum((x - m) ** 2 for x in r) / (len(r) - 1)
    return math.sqrt(var) * math.sqrt(252) * 100.0


def yahoo_schluesse(ticker, holen=None):
    holen = holen or _holen
    roh = holen(YAHOO_CHART.format(urllib.request.quote(str(ticker).replace(".", "-"))))
    d = json.loads(roh)
    r = (d.get("chart") or {}).get("result") or []
    if not r:
        return []
    q = ((r[0].get("indicators") or {}).get("quote") or [{}])[0]
    return [x for x in (q.get("close") or []) if x is not None]


def _holen(url, timeout=30):
    req = urllib.request.Request(url, headers=KOPF)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


# ---------------------------------------------------------------------------
# Konsens je Periode aus dem Schnappschuss vor der Meldung
# ---------------------------------------------------------------------------

_SCHNAPP = {}


def konsens_perioden_vor(daten, ticker, filing_utc):
    """{Periode: Zeile} aus dem juengsten Konsens-Schnappschuss VOR der Meldung
    (dieselbe Regel wie vorabwerte_8k.konsens_vor, aber alle vier Perioden)."""
    grenze = _utc(filing_utc)
    if not ticker or grenze is None:
        return {}
    kandidaten = []
    for p in glob.glob(os.path.join(daten, "konsens", "*", "*.jsonl.gz")):
        m = re.search(r"(\d{4}-\d{2}-\d{2})_(\d{2})(\d{2})Z", os.path.basename(p))
        if not m:
            continue
        z = dt.datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}:{m.group(3)}:00+00:00")
        if z < grenze:
            kandidaten.append((z, p))
    if not kandidaten:
        return {}
    _z, p = max(kandidaten)
    if p not in _SCHNAPP:
        tabelle = {}
        with gzip.open(p, "rt", encoding="utf-8") as h:
            for zeile in h:
                try:
                    d = json.loads(zeile)
                except ValueError:
                    continue
                tabelle.setdefault(str(d.get("ticker") or "").upper(), {})[d.get("periode")] = d
        _SCHNAPP[p] = tabelle
    return dict(_SCHNAPP[p].get(str(ticker).upper(), {}))


# ---------------------------------------------------------------------------
# Ausblick per Mistral (Antworten 5 und 12)
# ---------------------------------------------------------------------------

AUSBLICK_AUFTRAG = (
    "You are a meticulous financial data extractor. You receive the text of an earnings press release filed with "
    "the SEC (Form 8-K, Exhibit 99.1); passages may be omitted and marked with [...]. Extract ONLY the company's "
    "OUTLOOK or GUIDANCE for FUTURE periods, never results already reported. Fields: "
    "quartal_zeitraum = the label of the NEXT fiscal quarter the guidance covers, as written; null if the release "
    "gives no guidance for a single quarter; "
    "quartal_umsatz_tief and quartal_umsatz_hoch = the guided total revenue for that quarter in absolute US dollars "
    "($1.2 billion becomes 1200000000); a single value goes into both fields; "
    "quartal_umsatz_wachstum_tief and quartal_umsatz_wachstum_hoch = the guided revenue growth for that quarter in "
    "percent (10 to 12 percent becomes 10 and 12), only if the company guides a growth rate; "
    "quartal_eps_tief and quartal_eps_hoch = the guided diluted earnings per share for that quarter in dollars; "
    "quartal_eps_bereinigt = true if that EPS guidance is adjusted or non-GAAP, false if GAAP, null without EPS "
    "guidance; "
    "jahr_zeitraum, jahr_umsatz_tief, jahr_umsatz_hoch, jahr_umsatz_wachstum_tief, jahr_umsatz_wachstum_hoch, "
    "jahr_eps_tief, jahr_eps_hoch, jahr_eps_bereinigt = the same for the guided FULL FISCAL YEAR; "
    "beleg_quartal and beleg_jahr = the exact text fragment, at most 160 characters, from which the quarterly and "
    "the annual guidance were taken. Do not compute anything yourself; take figures only as the company states "
    "them. Use null for anything the text does not state. Answer with JSON only, no prose."
)
_ZAHL = {"type": ["number", "null"]}
_TEXT = {"type": ["string", "null"]}
_BOOL = {"type": ["boolean", "null"]}
AUSBLICK_SCHEMA = {
    "type": "object",
    "properties": {
        **{f"{t}_{k}": v for t in ("quartal", "jahr") for k, v in (
            ("zeitraum", _TEXT), ("umsatz_tief", _ZAHL), ("umsatz_hoch", _ZAHL), ("umsatz_wachstum_tief", _ZAHL),
            ("umsatz_wachstum_hoch", _ZAHL), ("eps_tief", _ZAHL), ("eps_hoch", _ZAHL), ("eps_bereinigt", _BOOL))},
        "beleg_quartal": _TEXT, "beleg_jahr": _TEXT,
    },
    "additionalProperties": False,
}
AUSBLICK_SCHEMA["required"] = list(AUSBLICK_SCHEMA["properties"])
AUSBLICK_WORTE = re.compile(r"outlook|guidance|guides|expects|anticipat|forecast|full[- ]year|fiscal (year )?20\d\d|"
                            r"next quarter|(first|second|third|fourth) quarter", re.I)


def ausblick_text(text, limit=30000, kopf=7000, umfeld=1500):
    """Der Kopf der Pressemitteilung und die Stellen um die Woerter des
    Ausblicks; die Ergebnistabellen am Ende braucht der Ausblick nicht."""
    text = str(text or "")
    if len(text) <= limit:
        return text
    teile, bis = [text[:kopf]], kopf
    for m in AUSBLICK_WORTE.finditer(text, kopf):
        a, b = max(bis, m.start() - umfeld), m.end() + umfeld
        if a < b:
            teile.append(text[a:b])
            bis = b
        if sum(len(t) for t in teile) >= limit:
            break
    return " [...] ".join(teile)[:limit]


def ausblick_fragen(text, kette=None, anfrage=None, bremse=None):
    """Der Ausblick als dict oder None; probiert die Modellkette der Vorabwerte."""
    import messung_8k as m8k
    import vorabwerte_8k as v8
    kette = kette or v8.KETTE
    anfrage = anfrage or m8k._anfrage
    bremse = bremse or m8k.Bremse()
    gekuerzt = ausblick_text(text)
    for modell in kette:
        for versuch in range(4):
            koerper = {"model": modell, "temperature": 0, "max_tokens": 900,
                       "messages": [{"role": "system", "content": AUSBLICK_AUFTRAG},
                                    {"role": "user", "content": gekuerzt}],
                       "response_format": {"type": "json_schema", "json_schema": {
                           "name": "ausblick", "strict": True, "schema": AUSBLICK_SCHEMA}}}
            bremse.warten(modell)
            status, kopf, roh = anfrage("https://api.mistral.ai/v1/chat/completions", koerper)
            bremse.merken(modell, kopf)
            if status == 429 or status >= 500:
                time.sleep(20 if status == 429 else 10)
                continue
            if status != 200:
                break
            try:
                inhalt = json.loads(roh)["choices"][0]["message"].get("content") or ""
                g = json.loads(inhalt)
            except Exception:  # noqa: BLE001
                break
            if isinstance(g, dict):
                g["modell"] = modell
                return g
            break
    return None


def _mitte(tief, hoch):
    a, b = _f(tief), _f(hoch)
    if a is None and b is None:
        return None
    if a is None or b is None:
        return a if b is None else b
    return (a + b) / 2.0


def ausblick_vergleich(g, perioden, periodenende):
    """Je Zeitraum (quartal, jahr) und Groesse (umsatz, eps): Spanne, Mitte,
    Konsens und Abweichung. Der Konsens des naechsten Quartals ist +1q; fuer das
    Jahr gilt 0y, ausser das gemeldete Quartal schliesst das Geschaeftsjahr ab,
    dann +1y."""
    raus = {}
    if not g:
        return raus
    try:
        pe = dt.date.fromisoformat(str(periodenende))
    except (TypeError, ValueError):
        pe = None
    jahr_periode = "0y"
    k0y = perioden.get("0y") or {}
    try:
        if pe and abs((dt.date.fromisoformat(str(k0y.get("periodenende"))) - pe).days) <= 10:
            jahr_periode = "+1y"
    except (TypeError, ValueError):
        pass
    for zeit, periode in (("quartal", "+1q"), ("jahr", jahr_periode)):
        k = perioden.get(periode) or {}
        for groesse in ("umsatz", "eps"):
            tief, hoch = g.get(f"{zeit}_{groesse}_tief"), g.get(f"{zeit}_{groesse}_hoch")
            mitte = _mitte(tief, hoch)
            quelle = "betrag"
            if mitte is None and groesse == "umsatz":
                w = _mitte(g.get(f"{zeit}_umsatz_wachstum_tief"), g.get(f"{zeit}_umsatz_wachstum_hoch"))
                basis = _f(k.get("umsatz_vorjahr"))
                if w is not None and basis:
                    mitte, quelle = basis * (1 + w / 100.0), "wachstum"
                    tief = basis * (1 + (_f(g.get(f"{zeit}_umsatz_wachstum_tief")) or w) / 100.0)
                    hoch = basis * (1 + (_f(g.get(f"{zeit}_umsatz_wachstum_hoch")) or w) / 100.0)
            if mitte is None:
                continue
            konsens = _f(k.get(f"{groesse}_avg"))
            raus[(zeit, groesse)] = {"tief": _f(tief), "hoch": _f(hoch), "mitte": mitte, "quelle": quelle,
                                     "wachstum_tief": _f(g.get(f"{zeit}_umsatz_wachstum_tief")),
                                     "wachstum_hoch": _f(g.get(f"{zeit}_umsatz_wachstum_hoch")),
                                     "konsens": konsens, "abweichung": rel(mitte, konsens) if konsens else None,
                                     "periode": periode, "bereinigt": g.get(f"{zeit}_eps_bereinigt")}
    return raus


# ---------------------------------------------------------------------------
# Bewerten
# ---------------------------------------------------------------------------

def bewerten(e, zeilen=None, tabelle=None, schluesse=None):
    """Die Kennzahlen einer Vorabwert-Datei und die Pruefungen. Liefert ein
    dict; aufgenommen ist es, wenn b["aufnehmen"] wahr ist."""
    w = e.get("werte") or {}
    vj = e.get("vorjahr") or {}
    ue = e.get("ueberraschung") or {}
    b = {"ticker": e.get("ticker"), "name": e.get("name"), "cik": e.get("cik"), "accession": e.get("accession"),
         "filing_utc": e.get("sec_akzeptanz_utc") or e.get("filing_utc"), "periodenende": w.get("periodenende"),
         "status": e.get("status"), "pruefung": list(e.get("pruefung") or []), "gruende": []}
    if b["status"] == "unsicher" and not all(NUR_UMSATZ_UNSICHER.match(g) for g in b["pruefung"]):
        b["gruende"].append("Vorabwert unsicher")
    b["umsatz"], b["eps"] = _f(w.get("umsatz")), _f(w.get("eps_verwaessert"))
    b["umsatz_wachstum"] = rel(w.get("umsatz"), vj.get("umsatz"))
    b["eps_wachstum"] = rel(w.get("eps_verwaessert"), vj.get("eps_verwaessert"))
    b["umsatz_wachstum_vorq"] = vorquartal_wachstum(zeilen, w.get("periodenende"), "umsatz")
    b["eps_wachstum_vorq"] = vorquartal_wachstum(zeilen, w.get("periodenende"), "eps_verwaessert")
    b["umsatz_beschl"] = (b["umsatz_wachstum"] - b["umsatz_wachstum_vorq"]
                          if b["umsatz_wachstum"] is not None and b["umsatz_wachstum_vorq"] is not None else None)
    b["eps_beschl"] = (b["eps_wachstum"] - b["eps_wachstum_vorq"]
                       if b["eps_wachstum"] is not None and b["eps_wachstum_vorq"] is not None else None)
    passt = ue.get("periode_passt") is not False
    b["konsens_passt"] = passt
    b["umsatz_konsens"], b["umsatz_ue"] = _f(ue.get("umsatz_konsens")), _f(ue.get("umsatz_prozent")) if passt else None
    b["eps_konsens"], b["eps_ue"] = _f(ue.get("eps_konsens")), _f(ue.get("eps_prozent")) if passt else None
    b["eps_basis"] = ue.get("eps_basis") or "amtlich"
    b["eps_ist"] = _f(w.get("eps_bereinigt")) if b["eps_basis"] == "bereinigt" else b["eps"]
    b["a_umsatz"] = b["umsatz_ue"] is not None and b["umsatz_ue"] >= KONSENS_UMSATZ_MIN
    b["a_eps"] = b["eps_ue"] is not None and b["eps_ue"] >= KONSENS_EPS_MIN
    b["b_umsatz"] = b["umsatz_beschl"] is not None and b["umsatz_beschl"] >= BESCHLEUNIGUNG_MIN
    b["b_eps"] = b["eps_beschl"] is not None and b["eps_beschl"] >= BESCHLEUNIGUNG_MIN
    b["a"], b["b"] = b["a_umsatz"] or b["a_eps"], b["b_umsatz"] or b["b_eps"]
    zeile = (tabelle or {}).get(str(b["ticker"] or "").upper()) or {}
    b["kurs"], b["marktkap_mrd"] = _f(zeile.get("kurs")), _f(zeile.get("marktkap_mrd"))
    b["vola"] = jahresvola(schluesse) if schluesse else None
    if b["umsatz_wachstum"] is None or b["umsatz_wachstum"] < UMSATZ_WACHSTUM_MIN:
        b["gruende"].append("Umsatzwachstum")
    if b["kurs"] is None or b["kurs"] < KURS_MIN or b["marktkap_mrd"] is None or b["marktkap_mrd"] < MARKTKAP_MIN_MRD:
        b["gruende"].append("Kurs oder Börsenwert")
    if b["vola"] is None or b["vola"] < VOLA_MIN:
        b["gruende"].append("Volatilität")
    if not (b["a"] or b["b"]):
        b["gruende"].append("weder Konsens geschlagen noch Beschleunigung")
    b["aufnehmen"] = not b["gruende"]
    return b


def vorpruefung(e, tabelle=None):
    """Was sich ohne SEC und Yahoo schon ausschliessen laesst: so bleiben die
    Abrufe bei den wenigen Kandidaten."""
    b = bewerten(e, zeilen=None, tabelle=tabelle, schluesse=[1.0] * (VOLA_TAGE + 1))
    harte = [g for g in b["gruende"] if g in ("Vorabwert unsicher", "Umsatzwachstum", "Kurs oder Börsenwert")]
    return not harte, harte


# ---------------------------------------------------------------------------
# Bericht
# ---------------------------------------------------------------------------

def _erfuellt(b) -> str:
    teile = []
    if b["a"]:
        welche = " und ".join(x for x, ok in (("beim Umsatz", b["a_umsatz"]), ("beim EPS", b["a_eps"])) if ok)
        teile.append(f"Konsens geschlagen {welche}")
    if b["b"]:
        welche = " und ".join(x for x, ok in (("beim Umsatz", b["b_umsatz"]), ("beim EPS", b["b_eps"])) if ok)
        teile.append(f"Beschleunigung {welche}")
    return ", ".join(teile)


def _ausblick_satz(vergleich) -> str:
    teile = []
    for zeit, wort in (("quartal", "nächstes Quartal"), ("jahr", "Gesamtjahr")):
        stuecke = []
        for groesse in ("umsatz", "eps"):
            v = vergleich.get((zeit, groesse))
            if not v:
                stuecke.append(("Umsatz" if groesse == "umsatz" else "EPS") + " nicht genannt")
                continue
            if groesse == "umsatz":
                if v["quelle"] == "wachstum":
                    spanne = (f"Umsatz {vz(v['wachstum_tief'], 1)} bis {vz(v['wachstum_hoch'], 1)}"
                              if v["wachstum_tief"] != v["wachstum_hoch"] else f"Umsatz {vz(v['wachstum_tief'], 1)}")
                    spanne += f", also {dollar(v['mitte'])} in der Mitte"
                else:
                    spanne = (f"Umsatz {dollar(v['tief'])} bis {dollar(v['hoch'])}, Mitte {dollar(v['mitte'])}"
                              if v["tief"] != v["hoch"] else f"Umsatz {dollar(v['mitte'])}")
                gegen = (f" gegen Konsens {dollar(v['konsens'])}, {vz(v['abweichung'])}" if v["konsens"]
                         else "; Konsens unbekannt")
            else:
                art = {True: "EPS bereinigt", False: "EPS amtlich"}.get(v["bereinigt"], "EPS")
                spanne = (f"{art} {je_aktie(v['tief'])} bis {je_aktie(v['hoch'])}, Mitte {je_aktie(v['mitte'])}"
                          if v["tief"] != v["hoch"] else f"{art} {je_aktie(v['mitte'])}")
                gegen = (f" gegen Konsens {je_aktie(v['konsens'])}, {vz(v['abweichung'])}"
                         if v["konsens"] is not None else "; Konsens unbekannt")
                if v["bereinigt"] is False:
                    gegen += ", der Konsens ist bereinigt"
            stuecke.append(spanne + gegen)
        teile.append(f"{wort} " + ", ".join(stuecke))
    return "; ".join(teile)


def absatz(nr, b, vergleich=None, aufgenommen=None) -> str:
    return f"{nr}. " + absatz_text(b, vergleich, aufgenommen)


def absatz_text(b, vergleich=None, aufgenommen=None) -> str:
    """Der Absatz einer Aktie ohne Nummer: Die Nummer vergibt der
    Tagesbericht, wenn er alle Treffer des Tages ordnet. Erfuellt sie beide
    Bedingungen, steht das gleich hinter dem Namen (Antwort 10), dahinter die
    Uhrzeit, zu der sie in den Bericht kam (Antwort 13)."""
    beide = "; beide Bedingungen erfüllt" if b["a"] and b["b"] else ""
    um = _utc(aufgenommen.isoformat() if isinstance(aufgenommen, dt.datetime) else aufgenommen)
    zeit = f"; aufgenommen um {um.astimezone(WIEN):%H:%M} Uhr Wiener Zeit" if um else ""
    z1 = (f"{b['ticker']}, {b['name'] or 'Firma unbekannt'}{beide}{zeit}; Quartal bis {_datum(b['periodenende'])}, "
          f"gemeldet am {_wien(b['filing_utc'])}; erfüllt: {_erfuellt(b)}")
    eps_wort = "EPS bereinigt" if b["eps_basis"] == "bereinigt" else "EPS amtlich"
    if b["konsens_passt"]:
        z2 = (f"Gegen den Konsens, {KI}: Umsatz {dollar(b['umsatz'])} gegen {dollar(b['umsatz_konsens'])}, "
              f"{vz(b['umsatz_ue'])}{', erfüllt' if b['a_umsatz'] else ''}; {eps_wort} {je_aktie(b['eps_ist'])} gegen "
              f"{je_aktie(b['eps_konsens'])}, {vz(b['eps_ue'])}{', erfüllt' if b['a_eps'] else ''}")
    else:
        z2 = "Gegen den Konsens: Der eingefrorene Konsens gilt für ein anderes Quartal, kein Vergleich"
    vorq_u = (f"nach {vz(b['umsatz_wachstum_vorq'], 0)} im Quartal davor, {vz(b['umsatz_beschl'], 0, 'Prozentpunkte')}"
              if b["umsatz_beschl"] is not None else "Quartal davor unbekannt")
    vorq_e = (f"nach {vz(b['eps_wachstum_vorq'], 0)} im Quartal davor, {vz(b['eps_beschl'], 0, 'Prozentpunkte')}"
              if b["eps_beschl"] is not None else "Quartal davor nicht berechenbar")
    z3 = (f"Wachstum gegen das Vorjahresquartal, {KI}: Umsatz {vz(b['umsatz_wachstum'], 0)} {vorq_u}"
          f"{', erfüllt' if b['b_umsatz'] else ''}; EPS {vz(b['eps_wachstum'], 0)} {vorq_e}"
          f"{', erfüllt' if b['b_eps'] else ''}")
    z4 = (f"Ausblick, {KI}: " + _ausblick_satz(vergleich)) if vergleich else f"Ausblick, {KI}: keiner genannt"
    z5 = (f"Kurs {zahl(b['kurs'], 2)} Dollar; Börsenwert {zahl(b['marktkap_mrd'], 1)} Milliarden Dollar; "
          f"Jahresvolatilität {zahl(b['vola'], 0)} Prozent")
    if b["status"] == "unsicher":
        z5 += "; Vorabwert als unsicher markiert, weil der Umsatz mehr als 50 Prozent über dem Vorjahresquartal liegt"
    return "\n".join((z1, z2, z3, z4, z5))


def kriterien_satz() -> str:
    return (f"Quartalszahlen, die die Kriterien erfüllen: Umsatzwachstum gegen das Vorjahresquartal mindestens "
            f"{zahl(UMSATZ_WACHSTUM_MIN, 0)} Prozent, Kurs ab {zahl(KURS_MIN, 0)} Dollar, Börsenwert ab "
            f"{zahl(MARKTKAP_MIN_MRD * 1000, 0)} Millionen Dollar, Jahresvolatilität ab {zahl(VOLA_MIN, 0)} "
            f"Prozent; dazu Konsens geschlagen, beim EPS ab plus {zahl(KONSENS_EPS_MIN, 0)} Prozent oder beim "
            f"Umsatz ab plus {zahl(KONSENS_UMSATZ_MIN, 0)} Prozent, oder Wachstum um mindestens "
            f"{zahl(BESCHLEUNIGUNG_MIN, 0)} Prozentpunkte beschleunigt. Kein Alarm, keine Kaufzeile.")


def treffer_eintrag(b, vergleich, jetzt) -> dict:
    """Was der Stand je Treffer behaelt: genug, um den Tagesbericht in jedem
    Lauf neu zu bauen, ohne SEC, Yahoo oder Mistral noch einmal zu fragen."""
    return {"accession": b["accession"], "ticker": b["ticker"], "zeit": jetzt.astimezone(dt.timezone.utc).isoformat(),
            "beide": bool(b["a"] and b["b"]), "umsatz_ue": b["umsatz_ue"], "text": absatz_text(b, vergleich, jetzt)}


def _mehrzahl(n, einzahl, mehrzahl):
    return f"{n} {einzahl if n == 1 else mehrzahl}"


def tagesbericht(tag, eintrag, jetzt) -> tuple:
    """(Titel, Absaetze, Kennung) des Earnings-Tagesberichts zum New Yorker
    Tag tag (JJJJ-MM-TT). Die Treffer stehen neueste zuerst, innerhalb eines
    Laufs die mit beiden Bedingungen zuerst, dann nach der Abweichung beim
    Umsatz. Ohne Treffer ist es die Meldung, dass keine Aktie die Kriterien
    erfuellt hat (Antwort 14). Die Kennung waechst mit den Treffern."""
    datum = _datum(tag)
    gelesen = int(eintrag.get("gelesen") or 0)
    treffer = sorted(eintrag.get("treffer") or [],
                     key=lambda t: (-(_utc(t.get("zeit")) or jetzt).timestamp(), not t.get("beide"),
                                    -(_f(t.get("umsatz_ue")) if _f(t.get("umsatz_ue")) is not None else -999.0)))
    frueher = max(0, int(eintrag.get("berichtet") or 0) - len(treffer))
    if not treffer and not frueher:
        if gelesen:
            satz = (f"Am {datum} wurden in New York {_mehrzahl(gelesen, 'Quartalsmeldung', 'Quartalsmeldungen')} "
                    "gelesen; keine Aktie hat die Kriterien des Earnings-Berichts erfüllt.")
        else:
            satz = (f"Am {datum} kamen in New York keine Quartalszahlen; keine Aktie hat die Kriterien des "
                    "Earnings-Berichts erfüllt.")
        return f"Earnings vom {datum}: keine Aktie erfüllt die Kriterien", [satz], ["leer", tag]
    letzte = max((_utc(t.get("zeit")) for t in treffer if _utc(t.get("zeit"))), default=jetzt)
    n = len(treffer) + frueher
    titel = (f"Earnings vom {datum}: {_mehrzahl(n, 'Aktie', 'Aktien')}, zuletzt ergänzt um "
             f"{letzte.astimezone(WIEN):%H:%M} Uhr Wiener Zeit")
    stand_satz = (f"Gelesen am {datum} in New York: {_mehrzahl(gelesen, 'Quartalsmeldung', 'Quartalsmeldungen')}, "
                  f"davon {n} im Bericht; Stand {jetzt.astimezone(WIEN):%H:%M} Uhr Wiener Zeit. Neue Treffer stehen "
                  "oben, darin zuerst die Aktien, die beide Bedingungen erfüllen.")
    if frueher:
        # Der Tag der Umstellung: Was vorher gefunden wurde, steht in den
        # Berichten je Lauf von frueher an diesem Tag, nicht im Stand.
        stand_satz += (f" {_mehrzahl(frueher, 'Aktie steht', 'Aktien stehen')} in den früheren Earnings-Berichten "
                       "dieses Tages.")
    absaetze = [kriterien_satz(), stand_satz] + [f"{i}. {t.get('text')}" for i, t in enumerate(treffer, 1)]
    return titel, absaetze, ["treffer", tag] + sorted(str(t.get("accession")) for t in treffer)


# ---------------------------------------------------------------------------
# Lauf
# ---------------------------------------------------------------------------

def tabelle_laden(url=TABELLE_URL):
    """{Ticker: {kurs, marktkap_mrd, name}} aus der Scanner-Tabelle."""
    import pandas as pd
    df = pd.read_parquet(url)
    raus = {}
    for z in df[[c for c in ("ticker", "kurs", "marktkap_mrd", "name") if c in df.columns]].to_dict("records"):
        t = str(z.get("ticker") or "").upper()
        if t:
            raus[t] = z
            raus.setdefault(t.replace(".", "-"), z)
            raus.setdefault(t.replace("-", "."), z)
    return raus


def vorabwerte_dateien(daten, seit_tage=7):
    grenze = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=seit_tage)).isoformat()
    raus = []
    for p in glob.glob(os.path.join(daten, "vorabwerte", "20*", "*.json")):
        try:
            with io.open(p, encoding="utf-8") as h:
                e = json.load(h)
        except (OSError, ValueError):
            continue
        if (e.get("filing_utc") or "") >= grenze and e.get("status") in ("vorlaeufig", "unsicher", "ersetzt"):
            raus.append(e)
    raus.sort(key=lambda e: e.get("sec_akzeptanz_utc") or e.get("filing_utc") or "")
    return raus


def _json_lesen(p, vorgabe):
    try:
        with io.open(p, encoding="utf-8") as h:
            return json.load(h)
    except (OSError, ValueError):
        return vorgabe


def _json_schreiben(p, d):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with io.open(p, "w", encoding="utf-8") as h:
        json.dump(d, h, ensure_ascii=False, indent=1, sort_keys=True)


def lauf(daten, trocken=False, jetzt=None, log=print, firma_laden=None, tabelle=None, schluesse_holen=None,
         ausblick=None, pressetext=None, ablegen=None):
    """Bewertet jede noch nicht bewertete Vorabwert-Datei der letzten Tage und
    legt die aufgenommenen als EINEN Bericht ab."""
    jetzt = jetzt or dt.datetime.now(dt.timezone.utc)
    stand_pfad = os.path.join(daten, STAND)
    erster = not os.path.exists(stand_pfad)
    stand = _json_lesen(stand_pfad, {})
    bewertet = dict(stand.get("bewertet") or {})
    neu = [e for e in vorabwerte_dateien(daten) if e.get("accession") and e["accession"] not in bewertet]
    if erster and neu:
        # DER ERSTE LAUF berichtet nur den laufenden Tag (New York): Ohne Stand
        # waeren alle Vorabwerte der letzten sieben Tage neu und kaemen auf
        # einmal in den Bericht, genau die Berichtsflut, die Gerhard nicht will.
        # Die aelteren gelten als Ausgangsstand und werden nicht berichtet.
        heute_ny = jetzt.astimezone(NY).date()
        alt = [e for e in neu if (_utc(e.get("filing_utc")) or jetzt).astimezone(NY).date() < heute_ny]
        for e in alt:
            bewertet[e["accession"]] = {"zeit": jetzt.isoformat(), "aufgenommen": False,
                                        "gruende": ["Ausgangsstand"], "ticker": e.get("ticker")}
        neu = [e for e in neu if e not in alt]
        log(f"Earnings: erster Lauf, {len(alt)} aeltere Vorabwert-Dateien als Ausgangsstand, nicht berichtet")
    log(f"Earnings: {len(neu)} neue Vorabwert-Dateien")
    if tabelle is None and neu:
        try:
            tabelle = tabelle_laden()
        except Exception as ex:  # noqa: BLE001
            log(f"Earnings: Scanner-Tabelle nicht lesbar: {type(ex).__name__}: {str(ex)[:120]}")
            return {"neu": len(neu), "aufgenommen": 0, "abbruch": "Scanner-Tabelle nicht lesbar"}
    if firma_laden is None and neu:
        import vorabwerte_8k as v8
        firma_laden = v8._zeilen_lader()
    schluesse_holen = schluesse_holen or yahoo_schluesse
    if ausblick is None:
        ausblick = ausblick_fragen
    if pressetext is None:
        def pressetext(cik, acc):
            import pressetexte as pt
            return pt.text_lesen(daten, cik, acc)
    aufgenommen = []
    # DIE BLACKLIST (Gerhard, 30.09.2026, Antworten 8 und 13): Eine gesperrte
    # Aktie wird nicht bewertet und steht in keinem Bericht; ihre Datei gilt als
    # erledigt. Ins Protokoll nur die Zahl, das Protokoll ist oeffentlich.
    import blacklist
    gesperrt = 0
    for e in neu:
        if blacklist.gesperrt(e.get("ticker")):
            bewertet[e["accession"]] = {"zeit": jetzt.isoformat(), "aufgenommen": False, "gruende": ["Blacklist"],
                                        "ticker": e.get("ticker")}
            gesperrt += 1
            continue
        ok, harte = vorpruefung(e, tabelle)
        if not ok:
            bewertet[e["accession"]] = {"zeit": jetzt.isoformat(), "aufgenommen": False, "gruende": harte,
                                        "ticker": e.get("ticker")}
            continue
        try:
            zeilen = firma_laden(e.get("cik"))
        except Exception as ex:  # noqa: BLE001
            log(f"  {e.get('ticker')}: SEC nicht lesbar, naechster Lauf: {str(ex)[:100]}")
            continue
        try:
            schl = schluesse_holen(e.get("ticker"))
        except Exception as ex:  # noqa: BLE001
            log(f"  {e.get('ticker')}: Kurse nicht lesbar, naechster Lauf: {str(ex)[:100]}")
            continue
        b = bewerten(e, zeilen, tabelle, schl)
        vergleich = None
        if b["aufnehmen"]:
            text = None
            try:
                text = pressetext(e.get("cik"), e.get("accession"))
            except Exception as ex:  # noqa: BLE001
                log(f"  {b['ticker']}: Pressetext nicht lesbar: {str(ex)[:100]}")
            g = ausblick(text) if text else None
            perioden = konsens_perioden_vor(daten, b["ticker"], b["filing_utc"])
            vergleich = ausblick_vergleich(g, perioden, b["periodenende"])
            aufgenommen.append((b, vergleich))
        bewertet[e["accession"]] = {"zeit": jetzt.isoformat(), "aufgenommen": b["aufnehmen"], "gruende": b["gruende"],
                                    "ticker": b["ticker"], "ausblick": {f"{k[0]}_{k[1]}": v for k, v in
                                                                        (vergleich or {}).items()}}
        log(f"  {b['ticker']}: {'im Bericht' if b['aufnehmen'] else 'nicht im Bericht'}"
            + (f", {', '.join(b['gruende'])}" if b["gruende"] else ""))
    if gesperrt:
        log(f"  Blacklist: {gesperrt} Aktie(n) gesperrt, nicht bewertet.")
    elif blacklist.fehler():
        log(f"  ACHTUNG: Blacklist nicht lesbar ({blacklist.fehler()}); es ist keine Aktie gesperrt.")
    ergebnis = {"neu": len(neu), "aufgenommen": len(aufgenommen), "abbruch": None, "gesperrt": gesperrt}
    ny = jetzt.astimezone(NY)
    tag = ny.date().isoformat()
    tage = stand.get("tage") or {}
    heute = tage.setdefault(tag, {"gelesen": 0, "berichtet": 0})
    heute["gelesen"] += len(neu)
    heute["berichtet"] += len(aufgenommen)
    heute.setdefault("treffer", []).extend(treffer_eintrag(b, v, jetzt) for b, v in aufgenommen)
    ablegen = ablegen or _ablegen
    import berichte
    import boersentage
    # Welche Tagesberichte jetzt zu schreiben sind: der heutige bei neuen
    # Treffern, und jeder Handelstag, dessen Abend (19:30 New York) vorbei ist
    # und noch nicht gemeldet wurde (Antwort 14), heute oder nachgeholt.
    faellig = [tag] if aufgenommen else []
    abend = []
    for t in sorted(tage):
        e = tage[t]
        if e.get("abend_gemeldet") or e.get("keine_gemeldet"):
            continue
        try:
            d = dt.date.fromisoformat(t)
        except ValueError:
            continue
        schluss = dt.datetime(d.year, d.month, d.day, ABEND_SCHLUSS_NY // 60, ABEND_SCHLUSS_NY % 60, tzinfo=NY)
        if not boersentage.ist_handelstag(d) or jetzt < schluss or jetzt - schluss > dt.timedelta(days=NACHHOLEN_TAGE):
            continue
        if jetzt >= berichte.leerung_nach_handelstag(d):
            e["abend_gemeldet"] = True        # stuende schon nicht mehr im Reiter
            continue
        abend.append(t)
        if t not in faellig:
            faellig.append(t)
    for t in faellig:
        titel, absaetze, kennung = tagesbericht(t, tage[t], jetzt)
        if t == tag:
            ergebnis["titel"] = titel
        if trocken:
            log(titel)
            for a in absaetze:
                log(a)
        elif not ablegen(titel, absaetze, jetzt, log, schluessel=f"earnings-{t}", kennung_aus=kennung,
                         bis=berichte.leerung_nach_handelstag(dt.date.fromisoformat(t))):
            return {**ergebnis, "abbruch": "Bericht nicht abgelegt"}
        if t in abend:
            tage[t]["abend_gemeldet"] = True
    if not trocken:
        alt = (jetzt - dt.timedelta(days=30)).isoformat()
        stand["bewertet"] = {k: v for k, v in bewertet.items() if v.get("zeit", "") >= alt}
        stand["tage"] = {k: v for k, v in tage.items() if k >= (ny.date() - dt.timedelta(days=30)).isoformat()}
        # Die Texte der Treffer braucht nur der Bericht, und der steht hoechstens
        # bis zum naechsten Handelstag; danach bleiben die Zahlen.
        grenze = (ny.date() - dt.timedelta(days=TREFFER_TAGE)).isoformat()
        for k, v in stand["tage"].items():
            if k < grenze and v.get("treffer"):
                v["treffer"] = []
        _json_schreiben(stand_pfad, stand)
    return ergebnis


def _ablegen(titel, absaetze, jetzt, log, schluessel=None, kennung_aus=None, bis=None):
    import berichte
    return berichte.ablegen(ART, titel, absaetze, zeit=jetzt, melder=log, schluessel=schluessel,
                            kennung_aus=kennung_aus, bis=bis)


def messen(daten, tage=10, log=print, firma_laden=None, tabelle=None, schluesse_holen=None):
    """Wie viele Aktien der Bericht je Tag enthalten haette (Gerhards Auftrag):
    alle Vorabwert-Dateien der letzten tage Tage, ohne Ausblick und ohne
    Ablage. Kurs und Boersenwert stammen aus der Scanner-Tabelle von heute."""
    import collections
    tabelle = tabelle if tabelle is not None else tabelle_laden()
    if firma_laden is None:
        import vorabwerte_8k as v8
        firma_laden = v8._zeilen_lader()
    schluesse_holen = schluesse_holen or yahoo_schluesse
    import blacklist
    je_tag = collections.defaultdict(collections.Counter)
    namen = collections.defaultdict(list)
    for e in vorabwerte_dateien(daten, seit_tage=tage):
        z = _utc(e.get("sec_akzeptanz_utc") or e.get("filing_utc"))
        if z is None:
            continue
        tag = z.astimezone(NY).date().isoformat()
        je_tag[tag]["gelesen"] += 1
        if blacklist.gesperrt(e.get("ticker")):
            je_tag[tag]["Blacklist"] += 1          # nur die Zahl, das Protokoll ist oeffentlich
            continue
        ok, harte = vorpruefung(e, tabelle)
        if not ok:
            for g in harte:
                je_tag[tag][g] += 1
            continue
        try:
            b = bewerten(e, firma_laden(e.get("cik")), tabelle, schluesse_holen(e.get("ticker")))
        except Exception:  # noqa: BLE001
            je_tag[tag]["nicht pruefbar"] += 1
            continue
        for g in b["gruende"]:
            je_tag[tag][g] += 1
        if b["aufnehmen"]:
            je_tag[tag]["im Bericht"] += 1
            je_tag[tag]["beide"] += 1 if (b["a"] and b["b"]) else 0
            je_tag[tag]["nur Konsens"] += 1 if (b["a"] and not b["b"]) else 0
            je_tag[tag]["nur Beschleunigung"] += 1 if (b["b"] and not b["a"]) else 0
            namen[tag].append(b["ticker"])
    for tag in sorted(je_tag):
        c = je_tag[tag]
        log(f"{tag}: {c['gelesen']} Quartalsmeldungen gelesen, {c['im Bericht']} im Bericht "
            f"(beide {c['beide']}, nur Konsens {c['nur Konsens']}, nur Beschleunigung {c['nur Beschleunigung']}); "
            "ausgeschlossen: " + ", ".join(f"{k} {v}" for k, v in sorted(c.items())
                                            if k not in ("gelesen", "im Bericht", "beide", "nur Konsens",
                                                         "nur Beschleunigung"))
            + (f"; im Bericht: {', '.join(namen[tag])}" if namen[tag] else ""))
    return {t: dict(c) for t, c in je_tag.items()}


# ---------------------------------------------------------------------------
# Selbsttest (ohne Netz)
# ---------------------------------------------------------------------------

def _beispiel(**aend):
    e = {"ticker": "ACME", "name": "Acme Corp", "cik": 1, "accession": "0000000001-26-000001",
         "filing_utc": "2026-10-01T20:05:00+00:00", "sec_akzeptanz_utc": "2026-10-01T20:05:12+00:00",
         "status": "vorlaeufig", "pruefung": [],
         "werte": {"periodenende": "2026-09-30", "umsatz": 1.36e9, "eps_verwaessert": 0.71, "eps_bereinigt": 0.85},
         "vorjahr": {"umsatz": 1.0e9, "eps_verwaessert": 0.50},
         "ueberraschung": {"periode_passt": True, "umsatz_konsens": 1.30e9, "umsatz_prozent": 4.62,
                           "eps_konsens": 0.80, "eps_prozent": 6.25, "eps_basis": "bereinigt"}}
    e.update(aend)
    return e


def _zeilen(u_vorq=1.2e9, u_vorq_vj=1.0e9, e_vorq=0.60, e_vorq_vj=0.50):
    return [{"typ": "Q", "kennzahl": "umsatz", "end": "2026-06-30", "wert_erst": u_vorq},
            {"typ": "Q", "kennzahl": "umsatz", "end": "2025-06-30", "wert_erst": u_vorq_vj},
            {"typ": "Q", "kennzahl": "eps_verwaessert", "end": "2026-06-30", "wert_erst": e_vorq},
            {"typ": "Q", "kennzahl": "eps_verwaessert", "end": "2025-06-30", "wert_erst": e_vorq_vj}]


def selbsttest() -> int:
    fehler = []

    def p(name, ok, zusatz=""):
        print(f"  {'OK    ' if ok else 'FEHLER'} {name}" + (f" ({zusatz})" if zusatz and not ok else ""))
        if not ok:
            fehler.append(name)

    print("earnings_bericht.py, Selbsttest")
    tab = {"ACME": {"kurs": 45.1, "marktkap_mrd": 3.2}, "KLEIN": {"kurs": 9.0, "marktkap_mrd": 0.4}}
    import random
    rnd = random.Random(7)
    kurse = [100.0]
    for _ in range(300):
        kurse.append(kurse[-1] * math.exp(rnd.gauss(0, 0.02)))
    v = jahresvola(kurse)
    p("Jahresvolatilitaet: zwei Prozent Tagesschwankung ergeben rund 32 Prozent im Jahr", v is not None and 27 < v < 37,
      str(v))
    p("Jahresvolatilitaet braucht 253 Schluesse", jahresvola(kurse[:200]) is None)
    ruhig = [100.0 + 0.01 * (i % 2) for i in range(300)]
    p("Ein ruhiger Wert liegt unter 10 Prozent", jahresvola(ruhig) < VOLA_MIN, str(jahresvola(ruhig)))
    p("Vorquartal: Wachstum aus der Erstfassung beider Quartale",
      abs(vorquartal_wachstum(_zeilen(), "2026-09-30", "umsatz") - 20.0) < 1e-9)
    b = bewerten(_beispiel(), _zeilen(), tab, kurse)
    p("Beispiel: Umsatz plus 36 nach plus 20 Prozent, also 16 Prozentpunkte schneller",
      abs(b["umsatz_wachstum"] - 36.0) < 1e-9 and abs(b["umsatz_beschl"] - 16.0) < 1e-9 and b["b_umsatz"])
    p("Beispiel: EPS plus 42 nach plus 20 Prozent", abs(b["eps_wachstum"] - 42.0) < 1e-9 and b["b_eps"])
    p("Konsens geschlagen beim Umsatz ab plus 4 und beim EPS ab plus 3 Prozent", b["a_umsatz"] and b["a_eps"])
    p("Beispiel kommt in den Bericht", b["aufnehmen"], str(b["gruende"]))
    b2 = bewerten(_beispiel(ueberraschung={"periode_passt": True, "umsatz_prozent": 3.9, "eps_prozent": 2.9,
                                           "eps_basis": "bereinigt"}), _zeilen(u_vorq=1.4e9), tab, kurse)
    p("Knapp verfehlt: plus 3,9 beim Umsatz und plus 2,9 beim EPS ist kein Konsens geschlagen",
      not b2["a_umsatz"] and not b2["a_eps"])
    p("Beschleunigung allein reicht: EPS 22 Prozentpunkte schneller", b2["b_eps"] and b2["aufnehmen"],
      str(b2["gruende"]))
    b3 = bewerten(_beispiel(ueberraschung={"periode_passt": True, "umsatz_prozent": 1.0, "eps_prozent": 1.0}),
                  _zeilen(u_vorq=1.5e9, e_vorq=0.75), tab, kurse)
    p("Weder Konsens noch Beschleunigung: nicht im Bericht", not b3["aufnehmen"]
      and "weder Konsens geschlagen noch Beschleunigung" in b3["gruende"])
    b4 = bewerten(_beispiel(werte={"periodenende": "2026-09-30", "umsatz": 1.15e9, "eps_verwaessert": 0.71}),
                  _zeilen(), tab, kurse)
    p("Unter 20 Prozent Umsatzwachstum: nicht im Bericht", not b4["aufnehmen"] and "Umsatzwachstum" in b4["gruende"])
    b5 = bewerten(_beispiel(ticker="KLEIN"), _zeilen(), tab, kurse)
    p("Kurs unter 15 Dollar oder Boersenwert unter 700 Millionen: nicht im Bericht",
      not b5["aufnehmen"] and "Kurs oder Börsenwert" in b5["gruende"])
    b6 = bewerten(_beispiel(), _zeilen(), tab, ruhig)
    p("Jahresvolatilitaet unter 10 Prozent: nicht im Bericht", not b6["aufnehmen"] and "Volatilität" in b6["gruende"])
    b7 = bewerten(_beispiel(status="unsicher", pruefung=["Umsatz 36 Prozent neben dem Vorjahresquartal"]),
                  _zeilen(), tab, kurse)
    p("Unsicher nur wegen des Umsatzsprungs: bewertet und vermerkt", b7["aufnehmen"])
    b8 = bewerten(_beispiel(status="unsicher", pruefung=["Modell meldet bereinigte statt amtliche Zahlen"]),
                  _zeilen(), tab, kurse)
    p("Aus anderem Grund unsicher: nicht im Bericht", not b8["aufnehmen"] and "Vorabwert unsicher" in b8["gruende"])
    b9 = bewerten(_beispiel(ueberraschung={"periode_passt": False, "umsatz_prozent": 30.0, "eps_prozent": 30.0}),
                  _zeilen(u_vorq=1.4e9, e_vorq=0.75), tab, kurse)
    p("Konsens fuer ein anderes Quartal zaehlt nicht als geschlagen", not b9["a"])
    # Ausblick
    g = {"quartal_umsatz_tief": 1.30e9, "quartal_umsatz_hoch": 1.35e9, "quartal_eps_tief": None,
         "quartal_eps_hoch": None, "quartal_eps_bereinigt": None, "quartal_umsatz_wachstum_tief": None,
         "quartal_umsatz_wachstum_hoch": None,
         "jahr_umsatz_tief": None, "jahr_umsatz_hoch": None, "jahr_umsatz_wachstum_tief": 30.0,
         "jahr_umsatz_wachstum_hoch": 32.0, "jahr_eps_tief": 3.10, "jahr_eps_hoch": 3.20, "jahr_eps_bereinigt": True}
    perioden = {"+1q": {"periodenende": "2026-12-31", "umsatz_avg": 1.28e9, "eps_avg": 0.88},
                "0y": {"periodenende": "2026-12-31", "umsatz_avg": 4.8e9, "eps_avg": 3.05, "umsatz_vorjahr": 3.7e9},
                "+1y": {"periodenende": "2027-12-31", "umsatz_avg": 6.0e9, "eps_avg": 4.0}}
    vg = ausblick_vergleich(g, perioden, "2026-09-30")
    q = vg.get(("quartal", "umsatz"))
    p("Ausblick: bei einer Spanne zaehlt die Mitte, gegen den Konsens des naechsten Quartals",
      q and abs(q["mitte"] - 1.325e9) < 1 and abs(q["abweichung"] - (1.325 / 1.28 - 1) * 100) < 1e-6
      and q["periode"] == "+1q")
    j = vg.get(("jahr", "umsatz"))
    p("Ausblick nur als Wachstum: Mitte aus dem Vorjahreswert des Konsens",
      j and j["quelle"] == "wachstum" and abs(j["mitte"] - 3.7e9 * 1.31) < 1 and j["periode"] == "0y")
    p("Ausblick EPS des Jahres gegen 0y", abs(vg[("jahr", "eps")]["abweichung"] - (3.15 / 3.05 - 1) * 100) < 1e-6)
    vg4 = ausblick_vergleich(g, perioden, "2026-12-31")
    p("Schliesst das gemeldete Quartal das Geschaeftsjahr ab, gilt fuer das Jahr +1y",
      vg4[("jahr", "eps")]["periode"] == "+1y")
    p("Ohne Ausblick kein Vergleich", ausblick_vergleich(None, perioden, "2026-09-30") == {})
    lang = "Kopf " * 3000 + " Ergebnis " * 3000 + " Fourth Quarter 2026 Outlook: revenue of $1.30 billion " + "x " * 9000
    kurz = ausblick_text(lang)
    p("Der Text fuer den Ausblick behaelt die Stelle des Ausblicks", "Fourth Quarter 2026 Outlook" in kurz
      and len(kurz) <= 30000)
    # Der Tagesbericht (Antworten 10, 13 und 14 vom 01.10.2026)
    z1 = dt.datetime(2026, 10, 1, 20, 30, tzinfo=dt.timezone.utc)
    z2 = dt.datetime(2026, 10, 1, 21, 0, tzinfo=dt.timezone.utc)
    b2x = dict(b2, ticker="BBB", name="Beta Inc", accession="0000000001-26-000003", umsatz_ue=9.0)
    tag_e = {"gelesen": 7, "berichtet": 3,
             "treffer": [treffer_eintrag(b2x, None, z1), treffer_eintrag(b, vg, z1),
                         treffer_eintrag(dict(b2, accession="0000000001-26-000004", ticker="CCC", name="Gamma Corp"),
                                         None, z2)]}
    titel, absaetze, kennung = tagesbericht("2026-10-01", tag_e, z2)
    p("Tagesbericht: Titel mit Tag, Zahl und letzter Ergaenzung",
      titel == "Earnings vom 01.10.2026: 3 Aktien, zuletzt ergänzt um 23:00 Uhr Wiener Zeit", titel)
    p("Tagesbericht: gelesen, im Bericht und Stand",
      absaetze[1].startswith("Gelesen am 01.10.2026 in New York: 7 Quartalsmeldungen, davon 3 im Bericht; Stand "
                             "23:00 Uhr Wiener Zeit."), absaetze[1])
    p("Tagesbericht: neueste Treffer oben, im selben Lauf beide Bedingungen zuerst, markiert und mit Uhrzeit",
      absaetze[2].startswith("1. CCC, Gamma Corp; aufgenommen um 23:00 Uhr Wiener Zeit;")
      and absaetze[3].startswith("2. ACME, Acme Corp; beide Bedingungen erfüllt; aufgenommen um 22:30 Uhr Wiener Zeit;")
      and absaetze[4].startswith("3. BBB, Beta Inc; aufgenommen um 22:30 Uhr"), "\n".join(absaetze[2:])[:300])
    _t2, _a2, kennung2 = tagesbericht("2026-10-01", dict(tag_e, gelesen=9), z2 + dt.timedelta(hours=2))
    p("Tagesbericht: neue Zahl gelesener, dieselbe Kennung", kennung2 == kennung and "9 Quartalsmeldungen" in _a2[1])
    _t3, _a3, kennung3 = tagesbericht("2026-10-01", dict(tag_e, treffer=tag_e["treffer"][:2], berichtet=2), z2)
    p("Tagesbericht: ein Treffer mehr, eine neue Kennung", kennung3 != kennung)
    tl, al, kl = tagesbericht("2026-10-02", {"gelesen": 4, "berichtet": 0}, z2)
    p("Leermeldung mit gelesenen Zahlen", tl == "Earnings vom 02.10.2026: keine Aktie erfüllt die Kriterien"
      and al == ["Am 02.10.2026 wurden in New York 4 Quartalsmeldungen gelesen; keine Aktie hat die Kriterien des "
                 "Earnings-Berichts erfüllt."] and kl == ["leer", "2026-10-02"], str(al))
    _tl, al0, _kl = tagesbericht("2026-10-02", {"gelesen": 0, "berichtet": 0}, z2)
    p("Leermeldung ohne Quartalszahlen", al0 == ["Am 02.10.2026 kamen in New York keine Quartalszahlen; keine Aktie "
                                                 "hat die Kriterien des Earnings-Berichts erfüllt."], str(al0))
    tu, au, _ku = tagesbericht("2026-10-01", {"gelesen": 5, "berichtet": 2, "treffer": []}, z2)
    p("Tag der Umstellung: frueher Gefundenes steht nicht als Leermeldung da",
      tu.startswith("Earnings vom 01.10.2026: 2 Aktien") and "2 Aktien stehen in den früheren" in au[1], tu)
    a1 = absatz(1, b, vg)
    p("Je Aktie: beide Bedingungen markiert, Konsens und Wachstum mit Vorzeichen, Ausblick, KI vorlaeufig",
      a1.startswith("1. ACME, Acme Corp; beide Bedingungen erfüllt; Quartal bis 30.09.2026") and "erfüllt: Konsens geschlagen beim Umsatz und "
      "beim EPS, Beschleunigung beim Umsatz und beim EPS" in a1 and "plus 4,6 Prozent, erfüllt" in a1
      and "Umsatz plus 36 Prozent nach plus 20 Prozent im Quartal davor, plus 16 Prozentpunkte, erfüllt" in a1
      and "Ausblick, KI, vorläufig: nächstes Quartal Umsatz 1,30 Milliarden Dollar bis 1,35 Milliarden Dollar" in a1
      and "Gesamtjahr Umsatz plus 30,0 Prozent bis plus 32,0 Prozent" in a1 and "Gegen den Konsens, KI, vorläufig" in a1,
      a1)
    p("Eine Aktie ohne Ausblick", "Ausblick, KI, vorläufig: keiner genannt" in absatz(2, b2, None))
    verboten = re.compile(r"[()–—|]")
    p("Kein Gedankenstrich, kein senkrechter Strich, keine Klammern im Bericht",
      not any(verboten.search(x) for x in [titel] + absaetze), str([x for x in absaetze if verboten.search(x)][:1]))
    # Lauf mit Attrappen
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "vorabwerte", "2026"))
        for i, e in enumerate((_beispiel(), _beispiel(ticker="KLEIN", accession="0000000001-26-000002"))):
            with io.open(os.path.join(d, "vorabwerte", "2026", f"{i}.json"), "w", encoding="utf-8") as h:
                json.dump({**e, "filing_utc": dt.datetime.now(dt.timezone.utc).isoformat()}, h)
        abgelegt = []

        def ablage(t, a, j, log, **k):
            abgelegt.append((t, a, k))
            return True
        import boersentage
        # Ein Handelstag, 10:00 New York; die Vorabwerte von heute
        frueh = dt.datetime.combine(boersentage.letzter_handelstag(dt.datetime.now(NY).date()), dt.time(10, 0),
                                    tzinfo=NY)
        for name in os.listdir(os.path.join(d, "vorabwerte", "2026")):
            pf = os.path.join(d, "vorabwerte", "2026", name)
            e0 = _json_lesen(pf, {})
            e0["filing_utc"] = (frueh - dt.timedelta(hours=1)).astimezone(dt.timezone.utc).isoformat()
            _json_schreiben(pf, e0)
        jetzt1 = frueh.astimezone(dt.timezone.utc)
        jetzt_tag = frueh.date().isoformat()
        r = lauf(d, jetzt=jetzt1, firma_laden=lambda cik: _zeilen(), tabelle=tab, schluesse_holen=lambda t: kurse,
                 ausblick=lambda text: g, pressetext=lambda cik, acc: "Outlook ...", ablegen=ablage,
                 log=lambda *x: None)
        p("Lauf: zwei neue Dateien, eine im Tagesbericht, mit Schluessel, Kennung und Frist",
          r["neu"] == 2 and r["aufgenommen"] == 1 and len(abgelegt) == 1 and "ACME" in abgelegt[0][1][2]
          and abgelegt[0][2]["schluessel"] == f"earnings-{jetzt_tag}"
          and abgelegt[0][2]["kennung_aus"] == ["treffer", jetzt_tag, "0000000001-26-000001"]
          and abgelegt[0][2]["bis"] > jetzt1, str(r) + str(abgelegt[:1])[:200])
        r2 = lauf(d, jetzt=jetzt1 + dt.timedelta(minutes=30), firma_laden=lambda cik: _zeilen(), tabelle=tab,
                  schluesse_holen=lambda t: kurse, ausblick=lambda text: g, pressetext=lambda cik, acc: "x",
                  ablegen=ablage, log=lambda *x: None)
        p("Zweiter Lauf: nichts Neues, nichts geschrieben", r2["neu"] == 0 and len(abgelegt) == 1, str(r2))
        spaet = frueh.replace(hour=19, minute=45)
        r3 = lauf(d, jetzt=spaet.astimezone(dt.timezone.utc), firma_laden=lambda cik: _zeilen(), tabelle=tab,
                  schluesse_holen=lambda t: kurse, ausblick=lambda text: g, pressetext=lambda cik, acc: "x",
                  ablegen=ablage, log=lambda *x: None)
        p("Abend: der Tagesbericht mit dem Stand des Abends, dieselbe Kennung, also nicht wieder ungelesen",
          len(abgelegt) == 2 and abgelegt[1][2]["kennung_aus"] == abgelegt[0][2]["kennung_aus"]
          and "2 Quartalsmeldungen, davon 1 im Bericht" in abgelegt[1][1][1], str(r3))
        lauf(d, jetzt=spaet.astimezone(dt.timezone.utc) + dt.timedelta(minutes=15), firma_laden=lambda cik: _zeilen(),
             tabelle=tab, schluesse_holen=lambda t: kurse, ausblick=lambda text: g, pressetext=lambda cik, acc: "x",
             ablegen=ablage, log=lambda *x: None)
        p("Der Abend kommt einmal am Tag", len(abgelegt) == 2)
        # Ein Handelstag ohne Treffer: die Leermeldung, einmal; ein Feiertag: nichts
        stand = _json_lesen(os.path.join(d, STAND), {})
        stand["tage"] = {"2026-10-07": {"gelesen": 3, "berichtet": 0}}
        _json_schreiben(os.path.join(d, STAND), stand)
        abgelegt.clear()
        lauf(d, jetzt=dt.datetime(2026, 10, 7, 19, 45, tzinfo=NY).astimezone(dt.timezone.utc),
             firma_laden=lambda cik: _zeilen(), tabelle=tab, schluesse_holen=lambda t: kurse,
             ausblick=lambda text: g, pressetext=lambda cik, acc: "x", ablegen=ablage, log=lambda *x: None)
        p("Leermeldung nach dem letzten Lauf des Abends, mit der Zahl der gelesenen",
          len(abgelegt) == 1 and abgelegt[0][0] == "Earnings vom 07.10.2026: keine Aktie erfüllt die Kriterien"
          and "3 Quartalsmeldungen gelesen" in abgelegt[0][1][0], str(abgelegt)[:200])
        # Ein ausgefallener Abend wird am naechsten Morgen nachgeholt, solange der Bericht noch stuende.
        # Die Zeit laeuft in diesem Teil nur vorwaerts: Der Stand vergisst Bewertungen nach 30 Tagen.
        stand = _json_lesen(os.path.join(d, STAND), {})
        stand["tage"] = {"2026-10-08": {"gelesen": 0, "berichtet": 0}, "2026-10-05": {"gelesen": 2, "berichtet": 0}}
        _json_schreiben(os.path.join(d, STAND), stand)
        abgelegt.clear()
        lauf(d, jetzt=dt.datetime(2026, 10, 9, 6, 0, tzinfo=NY).astimezone(dt.timezone.utc),
             firma_laden=lambda cik: _zeilen(), tabelle=tab, schluesse_holen=lambda t: kurse,
             ausblick=lambda text: g, pressetext=lambda cik, acc: "x", ablegen=ablage, log=lambda *x: None)
        st9 = _json_lesen(os.path.join(d, STAND), {})
        p("Ein ausgefallener Abend wird nachgeholt, ein laengst geleerter nicht mehr",
          [x[0] for x in abgelegt] == ["Earnings vom 08.10.2026: keine Aktie erfüllt die Kriterien"]
          and st9["tage"]["2026-10-05"].get("abend_gemeldet") is True, str([x[0] for x in abgelegt]))
        stand = _json_lesen(os.path.join(d, STAND), {})
        stand["tage"] = {"2026-11-26": {"gelesen": 0, "berichtet": 0}}
        _json_schreiben(os.path.join(d, STAND), stand)
        abgelegt.clear()
        lauf(d, jetzt=dt.datetime(2026, 11, 26, 19, 45, tzinfo=NY).astimezone(dt.timezone.utc),
             firma_laden=lambda cik: _zeilen(), tabelle=tab, schluesse_holen=lambda t: kurse,
             ausblick=lambda text: g, pressetext=lambda cik, acc: "x", ablegen=ablage, log=lambda *x: None)
        p("An einem US-Boersenfeiertag keine Leermeldung", not abgelegt, str(abgelegt)[:200])
    # Der erste Lauf ohne Stand berichtet nur den laufenden Tag
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "vorabwerte", "2026"))
        jetzt0 = dt.datetime.now(dt.timezone.utc)
        for i, (e, alter) in enumerate(((_beispiel(), dt.timedelta(0)),
                                        (_beispiel(accession="0000000001-26-000009"), dt.timedelta(days=3)))):
            with io.open(os.path.join(d, "vorabwerte", "2026", f"{i}.json"), "w", encoding="utf-8") as h:
                json.dump({**e, "filing_utc": (jetzt0 - alter).isoformat()}, h)
        abgelegt = []
        r = lauf(d, firma_laden=lambda cik: _zeilen(), tabelle=tab, schluesse_holen=lambda t: kurse,
                 ausblick=lambda text: g, pressetext=lambda cik, acc: "x",
                 ablegen=lambda t, a, j, log, **k: abgelegt.append((t, a)) or True, log=lambda *x: None)
        st = _json_lesen(os.path.join(d, STAND), {})
        p("Erster Lauf ohne Stand: nur der laufende Tag im Bericht, aeltere als Ausgangsstand",
          r["neu"] == 1 and r["aufgenommen"] == 1 and len(abgelegt) == 1
          and (st.get("bewertet") or {}).get("0000000001-26-000009", {}).get("gruende") == ["Ausgangsstand"], str(r))
        r2 = lauf(d, firma_laden=lambda cik: _zeilen(), tabelle=tab, schluesse_holen=lambda t: kurse,
                  ausblick=lambda text: g, pressetext=lambda cik, acc: "x",
                  ablegen=lambda t, a, j, log, **k: abgelegt.append((t, a)) or True, log=lambda *x: None)
        p("Danach gilt der Stand: nichts Neues, kein zweiter Bericht", r2["neu"] == 0 and len(abgelegt) <= 2, str(r2))
    # Die Blacklist: nicht bewertet, nicht im Bericht, im Protokoll nur die Zahl
    import blacklist
    blacklist.setzen(["ACME"])
    try:
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "vorabwerte", "2026"))
            with io.open(os.path.join(d, "vorabwerte", "2026", "0.json"), "w", encoding="utf-8") as h:
                json.dump({**_beispiel(), "filing_utc": dt.datetime.now(dt.timezone.utc).isoformat()}, h)
            abgelegt, gesagt = [], []
            r = lauf(d, firma_laden=lambda cik: _zeilen(), tabelle=tab, schluesse_holen=lambda t: kurse,
                     ausblick=lambda text: g, pressetext=lambda cik, acc: "x",
                     ablegen=lambda t, a, j, log, **k: abgelegt.append((t, a)) or True, log=gesagt.append)
            p("Blacklist: eine gesperrte Aktie wird nicht bewertet und steht in keinem Bericht",
              r["neu"] == 1 and r["aufgenommen"] == 0 and r["gesperrt"] == 1 and not abgelegt, str(r))
            p("Blacklist: im Protokoll nur die Zahl, kein Kuerzel",
              "  Blacklist: 1 Aktie(n) gesperrt, nicht bewertet." in gesagt
              and not any("ACME" in str(x) for x in gesagt), str(gesagt))
    finally:
        blacklist.zuruecksetzen()
    print("Ergebnis:", "alles bestanden" if not fehler else f"{len(fehler)} Fehler")
    return 1 if fehler else 0


def main():
    ap = argparse.ArgumentParser(description="Earnings-Bericht im Reiter Berichte")
    ap.add_argument("--daten", default="daten")
    ap.add_argument("--trocken", action="store_true")
    ap.add_argument("--messen", type=int, default=0)
    ap.add_argument("--selbsttest", action="store_true")
    a = ap.parse_args()
    if a.selbsttest:
        return selbsttest()
    if a.messen:
        messen(a.daten, a.messen)
        return 0
    try:
        r = lauf(a.daten, trocken=a.trocken)
    except Exception as ex:  # noqa: BLE001
        r = {"abbruch": f"{type(ex).__name__}: {str(ex)[:200]}"}
    print(f"Earnings-Bericht: {r}")
    if r.get("abbruch") and not a.trocken:
        # Stoerungen bleiben auf ntfy (Gerhard, 30.09.2026 nachts); der Bericht
        # selbst steht nur im Reiter Berichte.
        import konsens_einfrieren as ke
        ke.push("Störung: Earnings-Bericht", r["abbruch"])
    return 1 if r.get("abbruch") else 0


if __name__ == "__main__":
    sys.exit(main())
