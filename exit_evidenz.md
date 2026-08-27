# Exit-Evidenz und zwei Vorschläge zur automatischen Exit-Überwachung

Für Gerhard und Mathias, 27.08.2026. Auftrag (Gerhard): Evidenz für
Verkaufssignale in allen Strategien, die online sind, aus Fachliteratur
und Studienlage, gezielt nur zu unseren Strategien; dazu zwei
konzeptuelle Vorschläge, wie eine Kaufpunkt-Triggermeldung zusätzlich
zum Push an die jeweilige Exit-Strategie übergeben wird, sodass der
Exit ab dem Trigger laut Chart überwacht wird.

Arbeitsweise: Zuerst wurde der Bestand gelesen (Kapitel 11,
exit_regeln.py, positionen.py, Gerhards Exit-Regelwerk vom 05.08.2026),
dann je Strategie die Quelle der Strategie selbst und die Studienlage.
Messzahlen von Bulkowski wurden am 27.08.2026 direkt von seiner Seite
thepatternsite.com abgerufen, die zwei tragenden Studien (Kaminski und
Lo; Jeng, Metrick und Zeckhauser) wurden am selben Tag gegen die
Originalveröffentlichungen verifiziert. Wo eine Zahl nur aus dem
Gedächtnis der Bücher stammt, steht das ausdrücklich dabei.

## Teil 1: Was schon existiert, und wo die Lücke ist

Kapitel 11 (exit_regeln.py, von Gerhard am 05.08.2026 festgelegt) regelt
bereits systemweit: Stop am strukturellen Bruchpunkt mit
Zehn-Prozent-Deckel, Bruch nur per Schlusskurs, Stop wandert nur nach
oben, Stufe A Einstandsstop, Stufe B Teilverkauf bei 20 Prozent, Stufe C
Trailing über MA21 oder MA50, Acht-Wochen-Halteregel für Schnellstarter,
Round-Trip-Verbot. Die Tabelle STRUKTURPUNKT nennt je Muster den
Bruchpunkt. positionen.py führt offene Positionen und kennt zwei
Betriebsarten, ECHT und BEOBACHTUNG; die Beobachtungs-Betriebsart hat
Gerhard selbst vorgeschlagen (05.08.2026): eine Position wird nur
angenommen, damit sich Erfahrung sammelt, ohne dass Geld fließt.

Die Lücke, die der neue Auftrag benennt, ist zweifach. Erstens füttert
NICHTS die Exit-Überwachung automatisch: Ein gemeldeter Kaufpunkt
verhallt, solange niemand von Hand eine Position einträgt; die
Positionsverwaltung steht seit dem 05.08. bei null Einträgen. Zweitens
ist Kapitel 11 ein Einheitsregelwerk: Die musterspezifischen
Verkaufssignale der Quellen (Boxboden-Nachziehen bei Darvas,
Klimax-Zeichen bei O'Neil, Verkauf in die Stärke bei Minervini,
Measure-Rule-Ziele bei Bulkowski, der Sechs-Monats-Horizont der
Insider-Studien) sind darin nicht enthalten, und der Strukturpunkt
steht nur als Text, er wird nicht laufend am Chart nachgeführt.

Online sind derzeit: Darvas Box, Cup and Handle (Wochenbasis),
Rectangle Top, VCP, High and Tight Flag, Lücken-Bestätigungstag,
Red-to-Green und Red-to-Green Explosive, Shakeout-Spring (Kapitel 10),
die Ausweich-Marken (52-Wochen-Hoch, 20-Tage-Hoch, MA50), der
Insider-Kauf-Scanner und der Sektor-Radar (letzterer meldet Lagen,
keine Einstiege, und braucht deshalb keinen Exit).

## Teil 2: Evidenz je Strategie

Je Strategie: was die Quelle selbst zum Verkauf sagt, was die
Studienlage hergibt, und die daraus abgeleitete Regel. Evidenzgrad A
heißt durch unabhängige Messung oder Studie gestützt, B heißt
Primärquelle mit interner Statistik, C heißt Praktiker-Überlieferung
ohne belastbare Messung.

### Darvas Box

Quelle: Nicolas Darvas, How I Made 2,000,000 Dollars in the Stock
Market, 1960. Die Methode IST im Kern eine Exit-Methode: Darvas zog
den Stop mit jedem neuen, höheren Boxboden nach und verkaufte
ausschließlich, wenn der Kurs aus dem Boden der aktuellen Box fiel.
Kein Gewinnziel, kein Verkauf in Stärke; der nachgezogene Boxboden ist
der historische Urahn des Trailing-Stops. Kapitel 11 nennt genau das
als Bruchpunkt, verdrahtet ist das Nachziehen aber nicht.

Studienlage: Kaminski und Lo, When Do Stop-Loss Rules Stop Losses?,
Journal of Financial Markets 18 (2014), Seiten 234 bis 254, verifiziert
27.08.2026: Unter reiner Zufallsbewegung senken Stop-Regeln die
erwartete Rendite, unter Momentum (Trendfolge) fügen sie Wert hinzu,
gemessen 50 bis 100 Basispunkte je Monat während der
Stop-out-Phasen (Daten 1950 bis 2004). Unser gesamtes System ist ein
Momentum-System; die Studie ist damit die akademische Rückendeckung
für Trailing-Stops überhaupt.

Abgeleitete Regel (Evidenzgrad A für den Stop-Ansatz, B für die
Boxmechanik): Nach dem Trigger täglich am Tagesschluss die aktuelle Box
nachführen; Exit-Meldung, wenn ein Schlusskurs unter dem gültigen
Boxboden liegt; Stop-Nachzug-Meldung bei jeder neuen, höheren Box.

### Cup and Handle (Wochenbasis)

Quelle: William O'Neil, How to Make Money in Stocks (4. Auflage).
O'Neils Verkaufsregeln, aus dem Buch (Gedächtniswiedergabe, im Buch
verstreut über die Verkaufskapitel): Verluste hart bei 7 bis 8 Prozent
unter dem Kaufpunkt kappen; die meisten Gewinne bei 20 bis 25 Prozent
mitnehmen, AUSSER die Aktie stieg 20 Prozent in unter drei Wochen, dann
acht Wochen halten (beides ist in Kapitel 11 bereits eingebaut);
Klimax-Erkennung nach längerem Anstieg: größter Tagesgewinn seit Beginn
der Bewegung, Erschöpfungslücke, Überschreiten der oberen Kanallinie,
neue Hochs bei auffallend dünnem Volumen; als spätes Signal der
Schlusskurs unter der Zehn-Wochen-Linie bei hohem Volumen.

Messung: Bulkowski (thepatternsite.com/cup.html, abgerufen 27.08.2026,
913 vermessene Fälle): durchschnittlicher Anstieg 54 Prozent,
Break-even-Fehlerrate 5 Prozent, Throwback-Rate 62 Prozent,
Kurszielquote der Measure Rule 61 Prozent, Gesamtrang 3 von 39.
Bulkowskis eigene Stop-Empfehlung dort: Stop unter das Handle-Tief,
mit steigendem Kurs nachziehen; deckt sich mit Kapitel 11.

Abgeleitete Regel (Evidenzgrad B, Teilaspekte A): Kapitel 11
unverändert als Grundgerüst; ZUSÄTZLICH die Klimax-Zeichen als
Verkaufs-in-Stärke-Meldung (größter Tagesgewinn seit Trigger plus
Volumen über dem Schnitt nach mindestens 25 Prozent Anstieg) und die
Zehn-Wochen-Linie als spätes Exit-Signal. Die hohe Throwback-Rate (62
Prozent) begründet außerdem eine eigene Fehlsignal-Regel: Fällt der
Kurs nach dem Ausbruch per Schluss zurück UNTER den Kaufpunkt, ist der
Ausbruch gescheitert, noch bevor der Strukturstop erreicht ist.

### Rectangle Top

Quelle und Messung: Bulkowski, Encyclopedia of Chart Patterns;
aktuelle Zahlen von thepatternsite.com/recttops.html (27.08.2026):
durchschnittlicher Anstieg 51 Prozent, Break-even-Fehlerrate 15
Prozent, Throwback-Rate 66 Prozent, Zielquote der Measure Rule
(Rechteckhöhe auf die Oberkante addiert) 78 Prozent, Rang 4 von 39.

Abgeleitete Regel (Evidenzgrad B mit gemessenen Quoten): Erstens die
Fehlsignal-Regel: Ein Schlusskurs zurück IM Rechteck (unter der alten
Oberkante) widerlegt den Ausbruch; das ist präziser als der
Kapitel-11-Bruchpunkt Unterkante der Range, der erst viel tiefer
greift, und bei 66 Prozent Throwbacks die wichtigste Einzelregel.
Zweitens das Measure-Rule-Ziel als Straffungspunkt: Bei Erreichen von
Oberkante plus Rechteckhöhe (Trefferquote 78 Prozent) den Stop deutlich
enger ziehen oder Teilverkauf melden, denn ab dort ist der statistische
Erwartungswert des Musters verbraucht.

### VCP (Volatility Contraction Pattern)

Quelle: Mark Minervini, Trade Like a Stock Market Wizard (2012) und
Think and Trade Like a Champion (2017), Gedächtniswiedergabe der
Verkaufskapitel: Anfangsstop nie über 10 Prozent, im Schnitt deutlich
enger; nach einem Gewinn im Mehrfachen des Einstiegsrisikos den Stop
auf Einstand ziehen (nie einen ordentlichen Gewinn in einen Verlust
drehen lassen); in die Stärke hinein teilverkaufen, wenn der Gewinn ein
Vielfaches des durchschnittlichen Verlusts erreicht; Verstoß ist der
Schlusskurs unter der 50-Tage-Linie bei erhöhtem Volumen. Minervinis
eigener Leistungsnachweis (US Investing Championship 1997 und 2021)
ist dokumentiert, aber kein unabhängiger Beleg der Einzelregeln.

Abgeleitete Regel (Evidenzgrad B): Kapitel 11 deckt Stop, Einstand und
Teilverkauf bereits ab; ZUSÄTZLICH die 50-Tage-Linie als
strategie-eigenes Exit-Signal (Schluss darunter mit Volumen über dem
Schnitt) und die R-Rechnung, die Kapitel 11 schon führt, als Auslöser
für den Einstandsstop (ab 2R), nicht erst die Prozentschwelle.

### High and Tight Flag

Quelle: O'Neil (Fahnenmast 100 bis 120 Prozent in vier bis acht
Wochen, Flagge 10 bis 25 Prozent Korrektur); Messung Bulkowski
(thepatternsite.com/htf.html, 27.08.2026, 1028 Fälle):
durchschnittlicher Anstieg nach Ausbruch 39 Prozent,
Break-even-Fehlerrate 15 Prozent, Throwback 67 Prozent, Halbhöhen-Ziel
mit 82 Prozent Trefferquote, Gesamtrang 30 von 39. Ehrlich benannt:
Bulkowskis Messung stuft das Muster deutlich nüchterner ein als der
O'Neil-Ruf; die Fehlerrate ist dreimal so hoch wie beim Cup and
Handle. Bulkowskis Exit-Hinweis dort: bei steilen Anstiegen
Volatilitäts-Stop und Trendlinie unter den Kurs, Verkauf erwägen beim
Schluss darunter.

Abgeleitete Regel (Evidenzgrad B mit gemessenen Quoten): Stop unter dem
Flaggentief (Kapitel 11, bestätigt); Halbhöhen-Ziel (halber Fahnenmast
auf den Ausbruch addiert) als Straffungspunkt mit der besten
gemessenen Trefferquote im ganzen System (82 Prozent); wegen der hohen
Fehlerrate zusätzlich die Fehlsignal-Regel Schluss zurück unter den
Kaufpunkt. Die tägliche Melde-Ausnahme der Flagge (HTF-Marke) bleibt
davon unberührt, sie betrifft nur den Einstieg.

### Lücken-Bestätigungstag

Quellenlage: Zu Kurslücken selbst führt Bulkowski Statistiken (Lücken
in Trendrichtung mit Bestätigung laufen weiter, gewöhnliche Lücken
schließen schnell; Zahlen hier aus dem Gedächtnis, vor Einbau
gegenprüfen). Die stärkste Evidenz kommt aus einer anderen Ecke, und
sie ist für uns unmittelbar nutzbar: der Post-Earnings-Announcement
Drift (Ball und Brown 1968; Bernard und Thomas 1989, Journal of
Accounting Research): Nach Ergebnisüberraschungen driften Kurse über
Wochen in Richtung der Überraschung weiter; einer der ältesten und
meistbestätigten Kapitalmarkteffekte überhaupt.

Abgeleitete Regel (Evidenzgrad A für den Zahlen-Fall, C für den Rest):
Die Lücken-These ist widerlegt, wenn die Lücke per Schlusskurs
geschlossen wird; das ist der natürliche Bruchpunkt und ersetzt bei
diesem Muster jede Prozentmarke innerhalb des Deckels. INNOVATION aus
dem Bestand: zahlen_termine.json weiß bereits, ob die Lücke ein
Zahlen-Termin war. War sie es, spricht die Drift-Evidenz gegen einen
schnellen Gewinn-Exit und für den weiten Anker (Lückenschluss oder
Kapitel-11-Trail); war sie es nicht, gilt das engere Regime mit
Straffung nach wenigen Tagen.

### Red-to-Green und Red-to-Green Explosive

Quellenlage: Tageshandels-Überlieferung (unter anderem Andrew Aziz, How
to Day Trade for a Living; Ross Cameron), keine belastbare
unabhängige Messung bekannt; Evidenzgrad C, und das gehört ehrlich
gesagt. Kapitel 11 hat den Bruchpunkt bereits sauber definiert:
Schlusskurs zurück unter dem Vortagesschluss, die Triggerlinie ist
zugleich die Exit-Linie. Die Überlieferung ergänzt: Signale dieser Art
sind Tagesgeschäft, die Position wird nicht über Nacht gehalten,
sofern nicht ein übergeordnetes Muster dieselbe Aktie trägt.

Abgeleitete Regel (Evidenzgrad C, aber symmetrisch und prüfbar):
Intraday-Exit-Meldung, wenn der Kurs zurück unter den Vortagesschluss
fällt (dieselbe Datenrunde, die den Trigger fand, sieht auch den
Rückfall); Zeit-Exit-Hinweis zum Handelsschluss mit dem Stand seit
Trigger. Für Explosive zusätzlich das Tagestief des Auslösetags als
harte Linie.

### Shakeout-Spring mit Sekundärtest (Kapitel 10)

Quelle: Richard Wyckoff (Kursmethode), aufbereitet bei Pruden (The
Three Skills of Top Trading, 2007) und Weis (Trades About to Happen,
2013). Der Stop unter dem Spring-Tief steht bereits in Kapitel 10 und
in der STRUKTURPUNKT-Tabelle. Wyckoffs Ausstiegslehre: Ziel aus der
Höhe der Handelsspanne (Cause-Effect-Projektion), Warnzeichen sind
Upthrust (Fehlausbruch nach oben), Schwächezeichen mit weitem Spread
und hohem Volumen ohne Fortschritt, und der Kaufklimax. Unabhängige
akademische Validierung der Wyckoff-Signale existiert praktisch nicht;
Evidenzgrad C, in sich aber konsistent und regelbar.

Abgeleitete Regel: Exit-Meldung bei Schluss unter dem Tief des
Sekundärtests (näher als das Spring-Tief, sobald der Test bestätigt
ist); Zielmarke Oberkante der Handelsspanne plus Spannenhöhe als
Straffungspunkt; Warnmeldung bei Fehlausbruch über die Spanne mit
Schluss zurück darin (Upthrust).

### Insider-Kauf-Scanner

Studienlage, die stärkste akademische im ganzen System: Jeng, Metrick
und Zeckhauser, Estimating the Returns to Insider Trading, Review of
Economics and Statistics 85 (2003), verifiziert 27.08.2026:
Insider-KÄUFE erzielen abnormale Renditen von 52 bis 68 Basispunkten
je Monat über die ersten sechs Monate, rund die Hälfte davon im ersten
Monat; Insider-VERKÄUFE erzielen keine messbare abnormale Rendite.
Dazu Lakonishok und Lee (Review of Financial Studies 2001, Käufe
informativ, besonders bei kleinen Firmen) und Cohen, Malloy und
Pomorski (Decoding Inside Information, Journal of Finance 2012:
opportunistische, nicht routinemäßige Käufe tragen das Signal).

Abgeleitete Regel (Evidenzgrad A): Erstens NICHT auf Insider-Verkäufe
als Ausstiegssignal warten, die tragen laut Studienlage keine
Information (Vergütung, Streuung); ein Verkaufs-Scanner wäre
Fehlaufwand. Zweitens der Zeithorizont: Die Überrendite ist in den
ersten Wochen am dichtesten und nach etwa sechs Monaten verbraucht;
der Exit ist deshalb eine Zeitregel (Straffung nach vier Wochen,
Horizont-Ende nach sechs Monaten) PLUS der gewöhnliche
Kapitel-11-Chartstop, denn ein Insider-Signal hat keinen eigenen
Strukturpunkt.

### Ausweich-Marken (52-Wochen-Hoch, 20-Tage-Hoch, MA50)

Studienlage: George und Hwang, The 52-Week High and Momentum
Investing, Journal of Finance 2004: Die Nähe zum 52-Wochen-Hoch
erklärt Momentum-Renditen besser als klassische Rankings, und die
Gewinne kehren langfristig nicht um; das stützt sowohl die Marke als
Einstieg als auch den Verbleib, solange neue Hochs entstehen. Zu
MA-Regeln: Brock, Lakonishok und LeBaron (Journal of Finance 1992)
fanden Prognosekraft einfacher MA-Regeln in Daten bis 1987, spätere
Replikationen relativieren; Han, Yang und Zhou (JFQA 2013) zeigen
Nutzen von MA-Timing in volatilen Portfolios. Gemischt, aber real;
Evidenzgrad B.

Abgeleitete Regel: Für die Hoch-Marken gilt das Rectangle-Prinzip
sinngemäß: Schluss zurück unter der gerissenen Marke widerlegt den
Durchbruch. Für die MA50-Rückeroberung ist der Exit der Schluss zurück
unter die Linie. Ein eigenes Gewinnregime brauchen die Marken nicht,
Kapitel 11 trägt.

### Übergreifend: warum automatische Exit-Meldungen überhaupt

Die am besten belegte Erkenntnis der gesamten Exit-Forschung ist
verhaltensökonomisch: Anleger verkaufen Gewinner zu früh und halten
Verlierer zu lange (Dispositionseffekt; Shefrin und Statman, Journal
of Finance 1985; Odean, Are Investors Reluctant to Realize Their
Losses?, Journal of Finance 1998, an 10.000 Depots gemessen). Ein
System, das den Exit ab dem Trigger regelbasiert überwacht und
ansagt, bekämpft exakt diesen Fehler; zusammen mit Kaminski und Lo
(Stops nützen in Momentum-Umgebungen) ist das die Evidenz dafür, dass
der Auftrag selbst richtig angesetzt ist.

## Teil 3: Vorschlag A, das Schattenbuch

Grundidee: Jede Kaufpunkt-Triggermeldung eröffnet im selben Atemzug
eine BEOBACHTUNGS-Position in der bestehenden Positionsverwaltung;
genau die Betriebsart, die Gerhard am 05.08. vorgesehen hat und die
seither leer steht. Der Push bleibt unverändert, die Übergabe ist ein
zweiter, interner Empfänger derselben Meldung.

Mechanik: Der Wächter schreibt beim erfolgreichen Push je Signal einen
Schattenbuch-Eintrag mit Ticker, Strategie, Triggerkurs, Triggerzeit,
Strukturpunkt (aus der Mappe, wie er in der Meldung steht) und dem
gedeckelten Anfangsstop aus Kapitel 11. Ab dann prüft die Tagwache
intraday die Intraday-Regeln (Red-to-Green-Rückfall, Lückenschluss)
und der Nachtscan am Tagesschluss die Schlusskurs-Regeln (Kapitel 11
komplett plus die strategie-eigenen Zusätze aus Teil 2:
Boxboden-Nachzug, Klimax-Zeichen, Measure-Rule-Straffung,
50-Tage-Verstoß, Sechs-Monats-Horizont der Insider). Jede ausgelöste
Regel wird über das bestehende ntfy-Thema gemeldet, im gewohnten
Format, etwa: EXIT-Hinweis: JAZZ; Darvas Box; Schluss 241.10 unter
Boxboden 243.80; seit Trigger plus 12,4 Prozent. Stop-Nachzüge und
Straffungspunkte melden leiser (Priorität default), Brüche laut.

Zustand: eigene Datei schattenbuch.json nach dem Muster der
Shakeout-Warteliste; sie überlebt den Freitagsputz ausdrücklich (die
Lehre der Insider-30-Tage-Frist: Exit-Zustand ist kein
Melde-Gedächtnis). Intraday-Strategien schließen ihre Beobachtung
automatisch zum Handelsschluss, alle anderen enden durch Exit-Signal
oder Zeitdeckel (Vorschlag: 26 Wochen, der Insider-Horizont als
längster).

Der eigentliche Gewinn, und deshalb ist A mein Favorit: Das
Schattenbuch schreibt automatisch mit, was aus jedem Trigger geworden
ist (Triggerkurs, Exit-Kurs, Exit-Grund, Haltedauer, R-Vielfaches).
Gerhard schreibt in jedem Regelwerk, die Schwellen seien Startwerte
und per Mitschreiben zu verfeinern; das Schattenbuch IST dieses
Mitschreiben, ohne dass jemand etwas eintragen muss. Nach drei Monaten
liegen erstmals echte Trefferquoten je Strategie und je Exit-Regel
vor, gemessen an unseren eigenen Signalen statt an Bulkowskis
Universum.

Aufwand und Risiken: mittel; neue Datei, Fütterung an einer Stelle im
Wächter, Prüfschleife je Lauf über die offenen Beobachtungen (ein
Kursabruf je Beobachtung ist NICHT nötig, die Tagwache streamt die
Listen-Aktien ohnehin; nur Beobachtungen zu Aktien, die von der
Wochenliste gefallen sind, brauchen eine eigene kleine Abrufrunde,
dieselbe Mechanik wie beim Insider-Marktwert). Meldelast: bei zuletzt
rund 20 bis 40 Triggern je Woche entsteht ein Bestand von grob 50 bis
150 offenen Beobachtungen; Exit-Meldungen in ähnlicher Wochenzahl wie
heute die Einstiege, gebündelt je Lauf wie gewohnt.

## Teil 4: Vorschlag B, die Exit-Grammatik im Wächter

Grundidee: kein neues Buch, kein neues Kapitel; der Exit wird ein
dritter Zustand der Maschinerie, die es schon gibt. Das
Melde-Gedächtnis kennt je Signalschlüssel heute gemeldet oder nicht;
es bekommt zusätzlich Schlüssel mit der Marke EXIT| samt eigener
Frist (die Mechanik existiert, INSIDER| mit 30 Tagen zeigt den Weg).
Nach einem Push wird der Schlüssel scharf, und die bestehende
Fenster-Zustandsmaschine des Wächters prüft ihn fortan rückwärts.

Die Regeln kommen aus einer GRAMMATIK von sechs Bausteinen, die alle
recherchierten Regeln abdecken: erstens Anfangsstop gleich
Strukturpunkt mit Deckel (existiert); zweitens Nachziehanker, wählbar
Boxboden, Vortagestief, MA50 oder 20-Tage-Tief; drittens
Fehlsignal-Linie (Schluss zurück unter Kaufpunkt beziehungsweise
zurück in der Range oder unter der Marke); viertens Straffungsziel
(Measure Rule, Halbhöhe, Spannenprojektion); fünftens Klimax-Warnung
(größter Tagesgewinn seit Trigger plus Volumen); sechstens Zeit- und
Ereignisregel (Handelsschluss für Intraday, sechs Monate für Insider,
Zahlen-Termin-Hinweis aus zahlen_termine.json). Jede Strategie ist
dann nur noch ein Konfigurationsblock in config.py, der Bausteine
auswählt und parametriert; ein einziger Prüfmotor läuft im Wächter,
und die Gesamtprüfung kann jede Strategie mal jeden Baustein als
Matrix absichern.

Stärken: minimal-invasiv, keine neue Zustandsdatei außer den
EXIT|-Schlüsseln samt Ankerständen im vorhandenen Gedächtnis, ein
Motor statt je Strategie einem Modul, sehr gut prüfbar. Schwächen und
sie sind der Preis der Schlankheit: keine Mitschrift der Ergebnisse
(was aus einem Trigger wurde, weiß hinterher niemand; genau das
Verfeinerungs-Material fehlt dann wieder), das Melde-Gedächtnis
bekommt eine zweite Natur als Zustandsspeicher und muss sorgfältig vom
Freitagsputz abgeschirmt werden, und Tagesschluss-Regeln laufen im
Wächter zeitlich unbequem (die Schlussstunde endet mit der Glocke; die
saubere Schlusskurs-Prüfung gehört in den Nachtscan, womit auch B
zwei Bauplätze braucht).

## Teil 5: Vergleich, Empfehlung, offene Fragen

Beide Vorschläge teilen dieselbe recherchierte Regelbasis aus Teil 2
und dasselbe Meldeformat; sie unterscheiden sich darin, WO der Zustand
lebt und OB mitgeschrieben wird. B ist der schlankere Erstschritt, A
ist das vollständigere Zielbild. Meine Empfehlung ist A, aus drei
Gründen: Die Beobachtungs-Betriebsart existiert bereits und wartet
seit dem 05.08. genau auf diese Fütterung; die automatische Mitschrift
löst Gerhards eigenes Prinzip vom Verfeinern per Messung ein, das
bisher an der Handarbeit scheitert; und die Erfahrung dieser Woche
(Shakeout-Warteliste, Insider-Fenster) zeigt, dass langlebiger Zustand
eine EIGENE Datei mit eigenen Fristen verdient, nicht einen Untermieter
im Melde-Gedächtnis. Ein gangbarer Mittelweg: den Grammatik-Motor aus B
als Herzstück in A einbauen, dann ist die Regelauswertung ein
prüfbarer Block und das Schattenbuch nur die dünne Schicht darum.

Offene Fragen an Gerhard, vor dem Bau zu entscheiden: erstens, ob
JEDER gemeldete Trigger beobachtet wird oder nur bestätigte (mit
Volumen); zweitens, ob Stop-Nachzüge und Straffungen gemeldet werden
oder nur echte Exits (Meldelast); drittens die Zeitdeckel je Klasse
(Intraday am Tagesschluss, Insider sechs Monate, Rest 26 Wochen?);
viertens, ob die Klimax-Warnung scharf oder zunächst nur ins
Schattenbuch geschrieben wird, bis ihre Trefferquote gemessen ist.

Quellenübersicht: Darvas 1960; O'Neil, How to Make Money in Stocks,
4. Auflage; Minervini 2012 und 2017; Bulkowski, Encyclopedia of Chart
Patterns samt thepatternsite.com (Cup, Rectangle Tops, HTF, abgerufen
27.08.2026); Wyckoff nach Pruden 2007 und Weis 2013; Kaminski und Lo,
Journal of Financial Markets 2014; Jeng, Metrick und Zeckhauser,
Review of Economics and Statistics 2003; Lakonishok und Lee, RFS 2001;
Cohen, Malloy und Pomorski, Journal of Finance 2012; George und Hwang,
Journal of Finance 2004; Bernard und Thomas, JAR 1989; Brock,
Lakonishok und LeBaron, Journal of Finance 1992; Han, Yang und Zhou,
JFQA 2013; Shefrin und Statman, Journal of Finance 1985; Odean,
Journal of Finance 1998.
