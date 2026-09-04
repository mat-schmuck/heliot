# -*- coding: utf-8 -*-
"""Messung fuer Gerhards KI-Abfrage: Kann ein Mistral-Modell eine Frage wie
"Apple hat gute Zahlen, trotzdem ist der Kurs schwach, warum, zeige mir das
Quartal ueber Quartal" aus UNSEREN Daten beantworten?

Arbeitsteilung: Die Zahlen rechnet dieses Skript selbst (amtliche Quartale aus
dem SEC-Archiv, Konsens und Ueberraschung aus der EODHD-Historie, Kursreaktion
um den Meldetag aus den Yahoo-Kursen) und gibt sie dem Modell als fertige
Tabelle. Die Pressetexte (Archiv pressetexte/) dienen der Deutung. Jede
Antwort wird als Datei abgelegt (Datenrepo, messungen/frage-<ticker>-<zeit>/),
damit sie Wort fuer Wort gegengelesen werden kann. Nur im Actions-Lauf
(Secrets SEC_USER_AGENT, MISTRAL_API_KEY, DATEN_TOKEN).
"""
import argparse
import datetime as dt
import io
import json
import os
import sys
import time

FRAGE_VORGABE = ("Apple hat super Zahlen gemeldet, trotzdem ist der Kurs schwach. Warum? "
                 "Zeige mir das Quartal ueber Quartal.")
MODELLE_VORGABE = ["mistral-small-2603", "mistral-medium-2604"]
QUARTALE = 8
TEXT_JE_MITTEILUNG = 25000
KOPF_JE_MITTEILUNG = 12000
GROQ_KEY = os.environ.get("GROQ_API_KEY", "").strip()
WEBSUCHE_MODELL = "openai/gpt-oss-20b"   # Groqs eingebautes Werkzeug browser_search am Grundmodell; eigenes Kontingent
WEBSUCHE_ABSTAND_S = 2.5                  # (1.000 je Tag, 8.000 Tokens je Minute), das der Podcatcher nicht nutzt.
                                          # groq/compound antwortet in der Gratisstufe auf jede Suche mit 413 (Probe 04.09.2026).
YAHOO_RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
NACHRICHTEN_HOECHSTENS = 20

WEBSUCHE_AUFTRAG = (
    "Du bist ein Rechercheur fuer Boersennachrichten. Suche im Netz nach Nachrichten und Analystenkommentaren "
    "zu der Firma und beantworte nur diese zwei Fragen aus dem, was du gefunden hast: Erstens, welche Gruende "
    "nennen Nachrichten und Analysten fuer die Kursreaktion nach den juengsten Quartalszahlen? Zweitens, welche "
    "Gruende nennen sie fuer die Kursentwicklung der letzten Wochen? Nenne zu jeder Aussage die Quelle im Klartext, "
    "also den Namen des Mediums oder der Website und das Datum des Artikels, in Klammern hinter dem Satz; keine "
    "Fussnoten, keine Verweismarken, keine Zitatnummern. Gib bei Kurszielen ausdruecklich an, ob sie gehoben oder "
    "gesenkt wurden und von welchem auf welchen Wert. Erfinde nichts; was du nicht findest, sagst du ausdruecklich. "
    "Antworte auf Deutsch in ganzen Saetzen, ohne Markdown, ohne Tabellen, hoechstens 300 Woerter."
)

AUFTRAG = (
    "Du bist ein nuechterner Finanzanalyst. Du beantwortest die Frage des Nutzers AUSSCHLIESSLICH aus den "
    "mitgelieferten Daten: einer Zahlentabelle je Quartal (amtliche Zahlen aus dem SEC-Archiv, Analystenkonsens, "
    "gemeldetes bereinigtes Ergebnis, Ueberraschung, Kursreaktion um den Meldetag) und den Pressemitteilungen "
    "der Firma zu diesen Quartalen. Regeln: Alle Zahlen stammen aus der Tabelle; aus den Pressemitteilungen "
    "nimmst du nur Aussagen des Managements, Segmente, Sondereffekte und den Ausblick, mit Angabe des Quartals. "
    "Liegt ein Abschnitt Nachrichtenlage vor, darfst du daraus Gruende fuer die Kursentwicklung nennen, jeweils mit "
    "Quelle und Datum, wie dort angegeben. "
    "Erfinde nichts; was in den Daten nicht steht, nennst du ausdruecklich als fehlend. Vermutungen kennzeichnest "
    "du mit dem Wort Vermutung. Antworte auf Deutsch, in ganzen Saetzen, ohne Markdown, ohne Tabellen, ohne "
    "Aufzaehlungszeichen; die Antwort wird mit einem Screenreader vorgelesen. Aufbau: erstens eine Kurzantwort in "
    "zwei bis drei Saetzen; zweitens Quartal ueber Quartal, je Quartal ein Absatz vom aeltesten zum juengsten, mit "
    "Umsatz und Ergebnis je Aktie, Veraenderung zum Vorjahresquartal, Konsens und Ueberraschung, Kursreaktion und "
    "dem, was das Management sagte; drittens deine Deutung, warum der Kurs trotz guter Zahlen schwach sein koennte, "
    "nur soweit die Daten das hergeben, und jeder Deutungssatz beginnt mit dem Wort Vermutung; viertens, was fuer "
    "eine sichere Antwort fehlt. Die Standard-Risikohinweise am Ende der Pressemitteilungen (Safe Harbor) sind "
    "kein Inhalt und werden nicht als Aussage des Managements gewertet. Datumsangaben der Quartale nimmst du nur "
    "aus der Tabelle, nie aus dem Veroeffentlichungsdatum einer Mitteilung."
)


# ---------------------------------------------------------------------------
# Zahlentabelle
# ---------------------------------------------------------------------------

def _q(zeilen, kennzahl):
    """{periodenende: wert_erst} der Quartalszeilen einer Kennzahl."""
    raus = {}
    for z in zeilen:
        if z.get("typ") == "Q" and z.get("kennzahl") == kennzahl and z.get("end") and z.get("wert_erst") is not None:
            raus[str(z["end"])[:10]] = float(z["wert_erst"])
    return raus


def _vorjahr(werte, ende, toleranz=20):
    try:
        ziel = dt.date.fromisoformat(ende) - dt.timedelta(days=365)
    except ValueError:
        return None
    best = None
    for k, v in werte.items():
        try:
            d = abs((dt.date.fromisoformat(k) - ziel).days)
        except ValueError:
            continue
        if d <= toleranz and (best is None or d < best[0]):
            best = (d, v)
    return best[1] if best else None


def konsens_je_quartal(konsens_zeilen):
    """{periodenende: {eps_ist, eps_konsens, ueberraschung_prozent, meldedatum, zeitpunkt}} aus eps_history."""
    raus = {}
    for z in konsens_zeilen or []:
        if z.get("art") == "eps_history" and z.get("periodenende"):
            raus[str(z["periodenende"])[:10]] = z
    return raus


def kursreaktion(kurse, meldedatum, zeitpunkt):
    """Prozent vom Schluss vor der Meldung bis zum ersten Schluss danach.
    kurse: {datum: schluss} (Handelstage). BeforeMarket: Vortag gegen Meldetag;
    sonst Meldetag gegen den Handelstag danach."""
    if not kurse or not meldedatum:
        return None
    tage = sorted(kurse)
    try:
        m = dt.date.fromisoformat(meldedatum[:10])
    except ValueError:
        return None
    vor_market = (zeitpunkt or "").lower().startswith("before")
    davor = [t for t in tage if dt.date.fromisoformat(t) < m] if vor_market else [t for t in tage if dt.date.fromisoformat(t) <= m]
    danach = [t for t in tage if dt.date.fromisoformat(t) >= m] if vor_market else [t for t in tage if dt.date.fromisoformat(t) > m]
    if not davor or not danach:
        return None
    a, b = kurse[davor[-1]], kurse[danach[0]]
    if not a:
        return None
    return round((b / a - 1) * 100, 2)


def _mrd(x):
    return None if x is None else round(x / 1e9, 3)


def _pz(neu, alt):
    """Veraenderung in Prozent; bei Vorjahr null oder negativ oder Vorzeichenwechsel None,
    denn minus 153 Prozent fuer den Weg von 17 Millionen Verlust zu 9 Millionen Gewinn
    ist Unsinn (Ciena, Messung 04.09.2026)."""
    if neu is None or alt is None or alt <= 0 or neu < 0:
        return None
    return round((neu / alt - 1) * 100, 1)


def _vorzeichen_hinweis(neu, alt):
    if neu is None or alt is None:
        return ""
    if alt < 0 and neu >= 0:
        return " (Vorjahresquartal mit Verlust, jetzt Gewinn)"
    if alt >= 0 and neu < 0:
        return " (Vorjahresquartal mit Gewinn, jetzt Verlust)"
    if alt < 0 and neu < 0:
        return " (Verlust wie im Vorjahresquartal)"
    return ""


def tabelle(zeilen, konsens_zeilen, kurse, quartale=QUARTALE):
    """Liste je Quartal (aeltestes zuerst) mit allen Angaben, dazu die Textform."""
    umsatz, gewinn, eps = _q(zeilen, "umsatz"), _q(zeilen, "nettogewinn"), _q(zeilen, "eps_verwaessert")
    enden = sorted(set(umsatz) | set(eps))[-quartale:]
    k = konsens_je_quartal(konsens_zeilen)
    liste = []
    for e in enden:
        kk = k.get(e) or {}
        # Konsens-Periodenenden koennen um wenige Tage abweichen (Apple 28.06. gegen 30.06.)
        if not kk:
            for ke_, kv in k.items():
                try:
                    if abs((dt.date.fromisoformat(ke_) - dt.date.fromisoformat(e)).days) <= 7:
                        kk = kv
                        break
                except ValueError:
                    pass
        z = {"periodenende": e,
             "umsatz_mrd": _mrd(umsatz.get(e)), "umsatz_vorjahr_prozent": _pz(umsatz.get(e), _vorjahr(umsatz, e)),
             "nettogewinn_mrd": _mrd(gewinn.get(e)), "nettogewinn_vorjahr_prozent": _pz(gewinn.get(e), _vorjahr(gewinn, e)),
             "nettogewinn_hinweis": _vorzeichen_hinweis(gewinn.get(e), _vorjahr(gewinn, e)),
             "eps_amtlich": eps.get(e), "eps_vorjahr_prozent": _pz(eps.get(e), _vorjahr(eps, e)),
             "eps_hinweis": _vorzeichen_hinweis(eps.get(e), _vorjahr(eps, e)),
             "eps_konsens": kk.get("eps_konsens"), "eps_gemeldet_bereinigt": kk.get("eps_ist"),
             "ueberraschung_prozent": kk.get("ueberraschung_prozent"), "meldedatum": kk.get("meldedatum"),
             "zeitpunkt": kk.get("zeitpunkt"),
             "kursreaktion_prozent": kursreaktion(kurse, kk.get("meldedatum"), kk.get("zeitpunkt"))}
        # Basis der Ueberraschung fraglich: der Dienst fuehrt als gemeldeten Wert den amtlichen, der Konsens
        # ist aber meist bereinigt (Ciena: minus 88 Prozent Ueberraschung bei GAAP 0,06 gegen Konsens 0,52)
        z["ueberraschung_fraglich"] = bool(z["eps_amtlich"] is not None and z["eps_gemeldet_bereinigt"] is not None
                                           and abs(z["eps_amtlich"] - z["eps_gemeldet_bereinigt"]) < 0.005
                                           and z["ueberraschung_prozent"] is not None and abs(z["ueberraschung_prozent"]) > 25)
        liste.append(z)
    return liste, tabelle_text(liste)


def _f(x, nach=2):
    if x is None:
        return "keine Angabe"
    return f"{x:.{nach}f}".replace(".", ",")


def tabelle_text(liste):
    zeilen = ["Zahlentabelle je Quartal (aeltestes zuerst). Umsatz und Nettogewinn in Milliarden US-Dollar, amtliche "
              "Erstfassung aus dem SEC-Archiv; Konsens und gemeldetes bereinigtes Ergebnis je Aktie laut Analystendienst; "
              "Kursreaktion vom Schluss vor der Meldung bis zum ersten Schluss danach."]
    for z in liste:
        zeilen.append(
            f"Quartal bis {z['periodenende']}: Umsatz {_f(z['umsatz_mrd'], 3)} Mrd ({_f(z['umsatz_vorjahr_prozent'], 1)} Prozent zum Vorjahresquartal); "
            f"Nettogewinn {_f(z['nettogewinn_mrd'], 3)} Mrd ({_f(z['nettogewinn_vorjahr_prozent'], 1)} Prozent{z.get('nettogewinn_hinweis', '')}); "
            f"Ergebnis je Aktie amtlich {_f(z['eps_amtlich'])} ({_f(z['eps_vorjahr_prozent'], 1)} Prozent{z.get('eps_hinweis', '')}); "
            f"Konsens {_f(z['eps_konsens'])}, gemeldet bereinigt {_f(z['eps_gemeldet_bereinigt'])}, "
            f"Ueberraschung {_f(z['ueberraschung_prozent'], 1)} Prozent"
            + (" (Basis fraglich: der Dienst stellt hier den amtlichen Wert einem bereinigten Konsens gegenueber, "
               "die Ueberraschung ist nicht belastbar)" if z.get("ueberraschung_fraglich") else "")
            + f"; gemeldet am {z['meldedatum'] or 'keine Angabe'} "
            f"({z['zeitpunkt'] or 'Zeitpunkt unbekannt'}); Kursreaktion {_f(z['kursreaktion_prozent'])} Prozent.")
    return "\n".join(zeilen)


# ---------------------------------------------------------------------------
# Texte und Auftrag
# ---------------------------------------------------------------------------

def texte_block(texte, je=TEXT_JE_MITTEILUNG, kopf=KOPF_JE_MITTEILUNG):
    """texte: [(meta, text)] juengste zuerst; Rueckgabe aeltestes zuerst, gekuerzt."""
    import messung_8k as m8k
    teile = []
    for meta, text in sorted(texte, key=lambda mt: mt[0].get("filed") or ""):
        t = m8k.text_kuerzen(text, limit=je, kopf=kopf)
        teile.append(f"=== Pressemitteilung, veroeffentlicht am {meta.get('filed')} (das gemeldete Quartal steht im Text) ===\n{t}")
    return "\n\n".join(teile)


def eingabe(frage, tab_text, texte_text):
    return (f"Frage des Nutzers: {frage}\n\n{tab_text}\n\nPressemitteilungen der Firma zu diesen Quartalen:\n\n{texte_text}")


def _zahlen(text):
    """Zahlenwerte eines Textes (Beistrich oder Punkt als Dezimalzeichen, Tausenderzeichen entfernt);
    Jahreszahlen und Datumsteile werden ausgelassen. Rueckgabe: (werte, prozentwerte)."""
    import re
    werte, prozent = set(), set()
    t = re.sub(r"\d{4}-\d{2}-\d{2}", " ", text)
    for m in re.finditer(r"(?<![\d.,])(\d{1,3}(?:[.,]\d{3})+|\d+)(?:[.,](\d+))?\s*(Prozent|percent|%)?", t):
        ganz, nach, pz = m.group(1), m.group(2), m.group(3)
        # Tausenderzeichen nur, wenn die Gruppen dreistellig sind und ein Dezimalteil folgt oder gar keiner
        roh = ganz
        if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", ganz):
            if nach is None and ganz.count(",") + ganz.count(".") == 1 and len(ganz.split(",")[-1] if "," in ganz else ganz.split(".")[-1]) == 3:
                # 94,930 ist im Deutschen 94 Komma 930 (Milliarden), im Englischen 94.930 tausend: beide Lesarten aufnehmen
                a = float(ganz.replace(",", ".")) if "," in ganz else float(ganz)
                b = float(ganz.replace(",", "").replace(".", ""))
                for w in (a, b):
                    (prozent if pz else werte).add(round(w, 4))
                continue
            roh = ganz.replace(",", "").replace(".", "")
        try:
            w = float(roh + ("." + nach if nach else ""))
        except ValueError:
            continue
        if 1990 <= w <= 2035 and nach is None:
            continue
        (prozent if pz else werte).add(round(w, 4))
    return werte, prozent


def zahlen_pruefen(antwort, tab_text, texte_text):
    """Zahlen der Antwort, die weder in der Tabelle noch in den Pressetexten vorkommen
    (kleine ganze Zahlen bis 31 gelten als Aufzaehlung oder Datum und werden nicht gezaehlt)."""
    a_w, a_p = _zahlen(antwort)
    b_w, b_p = _zahlen(tab_text + "\n" + texte_text)
    belegt = b_w | b_p

    def gedeckt(w):
        if w in belegt:
            return True
        # Rundung: 94,04 deckt 94,036 und 143,76 deckt 143,756 (auf die Stellen der Antwortzahl gerundet)
        s = f"{w:.10f}".rstrip("0").split(".")
        stellen = len(s[1]) if len(s) > 1 else 0
        if stellen == 0:
            return False  # ganze Zahlen nur exakt, sonst deckte 12,6 die 13
        return any(round(b, stellen) == w for b in belegt)
    unbelegt_w = sorted(w for w in a_w if not gedeckt(w) and not (float(w).is_integer() and w <= 31))
    unbelegt_p = sorted(w for w in a_p if not gedeckt(w))
    return {"zahlen_gesamt": len(a_w) + len(a_p), "unbelegt": unbelegt_w, "unbelegt_prozent": unbelegt_p}


def websuche_frage(ticker, name, meldedatum, heute):
    return (f"Firma: {name} (Ticker {ticker}). Juengste Quartalszahlen gemeldet am {meldedatum or 'unbekannt'}. "
            f"Heutiges Datum: {heute}.")


def websuche_groq(ticker, name, meldedatum, heute, log=print):
    """Nachrichtenlage ueber Groqs compound-mini (eingebaute Websuche). Rueckgabe
    {text, quellen, usage, dauer_s, status, hinweise}; ohne Schluessel status 0."""
    import messung_8k as m8k
    if not GROQ_KEY:
        return {"text": "", "quellen": [], "usage": None, "dauer_s": 0, "status": 0, "hinweise": ["GROQ_API_KEY fehlt"]}
    koerper = {"model": WEBSUCHE_MODELL, "temperature": 0, "max_completion_tokens": 1500,
               "tools": [{"type": "browser_search"}], "reasoning_effort": "low",
               "messages": [{"role": "system", "content": WEBSUCHE_AUFTRAG},
                            {"role": "user", "content": websuche_frage(ticker, name, meldedatum, heute)}]}
    hinweise = []
    for versuch in range(4):
        t0 = time.time()
        status, kopf, roh = m8k._anfrage("https://api.groq.com/openai/v1/chat/completions", koerper, key=GROQ_KEY)
        dauer = time.time() - t0
        if status == 429 or status >= 500:
            hinweise.append(f"{status} beim Versuch {versuch + 1}")
            try:
                pause = float({str(a).lower(): b for a, b in (kopf or {}).items()}.get("retry-after") or 0)
            except (TypeError, ValueError):
                pause = 0
            time.sleep(min(90, pause) if pause > 0 else 15)
            continue
        if status != 200:
            return {"text": "", "quellen": [], "usage": None, "dauer_s": round(dauer, 1), "status": status,
                    "hinweise": hinweise + [f"HTTP {status}: {roh[:300]}"]}
        a = json.loads(roh)
        nachricht = a["choices"][0]["message"]
        quellen = []
        for w in nachricht.get("executed_tools") or []:
            quellen.append({"typ": w.get("type"), "eingabe": (w.get("arguments") or w.get("input") or "")[:300] if isinstance(w.get("arguments") or w.get("input"), str) else str(w.get("arguments") or w.get("input"))[:300],
                            "ausgabe": (w.get("output") or "")[:2000] if isinstance(w.get("output"), str) else str(w.get("output"))[:2000]})
        time.sleep(WEBSUCHE_ABSTAND_S)
        text = markdown_weg((nachricht.get("content") or "").strip())
        seiten = besuchte_seiten(quellen)
        if seiten:
            text += "\nBesuchte Seiten der Suche: " + ", ".join(seiten)
        return {"text": text, "quellen": quellen, "usage": a.get("usage"),
                "dauer_s": round(dauer, 1), "status": 200, "hinweise": hinweise, "modell_laut_antwort": a.get("model"),
                "abbruchgrund": a["choices"][0].get("finish_reason")}
    return {"text": "", "quellen": [], "usage": None, "dauer_s": 0, "status": 0, "hinweise": hinweise + ["aufgegeben"]}


def besuchte_seiten(quellen):
    """Adressen, die das Browser-Werkzeug geoeffnet hat (browser.open mit einer Adresse als id)."""
    import re
    raus = []
    for q in quellen or []:
        for u in re.findall(r"https?://[^\s\"'}]+", str(q.get("eingabe") or "")):
            u = u.rstrip(",.")
            if u not in raus:
                raus.append(u)
    return raus


def markdown_weg(text):
    import re
    text = re.sub(r"\u3010[^\u3011]*\u3011", "", text)  # Verweismarken des Browser-Werkzeugs wie 【0†L26-L34】
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"^\s*#+\s*", "", text, flags=re.M)
    text = re.sub(r"^\s*[-*]\s+", "", text, flags=re.M)
    return text.replace("**", "").replace("`", "").strip()


def rss_lesen(xml):
    """[(datum ISO, titel, quelle)] aus einem RSS-2.0-Feed (Yahoo Finance), ohne Fremdbibliothek."""
    import email.utils
    import html
    import re
    raus = []
    for item in re.findall(r"<item>(.*?)</item>", xml, re.S):
        def feld(name):
            m = re.search(rf"<{name}>(.*?)</{name}>", item, re.S)
            return html.unescape(re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", m.group(1), flags=re.S)).strip() if m else ""
        titel, link, datum = feld("title"), feld("link"), feld("pubDate")
        try:
            datum_iso = email.utils.parsedate_to_datetime(datum).date().isoformat()
        except (TypeError, ValueError):
            datum_iso = datum[:16]
        quelle = re.sub(r"^https?://(www\.)?", "", link).split("/")[0] if link else ""
        if titel:
            raus.append((datum_iso, titel, quelle))
    return raus


def nachrichten_yahoo(ticker, hole=None, hoechstens=NACHRICHTEN_HOECHSTENS, heute=None):
    """Schlagzeilen der letzten Tage aus dem Yahoo-Finance-Feed je Ticker (gratis, ohne Schluessel);
    Rueckfall, wenn die Websuche nichts liefert. Rueckgabe {text, eintraege, status, hinweise}."""
    if hole is None:
        def hole(url):
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (heliot)"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", "replace")
    try:
        xml = hole(YAHOO_RSS.format(ticker=ticker))
    except Exception as e:  # noqa
        return {"text": "", "eintraege": [], "status": 0, "hinweise": [f"Feed nicht lesbar: {str(e)[:160]}"]}
    eintraege = rss_lesen(xml)[:hoechstens]
    heute = heute or dt.date.today().isoformat()
    zeilen = [f"Schlagzeilen aus dem Yahoo-Finance-Nachrichtenfeed zu {ticker}, Stand {heute}; nur Ueberschriften, "
              f"keine Volltexte. Zitiere daraus mit Datum und Quelle."]
    for datum, titel, quelle in eintraege:
        zeilen.append(f"{datum}: {titel} (Quelle: {quelle or 'Yahoo Finance'})")
    return {"text": "\n".join(zeilen) if eintraege else "", "eintraege": [{"datum": d, "titel": ti, "quelle": q} for d, ti, q in eintraege],
            "status": 200 if eintraege else 204, "hinweise": [] if eintraege else ["Feed ohne Eintraege"]}


def nachrichtenlage(ticker, name, meldedatum, heute, log=print):
    """Erst die Websuche ueber Groq, bei Fehlschlag oder leerer Antwort der Yahoo-Feed."""
    n = websuche_groq(ticker, name, meldedatum, heute, log=log)
    n["quelle"] = "groq"
    if n.get("status") == 200 and (n.get("text") or "").strip():
        return n
    y = nachrichten_yahoo(ticker, heute=heute)
    y["quelle"] = "yahoo"
    y["hinweise"] = (n.get("hinweise") or []) + [f"Websuche Status {n.get('status')}, Rueckfall auf den Yahoo-Feed"] + (y.get("hinweise") or [])
    return y


def eingabe_mit_nachrichten(frage, tab_text, texte_text, nachrichten_text):
    if not nachrichten_text:
        return eingabe(frage, tab_text, texte_text)
    return (f"Frage des Nutzers: {frage}\n\n{tab_text}\n\nNachrichtenlage (aktuelle Nachrichten mit Quellenangaben; daraus "
            f"darfst du Gruende fuer die Kursentwicklung nennen, jeweils mit Quelle und Datum):\n{nachrichten_text}"
            f"\n\nPressemitteilungen der Firma zu diesen Quartalen:\n\n{texte_text}")


MONATE = {"jaenner": 1, "januar": 1, "februar": 2, "maerz": 3, "märz": 3, "april": 4, "mai": 5, "juni": 6, "juli": 7,
          "august": 8, "september": 9, "oktober": 10, "november": 11, "dezember": 12}


def _quartale_im_absatz(absatz, enden):
    """Periodenenden der Tabelle, die ein Absatz nennt: als ISO-Datum oder als Monat und Jahr
    (auch mit Tag davor, etwa 28. September 2024). Ein Absatz mit dem Meldedatum eines anderen
    Quartals trifft dann kein Tabellenquartal."""
    import re
    gefunden = set()
    for e in enden:
        if e in absatz:
            gefunden.add(e)
    for m in re.finditer(r"(?:\d{1,2}\.\s*)?([A-Za-zäöü]+)\s+(20\d{2})", absatz):
        mon = MONATE.get(m.group(1).lower())
        if not mon:
            continue
        jahr = int(m.group(2))
        for e in enden:
            if int(e[:4]) == jahr and int(e[5:7]) == mon:
                gefunden.add(e)
    return gefunden


def zuordnung_pruefen(antwort, liste):
    """Stehen die Umsatzzahlen in den Absaetzen zum richtigen Quartal? Rueckgabe
    {geprueft, fehler: [(genanntes Quartal, Umsatz im Absatz, Quartal dieses Umsatzes)]}."""
    import re
    enden = [z["periodenende"] for z in liste if z.get("umsatz_mrd") is not None]
    umsatz_zu_ende = {}
    for z in liste:
        u = z.get("umsatz_mrd")
        if u is None:
            continue
        for form in (f"{u:.3f}", f"{u:.2f}", f"{u:.1f}"):
            umsatz_zu_ende.setdefault(form.replace(".", ","), z["periodenende"])
            umsatz_zu_ende.setdefault(form, z["periodenende"])
    geprueft, fehler = 0, []
    for absatz in re.split(r"\n\s*\n|\n", antwort):
        quartale = _quartale_im_absatz(absatz, enden)
        if len(quartale) != 1:
            continue
        q = next(iter(quartale))
        treffer = set()
        for form, e in umsatz_zu_ende.items():
            if re.search(r"(?<![\d,.])" + re.escape(form) + r"(?![\d])", absatz):
                treffer.add(e)
        if not treffer:
            continue
        geprueft += 1
        for e in treffer:
            if e != q:
                fehler.append((q, e))
    return {"geprueft": geprueft, "fehler": fehler}


def modell_fragen(modell, frage_text, bremse):
    import messung_8k as m8k
    koerper = {"model": modell, "temperature": 0, "max_tokens": 3000,
               "messages": [{"role": "system", "content": AUFTRAG}, {"role": "user", "content": frage_text}]}
    hinweise = []
    for versuch in range(6):
        bremse.warten(modell)
        t0 = time.time()
        status, kopf, roh = m8k._anfrage("https://api.mistral.ai/v1/chat/completions", koerper, timeout=600)
        dauer = time.time() - t0
        bremse.merken(modell, kopf)
        if status == 429 or status >= 500:
            hinweise.append(f"{status} beim Versuch {versuch + 1}")
            time.sleep(20 if status == 429 else 10)
            continue
        if status != 200:
            return {"antwort": "", "usage": None, "dauer_s": round(dauer, 1), "status": status,
                    "hinweise": hinweise + [f"HTTP {status}: {roh[:300]}"]}
        a = json.loads(roh)
        return {"antwort": (a["choices"][0]["message"].get("content") or "").strip(), "usage": a.get("usage"),
                "dauer_s": round(dauer, 1), "status": 200, "hinweise": hinweise, "modell_laut_antwort": a.get("model"),
                "abbruchgrund": a["choices"][0].get("finish_reason")}
    return {"antwort": "", "usage": None, "dauer_s": 0, "status": 0, "hinweise": hinweise + ["aufgegeben"]}


# ---------------------------------------------------------------------------
# Lauf
# ---------------------------------------------------------------------------

def kurse_laden(ticker, von, bis):
    """{datum: schluss} ueber yfinance; leer, wenn nichts kommt."""
    try:
        import yfinance as yf
        df = yf.download(ticker, start=von, end=bis, auto_adjust=True, progress=False)
        if df is None or df.empty:
            return {}
        spalte = df["Close"]
        if hasattr(spalte, "columns"):
            spalte = spalte.iloc[:, 0]
        return {str(i)[:10]: float(v) for i, v in spalte.items() if v == v}
    except Exception as e:  # noqa
        print("Kurse nicht geladen:", str(e)[:200])
        return {}


def lauf(daten, ticker, frage, modelle, quartale=QUARTALE, ausgabe=None, log=print, websuche=True):
    import gzip
    import messung_8k as m8k
    import pressetexte as pt
    import vorabwerte_8k as va
    import fundament_lauf as fl
    if not m8k.MISTRAL_KEY:
        raise RuntimeError("MISTRAL_API_KEY fehlt (Secret im Actions-Lauf).")
    if not fl.UA:
        raise RuntimeError("SEC_USER_AGENT fehlt (Secret im Actions-Lauf).")
    ticker = ticker.upper()
    cik = fl.ticker_zu_cik().get(ticker)
    if not cik:
        raise RuntimeError(f"{ticker}: keine CIK in der SEC-Liste")
    zeilen = va._zeilen_lader()(cik)
    kpfad = os.path.join(daten, "eodhd", "konsens", f"{ticker}.json.gz")
    konsens_datei = json.load(gzip.open(kpfad, "rt", encoding="utf-8")) if os.path.exists(kpfad) else {}
    konsens = konsens_datei.get("zeilen", [])
    konsens_name = (konsens_datei.get("kopf") or {}).get("name") or ""
    texte = pt.texte_der_firma(daten, cik, quartale)
    if not texte:
        raise RuntimeError(f"{ticker}: keine Pressetexte im Archiv (zuerst pressetexte.yml mit ticker={ticker} laufen lassen)")
    enden = sorted(_q(zeilen, "umsatz"))[-quartale:]
    von = (dt.date.fromisoformat(enden[0]) - dt.timedelta(days=10)).isoformat() if enden else "2024-01-01"
    kurse = kurse_laden(ticker, von, (dt.date.today() + dt.timedelta(days=1)).isoformat())
    liste, tab_text = tabelle(zeilen, konsens, kurse, quartale)
    texte_text = texte_block(texte)
    nachrichten = None
    if websuche:
        juengst = liste[-1] if liste else {}
        name = konsens_name or ticker
        nachrichten = nachrichtenlage(ticker, name, juengst.get("meldedatum"), dt.date.today().isoformat(), log=log)
        log(f"  Nachrichtenlage ({nachrichten.get('quelle')}): Status {nachrichten.get('status')}, "
            f"{len(nachrichten.get('text') or '')} Zeichen, Hinweise {nachrichten.get('hinweise')}")
    frage_text = eingabe_mit_nachrichten(frage, tab_text, texte_text, (nachrichten or {}).get("text") or "")
    log(f"{ticker} CIK {cik}: {len(zeilen)} amtliche Zeilen, {len(konsens)} Konsens-Zeilen, {len(kurse)} Kurstage, "
        f"{len(texte)} Pressetexte, Eingabe {len(frage_text)} Zeichen")
    ausgabe = ausgabe or os.path.join(daten, "messungen", f"frage-{ticker.lower()}-{dt.datetime.now(dt.timezone.utc):%Y%m%d-%H%M}")
    os.makedirs(ausgabe, exist_ok=True)
    with io.open(os.path.join(ausgabe, "frage.txt"), "w", encoding="utf-8") as f:
        f.write(frage + "\n")
    with io.open(os.path.join(ausgabe, "auftrag.txt"), "w", encoding="utf-8") as f:
        f.write(AUFTRAG + "\n")
    with io.open(os.path.join(ausgabe, "tabelle.txt"), "w", encoding="utf-8") as f:
        f.write(tab_text + "\n")
    with io.open(os.path.join(ausgabe, "tabelle.json"), "w", encoding="utf-8") as f:
        json.dump(liste, f, ensure_ascii=False, indent=1)
    with io.open(os.path.join(ausgabe, "eingabe.txt"), "w", encoding="utf-8") as f:
        f.write(frage_text + "\n")
    if nachrichten is not None:
        with io.open(os.path.join(ausgabe, "nachrichten.txt"), "w", encoding="utf-8") as f:
            f.write((nachrichten.get("text") or "") + "\n")
        with io.open(os.path.join(ausgabe, "nachrichten.json"), "w", encoding="utf-8") as f:
            json.dump({k: v for k, v in nachrichten.items() if k != "text"}, f, ensure_ascii=False, indent=1)
    bremse = m8k.Bremse()
    bilanz = {"zeit": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(), "ticker": ticker,
              "eingabe_zeichen": len(frage_text), "modelle": {},
              "nachrichten": None if nachrichten is None else {k: v for k, v in nachrichten.items() if k not in ("text", "quellen", "eintraege")}}
    for modell in modelle:
        r = modell_fragen(modell, frage_text, bremse)
        u = r.get("usage") or {}
        p = m8k.preis(modell)
        kosten = ((u.get("prompt_tokens", 0) / 1e6 * p[0] + u.get("completion_tokens", 0) / 1e6 * p[1]) if p else None)
        with io.open(os.path.join(ausgabe, f"antwort-{modell}.txt"), "w", encoding="utf-8") as f:
            f.write(r.get("antwort") or "")
        meta = {k: v for k, v in r.items() if k != "antwort"}
        meta["kosten_usd"] = None if kosten is None else round(kosten, 5)
        meta["antwort_zeichen"] = len(r.get("antwort") or "")
        meta["zahlen"] = zahlen_pruefen(r.get("antwort") or "", tab_text, texte_text + "\n" + ((nachrichten or {}).get("text") or ""))
        meta["zuordnung"] = zuordnung_pruefen(r.get("antwort") or "", liste)
        with io.open(os.path.join(ausgabe, f"meta-{modell}.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)
        bilanz["modelle"][modell] = meta
        z = meta["zahlen"]
        log(f"  {modell}: Status {r.get('status')}, {meta['antwort_zeichen']} Zeichen, {r.get('dauer_s')} s, "
            f"Kosten {meta['kosten_usd']} USD, Tokens {u.get('prompt_tokens')}/{u.get('completion_tokens')}, "
            f"Abbruchgrund {r.get('abbruchgrund')}; Zahlen {z['zahlen_gesamt']}, unbelegt {z['unbelegt']}, "
            f"unbelegte Prozent {z['unbelegt_prozent']}; Quartalszuordnung geprueft {meta['zuordnung']['geprueft']}, "
            f"Fehlzuordnungen {meta['zuordnung']['fehler']}")
    with io.open(os.path.join(ausgabe, "bilanz.json"), "w", encoding="utf-8") as f:
        json.dump(bilanz, f, ensure_ascii=False, indent=1)
    log(f"Ablage: {ausgabe}")
    return bilanz


# ---------------------------------------------------------------------------
# Selbsttest (ohne Netz)
# ---------------------------------------------------------------------------

def selbsttest() -> int:
    fehler = 0

    def p(name, ok, extra=""):
        nonlocal fehler
        print(f"  {'ok  ' if ok else 'FEHL'} {name}{(' ' + str(extra)) if extra else ''}")
        if not ok:
            fehler += 1

    zeilen = []
    for i, (ende, u, g, e) in enumerate([("2024-06-29", 85.8e9, 21.4e9, 1.40), ("2024-09-28", 94.9e9, 14.7e9, 0.97),
                                         ("2024-12-28", 124.3e9, 36.3e9, 2.40), ("2025-03-29", 95.4e9, 24.8e9, 1.65),
                                         ("2025-06-28", 94.0e9, 23.4e9, 1.57), ("2025-09-27", 102.5e9, 27.5e9, 1.85),
                                         ("2025-12-27", 143.8e9, 42.0e9, 2.84), ("2026-03-28", 105.0e9, 28.0e9, 1.90),
                                         ("2026-06-27", 100.6e9, 25.0e9, 1.70)]):
        zeilen += [{"typ": "Q", "kennzahl": "umsatz", "end": ende, "wert_erst": u},
                   {"typ": "Q", "kennzahl": "nettogewinn", "end": ende, "wert_erst": g},
                   {"typ": "Q", "kennzahl": "eps_verwaessert", "end": ende, "wert_erst": e}]
    zeilen.append({"typ": "Y", "kennzahl": "umsatz", "end": "2025-09-27", "wert_erst": 416e9})
    konsens = [{"art": "eps_history", "periodenende": "2026-06-30", "eps_ist": 1.72, "eps_konsens": 1.60,
                "ueberraschung_prozent": 7.5, "meldedatum": "2026-07-30", "zeitpunkt": "AfterMarket"},
               {"art": "eps_history", "periodenende": "2026-03-31", "eps_ist": 1.92, "eps_konsens": 1.85,
                "ueberraschung_prozent": 3.8, "meldedatum": "2026-04-30", "zeitpunkt": "BeforeMarket"},
               {"art": "konsens_trend", "periodenende": "2026-09-30", "period": "0q"}]
    kurse = {"2026-07-29": 200.0, "2026-07-30": 202.0, "2026-07-31": 196.0, "2026-08-03": 198.0,
             "2026-04-29": 180.0, "2026-04-30": 175.5, "2026-05-01": 176.0}
    liste, text = tabelle(zeilen, konsens, kurse, 8)
    p("Tabelle: acht Quartale, aeltestes zuerst, Jahreszeile ausgelassen",
      len(liste) == 8 and liste[0]["periodenende"] == "2024-09-28" and liste[-1]["periodenende"] == "2026-06-27", [z["periodenende"] for z in liste])
    j = liste[-1]
    p("Juengstes Quartal: Umsatz in Mrd, Vorjahresvergleich, Konsens trotz Periodenende 30.06. gegen 27.06. zugeordnet",
      j["umsatz_mrd"] == 100.6 and j["umsatz_vorjahr_prozent"] == 7.0 and j["eps_konsens"] == 1.60 and j["eps_gemeldet_bereinigt"] == 1.72, j)
    p("Kursreaktion nach Boersenschluss: Schluss am Meldetag gegen den Tag danach (202 auf 196 = minus 2,97)",
      j["kursreaktion_prozent"] == -2.97, j["kursreaktion_prozent"])
    v = [z for z in liste if z["periodenende"] == "2026-03-28"][0]
    p("Kursreaktion vor Boersenoeffnung: Vortag gegen Meldetag (180 auf 175,5 = minus 2,5)",
      v["kursreaktion_prozent"] == -2.5, v["kursreaktion_prozent"])
    a = liste[0]
    p("Prozent nur bei gleichem Vorzeichen: Verlust zu Gewinn gibt keine Prozentzahl, aber einen Hinweis",
      _pz(9e6, -17e6) is None and _pz(-5e6, 4e6) is None and _pz(20e6, 10e6) == 100.0
      and "Verlust, jetzt Gewinn" in _vorzeichen_hinweis(9e6, -17e6) and _vorzeichen_hinweis(20e6, 10e6) == "")
    lc = [{"periodenende": "2025-05-03", "eps_amtlich": 0.06, "eps_gemeldet_bereinigt": 0.06, "ueberraschung_prozent": -88.1}]
    l2, t2 = tabelle([{"typ": "Q", "kennzahl": "umsatz", "end": "2025-05-03", "wert_erst": 1.126e9},
                      {"typ": "Q", "kennzahl": "eps_verwaessert", "end": "2025-05-03", "wert_erst": 0.06}],
                     [{"art": "eps_history", "periodenende": "2025-05-03", "eps_ist": 0.06, "eps_konsens": 0.52,
                       "ueberraschung_prozent": -88.1, "meldedatum": "2025-06-05", "zeitpunkt": "BeforeMarket"}], {}, 8)
    p("Ueberraschung mit fraglicher Basis (amtlich gleich gemeldet, minus 88 Prozent) wird in der Tabelle gekennzeichnet",
      l2[0]["ueberraschung_fraglich"] and "Basis fraglich" in t2, t2[-260:])
    p("Aeltestes Quartal ohne Vorjahr im Ausschnitt: Vergleich fehlt, kein Absturz",
      a["umsatz_vorjahr_prozent"] is None and a["eps_konsens"] is None, a)
    p("Textform: deutsche Dezimalzeichen, jede Zeile ein Quartal, Hinweis auf fehlende Angaben",
      text.count("Quartal bis") == 8 and "100,600 Mrd" in text and "keine Angabe" in text, text[:300])
    texte = [({"filed": "2026-07-31", "report": "2026-06-27"}, "Neu. " * 3000 + "Net income | 25,000"),
             ({"filed": "2026-05-01", "report": "2026-03-28"}, "Alt. " * 10)]
    block = texte_block(texte, je=2000, kopf=800)
    p("Textblock: aeltestes zuerst, langer Text gekuerzt, Kopfzeile je Mitteilung",
      block.index("2026-05-01") < block.index("2026-07-31") and len(block) < 4000 and "Net income | 25,000" in block, len(block))
    e = eingabe("Warum?", text, block)
    p("Eingabe: Frage, Tabelle und Texte in dieser Reihenfolge",
      e.index("Frage des Nutzers") < e.index("Zahlentabelle") < e.index("Pressemitteilungen der Firma"))
    w, pz = _zahlen("Umsatz 94,930 Milliarden, plus 6,1 Prozent, Konsens 0,95, am 31. Oktober 2024, up 8 percent, 1,85 US-Dollar")
    p("Zahlen lesen: Betraege, Prozente, deutsche und englische Schreibweise, ohne Jahreszahl",
      {94.93, 0.95, 1.85} <= w and {6.1, 8.0} <= pz and 2024 not in w and 31 in w, (w, pz))
    z1 = zahlen_pruefen("Das bereinigte Ergebnis lag bei 1,85 US-Dollar, was 13 Prozent ueber dem Vorjahresquartal liegt, "
                        "Ueberraschung 7,5 Prozent.", text, block)
    p("Waechter: die erfundene Prozentzahl 13 faellt auf, belegte Zahlen nicht",
      z1["unbelegt_prozent"] == [13.0] and z1["unbelegt"] == [], z1)
    z2 = zahlen_pruefen("Umsatz 100,600 Milliarden US-Dollar, ein Plus von 7,0 Prozent; Nettogewinn 25,000 Mrd; "
                        "Kursreaktion minus 2,97 Prozent. Erstens, zweitens, 3 Punkte.", text, block)
    p("Waechter: alle Zahlen einer treuen Antwort sind belegt, kleine Aufzaehlungszahlen zaehlen nicht",
      z2["unbelegt"] == [] and z2["unbelegt_prozent"] == [], z2)
    z3 = zahlen_pruefen("Umsatz 100,6 Milliarden, Vorjahr 94,0 Milliarden, Gewinn 25 Mrd, Konsens 1,6.", text, block)
    p("Waechter: gerundete Zahlen gelten als belegt (100,6 fuer 100,600; 94,0 fuer 94,036)",
      z3["unbelegt"] == [] and z3["unbelegt_prozent"] == [], z3)
    en = eingabe_mit_nachrichten("Warum?", text, block, "Jefferies senkte am 3. September 2026 das Kursziel (Quelle: Yahoo Finance, 3.9.2026).")
    p("Eingabe mit Nachrichtenlage: Abschnitt steht zwischen Tabelle und Pressemitteilungen",
      en.index("Zahlentabelle") < en.index("Nachrichtenlage") < en.index("Pressemitteilungen der Firma"))
    p("Eingabe ohne Nachrichten bleibt die alte Form", eingabe_mit_nachrichten("Warum?", text, block, "") == eingabe("Warum?", text, block))
    wf = websuche_frage("AAPL", "Apple Inc", "2026-07-30", "2026-09-03")
    p("Websuche-Frage nennt Firma, Ticker, Meldedatum und heutiges Datum",
      all(s in wf for s in ("Apple Inc", "AAPL", "2026-07-30", "2026-09-03")), wf)
    p("Websuche-Auftrag verlangt Quellen mit Datum, Deutsch, kein Markdown, Erfinden verboten",
      all(w in WEBSUCHE_AUFTRAG for w in ("Quelle", "Datum", "Deutsch", "ohne Markdown", "Erfinde nichts")))
    ohne = websuche_groq("AAPL", "Apple", "2026-07-30", "2026-09-03", log=lambda *_: None) if not GROQ_KEY else {"status": 0, "hinweise": ["GROQ_API_KEY fehlt"]}
    p("Websuche ohne Schluessel: Status 0 mit klarem Hinweis, kein Netzaufruf", ohne["status"] == 0 and "GROQ_API_KEY fehlt" in ohne["hinweise"])
    p("Markdown-Reste verschwinden", markdown_weg("**Schlagzeile:** Test\n- Punkt\n## Kopf") == "Schlagzeile: Test\nPunkt\nKopf", repr(markdown_weg("**Schlagzeile:** Test\n- Punkt\n## Kopf")))
    p("Verweismarken des Browser-Werkzeugs verschwinden",
      markdown_weg("Cook warnte \u3010" + "0\u2020L26-L34\u3011\u3010" + "0\u2020L54-L60\u3011. Ende") == "Cook warnte . Ende")
    bs = besuchte_seiten([{"typ": "browser_search", "eingabe": '{"query": "x"}'},
                          {"typ": "browser.open", "eingabe": '{"id":"https://www.finbold.com/analyst-apple-2026-09"}'},
                          {"typ": "browser.open", "eingabe": '{"cursor": 0, "id": 0}'}])
    p("Besuchte Seiten aus den Werkzeugaufrufen", bs == ["https://www.finbold.com/analyst-apple-2026-09"], bs)
    zn = zahlen_pruefen("Jefferies senkte das Kursziel auf 263,66 US-Dollar.", text, block + "\nKursziel auf $263,66 gesenkt")
    p("Waechter: Zahlen aus der Nachrichtenlage gelten als belegt", zn["unbelegt"] == [], zn)
    xml = ("<rss><channel><item><title>Jefferies Revamps Apple Stock Target On Setback</title>"
           "<link>https://finance.yahoo.com/news/jefferies-apple.html</link><pubDate>Thu, 03 Sep 2026 12:05:00 +0000</pubDate></item>"
           "<item><title><![CDATA[Apple faces &#163;2 bn lawsuit in UK]]></title><link>https://www.ft.com/x</link>"
           "<pubDate>Wed, 02 Sep 2026 08:00:00 +0000</pubDate></item><item><title></title></item></channel></rss>")
    rl = rss_lesen(xml)
    p("Yahoo-Feed lesen: Datum als ISO, Titel entschaerft, Quelle aus dem Link, leere Eintraege weg",
      rl == [("2026-09-03", "Jefferies Revamps Apple Stock Target On Setback", "finance.yahoo.com"),
             ("2026-09-02", "Apple faces \u00a32 bn lawsuit in UK", "ft.com")], rl)
    ny = nachrichten_yahoo("AAPL", hole=lambda url: xml, heute="2026-09-04")
    p("Yahoo-Nachrichtenlage: Abschnittstext mit Datum und Quelle je Zeile, Status 200",
      ny["status"] == 200 and len(ny["eintraege"]) == 2 and "2026-09-03: Jefferies" in ny["text"] and "(Quelle: ft.com)" in ny["text"], ny["text"])
    ny2 = nachrichten_yahoo("AAPL", hole=lambda url: "<rss><channel></channel></rss>")
    p("Yahoo-Feed leer: Status 204, kein Text", ny2["status"] == 204 and ny2["text"] == "", ny2)
    ny3 = nachrichten_yahoo("AAPL", hole=lambda url: (_ for _ in ()).throw(OSError("kein Netz")))
    p("Yahoo-Feed nicht lesbar: Status 0 mit Hinweis, kein Absturz", ny3["status"] == 0 and ny3["hinweise"], ny3)
    zu1 = zuordnung_pruefen("Im Quartal bis 2026-06-27 stieg der Umsatz auf 100,600 Milliarden.\n"
                            "Im Quartal bis 28. Maerz 2026 lag der Umsatz bei 105,0 Milliarden.", liste)
    p("Zuordnung: richtige Paare aus Datum und Umsatz, ISO und Monatsform", zu1 == {"geprueft": 2, "fehler": []}, zu1)
    zu2 = zuordnung_pruefen("Im Quartal zum 2026-01-29 meldete Apple einen Umsatz von 143,8 Milliarden.\n"
                            "Im Quartal zum 2025-12-27 meldete Apple einen Umsatz von 102,5 Milliarden.\n"
                            "Im Quartal zum 2025-09-27 meldete Apple einen Umsatz von 94,0 Milliarden.", liste)
    p("Zuordnung: um ein Quartal verschobene Zahlen fallen auf, Meldedatum trifft kein Quartal",
      zu2["geprueft"] == 2 and zu2["fehler"] == [("2025-12-27", "2025-09-27"), ("2025-09-27", "2025-06-28")], zu2)
    p("Auftrag verlangt Deutsch, keine Tabellen, Vermutungen gekennzeichnet, Quellen nur die Daten",
      all(w in AUFTRAG for w in ("Deutsch", "ohne Tabellen", "Vermutung", "AUSSCHLIESSLICH", "Safe Harbor")))
    p("Textblock nennt nur das Veroeffentlichungsdatum, kein falsches Quartal", "Quartal bis" not in block and "veroeffentlicht am 2026-07-31" in block)
    print("Alles bestanden." if fehler == 0 else f"{fehler} Fehler.")
    return fehler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--daten", default="daten")
    ap.add_argument("--ticker", default="AAPL")
    ap.add_argument("--frage", default=FRAGE_VORGABE)
    ap.add_argument("--modelle", default=",".join(MODELLE_VORGABE))
    ap.add_argument("--quartale", type=int, default=QUARTALE)
    ap.add_argument("--websuche", default="an", choices=["an", "aus"])
    ap.add_argument("--selbsttest", action="store_true")
    a = ap.parse_args()
    if a.selbsttest:
        return selbsttest()
    modelle = [m.strip() for m in a.modelle.split(",") if m.strip()]
    if modelle == ["alle"]:
        import messung_8k as m8k
        modelle = m8k.modelle_laden()
        print("Alle Text-Chat-Modelle der Tagesliste:", ", ".join(modelle))
    lauf(a.daten, a.ticker, a.frage or FRAGE_VORGABE, modelle, a.quartale, websuche=(a.websuche == "an"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
