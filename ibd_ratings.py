#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IBD-RATINGS ALS NAEHERUNG: EPS, SMR, A/D und Composite in EINER Zeile
=====================================================================
Gerhards Antworten vom 12.09.2026: R20 (alle vier als eine Zeile, A/D als
Naeherung), R21 (AMTLICH starten, gekennzeichnet; Umstellung auf
bereinigte Zahlen, sobald sie aus den Pressemitteilungen vorliegen),
R22 (Notengrenzen nach der IBD-Kaufregel: A und B obere 40 Prozent, C
die Mitte, D und E untere 40 Prozent), W4 (Erstfassung der Bausteine),
W5 (Umsatzbegriff je Branche), W6 (die Quartale gelten, der Jahreswert
nur als Vermerk), W7 (14-Wochen-Quartale auf 13 Wochen umrechnen, mit
Kennzeichnung), Antwort 8 (Auslaender laufen voll mit, IFRS-Zahlen als
ungeprueft gekennzeichnet), Antwort 10 (keine Untergrenze, die Zahl der
Quartale IMMER sichtbar), Antwort 11 (acht Quartale).

WOHER DIE ZAHLEN KOMMEN
  Aus dem SEC-Fundament, das der Zweig fundament-phase1 als Release im
  Repo heliot ablegt (fundament_kennzahlen_<Jahr>.parquet, je Zeile eine
  Kennzahl je Firma und Periode, Quelle amtlich oder berechnet). Die
  Zuordnung Ticker zu CIK kommt aus dem SEC-Verzeichnis
  company_tickers.json; der Abruf braucht den User-Agent aus dem Secret
  SEC_USER_AGENT (nur im Actions-Lauf). Ohne ihn gibt es keine Ratings,
  und das steht dann so in der Datei.

WIE GERECHNET WIRD (Naeherung, per Mitschreiben zu verfeinern)
  EPS-Rang    Wachstum der zwei juengsten Quartale gegen das Vorjahres-
              quartal (je gedeckelt auf plus/minus 300 Prozent; ein
              Vorjahr im Minus und ein Quartal im Plus zaehlt als Wende
              mit plus 100 Prozent) plus das Wachstum der Jahreswerte ueber
              drei Jahre (W6: nur als Vermerk, das Jahr geht mit einem
              Viertel Gewicht ein). Perzentil gegen ALLE Firmen im
              Fundament (rund 17.000), 1 bis 99.
  SMR         Umsatzwachstum (Mittel der drei juengsten Quartale gegen
              Vorjahr), Nettomarge (juengstes Quartal), Eigenkapitalrendite
              (Jahresgewinn durch Eigenkapital); jede Groesse als Perzentil,
              das Mittel wieder als Perzentil, daraus die Note.
  A/D         Naeherung aus Kurs und Volumen (rs_universum: 13 Wochen,
              Volumen an Plus-Tagen gegen Volumen an Minus-Tagen), Note
              nach demselben Schluessel.
  Composite   Wie bei IBD: EPS und RS doppelt, dazu SMR, A/D und die Naehe
              zum 52-Wochen-Hoch; Perzentil gegen alle Aktien mit
              vollstaendigen Bausteinen. Fehlt ein Baustein, gibt es KEIN
              Composite, sondern die Nennung, was fehlt.

Aufruf:
  python ibd_ratings.py --bauen           im Nachtscan, schreibt ibd_ratings.json
  python ibd_ratings.py --selbsttest      ohne Netz
"""

import argparse
import bisect
import json
import os
import sys
from datetime import date, datetime, timedelta

from config import CFG

CFGR = CFG["ibd_ratings"]
DATEI = "ibd_ratings.json"
RELEASE_BASIS = "https://github.com/mat-schmuck/heliot/releases/latest/download/"
SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"
CACHE = os.path.join(".cache", "fundament")
KENNZAHLEN = ("umsatz", "eps_verwaessert", "nettogewinn", "eigenkapital",
              "zinsueberschuss", "provisionsertrag", "praemien_verdient", "mieterloese")
DECKEL = 3.0          # Wachstum je Quartal auf plus/minus 300 Prozent gedeckelt
WENDE = 1.0           # Vorjahr im Minus, heute im Plus: zaehlt wie plus 100 Prozent
QUARTAL_LANG_TAGE = 95   # ab hier gilt ein Quartal als 14-Wochen-Quartal (W7)


# ---------------------------------------------------------------------------
# Kleine Helfer
# ---------------------------------------------------------------------------

def note(perzentil, noten=None):
    """R22: A ab 80, B ab 60, C ab 40, D ab 20, sonst E."""
    if perzentil is None:
        return None
    noten = noten or CFGR["noten"]
    for n, grenze in sorted(noten.items(), key=lambda p: -p[1]):
        if perzentil >= grenze:
            return n
    return "E"


def perzentile(werte):
    """{Schluessel: Rohwert} zu {Schluessel: Perzentil 1 bis 99}: Anteil der
    STRIKT kleineren Werte (dieselbe Festlegung wie beim RS)."""
    gueltig = {k: float(v) for k, v in werte.items() if v is not None and v == v}
    if not gueltig:
        return {}
    sortiert = sorted(gueltig.values())
    n = len(sortiert)
    raus = {}
    for k, v in gueltig.items():
        rang = bisect.bisect_left(sortiert, v) / n * 100
        raus[k] = int(round(max(1, min(99, rang))))
    return raus


def wachstum(neu, alt):
    if neu is None or alt is None:
        return None
    if alt <= 0:
        return WENDE if neu > 0 else -WENDE
    return max(-DECKEL, min(DECKEL, neu / alt - 1))


def _dat(x):
    try:
        return date.fromisoformat(str(x)[:10])
    except (TypeError, ValueError):
        return None


def auf_13_wochen(start, end, wert):
    """W7: Ein 14-Wochen-Quartal wird mal 13 durch 14 gerechnet, mit
    Kennzeichnung. Rueckgabe (wert, umgerechnet)."""
    s, e = _dat(start), _dat(end)
    if s is None or e is None or wert is None:
        return wert, False
    if (e - s).days > QUARTAL_LANG_TAGE:
        return wert * 13.0 / 14.0, True
    return wert, False


def vorjahr(reihe, end):
    """Der Wert des Quartals, das rund ein Jahr vor `end` endete."""
    for e2, w in reihe:
        d = (_dat(end) - _dat(e2)).days if (_dat(end) and _dat(e2)) else None
        if d is not None and 340 <= d <= 390:
            return w
    return None


# ---------------------------------------------------------------------------
# Daten holen
# ---------------------------------------------------------------------------

def lade_kennzahlen(jahre, holen=None, cache=CACHE, leise=True):
    """Die Parquet-Dateien des juengsten Fundament-Releases, auf die
    gebrauchten Kennzahlen gefiltert. holen(name) -> bytes ersetzt den
    Abruf (Selbsttest)."""
    import pandas as pd
    os.makedirs(cache, exist_ok=True)
    frames = []
    for jahr in jahre:
        name = f"fundament_kennzahlen_{jahr}.parquet"
        pfad = os.path.join(cache, f"{date.today().isoformat()}_{name}")
        if not os.path.exists(pfad):
            try:
                if holen is not None:
                    inhalt = holen(name)
                else:
                    import requests
                    r = requests.get(RELEASE_BASIS + name, timeout=120)
                    inhalt = r.content if r.status_code == 200 else None
            except Exception as e:  # noqa
                inhalt = None
                if not leise:
                    print(f"  {name}: Abruf gescheitert ({type(e).__name__})")
            if not inhalt:
                if not leise:
                    print(f"  {name}: nicht vorhanden")
                continue
            with open(pfad, "wb") as f:
                f.write(inhalt)
        try:
            df = pd.read_parquet(pfad, columns=["cik", "kennzahl", "typ", "start", "end", "wert_letzt",
                                                "quelle", "taxonomie", "fiskalperiode"])
        except Exception as e:  # noqa
            if not leise:
                print(f"  {name}: unlesbar ({type(e).__name__})")
            continue
        frames.append(df[df["kennzahl"].isin(KENNZAHLEN)])
    if not frames:
        return None
    alle = pd.concat(frames, ignore_index=True)
    # Zeilen ohne CIK gibt es im Release (Befund 12.09.2026, Rauchtest:
    # IntCastingNaNError); sie gehoeren zu keiner Firma und fallen weg.
    alle = alle[alle["cik"].notna()].copy()
    alle["cik"] = alle["cik"].astype("int64")
    return alle


def cik_je_ticker(user_agent, holen=None):
    """{Ticker: CIK} und {CIK: Hauptticker} aus dem SEC-Verzeichnis. Der
    erste Eintrag je CIK ist der Hauptticker (Antwort 7, SEC-Reihenfolge)."""
    if holen is not None:
        daten = holen()
    else:
        if not user_agent:
            return {}, {}
        import requests
        r = requests.get(SEC_TICKERS, headers={"User-Agent": user_agent}, timeout=60)
        if r.status_code != 200:
            return {}, {}
        daten = r.json()
    ticker_zu_cik, haupt = {}, {}
    eintraege = daten.values() if isinstance(daten, dict) else daten
    for e in eintraege:
        try:
            cik = int(e["cik_str"])
            t = str(e["ticker"]).upper().strip()
        except (KeyError, TypeError, ValueError):
            continue
        ticker_zu_cik[t] = cik
        haupt.setdefault(cik, t)
    return ticker_zu_cik, haupt


# ---------------------------------------------------------------------------
# Je Firma
# ---------------------------------------------------------------------------

def _reihen(df_firma):
    """{kennzahl: {typ: [(start, end, wert, quelle, taxonomie), ...] chronologisch}}"""
    raus = {}
    for z in df_firma.itertuples(index=False):
        w = z.wert_letzt
        if w is None or w != w:
            continue
        raus.setdefault(z.kennzahl, {}).setdefault(z.typ, []).append(
            (str(z.start)[:10], str(z.end)[:10], float(w), str(z.quelle), str(z.taxonomie)))
    for k in raus:
        for t in raus[k]:
            # juengste Einreichung je Periodenende gewinnt (die Datei fuehrt
            # je Periode eine Zeile; doppelte Enden entstehen bei Umstellungen)
            je_end = {}
            for e in raus[k][t]:
                je_end[e[1]] = e
            raus[k][t] = sorted(je_end.values(), key=lambda e: e[1])
    return raus


def umsatz_reihe(reihen):
    """W5: der Umsatzbegriff je Branche. Rueckgabe (Reihe, Vermerk)."""
    q = lambda k: (reihen.get(k) or {}).get("Q") or []  # noqa
    if len(q("zinsueberschuss")) >= 4:
        prov = {e[1]: e[2] for e in q("provisionsertrag")}
        reihe = [(e[0], e[1], e[2] + prov.get(e[1], 0.0), e[3], e[4]) for e in q("zinsueberschuss")]
        return reihe, "Bank: Nettoertraege (Zinsueberschuss plus Provisionsertrag) statt Umsatz"
    if len(q("praemien_verdient")) >= 4:
        return q("praemien_verdient"), "Versicherer: verdiente Praemien statt Umsatz"
    if len(q("mieterloese")) >= 4:
        return q("mieterloese"), "Immobilien: Mieterloese statt Umsatz"
    if q("umsatz"):
        return q("umsatz"), ""
    return [], "kein Umsatzurteil (kein Umsatz ausgewiesen, etwa Biotech)"


def bewerten_firma(reihen, quartale=None, heute=None):
    """Die Rohwerte einer Firma. Rueckgabe dict mit eps_roh, sales_roh,
    marge, roe, quartale, ifrs, vermerke, jahreswachstum."""
    quartale = int(quartale or CFGR["quartale"])
    heute = heute or date.today()
    vermerke = []
    eps = (reihen.get("eps_verwaessert") or {}).get("Q") or []
    eps_fy = (reihen.get("eps_verwaessert") or {}).get("FY") or []
    ifrs = any(e[4] == "ifrs-full" for k in reihen.values() for t in k.values() for e in t)
    if ifrs:
        vermerke.append("IFRS-Zahlen, ungeprueft (Antwort 8)")
    # Nur Quartale der letzten drei Jahre; zu alte Daten sagen nichts ueber heute.
    grenze = (heute - timedelta(days=3 * 366 + 120)).isoformat()
    eps = [e for e in eps if e[1] >= grenze]
    eps_13 = []
    umgerechnet = False
    for s, e, w, qu, tax in eps:
        w2, um = auf_13_wochen(s, e, w) if CFGR.get("wochen_13_umrechnen", True) else (w, False)
        umgerechnet = umgerechnet or um
        eps_13.append((e, w2))
    if umgerechnet:
        vermerke.append("14-Wochen-Quartal auf 13 Wochen umgerechnet (mal 13 durch 14)")
    juengste = eps_13[-quartale:]
    n_q = len(juengste)
    # EPS-Wachstum der zwei juengsten Quartale gegen Vorjahr
    g = []
    for e, w in juengste[-2:][::-1]:
        v = vorjahr(eps_13, e)
        gw = wachstum(w, v)
        if gw is not None:
            g.append(gw)
    jahres = None
    if len(eps_fy) >= 4:
        alt, neu = eps_fy[-4][2], eps_fy[-1][2]
        if alt > 0 and neu > 0:
            jahres = (neu / alt) ** (1 / 3) - 1
        else:
            jahres = wachstum(neu, alt)
    eps_roh = None
    if g:
        eps_roh = sum(g) / len(g)
        if jahres is not None:
            eps_roh += 0.25 * max(-DECKEL, min(DECKEL, jahres))
    if not g:
        vermerke.append("EPS-Wachstum nicht berechenbar (kein Vorjahresquartal)")
    ums, ums_vermerk = umsatz_reihe(reihen)
    if ums_vermerk:
        vermerke.append(ums_vermerk)
    ums = [(e[1], e[2]) for e in ums if e[1] >= grenze]
    sg = []
    for e, w in ums[-3:][::-1]:
        v = vorjahr(ums, e)
        gw = wachstum(w, v)
        if gw is not None:
            sg.append(gw)
    sales_roh = sum(sg) / len(sg) if sg else None
    ng = [(e[1], e[2]) for e in (reihen.get("nettogewinn") or {}).get("Q") or [] if e[1] >= grenze]
    marge = None
    if ng and ums:
        letzte_ums = dict(ums)
        e, w = ng[-1]
        if e in letzte_ums and letzte_ums[e] > 0:
            marge = w / letzte_ums[e]
    ek = (reihen.get("eigenkapital") or {}).get("B") or []
    ng_fy = (reihen.get("nettogewinn") or {}).get("FY") or []
    roe = None
    if ek and ng_fy and ek[-1][2] > 0:
        roe = ng_fy[-1][2] / ek[-1][2]
    quelle_amtlich = all(e[3] == "amtlich" for e in eps[-quartale:]) if eps else True
    if eps and not quelle_amtlich:
        vermerke.append("einzelne Quartale aus dem Jahreswert berechnet (Viertes Quartal gleich Jahr minus neun Monate)")
    return {"eps_roh": eps_roh, "sales_roh": sales_roh, "marge": marge, "roe": roe,
            "quartale": n_q, "ifrs": ifrs, "vermerke": vermerke, "jahreswachstum": jahres,
            "eps_juengst": juengste[-1][1] if juengste else None,
            "eps_ende": juengste[-1][0] if juengste else None}


# ---------------------------------------------------------------------------
# Bauen
# ---------------------------------------------------------------------------

def _hochnaehe(abst_pct):
    if abst_pct is None:
        return None
    return max(0.0, min(100.0, 100.0 + 2.0 * float(abst_pct)))


def bauen(ticker_liste, rs_daten, user_agent=None, jahre=None, kennzahlen=None, zuordnung=None,
          pfad=DATEI, leise=False, heute=None):
    """Ratings fuer die Ticker der Listen und des Nasdaq-Universums.
    kennzahlen (DataFrame) und zuordnung ({ticker: cik}) ersetzen die
    Abrufe im Selbsttest."""
    heute = heute or date.today()
    inhalt = {"gebaut_am": datetime.now().isoformat(timespec="seconds"), "basis": "amtlich",
              "hinweis": ("Noten nach der IBD-Kaufregel (R22): A ab 80, B ab 60, C ab 40, D ab 20. Amtliche "
                          "SEC-Zahlen, Umstellung auf bereinigte Zahlen sobald sie aus den Pressemitteilungen "
                          "vorliegen (R21). A/D ist eine Naeherung aus Kurs und Volumen. Entscheidungshilfe, "
                          "kein Filter."),
              "status": "ok", "grund": "", "aktien": {}}
    if kennzahlen is None:
        jahre = jahre or list(range(heute.year - 3, heute.year + 1))
        kennzahlen = lade_kennzahlen(jahre, leise=leise)
    if kennzahlen is None or len(kennzahlen) == 0:
        inhalt.update({"status": "nicht verfuegbar", "grund": "kein Fundament-Release erreichbar"})
        _schreiben(pfad, inhalt)
        return inhalt
    if zuordnung is None:
        zuordnung, _haupt = cik_je_ticker(user_agent)
    if not zuordnung:
        inhalt.update({"status": "nicht verfuegbar",
                       "grund": "keine Zuordnung Ticker zu CIK (SEC_USER_AGENT fehlt oder Abruf gescheitert)"})
        _schreiben(pfad, inhalt)
        return inhalt

    # Rohwerte ALLER Firmen (das Universum der Perzentile)
    roh = {}
    for cik, df_f in kennzahlen.groupby("cik"):
        try:
            roh[int(cik)] = bewerten_firma(_reihen(df_f), heute=heute)
        except Exception:  # noqa
            continue
    eps_rang = perzentile({c: r["eps_roh"] for c, r in roh.items()})
    sales_rang = perzentile({c: r["sales_roh"] for c, r in roh.items()})
    marge_rang = perzentile({c: r["marge"] for c, r in roh.items()})
    roe_rang = perzentile({c: r["roe"] for c, r in roh.items()})
    smr_roh = {}
    for c in roh:
        teile = [x for x in (sales_rang.get(c), marge_rang.get(c), roe_rang.get(c)) if x is not None]
        if len(teile) >= 2:
            smr_roh[c] = sum(teile) / len(teile)
    smr_rang = perzentile(smr_roh)
    inhalt["universum"] = {"firmen": len(roh), "mit_eps": len(eps_rang), "mit_smr": len(smr_rang)}

    listen = (rs_daten or {}).get("listen") or {}
    aktien = (rs_daten or {}).get("aktien") or {}
    alle_ticker = sorted(set(t.upper() for t in ticker_liste) | set(listen) | set(aktien))
    vor = {}
    for t in alle_ticker:
        cik = zuordnung.get(t)
        e = listen.get(t) or aktien.get(t) or {}
        rs = e.get("rs")
        ad = e.get("ad_rang")
        r = roh.get(cik) if cik else None
        eintrag = {"cik": cik, "eps": eps_rang.get(cik) if cik else None,
                   "smr_rang": smr_rang.get(cik) if cik else None,
                   "smr": note(smr_rang.get(cik)) if cik and smr_rang.get(cik) is not None else None,
                   "ad_rang": ad, "ad": note(ad) if ad is not None else None,
                   "rs": rs, "quartale": (r or {}).get("quartale", 0),
                   "ifrs": bool((r or {}).get("ifrs")), "basis": "amtlich",
                   "vermerke": list((r or {}).get("vermerke") or []),
                   "eps_juengst": (r or {}).get("eps_juengst"), "eps_ende": (r or {}).get("eps_ende")}
        if cik is None:
            eintrag["vermerke"].append("keine SEC-Zuordnung fuer diesen Ticker")
        elif r is None:
            eintrag["vermerke"].append("keine Fundamentaldaten im Release")
        fehlt = [n for n, w in (("EPS", eintrag["eps"]), ("RS", rs), ("SMR", eintrag["smr_rang"]),
                                ("A/D", ad)) if w is None]
        if not fehlt:
            vor[t] = (2 * eintrag["eps"] + 2 * rs + eintrag["smr_rang"] + ad
                      + (_hochnaehe(e.get("abst_52w_hoch_pct")) or 50.0))
        eintrag["composite_fehlt"] = fehlt
        inhalt["aktien"][t] = eintrag
    comp = perzentile(vor)
    for t, c in comp.items():
        inhalt["aktien"][t]["composite"] = c
    for t, e in inhalt["aktien"].items():
        e.setdefault("composite", None)
        e["zeile"] = zeile_aus(e)
    _schreiben(pfad, inhalt)
    if not leise:
        mit = sum(1 for e in inhalt["aktien"].values() if e.get("composite") is not None)
        print(f"IBD-Ratings: {len(roh)} Firmen im Fundament, {len(inhalt['aktien'])} Ticker bewertet, "
              f"{mit} mit Composite; Basis amtlich.")
    return inhalt


def _schreiben(pfad, inhalt):
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(inhalt, f, ensure_ascii=False, separators=(",", ":"))


def lies(pfad=DATEI):
    try:
        with open(pfad, encoding="utf-8-sig") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def zeile_aus(e):
    """R20: alle vier als EINE Zeile, samt Basis und Quartalszahl (Antwort 10)."""
    if not e:
        return ""
    teile = [f"EPS {e['eps']}" if e.get("eps") is not None else "EPS nicht verfuegbar",
             f"SMR {e['smr']}" if e.get("smr") else "SMR nicht verfuegbar",
             f"A/D {e['ad']} (Naeherung)" if e.get("ad") else "A/D nicht verfuegbar",
             (f"Composite {e['composite']}" if e.get("composite") is not None
              else "Composite nicht verfuegbar" + (f" (fehlt {', '.join(e['composite_fehlt'])})"
                                                   if e.get("composite_fehlt") else ""))]
    zusatz = [f"{e.get('basis', 'amtlich')}", f"{int(e.get('quartale') or 0)} Quartale"]
    if e.get("ifrs"):
        zusatz.append("IFRS ungeprueft")
    for v in e.get("vermerke") or []:
        if "13 Wochen" in v:
            zusatz.append("14-Wochen-Quartal auf 13 umgerechnet")
        elif v.startswith(("Bank", "Versicherer", "Immobilien")) or v.startswith("kein Umsatzurteil"):
            zusatz.append(v.split(" (")[0])
    return "Ratings: " + ", ".join(teile) + "; " + ", ".join(zusatz)


def zeile(ticker, daten=None):
    d = daten if daten is not None else lies()
    if not d:
        return ""
    if d.get("status") != "ok":
        return "Ratings nicht verfuegbar (" + str(d.get("grund") or d.get("status")) + ")"
    e = (d.get("aktien") or {}).get(str(ticker or "").upper())
    if not e:
        return ""
    return e.get("zeile") or zeile_aus(e)


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

def _quartale(cik, kennzahl, werte, start_jahr=2023, tax="us-gaap", quelle="amtlich", lang_letztes=False):
    """Zeilen einer Quartalsreihe, je Quartal 91 Tage; das letzte Quartal
    auf Wunsch 98 Tage (14 Wochen)."""
    zeilen = []
    d = date(start_jahr, 1, 1)
    for i, w in enumerate(werte):
        tage = 98 if (lang_letztes and i == len(werte) - 1) else 91
        s, e = d, d + timedelta(days=tage - 1)
        zeilen.append({"cik": cik, "kennzahl": kennzahl, "typ": "Q", "start": s.isoformat(), "end": e.isoformat(),
                       "wert_letzt": w, "quelle": quelle, "taxonomie": tax, "fiskalperiode": f"Q{i % 4 + 1}"})
        d = e + timedelta(days=1)
    return zeilen


def selbsttest() -> int:
    import pandas as pd
    fehler = []

    def p(name, ok, zusatz=""):
        print(f"  {'ok  ' if ok else 'FEHL'} {name}" + (f" — {zusatz}" if zusatz else ""))
        if not ok:
            fehler.append(name)

    print("IBD-Ratings, Selbsttest (ohne Netz)")
    p("Noten nach R22: 80 A, 79 B, 60 B, 59 C, 40 C, 39 D, 20 D, 19 E, None ohne Note",
      [note(x) for x in (80, 79, 60, 59, 40, 39, 20, 19, None)] == ["A", "B", "B", "C", "C", "D", "D", "E", None])
    pz = perzentile({"a": 1.0, "b": 2.0, "c": 2.0, "d": 3.0, "e": None})
    p("Perzentile: strikt kleinere zaehlen, Gleichstand gleicher Rang, None faellt weg",
      pz == {"a": 1, "b": 25, "c": 25, "d": 75}, pz)
    p("Wachstum: normal, gedeckelt, Wende aus dem Minus, Absturz ins Minus",
      wachstum(1.5, 1.0) == 0.5 and wachstum(10.0, 1.0) == 3.0 and wachstum(1.0, -1.0) == 1.0 and wachstum(-1.0, -2.0) == -1.0)
    p("W7: 98-Tage-Quartal wird mal 13 durch 14 gerechnet, 91-Tage-Quartal nicht",
      auf_13_wochen("2026-01-01", "2026-04-08", 14.0) == (13.0, True) and auf_13_wochen("2026-01-01", "2026-04-01", 14.0) == (14.0, False))

    zeilen = []
    # Firma 1: waechst kraeftig (EPS je Quartal plus 50 Prozent zum Vorjahr), 14 Quartale, letztes ein 14-Wochen-Quartal
    eps1 = [1.0, 1.1, 1.2, 1.3, 1.5, 1.65, 1.8, 1.95, 2.25, 2.48, 2.7, 2.93, 3.38, 3.71]
    zeilen += _quartale(1, "eps_verwaessert", eps1, lang_letztes=True)
    zeilen += _quartale(1, "umsatz", [100 * 1.1 ** i for i in range(14)])
    zeilen += _quartale(1, "nettogewinn", [10 * 1.1 ** i for i in range(14)])
    zeilen.append({"cik": 1, "kennzahl": "eigenkapital", "typ": "B", "start": "2026-06-30", "end": "2026-06-30",
                   "wert_letzt": 500.0, "quelle": "amtlich", "taxonomie": "us-gaap", "fiskalperiode": "Q2"})
    for j, w in ((2022, 4.0), (2023, 5.0), (2024, 6.5), (2025, 8.0)):
        zeilen.append({"cik": 1, "kennzahl": "eps_verwaessert", "typ": "FY", "start": f"{j}-01-01", "end": f"{j}-12-31",
                       "wert_letzt": w, "quelle": "amtlich", "taxonomie": "us-gaap", "fiskalperiode": "FY"})
        zeilen.append({"cik": 1, "kennzahl": "nettogewinn", "typ": "FY", "start": f"{j}-01-01", "end": f"{j}-12-31",
                       "wert_letzt": w * 10, "quelle": "amtlich", "taxonomie": "us-gaap", "fiskalperiode": "FY"})
    # Firma 2: schrumpft
    zeilen += _quartale(2, "eps_verwaessert", [2.0 - 0.1 * i for i in range(14)])
    zeilen += _quartale(2, "umsatz", [100 - 3 * i for i in range(14)])
    zeilen += _quartale(2, "nettogewinn", [5 - 0.4 * i for i in range(14)])
    # Firma 3: Bank ohne Umsatzzeile, waechst maessig
    zeilen += _quartale(3, "eps_verwaessert", [1.0 + 0.05 * i for i in range(14)])
    zeilen += _quartale(3, "zinsueberschuss", [50 + 2 * i for i in range(14)])
    zeilen += _quartale(3, "provisionsertrag", [10 + i for i in range(14)])
    zeilen += _quartale(3, "nettogewinn", [8 + 0.3 * i for i in range(14)])
    for cik, ek, ng in ((2, 100.0, -5.0), (3, 400.0, 40.0), (5, 300.0, 60.0)):
        zeilen.append({"cik": cik, "kennzahl": "eigenkapital", "typ": "B", "start": "2026-06-30", "end": "2026-06-30",
                       "wert_letzt": ek, "quelle": "amtlich", "taxonomie": "us-gaap", "fiskalperiode": "Q2"})
        zeilen.append({"cik": cik, "kennzahl": "nettogewinn", "typ": "FY", "start": "2025-01-01", "end": "2025-12-31",
                       "wert_letzt": ng, "quelle": "amtlich", "taxonomie": "us-gaap", "fiskalperiode": "FY"})
    # Firma 4: Biotech ohne Umsatz, EPS negativ, nur 5 Quartale
    zeilen += _quartale(4, "eps_verwaessert", [-0.5, -0.6, -0.4, -0.3, -0.2], start_jahr=2025)
    zeilen += _quartale(4, "nettogewinn", [-5, -6, -4, -3, -2], start_jahr=2025)
    # Firma 5: IFRS-Firma
    zeilen += _quartale(5, "eps_verwaessert", [1.0 + 0.2 * i for i in range(14)], tax="ifrs-full")
    zeilen += _quartale(5, "umsatz", [100 + 5 * i for i in range(14)], tax="ifrs-full")
    zeilen += _quartale(5, "nettogewinn", [10 + i for i in range(14)], tax="ifrs-full")
    df = pd.DataFrame(zeilen)
    heute = date(2026, 9, 14)
    r1 = bewerten_firma(_reihen(df[df.cik == 1]), heute=heute)
    p("Firma 1: acht Quartale sichtbar, EPS-Wachstum rund plus 50 Prozent, 13-Wochen-Vermerk, Jahreswachstum als Vermerk",
      r1["quartale"] == 8 and r1["eps_roh"] is not None and 0.4 < r1["eps_roh"] < 0.8
      and any("13 Wochen" in v for v in r1["vermerke"]) and r1["jahreswachstum"] is not None, r1)
    r3 = bewerten_firma(_reihen(df[df.cik == 3]), heute=heute)
    p("W5 Bank: Nettoertraege statt Umsatz, mit Vermerk", any(v.startswith("Bank") for v in r3["vermerke"]) and r3["sales_roh"] is not None, r3["vermerke"])
    r4 = bewerten_firma(_reihen(df[df.cik == 4]), heute=heute)
    p("Antwort 10: Biotech mit fuenf Quartalen bekommt trotzdem einen Wert, Quartalszahl 5, kein Umsatzurteil",
      r4["quartale"] == 5 and r4["eps_roh"] is not None and any("kein Umsatzurteil" in v for v in r4["vermerke"]), r4)
    r5 = bewerten_firma(_reihen(df[df.cik == 5]), heute=heute)
    p("Antwort 8: IFRS-Firma laeuft mit und ist als ungeprueft gekennzeichnet", r5["ifrs"] and any("IFRS" in v for v in r5["vermerke"]))

    rs = {"listen": {"AAA": {"rs": 90, "ad_rang": 70, "abst_52w_hoch_pct": -2.0},
                     "BBB": {"rs": 20, "ad_rang": 30, "abst_52w_hoch_pct": -30.0}},
          "aktien": {"CCC": {"rs": 50, "ad_rang": 50, "abst_52w_hoch_pct": -10.0},
                     "DDD": {"rs": 60, "ad_rang": 55, "abst_52w_hoch_pct": -5.0},
                     "EEE": {"rs": 70, "ad_rang": 80, "abst_52w_hoch_pct": -3.0},
                     "FFF": {"rs": 40}}}
    zu = {"AAA": 1, "BBB": 2, "CCC": 3, "DDD": 4, "EEE": 5}
    import tempfile
    pfad = os.path.join(tempfile.mkdtemp(), "r.json")
    inhalt = bauen([], rs, kennzahlen=df, zuordnung=zu, pfad=pfad, leise=True, heute=heute)
    a = inhalt["aktien"]
    p("Ratings gebaut: Firma 1 vor Firma 2 beim EPS-Rang, Noten vergeben (Wachser mindestens C, Schrumpfer D oder E)",
      a["AAA"]["eps"] > a["BBB"]["eps"] and a["AAA"]["smr"] in "ABC" and a["BBB"]["smr"] in "DE", {t: (e["eps"], e["smr"]) for t, e in a.items()})
    p("Composite: AAA hoechster, BBB niedrigster; FFF ohne Zuordnung und ohne A/D bekommt keines und nennt, was fehlt",
      a["AAA"]["composite"] > a["BBB"]["composite"] and a["FFF"]["composite"] is None
      and "EPS" in a["FFF"]["composite_fehlt"] and "A/D" in a["FFF"]["composite_fehlt"], a["FFF"])
    z = zeile("AAA", inhalt)
    p("R20 eine Zeile mit allen vier, Basis amtlich, Quartalszahl, 13-Wochen-Vermerk",
      z.startswith("Ratings: EPS ") and "SMR " in z and "A/D " in z and "(Naeherung)" in z and "Composite " in z
      and "amtlich" in z and "8 Quartale" in z and "14-Wochen-Quartal auf 13 umgerechnet" in z, z)
    z5 = zeile("EEE", inhalt)
    p("IFRS-Kennzeichnung in der Zeile", "IFRS ungeprueft" in z5, z5)
    z3 = zeile("CCC", inhalt)
    p("Bank-Umsatzbegriff in der Zeile", "Bank: Nettoertraege" in z3, z3)
    p("Kein Gedankenstrich in den Zeilen", all("–" not in e["zeile"] and "|" not in e["zeile"] for e in a.values()))
    p("Datei gelesen, Zeile ueber lies()", zeile("AAA", lies(pfad)) == z)
    leer = bauen([], rs, kennzahlen=df, zuordnung={}, pfad=pfad, leise=True, heute=heute)
    p("Ohne Zuordnung: Status nicht verfuegbar mit Grund", leer["status"] == "nicht verfuegbar" and "SEC_USER_AGENT" in leer["grund"])
    p("Zeile bei nicht verfuegbar nennt den Grund", zeile("AAA", {"status": "nicht verfuegbar", "grund": "x", "aktien": {"AAA": {}}}).startswith("Ratings nicht verfuegbar"))
    print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles bestanden.")
    return 1 if fehler else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="IBD-Ratings als Naeherung aus dem SEC-Fundament.")
    ap.add_argument("--bauen", action="store_true")
    ap.add_argument("--selbsttest", action="store_true")
    ap.add_argument("--ausgabe", default=DATEI)
    args = ap.parse_args()
    if args.selbsttest:
        return selbsttest()
    if args.bauen:
        import rs_universum
        rs = rs_universum.lies()
        ticker = list((rs.get("listen") or {}).keys())
        bauen(ticker, rs, user_agent=(os.environ.get("SEC_USER_AGENT") or "").strip() or None,
              pfad=args.ausgabe)
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
