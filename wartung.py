#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WARTUNG — Zustands-Aufräumer + täglicher Gesundheits-Check
==========================================================
Zwei Aufräum-Aufgaben in einem Modul:

1. ZUSTANDS-AUFRÄUMER
   Die Zustandsdateien (fortschritt.json, radar_state.json, watcher_state.json)
   sammeln über die Zeit alte Einträge an. Ohne Regel wächst da Müll, der
   irgendwann Fehlalarme (alter Eintrag blockiert neue Meldung) oder verpasste
   Meldungen verursacht. Hier: alles, was nicht vom heutigen Handelstag ist,
   wird beim ersten Lauf des Tages zurückgesetzt.

2. GESUNDHEITS-CHECK
   Bei so vielen beweglichen Teilen braucht es eine tägliche Morgenmeldung
   "alle Systeme laufen". Sonst merkt man erst, dass etwas still gestorben ist,
   wenn ein Signal ausbleibt. Der Check prüft die kritischen Punkte und pusht
   EINE Zusammenfassung.
"""

import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from config import CFG, letzter_putz_tag

ZUSTANDSDATEIEN = ["fortschritt.json", "radar_state.json", "watcher_state.json"]


# ---------------------------------------------------------------------------
# 1) Zustands-Aufräumer
# ---------------------------------------------------------------------------

def raeume_zustaende(basis=".", grenze=None, heute=None):
    """Setzt Zustandsdateien zurück, die ÄLTER sind als der letzte
    Freitags-Putz. Gibt einen Bericht zurück, was passiert ist.

    ACHTUNG — hier lagen ZWEI Fehler im ausgelieferten Modul, beide am
    28.07.2026 gefunden und von Gerhard zur Korrektur freigegeben:

    1. FALSCHER TAKT. Ursprünglich wurde jede Datei zurückgesetzt, deren
       'tag' nicht der heutige war, also TÄGLICH. Für dieses System ist
       das falsch und richtet echten Schaden an:
         * fortschritt.json führt die gesetzten TraderFox-Alarme. Täglich
           geleert, hielte der Bot jeden Morgen alles für unerledigt und
           setzte sämtliche Alarme neu — auch die bereits ausgelösten.
           Genau dieser Doppelsignal-Fehler ist am 27.07. passiert.
         * watcher_state.json führt, was diese WOCHE gemeldet wurde.
           Täglich geleert, meldete jede Aktie jeden Tag erneut — das
           'wilde Durcheinander', das ausdrücklich abgestellt wurde.
       Der Takt ist deshalb WÖCHENTLICH, passend zum Freitags-Putz.

    2. FALSCHER FELDNAME UND BAUART. Zurückgeschrieben wurde immer
       {'tag':…, 'gemeldet': []}. fortschritt.json heißt sein Feld aber
       'erledigt', und beim Wächter ist 'gemeldet' ein Verzeichnis, keine
       Liste. Beides wurde stillschweigend umgeschrieben. Jetzt bleiben
       Feldname und Bauart erhalten."""
    grenze = grenze or letzter_putz_tag()
    heute = heute or date.today().isoformat()
    bericht = []
    for name in ZUSTANDSDATEIEN:
        pfad = Path(basis) / name
        if not pfad.exists():
            bericht.append(f"{name}: nicht vorhanden (ok)")
            continue
        try:
            data = json.loads(pfad.read_text())
        except Exception as e:
            # NICHT überschreiben: Eine unlesbare Datei kann das Ergebnis
            # eines abgebrochenen Schreibvorgangs sein — dann ist der Inhalt
            # womöglich noch zu retten. Lieber melden als vernichten.
            bericht.append(f"{name}: unlesbar ({e}) — bleibt unangetastet")
            continue
        if not isinstance(data, dict):
            bericht.append(f"{name}: unerwarteter Aufbau — bleibt unangetastet")
            continue

        # Welches Feld führt die Einträge, und ist es Liste oder Verzeichnis?
        feld = "erledigt" if "erledigt" in data else "gemeldet"
        inhalt = data.get(feld)
        anzahl = len(inhalt) if isinstance(inhalt, (list, dict)) else 0
        tag = str(data.get("tag", ""))

        if tag and tag >= grenze:
            bericht.append(f"{name}: aktuell ({anzahl} Einträge seit dem "
                           f"Putz vom {grenze}, bleibt)")
            continue

        data["tag"] = heute
        data[feld] = {} if isinstance(inhalt, dict) else []
        pfad.write_text(json.dumps(data, indent=2))
        bericht.append(f"{name}: zurückgesetzt (war vom {tag or 'unbekannt'}, "
                       f"älter als der Putz vom {grenze}; {anzahl} alte "
                       f"Einträge entfernt, Feld '{feld}' erhalten)")
    bericht.extend(raeume_shakeout_warteliste(basis))
    return bericht


def raeume_shakeout_warteliste(basis=".", datei="shakeout_warteliste.json",
                               max_tage=None):
    """Die Warteliste aus Kapitel 10 aufräumen — aber NUR abgelaufene
    Einträge.

    Gerhard schreibt das ausdrücklich dazu: Diese Datei gehört in
    denselben wöchentlichen Rhythmus wie die anderen Zustandsdateien,
    darf aber nicht geleert werden. Ein Spring wartet bis zu 15
    Handelstage auf seinen Sekundärtest; wer die Liste am Freitag leert,
    verliert jede aktive Warteposition und damit genau die Signale, auf
    die das Verfahren hinarbeitet.

    Weg kommt deshalb nur, was seine Wartezeit überschritten hat."""
    if max_tage is None:
        max_tage = CFG["shakeout"]["sekundaertest_max_wartetage"]
    pfad = Path(basis) / datei
    if not pfad.exists():
        return [f"{datei}: nicht vorhanden (ok)"]
    try:
        data = json.loads(pfad.read_text(encoding="utf-8-sig"))
    except Exception as e:
        return [f"{datei}: unlesbar ({e}) — bleibt unangetastet"]
    if not isinstance(data, dict):
        return [f"{datei}: unerwarteter Aufbau — bleibt unangetastet"]

    abgelaufen = [t for t, e in data.items()
                  if isinstance(e, dict)
                  and e.get("tage_gewartet", 0) > max_tage]
    for t in abgelaufen:
        del data[t]
    if abgelaufen:
        pfad.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    return [f"{datei}: {len(data)} Warteposition(en) bleiben, "
            f"{len(abgelaufen)} abgelaufene entfernt (über {max_tage} Tage)"]


# ---------------------------------------------------------------------------
# 2) Gesundheits-Check
# ---------------------------------------------------------------------------

def sammle_gesundheit(checks):
    """checks: dict {name: (ok:bool, detail:str)}.
    Baut eine Zusammenfassung + Gesamtstatus."""
    zeilen = []
    alles_ok = True
    for name, (ok, detail) in checks.items():
        symbol = "OK" if ok else "FEHLER"
        if not ok:
            alles_ok = False
        zeilen.append(f"[{symbol}] {name}: {detail}")
    kopf = "✅ Alle Systeme laufen" if alles_ok else "⚠️ ACHTUNG — Problem erkannt"
    return kopf, "\n".join(zeilen), alles_ok


def baue_standard_checks(cache_stats=None, letzter_scan=None, versorgte_aktien=None,
                         gesetzte_alarme=None, stale_ticker=None,
                         actions_minuten=None, actions_limit_warnung=1700):
    """Baut die typischen Health-Checks aus den übergebenen Kennzahlen.
    Alle Argumente optional — was None ist, wird als 'nicht geprüft' geführt."""
    checks = {}

    if letzter_scan is not None:
        # letzter_scan als datetime; älter als 26h = verdächtig
        alter_h = (datetime.now(timezone.utc) - letzter_scan).total_seconds() / 3600
        checks["Letzter Scan"] = (alter_h < 26,
                                  f"vor {alter_h:.1f} h" + (" — zu lange her!" if alter_h >= 26 else ""))

    if versorgte_aktien is not None:
        gesamt, versorgt = versorgte_aktien
        quote = (versorgt / gesamt * 100) if gesamt else 0
        checks["Kursversorgung"] = (quote >= 95,
                                    f"{versorgt}/{gesamt} Aktien ({quote:.0f} %)")

    if stale_ticker is not None:
        n = len(stale_ticker)
        beispiel = (" z. B. " + ", ".join(stale_ticker[:5])) if stale_ticker else ""
        checks["Stale-Kurse"] = (n == 0, f"{n} hängende Kurse{beispiel}")

    if gesetzte_alarme is not None:
        checks["Alarme"] = (True, f"{gesetzte_alarme} gesetzt/aktiv")

    if cache_stats is not None:
        checks["Kurs-Cache"] = (True,
                                f"{cache_stats.get('trefferquote_pct', 0)} % Trefferquote, "
                                f"{cache_stats.get('echte_abrufe', 0)} echte Abrufe")

    if actions_minuten is not None:
        checks["GitHub-Minuten"] = (actions_minuten < actions_limit_warnung,
                                    f"{actions_minuten} min verbraucht"
                                    + (" — nähert sich dem Limit!" if actions_minuten >= actions_limit_warnung else ""))

    return checks


def push_gesundheit(topic, kopf, koerper, prioritaet="low"):
    """Sendet die Zusammenfassung an ntfy (eigenes Health-Topic, leise Priorität)."""
    import requests
    text = f"{datetime.now():%d.%m. %H:%M}\n{koerper}"
    try:
        r = requests.post(f"https://ntfy.sh/{topic}", data=text.encode("utf-8"),
                          headers={"Title": kopf.encode("utf-8"),
                                   "Priority": prioritaet,
                                   "Tags": "hospital"}, timeout=15)
        return r.status_code
    except Exception as e:
        print(f"Health-Push fehlgeschlagen: {e}")
        return None


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import tempfile, shutil
    tmp = tempfile.mkdtemp()

    # --- Zustands-Aufräumer: WÖCHENTLICH, nicht täglich -----------------
    grenze = letzter_putz_tag()
    vorwoche = (date.fromisoformat(grenze) - timedelta(days=3)).isoformat()
    seit_putz = (date.fromisoformat(grenze) + timedelta(days=1)).isoformat()

    # Steinalt -> muss weg
    (Path(tmp) / "radar_state.json").write_text(json.dumps(
        {"tag": vorwoche, "gemeldet": ["A|+", "B|-", "C|+"]}))
    # Aus DIESER Woche, aber NICHT von heute -> muss BLEIBEN. Genau hier lag
    # der Fehler: taeglich waere das geleert worden.
    (Path(tmp) / "fortschritt.json").write_text(json.dumps(
        {"tag": seit_putz, "erledigt": ["AAPL|1|100.00", "MSFT|1|400.00"]}))
    # Waechter fuehrt ein VERZEICHNIS, keine Liste -> Bauart muss bleiben
    (Path(tmp) / "watcher_state.json").write_text(json.dumps(
        {"tag": vorwoche, "gemeldet": {"X|1": vorwoche, "Y|2": vorwoche}}))

    bericht = raeume_zustaende(basis=tmp)
    print(f"Zustands-Aufräumer (Wochengrenze: Putz vom {grenze}):")
    for z in bericht:
        print("  " + z)

    radar = json.loads((Path(tmp) / "radar_state.json").read_text())
    fortschritt = json.loads((Path(tmp) / "fortschritt.json").read_text())
    watcher = json.loads((Path(tmp) / "watcher_state.json").read_text())

    assert radar["gemeldet"] == [], "steinalter Zustand muss geleert werden"
    assert fortschritt["erledigt"] == ["AAPL|1|100.00", "MSFT|1|400.00"], \
        "Eintrag aus DIESER Woche darf NICHT geleert werden (der alte Tagestakt)"
    assert "erledigt" in fortschritt and "gemeldet" not in fortschritt, \
        "Feldname 'erledigt' muss erhalten bleiben"
    assert watcher["gemeldet"] == {}, "alter Wächterzustand muss geleert werden"
    assert isinstance(watcher["gemeldet"], dict), \
        "Verzeichnis darf nicht zur Liste werden"
    print("  ✓ Nur ÄLTER als der Freitags-Putz wird geleert")
    print("  ✓ Gesetzte Alarme dieser Woche bleiben stehen (Doppelsignal-Fehler behoben)")
    print("  ✓ Feldname 'erledigt' und Bauart Verzeichnis bleiben erhalten")

    # Unlesbare Datei darf NICHT vernichtet werden
    (Path(tmp) / "radar_state.json").write_text("{kaputt")
    raeume_zustaende(basis=tmp)
    assert (Path(tmp) / "radar_state.json").read_text() == "{kaputt", \
        "unlesbare Datei muss unangetastet bleiben"
    print("  ✓ Unlesbare Datei bleibt unangetastet, statt überschrieben zu werden")

    # Gesundheits-Check testen — Normalfall
    checks = baue_standard_checks(
        cache_stats={"trefferquote_pct": 62.0, "echte_abrufe": 380},
        letzter_scan=datetime.now(timezone.utc),
        versorgte_aktien=(100, 100),
        gesetzte_alarme=35,
        stale_ticker=[],
        actions_minuten=900,
    )
    kopf, koerper, ok = sammle_gesundheit(checks)
    print(f"\nGesundheits-Check (Normalfall): {kopf}")
    for z in koerper.splitlines():
        print("  " + z)
    assert ok is True

    # Problemfall: Aktien nicht versorgt + stale Kurse
    checks2 = baue_standard_checks(
        versorgte_aktien=(100, 78),
        stale_ticker=["ABCD", "EFGH", "IJKL"],
        actions_minuten=1850,
    )
    kopf2, koerper2, ok2 = sammle_gesundheit(checks2)
    print(f"\nGesundheits-Check (Problemfall): {kopf2}")
    for z in koerper2.splitlines():
        print("  " + z)
    assert ok2 is False
    print("\n  ✓ Problemfall korrekt als FEHLER erkannt (Versorgung <95%, stale, Minuten-Limit)")

    shutil.rmtree(tmp)
    print("\nAlle Wartungs-Tests bestanden.")
