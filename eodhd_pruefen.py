# -*- coding: utf-8 -*-
"""Gegenprobe der gekauften EODHD-Historie gegen das amtliche Archiv.

Gerhards Punkt 3 (02.09.2026): Die Quartalszuordnung der Konsensdaten ist
hart zu pruefen, bevor die Historie als Referenz gilt. Anlass am
03.09.2026: EODHD nannte fuer Abercrombie (Quartal bis 31.07.2026) ein
tatsaechliches EPS von 2,42, die Pressemitteilung wies 4,17 aus.

Geprueft wird je Firma und Quartal das EPS aus der EODHD-History
(epsActual) gegen die amtliche Erstfassung von eps_verwaessert (typ Q) aus
den Kennzahlen-Parquets des Phase-1-Releases; das Periodenende darf bis zu
sechs Tage abweichen (52/53-Wochen-Jahre, Wochenendtermine). Klassen:
exakt (bis 0,5 Cent), rundung (bis 1,5 Cent), abweichend (mehr), kein
amtlicher Wert. Dazu die Meldedaten der History gegen das Filing-Datum der
Erstfassung (ist das EODHD-Meldedatum VOR dem amtlichen Bericht, wie es
fuer eine Pressemitteilung sein muss?).

Aufruf:
  python eodhd_pruefen.py --daten <heliot-daten> --parquet <Ordner mit
      fundament_kennzahlen_JJJJ.parquet> [--ab 2017] [--bericht DATEI]
  python eodhd_pruefen.py --selbsttest
"""
import argparse
import collections
import datetime as dt
import glob
import gzip
import io
import json
import os
import sys

EXAKT = 0.005
RUNDUNG = 0.015
TOLERANZ_TAGE = 6
ADJUST_EXAKT = 0.011      # nach Division durch den Split-Faktor rundet EODHD auf zwei bis vier Stellen
ADJUST_RUNDUNG = 0.03


def split_faktor(splits, ab_datum):
    f = 1.0
    for s in splits or []:
        try:
            if str(s.get("date")) <= str(ab_datum):
                continue
            n, m = str(s.get("split")).split("/")
            n, m = float(n), float(m)
            if n > 0 and m > 0:
                f *= n / m
        except (ValueError, AttributeError, TypeError):
            continue
    return f


def splits_laden(daten, ticker):
    import eodhd_konsens as ek
    p = os.path.join(daten, "eodhd", "splits", f"{ek.sicherer_name(ticker)}.json.gz")
    if not os.path.exists(p):
        return None
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return json.load(f)


def amtliche_eps(parquet_ordner, ab_jahr):
    """{cik: [(end_date, wert_erst, filed_erst, quelle)]} der Quartals-EPS."""
    import pandas as pd
    raus = collections.defaultdict(list)
    for p in sorted(glob.glob(os.path.join(parquet_ordner, "fundament_kennzahlen_*.parquet"))):
        try:
            jahr = int(os.path.basename(p).split("_")[-1].split(".")[0])
        except ValueError:
            continue
        if jahr < ab_jahr:
            continue
        df = pd.read_parquet(p, columns=["cik", "kennzahl", "typ", "end", "wert_erst", "filed_erst", "quelle"])
        df = df[(df["kennzahl"] == "eps_verwaessert") & (df["typ"] == "Q")]
        for cik, end, wert, filed, quelle in zip(df["cik"], df["end"], df["wert_erst"], df["filed_erst"], df["quelle"]):
            try:
                raus[int(cik)].append((dt.date.fromisoformat(str(end)[:10]), float(wert), str(filed)[:10], quelle))
            except (TypeError, ValueError):
                continue
    return raus


def eodhd_history(daten):
    """[(ticker, cik, [(end_date, eps_ist, eps_konsens, meldedatum)])]."""
    raus = []
    for p in sorted(glob.glob(os.path.join(daten, "eodhd", "konsens", "*.json.gz"))):
        with gzip.open(p, "rt", encoding="utf-8") as f:
            d = json.load(f)
        k = d.get("kopf") or {}
        try:
            cik = int(str(k.get("cik") or "").lstrip("0") or "0")
        except ValueError:
            cik = 0
        zeilen = []
        for z in d.get("zeilen") or []:
            if z.get("art") != "eps_history" or z.get("eps_ist") is None:
                continue
            try:
                zeilen.append((dt.date.fromisoformat(z["periodenende"]), float(z["eps_ist"]),
                               z.get("eps_konsens"), z.get("meldedatum")))
            except (TypeError, ValueError, KeyError):
                continue
        raus.append((k.get("ticker"), cik, zeilen))
    return raus


def vergleiche(history, amtlich, ab=dt.date(2017, 1, 1), splits=None):
    """Je History-Quartal die Klasse; liefert (zaehler, beispiele). Mit
    Split-Historie wird der amtliche Wert auf die heutige Aktienzahl
    gebracht (EODHD fuehrt die History so), Klasse split_adjustiert."""
    zaehler = collections.Counter()
    faelle = []
    for end, eps, konsens, melde in history:
        if end < ab:
            continue
        passend = [a for a in amtlich if abs((a[0] - end).days) <= TOLERANZ_TAGE]
        if not passend:
            zaehler["kein_amtlicher_wert"] += 1
            faelle.append((end, eps, None, "kein_amtlicher_wert", melde, None))
            continue
        a = min(passend, key=lambda x: abs((x[0] - end).days))
        diff = abs(eps - a[1])
        klasse = "exakt" if diff <= EXAKT else ("rundung" if diff <= RUNDUNG else "abweichend")
        if klasse == "abweichend" and splits:
            f = split_faktor(splits, end.isoformat())
            if f != 1.0:
                adj = a[1] / f
                d2 = abs(eps - adj)
                if d2 <= ADJUST_EXAKT:
                    klasse = "split_adjustiert"
                elif d2 <= ADJUST_RUNDUNG:
                    klasse = "rundung"
        zaehler[klasse] += 1
        if melde and a[2] and melde > a[2]:
            zaehler["meldedatum_nach_bericht"] += 1
        faelle.append((end, eps, a[1], klasse, melde, a[2]))
    return zaehler, faelle


def bericht(daten, parquet_ordner, ab_jahr=2017, ausgabe=None, log=print):
    amt = amtliche_eps(parquet_ordner, ab_jahr - 1)
    gesamt = collections.Counter()
    je_firma = []
    abweichungen = []
    ab = dt.date(ab_jahr, 1, 1)
    for ticker, cik, hist in eodhd_history(daten):
        z, faelle = vergleiche(hist, amt.get(cik, []), ab, splits=splits_laden(daten, ticker))
        gesamt.update(z)
        n = sum(v for k, v in z.items() if k != "meldedatum_nach_bericht")
        je_firma.append((ticker, cik, n, z))
        for end, eps, soll, klasse, melde, filed in faelle:
            if klasse == "abweichend":
                abweichungen.append((ticker, end.isoformat(), eps, soll, melde, filed))
    n = sum(v for k, v in gesamt.items() if k != "meldedatum_nach_bericht")
    zeilen = [f"EODHD-Gegenprobe: {len(je_firma)} Firmen, {n} Quartale ab {ab_jahr} mit EPS in der History"]
    for k in ("exakt", "split_adjustiert", "rundung", "abweichend", "kein_amtlicher_wert"):
        v = gesamt.get(k, 0)
        zeilen.append(f"  {k}: {v} ({(100.0 * v / n):.1f} Prozent)" if n else f"  {k}: {v}")
    zeilen.append(f"  Meldedatum laut EODHD NACH dem amtlichen Bericht: {gesamt.get('meldedatum_nach_bericht', 0)}")
    schlecht = sorted([f for f in je_firma if f[2] and (f[3].get("abweichend", 0) / f[2]) > 0.2],
                      key=lambda f: -(f[3].get("abweichend", 0) / f[2]))
    zeilen.append(f"  Firmen mit mehr als 20 Prozent abweichenden Quartalen: {len(schlecht)}")
    for t, c, nn, z in schlecht[:40]:
        zeilen.append(f"    {t} (CIK {c}): {z.get('abweichend', 0)} von {nn} abweichend, exakt {z.get('exakt', 0)}, "
                      f"kein amtlicher Wert {z.get('kein_amtlicher_wert', 0)}")
    zeilen.append(f"  Abweichende Quartale insgesamt: {len(abweichungen)}; die ersten 60:")
    for t, end, eps, soll, melde, filed in abweichungen[:60]:
        zeilen.append(f"    {t} {end}: EODHD {eps} gegen amtlich {soll} (EODHD-Meldedatum {melde}, Erstfassung eingereicht {filed})")
    text = "\n".join(zeilen)
    log(text)
    if ausgabe:
        with io.open(ausgabe, "w", encoding="utf-8") as f:
            f.write(text + "\n")
            f.write("\nALLE ABWEICHUNGEN\n")
            for t, end, eps, soll, melde, filed in abweichungen:
                f.write(f"{t}\t{end}\t{eps}\t{soll}\t{melde}\t{filed}\n")
    return gesamt, je_firma, abweichungen


def selbsttest() -> int:
    fehler = 0

    def p(name, ok, extra=""):
        nonlocal fehler
        print(f"  {'ok  ' if ok else 'FEHL'} {name}{(' ' + str(extra)) if extra else ''}")
        if not ok:
            fehler += 1

    amt = [(dt.date(2026, 6, 27), 2.02, "2026-08-01", "amtlich"), (dt.date(2026, 3, 28), 2.01, "2026-05-02", "amtlich"),
           (dt.date(2025, 12, 27), 2.84, "2026-01-31", "amtlich")]
    hist = [(dt.date(2026, 6, 30), 2.02, 1.88, "2026-07-30"), (dt.date(2026, 3, 31), 2.02, 1.94, "2026-04-30"),
            (dt.date(2025, 12, 31), 2.50, 2.67, "2026-02-05"), (dt.date(2025, 9, 30), 1.85, 1.77, "2025-10-30"),
            (dt.date(2016, 3, 31), 1.0, 1.0, "2016-04-26")]
    z, faelle = vergleiche(hist, amt)
    p("Klassen: exakt trotz drei Tagen Versatz, Rundung bei einem Cent, abweichend, kein amtlicher Wert",
      z["exakt"] == 1 and z["rundung"] == 1 and z["abweichend"] == 1 and z["kein_amtlicher_wert"] == 1, dict(z))
    p("Quartale vor 2017 werden nicht gezaehlt", sum(v for k, v in z.items() if k != "meldedatum_nach_bericht") == 4)
    p("Meldedatum nach dem amtlichen Bericht wird gezaehlt (Dezember-Fall)", z["meldedatum_nach_bericht"] == 1)
    amt2 = [(dt.date(2017, 4, 1), 2.10, "2017-05-03", "amtlich"), (dt.date(2021, 3, 27), 1.40, "2021-04-29", "amtlich")]
    hist2 = [(dt.date(2017, 3, 31), 0.525, 2.0, "2017-05-02"), (dt.date(2021, 3, 31), 1.40, 1.0, "2021-04-28"),
             (dt.date(2017, 3, 31), 0.60, 2.0, "2017-05-02")]
    sp = [{"date": "2020-08-31", "split": "4.000000/1.000000"}]
    z2, _ = vergleiche(hist2, amt2, splits=sp)
    p("Split-Adjustierung: 2,10 durch 4 ist 0,525 (split_adjustiert), nach dem Split exakt, echte Abweichung bleibt",
      z2["split_adjustiert"] == 1 and z2["exakt"] == 1 and z2["abweichend"] == 1, dict(z2))
    print("\n" + ("Alles bestanden." if fehler == 0 else f"{fehler} Fehler."))
    return fehler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--daten", default="")
    ap.add_argument("--parquet", default="")
    ap.add_argument("--ab", type=int, default=2017)
    ap.add_argument("--bericht", default="")
    ap.add_argument("--selbsttest", action="store_true")
    a = ap.parse_args()
    if a.selbsttest:
        sys.exit(1 if selbsttest() else 0)
    if not (a.daten and a.parquet):
        print("--daten und --parquet fehlen.")
        sys.exit(2)
    bericht(a.daten, a.parquet, a.ab, a.bericht or None)


if __name__ == "__main__":
    main()
