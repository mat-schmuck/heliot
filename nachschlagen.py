#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NACHSCHLAGEN: eine Aktie, alle unsere Zahlen, als Text
======================================================
Mathias' Auftrag vom 13.09.2026: Kuerzel oder Namen eingeben, dann alle
unsere Ratings, das Volumen nach unserer Volumenformel samt der bisher
gehandelten Stueckzahl, Umsatz- und Gewinnwachstum je Aktie mit den Zahlen
dahinter, und der Rang des Sektors. Fuer das iPhone mit VoiceOver: nur
Text, keine Tabellen, jede Angabe ein eigener Satz, keine Gedankenstriche.
Ohne KI; jede Zahl ist gerechnet, nichts ist geraten.

WOHER DIE ZAHLEN KOMMEN
  Nachtwerte aus dem Repo (der Nachtscan schreibt sie; der Ablauf
  nachschlag_daten.yml baut sie auf Zuruf frisch):
    rs_universum.json      RS gegen den ganzen US-Markt, Kurs, 52-Wochen-Hoch, seit
                           Etappe 2 die technischen Kennzahlen je Aktie (technik),
                           RS-Linien, Kennzeichnung "im Universum"
    ibd_ratings.json       EPS, SMR, A/D und Composite als Naeherung aus dem
                           SEC-Fundament (amtlich), dazu Umsatz und Gewinn je
                           Aktie des juengsten Quartals, des Vorquartals und
                           des Vorjahresquartals; seit Etappe 4 die
                           SMR-Bausteine, die fundamentalen Kennzahlen
                           (fundament: Margen, Wachstum, Bilanz, Cashflow,
                           F-Score, Altman Z, Bewertung, Streubesitz) und die
                           CAN-SLIM-Haekchen
    sektor_rangliste.json  Rang des Sektor-ETFs (36 ETFs, Faber-Mittel)
    volumenkurven.json     die eigene Volumenkurve je Listenaktie
  Live von Yahoo, ohne Schluessel: Kurs, das bisher gehandelte Volumen des
  Tages, fuer Aktien ohne Vorratskurve die Fuenf-Minuten-Historie fuer die
  Kurve, der Sektor, wenn die Aktie in keiner Wochenliste steht, und der
  Schlusskurs am Stichtag des Streubesitzes (daraus die Zahl der Aktien).

DIE VOLUMENFORMEL ist die von volumen.py (Gerhard, 28.07.2026): waehrend
des Handels hochgerechnet auf den Tag nach der eigenen Kurve der Aktie,
nach Handelsschluss die reine IBD-Tagesformel gegen den 50-Tage-Schnitt.
Ohne eigene Kurve heisst es "nicht verifizierbar", nie eine Ersatzrechnung.

Aufruf:
  python nachschlagen.py --selbsttest       ohne Netz
  python nachschlagen.py --zeige AAOI       echter Lauf: Dateien aus Repo oder Ordner, Kurse von Yahoo
"""

import argparse
import json
import re
import sys
from datetime import datetime

REPO_ROH = "https://raw.githubusercontent.com/mat-schmuck/heliot/main/"
DATEIEN = ("rs_universum.json", "ibd_ratings.json", "sektor_rangliste.json", "volumenkurven.json")
# Yahoo nennt die Sektoren fast wie Finviz; nur einer weicht ab.
SEKTOR_YAHOO = {"Financial Services": "Financial"}
# Wie die Sektornamen der Wochenlisten in Meldungen heissen.
SEKTOR_DEUTSCH = {"Technology": "Technologie", "Financial": "Finanzen", "Healthcare": "Gesundheit",
                  "Energy": "Energie", "Industrials": "Industrie", "Consumer Cyclical": "Zyklischer Konsum",
                  "Consumer Defensive": "Nichtzyklischer Konsum", "Basic Materials": "Grundstoffe",
                  "Communication Services": "Kommunikation", "Utilities": "Versorger", "Real Estate": "Immobilien"}


# ---------------------------------------------------------------------------
# Dateien und Schreibweise
# ---------------------------------------------------------------------------

def lade_datei(name, holen=None):
    """Erst das Repo (raw), dann die Datei im Ordner; leeres dict, wenn nichts da ist."""
    if holen is not None:
        try:
            d = holen(name)
            if d:
                return d
        except Exception:  # noqa
            pass
    else:
        try:
            import requests
            r = requests.get(REPO_ROH + name, timeout=20)
            if r.status_code == 200:
                d = r.json()
                if isinstance(d, dict):
                    return d
        except Exception:  # noqa
            pass
    try:
        with open(name, encoding="utf-8-sig") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def zahl(x, stellen=0):
    """Deutsche Schreibweise: Tausenderpunkt, Dezimalbeistrich; None wird 'unbekannt'."""
    if x is None:
        return "unbekannt"
    try:
        v = float(x)
        s = f"{abs(v):,.{stellen}f}"
    except (TypeError, ValueError):
        return str(x)
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return ("minus " + s) if v < 0 and float(s.replace(".", "").replace(",", ".")) != 0 else s


def prozent(x, stellen=0):
    """'plus 12,3 Prozent' oder 'minus 4 Prozent'; None wird 'nicht berechenbar'."""
    if x is None:
        return "nicht berechenbar"
    v = float(x)
    return ("plus " if v >= 0 else "minus ") + zahl(abs(v), stellen) + " Prozent"


def datum_text(iso):
    """'2026-06-30' wird '30.06.2026'."""
    s = str(iso or "")[:10]
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    return f"{m.group(3)}.{m.group(2)}.{m.group(1)}" if m else (s or "unbekannt")


def firmenname(name):
    """'Apple Inc. - Common Stock' wird 'Apple Inc.'"""
    n = str(name or "").strip()
    for trenner in (" - Common Stock", " - Class A", " - Class B", " - Class C", " - Ordinary Shares",
                    " - American Depositary Shares", " Common Stock", " Class A Common Stock", " - "):
        if trenner in n:
            n = n.split(trenner)[0]
    return n.strip()


# ---------------------------------------------------------------------------
# Suche
# ---------------------------------------------------------------------------

def eintraege(rs):
    """{Ticker: Eintrag} ueber 'ausserhalb', 'aktien' und 'listen'; die Listen
    ueberdecken, was sie kennen, der Name bleibt vom Verzeichnis."""
    raus = {}
    for gruppe in ("ausserhalb", "aktien", "listen"):
        for t, e in ((rs or {}).get(gruppe) or {}).items():
            if isinstance(e, dict):
                k = str(t).upper()
                raus[k] = {**raus.get(k, {}), **e, "_gruppe": gruppe}
    return raus


_KUERZEL = re.compile(r"[A-Z][A-Z0-9]{0,5}([.\-][A-Z])?")


def finde(eingabe, rs):
    """Rueckgabe (ticker, kandidaten). Ein bekanntes Kuerzel ergibt (Kuerzel, []);
    ein Firmenname ergibt (None, [(Kuerzel, Name), ...]); ein unbekanntes Kuerzel
    ergibt (Kuerzel, []), damit die Live-Werte trotzdem kommen."""
    alle = eintraege(rs)
    s = str(eingabe or "").strip()
    if not s:
        return None, []
    t = s.upper().replace(" ", "")
    if t in alle:
        return t, []
    varianten = {k.replace(".", "-"): k for k in alle}
    if t.replace(".", "-") in varianten:
        return varianten[t.replace(".", "-")], []
    wort = s.lower()
    treffer = []
    for k, e in alle.items():
        n = str(e.get("name") or e.get("firma") or "")
        if wort in n.lower():
            treffer.append((k, firmenname(n)))
    treffer.sort(key=lambda p: (not p[1].lower().startswith(wort), p[1]))
    if len(treffer) == 1:
        return treffer[0][0], []
    if treffer:
        return None, treffer[:8]
    if _KUERZEL.fullmatch(t):
        return t, []
    return None, []


# ---------------------------------------------------------------------------
# Live-Werte (Netz) und Kurve
# ---------------------------------------------------------------------------

def live_daten(ticker, jetzt=None, holen=None):
    """Kurs, Tagesvolumen bisher und 50-Tage-Schnitt von Yahoo. holen(ticker)
    liefert im Selbsttest einen DataFrame mit Close und Volume und Datumsindex.
    None, wenn nichts kommt."""
    import volumen
    try:
        from zoneinfo import ZoneInfo
        ny = ZoneInfo("America/New_York")
    except Exception:  # noqa
        return None
    jetzt = (jetzt or datetime.now(ny)).astimezone(ny)
    try:
        if holen is not None:
            df = holen(ticker)
        else:
            import yfinance as yf
            df = yf.Ticker(ticker).history(period="4mo", interval="1d", auto_adjust=False)
    except Exception:  # noqa
        return None
    if df is None or len(df) == 0:
        return None
    df = df.dropna(subset=["Close"])
    if len(df) < 2:
        return None
    tage = [(d.date() if hasattr(d, "date") else d) for d in df.index]
    heute = jetzt.date()
    minute = volumen.minute_seit_eroeffnung(jetzt)
    vor_eroeffnung = (jetzt.hour * 60 + jetzt.minute) < (9 * 60 + 30)
    if tage[-1] == heute and minute is None and vor_eroeffnung:
        # Vorboerslich liefert Yahoo schon eine leere Zeile fuer heute.
        df = df.iloc[:-1]
        tage = tage[:-1]
        if len(df) < 2:
            return None
    handel_laeuft = (tage[-1] == heute and minute is not None)
    vol = df["Volume"]
    basis = vol.iloc[-51:-1]
    basis = basis[basis > 0]
    v50 = float(basis.mean()) if len(basis) >= 40 else None
    kurs = float(df["Close"].iloc[-1])
    vortag = float(df["Close"].iloc[-2])
    return {"kurs": kurs, "vortag": vortag, "pct": (kurs / vortag - 1) * 100 if vortag else None,
            "v_bisher": int(vol.iloc[-1]) if vol.iloc[-1] == vol.iloc[-1] else None, "v50": v50,
            "minute": minute if handel_laeuft else None, "handel_laeuft": handel_laeuft,
            "tag": tage[-1].isoformat(), "stand": jetzt.strftime("%H:%M") + " Uhr New York"}


def kurve_fuer(ticker, kurven_json=None, bauen=True, holen=None):
    """(Kurve, Quelle): aus dem Vorrat volumenkurven.json, sonst live aus der
    Fuenf-Minuten-Historie von Yahoo (nur wenn bauen). holen(ticker) liefert im
    Selbsttest den Fuenf-Minuten-Rahmen."""
    import volumen
    t = str(ticker or "").upper()
    e = ((kurven_json or {}).get("aktien") or {}).get(t)
    if isinstance(e, dict) and e.get("kurve"):
        return {int(m): float(a) for m, a in e["kurve"].items()}, "Vorrat"
    if not bauen:
        return None, "keine"
    try:
        if holen is not None:
            df = holen(t)
        else:
            import yfinance as yf
            df = yf.download(t, period="59d", interval="5m", progress=False, auto_adjust=False)
    except Exception:  # noqa
        return None, "keine"
    try:
        kurve, n_tage = volumen._kurve_aus_kerzen(df)
    except Exception:  # noqa
        return None, "keine"
    if volumen.entscheide_kurven_quelle(n_tage) != "eigene_aktie" or not kurve:
        return None, "keine"
    return kurve, "live"


def sektor_name_fuer(ticker, holen_info=None):
    """(Finviz-Sektorname, Quelle): erst die Wochenlisten, sonst Yahoo."""
    try:
        import listen
        s = listen.sektor_von(ticker)
        if s:
            return s, "Wochenliste"
    except Exception:  # noqa
        pass
    try:
        if holen_info is not None:
            info = holen_info(ticker)
        else:
            import yfinance as yf
            info = yf.Ticker(ticker).info
        s = (info or {}).get("sector")
        if s:
            return SEKTOR_YAHOO.get(s, s), "Yahoo"
    except Exception:  # noqa
        pass
    return None, "keine"


# ---------------------------------------------------------------------------
# Die Saetze
# ---------------------------------------------------------------------------

def _vorwoche(e, tage=5):
    """Der RS-Wert am juengsten Verlaufstag, der mindestens tage Kalendertage
    zurueckliegt: 5 fuer eine Woche, 26 fuer vier Wochen."""
    verlauf = e.get("rs_verlauf") or []
    if len(verlauf) < 2:
        return None
    heute = verlauf[-1][0] if isinstance(verlauf[-1], list) and verlauf[-1] else None
    for tag, wert in reversed(verlauf[:-1]):
        try:
            if heute and (datetime.fromisoformat(heute) - datetime.fromisoformat(tag)).days >= tage:
                return wert
        except (TypeError, ValueError):
            continue
    return None


def kopf_saetze(t, e, live):
    name = firmenname(e.get("name") or e.get("firma")) or t
    s = [f"{t}, {name}" + (f", {e['boerse']}" if e.get("boerse") else "") + "."]
    if live and live.get("kurs") is not None:
        s.append(f"Kurs {zahl(live['kurs'], 2)} Dollar, {prozent(live.get('pct'), 1)} gegenüber dem Vortag, "
                 f"Stand {live.get('stand')}.")
    elif e.get("kurs") is not None:
        s.append(f"Schlusskurs am {datum_text(e.get('letzter_tag'))}: {zahl(e['kurs'], 2)} Dollar, "
                 f"{prozent(e.get('pct'), 1)} gegenüber dem Vortag.")
    else:
        s.append("Kein Kurs bekannt.")
    if e.get("abst_52w_hoch_pct") is not None:
        s.append(f"Abstand zum 52-Wochen-Hoch {prozent(e['abst_52w_hoch_pct'], 1)}"
                 + (", die Aktie steht auf dem 52-Wochen-Hoch" if e.get("kurs_52w_hoch") else "") + ".")
    if e.get("_gruppe") == "ausserhalb" and e.get("grund"):
        s.append(f"Nicht im Universum: {e['grund']}; der RS-Wert gilt trotzdem, gerechnet gegen den ganzen Bezug.")
    return s


def ratings_saetze(e, r, ratings):
    import rs_universum
    s = []
    if e.get("rs") is not None:
        vor = _vorwoche(e)
        # Etappe 2, Punkt 15 (Gerhard, 13.09.2026): die Aenderung auch ueber
        # vier Wochen, dieselbe Regel wie technik.rs_4w in rs_universum.
        vor4 = _vorwoche(e, 26)
        s.append(f"RS {int(e['rs'])}" + (", sehr gut" if int(e["rs"]) >= 85 else "")
                 + (f"; vor einer Woche {int(vor)}, Änderung {int(e['rs']) - int(vor):+d}".replace("+", "plus ").replace("-", "minus ")
                    if vor is not None else "")
                 + (f"; vor vier Wochen {int(vor4)}, Änderung {int(e['rs']) - int(vor4):+d}".replace("+", "plus ").replace("-", "minus ")
                    if vor4 is not None else "") + ".")
    elif e.get("rs_vorlaeufig") is not None:
        # Etappe 1, Entscheidung 1 (Gerhard, 13.09.2026): junge Titel
        s.append(rs_universum.rs_text(e["rs_vorlaeufig"], quartale=e.get("rs_quartale"))
                 + f"; gerechnet aus den vorhandenen Quartalen gegen den ganzen Bezug, "
                 f"die Aktie hat erst {e.get('tage')} Schlusskurse.")
    else:
        s.append("RS nicht verfügbar" + (f": {e['grund']}" if e.get("grund") else ", die Aktie steht in keiner Nachtdatei") + ".")
    lt = rs_universum.linien_text(e) if e else ""
    if lt:
        s.append(lt + ".")
    if not ratings:
        s.append("EPS, SMR, A/D und Composite: noch nicht gerechnet, die Ratings-Datei fehlt.")
        return s
    if ratings.get("status") != "ok":
        s.append("EPS, SMR, A/D und Composite nicht verfügbar: " + str(ratings.get("grund") or ratings.get("status")) + ".")
        return s
    if not r:
        s.append("EPS, SMR, A/D und Composite: für diese Aktie nicht gerechnet.")
        return s
    s.append(f"EPS-Rating {int(r['eps'])}." if r.get("eps") is not None else "EPS-Rating nicht verfügbar.")
    s.append(f"SMR-Note {r['smr']}, Rang {int(r['smr_rang'])}." if r.get("smr") else "SMR-Note nicht verfügbar.")
    # Etappe 4, Punkt 13 (Gerhard, 13.09.2026): die Bausteine des SMR mit Rohwert und Rang
    bs = r.get("smr_bausteine") or {}
    teile = []
    for k, name in (("umsatz", "Umsatzwachstum der drei jüngsten Quartale gegen das Vorjahr"),
                    ("marge", "Nettomarge des jüngsten Quartals"), ("vorsteuer", "Vorsteuermarge des Geschäftsjahres"),
                    ("roe", "Eigenkapitalrendite")):
        roh, rang = (bs.get(k) or [None, None])[:2]
        if roh is None:
            continue
        wert = prozent(roh * 100.0, 1) if k == "umsatz" else _pz(roh)
        teile.append(f"{name} {wert}" + (f", Rang {int(rang)}" if rang is not None else ""))
    if teile:
        s.append("SMR-Bausteine: " + "; ".join(teile) + ".")
    s.append(f"A/D-Note {r['ad']}, Rang {int(r['ad_rang'])}, Näherung aus der Schlusslage in der Tagesspanne und dem Volumen."
             if r.get("ad")
             else "A/D-Note nicht verfügbar.")
    if r.get("composite") is not None:
        s.append(f"Composite {int(r['composite'])}.")
    else:
        fehlt = r.get("composite_fehlt") or []
        s.append("Composite nicht verfügbar" + (f", es fehlt {', '.join(fehlt)}" if fehlt else "") + ".")
    zusatz = [f"Basis {r.get('basis', 'amtlich')}", f"{int(r.get('quartale') or 0)} Quartale"]
    if r.get("ifrs"):
        zusatz.append("IFRS-Zahlen ungeprüft")
    s.append(", ".join(zusatz) + ".")
    for v in r.get("vermerke") or []:
        if "IFRS" in v:
            continue
        s.append(v.replace("ue", "ü").replace("ae", "ä").replace("oe", "ö").replace("Naeherung", "Näherung") + ".")
    return s


def volumen_saetze(live, kurve, kurve_quelle=""):
    import volumen
    if not live or live.get("v_bisher") is None:
        return ["Kein Volumen von Yahoo bekommen."]
    s = []
    v_bisher, v50 = live["v_bisher"], live.get("v50")
    if live.get("handel_laeuft"):
        m = live.get("minute") or 0
        s.append(f"Bisher gehandelt: {zahl(v_bisher)} Stück, {int(m)} Minuten nach Handelsbeginn in New York.")
        p = volumen.volume_pct_change(v_bisher, v50, kurve, m) if v50 else None
        if p is None:
            s.append("Nach unserer Volumenformel nicht verifizierbar: "
                     + ("kein 50-Tage-Schnitt." if not v50 else "keine eigene Volumenkurve, unter 40 Handelstagen Historie."))
        else:
            s.append(f"Nach unserer Volumenformel, hochgerechnet auf den ganzen Tag: {prozent(p)} gegenüber dem 50-Tage-Schnitt"
                     + (", Kurve aus dem Vorrat des Nachtscans" if kurve_quelle == "Vorrat" else ", Kurve frisch aus der eigenen Fünf-Minuten-Historie")
                     + ".")
    else:
        s.append(f"Letzter Handelstag {datum_text(live.get('tag'))}: {zahl(v_bisher)} Stück gehandelt.")
        p = volumen.volume_pct_change(v_bisher, v50, None, None) if v50 else None
        s.append("Nach unserer Volumenformel: " + (f"{prozent(p)} gegenüber dem 50-Tage-Schnitt." if p is not None
                                                     else "nicht verifizierbar, kein 50-Tage-Schnitt."))
    if v50:
        s.append(f"50-Tage-Schnitt: {zahl(v50)} Stück je Tag.")
    return s


def _vz(x, stellen=1):
    """'plus 12,3' oder 'minus 4,0' ohne Einheit; None wird 'unbekannt'."""
    if x is None:
        return "unbekannt"
    return ("plus " if float(x) >= 0 else "minus ") + zahl(abs(float(x)), stellen)


def monat_text(jjjj_mm):
    """'2021-03' wird 'März 2021'."""
    m = re.fullmatch(r"(\d{4})-(\d{2})", str(jjjj_mm or ""))
    return f"{MONATE[int(m.group(2)) - 1]} {m.group(1)}" if m and 1 <= int(m.group(2)) <= 12 else str(jjjj_mm or "unbekannt")


def _dollar_menge(x):
    """Grosse Dollarbetraege in Worten: '45,6 Millionen Dollar'."""
    if x is None:
        return "unbekannt"
    v = float(x)
    if v >= 1e9:
        return f"{zahl(v / 1e9, 1)} Milliarden Dollar"
    if v >= 1e6:
        return f"{zahl(v / 1e6, 1)} Millionen Dollar"
    return f"{zahl(v)} Dollar"


def technik_saetze(e):
    """ETAPPE 2 (Gerhard, 13.09.2026, Entscheidungen 4 und 5): die 16
    technischen Kennzahlen, je Kennzahl ein Satz, REINE ANZEIGE. Die Werte
    stehen in rs_universum.json unter technik; gerechnet werden sie in
    kennzahlen_technik.py. Die RS-Aenderung steht bei den Ratings."""
    tk = (e or {}).get("technik")
    if not tk:
        return ["Keine technischen Kennzahlen: Die Aktie steht in keiner Nachtdatei, oder es gab für sie keine Kurse."]
    if tk.get("split_verdacht") is not None:
        sv = float(tk["split_verdacht"])
        sprung = (f"springt am letzten Handelstag auf das {zahl(sv, 1)}-fache des Vortags" if sv >= 1
                  else f"fällt am letzten Handelstag auf {zahl(sv * 100, 1)} Prozent des Vortags")
        return [f"Technische Kennzahlen heute nicht verfügbar: Der Schlusskurs {sprung}, "
                "das Dollarvolumen bleibt aber ähnlich. Vermutlich ein Split oder Reverse-Split, den die Kursquelle "
                "noch nicht in die älteren Kurse eingerechnet hat; die Werte wären falsch."]
    s = []
    teile = [f"{wort} {prozent(tk[name], 1)}" for name, wort in (
        ("perf_1w", "eine Woche"), ("perf_1m", "ein Monat"), ("perf_3m", "drei Monate"), ("perf_6m", "sechs Monate"),
        ("perf_12m", "zwölf Monate"), ("perf_ytd", "seit Jahresbeginn")) if tk.get(name) is not None]
    s.append("Wertentwicklung: " + ("; ".join(teile) if teile else "nicht berechenbar") + ".")
    datum = str(tk.get("ath_datum") or "")
    if tk.get("ath") is None:
        s.append("Allzeithoch nicht verfügbar.")
    elif len(datum) == 10 and datum == e.get("letzter_tag"):
        s.append(f"Die Aktie steht auf ihrem Allzeithoch von {zahl(tk['ath'], 2)} Dollar.")
    else:
        wann = f" vom {datum_text(datum)}" if len(datum) == 10 else (f" im {monat_text(datum)}" if len(datum) == 7 else "")
        s.append(f"Allzeithoch {zahl(tk['ath'], 2)} Dollar{wann}; Abstand {prozent(tk.get('ath_abst'), 1)}.")
    teile = [f"SMA {n} {prozent(tk.get(f'sma{n}_abst'), 1)}" for n in (20, 50, 200) if tk.get(f"sma{n}_abst") is not None]
    s.append("Abstand zu den gleitenden Durchschnitten: " + ("; ".join(teile) if teile else "nicht berechenbar") + ".")
    teile = [f"{wort} {prozent(tk.get(name), 1)}" for name, wort in (
        ("hoch50_abst", "zum 50-Tage-Hoch"), ("tief50_abst", "zum 50-Tage-Tief"), ("tief52_abst", "zum 52-Wochen-Tief"))
        if tk.get(name) is not None]
    s.append("Abstand " + ("; ".join(teile) if teile else "zu Hoch und Tief nicht berechenbar") + ".")
    s.append(f"ADR nach Qullamaggie, die mittlere Tagesspanne über 20 Tage: {zahl(tk['adr20'], 2)} Prozent."
             if tk.get("adr20") is not None else "ADR nicht berechenbar.")
    teile = [f"{wort} {zahl(tk[name], 2)} Prozent" for name, wort in (("vola5", "Woche"), ("vola21", "Monat"))
             if tk.get(name) is not None]
    s.append(("Volatilität wie bei Finviz, dieselbe Spanne über 5 und 21 Tage: " + "; ".join(teile) + ".")
             if teile else "Volatilität nicht berechenbar.")
    if tk.get("atr14") is not None:
        kurs = e.get("kurs")
        s.append(f"ATR 14 nach Wilder: {zahl(tk['atr14'], 2 if tk['atr14'] >= 10 else 4 if tk['atr14'] < 1 else 2)} Dollar"
                 + (f", das sind {zahl(tk['atr14'] / kurs * 100, 1)} Prozent des Kurses" if kurs else "") + ".")
    else:
        s.append("ATR nicht berechenbar.")
    s.append(f"Up/Down-Volumen über 50 Tage: {zahl(tk['ud50'], 2)}; über 1 überwiegt das Volumen an Plus-Tagen."
             if tk.get("ud50") is not None else "Up/Down-Volumen über 50 Tage nicht berechenbar.")
    if tk.get("mrs") is not None:
        richtung = ""
        if tk.get("mrs_vorher") is not None:
            richtung = (", also steigend" if tk["mrs"] > tk["mrs_vorher"]
                        else ", also fallend" if tk["mrs"] < tk["mrs_vorher"] else ", also unverändert")
            richtung = f", vor vier Wochen {_vz(tk['mrs_vorher'], 1)}{richtung}"
        s.append(f"Mansfield RS gegen SPY: {_vz(tk['mrs'], 1)}{richtung}.")
    else:
        s.append("Mansfield RS nicht berechenbar, dafür braucht es 52 Wochen gemeinsam mit dem Index.")
    s.append(weinstein_satz(tk))
    if tk.get("burst"):
        s.append(f"Momentum Burst nach Stockbee am letzten Handelstag: {prozent(e.get('pct'), 1)} bei höherem Volumen als am Vortag"
                 + (f"; Schluss bei {int(tk['schlusslage'])} Prozent der Tagesspanne" if tk.get("schlusslage") is not None else "")
                 + (f"; Vortag {prozent(tk['vortag_pct'], 1)} bei {zahl(tk.get('vortag_spanne'), 1)} Prozent Spanne"
                    if tk.get("vortag_pct") is not None else "") + ".")
    elif tk.get("burst") is False:
        s.append("Kein Momentum Burst nach Stockbee am letzten Handelstag.")
    else:
        s.append("Momentum Burst nicht berechenbar.")
    teile = []
    if tk.get("luecke") is not None:
        teile.append(f"Eröffnungslücke {prozent(tk['luecke'], 1)}")
    if tk.get("seit_eroeffnung") is not None:
        teile.append(f"seit Eröffnung {prozent(tk['seit_eroeffnung'], 1)}")
    if tk.get("vol_faktor") is not None:
        teile.append(f"Volumen {zahl(tk['vol_faktor'], 1)} mal so hoch wie der 50-Tage-Schnitt")
    s.append(("Am letzten Handelstag: " + "; ".join(teile) + ".") if teile else "Eröffnungslücke nicht bekannt.")
    if tk.get("pivot"):
        s.append("Episodic Pivot: Die Eröffnungslücke liegt bei 10 Prozent oder mehr.")
    s.append(f"Beta gegen SPY über 252 Handelstage: {zahl(tk['beta'], 2)}." if tk.get("beta") is not None
             else "Beta nicht berechenbar, dafür braucht es 252 Tagesrenditen gemeinsam mit dem Index.")
    teile = [f"RSI {n} bei {zahl(tk[name], 1)}" for n, name in ((14, "rsi14"), (2, "rsi2")) if tk.get(name) is not None]
    s.append(("; ".join(teile) + ".") if teile else "RSI nicht berechenbar.")
    teile = []
    if tk.get("vol63") is not None:
        teile.append(f"Durchschnittsvolumen über drei Monate {zahl(tk['vol63'])} Stück je Tag")
    if tk.get("dv20") is not None:
        teile.append(f"Dollarvolumen über 20 Tage {_dollar_menge(tk['dv20'])} je Tag")
    s.append(("; ".join(teile) + ".") if teile else "Durchschnittsvolumen nicht berechenbar.")
    s.append("Reine Anzeige: Keine dieser Kennzahlen filtert.")
    return s


def weinstein_satz(tk):
    """Die Weinstein-Stufe in einem Satz, mit den Zahlen, auf denen sie steht."""
    stufe, abst, steig = tk.get("stufe"), tk.get("linie_abst"), tk.get("linie_steig")
    if stufe is None or abst is None or steig is None:
        return "Weinstein-Stufe nicht berechenbar, dafür braucht es 34 Wochen Kurse."
    lage = f"Kurs {zahl(abs(abst), 1)} Prozent {'über' if abst >= 0 else 'unter'} der 30-Wochen-Linie"
    linie = (f"die Linie steigt in vier Wochen um {zahl(abs(steig), 1)} Prozent" if steig > 0
             else f"die Linie fällt in vier Wochen um {zahl(abs(steig), 1)} Prozent" if steig < 0
             else "die Linie ist in vier Wochen unverändert")
    # Gerhard, 15.09.2026, Nachfrage N3: Stufe 2 und 4 nur noch aus der
    # 30-Wochen-Linie und dem Kurs; die Mansfield RS steht im Satz davor.
    if stufe == 2:
        return f"Weinstein-Stufe 2: {lage}, {linie}, die letzten zwei Wochenschlüsse liegen über der Linie."
    if stufe == 4:
        return f"Weinstein-Stufe 4: {lage}, {linie}, die letzten zwei Wochenschlüsse liegen unter der Linie."
    if stufe == 3:
        return f"Weinstein-Stufe 3: 30-Wochen-Linie flach nach einem Anstieg; {lage}."
    if stufe == 1:
        return f"Weinstein-Stufe 1: 30-Wochen-Linie flach nach einem Rückgang; {lage}."
    return f"Weinstein-Stufe nicht eindeutig: {lage}, {linie}."


def _begriff(r):
    for v in r.get("vermerke") or []:
        if v.startswith("Bank"):
            return "Nettoerträge, also Zinsüberschuss plus Provisionsertrag,"
        if v.startswith("Versicherer"):
            return "Verdiente Prämien"
        if v.startswith("Immobilien"):
            return "Mieterlöse"
    return "Umsatz"


def _wachstum_satz(was, jetzt, vorher, pct, bezug):
    if jetzt is None:
        return None
    if vorher is None:
        return f"{was}: {bezug} unbekannt."
    if pct is None:
        return f"{was} gegenüber dem {bezug}: kein Prozentwert, das {bezug} lag bei null oder im Minus; vorher {vorher}, jetzt {jetzt}."
    return f"{was} gegenüber dem {bezug}: {prozent(pct, 1)}; vorher {vorher}, jetzt {jetzt}."


def wachstum_saetze(r):
    if not r or (r.get("umsatz_juengst") is None and r.get("eps_juengst") is None):
        s = ["Noch keine Fundamentaldaten für diese Aktie."]
        for v in (r or {}).get("vermerke") or []:
            if "SEC" in v or "Release" in v:
                s.append(v + ".")
        return s + fundament_wachstum_saetze(r)
    s = []
    if r.get("umsatz_juengst") is not None:
        was = _begriff(r)
        s.append(_wachstum_satz(f"{was} Wachstum", f"{zahl(r['umsatz_juengst'])} Dollar",
                                f"{zahl(r.get('umsatz_vorjahr'))} Dollar" if r.get("umsatz_vorjahr") is not None else None,
                                r.get("umsatz_wachstum_vj_pct"), "Vorjahresquartal"))
        s.append(_wachstum_satz(f"{was} Wachstum", f"{zahl(r['umsatz_juengst'])} Dollar",
                                f"{zahl(r.get('umsatz_vorquartal'))} Dollar" if r.get("umsatz_vorquartal") is not None else None,
                                r.get("umsatz_wachstum_vq_pct"), "Vorquartal"))
        s.append(f"Jüngstes Quartal bis {datum_text(r.get('umsatz_ende'))}.")
    else:
        v = next((x for x in r.get("vermerke") or [] if x.startswith("kein Umsatzurteil")), "Kein Umsatz ausgewiesen")
        s.append(v.split(" (")[0].capitalize() + ".")
    if r.get("eps_juengst") is not None:
        s.append(_wachstum_satz("Gewinn je Aktie, Wachstum", f"{zahl(r['eps_juengst'], 2)} Dollar",
                                f"{zahl(r.get('eps_vorjahr'), 2)} Dollar" if r.get("eps_vorjahr") is not None else None,
                                r.get("eps_wachstum_vj_pct"), "Vorjahresquartal"))
        s.append(_wachstum_satz("Gewinn je Aktie, Wachstum", f"{zahl(r['eps_juengst'], 2)} Dollar",
                                f"{zahl(r.get('eps_vorquartal'), 2)} Dollar" if r.get("eps_vorquartal") is not None else None,
                                r.get("eps_wachstum_vq_pct"), "Vorquartal"))
        if r.get("eps_ende") and r.get("eps_ende") != r.get("umsatz_ende"):
            s.append(f"Gewinnquartal bis {datum_text(r.get('eps_ende'))}.")
    else:
        s.append("Gewinn je Aktie: kein Quartalswert im Fundament.")
    s.append(f"Quelle SEC-Fundament, Basis {r.get('basis', 'amtlich')}, {int(r.get('quartale') or 0)} Quartale"
             + (", IFRS-Zahlen ungeprüft" if r.get("ifrs") else "") + ".")
    return [x for x in s if x] + fundament_wachstum_saetze(r)


# ---------------------------------------------------------------------------
# Etappe 4: fundamentale Kennzahlen aus dem SEC-Fundament (Entscheidungen 7 und 8)
# ---------------------------------------------------------------------------
# Gerhard, 13.09.2026: alle 13 Punkte aus Gruppe B und die CAN-SLIM-Haekchen,
# reine Anzeige. Gerechnet wird in kennzahlen_fundament.py, abgelegt je Aktie
# in ibd_ratings.json unter "fundament" und "canslim".

def _pz(anteil, stellen=1):
    """Ein Anteil (0,123) als '12,3 Prozent', negativ mit 'minus'."""
    return "nicht berechenbar" if anteil is None else f"{zahl(float(anteil) * 100.0, stellen)} Prozent"


def _q(x, stellen=2):
    return "nicht berechenbar" if x is None else zahl(x, stellen)


def _betrag(x, wort="Dollar"):
    """Grosse Betraege in Worten mit Vorzeichen: 'minus 1,2 Milliarden Dollar'."""
    if x is None:
        return "unbekannt"
    v = float(x)
    vz = "minus " if v < 0 else ""
    a = abs(v)
    if a >= 1e9:
        return f"{vz}{zahl(a / 1e9, 1)} Milliarden {wort}"
    if a >= 1e6:
        return f"{vz}{zahl(a / 1e6, 1)} Millionen {wort}"
    return f"{vz}{zahl(a)} {wort}"


def _geldwort(f):
    w = (f or {}).get("waehrung")
    return "Dollar" if w in (None, "USD") else str(w)


def split_text(faktor):
    """1,5 wird 'Split 3 zu 2', 0,1 wird 'Reverse-Split 1 zu 10'."""
    import kennzahlen_fundament as kf
    f = float(faktor)
    g = f if f >= 1 else 1.0 / f
    nett = min(kf.SPLIT_FAKTOREN, key=lambda s: abs(s / g - 1.0))
    z, n = (3, 2) if nett == 1.5 else (int(nett), 1)
    return f"Split {z} zu {n}" if f >= 1 else f"Reverse-Split {n} zu {z}"


def _perioden(n):
    return "1 Periode" if n == 1 else f"{n} Perioden"


def fundament_wachstum_saetze(r):
    """Etappe 4, Punkte 1, 5 und 6 samt Entscheidung 8: Margen, acht Quartale
    Wachstum, Beschleunigung, CAGR, EPS-Stabilitaet, Verwaesserung und die
    CAN-SLIM-Haekchen; dazu, was an den Rohzahlen berichtigt wurde."""
    f = (r or {}).get("fundament")
    s = []
    if not f:
        return s
    if f.get("fehler"):
        return [f"Erweiterte Kennzahlen aus dem SEC-Fundament nicht berechnet: {f['fehler']}."]
    for art, wort in (("q", "im Quartal"), ("fy", "im Geschäftsjahr")):
        teile = [f"{name} {_pz(f.get(f'marge_{k}_{art}'))}" for k, name in (
            ("brutto", "brutto"), ("operativ", "operativ"), ("vorsteuer", "vor Steuern"), ("netto", "netto"))
                 if f.get(f"marge_{k}_{art}") is not None]
        if teile:
            s.append(f"Margen {wort} bis {datum_text(f.get(f'marge_ende_{art}'))}: " + "; ".join(teile) + ".")
    begriff = _begriff(r).rstrip(",")
    for feld, was in (("umsatz_vj", begriff), ("eps_vj", "Gewinn je Aktie")):
        liste = f.get(feld) or []
        if liste:
            teile = [f"bis {datum_text(e)} {prozent(p, 1)}" for e, p in liste]
            s.append(f"{was} gegenüber dem Vorjahresquartal, jüngstes zuerst: " + "; ".join(teile) + ".")
    for feld, was in (("umsatz_trend", begriff), ("eps_trend", "Gewinn je Aktie")):
        if f.get(feld):
            s.append(f"{was}, Wachstum über die drei jüngsten Quartale: {f[feld]}.")
    teile = []
    if f.get("umsatz_cagr3") is not None:
        teile.append(f"{begriff} über drei Jahre {prozent(f['umsatz_cagr3'], 1)}")
    if f.get("umsatz_cagr5") is not None:
        teile.append(f"über fünf Jahre {prozent(f['umsatz_cagr5'], 1)}")
    if f.get("eps_cagr3") is not None:
        teile.append(f"Gewinn je Aktie über drei Jahre {prozent(f['eps_cagr3'], 1)}")
    if teile:
        s.append("Jährliches Wachstum im Schnitt: " + "; ".join(teile) + ".")
    if f.get("eps_stabilitaet") is not None:
        s.append(f"EPS-Stabilität {int(f['eps_stabilitaet'])} über {int(f.get('stabilitaet_quartale') or 0)} Quartale, "
                 "Näherung nach IBD-Art: 1 heißt gleichmäßig, 99 sprunghaft.")
    teile = []
    if f.get("aktien_1j_pct") is not None:
        teile.append(f"gegenüber einem Jahr zuvor {prozent(f['aktien_1j_pct'], 1)}")
    if f.get("aktien_3j_pct") is not None:
        teile.append(f"gegenüber drei Jahren zuvor {prozent(f['aktien_3j_pct'], 1)}")
    if teile:
        s.append("Verwässerte Aktienzahl " + ", ".join(teile)
                 + (f", Stand {datum_text(f['aktien_ende'])}" if f.get("aktien_ende") else "") + ".")
    if f.get("sbc_umsatz") is not None:
        s.append(f"Aktienbasierte Vergütung {_pz(f['sbc_umsatz'])} des Umsatzes.")
    cs = (r or {}).get("canslim")
    if cs:
        try:
            from config import CFG
            g = CFG["fundament_kennzahlen"]
            grenzen = {"eps_q": g["canslim_eps_quartal_pct"], "eps_cagr3": g["canslim_eps_cagr3_pct"], "roe": g["canslim_roe_pct"]}
        except Exception:  # noqa
            grenzen = {"eps_q": 25, "eps_cagr3": 25, "roe": 17}
        teile = []
        for k, name in (("eps_q", "Quartals-EPS gegenüber dem Vorjahr"), ("eps_cagr3", "Dreijahres-CAGR des Gewinns je Aktie"),
                        ("roe", "Eigenkapitalrendite")):
            erfuellt, wert = (cs.get(k) or [None, None])[:2]
            grenze = f"ab {zahl(grenzen[k])} Prozent"
            if erfuellt is None:
                teile.append(f"{name} {grenze} offen, nicht berechenbar")
            else:
                w = prozent(wert, 1) if k != "roe" else f"{zahl(wert, 1)} Prozent"
                teile.append(f"{name} {grenze} {'erfüllt' if erfuellt else 'nicht erfüllt'} mit {w}")
        s.append("CAN-SLIM-Häkchen, kein Filter: " + "; ".join(teile) + ".")
    if f.get("splits"):
        s.append("Eingerechnet: " + "; ".join(f"{split_text(fk)}, Umrechnung ab {datum_text(tag)}" for fk, tag in f["splits"]) + ".")
    if f.get("einheiten"):
        zaehler = {}
        for kz, _typ, _ende, _fk in f["einheiten"]:
            zaehler[kz] = zaehler.get(kz, 0) + 1
        namen = {"aktien_verwaessert": "Aktienzahl", "eps_verwaessert": "Gewinn je Aktie", "nettogewinn": "Nettogewinn"}
        s.append("Einheitenfehler in den SEC-Meldungen berichtigt, etwa Aktien in Tausend statt Stück: "
                 + "; ".join(f"{namen.get(k, k)} in {_perioden(n)}" for k, n in zaehler.items()) + ".")
    if f.get("unstimmig"):
        s.append(f"Unstimmig: Bei {_perioden(int(f['unstimmig']))} passen Gewinn je Aktie, Aktienzahl und Nettogewinn "
                 f"nicht zusammen, zuletzt bis {datum_text(f.get('unstimmig_ende'))}; Kennzahlen daraus mit Vorsicht lesen.")
    return s


def bilanz_saetze(r):
    """Etappe 4, Punkte 2, 3, 4, 7, 8, 9 und 12: Renditen, Verschuldung,
    Cashflow, F-Score, Altman Z, Rule of 40, Banken und Immobilien."""
    f = (r or {}).get("fundament")
    if not f:
        return ["Keine erweiterten Kennzahlen aus dem SEC-Fundament für diese Aktie."]
    if f.get("fehler"):
        return [f"Erweiterte Kennzahlen aus dem SEC-Fundament nicht berechnet: {f['fehler']}."]
    wort = _geldwort(f)
    s = []
    teile = []
    if f.get("roe") is not None:
        teile.append(f"Eigenkapitalrendite {_pz(f['roe'])}")
    if f.get("roa") is not None:
        teile.append(f"Rendite auf das Vermögen {_pz(f['roa'])}")
    if f.get("roic") is not None:
        teile.append(f"Rendite auf das eingesetzte Kapital {_pz(f['roic'])}"
                     + (f" bei einem Steuersatz von {_pz(f['steuersatz'])}" if f.get("steuersatz") is not None else ""))
    if teile:
        s.append("Renditen mit dem Gewinn des Geschäftsjahres: " + "; ".join(teile) + ".")
    teile = []
    if f.get("lt_schulden_ek") is not None:
        teile.append(f"langfristige Schulden zum Eigenkapital {_q(f['lt_schulden_ek'])}")
    if f.get("schulden_ek") is not None:
        teile.append(f"alle Schulden zum Eigenkapital {_q(f['schulden_ek'])}")
    if f.get("nettoschulden") is not None:
        teile.append(f"Nettoschulden {_betrag(f['nettoschulden'], wort)}" if f["nettoschulden"] >= 0
                     else f"Nettokasse {_betrag(-f['nettoschulden'], wort)}")
    if f.get("current_ratio") is not None:
        teile.append(f"Current Ratio {_q(f['current_ratio'])}")
    if f.get("quick_ratio") is not None:
        teile.append(f"Quick Ratio {_q(f['quick_ratio'])}")
    if f.get("zinsdeckung") is not None:
        teile.append(f"Zinsdeckung {_q(f['zinsdeckung'], 1)} mal")
    if teile:
        s.append((f"Bilanz zum {datum_text(f['bilanz_ende'])}: " if f.get("bilanz_ende") else "Bilanz: ")
                 + "; ".join(teile) + ".")
    if f.get("umsatz_12m") is not None:
        s.append(f"{_begriff(r).rstrip(',')} der letzten zwölf Monate {_betrag(f['umsatz_12m'], wort)}"
                 + (", aus dem Geschäftsjahr, weil ein Quartal fehlt" if f.get("umsatz_12m_art") == "fy" else "") + ".")
    teile = []
    if f.get("fcf") is not None:
        teile.append(f"Free Cashflow {_betrag(f['fcf'], wort)}")
    if f.get("fcf_marge") is not None:
        teile.append(f"FCF-Marge {_pz(f['fcf_marge'])}")
    if f.get("cash_conversion") is not None:
        teile.append(f"Cash Conversion {_q(f['cash_conversion'])}, also operativer Cashflow durch Nettogewinn")
    if f.get("ausschuettung") is not None:
        teile.append(f"Ausschüttungsquote {_pz(f['ausschuettung'])}")
    if teile:
        zeit = (f"im Geschäftsjahr bis {datum_text(f.get('cashflow_ende'))}" if f.get("cashflow_art") == "fy"
                else f"über die vier Quartale bis {datum_text(f.get('cashflow_ende'))}")
        s.append(f"Cashflow {zeit}: " + "; ".join(teile) + ".")
    if f.get("finanz_grund"):
        s.append(f"{f['finanz_grund']}.")
    if f.get("fscore") is not None:
        try:
            import kennzahlen_fundament as kf
            texte = [kf.F_SIGNALE.get(c, c) for c in f.get("fscore_erfuellt") or []]
        except Exception:  # noqa
            texte = list(f.get("fscore_erfuellt") or [])
        s.append(f"Piotroski F-Score {int(f['fscore'])} von {int(f.get('fscore_bewertbar') or 0)} bewertbaren Signalen"
                 + ("; erfüllt: " + ", ".join(texte) if texte else "") + ".")
    elif f.get("fscore_grund"):
        s.append(f"Piotroski F-Score {f['fscore_grund']}.")
    if f.get("altman_z") is not None:
        z = float(f["altman_z"])
        zone = "sichere Zone über 2,99" if z > 2.99 else ("Grauzone von 1,81 bis 2,99" if z >= 1.81 else "Gefahrenzone unter 1,81")
        s.append(f"Altman Z {zahl(z, 2)}, {zone}.")
    elif f.get("altman_grund"):
        s.append(f"Altman Z {f['altman_grund']}.")
    if f.get("rule40") is not None:
        s.append(f"Rule of 40, gedacht für Software: Umsatzwachstum der vier Quartale {prozent(f.get('umsatz_12m_vj_pct'), 1)} "
                 f"plus FCF-Marge {_pz(f.get('fcf_marge'))} ergibt {zahl(f['rule40'], 1)}; ab 40 erfüllt.")
    teile = []
    if f.get("kernkapitalquote") is not None:
        teile.append(f"Kernkapitalquote {_pz(f['kernkapitalquote'])}")
    if f.get("risikovorsorge_kredite") is not None:
        teile.append(f"Risikovorsorge {_pz(f['risikovorsorge_kredite'], 2)} der Kredite")
    if f.get("einlagen_vj_pct") is not None:
        teile.append(f"Einlagen gegenüber dem Vorjahr {prozent(f['einlagen_vj_pct'], 1)}")
    if teile:
        s.append("Bank: " + "; ".join(teile) + ".")
    if f.get("ffo") is not None:
        s.append(f"FFO nach NAREIT über zwölf Monate {_betrag(f['ffo'], wort)}"
                 + (f"; je Aktie {zahl(f['ffo_je_aktie'], 2)} {wort}" if f.get("ffo_je_aktie") is not None else "")
                 + (f"; Kurs zu FFO {_q(f['p_ffo'], 1)}" if f.get("p_ffo") is not None else "") + ".")
    return s or ["Aus dem SEC-Fundament lassen sich für diese Aktie keine Bilanz- und Cashflow-Kennzahlen rechnen."]


def bewertung_saetze(r, streubesitz_kurs=None):
    """Etappe 4, Punkte 10 und 11: Bewertung mit dem Schlusskurs der Nacht
    und der Aktienzahl vom Deckblatt, dazu der Streubesitz. Mit dem Kurs am
    Stichtag des Streubesitzes (live von Yahoo) auch die Zahl der Aktien."""
    f = (r or {}).get("fundament")
    if not f:
        return ["Keine Bewertung: Für diese Aktie gibt es keine erweiterten Kennzahlen aus dem SEC-Fundament."]
    if f.get("fehler"):
        return [f"Keine Bewertung: {f['fehler']}."]
    s = []
    if f.get("bewertung_grund"):
        s.append(f"Bewertung mit dem Kurs nicht gerechnet: {f['bewertung_grund']}.")
    elif f.get("mk") is not None:
        s.append(f"Marktkapitalisierung {_betrag(f['mk'])} aus {zahl(f.get('aktien_ausstehend'))} Aktien vom Deckblatt, "
                 f"Stand {datum_text(f.get('aktien_stand'))}, mal dem Schlusskurs der Nacht.")
        teile = []
        teile.append(f"KGV {_q(f['kgv'], 1)}" if f.get("kgv") is not None
                     else "KGV nicht sinnvoll, der Nettogewinn der letzten zwölf Monate ist null oder negativ")
        if f.get("kuv") is not None:
            teile.append(f"KUV {_q(f['kuv'])}")
        if f.get("kbv") is not None:
            teile.append(f"KBV {_q(f['kbv'])}")
        s.append("; ".join(teile) + ".")
        teile = []
        if f.get("ev") is not None:
            teile.append(f"Enterprise Value {_betrag(f['ev'])}")
        if f.get("ev_ebitda") is not None:
            teile.append(f"EV zu EBITDA {_q(f['ev_ebitda'], 1)}")
        if f.get("ev_umsatz") is not None:
            teile.append(f"EV zu Umsatz {_q(f['ev_umsatz'])}")
        if teile:
            s.append("; ".join(teile) + ".")
        if f.get("peg") is not None:
            s.append(f"PEG {_q(f['peg'])} mit einem Wachstum des Gewinns je Aktie im letzten Geschäftsjahr von "
                     f"{prozent(f.get('peg_wachstum'), 1)}.")
        teile = [f"{name} {zahl(f[k], 2)} Dollar" for k, name in (
            ("cash_je_aktie", "Cash"), ("nettokasse_je_aktie", "Nettokasse"), ("buchwert_je_aktie", "Buchwert"),
            ("fcf_je_aktie", "Free Cashflow")) if f.get(k) is not None]
        if teile:
            s.append("Je Aktie: " + "; ".join(teile) + ".")
        teile = [f"{name} {_pz(f[k])}" for k, name in (
            ("div_rendite", "Dividendenrendite"), ("fcf_rendite", "FCF-Rendite"),
            ("rueckkauf_mk", "Aktienrückkäufe in Prozent der Marktkapitalisierung")) if f.get(k) is not None]
        if teile:
            s.append("; ".join(teile) + ".")
    if f.get("streubesitz_wert") is not None:
        wort = "Dollar" if f.get("streubesitz_waehrung") in (None, "USD") else str(f["streubesitz_waehrung"])
        satz = f"Streubesitz laut Deckblatt zum {datum_text(f.get('streubesitz_stichtag'))}: {_betrag(f['streubesitz_wert'], wort)}"
        if streubesitz_kurs and wort == "Dollar":
            satz += (f"; beim Schlusskurs von {zahl(streubesitz_kurs, 2)} Dollar an jenem Tag rund "
                     f"{zahl(f['streubesitz_wert'] / streubesitz_kurs)} Aktien in heutiger Stückelung")
        s.append(satz + ".")
    return s or ["Aus dem SEC-Fundament lässt sich für diese Aktie keine Bewertung rechnen."]


def streubesitz_stichtag(ratings, ticker):
    """Der Stichtag des Streubesitzes einer Aktie, wenn er in Dollar steht; sonst None."""
    f = (((ratings or {}).get("aktien") or {}).get(str(ticker or "").upper()) or {}).get("fundament") or {}
    if f.get("streubesitz_wert") is None or f.get("streubesitz_waehrung") not in (None, "USD"):
        return None
    return f.get("streubesitz_stichtag")


def kurs_am(ticker, stichtag, holen=None):
    """Der Schlusskurs am Stichtag oder am letzten Handelstag davor
    (hoechstens sieben Tage zurueck), von Yahoo. holen(ticker, datum)
    liefert im Selbsttest einen DataFrame mit Close und Datumsindex. Yahoo
    rechnet spaetere Splits in die Kurse ein; die Aktienzahl daraus steht
    deshalb in heutiger Stueckelung. None ohne Kurs."""
    from datetime import date, timedelta
    try:
        d = date.fromisoformat(str(stichtag)[:10])
    except ValueError:
        return None
    try:
        if holen is not None:
            df = holen(ticker, d)
        else:
            import yfinance as yf
            df = yf.Ticker(ticker).history(start=(d - timedelta(days=7)).isoformat(),
                                           end=(d + timedelta(days=1)).isoformat(), interval="1d", auto_adjust=False)
    except Exception:  # noqa
        return None
    if df is None or len(df) == 0:
        return None
    df = df.dropna(subset=["Close"])
    tage = [(x.date() if hasattr(x, "date") else x) for x in df.index]
    werte = [float(c) for t, c in zip(tage, df["Close"]) if t <= d]
    return werte[-1] if werte else None


# ---------------------------------------------------------------------------
# Etappe 5: Analysten und Konsens (Entscheidung 9)
# ---------------------------------------------------------------------------
# Gerhard, 13.09.2026: Forward-KGV und erwartetes Wachstum aus dem
# eingefrorenen Yahoo-Konsens, EPS-Konsens aus dem Nasdaq-Kalender,
# Revisionen und Einstufungen nur fuer die Wochenliste; reine Anzeige.
# Gerechnet in kennzahlen_konsens.py; die Werte liegen im privaten Datenrepo
# (scanner_analysten.parquet) und kommen nur ueber die App mit dem Lese-Token.

AKTION_TEXT = {"up": "hochgestuft", "down": "herabgestuft", "init": "Erstbewertung", "main": "Einstufung bestätigt",
               "reit": "Einstufung bekräftigt"}
MONATE_EN = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10,
             "nov": 11, "dec": 12}
PERIODE_BEZUG = {"0q": "dem Vorjahresquartal", "1q": "dem Vorjahresquartal", "0y": "dem Vorjahr",
                 "1y": "dem Geschäftsjahr davor"}


def _fehlt(x):
    """None, NaN, NA und leere Texte gelten als nicht vorhanden."""
    if x is None:
        return True
    if type(x).__name__ in ("NAType", "NaTType"):
        return True
    if isinstance(x, float) and x != x:
        return True
    return isinstance(x, str) and not x.strip()


def analysten_zeile(tabelle, ticker):
    """Die Zeile einer Aktie aus scanner_analysten.parquet als dict mit None
    statt NaN; None, wenn die Tabelle fehlt oder die Aktie nicht darin steht."""
    if tabelle is None:
        return None
    try:
        treffer = tabelle[tabelle["ticker"].astype(str).str.upper() == str(ticker or "").strip().upper()]
    except Exception:  # noqa
        return None
    if len(treffer) == 0:
        return None
    raus = {}
    for k, v in treffer.iloc[0].to_dict().items():
        if _fehlt(v):
            raus[k] = None
        else:
            raus[k] = v.item() if hasattr(v, "item") and not isinstance(v, str) else v
    return raus


def _wien_zeit(iso):
    """'2026-09-14T19:30:40Z' wird '14.09.2026 um 21:30 Uhr Wiener Zeit'."""
    try:
        from datetime import timezone
        from zoneinfo import ZoneInfo
        zeit = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if zeit.tzinfo is None:
            zeit = zeit.replace(tzinfo=timezone.utc)
        w = zeit.astimezone(ZoneInfo("Europe/Vienna"))
        return f"{w:%d.%m.%Y} um {w:%H:%M} Uhr Wiener Zeit"
    except Exception:  # noqa
        return datum_text(iso)


def quartal_text(q):
    """Nasdaqs 'Jun/2026' wird 'Juni 2026'."""
    m = re.fullmatch(r"([A-Za-z]{3})/(\d{4})", str(q or "").strip())
    if m and m.group(1).lower() in MONATE_EN:
        return f"{MONATE[MONATE_EN[m.group(1).lower()] - 1]} {m.group(2)}"
    return str(q) if q else "unbekannt"


def _geld(x, waehrung=None, stellen=2):
    if x is None:
        return "unbekannt"
    return f"{zahl(x, stellen)} {'Dollar' if waehrung in (None, 'USD') else waehrung}"


def _stueck(n, einzahl, mehrzahl):
    return f"1 {einzahl}" if int(n) == 1 else f"{int(n)} {mehrzahl}"


def _n_analysten(n):
    return "Zahl der Analysten unbekannt" if n is None else _stueck(n, "Analyst", "Analysten")


def _n_schaetzungen(n):
    if n is None:
        return "einer unbekannten Zahl von Schätzungen"
    return "einer Schätzung" if int(n) == 1 else f"{int(n)} Schätzungen"


def _periode_kopf(a, k):
    """Die Periode nach ihrem Ende: 'Quartal bis 31.08.2026'. Yahoos 'Current
    Qtr.' ist das Quartal der naechsten Meldung und kann schon vorbei sein
    (AutoZone am 14.09.2026: Quartal bis 31.08.2026, Meldung am 22.09.2026);
    'laufendes Quartal' waere dann falsch. Ohne Ende gilt Yahoos Name."""
    import kennzahlen_konsens as kk
    ende = a.get(f"konsens_ende_{k}")
    if ende:
        return f"{'Quartal' if k.endswith('q') else 'Geschäftsjahr'} bis {datum_text(ende)}"
    return kk.PERIODE_NAME[k] + " laut Yahoo"


def _konsens_perioden_saetze(a):
    import kennzahlen_konsens as kk
    wae = a.get("konsens_waehrung")
    s = []
    for _y, k in kk.PERIODEN:
        eps, ums = a.get(f"konsens_eps_{k}"), a.get(f"konsens_umsatz_{k}")
        if eps is None and ums is None:
            continue
        kopf = _periode_kopf(a, k)
        bezug = PERIODE_BEZUG[k]
        if eps is not None:
            satz = (f"{kopf}: Gewinn je Aktie erwartet {_geld(eps, wae)}")
            if a.get(f"konsens_eps_tief_{k}") is not None and a.get(f"konsens_eps_hoch_{k}") is not None:
                satz += f", Spanne {zahl(a[f'konsens_eps_tief_{k}'], 2)} bis {_geld(a[f'konsens_eps_hoch_{k}'], wae)}"
            satz += f", {_n_analysten(a.get(f'konsens_eps_analysten_{k}'))}"
            vj, pct = a.get(f"konsens_eps_vj_{k}"), a.get(f"konsens_eps_wachstum_{k}_pct")
            if vj is None:
                satz += "; der Vergleichswert fehlt im Einfrier-Lauf"
            elif pct is None:
                satz += f"; gegenüber {bezug} {_geld(vj, wae)} kein Prozentwert, der Vergleichswert ist null oder negativ"
            else:
                satz += f"; gegenüber {bezug} {_geld(vj, wae)} {prozent(pct, 1)}"
            s.append(satz + ".")
        if ums is not None:
            satz = f"{kopf}: Umsatz erwartet {_betrag(ums, 'Dollar' if wae in (None, 'USD') else wae)}"
            satz += f", {_n_analysten(a.get(f'konsens_umsatz_analysten_{k}'))}"
            vj, pct = a.get(f"konsens_umsatz_vj_{k}"), a.get(f"konsens_umsatz_wachstum_{k}_pct")
            if vj is None:
                satz += "; der Vergleichswert fehlt im Einfrier-Lauf"
            elif pct is None:
                satz += f"; gegenüber {bezug} kein Prozentwert, der Vergleichswert ist null"
            else:
                satz += (f"; gegenüber {bezug} {_betrag(vj, 'Dollar' if wae in (None, 'USD') else wae)} "
                         f"{prozent(pct, 1)}")
            s.append(satz + ".")
    return s


def _kgv_satz(a):
    wae = a.get("konsens_waehrung")
    if a.get("konsens_fwd_kgv") is not None:
        satz = (f"Forward-KGV {zahl(a['konsens_fwd_kgv'], 1)} mit dem Schlusskurs der Nacht und dem erwarteten Gewinn "
                f"je Aktie des nächsten Geschäftsjahres"
                + (f" bis {datum_text(a['konsens_ende_1y'])}" if a.get("konsens_ende_1y") else ""))
        if a.get("konsens_kgv_0y") is not None:
            satz += (f"; KGV {zahl(a['konsens_kgv_0y'], 1)} auf das Geschäftsjahr davor"
                     + (f" bis {datum_text(a['konsens_ende_0y'])}" if a.get("konsens_ende_0y") else ""))
        return satz + "."
    eps = a.get("konsens_eps_1y")
    if wae is None:
        return "Kein Forward-KGV: Yahoo nennt keine Währung des Konsens."
    if wae != "USD":
        return f"Kein Forward-KGV: Der Konsens steht in {wae}, der Kurs in Dollar."
    if eps is None:
        return "Kein Forward-KGV: Für das nächste Geschäftsjahr gibt es keinen Gewinnkonsens."
    if eps <= 0:
        return "Kein Forward-KGV: Der erwartete Gewinn je Aktie des nächsten Geschäftsjahres ist null oder negativ."
    return "Kein Forward-KGV: In der Nachttabelle fehlt der Schlusskurs."


def _stufe_satz(e):
    a = str(e.get("aktion") or "").lower()
    von, zu = e.get("von"), e.get("zu")
    if a in ("up", "down") and von and zu:
        text = f"{AKTION_TEXT[a]} von {von} auf {zu}"
    elif a == "init":
        text = f"Erstbewertung mit {zu}" if zu else "Erstbewertung"
    else:
        text = AKTION_TEXT.get(a, "Einstufung") + (f", {zu}" if zu else "")
    ziel, vorher = e.get("ziel"), e.get("ziel_vorher")
    za = str(e.get("ziel_aktion") or "").lower()
    if ziel:
        if za == "raises" and vorher:
            text += f"; Kursziel angehoben von {zahl(vorher, 2)} auf {zahl(ziel, 2)} Dollar"
        elif za == "lowers" and vorher:
            text += f"; Kursziel gesenkt von {zahl(vorher, 2)} auf {zahl(ziel, 2)} Dollar"
        elif za == "maintains":
            text += f"; Kursziel unverändert bei {zahl(ziel, 2)} Dollar"
        else:
            text += f"; Kursziel {zahl(ziel, 2)} Dollar"
    return f"{datum_text(e.get('datum'))}, {e.get('firma') or 'ohne Namen'}: {text}."


def _revisionen_saetze(a):
    import kennzahlen_konsens as kk
    wae = a.get("konsens_waehrung")
    s = [f"Revisionen und Einstufungen laut Yahoo, abgefragt am {datum_text(a.get('rev_stand'))}."]
    for _y, k in kk.PERIODEN:
        zaehler = [a.get(f"rev_{x}_{k}") for x in ("hoch_7t", "runter_7t", "hoch_30t", "runter_30t")]
        jetzt = a.get(f"rev_eps_jetzt_{k}")
        if all(x is None for x in zaehler) and jetzt is None:
            continue
        teile = []
        if any(x is not None for x in zaehler):
            h7, r7, h30, r30 = (0 if x is None else int(x) for x in zaehler)
            teile.append(f"in 7 Tagen {_stueck(h7, 'Anhebung', 'Anhebungen')} und "
                         f"{_stueck(r7, 'Senkung', 'Senkungen')} einzelner Schätzungen, in 30 Tagen "
                         f"{_stueck(h30, 'Anhebung', 'Anhebungen')} und {_stueck(r30, 'Senkung', 'Senkungen')}")
        if jetzt is not None:
            satz = f"Konsens heute {_geld(jetzt, wae)}"
            for tage in ("30", "90"):
                vor = a.get(f"rev_eps_{tage}t_{k}")
                if vor is not None:
                    pct = (jetzt / vor - 1.0) * 100.0 if vor > 0 else None
                    satz += f", vor {tage} Tagen {_geld(vor, wae)}" + (f", {prozent(pct, 1)} seither" if pct is not None else "")
            teile.append(satz)
        s.append(f"{_periode_kopf(a, k)}: " + "; ".join(teile) + ".")
    for n in kk.STUFEN_FENSTER:
        werte = [a.get(f"stufen_{x}_{n}t") for x in ("hoch", "runter", "neu", "ziel_rauf", "ziel_runter")]
        if any(w is None for w in werte):
            continue
        hoch, runter, neu, rauf, runter_z = (int(w) for w in werte)
        s.append(f"In {n} Tagen {_stueck(hoch, 'Heraufstufung', 'Heraufstufungen')}, "
                 f"{_stueck(runter, 'Herabstufung', 'Herabstufungen')} und "
                 f"{_stueck(neu, 'Erstbewertung', 'Erstbewertungen')}; "
                 f"Kursziel {rauf} mal angehoben und {runter_z} mal gesenkt.")
    try:
        liste = json.loads(a.get("stufen_liste") or "[]")
    except ValueError:
        liste = []
    if liste:
        s.append(f"Jüngste Einstufungen der letzten {max(kk.STUFEN_FENSTER)} Tage:")
        s.extend(_stufe_satz(e) for e in liste)
    elif a.get("stufen_liste") is not None:
        s.append(f"Keine Einstufungen in den letzten {max(kk.STUFEN_FENSTER)} Tagen.")
    return s


# S4 (Gerhard, 20.09.2026): Gaeste bekommen nichts aus dem privaten Datenrepo.
# Die App reicht diesen Grund weiter, die Kapitel sagen dann nur, dass es die
# Werte angemeldet gibt, ohne Secrets oder Repos zu nennen.
NUR_VOLLER_ZUGANG = "nur im vollen Zugang"


def konsens_saetze(a, in_wochenliste=False, grund=None):
    """Kapitel 'Analysten und Konsens'. a: die Zeile der Aktie aus
    scanner_analysten.parquet (analysten_zeile); grund: warum die
    Analystendaten fehlen, None heisst nicht uebergeben."""
    if a is None:
        if grund == NUR_VOLLER_ZUGANG:
            return ["Analysten und Konsens stehen nur im vollen Zugang."]
        if grund is None:
            return ["Analysten und Konsens liegen im privaten Datenrepo; sie stehen nur in der App mit dem "
                    "Token DATEN_TOKEN."]
        if grund:
            return [f"Analystendaten nicht geladen: {grund}. Sie liegen im privaten Datenrepo; die App braucht dafür "
                    "den Token DATEN_TOKEN in den Streamlit-Secrets."]
        return ["Für diese Aktie stehen in der Nachttabelle des Scanners keine Analystendaten."]
    s = []
    # Eingefrorener Yahoo-Konsens
    if a.get("konsens_stand"):
        wae = a.get("konsens_waehrung")
        s.append(f"Eingefrorener Konsens von Yahoo, Stand {_wien_zeit(a['konsens_stand'])}"
                 + (f", Beträge in {wae}" if wae and wae != "USD" else "") + ".")
        s.append(_kgv_satz(a))
        s.extend(_konsens_perioden_saetze(a))
        if a.get("konsens_termin"):
            s.append(f"Nächster Termin laut Yahoo {datum_text(a['konsens_termin'])}.")
    else:
        s.append("Kein eingefrorener Analystenkonsens von Yahoo für diese Aktie.")
    # Nasdaq-Kalender
    if a.get("termin_konsens_datum"):
        satz = (f"Laut Nasdaq-Kalender meldet die Firma am {datum_text(a['termin_konsens_datum'])}"
                + (f" das Quartal bis {quartal_text(a['termin_quartal'])}" if a.get("termin_quartal") else ""))
        if a.get("termin_eps_konsens") is not None:
            satz += (f"; erwartet {_geld(a['termin_eps_konsens'])} je Aktie aus "
                     f"{_n_schaetzungen(a.get('termin_eps_schaetzungen'))}")
        else:
            satz += "; ohne EPS-Konsens"
        if a.get("termin_eps_vorjahr") is not None:
            satz += f"; im Vorjahresquartal {_geld(a['termin_eps_vorjahr'])}"
            if a.get("termin_vorjahr_datum"):
                satz += f", gemeldet am {datum_text(a['termin_vorjahr_datum'])}"
        s.append(satz + ".")
    else:
        s.append("Im Nasdaq-Kalender der kommenden Tage steht kein Termin für diese Aktie.")
    # Empfehlungen, Kursziel und Ueberraschungen von Nasdaq
    if a.get("analysten_stand"):
        if a.get("analysten_anzahl"):
            s.append(f"Empfehlungen laut Nasdaq, abgefragt am {datum_text(a['analysten_stand'])}: "
                     f"{int(a.get('analysten_kaufen') or 0)} Kaufen, {int(a.get('analysten_halten') or 0)} Halten, "
                     f"{int(a.get('analysten_verkaufen') or 0)} Verkaufen"
                     + (f"; Konsens {a['konsens']}" if a.get("konsens") else "") + ".")
        else:
            s.append(f"Nasdaq nennt für diese Aktie keine Empfehlungen, abgefragt am {datum_text(a['analysten_stand'])}.")
        if a.get("kursziel") is not None:
            satz = f"Kursziel im Mittel {zahl(a['kursziel'], 2)} Dollar"
            if a.get("kursziel_tief") is not None and a.get("kursziel_hoch") is not None:
                satz += f", Spanne {zahl(a['kursziel_tief'], 2)} bis {zahl(a['kursziel_hoch'], 2)} Dollar"
            if a.get("kursziel_abst_pct") is not None:
                satz += f"; {prozent(a['kursziel_abst_pct'], 1)} gegenüber dem Schlusskurs der Nacht"
            s.append(satz + ".")
    else:
        s.append("Empfehlungen und Kursziel von Nasdaq für diese Aktie noch nicht abgefragt; jede Nacht kommt ein "
                 "Siebtel des Markts dran.")
    if a.get("quartale_mit_schaetzung"):
        satz = (f"Gewinnüberraschungen laut Nasdaq: in {int(a['quartale_mit_schaetzung'])} Quartalen mit Schätzung "
                f"{int(a.get('schaetzung_geschlagen') or 0)} mal geschlagen")
        if a.get("letzte_ueberraschung_pct") is not None:
            satz += f"; zuletzt {prozent(a['letzte_ueberraschung_pct'], 1)}"
            if a.get("letzter_bericht"):
                satz += f" bei der Meldung vom {datum_text(a['letzter_bericht'])}"
        s.append(satz + ".")
    # Revisionen und Einstufungen, nur Wochenliste
    if not in_wochenliste:
        s.append("Revisionen und Einstufungen gibt es nur für Aktien der Wochenliste.")
    elif not a.get("rev_stand"):
        s.append("Revisionen und Einstufungen für diese Aktie der Wochenliste sind noch nicht abgefragt; der nächste "
                 "Bau der Nachttabelle holt sie.")
    else:
        s.extend(_revisionen_saetze(a))
    s.append("Entscheidungshilfen, keine Filter.")
    return s


def short_saetze(a, grund=None):
    """Kapitel 'Leerverkäufe' (Etappe 7, Entscheidung 12): der Anteil der
    Leerverkäufe am außerbörslich gemeldeten Umsatz laut FINRA-Tagesdatei.
    a: die Zeile der Aktie aus scanner_analysten.parquet; grund wie bei
    konsens_saetze."""
    import kennzahlen_short as ks
    fenster = int(ks.KS["fenster_tage"])
    if a is None:
        if grund == NUR_VOLLER_ZUGANG:
            return ["Die Short-Daten stehen nur im vollen Zugang."]
        if grund is None:
            return ["Die Short-Daten liegen im privaten Datenrepo; sie stehen nur in der App mit dem Token "
                    "DATEN_TOKEN."]
        if grund:
            return [f"Short-Daten nicht geladen: {grund}."]
        return ["Für diese Aktie stehen in der Nachttabelle des Scanners keine Short-Daten."]
    if not a.get("short_stand"):
        hinweis = a.get("short_hinweis") or "ohne Angabe"
        return [f"Leerverkaufsvolumen laut FINRA nicht verfügbar: {hinweis}."]
    s = []
    if a.get("short_anteil_pct") is not None:
        s.append(f"Leerverkäufe laut FINRA am {datum_text(a['short_stand'])}: {zahl(a['short_anteil_pct'], 1)} Prozent "
                 f"der außerbörslich gemeldeten Umsätze, {zahl(a.get('short_volumen'))} von "
                 f"{zahl(a.get('short_gesamtvolumen'))} Aktien.")
    else:
        s.append(f"Am {datum_text(a['short_stand'])} meldete FINRA für diese Aktie keine außerbörslichen Umsätze.")
    if a.get("short_anteil_20t_pct") is not None:
        tage = a.get("short_tage_20t")
        s.append(f"Über die letzten {fenster} Handelstage {zahl(a['short_anteil_20t_pct'], 1)} Prozent, nach Volumen "
                 f"gewichtet"
                 + (f"; an {int(tage)} der {fenster} Tage außerbörslich gehandelt" if tage is not None else "") + ".")
    elif a.get("short_hinweis"):
        h = str(a["short_hinweis"])
        s.append(h[:1].upper() + h[1:] + ".")
    if a.get("short_median_pct") is not None:
        s.append(f"Zum Vergleich der Median aller Aktien des Universums an diesem Tag: "
                 f"{zahl(a['short_median_pct'], 1)} Prozent.")
    s.append("Die FINRA-Tagesdatei erfasst nur außerbörslich gemeldete Umsätze während der regulären Handelszeit, "
             "nicht die Börsen. Ein hoher Anteil ist üblich, weil Market Maker beim Handel leer verkaufen, und er ist "
             "kein Short Interest, also kein Bestand offener Leerverkaufspositionen.")
    s.append("Entscheidungshilfe, kein Filter.")
    return s


def gruppe_saetze(a, grund=None):
    """Kapitel 'Branchengruppe' (Etappe 6, Entscheidung 11): Gruppe und Rang
    der Industry Group RS. a: die Zeile der Aktie aus
    scanner_analysten.parquet; grund wie bei konsens_saetze."""
    import kennzahlen_gruppen as kg
    if a is None:
        if grund == NUR_VOLLER_ZUGANG:
            return ["Die Branchengruppe steht nur im vollen Zugang."]
        if grund is None:
            return ["Die Branchengruppe liegt im privaten Datenrepo; sie steht nur in der App mit dem Token "
                    "DATEN_TOKEN."]
        if grund:
            return [f"Branchengruppe nicht geladen: {grund}."]
        return ["Für diese Aktie steht in der Nachttabelle des Scanners keine Branchengruppe."]
    g = a.get("gruppe")
    hinweis = a.get("gruppe_hinweis")
    if not g:
        return [f"Branchengruppe nicht verfügbar: {hinweis or 'ohne Angabe'}."]

    def da(x):
        return x is not None and x == x

    # Gerhard, 15.09.2026, Nachfragen N8 und N9: jede Gruppe hat einen Rang,
    # auch eine mit einer einzigen Aktie und Branche unbekannt, und bei jedem
    # Rang steht fest, aus wie vielen Aktien er gerechnet ist.
    unbekannt = g == kg.UNBEKANNT
    s = [f"Branche unbekannt: {hinweis or 'ohne Angabe'}."] if unbekannt else []
    teile = [("Sammelgruppe Branche unbekannt, darin die Titel ohne Branche, vor allem Listungen nach dem Stichtag "
              "der Zuordnungsliste") if unbekannt else f"Branchengruppe laut {a.get('gruppe_ebene') or 'GICS-Unterbranche'}: {g}"]
    for spalte, spalte_n, wann in (("gruppe_rang", "gruppe_titel", ""), ("gruppe_rang_3w", "gruppe_titel_3w", "vor drei Wochen "),
                                   ("gruppe_rang_6w", "gruppe_titel_6w", "vor sechs Wochen ")):
        if not da(a.get(spalte)):
            continue
        teil = f"{wann}Rang {int(a[spalte])}"
        if not wann:
            teil += ((f" von {int(a['gruppen_zahl'])} Gruppen" if da(a.get("gruppen_zahl")) else "")
                     + f" am {datum_text(a.get('gruppe_stand'))}")
        if da(a.get(spalte_n)):
            n = int(a[spalte_n])
            teil += f", aus {n} {'Aktie' if n == 1 else 'Aktien'} gerechnet"
        teile.append(teil)
    s.append("; ".join(teile) + ".")
    s.append("Gerechnet wird mit den Aktien der Gruppe, die einen vollen RS-Rohwert haben; Rang 1 hat die Gruppe mit "
             "dem höchsten Median der RS-Rohwerte. Jede Gruppe bekommt einen Rang, auch eine mit einer einzigen Aktie; "
             "deshalb steht bei jedem Rang, aus wie vielen Aktien er gerechnet ist.")
    if hinweis and not unbekannt:
        h = str(hinweis)
        s.append(h[:1].upper() + h[1:] + ".")
    if a.get("gruppe_zuordnung_stand"):
        s.append(f"Die Gruppe stammt aus der eigenen Zuordnungsliste vom {datum_text(a['gruppe_zuordnung_stand'])}.")
    s.append("Entscheidungshilfe, kein Filter.")
    return s


def sektor_saetze(sektor_name, sektoren, quelle=""):
    if not sektor_name:
        return ["Sektor unbekannt: die Aktie steht in keiner Wochenliste, und Yahoo nennt keinen Sektor."]
    try:
        import beobachtungen
        etf = beobachtungen.sektor_etf_fuer(sektor_name)
    except Exception:  # noqa
        etf = None
    deutsch = SEKTOR_DEUTSCH.get(sektor_name, sektor_name)
    if not etf:
        return [f"Sektor {deutsch}; dafür führt unsere Rangliste keinen Sektor-ETF."]
    liste = (sektoren or {}).get("liste") or []
    z = next((x for x in liste if x.get("etf") == etf), None)
    if not z or not z.get("rang"):
        return [f"Sektor {deutsch}, ETF {etf}; die Sektor-Rangliste liegt noch nicht vor."]
    # 36 ETFs wie in sektor_rangliste.text_fuer; die Zahl der Liste nur, wenn sie vollstaendig ist
    n = len(liste) if len(liste) >= 30 else 36
    s = [f"Sektor {deutsch}, ETF {etf}: Rang {int(z['rang'])} von {n}"
         + (f", vor drei Wochen Rang {int(z['rang_vor_15t'])}" if z.get("rang_vor_15t") else "")
         + (f", vor sechs Wochen Rang {int(z['rang_vor_30t'])}" if z.get("rang_vor_30t") else "") + "."]
    if z.get("faber_pct") is not None:
        s.append(f"Faber-Mittel des ETF {prozent(z['faber_pct'], 1)}.")
    for m in (sektoren or {}).get("aufsteiger") or []:
        if m.get("etf") == etf:
            try:
                import sektor_rangliste
                s.append("Aufsteiger: " + sektor_rangliste.aufsteiger_text(m) + ".")
            except Exception:  # noqa
                s.append("Aufsteiger laut Sektor-Rangliste.")
    if quelle == "Yahoo":
        s.append("Sektor laut Yahoo, die Aktie steht in keiner Wochenliste.")
    return s


def stand_saetze(rs, ratings, sektoren):
    s = []
    if rs:
        s.append(f"Nachtwerte vom Handelstag {datum_text(rs.get('handelstag'))}, gebaut {str(rs.get('gebaut_am') or '')[:16].replace('T', ' um ')}"
                 + (f"; Bezug {rs.get('universum', {}).get('bezug_anzahl') or rs.get('universum', {}).get('im_universum')} Stammaktien des US-Markts" if rs.get("universum") else "") + ".")
        if rs.get("status") and rs.get("status") != "ok":
            s.append(f"RS-Status: {rs.get('status')}, {rs.get('grund')}.")
        ath = rs.get("allzeithoch") or {}
        if ath.get("voll_am"):
            s.append(f"Allzeithoch aus der ganzen Kurshistorie, zuletzt vollständig abgerufen am {datum_text(ath['voll_am'])}, "
                     f"dazwischen jede Nacht fortgeschrieben.")
    else:
        s.append("Keine Nachtwerte vorhanden; der nächste Nachtscan legt sie an.")
    if ratings and ratings.get("gebaut_am"):
        s.append(f"Ratings gebaut {str(ratings['gebaut_am'])[:16].replace('T', ' um ')}.")
    if sektoren and sektoren.get("handelstag"):
        s.append(f"Sektor-Rangliste vom Handelstag {datum_text(sektoren['handelstag'])}.")
    s.append("Kurs und Volumen live von Yahoo; RS gegen den ganzen US-Markt mit Kappung der Einzelrenditen bei plus 50 Prozent; "
             "Ratings als Näherung aus amtlichen SEC-Zahlen. Entscheidungshilfen, keine Filter.")
    return s


def bericht(ticker, rs, ratings, sektoren, live=None, kurve=None, kurve_quelle="", sektor_name=None, sektor_quelle="",
            streubesitz_kurs=None, analysten=None, analysten_grund=None):
    """Liste von (Ueberschrift, [Saetze]) fuer die Anzeige. streubesitz_kurs:
    der Schlusskurs am Stichtag des Streubesitzes (kurs_am), sonst None.
    analysten: die Zeile der Aktie aus scanner_analysten.parquet
    (analysten_zeile); analysten_grund: warum sie fehlt, None heisst nicht
    uebergeben."""
    t = str(ticker or "").upper()
    e = eintraege(rs).get(t, {})
    r = ((ratings or {}).get("aktien") or {}).get(t, {})
    in_wochenliste = t in ((rs or {}).get("listen") or {})
    return [("Aktie", kopf_saetze(t, e, live)),
            ("Unsere Ratings", ratings_saetze(e, r, ratings)),
            ("Volumen", volumen_saetze(live, kurve, kurve_quelle)),
            ("Technische Kennzahlen", technik_saetze(e)),
            ("Umsatz und Gewinn", wachstum_saetze(r)),
            ("Bilanz und Cashflow", bilanz_saetze(r)),
            ("Bewertung", bewertung_saetze(r, streubesitz_kurs)),
            ("Analysten und Konsens", konsens_saetze(analysten, in_wochenliste, analysten_grund)),
            ("Leerverkäufe", short_saetze(analysten, analysten_grund)),
            ("Branchengruppe", gruppe_saetze(analysten, analysten_grund)),
            ("Sektor", sektor_saetze(sektor_name, sektoren, sektor_quelle)),
            ("Stand", stand_saetze(rs, ratings, sektoren))]


def bericht_text(teile):
    zeilen = []
    for ueberschrift, saetze in teile:
        zeilen.append(ueberschrift)
        zeilen.extend(saetze)
        zeilen.append("")
    return "\n".join(zeilen).strip()


# ---------------------------------------------------------------------------
# Chartmuster, Kaufpunkte und Kerzen (Mathias, 14.09.2026)
# ---------------------------------------------------------------------------
# "Wenn man ins obere Feld eine Aktie reinschreibt, will ich, dass sie oben
# gleichzeitig durch die Muster gejagt wird, dass ganz unten die Kaufpunkte
# angezeigt werden, dass der Chart dort auch noch einmal vorhanden ist.
# Darunter gibt es den Aktienchart, wo man zwischen täglich, monatlich, Jahr
# umschalten kann." Die Saetze stehen hier, damit sie ohne Netz pruefbar
# sind; die App zeichnet nur die Charts.
#
# KEINE BILDZEICHEN (Mathias, 14.09.2026: "Entferne konsequent alle Emojis
# ... dies gilt für all unsere Tools"). Screenreader lesen jedes Symbol als
# Wort vor. Fremde Texte, etwa Status und Notizen der Detektoren oder eine
# aeltere Mappe, gehen deshalb vor der Anzeige durch lesbar().

BILDZEICHEN_BEREICHE = ((0x1F000, 0x1FAFF), (0x2600, 0x27BF), (0x2B00, 0x2BFF), (0x25A0, 0x25FF),
                        (0x2300, 0x23FF), (0xFE0E, 0xFE0F), (0x200D, 0x200D), (0x20E3, 0x20E3),
                        (0x2139, 0x2139), (0x3030, 0x3030), (0x303D, 0x303D), (0x3297, 0x3297),
                        (0x3299, 0x3299))
MONATE = ("Jänner", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September",
          "Oktober", "November", "Dezember")
WOCHENTAGE = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")


def ist_bildzeichen(zeichen):
    o = ord(zeichen)
    return any(a <= o <= b for a, b in BILDZEICHEN_BEREICHE)


def bildzeichen_in(text):
    """Die Bildzeichen eines Textes, in der Reihenfolge ihres Vorkommens."""
    return [z for z in str(text or "") if ist_bildzeichen(z)]


def lesbar(text):
    """Fremder Text fuer die Anzeige: ohne Bildzeichen, Gedankenstriche als
    Strichpunkt, Zahlenbereiche mit 'bis', Vergleichszeichen in Worten."""
    s = "".join(" " if ist_bildzeichen(z) else z for z in str(text or ""))
    s = re.sub(r"(\d)\s*[–—]\s*(\d)", r"\1 bis \2", s)
    s = re.sub(r"\s*[–—]\s*", "; ", s)
    s = re.sub(r"\s*·\s*", "; ", s)
    s = s.replace("≥", "mindestens ").replace("≤", "höchstens ").replace(">=", "mindestens ").replace("<=", "höchstens ")
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^[;,]\s*|\s*[;,]$", "", s)
    return s.replace(" ;", ";").replace(" ,", ",")


def chart_skript(key, text):
    """JavaScript, das den Chart-Behaelter mit dem Streamlit-Schluessel key zu
    EINEM Bild mit Beschreibung macht (role img, aria-label) und seinen Inhalt
    vor dem Screenreader verbirgt. Ein Chart ist sonst eine Folge aus
    Achsenzahlen, Monatsnamen und Legenden; was er zeigt, steht als Text
    daneben. Wartet mit einem MutationObserver hoechstens 30 Sekunden, bis
    der Chart im Browser steht.

    KEIN KLEINER-ZEICHEN (gemessen 14.09.2026): st.html reinigt das HTML mit
    DOMPurify, und ein Skript mit "i<c.children" kam nicht an; die Charts
    blieben unbeschriftet. Das Skript kommt deshalb ohne Vergleich mit
    Kleiner-Zeichen aus, und aus dem Text werden spitze Klammern entfernt."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", str(key or "")):
        raise ValueError("unerlaubter Schluessel")
    sauber = str(text or "").replace("<", " ").replace(">", " ")
    skript = ("(function(){var k=" + json.dumps(key) + ",t=" + json.dumps(sauber) + ";"
              "function f(){var c=document.querySelector('.st-key-'+k+' [data-testid=stPlotlyChart]');"
              "if(!c)return false;c.setAttribute('role','img');c.setAttribute('aria-label',t);"
              "Array.prototype.forEach.call(c.children,function(x){x.setAttribute('aria-hidden','true')});"
              "return true}"
              "if(!f()){var o=new MutationObserver(function(){if(f())o.disconnect()});"
              "o.observe(document.body,{childList:true,subtree:true});"
              "setTimeout(function(){o.disconnect()},30000)}})();")
    assert "<" not in skript
    return skript


def tt_kriterium_text(name, cfg=None):
    """Die Bedingungen des Trend Templates als deutscher Satzteil; die
    Schwellen kommen aus den Regelwerk-Werten des Scanners (pattern_scanner.CFG),
    nicht aus dem Namen der Bedingung."""
    if cfg is None:
        import pattern_scanner
        cfg = pattern_scanner.CFG
    tief = zahl(cfg["tt_min_above_low"] * 100)
    hoch = zahl(cfg["tt_max_below_high"] * 100)
    texte = {"Kurs > MA150 & MA200": "Kurs über dem 150- und dem 200-Tage-Durchschnitt",
             "MA150 > MA200": "150-Tage-Durchschnitt über dem 200-Tage-Durchschnitt",
             "MA200 steigt (≥1 Monat)": "200-Tage-Durchschnitt steigt seit mindestens einem Monat",
             "MA50 > MA150 & MA200": "50-Tage-Durchschnitt über dem 150- und dem 200-Tage-Durchschnitt",
             "Kurs > MA50": "Kurs über dem 50-Tage-Durchschnitt",
             "≥25 % über 52W-Tief": f"mindestens {tief} Prozent über dem 52-Wochen-Tief",
             "≤25 % unter 52W-Hoch": f"höchstens {hoch} Prozent unter dem 52-Wochen-Hoch",
             "RS-Rank ≥ 70": f"RS mindestens {zahl(cfg['tt_rs_min'])}",
             "Zu wenig Historie für MA200": "zu wenig Kurshistorie für den 200-Tage-Durchschnitt"}
    return texte.get(name, lesbar(name))


def rs_fuer_muster(e):
    """(RS-Wert, Satz) fuer die RS-Bedingung des Trend Templates im
    Nachschlagen: das marktweite RS, sonst das vorlaeufige, sonst keines."""
    e = e or {}
    if e.get("rs") is not None:
        return float(e["rs"]), f"Die RS-Bedingung ist mit RS {int(e['rs'])} gegen den ganzen US-Markt geprüft."
    if e.get("rs_vorlaeufig") is not None:
        return (float(e["rs_vorlaeufig"]),
                f"Die RS-Bedingung ist mit dem vorläufigen RS {int(e['rs_vorlaeufig'])} geprüft, "
                "gerechnet aus den vorhandenen Quartalen.")
    return None, "Ohne RS-Wert gilt die RS-Bedingung als nicht erfüllt."


def muster_saetze(res, rs_satz=None, cfg=None):
    """Chartmuster und Trend Template als Saetze."""
    if not res:
        return ["Keine Kursdaten für die Musterprüfung bekommen."]
    s = []
    echte = [p for p in res.get("points") or [] if not str(p.get("strategie", "")).startswith("Fallback")]
    anzahl = int(res.get("pattern_count") or len(echte))
    if echte:
        namen = ", ".join(anzeige_text(p["strategie"]) for p in echte)
        if anzahl == 1:
            s.append(f"Ein aktives Chartmuster: {namen}.")
        elif anzahl > len(echte):
            s.append(f"{anzahl} aktive Chartmuster; die {len(echte)} wichtigsten mit Kaufpunkt: {namen}.")
        else:
            s.append(f"{anzahl} aktive Chartmuster: {namen}.")
    else:
        s.append("Kein aktives Chartmuster. Die Kaufpunkte weiter unten sind allgemeine Orientierungsmarken, "
                 "keine Signale des Regelwerks.")
    n = int(res.get("tt_count") or 0)
    if res.get("tt_pass"):
        s.append("Trend Template nach Minervini erfüllt, 8 von 8 Bedingungen.")
    else:
        s.append(f"Trend Template nach Minervini nicht erfüllt, {n} von 8 Bedingungen.")
        fehlt = [tt_kriterium_text(f, cfg) for f in res.get("tt_failed") or []]
        if fehlt:
            s.append("Es fehlt: " + "; ".join(fehlt) + ".")
    if rs_satz:
        s.append(rs_satz)
    return s


def abgeschlossene_kerzen(df, jetzt=None):
    """Nur Tageskerzen abgeschlossener Handelstage: Solange in New York
    gehandelt wird, faellt die Kerze des laufenden Tages weg. Ein Inside Day
    oder ein Pocket Pivot steht erst mit dem Schluss fest; eine halbe Kerze
    wuerde ein Muster zeigen, das es am Abend vielleicht nicht gibt.
    jetzt: Zeitpunkt mit Zeitzone, fuer die Pruefung."""
    import pandas as pd
    from zoneinfo import ZoneInfo
    if df is None or len(df) == 0:
        return None
    d = df[["datetime", "open", "high", "low", "close", "volume"]].dropna(subset=["open", "high", "low", "close"])
    d = d.sort_values("datetime").reset_index(drop=True)
    if len(d) == 0:
        return None
    ny = (jetzt or datetime.now(ZoneInfo("UTC"))).astimezone(ZoneInfo("America/New_York"))
    letzter = pd.Timestamp(d["datetime"].iloc[-1]).date()
    if letzter >= ny.date() and (ny.hour, ny.minute) < (16, 0):
        d = d.iloc[:-1].reset_index(drop=True)
    return d


def chartmuster_saetze(df, jetzt=None):
    """Die Chartmuster aus Gerhards Papier vom 20.09.2026 (chartmuster.py) fuer
    eine Aktie, mit denselben Worten wie bei den Treffern des Scanners
    (scanner_ansicht.muster_saetze). Gerechnet wird am letzten abgeschlossenen
    Handelstag; der Satz nennt ihn. Nichts davon filtert."""
    import chartmuster
    import scanner_ansicht
    d = abgeschlossene_kerzen(df, jetzt)
    if d is None or len(d) < 4:
        return ["Ohne Kursdaten gibt es keine Chartmuster."]
    teile = scanner_ansicht.muster_saetze(chartmuster.werte(d))
    tag = datum_text(str(d["datetime"].iloc[-1])[:10])
    s = [f"Mit dem Schluss vom {tag}: " + ("; ".join(teile) if teile else "keines der Muster trifft zu") + "."]
    s.append("Die Muster sind Entscheidungshilfen und filtern nichts. Unsere eigenen Schwellen, wo Gerhards "
             "Quellen keine Zahl nennen, stehen im Reiter Regelwerk.")
    return s


# Kuerzel der Detektoren in Worten, damit ein Screenreader nicht "52 W" oder
# "M A 50" vorliest. Nur fuer die Anzeige; die Mappe behaelt ihre Namen.
_ANZEIGE_WOERTER = (("Fallback: ", "allgemeine Marke, "), ("52W-Hoch", "52-Wochen-Hoch"),
                    ("52W-Tief", "52-Wochen-Tief"), ("MA200", "200-Tage-Durchschnitt"),
                    ("MA150", "150-Tage-Durchschnitt"), ("MA50", "50-Tage-Durchschnitt"),
                    ("SMA21", "21-Tage-Durchschnitt"), ("SMA 21", "21-Tage-Durchschnitt"))


def anzeige_text(text):
    """lesbar() und dazu die Kuerzel der Detektoren in Worten und englische
    Dezimalpunkte als Beistrich (ein Datum wie 11.09.2026 bleibt)."""
    t = lesbar(text)
    for alt_wort, neues_wort in _ANZEIGE_WOERTER:
        t = t.replace(alt_wort, neues_wort)
    t = t.replace(" > ", " über ").replace(" < ", " unter ")
    return re.sub(r"(?<![\d.])(\d+)\.(\d{1,2})(?![\d.])", r"\1,\2", t)


def _satz(text):
    t = anzeige_text(text)
    return t[:-1] if t.endswith(".") else t


def kaufpunkt_saetze(res):
    """Je Kaufpunkt ein Satz: Preis, Abstand zum Kurs, Stop samt Risiko,
    Ziel samt Chance, Status und Notiz."""
    import exit_regeln
    if not res or not res.get("points"):
        return ["Keine Kaufpunkte berechnet."]
    kurs = res.get("close")
    s = []
    for i, p in enumerate(res["points"], 1):
        kp = p.get("kaufpunkt")
        teile = [f"Kaufpunkt {i}, {_satz(p.get('strategie'))}: {zahl(kp, 2)} Dollar"]
        if kp and kurs:
            abst = (float(kp) / float(kurs) - 1) * 100
            teile[0] += (f", {zahl(abst, 1)} Prozent über dem Kurs" if abst >= 0
                         else f", der Kurs liegt {zahl(-abst, 1)} Prozent darüber")
        risiko = None
        if p.get("stop") is not None:
            risiko = exit_regeln.risiko_pct(kp, p["stop"])
            teile.append(f"Stop {zahl(p['stop'], 2)} Dollar"
                         + (f", Risiko {zahl(abs(risiko), 1)} Prozent" if risiko is not None else ""))
        if p.get("ziel"):
            chance = (float(p["ziel"]) / float(kp) - 1) * 100
            ziel = f"Ziel {zahl(p['ziel'], 2)} Dollar, Chance {zahl(chance, 1)} Prozent"
            if risiko:
                ziel += f", Chance zu Risiko {zahl(chance / abs(risiko), 1)} zu 1"
            teile.append(ziel)
        for feld in ("status", "notiz"):
            if p.get(feld) and _satz(p[feld]):
                teile.append(_satz(p[feld]))
        s.append("; ".join(teile) + ".")
    s.append("Kaufpunkt heißt nicht Kaufsignal: Jeder Ausbruch braucht laut Regelwerk zusätzlich die "
             "Volumenbestätigung am Ausbruchstag.")
    return s


KERZEN_ARTEN = ("tag", "monat", "jahr")


def kerzen(df, art):
    """Kerzen fuer den Aktienchart. df hat die Spalten datetime, open, high,
    low, close, volume: Tageskerzen fuer art 'tag', Monatskerzen fuer
    'monat' und 'jahr' (Jahre werden aus den Monaten gebildet). Liefert
    einen DataFrame in derselben Form, aufsteigend nach Datum."""
    import pandas as pd
    if art not in KERZEN_ARTEN:
        raise ValueError("unbekannte Kerzenart")
    if df is None or len(df) == 0:
        return None
    d = df[["datetime", "open", "high", "low", "close", "volume"]].dropna(subset=["open", "high", "low", "close"])
    d = d.sort_values("datetime").reset_index(drop=True)
    if art != "jahr":
        return d
    jahre = d.groupby(pd.to_datetime(d["datetime"]).dt.year)
    j = pd.DataFrame({"open": jahre["open"].first(), "high": jahre["high"].max(), "low": jahre["low"].min(),
                      "close": jahre["close"].last(), "volume": jahre["volume"].sum()})
    j["datetime"] = pd.to_datetime([f"{y}-01-01" for y in j.index])
    return j.reset_index(drop=True)[["datetime", "open", "high", "low", "close", "volume"]]


def _kerzen_name(ts, art, heute=None):
    heute = heute or datetime.now().date()
    tag = ts.date() if hasattr(ts, "date") else ts
    if art == "tag":
        return f"{WOCHENTAGE[tag.weekday()]}, {tag:%d.%m.%Y}"
    if art == "monat":
        laufend = (tag.year, tag.month) == (heute.year, heute.month)
        return f"{MONATE[tag.month - 1]} {tag.year}" + (", bisher" if laufend else "")
    return f"Jahr {tag.year}" + (", bisher" if tag.year == heute.year else "")


def kerzen_saetze(k, art, anzahl=12, heute=None):
    """Die juengsten Kerzen als Saetze, die neueste zuerst."""
    if k is None or len(k) == 0:
        return ["Keine Kurse für diese Darstellung bekommen."]
    bezug = {"tag": "Vortag", "monat": "Vormonat", "jahr": "Vorjahr"}[art]
    s = []
    n = len(k)
    for i in range(n - 1, max(-1, n - 1 - anzahl), -1):
        z = k.iloc[i]
        satz = (f"{_kerzen_name(z['datetime'], art, heute)}: Eröffnung {zahl(z['open'], 2)}, Hoch {zahl(z['high'], 2)}, "
                f"Tief {zahl(z['low'], 2)}, Schluss {zahl(z['close'], 2)} Dollar")
        if i > 0 and k.iloc[i - 1]["close"]:
            satz += f"; {prozent((z['close'] / k.iloc[i - 1]['close'] - 1) * 100, 1)} gegenüber dem {bezug}"
        if z.get("volume") is not None and z["volume"] == z["volume"]:
            satz += f"; {zahl(z['volume'])} Stück"
        s.append(satz + ".")
    return s


# ---------------------------------------------------------------------------
# Selbsttest (ohne Netz)
# ---------------------------------------------------------------------------

def selbsttest() -> int:
    import pandas as pd
    from zoneinfo import ZoneInfo
    fehler = []

    def p(name, ok, zusatz=""):
        print(f"  {'ok  ' if ok else 'FEHL'} {name}" + (f" — {zusatz}" if zusatz else ""))
        if not ok:
            fehler.append(name)

    print("Nachschlagen, Selbsttest (ohne Netz)")
    p("Zahlen deutsch: Tausenderpunkt, Dezimalbeistrich, unbekannt bei None",
      zahl(1234567) == "1.234.567" and zahl(12.345, 2) == "12,35" and zahl(None) == "unbekannt"
      and zahl(-0.2, 2) == "minus 0,20" and zahl(-0.001, 2) == "0,00")
    p("Prozent in Worten, nie mit Vorzeichen",
      prozent(12.34, 1) == "plus 12,3 Prozent" and prozent(-4) == "minus 4 Prozent" and prozent(None) == "nicht berechenbar")
    p("Datum und Firmenname", datum_text("2026-06-30") == "30.06.2026" and firmenname("Apple Inc. - Common Stock") == "Apple Inc.")

    rs = {"handelstag": "2026-09-11", "gebaut_am": "2026-09-13T00:04:45", "status": "ok",
          "universum": {"bezug_anzahl": 5339, "im_universum": 2017},
          "allzeithoch": {"voll_am": "2026-09-07"},
          "aktien": {"AAOI": {"name": "Applied Optoelectronics, Inc. - Common Stock", "boerse": "Nasdaq", "kurs": 105.36,
                              "pct": 5.2, "rs": 58, "abst_52w_hoch_pct": -54.9, "kurs_52w_hoch": False, "letzter_tag": "2026-09-11",
                              "rs_verlauf": [["2026-08-12", 51], ["2026-09-04", 56], ["2026-09-11", 58]],
                              "linie_spy_hoch": False, "linie_qqq_hoch": False,
                              "technik": {"perf_1w": 2.1, "perf_1m": -3.4, "perf_3m": 12.0, "perf_6m": None, "perf_12m": 150.2,
                                          "perf_ytd": 44.4, "ath": 233.63, "ath_datum": "2021-03", "ath_abst": -54.9,
                                          "sma20_abst": 1.2, "sma50_abst": -3.4, "sma200_abst": 12.0, "hoch50_abst": -4.0,
                                          "tief50_abst": 12.3, "tief52_abst": 80.1, "vola5": 5.12, "vola21": 4.5,
                                          "adr20": 4.31, "atr14": 4.21,
                                          "ud50": 1.34, "mrs": 12.3, "mrs_vorher": 8.1, "stufe": 2, "linie_abst": 5.2,
                                          "linie_steig": 2.13, "burst": True, "schlusslage": 85, "vortag_pct": -0.8,
                                          "vortag_spanne": 2.1, "luecke": 11.0, "seit_eroeffnung": -0.5, "vol_faktor": 4.2,
                                          "pivot": True, "beta": 1.35, "rsi14": 62.5, "rsi2": 91.0, "vol63": 1234567,
                                          "dv20": 45600000, "rs_1w": 2, "rs_4w": 7}},
                     "AAPL": {"name": "Apple Inc. - Common Stock", "boerse": "Nasdaq", "kurs": 230.0, "pct": -0.5, "rs": 70,
                              "letzter_tag": "2026-09-11"}},
          "ausserhalb": {"BILLG": {"name": "Billig Corp. - Common Stock", "boerse": "NYSE American", "kurs": 3.0, "rs": 12,
                                   "grund": "Kurs unter 15 Dollar"},
                         "APPLD": {"name": "Applied Digital Corporation - Common Stock", "boerse": "Nasdaq", "kurs": 9.0, "rs": 40,
                                   "grund": "Kurs unter 15 Dollar"},
                         "JUNGX": {"name": "Jungfirma Holdings - Common Stock", "boerse": "Nasdaq", "kurs": 40.0, "tage": 150,
                                   "roh": None, "roh_vorlaeufig": 0.31, "rs_quartale": 2, "rs_vorlaeufig": 91,
                                   "grund": "zu kurze Historie (150 Tage)"}},
          "listen": {"AAOI": {"firma": "Applied Optoelectronics", "rs": 58, "im_universum": True}}}
    p("Suche: Kuerzel direkt, Klassen-Schreibweise, Name eindeutig, Name mehrdeutig, unbekanntes Kuerzel",
      finde("aaoi", rs) == ("AAOI", []) and finde("billg", rs)[0] == "BILLG"
      and finde("Billig", rs) == ("BILLG", []) and finde("Applied", rs)[0] is None and len(finde("Applied", rs)[1]) == 2
      and finde("XYZQ", rs) == ("XYZQ", []) and finde("", rs) == (None, []), finde("Applied", rs))
    p("Suche: Kandidaten mit Kuerzel und gekuerztem Namen, passender Anfang zuerst",
      finde("Applied", rs)[1][0] == ("APPLD", "Applied Digital Corporation") or finde("Applied", rs)[1][0][0] in ("AAOI", "APPLD"),
      finde("Applied", rs)[1])

    ratings = {"status": "ok", "gebaut_am": "2026-09-13T00:10:00",
               "aktien": {"AAOI": {"eps": 87, "smr": "B", "smr_rang": 65, "ad": "C", "ad_rang": 48, "composite": 91,
                                   "composite_fehlt": [], "basis": "amtlich", "quartale": 8, "ifrs": False, "vermerke": [],
                                   "umsatz_juengst": 1234567890.0, "umsatz_vorquartal": 1190000000.0, "umsatz_vorjahr": 987654321.0,
                                   "umsatz_ende": "2026-06-30", "umsatz_wachstum_vj_pct": 25.0, "umsatz_wachstum_vq_pct": 3.7,
                                   "eps_juengst": 1.23, "eps_vorquartal": 1.15, "eps_vorjahr": -0.2, "eps_ende": "2026-06-30",
                                   "eps_wachstum_vj_pct": None, "eps_wachstum_vq_pct": 7.0,
                                   "smr_bausteine": {"umsatz": [0.2136, 81], "marge": [0.085, 60], "vorsteuer": [-0.012, 22],
                                                     "roe": [0.18, 66]},
                                   "canslim": {"eps_q": [None, None], "eps_cagr3": [True, 31.5], "roe": [True, 18.0]},
                                   "fundament": {
                                       "waehrung": "USD", "marge_brutto_q": 0.305, "marge_operativ_q": 0.061,
                                       "marge_vorsteuer_q": 0.058, "marge_netto_q": -0.021, "marge_ende_q": "2026-06-30",
                                       "marge_brutto_fy": 0.29, "marge_ende_fy": "2025-12-31",
                                       "umsatz_vj": [["2026-06-30", 25.0], ["2026-03-31", None]],
                                       "eps_vj": [["2026-06-30", None]], "umsatz_trend": "beschleunigt",
                                       "umsatz_cagr3": 18.2, "umsatz_cagr5": 9.0, "eps_cagr3": 31.5,
                                       "eps_stabilitaet": 42, "stabilitaet_quartale": 15,
                                       "aktien_1j_pct": 12.5, "aktien_3j_pct": 40.1, "aktien_ende": "2026-06-30",
                                       "sbc_umsatz": 0.034,
                                       "roe": 0.18, "roa": 0.071, "roic": 0.093, "steuersatz": 0.21, "bilanz_ende": "2026-06-30",
                                       "lt_schulden_ek": 0.45, "schulden_ek": 0.6, "nettoschulden": -120000000,
                                       "current_ratio": 1.8, "quick_ratio": 1.2, "zinsdeckung": 12.34,
                                       "umsatz_12m": 4567000000, "umsatz_12m_art": "4q",
                                       "fcf": 150000000, "fcf_marge": 0.0328, "cash_conversion": 1.42, "ausschuettung": 0.0,
                                       "cashflow_ende": "2026-06-30", "cashflow_art": "4q",
                                       "fscore": 6, "fscore_bewertbar": 8, "fscore_erfuellt": ["roa", "cfo", "cfo_ng"],
                                       "altman_z": 2.5, "rule40": 28.3, "umsatz_12m_vj_pct": 25.0,
                                       "aktien_ausstehend": 62000000, "aktien_stand": "2026-08-01", "mk": 6532320000,
                                       "kgv": 88.4, "kuv": 1.43, "kbv": 5.2, "ev": 6412320000, "ev_ebitda": 30.12,
                                       "ev_umsatz": 1.4, "cash_je_aktie": 3.1, "nettokasse_je_aktie": 1.94,
                                       "buchwert_je_aktie": 20.26, "fcf_je_aktie": 2.42, "fcf_rendite": 0.023,
                                       "streubesitz_wert": 3100000000, "streubesitz_stichtag": "2025-06-30",
                                       "streubesitz_waehrung": "USD",
                                       "splits": [[4, "2026-08-27"], [0.1, "2021-05-10"]],
                                       "einheiten": [["aktien_verwaessert", "FY", "2021-12-31", 1000.0],
                                                     ["aktien_verwaessert", "FY", "2022-12-31", 1000.0],
                                                     ["eps_verwaessert", "Q", "2022-07-30", 0.01]],
                                       "unstimmig": 1, "unstimmig_ende": "2023-06-30"}},
                          "AAPL": {"eps": 60, "smr": None, "smr_rang": None, "ad": None, "ad_rang": None, "composite": None,
                                   "composite_fehlt": ["SMR", "A/D"], "basis": "amtlich", "quartale": 8, "ifrs": True,
                                   "vermerke": ["IFRS-Zahlen, ungeprueft (Antwort 8)", "Bank: Nettoertraege (Zinsueberschuss plus Provisionsertrag) statt Umsatz"],
                                   "umsatz_juengst": 500.0, "umsatz_vorquartal": None, "umsatz_vorjahr": 400.0, "umsatz_ende": "2026-06-30",
                                   "umsatz_wachstum_vj_pct": 25.0, "umsatz_wachstum_vq_pct": None, "eps_juengst": None}}}
    sektoren = {"handelstag": "2026-09-11", "liste": [{"etf": "XLK", "name": "Technology", "rang": 3, "rang_vor_15t": 7, "faber_pct": 4.5},
                                                     {"etf": "XLF", "name": "Financials", "rang": 20}],
                "aufsteiger": [{"etf": "XLK", "name": "Technology", "art": "eintritt", "rang": 3, "rang_vor_3w": 7}]}
    ny = ZoneInfo("America/New_York")
    tage = pd.bdate_range(end="2026-09-11", periods=60)
    df = pd.DataFrame({"Close": [100.0 + i for i in range(60)], "Volume": [1_000_000.0] * 59 + [600_000.0]}, index=tage)
    df_heute = pd.concat([df.assign(Volume=1_000_000.0),
                          pd.DataFrame({"Close": [160.0], "Volume": [600_000.0]}, index=pd.DatetimeIndex(["2026-09-14"]))])
    live_zu = live_daten("AAOI", jetzt=datetime(2026, 9, 12, 18, 0, tzinfo=ny), holen=lambda t: df)
    p("Live nach Schluss: letzter Handelstag, Volumen des Tages, 50-Tage-Schnitt aus den Tagen davor",
      live_zu and not live_zu["handel_laeuft"] and live_zu["v_bisher"] == 600000 and abs(live_zu["v50"] - 1_000_000) < 1
      and live_zu["tag"] == "2026-09-11", live_zu)
    live_auf = live_daten("AAOI", jetzt=datetime(2026, 9, 14, 10, 0, tzinfo=ny), holen=lambda t: df_heute)
    p("Live im Handel: Minute seit Eroeffnung, heutiges Volumen bisher",
      live_auf and live_auf["handel_laeuft"] and live_auf["minute"] == 30 and live_auf["v_bisher"] == 600000, live_auf)
    live_vor = live_daten("AAOI", jetzt=datetime(2026, 9, 14, 8, 0, tzinfo=ny), holen=lambda t: df_heute)
    p("Live vorboerslich: die leere Zeile von heute faellt weg, es gilt der Vortag",
      live_vor and not live_vor["handel_laeuft"] and live_vor["tag"] == "2026-09-11", live_vor)
    kurve = {0: 0.05, 30: 0.25, 60: 0.35, 390: 1.0}
    v_auf = volumen_saetze(live_auf, kurve, "Vorrat")
    p("Volumen im Handel: Stueck, Minuten, hochgerechnet; 600.000 in 30 Minuten bei Anteil 0,25 gegen 1 Million heisst plus 140 Prozent",
      v_auf[0].startswith("Bisher gehandelt: 600.000 Stück, 30 Minuten") and "plus 140 Prozent" in v_auf[1] and "Vorrat" in v_auf[1], v_auf)
    v_ohne = volumen_saetze(live_auf, None, "keine")
    p("Volumen im Handel ohne Kurve: nicht verifizierbar, nie eine Ersatzrechnung", "nicht verifizierbar" in v_ohne[1] and "Volumenkurve" in v_ohne[1], v_ohne)
    v_zu = volumen_saetze(live_zu, None)
    p("Volumen nach Schluss: Tagesformel, minus 40 Prozent", "Letzter Handelstag 11.09.2026: 600.000 Stück" in v_zu[0] and "minus 40 Prozent" in v_zu[1], v_zu)

    teile = bericht("AAOI", rs, ratings, sektoren, live=live_auf, kurve=kurve, kurve_quelle="Vorrat", sektor_name="Technology", sektor_quelle="Wochenliste")
    text = bericht_text(teile)
    p("Bericht hat zwoelf Teile in fester Reihenfolge",
      [u for u, _ in teile] == ["Aktie", "Unsere Ratings", "Volumen", "Technische Kennzahlen", "Umsatz und Gewinn",
                                "Bilanz und Cashflow", "Bewertung", "Analysten und Konsens", "Leerverkäufe",
                                "Branchengruppe", "Sektor", "Stand"])
    p("Kopf: Kuerzel, Name, Boerse, Kurs live, Abstand zum Hoch",
      "AAOI, Applied Optoelectronics, Inc., Nasdaq." in text and "Kurs 160,00 Dollar" in text and "Abstand zum 52-Wochen-Hoch minus 54,9 Prozent" in text)
    p("Ratings: RS mit Vorwoche, EPS, SMR, A/D, Composite je ein Satz",
      "RS 58; vor einer Woche 56, Änderung plus 2; vor vier Wochen 51, Änderung plus 7." in text and "EPS-Rating 87." in text
      and "SMR-Note B, Rang 65." in text
      and "A/D-Note C, Rang 48, Näherung aus der Schlusslage in der Tagesspanne und dem Volumen." in text and "Composite 91." in text and "Basis amtlich, 8 Quartale." in text, text)
    p("Wachstum: Prozent zuerst, dann vorher und jetzt in ganzen Zahlen, Quartalsende; EPS-Vorjahr im Minus ohne Prozentwert",
      "Umsatz Wachstum gegenüber dem Vorjahresquartal: plus 25,0 Prozent; vorher 987.654.321 Dollar, jetzt 1.234.567.890 Dollar." in text
      and "gegenüber dem Vorquartal: plus 3,7 Prozent; vorher 1.190.000.000 Dollar" in text
      and "Jüngstes Quartal bis 30.06.2026." in text
      and "Gewinn je Aktie, Wachstum gegenüber dem Vorjahresquartal: kein Prozentwert" in text
      and "vorher minus 0,20 Dollar, jetzt 1,23 Dollar" in text, text)
    p("Sektor: deutscher Name, ETF, Rang von 36, vor drei Wochen, Aufsteiger",
      "Sektor Technologie, ETF XLK: Rang 3 von 36, vor drei Wochen Rang 7." in text and "Aufsteiger: Technology (XLK) neu unter den ersten fünf" in text, text)
    p("Stand: Handelstag, Bezug, Allzeithoch-Abruf, Ratings-Stand, Sektor-Stand",
      "Nachtwerte vom Handelstag 11.09.2026" in text and "Bezug 5339" in text
      and "zuletzt vollständig abgerufen am 07.09.2026" in text
      and "Ratings gebaut 2026-09-13 um 00:10" in text and "Sektor-Rangliste vom Handelstag 11.09.2026" in text)
    ts = dict(teile)["Technische Kennzahlen"]
    erwartet_ts = [
        "Wertentwicklung: eine Woche plus 2,1 Prozent; ein Monat minus 3,4 Prozent; drei Monate plus 12,0 Prozent; "
        "zwölf Monate plus 150,2 Prozent; seit Jahresbeginn plus 44,4 Prozent.",
        "Allzeithoch 233,63 Dollar im März 2021; Abstand minus 54,9 Prozent.",
        "Abstand zu den gleitenden Durchschnitten: SMA 20 plus 1,2 Prozent; SMA 50 minus 3,4 Prozent; SMA 200 plus 12,0 Prozent.",
        "Abstand zum 50-Tage-Hoch minus 4,0 Prozent; zum 50-Tage-Tief plus 12,3 Prozent; zum 52-Wochen-Tief plus 80,1 Prozent.",
        "ADR nach Qullamaggie, die mittlere Tagesspanne über 20 Tage: 4,31 Prozent.",
        "Volatilität wie bei Finviz, dieselbe Spanne über 5 und 21 Tage: Woche 5,12 Prozent; Monat 4,50 Prozent.",
        "ATR 14 nach Wilder: 4,21 Dollar, das sind 4,0 Prozent des Kurses.",
        "Up/Down-Volumen über 50 Tage: 1,34; über 1 überwiegt das Volumen an Plus-Tagen.",
        "Mansfield RS gegen SPY: plus 12,3, vor vier Wochen plus 8,1, also steigend.",
        "Weinstein-Stufe 2: Kurs 5,2 Prozent über der 30-Wochen-Linie, die Linie steigt in vier Wochen um 2,1 Prozent, "
        "die letzten zwei Wochenschlüsse liegen über der Linie.",
        "Momentum Burst nach Stockbee am letzten Handelstag: plus 5,2 Prozent bei höherem Volumen als am Vortag; "
        "Schluss bei 85 Prozent der Tagesspanne; Vortag minus 0,8 Prozent bei 2,1 Prozent Spanne.",
        "Am letzten Handelstag: Eröffnungslücke plus 11,0 Prozent; seit Eröffnung minus 0,5 Prozent; "
        "Volumen 4,2 mal so hoch wie der 50-Tage-Schnitt.",
        "Episodic Pivot: Die Eröffnungslücke liegt bei 10 Prozent oder mehr.",
        "Beta gegen SPY über 252 Handelstage: 1,35.",
        "RSI 14 bei 62,5; RSI 2 bei 91,0.",
        "Durchschnittsvolumen über drei Monate 1.234.567 Stück je Tag; Dollarvolumen über 20 Tage 45,6 Millionen Dollar je Tag.",
        "Reine Anzeige: Keine dieser Kennzahlen filtert."]
    p("Technische Kennzahlen (Etappe 2): je Kennzahl ein Satz, deutsche Zahlen, fehlende Werte ausgelassen",
      ts == erwartet_ts, [x for x in ts if x not in erwartet_ts] or ts)
    tk_ohne = {"stufe": 0, "linie_abst": -3.4, "linie_steig": 2.1, "burst": False, "ath": 50.0, "ath_datum": "2026-09-11",
               "mrs": -1.0, "mrs_vorher": None}
    ts2 = technik_saetze({"technik": tk_ohne, "letzter_tag": "2026-09-11", "kurs": 50.0})
    p("Technische Kennzahlen: Allzeithoch heute, Stufe nicht eindeutig, kein Burst, fehlende Werte ehrlich",
      "Die Aktie steht auf ihrem Allzeithoch von 50,00 Dollar." in ts2
      and "Weinstein-Stufe nicht eindeutig: Kurs 3,4 Prozent unter der 30-Wochen-Linie, die Linie steigt in vier Wochen um 2,1 Prozent." in ts2
      and "Kein Momentum Burst nach Stockbee am letzten Handelstag." in ts2 and "Mansfield RS gegen SPY: minus 1,0." in ts2
      and "Beta nicht berechenbar, dafür braucht es 252 Tagesrenditen gemeinsam mit dem Index." in ts2
      and "Wertentwicklung: nicht berechenbar." in ts2 and not any("Episodic Pivot" in x for x in ts2), ts2)
    p("Technische Kennzahlen bei Split-Verdacht: nur der Hinweis, keine Kennzahl",
      technik_saetze({"technik": {"split_verdacht": 13.29}})[0].startswith(
          "Technische Kennzahlen heute nicht verfügbar: Der Schlusskurs springt am letzten Handelstag auf das 13,3-fache")
      and len(technik_saetze({"technik": {"split_verdacht": 13.29}})) == 1
      and "fällt am letzten Handelstag auf 7,7 Prozent des Vortags" in technik_saetze({"technik": {"split_verdacht": 0.0769}})[0],
      technik_saetze({"technik": {"split_verdacht": 0.0769}}))
    p("Technische Kennzahlen ohne Werte: ein ehrlicher Satz; Monat in Worten",
      technik_saetze({}) == ["Keine technischen Kennzahlen: Die Aktie steht in keiner Nachtdatei, oder es gab für sie keine Kurse."]
      and monat_text("2021-03") == "März 2021" and monat_text("2021-13") == "2021-13"
      and weinstein_satz({"stufe": 3, "linie_abst": 1.0, "linie_steig": 0.2}).startswith("Weinstein-Stufe 3: 30-Wochen-Linie flach nach einem Anstieg")
      and weinstein_satz({"stufe": None, "linie_abst": None, "linie_steig": None}).startswith("Weinstein-Stufe nicht berechenbar"))
    p("Kein Gedankenstrich, kein senkrechter Strich, keine Tabelle", "–" not in text and "|" not in text and "—" not in text)
    p("Etappe 4: SMR-Bausteine mit Rohwert und Rang, Wachstum mit Vorzeichen, Margen ohne",
      "SMR-Bausteine: Umsatzwachstum der drei jüngsten Quartale gegen das Vorjahr plus 21,4 Prozent, Rang 81; "
      "Nettomarge des jüngsten Quartals 8,5 Prozent, Rang 60; Vorsteuermarge des Geschäftsjahres minus 1,2 Prozent, Rang 22; "
      "Eigenkapitalrendite 18,0 Prozent, Rang 66." in text, text)
    ug = dict(teile)["Umsatz und Gewinn"]
    erwartet_ug = [
        "Margen im Quartal bis 30.06.2026: brutto 30,5 Prozent; operativ 6,1 Prozent; vor Steuern 5,8 Prozent; netto minus 2,1 Prozent.",
        "Margen im Geschäftsjahr bis 31.12.2025: brutto 29,0 Prozent.",
        "Umsatz gegenüber dem Vorjahresquartal, jüngstes zuerst: bis 30.06.2026 plus 25,0 Prozent; bis 31.03.2026 nicht berechenbar.",
        "Gewinn je Aktie gegenüber dem Vorjahresquartal, jüngstes zuerst: bis 30.06.2026 nicht berechenbar.",
        "Umsatz, Wachstum über die drei jüngsten Quartale: beschleunigt.",
        "Jährliches Wachstum im Schnitt: Umsatz über drei Jahre plus 18,2 Prozent; über fünf Jahre plus 9,0 Prozent; "
        "Gewinn je Aktie über drei Jahre plus 31,5 Prozent.",
        "EPS-Stabilität 42 über 15 Quartale, Näherung nach IBD-Art: 1 heißt gleichmäßig, 99 sprunghaft.",
        "Verwässerte Aktienzahl gegenüber einem Jahr zuvor plus 12,5 Prozent, gegenüber drei Jahren zuvor plus 40,1 Prozent, "
        "Stand 30.06.2026.",
        "Aktienbasierte Vergütung 3,4 Prozent des Umsatzes.",
        "CAN-SLIM-Häkchen, kein Filter: Quartals-EPS gegenüber dem Vorjahr ab 25 Prozent offen, nicht berechenbar; "
        "Dreijahres-CAGR des Gewinns je Aktie ab 25 Prozent erfüllt mit plus 31,5 Prozent; "
        "Eigenkapitalrendite ab 17 Prozent erfüllt mit 18,0 Prozent.",
        "Eingerechnet: Split 4 zu 1, Umrechnung ab 27.08.2026; Reverse-Split 1 zu 10, Umrechnung ab 10.05.2021.",
        "Einheitenfehler in den SEC-Meldungen berichtigt, etwa Aktien in Tausend statt Stück: Aktienzahl in 2 Perioden; "
        "Gewinn je Aktie in 1 Periode.",
        "Unstimmig: Bei 1 Periode passen Gewinn je Aktie, Aktienzahl und Nettogewinn nicht zusammen, zuletzt bis 30.06.2023; "
        "Kennzahlen daraus mit Vorsicht lesen."]
    p("Etappe 4: Umsatz und Gewinn um Margen, acht Quartale, Trend, CAGR, Stabilitaet, Verwaesserung, CAN-SLIM, Splits und "
      "Einheiten erweitert",
      ug[-len(erwartet_ug):] == erwartet_ug, [x for x in ug if x not in erwartet_ug][-15:] or ug)
    bz = dict(teile)["Bilanz und Cashflow"]
    erwartet_bz = [
        "Renditen mit dem Gewinn des Geschäftsjahres: Eigenkapitalrendite 18,0 Prozent; Rendite auf das Vermögen 7,1 Prozent; "
        "Rendite auf das eingesetzte Kapital 9,3 Prozent bei einem Steuersatz von 21,0 Prozent.",
        "Bilanz zum 30.06.2026: langfristige Schulden zum Eigenkapital 0,45; alle Schulden zum Eigenkapital 0,60; "
        "Nettokasse 120,0 Millionen Dollar; Current Ratio 1,80; Quick Ratio 1,20; Zinsdeckung 12,3 mal.",
        "Umsatz der letzten zwölf Monate 4,6 Milliarden Dollar.",
        "Cashflow über die vier Quartale bis 30.06.2026: Free Cashflow 150,0 Millionen Dollar; FCF-Marge 3,3 Prozent; "
        "Cash Conversion 1,42, also operativer Cashflow durch Nettogewinn; Ausschüttungsquote 0,0 Prozent.",
        "Piotroski F-Score 6 von 8 bewertbaren Signalen; erfüllt: Rendite auf das Vermoegen positiv, operativer Cashflow positiv, "
        "operativer Cashflow ueber dem Nettogewinn.",
        "Altman Z 2,50, Grauzone von 1,81 bis 2,99.",
        "Rule of 40, gedacht für Software: Umsatzwachstum der vier Quartale plus 25,0 Prozent plus FCF-Marge 3,3 Prozent "
        "ergibt 28,3; ab 40 erfüllt."]
    p("Etappe 4: Bilanz und Cashflow, je Punkt ein Satz", bz == erwartet_bz, [x for x in bz if x not in erwartet_bz] or bz)
    bw = bewertung_saetze(ratings["aktien"]["AAOI"], streubesitz_kurs=50.0)
    erwartet_bw = [
        "Marktkapitalisierung 6,5 Milliarden Dollar aus 62.000.000 Aktien vom Deckblatt, Stand 01.08.2026, mal dem Schlusskurs der Nacht.",
        "KGV 88,4; KUV 1,43; KBV 5,20.",
        "Enterprise Value 6,4 Milliarden Dollar; EV zu EBITDA 30,1; EV zu Umsatz 1,40.",
        "Je Aktie: Cash 3,10 Dollar; Nettokasse 1,94 Dollar; Buchwert 20,26 Dollar; Free Cashflow 2,42 Dollar.",
        "FCF-Rendite 2,3 Prozent.",
        "Streubesitz laut Deckblatt zum 30.06.2025: 3,1 Milliarden Dollar; beim Schlusskurs von 50,00 Dollar an jenem Tag rund "
        "62.000.000 Aktien in heutiger Stückelung."]
    p("Etappe 4: Bewertung mit Kurs, Werten je Aktie, Renditen und Streubesitz samt Aktienzahl zum Kurs am Stichtag",
      bw == erwartet_bw and dict(teile)["Bewertung"][-1].startswith("Streubesitz laut Deckblatt zum 30.06.2025: 3,1 Milliarden Dollar.")
      and streubesitz_stichtag(ratings, "aaoi") == "2025-06-30" and streubesitz_stichtag(ratings, "AAPL") is None,
      [x for x in bw if x not in erwartet_bw] or bw)
    p("Etappe 4: ohne Kurs oder im Ausland ein ehrlicher Grund; ohne Fundament ein Satz; Splittexte",
      bewertung_saetze({"fundament": {"bewertung_grund": "kein Kurs"}}) == ["Bewertung mit dem Kurs nicht gerechnet: kein Kurs."]
      and bilanz_saetze({}) == ["Keine erweiterten Kennzahlen aus dem SEC-Fundament für diese Aktie."]
      and bewertung_saetze({"fundament": {"fehler": "KeyError: x"}}) == ["Keine Bewertung: KeyError: x."]
      and split_text(1.5) == "Split 3 zu 2" and split_text(0.6667) == "Reverse-Split 2 zu 3" and split_text(0.0286) == "Reverse-Split 1 zu 35"
      and split_text(10) == "Split 10 zu 1")
    import pandas as pd_k
    df_k = pd_k.DataFrame({"Close": [48.0, 49.0, 50.0, 51.0]},
                          index=pd_k.to_datetime(["2025-06-26", "2025-06-27", "2025-06-30", "2025-07-01"]))
    p("Kurs am Stichtag: der Schluss am Tag selbst, sonst am letzten Handelstag davor; ohne Daten None",
      kurs_am("AAOI", "2025-06-30", holen=lambda t, d: df_k) == 50.0
      and kurs_am("AAOI", "2025-06-29", holen=lambda t, d: df_k) == 49.0
      and kurs_am("AAOI", "unbekannt", holen=lambda t, d: df_k) is None and kurs_am("AAOI", "2025-06-30", holen=lambda t, d: None) is None)

    teile2 = bericht("AAPL", rs, ratings, sektoren, live=None, kurve=None, sektor_name="Financial", sektor_quelle="Yahoo")
    text2 = bericht_text(teile2)
    p("Ohne Live-Werte: Schlusskurs aus der Nachtdatei, kein Volumen; Composite nennt, was fehlt; Bank-Begriff; IFRS; Sektor laut Yahoo",
      "Schlusskurs am unbekannt" not in text2 and "Kein Volumen von Yahoo bekommen." in text2 and "Composite nicht verfügbar, es fehlt SMR, A/D." in text2
      and "Nettoerträge" in text2 and "IFRS-Zahlen ungeprüft" in text2 and "Sektor laut Yahoo" in text2 and "Rang 20 von 36" in text2, text2)
    teile3 = bericht("BILLG", rs, ratings, sektoren, live=live_zu)
    text3 = bericht_text(teile3)
    p("Aktie unter den Schwellen: RS gilt, Grund genannt, Ratings fuer sie nicht gerechnet, Sektor unbekannt",
      "RS 12." in text3 and "Nicht im Universum: Kurs unter 15 Dollar" in text3 and "für diese Aktie nicht gerechnet" in text3
      and "Sektor unbekannt" in text3, text3)
    text5 = bericht_text(bericht("JUNGX", rs, ratings, sektoren, live=None))
    p("Junge Aktie (Etappe 1): vorlaeufiges RS mit Kennzeichnung, Quartalen und Zahl der Schlusskurse",
      "RS 91 vorläufig, zwei Quartale, sehr gut; gerechnet aus den vorhandenen Quartalen gegen den ganzen Bezug, "
      "die Aktie hat erst 150 Schlusskurse." in text5, text5)
    # Etappe 5: Analysten und Konsens
    import json as _json
    zeile_k = {"ticker": "AAOI", "konsens_stand": "2026-09-14T19:30:40Z", "konsens_waehrung": "USD",
               "konsens_termin": "2026-11-05", "konsens_fwd_kgv": 14.02, "konsens_kgv_0y": 23.46,
               "konsens_ende_0q": "2026-10-31", "konsens_eps_0q": 2.47269, "konsens_eps_tief_0q": 2.34,
               "konsens_eps_hoch_0q": 2.7, "konsens_eps_analysten_0q": 42, "konsens_eps_vj_0q": 1.3,
               "konsens_eps_wachstum_0q_pct": 90.2, "konsens_umsatz_0q": 108988683310.0,
               "konsens_umsatz_analysten_0q": 42, "konsens_umsatz_vj_0q": 57006000000.0,
               "konsens_umsatz_wachstum_0q_pct": 91.2,
               "konsens_ende_0y": "2027-01-31", "konsens_eps_0y": 9.3, "konsens_eps_analysten_0y": 49,
               "konsens_eps_vj_0y": None, "konsens_eps_wachstum_0y_pct": None,
               "konsens_eps_1y": 15.57, "konsens_eps_vj_1y": -0.5, "konsens_eps_wachstum_1y_pct": None,
               "termin_konsens_datum": "2026-09-15", "termin_quartal": "Jun/2026", "termin_eps_konsens": -0.26,
               "termin_eps_schaetzungen": 1, "termin_eps_vorjahr": 0.9, "termin_vorjahr_datum": "2025-08-27",
               "analysten_stand": "2026-09-12", "analysten_anzahl": 30, "analysten_kaufen": 16, "analysten_halten": 10,
               "analysten_verkaufen": 4, "konsens": "Kaufen", "kursziel": 335.87, "kursziel_tief": 245.0,
               "kursziel_hoch": 400.0, "kursziel_abst_pct": 12.5, "quartale_mit_schaetzung": 4,
               "schaetzung_geschlagen": 3, "letzte_ueberraschung_pct": 1.6, "letzter_bericht": "2026-07-30",
               "rev_stand": "2026-09-14", "rev_hoch_7t_0q": 34, "rev_runter_7t_0q": 3, "rev_hoch_30t_0q": 35,
               "rev_runter_30t_0q": 1, "rev_eps_jetzt_0q": 2.47, "rev_eps_30t_0q": 2.35, "rev_eps_90t_0q": 2.0,
               "stufen_hoch_30t": 1, "stufen_runter_30t": 0, "stufen_neu_30t": 2, "stufen_ziel_rauf_30t": 5,
               "stufen_ziel_runter_30t": 0, "stufen_hoch_90t": 3, "stufen_runter_90t": 1, "stufen_neu_90t": 2,
               "stufen_ziel_rauf_90t": 9, "stufen_ziel_runter_90t": 1,
               "stufen_liste": _json.dumps([{"datum": "2026-09-10", "firma": "Needham", "von": "Hold", "zu": "Buy",
                                             "aktion": "up", "ziel_aktion": "Raises", "ziel": 300.0, "ziel_vorher": 250.0},
                                            {"datum": "2026-09-04", "firma": "Rosenblatt", "von": "Buy", "zu": "Buy",
                                             "aktion": "main", "ziel_aktion": "Maintains", "ziel": 390.0,
                                             "ziel_vorher": 390.0}])}
    kt = konsens_saetze(zeile_k, in_wochenliste=True, grund="")
    ktext = "\n".join(kt)
    p("Konsens: Stand in Wiener Zeit, Forward-KGV, Geschaeftsjahr davor mit seinem Ende",
      "Eingefrorener Konsens von Yahoo, Stand 14.09.2026 um 21:30 Uhr Wiener Zeit." in ktext
      and "Forward-KGV 14,0 mit dem Schlusskurs der Nacht und dem erwarteten Gewinn je Aktie des nächsten "
          "Geschäftsjahres; KGV 23,5 auf das Geschäftsjahr davor bis 31.01.2027." in ktext, ktext)
    p("Konsens: Quartal mit Spanne, Analysten und Wachstum; Umsatz in Milliarden",
      "Quartal bis 31.10.2026: Gewinn je Aktie erwartet 2,47 Dollar, Spanne 2,34 bis 2,70 Dollar, "
      "42 Analysten; gegenüber dem Vorjahresquartal 1,30 Dollar plus 90,2 Prozent." in ktext
      and "Quartal bis 31.10.2026: Umsatz erwartet 109,0 Milliarden Dollar, 42 Analysten; gegenüber dem "
          "Vorjahresquartal 57,0 Milliarden Dollar plus 91,2 Prozent." in ktext, ktext)
    p("Konsens: fehlender und negativer Vergleichswert ehrlich benannt",
      "Geschäftsjahr bis 31.01.2027: Gewinn je Aktie erwartet 9,30 Dollar, 49 Analysten; der "
      "Vergleichswert fehlt im Einfrier-Lauf." in ktext
      and "Nächstes Geschäftsjahr laut Yahoo: Gewinn je Aktie erwartet 15,57 Dollar, Zahl der Analysten unbekannt; "
          "gegenüber dem Geschäftsjahr davor minus 0,50 Dollar kein Prozentwert" in ktext, ktext)
    p("Konsens: Nasdaq-Kalender mit Quartal, negativem Konsens, einer Schaetzung und Vorjahr",
      "Laut Nasdaq-Kalender meldet die Firma am 15.09.2026 das Quartal bis Juni 2026; erwartet minus 0,26 Dollar je "
      "Aktie aus einer Schätzung; im Vorjahresquartal 0,90 Dollar, gemeldet am 27.08.2025." in ktext, ktext)
    p("Konsens: Empfehlungen, Kursziel und Ueberraschungen von Nasdaq",
      "Empfehlungen laut Nasdaq, abgefragt am 12.09.2026: 16 Kaufen, 10 Halten, 4 Verkaufen; Konsens Kaufen." in ktext
      and "Kursziel im Mittel 335,87 Dollar, Spanne 245,00 bis 400,00 Dollar; plus 12,5 Prozent gegenüber" in ktext
      and "in 4 Quartalen mit Schätzung 3 mal geschlagen; zuletzt plus 1,6 Prozent bei der Meldung vom 30.07.2026." in ktext,
      ktext)
    p("Konsens: Revisionen mit Veraenderung seit 30 und 90 Tagen",
      "Quartal bis 31.10.2026: in 7 Tagen 34 Anhebungen und 3 Senkungen einzelner Schätzungen, in 30 Tagen 35 "
      "Anhebungen und 1 Senkung; Konsens heute 2,47 Dollar, vor 30 Tagen 2,35 Dollar, plus 5,1 Prozent seither, vor "
      "90 Tagen 2,00 Dollar, plus 23,5 Prozent seither." in ktext, ktext)
    p("Konsens: Einstufungen je Fenster und die juengsten mit Kursziel",
      "In 30 Tagen 1 Heraufstufung, 0 Herabstufungen und 2 Erstbewertungen; Kursziel 5 mal angehoben und 0 mal "
      "gesenkt." in ktext
      and "10.09.2026, Needham: hochgestuft von Hold auf Buy; Kursziel angehoben von 250,00 auf 300,00 Dollar." in ktext
      and "04.09.2026, Rosenblatt: Einstufung bestätigt, Buy; Kursziel unverändert bei 390,00 Dollar." in ktext
      and kt[-1] == "Entscheidungshilfen, keine Filter.", ktext)
    eur_k = dict(zeile_k, konsens_waehrung="EUR", konsens_fwd_kgv=None)
    p("Konsens in Euro: Betraege in EUR, kein Forward-KGV mit Grund",
      "Beträge in EUR" in "\n".join(konsens_saetze(eur_k, True, ""))
      and "Kein Forward-KGV: Der Konsens steht in EUR, der Kurs in Dollar." in konsens_saetze(eur_k, True, ""))
    p("Nicht in der Wochenliste: keine Revisionen, ehrlich gesagt",
      "Revisionen und Einstufungen gibt es nur für Aktien der Wochenliste." in konsens_saetze(zeile_k, False, "")
      and not any("Needham" in x for x in konsens_saetze(zeile_k, False, "")))
    p("Ohne Analystendaten: Grund, fehlende Zeile, nicht uebergeben",
      konsens_saetze(None, True, "kein Token für das Datenrepo")[0].startswith(
          "Analystendaten nicht geladen: kein Token für das Datenrepo.")
      and konsens_saetze(None, True, "") == ["Für diese Aktie stehen in der Nachttabelle des Scanners keine Analystendaten."]
      and "DATEN_TOKEN" in konsens_saetze(None)[0] and "DATEN_TOKEN" in konsens_saetze(None, True, "x")[0])
    p("Gast (S4): Kapitel ohne Secrets und Repos, nur der Hinweis auf den vollen Zugang",
      konsens_saetze(None, True, NUR_VOLLER_ZUGANG) == ["Analysten und Konsens stehen nur im vollen Zugang."]
      and short_saetze(None, NUR_VOLLER_ZUGANG) == ["Die Short-Daten stehen nur im vollen Zugang."]
      and gruppe_saetze(None, NUR_VOLLER_ZUGANG) == ["Die Branchengruppe steht nur im vollen Zugang."])
    p("Quartal von Nasdaq in Worten", quartal_text("Jun/2026") == "Juni 2026" and quartal_text("Jan/2027") == "Jänner 2027"
      and quartal_text(None) == "unbekannt")
    df_a = pd.DataFrame([{"ticker": "AAOI", "konsens_fwd_kgv": 14.02, "konsens_stand": None, "rev_hoch_7t_0q": float("nan")},
                         {"ticker": "BBB", "konsens_fwd_kgv": float("nan"), "konsens_stand": "x", "rev_hoch_7t_0q": 2.0}])
    z_a = analysten_zeile(df_a, "aaoi")
    p("Analystenzeile: NaN wird None, Zahlen bleiben, fehlende Aktie None",
      z_a == {"ticker": "AAOI", "konsens_fwd_kgv": 14.02, "konsens_stand": None, "rev_hoch_7t_0q": None}
      and isinstance(z_a["konsens_fwd_kgv"], float) and analysten_zeile(df_a, "ZZZ") is None
      and analysten_zeile(None, "AAOI") is None, str(z_a))
    # Etappe 7: Leerverkaeufe laut FINRA
    zeile_s = {"short_stand": "2026-09-14", "short_anteil_pct": 60.2, "short_volumen": 380591.1,
               "short_gesamtvolumen": 631970.7, "short_anteil_20t_pct": 55.4, "short_tage_20t": 20,
               "short_median_pct": 51.8, "short_hinweis": None}
    st_text = "\n".join(short_saetze(zeile_s, ""))
    p("Leerverkaeufe: Tag, 20 Tage, Median, Erklaerung",
      "Leerverkäufe laut FINRA am 14.09.2026: 60,2 Prozent der außerbörslich gemeldeten Umsätze, 380.591 von 631.971 "
      "Aktien." in st_text
      and "Über die letzten 20 Handelstage 55,4 Prozent, nach Volumen gewichtet; an 20 der 20 Tage außerbörslich "
          "gehandelt." in st_text
      and "Zum Vergleich der Median aller Aktien des Universums an diesem Tag: 51,8 Prozent." in st_text
      and "kein Short Interest" in st_text, st_text)
    teil = short_saetze(dict(zeile_s, short_anteil_20t_pct=None, short_tage_20t=None,
                             short_hinweis="der Wert über 20 Handelstage fehlt, die Tagesdatei vom 20.08.2026 ist nicht verwendbar"), "")
    p("Leerverkaeufe: fehlender 20-Tage-Wert mit Grund, gross geschrieben",
      "Der Wert über 20 Handelstage fehlt, die Tagesdatei vom 20.08.2026 ist nicht verwendbar." in teil, str(teil))
    nv = short_saetze({"short_stand": None, "short_hinweis": "die FINRA-Tagesdatei vom 14.09.2026 fehlt oder ist "
                                                            "unvollständig, FINRA antwortete mit 404"}, "")
    p("Leerverkaeufe: nicht verfuegbar mit Grund", nv == ["Leerverkaufsvolumen laut FINRA nicht verfügbar: die "
                                                         "FINRA-Tagesdatei vom 14.09.2026 fehlt oder ist unvollständig, "
                                                         "FINRA antwortete mit 404."], str(nv))
    ohne_h = short_saetze(dict(zeile_s, short_anteil_pct=None, short_volumen=0.0, short_gesamtvolumen=0.0), "")
    p("Leerverkaeufe: kein ausserboerslicher Umsatz am Tag",
      ohne_h[0] == "Am 14.09.2026 meldete FINRA für diese Aktie keine außerbörslichen Umsätze.", str(ohne_h))
    p("Leerverkaeufe: ohne Daten wie beim Konsens", short_saetze(None, "kein Token für das Datenrepo")[0].startswith(
        "Short-Daten nicht geladen") and "DATEN_TOKEN" in short_saetze(None)[0])
    # Etappe 6: Branchengruppe
    zeile_g = {"gruppe": "Semiconductors", "gruppe_ebene": "GICS-Unterbranche", "gruppe_rang": 12.0,
               "gruppe_rang_3w": 20.0, "gruppe_rang_6w": None, "gruppen_zahl": 158.0, "gruppe_titel": 42.0,
               "gruppe_titel_3w": 41.0, "gruppe_titel_6w": None,
               "gruppe_stand": "2026-09-14", "gruppe_zuordnung_stand": "2026-09-16",
               "gruppe_hinweis": "der Rang vor sechs Wochen fehlt, die Kurshistorie kennt erst 20 Handelstage"}
    gt = gruppe_saetze(zeile_g, "")
    p("Branchengruppe: Rang von N am Tag, vor drei Wochen, je mit Zahl der Aktien, fehlender Rang mit Grund, Liste, "
      "kein Filter",
      gt == ["Branchengruppe laut GICS-Unterbranche: Semiconductors; Rang 12 von 158 Gruppen am 14.09.2026, aus 42 "
             "Aktien gerechnet; vor drei Wochen Rang 20, aus 41 Aktien gerechnet.",
             "Gerechnet wird mit den Aktien der Gruppe, die einen vollen RS-Rohwert haben; Rang 1 hat die Gruppe mit "
             "dem höchsten Median der RS-Rohwerte. Jede Gruppe bekommt einen Rang, auch eine mit einer einzigen Aktie; "
             "deshalb steht bei jedem Rang, aus wie vielen Aktien er gerechnet ist.",
             "Der Rang vor sechs Wochen fehlt, die Kurshistorie kennt erst 20 Handelstage.",
             "Die Gruppe stammt aus der eigenen Zuordnungsliste vom 16.09.2026.",
             "Entscheidungshilfe, kein Filter."], str(gt))
    gu = gruppe_saetze({"gruppe": "Branche unbekannt", "gruppe_rang": 150.0, "gruppen_zahl": 165.0, "gruppe_titel": 212.0,
                        "gruppe_rang_3w": float("nan"), "gruppe_titel_3w": float("nan"), "gruppe_stand": "2026-09-14",
                        "gruppe_hinweis": "die Aktie steht nicht in der Zuordnungsliste vom 16.09.2026"}, "")
    p("Branchengruppe: unbekannt mit Grund und mit Rang samt Zahl der Aktien (Nachfrage N9)",
      gu[0] == "Branche unbekannt: die Aktie steht nicht in der Zuordnungsliste vom 16.09.2026."
      and gu[1] == ("Sammelgruppe Branche unbekannt, darin die Titel ohne Branche, vor allem Listungen nach dem Stichtag "
                    "der Zuordnungsliste; Rang 150 von 165 Gruppen am 14.09.2026, aus 212 Aktien gerechnet.")
      and gu[-1] == "Entscheidungshilfe, kein Filter." and not any("ohne Rang" in x for x in gu), str(gu))
    g1 = gruppe_saetze({"gruppe": "Gold", "gruppe_rang": 3.0, "gruppe_titel": 1.0, "gruppe_stand": "2026-09-14"}, "")
    p("Branchengruppe: eine Gruppe mit einer einzigen Aktie hat einen Rang und sagt es (Nachfrage N8)",
      g1[0] == "Branchengruppe laut GICS-Unterbranche: Gold; Rang 3 am 14.09.2026, aus 1 Aktie gerechnet.", str(g1))
    gn = gruppe_saetze({"gruppe": None, "gruppe_hinweis": "die eigene Zuordnungsliste der Branchen liegt noch nicht vor"},
                       "")
    p("Branchengruppe: ohne Zuordnungsliste nicht verfuegbar", gn == ["Branchengruppe nicht verfügbar: die eigene "
                                                                    "Zuordnungsliste der Branchen liegt noch nicht vor."],
      str(gn))
    p("Branchengruppe: ohne Daten wie beim Konsens", gruppe_saetze(None, "kein Token für das Datenrepo")[0].startswith(
        "Branchengruppe nicht geladen") and "DATEN_TOKEN" in gruppe_saetze(None)[0])
    rs_w = dict(rs, listen={"AAOI": {}})
    teile_k = bericht("AAOI", rs_w, ratings, sektoren, live=live_auf, analysten=zeile_k, analysten_grund="")
    p("Bericht: Kapitel Analysten und Konsens nach der Bewertung, Wochenliste aus der Nachtdatei",
      teile_k[7][0] == "Analysten und Konsens" and any("Needham" in x for x in teile_k[7][1])
      and teile_k[8][0] == "Leerverkäufe" and teile_k[9][0] == "Branchengruppe")

    teile4 = bericht("XYZQ", {}, {}, {}, live=None)
    text4 = bericht_text(teile4)
    p("Ganz ohne Dateien: ehrliche Saetze statt Fehler", "RS nicht verfügbar" in text4 and "Ratings-Datei fehlt" in text4
      and "Keine Nachtwerte vorhanden" in text4, text4)
    k, q = kurve_fuer("AAOI", {"aktien": {"AAOI": {"kurve": {"0": 0.05, "390": 1.0}}}}, bauen=False)
    p("Kurve aus dem Vorrat mit ganzzahligen Minuten", k == {0: 0.05, 390: 1.0} and q == "Vorrat")
    p("Kurve ohne Vorrat und ohne Bauen: keine", kurve_fuer("ZZZZ", {}, bauen=False) == (None, "keine"))
    p("Datei laden: Repo-Abruf ersetzt, sonst leer", lade_datei("gibt_es_nicht.json", holen=lambda n: {}) == {}
      and lade_datei("x.json", holen=lambda n: {"a": 1}) == {"a": 1})

    # Chartmuster, Kaufpunkte, Kerzen (14.09.2026)
    haken = chr(0x2713) + " 8/8"
    p("Bildzeichen werden gefunden, gewoehnliche Zeichen nicht",
      bildzeichen_in("Rakete " + chr(0x1F680) + " und " + haken) == [chr(0x1F680), chr(0x2713)]
      and bildzeichen_in("Ä ö ß € 12,5 % → ≥ & | ;") == [], bildzeichen_in("Ä ö ß € → ≥"))
    p("lesbar: Bildzeichen weg, Gedankenstrich zu Strichpunkt, Bereich mit bis, Vergleich in Worten",
      lesbar(haken) == "8/8" and lesbar("Kein Muster — generischer Level") == "Kein Muster; generischer Level"
      and lesbar("Tiefe 12–50 %") == "Tiefe 12 bis 50 %" and lesbar("≥25 % über") == "mindestens 25 % über"
      and lesbar("Darvas Box · VCP") == "Darvas Box; VCP" and lesbar(chr(0x26A0) + chr(0xFE0F) + " Achtung") == "Achtung",
      [lesbar(haken), lesbar("Kein Muster — generischer Level"), lesbar(chr(0x26A0) + chr(0xFE0F) + " Achtung")])
    tt_cfg = {"tt_min_above_low": 0.25, "tt_max_below_high": 0.3, "tt_rs_min": 70}
    p("Trend-Template-Bedingungen deutsch, Schwellen aus den Regelwerk-Werten statt aus dem Namen",
      tt_kriterium_text("≥25 % über 52W-Tief", tt_cfg) == "mindestens 25 Prozent über dem 52-Wochen-Tief"
      and tt_kriterium_text("≤25 % unter 52W-Hoch", tt_cfg) == "höchstens 30 Prozent unter dem 52-Wochen-Hoch"
      and tt_kriterium_text("RS-Rank ≥ 70", tt_cfg) == "RS mindestens 70"
      and tt_kriterium_text("Kurs > MA50", tt_cfg) == "Kurs über dem 50-Tage-Durchschnitt"
      and tt_kriterium_text("Unbekannt ≥ 3", tt_cfg) == "Unbekannt mindestens 3")
    p("RS fuer das Trend Template: marktweit, vorlaeufig, keines",
      rs_fuer_muster({"rs": 91})[0] == 91.0 and "RS 91 gegen den ganzen US-Markt" in rs_fuer_muster({"rs": 91})[1]
      and rs_fuer_muster({"rs_vorlaeufig": 80})[0] == 80.0 and "vorläufigen RS 80" in rs_fuer_muster({"rs_vorlaeufig": 80})[1]
      and rs_fuer_muster({}) == (None, "Ohne RS-Wert gilt die RS-Bedingung als nicht erfüllt."))
    res = {"close": 100.0, "pattern_count": 1, "tt_pass": False, "tt_count": 6,
           "tt_failed": ["Kurs > MA50", "RS-Rank ≥ 70"],
           "points": [{"strategie": "VCP", "kaufpunkt": 105.0, "stop": 96.6, "ziel": 126.0,
                       "status": "Pivot noch nicht überschritten — beobachten", "notiz": "3 Kontraktionen."},
                      {"strategie": "Fallback: 20-Tage-Hoch (Pivot)", "kaufpunkt": 98.0, "stop": 90.0, "ziel": None,
                       "status": "Kein Muster — Konsolidierungs-Pivot", "notiz": ""}]}
    ms = muster_saetze(res, "Die RS-Bedingung ist mit RS 58 gegen den ganzen US-Markt geprüft.", tt_cfg)
    p("Muster: aktives Muster, Trend Template mit fehlenden Bedingungen, RS-Satz",
      ms[0] == "Ein aktives Chartmuster: VCP." and ms[1] == "Trend Template nach Minervini nicht erfüllt, 6 von 8 Bedingungen."
      and ms[2] == "Es fehlt: Kurs über dem 50-Tage-Durchschnitt; RS mindestens 70." and ms[3].startswith("Die RS-Bedingung"), ms)
    ohne = muster_saetze({"points": [res["points"][1]], "pattern_count": 0, "tt_pass": True, "tt_count": 8, "tt_failed": []})
    p("Muster: ohne echtes Muster ehrlicher Hinweis; Trend Template erfuellt",
      ohne[0].startswith("Kein aktives Chartmuster.") and ohne[1] == "Trend Template nach Minervini erfüllt, 8 von 8 Bedingungen.", ohne)
    ks = kaufpunkt_saetze(res)
    p("Kaufpunkte: Preis, Abstand, Stop, Risiko, Ziel, Chance zu Risiko, Status ohne Gedankenstrich",
      ks[0] == ("Kaufpunkt 1, VCP: 105,00 Dollar, 5,0 Prozent über dem Kurs; Stop 96,60 Dollar, Risiko 8,0 Prozent; "
                "Ziel 126,00 Dollar, Chance 20,0 Prozent, Chance zu Risiko 2,5 zu 1; Pivot noch nicht überschritten; "
                "beobachten; 3 Kontraktionen.")
      and ks[1].startswith("Kaufpunkt 2, allgemeine Marke, 20-Tage-Hoch (Pivot): 98,00 Dollar, der Kurs liegt 2,0 Prozent darüber")
      and ks[-1].startswith("Kaufpunkt heißt nicht Kaufsignal"), ks)
    p("Kaufpunkte ohne Ergebnis: ehrlicher Satz", kaufpunkt_saetze(None) == ["Keine Kaufpunkte berechnet."])
    p("Anzeige: Kuerzel in Worten, Dezimalpunkt als Beistrich, Datum bleibt",
      anzeige_text("Fallback: 52W-Hoch-Breakout; MA50 aktuell 114.74; am 11.09.2026; 3.5 Prozent")
      == "allgemeine Marke, 52-Wochen-Hoch-Breakout; 50-Tage-Durchschnitt aktuell 114,74; am 11.09.2026; 3,5 Prozent",
      anzeige_text("Fallback: 52W-Hoch-Breakout; MA50 aktuell 114.74; am 11.09.2026; 3.5 Prozent"))
    p("Anzeige: Vergleichszeichen zwischen Woertern in Worten",
      anzeige_text("Setup komplett (Kurs > SMA21)") == "Setup komplett (Kurs über 21-Tage-Durchschnitt)"
      and anzeige_text("Tief < Vortag") == "Tief unter Vortag", anzeige_text("Setup komplett (Kurs > SMA21)"))
    cs = chart_skript("aktienchart_tag", "Chart AAOI: Kurs < 50 und > 40, Jänner")
    p("Chart-Skript: ohne Kleiner-Zeichen, Schluessel-Klasse, Bild mit Beschreibung, Inhalt verborgen",
      "<" not in cs and ".st-key-'+k+' [data-testid=stPlotlyChart]" in cs and '"aktienchart_tag"' in cs
      and "setAttribute('role','img')" in cs and "aria-label" in cs and "aria-hidden" in cs, cs[:80])
    try:
        chart_skript("x'); alert(1); ('", "t")
        p("Chart-Skript weist fremde Zeichen im Schluessel ab", False)
    except ValueError:
        p("Chart-Skript weist fremde Zeichen im Schluessel ab", True)
    import pandas as pd
    tage_k = pd.DataFrame({"datetime": pd.to_datetime(["2026-09-10", "2026-09-11"]), "open": [10.0, 11.0],
                           "high": [12.0, 12.5], "low": [9.5, 10.5], "close": [11.0, 12.1], "volume": [1000.0, 2500.0]})
    kt = kerzen_saetze(kerzen(tage_k, "tag"), "tag")
    p("Tageskerzen: neueste zuerst, Wochentag, Werte, Veraenderung zum Vortag, Stueck",
      kt == ["Freitag, 11.09.2026: Eröffnung 11,00, Hoch 12,50, Tief 10,50, Schluss 12,10 Dollar; plus 10,0 Prozent "
             "gegenüber dem Vortag; 2.500 Stück.",
             "Donnerstag, 10.09.2026: Eröffnung 10,00, Hoch 12,00, Tief 9,50, Schluss 11,00 Dollar; 1.000 Stück."], kt)
    monate_k = pd.DataFrame({"datetime": pd.to_datetime(["2025-11-01", "2025-12-01", "2026-01-01", "2026-02-01"]),
                             "open": [10.0, 11.0, 12.0, 13.0], "high": [11.5, 12.5, 14.0, 13.5],
                             "low": [9.0, 10.0, 11.5, 12.0], "close": [11.0, 12.0, 13.0, 12.5],
                             "volume": [100.0, 200.0, 300.0, 400.0]})
    km = kerzen_saetze(kerzen(monate_k, "monat"), "monat", anzahl=2, heute=datetime(2026, 2, 20).date())
    p("Monatskerzen: Jaenner, laufender Monat mit bisher, nur die verlangte Anzahl",
      len(km) == 2 and km[0].startswith("Februar 2026, bisher: Eröffnung 13,00") and "minus 3,8 Prozent gegenüber dem Vormonat" in km[0]
      and km[1].startswith("Jänner 2026: Eröffnung 12,00"), km)
    kj = kerzen(monate_k, "jahr")
    p("Jahreskerzen aus Monaten: erste Eroeffnung, hoechstes Hoch, tiefstes Tief, letzter Schluss, Volumen summiert",
      len(kj) == 2 and kj.iloc[0]["open"] == 10.0 and kj.iloc[0]["high"] == 12.5 and kj.iloc[0]["low"] == 9.0
      and kj.iloc[0]["close"] == 12.0 and kj.iloc[0]["volume"] == 300.0 and kj.iloc[1]["high"] == 14.0
      and kj.iloc[1]["volume"] == 700.0, kj.to_dict("records"))
    kjs = kerzen_saetze(kj, "jahr", heute=datetime(2026, 2, 20).date())
    p("Jahreskerzen als Saetze: laufendes Jahr mit bisher",
      kjs[0].startswith("Jahr 2026, bisher:") and "plus 4,2 Prozent gegenüber dem Vorjahr" in kjs[0], kjs)
    # Chartmuster aus Gerhards Papier vom 20.09.2026: nur abgeschlossene Tage.
    # 300 Handelstage leicht steigend, der letzte (18.09.2026) ein Inside Day.
    from zoneinfo import ZoneInfo
    cm_tage = pd.bdate_range(end="2026-09-18", periods=300)
    cm_c = [50.0 + 0.1 * i for i in range(300)]
    cm_df = pd.DataFrame({"datetime": cm_tage, "open": [c - 0.2 for c in cm_c], "high": [c + 0.5 for c in cm_c],
                          "low": [c - 0.5 for c in cm_c], "close": cm_c, "volume": [1_000_000.0] * 300})
    cm_df.loc[298, ["high", "low"]] = [cm_c[298] + 2.0, cm_c[298] - 2.0]
    cm_df.loc[299, ["open", "high", "low", "close", "volume"]] = [cm_c[298], cm_c[298] + 1.0, cm_c[298] - 1.0,
                                                                  cm_c[298] + 0.3, 800_000.0]
    ny = ZoneInfo("America/New_York")
    cm_mittag = chartmuster_saetze(cm_df, jetzt=datetime(2026, 9, 18, 12, 0, tzinfo=ny))
    cm_abend = chartmuster_saetze(cm_df, jetzt=datetime(2026, 9, 18, 16, 30, tzinfo=ny))
    cm_montag = chartmuster_saetze(cm_df, jetzt=datetime(2026, 9, 21, 10, 0, tzinfo=ny))
    p("Chartmuster: waehrend des Handels zaehlt der Vortag, der Inside Day steht noch nicht fest",
      cm_mittag[0].startswith("Mit dem Schluss vom 17.09.2026:") and "Inside Day" not in cm_mittag[0], cm_mittag)
    p("Chartmuster: nach dem Schluss zaehlt der Tag selbst, mit beiden Einstiegen",
      cm_abend[0].startswith("Mit dem Schluss vom 18.09.2026:") and "Inside Day" in cm_abend[0]
      and "eng über" in cm_abend[0] and "konservativ über" in cm_abend[0], cm_abend)
    p("Chartmuster: ein abgeschlossener Vortag bleibt am naechsten Handelstag stehen",
      cm_montag[0] == cm_abend[0], cm_montag)
    p("Chartmuster: ohne Kurse ein ehrlicher Satz",
      chartmuster_saetze(None) == ["Ohne Kursdaten gibt es keine Chartmuster."])
    alle_saetze = ms + ohne + ks + kt + km + kjs + cm_mittag + cm_abend
    p("Keine Bildzeichen und keine Gedankenstriche in den neuen Saetzen",
      not any(bildzeichen_in(x) or "—" in x or "–" in x for x in alle_saetze))
    print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles bestanden.")
    return 1 if fehler else 0


def zeige(ticker):
    """Echter Lauf: Dateien aus dem Repo oder dem Ordner, Kurse von Yahoo."""
    daten = {n: lade_datei(n) for n in DATEIEN}
    t, kandidaten = finde(ticker, daten["rs_universum.json"])
    if t is None:
        print("Nicht eindeutig. Kandidaten: " + "; ".join(f"{k} {n}" for k, n in kandidaten))
        return 1
    live = live_daten(t)
    kurve, kq = kurve_fuer(t, daten["volumenkurven.json"])
    sektor, sq = sektor_name_fuer(t)
    stichtag = streubesitz_stichtag(daten["ibd_ratings.json"], t)
    sb_kurs = kurs_am(t, stichtag) if stichtag else None
    print(bericht_text(bericht(t, daten["rs_universum.json"], daten["ibd_ratings.json"], daten["sektor_rangliste.json"],
                               live=live, kurve=kurve, kurve_quelle=kq, sektor_name=sektor, sektor_quelle=sq,
                               streubesitz_kurs=sb_kurs)))
    try:
        import pattern_scanner as ps
        kurse = ps.yahoo_einzeln(t)
    except Exception:  # noqa: BLE001, ohne Kurse sagt der Satz das selbst
        kurse = None
    print("\nChartmuster aus Gerhards Papier vom 20.09.2026")
    for satz in chartmuster_saetze(kurse):
        print(satz)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Eine Aktie nachschlagen: alle unsere Zahlen als Text.")
    ap.add_argument("--selbsttest", action="store_true")
    ap.add_argument("--zeige", metavar="TICKER")
    args = ap.parse_args()
    if args.selbsttest:
        return selbsttest()
    if args.zeige:
        return zeige(args.zeige)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
