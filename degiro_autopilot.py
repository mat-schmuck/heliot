#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AUTOPILOT — vom Alarm bis zum Kontrollbildschirm, drei Mal
===========================================================
Der Chartwächter läuft bei GitHub in der Cloud, DEGIRO läuft auf Mathias'
PC. Dieses Programm verbindet beide: Es hört den ntfy-Kanal mit, auf dem
die Meldungen ohnehin ankommen, und stellt bei einer volumenbestätigten
Meldung den Auftrag fertig hin. Bestätigt wird nie automatisch.

DER ABLAUF
    1. Meldung mit "Vol BESTÄTIGT" kommt an
       → Stufe "kauf" wird vorbereitet, Limit = Kaufpunkt aus der Meldung
       → Signalton, Chrome kommt nach vorn, Auftrag wird vorgelesen
       → Mathias bestätigt oder verwirft. Beides ist in Ordnung.
    2. Die Stückzahl im Depot steigt → der Kauf wurde ausgeführt
       → Stufe "stop" wird vorbereitet, Stopkurs aus derselben Meldung
       → Signalton, vorlesen, Mathias bestätigt
    3. Der Kurs erreicht das Ziel aus der Meldung
       → Stufe "ziel" wird vorbereitet
       → Signalton, vorlesen, Mathias bestätigt

    Schritt 3 überwacht dieses Programm SELBST über den Yahoo-Strom
    (yahoo_ws.py), nicht der Wächter in der Cloud: Der weiß nicht, ob
    gekauft wurde, und kennt den Ausführungskurs nicht.

WARUM NICHT EINE EINZIGE VERKNÜPFTE ORDER
    DEGIRO kennt keine verbundenen Aufträge. Stop und Ziel wären zwei
    Verkäufe auf DIESELBEN Stücke. Also geht der Stop in den Markt und
    das Ziel wird hier überwacht.

IMMER NUR EIN AUFTRAG OFFEN
    Solange ein Kontrollbildschirm auf Mathias wartet, wird KEIN
    weiterer vorbereitet — sonst würde der wartende Auftrag ungefragt
    überschrieben. Neue Meldungen warten in der Schlange.

DAS TOPIC IST EIN GEHEIMNIS
    Es wird aus der Umgebungsvariablen NTFY_TOPIC gelesen, genau wie
    beim Wächter. Es steht in keiner Datei dieses Verzeichnisses und
    wird nirgends ausgegeben.

Aufruf:
    python trading_chrome.py           einmal, und dort anmelden
    python degiro_autopilot.py         mithören und vorbereiten
    python degiro_autopilot.py --trocken   alles außer dem Eintragen
    python degiro_autopilot.py --probe "<Meldungstext>"   Auswertung testen
"""

import argparse
import json
import os
import re
import sys
import threading
import time
import urllib.request

import degiro_order as do

ZUSTANDSDATEI = os.path.join(os.path.expanduser("~"),
                             ".pattern-scanner", "autopilot.json")
NTFY_BASIS = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")

BESTANDSTAKT = 20.0        # Sekunden zwischen zwei Blicken ins Depot
ZIELTAKT = 2.0             # Sekunden zwischen zwei Blicken auf den Kurs


# ---------------------------------------------------------------------------
# Meldungen auswerten
# ---------------------------------------------------------------------------

# Aufbau einer Meldung (breakout_watcher.format_treffer):
#     1. AXGN (AxoGen Inc); Flat Base
#     Kaufpunkt 42.50, Kurs 42.80 (+0.7%); Vol BESTÄTIGT, 35 % über Ø50
#     Stop 40.20, Risk 6.5%; Ziel 48.50 (+13.3%)
# Die Nummer steht nur da, wenn mehrere Aktien in einer Meldung sind.
MELDUNG = re.compile(
    r"(?:^|\n)\s*(?:\d+\.\s*)?"
    r"(?P<ticker>[A-Z][A-Z0-9.\-]{0,7})\s*"
    r"(?:\((?P<firma>[^)]*)\))?\s*;[^\n]*\n"
    r"\s*Kaufpunkt\s+(?P<kaufpunkt>[\d.]+)\s*,\s*Kurs\s+(?P<kurs>[\d.]+)"
    r"[^\n]*?;\s*Vol\s+(?P<vol>BESTÄTIGT|NICHT bestätigt|nicht bewertbar)"
    r"[^\n]*"
    r"(?:\n\s*Stop\s+(?P<stop>[\d.]+)\s*,\s*Risk[^\n;]*"
    r"(?:;\s*Ziel\s+(?P<ziel>[\d.]+))?)?",
    re.MULTILINE)


def signale_aus_text(text: str) -> list:
    """Alle volumenbestätigten Kaufpunkte aus einer Push-Meldung.

    Unbestätigte werden übergangen — nach Mathias' Vorgabe wird nur auf
    bestätigte Meldungen hin etwas vorbereitet. Der Nachtrag ("Vol jetzt
    bestätigt") hat denselben Aufbau und wird deshalb mitgelesen; genau
    dafür ist er da."""
    ergebnis = []
    for m in MELDUNG.finditer(text or ""):
        if m.group("vol") != "BESTÄTIGT":
            continue
        if not m.group("stop") or not m.group("ziel"):
            # Ohne Stop und Ziel wäre nur der Kauf möglich, die Absicherung
            # nicht. Das wird gemeldet, aber nicht vorbereitet.
            print(f"  {m.group('ticker')}: Stop oder Ziel fehlt in der "
                  f"Meldung — wird übergangen.")
            continue
        ergebnis.append({
            "ticker": m.group("ticker"),
            "firma": (m.group("firma") or "").strip(),
            "kaufpunkt": float(m.group("kaufpunkt")),
            "stop": float(m.group("stop")),
            "ziel": float(m.group("ziel")),
        })
    return ergebnis


# ---------------------------------------------------------------------------
# Zustand über Neustarts hinweg
# ---------------------------------------------------------------------------

def zustand_laden() -> dict:
    try:
        with open(ZUSTANDSDATEI, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def zustand_sichern(z: dict) -> None:
    """Der Zustand überlebt einen Neustart.

    Ohne ihn wäre nach einem Absturz nicht mehr bekannt, für welche
    Aktie noch ein Stop fehlt — und ein gekaufter Posten stünde
    ungesichert da."""
    os.makedirs(os.path.dirname(ZUSTANDSDATEI), exist_ok=True)
    with open(ZUSTANDSDATEI, "w", encoding="utf-8") as f:
        json.dump(z, f, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------------------
# Mithören
# ---------------------------------------------------------------------------

def mithoeren(topic: str, ablage: list, sperre: threading.Lock) -> None:
    """Dauerverbindung zum ntfy-Kanal, Zeile für Zeile JSON.

    Bricht die Leitung ab, wird neu verbunden — eine Nacht ohne
    Verbindung darf nicht bedeuten, dass am nächsten Morgen nichts mehr
    ankommt."""
    adresse = f"{NTFY_BASIS}/{topic}/json"
    while True:
        try:
            with urllib.request.urlopen(adresse, timeout=None) as strom:
                print("Kanal verbunden, warte auf Meldungen.")
                for zeile in strom:
                    try:
                        d = json.loads(zeile.decode("utf-8"))
                    except ValueError:
                        continue
                    if d.get("event") != "message":
                        continue
                    text = (d.get("title", "") + "\n"
                            + d.get("message", ""))
                    with sperre:
                        ablage.append(text)
        except Exception as e:
            print(f"Kanal unterbrochen ({type(e).__name__}) — neuer "
                  f"Versuch in 10 Sekunden.")
            time.sleep(10)


def melden(text: str) -> None:
    """Hörbar melden, dass etwas auf Mathias wartet.

    Er sieht den Bildschirm nicht; ein stiller Auftrag wäre nutzlos."""
    print("\a" + text, flush=True)
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Ablauf
# ---------------------------------------------------------------------------

def kontrolle_offen(seite) -> bool:
    return seite.query_selector(do.ANKER["kontrolle"]) is not None


def portfolioseite(ktx, vorhandene):
    """Eine eigene Registerkarte fürs Depot.

    Getrennt von der Handelsansicht: Sonst müsste der Autopilot alle
    zwanzig Sekunden Mathias' Ansicht wegschalten, womöglich mitten in
    seiner Entscheidung."""
    if vorhandene and not vorhandene.is_closed():
        return vorhandene
    s = ktx.new_page()
    s.goto("https://trader.degiro.nl/trader/#/portfolio", wait_until="load")
    s.wait_for_timeout(4000)
    return s


def hauptlauf(args) -> int:
    topic = os.environ.get("NTFY_TOPIC")
    if not topic and not args.trocken:
        sys.exit("Bitte NTFY_TOPIC setzen — ohne Kanal kein Mithören.")

    zustand = zustand_laden()
    ablage, sperre = [], threading.Lock()
    if args.testmeldung:
        # Eine erfundene Meldung, als wäre sie über den Kanal gekommen.
        # Damit lässt sich der ganze Ablauf prüfen, ohne auf einen
        # echten Ausbruch zu warten.
        ablage.append(args.testmeldung)
        print("Prüfmeldung eingespeist.")
    if topic:
        threading.Thread(target=mithoeren, args=(topic, ablage, sperre),
                         daemon=True).start()

    p, browser, seite = do.verbinde()
    ktx = browser.contexts[0]
    depotseite = None
    letzter_bestand = 0.0
    strom = None

    print(f"Autopilot läuft{' (trocken)' if args.trocken else ''}. "
          f"{len(zustand)} Vorgang/Vorgänge aus dem letzten Lauf.")
    try:
        while True:
            # --- 1. Neue Meldungen -------------------------------------
            with sperre:
                neue, ablage[:] = list(ablage), []
            for text in neue:
                for s in signale_aus_text(text):
                    t = s["ticker"]
                    # Abgeschlossene oder gescheiterte Vorgänge stehen
                    # einem neuen Signal nicht im Weg — sonst wäre eine
                    # Aktie nach dem ersten Durchlauf für immer gesperrt.
                    if zustand.get(t, {}).get("phase") not in (
                            None, "fertig", "fehler"):
                        print(f"{t}: läuft schon, Meldung übergangen.")
                        continue
                    s["phase"] = "neu"
                    zustand[t] = s
                    zustand_sichern(zustand)
                    print(f"{t}: bestätigtes Signal, Kaufpunkt "
                          f"{s['kaufpunkt']}, Stop {s['stop']}, "
                          f"Ziel {s['ziel']}.")

            # --- 2. Fällige Aufträge vorbereiten -----------------------
            # Nur einer auf einmal: Ein wartender Kontrollbildschirm
            # gehört Mathias, den überschreibt niemand.
            if not kontrolle_offen(seite):
                for t, s in list(zustand.items()):
                    auftrag = None
                    # Verkauft wird NUR, was zu diesem Signal gekauft
                    # wurde — nicht der ganze Bestand. Sonst würde ein
                    # Posten, den Mathias längst vorher hielt, vom
                    # Autopilot mitverkauft (30.07.2026 aufgefallen).
                    if s["phase"] == "neu":
                        auftrag = ("kauf", dict(limit=s["kaufpunkt"]))
                    elif s["phase"] == "gekauft":
                        auftrag = ("stop", dict(stop=s["stop"],
                                                anzahl=s.get("stueck")))
                    elif s["phase"] == "ziel_erreicht":
                        auftrag = ("ziel", dict(limit=s["ziel"],
                                                anzahl=s.get("stueck")))
                    if not auftrag:
                        continue
                    stufe, zusatz = auftrag
                    if args.trocken:
                        print(f"[trocken] {t}: Stufe {stufe} {zusatz}")
                    else:
                        try:
                            do.auftrag_vorbereiten(
                                seite, t, s.get("firma", ""), stufe, **zusatz)
                        except SystemExit as e:
                            melden(f"{t}: Stufe {stufe} abgebrochen — {e}")
                            s["phase"] = "fehler"
                            zustand_sichern(zustand)
                            break
                    s["phase"] = {"kauf": "wartet_auf_kauf",
                                  "stop": "gesichert",
                                  "ziel": "fertig"}[stufe]
                    if stufe == "kauf":
                        # Der Stand VOR der Ausführung — daran wird
                        # später erkannt, dass wirklich gekauft wurde.
                        depotseite = portfolioseite(ktx, depotseite)
                        s["bestand_vorher"] = do.depotbestaende(
                            depotseite).get(t, 0)
                    zustand_sichern(zustand)
                    melden(f"{t}: Auftrag ({stufe}) steht — bitte in "
                           f"Chrome bestätigen oder verwerfen.")
                    break                    # nur einer auf einmal

            # --- 3. Wurde ein Kauf ausgeführt? -------------------------
            warten = [t for t, s in zustand.items()
                      if s["phase"] == "wartet_auf_kauf"]
            if warten and time.time() - letzter_bestand > BESTANDSTAKT:
                letzter_bestand = time.time()
                depotseite = portfolioseite(ktx, depotseite)
                depotseite.reload(wait_until="load")
                depotseite.wait_for_timeout(3000)
                bestand = do.depotbestaende(depotseite)
                for t in warten:
                    jetzt = bestand.get(t, 0)
                    vorher = zustand[t].get("bestand_vorher", 0)
                    if jetzt > vorher:
                        zustand[t]["phase"] = "gekauft"
                        zustand[t]["stueck"] = jetzt - vorher
                        zustand_sichern(zustand)
                        melden(f"{t}: Kauf ausgeführt ({jetzt - vorher} "
                               f"Stück) — der Schutzstop wird vorbereitet.")

            # --- 4. Kursziel überwachen --------------------------------
            beobachtet = [t for t, s in zustand.items()
                          if s["phase"] == "gesichert"]
            if beobachtet:
                strom = kursstrom(strom, beobachtet)
                for t in beobachtet:
                    kurs = letzter_kurs(strom, t)
                    if kurs and kurs >= zustand[t]["ziel"]:
                        zustand[t]["phase"] = "ziel_erreicht"
                        zustand_sichern(zustand)
                        melden(f"{t}: Ziel {zustand[t]['ziel']} erreicht "
                               f"(Kurs {kurs:.2f}) — Verkauf wird "
                               f"vorbereitet.")
            time.sleep(ZIELTAKT)
    except KeyboardInterrupt:
        print("\nAutopilot beendet. Der Zustand ist gesichert.")
        return 0
    finally:
        try:
            p.stop()
        except Exception:
            pass


def kursstrom(vorhandener, ticker: list):
    """Den Yahoo-Strom für die überwachten Aktien offen halten.

    Derselbe Strom, den der Wächter benutzt — kein Schlüssel nötig, und
    jede Kursmeldung kommt in Echtzeit. Die Liste ändert sich, sobald
    eine Aktie dazukommt oder verkauft ist; dann wird neu verbunden."""
    gewuenscht = sorted(ticker)
    if vorhandener is not None and vorhandener[1] == gewuenscht:
        return vorhandener
    try:
        import yahoo_ws
        from kurs_cache import KursCache
    except ImportError as e:
        print(f"Kursstrom nicht verfügbar ({e}) — das Ziel kann nicht "
              f"überwacht werden.")
        return None
    if vorhandener is not None:
        try:
            vorhandener[0].stop()
        except Exception:
            pass
    cache = KursCache(stale_pro_quelle={"yahoo_ws": 900})
    ws = yahoo_ws.YahooWebSocket(cache)
    if not ws.start(gewuenscht):
        return None
    print(f"Kursstrom für {', '.join(gewuenscht)} offen.")
    return (ws, gewuenscht, cache)


def letzter_kurs(strom, ticker: str):
    """Der zuletzt gestromte Kurs — oder None, wenn noch keiner kam."""
    if not strom:
        return None
    wert = strom[2]._store.get(ticker.upper())
    return wert.preis if wert and wert.preis else None


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Hört den ntfy-Kanal mit und stellt DEGIRO-Aufträge "
                    "fertig hin. Bestätigt wird nie automatisch.")
    ap.add_argument("--trocken", action="store_true",
                    help="Alles außer dem Eintragen in DEGIRO.")
    ap.add_argument("--probe", metavar="TEXT",
                    help="Nur die Auswertung einer Meldung zeigen und "
                         "beenden. Rührt DEGIRO nicht an.")
    ap.add_argument("--testmeldung", metavar="TEXT",
                    help="Diesen Text beim Start einspeisen, als wäre er "
                         "über den Kanal gekommen. Zum Durchspielen.")
    args = ap.parse_args()

    if args.probe:
        gefunden = signale_aus_text(args.probe)
        print(f"{len(gefunden)} bestätigte(s) Signal(e):")
        for s in gefunden:
            print(f"  {s['ticker']} ({s['firma']}): Kaufpunkt "
                  f"{s['kaufpunkt']}, Stop {s['stop']}, Ziel {s['ziel']}")
        return 0
    return hauptlauf(args)


if __name__ == "__main__":
    sys.exit(main())
