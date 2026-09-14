#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SHORT-VOLUMEN AUS DER FINRA-TAGESDATEI (Etappe 7, Gerhards Entscheidung 12)
==========================================================================
Gerhard, 13.09.2026: "E12 BEIDES: FINRA-Tagesdatei Short-Volumen-Anteil und
Short Interest ueber die Nasdaq-Kurzabfrage; dieselbe Mindestabdeckungs-Regel
wie beim RS-Universum, lieber 'nicht verfuegbar' als halbe Daten."

Dieses Modul baut den ersten Teil, den Short-Volumen-Anteil. Reine Anzeige,
nichts filtert. Die Werte liegen wie die Analystenwerte im privaten Datenrepo
(scanner_analysten.parquet).

QUELLE (gelesen am 14.09.2026)
  FINRA "Daily Short Sale Volume Files", Datei "Consolidated NMS" je
  Handelstag unter cdn.finra.org/equity/regsho/daily/CNMSshvolJJJJMMTT.txt,
  ohne Schluessel, laut FINRA spaetestens um 18:00 New Yorker Zeit desselben
  Tages. Aufbau laut FINRA-Formatvorlage: Kopfzeile
  Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market, je Wertpapier
  eine Zeile, als letzte Zeile die Zahl der Datensaetze; ein Tag ohne Daten
  hat nur Kopf und Schlusszeile mit 0. ShortVolume enthaelt die
  Short-Exempt-Umsaetze. Gemessen: Seit einiger Zeit stehen die Volumen mit
  Nachkommastellen (Bruchstuecke von Aktien), obwohl die Vorlage "no decimals"
  sagt; Klassen heissen dort BRK/B statt BRK.B.
  Die Zahlen erfassen NUR ausserboerslich gemeldete Umsaetze (FINRA TRF und
  ADF) waehrend der regulaeren Handelszeit, nicht die Boersen; FINRA schreibt
  selbst, dass nicht verbreitete Umsaetze fehlen, was den Anteil hoeher
  erscheinen laesst, und dass die Datei nicht dem Short Interest entspricht.
  Nutzung laut FINRA frei fuer nicht gewerbliche Zwecke.

WAS GERECHNET WIRD
  Anteil am Tag       ShortVolume geteilt durch TotalVolume des juengsten
                      Handelstags, in Prozent.
  Anteil ueber 20     Summe ShortVolume geteilt durch Summe TotalVolume ueber
  Handelstage         die letzten 20 Handelstage (volumengewichtet, nicht das
                      Mittel der Tagesanteile); dazu, an wie vielen Tagen die
                      Aktie ausserboerslich gehandelt wurde.
  Vergleich           der Median des Tagesanteils ueber alle Aktien des
                      Universums mit Umsatz an diesem Tag (gemessen: 52,6
                      Prozent am 11.09.2026, 51,8 am 14.09.2026). Ein Anteil
                      um die Haelfte ist also der Normalfall, weil Market Maker
                      beim Handel leer verkaufen.

MINDESTABDECKUNG, wie beim RS-Universum (Teil 6, Regel 1): Eine Tagesdatei
zaehlt nur, wenn sie vollstaendig ist (Schlusszeile gleich Zahl der Zeilen,
Datum passend) und mindestens so viele Aktien des Universums fuehrt, wie die
Mindestabdeckung des RS-Universums verlangt (95 Prozent; gemessen am
11.09.2026 99,2, am 14.09.2026 99,4 Prozent). Fehlt die Datei des juengsten
Handelstags oder faellt sie durch, tragen ALLE Aktien "nicht verfuegbar";
fehlt einer der 20 Tage, gilt das fuer den 20-Tage-Wert. Werte der Vornacht
werden nicht weitergetragen. Ob ein Tag ein Handelstag ist, sagt die
Kurshistorie der Nachttabelle, nicht der Kalender.

KEINE VERNETZUNG: Das Modul sendet nichts und schreibt keine Datei, die
Waechter, Scanner-Mappe oder Alarmbot lesen.

Aufruf:
  python kennzahlen_short.py --selbsttest
"""

import argparse
import statistics
import sys
import time
from datetime import date

from config import CFG

KS = CFG["short_daten"]
FINRA_TAGES_URL = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{}.txt"
KOPF = ["Date", "Symbol", "ShortVolume", "ShortExemptVolume", "TotalVolume"]
SHORT_FELDER = ("short_stand", "short_anteil_pct", "short_volumen", "short_gesamtvolumen", "short_anteil_20t_pct",
                "short_tage_20t", "short_median_pct", "short_hinweis")


def mindest_abdeckung():
    """Dieselbe Regel wie beim RS-Universum (Entscheidung 12)."""
    return float(CFG["rs_universum"]["mindest_abdeckung"])


def finra_symbol(ticker):
    """BRK.B heisst in der FINRA-Tagesdatei BRK/B."""
    return str(ticker or "").strip().upper().replace(".", "/")


def tagesdatei_lesen(text, tag=None):
    """({Symbol: (short, exempt, gesamt)}, Befund). Befund: gueltig, grund,
    zeilen, datum. tag: ISO-Datum, das die Datei tragen muss."""
    zeilen = [z for z in str(text or "").splitlines() if z.strip()]
    if not zeilen:
        return {}, {"gueltig": False, "grund": "leere Datei"}
    if zeilen[0].strip().split("|")[:5] != KOPF:
        return {}, {"gueltig": False, "grund": "die Kopfzeile passt nicht zur Formatvorlage"}
    schluss = zeilen[-1].strip()
    if not schluss.isdigit():
        return {}, {"gueltig": False, "grund": "die Schlusszeile fehlt, die Datei ist abgeschnitten"}
    daten, datum, unlesbar = {}, None, 0
    for z in zeilen[1:-1]:
        t = z.split("|")
        if len(t) < 5:
            unlesbar += 1
            continue
        try:
            short, exempt, gesamt = float(t[2]), float(t[3]), float(t[4])
        except ValueError:
            unlesbar += 1
            continue
        datum = datum or t[0].strip()
        daten[t[1].strip()] = (short, exempt, gesamt)
    n = len(zeilen) - 2
    if int(schluss) != n:
        return {}, {"gueltig": False, "grund": f"die Schlusszeile nennt {int(schluss)} Zeilen, die Datei hat {n}"}
    if tag and datum and datum != str(tag).replace("-", ""):
        return {}, {"gueltig": False, "grund": f"die Datei trägt das Datum {_datum_text(f'{datum[:4]}-{datum[4:6]}-{datum[6:8]}')}"
                                               f" statt {_datum_text(tag)}"}
    return daten, {"gueltig": True, "zeilen": n, "unlesbar": unlesbar,
                   "datum": f"{datum[:4]}-{datum[4:6]}-{datum[6:8]}" if datum and len(datum) == 8 else None}


def abdeckung(daten, ticker_liste):
    """Anteil der Aktien des Universums, die in der Tagesdatei stehen."""
    liste = list(ticker_liste or [])
    if not liste:
        return 0.0
    return sum(1 for s in liste if finra_symbol(s) in daten) / len(liste)


def tagesdatei_holen(tag):
    """(HTTP-Status oder Fehlername, Text). tag: ISO-Datum."""
    import urllib.error
    import urllib.request
    url = FINRA_TAGES_URL.format(str(tag).replace("-", ""))
    anfrage = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    for versuch in (1, 2):
        try:
            with urllib.request.urlopen(anfrage, timeout=float(KS["abruf_zeitlimit_s"])) as a:
                return a.status, a.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return e.code, ""
            fehler = e.code
        except Exception as e:  # noqa
            fehler = type(e).__name__
        if versuch == 1:
            time.sleep(5)
    return fehler, ""


def _datum_text(iso):
    s = str(iso or "")
    return f"{s[8:10]}.{s[5:7]}.{s[0:4]}" if len(s) >= 10 else s


def short_werte(ticker_liste, handelstage, holen=None):
    """({Ticker: Felder SHORT_FELDER}, Befund) fuer die Aktien des Universums.
    handelstage: aufsteigende ISO-Daten der Handelstage bis zum Handelstag der
    Nachttabelle, laut Kurshistorie."""
    holen = holen or tagesdatei_holen
    fenster = int(KS["fenster_tage"])
    mindest = mindest_abdeckung()
    tage = sorted(set(handelstage or []))[-fenster:]
    befund = {"status": "nicht verfuegbar", "fenster": fenster, "mindest_abdeckung": mindest,
              "tage": len(tage), "erster_tag": tage[0] if tage else None, "letzter_tag": tage[-1] if tage else None,
              "fehlend": {}, "abdeckung_letzter_tag": None}
    geholt = {}
    for tag in tage:
        code, text = holen(tag)
        if code != 200:
            befund["fehlend"][tag] = f"FINRA antwortete mit {code}"
            continue
        daten, b = tagesdatei_lesen(text, tag)
        if not b["gueltig"]:
            befund["fehlend"][tag] = b["grund"]
            continue
        anteil = abdeckung(daten, ticker_liste)
        if tag == tage[-1]:
            befund["abdeckung_letzter_tag"] = round(anteil, 4)
        if anteil < mindest:
            befund["fehlend"][tag] = (f"die Datei führt {anteil * 100:.1f} Prozent des Universums, "
                                      f"verlangt sind {mindest * 100:.0f}").replace(".", ",")
            continue
        geholt[tag] = daten
    letzter = tage[-1] if tage else None
    tag_ok = bool(letzter and letzter in geholt)
    fenster_ok = tag_ok and len(tage) == fenster and all(t in geholt for t in tage)
    if not tage:
        hinweis = "keine Handelstage bekannt"
    elif not tag_ok:
        hinweis = (f"die FINRA-Tagesdatei vom {_datum_text(letzter)} fehlt oder ist unvollständig, "
                   f"{befund['fehlend'].get(letzter, 'ohne Angabe')}")
    elif not fenster_ok:
        luecken = [t for t in tage if t not in geholt]
        if not luecken:
            hinweis = f"der Wert über {fenster} Handelstage fehlt, die Kurshistorie kennt erst {len(tage)} Handelstage"
        elif len(luecken) == 1:
            hinweis = (f"der Wert über {fenster} Handelstage fehlt, die Tagesdatei vom {_datum_text(luecken[0])} ist "
                       f"nicht verwendbar")
        else:
            hinweis = (f"der Wert über {fenster} Handelstage fehlt, {len(luecken)} Tagesdateien sind nicht verwendbar, "
                       f"zuerst die vom {_datum_text(luecken[0])}")
    else:
        hinweis = None
    befund["status"] = "ok" if fenster_ok else ("teilweise" if tag_ok else "nicht verfuegbar")
    befund["hinweis"] = hinweis
    werte = {}
    for s in ticker_liste or []:
        f = finra_symbol(s)
        w = dict.fromkeys(SHORT_FELDER)
        w["short_hinweis"] = hinweis
        if tag_ok:
            w["short_stand"] = letzter
            r = geholt[letzter].get(f)
            w["short_volumen"] = r[0] if r else 0.0
            w["short_gesamtvolumen"] = r[2] if r else 0.0
            if r and r[2] > 0:
                w["short_anteil_pct"] = round(r[0] / r[2] * 100.0, 1)
        if fenster_ok:
            summe_s = summe_g = 0.0
            mit = 0
            for t in tage:
                r = geholt[t].get(f)
                if r and r[2] > 0:
                    summe_s += r[0]
                    summe_g += r[2]
                    mit += 1
            w["short_tage_20t"] = mit
            if summe_g > 0:
                w["short_anteil_20t_pct"] = round(summe_s / summe_g * 100.0, 1)
        werte[s] = w
    anteile = [w["short_anteil_pct"] for w in werte.values() if w["short_anteil_pct"] is not None]
    median = round(statistics.median(anteile), 1) if anteile else None
    for w in werte.values():
        w["short_median_pct"] = median
    befund["mit_anteil"] = len(anteile)
    befund["median_pct"] = median
    return werte, befund


# ---------------------------------------------------------------------------
# Selbsttest (ohne Netz)
# ---------------------------------------------------------------------------

def _datei(tag, zeilen, schluss=None, kopf="Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market"):
    roh = [kopf] + [f"{tag.replace('-', '')}|{s}|{a}|{b}|{c}|Q" for s, a, b, c in zeilen]
    roh.append(str(len(zeilen) if schluss is None else schluss))
    return "\n".join(roh) + "\n"


def selbsttest() -> int:
    fehler = []

    def p(name, ok, zusatz=""):
        print(f"  {'ok  ' if ok else 'FEHL'} {name}" + (f"; {zusatz}" if zusatz else ""))
        if not ok:
            fehler.append(name)

    print("Short-Volumen aus der FINRA-Tagesdatei, Selbsttest (ohne Netz)")
    p("Mindestabdeckung ist die des RS-Universums", mindest_abdeckung() == float(CFG["rs_universum"]["mindest_abdeckung"]))
    p("Schreibweise: BRK.B wird BRK/B", finra_symbol("brk.b") == "BRK/B" and finra_symbol("NVDA") == "NVDA")

    # Echte Zeilen vom 14.09.2026
    echt = ("Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market\n"
            "20260914|A|380591.095732|11|631970.726692|B,Q,N\n"
            "20260914|AA|545942.096555|4921|1401365.846772|B,Q,N\n"
            "20260914|BRK/B|100|0|400|Q,N\n"
            "3\n")
    d, b = tagesdatei_lesen(echt, "2026-09-14")
    p("Tagesdatei: Nachkommastellen, Klassen, Schlusszeile, Datum",
      b["gueltig"] and b["zeilen"] == 3 and b["datum"] == "2026-09-14" and abs(d["A"][0] - 380591.095732) < 1e-6
      and d["BRK/B"] == (100.0, 0.0, 400.0), str(b))
    _d, b = tagesdatei_lesen(echt.rsplit("\n3", 1)[0] + "\n", "2026-09-14")
    p("Tagesdatei ohne Schlusszeile gilt als abgeschnitten", not b["gueltig"] and "abgeschnitten" in b["grund"])
    _d, b2 = tagesdatei_lesen(echt, "2026-09-11")
    p("Gruende auf Deutsch mit Datum", b2["grund"] == "die Datei trägt das Datum 14.09.2026 statt 11.09.2026", b2["grund"])
    _d, b = tagesdatei_lesen(echt.replace("\n3\n", "\n5\n"), "2026-09-14")
    p("Schlusszeile mit falscher Zahl gilt als unvollstaendig", not b["gueltig"] and "nennt 5" in b["grund"])
    _d, b = tagesdatei_lesen(echt, "2026-09-11")
    p("Falsches Datum wird erkannt", not b["gueltig"] and "Datum" in b["grund"])
    _d, b = tagesdatei_lesen("<html>Access Denied</html>", "2026-09-14")
    p("Fremde Antwort wird erkannt", not b["gueltig"])
    leer, b = tagesdatei_lesen(_datei("2026-09-14", [], 0), "2026-09-14")
    p("Tag ohne Daten: nur Kopf und Schlusszeile 0 ist gueltig", b["gueltig"] and leer == {} and b["zeilen"] == 0)

    # 20 Handelstage mit einer Luecke im Kalender (Feiertag gibt es in der Liste nicht)
    universum = [f"T{i:03d}" for i in range(100)] + ["BRK.B"]
    tage = [f"2026-08-{t:02d}" for t in (17, 18, 19, 20, 21, 24, 25, 26, 27, 28, 31)] + \
           [f"2026-09-{t:02d}" for t in (1, 2, 3, 4, 8, 9, 10, 11, 14)]
    assert len(tage) == 20

    def zeilen_fuer(tag, auslassen=()):
        z = [(f"T{i:03d}", 50, 0, 100) for i in range(100) if f"T{i:03d}" not in auslassen]
        z.append(("BRK/B", 30 if tag == tage[-1] else 60, 0, 100))
        return z

    dateien = {t: _datei(t, zeilen_fuer(t)) for t in tage}
    abrufe = []

    def holen(tag):
        abrufe.append(tag)
        return (200, dateien[tag]) if tag in dateien else (404, "")

    w, bf = short_werte(universum, ["2026-08-14"] + tage, holen=holen)
    p("Nur die letzten 20 Handelstage werden geholt", abrufe == tage, f"{len(abrufe)} Abrufe")
    p("Vollstaendig: Anteil am Tag und ueber 20 Tage volumengewichtet",
      bf["status"] == "ok" and w["BRK.B"]["short_anteil_pct"] == 30.0 and w["BRK.B"]["short_anteil_20t_pct"] == 58.5
      and w["BRK.B"]["short_tage_20t"] == 20 and w["T001"]["short_anteil_20t_pct"] == 50.0
      and w["BRK.B"]["short_stand"] == "2026-09-14" and w["BRK.B"]["short_hinweis"] is None
      and w["T001"]["short_median_pct"] == 50.0 and bf["median_pct"] == 50.0,
      f"{w['BRK.B']}")

    # Aktie ohne ausserboerslichen Handel an einigen Tagen
    dateien2 = {t: _datei(t, zeilen_fuer(t, auslassen=("T005",) if t in tage[:5] else ())) for t in tage}
    w2, bf2 = short_werte(universum, tage, holen=lambda t: (200, dateien2[t]))
    p("Tage ohne ausserboerslichen Handel zaehlen nicht mit, der Wert bleibt",
      w2["T005"]["short_tage_20t"] == 15 and w2["T005"]["short_anteil_20t_pct"] == 50.0 and bf2["status"] == "ok")

    # Juengster Tag fehlt: alles nicht verfuegbar
    dateien3 = dict(dateien)
    del dateien3[tage[-1]]
    w3, bf3 = short_werte(universum, tage, holen=lambda t: (200, dateien3[t]) if t in dateien3 else (404, ""))
    p("Datei des juengsten Tags fehlt: alle Aktien nicht verfuegbar, Grund genannt",
      bf3["status"] == "nicht verfuegbar" and all(x["short_anteil_pct"] is None and x["short_anteil_20t_pct"] is None
                                                  for x in w3.values())
      and w3["T001"]["short_hinweis"] == "die FINRA-Tagesdatei vom 14.09.2026 fehlt oder ist unvollständig, FINRA "
                                         "antwortete mit 404", w3["T001"]["short_hinweis"])

    # Ein Tag im Fenster fehlt: nur der 20-Tage-Wert faellt
    dateien4 = dict(dateien)
    del dateien4[tage[3]]
    w4, bf4 = short_werte(universum, tage, holen=lambda t: (200, dateien4[t]) if t in dateien4 else (404, ""))
    p("Ein Tag im Fenster fehlt: Tageswert ja, 20-Tage-Wert nicht verfuegbar mit Grund",
      bf4["status"] == "teilweise" and w4["BRK.B"]["short_anteil_pct"] == 30.0 and w4["BRK.B"]["short_anteil_20t_pct"] is None
      and w4["BRK.B"]["short_hinweis"] == "der Wert über 20 Handelstage fehlt, die Tagesdatei vom 20.08.2026 ist nicht "
                                          "verwendbar", w4["BRK.B"]["short_hinweis"])

    # Abdeckung unter der Mindestabdeckung
    dateien5 = dict(dateien)
    dateien5[tage[-1]] = _datei(tage[-1], zeilen_fuer(tage[-1], auslassen=tuple(f"T{i:03d}" for i in range(10))))
    w5, bf5 = short_werte(universum, tage, holen=lambda t: (200, dateien5[t]))
    p("Datei fuehrt unter 95 Prozent des Universums: alle nicht verfuegbar (Regel 1 des RS-Universums)",
      bf5["status"] == "nicht verfuegbar" and all(x["short_anteil_pct"] is None for x in w5.values())
      and bf5["abdeckung_letzter_tag"] == round(91 / 101, 4)
      and w5["T050"]["short_hinweis"].endswith("die Datei führt 90,1 Prozent des Universums, verlangt sind 95"),
      str(bf5["fehlend"]))

    # Abgeschnittene Datei am juengsten Tag
    dateien6 = dict(dateien)
    dateien6[tage[-1]] = dateien[tage[-1]].rsplit("\n", 2)[0] + "\n"
    w6, bf6 = short_werte(universum, tage, holen=lambda t: (200, dateien6[t]))
    p("Abgeschnittene Datei am juengsten Tag: nicht verfuegbar", bf6["status"] == "nicht verfuegbar"
      and "abgeschnitten" in w6["T001"]["short_hinweis"])

    # Aktie fehlt in der juengsten Datei
    dateien7 = dict(dateien)
    dateien7[tage[-1]] = _datei(tage[-1], zeilen_fuer(tage[-1], auslassen=("T099",)))
    w7, _bf7 = short_werte(universum, tage, holen=lambda t: (200, dateien7[t]))
    p("Aktie ohne ausserboerslichen Handel am Tag: kein Anteil, Volumen null, 20-Tage-Wert bleibt",
      w7["T099"]["short_anteil_pct"] is None and w7["T099"]["short_volumen"] == 0.0
      and w7["T099"]["short_anteil_20t_pct"] == 50.0 and w7["T099"]["short_tage_20t"] == 19)

    # Zu wenige Handelstage bekannt
    w8, bf8 = short_werte(universum, tage[-5:], holen=holen)
    p("Nur fuenf Handelstage bekannt: Tageswert ja, 20-Tage-Wert nicht verfuegbar",
      bf8["status"] == "teilweise" and w8["T001"]["short_anteil_pct"] == 50.0 and w8["T001"]["short_anteil_20t_pct"] is None)
    w9, bf9 = short_werte(universum, [], holen=holen)
    p("Ohne Handelstage: nicht verfuegbar", bf9["status"] == "nicht verfuegbar" and w9["T001"]["short_hinweis"])

    quelle = open(__file__, encoding="utf-8").read()
    p("Keine Vernetzung: kein Sendecode, keine Alarmdateien",
      all(x not in quelle for x in ("NTFY_" + "TOPIC", "ntfy." + "sh", "requests." + "post(", "breakout_" + "watcher",
                                    "traderfox_" + "alarm", "kaufpunkte_" + "aktuell")))
    p("Datum-Hilfe", _datum_text("2026-09-14") == "14.09.2026" and date(2026, 9, 14).isoformat() == "2026-09-14")

    print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles bestanden.")
    return 1 if fehler else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Short-Volumen aus der FINRA-Tagesdatei (Etappe 7)")
    ap.add_argument("--selbsttest", action="store_true")
    args = ap.parse_args()
    if args.selbsttest:
        return selbsttest()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
