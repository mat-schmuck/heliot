#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ABENDBERICHT: eine Meldung nach Handelsschluss, als Bericht gekennzeichnet
==========================================================================
Gerhards Antworten vom 12.09.2026, R7 bis R11 und Teil 5, dazu M6.

  R7   Eine EIGENE Meldung abends nach Handelsschluss, mit Datum, als
       Bericht gekennzeichnet, niedrige Prioritaet. Sie ist KEIN Alarm und
       kein Kaufsignal, sie ordnet den Tag ein.
  R8   "Roter Markt" heisst NUR der Nasdaq, und rot erst ab mindestens
       0,5 Prozent Minus.
  R9   "Gruen bei rotem Markt": Schluss im Plus UND mindestens 80 Prozent
       der Handelsminuten im Plus; sortiert nach dem Abstand zum Index.
       Bis der Minutenanteil gezaehlt ist, gilt der Schluss allein, und
       das steht dann dabei.
  R10  Neue Hochs in DREI getrennten Stufen: 52-Wochen-Hoch, 20-Tage-Hoch,
       RS-Linien-Hoch vor dem Kurs. Ein Allzeithoch ist ein Zusatzvermerk.
  R11  RS ab 96 in ZWEI getrennten Listen: die eigenen Listen und die
       Kandidaten aus dem Universum; je Aktie Rang, Aenderung zur Vorwoche
       und Abstand zum 52-Wochen-Hoch.
  Teil 5  Meldung, wenn die RS-Linie einer Listen-Aktie ein neues
       52-Wochen-Hoch macht, in zwei getrennten Stufen: WAEHREND der Kurs
       ein Hoch macht, und OBWOHL der Kurs keines hat (IBDs blauer Punkt).
       Gegen den S&P 500 (SPY); zusaetzlich gegen den Nasdaq (QQQ), weil
       es keinen Mehraufwand kostet. Je Aktie hoechstens einmal in zehn
       Handelstagen. Hinweis, kein Filter.
  M6   Moeglichkeit 3: Die schlussnahen Befunde des Waechters (gegen 15:45
       New York mit Handelskursen gerechnet) werden mit dem echten Schluss
       nachgeprueft; faellt die Bestaetigung, wird die RUECKNAHME gemeldet,
       optisch klar unterscheidbar (eigener Absatz, Wort RUECKNAHME).

Der Bericht entsteht im Nachtscan nach dem Kapitel-12-Lauf, weil dort die
Schlusskurse, das RS-Universum und die Sektor-Rangliste frisch sind. Er
wird je Handelstag genau einmal verschickt (Gedaechtnis). Die Regel vom
27.07.2026 "gemeldet wird nur vom Waechter zur Handelszeit" gilt fuer
Alarme; dieser Bericht ist ausdruecklich keiner (Gerhard, R7, die
neuere Regel).

Aufruf:
  python abendbericht.py --senden         im Nachtscan (NTFY_TOPIC aus der Umgebung)
  python abendbericht.py --anzeigen       nur bauen und ausgeben, nichts senden
  python abendbericht.py --selbsttest
"""

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta

from config import CFG

CFGA = CFG["abendbericht"]
GEDAECHTNIS = "abendbericht_gedaechtnis.json"
GRUEN_DATEI = "gruen_minuten.json"
SCHLUSSNAH_DATEI = "schlussnahe_gemeldet.json"
NTFY_GRENZE = 3900


def _lies(pfad, vorgabe=None):
    try:
        with open(pfad, encoding="utf-8-sig") as f:
            d = json.load(f)
        return d if isinstance(d, (dict, list)) else (vorgabe if vorgabe is not None else {})
    except (OSError, ValueError):
        return vorgabe if vorgabe is not None else {}


def _schreib(pfad, inhalt):
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(inhalt, f, ensure_ascii=False, indent=1)


def _z(wert, stellen=1, vorzeichen=False):
    """Zahl mit Beistrich, wie in allen Meldungen."""
    if wert is None:
        return "?"
    s = f"{wert:+.{stellen}f}" if vorzeichen else f"{wert:.{stellen}f}"
    return s.replace(".", ",")


def _datum_de(iso):
    try:
        return date.fromisoformat(str(iso)[:10]).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return str(iso or "")


def _handelstage_her(tag, bis):
    try:
        d = date.fromisoformat(str(tag)[:10])
    except (TypeError, ValueError):
        return None
    n, lauf = 0, d
    while lauf < bis:
        lauf += timedelta(days=1)
        if lauf.weekday() < 5:
            n += 1
    return n


def _name(t, e):
    firma = e.get("firma") or e.get("name") or ""
    return f"{t} ({firma})" if firma else t


def lesbar(text):
    """Beobachtungsschluessel wie NRIX|2 tragen den senkrechten Strich, der
    in Meldungen nichts verloren hat (Screenreader). Aus 'NRIX|2' wird
    'NRIX Kaufpunkt 2', jeder uebrige Strich wird ein Beistrich."""
    import re
    s = re.sub(r"([A-Z0-9.\-]+)\|(\d+)", r"\1 Kaufpunkt \2", str(text or ""))
    return s.replace("|", ", ").replace("–", ",").replace("—", ",")


# ---------------------------------------------------------------------------
# Die Abschnitte
# ---------------------------------------------------------------------------

def gruen_bei_rot(rs, gruen, cfg=None):
    """R8 und R9. Rueckgabe (Zeilen, Vermerk)."""
    cfg = cfg or CFGA
    markt = rs.get("markt") or {}
    if not markt.get("rot"):
        return [], None
    m_pct = markt.get("pct") or 0.0
    anteil_min = float(cfg["gruen_minuten_anteil"])
    aktien = (gruen or {}).get("aktien") or {}
    gezaehlt = str((gruen or {}).get("tag") or "") == str(rs.get("handelstag") or "")
    kand = []
    for t, e in (rs.get("listen") or {}).items():
        pct = e.get("pct")
        if pct is None or pct <= 0:
            continue
        anteil = None
        if gezaehlt:
            z = aktien.get(t)
            if isinstance(z, list) and len(z) == 2 and z[1] >= 30:
                anteil = z[0] / z[1]
        if anteil is not None and anteil < anteil_min:
            continue
        kand.append((t, e, pct, pct - m_pct, anteil))
    kand.sort(key=lambda k: -k[3])
    zeilen = []
    for i, (t, e, pct, abst, anteil) in enumerate(kand, 1):
        teil = (f"{anteil * 100:.0f} Prozent der Minuten im Plus" if anteil is not None
                else "Minutenanteil nicht gezaehlt, Schluss allein")
        zeilen.append(f"{i}. {_name(t, e)}; Schluss {_z(pct, 1, True)} Prozent, Abstand zum Nasdaq "
                      f"{_z(abst, 1, True)} Punkte; {teil}")
    vermerk = (f"Nasdaq {_z(m_pct, 2, True)} Prozent, rot" if kand or True else None)
    return zeilen, vermerk


def allzeithoch(ticker, kurs, holen=None):
    """Zusatzvermerk R10: Ist das 52-Wochen-Hoch zugleich ein Allzeithoch?
    Ein Abruf je Kandidat (period=max); jeder Fehler heisst 'unbekannt'."""
    try:
        if holen is None:
            import yfinance as yf
            df = yf.download(ticker, period="max", interval="1d", progress=False,
                             auto_adjust=False)
            if df is None or df.empty:
                return None
            if hasattr(df.columns, "levels"):
                df.columns = df.columns.droplevel(1)
            hoch = float(df["High"].max())
        else:
            hoch = holen(ticker)
            if hoch is None:
                return None
        return bool(kurs is not None and kurs >= hoch * 0.999)
    except Exception:  # noqa
        return None


def neue_hochs(rs, holen_allzeit=None):
    """R10: drei Stufen, getrennt. Nur die Listen-Aktien, nur an einem
    roten Nasdaq-Tag (der Zweck der Frage war der rote Markt)."""
    markt = rs.get("markt") or {}
    if not markt.get("rot"):
        return {}
    stufen = {"52-Wochen-Hoch": [], "20-Tage-Hoch": [], "RS-Linien-Hoch vor dem Kurs": []}
    for t, e in sorted((rs.get("listen") or {}).items()):
        if e.get("kurs_52w_hoch"):
            zusatz = ""
            az = allzeithoch(t, e.get("kurs"), holen_allzeit)
            if az is True:
                zusatz = "; zugleich Allzeithoch"
            elif az is False:
                zusatz = "; kein Allzeithoch"
            stufen["52-Wochen-Hoch"].append(f"{_name(t, e)}; Kurs {_z(e.get('kurs'), 2)}{zusatz}")
        elif e.get("kurs_20t_hoch"):
            stufen["20-Tage-Hoch"].append(f"{_name(t, e)}; Kurs {_z(e.get('kurs'), 2)}")
        if e.get("linie_spy_hoch") and not e.get("kurs_52w_hoch"):
            stufen["RS-Linien-Hoch vor dem Kurs"].append(
                f"{_name(t, e)}; RS-Linie gegen SPY auf 52-Wochen-Hoch, der Kurs "
                f"{_z(e.get('abst_52w_hoch_pct'), 1, True)} Prozent unter seinem Hoch")
    return {k: v for k, v in stufen.items() if v}


def _vorwoche(e):
    """RS vor fuenf Handelstagen aus dem Verlauf, sonst None."""
    v = [x for x in (e.get("rs_verlauf") or []) if isinstance(x, list) and len(x) == 2 and x[1] is not None]
    if len(v) >= 6:
        return v[-6][1]
    return None


def rs_ab(rs, cfg=None):
    """R11: zwei getrennte Listen ab RS 96."""
    cfg = cfg or CFGA
    ab = int(cfg["rs_bericht_ab"])
    listen = rs.get("listen") or {}
    eigene, universum = [], []
    for t, e in listen.items():
        if e.get("rs") is not None and e["rs"] >= ab:
            eigene.append((t, e))
    for t, e in (rs.get("aktien") or {}).items():
        if t in listen:
            continue
        if e.get("rs") is not None and e["rs"] >= ab:
            universum.append((t, e))
    eigene.sort(key=lambda p: (-p[1]["rs"], p[0]))
    universum.sort(key=lambda p: (-p[1]["rs"], p[0]))

    def zeile(i, t, e):
        vor = _vorwoche(e)
        aend = (f", vor einer Woche {int(vor)}, Aenderung {int(e['rs']) - int(vor):+d}" if vor is not None
                else ", Vorwoche noch ohne Wert")
        return (f"{i}. {_name(t, e)}; RS {int(e['rs'])}{aend}; Abstand zum 52-Wochen-Hoch "
                f"{_z(e.get('abst_52w_hoch_pct'), 1, True)} Prozent")
    return ([zeile(i, t, e) for i, (t, e) in enumerate(eigene, 1)],
            [zeile(i, t, e) for i, (t, e) in enumerate(universum, 1)])


def rs_linien_hochs(rs, gedaechtnis, heute, cfg=None):
    """Teil 5: zwei Stufen, Sperre zehn Handelstage je Aktie.
    Rueckgabe (zeilen_waehrend, zeilen_obwohl, gedaechtnis_neu)."""
    cfg = cfg or CFGA
    sperre = int(cfg["rs_linien_sperre_tage"])
    g = dict(gedaechtnis or {})
    merker = dict(g.get("rs_linie") or {})
    tag = str(rs.get("handelstag") or heute.isoformat())
    waehrend, obwohl = [], []
    for t, e in sorted((rs.get("listen") or {}).items()):
        if not e.get("linie_spy_hoch"):
            continue
        letzter = merker.get(t)
        her = _handelstage_her(letzter, heute) if letzter else None
        if her is not None and her < sperre:
            continue
        auch_qqq = "; auch gegen QQQ" if e.get("linie_qqq_hoch") else ""
        if e.get("kurs_52w_hoch"):
            waehrend.append(f"{_name(t, e)}; RS-Linie gegen SPY auf 52-Wochen-Hoch waehrend eines "
                            f"Kurs-Hochs{auch_qqq}; RS {int(e['rs']) if e.get('rs') is not None else 'nicht verfuegbar'}")
        else:
            obwohl.append(f"{_name(t, e)}; RS-Linie gegen SPY auf 52-Wochen-Hoch, obwohl der Kurs keines "
                          f"hat, blauer Punkt; Kurs {_z(e.get('abst_52w_hoch_pct'), 1, True)} Prozent unter "
                          f"dem Hoch{auch_qqq}; RS {int(e['rs']) if e.get('rs') is not None else 'nicht verfuegbar'}")
        merker[t] = tag
    g["rs_linie"] = merker
    return ([f"{i}. {z}" for i, z in enumerate(waehrend, 1)],
            [f"{i}. {z}" for i, z in enumerate(obwohl, 1)], g)


def ruecknahmen(schlussnah, befunde_nacht, handelstag):
    """M6: Welche schlussnahen Befunde gelten mit dem echten Schluss nicht
    mehr? Rueckgabe (zeilen, bestaetigt, zurueckgenommen)."""
    if not isinstance(schlussnah, dict) or str(schlussnah.get("handelstag") or "") != str(handelstag):
        return [], [], []
    if schlussnah.get("geprueft"):
        return [], [], []
    nacht = befunde_nacht or []
    vorhanden = set()
    for b in nacht:
        if not isinstance(b, dict):
            continue
        vorhanden.add((b.get("typ"), b.get("key") or b.get("symbol"), b.get("zeichen")))
        vorhanden.add((b.get("typ"), b.get("symbol"), b.get("zeichen")))
    zeilen, best, zurueck = [], [], []
    for s in schlussnah.get("befunde") or []:
        if not isinstance(s, dict):
            continue
        kennung = (s.get("typ"), s.get("key") or s.get("symbol"), s.get("zeichen"))
        kennung2 = (s.get("typ"), s.get("symbol"), s.get("zeichen"))
        if kennung in vorhanden or kennung2 in vorhanden:
            best.append(s)
        else:
            zurueck.append(s)
            zeilen.append(f"RUECKNAHME: {lesbar(s.get('text') or s.get('titel') or s.get('symbol'))}; "
                          f"mit dem Schlusskurs nicht mehr gueltig")
    return [f"{i}. {z}" for i, z in enumerate(zeilen, 1)], best, zurueck


def sektor_kurz(sek):
    liste = (sek or {}).get("liste") or []
    if not liste:
        return []
    top = [z for z in liste if z.get("rang")][:5]
    zeilen = ["Sektoren nach Faber-Mittel: "
              + ", ".join(f"{z['rang']} {z['etf']} {z.get('name', '')}".strip() for z in top)]
    auf = (sek or {}).get("groesste_aufsteiger") or []
    if auf:
        zeilen.append("Groesste Aufsteiger in drei Wochen: "
                      + ", ".join(f"{z['etf']} plus {z['aenderung_3w']} Raenge auf {z['rang']}" for z in auf))
    return zeilen


# ---------------------------------------------------------------------------
# Bauen und senden
# ---------------------------------------------------------------------------

def bauen(rs, sek, gruen, gedaechtnis, schlussnah, befunde_nacht, heute, holen_allzeit=None, cfg=None):
    """Rueckgabe (titel, absaetze, prioritaet, gedaechtnis_neu, zurueckgenommen)."""
    cfg = cfg or CFGA
    handelstag = str(rs.get("handelstag") or heute.isoformat())
    titel = f"Abendbericht {_datum_de(handelstag)}, Bericht, kein Kaufsignal"
    absaetze = []
    markt = rs.get("markt") or {}
    kopf = [f"Bericht zum Handelstag {_datum_de(handelstag)}"]
    if markt.get("pct") is not None:
        kopf.append(f"Nasdaq {_z(markt['pct'], 2, True)} Prozent, "
                    + ("rot" if markt.get("rot") else "nicht rot (rot erst ab 0,5 Prozent Minus)"))
    if rs.get("status") != "ok":
        kopf.append(f"RS nicht verfuegbar: {rs.get('grund') or rs.get('status')}")
    else:
        u = rs.get("universum") or {}
        kopf.append(f"RS gegen {u.get('bezug_anzahl') or u.get('im_universum', '?')} Stammaktien des "
                    f"US-Markts gerechnet, Abdeckung "
                    f"{_z((u.get('abdeckung') or 0) * 100, 1)} Prozent")
        pl = rs.get("plausibilitaet") or {}
        if pl and not pl.get("ok"):
            kopf.append(f"Plausibilitaet der Perzentile NICHT bestanden: {pl.get('grund')}")
    absaetze.append("; ".join(kopf))

    # M6 zuerst: Was zurueckgenommen wird, ist das Dringlichste.
    rz, best, zurueck = ruecknahmen(schlussnah, befunde_nacht, handelstag)
    if rz:
        absaetze.append("Ruecknahmen der schlussnahen Befunde von 15:45:\n" + "\n".join(rz))
    elif isinstance(schlussnah, dict) and str(schlussnah.get("handelstag") or "") == handelstag \
            and not schlussnah.get("geprueft") and (schlussnah.get("befunde") or []):
        absaetze.append(f"Alle {len(best)} schlussnahen Befunde von 15:45 mit dem Schluss bestaetigt")

    if rs.get("status") == "ok":
        gz, vermerk = gruen_bei_rot(rs, gruen, cfg)
        if markt.get("rot"):
            absaetze.append("Gruen bei rotem Markt (Schluss im Plus, mindestens 80 Prozent der Minuten im Plus, "
                            "nach Abstand zum Nasdaq):\n" + ("\n".join(gz) if gz else "keine"))
            hochs = neue_hochs(rs, holen_allzeit)
            for stufe, zeilen in hochs.items():
                absaetze.append(f"Neue Hochs bei rotem Markt, Stufe {stufe}:\n"
                                + "\n".join(f"{i}. {z}" for i, z in enumerate(zeilen, 1)))
        eig, uni = rs_ab(rs, cfg)
        ab = int(cfg["rs_bericht_ab"])
        absaetze.append(f"RS ab {ab}, eigene Listen:\n" + ("\n".join(eig) if eig else "keine"))
        absaetze.append(f"RS ab {ab}, Kandidaten aus dem Nasdaq-Universum:\n" + ("\n".join(uni) if uni else "keine"))
        w, o, gedaechtnis = rs_linien_hochs(rs, gedaechtnis, heute, cfg)
        if w:
            absaetze.append("RS-Linie auf 52-Wochen-Hoch WAEHREND eines Kurs-Hochs (je Aktie hoechstens einmal in "
                            "zehn Handelstagen):\n" + "\n".join(w))
        if o:
            absaetze.append("RS-Linie auf 52-Wochen-Hoch OBWOHL der Kurs keines hat, blauer Punkt:\n" + "\n".join(o))
    sk = sektor_kurz(sek)
    if sk:
        absaetze.append("\n".join(sk))
    absaetze.append("Hinweis: RS, Sektorraenge und Ratings sind Entscheidungshilfen, keine Filter. "
                    "Kurse splitbereinigt, nicht dividendenbereinigt.")
    prio = str(cfg.get("prioritaet") or "low")
    return titel, absaetze, prio, gedaechtnis, zurueck, best


def klimax_merker_setzen(bestaetigt, laden=None, speichern=None):
    """M5 und M6: Ein um 15:45 gemeldetes Klimax-Zeichen gilt erst als
    gemeldet, wenn der Schluss es bestaetigt hat; dann traegt es JEDE
    Beobachtung der Aktie (je Aktie nur einmal). Rueckgabe: Anzahl."""
    zeichen = [(s.get("symbol"), s.get("zeichen")) for s in (bestaetigt or [])
               if s.get("typ") == "klimax_zeichen" and s.get("zeichen")]
    if not zeichen:
        return 0
    import positionen
    bestand = (laden or positionen.laden)()
    n = 0
    for e in bestand.values():
        if not isinstance(e, dict) or e.get("status") != "offen":
            continue
        for sym, z in zeichen:
            if str(e.get("symbol") or "").upper() == str(sym or "").upper().split("|")[0]:
                liste = e.setdefault("klimax_gemeldet", [])
                if z not in liste:
                    liste.append(z)
                    n += 1
    if n:
        (speichern or positionen.speichern)(bestand)
    return n


def _portionen(absaetze, grenze=NTFY_GRENZE):
    portionen, aktuell, laenge = [], [], 0
    for a in absaetze:
        if len(a.encode("utf-8")) > grenze:
            a = a.encode("utf-8")[:grenze - 20].decode("utf-8", "ignore") + " ..."
        gr = len(a.encode("utf-8")) + 2
        if aktuell and laenge + gr > grenze:
            portionen.append(aktuell)
            aktuell, laenge = [], 0
        aktuell.append(a)
        laenge += gr
    if aktuell:
        portionen.append(aktuell)
    return portionen


def senden(topic, titel, absaetze, prio="low", poster=None):
    """Eigener Sendeweg ohne Handelszeitsperre: Der Bericht kommt nach dem
    Schluss (R7). Kennungen wandern in den ntfy-Verlauf, damit der
    Freitags-Putz auch diese Meldungen raeumt."""
    import requests
    portionen = _portionen(absaetze)
    ok = True
    for nr, teil in enumerate(portionen, 1):
        kopf = titel if len(portionen) == 1 else f"{titel} ({nr} von {len(portionen)})"
        body = "\n\n".join(teil)
        try:
            if poster is not None:
                r = poster(topic, kopf, body, prio)
            else:
                r = requests.post(f"https://ntfy.sh/{topic}", data=body.encode("utf-8"),
                                  headers={"Title": kopf.encode("utf-8"), "Priority": prio}, timeout=20)
                try:
                    import ntfy_verlauf
                    ntfy_verlauf.merke_antwort(r)
                except Exception:  # noqa
                    pass
            if getattr(r, "status_code", 200) >= 400:
                ok = False
        except Exception as e:  # noqa
            print(f"Abendbericht: Senden fehlgeschlagen ({type(e).__name__}: {e})")
            ok = False
    return ok


def lauf(topic=None, senden_erlaubt=True, heute=None, leise=False, poster=None, holen_allzeit=None):
    """Der Aufruf aus dem Nachtscan. Baut den Bericht, sendet ihn einmal je
    Handelstag und schreibt Gedaechtnis und Rücknahme-Pruefung."""
    import rs_universum
    import sektor_rangliste
    heute = heute or date.today()
    rs = rs_universum.lies()
    sek = sektor_rangliste.lies()
    gruen = _lies(GRUEN_DATEI, {})
    ged = _lies(GEDAECHTNIS, {})
    schlussnah = _lies(SCHLUSSNAH_DATEI, {})
    befunde = (_lies("exit_befunde.json", {}) or {}).get("befunde") or []
    if not rs:
        print("Abendbericht: kein RS-Universum vorhanden, kein Bericht.")
        return None
    handelstag = str(rs.get("handelstag") or heute.isoformat())
    if str(ged.get("gesendet") or "") == handelstag:
        if not leise:
            print(f"Abendbericht fuer {handelstag} wurde schon gesendet.")
        return None
    titel, absaetze, prio, ged_neu, zurueck, best = bauen(rs, sek, gruen, ged, schlussnah, befunde, heute,
                                                           holen_allzeit=holen_allzeit)
    if best and not (isinstance(schlussnah, dict) and schlussnah.get("geprueft")):
        try:
            n = klimax_merker_setzen(best)
            if n and not leise:
                print(f"Abendbericht: {n} bestaetigte Klimax-Zeichen als gemeldet vermerkt.")
        except Exception as e:  # noqa
            print(f"Abendbericht: Klimax-Merker nicht gesetzt ({type(e).__name__}: {e})")
    if not leise:
        print(titel)
        for a in absaetze:
            print("  " + a.replace("\n", "\n  "))
    gesendet = False
    if senden_erlaubt and CFGA.get("melden") and topic:
        gesendet = senden(topic, titel, absaetze, prio, poster=poster)
        if gesendet:
            ged_neu["gesendet"] = handelstag
            ged_neu["gesendet_am"] = datetime.now().isoformat(timespec="seconds")
    elif not senden_erlaubt:
        print("Abendbericht: nur angezeigt, nicht gesendet.")
    _schreib(GEDAECHTNIS, ged_neu)
    if isinstance(schlussnah, dict) and str(schlussnah.get("handelstag") or "") == handelstag:
        schlussnah["geprueft"] = handelstag
        schlussnah["zurueckgenommen"] = [s.get("key") or s.get("symbol") for s in zurueck]
        _schreib(SCHLUSSNAH_DATEI, schlussnah)
    return {"titel": titel, "absaetze": absaetze, "gesendet": gesendet, "zurueck": len(zurueck)}


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

def selbsttest() -> int:
    fehler = []

    def p(name, ok, zusatz=""):
        print(f"  {'ok  ' if ok else 'FEHL'} {name}" + (f" — {zusatz}" if zusatz else ""))
        if not ok:
            fehler.append(name)

    print("Abendbericht, Selbsttest (ohne Netz)")
    heute = date(2026, 9, 14)
    rs = {"handelstag": "2026-09-14", "status": "ok",
          "universum": {"im_universum": 3000, "abdeckung": 0.99},
          "plausibilitaet": {"ok": True},
          "markt": {"pct": -1.2, "rot": True},
          "listen": {
              "AAA": {"firma": "Alpha", "kurs": 100.0, "pct": 2.0, "rs": 97, "rs_verlauf": [["d1", 90], ["d2", 91], ["d3", 92], ["d4", 93], ["d5", 94], ["d6", 95], ["2026-09-14", 97]],
                      "kurs_52w_hoch": True, "kurs_20t_hoch": True, "linie_spy_hoch": True, "linie_qqq_hoch": True, "abst_52w_hoch_pct": 0.0},
              "BBB": {"firma": "Beta", "kurs": 50.0, "pct": 0.5, "rs": 60, "rs_verlauf": [],
                      "kurs_52w_hoch": False, "kurs_20t_hoch": True, "linie_spy_hoch": True, "linie_qqq_hoch": False, "abst_52w_hoch_pct": -8.0},
              "CCC": {"firma": "Gamma", "kurs": 20.0, "pct": -0.3, "rs": 96, "rs_verlauf": [],
                      "kurs_52w_hoch": False, "kurs_20t_hoch": False, "linie_spy_hoch": False, "linie_qqq_hoch": False, "abst_52w_hoch_pct": -20.0},
              "DDD": {"firma": "Delta", "kurs": 30.0, "pct": 1.0, "rs": 40, "rs_verlauf": [],
                      "kurs_52w_hoch": False, "kurs_20t_hoch": False, "linie_spy_hoch": False, "linie_qqq_hoch": False, "abst_52w_hoch_pct": -5.0},
          },
          "aktien": {"UNI": {"name": "Uni Corp", "kurs": 70.0, "pct": 3.0, "rs": 98, "rs_verlauf": [], "abst_52w_hoch_pct": -1.0},
                     "AAA": {"name": "Alpha", "rs": 97}}}
    gruen = {"tag": "2026-09-14", "aktien": {"AAA": [300, 350], "DDD": [100, 350]}}
    ged = {"rs_linie": {"BBB": "2026-09-10"}}
    schlussnah = {"handelstag": "2026-09-14", "befunde": [
        {"typ": "klimax_zeichen", "key": "AAA|1", "symbol": "AAA", "zeichen": "2_groesster_tagesgewinn", "text": "AAA; Klimax-Zeichen 2"},
        {"typ": "kapitel11", "key": "BBB|1", "symbol": "BBB|1", "zeichen": None, "text": "BBB|1; Stop gerissen"}]}
    befunde_nacht = [{"typ": "klimax_zeichen", "key": "AAA|1", "symbol": "AAA", "zeichen": "2_groesster_tagesgewinn"}]
    sek = {"liste": [{"etf": "XLK", "name": "Technology", "rang": 1}, {"etf": "XLE", "name": "Energy", "rang": 2}],
           "groesste_aufsteiger": [{"etf": "XLE", "aenderung_3w": 7, "rang": 2}]}

    titel, absaetze, prio, ged_neu, zurueck, best = bauen(rs, sek, gruen, ged, schlussnah, befunde_nacht, heute,
                                                           holen_allzeit=lambda t: 100.0 if t == "AAA" else None)
    text = "\n\n".join(absaetze)
    p("Schluessel mit senkrechtem Strich werden lesbar", lesbar("NRIX|2 (Firma); Stop") == "NRIX Kaufpunkt 2 (Firma); Stop")
    gesetzt = {}
    n_m = klimax_merker_setzen(best, laden=lambda: {"AAA|1": {"symbol": "AAA", "status": "offen", "klimax_gemeldet": []},
                                                    "AAA|2": {"symbol": "AAA", "status": "offen"},
                                                    "ZZZ|1": {"symbol": "ZZZ", "status": "offen"}},
                               speichern=lambda b: gesetzt.update(b))
    p("Bestaetigtes Klimax-Zeichen wird an ALLEN Beobachtungen der Aktie vermerkt (M5), nicht an fremden",
      n_m == 2 and gesetzt["AAA|1"]["klimax_gemeldet"] == ["2_groesster_tagesgewinn"]
      and gesetzt["AAA|2"]["klimax_gemeldet"] == ["2_groesster_tagesgewinn"] and "klimax_gemeldet" not in gesetzt["ZZZ|1"])
    p("Titel traegt Datum und das Wort Bericht", "14.09.2026" in titel and "Bericht" in titel, titel)
    p("Prioritaet niedrig", prio == "low")
    p("Kein Gedankenstrich und kein senkrechter Strich im Bericht", "–" not in text and "|" not in text and "—" not in text)
    p("Gruen bei rotem Markt: AAA drin (86 Prozent der Minuten), DDD nicht (29 Prozent), CCC nicht (Schluss im Minus), BBB ohne Zaehlung mit Vermerk",
      "1. AAA (Alpha)" in text and "DDD" not in text.split("RS ab")[0].split("Gruen")[1] and "Minutenanteil nicht gezaehlt" in text
      and "CCC" not in text.split("Gruen bei rotem")[1].split("Neue Hochs")[0], text.split("Gruen bei rotem")[1][:300])
    p("Gruen sortiert nach Abstand zum Nasdaq: AAA vor BBB", text.find("1. AAA") < text.find("2. BBB (Beta); Schluss +0,5"))
    p("Neue Hochs drei Stufen getrennt, Allzeithoch als Zusatzvermerk",
      "Stufe 52-Wochen-Hoch:\n1. AAA (Alpha); Kurs 100,00; zugleich Allzeithoch" in text
      and "Stufe 20-Tage-Hoch:\n1. BBB" in text and "Stufe RS-Linien-Hoch vor dem Kurs:\n1. BBB" in text)
    p("RS ab 96: eigene Listen AAA und CCC, Universum nur UNI (AAA ist Listenaktie)",
      "eigene Listen:\n1. AAA (Alpha); RS 97, vor einer Woche 91, Aenderung +6" in text
      and "2. CCC" in text and "Nasdaq-Universum:\n1. UNI (Uni Corp); RS 98" in text and "2. AAA" not in text.split("Nasdaq-Universum")[1].split("RS-Linie")[0])
    p("RS-Linien-Hoch zwei Stufen: AAA waehrend Kurs-Hoch (auch QQQ), BBB gesperrt (vor 2 Handelstagen gemeldet)",
      "WAEHREND eines Kurs-Hochs" in text and "1. AAA (Alpha); RS-Linie gegen SPY auf 52-Wochen-Hoch waehrend" in text
      and "auch gegen QQQ" in text and "OBWOHL" not in text)
    p("Gedaechtnis merkt AAA mit Handelstag, BBB bleibt", ged_neu["rs_linie"].get("AAA") == "2026-09-14" and ged_neu["rs_linie"].get("BBB") == "2026-09-10")
    ged2 = {"rs_linie": {"BBB": "2026-08-20"}}
    _, abs2, _, _, _, _ = bauen(rs, sek, gruen, ged2, {}, [], heute, holen_allzeit=lambda t: None)
    p("Nach der Sperre wird BBB als blauer Punkt gemeldet", "OBWOHL der Kurs keines hat" in "\n".join(abs2) and "1. BBB (Beta)" in "\n".join(abs2))
    p("M6: Klimax AAA bestaetigt, Exit BBB zurueckgenommen und klar als RUECKNAHME gekennzeichnet",
      len(zurueck) == 1 and zurueck[0]["key"] == "BBB|1" and len(best) == 1
      and "RUECKNAHME: BBB Kaufpunkt 1; Stop gerissen; mit dem Schlusskurs nicht mehr gueltig" in text)
    p("Sektoren kurz mit Faber-Raengen und Aufsteigern", "Sektoren nach Faber-Mittel: 1 XLK Technology, 2 XLE Energy" in text and "XLE plus 7 Raenge auf 2" in text)
    p("Schlusshinweis: Entscheidungshilfen, keine Filter", "keine Filter" in text)
    p("Nummerierung je Abschnitt beginnt bei 1", text.count("\n1. ") >= 5)
    # nicht roter Markt: kein Gruen-Abschnitt, keine Hochs
    rs2 = dict(rs); rs2["markt"] = {"pct": 0.3, "rot": False}
    _, abs3, _, _, _, _ = bauen(rs2, sek, gruen, {}, {}, [], heute)
    t3 = "\n".join(abs3)
    p("Nicht roter Nasdaq: kein Gruen-Abschnitt und keine Hoch-Stufen, RS-Listen trotzdem", "Gruen bei rotem" not in t3 and "Neue Hochs" not in t3 and "RS ab 96" in t3)
    rs3 = dict(rs); rs3["status"] = "nicht verfuegbar"; rs3["grund"] = "Abdeckung 80 Prozent"
    _, abs4, _, _, _, _ = bauen(rs3, sek, gruen, {}, {}, [], heute)
    p("RS nicht verfuegbar: der Bericht sagt es und rechnet keine RS-Listen", "RS nicht verfuegbar: Abdeckung 80 Prozent" in abs4[0] and not any("RS ab" in a for a in abs4))
    # Portionen
    port = _portionen(["a" * 3000, "b" * 3000, "c" * 10])
    p("Portionierung trennt nur zwischen Absaetzen", len(port) == 2 and port[1] == ["b" * 3000, "c" * 10])
    # Senden ueber Fake-Poster und Gedaechtnis
    import tempfile
    alt = os.getcwd()
    tmp = tempfile.mkdtemp()
    os.chdir(tmp)
    try:
        import json as _j
        with open("rs_universum.json", "w", encoding="utf-8") as f:
            _j.dump(rs, f)
        with open("sektor_rangliste.json", "w", encoding="utf-8") as f:
            _j.dump(sek, f)
        _schreib(GRUEN_DATEI, gruen)
        _schreib(SCHLUSSNAH_DATEI, schlussnah)
        _schreib("exit_befunde.json", {"befunde": befunde_nacht})
        gesendet = []

        class R:
            status_code = 200
        erg = lauf(topic="probe", heute=heute, leise=True, poster=lambda t, k, b, pr: (gesendet.append((k, pr)), R())[1],
                   holen_allzeit=lambda t: None)
        p("Lauf sendet einmal mit niedriger Prioritaet und merkt den Handelstag",
          erg and erg["gesendet"] and len(gesendet) >= 1 and gesendet[0][1] == "low"
          and _lies(GEDAECHTNIS).get("gesendet") == "2026-09-14", str(gesendet)[:100])
        erg2 = lauf(topic="probe", heute=heute, leise=True, poster=lambda t, k, b, pr: (gesendet.append((k, pr)), R())[1])
        p("Zweiter Lauf am selben Handelstag sendet nichts", erg2 is None and len(gesendet) == 1)
        s = _lies(SCHLUSSNAH_DATEI)
        p("Schlussnahe Befunde als geprueft markiert, Ruecknahme vermerkt", s.get("geprueft") == "2026-09-14" and s.get("zurueckgenommen") == ["BBB|1"])
    finally:
        os.chdir(alt)
    print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles bestanden.")
    return 1 if fehler else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Abendbericht nach Handelsschluss (R7).")
    ap.add_argument("--senden", action="store_true")
    ap.add_argument("--anzeigen", action="store_true")
    ap.add_argument("--selbsttest", action="store_true")
    args = ap.parse_args()
    if args.selbsttest:
        return selbsttest()
    if args.senden or args.anzeigen:
        topic = (os.environ.get("NTFY_TOPIC") or "").strip() or None
        lauf(topic=topic, senden_erlaubt=bool(args.senden))
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
