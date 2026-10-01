#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RS-LINIEN-BERICHT: Aktien, deren RS-Linie auf dem 52-Wochen-Hoch steht
=====================================================================
Gerhards Auftrag vom 30.09.2026 abends (Antworten 6 und 7), auf meinen
Vorschlag, der die RS-Linie gegen SPY und gegen QQQ meinte:

    "Jeden Tag alle Aktien, deren RS-Linie auf dem 52-Wochen-Hoch steht.
    Neuzugaenge (erster Tag auf dem Hoch) stehen oben und sind als 'neu'
    markiert."
    "Mindestfilter: Wie beim Gap-Up-Bericht: Kurs ab 15 Dollar und
    Boersenwert ab 700 Millionen Dollar."

WAS DRINSTEHT, seit Gerhards Antwort 9 vom 01.10.2026: "Es reicht, wenn die
RS-Linie gegen EINEN der beiden Indizes auf dem 52-Wochen-Hoch steht. Bei
jeder Aktie steht, gegen welchen Index (SPY, QQQ oder beide). Aktien mit
beiden stehen zuerst, Neuzugaenge bleiben markiert." Also jede Aktie der
Nachttabelle (ganzer Markt), deren RS-Linie gegen SPY ODER gegen QQQ auf dem
52-Wochen-Hoch steht, mit Schlusskurs ab 15 Dollar und Boersenwert ab 700
Millionen Dollar; die mit beiden Linien zuerst, darin die neuen, dann nach
RS. Neu ist eine Aktie, deren Linien am Vortag beide noch nicht auf dem Hoch
standen, die also am Vortag nicht im Bericht gestanden haette (rs_universum
rechnet den Vortag aus derselben Reihe ohne den letzten Tag). Fehlt der
Vortag in der Tabelle, steht das im Bericht, und niemand wird als neu
markiert. Bis zum 01.10.2026 mussten beide Linien zugleich auf dem Hoch
stehen.

WANN: einmal je Nacht, sobald die Nachttabelle gebaut und veroeffentlicht
ist (scanner_daten.yml). Er steht nur im Reiter Berichte; reiner
Info-Bericht, kein Alarm, keine Kaufzeile.

Aufruf:
    python rslinie_bericht.py --bauen --tabelle scanner_tabelle.parquet [--trocken]
    python rslinie_bericht.py --selbsttest
"""

import os
import re
import sys

import berichte

ART = "rslinie"
KURS_MIN = 15.0
MARKTKAP_MIN_MRD = 0.7


def _f(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def _ja(x) -> bool:
    return x is True or (x is not None and not isinstance(x, str) and _f(x) == 1.0)


def _bekannt(x) -> bool:
    return x is not None and not (isinstance(x, float) and x != x)


def index_wort(z: dict) -> str:
    """Gegen welchen Index die Linie auf dem Hoch steht: beide, SPY oder QQQ."""
    spy, qqq = _ja(z.get("rs_linie_hoch")), _ja(z.get("rs_linie_qqq_hoch"))
    return "beide" if spy and qqq else ("SPY" if spy else ("QQQ" if qqq else ""))


def auswahl(zeilen: list) -> tuple:
    """(Treffer, Vortag bekannt). Treffer sind Zeilen der Nachttabelle mit der
    Linie gegen SPY oder gegen QQQ auf dem Hoch, Kurs und Boersenwert ueber
    der Grenze; je Treffer die Felder index (beide, SPY, QQQ) und neu."""
    import blacklist
    gesperrt = blacklist.gesperrte()      # Gerhard, 30.09.2026, Antworten 8 und 13
    raus = []
    vortag_bekannt = False
    for z in zeilen:
        index = index_wort(z)
        if not index:
            continue
        if blacklist.schluessel(z.get("ticker")) in gesperrt:
            continue
        kurs, mk = _f(z.get("kurs")), _f(z.get("marktkap_mrd"))
        if kurs is None or kurs < KURS_MIN or mk is None or mk < MARKTKAP_MIN_MRD:
            continue
        v_spy, v_qqq = z.get("rs_linie_hoch_vortag"), z.get("rs_linie_qqq_hoch_vortag")
        if _bekannt(v_spy) and _bekannt(v_qqq):
            vortag_bekannt = True
            neu = not (_ja(v_spy) or _ja(v_qqq))
        else:
            neu = False
        raus.append(dict(z, neu=neu, index=index))
    raus.sort(key=lambda z: (z["index"] != "beide", not z["neu"], -(_f(z.get("rs")) or 0), str(z.get("ticker"))))
    return raus, vortag_bekannt


INDEX_TEXT = {"beide": "RS-Linie auf dem Hoch gegen beide Indizes", "SPY": "RS-Linie auf dem Hoch gegen SPY",
              "QQQ": "RS-Linie auf dem Hoch gegen QQQ"}


def absatz(nr: int, z: dict, listen_map: dict) -> str:
    import nachschlagen as ns
    name = str(ns.firmenname(z.get("name")) or "")
    name = re.sub(r"\s*\([^)]*\)", "", name).replace("(", " ").replace(")", " ").strip(" ,;") or str(z["ticker"])
    teile = [f"{nr}. {z['ticker']}, {name}" + ("; neu" if z.get("neu") else "")]
    teile.append(INDEX_TEXT.get(z.get("index") or index_wort(z), "RS-Linie auf dem Hoch"))
    rs = _f(z.get("rs"))
    teile.append(f"Kurs {ns.zahl(_f(z.get('kurs')), 2)} Dollar; RS {ns.zahl(rs) if rs is not None else 'unbekannt'}")
    abst = _f(z.get("abst_hoch_1j_pct"))
    if abst is not None:
        teile.append("Kurs auf dem 52-Wochen-Hoch" if round(abst, 1) >= 0
                     else f"Kurs {ns.zahl(-abst, 1)} Prozent unter dem 52-Wochen-Hoch")
    mk = _f(z.get("marktkap_mrd"))
    teile.append(f"Börsenwert {ns._dollar_menge(mk * 1e9) if mk else 'unbekannt'}; Sektor {z.get('sektor') or 'unbekannt'}")
    auf = listen_map.get(str(z["ticker"]).upper()) or []
    teile.append("auf der Wochenliste: " + ", ".join(auf) if auf else "auf keiner Wochenliste")
    return "; ".join(teile)


def bericht_bauen(zeilen: list, listen_map: dict, stand=None) -> tuple:
    """(Titel, Absaetze)."""
    import nachschlagen as ns
    treffer, vortag_bekannt = auswahl(zeilen)
    neu = sum(1 for z in treffer if z["neu"])
    beide = sum(1 for z in treffer if z["index"] == "beide")
    stand_text = f"Stand Schluss {ns.datum_text(stand)}" if stand else "Stand des letzten Schlusses"
    if treffer:
        titel = (f"RS-Linie auf dem 52-Wochen-Hoch: {len(treffer)} Aktie" + ("n" if len(treffer) != 1 else "")
                 + f", davon {beide} gegen beide Indizes" + (f" und {neu} neu" if vortag_bekannt else ""))
    else:
        titel = "RS-Linie auf dem 52-Wochen-Hoch: keine Aktie"
    kopf = (f"{stand_text}; ganzer US-Markt. Aufgenommen ist jede Aktie, deren RS-Linie gegen SPY oder gegen QQQ "
            f"auf dem 52-Wochen-Hoch steht, mit Kurs ab {ns.zahl(KURS_MIN)} Dollar und Börsenwert ab 700 Millionen "
            f"Dollar; bei jeder steht, gegen welchen Index. Die Aktien mit beiden Linien auf dem Hoch stehen "
            f"zuerst, darin die neuen. Neu heißt: am Vortag stand keine der beiden Linien auf dem Hoch.")
    absaetze = [kopf]
    if not vortag_bekannt and treffer:
        absaetze.append("Der Vortag fehlt in dieser Nachttabelle; heute ist deshalb keine Aktie als neu markiert.")
    if treffer:
        absaetze += [absatz(i, z, listen_map) for i, z in enumerate(treffer, 1)]
    else:
        absaetze.append("Keine Aktie erfüllt heute die Bedingungen.")
    return titel, absaetze


def bauen(tabelle_pfad=None) -> tuple:
    import gapup_bericht
    df = gapup_bericht.tabelle_laden(tabelle_pfad)
    stand = None
    if "datum" in df.columns and len(df):
        stand = str(df["datum"].dropna().astype(str).max())[:10] if df["datum"].notna().any() else None
    return bericht_bauen(df.to_dict("records"), gapup_bericht.listen_je_aktie(), stand)


# ---------------------------------------------------------------------------
# Selbsttest (ohne Netz)
# ---------------------------------------------------------------------------

def selbsttest() -> int:
    fehler = []

    def p(name, ok, zusatz=""):
        print(f"  {'ok  ' if ok else 'FEHL'} {name}" + (f"; {zusatz}" if zusatz else ""))
        if not ok:
            fehler.append(name)

    print("RS-LINIEN-BERICHT, Selbsttest")
    basis = {"marktkap_mrd": 5.0, "kurs": 50.0, "rs": 90, "sektor": "Technology", "abst_hoch_1j_pct": -2.0}
    zeilen = [
        dict(basis, ticker="ALT", name="Alt Inc. - Common Stock", rs_linie_hoch=True, rs_linie_qqq_hoch=True,
             rs_linie_hoch_vortag=True, rs_linie_qqq_hoch_vortag=True, rs=95),
        dict(basis, ticker="NEU", name="Neu Corp (Ireland)", rs_linie_hoch=True, rs_linie_qqq_hoch=True,
             rs_linie_hoch_vortag=True, rs_linie_qqq_hoch_vortag=False, rs=80),
        dict(basis, ticker="SPY1", name="Nur SPY", rs_linie_hoch=True, rs_linie_qqq_hoch=False,
             rs_linie_hoch_vortag=False, rs_linie_qqq_hoch_vortag=False),
        dict(basis, ticker="BILL", name="Billig", rs_linie_hoch=True, rs_linie_qqq_hoch=True, kurs=12.0,
             rs_linie_hoch_vortag=False, rs_linie_qqq_hoch_vortag=False),
        dict(basis, ticker="KLEIN", name="Klein", rs_linie_hoch=True, rs_linie_qqq_hoch=True, marktkap_mrd=0.5,
             rs_linie_hoch_vortag=False, rs_linie_qqq_hoch_vortag=False),
        dict(basis, ticker="RAND", name="Rand", rs_linie_hoch=1.0, rs_linie_qqq_hoch=1.0, kurs=15.0, marktkap_mrd=0.7,
             rs_linie_hoch_vortag=0.0, rs_linie_qqq_hoch_vortag=0.0, rs=70),
    ]
    zeilen.append(dict(basis, ticker="QQQ1", name="Nur QQQ", rs_linie_hoch=False, rs_linie_qqq_hoch=True,
                       rs_linie_hoch_vortag=False, rs_linie_qqq_hoch_vortag=True, rs=99))
    zeilen.append(dict(basis, ticker="KEIN", name="Keine Linie", rs_linie_hoch=False, rs_linie_qqq_hoch=False,
                       rs_linie_hoch_vortag=True, rs_linie_qqq_hoch_vortag=True))
    treffer, bekannt = auswahl(zeilen)
    p("Antwort 9: eine Linie genuegt, Kurs ab 15, Boersenwert ab 0,7 Mrd, die Grenzen eingeschlossen",
      sorted(z["ticker"] for z in treffer) == ["ALT", "NEU", "QQQ1", "RAND", "SPY1"],
      str([z["ticker"] for z in treffer]))
    p("Antwort 9: beide Linien zuerst, darin die neuen, dann nach RS",
      [z["ticker"] for z in treffer] == ["RAND", "ALT", "NEU", "SPY1", "QQQ1"] and bekannt,
      str([(z["ticker"], z["index"], z["neu"]) for z in treffer]))
    p("Antwort 9: neu ist nur, wer am Vortag mit keiner Linie auf dem Hoch stand; NEU stand gegen SPY schon da",
      {z["ticker"]: z["neu"] for z in treffer} == {"NEU": False, "RAND": True, "ALT": False, "SPY1": True,
                                                    "QQQ1": False},
      str({z["ticker"]: z["neu"] for z in treffer}))
    titel, absaetze = bericht_bauen(zeilen, {"ALT": ["große Liste"]}, "2026-09-30")
    text = "\n".join(absaetze)
    p("Titel nennt Zahl, beide Indizes und Neue",
      titel == "RS-Linie auf dem 52-Wochen-Hoch: 5 Aktien, davon 3 gegen beide Indizes und 2 neu", titel)
    p("Kopf nennt Stand und Bedingungen",
      absaetze[0].startswith("Stand Schluss 30.09.2026; ganzer US-Markt.") and "gegen SPY oder gegen QQQ" in absaetze[0]
      and "gegen welchen Index" in absaetze[0])
    p("Absatz: Nummer, Kuerzel, Name ohne Klammer, Index, Kurs",
      absaetze[3].startswith("3. NEU, Neu Corp; RS-Linie auf dem Hoch gegen beide Indizes; Kurs 50,00 Dollar; RS 80"),
      absaetze[3])
    p("Absatz: ein neuer, und je Aktie der Index",
      absaetze[1].startswith("1. RAND, Rand; neu; RS-Linie auf dem Hoch gegen beide Indizes;")
      and absaetze[4].startswith("4. SPY1, Nur SPY; neu; RS-Linie auf dem Hoch gegen SPY;")
      and absaetze[5].startswith("5. QQQ1, Nur QQQ; RS-Linie auf dem Hoch gegen QQQ;"), absaetze[4])
    p("Absatz: Abstand, Boersenwert, Sektor, Wochenliste",
      "Kurs 2,0 Prozent unter dem 52-Wochen-Hoch; Börsenwert 5,0 Milliarden Dollar; Sektor Technology; "
      "auf der Wochenliste: große Liste" in absaetze[2], absaetze[2])
    ohne = [dict(z, rs_linie_hoch_vortag=None, rs_linie_qqq_hoch_vortag=None) for z in zeilen]
    titel2, abs2 = bericht_bauen(ohne, {}, "2026-09-30")
    p("Ohne Vortag: niemand neu, und das steht da",
      titel2 == "RS-Linie auf dem 52-Wochen-Hoch: 5 Aktien, davon 3 gegen beide Indizes" and "Der Vortag fehlt" in abs2[1]
      and "; neu" not in "\n".join(abs2))
    titel3, abs3 = bericht_bauen([zeilen[-1]], {}, "2026-09-30")
    p("Ohne Treffer ehrlich", titel3 == "RS-Linie auf dem 52-Wochen-Hoch: keine Aktie"
      and abs3[-1] == "Keine Aktie erfüllt heute die Bedingungen.")
    p("Keine Klammer, kein Gedankenstrich, kein senkrechter Strich",
      not re.search(r"[()–—|]", text + titel))
    print("\nAlles bestanden." if not fehler else f"\n{len(fehler)} Fehler.")
    return 1 if fehler else 0


def main() -> int:
    a = sys.argv[1:]
    if "--selbsttest" in a:
        return selbsttest()
    if "--bauen" in a:
        if "--trocken" in a:
            os.environ[berichte.TROCKEN_ENV] = "1"
        pfad = a[a.index("--tabelle") + 1] if "--tabelle" in a else None
        titel, absaetze = bauen(pfad)
        print(titel)
        for x in absaetze:
            print(x)
        return 0 if berichte.ablegen(ART, titel, absaetze) else 1
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
