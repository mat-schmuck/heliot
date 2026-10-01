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

WAS DRINSTEHT: jede Aktie der Nachttabelle (ganzer Markt), deren RS-Linie
gegen SPY UND gegen QQQ auf dem 52-Wochen-Hoch steht, mit Schlusskurs ab
15 Dollar und Boersenwert ab 700 Millionen Dollar. Neu ist eine Aktie,
deren beide Linien am Vortag noch nicht zugleich auf dem Hoch standen
(rs_universum rechnet den Vortag aus derselben Reihe ohne den letzten Tag).
Fehlt der Vortag in der Tabelle, steht das im Bericht, und niemand wird als
neu markiert.

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


def auswahl(zeilen: list) -> tuple:
    """(Treffer, Vortag bekannt). Treffer sind Zeilen der Nachttabelle mit
    beiden Linien auf dem Hoch, Kurs und Boersenwert ueber der Grenze; je
    Treffer das Feld neu."""
    import blacklist
    gesperrt = blacklist.gesperrte()      # Gerhard, 30.09.2026, Antworten 8 und 13
    raus = []
    vortag_bekannt = False
    for z in zeilen:
        if not (_ja(z.get("rs_linie_hoch")) and _ja(z.get("rs_linie_qqq_hoch"))):
            continue
        if blacklist.schluessel(z.get("ticker")) in gesperrt:
            continue
        kurs, mk = _f(z.get("kurs")), _f(z.get("marktkap_mrd"))
        if kurs is None or kurs < KURS_MIN or mk is None or mk < MARKTKAP_MIN_MRD:
            continue
        v_spy, v_qqq = z.get("rs_linie_hoch_vortag"), z.get("rs_linie_qqq_hoch_vortag")
        if _bekannt(v_spy) and _bekannt(v_qqq):
            vortag_bekannt = True
            neu = not (_ja(v_spy) and _ja(v_qqq))
        else:
            neu = False
        raus.append(dict(z, neu=neu))
    raus.sort(key=lambda z: (not z["neu"], -(_f(z.get("rs")) or 0), str(z.get("ticker"))))
    return raus, vortag_bekannt


def absatz(nr: int, z: dict, listen_map: dict) -> str:
    import nachschlagen as ns
    name = str(ns.firmenname(z.get("name")) or "")
    name = re.sub(r"\s*\([^)]*\)", "", name).replace("(", " ").replace(")", " ").strip(" ,;") or str(z["ticker"])
    teile = [f"{nr}. {z['ticker']}, {name}" + ("; neu" if z.get("neu") else "")]
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
    stand_text = f"Stand Schluss {ns.datum_text(stand)}" if stand else "Stand des letzten Schlusses"
    if treffer:
        titel = (f"RS-Linie auf dem 52-Wochen-Hoch: {len(treffer)} Aktie" + ("n" if len(treffer) != 1 else "")
                 + (f", davon {neu} neu" if vortag_bekannt else ""))
    else:
        titel = "RS-Linie auf dem 52-Wochen-Hoch: keine Aktie"
    kopf = (f"{stand_text}; ganzer US-Markt. Aufgenommen ist jede Aktie, deren RS-Linie gegen SPY und gegen QQQ "
            f"auf dem 52-Wochen-Hoch steht, mit Kurs ab {ns.zahl(KURS_MIN)} Dollar und Börsenwert ab 700 Millionen "
            f"Dollar. Neu heißt: am Vortag standen nicht beide Linien auf dem Hoch; die neuen stehen oben.")
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
    treffer, bekannt = auswahl(zeilen)
    p("Beide Linien auf dem Hoch, Kurs ab 15, Boersenwert ab 0,7 Mrd, die Grenzen eingeschlossen",
      sorted(z["ticker"] for z in treffer) == ["ALT", "NEU", "RAND"], str([z["ticker"] for z in treffer]))
    p("Neu stehen oben, darin nach RS", [z["ticker"] for z in treffer] == ["NEU", "RAND", "ALT"]
      and bekannt, str([(z["ticker"], z["neu"]) for z in treffer]))
    titel, absaetze = bericht_bauen(zeilen, {"ALT": ["große Liste"]}, "2026-09-30")
    text = "\n".join(absaetze)
    p("Titel nennt Zahl und Neue", titel == "RS-Linie auf dem 52-Wochen-Hoch: 3 Aktien, davon 2 neu", titel)
    p("Kopf nennt Stand und Bedingungen",
      absaetze[0].startswith("Stand Schluss 30.09.2026; ganzer US-Markt.") and "gegen SPY und gegen QQQ" in absaetze[0])
    p("Absatz: Nummer, Kuerzel, Name ohne Klammer, neu",
      absaetze[1].startswith("1. NEU, Neu Corp; neu; Kurs 50,00 Dollar; RS 80"), absaetze[1])
    p("Absatz: Abstand, Boersenwert, Sektor, Wochenliste",
      "Kurs 2,0 Prozent unter dem 52-Wochen-Hoch; Börsenwert 5,0 Milliarden Dollar; Sektor Technology; "
      "auf der Wochenliste: große Liste" in absaetze[3], absaetze[3])
    ohne = [dict(z, rs_linie_hoch_vortag=None, rs_linie_qqq_hoch_vortag=None) for z in zeilen]
    titel2, abs2 = bericht_bauen(ohne, {}, "2026-09-30")
    p("Ohne Vortag: niemand neu, und das steht da",
      titel2 == "RS-Linie auf dem 52-Wochen-Hoch: 3 Aktien" and "Der Vortag fehlt" in abs2[1]
      and "; neu" not in "\n".join(abs2))
    titel3, abs3 = bericht_bauen([zeilen[2]], {}, "2026-09-30")
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
