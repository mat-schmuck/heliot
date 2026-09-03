# Sicherungspunkt vor dem Umbau (27.07.2026)

Angelegt auf Mathias' Wunsch, unmittelbar bevor der Bot auf Gerhards
Vorgaben hin umgebaut wird. Dieser Stand ist erprobt und lief im
Echtbetrieb.

**Marke:** `stand-vor-umbau-2026-07-27` — **Zweig:** `stand-vor-umbau`

## Zurückholen

Nur ansehen, ohne etwas zu verändern:

    git checkout stand-vor-umbau-2026-07-27

Den alten Stand wieder zum gültigen machen (Verlauf bleibt erhalten):

    git checkout main
    git revert --no-commit stand-vor-umbau-2026-07-27..HEAD
    git commit -m "Zurück auf den Stand vom 27.07.2026"
    git push origin main

Einzelne Datei zurückholen:

    git checkout stand-vor-umbau-2026-07-27 -- traderfox_alarm_bot.py

## Was NICHT im Repo liegt und beim Wiederherstellen mitgedacht werden muss

**Zeitpläne bei cron-job.org** (Konto von Mathias, Zeitzone durchgehend
America/New_York, GitHub-Token als Kopfzeile im jeweiligen Auftrag):

- *Heliot Scan (18:00 New York, Wiederanlauf alle 10 Min bis 09:00)*
  (Auftrag 8147309) — `*/10 18-23,0-8 * * *`, scanner.yml,
  Text `{"ref":"main"}`.

  **Am 07.08.2026 vom Tagestermin auf einen Takt umgestellt.** Vorher
  stand hier `0 18 * * 0-5`, also genau ein Anstoß am Tag. Am 06.08.
  hatte GitHub Actions eine schwere Störung, der Lauf bekam keinen
  Rechner und fiel aus — am nächsten Morgen war die Kaufpunkte-Mappe
  zwei Tage alt, und niemand hatte es bemerkt.

  Jetzt wird von der Fälligkeit um 18:00 durchgehend bis 08:50 am
  nächsten Morgen alle zehn Minuten angeklopft. Dass daraus keine
  dreißig Scans werden, verhindert `scan_noetig.py` im Arbeitsablauf
  selbst: Es prüft, ob seit dem letzten fälligen Termin (18:00 New
  York, Sonntag bis Freitag) schon ein Lauf geglückt ist, und beendet
  den Ablauf sonst nach rund sechzehn Sekunden. Dazu die
  concurrency-Gruppe `pattern-scanner`, die der Scanner bis dahin gar
  nicht hatte.

  Gemessen gegen ein ALTER zu prüfen wäre falsch: Wird tagsüber von
  Hand nachgeholt, gälte der Abendausfall stundenlang als frisch.
  Deshalb entscheidet der Termin, nicht das Alter.

  Die Wochentage stehen bewusst auf `*` statt `0-5`. Das Fenster geht
  über Mitternacht, und ein Ausfall am Freitagabend braucht die
  Nachholversuche in der Nacht auf Samstag. Überflüssige Anstöße am
  Wochenende erkennt die Prüfung von selbst — samstags gibt es keinen
  fälligen Termin.

- *Heliot Wächter-Hüter (alle 2 Min, Handelszeit)* (Auftrag 8231247,
  angelegt 07.08.2026) — `*/2 9-15 * * 1-5`, **waechterhueter.yml**,
  Text `{"ref":"main"}`.

  Er sieht nach, ob überhaupt eine Wache läuft, und startet nur dann
  eine, wenn gar nichts da ist — weder ein laufender noch ein wartender
  Lauf. Ein WARTENDER zählt ausdrücklich mit: Das ist die
  Schlussstunden-Wache, die nicht verdrängt werden darf.

  **Deshalb ist er ein eigener Ablauf mit eigener concurrency-Gruppe.**
  Stieße man watcher.yml selbst alle zwei Minuten an, geriete jeder
  Anstoß in dessen Gruppe und würfe dort den wartenden Lauf weg — also
  ausgerechnet die Schlussstunden-Wache, im wichtigsten Abschnitt des
  Tages.

  Beide Prüfungen fragen GitHub MIT dem eingebauten Token ab. Ohne
  Anmeldung liegt die Grenze bei 60 Anfragen je Stunde und IP-Adresse,
  und auf den Actions-Rechnern teilt man sich die Adresse mit Fremden;
  mit Token sind es 1000 je Stunde und Repository. Erst damit ist ein
  Zwei-Minuten-Takt haltbar.
- *Heliot ntfy-Putz (16:05 New York)* — `5 16 * * 1-5`, alarme.yml,
  Text `{"ref":"main","inputs":{"modus":"ntfyputz"}}`.

**Am 30.07.2026 GELÖSCHT** (Gerhards Entscheid: ntfy ersetzt die
TraderFox-Alarme, siehe `EINTRAGEN_AKTIV` in traderfox_alarm_bot.py).
Falls die Alarme je wieder scharf geschaltet werden, müssen diese zwei
Aufträge neu angelegt werden:

- *Heliot Alarme (08:00 New York)* — `0 8 * * 1-5`, alarme.yml,
  Text `{"ref":"main","inputs":{"modus":"vollstaendig","quelle":"repo_datei"}}`.
  1,5 Stunden vor der Glocke, damit Alarme nicht im europäischen
  Vorhandel verfeuert werden.
- *Heliot Freitags-Putz (16:02 New York)* — `2 16 * * 5`, alarme.yml,
  Text `{"ref":"main","inputs":{"modus":"alles_loeschen","loeschen":"ALLE"}}`.
  ACHTUNG beim Wiederanlegen: Dieser Auftrag erledigte ZWEI Dinge — die
  Alarme löschen UND die ntfy-Meldungen räumen. Das Zweite läuft
  unabhängig davon weiter, weil der tägliche ntfy-Putz um 16:05
  denselben Befehl ausführt und Montag bis Freitag läuft, also auch am
  Freitag. Genau deshalb war das Löschen dieses Auftrags gefahrlos.
- *Heliot Tagwache (09:28 New York)* (Auftrag 8146990) —
  `28 9 * * 1-5`, watcher.yml,
  Text `{"ref":"main","inputs":{"dauerwache":"390"}}`.
- *Heliot Teil 2 (Schlussstunde, 15:26 New York)* (Auftrag 8147021) —
  `26 15 * * 1-5`, watcher.yml,
  Text `{"ref":"main","inputs":{"dauerwache":"390"}}`.

  Also derselbe Text wie bei der Tagwache. Hier stand kurzzeitig
  `{"ref":"main"}` — das war eine Annahme von mir und falsch, im
  Auftrag nachgesehen am 05.08.2026. Die 390 Minuten laufen ohnehin nie
  ab: Der Wächter beendet sich beim Schlussgong von selbst, also nach
  rund 34 Minuten.

  **Am 04.08.2026 verschoben** (Mathias), von 09:12 auf 09:28 und von
  15:09 auf 15:26. GitHub schießt jeden Auftrag nach sechs Stunden ab,
  gerechnet ab dem Start — jede Minute Vorlauf fehlt also am Nachmittag.
  Gemessen dauert die ganze Vorbereitung 28 Sekunden: 18 Sekunden
  GitHub-Rüstzeit, 8,6 Sekunden für die Tagesdaten aller 366 Aktien,
  eine Sekunde für die fünf Stromverbindungen. Reserviert waren dafür
  18 Minuten. Der Handelstag ist jetzt 16 Minuten länger abgedeckt.

  **Die beiden Zeiten gehören zusammen.** Der zweite Auftrag muss VOR
  dem Ende des ersten auslösen, sonst entsteht ein Loch: Er hängt sich
  per `concurrency` hinter die Tagwache und übernimmt genau dann, wenn
  sie fällt. Zwischen 15:26 und 15:28 liegen zweieinhalb Minuten, und
  das ist der einzige Puffer. Wer die eine Zeit verschiebt, muss die
  andere mitverschieben.

- *Heliot Konsens einfrieren (05:00 New York)* (Auftrag 8373624,
  angelegt 02.09.2026) — `0 5 * * 1-5`, **einfrieren.yml**,
  Text `{"ref":"main","inputs":{"modus":"schnappschuss"}}`.
- *Heliot Konsens einfrieren (15:30 New York)* (Auftrag 8373640,
  angelegt 02.09.2026) — `30 15 * * 1-5`, **einfrieren.yml**,
  Text `{"ref":"main","inputs":{"modus":"schnappschuss"}}`.

  Gerhards F9: Der Analystenkonsens wird zweimal je Handelstag
  eingefroren, vor den Vorbörsen-Meldungen und vor den
  Nachbörsen-Meldungen. Die Schnappschüsse landen im PRIVATEN Datenrepo
  `mat-schmuck/heliot-daten` (F17); der Ablauf braucht dafür das
  Geheimnis `DATEN_TOKEN` (fein granuliertes Token nur für dieses eine
  Repo, Inhalte lesen und schreiben, kein Ablaufdatum). Fehlt es, tut
  der Lauf nichts und sagt es. Die Bestandsaufnahme über das ganze
  SEC-Register (Modus `bestandsaufnahme`, Portionen zu 2.500) wird von
  Hand angestoßen; sie teilt die concurrency-Gruppe mit den
  Schnappschüssen, deshalb nie zwei Läufe auf einmal anstoßen: Die
  Gruppe hält nur EINEN wartenden Lauf.

ACHTUNG beim Klonen eines Auftrags: Die Kopie wird **deaktiviert**
angelegt und muss über „Job aktivieren" scharf geschaltet werden. Der
Anfragetext der Vorlage wird mitkopiert und muss angepasst werden.
Die Konsole speichert per Skript gesetzte Textfelder (Titel,
Anfrage-Body) erst, wenn das Feld auch verlassen wurde; Uhrzeit-Listen
und der Aktivieren-Schalter reagieren sofort. Nach dem Speichern die
Seite neu laden und nachsehen, was wirklich angekommen ist.

**Geheimnisse bei GitHub** (nur die Namen, die Werte trägt Mathias
selbst ein): `TRADERFOX_USER`, `TRADERFOX_PASS`, `NTFY_TOPIC`,
`TWELVE_DATA_API_KEY`, `FMP_API_KEY`, `FINNHUB_API_KEY`,
`SEC_USER_AGENT` (Kontaktkennung für SEC-Abrufe, nie im Quelltext),
`DATEN_TOKEN` (Schreibzugang auf heliot-daten).

**Zustand, der nur im Actions-Zwischenspeicher lebt:** `session.json`
(TraderFox-Sitzung, wird bei Bedarf neu erzeugt) und
`watcher_state.json` (was der Wächter diese Woche schon gemeldet hat).
Beides ist entbehrlich — im schlimmsten Fall meldet der Wächter einmal
doppelt.

## Wie der Ablauf zu diesem Zeitpunkt aussieht (österreichische Zeit)

- **00:00** (So–Fr): Scanner rechnet die neue Kaufpunkt-Liste, sendet
  nichts, veröffentlicht `kaufpunkte_aktuell.xlsx` ins Repo.
- **11:00** (Mo–Fr, 05:00 New York): Konsens einfrieren, Schnappschuss
  vor den Vorbörsen-Meldungen ins Datenrepo heliot-daten.
- **14:00** (Mo–Fr): Alarm-Bot gleicht ab — entfernt Marken, deren
  Kaufpunkt sich verschoben hat oder deren Muster weggefallen ist — und
  trägt die neuen ein. Zwei Durchgänge, der zweite holt Nachzügler.
- **15:12**: Wächter startet, wartet bis zur Glocke.
- **15:30 bis 22:00**: Wächter prüft alle sechs Minuten; meldet jede
  Aktie einmal pro Woche. Außerhalb dieser Zeiten wird **nie** gemeldet.
- **21:09**: Schlussstunden-Wache übernimmt.
- **21:30** (Mo–Fr, 15:30 New York): Konsens einfrieren, Schnappschuss
  vor den Nachbörsen-Meldungen.
- **22:05** (Mo–Fr): ntfy-Meldungen werden gelöscht.
- **22:02** (Fr): sämtliche TraderFox-Alarme und ntfy-Meldungen weg,
  Gedächtnis geleert; am Wochenende lädt Gerhard die neue Liste hoch.

## Erprobte Eigenheiten, die beim Umbau nicht verlorengehen sollten

Die ausführlichen Begründungen stehen als Kommentare direkt im Quelltext
(Mathias hat sie am 24.07. ausdrücklich behalten wollen). Kurzfassung:

- TraderFox-Knöpfe brauchen die volle Maus-Ereignisfolge
  (mouseover/mousedown/mouseup/click); einfache Klicks bleiben wirkungslos.
- Die Suchkonsole muss vor jeder Suche über „Liste zurücksetzen" geleert
  und das Ergebnis nachgezählt werden.
- Preise im deutschen Format mit Komma eintippen.
- Alarm-Dialog gegen den Firmennamen prüfen, sonst landen Kaufpunkte bei
  der falschen Aktie.
- ntfy wandelt Nachrichten ab 4096 Zeichen in einen Dateianhang um.
- Der Wächter darf ausschließlich während der New Yorker Handelszeit
  melden — die Sperre sitzt in `sende()`.
