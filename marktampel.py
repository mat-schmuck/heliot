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

ETAPPE 3 (Gerhard, 13.09.2026, Entscheidung 6: "JA BAUEN ... Die Ampel
filtert weiterhin NICHTS"): Je Index kommen die Distribution Days samt
Stalling Days und der Stand des Follow-through Day dazu (gerechnet in
marktbreite.py, Papier 4.4 Punkte 6 und 7). Die Zeile der ersten
Waechter-Meldung traegt dahinter die Marktbreite aus rs_universum.json
(Papier 4.4 Punkt 8: "die Farbe samt Distribution-Day-Zaehlung und Breite
als Zeile in der Morgenmeldung des Waechters und im Abendbericht").

Aufruf:
  python marktampel.py            berechnen, drucken, marktampel.json schreiben
"""

import json
import sys
from datetime import datetime

import marktbreite

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
    """Beide Indizes laden und die Farbe bestimmen. None bei Datenmangel.

    Ein Jahr Kurse (Etappe 3): Der Follow-through Day braucht die
    50-Tage-Linie und ein Tief, das Monate zuruecklegen kann; die Farbe
    selbst kommt mit 65 Schlusskursen aus. Scheitert die Rechnung der
    Distribution Days, bleibt die Farbe trotzdem stehen."""
    import yfinance as yf
    lagen = {}
    for symbol, name in INDIZES.items():
        try:
            df = yf.Ticker(symbol).history(period="1y", auto_adjust=False)
        except Exception as e:
            print(f"  Marktampel: {name} nicht ladbar ({type(e).__name__})")
            return None
        lage = _index_lage(df)
        if lage is None:
            print(f"  Marktampel: {name} mit zu wenig Historie")
            return None
        try:
            phase = marktbreite.index_phase(df)
        except Exception as e:  # noqa
            print(f"  Marktampel: Distribution Days fuer {name} nicht berechenbar ({type(e).__name__}: {e})")
            phase = None
        if phase:
            lage.update(phase)
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
    phase = marktbreite.phase_text(lage)
    if phase:
        teile.append(phase)
    return ", ".join(teile)


def zeile(daten, vortag=None, breite=None):
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
    innerhalb.

    breite (Etappe 3): der Eintrag "marktbreite" aus rs_universum.json.
    Ist er uebergeben (auch leer), steht die Breite in DERSELBEN Zeile
    hinter der Ampel, mit derselben Pruefung auf den Schluss: Gilt sie einem
    anderen Schluss, steht keine Zahl da. Ohne das Argument bleibt die
    Zeile, wie sie in Etappe 0 war."""
    if not daten or daten.get("farbe") not in FARBWORT:
        text = "Marktampel nicht verfügbar; es liegt keine Berechnung vor"
        if breite is None:
            return text + "."
        return "; ".join([text] + marktbreite.breite_teil(breite, vortag, mit_datum=True)) + "."
    tag = str(daten.get("handelstag") or "")[:10]
    if vortag and tag != str(vortag)[:10]:
        text = ("Marktampel nicht verfügbar; die letzte Berechnung gilt dem "
                f"Schluss vom {_datum_de(tag)}, die heutigen Kurse folgen "
                f"auf den {_datum_de(vortag)}")
        if breite is None:
            return text + "."
        return "; ".join([text] + marktbreite.breite_teil(breite, vortag, mit_datum=True)) + "."
    teile = [f"Marktampel {FARBWORT[daten['farbe']]}, Schluss vom "
             f"{_datum_de(tag)}"]
    for name, lage in (daten.get("indizes") or {}).items():
        if isinstance(lage, dict):
            teile.append(f"{name} {_lage_text(lage)}")
    if breite is not None:
        teile += marktbreite.breite_teil(breite, tag)
    return "; ".join(teile)


def bericht_absatz(daten, breite, handelstag):
    """Ampel, Distribution Days und die ganze Breite als EIN nummerierter
    Absatz fuer den Abendbericht (Etappe 3). handelstag: der Schluss, dem der
    Bericht gilt; eine Ampel oder Breite von einem anderen Schluss steht nicht
    mit Zahlen da."""
    zeilen = []
    tag_soll = str(handelstag or "")[:10]
    if not daten or daten.get("farbe") not in FARBWORT:
        zeilen.append("Marktampel nicht verfügbar, es liegt keine Berechnung vor")
    else:
        tag = str(daten.get("handelstag") or "")[:10]
        if tag_soll and tag != tag_soll:
            zeilen.append(f"Marktampel nicht verfügbar, die letzte Berechnung gilt dem Schluss vom {_datum_de(tag)}")
        else:
            zeilen.append(f"Marktampel {FARBWORT[daten['farbe']]}")
            for name, lage in (daten.get("indizes") or {}).items():
                if isinstance(lage, dict):
                    zeilen.append(f"{name} {_lage_text(lage)}")
    b_tag = str((breite or {}).get("handelstag") or "")[:10] if isinstance(breite, dict) else ""
    if isinstance(breite, dict) and breite.get("steiger") is not None and tag_soll and b_tag != tag_soll:
        zeilen.append(f"Marktbreite nicht verfügbar, die letzte Berechnung gilt dem Schluss vom {_datum_de(b_tag)}")
    else:
        zeilen += marktbreite.bericht_zeilen(breite)
    return ("Marktampel und Marktbreite, reine Anzeige, die Ampel filtert nichts:\n"
            + "\n".join(f"{i}. {z}" for i, z in enumerate(zeilen, 1)))


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
