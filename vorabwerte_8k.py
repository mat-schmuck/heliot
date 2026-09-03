# -*- coding: utf-8 -*-
"""Live-Strom der KI-Vorabwerte aus Ergebnis-8-Ks (Gerhards F15).

Gerhards Bedingungen (02.09.2026): Jeder Vorabwert ist UNUEBERSEHBAR
vorlaeufig gekennzeichnet (quelle vorlaeufig_pressemitteilung, status
vorlaeufig oder unsicher) und wird automatisch durch den amtlichen Wert
ersetzt, sobald der Quartalsbericht im SEC-Archiv steht, mit Protokoll der
Abweichung. Mathias am 03.09.2026: kein Push je Vorabwert, nur die Datei;
Push nur, wenn der Lauf selbst ausfaellt.

Ablauf (Modus strom, alle 30 Minuten werktags, cron-job.org):
  1. Die neuesten 8-Ks der SEC (Atom-Feed getcurrent, seitenweise bis zum
     Stand des letzten Laufs), nur Firmen aus dem Konsens-Bestand.
  2. Je Kandidat die Kopfdaten der Einreichung (index-headers): nur Item
     2.02 (Results of Operations), dazu die amtliche Annahmezeit der SEC.
  3. Anhang 99.1 als Text, gekuerzt wie in der Messung vom 03.09.2026.
  4. Modellkette ministral-14b-2512, mistral-medium-2604, mistral-small-2603
     (Messung 03.09.2026: die ersten beiden fehlerfrei an 30 Faellen).
  5. Plausibilitaet gegen das Vorjahresquartal aus dem amtlichen Archiv
     (Erstfassung): Umsatz mehr als 50 Prozent daneben, Nettogewinn oder
     EPS um mehr als das Zehnfache daneben, bereinigte statt amtliche
     Zahlen oder ein Periodenende, das nicht zum 8-K passt, heisst unsicher.
  6. Ablage im privaten Datenrepo unter vorabwerte/<Jahr>/, eine Datei je
     8-K, dazu register.jsonl und stand.json.
Modus abgleich (einmal taeglich): offene Vorabwerte gegen companyfacts
pruefen; liegt die Erstfassung des Quartals vor, wird der Eintrag auf
status ersetzt gesetzt, die amtlichen Werte und die Abweichung in Prozent
kommen in die Datei und nach abgleich.jsonl.

Aufruf (nur im Actions-Lauf: braucht SEC_USER_AGENT, MISTRAL_API_KEY,
DATEN_TOKEN; NTFY_TOPIC fuer Ausfall-Pushes):
  python vorabwerte_8k.py --daten daten --modus strom [--stunden 6] [--hoechstens 40]
  python vorabwerte_8k.py --daten daten --modus abgleich
  python vorabwerte_8k.py --modus probe --cik 320193 --accession 0000320193-26-000045
  python vorabwerte_8k.py --selbsttest
"""
import argparse
import datetime as dt
import glob
import io
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET

import konsens_einfrieren as ke

KETTE = ["ministral-14b-2512", "mistral-medium-2604", "mistral-small-2603"]
FEED = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&count=100&output=atom&start={start}"
ATOM = "{http://www.w3.org/2005/Atom}"
HOECHSTENS_SEITEN = 10
QUELLE = "vorlaeufig_pressemitteilung"
UMSATZ_TOLERANZ = 0.5           # mehr als 50 Prozent neben dem Vorjahresquartal heisst unsicher
GEWINN_FAKTOR = 10.0            # Nettogewinn und EPS: mehr als das Zehnfache daneben heisst unsicher
PERIODE_HOECHSTENS_TAGE = 75    # das gemeldete Quartalsende muss zum 8-K passen (Messung 03.09.2026)


# ---------------------------------------------------------------------------
# SEC: Feed, Kopfdaten, Zeiten
# ---------------------------------------------------------------------------

def _utc(s):
    """ISO-Zeit mit Zeitzone nach UTC; ohne Zeitzone gilt UTC."""
    d = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)


def akzeptanz_utc(roh14):
    """ACCEPTANCE-DATETIME der SEC (JJJJMMTThhmmss, New Yorker Zeit) als
    UTC-ISO; ohne Zeitzonendatenbank (Windows ohne tzdata) None."""
    try:
        from zoneinfo import ZoneInfo
        ny = ZoneInfo("America/New_York")
    except Exception:  # noqa
        return None
    d = dt.datetime.strptime(roh14, "%Y%m%d%H%M%S").replace(tzinfo=ny)
    return d.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat()


def feed_eintraege(xml_text):
    """[(accession, cik, name, form, updated_utc, index_url)] eines Atom-Feeds
    der neuesten Einreichungen; 8-K/A und Fremdformen werden ausgelassen."""
    wurzel = ET.fromstring(xml_text)
    raus = []
    for e in wurzel.findall(ATOM + "entry"):
        titel = (e.findtext(ATOM + "title") or "").strip()
        link = e.find(ATOM + "link")
        href = link.get("href") if link is not None else ""
        updated = (e.findtext(ATOM + "updated") or "").strip()
        m_form = re.match(r"^(8-K(?:/A)?)\s+-\s+(.+?)\s+\((\d{10})\)", titel)
        m_link = re.search(r"/edgar/data/(\d+)/(\d{18})/(\d{10}-\d{2}-\d{6})-index\.htm", href)
        if not m_form or not m_link:
            continue
        form, name = m_form.group(1), m_form.group(2)
        cik, accession = int(m_link.group(1)), m_link.group(3)
        if form != "8-K":
            continue
        raus.append((accession, cik, name, form, _utc(updated).isoformat(), href))
    return raus


def neue_8ks(seit_utc, hole, hoechstens_seiten=HOECHSTENS_SEITEN, log=print):
    """Alle 8-Ks des Feeds, die juenger als seit_utc sind, seitenweise."""
    raus, seit = [], _utc(seit_utc)
    for seite in range(hoechstens_seiten):
        xml_text = hole(FEED.format(start=seite * 100)).decode("utf-8", "replace")
        eintraege = feed_eintraege(xml_text)
        if not eintraege:
            break
        aelter = 0
        for acc, cik, name, form, upd, href in eintraege:
            if _utc(upd) > seit:
                raus.append((acc, cik, name, form, upd, href))
            else:
                aelter += 1
        if aelter == len(eintraege):
            break
    log(f"Feed: {len(raus)} 8-K(s) seit {seit.isoformat()}")
    return raus


def kopfdaten(text):
    """ITEM INFORMATION und ACCEPTANCE-DATETIME aus der index-headers-Seite."""
    # Die SEC schreibt die Kopfdaten teils als SGML-Tags (<ACCEPTANCE-DATETIME>),
    # teils mit Doppelpunkt; beide Formen gelten.
    items = [x.strip() for x in re.findall(r"ITEM INFORMATION[>:]\s*(.+)", text)]
    m = re.search(r"ACCEPTANCE-DATETIME[>:]\s*(\d{14})", text)
    f = re.search(r"FILED AS OF DATE[>:]\s*(\d{8})", text)
    roh = m.group(1) if m else None
    filed = f"{f.group(1)[:4]}-{f.group(1)[4:6]}-{f.group(1)[6:]}" if f else None
    return {"items": items, "akzeptanz_et": roh, "akzeptanz_utc": akzeptanz_utc(roh) if roh else None,
            "filed": filed, "ergebnis": any("results of operations" in i.lower() for i in items)}


# ---------------------------------------------------------------------------
# Plausibilitaet und Abgleich gegen das amtliche Archiv
# ---------------------------------------------------------------------------

def vorjahreswerte(zeilen, periodenende, toleranz_tage=20):
    """Erstfassung des Quartals ein Jahr vor periodenende (Ende bis
    toleranz_tage daneben, wegen 52/53-Wochen-Jahren)."""
    try:
        ziel = dt.date.fromisoformat(periodenende).replace(year=dt.date.fromisoformat(periodenende).year - 1)
    except ValueError:
        return {}
    raus = {}
    for z in zeilen:
        if z.get("typ") != "Q" or z.get("kennzahl") not in ("umsatz", "nettogewinn", "eps_verwaessert"):
            continue
        try:
            ende = dt.date.fromisoformat(z["end"])
        except (ValueError, TypeError, KeyError):
            continue
        if abs((ende - ziel).days) <= toleranz_tage and z.get("wert_erst") is not None:
            raus[z["kennzahl"]] = z["wert_erst"]
    return raus


def amtliche_werte(zeilen, periodenende, toleranz_tage=6):
    """Erstfassung der drei Kennzahlen des gemeldeten Quartals, sobald sie
    im Archiv steht (Ende bis toleranz_tage daneben)."""
    try:
        ziel = dt.date.fromisoformat(periodenende)
    except (ValueError, TypeError):
        return {}
    raus = {}
    for z in zeilen:
        if z.get("typ") != "Q" or z.get("kennzahl") not in ("umsatz", "nettogewinn", "eps_verwaessert"):
            continue
        try:
            ende = dt.date.fromisoformat(z["end"])
        except (ValueError, TypeError, KeyError):
            continue
        if abs((ende - ziel).days) <= toleranz_tage and z.get("wert_erst") is not None:
            raus[z["kennzahl"]] = z["wert_erst"]
    return raus


def _abw(ist, soll):
    if ist is None or soll is None:
        return None
    try:
        ist, soll = float(ist), float(soll)
    except (TypeError, ValueError):
        return None
    if soll == 0:
        return None
    return abs(ist - soll) / abs(soll)


def plausibilitaet(werte, vorjahr, filing_datum):
    """Liefert (status, gruende). status vorlaeufig oder unsicher."""
    gruende = []
    if werte.get("gaap") is False:
        gruende.append("Modell meldet bereinigte statt amtliche Zahlen")
    pe = werte.get("periodenende")
    try:
        tage = (dt.date.fromisoformat(filing_datum) - dt.date.fromisoformat(pe)).days
        if tage < 0 or tage > PERIODE_HOECHSTENS_TAGE:
            gruende.append(f"Periodenende {pe} passt nicht zum 8-K vom {filing_datum} ({tage} Tage)")
    except (ValueError, TypeError):
        gruende.append("Periodenende fehlt oder unlesbar")
    abw = {}
    if vorjahr:
        if vorjahr.get("umsatz") == 0 and (werte.get("umsatz") or 0) != 0:
            gruende.append("Vorjahresquartal ohne Umsatz")
        a = _abw(werte.get("umsatz"), vorjahr.get("umsatz"))
        if a is not None:
            abw["umsatz"] = round(a, 4)
            if a > UMSATZ_TOLERANZ:
                gruende.append(f"Umsatz {a * 100:.0f} Prozent neben dem Vorjahresquartal")
        for k in ("nettogewinn", "eps_verwaessert"):
            ist, vj = werte.get(k), vorjahr.get(k)
            if ist is None or vj is None:
                continue
            try:
                ist, vj = float(ist), float(vj)
            except (TypeError, ValueError):
                continue
            if vj != 0:
                faktor = abs(ist) / abs(vj) if abs(vj) > 0 else None
                abw[k] = round(_abw(ist, vj), 4)
                if faktor is not None and (faktor > GEWINN_FAKTOR or faktor < 1.0 / GEWINN_FAKTOR) and abs(ist - vj) > 1e-9:
                    gruende.append(f"{k} um mehr als das Zehnfache neben dem Vorjahresquartal")
    status = "unsicher" if gruende else "vorlaeufig"
    return status, gruende, abw


def abgleich_eintrag(eintrag, amtlich):
    """Setzt den amtlichen Wert ein und protokolliert die Abweichung."""
    werte = eintrag.get("werte") or {}
    abweichung = {}
    for k in ("umsatz", "nettogewinn", "eps_verwaessert"):
        if k in amtlich:
            a = _abw(werte.get(k), amtlich[k])
            abweichung[k] = None if a is None else (round(a * 100, 2) if a != float("inf") else None)
    eintrag["status"] = "ersetzt"
    eintrag["amtlich"] = amtlich
    eintrag["abweichung_prozent"] = abweichung
    eintrag["ersetzt_am"] = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    return eintrag


# ---------------------------------------------------------------------------
# Verarbeitung eines 8-K
# ---------------------------------------------------------------------------

def hauptticker(bestand, ticker_zu_cik):
    """CIK -> Ticker; bei mehreren Tickern derselben Firma (BF-A/BF-B, WLY/WLYB,
    Vorzugsaktien) gewinnt der Haupt-Ticker, das ist der erste in der SEC-Liste
    (company_tickers.json ist nach Marktkapitalisierung geordnet)."""
    rang = {str(k).upper(): i for i, k in enumerate(ticker_zu_cik)}
    raus, bester = {}, {}
    for t in bestand:
        t = str(t).upper()
        c = ticker_zu_cik.get(t)
        if not c:
            continue
        c = int(c)
        r = rang.get(t, 10 ** 9)
        if c not in raus or r < bester[c]:
            raus[c], bester[c] = t, r
    return raus


def bestand_ciks(daten, ticker_zu_cik):
    """CIK -> Ticker der Firmen mit Konsens (nur diese bekommen Vorabwerte)."""
    bestand = ke._json(os.path.join(daten, "konsens", "firmen_mit_konsens.json"), {})
    return hauptticker(bestand, ticker_zu_cik)


def verarbeite(cik, accession, name, filing_utc, hole, frage, kette, log=print, firma_laden=None):
    """Ein 8-K bis zur fertigen Vorabwert-Datei (ohne Ablage)."""
    import messung_8k as m8k
    ordner = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}"
    eintrag = {"quelle": QUELLE, "status": None, "cik": cik, "accession": accession, "name": name,
               "filing_utc": filing_utc, "zeitstempel_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
               "hinweise": []}
    try:
        kopf = kopfdaten(hole(ordner + f"/{accession}-index-headers.htm").decode("utf-8", "replace"))
    except Exception as e:  # noqa
        kopf = {"items": [], "akzeptanz_et": None, "akzeptanz_utc": None, "filed": None, "ergebnis": None}
        eintrag["hinweise"].append(f"Kopfdaten nicht lesbar: {str(e)[:120]}")
    if not filing_utc and kopf.get("filed"):
        filing_utc = kopf["filed"] + "T00:00:00+00:00"
        eintrag["filing_utc"] = filing_utc
    eintrag.update({"items": kopf["items"], "sec_akzeptanz_et": kopf["akzeptanz_et"], "sec_akzeptanz_utc": kopf["akzeptanz_utc"]})
    if kopf["ergebnis"] is False:
        eintrag["status"] = "kein_ergebnis_8k"
        return eintrag
    try:
        exhibit, text = m8k.exhibit_text(cik, accession)
    except Exception as e:  # noqa
        exhibit, text = None, None
        eintrag["hinweise"].append(f"Exhibit nicht lesbar: {str(e)[:120]}")
    eintrag["exhibit"] = exhibit
    if not text or len(text) < 1500:
        eintrag["status"] = "kein_exhibit"
        return eintrag
    if kopf["ergebnis"] is None and not re.search(r"item\s+2\.02", text, re.I):
        eintrag["hinweise"].append("Items unbekannt und kein Item 2.02 im Text")
    gekuerzt = m8k.text_kuerzen(text)
    eintrag["text_zeichen"] = len(text)
    antwort, modell_ok = None, None
    for modell in kette:
        r = frage(modell, gekuerzt)
        if r.get("status") == 200 and r.get("geparst"):
            antwort, modell_ok = r, modell
            break
        eintrag["hinweise"].append(f"{modell}: {', '.join(r.get('hinweise') or []) or 'keine Antwort'}")
    if antwort is None:
        eintrag["status"] = "fehlgeschlagen"
        return eintrag
    g = antwort["geparst"]
    werte = {k: g.get(k) for k in ("periodenende", "umsatz", "nettogewinn", "eps_verwaessert", "gaap")}
    belege = {k: g.get(k) for k in ("beleg_umsatz", "beleg_nettogewinn", "beleg_eps")}
    eintrag.update({"modell": modell_ok, "modell_laut_antwort": antwort.get("modell_laut_antwort"),
                    "dauer_s": antwort.get("dauer_s"), "werte": werte, "belege": belege})
    u = antwort.get("usage") or {}
    pr = m8k.preis(modell_ok)
    if pr and u:
        eintrag["kosten_usd"] = round((u.get("prompt_tokens", 0) * pr[0] + u.get("completion_tokens", 0) * pr[1]) / 1e6, 5)
    vorjahr = {}
    if firma_laden is not None:
        try:
            vorjahr = vorjahreswerte(firma_laden(cik), werte.get("periodenende") or "")
        except Exception as e:  # noqa
            eintrag["hinweise"].append(f"Vorjahr nicht pruefbar: {str(e)[:120]}")
    status, gruende, abw = plausibilitaet(werte, vorjahr, (filing_utc or "")[:10])
    eintrag.update({"status": status, "vorjahr": vorjahr or None, "abweichung_vorjahr": abw or None,
                    "pruefung": gruende or ["Vorjahresquartal nicht pruefbar"] if not vorjahr and not gruende else gruende})
    return eintrag


def _pfad(daten, eintrag):
    jahr = (eintrag.get("filing_utc") or eintrag.get("zeitstempel_utc") or "0000")[:4]
    return os.path.join(daten, "vorabwerte", jahr, f"{int(eintrag['cik']):010d}-{eintrag['accession']}.json")


def _register(daten, eintrag, art):
    with io.open(os.path.join(daten, "vorabwerte", "register.jsonl" if art == "vorabwert" else "abgleich.jsonl"),
                 "a", encoding="utf-8") as f:
        w = eintrag.get("werte") or {}
        f.write(json.dumps({"zeit": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
                            "ticker": eintrag.get("ticker"), "cik": eintrag.get("cik"), "accession": eintrag.get("accession"),
                            "status": eintrag.get("status"), "periodenende": w.get("periodenende"),
                            "umsatz": w.get("umsatz"), "nettogewinn": w.get("nettogewinn"), "eps": w.get("eps_verwaessert"),
                            "modell": eintrag.get("modell"), "abweichung_prozent": eintrag.get("abweichung_prozent")},
                           ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Laeufe
# ---------------------------------------------------------------------------

def _zeilen_lader():
    """Erstfassungs-Zeilen je CIK aus companyfacts, je Lauf einmal je Firma."""
    import fundament_lauf as fl
    import fundament_normalisieren as fn
    cache = {}

    def laden(cik):
        if cik not in cache:
            _, zeilen = fn.normalisiere(fl.companyfacts(int(cik)))
            cache[cik] = zeilen
        return cache[cik]
    return laden


def lauf_strom(daten, stunden=6, hoechstens=0, kette=None, hole=None, frage=None, firma_laden=None,
               ticker_zu_cik=None, log=print, jetzt=None):
    import messung_8k as m8k
    kette = kette or KETTE
    jetzt = jetzt or dt.datetime.now(dt.timezone.utc)
    if hole is None:
        import fundament_lauf as fl
        hole = fl.hole
    if frage is None:
        bremse = m8k.Bremse()

        def frage(modell, text):
            return m8k.mistral_frage(modell, text, bremse)
    if firma_laden is None:
        firma_laden = _zeilen_lader()
    if ticker_zu_cik is None:
        import fundament_lauf as fl
        ticker_zu_cik = fl.ticker_zu_cik()
    stand_pfad = os.path.join(daten, "vorabwerte", "stand.json")
    stand = ke._json(stand_pfad, {})
    seit = stand.get("zuletzt") or (jetzt - dt.timedelta(hours=stunden)).isoformat()
    gesehen = {a: z for a, z in (stand.get("gesehen") or {}).items()
               if z >= (jetzt - dt.timedelta(days=5)).isoformat()}
    ciks = bestand_ciks(daten, ticker_zu_cik)
    bilanz = {"zeit": jetzt.replace(microsecond=0).isoformat(), "modus": "strom", "feed": 0, "kandidaten": 0,
              "vorlaeufig": 0, "unsicher": 0, "kein_ergebnis": 0, "kein_exhibit": 0, "fehlgeschlagen": 0,
              "kosten_usd": 0.0, "abbruch": None}
    try:
        alle = neue_8ks(seit, hole, log=log)
    except Exception as e:  # noqa
        bilanz["abbruch"] = f"SEC-Feed nicht lesbar: {str(e)[:160]}"
        alle = []
    bilanz["feed"] = len(alle)
    kandidaten = [x for x in alle if x[1] in ciks and x[0] not in gesehen]
    kandidaten.sort(key=lambda x: x[4])
    if hoechstens:
        kandidaten = kandidaten[:hoechstens]
    bilanz["kandidaten"] = len(kandidaten)
    log(f"Kandidaten im Konsens-Bestand: {len(kandidaten)}")
    juengste = seit
    for acc, cik, name, form, upd, href in kandidaten:
        e = verarbeite(cik, acc, name, upd, hole, frage, kette, log=log, firma_laden=firma_laden)
        e["ticker"] = ciks.get(cik)
        st = e["status"]
        if st in ("vorlaeufig", "unsicher", "fehlgeschlagen"):
            ke._schreibe_json(_pfad(daten, e), e)
            _register(daten, e, "vorabwert")
        bilanz[{"vorlaeufig": "vorlaeufig", "unsicher": "unsicher", "fehlgeschlagen": "fehlgeschlagen",
                "kein_exhibit": "kein_exhibit"}.get(st, "kein_ergebnis")] += 1
        bilanz["kosten_usd"] = round(bilanz["kosten_usd"] + (e.get("kosten_usd") or 0), 5)
        gesehen[acc] = upd
        juengste = max(juengste, upd)
        w = e.get("werte") or {}
        log(f"  {e.get('ticker')} {acc} {st}: Umsatz {w.get('umsatz')}, Nettogewinn {w.get('nettogewinn')}, "
            f"EPS {w.get('eps_verwaessert')}, Periode {w.get('periodenende')}, Modell {e.get('modell')}"
            + (f"; {'; '.join(e.get('pruefung') or [])}" if st == "unsicher" else ""))
    # Der Stand wandert nur bis zur juengsten VERARBEITETEN Einreichung, damit
    # ein Abbruch keine 8-Ks verliert; ohne Kandidaten bis zum Feed-Stand.
    if not bilanz["abbruch"]:
        if not kandidaten and alle:
            juengste = max(juengste, max(x[4] for x in alle))
        stand.update({"zuletzt": juengste, "gesehen": gesehen})
        ke._schreibe_json(stand_pfad, stand)
    with io.open(os.path.join(daten, "vorabwerte", "laeufe.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(bilanz, ensure_ascii=False) + "\n")
    log(f"Ergebnis: {bilanz}")
    if bilanz["abbruch"] or bilanz["fehlgeschlagen"]:
        ke.push("Vorabwerte: Lauf gestoert", bilanz["abbruch"] or f"{bilanz['fehlgeschlagen']} 8-K(s) ohne Antwort der Modellkette")
    return bilanz


def lauf_abgleich(daten, firma_laden=None, log=print, hoechstens_alter_tage=120):
    """Offene Vorabwerte gegen das amtliche Archiv pruefen und ersetzen."""
    if firma_laden is None:
        firma_laden = _zeilen_lader()
    bilanz = {"zeit": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(), "modus": "abgleich",
              "offen": 0, "ersetzt": 0, "weiter_offen": 0, "fehler": 0}
    grenze = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=hoechstens_alter_tage)).isoformat()
    for pfad in sorted(glob.glob(os.path.join(daten, "vorabwerte", "*", "*.json"))):
        e = ke._json(pfad, None)
        if not e or e.get("status") not in ("vorlaeufig", "unsicher"):
            continue
        if (e.get("filing_utc") or "") < grenze:
            continue
        bilanz["offen"] += 1
        pe = (e.get("werte") or {}).get("periodenende")
        if not pe:
            bilanz["weiter_offen"] += 1
            continue
        try:
            amt = amtliche_werte(firma_laden(e["cik"]), pe)
        except Exception as ex:  # noqa
            bilanz["fehler"] += 1
            log(f"  {e.get('ticker')}: Archiv nicht lesbar: {str(ex)[:120]}")
            continue
        if "umsatz" in amt or "nettogewinn" in amt:
            abgleich_eintrag(e, amt)
            ke._schreibe_json(pfad, e)
            _register(daten, e, "abgleich")
            bilanz["ersetzt"] += 1
            log(f"  {e.get('ticker')} {e.get('accession')} ersetzt; Abweichung {e.get('abweichung_prozent')}")
        else:
            bilanz["weiter_offen"] += 1
    with io.open(os.path.join(daten, "vorabwerte", "laeufe.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(bilanz, ensure_ascii=False) + "\n")
    log(f"Ergebnis: {bilanz}")
    return bilanz


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

_ATOM = """<?xml version="1.0" encoding="ISO-8859-1" ?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>Latest Filings - Thu, 03 Sep 2026 07:00:00 EDT</title>
<entry><title>8-K - APPLE INC. (0000320193) (Filer)</title>
<link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/320193/000032019326000045/0000320193-26-000045-index.htm"/>
<summary type="html">&lt;b&gt;Filed:&lt;/b&gt; 2026-07-30 &lt;b&gt;AccNo:&lt;/b&gt; 0000320193-26-000045 &lt;b&gt;Size:&lt;/b&gt; 2 MB</summary>
<updated>2026-07-30T16:31:22-04:00</updated>
<category scheme="https://www.sec.gov/" label="form type" term="8-K"/>
<id>urn:tag:sec.gov,2008:accession-number=0000320193-26-000045</id></entry>
<entry><title>8-K/A - SOMEONE ELSE CORP (0000123456) (Filer)</title>
<link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/123456/000012345626000001/0000123456-26-000001-index.htm"/>
<summary type="html">x</summary><updated>2026-07-30T16:20:00-04:00</updated>
<category scheme="https://www.sec.gov/" label="form type" term="8-K/A"/>
<id>urn:tag:sec.gov,2008:accession-number=0000123456-26-000001</id></entry>
<entry><title>8-K - OLD CO (0000999999) (Filer)</title>
<link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/999999/000099999926000002/0000999999-26-000002-index.htm"/>
<summary type="html">x</summary><updated>2026-07-29T09:00:00-04:00</updated>
<category scheme="https://www.sec.gov/" label="form type" term="8-K"/>
<id>urn:tag:sec.gov,2008:accession-number=0000999999-26-000002</id></entry>
</feed>"""

_HEADERS = """<html><body><pre>
CONFORMED SUBMISSION TYPE:\t8-K
PUBLIC DOCUMENT COUNT:\t\t3
CONFORMED PERIOD OF REPORT:\t20260730
ITEM INFORMATION:\t\tResults of Operations and Financial Condition
ITEM INFORMATION:\t\tFinancial Statements and Exhibits
FILED AS OF DATE:\t\t20260730
<ACCEPTANCE-DATETIME>20260730163122
</pre></body></html>"""


def selbsttest() -> int:
    import tempfile
    fehler = 0

    def p(name, ok, extra=""):
        nonlocal fehler
        print(f"  {'ok  ' if ok else 'FEHL'} {name}{(' ' + str(extra)) if extra else ''}")
        if not ok:
            fehler += 1

    e = feed_eintraege(_ATOM)
    p("Feed: 8-K/A ausgelassen, CIK und Accession aus dem Link, Zeit in UTC",
      len(e) == 2 and e[0][0] == "0000320193-26-000045" and e[0][1] == 320193 and e[0][2] == "APPLE INC."
      and e[0][4] == "2026-07-30T20:31:22+00:00", e)
    ht = hauptticker({"WLYB": {}, "WLY": {}, "FCELB": {}, "AAPL": {}},
                     {"AAPL": 320193, "WLY": 107140, "FCEL": 886128, "WLYB": 107140, "FCELB": 886128})
    p("Haupt-Ticker je CIK: WLY vor WLYB, FCELB bleibt, wenn FCEL nicht im Bestand ist",
      ht == {107140: "WLY", 886128: "FCELB", 320193: "AAPL"}, ht)
    st7, gr7, abw7 = plausibilitaet({"periodenende": "2026-06-30", "umsatz": 450000, "nettogewinn": -20.687e6,
                                     "eps_verwaessert": -4.88, "gaap": True},
                                    {"umsatz": 0, "nettogewinn": -14.439e6, "eps_verwaessert": -3.71}, "2026-09-02")
    p("Vorjahr ohne Umsatz: unsicher mit klarem Grund, keine Unendlich-Zahl in der Ablage",
      st7 == "unsicher" and any("ohne Umsatz" in g for g in gr7) and abw7.get("umsatz") is None
      and json.dumps(abw7, allow_nan=False) is not None, (st7, gr7, abw7))
    seiten = []

    def hole(url):
        seiten.append(url)
        return _ATOM.encode("utf-8") if len(seiten) == 1 else b"<feed xmlns='http://www.w3.org/2005/Atom'></feed>"
    n = neue_8ks("2026-07-30T00:00:00+00:00", hole, log=lambda *_: None)
    p("Feed seitenweise: nur juengere als der Stand, Ende bei leerer Seite",
      len(n) == 1 and n[0][0] == "0000320193-26-000045" and len(seiten) == 2)
    k = kopfdaten(_HEADERS.replace("<ACCEPTANCE-DATETIME>", "ACCEPTANCE-DATETIME:\t"))
    p("Kopfdaten: Items und Annahmezeit gelesen, Ergebnis-8-K erkannt",
      k["ergebnis"] and len(k["items"]) == 2 and k["akzeptanz_et"] == "20260730163122"
      and k["akzeptanz_utc"] in (None, "2026-07-30T20:31:22+00:00"), k)
    p("Kopfdaten: ohne Results of Operations kein Ergebnis-8-K",
      kopfdaten("ITEM INFORMATION:\tOther Events\n")["ergebnis"] is False)
    k2 = kopfdaten(_HEADERS)
    p("Kopfdaten: SGML-Tag-Form der Annahmezeit und das Filing-Datum werden gelesen",
      k2["akzeptanz_et"] == "20260730163122" and k2["filed"] == "2026-07-30" and k2["ergebnis"], k2)

    zeilen = [{"typ": "Q", "kennzahl": "umsatz", "end": "2025-06-30", "wert_erst": 20.31e9},
              {"typ": "Q", "kennzahl": "nettogewinn", "end": "2025-06-30", "wert_erst": 3.175e9},
              {"typ": "Q", "kennzahl": "eps_verwaessert", "end": "2025-06-30", "wert_erst": 5.41},
              {"typ": "Y", "kennzahl": "umsatz", "end": "2025-12-31", "wert_erst": 80e9},
              {"typ": "Q", "kennzahl": "umsatz", "end": "2026-06-30", "wert_erst": 23.609e9},
              {"typ": "Q", "kennzahl": "nettogewinn", "end": "2026-06-30", "wert_erst": 3.311e9}]
    vj = vorjahreswerte(zeilen, "2026-06-30")
    p("Vorjahresquartal: drei Kennzahlen, Jahreswert ausgelassen", vj == {"umsatz": 20.31e9, "nettogewinn": 3.175e9, "eps_verwaessert": 5.41}, vj)
    p("Vorjahresquartal: 52/53-Wochen-Toleranz", vorjahreswerte(zeilen, "2026-07-05").get("umsatz") == 20.31e9)
    st, gr, abw = plausibilitaet({"periodenende": "2026-06-30", "umsatz": 7.568e9, "nettogewinn": 0.779e9,
                                  "eps_verwaessert": 1.34, "gaap": True}, vj, "2026-07-15")
    p("Plausibilitaet: Progressive-Monat statt Quartal heisst unsicher (Umsatz 63 Prozent daneben)",
      st == "unsicher" and any("Umsatz" in g for g in gr) and abw["umsatz"] > 0.6, gr)
    st2, gr2, _ = plausibilitaet({"periodenende": "2026-06-30", "umsatz": 23.609e9, "nettogewinn": 3.311e9,
                                  "eps_verwaessert": 5.67, "gaap": True}, vj, "2026-07-15")
    p("Plausibilitaet: stimmiger Fall bleibt vorlaeufig", st2 == "vorlaeufig" and not gr2)
    st3, gr3, _ = plausibilitaet({"periodenende": "2026-06-30", "umsatz": 23.609e9, "nettogewinn": 3.311e9,
                                  "eps_verwaessert": 5.67, "gaap": False}, vj, "2026-07-15")
    p("Plausibilitaet: bereinigte Zahlen heissen unsicher", st3 == "unsicher")
    st4, gr4, _ = plausibilitaet({"periodenende": "2026-04-03", "umsatz": 12.472e9, "nettogewinn": 3.924e9,
                                  "eps_verwaessert": 0.91, "gaap": True}, {}, "2026-07-28")
    p("Plausibilitaet: Periodenende 116 Tage vor dem 8-K heisst unsicher", st4 == "unsicher" and any("passt nicht" in g for g in gr4))
    st5, gr5, _ = plausibilitaet({"periodenende": "2026-06-30", "umsatz": 23.609e9, "nettogewinn": -11.033e9,
                                  "eps_verwaessert": -2.16, "gaap": True},
                                 {"umsatz": 22e9, "nettogewinn": -2.918e9, "eps_verwaessert": -0.67}, "2026-07-23")
    p("Plausibilitaet: Intel-Verlust um das 3,8-Fache bleibt vorlaeufig", st5 == "vorlaeufig", gr5)
    st6, gr6, _ = plausibilitaet({"periodenende": "2026-06-30", "umsatz": 12.56e6, "nettogewinn": 3.401e6,
                                  "eps_verwaessert": 0.8, "gaap": True},
                                 {"umsatz": 11.08e9, "nettogewinn": 3.125e9, "eps_verwaessert": 0.72}, "2026-07-16")
    p("Plausibilitaet: Einheitenfehler (Tausend statt Milliarden) heisst unsicher", st6 == "unsicher" and len(gr6) >= 2)

    amt = amtliche_werte(zeilen, "2026-06-30")
    e2 = abgleich_eintrag({"werte": {"umsatz": 7.568e9, "nettogewinn": 3.311e9, "eps_verwaessert": None}, "status": "unsicher"}, amt)
    p("Abgleich: amtlicher Wert eingesetzt, Abweichung in Prozent, EPS ohne Sollwert bleibt None",
      e2["status"] == "ersetzt" and e2["amtlich"]["umsatz"] == 23.609e9 and round(e2["abweichung_prozent"]["umsatz"]) == 68
      and e2["abweichung_prozent"]["nettogewinn"] == 0.0 and "eps_verwaessert" not in e2["abweichung_prozent"])

    with tempfile.TemporaryDirectory() as tmp:
        ke._schreibe_json(os.path.join(tmp, "konsens", "firmen_mit_konsens.json"), {"AAPL": {}, "PGR": {}})
        aufrufe = []

        def hole2(url):
            aufrufe.append(url)
            if "getcurrent" in url:
                return _ATOM.encode("utf-8") if url.endswith("start=0") else b"<feed xmlns='http://www.w3.org/2005/Atom'></feed>"
            if url.endswith("-index-headers.htm"):
                return _HEADERS.replace("<ACCEPTANCE-DATETIME>", "ACCEPTANCE-DATETIME:\t").encode("utf-8")
            raise RuntimeError("unbekannte Adresse " + url)

        def frage2(modell, text):
            return {"status": 200, "geparst": {"periodenende": "2026-06-27", "umsatz": 94.036e9, "nettogewinn": 23.434e9,
                                               "eps_verwaessert": 1.57, "gaap": True, "beleg_umsatz": "Total net sales 94,036",
                                               "beleg_nettogewinn": "Net income 23,434", "beleg_eps": "Diluted 1.57"},
                    "usage": {"prompt_tokens": 9000, "completion_tokens": 120}, "dauer_s": 2.1, "hinweise": [],
                    "modell_laut_antwort": modell}

        def firma2(cik):
            return [{"typ": "Q", "kennzahl": "umsatz", "end": "2025-06-28", "wert_erst": 85.8e9},
                    {"typ": "Q", "kennzahl": "nettogewinn", "end": "2025-06-28", "wert_erst": 21.4e9},
                    {"typ": "Q", "kennzahl": "eps_verwaessert", "end": "2025-06-28", "wert_erst": 1.40}]
        import messung_8k as m8k
        alt_exhibit = m8k.exhibit_text
        m8k.exhibit_text = lambda cik, acc: ("ex991.htm", "Item 2.02 Results " + "Apple reported revenue. " * 200)
        try:
            b = lauf_strom(tmp, stunden=48, hole=hole2, frage=frage2, firma_laden=firma2,
                           ticker_zu_cik={"AAPL": 320193, "PGR": 80661}, log=lambda *_: None,
                           jetzt=dt.datetime(2026, 7, 31, 12, 0, tzinfo=dt.timezone.utc))
        finally:
            m8k.exhibit_text = alt_exhibit
        p("Strom: ein Kandidat aus dem Bestand, vorlaeufig abgelegt, Kosten gezaehlt",
          b["feed"] == 2 and b["kandidaten"] == 1 and b["vorlaeufig"] == 1 and b["kosten_usd"] > 0, b)
        datei = glob.glob(os.path.join(tmp, "vorabwerte", "2026", "*.json"))
        p("Strom: Datei je 8-K mit Kennzeichnung, Belegen, Annahmezeit und Vorjahr",
          len(datei) == 1 and (lambda d: d["quelle"] == QUELLE and d["status"] == "vorlaeufig" and d["ticker"] == "AAPL"
                               and d["belege"]["beleg_eps"] == "Diluted 1.57" and d["sec_akzeptanz_et"] == "20260730163122"
                               and d["vorjahr"]["umsatz"] == 85.8e9 and d["modell"] == KETTE[0])(ke._json(datei[0], {})))
        stand = ke._json(os.path.join(tmp, "vorabwerte", "stand.json"), {})
        p("Strom: Stand und Register geschrieben",
          stand.get("zuletzt") == "2026-07-30T20:31:22+00:00" and "0000320193-26-000045" in stand.get("gesehen", {})
          and os.path.exists(os.path.join(tmp, "vorabwerte", "register.jsonl")))
        b2 = lauf_strom(tmp, stunden=48, hole=hole2, frage=frage2, firma_laden=firma2,
                        ticker_zu_cik={"AAPL": 320193}, log=lambda *_: None,
                        jetzt=dt.datetime(2026, 7, 31, 13, 0, tzinfo=dt.timezone.utc))
        p("Strom: zweiter Lauf verarbeitet dasselbe 8-K nicht noch einmal", b2["kandidaten"] == 0)

        def kette_tot(modell, text):
            return {"status": 429, "geparst": None, "hinweise": ["429 beim Versuch 8", "aufgegeben"]}
        ke._schreibe_json(os.path.join(tmp, "vorabwerte", "stand.json"), {"zuletzt": "2026-07-29T00:00:00+00:00", "gesehen": {}})
        m8k.exhibit_text = lambda cik, acc: ("ex991.htm", "Item 2.02 Results " + "Apple reported revenue. " * 200)
        try:
            b3 = lauf_strom(tmp, stunden=48, hole=hole2, frage=kette_tot, firma_laden=firma2,
                            ticker_zu_cik={"AAPL": 320193}, log=lambda *_: None,
                            jetzt=dt.datetime(2026, 7, 31, 14, 0, tzinfo=dt.timezone.utc))
        finally:
            m8k.exhibit_text = alt_exhibit
        p("Strom: erschoepfte Kette heisst fehlgeschlagen (Push-Fall), Datei mit Hinweisen",
          b3["fehlgeschlagen"] == 1 and any("ministral-14b" in h for h in ke._json(datei[0], {}).get("hinweise", [])))

        def firma3(cik):
            return firma2(cik) + [{"typ": "Q", "kennzahl": "umsatz", "end": "2026-06-27", "wert_erst": 94.036e9},
                                  {"typ": "Q", "kennzahl": "nettogewinn", "end": "2026-06-27", "wert_erst": 23.5e9}]
        ke._schreibe_json(datei[0], dict(ke._json(datei[0], {}), status="vorlaeufig",
                                         werte={"periodenende": "2026-06-27", "umsatz": 94.036e9, "nettogewinn": 23.434e9,
                                                "eps_verwaessert": 1.57, "gaap": True}, filing_utc="2026-07-30T20:31:22+00:00"))
        b4 = lauf_abgleich(tmp, firma_laden=firma3, log=lambda *_: None)
        d4 = ke._json(datei[0], {})
        p("Abgleich: Vorabwert durch die Erstfassung ersetzt, Abweichung protokolliert",
          b4["ersetzt"] == 1 and d4["status"] == "ersetzt" and d4["amtlich"]["nettogewinn"] == 23.5e9
          and 0.2 < d4["abweichung_prozent"]["nettogewinn"] < 0.4
          and os.path.exists(os.path.join(tmp, "vorabwerte", "abgleich.jsonl")), b4)
        b5 = lauf_abgleich(tmp, firma_laden=firma3, log=lambda *_: None)
        p("Abgleich: ersetzte Eintraege werden nicht erneut geprueft", b5["offen"] == 0)
    print("\n" + ("Alles bestanden." if fehler == 0 else f"{fehler} Fehler."))
    return fehler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--daten", default="")
    ap.add_argument("--modus", default="strom", choices=["strom", "abgleich", "probe"])
    ap.add_argument("--stunden", type=float, default=6)
    ap.add_argument("--hoechstens", type=int, default=0)
    ap.add_argument("--modelle", default="", help="Kette mit Beistrich, leer = Vorgabe")
    ap.add_argument("--cik", type=int, default=0)
    ap.add_argument("--accession", default="")
    ap.add_argument("--selbsttest", action="store_true")
    a = ap.parse_args()
    if a.selbsttest:
        sys.exit(1 if selbsttest() else 0)
    kette = [m.strip() for m in a.modelle.split(",") if m.strip()] or KETTE
    if a.modus == "probe":
        if not (a.cik and a.accession):
            print("--cik und --accession fehlen.")
            sys.exit(2)
        import fundament_lauf as fl
        import messung_8k as m8k
        bremse = m8k.Bremse()
        e = verarbeite(a.cik, a.accession, "", None, fl.hole, lambda m, t: m8k.mistral_frage(m, t, bremse), kette,
                       firma_laden=_zeilen_lader())
        print(json.dumps(e, ensure_ascii=False, indent=1))
        sys.exit(0)
    if not a.daten:
        print("--daten fehlt.")
        sys.exit(2)
    if a.modus == "strom":
        b = lauf_strom(a.daten, stunden=a.stunden, hoechstens=a.hoechstens, kette=kette)
        sys.exit(1 if b["abbruch"] else 0)
    b = lauf_abgleich(a.daten)
    sys.exit(0)


if __name__ == "__main__":
    main()
