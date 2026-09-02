#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Konsens einfrieren (Gerhards F9, Freigabe 02.09.2026).

WARUM: Der Analystenkonsens (erwarteter Umsatz und erwartetes Ergebnis je
Aktie fuer das laufende und die kommenden Quartale) existiert nur im
Moment seiner Abfrage; nach dem Quartalsbericht ist er Geschichte, und
keine amtliche Quelle bewahrt ihn auf. Wer spaeter wissen will, was der
Markt VOR einer Meldung erwartet hat, muss den Stand vorher eingefroren
haben. Genau das tut dieser Lauf, zweimal am Handelstag: um 05:00 New
Yorker Zeit vor allen Vorboersen-Meldungen und um 15:30 vor allen
Nachboersen-Meldungen (Gerhards Punkt 4: Der Zeitstempel entscheidet, was
als "vorher" gilt; zugeordnet wird spaeter ueber die Annahmezeit des
Ergebnis-8-K bei der SEC).

WAS GESPEICHERT WIRD: je Firma und Periode (0q laufendes Quartal, +1q
naechstes, 0y laufendes Jahr, +1y naechstes) der Durchschnitt, das Tief,
das Hoch und die Analystenzahl fuer Umsatz und Ergebnis je Aktie, das
PERIODENENDE laut Anbieter (die Grundlage fuer die Zuordnung zum
richtigen Quartal, Gerhards Punkt 3), der naechste Meldetermin, die
Waehrung, die Quelle und der Zeitstempel in UTC. Ablage als gepackte
JSONL-Datei je Lauf im privaten Datenrepo heliot-daten (F17).

UNIVERSUM (F9): Alle Firmen, die ueberhaupt einen Konsens tragen; welche
das sind, stellt die BESTANDSAUFNAHME selbst fest: Sie geht das
SEC-Ticker-Register in Portionen durch und merkt sich je Firma, ob ein
Konsens vorlag. Die Wochenlisten kommen in jedem Lauf zuerst.

QUELLE: Yahoo (LSEG-Konsens) ueber yfinance. Yahoo ist keine amtliche
Schnittstelle (Gerhards Punkt 5); deshalb prueft jeder Lauf zuerst ein
LEBENSZEICHEN an fuenf Referenzfirmen und meldet per Push, wenn die
Quelle nicht liefert.

Aufruf:
  python konsens_einfrieren.py --selbsttest
  python konsens_einfrieren.py --daten <Ordner des Datenrepos> [--modus schnappschuss|bestandsaufnahme]
      [--hoechstens N] [--ticker-datei DATEI] [--nur-wochenlisten] [--faeden 4]
"""

import argparse
import concurrent.futures
import datetime as dt
import gzip
import io
import json
import os
import sys
import time

REFERENZ = ["AAPL", "MSFT", "JPM", "ANF", "KRYS"]
PERIODEN = ("0q", "+1q", "0y", "+1y")
FELDER = ["zeit_utc", "ticker", "periode", "periodenende", "umsatz_avg", "umsatz_low",
          "umsatz_high", "umsatz_analysten", "eps_avg", "eps_low", "eps_high",
          "eps_analysten", "waehrung", "naechster_termin", "quelle"]
NEU_PRUEFEN_NACH_TAGEN = 90     # Firmen ohne Konsens spaeter noch einmal ansehen


# ---------------------------------------------------------------------------
# Hilfen
# ---------------------------------------------------------------------------

def yahoo_ticker(t):
    """SEC-Schreibweise BRK.B wird bei Yahoo zu BRK-B."""
    return str(t).strip().upper().replace(".", "-")


def _json(pfad, vorgabe):
    try:
        with io.open(pfad, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return vorgabe


def _schreibe_json(pfad, daten):
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with io.open(pfad, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=1, sort_keys=True)


def _raw(d, k):
    v = (d or {}).get(k)
    if isinstance(v, dict):
        return v.get("raw")
    return v


# ---------------------------------------------------------------------------
# Abruf
# ---------------------------------------------------------------------------

def hole_trend(ticker, fetcher=None):
    """{"trend": [je Periode ein Eintrag wie bei Yahoo], "termin": Datum
    oder None}. fetcher ersetzt den Netzabruf im Selbsttest."""
    if fetcher is not None:
        return fetcher(ticker)
    import yfinance as yf
    tk = yf.Ticker(yahoo_ticker(ticker))
    trend = None
    try:
        tk.revenue_estimate                       # loest den Abruf aus
        trend = getattr(tk._analysis, "_earnings_trend", None)
    except Exception:
        trend = None
    if not trend:
        # Rueckfall ohne Periodenende, falls yfinance sein Innenleben aendert
        trend = []
        try:
            re_, ee = tk.revenue_estimate, tk.earnings_estimate
            for per in PERIODEN:
                eintrag = {"period": per, "endDate": None, "revenueEstimate": {}, "earningsEstimate": {}}
                if re_ is not None and per in re_.index:
                    z = re_.loc[per]
                    eintrag["revenueEstimate"] = {"avg": z.get("avg"), "low": z.get("low"),
                                                  "high": z.get("high"),
                                                  "numberOfAnalysts": z.get("numberOfAnalysts"),
                                                  "revenueCurrency": z.get("currency")}
                if ee is not None and per in ee.index:
                    z = ee.loc[per]
                    eintrag["earningsEstimate"] = {"avg": z.get("avg"), "low": z.get("low"),
                                                   "high": z.get("high"),
                                                   "numberOfAnalysts": z.get("numberOfAnalysts"),
                                                   "earningsCurrency": z.get("currency")}
                trend.append(eintrag)
        except Exception:
            trend = []
    termin = None
    try:
        cal = tk.calendar or {}
        ed = cal.get("Earnings Date")
        if ed:
            termin = ed[0].isoformat() if hasattr(ed[0], "isoformat") else str(ed[0])
    except Exception:
        termin = None
    return {"trend": trend, "termin": termin}


def zeilen_aus_trend(ticker, trend, zeit, termin, quelle="yahoo"):
    out = []
    for e in trend or []:
        per = e.get("period")
        if per not in PERIODEN:
            continue
        re_, ee = e.get("revenueEstimate") or {}, e.get("earningsEstimate") or {}
        out.append({
            "zeit_utc": zeit, "ticker": ticker, "periode": per,
            "periodenende": e.get("endDate"),
            "umsatz_avg": _raw(re_, "avg"), "umsatz_low": _raw(re_, "low"),
            "umsatz_high": _raw(re_, "high"), "umsatz_analysten": _raw(re_, "numberOfAnalysts"),
            "eps_avg": _raw(ee, "avg"), "eps_low": _raw(ee, "low"),
            "eps_high": _raw(ee, "high"), "eps_analysten": _raw(ee, "numberOfAnalysts"),
            "waehrung": ee.get("earningsCurrency") or re_.get("revenueCurrency"),
            "naechster_termin": termin, "quelle": quelle,
        })
    return out


def hat_konsens(zeilen):
    """Mindestens ein Analyst fuer Umsatz oder Ergebnis im laufenden
    Quartal oder Jahr."""
    for z in zeilen:
        if z["periode"] in ("0q", "0y"):
            for f in ("umsatz_analysten", "eps_analysten"):
                try:
                    if float(z[f] or 0) > 0:
                        return True
                except (TypeError, ValueError):
                    pass
    return False


# ---------------------------------------------------------------------------
# Lebenszeichen (Gerhards Punkt 5)
# ---------------------------------------------------------------------------

def lebenszeichen(fetcher=None):
    """{ticker: True/False}; die Quelle gilt als lebendig, wenn
    mindestens vier der fuenf Referenzfirmen einen Umsatzkonsens mit
    Analystenzahl fuer das laufende Quartal liefern."""
    ergebnis = {}
    for t in REFERENZ:
        try:
            r = hole_trend(t, fetcher)
            z = zeilen_aus_trend(t, r["trend"], "", r["termin"])
            ergebnis[t] = any(x["periode"] == "0q" and float(x["umsatz_avg"] or 0) > 0
                              and float(x["umsatz_analysten"] or 0) > 0 for x in z)
        except Exception:
            ergebnis[t] = False
    return ergebnis


def lebendig(ergebnis):
    return sum(1 for ok in ergebnis.values() if ok) >= 4


def push(titel, text):
    """Meldung ueber ntfy, nur wenn das Thema als Secret gesetzt ist."""
    topic = (os.environ.get("NTFY_TOPIC") or "").strip()
    if not topic:
        print("(kein NTFY_TOPIC, keine Meldung)")
        return False
    try:
        import requests
        r = requests.post(f"https://ntfy.sh/{topic}", data=text.encode("utf-8"),
                          headers={"Title": titel.encode("utf-8"), "Priority": "high"}, timeout=20)
        return r.status_code < 400
    except Exception as e:  # noqa
        print(f"Push fehlgeschlagen: {e}")
        return False


# ---------------------------------------------------------------------------
# Universum
# ---------------------------------------------------------------------------

def sec_ticker():
    """Alle Ticker des SEC-Registers (nur im Actions-Lauf: braucht die
    Kontaktkennung im Secret SEC_USER_AGENT)."""
    ua = (os.environ.get("SEC_USER_AGENT") or "").strip()
    if not ua:
        raise RuntimeError("SEC_USER_AGENT fehlt; das Register ist nur im Actions-Lauf abrufbar")
    import urllib.request
    req = urllib.request.Request("https://www.sec.gov/files/company_tickers.json",
                                 headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read())
    return [str(v["ticker"]).strip().upper() for v in d.values() if v.get("ticker")]


def wochenlisten_ticker():
    try:
        import listen
        return [t for t, _ in listen.alle_ticker()]
    except Exception:
        return []


def universum(daten, modus, hoechstens, ticker_datei=None, nur_wochenlisten=False,
              heute=None, register=None):
    """Reihenfolge: Wochenlisten zuerst, dann der Bestand mit Konsens,
    dann (Bestandsaufnahme) eine Portion noch ungeprüfter Firmen aus
    dem SEC-Register samt Firmen, deren letzte Pruefung lange her ist."""
    heute = heute or dt.date.today()
    gesehen, raus = set(), []

    def nimm(t):
        t = str(t).strip().upper()
        if t and t not in gesehen:
            gesehen.add(t)
            raus.append(t)

    if ticker_datei:
        with io.open(ticker_datei, encoding="utf-8") as f:
            for zeile in f:
                nimm(zeile.split("#")[0])
        return raus
    for t in wochenlisten_ticker():
        nimm(t)
    if nur_wochenlisten:
        return raus
    bestand = _json(os.path.join(daten, "konsens", "firmen_mit_konsens.json"), {})
    for t in sorted(bestand):
        nimm(t)
    if modus == "bestandsaufnahme":
        stand = _json(os.path.join(daten, "konsens", "bestandsaufnahme.json"), {"geprueft": {}})
        geprueft = stand.get("geprueft", {})
        alle = register if register is not None else sec_ticker()
        offen = []
        for t in alle:
            t = str(t).strip().upper()
            if t in gesehen:
                continue
            eintrag = geprueft.get(t)
            if eintrag is None:
                offen.append(t)
            else:
                try:
                    alter = (heute - dt.date.fromisoformat(eintrag["datum"])).days
                except Exception:
                    alter = NEU_PRUEFEN_NACH_TAGEN + 1
                if alter > NEU_PRUEFEN_NACH_TAGEN:
                    offen.append(t)
        for t in offen[:max(0, hoechstens)]:
            nimm(t)
    return raus


# ---------------------------------------------------------------------------
# Lauf
# ---------------------------------------------------------------------------

def _einer(ticker, zeit, fetcher):
    versuche = 0
    while True:
        try:
            r = hole_trend(ticker, fetcher)
            return ticker, zeilen_aus_trend(ticker, r["trend"], zeit, r["termin"]), None
        except Exception as e:  # noqa
            name = type(e).__name__
            versuche += 1
            if "RateLimit" in name and versuche <= 3:
                time.sleep(60 * versuche)
                continue
            return ticker, [], f"{name}: {e}"[:200]


def lauf(daten, modus="schnappschuss", hoechstens=2500, ticker_datei=None,
         nur_wochenlisten=False, faeden=4, fetcher=None, register=None, jetzt=None):
    jetzt = jetzt or dt.datetime.now(dt.timezone.utc)
    zeit = jetzt.strftime("%Y-%m-%dT%H:%M:%SZ")
    kennung = jetzt.strftime("%Y-%m-%d_%H%MZ")
    start = time.time()

    leben = lebenszeichen(fetcher)
    print("Lebenszeichen:", ", ".join(f"{t} {'ok' if ok else 'FEHLT'}" for t, ok in leben.items()))
    _schreibe_json(os.path.join(daten, "lebenszeichen", f"{kennung}.json"),
                   {"zeit_utc": zeit, "quelle": "yahoo", "referenz": leben, "lebendig": lebendig(leben)})
    if not lebendig(leben):
        text = ("Konsens-Einfrieren abgebrochen: Yahoo liefert fuer "
                + ", ".join(t for t, ok in leben.items() if not ok)
                + " keinen Umsatzkonsens. Datenquelle pruefen.")
        print(text)
        push("Konsens: Yahoo liefert nicht", text)
        return 0

    ticker = universum(daten, modus, hoechstens, ticker_datei, nur_wochenlisten, register=register)
    print(f"{len(ticker)} Firmen ({modus})")
    alle_zeilen, fehler, mit, ohne = [], {}, [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, faeden)) as ex:
        for i, (t, zeilen, fehl) in enumerate(ex.map(lambda x: _einer(x, zeit, fetcher), ticker), 1):
            if fehl:
                fehler[t] = fehl
            elif hat_konsens(zeilen):
                alle_zeilen.extend(zeilen)
                mit.append(t)
            else:
                ohne.append(t)
            if i % 250 == 0:
                print(f"  {i}/{len(ticker)} nach {time.time()-start:.0f} s, "
                      f"{len(mit)} mit Konsens, {len(ohne)} ohne, {len(fehler)} Fehler", flush=True)

    jahr = jetzt.strftime("%Y")
    pfad = os.path.join(daten, "konsens", jahr, f"{kennung}.jsonl.gz")
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with gzip.open(pfad, "wt", encoding="utf-8") as f:
        for z in alle_zeilen:
            f.write(json.dumps(z, ensure_ascii=False) + "\n")

    bestand_pfad = os.path.join(daten, "konsens", "firmen_mit_konsens.json")
    bestand = _json(bestand_pfad, {})
    heute = jetzt.date().isoformat()
    for t in mit:
        bestand[t] = {"zuletzt": heute}
    for t in ohne:
        bestand.pop(t, None)
    _schreibe_json(bestand_pfad, bestand)

    stand_pfad = os.path.join(daten, "konsens", "bestandsaufnahme.json")
    stand = _json(stand_pfad, {"geprueft": {}})
    for t in mit:
        stand["geprueft"][t] = {"datum": heute, "konsens": True}
    for t in ohne:
        stand["geprueft"][t] = {"datum": heute, "konsens": False}
    _schreibe_json(stand_pfad, stand)

    protokoll = {"zeit_utc": zeit, "modus": modus, "firmen": len(ticker), "mit_konsens": len(mit),
                 "ohne_konsens": len(ohne), "fehler": len(fehler), "zeilen": len(alle_zeilen),
                 "dauer_s": round(time.time() - start), "datei": os.path.relpath(pfad, daten).replace(os.sep, "/")}
    with io.open(os.path.join(daten, "konsens", "laeufe.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(protokoll, ensure_ascii=False) + "\n")
    if fehler:
        _schreibe_json(os.path.join(daten, "konsens", jahr, f"{kennung}_fehler.json"), fehler)
    print(json.dumps(protokoll, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------------------
# Selbsttest (ohne Netz)
# ---------------------------------------------------------------------------

def _fake_trend(ticker, analysten=12, ende="2026-09-30"):
    def per(p, e):
        return {"period": p, "endDate": e,
                "revenueEstimate": {"avg": {"raw": 1000.0}, "low": {"raw": 900.0}, "high": {"raw": 1100.0},
                                    "numberOfAnalysts": {"raw": analysten}, "revenueCurrency": "USD"},
                "earningsEstimate": {"avg": {"raw": 1.5}, "low": {"raw": 1.2}, "high": {"raw": 1.8},
                                     "numberOfAnalysts": {"raw": analysten}, "earningsCurrency": "USD"}}
    return {"trend": [per("0q", ende), per("+1q", "2026-12-31"), per("0y", "2026-12-31"),
                      per("+1y", "2027-12-31")], "termin": "2026-10-29"}


def selbsttest() -> int:
    import tempfile
    fehler = []

    def p(name, bedingung, zusatz=""):
        print(f"  {'ok  ' if bedingung else 'FEHL'} {name}" + (f", {zusatz}" if zusatz else ""))
        if not bedingung:
            fehler.append(name)

    print("Konsens einfrieren, Selbsttest (ohne Netz)")
    z = zeilen_aus_trend("AAPL", _fake_trend("AAPL")["trend"], "2026-09-02T09:00:00Z", "2026-10-29")
    p("Vier Perioden je Firma mit allen Feldern",
      len(z) == 4 and all(set(FELDER) == set(x.keys()) for x in z))
    p("Periodenende und Termin werden mitgefuehrt (Punkt 3 und 4)",
      z[0]["periodenende"] == "2026-09-30" and z[0]["naechster_termin"] == "2026-10-29")
    p("Konsens erkannt, wenn Analysten da sind", hat_konsens(z))
    p("Kein Konsens ohne Analysten",
      not hat_konsens(zeilen_aus_trend("X", _fake_trend("X", analysten=0)["trend"], "", None)))
    p("Ticker-Schreibweise: BRK.B wird BRK-B", yahoo_ticker("brk.b") == "BRK-B")

    alle_ok = lebenszeichen(fetcher=lambda t: _fake_trend(t))
    p("Lebenszeichen: fuenf Referenzfirmen lebendig", lebendig(alle_ok) and len(alle_ok) == 5)
    wackelig = lebenszeichen(fetcher=lambda t: _fake_trend(t, analysten=0 if t in ("JPM", "ANF") else 5))
    p("Lebenszeichen: zwei Ausfaelle von fuenf gelten als tot", not lebendig(wackelig))

    with tempfile.TemporaryDirectory() as d:
        register = ["AAPL", "BBB", "CCC", "DDD", "EEE"]
        u = universum(d, "bestandsaufnahme", hoechstens=2, register=register, heute=dt.date(2026, 9, 2))
        wl = wochenlisten_ticker()
        p("Bestandsaufnahme nimmt hoechstens N ungeprüfte Firmen aus dem Register",
          sum(1 for t in u if t in register and t not in wl) == 2, u[-3:])
        _schreibe_json(os.path.join(d, "konsens", "bestandsaufnahme.json"),
                       {"geprueft": {"BBB": {"datum": "2026-08-30", "konsens": False},
                                     "CCC": {"datum": "2026-01-01", "konsens": False}}})
        u2 = universum(d, "bestandsaufnahme", hoechstens=10, register=register, heute=dt.date(2026, 9, 2))
        p("Frisch geprüfte Firmen ohne Konsens bleiben draussen, alte werden neu angesehen",
          "BBB" not in u2 and "CCC" in u2)

        def fetch(t):
            return _fake_trend(t, analysten=0 if t == "DDD" else 7)
        rc = lauf(d, modus="bestandsaufnahme", hoechstens=10, faeden=2, fetcher=fetch, register=register,
                  jetzt=dt.datetime(2026, 9, 2, 9, 0, tzinfo=dt.timezone.utc), nur_wochenlisten=False)
        bestand = _json(os.path.join(d, "konsens", "firmen_mit_konsens.json"), {})
        stand = _json(os.path.join(d, "konsens", "bestandsaufnahme.json"), {})
        p("Lauf schreibt Bestand: Firmen mit Konsens drin, DDD ohne Konsens nicht",
          rc == 0 and "AAPL" in bestand and "DDD" not in bestand
          and stand["geprueft"].get("DDD", {}).get("konsens") is False, sorted(bestand)[:5])
        datei = os.path.join(d, "konsens", "2026", "2026-09-02_0900Z.jsonl.gz")
        with gzip.open(datei, "rt", encoding="utf-8") as f:
            zeilen = [json.loads(l) for l in f]
        p("Gepackte JSONL-Datei je Lauf, vier Zeilen je Firma mit Konsens",
          len(zeilen) == 4 * len(bestand) and zeilen[0]["zeit_utc"] == "2026-09-02T09:00:00Z")
        leben_dateien = os.listdir(os.path.join(d, "lebenszeichen"))
        p("Lebenszeichen-Befund wird je Lauf abgelegt", leben_dateien == ["2026-09-02_0900Z.json"])
        tot = lauf(d, fetcher=lambda t: _fake_trend(t, analysten=0), register=register,
                   jetzt=dt.datetime(2026, 9, 3, 9, 0, tzinfo=dt.timezone.utc))
        p("Tote Quelle: Lauf bricht ohne Schnappschuss ab (Rueckgabe 0, keine Fehlermail)",
          tot == 0 and not os.path.exists(os.path.join(d, "konsens", "2026", "2026-09-03_0900Z.jsonl.gz")))

    if fehler:
        print(f"\n{len(fehler)} FEHLER: {', '.join(fehler)}")
        return 1
    print("\nAlles bestanden.")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selbsttest", action="store_true")
    ap.add_argument("--daten", help="Ordner des Datenrepos heliot-daten")
    ap.add_argument("--modus", choices=["schnappschuss", "bestandsaufnahme"], default="schnappschuss")
    ap.add_argument("--hoechstens", type=int, default=2500)
    ap.add_argument("--ticker-datei")
    ap.add_argument("--nur-wochenlisten", action="store_true")
    ap.add_argument("--faeden", type=int, default=4)
    a = ap.parse_args()
    if a.selbsttest:
        return selbsttest()
    if not a.daten:
        print("--daten fehlt")
        return 1
    return lauf(a.daten, a.modus, a.hoechstens, a.ticker_datei, a.nur_wochenlisten, a.faeden)


if __name__ == "__main__":
    sys.exit(main())
