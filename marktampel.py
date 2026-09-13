"""Marktampel: gruen, gelb oder rot — der Zustand des Gesamtmarkts.

WOZU (Gerhards Freigabe vom 31.08.2026, Baustein 4 des Einbau-Papiers,
Regelfrage G10 nach bestem Wissen entschieden): Leif Soreide steuert
seine Aggressivitaet ueber eine Marktampel, Oliver Kell handelt gross
nur, wenn S&P 500 und Nasdaq selbst im Aufwaertstrend sind. Bei uns gab
es bisher keine Marktzustands-Groesse ausser dem Red-to-Green-Gap.

WAS SIE TUT UND WAS NICHT: Die Ampel INFORMIERT nur. Sie unterdrueckt
keine Meldung und filtert nichts — erst wenn das Logbuch nach einigen
Wochen zeigt, wie die Trefferquote je Farbe aussieht, lohnt die
Diskussion ueber Konsequenzen. Deshalb schreibt trigger_logbuch die
Farbe in JEDE Zeile.

DIE DEFINITION (IBD-Konvention, zu Soreides CANSLIM-Wurzeln passend):
je Index der Schluss gegen die 21-Tage-Exponentiallinie und die
50-Tage-Durchschnittslinie.
  gruen: BEIDE Indizes schliessen ueber beiden Linien, die 21er liegt
         ueber der 50er, und die 50er steigt (hoeher als vor 10
         Handelstagen).
  rot:   mindestens ein Index schliesst UNTER seiner 50-Tage-Linie.
  gelb:  alles dazwischen.

Aufruf:
  python marktampel.py            berechnen, drucken, marktampel.json schreiben
"""

import json
import sys
from datetime import datetime

DATEI = "marktampel.json"
INDIZES = {"^GSPC": "S&P 500", "^IXIC": "Nasdaq"}


def _index_lage(df):
    """Schluss, Linienlage und Richtung fuer EINEN Index."""
    schluss = df["Close"].dropna()
    if len(schluss) < 65:
        return None
    ema21 = float(schluss.ewm(span=21, adjust=False).mean().iloc[-1])
    sma50_reihe = schluss.rolling(50).mean()
    sma50 = float(sma50_reihe.iloc[-1])
    sma50_vor10 = float(sma50_reihe.iloc[-11])
    letzter = float(schluss.iloc[-1])
    return {
        "schluss": round(letzter, 2),
        "ema21": round(ema21, 2),
        "sma50": round(sma50, 2),
        "ueber_ema21": letzter > ema21,
        "ueber_sma50": letzter > sma50,
        "ema21_ueber_sma50": ema21 > sma50,
        "sma50_steigt": sma50 > sma50_vor10,
        "handelstag": schluss.index[-1].strftime("%Y-%m-%d"),
    }


def berechnen():
    """Beide Indizes laden und die Farbe bestimmen. None bei Datenmangel."""
    import yfinance as yf
    lagen = {}
    for symbol, name in INDIZES.items():
        try:
            df = yf.Ticker(symbol).history(period="6mo", auto_adjust=False)
        except Exception as e:
            print(f"  Marktampel: {name} nicht ladbar ({type(e).__name__})")
            return None
        lage = _index_lage(df)
        if lage is None:
            print(f"  Marktampel: {name} mit zu wenig Historie")
            return None
        lagen[name] = lage

    if any(not l["ueber_sma50"] for l in lagen.values()):
        farbe = "rot"
    elif all(l["ueber_ema21"] and l["ema21_ueber_sma50"]
             and l["sma50_steigt"] for l in lagen.values()):
        farbe = "gruen"
    else:
        farbe = "gelb"
    return {
        "farbe": farbe,
        "handelstag": max(l["handelstag"] for l in lagen.values()),
        "gebaut_am": datetime.now().isoformat(timespec="seconds"),
        "indizes": lagen,
    }


def aktualisieren():
    """Berechnen und ablegen; bei Datenmangel bleibt der alte Stand
    liegen (eine veraltete Farbe ist im Logbuch als solche erkennbar,
    ein geloeschter Stand waere gar keine Information)."""
    d = berechnen()
    if d is None:
        return None
    with open(DATEI, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    return d


def lese_farbe():
    """Die abgelegte Farbe samt Handelstag, oder (None, None)."""
    d = lese()
    if not d:
        return None, None
    return d.get("farbe"), d.get("handelstag")


def lese(pfad=DATEI):
    """Die ganze abgelegte Ampel (Farbe, Handelstag, Indizes), oder None."""
    try:
        with open(pfad, encoding="utf-8-sig") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) and d.get("farbe") else None


FARBWORT = {"gruen": "grün", "gelb": "gelb", "rot": "rot"}


def _datum_de(iso):
    teile = str(iso or "")[:10].split("-")
    if len(teile) != 3:
        return str(iso or "unbekannt")
    return f"{teile[2]}.{teile[1]}.{teile[0]}"


def _lage_text(lage):
    """Schluss gegen die zwei Linien und die Richtung der 50er, knapp."""
    e21, s50 = lage.get("ueber_ema21"), lage.get("ueber_sma50")
    if e21 == s50:
        teile = [("über" if e21 else "unter") + " EMA 21 und SMA 50"]
    else:
        teile = [("über" if e21 else "unter") + " EMA 21",
                 ("über" if s50 else "unter") + " SMA 50"]
    if not lage.get("ema21_ueber_sma50"):
        teile.append("EMA 21 unter SMA 50")
    teile.append("SMA 50 steigt" if lage.get("sma50_steigt")
                 else "SMA 50 steigt nicht")
    return ", ".join(teile)


def zeile(daten, vortag=None):
    """Die Ampel als EINE Zeile fuer die erste Meldung des Handelstags.

    ETAPPE 0 (Gerhard, 13.09.2026, "braucht gar keine Entscheidung von
    mir"), vorgesehen seit Baustein 4 des Einbau-Papiers: "der Waechter
    stellt die Farbe als eine Zeile an den Anfang der ERSTEN Meldung des
    Tages". Die Zeile informiert nur, sie unterdrueckt nichts.

    vortag: der letzte abgeschlossene Handelstag laut den heutigen
    Kurszeilen (ISO-Datum), falls bekannt. Gilt die abgelegte Ampel einem
    anderen Schluss, steht KEINE Farbe da, sondern der Hinweis, dass sie
    nicht erneuert wurde. Eine Farbe vom falschen Tag waere schlimmer als
    keine (Befund 13.09.2026: marktampel.json stand im Repo zwei Wochen
    auf dem 28.08.2026, weil der Nachtscan sie nicht hochlud).

    Meldungsformat fuer Gerhard und Mathias: kein Gedankenstrich, kein
    senkrechter Strich, Strichpunkt zwischen den Angaben, Beistrich
    innerhalb."""
    if not daten or daten.get("farbe") not in FARBWORT:
        return "Marktampel nicht verfügbar; es liegt keine Berechnung vor."
    tag = str(daten.get("handelstag") or "")[:10]
    if vortag and tag != str(vortag)[:10]:
        return ("Marktampel nicht verfügbar; die letzte Berechnung gilt dem "
                f"Schluss vom {_datum_de(tag)}, die heutigen Kurse folgen "
                f"auf den {_datum_de(vortag)}.")
    teile = [f"Marktampel {FARBWORT[daten['farbe']]}, Schluss vom "
             f"{_datum_de(tag)}"]
    for name, lage in (daten.get("indizes") or {}).items():
        if isinstance(lage, dict):
            teile.append(f"{name} {_lage_text(lage)}")
    return "; ".join(teile)


def main():
    d = aktualisieren()
    if d is None:
        print("Marktampel: keine Daten, nichts geschrieben.")
        return 1
    print(f"Marktampel: {d['farbe'].upper()} (Handelstag {d['handelstag']})")
    for name, l in d["indizes"].items():
        print(f"  {name}: Schluss {l['schluss']}, EMA21 {l['ema21']} "
              f"({'darüber' if l['ueber_ema21'] else 'darunter'}), "
              f"SMA50 {l['sma50']} "
              f"({'darüber' if l['ueber_sma50'] else 'darunter'}, "
              f"{'steigend' if l['sma50_steigt'] else 'nicht steigend'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
