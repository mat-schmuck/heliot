"""Warum weist die SEC unsere Cloud-Laeufe ab? (26.08.2026)

BEFUND, der dieses Werkzeug noetig machte: Der Insider-Scanner hat in
der Cloud NIE einen Tagesindex bekommen - schon der erste Lauf am
14.08.2026 endete mit HTTP 403, und jeder seither. Von Mathias' Rechner
aus liefert dieselbe Adresse 940 KB. Die SEC nennt als Grund "Your
Request Originates from an Undeclared Automated Tool", also ihre
Kennsatz-Meldung.

ZWEI moegliche Ursachen, die dieses Werkzeug UNTERSCHEIDET:
  (a) Das Secret SEC_USER_AGENT kommt beschaedigt an (Anfuehrungs-
      zeichen, Zeilenumbruch, falsches Format).
  (b) Die SEC weist die Adressbereiche der GitHub-Rechner ab, egal mit
      welchem Kennsatz.
Dafuer laeuft derselbe Abruf zweimal: einmal mit dem Secret, einmal mit
einem fest eingebauten Kontroll-Kennsatz im SEC-Format. Antwortet der
Kontroll-Kennsatz mit 200, liegt es am Secret; antworten beide mit 403,
ist es die Adresse.

DER WERT DES SECRETS WIRD NIE AUSGEGEBEN - nur Laenge und Bauform
(enthaelt Klammeraffe, Leerzeichen, Anfuehrungszeichen, Zeilenumbruch).
Das genuegt zur Diagnose und verraet nichts.
"""

import os
import re
import sys
from datetime import date, timedelta

import requests

# Kontroll-Kennsatz im von der SEC verlangten Format (Name plus
# Kontaktadresse). Bewusst eine neutrale Projekt-Adresse und NICHT
# Mathias' private E-Mail - die geht niemanden etwas an.
KONTROLL_UA = "Heliot Pattern Scanner kontakt@heliot-scanner.example"


def letzter_werktag():
    """Der juengste Wochentag vor heute - fuer den gibt es einen Index."""
    d = date.today() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def bauform(wert):
    """Beschreibt einen Geheimwert, ohne ihn zu verraten."""
    if wert is None:
        return "nicht gesetzt"
    roh = wert
    hat_at = "ja" if "@" in roh else "NEIN"
    hat_leer = "ja" if " " in roh else "NEIN"
    anfuehrung = "JA" if any(z in roh for z in (chr(34), chr(39))) else "nein"
    umbruch = "JA" if any(z in roh for z in (chr(10), chr(13))) else "nein"
    rand = "JA" if roh != roh.strip() else "nein"
    return (f"{len(roh)} Zeichen; Klammeraffe {hat_at}; "
            f"Leerzeichen {hat_leer}; Anfuehrungszeichen {anfuehrung}; "
            f"Zeilenumbruch {umbruch}; Randleerzeichen {rand}")


def abruf(url, ua, name):
    kopf = {"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}
    try:
        r = requests.get(url, headers=kopf, timeout=40)
    except Exception as e:
        print(f"  {name}: FEHLER {type(e).__name__}: {e}")
        return None
    print(f"  {name}: HTTP {r.status_code}, {len(r.content)} Bytes")
    if r.status_code != 200:
        text = re.sub(r"<[^>]+>", " ", r.text)
        text = re.sub(r"\s+", " ", text).strip()
        print(f"     Grund laut SEC: {text[:120]}")
    return r.status_code


def main():
    d = letzter_werktag()
    q = (d.month - 1) // 3 + 1
    url = (f"https://www.sec.gov/Archives/edgar/daily-index/{d.year}/"
           f"QTR{q}/form.{d:%Y%m%d}.idx")
    print(f"Pruefadresse: Tagesindex vom {d}")

    roh = os.environ.get("SEC_USER_AGENT")
    print(f"SEC_USER_AGENT: {bauform(roh)}")

    ergebnisse = {}
    if roh:
        ergebnisse["secret"] = abruf(url, roh.strip(), "mit dem Secret")
    ergebnisse["kontrolle"] = abruf(url, KONTROLL_UA, "mit Kontroll-Kennsatz")

    print("")
    if not roh:
        print("BEFUND: Kein Secret gesetzt - dieser Lauf sagt nur, ob die "
              "Adresse ueberhaupt durchkommt (Kontrolle oben).")
    elif ergebnisse.get("kontrolle") == 200 and ergebnisse.get("secret") != 200:
        print("BEFUND: Das Secret ist schuld - derselbe Rechner kommt mit "
              "dem Kontroll-Kennsatz durch.")
    elif ergebnisse.get("kontrolle") == 200 and ergebnisse.get("secret") == 200:
        print("BEFUND: Beide kommen durch - der Fehler liegt woanders "
              "(Zeitpunkt, Adresse, voruebergehende Sperre).")
    elif ergebnisse.get("kontrolle") != 200:
        print("BEFUND: Auch der Kontroll-Kennsatz wird abgewiesen - die SEC "
              "sperrt die Adressbereiche der GitHub-Rechner.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
