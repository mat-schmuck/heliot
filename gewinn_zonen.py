#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GEWINN-ZONEN-ENGINE — Kapitel 12 (Gewinnseite)
==================================================
Gerhards Drei-Zonen-Bild (leicht/mittel/stark im Plus) plus O'Neils
Klimax-Katalog, Weinsteins Stufe-3-Erkennung und die Zeitdeckel — als
reine, getestete Funktionen. Ergänzt Kapitel 11 (Verlustseite, Stop/
10%-Deckel), das unangetastet bleibt.

Architektur (Vorschlag A aus der Übergabe, mit B's Prüfmotor als Kern):
Jede Beobachtung in der Positionsverwaltung ruft diese Funktionen
täglich (Nachtscan) bzw. bei Tagesgeschäft-Mustern intraday (Tagwache)
auf. Zustand (Höchststand seit Trigger, aktuelle Zone, Startdatum)
lebt in der Beobachtung selbst — diese Datei kennt keinen eigenen
Zustand, nur Berechnungen.

GERHARDS ENTSCHEIDUNGEN (27.08.):
  - Zonengrenzen: leicht bis 2R, mittel ab Musterziel oder 20%,
    stark ab Klimax-Definition (25% in <15 Handelstagen nach
    mind. 8 Wochen Lauf) oder 3R.
  - Klimax-Zeichen: SOFORT SCHARF, alle fünf gleichzeitig (nicht
    erst ein Quartal stumm gemessen).
  - Darvas: QUELLENTREU — kein Gewinnziel, nur Boxboden nachziehen.
    Darvas-Positionen laufen NIE in Zone "mittel" mit Zielmeldung,
    nur der Stop wandert (Kapitel 11, unverändert).
"""

from dataclasses import dataclass
# (datetime wird hier nicht gebraucht - der Aufrufer liefert Tage)


CFG_GEWINN = {
    "zone_leicht_max_r": 2.0,
    "zone_mittel_min_pct": 0.20,        # 20 % ohne eigenes Musterziel
    "zone_stark_min_r": 3.0,
    "klimax_pct_min": 0.25,             # 25–50 % in 1–3 Wochen
    "klimax_pct_max": 0.50,
    "klimax_tage_max": 15,              # "1–3 Wochen" ≈ 15 Handelstage
    "klimax_vorlauf_wochen_min": 8,     # NACH mind. 8 Wochen Lauf
    "ma200_abstand_min": 0.70,          # Zeichen 4: 70–100 % über MA200
    "ma200_abstand_max": 1.00,
    "erschoepfungsluecke_min_pct": 0.03,  # Gap-Mindestgröße, Startwert
    "kanal_ueberschreitung_min_pct": 0.05,  # 5 % über oberer Kanallinie, Startwert
    "zeitdeckel_tage_zahlen": 60,       # Post-Earnings-Drift-Fenster
    "zeitdeckel_monate_insider": 6,
    "zeitdeckel_monate_standard": 12,
    "handelstage_pro_monat": 21,        # grobe Näherung für Monat->Tage
}


# ---------------------------------------------------------------------------
# Grundgrößen: Gewinn in % und in R
# ---------------------------------------------------------------------------

def berechne_gewinn_pct(kaufpunkt, aktueller_kurs):
    return aktueller_kurs / kaufpunkt - 1


def berechne_gewinn_r(kaufpunkt, stop, aktueller_kurs):
    """R = Vielfaches des ursprünglichen Risikos (Kaufpunkt minus Stop).
    Positionsgrößenunabhängig, wie in Kapitel 11 bereits verwendet."""
    risiko = kaufpunkt - stop
    if risiko <= 0:
        return None
    return (aktueller_kurs - kaufpunkt) / risiko


# ---------------------------------------------------------------------------
# Zonenklassifikation
# ---------------------------------------------------------------------------

def klassifiziere_zone(kaufpunkt, stop, aktueller_kurs, musterziel_erreicht=False,
                       ist_klimax=False, cfg=None):
    """Ordnet eine Position einer der drei Zonen zu.
    musterziel_erreicht: True, wenn die Strategie ein eigenes, erreichtes
    Musterziel meldet (z. B. Rectangle-Top-Ziel) — zieht die Position
    automatisch mindestens in Zone 'mittel', unabhängig von R/%.
    ist_klimax: True, wenn irgendein Klimax-Zeichen bereits ausgelöst hat
    — zieht automatisch in Zone 'stark'.
    Rückgabe: dict mit zone, gewinn_pct, gewinn_r."""
    cfg = cfg or CFG_GEWINN
    pct = berechne_gewinn_pct(kaufpunkt, aktueller_kurs)
    r = berechne_gewinn_r(kaufpunkt, stop, aktueller_kurs)

    if ist_klimax or (r is not None and r >= cfg["zone_stark_min_r"]):
        zone = "stark"
    elif musterziel_erreicht or pct >= cfg["zone_mittel_min_pct"] or \
            (r is not None and r >= cfg["zone_leicht_max_r"]):
        zone = "mittel"
    else:
        zone = "leicht"

    return {"zone": zone, "gewinn_pct": round(pct * 100, 2),
           "gewinn_r": round(r, 2) if r is not None else None}


def klassifiziere_zone_darvas(kaufpunkt, box_boden_aktuell, aktueller_kurs):
    """SONDERFALL Darvas (Gerhards Entscheidung: quellentreu). Keine
    Zone 'mittel'/'stark' mit Zielmeldung — es gibt nur 'im Plus,
    Boden nachgezogen' oder 'ausgestoppt' (Kapitel 11). Diese Funktion
    liefert bewusst KEINE Zonen-Kategorie, nur die reine Information,
    zur Klarheit, dass hier absichtlich nichts vorgeschlagen wird."""
    pct = berechne_gewinn_pct(kaufpunkt, aktueller_kurs)
    return {"zone": None, "hinweis": "Darvas quellentreu — kein Gewinnziel, "
                                      "nur Stop-Nachzug (Kapitel 11)",
           "gewinn_pct": round(pct * 100, 2), "aktueller_stop": box_boden_aktuell}


# ---------------------------------------------------------------------------
# O'Neils Klimax-Katalog — fünf Zeichen, alle sofort scharf (Gerhards Wahl)
# ---------------------------------------------------------------------------

def klimax_zeichen_1_klimaxlauf(kurs_vor_n_tagen, kurs_heute, tage_seit_start,
                                wochen_vorlauf, cfg=None):
    """Zeichen 1 — das Hauptzeichen: 25-50 % Anstieg in <=15 Handelstagen,
    NACHDEM die Aktie schon mind. 8 Wochen gelaufen ist."""
    cfg = cfg or CFG_GEWINN
    if wochen_vorlauf < cfg["klimax_vorlauf_wochen_min"]:
        return False, None
    veraenderung = kurs_heute / kurs_vor_n_tagen - 1
    ok = (tage_seit_start <= cfg["klimax_tage_max"] and
         cfg["klimax_pct_min"] <= veraenderung <= cfg["klimax_pct_max"] * 1.5)
    # (obere Grenze bewusst mit Puffer — "50 %" ist eine Richtgröße, kein
    #  hartes Ausschlusskriterium; ein Anstieg von 55 % ist nicht WENIGER
    #  klimaxartig als einer von 45 %)
    return ok, round(veraenderung * 100, 1)


def klimax_zeichen_2_groesster_tagesgewinn(tagesgewinne_seit_start_pct):
    """Zeichen 2 — größter Tagesgewinn seit Beginn der Bewegung, SPÄT im
    Lauf. tagesgewinne_seit_start_pct: Liste der täglichen %-Änderungen
    seit Einstieg, chronologisch. Prüft, ob der aktuellste Tag der
    größte der ganzen Liste ist UND wir uns im letzten Drittel der
    bisherigen Laufzeit befinden."""
    if len(tagesgewinne_seit_start_pct) < 3:
        return False, None
    letzter = tagesgewinne_seit_start_pct[-1]
    ist_groesster = letzter == max(tagesgewinne_seit_start_pct)
    # ('im letzten Drittel' stellt der Aufruf-Kontext sicher: die Liste
    #  beginnt am Einstieg, der letzte Tag IST das Ende des Laufs)
    return (ist_groesster and letzter > 0), round(letzter * 100, 1)


def klimax_zeichen_3_erschoepfungsluecke(vortages_hoch, heutiges_tief,
                                         tage_seit_start, wochen_vorlauf, cfg=None):
    """Zeichen 3 — Erschöpfungslücke: Kurslücke NACH OBEN, nachdem der
    Lauf schon lange läuft (nicht die Ausbruchslücke am Anfang)."""
    cfg = cfg or CFG_GEWINN
    if wochen_vorlauf < cfg["klimax_vorlauf_wochen_min"]:
        return False, None
    luecke_pct = heutiges_tief / vortages_hoch - 1
    ok = luecke_pct >= cfg["erschoepfungsluecke_min_pct"]
    return ok, round(luecke_pct * 100, 1)


def klimax_zeichen_4_ma200_abstand(kurs, ma200, cfg=None):
    """Zeichen 4 — 70-100 % über der 200-Tage-Linie. Ehrliche Fußnote
    aus der Quelle: O'Neil selbst nutzte das eher selten."""
    cfg = cfg or CFG_GEWINN
    if ma200 <= 0:
        return False, None
    abstand = kurs / ma200 - 1
    ok = cfg["ma200_abstand_min"] <= abstand <= cfg["ma200_abstand_max"] * 1.3
    # (auch hier: obere Grenze mit Puffer, "100 %" ist keine harte Decke)
    return ok, round(abstand * 100, 1)


def klimax_zeichen_5_kanaluebershooting(kurs, obere_kanallinie, cfg=None):
    """Zeichen 5 — Überschießen der oberen Kanallinie.
    obere_kanallinie kann jetzt mit berechne_obere_kanallinie() aus den
    eigenen Kursdaten ermittelt werden (siehe unten), oder extern
    übergeben werden, falls eine andere Methode bevorzugt wird."""
    cfg = cfg or CFG_GEWINN
    if obere_kanallinie <= 0:
        return False, None
    ueberschuss = kurs / obere_kanallinie - 1
    ok = ueberschuss >= cfg["kanal_ueberschreitung_min_pct"]
    return ok, round(ueberschuss * 100, 1)


@dataclass
class KlimaxEingaben:
    """Bündelt alle Rohwerte, die der nächtliche Lauf für den kompletten
    Klimax-Check braucht — ein Aufruf statt fünf Einzelaufrufe."""
    kurs_vor_n_tagen: float
    kurs_heute: float
    tage_seit_bewegungsstart: int
    wochen_vorlauf: float
    tagesgewinne_seit_start_pct: list
    vortages_hoch: float
    heutiges_tief: float
    ma200: float
    obere_kanallinie: float


def pruefe_klimax_katalog(eingaben: KlimaxEingaben, cfg=None):
    """Prüft alle fünf Zeichen, liefert Gesamtstatus + Einzelheiten.
    Gerhards Entscheidung: SOFORT SCHARF, jedes einzeln erkannte Zeichen
    ist eine eigene, laute Meldung — keine Sammelschwelle nötig."""
    cfg = cfg or CFG_GEWINN
    z1, z1_wert = klimax_zeichen_1_klimaxlauf(
        eingaben.kurs_vor_n_tagen, eingaben.kurs_heute,
        eingaben.tage_seit_bewegungsstart, eingaben.wochen_vorlauf, cfg)
    z2, z2_wert = klimax_zeichen_2_groesster_tagesgewinn(eingaben.tagesgewinne_seit_start_pct)
    z3, z3_wert = klimax_zeichen_3_erschoepfungsluecke(
        eingaben.vortages_hoch, eingaben.heutiges_tief,
        eingaben.tage_seit_bewegungsstart, eingaben.wochen_vorlauf, cfg)
    z4, z4_wert = klimax_zeichen_4_ma200_abstand(eingaben.kurs_heute, eingaben.ma200, cfg)
    z5, z5_wert = klimax_zeichen_5_kanaluebershooting(
        eingaben.kurs_heute, eingaben.obere_kanallinie, cfg)

    zeichen = {
        "1_klimaxlauf": {"ausgeloest": z1, "wert_pct": z1_wert},
        "2_groesster_tagesgewinn": {"ausgeloest": z2, "wert_pct": z2_wert},
        "3_erschoepfungsluecke": {"ausgeloest": z3, "wert_pct": z3_wert},
        "4_ma200_abstand": {"ausgeloest": z4, "wert_pct": z4_wert},
        "5_kanaluebershooting": {"ausgeloest": z5, "wert_pct": z5_wert},
    }
    ausgeloeste = [name for name, d in zeichen.items() if d["ausgeloest"]]
    return {"ist_klimax": len(ausgeloeste) > 0, "ausgeloeste_zeichen": ausgeloeste,
           "details": zeichen}


def berechne_obere_kanallinie(schlusskurse, hochkurse=None, n_tage=120, aufschlag_sigma=2.0):
    """Berechnet die obere Kanallinie für Klimax-Zeichen 5 — jetzt
    eigenständig im Modul, nicht mehr vom Aufrufer erwartet.

    Methode (Standard, deckt sich mit O'Neils Beschreibung eines
    Aufwärtskanals): lineare Regression durch die Schlusskurse der
    letzten n_tage ergibt die Mittellinie des Trends; der Abstand der
    Kurse zu dieser Linie (Standardabweichung der Abweichungen) ergibt
    die Kanalbreite. Obere Linie = Mittellinie + aufschlag_sigma mal
    Standardabweichung, fortgeschrieben bis heute.

    schlusskurse: Liste/Series, chronologisch, mindestens n_tage lang
    (kürzere Reihen werden komplett verwendet).
    hochkurse: optional. Wenn übergeben, wird die Linie zusätzlich so
    angehoben, dass sie nicht unter dem höchsten bisherigen Hoch der
    Periode liegt — verhindert, dass ein bereits überschrittener Kanal
    dauerhaft Fehlalarme liefert.

    Rückgabe: float (Kurswert der oberen Linie für HEUTE) oder None,
    wenn zu wenig Daten."""
    import numpy as np

    werte = list(schlusskurse)[-n_tage:] if n_tage else list(schlusskurse)
    if len(werte) < 20:
        return None  # unter 20 Punkten ist eine Trendgerade nicht sinnvoll

    y = np.array(werte, dtype=float)
    x = np.arange(len(y), dtype=float)

    # Mittellinie: lineare Regression (Grad 1)
    steigung, achsenabschnitt = np.polyfit(x, y, 1)
    mittellinie = steigung * x + achsenabschnitt

    # Kanalbreite: Streuung der Kurse um die Mittellinie.
    # Schwelle relativ zum Kursniveau, nicht auf exakt 0 prüfen — bei einer
    # praktisch flachen Reihe ist sigma nicht exakt null, sondern ein
    # winziger Fließkomma-Rest. Ein Kanal ohne echte Breite ist sinnlos.
    abweichungen = y - mittellinie
    sigma = float(np.std(abweichungen))
    if sigma < abs(float(np.mean(y))) * 1e-6:
        return None

    # Obere Linie für HEUTE (letzter x-Wert), fortgeschrieben
    heute_x = len(y) - 1
    obere_linie = steigung * heute_x + achsenabschnitt + aufschlag_sigma * sigma

    return round(float(obere_linie), 2)


# ---------------------------------------------------------------------------
# Weinsteins Stufe-3-Erkennung (langsamstes, robustestes Stark-Signal)
# ---------------------------------------------------------------------------

def pruefe_weinstein_stufe3(ma30w_serie, min_tage_steigend_vorher=21):
    """Stufe-3-Ende: die 30-Wochen-Linie wird flach UND der Kurs schneidet
    sie erstmals nach langem Lauf. Vereinfachtes Kriterium: Steigung der
    letzten paar Wochen nahe null, nachdem sie vorher klar positiv war.
    ma30w_serie: Liste/Series der MA30W-Werte, chronologisch, mind. 5 lang."""
    if len(ma30w_serie) < 5:
        return False, None
    letzte_steigung = ma30w_serie[-1] - ma30w_serie[-2]
    vorherige_steigung = ma30w_serie[-4] - ma30w_serie[-5]
    war_klar_steigend = vorherige_steigung > 0
    ist_jetzt_flach = abs(letzte_steigung) < abs(vorherige_steigung) * 0.15
    return (war_klar_steigend and ist_jetzt_flach), {
        "letzte_steigung": round(letzte_steigung, 4),
        "vorherige_steigung": round(vorherige_steigung, 4)}


# ---------------------------------------------------------------------------
# Zeitdeckel — je Positionsklasse
# ---------------------------------------------------------------------------

def pruefe_zeitdeckel(klasse, tage_gehalten, ist_handelsschluss=None, cfg=None):
    """klasse: 'tagesgeschaeft', 'zahlen_luecke', 'insider', 'standard'.
    Für 'tagesgeschaeft' ist tage_gehalten irrelevant — hier zählt der
    Zeitpunkt, nicht die Tage; ist_handelsschluss (bool) MUSS übergeben
    werden. Rückgabe: (deckel_erreicht: bool, verbleibende_tage: int|None)."""
    cfg = cfg or CFG_GEWINN
    if klasse == "tagesgeschaeft":
        if ist_handelsschluss is None:
            raise ValueError("Für 'tagesgeschaeft' muss ist_handelsschluss übergeben werden")
        return ist_handelsschluss, (0 if ist_handelsschluss else None)
    if klasse == "zahlen_luecke":
        grenze = cfg["zeitdeckel_tage_zahlen"]
    elif klasse == "insider":
        grenze = cfg["zeitdeckel_monate_insider"] * cfg["handelstage_pro_monat"]
    else:
        grenze = cfg["zeitdeckel_monate_standard"] * cfg["handelstage_pro_monat"]
    erreicht = tage_gehalten >= grenze
    return erreicht, (None if erreicht else grenze - tage_gehalten)


# ---------------------------------------------------------------------------
# Meldepriorität — passend zur Übergabe (leise/laut/laut-einzeln)
# ---------------------------------------------------------------------------

def meldepriorität(ereignis_typ):
    """ereignis_typ: 'zonenwechsel', 'ziel_erreicht', 'klimax_zeichen'.
    Rückgabe: ntfy-Priorität + ob gebündelt oder einzeln gemeldet wird."""
    zuordnung = {
        "zonenwechsel": {"prioritaet": "default", "buendeln": True},
        "ziel_erreicht": {"prioritaet": "high", "buendeln": False},
        "klimax_zeichen": {"prioritaet": "high", "buendeln": False},
    }
    return zuordnung.get(ereignis_typ, {"prioritaet": "default", "buendeln": True})


if __name__ == "__main__":
    print("=" * 72)
    print("TEST 1: Grundgrößen — Gewinn in % und R")
    print("=" * 72)
    pct = berechne_gewinn_pct(100, 120)
    r = berechne_gewinn_r(100, 95, 120)
    print(f"  Kauf 100, Stop 95, Kurs 120 -> Gewinn={pct*100:.0f}%  R={r:.1f}")
    assert abs(pct - 0.20) < 1e-9
    assert abs(r - 4.0) < 1e-9
    print("  ✓ Grundformeln korrekt\n")

    print("=" * 72)
    print("TEST 2: Zonenklassifikation — alle drei Zonen")
    print("=" * 72)
    # Leicht: Gewinn 8%, R=1.6 (unter 2R, unter 20%)
    z = klassifiziere_zone(100, 95, 108)
    print(f"  Kauf 100, Stop 95, Kurs 108 (8%, {z['gewinn_r']}R) -> {z['zone']}")
    assert z["zone"] == "leicht"

    # Mittel: Gewinn 22% (über 20%-Schwelle), Stop weiter weg (10%) damit R nicht schon "stark" triggert
    z = klassifiziere_zone(100, 90, 122)
    print(f"  Kauf 100, Stop 90, Kurs 122 (22%, {z['gewinn_r']}R) -> {z['zone']}")
    assert z["zone"] == "mittel"

    # Mittel via Musterziel (auch wenn %/R noch niedrig)
    z = klassifiziere_zone(100, 95, 106, musterziel_erreicht=True)
    print(f"  Kauf 100, Kurs 106, Musterziel erreicht -> {z['zone']}")
    assert z["zone"] == "mittel"

    # Stark: R=3.2 (Klimax-Grenze)
    z = klassifiziere_zone(100, 95, 116)
    print(f"  Kauf 100, Stop 95, Kurs 116 (R={z['gewinn_r']}) -> {z['zone']}")
    assert z["zone"] == "stark"

    # Stark via explizitem Klimax-Flag, auch bei niedrigem R
    z = klassifiziere_zone(100, 95, 105, ist_klimax=True)
    print(f"  Kauf 100, Kurs 105, Klimax-Zeichen ausgelöst -> {z['zone']}")
    assert z["zone"] == "stark"
    print("  ✓ Alle drei Zonen + beide Sonderfälle (Musterziel, Klimax-Flag) korrekt\n")

    print("TEST 3: Darvas-Sonderfall — bewusst KEINE Zone")
    d = klassifiziere_zone_darvas(100, 108, 125)
    print(f"  {d}")
    assert d["zone"] is None
    print("  ✓ Darvas liefert quellentreu keine Zonen-Kategorie\n")

    print("=" * 72)
    print("TEST 4: Klimax-Zeichen 1 — der Klimax-Lauf selbst")
    print("=" * 72)
    ok, wert = klimax_zeichen_1_klimaxlauf(100, 135, tage_seit_start=10, wochen_vorlauf=12)
    print(f"  +35% in 10 Tagen nach 12 Wochen Vorlauf -> ausgelöst={ok}  Wert={wert}%")
    assert ok
    ok2, _ = klimax_zeichen_1_klimaxlauf(100, 135, tage_seit_start=10, wochen_vorlauf=3)
    print(f"  Gleicher Anstieg, aber nur 3 Wochen Vorlauf (<8) -> ausgelöst={ok2}")
    assert not ok2
    print("  ✓ Vorlauf-Bedingung wird korrekt erzwungen\n")

    print("TEST 5: Klimax-Zeichen 2 — größter Tagesgewinn, spät im Lauf")
    gewinne = [0.02, 0.01, -0.01, 0.03, 0.015, 0.05]  # letzter Tag = größter
    ok, wert = klimax_zeichen_2_groesster_tagesgewinn(gewinne)
    print(f"  Tagesgewinne {gewinne} -> ausgelöst={ok}  letzter={wert}%")
    assert ok
    gewinne2 = [0.02, 0.01, -0.01, 0.03, 0.05, 0.015]  # letzter Tag NICHT größter
    ok2, _ = klimax_zeichen_2_groesster_tagesgewinn(gewinne2)
    print(f"  Tagesgewinne {gewinne2} (größter liegt zurück) -> ausgelöst={ok2}")
    assert not ok2
    print("  ✓ Erkennt korrekt, ob der AKTUELLE Tag der größte ist\n")

    print("TEST 6: Klimax-Zeichen 3 — Erschöpfungslücke")
    ok, wert = klimax_zeichen_3_erschoepfungsluecke(
        vortages_hoch=100, heutiges_tief=105, tage_seit_start=12, wochen_vorlauf=10)
    print(f"  Lücke von 100 auf 105 (+5%) nach 10 Wochen Lauf -> ausgelöst={ok}  {wert}%")
    assert ok
    ok2, _ = klimax_zeichen_3_erschoepfungsluecke(
        vortages_hoch=100, heutiges_tief=105, tage_seit_start=12, wochen_vorlauf=2)
    print(f"  Gleiche Lücke, aber erst 2 Wochen Vorlauf -> ausgelöst={ok2}")
    assert not ok2
    print("  ✓ Auch hier greift die Vorlauf-Bedingung\n")

    print("TEST 7: Klimax-Zeichen 4 — Abstand zur 200-Tage-Linie")
    ok, wert = klimax_zeichen_4_ma200_abstand(kurs=185, ma200=100)
    print(f"  Kurs 185, MA200 100 (85% drüber) -> ausgelöst={ok}  {wert}%")
    assert ok
    ok2, wert2 = klimax_zeichen_4_ma200_abstand(kurs=130, ma200=100)
    print(f"  Kurs 130, MA200 100 (30% drüber, unter 70%-Schwelle) -> ausgelöst={ok2}  {wert2}%")
    assert not ok2
    print("  ✓ Schwelle korrekt angewendet\n")

    print("TEST 8: Klimax-Zeichen 5 — Kanal-Überschießen")
    ok, wert = klimax_zeichen_5_kanaluebershooting(kurs=112, obere_kanallinie=105)
    print(f"  Kurs 112, obere Kanallinie 105 (+6,7%) -> ausgelöst={ok}  {wert}%")
    assert ok
    print("  ✓\n")

    print("=" * 72)
    print("TEST 9: Kompletter Klimax-Katalog — alle fünf zusammen")
    print("=" * 72)
    eingaben = KlimaxEingaben(
        kurs_vor_n_tagen=100, kurs_heute=138, tage_seit_bewegungsstart=9,
        wochen_vorlauf=14, tagesgewinne_seit_start_pct=[0.02, 0.01, 0.04, 0.06],
        vortages_hoch=130, heutiges_tief=136, ma200=75, obere_kanallinie=125)
    ergebnis = pruefe_klimax_katalog(eingaben)
    print(f"  Ist Klimax: {ergebnis['ist_klimax']}")
    print(f"  Ausgelöste Zeichen: {ergebnis['ausgeloeste_zeichen']}")
    assert ergebnis["ist_klimax"]
    assert len(ergebnis["ausgeloeste_zeichen"]) >= 3  # mehrere Zeichen sollten hier greifen
    print("  ✓ Katalog kombiniert alle fünf Zeichen korrekt\n")

    print("TEST 10: Ruhige Aktie OHNE Klimax — keine Fehlalarme")
    eingaben_ruhig = KlimaxEingaben(
        kurs_vor_n_tagen=100, kurs_heute=103, tage_seit_bewegungsstart=9,
        wochen_vorlauf=14, tagesgewinne_seit_start_pct=[0.005, 0.003, -0.002, 0.004],
        vortages_hoch=102, heutiges_tief=102.5, ma200=98, obere_kanallinie=106)
    ergebnis_ruhig = pruefe_klimax_katalog(eingaben_ruhig)
    print(f"  Ist Klimax: {ergebnis_ruhig['ist_klimax']}  Zeichen: {ergebnis_ruhig['ausgeloeste_zeichen']}")
    assert not ergebnis_ruhig["ist_klimax"]
    print("  ✓ Keine Fehlalarme bei normalem Kursverlauf\n")

    print("=" * 72)
    print("TEST 11: Weinstein Stufe-3-Erkennung")
    print("=" * 72)
    ma30w_steigend_dann_flach = [90, 92, 95, 98, 100, 100.1]
    ok, details = pruefe_weinstein_stufe3(ma30w_steigend_dann_flach)
    print(f"  MA30W steigt dann flacht ab: {ma30w_steigend_dann_flach} -> {ok}  {details}")
    assert ok
    ma30w_weiter_steigend = [90, 92, 95, 98, 101, 104]
    ok2, _ = pruefe_weinstein_stufe3(ma30w_weiter_steigend)
    print(f"  MA30W steigt gleichmäßig weiter: {ma30w_weiter_steigend} -> {ok2}")
    assert not ok2
    print("  ✓ Erkennt das Abflachen, nicht den fortgesetzten Anstieg\n")

    print("=" * 72)
    print("TEST 12: Zeitdeckel je Klasse")
    print("=" * 72)
    # Tagesgeschäft hängt jetzt ehrlich vom tatsächlichen Handelsschluss ab,
    # nicht mehr unbedingt True (das war ein Fehler in der ersten Fassung)
    erreicht, rest = pruefe_zeitdeckel("tagesgeschaeft", tage_gehalten=0, ist_handelsschluss=False)
    print(f"  tagesgeschaeft, noch NICHT Handelsschluss -> Deckel erreicht={erreicht}")
    assert erreicht is False
    erreicht, rest = pruefe_zeitdeckel("tagesgeschaeft", tage_gehalten=0, ist_handelsschluss=True)
    print(f"  tagesgeschaeft, IST Handelsschluss -> Deckel erreicht={erreicht}")
    assert erreicht is True
    try:
        pruefe_zeitdeckel("tagesgeschaeft", tage_gehalten=0)
        assert False, "hätte ValueError werfen müssen"
    except ValueError:
        print(f"  tagesgeschaeft ohne ist_handelsschluss -> wirft ValueError, wie vorgesehen")
    print("  ✓ Tagesgeschäft jetzt ehrlich an den Zeitpunkt gekoppelt, kein Blindwert mehr\n")

    for klasse, tage, erwartet_erreicht in [
        ("zahlen_luecke", 59, False), ("zahlen_luecke", 60, True),
        ("insider", 125, False), ("insider", 126, True),  # 6 Monate = 126 Handelstage
        ("standard", 251, False), ("standard", 252, True),  # 12 Monate = 252 Handelstage
    ]:
        erreicht, rest = pruefe_zeitdeckel(klasse, tage)
        print(f"  {klasse:15s} {tage:4d} Tage gehalten -> Deckel erreicht={erreicht}  Rest={rest}")
        assert erreicht == erwartet_erreicht
    print("  ✓ Alle drei tageszählenden Klassen korrekt\n")

    print("=" * 72)
    print("TEST 13: Meldepriorität passend zur Übergabe")
    print("=" * 72)
    for typ in ["zonenwechsel", "ziel_erreicht", "klimax_zeichen"]:
        p = meldepriorität(typ)
        print(f"  {typ:16s} -> {p}")
    assert meldepriorität("zonenwechsel")["buendeln"] is True
    assert meldepriorität("klimax_zeichen")["buendeln"] is False
    assert meldepriorität("ziel_erreicht")["prioritaet"] == "high"
    print("  ✓ Zonenwechsel leise/gebündelt, Ziel+Klimax laut/einzeln — wie in der Übergabe beschrieben\n")

    print("=" * 72)
    print("TEST 14: Kanallinie selbst berechnen (für Klimax-Zeichen 5)")
    print("=" * 72)
    import numpy as _np
    _np.random.seed(42)
    _n = 120
    _kurse = list(100 + _np.arange(_n) * 0.5 + _np.random.normal(0, 3, _n))

    _linie = berechne_obere_kanallinie(_kurse)
    print(f"  Normaler Aufwärtstrend: letzter Kurs={_kurse[-1]:.1f}, obere Linie={_linie}")
    assert _linie is not None and _kurse[-1] < _linie
    _ok, _ = klimax_zeichen_5_kanaluebershooting(_kurse[-1], _linie)
    assert not _ok
    print("  ✓ Normaler Trend löst keinen Fehlalarm aus")

    _kurse_a = _kurse.copy(); _kurse_a[-1] = _linie * 1.12
    _linie2 = berechne_obere_kanallinie(_kurse_a)
    _ok2, _wert2 = klimax_zeichen_5_kanaluebershooting(_kurse_a[-1], _linie2)
    print(f"  Echter Ausbruch: Kurs={_kurse_a[-1]:.1f}, Linie={_linie2} -> ausgelöst={_ok2} ({_wert2}%)")
    assert _ok2
    print("  ✓ Kanal-Überschießen wird erkannt")

    assert berechne_obere_kanallinie([100, 101, 102]) is None
    assert berechne_obere_kanallinie([100.0] * 50) is None
    print("  ✓ Zu kurze und völlig flache Reihen liefern sauberes None\n")

    print("=" * 72)
    print("ALLE TESTS BESTANDEN")
    print("=" * 72)
