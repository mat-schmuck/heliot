#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WACHHALTEN: die Heliot-App auf Streamlit Community Cloud wach halten
====================================================================
Mathias' Auftrag vom 13.09.2026. Streamlit legt jede App schlafen, die
zwoelf Stunden ohne Besuch war ("All apps without traffic for 12 hours go
to sleep"), und zeigt dann eine englische Schlafseite mit dem Knopf
"Yes, get this app back up!", den wir weder umbenennen noch abschalten
koennen. Deshalb besucht dieser Lauf die App alle vier Stunden mit einem
echten Browser (Playwright, Chromium), so wie ein Mensch am iPhone.

WARUM EIN ECHTER BROWSER: Ein einfacher Aufruf der Adresse (curl,
cron-job.org) bekommt nur eine Weiterleitung auf share.streamlit.io und
kommt nie bei der App an (gemessen 13.09.2026: 303 auf
share.streamlit.io/-/auth/app, dann wieder 303). Erst der Browser laeuft
die Anmeldung durch, oeffnet die Seite samt Websocket und zaehlt als
Besucher.

WAS GEMESSEN WIRD: Jeder Lauf schreibt, ob die App WACH war oder SCHLIEF
und geweckt werden musste (samt Dauer). Steht ueber zwei Tage nie
"schlief", haelt der Besuch die App wach. Steht es doch, reicht der
Besuch nicht, und der Abstand muss kuerzer werden.

Aufruf:
  python wachhalten.py               besucht die App, druckt den Befund
  python wachhalten.py --sichtbar    mit sichtbarem Browserfenster (nur lokal)
"""

import re
import sys
import time
from datetime import datetime, timezone

URL = "https://heliot.streamlit.app/"
SCHLAF_TEXT = "gone to sleep"
WECK_KNOPF = re.compile(r"get this app back up", re.I)
APP_TITEL = "Chart-Screening-Tool"


def besuch(url=URL, kopflos=True, halten_s=20):
    """Oeffnet die App, weckt sie bei Bedarf, haelt die Sitzung halten_s
    Sekunden und gibt (befund, titel, rahmen) zurueck."""
    from playwright.sync_api import sync_playwright
    t0 = time.time()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=kopflos)
        seite = browser.new_page()
        seite.goto(url, wait_until="domcontentloaded", timeout=90_000)
        seite.wait_for_timeout(8_000)
        text = seite.inner_text("body")
        if SCHLAF_TEXT in text:
            seite.get_by_role("button", name=WECK_KNOPF).click()
            # Das Wecken dauert eine halbe Minute bis wenige Minuten.
            geweckt = False
            for _ in range(60):
                seite.wait_for_timeout(3_000)
                if APP_TITEL in seite.title() or len(seite.frames) > 1:
                    geweckt = True
                    break
            befund = (f"schlief, geweckt nach {time.time() - t0:.0f} s" if geweckt
                      else f"schlief, nach {time.time() - t0:.0f} s noch nicht wach")
        else:
            befund = "wach"
        seite.wait_for_timeout(halten_s * 1000)
        titel, rahmen = seite.title(), len(seite.frames)
        browser.close()
    return befund, titel, rahmen


def main() -> int:
    kopflos = "--sichtbar" not in sys.argv
    jetzt = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    try:
        befund, titel, rahmen = besuch(kopflos=kopflos)
    except Exception as e:  # noqa
        print(f"{jetzt}: FEHLER {type(e).__name__}: {e}")
        return 1
    print(f"{jetzt}: {befund}; Titel {titel!r}; Rahmen {rahmen}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
