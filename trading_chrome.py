#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CHROME FÜRS TRADEN — ein eigenes Profil mit Debug-Anschluss
===========================================================
Damit degiro_order.py das Bedienfeld ausfüllen kann, muss Chrome einen
Debug-Anschluss offen haben. Chrome lässt das seit Version 136 im
NORMALEN Profil nicht mehr zu — eine Sicherheitsmaßnahme, die man nicht
umgehen soll und die hier auch niemand umgehen muss.

Also bekommt das Traden ein eigenes Chrome-Profil. Es liegt getrennt vom
Alltagsprofil, hat eigene Cookies und eine eigene Anmeldung.

WAS MATHIAS EINMAL SELBST MACHT
    Beim ersten Start ist das Profil leer und DEGIRO fragt nach der
    Anmeldung. Die tippt AUSSCHLIESSLICH er. Dieses Programm kennt
    weder Benutzername noch Kennwort noch den Schlüssel für die
    Bestätigung, speichert nichts davon und fragt auch nie danach.
    Danach bleibt die Anmeldung im Profil liegen wie in jedem Browser.

Aufruf:
    python trading_chrome.py            starten (oder melden, dass es läuft)
    python trading_chrome.py --status   nachsehen, ob alles bereit ist
    python trading_chrome.py --wo       Pfade anzeigen
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ANSCHLUSS = 9222
STARTSEITE = "https://trader.degiro.nl/trader/#/markets"

# Getrennt vom Alltagsprofil. Ein eigener Ordner, damit eine kaputte
# Erweiterung oder ein voller Zwischenspeicher im Alltagsbrowser das
# Traden nicht mitreißt.
#
# BEWUSST NICHT UNTER AppData: Wird das Programm aus einer Umgebung mit
# App-Container gestartet (Claude-Desktop läuft als Paket), landen
# AppData-Schreibzugriffe VIRTUALISIERT in einer Kopie. Mathias meldet
# sich dann an und das Programm sieht trotzdem ein leeres Profil. Am
# 30.07.2026 nachgemessen: unter AppData virtualisiert, im Benutzer-
# ordner nicht.
PROFIL = os.path.join(os.path.expanduser("~"),
                      ".pattern-scanner", "chrome-trading")

CHROME_ORTE = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.join(os.environ.get("LOCALAPPDATA", ""),
                 r"Google\Chrome\Application\chrome.exe"),
]


def chrome_finden() -> str:
    """Chrome suchen — erst an den üblichen Orten, dann in der
    Registrierung. Ohne Fund bricht alles Weitere ohnehin ab."""
    for p in CHROME_ORTE:
        if p and os.path.isfile(p):
            return p
    try:
        import winreg
        for wurzel in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(
                        wurzel,
                        r"SOFTWARE\Microsoft\Windows\CurrentVersion"
                        r"\App Paths\chrome.exe") as k:
                    p = winreg.QueryValue(k, None)
                    if p and os.path.isfile(p):
                        return p
            except OSError:
                continue
    except ImportError:
        pass
    sys.exit("Chrome nicht gefunden. Bitte den Pfad zu chrome.exe in "
             "CHROME_ORTE eintragen.")


def laeuft() -> dict:
    """Antwortet der Debug-Anschluss? Gibt die Browserkennung zurück."""
    try:
        with urllib.request.urlopen(
                f"http://localhost:{ANSCHLUSS}/json/version", timeout=2) as a:
            return json.load(a)
    except (urllib.error.URLError, OSError, ValueError):
        return {}


def offene_seiten() -> list:
    """Die offenen Registerkarten — daran sieht man, ob DEGIRO offen ist."""
    try:
        with urllib.request.urlopen(
                f"http://localhost:{ANSCHLUSS}/json/list", timeout=2) as a:
            return [s for s in json.load(a) if s.get("type") == "page"]
    except (urllib.error.URLError, OSError, ValueError):
        return []


def starten() -> int:
    if laeuft():
        print(f"Chrome mit Debug-Anschluss {ANSCHLUSS} läuft bereits.")
        return status()

    exe = chrome_finden()
    os.makedirs(PROFIL, exist_ok=True)
    neu = not os.path.exists(os.path.join(PROFIL, "Default"))

    subprocess.Popen(
        [exe,
         f"--remote-debugging-port={ANSCHLUSS}",
         f"--user-data-dir={PROFIL}",
         "--no-first-run",
         "--no-default-browser-check",
         STARTSEITE],
        close_fds=True)

    for _ in range(30):                       # bis zu 15 Sekunden warten
        time.sleep(0.5)
        if laeuft():
            break
    else:
        print("Chrome ist gestartet, meldet sich am Debug-Anschluss aber "
              "nicht. Bitte einmal 'python trading_chrome.py --status'.")
        return 1

    print("Chrome fürs Traden läuft.")
    if neu:
        print()
        print("Das Profil ist NEU und daher noch nicht angemeldet.")
        print("Bitte melde dich jetzt selbst bei DEGIRO an — ich sehe "
              "deine Zugangsdaten nicht und frage auch nie danach.")
        print("Die Anmeldung bleibt danach in diesem Profil liegen.")
    return status()


def status() -> int:
    v = laeuft()
    if not v:
        print(f"Debug-Anschluss {ANSCHLUSS}: keine Antwort. "
              f"Bitte 'python trading_chrome.py' zum Starten.")
        return 1
    print(f"Debug-Anschluss {ANSCHLUSS}: bereit ({v.get('Browser', '?')})")

    seiten = offene_seiten()
    degiro = [s for s in seiten if "degiro" in s.get("url", "").lower()]
    if not degiro:
        print(f"{len(seiten)} Registerkarte(n) offen, aber keine mit "
              f"DEGIRO. Bitte trader.degiro.nl öffnen.")
        return 1
    print(f"DEGIRO offen: {degiro[0].get('url', '')[:70]}")

    # Angemeldet oder nicht: Die Anmeldeseite trägt /login in der Adresse.
    if "/login" in degiro[0].get("url", "").lower():
        print("Noch NICHT angemeldet — bitte selbst anmelden.")
        return 1
    print("Alles bereit für degiro_order.py.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Chrome mit eigenem Profil und Debug-Anschluss fürs "
                    "Traden starten.")
    ap.add_argument("--status", action="store_true",
                    help="Nur nachsehen, ob alles bereit ist.")
    ap.add_argument("--wo", action="store_true",
                    help="Pfade anzeigen und sonst nichts tun.")
    args = ap.parse_args()

    if args.wo:
        print(f"Chrome:  {chrome_finden()}")
        print(f"Profil:  {PROFIL}")
        print(f"Anschluss: {ANSCHLUSS}")
        return 0
    if args.status:
        return status()
    return starten()


if __name__ == "__main__":
    sys.exit(main())
