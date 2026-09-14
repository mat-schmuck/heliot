#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
INDUSTRY GROUP RS (Etappe 6, Gerhards Entscheidung 11)
======================================================
Gerhard, 13.09.2026: "11: JA, Industry Group RS bauen, auf Basis dieses
einmaligen Abzugs. Median der RS-Rohwerte je Gruppe, Rang heute und vor 3
und 6 Wochen." Dazu aus Entscheidung 10: "Der Abzug altert. Neue Listungen
nach dem Stichtag haben keine Branche, das sind rund 250 im Jahr. Bitte
einen Rueckfall 'Branche unbekannt' einbauen, sonst fehlen sie still in der
Gruppen-Rangliste."

Reine Anzeige, nichts filtert (Grundsatz der Entscheidungen 1 bis 13). Die
Werte liegen wie Konsens und Short-Daten im privaten Datenrepo
(scanner_analysten.parquet, dazu die Rangliste scanner_gruppen.json), weil
die Zuordnung Aktie zu Gruppe aus dem EODHD-Abzug stammt.

GRUPPEN
  Die Ebene steht in CFG["gruppen_rs"]["ebene"]. Vorgabe ist die
  GICS-Unterbranche (EODHD-Feld GicSubIndustry, rund 160 Gruppen), so wie
  die Recherche vom 13.09.2026 (Gruppe E, Punkt 6) sie Gerhard vorgelegt
  hat. Die Zuordnung kommt aus der eigenen Zuordnungsliste
  (zuordnung_bauen.py, Entscheidung 10), nie aus einem laufenden Abruf.

WAS GERECHNET WIRD
  Handelstage   ein Tag, an dem mindestens ein Zehntel der Aktien einen Kurs
                hat, bis zum Handelstag der Nachttabelle; dieselbe Regel wie
                bei den Short-Daten (Etappe 7).
  Stichtage     der Handelstag und 15 und 30 Handelstage davor (drei und
                sechs Wochen, wie IBD und unsere Sektor-Rangliste).
  Rohwert       red_to_green.rs_rohwert ueber die Schlusskurse bis
                einschliesslich Stichtag, dieselbe Formel wie das RS-Rating.
                Nur mit Kurs genau am Stichtag und voller Historie von 253
                Schlusskursen; vorlaeufige Rohwerte (Entscheidung 1) zaehlen
                wie im Bezug des RS-Universums nicht.
  Median        je Gruppe ueber die Rohwerte ihrer Aktien am Stichtag.
  Rang          1 fuer den hoechsten Median, fortlaufend ueber alle Gruppen
                mit mindestens einer Aktie am Stichtag; gleiche Mediane
                ordnet der Gruppenname.
  Branche unbekannt  Aktien ohne Eintrag oder ohne Gruppe in der
                Zuordnungsliste. Sie stehen als eigene Zeile in der
                Rangliste, mit Zahl der Aktien und Median, aber OHNE Rang:
                Eine Sammelgruppe ist keine Branche, und ein eigener Rang
                verschoebe die Raenge der echten Gruppen (eigene
                Festlegung, im Bericht benannt). Die Aktie selbst traegt
                die Gruppe "Branche unbekannt" samt Grund.

MINDESTABDECKUNG wie beim RS-Universum: Zaehlt eine Aktie an einem Stichtag
zur Basis (volle Historie bis dahin), fehlt ihr aber der Kurs genau an
diesem Tag, fehlt ihr Rohwert. Tragen weniger Aktien der Basis einen
Rohwert, als die Mindestabdeckung des RS-Universums verlangt, gibt es fuer
diesen Stichtag keine Raenge ("nicht verfuegbar" samt Grund); lieber kein
Rang als ein Rang aus halben Daten.

KEINE VERNETZUNG: Das Modul sendet nichts und schreibt keine Datei, die
Waechter, Scanner-Mappe oder Alarmbot lesen.

Aufruf:
  python kennzahlen_gruppen.py --selbsttest
"""

import argparse
import bisect
import json
import math
import statistics
import sys
from collections import Counter, defaultdict

import red_to_green
from config import CFG

KG = CFG["gruppen_rs"]
UNBEKANNT = "Branche unbekannt"
EBENEN = ("gics_sektor", "gics_gruppe", "gics_branche", "gics_unterbranche")
EBENE_NAME = {"gics_sektor": "GICS-Sektor", "gics_gruppe": "GICS-Branchengruppe", "gics_branche": "GICS-Branche",
              "gics_unterbranche": "GICS-Unterbranche"}
LEER = {"", "NA", "N/A", "NONE", "NULL", "-"}
GRUPPEN_FELDER = ("gruppe", "gruppe_ebene", "gruppe_rang", "gruppe_rang_3w", "gruppe_rang_6w", "gruppen_zahl",
                  "gruppe_titel", "gruppe_stand", "gruppe_zuordnung_stand", "gruppe_hinweis")


def mindest_abdeckung():
    """Dieselbe Regel wie beim RS-Universum."""
    return float(CFG["rs_universum"]["mindest_abdeckung"])


def abstaende():
    """(15, 30): drei und sechs Wochen in Handelstagen."""
    return tuple(int(k) for k in KG["rang_zurueck_tage"])


def historie_noetig():
    """Schlusskurse fuer einen vollen Rohwert: das laengste Quartal plus eins."""
    return max(red_to_green.RS_QUARTALE) + 1


def auszug_laenge():
    """So viele juengste Kurse braucht die Rechnung je Aktie; 40 Tage Rand
    fuer Tage, an denen der Aktie ein Kurs fehlt."""
    return historie_noetig() + max(abstaende()) + 40


def schluessel(ticker):
    """Eine Schreibweise fuer alle Quellen: BRK.B, BRK-B (EODHD) und BRK/B
    (Nasdaq, FINRA) werden BRK.B."""
    return str(ticker or "").strip().upper().replace("-", ".").replace("/", ".")


def _datum_text(iso):
    try:
        j, m, t = str(iso)[:10].split("-")
        return f"{t}.{m}.{j}"
    except ValueError:
        return str(iso)


def _prozent(x):
    return f"{x * 100:.1f}".replace(".", ",")


# --- Zuordnungsliste ----------------------------------------------------------

def gruppe_aus(eintrag, ebene=None):
    """Der Gruppenname eines Eintrags der Zuordnungsliste oder None."""
    if not isinstance(eintrag, dict):
        return None
    w = eintrag.get(ebene or KG["ebene"])
    if w is None:
        return None
    w = " ".join(str(w).split())
    return None if w.upper() in LEER else w


def zuordnung_lesen(pfad):
    """Die eigene Zuordnungsliste (zuordnung_bauen.py).
    -> ({Schluessel: Eintrag}, Befund mit status, stand, eintraege, grund)."""
    if not pfad:
        return None, {"status": "nicht verfuegbar", "grund": "die eigene Zuordnungsliste der Branchen liegt noch nicht vor"}
    try:
        with open(pfad, encoding="utf-8") as f:
            d = json.load(f)
    except FileNotFoundError:
        return None, {"status": "nicht verfuegbar", "grund": "die eigene Zuordnungsliste der Branchen liegt noch nicht vor"}
    except (OSError, ValueError) as e:
        return None, {"status": "nicht verfuegbar", "grund": f"die Zuordnungsliste ist nicht lesbar ({type(e).__name__})"}
    titel = d.get("titel") if isinstance(d, dict) else None
    if not isinstance(titel, dict) or not titel:
        return None, {"status": "nicht verfuegbar", "grund": "die Zuordnungsliste enthält keine Titel"}
    z = {schluessel(k): v for k, v in titel.items() if isinstance(v, dict)}
    return z, {"status": "ok", "stand": d.get("stand"), "eintraege": len(z), "quelle": d.get("quelle")}


# --- Kurse und Rohwerte --------------------------------------------------------

def kurs_auszug(voll, laenge=None):
    """Aus dem Kurs-DataFrame der Nachttabelle (Spalten datetime, close,
    aufsteigend) die juengsten Tage als (ISO-Tage, Schlusskurse)."""
    import pandas as pd
    t = voll.tail(int(laenge or auszug_laenge()))
    return (pd.to_datetime(t["datetime"]).dt.strftime("%Y-%m-%d").tolist(),
            [float(x) for x in t["close"]])


def handelstage_aus(auszuege, bis=None):
    """Tage, an denen mindestens ein Zehntel der Aktien einen Kurs hat,
    aufsteigend, bis einschliesslich bis."""
    zaehler = Counter()
    for daten, _s in auszuege.values():
        zaehler.update(set(daten))
    schwelle = max(1.0, 0.1 * len(auszuege))
    return sorted(t for t, n in zaehler.items() if n >= schwelle and (not bis or t <= str(bis)[:10]))


def stichtage(handelstage, zurueck=None):
    """{0: Handelstag, 15: vor drei Wochen, 30: vor sechs Wochen}; None, wo die
    Liste der Handelstage nicht so weit zurueckreicht."""
    tage = sorted(set(handelstage or []))
    return {k: (tage[-1 - k] if len(tage) > k else None) for k in (0,) + tuple(zurueck or abstaende())}


def rohwerte(daten, schluesse, tage):
    """{Abstand: (Rohwert oder None, zaehlt zur Basis)} einer Aktie.
    Zur Basis zaehlt, wer bis zum Stichtag die volle Historie hat; einen
    Rohwert hat, wer dazu genau am Stichtag einen Kurs hat."""
    raus = {}
    n_voll = historie_noetig()
    for k, tag in tage.items():
        if not tag:
            raus[k] = (None, False)
            continue
        bis = bisect.bisect_right(daten, tag)
        basis = bis >= n_voll
        roh = None
        if basis and daten[bis - 1] == tag:
            teil = schluesse[bis - n_voll:bis]
            if all(isinstance(x, (int, float)) and math.isfinite(x) and x > 0 for x in teil):
                roh = red_to_green.rs_rohwert(teil)
                roh = roh if (roh is not None and math.isfinite(roh)) else None
        raus[k] = (roh, basis)
    return raus


# --- Rangliste -------------------------------------------------------------------

def _wochen_text(k):
    return {15: "vor drei Wochen", 30: "vor sechs Wochen"}.get(k, f"vor {k} Handelstagen")


def gruppen_werte(auszuege, zuordnung, handelstag=None, zuordnung_befund=None, ausschluss=None, ebene=None):
    """Die ganze Rechnung.
    auszuege: {Ticker: (ISO-Tage, Schlusskurse)}; zuordnung: {Schluessel:
    Eintrag} aus zuordnung_lesen oder None; ausschluss: Ticker, die nicht in
    die Rechnung gehen (fuer Entscheidung 2).
    -> (je Aktie {Ticker: Felder}, Rangliste als Dict, Befund)."""
    ebene = ebene or KG["ebene"]
    zb = zuordnung_befund or {}
    leer = dict.fromkeys(GRUPPEN_FELDER)
    if zuordnung is None:
        grund = zb.get("grund") or "die eigene Zuordnungsliste der Branchen liegt noch nicht vor"
        return ({t: dict(leer, gruppe_hinweis=grund) for t in auszuege}, None,
                {"status": "nicht verfuegbar", "grund": grund})
    ausschluss = {schluessel(t) for t in (ausschluss or ())}
    zurueck = abstaende()
    tage_liste = handelstage_aus(auszuege, bis=handelstag)
    tage = stichtage(tage_liste, zurueck)
    zu_stand = zb.get("stand")

    gruppe_je, grund_unbekannt = {}, {}
    for t in auszuege:
        e = zuordnung.get(schluessel(t))
        g = gruppe_aus(e, ebene)
        if g is None:
            gruppe_je[t] = UNBEKANNT
            grund_unbekannt[t] = (f"die Zuordnungsliste vom {_datum_text(zu_stand)} nennt für die Aktie keine Branche"
                                  if e else f"die Aktie steht nicht in der Zuordnungsliste vom {_datum_text(zu_stand)}")
        else:
            gruppe_je[t] = g

    werte_k = {k: defaultdict(list) for k in tage}
    basis_k, vorhanden_k = Counter(), Counter()
    for t, (daten, schluesse) in auszuege.items():
        if schluessel(t) in ausschluss:
            continue
        for k, (roh, basis) in rohwerte(daten, schluesse, tage).items():
            if basis:
                basis_k[k] += 1
            if roh is not None:
                vorhanden_k[k] += 1
                werte_k[k][gruppe_je[t]].append(roh)

    mindest = mindest_abdeckung()
    raenge, mediane, abdeckung, hinweise = {}, {}, {}, {}
    for k, tag in tage.items():
        mediane[k] = {g: statistics.median(v) for g, v in werte_k[k].items()}
        a = (vorhanden_k[k] / basis_k[k]) if basis_k[k] else 0.0
        abdeckung[k] = {"tag": tag, "basis": basis_k[k], "mit_rohwert": vorhanden_k[k], "anteil": round(a, 4)}
        wort = "heute" if k == 0 else _wochen_text(k)
        if not tag:
            raenge[k] = {}
            hinweise[k] = (f"der Rang {wort} fehlt, die Kurshistorie kennt erst {len(tage_liste)} Handelstage")
            continue
        if not basis_k[k] or a < mindest:
            raenge[k] = {}
            hinweise[k] = (f"der Rang {wort} fehlt, am {_datum_text(tag)} tragen nur {_prozent(a)} Prozent der Aktien "
                           f"einen Rohwert, verlangt sind {mindest * 100:.0f}")
            continue
        echte = sorted((g for g in mediane[k] if g != UNBEKANNT), key=lambda g: (-mediane[k][g], g))
        raenge[k] = {g: i + 1 for i, g in enumerate(echte)}

    k3, k6 = zurueck[0], zurueck[-1]
    je_aktie = {}
    for t in auszuege:
        g = gruppe_je[t]
        z = dict(leer)
        z.update({"gruppe": g, "gruppe_ebene": EBENE_NAME.get(ebene, ebene), "gruppe_stand": tage.get(0),
                  "gruppe_zuordnung_stand": zu_stand, "gruppen_zahl": len(raenge[0]) or None,
                  "gruppe_titel": len(werte_k[0].get(g, [])),
                  "gruppe_rang": raenge[0].get(g), "gruppe_rang_3w": raenge[k3].get(g), "gruppe_rang_6w": raenge[k6].get(g)})
        teile = []
        if g == UNBEKANNT:
            teile.append(grund_unbekannt[t])
        else:
            for k in (0, k3, k6):
                if k in hinweise:
                    teile.append(hinweise[k])
                elif not raenge[k].get(g):
                    wort = "heute" if k == 0 else _wochen_text(k)
                    teile.append(f"der Rang {wort} fehlt, am {_datum_text(tage[k])} trug keine Aktie der Gruppe "
                                 f"einen Rohwert")
        z["gruppe_hinweis"] = "; ".join(teile) or None
        je_aktie[t] = z

    zeilen = []
    for g in sorted(set(mediane[0]) | set(mediane[k3]) | set(mediane[k6])):
        zeilen.append({"gruppe": g, "rang": raenge[0].get(g), "rang_3w": raenge[k3].get(g),
                       "rang_6w": raenge[k6].get(g), "titel": len(werte_k[0].get(g, [])),
                       "titel_3w": len(werte_k[k3].get(g, [])), "titel_6w": len(werte_k[k6].get(g, [])),
                       "median_roh": _rund(mediane[0].get(g)), "median_roh_3w": _rund(mediane[k3].get(g)),
                       "median_roh_6w": _rund(mediane[k6].get(g))})
    zeilen.sort(key=lambda z: (z["gruppe"] == UNBEKANNT, z["rang"] is None, z["rang"] or 0, z["gruppe"]))
    liste = {"stand": tage.get(0), "zuordnung_stand": zu_stand, "ebene": ebene,
             "stichtage": {"heute": tage.get(0), "vor_3_wochen": tage.get(k3), "vor_6_wochen": tage.get(k6)},
             "abdeckung": {str(k): v for k, v in abdeckung.items()}, "gruppen": zeilen}

    mit_gruppe = sum(1 for g in gruppe_je.values() if g != UNBEKANNT)
    status = "ok" if (raenge[0] and raenge[k3] and raenge[k6]) else ("teilweise" if raenge[0] else "nicht verfuegbar")
    befund = {"status": status, "zuordnung_stand": zu_stand, "zuordnung_eintraege": zb.get("eintraege"),
              "ebene": ebene, "aktien": len(auszuege), "mit_gruppe": mit_gruppe,
              "unbekannt": len(auszuege) - mit_gruppe, "gruppen_heute": len(raenge[0]),
              "stichtage": liste["stichtage"], "abdeckung": liste["abdeckung"],
              "hinweise": [hinweise[k] for k in sorted(hinweise)]}
    return je_aktie, liste, befund


def _rund(x):
    return round(x, 6) if isinstance(x, (int, float)) else None


# --- Selbsttest -------------------------------------------------------------------------

def _reihe(tage, start, schritt, fehlend=()):
    """Kuenstliche Kursreihe: steigt je Handelstag um den Faktor (1 + schritt)."""
    daten, schluesse = [], []
    x = start
    for t in tage:
        x *= (1 + schritt)
        if t in fehlend:
            continue
        daten.append(t)
        schluesse.append(round(x, 6))
    return daten, schluesse


def selbsttest() -> int:
    fehler = []

    def p(name, ok, zusatz=""):
        print(f"  {'ok  ' if ok else 'FEHL'} {name}" + (f"; {zusatz}" if zusatz else ""))
        if not ok:
            fehler.append(name)

    print("Industry Group RS, Selbsttest (ohne Netz)")
    p("Mindestabdeckung ist die des RS-Universums", mindest_abdeckung() == float(CFG["rs_universum"]["mindest_abdeckung"]))
    p("Rueckblick drei und sechs Wochen", abstaende() == (15, 30), str(abstaende()))
    p("Ebene aus der Konfiguration ist erlaubt", KG["ebene"] in EBENEN, KG["ebene"])
    p("Schreibweisen der Klassen", schluessel("brk-b") == schluessel("BRK/B") == schluessel("BRK.B") == "BRK.B")
    p("Leere Gruppen gelten als keine", gruppe_aus({"gics_unterbranche": "NA"}) is None
      and gruppe_aus({"gics_unterbranche": "  Semiconductors "}) == "Semiconductors" and gruppe_aus(None) is None)

    # 330 Handelstage, fuenf Wochentage je Woche, ohne Kalenderfeinheiten
    from datetime import date, timedelta
    tage, d = [], date(2025, 6, 2)
    while len(tage) < 330:
        if d.weekday() < 5:
            tage.append(d.isoformat())
        d += timedelta(days=1)
    st = stichtage(tage)
    p("Stichtage: juengster Tag, 15 und 30 Handelstage davor", st[0] == tage[-1] and st[15] == tage[-16] and st[30] == tage[-31])
    p("Stichtage fehlen bei zu kurzer Liste", stichtage(tage[:10])[15] is None)

    # Rohwert am Stichtag ist derselbe wie ueber die abgeschnittene Reihe
    dat, sch = _reihe(tage, 10.0, 0.001)
    r = rohwerte(dat, sch, st)
    soll15 = red_to_green.rs_rohwert(sch[:len(sch) - 15])
    p("Rohwert vor drei Wochen gleich der Formel ueber die abgeschnittene Reihe",
      r[15][1] and abs(r[15][0] - soll15) < 1e-12 and abs(r[0][0] - red_to_green.rs_rohwert(sch)) < 1e-12)
    dat_f, sch_f = _reihe(tage, 10.0, 0.001, fehlend={st[15]})
    r_f = rohwerte(dat_f, sch_f, st)
    p("Fehlt der Kurs am Stichtag: Basis ja, Rohwert nein", r_f[15] == (None, True) and r_f[0][0] is not None)
    jung_d, jung_s = _reihe(tage[-270:], 10.0, 0.001)
    r_j = rohwerte(jung_d, jung_s, st)
    p("Junge Aktie: heute voller Rohwert, vor sechs Wochen nicht in der Basis",
      r_j[0][0] is not None and r_j[30] == (None, False))

    # Drei Gruppen, eine unbekannte Aktie, eine Aktie ohne Eintrag
    auszuege = {}
    zuordnung = {}
    plan = {"STARK1": ("Semiconductors", 0.004), "STARK2": ("Semiconductors", 0.003), "STARK3": ("Semiconductors", 0.0035),
            "MITTEL1": ("Application Software", 0.002), "MITTEL2": ("Application Software", 0.0015),
            "SCHWACH1": ("Regional Banks", 0.0002), "SCHWACH2": ("Regional Banks", -0.0001),
            "OHNE": (None, 0.005), "NEU.A": ("KEIN_EINTRAG", 0.001)}
    for t, (g, schritt) in plan.items():
        auszuege[t] = _reihe(tage, 20.0, schritt)
        if g == "KEIN_EINTRAG":
            continue
        zuordnung[schluessel(t)] = {"typ": "Common Stock", "gics_unterbranche": g if g else "NA"}
    je, liste, bf = gruppen_werte(auszuege, zuordnung, handelstag=tage[-1],
                                  zuordnung_befund={"status": "ok", "stand": "2026-09-16", "eintraege": len(zuordnung)})
    p("Rangliste: staerkste Gruppe Rang 1, Reihenfolge nach Median",
      [z["gruppe"] for z in liste["gruppen"]][:3] == ["Semiconductors", "Application Software", "Regional Banks"]
      and liste["gruppen"][0]["rang"] == 1 and liste["gruppen"][2]["rang"] == 3, str([(z["gruppe"], z["rang"]) for z in liste["gruppen"]]))
    unb = [z for z in liste["gruppen"] if z["gruppe"] == UNBEKANNT]
    p("Branche unbekannt: eigene Zeile am Ende, ohne Rang, mit Zahl der Aktien",
      len(unb) == 1 and unb[0]["rang"] is None and unb[0]["titel"] == 2 and liste["gruppen"][-1]["gruppe"] == UNBEKANNT)
    p("Aktie: Gruppe, Rang heute und vor drei und sechs Wochen, Zahl der Gruppen und Aktien",
      je["STARK2"]["gruppe"] == "Semiconductors" and je["STARK2"]["gruppe_rang"] == 1 and je["STARK2"]["gruppe_rang_3w"] == 1
      and je["STARK2"]["gruppe_rang_6w"] == 1 and je["STARK2"]["gruppen_zahl"] == 3 and je["STARK2"]["gruppe_titel"] == 3
      and je["STARK2"]["gruppe_hinweis"] is None and je["STARK2"]["gruppe_zuordnung_stand"] == "2026-09-16", str(je["STARK2"]))
    p("Median ist der mittlere Rohwert der Gruppe",
      abs(liste["gruppen"][0]["median_roh"] - round(statistics.median(
          [red_to_green.rs_rohwert(auszuege[t][1]) for t in ("STARK1", "STARK2", "STARK3")]), 6)) < 1e-9)
    p("Ohne Gruppe in der Liste: Grund nennt die Liste",
      je["OHNE"]["gruppe"] == UNBEKANNT and je["OHNE"]["gruppe_rang"] is None
      and je["OHNE"]["gruppe_hinweis"] == "die Zuordnungsliste vom 16.09.2026 nennt für die Aktie keine Branche", str(je["OHNE"]))
    p("Ohne Eintrag: Klassenaktie mit Punkt, Grund nennt den Stand der Liste",
      je["NEU.A"]["gruppe"] == UNBEKANNT
      and je["NEU.A"]["gruppe_hinweis"] == "die Aktie steht nicht in der Zuordnungsliste vom 16.09.2026", str(je["NEU.A"]))
    p("Befund: Status ok, Zahl mit Gruppe und unbekannt", bf["status"] == "ok" and bf["mit_gruppe"] == 7
      and bf["unbekannt"] == 2 and bf["gruppen_heute"] == 3, str(bf))

    # Rang vor sechs Wochen anders als heute: Gruppe B holt auf
    auf = {"A1": ("Gruppe A", 0.002), "B1": ("Gruppe B", 0.0)}
    ausz2, zu2 = {}, {}
    for t, (g, s) in auf.items():
        zu2[t] = {"gics_unterbranche": g}
    ausz2["A1"] = _reihe(tage, 10.0, 0.002)
    b_dat, b_sch, x = [], [], 10.0
    for i, t in enumerate(tage):
        x *= (1.0 if i < len(tage) - 25 else 1.03)
        b_dat.append(t)
        b_sch.append(round(x, 6))
    ausz2["B1"] = (b_dat, b_sch)
    je2, liste2, _bf2 = gruppen_werte(ausz2, zu2, zuordnung_befund={"stand": "2026-09-16"})
    p("Aufsteiger: heute Rang 1, vor sechs Wochen Rang 2",
      je2["B1"]["gruppe_rang"] == 1 and je2["B1"]["gruppe_rang_6w"] == 2 and je2["A1"]["gruppe_rang_6w"] == 1,
      str({t: (z["gruppe_rang"], z["gruppe_rang_3w"], z["gruppe_rang_6w"]) for t, z in je2.items()}))

    # Mindestabdeckung: am Stichtag vor drei Wochen fehlt 10 von 20 Aktien der Kurs
    ausz3, zu3 = {}, {}
    for i in range(20):
        t = f"T{i:02d}"
        fehlend = {st[15]} if i < 10 else set()
        ausz3[t] = _reihe(tage, 10.0, 0.0005 + i * 0.0001, fehlend=fehlend)
        zu3[t] = {"gics_unterbranche": "Gruppe gerade" if i % 2 == 0 else "Gruppe ungerade"}
    je3, _l3, bf3 = gruppen_werte(ausz3, zu3, zuordnung_befund={"stand": "2026-09-16"})
    p("Mindestabdeckung: Rang vor drei Wochen fehlt mit Grund, heute und vor sechs Wochen da",
      je3["T05"]["gruppe_rang_3w"] is None and je3["T05"]["gruppe_rang"] is not None and je3["T05"]["gruppe_rang_6w"] is not None
      and bf3["status"] == "teilweise"
      and "der Rang vor drei Wochen fehlt, am " in (je3["T05"]["gruppe_hinweis"] or "")
      and "tragen nur 50,0 Prozent der Aktien einen Rohwert, verlangt sind 95" in (je3["T05"]["gruppe_hinweis"] or ""),
      str(je3["T05"]["gruppe_hinweis"]))

    # Ausschluss (Entscheidung 2) nimmt eine Aktie ganz aus der Rechnung
    je4, liste4, _b4 = gruppen_werte(auszuege, zuordnung, zuordnung_befund={"stand": "2026-09-16"},
                                     ausschluss={"STARK1", "STARK3"})
    p("Ausschluss: die Gruppe zaehlt nur noch die uebrigen Aktien", je4["STARK2"]["gruppe_titel"] == 1
      and liste4["gruppen"][0]["titel"] == 1)

    # Ohne Zuordnungsliste: alles nicht verfuegbar mit Grund
    z0, b0 = zuordnung_lesen(None)
    je0, liste0, bf0 = gruppen_werte(auszuege, z0, zuordnung_befund=b0)
    p("Ohne Zuordnungsliste: kein Wert, Grund in jeder Aktie, keine Rangliste",
      liste0 is None and bf0["status"] == "nicht verfuegbar" and je0["STARK1"]["gruppe"] is None
      and je0["STARK1"]["gruppe_hinweis"] == "die eigene Zuordnungsliste der Branchen liegt noch nicht vor")

    # Zuordnungsliste lesen: Schreibweise der Codes und kaputte Datei
    import os
    import tempfile
    ordner = tempfile.mkdtemp(prefix="gruppen_test_")
    pfad = os.path.join(ordner, "branchen.json")
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump({"stand": "2026-09-16", "quelle": "Test", "titel": {"BRK-B": {"gics_unterbranche": "Multi-Sector Holdings"}}}, f)
    zl, bl = zuordnung_lesen(pfad)
    p("Zuordnungsliste: EODHD-Schreibweise BRK-B findet BRK.B", bl["status"] == "ok" and bl["eintraege"] == 1
      and gruppe_aus(zl.get(schluessel("BRK.B"))) == "Multi-Sector Holdings")
    with open(pfad, "w", encoding="utf-8") as f:
        f.write("{kaputt")
    zk, bk = zuordnung_lesen(pfad)
    p("Kaputte Zuordnungsliste: nicht verfuegbar mit Grund", zk is None and "nicht lesbar" in bk["grund"])
    zf, bfeh = zuordnung_lesen(os.path.join(ordner, "fehlt.json"))
    p("Fehlende Zuordnungsliste: noch nicht vorhanden", zf is None and "noch nicht vor" in bfeh["grund"])
    try:
        os.remove(pfad)
        os.rmdir(ordner)
    except OSError:
        pass

    # Kursauszug aus einem DataFrame wie in der Nachttabelle
    import pandas as pd
    df = pd.DataFrame({"datetime": pd.to_datetime(tage), "close": sch})
    ad, asch = kurs_auszug(df)
    p("Kursauszug: juengste Tage als ISO und Zahlen", len(ad) == auszug_laenge() and ad[-1] == tage[-1]
      and asch[-1] == sch[-1], f"{len(ad)} Tage")

    print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles bestanden.")
    return 1 if fehler else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Industry Group RS (Etappe 6)")
    ap.add_argument("--selbsttest", action="store_true")
    a = ap.parse_args()
    if a.selbsttest:
        return selbsttest()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
