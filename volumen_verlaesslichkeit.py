#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WIE VERLAESSLICH IST DAS VOLUMENURTEIL FRUEH AM TAG?
=====================================================
Mathias' Frage vom 29.07.2026: Ist die Angabe, zu wieviel Prozent der
Handelstag gelaufen ist, fuer die Kaufentscheidung ueberhaupt wichtig?

Sie sagt eigentlich etwas anderes aus, als sie vorgibt. Ihr Wert liegt
nicht in der Zahl selbst, sondern darin, wie belastbar das Volumenurteil
zu diesem Zeitpunkt ist: Um 9:35 wird aus 7,5 Prozent des Tages auf den
ganzen Tag hochgerechnet — ein einziger groesserer Block verzerrt das
Ergebnis. Um 15:00 sind 80 Prozent gelaufen, da aendert sich kaum noch
etwas.

Gemessen wird deshalb, wie oft das Urteil UMKIPPT: Wie haeufig sagt die
Hochrechnung um 10:00, 11:00 oder 12:00 New Yorker Zeit "bestaetigt",
waehrend der fertige Tag am Ende "nicht bestaetigt" ergibt — und
umgekehrt.

Ist die Umkipprate frueh hoch, ist die Uhrzeit fuer die Kaufentscheidung
sehr wohl wichtig, weil ein frueher Treffer weniger wert ist. Ist sie
niedrig, kann die Angabe raus.

Aufruf:  python volumen_verlaesslichkeit.py [Anzahl Aktien]
"""

import sys

XLSX = "kaufpunkte_aktuell.xlsx"
# Minuten seit Handelsbeginn, zu denen geprueft wird
ZEITPUNKTE = [(30, "10:00"), (60, "10:30"), (90, "11:00"), (150, "12:00"),
              (270, "14:00")]


def main():
    anzahl = int(sys.argv[1]) if len(sys.argv) > 1 else 25

    import pandas as pd
    import yfinance as yf
    import volumen

    volumen.lade_kurve(leise=True)

    df = pd.read_excel(XLSX, sheet_name="Kaufpunkte")
    ticker = sorted({str(t).strip().upper() for t in df["Ticker"]})[:anzahl]
    print(f"{len(ticker)} Aktien, Fuenf-Minuten-Daten der letzten 50 Tage.\n")

    # Tagesdaten fuer den 50-Tage-Schnitt
    tage = yf.download(" ".join(ticker), period="6mo", interval="1d",
                       group_by="ticker", progress=False, auto_adjust=False,
                       threads=True)

    umkipp = {m: [0, 0] for m, _ in ZEITPUNKTE}   # [umgekippt, geprueft]
    abweichung = {m: [] for m, _ in ZEITPUNKTE}
    # RICHTUNG des Umkippens (Mathias, 29.07.2026). Die beiden Faelle
    # wiegen naemlich verschieden schwer:
    #   rauf  = frueh 'nicht bestaetigt', am Ende doch bestaetigt.
    #           Das ist der gefaehrliche Fall: Der Ausbruch gilt als
    #           gemeldet und erledigt, die spaetere Bestaetigung erfaehrt
    #           Mathias nie — ein echtes Signal geht still verloren.
    #   runter = frueh 'bestaetigt', am Ende nicht. Aergerlich, aber
    #           sichtbar: Er hat die Meldung bekommen und kann selbst
    #           nachsehen.
    richtung = {m: {"rauf": 0, "runter": 0,
                    "frueh_ja": 0, "frueh_nein": 0} for m, _ in ZEITPUNKTE}

    for t in ticker:
        try:
            fein = yf.download(t, period="50d", interval="5m",
                               progress=False, auto_adjust=False)
            if fein is None or fein.empty:
                continue
            if isinstance(fein.columns, pd.MultiIndex):
                fein.columns = fein.columns.get_level_values(0)
            try:
                fein = fein.tz_convert("America/New_York")
            except Exception:
                pass
            tagesreihe = tage[t].dropna(subset=["Volume"])["Volume"]
        except Exception:
            continue

        fein = fein[["Volume"]].dropna()
        fein["minute"] = [(z.hour * 60 + z.minute) - (9 * 60 + 30)
                          for z in fein.index.time]
        fein["datum"] = fein.index.date

        for datum, tagblock in fein.groupby("datum"):
            tagblock = tagblock[(tagblock["minute"] >= 0)
                                & (tagblock["minute"] < 390)].sort_index()
            if tagblock.empty or int(tagblock["minute"].max()) < 350:
                continue                      # halber Handelstag
            gesamt = float(tagblock["Volume"].sum())
            # Ø50 der Tage VOR diesem Tag
            vorher = tagesreihe[tagesreihe.index.date < datum]
            if len(vorher) < 50 or gesamt <= 0:
                continue
            o50 = float(vorher.tail(50).mean())
            if o50 <= 0:
                continue
            endurteil = (gesamt / o50) >= 1.0

            for m, _ in ZEITPUNKTE:
                bisher = float(tagblock[tagblock["minute"] < m]["Volume"].sum())
                if bisher <= 0:
                    continue
                f = volumen.tagesanteil(m)
                verh = (bisher / f) / o50
                frueh = verh >= 1.0
                umkipp[m][1] += 1
                richtung[m]["frueh_ja" if frueh else "frueh_nein"] += 1
                if frueh != endurteil:
                    umkipp[m][0] += 1
                    richtung[m]["runter" if frueh else "rauf"] += 1
                abweichung[m].append(abs(verh - gesamt / o50))

    print("Wie oft kippt das Urteil bis zum Handelsschluss noch um?\n")
    print("Uhrzeit   geprüfte Tage   Urteil kippt   mittlere Abweichung")
    print("-" * 62)
    for m, uhr in ZEITPUNKTE:
        kipp, n = umkipp[m]
        if not n:
            continue
        ab = sorted(abweichung[m])
        mitte = ab[len(ab) // 2] if ab else 0
        print(f"{uhr:>7s}   {n:13,}   {kipp/n*100:9.1f} %   "
              f"{mitte*100:14.0f} Prozentpunkte")

    print("\nIn WELCHE Richtung kippt es?\n")
    print("Uhrzeit   früh 'nicht bestätigt'   davon am Ende doch bestätigt")
    print("-" * 66)
    for m, uhr in ZEITPUNKTE:
        r = richtung[m]
        if r["frueh_nein"]:
            print(f"{uhr:>7s}   {r['frueh_nein']:20,}   "
                  f"{r['rauf']:5,}  = {r['rauf']/r['frueh_nein']*100:4.1f} %")
    print()
    print("Uhrzeit   früh 'bestätigt'         davon am Ende doch nicht")
    print("-" * 66)
    for m, uhr in ZEITPUNKTE:
        r = richtung[m]
        if r["frueh_ja"]:
            print(f"{uhr:>7s}   {r['frueh_ja']:20,}   "
                  f"{r['runter']:5,}  = "
                  f"{r['runter']/r['frueh_ja']*100:4.1f} %")

    print("\n--- DEUTUNG ---")
    r10, r14 = richtung[30], richtung[270]
    if r10["frueh_ja"] and r10["frueh_nein"]:
        fehlalarm = r10["runter"] / r10["frueh_ja"] * 100
        verpasst = r10["rauf"] / r10["frueh_nein"] * 100
        spaet_fehl = (r14["runter"] / r14["frueh_ja"] * 100
                      if r14["frueh_ja"] else 0)
        print(f"Ein 'bestätigt' um 10:00 ist in {fehlalarm:.0f} % der Fälle "
              f"bis zum Schluss wieder hinfällig — um 14:00 nur noch in "
              f"{spaet_fehl:.0f} %.")
        print(f"Ein 'nicht bestätigt' um 10:00 wird in {verpasst:.0f} % der "
              f"Fälle bis zum Schluss doch noch bestätigt.")
        print()
        print("Das zweite ist der teurere Fehler: Der Kaufpunkt gilt nach "
              "der Meldung für die Woche als erledigt, die spätere "
              "Bestätigung erfährt niemand mehr. Ein Nachtrag, sobald das "
              "Volumen nachzieht, würde genau diese Fälle einfangen.")
        print()
        print("ACHTUNG bei der Einordnung: Gemessen sind ALLE Handelstage, "
              "nicht nur die mit gerissenem Kaufpunkt. An Ausbruchstagen "
              "liegt das Volumen typischerweise höher, die Raten dürften "
              "dort etwas anders liegen.")


if __name__ == "__main__":
    main()
