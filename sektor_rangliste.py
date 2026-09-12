#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SEKTOR-RANGLISTE: die 36 Branchen-ETFs nach Staerke
====================================================
Gerhards Antworten R12 bis R17 vom 12.09.2026. Reine Anzeige, kein
Filter, "auch spaeter nicht ohne neue Entscheidung" (R17).

  R12  Dieselben 36 ETFs wie beim Sektor-Radar (sektor_radar.ETF_UNIVERSE).
  R13  Der Hauptrang kommt aus dem FABER-MITTEL: Mittel der Renditen ueber
       1, 3, 6, 9 und 12 Monate (21, 63, 126, 189 und 252 Handelstage).
       Daneben steht der Rang vor 3 und vor 6 Wochen, wie IBD es zeigt.
  R14  Zusaetzlich eine FRUEHE Aufsteiger-Meldung auf Drei-Monats-Basis
       (Rang nach der 63-Tage-Rendite), getrennt vom Hauptrang.
  R15  Jeden Morgen die drei groessten Aufsteiger (Rangaenderung ueber
       drei Wochen); gemeldet vom Waechter mit der ersten Meldung.
  R16  Rang plus RS-Linie gegen SPY und QQQ mit der Aenderung ueber 1, 4
       und 12 Wochen.
  Selbsttest (R14): Ein kuenstlicher Sektor, der ab morgen 1 Prozent je
  Tag steigt, muss binnen elf Handelstagen unter die ersten fuenf kommen.

Die Kurse kommen ueber die bestehende Kursquelle des Scanners
(pattern_scanner.fetch_history, splitbereinigt, nicht dividendenbereinigt).

Aufruf:
  python sektor_rangliste.py --bauen        im Nachtscan, schreibt sektor_rangliste.json
  python sektor_rangliste.py --selbsttest   ohne Netz
"""

import argparse
import json
import sys
from datetime import date, datetime

from config import CFG

CFGS = CFG["sektor_rangliste"]
DATEI = "sektor_rangliste.json"


def etf_namen():
    """{Kuerzel: Name} der 36 ETFs, aus dem Radar."""
    import sektor_radar
    u = sektor_radar.ETF_UNIVERSE
    if isinstance(u, dict):
        return {k: (v if isinstance(v, str) else str(v)) for k, v in u.items()}
    return {k: k for k in u}


# ---------------------------------------------------------------------------
# Rechnen
# ---------------------------------------------------------------------------

def rendite(closes, tage, versatz=0):
    """Kurs vor versatz Tagen geteilt durch den Kurs tage davor, minus 1."""
    n = len(closes)
    if n < tage + versatz + 1:
        return None
    a, b = closes[-1 - versatz], closes[-1 - versatz - tage]
    return (a / b - 1) if b > 0 else None


def faber(closes, versatz=0, monate_tage=None):
    """Faber-Mittel: Mittel der Renditen ueber die Fenster; None, wenn
    eines fehlt."""
    monate_tage = monate_tage or CFGS["monate_tage"]
    werte = [rendite(closes, t, versatz) for t in monate_tage]
    if any(w is None for w in werte):
        return None
    return sum(werte) / len(werte)


def raenge(werte):
    """{etf: Rang}, 1 = staerkster. Gleiche Werte bekommen denselben Rang
    (die kleinere Zahl); None bleibt None."""
    gueltig = {k: v for k, v in werte.items() if v is not None}
    raus = {}
    for k, v in gueltig.items():
        raus[k] = 1 + sum(1 for w in gueltig.values() if w > v)
    for k in werte:
        raus.setdefault(k, None)
    return raus


def linie_aenderung(closes, index, wochen):
    """Aenderung der RS-Linie (ETF durch Index) ueber wochen mal fuenf
    Handelstage, in Prozent; None bei zu kurzer Reihe."""
    n = min(len(closes), len(index))
    if n < wochen * 5 + 1:
        return None
    c, i = closes[-n:], index[-n:]
    heute = c[-1] / i[-1] if i[-1] > 0 else None
    damals = c[-1 - wochen * 5] / i[-1 - wochen * 5] if i[-1 - wochen * 5] > 0 else None
    if not heute or not damals:
        return None
    return round((heute / damals - 1) * 100, 2)


def rangliste(kurse, indizes=None, namen=None, cfg=None):
    """kurse: {etf: [closes]} chronologisch; indizes: {name: [closes]}.
    Rueckgabe: Liste je ETF, nach Hauptrang sortiert."""
    cfg = cfg or CFGS
    namen = namen or {}
    zurueck = list(cfg["rang_zurueck_tage"])
    f_heute = {e: faber(c, 0, cfg["monate_tage"]) for e, c in kurse.items()}
    f_zurueck = {t: {e: faber(c, t, cfg["monate_tage"]) for e, c in kurse.items()} for t in zurueck}
    r_heute = raenge(f_heute)
    r_zurueck = {t: raenge(f_zurueck[t]) for t in zurueck}
    ft = int(cfg["frueh_fenster_tage"])
    r3m = raenge({e: rendite(c, ft, 0) for e, c in kurse.items()})
    r3m_vor = raenge({e: rendite(c, ft, 5) for e, c in kurse.items()})
    liste = []
    for e, c in kurse.items():
        z = {"etf": e, "name": namen.get(e, e), "faber_pct": (round(f_heute[e] * 100, 2) if f_heute[e] is not None else None),
             "rang": r_heute[e], "tage": len(c)}
        for t in zurueck:
            z[f"rang_vor_{t}t"] = r_zurueck[t][e]
        r_alt = r_zurueck[int(cfg["aufsteiger_fenster_tage"])][e] if int(cfg["aufsteiger_fenster_tage"]) in r_zurueck else None
        z["aenderung_3w"] = (r_alt - r_heute[e]) if (r_alt is not None and r_heute[e] is not None) else None
        z["rang_3m"] = r3m[e]
        z["rang_3m_vor_1w"] = r3m_vor[e]
        for n, idx in (indizes or {}).items():
            kurz = n.lstrip("^").lower()
            for w in cfg["linie_wochen"]:
                z[f"linie_{kurz}_{w}w"] = linie_aenderung(c, idx, int(w))
        liste.append(z)
    liste.sort(key=lambda z: (z["rang"] is None, z["rang"] or 0, z["etf"]))
    return liste


def aufsteiger(liste, gedaechtnis, heute, cfg=None):
    """R15: Welche Sektoren sind heute zu melden? Eintritt in die ersten
    fuenf oder Aufstieg um mindestens fuenf Raenge in drei Wochen, je
    Sektor EINMAL je Ereignis (das Gedaechtnis merkt den Zustand).
    Rueckgabe (meldungen, gedaechtnis_neu)."""
    cfg = cfg or CFGS
    top = int(cfg["aufsteiger_top"])
    schritt = int(cfg["aufsteiger_raenge"])
    g = dict(gedaechtnis or {})
    meldungen = []
    for z in liste:
        e = z["etf"]
        m = dict(g.get(e) or {})
        rang, alt = z.get("rang"), z.get(f"rang_vor_{int(cfg['aufsteiger_fenster_tage'])}t")
        if rang is None:
            continue
        # Eintritt in die ersten fuenf: gemeldet, wenn er drin ist und
        # zuletzt nicht als drin gemeldet war.
        drin = rang <= top
        if drin and not m.get("top_gemeldet"):
            # Beim allerersten Lauf (kein Gedaechtnis) zaehlt nur, wer vor
            # drei Wochen noch draussen war; danach jeder Wiedereintritt.
            if m.get("top_bekannt") or alt is None or alt > top:
                meldungen.append({"etf": e, "name": z["name"], "art": "eintritt",
                                  "rang": rang, "rang_vor_3w": alt, "aenderung_3w": z.get("aenderung_3w")})
            m["top_gemeldet"] = True
        if not drin:
            m["top_gemeldet"] = False
        # Aufstieg um mindestens fuenf Raenge in drei Wochen, einmal je Episode
        a = z.get("aenderung_3w")
        if a is not None and a >= schritt:
            if not m.get("aufstieg_gemeldet"):
                meldungen.append({"etf": e, "name": z["name"], "art": "aufstieg",
                                  "rang": rang, "rang_vor_3w": alt, "aenderung_3w": a})
                m["aufstieg_gemeldet"] = True
        else:
            m["aufstieg_gemeldet"] = False
        m["top_bekannt"] = True
        m["stand"] = heute.isoformat() if hasattr(heute, "isoformat") else str(heute)
        g[e] = m
    return meldungen, g


def fruehe_aufsteiger(liste, gedaechtnis, heute, cfg=None):
    """R14: auf Drei-Monats-Basis in die ersten fuenf gekommen (vor einer
    Woche noch nicht), je Sektor einmal je Episode."""
    cfg = cfg or CFGS
    top = int(cfg["aufsteiger_top"])
    g = dict(gedaechtnis or {})
    meldungen = []
    for z in liste:
        e = z["etf"]
        m = dict(g.get(e) or {})
        r, r_alt = z.get("rang_3m"), z.get("rang_3m_vor_1w")
        if r is None:
            continue
        if r <= top and not m.get("frueh_gemeldet"):
            if m.get("frueh_bekannt") or r_alt is None or r_alt > top:
                meldungen.append({"etf": e, "name": z["name"], "art": "frueh",
                                  "rang_3m": r, "rang_3m_vor_1w": r_alt, "rang": z.get("rang")})
            m["frueh_gemeldet"] = True
        if r > top:
            m["frueh_gemeldet"] = False
        m["frueh_bekannt"] = True
        g[e] = m
    return meldungen, g


def groesste_aufsteiger(liste, anzahl=3):
    """R15: die drei groessten Aufsteiger der letzten drei Wochen."""
    kand = [z for z in liste if z.get("aenderung_3w") is not None and z["aenderung_3w"] > 0]
    kand.sort(key=lambda z: (-z["aenderung_3w"], z["rang"] or 99))
    return kand[:anzahl]


# ---------------------------------------------------------------------------
# Texte
# ---------------------------------------------------------------------------

def text_fuer(z, mit_linie=True):
    """Eine Zeile je Sektor: Rang, Ranghistorie, RS-Linie (R16)."""
    n = 36
    teile = [f"{z['name']} ({z['etf']}) Rang {z['rang']} von {n}" if z.get("rang") else f"{z['name']} ({z['etf']}) ohne Rang"]
    v3, v6 = z.get("rang_vor_15t"), z.get("rang_vor_30t")
    if v3 or v6:
        teile.append(f"vor 3 Wochen {v3 if v3 else 'ohne'}, vor 6 Wochen {v6 if v6 else 'ohne'}")
    if mit_linie:
        for kurz, name in (("spy", "SPY"), ("qqq", "QQQ")):
            w = [z.get(f"linie_{kurz}_{x}w") for x in (1, 4, 12)]
            if all(v is not None for v in w):
                teile.append(f"RS-Linie gegen {name} {w[0]:+.1f} % über 1 Woche, {w[1]:+.1f} % über 4, "
                             f"{w[2]:+.1f} % über 12".replace(".", ","))
    return "; ".join(teile)


def aufsteiger_text(m):
    if m["art"] == "eintritt":
        return (f"{m['name']} ({m['etf']}) neu unter den ersten fünf, Rang {m['rang']}"
                + (f", vor 3 Wochen {m['rang_vor_3w']}" if m.get("rang_vor_3w") else ""))
    if m["art"] == "aufstieg":
        return (f"{m['name']} ({m['etf']}) um {m['aenderung_3w']} Ränge gestiegen in 3 Wochen, "
                f"jetzt Rang {m['rang']}")
    return (f"{m['name']} ({m['etf']}) früher Aufsteiger auf Drei-Monats-Basis, Rang {m['rang_3m']} "
            f"nach drei Monaten" + (f", vor 1 Woche {m['rang_3m_vor_1w']}" if m.get("rang_3m_vor_1w") else "")
            + (f"; Hauptrang {m['rang']}" if m.get("rang") else ""))


def sektor_zeile(ticker, daten=None):
    """Fuer Meldungen zu einer AKTIE: der Rang ihres Sektor-ETFs, aus dem
    Finviz-Sektor der Wochenlisten. Leer, wenn nicht zuordenbar."""
    try:
        import listen
        import beobachtungen
        etf = beobachtungen.sektor_etf_fuer(listen.sektor_von(ticker))
    except Exception:  # noqa
        return ""
    if not etf:
        return ""
    d = daten if daten is not None else lies()
    z = next((x for x in d.get("liste", []) if x.get("etf") == etf), None)
    if not z or not z.get("rang"):
        return ""
    v3 = z.get("rang_vor_15t")
    return f"Sektor {z['name']} ({etf}) Rang {z['rang']} von 36" + (f", vor 3 Wochen {v3}" if v3 else "")


# ---------------------------------------------------------------------------
# Bauen und lesen
# ---------------------------------------------------------------------------

def _closes(df):
    try:
        return [float(x) for x in df["close"].tolist()]
    except Exception:  # noqa
        return []


def lade_kurse(leise=True):
    """ETF-Kurse ueber den Radar (dieselbe Kursquelle), Indizes ueber
    denselben Sammelabruf. Rueckgabe ({etf: closes}, {index: closes}, tag)."""
    import sektor_radar
    import pattern_scanner as ps
    daten = sektor_radar.lade_etf_kurse(leise=leise)
    kurse = {e: _closes(df) for e, df in daten.items() if len(df)}
    indizes = {}
    limiter = ps.RateLimiter(8)
    ps.lade_yahoo_sammelabruf(list(CFGS["indizes"]))
    for n in CFGS["indizes"]:
        try:
            df = ps.fetch_history(n, None, limiter)
        except Exception:  # noqa
            df = None
        if df is not None and len(df):
            indizes[n] = _closes(df)
    tag = sektor_radar._letzter_handelstag(daten)
    return kurse, indizes, tag


def bauen(pfad=DATEI, leise=False, kurse=None, indizes=None, tag=None, heute=None):
    if kurse is None:
        kurse, indizes, tag = lade_kurse(leise=leise)
    heute = heute or date.today()
    alt = lies(pfad)
    liste = rangliste(kurse, indizes, etf_namen() if kurse and not all(k.startswith("K") for k in kurse) else None)
    meld, g1 = aufsteiger(liste, alt.get("gedaechtnis", {}), heute)
    frueh, g2 = fruehe_aufsteiger(liste, g1, heute)
    inhalt = {"gebaut_am": datetime.now().isoformat(timespec="seconds"), "handelstag": tag,
              "geladen": len(kurse), "liste": liste, "aufsteiger": meld, "frueh": frueh,
              "groesste_aufsteiger": groesste_aufsteiger(liste), "gedaechtnis": g2,
              "aufsteiger_gemeldet": alt.get("aufsteiger_gemeldet", {})}
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(inhalt, f, ensure_ascii=False, indent=1)
    if not leise:
        print(f"Sektor-Rangliste: {len(kurse)} ETFs, {len(meld)} Aufsteiger, {len(frueh)} fruehe; "
              f"Spitze: " + ", ".join(f"{z['etf']} {z['rang']}" for z in liste[:5]))
    return inhalt


def lies(pfad=DATEI):
    try:
        with open(pfad, encoding="utf-8-sig") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

def _reihe(seed, tage=320, drift=0.0003, streuung=0.012, start=100.0):
    import random
    r = random.Random(seed)
    k, raus = start, []
    for _ in range(tage):
        k = max(1.0, k * (1 + drift + r.gauss(0, streuung)))
        raus.append(k)
    return raus


def selbsttest() -> int:
    fehler = []

    def p(name, ok, zusatz=""):
        print(f"  {'ok  ' if ok else 'FEHL'} {name}" + (f" — {zusatz}" if zusatz else ""))
        if not ok:
            fehler.append(name)

    print("Sektor-Rangliste, Selbsttest (ohne Netz)")
    p("Rendite: 10 Tage zurueck", abs(rendite([100.0] * 10 + [110.0], 10) - 0.1) < 1e-9
      and rendite([1.0, 2.0], 5) is None)
    c = [100.0 * (1.001 ** i) for i in range(300)]
    f = faber(c)
    p("Faber-Mittel ist das Mittel der fuenf Renditen",
      f is not None and abs(f - sum(1.001 ** t - 1 for t in CFGS["monate_tage"]) / 5) < 1e-9)
    p("Raenge: 1 ist der staerkste, Gleichstand teilt den Rang, None bleibt None",
      raenge({"A": 0.3, "B": 0.1, "C": 0.3, "D": None}) == {"A": 1, "B": 3, "C": 1, "D": None})

    kurse = {f"K{i:02d}": _reihe(i, drift=0.0001 + (i % 6) * 0.0002) for i in range(36)}
    idx = {"SPY": _reihe(500), "QQQ": _reihe(501)}
    liste = rangliste(kurse, idx, {k: k for k in kurse})
    p("Rangliste: 36 Zeilen, Raenge 1 bis 36, sortiert",
      len(liste) == 36 and [z["rang"] for z in liste] == list(range(1, 37)))
    p("Jede Zeile traegt Rang vor 3 und 6 Wochen, Drei-Monats-Rang und RS-Linien ueber 1, 4, 12 Wochen",
      all(z.get("rang_vor_15t") and z.get("rang_vor_30t") and z.get("rang_3m") for z in liste)
      and all(z.get("linie_spy_12w") is not None and z.get("linie_qqq_1w") is not None for z in liste))

    # Kuenstlicher Sektor (R14): Von Anfang an 1 Prozent je Tag heisst Rang 1
    # auf jeder Basis. Steigt er erst AB MORGEN, waehrend die anderen still
    # stehen, darf die Drei-Monats-Basis ihn nicht SPAETER unter die ersten
    # fuenf bringen als das Faber-Mittel, und beide muessen es binnen 63
    # Handelstagen schaffen. (Mit echter Sektorstreuung braucht ein
    # Nachzuegler beim Faber-Mittel Wochen; genau deshalb gibt es R14.)
    basis = {k: v[:] for k, v in kurse.items()}
    n_k = len(next(iter(basis.values())))
    voll = dict(basis)
    voll["KUENSTLICH"] = [100.0 * 1.01 ** i for i in range(n_k)]
    r_voll = rangliste(voll, {}, {k: k for k in voll})
    kz = next(z for z in r_voll if z["etf"] == "KUENSTLICH")
    p("Kuenstlicher Sektor mit 1 Prozent je Tag von Anfang an hat Rang 1 nach Faber und nach drei Monaten",
      kz["rang"] == 1 and kz["rang_3m"] == 1, f"{kz['rang']} und {kz['rang_3m']}")
    schwach = max(liste, key=lambda z: z["rang"])["etf"]
    tag_faber, tag_3m = None, None
    ft = int(CFGS["frueh_fenster_tage"])
    for t in range(1, 80):
        test = {k: (v + [v[-1]] * t) for k, v in basis.items()}
        s = basis[schwach]
        test[schwach] = s + [s[-1] * (1.01 ** i) for i in range(1, t + 1)]
        rf = raenge({e: faber(cc) for e, cc in test.items()})
        r3 = raenge({e: rendite(cc, ft, 0) for e, cc in test.items()})
        if tag_faber is None and rf[schwach] is not None and rf[schwach] <= 5:
            tag_faber = t
        if tag_3m is None and r3[schwach] is not None and r3[schwach] <= 5:
            tag_3m = t
        if tag_faber and tag_3m:
            break
    p("Der schwaechste Sektor, der ab morgen 1 Prozent je Tag steigt, kommt auf Drei-Monats-Basis nicht spaeter "
      "unter die ersten fuenf als nach Faber, beide binnen 63 Handelstagen (R14)",
      tag_3m is not None and tag_faber is not None and tag_3m <= tag_faber <= 63,
      f"drei Monate {tag_3m} Tage, Faber {tag_faber} Tage")

    m, g = aufsteiger(liste, {}, date(2026, 9, 12))
    p("Aufsteiger: beim ersten Lauf werden Eintritte nur gemeldet, wenn der Sektor vor 3 Wochen draussen war",
      all(x["art"] in ("eintritt", "aufstieg") for x in m))
    m2, g2 = aufsteiger(liste, g, date(2026, 9, 13))
    p("Dasselbe Ereignis wird nicht zweimal gemeldet", not m2)
    # Ein Sektor faellt heraus und kommt wieder: neue Meldung
    liste2 = [dict(z) for z in liste]
    erster = liste2[0]["etf"]
    for z in liste2:
        if z["etf"] == erster:
            z["rang"] = 10
    m3, g3 = aufsteiger(liste2, g2, date(2026, 9, 14))
    m4, g4 = aufsteiger(liste, g3, date(2026, 9, 15))
    p("Nach dem Herausfallen wird der Wiedereintritt erneut gemeldet",
      any(x["etf"] == erster and x["art"] == "eintritt" for x in m4), [x["etf"] for x in m4])
    fr, g5 = fruehe_aufsteiger(liste, {}, date(2026, 9, 12))
    p("Fruehe Aufsteiger tragen die Kennzeichnung frueh", all(x["art"] == "frueh" for x in fr))
    ga = groesste_aufsteiger(liste)
    p("Die drei groessten Aufsteiger, absteigend", len(ga) <= 3
      and all(ga[i]["aenderung_3w"] >= ga[i + 1]["aenderung_3w"] for i in range(len(ga) - 1)))
    t = text_fuer(liste[0])
    p("Text ohne Gedankenstrich und senkrechten Strich, mit Rang und RS-Linien",
      "–" not in t and "|" not in t and "Rang 1 von 36" in t and "RS-Linie gegen SPY" in t, t)
    p("Aufsteiger-Texte", all(aufsteiger_text(x) for x in m + fr))

    import tempfile, os
    pfad = os.path.join(tempfile.mkdtemp(), "s.json")
    inhalt = bauen(pfad=pfad, leise=True, kurse=kurse, indizes=idx, tag="2026-09-12", heute=date(2026, 9, 12))
    p("Datei: Liste, Aufsteiger, groesste Aufsteiger und Gedaechtnis",
      lies(pfad).get("liste") and "gedaechtnis" in lies(pfad) and "groesste_aufsteiger" in inhalt)

    print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles bestanden.")
    return 1 if fehler else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Sektor-Rangliste der 36 Branchen-ETFs.")
    ap.add_argument("--bauen", action="store_true")
    ap.add_argument("--ausgabe", default=DATEI)
    ap.add_argument("--selbsttest", action="store_true")
    args = ap.parse_args()
    if args.selbsttest:
        return selbsttest()
    if args.bauen:
        bauen(pfad=args.ausgabe)
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
