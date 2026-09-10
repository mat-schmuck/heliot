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

SEIT 10.09.2026: NACHTS VORRECHNEN, ZUM HANDELSSTART NEU RECHNEN
  Mathias' Regel, woertlich: "Es darf nie wieder etwas vom Vortag
  kommen, angezeigte Alarme muessen immer aus den aktuellen Kursen
  errechnet sein, die zu Handelsstart gelten." Anlass war der 09.09.2026:
  Ab 15:30:21 gingen zehn fertige Nachttexte hinaus, alle mit dem
  Schlusskurs vom 08.09. und ohne Datum. WFRD hiess "Stop gerissen" bei
  93,70, eroeffnete aber bei 94,82 ueber dem Stop; FSLY hiess "+3,9 %
  seit Trigger", in derselben Minute waren es rund +11 %.

  Der Nachtlauf schreibt deshalb KEINE fertigen Meldetexte mehr fuer
  das, was sich aus heutigen Kursen rechnen laesst. Er legt zwei Arten
  von Befunden ab:

    live              Musterziel, Zonenaufstieg, Klimax-Zeichen 1, 4 und 5,
                      Weinstein Stufe 3, Zeitdeckel, Zahlen-Hinweis. Der
                      Nachtlauf merkt nur den KANDIDATEN samt Kursverlauf
                      (verlaeufe). Der Waechter rechnet ihn mit dem ersten
                      heutigen Kurs der Aktie nach (live_pruefen) und
                      meldet nur, was dann noch gilt, mit den Zahlen von
                      heute. Die Melde-Merker (ziel_gemeldet und so weiter)
                      setzt erst der Waechter, wenn die Meldung wirklich
                      hinaus ist; der Nachtlauf setzt sie nicht mehr.

    zurueckgehalten   Was nach Gerhards Regeln einen SCHLUSSKURS braucht
                      und sich zur Eroeffnung nicht aus heutigen Kursen
                      rechnen laesst: die Kapitel-11-Exits ("Schlusskurs,
                      nicht Docht"), Klimax-Zeichen 2 (groesster
                      Tagesgewinn) und 3 (Erschoepfungsluecke, braucht das
                      Tagestief), Wedge Drop (erster SCHLUSS unter beiden
                      Linien), der Sektor-Hinweis (Radar auf Schlusskursen)
                      und "Tagesgeschaeft beendet" (der Handelsschluss
                      selbst). Diese Befunde werden aufgeschrieben, aber
                      nicht gemeldet, bis Gerhard die Regelfrage
                      beantwortet hat (Dokument vom 10.09.2026).

Die Befunde landen in exit_befunde.json; jede traegt Typ, Art,
Prioritaet und ob sie gebuendelt gemeldet wird (gewinn_zonen.
meldepriorität). Der Waechter merkt gemeldete Kandidaten im
Melde-Gedaechtnis (GEWINN|<Handelstag>|<Typ>|<Beobachtung>|<Zeichen>).
"""

import json
from datetime import date, datetime

import exit_regeln
import gewinn_zonen as gz
import beobachtungen
import positionen

BEFUNDE_DATEI = "exit_befunde.json"

# Ablageformat. 2 heisst: Kandidaten statt fertiger Texte (seit 10.09.2026).
# Eine Ablage ohne diese Angabe stammt aus der Zeit davor und traegt Texte
# mit Schlusskursen des Vortags - der Waechter meldet daraus nichts mehr.
FORMAT = 2
LIVE = "live"
ZURUECK = "zurueckgehalten"

# Die Klimax-Zeichen, die sich aus dem heutigen Kurs rechnen lassen. Zeichen
# 2 fragt nach dem Tagesgewinn und Zeichen 3 nach dem Tagestief: Beides
# steht erst mit der fertigen Tageskerze fest.
KLIMAX_LIVE = ("1_klimaxlauf", "4_ma200_abstand", "5_kanaluebershooting")

# So viele Handelstage Kursverlauf bekommt der Waechter je Kandidat mit:
# genug fuer die 200-Tage-Linie, den 120-Tage-Kanal und die 30-Wochen-Linie.
VERLAUF_TAGE = 260

RANG = {"leicht": 0, "mittel": 1, "stark": 2}


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
    sind Mitschrift (leise, gebuendelt). Weinstein Stufe 3 lief bis
    10.09.2026 unter dem Typ klimax_zeichen und behaelt dessen Meldeart."""
    eigene = {
        "zeitdeckel": {"prioritaet": "high", "buendeln": False},
        "zahlen_hinweis": {"prioritaet": "high", "buendeln": False},
        # Kell Wedge Drop (Gerhard, G12 vom 31.08.2026): ein hartes
        # Ausstiegssignal, laut und einzeln wie der Zeitdeckel.
        "wedge_drop": {"prioritaet": "high", "buendeln": False},
        "weinstein": {"prioritaet": "high", "buendeln": False},
        "sektor_hinweis": {"prioritaet": "default", "buendeln": True},
        "kapitel11": {"prioritaet": "high", "buendeln": True},
        "tagesende": {"prioritaet": "default", "buendeln": True},
    }
    if typ in eigene:
        return eigene[typ]
    return gz.meldepriorität(typ)


def _befund(typ, titel, text, symbol="", key="", art=ZURUECK, zeichen=None,
            grund=""):
    p = _prio(typ)
    b = {"typ": typ, "art": art, "titel": titel, "text": text,
         "symbol": symbol, "key": key, "prioritaet": p["prioritaet"],
         "buendeln": p["buendeln"]}
    if zeichen:
        b["zeichen"] = zeichen
    if grund:
        b["grund"] = grund
    return b


def _stand_text(eintrag, kurs, mit_kurs=False):
    """'seit Trigger +x,x % gleich y,y R', auf Wunsch mit dem Kurs davor.

    Den KURS nennen seit 10.09.2026 alle Meldungen, die der Waechter aus
    dem heutigen Kurs nachrechnet: Man soll sehen, von welchem Stand die
    Zahlen stammen."""
    pct = gz.berechne_gewinn_pct(eintrag["einstieg"], kurs) * 100
    r = gz.berechne_gewinn_r(eintrag["einstieg"],
                             eintrag.get("struktur_stop")
                             or eintrag["aktueller_stop"], kurs)
    r_teil = f" gleich {r:.1f} R".replace(".", ",") if r is not None else ""
    stand = f"seit Trigger {pct:+.1f} %".replace(".", ",") + r_teil
    if mit_kurs:
        return f"Kurs {kurs:.2f}".replace(".", ",") + ", " + stand
    return stand


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
    Fehlalarm zu geben.

    FEHLER BEHOBEN (10.09.2026): Als Dauer des Klimaxlaufs ging hier die
    GANZE Haltedauer hinein. Zeichen 1 verlangt aber hoechstens 15
    Handelstage Lauf UND mindestens acht Wochen Vorlauf; mit derselben
    Zahl fuer beides (hoechstens 15 und zugleich mindestens 40 Tage)
    konnte es nie ausloesen. Die Dauer des Laufs ist das Fenster, ueber
    das der Anstieg gemessen wird, also die letzten n Handelstage."""
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
        tage_seit_bewegungsstart=max(n, 0),
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


def _verlauf(df, tage):
    """Der Kursverlauf, den der Waechter zum Nachrechnen braucht.

    Die Haltedauer steht ausdruecklich dabei: Der Verlauf ist auf
    VERLAUF_TAGE gekuerzt, eine Beobachtung kann aelter sein."""
    if "datetime" not in df.columns:
        return None
    teil = df.tail(VERLAUF_TAGE)
    closes = teil["close"].tolist()
    hochs = teil["high"].tolist() if "high" in teil.columns else closes
    tiefs = teil["low"].tolist() if "low" in teil.columns else closes
    daten = []
    for d, c, h, l in zip(teil["datetime"], closes, hochs, tiefs):
        try:
            daten.append([str(d)[:10], round(float(c), 4),
                          round(float(h), 4), round(float(l), 4)])
        except (TypeError, ValueError):
            continue
    return {"tage": int(tage), "daten": daten} if daten else None


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
    verlaeufe = {}

    # Kapitel-11-Meldungen (Verlustseite) in die Ablage — vorher wurden
    # sie nur gedruckt, und das Protokoll liest niemand. ZURUECKGEHALTEN
    # seit 10.09.2026: Nach Gerhards Regel zaehlt der Schlusskurs, nicht
    # der Docht, und der steht zur Eroeffnung nicht aus heutigen Kursen fest.
    for m in (exit_meldungen or []):
        text = positionen.melde_text(m) if hasattr(positionen, "melde_text") \
            else str(m)
        befunde.append(_befund("kapitel11", "Exit-Regelwerk: "
                               + str(m.get("symbol", "")), text,
                               symbol=str(m.get("symbol", "")),
                               art=ZURUECK, grund="schlusskurs"))

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
            vorher = len(befunde)

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

            # 2) Tagesgeschaeft endet am Handelsschluss — Mitschrift. Der
            #    Befund IST der Handelsschluss: zurueckgehalten.
            if klasse == "tagesgeschaeft":
                beobachtungen.schliessen(e, "Handelsschluss (Tagesgeschäft)",
                                         kurs)
                befunde.append(_befund(
                    "tagesende", "Tagesgeschäft beendet",
                    f"{sym}; {e.get('strategie', '')}; "
                    + _stand_text(e, kurs), symbol=sym, key=key,
                    art=ZURUECK, grund="schlusskurs"))
                continue

            # 3) Darvas: keine Zonen, keine Ziele (Gerhard, 27.08.2026).
            if klasse == "darvas":
                continue

            # 4) Zeitdeckel je Klasse. Die Beobachtung endet hier (das ist
            #    Buchfuehrung), gemeldet wird mit dem Stand von heute.
            deckel, _rest = gz.pruefe_zeitdeckel(klasse, tage)
            if deckel:
                beobachtungen.schliessen(e, f"Zeitdeckel ({klasse})", kurs)
                befunde.append(_befund("zeitdeckel", "", "", symbol=sym,
                                       key=key, art=LIVE))
                v = _verlauf(df, tage)
                if v:
                    verlaeufe[key] = v
                continue

            # 5) Klimax-Katalog — sofort scharf, jedes Zeichen einzeln.
            #    Die Merker setzt der Waechter nach dem Senden.
            eingaben = _klimax_eingaben(df, tage)
            klimax = gz.pruefe_klimax_katalog(eingaben)
            for zeichen in klimax["ausgeloeste_zeichen"]:
                if zeichen in e.get("klimax_gemeldet", []):
                    continue
                if zeichen in KLIMAX_LIVE:
                    befunde.append(_befund("klimax_zeichen", "", "",
                                           symbol=sym, key=key, art=LIVE,
                                           zeichen=zeichen))
                    continue
                wert = klimax["details"][zeichen].get("wert_pct")
                wert_teil = (f" ({wert:+.1f} %)".replace(".", ",")
                             if wert is not None else "")
                befunde.append(_befund(
                    "klimax_zeichen", f"KLIMAX: {sym}",
                    f"{sym}; {e.get('strategie', '')}; Klimax-Zeichen "
                    f"{zeichen.replace('_', ' ')}{wert_teil}; Verkauf in "
                    f"die Stärke erwägen; " + _stand_text(e, kurs),
                    symbol=sym, key=key, art=ZURUECK, zeichen=zeichen,
                    grund="schlusskurs"))

            # 6) Zone und Musterziel. Die Zone selbst fuehrt der Nachtlauf
            #    weiter nach Gerhards Regeln (sie steuert die Pruefungen
            #    unten). GEMELDET wird ein Aufstieg gegen die zuletzt
            #    GEMELDETE Zone (zone_gemeldet): Nur so kommt ein Aufstieg
            #    erneut, dessen Meldung zur Eroeffnung nicht mehr galt.
            #    Ein Abstieg bleibt still und senkt diesen Stand mit.
            ziel = e.get("musterziel")
            ziel_da = bool(ziel) and kurs >= float(ziel)
            zonen = gz.klassifiziere_zone(
                e["einstieg"],
                e.get("struktur_stop") or e["aktueller_stop"], kurs,
                musterziel_erreicht=ziel_da,
                ist_klimax=klimax["ist_klimax"])
            alt = e.get("zone")
            gemeldet = e.get("zone_gemeldet") or alt
            e["zone"] = zonen["zone"]
            if gemeldet is None:
                e["zone_gemeldet"] = zonen["zone"]
            else:
                if (gemeldet in RANG
                        and RANG[zonen["zone"]] < RANG[gemeldet]):
                    gemeldet = zonen["zone"]
                e["zone_gemeldet"] = gemeldet
                if (zonen["gewinn_pct"] > 0 and gemeldet in RANG
                        and RANG[zonen["zone"]] > RANG[gemeldet]):
                    befunde.append(_befund("zonenwechsel", "", "",
                                           symbol=sym, key=key, art=LIVE))

            if ziel_da and not e.get("ziel_gemeldet"):
                befunde.append(_befund("ziel_erreicht", "", "", symbol=sym,
                                       key=key, art=LIVE))

            # 7) Weinstein Stufe 3 — nur in Zone stark geprueft.
            if zonen["zone"] == "stark" and not e.get("weinstein_gemeldet"):
                w3, _det = gz.pruefe_weinstein_stufe3(_ma30w_serie(df))
                if w3:
                    befunde.append(_befund("weinstein", "", "", symbol=sym,
                                           key=key, art=LIVE))

            # 7b) Kell Wedge Drop — nur in Zone stark (GERHARDS ENTSCHEID
            # vom 31.08.2026 abends, Regelfrage G12). Erster Schluss
            # unter BEIDEN Tageslinien (10er/20er-EMA) nach der weit
            # gelaufenen Phase ist Kells hartes Ausstiegssignal; die
            # Phasen-Definition kommt aus kell_zyklus, der EINEN Quelle
            # dieser Linienlogik. Einmalig je Beobachtung gemeldet.
            # Ein erster SCHLUSS: zurueckgehalten seit 10.09.2026.
            if zonen["zone"] == "stark" and not e.get("wedge_drop_gemeldet"):
                try:
                    import kell_zyklus
                    phase = kell_zyklus.klassifiziere(df)
                except Exception:
                    phase = None
                if phase == "Wedge Drop":
                    befunde.append(_befund(
                        "wedge_drop", f"Wedge Drop: {sym}",
                        f"{sym}; {e.get('strategie', '')}; erster Schluss "
                        f"unter der 10er- und 20er-Tageslinie nach der "
                        f"Überdehnung (Kell Wedge Drop); Ausstieg oder "
                        f"harte Straffung; " + _stand_text(e, kurs),
                        symbol=sym, key=key, art=ZURUECK,
                        grund="schlusskurs"))

            # 8a) Zahlen-Termin binnen fuenf Tagen, ab Zone mittel.
            if (zonen["zone"] in ("mittel", "stark")
                    and not e.get("zahlen_hinweis_gemeldet")):
                abstand = beobachtungen.termin_abstand_tage(sym)
                if abstand is not None and 0 <= abstand <= 5:
                    befunde.append(_befund("zahlen_hinweis", "", "",
                                           symbol=sym, key=key, art=LIVE))

            # 8b) Sektor-Dreher nach unten, in Zone stark. Der Radar
            #     rechnet auf Schlusskursen: zurueckgehalten.
            if (zonen["zone"] == "stark" and dreher
                    and not e.get("sektor_hinweis_gemeldet")):
                try:
                    import listen
                    etf = beobachtungen.sektor_etf_fuer(
                        listen.sektor_von(sym))
                except Exception:
                    etf = None
                if etf and etf in dreher:
                    befunde.append(_befund(
                        "sektor_hinweis", "Sektor dreht",
                        f"{sym}; eigener Sektor-ETF {etf} hat nach unten "
                        f"gedreht, Beobachtung in Zone stark; Straffung "
                        f"erwägen; " + _stand_text(e, kurs),
                        symbol=sym, key=key, art=ZURUECK,
                        grund="schlusskurs"))

            if any(b.get("art") == LIVE for b in befunde[vorher:]):
                v = _verlauf(df, tage)
                if v:
                    verlaeufe[key] = v

        positionen.speichern(bestand)

    inhalt = {"format": FORMAT,
              "handelstag": heute.isoformat(),
              "gebaut_am": datetime.now().isoformat(timespec="seconds"),
              "befunde": befunde,
              "verlaeufe": verlaeufe}
    with open(BEFUNDE_DATEI, "w", encoding="utf-8") as f:
        json.dump(inhalt, f, ensure_ascii=False, indent=1)
    n_live = sum(1 for b in befunde if b.get("art") == LIVE)
    print(f"Kapitel 12: {len(offen)} Beobachtung(en) geprueft, "
          f"{len(befunde)} Befund(e) nach {BEFUNDE_DATEI}: {n_live} zum "
          f"Nachrechnen am Handelsstart, {len(befunde) - n_live} "
          f"zurueckgehalten.")
    return befunde


# ---------------------------------------------------------------------------
# Zum Handelsstart: Kandidaten mit dem heutigen Kurs nachrechnen
# ---------------------------------------------------------------------------

def lies_befunde(pfad=BEFUNDE_DATEI):
    """Die Ablage des Nachtlaufs, leer bei jedem Fehler."""
    try:
        with open(pfad, encoding="utf-8-sig") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _df_live(verlauf, heute, kurs, hoch=None, tief=None):
    """Der Kursverlauf der Nacht plus EINE Zeile fuer heute mit dem
    aktuellen Kurs. Hoch und Tief der heutigen Zeile umfassen den Kurs
    immer; fehlen sie, stehen sie auf dem Kurs."""
    import pandas as pd
    tag = heute.isoformat()
    zeilen = [list(z[:4]) for z in (verlauf or {}).get("daten", [])
              if str(z[0])[:10] < tag]
    kurs = float(kurs)
    h = max(float(hoch), kurs) if hoch else kurs
    t = min(float(tief), kurs) if tief else kurs
    zeilen.append([tag, kurs, h, t])
    return pd.DataFrame(zeilen, columns=["datetime", "close", "high", "low"])


def live_pruefen(befund, eintrag, verlauf, kurs, heute, hoch=None, tief=None,
                 termine=None):
    """Einen Kandidaten des Nachtlaufs mit dem HEUTIGEN Kurs nachrechnen.

    Dieselben Regeln wie nachts (gewinn_zonen), nur mit dem Kurs von heute
    als juengstem Wert. Zur Zone zaehlen dabei nur die Klimax-Zeichen, die
    sich aus dem Kurs rechnen lassen (KLIMAX_LIVE).

    Rueckgabe (titel, text, merker), wenn der Befund mit diesem Kurs gilt,
    sonst None. merker sagt, was nach dem ERFOLGREICHEN Senden in die
    Beobachtung gehoert (merker_anwenden); vorher wird nichts veraendert."""
    if not eintrag or not verlauf or kurs is None:
        return None
    try:
        kurs = float(kurs)
    except (TypeError, ValueError):
        return None
    if not kurs > 0:
        return None
    typ = befund.get("typ")
    sym = eintrag.get("symbol") or befund.get("symbol") or "?"
    strategie = eintrag.get("strategie", "")
    stand = _stand_text(eintrag, kurs, mit_kurs=True)

    if typ == "zeitdeckel":
        # Die Tageszaehlung ist erreicht und bleibt es; neu gerechnet wird
        # der Stand, mit dem die Meldung hinausgeht.
        klasse = eintrag.get("klasse", "standard")
        return (f"Zeitdeckel erreicht: {sym}",
                f"{sym}; {strategie}; Zeitdeckel der Klasse {klasse} "
                f"erreicht; Gewinn sichern oder These erneuern; " + stand,
                {})

    df = _df_live(verlauf, heute, kurs, hoch, tief)
    tage = int(verlauf.get("tage", 0)) + 1
    klimax = gz.pruefe_klimax_katalog(_klimax_eingaben(df, tage))
    live_zeichen = [z for z in klimax["ausgeloeste_zeichen"]
                    if z in KLIMAX_LIVE]
    ziel = eintrag.get("musterziel")
    ziel_da = bool(ziel) and kurs >= float(ziel)
    zonen = gz.klassifiziere_zone(
        eintrag["einstieg"],
        eintrag.get("struktur_stop") or eintrag["aktueller_stop"], kurs,
        musterziel_erreicht=ziel_da, ist_klimax=bool(live_zeichen))
    zone = zonen["zone"]

    if typ == "ziel_erreicht":
        if not ziel_da or eintrag.get("ziel_gemeldet"):
            return None
        return (f"GEWINN-Ziel erreicht: {sym}",
                f"{sym}; {strategie}; Musterziel {float(ziel):.2f} erreicht; "
                f"Teilverkauf oder harte Straffung; " + stand,
                {"ziel_gemeldet": True})

    if typ == "klimax_zeichen":
        z = befund.get("zeichen")
        if z not in live_zeichen or z in eintrag.get("klimax_gemeldet", []):
            return None
        wert = klimax["details"][z].get("wert_pct")
        wert_teil = (f" ({wert:+.1f} %)".replace(".", ",")
                     if wert is not None else "")
        return (f"KLIMAX: {sym}",
                f"{sym}; {strategie}; Klimax-Zeichen {z.replace('_', ' ')}"
                f"{wert_teil}; Verkauf in die Stärke erwägen; " + stand,
                {"klimax_gemeldet": z})

    if typ == "zonenwechsel":
        von = eintrag.get("zone_gemeldet")
        if (von not in RANG or zonen["gewinn_pct"] <= 0
                or RANG[zone] <= RANG[von]):
            return None
        return ("Gewinnzonen",
                f"{sym}; {strategie}; Zone {von} zu {zone}; " + stand,
                {"zone_gemeldet": zone})

    if typ == "weinstein":
        if zone != "stark" or eintrag.get("weinstein_gemeldet"):
            return None
        w3, _det = gz.pruefe_weinstein_stufe3(_ma30w_serie(df))
        if not w3:
            return None
        return (f"Stufe 3: {sym}",
                f"{sym}; {strategie}; 30-Wochen-Linie flacht ab (Weinstein "
                f"Stufe 3); " + stand,
                {"weinstein_gemeldet": True})

    if typ == "zahlen_hinweis":
        if (zone not in ("mittel", "stark")
                or eintrag.get("zahlen_hinweis_gemeldet")):
            return None
        abstand = beobachtungen.termin_abstand_tage(sym, termine=termine,
                                                    heute=heute)
        if abstand is None or not 0 <= abstand <= 5:
            return None
        return (f"Zahlen voraus: {sym}",
                f"{sym}; Quartalszahlen in {abstand} Tag(en) bei Zone "
                f"{zone}; Gewinn vor Zahlen sichern erwägen; " + stand,
                {"zahlen_hinweis_gemeldet": True})

    return None


def merker_anwenden(eintrag, merker):
    """Die Melde-Merker nach dem Senden in die Beobachtung schreiben."""
    for feld, wert in (merker or {}).items():
        if feld == "klimax_gemeldet":
            liste = eintrag.setdefault("klimax_gemeldet", [])
            if wert not in liste:
                liste.append(wert)
        else:
            eintrag[feld] = wert
    return eintrag
