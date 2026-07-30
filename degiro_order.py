#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DEGIRO-ORDER VORBEREITEN — die letzte Auslösung bleibt bei Mathias
==================================================================
Mathias am 30.07.2026: "Alles, was mit Degiro zu tun hat, geht auf mein
Konto, baue daher dieses Tool mit manueller finaler Auslösung."

WAS DIESES PROGRAMM TUT
  Es meldet sich bei DEGIRO an, sucht die Aktie, oeffnet den Kaufdialog,
  stellt den Ordertyp, rechnet die Stueckzahl fuer den gewuenschten
  Gegenwert aus und traegt alles ein. Dann HAELT ES AN und liest den
  fertigen Auftrag vor.

WAS ES NICHT TUT
  Es drueckt niemals auf Bestaetigen. Der letzte Klick gehoert Mathias.
  Die Sperre BESTAETIGEN_GEHOERT_MATHIAS steht bewusst als Konstante im
  Code und nicht als Aufrufoption — eine Option waere irgendwann
  versehentlich gesetzt.

WARUM VORGELESEN WIRD
  Mathias sieht den Bildschirm nicht. Beim TraderFox-Bot ist genau der
  Fehler passiert, vor dem hier geschuetzt werden muss: Die Suche traf
  die falsche Zeile, und der Alarm landete auf der falschen Aktie. Bei
  einem Alarm ist das aergerlich, bei einer Order kostet es Geld.
  Deshalb wird VOR dem Anhalten zurueckgelesen, was wirklich im
  Orderfenster steht — Name, Kennung, Boerse, Ordertyp, Limit,
  Stueckzahl und Gegenwert. Nicht das, was das Programm eingetragen
  haben WOLLTE, sondern das, was die Seite hergibt.

ZUGANGSDATEN
  Ausschliesslich aus der Umgebung, nie im Code, nie im Protokoll:
      DEGIRO_USER, DEGIRO_PASS, DEGIRO_TOTP   (letzteres bei 2FA)
  Mathias legt sie selbst an. Sie werden nirgends ausgegeben, auch nicht
  in Fehlermeldungen — deshalb wird bei Ausnahmen nur der TYP gemeldet.

  Bewusst LOKAL auf Mathias' Rechner, nicht in GitHub Actions: Bei
  TraderFox ging es um einen Datendienst, hier um ein Depot.

Aufruf:
    python degiro_order.py NVDA
    python degiro_order.py NVDA --betrag 2000
    python degiro_order.py NVDA --limit 45.20
    python degiro_order.py --pruefe          nur Rechnung und Umrechnung
"""

import argparse
import os
import sys

# ===========================================================================
# HARTE SPERRE. Nicht als Aufrufoption ausgefuehrt, damit sie nicht
# versehentlich gesetzt werden kann. Wer sie aufhebt, tut das bewusst und
# im Quelltext.
BESTAETIGEN_GEHOERT_MATHIAS = True
# ===========================================================================

STANDARD_BETRAG_EUR = 1000.0
# Aufschlag auf den aktuellen Kurs beim Limit: Die Order soll ausgefuehrt
# werden, aber nicht zu jedem Preis. 0,3 Prozent ist der Vorschlag —
# genug Luft fuer den Spread, wenig genug als Deckel.
LIMIT_AUFSCHLAG = 0.003


def eurusd() -> float:
    """Aktueller Euro-Dollar-Kurs. Ohne ihn stimmt die Stueckzahl nicht:
    Die Kaufpunkte stehen in Dollar, der Gegenwert soll in Euro
    stimmen."""
    import yfinance as yf
    d = yf.download("EURUSD=X", period="5d", interval="1d",
                    progress=False, auto_adjust=False)
    if d is None or d.empty:
        raise RuntimeError("Euro-Dollar-Kurs nicht abrufbar.")
    import pandas as pd
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    return float(d["Close"].dropna().iloc[-1])


def kurs_von(ticker: str) -> float:
    import yfinance as yf
    import pandas as pd
    d = yf.download(ticker, period="5d", interval="1d", progress=False,
                    auto_adjust=False)
    if d is None or d.empty:
        raise RuntimeError(f"Kein Kurs für {ticker}.")
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    return float(d["Close"].dropna().iloc[-1])


def stueckzahl(betrag_eur: float, kurs_usd: float, eur_usd: float) -> dict:
    """Wie viele Stueck ergeben den gewuenschten Gegenwert?

    ABGERUNDET, nie aufgerundet: Lieber etwas unter dem Wunschbetrag als
    darueber. Bei einem Kurs ueber dem Betrag kommt null heraus — dann
    ist die Aktie schlicht zu teuer fuer diese Positionsgroesse, und das
    muss gesagt werden statt stillschweigend eine Aktie zu kaufen."""
    if kurs_usd <= 0 or eur_usd <= 0:
        raise ValueError("Kurs oder Wechselkurs unbrauchbar.")
    kurs_eur = kurs_usd / eur_usd
    stueck = int(betrag_eur // kurs_eur)
    return {
        "stueck": stueck,
        "kurs_usd": kurs_usd,
        "kurs_eur": kurs_eur,
        "eur_usd": eur_usd,
        "gegenwert_eur": stueck * kurs_eur,
        "gegenwert_usd": stueck * kurs_usd,
        "zu_teuer": stueck == 0,
    }


def limitpreis(kurs_usd: float, aufschlag=LIMIT_AUFSCHLAG) -> float:
    """Limit knapp ueber dem Kurs: soll ausgefuehrt werden, aber nicht zu
    jedem Preis. Auf zwei Stellen gerundet wie an der Boerse ueblich."""
    return round(kurs_usd * (1 + aufschlag), 2)


def vorlesen(ticker: str, firma: str, rechnung: dict, limit: float,
             ordertyp: str = "Limit") -> str:
    """Der Auftrag in Worten. Wird VOR dem Anhalten ausgegeben."""
    zeilen = [
        f"Kaufauftrag vorbereitet für {ticker}"
        + (f", {firma}" if firma else ""),
        f"Ordertyp {ordertyp}, Limit {limit:.2f} Dollar",
        f"Stückzahl {rechnung['stueck']}, "
        f"Gegenwert {rechnung['gegenwert_eur']:.0f} Euro "
        f"(Kurs {rechnung['kurs_usd']:.2f} Dollar, "
        f"Euro-Dollar {rechnung['eur_usd']:.4f})",
    ]
    return "\n".join(zeilen)


def zugangsdaten() -> dict:
    """Aus der Umgebung. Fehlt etwas, wird der NAME genannt, nie ein Wert."""
    daten = {
        "user": os.environ.get("DEGIRO_USER", "").strip(),
        "pass": os.environ.get("DEGIRO_PASS", "").strip(),
        "totp": os.environ.get("DEGIRO_TOTP", "").strip(),
    }
    fehlend = [n for n, s in (("DEGIRO_USER", daten["user"]),
                              ("DEGIRO_PASS", daten["pass"])) if not s]
    if fehlend:
        sys.exit("Bitte setzen: " + ", ".join(fehlend)
                 + ". Bei aktivierter Zwei-Faktor-Anmeldung zusätzlich "
                   "DEGIRO_TOTP. Die Werte trägt Mathias selbst ein; sie "
                   "werden nie ausgegeben.")
    return daten


def main():
    ap = argparse.ArgumentParser(
        description="Bereitet eine DEGIRO-Kauforder vor. Bestätigt wird "
                    "von Hand.")
    ap.add_argument("ticker", nargs="?", help="Kürzel, z. B. NVDA")
    ap.add_argument("--betrag", type=float, default=STANDARD_BETRAG_EUR,
                    help=f"Gegenwert in Euro (Vorgabe {STANDARD_BETRAG_EUR:.0f})")
    ap.add_argument("--limit", type=float, default=None,
                    help="Limitpreis in Dollar; ohne Angabe Kurs plus "
                         f"{LIMIT_AUFSCHLAG*100:.1f} Prozent")
    ap.add_argument("--firma", default="", help="Firmenname für die Suche")
    ap.add_argument("--pruefe", action="store_true",
                    help="NUR rechnen: Stückzahl und Umrechnung zeigen, "
                         "ohne DEGIRO überhaupt anzufassen")
    args = ap.parse_args()

    if not args.ticker:
        sys.exit("Bitte ein Kürzel angeben, z. B.: python degiro_order.py NVDA")

    kurs = kurs_von(args.ticker)
    wechsel = eurusd()
    rechnung = stueckzahl(args.betrag, kurs, wechsel)
    limit = args.limit if args.limit else limitpreis(kurs)

    print(vorlesen(args.ticker, args.firma, rechnung, limit))

    if rechnung["zu_teuer"]:
        sys.exit(f"\nEine einzelne Aktie kostet mehr als {args.betrag:.0f} "
                 f"Euro — für diese Positionsgröße nicht handelbar.")

    if args.pruefe:
        print("\n(Nur gerechnet — DEGIRO wurde nicht angefasst.)")
        return 0

    zugangsdaten()          # prueft nur, ob sie gesetzt sind
    print("\nDer Weg über die DEGIRO-Oberfläche ist noch nicht gebaut.")
    print("Dafür muss die Selektorkarte des Orderfensters aufgenommen "
          "werden — Suchfeld, Kaufen-Schaltfläche, Ordertyp, Limitfeld, "
          "Stückzahlfeld und die Rückleseflächen.")
    print("Bis dahin liefert dieses Programm die fertige Rechnung, die "
          "Mathias von Hand einträgt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
