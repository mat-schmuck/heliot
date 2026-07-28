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
from datetime import date, datetime, timezone
from pathlib import Path

ZUSTANDSDATEIEN = ["fortschritt.json", "radar_state.json", "watcher_state.json"]


# ---------------------------------------------------------------------------
# 1) Zustands-Aufräumer
# ---------------------------------------------------------------------------

def raeume_zustaende(basis=".", heute=None):
    """Setzt Zustandsdateien zurück, deren 'tag' nicht der heutige ist.
    Gibt einen Bericht zurück, was passiert ist."""
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
            bericht.append(f"{name}: unlesbar ({e}) — wird neu angelegt")
            pfad.write_text(json.dumps({"tag": heute, "gemeldet": []}, indent=2))
            continue

        if data.get("tag") != heute:
            alt = data.get("tag", "unbekannt")
            n_alt = len(data.get("gemeldet", data.get("erledigt", [])))
            pfad.write_text(json.dumps({"tag": heute, "gemeldet": []}, indent=2))
            bericht.append(f"{name}: zurückgesetzt (war vom {alt}, {n_alt} alte Einträge entfernt)")
        else:
            n = len(data.get("gemeldet", data.get("erledigt", [])))
            bericht.append(f"{name}: aktuell ({n} Einträge von heute, bleibt)")
    return bericht


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

    # Zustands-Aufräumer testen
    (Path(tmp) / "radar_state.json").write_text(json.dumps(
        {"tag": "2020-01-01", "gemeldet": ["A|+", "B|-", "C|+"]}))
    (Path(tmp) / "watcher_state.json").write_text(json.dumps(
        {"tag": date.today().isoformat(), "gemeldet": ["X|1|100"]}))
    bericht = raeume_zustaende(basis=tmp)
    print("Zustands-Aufräumer:")
    for z in bericht:
        print("  " + z)
    # radar (alt) muss zurückgesetzt sein, watcher (heute) muss bleiben
    radar = json.loads((Path(tmp) / "radar_state.json").read_text())
    watcher = json.loads((Path(tmp) / "watcher_state.json").read_text())
    assert radar["gemeldet"] == [] and radar["tag"] == date.today().isoformat()
    assert watcher["gemeldet"] == ["X|1|100"]
    print("  ✓ Alter Zustand zurückgesetzt, heutiger bleibt erhalten")

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
