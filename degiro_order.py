#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DEGIRO-ORDER VORBEREITEN — bestätigt wird von Hand
===================================================
Mathias am 30.07.2026: "Ich möchte UNBEDINGT, dass ich nur bestätigen
muss, alles davor soll das Programm machen."

Genau so ist es gebaut. Das Programm geht den ganzen Weg — Order
platzieren, suchen, richtige Zeile finden, Kaufdialog öffnen, Ordertyp,
Limit und Betrag eintragen, auf "Order platzieren" klicken — und HÄLT
DANN AN, wenn das Bestätigungsfenster offen ist. Es liest vor, was
dort steht. Der letzte Klick gehört Mathias.

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
    Die Feld-IDs enthalten Zeitstempel und sind NICHT brauchbar; die
    name-Attribute schon.

    Wichtiger Fund: Es gibt ein Feld "Betrag (€)". DEGIRO rechnet die
    Stückzahl daraus selbst aus. Der Umweg über einen eigenen
    Euro-Dollar-Kurs entfällt damit — und mit ihm eine Fehlerquelle.

WO ES LÄUFT
    An Mathias' eigenem Chrome, in dem er bei DEGIRO angemeldet ist.
    Damit braucht das Programm KEINE Zugangsdaten: kein Passwort, kein
    TOTP-Schlüssel, nichts zu speichern. Bei einem Depot ist das der
    entscheidende Unterschied zum TraderFox-Bot, wo es nur um einen
    Datendienst ging.

    Chrome muss dafür einmalig mit einem Debug-Anschluss gestartet
    werden:
        chrome.exe --remote-debugging-port=9222

Aufruf:
    python degiro_order.py NVDA --firma "NVIDIA Corp"
    python degiro_order.py NVDA --firma "NVIDIA Corp" --betrag 2000
    python degiro_order.py NVDA --firma "NVIDIA Corp" --limit 195.50
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
STANDARD_BETRAG_EUR = 1000.0
LIMIT_AUFSCHLAG = 0.003        # Limit knapp über dem Kurs, damit es füllt

# Nur diese Börsen kommen in Frage. Die Kaufpunkte stammen aus
# US-Kursdaten — eine Order auf Tradegate oder Xetra liefe gegen einen
# anderen Kurs, in anderer Währung und zu anderen Handelszeiten.
ERLAUBTE_BOERSEN = ("Nasdaq", "NYSE", "NYSE Arca", "NYSE American",
                    "NYSE MKT", "Cboe BZX", "BATS")
ERLAUBTE_WAEHRUNG = "USD"

ANKER = {
    "menue": '[data-name="placeOrderMenuButton"]',
    "formular": '[data-name="orderForm"]',
    "suchfeld": '[data-name="searchInput"]',
    "wechseln": '[data-name="productChangeButton"]',
    "treffer": '[data-name="productSearchResult"]',
    "abschnitt": '[data-name="productType"]',
    "zeile": '[data-name="productItem"]',
    "kauf": 'input[name="buySellActionField"][value="Kauf"]',
    "limit": 'input[name="limit"]',
    "anzahl": 'input[name="number"]',
    "betrag": 'input[name="amount"]',
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


def waehle_zeile(zeilen: list, kuerzel: str) -> dict:
    """Die EINE richtige Zeile — oder ein Abbruch mit Begründung.

    Vier Bedingungen zugleich, und am Ende muss genau EIN Treffer
    übrigbleiben. Bleiben mehrere oder keiner, wird nichts angeklickt:
    Bei einer Kauforder ist Abbrechen immer billiger als Raten."""
    passend = [z for z in zeilen
               if z["abschnitt"].startswith("Aktien")
               and z["kuerzel"] == kuerzel.upper()
               and z["waehrung"] == ERLAUBTE_WAEHRUNG
               and any(z["boerse"].startswith(b) for b in ERLAUBTE_BOERSEN)]
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
        "AUFTRAG STEHT — bitte prüfen und dann selbst bestätigen",
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
            f"Chrome muss mit Debug-Anschluss laufen:\n"
            f"    chrome.exe --remote-debugging-port=9222\n"
            f"Am einfachsten in die Chrome-Verknüpfung eintragen.")
    seiten = [s for ktx in browser.contexts for s in ktx.pages]
    ziel = next((s for s in seiten if "degiro" in (s.url or "")), None)
    if ziel is None:
        p.stop()
        sys.exit("Kein DEGIRO-Tab offen. Bitte trader.degiro.nl öffnen "
                 "und anmelden.")
    return p, browser, ziel


def main():
    ap = argparse.ArgumentParser(
        description="Bereitet eine DEGIRO-Kauforder vor. Bestätigt wird "
                    "von Hand.")
    ap.add_argument("ticker", nargs="?", help="Kürzel, z. B. NVDA")
    ap.add_argument("--firma", default="",
                    help="Voller Firmenname für die Suche — trifft besser "
                         "als das Kürzel")
    ap.add_argument("--betrag", type=float, default=STANDARD_BETRAG_EUR)
    ap.add_argument("--limit", type=float, default=None,
                    help="Limit in Dollar; ohne Angabe Kurs plus "
                         f"{LIMIT_AUFSCHLAG*100:.1f} Prozent")
    ap.add_argument("--pruefe", action="store_true",
                    help="Nur nachsehen, ob alle Anker in der Oberfläche "
                         "noch da sind. Ändert nichts.")
    args = ap.parse_args()

    if not args.ticker and not args.pruefe:
        sys.exit("Bitte ein Kürzel angeben, z. B.: "
                 "python degiro_order.py NVDA --firma \"NVIDIA Corp\"")

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

        such = args.firma or args.ticker
        print(f"Suche nach {such!r} …")
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
        if not zeilen:                       # Trefferliste manchmal langsam
            seite.wait_for_timeout(1500)
            zeilen = zeilen_lesen(seite)
        print(f"{len(zeilen)} Trefferzeile(n) gefunden.")
        ziel = waehle_zeile(zeilen, args.ticker)
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
        seite.wait_for_selector(ANKER["limit"], timeout=8000)

        kopf = kopf_lesen(seite)
        if kopf.get("kuerzel") != args.ticker.upper():
            raise SystemExit(
                f"Der geöffnete Auftrag zeigt {kopf.get('kuerzel')}, "
                f"erwartet war {args.ticker.upper()} — Abbruch, es wird "
                f"nichts eingetragen.")

        kurs = float(str(kopf["kurs"]).replace(".", "").replace(",", "."))
        limit = args.limit if args.limit else round(kurs * (1 + LIMIT_AUFSCHLAG), 2)

        seite.fill(ANKER["limit"], f"{limit:.2f}".replace(".", ","))
        seite.fill(ANKER["betrag"], f"{args.betrag:.0f}")
        seite.wait_for_timeout(900)      # DEGIRO rechnet die Anzahl aus

        kopf = kopf_lesen(seite)
        print(vorlesen(kopf, ziel["name"]))

        if not kopf.get("anzahl"):
            print("\n⚠ Es steht keine Anzahl im Auftrag — bitte nicht "
                  "bestätigen, sondern nachsehen.")
            return 1

        print("\nDas Programm hält hier an. Der Auftrag ist ausgefüllt, "
              "aber NICHT abgeschickt.")
        print("Zum Abschicken in Chrome auf 'Order platzieren' und dann "
              "auf 'Bestätigen'.")
        return 0
    finally:
        try:
            p.stop()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
