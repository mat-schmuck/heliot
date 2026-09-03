# -*- coding: utf-8 -*-
"""Gekaufte Konsens-Historie von EODHD ins private Datenrepo holen.

Gerhards F7 und F8 (Freigabe 02.09.2026): Umsatz-Konsens je Quartal ab 2017
und die EPS-Konsens-Historie kommen aus dem EODHD-Abo (Fundamentals Data
Feed, Personal use, von Mathias am 03.09.2026 abgeschlossen). Der Lauf
fragt je Firma EINMAL den Fundamentals-Endpunkt ab (kostet beim Anbieter
10 API-Calls, das Tagesbudget sind 100.000), gefiltert auf General und
Earnings, und legt Rohantwort und normalisierte Zeilen im Datenrepo ab
(F17: gekaufte Daten nur dort, nie im oeffentlichen Repo, nie angezeigt).

Gemessen am Demo-Zugang (03.09.2026, AAPL, TSLA, AMZN): Earnings::Trend hat
40 Eintraege ab 2017-06-30 (Perioden 0q, +1q, 0y, +1y, je Datum EIN
Eintrag; faellt das Quartalsende auf das Geschaeftsjahresende, steht dort
die Jahreszeile und das vierte Quartal fehlt), Earnings::History reicht
bei Apple bis 1993 zurueck (epsActual, epsEstimate, surprisePercent,
reportDate, beforeAfterMarket). Bulk-Abrufe gibt es nur im teureren
Extended-Plan; darum Einzelabrufe, 5.684 Firmen sind rund 57.000 Calls,
also ein Tag.

Aufruf (im Actions-Lauf, Secret EODHD_API_KEY):
  python eodhd_konsens.py --daten daten --modus probe
  python eodhd_konsens.py --daten daten --modus voll [--hoechstens N] [--frische 90]
  python eodhd_konsens.py --modus probe --demo      (ohne Schluessel, Demo-Firmen)
  python eodhd_konsens.py --selbsttest
"""
import argparse
import datetime as dt
import gzip
import io
import json
import os
import sys
import time

import konsens_einfrieren as ke

BASIS = "https://eodhd.com/api/v1.1/fundamentals/"
FILTER = ("General::Code,General::Name,General::CIK,General::Exchange,General::CurrencyCode,"
          "General::FiscalYearEnd,General::Type,Earnings::Trend,Earnings::History")
CALLS_JE_ABRUF = 10
TAGESBUDGET_CALLS = 95000          # Anbieter: 100.000 je Tag, ab Mitternacht GMT; Reserve fuer Proben
ABSTAND_S = 0.25                   # 4 Abrufe je Sekunde (Anbieter erlaubt 1000 je Minute)
REFERENZ = ["AAPL", "MSFT", "JPM", "ANF", "KRYS"]
DEMO = ["AAPL", "TSLA", "AMZN"]
DEMO_TOKEN = "demo"


class EodhdGesperrt(Exception):
    """Schluessel ungueltig, Tarif reicht nicht oder Budget erschoepft: der
    Lauf bricht ab, statt tausendmal denselben Fehler zu sammeln."""


def eodhd_symbol(ticker):
    """SEC-Schreibweise BRK.B heisst bei EODHD BRK-B.US."""
    return ke.yahoo_ticker(ticker) + ".US"


def _zahl(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def hole(symbol, token, fetcher=None, warte=time.sleep):
    """Ein Abruf. Liefert (status, daten_oder_text, kopf). 429 und 5xx werden
    dreimal wiederholt, 401/402/403 werfen EodhdGesperrt."""
    url = f"{BASIS}{symbol}?api_token={token}&fmt=json&filter={FILTER}"
    for versuch in range(3):
        if fetcher is not None:
            status, text, kopf = fetcher(symbol)
        else:
            import urllib.error
            import urllib.request
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "heliot-eodhd/1.0"}), timeout=60) as r:
                    status, text, kopf = r.status, r.read().decode("utf-8", "replace"), dict(r.headers)
            except urllib.error.HTTPError as e:
                status, text, kopf = e.code, e.read().decode("utf-8", "replace")[:500], dict(e.headers)
            except Exception as e:  # noqa
                status, text, kopf = 0, str(e)[:300], {}
        if status in (401, 402, 403):
            raise EodhdGesperrt(f"HTTP {status} bei {symbol}: {str(text)[:200]}")
        if status == 429 or status >= 500 or status == 0:
            warte(15 if status == 429 else 10)
            continue
        break
    if status == 200:
        try:
            return 200, json.loads(text) if isinstance(text, str) else text, kopf
        except ValueError:
            return 200, None, kopf
    return status, text, kopf


def entflachen(antwort):
    """Mit Feld-Filtern (General::Code,Earnings::Trend,...) antwortet EODHD
    FLACH, die Filterpfade sind die Schluessel (gemessen 03.09.2026 am
    Demo-Zugang); mit Abschnitts-Filtern (General,Earnings) verschachtelt.
    Beides wird auf die verschachtelte Form gebracht."""
    aus = {}
    for k, v in (antwort or {}).items():
        if "::" in str(k):
            a, b = str(k).split("::", 1)
            aus.setdefault(a, {})[b] = v
        else:
            aus[k] = v
    return aus


KONTO_FELDER = ("subscriptionType", "dailyRateLimit", "apiRequests", "apiRequestsDate", "extraLimit")


def konto(token, fetcher=None):
    """Der User-Endpunkt sagt, ob der Schluessel gilt und welcher Tarif
    dahintersteht. Ausgegeben werden NUR Tarif und Zaehler, nie Name oder
    E-Mail (die Actions-Logs des Repos sind oeffentlich). Liefert
    (status, tarifdaten)."""
    url = f"https://eodhd.com/api/user?api_token={token}&fmt=json"
    if fetcher is not None:
        status, text, _ = fetcher("user")
    else:
        import urllib.error
        import urllib.request
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "heliot-eodhd/1.0"}), timeout=60) as r:
                status, text = r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            status, text = e.code, e.read().decode("utf-8", "replace")[:300]
        except Exception as e:  # noqa
            status, text = 0, str(e)[:200]
    if status != 200:
        return status, {}
    try:
        d = json.loads(text) if isinstance(text, str) else text
    except ValueError:
        return status, {}
    return status, {k: d.get(k) for k in KONTO_FELDER if k in d}


def normalisiere(ticker, antwort, zeit):
    """Trend und History der Rohantwort in flache Zeilen; General-Angaben in
    einen Kopf."""
    antwort = entflachen(antwort)
    # Bei manchen Firmen liefert EODHD statt eines Blocks eine Zeichenkette
    # (leer oder N/A); der Vollabzug vom 03.09.2026 stuerzte daran nach rund
    # 1.000 Firmen ab. Alles, was kein Woerterbuch ist, gilt als leer.
    g = (antwort or {}).get("General")
    e = (antwort or {}).get("Earnings")
    g = g if isinstance(g, dict) else {}
    e = e if isinstance(e, dict) else {}
    kopf = {"ticker": ticker, "eodhd_code": g.get("Code"), "name": g.get("Name"),
            "cik": (str(g.get("CIK")).strip() if g.get("CIK") else None), "boerse": g.get("Exchange"),
            "waehrung": g.get("CurrencyCode"), "geschaeftsjahresende": g.get("FiscalYearEnd"),
            "typ": g.get("Type"), "abgerufen": zeit}
    zeilen = []
    trend = e.get("Trend")
    trend = trend if isinstance(trend, dict) else {}
    # v1.1 teilt den Trend in Quarterly und Annual (gemessen 03.09.2026: Apple
    # Quarterly 39 Eintraege ab 2017-06-30 SAMT der Quartale am
    # Geschaeftsjahresende, Annual 11); der alte Endpunkt liefert eine flache
    # Liste je Datum, in der die Jahreszeile das vierte Quartal verdeckt.
    if set(trend.keys()) & {"Quarterly", "Annual"}:
        bloecke = [("quartal", trend.get("Quarterly")), ("jahr", trend.get("Annual"))]
        alt_form = False
    else:
        bloecke = [(None, trend)]
        alt_form = True
    for umfang, block in bloecke:
      if not isinstance(block, dict):
          continue
      for datum, t in sorted(block.items()):
        if not isinstance(t, dict):
            continue
        period = t.get("period")
        z = {"art": "konsens_trend", "periodenende": t.get("date") or datum, "period": period,
             "umfang": umfang or ("jahr" if period in ("0y", "+1y", "-1y") else "quartal"),
             "umsatz_avg": _zahl(t.get("revenueEstimateAvg")), "umsatz_low": _zahl(t.get("revenueEstimateLow")),
             "umsatz_high": _zahl(t.get("revenueEstimateHigh")),
             "umsatz_analysten": _zahl(t.get("revenueEstimateNumberOfAnalysts")),
             "umsatz_wachstum": _zahl(t.get("revenueEstimateGrowth")),
             "eps_avg": _zahl(t.get("earningsEstimateAvg")), "eps_low": _zahl(t.get("earningsEstimateLow")),
             "eps_high": _zahl(t.get("earningsEstimateHigh")),
             "eps_analysten": _zahl(t.get("earningsEstimateNumberOfAnalysts")),
             "eps_vorjahr": _zahl(t.get("earningsEstimateYearAgoEps")),
             "eps_wachstum": _zahl(t.get("earningsEstimateGrowth")),
             "eps_trend_0": _zahl(t.get("epsTrendCurrent")), "eps_trend_7": _zahl(t.get("epsTrend7daysAgo")),
             "eps_trend_30": _zahl(t.get("epsTrend30daysAgo")), "eps_trend_60": _zahl(t.get("epsTrend60daysAgo")),
             "eps_trend_90": _zahl(t.get("epsTrend90daysAgo")),
             "hoch_7": _zahl(t.get("epsRevisionsUpLast7days")), "hoch_30": _zahl(t.get("epsRevisionsUpLast30days")),
             "runter_7": _zahl(t.get("epsRevisionsDownLast7days")), "runter_30": _zahl(t.get("epsRevisionsDownLast30days"))}
        if alt_form and period in ("0y", "+1y", "-1y"):
            z["hinweis"] = "jahresende_verdeckt_quartal"
        zeilen.append(z)
    history = e.get("History")
    history = history if isinstance(history, dict) else {}
    for datum, h in sorted(history.items()):
        if not isinstance(h, dict):
            continue
        zeilen.append({"art": "eps_history", "periodenende": h.get("date") or datum,
                       "meldedatum": h.get("reportDate"), "zeitpunkt": h.get("beforeAfterMarket"),
                       "waehrung": h.get("currency"), "eps_ist": _zahl(h.get("epsActual")),
                       "eps_konsens": _zahl(h.get("epsEstimate")), "eps_differenz": _zahl(h.get("epsDifference")),
                       "ueberraschung_prozent": _zahl(h.get("surprisePercent"))})
    return kopf, zeilen


def hole_splits(symbol, token, fetcher=None, warte=time.sleep):
    """Split-Historie einer Firma (Endpunkt splits, 1 API-Call): Liste von
    {date, split} mit split als Zeichenkette n/m. Noetig, weil EODHD die
    EPS-History auf die heutige Aktienzahl umrechnet, das amtliche Archiv
    aber die damals berichtete Zahl fuehrt (gemessen 03.09.2026: Apple
    0,525 gegen 2,10 = Faktor 4 aus dem Split 2020)."""
    url = f"https://eodhd.com/api/splits/{symbol}?api_token={token}&fmt=json&from=1990-01-01"
    for versuch in range(3):
        if fetcher is not None:
            status, text, kopf = fetcher("splits:" + symbol)
        else:
            import urllib.error
            import urllib.request
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "heliot-eodhd/1.0"}), timeout=60) as r:
                    status, text, kopf = r.status, r.read().decode("utf-8", "replace"), dict(r.headers)
            except urllib.error.HTTPError as e:
                status, text, kopf = e.code, e.read().decode("utf-8", "replace")[:500], dict(e.headers)
            except Exception as e:  # noqa
                status, text, kopf = 0, str(e)[:300], {}
        if status in (401, 402, 403):
            raise EodhdGesperrt(f"HTTP {status} bei Splits {symbol}: {str(text)[:200]}")
        if status == 429 or status >= 500 or status == 0:
            warte(15 if status == 429 else 10)
            continue
        break
    if status == 200:
        try:
            d = json.loads(text) if isinstance(text, str) else text
            return 200, (d if isinstance(d, list) else []), kopf
        except ValueError:
            return 200, [], kopf
    return status, [], kopf


def split_faktor(splits, ab_datum):
    """Produkt aller Splits NACH ab_datum (n/m als Faktor n durch m); damit
    laesst sich ein damals berichtetes EPS auf die heutige Aktienzahl
    bringen: damals geteilt durch Faktor."""
    f = 1.0
    for s in splits or []:
        try:
            if str(s.get("date")) <= str(ab_datum):
                continue
            n, m = str(s.get("split")).split("/")
            n, m = float(n), float(m)
            if n > 0 and m > 0:
                f *= n / m
        except (ValueError, AttributeError, TypeError):
            continue
    return f


def lauf_splits(daten, token, fetcher=None, warte=time.sleep, log=print, hoechstens=0, nur_ohne=True):
    """Split-Historie fuer alle Firmen mit ok-Stand holen (1 Call je Firma)."""
    stand = ke._json(os.path.join(daten, "eodhd", "stand.json"), {})
    firmen = [t for t, s in sorted(stand.items()) if s.get("status") == "ok" and (not nur_ohne or "splits" not in s)]
    if hoechstens:
        firmen = firmen[:hoechstens]
    bilanz = {"zeit": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(), "modus": "splits",
              "firmen": len(firmen), "ok": 0, "fehler": 0, "mit_splits": 0, "abbruch": None}
    log(f"EODHD splits: {len(firmen)} Firma(en)")
    for i, t in enumerate(firmen, 1):
        try:
            status, splits, kopf = hole_splits(eodhd_symbol(t), token, fetcher=fetcher, warte=warte)
        except EodhdGesperrt as e:
            bilanz["abbruch"] = str(e)
            break
        if status == 200:
            _gz_json(os.path.join(daten, "eodhd", "splits", f"{t}.json.gz"), splits)
            stand[t]["splits"] = len(splits)
            bilanz["ok"] += 1
            if splits:
                bilanz["mit_splits"] += 1
        else:
            bilanz["fehler"] += 1
        if i % 500 == 0:
            log(f"  ... {i} von {len(firmen)}")
            ke._schreibe_json(os.path.join(daten, "eodhd", "stand.json"), stand)
        warte(ABSTAND_S)
    ke._schreibe_json(os.path.join(daten, "eodhd", "stand.json"), stand)
    with io.open(os.path.join(daten, "eodhd", "laeufe.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(bilanz, ensure_ascii=False) + "\n")
    log(f"Ergebnis: {bilanz}")
    if bilanz["abbruch"]:
        ke.push("Konsens-Historie: EODHD-Splits abgebrochen", bilanz["abbruch"])
    return bilanz


def _gz_json(pfad, daten):
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with gzip.open(pfad, "wt", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, sort_keys=True)


def universum(daten, frische_tage, hoechstens, heute, stand, wochenlisten=None):
    """Wochenlisten zuerst, dann der Bestand mit Konsens; Firmen mit frischem
    ok-Stand werden ausgelassen. wochenlisten=None heisst die echten Listen
    (der Selbsttest gibt eine leere Liste mit)."""
    bestand = ke._json(os.path.join(daten, "konsens", "firmen_mit_konsens.json"), {})
    if wochenlisten is None:
        wochenlisten = ke.wochenlisten_ticker()
    reihe, gesehen = [], set()
    for t in list(wochenlisten) + sorted(bestand.keys()):
        t = str(t).strip().upper()
        if not t or t in gesehen:
            continue
        gesehen.add(t)
        s = stand.get(t) or {}
        if s.get("status") == "ok" and s.get("datum"):
            try:
                alter = (heute - dt.date.fromisoformat(s["datum"])).days
            except ValueError:
                alter = 10 ** 6
            if alter < frische_tage:
                continue
        if s.get("status") == "unbekannt" and s.get("datum") and s["datum"] >= (heute - dt.timedelta(days=frische_tage * 2)).isoformat():
            continue
        reihe.append(t)
        if hoechstens and len(reihe) >= hoechstens:
            break
    return reihe


def lauf(daten, modus="voll", token=None, hoechstens=0, frische_tage=90, fetcher=None,
         schreiben=None, warte=time.sleep, heute=None, log=print, budget_calls=TAGESBUDGET_CALLS,
         wochenlisten=None):
    heute = heute or dt.date.today()
    jetzt = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    if schreiben is None:
        schreiben = (modus == "voll")
    stand_pfad = os.path.join(daten, "eodhd", "stand.json")
    stand = ke._json(stand_pfad, {}) if daten else {}
    if modus == "probe":
        firmen = DEMO if token == DEMO_TOKEN else REFERENZ
        status, tarif = konto(token, fetcher=fetcher)
        if status == 401:
            log("Schluessel: UNGUELTIG (HTTP 401 am User-Endpunkt).")
        elif status == 200:
            log("Schluessel gueltig; Tarif laut Anbieter: " + json.dumps(tarif, ensure_ascii=False))
        else:
            log(f"User-Endpunkt: HTTP {status}, keine Tarifauskunft.")
    else:
        firmen = universum(daten, frische_tage, hoechstens, heute, stand, wochenlisten)
    log(f"EODHD {modus}: {len(firmen)} Firma(en), Frische {frische_tage} Tage, Budget {budget_calls} Calls")
    bilanz = {"zeit": jetzt, "modus": modus, "firmen": len(firmen), "ok": 0, "unbekannt": 0, "fehler": 0,
              "calls_geschaetzt": 0, "abbruch": None}
    for i, t in enumerate(firmen, 1):
        if bilanz["calls_geschaetzt"] + CALLS_JE_ABRUF > budget_calls:
            bilanz["abbruch"] = f"Tagesbudget erreicht nach {i - 1} Firmen"
            break
        try:
            status, antwort, kopf = hole(eodhd_symbol(t), token, fetcher=fetcher, warte=warte)
        except EodhdGesperrt as e:
            bilanz["abbruch"] = str(e)
            break
        bilanz["calls_geschaetzt"] += CALLS_JE_ABRUF
        rest = (kopf or {}).get("X-RateLimit-Remaining") or (kopf or {}).get("x-ratelimit-remaining")
        eintrag = {"datum": heute.isoformat()}
        if status == 200 and isinstance(antwort, dict):
            try:
                k, zeilen = normalisiere(t, antwort, jetzt)
            except Exception as ex:  # noqa
                # Eine einzelne kaputte Antwort darf den Lauf nicht mehr toeten.
                stand[t] = {"datum": heute.isoformat(), "status": "fehler", "http": 200, "text": f"normalisieren: {str(ex)[:100]}"}
                bilanz["fehler"] += 1
                log(f"  {t}: Antwort nicht normalisierbar: {str(ex)[:120]}")
                warte(ABSTAND_S)
                continue
            n_trend = sum(1 for z in zeilen if z["art"] == "konsens_trend")
            n_hist = sum(1 for z in zeilen if z["art"] == "eps_history")
            eintrag.update({"status": "ok", "trend": n_trend, "history": n_hist, "cik": k.get("cik")})
            bilanz["ok"] += 1
            if schreiben:
                _gz_json(os.path.join(daten, "eodhd", "roh", f"{t}.json.gz"), antwort)
                _gz_json(os.path.join(daten, "eodhd", "konsens", f"{t}.json.gz"), {"kopf": k, "zeilen": zeilen})
            if modus == "probe":
                juengst = [z for z in zeilen if z["art"] == "eps_history" and z.get("eps_ist") is not None]
                q = [z for z in zeilen if z["art"] == "konsens_trend" and z.get("umfang") == "quartal"]
                log(f"  {t}: {k.get('name')} CIK {k.get('cik')} GJ-Ende {k.get('geschaeftsjahresende')}; "
                    f"Trend {n_trend} Zeilen ({(q[0]['periodenende'] if q else '-')} bis {(q[-1]['periodenende'] if q else '-')}), "
                    f"History {n_hist} Zeilen")
                if juengst:
                    j = juengst[-1]
                    log(f"    juengstes gemeldetes Quartal {j['periodenende']}: EPS {j['eps_ist']} gegen Konsens {j['eps_konsens']}, "
                        f"Ueberraschung {j['ueberraschung_prozent']} Prozent, gemeldet {j['meldedatum']} {j['zeitpunkt']}")
                if q:
                    letzt = q[-1]
                    log(f"    Umsatzkonsens {letzt['periodenende']}: {letzt['umsatz_avg']} ({letzt['umsatz_analysten']} Analysten), "
                        f"EPS-Konsens {letzt['eps_avg']}")
        elif status == 404:
            eintrag.update({"status": "unbekannt"})
            bilanz["unbekannt"] += 1
        else:
            eintrag.update({"status": "fehler", "http": status, "text": str(antwort)[:120]})
            bilanz["fehler"] += 1
            log(f"  {t}: HTTP {status} {str(antwort)[:120]}")
        stand[t] = eintrag
        if rest is not None:
            try:
                if int(rest) < 40:
                    warte(20)
            except ValueError:
                pass
        if i % 200 == 0:
            log(f"  ... {i} von {len(firmen)}, ok {bilanz['ok']}, unbekannt {bilanz['unbekannt']}, fehler {bilanz['fehler']}")
            if schreiben:
                ke._schreibe_json(stand_pfad, stand)
        warte(ABSTAND_S)
    if schreiben and daten:
        ke._schreibe_json(stand_pfad, stand)
        with io.open(os.path.join(daten, "eodhd", "laeufe.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(bilanz, ensure_ascii=False) + "\n")
    log(f"Ergebnis: ok {bilanz['ok']}, unbekannt {bilanz['unbekannt']}, fehler {bilanz['fehler']}, "
        f"rund {bilanz['calls_geschaetzt']} API-Calls" + (f"; ABBRUCH: {bilanz['abbruch']}" if bilanz["abbruch"] else ""))
    if bilanz["abbruch"] and modus == "voll":
        ke.push("Konsens-Historie: EODHD-Lauf abgebrochen", bilanz["abbruch"])
    return bilanz


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

_DEMO_ANTWORT = {
    "General": {"Code": "AAPL", "Name": "Apple Inc", "CIK": "320193", "Exchange": "NASDAQ", "CurrencyCode": "USD",
                "FiscalYearEnd": "September", "Type": "Common Stock"},
    "Earnings": {
        "Trend": {
            "Quarterly": {
                "2017-06-30": {"date": "2017-06-30", "period": "0q", "revenueEstimateAvg": "44885600000.00",
                               "revenueEstimateNumberOfAnalysts": "36.00", "earningsEstimateAvg": "1.5700",
                               "epsTrendCurrent": "1.5700", "epsRevisionsUpLast7days": None},
                "2017-09-30": {"date": "2017-09-30", "period": "0q", "revenueEstimateAvg": "50790000000.00",
                               "revenueEstimateNumberOfAnalysts": "30.00", "earningsEstimateAvg": "1.8700"},
            },
            "Annual": {
                "2017-09-30": {"date": "2017-09-30", "period": "0y", "revenueEstimateAvg": "227414000000.00",
                               "revenueEstimateNumberOfAnalysts": "32.00", "earningsEstimateAvg": "9.0000"},
            },
        },
        "History": {
            "2017-12-31": {"reportDate": "2018-02-01", "date": "2017-12-31", "beforeAfterMarket": "AfterMarket",
                           "currency": "USD", "epsActual": 0.9725, "epsEstimate": 0.965, "epsDifference": 0.0075,
                           "surprisePercent": 0.7772},
        },
    },
}


def selbsttest() -> int:
    import tempfile
    fehler = 0

    def p(name, ok, extra=""):
        nonlocal fehler
        print(f"  {'ok  ' if ok else 'FEHL'} {name}{(' ' + str(extra)) if extra else ''}")
        if not ok:
            fehler += 1

    p("Symbol: SEC-Schreibweise BRK.B wird BRK-B.US", eodhd_symbol("brk.b") == "BRK-B.US")
    st, tarif = konto("x", fetcher=lambda s: (200, json.dumps({"name": "Max", "email": "geheim@example.org",
                                                             "subscriptionType": "Free", "dailyRateLimit": 20,
                                                             "apiRequests": 3, "apiRequestsDate": "2026-09-03"}), {}))
    p("Konto: nur Tarif und Zaehler, nie Name oder E-Mail",
      st == 200 and tarif == {"subscriptionType": "Free", "dailyRateLimit": 20, "apiRequests": 3, "apiRequestsDate": "2026-09-03"})
    p("Konto: 401 heisst ungueltiger Schluessel", konto("x", fetcher=lambda s: (401, "Unauthorized", {}))[0] == 401)
    sp = [{"date": "2014-06-09", "split": "7.000000/1.000000"}, {"date": "2020-08-31", "split": "4.000000/1.000000"}]
    p("Split-Faktor: nur Splits nach dem Quartalsende zaehlen",
      split_faktor(sp, "2017-06-30") == 4.0 and split_faktor(sp, "2013-12-31") == 28.0 and split_faktor(sp, "2021-01-01") == 1.0)
    flach = {"General::Code": "AAPL", "General::CIK": "320193", "Earnings::Trend": _DEMO_ANTWORT["Earnings"]["Trend"],
             "Earnings::History": _DEMO_ANTWORT["Earnings"]["History"]}
    kf, zf = normalisiere("AAPL", flach, "2026-09-03T10:00:00+00:00")
    p("Flache Antwort der Feld-Filter wird entflacht", kf["cik"] == "320193" and len(zf) == 4)
    kk, zk = normalisiere("KAPUTT", {"General::Code": "KAPUTT", "General::CIK": "1", "Earnings::Trend": "", "Earnings::History": "N/A"}, "2026-09-03T10:00:00+00:00")
    p("Zeichenketten statt Bloecken (Vollabzug-Absturz 03.09.2026) ergeben leere Zeilen, keinen Fehler",
      kk["cik"] == "1" and zk == [])
    kk2, zk2 = normalisiere("KAPUTT2", {"General": "", "Earnings": {"Trend": {"Quarterly": "", "Annual": None}, "History": ""}}, "2026-09-03T10:00:00+00:00")
    p("Leere Teilbloecke im v1.1-Trend ergeben leere Zeilen", zk2 == [] and kk2["name"] is None)
    kopf, zeilen = normalisiere("AAPL", _DEMO_ANTWORT, "2026-09-03T10:00:00+00:00")
    p("Kopf traegt CIK, Boerse und Geschaeftsjahresende",
      kopf["cik"] == "320193" and kopf["boerse"] == "NASDAQ" and kopf["geschaeftsjahresende"] == "September")
    tr = [z for z in zeilen if z["art"] == "konsens_trend"]
    hi = [z for z in zeilen if z["art"] == "eps_history"]
    p("Trend v1.1: Quartals- und Jahresblock getrennt, Zahlen aus Zeichenketten",
      len(tr) == 3 and tr[0]["umsatz_avg"] == 44885600000.0 and tr[0]["umsatz_analysten"] == 36.0
      and tr[0]["eps_avg"] == 1.57 and tr[0]["hoch_7"] is None and tr[0]["umfang"] == "quartal"
      and tr[1]["umfang"] == "quartal" and tr[1]["periodenende"] == "2017-09-30" and tr[2]["umfang"] == "jahr"
      and not any("hinweis" in z for z in tr))
    alt = {"General": _DEMO_ANTWORT["General"], "Earnings": {"Trend": {
        "2017-06-30": _DEMO_ANTWORT["Earnings"]["Trend"]["Quarterly"]["2017-06-30"],
        "2017-09-30": _DEMO_ANTWORT["Earnings"]["Trend"]["Annual"]["2017-09-30"]}, "History": {}}}
    _, za = normalisiere("AAPL", alt, "2026-09-03T10:00:00+00:00")
    p("Trend alte Form: Jahreszeile am Quartalsende traegt den Hinweis",
      len(za) == 2 and za[1]["umfang"] == "jahr" and za[1].get("hinweis") == "jahresende_verdeckt_quartal"
      and "hinweis" not in za[0])
    p("History: EPS ist, Konsens, Ueberraschung, Meldedatum",
      len(hi) == 1 and hi[0]["eps_ist"] == 0.9725 and hi[0]["eps_konsens"] == 0.965
      and hi[0]["ueberraschung_prozent"] == 0.7772 and hi[0]["meldedatum"] == "2018-02-01")

    with tempfile.TemporaryDirectory() as tmp:
        ke._schreibe_json(os.path.join(tmp, "konsens", "firmen_mit_konsens.json"),
                          {"AAPL": {"zuletzt": "2026-09-02"}, "ZZZZ": {"zuletzt": "2026-09-02"},
                           "FRIS": {"zuletzt": "2026-09-02"}, "ALT": {"zuletzt": "2026-09-02"}})
        ke._schreibe_json(os.path.join(tmp, "eodhd", "stand.json"),
                          {"FRIS": {"datum": "2026-09-01", "status": "ok"}, "ALT": {"datum": "2026-01-01", "status": "ok"}})
        heute = dt.date(2026, 9, 3)
        reihe = universum(tmp, 90, 0, heute, ke._json(os.path.join(tmp, "eodhd", "stand.json"), {}), wochenlisten=[])
        p("Universum: frische Firma ausgelassen, alte und ungeprueft dabei",
          "FRIS" not in reihe and "ALT" in reihe and "AAPL" in reihe and "ZZZZ" in reihe, reihe)
        aufrufe = []

        def fetcher(symbol):
            aufrufe.append(symbol)
            if symbol.startswith("ZZZZ"):
                return 404, "not found", {}
            if symbol.startswith("ALT") and len([a for a in aufrufe if a.startswith("ALT")]) == 1:
                return 429, "Too Many Requests", {}
            return 200, json.dumps(_DEMO_ANTWORT), {"X-RateLimit-Remaining": "998"}

        schlaf = []
        b = lauf(tmp, "voll", token="x", fetcher=fetcher, warte=schlaf.append, heute=heute, log=lambda *_: None,
                 wochenlisten=[])
        p("Lauf: ok 2, unbekannt 1, 429 einmal wiederholt",
          b["ok"] == 2 and b["unbekannt"] == 1 and b["fehler"] == 0 and 15 in schlaf, b)
        stand = ke._json(os.path.join(tmp, "eodhd", "stand.json"), {})
        p("Stand: ok mit Zeilenzahlen, unbekannt vermerkt, Datei liegt gepackt",
          stand["AAPL"]["status"] == "ok" and stand["AAPL"]["trend"] == 3 and stand["ZZZZ"]["status"] == "unbekannt"
          and os.path.exists(os.path.join(tmp, "eodhd", "konsens", "AAPL.json.gz"))
          and os.path.exists(os.path.join(tmp, "eodhd", "roh", "ALT.json.gz")))
        with gzip.open(os.path.join(tmp, "eodhd", "konsens", "AAPL.json.gz"), "rt", encoding="utf-8") as f:
            d = json.load(f)
        p("Abgelegte Datei traegt Kopf und Zeilen", d["kopf"]["cik"] == "320193" and len(d["zeilen"]) == 4)
        p("Lauf-Protokoll geschrieben", os.path.exists(os.path.join(tmp, "eodhd", "laeufe.jsonl")))

        def gesperrt(symbol):
            return 403, "Forbidden: plan", {}

        b2 = lauf(tmp, "voll", token="x", fetcher=gesperrt, warte=lambda s: None, heute=heute,
                  log=lambda *_: None, frische_tage=0, wochenlisten=[])
        p("Tarif- oder Schluesselfehler bricht ab statt weiterzulaufen",
          b2["abbruch"] is not None and "403" in b2["abbruch"] and b2["ok"] == 0)
        b3 = lauf(tmp, "voll", token="x", fetcher=fetcher, warte=lambda s: None, heute=heute,
                  log=lambda *_: None, frische_tage=0, budget_calls=25, wochenlisten=[])
        p("Tagesbudget begrenzt die Firmen je Lauf", b3["abbruch"] and "Tagesbudget" in b3["abbruch"] and b3["calls_geschaetzt"] <= 25)

        def fetcher_splits(symbol):
            if symbol.startswith("splits:AAPL"):
                return 200, json.dumps([{"date": "2020-08-31", "split": "4.000000/1.000000"}]), {}
            return 200, "[]", {}
        ke._schreibe_json(os.path.join(tmp, "eodhd", "stand.json"),
                          {"AAPL": {"datum": "2026-09-03", "status": "ok"}, "ALT": {"datum": "2026-09-03", "status": "ok"},
                           "ZZZZ": {"datum": "2026-09-03", "status": "unbekannt"}})
        b4 = lauf_splits(tmp, "x", fetcher=fetcher_splits, warte=lambda s: None, log=lambda *_: None)
        st2 = ke._json(os.path.join(tmp, "eodhd", "stand.json"), {})
        p("Splits: nur ok-Firmen, Datei je Firma, Zaehler im Stand",
          b4["ok"] == 2 and b4["mit_splits"] == 1 and st2["AAPL"]["splits"] == 1 and st2["ALT"]["splits"] == 0
          and os.path.exists(os.path.join(tmp, "eodhd", "splits", "AAPL.json.gz")), b4)
        b5 = lauf_splits(tmp, "x", fetcher=fetcher_splits, warte=lambda s: None, log=lambda *_: None)
        p("Splits: zweiter Lauf holt nichts doppelt", b5["firmen"] == 0)
    print("\n" + ("Alles bestanden." if fehler == 0 else f"{fehler} Fehler."))
    return fehler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--daten", default="")
    ap.add_argument("--modus", default="probe", choices=["probe", "voll", "splits"])
    ap.add_argument("--hoechstens", type=int, default=0)
    ap.add_argument("--frische", type=int, default=90)
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--schreiben", action="store_true", help="Probe-Modus trotzdem ins Datenrepo schreiben")
    ap.add_argument("--selbsttest", action="store_true")
    a = ap.parse_args()
    if a.selbsttest:
        sys.exit(1 if selbsttest() else 0)
    token = DEMO_TOKEN if a.demo else (os.environ.get("EODHD_API_KEY") or "").strip()
    if not token:
        print("EODHD_API_KEY fehlt (Secret) und --demo nicht gesetzt; nichts zu tun.")
        sys.exit(0)
    if a.modus in ("voll", "splits") and not a.daten:
        print("--daten fehlt.")
        sys.exit(2)
    if a.modus == "splits":
        b = lauf_splits(a.daten, token, hoechstens=a.hoechstens)
        sys.exit(1 if b["abbruch"] else 0)
    b = lauf(a.daten, a.modus, token=token, hoechstens=a.hoechstens, frische_tage=a.frische,
             schreiben=(True if a.schreiben else None))
    sys.exit(1 if (b["abbruch"] and a.modus == "voll" and b["ok"] == 0) else 0)


if __name__ == "__main__":
    main()
