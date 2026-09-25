#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FUNDAMENTALE KENNZAHLEN AUS DEM SEC-FUNDAMENT (Etappe 4, Entscheidungen 7 und 8)
=================================================================================
Gerhard, 13.09.2026: "7: ALLE 13 PUNKTE aus Gruppe B. Dass 49 von 57
Kennzahlen ungelesen im Parquet liegen, ist der groesste ungenutzte Bestand
den wir haben, und es kostet keinen einzigen neuen Abruf." und "8: JA,
CAN-SLIM-HAEKCHEN: Quartals-EPS ab 25 Prozent, Dreijahres-CAGR ab 25 Prozent,
ROE ab 17 Prozent. Ein Haekchen ist kein Filter, es unterdrueckt nichts."
Grundlage ist das Recherche-Papier vom 13.09.2026, Teil 4.2 und Etappe 6.5.
Alles ist Anzeige, nichts filtert.

Dieses Modul rechnet nur, auf den Reihen einer Firma in der Form von
ibd_ratings._reihen ({Kennzahl: {Typ: [(Start, Ende, Wert, Quelle, Taxonomie,
Einheit, Erstfassung, letzte Einreichung, erste Einreichung), ...]}}, Typ Q,
FY oder B). Es holt nichts aus dem Netz.

DREI EIGENHEITEN DES FUNDAMENTS, nach denen sich die Formeln richten
  1. Das vierte Quartal steht bei Flussgroessen (Umsatz, Gewinn, Cashflow)
     als Jahr minus neun Monate berechnet in der Reihe, bei Gewinn je Aktie
     und Aktienzahlen NIE (fundament_normalisieren.py, Falle 3). Alles, was
     vier Quartale braucht, rechnet deshalb mit Nettogewinn und
     Marktkapitalisierung statt mit der Summe von vier EPS; das KGV ist
     Marktkapitalisierung durch Nettogewinn der letzten vier Quartale.
  2. Bestandsgroessen stehen zu verschiedenen Stichtagen. Verhaeltnisse aus
     der Bilanz nehmen alle Werte vom SELBEN Stichtag, dem juengsten der
     Bilanzsumme; was dort fehlt, fehlt, statt einen aelteren Wert
     unterzumischen.
  3. Auslaendische Emittenten berichten oft in fremder Waehrung, und der
     Kurs eines ADR steht fuer eine unbekannte Zahl von Aktien. Alles mit
     dem Kurs (Bewertung, Renditen auf die Marktkapitalisierung, Werte je
     Aktie, Altman Z) gibt es deshalb nur fuer inlaendische Emittenten mit
     Dollarzahlen; die Verhaeltnisse innerhalb der Bilanz und der
     Erfolgsrechnung gelten fuer alle.

ZWEI BEFUNDE DES 14.09.2026, vor jeder Rechnung bereinigt
  4. Einheiten: Aktienzahl, Gewinn je Aktie und Nettogewinn stehen in rund
     2 Prozent der Perioden um eine glatte Zehnerpotenz daneben (Tausend,
     Millionen, Cent). einheiten_bereinigt rechnet zurueck, was zwei
     Hinweise belegen (EPS mal Aktien durch Gewinn, Deckblatt, Nachbarwerte,
     Ergebnis vor Steuern), und nennt den Rest unstimmig. Den Nettogewinn
     aus Vollmachtsunterlagen nimmt schon ibd_ratings.ohne_vollmachtszahlen
     heraus.
  5. Splits: Was vor einem Split zuletzt eingereicht wurde, bleibt in der
     alten Stueckelung. split_bereinigt erkennt Splits an umgeschriebenen
     Perioden und waehlt die Umrechnungstage an der glattesten Aktienreihe.
     Ergebnis und Korrekturen stehen in der Ablage (splits, einheiten,
     unstimmig).

DIE 13 PUNKTE (Papier 4.2), knapp
  1  Margen: brutto, operativ, vor Steuern, netto, je juengstes Quartal und
     Geschaeftsjahr. Die Vorsteuermarge des Jahres geht in den SMR ein
     (ibd_ratings.py).
  2  Kapitalrenditen: ROE wie im SMR, ROA, ROIC mit dem Steuersatz des
     Jahres (Steuern durch Ergebnis vor Steuern, bei Verlust null).
  3  Verschuldung und Liquiditaet: langfristige und gesamte Schulden zu
     Eigenkapital, Nettoschulden, Current und Quick Ratio, Zinsdeckung.
  4  Cashflow ueber vier Quartale: Free Cashflow, FCF-Marge, Cash
     Conversion, Ausschuettungsquote, Rueckkaeufe.
  5  Wachstum: Umsatz und EPS gegen das Vorjahresquartal ueber acht
     Quartale, Beschleunigung ueber drei aufeinanderfolgende Quartale,
     Umsatz-CAGR ueber 3 und 5 Jahre, EPS-CAGR ueber 3 Jahre, EPS-Stabilitaet
     als Naeherung nach IBD-Art (1 stabil bis 99 sprunghaft).
  6  Verwaesserung: verwaesserte Aktienzahl ueber 1 und 3 Jahre;
     aktienbasierte Verguetung in Prozent des Umsatzes.
  7  Piotroski F-Score aus Jahreswerten, nicht fuer Banken und Versicherer.
  8  Altman Z fuer Industriefirmen, nicht fuer Banken, Versicherer und
     Immobilien.
  9  Rule of 40: Umsatzwachstum der letzten vier Quartale plus FCF-Marge;
     gedacht fuer Software.
  10 Bewertung: Marktkapitalisierung, KGV, KUV, KBV, Enterprise Value,
     EV zu EBITDA, EV zu Umsatz, PEG mit dem EPS-Wachstum des letzten
     Geschaeftsjahrs, Cash, Nettokasse, Buchwert und FCF je Aktie,
     Dividendenrendite, FCF-Rendite.
  11 Streubesitz: Wert und Stichtag vom Deckblatt; die Aktienzahl daraus
     rechnet das Nachschlagen mit dem Kurs am Stichtag.
  12 Immobilien: FFO nach NAREIT; Banken: Kernkapitalquote, Risikovorsorge
     zu Krediten, Einlagen gegen das Vorjahr.
  13 Die SMR-Bausteine samt Rang legt ibd_ratings.py ab.

Aufruf:
  python kennzahlen_fundament.py --selbsttest     ohne Netz
"""

import argparse
import bisect
import math
import sys
from datetime import date, timedelta
from functools import lru_cache

from config import CFG

CFGF = CFG["fundament_kennzahlen"]


# ---------------------------------------------------------------------------
# Kleine Helfer
# ---------------------------------------------------------------------------

def _ok(x):
    return x is not None and x == x


@lru_cache(maxsize=1 << 17)
def _dat_text(s):
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _dat(x):
    # BEFUND 14.09.2026: 22 Millionen Aufrufe je Nachtbau, zwei Drittel der
    # Rechenzeit der Kennzahlen im Datumsparsen; dieselben Tage kehren wieder.
    return _dat_text(str(x)[:10])


def _tage(a, b):
    da, db = _dat(a), _dat(b)
    return (db - da).days if (da and db) else None


def _abstand(a, b, ersatz=99999, betrag=True):
    """Tage von a bis b, als Betrag oder mit Vorzeichen; ersatz ohne beide
    Daten. (Nie `_tage(...) or ersatz`: null Tage sind ein Wert.)"""
    t = _tage(a, b)
    if t is None:
        return ersatz
    return abs(t) if betrag else t


def _r(x, stellen=4):
    return round(float(x), stellen) if _ok(x) else None


def _quote(zaehler, nenner, positiv=True, stellen=4):
    """Zaehler durch Nenner; None ohne beide Werte, bei Nenner null oder, mit
    positiv, bei einem Nenner unter null."""
    if not (_ok(zaehler) and _ok(nenner)) or nenner == 0 or (positiv and nenner < 0):
        return None
    return round(float(zaehler) / float(nenner), stellen)


def _pct(neu, alt, stellen=1):
    """Veraenderung in Prozent, nur bei positiver Basis."""
    if not (_ok(neu) and _ok(alt)) or alt <= 0:
        return None
    return round((float(neu) / float(alt) - 1.0) * 100.0, stellen)


def reihe(reihen, kennzahl, typ):
    return (reihen.get(kennzahl) or {}).get(typ) or []


def auf_13_wochen(start, end, wert, grenze=None):
    """Wie ibd_ratings.auf_13_wochen (W7): ein 14-Wochen-Quartal mal 13 durch 14."""
    grenze = int(grenze or CFGF["quartal_lang_tage"])
    t = _tage(start, end)
    if t is None or not _ok(wert):
        return wert
    return wert * 13.0 / 14.0 if t > grenze else wert


def eintrag_um(liste, ende, von, bis):
    """Der Eintrag, dessen Ende von bis bis Tage vor `ende` liegt (der
    naechste an der Mitte)."""
    beste, abstand = None, None
    mitte = (von + bis) / 2.0
    for e in liste:
        t = _tage(e[1], ende)
        if t is not None and von <= t <= bis and (abstand is None or abs(t - mitte) < abstand):
            beste, abstand = e, abs(t - mitte)
    return beste


def eintrag_bei(liste, ende, toleranz=None):
    """Der Eintrag zum Stichtag `ende`, hoechstens toleranz Tage daneben."""
    toleranz = int(CFGF["stichtag_toleranz_tage"] if toleranz is None else toleranz)
    beste, abstand = None, None
    for e in liste:
        t = _tage(e[1], ende)
        if t is not None and abs(t) <= toleranz and (abstand is None or abs(t) < abstand):
            beste, abstand = e, abs(t)
    return beste


def _wert(e):
    return e[2] if e is not None else None


def vier_quartale(liste):
    """Summe der vier juengsten Quartale, wenn sie lueckenlos aufeinander
    folgen. Rueckgabe (Summe, Ende) oder (None, None)."""
    if len(liste) < 4:
        return None, None
    teil = liste[-4:]
    for a, b in zip(teil, teil[1:]):
        t = _tage(a[1], b[1])
        if t is None or not (80 <= t <= 100):
            return None, None
    return sum(e[2] for e in teil), teil[-1][1]


def vier_quartale_bis(liste, ende):
    """Summe der vier lueckenlosen Quartale, deren juengstes am Stichtag
    `ende` endet (fuer den Vorjahresvergleich)."""
    idx = next((i for i, e in enumerate(liste) if e[1] == ende), None)
    if idx is None or idx < 3:
        return None
    s, _ = vier_quartale(liste[:idx + 1])
    return s


def zwoelf_monate(reihen, kennzahl, q=None, fy=None, heute=None):
    """Der Wert der letzten zwoelf Monate: vier lueckenlose Quartale, sonst
    das juengste Geschaeftsjahr. Rueckgabe (Wert, Ende, Art "4q" oder "fy")."""
    q = reihe(reihen, kennzahl, "Q") if q is None else q
    fy = reihe(reihen, kennzahl, "FY") if fy is None else fy
    s, ende = vier_quartale(q)
    if s is not None:
        return s, ende, "4q"
    if fy:
        return fy[-1][2], fy[-1][1], "fy"
    return None, None, None


# ---------------------------------------------------------------------------
# Einheiten und Aktiensplits
# ---------------------------------------------------------------------------

# Uebliche Split-Verhaeltnisse (neue Aktien je alte Aktie); Reverse-Splits als Kehrwert.
SPLIT_FAKTOREN = (1.5, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 25, 30, 35, 40, 50, 60, 75, 80, 100, 150, 200, 250,
                  300, 400, 500, 1000)


# Zehnerpotenzen, um die eine Zahl im Fundament verrutscht sein kann: Aktien
# in Tausend oder Millionen, Gewinn je Aktie in Cent oder um Tausend und
# Millionen verschoben, Geldbetraege in Tausend oder Millionen.
STUFEN_AKTIEN = (-6, -3, 3, 6)
STUFEN_EPS = (-6, -3, -2, 2, 3, 6)
STUFEN_GELD = (-6, -3, 3, 6)


def _median(werte):
    w = sorted(werte)
    n = len(w)
    if not n:
        return None
    return w[n // 2] if n % 2 else (w[n // 2 - 1] + w[n // 2]) / 2.0


def _stufe(verhaeltnis, stufen, toleranz):
    """Die Zehnerpotenz aus stufen, um die verhaeltnis von eins abweicht, wenn
    es hoechstens toleranz Dekaden daneben liegt; sonst None."""
    if not (_ok(verhaeltnis) and verhaeltnis > 0):
        return None
    lg = math.log10(verhaeltnis)
    k = int(round(lg))
    return k if k in stufen and abs(lg - k) <= toleranz else None


def _mit(e, wert=None, erst=None):
    """Der Eintrag mit neuem Wert und, wo die Reihe sie fuehrt, neuer
    Erstfassung."""
    liste = list(e)
    if wert is not None:
        liste[2] = wert
    if erst is not None and len(liste) > 6:
        liste[6] = erst
    return tuple(liste)


def _original(e, frist=150):
    """Die Erstfassung eines Eintrags, wenn sie aus dem Bericht der Periode
    selbst stammt (hoechstens frist Tage nach dem Periodenende eingereicht);
    sonst None. Nur Erstfassungen aus derselben Zeit haben sicher dieselbe
    Stueckelung wie die Aktienzahl vom Deckblatt."""
    if len(e) < 9 or not (_ok(e[6]) and e[6] > 0) or not e[8]:
        return None
    t = _tage(e[1], e[8])
    return e[6] if t is not None and 0 <= t <= frist else None


def _aktien_index(a_liste):
    """Die ausstehenden Aktienzahlen (Deckblatt und Bilanz) als sortierte
    Liste (Tagesnummer des Stichtags, Wert), je in der Erstfassung aus dem
    Bericht ihrer Zeit; Reihen ohne Fassungen mit dem Wert."""
    raus = []
    for e in a_liste:
        d = _dat(e[1])
        if d is None:
            continue
        w = _original(e)
        if w is None and len(e) < 9 and _ok(e[2]) and e[2] > 0:
            w = e[2]
        if w is not None:
            raus.append((d.toordinal(), w))
    raus.sort()
    return raus


def _aktien_bezug(index, ende, max_tage=120, anzahl=3):
    """Median der hoechstens drei naechstgelegenen ausstehenden Aktienzahlen
    aus _aktien_index im Umkreis von max_tage Tagen um den Stichtag."""
    d = _dat(ende)
    if d is None or not index:
        return None
    o = d.toordinal()
    von = bisect.bisect_left(index, (o - max_tage, -math.inf))
    bis = bisect.bisect_right(index, (o + max_tage, math.inf))
    nah = sorted((abs(i[0] - o), i[1]) for i in index[von:bis])
    return _median([w for _, w in nah[:anzahl]])


def _q4_neu(q_liste, fy):
    """Index und neuer Wert des aus dem Geschaeftsjahr berechneten vierten
    Quartals, wenn die drei amtlichen Quartale davor vorliegen; sonst None."""
    idx = next((i for i, e in enumerate(q_liste) if len(e) > 3 and e[3] == "berechnet"
                and _abstand(e[1], fy[1]) <= 7), None)
    if idx is None:
        return None
    drei = [e for e in q_liste if len(e) > 3 and e[3] != "berechnet" and _ok(e[2])
            and _abstand(fy[0], e[1], -1, betrag=False) > 0 and _abstand(e[1], fy[1], -1, betrag=False) >= 60]
    if len(drei) != 3:
        return None
    return idx, fy[2] - sum(e[2] for e in drei)


def _verhaeltnis_sauber(r):
    """Ob ein Verhaeltnis zweier Aktienzahlen eins oder ein uebliches
    Split-Verhaeltnis ist (auf 3 Prozent)."""
    if not (_ok(r) and r > 0):
        return False
    f = r if r >= 1 else 1.0 / r
    return f < 1.05 or any(abs(sf / f - 1.0) <= 0.03 for sf in SPLIT_FAKTOREN)


def einheiten_bereinigt(reihen):
    """Verrutschte Zehnerpotenzen in verwaesserter Aktienzahl, Gewinn je
    Aktie und Nettogewinn.

    BEFUND 14.09.2026: Rund 2 Prozent der Perioden mit allen drei Werten
    passen nicht zusammen, fast immer um eine glatte Zehnerpotenz: EPS mal
    Aktienzahl ergibt ein Tausendstel oder das Tausendfache des
    Nettogewinns. Es sind Markierungsfehler in den Berichten selbst (Badger
    Meter meldet die Aktienzahl der Geschaeftsjahre 2020 bis 2022 mit 29.230
    statt 29,2 Millionen, National Retail Properties 2020 und 2021 mit 172,8
    Milliarden, Halliburton den Gewinn je Aktie mit 290.000 statt 0,29 Dollar,
    National Beverage in Cent). Manche berichtigt eine spaetere Einreichung,
    manche nie. Auch die ausstehenden Aktien vom Deckblatt sind nicht
    fehlerfrei (Packaging Corporation, April 2023: 89,9 Milliarden statt
    Millionen). Ein Split aendert Aktienzahl und EPS gegenlaeufig, das
    Produkt bleibt; EPS mal Aktien durch Gewinn verraet deshalb Einheiten,
    nicht Splits. Den Nettogewinn aus Vollmachtsunterlagen (der haeufigste
    Fehler) nimmt schon ibd_ratings.ohne_vollmachtszahlen heraus.

    Die Probe EPS mal Aktien durch Nettogewinn rechnet mit den Werten
    derselben Fassung (letzte mit letzten, erste mit ersten). Eine Aktienzahl
    wird nur geaendert, wenn zwei Hinweise dieselbe Potenz nennen:
      1. Letzte Fassung: Die Probe weicht um 10^3 oder 10^6 ab, und die
         Aktienzahl weicht um dieselbe Potenz vom Deckblatt ab (nur bei nie
         neu eingereichten Perioden, deren Erstfassung aus dem Bericht ihrer
         Zeit stammt) oder vom Median der uebrigen Aktienzahlen binnen 400
         Tagen. Ohne Probe (EPS oder Gewinn fehlen) muessen Deckblatt und
         Median beide dieselbe Potenz nennen.
      2. Erste Fassung einer umgeschriebenen Periode: Probe der Erstfassung
         und Deckblatt nennen dieselbe Potenz; ohne Probe das Deckblatt, wenn
         das Verhaeltnis zur letzten Fassung danach ein uebliches
         Split-Verhaeltnis oder eins ist. So zaehlt eine Berichtigung nicht
         als Split, und ein Split in falscher Einheit bleibt erkennbar.
      3. Hat eine spaetere Fassung eine richtige Aktienzahl um genau eine
         solche Potenz umgeschrieben (Probe der Erstfassung stimmig, der
         letzten nicht; ohne Gewinn: Deckblatt stimmig und EPS nicht
         gegenlaeufig umgeschrieben), gilt die Erstfassung.
    Danach Gewinn je Aktie und Nettogewinn: Weicht die Probe noch um eine
    Potenz ab, ist der Nettogewinn falsch, wenn er um dieselbe Potenz neben
    dem Ergebnis vor Steuern liegt; sonst entscheidet der Median der
    stimmigen Perioden derselben Art binnen 800 Tagen zwischen EPS und
    Nettogewinn. Bleibt es offen, wird nichts geaendert und die Periode als
    unstimmig gemeldet. Nach einer Aenderung des Nettogewinns wird das daraus
    berechnete vierte Quartal des Geschaeftsjahres neu gerechnet.

    Rueckgabe (Reihen, Korrekturen [(Kennzahl, Typ, Ende, Faktor)], unstimmige
    Perioden [(Typ, Ende)])."""
    korrekturen, unstimmig = [], []
    if "aktien_verwaessert" not in reihen and "eps_verwaessert" not in reihen:
        return reihen, korrekturen, unstimmig
    neu = dict(reihen)
    for k in ("aktien_verwaessert", "eps_verwaessert", "nettogewinn"):
        if k in reihen:
            neu[k] = {t: list(v) for t, v in reihen[k].items()}
    a_index = _aktien_index(reihe(reihen, "aktien_ausstehend", "B"))
    je_ende = {k: {typ: {e[1]: e for e in reihe(reihen, k, typ)} for typ in ("Q", "FY")}
               for k in ("eps_verwaessert", "nettogewinn")}

    def probe(typ, ende, s_wert, stelle):
        """EPS mal Aktien durch Nettogewinn mit der Fassung an stelle (2 die
        letzte, 6 die erste); None ohne belastbare Werte."""
        ee, nn = je_ende["eps_verwaessert"][typ].get(ende), je_ende["nettogewinn"][typ].get(ende)
        if ee is None or nn is None or len(ee) <= stelle or len(nn) <= stelle:
            return None
        e_w, n_w = ee[stelle], nn[stelle]
        if not (_ok(e_w) and _ok(n_w) and _ok(s_wert)) or abs(e_w) < 0.05 or n_w == 0 or s_wert <= 0:
            return None
        q = e_w * s_wert / n_w
        return q if q > 0 else None

    # 1 bis 3: die Aktienzahl
    s = neu.get("aktien_verwaessert") or {}
    alle_s = [(typ, i, e) for typ in ("Q", "FY") for i, e in enumerate(s.get(typ) or [])]
    tagnr = [(_dat(x[1]).toordinal() if _dat(x[1]) else None) for _t, _i, x in alle_s]
    for nr, (typ, i, e) in enumerate(alle_s):
        w = e[2]
        if not (_ok(w) and w > 0):
            continue
        erst = e[6] if len(e) > 6 and _ok(e[6]) and e[6] > 0 else None
        umgeschrieben = erst is not None and abs(math.log10(w / erst)) > math.log10(1.4)
        orig = _original(e)
        bezug = _aktien_bezug(a_index, e[1]) if (orig is not None or erst is None) else None
        o = tagnr[nr]
        nachbarn = ([x[2] for j, (_t2, _j2, x) in enumerate(alle_s) if j != nr and _ok(x[2]) and x[2] > 0
                     and tagnr[j] is not None and abs(tagnr[j] - o) <= 400] if o is not None else [])
        med = _median(nachbarn) if len(nachbarn) >= 3 else None
        # 1: die letzte Fassung
        q = probe(typ, e[1], w, 2)
        k_q = _stufe(q, STUFEN_AKTIEN, 0.2)
        k_a = _stufe(w / bezug, STUFEN_AKTIEN, 0.35) if bezug and not umgeschrieben else None
        k_n = _stufe(w / med, STUFEN_AKTIEN, 0.35) if med else None
        # eine umgeschriebene Periode, deren Erstfassung um dieselbe Potenz neben dem Deckblatt lag und die nur um ein
        # Split-Verhaeltnis umgeschrieben wurde, steht auch in der letzten Fassung in dieser Einheit
        k_s = (_stufe(orig / bezug, STUFEN_AKTIEN, 0.35) if umgeschrieben and orig is not None and bezug
               and _verhaeltnis_sauber(w / erst) else None)
        if (q is not None and k_q is not None and k_q in (k_a, k_n, k_s)) or (q is None and k_a is not None and k_a == k_n):
            k = k_q if q is not None else k_a
            w = w * 10.0 ** -k
            if erst is not None and not umgeschrieben:
                erst = erst * 10.0 ** -k
            s[typ][i] = _mit(e, w, erst)
            korrekturen.append(("aktien_verwaessert", typ, e[1], 10.0 ** -k))
            e = s[typ][i]
            q = probe(typ, e[1], w, 2)
            umgeschrieben = erst is not None and abs(math.log10(w / erst)) > math.log10(1.4)
        if not umgeschrieben:
            continue
        # 2: die erste Fassung einer umgeschriebenen Periode
        q_e = probe(typ, e[1], erst, 6)
        k_qe = _stufe(q_e, STUFEN_AKTIEN, 0.2)
        k_ae = _stufe(orig / bezug, STUFEN_AKTIEN, 0.35) if orig is not None and bezug else None
        k_e = None
        if q_e is not None:
            if k_qe is not None and (k_qe == k_ae or (k_ae is None and q is not None and 0.5 <= q <= 2.0
                                                      and _verhaeltnis_sauber(w / (erst * 10.0 ** -k_qe)))):
                k_e = k_qe
        elif k_ae is not None and _verhaeltnis_sauber(w / (erst * 10.0 ** -k_ae)):
            k_e = k_ae
        if k_e is not None:
            erst = erst * 10.0 ** -k_e
            s[typ][i] = _mit(e, erst=erst)
            continue
        # 3: eine richtige Erstfassung spaeter um eine Potenz umgeschrieben
        k_r = _stufe(w / erst, STUFEN_AKTIEN, 0.05)
        if k_r is None:
            continue
        falsch = False
        if q_e is not None and q is not None:
            falsch = 0.5 <= q_e <= 2.0 and _stufe(q, (k_r,), 0.2) is not None
        elif orig is not None and bezug and abs(math.log10(orig / bezug)) < 0.35:
            ep = je_ende["eps_verwaessert"][typ].get(e[1])
            falsch = (ep is not None and len(ep) > 6 and _ok(ep[6]) and _ok(ep[2]) and abs(ep[6]) >= 0.02
                      and abs(ep[2] - ep[6]) <= 0.006 + 0.03 * abs(ep[6]))
        if falsch:
            s[typ][i] = _mit(e, erst, erst)
            korrekturen.append(("aktien_verwaessert", typ, e[1], 10.0 ** -k_r))

    # 4: Gewinn je Aktie und Nettogewinn
    if "eps_verwaessert" not in neu or "nettogewinn" not in neu or "aktien_verwaessert" not in neu:
        return neu, korrekturen, unstimmig
    geaendert_ng = []
    for typ in ("Q", "FY"):
        ep = {e[1]: i for i, e in enumerate(neu["eps_verwaessert"].get(typ) or [])}
        ng = {e[1]: i for i, e in enumerate(neu["nettogewinn"].get(typ) or [])}
        vs = {e[1]: e for e in reihe(reihen, "ergebnis_vor_steuern", typ)}
        perioden = []
        for e in neu["aktien_verwaessert"].get(typ) or []:
            if e[1] not in ep or e[1] not in ng or not (_ok(e[2]) and e[2] > 0):
                continue
            ee = neu["eps_verwaessert"][typ][ep[e[1]]]
            nn = neu["nettogewinn"][typ][ng[e[1]]]
            if not (_ok(ee[2]) and _ok(nn[2])) or abs(ee[2]) < 0.05 or nn[2] == 0:
                continue
            q = ee[2] * e[2] / nn[2]
            if q > 0:
                perioden.append((e[1], q))
        stimmig = [p for p in perioden if 0.5 <= p[1] <= 2.0]
        for ende, q in perioden:
            k = _stufe(q, set(STUFEN_EPS) | set(STUFEN_GELD), 0.2)
            if k is None:
                continue
            i_e, i_n = ep[ende], ng[ende]
            ee, nn = neu["eps_verwaessert"][typ][i_e], neu["nettogewinn"][typ][i_n]
            v = vs.get(ende)
            nah = [p for p in stimmig if _abstand(p[0], ende) <= 800]
            med_e = _median([abs(neu["eps_verwaessert"][typ][ep[p[0]]][2]) for p in nah])
            med_n = _median([abs(neu["nettogewinn"][typ][ng[p[0]]][2]) for p in nah])
            if k in STUFEN_GELD and v is not None and _ok(v[2]) and v[2] != 0 \
                    and _stufe(abs(nn[2] / v[2]), (-k,), 0.5) is not None:
                ziel = ("nettogewinn", i_n, nn, 10.0 ** k)
            elif k in STUFEN_EPS and len(nah) >= 2 and med_e and _stufe(abs(ee[2]) / med_e, (k,), 0.7) is not None:
                ziel = ("eps_verwaessert", i_e, ee, 10.0 ** -k)
            elif k in STUFEN_GELD and len(nah) >= 2 and med_n and _stufe(abs(nn[2]) / med_n, (-k,), 0.7) is not None:
                ziel = ("nettogewinn", i_n, nn, 10.0 ** k)
            else:
                unstimmig.append((typ, ende))
                continue
            kz, idx, alt, faktor = ziel
            wert = alt[2] * faktor
            erst = alt[6] if len(alt) > 6 and _ok(alt[6]) else None
            if erst is not None and wert and _stufe(abs(erst / wert), set(STUFEN_EPS) | set(STUFEN_GELD), 0.2) is not None:
                erst = wert
            neu[kz][typ][idx] = _mit(alt, wert, erst)
            korrekturen.append((kz, typ, ende, faktor))
            if kz == "nettogewinn":
                geaendert_ng.append((typ, ende))
    q_ng = neu["nettogewinn"].get("Q") or []
    for fy in neu["nettogewinn"].get("FY") or []:
        if not any((t == "FY" and ende == fy[1]) or (t == "Q" and _abstand(fy[0], ende, -1, betrag=False) > 0
                                                     and _abstand(ende, fy[1], -1, betrag=False) >= 0)
                   for t, ende in geaendert_ng):
            continue
        r = _q4_neu(q_ng, fy)
        if r is not None:
            q_ng[r[0]] = _mit(q_ng[r[0]], r[1])
    return neu, korrekturen, unstimmig


def split_haufen(reihen, toleranz=0.03):
    """Aktiensplits aus den Umrechnungen der verwaesserten Aktienzahl.

    BEFUND 14.09.2026: Die Letztfassungen des Fundaments sind NICHT
    durchgehend splitbereinigt. Eine Periode wird nur so lange neu
    eingereicht, wie sie als Vergleich in Berichten steht; was davor zuletzt
    eingereicht wurde, bleibt in der alten Stueckelung (NVIDIA: das Quartal
    bis 30.04.2023 mit 2,49 Milliarden Aktien neben dem Quartal bis
    30.07.2023 mit 24,99 Milliarden; CrowdStrike: Split 4 zu 1 im Sommer 2026,
    drei Quartale davor noch ungeteilt). Den Split verraet die Periode
    selbst: Ihre letzte Fassung ist das f-fache der ersten (ein f-tel beim
    Reverse-Split), und der Split liegt zwischen ihrer ersten und letzten
    Einreichung. Kandidaten mit demselben Faktor, deren Zeitfenster sich
    ueberschneiden, gelten als derselbe Split. Berichtigte Einheitenfehler
    hat einheiten_bereinigt vorher unschaedlich gemacht.

    Rueckgabe [(Faktor, spaetester erster Tag, fruehester letzter Tag,
    [(Typ, Ende) der umgerechneten Perioden], [(erster Tag, letzter Tag) je
    Periode])]. Zwei Splits desselben Faktors binnen rund eines Jahres
    koennen dabei in einem Haufen landen; welche Tage wirklich gelten,
    entscheidet _split_wahl an den Werten."""
    kandidaten = []
    for typ in ("Q", "FY"):
        for e in reihe(reihen, "aktien_verwaessert", typ):
            if len(e) < 9 or not (_ok(e[6]) and e[6] > 0 and _ok(e[2]) and e[2] > 0 and e[7] and e[8]):
                continue
            r = e[2] / e[6]
            if abs(math.log(r)) < math.log(1.4):
                continue
            f = r if r > 1 else 1.0 / r
            nett = min(SPLIT_FAKTOREN, key=lambda s: abs(s / f - 1.0))
            if abs(nett / f - 1.0) > toleranz:
                continue
            kandidaten.append((nett if r > 1 else 1.0 / nett, e[8], e[7], typ, e[1]))
    haufen = []
    for faktor, erst, letzt, typ, ende in sorted(kandidaten, key=lambda k: k[2]):
        for h in haufen:
            if abs(h[0] / faktor - 1.0) < 1e-9 and erst < h[2] and letzt > h[1]:
                h[1], h[2] = max(h[1], erst), min(h[2], letzt)
                h[3].append((typ, ende))
                h[4].append((erst, letzt))
                break
        else:
            haufen.append([faktor, erst, letzt, [(typ, ende)], [(erst, letzt)]])
    return [tuple(h) for h in haufen]


def split_ereignisse(reihen, toleranz=0.03):
    """Die erkannten Splits als [(Faktor, fruehester letzter Tag)]."""
    return [(h[0], h[2]) for h in split_haufen(reihen, toleranz)]


def _eps_gegenlaeufig(reihen, faktor, perioden):
    """Wurde der Gewinn je Aktie der umgerechneten Perioden gegenlaeufig
    umgerechnet? True (ein Split), False (nur die Aktienzahl), None ohne
    Hinweis."""
    ja = nein = 0
    for typ, ende in perioden:
        e = next((x for x in reihe(reihen, "eps_verwaessert", typ) if x[1] == ende), None)
        if e is None or len(e) < 7 or not (_ok(e[2]) and _ok(e[6])) or abs(e[6]) < 0.02:
            continue
        soll = e[6] / faktor
        if abs(e[2] - soll) <= 0.006 + 0.005 / faktor + 0.03 * abs(soll):
            ja += 1
        elif abs(e[2] - e[6]) <= 0.006 + 0.03 * abs(e[6]):
            nein += 1
    return None if ja == nein == 0 else ja >= nein


def _split_wahl(liste, haufen, hoechstens=None):
    """Welche Splits in dieser Aktienreihe gelten und ab welchem
    Einreichungstag: Schritt fuer Schritt kommt der Split dazu, der die
    Reihe am staerksten glaettet (Summe der Betraege der logarithmischen
    Spruenge zwischen aufeinanderfolgenden Perioden), bis keiner mehr
    glaettet. Moeglich sind je Faktor der Haufen die Einreichungstage der
    Reihe, die im Zeitfenster mindestens einer umgeschriebenen Periode
    liegen, dazu der frueheste letzte Tag jedes Haufens; bei gleicher
    Glaettung gilt der spaetere Tag. Ein Split wirkt auf alles, was zuletzt
    vor seinem Tag eingereicht wurde. Rueckgabe [(Faktor, Tag)]."""
    pkt = sorted((e[1], math.log(e[2]), e[7] if len(e) > 7 and e[7] else "") for e in liste
                 if _ok(e[2]) and e[2] > 0)
    if len(pkt) < 2:
        return []
    logs = [p[1] for p in pkt]
    tage_reihe = sorted({p[2] for p in pkt if p[2]})
    optionen = []
    for faktor in sorted({h[0] for h in haufen}):
        fenster = [w for h in haufen if h[0] == faktor for w in h[4]]
        tage = {t for t in tage_reihe if any(a < t <= b for a, b in fenster)}
        tage |= {h[2] for h in haufen if h[0] == faktor}
        optionen += [(math.log(faktor), faktor, t) for t in sorted(tage)]
    versatz = [0.0] * len(pkt)
    gewaehlt = []
    for _schritt in range(hoechstens or 3 * len(haufen) + 2):
        spruenge = [logs[i + 1] + versatz[i + 1] - logs[i] - versatz[i] for i in range(len(pkt) - 1)]
        beste = None
        for lf, faktor, tag in optionen:
            gewinn = 0.0
            for i, d in enumerate(spruenge):
                s = (1 if pkt[i + 1][2] and pkt[i + 1][2] < tag else 0) - (1 if pkt[i][2] and pkt[i][2] < tag else 0)
                if s:
                    gewinn += abs(d) - abs(d + s * lf)
            schluessel = (round(gewinn, 9), tag)
            if gewinn > 1e-9 and (beste is None or schluessel > beste[0]):
                beste = (schluessel, lf, faktor, tag)
        if beste is None:
            break
        _, lf, faktor, tag = beste
        for i, p in enumerate(pkt):
            if p[2] and p[2] < tag:
                versatz[i] += lf
        gewaehlt.append((faktor, tag))
    return gewaehlt


def split_bereinigt(reihen):
    """Die Reihen mit verwaesserter Aktienzahl und EPS in heutiger
    Stueckelung. Je Periodenart waehlt _split_wahl, welche Splits ab welchem
    Einreichungstag gelten; eine Periodenart ohne Aktienreihe nimmt die Wahl
    der anderen.

    BEFUND 14.09.2026 zur ersten Fassung (jeder erkannte Split ab der
    fruehesten letzten Einreichung, fuer beide Periodenarten): Sie machte
    die Reihen von 616 der 1.011 Firmen mit erkanntem Split rauer statt
    glatter. Drei Ursachen: berichtigte Tausender-Fehler zaehlten als Split
    (Brown und Brown), eine Umrechnung nur der Jahreswerte traf auch die
    richtigen Quartale (Badger Meter), und bei zwei Reverse-Splits kurz
    hintereinander lag der wahre Umrechnungstag vor dem erkannten (AgEagle).

    Den Gewinn je Aktie rechnet ein Split nur um, wenn umgeschriebene
    Perioden seines Faktors ihn gegenlaeufig umgeschrieben haben, oder, ohne
    Hinweis darauf, wenn der Faktor keine Einheit sein kann (1.000 und ein
    Tausendstel, 10^6). Rueckgabe (Reihen, [(Faktor, Umrechnungstag)] der
    Splits, die mindestens einen Wert geaendert haben; derselbe Faktor binnen
    200 Tagen zaehlt einmal, mit dem frueheren Tag)."""
    haufen = split_haufen(reihen)
    if not haufen:
        return reihen, []
    eps_ok = {}
    for faktor in {h[0] for h in haufen}:
        arten = [_eps_gegenlaeufig(reihen, h[0], h[3]) for h in haufen if h[0] == faktor]
        eps_ok[faktor] = True in arten or (False not in arten and _stufe(faktor, STUFEN_AKTIEN, 0.01) is None)
    s = reihen.get("aktien_verwaessert") or {}
    ereignisse = {typ: _split_wahl(s[typ], haufen) for typ in ("Q", "FY") if s.get(typ)}
    neu = dict(reihen)
    wirksam = set()
    for k, mal in (("aktien_verwaessert", True), ("eps_verwaessert", False)):
        if k not in reihen:
            continue
        neu[k] = {}
        for typ, liste in reihen[k].items():
            ev = ereignisse.get(typ)
            if ev is None:
                ev = ereignisse.get("FY" if typ == "Q" else "Q") or []
            aus = []
            for e in liste:
                f = 1.0
                if ev and len(e) > 7 and e[7]:
                    for faktor, tag in ev:
                        if e[7] < tag and (mal or eps_ok[faktor]):
                            f *= faktor
                            wirksam.add((faktor, tag))
                aus.append(e if f == 1.0 else _mit(e, e[2] * f if mal else e[2] / f))
            neu[k][typ] = aus
    liste = []
    for faktor, tag in sorted(wirksam, key=lambda p: (p[1], p[0])):
        if not any(abs(f0 / faktor - 1.0) < 1e-9 and _abstand(t0, tag) <= 200 for f0, t0 in liste):
            liste.append((faktor, tag))
    return neu, liste


def waehrung(reihen):
    """Die Waehrung der Geldbetraege einer Firma: die haeufigste Einheit ohne
    Aktien, Verhaeltnisse und Werte je Aktie."""
    zaehler = {}
    for k in reihen.values():
        for t in k.values():
            for e in t:
                einheit = e[5] if len(e) > 5 else None
                if einheit and "/" not in einheit and einheit not in ("shares", "pure"):
                    zaehler[einheit] = zaehler.get(einheit, 0) + 1
    return max(zaehler.items(), key=lambda p: p[1])[0] if zaehler else None


# ---------------------------------------------------------------------------
# Die Punkte
# ---------------------------------------------------------------------------

def margen(reihen, umsatz_q, umsatz_fy, branche=""):
    """Punkt 1: je juengstes Quartal und Geschaeftsjahr. Die Bruttomarge nur
    beim gewoehnlichen Umsatz (Banken, Versicherer und Immobilien haben
    keinen Bruttogewinn im Sinn des Handels)."""
    raus = {}
    for art, uliste, typ in (("q", umsatz_q, "Q"), ("fy", umsatz_fy, "FY")):
        if not uliste or not uliste[-1][2] or uliste[-1][2] <= 0:
            continue
        ende, umsatz = uliste[-1][1], uliste[-1][2]
        raus[f"ende_{art}"] = ende

        def bei(k):
            return _wert(eintrag_bei(reihe(reihen, k, typ), ende, 0))
        if not branche:
            bg = bei("bruttogewinn")
            if bg is None and bei("umsatzkosten") is not None:
                bg = umsatz - bei("umsatzkosten")
            raus[f"brutto_{art}"] = _quote(bg, umsatz)
        raus[f"operativ_{art}"] = _quote(bei("operatives_ergebnis"), umsatz)
        raus[f"vorsteuer_{art}"] = _quote(bei("ergebnis_vor_steuern"), umsatz)
        raus[f"netto_{art}"] = _quote(bei("nettogewinn"), umsatz)
    return raus


def bilanz(reihen):
    """Die Bilanzwerte des juengsten Stichtags der Bilanzsumme, alle vom
    selben Tag (Eigenheit 2)."""
    bs = reihe(reihen, "bilanzsumme", "B")
    if not bs:
        return {}
    ende = bs[-1][1]
    raus = {"ende": ende, "bilanzsumme": bs[-1][2]}
    for k in ("umlaufvermoegen", "kasse", "kurzfristige_anlagen", "vorraete", "verbindlichkeiten",
              "kurzfristige_verbindlichkeiten", "langfristige_schulden", "kurzfristige_schulden", "eigenkapital",
              "gewinnruecklagen", "einlagen", "kredite", "kernkapitalquote"):
        raus[k] = _wert(eintrag_bei(reihe(reihen, k, "B"), ende))
    return raus


def renditen(reihen, bil):
    """Punkt 2. ROE wie im SMR (Jahresgewinn durch juengstes Eigenkapital)."""
    raus = {}
    ng_fy = reihe(reihen, "nettogewinn", "FY")
    ek = reihe(reihen, "eigenkapital", "B")
    if ng_fy and ek and ek[-1][2] > 0:
        raus["roe"] = _quote(ng_fy[-1][2], ek[-1][2])
    if ng_fy and bil.get("bilanzsumme"):
        raus["roa"] = _quote(ng_fy[-1][2], bil["bilanzsumme"])
    op_fy = reihe(reihen, "operatives_ergebnis", "FY")
    if op_fy and bil.get("eigenkapital") is not None:
        ende = op_fy[-1][1]
        ebt = _wert(eintrag_bei(reihe(reihen, "ergebnis_vor_steuern", "FY"), ende, 0))
        st = _wert(eintrag_bei(reihe(reihen, "steuern", "FY"), ende, 0))
        satz = 0.0
        if _ok(ebt) and _ok(st) and ebt > 0:
            satz = min(1.0, max(0.0, st / ebt))
        schulden = _summe(bil.get("langfristige_schulden"), bil.get("kurzfristige_schulden"))
        kapital = bil["eigenkapital"] + (schulden or 0.0) - (bil.get("kasse") or 0.0)
        if kapital > 0:
            raus["roic"] = _quote(op_fy[-1][2] * (1.0 - satz), kapital)
            raus["steuersatz"] = _r(satz)
    return raus


def _summe(*werte):
    gueltig = [w for w in werte if _ok(w)]
    return sum(gueltig) if gueltig else None


def schulden_liquiditaet(reihen, bil):
    """Punkt 3."""
    raus = {}
    ek = bil.get("eigenkapital")
    ltd, ktd = bil.get("langfristige_schulden"), bil.get("kurzfristige_schulden")
    schulden = _summe(ltd, ktd)
    raus["schulden"] = schulden
    if ek is not None and ek > 0:
        raus["lt_schulden_ek"] = _quote(ltd, ek)
        raus["schulden_ek"] = _quote(schulden, ek)
    if schulden is not None and bil.get("kasse") is not None:
        raus["nettoschulden"] = schulden - bil["kasse"] - (bil.get("kurzfristige_anlagen") or 0.0)
    kv = bil.get("kurzfristige_verbindlichkeiten")
    uv = bil.get("umlaufvermoegen")
    raus["current_ratio"] = _quote(uv, kv)
    if uv is not None:
        raus["quick_ratio"] = _quote(uv - (bil.get("vorraete") or 0.0), kv)
    op, ende_op, _ = zwoelf_monate(reihen, "operatives_ergebnis")
    za, ende_za, _ = zwoelf_monate(reihen, "zinsaufwand")
    if _ok(op) and _ok(za) and za > 0 and ende_op == ende_za:
        raus["zinsdeckung"] = _quote(op, za, stellen=2)
    return raus


def cashflow(reihen, umsatz_12m):
    """Punkt 4 und die Verguetung aus Punkt 6, ueber zwoelf Monate."""
    raus = {}
    cfo, ende, art = zwoelf_monate(reihen, "operativer_cashflow")
    capex, ende_c, _ = zwoelf_monate(reihen, "investitionen")
    ng, ende_ng, _ = zwoelf_monate(reihen, "nettogewinn")
    u, ende_u = umsatz_12m
    raus["cfo"] = cfo
    raus["art"] = art
    raus["ende"] = ende
    if _ok(cfo) and _ok(capex) and ende == ende_c:
        fcf = cfo - capex
        raus["fcf"] = fcf
        if ende == ende_u:
            raus["fcf_marge"] = _quote(fcf, u)
    if _ok(cfo) and ende == ende_ng and _ok(ng) and ng > 0:
        raus["cash_conversion"] = _quote(cfo, ng, stellen=2)
    div, ende_d, _ = zwoelf_monate(reihen, "dividenden_gezahlt")
    if _ok(div) and ende_d == ende_ng and _ok(ng) and ng > 0:
        raus["ausschuettung"] = _quote(div, ng)
    raus["dividenden"] = div if ende_d == ende else None
    rk, ende_r, _ = zwoelf_monate(reihen, "aktienrueckkauf")
    raus["rueckkauf"] = rk if ende_r == ende else None
    sbc, ende_s, _ = zwoelf_monate(reihen, "aktienbasierte_verguetung")
    if _ok(sbc) and ende_s == ende_u:
        raus["sbc_umsatz"] = _quote(sbc, u)
    raus["nettogewinn"] = ng
    raus["nettogewinn_ende"] = ende_ng
    return raus


def wachstum_liste(liste, anzahl=None, lang=None):
    """Punkt 5: Wachstum gegen das Vorjahresquartal fuer die juengsten
    anzahl Quartale, juengstes zuerst: [(Ende, Prozent oder None)]. Mit der
    Umrechnung der 14-Wochen-Quartale wie im EPS-Rang."""
    anzahl = int(anzahl or CFGF["wachstum_quartale"])
    adj = [(e[0], e[1], auf_13_wochen(e[0], e[1], e[2], lang)) for e in liste]
    raus = []
    for s, ende, w in reversed(adj[-anzahl:]):
        v = eintrag_um(adj, ende, 340, 390)
        raus.append((ende, _pct(w, v[2] if v else None)))
    return raus


def beschleunigung(liste):
    """Steigt die Wachstumsrate ueber drei aufeinanderfolgende Quartale?
    "beschleunigt", "verlangsamt", "uneinheitlich" oder None (keine drei
    lueckenlosen Quartale mit Wert)."""
    if len(liste) < 3:
        return None
    (e0, p0), (e1, p1), (e2, p2) = liste[0], liste[1], liste[2]
    if None in (p0, p1, p2):
        return None
    for a, b in ((e1, e0), (e2, e1)):
        t = _tage(a, b)
        if t is None or not (80 <= t <= 100):
            return None
    if p0 > p1 > p2:
        return "beschleunigt"
    if p0 < p1 < p2:
        return "verlangsamt"
    return "uneinheitlich"


def cagr(liste_fy, jahre):
    """Jaehrliches Wachstum ueber `jahre` Geschaeftsjahre, beide Werte positiv."""
    if not liste_fy:
        return None
    neu = liste_fy[-1]
    alt = eintrag_um(liste_fy, neu[1], 365 * jahre - 30, 365 * jahre + 45)
    if alt is None or not (_ok(neu[2]) and _ok(alt[2])) or neu[2] <= 0 or alt[2] <= 0:
        return None
    return round(((neu[2] / alt[2]) ** (1.0 / jahre) - 1.0) * 100.0, 1)


def eps_stabilitaet(liste, heute, min_q=None, max_q=None):
    """Punkt 5, Naeherung nach IBD-Art: die Streuung der Quartals-EPS um ihre
    Trendgerade ueber hoechstens fuenf Jahre, als Prozent des mittleren
    Betrags, auf 1 bis 99 begrenzt (1 stabil, 99 sprunghaft). Rueckgabe
    (Wert, Zahl der Quartale) oder (None, n)."""
    min_q, max_q = int(min_q or CFGF["stabilitaet_min_quartale"]), int(max_q or CFGF["stabilitaet_max_quartale"])
    grenze = (heute - timedelta(days=5 * 366 + 120)).isoformat()
    teil = [e for e in liste if e[1] >= grenze and _ok(e[2])][-max_q:]
    n = len(teil)
    if n < min_q:
        return None, n
    t0 = _dat(teil[0][1])
    xs = [(_dat(e[1]) - t0).days for e in teil]
    ys = [e[2] for e in teil]
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 0.0
    a = my - b * mx
    res = [y - (a + b * x) for x, y in zip(xs, ys)]
    streuung = math.sqrt(sum(r * r for r in res) / (n - 2)) if n > 2 else 0.0
    mittel = sum(abs(y) for y in ys) / n
    if mittel <= 0:
        return None, n
    return int(round(max(1.0, min(99.0, streuung / mittel * 100.0)))), n


def verwaesserung(reihen):
    """Punkt 6: Veraenderung der verwaesserten Aktienzahl gegen ein und drei
    Jahre zuvor, aus den Quartalen, sonst aus den Jahreswerten."""
    raus = {}
    for typ in ("Q", "FY"):
        liste = reihe(reihen, "aktien_verwaessert", typ)
        if not liste:
            continue
        neu = liste[-1]
        v1 = eintrag_um(liste, neu[1], 340, 390)
        v3 = eintrag_um(liste, neu[1], 1060, 1135)
        if v1 is None and v3 is None:
            continue
        raus["aktien_1j_pct"] = _pct(neu[2], v1[2]) if v1 else None
        raus["aktien_3j_pct"] = _pct(neu[2], v3[2]) if v3 else None
        raus["aktien_ende"] = neu[1]
        break
    return raus


# Kurzzeichen der neun Signale, wie sie in der Ablage stehen, und ihr Text
F_SIGNALE = {"roa": "Rendite auf das Vermögen positiv", "cfo": "operativer Cashflow positiv",
             "roa_plus": "Rendite auf das Vermögen gestiegen", "cfo_ng": "operativer Cashflow über dem Nettogewinn",
             "hebel": "langfristige Verschuldung nicht gestiegen", "cr": "Current Ratio gestiegen",
             "aktien": "keine zusätzlichen Aktien", "brutto": "Bruttomarge gestiegen",
             "umschlag": "Kapitalumschlag gestiegen"}


def f_score(reihen, umsatz_fy):
    """Punkt 7: Piotroski F-Score aus den zwei juengsten Geschaeftsjahren.
    Rueckgabe (Punkte, bewertbare Signale, Kurzzeichen der erfuellten
    Signale, siehe F_SIGNALE) oder (None, 0, [])."""
    ng = reihe(reihen, "nettogewinn", "FY")
    if len(ng) < 2:
        return None, 0, []
    t, t1 = ng[-1], ng[-2]
    if not (300 <= (_tage(t1[1], t[1]) or 0) <= 430):
        return None, 0, []
    bs = reihe(reihen, "bilanzsumme", "B")
    a_t = _wert(eintrag_bei(bs, t[1]))
    a_t1 = _wert(eintrag_bei(bs, t1[1]))
    a_t2 = _wert(eintrag_um(bs, t1[1], 330, 400))

    def fy(k, e):
        return _wert(eintrag_bei(reihe(reihen, k, "FY"), e[1], 10))

    def b(k, e):
        return _wert(eintrag_bei(reihe(reihen, k, "B"), e[1]))
    signale = {}
    roa_t = _quote(t[2], a_t1)
    roa_t1 = _quote(t1[2], a_t2)
    if roa_t is not None:
        signale["roa"] = roa_t > 0
    cfo_t = fy("operativer_cashflow", t)
    if cfo_t is not None:
        signale["cfo"] = cfo_t > 0
    if roa_t is not None and roa_t1 is not None:
        signale["roa_plus"] = roa_t > roa_t1
    if cfo_t is not None:
        signale["cfo_ng"] = cfo_t > t[2]
    ltd_t, ltd_t1 = b("langfristige_schulden", t), b("langfristige_schulden", t1)
    if ltd_t is not None and ltd_t1 is not None and a_t and a_t1:
        signale["hebel"] = ltd_t / a_t <= ltd_t1 / a_t1
    cr_t = _quote(b("umlaufvermoegen", t), b("kurzfristige_verbindlichkeiten", t))
    cr_t1 = _quote(b("umlaufvermoegen", t1), b("kurzfristige_verbindlichkeiten", t1))
    if cr_t is not None and cr_t1 is not None:
        signale["cr"] = cr_t > cr_t1
    ak_t, ak_t1 = fy("aktien_verwaessert", t), fy("aktien_verwaessert", t1)
    if ak_t is not None and ak_t1 is not None:
        signale["aktien"] = ak_t <= ak_t1
    u_t = _wert(eintrag_bei(umsatz_fy, t[1], 10))
    u_t1 = _wert(eintrag_bei(umsatz_fy, t1[1], 10))

    def bruttomarge(e, u):
        bg = fy("bruttogewinn", e)
        if bg is None and fy("umsatzkosten", e) is not None and u is not None:
            bg = u - fy("umsatzkosten", e)
        return _quote(bg, u)
    bm_t, bm_t1 = bruttomarge(t, u_t), bruttomarge(t1, u_t1)
    if bm_t is not None and bm_t1 is not None:
        signale["brutto"] = bm_t > bm_t1
    at_t, at_t1 = _quote(u_t, a_t1), _quote(u_t1, a_t2)
    if at_t is not None and at_t1 is not None:
        signale["umschlag"] = at_t > at_t1
    if not signale:
        return None, 0, []
    return sum(1 for v in signale.values() if v), len(signale), [k for k, v in signale.items() if v]


def altman_z(bil, op_12m, umsatz_12m, mk):
    """Punkt 8: Altman Z (1968) fuer Industriefirmen."""
    ta = bil.get("bilanzsumme")
    uv, kv = bil.get("umlaufvermoegen"), bil.get("kurzfristige_verbindlichkeiten")
    re_ = bil.get("gewinnruecklagen")
    tl = bil.get("verbindlichkeiten")
    if tl is None and bil.get("eigenkapital") is not None and ta:
        tl = ta - bil["eigenkapital"]
    if not all(_ok(x) for x in (ta, uv, kv, re_, tl, op_12m, umsatz_12m, mk)) or ta <= 0 or tl <= 0:
        return None
    z = (1.2 * (uv - kv) / ta + 1.4 * re_ / ta + 3.3 * op_12m / ta + 0.6 * mk / tl + 1.0 * umsatz_12m / ta)
    return round(z, 2)


def kennzahlen(reihen, umsatz_q=None, umsatz_fy=None, branche="", kurs=None, filer_typ=None, heute=None, cfg=None):
    """Alle Punkte fuer eine Firma. umsatz_q und umsatz_fy: die Umsatzreihen
    nach dem Begriff der Branche (ibd_ratings.umsatz_reihe); branche "",
    "bank", "versicherer" oder "immobilien". kurs: der letzte Schluss aus dem
    RS-Universum. Rueckgabe dict, Werte ohne Grundlage fehlen."""
    cfg = cfg or CFGF
    heute = heute or date.today()
    reihen, korrekturen, unstimmig = einheiten_bereinigt(reihen)
    reihen, splits = split_bereinigt(reihen)
    uq = reihe(reihen, "umsatz", "Q") if umsatz_q is None else umsatz_q
    ufy = reihe(reihen, "umsatz", "FY") if umsatz_fy is None else umsatz_fy
    raus = {"waehrung": waehrung(reihen), "branche": branche or None,
            "splits": [[round(f, 4), erste] for f, erste in splits],
            "einheiten": [[k, t, e, f] for k, t, e, f in korrekturen],
            "unstimmig": len(unstimmig) or None,
            "unstimmig_ende": max(e for _, e in unstimmig) if unstimmig else None}
    raus.update({"marge_" + k: v for k, v in margen(reihen, uq, ufy, branche).items()})
    bil = bilanz(reihen)
    raus["bilanz_ende"] = bil.get("ende")
    raus.update(renditen(reihen, bil))
    raus.update(schulden_liquiditaet(reihen, bil))
    u_12, ende_u, art_u = zwoelf_monate(reihen, "umsatz", q=uq, fy=ufy)
    raus["umsatz_12m"] = u_12
    raus["umsatz_12m_art"] = art_u
    cf = cashflow(reihen, (u_12, ende_u))
    for k in ("fcf", "fcf_marge", "cash_conversion", "ausschuettung", "sbc_umsatz"):
        raus[k] = cf.get(k)
    raus["cashflow_ende"] = cf.get("ende")
    raus["cashflow_art"] = cf.get("art")

    # Punkt 5
    raus["umsatz_vj"] = [[e, p] for e, p in wachstum_liste(uq)]
    raus["eps_vj"] = [[e, p] for e, p in wachstum_liste(reihe(reihen, "eps_verwaessert", "Q"))]
    raus["umsatz_trend"] = beschleunigung(wachstum_liste(uq))
    raus["eps_trend"] = beschleunigung(wachstum_liste(reihe(reihen, "eps_verwaessert", "Q")))
    raus["umsatz_cagr3"] = cagr(ufy, 3)
    raus["umsatz_cagr5"] = cagr(ufy, 5)
    raus["eps_cagr3"] = cagr(reihe(reihen, "eps_verwaessert", "FY"), 3)
    raus["eps_stabilitaet"], raus["stabilitaet_quartale"] = eps_stabilitaet(reihe(reihen, "eps_verwaessert", "Q"), heute)

    # Punkt 6
    raus.update(verwaesserung(reihen))

    # Punkt 7 und 8
    if branche in ("bank", "versicherer"):
        raus["fscore_grund"] = "nicht anwendbar auf Banken und Versicherer"
    else:
        raus["fscore"], raus["fscore_bewertbar"], raus["fscore_erfuellt"] = f_score(reihen, ufy)

    # Punkt 9
    if art_u == "4q":
        u_vj = vier_quartale_bis(uq, (eintrag_um(uq, ende_u, 340, 390) or (None, None))[1])
        wg = _pct(u_12, u_vj, 1)
        if wg is not None and raus.get("fcf_marge") is not None:
            raus["rule40"] = round(wg + raus["fcf_marge"] * 100.0, 1)
        raus["umsatz_12m_vj_pct"] = wg

    # Punkt 10 und 8: nur mit Kurs, inlaendisch, in Dollar
    aktien = reihe(reihen, "aktien_ausstehend", "B")
    grund = None
    if filer_typ != "inland_usgaap":
        grund = "Auslandsemittent, Waehrung und ADR-Verhaeltnis passen nicht zum Kurs"
    elif raus["waehrung"] is None:
        grund = "Waehrung der Zahlen unbekannt"
    elif raus["waehrung"] != "USD":
        grund = f"Zahlen in {raus['waehrung']}, nicht in Dollar"
    elif not (_ok(kurs) and kurs > 0):
        grund = "kein Kurs"
    elif not aktien or _abstand(aktien[-1][1], heute, betrag=False) > int(cfg["aktien_hoechstalter_tage"]):
        grund = "keine aktuelle Aktienzahl vom Deckblatt"
    if grund:
        raus["bewertung_grund"] = grund
    else:
        n = aktien[-1][2]
        mk = kurs * n
        raus["aktien_ausstehend"] = n
        raus["aktien_stand"] = aktien[-1][1]
        raus["mk"] = mk
        ng = cf.get("nettogewinn")
        if _ok(ng) and ng > 0:
            raus["kgv"] = _quote(mk, ng, stellen=2)
        raus["kuv"] = _quote(mk, u_12, stellen=2)
        if (bil.get("eigenkapital") or 0) > 0:
            raus["kbv"] = _quote(mk, bil["eigenkapital"], stellen=2)
        ev = mk + (raus.get("schulden") or 0.0) - (bil.get("kasse") or 0.0)
        raus["ev"] = ev
        op, ende_op, _ = zwoelf_monate(reihen, "operatives_ergebnis")
        ab, ende_ab, _ = zwoelf_monate(reihen, "abschreibungen")
        if _ok(op) and _ok(ab) and ende_op == ende_ab and op + ab > 0:
            raus["ev_ebitda"] = _quote(ev, op + ab, stellen=2)
        raus["ev_umsatz"] = _quote(ev, u_12, stellen=2)
        eps_fy = reihe(reihen, "eps_verwaessert", "FY")
        if raus.get("kgv") is not None and len(eps_fy) >= 2:
            g = _pct(eps_fy[-1][2], eps_fy[-2][2], 2)
            if g is not None and g > 0 and (_tage(eps_fy[-2][1], eps_fy[-1][1]) or 0) in range(330, 400):
                raus["peg"] = round(raus["kgv"] / g, 2)
                raus["peg_wachstum"] = g
        if bil.get("kasse") is not None:
            raus["cash_je_aktie"] = _quote(bil["kasse"] + (bil.get("kurzfristige_anlagen") or 0.0), n, stellen=2)
            if raus.get("schulden") is not None:
                raus["nettokasse_je_aktie"] = _quote(bil["kasse"] + (bil.get("kurzfristige_anlagen") or 0.0)
                                                     - raus["schulden"], n, stellen=2)
        if bil.get("eigenkapital") is not None:
            raus["buchwert_je_aktie"] = _quote(bil["eigenkapital"], n, stellen=2)
        if cf.get("fcf") is not None:
            raus["fcf_je_aktie"] = _quote(cf["fcf"], n, stellen=2)
            raus["fcf_rendite"] = _quote(cf["fcf"], mk)
        if cf.get("dividenden") is not None:
            raus["div_rendite"] = _quote(cf["dividenden"], mk)
        if cf.get("rueckkauf") is not None:
            raus["rueckkauf_mk"] = _quote(cf["rueckkauf"], mk)
        if branche in ("bank", "versicherer", "immobilien"):
            raus["altman_grund"] = "nicht anwendbar auf Banken, Versicherer und Immobilien"
        else:
            raus["altman_z"] = altman_z(bil, op, u_12, mk)

    # Punkt 11
    sb = reihe(reihen, "streubesitz_wert", "B")
    if sb:
        raus["streubesitz_wert"] = sb[-1][2]
        raus["streubesitz_stichtag"] = sb[-1][1]
        raus["streubesitz_waehrung"] = sb[-1][5] if len(sb[-1]) > 5 else None

    # Punkt 12
    if branche == "immobilien":
        ng, ende_ng, _ = zwoelf_monate(reihen, "nettogewinn")
        ab, ende_ab, _ = zwoelf_monate(reihen, "abschreibungen")
        if _ok(ng) and _ok(ab) and ende_ng == ende_ab:
            wm, ende_w, _ = zwoelf_monate(reihen, "wertminderung_immobilien")
            gv, ende_g, _ = zwoelf_monate(reihen, "gewinn_immobilienverkauf")
            ffo = ng + ab + (wm if ende_w == ende_ng and _ok(wm) else 0.0) - (gv if ende_g == ende_ng and _ok(gv) else 0.0)
            raus["ffo"] = ffo
            if raus.get("aktien_ausstehend"):
                raus["ffo_je_aktie"] = _quote(ffo, raus["aktien_ausstehend"], stellen=2)
                if raus["ffo_je_aktie"] and raus["ffo_je_aktie"] > 0:
                    raus["p_ffo"] = _quote(kurs, raus["ffo_je_aktie"], stellen=2)
    if branche == "bank":
        raus["kernkapitalquote"] = bil.get("kernkapitalquote")
        rv, ende_rv, _ = zwoelf_monate(reihen, "risikovorsorge")
        raus["risikovorsorge_kredite"] = _quote(rv, bil.get("kredite"))
        ein = reihe(reihen, "einlagen", "B")
        if ein:
            v = eintrag_um(ein, ein[-1][1], 340, 390)
            raus["einlagen_vj_pct"] = _pct(ein[-1][2], v[2] if v else None)

    # Bei Banken und Versicherern gehoert das Kreditgeschaeft zum operativen
    # Cashflow und die Einlagen zu den Schulden: Free Cashflow, Enterprise
    # Value, Nettoschulden, Schuldenquoten und Zinsdeckung sagen dort nichts.
    if branche in ("bank", "versicherer"):
        for k in ("fcf", "fcf_marge", "cash_conversion", "fcf_rendite", "fcf_je_aktie", "ev", "ev_ebitda",
                  "ev_umsatz", "nettoschulden", "schulden", "schulden_ek", "lt_schulden_ek", "zinsdeckung",
                  "nettokasse_je_aktie", "rule40", "roic", "steuersatz", "current_ratio", "quick_ratio"):
            raus.pop(k, None)
        raus["finanz_grund"] = "Free Cashflow, Enterprise Value und Verschuldung sagen bei Banken und Versicherern nichts"

    # Rundung und leere Felder weg
    for k in list(raus):
        v = raus[k]
        if v is None or v == [] or (isinstance(v, float) and v != v):
            del raus[k]
        elif isinstance(v, float) and k in ("mk", "ev", "fcf", "nettoschulden", "schulden", "umsatz_12m",
                                            "streubesitz_wert", "ffo", "aktien_ausstehend"):
            raus[k] = int(round(v))
    return raus


def canslim(eps_q_pct, eps_cagr3_pct, roe, cfg=None):
    """Entscheidung 8: drei Haekchen, je [erfuellt oder None, Wert]. None heisst
    nicht berechenbar (etwa ein Vorjahresquartal bei null oder im Minus)."""
    cfg = cfg or CFGF

    def haken(wert, schwelle):
        return [None if wert is None else bool(wert >= schwelle), wert]
    return {"eps_q": haken(eps_q_pct, float(cfg["canslim_eps_quartal_pct"])),
            "eps_cagr3": haken(eps_cagr3_pct, float(cfg["canslim_eps_cagr3_pct"])),
            "roe": haken(round(roe * 100.0, 1) if _ok(roe) else None, float(cfg["canslim_roe_pct"]))}


# ---------------------------------------------------------------------------
# Selbsttest (ohne Netz)
# ---------------------------------------------------------------------------

def _q_reihe(werte, start=date(2020, 1, 1), einheit="USD", laenge=91):
    raus, d = [], start
    for w in werte:
        e = d + timedelta(days=laenge - 1)
        raus.append((d.isoformat(), e.isoformat(), float(w), "amtlich", "us-gaap", einheit))
        d = e + timedelta(days=1)
    return raus


def _fy_aus_q(q):
    raus = []
    for i in range(3, len(q), 4):
        raus.append((q[i - 3][0], q[i][1], sum(e[2] for e in q[i - 3:i + 1]), "amtlich", "us-gaap", q[i][5]))
    return raus


def _b_aus_q(q, werte):
    return [(None, e[1], float(w), "amtlich", "us-gaap", "USD") for e, w in zip(q, werte)]


def selbsttest() -> int:
    fehler = []

    def p(name, ok, zusatz=""):
        print(f"  {'ok  ' if ok else 'FEHL'} {name}" + (f": {zusatz}" if zusatz and not ok else ""))
        if not ok:
            fehler.append(name)

    print("Fundamentale Kennzahlen, Selbsttest (ohne Netz)")
    # Eine Firma ueber 24 Quartale ab 2020: Umsatz waechst je Quartal um 5 Prozent
    n = 24
    heute = date(2026, 1, 20)
    umsatz = _q_reihe([100.0 * 1.05 ** i for i in range(n)])
    q_ende = [e[1] for e in umsatz]
    brutto = _q_reihe([0.6 * e[2] for e in umsatz])
    op = _q_reihe([0.2 * e[2] for e in umsatz])
    ebt = _q_reihe([0.18 * e[2] for e in umsatz])
    steuern = _q_reihe([0.18 * 0.25 * e[2] for e in umsatz])
    ng = _q_reihe([0.135 * e[2] for e in umsatz])
    cfo = _q_reihe([0.25 * e[2] for e in umsatz])
    capex = _q_reihe([0.05 * e[2] for e in umsatz])
    div = _q_reihe([0.02 * e[2] for e in umsatz])
    sbc = _q_reihe([0.01 * e[2] for e in umsatz])
    zins = _q_reihe([2.0] * n)
    abschr = _q_reihe([3.0] * n)
    eps = [e for i, e in enumerate(_q_reihe([1.0 * 1.05 ** i for i in range(n)], einheit="USD/shares")) if i % 4 != 3]
    eps_fy = _fy_aus_q(_q_reihe([1.0 * 1.05 ** i for i in range(n)], einheit="USD/shares"))
    aktien_v = [e for i, e in enumerate(_q_reihe([1000.0 * 0.99 ** (i // 4) for i in range(n)], einheit="shares")) if i % 4 != 3]
    aktien_v_fy = [(e[0], e[1], 1000.0 * 0.99 ** j, "amtlich", "us-gaap", "shares")
                   for j, e in enumerate(_fy_aus_q(umsatz))]
    bil = lambda werte: _b_aus_q(umsatz, werte)  # noqa
    reihen = {
        "umsatz": {"Q": umsatz, "FY": _fy_aus_q(umsatz)},
        "bruttogewinn": {"Q": brutto, "FY": _fy_aus_q(brutto)},
        "operatives_ergebnis": {"Q": op, "FY": _fy_aus_q(op)},
        "ergebnis_vor_steuern": {"Q": ebt, "FY": _fy_aus_q(ebt)},
        "steuern": {"Q": steuern, "FY": _fy_aus_q(steuern)},
        "nettogewinn": {"Q": ng, "FY": _fy_aus_q(ng)},
        "operativer_cashflow": {"Q": cfo, "FY": _fy_aus_q(cfo)},
        "investitionen": {"Q": capex, "FY": _fy_aus_q(capex)},
        "dividenden_gezahlt": {"Q": div, "FY": _fy_aus_q(div)},
        "aktienbasierte_verguetung": {"Q": sbc, "FY": _fy_aus_q(sbc)},
        "zinsaufwand": {"Q": zins, "FY": _fy_aus_q(zins)},
        "abschreibungen": {"Q": abschr, "FY": _fy_aus_q(abschr)},
        "eps_verwaessert": {"Q": eps, "FY": eps_fy},
        "aktien_verwaessert": {"Q": aktien_v, "FY": aktien_v_fy},
        "bilanzsumme": {"B": bil([2000.0 + 50 * i for i in range(n)])},
        "umlaufvermoegen": {"B": bil([800.0 + 10 * i for i in range(n)])},
        "kurzfristige_verbindlichkeiten": {"B": bil([400.0] * n)},
        "vorraete": {"B": bil([100.0] * n)},
        "kasse": {"B": bil([300.0] * n)},
        "kurzfristige_anlagen": {"B": bil([50.0] * n)},
        "langfristige_schulden": {"B": bil([500.0 - 5 * i for i in range(n)])},
        "kurzfristige_schulden": {"B": bil([100.0] * n)},
        "eigenkapital": {"B": bil([1000.0 + 20 * i for i in range(n)])},
        "gewinnruecklagen": {"B": bil([600.0] * n)},
        "verbindlichkeiten": {"B": bil([1000.0 + 30 * i for i in range(n)])},
        "aktien_ausstehend": {"B": [(None, q_ende[-1], 950.0, "amtlich", "dei", "shares")]},
        "streubesitz_wert": {"B": [(None, q_ende[-3], 50000.0, "amtlich", "dei", "USD")]},
    }
    k = kennzahlen(reihen, kurs=100.0, filer_typ="inland_usgaap", heute=heute)
    p("Margen: Quartal und Geschaeftsjahr, brutto, operativ, vor Steuern, netto",
      k["marge_brutto_q"] == 0.6 and k["marge_operativ_q"] == 0.2 and k["marge_vorsteuer_fy"] == 0.18
      and k["marge_netto_fy"] == 0.135 and k["marge_ende_q"] == q_ende[-1], k)
    ng_fy = _fy_aus_q(ng)[-1][2]
    p("Renditen: ROE und ROA mit dem Jahresgewinn, ROIC mit dem Steuersatz des Jahres",
      k["roe"] == round(ng_fy / (1000 + 20 * 23), 4) and k["roa"] == round(ng_fy / (2000 + 50 * 23), 4)
      and k["steuersatz"] == 0.25
      and k["roic"] == round(_fy_aus_q(op)[-1][2] * 0.75 / ((1000 + 460) + (500 - 115 + 100) - 300), 4), k)
    p("Schulden und Liquiditaet vom selben Stichtag: Schulden zu Eigenkapital, Nettoschulden, Current und Quick Ratio",
      k["schulden_ek"] == round((385 + 100) / 1460, 4) and k["lt_schulden_ek"] == round(385 / 1460, 4)
      and k["nettoschulden"] == 485 - 300 - 50 and k["current_ratio"] == round(1030 / 400, 4)
      and k["quick_ratio"] == round(930 / 400, 4), k)
    u12 = sum(e[2] for e in umsatz[-4:])
    p("Zwoelf Monate aus vier lueckenlosen Quartalen: FCF, FCF-Marge, Cash Conversion, Ausschuettung, Verguetung",
      k["fcf"] == int(round(0.2 * u12)) and k["fcf_marge"] == 0.2 and k["cash_conversion"] == round(0.25 / 0.135, 2)
      and k["ausschuettung"] == round(0.02 / 0.135, 4) and k["sbc_umsatz"] == 0.01 and k["cashflow_art"] == "4q", k)
    p("Zinsdeckung: operatives Ergebnis durch Zinsaufwand ueber zwoelf Monate",
      k["zinsdeckung"] == round(sum(e[2] for e in op[-4:]) / 8.0, 2), k.get("zinsdeckung"))
    p("Wachstum: acht Quartale Umsatz gegen das Vorjahr, juengstes zuerst; EPS mit Luecke im vierten Quartal",
      len(k["umsatz_vj"]) == 8 and k["umsatz_vj"][0] == [q_ende[-1], round((1.05 ** 4 - 1) * 100, 1)]
      and all(pv == round((1.05 ** 4 - 1) * 100, 1) for _, pv in k["eps_vj"]) and len(k["eps_vj"]) == 8, k["eps_vj"])
    liste_luecke = [("2025-12-31", 30.0), ("2025-06-30", 20.0), ("2025-03-31", 10.0)]
    p("Beschleunigung: gleiches Wachstum ist uneinheitlich; ohne drei lueckenlose Quartale keine Aussage",
      k["umsatz_trend"] == "uneinheitlich" and k["eps_trend"] == "uneinheitlich" and beschleunigung(liste_luecke) is None,
      (k["umsatz_trend"], k.get("eps_trend")))
    p("Beschleunigung: steigende Raten ueber drei Quartale heissen beschleunigt, fallende verlangsamt",
      beschleunigung([("2025-12-31", 30.0), ("2025-09-30", 20.0), ("2025-06-30", 10.0)]) == "beschleunigt"
      and beschleunigung([("2025-12-31", 10.0), ("2025-09-30", 20.0), ("2025-06-30", 30.0)]) == "verlangsamt")
    p("CAGR: Umsatz ueber 3 und 5 Jahre aus den Geschaeftsjahren, EPS ueber 3 Jahre",
      k["umsatz_cagr3"] == round(((1.05 ** 12) ** (1 / 3) - 1) * 100, 1)
      and k["umsatz_cagr5"] == round(((1.05 ** 20) ** (1 / 5) - 1) * 100, 1) and k["eps_cagr3"] == k["umsatz_cagr3"], k)
    st, nq = eps_stabilitaet(_q_reihe([1.0 + 0.01 * i for i in range(20)], start=date(2021, 1, 1)), heute)
    st2, _ = eps_stabilitaet(_q_reihe([1.0 if i % 2 else 3.0 for i in range(20)], start=date(2021, 1, 1)), heute)
    p("EPS-Stabilitaet: eine gerade Reihe ist stabil (1), eine springende sprunghaft; zu wenige Quartale ohne Wert",
      st == 1 and nq == 20 and st2 >= 40 and eps_stabilitaet(_q_reihe([1.0] * 5), heute)[0] is None, (st, st2))
    p("Verwaesserung: ein Prozent weniger Aktien je Jahr, drei Jahre rund drei Prozent",
      k["aktien_1j_pct"] == -1.0 and k["aktien_3j_pct"] == round((0.99 ** 3 - 1) * 100, 1), k)
    p("F-Score: alle bewertbaren Signale aus zwei Geschaeftsjahren",
      k["fscore_bewertbar"] == 9 and 0 <= k["fscore"] <= 9 and "aktien" in k["fscore_erfuellt"], k)
    mk = 100.0 * 950
    p("Bewertung: Marktkapitalisierung aus Kurs mal Aktien vom Deckblatt, KGV aus dem Nettogewinn der vier Quartale",
      k["mk"] == 95000 and k["kgv"] == round(mk / sum(e[2] for e in ng[-4:]), 2) and k["kuv"] == round(mk / u12, 2)
      and k["kbv"] == round(mk / 1460, 2) and k["ev"] == int(round(mk + 485 - 300)), k)
    p("Bewertung: EV zu EBITDA, Werte je Aktie, Dividenden- und FCF-Rendite",
      k["ev_ebitda"] == round((mk + 185) / (sum(e[2] for e in op[-4:]) + 12), 2)
      and k["buchwert_je_aktie"] == round(1460 / 950, 2) and k["div_rendite"] == round(0.02 * u12 / mk, 4)
      and k["fcf_rendite"] == round(0.2 * u12 / mk, 4) and k["nettokasse_je_aktie"] == round((350 - 485) / 950, 2), k)
    p("PEG mit dem EPS-Wachstum des letzten Geschaeftsjahrs",
      k["peg"] == round(k["kgv"] / round((1.05 ** 4 - 1) * 100, 2), 2), k.get("peg"))
    p("Altman Z fuer Industriefirmen gerechnet",
      k["altman_z"] == altman_z(bilanz(reihen), sum(e[2] for e in op[-4:]), u12, mk) and k["altman_z"] > 0, k.get("altman_z"))
    p("Rule of 40: Umsatzwachstum der vier Quartale plus FCF-Marge",
      k["rule40"] == round(round((1.05 ** 4 - 1) * 100, 1) + 20.0, 1), k.get("rule40"))
    p("Streubesitz: Wert und Stichtag vom Deckblatt",
      k["streubesitz_wert"] == 50000 and k["streubesitz_stichtag"] == q_ende[-3], k)
    k_aus = kennzahlen(reihen, kurs=100.0, filer_typ="ausland_usgaap", heute=heute)
    p("Auslandsemittent: keine Bewertung mit dem Kurs, die Verhaeltnisse der Bilanz schon",
      "kgv" not in k_aus and "mk" not in k_aus and "altman_z" not in k_aus and k_aus["bewertung_grund"].startswith("Auslandsemittent")
      and k_aus["current_ratio"] == k["current_ratio"], k_aus.get("bewertung_grund"))
    reihen_eur = {kk: {t: [e[:5] + ("EUR" if e[5] == "USD" else e[5],) for e in v] for t, v in vv.items()} for kk, vv in reihen.items()}
    k_eur = kennzahlen(reihen_eur, kurs=100.0, filer_typ="inland_usgaap", heute=heute)
    p("Zahlen in Euro: keine Bewertung, die Waehrung ist genannt",
      k_eur["waehrung"] == "EUR" and k_eur["bewertung_grund"] == "Zahlen in EUR, nicht in Dollar" and "kgv" not in k_eur, k_eur.get("bewertung_grund"))
    k_alt = kennzahlen(reihen, kurs=100.0, filer_typ="inland_usgaap", heute=date(2027, 6, 1))
    p("Eine Aktienzahl vom Deckblatt, die aelter ist als die Frist, ergibt keine Marktkapitalisierung",
      k_alt.get("bewertung_grund") == "keine aktuelle Aktienzahl vom Deckblatt", k_alt.get("bewertung_grund"))
    k_bank = kennzahlen({**reihen, "einlagen": {"B": bil([5000.0 + 100 * i for i in range(n)])},
                         "kredite": {"B": bil([4000.0] * n)}, "risikovorsorge": {"Q": _q_reihe([10.0] * n)},
                         "kernkapitalquote": {"B": bil([0.12] * n)}},
                        branche="bank", kurs=100.0, filer_typ="inland_usgaap", heute=heute)
    p("Bank: Kernkapitalquote, Risikovorsorge zu Krediten, Einlagen gegen das Vorjahr; kein F-Score, kein Altman Z, keine Bruttomarge",
      k_bank["kernkapitalquote"] == 0.12 and k_bank["risikovorsorge_kredite"] == 0.01
      and k_bank["einlagen_vj_pct"] == _pct(5000 + 2300, 5000 + 1900) and "fscore" not in k_bank
      and "altman_z" not in k_bank and "marge_brutto_q" not in k_bank, k_bank)
    k_reit = kennzahlen({**reihen, "wertminderung_immobilien": {"Q": _q_reihe([1.0] * n)},
                         "gewinn_immobilienverkauf": {"Q": _q_reihe([2.0] * n)}},
                        branche="immobilien", kurs=100.0, filer_typ="inland_usgaap", heute=heute)
    ffo = sum(e[2] for e in ng[-4:]) + 12 + 4 - 8
    p("Immobilien: FFO nach NAREIT, je Aktie und Kurs dazu",
      k_reit["ffo"] == int(round(ffo)) and k_reit["ffo_je_aktie"] == round(ffo / 950, 2)
      and k_reit["p_ffo"] == round(100.0 / round(ffo / 950, 2), 2) and "altman_z" not in k_reit, k_reit)
    luecke = {**reihen, "umsatz": {"Q": umsatz[:-2] + umsatz[-1:], "FY": _fy_aus_q(umsatz)}}
    k_l = kennzahlen(luecke, kurs=100.0, filer_typ="inland_usgaap", heute=heute)
    p("Fehlt ein Quartal, gilt fuer zwoelf Monate das Geschaeftsjahr, gekennzeichnet",
      k_l["umsatz_12m_art"] == "fy" and "rule40" not in k_l, (k_l.get("umsatz_12m_art"), k_l.get("rule40")))
    # Splitbereinigung: CrowdStrike-Fall (4 zu 1, drei Quartale davor noch ungeteilt)
    def a(ende, erst, f_erst, letzt, f_letzt, einheit="shares"):
        return ("", ende, float(letzt), "amtlich", "us-gaap", einheit, float(erst), f_letzt, f_erst)
    crwd = {"aktien_verwaessert": {"Q": [a("2025-04-30", 248, "2025-06-04", 248, "2026-06-04"),
                                         a("2025-07-31", 250, "2025-08-28", 1000, "2026-08-27"),
                                         a("2025-10-31", 251, "2025-12-03", 251, "2025-12-03"),
                                         a("2026-04-30", 258, "2026-06-04", 258, "2026-06-04"),
                                         a("2026-07-31", 1044, "2026-08-27", 1044, "2026-08-27")]},
            "eps_verwaessert": {"Q": [a("2025-04-30", -0.44, "2025-06-04", -0.44, "2026-06-04", "USD/shares"),
                                      a("2026-07-31", 0.01, "2026-08-27", 0.01, "2026-08-27", "USD/shares")]}}
    b_crwd, ev_crwd = split_bereinigt(crwd)
    p("Split 4 zu 1: erkannt an der umgerechneten Periode, alles zuvor Eingereichte umgerechnet, Aktien mal 4, EPS durch 4",
      ev_crwd == [(4, "2026-08-27")]
      and [e[2] for e in b_crwd["aktien_verwaessert"]["Q"]] == [992.0, 1000.0, 1004.0, 1032.0, 1044.0]
      and [e[2] for e in b_crwd["eps_verwaessert"]["Q"]] == [-0.11, 0.01], (ev_crwd, b_crwd))
    nvda = {"aktien_verwaessert": {"Q": [a("2021-05-02", 632, "2021-05-26", 2528, "2022-05-27"),
                                         a("2023-04-30", 2490, "2023-05-26", 2490, "2024-05-29"),
                                         a("2023-07-30", 2499, "2023-08-28", 24990, "2024-08-28"),
                                         a("2024-07-28", 24848, "2024-08-28", 24848, "2025-08-27")],
                                   "FY": [a("2024-01-28", 2494, "2024-02-21", 24940, "2026-02-25")]}}
    b_nvda, ev_nvda = split_bereinigt(nvda)
    p("Zwei Splits (4 zu 1, dann 10 zu 1): jede Periode bekommt die Faktoren der Splits nach ihrer letzten Einreichung; "
      "genannt wird nur der Split, der einen Wert geaendert hat",
      split_ereignisse(nvda) == [(4, "2022-05-27"), (10, "2024-08-28")] and ev_nvda == [(10, "2024-08-28")]
      and [e[2] for e in b_nvda["aktien_verwaessert"]["Q"]] == [25280.0, 24900.0, 24990.0, 24848.0]
      and b_nvda["aktien_verwaessert"]["FY"][0][2] == 24940.0, (ev_nvda, b_nvda))
    rev = {"aktien_verwaessert": {"Q": [a("2025-03-31", 5000, "2025-05-10", 5000, "2025-05-10"),
                                        a("2025-06-30", 5100, "2025-08-10", 510, "2026-08-10"),
                                        a("2026-06-30", 520, "2026-08-10", 520, "2026-08-10")]}}
    b_rev, ev_rev = split_bereinigt(rev)
    p("Reverse-Split 1 zu 10 wird ebenso erkannt; eine Umrechnung ohne uebliches Verhaeltnis ist kein Split",
      ev_rev == [(0.1, "2026-08-10")] and round(b_rev["aktien_verwaessert"]["Q"][0][2], 6) == 500.0
      and split_ereignisse({"aktien_verwaessert": {"Q": [a("2025-06-30", 100, "2025-08-01", 263, "2026-08-01")]}}) == []
      and split_bereinigt(reihen)[1] == [], ev_rev)

    # Einheiten: Badger-Meter-Fall, die Jahres-Aktienzahl in Tausend gemeldet;
    # zwei Jahre nie berichtigt, eines spaeter berichtigt
    def b(ende, wert, filed):
        return (None, ende, float(wert), "amtlich", "dei", "shares", float(wert), filed, filed)
    bmi = {"aktien_verwaessert": {"FY": [a("2021-12-31", 29338, "2022-02-23", 29338, "2024-02-16"),
                                         a("2022-12-31", 29376, "2023-02-22", 29376, "2025-02-14"),
                                         a("2023-12-31", 29456, "2024-02-16", 29456000, "2026-02-17"),
                                         a("2025-12-31", 29569000, "2026-02-17", 29569000, "2026-02-17")],
                                  "Q": [a("2022-03-31", 29363326, "2022-04-28", 29363326, "2023-04-25"),
                                        a("2025-09-30", 29583384, "2025-10-22", 29583384, "2025-10-22")]},
           "aktien_ausstehend": {"B": [b("2021-12-31", 29100000, "2022-02-23"), b("2022-12-31", 29200000, "2023-02-22"),
                                       b("2023-12-31", 29300000, "2024-02-16"), b("2025-12-31", 29400000, "2026-02-17"),
                                       b("2022-03-31", 29150000, "2022-04-28"), b("2025-09-30", 29350000, "2025-10-22")]},
           "eps_verwaessert": {"FY": [a(e, w, f, w, f, "USD/shares") for e, w, f in
                                      (("2021-12-31", 2.08, "2022-02-23"), ("2022-12-31", 2.26, "2023-02-22"),
                                       ("2023-12-31", 3.14, "2024-02-16"), ("2025-12-31", 4.79, "2026-02-17"))],
                               "Q": [a("2022-03-31", 0.49, "2022-04-28", 0.49, "2023-04-25", "USD/shares"),
                                     a("2025-09-30", 1.19, "2025-10-22", 1.19, "2025-10-22", "USD/shares")]},
           "nettogewinn": {"FY": [a(e, w, f, w, f, "USD") for e, w, f in
                                  (("2021-12-31", 61.0e6, "2022-02-23"), ("2022-12-31", 66.4e6, "2023-02-22"),
                                   ("2023-12-31", 92.6e6, "2024-02-16"), ("2025-12-31", 141.6e6, "2026-02-17"))],
                           "Q": [a("2022-03-31", 14.4e6, "2022-04-28", 14.4e6, "2023-04-25", "USD"),
                                 a("2025-09-30", 35.2e6, "2025-10-22", 35.2e6, "2025-10-22", "USD")]}}
    r_bmi, korr_bmi, _ = einheiten_bereinigt(bmi)
    s_bmi, ev_bmi = split_bereinigt(r_bmi)
    p("Einheiten: eine Aktienzahl in Tausend wird gegen das Deckblatt zurueckgerechnet, eine spaeter berichtigte zaehlt nicht als Split, "
      "die richtigen Quartale bleiben",
      [round(e[2]) for e in s_bmi["aktien_verwaessert"]["FY"]] == [29338000, 29376000, 29456000, 29569000]
      and [e[2] for e in s_bmi["aktien_verwaessert"]["Q"]] == [29363326.0, 29583384.0] and ev_bmi == []
      and korr_bmi == [("aktien_verwaessert", "FY", "2021-12-31", 1000.0), ("aktien_verwaessert", "FY", "2022-12-31", 1000.0)],
      (korr_bmi, ev_bmi, s_bmi["aktien_verwaessert"]))
    spaet = {"aktien_verwaessert": {"Q": [a("2024-03-31", 5.0e6, "2024-05-01", 5.0e9, "2025-05-01")]},
             "eps_verwaessert": {"Q": [a("2024-03-31", 0.40, "2024-05-01", 0.40, "2025-05-01", "USD/shares")]},
             "aktien_ausstehend": {"B": [b("2024-03-31", 5.1e6, "2024-05-01")]}}
    r_sp, korr_sp, _ = einheiten_bereinigt(spaet)
    r_sp2, korr_sp2, _ = einheiten_bereinigt({**spaet, "nettogewinn": {"Q": [a("2024-03-31", 2.0e6, "2024-05-01", 2.0e6, "2025-05-01", "USD")]}})
    p("Einheiten: schreibt eine spaetere Fassung die richtige Aktienzahl auf das Tausendfache um, ohne den Gewinn je Aktie "
      "gegenlaeufig zu aendern, gilt die Erstfassung",
      r_sp["aktien_verwaessert"]["Q"][0][2] == 5.0e6 and korr_sp == [("aktien_verwaessert", "Q", "2024-03-31", 0.001)]
      and split_bereinigt(r_sp)[1] == [] and r_sp2["aktien_verwaessert"]["Q"][0][2] == 5.0e6 and korr_sp2 == korr_sp,
      (korr_sp, korr_sp2, r_sp))
    idx_t = _aktien_index([b("2024-03-31", 10.0, "2024-04-20"), b("2024-06-30", 20.0, "2024-07-20"),
                           b("2024-09-30", 30.0, "2024-10-20"), b("2024-12-31", 40.0, "2025-02-20"), (None, "kaputt", 5.0)])
    p("Aktien-Index: sortiert, die drei naechsten binnen 120 Tagen im Median, ohne Nachbarn None",
      _aktien_bezug(idx_t, "2024-08-15") == 25.0 and _aktien_bezug(idx_t, "2024-11-30") == 35.0
      and _aktien_bezug(idx_t, "2024-07-10") == 20.0
      and _aktien_bezug(idx_t, "2023-01-01") is None and _aktien_bezug([], "2024-08-15") is None
      and [w for _, w in idx_t] == [10.0, 20.0, 30.0, 40.0], idx_t)
    pkg = {"aktien_verwaessert": {"Q": [a("2024-03-31", 89.4e6, "2024-05-08", 89.4e6, "2025-05-08")]},
           "eps_verwaessert": {"Q": [a("2024-03-31", 2.31, "2024-05-08", 2.31, "2025-05-08", "USD/shares")]},
           "nettogewinn": {"Q": [a("2024-03-31", 206.5e6, "2024-05-08", 206.5e6, "2025-05-08", "USD")]},
           "aktien_ausstehend": {"B": [b("2024-03-31", 89.6e9, "2024-05-03"), b("2024-04-26", 89.5e9, "2024-05-03")]}}
    p("Einheiten: steht die Aktienzahl vom Deckblatt in falscher Einheit, die Probe EPS mal Aktien durch Gewinn aber stimmt, "
      "bleibt die Aktienzahl (Packaging Corporation)",
      einheiten_bereinigt(pkg)[1] == [] and einheiten_bereinigt(pkg)[0]["aktien_verwaessert"]["Q"][0][2] == 89.4e6,
      einheiten_bereinigt(pkg)[1])
    wrb_s = [a("2020-12-31", 188763, "2021-02-18", 283145, "2023-02-24"), a("2023-12-31", 273298, "2024-02-23", 409948000, "2026-02-27"),
             a("2024-12-31", 403224000, "2025-02-24", 403224000, "2026-02-27")]
    wrb = {"aktien_verwaessert": {"FY": wrb_s, "Q": [a("2020-06-30", 187.9e6, "2020-08-03", 187.9e6, "2021-08-02"),
                                                     a("2020-09-30", 187.7e6, "2020-11-05", 187.7e6, "2021-11-04"),
                                                     a("2021-03-31", 186.8e6, "2021-05-05", 280.2e6, "2022-05-03")]},
           "eps_verwaessert": {"FY": [a("2020-12-31", 2.12, "2021-02-18", 1.41, "2023-02-24", "USD/shares"),
                                      a("2023-12-31", 5.00, "2024-02-23", 3.34, "2026-02-27", "USD/shares"),
                                      a("2024-12-31", 4.36, "2025-02-24", 4.36, "2026-02-27", "USD/shares")]},
           "nettogewinn": {"FY": [a("2020-12-31", 400e6, "2021-02-18", 400e6, "2023-02-24", "USD"),
                                  a("2023-12-31", 1367e6, "2024-02-23", 1367e6, "2026-02-27", "USD"),
                                  a("2024-12-31", 1758e6, "2025-02-24", 1758e6, "2026-02-27", "USD")]},
           "aktien_ausstehend": {"B": [b("2020-12-31", 177e6, "2021-02-18"), b("2021-02-10", 177.5e6, "2021-02-18"),
                                       b("2023-12-31", 257e6, "2024-02-23"), b("2024-02-15", 256.5e6, "2024-02-23")]}}
    r_wrb, korr_wrb, _ = einheiten_bereinigt(wrb)
    p("Einheiten: eine Periode, deren beide Fassungen in Tausend stehen und die ein Split 3 zu 2 umgeschrieben hat, wird in beiden "
      "Fassungen zurueckgerechnet; beide Splits bleiben erkennbar (W. R. Berkley, 2022 und 2024)",
      [round(e[2]) for e in r_wrb["aktien_verwaessert"]["FY"]] == [283145000, 409948000, 403224000]
      and [round(e[6]) for e in r_wrb["aktien_verwaessert"]["FY"]] == [188763000, 273298000, 403224000]
      and [h[0] for h in split_haufen(r_wrb)] == [1.5, 1.5], (korr_wrb, r_wrb["aktien_verwaessert"]["FY"], split_haufen(r_wrb)))
    s_fizz = _q_reihe([93.6e6] * 6, einheit="shares")
    n_fizz = _q_reihe([30e6, 32e6, 34e6, 36e6, 38e6, 40e6])
    e_fizz = _q_reihe([0.32, 0.34, 36.0, 0.38, 0.41, 0.43], einheit="USD/shares")
    v_fizz = _q_reihe([w / 0.8 for w in (30e6, 32e6, 34e6, 36e6, 38e6, 40e6)])
    r_fz, korr_fz, un_fz = einheiten_bereinigt({"aktien_verwaessert": {"Q": s_fizz}, "eps_verwaessert": {"Q": e_fizz},
                                                "nettogewinn": {"Q": n_fizz}, "ergebnis_vor_steuern": {"Q": v_fizz}})
    p("Einheiten: Gewinn je Aktie in Cent gemeldet (EPS mal Aktien das Hundertfache des Gewinns) wird durch 100 geteilt",
      r_fz["eps_verwaessert"]["Q"][2][2] == 0.36 and korr_fz == [("eps_verwaessert", "Q", e_fizz[2][1], 0.01)] and un_fz == [],
      (korr_fz, un_fz))
    q_che = _q_reihe([10e6, 11e6, 12e6, 0.0])
    fy_che = (q_che[0][0], q_che[3][1], 46000.0, "amtlich", "us-gaap", "USD")
    q_che[3] = q_che[3][:2] + (46000.0 - 33e6, "berechnet") + q_che[3][4:]
    r_ch, korr_ch, _ = einheiten_bereinigt({
        "aktien_verwaessert": {"FY": [(fy_che[0], fy_che[1], 20e6, "amtlich", "us-gaap", "shares")]},
        "eps_verwaessert": {"FY": [(fy_che[0], fy_che[1], 2.30, "amtlich", "us-gaap", "USD/shares")]},
        "nettogewinn": {"Q": q_che, "FY": [fy_che]},
        "ergebnis_vor_steuern": {"FY": [(fy_che[0], fy_che[1], 57.5e6, "amtlich", "us-gaap", "USD")]}})
    p("Einheiten: Nettogewinn des Jahres in Tausend (gegen das Ergebnis vor Steuern) mal 1000, das berechnete vierte Quartal neu",
      r_ch["nettogewinn"]["FY"][0][2] == 46e6 and r_ch["nettogewinn"]["Q"][3][2] == 13e6
      and korr_ch == [("nettogewinn", "FY", fy_che[1], 1000.0)], (korr_ch, r_ch["nettogewinn"]))
    # Zwei Reverse-Splits kurz hintereinander (AgEagle-Fall): eine Periode
    # uebersprang den ersten und traegt beide zusammen (ein Tausendstel)
    uavs = {"aktien_verwaessert": {"Q": [a("2022-09-30", 113.6e6, "2022-11-14", 113.6e6, "2023-11-13"),
                                         a("2023-03-31", 4.48e6, "2024-05-15", 4.48e6, "2024-05-15"),
                                         a("2023-06-30", 96.2e6, "2023-08-14", 4.81e6, "2024-08-14"),
                                         a("2023-09-30", 111.1e6, "2023-11-13", 111100, "2024-11-19"),
                                         a("2024-03-31", 8.24e6, "2024-05-15", 164800, "2025-05-15"),
                                         a("2024-06-30", 12.4e6, "2024-08-14", 248000, "2025-08-14"),
                                         a("2024-09-30", 309350, "2024-11-19", 309350, "2025-11-14"),
                                         a("2025-03-31", 20.19e6, "2025-05-15", 20.19e6, "2026-05-15")]}}
    s_ua, ev_ua = split_bereinigt(einheiten_bereinigt(uavs)[0])
    p("Zwei Reverse-Splits: gewaehlt werden die Umrechnungstage, die die Reihe am glattesten machen, die Sammelumrechnung faellt weg",
      [round(e[2]) for e in s_ua["aktien_verwaessert"]["Q"]] == [113600, 89600, 96200, 111100, 164800, 248000, 309350, 20190000]
      and ev_ua == [(0.05, "2024-05-15"), (0.02, "2024-11-19")], (ev_ua, [round(e[2]) for e in s_ua["aktien_verwaessert"]["Q"]]))
    # Fuenf Splits 2 zu 1 in fuenf Jahren: mehr als 256 Moeglichkeiten, die
    # Suche geht Split fuer Split
    viele, splits_t = [], [date(2021 + j, 7, 1) for j in range(5)]
    for i in range(24):
        ende = date(2020, 3, 31) + timedelta(days=91 * i)
        f_e, f_l = ende + timedelta(days=30), min(ende + timedelta(days=395), date(2026, 8, 30))
        mal = lambda tag: 2 ** sum(1 for s_t in splits_t if s_t <= tag)  # noqa
        viele.append(a(ende.isoformat(), 100 * mal(f_e), f_e.isoformat(), 100 * mal(f_l), f_l.isoformat()))
    haufen_v = split_haufen({"aktien_verwaessert": {"Q": viele}})
    s_v, ev_v = split_bereinigt({"aktien_verwaessert": {"Q": viele}})
    p("Fuenf Splits 2 zu 1 im Jahresabstand: auch wenn die Zeitfenster zu weniger Haufen verschmelzen, steht die Reihe danach "
      "durchgehend in heutiger Stueckelung, und jeder Split ist einmal genannt",
      len(haufen_v) < 5 and all(round(e[2]) == 3200 for e in s_v["aktien_verwaessert"]["Q"]) and len(ev_v) == 5
      and [f for f, _ in ev_v] == [2] * 5,
      (len(haufen_v), [round(e[2]) for e in s_v["aktien_verwaessert"]["Q"]], ev_v))
    c = canslim(38.0, 12.0, 0.24)
    p("CAN-SLIM-Haekchen: Quartals-EPS ab 25, Dreijahres-CAGR ab 25, ROE ab 17 Prozent; ohne Wert offen",
      c == {"eps_q": [True, 38.0], "eps_cagr3": [False, 12.0], "roe": [True, 24.0]}
      and canslim(None, 25.0, 0.17)["eps_q"] == [None, None] and canslim(None, 25.0, 0.17)["roe"] == [True, 17.0], c)

    print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles bestanden.")
    return 1 if fehler else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Fundamentale Kennzahlen (Etappe 4).")
    ap.add_argument("--selbsttest", action="store_true")
    args = ap.parse_args()
    if args.selbsttest:
        return selbsttest()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
