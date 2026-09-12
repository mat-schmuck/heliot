# -*- coding: utf-8 -*-
"""EODHD-Vollabzug: alles holen, was der Tarif Fundamentals Data Feed hergibt.

WARUM (Mathias, 12.09.2026, nach Gerhards Antwort vom selben Tag): Das
EODHD-Abo laeuft am 03.10.2026 aus. Bis dahin soll alles gezogen werden,
was mit dem Zugang moeglich ist; Vorrang haben die delisteten Firmen, dann
die Branchenzuordnung des Universums und die Fundamentals auslaendischer
Listings (Gerhards Luecke 2). Die Daten sind lizenziert und bleiben im
PRIVATEN Datenrepo heliot-daten (F17); sie werden nirgends angezeigt oder
weitergegeben.

WAS DER TARIF HERGIBT (Doku gelesen 12.09.2026): Fundamentals je Symbol
(10 Calls, ungefiltert mit Financials, Highlights, Valuation, SharesStats,
Technicals, SplitsDividends, AnalystRatings, Holders, InsiderTransactions,
outstandingShares, Earnings; bei ETFs ETF_Data samt Holdings, bei Fonds
MutualFund_Data, bei Indizes Components und HistoricalTickerComponents),
die Symbollisten je Boerse mit und ohne delistete Titel (1 Call), die
Boersenliste (1 Call), die Kalender earnings, ipos, splits, trends (je 1
Call, trends mit vielen Symbolen je Anfrage), Economic Events (1 Call je
Seite) und die Makro-Indikatoren je Land (10 Calls). NICHT im Tarif:
Kurse (EOD, Intraday), Bulk-Fundamentals, News, Screener, der
Splits-Endpunkt (403, gemessen 03.09.2026).

BUDGET: 100.000 Calls je Tag, Zaehler ab Mitternacht GMT; 1.000 Anfragen
je Minute. Bei 10 Calls je Fundamentals-Abruf sind das rund 9.700 Symbole
je Tag nach Abzug der Reserve. Der Lauf fragt das Konto (/api/user), rechnet
sein Restbudget selbst und wartet bei Bedarf ueber Mitternacht GMT hinweg.

ABLAGE: Die Rohantworten (eine gepackte Datei je Symbol) gehen als
tar-Archive je Stufe und Lauf in die RELEASES des Datenrepos, nicht in
dessen Dateibaum: 80.000 Dateien zu je 20 bis 150 KB wuerden jeden Checkout
des Datenrepos (die Konsens-Schnappschuesse laufen zweimal taeglich) um
Gigabytes verlangsamen. Im Dateibaum liegen nur das Register stand.json
(je Symbol Stufe, Datum, Status, Groesse, Release und Archiv), die
Symbollisten, die Kalender, die Makro-Reihen, die Trends und die Laufe.

Aufruf (nur im Actions-Lauf: Secrets EODHD_API_KEY, DATEN_TOKEN; NTFY_TOPIC
fuer die Bilanz):
  python eodhd_voll.py --daten daten --modus inventur
  python eodhd_voll.py --daten daten --modus voll [--stufen a,b] [--hoechstens N]
                       [--zeitgrenze-min 300]
  python eodhd_voll.py --selbsttest
"""
import argparse
import datetime as dt
import gzip
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request

BASIS = "https://eodhd.com/api"
ORDNER = "eodhd_voll"
DATENREPO = "mat-schmuck/heliot-daten"
ABSTAND_S = 0.2                    # 5 Anfragen je Sekunde, weit unter 1.000 je Minute
RESERVE_CALLS = 3000               # bleibt frei fuer Konsens-Laeufe und Proben
CALLS_FUNDAMENTALS = 10
CALLS_MAKRO = 10
ARCHIV_TEILE_BYTES = 1_900_000_000  # Release-Anhaenge duerfen 2 GB nicht ueberschreiten
KONTO_FELDER = ("subscriptionType", "dailyRateLimit", "apiRequests", "apiRequestsDate", "extraLimit")

# Boersenplaetze der US-Liste, die als "an der Boerse" gelten; alles andere
# ist Freiverkehr (OTCQX, OTCQB, PINK, OTCGREY, OTCMKTS, NMFQS ...).
BOERSEN_HAUPT = {"NYSE", "NASDAQ", "NYSE ARCA", "NYSE MKT", "NYSE AMERICAN", "AMEX", "BATS", "CBOE", "IEX"}
TYP_STAMM = {"common stock"}
TYP_ETF = {"etf"}
TYP_FONDS = {"fund", "mutual fund"}

# Reihenfolge = Vorrang. Gerhard: zuerst die delisteten Firmen.
STUFEN = [
    ("delisted_stock", "delistete Aktien (Common Stock)"),
    ("stock_boerse", "aktive Aktien an NYSE, Nasdaq, NYSE Arca, NYSE American, Cboe"),
    ("stock_otc", "aktive Aktien im Freiverkehr (OTC, Pink Sheets und andere)"),
    ("etf", "aktive ETFs"),
    ("fund", "aktive Fonds"),
    ("sonstige", "aktive Vorzugsaktien, Optionsscheine, Einheiten, Rechte, Anleihen"),
    ("delisted_rest", "delistete ETFs, Fonds, Vorzugsaktien und Uebriges"),
    ("index", "Indizes mit Komponenten und Mitgliedschaftsgeschichte"),
    ("makro", "Makro-Indikatoren je Land"),
]
STUFEN_NAMEN = [s for s, _ in STUFEN]

MAKRO_LAENDER = ["USA", "CAN", "GBR", "DEU", "FRA", "ITA", "ESP", "NLD", "CHE", "AUT", "SWE", "DNK",
                 "NOR", "FIN", "IRL", "BEL", "POL", "JPN", "CHN", "KOR", "TWN", "IND", "HKG", "SGP",
                 "AUS", "NZL", "BRA", "MEX", "ARG", "CHL", "ZAF", "ISR", "SAU", "ARE", "TUR", "RUS",
                 "IDN", "THA", "VNM", "EUU", "WLD", "OED"]
MAKRO_INDIKATOREN = [
    "gdp_current_usd", "gdp_per_capita_usd", "gdp_growth_annual", "gni_usd", "gni_per_capita_usd",
    "gni_ppp_usd", "gni_per_capita_ppp_usd", "gross_capital_formation_percent_gdp",
    "agriculture_value_added_percent_gdp", "industry_value_added_percent_gdp",
    "services_value_added_percent_gdp", "inflation_consumer_prices_annual", "consumer_price_index",
    "inflation_gdp_deflator_annual", "real_interest_rate", "net_trades_goods_services",
    "exports_of_goods_services_percent_gdp", "imports_of_goods_services_percent_gdp",
    "merchandise_trade_percent_gdp", "high_technology_exports_percent_total", "debt_percent_gdp",
    "revenue_excluding_grants_percent_gdp", "cash_surplus_deficit_percent_gdp",
    "total_debt_service_percent_gni", "population_total", "population_growth_annual", "net_migration",
    "life_expectancy", "fertility_rate", "prevalence_hiv_total", "unemployment_total_percent",
    "income_share_lowest_twenty", "poverty_poverty_lines_percent_population",
    "market_cap_domestic_companies_percent_gdp", "mobile_subscriptions_per_hundred",
    "internet_users_per_hundred", "startup_procedures_register", "co2_emissions_tons_per_capita",
    "surface_area_km",
]

RESERVIERT = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}


class EodhdGesperrt(Exception):
    """Schluessel ungueltig, Tarif reicht nicht oder Konto gesperrt: der Lauf
    bricht ab, statt tausendmal denselben Fehler zu sammeln."""


# ---------------------------------------------------------------------------
# Hilfen
# ---------------------------------------------------------------------------

def _utc_jetzt():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def _json_lesen(pfad, vorgabe):
    try:
        with io.open(pfad, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return vorgabe


def _json_schreiben(pfad, daten):
    os.makedirs(os.path.dirname(pfad) or ".", exist_ok=True)
    with io.open(pfad, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=1, sort_keys=True)


def _gz_json(pfad, daten):
    os.makedirs(os.path.dirname(pfad) or ".", exist_ok=True)
    with gzip.open(pfad, "wt", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, sort_keys=True)
    return os.path.getsize(pfad)


def _gz_text(pfad, text):
    os.makedirs(os.path.dirname(pfad) or ".", exist_ok=True)
    with gzip.open(pfad, "wt", encoding="utf-8") as f:
        f.write(text)
    return os.path.getsize(pfad)


def sicherer_dateiname(symbol):
    """Dateiname je Symbol: nur Buchstaben, Ziffern, Punkt, Bindestrich und
    Unterstrich; reservierte Windows-Geraetenamen bekommen einen Unterstrich
    (Befund 03.09.2026 am Ticker CON)."""
    s = re.sub(r"[^A-Za-z0-9.\-_]", "_", str(symbol).strip().upper())
    basis = s.split(".")[0]
    if basis in RESERVIERT:
        s = basis + "_" + s[len(basis):]
    return s or "_"


def sekunden_bis_mitternacht_gmt(jetzt=None):
    jetzt = jetzt or _utc_jetzt()
    morgen = (jetzt + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return (morgen - jetzt).total_seconds()


def push(titel, text, prio="low"):
    """Meldung ueber ntfy, nur wenn das Thema als Secret gesetzt ist. Der
    Wert des Themas wird nie ausgegeben."""
    topic = (os.environ.get("NTFY_TOPIC") or "").strip()
    if not topic:
        print("(kein NTFY_TOPIC, keine Meldung)")
        return False
    try:
        import requests
        r = requests.post(f"https://ntfy.sh/{topic}", data=text.encode("utf-8"),
                          headers={"Title": titel.encode("utf-8"), "Priority": prio}, timeout=20)
        return r.status_code < 400
    except Exception as e:  # noqa
        print(f"Push fehlgeschlagen: {type(e).__name__}")
        return False


# ---------------------------------------------------------------------------
# Abruf
# ---------------------------------------------------------------------------

def abruf(pfad, token, params=None, fetcher=None, warte=time.sleep, versuche=4):
    """Eine Anfrage an EODHD. Liefert (status, text, kopf). 429, 5xx und
    Netzfehler werden wiederholt, 401 und 402 und 403 werfen EodhdGesperrt.
    Der Schluessel steht nur in der Anfrage, nie in einer Ausgabe."""
    q = {"api_token": token, "fmt": "json"}
    q.update(params or {})
    url = f"{BASIS}/{pfad.lstrip('/')}?{urllib.parse.urlencode(q)}"
    kennung = f"{pfad}?" + urllib.parse.urlencode({k: v for k, v in (params or {}).items()})
    status, text, kopf = 0, "", {}
    for versuch in range(versuche):
        if fetcher is not None:
            status, text, kopf = fetcher(kennung)
        else:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "heliot-eodhd-voll/1.0"})
                with urllib.request.urlopen(req, timeout=120) as r:
                    status, text, kopf = r.status, r.read().decode("utf-8", "replace"), dict(r.headers)
            except urllib.error.HTTPError as e:
                status, text, kopf = e.code, e.read().decode("utf-8", "replace")[:500], dict(e.headers)
            except Exception as e:  # noqa
                status, text, kopf = 0, f"{type(e).__name__}: {str(e)[:200]}", {}
        if status in (401, 402, 403):
            raise EodhdGesperrt(f"HTTP {status} bei {kennung[:80]}: {str(text)[:160]}")
        if status == 429 or status >= 500 or status == 0:
            warte(20 if status == 429 else 10 * (versuch + 1))
            continue
        break
    return status, text, kopf


def abruf_json(pfad, token, params=None, fetcher=None, warte=time.sleep):
    """(status, daten_oder_None, kopf, bytes). Eine leere oder nicht lesbare
    200-Antwort liefert None als Daten."""
    status, text, kopf = abruf(pfad, token, params, fetcher, warte)
    if status != 200:
        return status, None, kopf, len(text or "")
    try:
        d = json.loads(text) if isinstance(text, str) else text
    except ValueError:
        return 200, None, kopf, len(text or "")
    return 200, d, kopf, (len(text) if isinstance(text, str) else len(json.dumps(text)))


def konto(token, fetcher=None):
    """Tarif und Tageszaehler des Kontos; nie Name oder E-Mail (die Logs des
    Repos heliot sind oeffentlich). Liefert (status, dict)."""
    status, d, _, _ = abruf_json("user", token, fetcher=fetcher)
    if status != 200 or not isinstance(d, dict):
        return status, {}
    return status, {k: d.get(k) for k in KONTO_FELDER if k in d}


def restbudget(tarif, reserve=RESERVE_CALLS, heute_gmt=None):
    """Wie viele Calls heute noch frei sind. Der Zaehler des Anbieters gilt
    nur, wenn sein Datum der heutige GMT-Tag ist; sonst ist er der Stand von
    gestern und der Tag beginnt bei null."""
    heute_gmt = heute_gmt or _utc_jetzt().date().isoformat()
    try:
        grenze = int(tarif.get("dailyRateLimit") or 0) + int(tarif.get("extraLimit") or 0)
    except (TypeError, ValueError):
        grenze = 0
    verbraucht = 0
    if str(tarif.get("apiRequestsDate") or "")[:10] == heute_gmt:
        try:
            verbraucht = int(tarif.get("apiRequests") or 0)
        except (TypeError, ValueError):
            verbraucht = 0
    return max(0, grenze - verbraucht - reserve)


# ---------------------------------------------------------------------------
# Symbollisten und Einordnung
# ---------------------------------------------------------------------------

def symbolliste(token, boerse="US", delisted=False, fetcher=None, warte=time.sleep):
    params = {"delisted": "1"} if delisted else {}
    status, d, _, groesse = abruf_json(f"exchange-symbol-list/{boerse}", token, params, fetcher, warte)
    if status != 200 or not isinstance(d, list):
        raise RuntimeError(f"Symbolliste {boerse} delisted={int(delisted)}: HTTP {status}")
    return d, groesse


def _typ(e):
    return str(e.get("Type") or "").strip().lower()


def _boerse(e):
    return str(e.get("Exchange") or "").strip().upper()


def einordnen(aktiv, delisted):
    """Die Symbole der US-Listen auf die Stufen verteilen. Rueckgabe:
    {stufe: [eintrag mit Code, Name, Exchange, Type, Isin, delisted]}."""
    stufen = {s: [] for s in STUFEN_NAMEN}
    aktive_codes = set()
    for e in aktiv or []:
        code = str(e.get("Code") or "").strip()
        if not code:
            continue
        aktive_codes.add(code.upper())
        typ, boerse = _typ(e), _boerse(e)
        eintrag = {"Code": code, "Name": e.get("Name"), "Exchange": e.get("Exchange"),
                   "Type": e.get("Type"), "Isin": e.get("Isin"), "delisted": False}
        if typ in TYP_STAMM:
            stufen["stock_boerse" if boerse in BOERSEN_HAUPT else "stock_otc"].append(eintrag)
        elif typ in TYP_ETF:
            stufen["etf"].append(eintrag)
        elif typ in TYP_FONDS:
            stufen["fund"].append(eintrag)
        else:
            stufen["sonstige"].append(eintrag)
    for e in delisted or []:
        code = str(e.get("Code") or "").strip()
        if not code:
            continue
        eintrag = {"Code": code, "Name": e.get("Name"), "Exchange": e.get("Exchange"),
                   "Type": e.get("Type"), "Isin": e.get("Isin"), "delisted": True,
                   # Derselbe Code auch bei einer AKTIVEN Firma: EODHD liefert
                   # unter dem Symbol die aktive; der Vermerk bleibt im Register.
                   "code_auch_aktiv": code.upper() in aktive_codes}
        stufen["delisted_stock" if _typ(e) in TYP_STAMM else "delisted_rest"].append(eintrag)
    for s in stufen:
        stufen[s].sort(key=lambda x: x["Code"].upper())
    return stufen


def schluessel(stufe, code):
    """Registerschluessel je Stufe und Code. Derselbe Code kann aktiv und
    delisted vorkommen; die Stufe haelt beide auseinander."""
    return f"{stufe}:{str(code).strip().upper()}"


def eodhd_symbol(stufe, code):
    return f"{str(code).strip().upper()}.INDX" if stufe == "index" else f"{str(code).strip().upper()}.US"


# ---------------------------------------------------------------------------
# Archive und Releases
# ---------------------------------------------------------------------------

def archive_bauen(arbeit, stufe, lauf, ziel, teile_bytes=ARCHIV_TEILE_BYTES):
    """Alle Dateien eines Stufen-Ordners in tar-Archive (ohne zweite
    Kompression, die Dateien sind gepackt), hoechstens teile_bytes je Archiv.
    Rueckgabe: [(archivpfad, [dateinamen])]."""
    ordner = os.path.join(arbeit, stufe)
    if not os.path.isdir(ordner):
        return []
    namen = sorted(n for n in os.listdir(ordner) if n.endswith(".json.gz"))
    if not namen:
        return []
    os.makedirs(ziel, exist_ok=True)
    archive, teil, aktuell, groesse = [], 1, [], 0
    for n in namen:
        g = os.path.getsize(os.path.join(ordner, n))
        if aktuell and groesse + g > teile_bytes:
            archive.append((teil, aktuell)); teil += 1; aktuell, groesse = [], 0
        aktuell.append(n); groesse += g
    if aktuell:
        archive.append((teil, aktuell))
    raus = []
    for teil, liste in archive:
        name = f"eodhd_{stufe}_{lauf}" + (f"_teil{teil}" if len(archive) > 1 else "") + ".tar"
        pfad = os.path.join(ziel, name)
        with tarfile.open(pfad, "w") as tar:
            for n in liste:
                tar.add(os.path.join(ordner, n), arcname=f"{stufe}/{n}")
        raus.append((pfad, liste))
    return raus


# Releases, die dieser Prozess schon angelegt oder gesehen hat: spart je
# Stufe die Nachfrage beim Anbieter.
_RELEASES_ANGELEGT = set()


def release_hochladen(tag, dateien, titel, notizen, repo=DATENREPO, runner=None, log=print):
    """Ein Release im Datenrepo anlegen (falls noetig) und die Dateien
    anhaengen; ueber die gh-Befehlszeile mit GH_TOKEN aus der Umgebung.
    runner ersetzt subprocess.run im Selbsttest. Rueckgabe True bei Erfolg."""
    runner = runner or (lambda args: subprocess.run(args, capture_output=True, text=True, timeout=3600))
    if not dateien:
        return True
    if tag not in _RELEASES_ANGELEGT:
        r = runner(["gh", "release", "view", tag, "--repo", repo])
        if r.returncode != 0:
            r = runner(["gh", "release", "create", tag, "--repo", repo, "--title", titel, "--notes", notizen])
            if r.returncode != 0:
                log(f"  Release {tag} konnte nicht angelegt werden: {(r.stderr or '')[:200]}")
                return False
        _RELEASES_ANGELEGT.add(tag)
    for versuch in range(3):
        r = runner(["gh", "release", "upload", tag, "--repo", repo, "--clobber"] + list(dateien))
        if r.returncode == 0:
            return True
        log(f"  Upload nach {tag} fehlgeschlagen (Versuch {versuch + 1}): {(r.stderr or '')[:200]}")
        time.sleep(30)
    return False


# ---------------------------------------------------------------------------
# Inventur
# ---------------------------------------------------------------------------

def _probe(token, pfad, params, fetcher, warte, name, bilanz, calls):
    """Eine Probeanfrage: Groesse roh und gepackt, Status. Kostet calls.
    Ein 403 (Endpunkt nicht im Tarif) ist hier ein Befund, kein Abbruch."""
    try:
        status, text, kopf = abruf(pfad, token, params, fetcher, warte)
    except EodhdGesperrt as e:
        status, text, kopf = (403 if "403" in str(e) else 402), "", {}
        bilanz["hinweise"].append(f"{name}: nicht im Tarif ({str(e)[:80]})")
    gz = len(gzip.compress(text.encode("utf-8"))) if status == 200 and text else 0
    bilanz["proben"][name] = {"status": status, "bytes": len(text or ""), "bytes_gz": gz,
                              "rate_limit_rest": (kopf or {}).get("X-RateLimit-Remaining")
                              or (kopf or {}).get("x-ratelimit-remaining")}
    bilanz["calls_geschaetzt"] += calls
    warte(ABSTAND_S)
    return status, text


def inventur(daten, token, fetcher=None, warte=time.sleep, log=print, heute=None):
    """Was gibt es, wie gross ist es, wie lange dauert es? Legt die
    Symbollisten, die Kalender und Proben im Datenrepo ab und schreibt
    inventur.json samt einem lesbaren Bericht."""
    heute = heute or _utc_jetzt().date()
    tag = heute.isoformat()
    wurzel = os.path.join(daten, ORDNER)
    bilanz = {"zeit": _utc_jetzt().isoformat(), "modus": "inventur", "calls_geschaetzt": 0,
              "proben": {}, "listen": {}, "stufen": {}, "hinweise": []}
    status, tarif = konto(token, fetcher)
    bilanz["konto_status"] = status
    bilanz["tarif"] = tarif
    if status == 401:
        raise EodhdGesperrt("Schluessel ungueltig (HTTP 401 am User-Endpunkt)")
    log("Konto: " + json.dumps(tarif, ensure_ascii=False))

    # 1. Symbollisten
    aktiv, g1 = symbolliste(token, "US", False, fetcher, warte)
    bilanz["calls_geschaetzt"] += 1
    warte(ABSTAND_S)
    delisted, g2 = symbolliste(token, "US", True, fetcher, warte)
    bilanz["calls_geschaetzt"] += 1
    warte(ABSTAND_S)
    _gz_json(os.path.join(wurzel, "listen", f"us_aktiv_{tag}.json.gz"), aktiv)
    _gz_json(os.path.join(wurzel, "listen", f"us_delisted_{tag}.json.gz"), delisted)
    bilanz["listen"] = {"us_aktiv": len(aktiv), "us_aktiv_bytes": g1,
                        "us_delisted": len(delisted), "us_delisted_bytes": g2}
    st, boersen, _, _ = abruf_json("exchanges-list", token, fetcher=fetcher, warte=warte)
    bilanz["calls_geschaetzt"] += 1
    warte(ABSTAND_S)
    if st == 200 and isinstance(boersen, list):
        _gz_json(os.path.join(wurzel, "listen", f"exchanges_{tag}.json.gz"), boersen)
        bilanz["listen"]["boersen"] = len(boersen)
    st, indizes, _, _ = abruf_json("exchange-symbol-list/INDX", token, fetcher=fetcher, warte=warte)
    bilanz["calls_geschaetzt"] += 1
    warte(ABSTAND_S)
    if st == 200 and isinstance(indizes, list):
        _gz_json(os.path.join(wurzel, "listen", f"indx_{tag}.json.gz"), indizes)
        bilanz["listen"]["indizes"] = len(indizes)
    else:
        indizes = []

    # 2. Einordnung und Typen
    stufen = einordnen(aktiv, delisted)
    typen_aktiv, typen_del, boersen_aktiv = {}, {}, {}
    for e in aktiv:
        typen_aktiv[str(e.get("Type"))] = typen_aktiv.get(str(e.get("Type")), 0) + 1
        boersen_aktiv[str(e.get("Exchange"))] = boersen_aktiv.get(str(e.get("Exchange")), 0) + 1
    for e in delisted:
        typen_del[str(e.get("Type"))] = typen_del.get(str(e.get("Type")), 0) + 1
    bilanz["typen_aktiv"], bilanz["typen_delisted"], bilanz["boersen_aktiv"] = typen_aktiv, typen_del, boersen_aktiv
    for s, liste in stufen.items():
        bilanz["stufen"][s] = len(liste)
    bilanz["stufen"]["index"] = len(indizes)
    bilanz["stufen"]["makro"] = len(MAKRO_LAENDER) * len(MAKRO_INDIKATOREN)
    kollisionen = sum(1 for e in stufen["delisted_stock"] + stufen["delisted_rest"] if e.get("code_auch_aktiv"))
    bilanz["delisted_code_auch_aktiv"] = kollisionen

    # 3. Groessenproben (ungefilterte Fundamentals), 10 Calls je Probe
    proben = [("aapl", "fundamentals/AAPL.US", {}), ("jpm", "fundamentals/JPM.US", {}),
              ("spy_etf", "fundamentals/SPY.US", {}), ("gspc_index", "fundamentals/GSPC.INDX", {}),
              ("gspc_historisch", "fundamentals/GSPC.INDX", {"historical": "1", "from": "1991-01-01", "to": tag})]
    if stufen["delisted_stock"]:
        e = next((x for x in stufen["delisted_stock"] if str(x["Code"]).upper() == "ATVI"), stufen["delisted_stock"][0])
        proben.append(("delisted_" + e["Code"].lower(), f"fundamentals/{e['Code'].upper()}.US", {}))
    if stufen["fund"]:
        e = stufen["fund"][len(stufen["fund"]) // 2]
        proben.append(("fund_" + e["Code"].lower(), f"fundamentals/{e['Code'].upper()}.US", {}))
    if stufen["stock_otc"]:
        e = stufen["stock_otc"][len(stufen["stock_otc"]) // 2]
        proben.append(("otc_" + e["Code"].lower(), f"fundamentals/{e['Code'].upper()}.US", {}))
    for name, pfad, params in proben:
        st, text = _probe(token, pfad, params, fetcher, warte, name, bilanz, CALLS_FUNDAMENTALS)
        if st == 200 and text:
            _gz_text(os.path.join(wurzel, "proben", f"{name}_{tag}.json.gz"), text)
    # Groessenschaetzung: Mittel der Aktienproben, gepackt
    aktien_gz = [p["bytes_gz"] for n, p in bilanz["proben"].items()
                 if p["status"] == 200 and (n in ("aapl", "jpm") or n.startswith(("delisted_", "otc_")))]
    mittel_gz = (sum(aktien_gz) / len(aktien_gz)) if aktien_gz else 0
    bilanz["bytes_gz_je_aktie_geschaetzt"] = round(mittel_gz)

    # 4. Kalender und Ereignisse (je 1 Call je Anfrage)
    kalender = [("earnings_2016_2026", "calendar/earnings", {"from": "2016-01-01", "to": tag}),
                ("earnings_2006_2016", "calendar/earnings", {"from": "2006-01-01", "to": "2015-12-31"}),
                ("earnings_1996_2006", "calendar/earnings", {"from": "1996-01-01", "to": "2005-12-31"}),
                ("earnings_kommend", "calendar/earnings", {"from": tag, "to": (heute + dt.timedelta(days=120)).isoformat()}),
                ("ipos_2000_heute", "calendar/ipos", {"from": "2000-01-01", "to": (heute + dt.timedelta(days=60)).isoformat()}),
                ("splits_2000_heute", "calendar/splits", {"from": "2000-01-01", "to": (heute + dt.timedelta(days=180)).isoformat()})]
    for name, pfad, params in kalender:
        st, text = _probe(token, pfad, params, fetcher, warte, name, bilanz, 1)
        if st == 200 and text:
            _gz_text(os.path.join(wurzel, "kalender", f"{name}_{tag}.json.gz"), text)
    # Economic Events, ab 2020, alle Laender, seitenweise
    seiten, gesamt = 0, 0
    jahr = 2020
    while jahr <= heute.year:
        von, bis = f"{jahr}-01-01", (f"{jahr}-12-31" if jahr < heute.year else tag)
        offset, zeilen = 0, []
        while True:
            st, d, _, _ = abruf_json("economic-events", token, {"from": von, "to": bis, "limit": 1000, "offset": offset},
                                     fetcher, warte)
            bilanz["calls_geschaetzt"] += 1
            seiten += 1
            warte(ABSTAND_S)
            if st != 200 or not isinstance(d, list) or not d:
                break
            zeilen.extend(d)
            if len(d) < 1000 or offset >= 20000:
                break
            offset += 1000
        if zeilen:
            _gz_json(os.path.join(wurzel, "kalender", f"events_{jahr}.json.gz"), zeilen)
            gesamt += len(zeilen)
        jahr += 1
    bilanz["events"] = {"seiten": seiten, "eintraege": gesamt}

    # 5. Trends-Probe: 100 Symbole in EINER Anfrage; der Call-Verbrauch wird am
    #    Konto abgelesen (vorher/nachher), weil die Doku "1 Call" verspricht.
    probe_symbole = [e["Code"] for e in stufen["stock_boerse"][:100]]
    if probe_symbole:
        st1, t1 = konto(token, fetcher)
        st, text = _probe(token, "calendar/trends", {"symbols": ",".join(f"{c}.US" for c in probe_symbole)},
                          fetcher, warte, "trends_100", bilanz, 1)
        if st == 200 and text:
            _gz_text(os.path.join(wurzel, "trends", f"probe_{tag}.json.gz"), text)
        st2, t2 = konto(token, fetcher)
        try:
            bilanz["trends_100_calls_laut_konto"] = int(t2.get("apiRequests") or 0) - int(t1.get("apiRequests") or 0)
        except (TypeError, ValueError):
            bilanz["trends_100_calls_laut_konto"] = None

    # 6. Makro-Probe (USA, ein Indikator) und Symbolwechsel-Probe
    st, text = _probe(token, "macro-indicator/USA", {"indicator": "gdp_current_usd"}, fetcher, warte,
                      "makro_usa_gdp", bilanz, CALLS_MAKRO)
    if st == 200 and text:
        _gz_text(os.path.join(wurzel, "makro", f"USA_gdp_current_usd_{tag}.json.gz"), text)
    for name, pfad in (("symbolwechsel_a", "symbol-change-history"), ("symbolwechsel_b", "symbol-change-history/US")):
        st, text = _probe(token, pfad, {"from": "2000-01-01", "to": tag}, fetcher, warte, name, bilanz, 1)
        if st == 200 and text and len(text) > 2:
            _gz_text(os.path.join(wurzel, "listen", f"symbolwechsel_{tag}.json.gz"), text)
            break
    # Handelszeiten und Feiertage: laut Doku nur in anderen Tarifen; die
    # Probe sagt, ob unser Zugang sie trotzdem hergibt (5 Calls).
    st, text = _probe(token, "v2/exchange-details/US", {}, fetcher, warte, "boersenkalender_us", bilanz, 5)
    if st == 200 and text:
        _gz_text(os.path.join(wurzel, "listen", f"boersenkalender_us_{tag}.json.gz"), text)

    # 7. Schaetzung: Calls je Stufe, Tage bei vollem Budget, Datenmenge
    je_tag = max(1, restbudget(tarif, RESERVE_CALLS))
    schaetzung = {}
    gesamt_calls = 0
    for s in STUFEN_NAMEN:
        n = bilanz["stufen"].get(s, 0)
        calls = n * (CALLS_MAKRO if s == "makro" else CALLS_FUNDAMENTALS)
        gesamt_calls += calls
        schaetzung[s] = {"symbole": n, "calls": calls, "tage": round(calls / 97000, 2),
                         "bytes_gz_geschaetzt": int(n * mittel_gz) if s not in ("index", "makro") else None}
    bilanz["schaetzung"] = schaetzung
    bilanz["schaetzung_gesamt"] = {"calls": gesamt_calls, "tage_bei_97000": round(gesamt_calls / 97000, 1),
                                   "heute_frei": je_tag,
                                   "bytes_gz_aktien_etf_fonds": int(sum(bilanz["stufen"].get(s, 0) for s in STUFEN_NAMEN if s not in ("index", "makro")) * mittel_gz)}
    _json_schreiben(os.path.join(wurzel, "inventur.json"), bilanz)
    bericht = inventur_bericht(bilanz)
    with io.open(os.path.join(wurzel, "inventur.md"), "w", encoding="utf-8") as f:
        f.write(bericht)
    with io.open(os.path.join(wurzel, "laeufe.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({k: v for k, v in bilanz.items() if k in ("zeit", "modus", "calls_geschaetzt", "listen", "stufen", "schaetzung_gesamt")}, ensure_ascii=False) + "\n")
    log(bericht)
    return bilanz


def inventur_bericht(b):
    z = ["EODHD-Inventur vom " + str(b.get("zeit", ""))[:16].replace("T", " ") + " UTC",
         "Tarif laut Anbieter: " + json.dumps(b.get("tarif", {}), ensure_ascii=False),
         f"US-Liste aktiv: {b['listen'].get('us_aktiv')} Symbole; delistet: {b['listen'].get('us_delisted')}; "
         f"Boersen: {b['listen'].get('boersen', '?')}; Indizes: {b['listen'].get('indizes', '?')}",
         "Typen aktiv: " + ", ".join(f"{k} {v}" for k, v in sorted(b.get("typen_aktiv", {}).items(), key=lambda kv: -kv[1])),
         "Typen delistet: " + ", ".join(f"{k} {v}" for k, v in sorted(b.get("typen_delisted", {}).items(), key=lambda kv: -kv[1])),
         "Boersen aktiv: " + ", ".join(f"{k} {v}" for k, v in sorted(b.get("boersen_aktiv", {}).items(), key=lambda kv: -kv[1])[:12]),
         f"Delistete Codes, die auch aktiv vorkommen: {b.get('delisted_code_auch_aktiv')}",
         "Stufen: " + "; ".join(f"{s} {b['stufen'].get(s, 0)}" for s in STUFEN_NAMEN),
         "Proben (Status, Bytes roh, Bytes gepackt): " + "; ".join(
             f"{n} {p['status']}, {p['bytes']}, {p['bytes_gz']}" for n, p in b.get("proben", {}).items()),
         f"Gepackte Groesse je Aktie, geschaetzt: {b.get('bytes_gz_je_aktie_geschaetzt')} Bytes",
         f"Trends-Probe mit 100 Symbolen kostete laut Konto {b.get('trends_100_calls_laut_konto')} Calls",
         f"Economic Events ab 2020: {b.get('events', {}).get('eintraege')} Eintraege in {b.get('events', {}).get('seiten')} Seiten",
         "Schaetzung je Stufe (Symbole, Calls, Tage bei 97.000 Calls je Tag): " + "; ".join(
             f"{s} {v['symbole']}, {v['calls']}, {v['tage']}" for s, v in b.get("schaetzung", {}).items()),
         f"Gesamt: {b.get('schaetzung_gesamt', {}).get('calls')} Calls, "
         f"{b.get('schaetzung_gesamt', {}).get('tage_bei_97000')} Tage; heute noch frei {b.get('schaetzung_gesamt', {}).get('heute_frei')} Calls; "
         f"Datenmenge Aktien, ETFs und Fonds gepackt rund {round((b.get('schaetzung_gesamt', {}).get('bytes_gz_aktien_etf_fonds') or 0) / 1e9, 2)} GB",
         f"Calls dieser Inventur, geschaetzt: {b.get('calls_geschaetzt')}"]
    return "\n".join(z) + "\n"


# ---------------------------------------------------------------------------
# Vollabzug
# ---------------------------------------------------------------------------

def _juengste_liste(wurzel, praefix):
    ordner = os.path.join(wurzel, "listen")
    if not os.path.isdir(ordner):
        return None
    namen = sorted(n for n in os.listdir(ordner) if n.startswith(praefix) and n.endswith(".json.gz"))
    if not namen:
        return None
    with gzip.open(os.path.join(ordner, namen[-1]), "rt", encoding="utf-8") as f:
        return json.load(f)


def warteschlange(daten, token, stufen_gewuenscht, stand, fetcher=None, warte=time.sleep, log=print):
    """Je Stufe die noch offenen Symbole (nicht ok, nicht unbekannt). Die
    Symbollisten kommen aus der juengsten Inventur-Ablage; fehlt sie, werden
    sie frisch geholt (2 Calls)."""
    wurzel = os.path.join(daten, ORDNER)
    aktiv = _juengste_liste(wurzel, "us_aktiv_")
    delisted = _juengste_liste(wurzel, "us_delisted_")
    if aktiv is None or delisted is None:
        aktiv, _ = symbolliste(token, "US", False, fetcher, warte)
        delisted, _ = symbolliste(token, "US", True, fetcher, warte)
        tag = _utc_jetzt().date().isoformat()
        _gz_json(os.path.join(wurzel, "listen", f"us_aktiv_{tag}.json.gz"), aktiv)
        _gz_json(os.path.join(wurzel, "listen", f"us_delisted_{tag}.json.gz"), delisted)
    stufen = einordnen(aktiv, delisted)
    indizes = _juengste_liste(wurzel, "indx_")
    if indizes is None:
        st, indizes, _, _ = abruf_json("exchange-symbol-list/INDX", token, fetcher=fetcher, warte=warte)
        indizes = indizes if (st == 200 and isinstance(indizes, list)) else []
    stufen["index"] = [{"Code": str(e.get("Code") or "").strip(), "Name": e.get("Name")} for e in indizes if e.get("Code")]
    stufen["makro"] = [{"Code": f"{land}:{ind}", "Name": f"{land} {ind}"} for land in MAKRO_LAENDER for ind in MAKRO_INDIKATOREN]
    schlange = []
    for s in STUFEN_NAMEN:
        if s not in stufen_gewuenscht:
            continue
        offen = [e for e in stufen[s] if (stand.get(schluessel(s, e["Code"])) or {}).get("status") not in ("ok", "unbekannt", "leer")]
        log(f"  Stufe {s}: {len(stufen[s])} Symbole, davon offen {len(offen)}")
        schlange.extend((s, e) for e in offen)
    return schlange


def _hole_eins(stufe, e, token, fetcher, warte):
    """Ein Fundamentals- oder Makro-Abruf. Rueckgabe (status, daten, kopf, bytes)."""
    if stufe == "makro":
        land, ind = str(e["Code"]).split(":", 1)
        return abruf_json(f"macro-indicator/{land}", token, {"indicator": ind}, fetcher, warte)
    return abruf_json(f"fundamentals/{eodhd_symbol(stufe, e['Code'])}", token, {}, fetcher, warte)


def lauf_voll(daten, token, stufen=None, hoechstens=0, zeitgrenze_min=300, reserve=RESERVE_CALLS,
              fetcher=None, warte=time.sleep, log=print, runner=None, arbeit=None, lauf=None,
              ueber_mitternacht=True, jetzt=None):
    """Der Vollabzug. Holt Symbol fuer Symbol in der Vorrangfolge der Stufen,
    bis Budget oder Zeit erschoepft sind; legt je Stufe tar-Archive als
    Release-Anhaenge im Datenrepo ab und fuehrt stand.json fort."""
    start = time.monotonic()
    jetzt = jetzt or _utc_jetzt
    lauf = lauf or jetzt().strftime("%Y%m%d-%H%M")
    wurzel = os.path.join(daten, ORDNER)
    arbeit = arbeit or os.path.join(daten, "..", "eodhd_abzug")
    archive_ordner = os.path.join(arbeit, "_archive")
    stand_pfad = os.path.join(wurzel, "stand.json")
    stand = _json_lesen(stand_pfad, {})
    stufen = [s for s in (stufen or STUFEN_NAMEN) if s in STUFEN_NAMEN]
    bilanz = {"zeit": jetzt().isoformat(), "modus": "voll", "lauf": lauf, "stufen": stufen, "ok": 0,
              "unbekannt": 0, "leer": 0, "fehler": 0, "calls_geschaetzt": 0, "bytes_gz": 0,
              "hochgeladen": [], "abbruch": None, "release": f"eodhd-voll-{lauf}"}

    status, tarif = konto(token, fetcher)
    if status == 401:
        raise EodhdGesperrt("Schluessel ungueltig (HTTP 401 am User-Endpunkt)")
    budget = restbudget(tarif, reserve, jetzt().date().isoformat()) if tarif else 97000
    log(f"Konto: {json.dumps(tarif, ensure_ascii=False)}; Budget dieses Laufs {budget} Calls")

    schlange = warteschlange(daten, token, stufen, stand, fetcher, warte, log)
    if hoechstens:
        schlange = schlange[:hoechstens]
    log(f"Warteschlange: {len(schlange)} Abrufe in {len(stufen)} Stufe(n)")

    geholt_je_stufe = {}
    aktuelle_stufe = None

    def stufe_abschliessen(s):
        """Archiv bauen und hochladen; erst bei Erfolg gelten die Symbole als
        geholt (sonst blieben sie im Register als ok, ohne dass die Datei
        irgendwo laege)."""
        if not geholt_je_stufe.get(s):
            return
        archive = archive_bauen(arbeit, s, lauf, archive_ordner)
        pfade = [p for p, _ in archive]
        ok = release_hochladen(bilanz["release"], pfade,
                               f"EODHD-Vollabzug {lauf}",
                               "Ungefilterte Fundamentals je Symbol, eine gepackte JSON-Datei je Symbol, "
                               "je Stufe ein tar-Archiv. Register: eodhd_voll/stand.json im Dateibaum.",
                               runner=runner, log=log)
        for pfad, liste in archive:
            name = os.path.basename(pfad)
            for datei in liste:
                k = geholt_je_stufe[s].get(datei)
                if not k:
                    continue
                if ok:
                    stand[k]["release"] = bilanz["release"]
                    stand[k]["archiv"] = name
                else:
                    stand[k]["status"] = "nicht_gesichert"
        if ok:
            bilanz["hochgeladen"].extend(os.path.basename(p) for p in pfade)
            log(f"  Stufe {s}: {len(geholt_je_stufe[s])} Dateien in {len(pfade)} Archiv(en) hochgeladen.")
        else:
            bilanz["abbruch"] = bilanz["abbruch"] or f"Upload der Stufe {s} fehlgeschlagen"
            log(f"  Stufe {s}: Upload FEHLGESCHLAGEN; die Symbole bleiben offen.")
        for pfad, _ in archive:
            try:
                os.remove(pfad)
            except OSError:
                pass
        geholt_je_stufe[s] = {}
        _json_schreiben(stand_pfad, stand)

    for i, (s, e) in enumerate(schlange, 1):
        if aktuelle_stufe is not None and s != aktuelle_stufe:
            stufe_abschliessen(aktuelle_stufe)
        aktuelle_stufe = s
        calls = CALLS_MAKRO if s == "makro" else CALLS_FUNDAMENTALS
        # Zeitgrenze: davor bleibt Luft fuer Archiv und Upload.
        if (time.monotonic() - start) / 60 > zeitgrenze_min:
            bilanz["abbruch"] = f"Zeitgrenze {zeitgrenze_min} Minuten erreicht nach {i - 1} Abrufen"
            break
        if budget < calls:
            rest_s = sekunden_bis_mitternacht_gmt(jetzt())
            verbleibend_s = zeitgrenze_min * 60 - (time.monotonic() - start)
            if ueber_mitternacht and rest_s + 900 < verbleibend_s:
                log(f"  Tagesbudget erreicht nach {i - 1} Abrufen; warte {int(rest_s // 60) + 2} Minuten bis "
                    f"Mitternacht GMT und rechne mit dem neuen Budget weiter.")
                warte(rest_s + 90)
                st, tarif = konto(token, fetcher)
                budget = restbudget(tarif, reserve, jetzt().date().isoformat()) if tarif else 97000
                log(f"  Neues Budget {budget} Calls")
                if budget < calls:
                    bilanz["abbruch"] = "Budget auch nach Mitternacht nicht frei"
                    break
            else:
                bilanz["abbruch"] = f"Tagesbudget erreicht nach {i - 1} Abrufen"
                break
        try:
            st, d, kopf, groesse = _hole_eins(s, e, token, fetcher, warte)
        except EodhdGesperrt as ex:
            bilanz["abbruch"] = str(ex)
            break
        bilanz["calls_geschaetzt"] += calls
        budget -= calls
        k = schluessel(s, e["Code"])
        eintrag = {"stufe": s, "datum": jetzt().date().isoformat(), "name": e.get("Name"),
                   "typ": e.get("Type"), "boerse": e.get("Exchange"), "delisted": bool(e.get("delisted"))}
        if e.get("code_auch_aktiv"):
            eintrag["code_auch_aktiv"] = True
        if st == 200 and isinstance(d, (dict, list)) and d:
            datei = sicherer_dateiname(e["Code"] if s != "makro" else e["Code"].replace(":", "_")) + ".json.gz"
            gz = _gz_json(os.path.join(arbeit, s, datei), d)
            eintrag.update({"status": "ok", "bytes_gz": gz, "datei": datei})
            if isinstance(d, dict) and isinstance(d.get("General"), dict):
                g = d["General"]
                eintrag.update({"cik": g.get("CIK"), "sektor": g.get("Sector"), "branche": g.get("Industry"),
                                "gic_sektor": g.get("GicSector"), "gic_gruppe": g.get("GicGroup"),
                                "land": g.get("CountryName"), "waehrung": g.get("CurrencyCode"),
                                "delisted_laut_anbieter": g.get("IsDelisted"), "aktualisiert": g.get("UpdatedAt")})
            geholt_je_stufe.setdefault(s, {})[datei] = k
            bilanz["ok"] += 1
            bilanz["bytes_gz"] += gz
        elif st == 404:
            eintrag["status"] = "unbekannt"
            bilanz["unbekannt"] += 1
        elif st == 200:
            eintrag["status"] = "leer"
            bilanz["leer"] += 1
        else:
            eintrag.update({"status": "fehler", "http": st})
            bilanz["fehler"] += 1
        stand[k] = eintrag
        rest = (kopf or {}).get("X-RateLimit-Remaining") or (kopf or {}).get("x-ratelimit-remaining")
        if rest is not None:
            try:
                if int(rest) < 40:
                    warte(20)
            except ValueError:
                pass
        if i % 250 == 0:
            log(f"  ... {i} von {len(schlange)} ({s}), ok {bilanz['ok']}, unbekannt {bilanz['unbekannt']}, "
                f"leer {bilanz['leer']}, fehler {bilanz['fehler']}, {bilanz['bytes_gz'] / 1e6:.0f} MB, "
                f"Budget {budget}")
            _json_schreiben(stand_pfad, stand)
        if i % 500 == 0:
            st2, tarif2 = konto(token, fetcher)
            if tarif2:
                budget = restbudget(tarif2, reserve, jetzt().date().isoformat())
        warte(ABSTAND_S)
    if aktuelle_stufe is not None:
        stufe_abschliessen(aktuelle_stufe)

    _json_schreiben(stand_pfad, stand)
    bilanz["dauer_min"] = round((time.monotonic() - start) / 60, 1)
    bilanz["offen_danach"] = sum(1 for _, e in schlange if (stand.get(schluessel(_, e["Code"])) or {}).get("status") not in ("ok", "unbekannt", "leer"))
    with io.open(os.path.join(wurzel, "laeufe.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(bilanz, ensure_ascii=False) + "\n")
    text = (f"EODHD-Vollabzug {lauf}: ok {bilanz['ok']}, unbekannt {bilanz['unbekannt']}, leer {bilanz['leer']}, "
            f"fehler {bilanz['fehler']}, rund {bilanz['calls_geschaetzt']} Calls, {bilanz['bytes_gz'] / 1e6:.0f} MB gepackt, "
            f"{bilanz['dauer_min']} Minuten, Archive {len(bilanz['hochgeladen'])}"
            + (f"; Abbruch: {bilanz['abbruch']}" if bilanz["abbruch"] else "")
            + f"; danach noch offen in den gewaehlten Stufen: {bilanz['offen_danach']}")
    log(text)
    return bilanz, text


# ---------------------------------------------------------------------------
# Trends: der Konsens aller aktiven Aktien, 100 Symbole je Anfrage
# ---------------------------------------------------------------------------

def lauf_trends(daten, token, fetcher=None, warte=time.sleep, log=print, je_anfrage=100, hoechstens=0, jetzt=None):
    """Kalender-Trends (Konsens je Quartal und Jahr samt Revisionen) fuer alle
    aktiven Boersen-Aktien, in Gruppen; laut Doku 1 Call je Anfrage."""
    jetzt = jetzt or _utc_jetzt
    wurzel = os.path.join(daten, ORDNER)
    aktiv = _juengste_liste(wurzel, "us_aktiv_")
    if aktiv is None:
        aktiv, _ = symbolliste(token, "US", False, fetcher, warte)
    stufen = einordnen(aktiv, [])
    codes = [e["Code"] for e in stufen["stock_boerse"]] + [e["Code"] for e in stufen["stock_otc"]]
    if hoechstens:
        codes = codes[:hoechstens]
    kennung = jetzt().strftime("%Y-%m-%d_%H%MZ")
    pfad = os.path.join(wurzel, "trends", f"{kennung}.jsonl.gz")
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    zeilen, anfragen, fehler = 0, 0, 0
    with gzip.open(pfad, "wt", encoding="utf-8") as f:
        for i in range(0, len(codes), je_anfrage):
            gruppe = codes[i:i + je_anfrage]
            try:
                st, d, _, _ = abruf_json("calendar/trends", token, {"symbols": ",".join(f"{c}.US" for c in gruppe)}, fetcher, warte)
            except EodhdGesperrt as ex:
                log(f"  Abbruch: {ex}")
                break
            anfragen += 1
            if st == 200 and d:
                f.write(json.dumps({"zeit": jetzt().isoformat(), "symbole": gruppe, "antwort": d}, ensure_ascii=False) + "\n")
                zeilen += 1
            else:
                fehler += 1
            warte(ABSTAND_S)
    bilanz = {"zeit": jetzt().isoformat(), "modus": "trends", "symbole": len(codes), "anfragen": anfragen,
              "gruppen_geschrieben": zeilen, "fehler": fehler, "datei": os.path.relpath(pfad, daten).replace(os.sep, "/")}
    with io.open(os.path.join(wurzel, "laeufe.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(bilanz, ensure_ascii=False) + "\n")
    log(json.dumps(bilanz, ensure_ascii=False))
    return bilanz


# ---------------------------------------------------------------------------
# Selbsttest (ohne Netz)
# ---------------------------------------------------------------------------

def _liste_probe():
    aktiv = [{"Code": "AAPL", "Name": "Apple", "Exchange": "NASDAQ", "Type": "Common Stock", "Isin": "US0378331005"},
             {"Code": "JPM", "Name": "JPMorgan", "Exchange": "NYSE", "Type": "Common Stock"},
             {"Code": "TCEHY", "Name": "Tencent ADR", "Exchange": "PINK", "Type": "Common Stock"},
             {"Code": "SPY", "Name": "SPDR S&P 500", "Exchange": "NYSE ARCA", "Type": "ETF"},
             {"Code": "VFIAX", "Name": "Vanguard 500", "Exchange": "NMFQS", "Type": "FUND"},
             {"Code": "BAC-PL", "Name": "BofA Preferred", "Exchange": "NYSE", "Type": "Preferred Stock"},
             {"Code": "CON", "Name": "Geraetename", "Exchange": "NYSE", "Type": "Common Stock"}]
    delisted = [{"Code": "ATVI", "Name": "Activision", "Exchange": "NASDAQ", "Type": "Common Stock"},
                {"Code": "AAPL", "Name": "Alter Code", "Exchange": "NYSE", "Type": "Common Stock"},
                {"Code": "XYZ", "Name": "Alter Fonds", "Exchange": "NMFQS", "Type": "FUND"}]
    return aktiv, delisted


def selbsttest() -> int:
    import tempfile
    fehler = 0

    def p(name, ok, extra=""):
        nonlocal fehler
        print(f"  {'ok  ' if ok else 'FEHL'} {name}{(' ' + str(extra)) if extra else ''}")
        if not ok:
            fehler += 1

    print("EODHD-Vollabzug, Selbsttest (ohne Netz)")
    aktiv, delisted = _liste_probe()
    st = einordnen(aktiv, delisted)
    p("Einordnung: Boersenaktien, OTC, ETF, Fonds, Sonstige, delistete Aktien und delisteter Rest",
      [e["Code"] for e in st["stock_boerse"]] == ["AAPL", "CON", "JPM"] and [e["Code"] for e in st["stock_otc"]] == ["TCEHY"]
      and [e["Code"] for e in st["etf"]] == ["SPY"] and [e["Code"] for e in st["fund"]] == ["VFIAX"]
      and [e["Code"] for e in st["sonstige"]] == ["BAC-PL"] and [e["Code"] for e in st["delisted_stock"]] == ["AAPL", "ATVI"]
      and [e["Code"] for e in st["delisted_rest"]] == ["XYZ"], {k: len(v) for k, v in st.items()})
    p("Delisteter Code, der auch aktiv vorkommt, ist vermerkt",
      next(e for e in st["delisted_stock"] if e["Code"] == "AAPL")["code_auch_aktiv"] is True
      and next(e for e in st["delisted_stock"] if e["Code"] == "ATVI")["code_auch_aktiv"] is False)
    p("Registerschluessel haelt Stufen auseinander", schluessel("delisted_stock", "aapl") != schluessel("stock_boerse", "AAPL"))
    p("Symbolform: Aktie .US, Index .INDX", eodhd_symbol("stock_otc", "tcehy") == "TCEHY.US" and eodhd_symbol("index", "GSPC") == "GSPC.INDX")
    p("Dateinamen: reservierte Namen und Sonderzeichen abgesichert",
      sicherer_dateiname("CON") == "CON_" and sicherer_dateiname("BRK-B") == "BRK-B" and sicherer_dateiname("A/B") == "A_B"
      and sicherer_dateiname("USA:gdp_current_usd".replace(":", "_")) == "USA_GDP_CURRENT_USD")
    heute = "2026-09-13"
    p("Restbudget: heutiger Zaehler wird abgezogen, gestriger nicht",
      restbudget({"dailyRateLimit": 100000, "apiRequests": 40000, "apiRequestsDate": heute}, 3000, heute) == 57000
      and restbudget({"dailyRateLimit": 100000, "apiRequests": 40000, "apiRequestsDate": "2026-09-12", "extraLimit": 500}, 3000, heute) == 97500
      and restbudget({}, 3000, heute) == 0)
    p("Sekunden bis Mitternacht GMT",
      sekunden_bis_mitternacht_gmt(dt.datetime(2026, 9, 12, 23, 30, tzinfo=dt.timezone.utc)) == 1800)

    with tempfile.TemporaryDirectory() as tmp:
        daten = os.path.join(tmp, "daten")
        os.makedirs(os.path.join(daten, ORDNER, "listen"), exist_ok=True)
        _gz_json(os.path.join(daten, ORDNER, "listen", "us_aktiv_2026-09-12.json.gz"), aktiv)
        _gz_json(os.path.join(daten, ORDNER, "listen", "us_delisted_2026-09-12.json.gz"), delisted)
        _gz_json(os.path.join(daten, ORDNER, "listen", "indx_2026-09-12.json.gz"), [{"Code": "GSPC", "Name": "S&P 500"}])
        aufrufe = []

        def fetcher(kennung):
            aufrufe.append(kennung)
            if kennung.startswith("user?"):
                return 200, json.dumps({"name": "geheim", "email": "geheim@example.org", "subscriptionType": "Fundamentals",
                                        "dailyRateLimit": 100000, "apiRequests": 10, "apiRequestsDate": _utc_jetzt().date().isoformat()}), {}
            if "ATVI.US" in kennung:
                return 404, "not found", {}
            if "TCEHY.US" in kennung and sum(1 for a in aufrufe if "TCEHY.US" in a) == 1:
                return 429, "Too Many Requests", {}
            if "JPM.US" in kennung:
                return 200, "", {}
            if "macro-indicator" in kennung:
                return 200, json.dumps([{"Date": "2024-12-31", "Value": 1.0}]), {}
            return 200, json.dumps({"General": {"Code": kennung.split("/")[1].split("?")[0].split(".")[0], "CIK": "1",
                                                "Sector": "Technology", "Industry": "Hardware", "IsDelisted": False}}), {"X-RateLimit-Remaining": "900"}

        befehle = []

        def runner(args):
            befehle.append(args)
            class R:
                returncode = 0 if args[:3] != ["gh", "release", "view"] else 1
                stderr = ""
            return R()

        schlaf = []
        b, text = lauf_voll(daten, "x", stufen=["delisted_stock", "stock_boerse", "stock_otc", "index"], fetcher=fetcher,
                            warte=schlaf.append, log=lambda *_: None, runner=runner, lauf="20260912-2000",
                            arbeit=os.path.join(tmp, "arbeit"))
        stand = _json_lesen(os.path.join(daten, ORDNER, "stand.json"), {})
        p("Lauf: delistete Aktien zuerst, 404 wird unbekannt, leere Antwort wird leer, 429 einmal wiederholt",
          b["ok"] == 5 and b["unbekannt"] == 1 and b["leer"] == 1 and b["fehler"] == 0 and 20 in schlaf
          and aufrufe[1].startswith("fundamentals/AAPL.US") and aufrufe[2].startswith("fundamentals/ATVI.US"), b)
        p("Register: Status, Datei, Release und Archiv je Symbol; Sektor und Branche aus General",
          stand[schluessel("stock_boerse", "AAPL")]["status"] == "ok"
          and stand[schluessel("stock_boerse", "AAPL")]["release"] == "eodhd-voll-20260912-2000"
          and stand[schluessel("stock_boerse", "AAPL")]["archiv"] == "eodhd_stock_boerse_20260912-2000.tar"
          and stand[schluessel("stock_boerse", "AAPL")]["sektor"] == "Technology"
          and stand[schluessel("delisted_stock", "ATVI")]["status"] == "unbekannt"
          and stand[schluessel("stock_boerse", "JPM")]["status"] == "leer"
          and stand[schluessel("delisted_stock", "AAPL")]["code_auch_aktiv"] is True
          and stand[schluessel("index", "GSPC")]["status"] == "ok", {k: v.get("status") for k, v in stand.items()})
        p("Release: einmal angelegt, je Stufe ein Upload",
          sum(1 for a in befehle if a[:3] == ["gh", "release", "create"]) == 1
          and sum(1 for a in befehle if a[:3] == ["gh", "release", "upload"]) == 4
          and all("--clobber" in a for a in befehle if a[:3] == ["gh", "release", "upload"]), [a[:3] for a in befehle])
        p("Archiv-Dateien sind nach dem Upload weggeraeumt, Arbeitsdateien liegen je Stufe",
          not os.listdir(os.path.join(tmp, "arbeit", "_archive"))
          and sorted(os.listdir(os.path.join(tmp, "arbeit", "stock_boerse"))) == ["AAPL.json.gz", "CON_.json.gz"])
        b2, _ = lauf_voll(daten, "x", stufen=["delisted_stock", "stock_boerse", "stock_otc", "index"], fetcher=fetcher,
                          warte=schlaf.append, log=lambda *_: None, runner=runner, lauf="20260913-0000",
                          arbeit=os.path.join(tmp, "arbeit2"))
        p("Zweiter Lauf holt nichts doppelt", b2["ok"] == 0 and b2["calls_geschaetzt"] == 0, b2)
        b3, _ = lauf_voll(daten, "x", stufen=["etf", "fund"], fetcher=fetcher, warte=schlaf.append, log=lambda *_: None,
                          runner=runner, lauf="20260913-0001", arbeit=os.path.join(tmp, "arbeit3"), reserve=99975,
                          ueber_mitternacht=False)
        p("Budget begrenzt den Lauf und nennt den Abbruch", b3["ok"] == 1 and "Tagesbudget" in (b3["abbruch"] or ""), b3["abbruch"])

        def runner_kaputt(args):
            class R:
                returncode = 1
                stderr = "kaputt"
            return R()
        b4, _ = lauf_voll(daten, "x", stufen=["fund"], fetcher=fetcher, warte=schlaf.append, log=lambda *_: None,
                          runner=runner_kaputt, lauf="20260913-0002", arbeit=os.path.join(tmp, "arbeit4"))
        stand = _json_lesen(os.path.join(daten, ORDNER, "stand.json"), {})
        p("Scheitert der Upload, bleiben die Symbole offen (nicht_gesichert) und der Abbruch ist vermerkt",
          stand[schluessel("fund", "VFIAX")]["status"] == "nicht_gesichert" and "Upload" in (b4["abbruch"] or ""))
        b5, _ = lauf_voll(daten, "x", stufen=["fund"], fetcher=fetcher, warte=schlaf.append, log=lambda *_: None,
                          runner=runner, lauf="20260913-0003", arbeit=os.path.join(tmp, "arbeit5"))
        p("Ein nicht gesichertes Symbol wird im naechsten Lauf erneut geholt", b5["ok"] == 1)

        def gesperrt(kennung):
            if kennung.startswith("user?"):
                return 200, json.dumps({"dailyRateLimit": 100000, "apiRequests": 0}), {}
            return 403, "Forbidden", {}
        b6, _ = lauf_voll(daten, "x", stufen=["sonstige"], fetcher=gesperrt, warte=schlaf.append, log=lambda *_: None,
                          runner=runner, lauf="20260913-0004", arbeit=os.path.join(tmp, "arbeit6"))
        p("403 bricht den Lauf ab", "403" in (b6["abbruch"] or "") and b6["ok"] == 0)

        archive = archive_bauen(os.path.join(tmp, "arbeit"), "stock_boerse", "x", os.path.join(tmp, "za"), teile_bytes=1)
        p("Archive werden bei der Groessengrenze geteilt", len(archive) == 2 and archive[0][0].endswith("_teil1.tar"))

        bt = lauf_trends(daten, "x", fetcher=lambda k: (200, json.dumps({"AAPL.US": {}}), {}), warte=schlaf.append,
                         log=lambda *_: None, je_anfrage=2)
        p("Trends: Boersen- und OTC-Aktien in Gruppen, eine Datei je Lauf",
          bt["symbole"] == 4 and bt["anfragen"] == 2 and bt["gruppen_geschrieben"] == 2)

        def fetcher_inv(kennung):
            if kennung.startswith("user?"):
                return 200, json.dumps({"dailyRateLimit": 100000, "apiRequests": 5, "apiRequestsDate": _utc_jetzt().date().isoformat()}), {}
            if kennung.startswith("exchange-symbol-list/US?delisted=1"):
                return 200, json.dumps(delisted), {}
            if kennung.startswith("exchange-symbol-list/US"):
                return 200, json.dumps(aktiv), {}
            if kennung.startswith("exchange-symbol-list/INDX"):
                return 200, json.dumps([{"Code": "GSPC"}]), {}
            if kennung.startswith("exchanges-list"):
                return 200, json.dumps([{"Code": "US"}]), {}
            if kennung.startswith("economic-events"):
                return 200, json.dumps([{"type": "GDP", "date": "2020-01-01"}]), {}
            if kennung.startswith("symbol-change-history"):
                return 404, "", {}
            return 200, json.dumps({"General": {"Code": "X"}, "Financials": {"a": 1}}), {}
        inv = inventur(daten, "x", fetcher=fetcher_inv, warte=schlaf.append, log=lambda *_: None, heute=dt.date(2026, 9, 12))
        p("Inventur zaehlt Listen, Stufen und Proben und schreibt die Schaetzung",
          inv["listen"]["us_aktiv"] == 7 and inv["stufen"]["delisted_stock"] == 2 and inv["proben"]["aapl"]["status"] == 200
          and inv["schaetzung_gesamt"]["calls"] > 0 and os.path.exists(os.path.join(daten, ORDNER, "inventur.md")))
        p("Inventur legt Listen, Proben, Kalender und Ereignisse ab",
          os.path.exists(os.path.join(daten, ORDNER, "listen", "us_aktiv_2026-09-12.json.gz"))
          and os.path.exists(os.path.join(daten, ORDNER, "kalender", "events_2020.json.gz"))
          and any(n.startswith("earnings_2016_2026") for n in os.listdir(os.path.join(daten, ORDNER, "kalender"))))
        bericht = inventur_bericht(inv)
        p("Bericht ohne Gedankenstrich und ohne senkrechten Strich", "–" not in bericht and "|" not in bericht)

    print("\n" + ("Alles bestanden." if fehler == 0 else f"{fehler} Fehler."))
    return fehler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--daten", default="")
    ap.add_argument("--modus", default="inventur", choices=["inventur", "voll", "trends"])
    ap.add_argument("--stufen", default="", help="voll: Stufen mit Beistrich, leer = alle in Vorrangfolge")
    ap.add_argument("--hoechstens", type=int, default=0)
    ap.add_argument("--zeitgrenze-min", type=int, default=300)
    ap.add_argument("--reserve", type=int, default=RESERVE_CALLS)
    ap.add_argument("--selbsttest", action="store_true")
    a = ap.parse_args()
    if a.selbsttest:
        sys.exit(1 if selbsttest() else 0)
    token = (os.environ.get("EODHD_API_KEY") or "").strip()
    if not token:
        print("EODHD_API_KEY fehlt (Secret); nichts zu tun.")
        sys.exit(0)
    if not a.daten:
        print("--daten fehlt.")
        sys.exit(2)
    try:
        if a.modus == "inventur":
            b = inventur(a.daten, token)
            push("EODHD-Inventur fertig", inventur_bericht(b))
            sys.exit(0)
        if a.modus == "trends":
            lauf_trends(a.daten, token, hoechstens=a.hoechstens)
            sys.exit(0)
        stufen = [s.strip() for s in a.stufen.split(",") if s.strip()] or None
        b, text = lauf_voll(a.daten, token, stufen=stufen, hoechstens=a.hoechstens,
                            zeitgrenze_min=a.zeitgrenze_min, reserve=a.reserve)
        push("EODHD-Vollabzug: Lauf beendet", text)
        sys.exit(1 if (b["abbruch"] and b["ok"] == 0 and "Tagesbudget" not in b["abbruch"]) else 0)
    except EodhdGesperrt as e:
        print(f"ABBRUCH: {e}")
        push("EODHD-Vollabzug abgebrochen", str(e), prio="high")
        sys.exit(1)


if __name__ == "__main__":
    main()
