#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Messung der KI-Vorabwerte (Gerhards F15): Liest ein Sprachmodell die
Ergebniszahlen aus echten 8-K-Pressemitteilungen richtig?

WARUM: Die maschinenlesbaren Zahlen (XBRL) kommen erst mit dem 10-Q, bis zu
45 Tage nach Quartalsende; die Pressemitteilung (8-K, Exhibit 99.1) kommt am
Meldetag, aber als freier Text. Gerhard will am Meldetag den Vergleich mit
dem eingefrorenen Konsens. Ein Modell soll deshalb NUR lesen: Umsatz,
Nettogewinn, verwaessertes Ergebnis je Aktie, Periodenende, GAAP oder nicht,
je Wert die Textstelle als Beleg. Bevor irgendein Dienst gewaehlt wird,
misst dieser Lauf an Faellen, deren amtliche Werte inzwischen im
companyfacts-Archiv stehen, wie oft die gelesene Zahl mit der amtlichen
uebereinstimmt, je Modell, und legt JEDE Antwort als Datei ab (Regel:
Messreihen vollstaendig gegenlesen).

FAELLE: Je Firma das juengste Ergebnis-8-K (Item 2.02), dessen Quartal in
companyfacts amtlich belegt ist (Erstfassung, wie ueberall im Tool). Der
Text ist Exhibit 99.1 als Klartext, auf TEXT_ZEICHEN Zeichen gekuerzt (der
Zahlenteil steht vorn).

DIENST: Mistral (alle Text-Chat-Modelle der Tagesliste, Aliasgruppen nur
einmal), JSON-Formzwang, Temperatur 0, Bremse je Modell aus den
Kopfzeilen der Antworten. Nur im Actions-Lauf (Secrets SEC_USER_AGENT und
MISTRAL_API_KEY).

Aufruf:
  python messung_8k.py --selbsttest
  python messung_8k.py --lauf [--hoechstens 30] [--modelle a,b] [--ausgabe messung_8k]
"""

import argparse
import concurrent.futures
import datetime as dt
import io
import json
import os
import re
import sys
import threading
import time

AUSGABE = "messung_8k"
TEXT_ZEICHEN = 30000
KOPF_ZEICHEN = 9000
MISTRAL_KEY = os.environ.get("MISTRAL_API_KEY", "").strip()

# Gemischt: Grosskonzerne, Bank, Versicherer, Immobilien, Mittelstand,
# Small Caps; dazu die Wochenlisten (siehe lauf()).
TICKER = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "JPM", "PGR", "O",
          "XOM", "KO", "PEP", "MCD", "NKE", "HD", "COST", "UNH", "PFE", "CAT",
          "DE", "INTC", "AMD", "ADBE", "CRM", "NFLX", "ANF", "IESC", "KRYS",
          "TSLA", "SBUX"]

AUFTRAG = (
    "You are a meticulous financial data extractor. You receive the text of an "
    "earnings press release filed with the SEC (Form 8-K, Exhibit 99.1); passages "
    "may be omitted and marked with [...]. Extract ONLY figures for the MOST RECENT "
    "fiscal QUARTER, i.e. the three-month period the release reports on. Never use "
    "year-to-date, six-month, nine-month or full-year columns, never the prior-year "
    "quarter, and if the release also reports a single month (some insurers do), "
    "use the QUARTER column, not the month. Fields: "
    "periodenende = last day of that quarter as YYYY-MM-DD; "
    "umsatz = TOTAL revenues, the top line of the income statement as the company "
    "totals it, INCLUDING components such as membership fees, financial services "
    "revenues, interest income or other income when the company total revenue "
    "line includes them (prefer a line named total revenues, total net revenues, "
    "net sales and revenues, revenues and other income over a partial line such "
    "as net sales or product revenue when both exist); in absolute US dollars "
    "(a value stated as $94,036 million becomes 94036000000; thousands become "
    "units); "
    "nettogewinn = GAAP net income (net earnings, profit) attributable to the "
    "company or its common shareholders for the quarter, in absolute US dollars, "
    "losses negative; NEVER operating income, operating profit, earnings from "
    "operations, segment profit, EBITDA or adjusted figures; if the GAAP quarterly "
    "net income is not stated, use null; "
    "eps_verwaessert = GAAP diluted earnings per share for the quarter in dollars, "
    "losses negative; NOT adjusted or non-GAAP EPS unless no GAAP figure exists, "
    "in which case set gaap to false; "
    "gaap = true only if the three figures are GAAP (reported) figures; "
    "beleg_umsatz, beleg_nettogewinn, beleg_eps = the exact text fragment (at most "
    "120 characters) from which each value was taken. Use null for anything the "
    "text does not state. Answer with JSON only, no prose."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "periodenende": {"type": ["string", "null"]},
        "umsatz": {"type": ["number", "null"]},
        "nettogewinn": {"type": ["number", "null"]},
        "eps_verwaessert": {"type": ["number", "null"]},
        "gaap": {"type": "boolean"},
        "beleg_umsatz": {"type": ["string", "null"]},
        "beleg_nettogewinn": {"type": ["string", "null"]},
        "beleg_eps": {"type": ["string", "null"]},
    },
    "required": ["periodenende", "umsatz", "nettogewinn", "eps_verwaessert", "gaap",
                 "beleg_umsatz", "beleg_nettogewinn", "beleg_eps"],
    "additionalProperties": False,
}

# USD je 1 Mio Tokens (mistral.ai/pricing/api, Stand 02.09.2026), nur informativ.
PREISE = {"mistral-small": (0.15, 0.6), "mistral-medium": (1.5, 7.5), "mistral-large": (0.5, 1.5),
          "ministral-3b": (0.1, 0.1), "ministral-8b": (0.15, 0.15), "ministral-14b": (0.2, 0.2),
          "codestral": (0.3, 0.9), "voxtral-small": (0.1, 0.4), "zai-glm-5-2": (1.4, 4.4),
          "labs-leanstral": (0, 0), "magistral-small": (0.15, 0.6), "magistral-medium": (1.5, 7.5),
          "devstral": (0.3, 0.9), "open-mistral-nemo": (0.15, 0.15)}


def preis(modell):
    m = (modell or "").lower()
    best = None
    for k in PREISE:
        if m.startswith(k) and (best is None or len(k) > len(best)):
            best = k
    return PREISE.get(best)


# ---------------------------------------------------------------------------
# SEC: Ergebnis-8-Ks und Exhibit 99.1 als Klartext
# ---------------------------------------------------------------------------

def submissions(cik):
    import fundament_lauf as fl
    return json.loads(fl.hole(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))


def ergebnis_8ks(sub):
    """[(filingDate, reportDate, accession, primaryDocument)] der 8-Ks mit
    Item 2.02 (Results of Operations), juengste zuerst."""
    r = sub.get("filings", {}).get("recent", {})
    raus = []
    for form, fd, rd, acc, prim, items in zip(r.get("form", []), r.get("filingDate", []),
                                             r.get("reportDate", []), r.get("accessionNumber", []),
                                             r.get("primaryDocument", []), r.get("items", [])):
        if form == "8-K" and "2.02" in (items or ""):
            raus.append((fd, rd or fd, acc, prim))
    raus.sort(reverse=True)
    return raus


def html_zu_text(html_roh):
    """Klartext samt Tabellenzeilen (Zellen mit ' | ' getrennt), damit ein
    Modell Spaltenkoepfe wie 'Three Months Ended' den Zahlen zuordnen kann."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html_roh, "lxml")
    for t in soup(["script", "style"]):
        t.decompose()
    for tr in soup.find_all("tr"):
        zellen = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        zellen = [z for z in zellen if z]
        tr.replace_with(soup.new_string("\n" + " | ".join(zellen) + "\n") if zellen else "\n")
    text = soup.get_text("\n")
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


SCHLUESSEL = re.compile(r"net income|net earnings|net \(loss\)|net loss|profit attributable|attributable to|"
                        r"diluted|total revenue|total net revenue|net sales|revenues|three months ended|"
                        r"quarter ended|per share", re.I)


def text_kuerzen(text, limit=TEXT_ZEICHEN, kopf=KOPF_ZEICHEN, davor=300, danach=900):
    """Der Anfang der Mitteilung (Ueberschriften, Kernaussagen) plus Fenster um
    jede Zeile mit Kennzahl-Stichwoertern, damit die Ergebnistabellen auch
    dann mitkommen, wenn sie hinter langen Erlaeuterungen stehen (UNH, CAT
    beim ersten Lauf: die GAAP-Tabelle lag jenseits von 24.000 Zeichen).
    Ausgelassenes ist mit [...] markiert."""
    if len(text) <= limit:
        return text
    fenster = [(0, kopf)]
    for m in SCHLUESSEL.finditer(text, kopf):
        fenster.append((max(kopf, m.start() - davor), min(len(text), m.end() + danach)))
    fenster.sort()
    zusammen = []
    for a, b in fenster:
        if zusammen and a <= zusammen[-1][1]:
            zusammen[-1] = (zusammen[-1][0], max(zusammen[-1][1], b))
        else:
            zusammen.append((a, b))
    teile, laenge = [], 0
    for a, b in zusammen:
        stueck = text[a:b]
        if laenge + len(stueck) > limit:
            stueck = stueck[:max(0, limit - laenge)]
        if not stueck:
            break
        teile.append(stueck)
        laenge += len(stueck)
        if laenge >= limit:
            break
    return "\n[...]\n".join(teile)


def exhibit_text(cik, accession):
    import fundament_lauf as fl
    ordner = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}"
    index = json.loads(fl.hole(ordner + "/index.json"))
    dateien = [d for d in index.get("directory", {}).get("item", [])
               if d.get("name", "").lower().endswith((".htm", ".html"))]
    kandidaten = [d for d in dateien if re.search(r"ex[-_]?99", d["name"].lower())]
    if not kandidaten:
        kandidaten = [d for d in dateien if not d["name"].lower().startswith("0")]
    if not kandidaten:
        return None, None
    kandidaten.sort(key=lambda d: int(d.get("size") or 0), reverse=True)
    name = kandidaten[0]["name"]
    roh = fl.hole(ordner + "/" + name)
    try:
        html_roh = roh.decode("utf-8")
    except UnicodeDecodeError:
        html_roh = roh.decode("latin-1")
    return name, html_zu_text(html_roh)


def amtlich(zeilen, ende):
    """Erstfassung der drei Kennzahlen zum Quartalsende, dazu die Werte
    ANDERER Periodentypen (Neunmonats-, Jahreswert) am selben Ende, an
    denen sich die Fehlerklasse 'falsche Periode' erkennen laesst."""
    werte, andere = {}, {}
    for z in zeilen:
        if z["end"] != ende or z["kennzahl"] not in ("umsatz", "nettogewinn", "eps_verwaessert"):
            continue
        if z["typ"] == "Q":
            werte[z["kennzahl"]] = z["wert_erst"]
        else:
            andere.setdefault(z["kennzahl"], []).append(z["wert_erst"])
    return werte, andere


def periode_zum_8k(quartalsenden, report_datum, hoechstens_tage=75):
    """Das juengste amtlich belegte Quartalsende vor dem Meldedatum."""
    rd = dt.date.fromisoformat(report_datum)
    passend = [e for e in quartalsenden
               if dt.date.fromisoformat(e) < rd
               and (rd - dt.date.fromisoformat(e)).days <= hoechstens_tage]
    return max(passend) if passend else None


def fall_finden(ticker, cik, log=print):
    import fundament_lauf as fl
    import fundament_normalisieren as fn
    firma = fl.companyfacts(cik)
    _, zeilen = fn.normalisiere(firma)
    quartalsenden = sorted({z["end"] for z in zeilen
                            if z["typ"] == "Q" and z["kennzahl"] in ("umsatz", "nettogewinn")})
    for fd, rd, acc, prim in ergebnis_8ks(submissions(cik))[:8]:
        ende = periode_zum_8k(quartalsenden, rd)
        if not ende:
            continue
        werte, andere = amtlich(zeilen, ende)
        if "umsatz" not in werte and "nettogewinn" not in werte:
            continue
        name, text = exhibit_text(cik, acc)
        if not text or len(text) < 1500:
            log(f"  {ticker}: Exhibit zu {acc} unbrauchbar ({name}), naechstes 8-K")
            continue
        return {"ticker": ticker, "cik": cik, "8k_datum": fd, "melde_datum": rd,
                "accession": acc, "exhibit": name, "periodenende": ende,
                "amtlich": werte, "andere_perioden": andere,
                "text": text_kuerzen(text), "text_zeichen_voll": len(text)}
    return None


# ---------------------------------------------------------------------------
# Mistral
# ---------------------------------------------------------------------------

def _anfrage(url, koerper=None, methode="POST", timeout=180, key=None):
    """HTTP-Anfrage an einen OpenAI-kompatiblen Dienst; key = anderer Schluessel als Mistral
    (Groq-Websuche der KI-Abfrage). Groqs Cloudflare weist urllib ohne User-Agent ab."""
    import urllib.request
    import urllib.error
    daten = json.dumps(koerper).encode("utf-8") if koerper is not None else None
    req = urllib.request.Request(url, data=daten, method=methode, headers={
        "Authorization": "Bearer " + (key if key is not None else MISTRAL_KEY), "Content-Type": "application/json",
        "Accept": "application/json", "User-Agent": "heliot/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8", "replace")


def modelle_laden():
    """Alle Text-Chat-Modelle der Tagesliste, je Aliasgruppe eines (der
    Name mit Fassungsangabe), ohne Einbettung, OCR, Moderation, Sprachausgabe,
    Transkription und Echtzeit."""
    status, _, roh = _anfrage("https://api.mistral.ai/v1/models", methode="GET")
    if status != 200:
        raise RuntimeError(f"Modellliste: {status} {roh[:200]}")
    return modelle_filtern(json.loads(roh).get("data", []))


def modelle_filtern(liste):
    raus, gesehen = [], set()
    for m in liste:
        kennung = m.get("id", "")
        caps = m.get("capabilities", {}) or {}
        if not caps.get("completion_chat", True):
            continue
        if re.search(r"embed|ocr|moderation|tts|transcribe|realtime|saba|pixtral-12b-2409|^labs-", kennung):
            continue
        gruppe = {kennung} | set(m.get("aliases", []) or [])
        if gruppe & gesehen:
            continue
        gesehen |= gruppe
        mit_fassung = sorted([k for k in gruppe if re.search(r"\d{4}$", k)])
        raus.append(mit_fassung[0] if mit_fassung else kennung)
    return sorted(raus)


class Bremse:
    """Mindestabstand je Modell aus x-ratelimit-limit-req-minute."""

    def __init__(self):
        self.lock = threading.Lock()
        self.zuletzt = {}
        self.abstand = {}

    def warten(self, modell):
        with self.lock:
            ab = self.abstand.get(modell, 6.5)
            rest = self.zuletzt.get(modell, 0) + ab - time.monotonic()
        if rest > 0:
            time.sleep(rest)

    def merken(self, modell, kopf):
        try:
            rpm = float(kopf.get("x-ratelimit-limit-req-minute") or 0)
        except ValueError:
            rpm = 0
        try:
            tpm = float(kopf.get("x-ratelimit-limit-tokens-minute") or 0)
            kosten = float(kopf.get("x-ratelimit-tokens-query-cost") or 0)
        except ValueError:
            tpm = kosten = 0
        with self.lock:
            self.zuletzt[modell] = time.monotonic()
            ab = 0.0
            if rpm > 0:
                ab = 60.0 / rpm * 1.3 + 0.5
            if tpm > 0 and kosten > 0:
                ab = max(ab, kosten / tpm * 60.0 * 1.2)
            if ab > 0:
                self.abstand[modell] = ab


def mistral_frage(modell, text, bremse):
    """Rueckgabe: {roh, geparst, usage, dauer_s, status, hinweise}."""
    hinweise = []
    schema_aktiv = True
    for versuch in range(8):
        koerper = {
            "model": modell, "temperature": 0, "max_tokens": 700,
            "messages": [{"role": "system", "content": AUFTRAG},
                         {"role": "user", "content": text}],
        }
        if schema_aktiv:
            koerper["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "ergebnis", "strict": True, "schema": SCHEMA}}
        else:
            koerper["response_format"] = {"type": "json_object"}
        bremse.warten(modell)
        t0 = time.time()
        status, kopf, roh = _anfrage("https://api.mistral.ai/v1/chat/completions", koerper)
        dauer = time.time() - t0
        bremse.merken(modell, kopf)
        if status == 429 or status >= 500:
            hinweise.append(f"{status} beim Versuch {versuch + 1}")
            time.sleep(20 if status == 429 else 10)
            continue
        if status in (400, 422) and schema_aktiv:
            hinweise.append(f"{status} mit Schema, weiter mit json_object")
            schema_aktiv = False
            continue
        if status != 200:
            return {"roh": roh[:800], "geparst": None, "usage": None, "dauer_s": round(dauer, 1),
                    "status": status, "hinweise": hinweise + [f"HTTP {status}"]}
        antwort = json.loads(roh)
        inhalt = antwort["choices"][0]["message"].get("content") or ""
        geparst = None
        try:
            geparst = json.loads(inhalt)
        except Exception:
            m = re.search(r"\{.*\}", inhalt, re.S)
            if m:
                try:
                    geparst = json.loads(m.group(0))
                except Exception:
                    geparst = None
        return {"roh": inhalt, "geparst": geparst, "usage": antwort.get("usage"),
                "dauer_s": round(dauer, 1), "status": status, "hinweise": hinweise,
                "modell_laut_antwort": antwort.get("model")}
    return {"roh": "", "geparst": None, "usage": None, "dauer_s": 0, "status": 0,
            "hinweise": hinweise + ["aufgegeben"]}


# ---------------------------------------------------------------------------
# Vergleich
# ---------------------------------------------------------------------------

def _nah(a, b, rel=0.005, abs_=100000.0):
    return abs(a - b) <= max(rel * abs(b), abs_)


def vergleiche(soll, ist, andere=None, eps=False):
    """'richtig', 'fehlt', 'einheit' (Faktor 1000 oder 1 Mio daneben),
    'periode' (Neunmonats- oder Jahreswert getroffen), 'vorzeichen',
    'abweichend'; dazu die Abweichung in Prozent."""
    if soll is None:
        return "kein_sollwert", None
    if ist is None:
        return "fehlt", None
    try:
        ist = float(ist)
        soll = float(soll)
    except (TypeError, ValueError):
        return "unlesbar", None
    if eps:
        if abs(ist - soll) <= 0.015:
            return "richtig", 0.0
        if soll != 0 and any(abs(ist / f - soll) <= 0.015 for f in (100, 1000, 0.01, 0.001)):
            return "einheit", None
        if abs(ist + soll) <= 0.015:
            return "vorzeichen", None
        return "abweichend", (round((ist - soll) / abs(soll) * 100, 1) if soll else None)
    if _nah(ist, soll):
        return "richtig", round((ist - soll) / abs(soll) * 100, 3) if soll else 0.0
    if soll != 0 and any(_nah(ist / f, soll, abs_=1.0) for f in (1000, 1e6, 1e-3, 1e-6, 1e9)):
        return "einheit", None
    if abs(ist + soll) <= max(0.005 * abs(soll), 100000.0):
        return "vorzeichen", None
    for a in andere or []:
        try:
            if _nah(ist, float(a)):
                return "periode", None
        except (TypeError, ValueError):
            pass
    return "abweichend", (round((ist - soll) / abs(soll) * 100, 1) if soll else None)


def bewerte(fall, geparst, status=200):
    werte, andere = fall["amtlich"], fall["andere_perioden"]
    if status != 200:
        b = {k: ("http", status) for k in ("umsatz", "nettogewinn", "eps_verwaessert", "periodenende")}
        b["form"] = "http"
        return b
    g = geparst or {}
    b = {}
    b["umsatz"] = vergleiche(werte.get("umsatz"), g.get("umsatz"), andere.get("umsatz"))
    b["nettogewinn"] = vergleiche(werte.get("nettogewinn"), g.get("nettogewinn"), andere.get("nettogewinn"))
    b["eps_verwaessert"] = vergleiche(werte.get("eps_verwaessert"), g.get("eps_verwaessert"),
                                      andere.get("eps_verwaessert"), eps=True)
    pe = g.get("periodenende")
    if not pe:
        b["periodenende"] = ("fehlt", None)
    else:
        try:
            tage = abs((dt.date.fromisoformat(str(pe)[:10]) - dt.date.fromisoformat(fall["periodenende"])).days)
            b["periodenende"] = ("richtig" if tage <= 7 else "abweichend", tage)
        except ValueError:
            b["periodenende"] = ("unlesbar", None)
    b["form"] = "ok" if geparst else "kein_json"
    return b


# ---------------------------------------------------------------------------
# Lauf
# ---------------------------------------------------------------------------

def faelle_sammeln(hoechstens, ausgabe, log=print):
    import fundament_lauf as fl
    ticker = list(TICKER)
    try:
        import listen
        for t, _ in listen.alle_ticker():
            if t not in ticker:
                ticker.append(t)
    except Exception as e:  # noqa
        log(f"Wochenlisten nicht lesbar: {e}")
    cik = fl.ticker_zu_cik()
    faelle = []
    os.makedirs(os.path.join(ausgabe, "texte"), exist_ok=True)
    for t in ticker:
        if len(faelle) >= hoechstens:
            break
        c = cik.get(t.upper())
        if not c:
            log(f"  {t}: nicht im SEC-Register")
            continue
        try:
            fall = fall_finden(t, c, log)
        except Exception as e:  # noqa
            log(f"  {t}: {type(e).__name__}: {str(e)[:120]}")
            continue
        if not fall:
            log(f"  {t}: kein passendes Ergebnis-8-K mit amtlich belegtem Quartal")
            continue
        faelle.append(fall)
        with io.open(os.path.join(ausgabe, "texte", f"{t}.txt"), "w", encoding="utf-8") as f:
            f.write(fall["text"])
        log(f"  {t}: 8-K {fall['8k_datum']} ({fall['exhibit']}), Quartal bis {fall['periodenende']}, "
            f"amtlich {sorted(fall['amtlich'])}, Text {fall['text_zeichen_voll']} Zeichen")
        time.sleep(0.2)
    with io.open(os.path.join(ausgabe, "faelle.json"), "w", encoding="utf-8") as f:
        json.dump([{k: v for k, v in fl_.items() if k != "text"} for fl_ in faelle],
                  f, ensure_ascii=False, indent=1)
    return faelle


def messen(faelle, modelle, ausgabe, log=print):
    bremse = Bremse()
    ergebnisse = {}

    def ein_modell(modell):
        ordner = os.path.join(ausgabe, "antworten", modell.replace("/", "_"))
        os.makedirs(ordner, exist_ok=True)
        liste = []
        for fall in faelle:
            r = mistral_frage(modell, fall["text"], bremse)
            b = bewerte(fall, r.get("geparst"), r.get("status", 200))
            u = r.get("usage") or {}
            p = preis(modell)
            kosten = ((u.get("prompt_tokens", 0) / 1e6 * p[0] + u.get("completion_tokens", 0) / 1e6 * p[1])
                      if p else None)
            eintrag = {"ticker": fall["ticker"], "periodenende": fall["periodenende"],
                       "amtlich": fall["amtlich"], "antwort": r, "bewertung": b, "kosten_usd": kosten}
            with io.open(os.path.join(ordner, f"{fall['ticker']}.json"), "w", encoding="utf-8") as f:
                json.dump(eintrag, f, ensure_ascii=False, indent=1)
            liste.append(eintrag)
            log(f"  {modell} {fall['ticker']}: umsatz={b['umsatz'][0]} nettogewinn={b['nettogewinn'][0]} "
                f"eps={b['eps_verwaessert'][0]} periode={b['periodenende'][0]} {r['dauer_s']} s")
        return modell, liste

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(modelle))) as ex:
        for modell, liste in ex.map(ein_modell, modelle):
            ergebnisse[modell] = liste
    return ergebnisse


def bericht(ergebnisse, faelle, ausgabe):
    zeilen = ["# Messung der KI-Vorabwerte: Mistral liest 8-K-Pressemitteilungen", "",
              f"Faelle: {len(faelle)}; Stand {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC; "
              f"Text je Fall auf {TEXT_ZEICHEN} Zeichen gekuerzt.", ""]
    zusammen = {}
    for modell, liste in sorted(ergebnisse.items()):
        z = {"faelle": len(liste), "kosten_usd": round(sum(e["kosten_usd"] or 0 for e in liste), 4),
             "dauer_s": round(sum(e["antwort"]["dauer_s"] for e in liste) / max(1, len(liste)), 1),
             "kein_json": sum(1 for e in liste if e["bewertung"]["form"] != "ok")}
        for feld in ("umsatz", "nettogewinn", "eps_verwaessert", "periodenende"):
            klassen = {}
            for e in liste:
                k = e["bewertung"][feld][0]
                klassen[k] = klassen.get(k, 0) + 1
            z[feld] = klassen
        zusammen[modell] = z
        zeilen.append(f"## {modell}")
        zeilen.append(f"Faelle {z['faelle']}, Kosten {z['kosten_usd']} USD, mittlere Dauer {z['dauer_s']} s, "
                      f"ohne lesbares JSON {z['kein_json']}.")
        for feld in ("umsatz", "nettogewinn", "eps_verwaessert", "periodenende"):
            teile = ", ".join(f"{k} {v}" for k, v in sorted(z[feld].items()))
            zeilen.append(f"- {feld}: {teile}")
        harte = [e for e in liste if any(e["bewertung"][f][0] in ("einheit", "periode", "vorzeichen", "abweichend")
                                          for f in ("umsatz", "nettogewinn", "eps_verwaessert"))]
        if harte:
            zeilen.append("- Faelle mit falschen Zahlen: " + ", ".join(
                f"{e['ticker']} ({e['bewertung']['umsatz'][0]}/{e['bewertung']['nettogewinn'][0]}/{e['bewertung']['eps_verwaessert'][0]})"
                for e in harte))
        zeilen.append("")
    with io.open(os.path.join(ausgabe, "ergebnis.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(zeilen))
    with io.open(os.path.join(ausgabe, "ergebnis.json"), "w", encoding="utf-8") as f:
        json.dump(zusammen, f, ensure_ascii=False, indent=1)
    return "\n".join(zeilen)


def lauf(hoechstens, modelle, ausgabe):
    if not MISTRAL_KEY:
        print("MISTRAL_API_KEY fehlt (Secret im Actions-Lauf).")
        return 1
    import fundament_lauf as fl
    if not fl.UA:
        print("SEC_USER_AGENT fehlt (Secret im Actions-Lauf).")
        return 1
    os.makedirs(ausgabe, exist_ok=True)
    print("Faelle sammeln:")
    faelle = faelle_sammeln(hoechstens, ausgabe)
    print(f"{len(faelle)} Faelle.")
    if not faelle:
        return 1
    modelle = modelle or modelle_laden()
    print("Modelle:", ", ".join(modelle))
    ergebnisse = messen(faelle, modelle, ausgabe)
    print(bericht(ergebnisse, faelle, ausgabe))
    return 0


# ---------------------------------------------------------------------------
# Selbsttest (ohne Netz)
# ---------------------------------------------------------------------------

def selbsttest() -> int:
    fehler = []

    def p(name, ok, zusatz=""):
        print(f"  {'ok  ' if ok else 'FEHL'} {name}" + (f", {zusatz}" if zusatz else ""))
        if not ok:
            fehler.append(name)

    print("Messung 8-K, Selbsttest (ohne Netz)")
    html_roh = ("<html><body><h1>Q2 Results</h1><table><tr><th></th><th>Three Months Ended June 30, 2026</th></tr>"
                "<tr><td>Net sales</td><td>$ 1,234.5</td></tr><tr><td>Net income</td><td>210.0</td></tr></table>"
                "<p>Diluted EPS was $1.05.</p><script>x=1</script></body></html>")
    text = html_zu_text(html_roh)
    p("HTML wird Klartext mit Tabellenzeilen",
      "Net sales | $ 1,234.5" in text and "Three Months Ended" in text and "x=1" not in text, text[:80])
    p("Richtig innerhalb der Rundung", vergleiche(1234500000, 1234000000)[0] == "richtig")
    p("Tausend-Faktor als Einheitenfehler", vergleiche(1234500000, 1234500)[0] == "einheit")
    p("Millionen-Faktor als Einheitenfehler", vergleiche(1234500000, 1234.5)[0] == "einheit")
    p("Neunmonatswert als Periodenfehler", vergleiche(210000000, 640000000, andere=[640000000])[0] == "periode")
    p("Vorzeichen erkannt", vergleiche(-50000000, 50000000)[0] == "vorzeichen")
    p("Fehlend erkannt", vergleiche(1, None)[0] == "fehlt")
    p("Sonst abweichend", vergleiche(1000000000, 1300000000)[0] == "abweichend")
    p("EPS richtig bei 1 Cent", vergleiche(1.05, 1.06, eps=True)[0] == "richtig")
    p("EPS Faktor 100 als Einheit", vergleiche(1.05, 105, eps=True)[0] == "einheit")
    quart = ["2025-12-31", "2026-03-31", "2026-06-30"]
    p("Periode zum 8-K: juengstes belegtes Quartalsende davor",
      periode_zum_8k(quart, "2026-07-30") == "2026-06-30" and periode_zum_8k(quart, "2026-05-01") == "2026-03-31")
    p("Periode zum 8-K: kein Quartal, wenn zu alt", periode_zum_8k(quart, "2026-12-01") is None)
    p("Periode zum 8-K: 116 Tage sind zu alt (KO- und ANF-Falle des ersten Laufs)",
      periode_zum_8k(["2026-04-03"], "2026-07-28") is None)
    lang = "KOPF " * 2000 + "blabla " * 3000 + "Net income | $ | 4,766 | $ | 4,551\n" + "x " * 3000 + "Diluted | $ | 4.79\n" + "y " * 2000
    gek = text_kuerzen(lang, limit=16000, kopf=3000)
    p("Kuerzung nimmt Kopf und Kennzahlfenster mit, markiert Auslassungen",
      gek.startswith("KOPF") and "Net income | $ | 4,766" in gek and "Diluted | $ | 4.79" in gek
      and "[...]" in gek and len(gek) <= 16100, len(gek))
    p("HTTP-Fehler wird eigene Klasse",
      bewerte({"amtlich": {}, "andere_perioden": {}, "periodenende": "2026-06-30"}, None, 403)["form"] == "http")
    sub = {"filings": {"recent": {"form": ["8-K", "10-Q", "8-K"], "filingDate": ["2026-07-31", "2026-08-05", "2026-05-01"],
                                  "reportDate": ["2026-07-30", "", "2026-04-30"],
                                  "accessionNumber": ["a", "b", "c"], "primaryDocument": ["x", "y", "z"],
                                  "items": ["2.02,9.01", "", "5.02"]}}}
    e = ergebnis_8ks(sub)
    p("Nur 8-Ks mit Item 2.02, juengste zuerst", [x[2] for x in e] == ["a"])
    liste = [{"id": "mistral-small-latest", "aliases": ["mistral-small-2603"], "capabilities": {"completion_chat": True}},
             {"id": "mistral-small-2603", "aliases": ["mistral-small-latest"], "capabilities": {"completion_chat": True}},
             {"id": "mistral-embed", "aliases": [], "capabilities": {"completion_chat": False}},
             {"id": "voxtral-mini-transcribe-2602", "aliases": [], "capabilities": {"completion_chat": True}},
             {"id": "ministral-8b-2512", "aliases": ["ministral-8b-latest"], "capabilities": {"completion_chat": True}},
             {"id": "labs-leanstral-1-5-1", "aliases": [], "capabilities": {"completion_chat": True}}]
    p("Modellfilter: Aliasgruppen einmal, Einbettung und Transkription draussen",
      modelle_filtern(liste) == ["ministral-8b-2512", "mistral-small-2603"], modelle_filtern(liste))
    fall = {"amtlich": {"umsatz": 94036000000, "nettogewinn": 23434000000, "eps_verwaessert": 1.57},
            "andere_perioden": {"umsatz": [300000000000]}, "periodenende": "2025-06-28"}
    b = bewerte(fall, {"periodenende": "2025-06-30", "umsatz": 94036000000, "nettogewinn": 23434000000,
                       "eps_verwaessert": 1.57, "gaap": True})
    p("Bewertung: alles richtig, Periodenende innerhalb einer Woche",
      all(b[k][0] == "richtig" for k in ("umsatz", "nettogewinn", "eps_verwaessert", "periodenende")))
    b2 = bewerte(fall, None)
    p("Bewertung ohne JSON: Form kein_json, Werte fehlen", b2["form"] == "kein_json" and b2["umsatz"][0] == "fehlt")
    p("Preisregister findet Familien", preis("mistral-small-2603") == (0.15, 0.6) and preis("ministral-14b-2512") == (0.2, 0.2))
    if fehler:
        print(f"\n{len(fehler)} FEHLER: {', '.join(fehler)}")
        return 1
    print("\nAlles bestanden.")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selbsttest", action="store_true")
    ap.add_argument("--lauf", action="store_true")
    ap.add_argument("--hoechstens", type=int, default=30)
    ap.add_argument("--modelle", default="")
    ap.add_argument("--ausgabe", default=AUSGABE)
    a = ap.parse_args()
    if a.selbsttest:
        return selbsttest()
    if a.lauf:
        modelle = [m.strip() for m in a.modelle.split(",") if m.strip()]
        return lauf(a.hoechstens, modelle, a.ausgabe)
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
