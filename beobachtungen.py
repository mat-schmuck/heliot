#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BEOBACHTUNGS-FUETTERUNG — das Bindeglied fuer Kapitel 12 (Gewinnseite)
=======================================================================
Gerhards Uebergabe vom 28.08.2026, Abschnitt "Was Mathias noch selbst
bauen muss": Jede Kaufpunkt-Triggermeldung oeffnet automatisch eine
Beobachtung in der Positionsverwaltung (die Beobachtungs-Betriebsart
stand seit dem 05.08. leer). Dieses Modul uebersetzt einen Trigger in
einen Beobachtungs-Eintrag; die Regeln selbst stehen in gewinn_zonen.py
(Gerhards Modul) und exit_regeln.py (Kapitel 11).

SCHLUESSEL-SCHEMA: Ein Ticker kann mehrere Kaufpunkte zugleich reissen
(ASC|1 und ASC|2 am 19.08. waren genau so ein Fall) und naechste Woche
erneut triggern. Der Bestand ist deshalb mit "TICKER|Zusatz"
verschluesselt (Kaufpunkt-Nummer oder Signal-Kuerzel samt Datum); das
echte Symbol steht im Feld "symbol". positionen.pruefe_bestand schlaegt
Kurse seither ueber dieses Feld nach, nicht ueber den Schluessel.

KLASSEN (fuer gewinn_zonen.pruefe_zeitdeckel und die Melde-Wege):
  tagesgeschaeft  Red-to-Green, Red-to-Green Explosive, Gap and Go;
                  endet am Handelsschluss.
  zahlen_luecke   Luecken-Bestaetigungstag, WENN der Zahlen-Termin der
                  Aktie in den letzten fuenf Tagen lag (Drift-Fenster
                  60 Handelstage, Bernard und Thomas 1989).
  insider         Insider-Kauf; Horizont sechs Monate (Jeng, Metrick
                  und Zeckhauser 2003).
  darvas          quellentreu KEINE Gewinnseite (Gerhards Entscheidung
                  vom 27.08.2026): nur Stop-Nachzug aus Kapitel 11.
  standard        alles andere; Horizont zwoelf Monate.
"""

import json
from datetime import date

import exit_regeln

TAGESGESCHAEFT = ("Red-to-Green", "Red-to-Green Explosive", "Gap and Go")

# Finviz-Sektorname -> Sektor-ETF des Radars (sektor_radar.ETF_UNIVERSE
# fuehrt die ETFs mit eigenen Namen; diese Tabelle uebersetzt die
# Sektor-Spalte der Wochenlisten dorthin).
SEKTOR_ETF = {
    "Technology": "XLK",
    "Financial": "XLF",
    "Healthcare": "XLV",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Basic Materials": "XLB",
    "Communication Services": "XLC",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
}


def klasse_fuer(strategien, termin_tage=None):
    """Die Positionsklasse eines Triggers, aus seinen Musternamen.

    termin_tage: Abstand zum Zahlen-Termin in Tagen (negativ =
    vergangen), oder None wenn unbekannt. Nur der
    Luecken-Bestaetigungstag wird darueber zur Zahlen-Luecke: Lag der
    Termin binnen der letzten fuenf Tage, gilt das Drift-Fenster; sonst
    ist es eine gewoehnliche Luecke mit Standard-Horizont."""
    namen = [str(n) for n in (strategien or []) if n]
    if not namen:
        return "standard"
    if all(n.startswith("Darvas") for n in namen):
        return "darvas"
    if any(n in TAGESGESCHAEFT for n in namen):
        return "tagesgeschaeft"
    if any("Insider" in n for n in namen):
        return "insider"
    if any("cken-Best" in n for n in namen):     # Luecken/Lücken
        if termin_tage is not None and -5 <= termin_tage <= 0:
            return "zahlen_luecke"
        return "standard"
    # EARNINGS-PULLBACK (Gerhards Freigabe 31.08.2026): per Definition
    # zahlengebunden — der Detektor belegt den Termin selbst, deshalb
    # braucht es hier keine termin_tage-Bedingung. Die Klasse traegt
    # den 60-Tage-Zeitdeckel, exakt die PEAD-Drift-Frist.
    if any("Earnings-Pullback" in n for n in namen):
        return "zahlen_luecke"
    return "standard"


def schluessel(ticker, zusatz):
    return f"{str(ticker).upper()}|{zusatz}"


def oeffnen(bestand, ticker, zusatz, strategie, kaufpunkt, struktur_stop,
            musterziel=None, firma="", klasse="standard", datum=None):
    """Eine Beobachtung anlegen. Rueckgabe: Schluessel, oder None wenn
    unter diesem Schluessel schon eine OFFENE Beobachtung steht (der
    Nachtrag derselben Meldung darf keine zweite oeffnen).

    Die Felder sind dieselben wie in positionen.eroeffne, plus die
    Kapitel-12-Felder klasse, musterziel, zone und die Melde-Merker.
    Der Stop laeuft durch denselben Deckel wie ueberall
    (exit_regeln.berechne_initialen_stop)."""
    key = schluessel(ticker, zusatz)
    alt = bestand.get(key)
    if alt and alt.get("status") == "offen":
        return None
    if kaufpunkt is None or kaufpunkt <= 0:
        return None
    stop, quelle = exit_regeln.berechne_initialen_stop(
        float(kaufpunkt), struktur_stop)
    bestand[key] = {
        "symbol": str(ticker).upper(), "firma": firma or "",
        "strategie": strategie, "einstieg": round(float(kaufpunkt), 4),
        "einstieg_datum": datum or date.today().isoformat(),
        "einstieg_index": 0,
        "struktur_stop": (round(float(struktur_stop), 4)
                          if struktur_stop is not None else None),
        "aktueller_stop": stop, "stop_quelle": quelle,
        "hoechstkurs": round(float(kaufpunkt), 4),
        "teilverkauft": False, "halteregel_aktiv": False,
        "beobachtung": True, "status": "offen", "verlauf": [],
        # Kapitel 12:
        "klasse": klasse,
        "musterziel": (round(float(musterziel), 4)
                       if musterziel is not None and musterziel == musterziel
                       else None),
        "zone": None,
        "ziel_gemeldet": False,
        "klimax_gemeldet": [],
        "weinstein_gemeldet": False,
        "zahlen_hinweis_gemeldet": False,
        "sektor_hinweis_gemeldet": False,
        # Kell Wedge Drop (Gerhard, G12 vom 31.08.2026), nur Zone stark.
        "wedge_drop_gemeldet": False,
    }
    return key


def offene(bestand):
    """Alle offenen Beobachtungen (nicht die von Hand gefuehrten
    Echt-Positionen)."""
    return {k: e for k, e in (bestand or {}).items()
            if isinstance(e, dict) and e.get("status") == "offen"
            and e.get("beobachtung")}


def schliessen(eintrag, grund, kurs=None):
    """Eine Beobachtung beenden und das Ergebnis festhalten — das ist
    die Mitschrift, um die es bei Architektur A geht."""
    eintrag["status"] = "geschlossen"
    eintrag["schluss_datum"] = date.today().isoformat()
    eintrag["schluss_grund"] = grund
    if kurs is not None:
        eintrag["schluss_kurs"] = round(float(kurs), 4)
        eintrag["ergebnis_pct"] = round(
            (kurs / eintrag["einstieg"] - 1) * 100, 2)
        abstand = eintrag["einstieg"] - (eintrag.get("struktur_stop")
                                         or eintrag["aktueller_stop"])
        if abstand > 0:
            eintrag["ergebnis_r"] = round(
                (kurs - eintrag["einstieg"]) / abstand, 2)
    return eintrag


def termin_abstand_tage(ticker, termine=None, heute=None, pfad="zahlen_termine.json"):
    """Abstand zum Zahlen-Termin in Kalendertagen (positiv = kommt noch,
    negativ = war schon). None, wenn kein Termin bekannt.

    termine kann fuer Pruefungen direkt uebergeben werden; sonst wird
    zahlen_termine.json gelesen (der Nachtscan haelt sie frisch)."""
    if termine is None:
        try:
            with open(pfad, encoding="utf-8-sig") as f:
                termine = json.load(f).get("aktien", {})
        except (OSError, ValueError):
            return None
    eintrag = (termine or {}).get(str(ticker).upper())
    if not eintrag or not eintrag.get("datum"):
        return None
    try:
        termin = date.fromisoformat(str(eintrag["datum"])[:10])
    except ValueError:
        return None
    return (termin - (heute or date.today())).days


def sektor_etf_fuer(sektor_name):
    """Der Radar-ETF zum Finviz-Sektor der Aktie, oder None."""
    return SEKTOR_ETF.get(str(sektor_name or "").strip())
