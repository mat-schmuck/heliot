#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCANNER-ANSICHT: Einstellungen, Treffer, Ergebnisliste und Dateien
==================================================================
Der Reiter "Scanner" der Heliot-App (Mathias, 14.09.2026). Die Nachttabelle
baut scanner_daten.py. Dieser Baustein rechnet alles, was die App daraus
macht, ohne Streamlit und ohne Netz, und prueft sich selbst:

  GRUPPEN, FELDER    jedes einstellbare Merkmal aus Teil 2 mit Spalte,
                     Einheit und Erklaerung; die App baut daraus die
                     Bedienfelder
  AUSWAHL            die Strategien und Chart-Signale aus Teil 1
  voreinstellung()   was eine Strategie unten anhakt und eintraegt
                     (Mathias: "Wenn wir oben die Ausklapplisten mit einer
                     Strategie fuellen moechten wir dass die dafuer
                     notwendigen Felder unten befuellt werden
                     (anfaengertauglich!)")
  auswerten()        die Treffer
  zeilen()           die Ergebnisliste als Saetze; das Kuerzel verweist auf
                     die vollstaendigen Daten der Aktie (?aktie=)
  datei()            dieselbe Liste als CSV, Excel, OpenDocument, JSON,
                     HTML, Text oder Markdown

NUR WAS ANGEHAKT IST, STEHT IM ERGEBNIS (Mathias: "Alle Indikatoren, die bei
den Scanner nicht angehakt wurden, sollen beim Ergebnis auch nicht
aufscheinen"). Ein angehaktes Feld ohne Grenzen filtert nicht, es zeigt nur
seinen Wert.

DIE VORGABEN EINER STRATEGIE FILTERN NIE STRENGER ALS IHR MUSTER. Eingetragen
werden die Schwellen des Detektors, bei Toleranz um die Toleranz gelockert;
alles andere bleibt ohne Grenze und zeigt nur den Wert. So faellt durch die
Vorgabe kein Treffer heraus, den der Detektor gefunden hat. Der Selbsttest
prueft das am Trend Template gegen scanner_daten.trend_template.

ZAHLEN WIE MAN SIE TIPPT: "0,3", "1.000", "1000", "-5", "minus 5" und
"12 Prozent". Die Marktkapitalisierung steht in Milliarden Dollar (0,3 heisst
300 Millionen, 1000 heisst eine Billion, Mathias' Vorgabe).

Aufruf:
  python scanner_ansicht.py --selbsttest
"""

import argparse
import html as html_text
import io
import json
import math
import re
import sys
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

import numpy as np
import pandas as pd

import nachschlagen
import scanner_daten as sd
from config import CFG as ZENTRAL

SC = ZENTRAL["scanner"]
EPS = 1e-9

# ---------------------------------------------------------------------------
# Zahlen, Texte, Zeiten
# ---------------------------------------------------------------------------

_MINUS = chr(0x2212)


def zahl_lesen(text):
    """(Zahl oder None, Fehlertext oder "") aus einer Eingabe wie "0,3",
    "1.000", "-5", "minus 5" oder "12 Prozent". Leer ergibt (None, "")."""
    roh = str(text if text is not None else "").strip()
    if not roh:
        return None, ""
    t = roh.lower().replace(_MINUS, "-")
    for wort in ("prozentpunkte", "prozent", "dollar", "stück", "stueck", "milliarden", "millionen", "%", "$"):
        t = t.replace(wort, "")
    t = re.sub(r"\s+", "", t)
    vorzeichen = 1.0
    if t.startswith("minus"):
        vorzeichen, t = -1.0, t[5:]
    elif t.startswith("plus"):
        t = t[4:]
    if t.startswith("-"):
        vorzeichen, t = -vorzeichen, t[1:]
    elif t.startswith("+"):
        t = t[1:]
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", t):
        t = t.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d*,\d+|\d+,?", t):
        t = t.replace(",", ".")
    elif not re.fullmatch(r"\d*\.\d+|\d+\.?", t):
        return None, f"„{roh}“ ist keine Zahl"
    try:
        return vorzeichen * float(t), ""
    except ValueError:
        return None, f"„{roh}“ ist keine Zahl"


def zahl_eingabe(x):
    """Eine Zahl so, wie man sie in ein Feld tippt: 66,5 oder 25."""
    if x is None:
        return ""
    v = round(float(x), 4)
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return f"{v:.4f}".rstrip("0").rstrip(".").replace(".", ",")


def _num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def zahl(x, stellen=1):
    v = _num(x)
    return "unbekannt" if v is None else nachschlagen.zahl(v, stellen)


def mit_vorzeichen(x, stellen=1):
    """'plus 12,3' oder 'minus 4,5'; None heisst 'nicht berechenbar'."""
    v = _num(x)
    if v is None:
        return "nicht berechenbar"
    if round(abs(v), stellen) == 0:
        return nachschlagen.zahl(0, stellen)
    return ("plus " if v > 0 else "minus ") + nachschlagen.zahl(abs(v), stellen)


_MD_ZEICHEN = re.compile(r"([\\`*_\[\]<>#|~$])")


def md(text):
    """Text sicher fuer st.markdown: keine Formatierung, keine Formeln (das
    Dollarzeichen setzt sonst LaTeX), keine Pfeile aus "->" und kein langer
    Strich aus "--"."""
    t = nachschlagen.lesbar(text)
    t = t.replace("--", "-").replace("->", " zu ").replace("<-", " von ")
    return _MD_ZEICHEN.sub(lambda m: "\\" + m.group(1), t)


def _wahr(spalte):
    """True nur fuer echte Wahrheitswerte; None, NA und alles andere False."""
    return spalte.map(_ja).astype(bool)


def _ja(x):
    return x is True or (isinstance(x, np.bool_) and bool(x))


def _sp(df, name):
    """Eine Spalte; fehlt sie, eine Spalte aus None in derselben Laenge."""
    if name in df.columns:
        return df[name]
    return pd.Series([None] * len(df), index=df.index, dtype="object")


def _zahlen(df, name):
    return pd.to_numeric(_sp(df, name), errors="coerce").astype("float64")


def _zone(name):
    from zoneinfo import ZoneInfo
    return ZoneInfo(name)


def ny_jetzt(jetzt=None):
    tz = _zone(ZENTRAL["betrieb"]["zeitzone_boerse"])
    return jetzt.astimezone(tz) if jetzt else datetime.now(tz)


def naechster_handelstag(tag):
    """Der naechste Werktag; Feiertage kennt der Scanner nicht."""
    t = tag + timedelta(days=1)
    while t.weekday() >= 5:
        t += timedelta(days=1)
    return t


def datum_lang(iso):
    """'2026-09-11' wird 'Freitag, 11.09.2026'."""
    try:
        d = date.fromisoformat(str(iso)[:10])
    except (TypeError, ValueError):
        return nachschlagen.datum_text(iso)
    return f"{nachschlagen.WOCHENTAGE[d.weekday()]}, {d:%d.%m.%Y}"


def wiener_zeit(iso):
    """Bauzeit als '14.09.2026 um 00:35 Uhr Wiener Zeit'; ohne Zeitzone gilt UTC
    (der Ablauf rechnet in UTC)."""
    try:
        t = datetime.fromisoformat(str(iso))
    except (TypeError, ValueError):
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    w = t.astimezone(_zone("Europe/Vienna"))
    return f"{w:%d.%m.%Y} um {w:%H:%M} Uhr Wiener Zeit"


def adresse(basis, ticker):
    """Verweis auf die vollstaendigen Daten einer Aktie in der App."""
    return (basis or "").rstrip("/") + "/?aktie=" + quote(str(ticker or ""), safe=".-")


def toleranz_prozent():
    return zahl_eingabe(SC["toleranz"] * 100)


# ---------------------------------------------------------------------------
# Teil 1: Strategien und Chart-Signale
# ---------------------------------------------------------------------------

SIGNALE = (("rs_linie", "Chart-Signal: RS-Linie gegen SPY auf 52-Wochen-Hoch"),
           ("red_to_green", "Chart-Signal: Red to Green am letzten Handelstag"))
SIGNAL_MUSTER = ("hoch_52w", "hoch_allzeit")


def _auswahl():
    raus = [("", "Keine Strategie, nur die Einstellungen darunter")]
    for kennung, name, _tol in sd.STRATEGIEN:
        raus.append((kennung, ("Chart-Signal: " + name) if kennung in SIGNAL_MUSTER else name))
    return tuple(raus) + SIGNALE


AUSWAHL = _auswahl()
AUSWAHL_NAMEN = dict(AUSWAHL)


def strategie_name(kennung):
    return sd.STRATEGIE_NAMEN.get(kennung) or dict(SIGNALE).get(kennung, "").replace("Chart-Signal: ", "") or kennung


def ist_muster(kennung):
    return kennung in sd.STRATEGIE_NAMEN


def toleranz_moeglich(kennung):
    return any(k == kennung and tol for k, _n, tol in sd.STRATEGIEN)


def strategie_text(kennung):
    """Was die Strategie verlangt, in einem Satz fuer Anfaenger; die Zahlen
    kommen aus den Einstellungen des Scanners."""
    import pattern_scanner as ps
    c = ps.CFG
    p = lambda x: zahl_eingabe(x * 100)  # noqa: E731
    texte = {
        "": "Ohne Strategie filtern nur die Einstellungen darunter; angehakte Merkmale stehen im Ergebnis.",
        "darvas": (f"Darvas Box: ein neues 52-Wochen-Hoch, danach eine Box aus mindestens {c['darvas_box_days']} "
                   f"plus {c['darvas_box_days']} Tagen; Kauf über der Oberkante, Stop unter der Unterkante. "
                   f"Gemeldet werden nur Boxen, deren Hoch höchstens {ZENTRAL['darvas']['frische_max_tage']} "
                   "Tage alt ist."),
        "trend_template": (f"Minervini Trend Template: alle acht Bedingungen erfüllt. Kurs über dem 50-, 150- und "
                           "200-Tage-Durchschnitt in dieser Reihenfolge, der 200er steigt seit einem Monat, "
                           f"mindestens {p(c['tt_min_above_low'])} Prozent über dem 52-Wochen-Tief, höchstens "
                           f"{p(c['tt_max_below_high'])} Prozent unter dem 52-Wochen-Hoch und RS mindestens "
                           f"{zahl_eingabe(c['tt_rs_min'])}. Liefert keinen Kaufpunkt."),
        "vcp": ("VCP: Trend Template erfüllt, dazu mindestens zwei immer engere Rücksetzer mit austrocknendem "
                "Volumen; Kauf über dem Pivot."),
        "cup_handle": (f"Cup & Handle: eine runde Tasse, {p(c['cup_min_depth'])} bis {p(c['cup_max_depth'])} "
                       "Prozent tief, mit einem Henkel im oberen Drittel; Kauf über dem Henkelhoch."),
        "rectangle": ("Rectangle Top: mindestens zwei Berührungen oben und unten, der Kurs über dem "
                      "21-Tage-Durchschnitt; Kauf einen Cent über der Oberkante."),
        "htf": (f"High & Tight Flag: ein Anstieg um mindestens {p(c['htf_min_rise'])} Prozent in höchstens "
                f"{c['htf_max_pole_days']} Handelstagen, danach eine enge Flagge von höchstens "
                f"{c['htf_max_flag_cal_days']} Kalendertagen; Kauf über der Flagge."),
        "htf_innen": "HTF Innen-Einstieg: der Einstieg innerhalb der Flagge einer High & Tight Flag.",
        "ema_crossback": ("EMA Crossback nach Oliver Kell: der erste Rücksetzer an die 10- und 20-Tage-Linie nach "
                          "ihrer Rückeroberung; Kauf über dem Hoch des Umkehrtags."),
        "power_gap": (f"Power-Gap: Eröffnung mindestens {p(ZENTRAL['gap_and_go']['gap_min'])} Prozent über dem "
                      "Vortagesschluss, das Tief bleibt darüber, Schluss im oberen Fünftel der Tagesspanne und "
                      f"Volumen mindestens das {zahl_eingabe(ZENTRAL['volumen']['gap_and_go_faktor'])}fache des "
                      "50-Tage-Schnitts; Kauf über dem Tageshoch."),
        "hoch_52w": "Neues 52-Wochen-Hoch: Das Tageshoch des letzten Handelstags liegt über allen Hochs der 52 Wochen davor.",
        "hoch_allzeit": "Neues Allzeithoch: Am letzten Handelstag wurde das Hoch der ganzen Kurshistorie erreicht.",
        "rs_linie": "RS-Linie gegen SPY auf 52-Wochen-Hoch: Kurs geteilt durch den S&P-500-ETF SPY steht so hoch wie seit einem Jahr nicht.",
        "red_to_green": "Red to Green: am letzten Handelstag unter dem Vortagesschluss eröffnet und darüber geschlossen.",
    }
    return texte.get(kennung, "")


def handelbar_text():
    hb = SC["handelbar"]
    return (f"Nur handelbare Aktien: Kurs ab {zahl_eingabe(hb['kurs_min'])} Dollar, Tagesumsatz im Schnitt ab "
            f"{zahl_eingabe(hb['dollarvolumen_min'] / 1e6)} Millionen Dollar, mindestens "
            f"{hb['historie_min_tage']} Handelstage Kurshistorie")


def langweile_text():
    lw = SC["langeweile"]
    return (f"Langweilige Darvas-Boxen aussortieren: Jahreshoch mindestens das {zahl_eingabe(lw['jahresspanne_min'])}fache "
            f"des Jahrestiefs, mittlere Tagesspanne ab {zahl_eingabe(lw['adr_min_pct'])} Prozent, Box mindestens "
            f"{zahl_eingabe(lw['box_adr_min'])} Tagesspannen und höchstens {zahl_eingabe(lw['box_hoehe_max_pct'])} Prozent hoch")


def treffer_satz(stand, kennung):
    """Wie viele Treffer die Nachttabelle fuer eine Strategie traegt."""
    t = ((stand or {}).get("strategien") or {}).get(kennung)
    if not t:
        return ""
    s = f"In der Nachttabelle: {t.get('streng', 0)} streng erfüllt"
    if t.get("toleranz_moeglich"):
        s += f", {t.get('nur_toleranz', 0)} nur mit {toleranz_prozent()} Prozent Toleranz"
    s += f"; davon handelbar {t.get('handelbar', 0)}"
    if "handelbar_langweilig" in t:
        s += f", davon mit langweiliger Box {t['handelbar_langweilig']}"
    return s + "."


# ---------------------------------------------------------------------------
# Teil 2: die Felder
# ---------------------------------------------------------------------------

GRUPPEN = (("wachstum", "Wachstum und Bruttomarge"),
           ("groesse", "Kurs, Größe und Volumen"),
           ("tag", "Letzter Handelstag"),
           ("ema", "Exponentielle gleitende Durchschnitte"),
           ("hochtief", "Abstand von Hoch und Tief"),
           ("rs", "Relative Stärke"),
           ("bilanz", "Bilanz"),
           ("analysten", "Analysten und Quartalszahlen"))

HOCH_TIEF = (("1t", "Tag, der letzte Handelstag", "Tageshoch", "Tagestief"),
             ("1w", "Woche, die letzten 5 Handelstage", "Wochenhoch", "Wochentief"),
             ("1m", "Monat, die letzten 21 Handelstage", "Monatshoch", "Monatstief"),
             ("3m", "Quartal, die letzten 63 Handelstage", "Quartalshoch", "Quartalstief"),
             ("6m", "Halbjahr, die letzten 126 Handelstage", "Halbjahreshoch", "Halbjahrestief"),
             ("1j", "Jahr, 52 Wochen", "Jahreshoch", "Jahrestief"),
             ("3j", "Drei Jahre", "Dreijahreshoch", "Dreijahrestief"),
             ("allzeit", "Allzeit, die ganze Kurshistorie", "Allzeithoch", "Allzeittief"))

VOLA = (("20", "Durchschnitt der letzten 20 Handelstage", "volatilitaet_20_pct",
         "mittlere Tagesspanne der letzten 20 Handelstage"),
        ("5", "Durchschnitt der letzten 5 Handelstage", "volatilitaet_5_pct",
         "mittlere Tagesspanne der letzten 5 Handelstage"),
        ("1", "nur der letzte Handelstag", "tagesspanne_pct", "Tagesspanne des letzten Handelstags"))

NUR_ANZEIGEN = ("anzeigen", "nur anzeigen, nicht filtern")
KONSENS = (NUR_ANZEIGEN, ("5", "starker Kauf"), ("4", "mindestens Kaufen"), ("3", "mindestens Halten"),
           ("2", "mindestens Verkaufen"))
BEAT = (NUR_ANZEIGEN, ("4", "in allen vier der letzten vier Quartale"),
        ("3", "in mindestens drei der letzten vier Quartale"), ("2", "in mindestens zwei der letzten vier Quartale"),
        ("1", "in mindestens einem der letzten vier Quartale"))


def _volmax_wahl():
    raus = [NUR_ANZEIGEN, ("0", "heute, am letzten Handelstag"), ("1", "heute oder vor einem Handelstag")]
    raus += [(str(n), f"heute bis vor {n} Handelstagen") for n in range(2, 11)]
    return tuple(raus)


VOLMAX = _volmax_wahl()
LAGE = (("egal", "Lage egal"), ("darueber", "Kurs darüber"), ("darunter", "Kurs darunter"))


class Feld:
    """Ein Merkmal aus Teil 2.

    art "bereich": Grenzen mindestens und hoechstens (leer heisst keine),
        wahl bestimmt bei Hoch, Tief und Tagesvolatilitaet die Spalte;
    art "ja": angehakt heisst, die Bedingung muss erfuellt sein;
    art "stufe": eine Auswahl, deren erste Zeile nur anzeigt."""

    def __init__(self, schluessel, gruppe, titel, art="bereich", spalte=None, einheit="Prozent", erklaerung="",
                 stellen=1, faktor=1.0, vorzeichen=False, signed=False, wahl=(), wahl_titel="",
                 analysten=False, lage=False):
        self.schluessel = schluessel
        self.gruppe = gruppe
        self.titel = titel
        self.art = art
        self.spalte = spalte
        self.einheit = einheit
        self.erklaerung = erklaerung
        self.stellen = stellen
        self.faktor = faktor
        self.vorzeichen = vorzeichen
        self.signed = signed
        self.wahl = tuple(wahl)
        self.wahl_titel = wahl_titel
        self.analysten = analysten
        self.lage = lage

    # --- Werte ---------------------------------------------------------------
    def wahl_eintrag(self, fe):
        if not self.wahl:
            return None
        w = (fe or {}).get("wahl")
        return next((x for x in self.wahl if x[0] == w), self.wahl[0])

    def spalte_fuer(self, fe):
        e = self.wahl_eintrag(fe)
        if self.art == "bereich" and e is not None and len(e) > 2:
            return e[2]
        return self.spalte

    def werte(self, df, fe=None):
        """Die Werte in der Einheit der Eingabe, als Gleitkommazahlen."""
        name = self.spalte_fuer(fe)
        v = _zahlen(df, name) * self.faktor if name else pd.Series(np.nan, index=df.index, dtype="float64")
        if self.schluessel == "rs" and (fe or {}).get("vorlaeufig"):
            v = v.fillna(_zahlen(df, "rs_vorlaeufig"))
        return -v if self.vorzeichen else v

    def wert(self, r, fe=None):
        """Der Wert einer Zeile (dict) in der Einheit der Eingabe, oder None."""
        name = self.spalte_fuer(fe)
        v = _num(r.get(name)) if name else None
        if v is None and self.schluessel == "rs" and (fe or {}).get("vorlaeufig"):
            v = _num(r.get("rs_vorlaeufig"))
        if v is None:
            return None
        v *= self.faktor
        return -v if self.vorzeichen else v

    # --- Filter --------------------------------------------------------------
    def maske(self, df, fe):
        """(Maske oder None, [Fehler]); None heisst: dieses Feld filtert nicht."""
        fe = fe or {}
        fehler = []
        if self.art == "ja":
            return _wahr(_sp(df, self.spalte)), fehler
        if self.art == "stufe":
            w = fe.get("wahl") or NUR_ANZEIGEN[0]
            if w == NUR_ANZEIGEN[0]:
                return None, fehler
            n = int(w)
            if self.schluessel == "konsens":
                return _zahlen(df, "konsens_wert") >= n, fehler
            if self.schluessel == "beat":
                return _zahlen(df, "schaetzung_geschlagen") >= n, fehler
            if self.schluessel == "volmax":
                return _zahlen(df, "volumen_max_tage_her") <= n, fehler
            return None, fehler
        v = self.werte(df, fe)
        m = pd.Series(True, index=df.index)
        gesetzt = False
        lage = fe.get("lage") or "egal"
        if self.lage and lage in ("darueber", "darunter"):
            m &= (v > 0) if lage == "darueber" else (v < 0)
            gesetzt = True
        for teil, wort in (("min", "mindestens"), ("max", "höchstens")):
            x, f = zahl_lesen(fe.get(teil))
            if f:
                fehler.append(f"{self.titel}, {wort}: {f}; diese Grenze wirkt deshalb nicht.")
            elif x is not None:
                m &= (v >= x - EPS) if teil == "min" else (v <= x + EPS)
                gesetzt = True
        return (m.fillna(False) if gesetzt else None), fehler

    # --- Texte ---------------------------------------------------------------
    def eingabe_titel(self, teil, fe=None):
        """Beschriftung eines Grenzfelds; bei Hoch und Tief mit dem gewaehlten Zeitraum."""
        wort = "mindestens" if teil == "min" else "höchstens"
        if self.schluessel in ("hoch", "tief"):
            e = self.wahl_eintrag(fe)
            name = e[3] if self.schluessel == "hoch" else e[4]
            return f"Abstand zum {name} {wort}, in Prozent {'darunter' if self.schluessel == 'hoch' else 'darüber'}"
        if self.schluessel == "vola":
            return f"Tagesvolatilität {wort}, in Prozent"
        einheit = self.einheit_fuer(fe)
        return f"{self.titel} {wort}" + (f", in {einheit}" if einheit else "")

    def einheit_fuer(self, fe):
        if self.schluessel == "hoch":
            return "Prozent unter dem Hoch"
        if self.schluessel == "tief":
            return "Prozent über dem Tief"
        return self.einheit

    def _wert_text(self, v):
        if v is None:
            return "nicht berechenbar" if (self.signed or self.gruppe == "wachstum") else "unbekannt"
        text = mit_vorzeichen(v, self.stellen) if self.signed else zahl(v, self.stellen)
        return text + (f" {self.einheit}" if self.einheit else "")

    def satz(self, r, fe=None, analysten_da=True):
        """Das Merkmal einer Aktie (Zeile als dict) als Satzteil fuer die Liste."""
        fe = fe or {}
        if self.analysten and not analysten_da:
            return f"{self.titel}: Analystendaten nicht geladen"
        s = self.schluessel
        if self.art == "ja":
            ja = _ja(r.get(self.spalte))
            for kennung, gegen, spalte in (("rs_linie", "SPY", "rs_linie_abst_pct"),
                                           ("rs_linie_qqq", "QQQ", "rs_linie_qqq_abst_pct")):
                if s == kennung and not ja:
                    a = _num(r.get(spalte))
                    return (f"RS-Linie gegen {gegen} " + (f"{zahl(abs(a), 1)} Prozent unter dem 52-Wochen-Hoch"
                                                         if a is not None else "ohne bekannten Abstand zum Hoch"))
            return self.titel if ja else f"{self.titel}: nein"
        if s == "konsens":
            k = r.get("konsens")
            k = k if isinstance(k, str) and k else None
            n = [_num(r.get(x)) for x in ("analysten_kaufen", "analysten_halten", "analysten_verkaufen")]
            if not k and not any(n):
                return "keine Analystenempfehlungen bekannt"
            teile = [f"Analystenkonsens {k}" if k else "Analystenkonsens unbekannt"]
            if any(x is not None for x in n):
                teile.append(f"{int(n[0] or 0)} Kaufen, {int(n[1] or 0)} Halten, {int(n[2] or 0)} Verkaufen")
            return ", ".join(teile)
        if s == "beat":
            q, g = _num(r.get("quartale_mit_schaetzung")), _num(r.get("schaetzung_geschlagen"))
            if not q:
                return "keine Gewinnschätzungen der letzten Quartale bekannt"
            return f"Schätzung in {int(g or 0)} von {int(q)} Quartalen geschlagen"
        if s == "volmax":
            tage = _num(r.get("volumen_max_tage_her"))
            menge = zahl(r.get("volumen_max"), 0)
            datum = r.get("volumen_max_datum")
            am = nachschlagen.datum_text(datum) if isinstance(datum, str) and datum else "unbekannt"
            if tage is None:
                return f"größtes Volumen jemals {menge} Stück am {am}, vor mehr als drei Jahren"
            n = int(tage)
            wann = "heute" if n == 0 else ("vor einem Handelstag" if n == 1 else f"vor {n} Handelstagen")
            return f"größtes Volumen jemals {wann}, {menge} Stück am {am}"
        v = self.wert(r, fe)
        if s in ("hoch", "tief"):
            e = self.wahl_eintrag(fe)
            name = e[3] if s == "hoch" else e[4]
            if v is None:
                return f"Abstand zum {name} unbekannt"
            return f"{zahl(v, 1)} Prozent {'unter dem' if s == 'hoch' else 'über dem'} {name}"
        if s == "vola":
            e = self.wahl_eintrag(fe)
            return f"{e[3]} {zahl(v, 2)} Prozent" if v is not None else f"{e[3]} unbekannt"
        if self.lage:
            linie = self.titel.replace("Abstand zur ", "")
            if v is None:
                return f"{linie} unbekannt"
            if round(v, 2) == 0:
                return f"Kurs auf der {linie}"
            return f"Kurs {zahl(abs(v), 2)} Prozent {'über' if v > 0 else 'unter'} der {linie}"
        if s == "rs":
            if v is not None:
                vorl = _num(r.get("rs")) is None
                return f"RS {int(round(v))}" + (" vorläufig" if vorl else "")
            vl = _num(r.get("rs_vorlaeufig"))
            return f"kein RS, vorläufiges RS {int(round(vl))}" if vl is not None else "RS unbekannt"
        if s == "rs_linie_abst":
            return (f"RS-Linie gegen SPY {zahl(v, 1)} Prozent unter dem 52-Wochen-Hoch" if v is not None
                    else "Abstand der RS-Linie gegen SPY unbekannt")
        if s == "kursziel":
            ziel = _num(r.get("kursziel"))
            if v is None or ziel is None:
                return "kein Kursziel bekannt"
            return f"Kursziel {zahl(ziel, 2)} Dollar, {zahl(abs(v), 1)} Prozent {'über' if v >= 0 else 'unter'} dem Kurs"
        return f"{self.titel} {self._wert_text(v)}"

    def einstellung_text(self, fe):
        """Was dieses Feld gerade tut, fuer die Zeile mit den aktiven Einstellungen."""
        fe = fe or {}
        if self.art == "ja":
            return self.titel
        if self.art == "stufe":
            e = self.wahl_eintrag(fe)
            if e[0] == NUR_ANZEIGEN[0]:
                return f"{self.titel} angezeigt"
            return f"{self.titel} {e[1]}"
        teile = []
        titel = self.titel
        if self.schluessel in ("hoch", "tief", "vola"):
            e = self.wahl_eintrag(fe)
            titel = (f"Abstand zum {e[3]}" if self.schluessel == "hoch" else
                     f"Abstand zum {e[4]}" if self.schluessel == "tief" else f"Tagesvolatilität, {e[1]}")
        if self.lage and (fe.get("lage") or "egal") != "egal":
            teile.append("Kurs darüber" if fe.get("lage") == "darueber" else "Kurs darunter")
        einheit = self.einheit_fuer(fe)
        for teil, wort in (("min", "mindestens"), ("max", "höchstens")):
            x, f = zahl_lesen(fe.get(teil))
            if x is not None and not f:
                teile.append(f"{wort} {zahl_eingabe(x)}" + (f" {einheit}" if einheit else ""))
        if self.schluessel == "rs" and fe.get("vorlaeufig"):
            teile.append("mit vorläufigem RS")
        return titel + (" " + ", ".join(teile) if teile else " angezeigt")

    def datei_spalten(self, df, fe=None, analysten_da=True):
        """[(Spaltenkopf, Werte)] fuer die Dateien."""
        fe = fe or {}
        s = self.schluessel
        if self.analysten and not analysten_da:
            return [(self.titel, pd.Series("Analystendaten nicht geladen", index=df.index))]
        if self.art == "ja":
            raus = [(self.titel, _wahr(_sp(df, self.spalte)).map({True: "ja", False: "nein"}))]
            if s == "rs_linie":
                raus.append(("RS-Linie gegen SPY, Prozent unter dem 52-Wochen-Hoch", -_zahlen(df, "rs_linie_abst_pct")))
            if s == "rs_linie_qqq":
                raus.append(("RS-Linie gegen QQQ, Prozent unter dem 52-Wochen-Hoch", -_zahlen(df, "rs_linie_qqq_abst_pct")))
            return raus
        if s == "konsens":
            return [("Analystenkonsens", _sp(df, "konsens")), ("Kaufempfehlungen", _zahlen(df, "analysten_kaufen")),
                    ("Halten", _zahlen(df, "analysten_halten")), ("Verkaufsempfehlungen", _zahlen(df, "analysten_verkaufen"))]
        if s == "beat":
            return [("Quartale über der Schätzung", _zahlen(df, "schaetzung_geschlagen")),
                    ("Quartale mit Schätzung", _zahlen(df, "quartale_mit_schaetzung"))]
        if s == "volmax":
            return [("Größtes Volumen jemals, Stück", _zahlen(df, "volumen_max")),
                    ("Größtes Volumen jemals, Datum", _sp(df, "volumen_max_datum")),
                    ("Größtes Volumen jemals, vor Handelstagen", _zahlen(df, "volumen_max_tage_her"))]
        werte = self.werte(df, fe).round(self.stellen)
        if s in ("hoch", "tief"):
            e = self.wahl_eintrag(fe)
            return [(f"Prozent {'unter dem' if s == 'hoch' else 'über dem'} {e[3] if s == 'hoch' else e[4]}", werte)]
        if s == "vola":
            e = self.wahl_eintrag(fe)
            return [(f"Tagesvolatilität in Prozent, {e[1]}", werte)]
        if s == "rs":
            raus = [("RS", werte)]
            if fe.get("vorlaeufig"):
                vorl = _zahlen(df, "rs").isna() & _zahlen(df, "rs_vorlaeufig").notna()
                raus.append(("RS vorläufig", vorl.map({True: "ja", False: "nein"})))
            return raus
        if s == "kursziel":
            return [("Kursziel in Dollar", _zahlen(df, "kursziel").round(2)), ("Kursziel über dem Kurs in Prozent", werte)]
        kopf = f"{self.titel} in {self.einheit}" if self.einheit else self.titel
        return [(kopf, werte)]


def _felder():
    F = Feld
    return (
        # Wachstum und Bruttomarge, aus den SEC-Zahlen
        F("umsatz_q", "wachstum", "Umsatzwachstum q/q", spalte="umsatz_q_vj_pct", signed=True,
          erklaerung="Jüngstes Quartal gegen dasselbe Quartal des Vorjahres, aus den SEC-Zahlen."),
        F("umsatz_j", "wachstum", "Umsatzwachstum y/y", spalte="umsatz_ttm_pct", signed=True,
          erklaerung="Die letzten vier Quartale gegen die vier Quartale ein Jahr davor."),
        F("umsatz_s", "wachstum", "Umsatzwachstum sequenziell", spalte="umsatz_seq_pct", signed=True,
          erklaerung="Jüngstes Quartal gegen das Quartal davor."),
        F("eps_q", "wachstum", "EPS-Wachstum q/q", spalte="eps_q_vj_pct", signed=True,
          erklaerung="Verwässerter Gewinn je Aktie, jüngstes Quartal gegen das Vorjahresquartal. Lag der "
                     "Vorjahreswert bei null oder im Minus, ist kein Prozentwert berechenbar."),
        F("eps_j", "wachstum", "EPS-Wachstum y/y", spalte="eps_ttm_pct", signed=True,
          erklaerung="Gewinn je Aktie der letzten vier Quartale gegen die vier Quartale ein Jahr davor."),
        F("eps_s", "wachstum", "EPS-Wachstum sequenziell", spalte="eps_seq_pct", signed=True,
          erklaerung="Gewinn je Aktie des jüngsten Quartals gegen das Quartal davor."),
        F("marge", "wachstum", "Bruttomarge", spalte="bruttomarge_pct", stellen=1,
          erklaerung="Bruttogewinn in Prozent des Umsatzes im jüngsten Quartal. Banken, Versicherer und "
                     "Immobilienfirmen weisen keine aus."),
        F("marge_q", "wachstum", "Bruttomarge q/q", spalte="bruttomarge_q_vj_pp", einheit="Prozentpunkte", signed=True,
          erklaerung="Veränderung der Bruttomarge des jüngsten Quartals gegen das Vorjahresquartal."),
        F("marge_j", "wachstum", "Bruttomarge y/y", spalte="bruttomarge_ttm_pp", einheit="Prozentpunkte", signed=True,
          erklaerung="Bruttomarge der letzten vier Quartale gegen die der vier Quartale ein Jahr davor."),
        F("marge_s", "wachstum", "Bruttomarge sequenziell", spalte="bruttomarge_seq_pp", einheit="Prozentpunkte",
          signed=True, erklaerung="Bruttomarge des jüngsten Quartals gegen die des Quartals davor."),
        # Kurs, Groesse und Volumen
        F("kurs", "groesse", "Kurs", spalte="kurs", einheit="Dollar", stellen=2,
          erklaerung="Schlusskurs des letzten Handelstags."),
        F("marktkap", "groesse", "Marktkapitalisierung", spalte="marktkap_mrd", einheit="Milliarden Dollar", stellen=2,
          erklaerung="In Milliarden Dollar: 0,3 heißt 300 Millionen, 1000 heißt eine Billion. Quelle Nasdaq."),
        F("volumen", "groesse", "Durchschnittliches Tagesvolumen, 50 Tage", spalte="volumen_50", einheit="Stück",
          stellen=0, erklaerung="Gehandelte Aktien je Tag im Schnitt der letzten 50 Handelstage."),
        F("umsatz_dollar", "groesse", "Durchschnittlicher Tagesumsatz, 50 Tage", spalte="dollarvolumen_50",
          einheit="Millionen Dollar", faktor=1e-6, stellen=1,
          erklaerung="Kurs mal Volumen im Schnitt der letzten 50 Handelstage."),
        F("aktien", "groesse", "Ausstehende Aktien", spalte="aktien_ausstehend", einheit="Millionen Stück",
          faktor=1e-6, stellen=1, erklaerung="Zahl der ausstehenden Aktien aus dem jüngsten SEC-Bericht."),
        F("volmax", "groesse", "Größtes Volumen der ganzen Kurshistorie", art="stufe", wahl=VOLMAX,
          wahl_titel="Größtes Volumen jemals gehandelt",
          erklaerung="Der Tag mit dem höchsten Volumen seit Beginn der Kurshistorie bei Yahoo."),
        # Letzter Handelstag
        F("veraenderung", "tag", "Veränderung zum Vortag", spalte="veraenderung_pct", signed=True, stellen=2,
          erklaerung="Schlusskurs des letzten Handelstags gegen den Schlusskurs davor."),
        F("seit_open", "tag", "Veränderung seit der Eröffnung, Change from Open", spalte="seit_eroeffnung_pct",
          signed=True, stellen=2,
          erklaerung="Schlusskurs gegen den Eröffnungskurs des letzten Handelstags. Die Tabelle entsteht nachts, "
                     "während des Handels steht hier noch der Vortag."),
        F("rtg", "tag", "Red to Green", art="ja", spalte="red_to_green",
          erklaerung="Am letzten Handelstag unter dem Vortagesschluss eröffnet und darüber geschlossen."),
        F("vola", "tag", "Tagesvolatilität", wahl=VOLA, wahl_titel="Zeitraum der Tagesvolatilität", stellen=2,
          erklaerung="Spanne zwischen Tageshoch und Tagestief in Prozent des Tagestiefs."),
        # Exponentielle Durchschnitte
        F("ema21", "ema", "Abstand zur EMA 21", spalte="abst_ema21_pct", signed=True, stellen=2, lage=True,
          erklaerung="Schlusskurs gegen den exponentiellen Durchschnitt der letzten 21 Tage; negativ heißt darunter."),
        F("ema50", "ema", "Abstand zur EMA 50", spalte="abst_ema50_pct", signed=True, stellen=2, lage=True,
          erklaerung="Schlusskurs gegen den exponentiellen Durchschnitt der letzten 50 Tage; negativ heißt darunter."),
        F("ema200", "ema", "Abstand zur EMA 200", spalte="abst_ema200_pct", signed=True, stellen=2, lage=True,
          erklaerung="Schlusskurs gegen den exponentiellen Durchschnitt der letzten 200 Tage; negativ heißt darunter."),
        # Abstand von Hoch und Tief
        F("hoch", "hochtief", "Abstand vom Hoch", vorzeichen=True, stellen=1, wahl_titel="Zeitraum des Hochs",
          wahl=tuple((h, text, f"abst_hoch_{h}_pct", hoch, tief) for h, text, hoch, tief in HOCH_TIEF),
          erklaerung="Wie weit der Schlusskurs unter dem Hoch des gewählten Zeitraums liegt; 0 heißt am Hoch."),
        F("tief", "hochtief", "Abstand vom Tief", stellen=1, wahl_titel="Zeitraum des Tiefs",
          wahl=tuple((h, text, f"abst_tief_{h}_pct", hoch, tief) for h, text, hoch, tief in HOCH_TIEF),
          erklaerung="Wie weit der Schlusskurs über dem Tief des gewählten Zeitraums liegt."),
        F("neu_52w", "hochtief", "Neues 52-Wochen-Hoch", art="ja", spalte="hoch_52w",
          erklaerung="Das Tageshoch des letzten Handelstags liegt über allen Hochs der 52 Wochen davor."),
        F("neu_ath", "hochtief", "Neues Allzeithoch", art="ja", spalte="hoch_allzeit",
          erklaerung="Am letzten Handelstag wurde das Hoch der ganzen Kurshistorie erreicht."),
        # Relative Staerke
        F("rs", "rs", "RS gegen den ganzen US-Markt", spalte="rs", einheit="", stellen=0,
          erklaerung="Relative Stärke von 1 bis 99 gegen alle Stammaktien des US-Markts; 90 heißt stärker als "
                     "90 Prozent. Junge Titel haben nur ein vorläufiges RS."),
        F("rs_linie", "rs", "RS-Linie gegen SPY auf 52-Wochen-Hoch", art="ja", spalte="rs_linie_hoch",
          erklaerung="Kurs geteilt durch den S&P-500-ETF SPY steht auf einem 52-Wochen-Hoch."),
        F("rs_linie_qqq", "rs", "RS-Linie gegen QQQ auf 52-Wochen-Hoch", art="ja", spalte="rs_linie_qqq_hoch",
          erklaerung="Kurs geteilt durch den Nasdaq-100-ETF QQQ steht auf einem 52-Wochen-Hoch."),
        F("rs_linie_abst", "rs", "Abstand der RS-Linie gegen SPY vom 52-Wochen-Hoch", spalte="rs_linie_abst_pct",
          vorzeichen=True, einheit="Prozent unter dem Hoch", stellen=1,
          erklaerung="Wie weit die RS-Linie gegen SPY unter ihrem 52-Wochen-Hoch steht; 0 heißt auf dem Hoch."),
        # Bilanz
        F("schulden_ek", "bilanz", "Schulden zu Eigenkapital, Debt to Equity", spalte="schulden_zu_ek", einheit="",
          stellen=2, erklaerung="Kurz- und langfristige Finanzschulden geteilt durch das Eigenkapital; 0,5 heißt halb "
                                "so viele Schulden wie Eigenkapital. Aus der jüngsten SEC-Bilanz."),
        F("schulden_vermoegen", "bilanz", "Verschuldung im Verhältnis zum Vermögen", spalte="schulden_zu_vermoegen_pct",
          erklaerung="Finanzschulden in Prozent der Bilanzsumme."),
        F("ek_quote", "bilanz", "Eigenkapitalquote", spalte="ek_quote_pct",
          erklaerung="Eigenkapital in Prozent der Bilanzsumme."),
        F("fk_quote", "bilanz", "Fremdkapitalquote", spalte="fk_quote_pct",
          erklaerung="Alle Verbindlichkeiten in Prozent der Bilanzsumme."),
        # Analysten und Quartalszahlen
        F("konsens", "analysten", "Analystenkonsens", art="stufe", wahl=KONSENS, wahl_titel="Analystenkonsens",
          analysten=True,
          erklaerung="Die jüngste Empfehlung der Analysten laut Nasdaq, samt der Zahl der Kauf-, Halten- und "
                     "Verkaufsempfehlungen."),
        F("kaufanteil", "analysten", "Anteil der Kaufempfehlungen", spalte="analysten_kauf_anteil_pct", analysten=True,
          erklaerung="Kaufempfehlungen in Prozent aller Empfehlungen."),
        F("kursziel", "analysten", "Kursziel über dem Kurs", spalte="kursziel_abst_pct", signed=True, analysten=True,
          erklaerung="Mittleres Kursziel der Analysten gegen den Schlusskurs; negativ heißt, das Ziel liegt darunter."),
        F("beat", "analysten", "Schätzungen geschlagen", art="stufe", wahl=BEAT,
          wahl_titel="Wie oft der Gewinn je Aktie über der Schätzung lag", analysten=True,
          erklaerung="Wie oft der gemeldete Gewinn je Aktie in den letzten vier Quartalen über der Schätzung der "
                     "Analysten lag, laut Nasdaq."),
        F("ueberraschung", "analysten", "Letzte Gewinnüberraschung", spalte="letzte_ueberraschung_pct", signed=True,
          analysten=True,
          erklaerung="Abweichung des zuletzt gemeldeten Gewinns je Aktie von der Schätzung der Analysten."),
    )


FELDER = _felder()
FELD = {f.schluessel: f for f in FELDER}

# ---------------------------------------------------------------------------
# Zahlentermine und Sektoren
# ---------------------------------------------------------------------------

TERMIN_TEILE = (("heute_vor", "heute vorbörslich", 0, "vorboerslich"),
                ("heute_nach", "heute nachbörslich", 0, "nachboerslich"),
                ("morgen_vor", "morgen vorbörslich", 1, "vorboerslich"),
                ("morgen_nach", "morgen nachbörslich", 1, "nachboerslich"))
LAGE_TEXT = {"vorboerslich": "vorbörslich", "nachboerslich": "nachbörslich", "im_handel": "während des Handels",
             "unbekannt": "Tageszeit unbekannt"}
UMFANG = (("markt", "ganzer Markt"), ("listen", "nur die Aktien der Wochenlisten"))

SEKTOREN = {"Basic Materials": "Grundstoffe", "Consumer Discretionary": "Zyklischer Konsum",
            "Consumer Staples": "Basiskonsum", "Energy": "Energie", "Finance": "Finanzen",
            "Health Care": "Gesundheit", "Industrials": "Industrie", "Miscellaneous": "Sonstiges",
            "Real Estate": "Immobilien", "Technology": "Technologie", "Telecommunications": "Telekommunikation",
            "Utilities": "Versorger"}


def sektor_name(kennung):
    if not kennung:
        return "ohne Sektorangabe"
    return SEKTOREN.get(kennung, kennung)


def sektoren_in(tabelle):
    """Die Sektoren der Tabelle, deutsch sortiert; "" steht fuer ohne Angabe."""
    vorhanden = set(SEKTOREN)
    if tabelle is not None and "sektor" in tabelle.columns:
        vorhanden |= {str(s) for s in tabelle["sektor"].dropna().unique() if str(s).strip()}
        if tabelle["sektor"].isna().any() or (tabelle["sektor"].astype(str).str.strip() == "").any():
            vorhanden.add("")
    return sorted(vorhanden, key=lambda s: (s == "", sektor_name(s).lower()))


def termin_ziele(te, heute):
    """[(Datum, Lage)] der angehakten Zeitpunkte."""
    morgen = naechster_handelstag(heute)
    return [((heute if plus == 0 else morgen).isoformat(), lage)
            for key, _t, plus, lage in TERMIN_TEILE if (te or {}).get(key)]


def termin_maske(df, te, heute):
    ziele = termin_ziele(te, heute)
    dat = df["termin_datum"].astype("string") if "termin_datum" in df.columns else pd.Series(pd.NA, index=df.index, dtype="string")
    lg = df["termin_lage"].astype("string") if "termin_lage" in df.columns else pd.Series(pd.NA, index=df.index, dtype="string")
    if ziele:
        m = pd.Series(False, index=df.index)
        for d, lage in ziele:
            m |= ((dat == d) & (lg == lage)).fillna(False).astype(bool)
        if (te or {}).get("ohne_zeit"):
            for d in {d for d, _l in ziele}:
                m |= ((dat == d) & lg.isin(["im_handel", "unbekannt"])).fillna(False).astype(bool)
    else:
        m = pd.Series(True, index=df.index)
    if (te or {}).get("umfang") == "listen":
        m &= _wahr(df["in_wochenliste"]) if "in_wochenliste" in df.columns else False
    return m


# ---------------------------------------------------------------------------
# Voreinstellungen
# ---------------------------------------------------------------------------

def voreinstellung(kennung, toleranz=False):
    """{Feldschluessel: Einstellung} fuer eine Strategie. Grenzen nur dort,
    wo der Detektor dieselbe Schwelle prueft, bei Toleranz gelockert."""
    import pattern_scanner as ps
    t = float(SC["toleranz"]) if (toleranz and toleranz_moeglich(kennung)) else 0.0
    f = {}

    def an(schluessel, **werte):
        f[schluessel] = {"an": True, **werte}

    if kennung in ("trend_template", "vcp"):
        an("rs", min=zahl_eingabe(ps.CFG["tt_rs_min"] * (1.0 - t)))
        an("tief", wahl="1j", min=zahl_eingabe(ps.CFG["tt_min_above_low"] * 100.0 * (1.0 - t)))
        an("hoch", wahl="1j", max=zahl_eingabe(ps.CFG["tt_max_below_high"] * 100.0 * (1.0 + t)))
        an("ema50")
        an("ema200")
    elif kennung == "darvas":
        an("rs")
        an("hoch", wahl="1j")
        an("vola", wahl="20")
    elif kennung == "cup_handle":
        an("rs")
        an("hoch", wahl="1j")
        an("volumen")
    elif kennung == "rectangle":
        an("rs")
        an("hoch", wahl="3m")
        an("ema21")
    elif kennung in ("htf", "htf_innen"):
        an("rs")
        an("tief", wahl="3m")
        an("hoch", wahl="1m")
    elif kennung == "ema_crossback":
        an("rs")
        an("ema21")
        an("ema50")
    elif kennung == "power_gap":
        an("veraenderung")
        an("seit_open")
        an("umsatz_dollar")
    elif kennung == "hoch_52w":
        an("rs")
        an("hoch", wahl="1j")
        an("tief", wahl="1j")
    elif kennung == "hoch_allzeit":
        an("rs")
        an("hoch", wahl="allzeit")
    elif kennung == "rs_linie":
        an("rs")
        an("rs_linie")
    elif kennung == "red_to_green":
        an("rtg")
        an("seit_open")
        an("veraenderung")
    return f


def standard_einstellung():
    return {"strategie": "", "toleranz": False, "nur_handelbar": True, "langweilig_raus": True, "felder": {},
            "termine": {"an": False, "umfang": "markt"}, "sektoren": None, "sortierung": ""}


# ---------------------------------------------------------------------------
# Auswerten
# ---------------------------------------------------------------------------

def aktive_felder(e):
    felder = (e or {}).get("felder") or {}
    return [(feld, felder[feld.schluessel]) for feld in FELDER if (felder.get(feld.schluessel) or {}).get("an")]


def auswerten(tabelle, e, heute=None, analysten_da=True):
    """Die Treffer fuer die Einstellung e. Rueckgabe dict: df, felder,
    fehler, hinweise, strategie, termine, sektor_aktiv, analysten_da,
    gesamt (Zeilen mit Kursen vom letzten Handelstag)."""
    e = {**standard_einstellung(), **(e or {})}
    heute = heute or ny_jetzt().date()
    fehler, hinweise = [], []
    df = tabelle if tabelle is not None else pd.DataFrame()
    if "kurse_aktuell" in df.columns:
        df = df[_wahr(df["kurse_aktuell"])]
    gesamt = len(df)
    k = e.get("strategie") or ""
    if ist_muster(k):
        spalte = f"m_{k}"
        stufe_min = 1 if (e.get("toleranz") and toleranz_moeglich(k)) else 2
        if spalte in df.columns:
            df = df[pd.to_numeric(df[spalte], errors="coerce").fillna(0) >= stufe_min]
        else:
            df = df.iloc[0:0]
            hinweise.append(f"Die Nachttabelle kennt {strategie_name(k)} noch nicht.")
        if k == "darvas" and e.get("langweilig_raus") and "darvas_langweilig" in df.columns:
            df = df[~_wahr(df["darvas_langweilig"])]
    elif k == "rs_linie":
        df = df[_wahr(df["rs_linie_hoch"])] if "rs_linie_hoch" in df.columns else df.iloc[0:0]
    elif k == "red_to_green":
        df = df[_wahr(df["red_to_green"])] if "red_to_green" in df.columns else df.iloc[0:0]
    if e.get("nur_handelbar") and "handelbar" in df.columns:
        df = df[_wahr(df["handelbar"])]
    felder = aktive_felder(e)
    ohne_analysten = []
    for feld, fe in felder:
        if feld.analysten and not analysten_da:
            ohne_analysten.append(feld.titel)
            continue
        m, f = feld.maske(df, fe)
        fehler += f
        if m is not None:
            df = df[m.reindex(df.index).fillna(False).astype(bool)]
    if ohne_analysten:
        hinweise.append("Die Analystendaten sind nicht geladen; " + ", ".join(ohne_analysten)
                        + " filtern deshalb nicht.")
    te = e.get("termine") or {}
    termine = te if te.get("an") else None
    if termine:
        df = df[termin_maske(df, termine, heute)]
        if not termin_ziele(termine, heute):
            hinweise.append("Bei den Zahlenterminen ist kein Zeitpunkt angehakt; angezeigt wird nur der nächste Termin.")
    auswahl_s = e.get("sektoren")
    sektor_aktiv = False
    if auswahl_s is not None and tabelle is not None and "sektor" in df.columns:
        alle = set(sektoren_in(tabelle))
        gewaehlt = set(auswahl_s)
        if gewaehlt != alle:
            sektor_aktiv = True
            df = df[df["sektor"].fillna("").astype(str).str.strip().isin(gewaehlt)]
            if not gewaehlt:
                hinweise.append("Kein Sektor angehakt; es bleibt keine Aktie übrig.")
    ausw = {"df": df, "felder": felder, "fehler": fehler, "hinweise": hinweise, "strategie": k,
            "toleranz": bool(e.get("toleranz") and toleranz_moeglich(k)), "termine": termine,
            "sektor_aktiv": sektor_aktiv, "analysten_da": analysten_da, "gesamt": gesamt, "heute": heute,
            "einstellung": e}
    ausw["df"] = sortieren(ausw, e.get("sortierung") or "")
    return ausw


def sortier_wahl(e):
    """[(Kennung, Text)] der Sortierungen, die zur Einstellung passen."""
    e = e or {}
    k = e.get("strategie") or ""
    raus = []
    if ist_muster(k):
        raus.append(("rating", "Rating der Strategie, bestes zuerst"))
    raus += [("rs", "RS, höchstes zuerst"), ("marktkap", "Marktkapitalisierung, größte zuerst"),
             ("ticker", "Kürzel von A bis Z")]
    for feld, _fe in aktive_felder(e):
        if feld.art == "bereich":
            raus.append((f"{feld.schluessel}:ab", f"{feld.titel}, größter Wert zuerst"))
            raus.append((f"{feld.schluessel}:auf", f"{feld.titel}, kleinster Wert zuerst"))
    return raus


def sortieren(ausw, kennung):
    df = ausw["df"]
    if df is None or df.empty:
        return df
    e = ausw.get("einstellung") or {}
    k = ausw.get("strategie") or ""
    gueltig = {x for x, _t in sortier_wahl(e)}
    if kennung not in gueltig:
        kennung = "rating" if ist_muster(k) else "rs"
    absteigend = True
    if kennung == "rating":
        schluessel = _zahlen(df, f"rating_{k}")
    elif kennung == "rs":
        schluessel = _zahlen(df, "rs")
        if "rs_vorlaeufig" in df.columns:
            schluessel = schluessel.fillna(_zahlen(df, "rs_vorlaeufig"))
    elif kennung == "marktkap":
        schluessel = _zahlen(df, "marktkap_mrd")
    elif kennung == "ticker":
        return df.sort_values("ticker", kind="stable")
    else:
        name, richtung = kennung.split(":", 1)
        feld = FELD.get(name)
        fe = ((e.get("felder") or {}).get(name)) or {}
        schluessel = feld.werte(df, fe) if feld else pd.Series(np.nan, index=df.index)
        absteigend = richtung == "ab"
    return (df.assign(_sortier=schluessel).sort_values(["_sortier", "ticker"], ascending=[not absteigend, True],
                                                        na_position="last", kind="stable").drop(columns="_sortier"))


# ---------------------------------------------------------------------------
# Ergebnisliste und Dateien
# ---------------------------------------------------------------------------

_FIRMEN_SCHNITTE = tuple(re.compile(m) for m in (
    r"\s+-\s+.*$", r"\s+American Depositary.*$", r"\s+(Ordinary|Common) (Shares|Stock).*$",
    r"\s+Class [A-C]\b.*$", r"\s+Depositary Shares.*$", r"\s+\(.*$"))


def _firma(name):
    """Der Firmenname ohne Wertpapierzusatz: 'Ternium S.A. Ternium S.A.
    American Depositary Shares (each ...)' wird 'Ternium S.A.'."""
    if not isinstance(name, str) or not name.strip():
        return "Name unbekannt"
    n = nachschlagen.firmenname(name)
    for muster in _FIRMEN_SCHNITTE:
        n = muster.sub("", n)
    n = n.strip().rstrip(",").strip()
    worte = n.split()
    halb = len(worte) // 2
    if halb and len(worte) % 2 == 0 and worte[:halb] == worte[halb:]:
        n = " ".join(worte[:halb])
    return n or name.strip()


def strategie_teile(ausw, r):
    k = ausw.get("strategie") or ""
    teile = []
    if ist_muster(k):
        stufe = int(_num(r.get(f"m_{k}")) or 0)
        teile.append(strategie_name(k) + (" streng erfüllt" if stufe == 2 else
                                          f" nur mit {toleranz_prozent()} Prozent Toleranz erfüllt"))
        rating = _num(r.get(f"rating_{k}"))
        if rating is not None:
            grund = str(r.get(f"grund_{k}") or "").replace("; ", ", ")
            teile.append(f"Rating {int(round(rating))} von 100" + (f", {grund}" if grund else ""))
        kp, stop = _num(r.get(f"kp_{k}")), _num(r.get(f"stop_{k}"))
        if kp:
            teile.append(f"Kaufpunkt {zahl(kp, 2)} Dollar")
        if stop:
            teile.append(f"Stop {zahl(stop, 2)} Dollar")
        status = nachschlagen.anzeige_text(r.get(f"status_{k}") or "") if isinstance(r.get(f"status_{k}"), str) else ""
        if status:
            teile.append(status.replace("; ", ", ").rstrip("."))
        if k == "trend_template" and _num(r.get("tt_count")) is not None:
            teile.append(f"{int(_num(r.get('tt_count')))} von 8 Bedingungen")
        if k == "darvas":
            h = _num(r.get("darvas_box_hoehe_pct"))
            if h is not None:
                teile.append(f"Box {zahl(h, 1)} Prozent hoch")
            if r.get("darvas_langweilig") is True or isinstance(r.get("darvas_langweilig"), np.bool_) and bool(r.get("darvas_langweilig")):
                gruende = str(r.get("darvas_langweilig_gruende") or "").replace("; ", ", ")
                teile.append("langweilige Box" + (f": {gruende}" if gruende else ""))
    return teile


def termin_teil(r):
    d = r.get("termin_datum")
    if not isinstance(d, str) or not d:
        return "kein Zahlentermin in den nächsten zehn Tagen bekannt"
    lage = LAGE_TEXT.get(r.get("termin_lage") or "unbekannt", "Tageszeit unbekannt")
    quelle = r.get("termin_quelle")
    return f"Zahlen am {datum_lang(d)}, {lage}" + (f", laut {quelle}" if isinstance(quelle, str) and quelle else "")


def satz_teile(ausw, r):
    teile = strategie_teile(ausw, r)
    for feld, fe in ausw.get("felder") or []:
        teile.append(feld.satz(r, fe, ausw.get("analysten_da", True)))
    if ausw.get("termine"):
        teile.append(termin_teil(r))
    if ausw.get("sektor_aktiv"):
        teile.append(f"Sektor {sektor_name(r.get('sektor') if isinstance(r.get('sektor'), str) else '')}")
    return teile


def zeilen(ausw, basis_url, anzahl=None, markdown=True):
    """Die Ergebnisliste: eine nummerierte Zeile je Aktie. In Markdown ist das
    Kuerzel ein Verweis auf die vollstaendigen Daten; als Text steht die
    Adresse am Ende."""
    df = ausw["df"]
    if anzahl:
        df = df.head(int(anzahl))
    raus = []
    for i, r in enumerate(df.to_dict("records"), 1):
        t = str(r.get("ticker") or "")
        url = adresse(basis_url, t)
        teile = satz_teile(ausw, r)
        if markdown:
            kopf = f"[{md(t)}]({url}), {md(_firma(r.get('name')))}"
            text = "; ".join(md(x) for x in teile)
        else:
            kopf = f"{t}, {nachschlagen.lesbar(_firma(r.get('name')))}"
            text = "; ".join(nachschlagen.lesbar(x) for x in teile)
        zeile = f"{i}. {kopf}" + (f"; {text}" if text else "")
        if not zeile.endswith("."):
            zeile += "."
        if not markdown:
            zeile += f" Vollständige Daten: {url}"
        raus.append(zeile)
    return raus


def einstellungs_teile(e, tabelle=None):
    """Die aktiven Einstellungen in Worten."""
    e = {**standard_einstellung(), **(e or {})}
    t = []
    k = e.get("strategie") or ""
    if k:
        t.append(strategie_name(k) + ((f", auch mit {toleranz_prozent()} Prozent Toleranz" if e.get("toleranz") else ", streng")
                                      if toleranz_moeglich(k) else ""))
    if e.get("nur_handelbar"):
        t.append("nur handelbare Aktien")
    if k == "darvas" and e.get("langweilig_raus"):
        t.append("ohne langweilige Boxen")
    for feld, fe in aktive_felder(e):
        t.append(feld.einstellung_text(fe))
    te = e.get("termine") or {}
    if te.get("an"):
        zeiten = [text for key, text, _p, _l in TERMIN_TEILE if te.get(key)]
        s = "Zahlentermine " + (", ".join(zeiten) if zeiten else "angezeigt")
        if te.get("ohne_zeit"):
            s += ", auch ohne bekannte Tageszeit"
        s += ", " + dict(UMFANG).get(te.get("umfang") or "markt", "ganzer Markt")
        t.append(s)
    if e.get("sektoren") is not None and tabelle is not None:
        alle = sektoren_in(tabelle)
        gewaehlt = [s for s in alle if s in set(e["sektoren"])]
        if len(gewaehlt) != len(alle):
            t.append("Sektoren " + (", ".join(sektor_name(s) for s in gewaehlt) if gewaehlt else "keiner"))
    return t


def ergebnis_tabelle(ausw, basis_url, stand=None):
    """Die Treffer als Tabelle fuer die Dateien, nur mit den angehakten Merkmalen."""
    df = ausw["df"]
    raus = pd.DataFrame(index=df.index)
    raus["Kürzel"] = df["ticker"] if "ticker" in df.columns else pd.Series(dtype="object")
    raus["Firma"] = df["name"].map(_firma) if "name" in df.columns else "Name unbekannt"
    k = ausw.get("strategie") or ""
    if ist_muster(k) and f"m_{k}" in df.columns:
        raus["Strategie"] = strategie_name(k)
        raus["Erfüllt"] = pd.to_numeric(df[f"m_{k}"], errors="coerce").map({2: "streng", 1: "mit Toleranz"})
        raus["Rating"] = _zahlen(df, f"rating_{k}")
        raus["Begründung des Ratings"] = _sp(df, f"grund_{k}")
        kp = _zahlen(df, f"kp_{k}")
        if kp.notna().any():
            raus["Kaufpunkt in Dollar"] = kp.round(2)
            raus["Stop in Dollar"] = _zahlen(df, f"stop_{k}").round(2)
        raus["Status"] = _sp(df, f"status_{k}").map(lambda s: nachschlagen.anzeige_text(s) if isinstance(s, str) else "")
        if k == "trend_template":
            raus["Bedingungen des Trend Templates erfüllt"] = _zahlen(df, "tt_count")
        if k == "darvas":
            raus["Boxhöhe in Prozent"] = _zahlen(df, "darvas_box_hoehe_pct").round(2)
            raus["Langweilige Box"] = _sp(df, "darvas_langweilig_gruende").map(lambda s: s if isinstance(s, str) else "")
    elif k in dict(SIGNALE):
        raus["Chart-Signal"] = strategie_name(k)
    for feld, fe in ausw.get("felder") or []:
        for kopf, werte in feld.datei_spalten(df, fe, ausw.get("analysten_da", True)):
            raus[kopf] = werte
    if ausw.get("termine"):
        raus["Zahlentermin"] = _sp(df, "termin_datum").map(lambda d: nachschlagen.datum_text(d) if isinstance(d, str) and d else "")
        raus["Tageszeit"] = _sp(df, "termin_lage").map(lambda x: LAGE_TEXT.get(x, "") if isinstance(x, str) else "")
        raus["Quelle des Termins"] = _sp(df, "termin_quelle")
    if ausw.get("sektor_aktiv"):
        raus["Sektor"] = _sp(df, "sektor").map(lambda s: sektor_name(s if isinstance(s, str) else ""))
    raus["Schlusskurse vom"] = nachschlagen.datum_text((stand or {}).get("handelstag")) if (stand or {}).get("handelstag") else ""
    raus["Vollständige Daten"] = raus["Kürzel"].map(lambda t: adresse(basis_url, t))
    return raus.reset_index(drop=True)


FORMATE = (("csv_de", "CSV mit Strichpunkt und Dezimalbeistrich, für Excel auf Deutsch", "csv", "text/csv"),
           ("csv_en", "CSV mit Beistrich und Dezimalpunkt, international", "csv", "text/csv"),
           ("xlsx", "Excel-Arbeitsmappe, XLSX", "xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
           ("ods", "OpenDocument-Tabelle für LibreOffice, ODS", "ods", "application/vnd.oasis.opendocument.spreadsheet"),
           ("json", "JSON", "json", "application/json"),
           ("html", "HTML-Tabelle zum Öffnen im Browser", "html", "text/html"),
           ("txt", "Text, eine Zeile je Aktie", "txt", "text/plain"),
           ("md", "Markdown", "md", "text/markdown"))


def kopf_saetze(ausw, stand=None, tabelle=None):
    s = ["Heliot-Scanner"]
    if (stand or {}).get("handelstag"):
        s.append(f"Schlusskurse vom {datum_lang(stand['handelstag'])}")
    teile = einstellungs_teile(ausw.get("einstellung"), tabelle)
    s.append("Einstellungen: " + ("; ".join(teile) if teile else "keine"))
    s.append(f"Treffer: {len(ausw['df'])} von {ausw.get('gesamt', 0)} Aktien mit Kursen vom letzten Handelstag")
    return s


def dateiname(ausw, stand, fmt):
    endung = next((x[2] for x in FORMATE if x[0] == fmt), "txt")
    teil = ausw.get("strategie") or "einstellungen"
    tag = str((stand or {}).get("handelstag") or "")[:10] or date.today().isoformat()
    return f"scanner_{teil}_{tag}.{endung}"


def _json_wert(x):
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        return float(x) if math.isfinite(float(x)) else None
    if isinstance(x, np.bool_):
        return bool(x)
    if x is pd.NA or x is None:
        return None
    return x


def _zelle_html(x, stellen=2):
    if isinstance(x, (int, float, np.integer, np.floating)) and not isinstance(x, bool):
        v = _num(x)
        if v is None:
            return ""
        return nachschlagen.zahl(v, 0 if float(v).is_integer() else stellen)
    if x is None or x is pd.NA or (isinstance(x, float) and not math.isfinite(x)):
        return ""
    return html_text.escape(nachschlagen.lesbar(str(x)))


def datei(ausw, basis_url, fmt, stand=None, tabelle=None):
    """(Inhalt als bytes, MIME-Typ, Dateiname) im gewaehlten Format."""
    tab = ergebnis_tabelle(ausw, basis_url, stand)
    mime = next((x[3] for x in FORMATE if x[0] == fmt), "text/plain")
    name = dateiname(ausw, stand, fmt)
    kopf = kopf_saetze(ausw, stand, tabelle)
    if fmt == "csv_de":
        return tab.to_csv(sep=";", decimal=",", index=False).encode("utf-8-sig"), mime, name
    if fmt == "csv_en":
        return tab.to_csv(index=False).encode("utf-8"), mime, name
    if fmt in ("xlsx", "ods"):
        puffer = io.BytesIO()
        with pd.ExcelWriter(puffer, engine="openpyxl" if fmt == "xlsx" else "odf") as w:
            tab.to_excel(w, sheet_name="Scanner", index=False)
            pd.DataFrame({"Angaben": kopf}).to_excel(w, sheet_name="Einstellungen", index=False)
        return puffer.getvalue(), mime, name
    if fmt == "json":
        inhalt = {"titel": kopf[0], "angaben": kopf[1:],
                  "aktien": [{k2: _json_wert(v) for k2, v in z.items()} for z in tab.to_dict("records")]}
        return json.dumps(inhalt, ensure_ascii=False, indent=1).encode("utf-8"), mime, name
    if fmt == "html":
        kopfzeile = "".join(f'<th scope="col">{html_text.escape(str(c))}</th>' for c in tab.columns)
        koerper = []
        for z in tab.to_dict("records"):
            zellen = []
            for c, v in z.items():
                if c == "Kürzel":
                    zellen.append(f'<th scope="row"><a href="{html_text.escape(adresse(basis_url, v))}">'
                                  f"{html_text.escape(str(v))}</a></th>")
                elif c == "Vollständige Daten":
                    zellen.append(f'<td><a href="{html_text.escape(str(v))}">{html_text.escape(str(v))}</a></td>')
                else:
                    zellen.append(f"<td>{_zelle_html(v)}</td>")
            koerper.append("<tr>" + "".join(zellen) + "</tr>")
        seite = ("<!DOCTYPE html>\n<html lang=\"de\">\n<head>\n<meta charset=\"utf-8\">\n"
                 f"<title>{html_text.escape(kopf[0])}</title>\n</head>\n<body>\n<h1>{html_text.escape(kopf[0])}</h1>\n"
                 + "".join(f"<p>{html_text.escape(x)}</p>\n" for x in kopf[1:])
                 + f"<table>\n<caption>{html_text.escape(kopf[-1])}</caption>\n<thead><tr>{kopfzeile}</tr></thead>\n"
                 + "<tbody>\n" + "\n".join(koerper) + "\n</tbody>\n</table>\n</body>\n</html>\n")
        return seite.encode("utf-8"), mime, name
    if fmt == "md":
        text = "\n".join([f"# {kopf[0]}", ""] + [md(x) + "  " for x in kopf[1:]] + [""]
                         + zeilen(ausw, basis_url, markdown=True)) + "\n"
        return text.encode("utf-8"), mime, name
    text = "\n".join(kopf + [""] + zeilen(ausw, basis_url, markdown=False)) + "\n"
    return text.encode("utf-8"), "text/plain", name


# ---------------------------------------------------------------------------
# Stand und Grenzen
# ---------------------------------------------------------------------------

def letzter_handelstag_ny(jetzt=None):
    """Der zuletzt geschlossene Handelstag ohne Feiertage: werktags ab 16:30
    New Yorker Zeit der Tag selbst, sonst der Werktag davor."""
    j = ny_jetzt(jetzt)
    tag = j.date()
    if tag.weekday() >= 5 or (j.hour, j.minute) < (16, 30):
        tag -= timedelta(days=1)
        while tag.weekday() >= 5:
            tag -= timedelta(days=1)
    return tag


def stand_saetze(stand, jetzt=None, analysten_da=True):
    stand = stand or {}
    s = []
    ht = stand.get("handelstag")
    zeit = wiener_zeit(stand.get("gebaut_am")) if stand.get("gebaut_am") else None
    if ht:
        s.append(f"Stand der Daten: Schlusskurse vom {datum_lang(ht)}" + (f", gebaut am {zeit}" if zeit else "") + ".")
    q = stand.get("quellen") or {}
    kurse = q.get("kurse") or {}
    if kurse:
        s.append(f"{nachschlagen.zahl(kurse.get('aktuell', 0))} von {nachschlagen.zahl(stand.get('universum', 0))} "
                 "Aktien des US-Markts haben Kurse vom letzten Handelstag.")
    if stand.get("status") and stand.get("status") != "ok":
        s.append("Achtung, die Tabelle ist unvollständig: " + "; ".join(stand.get("hinweise") or ["ohne Angabe"]) + ".")
    try:
        if ht and date.fromisoformat(str(ht)[:10]) < letzter_handelstag_ny(jetzt):
            s.append("Ist seither ein Handelstag zu Ende gegangen, entsteht die neue Tabelle nach dem Nachtscan.")
    except ValueError:
        pass
    fund = q.get("fundament") or {}
    if fund and str(fund.get("status", "")).startswith("nicht"):
        s.append("Fundamentzahlen fehlen in dieser Tabelle: " + str(fund.get("status")) + ".")
    an = q.get("analysten") or {}
    if not analysten_da:
        s.append("Analystendaten sind nicht geladen: Sie liegen im privaten Datenrepo, und in den Streamlit-Secrets "
                 "fehlt der Lese-Token DATEN_LESE_TOKEN.")
    elif an and stand.get("zeilen") and (an.get("mit_stand") or 0) < stand.get("zeilen"):
        s.append(f"Analystendaten bisher für {nachschlagen.zahl(an.get('mit_stand') or 0)} von "
                 f"{nachschlagen.zahl(stand.get('zeilen'))} Aktien; jede Nacht kommt ein Siebtel dazu.")
    return s


def grenzen_saetze():
    """Was der Scanner nicht kann, und warum."""
    return [
        "Change from Open und Red to Green beschreiben den letzten abgeschlossenen Handelstag. Live während des "
        "Handels rechnet der Scanner nicht: Die Tabelle entsteht nachts aus Tageskerzen für den ganzen Markt. "
        "Live-Signale bleiben beim Breakout-Wächter.",
        "Die Fundamentzahlen sind so frisch wie das SEC-Fundament-Release; ein neuer Quartalsbericht erscheint "
        "erst nach dessen nächstem Lauf.",
        "Analystenempfehlungen und Gewinnüberraschungen holt der Scanner je Nacht für ein Siebtel des Markts und "
        "für alle, die gerade Zahlen gemeldet haben; nach sieben Nächten ist jede Aktie einmal dran. Nasdaq nennt "
        "die Überraschungen der letzten vier Quartale, weiter zurück reicht die Quote deshalb nicht.",
        "Zahlentermine kommen aus dem Nasdaq-Kalender der nächsten zehn Tage, für die Wochenlisten aus der "
        "genaueren Terminliste des Nachtscans. Feiertage kennt der Scanner nicht; morgen heißt der nächste Werktag.",
        f"Die Toleranz von {toleranz_prozent()} Prozent gilt für Schwellen in Prozent, Verhältnisse und Dauern. "
        "Zählregeln, Richtungen und feste Formbedingungen der Muster bleiben streng; EMA Crossback und Power-Gap "
        "haben keine Toleranzstufe.",
        "Power-Gap prüft die Tageskerze. Die Frühregel der ersten halben Stunde lässt sich nur live prüfen und "
        "fehlt hier.",
        "Das alte Excel-Format XLS lässt sich nicht mehr schreiben: Pandas hat den Schreiber mit Version 2.0 "
        "entfernt, und die dafür nötige Bibliothek wird nicht mehr gepflegt. XLSX öffnet jedes Excel seit 2007.",
    ]


# ---------------------------------------------------------------------------
# Selbsttest (ohne Netz)
# ---------------------------------------------------------------------------

def _probe_tabelle():
    zeilen_p = [
        {"ticker": "AAA", "name": "Alpha Inc. - Common Stock", "kurse_aktuell": True, "handelbar": True,
         "in_wochenliste": True, "kurs": 120.0, "marktkap_mrd": 0.3, "volumen_50": 900000.0,
         "dollarvolumen_50": 5e7, "aktien_ausstehend": 25e6, "umsatz_q_vj_pct": 30.0, "eps_q_vj_pct": 55.5,
         "bruttomarge_q_vj_pp": 1.5, "abst_ema21_pct": 2.0, "abst_ema50_pct": 8.0, "abst_ema200_pct": 30.0,
         "abst_hoch_1j_pct": -3.0, "abst_tief_1j_pct": 80.0, "abst_hoch_3m_pct": -1.0, "rs": 95, "rs_vorlaeufig": None,
         "rs_linie_hoch": True, "rs_linie_abst_pct": 0.0, "red_to_green": False, "veraenderung_pct": 1.2,
         "seit_eroeffnung_pct": 0.5, "volatilitaet_20_pct": 4.4, "tagesspanne_pct": 3.0, "volumen_max_tage_her": 2,
         "volumen_max": 5e6, "volumen_max_datum": "2026-09-09", "sektor": "Technology", "termin_datum": "2026-09-14",
         "termin_lage": "nachboerslich", "termin_quelle": "Wochenliste", "m_darvas": 2, "rating_darvas": 82,
         "grund_darvas": "stark: relative Stärke, Nachfrage; schwach: Enge", "kp_darvas": 121.5, "stop_darvas": 110.0,
         "status_darvas": "Box $110.00 bis $121.50", "darvas_box_hoehe_pct": 9.5, "darvas_langweilig": False,
         "darvas_langweilig_gruende": None, "m_trend_template": 2, "rating_trend_template": 70, "tt_count": 8,
         "schulden_zu_ek": 0.4, "konsens": "Kaufen", "konsens_wert": 4, "analysten_kaufen": 10,
         "analysten_halten": 2, "analysten_verkaufen": 0, "schaetzung_geschlagen": 4, "quartale_mit_schaetzung": 4,
         "kursziel": 140.0, "kursziel_abst_pct": 16.67},
        {"ticker": "BBB", "name": "Beta_Corp *Test*", "kurse_aktuell": True, "handelbar": True,
         "in_wochenliste": False, "kurs": 15.0, "marktkap_mrd": 1200.0, "volumen_50": 100000.0,
         "dollarvolumen_50": 1.5e6, "umsatz_q_vj_pct": None, "abst_ema21_pct": -4.0, "abst_ema50_pct": -1.0,
         "abst_hoch_1j_pct": -26.0, "abst_tief_1j_pct": 24.0, "rs": None, "rs_vorlaeufig": 80,
         "rs_linie_hoch": False, "rs_linie_abst_pct": -2.5, "red_to_green": True, "seit_eroeffnung_pct": 3.0,
         "volumen_max_tage_her": 30, "sektor": None, "termin_datum": "2026-09-15", "termin_lage": "vorboerslich",
         "termin_quelle": "Nasdaq", "m_darvas": 1, "rating_darvas": 40, "darvas_langweilig": True,
         "darvas_langweilig_gruende": "mittlere Tagesspanne unter 2,5 Prozent", "m_trend_template": 1,
         "konsens": "Halten", "konsens_wert": 3, "schaetzung_geschlagen": 2, "quartale_mit_schaetzung": 4},
        {"ticker": "CCC", "name": "Gamma", "kurse_aktuell": True, "handelbar": False, "in_wochenliste": True,
         "kurs": 8.0, "marktkap_mrd": 0.05, "abst_hoch_1j_pct": -50.0, "rs": 30, "m_darvas": 0,
         "m_trend_template": 0, "sektor": "Finance", "termin_datum": "2026-09-14", "termin_lage": "unbekannt",
         "red_to_green": None},
        {"ticker": "DDD", "name": "Delta", "kurse_aktuell": False, "handelbar": True, "kurs": 50.0, "rs": 99,
         "m_darvas": 2, "rating_darvas": 99, "sektor": "Technology"},
    ]
    return pd.DataFrame(zeilen_p)


def selbsttest() -> int:
    fehler = []

    def p(name, ok, zusatz=""):
        print(f"  {'ok  ' if ok else 'FEHL'} {name}" + (f"; {zusatz}" if zusatz else ""))
        if not ok:
            fehler.append(name)

    print("Scanner-Ansicht, Selbsttest")
    heute = date(2026, 9, 14)

    # Zahlen, wie man sie tippt
    p("Zahlen: Beistrich, Tausenderpunkt, Minus, Wort und Einheit",
      zahl_lesen("0,3")[0] == 0.3 and zahl_lesen("1.000")[0] == 1000.0 and zahl_lesen("1000")[0] == 1000.0
      and zahl_lesen("-5")[0] == -5.0 and zahl_lesen("minus 5")[0] == -5.0 and zahl_lesen("12 Prozent")[0] == 12.0
      and zahl_lesen("10.000,5")[0] == 10000.5 and zahl_lesen("0.3")[0] == 0.3 and zahl_lesen(_MINUS + "2")[0] == -2.0
      and zahl_lesen(",5")[0] == 0.5)
    p("Zahlen: leer ist keine Grenze, Unsinn ist ein Fehler",
      zahl_lesen("") == (None, "") and zahl_lesen(None) == (None, "") and zahl_lesen("abc")[0] is None
      and "keine Zahl" in zahl_lesen("abc")[1] and zahl_lesen("1,2,3")[0] is None)
    p("Zahlen fuer die Felder", zahl_eingabe(66.5) == "66,5" and zahl_eingabe(25.0) == "25"
      and zahl_eingabe(23.75) == "23,75" and zahl_eingabe(None) == "")
    p("Deutsche Anzeige mit Vorzeichen", mit_vorzeichen(12.34, 1) == "plus 12,3" and mit_vorzeichen(-4.5, 1) == "minus 4,5"
      and mit_vorzeichen(None) == "nicht berechenbar" and mit_vorzeichen(0.001, 1) == "0,0")
    p("Markdown: Dollar, Stern, Unterstrich und Klammern werden entschaerft",
      md("Box $110 *fett* a_b [x]") == "Box \\$110 \\*fett\\* a\\_b \\[x\\]" and "--" not in md("a -- b"))

    tab = _probe_tabelle()

    # Grundfilter
    a = auswerten(tab, {"nur_handelbar": False}, heute)
    p("Nur Aktien mit Kursen vom letzten Handelstag", set(a["df"]["ticker"]) == {"AAA", "BBB", "CCC"} and a["gesamt"] == 3)
    a = auswerten(tab, {"nur_handelbar": True}, heute)
    p("Nur handelbare", set(a["df"]["ticker"]) == {"AAA", "BBB"})

    # Strategie, Toleranz, Langeweile
    a = auswerten(tab, {"strategie": "darvas", "langweilig_raus": False}, heute)
    p("Darvas streng: nur Stufe 2", list(a["df"]["ticker"]) == ["AAA"])
    a = auswerten(tab, {"strategie": "darvas", "toleranz": True, "langweilig_raus": False}, heute)
    p("Darvas mit Toleranz: Stufe 1 dazu, nach Rating sortiert", list(a["df"]["ticker"]) == ["AAA", "BBB"])
    a = auswerten(tab, {"strategie": "darvas", "toleranz": True, "langweilig_raus": True}, heute)
    p("Langweilige Box aussortiert", list(a["df"]["ticker"]) == ["AAA"])
    a = auswerten(tab, {"strategie": "rs_linie"}, heute)
    p("Chart-Signal RS-Linie", list(a["df"]["ticker"]) == ["AAA"])
    a = auswerten(tab, {"strategie": "red_to_green"}, heute)
    p("Chart-Signal Red to Green, None ist nein", list(a["df"]["ticker"]) == ["BBB"])
    p("Toleranz gibt es nur bei Mustern mit Schwellen",
      toleranz_moeglich("darvas") and not toleranz_moeglich("power_gap") and not toleranz_moeglich("rs_linie"))

    # Bereiche
    def felder(**kw):
        return {"nur_handelbar": False, "felder": kw}

    a = auswerten(tab, felder(marktkap={"an": True, "min": "0,3"}), heute)
    p("Marktkapitalisierung ab 0,3 Milliarden, Grenze eingeschlossen", set(a["df"]["ticker"]) == {"AAA", "BBB"})
    a = auswerten(tab, felder(marktkap={"an": True, "min": "1000"}), heute)
    p("Marktkapitalisierung ab 1000 Milliarden", list(a["df"]["ticker"]) == ["BBB"])
    a = auswerten(tab, felder(umsatz_q={"an": True, "min": "10"}), heute)
    p("Fehlender Wert faellt bei einer Grenze heraus", list(a["df"]["ticker"]) == ["AAA"])
    a = auswerten(tab, felder(umsatz_q={"an": True}), heute)
    p("Angehakt ohne Grenze filtert nicht", len(a["df"]) == 3)
    a = auswerten(tab, felder(kurs={"an": True, "min": "zehn"}), heute)
    p("Unlesbare Grenze wirkt nicht und wird gemeldet", len(a["df"]) == 3 and a["fehler"] and "zehn" in a["fehler"][0])
    a = auswerten(tab, felder(volumen={"an": True, "min": "500.000"}), heute)
    p("Volumen mit Tausenderpunkt", list(a["df"]["ticker"]) == ["AAA"])
    a = auswerten(tab, felder(umsatz_dollar={"an": True, "min": "10"}), heute)
    p("Tagesumsatz in Millionen Dollar", list(a["df"]["ticker"]) == ["AAA"])

    # Hoch, Tief, EMA, RS
    a = auswerten(tab, felder(hoch={"an": True, "wahl": "1j", "max": "25"}), heute)
    p("Hoechstens 25 Prozent unter dem Jahreshoch", list(a["df"]["ticker"]) == ["AAA"])
    a = auswerten(tab, felder(hoch={"an": True, "wahl": "3m", "max": "2"}), heute)
    p("Zeitraum waehlt die Spalte: Quartalshoch", list(a["df"]["ticker"]) == ["AAA"])
    a = auswerten(tab, felder(tief={"an": True, "wahl": "1j", "min": "25"}), heute)
    p("Mindestens 25 Prozent ueber dem Jahrestief", list(a["df"]["ticker"]) == ["AAA"])
    a = auswerten(tab, felder(ema21={"an": True, "lage": "darunter"}), heute)
    p("EMA 21: Kurs darunter", list(a["df"]["ticker"]) == ["BBB"])
    a = auswerten(tab, felder(ema50={"an": True, "lage": "darueber", "min": "5"}), heute)
    p("EMA 50: darueber und mindestens 5 Prozent", list(a["df"]["ticker"]) == ["AAA"])
    a = auswerten(tab, felder(rs={"an": True, "min": "70"}), heute)
    p("RS ab 70 ohne vorlaeufiges RS", list(a["df"]["ticker"]) == ["AAA"])
    a = auswerten(tab, felder(rs={"an": True, "min": "70", "vorlaeufig": True}), heute)
    p("RS ab 70 mit vorlaeufigem RS junger Titel", set(a["df"]["ticker"]) == {"AAA", "BBB"})
    a = auswerten(tab, felder(neu_52w={"an": True}), heute)
    p("Ja-Feld ohne Spalte laesst nichts durch", a["df"].empty)

    # Stufen und Analysten
    a = auswerten(tab, felder(konsens={"an": True, "wahl": "4"}), heute)
    p("Konsens mindestens Kaufen", list(a["df"]["ticker"]) == ["AAA"])
    a = auswerten(tab, felder(konsens={"an": True, "wahl": "3"}), heute)
    p("Konsens mindestens Halten", set(a["df"]["ticker"]) == {"AAA", "BBB"})
    a = auswerten(tab, felder(konsens={"an": True, "wahl": "anzeigen"}), heute)
    p("Stufe nur anzeigen filtert nicht", len(a["df"]) == 3)
    a = auswerten(tab, felder(beat={"an": True, "wahl": "3"}), heute)
    p("Schaetzung in mindestens drei von vier Quartalen geschlagen", list(a["df"]["ticker"]) == ["AAA"])
    a = auswerten(tab, felder(volmax={"an": True, "wahl": "2"}), heute)
    p("Groesstes Volumen jemals heute bis vor zwei Handelstagen", list(a["df"]["ticker"]) == ["AAA"])
    a = auswerten(tab, felder(konsens={"an": True, "wahl": "5"}), heute, analysten_da=False)
    p("Ohne Analystendaten filtert das Feld nicht und sagt es",
      len(a["df"]) == 3 and any("Analystendaten" in h for h in a["hinweise"]))

    # Termine und Sektoren
    a = auswerten(tab, {"nur_handelbar": False, "termine": {"an": True, "heute_nach": True}}, heute)
    p("Zahlen heute nachboerslich", list(a["df"]["ticker"]) == ["AAA"])
    a = auswerten(tab, {"nur_handelbar": False, "termine": {"an": True, "morgen_vor": True}}, heute)
    p("Zahlen morgen vorboerslich", list(a["df"]["ticker"]) == ["BBB"])
    a = auswerten(tab, {"nur_handelbar": False, "termine": {"an": True, "heute_vor": True, "ohne_zeit": True}}, heute)
    p("Heute auch ohne bekannte Tageszeit", list(a["df"]["ticker"]) == ["CCC"])
    a = auswerten(tab, {"nur_handelbar": False, "termine": {"an": True, "heute_nach": True, "heute_vor": True,
                                                               "ohne_zeit": True, "umfang": "listen"}}, heute)
    p("Nur die Wochenlisten", set(a["df"]["ticker"]) == {"AAA", "CCC"})
    p("Morgen am Freitag heisst Montag", naechster_handelstag(date(2026, 9, 18)) == date(2026, 9, 21))
    alle_s = sektoren_in(tab)
    p("Sektoren: bekannte und ohne Angabe, deutsch sortiert", "" in alle_s and alle_s[-1] == "" and "Technology" in alle_s)
    a = auswerten(tab, {"nur_handelbar": False, "sektoren": alle_s}, heute)
    p("Alle Sektoren angehakt filtert nicht", len(a["df"]) == 3 and not a["sektor_aktiv"])
    a = auswerten(tab, {"nur_handelbar": False, "sektoren": ["Technology"]}, heute)
    p("Nur Technologie", list(a["df"]["ticker"]) == ["AAA"] and a["sektor_aktiv"])
    a = auswerten(tab, {"nur_handelbar": False, "sektoren": [s for s in alle_s if s != ""]}, heute)
    p("Ohne Sektorangabe abgewaehlt", "BBB" not in set(a["df"]["ticker"]))

    # Sortierung
    a = auswerten(tab, {"nur_handelbar": False, "sortierung": "marktkap"}, heute)
    p("Sortiert nach Marktkapitalisierung", list(a["df"]["ticker"]) == ["BBB", "AAA", "CCC"])
    a = auswerten(tab, {"nur_handelbar": False, "felder": {"kurs": {"an": True}}, "sortierung": "kurs:auf"}, heute)
    p("Sortiert nach einem angehakten Feld, aufsteigend", list(a["df"]["ticker"]) == ["CCC", "BBB", "AAA"])
    a = auswerten(tab, {"nur_handelbar": False, "sortierung": "rs"}, heute)
    p("RS absteigend, vorlaeufiges RS zaehlt, fehlendes zuletzt", list(a["df"]["ticker"]) == ["AAA", "BBB", "CCC"])
    p("Unbekannte Sortierung faellt auf das Rating zurueck",
      list(auswerten(tab, {"strategie": "darvas", "toleranz": True, "langweilig_raus": False,
                           "sortierung": "unsinn"}, heute)["df"]["ticker"]) == ["AAA", "BBB"])

    # Voreinstellungen und ihre Treue zum Detektor
    import pattern_scanner as ps
    v = voreinstellung("trend_template")
    p("Trend Template traegt die Schwellen des Detektors ein",
      v["rs"]["min"] == zahl_eingabe(ps.CFG["tt_rs_min"]) and v["tief"]["min"] == zahl_eingabe(ps.CFG["tt_min_above_low"] * 100)
      and v["hoch"]["max"] == zahl_eingabe(ps.CFG["tt_max_below_high"] * 100) and v["hoch"]["wahl"] == "1j"
      and v["ema50"] == {"an": True})
    vt = voreinstellung("trend_template", toleranz=True)
    p("Mit Toleranz gelockert", vt["rs"]["min"] == "66,5" and vt["tief"]["min"] == "23,75" and vt["hoch"]["max"] == "26,25",
      str(vt))
    p("Power-Gap ohne Toleranzstufe bleibt ohne Lockerung", voreinstellung("power_gap", True) == voreinstellung("power_gap"))
    treu_streng = treu_locker = geprueft_s = geprueft_l = 0
    for seed in range(80):
        roh = sd._kunstreihe(seed=seed, schritt=0.0005 * (seed % 6), streuung=0.008 + 0.002 * (seed % 3))
        di = ps.add_indicators(roh)
        werte_k = sd.kurs_werte(roh, sd.extrema(roh))
        for rs_w in (68.0, 75.0, 90.0):
            zeile = {"ticker": f"S{seed}", "kurse_aktuell": True, "handelbar": True, **werte_k, "rs": rs_w}
            if sd.trend_template(di, rs_w, 0.0)[0]:
                geprueft_s += 1
                t1 = pd.DataFrame([{**zeile, "m_trend_template": 2}])
                treu_streng += int(len(auswerten(t1, {"strategie": "trend_template", "nur_handelbar": False,
                                                      "felder": voreinstellung("trend_template")}, heute)["df"]) == 1)
            if sd.trend_template(di, rs_w, float(SC["toleranz"]))[0]:
                geprueft_l += 1
                t2 = pd.DataFrame([{**zeile, "m_trend_template": 1}])
                treu_locker += int(len(auswerten(t2, {"strategie": "trend_template", "toleranz": True, "nur_handelbar": False,
                                                      "felder": voreinstellung("trend_template", True)}, heute)["df"]) == 1)
    p("Vorgabe filtert keinen strengen Treffer des Detektors weg",
      geprueft_s >= 5 and treu_streng == geprueft_s, f"{treu_streng} von {geprueft_s}")
    p("Vorgabe mit Toleranz filtert keinen gelockerten Treffer weg",
      geprueft_l >= geprueft_s and treu_locker == geprueft_l, f"{treu_locker} von {geprueft_l}")
    p("Jede Strategie der Auswahl hat einen Text und eine Vorgabe ohne unbekannte Felder",
      all(strategie_text(k) and all(s in FELD for s in voreinstellung(k)) for k, _n in AUSWAHL))

    # Ergebnisliste: nur Angehaktes, Verweise, Satzform
    e = {"strategie": "darvas", "nur_handelbar": False, "langweilig_raus": False,
         "felder": {"rs": {"an": True}, "hoch": {"an": True, "wahl": "1j"}, "marktkap": {"an": True}},
         "termine": {"an": True}}
    a = auswerten(tab, e, heute)
    z = zeilen(a, "https://heliot.streamlit.app", markdown=True)
    p("Liste: nummeriert, Kuerzel als Verweis auf die vollstaendigen Daten",
      z and z[0].startswith("1. [AAA](https://heliot.streamlit.app/?aktie=AAA), Alpha Inc.;"), z[0] if z else "")
    p("Liste: angehakte Merkmale stehen drin, andere nicht",
      "RS 95" in z[0] and "3,0 Prozent unter dem Jahreshoch" in z[0] and "Marktkapitalisierung 0,30 Milliarden Dollar" in z[0]
      and "Umsatzwachstum" not in z[0] and "EMA" not in z[0] and "Zahlen am Montag, 14.09.2026, nachbörslich" in z[0], z[0])
    p("Liste: Strategie mit Rating, Begruendung, Kaufpunkt, Stop und Status ohne Formel-Dollar",
      "Darvas Box streng erfüllt" in z[0] and "Rating 82 von 100, stark: relative Stärke, Nachfrage, schwach: Enge" in z[0]
      and "Kaufpunkt 121,50 Dollar" in z[0] and "Stop 110,00 Dollar" in z[0] and "\\$110" in z[0], z[0])
    t_z = zeilen(a, "https://heliot.streamlit.app", markdown=False)
    p("Textliste mit Adresse am Ende und ohne Markdown",
      t_z[0].startswith("1. AAA, Alpha Inc.;") and t_z[0].endswith("Vollständige Daten: https://heliot.streamlit.app/?aktie=AAA")
      and "\\" not in t_z[0], t_z[0])
    p("Firmennamen ohne Wertpapierzusatz und ohne doppelten Punkt",
      _firma("Ternium S.A. Ternium S.A. American Depositary Shares (each representing ten shares, USD1.00 par value)")
      == "Ternium S.A." and _firma("Hinge Health, Inc. Class A") == "Hinge Health, Inc."
      and _firma("Frontline Plc Ordinary Shares") == "Frontline Plc" and _firma("Class Acceptance Corp") == "Class Acceptance Corp"
      and _firma("Bank of America Corporation Common Stock") == "Bank of America Corporation" and _firma(None) == "Name unbekannt"
      and zeilen(auswerten(pd.DataFrame([{"ticker": "X", "name": "Dave Inc.", "kurse_aktuell": True}]),
                           {"nur_handelbar": False}, heute), "https://x")[0] == "1. [X](https://x/?aktie=X), Dave Inc.")
    p("Firmenname mit Sonderzeichen wird in Markdown entschaerft",
      "Beta\\_Corp \\*Test\\*" in zeilen(auswerten(tab, {"nur_handelbar": False, "felder": {}}, heute), "https://x")[1])
    p("Kein langer Strich in der Liste", all(chr(0x2013) not in x and chr(0x2014) not in x for x in z + t_z))

    # Dateien
    stand = {"handelstag": "2026-09-11", "gebaut_am": "2026-09-14T04:35:00+00:00"}
    tabelle_e = ergebnis_tabelle(a, "https://heliot.streamlit.app", stand)
    p("Datei: nur angehakte Spalten, Verweis und Stand",
      "RS" in tabelle_e.columns and "Prozent unter dem Jahreshoch" in tabelle_e.columns
      and "Marktkapitalisierung in Milliarden Dollar" in tabelle_e.columns and "Umsatzwachstum q/q in Prozent" not in tabelle_e.columns
      and tabelle_e.loc[0, "Vollständige Daten"] == "https://heliot.streamlit.app/?aktie=AAA"
      and tabelle_e.loc[0, "Schlusskurse vom"] == "11.09.2026", list(tabelle_e.columns))
    inhalte = {}
    for fmt, _t, _e, _m in FORMATE:
        try:
            inhalte[fmt] = datei(a, "https://heliot.streamlit.app", fmt, stand, tab)
        except ImportError as ex:
            inhalte[fmt] = ex
    csv_de = inhalte["csv_de"][0].decode("utf-8-sig")
    p("CSV deutsch: Strichpunkt und Dezimalbeistrich", csv_de.startswith("Kürzel;Firma;") and "0,3" in csv_de, csv_de[:80])
    p("CSV international: Beistrich und Punkt", inhalte["csv_en"][0].decode("utf-8").startswith("Kürzel,Firma,"))
    x = pd.read_excel(io.BytesIO(inhalte["xlsx"][0]), sheet_name=None)
    p("Excel mit zwei Blaettern, Treffer und Einstellungen",
      set(x) == {"Scanner", "Einstellungen"} and x["Scanner"].loc[0, "Kürzel"] == "AAA"
      and any("Darvas Box" in str(s) for s in x["Einstellungen"]["Angaben"]))
    if isinstance(inhalte["ods"], ImportError):
        p("OpenDocument: odfpy fehlt in dieser Umgebung, die App hat es ueber requirements.txt", True,
          str(inhalte["ods"]))
    else:
        o = pd.read_excel(io.BytesIO(inhalte["ods"][0]), engine="odf", sheet_name="Scanner")
        p("OpenDocument lesbar", o.loc[0, "Kürzel"] == "AAA")
    j = json.loads(inhalte["json"][0].decode("utf-8"))
    p("JSON mit Angaben und Aktien, fehlende Werte als null",
      j["titel"] == "Heliot-Scanner" and j["aktien"][0]["Kürzel"] == "AAA" and "NaN" not in inhalte["json"][0].decode("utf-8"))
    h = inhalte["html"][0].decode("utf-8")
    p("HTML: Tabelle mit Beschriftung, Spaltenkoepfen und Verweis, deutsche Zahlen",
      '<html lang="de">' in h and "<caption>" in h and '<th scope="col">Kürzel</th>' in h
      and 'href="https://heliot.streamlit.app/?aktie=AAA"' in h and "0,3" in h)
    p("Text und Markdown", inhalte["txt"][0].decode("utf-8").startswith("Heliot-Scanner")
      and inhalte["md"][0].decode("utf-8").startswith("# Heliot-Scanner"))
    p("Dateiname nennt Strategie und Handelstag", inhalte["xlsx"][2] == "scanner_darvas_2026-09-11.xlsx")

    # Stand
    s = stand_saetze({**stand, "universum": 6612, "zeilen": 6500,
                      "quellen": {"kurse": {"aktuell": 6480}, "analysten": {"mit_stand": 950}}},
                     jetzt=datetime(2026, 9, 14, 20, 0, tzinfo=timezone.utc))
    p("Stand: Handelstag, Bauzeit in Wiener Zeit, Abdeckung der Analysten",
      s[0] == "Stand der Daten: Schlusskurse vom Freitag, 11.09.2026, gebaut am 14.09.2026 um 06:35 Uhr Wiener Zeit."
      and any("950 von 6.500" in x for x in s), " | ".join(s))
    s2 = stand_saetze({"handelstag": "2026-09-10"}, jetzt=datetime(2026, 9, 11, 22, 0, tzinfo=timezone.utc))
    p("Stand: aeltere Tabelle nach Handelsschluss wird benannt", any("nach dem Nachtscan" in x for x in s2), " | ".join(s2))
    s3 = stand_saetze({"handelstag": "2026-09-11"}, jetzt=datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc),
                      analysten_da=False)
    p("Stand: vor Handelsschluss ist der Freitag aktuell, fehlende Analystendaten benannt",
      not any("nach dem Nachtscan" in x for x in s3) and any("DATEN_LESE_TOKEN" in x for x in s3), " | ".join(s3))

    # Texte: kein langer Strich, keine Bildzeichen
    texte = [f.titel for f in FELDER] + [f.erklaerung for f in FELDER] + [f.wahl_titel for f in FELDER]
    texte += [w[1] for f in FELDER for w in f.wahl] + [strategie_text(k) for k, _n in AUSWAHL]
    texte += [n for _k, n in AUSWAHL] + grenzen_saetze() + [handelbar_text(), langweile_text()]
    texte += [t for _k, t, _p, _l in TERMIN_TEILE] + list(LAGE_TEXT.values()) + [x[1] for x in FORMATE]
    texte += [x[1] for x in LAGE] + [x[1] for x in UMFANG] + list(SEKTOREN.values()) + [g for _k, g in GRUPPEN]
    lang = [t for t in texte if chr(0x2013) in t or chr(0x2014) in t]
    p("Kein langer Strich in Beschriftungen und Erklaerungen", not lang, "; ".join(lang[:3]))
    bild = [t for t in texte if nachschlagen.bildzeichen_in(t)]
    p("Keine Bildzeichen in Beschriftungen und Erklaerungen", not bild, "; ".join(bild[:3]))
    p("Beschriftung der Grenzfelder nennt Zeitraum und Einheit",
      FELD["hoch"].eingabe_titel("max", {"wahl": "1j"}) == "Abstand zum Jahreshoch höchstens, in Prozent darunter"
      and FELD["tief"].eingabe_titel("min", {"wahl": "3m"}) == "Abstand zum Quartalstief mindestens, in Prozent darüber"
      and FELD["marktkap"].eingabe_titel("min") == "Marktkapitalisierung mindestens, in Milliarden Dollar"
      and FELD["rs"].eingabe_titel("min") == "RS gegen den ganzen US-Markt mindestens")
    p("Jedes Feld hat Titel, Gruppe und Erklaerung",
      all(f.titel and f.erklaerung and f.gruppe in dict(GRUPPEN) for f in FELDER) and len(FELD) == len(FELDER))

    print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles bestanden.")
    return 1 if fehler else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Scanner-Ansicht der Heliot-App")
    ap.add_argument("--selbsttest", action="store_true")
    args = ap.parse_args()
    if args.selbsttest:
        return selbsttest()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
