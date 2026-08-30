# Einbau-Vorbereitung: Sechs Strategie-Bausteine aus der Literatur-Recherche

Stand 31.08.2026. Grundlage: Recherche vom 31.08.2026 (Lynch, Thiel,
Phelps/Mayer/Alta Fox, Oliver Kell, Leif Soreide, Earnings-Pullback samt
PEAD-Evidenz) und die Logbuch-Forensik vom 30.08.2026 (338 Signale seit
06.08.). Dieses Papier legt fest, WAS sich WIE in unser System einbauen
laesst, was dafuer da ist, was fehlt, und welche Regelfragen Gerhard
entscheiden muss. Gebaut wird erst nach Freigabe.

Kurzueberblick der sechs Bausteine, sortiert nach empfohlener Reihenfolge:

1. Zahlen-Karenz (Meldefilter vor Quartalszahlen). Aufwand klein.
2. Earnings-Pullback als neues Kaufmuster (Kapitel-Kandidat). Aufwand mittel.
3. High-Tight-Flag-Ausbau nach Soreide (Innen-Einstieg, Benotung). Aufwand mittel.
4. Marktampel gruen/gelb/rot (Soreide/Kell). Aufwand klein.
5. Kell-Zyklus: Phasen-Kennung, EMA-Crossback-Setup, Wedge-Drop-Exit. Aufwand mittel.
6. Tenbagger-Radar (Lynch/Mayer/Alta Fox/Thiel). Aufwand gross, eigene Datenklasse.

---

## Baustein 1: Zahlen-Karenz vor Quartalsterminen

**Literatur- und Messgrundlage.** Unsere eigene Forensik vom 30.08.2026:
11 Prozent aller 338 gemeldeten Signale hatten einen Zahlentermin binnen
sieben Tagen nach dem Trigger, unter den Ausgestoppten waren es 22 Prozent.
Signale mit Termin im Fenster liefen im Schnitt auf minus 3,38 Prozent bei
25 Prozent Stopp-Quote, alle uebrigen auf minus 0,83 Prozent bei 11 Prozent.
Sechs der zehn groessten Verlierer stuerzten an frischen Zahlen ab. Die
Earnings-Pullback-Literatur (Baustein 2) sagt dasselbe von der anderen
Seite: erst die Zahl, dann der Einstieg.

**Umsetzung.** Im Waechter, unmittelbar vor dem Push jeder Ausbruchs- und
Wiedereintritts-Meldung: zahlen_termine nach einem Termin binnen K
Handelstagen fragen (K einstellbar in config.py). Je nach Regelentscheid:

- Stufe A (weich): melden wie bisher, aber mit hartem Warnkopf als erster
  Zeile. Den Termin-Hinweis vorn haben wir seit 31.08. ohnehin; die Stufe
  ergaenzt nur Termine, die weiter als morgen liegen.
- Stufe B (mittel): nur VOLUMENBESTAETIGTE Ausbruche melden, unbestaetigte
  im Karenzfenster unterdruecken.
- Stufe C (hart): im Karenzfenster gar nichts melden; der Kaufpunkt bleibt
  im Gedaechtnis und wird nach der Zahl regulaer behandelt.

Jede unterdrueckte Meldung landet als Logbuch-Zeile (gemeldet=False,
grund="zahlen_karenz"), damit die Wirkung der Regel messbar bleibt und
nichts still verschwindet.

**Ehrliche Grenze.** Die Karenz schuetzt nur, wo der Termin BEKANNT ist.
Unser Terminmodul speist sich aus Yahoo- und Nasdaq-Kalender; im
KALU-Fall der Forensik kannte keine Quelle einen Termin. Die Regel senkt
das Risiko, sie beseitigt es nicht.

**Regelfragen an Gerhard.** G1: Welche Stufe (A, B oder C)? G2: Wie viele
Handelstage Karenz (Vorschlag 2, gemessen wurde das 7-Tage-Fenster)?
G3: Gilt die Karenz auch fuer Gap and Go und Red-to-Green oder nur fuer
die Muster-Ausbrueche?

---

## Baustein 2: Earnings-Pullback als neues Kaufmuster

**Literaturgrundlage.** Akademisch: Post-Earnings-Announcement Drift
(Ball/Brown 1968; Bernard/Thomas 1989 und 1990): Nach positiven
Gewinnueberraschungen driften Kurse ueber Wochen bis Monate weiter, die
Long-Short-Umsetzung erzielte historisch rund 18 Prozent abnormale
Jahresrendite, und 25 bis 30 Prozent der Drift ballen sich um die
naechsten Quartalstermine. Praktisch: Episodic Pivot (Pradeep Bonde),
Power Earnings Gap (TraderStewie, die Pullback-Fassung) und Buyable
Gap-Up (Morales/Kacher) mit den Kennzahlen Gap ab 8 bis 10 Prozent,
Volumen-Vielfaches frueh am Tag, Einstieg an der ersten Konsolidierung
nach dem Gap, Stop unter Konsolidierung bzw. Gap-Tag-Tief mit 3 bis 4
Prozent Toleranz.

**Was schon da ist.** Gap and Go (Kapitel 7, Anzeigename
Luecken-Bestaetigungstag) erkennt Eroeffnungsluecken ab 7 Prozent samt
Flat Base und Volumenregeln, kauft aber den GAP-TAG selbst und fragt
nicht nach dem Anlass. Das Zahlen-Termine-Modul kennt die Termine je
Aktie. yfinance liefert je Termin die Gewinnueberraschung in Prozent
(Spalte Surprise in get_earnings_dates, in der Forensik bereits benutzt).
Kapitel 12 fuehrt die Beobachtungs-Klasse zahlen_luecke mit 60 Tagen
Zeitdeckel, die exakt fuer solche Neubewertungs-Trades gedacht ist.

**Umsetzung.** Neues Nachtscan-Muster "Earnings-Pullback" in einer
eigenen Datei (earnings_pullback.py), Ablauf je Aktie der Listen:

1. Gap-Tag finden, hoechstens 15 Handelstage zurueck: Eroeffnung
   mindestens 8 Prozent ueber Vortagesschluss ODER Tagesgewinn ab 10
   Prozent, Tagesvolumen mindestens 3-fach ueber dem 10-Tage-Schnitt.
2. Zahlen-Bindung: Am Gap-Tag oder am Vorabend lag der Quartalstermin
   (Terminmodul), Ueberraschung positiv soweit abrufbar. Ohne
   Zahlen-Bindung kein Earnings-Pullback (dafuer gibt es Gap and Go).
3. Konsolidierung ab dem zweiten Tag nach dem Gap: mindestens 2,
   hoechstens 15 Handelstage; alle Tiefs bleiben ueber dem Tief des
   Gap-Tags; die Spanne der Konsolidierung bleibt unter einem Anteil der
   Gap-Tag-Spanne (Vorschlag: hoechstens die Haelfte); Volumen trocknet
   gegenueber dem Gap-Tag aus.
4. Marken in die Mappe: Kaufpunkt = Konsolidierungshoch plus 1 Cent.
   Stop = das Hoehere aus Konsolidierungstief minus 1 Cent und Gap-Tag-
   Tief mal 0,96 (Porosity-Toleranz nach Morales), gedeckelt durch
   unseren bestehenden 10-Prozent-Deckel. Ziel: keines; die Bewirtschaft-
   ung uebernimmt Kapitel 12.
5. Waechter: gewoehnliche Ausbruchs-Ueberwachung ueber die Mappe, eigener
   Strategiename, Volumenfaktor wie Standard (1,5-fach), Meldung traegt
   den Zusatz "nach Quartalszahlen vom TT.MM." im Kopfbereich.
6. Beobachtung: nach Push-Erfolg Kapitel-12-Eintrag mit Klasse
   zahlen_luecke (Zeitdeckel 60 Tage existiert dort schon), Trailing wie
   gehabt ueber die Gewinnzonen.

**Datenlage.** Vollstaendig vorhanden: Tagesdaten, Termine,
Ueberraschungen, Mappe, Waechter, Kapitel 12. Kein neuer Dienst noetig.

**Pruefweg.** Selbsttest mit synthetischen Reihen (Gap, saubere und
verletzte Konsolidierung, fehlende Zahlen-Bindung); Rueckrechnung ueber
die echten Earnings-Gaps der letzten Wochen (ONON, LQDA, RBRK als
Negativ-Beispiele VOR der Zahl, APPS-Muster aus der Literatur als
Positiv-Schema); Logbuch-Quelle scanner/earnings_pullback.

**Regelfragen.** G4: Gap-Schwelle 8 Prozent Eroeffnung oder 10 Prozent
Tagesgewinn, beides, und mit welchem Volumenfaktor? G5: Muss die
Ueberraschung positiv sein, oder genuegt der Termin (manche Gaps kommen
auf Ausblick statt Gewinn)? G6: Konsolidierungs-Enge die Haelfte der
Gap-Spanne oder strenger? G7: Porosity 4 Prozent unter dem Gap-Tag-Tief
uebernehmen oder harter Stop am Konsolidierungstief?

---

## Baustein 3: High-Tight-Flag-Ausbau nach Leif Soreide

**Grundlage.** Soreide (US-Meister 2019, plus 60,9 Prozent) handelt fast
nur High Tight Flags: Pol ab rund 90 Prozent in hoechstens 8 Wochen, enge
Flagge, Einstieg an ENGEN Stellen IN der Flagge (Inside Day, Shakeout-
Rueckkehr), Stops eng, Setups werden benotet und die Positionsgroesse
folgt der Note. Unsere Forensik: HTF war mit plus 0,47 Prozent Schnitt
und null Ausstoppern bei 18 Signalen die beste Strategie des Logbuchs.

**Was schon da ist.** Die Erkennung in pattern_scanner.py verlangt
bereits: Pol mindestens 90 Prozent (htf_min_rise 0,90) in hoechstens 42
Tagen, Flagge hoechstens 35 Kalendertage und enger als 25 Prozent der
Masthoehe. Soreides Pol-Regel ist also erfuellt, teils strenger.

**Umsetzung in drei Teilen.**

1. Innen-Einstieg: Liegt in der Flagge ein Inside Day (Hoch und Tief
   innerhalb des Vortags) oder ein Engster-Tag-der-Flagge, wird eine
   ZWEITE Marke vergeben: Kaufpunkt = Hoch dieses Tages plus 1 Cent,
   Stop = sein Tief minus 1 Cent. Die Mappe traegt bis zu drei Kaufpunkte
   je Aktie, der Platz ist da. Meldetext nennt die Art ("HTF
   Innen-Einstieg, Inside Day"). Das Risiko je Trade sinkt drastisch,
   dafuer steigt die Fehlversuchsquote; genau so beschreibt es Soreide
   ("der beste Verlierer sein").
2. Shakeout-Rueckkehr: Faellt der Kurs unter das Flaggentief und kehrt
   binnen 3 Handelstagen darueber zurueck, wird das Rueckkehr-Hoch zur
   Marke. Die Logik existiert sinngemaess in Kapitel 10 (Shakeout-Spring)
   und wird hier auf die Flagge uebertragen.
3. Benotung: Jede HTF bekommt eine Note aus vier messbaren Groessen:
   Flaggen-Enge (Spanne zu Masthoehe), Pol-Steilheit (Prozent je Woche),
   Volumen-Austrocknung in der Flagge, RS-Rating der Aktie. Note A/B/C
   steht in der Meldung und im Logbuch; was Mathias daraus an
   Positionsgroesse macht, bleibt seine Sache. Die Gewichte werden nach
   drei Monaten Logbuch nachgemessen.

**Regelfragen.** G8: Sollen Innen-Einstiege ZUSAETZLICH zur Flaggenhoch-
Marke laufen (zwei Meldungen moeglich) oder sie ersetzen? G9: Duerfen
Innen-Einstiege auch UNBESTAETIGT melden (kleines Risiko, frueher
Einstieg), oder gilt die normale Volumenpflicht?

---

## Baustein 4: Marktampel gruen/gelb/rot

**Grundlage.** Soreide steuert seine Aggressivitaet ueber eine
Marktampel plus die eigene Ergebniskurve; Kell handelt gross nur, wenn
S&P 500 und Nasdaq selbst im Aufwaertstrend sind. Bei uns existiert nur
das Red-to-Green-Regime (Nasdaq-Eroeffnungsgap ab minus 1,5 Prozent),
sonst keine Marktzustands-Groesse.

**Umsetzung.** Im Nachtscan taeglich aus S&P 500 und Nasdaq berechnen:
gruen, wenn beide Indizes ueber steigender 21-Tage- UND 50-Tage-Linie
schliessen; rot, wenn einer unter der 50-Tage-Linie schliesst; gelb
sonst. Ergebnis in eine kleine JSON-Datei, der Waechter stellt die Farbe
als eine Zeile an den Anfang der ERSTEN Meldung des Tages und schreibt
sie in jede Logbuch-Zeile. KEINE Meldungsunterdrueckung, die Ampel
informiert nur; ob rot etwa die Fallback-Marken stummschalten soll, ist
eine spaetere Regelfrage, wenn Messdaten da sind. Nach einigen Wochen
liefert das Logbuch die Auswertung "Trefferquote je Ampelfarbe" gratis.

**Regelfrage.** G10: Definition wie vorgeschlagen (21/50-Tage-Linien),
oder will Gerhard seine eigene Marktdefinition verankern?

---

## Baustein 5: Kell-Zyklus (Phasen-Kennung, EMA-Crossback, Wedge Drop)

**Grundlage.** Kells Cycle of Price Action (Victory in Stock Trading,
2021; Meister 2020 mit plus 941,1 Prozent): sechs Stufen um die 10- und
20-Tage-EMA. Fuer uns zerfaellt das in drei getrennt einbaubare Teile.

1. Phasen-Kennung (nur messen, nichts melden): Ein kleines Modul
   (kell_zyklus.py) klassifiziert je Aktie die aktuelle Stufe (Reversal
   Extension, Wedge Pop, EMA Crossback, Base n Break, Exhaustion
   Extension, Wedge Drop) aus Kurs, 10er- und 20er-EMA, Abstaenden und
   Richtung. Die Stufe wird als Feld in Mappe und Logbuch gefuehrt.
   Gewinn: Nach ein paar Wochen laesst sich messen, in welcher Stufe
   unsere Ausbrueche funktionieren und in welcher sie scheitern; erst
   danach lohnt die Diskussion, ob die Stufe Meldungen filtern soll.
2. EMA-Crossback als eigenes Kaufmuster: Nach frischem Wedge Pop
   (Kreuzung ueber beide EMAs binnen der letzten 10 Tage nach
   vorheriger Abwaertsphase) ein Ruecksetzer AN die 10/20er-Linie mit
   Umkehrtag; Kaufpunkt = Hoch des Umkehrtags plus 1 Cent, Stop = Tief
   des Ruecksetzers. ACHTUNG: Das ist ein Ruecksetzer-Kauf, kein
   Ausbruch, und damit ein Stilbruch zur bisherigen Linie des Regelwerks;
   ausdruecklich als eigenes Kapitel vorzulegen, nicht still einzubauen.
3. Exhaustion und Wedge Drop in Kapitel 12: Der Klimax-Katalog bekommt
   als zusaetzliches Zeichen die Ueberdehnung gegen den 10er-EMA
   (Abstand in Prozent, Schwelle zu messen), und als hartes
   Zone-stark-Ausstiegssignal den Wedge Drop: erster Schluss unter
   BEIDEN EMAs nach einer Exhaustion. Das ergaenzt Gerhards Katalog um
   Kells kurzfristige Sicht, ersetzt aber nichts.

Die fuenf Kell-Screens brauchen kein eigenes Modul: 52-Wochen-Hoch und
Gapper existieren als Marken, RS existiert als Rating; einzig der Bull
Snort (Volumen 3-fach ohne Kursausbruch, Hinweis auf Akkumulation) waere
eine kleine neue Nachtscan-Hinweisliste ohne Meldepflicht.

**Regelfragen.** G11: EMA-Crossback als Kapitel gewuenscht, ja oder
nein (Stilfrage Ruecksetzer-Kauf)? G12: Wedge-Drop-Ausstieg nur in Zone
stark oder in allen Zonen?

---

## Baustein 6: Tenbagger-Radar (Lynch, Mayer, Alta Fox, Thiel)

**Grundlage.** Lynch (Fast Grower, PEG unter 1, Insiderkaeufe,
Rueckkaeufe, wenig Institutionen, verstaendliche Story), Mayer (365
Hundertfacher: klein, Eigenkapitalrendite 20 bis 30 Prozent,
reinvestierbar, Owner-Operator, Twin Engines aus Gewinnwachstum und
Bewertungsausdehnung), Alta Fox (104 Topwerte 2015 bis 2020: klein,
unbeachtet, 82 Prozent starteten unter 3-fach Umsatz, 20-fach EBITDA
oder 30-fach Gewinn, Nischen-Dominanz, hoher Insiderbesitz), Thiel
(Power Law: die seltenen Ausreisser zahlen alles; Monopolmerkmale und
die sieben Fragen als Pruefraster).

**Ehrliche Einordnung.** Das ist eine INVESTMENT-Strategie mit
Fundamentaldaten und Monats- bis Jahreshorizont, kein Ausbruchs-Setup.
Automatisierbar sind die messbaren Filter und ein Scoring; NICHT
automatisierbar sind Story, Burggraben und Nische (Lynchs
Zwei-Minuten-Erklaerung, Thiels Geheimnis-Frage). Der Radar liefert
deshalb eine kleine, geprüfte Kandidatenliste; das Urteil bleibt bei
Gerhard und Mathias.

**Umsetzung.** Eigener WOCHENLAUF (Samstagvormittag, eigener Workflow),
Modul tenbagger_radar.py:

1. Universum: zunaechst unsere beiden Wochenlisten plus Darvas-Liste
   (pragmatisch, Daten vorhanden). Erweiterung auf ein breites
   Smallcap-Universum ist moeglich, aber ein eigener Beschaffungs-
   schritt; die Studien sagen klar, dass die besten Kandidaten KLEIN
   und UNBEACHTET sind, also teils ausserhalb unserer Momentum-Listen.
2. Messbare Filter und Punkte (Quelle je Wert in Klammern):
   Marktkapitalisierung unter 1 Milliarde, Bonus unter 300 Millionen
   (yfinance); Umsatzwachstum ab 20 Prozent jaehrlich (yfinance,
   Zweitquelle FMP); Gewinn positiv und wachsend (dito); PEG unter 1
   (gerechnet aus KGV und Wachstum); Bruttomarge ab 50 Prozent als
   Monopol-Naeherung nach Thiel und Alta Fox (yfinance); Eigenkapital-
   rendite ab 20 Prozent (yfinance); Nettoschulden hoechstens null
   (yfinance); Insiderbesitz ab 10 Prozent (yfinance heldPercentInsiders);
   Institutionenanteil UNTER 40 Prozent als Lynch-Unentdecktheits-Signal
   (yfinance); Bewertung unter 3-fach Umsatz ODER unter 30-fach Gewinn
   (Alta-Fox-Befund); frische Insider-CLUSTER-Kaeufe aus unserem eigenen
   EDGAR-Modul als Lynch-Bestaetigung; RS-Rating und Trend-Template aus
   dem Bestand als technische Mindestbedingung.
3. Ausgabe: Punktestand 0 bis 100 je Kandidat, die Top 10 als
   Wochen-Push "Tenbagger-Radar" (reine Informationsliste, KEINE
   Kaufpunkte) plus JSON im Repo. Und die elegante Kopplung: Meldet der
   Waechter einen gewoehnlichen Ausbruch einer Radar-Aktie, traegt die
   Meldung den Zusatz "Tenbagger-Radar: N Punkte" im Kopfbereich; so
   fliesst die Investment-Sicht in die bestehenden Meldewege, ohne einen
   neuen zu erfinden.
4. Haltelogik: neue Kapitel-12-Klasse "tenbagger" OHNE Zeitdeckel, mit
   weitem Trail (Wochen-Schluss unter der 30-Wochen-Linie nach
   Weinstein als einziges Ausstiegssignal), fuer Beobachtungen, die
   Mathias ausdruecklich als Langfrist-Kandidaten eintraegt. Das bildet
   Phelps' "buy right and hold on" und Mayers Kaffeedose ab, ohne echte
   Depots zu beruehren.

**Ehrliche Datenlage.** yfinance-Fundamentaldaten sind bei Microcaps
lueckig und teils verzoegert; FMP als Zweitquelle hat im Gratis-Tarif
250 Abrufe je Tag, ein Wochenlauf ueber ein paar hundert Titel muss
also haushalten oder sich ueber zwei Tage strecken. Felder koennen
fehlen; der Radar rechnet dann mit dem Vorhandenen und weist je
Kandidat aus, wie viele Kriterien pruefbar waren. Ein Kandidat mit 6
von 12 pruefbaren Kriterien wird nie gleich behandelt wie einer mit 12
von 12.

**Regelfragen.** G13: Universum nur unsere Listen oder eigener
Smallcap-Beschaffungsschritt? G14: Schwellenwerte wie vorgeschlagen
oder Gerhards eigene? G15: Soll die tenbagger-Halteklasse gebaut
werden, und ist die 30-Wochen-Linie ihr einziger Ausstieg?

---

## Was bewusst NICHT vorgeschlagen wird

- Thiels sieben Fragen als Automatik: vier davon (Technik, Team,
  Geheimnis, Dauerhaftigkeit) sind nicht maschinell pruefbar. Sie
  gehoeren als Pruefraster in Gerhards Hand, der Radar liefert nur die
  Vorauswahl.
- Soreides Ergebniskurven-Steuerung und Monats-Drawdown-Limit: das
  steuert einen HAENDLER, nicht ein Meldesystem. Wir handeln nicht.
- Kells bearische Zyklushaelfte als Short-Signale: das Regelwerk kennt
  keine Leerverkaeufe.
- Lynch-Kategorien als Automatik: die Einordnung (Zykliker, Turnaround,
  Substanzwert) braucht Verstaendnis des Geschaefts; automatisierbar
  ist nur der Fast-Grower-Filter, und der steckt im Radar.

## Empfohlene Reihenfolge und Aufwand

1. Zahlen-Karenz: klein, Messgrundlage liegt vor, drei Regelfragen.
2. Earnings-Pullback: mittel, alle Daten vorhanden, staerkste
   Literatur-Deckung (akademisch und praktisch).
3. HTF-Ausbau: mittel, beste Strategie im eigenen Logbuch, Soreides
   Regeln passen fast nahtlos auf die bestehende Erkennung.
4. Marktampel: klein, schafft sofort Messdaten fuer alles Weitere.
5. Kell-Zyklus: mittel, Teil 1 (nur messen) zuerst, Teil 2 als
   Stilfrage an Gerhard.
6. Tenbagger-Radar: gross, eigene Datenklasse, als letztes und in
   Etappen.

Alle Regelfragen gesammelt: G1 bis G3 (Karenz), G4 bis G7
(Earnings-Pullback), G8 bis G9 (HTF), G10 (Ampel), G11 bis G12 (Kell),
G13 bis G15 (Tenbagger-Radar).
