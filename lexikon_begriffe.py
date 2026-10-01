# -*- coding: utf-8 -*-
"""
DIE BEGRIFFE DES LEXIKONS, von Hand geschrieben (Gerhard, 29.09.2026, Teil 3 b)
==============================================================================
"Dort wird alles erklaert, was es im System gibt: alle Kennzahlen und Felder
des Scanners, alle Strategien und Muster, alle Templates bekannter Trader,
Marktampel, Relative Staerke, Volumenformel, Stop-Regeln, Wochenlisten,
Begriffe wie Kaufpunkt, Stop, Pivot, Basis. Einfaches, klares Deutsch, jeweils
mit kurzem Beispiel."

Hier stehen die Begriffe, die in keinem Register des Systems schon stehen.
Die Felder des Scanners, die Strategien, die Alarm-Muster und die Templates
nimmt lexikon.py aus ihren Registern; die Beispiele dazu stehen in
lexikon_beispiele.py.

JEDE AUSSAGE IST AM CODE GEPRUEFT (01.10.2026), und die Schwellen kommen aus
config.py, einstellungen.py, gewinn_zonen.py, chartmuster.py und den
Berichtsmodulen, nicht aus dem Gedaechtnis. Die Beispiele rechnen mit den
heutigen Werten; die Gesamtpruefung (Block D) haelt fest, auf welchen Werten
sie beruhen, und schlaegt an, sobald sich einer aendert.

Befunde der Pruefung, die das Lexikon so beschreibt, wie der Code es tut:
  * Die Ausstiegsregeln pruefen den Stop am Schlusskurs (exit_regeln:
    "Nur ein SCHLUSSKURS darunter loest aus, kein Docht"); der Handels-Bot
    legt nach dem Kauf zusaetzlich eine Stop-Loss-Order zum Stop (bot_kanal).
  * Die Nachzieh-Linie ist im Betrieb immer die 21-Tage-Linie: pruefe_exit
    wird nirgends mit trail_schnell=False gerufen, die 50-Tage-Linie fuer
    ruhige Bewegungen ist nicht angebunden.
  * Die Halteregel haengt im Betrieb nicht am Markt: markt_im_aufwaertstrend
    bleibt bei allen Aufrufen auf seiner Vorgabe True.
  * Darvas-Positionen haben weder Teilverkauf noch Gewinnzonen noch
    Zeitdeckel (gewinnzonen_lauf: "Darvas: keine Zonen, keine Ziele").

Jeder Eintrag: (Kapitel, Gruppe, Begriff, Erklaerung, Beispiel); die Gruppe
ist eine Zwischenueberschrift im Kapitel oder leer.
"""

from config import CFG
import berichte
import chartmuster as cm
import einstellungen
import gapup_bericht
import gewinn_zonen as gz
import rslinie_bericht


def _z(x, stellen=2) -> str:
    """Eine Zahl in deutscher Schreibweise ohne ueberfluessige Nullen."""
    s = f"{float(x):.{stellen}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s.replace(".", ",")


def _pz(x) -> str:
    """Ein Bruchteil als Prozentzahl: 0,1 wird 10."""
    return _z(float(x) * 100)


def _uhr(minute) -> str:
    """Minute des Tages als Uhrzeit: 945 wird 15:45."""
    m = int(minute)
    return f"{m // 60}:{m % 60:02d}"


def _karenz_satz(tage) -> str:
    n = int(tage)
    if n == 2:
        return "heute, morgen oder übermorgen"
    if n == 1:
        return "heute oder morgen"
    return f"heute oder in den nächsten {n} Handelstagen"


def _anteil_wort(anteil) -> str:
    a = float(anteil)
    return "die Hälfte" if abs(a - 0.5) < 1e-9 else f"{_pz(a)} Prozent"


def begriffe(einst=None) -> list:
    """Die Begriffe als Liste von (Kapitel, Gruppe, Begriff, Erklaerung,
    Beispiel). einst: die geltenden Einstellungen der App (Volumenhuerden),
    None heisst die Vorgaben."""
    ex, b = CFG["exit"], CFG["betrieb"]
    mb, sr, sl, ab = CFG["marktbreite"], CFG["sektor_radar"], CFG["sektor_rangliste"], CFG["abendbericht"]
    g = gz.CFG_GEWINN
    vz = einstellungen.vorzeichen_text
    deckel = _pz(ex["stop_deckel_pct"])
    fenster = _pz(b["nachlauf_grenze"])
    # Die Vorgaben; was gerade gilt, steht bei jeder Strategie selbst
    # (lexikon.py haengt dort den Satz mit dem eingestellten Wert an).
    v_std = vz(einstellungen.volumen_vorgabe("rechteck"))
    v_52w = vz(einstellungen.volumen_vorgabe("fb_52w"))
    v_gap = vz(einstellungen.volumen_vorgabe("gapgo"))
    v_rueck = vz(einstellungen.ruecksetzer_ueber(einst, "earnings"))
    tv = _pz(ex["teilverkauf_ab_pct"])
    anteil = _anteil_wort(ex["teilverkauf_anteil"])
    q, f = cm.QUELLE, cm.FESTLEGUNGEN
    e = []

    def neu(kapitel, begriff, text, beispiel, gruppe=""):
        e.append((kapitel, gruppe, begriff, text, beispiel))

    # ------------------------------------------------------------- Grundlagen
    neu("grundlagen", "Kaufpunkt",
        "Der Kurs, über dem eine Aktie gekauft wird. Der Nachtscan rechnet ihn aus einem Muster, meist einen Cent "
        "oder zehn Cent über einer Oberkante oder einem Hoch. Steigt der Kurs im Handel darüber, ist der Kaufpunkt "
        "gerissen; der Wächter meldet ihn, wenn das Volumen die Hürde nimmt und der Kurs noch im Einstiegsfenster "
        "liegt.",
        "Die Oberkante einer Darvas-Box liegt bei 50,00 Dollar, der Kaufpunkt bei 50,01 Dollar. Steigt die Aktie am "
        "nächsten Tag auf 50,40 Dollar, ist er gerissen.")
    neu("grundlagen", "Stop",
        f"Der Kurs, unter dem verkauft wird, weil das Muster dann widerlegt ist. Er steht am strukturellen "
        f"Bruchpunkt des Musters, höchstens aber {deckel} Prozent unter dem Kaufpunkt. Die Ausstiegsregeln prüfen "
        "ihn am Schlusskurs; ein kurzer Ausreißer im Handel löst dort nichts aus. Der Stop wandert nur nach oben, "
        "nie zurück. Der Handels-Bot legt nach dem Kauf zusätzlich eine Stop-Loss-Order zu diesem Stop.",
        "Kaufpunkt 50 Dollar, Unterkante der Box 46 Dollar: Der Stop liegt bei 46 Dollar. Schließt die Aktie bei "
        "45,80 Dollar, ist der Stop gerissen.")
    neu("grundlagen", "Zehn-Prozent-Deckel",
        f"Kein Stop liegt mehr als {deckel} Prozent unter dem Kaufpunkt. Liegt der Bruchpunkt des Musters tiefer "
        f"oder liefert das Muster keinen, zieht der Deckel den Stop auf {deckel} Prozent unter den Kaufpunkt hinauf, "
        f"auf den Cent nach oben gerundet. Die {deckel} Prozent sind eine Obergrenze, kein Ziel.",
        "Kaufpunkt 50 Dollar, Bruchpunkt des Musters bei 43 Dollar, also 14 Prozent darunter: Der Stop liegt bei 45 "
        "Dollar.")
    neu("grundlagen", "Risk und R",
        "Risk ist der Abstand vom Kaufpunkt zum Stop in Prozent des Kaufpunkts: so viel kostet ein Kauf zum "
        "Kaufpunkt höchstens, wenn der Stop greift. Er liegt nie über dem Zehn-Prozent-Deckel. R ist derselbe "
        "Abstand in Dollar; 2R im Plus heißt doppelt so viel Gewinn, wie der Stop gekostet hätte.",
        "Kaufpunkt 50 Dollar, Stop 46 Dollar: Risk 8 Prozent, 1R sind 4 Dollar. Bei 58 Dollar steht die Aktie 2R im "
        "Plus.")
    neu("grundlagen", "Musterziel",
        "Ein Kursziel aus der Höhe eines Musters: beim Cup & Handle Ausbruch plus Tassenhöhe, beim Rectangle Top "
        "Ausbruch plus Rechteckhöhe. Es steht in der Kaufmeldung als Auskunft und zählt bei den Gewinnzonen mit; "
        "ein Verkaufssignal ist es nicht.",
        "Ein Rechteck reicht von 40 bis 50 Dollar, der Ausbruch kommt bei 50 Dollar: Das Musterziel liegt bei 60 "
        "Dollar.")
    neu("grundlagen", "Pivot",
        "Der Wendepunkt eines Musters, über dem der Ausbruch beginnt; meist das Hoch, auf dem der Kaufpunkt sitzt. "
        "Beim VCP ist es das Hoch der letzten, engsten Kontraktion.",
        "Ein VCP zieht sich zuletzt zwischen 48 und 50 Dollar zusammen: Der Pivot ist das Hoch bei 50 Dollar, der "
        "Kaufpunkt liegt bei 50,01 Dollar.")
    neu("grundlagen", "Basis",
        "Eine Seitwärtsphase, in der eine Aktie nach einem Anstieg Atem holt, bevor sie weiter steigt. Tasse, "
        "flache Basis, Rechteck und Box sind Basen. Ihre Tiefe ist der Abstand vom linken Hoch zum tiefsten Tief, "
        "in Prozent des linken Hochs.",
        "Eine Aktie steigt von 30 auf 50 Dollar und pendelt danach sechs Wochen zwischen 45 und 50 Dollar: eine "
        "Basis mit 10 Prozent Tiefe.")
    neu("grundlagen", "Ausbruch",
        "Der Kurs steigt über die Oberkante einer Basis oder über ein Hoch, das ihn vorher gebremst hat. Gemeldet "
        "wird ein Ausbruch erst, wenn auch das Volumen die Hürde nimmt.",
        "Eine Aktie steigt bei plus 85 Prozent Volumen über ihr Basishoch von 50 Dollar.")
    neu("grundlagen", "Einstiegsfenster",
        f"Ein gerissener Kaufpunkt wird als Kaufsignal gemeldet, solange der Kurs höchstens {fenster} Prozent "
        "darüber liegt. Liegt er weiter darüber, kommt stattdessen die Meldung übersprungen.",
        "Kaufpunkt 100 Dollar: Bei 104 Dollar kommt die Kaufmeldung, bei 106 Dollar die Meldung übersprungen.")
    neu("grundlagen", "Übersprungen",
        f"Der Kaufpunkt ist gerissen, aber der Kurs lag dabei schon mehr als {fenster} Prozent darüber, etwa nach "
        "einer Lücke zur Eröffnung. Die Meldung ist ausdrücklich kein Kaufsignal; sie nennt, wie viel Risiko ein "
        "Einstieg jetzt hätte. Der Handels-Bot bekommt trotzdem eine Kaufzeile: Sein Limit liegt 3,5 Prozent über "
        "dem Kaufpunkt, die Order kommt also nur zum Zug, wenn der Kurs zurückfällt.",
        "Kaufpunkt 100 Dollar, Stop 92 Dollar, Eröffnung bei 108 Dollar: übersprungen. Ein Einstieg jetzt hieße 15 "
        "Prozent Risiko bis zum Stop statt der geplanten 8; das Limit des Bots liegt bei 103,50 Dollar.")
    neu("grundlagen", "Wochenlisten",
        "Die Aktien, die das System in einer Woche überwacht: die Darvas-Liste, die große Liste, die dritte und die "
        "vierte Liste, dazu die einzeln überwachten Aktien. Die Darvas Box läuft nur auf der Darvas-Liste und bei "
        "einzeln überwachten Aktien, alle anderen Strategien laufen auf allen Listen. Steht eine Aktie auf mehreren "
        "Listen, wird sie nur einmal überwacht und nur einmal gemeldet; eine Liste darf auch leer bleiben.",
        "Eine Aktie steht nur auf der großen Liste: Für sie rechnet der Nachtscan alle Strategien außer der Darvas "
        "Box.")
    neu("grundlagen", "Wochenputz",
        "Freitags nach Handelsschluss in New York endet die Woche: Die Kaufpunkte, die Fokusliste, die Kaufpunkte "
        "der Alarm-Muster und die einzeln überwachten Aktien der alten Woche werden geleert. Kaufpunkte gibt es "
        "danach erst wieder aus Wochenlisten, die nach diesem Freitag hochgeladen wurden.",
        "Der Putz läuft am Freitag um 16:02 Uhr New Yorker Zeit; neue Wochenlisten vom Wochenende liefern die "
        "Kaufpunkte ab Montag.")
    neu("grundlagen", "Einzeln überwachte Aktie",
        "Eine Aktie, die man beim Nachschlagen mit dem Knopf Diese Aktie überwachen zusätzlich überwachen lässt. "
        "Auf ihr laufen alle Strategien, auch die Darvas Box. Der Wächter nimmt sie im laufenden Handel binnen "
        "einer Minute auf und rechnet ihre Kaufpunkte selbst; der Wochenputz beendet die Überwachung.",
        "Man schlägt am Dienstag eine Aktie nach und drückt den Knopf: Ab dann meldet der Wächter auch ihre "
        "Kaufpunkte, bis zum Freitag.")
    neu("grundlagen", "Nachtscan",
        "Der nächtliche Lauf, Sonntag bis Freitag um 18:00 Uhr New Yorker Zeit, meist Mitternacht Wiener Zeit. Er "
        "rechnet für alle Aktien der Wochenlisten Muster, Kaufpunkte und Stops, schreibt die Mappe der Kaufpunkte "
        "für den nächsten Handelstag und baut die Scanner-Tabelle. Kaufsignale meldet nur der Wächter im "
        "Handel.",
        "Am Dienstag um Mitternacht Wiener Zeit rechnet der Nachtscan die Kaufpunkte, die der Wächter am Mittwoch "
        "überwacht.")
    neu("grundlagen", "Wächter",
        f"Der Lauf, der während des Handels alle {int(b['pruef_takt_sekunden'])} Sekunden die Kurse der überwachten "
        "Aktien prüft. Reißt ein Kaufpunkt mit bestätigtem Volumen, schickt er die Kaufmeldung aufs Handy und die "
        "Kaufzeile an den Handels-Bot; dazu meldet er Red to Green und den Power-Gap und legt um "
        f"{_uhr(b['schlussnahe_minute'])} Uhr New Yorker Zeit die schlussnahen Befunde in den Reiter Berichte.",
        "Um 15:47 Uhr Wiener Zeit steigt eine Aktie bei plus 70 Prozent Volumen über ihren Kaufpunkt: Die Meldung "
        "kommt wenige Sekunden später.")
    neu("grundlagen", "Handels-Bot",
        "Der Bot kauft und verkauft im Depot nach den Zeilen, die ihm der Wächter schickt: je gerissenem Kaufpunkt "
        "eine Kaufzeile mit Kürzel, Name, Woche, Kaufpunkt und Stop, je Ausstieg eine Verkaufszeile mit dem Anteil, "
        "ganz oder die Hälfte. Er kauft mit einem Limit 3,5 Prozent über dem Kaufpunkt und legt nach dem Kauf "
        "sofort eine Stop-Loss-Order zum Stop. Ohne Stop geht keine Kaufzeile hinaus.",
        "Kaufpunkt 40 Dollar, Stop 37 Dollar: Der Bot kauft mit Limit 41,40 Dollar und legt danach eine "
        "Stop-Loss-Order bei 37 Dollar.")
    neu("grundlagen", "Mappe der Kaufpunkte",
        "Die Tabelle, die der Nachtscan schreibt: je Aktie bis zu drei Kaufpunkte aus den wichtigsten Mustern, mit "
        "Stop, Ziel und Kennzahlen. Die Kaufpunkte der sechs Alarm-Muster stehen in einer eigenen Datei daneben und "
        "verdrängen keinen Kaufpunkt der Mappe.",
        "In der Mappe steht eine Aktie mit Kaufpunkt 1 aus einer Tasse mit Henkel und Kaufpunkt 2 aus dem Fallback "
        "20-Tage-Hoch.")
    neu("grundlagen", "Fallback",
        "Ein Ersatz-Kaufpunkt ohne Muster für Aktien mit weniger als drei Mustern, etwa knapp über dem "
        "52-Wochen-Hoch oder einen Cent über dem Hoch der letzten 20 Handelstage. Ein Fallback, über dem der Kurs "
        "schon am Vortag stand, meldet nicht.",
        "Eine Aktie hat nur eine Tasse: Die zwei freien Plätze füllen Fallbacks, etwa das 20-Tage-Hoch und das "
        "52-Wochen-Hoch.")
    neu("grundlagen", "Trend Template",
        "Nach Mark Minervini. " + einstellungen.TREND_TEMPLATE_REGEL,
        "Eine Aktie erfüllt sieben der acht Bedingungen, nur ihr RS liegt bei 65: Das Trend Template ist nicht "
        "erfüllt, und für sie entsteht kein VCP.")
    neu("grundlagen", "Handelstag",
        "Ein Tag, an dem die US-Börsen handeln; Wochenenden und Feiertage zählen nicht. 5 Handelstage sind eine "
        "Woche, 21 rund ein Monat, 63 ein Quartal, 126 ein halbes Jahr und 252 ein Jahr.",
        "Vom Freitag bis zum Dienstag darauf vergehen zwei Handelstage, weil Samstag und Sonntag nicht zählen.")
    neu("grundlagen", "Handelszeit",
        "Die US-Börse handelt von 9:30 bis 16:00 Uhr New Yorker Zeit, meist 15:30 bis 22:00 Uhr Wiener Zeit. In den "
        "Wochen, in denen nur eine Seite die Uhr umgestellt hat, liegt alles eine Stunde früher. Vorbörslich heißt "
        "vor 9:30 Uhr, nachbörslich nach 16:00 Uhr New Yorker Zeit.",
        "Bringt eine Firma ihre Zahlen um 7:00 Uhr New Yorker Zeit, sind sie vorbörslich; die Reaktion zeigt sich "
        "ab der Eröffnung um 15:30 Uhr Wiener Zeit.")

    # ------------------------------------------------------ Volumen und Formel
    neu("volumen", "50-Tage-Schnitt",
        "Das durchschnittliche Tagesvolumen der letzten 50 Handelstage. An ihm misst das System, ob an einem Tag "
        "viel oder wenig gehandelt wird.",
        "Eine Aktie handelt im Schnitt der letzten 50 Tage 800.000 Stück am Tag; heute sind es 1,2 Millionen.")
    neu("volumen", "Prozent über dem 50-Tage-Schnitt",
        "Die Schreibweise nach IBD für das Volumen: wie viel Prozent mehr oder weniger als im 50-Tage-Schnitt "
        "gehandelt wird, mit plus oder minus. 0 heißt so viel wie üblich, plus 100 doppelt so viel, minus 50 die "
        "Hälfte, minus 95 ein Zwanzigstel.",
        "Schnitt 800.000 Stück, heute 1,2 Millionen: plus 50 Prozent über dem 50-Tage-Schnitt.")
    neu("volumen", "Relatives Volumen",
        "Das Volumen eines Tages im Verhältnis zum 50-Tage-Schnitt, geschrieben als Prozent über dem Schnitt. Im "
        "Handel ist es über die F(t)-Kurve hochgerechnet, nach dem Schluss ist es das echte Tagesvolumen.",
        "Relatives Volumen plus 150 Prozent heißt zweieinhalbmal so viel wie üblich.")
    neu("volumen", "F(t)-Kurve",
        "Für jede überwachte Aktie die Kurve, welcher Anteil ihres Tagesvolumens zu jeder Minute üblicherweise "
        "schon gehandelt ist, gerechnet aus ihren eigenen Fünf-Minuten-Kerzen der letzten 50 Handelstage. Mit ihr "
        "rechnet der Wächter das bisherige Volumen auf den ganzen Tag hoch: bisheriges Volumen geteilt durch F(t), "
        "verglichen mit dem 50-Tage-Schnitt.",
        "Um 10:00 Uhr New Yorker Zeit sind bei einer Aktie üblicherweise 20 Prozent des Tagesvolumens gehandelt. "
        "Wurden bis dahin 400.000 Stück gehandelt, ergibt die Hochrechnung 2 Millionen Stück; bei einem Schnitt von "
        "1 Million sind das plus 100 Prozent.")
    neu("volumen", "Erste Volumenprüfung",
        "Das Volumen wird erst fünf Minuten nach Handelsbeginn beurteilt, um 9:35 Uhr New Yorker Zeit, meist 15:35 "
        "Uhr Wiener Zeit. Davor meldet der Wächter keinen Ausbruch; ein Kaufpunkt, der früher reißt, bleibt offen "
        "und meldet, sobald die Hochrechnung die Hürde nimmt.",
        "Ein Kaufpunkt reißt um 9:31 Uhr New Yorker Zeit: Gemeldet wird frühestens um 9:35 Uhr, wenn die "
        "Hochrechnung dann die Hürde nimmt.")
    neu("volumen", "Volumenhürden",
        "Wie viel Volumen ein Ausbruch braucht, damit der Wächter meldet, in Prozent über dem 50-Tage-Schnitt und "
        f"hochgerechnet über die F(t)-Kurve. In der Vorgabe: die Muster, Fallbacks und Alarm-Muster mindestens {v_std}, "
        f"der Fallback 52-Wochen-Hoch mindestens {v_52w}, der Power-Gap am Lückentag mindestens {v_gap} und am "
        "Einstiegstag danach mindestens 0. Der Earnings-Pullback hat am Tag des Ausbruchs keine Hürde, dafür gelten "
        "die Rücksetzer-Tage. Red to Green folgt eigenen Regeln, Insider-Käufe haben keine Volumenprüfung. Die Hürden "
        "lassen sich im Reiter Einstellungen je Muster ändern; was gerade gilt, steht bei jeder Strategie im Kapitel "
        "Chartmuster und Strategien.",
        f"Ein Rectangle Top reißt bei plus 45 Prozent: Der Wächter wartet. Steigt die Hochrechnung auf {v_std} "
        "Prozent oder mehr, meldet er.")
    neu("volumen", "Rücksetzer-Tage beim Earnings-Pullback",
        "Die Handelstage nach dem Kurssprung auf die Zahlen bis zum letzten abgeschlossenen Handelstag, also die "
        f"Tage der Konsolidierung. Jeder dieser Tage darf höchstens {v_rueck} Prozent über dem 50-Tage-Schnitt "
        "liegen. Liegt einer darüber oder fehlen seine Volumendaten, ist das Setup ungültig.",
        "Nach dem Sprung folgen vier ruhige Tage mit minus 60, minus 55, minus 70 und minus 52 Prozent: gültig. Läge "
        "ein Tag bei minus 40 Prozent, wäre das Setup ungültig.")
    neu("volumen", "Regel 3, nur verifiziertes Volumen",
        "Gemeldet wird nur, wenn echte Volumendaten von Yahoo vorliegen und die Hochrechnung die Hürde bestätigt; "
        "keine Meldung auf Verdacht, nur weil der Kurs den Kaufpunkt berührt. Liefert Yahoo noch kein Volumen, "
        "bleibt der Kaufpunkt offen und wird weiter geprüft.",
        "Der Kurs reißt den Kaufpunkt, Yahoo hat für die Aktie noch kein Tagesvolumen geschickt: keine Meldung, bis "
        "es kommt und die Hürde stimmt.")
    neu("volumen", "Schlussauktion",
        "Zum Handelsschluss um 16:00 Uhr New Yorker Zeit wird in einer Auktion oft viel gehandelt, am Quartalsende "
        "besonders. Yahoo zählt dieses Volumen erst nach dem Schluss zum Tagesvolumen. Im Handel sieht der Wächter es "
        "deshalb nicht; das volle Tagesvolumen steht erst danach fest.",
        "An einem Quartalsende kamen bei einer Aktie im Handel rund 699.000 Stück zusammen, mit der Schlussauktion "
        "1.038.000.")
    neu("volumen", "Dollarvolumen",
        "Kurs mal Volumen: wie viel Geld an einem Tag in einer Aktie umgeht. Es zeigt besser als die Stückzahl, ob "
        "sich eine Aktie für große Käufe eignet.",
        "1 Million Stück zu 40 Dollar sind 40 Millionen Dollar Dollarvolumen.")
    neu("volumen", "Volumen trocknet aus",
        "In einer gesunden Basis wird das Volumen vor dem Ausbruch kleiner, weil kaum noch jemand verkauft. Die "
        "Kennzahlen dafür sind das Austrocknen des Volumens und das Verhältnis von 5 zu 20 Tagen, beide unter 0.",
        "In den letzten zehn Tagen einer Basis liegt das Volumen bei minus 40 Prozent über dem 50-Tage-Schnitt.")

    # ---------------------------------------- Relative Staerke und Marktampel
    kapp = _pz(CFG["lookback"]["rs_kappung"])
    neu("rs", "RS, Relative Stärke",
        "Wie stark eine Aktie in den letzten zwölf Monaten gestiegen ist, verglichen mit allen Stammaktien des "
        "US-Markts, als Wert von 1 bis 99. Die Rendite der letzten drei Monate zählt doppelt so viel wie die über "
        f"sechs, neun und zwölf Monate; jede dieser Renditen wird bei plus {kapp} Prozent gekappt. 90 heißt stärker "
        "als 90 Prozent aller Aktien. Junge Titel mit weniger als einem Jahr Kurshistorie bekommen ein vorläufiges "
        "RS aus den vorhandenen Quartalen. Das RS ist eine Auskunft und filtert nichts; nur die Fokusliste für Red "
        f"to Green nimmt Aktien mit RS über {int(CFG['red_to_green']['rs_min'])}.",
        "Eine Aktie mit RS 95 gehört zu den stärksten 5 Prozent des Markts.")
    neu("rs", "RS-Linie",
        "Der Kurs der Aktie geteilt durch den Kurs eines Index, gegen SPY für den S&P 500 und gegen QQQ für den "
        "Nasdaq 100. Steigt die Linie, ist die Aktie stärker als der Markt. Ein 52-Wochen-Hoch der Linie zeigt "
        "Führungsstärke, oft noch vor dem Kurs.",
        "Der Markt fällt um 3 Prozent, die Aktie nur um 1 Prozent: Ihre RS-Linie steigt.")
    neu("rs", "RS-Linie auf dem 52-Wochen-Hoch",
        "Die RS-Linie steht so hoch wie seit einem Jahr nicht. Der RS-Linien-Bericht nennt jeden Abend alle Aktien, "
        "deren Linie gegen SPY und gegen QQQ zugleich auf dem Hoch steht, ab "
        f"{_z(rslinie_bericht.KURS_MIN, 0)} Dollar Kurs und {_z(rslinie_bericht.MARKTKAP_MIN_MRD * 1000, 0)} "
        "Millionen Dollar Börsenwert; neu ist, wer am Vortag noch nicht auf dem Hoch stand.",
        "Eine Aktie steht 3 Prozent unter ihrem Kurshoch, ihre RS-Linie aber auf dem 52-Wochen-Hoch: Sie hält sich "
        "besser als der Markt.")
    neu("rs", "Mansfield RS",
        "Relative Stärke nach Stan Weinstein: die RS-Linie gegen SPY im Verhältnis zu ihrem eigenen "
        "52-Wochen-Schnitt. Über null ist die Aktie stärker als der Markt.",
        "Mansfield RS plus 12 heißt, die Linie liegt 12 Prozent über ihrem Jahresschnitt.")
    neu("rs", "Marktampel",
        "Der Zustand des Gesamtmarkts aus S&P 500 und Nasdaq, gemessen am Schluss gegen die EMA 21 und die SMA 50 "
        "je Index. Grün: Beide Indizes schließen über beiden Linien, die EMA 21 liegt über der SMA 50, und die SMA "
        "50 steigt gegenüber zehn Handelstagen davor. Rot: Mindestens ein Index schließt unter seiner SMA 50. Gelb: "
        "alles dazwischen. Gerechnet wird jede Nacht mit dem Schluss des letzten Handelstags. Die Ampel informiert "
        "nur; sie filtert keine Aktie und hält keine Meldung zurück.",
        "Der S&P 500 schließt über beiden Linien, der Nasdaq unter seiner SMA 50: Die Ampel ist rot.")
    neu("rs", "Distribution Day",
        f"Ein Tag, an dem ein Index mindestens {_z(mb['dd_verlust_pct'])} Prozent tiefer schließt als am Vortag, "
        "bei höherem Volumen als am Vortag; ein Zeichen, dass große Anleger verkaufen. Ein Stalling Day ist ein "
        f"Tag mit höherem Volumen und einem Gewinn oder Verlust unter {_z(mb['stalling_gewinn_pct'])} Prozent. "
        f"Beide zählen {int(mb['dd_fenster'])} Handelstage lang und verfallen früher, sobald der Index "
        f"{_z(mb['dd_verfall_pct'])} Prozent über dem Schluss dieses Tages handelt. Ab {int(mb['dd_druck_ab'])} "
        f"heißt der Markt nach IBD unter Druck, ab {int(mb['dd_korrektur_ab'])} Korrektur. Die Zählung steht "
        "neben der Marktampel und ändert ihre Farbe nicht.",
        "Der Nasdaq schließt 1,1 Prozent tiefer bei höherem Volumen als gestern: ein Distribution Day.")
    neu("rs", "Follow-through Day",
        "Der Tag, der nach einer Korrektur einen Erholungsversuch bestätigt. Der Versuch beginnt mit dem ersten "
        f"höheren Schluss nach einem Tief; ab Tag {int(mb['ftd_ab_tag'])} zählt ein Anstieg eines Index um "
        f"mindestens {_z(mb['ftd_gewinn_pct'])} Prozent bei höherem Volumen als am Vortag. Ein Tief zählt bei "
        f"einem Schluss unter der {int(mb['ftd_linie_tage'])}-Tage-Linie, der zugleich der tiefste der letzten "
        f"{int(mb['ftd_tief_fenster'])} Handelstage ist.",
        "Am sechsten Tag nach dem Tief steigt der S&P 500 um 1,8 Prozent bei höherem Volumen: Follow-through Day.")
    neu("rs", "Marktbreite",
        "Wie breit der Markt einen Anstieg oder Fall trägt, gezählt über alle Stammaktien: Steiger und Faller je "
        "Tag, die A/D-Linie, der McClellan-Oszillator, der Anteil der Aktien über SMA 20, 50 und 200, neue Hochs "
        "und Tiefs und die Zahlen des Stockbee Market Monitor. Sie steht im Abendbericht.",
        "Der S&P 500 steigt, aber nur 40 Prozent der Aktien liegen über ihrer SMA 50: Der Anstieg ist schmal.")
    neu("rs", "Sektor-Rangliste",
        "Die 36 Branchen-ETFs, gereiht nach dem Faber-Mittel, dem Mittel ihrer Renditen über 1, 3, 6, 9 und 12 "
        "Monate; daneben stehen der Rang vor drei und vor sechs Wochen.",
        "Der Halbleiter-ETF hat über die fünf Zeiträume im Mittel 18 Prozent gewonnen und steht damit auf Rang 2.")
    neu("rs", "Sektor-Aufsteiger",
        f"Jeden Morgen die Aufsteiger der Sektor-Rangliste: neu unter den ersten {int(sl['aufsteiger_top'])} oder "
        f"um mindestens {int(sl['aufsteiger_raenge'])} Ränge in drei Wochen gestiegen. Eine Rangfolge nach den "
        "Schlusskursen des Vortags, kein Kursalarm; sie steht im Reiter Berichte.",
        "Ein Branchen-ETF steigt in drei Wochen von Rang 12 auf Rang 4: Er steht bei den Sektor-Aufsteigern.")
    neu("rs", "Sektor-Radar",
        f"Um {_uhr(b['schlussnahe_minute'])} Uhr New Yorker Zeit prüft der Wächter, ob ein Branchen-ETF dreht: Sein "
        f"Kurs kreuzt den eigenen {int(sr['ma_tage'])}-Tage-Schnitt, und sein hochgerechnetes Volumen liegt "
        f"zugleich mindestens plus {_z(sr['vol_pct_schwelle'], 0)} Prozent über dem 50-Tage-Schnitt; der Abstand "
        "zur Linie muss sich seit zwei Tagen in dieselbe Richtung entwickelt haben. Eine Auskunft, kein "
        "Kaufsignal.",
        f"Der Halbleiter-ETF steigt über seinen {int(sr['ma_tage'])}-Tage-Schnitt bei plus 70 Prozent Volumen: "
        "Sektor-Radar dreht nach oben.")
    neu("rs", "Branchengruppe",
        "Die Aktien einer Nasdaq-Branche als Gruppe, gereiht nach dem Median der RS-Rohwerte ihrer Aktien; Rang 1 "
        "ist die stärkste Gruppe.",
        "Eine Gruppe springt in drei Wochen von Rang 40 auf Rang 8: Geld fließt in diese Branche.")

    # ---------------------------------------------------------- Stops und Risiko
    neu("stops", "Struktureller Bruchpunkt",
        "Der Punkt im Chart, an dem das Muster widerlegt ist, etwa der Boden einer Box, die Unterkante eines "
        "Rechtecks oder das Tief des Henkels. Dort liegt der Stop, gedeckelt bei "
        f"{deckel} Prozent unter dem Kaufpunkt.",
        "Bei einer Tasse mit Henkel liegt der Bruchpunkt am Tief des Henkels.")
    neu("stops", "Stop auf Einstand",
        f"Stufe A der Ausstiegsregeln: Steht die Aktie {_z(ex['breakeven_ab_r'])}R oder plus "
        f"{_pz(ex['breakeven_ab_pct'])} Prozent im Plus, je nachdem was zuerst eintritt, rückt der Stop auf den "
        "Einstiegskurs. Aus dem Gewinner wird so kein Verlust mehr.",
        "Einstieg 50 Dollar, Stop 46 Dollar, also 4 Dollar Risk: Bei 55 Dollar, plus 10 Prozent, rückt der Stop auf "
        "50 Dollar.")
    neu("stops", "Teilverkauf",
        f"Stufe B der Ausstiegsregeln: Bei plus {tv} Prozent seit dem Einstieg wird {anteil} verkauft. Der Wächter "
        "meldet das im Handel, sobald der Kurs die Schwelle erreicht, und schickt dem Bot eine Verkaufszeile über "
        f"{anteil}. Solange die Halteregel läuft, ist der Teilverkauf ausgesetzt. Darvas-Positionen kennen keinen "
        "Teilverkauf; dort wandert nur der Stop mit jeder neuen, höheren Box.",
        "Einstieg 50 Dollar: Bei 60 Dollar wird die Hälfte verkauft.")
    neu("stops", "Nachzieh-Linie",
        f"Stufe C der Ausstiegsregeln: Nach dem Teilverkauf läuft der Rest über die {int(ex['trail_ma_schnell'])}-"
        f"Tage-Linie. Schließt der Kurs darunter, wird der Rest verkauft.",
        f"Nach dem Teilverkauf schließt die Aktie unter ihrer {int(ex['trail_ma_schnell'])}-Tage-Linie: Der Rest "
        "wird verkauft.")
    neu("stops", "Halteregel",
        f"Steigt eine Aktie binnen {int(ex['schnellstarter_tage'])} Handelstagen nach dem Einstieg um "
        f"{_pz(ex['schnellstarter_pct'])} Prozent, wird sie {int(ex['halteregel_tage'])} Handelstage ab dem "
        "Einstieg gehalten, rund acht Wochen, und der Teilverkauf ist so lange ausgesetzt. Solche Schnellstarter "
        "laufen oft weit.",
        "Einstieg 50 Dollar, nach acht Handelstagen 61 Dollar: Halteregel, die Aktie bleibt acht Wochen ganz im "
        "Depot.")
    neu("stops", "Round Trip",
        "Während der Halteregel darf ein dicker Gewinn nicht ganz verpuffen: Fällt eine Aktie, die schon "
        f"{_pz(ex['schnellstarter_pct'])} Prozent im Plus war, mit dem Schluss auf den Einstiegskurs zurück, wird "
        "alles verkauft.",
        "Einstieg 50 Dollar, Hoch bei 62 Dollar, Schluss wieder bei 50 Dollar: Round Trip, alles raus.")
    neu("stops", "Gewinnzonen",
        f"Wie weit eine gehaltene Aktie im Plus ist. Leicht: unter {_z(g['zone_leicht_max_r'])}R und unter plus "
        f"{_pz(g['zone_mittel_min_pct'])} Prozent. Mittel: ab {_z(g['zone_leicht_max_r'])}R, ab plus "
        f"{_pz(g['zone_mittel_min_pct'])} Prozent oder mit erreichtem Musterziel. Stark: ab "
        f"{_z(g['zone_stark_min_r'])}R oder mit einem Klimax-Zeichen. Steigt eine Position in eine höhere Zone, "
        "steht das im Reiter Berichte. Darvas-Positionen haben keine Zonen.",
        "Kaufpunkt 100 Dollar, Stop 95 Dollar, also 1R gleich 5 Dollar: Bei 108 Dollar ist die Zone leicht, bei 111 "
        "Dollar mittel, bei 116 Dollar stark.")
    neu("stops", "Zeitdeckel",
        "Wie lange eine Position höchstens läuft, je nach Art: Ein Tagesgeschäft endet mit dem Handelsschluss, eine "
        f"Zahlen-Lücke nach {int(g['zeitdeckel_tage_zahlen'])} Handelstagen, ein Insider-Kauf nach "
        f"{int(g['zeitdeckel_monate_insider'])} Monaten, alles andere nach {int(g['zeitdeckel_monate_standard'])} "
        "Monaten; Darvas-Positionen haben keinen Zeitdeckel. Ist er erreicht, steht im Reiter Berichte: Gewinn "
        "sichern oder These erneuern.",
        "Ein Insider-Kauf ist seit sechs Monaten im Depot: Zeitdeckel erreicht.")
    neu("stops", "Klimax",
        "Zeichen nach William O'Neil, dass ein Anstieg sich erschöpft. Das System kennt fünf: ein Klimaxlauf von "
        f"{_pz(g['klimax_pct_min'])} bis {_pz(g['klimax_pct_max'])} Prozent in höchstens {int(g['klimax_tage_max'])} "
        f"Handelstagen nach mindestens {int(g['klimax_vorlauf_wochen_min'])} Wochen Anstieg; der größte "
        "Tagesgewinn seit Beginn der Bewegung; eine Erschöpfungslücke von mindestens "
        f"{_pz(g['erschoepfungsluecke_min_pct'])} Prozent nach langem Lauf; ein Abstand von "
        f"{_pz(g['ma200_abstand_min'])} bis {_pz(g['ma200_abstand_max'])} Prozent über der 200-Tage-Linie; ein Kurs "
        f"mindestens {_pz(g['kanal_ueberschreitung_min_pct'])} Prozent über der oberen Kanallinie. Jedes Zeichen "
        "kommt je Aktie einmal als Bericht: Verkauf in die Stärke erwägen. Drei Zeichen prüft der Wächter mit dem "
        "ersten Kurs des Tages; der größte Tagesgewinn und die Erschöpfungslücke brauchen die fertige Tageskerze "
        f"und kommen um {_uhr(b['schlussnahe_minute'])} Uhr New Yorker Zeit.",
        "Eine gehaltene Aktie steht 90 Prozent über ihrer 200-Tage-Linie: Klimax-Zeichen Abstand zur "
        "200-Tage-Linie.")
    neu("stops", "Stufe 3 nach Weinstein",
        "Die Topbildung nach Stan Weinstein: Die 30-Wochen-Linie, die vorher klar stieg, wird flach. Danach droht "
        "Stufe 4, der Abwärtstrend. Für gehaltene Aktien in der starken Gewinnzone steht dann ein Bericht im Reiter "
        "Berichte; ein Verkaufssignal ist es nicht.",
        "Die 30-Wochen-Linie einer gehaltenen Aktie stieg monatelang und bewegt sich seit Wochen kaum noch: Stufe 3.")
    neu("stops", "Exit eines Tagesgeschäfts",
        "Red to Green, Red to Green Explosive und der Einstieg nach einem Power-Gap sind Tagesgeschäfte. Fällt der "
        "Kurs im Handel unter die Exit-Linie, bei Red to Green den Vortagesschluss, beim Power-Gap den Stop des "
        "Musters, kommt sofort das Verkaufssignal, und der Bot verkauft die ganze Position. Spätestens endet ein "
        "Tagesgeschäft mit dem Handelsschluss.",
        "Red to Green bei 41 Dollar, Vortagesschluss 40 Dollar: Fällt der Kurs auf 39,90 Dollar, kommt das "
        "Verkaufssignal.")
    neu("stops", "8-EMA-Hinweis",
        "Schließt eine gehaltene Aktie unter ihrer 8-Tage-Exponentiallinie, steht ein Hinweis im Reiter Berichte. Er "
        "ist kein Ausstiegssignal, nur eine Beobachtung.",
        "Eine gehaltene Aktie schließt bei 52 Dollar, ihre EMA 8 liegt bei 53 Dollar: 8-EMA-Hinweis.")
    neu("stops", "Zahlen voraus",
        "Bringt eine gehaltene Aktie in der mittleren oder starken Gewinnzone in den nächsten fünf Tagen "
        "Quartalszahlen, steht ein Hinweis im Reiter Berichte; Zahlen entscheiden über Nacht oft mehr als das "
        "Muster.",
        "Eine Aktie liegt 25 Prozent im Plus und berichtet übermorgen: Hinweis Zahlen voraus.")

    # ------------------------------------------------------ Meldungen und Berichte
    arten = [name for _k, name in berichte.ARTEN]
    neu("meldungen", "Kaufmeldung",
        "Die Meldung aufs Handy, wenn ein Kaufpunkt mit bestätigtem Volumen reißt, dazu je Kaufpunkt eine Kaufzeile "
        "an den Bot. Oben stehen Kürzel, Firma und Muster, darunter Kaufpunkt, Kurs und Volumen, dann Stop, Risk und "
        "Ziel, zuletzt die Lage zu den EMA-Linien, RS und Ratings. Reißen bei einer Aktie mehrere Kaufpunkte "
        "zugleich, stehen sie in einer Meldung mit Unternummern.",
        "Eine Aktie reißt ihr Rectangle Top: Kaufpunkt 50,01 Dollar, Kurs 50,30 Dollar, Volumen bestätigt; Stop 46 "
        "Dollar, Risk 8 Prozent.")
    neu("meldungen", "Regel 1, einmal am Tag",
        "Ein Kaufpunkt meldet am Tag genau einmal. Fällt die Aktie danach zurück und steigt wieder darüber, kommt "
        "keine zweite Meldung.",
        "Die Aktie eröffnet bei 70 Dollar, der Kaufpunkt 77 Dollar wird gerissen und gemeldet. Fällt sie auf 72,10 "
        "Dollar zurück und steigt wieder über 77 Dollar, kommt keine neue Meldung.")
    neu("meldungen", "Wochen-Sperre",
        "Je Aktie und Muster meldet ein Kaufpunkt höchstens einmal in der Woche, über alle Wege: Ausbruch und "
        "übersprungen sperren einander. Dasselbe Muster meldet erst wieder, wenn der neu gerechnete Kaufpunkt "
        f"mindestens {_pz(b['melde_neu_ab'])} Prozent über dem schon gemeldeten liegt; alles darunter gilt als "
        "Neuberechnung.",
        "Montag gemeldet bei 50 Dollar; am Mittwoch rechnet der Nachtscan denselben Kaufpunkt bei 50,40 Dollar: "
        "keine neue Meldung. Bei 51 Dollar meldet er wieder.")
    neu("meldungen", "Zahlen-Karenz",
        f"Bringt eine Firma {_karenz_satz(CFG['zahlen_karenz']['handelstage'])} Quartalszahlen, trägt ihre "
        "Kaufmeldung einen deutlichen Warnkopf als oberste Zeile. Gemeldet wird trotzdem; das Urteil bleibt beim "
        "Menschen. Red to Green und der Power-Gap am Lückentag tragen den Warnkopf nicht.",
        "Eine Aktie bricht um 16:00 Uhr Wiener Zeit aus und bringt am selben Abend Zahlen: Die Meldung beginnt mit "
        "dem Termin.")
    neu("meldungen", "Alarm-Muster",
        einstellungen.GRUPPEN_REGEL.get("alarm", "") + " Die sechs sind Three Weeks Tight, Inside Day, Pocket "
        "Pivot, IPO Base, Shakeout plus drei und Wick Play.",
        "Ein Inside Day nach drei steigenden Tagen reißt mit plus 75 Prozent Volumen: Kaufmeldung und Kaufzeile.")
    neu("meldungen", "Schlussbefund",
        f"Um {_uhr(b['schlussnahe_minute'])} Uhr New Yorker Zeit, eine Viertelstunde vor Schluss, rechnet der "
        "Wächter mit den Handelskursen alles, was nach den Regeln einen Schlusskurs braucht: die Ausstiege, das Ende "
        "der Tagesgeschäfte, den 8-EMA-Hinweis, zwei der Klimax-Zeichen und den Sektor-Radar. Die Befunde tragen "
        "den Vermerk Schluss noch offen und stehen je Art im Reiter Berichte; die Ausstiege gehen zugleich als "
        "Verkaufszeile an den Bot.",
        "Um 21:45 Uhr Wiener Zeit liegt eine gehaltene Aktie unter ihrem Stop: Bericht bei den Verkaufssignalen und "
        "Verkaufszeile an den Bot.")
    neu("meldungen", "Rücknahme",
        "Der Abendbericht prüft die schlussnahen Befunde mit dem echten Schluss nach. Gilt einer nicht mehr, steht "
        "dort eine Rücknahme.",
        "Um 15:45 Uhr meldet der Wächter ein Klimax-Zeichen; die Aktie fällt bis zum Schluss zurück, und der "
        "Abendbericht nimmt es zurück.")
    neu("meldungen", "Reiter Berichte",
        "Alle Berichte stehen nur in der App, nicht auf dem Handy: je Berichtsart ein Unterreiter, daneben die Zahl "
        "der ungelesenen. Jeder Bericht lässt sich von Hand auf gelesen setzen; was gelesen ist, merkt sich jedes "
        f"Gerät für sich. Geleert wird Montag bis Freitag um {berichte.LEERUNG_STUNDE}:00 Uhr Wiener Zeit; der Stand "
        "vom Vortag und vom Wochenende bleibt bis dahin lesbar. Auf dem Handy bleiben die Kaufmeldungen samt "
        "übersprungen, Red to Green, der Power-Gap am Lückentag und Störungen. Die Unterreiter: "
        + ", ".join(arten) + ".",
        f"Der Abendbericht der Nacht steht morgens im Unterreiter Abendbericht, bis er um {berichte.LEERUNG_STUNDE}:00 "
        "Uhr geleert wird.")
    neu("meldungen", "Verkaufssignale",
        "Der Unterreiter für die Ausstiege: Stop gerissen, Round Trip, Nachzieh-Linie unterschritten, Teilverkauf "
        "und das Ende oder der Exit eines Tagesgeschäfts. Jede dieser Meldungen geht zugleich als Verkaufszeile an "
        "den Handels-Bot.",
        "Eine gehaltene Aktie schließt unter ihrem Stop: Bericht Stop gerissen, ganz raus, und eine Verkaufszeile an "
        "den Bot.")
    neu("meldungen", "Gap-Up-Bericht",
        "Jeden Handelstag 20 Minuten vor der US-Eröffnung, meist um 15:10 Uhr Wiener Zeit: alle Aktien des ganzen "
        f"Markts mit einer vorbörslichen Lücke ab {_z(gapup_bericht.GAP_MIN_PCT, 0)} Prozent, vorbörslichem Volumen "
        f"von mindestens minus {_z(100 - gapup_bericht.VOL_MIN_ANTEIL * 100, 0)} Prozent über dem 50-Tage-Schnitt, "
        "Kurs ab "
        f"{_z(gapup_bericht.KURS_MIN, 0)} Dollar und Börsenwert ab "
        f"{_z(gapup_bericht.MARKTKAP_MIN_MRD * 1000, 0)} Millionen Dollar, sortiert nach vorbörslichem Dollarvolumen. "
        "Je Aktie stehen Kurs, Lücke, Volumen, Wachstum, RS, Abstand zum Hoch, Sektor, Wochenlisten, Zahlentermin "
        "und Schlagzeilen dabei. Reine Auskunft, kein Alarm, keine Kaufzeile.",
        "Eine Aktie steht vorbörslich 17 Prozent höher, nach Quartalszahlen, mit 2,6 Millionen Stück: Sie steht "
        "oben im Bericht.")
    neu("meldungen", "Abendbericht",
        "Der Bericht nach dem Nachtscan: Rücknahmen der schlussnahen Befunde, Marktampel samt Distribution Days und "
        "Marktbreite, Aktien im Plus an einem roten Nasdaq-Tag, neue Hochs in drei Stufen, RS ab "
        f"{int(ab['rs_bericht_ab'])} und neue Hochs der RS-Linie bei den Aktien der Wochenlisten. Er ordnet den Tag "
        "ein und ist kein Alarm.",
        "Der Abendbericht nennt, dass ein Klimax-Zeichen von 15:45 Uhr mit dem Schluss zurückgenommen ist.")
    neu("meldungen", "Amtliche Zahlen",
        "Die Vorabwerte aus den Pressemitteilungen zu Quartalszahlen, von einem Sprachmodell gelesen und als "
        "vorläufig gekennzeichnet, werden mit den amtlichen Zahlen des Quartalsberichts bei der SEC abgeglichen, "
        "sobald er vorliegt. Weicht ein Wert ab, steht das im Unterreiter Amtliche Zahlen.",
        "Die Pressemitteilung nannte 1,20 Dollar Gewinn je Aktie, der Quartalsbericht 1,18 Dollar: Die Abweichung "
        "steht im Bericht.")
    neu("meldungen", "Power-Gap-Einstieg übersprungen",
        "Beim Power-Gap wird am Handelstag nach der Lücke gekauft, solange der Kurs höchstens 3 Prozent über dem "
        "Kaufpunkt steht. Liegt er weiter darüber, ist der Einstieg übersprungen; das steht im Reiter Berichte.",
        "Kaufpunkt 46 Dollar, am Folgetag eröffnet die Aktie bei 48 Dollar, 4,3 Prozent darüber: Einstieg "
        "übersprungen.")
    neu("meldungen", "Weitere Auskünfte",
        "Der Unterreiter für Befunde, die keiner anderen Berichtsart angehören.",
        "Ein Befund ohne eigene Art landet hier statt in einem falschen Unterreiter.")

    # ------------------------------------- Chartmuster bei den Treffern des Scanners
    gr = "Chartmuster bei den Treffern des Scanners"
    neu("muster", "Power Trend",
        f"Ein starker Aufwärtstrend: Seit mindestens {int(q['f_tage_ueber_ema'])} Handelstagen liegt jedes Tagestief "
        f"über der EMA 21, die EMA 21 liegt über der SMA 50, und die SMA 50 steigt seit mindestens "
        f"{int(q['f_sma50_steigt'])} Tagen. Er endet, sobald die EMA 21 unter die SMA 50 fällt oder der Schluss "
        "unter der SMA 50 liegt. Eine Auskunft bei den Treffern, ohne Kaufpunkt und ohne Alarm.",
        "Seit zwölf Handelstagen liegt jedes Tagestief über der EMA 21, und die SMA 50 steigt seit einem Monat: Power "
        "Trend.", gr)
    neu("muster", "Flat Base",
        f"Eine flache Basis aus mindestens {int(q['g_wochen_min'])} abgeschlossenen Wochen, höchstens "
        f"{_pz(q['g_tiefe_max'])} Prozent tief, nach einem Anstieg von mindestens {_pz(q['g_anstieg_min'])} Prozent. "
        f"Kaufpunkt am Basishoch plus {_z(q['aufschlag'] * 100, 0)} Cent, Stop am Basistief.",
        "Nach einem Anstieg von 40 auf 60 Dollar pendelt die Aktie sieben Wochen zwischen 53 und 60 Dollar: Flat Base "
        "mit 12 Prozent Tiefe, Kaufpunkt 60,10 Dollar.", gr)
    neu("muster", "Shakeout am EMA 10",
        "Im Aufwärtstrend, Kurs über SMA 50 und SMA 50 über SMA 200, fällt die Aktie kurz unter ihre EMA 10 und "
        f"schließt wieder darüber, am selben Tag oder am Tag danach; höchstens {_pz(f['t_unterschreitung_max'])} "
        "Prozent darunter. Schwache Hände sind ausgeschüttelt. Eine Auskunft bei den Treffern.",
        "Die EMA 10 liegt bei 50 Dollar, das Tagestief bei 49,20 Dollar, der Schluss bei 51 Dollar.", gr)
    neu("muster", "Base-on-Base",
        "Eine Basis, die direkt auf einer anderen sitzt, weil die Aktie aus der ersten ausbrach, aber bis zum "
        f"linken Hoch der neuen weniger als {_pz(q['k_gewinn_min'])} Prozent gewann. Beide zählen in der "
        "Stufenzählung als eine Stufe; Einstieg über dem Hoch der oberen Basis.",
        "Ausbruch aus einer Basis bei 50 Dollar, nur bis 54 Dollar gestiegen, dann eine neue Basis zwischen 48 und 54 "
        "Dollar: Base-on-Base.", gr)
    neu("muster", "Stufenzählung der Basen",
        "Die wievielte Basis seit dem letzten Markttief oder der letzten eigenen Korrektur es ist, nur für Aktien "
        f"über {_z(q['m_kurs_min'], 0)} Dollar. Eine Basis dauert mindestens {int(q['m_wochen_min'])} Wochen und ist "
        f"höchstens {_pz(q['m_tiefe_max'])} Prozent tief; jede weitere zählt eine Stufe höher, wenn die Aktie aus "
        f"der vorigen ausgebrochen ist und mindestens {_pz(q['k_gewinn_min'])} Prozent gewonnen hat. Ab Stufe 3 "
        "heißt die Basis spät, ab Stufe 4 sehr spät.",
        "Nach dem Markttief im Frühjahr ist das die dritte Basis der Aktie: späte Basis.", gr)
    neu("muster", "Green Line Breakout",
        f"Die grüne Linie ist ein Allzeithoch, das mindestens {int(q['q_tage_ohne_hoch'])} Handelstage ohne neues "
        "Hoch stand. Das Signal ist ein Monatsschluss darüber, bei deutlich höherem Volumen als davor; gezeigt wird "
        "es nach dem bestätigten Monatsschluss den ganzen Folgemonat.",
        "Das Allzeithoch von 120 Dollar hielt zwei Jahre; der September schließt bei 124 Dollar: Green Line "
        "Breakout.", gr)
    neu("muster", "Episodic Pivot",
        f"Eine Eröffnungslücke von mehr als {_pz(q['v_luecke'])} Prozent mit einem Volumen von mindestens "
        f"{vz((q['v_vol_faktor'] - 1) * 100)} Prozent über dem {int(q['v_vol_tage'])}-Tage-Schnitt, nachdem die "
        "Aktie mindestens zwei Monate kaum gestiegen war und mindestens "
        f"{_pz(q['v_abstand_200'])} Prozent unter ihrem {int(q['v_hoch_tage'])}-Tage-Hoch lag. Auslöser sind Zahlen; "
        "eine Lücke ohne erkannten Auslöser steht getrennt da. Einstieg über dem Eröffnungsbereich des Lückentags.",
        "Eine Aktie liegt drei Monate bei 20 Dollar, 30 Prozent unter ihrem Hoch, und eröffnet nach Zahlen bei 26 "
        "Dollar mit dem Fünffachen des üblichen Volumens.", gr)
    neu("muster", "Neues 52-Wochen-Hoch",
        "Das Tageshoch des letzten Handelstags liegt über allen Hochs der 52 Wochen davor. Im Scanner ist es ein "
        "Chart-Signal und ein Merkmal im Block Abstand von Hoch und Tief.",
        "Das bisherige 52-Wochen-Hoch lag bei 80 Dollar, heute erreicht die Aktie 81 Dollar: neues 52-Wochen-Hoch.", gr)
    neu("muster", "Neues Allzeithoch",
        "Am letzten Handelstag wurde das Hoch der ganzen Kurshistorie erreicht.",
        "Eine Aktie stand vor drei Jahren bei 150 Dollar, heute erreicht sie 151 Dollar: neues Allzeithoch.", gr)
    return e
