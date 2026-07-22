#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BREAKOUT-WÄCHTER
================
Prüft die Kaufpunkte aus kaufpunkte.xlsx gegen die aktuellen Kurse und meldet
per ntfy-Push, sobald ein Kaufpunkt gerissen wurde — MIT Volumen-Bestätigung,
so wie das Regelwerk es verlangt.

Das schließt die Lücke des Scanners: der liefert die Trigger-Level, dieser
Wächter prüft, ob ein Ausbruch wirklich stattfindet und ob er gültig ist.

Volumen-Regeln je Strategie (aus dem Regelwerk):
  Darvas Box        Volumen > Ø20-Tage-Volumen
  VCP               Volumen ≥ 140 % vom Ø20-Tage-Volumen (Minervini: 40-50 % über Ø)
  Cup & Handle      Volumen > Ø20-Tage-Volumen (O'Neil: Volumen-Bestätigung)
  Rectangle Top     Volumen > Ø20d UND Kurs > SMA21 (Bulkowskis bestes Setup)
  High & Tight Flag Volumen > Ø20-Tage-Volumen
  Fallback-Level    Volumen > Ø20-Tage-Volumen

Aufruf:
  export TWELVE_DATA_API_KEY="dein_key"
  export NTFY_TOPIC="dein-topic"
  python breakout_watcher.py kaufpunkte.xlsx
  python breakout_watcher.py kaufpunkte.xlsx --alle       # auch Fallback-Level überwachen
  python breakout_watcher.py kaufpunkte.xlsx --dry-run    # nur anzeigen, kein Push

Zustandsdatei:
  ./watcher_state.json merkt sich, was schon gemeldet wurde — du bekommst
  jeden Treffer genau EINMAL pro Handelstag, nicht alle 15 Minuten aufs Neue.
"""

import argparse
import json
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd

try:
    import requests
except ImportError:
    sys.exit("Bitte installieren: pip install requests pandas openpyxl")

QUOTE_URL = "https://api.twelvedata.com/quote"
STATE_FILE = Path("watcher_state.json")

# Volumen-Faktor je Strategie (Vielfaches des Ø20-Tage-Volumens)
VOL_FAKTOR = {
    "Darvas Box": 1.0,
    "VCP": 1.4,
    "Cup & Handle": 1.0,
    "Rectangle Top": 1.0,
    "High & Tight Flag": 1.0,
}
VOL_FAKTOR_FALLBACK = 1.0


# ---------------------------------------------------------------------------
# Zustand (was wurde schon gemeldet)
# ---------------------------------------------------------------------------

# Wie sich das Handelsvolumen ueber den Boersentag verteilt.
# Gemessen an acht Aktien ueber 168 Aktien-Tage (30-Minuten-Kerzen,
# nur regulaerer Handel). Schluessel: Minuten seit Mitternacht New Yorker
# Zeit am ENDE der jeweiligen Halbstunde; Wert: bis dahin gehandelter
# Anteil am Tagesvolumen.
#
# Wichtig: Die Verteilung ist NICHT gleichmaessig. Allein die erste halbe
# Stunde macht 21 % aus, linear waeren es 7,7 %. Wer linear hochrechnet,
# ueberschaetzt den Vormittag um ein Vielfaches und erzeugt Fehlsignale.
VOLUMENKURVE = [
    (570, 0.000),   # 09:30 NY — Eroeffnung, noch nichts gehandelt
    (600, 0.213),   # 10:00
    (630, 0.314),   # 10:30
    (660, 0.396),   # 11:00
    (690, 0.465),   # 11:30
    (720, 0.523),   # 12:00
    (750, 0.581),   # 12:30
    (780, 0.630),   # 13:00
    (810, 0.676),   # 13:30
    (840, 0.721),   # 14:00
    (870, 0.764),   # 14:30
    (900, 0.810),   # 15:00
    (930, 0.867),   # 15:30
    (960, 1.000),   # 16:00 — Handelsschluss
]


def tagesanteil(jetzt=None) -> float:
    """Welcher Anteil des Tagesvolumens ist zu dieser Uhrzeit ueblicherweise
    schon gehandelt? Zwischen den Stuetzstellen wird linear interpoliert.

    Vor Handelsbeginn und nach Schluss: 1.0 (voller Tag), damit die
    Hochrechnung dann nichts mehr veraendert."""
    try:
        from zoneinfo import ZoneInfo
        ny = ZoneInfo("America/New_York")
    except Exception:
        return 1.0
    jetzt = (jetzt or datetime.now(ny)).astimezone(ny)
    minuten = jetzt.hour * 60 + jetzt.minute
    if minuten <= VOLUMENKURVE[0][0]:
        return 1.0                      # vor Eroeffnung
    if minuten >= VOLUMENKURVE[-1][0]:
        return 1.0                      # nach Schluss: Tag ist komplett
    for i in range(1, len(VOLUMENKURVE)):
        m0, a0 = VOLUMENKURVE[i - 1]
        m1, a1 = VOLUMENKURVE[i]
        if minuten <= m1:
            spanne = m1 - m0
            anteil = a0 + (a1 - a0) * ((minuten - m0) / spanne) if spanne else a1
            return max(anteil, 0.01)    # nie durch (fast) null teilen
    return 1.0


def markt_offen(jetzt=None) -> tuple:
    """Handelt die US-Börse gerade? Liefert (offen, Begruendung).

    Richtet sich selbsttaetig nach amerikanischer Sommer- und Winterzeit:
    Python kennt die Umstellungstermine ueber die Zeitzone America/New_York,
    die sich von den europaeischen unterscheiden (USA: zweiter Sonntag im
    Maerz bis erster Sonntag im November; EU: letzter Sonntag im Maerz bis
    letzter Sonntag im Oktober). In den Wochen dazwischen verschiebt sich
    der Handel gegenueber Wiener Zeit um eine Stunde.

    Der Zeitplan im Workflow deckt deshalb den groesseren Bereich ab, und
    diese Pruefung entscheidet, ob wirklich gehandelt wird. So ist immer der
    volle Boersenhandel abgedeckt, ohne dass jemand zweimal im Jahr
    Zeitangaben nachziehen muss.

    Boersenfeiertage kennt diese Pruefung NICHT - an solchen Tagen laeuft
    der Waechter, findet aber unveraenderte Kurse und meldet nichts."""
    try:
        from zoneinfo import ZoneInfo
        ny = ZoneInfo("America/New_York")
    except Exception:
        return True, "Zeitzone nicht verfügbar — Prüfung übersprungen"

    jetzt = (jetzt or datetime.now(ny)).astimezone(ny)
    if jetzt.weekday() >= 5:
        return False, f"Wochenende in New York ({jetzt:%A})"

    beginn = jetzt.replace(hour=9, minute=30, second=0, microsecond=0)
    ende = jetzt.replace(hour=16, minute=0, second=0, microsecond=0)
    zone = "Sommerzeit" if jetzt.dst() else "Winterzeit"
    if jetzt < beginn:
        return False, f"vor Handelsbeginn ({jetzt:%H:%M} New York, {zone})"
    if jetzt > ende:
        return False, f"nach Handelsschluss ({jetzt:%H:%M} New York, {zone})"
    return True, f"{jetzt:%H:%M} New York ({zone})"


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
            # Zustand gilt nur für den heutigen Handelstag
            if data.get("tag") == date.today().isoformat():
                return data
        except Exception:
            pass
    return {"tag": date.today().isoformat(), "gemeldet": []}


def save_state(state: dict):
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception as e:
        print(f"Zustand konnte nicht gespeichert werden: {e}")


# ---------------------------------------------------------------------------
# Kaufpunkte aus der Excel
# ---------------------------------------------------------------------------

def load_watchlist(xlsx_path: str, nur_muster: bool) -> list[dict]:
    """Liest alle Kaufpunkte + die für die Prüfung nötigen Kontextwerte."""
    df = pd.read_excel(xlsx_path, sheet_name="Kaufpunkte")
    items = []
    for _, row in df.iterrows():
        ticker = str(row["Ticker"]).strip()
        for i in (1, 2, 3):
            strat = str(row.get(f"KP{i} Strategie", "") or "").strip()
            preis = row.get(f"KP{i} Preis")
            if not strat or pd.isna(preis):
                continue
            if nur_muster and strat.startswith("Fallback"):
                continue
            stop = row.get(f"KP{i} Stop")
            ziel = row.get(f"KP{i} Ziel")
            items.append({
                "ticker": ticker,
                "firma": str(row.get("Firma", "")),
                "nr": i,
                "strategie": strat,
                "kaufpunkt": float(preis),
                "stop": None if pd.isna(stop) else float(stop),
                "ziel": None if (ziel is None or pd.isna(ziel) or ziel == "") else float(ziel),
            })
    return items


# ---------------------------------------------------------------------------
# Live-Kurse holen (Batch: Twelve Data kann mehrere Symbole pro Call)
# ---------------------------------------------------------------------------

def fetch_quotes_yahoo(tickers: list[str]) -> dict:
    """Holt Kurs, Tagesvolumen und Ø20-Volumen fuer ALLE Ticker in einem Abruf.

    Vorteil gegenueber Twelve Data: kein Minutenlimit, kein Tageslimit, und
    31 Aktien sind in rund drei Sekunden da statt in vier Minuten.

    Das Ø20-Volumen wird hier SELBST aus den Tagesdaten berechnet. Bei Twelve
    Data kam es als Feld 'average_volume', dessen Mittelungszeitraum nirgends
    dokumentiert ist — das Regelwerk verlangt aber ausdruecklich 20 Tage."""
    try:
        import yfinance as yf
    except ImportError:
        print("  yfinance nicht verfügbar — weiche auf Twelve Data aus.")
        return {}

    unique = sorted(set(t.upper() for t in tickers))
    try:
        roh = yf.download(" ".join(unique), period="3mo", interval="1d",
                          group_by="ticker", progress=False,
                          auto_adjust=False, threads=True)
    except Exception as e:
        print(f"  Yahoo-Abruf fehlgeschlagen ({str(e)[:60]}) — Twelve Data übernimmt.")
        return {}

    out = {}
    for t in unique:
        try:
            df = roh[t] if len(unique) > 1 else roh
            df = df.dropna(subset=["Close", "Volume"])
            if df.empty:
                continue
            letzte = df.iloc[-1]
            vol20 = float(df["Volume"].tail(20).mean())
            out[t] = {
                "close": float(letzte["Close"]),
                "volume": float(letzte["Volume"]),
                "avg_volume": vol20,
                "is_open": False,
                "name": "",
            }
        except Exception:
            continue
    return out


def fetch_quotes(tickers: list[str], api_key: str, batch_size: int = 8,
                 pause: float = 62.0) -> dict:
    """Holt Quotes in Batches. Rückgabe: {ticker: {close, volume, avg_volume, ...}}

    ACHTUNG Rate-Limit: Twelve Data zaehlt JEDES Symbol als eigenen Credit,
    nicht jeden Aufruf. Beim Free-Tier sind das 8 Credits pro Minute. Ein
    Block mit 8 Symbolen schoepft das Minutenkontingent also komplett aus.

    Die urspruengliche Pause von 8 Sekunden war viel zu kurz: Der zweite
    Block lief in derselben Minute und wurde mit HTTP 429 abgewiesen - von
    31 Aktien kamen nur 16 durch, der Rest wurde stillschweigend nicht
    geprueft. Darum jetzt gut 60 Sekunden zwischen den Bloecken."""
    out = {}
    unique = sorted(set(tickers))
    for i in range(0, len(unique), batch_size):
        chunk = unique[i: i + batch_size]
        params = {"symbol": ",".join(chunk), "apikey": api_key}
        try:
            r = requests.get(QUOTE_URL, params=params, timeout=30)
            data = r.json()
        except Exception as e:
            print(f"  Quote-Abruf fehlgeschlagen für {chunk}: {e}")
            continue

        # Bei einem einzelnen Symbol liefert die API das Objekt direkt,
        # bei mehreren ein Dict {symbol: objekt}
        if isinstance(data, dict) and "symbol" in data:
            data = {data["symbol"]: data}
        if not isinstance(data, dict):
            continue

        for sym, q in data.items():
            if not isinstance(q, dict) or q.get("status") == "error":
                print(f"  [{sym}] keine Quote: {q.get('message', 'unbekannt') if isinstance(q, dict) else q}")
                continue
            try:
                out[sym.upper()] = {
                    "close": float(q["close"]),
                    "volume": float(q.get("volume") or 0),
                    "avg_volume": float(q.get("average_volume") or 0),
                    "is_open": bool(q.get("is_market_open", False)),
                    "name": q.get("name", ""),
                }
            except (KeyError, TypeError, ValueError):
                continue

        if i + batch_size < len(unique):
            time.sleep(pause)  # Free-Tier-Rate-Limit respektieren
    return out


# ---------------------------------------------------------------------------
# Breakout-Prüfung
# ---------------------------------------------------------------------------

def pruefe_breakout(item: dict, quote: dict) -> dict | None:
    """Prüft, ob der Kaufpunkt gerissen wurde. Gibt Treffer-Info zurück oder None."""
    kurs = quote["close"]
    kp = item["kaufpunkt"]
    if kurs < kp:
        return None  # Kaufpunkt noch nicht erreicht

    # Zu weit drüber? Dann ist der Zug abgefahren (kein sauberer Einstieg mehr)
    ueber = kurs / kp - 1
    if ueber > 0.05:
        return None

    faktor = VOL_FAKTOR.get(item["strategie"], VOL_FAKTOR_FALLBACK)
    vol, avg = quote["volume"], quote["avg_volume"]

    # RELATIVES VOLUMEN, auf den ganzen Tag hochgerechnet.
    #
    # Ohne Hochrechnung waere die Volumenbestaetigung vormittags nie
    # erfuellbar: Um 16:00 Wiener Zeit sind erst rund 31 % eines normalen
    # Tagesvolumens gehandelt — ein Ausbruch muesste also das Dreifache des
    # Ueblichen ziehen, nur um die 100-%-Schwelle zu erreichen.
    #
    # Mit Hochrechnung lautet die Frage richtig: Ist das Volumen FUER DIESE
    # UHRZEIT ungewoehnlich hoch? Ergebnis kann 180 %, 640 % oder 3200 %
    # sein — je staerker der Andrang, desto hoeher.
    anteil = tagesanteil()
    vol_hochgerechnet = vol / anteil if anteil > 0 else vol
    if avg > 0:
        vol_ratio = vol_hochgerechnet / avg
        vol_ok = vol_ratio >= faktor
        # Alte Rechnung (vor der Hochrechnung): rohes Tagesvolumen gegen Ø20.
        # Nur fuer Gerhards eintaegigen Vergleich der beiden Verfahren —
        # wird per VOL_VERGLEICH=1 an die Meldungen angehaengt.
        vol_ratio_roh = vol / avg
        vol_ok_roh = vol_ratio_roh >= faktor
    else:
        vol_ratio = None
        vol_ok = None  # unbekannt — wir melden trotzdem, aber gekennzeichnet
        vol_ratio_roh = None
        vol_ok_roh = None

    return {
        **item,
        "kurs": kurs,
        "ueber_pct": ueber * 100,
        "vol_ratio": vol_ratio,
        "vol_noetig": faktor,
        "vol_ok": vol_ok,
        "vol_roh": vol,
        "vol_anteil": anteil,
        "vol_ratio_roh": vol_ratio_roh,
        "vol_ok_roh": vol_ok_roh,
    }


def format_treffer(t: dict) -> str:
    # Bei laufendem Handel dazuschreiben, dass hochgerechnet wurde — sonst
    # wundert man sich ueber 3200 %, wenn erst eine Stunde gehandelt wurde.
    anteil = t.get("vol_anteil", 1.0)
    zusatz = ""
    if anteil < 0.99:
        zusatz = f" (hochgerechnet, erst {anteil*100:.0f}% des Tages)"
    if t["vol_ok"] is True:
        vol_txt = f"Vol {t['vol_ratio']*100:.0f}% vom Ø — BESTÄTIGT{zusatz}"
    elif t["vol_ok"] is False:
        vol_txt = (f"Vol nur {t['vol_ratio']*100:.0f}% vom Ø "
                   f"(nötig: {t['vol_noetig']*100:.0f}%) — NICHT bestätigt{zusatz}")
    else:
        vol_txt = "Volumen unbekannt — selbst prüfen"
    zeilen = [
        f"{t['ticker']} — {t['strategie']}",
        f"Kaufpunkt {t['kaufpunkt']:.2f} | Kurs {t['kurs']:.2f} (+{t['ueber_pct']:.1f}%)",
        vol_txt,
    ]
    if t["stop"] is not None:
        risiko = (t["kurs"] / t["stop"] - 1) * 100
        zeilen.append(f"Stop {t['stop']:.2f} (Risiko {risiko:.1f}%)")
    if t["ziel"] is not None:
        chance = (t["ziel"] / t["kurs"] - 1) * 100
        zeilen.append(f"Ziel {t['ziel']:.2f} (+{chance:.1f}%)")

    # Gerhards eintaegiger Vergleich (VOL_VERGLEICH=1 in watcher.yml):
    # Zusatzzeile mit der ALTEN Rechnung (rohes Volumen ohne Hochrechnung),
    # damit sich beide Verfahren am selben Treffer vergleichen lassen.
    # Nach einem vollen Handelstag den Schalter in watcher.yml wieder
    # entfernen — die Zeile verschwindet dann von selbst.
    if (os.environ.get("VOL_VERGLEICH", "") == "1"
            and t.get("vol_ratio_roh") is not None):
        roh_urteil = "hätte BESTÄTIGT" if t["vol_ok_roh"] else "hätte NICHT bestätigt"
        zeilen.append(f"Vergleich alte Rechnung: Vol roh {t['vol_ratio_roh']*100:.0f}% "
                      f"vom Ø (nötig {t['vol_noetig']*100:.0f}%) — {roh_urteil}")
    return "\n".join(zeilen)


# ---------------------------------------------------------------------------
# Push
# ---------------------------------------------------------------------------

def email_kopf() -> dict:
    """Zusatz-Kopfzeile, damit ntfy die Meldung auch als E-Mail zustellt.

    Hintergrund: Die ntfy-App fuer iOS ist laut eigener Dokumentation
    fehlerhaft und verlangte beim Abonnieren ein Kennwort, das es fuer
    oeffentliche Topics gar nicht gibt. Der E-Mail-Weg braucht weder App noch
    Konto - und eine Mail laesst sich mit einem Screenreader problemlos lesen.

    Ist NTFY_EMAIL nicht gesetzt, aendert sich nichts."""
    adresse = (os.environ.get("NTFY_EMAIL") or "").strip()
    return {"Email": adresse} if adresse else {}


def push(topic: str, treffer: list[dict]) -> bool:
    """Schickt die Meldung und sagt ehrlich, ob sie angekommen ist.

    Der Rueckgabewert ist wichtig: Frueher wurde der Zustand auch dann als
    'gemeldet' gespeichert, wenn der Push fehlschlug - der Treffer waere
    danach NIE wieder gemeldet worden."""
    bestaetigt = [t for t in treffer if t["vol_ok"] is True]
    rest = [t for t in treffer if t["vol_ok"] is not True]
    body = "\n\n".join([format_treffer(t) for t in bestaetigt + rest])
    titel = (f"🚀 {len(bestaetigt)} bestätigt"
             + (f", {len(rest)} ohne Vol-Bestätigung" if rest else ""))
    kopf = {"Title": titel.encode("utf-8"),
            "Priority": "high" if bestaetigt else "default",
            "Tags": "chart_with_upwards_trend"}
    kopf.update(email_kopf())
    try:
        r = requests.post(f"https://ntfy.sh/{topic}", data=body.encode("utf-8"),
                          headers=kopf, timeout=20)
    except Exception as e:
        print(f"⚠ Push fehlgeschlagen: {e}")
        return False
    if r.status_code >= 400:
        print(f"⚠ Push abgelehnt: HTTP {r.status_code} — {r.text[:200]}")
        return False
    print(f"Push gesendet an ntfy.sh/{topic} (HTTP {r.status_code})")
    return True


def testpush(topic: str) -> int:
    """Schickt eine einzelne Testnachricht, damit die Push-Kette einmal
    nachweislich geprueft ist. Ohne Kursdaten, ohne Zustandsaenderung."""
    adresse = (os.environ.get("NTFY_EMAIL") or "").strip()
    weg = f"E-Mail an {adresse}" if adresse else "ntfy-App / Browser"
    text = ("Testnachricht vom Breakout-Wächter.\n\n"
            "Wenn diese Meldung ankommt, funktioniert die "
            "Benachrichtigungskette.\n"
            f"Zustellweg: {weg}\n"
            f"Gesendet: {datetime.now():%d.%m.%Y %H:%M:%S}")
    kopf = {"Title": "Test: Breakout-Wächter".encode("utf-8"),
            "Priority": "default",
            "Tags": "white_check_mark"}
    kopf.update(email_kopf())
    print(f"    Zustellweg: {weg}")
    try:
        r = requests.post(f"https://ntfy.sh/{topic}", data=text.encode("utf-8"),
                          headers=kopf, timeout=20)
    except Exception as e:
        print(f"⚠ Testnachricht fehlgeschlagen: {e}")
        return 1
    if r.status_code >= 400:
        print(f"⚠ Testnachricht abgelehnt: HTTP {r.status_code} — {r.text[:200]}")
        return 1
    print(f"✓ Testnachricht gesendet (HTTP {r.status_code}).")
    print("  Kommt sie am Handy an, ist die Push-Kette in Ordnung.")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Live-Wächter für Kaufpunkt-Breakouts")
    ap.add_argument("xlsx", nargs="?", help="kaufpunkte.xlsx vom Pattern-Scanner")
    ap.add_argument("--alle", action="store_true",
                    help="Auch Fallback-Level überwachen (Standard: nur Muster-Treffer)")
    ap.add_argument("--dry-run", action="store_true", help="Nur anzeigen, kein Push")
    ap.add_argument("--auch-unbestaetigt", action="store_true",
                    help="Auch Breakouts ohne Volumen-Bestätigung pushen (Standard: ja, "
                         "aber klar gekennzeichnet)")
    ap.add_argument("--nur-bestaetigt", action="store_true",
                    help="Nur Breakouts MIT Volumen-Bestätigung pushen")
    ap.add_argument("--testpush", action="store_true",
                    help="Nur eine Testnachricht senden (ohne Kursdaten)")
    ap.add_argument("--ignoriere-handelszeit", action="store_true",
                    dest="ignoriere_handelszeit",
                    help="Auch ausserhalb der US-Handelszeit prüfen (zum Testen)")
    args = ap.parse_args()

    topic = os.environ.get("NTFY_TOPIC")

    # Testnachricht braucht weder API-Schluessel noch Kaufpunkte.
    if args.testpush:
        if not topic:
            sys.exit("Bitte NTFY_TOPIC setzen — ohne Topic kein Push möglich.")
        sys.exit(testpush(topic))

    # Nur noch fuer die Rueckfallebene noetig — Hauptquelle ist Yahoo.
    api_key = os.environ.get("TWELVE_DATA_API_KEY")
    if not api_key:
        print("⚠ Kein TWELVE_DATA_API_KEY gesetzt — keine Rückfallebene, "
              "falls Yahoo ausfällt.")
    if not topic and not args.dry_run:
        sys.exit("Bitte NTFY_TOPIC setzen (oder --dry-run benutzen).")
    if not args.xlsx:
        sys.exit("Bitte kaufpunkte.xlsx angeben (oder --testpush benutzen).")

    # Ausserhalb der Handelszeit gar nicht erst Kurse abrufen. Der Zeitplan
    # im Workflow deckt Sommer- UND Winterzeit ab; welche gerade gilt,
    # entscheidet sich hier.
    offen, grund = markt_offen()
    print(f"Börsenstatus: {'offen' if offen else 'geschlossen'} — {grund}")
    if not offen and not args.ignoriere_handelszeit:
        print("Nichts zu tun. (Mit --ignoriere-handelszeit trotzdem prüfen.)")
        sys.exit(0)

    items = load_watchlist(args.xlsx, nur_muster=not args.alle)
    if not items:
        sys.exit("Keine Kaufpunkte zum Überwachen gefunden.")
    tickers = [i["ticker"] for i in items]
    print(f"{len(items)} Kaufpunkte über {len(set(tickers))} Aktien werden geprüft "
          f"({datetime.now():%H:%M:%S}).")

    gewuenscht = set(t.upper() for t in tickers)

    # Hauptquelle Yahoo (ein Abruf, kein Limit), Twelve Data als Rueckfall.
    quotes = fetch_quotes_yahoo(tickers)
    if len(quotes) < len(gewuenscht):
        fehlend_yahoo = sorted(gewuenscht - set(quotes))
        if quotes:
            print(f"  Yahoo lieferte {len(quotes)} von {len(gewuenscht)} — "
                  f"hole {len(fehlend_yahoo)} über Twelve Data nach.")
        if api_key:
            quotes.update(fetch_quotes(fehlend_yahoo, api_key))
        elif not quotes:
            sys.exit("Yahoo lieferte nichts und kein TWELVE_DATA_API_KEY gesetzt.")

    print(f"{len(quotes)} von {len(gewuenscht)} Quotes erhalten.")
    if not quotes:
        sys.exit("Keine Kursdaten erhalten — Abbruch.")

    # Unvollstaendige Abfragen NICHT stillschweigend hinnehmen: Fuer die
    # fehlenden Aktien kann kein Breakout erkannt werden, und ohne Hinweis
    # sieht der Lauf trotzdem erfolgreich aus.
    fehlend = sorted(gewuenscht - set(quotes))
    if fehlend:
        print(f"\n⚠ ACHTUNG: {len(fehlend)} Aktien konnten NICHT geprüft werden:")
        print("  " + ", ".join(fehlend))
        print("  Für diese Werte wird in diesem Lauf kein Ausbruch erkannt.")
        print("  Meist Rate-Limit der Kursdaten-Schnittstelle (8 Abfragen/Minute).\n")

    state = load_state()
    schon_gemeldet = set(state["gemeldet"])

    treffer, neu = [], []
    for item in items:
        q = quotes.get(item["ticker"].upper())
        if not q:
            continue
        res = pruefe_breakout(item, q)
        if not res:
            continue
        # Kennung am Treffer mitfuehren. Vorgemerkt wird ERST nach einem
        # erfolgreichen Push - siehe unten.
        res["key"] = f"{item['ticker']}|{item['nr']}|{item['kaufpunkt']:.2f}"
        treffer.append(res)
        if res["key"] not in schon_gemeldet:
            neu.append(res)

    print(f"\n{len(treffer)} Kaufpunkte aktuell gerissen, davon {len(neu)} neu seit "
          f"dem letzten Lauf.")
    for t in treffer:
        marker = "🟢" if t["vol_ok"] is True else ("🟡" if t["vol_ok"] is False else "⚪")
        neu_marker = " [NEU]" if t in neu else ""
        print(f"  {marker} {format_treffer(t)}{neu_marker}\n")

    # Erst filtern, dann vormerken. Frueher galten auch Treffer als gemeldet,
    # die wegen --nur-bestaetigt gar nicht gepusht wurden - bekamen sie spaeter
    # die Volumenbestaetigung, wurden sie nie mehr gemeldet.
    zu_melden = neu
    if args.nur_bestaetigt:
        zu_melden = [t for t in neu if t["vol_ok"] is True]
        uebersprungen = len(neu) - len(zu_melden)
        if uebersprungen:
            print(f"{uebersprungen} Treffer ohne Volumenbestätigung — bleiben "
                  "offen und werden weiter beobachtet.")

    if zu_melden and not args.dry_run:
        if push(topic, zu_melden):
            for t in zu_melden:
                schon_gemeldet.add(t["key"])
            state["gemeldet"] = sorted(schon_gemeldet)
            save_state(state)
        else:
            print("⚠ Zustand NICHT gespeichert — der nächste Lauf versucht es erneut.")
    elif not zu_melden:
        print("Nichts Neues zu melden.")
    else:
        print("(Dry-Run — kein Push gesendet, Zustand nicht gespeichert)")


if __name__ == "__main__":
    main()
