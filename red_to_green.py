#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RED-TO-GREEN — Kapitel 9, präzisierte Volumen-Signatur (02.08.2026)
===================================================================
Portiert aus Gerhards red_to_green_engine.py.

WAS SICH ÄNDERT
    Bisher stand im Regelwerk nur "Volumen zieht an" — nicht prüfbar.
    Jetzt zwei exakt definierte Phasen, beide über dieselbe
    IBD-Volumenformel wie der Rest des Systems (volumen.py):

    ANFLUG, vor der Kreuzung: Das Volumen darf höchstens im Normaltempo
        laufen (Volume%Change ≤ 0 %, also höchstens 100 % des
        50-Tage-Schnitts, hochgerechnet auf die Uhrzeit). "Trocken."
        AUSNAHME: Kreuzt es in den ersten 30 Handelsminuten, entfällt
        diese Bedingung — die Eröffnungsphase ist ohnehin volumenstark,
        und genau das steckt schon in der F(t)-Kurve.

    SPRUNG, an der Kreuzung: Das Volumen muss auf mindestens doppeltes
        Normaltempo springen (≥ +100 %) UND darf in den folgenden zehn
        Minuten nicht um mehr als 20 % wieder abfallen. Sonst war es
        eine Eintagsfliege und keine echte Beschleunigung.

    Warum nicht einfach eine feste Stückzahl als Schwelle: Die ignoriert
    die Uhrzeit. Am Morgen ist viel Volumen normal, mittags nicht. Die
    F(t)-Kurve rechnet genau das heraus.

DAVOR STEHEN ZWEI SCHALTER
    Regime: Der Nasdaq muss bei Eröffnung mindestens 1,5 % nach unten
        gapen, sonst bleibt die ganze Strategie den Tag über stumm.
    Fokusliste (nachts vorberechnet): RS-Rating über 90, Kurs über EMA21
        und EMA50, mindestens 50 % über dem 52-Wochen-Tief. Am Morgen
        kommt dazu, dass die Aktie selbst mindestens 5 % nach unten
        gapt.

ABWEICHUNG VON GERHARDS VORLAGE, BEWUSST
    Er arbeitet mit einem pandas-DataFrame je Aktie. Im Wächter läuft
    die Prüfung alle zwei Sekunden über bis zu hundert Aktien — dafür
    wäre ein DataFrame je Tick zu teuer. Hier ist der Verlauf eine
    schlichte Liste von Punkten je Aktie, ein Punkt je Minute. Die
    Rechenwege selbst sind unverändert.

GERHARDS EIGENE EINSCHRÄNKUNG, wörtlich übernommen: Die Frühphasen-
    Ausnahme ist "bewusst großzügig" und die Halte-Prüfung ein
    "Startwert, kein gemessenes Optimum". Beides erst mitschreiben,
    dann nachjustieren.

Aufruf:
    python red_to_green.py --selbsttest
"""

import argparse
import sys

import volumen
from config import CFG as _ALLE, hoechstens, mind_erreicht

CFG = _ALLE["red_to_green"]

# Gerhards Regel schließt die Grenze EIN ("≤ 0 %", "≥ +100 %"). Ohne
# diese Winzigkeit fällt der Grenzfall trotzdem durch: Ein Volumen von
# exakt Normaltempo rechnet sich zu 2,2 mal 10 hoch minus 14 statt zu
# glatt null, ein exakt doppeltes zu 99,999999999999 statt zu 100. Beim
# Nachrechnen des Selbsttests am 02.08.2026 aufgefallen.
GRENZ_SPIEL = 1e-9


# ---------------------------------------------------------------------------
# Die zwei Schalter davor
# ---------------------------------------------------------------------------

def regime_scharf(nasdaq_open, nasdaq_vortagesschluss):
    """Gapt der Nasdaq stark genug nach unten?

    Das ist ein Schalter für den ganzen Tag: Ohne Markt-Gap gibt es
    keinen Red-to-Green-Handel. Rückgabe: (scharf, Gap in Prozent)."""
    if not nasdaq_vortagesschluss or nasdaq_vortagesschluss <= 0:
        return False, 0.0
    gap = nasdaq_open / nasdaq_vortagesschluss - 1
    return hoechstens(gap, CFG["nasdaq_gap_scharf"]), round(gap * 100, 2)


def aktien_gap(aktie_open, aktie_vortagesschluss):
    """Gapt die Aktie selbst stark genug nach unten?"""
    if not aktie_vortagesschluss or aktie_vortagesschluss <= 0:
        return False, 0.0
    gap = aktie_open / aktie_vortagesschluss - 1
    return hoechstens(gap, CFG["aktie_gap_min"]), round(gap * 100, 2)


def fokuslisten_kandidat(schluss_serie, tief_serie, rs_rating):
    """Die Bedingungen, die schon am Vorabend feststehen.

    schluss_serie und tief_serie sind Tageswerte bis einschließlich
    gestern, chronologisch. Der Gap kommt erst am Morgen dazu und wird
    hier bewusst NICHT geprüft."""
    if len(schluss_serie) < CFG["ema_lang"] + 1:
        return {"ok": False, "grund": "zu wenig Historie"}

    kurs = float(schluss_serie[-1])
    ema21 = _ema(schluss_serie, CFG["ema_kurz"])
    ema50 = _ema(schluss_serie, CFG["ema_lang"])
    ueber_emas = kurs > ema21 and kurs > ema50

    tief_52w = min(tief_serie[-252:]) if tief_serie else 0
    ueber_tief = (kurs / tief_52w - 1) if tief_52w > 0 else 0
    tief_ok = ueber_tief >= CFG["min_ueber_tief"]

    rs_ok = rs_rating is not None and rs_rating > CFG["rs_min"]
    return {
        "ok": bool(ueber_emas and tief_ok and rs_ok),
        "ueber_emas": ueber_emas, "ema21": round(ema21, 2),
        "ema50": round(ema50, 2),
        "ueber_52w_tief_pct": round(ueber_tief * 100, 1),
        "tief_ok": tief_ok, "rs_rating": rs_rating, "rs_ok": rs_ok,
    }


def _ema(werte, spanne):
    """Exponentieller Schnitt, wie ihn pandas mit adjust=False rechnet —
    hier ohne pandas, weil es sonst nur für diese eine Zahl importiert
    werden müsste."""
    faktor = 2 / (spanne + 1)
    schnitt = float(werte[0])
    for w in werte[1:]:
        schnitt = float(w) * faktor + schnitt * (1 - faktor)
    return schnitt


# ---------------------------------------------------------------------------
# RS-Rating (IBD-Formel)
# ---------------------------------------------------------------------------

RS_QUARTALE = (63, 126, 189, 252)
RS_GEWICHTE = (0.40, 0.20, 0.20, 0.20)


def rs_rohwert(schluss_serie):
    """Gewichtete Rendite über die vier IBD-Quartale, das letzte doppelt."""
    if len(schluss_serie) < max(RS_QUARTALE) + 1:
        return None
    heute = float(schluss_serie[-1])
    rohwert = 0.0
    for tage, gewicht in zip(RS_QUARTALE, RS_GEWICHTE):
        start = float(schluss_serie[-1 - tage])
        if start <= 0:
            return None
        rohwert += gewicht * (heute / start - 1)
    return rohwert


def rs_rating_perzentil(alle_rohwerte, eigener):
    """Rang des eigenen Rohwerts gegen ALLE anderen, 1 bis 99.

    Gerhards Hinweis dazu: Aussagekräftig wird das erst mit einem
    marktweiten Universum. Gegen die eigene Kernliste gerechnet ist es
    eine Näherung — sie bleibt, bis der marktweite Scanner steht."""
    werte = [r for r in alle_rohwerte if r is not None]
    if not werte or eigener is None:
        return None
    rang = sum(1 for r in werte if r < eigener) / len(werte) * 100
    return round(max(1, min(99, rang)))


def rs_ratings_fuer_universum(kurse_je_ticker):
    """{Ticker: Schlusskursliste} → {Ticker: RS-Rating}."""
    rohwerte = {t: rs_rohwert(s) for t, s in kurse_je_ticker.items()}
    alle = list(rohwerte.values())
    return {t: rs_rating_perzentil(alle, r) for t, r in rohwerte.items()}


# ---------------------------------------------------------------------------
# Die Volumen-Signatur
# ---------------------------------------------------------------------------

def volumen_signatur(verlauf, v50, index, kurve=None):
    """Prüft Anflug, Sprung und Nachhaltigkeit an der Kreuzung.

    verlauf: Liste von Punkten, chronologisch, je Punkt ein dict mit
        "minute" (Minuten seit Handelsbeginn), "kurs" und "kum_volumen"
        (KUMULIERTES Tagesvolumen, nicht das Volumen der einzelnen
        Kerze — der Strom liefert genau das).
    index: Position der Kreuzung im Verlauf.
    kurve: die EIGENE Volumenkurve dieser Aktie (Gerhard,
        06.08.2026). Ohne sie liefert volume_pct_change None,
        und die Signatur gilt als nicht pruefbar — es wird
        NICHT mit einer fremden Kurve gerechnet."""
    punkt = verlauf[index]
    minute = punkt["minute"]
    fruehphase = minute <= CFG["fruehe_phase_minuten"]

    # --- Anflug: der Punkt VOR der Kreuzung ---------------------------
    anflug_pct, anflug_ok = None, True
    if index > 0 and not fruehphase:
        vorher = verlauf[index - 1]
        anflug_pct = volumen.volume_pct_change(
            vorher["kum_volumen"], v50, kurve, vorher["minute"])
        anflug_ok = (anflug_pct is not None
                     and anflug_pct <= CFG["vol_anflug_max_pct"] + GRENZ_SPIEL)

    # --- Sprung: an der Kreuzung --------------------------------------
    sprung_pct = volumen.volume_pct_change(
        punkt["kum_volumen"], v50, kurve, minute)
    sprung_ok = (sprung_pct is not None
                 and sprung_pct >= CFG["vol_sprung_min_pct"] - GRENZ_SPIEL)

    # --- Hält der Sprung an? ------------------------------------------
    # Nur prüfbar, wenn es überhaupt schon spätere Punkte gibt. Solange
    # keine da sind, gilt die Bedingung als erfüllt — sonst könnte in den
    # ersten Sekunden nach der Kreuzung nie gemeldet werden.
    haelt_pct, haelt_an = None, True
    bis_minute = minute + CFG["sprung_bestaetigung_minuten"]
    spaeter = [p for p in verlauf[index + 1:] if p["minute"] <= bis_minute]
    if spaeter and sprung_pct is not None:
        letzter = spaeter[-1]
        haelt_pct = volumen.volume_pct_change(
            letzter["kum_volumen"], v50, kurve, letzter["minute"])
        haelt_an = (haelt_pct is not None
                    and haelt_pct >= sprung_pct * (1 - CFG["sprung_abfall_max"])
                                     - GRENZ_SPIEL)

    return {
        "ok": bool(anflug_ok and sprung_ok and haelt_an),
        "in_fruehphase": fruehphase,
        "anflug_pct": None if anflug_pct is None else round(anflug_pct, 1),
        "anflug_ok": anflug_ok,
        "sprung_pct": None if sprung_pct is None else round(sprung_pct, 1),
        "sprung_ok": sprung_ok,
        "haelt_an": haelt_an,
        "haelt_pct": None if haelt_pct is None else round(haelt_pct, 1),
    }


def pruefe(verlauf, vortagesschluss, v50, kurve=None):
    """Sucht im bisherigen Tagesverlauf die erste gültige Kreuzung.

    Rot heißt unter dem Vortagesschluss, grün darüber. Gezählt wird nur
    ein Wechsel von rot nach grün — und nur, wenn die Volumen-Signatur
    an dieser Stelle stimmt. Tut sie es nicht, wird weitergesucht: Die
    Aktie kann später noch einmal rot werden und es besser machen."""
    if not verlauf or not vortagesschluss:
        return None
    war_rot = False
    for i, punkt in enumerate(verlauf):
        kurs = float(punkt["kurs"])
        if kurs < vortagesschluss:
            war_rot = True
            continue
        if war_rot and kurs > vortagesschluss:
            sig = volumen_signatur(verlauf, v50, i, kurve)
            if sig["ok"]:
                return {
                    "strategie": "Red-to-Green",
                    "index": i, "minute": punkt["minute"], "kurs": kurs,
                    "vortagesschluss": vortagesschluss,
                    "signatur": sig,
                }
            war_rot = False        # diese Kreuzung zählt nicht
    return None


# ---------------------------------------------------------------------------
# Verlauf mitschreiben
# ---------------------------------------------------------------------------

def punkt_setzen(verlauf, minute, kurs, kum_volumen):
    """Einen Punkt in den Tagesverlauf schreiben, höchstens einen je Minute.

    Der Wächter prüft alle zwei Sekunden; würde jeder Durchlauf einen
    Punkt anlegen, wären es 11.700 je Aktie und Tag. Die Signatur rechnet
    ohnehin in Minuten, also gewinnt innerhalb einer Minute der jeweils
    letzte Wert."""
    if verlauf and verlauf[-1]["minute"] == minute:
        verlauf[-1]["kurs"] = kurs
        verlauf[-1]["kum_volumen"] = kum_volumen
        return verlauf
    verlauf.append({"minute": minute, "kurs": kurs,
                    "kum_volumen": kum_volumen})
    return verlauf


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

def selbsttest() -> int:
    fehler = []

    def pruefe_es(name, bedingung, zusatz=""):
        print(f"  {'ok  ' if bedingung else 'FEHL'} {name}"
              + (f" — {zusatz}" if zusatz else ""))
        if not bedingung:
            fehler.append(name)

    print("Red-to-Green, Selbsttest")
    # Feste Kurve, damit der Test nicht von volumenkurve.json abhängt:
    # gleichmäßiger Handel über den ganzen Tag. Dann ist der Anteil
    # bis Minute m genau m/390, und die Sollwerte lassen sich von Hand
    # nachrechnen.
    # Seit 06.08.2026 wird die Kurve UEBERGEBEN statt global gesetzt —
    # jede Aktie hat ihre eigene.
    testkurve = {m: m / volumen.HANDELSMINUTEN
                 for m in range(0, volumen.HANDELSMINUTEN + 1, 5)}
    v50 = 1_000_000.0

    pruefe_es("Regime scharf bei Nasdaq minus 2 %",
              regime_scharf(98.0, 100.0)[0] is True)
    pruefe_es("Regime stumm bei Nasdaq minus 1 %",
              regime_scharf(99.0, 100.0)[0] is False)
    pruefe_es("Aktien-Gap greift bei minus 6 %",
              aktien_gap(94.0, 100.0)[0] is True)
    pruefe_es("Aktien-Gap greift nicht bei minus 3 %",
              aktien_gap(97.0, 100.0)[0] is False)

    # Fokusliste: steigende Kurse, Tief weit unten, RS 95
    schluss = [50.0 + i * 0.2 for i in range(300)]
    tiefs = [30.0] + [s * 0.99 for s in schluss[1:]]
    k = fokuslisten_kandidat(schluss, tiefs, 95)
    pruefe_es("Fokusliste nimmt den starken Kandidaten", k["ok"],
              f"{k['ueber_52w_tief_pct']} % über dem Tief")
    pruefe_es("Fokusliste verwirft RS 80",
              not fokuslisten_kandidat(schluss, tiefs, 80)["ok"])

    # --- Der gültige Fall -------------------------------------------
    # 120 Minuten nach Eröffnung: Anteil 120/390 = 30,8 % des Tages.
    # Anflug soll trocken sein (genau Normaltempo), der Sprung doppelt.
    anteil = lambda m: m / volumen.HANDELSMINUTEN
    verlauf = []
    punkt_setzen(verlauf, 118, 99.0, v50 * anteil(118) * 1.00)   # rot, trocken
    punkt_setzen(verlauf, 119, 99.5, v50 * anteil(119) * 1.00)   # rot, trocken
    punkt_setzen(verlauf, 120, 100.5, v50 * anteil(120) * 2.00)  # grün, Sprung
    punkt_setzen(verlauf, 128, 101.0, v50 * anteil(128) * 1.95)  # hält
    treffer = pruefe(verlauf, 100.0, v50, testkurve)
    pruefe_es("Gültige Kreuzung wird gemeldet", treffer is not None,
              f"Sprung {treffer['signatur']['sprung_pct']} %, Anflug "
              f"{treffer['signatur']['anflug_pct']} %" if treffer else "")

    # --- Nasser Anflug: verworfen -----------------------------------
    nass = []
    punkt_setzen(nass, 119, 99.5, v50 * anteil(119) * 1.60)      # zu viel
    punkt_setzen(nass, 120, 100.5, v50 * anteil(120) * 2.00)
    punkt_setzen(nass, 128, 101.0, v50 * anteil(128) * 1.95)
    pruefe_es("Nasser Anflug wird verworfen", pruefe(nass, 100.0, v50, testkurve) is None)

    # --- Kein Sprung: verworfen -------------------------------------
    flau = []
    punkt_setzen(flau, 119, 99.5, v50 * anteil(119) * 1.00)
    punkt_setzen(flau, 120, 100.5, v50 * anteil(120) * 1.20)     # zu wenig
    pruefe_es("Fehlender Sprung wird verworfen",
              pruefe(flau, 100.0, v50, testkurve) is None)

    # --- Eintagsfliege: Sprung fällt wieder ab ----------------------
    fliege = []
    punkt_setzen(fliege, 119, 99.5, v50 * anteil(119) * 1.00)
    punkt_setzen(fliege, 120, 100.5, v50 * anteil(120) * 2.00)
    punkt_setzen(fliege, 129, 101.0, v50 * anteil(129) * 1.30)   # bricht ein
    pruefe_es("Abfallender Sprung wird verworfen",
              pruefe(fliege, 100.0, v50, testkurve) is None)

    # --- Frühphase: nasser Anflug ist erlaubt -----------------------
    frueh = []
    punkt_setzen(frueh, 9, 99.5, v50 * anteil(9) * 3.00)         # sehr nass
    punkt_setzen(frueh, 10, 100.5, v50 * anteil(10) * 3.00)      # Sprung
    punkt_setzen(frueh, 18, 101.0, v50 * anteil(18) * 2.90)
    t2 = pruefe(frueh, 100.0, v50, testkurve)
    pruefe_es("In den ersten 30 Minuten entfällt die Anflug-Bedingung",
              t2 is not None and t2["signatur"]["in_fruehphase"])

    # --- Nur grün, nie rot: keine Kreuzung --------------------------
    nur_gruen = []
    punkt_setzen(nur_gruen, 120, 101.0, v50 * anteil(120) * 2.00)
    pruefe_es("Ohne vorherige rote Phase keine Meldung",
              pruefe(nur_gruen, 100.0, v50, testkurve) is None)

    # --- Ein Punkt je Minute ----------------------------------------
    v = []
    for _ in range(30):
        punkt_setzen(v, 42, 100.0, 5.0)
    pruefe_es("Je Minute bleibt genau ein Punkt", len(v) == 1,
              f"{len(v)} Punkt(e) aus 30 Durchläufen")

    print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles bestanden.")
    return 1 if fehler else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Red-to-Green, Kapitel 9.")
    ap.add_argument("--selbsttest", action="store_true")
    args = ap.parse_args()
    sys.exit(selbsttest() if args.selbsttest else ap.print_help() or 0)
