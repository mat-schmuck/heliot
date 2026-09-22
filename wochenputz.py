#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WOCHENPUTZ — freitags alles Wochenbezogene leeren
=================================================
Mathias, 13.09.2026: "In einigen Kategorien liegen noch alte Aktien,
Kursalarme, Chartpunkte etc. von voriger Woche, dies muss immer automatisch
entfernt werden. Sorge dafuer, dass freitags alles geloescht wird, wie es der
Freitagsputz eigentlich tun sollte."

BEFUND, der zu dieser Datei gefuehrt hat (gemessen an der Laufhistorie):
  * Der Auftrag "Heliot Freitags-Putz" bei cron-job.org (alarme.yml mit
    modus=alles_loeschen) lief zuletzt am 29.07.2026, und das waren zwei
    Handlaeufe. Seither kein einziger Freitags-Putz.
  * Selbst wenn er liefe, raeumte er nur TraderFox-Alarme (stillgelegt
    seit 29.07.2026) und ntfy-Meldungen. Fuer die Kaufpunkte-Mappe, die
    Fokusliste und das Melde-Gedaechtnis gab es nie einen Putz.
  * wartung.raeume_zustaende wird von keinem Ablauf aufgerufen; seine
    drei Dateien gibt es im Repo nicht mehr.
  * Der Nachtscan laeuft Sonntag bis Freitag 18:00 New York und rechnete
    am Freitag die ALTE Wochenliste noch einmal. Die blieb bis zum
    Sonntagsscan in der Karte "Aktueller Scan" stehen.

DIE REGEL, in einem Satz: Kaufpunkte gibt es nur aus einer Wochenliste, die
NACH dem letzten Freitagsputz (Freitag 16:02 New York, dieselbe Wochengrenze
wie ueberall, siehe config.letzter_putz_tag) hochgeladen wurde.

WAS GEPUTZT WIRD, sobald der Putz-Freitag vorbei ist und die Wochenliste
aelter ist als dieser Freitag:
  * kaufpunkte_aktuell.xlsx wird durch die leere Vorlage kaufpunkte_leer.xlsx
    ersetzt (dieselben Spalten, keine Zeile). Die App sagt dann, dass die
    Wochenliste aussteht; der Waechter endet mit einem Hinweis statt rot.
  * fokusliste.json wird geleert (Kapitel 9 braucht sie am Morgen; eine
    Liste der alten Woche waere dort falsch).
  * melde_gedaechtnis.json wird auf die Wochenregel gefiltert, so wie der
    Waechter es beim Laden ohnehin tut: Insider-Meldungen behalten ihre
    30 Tage, alles andere von vor dem Putz-Freitag verfaellt, das
    Einstiegsfenster wird geleert, die Warteliste der Luecken-Tage bleibt.
  * alarm_kaufpunkte.json wird geleert (die Kaufpunkte der sechs Alarm-Muster
    stammen aus demselben Nachtscan ueber dieselbe Wochenliste).
  * einzelaktien.csv verliert jede Aktie, die VOR dem Putz-Freitag einzeln
    zur Ueberwachung eingetragen wurde (Gerhard, 22.09.2026, O12: "der
    Freitagsputz soll die Ueberwachung selbst mit beenden"). Was danach
    eingetragen wurde, bleibt; diese Regel haengt nicht am Listen-Datum,
    sondern am Eintragsdatum der Zeile.

WAS NIE ANGEFASST WIRD: positionen.json (offene Positionen leben, solange sie
offen sind), exit_befunde.json (Gesamtpruefung, Block E), die
Shakeout-Warteliste (Gerhard: bis zu 15 Handelstage), trigger_logbuch.jsonl
(das Gedaechtnis), sektor_radar.json (misst Sektor-ETFs, nicht die Liste),
ntfy_ids.json (den ntfy-Putz macht alarme.yml werktags 16:05 New York) und
die Nachschlagedaten.

WANN ES LAEUFT: bei JEDEM Anstoss von scanner.yml, also alle zehn Minuten,
mit Bordmitteln (kein pip). Es ist datumsgesteuert und wiederholbar: Vor
dem Putz-Freitag tut es nichts, nach dem naechsten Upload tut es nichts,
und ein versaeumter Freitag (cron-job.org-Ausfall) wird beim naechsten
Anstoss nachgeholt. Mit --nach-scan wendet der Veroeffentlichungs-Schritt
dieselbe Regel auf die frisch gerechnete Mappe an: Der Freitagsscan laeuft
weiter (Exit-Pruefung, Logbuch, Volumenkurven, Abendbericht gehoeren zur
Nacht), veroeffentlicht aber eine leere Mappe, solange keine neue Liste da
ist.

WOHER DAS LISTEN-DATUM KOMMT: aus dem juengsten Commit der beiden
Wochenlisten laut GitHub (dieselbe Abfrage wie in der App). Ist es nicht
feststellbar, bleibt alles, wie es ist, und der naechste Anstoss versucht es
erneut. Fuer Pruefungen laesst es sich mit --listen-datum vorgeben.

Aufruf:
    python wochenputz.py                       im Arbeitsablauf (Betrieb)
    python wochenputz.py --nach-scan --mappe kaufpunkte.xlsx
    python wochenputz.py --selbsttest
    python wochenputz.py --jetzt 2026-09-18T16:10:00-04:00 --listen-datum 2026-09-13T15:14:30Z --basis ordner
"""

import argparse
import json
import os
import shutil
import sys
import urllib.request
import zipfile
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from config import CFG, letzter_putz_tag

MAPPE = "kaufpunkte_aktuell.xlsx"
VORLAGE = "kaufpunkte_leer.xlsx"
FOKUSLISTE = "fokusliste.json"
# Die Kaufpunkte der sechs Alarm-Muster (Gerhard, 22.09.2026): eine eigene
# Datei neben der Mappe, also auch ein eigener Putz.
ALARM = "alarm_kaufpunkte.json"
GEDAECHTNIS = "melde_gedaechtnis.json"
LISTEN = ("finviz_3.csv", "darvas.csv")
INSIDER_MARKE = "INSIDER|"
INSIDER_TAGE = 30
# Die Warteliste der Luecken-Bestaetigungstage (breakout_watcher.GAPGO_WARTEN):
# ihr Einstieg liegt im Folgetag, ein Freitags-Eintrag wartet auf den Montag.
GAPGO_WARTEN = "gapgo_warten"
NIE_ANFASSEN = ("positionen.json", "exit_befunde.json", "shakeout_warteliste.json",
                "trigger_logbuch.jsonl", "sektor_radar.json", "ntfy_ids.json",
                "finviz_3.csv", "darvas.csv")


def zone():
    return ZoneInfo(CFG["betrieb"]["zeitzone_boerse"])


def putz_grenze(jetzt=None):
    """Der juengste VERGANGENE Freitag 16:02 New York als Zeitpunkt mit
    Zeitzone. Steht der heutige Putz noch aus, zaehlt der der Vorwoche."""
    ny = zone()
    jetzt = jetzt.astimezone(ny) if jetzt else datetime.now(ny)
    tag = date.fromisoformat(letzter_putz_tag(jetzt))
    return datetime.combine(tag, time(16, 2), tzinfo=ny)


def _kopfzeilen():
    kopf = {"Accept": "application/vnd.github+json",
            "User-Agent": "heliot-wochenputz"}
    token = (os.environ.get("GITHUB_TOKEN") or "").strip()
    if token:
        kopf["Authorization"] = f"Bearer {token}"
    return kopf


def listen_datum(repo, dateien=LISTEN):
    """Der juengste Commit-Zeitpunkt der Wochenlisten laut GitHub, mit
    Zeitzone UTC. None, wenn keine Liste je eingecheckt war."""
    neuestes = None
    for name in dateien:
        url = (f"https://api.github.com/repos/{repo}/commits"
               f"?path={name}&per_page=1")
        bitte = urllib.request.Request(url, headers=_kopfzeilen())
        with urllib.request.urlopen(bitte, timeout=30) as a:
            commits = json.loads(a.read().decode("utf-8"))
        if not commits:
            continue
        wann = datetime.fromisoformat(
            str(commits[0]["commit"]["committer"]["date"]).replace("Z", "+00:00"))
        if neuestes is None or wann > neuestes:
            neuestes = wann
    return neuestes


def liste_frisch(listen_zeit, grenze):
    """True: die Liste kam nach dem Putz-Freitag, die Kaufpunkte gelten.
    False: sie ist aelter, die Woche ist vorbei. None: nicht feststellbar."""
    if listen_zeit is None:
        return None
    return listen_zeit > grenze


def mappe_leer(pfad):
    """Traegt das Blatt Kaufpunkte keine einzige Datenzeile? Gelesen ohne
    openpyxl (Bordmittel): Das erste Blatt ist die Kaufpunkte-Tabelle, jede
    Zeile steht als <row>-Element, die Kopfzeile ist die einzige."""
    try:
        with zipfile.ZipFile(pfad) as z:
            xml = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
    except Exception:
        return False
    return xml.count("<row ") <= 1


def _lies_json(pfad, vorgabe):
    try:
        with open(pfad, encoding="utf-8-sig") as f:
            daten = json.load(f)
        return daten if isinstance(daten, dict) else vorgabe
    except Exception:
        return vorgabe


def _schreib_json(pfad, daten):
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(daten, f, indent=1, ensure_ascii=False)


def wiener_zeit(jetzt=None):
    jetzt = jetzt or datetime.now(timezone.utc)
    return jetzt.astimezone(ZoneInfo("Europe/Vienna")).strftime("%Y-%m-%d %H:%M Wien")


def mappe_regel(basis, jetzt, listen_zeit, mappe=MAPPE):
    """Die Wochenregel auf Mappe und Fokusliste: leeren, wenn die Liste
    aelter ist als der Putz-Freitag. Liefert (bericht, geaendert)."""
    b = Path(basis)
    grenze = putz_grenze(jetzt)
    frisch = liste_frisch(listen_zeit, grenze)
    bericht, geaendert = [], False
    if frisch is None:
        bericht.append("Listen-Datum nicht feststellbar; Mappe und Fokusliste bleiben.")
        return bericht, False
    if frisch:
        bericht.append(f"Wochenliste vom {listen_zeit.astimezone(zone()):%d.%m. %H:%M} New York "
                       f"ist juenger als der Putz vom {grenze:%d.%m. %H:%M}; Kaufpunkte gelten.")
        return bericht, False
    bericht.append(f"Wochenliste vom {listen_zeit.astimezone(zone()):%d.%m. %H:%M} New York "
                   f"ist aelter als der Putz vom {grenze:%d.%m. %H:%M}: die Woche ist vorbei.")
    mp = b / mappe
    if mp.exists() and mappe_leer(mp):
        bericht.append(f"{mappe}: schon leer.")
    elif not (b / VORLAGE).exists():
        bericht.append(f"{mappe}: Vorlage {VORLAGE} fehlt, bleibt unangetastet.")
    else:
        shutil.copyfile(b / VORLAGE, mp)
        geaendert = True
        bericht.append(f"{mappe}: geleert (leere Vorlage).")
    fp = b / FOKUSLISTE
    fokus = _lies_json(fp, {})
    if fp.exists() and not fokus.get("aktien"):
        bericht.append(f"{FOKUSLISTE}: schon leer.")
    else:
        _schreib_json(fp, {"gebaut_am": wiener_zeit(jetzt), "universum": 0, "aktien": {},
                           "hinweis": "Wochenputz: die neue Wochenliste steht aus"})
        geaendert = True
        bericht.append(f"{FOKUSLISTE}: geleert ({len(fokus.get('aktien') or {})} Aktien).")
    # Die Alarm-Kaufpunkte gehoeren zur Woche wie die Mappe: Sie stammen aus
    # demselben Nachtscan ueber dieselbe Wochenliste.
    ap = b / ALARM
    alarm = _lies_json(ap, {})
    if ap.exists() and not alarm.get("aktien"):
        bericht.append(f"{ALARM}: schon leer.")
    elif ap.exists():
        _schreib_json(ap, {"stand": wiener_zeit(jetzt), "aktien": [],
                           "hinweis": "Wochenputz: die neue Wochenliste steht aus"})
        geaendert = True
        bericht.append(f"{ALARM}: geleert ({len(alarm.get('aktien') or [])} Aktien).")
    return bericht, geaendert


def einzel_regel(basis, jetzt):
    """O12 (Gerhard, 22.09.2026): "der Freitagsputz soll die Ueberwachung
    selbst mit beenden, nicht nur die gemeldeten Kaufpunkte zuruecksetzen".

    Geleert wird zeilenweise nach dem Eintragsdatum: Was VOR dem letzten
    Putz-Freitag eingetragen wurde, faellt; was danach kam, bleibt. So
    ueberlebt eine Aktie, die am Samstag eingetragen wurde, den Putz vom
    Freitag davor, und der Putz kann wie alles hier alle zehn Minuten laufen,
    ohne etwas doppelt zu tun. Eine Zeile ohne lesbares Datum stammt aus der
    Zeit vor dieser Regel und faellt ebenfalls."""
    import listen
    pfad = Path(basis) / listen.EINZEL_DATEI
    if not pfad.exists():
        return [], False
    zeilen = listen.einzel_zeilen(pfad.read_bytes())
    if not zeilen:
        return [], False
    grenze = putz_grenze(jetzt)
    wien = ZoneInfo("Europe/Vienna")
    bleiben, weg = [], []
    for z in zeilen:
        try:
            wann = datetime.strptime(str(z[2])[:16], "%Y-%m-%d %H:%M").replace(tzinfo=wien)
        except (ValueError, IndexError):
            wann = None
        (bleiben if wann is not None and wann > grenze else weg).append(z)
    if not weg:
        return [f"{listen.EINZEL_DATEI}: {len(bleiben)} Aktie(n) aus dieser Woche, nichts auszutragen."], False
    pfad.write_bytes(listen.einzel_csv(bleiben))
    return ([f"{listen.EINZEL_DATEI}: {len(weg)} einzeln ueberwachte Aktie(n) aus der alten Woche "
             f"ausgetragen ({', '.join(z[0] for z in weg)}); {len(bleiben)} bleiben."], True)


def gedaechtnis_filtern(daten, jetzt=None):
    """Das Melde-Gedaechtnis auf die Wochenregel bringen, wie der Waechter
    es beim Laden tut (breakout_watcher._gemeldet_filtern und load_state):
    Insider 30 Tage, alles andere bis zum Putz-Freitag, Fenster verfaellt
    mit dem Putz, die Warteliste der Luecken-Tage bleibt.
    Liefert (neue_daten, entfernt, geaendert)."""
    ny = zone()
    jetzt = jetzt.astimezone(ny) if jetzt else datetime.now(ny)
    grenze = putz_grenze(jetzt).date().isoformat()
    grenze_insider = (jetzt.date() - timedelta(days=INSIDER_TAGE)).isoformat()
    neu = dict(daten)
    gemeldet = daten.get("gemeldet", {})
    if isinstance(gemeldet, list):
        gemeldet = {k: str(daten.get("tag", "")) for k in gemeldet}
    behalten = {}
    for k, d in (gemeldet or {}).items():
        k_s, d_s = str(k), str(d)
        if INSIDER_MARKE in k_s:
            if d_s > grenze_insider:
                behalten[k_s] = d
        elif d_s > grenze:
            behalten[k_s] = d
    entfernt = len(gemeldet or {}) - len(behalten)
    geaendert = entfernt > 0
    neu["gemeldet"] = behalten
    if str(daten.get("fenster_tag") or "") <= grenze and daten.get("fenster"):
        neu["fenster"] = {}
        neu["fenster_tag"] = jetzt.date().isoformat()
        geaendert = True
    return neu, entfernt, geaendert


def gedaechtnis_regel(basis, jetzt):
    p = Path(basis) / GEDAECHTNIS
    if not p.exists():
        return [f"{GEDAECHTNIS}: nicht vorhanden (ok)."], False
    daten = _lies_json(p, None)
    if daten is None:
        return [f"{GEDAECHTNIS}: unlesbar, bleibt unangetastet."], False
    neu, entfernt, geaendert = gedaechtnis_filtern(daten, jetzt)
    if not geaendert:
        return [f"{GEDAECHTNIS}: nichts Altes ({len(neu.get('gemeldet', {}))} Eintraege)."], False
    _schreib_json(p, neu)
    return [f"{GEDAECHTNIS}: {entfernt} Eintraege der alten Woche entfernt, "
            f"{len(neu.get('gemeldet', {}))} bleiben."], True


def putz(basis=".", jetzt=None, listen_zeit=None):
    """Der ganze Wochenputz. Liefert (bericht, geaendert)."""
    b1, g1 = mappe_regel(basis, jetzt, listen_zeit)
    b2, g2 = gedaechtnis_regel(basis, jetzt)
    b3, g3 = einzel_regel(basis, jetzt)
    return b1 + b2 + b3, g1 or g2 or g3


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

def selbsttest():
    import tempfile
    ny = zone()
    fehler = []

    def p(name, ok, zusatz=""):
        print(f"  {'ok  ' if ok else 'FEHL'} {name}" + (f" — {zusatz}" if zusatz else ""))
        if not ok:
            fehler.append(name)

    print("Wochenputz, Selbsttest")
    fr_vorher = datetime(2026, 9, 18, 16, 1, tzinfo=ny)
    fr_nachher = datetime(2026, 9, 18, 16, 3, tzinfo=ny)
    so = datetime(2026, 9, 20, 12, 0, tzinfo=ny)
    p("Freitag 16:01 New York: der Putz der Vorwoche gilt",
      putz_grenze(fr_vorher) == datetime(2026, 9, 11, 16, 2, tzinfo=ny), putz_grenze(fr_vorher))
    p("Freitag 16:03 New York: der heutige Putz gilt",
      putz_grenze(fr_nachher) == datetime(2026, 9, 18, 16, 2, tzinfo=ny))
    p("Sonntag: der Freitag davor gilt",
      putz_grenze(so) == datetime(2026, 9, 18, 16, 2, tzinfo=ny))
    p("Ein Zeitpunkt in Wiener Zeit wird nach New York umgerechnet",
      putz_grenze(datetime(2026, 9, 18, 22, 3, tzinfo=ZoneInfo("Europe/Vienna")))
      == datetime(2026, 9, 18, 16, 2, tzinfo=ny))

    grenze = putz_grenze(so)
    alt = datetime(2026, 9, 13, 15, 14, tzinfo=timezone.utc)
    frisch = datetime(2026, 9, 20, 15, 0, tzinfo=timezone.utc)
    p("Die Liste vom Sonntag davor ist alt", liste_frisch(alt, grenze) is False)
    p("Die Liste vom Sonntag danach ist frisch", liste_frisch(frisch, grenze) is True)
    p("Ohne Datum keine Aussage", liste_frisch(None, grenze) is None)

    hier = Path(__file__).resolve().parent
    vorlage = hier / VORLAGE
    p("Die leere Vorlage liegt neben dem Skript", vorlage.exists())
    p("Die Vorlage gilt als leer", vorlage.exists() and mappe_leer(vorlage))
    echte = hier / MAPPE
    if echte.exists() and not mappe_leer(echte):
        p("Eine gefuellte Mappe gilt nicht als leer", True)
    p("Eine fehlende Datei gilt nicht als leer", not mappe_leer(hier / "gibtsnicht.xlsx"))

    with tempfile.TemporaryDirectory() as o:
        b = Path(o)
        shutil.copyfile(vorlage, b / VORLAGE)
        (b / MAPPE).write_bytes(b"nicht leer, egal was drinsteht")
        _schreib_json(b / FOKUSLISTE, {"gebaut_am": "x", "universum": 3,
                                       "aktien": {"AAA": {}, "BBB": {}}})
        gemerkt = {"fenster_tag": "2026-09-18", "fenster": {"AAA|Rectangle Top": "drin"},
                   "gemeldet": {"AAA|1": "2026-09-15", "BEST|BBB|2": "2026-09-18",
                                "INSIDER|CCC|pfad_a|0": "2026-09-01",
                                "INSIDER|DDD|pfad_a|0": "2026-08-01",
                                "GEWINN|2026-09-13|0": "2026-09-14",
                                "NEU|1": "2026-09-21"},
                   GAPGO_WARTEN: {"EEE": {"signal": "x"}}}
        _schreib_json(b / GEDAECHTNIS, gemerkt)
        for name in NIE_ANFASSEN:
            (b / name).write_text("unantastbar " + name, encoding="utf-8")

        _schreib_json(b / ALARM, {"stand": "x", "aktien": [
            {"ticker": "AAA", "punkte": [{"muster": "Inside Day", "kaufpunkt": 1.0}]}]})
        bericht, geaendert = putz(str(b), so, alt)
        p("Alte Liste: die Mappe wird zur leeren Vorlage",
          geaendert and (b / MAPPE).read_bytes() == vorlage.read_bytes())
        p("Alte Liste: die Alarm-Kaufpunkte sind geleert (Gerhard, 22.09.2026)",
          _lies_json(b / ALARM, {}).get("aktien") == [])
        fokus = _lies_json(b / FOKUSLISTE, {})
        p("Alte Liste: die Fokusliste ist leer", fokus.get("aktien") == {} and fokus.get("universum") == 0)
        g = _lies_json(b / GEDAECHTNIS, {})
        p("Gedaechtnis: Meldungen von vor dem Putz sind weg",
          "AAA|1" not in g["gemeldet"] and "BEST|BBB|2" not in g["gemeldet"]
          and "GEWINN|2026-09-13|0" not in g["gemeldet"])
        p("Gedaechtnis: eine Meldung nach dem Putz bleibt", g["gemeldet"].get("NEU|1") == "2026-09-21")
        p("Gedaechtnis: Insider bleiben 30 Tage, aeltere nicht",
          "INSIDER|CCC|pfad_a|0" in g["gemeldet"] and "INSIDER|DDD|pfad_a|0" not in g["gemeldet"])
        p("Gedaechtnis: das Fenster ist geleert, die Warteliste bleibt",
          g.get("fenster") == {} and g.get(GAPGO_WARTEN) == {"EEE": {"signal": "x"}})
        p("Nie angefasst: Positionen, Befunde, Warteliste, Logbuch, Radar, ntfy, Listen",
          all((b / n).read_text(encoding="utf-8") == "unantastbar " + n for n in NIE_ANFASSEN))
        bericht2, geaendert2 = putz(str(b), so, alt)
        p("Ein zweiter Lauf aendert nichts mehr", not geaendert2, "; ".join(bericht2))

        # Frische Liste: nichts wird geleert.
        (b / MAPPE).write_bytes(b"voll")
        _schreib_json(b / FOKUSLISTE, {"gebaut_am": "x", "universum": 1, "aktien": {"AAA": {}}})
        bericht3, geaendert3 = mappe_regel(str(b), so, frisch)
        p("Frische Liste: Mappe und Fokusliste bleiben",
          not geaendert3 and (b / MAPPE).read_bytes() == b"voll", "; ".join(bericht3))
        bericht4, geaendert4 = mappe_regel(str(b), so, None)
        p("Unbekanntes Datum: nichts wird geleert", not geaendert4, "; ".join(bericht4))
        # Vor dem Putz-Freitag: die Liste der laufenden Woche ist frisch.
        bericht5, geaendert5 = mappe_regel(str(b), fr_vorher, alt)
        p("Freitag vor 16:02: die Liste der laufenden Woche gilt noch", not geaendert5)
        # Fehlende Vorlage: nichts kaputt machen.
        (b / VORLAGE).unlink()
        bericht6, geaendert6 = mappe_regel(str(b), so, alt)
        p("Ohne Vorlage bleibt die Mappe, die Fokusliste wird trotzdem geleert",
          (b / MAPPE).read_bytes() == b"voll" and any("Vorlage" in z for z in bericht6))

        # O12 (Gerhard, 22.09.2026): Der Putz beendet die Einzelueberwachung
        # selbst. Der Putz-Freitag ist hier der 18.09.2026, 16:02 New York,
        # also der 18.09. um 22:02 Wiener Zeit.
        import listen
        (b / listen.EINZEL_DATEI).write_bytes(listen.einzel_csv([
            ("AAA", "Alpha", "2026-09-17 09:30"),      # vor dem Putz
            ("BBB", "Beta", "2026-09-19 08:00"),       # danach
            ("CCC", "Gamma", ""),                      # ohne Datum
        ]))
        bericht7, geaendert7 = einzel_regel(str(b), so)
        zeilen = listen.einzel_zeilen((b / listen.EINZEL_DATEI).read_bytes())
        p("O12: der Putz traegt die Aktien der alten Woche aus, die neue bleibt",
          geaendert7 and [z[0] for z in zeilen] == ["BBB"], "; ".join(bericht7))
        bericht8, geaendert8 = einzel_regel(str(b), so)
        p("O12: ein zweiter Lauf aendert nichts mehr", not geaendert8, "; ".join(bericht8))
        (b / listen.EINZEL_DATEI).unlink()
        p("O12: ohne die Datei ist nichts zu tun", einzel_regel(str(b), so) == ([], False))

    print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles bestanden.")
    return 1 if fehler else 0


def main():
    ap = argparse.ArgumentParser(description="Wochenputz nach Freitag 16:02 New York")
    ap.add_argument("--selbsttest", action="store_true")
    ap.add_argument("--nach-scan", action="store_true",
                    help="nur die Wochenregel auf die frisch gerechnete Mappe anwenden")
    ap.add_argument("--mappe", default=MAPPE, help="Dateiname der Mappe (mit --nach-scan)")
    ap.add_argument("--basis", default=".", help="Ordner mit den Dateien")
    ap.add_argument("--jetzt", default=None, help="Zeitpunkt mit Zeitzone fuer Pruefungen")
    ap.add_argument("--listen-datum", default=None,
                    help="Upload-Zeitpunkt der Wochenliste statt der GitHub-Abfrage")
    args = ap.parse_args()
    if args.selbsttest:
        return selbsttest()

    jetzt = datetime.fromisoformat(args.jetzt) if args.jetzt else None
    if args.listen_datum:
        listen_zeit = datetime.fromisoformat(args.listen_datum.replace("Z", "+00:00"))
    else:
        repo = os.environ.get("GITHUB_REPOSITORY", "mat-schmuck/heliot")
        try:
            listen_zeit = listen_datum(repo)
        except Exception as e:
            print(f"Listen-Datum nicht abfragbar ({type(e).__name__}: {e}).")
            listen_zeit = None
    if args.nach_scan:
        bericht, geaendert = mappe_regel(args.basis, jetzt, listen_zeit, mappe=args.mappe)
    else:
        bericht, geaendert = putz(args.basis, jetzt, listen_zeit)
    print("Wochenputz:" + (" geaendert" if geaendert else " nichts zu tun"))
    for zeile in bericht:
        print("  " + zeile)
    return 0


if __name__ == "__main__":
    sys.exit(main())
