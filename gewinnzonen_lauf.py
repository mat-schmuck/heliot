#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KAPITEL-12-NACHTLAUF — Gewinnzonen je offener Beobachtung
==========================================================
Gerhards Uebergabe vom 28.08.2026: gewinn_zonen.py liefert die reinen
Regeln (Zonen, Klimax-Katalog, Weinstein, Zeitdeckel), dieses Modul
wendet sie NAECHTLICH auf jede offene Beobachtung an und legt die
Befunde fuer den Waechter ab — gemeldet wird zur Handelszeit, nicht um
Mitternacht (dasselbe Muster wie beim Sektor-Radar: nachts rechnen,
morgens melden). Auch die Kapitel-11-Meldungen (Verlustseite) laufen
seither ueber diese Ablage: Vorher wurden sie nur ins Protokoll
gedruckt, und das liest niemand.

WAS JE BEOBACHTUNG PASSIERT
  1. Hoechststand nachfuehren, Stop aus der frischen Mappe nachziehen
     (Kapitel 11, 'der Stop wandert mit' — bei Darvas ist genau das die
     ganze Gewinnseite, Gerhards quellentreue Entscheidung).
  2. Tagesgeschaeft (Red-to-Green, Gap and Go): am Handelsschluss
     beenden, Ergebnis in die Mitschrift, ein gebuendelter Befund.
  3. Zeitdeckel je Klasse (60 Handelstage Zahlen-Luecke, 6 Monate
     Insider, 12 Monate Standard): Beobachtung endet, lauter Befund
     'Gewinn sichern oder These erneuern'.
  4. Zone bestimmen (leicht/mittel/stark), Zonen-AUFSTIEG als leiser,
     gebuendelter Befund.
  5. Musterziel erreicht: lauter Einzel-Befund (die Verkaufszone).
  6. Klimax-Katalog, alle fuenf Zeichen SOFORT SCHARF (Gerhards
     Entscheidung), je Zeichen ein lauter Einzel-Befund, nur einmal.
  7. Weinstein Stufe 3 (nur in Zone stark geprueft).
  8. Kopplungen: Zahlen-Termin binnen fuenf Tagen ab Zone mittel
     (laut), Sektor-ETF-Dreher nach unten in Zone stark (gebuendelt).

Die Befunde landen in exit_befunde.json; jede traegt Titel, Text,
Prioritaet und ob sie gebuendelt gemeldet wird (gewinn_zonen.
meldepriorität). Der Waechter meldet sie ueber das bestehende Thema
und merkt sie im Melde-Gedaechtnis (GEWINN|<Handelstag>|<Nr>).
"""

import json
from datetime import date, datetime

import exit_regeln
import gewinn_zonen as gz
import beobachtungen
import positionen

BEFUNDE_DATEI = "exit_befunde.json"


# ---------------------------------------------------------------------------
# Hilfen
# ---------------------------------------------------------------------------

def _prio(typ):
    """Meldeart je Befundtyp. Die drei Kerntypen kommen aus Gerhards
    Modul; die uebrigen sind hier festgelegt: Zeitdeckel und
    Zahlen-Hinweis sind handlungsrelevant und selten (laut, einzeln),
    ein Sektor-Dreher trifft oft viele Beobachtungen zugleich
    (gebuendelt), Kapitel-11-Exits sind dringlich, aber nach einem
    roten Tag zahlreich (laut, EIN Buendel), Tagesgeschaeft-Ergebnisse
    sind Mitschrift (leise, gebuendelt)."""
    eigene = {
        "zeitdeckel": {"prioritaet": "high", "buendeln": False},
        "zahlen_hinweis": {"prioritaet": "high", "buendeln": False},
        "sektor_hinweis": {"prioritaet": "default", "buendeln": True},
        "kapitel11": {"prioritaet": "high", "buendeln": True},
        "tagesende": {"prioritaet": "default", "buendeln": True},
    }
    if typ in eigene:
        return eigene[typ]
    return gz.meldepriorität(typ)


def _befund(typ, titel, text, symbol="", key=""):
    p = _prio(typ)
    return {"typ": typ, "titel": titel, "text": text, "symbol": symbol,
            "key": key, "prioritaet": p["prioritaet"],
            "buendeln": p["buendeln"]}


def _stand_text(eintrag, kurs):
    pct = gz.berechne_gewinn_pct(eintrag["einstieg"], kurs) * 100
    r = gz.berechne_gewinn_r(eintrag["einstieg"],
                             eintrag.get("struktur_stop")
                             or eintrag["aktueller_stop"], kurs)
    r_teil = f" gleich {r:.1f} R".replace(".", ",") if r is not None else ""
    return f"seit Trigger {pct:+.1f} %".replace(".", ",") + r_teil


def frische_stops_aus_mappe(mappe_pfad):
    """(Symbol, Strategie) -> Stop aus der eben geschriebenen Mappe.

    Das ist der automatisierte 'Stop wandert mit': Die Detektoren des
    Nachtscans liefern jede Nacht frische Strukturpunkte (neue
    Darvas-Box, neues Handle-Tief); lag der neue Stop hoeher, zieht
    exit_regeln.ziehe_stop_nach nach — nie zurueck."""
    stops = {}
    try:
        import pandas as pd
        d = pd.read_excel(mappe_pfad)
    except Exception:
        return stops
    for _, r in d.iterrows():
        for k in (1, 2, 3):
            s = r.get(f"KP{k} Strategie")
            stop = r.get(f"KP{k} Stop")
            if isinstance(s, str) and s.strip() and stop == stop and stop:
                stops[(str(r["Ticker"]).upper(), s.strip())] = float(stop)
    return stops


def _kurse_nachladen(symbole):
    """Tagesdaten fuer Beobachtungen, deren Aktie nicht (mehr) auf den
    Wochenlisten steht — Insider-Funde sind marktweit, und eine Aktie
    kann von der Liste fallen, waehrend die Beobachtung laeuft.
    Rueckgabe: {symbol: df} im Spaltenschema des Scanners."""
    if not symbole:
        return {}
    raus = {}
    try:
        import yfinance as yf
        roh = yf.download(" ".join(sorted(symbole)), period="2y",
                          interval="1d", progress=False, auto_adjust=False,
                          group_by="ticker", threads=True)
        import pandas as pd
        for s in symbole:
            try:
                df = roh[s] if len(symbole) > 1 else roh
                df = df.dropna(subset=["Close"])
                if df.empty:
                    continue
                raus[s] = pd.DataFrame({
                    "datetime": df.index.astype(str),
                    "close": df["Close"].values,
                    "high": df["High"].values,
                    "low": df["Low"].values})
            except Exception:
                continue
    except Exception as e:
        print(f"  Nachladen fuer {len(symbole)} listenfremde "
              f"Beobachtung(en) fehlgeschlagen: {type(e).__name__}")
    return raus


def _klimax_eingaben(df, tage_gehalten):
    """Die Rohwerte fuer Gerhards Klimax-Katalog aus der Kurshistorie.

    BEWUSSTE VEREINFACHUNG (Startwert, per Mitschreiben zu verfeinern):
    'Wochen Vorlauf' zaehlt ab UNSEREM Einstieg, nicht ab dem
    tatsaechlichen Beginn der Kursbewegung. Das ist die konservative
    Richtung — Zeichen 1 und 3 verlangen mindestens acht Wochen
    Vorlauf und bleiben bei frischen Beobachtungen still, statt frueh
    Fehlalarm zu geben."""
    closes = [float(x) for x in df["close"].tolist()]
    hochs = ([float(x) for x in df["high"].tolist()]
             if "high" in df.columns else None)
    tiefs = ([float(x) for x in df["low"].tolist()]
             if "low" in df.columns else None)
    n = min(len(closes) - 1, 15)
    start = max(1, len(closes) - max(tage_gehalten, 1))
    gewinne = [closes[i] / closes[i - 1] - 1
               for i in range(start, len(closes))]
    ma200 = (sum(closes[-200:]) / 200) if len(closes) >= 200 else 0.0
    kanal = gz.berechne_obere_kanallinie(closes, hochs) or 0.0
    return gz.KlimaxEingaben(
        kurs_vor_n_tagen=closes[-1 - n] if n > 0 else closes[0],
        kurs_heute=closes[-1],
        tage_seit_bewegungsstart=min(tage_gehalten, 10 ** 6),
        wochen_vorlauf=tage_gehalten / 5.0,
        tagesgewinne_seit_start_pct=gewinne,
        vortages_hoch=hochs[-2] if hochs and len(hochs) >= 2 else closes[-1],
        heutiges_tief=tiefs[-1] if tiefs else closes[-1],
        ma200=ma200,
        obere_kanallinie=kanal)


def _ma30w_serie(df):
    """Die 30-Wochen-Linie fuer Weinsteins Stufe-3-Pruefung."""
    try:
        import pandas as pd
        t = pd.DataFrame({
            "datum": pd.to_datetime(df["datetime"], errors="coerce"),
            "close": df["close"].astype(float)}).dropna()
        wochen = (t.set_index("datum")["close"]
                  .resample("W").last().dropna())
        ma = wochen.rolling(30).mean().dropna()
        return [float(x) for x in ma.tail(6).tolist()]
    except Exception:
        return []


def _sektor_dreher_runter():
    """Die Sektor-ETFs, die der Radar HEUTE NACHT auf 'runter' gedreht
    hat (sektor_radar.json wird im selben Nachtlauf gebaut)."""
    try:
        with open("sektor_radar.json", encoding="utf-8-sig") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return set()
    raus = set()
    for t in d.get("treffer", []):
        if str(t.get("richtung", "")).startswith("runter"):
            etf = t.get("etf") or t.get("symbol") or t.get("ticker")
            if etf:
                raus.add(str(etf).upper())
    return raus


# ---------------------------------------------------------------------------
# Fuetterung aus dem Nachtscan (Shakeout-Signale)
# ---------------------------------------------------------------------------

def beobachtungen_aus_shakeout(signale):
    """Shakeout-Springs werden im Nachtscan erkannt, nicht im Waechter —
    ihre Beobachtungen entstehen deshalb hier."""
    if not signale:
        return 0
    bestand = positionen.laden()
    neu = 0
    tag = date.today().isoformat()
    for s in signale:
        key = beobachtungen.oeffnen(
            bestand, s.get("symbol"), f"SPRING-{tag}", "Shakeout-Spring",
            s.get("kaufpunkt"), s.get("stop"), musterziel=s.get("kursziel"),
            firma=s.get("firma", ""), klasse="standard")
        if key:
            neu += 1
    if neu:
        positionen.speichern(bestand)
        print(f"Kapitel 12: {neu} Beobachtung(en) aus Shakeout-Signalen.")
    return neu


# ---------------------------------------------------------------------------
# Der naechtliche Durchgang
# ---------------------------------------------------------------------------

def gewinn_durchgang(loaded, mappe_pfad, exit_meldungen=None, heute=None):
    """Alle offenen Beobachtungen pruefen, Befunde fuer den Waechter
    ablegen. Rueckgabe: die Befundliste."""
    heute = heute or date.today()
    bestand = positionen.laden()
    offen = beobachtungen.offene(bestand)
    befunde = []

    # Kapitel-11-Meldungen (Verlustseite) in die Ablage — vorher wurden
    # sie nur gedruckt, und das Protokoll liest niemand.
    for m in (exit_meldungen or []):
        text = positionen.melde_text(m) if hasattr(positionen, "melde_text") \
            else str(m)
        befunde.append(_befund("kapitel11", "Exit-Regelwerk: "
                               + str(m.get("symbol", "")), text,
                               symbol=str(m.get("symbol", ""))))

    if offen:
        stops_neu = frische_stops_aus_mappe(mappe_pfad)
        dreher = _sektor_dreher_runter()
        fehlend = {e["symbol"] for e in offen.values()
                   if e["symbol"] not in loaded}
        nachgeladen = _kurse_nachladen(fehlend)

        for key, e in sorted(offen.items()):
            sym = e["symbol"]
            df = None
            if sym in loaded:
                df = loaded[sym][0] if isinstance(loaded[sym], tuple) \
                    else loaded[sym]
            elif sym in nachgeladen:
                df = nachgeladen[sym]
            if df is None or not len(df):
                continue
            kurs = float(df["close"].iloc[-1])
            e["hoechstkurs"] = max(float(e.get("hoechstkurs", kurs)), kurs)

            # Handelstage seit Einstieg, aus der Historie (nicht Kalender)
            if "datetime" in df.columns:
                tage = int((df["datetime"].astype(str)
                            > e["einstieg_datum"]).sum())
            else:
                tage = max(0, (heute - date.fromisoformat(
                    e["einstieg_datum"])).days)

            # 1) Stop-Nachzug aus der frischen Mappe — fuer Darvas ist
            #    das die GANZE Gewinnseite (quellentreu).
            neu_stop = stops_neu.get((sym, e.get("strategie", "")))
            if neu_stop:
                e["aktueller_stop"] = exit_regeln.ziehe_stop_nach(
                    e["aktueller_stop"], neu_stop)

            klasse = e.get("klasse", "standard")

            # 2) Tagesgeschaeft endet am Handelsschluss — Mitschrift.
            if klasse == "tagesgeschaeft":
                beobachtungen.schliessen(e, "Handelsschluss (Tagesgeschäft)",
                                         kurs)
                befunde.append(_befund(
                    "tagesende", "Tagesgeschäft beendet",
                    f"{sym}; {e.get('strategie', '')}; "
                    + _stand_text(e, kurs), symbol=sym, key=key))
                continue

            # 3) Darvas: keine Zonen, keine Ziele (Gerhard, 27.08.2026).
            if klasse == "darvas":
                continue

            # 4) Zeitdeckel je Klasse.
            deckel, _rest = gz.pruefe_zeitdeckel(klasse, tage)
            if deckel:
                beobachtungen.schliessen(e, f"Zeitdeckel ({klasse})", kurs)
                befunde.append(_befund(
                    "zeitdeckel", f"Zeitdeckel erreicht: {sym}",
                    f"{sym}; {e.get('strategie', '')}; Zeitdeckel der "
                    f"Klasse {klasse} erreicht; Gewinn sichern oder These "
                    f"erneuern; " + _stand_text(e, kurs),
                    symbol=sym, key=key))
                continue

            # 5) Klimax-Katalog — sofort scharf, jedes Zeichen einzeln.
            eingaben = _klimax_eingaben(df, tage)
            klimax = gz.pruefe_klimax_katalog(eingaben)
            for zeichen in klimax["ausgeloeste_zeichen"]:
                if zeichen in e.get("klimax_gemeldet", []):
                    continue
                e.setdefault("klimax_gemeldet", []).append(zeichen)
                wert = klimax["details"][zeichen].get("wert_pct")
                wert_teil = (f" ({wert:+.1f} %)".replace(".", ",")
                             if wert is not None else "")
                befunde.append(_befund(
                    "klimax_zeichen", f"KLIMAX: {sym}",
                    f"{sym}; {e.get('strategie', '')}; Klimax-Zeichen "
                    f"{zeichen.replace('_', ' ')}{wert_teil}; Verkauf in "
                    f"die Stärke erwägen; " + _stand_text(e, kurs),
                    symbol=sym, key=key))

            # 6) Zone und Musterziel.
            ziel = e.get("musterziel")
            ziel_da = bool(ziel) and kurs >= float(ziel)
            zonen = gz.klassifiziere_zone(
                e["einstieg"],
                e.get("struktur_stop") or e["aktueller_stop"], kurs,
                musterziel_erreicht=ziel_da,
                ist_klimax=klimax["ist_klimax"])
            rang = {"leicht": 0, "mittel": 1, "stark": 2}
            alt = e.get("zone")
            e["zone"] = zonen["zone"]
            if (zonen["gewinn_pct"] > 0 and alt in rang
                    and rang[zonen["zone"]] > rang.get(alt, -1)):
                befunde.append(_befund(
                    "zonenwechsel", "Gewinnzonen",
                    f"{sym}; {e.get('strategie', '')}; Zone {alt} zu "
                    f"{zonen['zone']}; " + _stand_text(e, kurs),
                    symbol=sym, key=key))
            elif alt is None:
                e["zone"] = zonen["zone"]

            if ziel_da and not e.get("ziel_gemeldet"):
                e["ziel_gemeldet"] = True
                befunde.append(_befund(
                    "ziel_erreicht", f"GEWINN-Ziel erreicht: {sym}",
                    f"{sym}; {e.get('strategie', '')}; Musterziel "
                    f"{float(ziel):.2f} erreicht; Teilverkauf oder harte "
                    f"Straffung; " + _stand_text(e, kurs),
                    symbol=sym, key=key))

            # 7) Weinstein Stufe 3 — nur in Zone stark geprueft.
            if zonen["zone"] == "stark" and not e.get("weinstein_gemeldet"):
                w3, _det = gz.pruefe_weinstein_stufe3(_ma30w_serie(df))
                if w3:
                    e["weinstein_gemeldet"] = True
                    befunde.append(_befund(
                        "klimax_zeichen", f"Stufe 3: {sym}",
                        f"{sym}; {e.get('strategie', '')}; 30-Wochen-Linie "
                        f"flacht ab (Weinstein Stufe 3); "
                        + _stand_text(e, kurs), symbol=sym, key=key))

            # 8a) Zahlen-Termin binnen fuenf Tagen, ab Zone mittel.
            if (zonen["zone"] in ("mittel", "stark")
                    and not e.get("zahlen_hinweis_gemeldet")):
                abstand = beobachtungen.termin_abstand_tage(sym)
                if abstand is not None and 0 <= abstand <= 5:
                    e["zahlen_hinweis_gemeldet"] = True
                    befunde.append(_befund(
                        "zahlen_hinweis", f"Zahlen voraus: {sym}",
                        f"{sym}; Quartalszahlen in {abstand} Tag(en) bei "
                        f"Zone {zonen['zone']}; Gewinn vor Zahlen sichern "
                        f"erwägen; " + _stand_text(e, kurs),
                        symbol=sym, key=key))

            # 8b) Sektor-Dreher nach unten, in Zone stark.
            if (zonen["zone"] == "stark" and dreher
                    and not e.get("sektor_hinweis_gemeldet")):
                try:
                    import listen
                    etf = beobachtungen.sektor_etf_fuer(
                        listen.sektor_von(sym))
                except Exception:
                    etf = None
                if etf and etf in dreher:
                    e["sektor_hinweis_gemeldet"] = True
                    befunde.append(_befund(
                        "sektor_hinweis", "Sektor dreht",
                        f"{sym}; eigener Sektor-ETF {etf} hat nach unten "
                        f"gedreht, Beobachtung in Zone stark; Straffung "
                        f"erwägen; " + _stand_text(e, kurs),
                        symbol=sym, key=key))

        positionen.speichern(bestand)

    inhalt = {"handelstag": heute.isoformat(),
              "gebaut_am": datetime.now().isoformat(timespec="seconds"),
              "befunde": befunde}
    with open(BEFUNDE_DATEI, "w", encoding="utf-8") as f:
        json.dump(inhalt, f, ensure_ascii=False, indent=1)
    print(f"Kapitel 12: {len(offen)} Beobachtung(en) geprueft, "
          f"{len(befunde)} Befund(e) nach {BEFUNDE_DATEI}.")
    return befunde
