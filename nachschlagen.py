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
    rs_universum.json      RS gegen den ganzen US-Markt, Kurs, 52-Wochen-Hoch,
                           RS-Linien, Kennzeichnung "im Universum"
    ibd_ratings.json       EPS, SMR, A/D und Composite als Naeherung aus dem
                           SEC-Fundament (amtlich), dazu Umsatz und Gewinn je
                           Aktie des juengsten Quartals, des Vorquartals und
                           des Vorjahresquartals
    sektor_rangliste.json  Rang des Sektor-ETFs (36 ETFs, Faber-Mittel)
    volumenkurven.json     die eigene Volumenkurve je Listenaktie
  Live von Yahoo, ohne Schluessel: Kurs, das bisher gehandelte Volumen des
  Tages, fuer Aktien ohne Vorratskurve die Fuenf-Minuten-Historie fuer die
  Kurve, und der Sektor, wenn die Aktie in keiner Wochenliste steht.

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

def _vorwoche(e):
    verlauf = e.get("rs_verlauf") or []
    if len(verlauf) < 2:
        return None
    heute = verlauf[-1][0] if isinstance(verlauf[-1], list) and verlauf[-1] else None
    for tag, wert in reversed(verlauf[:-1]):
        try:
            if heute and (datetime.fromisoformat(heute) - datetime.fromisoformat(tag)).days >= 5:
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
        s.append(f"RS {int(e['rs'])}" + (", sehr gut" if int(e["rs"]) >= 85 else "")
                 + (f"; vor einer Woche {int(vor)}, Änderung {int(e['rs']) - int(vor):+d}".replace("+", "plus ").replace("-", "minus ")
                    if vor is not None else "") + ".")
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
    s.append(f"A/D-Note {r['ad']}, Rang {int(r['ad_rang'])}, Näherung aus Kurs und Volumen." if r.get("ad")
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
        return s
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
    return [x for x in s if x]


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
    else:
        s.append("Keine Nachtwerte vorhanden; der nächste Nachtscan legt sie an.")
    if ratings and ratings.get("gebaut_am"):
        s.append(f"Ratings gebaut {str(ratings['gebaut_am'])[:16].replace('T', ' um ')}.")
    if sektoren and sektoren.get("handelstag"):
        s.append(f"Sektor-Rangliste vom Handelstag {datum_text(sektoren['handelstag'])}.")
    s.append("Kurs und Volumen live von Yahoo; RS gegen den ganzen US-Markt mit Kappung der Einzelrenditen bei plus 50 Prozent; "
             "Ratings als Näherung aus amtlichen SEC-Zahlen. Entscheidungshilfen, keine Filter.")
    return s


def bericht(ticker, rs, ratings, sektoren, live=None, kurve=None, kurve_quelle="", sektor_name=None, sektor_quelle=""):
    """Liste von (Ueberschrift, [Saetze]) fuer die Anzeige."""
    t = str(ticker or "").upper()
    e = eintraege(rs).get(t, {})
    r = ((ratings or {}).get("aktien") or {}).get(t, {})
    return [("Aktie", kopf_saetze(t, e, live)),
            ("Unsere Ratings", ratings_saetze(e, r, ratings)),
            ("Volumen", volumen_saetze(live, kurve, kurve_quelle)),
            ("Umsatz und Gewinn", wachstum_saetze(r)),
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
          "aktien": {"AAOI": {"name": "Applied Optoelectronics, Inc. - Common Stock", "boerse": "Nasdaq", "kurs": 105.36,
                              "pct": 2.0, "rs": 58, "abst_52w_hoch_pct": -54.9, "kurs_52w_hoch": False,
                              "rs_verlauf": [["2026-09-04", 56], ["2026-09-11", 58]], "linie_spy_hoch": False, "linie_qqq_hoch": False},
                     "AAPL": {"name": "Apple Inc. - Common Stock", "boerse": "Nasdaq", "kurs": 230.0, "pct": -0.5, "rs": 70,
                              "letzter_tag": "2026-09-11"}},
          "ausserhalb": {"BILLG": {"name": "Billig Corp. - Common Stock", "boerse": "NYSE American", "kurs": 3.0, "rs": 12,
                                   "grund": "Kurs unter 15 Dollar"},
                         "APPLD": {"name": "Applied Digital Corporation - Common Stock", "boerse": "Nasdaq", "kurs": 9.0, "rs": 40,
                                   "grund": "Kurs unter 15 Dollar"}},
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
                                   "eps_wachstum_vj_pct": None, "eps_wachstum_vq_pct": 7.0},
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
    p("Bericht hat sechs Teile in fester Reihenfolge",
      [u for u, _ in teile] == ["Aktie", "Unsere Ratings", "Volumen", "Umsatz und Gewinn", "Sektor", "Stand"])
    p("Kopf: Kuerzel, Name, Boerse, Kurs live, Abstand zum Hoch",
      "AAOI, Applied Optoelectronics, Inc., Nasdaq." in text and "Kurs 160,00 Dollar" in text and "Abstand zum 52-Wochen-Hoch minus 54,9 Prozent" in text)
    p("Ratings: RS mit Vorwoche, EPS, SMR, A/D, Composite je ein Satz",
      "RS 58; vor einer Woche 56, Änderung plus 2." in text and "EPS-Rating 87." in text and "SMR-Note B, Rang 65." in text
      and "A/D-Note C, Rang 48, Näherung" in text and "Composite 91." in text and "Basis amtlich, 8 Quartale." in text, text)
    p("Wachstum: Prozent zuerst, dann vorher und jetzt in ganzen Zahlen, Quartalsende; EPS-Vorjahr im Minus ohne Prozentwert",
      "Umsatz Wachstum gegenüber dem Vorjahresquartal: plus 25,0 Prozent; vorher 987.654.321 Dollar, jetzt 1.234.567.890 Dollar." in text
      and "gegenüber dem Vorquartal: plus 3,7 Prozent; vorher 1.190.000.000 Dollar" in text
      and "Jüngstes Quartal bis 30.06.2026." in text
      and "Gewinn je Aktie, Wachstum gegenüber dem Vorjahresquartal: kein Prozentwert" in text
      and "vorher minus 0,20 Dollar, jetzt 1,23 Dollar" in text, text)
    p("Sektor: deutscher Name, ETF, Rang von 36, vor drei Wochen, Aufsteiger",
      "Sektor Technologie, ETF XLK: Rang 3 von 36, vor drei Wochen Rang 7." in text and "Aufsteiger: Technology (XLK) neu unter den ersten fünf" in text, text)
    p("Stand: Handelstag, Bezug, Ratings-Stand, Sektor-Stand", "Nachtwerte vom Handelstag 11.09.2026" in text and "Bezug 5339" in text
      and "Ratings gebaut 2026-09-13 um 00:10" in text and "Sektor-Rangliste vom Handelstag 11.09.2026" in text)
    p("Kein Gedankenstrich, kein senkrechter Strich, keine Tabelle", "–" not in text and "|" not in text and "—" not in text)

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
    teile4 = bericht("XYZQ", {}, {}, {}, live=None)
    text4 = bericht_text(teile4)
    p("Ganz ohne Dateien: ehrliche Saetze statt Fehler", "RS nicht verfügbar" in text4 and "Ratings-Datei fehlt" in text4
      and "Keine Nachtwerte vorhanden" in text4, text4)
    k, q = kurve_fuer("AAOI", {"aktien": {"AAOI": {"kurve": {"0": 0.05, "390": 1.0}}}}, bauen=False)
    p("Kurve aus dem Vorrat mit ganzzahligen Minuten", k == {0: 0.05, 390: 1.0} and q == "Vorrat")
    p("Kurve ohne Vorrat und ohne Bauen: keine", kurve_fuer("ZZZZ", {}, bauen=False) == (None, "keine"))
    p("Datei laden: Repo-Abruf ersetzt, sonst leer", lade_datei("gibt_es_nicht.json", holen=lambda n: {}) == {}
      and lade_datei("x.json", holen=lambda n: {"a": 1}) == {"a": 1})
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
    print(bericht_text(bericht(t, daten["rs_universum.json"], daten["ibd_ratings.json"], daten["sektor_rangliste.json"],
                               live=live, kurve=kurve, kurve_quelle=kq, sektor_name=sektor, sektor_quelle=sq)))
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
