# -*- coding: utf-8 -*-
"""
QUIZ: der Reiter Quiz der App (Gerhard, 29.09.2026, Teil 3 c)
=============================================================
"Dein Claude Code denkt sich rund 100 Fragen aus, aufgeteilt in Kapitel.
  * Beispielkapitel: Grundlagen, Chartmuster, Volumen und Formel, Relative
    Staerke und Marktampel, Stops und Risiko, Scanner-Kennzahlen,
    Trader-Templates.
  * Multiple Choice mit einer richtigen Antwort und kurzer Erklaerung danach.
  * Ergebnis je Kapitel und gesamt, Wiederholen moeglich.
  * Die Fragen muessen zum Lexikon und zu unseren tatsaechlichen Regeln passen.
  * Auch das Quiz ist mit VoiceOver bedienbar."

100 Fragen in sieben Kapiteln, je vier Antworten, eine richtig. Jede Frage
verweist auf ihren Eintrag im Lexikon, und der Selbsttest prueft, dass es ihn
gibt. Die Zahlen der Regeln kommen wie im Lexikon aus config.py und den
Modulen; wo eine Frage mit Beispielzahlen rechnet, haelt
lexikon.beispiel_schwellen fest, auf welchen Werten sie beruht.

Die Reihenfolge der Antworten ist je Frage fest, aber verschieden: Die Stelle
der richtigen Antwort kommt aus der Pruefsumme der Frage. So bleibt sie bei
jedem Durchgang dieselbe, was mit dem Screenreader die Orientierung haelt, und
die richtige Antwort steht nicht immer an derselben Stelle.

Aufruf:
    python quiz.py --selbsttest
    python quiz.py --zeigen [Kapitel]
"""

import hashlib
import sys

from config import CFG
import einstellungen
import gewinn_zonen as gz
import chartmuster as cm
import lexikon
import lexikon_begriffe as lb
import scanner_ansicht as sa

KAPITEL = (
    ("grundlagen", "Grundlagen"),
    ("chartmuster", "Chartmuster"),
    ("volumen", "Volumen und Formel"),
    ("rs", "Relative Stärke und Marktampel"),
    ("stops", "Stops und Risiko"),
    ("kennzahlen", "Scanner-Kennzahlen"),
    ("templates", "Trader-Templates"),
)
KAPITEL_NAMEN = dict(KAPITEL)


def _stelle(frage: str) -> int:
    """Die Stelle der richtigen Antwort, 0 bis 3, aus der Pruefsumme der Frage."""
    return int(hashlib.sha1(frage.encode("utf-8")).hexdigest(), 16) % 4


def fragen() -> list:
    """Alle Fragen als dicts: kennung, kapitel, frage, antworten (vier),
    richtig (Stelle der richtigen Antwort), erklaerung, lexikon (Begriff)."""
    import pattern_scanner as ps
    ex, b, g = CFG["exit"], CFG["betrieb"], gz.CFG_GEWINN
    mb, q = CFG["marktbreite"], cm.QUELLE
    vz = einstellungen.vorzeichen_text
    deckel = lb._pz(ex["stop_deckel_pct"])
    fenster = lb._pz(b["nachlauf_grenze"])
    v_std = vz(einstellungen.volumen_vorgabe("rechteck"))
    v_52w = vz(einstellungen.volumen_vorgabe("fb_52w"))
    v_gap = vz(einstellungen.volumen_vorgabe("gapgo"))
    v_rueck = vz(einstellungen.ruecksetzer_vorgabe("earnings"))
    schluss = lb._uhr(b["schlussnahe_minute"])
    tpl = {t["id"]: t["felder"] for t in sa.TEMPLATES}
    ueber = "Prozent über dem 50-Tage-Schnitt"
    roh = []

    def neu(kapitel, frage, richtig, falsch, erklaerung, lex):
        roh.append((kapitel, frage, richtig, tuple(falsch), erklaerung, lex))

    # --------------------------------------------------------------- Grundlagen
    k = "grundlagen"
    neu(k, "Was ist ein Kaufpunkt?", "Der Kurs, über dem eine Aktie gekauft wird",
        ("Der Kurs, unter dem verkauft wird", "Der höchste Kurs der letzten 52 Wochen", "Der Schlusskurs des Vortags"),
        "Der Nachtscan rechnet den Kaufpunkt aus einem Muster; steigt der Kurs im Handel darüber, ist er gerissen, "
        "und der Wächter prüft das Volumen.", "Kaufpunkt")
    neu(k, "Wie weit darf ein Stop höchstens unter dem Kaufpunkt liegen?", f"{deckel} Prozent",
        ("5 Prozent", "15 Prozent", "20 Prozent"),
        f"Das ist der Zehn-Prozent-Deckel: Liegt der Bruchpunkt des Musters tiefer, zieht er den Stop auf {deckel} "
        "Prozent unter den Kaufpunkt hinauf.", "Zehn-Prozent-Deckel")
    neu(k, "Kaufpunkt 50 Dollar, der Bruchpunkt des Musters liegt bei 43 Dollar. Wo liegt der Stop?", "Bei 45 Dollar",
        ("Bei 43 Dollar", "Bei 46 Dollar", "Bei 47,50 Dollar"),
        "43 Dollar liegen 14 Prozent unter dem Kaufpunkt; der Deckel zieht den Stop auf 10 Prozent darunter, also auf "
        "45 Dollar.", "Zehn-Prozent-Deckel")
    neu(k, "Woran prüfen die Ausstiegsregeln, ob der Stop gerissen ist?", "Am Schlusskurs",
        ("An jedem Kurs im Handel", "Am Eröffnungskurs", "Am Wochenschluss"),
        "Ein kurzer Ausreißer im Handel löst bei den Ausstiegsregeln nichts aus. Der Handels-Bot legt nach dem Kauf "
        "zusätzlich eine Stop-Loss-Order zum Stop.", "Stop")
    neu(k, "Kaufpunkt 50 Dollar, Stop 46 Dollar. Wie hoch ist das Risk?", "8 Prozent",
        ("4 Prozent", "8,7 Prozent", "10 Prozent"),
        "Risk ist der Abstand vom Kaufpunkt zum Stop in Prozent des Kaufpunkts: 4 durch 50 sind 8 Prozent.",
        "Risk und R")
    neu(k, "Bis wie weit über dem Kaufpunkt wird ein Ausbruch als Kaufsignal gemeldet?", f"Bis {fenster} Prozent",
        ("Bis 2 Prozent", "Bis 10 Prozent", "Ohne Grenze"),
        f"Das ist das Einstiegsfenster; liegt der Kurs mehr als {fenster} Prozent darüber, kommt die Meldung "
        "übersprungen.", "Einstiegsfenster")
    neu(k, "Kaufpunkt 100 Dollar, die Aktie eröffnet bei 108 Dollar. Was geschieht?",
        "Es kommt die Meldung übersprungen, und der Bot bekommt eine Kaufzeile mit Limit 103,50 Dollar",
        ("Eine normale Kaufmeldung", "Gar nichts", "Ein Verkaufssignal"),
        f"Der Kurs liegt mehr als {fenster} Prozent über dem Kaufpunkt. Übersprungen ist kein Kaufsignal; die Order "
        "des Bots kommt nur zum Zug, wenn der Kurs zurückfällt.", "Übersprungen")
    neu(k, "Auf welchen Listen läuft die Darvas Box?", "Nur auf der Darvas-Liste und bei einzeln überwachten Aktien",
        ("Auf allen Wochenlisten", "Nur auf der großen Liste", "Im ganzen Markt"),
        "Alle anderen Strategien laufen auf allen Wochenlisten.", "Wochenlisten")
    neu(k, "Wie oft prüft der Wächter im Handel die Kurse?", f"Alle {int(b['pruef_takt_sekunden'])} Sekunden",
        ("Jede Minute", "Alle fünf Minuten", "Einmal vor dem Schluss"),
        "Der Wächter läuft während des ganzen Handels und meldet einen gerissenen Kaufpunkt binnen Sekunden.",
        "Wächter")
    neu(k, "Wann läuft der Nachtscan?",
        "Sonntag bis Freitag um 18:00 Uhr New Yorker Zeit, meist Mitternacht Wiener Zeit",
        ("Jeden Morgen um 8:00 Uhr Wiener Zeit", "Während des Handels", "Nur am Wochenende"),
        "Er rechnet Muster, Kaufpunkte und Stops für den nächsten Handelstag.", "Nachtscan")
    neu(k, "Mit welchem Limit kauft der Handels-Bot?", "3,5 Prozent über dem Kaufpunkt",
        ("Genau zum Kaufpunkt", "5 Prozent über dem Kaufpunkt", "Ohne Limit"),
        "Liegt der Kurs schon weiter darüber, kommt die Order erst zum Zug, wenn er zurückfällt.", "Handels-Bot")
    neu(k, "Welche Order legt der Handels-Bot sofort nach dem Kauf?", "Eine Stop-Loss-Order zum Stop",
        ("Eine Order für den Teilverkauf", "Eine zweite Kauforder", "Keine"),
        "Ohne Stop geht deshalb auch keine Kaufzeile hinaus.", "Handels-Bot")
    neu(k, "Wann endet die Überwachung einer einzeln überwachten Aktie?", "Mit dem Wochenputz am Freitag",
        ("Nach 24 Stunden", "Nach dem ersten Alarm", "Nie"),
        "Der Wächter nimmt sie binnen einer Minute auf; auf ihr laufen alle Strategien, auch die Darvas Box.",
        "Einzeln überwachte Aktie")
    neu(k, "Was ist ein Fallback?", "Ein Ersatz-Kaufpunkt ohne Muster für Aktien mit weniger als drei Mustern",
        ("Ein Stop für den Notfall", "Eine Meldung, wenn der Wächter ausfällt", "Ein zweiter Handels-Bot"),
        "Etwa knapp über dem 52-Wochen-Hoch oder einen Cent über dem Hoch der letzten 20 Handelstage.", "Fallback")
    neu(k, "Welche Bedingung gehört zum Trend Template?", f"Ein RS von mindestens {int(ps.CFG['tt_rs_min'])}",
        ("Ein Kurs unter dem 200-Tage-Durchschnitt", "Ein neues Allzeithoch", "Ein Zahlentermin in dieser Woche"),
        "Acht Bedingungen nach Mark Minervini; das Trend Template ist Voraussetzung für den VCP.", "Trend Template")
    neu(k, "Wie viele Handelstage hat ein Jahr ungefähr?", "252", ("365", "200", "300"),
        "Wochenenden und Feiertage zählen nicht; 21 Handelstage sind rund ein Monat.", "Handelstag")

    # -------------------------------------------------------------- Chartmuster
    k = "chartmuster"
    neu(k, "Was folgt bei der Darvas Box auf ein neues 52-Wochen-Hoch?", "Eine Box aus mindestens drei plus drei Tagen",
        ("Eine Tasse mit Henkel", "Eine Kurslücke von 7 Prozent", "Drei enge Wochen"),
        "Drei Tage bilden den Deckel, drei den Boden; Kaufpunkt einen Cent über der Oberkante.", "Darvas Box")
    neu(k, "Wie tief darf die Tasse beim Cup & Handle auf Tageskerzen sein?",
        f"{lb._pz(ps.CFG['cup_min_depth'])} bis {lb._pz(ps.CFG['cup_max_depth'])} Prozent",
        ("3 bis 25 Prozent", "Höchstens 15 Prozent", "20 bis 50 Prozent"),
        "Der Henkel liegt im oberen Drittel; Kaufpunkt über dem Henkelhoch.", "Cup & Handle")
    neu(k, "Was ist Voraussetzung für einen VCP?", "Das Trend Template ist erfüllt",
        ("Ein Zahlentermin am selben Tag", "Eine rote Marktampel", "Ein Insider-Kauf"),
        "Dazu kommen mindestens zwei immer engere Rücksetzer mit austrocknendem Volumen.", "VCP")
    neu(k, "Wo liegt der Kaufpunkt beim Rectangle Top?",
        "Einen Cent über der Oberkante, wenn der Kurs über dem 21-Tage-Durchschnitt liegt",
        ("Am Tief des Rechtecks", "In der Mitte des Rechtecks", "10 Prozent über der Oberkante"),
        "Stop einen Cent unter der Unterkante, Ziel gleich Ausbruch plus Rechteckhöhe.", "Rectangle Top")
    neu(k, "Was ist ein Inside Day?", "Ein Tag, dessen Hoch und Tief innerhalb der Spanne des Vortags liegen",
        ("Ein Tag mit einer Lücke nach oben", "Ein Tag, der unter dem Vortagestief eröffnet",
         "Ein Tag mit Rekordvolumen"),
        "Die Aktie atmet kurz durch; als Alarm-Muster zählt die Fassung mit drei steigenden Tagen davor.",
        "Inside Day")
    neu(k, "Welcher Inside Day meldet als Alarm-Muster?", "Nur die Fassung mit drei steigenden Tagen davor",
        ("Jeder Inside Day", "Nur einer an einem Freitag", "Nur einer mit Zahlen am selben Tag"),
        "Gemeldet wird der Ausbruch über das Hoch des Inside Day; der konservative Einstieg über dem Vortageshoch steht "
        "daneben.", "Inside Day")
    neu(k, "Wie nah liegen die Wochenschlüsse bei Three Weeks Tight beieinander?",
        f"Höchstens {lb._pz(q['a_eng'])} Prozent vom Schluss der Vorwoche entfernt",
        ("Höchstens 5 Prozent entfernt", "Auf den Cent genau gleich", "Höchstens 10 Prozent entfernt"),
        f"Es zählen {q['a_wochen_min']} oder {q['a_wochen_max']} enge Wochen nach einem Anstieg; Kaufpunkt über dem "
        "höchsten Wochenhoch der engen Wochen.", "Three Weeks Tight")
    neu(k, "Was muss das Volumen am Tag eines Pocket Pivot übertreffen?",
        "Das Volumen jedes Abwärtstags der letzten zehn Handelstage",
        ("Den 200-Tage-Schnitt", "Das Doppelte des Vortags", "Das größte Volumen jemals"),
        "Gekauft wird über dem Hoch des Pivot-Tages.", "Pocket Pivot")
    n1, n2 = (lb._pz(x) for x in q["n_aufschlag"])
    neu(k, "Bei welchem Abstand über dem Tief des Abverkaufs meldet Shakeout plus drei?", f"{n2} Prozent",
        ("3 Prozent", f"{n1} Prozent", "20 Prozent"),
        f"Gemeldet wird der Einstieg {n2} Prozent über dem Tief; der bei {n1} Prozent steht in der Meldung daneben.",
        "Shakeout plus drei")
    neu(k, "Wie lang ist der Docht beim Wick Play mindestens?", "Doppelt so lang wie der Körper",
        ("Gleich lang wie der Körper", "Fünfmal so lang wie der Körper", "Länger als die ganze Spanne des Vortags"),
        "Der Docht zeigt, dass Käufer einen Rückfall an einer markanten Stelle abgefangen haben.", "Wick Play")
    neu(k, "Wie groß muss die Kurslücke beim Power-Gap mindestens sein?",
        f"{lb._pz(CFG['gap_and_go']['gap_min'])} Prozent", ("3 Prozent", "5 Prozent", "15 Prozent"),
        "Dazu kommen ein Schluss im oberen Fünftel der Tagesspanne und hohes Volumen am Lückentag.", "Power-Gap")
    neu(k, "Wann wird beim Power-Gap gekauft?",
        "Am Handelstag nach der Lücke, solange der Kurs höchstens 3 Prozent über dem Kaufpunkt steht",
        ("Sofort am Lückentag", "Eine Woche später", "Nie, der Power-Gap ist nur eine Auskunft"),
        "Am Lückentag kommt die Meldung; der Einstieg am Folgetag ist ein Tagesgeschäft.", "Power-Gap")
    neu(k, "Was wird beim Earnings-Pullback gekauft?",
        "Der Ausbruch aus der ersten ruhigen Konsolidierung nach dem Kurssprung auf Zahlen",
        ("Der Kurssprung selbst", "Der Tag vor den Zahlen", "Der erste Schluss unter der 50-Tage-Linie"),
        "Kaufpunkt einen Cent über dem Hoch der Konsolidierung.", "Earnings-Pullback")
    neu(k, "Was gilt beim Crash-Support?", "Die Funde stehen nur im Logbuch; eine Meldung gibt es bisher nicht",
        ("Er meldet jeden Tag", "Er gilt nur bei grüner Marktampel", "Er kauft ohne Volumenprüfung"),
        "Er sucht große, gesunde Firmen an einer Unterstützungszone, nur während einer Marktkorrektur.",
        "Crash-Support")
    neu(k, "Was ist ein Episodic Pivot?",
        "Eine große Eröffnungslücke mit viel Volumen nach langer Ruhe, meist ausgelöst durch Zahlen",
        ("Ein Rücksetzer an die 10-Tage-Linie", "Ein langsamer Anstieg über viele Monate",
         "Ein Verkaufssignal nach Zahlen"),
        "Einstieg über dem Eröffnungsbereich des Lückentags.", "Episodic Pivot")
    neu(k, "Ab welcher Stufe heißt eine Basis spät?", "Ab Stufe 3", ("Ab Stufe 1", "Ab Stufe 2", "Ab Stufe 5"),
        "Frühe Basen, Stufe 1 und 2, gelten als die besten; ab Stufe 4 heißt die Basis sehr spät.",
        "Stufenzählung der Basen")

    # -------------------------------------------------------- Volumen und Formel
    k = "volumen"
    neu(k, "Was heißt plus 100 Prozent über dem 50-Tage-Schnitt?", "Doppelt so viel Volumen wie üblich",
        ("Hundertmal so viel", "Genau so viel wie üblich", "Halb so viel"),
        "0 heißt so viel wie üblich, plus 100 doppelt so viel, minus 50 die Hälfte.", "Prozent über dem 50-Tage-Schnitt")
    neu(k, "Was heißt minus 50 Prozent über dem 50-Tage-Schnitt?", "Die Hälfte des üblichen Volumens",
        ("50 Stück weniger als üblich", "Gar kein Volumen", "Anderthalbmal so viel"),
        "Das Vorzeichen sagt, ob mehr oder weniger gehandelt wird als im 50-Tage-Schnitt.",
        "Prozent über dem 50-Tage-Schnitt")
    neu(k, "Wozu dient die F(t)-Kurve?", "Sie rechnet das bisherige Volumen des Tages auf den ganzen Tag hoch",
        ("Sie zeigt den Kursverlauf", "Sie berechnet den Stop", "Sie misst die Relative Stärke"),
        "Sie sagt je Aktie, welcher Anteil des Tagesvolumens zu jeder Minute üblicherweise schon gehandelt ist.",
        "F(t)-Kurve")
    neu(k, "Um 10:00 Uhr sind üblicherweise 20 Prozent des Tagesvolumens gehandelt, bisher 400.000 Stück. Was ergibt "
           "die Hochrechnung?", "2 Millionen Stück", ("400.000 Stück", "800.000 Stück", "4 Millionen Stück"),
        "Bisheriges Volumen geteilt durch F(t): 400.000 durch 0,2.", "F(t)-Kurve")
    neu(k, "Ab wann beurteilt der Wächter das Volumen eines Ausbruchs?", "Fünf Minuten nach Handelsbeginn",
        ("Sofort zur Eröffnung", "Ab Mittag New Yorker Zeit", "Erst nach dem Schluss"),
        "Ein Kaufpunkt, der früher reißt, bleibt offen und meldet, sobald die Hochrechnung die Hürde nimmt.",
        "Erste Volumenprüfung")
    neu(k, "Welche Volumenhürde haben die Muster beim Ausbruch in der Vorgabe?", f"Mindestens {v_std} {ueber}",
        (f"Mindestens plus 100 {ueber}", f"Mindestens plus 200 {ueber}", "Keine"),
        "Die Hürden lassen sich im Reiter Einstellungen je Muster ändern.", "Volumenhürden")
    neu(k, "Welche Volumenhürde hat der Fallback 52-Wochen-Hoch in der Vorgabe?", f"Mindestens {v_52w} {ueber}",
        (f"Mindestens plus 60 {ueber}", f"Mindestens plus 200 {ueber}", "Keine"),
        "Er braucht mehr Volumen als die Muster.", "Volumenhürden")
    neu(k, "Welche Volumenhürde hat der Power-Gap am Lückentag in der Vorgabe?", f"Mindestens {v_gap} {ueber}",
        (f"Mindestens plus 60 {ueber}", f"Mindestens plus 100 {ueber}", f"Mindestens 0 {ueber}"),
        "Am Einstiegstag danach genügt der Schnitt, also mindestens 0.", "Volumenhürden")
    neu(k, "Wie viel Volumen darf ein Rücksetzer-Tag beim Earnings-Pullback höchstens haben?",
        f"Höchstens {v_rueck} {ueber}, also die Hälfte des Schnitts",
        (f"Höchstens plus 60 {ueber}", "Beliebig viel", f"Höchstens plus 200 {ueber}"),
        "Liegt ein Tag darüber oder fehlen seine Volumendaten, ist das Setup ungültig.",
        "Rücksetzer-Tage beim Earnings-Pullback")
    neu(k, "Was besagt Regel 3?", "Gemeldet wird nur mit echten Volumendaten und bestätigter Hürde",
        ("Ein Kaufpunkt meldet dreimal am Tag", "Gemeldet wird nur bei grüner Marktampel",
         "Gemeldet wird schon beim Berühren des Kaufpunkts"),
        "Liefert Yahoo noch kein Volumen, bleibt der Kaufpunkt offen und wird weiter geprüft.",
        "Regel 3, nur verifiziertes Volumen")
    neu(k, "Warum sieht der Wächter das Volumen der Schlussauktion nicht?",
        "Yahoo zählt es erst nach dem Schluss zum Tagesvolumen",
        ("Die Auktion findet am Vormittag statt", "Es zählt nie zum Volumen", "Die Auktion gibt es nur an Freitagen"),
        "Das volle Tagesvolumen steht deshalb erst nach dem Schluss fest.", "Schlussauktion")
    neu(k, "Was ist das Dollarvolumen?", "Kurs mal Volumen",
        ("Volumen geteilt durch den Kurs", "Der Börsenwert", "Die Zahl der ausstehenden Aktien"),
        "1 Million Stück zu 40 Dollar sind 40 Millionen Dollar.", "Dollarvolumen")
    neu(k, "Was zeigt austrocknendes Volumen in einer Basis?",
        "Kaum noch jemand verkauft; das Volumen wird vor dem Ausbruch kleiner",
        ("Große Anleger verkaufen", "Der Ausbruch ist gescheitert", "Die Aktie wird bald von der Börse genommen"),
        "Kennzahlen dafür sind das Austrocknen des Volumens und das Verhältnis von 5 zu 20 Tagen, beide unter 0.",
        "Volumen trocknet aus")
    neu(k, "Was heißt ein relatives Volumen von plus 150 Prozent?", "Zweieinhalbmal so viel wie üblich",
        ("Anderthalbmal so viel", "150-mal so viel", "Weniger als üblich"),
        "Ein Volumen von plus 150 Prozent über dem Schnitt ist zweieinhalbmal so viel wie üblich.",
        "Relatives Volumen")

    # ------------------------------------------ Relative Staerke und Marktampel
    k = "rs"
    neu(k, "Was misst das RS?",
        "Wie stark eine Aktie in zwölf Monaten gestiegen ist, verglichen mit allen US-Aktien, als Wert von 1 bis 99",
        ("Den Gewinn je Aktie", "Wie stark eine Aktie schwankt", "Den Abstand zum 52-Wochen-Hoch"),
        "Junge Titel mit weniger als einem Jahr Kurshistorie bekommen ein vorläufiges RS.", "RS, Relative Stärke")
    neu(k, "Welche Rendite zählt beim RS doppelt?", "Die der letzten drei Monate",
        ("Die des letzten Jahres", "Die der letzten Woche", "Alle zählen gleich"),
        f"Dazu zählen die Renditen über sechs, neun und zwölf Monate; jede wird bei plus "
        f"{lb._pz(CFG['lookback']['rs_kappung'])} Prozent gekappt.", "RS, Relative Stärke")
    neu(k, "Was heißt RS 95?", "Die Aktie war stärker als 95 Prozent aller Aktien",
        ("Die Aktie ist um 95 Prozent gestiegen", "Die Aktie steht auf Platz 95", "Die Aktie war an 95 Tagen im Plus"),
        "Sie gehört zu den stärksten 5 Prozent des Markts.", "RS, Relative Stärke")
    neu(k, "Was ist die RS-Linie?", "Der Kurs der Aktie geteilt durch den Kurs eines Index",
        ("Die 50-Tage-Linie", "Der Kurs der Aktie minus der Index", "Die Linie der Kursziele der Analysten"),
        "Gegen SPY für den S&P 500 und gegen QQQ für den Nasdaq 100; steigt sie, ist die Aktie stärker als der Markt.",
        "RS-Linie")
    neu(k, "Was zeigt eine RS-Linie auf dem 52-Wochen-Hoch?", "Führungsstärke, oft noch vor dem Kurs",
        ("Ein Verkaufssignal", "Eine schwache Aktie", "Einen Zahlentermin"),
        "Der RS-Linien-Bericht nennt jeden Abend die Aktien, deren Linie gegen SPY und QQQ zugleich auf dem Hoch steht.",
        "RS-Linie auf dem 52-Wochen-Hoch")
    neu(k, "Wann ist die Marktampel rot?", "Wenn mindestens ein Index unter seiner SMA 50 schließt",
        ("Wenn beide Indizes an einem Tag fallen", "Bei jedem Distribution Day", "Wenn mehr Aktien fallen als steigen"),
        "Gemessen wird am Schluss von S&P 500 und Nasdaq.", "Marktampel")
    neu(k, "Wann ist die Marktampel grün?",
        "Beide Indizes schließen über EMA 21 und SMA 50, die EMA 21 liegt über der SMA 50, und die SMA 50 steigt",
        ("Wenn der S&P 500 an einem Tag steigt", "Wenn mehr Aktien steigen als fallen",
         "Wenn der Nasdaq ein Allzeithoch macht"),
        "Alles zwischen grün und rot ist gelb.", "Marktampel")
    neu(k, "Was tut die Marktampel bei Rot mit den Kaufmeldungen?",
        "Nichts; sie informiert nur und hält keine Meldung zurück",
        ("Sie stoppt alle Kaufmeldungen", "Sie halbiert die Kaufzeilen", "Sie verkauft alle Positionen"),
        "Die Ampel filtert keine Aktie.", "Marktampel")
    neu(k, "Was ist ein Distribution Day?",
        f"Ein Index schließt mindestens {lb._z(mb['dd_verlust_pct'])} Prozent tiefer bei höherem Volumen als am "
        "Vortag", ("Ein Index steigt um 1 Prozent", "Ein Tag mit einer Dividende", "Ein Feiertag an der Börse"),
        "Ein Zeichen, dass große Anleger verkaufen; er zählt 25 Handelstage lang.", "Distribution Day")
    neu(k, "Ab wie vielen Distribution Days heißt der Markt nach IBD unter Druck?", f"Ab {int(mb['dd_druck_ab'])}",
        ("Ab 1", f"Ab {int(mb['dd_korrektur_ab'])}", "Ab 10"),
        f"Ab {int(mb['dd_korrektur_ab'])} heißt er Korrektur; die Zählung ändert die Farbe der Marktampel nicht.",
        "Distribution Day")
    neu(k, "Ab welchem Tag eines Erholungsversuchs zählt ein Follow-through Day?", f"Ab Tag {int(mb['ftd_ab_tag'])}",
        ("Ab Tag 1", "Ab Tag 10", "Ab Tag 25"),
        f"Nötig ist ein Anstieg eines Index um mindestens {lb._z(mb['ftd_gewinn_pct'])} Prozent bei höherem Volumen "
        "als am Vortag.", "Follow-through Day")
    neu(k, "Wonach reiht die Sektor-Rangliste die Branchen-ETFs?",
        "Nach dem Faber-Mittel ihrer Renditen über 1, 3, 6, 9 und 12 Monate",
        ("Nach dem Börsenwert", "Alphabetisch", "Nach der Dividendenrendite"),
        "Daneben stehen der Rang vor drei und vor sechs Wochen.", "Sektor-Rangliste")
    neu(k, "Wann prüft der Sektor-Radar?", f"Um {schluss} Uhr New Yorker Zeit, kurz vor Schluss",
        ("Zur Eröffnung", "In der Nacht", "Am Wochenende"),
        "Ein Branchen-ETF dreht, wenn er seinen 10-Tage-Schnitt kreuzt und sein Volumen zugleich ausschlägt.",
        "Sektor-Radar")
    neu(k, "Was heißt ein Mansfield RS über null?", "Die Aktie ist stärker als der Markt",
        ("Die Aktie ist schwächer als der Markt", "Die Aktie hat gerade Zahlen gemeldet", "Die Aktie ist überkauft"),
        "Er misst die RS-Linie gegen SPY im Verhältnis zu ihrem eigenen 52-Wochen-Schnitt.", "Mansfield RS")

    # ---------------------------------------------------------- Stops und Risiko
    k = "stops"
    neu(k, "Wann rückt der Stop auf Einstand?",
        f"Bei {lb._z(ex['breakeven_ab_r'])}R oder plus {lb._pz(ex['breakeven_ab_pct'])} Prozent, je nachdem was "
        "zuerst eintritt", ("Bei plus 5 Prozent", "Nach einer Woche", "Nie"),
        "Aus dem Gewinner wird so kein Verlust mehr.", "Stop auf Einstand")
    neu(k, "Einstieg 50 Dollar, Stop 46 Dollar. Bei welchem Kurs rückt der Stop auf Einstand?",
        "Bei 55 Dollar, plus 10 Prozent", ("Bei 58 Dollar", "Bei 60 Dollar", "Bei 52 Dollar"),
        "2R wären 58 Dollar, plus 10 Prozent sind 55 Dollar; es gilt, was zuerst eintritt.", "Stop auf Einstand")
    neu(k, "Bei welchem Gewinn kommt der Teilverkauf?", f"Bei plus {lb._pz(ex['teilverkauf_ab_pct'])} Prozent",
        ("Bei plus 10 Prozent", "Bei plus 50 Prozent", "Bei plus 100 Prozent"),
        "Der Wächter meldet ihn im Handel, sobald der Kurs die Schwelle erreicht.", "Teilverkauf")
    anteil = lb._anteil_wort(ex["teilverkauf_anteil"])
    neu(k, "Wie viel wird beim Teilverkauf verkauft?", anteil[:1].upper() + anteil[1:],
        ("Ein Viertel", "Alles", "Ein Drittel"),
        "Der Bot bekommt dafür eine Verkaufszeile über die Hälfte.", "Teilverkauf")
    neu(k, "Wann ist der Teilverkauf ausgesetzt?", "Solange die Halteregel läuft",
        ("An Freitagen", "Bei roter Marktampel", "Nie"),
        "Darvas-Positionen kennen gar keinen Teilverkauf; dort wandert nur der Stop.", "Teilverkauf")
    neu(k, "Was löst die Halteregel aus?",
        f"{lb._pz(ex['schnellstarter_pct'])} Prozent Anstieg binnen {int(ex['schnellstarter_tage'])} Handelstagen nach "
        "dem Einstieg", ("Ein neues Allzeithoch", "Ein Insider-Kauf", "Eine grüne Marktampel"),
        "Solche Schnellstarter laufen oft weit.", "Halteregel")
    neu(k, "Wie lange gilt die Halteregel?",
        f"{int(ex['halteregel_tage'])} Handelstage ab dem Einstieg, rund acht Wochen",
        ("Eine Woche", "Ein Jahr", "Bis zum nächsten Zahlentermin"),
        "So lange ist der Teilverkauf ausgesetzt.", "Halteregel")
    neu(k, "Was ist ein Round Trip?",
        "Eine Aktie, die schon 20 Prozent im Plus war, fällt während der Halteregel mit dem Schluss auf den Einstieg "
        "zurück; alles wird verkauft",
        ("Kauf und Verkauf am selben Tag", "Ein Kurs, der um den Kaufpunkt pendelt", "Ein Fehlkauf ohne Stop"),
        "Ein dicker Gewinn darf nicht ganz verpuffen.", "Round Trip")
    neu(k, "Über welche Linie läuft der Rest nach dem Teilverkauf?", f"Über die {int(ex['trail_ma_schnell'])}-Tage-Linie",
        ("Über die 200-Tage-Linie", "Über die 5-Tage-Linie", "Über gar keine Linie"),
        "Schließt der Kurs darunter, wird der Rest verkauft.", "Nachzieh-Linie")
    neu(k, "Wann ist eine Position in der starken Gewinnzone?",
        f"Ab {lb._z(g['zone_stark_min_r'])}R oder mit einem Klimax-Zeichen",
        ("Ab plus 5 Prozent", "Ab 1R", "Erst ab plus 100 Prozent"),
        "Mittel ist sie ab 2R, ab plus 20 Prozent oder mit erreichtem Musterziel.", "Gewinnzonen")
    neu(k, "Welcher Zeitdeckel gilt für einen Insider-Kauf?", f"{int(g['zeitdeckel_monate_insider'])} Monate",
        ("60 Handelstage", "12 Monate", "Ein Tag"),
        "Eine Zahlen-Lücke endet nach 60 Handelstagen, alles andere nach 12 Monaten.", "Zeitdeckel")
    neu(k, "Was ist ein Klimax-Zeichen?",
        "Ein Zeichen, dass ein Anstieg sich erschöpft; Verkauf in die Stärke erwägen",
        ("Ein Kaufsignal", "Ein Zeichen für einen Börsengang", "Eine Lücke nach unten"),
        "Jedes Zeichen kommt je Aktie einmal als Bericht.", "Klimax")
    neu(k, "Ab welchem Abstand zur 200-Tage-Linie zählt das Klimax-Zeichen?",
        f"Ab {lb._pz(g['ma200_abstand_min'])} Prozent darüber",
        ("Ab 10 Prozent darüber", "Unter der Linie", "Genau auf der Linie"),
        f"Gezählt wird bis {lb._pz(g['ma200_abstand_max'] * 1.3)} Prozent darüber. Die übrigen Zeichen sind der "
        "Klimaxlauf, der größte Tagesgewinn, die Erschöpfungslücke und die obere Kanallinie.", "Klimax")
    neu(k, "Was zeigt Stufe 3 nach Weinstein?", "Die 30-Wochen-Linie wird flach: eine Topbildung",
        ("Einen frischen Aufwärtstrend", "Einen Boden", "Eine Kurslücke"),
        "Danach droht Stufe 4, der Abwärtstrend; ein Verkaufssignal ist es nicht.", "Stufe 3 nach Weinstein")
    neu(k, "Wo liegt die Exit-Linie bei Red to Green?", "Am Vortagesschluss",
        ("Am Tageshoch", "An der 200-Tage-Linie", "Am Eröffnungskurs"),
        "Fällt der Kurs darunter, kommt sofort das Verkaufssignal, und der Bot verkauft die ganze Position.",
        "Exit eines Tagesgeschäfts")
    neu(k, "Ist der 8-EMA-Hinweis ein Verkaufssignal?", "Nein, nur eine Beobachtung",
        ("Ja, alles verkaufen", "Ja, die Hälfte verkaufen", "Ja, aber nur an Freitagen"),
        "Er steht im Reiter Berichte, wenn eine gehaltene Aktie unter ihrer 8-Tage-Exponentiallinie schließt.",
        "8-EMA-Hinweis")

    # -------------------------------------------------------- Scanner-Kennzahlen
    k = "kennzahlen"
    neu(k, "Umsatz im jüngsten Quartal 120 Millionen Dollar, im Vorjahresquartal 100 Millionen. Wie hoch ist das "
           "Umsatzwachstum q/q?", "Plus 20 Prozent", ("Plus 120 Prozent", "Plus 16,7 Prozent", "Plus 2 Prozent"),
        "Jüngstes Quartal gegen dasselbe Quartal des Vorjahres.", "Umsatzwachstum q/q")
    neu(k, "Was misst das EPS-Wachstum?", "Das Wachstum des Gewinns je Aktie",
        ("Das Wachstum des Umsatzes", "Das Wachstum des Kurses", "Das Wachstum der Aktienzahl"),
        "EPS steht für Gewinn je Aktie; lag der Vorjahreswert bei null oder im Minus, ist kein Prozentwert "
        "berechenbar.", "EPS-Wachstum q/q")
    neu(k, "Was ist die ADR?", "Die mittlere Tagesspanne der letzten 20 Handelstage in Prozent",
        ("Der Abstand zum Allzeithoch", "Die Dividendenrendite", "Die Zahl der Analysten"),
        "Je Tag Hoch geteilt durch Tief, davon das Mittel, minus 1.", "ADR nach Qullamaggie, 20 Tage")
    neu(k, "52-Wochen-Hoch 50 Dollar, Schluss 45 Dollar. Wie groß ist der Abstand zum 52-Wochen-Hoch?", "10 Prozent",
        ("5 Prozent", "11,1 Prozent", "45 Prozent"),
        "5 Dollar unter dem Hoch, gemessen am Hoch: 10 Prozent.", "Abstand zum 52-Wochen-Hoch")
    neu(k, "Was zeigt ein RSI 14 über 70?", "Die Aktie gilt als überkauft",
        ("Die Aktie gilt als überverkauft", "Die Aktie hat ein RS von 70", "Die Aktie hat Zahlen gemeldet"),
        "Unter 30 gilt sie als überverkauft.", "RSI 14")
    neu(k, "Was ist die Marktkapitalisierung?", "Kurs mal Zahl der ausstehenden Aktien, also der Börsenwert",
        ("Der Umsatz eines Jahres", "Der Gewinn eines Jahres", "Die Summe der Schulden"),
        "100 Millionen Aktien zu 30 Dollar sind 3 Milliarden Dollar.", "Marktkapitalisierung")
    neu(k, "Im Scanner steht bei der Marktkapitalisierung 0,7. Was heißt das?", "700 Millionen Dollar",
        ("0,7 Millionen Dollar", "7 Milliarden Dollar", "70 Millionen Dollar"),
        "Die Marktkapitalisierung steht in Milliarden Dollar.", "Marktkapitalisierung")
    neu(k, "Was ist das KGV?", "Der Börsenwert geteilt durch den Nettogewinn der letzten vier Quartale",
        ("Der Kurs geteilt durch den Umsatz", "Der Gewinn geteilt durch die Schulden", "Der Kurs mal dem Gewinn"),
        "Es gibt das KGV nur bei Gewinn.", "KGV")
    neu(k, "Was heißt eine Schlusslage von 100?", "Der Schluss lag am Tageshoch",
        ("Der Schluss lag am Tagestief", "Die Aktie ist um 100 Prozent gestiegen", "Es wurden 100 Aktien gehandelt"),
        "0 heißt am Tagestief, 100 am Tageshoch.", "Schlusslage in der Tagesspanne")
    neu(k, "Was ist ein Momentum Burst nach Stockbee?",
        "Schluss mindestens 4 Prozent über dem Vortag bei höherem Volumen und mindestens 100.000 Stück",
        ("Eine Lücke von 10 Prozent", "Ein neues Allzeithoch", "Ein Tag ohne Kursänderung"),
        "Ein kurzer Schub, oft der Beginn einer Bewegung über mehrere Tage.", "Momentum Burst nach Stockbee")
    neu(k, "Was heißt ein Wert unter 0 bei Austrocknen des Volumens?",
        "Das Volumen der letzten zehn Tage liegt unter dem 50-Tage-Schnitt davor",
        ("Die Aktie ist überkauft", "Die Aktie hat keine Analysten", "Die Aktie ist gefallen"),
        "Ein austrocknendes Volumen zeigt, dass kaum noch jemand verkauft.", "Austrocknen des Volumens")
    neu(k, "Was zeigt der Leerverkaufsanteil im Scanner?",
        "Den Anteil der Leerverkäufe an den außerbörslich gemeldeten Umsätzen laut FINRA",
        ("Den Bestand offener Leerverkaufspositionen, das Short Interest", "Den Anteil der Aktien im Streubesitz",
         "Den Anteil der Kaufempfehlungen"),
        "Er ist ausdrücklich kein Short Interest.", "Leerverkaufsanteil am letzten Handelstag")
    neu(k, "Was heißt Rang 1 bei der Branchengruppe?", "Die stärkste Gruppe",
        ("Die schwächste Gruppe", "Die größte Gruppe", "Eine Gruppe mit nur einer Aktie"),
        "Gereiht wird nach dem Median der RS-Rohwerte ihrer Aktien.", "Rang der Branchengruppe")
    neu(k, "Bei Handelstage seit dem letzten 52-Wochen-Hoch steht 0. Was heißt das?",
        "Das Hoch wurde am letzten Handelstag erreicht",
        ("Es gibt kein Hoch", "Das Hoch liegt ein Jahr zurück", "Die Aktie ist neu an der Börse"),
        "Von 0 bis 5 findet alle Aktien mit einem 52-Wochen-Hoch in der letzten Woche.",
        "Handelstage seit dem letzten 52-Wochen-Hoch")

    # ------------------------------------------------------------ Trader-Templates
    k = "templates"
    neu(k, "Was tut ein Template bekannter Trader?",
        "Es setzt alles zurück und hakt genau die Kennzahlen des Traders mit seinen Werten an; es wählt nur Aktien aus",
        ("Es löst Alarme aus", "Es kauft automatisch", "Es ändert die Regeln des Wächters"),
        "Keine Strategie, kein Muster, kein Alarm.", "Templates bekannter Trader")
    neu(k, "Lassen sich die Templates überschreiben?",
        "Nein; sie sind fest, die Werte lassen sich nach dem Laden ändern, das Template bleibt",
        ("Ja, jederzeit", "Nur im Gastzugang", "Nur an Wochenenden"),
        "Eigene Einstellungen lassen sich dafür als Vorlage speichern.", "Templates bekannter Trader")
    neu(k, "Welche Eröffnungslücke verlangt Kell: Gappers?", f"Ab {tpl['kell_gappers']['luecke']['min']} Prozent",
        ("Ab 10 Prozent", "Ab 20 Prozent", "Ab 1 Prozent"),
        "Dazu Kurs ab 20 Dollar und mindestens 500.000 Stück im Schnitt.", "Kell: Gappers")
    neu(k, "Welchen Kurs verlangen die Templates von Oliver Kell mindestens?",
        f"{tpl['kell_bull_snort']['kurs']['min']} Dollar", ("5 Dollar", "10 Dollar", "50 Dollar"),
        "Dazu mindestens 500.000 Stück Volumen im Schnitt.", "Kell: Bull Snort")
    neu(k, "Was sucht Kell: Doublers?", "Aktien, die seit Jahresbeginn um mindestens 100 Prozent gestiegen sind",
        ("Aktien mit doppeltem Volumen", "Aktien mit doppeltem Umsatz", "Aktien mit zwei Kaufpunkten"),
        "Gemessen an der Wertentwicklung seit Jahresbeginn.", "Kell: Doublers")
    neu(k, "Was verlangt Qullamaggie: Episodic Pivot?",
        "Eine Eröffnungslücke ab 10 Prozent und in den ersten 20 Minuten mindestens ein ganzes übliches "
        "Tagesvolumen", ("Ein neues Allzeithoch", "Drei enge Wochen", "Ein RS von 99"),
        "Sinnvoll ab 20 Minuten nach der Eröffnung.", "Qullamaggie: Episodic Pivot")
    neu(k, "Was sucht Stockbee: EP 9 Millionen?",
        "Heute mindestens 9 Millionen Stück Volumen, im ganzen Jahr davor nie so viel",
        ("9 Millionen Dollar Gewinn", "Eine Lücke von 9 Prozent", "9 Tage im Plus"),
        "Dazu ein Kurs ab 3 Dollar.", "Stockbee: EP 9 Millionen")
    neu(k, "Was verlangt Walker: 40,40?", "EPS-Wachstum ab 40 Prozent in jedem der letzten drei Quartale",
        ("40 Prozent Umsatzwachstum im Jahr", "Einen Kurs über 40 Dollar", "40 Tage im Aufwärtstrend"),
        "Dazu Kurs ab 10 Dollar und höchstens 20 Prozent unter dem 52-Wochen-Hoch.", "Walker: 40,40")
    neu(k, "Was sucht Haber: RS vor Kurs?",
        "Die RS-Linie steht auf dem 52-Wochen-Hoch, der Kurs hatte sein Hoch nicht am letzten Handelstag",
        ("Kurs und RS-Linie zugleich auf dem Hoch", "Ein RS unter 50", "Einen fallenden Kurs"),
        "Die Stärke führt, der Kurs ist noch nicht am Hoch.", "Haber: RS vor Kurs")
    neu(k, "Was ist Oops nach Larry Williams?", "Eröffnung unter dem Vortagestief, Schluss wieder in der Vortagesspanne",
        ("Eine Lücke nach oben", "Ein Inside Day", "Ein neues 52-Wochen-Hoch"),
        "Die schärferen Fassungen verlangen einen Schluss über der Mitte oder über dem Hoch des Vortags.", "Oops")

    raus, zaehler = [], {}
    for kap, frage, richtig, falsch, erklaerung, lex in roh:
        zaehler[kap] = zaehler.get(kap, 0) + 1
        stelle = _stelle(frage)
        antworten = list(falsch)
        antworten.insert(stelle, richtig)
        raus.append({"kennung": f"{kap}_{zaehler[kap]:02d}", "kapitel": kap, "frage": frage, "antworten": antworten,
                     "richtig": stelle, "erklaerung": erklaerung, "lexikon": lex})
    return raus


def je_kapitel(liste) -> dict:
    raus = {k: [] for k, _n in KAPITEL}
    for fr in liste:
        raus.setdefault(fr["kapitel"], []).append(fr)
    return raus


def auswertung(liste, antworten: dict) -> dict:
    """{Kapitel: (richtig, beantwortet, Zahl der Fragen)} und "gesamt"; antworten
    ist {Kennung: gewaehlte Stelle} der gepruefte Stand."""
    raus = {}
    for kap, fragen_kap in je_kapitel(liste).items():
        beantwortet = [fr for fr in fragen_kap if fr["kennung"] in antworten]
        richtig = sum(1 for fr in beantwortet if antworten[fr["kennung"]] == fr["richtig"])
        raus[kap] = (richtig, len(beantwortet), len(fragen_kap))
    raus["gesamt"] = tuple(sum(w[i] for k, w in raus.items()) for i in range(3))
    return raus


def selbsttest() -> int:
    fehler = []

    def p(name, ok, info=""):
        print(("  OK    " if ok else "  FEHLER ") + name + (f" ({info})" if info and not ok else ""))
        if not ok:
            fehler.append(name)

    print("quiz.py, Selbsttest")
    liste = fragen()
    kap = je_kapitel(liste)
    p("Rund 100 Fragen", 95 <= len(liste) <= 110, str(len(liste)))
    p("Die sieben Kapitel aus dem Auftrag, jedes mit mindestens acht Fragen",
      [n for _k, n in KAPITEL] == ["Grundlagen", "Chartmuster", "Volumen und Formel", "Relative Stärke und Marktampel",
                                   "Stops und Risiko", "Scanner-Kennzahlen", "Trader-Templates"]
      and all(len(kap[k]) >= 8 for k, _n in KAPITEL), str({k: len(v) for k, v in kap.items()}))
    p("Kennungen eindeutig", len({fr["kennung"] for fr in liste}) == len(liste))
    p("Jede Frage einmal", len({fr["frage"] for fr in liste}) == len(liste))
    schlecht = [fr["kennung"] for fr in liste if len(fr["antworten"]) != 4 or len(set(fr["antworten"])) != 4
                or not 0 <= fr["richtig"] < 4]
    p("Je Frage vier verschiedene Antworten, eine davon richtig", not schlecht, ", ".join(schlecht))
    p("Jede Frage hat eine Erklaerung", all(fr["erklaerung"].strip() for fr in liste))
    lex = lexikon.eintraege()
    namen = {e["begriff"] for e in lex}
    ohne = [f"{fr['kennung']}: {fr['lexikon']}" for fr in liste if fr["lexikon"] not in namen]
    p("Jede Frage verweist auf einen Eintrag, den es im Lexikon gibt", not ohne, ", ".join(ohne))
    texte = [(fr["kennung"], x) for fr in liste for x in [fr["frage"], fr["erklaerung"]] + fr["antworten"]]
    schlecht = [(k, f) for k, x in texte for f in lexikon.textfehler(x)]
    p("Keine Klammern ausser F(t), kein Gedankenstrich, kein senkrechter Strich, keine Namen, kein Datum",
      not schlecht, str(schlecht[:6]))
    stellen = [fr["richtig"] for fr in liste]
    p("Die richtige Antwort steht nicht immer an derselben Stelle", all(stellen.count(i) >= 10 for i in range(4)),
      str([stellen.count(i) for i in range(4)]))
    p("Die Reihenfolge ist bei jedem Aufruf dieselbe", fragen() == liste)
    # Die Zahlen, auf denen Fragen mit Beispielen beruhen
    geaendert = [n for n, ist, soll in lexikon.beispiel_schwellen() if not lexikon._gleich(ist, soll)]
    p("Die Fragen mit Beispielzahlen beruhen auf den geltenden Schwellen", not geaendert, ", ".join(geaendert))
    tpl = {t["id"]: t["felder"] for t in sa.TEMPLATES}
    p("Die Werte der Templates, nach denen gefragt wird, stimmen",
      tpl["qm_ep"] == {"luecke": {"min": "10"}, "vol_erste20": {"min": "100"}}
      and tpl["sb_ep9"]["tag_volumen"] == {"min": "9.000.000"} and tpl["kell_doublers"]["perf_ytd"] == {"min": "100"}
      and all(tpl["walker_4040"][s] == {"min": "40"} for s in ("eps_q", "eps_q1", "eps_q2"))
      and tpl["kell_gappers"]["volumen"] == {"min": "500.000"})
    p("Der Power-Gap verlangt 7 Prozent Luecke, die Frage nennt den Wert aus config.py",
      any("7 Prozent" == a for fr in liste for a in fr["antworten"]) == (abs(CFG["gap_and_go"]["gap_min"] - 0.07) < 1e-9))
    # Auswertung
    erste = kap["grundlagen"]
    antw = {erste[0]["kennung"]: erste[0]["richtig"], erste[1]["kennung"]: (erste[1]["richtig"] + 1) % 4}
    a = auswertung(liste, antw)
    p("Auswertung je Kapitel und gesamt", a["grundlagen"] == (1, 2, len(erste)) and a["gesamt"] == (1, 2, len(liste))
      and a["templates"] == (0, 0, len(kap["templates"])), str(a["grundlagen"]) + str(a["gesamt"]))
    print(f"  {len(liste)} Fragen: " + ", ".join(f"{n} {len(kap[k])}" for k, n in KAPITEL))
    print("Ergebnis:", "alles bestanden" if not fehler else f"{len(fehler)} Fehler")
    return 1 if fehler else 0


def zeigen(kapitel=""):
    for fr in fragen():
        if kapitel and fr["kapitel"] != kapitel:
            continue
        print(f"[{KAPITEL_NAMEN[fr['kapitel']]}] {fr['frage']}")
        for i, a in enumerate(fr["antworten"]):
            print(("   * " if i == fr["richtig"] else "     ") + a)
        print("   " + fr["erklaerung"] + " Lexikon: " + fr["lexikon"])


if __name__ == "__main__":
    if "--selbsttest" in sys.argv:
        sys.exit(selbsttest())
    if "--zeigen" in sys.argv:
        rest = sys.argv[sys.argv.index("--zeigen") + 1:]
        zeigen(rest[0] if rest else "")
        sys.exit(0)
    print(__doc__)
