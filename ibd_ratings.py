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
  A/D         Naeherung aus Kurs und Volumen (rs_universum: 13 Wochen; seit
              Etappe 2 nach Chaikin, also die Lage des Schlusskurses in der
              Tagesspanne mit dem Volumen gewichtet, vorher Volumen an
              Plus-Tagen gegen Volumen an Minus-Tagen), Note nach demselben
              Schluessel.
  Composite   Wie bei IBD: EPS und RS doppelt, dazu SMR, A/D und die Naehe
              zum 52-Wochen-Hoch; Perzentil gegen alle Aktien mit
              vollstaendigen Bausteinen. Fehlt ein Baustein, gibt es KEIN
              Composite, sondern die Nennung, was fehlt.

ETAPPE 4 (Gerhard, 13.09.2026, Entscheidungen 7 und 8)
  Punkt 1 der Gruppe B: Der SMR nimmt als vierten Baustein die Vorsteuer-
  marge des Geschaeftsjahrs dazu (IBD nutzt die Vorsteuermarge des Jahres
  und die Nachsteuermarge des Quartals). Punkt 13: Die Bausteine stehen je
  Aktie mit Rohwert und Rang unter "smr_bausteine", statt vor der Ablage
  verworfen zu werden. Die uebrigen Punkte rechnet kennzahlen_fundament.py
  aus einem LANGEN Fundament (alle Kennzahlen ueber sieben Kalenderjahre,
  nur fuer die Firmen unserer Ticker) und legt sie unter "fundament" ab;
  dazu die CAN-SLIM-Haekchen unter "canslim". Alles Anzeige, nichts filtert,
  und die Meldezeile bleibt, wie sie ist.

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
import kennzahlen_fundament

CFGR = CFG["ibd_ratings"]
DATEI = "ibd_ratings.json"
RELEASE_BASIS = "https://github.com/mat-schmuck/heliot/releases/latest/download/"
SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"
CACHE = os.path.join(".cache", "fundament")
KENNZAHLEN = ("umsatz", "eps_verwaessert", "nettogewinn", "eigenkapital",
              "zinsueberschuss", "provisionsertrag", "praemien_verdient", "mieterloese",
              # Etappe 4, Punkt 1: die Vorsteuermarge des Jahres im SMR
              "ergebnis_vor_steuern")
# Etappe 4: alles, was kennzahlen_fundament.py liest
KENNZAHLEN_LANG = KENNZAHLEN + (
    "umsatzkosten", "bruttogewinn", "operatives_ergebnis", "steuern", "aktien_verwaessert", "zinsaufwand",
    "abschreibungen", "aktienbasierte_verguetung", "operativer_cashflow", "investitionen", "dividenden_gezahlt",
    "aktienrueckkauf", "bilanzsumme", "umlaufvermoegen", "kasse", "kurzfristige_anlagen", "vorraete",
    "verbindlichkeiten", "kurzfristige_verbindlichkeiten", "langfristige_schulden", "kurzfristige_schulden",
    "gewinnruecklagen", "aktien_ausstehend", "streubesitz_wert", "risikovorsorge", "einlagen", "kredite",
    "kernkapitalquote", "wertminderung_immobilien", "gewinn_immobilienverkauf")
FIRMEN = "fundament_firmen.csv"
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

def _release_datei(name, holen=None, cache=CACHE, leise=True):
    """Pfad einer Datei des juengsten Fundament-Releases im Tagescache, oder
    None. holen(name) -> bytes ersetzt den Abruf."""
    os.makedirs(cache, exist_ok=True)
    pfad = os.path.join(cache, f"{date.today().isoformat()}_{name}")
    if os.path.exists(pfad):
        return pfad
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
        return None
    with open(pfad, "wb") as f:
        f.write(inhalt)
    return pfad


def lade_firmen(holen=None, cache=CACHE, leise=True):
    """{CIK: Filer-Typ} aus fundament_firmen.csv (inland_usgaap,
    ausland_usgaap, ausland_ifrs). Leer, wenn die Datei fehlt."""
    pfad = _release_datei(FIRMEN, holen, cache, leise)
    if not pfad:
        return {}
    try:
        import pandas as pd
        f = pd.read_csv(pfad, usecols=["cik", "filer_typ"])
    except Exception as e:  # noqa
        if not leise:
            print(f"  {FIRMEN}: unlesbar ({type(e).__name__})")
        return {}
    f = f[f["cik"].notna()]
    return {int(c): str(t) for c, t in zip(f["cik"], f["filer_typ"])}


# Formulare, deren Zahlen nicht aus einem Abschluss stammen: Vollmachts- und
# Informationsunterlagen zur Hauptversammlung (DEF 14A, DEFR14A, DEFA14A,
# PRE 14A, DEF 14C und Verwandte).
VOLLMACHT_FORMULARE = r"14A|14C"


def ohne_vollmachtszahlen(df):
    """BEFUND 14.09.2026: Bei 12.782 Zeilen des Fundaments (1.655 Firmen,
    fast nur der Nettogewinn) stammt die letzte Fassung aus einer
    Vollmachtsunterlage zur Hauptversammlung. Deren Tabelle "Pay versus
    Performance" nennt den Nettogewinn oft in Tausend oder Millionen,
    markiert ihn aber als Dollar: Arista 1.352 statt 1,352 Milliarden
    (Geschaeftsjahr 2022), Schwab 7,183 Millionen statt 7,183 Milliarden,
    Chemed 249.624 statt 249,6 Millionen. Das Vierte Quartal, aus dem
    Jahreswert berechnet, erbt den Fehler. Solche Zeilen nehmen die
    Erstfassung, wenn diese aus einem Abschluss stammt; stammen beide aus
    Vollmachtsunterlagen, fallen sie weg. Ohne Formularspalten (aeltere
    Dateien) bleibt der Rahmen unveraendert."""
    if not {"form_letzt", "form_erst", "wert_erst"} <= set(df.columns) or df.empty:
        return df
    pl = df["form_letzt"].fillna("").astype(str).str.contains(VOLLMACHT_FORMULARE, regex=True)
    if not pl.any():
        return df
    pe = df["form_erst"].fillna("").astype(str).str.contains(VOLLMACHT_FORMULARE, regex=True)
    df = df[~(pl & pe)].copy()
    m = (pl & ~pe).loc[df.index]
    df.loc[m, "wert_letzt"] = df.loc[m, "wert_erst"]
    for neu, alt in (("filed_letzt", "filed_erst"), ("form_letzt", "form_erst")):
        if neu in df.columns and alt in df.columns:
            df.loc[m, neu] = df.loc[m, alt]
    return df


def lade_kennzahlen(jahre, holen=None, cache=CACHE, leise=True, auswahl=None, ciks=None, mit_fassungen=False):
    """Die Parquet-Dateien des juengsten Fundament-Releases, auf die
    gebrauchten Kennzahlen gefiltert. holen(name) -> bytes ersetzt den
    Abruf (Selbsttest). auswahl ersetzt die Kennzahlen der Ratings, etwa
    fuer den Scanner (scanner_daten.py), der zusaetzlich Bruttogewinn,
    Schulden, Bilanzsumme und ausstehende Aktien braucht. ciks beschraenkt
    auf diese Firmen (Etappe 4, das lange Fundament). Die Einheit der Werte
    kommt mit, wo die Datei sie fuehrt; mit_fassungen dazu Erstfassung und
    Tag der letzten Einreichung (fuer die Splitbereinigung)."""
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
        spalten = ["cik", "kennzahl", "typ", "start", "end", "wert_letzt", "quelle", "taxonomie", "fiskalperiode"]
        try:
            df = pd.read_parquet(pfad, columns=spalten + ["einheit", "wert_erst", "form_erst", "form_letzt",
                                                          "filed_erst", "filed_letzt"])
        except Exception:  # noqa
            try:
                df = pd.read_parquet(pfad, columns=spalten)
            except Exception as e:  # noqa
                if not leise:
                    print(f"  {name}: unlesbar ({type(e).__name__})")
                continue
        df = df[df["kennzahl"].isin(auswahl or KENNZAHLEN)]
        if ciks is not None:
            df = df[df["cik"].isin(list(ciks))]
        df = ohne_vollmachtszahlen(df)
        weg = ["form_erst", "form_letzt"] + ([] if mit_fassungen else ["wert_erst", "filed_erst"])
        frames.append(df.drop(columns=[s for s in weg if s in df.columns]))
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

_REIHEN_SPALTEN = ("kennzahl", "typ", "start", "end", "wert_letzt", "quelle", "taxonomie")
_REIHEN_ZUSATZ = ("einheit", "wert_erst", "filed_letzt", "filed_erst")


def _reihen(df_firma):
    """{kennzahl: {typ: [(start, end, wert, quelle, taxonomie, einheit, wert_erst, filed_letzt, filed_erst), ...]
    chronologisch}}. Etappe 4: Einheit, Erstfassung, Tag der letzten und der
    ersten Einreichung stehen an sechster bis neunter Stelle, je None ohne
    Spalte; wer die Eintraege entpackt, nimmt die ersten fuenf und den Rest
    (*_). Erstfassung und Einreichungstage verraten Aktiensplits
    (kennzahlen_fundament.split_bereinigt)."""
    namen = list(_REIHEN_SPALTEN) + [c for c in _REIHEN_ZUSATZ if c in df_firma.columns]
    return _reihen_zeilen(namen, list(zip(*(df_firma[c].tolist() for c in namen))))


def _reihen_je_firma(df):
    """{CIK: Reihen wie _reihen} fuer alle Firmen eines Rahmens. BEFUND
    14.09.2026: groupby mit itertuples brauchte beim Nachtbau fuer 13.851
    Firmen 111 Sekunden, fast alles im spaltenweisen Zugriff je Firma. Jetzt
    wird einmal nach CIK sortiert (nur die Reihenfolge, die Spalten bleiben
    numpy-Felder) und je Firma ein Ausschnitt gelesen."""
    import numpy as np
    if df is None or len(df) == 0:
        return {}
    namen = list(_REIHEN_SPALTEN) + [c for c in _REIHEN_ZUSATZ if c in df.columns]
    cik = df["cik"].to_numpy()
    folge = np.argsort(cik, kind="stable")
    cik_s = cik[folge]
    felder = [df[c].to_numpy()[folge] for c in namen]
    grenzen = np.flatnonzero(cik_s[1:] != cik_s[:-1]) + 1
    anfaenge = np.concatenate(([0], grenzen))
    enden = np.concatenate((grenzen, [len(cik_s)]))
    raus = {}
    for a, b in zip(anfaenge.tolist(), enden.tolist()):
        try:
            raus[int(cik_s[a])] = _reihen_zeilen(namen, list(zip(*(f[a:b].tolist() for f in felder))))
        except Exception:  # noqa
            continue
    return raus


def _reihen_zeilen(namen, zeilen):
    pos = {n: i for i, n in enumerate(namen)}
    raus = {}
    mit_einheit = "einheit" in pos
    mit_fassungen = all(s in pos for s in ("wert_erst", "filed_letzt", "filed_erst"))
    mit_tag = "filed_letzt" in pos
    i_k, i_t, i_s, i_e, i_w, i_q, i_x = (pos[n] for n in _REIHEN_SPALTEN)
    tage = {}
    for z in zeilen:
        w = z[i_w]
        if w is None or w != w:
            continue
        einheit = z[pos["einheit"]] if mit_einheit else None
        w_erst = z[pos["wert_erst"]] if mit_fassungen else None
        filed = z[pos["filed_letzt"]] if mit_fassungen else None
        filed_erst = z[pos["filed_erst"]] if mit_fassungen else None
        e = (str(z[i_s])[:10], str(z[i_e])[:10], float(w), str(z[i_q]), str(z[i_x]),
             einheit if isinstance(einheit, str) else None,
             float(w_erst) if w_erst is not None and w_erst == w_erst else None,
             str(filed)[:10] if isinstance(filed, str) and filed else None,
             str(filed_erst)[:10] if isinstance(filed_erst, str) and filed_erst else None)
        raus.setdefault(z[i_k], {}).setdefault(z[i_t], []).append(e)
        if mit_tag:
            f_l = z[pos["filed_letzt"]]
            tage[id(e)] = str(f_l)[:10] if isinstance(f_l, str) else ""
    for k in raus:
        for t in raus[k]:
            # juengste Einreichung je Periodenende gewinnt (die Datei fuehrt
            # je Periode eine Zeile; doppelte Enden entstehen bei Umstellungen
            # des Periodenbeginns). BEFUND 14.09.2026: Bisher gewann die
            # letzte ZEILE, nicht die juengste Einreichung (National Beverage,
            # Quartal bis 29.07.2023: 53 Dollar je Aktie aus dem
            # Quartalsbericht 2023, der Cent als Dollar markierte, neben 0,53
            # aus dem Bericht 2024 mit einen Tag spaeterem Periodenbeginn).
            je_end = {}
            for e in raus[k][t]:
                alt = je_end.get(e[1])
                if alt is None or not mit_tag or tage.get(id(e), "") >= tage.get(id(alt), ""):
                    je_end[e[1]] = e
            raus[k][t] = sorted(je_end.values(), key=lambda e: e[1])
    return raus


def umsatz_reihe(reihen):
    """W5: der Umsatzbegriff je Branche. Rueckgabe (Reihe, Vermerk).

    Die Branchenreihe gilt nur, wenn sie das Geschaeft TRAEGT: Fehlt ein
    gewoehnlicher Umsatz, oder ist die Branchenreihe im juengsten Quartal
    mindestens halb so gross wie er. Befund 13.09.2026: DELL und HPE weisen
    neben 25 Milliarden Umsatz auch Mieterloese aus dem Geraeteleasing aus
    (405 Millionen) und galten deshalb als Immobilienfirmen, mit falschem
    Umsatzwachstum und falscher SMR-Note. Ein Versicherer oder ein REIT hat
    keinen groesseren gewoehnlichen Umsatz daneben, fuer sie aendert sich
    nichts."""
    q = lambda k: (reihen.get(k) or {}).get("Q") or []  # noqa
    umsatz = q("umsatz")

    def traegt(reihe):
        if not umsatz:
            return True
        letzte_u = umsatz[-1][2]
        return letzte_u <= 0 or reihe[-1][2] >= 0.5 * letzte_u

    if len(q("zinsueberschuss")) >= 4:
        prov = {e[1]: e[2] for e in q("provisionsertrag")}
        reihe = [(e[0], e[1], e[2] + prov.get(e[1], 0.0), e[3], e[4]) + tuple(e[5:6]) for e in q("zinsueberschuss")]
        if traegt(reihe):
            return reihe, "Bank: Nettoertraege (Zinsueberschuss plus Provisionsertrag) statt Umsatz"
    if len(q("praemien_verdient")) >= 4 and traegt(q("praemien_verdient")):
        return q("praemien_verdient"), "Versicherer: verdiente Praemien statt Umsatz"
    if len(q("mieterloese")) >= 4 and traegt(q("mieterloese")):
        return q("mieterloese"), "Immobilien: Mieterloese statt Umsatz"
    if umsatz:
        return umsatz, ""
    return [], "kein Umsatzurteil (kein Umsatz ausgewiesen, etwa Biotech)"


def branche_aus(vermerk):
    """Der Umsatzbegriff aus umsatz_reihe als Kennwort fuer
    kennzahlen_fundament: "bank", "versicherer", "immobilien" oder ""."""
    v = str(vermerk or "")
    for wort, kenn in (("Bank", "bank"), ("Versicherer", "versicherer"), ("Immobilien", "immobilien")):
        if v.startswith(wort):
            return kenn
    return ""


def umsatz_reihe_fy(reihen, vermerk):
    """Etappe 4: die Geschaeftsjahre nach demselben Umsatzbegriff, den
    umsatz_reihe fuer die Quartale gewaehlt hat."""
    fy = lambda k: (reihen.get(k) or {}).get("FY") or []  # noqa
    b = branche_aus(vermerk)
    if b == "bank":
        prov = {e[1]: e[2] for e in fy("provisionsertrag")}
        return [(e[0], e[1], e[2] + prov.get(e[1], 0.0), e[3], e[4]) + tuple(e[5:6]) for e in fy("zinsueberschuss")]
    if b == "versicherer":
        return fy("praemien_verdient")
    if b == "immobilien":
        return fy("mieterloese")
    return fy("umsatz")


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
    for s, e, w, qu, tax, *_ in eps:
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
    ums = [e for e in ums if e[1] >= grenze]
    # Die Marge vergleicht Werte DESSELBEN Quartals, dort hebt sich die
    # Laenge auf; sie rechnet deshalb mit den Zahlen, wie die SEC sie fuehrt.
    ums_sec = [(e[1], e[2]) for e in ums]
    # W7 gilt auch fuer den Umsatz (Befund 14.09.2026: BNED und RGP zeigten
    # im Scanner ein anderes Umsatzwachstum als hier, weil ein 14-Wochen-
    # Vorjahresquartal gegen ein 13-Wochen-Quartal stand).
    ums_13 = []
    ums_umgerechnet = False
    for s, e, w, _qu, _tax, *_ in ums:
        w2, um = auf_13_wochen(s, e, w) if CFGR.get("wochen_13_umrechnen", True) else (w, False)
        ums_umgerechnet = ums_umgerechnet or um
        ums_13.append((e, w2))
    if ums_umgerechnet and not umgerechnet:
        vermerke.append("14-Wochen-Quartal auf 13 Wochen umgerechnet (mal 13 durch 14)")
    ums = ums_13
    sg = []
    for e, w in ums[-3:][::-1]:
        v = vorjahr(ums, e)
        gw = wachstum(w, v)
        if gw is not None:
            sg.append(gw)
    sales_roh = sum(sg) / len(sg) if sg else None
    ng = [(e[1], e[2]) for e in (reihen.get("nettogewinn") or {}).get("Q") or [] if e[1] >= grenze]
    marge = None
    if ng and ums_sec:
        letzte_ums = dict(ums_sec)
        e, w = ng[-1]
        if e in letzte_ums and letzte_ums[e] > 0:
            marge = w / letzte_ums[e]
    ek = (reihen.get("eigenkapital") or {}).get("B") or []
    ng_fy = (reihen.get("nettogewinn") or {}).get("FY") or []
    roe = None
    if ek and ng_fy and ek[-1][2] > 0:
        roe = ng_fy[-1][2] / ek[-1][2]
    # Etappe 4, Punkt 1: Vorsteuermarge des juengsten Geschaeftsjahrs, nach
    # dem Umsatzbegriff der Branche, nur aus den letzten drei Jahren.
    vorsteuer_marge_fy = None
    ums_fy = [e for e in umsatz_reihe_fy(reihen, ums_vermerk) if e[1] >= grenze]
    ebt_fy = {e[1]: e[2] for e in (reihen.get("ergebnis_vor_steuern") or {}).get("FY") or []}
    if ums_fy and ums_fy[-1][2] > 0 and ums_fy[-1][1] in ebt_fy:
        vorsteuer_marge_fy = ebt_fy[ums_fy[-1][1]] / ums_fy[-1][2]
    quelle_amtlich = all(e[3] == "amtlich" for e in eps[-quartale:]) if eps else True
    if eps and not quelle_amtlich:
        vermerke.append("einzelne Quartale aus dem Jahreswert berechnet (Viertes Quartal gleich Jahr minus neun Monate)")
    # Die Zahlen hinter dem Wachstum, fuers Nachschlagen (Mathias, 13.09.2026):
    # juengstes Quartal, Vorquartal und Vorjahresquartal fuer Umsatz und
    # Gewinn je Aktie. Umsatz in ganzen Dollar, wie die SEC ihn fuehrt.
    return {"eps_roh": eps_roh, "sales_roh": sales_roh, "marge": marge, "roe": roe,
            "vorsteuer_marge_fy": vorsteuer_marge_fy,
            "quartale": n_q, "ifrs": ifrs, "vermerke": vermerke, "jahreswachstum": jahres,
            "eps_juengst": juengste[-1][1] if juengste else None,
            "eps_ende": juengste[-1][0] if juengste else None,
            "eps_vorquartal": juengste[-2][1] if len(juengste) >= 2 else None,
            "eps_vorjahr": vorjahr(eps_13, juengste[-1][0]) if juengste else None,
            "umsatz_juengst": ums[-1][1] if ums else None,
            "umsatz_ende": ums[-1][0] if ums else None,
            "umsatz_vorquartal": ums[-2][1] if len(ums) >= 2 else None,
            "umsatz_vorjahr": vorjahr(ums, ums[-1][0]) if ums else None}


def wachstum_pct(neu, alt):
    """Prozent fuer die Anzeige, nur bei positiver Basis; sonst None (die
    Anzeige sagt dann, dass die Basis bei null oder im Minus lag)."""
    if neu is None or alt is None or alt <= 0:
        return None
    return round((float(neu) / float(alt) - 1.0) * 100.0, 1)


# ---------------------------------------------------------------------------
# Bauen
# ---------------------------------------------------------------------------

def _hochnaehe(abst_pct):
    if abst_pct is None:
        return None
    return max(0.0, min(100.0, 100.0 + 2.0 * float(abst_pct)))


def _rund(x, stellen=4):
    return round(float(x), stellen) if x is not None and x == x else None


def _fundament_reihen(ciks, heute, kennzahlen_lang=None, leise=True):
    """Etappe 4: {CIK: Reihen} aus dem langen Fundament fuer diese Firmen.
    kennzahlen_lang (DataFrame) ersetzt den Abruf im Selbsttest."""
    if kennzahlen_lang is None:
        jahre = list(range(heute.year - int(CFG["fundament_kennzahlen"]["jahre"]) + 1, heute.year + 1))
        kennzahlen_lang = lade_kennzahlen(jahre, leise=leise, auswahl=KENNZAHLEN_LANG, ciks=ciks, mit_fassungen=True)
    if kennzahlen_lang is None or len(kennzahlen_lang) == 0:
        return {}
    return _reihen_je_firma(kennzahlen_lang[kennzahlen_lang["cik"].isin(list(ciks))])


def bauen(ticker_liste, rs_daten, user_agent=None, jahre=None, kennzahlen=None, zuordnung=None,
          pfad=DATEI, leise=False, heute=None, kennzahlen_lang=None, firmen=None):
    """Ratings fuer die Ticker der Listen und des ganzen Bezugs (seit
    13.09.2026 auch die Titel unter den Schwellen, fuers Nachschlagen).
    kennzahlen (DataFrame) und zuordnung ({ticker: cik}) ersetzen die
    Abrufe im Selbsttest; ebenso kennzahlen_lang (das lange Fundament der
    Etappe 4, ohne Angabe im Selbsttest dieselbe Tabelle wie kennzahlen) und
    firmen ({CIK: Filer-Typ})."""
    heute = heute or date.today()
    test_modus = kennzahlen is not None
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
    for cik, reihen_f in _reihen_je_firma(kennzahlen).items():
        try:
            roh[cik] = bewerten_firma(reihen_f, heute=heute)
        except Exception:  # noqa
            continue
    eps_rang = perzentile({c: r["eps_roh"] for c, r in roh.items()})
    sales_rang = perzentile({c: r["sales_roh"] for c, r in roh.items()})
    marge_rang = perzentile({c: r["marge"] for c, r in roh.items()})
    roe_rang = perzentile({c: r["roe"] for c, r in roh.items()})
    vorsteuer_rang = perzentile({c: r.get("vorsteuer_marge_fy") for c, r in roh.items()})
    smr_roh = {}
    for c in roh:
        teile = [x for x in (sales_rang.get(c), marge_rang.get(c), vorsteuer_rang.get(c), roe_rang.get(c))
                 if x is not None]
        if len(teile) >= 2:
            smr_roh[c] = sum(teile) / len(teile)
    smr_rang = perzentile(smr_roh)
    inhalt["universum"] = {"firmen": len(roh), "mit_eps": len(eps_rang), "mit_smr": len(smr_rang),
                           "mit_vorsteuermarge": len(vorsteuer_rang)}

    listen = (rs_daten or {}).get("listen") or {}
    aktien = (rs_daten or {}).get("aktien") or {}
    aussen = {t: e for t, e in ((rs_daten or {}).get("ausserhalb") or {}).items()
              if isinstance(e, dict) and e.get("rs") is not None}
    alle_ticker = sorted(set(t.upper() for t in ticker_liste) | set(listen) | set(aktien) | set(aussen))
    # Etappe 4: das lange Fundament nur fuer unsere Firmen
    ciks_unsere = {zuordnung.get(t) for t in alle_ticker} - {None}
    lang_ersatz = kennzahlen_lang if kennzahlen_lang is not None else (kennzahlen if test_modus else None)
    try:
        fund_reihen = _fundament_reihen(ciks_unsere, heute, lang_ersatz, leise)
    except Exception as e:  # noqa
        print(f"  Fundament der Etappe 4: nicht ladbar ({type(e).__name__}: {e})")
        fund_reihen = {}
    if firmen is None:
        firmen = {} if test_modus else lade_firmen(leise=leise)
    inhalt["fundament_stand"] = {"firmen": len(fund_reihen), "filer_typen": len(firmen),
                                 "jahre": int(CFG["fundament_kennzahlen"]["jahre"])}
    vor = {}
    for t in alle_ticker:
        cik = zuordnung.get(t)
        e = listen.get(t) or aktien.get(t) or aussen.get(t) or {}
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
        for feld in ("eps_vorquartal", "eps_vorjahr", "umsatz_juengst", "umsatz_ende", "umsatz_vorquartal", "umsatz_vorjahr"):
            eintrag[feld] = (r or {}).get(feld)
        eintrag["eps_wachstum_vj_pct"] = wachstum_pct(eintrag["eps_juengst"], eintrag["eps_vorjahr"])
        eintrag["eps_wachstum_vq_pct"] = wachstum_pct(eintrag["eps_juengst"], eintrag["eps_vorquartal"])
        eintrag["umsatz_wachstum_vj_pct"] = wachstum_pct(eintrag["umsatz_juengst"], eintrag["umsatz_vorjahr"])
        eintrag["umsatz_wachstum_vq_pct"] = wachstum_pct(eintrag["umsatz_juengst"], eintrag["umsatz_vorquartal"])
        if cik is None:
            eintrag["vermerke"].append("keine SEC-Zuordnung fuer diesen Ticker")
        elif r is None:
            eintrag["vermerke"].append("keine Fundamentaldaten im Release")
        if cik is not None and r is not None:
            # Etappe 4, Punkt 13: die SMR-Bausteine mit Rohwert und Rang
            eintrag["smr_bausteine"] = {
                "umsatz": [_rund(r.get("sales_roh")), sales_rang.get(cik)],
                "marge": [_rund(r.get("marge")), marge_rang.get(cik)],
                "vorsteuer": [_rund(r.get("vorsteuer_marge_fy")), vorsteuer_rang.get(cik)],
                "roe": [_rund(r.get("roe")), roe_rang.get(cik)]}
        fr = fund_reihen.get(cik) if cik is not None else None
        if fr:
            try:
                uq, verm = umsatz_reihe(fr)
                eintrag["fundament"] = kennzahlen_fundament.kennzahlen(
                    fr, uq, umsatz_reihe_fy(fr, verm), branche_aus(verm), kurs=e.get("kurs"),
                    filer_typ=firmen.get(cik), heute=heute)
            except Exception as ex:  # noqa
                eintrag["fundament"] = {"fehler": f"{type(ex).__name__}: {ex}"}
        if cik is not None and (r is not None or fr):
            # Entscheidung 8: drei Haekchen, kein Filter
            eintrag["canslim"] = kennzahlen_fundament.canslim(
                eintrag["eps_wachstum_vj_pct"], (eintrag.get("fundament") or {}).get("eps_cagr3"),
                (r or {}).get("roe"))
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
    # Firma 6: Geraetehersteller mit kleinen Mieterloesen aus dem Leasing neben grossem Umsatz (DELL-Fall, 13.09.2026)
    zeilen += _quartale(6, "eps_verwaessert", [1.0 + 0.1 * i for i in range(14)])
    zeilen += _quartale(6, "umsatz", [25000 + 500 * i for i in range(14)])
    zeilen += _quartale(6, "mieterloese", [400 + 5 * i for i in range(14)])
    zeilen += _quartale(6, "nettogewinn", [1000 + 50 * i for i in range(14)])
    # Firma 7: REIT, Mieterloese tragen das Geschaeft, daneben ein kleiner sonstiger Umsatz
    zeilen += _quartale(7, "eps_verwaessert", [0.5 + 0.02 * i for i in range(14)])
    zeilen += _quartale(7, "umsatz", [30 + i for i in range(14)])
    zeilen += _quartale(7, "mieterloese", [500 + 10 * i for i in range(14)])
    zeilen += _quartale(7, "nettogewinn", [100 + 2 * i for i in range(14)])
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
    p("Nachschlagen: Umsatz juengst, Vorquartal und Vorjahr mit Quartalsende; Wachstum zum Vorjahr rund 46 Prozent, "
      "EPS-Vorjahr 2,48",
      r1["umsatz_juengst"] is not None and r1["umsatz_vorquartal"] is not None and r1["umsatz_vorjahr"] is not None
      and abs(wachstum_pct(r1["umsatz_juengst"], r1["umsatz_vorjahr"]) - 46.4) < 0.2
      and abs(wachstum_pct(r1["umsatz_juengst"], r1["umsatz_vorquartal"]) - 10.0) < 0.2
      and r1["eps_vorjahr"] == 2.48 and str(r1["umsatz_ende"]).startswith("2026-06"),
      {k: r1[k] for k in ("umsatz_juengst", "umsatz_vorquartal", "umsatz_vorjahr", "umsatz_ende", "eps_vorjahr", "eps_vorquartal")})
    p("Wachstum in Prozent nur bei positiver Basis", wachstum_pct(150, 100) == 50.0 and wachstum_pct(1.0, -0.5) is None
      and wachstum_pct(1.0, 0) is None and wachstum_pct(None, 1) is None)
    r3 = bewerten_firma(_reihen(df[df.cik == 3]), heute=heute)
    p("W5 Bank: Nettoertraege statt Umsatz, mit Vermerk", any(v.startswith("Bank") for v in r3["vermerke"]) and r3["sales_roh"] is not None, r3["vermerke"])
    r4 = bewerten_firma(_reihen(df[df.cik == 4]), heute=heute)
    p("Antwort 10: Biotech mit fuenf Quartalen bekommt trotzdem einen Wert, Quartalszahl 5, kein Umsatzurteil",
      r4["quartale"] == 5 and r4["eps_roh"] is not None and any("kein Umsatzurteil" in v for v in r4["vermerke"]), r4)
    r6 = bewerten_firma(_reihen(df[df.cik == 6]), heute=heute)
    p("W5 mit Wächter: kleine Mieterloese neben grossem Umsatz machen keine Immobilienfirma, der Umsatz gilt",
      not any(v.startswith("Immobilien") for v in r6["vermerke"]) and r6["umsatz_juengst"] > 25000, r6["vermerke"])
    r7 = bewerten_firma(_reihen(df[df.cik == 7]), heute=heute)
    p("W5: beim REIT tragen die Mieterloese das Geschaeft und gelten, mit Vermerk",
      any(v.startswith("Immobilien") for v in r7["vermerke"]) and r7["umsatz_juengst"] > 500, r7["vermerke"])
    r5 = bewerten_firma(_reihen(df[df.cik == 5]), heute=heute)
    p("Antwort 8: IFRS-Firma laeuft mit und ist als ungeprueft gekennzeichnet", r5["ifrs"] and any("IFRS" in v for v in r5["vermerke"]))
    # Firma 8: Umsatz gleich hoch je Woche, das juengste Quartal hat 14 Wochen.
    # Ohne W7 saehe das nach 7,7 Prozent Wachstum aus, mit W7 sind es null.
    zeilen8 = _quartale(8, "eps_verwaessert", [1.0] * 14) + _quartale(8, "umsatz", [91.0] * 13 + [98.0], lang_letztes=True)
    zeilen8 += _quartale(8, "nettogewinn", [9.1] * 13 + [9.8], lang_letztes=True)
    r8 = bewerten_firma(_reihen(pd.DataFrame(zeilen8)), heute=heute)
    p("W7 auch beim Umsatz: 14-Wochen-Quartal mit gleichem Wochenumsatz ergibt null Wachstum, Vermerk, Marge aus den SEC-Zahlen",
      r8["umsatz_juengst"] == 91.0 and abs(wachstum_pct(r8["umsatz_juengst"], r8["umsatz_vorjahr"])) < 0.05
      and any("13 Wochen" in v for v in r8["vermerke"]) and abs(r8["marge"] - 0.1) < 1e-9,
      {k: r8[k] for k in ("umsatz_juengst", "umsatz_vorjahr", "marge", "vermerke")})

    rs = {"listen": {"AAA": {"rs": 90, "ad_rang": 70, "abst_52w_hoch_pct": -2.0},
                     "BBB": {"rs": 20, "ad_rang": 30, "abst_52w_hoch_pct": -30.0}},
          "aktien": {"CCC": {"rs": 50, "ad_rang": 50, "abst_52w_hoch_pct": -10.0},
                     "DDD": {"rs": 60, "ad_rang": 55, "abst_52w_hoch_pct": -5.0},
                     "EEE": {"rs": 70, "ad_rang": 80, "abst_52w_hoch_pct": -3.0},
                     "FFF": {"rs": 40}},
          "ausserhalb": {"GGG": {"rs": 30, "ad_rang": 40, "abst_52w_hoch_pct": -40.0, "grund": "Kurs unter 15 Dollar"},
                         "HHH": {"grund": "keine Kurse"}}}
    zu = {"AAA": 1, "BBB": 2, "CCC": 3, "DDD": 4, "EEE": 5, "GGG": 1}
    import tempfile
    pfad = os.path.join(tempfile.mkdtemp(), "r.json")
    inhalt = bauen([], rs, kennzahlen=df, zuordnung=zu, pfad=pfad, leise=True, heute=heute)
    a = inhalt["aktien"]
    p("Ratings gebaut: Firma 1 vor Firma 2 beim EPS-Rang, Noten vergeben (Wachser mindestens C, Schrumpfer D oder E)",
      a["AAA"]["eps"] > a["BBB"]["eps"] and a["AAA"]["smr"] in "ABC" and a["BBB"]["smr"] in "DE", {t: (e["eps"], e["smr"]) for t, e in a.items()})
    p("Titel unter den Schwellen mit RS werden gerechnet (GGG), ohne RS nicht (HHH)",
      "GGG" in a and a["GGG"]["eps"] is not None and a["GGG"]["composite"] is not None and "HHH" not in a,
      {k: a[k].get("composite") for k in a})
    p("Wachstumszahlen stehen im Eintrag, Prozent gerundet",
      a["AAA"]["umsatz_juengst"] is not None and abs(a["AAA"]["umsatz_wachstum_vj_pct"] - 46.4) < 0.2
      and a["AAA"]["eps_wachstum_vj_pct"] is not None, {k: a["AAA"][k] for k in ("umsatz_wachstum_vj_pct", "eps_wachstum_vj_pct")})
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
    # Etappe 4: SMR-Bausteine, Fundament und CAN-SLIM-Haekchen je Aktie
    b_aaa = a["AAA"].get("smr_bausteine") or {}
    p("Etappe 4: SMR-Bausteine mit Rohwert und Rang, Fundament-Kennzahlen und drei CAN-SLIM-Haekchen im Eintrag",
      set(b_aaa) == {"umsatz", "marge", "vorsteuer", "roe"} and b_aaa["umsatz"][1] is not None
      and isinstance(a["AAA"].get("fundament"), dict) and "fehler" not in a["AAA"]["fundament"]
      and set(a["AAA"].get("canslim") or {}) == {"eps_q", "eps_cagr3", "roe"} and "fundament_stand" in inhalt,
      {k: a["AAA"].get(k) for k in ("smr_bausteine", "canslim")})
    # Vollmachtsunterlagen: Arista-Fall (Letztfassung aus DEF 14A in Tausend markiert)
    def zeile_v(kz, wert_erst, form_erst, filed_erst, wert_letzt, form_letzt, filed_letzt, ende="2022-12-31"):
        return {"cik": 9, "kennzahl": kz, "typ": "FY", "start": ende[:4] + "-01-01", "end": ende, "wert_letzt": wert_letzt,
                "quelle": "amtlich", "taxonomie": "us-gaap", "fiskalperiode": "FY", "einheit": "USD", "wert_erst": wert_erst,
                "form_erst": form_erst, "form_letzt": form_letzt, "filed_erst": filed_erst, "filed_letzt": filed_letzt}
    dv = pd.DataFrame([zeile_v("nettogewinn", 1.352446e9, "10-K", "2023-02-14", 1352.0, "DEF 14A", "2026-04-16"),
                       zeile_v("nettogewinn", 259.49, "DEF 14A", "2026-04-09", 259.49, "DEF 14A", "2026-04-09", "2023-12-31"),
                       zeile_v("umsatz", 4.38e9, "10-K", "2023-02-14", 4.381e9, "10-K", "2025-02-19"),
                       zeile_v("nettogewinn", 2.0e9, "10-K", "2024-02-13", 2.1e9, "DEFR14A", "2026-04-16", "2024-12-31")])
    ov = ohne_vollmachtszahlen(dv)
    p("Vollmachtsunterlagen: Letztfassung aus DEF 14A oder DEFR14A gilt nicht, die Erstfassung aus dem Abschluss schon; "
      "stammen beide aus Vollmachtsunterlagen, faellt die Zeile weg; ohne Formularspalten bleibt alles",
      len(ov) == 3 and list(ov["wert_letzt"]) == [1.352446e9, 4.381e9, 2.0e9] and list(ov["form_letzt"]) == ["10-K", "10-K", "10-K"]
      and list(ov["filed_letzt"]) == ["2023-02-14", "2025-02-19", "2024-02-13"]
      and ohne_vollmachtszahlen(dv.drop(columns=["form_erst", "form_letzt"])).equals(dv.drop(columns=["form_erst", "form_letzt"])),
      ov[["kennzahl", "end", "wert_letzt", "form_letzt"]].to_dict("records"))
    # Doppelte Periodenenden: die juengste Einreichung gewinnt, gleich in welcher Zeilenfolge (National-Beverage-Fall)
    def zeile_d(start, wert, filed):
        return {"cik": 10, "kennzahl": "eps_verwaessert", "typ": "Q", "start": start, "end": "2023-07-29", "wert_letzt": wert,
                "quelle": "amtlich", "taxonomie": "us-gaap", "fiskalperiode": "Q1", "filed_letzt": filed}
    d1 = pd.DataFrame([zeile_d("2023-05-01", 0.53, "2024-09-05"), zeile_d("2023-04-30", 53.0, "2023-09-07")])
    d2 = pd.DataFrame([zeile_d("2023-04-30", 53.0, "2023-09-07"), zeile_d("2023-05-01", 0.53, "2024-09-05")])
    je_f = _reihen_je_firma(df)
    p("Reihen je Firma in einem Durchgang: dieselben Reihen wie je Firma einzeln, alle Firmen",
      sorted(je_f) == sorted(int(c) for c in df.cik.unique())
      and all(je_f[c] == _reihen(df[df.cik == c]) for c in je_f) and _reihen_je_firma(df.iloc[0:0]) == {},
      sorted(je_f))
    p("Doppelte Periodenenden: die juengste Einreichung gewinnt, unabhaengig von der Zeilenfolge",
      [e[2] for e in _reihen(d1)["eps_verwaessert"]["Q"]] == [0.53] and [e[2] for e in _reihen(d2)["eps_verwaessert"]["Q"]] == [0.53],
      (_reihen(d1), _reihen(d2)))
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
