"""EINSTELLUNGEN VON APP UND WAECHTER (Mathias und Gerhard, 23.09.2026)

WOFUER: Der Reiter Einstellungen der App legt hier fest, welche Chartmuster,
Strategien und Meldungen ueber ntfy hinausgehen. Mathias, 23.09.2026: "wir
meinen die Alarme fuer ntfy, da moechten wir waehlen koennen, welche
Chartmuster zur Anwendung kommen."

WO: einstellungen.json im oeffentlichen Repo auf main. Die App schreibt die
Datei ueber die GitHub-Schnittstelle (nur voller Zugang), der Waechter liest
sie in jedem Datentakt frisch aus origin/main, genau wie die einzeln
ueberwachten Aktien. Eine Abwahl wirkt also binnen einer Minute.

WAS ABGEWAEHLT HEISST (Gerhard, 24.09.2026, Frage 9): nur "keine Meldung".
Keine Meldung ueber ntfy und kein Signal an den Handels-Bot, der seine
Signale ebenfalls ueber ntfy bekommt. Der Waechter prueft ein abgewaehltes
Muster aber weiter und schreibt jeden Ausbruch ins Trigger-Logbuch, mit
"gemeldet": false und "abgewaehlt": true; grundsaetzlich kommen alle
Strategien ins Logbuch, ausnahmslos. Der Nachtscan rechnet weiter, und die
Kaufpunkte stehen weiter im Reiter Aktueller Scan.

ALLES IST ABWAEHLBAR (Gerhard, 24.09.2026, Frage 7, Vorschlag 3): auch die
Meldungen zu offenen Positionen, also Ausstiege und Stops, Gewinnzonen, die
schlussnahen Befunde ab 15:45 New Yorker Zeit und die Beobachtungen offener
Positionen. Diese Eintraege tragen eine Warnung, die die App beim Abwaehlen
zeigt. Der Sektor-Radar vor dem Schluss steht im Block Weitere Auskuenfte
(Fragen 8 und 19). Welche Art eines Befunds zu welchem Schalter gehoert,
steht in BEFUND_ARTEN.

AUSSEHEN UND TON (Mathias, 24.09.2026, Fragen 2 und 3): jede Person fuer
sich, im eigenen Browser gespeichert; sie stehen deshalb NICHT mehr in dieser
Datei. Gaeste bekommen die Grundeinstellung eines neuen Browsers, also
DESIGN_VORGABE und KLANG_VORGABE. Eine aeltere Datei mit "design" und
"klang" wird ohne Fehler gelesen; die beiden Felder fallen weg.

NEUES IST EINGESCHALTET: Die Datei fuehrt nur, was ABGEWAEHLT ist. Ein neuer
Eintrag im Register, ein unbekannter Name oder eine fehlende oder kaputte
Datei heisst deshalb immer: Alarm an. Eher ein Alarm zu viel als ein
stiller Ausfall.

DAS REGELWERK der App entsteht aus diesem Register (Frage 76): je Strategie
ein Absatz, das Feld "regel", ersatzweise die Erklaerung. Eine neue Strategie
steht damit von selbst im Regelwerk.

Aufruf:
    python einstellungen.py --selbsttest
"""

import argparse
import json
import sys

DATEI = "einstellungen.json"

# Die Gruppen der Alarme in der Reihenfolge der Anzeige. Die Fallbacks heissen
# ueberall Fallback, auch in der Blockueberschrift (Gerhard, 24.09.2026,
# Frage 82).
GRUPPEN = [
    ("kauf", "Kaufsignale aus Chartmustern"),
    ("ausweich", "Fallbacks für Aktien mit weniger als drei Mustern"),
    ("auskunft", "Chartmuster als Auskunft, ohne Kaufsignal"),
    ("weitere", "Weitere Kaufsignale"),
    ("positionen", "Meldungen zu offenen Positionen"),
    ("info", "Weitere Auskünfte"),
]

# Die Gruppen, deren Eintraege Strategien sind: Sie stehen im Regelwerk und in
# der Pruefung, ob jede Strategie ins Logbuch kommt.
STRATEGIE_GRUPPEN = ("kauf", "ausweich", "auskunft", "weitere")

# Ein Satz je Gruppe fuer das Regelwerk, vor den Absaetzen der Strategien.
GRUPPEN_REGEL = {
    "kauf": "Diese Muster entstehen jede Nacht aus den Tageskerzen der beiden Wochenlisten und der einzeln "
            "überwachten Aktien. Je Aktie gelten die drei wichtigsten Kaufpunkte; der Breakout-Wächter meldet, "
            "wenn der Kurs einen davon reißt.",
    "ausweich": "Hat eine Aktie weniger als drei Muster, füllen Fallbacks die freien Plätze: Kaufpunkte ohne "
                "Muster, etwa knapp über dem 52-Wochen-Hoch. Ein Fallback, über dem der Kurs schon am Vortag stand, "
                "meldet nicht.",
    "auskunft": "Diese sechs Chartmuster melden als Auskunft, ohne Kaufsignal an den Handels-Bot. Jedes lässt sich "
                "im Reiter Einstellungen abwählen; abgewählt kommt keine Meldung, der Wächter prüft es aber weiter "
                "und schreibt jeden Ausbruch ins Logbuch.",
    "weitere": "Diese Strategien rechnet der Wächter selbst im Handel, nicht der Nachtscan.",
}

# Das Trend Template ist keine Strategie mit eigenem Kaufpunkt, gehoert aber
# vor die Muster, weil der VCP es voraussetzt.
TREND_TEMPLATE_REGEL = (
    "Acht Bedingungen, die alle erfüllt sein müssen: Kurs über dem 150- und dem 200-Tage-Durchschnitt, der 150er "
    "über dem 200er, der 200er steigt seit einem Monat, der 50er über beiden, Kurs über dem 50er, mindestens 25 "
    "Prozent über dem 52-Wochen-Tief, höchstens 25 Prozent unter dem 52-Wochen-Hoch und ein RS von mindestens 70. "
    "Es liefert selbst keinen Kaufpunkt, ist aber Voraussetzung für den VCP.")

# DAS REGISTER DER ABWAEHLBAREN ALARME.
#   name:      der Name in der Anzeige (Beistrich statt Klammern, Frage 95;
#              52-Wochen-Hoch, Frage 89; Fallback, Frage 82; Power-Gap und
#              Red to Green, Fragen 93 und 94).
#   namen:     die Strategienamen, wie sie in Mappe, Meldung und Logbuch
#              stehen, genau so geschrieben; die Namen in Mappe und Meldungen
#              bleiben (Frage 95).
#   anfaenge:  Namensanfaenge fuer Strategien, die ihren Namen um einen Zusatz
#              verlaengern ("Shakeout-Spring, wartet auf Sekundaertest").
#   erklaerung: der Text hinter dem Knopf "Was ist ...?", hoechstens 260 Zeichen.
#   regel:     der Absatz im Regelwerk; fehlt er, gilt die Erklaerung.
#   warnung:   nur bei den Meldungen zu offenen Positionen, gezeigt beim
#              Abwaehlen (Frage 7).
# Die Gesamtpruefung achtet darauf, dass jede Strategie, die im System entstehen
# kann, hier einen Eintrag hat.
ALARME = [
    # Kaufpunkte aus dem Nachtscan, in der Reihenfolge von
    # pattern_scanner.PRIORITY
    {"schluessel": "htf", "gruppe": "kauf", "name": "High & Tight Flag",
     "namen": ["High & Tight Flag"],
     "erklaerung": "Ein Anstieg um mindestens 90 Prozent in höchstens 42 Handelstagen, danach eine enge Flagge "
                   "von höchstens 35 Kalendertagen; Alarm beim Ausbruch über die Flagge.",
     "regel": "Ein Mast mit mindestens 90 Prozent Anstieg in höchstens 42 Handelstagen, sein Tief bei mindestens "
              "einem Dollar, danach eine enge Flagge von höchstens 35 Kalendertagen, deren Spanne höchstens ein "
              "Viertel der Masthöhe ausmacht. Kaufpunkt einen Cent über dem Hoch der Flagge, Stop einen Cent unter "
              "ihrem Tief; die Note A, B oder C bewertet Enge, Steilheit und Volumen. Selten, aber stark."},
    {"schluessel": "htf_innen", "gruppe": "kauf", "name": "HTF Innen-Einstieg",
     "namen": ["HTF Innen-Einstieg"],
     "erklaerung": "Der Einstieg innerhalb der Flagge einer High & Tight Flag; der Alarm kommt früher als beim "
                   "Ausbruch über die ganze Flagge.",
     "regel": "Der frühere Einstieg in eine High & Tight Flag: ein Inside Day oder der engste Tag unter den letzten "
              "fünf Tagen der Flagge. Kaufpunkt einen Cent über dem Hoch dieses Tages, Stop einen Cent unter seinem "
              "Tief; er läuft zusätzlich zum Ausbruch über das Hoch der Flagge."},
    {"schluessel": "vcp", "gruppe": "kauf", "name": "VCP",
     "namen": ["VCP"],
     "erklaerung": "Volatility Contraction Pattern: Trend Template erfüllt, dazu mindestens zwei immer engere "
                   "Rücksetzer mit austrocknendem Volumen; Alarm beim Ausbruch über den Pivot.",
     "regel": "Volatility Contraction Pattern: Das Trend Template muss erfüllt sein, dazu mindestens zwei, höchstens "
              "sechs Kontraktionen mit abnehmender Tiefe und austrocknendem Volumen. Kaufpunkt einen Cent über dem "
              "Pivot, Stop 8 Prozent darunter; steht der Kurs schon mehr als 2 Prozent über dem Pivot, entsteht kein "
              "Kaufpunkt."},
    {"schluessel": "cup", "gruppe": "kauf", "name": "Cup & Handle",
     "namen": ["Cup & Handle"],
     "erklaerung": "Tasse mit Henkel auf Tageskerzen: eine runde Tasse, 12 bis 50 Prozent tief, mit einem Henkel im "
                   "oberen Drittel; Alarm beim Ausbruch über das Henkelhoch.",
     "regel": "Tasse mit Henkel auf Tageskerzen. Die U-Form wird über eine quadratische Anpassung geprüft, V-Formen "
              "fallen weg; die Tasse ist 12 bis 50 Prozent tief, der Henkel liegt im oberen Drittel und gibt "
              "höchstens ein Drittel der Tassenhöhe ab. Das Ergebnis ist eine Punktzahl, weil die Formerkennung "
              "unscharf ist. Kaufpunkt über dem Henkelhoch, Ziel gleich Ausbruch plus Tassenhöhe."},
    {"schluessel": "cup_woche", "gruppe": "kauf", "name": "Cup & Handle, Wochenbasis",
     "namen": ["Cup & Handle (Wochenbasis)"],
     "erklaerung": "Dieselbe Tasse mit Henkel auf Wochenkerzen, also über einen längeren Zeitraum; Alarm beim "
                   "Ausbruch über das Henkelhoch.",
     "regel": "Dieselbe Tasse mit Henkel auf Wochenkerzen: 5 bis 104 Wochen lang und 12 bis 60 Prozent tief, der "
              "Henkel in der oberen Hälfte der Tasse und höchstens 45 Prozent ihrer Höhe tief. Die lockereren "
              "Grenzen gelten nur hier, weil sie für sehr lange Formationen gemacht sind; auf kurze Tassen "
              "angewandt ließen sie Fehlsignale durch. Kaufpunkt über dem Henkelhoch."},
    {"schluessel": "darvas", "gruppe": "kauf", "name": "Darvas Box",
     "namen": ["Darvas Box"],
     "erklaerung": "Ein neues 52-Wochen-Hoch, danach eine Box aus mindestens drei plus drei Tagen; Alarm beim "
                   "Ausbruch über die Oberkante der Box. Läuft auf der Darvas-Liste und bei einzeln überwachten "
                   "Aktien.",
     "regel": "Ein neues 52-Wochen-Hoch, danach eine Box aus mindestens drei plus drei Tagen: drei Tage bilden den "
              "Deckel, die drei Tage danach den Boden, und der Kurs bleibt seither in der Box. Kaufpunkt einen Cent "
              "über der Oberkante, Stop einen Cent unter der Unterkante. Gemeldet werden nur frische Boxen, deren "
              "Hoch höchstens 25 Handelstage zurückliegt; sie entstehen auf der Darvas-Liste und bei einzeln "
              "überwachten Aktien."},
    {"schluessel": "earnings", "gruppe": "kauf", "name": "Earnings-Pullback",
     "namen": ["Earnings-Pullback"],
     "erklaerung": "Nach starken Quartalszahlen wird nicht der Sprung gekauft, sondern die erste ruhige "
                   "Konsolidierung darüber; Alarm beim Ausbruch aus dieser Konsolidierung.",
     "regel": "Nach Quartalszahlen eine Eröffnung mindestens 8 Prozent oder ein Schluss mindestens 10 Prozent über "
              "dem Vortag, mit mindestens dem Dreifachen des Volumens; danach 2 bis 15 Handelstage ruhige "
              "Konsolidierung, deren Tiefs über dem Tief des Sprungtags bleiben. Kaufpunkt einen Cent über dem Hoch "
              "der Konsolidierung, Stop 4 Prozent unter ihrem Tief."},
    {"schluessel": "ema", "gruppe": "kauf", "name": "EMA Crossback",
     "namen": ["EMA Crossback"],
     "erklaerung": "EMA Crossback nach Oliver Kell: der erste Rücksetzer an die 10- und 20-Tage-Linie nach ihrer "
                   "Rückeroberung; Alarm, wenn der Kurs das Hoch des Umkehrtags überschreitet.",
     "regel": "Nach Oliver Kell: Der Kurs hat die 10er- und die 20er-Tageslinie frisch von unten zurückerobert und "
              "setzt zum ersten Mal an sie zurück; ein Umkehrtag bestätigt die Linien als Unterstützung. Kaufpunkt "
              "einen Cent über dem Hoch des Umkehrtags."},
    {"schluessel": "rechteck", "gruppe": "kauf", "name": "Rectangle Top",
     "namen": ["Rectangle Top"],
     "erklaerung": "Eine waagrechte Handelsspanne mit mindestens zwei Berührungen oben und unten; Alarm einen Cent über "
                   "der Oberkante, wenn der Kurs zugleich über dem 21-Tage-Durchschnitt liegt.",
     "regel": "Eine waagrechte Handelsspanne mit mindestens zwei Berührungen oben und unten, 3 bis 25 Prozent hoch. "
              "Kaufpunkt einen Cent über der Oberkante, wenn der Kurs zugleich über dem 21-Tage-Durchschnitt liegt; "
              "Stop einen Cent unter der Unterkante, Ziel gleich Ausbruch plus Rechteckhöhe."},
    {"schluessel": "shakeout", "gruppe": "kauf", "name": "Shakeout-Spring",
     "namen": [], "anfaenge": ["Shakeout-Spring", "Shakeout an starkem Level"],
     "erklaerung": "Eine Aktie im Aufwärtstrend unterschreitet kurz eine starke Unterstützungszone und erobert sie "
                   "am selben Tag zurück; Alarm, wenn der Test der Zone gehalten hat.",
     "regel": "Eine Aktie im Aufwärtstrend unterschreitet kurz eine starke Unterstützungszone und erobert sie am "
              "selben Tag zurück. Danach wartet der Spring bis zu 15 Handelstage auf den Test der Zone mit geringerem "
              "Volumen; hält der Test, entsteht der Kaufpunkt."},
    {"schluessel": "crash", "gruppe": "kauf", "name": "Crash-Support",
     "namen": ["Crash-Support"],
     "erklaerung": "Während einer Marktkorrektur: große, gesunde Unternehmen an einer starken Unterstützungszone. Die "
                   "Funde stehen nur im Logbuch; eine Meldung gibt es bisher nicht.",
     "regel": "Nur während einer Marktkorrektur, wenn der S&P 500 mindestens 10 Prozent unter seinem 52-Wochen-Hoch "
              "steht: große, gesunde Unternehmen an einer starken Unterstützungszone. Die Funde stehen nur im "
              "Logbuch; eine Meldung und einen Kaufpunkt in der Mappe gibt es bisher nicht."},
    # Fallbacks (pattern_scanner.fallback_points)
    {"schluessel": "fb_52w", "gruppe": "ausweich", "name": "Fallback 52-Wochen-Hoch-Breakout",
     "namen": ["Fallback: 52W-Hoch-Breakout"],
     "erklaerung": "Ein Fallback für Aktien ohne genug Muster: Alarm knapp über dem 52-Wochen-Hoch.",
     "regel": "Kaufpunkt 0,1 Prozent über dem 52-Wochen-Hoch, Stop 7 Prozent unter ihm."},
    {"schluessel": "fb_20t", "gruppe": "ausweich", "name": "Fallback 20-Tage-Hoch, Pivot",
     "namen": ["Fallback: 20-Tage-Hoch (Pivot)"],
     "erklaerung": "Ein Fallback: Alarm einen Cent über dem Hoch der letzten 20 Handelstage.",
     "regel": "Kaufpunkt einen Cent über dem Hoch der letzten 20 Handelstage, Stop einen Cent unter ihrem Tief."},
    {"schluessel": "fb_ma50p", "gruppe": "ausweich", "name": "Fallback 50-Tage-Durchschnitt, Pullback",
     "namen": ["Fallback: MA50-Pullback"],
     "erklaerung": "Ein Fallback bei intaktem Trend: Alarm knapp über der 50-Tage-Linie nach einem Rücksetzer.",
     "regel": "Steht der Kurs über dem 50-Tage-Durchschnitt: Kaufpunkt 0,5 Prozent über ihm, Stop 5 Prozent unter "
              "ihm; nur bei intaktem Trend."},
    {"schluessel": "fb_ma50r", "gruppe": "ausweich", "name": "Fallback 50-Tage-Durchschnitt, Rückeroberung",
     "namen": ["Fallback: MA50-Rückeroberung"],
     "erklaerung": "Ein Fallback für Aktien unter der 50-Tage-Linie: Alarm, wenn der Kurs sie knapp überschreitet.",
     "regel": "Steht der Kurs unter dem 50-Tage-Durchschnitt: Kaufpunkt 0,5 Prozent über ihm, Stop 6 Prozent unter "
              "ihm; gilt erst nach der Rückeroberung."},
    {"schluessel": "fb_63t", "gruppe": "ausweich", "name": "Fallback Quartals-Hoch, 63 Tage",
     "namen": ["Fallback: Quartals-Hoch (63 Tage)"],
     "erklaerung": "Ein Fallback: Alarm einen Cent über dem Hoch der letzten 63 Handelstage.",
     "regel": "Kaufpunkt einen Cent über dem Hoch der letzten 63 Handelstage, Stop 8 Prozent darunter."},
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
    {"schluessel": "r2g", "gruppe": "weitere", "name": "Red to Green",
     "namen": ["Red-to-Green", "Red to Green"],
     "erklaerung": "Nach einer schwachen Eröffnung des Nasdaq dreht eine Aktie der Fokusliste mit einem Volumenschub "
                   "über ihren Vortagesschluss.",
     "regel": "Nach einer schwachen Eröffnung des Nasdaq dreht eine Aktie der Fokusliste mit einem Volumenschub über "
              "ihren Vortagesschluss. Kaufpunkt ist der Kurs der Meldung, der Stop liegt am Vortagesschluss; die "
              "Position ist ein Tagesgeschäft."},
    {"schluessel": "r2gx", "gruppe": "weitere", "name": "Red to Green Explosive",
     "namen": ["Red-to-Green Explosive", "Red to Green Explosive"],
     "erklaerung": "Eine Aktie eröffnet unter ihrem Vortagesschluss und dreht aus eigener Kraft ins Plus, "
                   "unabhängig vom Markt.",
     "regel": "Eine Aktie der Fokusliste eröffnet unter ihrem Vortagesschluss und dreht aus eigener Kraft ins Plus, "
              "ohne Bedingung an den Markt; Kaufpunkt und Stop wie bei Red to Green."},
    {"schluessel": "gapgo", "gruppe": "weitere", "name": "Power-Gap",
     "namen": ["Gap and Go", "Lücken-Bestätigungstag", "Power-Gap"],
     "erklaerung": "Eine Kurslücke von mindestens sieben Prozent nach oben mit hohem Volumen; Meldung am Lückentag, "
                   "der Einstieg folgt am Handelstag danach.",
     "regel": "Eine Kurslücke von mindestens sieben Prozent nach oben mit mindestens dem Fünffachen des üblichen "
              "Volumens. Am Lückentag kommt die Meldung; gekauft wird am Handelstag danach, solange der Kurs höchstens "
              "3 Prozent über dem Kaufpunkt steht, darüber ist es nur eine Auskunft."},
    {"schluessel": "insider", "gruppe": "weitere", "name": "Insider-Käufe",
     "namen": ["Insider-Kauf"],
     "erklaerung": "Große Käufe von Vorständen und Direktoren laut den Meldungen an die SEC; Meldung mit dem Kurs "
                   "des Tages.",
     "regel": "Große Käufe von Vorständen und Direktoren laut den Meldungen an die SEC, bewertet mit dem Marktwert "
              "des Tages; gemeldet mit dem Kurs des Tages, der zugleich der Einstieg ist."},
    # Die Meldungen zu offenen Positionen (Gerhard, 24.09.2026, Frage 7:
    # alles abwaehlbar, mit einer Warnung beim Abwaehlen)
    {"schluessel": "ausstiege", "gruppe": "positionen", "name": "Ausstiege und Stops",
     "namen": [],
     "erklaerung": "Die Ausstiege des Exit-Regelwerks für offene Positionen: gerissene Stops, Zeitdeckel, der "
                   "Teilverkauf und der Rückfall eines Tagesgeschäfts unter seine Exit-Linie; dazu das "
                   "Verkaufssignal an den Handels-Bot.",
     "warnung": "Abgewählt kommt keine Meldung, wenn eine offene Position ihren Stop reißt, und der Handels-Bot "
                "bekommt kein Verkaufssignal; die Positionen bleiben dann ohne Ausstieg offen."},
    {"schluessel": "gewinnzonen", "gruppe": "positionen", "name": "Gewinnzonen",
     "namen": [],
     "erklaerung": "Die Hinweise auf der Gewinnseite offener Positionen: der Aufstieg in eine höhere Gewinnzone, "
                   "Klimax-Zeichen, das erreichte Musterziel, Weinstein Stufe 3, Wedge Drop und ein drehender Sektor.",
     "warnung": "Abgewählt kommt kein Hinweis mehr, wann bei offenen Positionen Gewinne gesichert werden sollten."},
    {"schluessel": "schlussnah", "gruppe": "positionen", "name": "Schlussnahe Befunde ab 15:45 New Yorker Zeit",
     "namen": [],
     "erklaerung": "Die Meldung kurz vor dem Schluss, gerechnet mit den Handelskursen: alles, was nach den Regeln "
                   "einen Schlusskurs braucht, also Ausstiege, Gewinnzonen, Beobachtungen und der Sektor-Radar.",
     "warnung": "Abgewählt kommt die Meldung um 15:45 gar nicht, und mit ihr fehlen die Ausstiege des "
                "Exit-Regelwerks samt Verkaufssignal an den Handels-Bot; sie werden nur zu diesem Zeitpunkt gemeldet."},
    {"schluessel": "beobachtungen", "gruppe": "positionen", "name": "Beobachtungen offener Positionen",
     "namen": [],
     "erklaerung": "Hinweise zu offenen Positionen, die keinen Ausstieg verlangen: Schluss unter der 8-Tage-EMA, "
                   "Quartalszahlen in den nächsten fünf Tagen und das Ende eines Tagesgeschäfts mit dem Schluss.",
     "warnung": "Abgewählt fehlen die Hinweise zu offenen Positionen, etwa auf Quartalszahlen in den nächsten Tagen."},
    # Weitere Auskuenfte
    {"schluessel": "sektor_morgen", "gruppe": "info", "name": "Sektor-Aufsteiger am Morgen",
     "namen": [],
     "erklaerung": "Jeden Morgen die größten Aufsteiger der Sektor-Rangliste und die neuen Branchen unter den "
                   "ersten fünf; eine Rangfolge nach den Schlusskursen des Vortags, kein Kursalarm."},
    {"schluessel": "sektor_radar", "gruppe": "info", "name": "Sektor-Radar vor dem Schluss",
     "namen": [],
     "erklaerung": "Gegen 15:45 New Yorker Zeit die Sektor-ETFs, die mit hochgerechnetem Volumen nach oben oder "
                   "unten drehen; eine Auskunft, kein Kaufsignal."},
]

# WELCHER SCHALTER ZU WELCHER ART VON BEFUND GEHOERT (Frage 7 und 8). Die Arten
# sind die Typen, die gewinnzonen_lauf und der Waechter fuehren; dazu zwei eigene
# fuer die Wachen im Handel (tagesgeschaeft_exit, teilverkauf). Eine unbekannte
# Art gilt als eingeschaltet (siehe Kopf: Neues ist an).
BEFUND_ARTEN = {
    "kapitel11": "ausstiege", "zeitdeckel": "ausstiege", "tagesgeschaeft_exit": "ausstiege",
    "teilverkauf": "ausstiege",
    "klimax_zeichen": "gewinnzonen", "zonenwechsel": "gewinnzonen", "ziel_erreicht": "gewinnzonen",
    "weinstein": "gewinnzonen", "wedge_drop": "gewinnzonen", "sektor_hinweis": "gewinnzonen",
    "ema8_hinweis": "beobachtungen", "zahlen_hinweis": "beobachtungen", "tagesende": "beobachtungen",
    "sektor_radar": "sektor_radar",
}

# DIE NAMEN IN DEN MELDUNGEN (Gerhard, 24.09.2026, Fragen 93 und 94): ueberall
# Power-Gap und Red to Green, auch in den Meldungen. Die Strategienamen in Mappe,
# Logbuch und Beobachtungen bleiben, wie sie sind: Sie sind Daten, an denen
# Exit-Regeln und Auswertungen haengen. Umgeschrieben wird erst beim Senden, an
# genau einer Stelle je Absender (breakout_watcher._sende_eine,
# abendbericht.senden).
MELDUNGS_NAMEN = (("Red-to-Green", "Red to Green"), ("Lücken-Bestätigungstag", "Power-Gap"),
                  ("Gap and Go", "Power-Gap"))


def meldungs_text(text) -> str:
    """Titel oder Text einer Meldung mit den gewaehlten Namen."""
    t = str(text if text is not None else "")
    for alt, neu in MELDUNGS_NAMEN:
        t = t.replace(alt, neu)
    return t


DESIGNS = [
    ("standard", "Standard"),
    ("zukunft", "Zukunft, mit Bewegung und Leuchteffekten"),
]

# Die Toene: die Kennung, der Name und was man hoert. Erzeugt werden sie im
# Browser (oberflaeche.KLANG_JS), es gibt keine Tondateien. Dazu kommt der feste
# Fehlerton "fehler" (Frage 5), der nicht waehlbar ist und hier nicht steht.
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

# Die Grundeinstellung eines neuen Browsers; Gaeste bekommen immer sie (Frage 3).
DESIGN_VORGABE = "standard"
KLANG_VORGABE = "kristall"

VORGABE = {"alarme_aus": []}


def _schluessel_alle() -> list[str]:
    return [a["schluessel"] for a in ALARME]


def lesen(roh) -> dict:
    """Die Einstellungen aus dem Inhalt der Datei (bytes, str oder dict).
    Alles Unbekannte faellt weg, auch die frueheren Felder design und klang;
    Fehlendes nimmt die Vorgabe, eine kaputte oder leere Datei ergibt die
    Vorgabe. Nie eine Ausnahme."""
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
    raus = {"alarme_aus": aus}
    if isinstance(daten.get("geaendert"), str):
        raus["geaendert"] = daten["geaendert"][:40]
    return raus


def schreiben(einst: dict, geaendert: str = "") -> bytes:
    """Der Dateiinhalt: gueltige Werte, sortiert, mit Zeilenende LF."""
    e = lesen(einst)
    if geaendert:
        e["geaendert"] = str(geaendert)[:40]
    return (json.dumps(e, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def design_gueltig(wert) -> str:
    """Ein Aussehen aus dem Browser, oder die Vorgabe."""
    return wert if wert in {k for k, _ in DESIGNS} else DESIGN_VORGABE


def klang_gueltig(wert) -> str:
    """Ein Ton aus dem Browser, oder die Vorgabe."""
    return wert if wert in {k for k, _n, _b in KLAENGE} else KLANG_VORGABE


def eigen_lesen(wert) -> tuple[str, str]:
    """(Aussehen, Ton) aus dem Eintrag im Browser, geschrieben als
    "aussehen.ton", etwa "zukunft.pixel". Alles Ungueltige ergibt die
    Grundeinstellung eines neuen Browsers."""
    teile = str(wert or "").split(".")
    if len(teile) != 2:
        return DESIGN_VORGABE, KLANG_VORGABE
    return design_gueltig(teile[0]), klang_gueltig(teile[1])


def eigen_schreiben(design, klang) -> str:
    """Der Eintrag im Browser zu (Aussehen, Ton), nur aus erlaubten Zeichen."""
    return f"{design_gueltig(design)}.{klang_gueltig(klang)}"


def alarm_an(einst: dict, schluessel: str) -> bool:
    """Ist der Alarm mit diesem Schluessel eingeschaltet? Unbekanntes: ja."""
    return schluessel not in set((einst or {}).get("alarme_aus") or [])


def befund_an(einst: dict, art) -> bool:
    """Wird ein Befund dieser Art gemeldet (BEFUND_ARTEN)? Unbekannte Art: ja."""
    s = BEFUND_ARTEN.get(str(art or ""))
    return True if s is None else alarm_an(einst, s)


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


def anzeige_name(name) -> str:
    """Der Name in der Anzeige zu einem Strategienamen aus Mappe oder Meldung,
    etwa "Cup & Handle, Wochenbasis" zu "Cup & Handle (Wochenbasis)". Ohne
    Registereintrag bleibt der Name, wie er ist; ein Zusatz hinter einem
    Namensanfang bleibt stehen."""
    n = str(name or "").strip()
    s = schluessel_fuer(n)
    if s is None:
        return n
    e = eintrag(s)
    if n in e["namen"]:
        return e["name"]
    return n


def muster_an(einst: dict, name) -> bool:
    """Meldet die Strategie mit diesem Namen? Ein Name ohne Registereintrag
    gilt als eingeschaltet (siehe Kopf: Neues ist an)."""
    s = schluessel_fuer(name)
    return True if s is None else alarm_an(einst, s)


def abgewaehlte_namen(einst: dict) -> list[str]:
    """Die Anzeigenamen der abgewaehlten Alarme, fuer Protokoll und Anzeige."""
    aus = set((einst or {}).get("alarme_aus") or [])
    return [a["name"] for a in ALARME if a["schluessel"] in aus]


def eintrag(schluessel: str) -> dict | None:
    return next((a for a in ALARME if a["schluessel"] == schluessel), None)


def regelwerk_gruppen() -> list[tuple[str, str, list[tuple[str, str]]]]:
    """Das Regelwerk der Strategien, aus dem Register erzeugt (Frage 76):
    je Gruppe (Name, Einleitung, [(Strategie, Absatz)]). Eine neue Strategie
    steht damit von selbst darin."""
    raus = []
    for g, gname in GRUPPEN:
        if g not in STRATEGIE_GRUPPEN:
            continue
        absaetze = [(a["name"], a.get("regel") or a["erklaerung"]) for a in ALARME if a["gruppe"] == g]
        if absaetze:
            raus.append((gname, GRUPPEN_REGEL.get(g, ""), absaetze))
    return raus


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
    eigene_wege = {"sektor_morgen", "sektor_radar", "ausstiege", "gewinnzonen", "schlussnah", "beobachtungen"}
    p("Jeder Eintrag hat Namen oder Namensanfaenge oder ist ein eigener Weg",
      all(a["namen"] or a.get("anfaenge") or a["schluessel"] in eigene_wege for a in ALARME))
    p("Jeder Eintrag hat eine Erklaerung von hoechstens 260 Zeichen",
      all(0 < len(a["erklaerung"]) <= 260 for a in ALARME),
      ", ".join(a["schluessel"] for a in ALARME if not 0 < len(a["erklaerung"]) <= 260))
    alle_namen = [n for a in ALARME for n in a["namen"]]
    p("Kein Strategiename gehoert zwei Eintraegen", len(alle_namen) == len(set(alle_namen)))
    verboten = ("–", "—", "|")
    texte = [a["name"] + a["erklaerung"] + a.get("regel", "") + a.get("warnung", "") for a in ALARME]
    texte += list(GRUPPEN_REGEL.values()) + [TREND_TEMPLATE_REGEL] + [n for _g, n in GRUPPEN]
    p("Kein Gedankenstrich und kein senkrechter Strich in Namen, Erklaerungen und Regeln",
      not any(z in t for t in texte for z in verboten))
    p("Keine Klammern in Namen und Texten der Anzeige", not any(z in t for t in texte for z in "()"))
    p("Jede Meldung zu offenen Positionen hat eine Warnung",
      all(a.get("warnung") for a in ALARME if a["gruppe"] == "positionen"))
    p("Nur die Meldungen zu offenen Positionen tragen eine Warnung",
      not any(a.get("warnung") for a in ALARME if a["gruppe"] != "positionen"))
    p("Der Sektor-Radar steht bei den Weiteren Auskuenften",
      (eintrag("sektor_radar") or {}).get("gruppe") == "info")
    p("Jede Art in BEFUND_ARTEN zeigt auf einen Eintrag",
      all(eintrag(s) for s in BEFUND_ARTEN.values()))
    p("Die Fallbacks heissen Fallback, auch die Gruppe",
      all(a["name"].startswith("Fallback ") for a in ALARME if a["gruppe"] == "ausweich")
      and dict(GRUPPEN)["ausweich"].startswith("Fallbacks"))

    p("Leere Datei ergibt die Vorgabe", lesen(b"") == VORGABE)
    p("Kaputte Datei ergibt die Vorgabe", lesen(b"{nicht json") == VORGABE)
    p("Keine Liste ergibt die Vorgabe", lesen(b"[1, 2]") == VORGABE)
    e = lesen(json.dumps({"alarme_aus": ["vcp", "gibtsnicht", "darvas"], "design": "zukunft",
                          "klang": "nova", "fremd": 1}).encode())
    p("Unbekannte Schluessel fallen weg, bekannte bleiben sortiert", e["alarme_aus"] == ["darvas", "vcp"], str(e))
    p("Aussehen und Ton einer alten Datei fallen weg", "design" not in e and "klang" not in e, str(e))
    p("Fremde Felder fallen weg", "fremd" not in e)
    roh = schreiben(e, "2026-09-23 22:10")
    p("Schreiben und Lesen ergeben dasselbe", {k: v for k, v in lesen(roh).items() if k != "geaendert"} == e)
    p("Die Datei endet mit LF und hat kein CR", roh.endswith(b"\n") and b"\r" not in roh)
    p("Der Zeitpunkt der Aenderung steht in der Datei", lesen(roh).get("geaendert") == "2026-09-23 22:10")
    p("Die Datei fuehrt weder Aussehen noch Ton", b"design" not in roh and b"klang" not in roh)

    p("Eintrag im Browser: gueltig", eigen_lesen("zukunft.pixel") == ("zukunft", "pixel"))
    p("Eintrag im Browser: leer ergibt die Grundeinstellung", eigen_lesen("") == ("standard", "kristall"))
    p("Eintrag im Browser: Unbekanntes ergibt die Vorgabe", eigen_lesen("bunt.hupe") == ("standard", "kristall"))
    p("Eintrag im Browser: Schreiben und Lesen", eigen_lesen(eigen_schreiben("zukunft", "aus")) == ("zukunft", "aus"))
    p("Eintrag im Browser: nur erlaubte Zeichen",
      all(c.isalnum() or c in "._-" for c in eigen_schreiben("zukunft", "warp")))

    p("Genauer Name: VCP", schluessel_fuer("VCP") == "vcp")
    p("Genauer Name: Cup & Handle (Wochenbasis) ist ein eigener Eintrag",
      schluessel_fuer("Cup & Handle (Wochenbasis)") == "cup_woche" and schluessel_fuer("Cup & Handle") == "cup")
    p("Namensanfang: Shakeout-Spring mit Zusatz",
      schluessel_fuer("Shakeout-Spring, Sekundärtest bestätigt") == "shakeout"
      and schluessel_fuer("Shakeout an starkem Level (Kapitel 10)") == "shakeout")
    p("Shakeout plus drei ist ein anderer Eintrag als Shakeout-Spring",
      schluessel_fuer("Shakeout plus drei") == "a_shakeout3")
    p("Gap and Go, Lücken-Bestätigungstag und Power-Gap teilen einen Schalter",
      schluessel_fuer("Gap and Go") == schluessel_fuer("Lücken-Bestätigungstag") == schluessel_fuer("Power-Gap")
      == "gapgo")
    p("Red-to-Green in beiden Schreibweisen", schluessel_fuer("Red-to-Green") == schluessel_fuer("Red to Green")
      == "r2g")
    p("Unbekannter Name hat keinen Eintrag", schluessel_fuer("Gibt es nicht") is None)
    p("Anzeigenamen: Klammern werden Beistriche",
      anzeige_name("Cup & Handle (Wochenbasis)") == "Cup & Handle, Wochenbasis"
      and anzeige_name("Fallback: Quartals-Hoch (63 Tage)") == "Fallback Quartals-Hoch, 63 Tage")
    p("Anzeigenamen: Power-Gap und Red to Green",
      anzeige_name("Gap and Go") == "Power-Gap" and anzeige_name("Red-to-Green") == "Red to Green")
    p("Anzeigenamen: Unbekanntes und Zusatz bleiben",
      anzeige_name("Gibt es nicht") == "Gibt es nicht"
      and anzeige_name("Shakeout-Spring, Sekundärtest bestätigt") == "Shakeout-Spring, Sekundärtest bestätigt")
    aus = {"alarme_aus": ["vcp", "a_wick", "ausstiege", "sektor_radar"]}
    p("Abgewaehlt: VCP aus, Darvas an", not muster_an(aus, "VCP") and muster_an(aus, "Darvas Box"))
    p("Abgewaehlt: Wick Play aus", not muster_an(aus, "Wick Play"))
    p("Unbekannter Name bleibt an", muster_an(aus, "Gibt es nicht"))
    p("Ohne Einstellungen ist alles an", all(muster_an(None, n) for n in alle_namen))
    p("Anzeigenamen der Abgewaehlten",
      abgewaehlte_namen(aus) == ["VCP", "Wick Play", "Ausstiege und Stops", "Sektor-Radar vor dem Schluss"],
      str(abgewaehlte_namen(aus)))
    p("Befunde: Ausstiege aus, Gewinnzonen an",
      not befund_an(aus, "kapitel11") and not befund_an(aus, "teilverkauf") and befund_an(aus, "klimax_zeichen"))
    p("Befunde: Sektor-Radar aus", not befund_an(aus, "sektor_radar"))
    p("Befunde: unbekannte Art bleibt an", befund_an(aus, "gibtsnicht") and befund_an(None, "kapitel11"))
    p("Meldungen: Red to Green und Power-Gap",
      meldungs_text("Red-to-Green Explosive: AAA") == "Red to Green Explosive: AAA"
      and meldungs_text("Einstieg Lücken-Bestätigungstag: BBB") == "Einstieg Power-Gap: BBB"
      and meldungs_text("Gap and Go") == "Power-Gap")
    p("Meldungen: anderes bleibt, auch None", meldungs_text("VCP; Lücke +8%") == "VCP; Lücke +8%"
      and meldungs_text(None) == "")
    rw = regelwerk_gruppen()
    namen_rw = [n for _g, _e, ab in rw for n, _t in ab]
    p("Regelwerk: jede Strategie hat einen Absatz",
      namen_rw == [a["name"] for a in ALARME if a["gruppe"] in STRATEGIE_GRUPPEN])
    p("Regelwerk: keine Meldung zu offenen Positionen darin",
      not any(n == a["name"] for n in namen_rw for a in ALARME if a["gruppe"] not in STRATEGIE_GRUPPEN))
    regeln = dict(ab for _g, _e, abs_ in rw for ab in abs_)
    p("Regelwerk nach dem Code: High & Tight Flag in höchstens 42 Handelstagen",
      "höchstens 42 Handelstagen" in regeln["High & Tight Flag"])
    p("Regelwerk nach dem Code: VCP mindestens zwei, höchstens sechs Kontraktionen",
      "mindestens zwei, höchstens sechs Kontraktionen" in regeln["VCP"])
    p("Regelwerk nach dem Code: Darvas mindestens drei plus drei Tage",
      "mindestens drei plus drei Tagen" in regeln["Darvas Box"])
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
