#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TRADERFOX ALARM-BOT  (gehärtete Version 2.0)
============================================
Setzt die Kaufpunkte aus kaufpunkte.xlsx als Preis-Alarme im TraderFox
Trading-Desk (desk.traderfox.com).

WAS DIESE VERSION ROBUST MACHT
------------------------------
1. SELEKTOR-KARTE     Jedes Bedienelement hat mehrere Erkennungswege. Fällt einer
                      aus, greift der nächste. Alles steht gebündelt in SELEKTOREN
                      ganz oben — ändert TraderFox etwas, wird NUR dort angepasst.
2. RETRIES            Jeder Schritt wird bis zu 3× versucht, mit Pause dazwischen.
                      Lahme Ladezeiten und Aussetzer fangen sich damit von selbst.
3. SESSION-SPEICHER   Der Login wird in session.json gespeichert und beim nächsten
                      Lauf wiederverwendet. Weniger Logins = weniger Angriffsfläche.
4. VERIFIKATION       Nach jedem Save wird geprüft, ob der Alarm wirklich in der
                      Liste steht. Kein blindes "hab geklickt, wird schon".
5. WIEDERAUFNAHME     fortschritt.json merkt sich erledigte Alarme. Bricht der Lauf
                      ab, macht der nächste dort weiter statt von vorn.
6. DOPPELTE VERMEIDEN Bestehende Alarme werden gelesen; identische Preise werden
                      übersprungen statt doppelt angelegt.
7. SELBSTDIAGNOSE     Bei jedem Fehler: Screenshot + HTML-Auszug + Liste aller
                      sichtbaren Felder/Buttons in ./debug/. Damit ist eine
                      Reparatur eine Sache von Minuten statt Raten.
8. SELBSTTEST         --selbsttest prüft nur, ob alle Bedienelemente gefunden
                      werden — ohne einen einzigen Alarm anzufassen. Nach jedem
                      TraderFox-Update einmal laufen lassen, dann weißt du sofort,
                      ob noch alles sitzt.

AUFRUF
------
  export TRADERFOX_USER="deine@mail"
  export TRADERFOX_PASS="dein_passwort"

  python traderfox_alarm_bot.py --selbsttest              # Gesundheitscheck, ändert nichts
  python traderfox_alarm_bot.py kaufpunkte.xlsx --limit 2 --sichtbar   # Testlauf
  python traderfox_alarm_bot.py kaufpunkte.xlsx           # Echtlauf (nur Muster-Treffer)
  python traderfox_alarm_bot.py kaufpunkte.xlsx --alle    # inkl. Fallback-Level
  python traderfox_alarm_bot.py kaufpunkte.xlsx --neu     # Fortschritt ignorieren, alles neu

INSTALLATION
------------
  pip install playwright pandas openpyxl
  playwright install chromium
"""

import argparse
import json
import os
import random
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    sys.exit("Bitte installieren: pip install playwright && playwright install chromium")

DESK_URL = "https://desk.traderfox.com"
DEBUG_DIR = Path("debug")
SESSION_FILE = Path("session.json")
FORTSCHRITT_FILE = Path("fortschritt.json")


# ===========================================================================
# SELEKTOR-KARTE  —  HIER wird angepasst, wenn TraderFox das Design ändert.
# Jeder Eintrag ist eine Liste von Erkennungswegen, die der Reihe nach
# probiert werden. Der erste sichtbare Treffer gewinnt.
# Typen: "text" (sichtbarer Text, Regex), "placeholder" (Feld-Platzhalter),
#        "role" (Button mit Beschriftung), "css" (CSS-Selektor)
# ===========================================================================

SELEKTOREN = {
    "cookie_ablehnen": [
        ("css", "#maintfcookie-reject-all"),
        ("text", r"^\s*Nur Notwendige\s*$"),
        ("css", "[id$='-reject-all']"),
    ],
    # ACHTUNG: Das Desk enthaelt mehrere Elemente mit dem blossen Text "Login"
    # (Broker-Balken, comdirect, finanzen.net zero, CAPTRADER). Die oeffnen den
    # Broker-Verknuepfungsdialog, NICHT den Benutzer-Login. Darum ausschliesslich
    # die eindeutigen IDs verwenden und keine breiten Text-Fallbacks.
    "login_oeffnen": [
        ("css", "#login-ico"),
        ("css", ".login-holder .login"),
    ],
    # Der Dialog gilt nur als offen, wenn man wirklich tippen kann.
    # '.login-popup' steckt dauerhaft im DOM und galt zeitweise als sichtbar,
    # obwohl keine Felder da waren - dann hielt der Bot sich faelschlich fuer
    # ausgeloggt, obwohl die gespeicherte Sitzung laengst griff.
    "login_dialog": [
        ("css", "#password01"),
        ("css", ".login-popup input[type='password']"),
    ],
    "login_email": [
        ("css", "#email02"),
        ("css", ".login-popup input[type='email']"),
    ],
    "login_passwort": [
        ("css", "#password01"),
        ("css", ".login-popup input[type='password']"),
    ],
    "login_absenden": [
        ("css", "#login-button"),
        ("css", ".login-popup button[type='submit']"),
    ],
    "suchfeld": [
        ("placeholder", r"Suchbegriff"),
        ("placeholder", r"Suchbegriff, WKN, ISIN"),
        ("placeholder", r"WKN|ISIN"),
        ("css", "input[type='search']"),
    ],
    "kontextmenue_alarm": [
        ("text", r"Alarm hinzufügen"),
        ("text", r"Alarm\s*erstellen|Neuer\s*Alarm.*hinzufügen"),
    ],
    "alarm_dialog": [
        ("text", r"Alarm-?Konfiguration"),
        ("text", r"PREIS-?ALARM"),
    ],
    "neuer_alarm_label": [
        ("text", r"\+\s*Neuer Alarm"),
        ("text", r"Neuer Alarm"),
    ],
    "alarm_speichern": [
        ("role", r"^\s*Save\s*$|^\s*Speichern\s*$"),
        ("text", r"^\s*Save\s*$"),
        ("text", r"^\s*Speichern\s*$"),
    ],
    "dialog_schliessen": [
        ("css", "[class*='close' i]"),
        ("text", r"^[✕✖×xX]$"),
    ],
    # Verwaltung bestehender Alarme. ACHTUNG: Diese beiden wirken auf die
    # echten Alarme des Nutzers. Nie blind den ersten Treffer anklicken —
    # immer ueber die Zeile gehen, deren Preis wirklich gemeint ist
    # (siehe alarm_loeschen()).
    "alarm_loeschen": [
        ("css", "a.remove-alert"),
    ],
    "alarm_bearbeiten": [
        ("css", "a.edit-alert"),
    ],
    "alarm_preisfeld": [
        ("css", "input.price-alert"),
    ],
    "nutzer_alarme_oeffnen": [
        ("css", "li[title*='Alarm' i]"),
        ("css", ".alerts-link"),
    ],
}


# ===========================================================================
# Selektor-Auflösung
# ===========================================================================

def finde(page, key: str, timeout_ms: int = 4000, alle: bool = False):
    """Probiert alle Erkennungswege für 'key' durch und liefert das erste
    sichtbare Element (oder None). Mit alle=True: Liste aller Treffer."""
    if key not in SELEKTOREN:
        raise KeyError(f"Unbekannter Selektor '{key}'")
    for typ, muster in SELEKTOREN[key]:
        try:
            if typ == "text":
                loc = page.get_by_text(re.compile(muster, re.I))
            elif typ == "placeholder":
                loc = page.get_by_placeholder(re.compile(muster, re.I))
            elif typ == "role":
                loc = page.get_by_role("button", name=re.compile(muster, re.I))
            elif typ == "css":
                loc = page.locator(muster)
            else:
                continue

            n = loc.count()
            if n == 0:
                continue
            treffer = []
            for i in range(min(n, 12)):
                el = loc.nth(i)
                try:
                    if el.is_visible():
                        if alle:
                            treffer.append(el)
                        else:
                            return el
                except Exception:
                    continue
            if alle and treffer:
                return treffer
        except Exception:
            continue
    return [] if alle else None


def klick(el, name: str = "", timeout_ms: int = 5000) -> bool:
    """Klickt moeglichst robust.

    Das Desk ordnet seine Fenster nach dem gespeicherten Layout des Nutzers
    an; einzelne ragen aus dem Sichtfeld. Der normale Klick laeuft dann in
    Timeout, obwohl das Element existiert und sichtbar ist. Zweiter Versuch
    per JS-Klick, der Position und Ueberdeckung ignoriert."""
    try:
        el.click(timeout=timeout_ms)
        return True
    except Exception:
        pass
    # Zweite Stufe: ins Sichtfeld holen und erzwungen klicken. Das erzeugt
    # weiterhin echte Mausereignisse - im Gegensatz zum JS-Klick, der bei
    # jQuery-Handlern oft wirkungslos verpufft.
    try:
        el.scroll_into_view_if_needed(timeout=3000)
        el.click(force=True, timeout=timeout_ms)
        if name:
            print(f"    ({name}: erzwungener Klick noetig)")
        return True
    except Exception:
        pass
    # Letzte Stufe: JS. ACHTUNG - liefert True, ohne dass etwas passiert sein
    # muss. Wer damit etwas veraendert, MUSS das Ergebnis nachpruefen.
    try:
        el.evaluate("e => e.click()")
        if name:
            print(f"    ({name}: JS-Klick noetig — Wirkung ungeprueft!)")
        return True
    except Exception as e:
        if name:
            print(f"    Klick auf {name} fehlgeschlagen: {str(e)[:60]}")
        return False


def warte_auf(page, key: str, timeout_s: float = 15.0):
    """Wartet, bis ein Selektor sichtbar wird (Polling über alle Varianten)."""
    ende = time.time() + timeout_s
    while time.time() < ende:
        el = finde(page, key)
        if el is not None:
            return el
        page.wait_for_timeout(500)
    return None


# ===========================================================================
# Diagnose bei Fehlern
# ===========================================================================

def diagnose(page, name: str, notiz: str = ""):
    """Screenshot + HTML-Auszug + sichtbare Bedienelemente ablegen.
    Das ist das Material, mit dem sich der Bot schnell reparieren lässt."""
    DEBUG_DIR.mkdir(exist_ok=True)
    stempel = datetime.now().strftime("%H%M%S")
    basis = DEBUG_DIR / f"{stempel}_{name}"
    try:
        page.screenshot(path=f"{basis}.png")
    except Exception:
        pass

    zeilen = [f"# Diagnose: {name}",
              f"Zeit: {datetime.now():%Y-%m-%d %H:%M:%S}",
              f"URL: {page.url}",
              f"Notiz: {notiz}", ""]

    # Welche bekannten Selektoren werden gerade gefunden?
    zeilen.append("## Selektor-Status")
    for key in SELEKTOREN:
        gefunden = finde(page, key) is not None
        zeilen.append(f"  {'OK    ' if gefunden else 'FEHLT '} {key}")

    # Sichtbare Eingabefelder und Buttons auflisten
    for titel, css in (("## Sichtbare Eingabefelder", "input:visible"),
                       ("## Sichtbare Buttons", "button:visible")):
        zeilen.append("")
        zeilen.append(titel)
        try:
            loc = page.locator(css)
            for i in range(min(loc.count(), 25)):
                el = loc.nth(i)
                info = {
                    "text": (el.inner_text() or "").strip()[:40] if css.startswith("button") else "",
                    "placeholder": el.get_attribute("placeholder") or "",
                    "type": el.get_attribute("type") or "",
                    "name": el.get_attribute("name") or "",
                    "id": el.get_attribute("id") or "",
                    "class": (el.get_attribute("class") or "")[:60],
                }
                zeilen.append("  " + " | ".join(f"{k}={v}" for k, v in info.items() if v))
        except Exception as e:
            zeilen.append(f"  (nicht lesbar: {e})")

    try:
        html = page.content()
        # 400k reichten nicht: Der Alerts manager steht weit hinten im DOM und
        # wurde abgeschnitten. Das Desk-HTML ist gross, darum grosszuegig.
        (DEBUG_DIR / f"{basis.name}.html").write_text(html[:1500000], encoding="utf-8")
    except Exception:
        pass

    (DEBUG_DIR / f"{basis.name}.txt").write_text("\n".join(zeilen), encoding="utf-8")
    print(f"    → Diagnose abgelegt: debug/{basis.name}.[png|txt|html]")


# ===========================================================================
# Retry-Hilfe
# ===========================================================================

def mit_retry(fn, versuche: int = 3, pause: float = 2.0, name: str = ""):
    """Führt fn() aus; bei False/Exception bis zu 'versuche' Mal wiederholen."""
    letzter_fehler = None
    for v in range(1, versuche + 1):
        try:
            ergebnis = fn()
            if ergebnis:
                return ergebnis
            letzter_fehler = "Rückgabe war leer/False"
        except Exception as e:
            letzter_fehler = str(e)
        if v < versuche:
            print(f"    Versuch {v}/{versuche} für '{name}' fehlgeschlagen ({letzter_fehler}) "
                  f"— neuer Versuch in {pause:.0f}s")
            time.sleep(pause)
            pause *= 1.6
    return None


def menschliche_pause(langsam: bool = False):
    """Kleine unregelmäßige Pause — schont die fremde Seite und wirkt weniger maschinell."""
    time.sleep(random.uniform(1.2, 2.2) if langsam else random.uniform(0.4, 0.9))


# ===========================================================================
# Fortschritt (Wiederaufnahme nach Abbruch)
# ===========================================================================

def lade_fortschritt(neu: bool) -> set:
    if neu or not FORTSCHRITT_FILE.exists():
        return set()
    try:
        data = json.loads(FORTSCHRITT_FILE.read_text())
        if data.get("tag") == date.today().isoformat():
            return set(data.get("erledigt", []))
    except Exception:
        pass
    return set()


def speichere_fortschritt(erledigt: set):
    try:
        FORTSCHRITT_FILE.write_text(json.dumps(
            {"tag": date.today().isoformat(), "erledigt": sorted(erledigt)}, indent=2))
    except Exception as e:
        print(f"    Fortschritt nicht speicherbar: {e}")


# ===========================================================================
# Excel einlesen
# ===========================================================================

def load_buypoints(xlsx_path: str, nur_muster: bool) -> list[dict]:
    df = pd.read_excel(xlsx_path, sheet_name="Kaufpunkte")
    jobs = []
    for _, row in df.iterrows():
        points = []
        for i in (1, 2, 3):
            strat = str(row.get(f"KP{i} Strategie", "") or "").strip()
            preis = row.get(f"KP{i} Preis")
            if not strat or pd.isna(preis):
                continue
            if nur_muster and strat.startswith("Fallback"):
                continue
            points.append({"nr": i, "strategie": strat, "preis": float(preis)})
        if points:
            jobs.append({"ticker": str(row["Ticker"]).strip(),
                         "firma": str(row.get("Firma", "") or ""),
                         "points": points})
    return jobs


# ===========================================================================
# Browser-Schritte
# ===========================================================================

def ist_eingeloggt(page) -> bool:
    """Sind wir bei TraderFox angemeldet?

    ACHTUNG, hier bin ich zweimal in dieselbe Falle getappt: Das Element
    #login-ico existiert IMMER. Ausgeloggt zeigt es 'Login / Registrieren',
    eingeloggt den Benutzernamen. Seine blosse Existenz taugt also NICHT als
    Merkmal — weder als Beweis fuers Eingeloggtsein noch dagegen.

    Entscheidend ist der TEXT. Steht dort 'Registrieren', sind wir draussen.

    Warum das wichtig ist: Ohne Anmeldung fehlt im Kontextmenue der Eintrag
    'Alarm hinzufuegen'. Der Bot laeuft dann scheinbar normal und findet
    nur nichts — ein Fehler, der ohne Screenshot kaum zu erkennen ist."""
    if finde(page, "suchfeld") is None:
        return False
    if finde(page, "login_dialog") is not None:
        return False          # Passwortfeld sichtbar = Anmeldemaske offen
    try:
        el = page.locator("#login-ico").first
        if el.count():
            text = (el.inner_text() or "").strip().lower()
            if "registrieren" in text:
                return False
    except Exception:
        pass
    return True


def cookie_hinweis_behandeln(page) -> bool:
    """TraderFox leitet Sitzungen ohne Cookie-Einwilligung auf eine ganzseitige
    Abfrage um (desk.traderfox.com/cookie/). Dahinter ist kein Bedienelement
    erreichbar, der Login scheiterte deshalb mit 'login_dialog_fehlt'.

    Wir wählen bewusst 'Nur Notwendige': Der Bot braucht ausschliesslich die
    technisch notwendigen Cookies. Tracking- und Werbedienste bleiben aus."""
    btn = finde(page, "cookie_ablehnen", timeout_ms=3000)
    if btn is None:
        return False
    try:
        btn.click()
        page.wait_for_timeout(2000)
        print("Cookie-Hinweis mit 'Nur Notwendige' beantwortet.")
        return True
    except Exception:
        diagnose(page, "cookie_klick_fehlt", "'Nur Notwendige' nicht klickbar")
        return False


def login(page, user: str, pw: str) -> bool:
    """Login laut Screenshot: 'Login' → Dialog 'Benutzer Login' → Felder →
    'JETZT EINLOGGEN'. Erkennt eine bestehende Session und überspringt dann."""
    page.goto(DESK_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    # Cookie-Abfrage kommt vor allem anderen — sonst ist die Seite leer.
    if cookie_hinweis_behandeln(page):
        page.goto(DESK_URL, wait_until="domcontentloaded")

    page.wait_for_timeout(4000)

    if ist_eingeloggt(page):
        print("Bereits eingeloggt (Session wiederverwendet).")
        return True

    # Dialog öffnen, falls nötig
    if finde(page, "login_dialog") is None:
        opener = finde(page, "login_oeffnen")
        if opener is not None:
            klick(opener, "Login öffnen")
            page.wait_for_timeout(2000)

    if warte_auf(page, "login_dialog", 12) is None:
        diagnose(page, "login_dialog_fehlt", "Login-Dialog nicht auffindbar")
        return False

    email = finde(page, "login_email")
    passwort = finde(page, "login_passwort")
    if email is None or passwort is None:
        diagnose(page, "login_felder_fehlen", "E-Mail- oder Passwortfeld nicht gefunden")
        return False

    email.click(); email.fill(user)
    menschliche_pause()
    passwort.click(); passwort.fill(pw)
    menschliche_pause()

    btn = finde(page, "login_absenden")
    if btn is None:
        diagnose(page, "login_button_fehlt", "Button 'JETZT EINLOGGEN' nicht gefunden")
        return False
    klick(btn, "JETZT EINLOGGEN")
    page.wait_for_timeout(6000)

    # Erfolg: Dialog weg UND Suchfeld da
    if finde(page, "login_dialog") is not None:
        diagnose(page, "login_abgelehnt",
                 "Login-Dialog noch offen — vermutlich falsche Zugangsdaten")
        return False
    if warte_auf(page, "suchfeld", 20) is None:
        diagnose(page, "desk_nicht_geladen", "Nach Login kein Suchfeld")
        return False

    # Gegenprobe ueber den Text der Kopfzeile, nicht ueber die Existenz des
    # Elements — siehe ist_eingeloggt().
    if not ist_eingeloggt(page):
        diagnose(page, "login_scheinbar_ok",
                 "Suchfeld da, aber Kopfzeile zeigt weiterhin 'Registrieren'")
        print("✗ Login nicht wirksam — Kopfzeile zeigt weiterhin Anmeldung an.")
        return False

    print("Login OK.")
    return True


# Anzeigename des zuletzt gewaehlten Suchtreffers, in TraderFox' EIGENER
# Schreibweise. alarm_dialog_oeffnen sucht die Kurslisten-Zeile damit.
# Grund (Lauf #26): Die Excel-Namen passen oft nicht auf die Zeile —
# 'Cg Oncology Inc' vs. 'CG Oncology', 'nLIGHT Inc' vs. 'nLIGHT', und
# 'Liquidia Corp' heisst bei TraderFox 'Liquidia Technologies Inc.'.
# Das US-Kuerzel steht in der Zeile GAR nicht.
LETZTER_ANZEIGENAME = ""

# Schneidet Boersen-/Waehrungsanhaengsel vom Treffertext ab:
# 'Bel Fuse Inc. CI A Echtzeit USD $ BELF/A …' → 'Bel Fuse Inc. CI A'
_VENUE_SCHNITT = re.compile(
    r"\s+(?:Echtzeit|NASDAQ|NYSE|XNAS|XNYS|B[öo]rse|Tradegate|Gettex|Xetra|"
    r"Lang\b|Indikation|USD|EUR|SEK|NOK|DKK)\b.*$|\s*[$€].*$", re.I)


def _anzeigename(treffertext: str) -> str:
    return _VENUE_SCHNITT.sub("", treffertext).strip()


def aktie_suchen(page, ticker: str, langsam: bool, firma: str = "") -> bool:
    """Ticker ins Suchfeld tippen und den RICHTIGEN Treffer waehlen.

    Wichtig: Ein Kuerzel ist nicht eindeutig. 'BIOA' liefert sowohl
    BioArctic AB (Stockholm) als auch BioAge Labs Inc (USA). Frueher wurde
    einfach der erste sichtbare Treffer genommen - im Testlauf landete der
    Bot damit bei der falschen Firma. Darum wird jetzt gegen den Firmennamen
    abgeglichen und im Zweifel lieber abgebrochen.

    Kennt TraderFox das Kuerzel nicht, wird weitergesucht: erst in der
    Klassen-Schreibweise (BELFA → BELF/A, wie BIOA/B bei BioArctic), dann
    mit dem Firmennamen. Lauf #26 scheiterte an BELFA/BELFB, weil es nur
    einen einzigen Versuch mit dem US-Kuerzel gab."""
    global LETZTER_ANZEIGENAME
    LETZTER_ANZEIGENAME = ""
    such = finde(page, "suchfeld")
    if such is None:
        diagnose(page, f"suchfeld_weg_{ticker}", "Suchfeld nicht gefunden")
        return False
    # Haengengebliebene Menues schliessen: In Lauf #26 stand das News-Menue
    # offen ueber der Kursliste — Escape kostet nichts und raeumt auf.
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(250)
    except Exception:
        pass
    # klick() statt .click(): Liegt ein Fenster ueber dem Suchfeld — etwa der
    # Alerts manager nach einer Bestandsaufnahme — laeuft der einfache Klick
    # in Timeout. Genau daran ist der erste Aufraeumlauf gescheitert.
    if not klick(such, "Suchfeld"):
        diagnose(page, f"suchfeld_klick_{ticker}", "Suchfeld nicht anklickbar")
        return False

    begriffe = [ticker]
    if len(ticker) == 5 and ticker[-1] in "AB" and ticker[:4].isalpha():
        begriffe.append(f"{ticker[:4]}/{ticker[-1]}")
    if firma:
        begriffe.append(firma[:20])

    kandidaten = []
    benutzter_begriff = ticker
    for begriff in begriffe:
        such.fill("")
        such.type(begriff, delay=90 if langsam else 55)
        page.wait_for_timeout(2800)

        # Vorschlagsliste einsammeln
        kandidaten = []
        try:
            eintraege = page.locator("ul.ui-autocomplete li.ui-menu-item")
            for i in range(min(eintraege.count(), 15)):
                el = eintraege.nth(i)
                try:
                    if not el.is_visible():
                        continue
                    text = " ".join((el.inner_text() or "").split())
                    if text:
                        kandidaten.append((el, text))
                except Exception:
                    continue
        except Exception:
            pass
        if kandidaten:
            benutzter_begriff = begriff
            break
        print(f"    Kein Treffer für '{begriff}'"
              + (f" — versuche nächsten Suchbegriff" if begriff != begriffe[-1] else ""))

    if not kandidaten:
        diagnose(page, f"kein_suchtreffer_{ticker}",
                 f"Kein Treffer für {ticker} im Dropdown (auch nicht als "
                 f"{', '.join(begriffe[1:]) or 'weitere Schreibweise'})")
        return False

    print(f"    {len(kandidaten)} Treffer für '{ticker}':")
    for _, text in kandidaten[:8]:
        print(f"      · {text[:75]}")

    def bewerte(text: str) -> int:
        """Je hoeher, desto besser. Der Firmenname zaehlt am meisten."""
        t = text.lower()
        punkte = 0
        if firma:
            worte = [w for w in re.split(r"[^A-Za-zÄÖÜäöüß]+", firma) if len(w) > 2]
            treffer = sum(1 for w in worte[:3] if w.lower() in t)
            punkte += treffer * 10
            if worte and worte[0].lower() in t:
                punkte += 5
        if re.search(rf"\b{re.escape(ticker)}\b", text, re.I):
            punkte += 3
        # Auch den tatsaechlich benutzten Suchbegriff honorieren — bei
        # Aktienklassen unterscheidet NUR er A von B ('BELF/A' vs 'BELF/B';
        # der Firmenname ist bei beiden Klassen identisch).
        if (benutzter_begriff != ticker
                and re.search(rf"\b{re.escape(benutzter_begriff)}\b", text, re.I)):
            punkte += 3
        if re.search(r"USD|NASDAQ|NYSE|\$", text, re.I):
            punkte += 2
        return punkte

    bewertet = sorted(((bewerte(t), el, t) for el, t in kandidaten),
                      key=lambda x: x[0], reverse=True)
    punkte, el, text = bewertet[0]

    # Ohne Firmennamen-Treffer nicht raten: lieber sauber scheitern, als
    # Kaufpunkte bei der falschen Aktie einzutragen.
    if firma and punkte < 10:
        diagnose(page, f"kein_passender_treffer_{ticker}",
                 f"Kein Treffer passt zu {firma!r}; bester war {text!r}")
        print(f"    ✗ Kein Treffer passt zu '{firma}' — bester war '{text[:60]}'")
        return False

    print(f"    → gewählt: {text[:70]}")
    LETZTER_ANZEIGENAME = _anzeigename(text)
    try:
        el.click()
    except Exception:
        maus_klick(el, "Suchtreffer")
    page.wait_for_timeout(2200)
    return True


def alarm_dialog_oeffnen(page, ticker: str, firma: str) -> bool:
    """Rechtsklick auf den Aktiennamen → 'Alarm hinzufügen'.

    Genau so beschreibt es auch die TraderFox-Anleitung:
    https://traderfox.de/features/preisalarm.html

    Wichtig ist das Ziel des Rechtsklicks: Der Firmenname steht auch in
    News-Schlagzeilen und im Info-Fenster, und dort gibt es kein
    Kontextmenue. Darum ausschliesslich Tabellenzellen der Kursliste."""
    zeile = None
    kandidaten = []
    # Primaer TraderFox' eigene Schreibweise aus dem Suchtreffer — die
    # Excel-Namen passen oft nicht auf die Zeile (Lauf #26: 'Cg Oncology
    # Inc' vs. 'CG Oncology', 'Liquidia Corp' vs. 'Liquidia Technologies
    # Inc.', 'nLIGHT Inc' vs. 'nLIGHT'), und das US-Kuerzel steht dort gar
    # nicht. Danach Wort-Muster aus dem Firmennamen statt der frueheren
    # starren ersten 14 Zeichen.
    if LETZTER_ANZEIGENAME:
        kandidaten.append(r"\s+".join(re.escape(w)
                                      for w in LETZTER_ANZEIGENAME.split()))
    if firma:
        worte = [w for w in re.split(r"[^A-Za-z0-9ÄÖÜäöüß]+", firma) if w]
        if len(worte) >= 2:
            kandidaten.append(rf"{re.escape(worte[0])}\s+{re.escape(worte[1])}")
        if worte and len(worte[0]) >= 4:
            kandidaten.append(re.escape(worte[0]))
    kandidaten.append(re.escape(ticker))

    for muster in kandidaten:
        for css in ("td", "tr"):
            try:
                loc = page.locator(css).filter(has_text=re.compile(muster, re.I))
                for i in range(min(loc.count(), 8)):
                    el = loc.nth(i)
                    if el.is_visible():
                        zeile = el
                        break
            except Exception:
                continue
            if zeile is not None:
                break
        if zeile is not None:
            break

    if zeile is None:
        diagnose(page, f"zeile_fehlt_{ticker}", "Aktienzeile in der Kursliste nicht gefunden")
        return False

    try:
        zeile.click(button="right", timeout=6000)
    except Exception:
        # Fenster ausserhalb des Sichtfelds o. ae. — per JS nachhelfen.
        try:
            zeile.evaluate(
                "e => e.dispatchEvent(new MouseEvent('contextmenu', "
                "{bubbles: true, cancelable: true, button: 2}))")
            print("    (Rechtsklick per JS ausgeloest)")
        except Exception as e:
            diagnose(page, f"rechtsklick_{ticker}", f"Rechtsklick nicht moeglich: {e}")
            return False
    page.wait_for_timeout(1500)
    # Das Kontextmenue entsteht erst jetzt per JS — Zustand festhalten.
    diagnose(page, f"nach_rechtsklick_{ticker}", "Direkt nach dem Rechtsklick")

    menue = warte_auf(page, "kontextmenue_alarm", 6)
    if menue is None:
        diagnose(page, f"kontextmenue_{ticker}", "'Alarm hinzufügen' nicht im Kontextmenü")
        return False
    klick(menue, "Alarm hinzufügen")
    page.wait_for_timeout(1600)

    if warte_auf(page, "alarm_dialog", 10) is None:
        diagnose(page, f"alarm_dialog_{ticker}", "Alarm-Dialog öffnete sich nicht")
        return False

    # SICHERHEITSPRUEFUNG: Zeigt der Dialog wirklich die gemeinte Aktie?
    # Bei Laeufen ueber mehrere Werte koennte ein nicht geschlossener Dialog
    # der vorigen Aktie stehenbleiben - die Alarme landeten dann beim
    # falschen Wert, ohne dass es jemand merkt.
    try:
        kopf = page.locator(".alert-configurator-header")
        if kopf.count():
            titel = (kopf.first.inner_text() or "").strip()
            erwartet = (firma or ticker).strip()
            kern = erwartet.split()[0][:8].lower() if erwartet else ""
            if kern and kern not in titel.lower():
                diagnose(page, f"falsche_aktie_{ticker}",
                         f"Dialog zeigt {titel!r}, erwartet wurde {erwartet!r}")
                print(f"    ✗ Dialog zeigt {titel!r}, erwartet {erwartet!r} — abgebrochen")
                return False
            print(f"    Dialog bestätigt für: {titel[:60]!r}")
    except Exception as e:
        print(f"    (Dialog-Titel nicht prüfbar: {e})")

    return True


def preis_formatieren(preis: float) -> str:
    """Preis so schreiben, wie TraderFox ihn erwartet: deutsches Format mit
    KOMMA. Mit Punkt getippt liest TraderFox ihn als Tausendertrennzeichen —
    aus 999.99 wurde so 99.999,00."""
    return f"{preis:.2f}".replace(".", ",")


def preis_parsen(text: str):
    """Deutsches Zahlenformat einlesen: '99.999,00' -> 99999.0,
    '78,000' -> 78.0. Liefert None, wenn nichts Sinnvolles drinsteht."""
    t = (text or "").strip()
    if not t:
        return None
    t = t.replace(" ", "").replace("$", "").replace("€", "")
    t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def bestehende_alarme(page) -> set:
    """Liest die bereits eingetragenen Alarmpreise, um Doppelte zu vermeiden.

    Nur input.price-alert: Das Desk ist voller anderer Eingabefelder
    (Suche, Hebel, Laufzeit). 'input:visible' lieferte hier Zufallswerte
    und machte die Verifikation wertlos."""
    preise = set()
    try:
        for el in page.locator("input.price-alert:visible").all()[:60]:
            wert = preis_parsen(el.input_value() or "")
            if wert is not None:
                preise.add(round(wert, 2))
    except Exception:
        pass
    return preise


JS_ALARM_INVENTUR = """
() => {
  // Nur Abschnitte INNERHALB des Alerts manager, und jeden nur einmal.
  // Vorher wurden alle .alert-section im ganzen Dokument gezaehlt - dabei
  // kamen die Abschnitte des offenen Alarm-Dialogs (Preis-/Signal-/
  // News-Alarm) dazu, und bei zweimal geoeffnetem Manager alles doppelt.
  const titel = [...document.querySelectorAll('*')].find(e => {
    const t = e.getAttribute('title') || '';
    return t.includes('Alerts manager') && e.children.length === 0;
  });
  const wurzel = titel ? titel.closest('.container') : null;
  if (!wurzel) return [];

  const gesehen = new Set();
  const out = [];
  for (const sec of wurzel.querySelectorAll('.alert-section')) {
    const titelEl = sec.querySelector('.title');
    let name = titelEl ? (titelEl.textContent || '').trim() : '';
    name = name.replace(/\\s+/g, ' ');
    const preise = [...sec.querySelectorAll('input.price-alert')].map(i => i.value);
    if (!name && !preise.length) continue;
    const schluessel = name + '|' + preise.join(';');
    if (gesehen.has(schluessel)) continue;
    gesehen.add(schluessel);
    out.push({titel: name, preise: preise});
  }
  return out;
}
"""


JS_FENSTER_SCHLIESSEN = """
(suchtext) => {
  const alle = [...document.querySelectorAll('*')];
  const titel = alle.find(e => {
    const t = e.getAttribute('title') || '';
    return t.includes(suchtext) && e.children.length === 0;
  });
  if (!titel) return false;
  const box = titel.closest('.container');
  if (!box) return false;
  const zu = box.querySelector('.close, .fa-times, [data-action="close"]');
  if (!zu) return false;
  zu.click();
  return true;
}
"""


def fenster_schliessen(page, suchtext: str) -> bool:
    """Schliesst das Fenster mit diesem Titel. Noetig, weil offene Fenster im
    Desk andere ueberdecken - der Alerts manager legte sich sonst ueber die
    Kursliste, und der Rechtsklick dort ging ins Leere.

    Zweistufig: erst der Schliessknopf des Fensters, dann - falls das nicht
    greift - der Container ausgeblendet. Beim ersten Aufraeumlauf schlug der
    Knopf fehl, das Fenster blieb offen und verdeckte das Suchfeld."""
    try:
        ok = page.evaluate(JS_FENSTER_SCHLIESSEN, suchtext)
        page.wait_for_timeout(1200)
        if ok:
            print(f"    Fenster '{suchtext}' geschlossen.")
            return True
    except Exception as e:
        print(f"    Fenster '{suchtext}': {str(e)[:60]}")

    # Rueckfall: Container ausblenden. Aendert nichts an gespeicherten
    # Daten, macht aber die darunterliegende Oberflaeche wieder frei.
    try:
        weg = page.evaluate(
            "(suchtext) => {"
            " const alle = [...document.querySelectorAll('*')];"
            " const t = alle.find(e => (e.getAttribute('title') || '').includes(suchtext)"
            "                          && e.children.length === 0);"
            " if (!t) return false;"
            " const box = t.closest('.container');"
            " if (!box) return false;"
            " box.style.display = 'none';"
            " return true; }", suchtext)
        page.wait_for_timeout(500)
        print(f"    Fenster '{suchtext}' ausgeblendet: {bool(weg)}")
        return bool(weg)
    except Exception as e:
        print(f"    Fenster '{suchtext}' nicht schliessbar: {str(e)[:60]}")
        return False


def alarme_inventur(page, name: str = "bestand") -> list:
    """Liest alle bestehenden Alarme aus dem Alerts manager und legt sie als
    Datei ab. Reines Lesen. Nuetzlich, um Doppelte zu vermeiden und um nach
    einem Lauf nachweisen zu koennen, dass nichts verlorenging."""
    eintraege = []
    try:
        oeffner = finde(page, "nutzer_alarme_oeffnen")
        if oeffner is not None:
            klick(oeffner, "Nutzer-Alarme")
            # Warten, bis wirklich Inhalt da ist. Ein fester Wert reichte
            # nicht: Beim ersten Aufraeumlauf meldete die Inventur null
            # Alarme, weil das Fenster noch leer war.
            for _ in range(12):
                page.wait_for_timeout(1000)
                try:
                    if page.locator(".alert-section").count() > 0:
                        break
                except Exception:
                    pass
        eintraege = page.evaluate(JS_ALARM_INVENTUR)
    except Exception as e:
        print(f"    (Inventur fehlgeschlagen: {e})")
        return []

    if not eintraege:
        print("    ⚠ Keine Alarme gelesen — Fenster vermutlich nicht geladen.")

    DEBUG_DIR.mkdir(exist_ok=True)
    stempel = datetime.now().strftime("%H%M%S")
    ziel = DEBUG_DIR / f"{stempel}_alarmbestand_{name}.txt"
    gesamt = sum(len(e["preise"]) for e in eintraege)
    zeilen = [f"# Alarm-Bestand: {name}",
              f"Zeit: {datetime.now():%Y-%m-%d %H:%M:%S}",
              f"Werte: {len(eintraege)}   Alarme gesamt: {gesamt}", ""]
    for e in eintraege:
        zeilen.append(f"  {e['titel']}")
        zeilen.append(f"      {', '.join(e['preise'])}")
    ziel.write_text("\n".join(zeilen), encoding="utf-8")
    print(f"    → Alarm-Bestand: {len(eintraege)} Werte, {gesamt} Alarme "
          f"→ debug/{ziel.name}")
    return eintraege


JS_MAUSFOLGE = (
    "e => { for (const t of ['mouseover','mousedown','mouseup','click']) "
    "e.dispatchEvent(new MouseEvent(t, "
    "{bubbles:true, cancelable:true, view:window})); }"
)


def maus_klick(el, name: str = "") -> bool:
    """Klickt per vollstaendiger Maus-Ereignisfolge.

    Bei den Alarm-Knoepfen von TraderFox der einzige Weg, der wirkt. Gemessen
    im Testlauf: Der Knopf ist 21x21 gross und sichtbar, trotzdem laeuft ein
    normaler Playwright-Klick in Timeout, ein erzwungener bewirkt nichts, und
    ein blosses e.click() ebenfalls nicht. Erst mouseover/mousedown/mouseup/
    click nacheinander loesen den Handler aus.

    ACHTUNG: Liefert True, sobald die Ereignisse abgesetzt wurden - das ist
    KEIN Nachweis, dass etwas passiert ist. Immer das Ergebnis nachpruefen."""
    try:
        el.evaluate(JS_MAUSFOLGE)
        return True
    except Exception as e:
        if name:
            print(f"    Maus-Ereignisfolge auf {name} fehlgeschlagen: {str(e)[:60]}")
        return False


def zaehle_preis(page, preis: float) -> int:
    """Wie oft steht dieser Preis gerade in einem sichtbaren Alarmfeld?"""
    felder = page.locator("input.price-alert:visible")
    n = 0
    for i in range(min(felder.count(), 60)):
        w = preis_parsen(felder.nth(i).input_value() or "")
        if w is not None and abs(w - preis) < 0.005:
            n += 1
    return n


def erkunde_loeschweg(page, preis: float) -> bool:
    """Probiert der Reihe nach verschiedene Wege, einen Alarm zu loeschen,
    und prueft nach jedem, ob er wirklich verschwunden ist.

    Hintergrund: Die Knoepfe sind leere <a>-Elemente ohne Text und ohne
    Symbol; ihr Aussehen kommt allein aus CSS. Ist die Box 0x0 gross, laesst
    sich nicht darauf klicken - dann muss der Klick woanders hin."""
    print(f"\n--- Erkundung: Wie loescht man den Alarm zu {preis}? ---")
    felder = page.locator("input.price-alert:visible")
    ziel = None
    for i in range(min(felder.count(), 60)):
        w = preis_parsen(felder.nth(i).input_value() or "")
        if w is not None and abs(w - preis) < 0.005:
            ziel = felder.nth(i)
            break
    if ziel is None:
        print(f"    Kein Feld mit {preis} gefunden.")
        return False

    zeile = ziel.locator("xpath=ancestor::tr[1]")
    knopf = zeile.locator("a.remove-alert").first
    if knopf.count() == 0:
        print("    Kein a.remove-alert in dieser Zeile.")
        return False

    # Erst einmal ausmessen — das erklaert die Timeouts.
    try:
        box = knopf.bounding_box()
        sichtbar = knopf.is_visible()
        print(f"    Knopf: sichtbar={sichtbar}  box={box}")
    except Exception as e:
        print(f"    Knopf nicht messbar: {e}")

    vorher = zaehle_preis(page, preis)
    print(f"    Vorhanden vor den Versuchen: {vorher}x")

    versuche = [
        ("normaler Klick",
         lambda: knopf.click(timeout=4000)),
        ("erzwungener Klick",
         lambda: knopf.click(force=True, timeout=4000)),
        ("Klick auf die Zelle",
         lambda: zeile.locator("td").last.click(force=True, timeout=4000)),
        ("Maus-Ereignisfolge per JS",
         lambda: knopf.evaluate(
             "e => { for (const t of ['mouseover','mousedown','mouseup','click']) "
             "e.dispatchEvent(new MouseEvent(t, {bubbles:true, cancelable:true, view:window})); }")),
        ("jQuery-Trigger",
         lambda: knopf.evaluate(
             "e => { if (window.jQuery) window.jQuery(e).trigger('click'); }")),
    ]

    for bezeichnung, aktion in versuche:
        try:
            aktion()
        except Exception as e:
            print(f"    [{bezeichnung}] nicht ausfuehrbar: {str(e)[:60]}")
            continue
        page.wait_for_timeout(2500)
        jetzt = zaehle_preis(page, preis)
        if jetzt < vorher:
            print(f"    ✓ [{bezeichnung}] HAT FUNKTIONIERT ({vorher} -> {jetzt})")
            diagnose(page, "loeschweg_gefunden", f"'{bezeichnung}' loescht Alarme")
            return True
        print(f"    ✗ [{bezeichnung}] wirkungslos (weiterhin {jetzt}x)")

    diagnose(page, "loeschweg_unbekannt", f"Kein Weg gefunden, {preis} zu loeschen")
    print("    Kein Weg hat funktioniert.")
    return False


def alarm_loeschen(page, preis: float, maximal: int = 5) -> int:
    """Loescht alle Alarme mit GENAU diesem Preis. Liefert die Anzahl.

    Sicherheitsprinzip: Es wird das Preisfeld gesucht, dessen Wert exakt
    passt, und nur in dessen Zeile auf 'Löschen' geklickt. Niemals blind den
    ersten remove-alert-Knopf — dort haengen die Alarme des Nutzers.

    Mehrfach, weil ein fehlgeschlagener Wiederholungsversuch beim Setzen
    Duplikate hinterlassen kann. Nach jedem Loeschen baut TraderFox die
    Liste neu auf, darum jedes Mal von vorn suchen."""
    geloescht = 0
    for _ in range(maximal):
        treffer = None
        felder = page.locator("input.price-alert:visible")
        for i in range(min(felder.count(), 60)):
            el = felder.nth(i)
            wert = preis_parsen(el.input_value() or "")
            if wert is not None and abs(wert - preis) < 0.005:
                treffer = el
                break
        if treffer is None:
            break
        try:
            zeile = treffer.locator("xpath=ancestor::tr[1]")
            knopf = zeile.locator("a.remove-alert").first
            if knopf.count() == 0:
                print(f"    Kein Löschen-Knopf in der Zeile zu {preis}")
                break
            vorher = sum(1 for i in range(min(felder.count(), 60))
                         if (lambda w: w is not None and abs(w - preis) < 0.005)(
                             preis_parsen(felder.nth(i).input_value() or "")))
            # Maus-Ereignisfolge statt klick(): siehe maus_klick(). Normale
            # und erzwungene Klicks bleiben bei diesen Knoepfen wirkungslos.
            if not maus_klick(knopf, f"Löschen {preis}"):
                break
            page.wait_for_timeout(2500)

            # NACHPRUEFEN. Der Klick meldet Erfolg, auch wenn nichts geschah -
            # so wurden fuenfmal dieselben Alarme "geloescht", die danach immer
            # noch dastanden. Sinkt die Anzahl nicht, hat es nicht funktioniert.
            felder_neu = page.locator("input.price-alert:visible")
            nachher = sum(1 for i in range(min(felder_neu.count(), 60))
                          if (lambda w: w is not None and abs(w - preis) < 0.005)(
                              preis_parsen(felder_neu.nth(i).input_value() or "")))
            if nachher >= vorher:
                print(f"    ⚠ Löschen wirkungslos: {preis} ist immer noch "
                      f"{nachher}x da (vorher {vorher}x) — abgebrochen")
                break
            geloescht += 1
            print(f"    Gelöscht: {preis} (bestätigt, noch {nachher}x vorhanden)")
        except Exception as e:
            print(f"    Löschen fehlgeschlagen: {str(e)[:70]}")
            break
    if geloescht == 0:
        print(f"    Kein Alarm mit Preis {preis} gefunden (nichts geloescht)")
    return geloescht


def aufraeum_lauf(page, user: str, pw: str, auftraege: list) -> int:
    """Loescht gezielt einzelne Alarme.

    auftraege: Liste von (ticker, firma, preis). Es wird ausschliesslich der
    Alarm mit genau diesem Preis entfernt — alle anderen bleiben unangetastet.

    Gebraucht, wenn Kaufpunkte veralten: Aendert sich das Regelwerk oder
    liefert ein neuer Scan andere Level, stehen die alten Marken sonst
    weiter im Konto und melden sich zu Kursen, die niemand mehr will."""
    print(f"\n=== AUFRÄUMEN: {len(auftraege)} Alarm(e) entfernen ===\n")
    for ticker, firma, preis in auftraege:
        print(f"    {ticker} ({firma}): {preis}")
    print()

    if not login(page, user, pw):
        print("✗ Login fehlgeschlagen.")
        return 1

    # BEWUSST KEINE Bestandsaufnahme vorweg.
    #
    # Sie oeffnet den Alerts manager, und der laedt nicht immer zuverlaessig.
    # Ein halb geladenes, leeres Fenster laesst sich weder auslesen noch
    # schliessen — es liegt danach ueber der Kursliste und verschluckt den
    # Rechtsklick. Genau daran ist der zweite Aufraeumlauf gescheitert.
    #
    # Fuer das Loeschen wird sie nicht gebraucht: alarm_loeschen() zaehlt
    # ohnehin vor und nach jedem Klick nach und meldet, was wirklich
    # verschwunden ist.

    entfernt, probleme = 0, []
    for i, (ticker, firma, preis) in enumerate(auftraege, 1):
        print(f"\n[{i}/{len(auftraege)}] {ticker} — {preis} entfernen")
        dialog_schliessen(page)
        if not aktie_suchen(page, ticker, langsam=True, firma=firma):
            probleme.append(f"{ticker} (Suche)")
            continue
        if not alarm_dialog_oeffnen(page, ticker, firma):
            probleme.append(f"{ticker} (Dialog)")
            continue
        anzahl = alarm_loeschen(page, preis)
        if anzahl:
            entfernt += anzahl
        else:
            probleme.append(f"{ticker} @ {preis} (nicht gefunden oder nicht löschbar)")

    dialog_schliessen(page)

    print("\n--- Ergebnis ---")
    print(f"  Aufträge:  {len(auftraege)}")
    print(f"  Entfernt:  {entfernt}")
    if probleme:
        print(f"\n⚠ {len(probleme)} Problem(e): {', '.join(probleme)}")
        return 1
    if entfernt == 0:
        print("\n⚠ Nichts entfernt — standen die Alarme überhaupt noch?")
        return 1
    print("\n✓ Aufräumen abgeschlossen.")
    return 0


# Zaehlt die Preis-Alarme INNERHALB des Alerts manager (nicht im ganzen
# Desk — sonst zaehlten offene Alarm-Dialoge mit, der Fehler von frueher).
JS_MANAGER_ALARMZAHL = """
() => {
  const titel = [...document.querySelectorAll('*')].find(e => {
    const t = e.getAttribute('title') || '';
    return t.includes('Alerts manager') && e.children.length === 0;
  });
  const wurzel = titel ? titel.closest('.container') : null;
  if (!wurzel) return -1;
  return wurzel.querySelectorAll('.alert-section input.price-alert').length;
}
"""

# Loest den ERSTEN Loeschknopf im Alerts manager aus — mit der vollen
# Maus-Ereignisfolge, dem einzigen Klickweg, der bei diesen Knoepfen wirkt.
JS_MANAGER_ERSTEN_LOESCHEN = """
() => {
  const titel = [...document.querySelectorAll('*')].find(e => {
    const t = e.getAttribute('title') || '';
    return t.includes('Alerts manager') && e.children.length === 0;
  });
  const wurzel = titel ? titel.closest('.container') : null;
  if (!wurzel) return false;
  const knopf = wurzel.querySelector('.alert-section a.remove-alert');
  if (!knopf) return false;
  for (const t of ['mouseover','mousedown','mouseup','click'])
    knopf.dispatchEvent(new MouseEvent(t, {bubbles:true, cancelable:true, view:window}));
  return true;
}
"""


def loesche_alle_lauf(page, user: str, pw: str) -> int:
    """Loescht SAEMTLICHE Alarme im Konto — auch die handgesetzten.

    Ausdruecklich beauftragt von Mathias am 23.07.2026, mit Gerhards
    Zustimmung ('In Zukunft wird es ohnehin nur die Alarme des Tools
    geben'). Die alte Schutzregel 'handgesetzte Alarme sind tabu' ist
    fuer DIESEN Modus bewusst aufgehoben — fuer alle anderen gilt sie
    unveraendert weiter.

    BEWUSST OHNE Sicherungsdatei (Mathias, 23.07.2026): Die Aktienliste
    (finviz_3.csv) ist das Original, aus ihr erzeugt der Scanner die
    Alarme laufend neu — ein Alarm-Backup waere totes Gewicht.
    Fehlerfreiheit stellt das Zaehlen sicher:
    1. Jeder Loeschklick wird nachgezaehlt; sinkt die Zahl dreimal in
       Folge nicht, bricht der Lauf ab, statt blind weiterzuklicken.
    2. Am Ende wird nachgezaehlt — Erfolg heisst exakt null uebrig."""
    print("\n=== ALLES LÖSCHEN: sämtliche Alarme entfernen ===\n")
    if not login(page, user, pw):
        print("✗ Login fehlgeschlagen.")
        return 1

    print("[1/3] Alerts manager öffnen und zählen")
    oeffner = finde(page, "nutzer_alarme_oeffnen")
    if oeffner is None:
        diagnose(page, "loeschen_kein_manager", "Öffner für Nutzer-Alarme fehlt")
        print("✗ Alarm-Übersicht nicht auffindbar.")
        return 1
    klick(oeffner, "Nutzer-Alarme")
    # Warten, bis wirklich Inhalt geladen ist — ein halb leeres Fenster
    # lieferte frueher die Zaehlung null, obwohl Alarme existierten.
    for _ in range(12):
        page.wait_for_timeout(1000)
        try:
            if page.locator(".alert-section").count() > 0:
                break
        except Exception:
            pass
    vorher = page.evaluate(JS_MANAGER_ALARMZAHL)
    if vorher < 0:
        diagnose(page, "loeschen_manager_leer", "Alerts manager nicht gefunden")
        print("✗ Alarm-Fenster nicht lesbar — nichts gelöscht.")
        return 1
    if vorher == 0:
        print("    Konto ist bereits leer — nichts zu tun.")
        return 0

    print(f"\n[2/3] {vorher} Alarme löschen (einzeln, mit Nachzählen)")
    entfernt, fehlversuche = 0, 0
    letzte_meldung = 0
    while True:
        try:
            zahl = page.evaluate(JS_MANAGER_ALARMZAHL)
        except Exception as e:
            print(f"    ✗ Zählung fehlgeschlagen: {str(e)[:60]}")
            break
        if zahl <= 0:
            break
        try:
            ok = page.evaluate(JS_MANAGER_ERSTEN_LOESCHEN)
        except Exception:
            ok = False
        page.wait_for_timeout(900)
        try:
            danach = page.evaluate(JS_MANAGER_ALARMZAHL)
        except Exception:
            danach = zahl
        if not (ok and danach < zahl):
            # TraderFox braucht manchmal laenger als die normale Wartezeit —
            # in Lauf #29 waren ~20 von 178 Loeschungen solche Spaetzuender.
            # Erst nachfassen, dann warnen.
            page.wait_for_timeout(2500)
            try:
                danach = page.evaluate(JS_MANAGER_ALARMZAHL)
            except Exception:
                pass
        if ok and danach < zahl:
            entfernt += zahl - danach
            fehlversuche = 0
            if entfernt - letzte_meldung >= 10:
                print(f"    … {entfernt} von {vorher} entfernt")
                letzte_meldung = entfernt
        else:
            fehlversuche += 1
            print(f"    ⚠ Klick ohne Wirkung ({fehlversuche}/3) — "
                  f"Stand {danach} Alarme")
            if fehlversuche >= 3:
                diagnose(page, "loeschen_stockt",
                         f"Zahl sinkt nicht mehr: noch {danach} Alarme")
                break
        if entfernt > vorher + 20:
            print("    ⚠ Mehr entfernt als erwartet — Sicherheitsstopp.")
            break

    print(f"\n[3/3] Schlusszählung")
    uebrig = max(page.evaluate(JS_MANAGER_ALARMZAHL), 0)

    print("\n--- Ergebnis ---")
    print(f"  Alarme vorher:  {vorher}")
    print(f"  Entfernt:       {vorher - uebrig}")
    print(f"  Übrig:          {uebrig}")
    if uebrig == 0:
        print("\n✓ Konto ist leer — alle Alarme entfernt und nachgezählt.")
        return 0
    print("\n⚠ Es sind noch Alarme übrig — Diagnose siehe debug/.")
    return 1


def testalarm_lauf(page, user: str, pw: str, ticker: str = "AAPL",
                   firma: str = "Apple") -> int:
    """Legt EINEN Testalarm an, prueft ihn und raeumt ihn wieder weg.

    Der Preis liegt bewusst weit ueber dem Kurs, damit der Alarm nicht
    ausloest und keine Benachrichtigung erzeugt."""
    TESTPREIS = 999.99
    print(f"\n=== TESTALARM auf {ticker} zu {TESTPREIS} $ ===")
    print("    Preis bewusst weit ueber dem Kurs — loest nicht aus.")
    print("    Der Alarm wird am Ende wieder geloescht.\n")

    if not login(page, user, pw):
        print("✗ Login fehlgeschlagen.")
        return 1

    print("\n[1/6] Bestandsaufnahme vorher")
    vorher = alarme_inventur(page, "01_vorher")
    anzahl_vorher = sum(len(e["preise"]) for e in vorher)
    # Der Manager wuerde sonst die Kursliste verdecken.
    fenster_schliessen(page, "Alerts manager")

    print(f"\n[2/6] {ticker} suchen")
    if not aktie_suchen(page, ticker, langsam=True, firma=firma):
        print("✗ Suche fehlgeschlagen.")
        return 1

    print("\n[3/6] Alarm-Dialog oeffnen")
    # Firmenname ist wichtig: In der Kursliste steht 'Apple Inc.', das
    # Kuerzel AAPL kommt dort gar nicht vor.
    if not alarm_dialog_oeffnen(page, ticker, firma):
        print("✗ Alarm-Dialog ging nicht auf.")
        return 1

    # Reste aus frueheren Testlaeufen zuerst wegraeumen. 99999 stammt aus dem
    # Lauf, in dem '999.99' mit Punkt getippt und als 99.999,00 gelesen wurde.
    print("\n[3b] Alte Testalarme entfernen")
    aufgeraeumt = 0
    for altpreis in (TESTPREIS, 99999.0):
        aufgeraeumt += alarm_loeschen(page, altpreis)
    print(f"    Aufgeraeumt: {aufgeraeumt}")

    # Wenn nichts wegging, obwohl noch etwas dasteht: herausfinden, warum.
    if aufgeraeumt == 0:
        for altpreis in (TESTPREIS, 99999.0):
            if zaehle_preis(page, altpreis) > 0:
                if erkunde_loeschweg(page, altpreis):
                    # Weg gefunden — gleich weiter aufraeumen.
                    aufgeraeumt += alarm_loeschen(page, altpreis)
                break

    print(f"\n[4/6] Testalarm zu {TESTPREIS} setzen")
    gesetzt = alarm_setzen(page, ticker, TESTPREIS, "Testalarm", langsam=True)
    diagnose(page, "testalarm_nach_setzen", f"Nach dem Setzen von {TESTPREIS}")
    if not gesetzt:
        print("✗ Alarm konnte nicht gesetzt werden.")
        return 1
    print("    ✓ Alarm gesetzt und verifiziert")

    print(f"\n[5/6] Testalarm zu {TESTPREIS} wieder loeschen")
    geloescht = alarm_loeschen(page, TESTPREIS) > 0
    diagnose(page, "testalarm_nach_loeschen", f"Nach dem Loeschen von {TESTPREIS}")
    if not geloescht:
        print(f"⚠ ACHTUNG: Der Testalarm zu {TESTPREIS} $ auf {ticker} konnte")
        print("  nicht geloescht werden und steht noch im Konto!")
        print("  Bitte von Hand entfernen (App oder Alerts manager).")

    print("\n[6/6] Bestandsaufnahme nachher")
    nachher = alarme_inventur(page, "02_nachher")
    anzahl_nachher = sum(len(e["preise"]) for e in nachher)

    print("\n--- Ergebnis ---")
    print(f"  Alarme vorher:  {anzahl_vorher}")
    print(f"  Aufgeraeumt:    {aufgeraeumt} (Reste frueherer Testlaeufe)")
    print(f"  Alarme nachher: {anzahl_nachher}")
    print(f"  Setzen:   {'OK' if gesetzt else 'FEHLGESCHLAGEN'}")
    print(f"  Loeschen: {'OK' if geloescht else 'FEHLGESCHLAGEN'}")

    # Erwartet wird: vorher minus aufgeraeumte Reste. Der Testalarm selbst
    # wird ja wieder geloescht und darf die Bilanz nicht veraendern.
    erwartet = anzahl_vorher - aufgeraeumt
    abweichung = anzahl_nachher - erwartet
    if gesetzt and geloescht and abweichung == 0:
        print("\n✓ Anlegen und Loeschen funktionieren. Bestand wie erwartet.")
        return 0
    if abweichung != 0:
        print(f"\n⚠ Erwartet waren {erwartet} Alarme, gezaehlt {anzahl_nachher} "
              f"(Abweichung {abweichung:+d}).")
        print("  Achtung: Ausgeloeste Alarme entfernt TraderFox von selbst —")
        print("  eine Abweichung nach unten kann auch daher kommen.")
    return 1


def alarm_setzen(page, ticker: str, preis: float, strategie: str, langsam: bool) -> bool:
    """Einen Preis-Alarm eintragen und verifizieren, dass er wirklich drin steht."""
    # KOMMA, nicht Punkt: TraderFox rechnet deutsch. Mit '999.99' wurde der
    # Punkt als Tausendertrennzeichen gelesen und daraus 99.999,00 - der
    # Alarm landete also auf einem voellig anderen Kurs.
    preis_str = preis_formatieren(preis)

    def versuch():
        # Steht der Preis schon drin, nicht noch einmal setzen. Sonst
        # erzeugt jeder Wiederholungsversuch ein weiteres Duplikat - genau
        # so entstanden drei Alarme statt einem.
        if round(preis, 2) in bestehende_alarme(page):
            print(f"    {ticker}: {preis_str} steht bereits — nicht doppelt gesetzt")
            return True

        # Eingabefeld direkt hinter '+ Neuer Alarm'.
        #
        # NIEMALS auf "irgendein sichtbares Feld" ausweichen: Frueher wurde
        # hier notfalls das letzte sichtbare input der Seite genommen, geleert
        # und ueberschrieben. Auf dem Desk sind das im Zweifel die
        # price-alert-Felder bereits bestehender Alarme des Nutzers.
        # Lieber sauber scheitern als fremde Alarme zerstoeren.
        feld = None
        label = finde(page, "neuer_alarm_label")
        if label is not None:
            try:
                kandidat = label.locator("xpath=following::input[1]")
                if kandidat.count() > 0 and kandidat.first.is_visible():
                    feld = kandidat.first
            except Exception:
                feld = None
        if feld is None:
            diagnose(page, f"neues_alarmfeld_fehlt_{ticker}",
                     "Feld hinter '+ Neuer Alarm' nicht gefunden — "
                     "abgebrochen, um keine bestehenden Alarme zu ueberschreiben")
            return False

        # Sicherheitsnetz: Ein Feld, in dem schon ein Preis steht, gehoert zu
        # einem bestehenden Alarm und wird nicht angefasst.
        try:
            vorhandener_wert = (feld.input_value() or "").strip()
        except Exception:
            vorhandener_wert = ""
        if vorhandener_wert:
            diagnose(page, f"alarmfeld_belegt_{ticker}",
                     f"Feld war bereits mit {vorhandener_wert!r} belegt — nicht ueberschrieben")
            return False

        if not klick(feld, "Alarm-Eingabefeld"):
            return False
        feld.type(preis_str, delay=70 if langsam else 40)
        menschliche_pause(langsam)

        speichern = finde(page, "alarm_speichern")
        if speichern is None:
            return False
        if not klick(speichern, "Save"):
            return False
        page.wait_for_timeout(1800)

        # VERIFIKATION: Steht der Preis jetzt irgendwo im Dialog?
        gesetzt = bestehende_alarme(page)
        if round(preis, 2) in gesetzt:
            return True
        try:
            if page.get_by_text(re.compile(re.escape(preis_str))).count() > 0:
                return True
        except Exception:
            pass
        return False

    ok = mit_retry(versuch, versuche=3, pause=1.5, name=f"Alarm {ticker} {preis_str}")
    if ok:
        print(f"    ✓ {ticker}: {preis_str} $ ({strategie}) — verifiziert")
        return True
    print(f"    ✗ {ticker}: {preis_str} $ ({strategie}) — nicht bestätigt")
    diagnose(page, f"alarm_unbestaetigt_{ticker}_{preis_str.replace('.', '_')}",
             f"Alarm {preis_str} nach 3 Versuchen nicht in der Liste")
    return False


def alarmdialog_offen(page) -> bool:
    """Ist gerade ein Alarm-Dialog offen?"""
    try:
        return page.locator(".contextmenu-element.alert-config:visible").count() > 0
    except Exception:
        return False


def dialog_schliessen(page) -> bool:
    """Schliesst gezielt den Alarm-Dialog und prueft nach.

    Frueher wurde ueber [class*='close' i] das erste beliebige Element mit
    'close' im Klassennamen angeklickt. Im Desk gibt es davon viele - damit
    haette der Bot Fenster aus dem gespeicherten Layout des Nutzers zumachen
    koennen. Jetzt der eindeutige Knopf des Alarm-Dialogs.

    Wichtig fuer Laeufe ueber mehrere Aktien: Bleibt der Dialog offen, zeigt
    er weiter die vorige Aktie - Alarme koennten beim falschen Wert landen."""
    if not alarmdialog_offen(page):
        return True

    # Es koennen mehrere Dialoge uebereinanderliegen — alle zumachen.
    for _ in range(4):
        zu = page.locator(".alert-configurator-close-icon:visible")
        if zu.count() == 0:
            break
        maus_klick(zu.first, "Alarm-Dialog schliessen")
        page.wait_for_timeout(900)
        if not alarmdialog_offen(page):
            return True

    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(700)
    except Exception:
        pass
    if not alarmdialog_offen(page):
        return True

    # Letzter Ausweg: den Container direkt aus dem Weg raeumen. Das aendert
    # nichts an gespeicherten Daten, macht aber die Kursliste wieder frei.
    try:
        page.evaluate(
            "() => { for (const e of document.querySelectorAll("
            "'.context_menu_wrapper, .contextmenu-element.alert-config')) "
            "e.style.display = 'none'; }")
        page.wait_for_timeout(500)
    except Exception:
        pass
    if alarmdialog_offen(page):
        print("    ⚠ Alarm-Dialog liess sich nicht schliessen")
        return False
    return True


# ===========================================================================
# Selbsttest — prüft die Bedienelemente, ohne etwas zu verändern
# ===========================================================================

JS_ALARM_ELEMENTE = """
() => {
  const out = [];
  for (const el of document.querySelectorAll('*')) {
    const titel = el.getAttribute('title') || '';
    const cls = (typeof el.className === 'string') ? el.className : '';
    const id = el.id || '';
    const txt = (el.children.length === 0) ? (el.textContent || '').trim().slice(0, 50) : '';
    const blob = (titel + ' ' + cls + ' ' + id + ' ' + txt).toLowerCase();
    if (!/alarm|alert/.test(blob)) continue;
    const r = el.getBoundingClientRect();
    out.push({
      tag: el.tagName.toLowerCase(), id: id, cls: cls.slice(0, 55),
      titel: titel, text: txt,
      sichtbar: !!(r.width && r.height), x: Math.round(r.x), y: Math.round(r.y)
    });
  }
  return out.slice(0, 70);
}
"""


JS_FENSTER_HTML = """
(suchtext) => {
  const alle = [...document.querySelectorAll('*')];
  const treffer = alle.find(e => {
    const t = e.getAttribute('title') || '';
    return t.includes(suchtext) && e.children.length === 0;
  });
  if (!treffer) return null;
  let box = treffer.closest('.container');
  if (!box) {
    box = treffer;
    for (let i = 0; i < 5 && box.parentElement; i++) box = box.parentElement;
  }
  return box.outerHTML;
}
"""


def fenster_html_sichern(page, suchtext: str, name: str):
    """Speichert gezielt das Fenster, dessen Titel 'suchtext' enthaelt.
    Noetig, weil das komplette Desk-HTML riesig ist und das Interessante
    sonst der Kappung zum Opfer faellt."""
    DEBUG_DIR.mkdir(exist_ok=True)
    stempel = datetime.now().strftime("%H%M%S")
    ziel = DEBUG_DIR / f"{stempel}_fenster_{name}.html"
    try:
        html = page.evaluate(JS_FENSTER_HTML, suchtext)
    except Exception as e:
        print(f"    (Fenster '{suchtext}' nicht lesbar: {e})")
        return
    if not html:
        print(f"    (Fenster '{suchtext}' nicht gefunden)")
        return
    ziel.write_text(html, encoding="utf-8")
    print(f"    → Fenster-HTML abgelegt: debug/{ziel.name} ({len(html)} Zeichen)")


def alarm_elemente_auflisten(page, name: str):
    """Schreibt alle Elemente, die nach Alarm aussehen, samt Sichtbarkeit und
    Position in eine Datei. Reines Lesen — klickt nichts an."""
    DEBUG_DIR.mkdir(exist_ok=True)
    stempel = datetime.now().strftime("%H%M%S")
    ziel = DEBUG_DIR / f"{stempel}_alarmelemente_{name}.txt"
    try:
        treffer = page.evaluate(JS_ALARM_ELEMENTE)
    except Exception as e:
        treffer = []
        print(f"    (Elementliste nicht lesbar: {e})")
    zeilen = [f"# Alarm-verdaechtige Elemente: {name}",
              f"Zeit: {datetime.now():%Y-%m-%d %H:%M:%S}",
              f"URL: {page.url}", f"Anzahl: {len(treffer)}", ""]
    for t in treffer:
        sicht = "SICHTBAR" if t["sichtbar"] else "versteckt"
        zeilen.append(
            f"  [{sicht:9}] <{t['tag']}> id={t['id']!r} class={t['cls']!r} "
            f"title={t['titel']!r} text={t['text']!r} @({t['x']},{t['y']})")
    ziel.write_text("\n".join(zeilen), encoding="utf-8")
    print(f"    → Elementliste abgelegt: debug/{ziel.name} ({len(treffer)} Treffer)")


def erkunde_alarmweg(page, ticker: str):
    """Erkundet, wie auf dem DESKTOP ein Preisalarm angelegt wird.

    Hintergrund: Der erwartete Menueintrag 'Alarm hinzufuegen' existiert im
    Desktop-HTML nicht — die Vorlage dafuer stammte offenbar aus der
    iPhone-App. Diese Funktion klickt sich vorsichtig an die Kandidaten heran
    und legt nach jedem Schritt Diagnosematerial ab.

    WICHTIG: Sie setzt KEINEN Alarm. Es wird nichts gespeichert und nichts
    bestaetigt — nur geoeffnet und angeschaut."""
    print("\n--- Erkundung: Wo legt die Desktop-Oberflaeche Alarme an? ---")
    print("    (setzt nichts, speichert nichts)")

    alarm_elemente_auflisten(page, "01_ausgangslage")

    # Schritt 1: Chart auf den Ticker stellen — ein Kursalarm haengt am Chart.
    try:
        chartsuche = page.locator("input.search[placeholder*='Aktie suchen' i]")
        gesetzt = False
        for i in range(min(chartsuche.count(), 4)):
            el = chartsuche.nth(i)
            if not el.is_visible():
                continue
            el.click()
            el.fill(ticker)
            page.wait_for_timeout(2500)
            page.keyboard.press("Enter")
            page.wait_for_timeout(3000)
            gesetzt = True
            break
        print(f"    Chart auf {ticker} gestellt: {gesetzt}")
    except Exception as e:
        print(f"    Chart-Suche fehlgeschlagen: {e}")

    diagnose(page, "erkundung_chart", f"Chart nach Suche nach {ticker}")

    # Schritt 2: Das Alarm-Werkzeug in der Chart-Symbolleiste anklicken.
    try:
        werkzeug = page.locator("a.alert_icon")
        print(f"    a.alert_icon im DOM: {werkzeug.count()}x")
        geklickt = False
        for i in range(min(werkzeug.count(), 4)):
            el = werkzeug.nth(i)
            if not el.is_visible():
                continue
            el.click()
            page.wait_for_timeout(2500)
            geklickt = True
            break
        print(f"    Alarm-Werkzeug angeklickt: {geklickt}")
    except Exception as e:
        print(f"    Alarm-Werkzeug nicht klickbar: {e}")

    diagnose(page, "erkundung_alarmwerkzeug", "Nach Klick auf a.alert_icon")
    alarm_elemente_auflisten(page, "02_nach_werkzeug")

    # Schritt 3: Seitenleisten-Eintrag 'Nutzer-Alarme' anschauen.
    try:
        seitenleiste = page.locator("li[title*='Alarm' i]")
        print(f"    li[title*=Alarm] im DOM: {seitenleiste.count()}x")
        for i in range(min(seitenleiste.count(), 3)):
            el = seitenleiste.nth(i)
            if not el.is_visible():
                continue
            el.click()
            page.wait_for_timeout(2500)
            break
    except Exception as e:
        print(f"    Seitenleiste nicht klickbar: {e}")

    diagnose(page, "erkundung_seitenleiste", "Nach Klick auf 'Nutzer-Alarme'")
    alarm_elemente_auflisten(page, "03_nach_seitenleiste")
    # Genau das ist das interessante Fenster — gezielt sichern.
    fenster_html_sichern(page, "Alerts manager", "alertsmanager")

    # Schritt 4: Der Manager hat drei Reiter (Einzelaktien / Kurslisten /
    # Alerts ticker) und KEINEN sichtbaren Knopf zum Neuanlegen. Vielleicht
    # steckt der in einem der anderen Reiter. Nur umschalten, sonst nichts.
    for reiter in ("ticker", "list", "stock"):
        try:
            el = page.locator(f"a[name='{reiter}']").first
            if el.count() and klick(el, f"Reiter {reiter}"):
                page.wait_for_timeout(2000)
                print(f"    Reiter '{reiter}' geoeffnet")
                fenster_html_sichern(page, "Alerts manager", f"reiter_{reiter}")
                diagnose(page, f"reiter_{reiter}", f"Manager-Reiter '{reiter}'")
        except Exception as e:
            print(f"    Reiter '{reiter}' nicht erreichbar: {str(e)[:80]}")

    # Schritt 5: Das Chart-Werkzeug liess sich normal nicht anklicken
    # (Timeout trotz Sichtbarkeit) — vermutlich ueberdeckt. Zweiter Versuch
    # per JS-Klick, der Ueberdeckungen ignoriert.
    try:
        el = page.locator("a.alert_icon").first
        if el.count():
            el.evaluate("e => e.click()")
            page.wait_for_timeout(2500)
            print("    Alarm-Werkzeug per JS angeklickt")
            diagnose(page, "erkundung_werkzeug_js", "a.alert_icon per JS geklickt")
            alarm_elemente_auflisten(page, "04_nach_werkzeug_js")
    except Exception as e:
        print(f"    JS-Klick fehlgeschlagen: {str(e)[:80]}")

    print("--- Erkundung beendet ---\n")


def selbsttest(page, user: str, pw: str) -> int:
    print("\n=== SELBSTTEST: prüft nur, ob alles gefunden wird — setzt KEINE Alarme ===\n")
    ergebnis = {}

    ok_login = login(page, user, pw)
    ergebnis["Login"] = ok_login
    if not ok_login:
        print("\n✗ Login fehlgeschlagen — weitere Prüfungen nicht möglich.")
        return 1

    ergebnis["Suchfeld"] = finde(page, "suchfeld") is not None

    test_ticker = "AAPL"  # existiert garantiert, wird nur gesucht
    ok_suche = aktie_suchen(page, test_ticker, langsam=True, firma="Apple")
    ergebnis[f"Suche ({test_ticker})"] = ok_suche

    ok_dialog = False
    if ok_suche:
        ok_dialog = alarm_dialog_oeffnen(page, test_ticker, "Apple")
        ergebnis["Alarm-Dialog öffnen"] = ok_dialog
        if not ok_dialog:
            # Der bisherige Weg (Rechtsklick) stammt aus der iPhone-App und
            # existiert auf dem Desktop nicht. Material sammeln statt raten.
            erkunde_alarmweg(page, test_ticker)

    if ok_dialog:
        ergebnis["Feld '+ Neuer Alarm'"] = finde(page, "neuer_alarm_label") is not None
        ergebnis["Button 'Save'"] = finde(page, "alarm_speichern") is not None

        # Struktur des offenen Dialogs festhalten: Hier wird spaeter wirklich
        # geschrieben, darum vorher genau anschauen. Insbesondere, ob das Feld
        # hinter '+ Neuer Alarm' leer ist und wie viele price-alert-Felder
        # bereits belegt sind (= bestehende Alarme des Nutzers).
        diagnose(page, "alarmdialog_offen", "Alarm-Dialog geoeffnet (nichts eingetragen)")
        try:
            belegt = bestehende_alarme(page)
            print(f"    Bereits belegte Alarmpreise in diesem Dialog: {sorted(belegt)}")
            label = finde(page, "neuer_alarm_label")
            if label is not None:
                k = label.locator("xpath=following::input[1]")
                if k.count():
                    print(f"    Feld hinter '+ Neuer Alarm' enthaelt: "
                          f"{(k.first.input_value() or '')!r}")
        except Exception as e:
            print(f"    (Dialog-Analyse fehlgeschlagen: {e})")

        dialog_schliessen(page)

    print("\n--- Ergebnis ---")
    for k, v in ergebnis.items():
        print(f"  {'✓' if v else '✗'} {k}")
    fehler = [k for k, v in ergebnis.items() if not v]
    if fehler:
        print(f"\n✗ {len(fehler)} Prüfpunkt(e) fehlgeschlagen: {', '.join(fehler)}")
        print("  → Die Dateien in ./debug/ an Claude schicken, dann wird die "
              "SELEKTOREN-Karte oben im Script angepasst.")
        return 1
    print("\n✓ Alles gefunden — der Bot ist einsatzbereit.")
    return 0


# ===========================================================================
# Main
# ===========================================================================

def main():
    ap = argparse.ArgumentParser(description="Setzt Kaufpunkte als Preis-Alarme in TraderFox")
    ap.add_argument("xlsx", nargs="?", help="kaufpunkte.xlsx vom Pattern-Scanner")
    ap.add_argument("--alle", action="store_true", help="Auch Fallback-Level alarmieren")
    ap.add_argument("--sichtbar", action="store_true", help="Browser sichtbar (zum Zuschauen)")
    ap.add_argument("--limit", type=int, default=None, help="Nur die ersten N Aktien")
    ap.add_argument("--neu", action="store_true", help="Fortschritt ignorieren, alles neu setzen")
    ap.add_argument("--langsam", action="store_true", help="Gemächlicher tippen und klicken")
    ap.add_argument("--selbsttest", action="store_true",
                    help="Nur prüfen, ob alle Bedienelemente gefunden werden")
    ap.add_argument("--testalarm", action="store_true",
                    help="Einen Testalarm anlegen, prüfen und wieder löschen")
    ap.add_argument("--loesche", metavar="TICKER:PREIS[,...]",
                    help="Gezielt einzelne Alarme entfernen, z. B. "
                         "'BIOA:21.28,CRNX:83.64'. Firmennamen werden aus der "
                         "angegebenen kaufpunkte.xlsx nachgeschlagen.")
    ap.add_argument("--loesche-alle", action="store_true",
                    help="SÄMTLICHE Alarme löschen, auch handgesetzte. "
                         "Legt vorher zwingend eine Sicherung ab.")
    args = ap.parse_args()

    user = os.environ.get("TRADERFOX_USER")
    pw = os.environ.get("TRADERFOX_PASS")
    if not user or not pw:
        sys.exit("Bitte TRADERFOX_USER und TRADERFOX_PASS als Umgebungsvariablen setzen.")
    nur_pruefen = (args.selbsttest or args.testalarm or bool(args.loesche)
                   or args.loesche_alle)
    if not nur_pruefen and not args.xlsx:
        sys.exit("Bitte kaufpunkte.xlsx angeben (oder --selbsttest / --testalarm benutzen).")

    # Loeschauftraege einlesen und Firmennamen ergaenzen
    loesch_auftraege = []
    if args.loesche:
        firmen = {}
        if args.xlsx:
            try:
                d = pd.read_excel(args.xlsx, sheet_name="Kaufpunkte")
                for _, zeile in d.iterrows():
                    firmen[str(zeile["Ticker"]).strip()] = str(zeile.get("Firma", "")).strip()
            except Exception as e:
                print(f"⚠ Firmennamen nicht lesbar ({e}) — suche nur nach Kürzel.")
        for teil in args.loesche.split(","):
            teil = teil.strip()
            if not teil or ":" not in teil:
                continue
            ticker, preis = teil.split(":", 1)
            ticker = ticker.strip().upper()
            try:
                loesch_auftraege.append((ticker, firmen.get(ticker, ""), float(preis)))
            except ValueError:
                sys.exit(f"Preis nicht lesbar in {teil!r} — erwartet z. B. 'BIOA:21.28'")
        if not loesch_auftraege:
            sys.exit("Keine gültigen Löschaufträge erkannt.")

    jobs = []
    if not nur_pruefen:
        jobs = load_buypoints(args.xlsx, nur_muster=not args.alle)
        if args.limit:
            jobs = jobs[: args.limit]
        if not jobs:
            sys.exit("Keine passenden Kaufpunkte gefunden "
                     "(ohne --alle werden nur echte Muster-Treffer verarbeitet).")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.sichtbar,
                                    args=["--disable-blink-features=AutomationControlled"])
        # 1680x950 war zu klein: Das Desk positioniert seine Fenster frei nach
        # dem gespeicherten Layout des Nutzers, dabei landete der Alerts
        # manager teilweise links ausserhalb (x = -183). Playwright kann
        # nichts anklicken, was ausserhalb des Sichtfelds liegt - alle Klicks
        # dort liefen in Timeout.
        kontext_args = {"viewport": {"width": 2560, "height": 1440},
                        "locale": "de-AT"}
        if SESSION_FILE.exists() and not nur_pruefen:
            try:
                kontext_args["storage_state"] = str(SESSION_FILE)
            except Exception:
                pass
        kontext = browser.new_context(**kontext_args)
        page = kontext.new_page()
        page.set_default_timeout(15000)

        if args.selbsttest:
            code = selbsttest(page, user, pw)
            browser.close()
            sys.exit(code)

        if args.testalarm:
            code = testalarm_lauf(page, user, pw)
            browser.close()
            sys.exit(code)

        if args.loesche_alle:
            code = loesche_alle_lauf(page, user, pw)
            browser.close()
            sys.exit(code)

        if loesch_auftraege:
            code = aufraeum_lauf(page, user, pw, loesch_auftraege)
            browser.close()
            sys.exit(code)

        if not mit_retry(lambda: login(page, user, pw), versuche=2, pause=5, name="Login"):
            browser.close()
            sys.exit("Login endgültig fehlgeschlagen — siehe ./debug/. "
                     "Prüf zuerst die Secrets TRADERFOX_USER / TRADERFOX_PASS.")

        # Session für den nächsten Lauf sichern
        try:
            kontext.storage_state(path=str(SESSION_FILE))
        except Exception:
            pass

        erledigt = lade_fortschritt(args.neu)
        gesamt = sum(len(j["points"]) for j in jobs)
        offen = [(j, p) for j in jobs for p in j["points"]
                 if f"{j['ticker']}|{p['nr']}|{p['preis']:.2f}" not in erledigt]
        print(f"\n{len(jobs)} Aktien, {gesamt} Alarme gesamt, davon {len(offen)} offen "
              f"({gesamt - len(offen)} bereits erledigt).")
        if gesamt > 100:
            print("⚠ Über 100 Alarme — prüf, ob dein TraderFox-Abo so viele zulässt.")

        gesetzt, probleme = 0, []
        for i, job in enumerate(jobs, 1):
            offene_punkte = [p for p in job["points"]
                             if f"{job['ticker']}|{p['nr']}|{p['preis']:.2f}" not in erledigt]
            if not offene_punkte:
                continue
            t = job["ticker"]
            print(f"[{i}/{len(jobs)}] {t} — {len(offene_punkte)} offene(r) Alarm(e)")

            if not mit_retry(lambda: aktie_suchen(page, t, args.langsam, job["firma"]),
                             versuche=3, pause=2, name=f"Suche {t}"):
                probleme.append(f"{t} (Suche)")
                continue
            # Vor jeder Aktie sicherstellen, dass kein Dialog der vorigen
            # offen ist — sonst landen Alarme womoeglich beim falschen Wert.
            dialog_schliessen(page)

            if not mit_retry(lambda: alarm_dialog_oeffnen(page, t, job["firma"]),
                             versuche=3, pause=2, name=f"Dialog {t}"):
                probleme.append(f"{t} (Dialog)")
                continue

            schon_drin = bestehende_alarme(page)
            for punkt in offene_punkte:
                if round(punkt["preis"], 2) in schon_drin:
                    print(f"    ↷ {t}: {punkt['preis']:.2f} $ existiert bereits — übersprungen")
                    erledigt.add(f"{t}|{punkt['nr']}|{punkt['preis']:.2f}")
                    continue
                if alarm_setzen(page, t, punkt["preis"], punkt["strategie"], args.langsam):
                    gesetzt += 1
                    erledigt.add(f"{t}|{punkt['nr']}|{punkt['preis']:.2f}")
                    speichere_fortschritt(erledigt)   # nach JEDEM Erfolg sichern
                else:
                    probleme.append(f"{t} @ {punkt['preis']:.2f}")
                menschliche_pause(args.langsam)

            dialog_schliessen(page)
            menschliche_pause(args.langsam)

        try:
            kontext.storage_state(path=str(SESSION_FILE))
        except Exception:
            pass
        browser.close()

    print(f"\n=== Fertig: {gesetzt} Alarme neu gesetzt ===")
    if probleme:
        print(f"Probleme ({len(probleme)}): {', '.join(probleme[:20])}"
              + (" …" if len(probleme) > 20 else ""))
        print("→ Ordner ./debug/ an Claude schicken. Der Fortschritt ist gesichert: "
              "ein erneuter Lauf macht nur die offenen Alarme.")
    else:
        print("Keine Probleme aufgetreten.")


if __name__ == "__main__":
    main()
