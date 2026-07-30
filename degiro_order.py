#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DEGIRO-ORDER VORBEREITEN — bestätigt wird von Hand
===================================================
Mathias am 30.07.2026: "Ich möchte UNBEDINGT, dass ich nur bestätigen
muss, alles davor soll das Programm machen."

Genau so ist es gebaut. Das Programm geht den ganzen Weg — Order
platzieren, suchen, richtige Zeile finden, Dialog öffnen, Ordertyp,
Kurse und Stückzahl eintragen, auf "Order platzieren" klicken — und
HÄLT DANN AN, wenn der Kontrollbildschirm offen ist. Es liest vor, was
dort steht. Der letzte Klick gehört Mathias.

DREI STUFEN
    kauf   Limit-Kauf über einen Eurobetrag; die Stückzahl rechnet
           DEGIRO selbst aus.
    stop   Schutzstop auf den Bestand, der nach dem Kauf wirklich im
           Depot liegt. Ordertyp "Stop Loss", unbefristet.
    ziel   Verkauf beim Kursziel, Ordertyp "Limit".

    Warum drei Aufrufe und keine verknüpfte Order: DEGIRO kennt keine
    verbundenen Aufträge. Stop und Ziel wären zwei Verkäufe auf
    DIESELBEN Stücke; ob der zweite abgelehnt oder als Leerverkauf
    angenommen wird, ist ungeprüft. Darum geht der Stop in den Markt,
    und das Ziel überwacht der Chartwächter, der ohnehin in Echtzeit
    mitläuft. Erreicht die Aktie das Ziel, ruft er Stufe "ziel" auf.

DIE SPERRE
    BESTAETIGEN_GEHOERT_MATHIAS steht als Konstante im Quelltext und
    nicht als Aufrufoption. Eine Option wäre irgendwann versehentlich
    gesetzt. Das Programm kennt die Bestätigen-Schaltfläche nicht einmal
    — es sucht sie nirgends.

WARUM VORGELESEN WIRD
    Mathias sieht den Bildschirm nicht. Am 30.07.2026 habe ich die Suche
    nach "NVIDIA" in seinem Konto angesehen: Sie liefert eine Aktie und
    ZEHN weitere handelbare Zeilen — dieselbe Aktie auf Tradegate und
    Xetra in Euro, dazu 3NVD, NVD3, NVI3, ONVD (Hebelpapiere), NVDI
    (Optionsschein) und 3SNV sowie NVDD, die auf FALLENDE Kurse setzen.
    Jede Zeile hat eine eigene K-Schaltfläche.

    Ein Vergreifen um eine Zeile kauft also ein Short-Papier statt der
    Aktie. Genau dieser Fehler ist dem TraderFox-Bot passiert (falsche
    Trefferzeile); dort kostete er einen falschen Alarm, hier Geld.
    Deshalb wird die Zeile mehrfach abgesichert und der fertige Auftrag
    aus der SEITE zurückgelesen, nicht aus dem, was das Programm
    eintragen wollte.

WAS AM 30.07.2026 IN DER OBERFLÄCHE GEMESSEN WURDE
    Verlässliche Anker, alle vorhanden:
      [data-name="placeOrderMenuButton"]  Menü "Order platzieren"
      [data-name="orderForm"]             das ganze Bedienfeld
      [data-name="productSearchResult"]   Trefferliste
      [data-name="productType"]           Abschnitt: "Aktien" / "ETFs"
      [data-name="productItem"]           eine Trefferzeile
      [data-name="productChangeButton"]   "Ändern"
      input[name="buySellActionField"]    Kauf / Verkauf
      input[name="limit"]                 Limit ($)
      input[name="number"]                Anzahl
      input[name="amount"]                Betrag (€)
      [data-name="orderType"]             Ordertyp
      [data-name="orderTimeType"]         Orderdauer
      [data-name="productPositionInfo"]   "Aktuelle Position … (30 St.)"
      input[name="stopPrice"]             Stop-Preis ($)
      [data-name="orderConfirmation"]     Kontrollbildschirm
      [data-name="orderConfirmationCancel"]  "Abbrechen"

    Ordertyp und Orderdauer sind nachgebaute Auswahlfelder, keine
    echten. Der gewählte Text landet in einem versteckten Feld:
      Ordertyp   Limit 0, Stop Limit 1, Stop Loss 3
      Dauer      Tagesgültig 1, Unbefristet 3
    Erst dieser Wert beweist, dass die Umstellung angekommen ist —
    React zeichnet verzögert, ein einmaliges Nachsehen greift zu früh.
    Stop Loss blendet "stopPrice" ein, Stop Limit "limit" UND
    "stopPrice", Limit nur "limit".
    Die Schaltfläche "Order platzieren" im Formular trägt kein data-name,
    ist aber die einzige mit type="submit" darin.
    Die Feld-IDs enthalten Zeitstempel und sind NICHT brauchbar; die
    name-Attribute schon.

    Der Kontrollbildschirm zeigt (live gemessen an AXGN): Anzahl,
    Ordertyp, Orderdauer, Limit, Gesamtbetrag in Dollar UND Euro, Börse,
    Geld-/Brief und die erwartete Transaktionsgebühr.

    Wichtiger Fund: Es gibt ein Feld "Betrag (€)". DEGIRO rechnet die
    Stückzahl daraus selbst aus. Der Umweg über einen eigenen
    Euro-Dollar-Kurs entfällt damit — und mit ihm eine Fehlerquelle.

WO ES LÄUFT
    In einem eigenen Chrome-Profil fürs Traden, in dem Mathias selbst
    bei DEGIRO angemeldet ist (trading_chrome.py). Damit braucht das
    Programm KEINE Zugangsdaten: kein Passwort, kein TOTP-Schlüssel,
    nichts zu speichern. Bei einem Depot ist das der entscheidende
    Unterschied zum TraderFox-Bot, wo es nur um einen Datendienst ging.

Aufruf:
    python trading_chrome.py                             einmal starten

    python degiro_order.py NVDA --firma "NVIDIA Corp"
    python degiro_order.py NVDA --firma "NVIDIA Corp" --betrag 2000
    python degiro_order.py NVDA --stufe stop --stop 41.20
    python degiro_order.py NVDA --stufe ziel --limit 48.50
    python degiro_order.py --pruefe          nur die Anker prüfen
"""

import argparse
import re
import sys

# ===========================================================================
# HARTE SPERRE — im Quelltext, nicht als Aufrufoption.
BESTAETIGEN_GEHOERT_MATHIAS = True
# ===========================================================================

CHROME_ANSCHLUSS = "http://localhost:9222"
MINDESTBREITE = 1400          # darunter zeigt DEGIRO die kompakte Ansicht
STANDARD_BETRAG_EUR = 1000.0
LIMIT_AUFSCHLAG = 0.003        # Limit knapp über dem Kurs, damit es füllt

# Nur diese Börsen kommen in Frage. Die Kaufpunkte stammen aus
# US-Kursdaten — eine Order auf Tradegate oder Xetra liefe gegen einen
# anderen Kurs, in anderer Währung und zu anderen Handelszeiten.
ERLAUBTE_BOERSEN = ("Nasdaq", "NYSE", "NYSE Arca", "NYSE American",
                    "NYSE MKT", "Cboe BZX", "BATS")
ERLAUBTE_WAEHRUNG = "USD"

# Am 30.07.2026 in der Oberfläche abgelesen. Die Auswahl geschieht über
# den sichtbaren Text; diese Zahlen dienen nur zur Gegenprobe, ob sie
# auch angekommen ist — DEGIRO schreibt sie in ein verstecktes Feld.
ORDERTYP_WERTE = {"Limit": "0", "Stop Limit": "1", "Stop Loss": "3"}
DAUER_WERTE = {"Tagesgültig": "1", "Unbefristet": "3"}

# Der Schutzstop soll auch über Nacht liegen bleiben. Preis dafür: Bei
# einer Eröffnungslücke wird er tief unter dem Stopkurs ausgeführt.
# Wer das nicht will, trägt hier "Tagesgültig" ein.
STOP_DAUER = "Unbefristet"

# Stop Loss und nicht Stop Limit: Ein Stop Limit verkauft nur bis zum
# Grenzkurs — im schnellen Absturz, wofür der Stop da ist, greift er
# dann ins Leere. Stop Loss verkauft notfalls billiger, aber er verkauft.
STOP_ORDERTYP = "Stop Loss"

ANKER = {
    "menue": '[data-name="placeOrderMenuButton"]',
    "formular": '[data-name="orderForm"]',
    "suchfeld": '[data-name="searchInput"]',
    "wechseln": '[data-name="productChangeButton"]',
    "treffer": '[data-name="productSearchResult"]',
    "abschnitt": '[data-name="productType"]',
    "zeile": '[data-name="productItem"]',
    # Kauf/Verkauf: Der Schalter selbst ist unsichtbar (opacity-0), davor
    # liegt die Beschriftung und fängt jeden Klick ab. Angeklickt wird
    # deshalb das Label, nicht das Feld (am 30.07.2026 aufgelaufen).
    "kauf": 'label[for="buySellActionField-Kauf"]',
    "verkauf": 'label[for="buySellActionField-Verkauf"]',
    "limit": 'input[name="limit"]',
    "stopkurs": 'input[name="stopPrice"]',
    "anzahl": 'input[name="number"]',
    "betrag": 'input[name="amount"]',
    "ordertyp": '[data-name="orderForm"] [data-name="orderType"]',
    "dauer": '[data-name="orderForm"] [data-name="orderTimeType"]',
    "position": '[data-name="productPositionInfo"]',
    # Die Schaltfläche "Order platzieren" IM Formular. Sie trägt kein
    # data-name, ist aber die einzige mit type="submit" darin — oben im
    # Kopf der Seite heißt eine gleich, die öffnet nur das Bedienfeld.
    "absenden": '[data-name="orderForm"] button[type="submit"]',
    "kontrolle": '[data-name="orderConfirmation"]',
    # Nur für den Notausgang: Stimmt auf dem Kontrollbildschirm etwas
    # nicht, wird abgebrochen. "Bestätigen" kommt hier bewusst NICHT vor.
    "kontrolle_abbrechen": '[data-name="orderConfirmationCancel"]',
}


# ---------------------------------------------------------------------------
# Die Trefferzeile finden — hier entscheidet sich alles
# ---------------------------------------------------------------------------

def zeilen_lesen(seite) -> list:
    """Alle Trefferzeilen samt Abschnitt, Börse, Kürzel und Währung.

    Der Abschnitt ("Aktien" oder "ETFs") steht NICHT in der Zeile,
    sondern als eigene Überschrift davor. Er wird deshalb über die
    Reihenfolge im Dokument zugeordnet — anders ist ein Hebelpapier
    nicht von der Aktie zu unterscheiden."""
    return seite.evaluate("""() => {
        const wurzel = document.querySelector('[data-name="productSearchResult"]');
        if (!wurzel) return [];
        const alle = [...wurzel.querySelectorAll(
            '[data-name="productType"], [data-name="productName"], [data-name="productItem"]')];
        let abschnitt = '', name = '', ergebnis = [];
        for (const e of alle) {
            const dn = e.getAttribute('data-name');
            const t = (e.textContent || '').replace(/\\s+/g, ' ').trim();
            if (dn === 'productType') { abschnitt = t; continue; }
            // In der Trefferliste steht hier NUR der Firmenname, keine
            // Kennung — die kommt erst im Auftragskopf (30.07. nachgemessen).
            if (dn === 'productName') { name = t; continue; }
            // Zeilenform: "NasdaqNVDA | USDKV"
            const m = t.match(/^(.*?)([A-Z0-9.]{1,8})\\s*\\|\\s*([A-Z]{3})KV$/);
            ergebnis.push({
                abschnitt, name,
                boerse: m ? m[1].trim() : '',
                kuerzel: m ? m[2] : '',
                waehrung: m ? m[3] : '',
                roh: t.slice(0, 60)
            });
        }
        return ergebnis;
    }""")


def passende_zeilen(zeilen: list, kuerzel: str) -> list:
    """Alle Zeilen, die alle vier Bedingungen erfüllen."""
    return [z for z in zeilen
            if z["abschnitt"].startswith("Aktien")
            and z["kuerzel"] == kuerzel.upper()
            and z["waehrung"] == ERLAUBTE_WAEHRUNG
            and any(z["boerse"].startswith(b) for b in ERLAUBTE_BOERSEN)]


def suchbegriffe(ticker: str, firma: str) -> list:
    """In welcher Reihenfolge gesucht wird.

    Das Kürzel zuerst: Es ist eindeutig, und die Zeilenprüfung verlangt
    es ohnehin exakt. Der volle Firmenname taugt schlecht als
    Suchbegriff — "AxoGen Inc" liefert bei DEGIRO NICHTS, "Axogen"
    dagegen genau eine Zeile (am 30.07.2026 gemessen). Deshalb kommt
    zuletzt der Name ohne Rechtsform."""
    begriffe = [ticker.upper()]
    if firma:
        begriffe.append(firma)
        kurz = re.sub(
            r"[\s,]+(Inc|Inc\.|Corp|Corp\.|Corporation|Co|Co\.|Ltd|Ltd\.|"
            r"plc|PLC|LLC|N\.V\.|NV|S\.A\.|SA|AG|SE|Group|Holdings?)\.?$",
            "", firma.strip(), flags=re.IGNORECASE).strip()
        if kurz and kurz.lower() != firma.strip().lower():
            begriffe.append(kurz)
    # Reihenfolge behalten, Doppelte raus
    gesehen, ergebnis = set(), []
    for b in begriffe:
        if b.lower() not in gesehen:
            gesehen.add(b.lower())
            ergebnis.append(b)
    return ergebnis


def waehle_zeile(zeilen: list, kuerzel: str) -> dict:
    """Die EINE richtige Zeile — oder ein Abbruch mit Begründung.

    Vier Bedingungen zugleich, und am Ende muss genau EIN Treffer
    übrigbleiben. Bleiben mehrere oder keiner, wird nichts angeklickt:
    Bei einer Kauforder ist Abbrechen immer billiger als Raten."""
    passend = passende_zeilen(zeilen, kuerzel)
    if len(passend) == 1:
        return passend[0]
    if not passend:
        raise SystemExit(
            f"Keine passende Zeile für {kuerzel}. Gefunden wurden "
            f"{len(zeilen)} Zeilen; gesucht war der Abschnitt Aktien, "
            f"Kürzel {kuerzel}, Währung USD und eine US-Börse.\n"
            + "\n".join(f"  {z['abschnitt']:8s} {z['boerse']:26s} "
                        f"{z['kuerzel']:6s} {z['waehrung']}" for z in zeilen[:12]))
    raise SystemExit(
        f"{len(passend)} Zeilen passen gleichzeitig auf {kuerzel} — das "
        f"ist mehrdeutig, es wird nichts angeklickt:\n"
        + "\n".join(f"  {z['boerse']} {z['kuerzel']} {z['waehrung']}"
                    for z in passend))


def kopf_lesen(seite) -> dict:
    """Was steht WIRKLICH im geöffneten Auftrag? Aus der Seite gelesen,
    nicht aus den eigenen Absichten."""
    return seite.evaluate("""() => {
        const f = document.querySelector('[data-name="orderForm"]');
        if (!f) return null;
        const t = (f.textContent || '').replace(/\\s+/g, ' ');
        const m = t.match(/([A-Z0-9.]{1,8})\\s*\\|\\s*([A-Z]{2}[A-Z0-9]{9,10})\\s*\\|\\s*([^$]+?)\\s*\\$\\s*([\\d.,]+)/);
        const wert = (n) => {
            const e = f.querySelector(`input[name="${n}"]`);
            return e ? e.value : null;
        };
        return {
            kuerzel: m ? m[1] : null,
            isin: m ? m[2] : null,
            boerse: m ? m[3].trim() : null,
            kurs: m ? m[4] : null,
            limit: wert('limit'), anzahl: wert('number'), betrag: wert('amount'),
            kauf_gewaehlt: !!f.querySelector('input[name="buySellActionField"][value="Kauf"]:checked'),
            text: t.slice(0, 200)
        };
    }""")


def vorlesen(kopf: dict, firma: str) -> str:
    """Der fertige Auftrag in Worten — die einzige Kontrolle, die Mathias
    vor dem Bestätigen hat."""
    zeilen = [
        "",
        "=" * 62,
        "AUFTRAG AUSGEFÜLLT — gleich kommt der Kontrollbildschirm",
        "=" * 62,
        f"  Aktie      {kopf.get('kuerzel')}"
        + (f", {firma}" if firma else ""),
        f"  Kennung    {kopf.get('isin')}",
        f"  Börse      {kopf.get('boerse')}",
        f"  Richtung   {'KAUF' if kopf.get('kauf_gewaehlt') else '⚠ NICHT als Kauf gewählt'}",
        f"  Kurs       {kopf.get('kurs')} Dollar",
        f"  Limit      {kopf.get('limit')}",
        f"  Anzahl     {kopf.get('anzahl')}",
        f"  Betrag     {kopf.get('betrag')}",
        "=" * 62,
    ]
    return "\n".join(zeilen)


def kontrolle_lesen(seite) -> list:
    """Die Zeilen des Kontrollbildschirms "Order überprüfen".

    DEGIRO baut jede Zeile als Beschriftung und Wert nebeneinander. Die
    Werte sind innen noch einmal genauso aufgebaut ("$ 1.148" und
    "(€ 995,69)"), das gäbe Doppelmeldungen — deshalb wird alles
    übersprungen, was INNERHALB einer schon genommenen Zeile liegt."""
    return seite.evaluate("""() => {
        const p = document.querySelector('[data-name="orderConfirmation"]');
        if (!p) return [];
        const genommen = [], zeilen = [];
        for (const e of p.querySelectorAll('*')) {
            if (e.children.length !== 2) continue;
            if (e.querySelector('button')) continue;
            if (genommen.some(g => g.contains(e))) continue;
            const a = (e.children[0].textContent || '').replace(/\\s+/g, ' ').trim();
            const b = (e.children[1].textContent || '').replace(/\\s+/g, ' ').trim();
            if (!a || !b || a.length > 40 || b.length > 40) continue;
            genommen.push(e);
            zeilen.push(a + ': ' + b);
        }
        return zeilen;
    }""")


def vorlesen_kontrolle(kopf: dict, firma: str, zeilen: list) -> str:
    """Was auf dem Kontrollbildschirm steht — Wort für Wort aus der Seite.

    Das ist die letzte Kontrolle vor dem Klick, den nur Mathias macht."""
    kopfzeile = f"  {kopf.get('kuerzel')}" + (f", {firma}" if firma else "")
    return "\n".join([
        "",
        "=" * 62,
        "KONTROLLBILDSCHIRM OFFEN — jetzt liegt es an dir",
        "=" * 62,
        kopfzeile,
        f"  {kopf.get('isin')} | {kopf.get('boerse')}",
        "",
        *[f"  {z}" for z in zeilen],
        "=" * 62,
        "Das Programm ist fertig. Der Auftrag ist NICHT abgeschickt.",
        "In Chrome steht das Feld 'Order überprüfen' offen; unten sind",
        "'Abbrechen' und 'Bestätigen'. Den letzten Klick machst du.",
    ])


# ---------------------------------------------------------------------------
# Auswahlfelder und Bestand
# ---------------------------------------------------------------------------

def auswahl_setzen(seite, anker: str, wunsch: str, feldname: str,
                   erwartet: dict) -> None:
    """Ordertyp oder Orderdauer umstellen — und nachsehen, ob es ankam.

    Das sind keine gewöhnlichen Auswahlfelder, sondern nachgebaute. Der
    gewählte Text landet in einem versteckten Feld; erst dessen Wert
    beweist, dass die Umstellung gegriffen hat. React zeichnet verzögert,
    darum wird bis zu zwei Sekunden nachgesehen statt einmal geraten."""
    seite.click(anker)
    seite.wait_for_timeout(250)
    getroffen = seite.evaluate("""(wunsch) => {
        const lb = document.querySelector('[role="listbox"]');
        if (!lb) return false;
        const z = [...lb.children].find(
            c => (c.textContent || '').trim() === wunsch);
        if (!z) return false;
        z.click();
        return true;
    }""", wunsch)
    if not getroffen:
        raise SystemExit(f"'{wunsch}' steht nicht zur Auswahl — Abbruch.")

    soll = erwartet[wunsch]
    for _ in range(20):
        seite.wait_for_timeout(100)
        ist = seite.evaluate(
            """(n) => { const e = document.querySelector(
                   `[data-name="orderForm"] input[name="${n}"]`);
                        return e ? e.value : null; }""", feldname)
        if ist == soll:
            return
    raise SystemExit(
        f"'{wunsch}' wurde angeklickt, ist aber nicht angekommen "
        f"(erwartet {soll}, steht {ist}) — Abbruch, es wird nichts "
        f"abgeschickt.")


def position_lesen(seite):
    """Wie viele Stücke liegen wirklich im Depot?

    Steht im Bedienfeld als "Aktuelle Position $ 1.251,60 (30 St.)".
    Diese Zahl ist die Grundlage jedes Verkaufs — geraten wird nichts,
    denn ein Kauf kann auch nur teilweise ausgeführt worden sein."""
    roh = seite.evaluate(
        """() => { const e = document.querySelector(
               '[data-name="productPositionInfo"]');
                   return e ? e.textContent.replace(/\\s+/g, ' ').trim() : ''; }""")
    m = re.search(r"\((\d+(?:[.\s]\d{3})*)\s*St\.", roh or "")
    if not m:
        return None, roh
    return int(re.sub(r"[.\s]", "", m.group(1))), roh


# ---------------------------------------------------------------------------
# Ablauf
# ---------------------------------------------------------------------------

def verbinde():
    """An Mathias' laufenden Chrome anhängen. Kein eigener Browser, keine
    Zugangsdaten — er ist dort schon angemeldet."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Bitte installieren: pip install playwright")
    p = sync_playwright().start()
    try:
        browser = p.chromium.connect_over_cdp(CHROME_ANSCHLUSS)
    except Exception as e:
        p.stop()
        sys.exit(
            f"Chrome nicht erreichbar ({type(e).__name__}).\n"
            f"Bitte zuerst starten:\n"
            f"    python trading_chrome.py")
    seiten = [s for ktx in browser.contexts for s in ktx.pages]
    # Nach dem Anmelden bleibt die Anmeldeseite oft als zweite
    # Registerkarte offen. Die erstbeste zu nehmen führte dort hinein —
    # gesucht ist die Handelsansicht, nicht /login.
    handel = [s for s in seiten
              if "/trader/" in (s.url or "") and "/login" not in (s.url or "")]
    ziel = handel[0] if handel else None
    if ziel is None:
        p.stop()
        offen = [s.url for s in seiten if "degiro" in (s.url or "")]
        sys.exit("Keine angemeldete DEGIRO-Handelsansicht offen"
                 + (f" (gefunden: {offen})" if offen else "")
                 + ".\nBitte anmelden: python trading_chrome.py")
    fenster_breit_genug(ziel)
    return p, browser, ziel


def fenster_breit_genug(seite) -> None:
    """Ein zu schmales Fenster breiter machen.

    Unter etwa 1200 Punkten schaltet DEGIRO auf die kompakte Ansicht um.
    Dort gibt es kein "Order platzieren" im Kopf mehr, sondern nur einen
    Menüknopf — sämtliche Anker fehlen dann. Statt daran zu scheitern
    wird das Fenster einfach breit genug gemacht."""
    try:
        cdp = seite.context.new_cdp_session(seite)
        info = cdp.send("Browser.getWindowForTarget")
        b = info.get("bounds", {})
        if b.get("windowState") != "normal":
            cdp.send("Browser.setWindowBounds",
                     {"windowId": info["windowId"],
                      "bounds": {"windowState": "normal"}})
            b = cdp.send("Browser.getWindowForTarget").get("bounds", {})
        if b.get("width", 0) < MINDESTBREITE:
            print(f"Fenster ist {b.get('width')} Punkte breit — DEGIRO "
                  f"zeigt dann die kompakte Ansicht. Wird verbreitert.")
            cdp.send("Browser.setWindowBounds",
                     {"windowId": info["windowId"],
                      "bounds": {"width": MINDESTBREITE,
                                 "height": max(b.get("height", 0), 900)}})
            seite.wait_for_timeout(800)
    except Exception as e:
        print(f"Fensterbreite nicht prüfbar ({type(e).__name__}) — "
              f"falls Anker fehlen, bitte das Fenster breiter ziehen.")


def papier_oeffnen(seite, ticker: str, firma: str) -> dict:
    """Bedienfeld öffnen, das richtige Papier suchen, Kaufdialog öffnen.

    Für alle drei Stufen derselbe Weg — auch beim Verkaufen führt DEGIRO
    nur hier hinein. Zurück kommt die gewählte Trefferzeile."""
    if seite.query_selector(ANKER["formular"]) is None:
        seite.click(ANKER["menue"])
        seite.wait_for_timeout(400)
        seite.get_by_text("Schnell & einfach", exact=False).first.click()
        seite.wait_for_selector(ANKER["suchfeld"], timeout=8000)
    elif seite.query_selector(ANKER["suchfeld"]) is None:
        # Das Bedienfeld steht schon offen, aber auf einem ANDEREN Papier.
        # Dann gibt es kein Suchfeld, sondern nur "Ändern" — ohne diesen
        # Klick landet die Suche im Nichts (am 30.07. live aufgelaufen).
        seite.click(ANKER["wechseln"])
        seite.wait_for_selector(ANKER["suchfeld"], timeout=8000)

    zeilen, ziel = [], None
    for such in suchbegriffe(ticker, firma):
        print(f"Suche nach {such!r} …")
        # Das Suchfeld behält nach "Ändern" den alten Text. Ohne Leeren
        # hängt die neue Eingabe hinten an ("NVIDIA" + "Axogen") und die
        # Suche findet gar nichts. fill("") allein greift bei diesem
        # React-Feld nicht verlässlich, darum von Hand markieren.
        feld = seite.query_selector(ANKER["suchfeld"])
        feld.click()
        seite.keyboard.press("Control+A")
        seite.keyboard.press("Delete")
        feld.type(such, delay=40)
        seite.wait_for_timeout(1200)

        zeilen = zeilen_lesen(seite)
        if not zeilen:                   # Trefferliste manchmal langsam
            seite.wait_for_timeout(1500)
            zeilen = zeilen_lesen(seite)
        passend = passende_zeilen(zeilen, ticker)
        print(f"  {len(zeilen)} Trefferzeile(n), davon {len(passend)} passend.")
        if len(passend) == 1:
            ziel = passend[0]
            break

    if ziel is None:                     # bricht mit voller Begründung ab
        ziel = waehle_zeile(zeilen, ticker)
    print(f"Gewählt: {ziel['name']} | {ziel['boerse']} | "
          f"{ziel['kuerzel']} | {ziel['waehrung']}")

    # Die K-Schaltfläche GENAU dieser Zeile
    seite.evaluate("""(roh) => {
        const zeilen = [...document.querySelectorAll(
            '[data-name="productSearchResult"] [data-name="productItem"]')];
        const z = zeilen.find(e =>
            (e.textContent||'').replace(/\\s+/g,' ').trim().startsWith(roh));
        if (!z) throw new Error('Zeile beim Klicken nicht mehr da');
        const k = [...z.querySelectorAll('button')]
            .find(b => (b.textContent||'').trim() === 'K');
        if (!k) throw new Error('K-Schaltflaeche fehlt');
        k.click();
    }""", ziel["roh"])
    seite.wait_for_selector(ANKER["formular"], timeout=8000)
    seite.wait_for_selector(ANKER["ordertyp"], timeout=8000)

    kopf = kopf_lesen(seite)
    if kopf.get("kuerzel") != ticker.upper():
        raise SystemExit(
            f"Der geöffnete Auftrag zeigt {kopf.get('kuerzel')}, "
            f"erwartet war {ticker.upper()} — Abbruch, es wird nichts "
            f"eingetragen.")
    return ziel


def absenden_und_vorlesen(seite, ticker: str, firma: str) -> int:
    """Der letzte Schritt, den das Programm noch selbst macht.

    "Order platzieren" schickt NICHTS ab, es öffnet nur den
    Kontrollbildschirm mit "Abbrechen" und "Bestätigen". Erst
    "Bestätigen" führt aus — und das macht Mathias."""
    seite.click(ANKER["absenden"])
    try:
        seite.wait_for_selector(ANKER["kontrolle"], timeout=10000)
    except Exception:
        print("\n⚠ Der Kontrollbildschirm ist nicht aufgegangen. Bitte "
              "in Chrome nachsehen, bevor du irgendetwas bestätigst.")
        return 1

    # Noch einmal gegengeprüft, diesmal auf dem Kontrollbildschirm:
    # Steht dort ein anderes Papier, wird abgebrochen statt gemeldet.
    pruef = kopf_lesen(seite)
    if pruef and pruef.get("kuerzel") != ticker.upper():
        seite.click(ANKER["kontrolle_abbrechen"])
        raise SystemExit(
            f"Der Kontrollbildschirm zeigt {pruef.get('kuerzel')} statt "
            f"{ticker.upper()} — abgebrochen, es wurde nichts ausgeführt.")

    print(vorlesen_kontrolle(pruef, firma, kontrolle_lesen(seite)))
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="Bereitet eine DEGIRO-Order vor. Bestätigt wird "
                    "von Hand.")
    ap.add_argument("ticker", nargs="?", help="Kürzel, z. B. NVDA")
    ap.add_argument("--stufe", choices=("kauf", "stop", "ziel"),
                    default="kauf",
                    help="kauf: Limit-Kauf über den Betrag. "
                         "stop: Schutzstop auf den ganzen Bestand. "
                         "ziel: Verkauf beim Kursziel.")
    ap.add_argument("--firma", default="",
                    help="Voller Firmenname für die Suche — trifft besser "
                         "als das Kürzel")
    ap.add_argument("--betrag", type=float, default=STANDARD_BETRAG_EUR)
    ap.add_argument("--limit", type=float, default=None,
                    help="Limit in Dollar; ohne Angabe Kurs plus "
                         f"{LIMIT_AUFSCHLAG*100:.1f} Prozent")
    ap.add_argument("--stop", type=float, default=None,
                    help="Stopkurs in Dollar (Stufe stop)")
    ap.add_argument("--anzahl", type=int, default=None,
                    help="Stückzahl beim Verkaufen; ohne Angabe der "
                         "gesamte Bestand aus dem Depot")
    ap.add_argument("--pruefe", action="store_true",
                    help="Nur nachsehen, ob alle Anker in der Oberfläche "
                         "noch da sind. Ändert nichts.")
    ap.add_argument("--abbrechen", action="store_true",
                    help="Einen offenen Kontrollbildschirm verwerfen. "
                         "Klickt 'Abbrechen', nie 'Bestätigen'.")
    args = ap.parse_args()

    if not args.ticker and not (args.pruefe or args.abbrechen):
        sys.exit("Bitte ein Kürzel angeben, z. B.: "
                 "python degiro_order.py NVDA --firma \"NVIDIA Corp\"")
    if args.stufe == "stop" and args.stop is None:
        sys.exit("Stufe 'stop' braucht den Stopkurs: --stop 41.20")
    if args.stufe == "ziel" and args.limit is None:
        sys.exit("Stufe 'ziel' braucht das Kursziel: --limit 48.50")

    p, browser, seite = verbinde()
    try:
        if args.pruefe:
            fehlend = [k for k, s in ANKER.items()
                       if seite.query_selector(s) is None]
            print(f"DEGIRO-Tab: {seite.url[:60]}")
            print(f"Anker gefunden: {len(ANKER) - len(fehlend)} von {len(ANKER)}")
            if fehlend:
                print("Nicht gefunden (kann normal sein, solange das "
                      "Bedienfeld zu ist): " + ", ".join(fehlend))
            return 0

        if args.abbrechen:
            if seite.query_selector(ANKER["kontrolle"]) is None:
                print("Es steht kein Kontrollbildschirm offen.")
                return 0
            seite.click(ANKER["kontrolle_abbrechen"])
            seite.wait_for_timeout(800)
            noch_offen = seite.query_selector(ANKER["kontrolle"]) is not None
            print("Kontrollbildschirm verworfen — es wurde nichts "
                  "ausgeführt." if not noch_offen else
                  "⚠ Der Kontrollbildschirm ist noch offen, bitte "
                  "in Chrome nachsehen.")
            return 1 if noch_offen else 0

        ziel = papier_oeffnen(seite, args.ticker, args.firma)
        kopf = kopf_lesen(seite)

        if args.stufe == "kauf":
            kurs = float(str(kopf["kurs"]).replace(".", "").replace(",", "."))
            limit = (args.limit if args.limit
                     else round(kurs * (1 + LIMIT_AUFSCHLAG), 2))
            seite.fill(ANKER["limit"], f"{limit:.2f}".replace(".", ","))
            seite.fill(ANKER["betrag"], f"{args.betrag:.0f}")
            seite.wait_for_timeout(900)      # DEGIRO rechnet die Anzahl aus

            kopf = kopf_lesen(seite)
            print(vorlesen(kopf, ziel["name"]))
            if not kopf.get("anzahl"):
                print("\n⚠ Es steht keine Anzahl im Auftrag — es wird "
                      "nichts abgeschickt. Bitte nachsehen.")
                return 1
            return absenden_und_vorlesen(seite, args.ticker, ziel["name"])

        # ---- Verkaufsstufen: Schutzstop und Kursziel -------------------
        # Beide verkaufen etwas, das schon im Depot liegt. Die Stückzahl
        # kommt daher aus dem Depot und nicht aus einer Annahme — ein
        # Kauf kann auch nur teilweise ausgeführt worden sein.
        bestand, roh = position_lesen(seite)
        if bestand is None:
            raise SystemExit(
                f"Der Bestand ist nicht lesbar ({roh!r}) — Abbruch, es "
                f"wird nichts eingetragen.")
        anzahl = args.anzahl if args.anzahl else bestand
        if anzahl > bestand:
            raise SystemExit(
                f"{anzahl} Stück verlangt, im Depot liegen aber nur "
                f"{bestand} — Abbruch. Mehr zu verkaufen als man hat, "
                f"wäre ein Leerverkauf.")
        print(f"Im Depot: {bestand} Stück, verkauft werden {anzahl}.")

        seite.click(ANKER["verkauf"])
        seite.wait_for_timeout(300)

        if args.stufe == "stop":
            auswahl_setzen(seite, ANKER["ordertyp"], STOP_ORDERTYP,
                           "orderType", ORDERTYP_WERTE)
            auswahl_setzen(seite, ANKER["dauer"], STOP_DAUER,
                           "orderTimeType", DAUER_WERTE)
            seite.wait_for_selector(ANKER["stopkurs"], timeout=8000)
            seite.fill(ANKER["stopkurs"],
                       f"{args.stop:.2f}".replace(".", ","))
        else:
            auswahl_setzen(seite, ANKER["ordertyp"], "Limit",
                           "orderType", ORDERTYP_WERTE)
            seite.fill(ANKER["limit"],
                       f"{args.limit:.2f}".replace(".", ","))

        seite.fill(ANKER["anzahl"], str(anzahl))
        seite.wait_for_timeout(900)

        kopf = kopf_lesen(seite)
        if str(kopf.get("anzahl") or "").strip() != str(anzahl):
            raise SystemExit(
                f"Im Auftrag steht die Anzahl {kopf.get('anzahl')!r} "
                f"statt {anzahl} — Abbruch, es wird nichts abgeschickt.")
        if kopf.get("kauf_gewaehlt"):
            raise SystemExit(
                "Der Auftrag steht auf KAUF, verlangt war ein Verkauf — "
                "Abbruch.")
        return absenden_und_vorlesen(seite, args.ticker, ziel["name"])
    finally:
        try:
            p.stop()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
