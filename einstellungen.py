"""EINSTELLUNGEN VON APP UND WAECHTER (Mathias und Gerhard, 23.09.2026)

WOFUER: Der Reiter Einstellungen der App legt hier fest, welche Chartmuster
und Strategien einen Alarm ueber ntfy ausloesen, wie die App aussieht und
welcher Ton nach einer erfolgreichen Aktion spielt. Mathias, 23.09.2026:
"wir meinen die Alarme fuer ntfy, da moechten wir waehlen koennen, welche
Chartmuster zur Anwendung kommen."

WO: einstellungen.json im oeffentlichen Repo auf main. Die App schreibt die
Datei ueber die GitHub-Schnittstelle (nur voller Zugang), der Waechter liest
sie in jedem Datentakt frisch aus origin/main, genau wie die einzeln
ueberwachten Aktien. Eine Abwahl wirkt also binnen einer Minute.

WAS ABGEWAEHLT HEISST: keine Meldung ueber ntfy und kein Signal an den
Handels-Bot, der seine Signale ebenfalls ueber ntfy bekommt. Der Nachtscan
rechnet weiter, und die Kaufpunkte stehen weiter in der Mappe. Der Waechter
prueft ein abgewaehltes Muster dagegen gar nicht mehr; das Trigger-Logbuch
vermerkt dessen Ausbrueche also nicht (ob es das soll, steht im
Fragenkatalog).

WAS NIE ABWAEHLBAR IST: Ausstiege, Stops, Gewinnzonen, die schlussnahen
Befunde und die Beobachtungen offener Positionen. Sie gehoeren zu
Positionen, die schon bestehen, und ein Klick darf keine Position ohne
Stop-Ueberwachung lassen (vorlaeufige Festlegung, steht im Fragenkatalog).

NEUES IST EINGESCHALTET: Die Datei fuehrt nur, was ABGEWAEHLT ist. Ein neuer
Eintrag im Register, ein unbekannter Name oder eine fehlende oder kaputte
Datei heisst deshalb immer: Alarm an. Eher ein Alarm zu viel als ein
stiller Ausfall.

Aufruf:
    python einstellungen.py --selbsttest
"""

import argparse
import json
import sys

DATEI = "einstellungen.json"

# Die Gruppen der Alarme in der Reihenfolge der Anzeige.
GRUPPEN = [
    ("kauf", "Kaufsignale aus Chartmustern"),
    ("ausweich", "Ausweichmarken für Aktien mit weniger als drei Mustern"),
    ("auskunft", "Chartmuster als Auskunft, ohne Kaufsignal"),
    ("weitere", "Weitere Kaufsignale"),
    ("info", "Weitere Auskünfte"),
]

# DAS REGISTER DER ABWAEHLBAREN ALARME. namen: die Strategienamen, wie sie
# in Mappe, Meldung und Logbuch stehen, genau so geschrieben; anfaenge:
# Namensanfaenge fuer Strategien, die ihren Namen um einen Zusatz
# verlaengern ("Shakeout-Spring, wartet auf Sekundaertest"). Die
# Gesamtpruefung achtet darauf, dass jede Strategie, die im System entstehen
# kann, hier einen Eintrag hat.
ALARME = [
    # Kaufpunkte aus dem Nachtscan, in der Reihenfolge von
    # pattern_scanner.PRIORITY
    {"schluessel": "htf", "gruppe": "kauf", "name": "High & Tight Flag",
     "namen": ["High & Tight Flag"],
     "erklaerung": "Ein Anstieg um mindestens 90 Prozent in höchstens 42 Handelstagen, danach eine enge Flagge "
                   "von höchstens 35 Kalendertagen; Alarm beim Ausbruch über die Flagge."},
    {"schluessel": "htf_innen", "gruppe": "kauf", "name": "HTF Innen-Einstieg",
     "namen": ["HTF Innen-Einstieg"],
     "erklaerung": "Der Einstieg innerhalb der Flagge einer High & Tight Flag; der Alarm kommt früher als beim "
                   "Ausbruch über die ganze Flagge."},
    {"schluessel": "vcp", "gruppe": "kauf", "name": "VCP",
     "namen": ["VCP"],
     "erklaerung": "Volatility Contraction Pattern: Trend Template erfüllt, dazu mindestens zwei immer engere "
                   "Rücksetzer mit austrocknendem Volumen; Alarm beim Ausbruch über den Pivot."},
    {"schluessel": "cup", "gruppe": "kauf", "name": "Cup & Handle",
     "namen": ["Cup & Handle"],
     "erklaerung": "Tasse mit Henkel auf Tageskerzen: eine runde Tasse, 12 bis 50 Prozent tief, mit einem Henkel im "
                   "oberen Drittel; Alarm beim Ausbruch über das Henkelhoch."},
    {"schluessel": "cup_woche", "gruppe": "kauf", "name": "Cup & Handle (Wochenbasis)",
     "namen": ["Cup & Handle (Wochenbasis)"],
     "erklaerung": "Dieselbe Tasse mit Henkel auf Wochenkerzen, also über einen längeren Zeitraum; Alarm beim "
                   "Ausbruch über das Henkelhoch."},
    {"schluessel": "darvas", "gruppe": "kauf", "name": "Darvas Box",
     "namen": ["Darvas Box"],
     "erklaerung": "Ein neues 52-Wochen-Hoch, danach eine Box aus mindestens drei plus drei Tagen; Alarm beim "
                   "Ausbruch über die Oberkante der Box. Läuft auf der Darvas-Liste und bei einzeln überwachten "
                   "Aktien."},
    {"schluessel": "earnings", "gruppe": "kauf", "name": "Earnings-Pullback",
     "namen": ["Earnings-Pullback"],
     "erklaerung": "Nach starken Quartalszahlen wird nicht der Sprung gekauft, sondern die erste ruhige "
                   "Konsolidierung darüber; Alarm beim Ausbruch aus dieser Konsolidierung."},
    {"schluessel": "ema", "gruppe": "kauf", "name": "EMA Crossback",
     "namen": ["EMA Crossback"],
     "erklaerung": "EMA Crossback nach Oliver Kell: der erste Rücksetzer an die 10- und 20-Tage-Linie nach ihrer "
                   "Rückeroberung; Alarm, wenn der Kurs das Hoch des Umkehrtags überschreitet."},
    {"schluessel": "rechteck", "gruppe": "kauf", "name": "Rectangle Top",
     "namen": ["Rectangle Top"],
     "erklaerung": "Eine waagrechte Handelsspanne mit mindestens zwei Berührungen oben und unten; Alarm einen Cent über "
                   "der Oberkante, wenn der Kurs zugleich über dem 21-Tage-Durchschnitt liegt."},
    {"schluessel": "shakeout", "gruppe": "kauf", "name": "Shakeout-Spring",
     "namen": [], "anfaenge": ["Shakeout-Spring", "Shakeout an starkem Level"],
     "erklaerung": "Eine Aktie im Aufwärtstrend unterschreitet kurz eine starke Unterstützungszone und erobert sie "
                   "am selben Tag zurück; Alarm, wenn der Test der Zone gehalten hat."},
    {"schluessel": "crash", "gruppe": "kauf", "name": "Crash-Support",
     "namen": ["Crash-Support"],
     "erklaerung": "Während einer Marktkorrektur: große, gesunde Unternehmen an einer starken Unterstützungszone; "
                   "Alarm beim Wiederanstieg."},
    # Ausweichmarken (pattern_scanner.fallback_points)
    {"schluessel": "fb_52w", "gruppe": "ausweich", "name": "Fallback: 52W-Hoch-Breakout",
     "namen": ["Fallback: 52W-Hoch-Breakout"],
     "erklaerung": "Eine Ersatzmarke für Aktien ohne genug Muster: Alarm knapp über dem 52-Wochen-Hoch."},
    {"schluessel": "fb_20t", "gruppe": "ausweich", "name": "Fallback: 20-Tage-Hoch (Pivot)",
     "namen": ["Fallback: 20-Tage-Hoch (Pivot)"],
     "erklaerung": "Eine Ersatzmarke: Alarm einen Cent über dem Hoch der letzten 20 Handelstage."},
    {"schluessel": "fb_ma50p", "gruppe": "ausweich", "name": "Fallback: MA50-Pullback",
     "namen": ["Fallback: MA50-Pullback"],
     "erklaerung": "Eine Ersatzmarke bei intaktem Trend: Alarm knapp über der 50-Tage-Linie nach einem Rücksetzer."},
    {"schluessel": "fb_ma50r", "gruppe": "ausweich", "name": "Fallback: MA50-Rückeroberung",
     "namen": ["Fallback: MA50-Rückeroberung"],
     "erklaerung": "Eine Ersatzmarke für Aktien unter der 50-Tage-Linie: Alarm, wenn der Kurs sie knapp "
                   "überschreitet."},
    {"schluessel": "fb_63t", "gruppe": "ausweich", "name": "Fallback: Quartals-Hoch (63 Tage)",
     "namen": ["Fallback: Quartals-Hoch (63 Tage)"],
     "erklaerung": "Eine Ersatzmarke: Alarm einen Cent über dem Hoch der letzten 63 Handelstage."},
    # Die sechs Alarm-Muster (alarm_muster.NAMEN), gemeldet als INFORMATION
    {"schluessel": "a_3wt", "gruppe": "auskunft", "name": "Three Weeks Tight",
     "namen": ["Three Weeks Tight"],
     "erklaerung": "Nach einem Anstieg schließen drei oder vier Wochen hintereinander jeweils sehr nah am Schluss der "
                   "Vorwoche; Auskunft beim Ausbruch über das Hoch dieser Wochen."},
    {"schluessel": "a_inside", "gruppe": "auskunft", "name": "Inside Day",
     "namen": ["Inside Day"],
     "erklaerung": "Ein Tag, dessen Hoch und Tief innerhalb des Vortags liegen, nach drei steigenden Tagen; Auskunft "
                   "beim Ausbruch über sein Hoch."},
    {"schluessel": "a_pocket", "gruppe": "auskunft", "name": "Pocket Pivot",
     "namen": ["Pocket Pivot"],
     "erklaerung": "Ein Aufwärtstag in oder knapp über einer Basis mit mehr Volumen als jeder Abwärtstag der letzten "
                   "zehn Handelstage; Auskunft beim Überschreiten seines Hochs."},
    {"schluessel": "a_ipo", "gruppe": "auskunft", "name": "IPO Base",
     "namen": ["IPO Base"],
     "erklaerung": "Die erste Basis einer frisch notierten Aktie, schon nach drei Wochen und 20 bis 50 Prozent tief; "
                   "Auskunft beim Ausbruch."},
    {"schluessel": "a_shakeout3", "gruppe": "auskunft", "name": "Shakeout plus drei",
     "namen": ["Shakeout plus drei"],
     "erklaerung": "Nach dem ersten scharfen Abverkauf aus einem Hoch: Auskunft, wenn der Kurs zehn Prozent über das "
                   "Tief dieses Abverkaufs steigt."},
    {"schluessel": "a_wick", "gruppe": "auskunft", "name": "Wick Play",
     "namen": ["Wick Play"],
     "erklaerung": "Eine Kerze mit langem Docht und kleinem Körper an einer markanten Stelle; Auskunft beim "
                   "Überschreiten ihres Hochs."},
    # Die eigenen Wege des Waechters
    {"schluessel": "r2g", "gruppe": "weitere", "name": "Red-to-Green",
     "namen": ["Red-to-Green"],
     "erklaerung": "Nach einer schwachen Eröffnung des Nasdaq dreht eine Aktie der Fokusliste mit einem Volumenschub "
                   "über ihren Vortagesschluss."},
    {"schluessel": "r2gx", "gruppe": "weitere", "name": "Red-to-Green Explosive",
     "namen": ["Red-to-Green Explosive"],
     "erklaerung": "Eine Aktie eröffnet unter ihrem Vortagesschluss und dreht aus eigener Kraft ins Plus, "
                   "unabhängig vom Markt."},
    {"schluessel": "gapgo", "gruppe": "weitere", "name": "Gap and Go, Lücken-Bestätigungstag",
     "namen": ["Gap and Go", "Lücken-Bestätigungstag"],
     "erklaerung": "Eine Kurslücke von mindestens sieben Prozent nach oben mit hohem Volumen; Meldung am Lückentag, "
                   "der Einstieg folgt am Handelstag danach."},
    {"schluessel": "insider", "gruppe": "weitere", "name": "Insider-Käufe",
     "namen": ["Insider-Kauf"],
     "erklaerung": "Große Käufe von Vorständen und Direktoren laut den Meldungen an die SEC; Meldung mit dem Kurs "
                   "des Tages."},
    {"schluessel": "sektor_morgen", "gruppe": "info", "name": "Sektor-Aufsteiger am Morgen",
     "namen": [],
     "erklaerung": "Jeden Morgen die größten Aufsteiger der Sektor-Rangliste und die neuen Branchen unter den "
                   "ersten fünf; eine Rangfolge nach den Schlusskursen des Vortags, kein Kursalarm."},
]

NIE_ABWAEHLBAR = ("Ausstiege und Stops, Gewinnzonen, die schlussnahen Befunde ab 15:45 New Yorker Zeit und die "
                  "Beobachtungen offener Positionen melden immer; sie gehören zu Positionen, die schon bestehen.")

DESIGNS = [
    ("standard", "Standard"),
    ("zukunft", "Zukunft, mit Bewegung und Leuchteffekten"),
]

# Die Toene: die Kennung, der Name und was man hoert. Erzeugt werden sie im
# Browser (oberflaeche.KLANG_JS), es gibt keine Tondateien.
KLAENGE = [
    ("aus", "Kein Ton", "Nach einer erfolgreichen Aktion bleibt es still."),
    ("kristall", "Kristall", "Zwei helle Glockentöne, die nachklingen."),
    ("nova", "Nova", "Ein schneller, aufsteigender Dreiklang mit Echo."),
    ("sonar", "Sonar", "Ein einzelner Ortungston, der langsam ausklingt."),
    ("pixel", "Pixel", "Zwei kurze Töne wie in einem alten Videospiel."),
    ("aurora", "Aurora", "Ein weicher, schwebender Akkord."),
    ("tropfen", "Tropfen", "Zwei Wassertropfen."),
    ("warp", "Warp", "Ein aufsteigendes Rauschen mit einem hellen Ton am Ende."),
]

VORGABE = {"alarme_aus": [], "design": "standard", "klang": "kristall"}


def _schluessel_alle() -> list[str]:
    return [a["schluessel"] for a in ALARME]


def lesen(roh) -> dict:
    """Die Einstellungen aus dem Inhalt der Datei (bytes, str oder dict).
    Alles Unbekannte faellt weg, Fehlendes nimmt die Vorgabe; eine kaputte
    oder leere Datei ergibt die Vorgabe. Nie eine Ausnahme."""
    daten = {}
    try:
        if isinstance(roh, dict):
            daten = roh
        elif roh:
            text = roh.decode("utf-8-sig") if isinstance(roh, (bytes, bytearray)) else str(roh)
            daten = json.loads(text) if text.strip() else {}
    except (ValueError, UnicodeDecodeError):
        daten = {}
    if not isinstance(daten, dict):
        daten = {}
    bekannt = set(_schluessel_alle())
    aus = daten.get("alarme_aus")
    aus = sorted({str(x) for x in aus if str(x) in bekannt}) if isinstance(aus, list) else []
    design = daten.get("design")
    if design not in {k for k, _ in DESIGNS}:
        design = VORGABE["design"]
    klang = daten.get("klang")
    if klang not in {k for k, _n, _b in KLAENGE}:
        klang = VORGABE["klang"]
    raus = {"alarme_aus": aus, "design": design, "klang": klang}
    if isinstance(daten.get("geaendert"), str):
        raus["geaendert"] = daten["geaendert"][:40]
    return raus


def schreiben(einst: dict, geaendert: str = "") -> bytes:
    """Der Dateiinhalt: gueltige Werte, sortiert, mit Zeilenende LF."""
    e = lesen(einst)
    if geaendert:
        e["geaendert"] = str(geaendert)[:40]
    return (json.dumps(e, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def alarm_an(einst: dict, schluessel: str) -> bool:
    """Ist der Alarm mit diesem Schluessel eingeschaltet? Unbekanntes: ja."""
    return schluessel not in set((einst or {}).get("alarme_aus") or [])


def schluessel_fuer(name) -> str | None:
    """Der Registereintrag zu einem Strategienamen: erst der genaue Name,
    dann der laengste passende Namensanfang. Nichts gefunden: None."""
    n = str(name or "").strip()
    if not n:
        return None
    for a in ALARME:
        if n in a["namen"]:
            return a["schluessel"]
    bester, laenge = None, 0
    for a in ALARME:
        for anf in a.get("anfaenge") or []:
            if n.startswith(anf) and len(anf) > laenge:
                bester, laenge = a["schluessel"], len(anf)
    return bester


def muster_an(einst: dict, name) -> bool:
    """Loest die Strategie mit diesem Namen einen Alarm aus? Ein Name ohne
    Registereintrag gilt als eingeschaltet (siehe Kopf: Neues ist an)."""
    s = schluessel_fuer(name)
    return True if s is None else alarm_an(einst, s)


def abgewaehlte_namen(einst: dict) -> list[str]:
    """Die Anzeigenamen der abgewaehlten Alarme, fuer Protokoll und Anzeige."""
    aus = set((einst or {}).get("alarme_aus") or [])
    return [a["name"] for a in ALARME if a["schluessel"] in aus]


def eintrag(schluessel: str) -> dict | None:
    return next((a for a in ALARME if a["schluessel"] == schluessel), None)


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

def selbsttest() -> int:
    fehler = []

    def p(text, ok, info=""):
        print(("  OK    " if ok else "  FEHLER ") + text + (f" ({info})" if info and not ok else ""))
        if not ok:
            fehler.append(text)

    print("einstellungen.py, Selbsttest")
    sch = _schluessel_alle()
    p("Jeder Schluessel kommt einmal vor", len(sch) == len(set(sch)))
    p("Jeder Eintrag hat eine bekannte Gruppe", all(a["gruppe"] in {g for g, _ in GRUPPEN} for a in ALARME))
    p("Jeder Eintrag hat Namen oder Namensanfaenge oder ist ein eigener Weg",
      all(a["namen"] or a.get("anfaenge") or a["schluessel"] == "sektor_morgen" for a in ALARME))
    p("Jeder Eintrag hat eine Erklaerung von hoechstens 260 Zeichen",
      all(0 < len(a["erklaerung"]) <= 260 for a in ALARME),
      ", ".join(a["schluessel"] for a in ALARME if not 0 < len(a["erklaerung"]) <= 260))
    alle_namen = [n for a in ALARME for n in a["namen"]]
    p("Kein Strategiename gehoert zwei Eintraegen", len(alle_namen) == len(set(alle_namen)))
    verboten = ("–", "—", "|")
    p("Kein Gedankenstrich und kein senkrechter Strich in Namen und Erklaerungen",
      not any(z in a["name"] + a["erklaerung"] for a in ALARME for z in verboten))

    p("Leere Datei ergibt die Vorgabe", lesen(b"") == VORGABE)
    p("Kaputte Datei ergibt die Vorgabe", lesen(b"{nicht json") == VORGABE)
    p("Keine Liste ergibt die Vorgabe", lesen(b"[1, 2]") == VORGABE)
    e = lesen(json.dumps({"alarme_aus": ["vcp", "gibtsnicht", "darvas"], "design": "zukunft",
                          "klang": "nova", "fremd": 1}).encode())
    p("Unbekannte Schluessel fallen weg, bekannte bleiben sortiert", e["alarme_aus"] == ["darvas", "vcp"], str(e))
    p("Design und Ton werden uebernommen", e["design"] == "zukunft" and e["klang"] == "nova")
    p("Fremde Felder fallen weg", "fremd" not in e)
    p("Unbekanntes Design und unbekannter Ton ergeben die Vorgabe",
      lesen({"design": "bunt", "klang": "hupe"}) == VORGABE)
    roh = schreiben(e, "2026-09-23 22:10")
    p("Schreiben und Lesen ergeben dasselbe", {k: v for k, v in lesen(roh).items() if k != "geaendert"} == e)
    p("Die Datei endet mit LF und hat kein CR", roh.endswith(b"\n") and b"\r" not in roh)
    p("Der Zeitpunkt der Aenderung steht in der Datei", lesen(roh).get("geaendert") == "2026-09-23 22:10")

    p("Genauer Name: VCP", schluessel_fuer("VCP") == "vcp")
    p("Genauer Name: Cup & Handle (Wochenbasis) ist ein eigener Eintrag",
      schluessel_fuer("Cup & Handle (Wochenbasis)") == "cup_woche" and schluessel_fuer("Cup & Handle") == "cup")
    p("Namensanfang: Shakeout-Spring mit Zusatz",
      schluessel_fuer("Shakeout-Spring, Sekundärtest bestätigt") == "shakeout"
      and schluessel_fuer("Shakeout an starkem Level (Kapitel 10)") == "shakeout")
    p("Shakeout plus drei ist ein anderer Eintrag als Shakeout-Spring",
      schluessel_fuer("Shakeout plus drei") == "a_shakeout3")
    p("Gap and Go und Lücken-Bestätigungstag teilen einen Schalter",
      schluessel_fuer("Gap and Go") == schluessel_fuer("Lücken-Bestätigungstag") == "gapgo")
    p("Unbekannter Name hat keinen Eintrag", schluessel_fuer("Gibt es nicht") is None)
    aus = {"alarme_aus": ["vcp", "a_wick"]}
    p("Abgewaehlt: VCP aus, Darvas an", not muster_an(aus, "VCP") and muster_an(aus, "Darvas Box"))
    p("Abgewaehlt: Wick Play aus", not muster_an(aus, "Wick Play"))
    p("Unbekannter Name bleibt an", muster_an(aus, "Gibt es nicht"))
    p("Ohne Einstellungen ist alles an", all(muster_an(None, n) for n in alle_namen))
    p("Anzeigenamen der Abgewaehlten", abgewaehlte_namen(aus) == ["VCP", "Wick Play"])
    try:
        import alarm_muster
        p("Die sechs Alarm-Muster stehen im Register",
          all(schluessel_fuer(n) for n in alarm_muster.NAMEN.values()),
          ", ".join(n for n in alarm_muster.NAMEN.values() if not schluessel_fuer(n)))
    except Exception as ex:  # noqa: BLE001
        p("alarm_muster ladbar", False, f"{type(ex).__name__}: {ex}")
    print(f"ERGEBNIS: {len(fehler)} FEHLGESCHLAGEN" if fehler else "ERGEBNIS: alles bestanden")
    return 1 if fehler else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Einstellungen von App und Waechter")
    ap.add_argument("--selbsttest", action="store_true")
    a = ap.parse_args()
    if a.selbsttest:
        return selbsttest()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
