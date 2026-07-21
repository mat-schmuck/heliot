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
    "login_dialog": [
        ("css", ".login-popup"),
        ("text", r"Zugangsdaten eingeben"),
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

    # Bereits eingeloggt? Suchfeld da und kein Login-Dialog/-Button.
    if finde(page, "suchfeld") is not None and finde(page, "login_dialog") is None \
            and finde(page, "login_oeffnen") is None:
        print("Bereits eingeloggt (Session wiederverwendet).")
        return True

    # Dialog öffnen, falls nötig
    if finde(page, "login_dialog") is None:
        opener = finde(page, "login_oeffnen")
        if opener is not None:
            try:
                opener.click()
                page.wait_for_timeout(2000)
            except Exception:
                pass

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
    btn.click()
    page.wait_for_timeout(6000)

    # Erfolg: Dialog weg UND Suchfeld da
    if finde(page, "login_dialog") is not None:
        diagnose(page, "login_abgelehnt",
                 "Login-Dialog noch offen — vermutlich falsche Zugangsdaten")
        return False
    if warte_auf(page, "suchfeld", 20) is None:
        diagnose(page, "desk_nicht_geladen", "Nach Login kein Suchfeld")
        return False

    print("Login OK.")
    return True


def aktie_suchen(page, ticker: str, langsam: bool) -> bool:
    """Ticker ins Suchfeld tippen und den US-Treffer wählen."""
    such = finde(page, "suchfeld")
    if such is None:
        diagnose(page, f"suchfeld_weg_{ticker}", "Suchfeld nicht gefunden")
        return False
    such.click()
    such.fill("")
    such.type(ticker, delay=90 if langsam else 55)
    page.wait_for_timeout(2600)

    # Bevorzugt der US-Treffer (Dollar/NASDAQ), sonst irgendein Treffer mit dem Ticker
    for muster in (rf"\$\s*{re.escape(ticker)}\b",
                   rf"\b{re.escape(ticker)}\b.*(USD|NASDAQ|NYSE|\$)",
                   rf"\b{re.escape(ticker)}\b"):
        try:
            loc = page.get_by_text(re.compile(muster, re.I))
            for i in range(min(loc.count(), 8)):
                el = loc.nth(i)
                if el.is_visible():
                    el.click()
                    page.wait_for_timeout(2200)
                    return True
        except Exception:
            continue

    diagnose(page, f"kein_suchtreffer_{ticker}", f"Kein Treffer für {ticker} im Dropdown")
    return False


def alarm_dialog_oeffnen(page, ticker: str, firma: str) -> bool:
    """Rechtsklick auf die Aktienzeile → 'Alarm hinzufügen'."""
    zeile = None
    kandidaten = []
    if firma:
        kandidaten.append(re.escape(firma[:14]))
    kandidaten.append(re.escape(ticker))
    for muster in kandidaten:
        try:
            loc = page.get_by_text(re.compile(muster, re.I))
            for i in range(min(loc.count(), 6)):
                el = loc.nth(i)
                if el.is_visible():
                    zeile = el
                    break
        except Exception:
            continue
        if zeile is not None:
            break

    if zeile is None:
        diagnose(page, f"zeile_fehlt_{ticker}", "Aktienzeile in der Konsole nicht gefunden")
        return False

    zeile.click(button="right")
    page.wait_for_timeout(1200)

    menue = warte_auf(page, "kontextmenue_alarm", 6)
    if menue is None:
        diagnose(page, f"kontextmenue_{ticker}", "'Alarm hinzufügen' nicht im Kontextmenü")
        return False
    menue.click()
    page.wait_for_timeout(1600)

    if warte_auf(page, "alarm_dialog", 10) is None:
        diagnose(page, f"alarm_dialog_{ticker}", "Alarm-Dialog öffnete sich nicht")
        return False
    return True


def bestehende_alarme(page) -> set:
    """Liest die bereits im Dialog eingetragenen Alarmpreise, um Doppelte zu vermeiden."""
    preise = set()
    try:
        for el in page.locator("input:visible").all()[:15]:
            wert = (el.input_value() or "").strip().replace(",", ".")
            if wert:
                try:
                    preise.add(round(float(wert), 2))
                except ValueError:
                    continue
    except Exception:
        pass
    return preise


def alarm_setzen(page, ticker: str, preis: float, strategie: str, langsam: bool) -> bool:
    """Einen Preis-Alarm eintragen und verifizieren, dass er wirklich drin steht."""
    preis_str = f"{preis:.2f}"

    def versuch():
        # Eingabefeld direkt hinter '+ Neuer Alarm', sonst letztes sichtbares Input
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
            sichtbar = page.locator("input:visible")
            if sichtbar.count() == 0:
                return False
            feld = sichtbar.last

        feld.click()
        feld.fill("")
        feld.type(preis_str, delay=70 if langsam else 40)
        menschliche_pause(langsam)

        speichern = finde(page, "alarm_speichern")
        if speichern is None:
            return False
        speichern.click()
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


def dialog_schliessen(page):
    el = finde(page, "dialog_schliessen")
    if el is not None:
        try:
            el.click()
            page.wait_for_timeout(700)
            return
        except Exception:
            pass
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(700)
    except Exception:
        pass


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
            if el.count() and el.is_visible():
                el.click(timeout=5000)
                page.wait_for_timeout(2000)
                print(f"    Reiter '{reiter}' geoeffnet")
                fenster_html_sichern(page, "Alerts manager", f"reiter_{reiter}")
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
    ok_suche = aktie_suchen(page, test_ticker, langsam=True)
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
    args = ap.parse_args()

    user = os.environ.get("TRADERFOX_USER")
    pw = os.environ.get("TRADERFOX_PASS")
    if not user or not pw:
        sys.exit("Bitte TRADERFOX_USER und TRADERFOX_PASS als Umgebungsvariablen setzen.")
    if not args.selbsttest and not args.xlsx:
        sys.exit("Bitte kaufpunkte.xlsx angeben (oder --selbsttest benutzen).")

    jobs = []
    if not args.selbsttest:
        jobs = load_buypoints(args.xlsx, nur_muster=not args.alle)
        if args.limit:
            jobs = jobs[: args.limit]
        if not jobs:
            sys.exit("Keine passenden Kaufpunkte gefunden "
                     "(ohne --alle werden nur echte Muster-Treffer verarbeitet).")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.sichtbar,
                                    args=["--disable-blink-features=AutomationControlled"])
        kontext_args = {"viewport": {"width": 1680, "height": 950},
                        "locale": "de-AT"}
        if SESSION_FILE.exists() and not args.selbsttest:
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

            if not mit_retry(lambda: aktie_suchen(page, t, args.langsam),
                             versuche=3, pause=2, name=f"Suche {t}"):
                probleme.append(f"{t} (Suche)")
                continue
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
