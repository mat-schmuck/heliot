# -*- coding: utf-8 -*-
"""Pressetext-Archiv fuer Gerhards KI-Abfrage (Vorstufe zu "Quartal ueber
Quartal"): die Ergebnis-Pressemitteilungen (Anhang 99.1 der 8-Ks mit
Item 2.02) der Firmen mit Konsens, je Firma die juengsten QUARTALE Stueck,
als gepackter Klartext im privaten Datenrepo.

Ablage (Ordner pressetexte im Datenrepo):
  <CIK10>/<accession>.txt.gz   Klartext samt Tabellenzeilen (Zellen mit
                               ' | ' getrennt), auf TEXT_DECKEL Zeichen
                               begrenzt
  index.jsonl                  eine Zeile je Text: cik, ticker, accession,
                               filed, report, exhibit, zeichen, quelle, zeit
  stand.json                   je CIK: Ticker, gepruefte Accessions, Zeit
                               (Fortsetzung ueber mehrere Laeufe)
  laeufe.jsonl                 eine Zeile je Lauf

Der Abzug laeuft in Portionen (hoechstens N Firmen je Lauf); Firmen mit
frischem Stand werden uebersprungen. Der 8-K-Strom (vorabwerte_8k.py)
speichert jeden neu gelesenen Text ueber speichern() mit. SEC-Abrufe nur im
Actions-Lauf (Secret SEC_USER_AGENT), hoechstens rund acht je Sekunde.
"""
import argparse
import datetime as dt
import gzip
import io
import json
import os
import re
import sys
import time

QUARTALE = 8
TEXT_DECKEL = 80000
PAUSE_S = 0.13
FRISCH_TAGE = 20
ORDNER = "pressetexte"
EFTS = ("https://efts.sec.gov/LATEST/search-index?q={q}&forms=6-K&ciks={cik10}&startdt={von}&enddt={bis}")
SECHS_K_SUCHEN = ('"quarter" results', '"half-year" results', '"interim" results', '"trading update"',
                  '"first half" results', '"full year" results')   # Volltextsuche der SEC: alle Woerter muessen vorkommen
SECHS_K_MAX_ZEICHEN = 900000          # darueber liegen Prospekte und Jahresberichte; Abschluesse grosser Konzerne haben bis 760.000
KOPF_BEI_KUERZUNG = 20000             # ueberlange Texte: Kopf plus Fenster um die Kennzahlzeilen statt hartem Schnitt
SECHS_K_TAGE = 760                    # zwei Jahre, also acht Quartale
SECHS_K_JE_FILING = 3                 # hoechstens so viele Anhaenge je 6-K laden


# ---------------------------------------------------------------------------
# Ablage
# ---------------------------------------------------------------------------

def _jetzt():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def text_pfad(daten, cik, accession):
    return os.path.join(daten, ORDNER, f"{int(cik):010d}", f"{accession}.txt.gz")


def vorhanden(daten, cik, accession):
    return os.path.exists(text_pfad(daten, cik, accession))


def text_lesen(daten, cik, accession):
    p = text_pfad(daten, cik, accession)
    if not os.path.exists(p):
        return None
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return f.read()


def speichern(daten, cik, ticker, accession, filed, report, exhibit, text, quelle="archiv"):
    """Legt einen Text ab und schreibt die Index-Zeile; gibt die Metadaten zurueck."""
    text = (text or "").strip()
    gekuerzt = len(text) > TEXT_DECKEL
    if gekuerzt:
        import messung_8k as m8k
        text = m8k.text_kuerzen(text, limit=TEXT_DECKEL, kopf=KOPF_BEI_KUERZUNG)
    p = text_pfad(daten, cik, accession)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    # mtime 0: derselbe Text ergibt immer dieselben Bytes; sonst legen Strom und Archiv-Portion
    # dieselbe Datei byte-verschieden an, und Git meldet beim Zusammenfuehren einen add/add-Konflikt
    with open(p, "wb") as roh:
        with gzip.GzipFile(fileobj=roh, mode="wb", mtime=0) as gz:
            gz.write(text.encode("utf-8"))
    meta = {"zeit": _jetzt(), "cik": int(cik), "ticker": ticker, "accession": accession, "filed": filed,
            "report": report, "exhibit": exhibit, "zeichen": len(text), "gekuerzt": gekuerzt, "quelle": quelle}
    os.makedirs(os.path.join(daten, ORDNER), exist_ok=True)
    with io.open(os.path.join(daten, ORDNER, "index.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")
    return meta


def index_lesen(daten):
    p = os.path.join(daten, ORDNER, "index.jsonl")
    if not os.path.exists(p):
        return []
    raus = []
    with io.open(p, encoding="utf-8") as f:
        for zeile in f:
            zeile = zeile.strip()
            if zeile:
                raus.append(json.loads(zeile))
    return raus


def texte_der_firma(daten, cik, hoechstens=QUARTALE):
    """[(meta, text)] der juengsten Texte einer Firma, juengste zuerst."""
    metas = {}
    for m in index_lesen(daten):
        if int(m.get("cik", -1)) == int(cik):
            metas[m["accession"]] = m
    liste = sorted(metas.values(), key=lambda m: (m.get("filed") or "", m["accession"]), reverse=True)[:hoechstens]
    raus = []
    for m in liste:
        t = text_lesen(daten, cik, m["accession"])
        if t:
            raus.append((m, t))
    return raus


def stand_laden(daten):
    p = os.path.join(daten, ORDNER, "stand.json")
    if not os.path.exists(p):
        return {}
    with io.open(p, encoding="utf-8") as f:
        return json.load(f)


def stand_schreiben(daten, stand):
    os.makedirs(os.path.join(daten, ORDNER), exist_ok=True)
    p = os.path.join(daten, ORDNER, "stand.json")
    tmp = p + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(stand, f, ensure_ascii=False, indent=0, sort_keys=True)
    os.replace(tmp, p)


# ---------------------------------------------------------------------------
# SEC
# ---------------------------------------------------------------------------

def submissions(cik, hole):
    return json.loads(hole(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"))


def exhibit(cik, accession, hole):
    """(Dateiname, Klartext) des Anhangs 99.1, sonst (None, None); Logik wie
    messung_8k.exhibit_text, aber mit uebergebenem Abruf (pruefbar ohne Netz)."""
    import messung_8k as m8k
    ordner = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}"
    index = json.loads(hole(ordner + "/index.json"))
    dateien = [d for d in index.get("directory", {}).get("item", [])
               if d.get("name", "").lower().endswith((".htm", ".html"))]
    kandidaten = [d for d in dateien if re.search(r"ex[-_]?99", d["name"].lower())]
    if not kandidaten:
        kandidaten = [d for d in dateien if not d["name"].lower().startswith("0")]
    if not kandidaten:
        return None, None
    kandidaten.sort(key=lambda d: int(d.get("size") or 0), reverse=True)
    name = kandidaten[0]["name"]
    roh = hole(ordner + "/" + name)
    try:
        html_roh = roh.decode("utf-8")
    except UnicodeDecodeError:
        html_roh = roh.decode("latin-1")
    return name, m8k.html_zu_text(html_roh)


def firmen(daten, ticker_zu_cik, nur=None):
    """[(cik, ticker)] der Firmen mit Konsens, je Firma der Haupt-Ticker,
    nach Ticker sortiert; nur = Liste gewuenschter Ticker."""
    import konsens_einfrieren as ke
    import vorabwerte_8k as va
    bestand = ke._json(os.path.join(daten, "konsens", "firmen_mit_konsens.json"), {})
    if nur:
        gewuenscht = {t.strip().upper() for t in nur if t.strip()}
        bestand = {t: v for t, v in bestand.items() if str(t).upper() in gewuenscht}
        for t in gewuenscht:
            if t not in {str(b).upper() for b in bestand}:
                bestand[t] = {}
    raus = va.hauptticker(bestand, ticker_zu_cik)
    return sorted(raus.items(), key=lambda kv: kv[1])


# ---------------------------------------------------------------------------
# 6-K (auslaendische Emittenten): Ergebnismitteilungen ohne Item-Kennung
# ---------------------------------------------------------------------------

def sechs_k_treffer(antwort_json):
    """Treffer der SEC-Volltextsuche als [{accession, datei, file_type, file_date, period_ending}];
    nur Anhaenge (EX-99...) oder das Hauptdokument des 6-K."""
    raus = []
    for h in (antwort_json.get("hits") or {}).get("hits") or []:
        kennung = h.get("_id") or ""
        if ":" not in kennung:
            continue
        acc, datei = kennung.split(":", 1)
        s = h.get("_source") or {}
        art = (s.get("file_type") or "").upper()
        if not (art.startswith("EX-99") or art == "6-K"):
            continue
        raus.append({"accession": acc, "datei": datei, "file_type": art, "file_date": s.get("file_date"),
                     "period_ending": s.get("period_ending")})
    return raus


_MUSTER_ERGEBNIS = (
    re.compile(r"net (income|profit|loss|earnings)|profit (for|after)|EBITDA|operating (income|profit|result)", re.I),
    re.compile(r"revenue|net sales|turnover|total sales", re.I),
    re.compile(r"(first|second|third|fourth) quarter|\bQ[1-4]\b|three months|six months|half[- ]year|nine months|"
               r"full[- ]year|fiscal (year|20\d\d)|interim", re.I),
    re.compile(r"(per share|per ADS|EPS|earnings per)", re.I),
)


_KEINE_MITTEILUNG = re.compile(r"comments from the officers|reference form|formul[aá]rio de refer|annual report on form 20-F|"
                               r"proxy statement|management proposal|convocation", re.I)
# Hauptversammlungs- und Vollmachtsunterlagen: nur im Titel (die ersten Zeichen nach dem Formularkopf), denn
# Quartalsberichte verweisen im Text auf das Information Circular, und ein Ergebnistext darf die Hauptversammlung
# ankuendigen ("announces results and issues notice of annual general meeting")
_HV_TITEL = re.compile(r"proxy circular|information circular|management proxy|form of proxy|solicitation of prox|"
                       r"notice of (the )?(\d{4} )?(annual|special|extraordinary)|notice of meeting|meeting brochure|"
                       r"circular is important|document is important and requires|"
                       r"(annual|special|extraordinary)( general)?( and special)? meeting of (share|stock)holders", re.I)
# andere Unterlagen, die Ergebnis- und Periodenwoerter samt Betraegen tragen, aber keine Ergebnismitteilung sind:
# Vertraege, Prospekte, technische Berichte, Praesentationen, Verguetungs- und Nachhaltigkeitsberichte
_UNTERLAGE_TITEL = re.compile(r"technical report|ni 43-101|mineral resource estimate|prospectus supplement|"
                              r"no securities regulatory authority|filed pursuant to rule 424|execution version|"
                              r"by and among|by and between|witnesseth|as lenders|administrative agent|"
                              r"(joint )?bookrunners|credit (agreement|facility) dated|"
                              r"(share|stock|asset|membership interest|master|securities) purchase agreement|"
                              r"arrangement agreement|amending agreement|subscription agreement|facility agreement|"
                              r"term loan facility|declaration of trust|terms and conditions of the notes|"
                              r"sustainability report|compensation report|corporate governance report|"
                              r"annual information form|investor presentation|material change report|"
                              r"business acquisition report|pro forma condensed", re.I)
# Ergebnistitel: Mitteilung, Bericht oder Abschluss. Steht er im Titel VOR einem Unterlagen- oder
# Hauptversammlungswort, ist der Text eine Ergebnisunterlage, die nur darauf verweist (Berichte nennen das
# Information Circular und die Annual Information Form; TAL kuendigt im Ergebnistitel die Hauptversammlung an).
# Steht das Unterlagenwort zuerst, ist es der Titel des Dokuments (Circulars nennen spaeter Abschluss und MD&A).
_ERGEBNIS_TITEL = re.compile(r"(announces|reports|posts|delivers|publishes|releases)[^.]{0,80}(results|earnings)|"
                             r"earnings (release|report)|kessan tanshin|results announcement|financial results|"
                             r"management.{0,3}s discussion|MD&A|annual report(?!s? under cover)|"
                             r"(audited|unaudited|condensed|interim|consolidated) (consolidated )?(interim )?financial (statements|information|report)|"
                             r"(quarterly|interim|half.?year|(first|second|third|fourth) quarter) (report|results|update)|"
                             r"activit(y|ies) report|returns? to profitab|(revenue|sales)s? (increased?|grew|rose|growth)|"
                             r"net (income|loss|profit) (of|was|rose|fell|increased|decreased)|"
                             r"\b[1-4]q ?\d{2}\b|\bq[1-4] ?(fy)?(20)?\d{2}\b|"
                             r"results for the (period|quarter|year|three|six|nine|twelve|first|second|third|fourth)", re.I)
_DECKBLATT_ENDE = re.compile(r"Rule 12g3-2\(b\)[^\n]{0,200}|Rule 101\(b\)\(7\)[^\n]{0,60}|Form 40-?\s?F[^\n]{0,40}", re.I)


def titelzone(text, laenge=1200):
    """Die ersten Zeichen des eigentlichen Dokuments: bei 6-K-Hauptdokumenten hinter dem Formularkopf
    (der endet mit der Frage nach Rule 12g3-2(b)), sonst der Textanfang; dazu immer der Textanfang selbst
    (Anhaenge tragen ihren Titel in der ersten Zeile)."""
    kopf = text[:1200]
    ende = None
    for m in _DECKBLATT_ENDE.finditer(text[:6000]):
        ende = m.end()
    if ende:
        return kopf + "\n" + text[ende:ende + laenge]
    return text[:laenge + 1200]


def ausschlussgrund(text):
    """Warum ein Text keine Ergebnismitteilung sein kann (Kopf- und Titelmuster), sonst None."""
    kopf = text[:6000]
    a = _KEINE_MITTEILUNG.search(kopf)
    if a:
        return "Kopf: " + a.group(0)
    titel = titelzone(text)
    kandidaten = [(m.start(), art + ": " + m.group(0)) for art, m in
                  (("Hauptversammlung", _HV_TITEL.search(titel)), ("Unterlage", _UNTERLAGE_TITEL.search(titel))) if m]
    if kandidaten:
        e = _ERGEBNIS_TITEL.search(titel)
        erster = min(kandidaten)
        if e is None or erster[0] < e.start():
            return erster[1]
    return None


def ist_ergebnismitteilung(text, dateiname=""):
    """(ja/nein, Punkte): Ergebnismitteilung, wenn frueh im Text ein Periodenwort steht, Ergebnis- und
    Umsatzwoerter samt Waehrungszahlen vorkommen und es keine Hauptversammlungs- oder Berichtsunterlage ist.
    Punkte bevorzugen dichte, mittellange Texte mit sprechendem Dateinamen (Pressemitteilung vor Berichtsheft)."""
    if not text or len(text) < 1500:
        return False, 0
    if ausschlussgrund(text):
        return False, 0
    if not _MUSTER_ERGEBNIS[2].search(text[:max(6000, len(text) // 3)]):
        return False, 0
    punkte, zahlen, treffer = kriterien(text)
    ja = punkte >= 3 and zahlen >= 5 and treffer >= 4
    dichte = treffer * 10000.0 / max(len(text), 1)
    wert = punkte * 10 + min(dichte * 4, 40) + min(zahlen, 30) + textklasse(text, dateiname)[1]
    if re.search(r"itr|\d{8}_6k", (dateiname or "").lower()):
        wert -= 10
    if len(text) > 150000:
        wert -= 20
    return ja, round(wert, 1)


_WAEHRUNG = (r"US\$|\$|EUR|€|R\$|CHF|£|¥|USD|BRL|Ps\.|MXN|Ch\$|CLP|COP|ARS|AR\$|PEN|S/\.?|KRW|₩|INR|₹|Rs\.?|JPY|TWD|NT\$|"
             r"HK\$|HKD|RMB|CNY|SGD|S\$|A\$|AUD|C\$|CAD|CA\$|NZ\$|NOK|SEK|DKK|ZAR|TRY|PLN|CZK|HUF|ILS|NIS|EGP|SAR|AED|IDR|Rp|"
             r"THB|PHP|MYR|RM|VND|GBP|NGN|KES|GHS|QAR|KWD|Bs\.|Bs")
_ZAHL_MIT_WAEHRUNG = re.compile(r"(?:" + _WAEHRUNG + r")\s?\d[\d,.]*", re.I)
_ZAHL_MIT_EINHEIT = re.compile(r"\d[\d,.]*\s?(?:million|billion|mn|bn|thousand|crore|lakh)\b", re.I)
_TAUSENDERZAHL = re.compile(r"(?<![\d.,])\d{1,3}(?:,\d{3}){1,4}(?![\d,])")


def kriterien(text):
    """(punkte, zahlen, treffer): Zahl der Musterarten mit Treffer, Zahl der Betraege (mit Waehrung, mit
    Einheit oder als Tausenderzahl) und Zahl der Ergebnis- und Umsatzwoerter."""
    punkte = sum(1 for m in _MUSTER_ERGEBNIS if m.search(text))
    zahlen = (len(_ZAHL_MIT_WAEHRUNG.findall(text)) + len(_ZAHL_MIT_EINHEIT.findall(text))
              + len(_TAUSENDERZAHL.findall(text)))
    treffer = sum(len(m.findall(text)) for m in _MUSTER_ERGEBNIS[:2])
    return punkte, zahlen, treffer


_TITEL_MITTEILUNG = re.compile(r"(announces|reports|posts|delivers|publishes|releases)[^.]{0,80}(results|earnings)|"
                               r"earnings (release|report)|results announcement|press release|news release|"
                               r"financial results|trading update", re.I)
_TITEL_MDA = re.compile(r"management.{0,3}s discussion|MD&A", re.I)
_TITEL_BERICHT = re.compile(r"(quarterly|interim|half.?year|annual) report|financial statements and review|"
                            r"(first|second|third|fourth) quarter (20\d\d )?report", re.I)


def textklasse(text, dateiname=""):
    """(Klasse, Rangbonus): Pressemitteilung vor MD&A vor Berichtsheft vor Abschluss. Die Klasse kommt aus dem
    Dateinamen (pressrelease, mda, fs) oder dem Titel; der Bonus ordnet die Anhaenge einer Einreichung, die
    Feinpunkte (Dichte, Betraege) entscheiden nur innerhalb einer Klasse."""
    name = (dateiname or "").lower()
    # erst der Dateiname (er benennt den Anhang eindeutig: pressrelease, mda, fs), dann der Titel
    if re.search(r"pr\d|press|release|news|earnings", name):
        return "mitteilung", 60
    if re.search(r"mda|md&a|discussion", name):
        return "mda", 30
    if re.search(r"fs(?=[0-9_.-]|$)|financial.?statements|finstat|fs", name):
        return "abschluss", 0
    if re.search(r"report|itr|review", name):
        return "bericht", 15
    titel = titelzone(text, 800)
    if _TITEL_MITTEILUNG.search(titel):
        return "mitteilung", 60
    if _TITEL_MDA.search(titel):
        return "mda", 30
    if _TITEL_BERICHT.search(titel):
        return "bericht", 15
    return "abschluss", 0


def sechs_k_ergebnisse(cik, hole, heute, quartale=QUARTALE, log=print, warte=True, ausfuehrlich=False):
    """[(filing_datum, period_ending, accession, datei, text)] der juengsten Ergebnis-6-Ks einer Firma:
    eine Volltextsuche der SEC, dann je Einreichung die Anhaenge, der beste Text je Einreichung,
    hoechstens einer je Kalendermonat, juengste zuerst."""
    von = (heute - dt.timedelta(days=SECHS_K_TAGE)).isoformat()
    je_filing = {}
    for suche in SECHS_K_SUCHEN:
        url = EFTS.format(q=suche.replace('"', "%22").replace(" ", "%20"), cik10=f"{int(cik):010d}",
                          von=von, bis=heute.isoformat())
        try:
            antwort = json.loads(hole(url))
        except Exception as e:  # noqa
            log(f"    Volltextsuche {suche}: {str(e)[:100]}")
            continue
        if warte:
            time.sleep(PAUSE_S)
        treffer = sechs_k_treffer(antwort)
        if ausfuehrlich:
            roh = len(((antwort.get("hits") or {}).get("hits") or []))
            log(f"    Suche {suche}: {roh} Treffer, davon {len(treffer)} Anhaenge oder Hauptdokumente")
        for tr in treffer:
            liste = je_filing.setdefault(tr["accession"], [])
            if all(x["datei"] != tr["datei"] for x in liste):
                liste.append(tr)
    kandidaten = []
    for acc, liste in je_filing.items():
        anhaenge = [x for x in liste if x["file_type"].startswith("EX-99")] or liste
        bester = None
        for x in anhaenge[:SECHS_K_JE_FILING]:
            ordner = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}"
            try:
                roh = hole(ordner + "/" + x["datei"])
            except Exception as e:  # noqa
                log(f"    {acc} {x['datei']}: nicht lesbar: {str(e)[:100]}")
                continue
            if warte:
                time.sleep(PAUSE_S)
            try:
                html_roh = roh.decode("utf-8")
            except UnicodeDecodeError:
                html_roh = roh.decode("latin-1")
            import messung_8k as m8k
            text = m8k.html_zu_text(html_roh)
            if len(text) > SECHS_K_MAX_ZEICHEN:
                if ausfuehrlich:
                    log(f"    {acc} {x['datei']}: {len(text)} Zeichen, zu gross")
                continue
            ja, punkte = ist_ergebnismitteilung(text, x["datei"])
            if ausfuehrlich:
                k = kriterien(text)
                log(f"    {acc} {x['file_date']} {x['file_type']} {x['datei']}: {len(text)} Zeichen, "
                    f"{'Mitteilung' if ja else 'keine Mitteilung'} ({textklasse(text, x['datei'])[0]}, Musterarten {k[0]}, "
                    f"Betraege {k[1]}, Ergebniswoerter {k[2]}, Ausschluss {ausschlussgrund(text) or '-'}), {punkte} Punkte: "
                    f"{' '.join(text[:110].split())}")
            if ja and (bester is None or punkte > bester[0]):
                bester = (punkte, x, text)
        if bester:
            punkte, x, text = bester
            kandidaten.append((x["file_date"] or "", x.get("period_ending") or "", acc, x["datei"], text, punkte))
    # je Einreichmonat nur der beste Text (Pressemitteilung schlaegt Berichtsheft); die Periodenangabe der
    # Volltextsuche ist bei 6-K unzuverlaessig (oft das Einreichdatum oder ein fremdes Quartal) und dient nur
    # als Hinweis, wenn sie vom Einreichdatum abweicht
    kandidaten.sort(key=lambda k: k[5], reverse=True)
    raus, monate = [], set()
    for fd, pe, acc, datei, text, punkte in kandidaten:
        monat = (fd or "")[:7]
        if monat in monate:
            continue
        monate.add(monat)
        raus.append((fd, pe if (pe and pe != fd) else "", acc, datei, text))
    raus.sort(key=lambda k: (k[0], k[2]), reverse=True)
    return raus[:quartale]


def firmen_ohne_8k(daten):
    """[(cik, ticker)] der Firmen, deren Stand keine Ergebnis-8-Ks kennt (Kandidaten fuer 6-K)."""
    stand = stand_laden(daten)
    raus = [(int(cik), s.get("ticker")) for cik, s in stand.items() if not s.get("accessions")]
    return sorted(raus, key=lambda kv: kv[1] or "")


def lauf_6k(daten, hoechstens=0, quartale=QUARTALE, nur=None, hole=None, log=print, jetzt=None, warte=True,
            frisch_tage=FRISCH_TAGE):
    if hole is None:
        import fundament_lauf as fl
        if not fl.UA:
            raise RuntimeError("SEC_USER_AGENT fehlt (Secret im Actions-Lauf).")
        hole = fl.hole
    jetzt = jetzt or dt.datetime.now(dt.timezone.utc)
    heute = jetzt.date()
    stand = stand_laden(daten)
    liste = firmen_ohne_8k(daten)
    if nur:
        gewuenscht = {x.strip().upper() for x in nur if x.strip()}
        liste = [(c, tck) for c, tck in liste if (tck or "").upper() in gewuenscht]
    bilanz = {"zeit": jetzt.replace(microsecond=0).isoformat(), "modus": "6k", "firmen_gesamt": len(liste), "firmen": 0,
              "uebersprungen": 0, "texte_neu": 0, "texte_da": 0, "ohne_ergebnis": 0, "fehler": 0, "abbruch": None}
    log(f"Firmen ohne Ergebnis-8-K: {len(liste)}; 6-K-Suche ueber die SEC-Volltextsuche, je Firma hoechstens {quartale} Mitteilungen")
    for cik, ticker in liste:
        if hoechstens and bilanz["firmen"] >= hoechstens:
            bilanz["abbruch"] = "Portion voll"
            break
        s = stand.get(str(cik)) or {}
        sk = s.get("sechs_k") or {}
        if sk.get("zeit") and not nur and frisch_tage > 0:
            try:
                if (jetzt - dt.datetime.fromisoformat(sk["zeit"])).days < frisch_tage:
                    bilanz["uebersprungen"] += 1
                    continue
            except ValueError:
                pass
        try:
            ergebnisse = sechs_k_ergebnisse(cik, hole, heute, quartale, log=log, warte=warte)
        except Exception as e:  # noqa
            bilanz["fehler"] += 1
            log(f"  {ticker} {cik}: 6-K-Suche gescheitert: {str(e)[:120]}")
            continue
        neu = da = 0
        for fd, pe, acc, datei, text in ergebnisse:
            if vorhanden(daten, cik, acc):
                da += 1
                continue
            speichern(daten, cik, ticker, acc, fd, pe, datei, text, quelle="archiv-6k")
            neu += 1
        s["sechs_k"] = {"zeit": jetzt.replace(microsecond=0).isoformat(), "accessions": [e[2] for e in ergebnisse]}
        s.setdefault("ticker", ticker)
        stand[str(cik)] = s
        bilanz["firmen"] += 1
        bilanz["texte_neu"] += neu
        bilanz["texte_da"] += da
        if not ergebnisse:
            bilanz["ohne_ergebnis"] += 1
        log(f"  {ticker} {cik}: {len(ergebnisse)} Ergebnis-6-Ks, {neu} neu, {da} vorhanden")
        if bilanz["firmen"] % 100 == 0:
            stand_schreiben(daten, stand)
    stand_schreiben(daten, stand)
    with io.open(os.path.join(daten, ORDNER, "laeufe.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(bilanz, ensure_ascii=False) + "\n")
    log(f"Ergebnis: {bilanz}")
    return bilanz


def probe_6k(ticker, hole=None, jetzt=None, log=print):
    """Zeigt fuer eine Firma, was die 6-K-Suche findet, ohne zu speichern."""
    import fundament_lauf as fl
    if hole is None:
        if not fl.UA:
            raise RuntimeError("SEC_USER_AGENT fehlt (Secret im Actions-Lauf).")
        hole = fl.hole
    cik = fl.ticker_zu_cik().get(ticker.upper())
    if not cik:
        log(f"{ticker}: keine CIK")
        return []
    heute = (jetzt or dt.datetime.now(dt.timezone.utc)).date()
    ergebnisse = sechs_k_ergebnisse(cik, hole, heute, log=log, ausfuehrlich=True)
    log(f"{ticker} CIK {cik}: {len(ergebnisse)} Ergebnis-6-Ks")
    for fd, pe, acc, datei, text in ergebnisse:
        log(f"  {fd} Periode {pe or '?'} {acc} {datei} {len(text)} Zeichen: {text[:160].replace(chr(10), ' ')}")
    return ergebnisse


def probe_8k(ticker, hole=None, hoechstens=12, log=print):
    """Zeigt fuer eine Firma die juengsten 8-Ks samt Item-Kennungen und wie viele davon
    als Ergebnis-8-K (Item 2.02) gelten, ohne zu speichern."""
    import fundament_lauf as fl
    import messung_8k as m8k
    if hole is None:
        if not fl.UA:
            raise RuntimeError("SEC_USER_AGENT fehlt (Secret im Actions-Lauf).")
        hole = fl.hole
    cik = fl.ticker_zu_cik().get(ticker.upper())
    if not cik:
        log(f"{ticker}: keine CIK")
        return []
    sub = submissions(cik, hole)
    r = sub.get("filings", {}).get("recent", {})
    achtks = [(fd, items, prim, acc) for form, fd, items, prim, acc in zip(r.get("form", []), r.get("filingDate", []),
              r.get("items", []), r.get("primaryDocument", []), r.get("accessionNumber", [])) if form == "8-K"]
    ergebnis = m8k.ergebnis_8ks(sub)
    formen = {}
    for form in r.get("form", []):
        formen[form] = formen.get(form, 0) + 1
    log(f"{ticker} CIK {cik}: {len(achtks)} 8-Ks in der juengsten Liste, {len(ergebnis)} mit Item 2.02; Formulare: "
        + ", ".join(f"{k} {v}" for k, v in sorted(formen.items(), key=lambda kv: -kv[1])[:8]))
    for fd, items, prim, acc in achtks[:hoechstens]:
        log(f"  {fd} Items {items or '?':20s} {acc} {prim}")
    return achtks


# ---------------------------------------------------------------------------
# Lauf
# ---------------------------------------------------------------------------

def lauf(daten, hoechstens=1200, quartale=QUARTALE, nur=None, hole=None, ticker_zu_cik=None,
         log=print, jetzt=None, warte=True, frisch_tage=FRISCH_TAGE):
    if hole is None or ticker_zu_cik is None:
        import fundament_lauf as fl
        if not fl.UA:
            raise RuntimeError("SEC_USER_AGENT fehlt (Secret im Actions-Lauf).")
        hole = hole or fl.hole
        ticker_zu_cik = ticker_zu_cik or fl.ticker_zu_cik()
    jetzt = jetzt or dt.datetime.now(dt.timezone.utc)
    stand = stand_laden(daten)
    liste = firmen(daten, ticker_zu_cik, nur)
    bilanz = {"zeit": jetzt.replace(microsecond=0).isoformat(), "firmen_gesamt": len(liste), "firmen": 0,
              "uebersprungen": 0, "texte_neu": 0, "texte_da": 0, "ohne_exhibit": 0, "fehler": 0, "abbruch": None}
    log(f"Firmen mit Konsens: {len(liste)}; je Firma die juengsten {quartale} Ergebnis-8-Ks; hoechstens {hoechstens or 'alle'} Firmen in diesem Lauf")

    def pause():
        if warte:
            time.sleep(PAUSE_S)

    try:
        for cik, ticker in liste:
            if hoechstens and bilanz["firmen"] >= hoechstens:
                bilanz["abbruch"] = "Portion voll"
                break
            s = stand.get(str(cik))
            if s and not nur:
                try:
                    alter = (jetzt - dt.datetime.fromisoformat(s["zeit"])).days
                except (KeyError, ValueError):
                    alter = 10 ** 6
                if s.get("vollstaendig") and alter < frisch_tage:
                    bilanz["uebersprungen"] += 1
                    continue
            try:
                sub = submissions(cik, hole)
                pause()
            except Exception as e:  # noqa
                bilanz["fehler"] += 1
                log(f"  {ticker} {cik}: Einreichungen nicht lesbar: {str(e)[:120]}")
                continue
            import messung_8k as m8k
            achtks = m8k.ergebnis_8ks(sub)[:quartale]
            geprueft = list((s or {}).get("accessions") or [])
            neu = da = leer = 0
            for fd, rd, acc, prim in achtks:
                if vorhanden(daten, cik, acc):
                    da += 1
                    continue
                if acc in geprueft and (s or {}).get("leer", {}).get(acc):
                    leer += 1
                    continue
                try:
                    name, text = exhibit(cik, acc, hole)
                    pause()
                except Exception as e:  # noqa
                    bilanz["fehler"] += 1
                    log(f"  {ticker} {acc}: Anhang nicht lesbar: {str(e)[:120]}")
                    continue
                if not text:
                    leer += 1
                    s = s or {}
                    s.setdefault("leer", {})[acc] = True
                    continue
                speichern(daten, cik, ticker, acc, fd, rd, name, text, quelle="archiv")
                neu += 1
            stand[str(cik)] = {"ticker": ticker, "zeit": jetzt.replace(microsecond=0).isoformat(),
                               "accessions": [a[2] for a in achtks], "vollstaendig": True,
                               "leer": (s or {}).get("leer", {})}
            bilanz["firmen"] += 1
            bilanz["texte_neu"] += neu
            bilanz["texte_da"] += da
            bilanz["ohne_exhibit"] += leer
            log(f"  {ticker} {cik}: {len(achtks)} Ergebnis-8-Ks, {neu} neu, {da} vorhanden, {leer} ohne Anhang")
            if bilanz["firmen"] % 100 == 0:
                stand_schreiben(daten, stand)
    except KeyboardInterrupt:
        bilanz["abbruch"] = "unterbrochen"
    stand_schreiben(daten, stand)
    os.makedirs(os.path.join(daten, ORDNER), exist_ok=True)
    with io.open(os.path.join(daten, ORDNER, "laeufe.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(bilanz, ensure_ascii=False) + "\n")
    log(f"Ergebnis: {bilanz}")
    return bilanz


# ---------------------------------------------------------------------------
# Selbsttest (ohne Netz)
# ---------------------------------------------------------------------------

def selbsttest() -> int:
    import tempfile
    import konsens_einfrieren as ke
    fehler = 0

    def p(name, ok, extra=""):
        nonlocal fehler
        print(f"  {'ok  ' if ok else 'FEHL'} {name}{(' ' + str(extra)) if extra else ''}")
        if not ok:
            fehler += 1

    def sub_json(cik, n):
        accs = [f"{cik:010d}-26-{i:06d}" for i in range(n)]
        return json.dumps({"filings": {"recent": {
            "form": ["8-K"] * n + ["10-Q"], "filingDate": [f"2026-{(i % 12) + 1:02d}-15" for i in range(n)] + ["2026-05-01"],
            "reportDate": [f"2026-{(i % 12) + 1:02d}-01" for i in range(n)] + [""],
            "accessionNumber": accs + [f"{cik:010d}-26-999999"], "primaryDocument": ["a.htm"] * (n + 1),
            "items": ["2.02,9.01"] * n + [""]}}}).encode("utf-8")

    html = ("<html><body><p>Apple today announced results.</p><table><tr><td>Net sales</td><td>94,036</td>"
            "</tr></table><p>Outlook: we expect growth.</p></body></html>").encode("utf-8")
    aufrufe = []

    def hole(url):
        aufrufe.append(url)
        if "submissions" in url:
            cik = int(re.search(r"CIK(\d+)", url).group(1))
            return sub_json(cik, 10 if cik == 320193 else 2)
        if url.endswith("index.json"):
            if "000001472426000001" in url.replace("-", ""):
                return json.dumps({"directory": {"item": [{"name": "0001.htm", "size": 10}]}}).encode("utf-8")
            return json.dumps({"directory": {"item": [{"name": "a-ex99_1.htm", "size": 5000},
                                                       {"name": "0001.htm", "size": 100}]}}).encode("utf-8")
        return html

    with tempfile.TemporaryDirectory() as tmp:
        ke._schreibe_json(os.path.join(tmp, "konsens", "firmen_mit_konsens.json"),
                          {"AAPL": {}, "BF-B": {}, "BF-A": {}, "XYZ": {}})
        tzc = {"AAPL": 320193, "BF-B": 14693, "BF-A": 14693}
        f = firmen(tmp, tzc)
        p("Firmen: Haupt-Ticker je CIK (BF-B vor BF-A), Unbekanntes faellt weg",
          f == [(320193, "AAPL"), (14693, "BF-B")], f)
        b = lauf(tmp, hoechstens=0, quartale=8, hole=hole, ticker_zu_cik=tzc, log=lambda *_: None,
                 jetzt=dt.datetime(2026, 9, 3, tzinfo=dt.timezone.utc), warte=False)
        p("Lauf: Apple bekommt die juengsten 8 von 10 Ergebnis-8-Ks, Brown-Forman seine 2",
          b["firmen"] == 2 and b["texte_neu"] == 10 and b["texte_da"] == 0, b)
        idx = index_lesen(tmp)
        p("Index: 10 Zeilen mit Ticker, Datum, Anhang und Zeichenzahl",
          len(idx) == 10 and idx[0]["ticker"] == "AAPL" and idx[0]["exhibit"] == "a-ex99_1.htm" and idx[0]["zeichen"] > 30, idx[:1])
        t = text_lesen(tmp, 320193, idx[0]["accession"])
        p("Text: Klartext mit Tabellenzeile und Ausblick", "Net sales | 94,036" in t and "Outlook" in t, t)
        juengste = texte_der_firma(tmp, 320193, 3)
        p("Texte der Firma: juengste zuerst, hoechstens 3",
          len(juengste) == 3 and juengste[0][0]["filed"] >= juengste[1][0]["filed"] >= juengste[2][0]["filed"],
          [m["filed"] for m, _ in juengste])
        n1 = len(aufrufe)
        b2 = lauf(tmp, hoechstens=0, quartale=8, hole=hole, ticker_zu_cik=tzc, log=lambda *_: None,
                  jetzt=dt.datetime(2026, 9, 4, tzinfo=dt.timezone.utc), warte=False)
        p("Zweiter Lauf am naechsten Tag: beide Firmen frisch, uebersprungen, kein Abruf",
          b2["uebersprungen"] == 2 and b2["firmen"] == 0 and len(aufrufe) == n1, b2)
        b3 = lauf(tmp, hoechstens=0, quartale=8, hole=hole, ticker_zu_cik=tzc, log=lambda *_: None,
                  jetzt=dt.datetime(2026, 10, 3, tzinfo=dt.timezone.utc), warte=False)
        p("Dritter Lauf nach 30 Tagen: geprueft, alles schon da, nichts neu geholt",
          b3["firmen"] == 2 and b3["texte_da"] == 10 and b3["texte_neu"] == 0, b3)
        b4 = lauf(tmp, hoechstens=0, quartale=8, nur=["AAPL"], hole=hole, ticker_zu_cik=tzc, log=lambda *_: None,
                  jetzt=dt.datetime(2026, 9, 3, tzinfo=dt.timezone.utc), warte=False)
        p("Gezielt: nur Apple, trotz frischem Stand geprueft", b4["firmen"] == 1 and b4["texte_da"] == 8, b4)
        ke._schreibe_json(os.path.join(tmp, "konsens", "firmen_mit_konsens.json"), {"LEER": {}})
        b5 = lauf(tmp, hoechstens=0, quartale=8, hole=hole, ticker_zu_cik={"LEER": 14724}, log=lambda *_: None,
                  jetzt=dt.datetime(2026, 9, 3, tzinfo=dt.timezone.utc), warte=False)
        st = stand_laden(tmp)
        p("Ohne Anhang: das 8-K ohne Anhang 99.1 wird gezaehlt und im Stand als leer gemerkt, das andere abgelegt",
          b5["ohne_exhibit"] == 1 and b5["texte_neu"] == 1 and list(st["14724"]["leer"]) == ["0000014724-26-000001"]
          and not vorhanden(tmp, 14724, "0000014724-26-000001") and vorhanden(tmp, 14724, "0000014724-26-000000"), b5)
        b5b = lauf(tmp, hoechstens=0, quartale=8, hole=hole, ticker_zu_cik={"LEER": 14724}, log=lambda *_: None,
                   jetzt=dt.datetime(2026, 10, 3, tzinfo=dt.timezone.utc), warte=False)
        p("Ohne Anhang, spaeterer Lauf: das leere 8-K wird nicht erneut abgerufen",
          b5b["ohne_exhibit"] == 1 and b5b["texte_da"] == 1 and b5b["texte_neu"] == 0, b5b)
        ke._schreibe_json(os.path.join(tmp, "konsens", "firmen_mit_konsens.json"), {"AAPL": {}, "BF-B": {}})
        m = speichern(tmp, 1, "T", "0000000001-26-000001", "2026-01-01", "2025-12-31", "x.htm", "A" * (TEXT_DECKEL + 500))
        speichern(tmp, 2, "T2", "0000000002-26-000001", "2026-01-01", "2025-12-31", "x.htm", "gleicher Text")
        b1 = open(text_pfad(tmp, 2, "0000000002-26-000001"), "rb").read()
        speichern(tmp, 2, "T2", "0000000002-26-000001", "2026-01-01", "2025-12-31", "x.htm", "gleicher Text")
        b2 = open(text_pfad(tmp, 2, "0000000002-26-000001"), "rb").read()
        p("Ablage ist byte-gleich bei gleichem Text (kein Zeitstempel im gzip)", b1 == b2 and text_lesen(tmp, 2, "0000000002-26-000001") == "gleicher Text")
        p("Deckel: langer Text wird gekuerzt (Kopf plus Kennzahlfenster) und als gekuerzt vermerkt",
          m["gekuerzt"] and m["zeichen"] <= TEXT_DECKEL + 200, m)
        efts = {"hits": {"hits": [
            {"_id": "0001193125-26-200001:d1ex991.htm", "_source": {"file_type": "EX-99.1", "file_date": "2026-08-05", "period_ending": "2026-06-30"}},
            {"_id": "0001193125-26-200001:d1.htm", "_source": {"file_type": "6-K", "file_date": "2026-08-05"}},
            {"_id": "0001193125-26-100001:d2ex991.htm", "_source": {"file_type": "EX-99.1", "file_date": "2026-05-06", "period_ending": "2026-03-31"}},
            {"_id": "0001193125-26-100002:d3ex991.htm", "_source": {"file_type": "EX-99.1", "file_date": "2026-05-20", "period_ending": None}},
            {"_id": "0001193125-26-200009:d9ex991.htm", "_source": {"file_type": "EX-99.1", "file_date": "2026-08-20", "period_ending": "2026-06-30"}},
            {"_id": "0001193125-26-050001:d4ex992.htm", "_source": {"file_type": "EX-99.2", "file_date": "2026-02-10"}},
            {"_id": "0001193125-26-000001:graphic.jpg", "_source": {"file_type": "GRAPHIC", "file_date": "2026-01-10"}}]}}
        tr = sechs_k_treffer(efts)
        p("6-K-Treffer: Anhaenge und Hauptdokument, keine Grafiken", len(tr) == 6 and tr[0]["accession"] == "0001193125-26-200001", tr)
        ergebnis_html = ("<html><body><p>Ambev reports second quarter 2026 results. Net revenue reached R$ 20,500 million, up 8%. "
                         "Net income was R$ 3,200 million; EBITDA R$ 9,100 million; EPS R$ 0.20 per share. "
                         "Revenue in Brazil US$ 1,100 million, Canada US$ 400 million, R$ 500 million, R$ 600 million, R$ 700 million. "
                         "Three months ended June 30, 2026.</p>" + "<p>More text about the quarter and revenue.</p>" * 40 + "</body></html>")
        dividende_html = "<html><body><p>Notice of dividend payment. The board approved a dividend of R$ 0.10 per share payable in July.</p>" + "<p>x</p>" * 300 + "</body></html>"
        ja, pr = ist_ergebnismitteilung(ergebnis_html, "abevpr2q26_6k.htm")
        nein, _ = ist_ergebnismitteilung(dividende_html)
        hv_html = "<html><body><p>EXHIBIT A.I - COMMENTS FROM THE OFFICERS (as Item 2 to Exhibit C)</p>" + ergebnis_html
        nein2, _ = ist_ergebnismitteilung(hv_html, "ex99-1.htm")
        _, bericht = ist_ergebnismitteilung(ergebnis_html, "abevitr2q26_6k.htm")
        p("Erkennung: Ergebnismitteilung ja, Dividendenmeldung nein, Hauptversammlungskommentar nein, Pressemitteilung vor Bericht",
          ja and not nein and not nein2 and pr > bericht, (pr, bericht))
        circular_html = ("<html><body><p>NOTICE OF 2026 ANNUAL GENERAL AND SPECIAL MEETING OF SHAREHOLDERS AND MANAGEMENT "
                         "INFORMATION CIRCULAR</p><p>Dear Shareholder, you are invited to the meeting. The business of the "
                         "meeting includes receipt of the audited consolidated financial statements and the management's "
                         "discussion and analysis for the year, the election of directors and the appointment of auditors.</p>"
                         + ergebnis_html)
        nein3, _ = ist_ergebnismitteilung(circular_html, "ex99-2.htm")
        proxy_html = ergebnis_html.replace("Revenue", "Revenue from enterprise proxy network services", 1)
        ja2, _ = ist_ergebnismitteilung(proxy_html, "ex99-1.htm")
        p("Erkennung: Hauptversammlungs-Circular nein, das Wort proxy als Produkt stoert nicht", (not nein3) and ja2, (nein3, ja2))
        tal_html = ("<html><body><p>TAL Education Group Announces Unaudited Financial Results for the Second Fiscal Quarter "
                    "and Issues Notice of Annual General Meeting</p>" + ergebnis_html)
        ja3, _ = ist_ergebnismitteilung(tal_html, "ex99-1.htm")
        mda_html = ("<html><body><p>Management's Discussion and Analysis for the three months ended June 30, 2026.</p>"
                    "<p>Further details are in the Information Circular and the Annual Information Form.</p>" + ergebnis_html)
        ja4, _ = ist_ergebnismitteilung(mda_html, "ex99-2.htm")
        vertrag_html = ("<html><body><p>Exhibit 99.2 EXECUTION VERSION CREDIT AGREEMENT dated as of May 7, 2026 by and among "
                        "the Borrower and the Lenders.</p>" + ergebnis_html)
        nein4, _ = ist_ergebnismitteilung(vertrag_html, "ex99-2.htm")
        deckblatt = ("<html><body><p>FORM 6-K Report of Foreign Private Issuer. This report on Form 6-K shall be deemed "
                     "incorporated by reference into the registration statement on Form F-3 and the prospectus therein. "
                     "Indicate by check mark whether the registrant by furnishing the information is also thereby furnishing "
                     "the information to the Commission pursuant to Rule 12g3-2(b) under the Securities Exchange Act of 1934. "
                     "Yes No X</p><p>Quarterly Report</p>" + ergebnis_html)
        ja5, _ = ist_ergebnismitteilung(deckblatt, "q12026.htm")
        p("Erkennung: Ergebnis samt Einladung ja, Bericht mit Verweis auf das Circular ja, Kreditvertrag nein, "
          "Formularkopf mit Prospekt-Floskel stoert nicht", ja3 and ja4 and (not nein4) and ja5, (ja3, ja4, nein4, ja5))
        peso_html = ("<html><body><p>Grupo Ejemplo reports second quarter 2026 results. Revenues reached Ps. 236,152 million "
                     "in the three months ended June 30, 2026, net income was Ps. 12,345 million and EBITDA Ps. 90,123 million; "
                     "net income per share Ps. 0.45. Revenues in the second quarter grew 7 percent, net income rose 9 percent, "
                     "total revenues of 1,234 million pesos in Colombia and 987 million pesos in Peru.</p>"
                     + "<p>The company serves customers in many markets and continues to invest in its network.</p>" * 40
                     + "</body></html>")
        ja6, _ = ist_ergebnismitteilung(peso_html, "ex99-1.htm")
        _, pr2 = ist_ergebnismitteilung(ergebnis_html, "a03312025q1pressrelease.htm")
        _, fs2 = ist_ergebnismitteilung(ergebnis_html, "a03312025q1fs.htm")
        _, mda2 = ist_ergebnismitteilung(ergebnis_html, "a03312025q1mda.htm")
        p("Erkennung: Betraege in Pesos zaehlen; Pressemitteilung vor MD&A vor Abschluss derselben Einreichung",
          ja6 and pr2 > mda2 > fs2, (ja6, pr2, mda2, fs2))

        suchen = []

        def hole6(url):
            if "efts.sec.gov" in url:
                suchen.append(url)
                return json.dumps(efts).encode("utf-8")
            if "d4ex992" in url or "d3ex991" in url:
                return dividende_html.encode("utf-8")
            if "d9ex991" in url:
                return (ergebnis_html * 3).encode("utf-8")  # derselbe Inhalt als Quartalsbericht, schwaecher als die Mitteilung? nein: mehr Treffer
            return ergebnis_html.encode("utf-8")
        e6 = sechs_k_ergebnisse(1565025, hole6, dt.date(2026, 9, 4), log=lambda *_: None, warte=False)
        p("6-K-Ergebnisse: alle Suchbegriffe abgefragt, je Periode nur ein Text, Dividendenmeldungen verworfen, juengste zuerst",
          len(suchen) == len(SECHS_K_SUCHEN) and len(e6) == 2 and {x[1] for x in e6} == {"2026-06-30", "2026-03-31"}
          and e6[0][2] in ("0001193125-26-200001", "0001193125-26-200009") and e6[1][2] == "0001193125-26-100001",
          [(x[0], x[1], x[2]) for x in e6])
        riesig = {"hits": {"hits": [{"_id": "0001193125-26-300001:agm.htm", "_source": {"file_type": "6-K", "file_date": "2026-05-26", "period_ending": "2026-06-30"}}]}}
        riesen_html = "<html><body>" + "<p>Net revenue R$ 20,500 million in the quarter, net income R$ 3,200 million.</p>" * 6000 + "</body></html>"
        e7 = sechs_k_ergebnisse(1565025, lambda url: json.dumps(riesig).encode("utf-8") if "efts" in url else riesen_html.encode("utf-8"),
                                dt.date(2026, 9, 4), log=lambda *_: None, warte=False)
        p("6-K-Ergebnisse: Riesendokumente (Berichtshefte, Hauptversammlung) werden verworfen", e7 == [], e7)
        stand6 = stand_laden(tmp)
        stand6["1565025"] = {"ticker": "ABEV", "accessions": [], "vollstaendig": True, "zeit": "2026-09-03T00:00:00+00:00"}
        stand_schreiben(tmp, stand6)
        b7 = lauf_6k(tmp, hole=hole6, log=lambda *_: None, jetzt=dt.datetime(2026, 9, 4, tzinfo=dt.timezone.utc), warte=False)
        p("6-K-Lauf: Firma ohne 8-K bekommt ihre Ergebnis-6-Ks, Stand merkt sie",
          b7["firmen"] == 1 and b7["texte_neu"] == 2 and vorhanden(tmp, 1565025, "0001193125-26-100001")
          and len(stand_laden(tmp)["1565025"]["sechs_k"]["accessions"]) == 2, b7)
        b8 = lauf_6k(tmp, hole=hole6, log=lambda *_: None, jetzt=dt.datetime(2026, 9, 5, tzinfo=dt.timezone.utc), warte=False)
        p("6-K-Lauf am naechsten Tag: uebersprungen", b8["uebersprungen"] == 1 and b8["firmen"] == 0, b8)
        b6 = lauf(tmp, hoechstens=1, quartale=8, hole=hole, ticker_zu_cik=tzc, log=lambda *_: None,
                  jetzt=dt.datetime(2026, 11, 3, tzinfo=dt.timezone.utc), warte=False)
        p("Portion: hoechstens eine Firma je Lauf, Abbruchgrund genannt",
          b6["firmen"] == 1 and b6["abbruch"] == "Portion voll", b6)
    print("Alles bestanden." if fehler == 0 else f"{fehler} Fehler.")
    return fehler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--daten", default="daten")
    ap.add_argument("--hoechstens", type=int, default=1200)
    ap.add_argument("--quartale", type=int, default=QUARTALE)
    ap.add_argument("--ticker", default="", help="nur diese Ticker, mit Beistrich getrennt")
    ap.add_argument("--modus", default="archiv", choices=["archiv", "6k", "probe6k", "probe8k"])
    ap.add_argument("--frisch", type=int, default=FRISCH_TAGE, help="6k: Firmen mit juengerem Stand ueberspringen (0 = alle neu)")
    ap.add_argument("--selbsttest", action="store_true")
    a = ap.parse_args()
    if a.selbsttest:
        return selbsttest()
    nur = [t for t in a.ticker.split(",") if t.strip()] or None
    if a.modus == "probe6k":
        for tck in (nur or []):
            probe_6k(tck)
        return 0
    if a.modus == "probe8k":
        for tck in (nur or []):
            probe_8k(tck)
        return 0
    if a.modus == "6k":
        b = lauf_6k(a.daten, hoechstens=a.hoechstens, quartale=a.quartale, nur=nur, frisch_tage=a.frisch)
        return 1 if b["fehler"] and not b["firmen"] else 0
    b = lauf(a.daten, hoechstens=a.hoechstens, quartale=a.quartale, nur=nur)
    return 1 if b["fehler"] and not b["firmen"] else 0


if __name__ == "__main__":
    sys.exit(main())
