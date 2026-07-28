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

- *Heliot Scan (18:00 New York)* — `0 18 * * 0-5`, scanner.yml,
  Text `{"ref":"main"}`. Sonntag ist bewusst dabei, damit die am
  Wochenende hochgeladene Liste am Montag bereitliegt.
- *Heliot Alarme (08:00 New York)* — `0 8 * * 1-5`, alarme.yml,
  Text `{"ref":"main","inputs":{"modus":"vollstaendig","quelle":"repo_datei"}}`.
  1,5 Stunden vor der Glocke, damit Alarme nicht im europäischen
  Vorhandel verfeuert werden.
- *Heliot ntfy-Putz (16:05 New York)* — `5 16 * * 1-5`, alarme.yml,
  Text `{"ref":"main","inputs":{"modus":"ntfyputz"}}`.
- *Heliot Freitags-Putz (16:02 New York)* — `2 16 * * 5`, alarme.yml,
  Text `{"ref":"main","inputs":{"modus":"alles_loeschen","loeschen":"ALLE"}}`.
- *Wächter Tagwache* — `12 9 * * 1-5`, watcher.yml,
  Text `{"ref":"main","inputs":{"dauerwache":"390"}}`.
- *Heliot Teil 2 (Schlussstunde, 15:09 New York)* — `9 15 * * 1-5`,
  watcher.yml.

ACHTUNG beim Klonen eines Auftrags: Die Kopie wird **deaktiviert**
angelegt und muss über „Job aktivieren" scharf geschaltet werden. Der
Anfragetext der Vorlage wird mitkopiert und muss angepasst werden.

**Geheimnisse bei GitHub** (nur die Namen, die Werte trägt Mathias
selbst ein): `TRADERFOX_USER`, `TRADERFOX_PASS`, `NTFY_TOPIC`,
`TWELVE_DATA_API_KEY`, `FMP_API_KEY`.

**Zustand, der nur im Actions-Zwischenspeicher lebt:** `session.json`
(TraderFox-Sitzung, wird bei Bedarf neu erzeugt) und
`watcher_state.json` (was der Wächter diese Woche schon gemeldet hat).
Beides ist entbehrlich — im schlimmsten Fall meldet der Wächter einmal
doppelt.

## Wie der Ablauf zu diesem Zeitpunkt aussieht (österreichische Zeit)

- **00:00** (So–Fr): Scanner rechnet die neue Kaufpunkt-Liste, sendet
  nichts, veröffentlicht `kaufpunkte_aktuell.xlsx` ins Repo.
- **14:00** (Mo–Fr): Alarm-Bot gleicht ab — entfernt Marken, deren
  Kaufpunkt sich verschoben hat oder deren Muster weggefallen ist — und
  trägt die neuen ein. Zwei Durchgänge, der zweite holt Nachzügler.
- **15:12**: Wächter startet, wartet bis zur Glocke.
- **15:30 bis 22:00**: Wächter prüft alle sechs Minuten; meldet jede
  Aktie einmal pro Woche. Außerhalb dieser Zeiten wird **nie** gemeldet.
- **21:09**: Schlussstunden-Wache übernimmt.
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
