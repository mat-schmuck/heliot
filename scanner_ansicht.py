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

JEDE KENNZAHL ALS SPANNE (Gerhard, 15.09.2026): Von und Bis, ein leeres Ende
heisst offen. Das gilt fuer jede gebaute Kennzahl, auch fuer die technischen
und fundamentalen aus Nachtscan und Fundament, die scanner_daten.py mit
Vorsilbe in die Nachttabelle legt (tk_, rl_, ib_, fu_).

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


# Gerhard, 15.09.2026, Nachfrage N8: "Die ANZAHL DER AKTIEN muss neben dem
# Rang stehen, fest in der Anzeige, nicht als Beigabe." Zu jedem Rangfeld die
# Spalte mit der Zahl der Aktien, aus denen dieser Rang gerechnet ist.
RANG_TITEL = {"gruppe_rang": "gruppe_titel", "gruppe_rang_3w": "gruppe_titel_3w", "gruppe_rang_6w": "gruppe_titel_6w"}


def _aktien(n):
    return f"{int(n)} {'Aktie' if int(n) == 1 else 'Aktien'}"


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
    # Ohne Strategie steht kein Text da (Gerhard, 15.09.2026: "Den Erklaertext
    # zum Scanner bitte entfernen, den brauche ich nicht").
    texte = {
        "": "",
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
# JEDE KENNZAHL ALS SPANNE (Gerhard, 15.09.2026, Auftrag 1): "Wenn ich keine
# fertige Strategie auswaehle, will ich jede Kennzahl selbst einstellen
# koennen, und zwar als Spanne mit Von und Bis ... Das obere Ende muss also
# leer bleiben duerfen und bedeutet dann nach oben offen. Dasselbe gilt fuer
# das untere Ende. Das soll fuer alle Kennzahlen gelten, die wir bauen." Jede
# Kennzahl ist deshalb ein eigenes Feld mit Von und Bis. Auch die Zeitraeume
# von Hoch, Tief, Volatilitaet und Wertentwicklung stehen je fuer sich, damit
# sich etwa der Abstand zum Jahreshoch und zum Allzeithoch zugleich eingrenzen
# laesst. Die frueheren Stufenwahlen (Konsens, geschlagene Schaetzungen,
# groesstes Volumen) sind Spannen auf ihre Zahl; die Lagewahl bei den
# Durchschnitten ist eine Spanne ab oder bis null. Nur Bedingungen ohne Zahl
# (Red to Green, neues Hoch, RS-Linie auf dem Hoch, Momentum Burst, Episodic
# Pivot) bleiben Kontrollfelder, die erfuellt sein muessen. Der Selbsttest
# prueft, dass jede Kennzahl der Nachttabelle (scanner_daten.KENNZAHL_SPALTEN)
# ein Feld hat.

GRUPPEN = (("wachstum", "Wachstum von Umsatz und Gewinn"),
           ("margen", "Margen, Renditen und Cashflow"),
           ("groesse", "Kurs, Größe und Aktienzahl"),
           ("volumen", "Volumen"),
           ("tag", "Letzter Handelstag"),
           ("volatilitaet", "Volatilität und Schwankung"),
           ("durchschnitte", "Gleitende Durchschnitte und Trend"),
           ("hochtief", "Abstand von Hoch und Tief"),
           ("entwicklung", "Wertentwicklung und Momentum"),
           ("rs", "Relative Stärke"),
           ("ratings", "Ratings"),
           ("bilanz", "Bilanz und Sicherheit"),
           ("bewertung", "Bewertung"),
           ("analysten", "Analysten und Konsens"),
           ("revisionen", "Revisionen und Einstufungen"),
           ("short", "Leerverkäufe"),
           ("gruppe", "Branchengruppe"))

HOCH_TIEF = (("1t", "den letzten Handelstag", "Tageshoch", "Tagestief"),
             ("1w", "die letzten 5 Handelstage", "Wochenhoch", "Wochentief"),
             ("1m", "die letzten 21 Handelstage", "Monatshoch", "Monatstief"),
             ("3m", "die letzten 63 Handelstage", "Quartalshoch", "Quartalstief"),
             ("6m", "die letzten 126 Handelstage", "Halbjahreshoch", "Halbjahrestief"),
             ("1j", "52 Wochen", "Jahreshoch", "Jahrestief"),
             ("3j", "drei Jahre", "Dreijahreshoch", "Dreijahrestief"),
             ("allzeit", "die ganze Kurshistorie", "Allzeithoch", "Allzeittief"))

# Yahoos Namen der Perioden; das laufende Quartal ist das Quartal der naechsten
# Meldung und kann schon vorbei sein (siehe nachschlagen._periode_kopf).
PERIODEN_REV = (("0q", "laufendes Quartal"), ("1q", "nächstes Quartal"), ("0y", "laufendes Geschäftsjahr"),
                ("1y", "nächstes Geschäftsjahr"))
_FEHLT = object()


def _anteil(zaehler, nenner, basis_positiv=True):
    """Rechnung fuer Felder: zaehler geteilt durch nenner, minus 1, mal 100;
    bei basis_positiv nur mit positivem Nenner."""
    def rechnung(df):
        z, n = _zahlen(df, zaehler), _zahlen(df, nenner)
        if basis_positiv:
            n = n.where(n > 0)
        return (z / n - 1.0) * 100.0
    return rechnung


class Feld:
    """Ein Merkmal aus Teil 2.

    art "bereich": Von und Bis, leer heisst offen; angehakt ohne Grenze zeigt
        das Feld nur seinen Wert;
    art "ja": angehakt heisst, die Bedingung muss erfuellt sein.
    rechnung: statt einer Spalte eine Rechnung aus der Tabelle (df -> Series),
        quellen nennt die Spalten, aus denen sie rechnet;
    bezug: bei Hoch und Tief der Name des Hochs oder Tiefs;
    linie: bei Abstaenden zu einem Durchschnitt dessen Name."""

    def __init__(self, schluessel, gruppe, titel, art="bereich", spalte=None, einheit="Prozent", erklaerung="",
                 stellen=1, faktor=1.0, vorzeichen=False, signed=False, analysten=False, rechnung=None, quellen=(),
                 bezug="", linie=""):
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
        self.analysten = analysten
        self.rechnung = rechnung
        self.quellen = tuple(quellen)
        self.bezug = bezug
        self.linie = linie

    # --- Werte ---------------------------------------------------------------
    def werte(self, df, fe=None):
        """Die Werte in der Einheit der Eingabe, als Gleitkommazahlen."""
        if self.rechnung is not None:
            v = pd.to_numeric(self.rechnung(df), errors="coerce").astype("float64") * self.faktor
        elif self.spalte:
            v = _zahlen(df, self.spalte) * self.faktor
        else:
            v = pd.Series(np.nan, index=df.index, dtype="float64")
        if self.schluessel == "rs" and (fe or {}).get("vorlaeufig"):
            v = v.fillna(_zahlen(df, "rs_vorlaeufig"))
        v = v.where(np.isfinite(v))
        return -v if self.vorzeichen else v

    def wert(self, r, fe=None):
        """Der Wert einer Zeile (dict) in der Einheit der Eingabe, oder None."""
        return _num(self.werte(pd.DataFrame([r]), fe).iloc[0])

    # --- Filter --------------------------------------------------------------
    def grenzen(self, fe):
        """(Von, Bis, [Fehler]) aus der Einstellung. Leer heisst offen; eine
        unlesbare Grenze wirkt nicht, ebenso eine Spanne mit Von ueber Bis."""
        fe = fe or {}
        fehler = []
        von, f1 = zahl_lesen(fe.get("min"))
        bis, f2 = zahl_lesen(fe.get("max"))
        if f1:
            fehler.append(f"{self.titel}, von: {f1}; diese Grenze wirkt deshalb nicht.")
        if f2:
            fehler.append(f"{self.titel}, bis: {f2}; diese Grenze wirkt deshalb nicht.")
        if von is not None and bis is not None and von > bis + EPS:
            fehler.append(f"{self.titel}: Von {zahl_eingabe(von)} liegt über Bis {zahl_eingabe(bis)}; "
                          "diese Spanne wirkt deshalb nicht.")
            von = bis = None
        return von, bis, fehler

    def maske(self, df, fe):
        """(Maske oder None, [Fehler]); None heisst: dieses Feld filtert nicht."""
        fe = fe or {}
        if self.art == "ja":
            return _wahr(_sp(df, self.spalte)), []
        von, bis, fehler = self.grenzen(fe)
        if von is None and bis is None:
            return None, fehler
        v = self.werte(df, fe)
        m = pd.Series(True, index=df.index)
        if von is not None:
            m &= v >= von - EPS
        if bis is not None:
            m &= v <= bis + EPS
        return m.fillna(False).astype(bool), fehler

    def filtert(self, fe):
        """Traegt die Einstellung eine wirksame Grenze oder ist es eine Bedingung?"""
        if self.art == "ja":
            return True
        von, bis, _f = self.grenzen(fe)
        return von is not None or bis is not None

    # --- Texte ---------------------------------------------------------------
    def eingabe_titel(self, teil, fe=None):
        """Beschriftung eines Grenzfelds: Von oder Bis, mit der Einheit."""
        wort = "von" if teil == "min" else "bis"
        return f"{self.titel} {wort}" + (f", in {self.einheit}" if self.einheit else "")

    def eingabe_hinweis(self, teil):
        """Platzhalter eines leeren Grenzfelds."""
        return "leer heißt nach unten offen" if teil == "min" else "leer heißt nach oben offen"

    def _wert_text(self, v):
        if v is None:
            return "nicht berechenbar" if (self.signed or self.gruppe == "wachstum") else "unbekannt"
        text = mit_vorzeichen(v, self.stellen) if self.signed else zahl(v, self.stellen)
        return text + (f" {self.einheit}" if self.einheit else "")

    def satz(self, r, fe=None, analysten_da=True, v=_FEHLT):
        """Das Merkmal einer Aktie (Zeile als dict) als Satzteil fuer die Liste;
        v ist der schon gerechnete Wert, sonst wird er aus der Zeile gerechnet."""
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
        if s in RANG_TITEL:
            # Nachfragen N8 und N9: der Rang nie ohne die Zahl seiner Aktien;
            # der Gruppenname steht dabei, auch Branche unbekannt.
            g = r.get("gruppe") if isinstance(r.get("gruppe"), str) and r.get("gruppe") else None
            rang, anzahl = _num(r.get(self.spalte)), _num(r.get(RANG_TITEL[s]))
            if rang is None:
                return f"{self.titel} unbekannt" + (f", {g}" if g else "")
            von = _num(r.get("gruppen_zahl")) if s == "gruppe_rang" else None
            return (f"{self.titel} {int(rang)}" + (f" von {int(von)}" if von else "") + (f", {g}" if g else "")
                    + (f", aus {_aktien(anzahl)} gerechnet" if anzahl is not None else ""))
        if v is _FEHLT:
            v = self.wert(r, fe)
        else:
            v = _num(v)
        if self.bezug:
            if v is None:
                return f"Abstand zum {self.bezug} unbekannt"
            return f"{zahl(v, 1)} Prozent {'unter dem' if self.vorzeichen else 'über dem'} {self.bezug}"
        if self.linie:
            if v is None:
                return f"{self.linie} unbekannt"
            if round(v, 2) == 0:
                return f"Kurs auf der {self.linie}"
            return f"Kurs {zahl(abs(v), 2)} Prozent {'über' if v > 0 else 'unter'} der {self.linie}"
        if s == "rs":
            if v is not None:
                vorl = _num(r.get("rs")) is None
                return f"RS {int(round(v))}" + (" vorläufig" if vorl else "")
            vl = _num(r.get("rs_vorlaeufig"))
            return f"kein RS, vorläufiges RS {int(round(vl))}" if vl is not None else "RS unbekannt"
        for kennung, gegen in (("rs_linie_abst", "SPY"), ("rs_linie_qqq_abst", "QQQ")):
            if s == kennung:
                return (f"RS-Linie gegen {gegen} {zahl(v, 1)} Prozent unter dem 52-Wochen-Hoch" if v is not None
                        else f"Abstand der RS-Linie gegen {gegen} unbekannt")
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
        von, bis, _f = self.grenzen(fe)
        einheit = f" {self.einheit}" if self.einheit else ""
        if von is not None and bis is not None:
            teil = f"von {zahl_eingabe(von)} bis {zahl_eingabe(bis)}{einheit}"
        elif von is not None:
            teil = f"ab {zahl_eingabe(von)}{einheit}, nach oben offen"
        elif bis is not None:
            teil = f"bis {zahl_eingabe(bis)}{einheit}, nach unten offen"
        else:
            teil = "angezeigt"
        return f"{self.titel} {teil}" + (", mit vorläufigem RS" if self.schluessel == "rs" and fe.get("vorlaeufig") else "")

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
            return [("Analystenkonsens", _sp(df, "konsens")), ("Analystenkonsens als Zahl", _zahlen(df, "konsens_wert")),
                    ("Kaufempfehlungen", _zahlen(df, "analysten_kaufen")), ("Halten", _zahlen(df, "analysten_halten")),
                    ("Verkaufsempfehlungen", _zahlen(df, "analysten_verkaufen"))]
        if s == "beat":
            return [("Quartale über der Schätzung", _zahlen(df, "schaetzung_geschlagen")),
                    ("Quartale mit Schätzung", _zahlen(df, "quartale_mit_schaetzung"))]
        if s == "volmax":
            return [("Größtes Volumen jemals, Stück", _zahlen(df, "volumen_max")),
                    ("Größtes Volumen jemals, Datum", _sp(df, "volumen_max_datum")),
                    ("Größtes Volumen jemals, vor Handelstagen", _zahlen(df, "volumen_max_tage_her"))]
        werte = self.werte(df, fe).round(self.stellen)
        if s in RANG_TITEL:
            return [(self.titel, werte), ("Branchengruppe", _sp(df, "gruppe")),
                    (f"Aktien zum {self.titel}", _zahlen(df, RANG_TITEL[s]))]
        if self.bezug:
            return [(f"Prozent {'unter dem' if self.vorzeichen else 'über dem'} {self.bezug}", werte)]
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
    tech = ZENTRAL["technik"]
    fenster_short = int(sd.ks.KS["fenster_tage"])
    nur_dollar = " Nur für Firmen, die in Dollar berichten."
    nur_inland = " Nur für inländische Firmen mit Dollarzahlen."
    felder = [
        # Wachstum von Umsatz und Gewinn
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
        F("umsatz_cagr3", "wachstum", "Umsatzwachstum pro Jahr über drei Jahre", spalte="fu_umsatz_cagr3", signed=True,
          erklaerung="Durchschnittliches jährliches Wachstum des Umsatzes über die letzten drei Geschäftsjahre, "
                     "CAGR, aus dem SEC-Fundament."),
        F("umsatz_cagr5", "wachstum", "Umsatzwachstum pro Jahr über fünf Jahre", spalte="fu_umsatz_cagr5", signed=True,
          erklaerung="Durchschnittliches jährliches Wachstum des Umsatzes über die letzten fünf Geschäftsjahre, CAGR."),
        F("eps_cagr3", "wachstum", "EPS-Wachstum pro Jahr über drei Jahre", spalte="fu_eps_cagr3", signed=True,
          erklaerung="Durchschnittliches jährliches Wachstum des verwässerten Gewinns je Aktie über die letzten drei "
                     "Geschäftsjahre, CAGR."),
        F("eps_stabilitaet", "wachstum", "EPS-Stabilität", spalte="fu_eps_stabilitaet", einheit="", stellen=0,
          erklaerung="Wie gleichmäßig der Gewinn je Aktie über die Quartale verläuft, Näherung nach IBD-Art: 1 heißt "
                     "gleichmäßig, 99 sprunghaft."),
        F("rule40", "wachstum", "Rule of 40", spalte="fu_rule40", einheit="", signed=True,
          erklaerung="Umsatzwachstum der letzten vier Quartale in Prozent plus FCF-Marge in Prozent; ab 40 erfüllt, "
                     "gedacht für Software."),
        # Margen, Renditen und Cashflow
        F("marge", "margen", "Bruttomarge", spalte="bruttomarge_pct",
          erklaerung="Bruttogewinn in Prozent des Umsatzes im jüngsten Quartal. Banken, Versicherer und "
                     "Immobilienfirmen weisen keine aus."),
        F("marge_q", "margen", "Bruttomarge q/q", spalte="bruttomarge_q_vj_pp", einheit="Prozentpunkte", signed=True,
          erklaerung="Veränderung der Bruttomarge des jüngsten Quartals gegen das Vorjahresquartal."),
        F("marge_j", "margen", "Bruttomarge y/y", spalte="bruttomarge_ttm_pp", einheit="Prozentpunkte", signed=True,
          erklaerung="Bruttomarge der letzten vier Quartale gegen die der vier Quartale ein Jahr davor."),
        F("marge_s", "margen", "Bruttomarge sequenziell", spalte="bruttomarge_seq_pp", einheit="Prozentpunkte",
          signed=True, erklaerung="Bruttomarge des jüngsten Quartals gegen die des Quartals davor."),
        F("marge_op_q", "margen", "Operative Marge im Quartal", spalte="fu_marge_operativ_q", faktor=100.0, signed=True,
          erklaerung="Operatives Ergebnis in Prozent des Umsatzes im jüngsten Quartal."),
        F("marge_vst_q", "margen", "Vorsteuermarge im Quartal", spalte="fu_marge_vorsteuer_q", faktor=100.0, signed=True,
          erklaerung="Ergebnis vor Steuern in Prozent des Umsatzes im jüngsten Quartal."),
        F("marge_netto_q", "margen", "Nettomarge im Quartal", spalte="fu_marge_netto_q", faktor=100.0, signed=True,
          erklaerung="Nettogewinn in Prozent des Umsatzes im jüngsten Quartal."),
        F("marge_brutto_fy", "margen", "Bruttomarge im Geschäftsjahr", spalte="fu_marge_brutto_fy", faktor=100.0,
          signed=True, erklaerung="Bruttogewinn in Prozent des Umsatzes im jüngsten Geschäftsjahr."),
        F("marge_op_fy", "margen", "Operative Marge im Geschäftsjahr", spalte="fu_marge_operativ_fy", faktor=100.0,
          signed=True, erklaerung="Operatives Ergebnis in Prozent des Umsatzes im jüngsten Geschäftsjahr."),
        F("marge_vst_fy", "margen", "Vorsteuermarge im Geschäftsjahr", spalte="fu_marge_vorsteuer_fy", faktor=100.0,
          signed=True, erklaerung="Ergebnis vor Steuern in Prozent des Umsatzes im jüngsten Geschäftsjahr."),
        F("marge_netto_fy", "margen", "Nettomarge im Geschäftsjahr", spalte="fu_marge_netto_fy", faktor=100.0,
          signed=True, erklaerung="Nettogewinn in Prozent des Umsatzes im jüngsten Geschäftsjahr."),
        F("roe", "margen", "Eigenkapitalrendite, ROE", spalte="fu_roe", faktor=100.0, signed=True,
          erklaerung="Nettogewinn des Geschäftsjahres in Prozent des Eigenkapitals, wie im SMR-Rating."),
        F("roa", "margen", "Rendite auf das Vermögen, ROA", spalte="fu_roa", faktor=100.0, signed=True,
          erklaerung="Nettogewinn des Geschäftsjahres in Prozent der Bilanzsumme."),
        F("roic", "margen", "Rendite auf das eingesetzte Kapital, ROIC", spalte="fu_roic", faktor=100.0, signed=True,
          erklaerung="Operatives Ergebnis des Geschäftsjahres nach Steuern in Prozent des eingesetzten Kapitals, "
                     "mit dem Steuersatz des Jahres."),
        F("steuersatz", "margen", "Steuersatz", spalte="fu_steuersatz", faktor=100.0,
          erklaerung="Steuern in Prozent des Ergebnisses vor Steuern im Geschäftsjahr; bei Verlust null."),
        F("umsatz_12m", "margen", "Umsatz der letzten zwölf Monate", spalte="fu_umsatz_12m", einheit="Millionen Dollar",
          faktor=1e-6, erklaerung="Umsatz der letzten vier Quartale, sonst des jüngsten Geschäftsjahres." + nur_dollar),
        F("fcf", "margen", "Free Cashflow", spalte="fu_fcf", einheit="Millionen Dollar", faktor=1e-6, signed=True,
          erklaerung="Free Cashflow über die letzten vier Quartale, sonst im jüngsten Geschäftsjahr." + nur_dollar),
        F("fcf_marge", "margen", "FCF-Marge", spalte="fu_fcf_marge", faktor=100.0, signed=True,
          erklaerung="Free Cashflow in Prozent des Umsatzes."),
        F("cash_conversion", "margen", "Cash Conversion", spalte="fu_cash_conversion", einheit="", stellen=2,
          signed=True, erklaerung="Operativer Cashflow geteilt durch den Nettogewinn; 1 heißt, der Gewinn kommt "
                                  "vollständig als Geld herein."),
        F("ausschuettung", "margen", "Ausschüttungsquote", spalte="fu_ausschuettung", faktor=100.0,
          erklaerung="Gezahlte Dividenden in Prozent des Nettogewinns."),
        F("sbc", "margen", "Aktienbasierte Vergütung", spalte="fu_sbc_umsatz", faktor=100.0, stellen=2,
          erklaerung="Aktienbasierte Vergütung in Prozent des Umsatzes."),
        F("ffo", "margen", "FFO nach NAREIT", spalte="fu_ffo", einheit="Millionen Dollar", faktor=1e-6, signed=True,
          erklaerung="Funds from Operations über zwölf Monate, die Gewinnkennzahl der Immobilienfirmen." + nur_dollar),
        F("ffo_je_aktie", "margen", "FFO je Aktie", spalte="fu_ffo_je_aktie", einheit="Dollar", stellen=2, signed=True,
          erklaerung="FFO nach NAREIT je Aktie." + nur_dollar),
        # Kurs, Groesse und Aktienzahl
        F("kurs", "groesse", "Kurs", spalte="kurs", einheit="Dollar", stellen=2,
          erklaerung="Schlusskurs des letzten Handelstags."),
        F("marktkap", "groesse", "Marktkapitalisierung", spalte="marktkap_mrd", einheit="Milliarden Dollar", stellen=2,
          erklaerung="In Milliarden Dollar: 0,3 heißt 300 Millionen, 1000 heißt eine Billion. Quelle Nasdaq."),
        F("aktien", "groesse", "Ausstehende Aktien", spalte="aktien_ausstehend", einheit="Millionen Stück",
          faktor=1e-6, stellen=1, erklaerung="Zahl der ausstehenden Aktien aus dem jüngsten SEC-Bericht."),
        F("aktien_1j", "groesse", "Veränderung der Aktienzahl über ein Jahr", spalte="fu_aktien_1j_pct", signed=True,
          erklaerung="Verwässerte Aktienzahl gegenüber einem Jahr zuvor; ein Plus heißt Verwässerung, ein Minus "
                     "Rückkäufe."),
        F("aktien_3j", "groesse", "Veränderung der Aktienzahl über drei Jahre", spalte="fu_aktien_3j_pct", signed=True,
          erklaerung="Verwässerte Aktienzahl gegenüber drei Jahren zuvor."),
        F("streubesitz", "groesse", "Streubesitz", spalte="fu_streubesitz_wert", einheit="Millionen Dollar",
          faktor=1e-6, erklaerung="Marktwert der Aktien im Streubesitz laut Deckblatt des Jahresberichts, zum "
                                  "Stichtag dort; nur Angaben in Dollar."),
        F("historie", "groesse", "Kurshistorie", spalte="historie_gesamt_tage", einheit="Handelstage", stellen=0,
          erklaerung="Wie viele Handelstage mit Kursen die Aktie hat; frische Börsengänge haben wenige. 252 "
                     "Handelstage sind rund ein Jahr."),
        # Volumen
        F("volumen", "volumen", "Durchschnittliches Tagesvolumen, 50 Tage", spalte="volumen_50", einheit="Stück",
          stellen=0, erklaerung="Gehandelte Aktien je Tag im Schnitt der letzten 50 Handelstage."),
        F("umsatz_dollar", "volumen", "Durchschnittlicher Tagesumsatz, 50 Tage", spalte="dollarvolumen_50",
          einheit="Millionen Dollar", faktor=1e-6, stellen=1,
          erklaerung="Kurs mal Volumen im Schnitt der letzten 50 Handelstage."),
        F("tag_volumen", "volumen", "Volumen am letzten Handelstag", spalte="volumen", einheit="Stück", stellen=0,
          erklaerung="Gehandelte Aktien am letzten Handelstag."),
        F("vol_faktor", "volumen", "Volumenfaktor zum 50-Tage-Schnitt", spalte="tk_vol_faktor", einheit="", stellen=2,
          erklaerung=f"Volumen des letzten Handelstags geteilt durch den Schnitt der {tech['volumen_schnitt_tage']} "
                     "Handelstage davor; 2 heißt doppelt so hoch."),
        F("vol63", "volumen", "Durchschnittsvolumen über drei Monate", spalte="tk_vol63", einheit="Stück", stellen=0,
          erklaerung="Gehandelte Aktien je Tag im Schnitt der letzten 63 Handelstage."),
        F("dv20", "volumen", "Dollarvolumen über 20 Tage", spalte="tk_dv20", einheit="Millionen Dollar", faktor=1e-6,
          erklaerung="Kurs mal Volumen im Schnitt der letzten 20 Handelstage."),
        F("vdu", "volumen", "Austrocknen des Volumens", spalte="vdu", einheit="", stellen=2,
          erklaerung="Volumen der letzten 10 Handelstage im Schnitt geteilt durch den Schnitt der 50 Handelstage "
                     "davor; unter 1 trocknet das Volumen aus."),
        F("vol_spitze", "volumen", "Volumenspitze der letzten 10 Tage", spalte="vol_spitze_10", einheit="", stellen=2,
          erklaerung="Das größte Tagesvolumen der letzten 10 Handelstage geteilt durch den Schnitt der 50 "
                     "Handelstage davor."),
        F("ud50", "volumen", "Up/Down-Volumen über 50 Tage", spalte="tk_ud50", einheit="", stellen=2,
          erklaerung=f"Volumen der Plus-Tage der letzten {tech['updown_tage']} Handelstage geteilt durch das Volumen "
                     "der Minus-Tage, nach IBD; über 1 überwiegt das Volumen an Plus-Tagen."),
        F("volmax", "volumen", "Größtes Volumen jemals, vor so vielen Handelstagen", spalte="volumen_max_tage_her",
          einheit="Handelstage", stellen=0,
          erklaerung="Wie viele Handelstage der Tag mit dem höchsten Volumen der ganzen Kurshistorie zurückliegt; 0 "
                     "heißt am letzten Handelstag. Liegt der Tag mehr als drei Jahre zurück, gibt es keinen Wert."),
        # Letzter Handelstag
        F("veraenderung", "tag", "Veränderung zum Vortag", spalte="veraenderung_pct", signed=True, stellen=2,
          erklaerung="Schlusskurs des letzten Handelstags gegen den Schlusskurs davor."),
        F("seit_open", "tag", "Veränderung seit der Eröffnung, Change from Open", spalte="seit_eroeffnung_pct",
          signed=True, stellen=2,
          erklaerung="Schlusskurs gegen den Eröffnungskurs des letzten Handelstags. Die Tabelle entsteht nachts, "
                     "während des Handels steht hier noch der Vortag."),
        F("rtg", "tag", "Red to Green", art="ja", spalte="red_to_green",
          erklaerung="Am letzten Handelstag unter dem Vortagesschluss eröffnet und darüber geschlossen."),
        F("spanne", "tag", "Tagesspanne", spalte="tagesspanne_pct", stellen=2,
          erklaerung="Spanne zwischen Tageshoch und Tagestief des letzten Handelstags in Prozent des Tagestiefs."),
        F("luecke", "tag", "Eröffnungslücke", spalte="tk_luecke", signed=True,
          erklaerung="Eröffnungskurs des letzten Handelstags gegen den Schlusskurs davor."),
        F("pivot", "tag", "Episodic Pivot", art="ja", spalte="tk_pivot",
          erklaerung=f"Eröffnungslücke von {zahl_eingabe(tech['pivot_luecke_pct'])} Prozent oder mehr am letzten "
                     "Handelstag."),
        F("burst", "tag", "Momentum Burst nach Stockbee", art="ja", spalte="tk_burst",
          erklaerung=f"Schluss mindestens {zahl_eingabe(tech['burst_pct'])} Prozent über dem Vortag, bei höherem "
                     f"Volumen als am Vortag und mindestens {nachschlagen.zahl(tech['burst_mindestvolumen'])} Stück."),
        F("schlusslage", "tag", "Schlusslage in der Tagesspanne", spalte="tk_schlusslage", stellen=0,
          erklaerung="Wo der Schlusskurs in der Tagesspanne liegt: 0 heißt am Tagestief, 100 am Tageshoch."),
        F("vortag", "tag", "Veränderung am Vortag", spalte="tk_vortag_pct", signed=True,
          erklaerung="Schlusskurs des vorletzten Handelstags gegen den Schlusskurs davor."),
        F("vortag_spanne", "tag", "Tagesspanne am Vortag", spalte="tk_vortag_spanne",
          erklaerung="Hoch geteilt durch Tief des vorletzten Handelstags, minus 1, in Prozent."),
        # Volatilitaet und Schwankung
        F("adr", "volatilitaet", "ADR nach Qullamaggie, 20 Tage", spalte="volatilitaet_20_pct", stellen=2,
          erklaerung="Mittlere Tagesspanne der letzten 20 Handelstage: je Tag Hoch geteilt durch Tief, davon das "
                     "Mittel, minus 1, in Prozent."),
        F("vola5", "volatilitaet", "Volatilität Woche wie bei Finviz, 5 Tage", spalte="volatilitaet_5_pct", stellen=2,
          erklaerung="Dieselbe Rechnung wie die ADR über die letzten 5 Handelstage."),
        F("vola21", "volatilitaet", "Volatilität Monat wie bei Finviz, 21 Tage", spalte="tk_vola21", stellen=2,
          erklaerung="Dieselbe Rechnung wie die ADR über die letzten 21 Handelstage."),
        F("atr", "volatilitaet", "ATR 14 in Dollar", spalte="tk_atr14", einheit="Dollar", stellen=2,
          erklaerung="Mittlere wahre Tagesspanne über 14 Tage nach Wilder, in Dollar."),
        F("atr_pct", "volatilitaet", "ATR 14 in Prozent des Kurses", stellen=2, quellen=("tk_atr14", "kurs"),
          rechnung=lambda df: _zahlen(df, "tk_atr14") / _zahlen(df, "kurs").where(_zahlen(df, "kurs") > 0) * 100.0,
          erklaerung="Die ATR 14 geteilt durch den Schlusskurs."),
        F("atr_verh", "volatilitaet", "ATR der letzten 5 Tage zur ATR der letzten 50", spalte="atr_verhaeltnis",
          einheit="", stellen=2,
          erklaerung="Mittlere wahre Tagesspanne der letzten 5 Handelstage geteilt durch die der letzten 50; unter 1 "
                     "wird die Aktie ruhiger."),
        F("beta", "volatilitaet", f"Beta gegen SPY über {int(tech['beta_tage'])} Handelstage", spalte="tk_beta",
          einheit="", stellen=2, signed=True,
          erklaerung=f"Schwankung gegenüber dem S&P-500-ETF SPY über die Tagesrenditen der letzten "
                     f"{int(tech['beta_tage'])} Handelstage; 1 heißt so beweglich wie der Markt. Finviz rechnet "
                     f"sein Beta über 60 Monate, die Zahlen weichen deshalb voneinander ab."),
        F("jahresspanne", "volatilitaet", "Jahresspanne", spalte="jahresspanne", einheit="", stellen=2,
          erklaerung="Jahreshoch geteilt durch das Jahrestief der letzten 252 Handelstage; 2 heißt, das Hoch liegt "
                     "doppelt so hoch wie das Tief."),
        # Gleitende Durchschnitte und Trend
        F("ema21", "durchschnitte", "Abstand zur EMA 21", spalte="abst_ema21_pct", signed=True, stellen=2,
          linie="EMA 21", erklaerung="Schlusskurs gegen den exponentiellen Durchschnitt der letzten 21 Tage; "
                                    "negativ heißt darunter; von 0 an liegt der Kurs darüber."),
        F("ema50", "durchschnitte", "Abstand zur EMA 50", spalte="abst_ema50_pct", signed=True, stellen=2,
          linie="EMA 50", erklaerung="Schlusskurs gegen den exponentiellen Durchschnitt der letzten 50 Tage; "
                                    "negativ heißt darunter; von 0 an liegt der Kurs darüber."),
        F("ema200", "durchschnitte", "Abstand zur EMA 200", spalte="abst_ema200_pct", signed=True, stellen=2,
          linie="EMA 200", erklaerung="Schlusskurs gegen den exponentiellen Durchschnitt der letzten 200 Tage; "
                                     "negativ heißt darunter; von 0 an liegt der Kurs darüber."),
        F("sma20", "durchschnitte", "Abstand zur SMA 20", spalte="tk_sma20_abst", signed=True, linie="SMA 20",
          erklaerung="Schlusskurs gegen den einfachen Durchschnitt der letzten 20 Tage; negativ heißt darunter; von 0 an liegt der Kurs darüber."),
        F("sma50", "durchschnitte", "Abstand zur SMA 50", spalte="tk_sma50_abst", signed=True, linie="SMA 50",
          erklaerung="Schlusskurs gegen den einfachen Durchschnitt der letzten 50 Tage; negativ heißt darunter; von 0 an liegt der Kurs darüber."),
        F("sma200", "durchschnitte", "Abstand zur SMA 200", spalte="tk_sma200_abst", signed=True, linie="SMA 200",
          erklaerung="Schlusskurs gegen den einfachen Durchschnitt der letzten 200 Tage; negativ heißt darunter; von 0 an liegt der Kurs darüber."),
        F("ma200_steigt", "durchschnitte", "Anstieg der SMA 200 in Folge", spalte="ma200_steigt_tage",
          einheit="Handelstage", stellen=0,
          erklaerung="Wie viele Handelstage in Folge der einfache 200-Tage-Durchschnitt zuletzt gestiegen ist; 0 "
                     "heißt, er ist am letzten Handelstag nicht gestiegen."),
        F("weinstein", "durchschnitte", "Weinstein-Stufe", spalte="tk_stufe", einheit="", stellen=0,
          erklaerung="Stufe nach Stan Weinstein aus der 30-Wochen-Linie und dem Kurs: 1 Boden, 2 Aufwärtstrend, "
                     "die Linie steigt und die letzten zwei Wochenschlüsse liegen darüber, 3 Top, 4 Abwärtstrend, "
                     "spiegelbildlich; 0 heißt nicht eindeutig. Der Mansfield RS entscheidet nicht mit, er steht "
                     "als eigenes Feld daneben."),
        F("linie30", "durchschnitte", "Abstand zur 30-Wochen-Linie", spalte="tk_linie_abst", signed=True,
          linie="30-Wochen-Linie",
          erklaerung="Schlusskurs gegen den Durchschnitt der letzten 30 Wochen; negativ heißt darunter; von 0 an liegt der Kurs darüber."),
        F("linie30_steig", "durchschnitte", "Veränderung der 30-Wochen-Linie in vier Wochen", spalte="tk_linie_steig",
          signed=True, stellen=2,
          erklaerung="Wie stark die 30-Wochen-Linie in den letzten vier Wochen gestiegen oder gefallen ist."),
    ]
    # Abstand von Hoch und Tief, je Zeitraum ein Feld
    for h, zeitraum, hoch, _tief in HOCH_TIEF:
        felder.append(F(f"hoch_{h}", "hochtief", f"Abstand zum {hoch}", spalte=f"abst_hoch_{h}_pct", vorzeichen=True,
                        einheit="Prozent unter dem Hoch", bezug=hoch,
                        erklaerung=f"Wie weit der Schlusskurs unter dem {hoch} liegt, dem höchsten Kurs über "
                                   f"{zeitraum}; 0 heißt am Hoch."))
    felder.append(F("hoch50", "hochtief", "Abstand zum 50-Tage-Hoch", spalte="tk_hoch50_abst", vorzeichen=True,
                    einheit="Prozent unter dem Hoch", bezug="50-Tage-Hoch",
                    erklaerung="Wie weit der Schlusskurs unter dem Hoch der letzten 50 Handelstage liegt."))
    for h, zeitraum, _hoch, tief in HOCH_TIEF:
        felder.append(F(f"tief_{h}", "hochtief", f"Abstand zum {tief}", spalte=f"abst_tief_{h}_pct",
                        einheit="Prozent über dem Tief", bezug=tief,
                        erklaerung=f"Wie weit der Schlusskurs über dem {tief} liegt, dem tiefsten Kurs über "
                                   f"{zeitraum}."))
    felder += [
        F("tief50", "hochtief", "Abstand zum 50-Tage-Tief", spalte="tk_tief50_abst", einheit="Prozent über dem Tief",
          bezug="50-Tage-Tief", erklaerung="Wie weit der Schlusskurs über dem Tief der letzten 50 Handelstage liegt."),
        F("neu_52w", "hochtief", "Neues 52-Wochen-Hoch", art="ja", spalte="hoch_52w",
          erklaerung="Das Tageshoch des letzten Handelstags liegt über allen Hochs der 52 Wochen davor."),
        F("neu_ath", "hochtief", "Neues Allzeithoch", art="ja", spalte="hoch_allzeit",
          erklaerung="Am letzten Handelstag wurde das Hoch der ganzen Kurshistorie erreicht."),
        # Wertentwicklung und Momentum
        F("perf_1w", "entwicklung", "Wertentwicklung eine Woche", spalte="tk_perf_1w", signed=True,
          erklaerung="Schlusskurs gegen den Schluss vor 5 Handelstagen, wie bei Finviz."),
        F("perf_1m", "entwicklung", "Wertentwicklung ein Monat", spalte="tk_perf_1m", signed=True,
          erklaerung="Schlusskurs gegen den Schluss vor 21 Handelstagen, wie bei Finviz."),
        F("perf_3m", "entwicklung", "Wertentwicklung drei Monate", spalte="tk_perf_3m", signed=True,
          erklaerung="Schlusskurs gegen den Schluss vor 63 Handelstagen, wie bei Finviz."),
        F("perf_6m", "entwicklung", "Wertentwicklung sechs Monate", spalte="tk_perf_6m", signed=True,
          erklaerung="Schlusskurs gegen den Schluss vor 126 Handelstagen, wie bei Finviz."),
        F("perf_12m", "entwicklung", "Wertentwicklung zwölf Monate", spalte="tk_perf_12m", signed=True,
          erklaerung="Schlusskurs gegen den letzten Schluss am oder vor demselben Kalendertag ein Jahr früher, wie bei "
                     "Finviz."),
        F("perf_ytd", "entwicklung", "Wertentwicklung seit Jahresbeginn", spalte="tk_perf_ytd", signed=True,
          erklaerung="Schlusskurs gegen den letzten Schluss des Vorjahres."),
        F("rsi14", "entwicklung", "RSI 14", spalte="tk_rsi14", einheit="",
          erklaerung="Relative Strength Index über 14 Tage nach Wilder, von 0 bis 100; über 70 gilt als überkauft, "
                     "unter 30 als überverkauft."),
        F("rsi2", "entwicklung", "RSI 2", spalte="tk_rsi2", einheit="",
          erklaerung="Relative Strength Index über 2 Tage nach Wilder, von 0 bis 100; zeigt kurze Übertreibungen."),
        # Relative Staerke
        F("rs", "rs", "RS gegen den ganzen US-Markt", spalte="rs", einheit="", stellen=0,
          erklaerung="Relative Stärke von 1 bis 99 gegen alle Stammaktien des US-Markts; 90 heißt stärker als "
                     "90 Prozent. Junge Titel haben nur ein vorläufiges RS."),
        F("rs_1w", "rs", "RS-Veränderung über eine Woche", spalte="tk_rs_1w", einheit="Punkte", stellen=0, signed=True,
          erklaerung="RS heute minus RS vor einer Woche."),
        F("rs_4w", "rs", "RS-Veränderung über vier Wochen", spalte="tk_rs_4w", einheit="Punkte", stellen=0, signed=True,
          erklaerung="RS heute minus RS vor vier Wochen."),
        F("mrs", "rs", "Mansfield RS gegen SPY", spalte="tk_mrs", einheit="", signed=True,
          erklaerung="Relation von Kurs zu SPY, geteilt durch ihren 52-Wochen-Schnitt, minus 1, mal 100, nach "
                     "Weinstein; über null ist die Aktie stärker als der Markt."),
        F("mrs_vorher", "rs", "Mansfield RS vor vier Wochen", spalte="tk_mrs_vorher", einheit="", signed=True,
          erklaerung="Derselbe Wert vier Wochen früher; ist er kleiner als heute, steigt der Mansfield RS."),
        F("rs_linie", "rs", "RS-Linie gegen SPY auf 52-Wochen-Hoch", art="ja", spalte="rs_linie_hoch",
          erklaerung="Kurs geteilt durch den S&P-500-ETF SPY steht auf einem 52-Wochen-Hoch."),
        F("rs_linie_qqq", "rs", "RS-Linie gegen QQQ auf 52-Wochen-Hoch", art="ja", spalte="rs_linie_qqq_hoch",
          erklaerung="Kurs geteilt durch den Nasdaq-100-ETF QQQ steht auf einem 52-Wochen-Hoch."),
        F("rs_linie_abst", "rs", "Abstand der RS-Linie gegen SPY vom 52-Wochen-Hoch", spalte="rs_linie_abst_pct",
          vorzeichen=True, einheit="Prozent unter dem Hoch",
          erklaerung="Wie weit die RS-Linie gegen SPY unter ihrem 52-Wochen-Hoch steht; 0 heißt auf dem Hoch."),
        F("rs_linie_qqq_abst", "rs", "Abstand der RS-Linie gegen QQQ vom 52-Wochen-Hoch", spalte="rs_linie_qqq_abst_pct",
          vorzeichen=True, einheit="Prozent unter dem Hoch",
          erklaerung="Wie weit die RS-Linie gegen QQQ unter ihrem 52-Wochen-Hoch steht; 0 heißt auf dem Hoch."),
        F("rs_linie_1w", "rs", "Veränderung der RS-Linie gegen SPY in einer Woche", spalte="rl_linie_spy_1w",
          signed=True, stellen=2,
          erklaerung="Wie stark die RS-Linie gegen SPY in den letzten 5 Handelstagen gestiegen oder gefallen ist."),
        F("rs_linie_qqq_1w", "rs", "Veränderung der RS-Linie gegen QQQ in einer Woche", spalte="rl_linie_qqq_1w",
          signed=True, stellen=2,
          erklaerung="Wie stark die RS-Linie gegen QQQ in den letzten 5 Handelstagen gestiegen oder gefallen ist."),
        # Ratings
        F("eps_rating", "ratings", "EPS-Rating", spalte="ib_eps", einheit="", stellen=0,
          erklaerung="Rating des Gewinnwachstums von 1 bis 99 nach IBD-Art aus den amtlichen SEC-Zahlen; 99 ist das "
                     "beste."),
        F("smr", "ratings", "SMR-Rang", spalte="ib_smr_rang", einheit="", stellen=0,
          erklaerung="Rang aus Umsatzwachstum, Nettomarge, Vorsteuermarge und Eigenkapitalrendite von 1 bis 99; Note A "
                     "ab 80, B ab 60, C ab 40, D ab 20, darunter E."),
        F("ad", "ratings", "A/D-Rang", spalte="ib_ad_rang", einheit="", stellen=0,
          erklaerung="Rang von 1 bis 99 für Kauf- und Verkaufsdruck, Näherung aus der Schlusslage in der Tagesspanne "
                     f"und dem Volumen der letzten {tech['ad_tage']} Handelstage; Note A ab 80."),
        F("composite", "ratings", "Composite Rating", spalte="ib_composite", einheit="", stellen=0,
          erklaerung="Gesamtrang von 1 bis 99 aus EPS-Rating und RS doppelt gewichtet, dazu SMR, A/D und der Nähe "
                     "zum 52-Wochen-Hoch."),
        F("tt_count", "ratings", "Bedingungen des Trend Templates", spalte="tt_count", einheit="von 8", stellen=0,
          erklaerung="Wie viele der acht Bedingungen des Minervini Trend Templates erfüllt sind."),
        # Bilanz und Sicherheit
        F("schulden_ek", "bilanz", "Schulden zu Eigenkapital, Debt to Equity", spalte="schulden_zu_ek", einheit="",
          stellen=2, erklaerung="Kurz- und langfristige Finanzschulden geteilt durch das Eigenkapital; 0,5 heißt halb "
                                "so viele Schulden wie Eigenkapital. Aus der jüngsten SEC-Bilanz."),
        F("lt_schulden_ek", "bilanz", "Langfristige Schulden zu Eigenkapital", spalte="fu_lt_schulden_ek", einheit="",
          stellen=2, erklaerung="Langfristige Finanzschulden geteilt durch das Eigenkapital."),
        F("schulden_vermoegen", "bilanz", "Verschuldung im Verhältnis zum Vermögen", spalte="schulden_zu_vermoegen_pct",
          erklaerung="Finanzschulden in Prozent der Bilanzsumme."),
        F("ek_quote", "bilanz", "Eigenkapitalquote", spalte="ek_quote_pct",
          erklaerung="Eigenkapital in Prozent der Bilanzsumme."),
        F("fk_quote", "bilanz", "Fremdkapitalquote", spalte="fk_quote_pct",
          erklaerung="Alle Verbindlichkeiten in Prozent der Bilanzsumme."),
        F("current_ratio", "bilanz", "Current Ratio", spalte="fu_current_ratio", einheit="", stellen=2,
          erklaerung="Umlaufvermögen geteilt durch kurzfristige Verbindlichkeiten; über 1 decken die kurzfristigen "
                     "Mittel die kurzfristigen Schulden."),
        F("quick_ratio", "bilanz", "Quick Ratio", spalte="fu_quick_ratio", einheit="", stellen=2,
          erklaerung="Wie die Current Ratio, aber ohne Vorräte."),
        F("zinsdeckung", "bilanz", "Zinsdeckung", spalte="fu_zinsdeckung", einheit="", signed=True,
          erklaerung="Operatives Ergebnis der letzten vier Quartale geteilt durch die Zinsaufwendungen; 5 heißt, "
                     "die Zinsen sind fünfmal verdient."),
        F("schulden", "bilanz", "Finanzschulden", spalte="fu_schulden", einheit="Millionen Dollar", faktor=1e-6,
          erklaerung="Kurz- und langfristige Finanzschulden laut jüngster Bilanz." + nur_dollar),
        F("nettoschulden", "bilanz", "Nettoschulden", spalte="fu_nettoschulden", einheit="Millionen Dollar",
          faktor=1e-6, signed=True,
          erklaerung="Finanzschulden minus Kasse und kurzfristige Anlagen; negativ heißt Nettokasse." + nur_dollar),
        F("fscore", "bilanz", "Piotroski F-Score", spalte="fu_fscore", einheit="", stellen=0,
          erklaerung="Wie viele der neun Signale nach Piotroski erfüllt sind, aus Jahreswerten; nicht für Banken und "
                     "Versicherer."),
        F("altman_z", "bilanz", "Altman Z", spalte="fu_altman_z", einheit="", stellen=2, signed=True,
          erklaerung="Insolvenzmaß nach Altman für Industriefirmen: über 2,99 sichere Zone, 1,81 bis 2,99 Grauzone, "
                     "darunter Gefahrenzone." + nur_inland),
        F("kernkapital", "bilanz", "Kernkapitalquote", spalte="fu_kernkapitalquote", faktor=100.0, stellen=2,
          erklaerung="Nur Banken: Kernkapital in Prozent der risikogewichteten Aktiva."),
        F("risikovorsorge", "bilanz", "Risikovorsorge zu Krediten", spalte="fu_risikovorsorge_kredite", faktor=100.0,
          stellen=2, signed=True, erklaerung="Nur Banken: Risikovorsorge in Prozent der Kredite."),
        F("einlagen", "bilanz", "Einlagen gegenüber dem Vorjahr", spalte="fu_einlagen_vj_pct", signed=True,
          erklaerung="Nur Banken: Kundeneinlagen gegenüber dem Vorjahr."),
        # Bewertung
        F("kgv", "bewertung", "KGV", spalte="fu_kgv", einheit="",
          erklaerung="Marktkapitalisierung geteilt durch den Nettogewinn der letzten vier Quartale; nur bei Gewinn."
                     + nur_inland),
        F("kuv", "bewertung", "KUV", spalte="fu_kuv", einheit="", stellen=2,
          erklaerung="Marktkapitalisierung geteilt durch den Umsatz der letzten zwölf Monate." + nur_inland),
        F("kbv", "bewertung", "KBV", spalte="fu_kbv", einheit="", stellen=2,
          erklaerung="Marktkapitalisierung geteilt durch das Eigenkapital; nur bei positivem Eigenkapital." + nur_inland),
        F("ev", "bewertung", "Enterprise Value", spalte="fu_ev", einheit="Millionen Dollar", faktor=1e-6,
          erklaerung="Marktkapitalisierung plus Finanzschulden minus Kasse." + nur_inland),
        F("ev_ebitda", "bewertung", "EV zu EBITDA", spalte="fu_ev_ebitda", einheit="",
          erklaerung="Enterprise Value geteilt durch operatives Ergebnis plus Abschreibungen der letzten zwölf Monate."
                     + nur_inland),
        F("ev_umsatz", "bewertung", "EV zu Umsatz", spalte="fu_ev_umsatz", einheit="", stellen=2,
          erklaerung="Enterprise Value geteilt durch den Umsatz der letzten zwölf Monate." + nur_inland),
        F("peg", "bewertung", "PEG", spalte="fu_peg", einheit="", stellen=2,
          erklaerung="KGV geteilt durch das Wachstum des Gewinns je Aktie im letzten Geschäftsjahr in Prozent; nur "
                     "bei Gewinn und Wachstum." + nur_inland),
        F("p_ffo", "bewertung", "Kurs zu FFO", spalte="fu_p_ffo", einheit="",
          erklaerung="Nur Immobilienfirmen: Kurs geteilt durch FFO je Aktie."),
        F("fcf_rendite", "bewertung", "FCF-Rendite", spalte="fu_fcf_rendite", faktor=100.0, stellen=2, signed=True,
          erklaerung="Free Cashflow in Prozent der Marktkapitalisierung." + nur_inland),
        F("div_rendite", "bewertung", "Dividendenrendite", spalte="fu_div_rendite", faktor=100.0, stellen=2,
          erklaerung="Gezahlte Dividenden in Prozent der Marktkapitalisierung." + nur_inland),
        F("rueckkauf", "bewertung", "Aktienrückkäufe", spalte="fu_rueckkauf_mk", faktor=100.0, stellen=2,
          erklaerung="Aktienrückkäufe in Prozent der Marktkapitalisierung." + nur_inland),
        F("cash_je_aktie", "bewertung", "Cash je Aktie", spalte="fu_cash_je_aktie", einheit="Dollar", stellen=2,
          erklaerung="Kasse und kurzfristige Anlagen je Aktie." + nur_inland),
        F("nettokasse_je_aktie", "bewertung", "Nettokasse je Aktie", spalte="fu_nettokasse_je_aktie", einheit="Dollar",
          stellen=2, signed=True,
          erklaerung="Kasse und kurzfristige Anlagen minus Finanzschulden, je Aktie; negativ heißt Nettoschulden."
                     + nur_inland),
        F("buchwert_je_aktie", "bewertung", "Buchwert je Aktie", spalte="fu_buchwert_je_aktie", einheit="Dollar",
          stellen=2, signed=True, erklaerung="Eigenkapital je Aktie." + nur_inland),
        F("fcf_je_aktie", "bewertung", "Free Cashflow je Aktie", spalte="fu_fcf_je_aktie", einheit="Dollar", stellen=2,
          signed=True, erklaerung="Free Cashflow der letzten vier Quartale je Aktie." + nur_inland),
        # Analysten und Konsens
        F("konsens", "analysten", "Analystenkonsens", spalte="konsens_wert", einheit="", stellen=0, analysten=True,
          erklaerung="Die jüngste Empfehlung der Analysten laut Nasdaq als Zahl: 5 starker Kauf, 4 Kaufen, 3 Halten, "
                     "2 Verkaufen, 1 starker Verkauf."),
        F("analysten_anzahl", "analysten", "Zahl der Analysten", spalte="analysten_anzahl", einheit="", stellen=0,
          analysten=True, erklaerung="Wie viele Analysten laut Nasdaq eine Empfehlung abgeben."),
        F("kaufanteil", "analysten", "Anteil der Kaufempfehlungen", spalte="analysten_kauf_anteil_pct", analysten=True,
          erklaerung="Kaufempfehlungen in Prozent aller Empfehlungen."),
        F("kursziel", "analysten", "Kursziel über dem Kurs", spalte="kursziel_abst_pct", signed=True, analysten=True,
          erklaerung="Mittleres Kursziel der Analysten gegen den Schlusskurs; negativ heißt, das Ziel liegt darunter."),
        F("kursziel_tief", "analysten", "Niedrigstes Kursziel über dem Kurs", signed=True, analysten=True,
          rechnung=_anteil("kursziel_tief", "kurs"), quellen=("kursziel_tief", "kurs"),
          erklaerung="Das niedrigste Kursziel der Analysten gegen den Schlusskurs; negativ heißt, das Ziel liegt "
                     "darunter."),
        F("kursziel_hoch", "analysten", "Höchstes Kursziel über dem Kurs", signed=True, analysten=True,
          rechnung=_anteil("kursziel_hoch", "kurs"), quellen=("kursziel_hoch", "kurs"),
          erklaerung="Das höchste Kursziel der Analysten gegen den Schlusskurs."),
        F("fwd_kgv", "analysten", "Forward-KGV", spalte="konsens_fwd_kgv", einheit="", analysten=True,
          erklaerung="Schlusskurs geteilt durch den erwarteten Gewinn je Aktie des nächsten Geschäftsjahres laut "
                     "eingefrorenem Yahoo-Konsens."),
        F("kgv_0y", "analysten", "KGV auf das laufende Geschäftsjahr laut Konsens", spalte="konsens_kgv_0y", einheit="",
          analysten=True, erklaerung="Schlusskurs geteilt durch den erwarteten Gewinn je Aktie des laufenden "
                                     "Geschäftsjahres laut eingefrorenem Yahoo-Konsens."),
        F("eps_erwartet", "analysten", "Erwartetes EPS-Wachstum im nächsten Geschäftsjahr",
          spalte="konsens_eps_wachstum_1y_pct", signed=True, analysten=True,
          erklaerung="Erwarteter Gewinn je Aktie des nächsten Geschäftsjahres gegen das Geschäftsjahr davor, laut "
                     "eingefrorenem Yahoo-Konsens."),
        F("umsatz_erwartet", "analysten", "Erwartetes Umsatzwachstum im nächsten Geschäftsjahr",
          spalte="konsens_umsatz_wachstum_1y_pct", signed=True, analysten=True,
          erklaerung="Erwarteter Umsatz des nächsten Geschäftsjahres gegen das Geschäftsjahr davor, laut eingefrorenem "
                     "Yahoo-Konsens."),
        F("beat", "analysten", "Quartale mit übertroffener Gewinnschätzung", spalte="schaetzung_geschlagen", einheit="",
          stellen=0, analysten=True,
          erklaerung="In wie vielen der letzten vier Quartale mit Schätzung der gemeldete Gewinn je Aktie über der "
                     "Schätzung der Analysten lag, laut Nasdaq; 4 heißt jedes Mal."),
        F("ueberraschung", "analysten", "Letzte Gewinnüberraschung", spalte="letzte_ueberraschung_pct", signed=True,
          analysten=True,
          erklaerung="Abweichung des zuletzt gemeldeten Gewinns je Aktie von der Schätzung der Analysten."),
    ]
    # Revisionen und Einstufungen, nur fuer die Aktien der Wochenliste
    for k, name in PERIODEN_REV:
        for richtung, wort in (("hoch", "Anhebungen"), ("runter", "Senkungen")):
            for tage in (7, 30):
                felder.append(F(f"rev_{richtung}_{tage}t_{k}", "revisionen",
                                f"{wort} der Gewinnschätzung in {tage} Tagen, {name}",
                                spalte=f"rev_{richtung}_{tage}t_{k}", einheit="", stellen=0, analysten=True,
                                erklaerung=f"Wie viele Analysten ihre Schätzung des Gewinns je Aktie für das {name} "
                                           f"laut Yahoo in den letzten {tage} Tagen "
                                           f"{'angehoben' if richtung == 'hoch' else 'gesenkt'} haben; nur für die "
                                           "Aktien der Wochenliste."))
        for tage in (30, 90):
            felder.append(F(f"rev_aend_{tage}t_{k}", "revisionen",
                            f"Veränderung des Gewinnkonsens in {tage} Tagen, {name}", signed=True, analysten=True,
                            rechnung=_anteil(f"rev_eps_jetzt_{k}", f"rev_eps_{tage}t_{k}"),
                            quellen=(f"rev_eps_jetzt_{k}", f"rev_eps_{tage}t_{k}"),
                            erklaerung=f"Erwarteter Gewinn je Aktie für das {name} heute gegen den Wert vor {tage} "
                                       "Tagen, laut Yahoo; nur bei positivem Vergleichswert und nur für die Aktien "
                                       "der Wochenliste."))
    for tage in sd.kk.STUFEN_FENSTER:
        for art, titel, verb in (("hoch", "Heraufstufungen", "heraufgestuft haben"),
                                 ("runter", "Herabstufungen", "herabgestuft haben"),
                                 ("neu", "Erstbewertungen", "erstmals bewertet haben"),
                                 ("ziel_rauf", "Angehobene Kursziele", "ihr Kursziel angehoben haben"),
                                 ("ziel_runter", "Gesenkte Kursziele", "ihr Kursziel gesenkt haben")):
            felder.append(F(f"stufen_{art}_{tage}t", "revisionen", f"{titel} in {tage} Tagen",
                            spalte=f"stufen_{art}_{tage}t", einheit="", stellen=0, analysten=True,
                            erklaerung=f"Wie viele Analysten die Aktie laut Yahoo in den letzten {tage} Tagen {verb}; "
                                       "nur für die Aktien der Wochenliste."))
    felder += [
        # Leerverkaeufe
        F("short_anteil", "short", "Leerverkaufsanteil am letzten Handelstag", spalte="short_anteil_pct",
          analysten=True,
          erklaerung="Anteil der Leerverkäufe an den außerbörslich gemeldeten Umsätzen laut FINRA-Tagesdatei; kein "
                     "Short Interest, also kein Bestand offener Leerverkaufspositionen."),
        F("short_anteil_fenster", "short", f"Leerverkaufsanteil über {fenster_short} Handelstage",
          spalte="short_anteil_20t_pct", analysten=True,
          erklaerung=f"Derselbe Anteil über die letzten {fenster_short} Handelstage, nach Volumen gewichtet."),
        F("short_tage", "short", "Handelstage mit außerbörslichem Umsatz", spalte="short_tage_20t",
          einheit="Handelstage", stellen=0, analysten=True,
          erklaerung=f"An wie vielen der letzten {fenster_short} Handelstage FINRA außerbörsliche Umsätze gemeldet hat."),
        # Branchengruppe
        F("gruppe_rang", "gruppe", "Rang der Branchengruppe", spalte="gruppe_rang", einheit="", stellen=0,
          analysten=True,
          erklaerung="Rang der Branchengruppe nach dem Median der RS-Rohwerte ihrer Aktien; Rang 1 ist die stärkste "
                     "Gruppe. Jede Gruppe bekommt einen Rang, auch eine mit einer einzigen Aktie und die Sammelgruppe "
                     "Branche unbekannt; neben dem Rang stehen immer die Gruppe und die Zahl der Aktien, aus denen er "
                     "gerechnet ist."),
        F("gruppe_rang_3w", "gruppe", "Rang der Branchengruppe vor drei Wochen", spalte="gruppe_rang_3w", einheit="",
          stellen=0, analysten=True, erklaerung="Derselbe Rang drei Wochen früher, mit der Zahl der Aktien von damals."),
        F("gruppe_rang_6w", "gruppe", "Rang der Branchengruppe vor sechs Wochen", spalte="gruppe_rang_6w", einheit="",
          stellen=0, analysten=True, erklaerung="Derselbe Rang sechs Wochen früher, mit der Zahl der Aktien von damals."),
        F("gruppe_titel", "gruppe", "Aktien der Branchengruppe in der Rechnung", spalte="gruppe_titel", einheit="",
          stellen=0, analysten=True,
          erklaerung="Wie viele Aktien der Gruppe mit vollem RS-Rohwert in den Rang eingehen."),
    ]
    return tuple(felder)


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
    """Die Sektoren der Tabelle, deutsch sortiert; "" steht fuer ohne Angabe.
    Ohne Tabelle die bekannten Sektoren samt ohne Angabe."""
    vorhanden = set(SEKTOREN)
    if tabelle is None:
        vorhanden.add("")
    elif "sektor" in tabelle.columns:
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
        an("tief_1j", min=zahl_eingabe(ps.CFG["tt_min_above_low"] * 100.0 * (1.0 - t)))
        an("hoch_1j", max=zahl_eingabe(ps.CFG["tt_max_below_high"] * 100.0 * (1.0 + t)))
        an("ema50")
        an("ema200")
    elif kennung == "darvas":
        an("rs")
        an("hoch_1j")
        an("adr")
    elif kennung == "cup_handle":
        an("rs")
        an("hoch_1j")
        an("volumen")
    elif kennung == "rectangle":
        an("rs")
        an("hoch_3m")
        an("ema21")
    elif kennung in ("htf", "htf_innen"):
        an("rs")
        an("tief_3m")
        an("hoch_1m")
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
        an("hoch_1j")
        an("tief_1j")
    elif kennung == "hoch_allzeit":
        an("rs")
        an("hoch_allzeit")
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


def wirksame_einstellung(e):
    """Nur was das Ergebnis eines Scans bestimmt, zum Vergleich zweier
    Einstellungen: angehakte Felder samt Grenzen, Termine nur wenn an, keine
    Sortierung. Die App merkt so, dass sich seit dem letzten Scan etwas
    geaendert hat, ohne selbst neu zu rechnen (Gerhard, 15.09.2026: kein
    stilles Nachladen)."""
    e = {**standard_einstellung(), **(e or {})}
    k = e.get("strategie") or ""
    felder = {}
    for feld, fe in aktive_felder(e):
        if feld.art == "ja":
            felder[feld.schluessel] = True
        else:
            felder[feld.schluessel] = (str(fe.get("min") or "").strip(), str(fe.get("max") or "").strip(),
                                       bool(fe.get("vorlaeufig")) and feld.schluessel == "rs")
    te = e.get("termine") or {}
    termine = None
    if te.get("an"):
        termine = (tuple(bool(te.get(key)) for key, _t, _p, _l in TERMIN_TEILE), bool(te.get("ohne_zeit")),
                   te.get("umfang") or "markt")
    return {"strategie": k, "toleranz": bool(e.get("toleranz")) and toleranz_moeglich(k),
            "nur_handelbar": bool(e.get("nur_handelbar")),
            "langweilig_raus": bool(e.get("langweilig_raus")) and k == "darvas", "felder": felder,
            "termine": termine, "sektoren": None if e.get("sektoren") is None else sorted(e.get("sektoren"))}


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
    basis = df
    felder = aktive_felder(e)
    ohne_analysten, ohne_werte = [], []
    for feld, fe in felder:
        if feld.analysten and not analysten_da:
            ohne_analysten.append(feld.titel)
            continue
        m, f = feld.maske(df, fe)
        fehler += f
        if m is not None:
            # Eine Grenze oder Bedingung auf eine Kennzahl ohne jeden Wert laesst
            # keine Aktie uebrig; das soll nicht wie ein leerer Markt aussehen.
            if feld.art == "bereich":
                leer = not feld.werte(basis, fe).notna().any()
            else:
                leer = not _sp(basis, feld.spalte).notna().any()
            if leer:
                ohne_werte.append(feld.titel)
            df = df[m.reindex(df.index).fillna(False).astype(bool)]
    if ohne_analysten:
        hinweise.append("Die Analystendaten sind nicht geladen; " + ", ".join(ohne_analysten)
                        + " filtern deshalb nicht.")
    if ohne_werte:
        hinweise.append("Für " + ", ".join(ohne_werte) + " stehen in der Tabelle noch keine Werte; mit einer Grenze "
                        "oder Bedingung bleibt deshalb keine Aktie übrig.")
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


# ---------------------------------------------------------------------------
# Chartmuster der Etappe 1 (Gerhard, 20.09.2026)
# ---------------------------------------------------------------------------
# "Sie werden zu einem Treffer dazugeschrieben, so wie wir es bei den
# bestehenden Kapiteln halten. Wenn ein Muster passt, steht es dabei; wenn
# nicht, steht nichts dabei. Ausgeschlossen wird nie." Gerechnet wird in der
# Nachttabelle (chartmuster.py); hier entstehen nur die Saetze. Jede Zeile
# bekommt sie, gleich was eingestellt ist, und sie filtern nichts. Power Trend
# steht als Zustand immer dabei, an oder aus (Gerhard: "Als Zusatzzeile bei
# jedem Treffer"). Bei S und T sind die Kernschwellen unsere Festlegung, das
# steht in der Zeile selbst; alle Festlegungen nennt chartmuster_erklaerung.

def _cm_ja(r, spalte):
    v = _num(r.get(spalte))
    return v is not None and int(v) == 1


def _cm_wahr(x):
    return x is True or (isinstance(x, np.bool_) and bool(x))


def _cm_dollar(x):
    v = _num(x)
    return f"{zahl(v, 2 if v >= 1 else 4)} Dollar" if v is not None else "unbekannt"


def _cm_aufzaehlung(teile):
    teile = [t for t in teile if t]
    if not teile:
        return ""
    return teile[0] if len(teile) == 1 else ", ".join(teile[:-1]) + " und " + teile[-1]


def _cm_tag(iso):
    try:
        return date.fromisoformat(str(iso)[:10]).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return "unbekannt"


_CM_MONATE = ("Jänner", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
              "November", "Dezember")


def _cm_monat(iso):
    """'2026-08' wird 'August 2026'."""
    try:
        jahr, monat = str(iso)[:7].split("-")
        return f"{_CM_MONATE[int(monat) - 1]} {int(jahr)}"
    except (ValueError, IndexError):
        return "unbekannt"


def _cm_gezaehlt(r):
    """Seit wann die Stufenzaehlung laeuft, als Satzteil."""
    import chartmuster as cm
    grund, tag = r.get("cm_m_neu_grund"), _cm_tag(r.get("cm_m_neu_tag"))
    if grund == "markttief":
        return f"gezählt seit dem Markttief am {tag}"
    if grund == "korrektur":
        return f"gezählt seit der eigenen Korrektur um {zahl(cm.QUELLE['m_korrektur'] * 100, 0)} Prozent am {tag}"
    if grund == "basistief":
        return f"gezählt, seit der Kurs am {tag} das Tief der letzten Basis unterschritt"
    return f"gezählt seit Beginn der Kurshistorie am {tag}"


def muster_saetze(r):
    """Die Chartmuster einer Trefferzeile als Satzteile, in der Reihenfolge
    von Gerhards Tabelle B, A, D, F, G, N, S, T, L, K, Q, M, V; ohne Fund kein
    Satzteil, nur Power Trend steht immer dabei, sobald er gerechnet ist. Eine
    Luecke ohne erkannten Ausloeser steht getrennt vom Episodic Pivot (O16)."""
    t = []
    if _cm_ja(r, "cm_b"):
        s = "Inside Day"
        if _cm_wahr(r.get("cm_b_steigend")):
            s += " nach drei steigenden Tagen"
        if _cm_wahr(r.get("cm_b_vol_schrumpft")):
            s += ", Volumen kleiner als am Vortag"
        s += (f", eng über {_cm_dollar(r.get('cm_b_eng_kp'))} mit Stop {_cm_dollar(r.get('cm_b_eng_stop'))}"
              f", konservativ über {_cm_dollar(r.get('cm_b_kons_kp'))} mit Stop {_cm_dollar(r.get('cm_b_kons_stop'))}")
        t.append(s)
    if _cm_ja(r, "cm_a"):
        w = _num(r.get("cm_a_wochen"))
        t.append(f"Three Weeks Tight, {int(w) if w else 3} enge Wochen bis {_cm_tag(r.get('cm_a_bis'))}, "
                 f"Kaufpunkt {_cm_dollar(r.get('cm_a_kp'))}, Stop {_cm_dollar(r.get('cm_a_stop'))}")
    if _cm_ja(r, "cm_d"):
        f = _num(r.get("cm_d_vol_faktor"))
        t.append("Pocket Pivot" + (f", Volumen das {zahl(f, 1)}-Fache des stärksten Abwärtstags der zehn Tage davor"
                                   if f is not None else "")
                 + f", Einstieg über {_cm_dollar(r.get('cm_d_kp'))}, Stop {_cm_dollar(r.get('cm_d_stop'))}")
    pt = _num(r.get("cm_f"))
    if pt is not None:
        if int(pt) == 1:
            tage = _num(r.get("cm_f_tage"))
            t.append("Power Trend an seit " + ("einem Handelstag" if tage == 1 else
                                               f"{int(tage)} Handelstagen" if tage else "kurzem"))
        else:
            t.append("Power Trend aus")
    if _cm_ja(r, "cm_g"):
        w, tief = _num(r.get("cm_g_wochen")), _num(r.get("cm_g_tiefe_pct"))
        t.append(f"Flat Base über {int(w) if w else 5} Wochen"
                 + (f", {zahl(tief, 1)} Prozent tief" if tief is not None else "")
                 + f", Kaufpunkt {_cm_dollar(r.get('cm_g_kp'))}, Stop {_cm_dollar(r.get('cm_g_stop'))}")
    if _cm_ja(r, "cm_n"):
        ab, tage = _num(r.get("cm_n_abverkauf_pct")), _num(r.get("cm_n_tage"))
        t.append("Shakeout plus drei"
                 + (f" nach {zahl(ab, 1)} Prozent Abverkauf" if ab is not None else "")
                 + (f" in {int(tage)} Handelstagen" if tage else "")
                 + f", Tief am {_cm_tag(r.get('cm_n_tief_tag'))}"
                 + f", Einstieg plus 5 Prozent über {_cm_dollar(r.get('cm_n_kp5'))}"
                 + (" schon erreicht" if _cm_wahr(r.get("cm_n_kp5_erreicht")) else "")
                 + f", plus 10 Prozent über {_cm_dollar(r.get('cm_n_kp10'))}, Stop {_cm_dollar(r.get('cm_n_stop'))}"
                 + ", Hoch und Abverkauf nach eigener Festlegung")
    if _cm_ja(r, "cm_s"):
        stellen = [x.strip() for x in str(r.get("cm_s_stelle") or "").split(",") if x.strip()]
        t.append(f"Wick Play am {_cm_tag(r.get('cm_s_tag'))}, Docht {r.get('cm_s_seite') or 'unbekannt'}"
                 + (f" an {_cm_aufzaehlung(stellen)}" if stellen else "")
                 + f", Einstieg über {_cm_dollar(r.get('cm_s_kp'))}, Stop {_cm_dollar(r.get('cm_s_stop'))}"
                 + ", Schwellen eigene Festlegung")
    if _cm_ja(r, "cm_t"):
        u, v = _num(r.get("cm_t_unterschreitung_pct")), _num(r.get("cm_t_variante"))
        t.append("Shakeout am EMA 10" + (f", {zahl(u, 1)} Prozent darunter" if u is not None else "")
                 + (" und am Folgetag wieder darüber" if v == 2 else " und am selben Tag wieder darüber")
                 + ", Schwelle eigene Festlegung")
    if _cm_ja(r, "cm_l"):
        w, tief = _num(r.get("cm_l_wochen")), _num(r.get("cm_l_tiefe_pct"))
        seit = _num(r.get("cm_l_seit_wochen"))
        t.append(f"IPO Base über {int(w) if w else 3} Wochen"
                 + (f", {zahl(tief, 1)} Prozent tief" if tief is not None else "")
                 + (f", Erstnotiz vor {int(seit)} Wochen am {_cm_tag(r.get('cm_l_erstnotiz'))}"
                    if seit is not None else "")
                 + (", der Börsenmantel davor zählt nicht mit" if _cm_wahr(r.get("cm_l_mantel")) else "")
                 + (", die Erstnotiz ist unsicher" if _cm_wahr(r.get("cm_l_unsicher")) else "")
                 + f", Kaufpunkt {_cm_dollar(r.get('cm_l_kp'))}, Stop {_cm_dollar(r.get('cm_l_stop'))}")
    if _cm_ja(r, "cm_k"):
        w, g = _num(r.get("cm_k_wochen")), _num(r.get("cm_k_gewinn_pct"))
        t.append("Base-on-Base, die obere Basis"
                 + (f" seit {int(w)} Wochen" if w else "")
                 + (f" nur {zahl(g, 1)} Prozent über dem Ausbruch der unteren" if g is not None else "")
                 + ", beide zählen als eine Stufe"
                 + f", Kaufpunkt {_cm_dollar(r.get('cm_k_kp'))}, Stop {_cm_dollar(r.get('cm_k_stop'))}")
    if _cm_ja(r, "cm_q"):
        n, f = _num(r.get("cm_q_tage_ohne_hoch")), _num(r.get("cm_q_vol_faktor"))
        t.append(f"Green Line Breakout mit dem Monatsschluss {_cm_monat(r.get('cm_q_monat'))} über dem Allzeithoch "
                 f"von {_cm_dollar(r.get('cm_q_linie'))} vom {_cm_tag(r.get('cm_q_linie_tag'))}"
                 + (f", das {int(n)} Handelstage stand" if n else "")
                 + f", erster Schluss darüber am {_cm_tag(r.get('cm_q_ausbruch_tag'))}"
                 + (f", Volumen je Tag das {zahl(f, 1)}-Fache der 50 Tage davor" if f is not None else "")
                 + f", Einstieg über {_cm_dollar(r.get('cm_q_kp'))}, Stop {_cm_dollar(r.get('cm_q_stop'))}"
                 + ", Volumenschwelle eigene Festlegung")
    if _cm_ja(r, "cm_m"):
        s = _num(r.get("cm_m_stufe"))
        w, tief = _num(r.get("cm_m_wochen")), _num(r.get("cm_m_tiefe_pct"))
        satz = f"Basis Stufe {int(s)}" if s else "Basis"
        if s and int(s) == 3:
            satz += ", spät"
        elif s and int(s) >= 4:
            satz += ", sehr spät"
        if r.get("cm_m_status") == "ausbruch":
            satz += f", Ausbruch am {_cm_tag(r.get('cm_m_ausbruch'))}" + (f" aus {int(w)} Wochen" if w else "")
        else:
            satz += ", in Bildung" + (f" seit {int(w)} Wochen" if w else "")
        if tief is not None:
            satz += f", {zahl(tief, 1)} Prozent tief"
        if _cm_wahr(r.get("cm_m_bob")):
            satz += ", als Base-on-Base gleiche Stufe wie die Basis darunter"
        t.append(satz + ", " + _cm_gezaehlt(r))
    for merker, kopf in (("cm_v", "Episodic Pivot am {tag} nach Quartalszahlen"),
                         ("cm_vl", "Lücke ohne erkannten Auslöser am {tag}")):
        if not _cm_ja(r, merker):
            continue
        lu, f, ab = _num(r.get("cm_v_luecke_pct")), _num(r.get("cm_v_vol_faktor")), _num(r.get("cm_v_abstand_pct"))
        satz = kopf.format(tag=_cm_tag(r.get("cm_v_tag")))
        satz += (f", Lücke {zahl(lu, 1)} Prozent" if lu is not None else "")
        satz += (f", Volumen das {zahl(f, 1)}-Fache des 50-Tage-Schnitts" if f is not None else "")
        satz += (f", davor {zahl(ab, 1)} Prozent unter dem 200-Tage-Hoch" if ab is not None else "")
        satz += " und zwei Monate flach oder fallend"
        if _num(r.get("cm_v_kp")) is not None:
            satz += (f", Einstieg über {_cm_dollar(r.get('cm_v_kp'))}, dem Hoch der ersten fünf Minuten, "
                     f"Stop {_cm_dollar(r.get('cm_v_stop'))}")
        else:
            satz += ", Einstieg über dem Eröffnungsbereich, ohne Fünf-Minuten-Kurse nicht bestimmbar"
        t.append(satz + ", tote Phase und Eröffnungsbereich nach eigener Festlegung")
    return t


def chartmuster_erklaerung():
    """Die neun gebauten Muster und alle unsere Festlegungen als Saetze, fuer
    den Erklaerteil des Scanners (Gerhard: "im Code und in der Ausgabe als
    unsere eigene Festlegung gekennzeichnet")."""
    import chartmuster as cm
    q, f = cm.QUELLE, cm.FESTLEGUNGEN

    def pz(x):
        return zahl(x * 100, 0)

    k = f["pivot_kerzen"]
    return [
        "Seit dem 21.09.2026 stehen bei jedem Treffer die Chartmuster aus Gerhards Dokument vom 20.09.2026: "
        "Inside Day, Three Weeks Tight, Pocket Pivot, Power Trend, Flat Base, Shakeout plus drei, Wick Play, "
        "Shakeout am EMA 10, seit dem 22.09.2026 die IPO Base und seit dem 23.09.2026 Base-on-Base, der Green "
        "Line Breakout, die Stufenzählung der Basen und der Episodic Pivot. Sie sind Entscheidungshilfen und "
        "filtern nichts. "
        "Gerechnet wird am letzten Handelstag der Nachttabelle; Three Weeks Tight, Flat Base und IPO Base zählen "
        "nur abgeschlossene Wochen, Base-on-Base, Green Line und die Stufenzählung brauchen die ganze "
        "Kurshistorie. Das W, also das Double Bottom, ist am 22.09.2026 auf Gerhards Entscheid ganz entfallen.",
        f"Bei Three Weeks Tight zählen {q['a_wochen_min']} oder {q['a_wochen_max']} enge Wochen, ab "
        f"{q['a_wochen_max'] + 1} nicht mehr, auf Gerhards Entscheid vom 23.09.2026; länger eng ist ein "
        "festgenagelter Kurs, etwa bei einer Übernahme. Unsere Festlegungen dazu: davor mindestens "
        f"{pz(f['a_anstieg_min'])} Prozent Anstieg in den {f['a_anstieg_wochen']} Wochen vor der engen Phase, "
        f"und die Woche davor liegt höchstens {pz(f['a_nahe_hoch'])} Prozent unter dem höchsten Wochenschluss "
        "dieser Zeit.",
        f"Unsere Festlegung beim Pocket Pivot: in oder knapp über einer Basis heißt, die {f['d_basis_tage']} "
        f"Handelstage davor schwanken höchstens {pz(f['d_basis_tiefe_max'])} Prozent vom Hoch zum Tief, und der "
        f"Pivot-Tag schließt höchstens {pz(f['d_basis_ueber_max'])} Prozent über ihrem Hoch.",
        f"Unsere Festlegung beim Power Trend: nach dem letzten Tief heißt nach dem tiefsten Tief der "
        f"{f['f_tief_fenster']} Tage, deren Tiefs über dem EMA 21 liegen.",
        f"Unsere Festlegung bei der Flat Base: der Anstieg davor zählt vom tiefsten Wochentief der "
        f"{f['g_anstieg_wochen']} Wochen vor der Basis bis zu ihrem Hoch, und die Basis beginnt an ihrem Hoch.",
        f"Unsere Festlegungen beim Wick Play: Docht mindestens {zahl(f['s_docht_zu_koerper'], 0)}-mal so lang wie "
        f"der Körper, Körper höchstens {pz(f['s_koerper_max'])} Prozent der Tagesspanne, die Tagesspanne mindestens "
        f"so groß wie die durchschnittliche der {f['s_atr_tage']} Tage davor. Die markante Stelle liegt im Docht: "
        "EMA 10, EMA 21, SMA 50, SMA 200, Hoch oder Tief der 20 Tage davor oder das alte Hoch des Jahres davor. "
        f"Gesucht wird bis {f['s_tage_zurueck']} Handelstage zurück, solange seither kein Schluss über dem Hoch "
        f"der Kerze lag; Einstieg über dem Hoch plus {zahl(q['aufschlag'], 2)} Dollar.",
        f"Unsere Festlegung beim Shakeout am EMA 10: die Unterschreitung beträgt höchstens "
        f"{pz(f['t_unterschreitung_max'])} Prozent.",
        f"Unsere Festlegung bei der Erkennung von Hochs und Tiefs, auf der Shakeout plus drei sitzt: "
        f"Ein Hoch oder Tief ist das höchste oder tiefste von {2 * k + 1} Kerzen, {k} davor und {k} danach; "
        f"ein Tief gilt also erst, wenn {k} Kerzen danach höher lagen.",
        f"Unsere Festlegungen beim Shakeout plus drei: aus einem Hoch heißt aus dem höchsten Hoch der "
        f"{f['n_hoch_tage']} Handelstage bis dahin, scharf heißt mindestens {pz(f['n_abverkauf_min'])} Prozent "
        f"vom Hoch zum Tief in höchstens {f['n_abverkauf_tage']} Handelstagen. Es zählt nur der erste scharfe "
        f"Abverkauf nach dem Hoch: Stieg der Kurs schon nach einem früheren scharfen Tief um "
        f"{pz(q['n_aufschlag'][1])} Prozent, ist das spätere Tief ein zweiter Abverkauf. Gezeigt wird, solange das Tief "
        f"höchstens {f['n_tief_tage_max']} Handelstage zurückliegt, seither nicht unterschritten wurde und der Kurs "
        f"den Einstieg bei {pz(q['n_aufschlag'][1])} Prozent noch nicht erreicht hat. Die Einstiege bei "
        f"{pz(q['n_aufschlag'][0])} und {pz(q['n_aufschlag'][1])} Prozent über dem Tief stehen nebeneinander.",
        f"Unsere Festlegungen bei der IPO Base: Eine Aktie gilt höchstens {f['l_erstnotiz_wochen_max']} Wochen "
        "nach ihrer Erstnotiz als frisch notiert. Die Basis beginnt an ihrem Hoch wie die Flat Base, dauert "
        f"mindestens {q['l_wochen_min']} Wochen und ist {pz(q['l_tiefe_min'])} bis {pz(q['l_tiefe_max'])} Prozent "
        f"tief; Kaufpunkt am linken Hoch plus {zahl(q['aufschlag'], 2)} Dollar. Kam die Firma über einen "
        "Börsenmantel an die Börse, gilt der erste Handelstag nach der Übernahme als Erstnotiz, wenn der Mantel "
        f"erkennbar ist: mindestens {f['l_mantel_tage']} Handelstage zwischen {zahl(f['l_mantel_von'], 0)} und "
        f"{zahl(f['l_mantel_bis'], 0)} Dollar mit höchstens {pz(f['l_mantel_enge'])} Prozent Spanne, danach ein "
        f"Sprung von mindestens {pz(f['l_mantel_sprung'])} Prozent. Sieht der Anfang nur nach Mantel aus, bleibt "
        "der erste Kurstag die Erstnotiz und der Fund sagt, dass sie unsicher ist.",
        f"Stufenzählung der Basen nach Gerhards Regeln vom 23.09.2026, nur für Aktien über "
        f"{zahl(q['m_kurs_min'], 0)} Dollar: Eine Basis dauert mindestens {q['m_wochen_min']} Wochen, ist höchstens "
        f"{pz(q['m_tiefe_max'])} Prozent tief vom linken Hoch zum tiefsten Tief und ist ausgebrochen mit einem "
        "Tagesschluss über dem linken Hoch. Stufe 1 ist die erste Basis nach einem Markttief oder einer eigenen "
        "Korrektur; jede weitere zählt eine Stufe höher, wenn die Aktie aus der vorigen ausgebrochen ist und bis "
        f"zum linken Hoch der neuen mindestens {pz(q['k_gewinn_min'])} Prozent gewonnen hat. Darunter ist es "
        "Base-on-Base, beide Basen zählen als eine Stufe; Einstieg über dem Hoch der oberen Basis plus "
        f"{zahl(q['aufschlag'], 2)} Dollar, Stop an ihrem Tief. Die Zählung beginnt von vorn an einem Markttief, "
        f"sobald der Kurs das Tief der letzten Basis unterschreitet und sobald er {pz(q['m_korrektur'])} Prozent "
        f"unter dem letzten Hoch liegt; jede Basis, die tiefer als {pz(q['m_korrektur'])} Prozent korrigiert, ist "
        "damit Stufe 1, so gewollt. Ab Stufe 3 heißt die Basis spät, ab Stufe 4 sehr spät.",
        "Unsere Festlegungen bei der Stufenzählung: Ein Markttief ist das Tief einer Korrektur des S&P 500 oder "
        "des Nasdaq, deren Erholungsversuch ein Follow-through Day bestätigt hat, nach denselben Regeln wie in der "
        "Marktampel. Das linke Hoch einer Basis ist das höchste Hoch seit dem letzten Ausbruch; ein neues Hoch, "
        "bevor die Basis fünf Wochen alt ist, lässt sie dort neu beginnen. Gezählt wird in Kalenderwochen, die "
        f"Woche des linken Hochs zählt mit. Fällt der Kurs mehr als {pz(q['m_tiefe_max'])} Prozent unter das "
        "linke Hoch, beginnt die nächste Basis erst am höchsten Hoch nach dem tiefsten Tief dieses Rückgangs; eine "
        "bloße Erholung auf das alte Niveau zählt so nie als Basis. Unterschritten heißt mit dem Tagestief. Die "
        f"{zahl(q['m_kurs_min'], 0)} Dollar gelten für den letzten Schluss, gezählt wird die ganze Kurshistorie. "
        "Gezeigt wird die Basis, die sich bildet, sobald sie fünf Wochen alt ist, sonst die letzte, aus der die "
        "Aktie ausgebrochen ist.",
        f"Green Line Breakout nach Gerhards Regeln: Die grüne Linie ist das Allzeithoch, das mindestens "
        f"{q['q_tage_ohne_hoch']} Handelstage ohne neues Hoch stand. Das Signal ist ein Monatsschluss darüber; "
        "gezeigt wird es erst nach dem bestätigten Monatsschluss und dann im ganzen Folgemonat. Einstieg über der "
        "Linie, Stop am letzten Tief der Erkennung von Hochs und Tiefs vor dem ersten Schluss über der Linie, mit "
        "dem Zehn-Prozent-Deckel. Unsere Festlegung dazu: Volumen deutlich über dem Schnitt heißt, der Schnitt "
        f"je Handelstag im Ausbruchsmonat beträgt mindestens das {zahl(f['q_vol_faktor'], 1)}-Fache des Schnitts "
        f"der {f['q_vol_tage']} Handelstage vor diesem Monat. Ein Monat gilt als abgeschlossen, wenn sein letzter "
        "Werktag vorbei ist.",
        f"Episodic Pivot nach Gerhards Regeln vom 23.09.2026: eine Eröffnungslücke von mehr als "
        f"{pz(q['v_luecke'])} Prozent über dem Schluss des Vortags mit mindestens dem "
        f"{zahl(q['v_vol_faktor'], 0)}-Fachen des Schnittvolumens der {q['v_vol_tage']} Tage davor, nachdem die "
        f"Aktie mindestens zwei Monate tot war und mindestens {pz(q['v_abstand_200'])} Prozent unter ihrem "
        f"{q['v_hoch_tage']}-Tage-Hoch lag. Der Auslöser sind Zahlen am Lückentag oder am Handelstag davor laut "
        "Nasdaq-Kalender; eine Lücke ohne erkannten Auslöser steht getrennt da. Zulassung, Auftrag und "
        "Übernahme erkennt der Scanner nicht, dafür fehlt eine Nachrichtenquelle; solche Lücken stehen ebenfalls "
        "als Lücke ohne erkannten Auslöser da. Einstieg über dem Eröffnungsbereich des Lückentags. Stop am "
        "Tagestief; liegt es mehr als zehn Prozent unter dem Einstieg, an der Lückenunterkante, dem Schluss des "
        "Vortags, wenn diese den Zehn-Prozent-Deckel einhält, sonst greift der Deckel.",
        f"Unsere Festlegungen beim Episodic Pivot: Tot heißt, der Schluss vor der Lücke liegt höchstens "
        f"{pz(f['v_tot_anstieg_max'])} Prozent über dem Schluss zwei Monate davor, also {q['v_tote_tage']} "
        f"Handelstage, gerechnet wie die drei Monate beim Green Line Breakout. Gezeigt wird die jüngste Lücke "
        f"der letzten {f['v_tage_max']} Handelstage. Der Eröffnungsbereich ist das Hoch der ersten "
        f"{f['v_eroeffnung_minuten']} Minuten.",
        "Sechs dieser Muster melden seit dem 22.09.2026 auch im Handel, auf Gerhards Entscheid: Three Weeks "
        "Tight, Inside Day, Pocket Pivot, IPO Base, Shakeout plus drei und Wick Play. Der Nachtscan rechnet "
        "ihre Einstiege, der Wächter meldet, sobald der Kurs sie überschreitet, und zwar nur für die Aktien "
        "der beiden Wochenlisten und die einzeln überwachten. Es gelten dieselben Melderegeln wie bei den "
        "bestehenden Strategien; beim Inside Day meldet nur die Fassung mit drei steigenden Tagen davor, beim "
        "Shakeout plus drei der Einstieg bei 10 Prozent. Die Meldungen kommen vorerst als Auskunft und nicht "
        "als Alarm in der Handels-App, bis das Logbuch zeigt, wie die Muster laufen. Bestehende Kaufpunkte "
        "verdrängen sie nie.",
        "Alle Stops tragen den Zehn-Prozent-Deckel des Systems. Volumen vergleicht der Scanner nach Handelsschluss "
        "als ganze Tagesvolumina; dort ist die F(t)-Kurve bei eins.",
    ]


def satz_teile(ausw, r, werte=None):
    """Die Satzteile einer Zeile; werte: {Feldschluessel: schon gerechneter Wert}.
    Die Chartmuster (muster_saetze) kommen immer ans Ende, gleich was
    eingestellt ist."""
    teile = strategie_teile(ausw, r)
    werte = werte or {}
    for feld, fe in ausw.get("felder") or []:
        teile.append(feld.satz(r, fe, ausw.get("analysten_da", True), werte.get(feld.schluessel, _FEHLT)))
    if ausw.get("termine"):
        teile.append(termin_teil(r))
    if ausw.get("sektor_aktiv"):
        teile.append(f"Sektor {sektor_name(r.get('sektor') if isinstance(r.get('sektor'), str) else '')}")
    teile += muster_saetze(r)
    return teile


def zeilen(ausw, basis_url, anzahl=None, markdown=True):
    """Die Ergebnisliste: eine nummerierte Zeile je Aktie. In Markdown ist das
    Kuerzel ein Verweis auf die vollstaendigen Daten; als Text steht die
    Adresse am Ende."""
    df = ausw["df"]
    if anzahl:
        df = df.head(int(anzahl))
    # Die Werte der Felder einmal fuer alle Zeilen, nicht je Zeile neu.
    vorab = {feld.schluessel: feld.werte(df, fe).to_numpy() for feld, fe in ausw.get("felder") or []
             if feld.art == "bereich"}
    raus = []
    for i, r in enumerate(df.to_dict("records"), 1):
        t = str(r.get("ticker") or "")
        url = adresse(basis_url, t)
        teile = satz_teile(ausw, r, {k: w[i - 1] for k, w in vorab.items()})
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
    if "cm_f" in df.columns:
        raus["Chartmuster"] = ["; ".join(muster_saetze(r)) for r in df.to_dict("records")]
    raus["Schlusskurse vom"] =nachschlagen.datum_text((stand or {}).get("handelstag")) if (stand or {}).get("handelstag") else ""
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


def stand_saetze(stand, jetzt=None, analysten_da=True, nur_voll=False):
    """Saetze zum Stand der Tabelle. nur_voll: der Besucher ist nicht voll
    angemeldet (Gast, S4 vom 20.09.2026); dann heisst es nur, dass es die
    Analystendaten im vollen Zugang gibt, ohne Secrets oder Repos zu nennen."""
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
    kz = q.get("kennzahlen") or {}
    if kz and kz.get("status") != "ok":
        s.append(f"Die technischen Kennzahlen fehlen in dieser Tabelle: Der Nachtscan gehört zum "
                 f"{datum_lang(kz.get('technik_handelstag'))}.")
    an = q.get("analysten") or {}
    if nur_voll:
        s.append("Analystendaten gibt es nur im vollen Zugang.")
    elif not analysten_da:
        s.append("Analystendaten sind nicht geladen: Sie liegen im privaten Datenrepo, und in den Streamlit-Secrets "
                 "fehlt der Token DATEN_TOKEN.")
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
        "Die Fundamentzahlen kommen aus dem SEC-Fundament, das seit dem 21.09.2026 an jedem Abend Montag bis "
        "Freitag neu entsteht; ein neuer Quartalsbericht steht in der Regel in der zweiten Nacht nach seiner "
        "Einreichung darin, weil die SEC ihren Gesamtbestand einmal je Nacht neu zusammenstellt.",
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
# Vorlagen (Gerhard, 20.09.2026, S1; Mathias, 21.09.2026)
# ---------------------------------------------------------------------------
# "Im Scanner moechte ich meine eigenen Kriterien-Sets einstellen und unter
# einem selbstgewaehlten Namen abspeichern koennen. Fuer den Schnellzugriff
# spaeter: wenn ich genau diese Kombination irgendwann wieder scannen will,
# will ich sie mit einem Klick laden koennen." Eine Vorlage ist der Stand
# aller Bedienfelder des Scanners (die Schluessel nennt die App); die Datei
# liegt im PRIVATEN Datenrepo heliot-daten (Mathias: "3 Datenrepo") und gilt
# fuer beide, die den vollen Zugang haben. Hier nur Lesen, Pruefen und
# Schreiben der Datei, ohne Netz pruefbar.

VORLAGE_DATEI = "scanner_vorlagen.json"
VORLAGE_NAME_LAENGE = 60


def vorlagen_lesen(text):
    """Die Liste der Vorlagen aus dem Text der Datei; unlesbare oder fremde
    Eintraege fallen still weg. Ohne Datei (None, leer) eine leere Liste."""
    if not text:
        return []
    try:
        daten = json.loads(text)
    except ValueError:
        return []
    liste = daten.get("vorlagen") if isinstance(daten, dict) else None
    ergebnis = []
    for v in liste or []:
        if (isinstance(v, dict) and isinstance(v.get("name"), str) and v["name"].strip()
                and isinstance(v.get("werte"), dict)):
            ergebnis.append({"name": v["name"].strip(), "gespeichert_am": str(v.get("gespeichert_am") or ""),
                             "werte": v["werte"]})
    return ergebnis


def vorlage_name_pruefen(name):
    """(ok, bereinigter Name oder Grund). Ein Name hat 1 bis 60 Zeichen und
    keine Steuerzeichen; Leerraum am Rand faellt weg."""
    name = re.sub(r"\s+", " ", str(name or "")).strip()
    if not name:
        return False, "Bitte einen Namen für die Vorlage eingeben."
    if len(name) > VORLAGE_NAME_LAENGE:
        return False, f"Der Name ist länger als {VORLAGE_NAME_LAENGE} Zeichen."
    if any(ord(z) < 32 for z in name):
        return False, "Der Name enthält ein Steuerzeichen."
    return True, name


def vorlage_werte(zustand, schluessel):
    """Die Werte der Bedienfelder als Vorlage: nur die genannten Schluessel und
    nur einfache Werte (Wahrheitswert, Text, Zahl)."""
    werte = {}
    for s in schluessel:
        w = zustand.get(s)
        if isinstance(w, (bool, str, int, float)):
            werte[s] = w
    return werte


def vorlage_anwenden(werte, schluessel):
    """Was beim Laden einer Vorlage gesetzt wird: nur Schluessel, die der
    Scanner heute noch kennt, und nur einfache Werte. Merkmale, die es beim
    Speichern noch nicht gab, fehlen hier und bleiben beim Laden aus, weil die
    App vorher alles zuruecksetzt."""
    bekannt = set(schluessel)
    return {s: w for s, w in (werte or {}).items() if s in bekannt and isinstance(w, (bool, str, int, float))}


def vorlage_setzen(vorlagen, name, werte, jetzt=None):
    """(neue Liste, ersetzt): speichert unter dem Namen, ein gleicher Name
    ohne Ruecksicht auf Gross- und Kleinschreibung wird ersetzt. Die Liste ist
    nach Namen sortiert."""
    jetzt = jetzt or datetime.now(timezone.utc)
    neu = {"name": name, "gespeichert_am": jetzt.isoformat(timespec="seconds"), "werte": dict(werte)}
    rest = [v for v in vorlagen if v["name"].casefold() != name.casefold()]
    ersetzt = len(rest) != len(vorlagen)
    return sorted(rest + [neu], key=lambda v: v["name"].casefold()), ersetzt


def vorlage_entfernen(vorlagen, name):
    """(neue Liste, gefunden)."""
    rest = [v for v in vorlagen if v["name"] != name]
    return rest, len(rest) != len(vorlagen)


def vorlagen_text(vorlagen, jetzt=None):
    """Der Inhalt der Datei, lesbar eingerueckt."""
    jetzt = jetzt or datetime.now(timezone.utc)
    return json.dumps({"version": 1, "stand": jetzt.isoformat(timespec="seconds"), "vorlagen": vorlagen},
                      ensure_ascii=False, indent=1) + "\n"


def vorlage_beschriftung(v):
    """'Minervini streng, gespeichert am 21.09.2026 um 12:45 Uhr Wiener Zeit'."""
    teile = [v["name"]]
    try:
        zeit = wiener_zeit(v["gespeichert_am"])
    except Exception:  # noqa
        zeit = None
    if zeit:
        teile.append(f"gespeichert am {zeit}")
    return ", ".join(teile)


# ---------------------------------------------------------------------------
# Uebergabe an Wochen- oder Darvas-Liste (Gerhard, 20.09.2026, S2)
# ---------------------------------------------------------------------------
# "Eine im Scanner erzeugte Liste soll ich direkt an das Programm uebergeben
# koennen, als Wochenliste oder als Darvas-Liste. Vor der Uebergabe brauche ich
# einen Bearbeitungsmodus: pro Aktie ein Kontrollfeld." Die Listen haben das
# Format des Finviz-Exports, und gelesen werden daraus Ticker, Company und
# Sector (listen.py; der Sektor fuehrt ueber beobachtungen.SEKTOR_ETF zum
# Sektor-ETF fuer Sektor-Rang, Logbuch und Sektorhinweis). Eine uebergebene
# Liste muss dieselben Spalten tragen, sonst fehlte der Sektor still: Steht
# eine Aktie schon in einer der beiden Listen, wird ihre Finviz-Zeile
# uebernommen; sonst Ticker, Firmenname und der Sektor im Finviz-Schema, den
# die App nachschlaegt (erst Wochenlisten, dann Yahoo). Ein Sektor, der sich
# nicht feststellen laesst, bleibt leer, nichts wird erfunden. Ein fehlender
# Firmenname heisst "Name unbekannt" wie in der Ergebnisliste: listen.py liest
# ein leeres Feld als "nan", und so stuende es sonst in den Meldungen.

UEBERGABE_GRENZE = 1500          # dieselbe Grenze wie pruefe_wochenliste in der App
FINVIZ_SPALTEN = ("No.", "Ticker", "Company", "Sector", "Industry", "Country", "Market Cap", "P/E", "Price",
                  "Change", "Volume")
UEBERGABE_ZIELE = {"finviz_3.csv": "Wochenliste finviz_3.csv", "darvas.csv": "Darvas-Liste darvas.csv"}


def uebergabe_zeile(ticker, name):
    """Die Beschriftung des Kontrollfelds im Bearbeitungsmodus."""
    return f"{ticker}, {nachschlagen.lesbar(_firma(name))}"


def uebergabe_satz(gewaehlt, alle, ziel):
    if not gewaehlt:
        return "Alle Aktien sind abgewählt; es gibt nichts zu übergeben."
    teil = (f"alle {nachschlagen.zahl(alle)}" if gewaehlt == alle
            else f"{nachschlagen.zahl(gewaehlt)} von {nachschlagen.zahl(alle)}")
    if not ziel:
        return f"Ausgewählt sind {teil} Aktien; noch fehlt die Wahl der Liste."
    return f"Ausgewählt sind {teil} Aktien; sie ersetzen die {UEBERGABE_ZIELE.get(ziel, ziel)}."


def finviz_zeilen(*inhalte):
    """{Ticker: Zeile als dict} aus dem Text einer oder mehrerer Listen im
    Finviz-Format; die erste Nennung eines Tickers gewinnt. Unlesbares faellt
    still weg."""
    import csv
    zeilen = {}
    for inhalt in inhalte:
        if not inhalt:
            continue
        text = inhalt.decode("utf-8-sig", errors="replace") if isinstance(inhalt, bytes) else str(inhalt)
        try:
            leser = csv.DictReader(io.StringIO(text))
            for z in leser:
                t = str(z.get("Ticker") or "").strip().upper()
                if t and t not in zeilen:
                    zeilen[t] = {k: (v if v is not None else "") for k, v in z.items() if k}
        except csv.Error:
            continue
    return zeilen


def uebergabe_csv(ticker, namen, finviz, sektoren):
    """Die uebergebene Liste als CSV im Finviz-Format (bytes, UTF-8)."""
    import csv
    puffer = io.StringIO()
    schreiber = csv.DictWriter(puffer, fieldnames=FINVIZ_SPALTEN, lineterminator="\n", extrasaction="ignore")
    schreiber.writeheader()
    for nr, t in enumerate(ticker, 1):
        alt = finviz.get(t)
        if alt:
            zeile = {k: alt.get(k, "") for k in FINVIZ_SPALTEN}
        else:
            zeile = {k: "" for k in FINVIZ_SPALTEN}
            zeile["Company"] = _firma(namen.get(t))
            zeile["Sector"] = sektoren.get(t) or ""
        zeile["No."] = str(nr)
        zeile["Ticker"] = t
        schreiber.writerow(zeile)
    return puffer.getvalue().encode("utf-8")


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
         "kursziel": 140.0, "kursziel_abst_pct": 16.67, "kursziel_tief": 90.0, "abst_hoch_allzeit_pct": -12.0,
         "tk_atr14": 6.0, "tk_burst": False, "tk_sma50_abst": -0.001, "fu_fcf": 2.5e8, "tk_perf_1w": 4.25},
        {"ticker": "BBB", "name": "Beta_Corp *Test*", "kurse_aktuell": True, "handelbar": True,
         "in_wochenliste": False, "kurs": 15.0, "marktkap_mrd": 1200.0, "volumen_50": 100000.0,
         "dollarvolumen_50": 1.5e6, "umsatz_q_vj_pct": None, "abst_ema21_pct": -4.0, "abst_ema50_pct": -1.0,
         "abst_hoch_1j_pct": -26.0, "abst_tief_1j_pct": 24.0, "rs": None, "rs_vorlaeufig": 80,
         "rs_linie_hoch": False, "rs_linie_abst_pct": -2.5, "red_to_green": True, "seit_eroeffnung_pct": 3.0,
         "volumen_max_tage_her": 30, "sektor": None, "termin_datum": "2026-09-15", "termin_lage": "vorboerslich",
         "termin_quelle": "Nasdaq", "m_darvas": 1, "rating_darvas": 40, "darvas_langweilig": True,
         "darvas_langweilig_gruende": "mittlere Tagesspanne unter 2,5 Prozent", "m_trend_template": 1,
         "konsens": "Halten", "konsens_wert": 3, "schaetzung_geschlagen": 2, "quartale_mit_schaetzung": 4,
         "abst_hoch_allzeit_pct": -2.0, "tk_atr14": 0.3, "tk_burst": True, "tk_sma50_abst": 5.5, "fu_fcf": -1.2e7},
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

    # Spannen mit Von und Bis (Gerhard, 15.09.2026, Auftrag 1)
    a = auswerten(tab, felder(marktkap={"an": True, "min": "0,1", "max": "1000"}), heute)
    p("Spanne von 0,1 bis 1000 Milliarden, beide Grenzen", list(a["df"]["ticker"]) == ["AAA"])
    a = auswerten(tab, felder(kurs={"an": True, "max": "15"}), heute)
    p("Nach unten offen: bis 15 Dollar, die Grenze eingeschlossen", set(a["df"]["ticker"]) == {"BBB", "CCC"})
    a = auswerten(tab, felder(umsatz_q={"an": True, "min": "5", "max": "100"}), heute)
    p("Umsatzwachstum von 5 bis 100 Prozent", list(a["df"]["ticker"]) == ["AAA"])
    a = auswerten(tab, felder(kurs={"an": True, "min": "100", "max": "10"}), heute)
    p("Von ueber Bis wirkt nicht und wird gemeldet",
      len(a["df"]) == 3 and any("liegt über Bis" in f for f in a["fehler"]), "; ".join(a["fehler"]))
    a = auswerten(tab, felder(perf_1m={"an": True, "min": "1"}), heute)
    p("Grenze auf eine Kennzahl ohne jeden Wert: keine Aktie und ein Hinweis",
      a["df"].empty and any("noch keine Werte" in h for h in a["hinweise"]), "; ".join(a["hinweise"]))
    a = auswerten(tab, felder(atr_pct={"an": True, "min": "4"}), heute)
    p("Gerechnete Kennzahl: ATR in Prozent des Kurses", list(a["df"]["ticker"]) == ["AAA"])
    a = auswerten(tab, felder(fcf={"an": True, "min": "minus 20", "max": "0"}), heute)
    p("Betrag in Millionen Dollar, negative Grenze", list(a["df"]["ticker"]) == ["BBB"])
    a = auswerten(tab, felder(burst={"an": True}), heute)
    p("Bedingung ohne Zahl: Momentum Burst muss erfuellt sein", list(a["df"]["ticker"]) == ["BBB"])
    a = auswerten(tab, felder(pivot={"an": True}), heute)
    p("Bedingung auf eine Kennzahl ohne jeden Wert: keine Aktie und ein Hinweis",
      a["df"].empty and any("Episodic Pivot stehen in der Tabelle noch keine Werte" in h for h in a["hinweise"]),
      "; ".join(a["hinweise"]))
    p("Einstellungstext: von bis, nach oben offen, nach unten offen, angezeigt",
      FELD["marktkap"].einstellung_text({"min": "0,3", "max": "2"}) == "Marktkapitalisierung von 0,3 bis 2 Milliarden Dollar"
      and FELD["marktkap"].einstellung_text({"min": "0,3"}) == "Marktkapitalisierung ab 0,3 Milliarden Dollar, nach oben offen"
      and FELD["umsatz_q"].einstellung_text({"max": "100"}) == "Umsatzwachstum q/q bis 100 Prozent, nach unten offen"
      and FELD["rs"].einstellung_text({}) == "RS gegen den ganzen US-Markt angezeigt",
      FELD["marktkap"].einstellung_text({"min": "0,3", "max": "2"}))

    # Hoch, Tief, EMA, RS
    a = auswerten(tab, felder(hoch_1j={"an": True, "max": "25"}), heute)
    p("Bis 25 Prozent unter dem Jahreshoch", list(a["df"]["ticker"]) == ["AAA"])
    a = auswerten(tab, felder(hoch_3m={"an": True, "max": "2"}), heute)
    p("Jeder Zeitraum ein eigenes Feld: Quartalshoch", list(a["df"]["ticker"]) == ["AAA"])
    a = auswerten(tab, felder(hoch_1j={"an": True, "max": "30"}, hoch_allzeit={"an": True, "max": "5"}), heute)
    p("Jahreshoch und Allzeithoch zugleich eingegrenzt", list(a["df"]["ticker"]) == ["BBB"])
    a = auswerten(tab, felder(tief_1j={"an": True, "min": "25"}), heute)
    p("Ab 25 Prozent ueber dem Jahrestief", list(a["df"]["ticker"]) == ["AAA"])
    a = auswerten(tab, felder(ema21={"an": True, "max": "0"}), heute)
    p("EMA 21: bis 0 heisst Kurs darunter", list(a["df"]["ticker"]) == ["BBB"])
    a = auswerten(tab, felder(ema50={"an": True, "min": "5"}), heute)
    p("EMA 50: ab 5 Prozent darueber", list(a["df"]["ticker"]) == ["AAA"])
    a = auswerten(tab, felder(rs={"an": True, "min": "70"}), heute)
    p("RS ab 70 ohne vorlaeufiges RS", list(a["df"]["ticker"]) == ["AAA"])
    a = auswerten(tab, felder(rs={"an": True, "min": "70", "vorlaeufig": True}), heute)
    p("RS ab 70 mit vorlaeufigem RS junger Titel", set(a["df"]["ticker"]) == {"AAA", "BBB"})
    a = auswerten(tab, felder(neu_52w={"an": True}), heute)
    p("Ja-Feld ohne Spalte laesst nichts durch", a["df"].empty)

    # Fruehere Stufen als Spannen, Analysten
    a = auswerten(tab, felder(konsens={"an": True, "min": "4", "max": "5"}), heute)
    p("Konsens von 4 bis 5, Kaufen oder starker Kauf", list(a["df"]["ticker"]) == ["AAA"])
    a = auswerten(tab, felder(konsens={"an": True, "min": "3"}), heute)
    p("Konsens ab 3, mindestens Halten", set(a["df"]["ticker"]) == {"AAA", "BBB"})
    a = auswerten(tab, felder(konsens={"an": True}), heute)
    p("Konsens ohne Grenze filtert nicht", len(a["df"]) == 3)
    a = auswerten(tab, felder(beat={"an": True, "min": "3"}), heute)
    p("Schaetzung in 3 bis 4 von vier Quartalen geschlagen", list(a["df"]["ticker"]) == ["AAA"])
    a = auswerten(tab, felder(volmax={"an": True, "max": "2"}), heute)
    p("Groesstes Volumen jemals vor bis zu zwei Handelstagen", list(a["df"]["ticker"]) == ["AAA"])
    a = auswerten(tab, felder(kursziel_tief={"an": True, "max": "-20"}), heute)
    p("Gerechnete Analystenkennzahl: niedrigstes Kursziel 25 Prozent unter dem Kurs", list(a["df"]["ticker"]) == ["AAA"])
    a = auswerten(tab, felder(konsens={"an": True, "min": "5"}), heute, analysten_da=False)
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
      v["rs"]["min"] == zahl_eingabe(ps.CFG["tt_rs_min"]) and v["tief_1j"]["min"] == zahl_eingabe(ps.CFG["tt_min_above_low"] * 100)
      and v["hoch_1j"]["max"] == zahl_eingabe(ps.CFG["tt_max_below_high"] * 100) and v["ema50"] == {"an": True})
    vt = voreinstellung("trend_template", toleranz=True)
    p("Mit Toleranz gelockert", vt["rs"]["min"] == "66,5" and vt["tief_1j"]["min"] == "23,75"
      and vt["hoch_1j"]["max"] == "26,25", str(vt))
    p("Power-Gap ohne Toleranzstufe bleibt ohne Lockerung", voreinstellung("power_gap", True) == voreinstellung("power_gap"))
    w1 = wirksame_einstellung({"felder": {"kurs": {"an": True, "min": "10"}, "rs": {"an": False, "min": "80"}},
                               "sortierung": "rs", "termine": {"an": False, "heute_vor": True}})
    w2 = wirksame_einstellung({"felder": {"kurs": {"an": True, "min": " 10 "}, "rs": {"an": False, "min": "90"}},
                               "sortierung": "kurs:auf", "termine": {"an": False}})
    w3 = wirksame_einstellung({"felder": {"kurs": {"an": True, "min": "11"}}})
    p("Vergleich der Einstellungen: Sortierung, abgehakte Felder und abgeschaltete Termine zaehlen nicht, Grenzen schon",
      w1 == w2 and w1 != w3 and wirksame_einstellung({"felder": {"kurs": {"an": True}}}) != wirksame_einstellung({})
      and wirksame_einstellung({"strategie": "power_gap", "toleranz": True}) == wirksame_einstellung({"strategie": "power_gap"}))
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
    p("Jede Strategie der Auswahl hat einen Text und eine Vorgabe ohne unbekannte Felder; ohne Strategie kein Text",
      all(strategie_text(k) and all(s in FELD for s in voreinstellung(k)) for k, _n in AUSWAHL if k)
      and strategie_text("") == "")

    # Ergebnisliste: nur Angehaktes, Verweise, Satzform
    e = {"strategie": "darvas", "nur_handelbar": False, "langweilig_raus": False,
         "felder": {"rs": {"an": True}, "hoch_1j": {"an": True}, "marktkap": {"an": True}, "ema21": {"an": True},
                    "fcf": {"an": True}, "sma50": {"an": True}},
         "termine": {"an": True}}
    a = auswerten(tab, e, heute)
    z = zeilen(a, "https://heliot.streamlit.app", markdown=True)
    p("Liste: nummeriert, Kuerzel als Verweis auf die vollstaendigen Daten",
      z and z[0].startswith("1. [AAA](https://heliot.streamlit.app/?aktie=AAA), Alpha Inc.;"), z[0] if z else "")
    p("Liste: angehakte Merkmale stehen drin, andere nicht",
      "RS 95" in z[0] and "3,0 Prozent unter dem Jahreshoch" in z[0] and "Marktkapitalisierung 0,30 Milliarden Dollar" in z[0]
      and "Umsatzwachstum" not in z[0] and "EMA 50" not in z[0] and "Zahlen am Montag, 14.09.2026, nachbörslich" in z[0], z[0])
    p("Liste: Abstand zur Linie, Betrag in Millionen mit Vorzeichen, Kurs auf der Linie",
      "Kurs 2,00 Prozent über der EMA 21" in z[0] and "Free Cashflow plus 250,0 Millionen Dollar" in z[0]
      and "Kurs auf der SMA 50" in z[0], z[0])
    z2 = zeilen(auswerten(tab, {"nur_handelbar": False, "felder": {"fcf": {"an": True}, "sma50": {"an": True},
                                                                     "perf_1w": {"an": True}}}, heute), "https://x")
    p("Liste: negativer Betrag, Kurs ueber der Linie, fehlender Wert heisst nicht berechenbar",
      "Free Cashflow minus 12,0 Millionen Dollar" in z2[1] and "Kurs 5,50 Prozent über der SMA 50" in z2[1]
      and "Wertentwicklung eine Woche nicht berechenbar" in z2[1] and "Wertentwicklung eine Woche plus 4,2 Prozent" in z2[0]
      and "SMA 50 unbekannt" in z2[2], " | ".join(z2))
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
      and "Free Cashflow in Millionen Dollar" in tabelle_e.columns and "Abstand zur EMA 21 in Prozent" in tabelle_e.columns
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
      not any("nach dem Nachtscan" in x for x in s3) and any("DATEN_TOKEN" in x for x in s3), " | ".join(s3))
    s4 = stand_saetze({"handelstag": "2026-09-11", "quellen": {"analysten": {"mit_stand": 950}}, "zeilen": 6500},
                      jetzt=datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc), analysten_da=False, nur_voll=True)
    p("Stand fuer Gaeste (S4): nur der Hinweis auf den vollen Zugang, kein Secret, kein Repo",
      "Analystendaten gibt es nur im vollen Zugang." in s4
      and not any("TOKEN" in x or "Datenrepo" in x or "Secrets" in x for x in s4), " | ".join(s4))

    # Texte: kein langer Strich, keine Bildzeichen
    texte = [f.titel for f in FELDER] + [f.erklaerung for f in FELDER] + [f.einheit for f in FELDER]
    texte += [f.eingabe_titel(teil) for f in FELDER for teil in ("min", "max")] + [strategie_text(k) for k, _n in AUSWAHL]
    texte += [n for _k, n in AUSWAHL] + grenzen_saetze() + [handelbar_text(), langweile_text()]
    texte += [t for _k, t, _p, _l in TERMIN_TEILE] + list(LAGE_TEXT.values()) + [x[1] for x in FORMATE]
    texte += [x[1] for x in UMFANG] + list(SEKTOREN.values()) + [g for _k, g in GRUPPEN]
    texte += [FELDER[0].eingabe_hinweis("min"), FELDER[0].eingabe_hinweis("max")]
    lang = [t for t in texte if chr(0x2013) in t or chr(0x2014) in t]
    p("Kein langer Strich in Beschriftungen und Erklaerungen", not lang, "; ".join(lang[:3]))
    bild = [t for t in texte if nachschlagen.bildzeichen_in(t)]
    p("Keine Bildzeichen in Beschriftungen und Erklaerungen", not bild, "; ".join(bild[:3]))
    p("Beschriftung der Grenzfelder: von und bis mit der Einheit, Platzhalter nennen das offene Ende",
      FELD["hoch_1j"].eingabe_titel("max") == "Abstand zum Jahreshoch bis, in Prozent unter dem Hoch"
      and FELD["tief_3m"].eingabe_titel("min") == "Abstand zum Quartalstief von, in Prozent über dem Tief"
      and FELD["marktkap"].eingabe_titel("min") == "Marktkapitalisierung von, in Milliarden Dollar"
      and FELD["rs"].eingabe_titel("min") == "RS gegen den ganzen US-Markt von"
      and FELD["kurs"].eingabe_hinweis("min") == "leer heißt nach unten offen"
      and FELD["kurs"].eingabe_hinweis("max") == "leer heißt nach oben offen")
    p("Jedes Feld hat Titel, Gruppe und Erklaerung; Schluessel und Titel sind eindeutig; jede Gruppe hat Felder",
      all(f.titel and f.erklaerung and f.gruppe in dict(GRUPPEN) for f in FELDER) and len(FELD) == len(FELDER)
      and len({f.titel for f in FELDER}) == len(FELDER) and all(any(f.gruppe == g for f in FELDER) for g, _n in GRUPPEN))
    zr = {"gruppe": "Gold", "gruppe_rang": 3.0, "gruppen_zahl": 165.0, "gruppe_titel": 1.0, "gruppe_rang_3w": 150.0,
          "gruppe_titel_3w": 1.0, "gruppe_rang_6w": None, "gruppe_titel_6w": 0.0}
    zu = {"gruppe": "Branche unbekannt", "gruppe_rang": 40.0, "gruppen_zahl": 165.0, "gruppe_titel": 212.0}
    p("Rang der Branchengruppe: immer mit Gruppe und Zahl der Aktien, auch Branche unbekannt (Nachfragen N8 und N9)",
      FELD["gruppe_rang"].satz(zr) == "Rang der Branchengruppe 3 von 165, Gold, aus 1 Aktie gerechnet"
      and FELD["gruppe_rang_3w"].satz(zr) == "Rang der Branchengruppe vor drei Wochen 150, Gold, aus 1 Aktie gerechnet"
      and FELD["gruppe_rang_6w"].satz(zr) == "Rang der Branchengruppe vor sechs Wochen unbekannt, Gold"
      and FELD["gruppe_rang"].satz(zu) == "Rang der Branchengruppe 40 von 165, Branche unbekannt, aus 212 Aktien gerechnet",
      " | ".join([FELD["gruppe_rang"].satz(zr), FELD["gruppe_rang_3w"].satz(zr), FELD["gruppe_rang_6w"].satz(zr),
                  FELD["gruppe_rang"].satz(zu)]))
    sp_r = FELD["gruppe_rang_3w"].datei_spalten(pd.DataFrame([zr, zu]))
    p("Rang der Branchengruppe in den Dateien: Rang, Gruppe und Zahl der Aktien nebeneinander",
      [k for k, _w in sp_r] == ["Rang der Branchengruppe vor drei Wochen", "Branchengruppe",
                                "Aktien zum Rang der Branchengruppe vor drei Wochen"]
      and list(sp_r[1][1]) == ["Gold", "Branche unbekannt"] and sp_r[2][1].iloc[0] == 1.0 and pd.isna(sp_r[2][1].iloc[1]),
      str([(k, list(w)) for k, w in sp_r]))
    p("Beta nennt im Titel die Handelstage, ueber die es gerechnet ist (Nachfrage N4)",
      FELD["beta"].titel == f"Beta gegen SPY über {int(ZENTRAL['technik']['beta_tage'])} Handelstage"
      and FELD["beta"].satz({"tk_beta": 1.35}) == f"Beta gegen SPY über {int(ZENTRAL['technik']['beta_tage'])} Handelstage plus 1,35",
      FELD["beta"].satz({"tk_beta": 1.35}))
    genutzt = {f.spalte for f in FELDER if f.spalte} | {q for f in FELDER for q in f.quellen}
    fehlend = [s for s in sd.KENNZAHL_SPALTEN if s not in genutzt]
    p("Jede Kennzahl der Nachttabelle aus Nachtscan und Fundament hat ein Feld", not fehlend, ", ".join(fehlend))
    p("Nur noch Spannen und Bedingungen, keine Stufen- oder Lagewahl mehr",
      all(f.art in ("bereich", "ja") for f in FELDER) and not any(hasattr(f, "wahl") for f in FELDER))

    # Vorlagen (Gerhard, 20.09.2026, S1)
    t0 = datetime(2026, 9, 21, 10, 45, tzinfo=timezone.utc)
    schl = ["sc_strategie", "sc_rs_an", "sc_rs_min", "sc_sektor_technology"]
    zustand = {"sc_strategie": "vcp", "sc_rs_an": True, "sc_rs_min": "80", "sc_sektor_technology": False,
               "sc_ergebnis": {"treffer": 3}, "sc_fremd": "x", "sc_liste": [1, 2]}
    w = vorlage_werte(zustand, schl)
    p("Vorlage: nur die Schluessel des Scanners und nur einfache Werte",
      w == {"sc_strategie": "vcp", "sc_rs_an": True, "sc_rs_min": "80", "sc_sektor_technology": False}, str(w))
    v1, ersetzt1 = vorlage_setzen([], "Minervini streng", w, t0)
    v2, ersetzt2 = vorlage_setzen(v1, "  Anfang  ", {"sc_strategie": ""}, t0)
    v3, ersetzt3 = vorlage_setzen(v2, "minervini STRENG", {"sc_strategie": "vcp"}, t0)
    p("Vorlage: nach Namen sortiert, gleicher Name ohne Gross- und Kleinschreibung wird ersetzt",
      [v["name"] for v in v2] == ["  Anfang  ", "Minervini streng"] and not ersetzt1 and not ersetzt2 and ersetzt3
      and [v["name"] for v in v3] == ["  Anfang  ", "minervini STRENG"], str([v["name"] for v in v3]))
    text = vorlagen_text(v3, t0)
    gelesen = vorlagen_lesen(text)
    p("Vorlage: Datei hin und zurueck, Rand-Leerraum faellt beim Lesen weg, Umlaute bleiben",
      [v["name"] for v in gelesen] == ["Anfang", "minervini STRENG"] and gelesen[1]["werte"] == {"sc_strategie": "vcp"}
      and '"version": 1' in text and vorlagen_lesen(vorlagen_text([{"name": "Größe", "gespeichert_am": "",
                                                                   "werte": {}}]))[0]["name"] == "Größe")
    p("Vorlage: unlesbare Datei und fremde Eintraege",
      vorlagen_lesen("kaputt") == [] and vorlagen_lesen(None) == []
      and vorlagen_lesen('{"vorlagen": [{"name": ""}, {"name": "a", "werte": 3}, "x", {"name": "b", "werte": {}}]}')
      == [{"name": "b", "gespeichert_am": "", "werte": {}}])
    p("Vorlage: Name pruefen",
      vorlage_name_pruefen("  Minervini   streng ") == (True, "Minervini streng")
      and not vorlage_name_pruefen("")[0] and not vorlage_name_pruefen("x" * 61)[0]
      and not vorlage_name_pruefen("a\x07b")[0])
    p("Vorlage: beim Laden nur heute bekannte Schluessel und einfache Werte",
      vorlage_anwenden({"sc_rs_min": "80", "sc_alt_weg": True, "sc_rs_an": [1]}, schl) == {"sc_rs_min": "80"})
    p("Vorlage: entfernen",
      vorlage_entfernen(gelesen, "Anfang") == ([gelesen[1]], True) and vorlage_entfernen(gelesen, "fehlt")[1] is False)
    p("Vorlage: Beschriftung mit Wiener Zeit",
      vorlage_beschriftung({"name": "Minervini streng", "gespeichert_am": "2026-09-21T10:45:00+00:00"})
      == "Minervini streng, gespeichert am 21.09.2026 um 12:45 Uhr Wiener Zeit"
      and vorlage_beschriftung({"name": "a", "gespeichert_am": ""}) == "a")

    # Uebergabe an Wochen- oder Darvas-Liste (Gerhard, 20.09.2026, S2)
    haupt = ("﻿No.,Ticker,Company,Sector,Industry,Country,Market Cap,P/E,Price,Change,Volume\n"
             '1,ADPT,Adaptive Biotechnologies Corp,Healthcare,Diagnostics & Research,USA,4566.04,,28.61,0.21%,2985539\n'
             '2,"BRK.B","Berkshire Hathaway Inc, Class B",Financial,Insurance,USA,1.0,,1,1%,1\n').encode("utf-8")
    darv = ("No.,Ticker,Company,Sector,Industry,Country,Market Cap,P/E,Price,Change,Volume\n"
            "1,ADPT,Adaptive Anders,Technology,,USA,,,,,\n").encode("utf-8")
    fz = finviz_zeilen(darv, haupt, None)
    p("Uebergabe: Finviz-Zeilen beider Listen, erste Nennung gewinnt, Beistrich im Namen",
      sorted(fz) == ["ADPT", "BRK.B"] and fz["ADPT"]["Company"] == "Adaptive Anders"
      and fz["BRK.B"]["Company"] == "Berkshire Hathaway Inc, Class B", str(sorted(fz)))
    roh_u = uebergabe_csv(["BRK.B", "NEU", "OHNE"], {"NEU": "Neuer Name Inc. - Common Stock", "OHNE": None}, fz,
                          {"NEU": "Technology"})
    df_u = pd.read_csv(io.BytesIO(roh_u), dtype=str, keep_default_na=False)
    p("Uebergabe: CSV im Finviz-Format, bekannte Aktie mit ihrer Zeile, neue mit Firmenname und Sektor, "
      "fehlender Sektor leer, fehlender Name wie in der Ergebnisliste, neu nummeriert",
      list(df_u.columns) == list(FINVIZ_SPALTEN) and list(df_u["Ticker"]) == ["BRK.B", "NEU", "OHNE"]
      and list(df_u["No."]) == ["1", "2", "3"] and df_u.loc[0, "Sector"] == "Financial"
      and df_u.loc[0, "Industry"] == "Insurance" and df_u.loc[1, "Company"] == "Neuer Name Inc."
      and df_u.loc[1, "Sector"] == "Technology" and df_u.loc[1, "Industry"] == ""
      and df_u.loc[2, "Company"] == "Name unbekannt" and df_u.loc[2, "Sector"] == "", " | ".join(df_u["Ticker"]))
    p("Uebergabe: Saetze",
      uebergabe_satz(3, 3, "darvas.csv") == "Ausgewählt sind alle 3 Aktien; sie ersetzen die Darvas-Liste darvas.csv."
      and uebergabe_satz(2, 1200, None) == "Ausgewählt sind 2 von 1.200 Aktien; noch fehlt die Wahl der Liste."
      and uebergabe_satz(0, 3, "finviz_3.csv").startswith("Alle Aktien sind abgewählt")
      and uebergabe_zeile("AAOI", "Applied Optoelectronics, Inc. - Common Stock") == "AAOI, Applied Optoelectronics, Inc.")

    # Chartmuster der Etappe 1 (Gerhard, 20.09.2026)
    r = {"cm_b": 1, "cm_b_steigend": True, "cm_b_vol_schrumpft": np.bool_(False), "cm_b_eng_kp": 12.34,
         "cm_b_eng_stop": 11.9, "cm_b_kons_kp": 12.8, "cm_b_kons_stop": 11.5, "cm_a": 0, "cm_d": float("nan"),
         "cm_f": 1.0, "cm_f_tage": 14.0, "cm_g": 0, "cm_s": 1, "cm_s_tag": "2026-09-18", "cm_s_seite": "unten",
         "cm_s_stelle": "EMA 10, SMA 50", "cm_s_kp": 45.6, "cm_s_stop": 41.04, "cm_t": 1, "cm_t_variante": 2.0,
         "cm_t_unterschreitung_pct": 1.43}
    ms = muster_saetze(r)
    p("Chartmuster: Reihenfolge B, F, S, T, Preise in Dollar, Festlegung bei S und T genannt",
      ms == ["Inside Day nach drei steigenden Tagen, eng über 12,34 Dollar mit Stop 11,90 Dollar, konservativ über "
             "12,80 Dollar mit Stop 11,50 Dollar",
             "Power Trend an seit 14 Handelstagen",
             "Wick Play am 18.09.2026, Docht unten an EMA 10 und SMA 50, Einstieg über 45,60 Dollar, Stop 41,04 "
             "Dollar, Schwellen eigene Festlegung",
             "Shakeout am EMA 10, 1,4 Prozent darunter und am Folgetag wieder darüber, Schwelle eigene Festlegung"],
      " | ".join(ms))
    ms = muster_saetze({"cm_a": 1, "cm_a_wochen": 4.0, "cm_a_bis": "2026-09-18", "cm_a_kp": 0.5123, "cm_a_stop": 0.47,
                        "cm_d": 1, "cm_d_vol_faktor": 2.4, "cm_d_kp": 18.81, "cm_d_stop": 18.06, "cm_f": 0,
                        "cm_g": 1, "cm_g_wochen": 5.0, "cm_g_tiefe_pct": 10.0, "cm_g_kp": 51.07, "cm_g_stop": 45.97})
    p("Chartmuster: A, D, Power Trend aus, G; Kleinstbetraege mit vier Stellen",
      ms == ["Three Weeks Tight, 4 enge Wochen bis 18.09.2026, Kaufpunkt 0,5123 Dollar, Stop 0,4700 Dollar",
             "Pocket Pivot, Volumen das 2,4-Fache des stärksten Abwärtstags der zehn Tage davor, Einstieg über "
             "18,81 Dollar, Stop 18,06 Dollar",
             "Power Trend aus",
             "Flat Base über 5 Wochen, 10,0 Prozent tief, Kaufpunkt 51,07 Dollar, Stop 45,97 Dollar"],
      " | ".join(ms))
    p("Chartmuster: ohne Spalten und ohne gerechneten Power Trend steht nichts dabei",
      muster_saetze({"ticker": "AAA"}) == [] and muster_saetze({"cm_f": float("nan"), "cm_b": 0}) == [])
    ms = muster_saetze({"cm_n": 1, "cm_n_tief_tag": "2026-09-16", "cm_n_abverkauf_pct": 20.3, "cm_n_tage": 15.0,
                        "cm_n_kp5": 31.3635, "cm_n_kp10": 32.857, "cm_n_kp5_erreicht": np.bool_(True),
                        "cm_n_stop": 29.87, "cm_t": 0})
    p("Chartmuster: Shakeout plus drei mit beiden Einstiegen, in der Reihenfolge der Tabelle",
      ms == ["Shakeout plus drei nach 20,3 Prozent Abverkauf in 15 Handelstagen, Tief am 16.09.2026, Einstieg "
             "plus 5 Prozent über 31,36 Dollar schon erreicht, plus 10 Prozent über 32,86 Dollar, Stop 29,87 Dollar, "
             "Hoch und Abverkauf nach eigener Festlegung"],
      " | ".join(ms))
    p("Chartmuster: das W ist gestrichen, alte Spalten ergeben keinen Satz mehr (Gerhard, 22.09.2026)",
      muster_saetze({"cm_h": 1.0, "cm_h_wochen": 13.0, "cm_h_kp": 25.27, "cm_h_stop": 22.75}) == [])
    ms = muster_saetze({"cm_l": 1, "cm_l_wochen": 6.0, "cm_l_tiefe_pct": 28.4, "cm_l_seit_wochen": 11.0,
                        "cm_l_erstnotiz": "2026-05-04", "cm_l_mantel": np.bool_(True),
                        "cm_l_unsicher": False, "cm_l_kp": 40.18, "cm_l_stop": 36.17})
    p("Chartmuster: IPO Base samt Erstnotiz und Boersenmantel",
      ms == ["IPO Base über 6 Wochen, 28,4 Prozent tief, Erstnotiz vor 11 Wochen am 04.05.2026, "
             "der Börsenmantel davor zählt nicht mit, Kaufpunkt 40,18 Dollar, Stop 36,17 Dollar"], " | ".join(ms))
    ms = muster_saetze({"cm_l": 1, "cm_l_wochen": 3.0, "cm_l_tiefe_pct": 22.0, "cm_l_seit_wochen": 5.0,
                        "cm_l_erstnotiz": "2026-08-17", "cm_l_mantel": False, "cm_l_unsicher": True,
                        "cm_l_kp": 12.6, "cm_l_stop": 11.34})
    p("Chartmuster: IPO Base mit unsicherer Erstnotiz sagt das (Gerhard, O14)",
      ms == ["IPO Base über 3 Wochen, 22,0 Prozent tief, Erstnotiz vor 5 Wochen am 17.08.2026, "
             "die Erstnotiz ist unsicher, Kaufpunkt 12,60 Dollar, Stop 11,34 Dollar"], " | ".join(ms))
    ms = muster_saetze({"cm_n": 1, "cm_n_tief_tag": "2026-09-16", "cm_n_abverkauf_pct": 16.3, "cm_n_tage": 6,
                        "cm_n_kp5": 174.57, "cm_n_kp10": 182.89, "cm_n_kp5_erreicht": False, "cm_n_stop": 166.26})
    p("Chartmuster: Shakeout plus drei, fuenf Prozent noch nicht erreicht",
      ms == ["Shakeout plus drei nach 16,3 Prozent Abverkauf in 6 Handelstagen, Tief am 16.09.2026, Einstieg "
             "plus 5 Prozent über 174,57 Dollar, plus 10 Prozent über 182,89 Dollar, Stop 166,26 Dollar, "
             "Hoch und Abverkauf nach eigener Festlegung"], " | ".join(ms))
    ms = muster_saetze({"cm_k": 1, "cm_k_gewinn_pct": 3.1, "cm_k_wochen": 7.0, "cm_k_kp": 287.3,
                        "cm_k_stop": 258.57, "cm_q": 1, "cm_q_monat": "2026-08", "cm_q_linie": 50.25,
                        "cm_q_linie_tag": "2025-11-28", "cm_q_tage_ohne_hoch": 179.0, "cm_q_vol_faktor": 2.0,
                        "cm_q_ausbruch_tag": "2026-08-07", "cm_q_kp": 50.25, "cm_q_stop": 45.23,
                        "cm_m": 1, "cm_m_stufe": 1.0, "cm_m_status": "bildung", "cm_m_wochen": 7.0,
                        "cm_m_tiefe_pct": 14.9, "cm_m_bob": np.bool_(True), "cm_m_neu_grund": "markttief",
                        "cm_m_neu_tag": "2026-07-29"})
    p("Chartmuster: Base-on-Base, Green Line und Stufe in der Reihenfolge der Tabelle",
      ms == ["Base-on-Base, die obere Basis seit 7 Wochen nur 3,1 Prozent über dem Ausbruch der unteren, beide "
             "zählen als eine Stufe, Kaufpunkt 287,30 Dollar, Stop 258,57 Dollar",
             "Green Line Breakout mit dem Monatsschluss August 2026 über dem Allzeithoch von 50,25 Dollar vom "
             "28.11.2025, das 179 Handelstage stand, erster Schluss darüber am 07.08.2026, Volumen je Tag das "
             "2,0-Fache der 50 Tage davor, Einstieg über 50,25 Dollar, Stop 45,23 Dollar, Volumenschwelle eigene "
             "Festlegung",
             "Basis Stufe 1, in Bildung seit 7 Wochen, 14,9 Prozent tief, als Base-on-Base gleiche Stufe wie die "
             "Basis darunter, gezählt seit dem Markttief am 29.07.2026"], " | ".join(ms))
    ms = muster_saetze({"cm_m": 1, "cm_m_stufe": 3.0, "cm_m_status": "ausbruch", "cm_m_wochen": 9.0,
                        "cm_m_tiefe_pct": 25.1, "cm_m_ausbruch": "2026-08-03", "cm_m_bob": False,
                        "cm_m_neu_grund": "korrektur", "cm_m_neu_tag": "2026-06-10"})
    ms4 = muster_saetze({"cm_m": 1, "cm_m_stufe": 4.0, "cm_m_status": "bildung", "cm_m_wochen": 6.0,
                         "cm_m_tiefe_pct": 11.0, "cm_m_bob": None, "cm_m_neu_grund": "basistief",
                         "cm_m_neu_tag": "2026-02-02"})
    ms_b = muster_saetze({"cm_m": 1, "cm_m_stufe": 2.0, "cm_m_status": "bildung", "cm_m_wochen": 8.0,
                          "cm_m_tiefe_pct": 12.0, "cm_m_neu_grund": "beginn", "cm_m_neu_tag": "2025-06-18"})
    p("Chartmuster: Stufe 3 heißt spät, Stufe 4 sehr spät, jede Ruecksetzung nennt ihren Grund",
      ms == ["Basis Stufe 3, spät, Ausbruch am 03.08.2026 aus 9 Wochen, 25,1 Prozent tief, gezählt seit der "
             "eigenen Korrektur um 20 Prozent am 10.06.2026"]
      and ms4 == ["Basis Stufe 4, sehr spät, in Bildung seit 6 Wochen, 11,0 Prozent tief, gezählt, seit der Kurs "
                  "am 02.02.2026 das Tief der letzten Basis unterschritt"]
      and ms_b == ["Basis Stufe 2, in Bildung seit 8 Wochen, 12,0 Prozent tief, gezählt seit Beginn der "
                   "Kurshistorie am 18.06.2025"], " | ".join(ms + ms4 + ms_b))
    p("Chartmuster: ohne Treffer bei K, Q und M kein Satz",
      muster_saetze({"cm_k": 0, "cm_q": 0.0, "cm_m": 0, "cm_m_stufe": float("nan")}) == [])
    v_zeile = {"cm_v_tag": "2026-09-17", "cm_v_luecke_pct": 13.3, "cm_v_vol_faktor": 4.0,
               "cm_v_abstand_pct": 25.4, "cm_v_kp": 35.2, "cm_v_stop": 33.66}
    ms = muster_saetze({"cm_v": 1, "cm_vl": 0, **v_zeile})
    ms_l = muster_saetze({"cm_v": 0, "cm_vl": 1.0, **v_zeile, "cm_v_kp": None, "cm_v_stop": None})
    p("Chartmuster: Episodic Pivot mit Ausloeser und getrennt die Luecke ohne erkannten Ausloeser (O16)",
      ms == ["Episodic Pivot am 17.09.2026 nach Quartalszahlen, Lücke 13,3 Prozent, Volumen das 4,0-Fache des "
             "50-Tage-Schnitts, davor 25,4 Prozent unter dem 200-Tage-Hoch und zwei Monate flach oder fallend, "
             "Einstieg über 35,20 Dollar, dem Hoch der ersten fünf Minuten, Stop 33,66 Dollar, tote Phase und "
             "Eröffnungsbereich nach eigener Festlegung"]
      and ms_l == ["Lücke ohne erkannten Auslöser am 17.09.2026, Lücke 13,3 Prozent, Volumen das 4,0-Fache des "
                   "50-Tage-Schnitts, davor 25,4 Prozent unter dem 200-Tage-Hoch und zwei Monate flach oder "
                   "fallend, Einstieg über dem Eröffnungsbereich, ohne Fünf-Minuten-Kurse nicht bestimmbar, tote "
                   "Phase und Eröffnungsbereich nach eigener Festlegung"], " | ".join(ms + ms_l))
    import chartmuster as cm
    erkl = " ".join(chartmuster_erklaerung())
    p("Chartmuster: Erklaerung nennt jede Festlegung mit ihrer Zahl",
      all(x in erkl for x in ("zählen 3 oder 4 enge Wochen, ab 5 nicht mehr", "höchstens 10 Prozent unter",
                              "höchstens 20 Prozent vom Hoch",
                              "höchstens 5 Prozent über", "der 26 Wochen", "mindestens 2-mal so lang",
                              "höchstens 30 Prozent der Tagesspanne", "der 14 Tage davor", "bis 3 Handelstage",
                              "höchstens 3 Prozent", "von 5 Kerzen, 2 davor und 2 danach", "der 63 Handelstage",
                              "mindestens 10 Prozent vom Hoch zum Tief in höchstens 15 Handelstagen",
                              "höchstens 20 Handelstage zurückliegt", "bei 5 und 10 Prozent",
                              "höchstens 52 Wochen nach ihrer Erstnotiz", "mindestens 3 Wochen und ist 20 bis 50",
                              "mindestens 20 Handelstage zwischen 9 und 11 Dollar",
                              "mindestens das 1,4-Fache des Schnitts der 50 Handelstage vor diesem Monat",
                              "nur für Aktien über 10 Dollar", "mindestens 5 Wochen, ist höchstens 35 Prozent tief",
                              "mindestens 20 Prozent gewonnen hat", "Follow-through Day bestätigt hat",
                              "mindestens 63 Handelstage ohne neues Hoch",
                              "Eröffnungslücke von mehr als 10 Prozent", "mindestens dem 3-Fachen",
                              "mindestens 15 Prozent unter ihrem 200-Tage-Hoch", "höchstens 5 Prozent über dem Schluss",
                              "der letzten 10 Handelstage", "der ersten 5 Minuten"))
      and not any(x in erkl for x in ("Double Bottom:", "höchstens 13 Wochen", "höchstens 3 enge Wochen"))
      and len(cm.FESTLEGUNGEN) == 34 and "a_wochen_max" not in cm.FESTLEGUNGEN, erkl[:200])

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
