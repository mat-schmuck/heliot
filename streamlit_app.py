#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CHART-SCREENING-TOOL, Web-Oberflaeche
====================================
Oben "Aktie nachschlagen": Kuerzel oder Name eingeben, dann alle unsere
Zahlen als Text, alle Muster, die Kaufpunkte samt Chart und darunter der
Aktienchart mit Tages-, Monats- oder Jahreskerzen. Darunter die
Registerkarten Liste pruefen, Aktueller Scan, Scanner, Wochenlisten,
Gastzugang, Ablaeufe, Regelwerk und Einstellungen.

Lokal starten:
  pip install -r requirements.txt
  streamlit run streamlit_app.py

Auf Streamlit Community Cloud:
  1. Repo waehlen, Main file: streamlit_app.py
  2. Secrets: TWELVE_DATA_API_KEY ist nur noch Rueckfallebene, Kurse kommen
     von Yahoo.
  3. Anmeldung (Mathias, 13.09.2026, siehe zugang.py): In den Secrets stehen
     HELIOT_PASSWORT, das feste Passwort fuer den vollen Zugang, und
     GAST_GEHEIMNIS, eine lange Zufallszeichenkette fuer die Gastpasswoerter
     und fuer das Angemeldet-Bleiben. Fehlt HELIOT_PASSWORT, bleibt die App
     offen und sagt das oben an.

NACH EINEM PUSH laedt die App ihre eigenen Module selbst neu (frischhalten.py);
ohne das liefe in der Cloud neuer Code mit alten Modulen im Speicher.

KEINE EMOJIS (Mathias, 14.09.2026): weder in Titeln, Registerkarten, Knoepfen
noch in Texten. Beide Nutzer arbeiten mit Screenreader, und jedes Bildzeichen
wird als Wort vorgelesen. Die Gesamtpruefung (Block H) achtet darauf.
"""

import io
import os
import re
import time
from datetime import datetime

import pandas as pd
import streamlit as st

import ablaeufe
import einstellungen
import frischhalten
import listen
import marktampel
import nachschlagen
import oberflaeche
import pattern_scanner as ps
import scanner_ansicht as sa
import zugang

st.set_page_config(page_title="Chart-Screening-Tool", layout="wide")

# EIGENE MODULE FRISCH HALTEN (Befund 17.09.2026): Streamlit Community Cloud
# holt bei einem Push nur den neuen Code und fuehrt dieses Skript neu aus, ohne
# den Python-Prozess neu zu starten. Die importierten eigenen Module bleiben
# dabei in der alten Fassung im Speicher; das Nachschlagen-Feld und der
# Scanner-Reiter brachen deshalb mit "module 'nachschlagen' has no attribute
# 'analysten_zeile'" ab. Die Pruefung kostet je Lauf einen Blick auf die
# Zeitstempel; geladen wird nur, wenn sich wirklich etwas geaendert hat.
_neu_geladen, _lade_fehler = frischhalten.auffrischen(os.path.dirname(os.path.abspath(__file__)),
                                                      ausser=("frischhalten",))
if _neu_geladen:
    # Fuer die Fehlersuche in den Cloud-Protokollen, nicht fuer den Nutzer.
    print("Eigene Module nach einer Aenderung neu geladen: " + ", ".join(_neu_geladen), flush=True)
    # Zwischengespeicherte Werte koennen aus der alten Fassung stammen.
    try:
        st.cache_data.clear()
        st.cache_resource.clear()
    except Exception:
        pass
for _f in _lade_fehler:
    st.error("Eine Programmdatei ließ sich nach der letzten Änderung nicht laden; es gilt weiter der Stand davor.")
    st.caption("Technischer Grund: " + _f)


# ---------------------------------------------------------------------------
# Key + Datenabruf
# ---------------------------------------------------------------------------

def get_api_key() -> str | None:
    """Twelve-Data-Schlüssel — seit der Umstellung auf Yahoo nur noch die
    Rückfallebene. Ohne Schlüssel läuft die App normal weiter."""
    try:
        if "TWELVE_DATA_API_KEY" in st.secrets:
            return st.secrets["TWELVE_DATA_API_KEY"]
    except Exception:
        pass
    return os.environ.get("TWELVE_DATA_API_KEY") or ""


@st.cache_data(ttl=900, show_spinner=False)
def hole_kurse(ticker: str, api_key: str) -> pd.DataFrame:
    """Kurshistorie holen — 15 Minuten gecacht, spart API-Calls.

    Wichtig: Fehlschlaege duerfen NICHT im Zwischenspeicher landen. Frueher
    wurde auch None gecacht — ein einziger Yahoo-Aussetzer (z. B.
    YFRateLimitError auf den geteilten Cloud-IPs) sperrte die Aktie dann fuer
    volle 15 Minuten, obwohl der naechste Versuch laengst klappen wuerde.
    st.cache_data speichert keine Ausnahmen, deshalb wird hier geworfen.

    KEIN TAGES-CACHE (14.09.2026): ps.fetch_history legt je Aktie eine
    CSV-Datei fuer den ganzen Tag an. Die App bekam deshalb nach dem ersten
    Abruf eines Tages bis Mitternacht dieselben Kurse; der Kurs der
    Musterpruefung blieb auf dem Stand des Morgens stehen, waehrend das
    Nachschlagen den Live-Kurs zeigte. Yahoo wird deshalb direkt gefragt;
    fetch_history bleibt die Rueckfallebene ueber Twelve Data."""
    df = ps.yahoo_einzeln(ticker)
    if df is None:
        limiter = ps.RateLimiter(60)  # im Web keine künstliche Bremse nötig
        df = ps.fetch_history(ticker, api_key, limiter)
    if df is None:
        raise LookupError(f"keine Kursdaten für {ticker}")
    return df


def analysiere(ticker: str, api_key: str, rs_wert=None):
    """Kurse holen und alle Muster pruefen.

    RS (Mathias, 14.09.2026): Bis dahin rechnete diese Funktion das RS aus
    einer tanh-Kennlinie selbst, weil die Einzelabfrage keine Vergleichsliste
    hatte, und die Karte zeigte "RS (geschaetzt)". Seit dem 12.09.2026 gibt es
    das echte RS gegen den ganzen US-Markt in rs_universum.json. Der Aufrufer
    uebergibt es (nachschlagen.rs_fuer_muster); ohne RS gilt die
    RS-Bedingung des Trend Templates als nicht erfuellt, geschaetzt wird
    nichts mehr."""
    try:
        df = hole_kurse(ticker, api_key)
    except LookupError:
        return None, None
    df_ind = ps.add_indicators(df)
    res = ps.analyze(df_ind, rs_wert)
    return df_ind, res


@st.cache_data(ttl=900, show_spinner=False)
def muster_fuer(ticker: str, api_key: str, rs_wert):
    """analysiere() mit Zwischenspeicher: Ein Wechsel der Chart-Darstellung
    oder ein zweiter Blick auf dieselbe Aktie rechnet nicht alles neu.
    Ohne Kurse wird geworfen, damit kein Fehlschlag gespeichert wird."""
    df_ind, res = analysiere(ticker, api_key, rs_wert)
    if df_ind is None:
        raise LookupError(f"keine Kursdaten für {ticker}")
    return df_ind, res


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def hole_monatskerzen(ticker: str) -> pd.DataFrame:
    """Monatskerzen der ganzen Historie von Yahoo (gemessen 14.09.2026: AAPL
    501 Monate in 0,1 s, keine doppelten Monate). Fehlschlaege werfen und
    landen deshalb nicht im Zwischenspeicher."""
    import yfinance as yf
    df = yf.Ticker(ticker).history(period="max", interval="1mo", auto_adjust=False, actions=False)
    if df is None or df.empty:
        raise LookupError(f"keine Monatskerzen für {ticker}")
    df = df.reset_index().rename(columns={"Date": "datetime", "Open": "open", "High": "high", "Low": "low",
                                          "Close": "close", "Volume": "volume"})
    zeit = pd.to_datetime(df["datetime"])
    try:
        zeit = zeit.dt.tz_localize(None)
    except (TypeError, AttributeError):
        pass
    df["datetime"] = zeit
    df = df[["datetime", "open", "high", "low", "close", "volume"]].dropna(subset=["open", "high", "low", "close"])
    if df.empty:
        raise LookupError(f"keine Monatskerzen für {ticker}")
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------
# Beide Charts sind fuer Sehende da; alles, was sie zeigen, steht zusaetzlich
# als Text daneben. Die Werkzeugleiste von Plotly ist abgeschaltet: Ihre
# Knoepfe waeren sonst Tabulator-Halte ohne Nutzen fuer Screenreader.

CHART_CONFIG = {"displayModeBar": False}
AKTIENCHART_ARTEN = {"Täglich, zwölf Monate": "tag",
                     "Monatlich, ganze Historie": "monat",
                     "Jährlich, ganze Historie": "jahr"}
DURCHSCHNITTE = (("ma50", "#1e88e5", "50-Tage-Durchschnitt"),
                 ("ma150", "#fb8c00", "150-Tage-Durchschnitt"),
                 ("ma200", "#8e24aa", "200-Tage-Durchschnitt"))


def _plotly():
    try:
        import plotly.graph_objects as go
        return go
    except ImportError:
        st.markdown("Für die Charts fehlt das Paket plotly.")
        return None


def _kerzen_figur(go, k, name, datumsformat="%d.%m.%Y"):
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=k["datetime"], open=k["open"], high=k["high"], low=k["low"],
                                 close=k["close"], name=name,
                                 increasing_line_color="#26a69a", decreasing_line_color="#ef5350"))
    fig.update_xaxes(tickformat=datumsformat, hoverformat=datumsformat)
    return fig


def chart_beschriften(key: str, text: str):
    """Macht den Chart mit dem Streamlit-Schluessel key fuer Screenreader zu
    EINEM Bild mit Beschreibung; das Skript baut nachschlagen.chart_skript."""
    st.html(f"<script>{nachschlagen.chart_skript(key, text)}</script>", unsafe_allow_javascript=True)


def zeichne_kaufpunkt_chart(df: pd.DataFrame, res: dict, ticker: str, tage: int = 180):
    """Tageskerzen der letzten 180 Handelstage mit den Durchschnitten und den
    Kaufpunkten als waagrechte Linien."""
    go = _plotly()
    if go is None or df is None or not res:
        return
    sub = df.iloc[-tage:]
    fig = _kerzen_figur(go, sub, ticker)
    for spalte, farbe, name in DURCHSCHNITTE:
        if spalte in sub and not sub[spalte].isna().all():
            fig.add_trace(go.Scatter(x=sub["datetime"], y=sub[spalte], mode="lines", name=name,
                                     line=dict(width=1.2, color=farbe)))
    farben = ["#2e7d32", "#f9a825", "#d84315"]
    for i, p in enumerate(res.get("points") or []):
        preis = f"{p['kaufpunkt']:.2f}".replace(".", ",")
        fig.add_hline(y=p["kaufpunkt"], line_dash="dash", line_color=farben[i % 3], line_width=1.5,
                      annotation_text=f"KP{i + 1} {preis}: {nachschlagen.anzeige_text(p['strategie'])[:28]}",
                      annotation_position="right", annotation_font=dict(size=10, color=farben[i % 3]))
    fig.update_layout(height=520, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=30, b=10),
                      legend=dict(orientation="h", y=1.02, yanchor="bottom"))
    st.plotly_chart(fig, config=CHART_CONFIG, key="kaufpunkt_chart")
    chart_beschriften("kaufpunkt_chart",
                      f"Chart {ticker}: Tageskerzen der letzten {len(sub)} Handelstage mit dem 50-, 150- und "
                      "200-Tage-Durchschnitt und den Kaufpunkten als waagrechte Linien. Die Werte stehen oben als Text.")


@st.fragment
def aktienchart(ticker: str, df_tag):
    """Der Aktienchart mit Umschaltung zwischen Tages-, Monats- und
    Jahreskerzen. Als Fragment gebaut: Die Umschaltung zeichnet nur diesen
    Teil neu, der Fokus bleibt auf der Auswahl."""
    wahl = st.radio("Darstellung des Aktiencharts", list(AKTIENCHART_ARTEN), horizontal=True,
                    key="aktienchart_art")
    art = AKTIENCHART_ARTEN.get(wahl, "tag")
    if art == "tag":
        k = nachschlagen.kerzen(df_tag.iloc[-252:], "tag") if df_tag is not None else None
    else:
        try:
            monate = hole_monatskerzen(ticker)
        except Exception:  # noqa
            monate = None
        k = nachschlagen.kerzen(monate, art) if monate is not None else None
    if k is None or len(k) == 0:
        st.markdown("Für diese Darstellung kamen keine Kurse von Yahoo; schalte bitte später noch einmal um.")
        return
    go = _plotly()
    if go is not None:
        fig = _kerzen_figur(go, k, ticker, {"tag": "%d.%m.%Y", "monat": "%m.%Y", "jahr": "%Y"}[art])
        if art == "tag":
            sub = df_tag.iloc[-252:]
            for spalte, farbe, name in DURCHSCHNITTE:
                if spalte in sub and not sub[spalte].isna().all():
                    fig.add_trace(go.Scatter(x=sub["datetime"], y=sub[spalte], mode="lines", name=name,
                                             line=dict(width=1.2, color=farbe)))
        fig.update_layout(height=480, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=30, b=10),
                          legend=dict(orientation="h", y=1.02, yanchor="bottom"))
        st.plotly_chart(fig, config=CHART_CONFIG, key=f"aktienchart_{art}")
        was = {"tag": f"Tageskerzen der letzten {len(k)} Handelstage mit dem 50-, 150- und 200-Tage-Durchschnitt",
               "monat": f"{len(k)} Monatskerzen der ganzen Historie",
               "jahr": f"{len(k)} Jahreskerzen der ganzen Historie"}[art]
        chart_beschriften(f"aktienchart_{art}", f"Chart {ticker}: {was}. Die Kerzen stehen darunter als Text.")
    anzahl = {"tag": 20, "monat": 24, "jahr": 100}[art]
    # Ein Kontrollfeld statt st.expander (Antwort 103 vom 24.09.2026): Vor die
    # Beschriftung eines Ausklappers schreibt Streamlit das Symbolwort
    # keyboard_arrow_right, und ein Screenreader liest es vor.
    if st.checkbox("Die Kerzen dieses Charts als Text zeigen, die neueste zuerst", key=f"kerzen_text_{art}"):
        for satz in nachschlagen.kerzen_saetze(k, art, anzahl=anzahl):
            st.markdown(satz)


# ---------------------------------------------------------------------------
# Oberflaeche
# ---------------------------------------------------------------------------

# Das oeffentliche Repo mit Listen, Mappe, Ablaeufen und Einstellungen. Seit dem
# 23.09.2026 ganz oben, weil Aussehen und Marktampel vor allem anderen gelesen
# werden (vorher stand es beim Nachschlagen).
REPO = "mat-schmuck/heliot"

# --- Einstellungen, Aussehen und Toene (Mathias und Gerhard, 23.09.2026) ------
# einstellungen.json im oeffentlichen Repo (einstellungen.py) legt fest, welche
# Alarme ueber ntfy melden; aendern laesst sich das nur im vollen Zugang, im Reiter
# Einstellungen.
# AUSSEHEN UND TON JE PERSON (Antworten 2 und 3 vom 24.09.2026): Jede Person
# waehlt sie fuer sich; gespeichert werden sie im eigenen Browser, ueber dieselbe
# unsichtbare Speicher-Komponente wie das Angemeldet-Bleiben, nur unter eigenem
# Namen (zugang.speicher_js). Gaeste und die Anmeldeseite bekommen die
# Grundeinstellung eines neuen Browsers: Standard-Aussehen, Ton Kristall. Das
# Zukunftsdesign ist reines CSS (oberflaeche.DESIGN_ZUKUNFT): Es aendert weder
# Aufbau noch Text, ein Screenreader liest dasselbe.
@st.cache_data(ttl=60, show_spinner=False)
def _einstellungen_holen() -> dict:
    """Die Einstellungen ueber die oeffentliche Adresse, zum Ansehen ohne vollen
    Zugang; ohne Datei oder ohne Netz gilt die Vorgabe. Der Reiter Einstellungen
    liest im vollen Zugang ueber die GitHub-Schnittstelle und speichert nichts,
    wenn das Lesen scheitert (_einst_api)."""
    import requests
    try:
        r = requests.get(f"https://raw.githubusercontent.com/{REPO}/main/{einstellungen.DATEI}", timeout=10)
    except Exception:  # noqa
        return einstellungen.lesen(None)
    return einstellungen.lesen(r.content if r.status_code == 200 else None)


def _einstellungen() -> dict:
    """Die geltenden Einstellungen. Nach dem Speichern gilt in dieser Sitzung der
    gespeicherte Stand, bis die oeffentliche Adresse ihn auch liefert (sie haelt
    aeltere Staende bis zu fuenf Minuten)."""
    eigen = st.session_state.get("einst_gespeichert")
    if eigen and time.time() - eigen[0] < 330:
        return eigen[1]
    return _einstellungen_holen()


EIGEN_NAME = "heliot_eigen"          # Name im Browserspeicher fuer Aussehen und Ton
EIGEN_SCHLUESSEL = "eigen_speicher"
_eigen_speicher = st.components.v2.component("heliot_eigen", js=zugang.speicher_js(EIGEN_NAME))


def _eigen_gemeldet():
    """Rueckruf der Komponente: Der Browser hat gemeldet, was er fuer Aussehen und
    Ton gespeichert hat."""
    stand = st.session_state.get(EIGEN_SCHLUESSEL) or {}
    st.session_state["eigen_gemeldet"] = stand.get("wert") or ""


def _eigen_binden():
    """Bindet die Speicher-Komponente genau einmal je Lauf ein: Steht eine neue
    Wahl zum Speichern an (_einst_speichern), schreibt sie diese, sonst liest sie."""
    neu = st.session_state.pop("eigen_setzen", None)
    if neu:
        st.session_state["eigen_gemeldet"] = neu
        daten = zugang.speicher_daten("setzen", neu)
    else:
        daten = zugang.speicher_daten("lesen", bekannt=st.session_state.get("eigen_gemeldet"))
    _eigen_speicher(key=EIGEN_SCHLUESSEL, data=daten, on_wert_change=_eigen_gemeldet,
                    on_gespeichert_change=lambda: None)


def _eigen() -> tuple:
    """(Aussehen, Ton), wie dieser Browser sie gespeichert hat; Gaeste bekommen
    immer die Grundeinstellung (Antwort 3)."""
    if globals().get("rolle") == "gast":
        return einstellungen.DESIGN_VORGABE, einstellungen.KLANG_VORGABE
    return einstellungen.eigen_lesen(st.session_state.get("eigen_gemeldet"))


def _eigen_modell_nachziehen():
    """Meldet der Browser Aussehen und Ton erst, nachdem der Reiter Einstellungen
    seine Wahl schon aufgebaut hat, zieht die Wahl nach, solange dort nichts
    geaendert ist; eine geaenderte Wahl bleibt stehen."""
    modell = st.session_state.get("einst_modell")
    if not isinstance(modell, dict):
        return
    jetzt = st.session_state.get("eigen_gemeldet") or ""
    von = modell.get("eigen_von") or ""
    if von == jetzt:
        return
    alt_design, alt_ton = einstellungen.eigen_lesen(von)
    if modell.get("design") == alt_design and modell.get("klang") == alt_ton:
        modell["design"], modell["klang"] = einstellungen.eigen_lesen(jetzt)
    modell["eigen_von"] = jetzt


def _design() -> str:
    """Das Aussehen dieses Laufs. Hat der Reiter Einstellungen schon einmal
    gezeichnet, gilt seine Wahl, gespeichert oder nicht (Vorschau in diesem
    Browser); sonst das gespeicherte."""
    _eigen_modell_nachziehen()
    modell = st.session_state.get("einst_modell")
    if globals().get("rolle") != "gast" and isinstance(modell, dict) and modell.get("design"):
        return modell["design"]
    return _eigen()[0]


_klang_komponente = st.components.v2.component("heliot_klang", js=oberflaeche.KLANG_JS)


def klang(kennung: str | None = None, name: str | None = None):
    """Den gewaehlten Erfolgston spielen, je Ereignis genau einmal (Mathias und
    Gerhard, 23.09.2026: "Baue Sounds ein, die das erfolgreiche Durchfuehren einer
    Aktion anzeigen"). Die Kennung merkt sich der Browser: Wird dieselbe Meldung
    beim naechsten Lauf wieder gezeichnet, bleibt es still. Ohne Kennung ist es
    ein neues Ereignis."""
    name = name or _eigen()[1]
    if name == "aus":
        return
    kennung = str(kennung or time.time_ns())
    _klang_komponente(key=f"heliot_klang_{kennung}", data={"id": kennung, "klang": name})


def erfolg(text: str, kennung: str | None = None):
    """Eine Erfolgsmeldung samt Ton."""
    st.success(text)
    klang(kennung)


def technik_zeile(text) -> str:
    """Ein technischer Grund als kleine Zeile (Antwort 102 vom 24.09.2026)."""
    t = str(text or "").strip()
    return t if t.startswith(nachschlagen.TECHNIK) else nachschlagen.TECHNIK + t


def fehler(text: str, technik=None, kennung: str | None = None):
    """Eine Fehlermeldung (Antworten 5 und 102 vom 24.09.2026): oben ein einfacher
    Satz, was nicht geht und was zu tun ist, der technische Grund klein darunter,
    dazu der feste tiefe Fehlerton, je Ereignis einmal. Er spielt auch, wenn als
    Erfolgston Kein Ton gewaehlt ist. Eine Meldung, die bei jedem Lauf wieder
    dasteht, braucht eine feste Kennung, sonst spielte der Ton bei jedem Lauf."""
    st.error(text)
    if technik:
        st.caption(technik_zeile(technik))
    klang(kennung, name="fehler")


def saetze_zeigen(saetze):
    """Saetze als Absaetze; ein technischer Grund steht klein darunter."""
    for satz in saetze:
        if str(satz).startswith(nachschlagen.TECHNIK):
            st.caption(satz)
        else:
            st.markdown(satz)


def erklaerung_umschalten(k: str, sichtbar: bool):
    st.session_state[k] = not sichtbar


def zeit_wien(zeitpunkt: float) -> str:
    """'25.09.2026 um 15:30 Uhr Wiener Zeit': Tag, Monat, Jahr und Wiener Zeit
    (Antwort 99 vom 24.09.2026)."""
    try:
        from zoneinfo import ZoneInfo
        w = datetime.fromtimestamp(zeitpunkt, ZoneInfo("Europe/Vienna"))
    except Exception:  # noqa
        w = datetime.fromtimestamp(zeitpunkt)
    return f"{w:%d.%m.%Y} um {w:%H:%M} Uhr Wiener Zeit"


# Die Komponenten fuer Toene und Browserspeicher zeichnen nichts; ihr Platz wird
# ausgeblendet, damit sie keine Luecke in die Seite reissen.
st.html("<style>" + oberflaeche.AMPEL_CSS
        + "[class*='st-key-heliot_klang'],[class*='st-key-eigen_speicher']{display:none}</style>")
# Die Wache fuer die Toene: Sie gibt den Ton im Browser beim ersten Klick oder
# Tastendruck frei; ohne diese Freigabe bliebe es auf dem iPhone still.
_klang_komponente(key="heliot_klang_wache", data={"id": "", "klang": "aus"})
_eigen_binden()

# DER NAME DER APP bleibt Chart-Screening-Tool; der Untertitel mit einer Auswahl
# der Muster ist entfallen (Antworten 21 und 22 vom 24.09.2026).
st.title("Chart-Screening-Tool")


# DIE MARKTAMPEL (Mathias und Gerhard, 23.09.2026): "Die Marktampel muss auf jeder
# Seite des gesamten Streamlit-Tools ersichtlich sein, sie muss ganz oben, auch auf
# der Einstellungs-Seite." Der Platz steht vor der Anmeldung; gefuellt wird er erst
# danach, denn ohne Anmeldung ist nichts zu sehen (Mathias, 13.09.2026). Die Worte
# sind die der ersten Meldung des Waechters (oberflaeche.ampel_saetze).
@st.cache_data(ttl=120, show_spinner=False)
def _ampel_holen():
    import json
    import requests
    try:
        r = requests.get(f"https://raw.githubusercontent.com/{REPO}/main/marktampel.json", timeout=10)
        if r.status_code == 200:
            return json.loads(r.content.decode("utf-8-sig"))
    except Exception:  # noqa
        pass
    return None


@st.cache_data(ttl=600, show_spinner=False)
def _nachtscan_tag_holen() -> str:
    """Der letzte Handelstag, den der Nachtscan gerechnet hat (Antwort 10 vom
    24.09.2026), aus der Sektor-Rangliste desselben Laufs; ohne sie gilt die
    Rechnung nach Wochentagen."""
    try:
        return str((nachschlagen.lade_datei("sektor_rangliste.json") or {}).get("handelstag") or "")[:10]
    except Exception:  # noqa
        return ""


def _ampel_zeigen():
    farbe, kopf, satz = oberflaeche.ampel_saetze(_ampel_holen(), sa.ny_jetzt(),
                                                 nachtscan_tag=_nachtscan_tag_holen() or None)
    st.html(oberflaeche.ampel_html(farbe, kopf, satz))


_ampel_platz = st.empty()

# --- Anmeldung (Mathias, 13.09.2026) ----------------------------------------
# Vor allem anderen: Ohne Anmeldung ist nichts zu sehen. Das feste Passwort
# (Secret HELIOT_PASSWORT) oeffnet alles. Ein Gastpasswort, errechnet aus
# GAST_GEHEIMNIS (zugang.py), oeffnet 60 bis 70 Minuten lang nur zum Lesen:
# Aktie nachschlagen, Liste pruefen, Aktueller Scan und Regelwerk. Die
# Wochenliste mit ihrem Schreibzugriff und die Seite fuer Gastpasswoerter
# werden fuer Gaeste gar nicht gebaut, siehe "Ab hier nur mit vollem Zugang"
# weiter unten.
#
# ANGEMELDET BLEIBEN (Mathias, 14.09.2026): Streamlit merkt die Anmeldung nur
# je Browsersitzung. Mit dem Haken "Angemeldet bleiben" legt die App einen
# Eintrag im Speicher des Browsers ab (zugang.py, Abschnitt ANGEMELDET
# BLEIBEN). Lesen, Schreiben und Loeschen erledigt eine unsichtbare
# Komponente im Browser (zugang.speicher_js); sie meldet den Eintrag beim
# ersten Lauf einer Sitzung an die App. Ein Cookie ueber st.context.cookies
# ging nur lokal: Streamlit Community Cloud reicht es nicht an die App durch
# (gemessen 14.09.2026). Bis die Meldung da ist, steht das Anmeldefeld; ein
# gueltiger Eintrag meldet einen Augenblick spaeter an. Scheitert die
# Komponente, bleibt so immer die Anmeldung von Hand.
#
# UEBERGANG: Solange HELIOT_PASSWORT in den Secrets fehlt, bleibt die App
# offen wie bisher und sagt das oben an, damit ein Upload vor dem Eintragen
# niemanden aussperrt. Lassen sich die Secrets gar nicht lesen, bleibt sie zu.


def _secret(name: str):
    """Wert eines Secrets als Text: "" wenn es fehlt, None wenn die Secrets
    sich nicht lesen lassen oder der Eintrag kein einfacher Wert ist."""
    try:
        wert = st.secrets.get(name, "")
    except Exception:
        return None
    if wert is None:
        return ""
    if isinstance(wert, (str, int, float)) and not isinstance(wert, bool):
        return str(wert)
    return None


def _daten_token() -> str:
    """Der Token fuer das private Datenrepo heliot-daten (Mathias, 21.09.2026):
    DATEN_TOKEN darf genau dieses Repo lesen und beschreiben; der aeltere
    DATEN_LESE_TOKEN gilt als Rueckfall weiter. Nur der volle Zugang bekommt
    ihn (Gerhard, 20.09.2026, S4: "Der Gastzugang darf keinen Zugriff auf die
    GitHub-Anbindung in Streamlit bekommen"); Gaeste und die offene
    Uebergangsseite ohne Passwort sehen nichts aus dem privaten Datenrepo."""
    if globals().get("rolle") != "voll":
        return ""
    return ((_secret("DATEN_TOKEN") or "").strip()
            or (_secret("DATEN_LESE_TOKEN") or "").strip())


def _ablauf_token() -> str:
    """Der Token fuer die Knoepfe im Reiter Ablaeufe (Mathias, 21.09.2026, zu
    Gerhards S8): ABLAUF_TOKEN darf nur Ablaeufe im Repo heliot lesen und
    starten. Nur der volle Zugang bekommt ihn."""
    if globals().get("rolle") != "voll":
        return ""
    return (_secret("ABLAUF_TOKEN") or "").strip()


@st.cache_resource(show_spinner=False)
def _anmelde_bremse():
    """Eine Bremse fuer alle Sitzungen dieses App-Prozesses, siehe zugang.Bremse."""
    return zugang.Bremse()


def _abmelden():
    for schluessel in ("zugang", "zugang_fehl", "zugang_pause_bis", "gast_erzeugt",
                       "bleiben_wert", "bleiben_ende"):
        st.session_state.pop(schluessel, None)


def _abmelden_knopf():
    """Abmelden vergisst die Anmeldung dieser Sitzung und loescht beim
    naechsten Lauf das Cookie fuer das Angemeldet-Bleiben."""
    _abmelden()
    st.session_state["bleiben_loeschen"] = True


# Die Komponente wird bei jedem Lauf mit derselben Definition registriert;
# Streamlit warnt nur, wenn sich die Definition unterscheidet.
_bleiben_speicher = st.components.v2.component("heliot_bleiben", js=zugang.speicher_js())
BLEIBEN_SCHLUESSEL = "bleiben_speicher"


def _bleiben_gemeldet():
    """Rueckruf der Komponente: Der Browser hat gemeldet, was er gespeichert hat."""
    stand = st.session_state.get(BLEIBEN_SCHLUESSEL) or {}
    st.session_state["bleiben_gemeldet"] = stand.get("wert") or ""


def _speicher(auftrag: str, wert: str = ""):
    """Bindet die Speicher-Komponente ein, genau einmal je Lauf. Nach dem
    Setzen oder Loeschen kennt die App den Eintrag schon; ein spaeteres
    Lesen in derselben Sitzung loest deshalb keinen neuen Lauf aus."""
    if auftrag in ("setzen", "loeschen"):
        st.session_state["bleiben_gemeldet"] = wert if auftrag == "setzen" else ""
    _bleiben_speicher(key=BLEIBEN_SCHLUESSEL,
                      data=zugang.speicher_daten(auftrag, wert, st.session_state.get("bleiben_gemeldet")),
                      on_wert_change=_bleiben_gemeldet, on_gespeichert_change=lambda: None)


def _datum_wien(zeitpunkt: float) -> str:
    try:
        from zoneinfo import ZoneInfo
        return datetime.fromtimestamp(zeitpunkt, ZoneInfo("Europe/Vienna")).strftime("%d.%m.%Y")
    except Exception:  # noqa
        return datetime.fromtimestamp(zeitpunkt).strftime("%d.%m.%Y")


def anmeldung() -> str:
    """Liefert "voll", "gast" oder "offen". Ohne gueltige Anmeldung zeigt sie
    das Anmeldefeld und beendet den Lauf der Seite."""
    passwort = _secret("HELIOT_PASSWORT")
    if passwort is None:
        fehler("Die Anmeldung ist gerade nicht möglich.",
               "Die Streamlit-Secrets lassen sich nicht lesen; prüfe sie in den Einstellungen der App bei Streamlit.",
               kennung="secrets_unlesbar")
        st.stop()
    if not passwort.strip():
        st.warning("Der Zugangsschutz ist noch nicht eingerichtet; bis dahin ist die App ohne Anmeldung offen.")
        st.caption(technik_zeile("In den Streamlit-Secrets fehlt HELIOT_PASSWORT."))
        return "offen"
    geheimnis = _secret("GAST_GEHEIMNIS") or ""
    jetzt = time.time()

    # Abgemeldet: den Eintrag im Browser loeschen, und in dieser Sitzung
    # meldet ein gespeicherter Eintrag nicht wieder an.
    auftrag = "lesen"
    if st.session_state.pop("bleiben_loeschen", False):
        st.session_state["bleiben_verworfen"] = True
        auftrag = "loeschen"

    stand = st.session_state.get("zugang")
    if stand and stand.get("rolle") == "gast" and jetzt >= float(stand.get("bis") or 0):
        _abmelden()
        st.session_state["zugang_hinweis"] = f"Der Gastzugang ist am {zeit_wien(stand['bis'])} abgelaufen."
        st.session_state["bleiben_verworfen"] = True
        auftrag = "loeschen"
        stand = None

    # Angemeldet bleiben: ein gueltiger Eintrag meldet an. Ein ungueltiger oder
    # abgelaufener wird geloescht und zaehlt nicht als Fehlversuch. Gemeldet
    # hat ihn die Komponente (_bleiben_gemeldet); vor der ersten Meldung
    # steht dort nichts, dann liest sie weiter unten.
    if not stand and not st.session_state.get("bleiben_verworfen"):
        wert = st.session_state.get("bleiben_gemeldet")
        if wert:
            rolle_c, ende_c = zugang.bleiben_pruefen(wert, passwort, geheimnis, jetzt)
            if rolle_c:
                st.session_state["zugang"] = {"rolle": rolle_c, "bleiben": True,
                                              "bis": ende_c if rolle_c == "gast" else None}
                stand = st.session_state["zugang"]
            else:
                st.session_state["bleiben_verworfen"] = True
                auftrag = "loeschen"
    elif auftrag == "lesen":
        auftrag = "ruhe"

    if stand:
        if stand.get("bleiben") and zugang.bleiben_moeglich(passwort, geheimnis):
            # Jede Sitzung stellt den Eintrag neu aus: 30 Tage ab dem letzten
            # Oeffnen, ein Gast bis zum Ablauf seines Passworts.
            if not st.session_state.get("bleiben_wert"):
                ende = zugang.bleiben_ende(stand["rolle"], stand.get("bis"), jetzt)
                st.session_state["bleiben_wert"] = zugang.bleiben_ausstellen(
                    stand["rolle"], ende, passwort, geheimnis)
                st.session_state["bleiben_ende"] = ende
            _speicher("setzen", st.session_state["bleiben_wert"])
        else:
            _speicher("loeschen" if auftrag == "loeschen" else "ruhe")
        return stand["rolle"]

    _speicher(auftrag)
    st.markdown("## Anmeldung", anchors=False)
    hinweis = st.session_state.pop("zugang_hinweis", "")
    if hinweis:
        st.info(hinweis)
    bleiben_geht = zugang.bleiben_moeglich(passwort, geheimnis)
    # Das Augensymbol im Passwortfeld heisst Passwort zeigen oder Passwort
    # verbergen (Antwort 28 vom 24.09.2026); das Skript steht in oberflaeche.py.
    st.html("<script>" + oberflaeche.PASSWORT_AUGE_JS + "</script>", unsafe_allow_javascript=True)
    with st.form("anmeldung", clear_on_submit=True):
        eingabe = st.text_input("Passwort oder Gastpasswort", type="password")
        bleiben = False
        if bleiben_geht:
            bleiben = st.checkbox("Angemeldet bleiben, in diesem Browser 30 Tage ab dem letzten Öffnen",
                                  value=True)
        senden = st.form_submit_button("Anmelden", type="primary")
    if bleiben_geht:
        st.caption("Mit Gastpasswort bleibt der Browser nur so lange angemeldet, wie das Gastpasswort gilt. "
                   "Auf fremden Geräten entferne bitte den Haken. Safari auf dem iPhone vergisst die "
                   "Anmeldung, wenn die App sieben Tage lang nicht geöffnet wurde.")
    if senden:
        bremse = _anmelde_bremse()
        gesperrt = bremse.gesperrt_bis(jetzt)
        pause = float(st.session_state.get("zugang_pause_bis") or 0)
        if not (eingabe or "").strip():
            fehler("Gib bitte ein Passwort ein.")
        elif gesperrt:
            fehler("Zu viele Fehlversuche in den letzten zehn Minuten. Die Anmeldung "
                   f"ist bis {zeit_wien(gesperrt)} gesperrt.")
        elif jetzt < pause:
            fehler("Fünf Fehlversuche hintereinander. Warte bitte eine Minute und versuche es dann erneut.")
        else:
            rolle_neu, bis = zugang.anmelden(eingabe, passwort, geheimnis, jetzt)
            if rolle_neu:
                _abmelden()
                st.session_state.pop("bleiben_verworfen", None)
                st.session_state["zugang"] = {"rolle": rolle_neu, "bis": bis,
                                              "bleiben": bool(bleiben and bleiben_geht)}
                st.session_state["klang_anmeldung"] = str(time.time_ns())
                st.rerun()
            anzahl = bremse.fehlversuch(jetzt)
            zaehler, pause_bis = zugang.sitzung_nach_fehlversuch(
                int(st.session_state.get("zugang_fehl") or 0), jetzt)
            st.session_state["zugang_fehl"] = zaehler
            if pause_bis:
                st.session_state["zugang_pause_bis"] = pause_bis
                fehler("Das Passwort stimmt nicht. Das war der fünfte Fehlversuch hintereinander; warte bitte eine "
                       "Minute.")
            else:
                fehler("Das Passwort stimmt nicht.")
            if anzahl >= zugang.GESAMT_GRENZE:
                print(f"Anmeldung: {anzahl} Fehlversuche in zehn Minuten, Sperre aktiv")
    st.stop()


rolle = anmeldung()
with _ampel_platz.container():
    _ampel_zeigen()
# Das Zukunftsdesign erst nach der Anmeldung: Die Anmeldeseite und Gaeste sehen
# die Grundeinstellung eines neuen Browsers (Antwort 3 vom 24.09.2026).
if _design() == "zukunft":
    st.html("<style>" + oberflaeche.DESIGN_ZUKUNFT + "</style>")
if st.session_state.get("klang_anmeldung"):
    klang(st.session_state.pop("klang_anmeldung"))
if rolle in ("voll", "gast"):
    stand_anzeige = st.session_state.get("zugang") or {}
    if rolle == "gast":
        zeile = f"Gastzugang zum Lesen, gültig bis {zeit_wien(stand_anzeige['bis'])}."
    else:
        zeile = "Angemeldet mit vollem Zugang."
    if stand_anzeige.get("bleiben") and st.session_state.get("bleiben_ende"):
        if (st.session_state.get(BLEIBEN_SCHLUESSEL) or {}).get("gespeichert") is False:
            zeile += (" Dieser Browser lässt die App die Anmeldung nicht speichern; beim nächsten "
                      "Öffnen ist das Passwort wieder einzugeben.")
        elif rolle == "gast":
            zeile += " Dieser Browser bleibt bis zum Ablauf angemeldet."
        else:
            # Antwort 23 vom 24.09.2026
            zeile = ("Angemeldet mit vollem Zugang; dieser Browser bleibt angemeldet bis "
                     f"{_datum_wien(st.session_state['bleiben_ende'])}, jedes Öffnen verlängert um 30 Tage.")
    st.write(zeile)


def abmelden_zeigen():
    """Der Abmelden-Knopf am Seitenende (Antwort 25 vom 24.09.2026): Wer mit dem
    Tabulator durch die Seite geht, kommt nicht mehr bei jedem Besuch zuerst an
    ihm vorbei."""
    if rolle in ("voll", "gast"):
        st.markdown("---")
        st.button("Abmelden", key="abmelden", on_click=_abmelden_knopf)


# Kursdaten kommen seit der Umstellung von Yahoo und brauchen keinen
# Schlüssel. Twelve Data ist nur noch Rückfallebene — die App startet
# deshalb auch ohne. Früher stand hier st.stop(), was den Start ganz
# verhindert hätte. Der Hinweis dazu steht seit dem 24.09.2026 im Regelwerk
# unter den Grenzen (Antwort 24).
api_key = get_api_key()


# --- Aktie nachschlagen (Mathias, 13.09.2026) -----------------------------
# GANZ OBEN, vor den Registerkarten: das Suchfeld, darunter alles als Text
# in eigenen Absaetzen mit Zwischenueberschriften, damit VoiceOver am
# iPhone von Ueberschrift zu Ueberschrift springen kann. Keine Tabellen,
# keine Spalten, keine Kennzahlkaesten. Die Zahlen kommen aus den
# Nachtdateien im Repo (RS, Ratings, Sektor-Rangliste, Volumenkurven) und
# live von Yahoo (Kurs, Volumen); gerechnet wird in nachschlagen.py, das
# ohne Netz pruefbar ist.


# DIE ANALYSTENWERTE DES SCANNERS (Mathias, 14.09.2026) liest seit Etappe 5
# auch das Nachschlagen (Gerhard, 13.09.2026, Entscheidung 9: Konsens,
# Forward-KGV, erwartetes Wachstum, Revisionen der Wochenliste); deshalb
# stehen die Lesefunktionen hier vor dem Suchfeld und nicht beim Scanner.
DATEN_REPO = "mat-schmuck/heliot-daten"
# Das oeffentliche Repo REPO steht seit dem 23.09.2026 ganz oben bei der Oberflaeche.
@st.cache_data(ttl=600, show_spinner=False)
def _scanner_analysten_holen():
    """Die Analystenwerte liegen im PRIVATEN Datenrepo (wie der eingefrorene
    Konsens, F17). Gelesen wird mit DATEN_TOKEN aus den Streamlit-Secrets,
    einem Token nur fuer dieses eine Repo (siehe _daten_token); der Wert
    erscheint in keiner Meldung. Fehlschlaege werfen und landen nicht im
    Speicher. Aufgerufen wird nur ueber lade_scanner_analysten, das Gaeste
    vorher abweist: Der Zwischenspeicher gilt fuer alle Besucher."""
    import requests
    token = _daten_token()
    if not token:
        raise LookupError("kein Token für das Datenrepo")
    kopf = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    r = requests.get(f"https://api.github.com/repos/{DATEN_REPO}/releases/tags/scanner-daten",
                     headers=kopf, timeout=20)
    if r.status_code != 200:
        raise LookupError(f"GitHub antwortete mit Code {r.status_code}")
    anhang = next((a for a in (r.json().get("assets") or []) if a.get("name") == "scanner_analysten.parquet"), None)
    if not anhang:
        raise LookupError("noch keine Analystendatei")
    d = requests.get(anhang["url"], headers={**kopf, "Accept": "application/octet-stream"}, timeout=60)
    if d.status_code != 200:
        raise LookupError(f"GitHub antwortete mit Code {d.status_code}")
    return pd.read_parquet(io.BytesIO(d.content))


def lade_scanner_analysten():
    # S4: Die Rolle wird VOR dem Zwischenspeicher geprueft, sonst bekaeme ein
    # Gast die Tabelle, die ein voll angemeldeter Besucher geladen hat.
    if globals().get("rolle") != "voll":
        return None, nachschlagen.NUR_VOLLER_ZUGANG
    try:
        return _scanner_analysten_holen(), ""
    except LookupError as e:
        return None, str(e)
    except Exception as e:  # noqa
        return None, f"Netzwerkfehler {type(e).__name__}"


SCANNER_RELEASE = f"https://github.com/{REPO}/releases/download/scanner-daten/"


@st.cache_data(ttl=600, show_spinner=False)
def _scanner_tabelle_holen():
    """Die Nachttabelle aus dem Release. Fehlschlaege werfen und landen
    deshalb nicht im Zwischenspeicher."""
    import requests
    r = requests.get(SCANNER_RELEASE + "scanner_tabelle.parquet", timeout=60)
    if r.status_code != 200:
        raise LookupError(f"GitHub antwortete mit Code {r.status_code}")
    return pd.read_parquet(io.BytesIO(r.content))


def lade_scanner_tabelle():
    """(Tabelle oder None, Grund); ohne Release die Datei im Ordner."""
    try:
        return _scanner_tabelle_holen(), ""
    except LookupError as e:
        grund = str(e)
    except Exception as e:  # noqa
        grund = f"Netzwerkfehler {type(e).__name__}"
    if os.path.exists("scanner_tabelle.parquet"):
        try:
            return pd.read_parquet("scanner_tabelle.parquet"), ""
        except Exception:  # noqa
            pass
    return None, grund


@st.cache_data(ttl=600, show_spinner=False)
def nachschlag_dateien():
    return {n: nachschlagen.lade_datei(n) for n in nachschlagen.DATEIEN}


@st.cache_data(ttl=60, show_spinner=False)
def nachschlag_live(ticker: str):
    return nachschlagen.live_daten(ticker)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def nachschlag_kurve(ticker: str):
    return nachschlagen.kurve_fuer(ticker, nachschlag_dateien().get("volumenkurven.json"))


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def nachschlag_sektor(ticker: str):
    return nachschlagen.sektor_name_fuer(ticker)


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def nachschlag_stichtagkurs(ticker: str, stichtag: str):
    # Etappe 4, Punkt 11: der Schlusskurs am Stichtag des Streubesitzes, fuer
    # die Zahl der Aktien im Streubesitz
    return nachschlagen.kurs_am(ticker, stichtag)


# --- Wochenliste -----------------------------------------------------------
# Die Definitionen stehen seit dem 21.09.2026 vor dem Scanner, weil auch die
# Uebergabe aus dem Scanner (Gerhard, 20.09.2026, S2) sie braucht, und seit dem
# Abend desselben Tages vor dem Nachschlagen, weil der Knopf zum einzeln
# Ueberwachen (S7) sie beim Klick braucht: Streamlit fuehrt das Skript von oben
# nach unten aus. Die Seite zum Hochladen selbst steht weiter hinter der
# Schranke fuer Gaeste.
#
# Gerhard siebt jede Woche den Markt mit seinem Finviz-Screener und liefert
# eine CSV mit der Spalte 'Ticker' (bestätigt am 22.07.2026: immer CSV, nie
# Excel). Diese Seite legt die Datei als finviz_3.csv ins Repo; ab dem
# nächsten nächtlichen Scan arbeitet die Automatik damit.
# OHNE KENNWORT (Mathias, 13.09.2026): Bis dahin verlangte die Seite das
# Streamlit-Secret UPLOAD_KENNWORT; das ist herausgenommen, weil niemand
# wusste, welches Kennwort gemeint war. Geschrieben wird weiter über den
# GitHub-Token (GITHUB_TOKEN), der NUR auf dieses Repo und NUR auf
# Dateiinhalte berechtigt ist. Seit der Anmeldung vom selben Abend gibt es
# diese Seite nur mit dem festen Passwort (HELIOT_PASSWORT); Gaeste sehen sie
# nicht. Solange das Passwort nicht eingerichtet ist, bleibt sie offen, und
# die einzige Schranke ist pruefe_wochenliste (CSV mit Spalte Ticker,
# plausible Kuerzel).

LISTEN_DATEI = "finviz_3.csv"     # REPO steht oben bei DATEN_REPO
DARVAS_DATEI = "darvas.csv"

# JEDER ZWEIG, DER EINE WOCHENLISTE FUEHRT (Mathias, 08.09.2026).
# main ist der Standardzweig, von dem Nachtscan und Waechter laufen;
# fundament-phase1 ist der Arbeitszweig, auf dem messung_8k.py die
# Listen ueber dasselbe Modul listen.py liest.
#
# WOZU: Bis dahin schrieb der Upload OHNE Angabe eines Zweigs, und
# GitHub legt das auf dem Standardzweig ab. Auf jedem anderen Zweig
# blieb die alte Liste liegen, ohne dass irgendwo etwas gemeldet worden
# waere. Ein Lauf, der von dort gestartet wird, haette still die
# falschen Aktien gescannt, und genau das faellt niemandem auf.
#
# SICHERUNGSZWEIGE GEHOEREN NICHT HIERHER: stand-vor-umbau soll den
# alten Stand bewahren, nicht mitwandern. Wer einen neuen Arbeitszweig
# anlegt, traegt ihn hier ein. Vergisst er es, meldet es die
# Gesamtpruefung (Block H, "Jeder Zweig mit Wochenliste steht in
# LISTEN_ZWEIGE"): Sie zaehlt die Zweige auf origin seit 10.09.2026 selbst
# auf und nimmt nur Sicherungszweige aus, deren Name mit stand-, sicherung
# oder backup beginnt. Bis dahin stand dort dieselbe feste Liste wie hier,
# und einen dritten Zweig haette sie gar nicht gesehen.
LISTEN_ZWEIGE = ("main", "fundament-phase1")

# ZWEI LISTEN seit 14.08.2026 (Gerhard): "Die Darvas-Tradingstrategie
# bekommt eine eigene Liste. Das Tradingmuster Darvas soll in Zukunft
# ausschliesslich auf diese Liste angewandt werden. Die Darvasliste soll
# fuer die anderen Strategien herangezogen werden, jedoch nicht
# umgekehrt." Beide werden getrennt abgelegt und getrennt ersetzt - wer
# nur eine hochlaedt, laesst die andere unveraendert stehen.
#
# WELCHE IST WELCHE: Gerhard nennt die eine "Darvers"/"Darvas", die
# andere "finviz.csv oder aehnlich". Der Dateiname entscheidet also
# vor, ABER die Seite sagt vorher an, wohin sie geht, und die Wahl
# laesst sich umstellen - ein stiller Griff in die falsche Liste waere
# der teuerste Fehler dieser Seite.


def liste_aus_dateiname(name: str) -> str:
    """Welche Liste ist gemeint? Rueckgabe: DARVAS_DATEI oder LISTEN_DATEI.

    ACHTUNG BEI DER SCHREIBWEISE: Der Name kommt mit drei Varianten
    vorbei. Gerhard schreibt "Darvers", die Datei vom 15.08.2026 hiess
    "darwas", das Muster selbst heisst Darvas. Eine Suche nach "darv"
    allein haette "darwas" NICHT erkannt und die Darvas-Liste
    stillschweigend in die grosse Liste geschrieben - genau der
    Fehlgriff, gegen den diese Seite die Wahl sichtbar anzeigt.
    Erkannt wird deshalb "dar" plus v ODER w."""
    import re
    return (DARVAS_DATEI if re.search(r"dar[vw]", (name or "").lower())
            else LISTEN_DATEI)


def pruefe_wochenliste(rohdaten: bytes) -> tuple[str, list[str]]:
    """Prüft die Datei GRÜNDLICH, bevor irgendetwas ins Repo geschrieben
    wird — ein Tippfehler beim Hochladen darf nicht die nächtliche
    Scan-Grundlage zerstören. Liefert (Fehlertext, Tickerliste)."""
    try:
        df = pd.read_csv(io.BytesIO(rohdaten))
    except Exception as e:
        return f"Die Datei ließ sich nicht als CSV lesen ({e}).", []
    spalte = next((c for c in df.columns if c.strip().lower() == "ticker"), None)
    if spalte is None:
        return "Keine Spalte Ticker gefunden. Ist das wirklich der Finviz-Export?", []
    ticker = [str(t).strip().upper() for t in df[spalte].dropna() if str(t).strip()]
    ticker = list(dict.fromkeys(ticker))
    if not ticker:
        return "Die Ticker-Spalte ist leer.", []
    if len(ticker) > 1500:
        # Grenze am 25.07.2026 von 500 auf 1500 erhoeht: Gerhards
        # Wochenexport umfasst inzwischen ~780 Aktien.
        return f"{len(ticker)} Ticker sind verdächtig viele (erwartet: bis 1500).", []
    muster = re.compile(r"^[A-Z0-9.\-]{1,10}$")
    komisch = [t for t in ticker if not muster.match(t)]
    if komisch:
        return "Unplausible Einträge in der Ticker-Spalte: " + ", ".join(komisch[:5]), []
    return "", ticker


def wochenliste_einspielen(rohdaten: bytes, token: str, anzahl: int,
                           ziel: str = None, herkunft: str = "Upload über Heliot") -> tuple:
    """Ersetzt die Zielliste auf JEDEM Zweig, der sie fuehrt.

    Liefert (fehler, geschrieben): fehler ist leer, wenn alles geklappt
    hat, geschrieben nennt die Zweige, auf denen die Liste jetzt steht.

    DREI FAELLE, und alle drei werden dem Nutzer gesagt:
      * Ein Zweig fuehrt die Datei gar nicht (GET liefert 404): Er wird
        uebersprungen und gilt NICHT als Fehler. Die Liste wird dort
        auch nicht angelegt, denn wer sie nicht fuehrt, braucht sie
        nicht.
      * Ein Zweig scheitert: Er wird beim Namen genannt, und was schon
        geschrieben wurde, steht trotzdem in der Rueckgabe. Niemand soll
        glauben, es sei nichts passiert, wenn die halbe Arbeit getan ist.
      * Kein einziger Zweig hat es genommen: harter Fehler.
    """
    import base64
    import requests
    kopf = {"Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json"}
    ziel = ziel or LISTEN_DATEI
    url = f"https://api.github.com/repos/{REPO}/contents/{ziel}"
    inhalt = base64.b64encode(rohdaten).decode()
    geschrieben, gescheitert = [], []
    for zweig in LISTEN_ZWEIGE:
        try:
            alt = requests.get(url, headers=kopf, timeout=20,
                               params={"ref": zweig})
            if alt.status_code == 404:
                continue          # Zweig oder Datei gibt es dort nicht
            sha = alt.json().get("sha") if alt.status_code == 200 else None
            daten = {"message": f"{ziel}: {anzahl} {'Aktie' if anzahl == 1 else 'Aktien'} ({herkunft})",
                     "content": inhalt, "branch": zweig}
            if sha:
                daten["sha"] = sha
            antwort = requests.put(url, headers=kopf, json=daten, timeout=30)
            if antwort.status_code in (200, 201):
                geschrieben.append(zweig)
            else:
                grund = "ohne Begründung"
                try:
                    grund = antwort.json().get("message", grund)
                except Exception:
                    pass
                gescheitert.append(f"{zweig} (Code {antwort.status_code}: "
                                   f"{grund})")
        except Exception as e:
            gescheitert.append(f"{zweig} ({type(e).__name__}: {e})")
    bericht = ", ".join(geschrieben)
    if not geschrieben:
        return (("Auf keinem Zweig geschrieben: " + "; ".join(gescheitert))
                if gescheitert else
                ("Kein bekannter Zweig führt " + ziel + "."), "")
    if gescheitert:
        return ("Nur teilweise übernommen. Geschrieben auf " + bericht
                + "; NICHT geschrieben auf " + "; ".join(gescheitert),
                bericht)
    return "", bericht


@st.cache_data(ttl=300, show_spinner=False)
def aktuelle_listengroesse(datei: str = None) -> int | None:
    """Wie viele Aktien stehen derzeit im Repo? (öffentlich lesbar)"""
    import requests
    datei = datei or LISTEN_DATEI
    try:
        r = requests.get(f"https://raw.githubusercontent.com/{REPO}/main/{datei}",
                         timeout=15)
        if r.status_code != 200:
            return None
        fehler, ticker = pruefe_wochenliste(r.content)
        return len(ticker) if not fehler else None
    except Exception:
        return None


# --- Einzeln ueberwachte Aktien (S7, Gerhard, 20.09.2026) -------------------
# Gerhard: "Wenn ich eine einzelne Aktie ins Tool eintrage, auch nur eine oder
# zwei, moechte ich sie per Button auf ueberwachen setzen koennen." Die Aktien
# stehen in einer EIGENEN Datei (listen.EINZEL_DATEI) auf jedem Zweig der
# Wochenlisten, damit ein Eintrag nicht als neue Wochenliste zaehlt; geschrieben
# wird ueber denselben Weg wie der Upload (wochenliste_einspielen).
# UEBERWACHT WIRD SEIT 22.09.2026 (Gerhards Antworten O11 bis O13): alle
# Strategien samt Darvas, sofort im laufenden Handel, und der Wochenputz
# beendet die Ueberwachung wieder (ueberall Wochenputz, Antwort 87 vom
# 24.09.2026). Lesen und Schreiben nur im vollen Zugang (gesamtpruefung,
# gast_abschottung).
EINZEL_HINWEIS = ("Überwacht wird ab sofort: Auf einer einzeln eingetragenen Aktie laufen alle Strategien, "
                  "auch Darvas. Der Wächter nimmt sie im laufenden Handel binnen einer Minute auf und rechnet "
                  "ihre Kaufpunkte selbst; der Wochenputz beendet die Überwachung wieder.")


def _einzel_roh() -> bytes:
    """Der Inhalt der Datei auf main, frisch ueber die GitHub-API; die
    oeffentliche Adresse raw.githubusercontent.com liefert bis zu fuenf
    Minuten alte Staende."""
    import base64
    import requests
    token = (_secret("GITHUB_TOKEN") or "").strip()
    if not token:
        raise LookupError("In den Streamlit-Secrets fehlt GITHUB_TOKEN.")
    r = requests.get(f"https://api.github.com/repos/{REPO}/contents/{listen.EINZEL_DATEI}",
                     params={"ref": "main"},
                     headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                     timeout=20)
    if r.status_code == 404:
        raise LookupError(f"Die Datei {listen.EINZEL_DATEI} fehlt im Repo.")
    if r.status_code != 200:
        raise LookupError(f"GitHub antwortete mit Code {r.status_code}.")
    return base64.b64decode(r.json().get("content") or "")


@st.cache_data(ttl=60, show_spinner=False)
def _einzel_holen() -> bytes:
    return _einzel_roh()


def _einzel_setzen(ticker: str, firma: str, an: bool) -> tuple:
    """Eine Aktie ein- oder austragen, auf jedem Zweig der Wochenlisten.
    Gelesen wird vorher frisch, nicht aus dem Zwischenspeicher. Liefert
    (Art, Satz, technischer Grund oder None) mit Art ok, teil oder fehler. Die
    Meldung nennt keine Zweige (Antwort 38 vom 24.09.2026); die stehen nur im
    technischen Grund, wenn etwas schiefging (Antwort 102)."""
    from zoneinfo import ZoneInfo
    nicht = "Die Einzelüberwachung ließ sich nicht ändern; versuche es bitte später noch einmal."
    token = (_secret("GITHUB_TOKEN") or "").strip()
    if not token:
        return "fehler", nicht, "In den Streamlit-Secrets fehlt GITHUB_TOKEN."
    try:
        neu, geaendert, anzahl = listen.einzel_aendern(
            _einzel_roh(), ticker, firma, an, datetime.now(ZoneInfo("Europe/Vienna")).strftime("%Y-%m-%d %H:%M"))
    except Exception as e:  # noqa
        return "fehler", nicht, str(e) or type(e).__name__
    if not geaendert:
        return "ok", (f"{ticker} wird schon einzeln überwacht." if an else f"{ticker} wird nicht einzeln überwacht."), None
    fehler_text, zweige = wochenliste_einspielen(neu, token, anzahl, listen.EINZEL_DATEI,
                                                herkunft=f"{ticker} {'eingetragen' if an else 'ausgetragen'} über Heliot")
    if zweige:
        _einzel_holen.clear()
    if fehler_text:
        if zweige:
            return "teil", f"{ticker} ist nur teilweise {'eingetragen' if an else 'ausgetragen'}.", fehler_text
        return "fehler", nicht, fehler_text
    if an:
        return "ok", f"{ticker} wird ab sofort einzeln überwacht.", None
    return "ok", f"{ticker} wird ab sofort nicht mehr einzeln überwacht.", None


def _einzel_meldung(schluessel: str):
    eintrag = st.session_state.pop(schluessel, None)
    if not eintrag:
        return
    art, satz, technik = (tuple(eintrag) + (None, None, None))[:3]
    if art == "ok":
        erfolg(satz)
    elif art == "teil":
        st.warning(satz)
        if technik:
            st.caption(technik_zeile(technik))
    elif art:
        fehler(satz, technik)


def _einzel_eingetragen(wann: str) -> str:
    wann = str(wann or "")
    if len(wann) >= 16:
        return f", eingetragen am {nachschlagen.datum_text(wann[:10])} um {wann[11:16]} Uhr Wiener Zeit"
    return f", eingetragen am {nachschlagen.datum_text(wann[:10])}" if wann else ""


def einzel_bereich(ticker: str, firma: str):
    """Der Knopf im Nachschlagen: diese Aktie ueberwachen oder nicht mehr."""
    st.markdown("### Einzeln überwachen", anchors=False)
    _einzel_meldung("einzel_meldung_nachschlagen")
    try:
        zeilen = listen.einzel_zeilen(_einzel_holen())
    except Exception as e:  # noqa
        st.markdown("Die Liste der einzeln überwachten Aktien ist gerade nicht lesbar.")
        st.caption(technik_zeile(str(e) or type(e).__name__))
        return
    eintrag = next((z for z in zeilen if z[0] == ticker), None)
    if eintrag:
        st.markdown(f"{ticker} steht auf der Liste der einzeln überwachten Aktien{_einzel_eingetragen(eintrag[2])}. "
                    + EINZEL_HINWEIS)
        if st.button("Diese Aktie nicht mehr überwachen", key=f"einzel_aus_{ticker}"):
            st.session_state["einzel_meldung_nachschlagen"] = _einzel_setzen(ticker, firma, False)
            st.rerun()
    else:
        st.markdown(f"{ticker} steht nicht auf der Liste der einzeln überwachten Aktien. " + EINZEL_HINWEIS)
        if st.button("Diese Aktie überwachen", key=f"einzel_an_{ticker}"):
            st.session_state["einzel_meldung_nachschlagen"] = _einzel_setzen(ticker, firma, True)
            st.rerun()


def einzel_liste_zeigen():
    """Die Liste im Reiter Wochenlisten, je Aktie ein Knopf zum Austragen."""
    st.markdown("### Einzeln überwachte Aktien", anchors=False)
    _einzel_meldung("einzel_meldung_liste")
    try:
        zeilen = listen.einzel_zeilen(_einzel_holen())
    except Exception as e:  # noqa
        st.markdown("Die Liste ist gerade nicht lesbar.")
        st.caption(technik_zeile(str(e) or type(e).__name__))
        return
    if not zeilen:
        st.markdown("Keine Aktie ist einzeln eingetragen. Eingetragen wird beim Nachschlagen einer Aktie mit dem "
                    "Knopf Diese Aktie überwachen. " + EINZEL_HINWEIS)
        return
    st.markdown(("Eine Aktie ist" if len(zeilen) == 1 else f"{nachschlagen.zahl(len(zeilen))} Aktien sind")
                + " einzeln eingetragen; weitere kommen beim Nachschlagen dazu. " + EINZEL_HINWEIS)
    for t, firma, wann in zeilen:
        st.markdown(t + (f", {firma}" if firma else "") + _einzel_eingetragen(wann))
        if st.button(f"{t} nicht mehr überwachen", key=f"einzel_liste_aus_{t}"):
            st.session_state["einzel_meldung_liste"] = _einzel_setzen(t, firma, False)
            st.rerun()


# S4 (Gerhard, 20.09.2026): "Ein Gast soll wirklich nur den Scanner sehen und
# sonst nichts von dem, was dahinter laeuft." Das Nachschlagen gibt es deshalb
# nur angemeldet; ein Verweis mit ?aktie=... bleibt fuer Gaeste ohne Wirkung.
def abschnitt_erklaerung(titel: str, erklaerungen: dict):
    """Der Erklaerungsknopf je Abschnitt des Nachschlagens (Antwort 13 vom
    24.09.2026): Ein Klick zeigt die Erklaerungen aller Kennzahlen des
    Abschnitts darunter, der naechste blendet sie aus (Antwort 12). Die
    Beschriftung ist eine Frage wie im Scanner (Antwort 11)."""
    eintraege = erklaerungen.get(titel) or []
    if not eintraege:
        return
    k = "ns_erkl_" + (re.sub(r"[^a-z0-9]+", "_", titel.lower()).strip("_") or "abschnitt")
    sichtbar = bool(st.session_state.get(k))
    st.button(f"Was bedeuten die Angaben im Abschnitt {titel}?", key=f"{k}_knopf", type="tertiary",
              on_click=erklaerung_umschalten, args=(k, sichtbar))
    if sichtbar:
        for name, text in eintraege:
            st.caption(f"{name}: {text}" if name else text)


if rolle != "gast":
    st.markdown("## Aktie nachschlagen", anchors=False)
    # DAS FELD STEHT IN DER ADRESSE (Mathias, 14.09.2026): bind="query-params"
    # schreibt die Eingabe als ?aktie=... in die Adresse der Seite und liest sie
    # beim Oeffnen wieder. So fuehrt ein Verweis wie ?aktie=AAOI direkt zu den
    # vollstaendigen Daten einer Aktie, und ein Lesezeichen merkt sich die Aktie.
    nachschlag_eingabe = (st.text_input("Gib ein Kürzel oder einen Firmennamen ein und drück die Eingabetaste", key="aktie",
                                        bind="query-params", placeholder="Zum Beispiel AAOI oder Apple")
                          or "").strip()
else:
    nachschlag_eingabe = ""
if nachschlag_eingabe:
    nachschlag_daten = nachschlag_dateien()
    nachschlag_ticker, nachschlag_kandidaten = nachschlagen.finde(nachschlag_eingabe,
                                                                  nachschlag_daten.get("rs_universum.json"))
    if nachschlag_ticker is None:
        if nachschlag_kandidaten:
            st.markdown("Mehrere Aktien passen. Gib bitte das Kürzel ein:")
            for k, n in nachschlag_kandidaten:
                st.markdown(f"{k}, {n}")
        else:
            st.markdown("Nichts gefunden. Prüfe bitte Kürzel oder Namen.")
    else:
        with st.spinner(f"Hole Kurs, Volumen und Chartmuster für {nachschlag_ticker}"):
            try:
                nachschlag_live_werte = nachschlag_live(nachschlag_ticker)
            except Exception:
                nachschlag_live_werte = None
            try:
                nachschlag_k, nachschlag_kq = nachschlag_kurve(nachschlag_ticker)
            except Exception:
                nachschlag_k, nachschlag_kq = None, "keine"
            try:
                nachschlag_s, nachschlag_sq = nachschlag_sektor(nachschlag_ticker)
            except Exception:
                nachschlag_s, nachschlag_sq = None, "keine"
            try:
                nachschlag_stichtag = nachschlagen.streubesitz_stichtag(nachschlag_daten.get("ibd_ratings.json"),
                                                                       nachschlag_ticker)
                nachschlag_sb_kurs = (nachschlag_stichtagkurs(nachschlag_ticker, nachschlag_stichtag)
                                      if nachschlag_stichtag else None)
            except Exception:
                nachschlag_sb_kurs = None
            # ETAPPE 5 (Gerhard, 13.09.2026, Entscheidung 9): Analysten und
            # Konsens aus dem privaten Datenrepo, nur mit dem Lese-Token; ohne
            # ihn nennt das Kapitel den Grund.
            nachschlag_an_tab, nachschlag_an_grund = lade_scanner_analysten()
            nachschlag_an = nachschlagen.analysten_zeile(nachschlag_an_tab, nachschlag_ticker)
            # Die Muster laufen mit dem echten RS aus der Nachtdatei, nicht mit
            # einer Schaetzung (siehe analysiere).
            nachschlag_e = nachschlagen.eintraege(nachschlag_daten.get("rs_universum.json")).get(nachschlag_ticker, {})
            nachschlag_rs, nachschlag_rs_satz = nachschlagen.rs_fuer_muster(nachschlag_e)
            try:
                nachschlag_df, nachschlag_res = muster_fuer(nachschlag_ticker, api_key, nachschlag_rs)
            except Exception:
                nachschlag_df, nachschlag_res = None, None
            # Base-on-Base, Green Line und die Stufenzaehlung brauchen die ganze
            # Kurshistorie; sie kommen aus der Zeile der Scanner-Tabelle.
            try:
                nachschlag_nacht = nachschlagen.analysten_zeile(lade_scanner_tabelle()[0], nachschlag_ticker)
            except Exception:
                nachschlag_nacht = None
        nachschlag_erkl = nachschlagen.abschnitt_erklaerungen()
        for ueberschrift, saetze in nachschlagen.bericht(
                nachschlag_ticker, nachschlag_daten.get("rs_universum.json"), nachschlag_daten.get("ibd_ratings.json"),
                nachschlag_daten.get("sektor_rangliste.json"), live=nachschlag_live_werte, kurve=nachschlag_k,
                kurve_quelle=nachschlag_kq, sektor_name=nachschlag_s, sektor_quelle=nachschlag_sq,
                streubesitz_kurs=nachschlag_sb_kurs, analysten=nachschlag_an, analysten_grund=nachschlag_an_grund):
            st.markdown(f"### {ueberschrift}", anchors=False)
            saetze_zeigen(saetze)
            abschnitt_erklaerung(ueberschrift, nachschlag_erkl)

        # MUSTER, KAUFPUNKTE, CHARTS (Mathias, 14.09.2026). Diese Teile
        # stammen aus der frueheren Einzelabfrage, die damit entfaellt.
        st.markdown("### Chartmuster und Trend Template", anchors=False)
        saetze_zeigen(nachschlagen.muster_saetze(nachschlag_res, nachschlag_rs_satz if nachschlag_res else None))
        abschnitt_erklaerung("Chartmuster und Trend Template", nachschlag_erkl)
        # CHARTMUSTER AUS GERHARDS PAPIER VOM 20.09.2026 (Etappe 1): dieselben
        # Worte wie bei den Treffern des Scanners, gerechnet am letzten
        # abgeschlossenen Handelstag; waehrend des Handels zaehlt der Vortag.
        st.markdown("### Weitere Chartmuster", anchors=False)
        saetze_zeigen(nachschlagen.chartmuster_saetze(nachschlag_df, nachtzeile=nachschlag_nacht))
        abschnitt_erklaerung("Weitere Chartmuster", nachschlag_erkl)
        st.markdown("### Kaufpunkte", anchors=False)
        if nachschlag_res:
            saetze_zeigen(nachschlagen.kaufpunkt_saetze(nachschlag_res))
            abschnitt_erklaerung("Kaufpunkte", nachschlag_erkl)
            st.caption("Der folgende Chart zeigt die letzten 180 Handelstage mit den Kaufpunkten als waagrechte "
                       "Linien; alle Werte stehen darüber als Text.")
            zeichne_kaufpunkt_chart(nachschlag_df, nachschlag_res, nachschlag_ticker)
        else:
            st.markdown("Ohne Kursdaten gibt es keine Kaufpunkte. Zwei mögliche Gründe: Die Schreibweise stimmt "
                        "nicht, oder die Kursquelle bremst gerade auf den geteilten Servern; dann schlag in ein "
                        "paar Minuten noch einmal nach.")
        st.markdown("### Aktienchart", anchors=False)
        aktienchart(nachschlag_ticker, nachschlag_df)
        # S7 (Gerhard, 20.09.2026): der Knopf zum einzeln Ueberwachen, als letzter
        # Abschnitt, weil er der naechste Schritt nach dem Lesen ist; nur im
        # vollen Zugang.
        if rolle == "voll":
            einzel_bereich(nachschlag_ticker,
                           nachschlagen.firmenname(nachschlag_e.get("name") or nachschlag_e.get("firma")) or "")

if rolle != "gast":
    st.markdown("---")

# Gaeste bekommen weder die Wochenliste noch die Seite fuer Gastpasswoerter.
# Ohne eingerichtetes Passwort gibt es keine Gastpasswoerter, also auch die
# Seite dafuer nicht.
# DIE EINZELABFRAGE IST ENTFALLEN (Mathias, 14.09.2026): Sie zeigte Muster,
# Kaufpunkte und Chart einer Aktie mit einem geschaetzten RS. Muster,
# Kaufpunkte und Chart stehen jetzt beim Nachschlagen oben, mit dem echten RS.
# DER SCANNER (Mathias, 14.09.2026) steht allen offen, auch Gaesten: Er liest
# nur und veraendert nichts.
# S4 (Gerhard, 20.09.2026): Ein Gast sieht NUR den Scanner, ohne
# Registerkarten; Liste pruefen, Aktueller Scan und Regelwerk gibt es fuer ihn
# nicht, der Lauf endet hinter dem Scanner (Schranke "if tab_liste is None").
# DER REITER EINSTELLUNGEN (Mathias und Gerhard, 23.09.2026) steht zuletzt; Gaeste
# bekommen ihn nicht, ohne vollen Zugang laesst er sich nur ansehen.
tab_upload = tab_gast = tab_ablaeufe = tab_einst = None
if rolle == "gast":
    st.markdown("## Scanner", anchors=False)
    tab_scanner = st.container()
    tab_liste = tab_scan = tab_info = None
elif rolle == "voll":
    (tab_liste, tab_scan, tab_scanner, tab_upload, tab_gast, tab_ablaeufe, tab_info,
     tab_einst) = st.tabs(["Liste prüfen", "Aktueller Scan", "Scanner", "Wochenlisten", "Gastzugang", "Abläufe",
                           "Regelwerk", "Einstellungen"])
else:
    tab_liste, tab_scan, tab_scanner, tab_upload, tab_info, tab_einst = st.tabs(
        ["Liste prüfen", "Aktueller Scan", "Scanner", "Wochenlisten", "Regelwerk", "Einstellungen"])


def tt_text(wert) -> str:
    """Die Spalte Trend Template einer Mappe in Worten: 'erfüllt, 8 von 8'
    oder '7 von 8'. Versteht die alte Schreibweise mit Haken und Kreuz."""
    m = re.search(r"(\d)\s*(?:/|von)\s*8", str(wert or ""))
    if not m:
        return nachschlagen.lesbar(wert) or "unbekannt"
    return ("erfüllt, " if m.group(1) == "8" else "") + f"{m.group(1)} von 8"


def mappe_text(wert) -> str:
    """Eine Zelle der Mappe in Worten: Haken und Kreuz der alten Schreibweise
    werden zu 'erfüllt' und 'nicht erfüllt', andere Bildzeichen fallen weg. Ein
    fehlender Wert heisst 'unbekannt', nie 'nan' (Berichtigung 1 vom 24.09.2026)."""
    if wert is None or (isinstance(wert, float) and pd.isna(wert)):
        return "unbekannt"
    s = str(wert)
    if s.strip().lower() in ("", "nan", "none", "nat", "?"):
        return "unbekannt"
    s = s.replace("\u2713", "erfüllt ").replace("\u2717", "nicht erfüllt ")
    return nachschlagen.lesbar(s) or "unbekannt"


# --- Aktueller Scan --------------------------------------------------------
# Fenster auf die Nachtergebnisse (Mathias' Auftrag vom 23.07.2026): Der
# Scanner legt sein Ergebnis seit demselben Tag als kaufpunkte_aktuell.xlsx
# ins Repo (scanner.yml, Schritt 'Ergebnis für die Heliot-Anzeige
# veröffentlichen'). Diese Karte zeigt es gut vorlesbar an — als Liste,
# nicht als Tabelle (JAWS), die Tabelle gibt es zusätzlich im Ausklapper.

# REPO steht oben bei DATEN_REPO.
SCAN_DATEI = "kaufpunkte_aktuell.xlsx"


@st.cache_data(ttl=600, show_spinner=False)
def lade_nachtscan():
    """Liefert (DataFrame, Standtext, Rohbytes, None) oder (None, einfacher
    Hinweis, None, technischer Grund oder None), Antwort 102 vom 24.09.2026."""
    import requests
    nicht = "Der Nachtscan ließ sich gerade nicht laden; versuche es bitte später noch einmal."
    try:
        r = requests.get(
            f"https://raw.githubusercontent.com/{REPO}/main/{SCAN_DATEI}",
            timeout=20)
    except Exception as e:
        return None, nicht, None, f"Netzwerkfehler {type(e).__name__}: {e}"
    if r.status_code == 404:
        return None, ("Noch kein Nachtscan abgelegt. Die Datei entsteht beim "
                      "nächsten Lauf des Scanners und liegt dann jeden Morgen "
                      "hier bereit."), None, None
    if r.status_code != 200:
        return None, nicht, None, f"GitHub antwortete mit Code {r.status_code}."
    try:
        df = pd.read_excel(io.BytesIO(r.content), sheet_name="Kaufpunkte")
    except Exception as e:
        return None, "Die Ergebnisdatei des Nachtscans ließ sich nicht lesen.", None, f"{type(e).__name__}: {e}"
    stand = ""
    try:
        from zoneinfo import ZoneInfo
        c = requests.get(f"https://api.github.com/repos/{REPO}/commits",
                         params={"path": SCAN_DATEI, "per_page": 1}, timeout=15)
        if c.status_code == 200 and c.json():
            utc = datetime.fromisoformat(
                c.json()[0]["commit"]["committer"]["date"].replace("Z", "+00:00"))
            wien = utc.astimezone(ZoneInfo("Europe/Vienna"))
            stand = f"{wien:%d.%m.%Y um %H:%M} Uhr Wiener Zeit"
    except Exception:
        pass
    return df, stand, r.content, None


def _zahl(wert) -> str:
    """Excel-Werte lesbar machen: deutsche Schreibweise mit zwei
    Nachkommastellen (119.26 wird 119,26), NaN und leer werden leer."""
    if wert is None or (isinstance(wert, float) and pd.isna(wert)):
        return ""
    if isinstance(wert, (int, float)):
        return nachschlagen.zahl(wert, 2)
    return nachschlagen.anzeige_text(wert)


def rs_mappe(wert) -> str:
    """Die Spalte RS Nasdaq der Mappe: ganze Zahl, 'vorläufig' bleibt stehen."""
    if wert is None or (isinstance(wert, float) and pd.isna(wert)) or str(wert).strip() in ("", "n/a"):
        return "nicht verfügbar"
    if isinstance(wert, (int, float)):
        return str(int(round(wert)))
    return nachschlagen.lesbar(wert)


# --- Scanner (Mathias, 14.09.2026) ------------------------------------------
# "Wir bauen nun den scanner ein, erreichbar aus dem web-tool." Teil 1 schickt
# eine Strategie oder ein Chart-Signal durch den ganzen US-Markt, Teil 2
# filtert frei nach jedem Merkmal, jede Kennzahl als Spanne mit Von und Bis
# (Gerhard, 15.09.2026, Auftrag 1). Gerechnet wird nachts (scanner_daten.py,
# Ablauf scanner_daten.yml). Die App liest die Tabelle aus dem Release
# "scanner-daten" dieses Repos und die Analystenwerte aus dem privaten
# Datenrepo; alles Weitere rechnet scanner_ansicht.py, das ohne Streamlit
# pruefbar ist. Fuer Screenreader steht alles als Text: Kontrollfelder,
# Eingabefelder mit ausgeschriebener Beschriftung, das Ergebnis als
# nummerierte Liste mit Verweisen, keine Tabelle und kein Chart. Der Scanner
# beeinflusst weder Waechter noch Alarme (Mathias: "Baue noch keine
# Vernetzung zu unserem Haupttool"), mit einer Ausnahme seit 21.09.2026
# (Gerhard, S2; Mathias: "2 ja"): Der volle Zugang kann ein Ergebnis per Knopf
# als Wochen- oder Darvas-Liste uebergeben, nach Abwahl einzelner Aktien und
# einer Bestaetigung. Das ist derselbe Weg wie der Upload der Wochenliste, und
# ab dem naechsten Nachtscan arbeitet die Automatik mit der neuen Liste.
#
# GESCANNT WIRD NUR MIT DEM KNOPF (Gerhard, 15.09.2026, Auftrag 2): "Den
# Erklaertext zum Scanner bitte entfernen, den brauche ich nicht. Unten einen
# Knopf einbauen, mit dem ich den Scan starte. Wichtig ist mir, dass ich
# merke, dass etwas passiert: Der Knopf soll waehrend des Laufs anzeigen, dass
# gescannt wird, und danach, wie viele Treffer es gab. Kein stilles Nachladen
# im Hintergrund." Die Einstellungen aendern das Ergebnis deshalb nicht mehr;
# erst der Knopf holt die Tabelle und rechnet. Der Knopf behaelt dabei seinen
# Schluessel, nur die Beschriftung wechselt: So bleibt der Fokus eines
# Screenreaders auf ihm (Streamlit leitet die Kennung eines Knopfs mit
# Schluessel allein aus dem Schluessel ab, nachgelesen in 1.63).

# SCANNER_RELEASE, _scanner_tabelle_holen und lade_scanner_tabelle stehen weiter
# oben vor dem Nachschlagen, das die Tabelle seit dem 23.09.2026 ebenfalls liest
# (Base-on-Base, Green Line und die Stufenzaehlung der Basen).


@st.cache_data(ttl=600, show_spinner=False)
def lade_scanner_stand():
    import requests
    try:
        r = requests.get(SCANNER_RELEASE + "scanner_stand.json", timeout=20)
        if r.status_code == 200 and isinstance(r.json(), dict):
            return r.json()
    except Exception:  # noqa
        pass
    return nachschlagen.lade_datei("scanner_stand.json")


@st.cache_data(ttl=600, show_spinner=False)
def _scanner_kennzahlen_nachtragen(handelstag):
    """Die Kennzahlen aus Nachtscan und Fundament fuer eine Nachttabelle, der sie
    fehlen (gebaut vor dem 15.09.2026): aus denselben Nachtdateien, die das
    Nachschlagen liest. Rueckgabe (Tabelle oder None, Hinweis)."""
    tabelle, _grund = lade_scanner_tabelle()
    if tabelle is None:
        return None, ""
    dateien = nachschlag_dateien()
    return sa.sd.kennzahlen_ergaenzen(tabelle, dateien.get("rs_universum.json") or {},
                                      dateien.get("ibd_ratings.json") or {}, handelstag=handelstag)


def app_adresse() -> str:
    """Die Adresse der App fuer die Verweise auf die vollstaendigen Daten. Auf
    Streamlit Community Cloud laeuft die App in einem Rahmen unter /~/+/;
    verwiesen wird auf die Adresse davor, die den Rahmen samt Anmeldung laedt."""
    try:
        u = str(st.context.url or "")
    except Exception:  # noqa
        u = ""
    if "/~/+" in u:
        u = u.split("/~/+")[0]
    if not u.startswith("http"):
        u = "https://heliot.streamlit.app"
    return u.rstrip("/")


def _sc_schluessel(feld: str, teil: str) -> str:
    return f"sc_{feld}_{teil}"


def _sc_sektor_schluessel(sektor: str) -> str:
    return "sc_sektor_" + (re.sub(r"[^a-z0-9]+", "_", str(sektor).lower()).strip("_") or "ohne_angabe")


def _sc_felder_leeren():
    for feld in sa.FELDER:
        st.session_state[_sc_schluessel(feld.schluessel, "an")] = False
        st.session_state[_sc_schluessel(feld.schluessel, "min")] = ""
        st.session_state[_sc_schluessel(feld.schluessel, "max")] = ""
    st.session_state["sc_rs_vorlaeufig"] = False


def _sc_vorgaben_setzen(nur_grenzen: bool = False):
    """Traegt die Merkmale der gewaehlten Strategie in Teil 2 ein. Beim Wechsel
    der Strategie werden die Felder neu gesetzt; beim Wechsel der Toleranz nur
    die Grenzen der Strategie."""
    k = st.session_state.get("sc_strategie") or ""
    vorgabe = sa.voreinstellung(k, st.session_state.get("sc_toleranz") == "toleranz")
    if not nur_grenzen:
        _sc_felder_leeren()
        gruppen = {sa.FELD[s].gruppe for s in vorgabe}
        for g, _name in sa.GRUPPEN:
            st.session_state[f"sc_gruppe_{g}"] = g in gruppen
        st.session_state["sc_sortierung"] = "rating" if sa.ist_muster(k) else "rs"
    for schluessel, werte in vorgabe.items():
        if not nur_grenzen:
            st.session_state[_sc_schluessel(schluessel, "an")] = True
        for teil in ("min", "max"):
            if teil in werte:
                st.session_state[_sc_schluessel(schluessel, teil)] = werte[teil]


def _sc_strategie_gewaehlt():
    _sc_vorgaben_setzen()


def _sc_toleranz_geaendert():
    _sc_vorgaben_setzen(nur_grenzen=True)


def _sc_sektoren_setzen(an: bool):
    for s in st.session_state.get("sc_sektorliste") or []:
        st.session_state[_sc_sektor_schluessel(s)] = an


def _sc_alles_zuruecksetzen():
    st.session_state["sc_strategie"] = ""
    st.session_state["sc_toleranz"] = "streng"
    st.session_state["sc_handelbar"] = True
    st.session_state["sc_langweilig"] = True
    _sc_felder_leeren()
    for g, _name in sa.GRUPPEN:
        st.session_state[f"sc_gruppe_{g}"] = False
    st.session_state["sc_termine_an"] = False
    for key, _text, _plus, _lage in sa.TERMIN_TEILE:
        st.session_state[f"sc_termine_{key}"] = False
    st.session_state["sc_termine_ohne_zeit"] = False
    st.session_state["sc_termine_umfang"] = "markt"
    _sc_sektoren_setzen(True)
    st.session_state["sc_sortierung"] = "rs"


def _sc_einstellung(sektoren) -> dict:
    """Die Einstellungen aus den Bedienfeldern, fuer scanner_ansicht.auswerten."""
    felder = {}
    for f in sa.FELDER:
        s = f.schluessel
        felder[s] = {"an": bool(st.session_state.get(_sc_schluessel(s, "an"))),
                     "min": st.session_state.get(_sc_schluessel(s, "min")) or "",
                     "max": st.session_state.get(_sc_schluessel(s, "max")) or "",
                     "vorlaeufig": bool(st.session_state.get("sc_rs_vorlaeufig")) if s == "rs" else False}
    termine = {"an": bool(st.session_state.get("sc_termine_an")),
               "ohne_zeit": bool(st.session_state.get("sc_termine_ohne_zeit")),
               "umfang": st.session_state.get("sc_termine_umfang") or "markt"}
    for key, _text, _plus, _lage in sa.TERMIN_TEILE:
        termine[key] = bool(st.session_state.get(f"sc_termine_{key}"))
    return {"strategie": st.session_state.get("sc_strategie") or "",
            "toleranz": st.session_state.get("sc_toleranz") == "toleranz",
            "nur_handelbar": bool(st.session_state.get("sc_handelbar")),
            "langweilig_raus": bool(st.session_state.get("sc_langweilig", True)),
            "felder": felder, "termine": termine,
            "sektoren": [s for s in sektoren if st.session_state.get(_sc_sektor_schluessel(s), True)],
            "sortierung": st.session_state.get("sc_sortierung") or ""}


# VORLAGEN DES SCANNERS (Gerhard, 20.09.2026, S1; Mathias, 21.09.2026: "3
# Datenrepo"). Eine Vorlage ist der Stand aller Bedienfelder des Scanners; die
# Datei scanner_vorlagen.json liegt im PRIVATEN Datenrepo und wird mit
# DATEN_TOKEN gelesen und geschrieben, also nur im vollen Zugang. Lesen,
# Pruefen und Schreiben der Datei rechnet scanner_ansicht.py ohne Netz.
def _sc_vorlage_schluessel(sektoren) -> list:
    k = ["sc_strategie", "sc_toleranz", "sc_handelbar", "sc_langweilig", "sc_rs_vorlaeufig", "sc_termine_an",
         "sc_termine_ohne_zeit", "sc_termine_umfang", "sc_sortierung", "sc_anzahl", "sc_format",
         "sc_gruppe_sektoren"]
    for f in sa.FELDER:
        k += [_sc_schluessel(f.schluessel, teil) for teil in ("an", "min", "max")]
    for g, _name in sa.GRUPPEN:
        k.append(f"sc_gruppe_{g}")
    for key, _text, _plus, _lage in sa.TERMIN_TEILE:
        k.append(f"sc_termine_{key}")
    for s in sektoren:
        k.append(_sc_sektor_schluessel(s))
    return k


def _datenrepo_kopf(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


@st.cache_data(ttl=60, show_spinner=False)
def _sc_vorlagen_holen():
    """(Vorlagen, sha der Datei oder None). Fehlschlaege werfen und landen
    nicht im Speicher."""
    import base64
    import requests
    token = _daten_token()
    if not token:
        raise LookupError("kein Token für das Datenrepo")
    r = requests.get(f"https://api.github.com/repos/{DATEN_REPO}/contents/{sa.VORLAGE_DATEI}",
                     headers=_datenrepo_kopf(token), timeout=20)
    if r.status_code == 404:
        return [], None
    if r.status_code != 200:
        raise LookupError(f"GitHub antwortete mit Code {r.status_code}")
    j = r.json()
    inhalt = base64.b64decode(j.get("content") or "").decode("utf-8")
    return sa.vorlagen_lesen(inhalt), j.get("sha")


def _sc_vorlagen_schreiben(vorlagen, sha, nachricht):
    """(ok, Grund). Schreibt die ganze Datei; mit sha nur, wenn sie seit dem
    Lesen niemand geaendert hat."""
    import base64
    import requests
    token = _daten_token()
    if not token:
        return False, "kein Token für das Datenrepo"
    koerper = {"message": nachricht,
               "content": base64.b64encode(sa.vorlagen_text(vorlagen).encode("utf-8")).decode("ascii")}
    if sha:
        koerper["sha"] = sha
    try:
        r = requests.put(f"https://api.github.com/repos/{DATEN_REPO}/contents/{sa.VORLAGE_DATEI}",
                         json=koerper, headers=_datenrepo_kopf(token), timeout=30)
    except Exception as e:  # noqa
        return False, f"GitHub war nicht erreichbar ({type(e).__name__})"
    finally:
        _sc_vorlagen_holen.clear()
    if r.status_code in (200, 201):
        return True, ""
    if r.status_code in (409, 422):
        return False, "die Vorlagen wurden inzwischen woanders geändert; bitte noch einmal versuchen"
    if r.status_code in (401, 403):
        return False, f"GitHub hat das Schreiben abgelehnt (Code {r.status_code}); der Token darf das Datenrepo nicht beschreiben"
    return False, f"GitHub antwortete mit Code {r.status_code}"


def _sc_vorlagen_frisch():
    """Vor dem Schreiben immer den neuesten Stand: (Vorlagen, sha) oder
    (None, Grund)."""
    _sc_vorlagen_holen.clear()
    try:
        return _sc_vorlagen_holen()
    except LookupError as e:
        return None, str(e)
    except Exception as e:  # noqa
        return None, f"Netzwerkfehler {type(e).__name__}"


def _sc_vorlage_laden():
    name = st.session_state.get("sc_vorlage_wahl")
    vorlagen, sha_oder_grund = _sc_vorlagen_frisch()
    if vorlagen is None:
        st.session_state["sc_vorlage_meldung_oben"] = (
            "fehler", "Die Vorlage ließ sich nicht laden; versuche es bitte später noch einmal.", sha_oder_grund)
        return
    v = next((x for x in vorlagen if x["name"] == name), None)
    if v is None:
        st.session_state["sc_vorlage_meldung_oben"] = ("fehler", "Diese Vorlage gibt es nicht mehr.", None)
        return
    sektoren = st.session_state.get("sc_sektorliste") or []
    _sc_alles_zuruecksetzen()
    for schluessel, wert in sa.vorlage_anwenden(v["werte"], _sc_vorlage_schluessel(sektoren)).items():
        st.session_state[schluessel] = wert
    st.session_state["sc_vorlage_name"] = v["name"]
    st.session_state["sc_vorlage_meldung_oben"] = (
        "ok", f"Vorlage {v['name']} geladen. Zum Rechnen drück unten Scan starten.", None)


def _sc_vorlage_speichern():
    ok, name = sa.vorlage_name_pruefen(st.session_state.get("sc_vorlage_name"))
    if not ok:
        st.session_state["sc_vorlage_meldung_unten"] = ("fehler", name, None)
        return
    sektoren = st.session_state.get("sc_sektorliste") or []
    werte = sa.vorlage_werte(st.session_state, _sc_vorlage_schluessel(sektoren))
    vorlagen, sha_oder_grund = _sc_vorlagen_frisch()
    if vorlagen is None:
        st.session_state["sc_vorlage_meldung_unten"] = (
            "fehler", "Die Vorlage ist nicht gespeichert; versuche es bitte später noch einmal.", sha_oder_grund)
        return
    neu, ersetzt = sa.vorlage_setzen(vorlagen, name, werte)
    ok, grund = _sc_vorlagen_schreiben(neu, sha_oder_grund,
                                       f"Scanner-Vorlage {'ersetzt' if ersetzt else 'gespeichert'}: {name}")
    if ok:
        st.session_state["sc_vorlage_meldung_unten"] = (
            "ok", f"Vorlage {name} {'ersetzt' if ersetzt else 'gespeichert'}; sie steht oben unter Vorlagen.", None)
    else:
        st.session_state["sc_vorlage_meldung_unten"] = (
            "fehler", "Die Vorlage ist nicht gespeichert; versuche es bitte später noch einmal.", grund)


def _sc_vorlage_loeschen():
    name = st.session_state.get("sc_vorlage_wahl")
    if not (name and st.session_state.get("sc_vorlage_loeschen_ja")):
        st.session_state["sc_vorlage_meldung_oben"] = (
            "fehler", "Wähle bitte zuerst eine Vorlage und bestätige das Löschen.", None)
        return
    vorlagen, sha_oder_grund = _sc_vorlagen_frisch()
    if vorlagen is None:
        st.session_state["sc_vorlage_meldung_oben"] = (
            "fehler", "Die Vorlage ist nicht gelöscht; versuche es bitte später noch einmal.", sha_oder_grund)
        return
    rest, gefunden = sa.vorlage_entfernen(vorlagen, name)
    if not gefunden:
        st.session_state["sc_vorlage_meldung_oben"] = ("fehler", "Diese Vorlage gibt es nicht mehr.", None)
        return
    ok, grund = _sc_vorlagen_schreiben(rest, sha_oder_grund, f"Scanner-Vorlage gelöscht: {name}")
    st.session_state["sc_vorlage_loeschen_ja"] = False
    if ok:
        st.session_state["sc_vorlage_wahl"] = None
        st.session_state["sc_vorlage_meldung_oben"] = ("ok", f"Vorlage {name} gelöscht.", None)
    else:
        st.session_state["sc_vorlage_meldung_oben"] = (
            "fehler", "Die Vorlage ist nicht gelöscht; versuche es bitte später noch einmal.", grund)


def _sc_scan_anfordern():
    st.session_state["sc_scan_auftrag"] = True


# Dieselbe Angabe wie auf dem Knopf als Statusmeldung fuer Screenreader, die den
# Wechsel der Beschriftung am fokussierten Knopf nicht von selbst vorlesen. Die
# Meldung braucht einen Knoten, der bleibt: st.html ersetzt seinen Inhalt bei
# jeder Aenderung samt Knoten (gemessen 15.09.2026 im Browser), und ein neu
# eingesetzter Knoten wird oft nicht angesagt. Die Komponente legt den Knoten
# deshalb einmal unsichtbar an und aendert danach nur seinen Text, und nur,
# wenn er sich aendert.
_SC_STATUS_JS = """export default function (component) {
  const text = String((component.data || {}).text || "");
  let el = document.getElementById("heliot_scan_status");
  if (!el) {
    el = document.createElement("div");
    el.id = "heliot_scan_status";
    el.setAttribute("role", "status");
    el.setAttribute("aria-live", "polite");
    el.style.cssText = "position:absolute;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;"
      + "clip:rect(0 0 0 0);white-space:nowrap;border:0;";
    document.body.appendChild(el);
  }
  if (el.textContent !== text) {
    el.textContent = text;
  }
}
"""
_sc_status = st.components.v2.component("heliot_scan_status", js=_SC_STATUS_JS)


def _sc_wien_uhrzeit() -> str:
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Europe/Vienna")).strftime("%H:%M")


def _sc_meldung_zeigen(meldung):
    """Eine Meldung der Vorlagen: (Art, Satz, technischer Grund oder None)."""
    art, satz, technik = (tuple(meldung) + (None, None, None))[:3]
    if art == "ok":
        erfolg(satz)
    else:
        fehler(satz, technik)


def _sc_scannen(vergleich: dict) -> dict:
    """Ein Scan: Tabelle, Kennzahlen und Analystenwerte holen, auswerten. Das
    Ergebnis bleibt bis zum naechsten Scan stehen."""
    erg = {"vergleich": vergleich, "uhrzeit": _sc_wien_uhrzeit(), "zeitpunkt": zeit_wien(time.time()),
           "hinweise": [], "technik": [], "klang": str(time.time_ns())}
    tabelle, grund = lade_scanner_tabelle()
    stand = lade_scanner_stand() or {}
    erg["stand"] = stand
    if tabelle is None:
        erg["fehlt"] = "Die Scanner-Tabelle ist noch nicht da. Sie entsteht jede Nacht nach dem Nachtscan."
        if grund:
            erg["technik"].append(grund)
        erg["treffer"] = 0
        return erg
    if any(s not in tabelle.columns for s in sa.sd.KENNZAHL_SPALTEN):
        ergaenzt, hinweis = _scanner_kennzahlen_nachtragen(stand.get("handelstag"))
        if ergaenzt is not None and len(ergaenzt) == len(tabelle):
            tabelle = ergaenzt
        if hinweis:
            erg["hinweise"].append(hinweis)
    if "cm_f" not in tabelle.columns:
        erg["hinweise"].append("Die weiteren Chartmuster stehen erst nach dem nächsten Bau der Scanner-Tabelle "
                               "bei den Treffern.")
    analysten, analysten_grund = lade_scanner_analysten()
    analysten_da = analysten is not None
    if analysten_da:
        tabelle = tabelle.merge(analysten, on="ticker", how="left")
    elif _daten_token():
        erg["hinweise"].append("Die Analystendaten ließen sich nicht laden; die Merkmale dazu zeigen und filtern "
                               "deshalb nichts.")
        erg["technik"].append(analysten_grund)
    sektoren = sa.sektoren_in(tabelle)
    heute = sa.ny_jetzt().date()
    ausw = sa.auswerten(tabelle, _sc_einstellung(sektoren), heute, analysten_da)
    erg.update({"ausw": ausw, "treffer": len(ausw["df"]), "sektor_tabelle": tabelle[["sektor"]].copy()
                if "sektor" in tabelle.columns else None})
    return erg


def _sc_neu_zeichnen():
    """Nach dem Scan nur den Scanner neu zeichnen; laeuft der Scanner gerade als
    Teil der ganzen Seite, die ganze Seite."""
    from streamlit.errors import StreamlitAPIException
    try:
        st.rerun(scope="fragment")
    except StreamlitAPIException:
        st.rerun()


def _sc_ergebnis_zeigen(erg: dict, geaendert: bool):
    """Das Ergebnis des letzten Scans; die Einstellungen darueber aendern es nicht."""
    if erg.get("fehlt"):
        st.info(erg["fehlt"])
        for grund in erg.get("technik") or []:
            st.caption(technik_zeile(grund))
        return
    # Der Ton je Scan: Das Ergebnis wird bei jedem Lauf des Scanners neu
    # gezeichnet, der Ton kommt nur einmal (Kennung aus _sc_scannen).
    klang(erg.get("klang"))
    ausw = erg["ausw"]
    stand = erg.get("stand") or {}
    if geaendert:
        st.warning("Die Einstellungen wurden seit dem letzten Scan geändert. Die Liste zeigt noch das Ergebnis des "
                   "letzten Scans; mit dem Knopf Scan starten gilt die neue Einstellung.")
    st.markdown(f"### Ergebnis: {nachschlagen.zahl(erg['treffer'])} von {nachschlagen.zahl(ausw['gesamt'])} Aktien",
                anchors=False)
    # Tag, Monat, Jahr und Wiener Zeit (Antwort 99 vom 24.09.2026)
    satz = ("Scan vom " + erg["zeitpunkt"]) if erg.get("zeitpunkt") else f"Scan von {erg['uhrzeit']} Uhr Wiener Zeit"
    if stand.get("handelstag"):
        satz += f", Schlusskurse vom {sa.datum_lang(stand['handelstag'])}"
    st.markdown(sa.md(satz + "."))
    teile = sa.einstellungs_teile(ausw["einstellung"], erg.get("sektor_tabelle"))
    st.markdown(sa.md("Eingestellt: " + ("; ".join(teile) if teile else "nichts, die Liste zeigt den ganzen Markt") + "."))
    for hinweis in list(erg.get("hinweise") or []) + list(ausw["hinweise"]):
        st.warning(sa.md(hinweis))
    for grund in erg.get("technik") or []:
        st.caption(technik_zeile(grund))
    # Die Fehler gehoeren zum Scan: Der Ton spielt einmal je Scan, nicht bei
    # jedem Lauf, der das Ergebnis wieder zeichnet.
    for i, fehler_satz in enumerate(ausw["fehler"]):
        fehler(sa.md(fehler_satz), kennung=f"{erg.get('klang')}_fehler_{i}")
    sortier = sa.sortier_wahl(ausw["einstellung"])
    if st.session_state.get("sc_sortierung") not in [x for x, _t in sortier]:
        st.session_state["sc_sortierung"] = sortier[0][0]
    st.selectbox("Sortieren nach", [x for x, _t in sortier], format_func=dict(sortier).get, key="sc_sortierung",
                 placeholder="Bitte wählen")
    # Umsortieren braucht keinen neuen Scan: dieselben Treffer in anderer Reihenfolge.
    ausw = {**ausw, "df": sa.sortieren(ausw, st.session_state["sc_sortierung"])}
    anzahlen = ["25", "50", "100", "250", "alle"]
    if st.session_state.get("sc_anzahl") not in anzahlen:
        st.session_state["sc_anzahl"] = "50"
    anzahl = st.selectbox("Wie viele Aktien die Liste zeigt", anzahlen,
                          format_func=lambda x: "Alle" if x == "alle" else f"Die ersten {x}", key="sc_anzahl",
                          placeholder="Bitte wählen")
    basis = app_adresse()
    anzahl_treffer = erg["treffer"]
    if not anzahl_treffer:
        st.info("Keine Aktie erfüllt alle Einstellungen.")
        return
    grenze = None if anzahl == "alle" else int(anzahl)
    st.markdown("\n".join(sa.zeilen(ausw, basis, anzahl=grenze)))
    if grenze and anzahl_treffer > grenze:
        st.caption(f"Die übrigen {nachschlagen.zahl(anzahl_treffer - grenze)} Aktien stehen in der Datei.")
    formate = [x[0] for x in sa.FORMATE]
    if st.session_state.get("sc_format") not in formate:
        st.session_state["sc_format"] = "xlsx"
    fmt = st.selectbox("Dateiformat", formate, format_func={x[0]: x[1] for x in sa.FORMATE}.get, key="sc_format",
                       placeholder="Bitte wählen", persist_state="page")
    st.download_button("Ergebnis als Datei herunterladen",
                       data=lambda: sa.datei(ausw, basis, fmt, stand, erg.get("sektor_tabelle"))[0],
                       file_name=sa.dateiname(ausw, stand, fmt),
                       mime=next(x[3] for x in sa.FORMATE if x[0] == fmt), on_click="ignore", key="sc_download")
    # UEBERGABE (Gerhard, 20.09.2026, S2): nur mit vollem Zugang, weil sie die
    # Wochen- oder Darvas-Liste ersetzt.
    if rolle == "voll":
        _sc_uebergabe(erg, ausw)


def _sc_uebergabe(erg: dict, ausw: dict):
    """Die Treffer als Wochen- oder Darvas-Liste an das Programm uebergeben
    (Gerhard, 20.09.2026, S2): "Eine im Scanner erzeugte Liste soll ich direkt
    an das Programm uebergeben koennen, als Wochenliste oder als Darvas-Liste.
    Vor der Uebergabe brauche ich einen Bearbeitungsmodus: pro Aktie ein
    Kontrollfeld, mit dem ich sie abwaehlen kann."

    Uebergeben werden alle Treffer in der eingestellten Reihenfolge, nicht nur
    die angezeigten. Die Abwahl gehoert zum Ergebnis (erg["nr"]): Ein neuer
    Scan beginnt wieder mit allen angehakt, und die Abwahl des vorigen faellt
    weg. Eingespielt wird erst nach Wahl der Liste und Bestaetigung, auf
    demselben Weg wie beim Upload.

    DIE ABWAHL STEHT IN EINEM EIGENEN EINTRAG (sc_ueb_abgewaehlt), nicht im
    Zustand der Kontrollfelder: Diese gibt es nur, solange der Bearbeitungsmodus
    offen ist, und den Wert eines nicht gezeichneten Felds raeumt Streamlit weg
    (gemessen 21.09.2026 im Testrahmen AppTest sogar trotz persist_state). Ein
    eigener Eintrag bleibt fuer die ganze Sitzung, und die Kontrollfelder werden
    bei jedem Zeichnen aus ihm gesetzt. Eine abgewaehlte Aktie kann so nie still
    wieder in die Liste rutschen."""
    st.markdown("#### Ergebnis als Liste übergeben", anchors=False)
    alle = [str(t) for t in ausw["df"]["ticker"].tolist()]
    if len(alle) > sa.UEBERGABE_GRENZE:
        st.markdown(f"Übergeben lassen sich höchstens {nachschlagen.zahl(sa.UEBERGABE_GRENZE)} Aktien; dieser Scan "
                    f"hat {nachschlagen.zahl(len(alle))} Treffer. Scanne bitte mit engeren Einstellungen neu.")
        return
    nr = erg.setdefault("nr", time.time_ns())
    modell = st.session_state.get("sc_ueb_abgewaehlt")
    if not isinstance(modell, dict) or modell.get("nr") != nr:
        alt = modell.get("nr") if isinstance(modell, dict) else None
        for k in list(st.session_state.keys()):
            if str(k).startswith((f"sc_ueb_{alt}_", f"sc_ueb_ja_{alt}")) or k == "sc_ueb_meldung":
                del st.session_state[k]
        modell = {"nr": nr, "ticker": set()}
        st.session_state["sc_ueb_abgewaehlt"] = modell
    abgewaehlt = modell["ticker"]
    namen = dict(zip(alle, ausw["df"]["name"].tolist())) if "name" in ausw["df"].columns else {}
    st.markdown(f"Übergeben werden alle {nachschlagen.zahl(len(alle))} Treffer, nicht nur die angezeigten; im "
                "Bearbeitungsmodus lassen sich einzelne abwählen. Die gewählte Liste wird ersetzt, die andere "
                "bleibt, wie sie ist.")
    if st.checkbox("Bearbeitungsmodus: Aktien einzeln abwählen", key="sc_ueb_bearbeiten", persist_state="page"):
        st.button("Alle anhaken", key="sc_ueb_alle", on_click=_sc_uebergabe_setzen, args=(alle, True))
        st.button("Alle abhaken", key="sc_ueb_keine", on_click=_sc_uebergabe_setzen, args=(alle, False))
        for t in alle:
            schluessel = f"sc_ueb_{nr}_{t}"
            st.session_state[schluessel] = t not in abgewaehlt
            st.checkbox(sa.uebergabe_zeile(t, namen.get(t)), key=schluessel, on_change=_sc_uebergabe_haken,
                        args=(schluessel, t))
    gewaehlt = [t for t in alle if t not in abgewaehlt]
    # Grosse Liste und Darvas-Liste, zusammen Wochenlisten (Antwort 86 vom 24.09.2026)
    ziele = {LISTEN_DATEI: f"Große Liste {LISTEN_DATEI}: alle Strategien außer Darvas",
             DARVAS_DATEI: f"Darvas-Liste {DARVAS_DATEI}: dort laufen alle Strategien"}
    if st.session_state.get("sc_ueb_ziel") not in ziele:
        st.session_state["sc_ueb_ziel"] = None
    st.selectbox("Welche Liste ersetzt wird", list(ziele), key="sc_ueb_ziel", format_func=ziele.get,
                 placeholder="Bitte wählen")
    ziel = st.session_state.get("sc_ueb_ziel")
    st.markdown(sa.uebergabe_satz(len(gewaehlt), len(alle), ziel))
    bestaetigt = st.checkbox(f"Ja, die gewählte Liste durch diese {nachschlagen.zahl(len(gewaehlt))} Aktien ersetzen",
                             key=f"sc_ueb_ja_{nr}", disabled=not (ziel and gewaehlt))
    if st.button("Liste übergeben", key="sc_ueb_los", type="primary",
                 disabled=not (ziel and gewaehlt and bestaetigt)):
        # Die dritte Angabe ist die Kennung fuer den Ton: Die Meldung steht bei
        # jedem Lauf wieder da, der Ton kommt nur einmal.
        st.session_state["sc_ueb_meldung"] = (nr, _sc_uebergabe_ausfuehren(gewaehlt, namen, ziel),
                                              str(time.time_ns()))
    meldung = st.session_state.get("sc_ueb_meldung")
    if meldung and meldung[0] == nr:
        art, satz, technik = (tuple(meldung[1]) + (None, None, None))[:3]
        kennung = meldung[2] if len(meldung) > 2 else None
        if art == "ok":
            erfolg(satz, kennung)
        elif art == "teil":
            st.warning(satz)
            if technik:
                st.caption(technik_zeile(technik))
        else:
            fehler(satz, technik, kennung)


def _sc_uebergabe_haken(schluessel: str, t: str):
    """Ein Kontrollfeld des Bearbeitungsmodus wurde umgeschaltet."""
    modell = st.session_state.get("sc_ueb_abgewaehlt")
    if not isinstance(modell, dict):
        return
    if st.session_state.get(schluessel, True):
        modell["ticker"].discard(t)
    else:
        modell["ticker"].add(t)


def _sc_uebergabe_setzen(alle, an: bool):
    modell = st.session_state.get("sc_ueb_abgewaehlt")
    if isinstance(modell, dict):
        modell["ticker"] = set() if an else set(alle)


def _sc_listen_roh() -> tuple:
    """Die beiden Wochenlisten, wie sie auf main stehen (oeffentlich lesbar),
    erst die Darvas-Liste, dann die grosse, wie listen.alle_ticker; Rueckfall
    ist die Datei im Arbeitsverzeichnis der App."""
    import requests
    raus = []
    for datei in (DARVAS_DATEI, LISTEN_DATEI):
        inhalt = None
        try:
            r = requests.get(f"https://raw.githubusercontent.com/{REPO}/main/{datei}", timeout=15)
            if r.status_code == 200:
                inhalt = r.content
        except Exception:  # noqa
            pass
        if inhalt is None:
            try:
                with open(datei, "rb") as f:
                    inhalt = f.read()
            except OSError:
                inhalt = None
        raus.append(inhalt)
    return tuple(raus)


def _sc_uebergabe_ausfuehren(gewaehlt: list, namen: dict, ziel: str) -> tuple:
    """Baut die Liste im Finviz-Format (sa.uebergabe_csv), prueft sie wie einen
    Upload und spielt sie auf jedem Zweig ein, der die Liste fuehrt. Der Sektor
    kommt aus der bisherigen Finviz-Zeile einer Aktie, sonst aus dem
    Nachschlagen (erst Wochenlisten, dann Yahoo). Liefert (Art, Satz,
    technischer Grund oder None) mit Art ok, teil oder fehler."""
    token = (_secret("GITHUB_TOKEN") or "").strip()
    if not token:
        return "fehler", "Die Liste ist nicht übergeben.", "In den Streamlit-Secrets fehlt GITHUB_TOKEN."
    finviz = sa.finviz_zeilen(*_sc_listen_roh())
    fehlend = [t for t in gewaehlt if t not in finviz]
    sektoren = {}
    if fehlend:
        gesamt = nachschlagen.zahl(len(fehlend))
        balken = st.progress(0.0, text=f"Sektor nachschlagen: 0 von {gesamt}")
        for i, t in enumerate(fehlend, 1):
            try:
                sektoren[t] = nachschlag_sektor(t)[0]
            except Exception:  # noqa
                sektoren[t] = None
            balken.progress(i / len(fehlend), text=f"Sektor nachschlagen: {nachschlagen.zahl(i)} von {gesamt}")
        balken.empty()
    roh = sa.uebergabe_csv(gewaehlt, namen, finviz, sektoren)
    fehler_text, ticker = pruefe_wochenliste(roh)
    if fehler_text:
        return "fehler", "Die Liste ist nicht übergeben: " + fehler_text, None
    fehler_text, zweige = wochenliste_einspielen(roh, token, len(ticker), ziel, herkunft="Übergabe aus dem Scanner")
    # Der Zaehler wird auch bei einem Teilerfolg geleert: Auf mindestens einem
    # Zweig steht die neue Liste.
    if zweige:
        aktuelle_listengroesse.clear()
    if fehler_text:
        if zweige:
            return "teil", "Die Liste ist nur teilweise übergeben.", fehler_text
        return "fehler", "Die Liste ist nicht übergeben; versuche es bitte später noch einmal.", fehler_text
    satz = (f"Übergeben in {ziel} auf {zweige}: {nachschlagen.zahl(len(ticker))} Aktien, "
            f"die ersten: {', '.join(ticker[:5])}. Ab dem nächsten nächtlichen Scan aktiv.")
    ohne = [t for t in fehlend if not sektoren.get(t)]
    if ohne:
        satz += (f" Für {nachschlagen.zahl(len(ohne))} Aktien war kein Sektor feststellbar, darunter "
                 + ", ".join(ohne[:5]) + "; für sie fehlen Sektor-Rang und Sektorhinweis.")
    return "ok", satz, None


def _sc_erklaerung(schluessel: str, titel: str, text: str, frage: str | None = None):
    """Der Erklaerungsknopf unter einem Kriterium (Mathias und Gerhard, 23.09.2026):
    "eine Schaltflaeche unter wirklich jedem Kriterium, die bei Anklicken eine
    kurze Erklaerung des Kriteriums auf Deutsch liefert". Die Beschriftung ist eine
    Frage (Antwort 11 vom 24.09.2026): "Was ist <Kriterium>?"; wo ein Kriterium
    keine Sache benennt, eine Frage mit demselben Anfang (frage). Sie bleibt immer
    dieselbe, damit der Fokus beim Klick nicht verloren geht. Die Erklaerung
    erscheint nur auf Knopfdruck, nicht beim Anhaken (Antwort 12): Ein Klick zeigt
    sie direkt darunter, der naechste blendet sie aus."""
    k = f"sc_erkl_{schluessel}"
    sichtbar = bool(st.session_state.get(k))
    st.button(frage or f"Was ist {titel}?", key=f"{k}_knopf", type="tertiary",
              on_click=erklaerung_umschalten, args=(k, sichtbar))
    if sichtbar:
        st.caption(text)


@st.fragment
def scanner_reiter():
    """Der Reiter als Fragment: Ein Klick im Scanner rechnet nur den Scanner
    neu, nicht die ganze Seite. Die Tabelle holt erst der Knopf Scan starten."""
    stand = lade_scanner_stand() or {}
    lese_token = bool(_daten_token())
    for satz in sa.stand_saetze(stand, analysten_da=lese_token, nur_voll=rolle != "voll"):
        st.markdown(sa.md(satz))
    for satz in sa.stand_technik(stand, analysten_da=lese_token, nur_voll=rolle != "voll"):
        st.caption(sa.md(technik_zeile(satz)))

    sektoren = sa.sektoren_in(None)
    st.session_state["sc_sektorliste"] = sektoren
    if not st.session_state.get("sc_bereit"):
        _sc_alles_zuruecksetzen()
        st.session_state["sc_anzahl"] = "50"
        st.session_state["sc_format"] = "xlsx"
        st.session_state["sc_bereit"] = True
    for s in sektoren:
        if _sc_sektor_schluessel(s) not in st.session_state:
            st.session_state[_sc_sektor_schluessel(s)] = True
    heute = sa.ny_jetzt().date()

    # VORLAGEN (Gerhard, 20.09.2026, S1): Die Datei liegt im privaten Datenrepo,
    # deshalb nur im vollen Zugang (S4). Laden setzt alle Bedienfelder, dann
    # rechnet wie immer erst der Knopf Scan starten.
    if rolle == "voll":
        st.markdown("### Vorlagen", anchors=False)
        try:
            sc_vorlagen, _sc_sha = _sc_vorlagen_holen()
            sc_vorlagen_grund = ""
        except LookupError as e:
            sc_vorlagen, sc_vorlagen_grund = [], str(e)
        except Exception as e:  # noqa
            sc_vorlagen, sc_vorlagen_grund = [], f"Netzwerkfehler {type(e).__name__}"
        if sc_vorlagen_grund:
            st.markdown("Die Vorlagen lassen sich gerade nicht laden.")
            st.caption(technik_zeile(sc_vorlagen_grund))
        sc_namen = [v["name"] for v in sc_vorlagen]
        if sc_namen:
            sc_beschriftung = {v["name"]: sa.vorlage_beschriftung(v) for v in sc_vorlagen}
            if st.session_state.get("sc_vorlage_wahl") not in sc_namen:
                st.session_state["sc_vorlage_wahl"] = None
            st.selectbox("Gespeicherte Vorlage", sc_namen, key="sc_vorlage_wahl",
                         format_func=lambda n: sc_beschriftung.get(n, n), placeholder="Bitte wählen",
                         persist_state="page")
            sc_gewaehlt = bool(st.session_state.get("sc_vorlage_wahl"))
            st.button("Vorlage laden", key="sc_vorlage_laden", on_click=_sc_vorlage_laden, disabled=not sc_gewaehlt)
            st.checkbox("Ja, die gewählte Vorlage löschen", key="sc_vorlage_loeschen_ja", persist_state="page")
            st.button("Vorlage löschen", key="sc_vorlage_loeschen", on_click=_sc_vorlage_loeschen,
                      disabled=not (sc_gewaehlt and st.session_state.get("sc_vorlage_loeschen_ja")))
        elif not sc_vorlagen_grund:
            st.markdown("Noch keine Vorlage gespeichert; speichern lässt sich unten vor dem Scan.")
        sc_meldung = st.session_state.pop("sc_vorlage_meldung_oben", None)
        if sc_meldung:
            _sc_meldung_zeigen(sc_meldung)

    # Teil 1
    st.markdown("### Teil 1: Strategie oder Chart-Signal", anchors=False)
    ids = [k for k, _name in sa.AUSWAHL]
    if st.session_state.get("sc_strategie") not in ids:
        st.session_state["sc_strategie"] = ""
    st.selectbox("Strategie oder Chart-Signal", ids, format_func=sa.AUSWAHL_NAMEN.get, key="sc_strategie",
                 on_change=_sc_strategie_gewaehlt, placeholder="Bitte wählen")
    _sc_erklaerung("strategie", "Strategie oder Chart-Signal", oberflaeche.SCANNER_ERKLAERUNGEN["strategie"],
                   frage="Was ist eine Strategie oder ein Chart-Signal?")
    k = st.session_state.get("sc_strategie") or ""
    if sa.strategie_text(k):
        st.markdown(sa.md(sa.strategie_text(k)))
    if sa.ist_muster(k) and sa.treffer_satz(stand, k):
        st.markdown(sa.md(sa.treffer_satz(stand, k)))
    if sa.toleranz_moeglich(k):
        if st.session_state.get("sc_toleranz") not in ("streng", "toleranz"):
            st.session_state["sc_toleranz"] = "streng"
        tol = sa.toleranz_prozent()
        st.radio("Wie genau das Muster passen muss", ["streng", "toleranz"],
                 format_func={"streng": "Streng: jede Regel des Musters erfüllt",
                              "toleranz": f"Mit {tol} Prozent Toleranz: Schwellen dürfen um {tol} Prozent "
                                          "verfehlt werden"}.get,
                 key="sc_toleranz", on_change=_sc_toleranz_geaendert, persist_state="page")
        _sc_erklaerung("toleranz", "Wie genau das Muster passen muss", oberflaeche.SCANNER_ERKLAERUNGEN["toleranz"],
                       frage="Was ist die Toleranz?")
    st.checkbox(sa.handelbar_text(), key="sc_handelbar")
    _sc_erklaerung("handelbar", "Nur handelbare Aktien", oberflaeche.SCANNER_ERKLAERUNGEN["handelbar"],
                   frage="Was ist eine handelbare Aktie?")
    if k == "darvas":
        st.checkbox(sa.langweile_text(), key="sc_langweilig", persist_state="page")
        _sc_erklaerung("langweilig", "Langweilige Darvas-Boxen aussortieren",
                       oberflaeche.SCANNER_ERKLAERUNGEN["langweilig"], frage="Was ist eine langweilige Darvas-Box?")

    # Teil 2
    st.markdown("### Teil 2: Einstellungen", anchors=False)
    for g, gname in sa.GRUPPEN:
        felder = [f for f in sa.FELDER if f.gruppe == g]
        n_an = sum(1 for f in felder if st.session_state.get(_sc_schluessel(f.schluessel, "an")))
        # Ein Kontrollfeld statt st.expander: Streamlit 1.63 schreibt vor die
        # Beschriftung eines Ausklappers das Symbolwort keyboard_arrow_right, und
        # ein Screenreader liest es vor (gemessen 14.09.2026). Alles Verborgene
        # behaelt seinen Wert (persist_state), eine zugeklappte Gruppe filtert weiter.
        # Gezaehlt wird ueberall "N von M angehakt" (Antwort 15 vom 24.09.2026).
        st.markdown(f"#### {gname}", anchors=False)
        if st.checkbox(f"Gruppe {gname} anzeigen, {n_an} von {len(felder)} angehakt", key=f"sc_gruppe_{g}"):
            if any(f.analysten for f in felder) and not lese_token:
                # Leerverkaeufe und Branchengruppe sind keine Analystendaten (Berichtigung 12)
                st.caption(("Diese Daten sind nicht geladen" if g in ("short", "gruppe")
                            else "Die Analystendaten sind nicht geladen")
                           + "; diese Merkmale zeigen und filtern deshalb nichts.")
            for f in felder:
                an = st.checkbox(f.titel, key=_sc_schluessel(f.schluessel, "an"), persist_state="page")
                _sc_erklaerung(f.schluessel, f.titel, f.erklaerung)
                if not an or f.art != "bereich":
                    continue
                for teil in ("min", "max"):
                    st.text_input(f.eingabe_titel(teil), key=_sc_schluessel(f.schluessel, teil),
                                  placeholder=f.eingabe_hinweis(teil), persist_state="page")
                if f.schluessel == "rs":
                    st.checkbox("Junge Titel mit vorläufigem RS mitnehmen", key="sc_rs_vorlaeufig",
                                persist_state="page")
                    _sc_erklaerung("rs_vorlaeufig", "Junge Titel mit vorläufigem RS mitnehmen",
                                   oberflaeche.SCANNER_ERKLAERUNGEN["rs_vorlaeufig"],
                                   frage="Was ist ein vorläufiges RS?")

    st.markdown("#### Zahlentermine", anchors=False)
    termine_an = st.checkbox("Nach Zahlenterminen filtern", key="sc_termine_an")
    _sc_erklaerung("termine", "Nach Zahlenterminen filtern", oberflaeche.SCANNER_ERKLAERUNGEN["termine"],
                   frage="Was ist der Filter nach Zahlenterminen?")
    if termine_an:
        st.caption(f"Heute ist in New York {sa.datum_lang(heute.isoformat())}; morgen heißt der nächste "
                   f"Werktag, {sa.datum_lang(sa.naechster_handelstag(heute).isoformat())}.")
        for key, text, _plus, _lage in sa.TERMIN_TEILE:
            st.checkbox(f"Zahlen {text}", key=f"sc_termine_{key}", persist_state="page")
            _sc_erklaerung(f"termine_{key}", f"Zahlen {text}", oberflaeche.SCANNER_ERKLAERUNGEN[f"termine_{key}"],
                           frage=f"Was ist mit „Zahlen {text}“ gemeint?")
        st.checkbox("Auch Termine während des Handels oder ohne bekannte Tageszeit",
                    key="sc_termine_ohne_zeit", persist_state="page")
        _sc_erklaerung("termine_ohne_zeit", "Auch Termine während des Handels oder ohne bekannte Tageszeit",
                       oberflaeche.SCANNER_ERKLAERUNGEN["termine_ohne_zeit"],
                       frage="Was ist mit „Auch Termine während des Handels oder ohne bekannte Tageszeit“ gemeint?")
        st.radio("Welche Aktien", [u[0] for u in sa.UMFANG], format_func=dict(sa.UMFANG).get,
                 key="sc_termine_umfang", persist_state="page")
        _sc_erklaerung("termine_umfang", "Welche Aktien", oberflaeche.SCANNER_ERKLAERUNGEN["termine_umfang"],
                       frage="Was ist mit „Welche Aktien“ gemeint?")

    gewaehlt = sum(1 for s in sektoren if st.session_state.get(_sc_sektor_schluessel(s), True))
    st.markdown("#### Sektoren", anchors=False)
    if st.checkbox(f"Gruppe Sektoren anzeigen, {gewaehlt} von {len(sektoren)} angehakt", key="sc_gruppe_sektoren"):
        st.button("Alle Sektoren anhaken", key="sc_sektoren_alle", on_click=_sc_sektoren_setzen, args=(True,))
        st.button("Alle Sektoren abhaken", key="sc_sektoren_keine", on_click=_sc_sektoren_setzen, args=(False,))
        for s in sektoren:
            st.checkbox(sa.sektor_name(s), key=_sc_sektor_schluessel(s), persist_state="page")
            _sc_erklaerung(_sc_sektor_schluessel(s)[3:], sa.sektor_name(s),
                           oberflaeche.SEKTOR_ERKLAERUNGEN.get(s, "Aktien, die die Nasdaq diesem Sektor zuordnet."),
                           frage=(f"Was ist der Sektor {sa.sektor_name(s)}?" if s
                                  else f"Was ist mit „{sa.OHNE_SEKTOR}“ gemeint?"))
    # Der Knopf steht am Ende von Teil 2, vor dem Scan (Antwort 70 vom 24.09.2026):
    # Er setzt Teil 1 und Teil 2 zurueck.
    st.button("Alle Einstellungen zurücksetzen", key="sc_zuruecksetzen", on_click=_sc_alles_zuruecksetzen)

    # Scan: nur mit dem Knopf (Auftrag 2)
    vergleich = sa.wirksame_einstellung(_sc_einstellung(sektoren))
    ergebnis = st.session_state.get("sc_ergebnis")
    laeuft = bool(st.session_state.get("sc_scan_auftrag"))
    geaendert = bool(ergebnis) and ergebnis.get("vergleich") != vergleich
    # Der Knopf heisst immer Scan starten; die Trefferzahl steht in der
    # Ueberschrift des Ergebnisses (Antwort 68 vom 24.09.2026). Nur waehrend des
    # Laufs sagt er, dass gescannt wird (Gerhard, 15.09.2026, Auftrag 2).
    beschriftung = "Scan läuft, warte bitte" if laeuft else "Scan starten"
    # Die Statusmeldung wechselt nur mit dem Scan selbst, nie mit den
    # Einstellungen; sonst meldete ein Screenreader "Scan fertig", sobald eine
    # Einstellung wieder auf dem Stand des letzten Scans steht.
    if laeuft:
        status = "Scan läuft."
    elif ergebnis:
        status = ("Scan fertig: keine Tabelle." if ergebnis.get("fehlt")
                  else f"Scan fertig: {nachschlagen.zahl(ergebnis['treffer'])} Treffer.")
    else:
        status = ""
    if rolle == "voll":
        st.markdown("### Einstellungen als Vorlage speichern", anchors=False)
        st.text_input("Name der Vorlage", key="sc_vorlage_name", max_chars=sa.VORLAGE_NAME_LAENGE,
                      placeholder="Zum Beispiel Minervini streng", persist_state="page")
        st.button("Aktuelle Einstellungen als Vorlage speichern", key="sc_vorlage_speichern",
                  on_click=_sc_vorlage_speichern)
        sc_meldung_u = st.session_state.pop("sc_vorlage_meldung_unten", None)
        if sc_meldung_u:
            _sc_meldung_zeigen(sc_meldung_u)
    st.markdown("### Scan", anchors=False)
    st.button(beschriftung, key="sc_scan", type="primary", on_click=_sc_scan_anfordern)
    _sc_status(key="sc_scan_status", data={"text": status})
    if laeuft:
        try:
            st.session_state["sc_ergebnis"] = _sc_scannen(vergleich)
        finally:
            st.session_state["sc_scan_auftrag"] = False
        _sc_neu_zeichnen()
    if ergebnis:
        _sc_ergebnis_zeigen(ergebnis, geaendert)


with tab_scanner:
    # Streamlit schreibt unter ein Textfeld mit ungespeicherter Eingabe den
    # englischen Hinweis "Press Enter to apply", und ein Screenreader liest ihn
    # beim Weiterlesen vor (gemessen 14.09.2026). Ausgeblendet wird er nur im
    # Scanner; eine Eingabe gilt dort spaetestens beim Druck auf Scan starten,
    # weil das Feld dabei verlassen wird.
    st.html("<style>.st-key-scanner_bereich [data-testid='InputInstructions'] {display: none;}</style>")
    # Jeder Reiter beginnt mit seinem Namen als Ueberschrift der Ebene 2
    # (Antwort 27 vom 24.09.2026); fuer Gaeste steht sie schon darueber.
    if rolle != "gast":
        st.markdown("## Scanner", anchors=False)
    with st.container(key="scanner_bereich"):
        scanner_reiter()


# S4 GASTZUGANG ABGESCHOTTET (Gerhard, 20.09.2026): Fuer Gaeste endet der Lauf
# hier, hinter dem Scanner. Liste pruefen, Aktueller Scan und Regelwerk gibt es
# fuer sie nicht (tab_liste ist None). Die Gesamtpruefung (Block H) achtet
# darauf, dass das so bleibt.
if tab_liste is None:
    abmelden_zeigen()
    st.stop()


# --- Liste pruefen ---------------------------------------------------------
# DAS ERGEBNIS BLEIBT STEHEN (Antworten 54 und 103 vom 24.09.2026): Die Wahl des
# Dateiformats und das Kontrollfeld fuer die Tabelle loesen einen neuen Lauf aus;
# das Ergebnis steht deshalb im Sitzungszustand, nicht nur im Lauf des Knopfs.
# CHARTMUSTER DER SCANNER-TABELLE (Antwort 40): Bei jeder Aktie stehen die
# weiteren Chartmuster in denselben Worten wie beim Nachschlagen, mit der Zeile
# der Scanner-Tabelle, wo es eine gibt. SPALTEN ALS ZAHLEN (Antwort 41): RS und
# die Ziele stehen als Zahlen, damit die Tabelle richtig sortiert.
def _lp_rechnen(tickers: list, nur_treffer: bool) -> dict:
    fortschritt = st.progress(0.0)
    status = st.empty()
    zeilen, texte, fehlend = [], [], []
    rs_eintraege = nachschlagen.eintraege(nachschlag_dateien().get("rs_universum.json"))
    try:
        nacht_tabelle = lade_scanner_tabelle()[0]
    except Exception:  # noqa
        nacht_tabelle = None
    for i, t in enumerate(tickers, 1):
        status.text(f"{i} von {len(tickers)}: {t}")
        rs_wert, _ = nachschlagen.rs_fuer_muster(rs_eintraege.get(t))
        try:
            df, res = analysiere(t, api_key, rs_wert)
        except Exception:  # noqa
            df, res = None, None
        if df is None:
            fehlend.append(t)
        else:
            echte = [p for p in res["points"] if not p["strategie"].startswith("Fallback")]
            if not (nur_treffer and not echte):
                try:
                    nachtzeile = nachschlagen.analysten_zeile(nacht_tabelle, t) if nacht_tabelle is not None else None
                    weitere = nachschlagen.chartmuster_saetze(df, nachtzeile=nachtzeile)
                except Exception:  # noqa
                    weitere = []
                zeile = {
                    "Ticker": t,
                    "Kurs": round(res["close"], 2),
                    "RS": int(rs_wert) if rs_wert is not None else None,
                    "52W-Hoch": round(res["hi52"], 2),
                    "Abst. Hoch": f"{(res['close'] / res['hi52'] - 1) * 100:+.1f}%",
                    "Trend Template": ("erfüllt, 8 von 8" if res["tt_pass"] else f"{res['tt_count']} von 8"),
                    "Muster": len(echte),
                }
                for n, p in enumerate(res["points"], 1):
                    zeile[f"KP{n} Strategie"] = p["strategie"]
                    zeile[f"KP{n} Preis"] = p["kaufpunkt"]
                    zeile[f"KP{n} Stop"] = p["stop"]
                    zeile[f"KP{n} Ziel"] = p["ziel"] if p["ziel"] else None
                    zeile[f"KP{n} Status"] = p["status"]
                zeile["Weitere Chartmuster"] = " ".join(weitere)
                zeilen.append(zeile)
                texte.append((t, weitere))
        fortschritt.progress(i / len(tickers))
    status.empty()
    fortschritt.empty()
    erg = pd.DataFrame(zeilen)
    if len(erg):
        erg = erg.sort_values("Muster", ascending=False, kind="stable").reset_index(drop=True)
        erg["RS"] = pd.to_numeric(erg["RS"], errors="coerce").astype("Int64")
        for spalte in [c for c in erg.columns if c.endswith(" Ziel")]:
            erg[spalte] = pd.to_numeric(erg[spalte], errors="coerce")
    weitere_je = dict(texte)
    return {"tickers": tuple(tickers), "nur_treffer": nur_treffer, "erg": erg, "fehlend": fehlend,
            "weitere": weitere_je, "zeitpunkt": zeit_wien(time.time()), "kennung": str(time.time_ns())}


def _lp_zeile(z) -> str:
    teile = [f"{z['Ticker']}", f"Kurs {nachschlagen.zahl(z['Kurs'], 2)} Dollar"]
    if pd.notna(z["RS"]):
        teile.append(f"RS {int(z['RS'])}")
    teile.append(f"Trend Template {z['Trend Template']}")
    kps = []
    for n in (1, 2, 3):
        s = z.get(f"KP{n} Strategie")
        if isinstance(s, str) and s and not s.startswith("Fallback"):
            kps.append(f"{nachschlagen.strategie_anzeige(s)} Kaufpunkt {nachschlagen.zahl(z[f'KP{n} Preis'], 2)}")
    teile.append(("Muster: " + ", ".join(kps)) if kps else "kein Muster")
    return "; ".join(teile) + "."


def _lp_zeigen(lp: dict):
    erg = lp["erg"]
    fehlend = lp["fehlend"]
    if not len(erg):
        st.warning("Keine Treffer" + (", nur Aktien mit Muster sind angehakt" if lp["nur_treffer"] else "") + ".")
        if fehlend:
            st.caption("Keine Daten für: " + ", ".join(fehlend))
        return
    erfolg(f"{len(erg)} Treffer" + (f", {len(fehlend)} ohne Daten" if fehlend else ""), lp["kennung"])
    # ALS LISTE, nicht als Tabelle: Die Tabelle von Streamlit ist eine
    # Zeichenflaeche, die kein Screenreader lesen kann. Sie steht zusaetzlich
    # hinter dem Kontrollfeld Nutzung ohne Screenreader darunter.
    zeilen_text = []
    for _, z in erg.iterrows():
        zeile = _lp_zeile(z)
        st.markdown(zeile)
        for satz in lp["weitere"].get(z["Ticker"]) or []:
            st.markdown(satz)
        zeilen_text.append(" ".join([zeile] + list(lp["weitere"].get(z["Ticker"]) or [])))
    formate = [x[0] for x in sa.FORMATE]
    if st.session_state.get("lp_format") not in formate:
        st.session_state["lp_format"] = "xlsx"
    fmt = st.selectbox("Dateiformat", formate, format_func={x[0]: x[1] for x in sa.FORMATE}.get, key="lp_format",
                       placeholder="Bitte wählen")
    endung = next(x[2] for x in sa.FORMATE if x[0] == fmt)
    st.download_button("Ergebnis als Datei herunterladen",
                       data=lambda: sa.tabelle_datei(erg, fmt, "Chart-Screening-Tool, Liste prüfen",
                                                     [f"Gerechnet am {lp['zeitpunkt']}"], zeilen_text=zeilen_text,
                                                     blatt="Kaufpunkte")[0],
                       file_name=f"kaufpunkte_{datetime.now():%Y-%m-%d}.{endung}",
                       mime=next(x[3] for x in sa.FORMATE if x[0] == fmt), on_click="ignore", key="lp_download")
    # Ein Kontrollfeld statt st.expander (Antworten 103 und 104 vom 24.09.2026)
    if st.checkbox("Nutzung ohne Screenreader", key="lp_tabelle"):
        st.dataframe(erg, hide_index=True)
    if fehlend:
        st.caption("Keine Daten für: " + ", ".join(fehlend))


with tab_liste:
    st.markdown("## Liste prüfen", anchors=False)
    st.write("Hier prüfst du mehrere Aktien auf einmal: Lade eine Finviz-CSV hoch oder tippe die Kürzel ein, mit "
             "Beistrich getrennt.")
    hoch = st.file_uploader("Finviz-CSV mit der Spalte Ticker", type=["csv"])
    manuell = st.text_input("Kürzel, mit Beistrich getrennt", placeholder="AAOI, ETON, NVDA, LASR")

    tickers = []
    if hoch is not None:
        hoch_kennung = f"lp_csv_{hoch.name}_{hoch.size}"
        try:
            df_csv = pd.read_csv(hoch)
            spalte = next((c for c in df_csv.columns if c.strip().lower() == "ticker"), None)
            if spalte:
                tickers = [str(t).strip().upper() for t in df_csv[spalte].dropna()]
            else:
                fehler("In der CSV-Datei fehlt die Spalte Ticker; prüfe bitte, ob es der Finviz-Export ist.",
                       kennung=hoch_kennung)
        except Exception as e:
            fehler("Die CSV-Datei ließ sich nicht lesen; prüfe bitte, ob es der Finviz-Export ist.",
                   f"{type(e).__name__}: {e}", kennung=hoch_kennung)
    elif manuell:
        tickers = [t.strip().upper() for t in manuell.replace(";", ",").split(",") if t.strip()]

    tickers = list(dict.fromkeys([t for t in tickers if t]))  # Duplikate raus

    if tickers:
        st.info(f"{len(tickers)} Kürzel erkannt. Für jede Aktie werden die Kurse von Yahoo geholt; "
                "bei vielen Aktien dauert das einige Minuten.")
        nur_treffer = st.checkbox("Nur Aktien mit aktivem Chartmuster anzeigen", value=True, key="lp_nur_treffer")
        if st.button("Liste durchrechnen", type="primary"):
            st.session_state["lp_ergebnis"] = _lp_rechnen(tickers, nur_treffer)
        lp_ergebnis = st.session_state.get("lp_ergebnis")
        if lp_ergebnis and lp_ergebnis["tickers"] == tuple(tickers) and lp_ergebnis["nur_treffer"] == nur_treffer:
            _lp_zeigen(lp_ergebnis)


# --- Aktueller Scan (Registerkarte) ------------------------------------
def _abstand_satz(kurs, kp) -> str:
    """Wie weit der Kaufpunkt ueber dem Kurs liegt oder der Kurs schon darueber
    steht (Antwort 48 vom 24.09.2026), in denselben Worten wie beim
    Nachschlagen."""
    try:
        kurs, kp = float(kurs), float(kp)
    except (TypeError, ValueError):
        return ""
    if not (kurs > 0 and kp > 0):
        return ""
    abst = (kp / kurs - 1) * 100
    return (f"{nachschlagen.zahl(abst, 1)} Prozent über dem Kurs" if abst >= 0
            else f"der Kurs liegt {nachschlagen.zahl(-abst, 1)} Prozent darüber")


with tab_scan:
    st.markdown("## Aktueller Scan", anchors=False)
    df_scan, scan_info, scan_roh, scan_technik = lade_nachtscan()
    if df_scan is None:
        st.info(scan_info)
        if scan_technik:
            st.caption(technik_zeile(scan_technik))
    else:
        if scan_info:
            st.caption(f"Stand: {scan_info}.")
        # R1 bis R3 (Gerhard, 12.09.2026, ergaenzt am selben Abend): der
        # Bezug steht in der App. Die Spalte heisst aus Bestandsgruenden
        # weiter "RS Nasdaq", gerechnet wird gegen den ganzen US-Markt
        # (Antwort 92: bleibt). Antwort 45: Der Nachtscan prueft das Trend
        # Template mit dem RS-Rank, der Unterschied steht im Text.
        st.caption("RS: relative Stärke gegen alle Stammaktien des US-Markts, also Nasdaq, NYSE und NYSE American, "
                   "mit mindestens 253 Schlusskursen; jede Einzelrendite ist bei plus 50 Prozent gekappt. Jüngere "
                   "Titel ab 64 Schlusskursen tragen ein vorläufiges RS aus den vorhandenen Quartalen. RS ist eine "
                   "Entscheidungshilfe, kein Filter. RS-Rank ist dagegen das Perzentil innerhalb der Wochenlisten. "
                   "Der Nachtscan prüft die RS-Bedingung des Trend Templates mit dem RS-Rank, Aktie nachschlagen "
                   "und der Scanner mit dem RS gegen den ganzen Markt; dieselbe Aktie kann deshalb hier 8 von 8 "
                   "haben und beim Nachschlagen 7 von 8.")

        treffer_zeilen = []
        for _, z in df_scan.iterrows():
            muster = []
            for k in (1, 2, 3):
                s = z.get(f"KP{k} Strategie")
                if isinstance(s, str) and s and not s.startswith("Fallback"):
                    muster.append((k, s))
            if muster:
                treffer_zeilen.append((z, muster))
        anzahl_muster = sum(len(m) for _, m in treffer_zeilen)
        if len(df_scan) == 0:
            # WOCHENPUTZ (Mathias, 13.09.2026): Nach Freitag 16:02 New York
            # ist die Mappe leer, bis neue Wochenlisten hochgeladen und
            # gescannt sind (wochenputz.py). Das ist gewollt, kein Fehler.
            st.info("Zurzeit gibt es keine Kaufpunkte: Der Wochenputz hat die "
                    "alte Woche geleert. Sobald neue Wochenlisten hochgeladen "
                    "und gescannt sind, stehen hier wieder Kaufpunkte.")
        else:
            # Antworten 42, 43 und 49 vom 24.09.2026
            st.write(f"Geprüft wurden {len(df_scan)} Aktien. {len(treffer_zeilen)} davon tragen ein Chartmuster, "
                     f"nicht nur Fallbacks, zusammen {anzahl_muster} Muster-Kaufpunkte. Die Liste ist nach der Zahl "
                     "der erfüllten Bedingungen des Trend Templates sortiert; bei gleicher Zahl bleibt die "
                     "Reihenfolge der Datei.")

        # Beste zuerst: volle Trend-Template-Punktzahl nach oben
        def _rang(paar):
            m = re.search(r"(\d)\s*(?:/|von)\s*8", str(paar[0].get("Trend Template", "")))
            return -(int(m.group(1)) if m else -1)

        for z, muster in sorted(treffer_zeilen, key=_rang):
            with st.container(border=True):
                # Jede Aktie als Ueberschrift (Antwort 50): Ein Screenreader
                # springt von Aktie zu Aktie.
                firma = mappe_text(z.get("Firma"))
                st.markdown(f"### {z['Ticker']}" + (f", {firma}" if firma != "unbekannt" else ""), anchors=False)
                # RS-Rank in jeder Zeile (Antwort 44)
                st.write(f"Kurs {_zahl(z.get('Kurs'))} Dollar; "
                         f"RS {rs_mappe(z.get('RS Nasdaq'))}; "
                         f"RS-Rank {rs_mappe(z.get('RS-Rank'))}; "
                         f"Trend Template {tt_text(z.get('Trend Template'))}; "
                         f"Umsatzwachstum {mappe_text(z.get('Umsatzwachstum'))}")
                for k, s in muster:
                    kp_text = f"{nachschlagen.strategie_anzeige(s)}: Kaufpunkt {_zahl(z.get(f'KP{k} Preis'))} Dollar"
                    abstand = _abstand_satz(z.get("Kurs"), z.get(f"KP{k} Preis"))
                    teile = [kp_text + (f", {abstand}" if abstand else "")]
                    if _zahl(z.get(f"KP{k} Stop")):
                        teile.append(f"Stop {_zahl(z.get(f'KP{k} Stop'))}")
                    if _zahl(z.get(f"KP{k} Ziel")):
                        teile.append(f"Ziel {_zahl(z.get(f'KP{k} Ziel'))}")
                    status = z.get(f"KP{k} Status")
                    if isinstance(status, str) and nachschlagen.anzeige_text(status):
                        teile.append(nachschlagen.anzeige_text(status))
                    st.write("; ".join(teile))

        # Ueberall Download mit Formatwahl (Antwort 54): Excel ist die ganze
        # Mappe, wie der Nachtscan sie ablegt; die anderen Formate enthalten
        # das Blatt Kaufpunkte.
        if scan_roh:
            formate = [x[0] for x in sa.FORMATE]
            if st.session_state.get("scan_format") not in formate:
                st.session_state["scan_format"] = "xlsx"
            scan_fmt = st.selectbox("Dateiformat", formate, format_func={x[0]: x[1] for x in sa.FORMATE}.get,
                                    key="scan_format", placeholder="Bitte wählen")
            scan_endung = next(x[2] for x in sa.FORMATE if x[0] == scan_fmt)
            st.download_button(
                "Nachtscan als Datei herunterladen",
                data=(scan_roh if scan_fmt == "xlsx"
                      else lambda: sa.tabelle_datei(df_scan, scan_fmt, "Chart-Screening-Tool, Nachtscan",
                                                    [f"Stand: {scan_info}" if scan_info else ""],
                                                    blatt="Kaufpunkte")[0]),
                file_name=SCAN_DATEI if scan_fmt == "xlsx" else f"kaufpunkte_aktuell.{scan_endung}",
                mime=next(x[3] for x in sa.FORMATE if x[0] == scan_fmt), on_click="ignore", key="scan_download")
        # NUTZUNG OHNE SCREENREADER (Mathias, 22.09.2026): So heisst die Tabelle.
        # RS Nasdaq kommt als Zahl, dahinter "RS vorlaeufig" mit ja oder nein;
        # sonst machte Streamlit die ganze Spalte zu Text und sortierte sie nach
        # Zeichen. Die Mappe selbst bleibt, wie sie ist. Ein Kontrollfeld statt
        # st.expander (Antwort 103 vom 24.09.2026).
        if st.checkbox("Nutzung ohne Screenreader", key="scan_tabelle"):
            st.dataframe(nachschlagen.rs_spalte_als_zahl(df_scan), hide_index=True)


# --- Regelwerk -------------------------------------------------------------
# DAS REGELWERK ENTSTEHT AUS DEM REGISTER (Antwort 76 vom 24.09.2026): je
# Strategie ein Absatz aus einstellungen.ALARME, damit neue von selbst dazukommen;
# die Zahlen folgen dem Code (Antwort 107). Die Gliederung bleibt (Antwort 77),
# dazu kommt der Abschnitt Marktampel (Antwort 78). Technische Saetze sind
# gestrichen (Antwort 79), der Hinweis zur Datenquelle steht unter den Grenzen
# (Antworten 24 und 33).
with tab_info:
    st.markdown("## Regelwerk", anchors=False)
    st.markdown("### Was die App prüft", anchors=False)
    st.markdown("**Minervini Trend Template.** " + einstellungen.TREND_TEMPLATE_REGEL)
    for rw_gruppe, rw_einleitung, rw_absaetze in einstellungen.regelwerk_gruppen():
        st.markdown(f"#### {rw_gruppe}", anchors=False)
        if rw_einleitung:
            st.markdown(rw_einleitung)
        for rw_name, rw_text in rw_absaetze:
            st.markdown(f"**{rw_name}.** {rw_text}")

    st.markdown("### Marktampel", anchors=False)
    for satz in marktampel.REGELWERK:
        st.markdown(satz)

    st.markdown("### Grenzen, die du kennen solltest", anchors=False)
    st.markdown("**RS gegen den ganzen US-Markt.** Aktie nachschlagen, Liste prüfen und der Scanner nehmen das RS aus "
                "der Nachtdatei: das Perzentil gegen alle Stammaktien des US-Markts, jede Einzelrendite bei plus 50 "
                "Prozent gekappt. Junge Titel tragen ein vorläufiges RS aus den vorhandenen Quartalen. Fehlt ein RS, "
                "gilt die RS-Bedingung des Trend Templates als nicht erfüllt. Der Nachtscan prüft das Trend Template "
                "dagegen mit dem RS-Rank innerhalb der Wochenlisten; dieselbe Aktie kann deshalb im Aktuellen Scan 8 "
                "von 8 Bedingungen erfüllen und beim Nachschlagen 7 von 8.")
    st.markdown("**Kaufpunkt heißt nicht Kaufsignal.** Die Volumenbestätigung am Ausbruchstag prüfen Aktie "
                "nachschlagen und Liste prüfen nicht, dafür ist der Breakout-Wächter da.")
    st.markdown("**Kursdaten.** Die Kurse kommen von Yahoo und sind bis zu 15 Minuten alt; Yahoo braucht keinen "
                "Schlüssel. "
                + ("Fällt Yahoo aus, springt Twelve Data als Rückfallebene ein." if api_key else
                   "Eine Rückfallebene über Twelve Data gibt es nur mit einem eigenen Schlüssel; dafür wäre "
                   "TWELVE_DATA_API_KEY in den Streamlit-Secrets zu hinterlegen."))

    st.markdown("### Der Scanner", anchors=False)
    st.markdown(sa.md(
        "Teil 1 prüft eine Strategie oder ein Chart-Signal für jede Stammaktie des US-Markts, Teil 2 filtert nach "
        "Merkmalen. Gerechnet wird jede Nacht aus den Tageskerzen; der Scanner setzt keine Alarme."))
    st.markdown(sa.md(
        f"Treffer: Ein Muster muss streng erfüllt sein. Mit {sa.toleranz_prozent()} Prozent Toleranz dürfen "
        "Schwellen in Prozent, Verhältnisse und Dauern um diesen Anteil verfehlt werden, die Lage zu gleitenden "
        "Durchschnitten um diesen Anteil der mittleren Tagesschwankung. Ein Treffer nur mit Toleranz kostet "
        f"{sa.SC['rating']['toleranz_abzug']} Punkte beim Rating."))
    st.markdown(sa.md(
        "Rating von 0 bis 100: relative Stärke, Nähe zum Hoch, Vorlauf, Jahresspanne, Tagesspanne, Liquidität, "
        "Austrocknen des Volumens, Enge, Nachfrage und die Qualität des Musters, gewichtet je Muster. Das Rating "
        "ordnet die Treffer, ein fehlendes Muster ersetzt es nie. Die drei stärksten und die zwei schwächsten "
        "Bausteine stehen als Begründung dabei."))
    st.markdown(sa.md(sa.handelbar_text() + "."))
    st.markdown(sa.md(sa.langweile_text() + "."))
    st.markdown("### Grenzen des Scanners", anchors=False)
    for satz in sa.grenzen_saetze():
        st.markdown(sa.md(satz))
    # Etappe 1 der Chartmuster (Gerhard, 20.09.2026): was bei jedem Treffer
    # dazugeschrieben wird, und jede Zahl, die von uns stammt.
    st.markdown("### Chartmuster bei den Treffern", anchors=False)
    for satz in sa.chartmuster_erklaerung():
        st.markdown(sa.md(satz))


# --- Ab hier nur mit vollem Zugang -----------------------------------------
# Gaeste sind hier fertig (Mathias, 13.09.2026): Die Wochenliste schreibt ueber
# den GitHub-Token ins Repo, und Gastpasswoerter erzeugt nur, wer das feste
# Passwort kennt. Fuer Gaeste gibt es tab_upload und tab_gast deshalb gar
# nicht, und der Lauf der Seite endet hier, bevor davon etwas gebaut wird.
# Die Gesamtpruefung (Block H) achtet darauf, dass das so bleibt.
if tab_upload is None:
    st.stop()


# --- Wochenliste (Registerkarte) ----------------------------------------
# Pruefen und Einspielen stehen seit dem 21.09.2026 oben vor dem Scanner, weil
# auch die Uebergabe aus dem Scanner (Gerhard, 20.09.2026, S2) sie braucht.
# Die Seite zum Hochladen gibt es weiter nur mit vollem Zugang.
with tab_upload:
    st.markdown("## Wochenlisten", anchors=False)
    # Ohne Personennamen (Antwort 71 vom 24.09.2026)
    st.write("Hier werden die wöchentlichen Aktienlisten hochgeladen, als CSV-Datei mit der Spalte Ticker. Es sind "
             "ZWEI: die große Liste für alle Strategien und die Darvas-Liste. Auf der großen läuft alles außer "
             "Darvas, auf der Darvas-Liste läuft alles. Die neuen Listen gelten ab dem nächsten nächtlichen Scan.")

    try:
        github_token = st.secrets.get("GITHUB_TOKEN", "")
    except Exception:
        github_token = ""

    anzahl_aktuell = aktuelle_listengroesse(LISTEN_DATEI)
    anzahl_darvas = aktuelle_listengroesse(DARVAS_DATEI)
    st.caption(
        f"Im System: große Liste "
        f"{anzahl_aktuell if anzahl_aktuell else 'fehlt'} Aktien, "
        f"Darvas-Liste {anzahl_darvas if anzahl_darvas else 'fehlt'} Aktien.")
    if not anzahl_darvas:
        st.warning("Die Darvas-Liste fehlt. Solange sie fehlt, entstehen "
                   "KEINE Darvas-Kaufpunkte; alle anderen Muster laufen "
                   "normal weiter.")

    if not github_token:
        st.warning("Das Hochladen ist noch nicht eingerichtet; bis dahin ist diese Seite nur Anzeige.")
        st.caption(technik_zeile("In den Streamlit-Secrets fehlt GITHUB_TOKEN."))
    else:
        datei = st.file_uploader("CSV-Datei mit der Spalte Ticker", type=["csv"],
                                 key="upload_datei")
        # Der Dateiname schlaegt die Liste vor, entschieden wird hier
        # sichtbar. Ein stiller Griff in die falsche Liste waere der
        # teuerste Fehler dieser Seite.
        vorschlag = liste_aus_dateiname(datei.name if datei else "")
        wahl = st.radio(
            "In welche Liste?",
            [f"Große Liste für alle Strategien außer Darvas, {LISTEN_DATEI}",
             f"Darvas-Liste, dort laufen ALLE Strategien, {DARVAS_DATEI}"],
            index=1 if vorschlag == DARVAS_DATEI else 0, key="upload_wahl")
        ziel_datei = DARVAS_DATEI if wahl.startswith("Darvas") else LISTEN_DATEI
        if datei is not None:
            st.caption(f"Aus dem Dateinamen {datei.name} geschlossen: "
                       f"{vorschlag}. Prüfe bitte oben die Wahl.")
        if datei is not None and st.button(f"Liste {ziel_datei} übernehmen",
                                           type="primary"):
            roh = datei.getvalue()
            fehler_text, ticker = pruefe_wochenliste(roh)
            if fehler_text:
                fehler("NICHT übernommen: " + fehler_text)
            else:
                fehler_text, zweige = wochenliste_einspielen(
                    roh, github_token, len(ticker), ziel_datei)
                # Der Zaehler wird auch bei einem Teilerfolg geleert:
                # Auf mindestens einem Zweig steht die neue Liste.
                if zweige:
                    aktuelle_listengroesse.clear()
                if fehler_text:
                    fehler("Die Liste ist nicht vollständig übernommen; versuche es bitte später noch einmal."
                           if zweige else "Die Liste ist nicht übernommen; versuche es bitte später noch "
                                          "einmal.", fehler_text)
                else:
                    erfolg(f"Übernommen in {ziel_datei} auf "
                           f"{zweige}: {len(ticker)} Aktien, "
                           f"die ersten: {', '.join(ticker[:5])}. "
                           "Ab dem nächsten nächtlichen Scan aktiv.")

    # S7 (Gerhard, 20.09.2026): die einzeln eingetragenen Aktien, nur im
    # vollen Zugang
    if rolle == "voll":
        einzel_liste_zeigen()


# --- Gastzugang (Mathias, 13.09.2026) ---------------------------------------
# Nur mit dem festen Passwort. Das Gastpasswort wird gerechnet, nicht
# gespeichert (zugang.py): Es gilt fuer alle, die es bekommen, und laesst sich
# vor dem Ablauf nur zuruecknehmen, indem GAST_GEHEIMNIS geaendert wird.
if tab_gast is not None:
    with tab_gast:
        st.markdown("## Gastzugang", anchors=False)
        st.markdown("### Gastpasswort erzeugen", anchors=False)
        # Antworten 74 und 100 vom 24.09.2026
        st.write("Ein Gastpasswort öffnet die App für 60 bis 70 Minuten; die genaue Zeit steht nach dem Erzeugen "
                 "dabei. Gäste sehen nur den Scanner; alles andere sehen sie nicht, verändern können sie nichts. "
                 "Weitergegeben wird das Passwort von dem, der es erzeugt.")
        gast_geheimnis = _secret("GAST_GEHEIMNIS") or ""
        if not gast_geheimnis.strip():
            st.warning("Gastpasswörter sind noch nicht eingerichtet.")
            st.caption(technik_zeile("In den Streamlit-Secrets fehlt GAST_GEHEIMNIS."))
        else:
            if st.button("Gastpasswort erzeugen", type="primary", key="gast_erzeugen"):
                st.session_state["gast_erzeugt"] = zugang.erzeuge(gast_geheimnis, time.time())
                klang()
            erzeugt = st.session_state.get("gast_erzeugt")
            if erzeugt and time.time() < erzeugt[1]:
                gast_pw, gast_bis = erzeugt
                st.markdown(f"Gastpasswort: **{gast_pw}**")
                st.write("Buchstabe für Buchstabe: " + zugang.buchstabiert(gast_pw))
                st.write(f"Gültig bis {zeit_wien(gast_bis)}. "
                         "Groß- und Kleinschreibung spielt beim Gastpasswort keine Rolle.")
                st.code(gast_pw, language=None)
                st.caption("Wer innerhalb derselben zehn Minuten noch einmal erzeugt, "
                           "bekommt dasselbe Passwort. Vor dem Ablauf lassen sich alle "
                           "Gastpasswörter nur zurücknehmen, indem GAST_GEHEIMNIS in den "
                           "Streamlit-Secrets geändert wird.")
            elif erzeugt:
                st.info("Das zuletzt erzeugte Gastpasswort ist abgelaufen.")


# --- Ablaeufe (Gerhard, 20.09.2026, S8; Mathias, 21.09.2026) -------------------
# Knoepfe, die Waechter, Nachtscan und Scanner-Tabelle nach einem Absturz oder
# nach GitHub-Problemen anstossen. Angestossen werden nur Ablaeufe, die selbst
# pruefen, ob etwas zu tun ist (ablaeufe.py); ein Knopf startet also nichts
# doppelt und nichts ausserhalb der Zeit. Nur mit vollem Zugang und dem Token
# ABLAUF_TOKEN, der nur Ablaeufe im Repo heliot lesen und starten darf.
@st.cache_data(ttl=30, show_spinner=False)
def _ablauf_laeufe(datei: str):
    import requests
    token = _ablauf_token()
    if not token:
        raise LookupError("kein Token")
    r = requests.get(f"https://api.github.com/repos/{REPO}/actions/workflows/{datei}/runs",
                     params={"per_page": 30},
                     headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                     timeout=20)
    if r.status_code != 200:
        raise LookupError(f"GitHub antwortete mit Code {r.status_code}")
    return r.json().get("workflow_runs") or []


def _ablauf_anstossen(datei: str):
    """(angenommen, einfacher Satz, technischer Grund oder None), Antwort 102."""
    import requests
    token = _ablauf_token()
    if not token:
        return False, ablaeufe.NICHT_ANGESTOSSEN, "In den Streamlit-Secrets fehlt ABLAUF_TOKEN."
    try:
        r = requests.post(f"https://api.github.com/repos/{REPO}/actions/workflows/{datei}/dispatches",
                          json={"ref": "main"},
                          headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                          timeout=20)
    except Exception as e:  # noqa
        return False, ablaeufe.NICHT_ANGESTOSSEN, f"GitHub war nicht erreichbar, {type(e).__name__}."
    return ablaeufe.anstoss_satz(r.status_code)


if tab_ablaeufe is not None:
    with tab_ablaeufe:
        st.markdown("## Abläufe", anchors=False)
        ablauf_token_da = bool(_ablauf_token())
        if not ablauf_token_da:
            st.warning("Die Abläufe lassen sich hier weder ansehen noch anstoßen, weil der Zugang dafür nicht "
                       "eingerichtet ist.")
            st.caption(technik_zeile("In den Streamlit-Secrets fehlt ABLAUF_TOKEN."))
        for ablauf in ablaeufe.ABLAEUFE:
            st.markdown(f"### {ablauf['titel']}", anchors=False)
            if ablauf_token_da:
                try:
                    saetze_zeigen(ablaeufe.zustand_saetze(_ablauf_laeufe(ablauf["zustand"]), ablauf))
                except LookupError as e:
                    st.markdown("Der Stand ist gerade nicht abrufbar.")
                    st.caption(technik_zeile(str(e)))
                except Exception as e:  # noqa
                    st.markdown("Der Stand ist gerade nicht abrufbar.")
                    st.caption(technik_zeile(type(e).__name__))
            st.markdown(ablauf["erklaerung"])
            if st.button(ablauf["knopf"], key=f"ablauf_{ablauf['schluessel']}", disabled=not ablauf_token_da):
                ablauf_ok, ablauf_satz, ablauf_technik = _ablauf_anstossen(ablauf["anstoss"])
                _ablauf_laeufe.clear()
                if ablauf_ok:
                    erfolg(ablauf_satz)
                else:
                    fehler(ablauf_satz, ablauf_technik)
        st.button("Stand neu laden", key="ablauf_neu_laden", disabled=not ablauf_token_da,
                  on_click=_ablauf_laeufe.clear)


# --- Einstellungen (Mathias und Gerhard, 23.09.2026) ------------------------
# "Wir wollen die Ueberwachung aller Strategien einzeln ein- oder ausschalten
# koennen", und zwar die Alarme ueber ntfy (Mathias, 23.09.2026: "wir meinen die
# Alarme fuer ntfy, da moechten wir waehlen koennen, welche Chartmuster zur
# Anwendung kommen"). Dazu das Aussehen ("per Button soll ein wirklich cooles,
# futuristisches Design aktivierbar sein") und die Toene ("Erstelle coole Sounds
# und mache sie waehlbar"). Die Bloecke sind gebaut wie die Gruppen im Scanner:
# eine Ueberschrift und ein Kontrollfeld, das zu Beginn nicht angehakt ist.
# Gespeichert wird mit einem Knopf ganz unten in einstellungen.json auf main; der
# Waechter liest die Datei in jedem Datentakt, eine Abwahl wirkt also binnen einer
# Minute. Schreiben nur im vollen Zugang.
#
# DIE WAHL STEHT IN EINEM EIGENEN EINTRAG (einst_modell), nicht im Zustand der
# Kontrollfelder: Diese gibt es nur, solange ihre Gruppe angezeigt wird, und den
# Wert eines nicht gezeichneten Felds raeumt Streamlit weg (Befund vom 21.09.2026
# bei der Uebergabe). Die Kontrollfelder werden bei jedem Zeichnen aus dem Eintrag
# gesetzt.
def _einst_api() -> tuple:
    """(Einstellungen, sha) frisch ueber die GitHub-Schnittstelle; sha ist None,
    solange es die Datei noch nicht gibt. Scheitert das Lesen: LookupError, und
    gespeichert wird nicht, sonst ueberschriebe die Vorgabe einen Stand, den
    niemand gesehen hat."""
    import base64
    import requests
    token = (_secret("GITHUB_TOKEN") or "").strip()
    if not token:
        raise LookupError("In den Streamlit-Secrets fehlt GITHUB_TOKEN")
    r = requests.get(f"https://api.github.com/repos/{REPO}/contents/{einstellungen.DATEI}", params={"ref": "main"},
                     headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                     timeout=20)
    if r.status_code == 404:
        return einstellungen.lesen(None), None
    if r.status_code != 200:
        raise LookupError(f"GitHub antwortete mit Code {r.status_code}")
    j = r.json()
    return einstellungen.lesen(base64.b64decode(j.get("content") or "")), j.get("sha")


def _einst_eigen_basis() -> tuple:
    """(Aussehen, Ton), wie dieser Browser sie gespeichert hat (Antwort 2)."""
    return einstellungen.eigen_lesen(st.session_state.get("eigen_gemeldet"))


def _einst_laden():
    """Den gespeicherten Stand holen und die Wahl darauf setzen: die Alarme aus
    einstellungen.json, ohne vollen Zugang ueber die oeffentliche Adresse und nur
    zum Ansehen; Aussehen und Ton aus diesem Browser."""
    try:
        if rolle == "voll":
            basis, sha = _einst_api()
        else:
            basis, sha = _einstellungen_holen(), None
        fehler_text = ""
    except Exception as e:  # noqa
        basis, sha, fehler_text = _einstellungen(), None, (str(e) or type(e).__name__)
    design, ton = _einst_eigen_basis()
    st.session_state["einst_basis"] = {"daten": basis, "sha": sha, "fehler": fehler_text}
    st.session_state["einst_modell"] = {"aus": set(basis["alarme_aus"]), "design": design, "klang": ton,
                                        "eigen_von": st.session_state.get("eigen_gemeldet") or ""}


def _einst_verwerfen():
    basis = (st.session_state.get("einst_basis") or {}).get("daten") or einstellungen.lesen(None)
    design, ton = _einst_eigen_basis()
    st.session_state["einst_modell"] = {"aus": set(basis["alarme_aus"]), "design": design, "klang": ton,
                                        "eigen_von": st.session_state.get("eigen_gemeldet") or ""}


def _einst_neu() -> dict:
    """Die Alarme der Wahl als Inhalt von einstellungen.json."""
    modell = st.session_state["einst_modell"]
    return einstellungen.lesen({"alarme_aus": sorted(modell["aus"])})


def _einst_aenderungen(basis: dict, neu: dict) -> list:
    """Was sich an den Alarmen gegenueber dem gespeicherten Stand geaendert hat, als Saetze."""
    saetze = []
    alt_aus, neu_aus = set(basis["alarme_aus"]), set(neu["alarme_aus"])
    for satz, menge in (("Abgewählt: ", neu_aus - alt_aus), ("Wieder eingeschaltet: ", alt_aus - neu_aus)):
        namen = [a["name"] for a in einstellungen.ALARME if a["schluessel"] in menge]
        if namen:
            saetze.append(satz + "; ".join(namen) + ".")
    return saetze


def _einst_eigen_aenderungen() -> list:
    """Was sich an Aussehen und Ton gegenueber diesem Browser geaendert hat, als Saetze."""
    modell = st.session_state.get("einst_modell") or {}
    design, ton = _einst_eigen_basis()
    saetze = []
    if modell.get("design") and modell["design"] != design:
        saetze.append(f"Aussehen: {dict(einstellungen.DESIGNS)[modell['design']]}.")
    if modell.get("klang") and modell["klang"] != ton:
        saetze.append(f"Ton: {next(n for k, n, _b in einstellungen.KLAENGE if k == modell['klang'])}.")
    return saetze


def _einst_haken(k: str, schluessel: str):
    modell = st.session_state.get("einst_modell")
    if isinstance(modell, dict):
        (modell["aus"].discard if st.session_state.get(k, True) else modell["aus"].add)(schluessel)


def _einst_gruppe_setzen(gruppe: str, an: bool):
    modell = st.session_state.get("einst_modell")
    if isinstance(modell, dict):
        for a in einstellungen.ALARME:
            if a["gruppe"] == gruppe:
                (modell["aus"].discard if an else modell["aus"].add)(a["schluessel"])


def _einst_design_umschalten():
    modell = st.session_state.get("einst_modell")
    if isinstance(modell, dict):
        modell["design"] = "standard" if modell["design"] == "zukunft" else "zukunft"


def _einst_klang_gewaehlt():
    modell = st.session_state.get("einst_modell")
    if isinstance(modell, dict) and st.session_state.get("einst_klang"):
        modell["klang"] = st.session_state["einst_klang"]


def _einst_speichern():
    """Die Wahl speichern: Aussehen und Ton in diesem Browser (Antwort 2 vom
    24.09.2026), die Alarme als einstellungen.json auf main, nur im vollen
    Zugang. Gespeichert wird mit dem sha des gelesenen Stands: Hat jemand anderer
    inzwischen gespeichert, lehnt GitHub ab, statt dessen Stand still zu
    ueberschreiben."""
    import base64
    import requests
    from zoneinfo import ZoneInfo
    basis = st.session_state.get("einst_basis") or {}
    modell = st.session_state.get("einst_modell")
    kennung = str(time.time_ns())
    if not isinstance(modell, dict):
        st.session_state["einst_meldung"] = ("fehler", "Nicht gespeichert: Der gespeicherte Stand ist nicht gelesen. "
                                             "Drück bitte Gespeicherten Stand neu laden.", None, kennung)
        return
    eigen_saetze = _einst_eigen_aenderungen()
    if eigen_saetze:
        neu_wert = einstellungen.eigen_schreiben(modell["design"], modell["klang"])
        st.session_state["eigen_setzen"] = neu_wert
        modell["eigen_von"] = neu_wert
    neu = _einst_neu()
    saetze = _einst_aenderungen(basis.get("daten") or einstellungen.lesen(None), neu)
    if not saetze:
        st.session_state["einst_meldung"] = ("ok", "Gespeichert. " + " ".join(eigen_saetze) + " Aussehen und Ton "
                                             "gelten ab sofort in diesem Browser.", None, kennung)
        return
    vorher = "Aussehen und Ton sind in diesem Browser gespeichert. " if eigen_saetze else ""
    if rolle != "voll" or basis.get("fehler"):
        st.session_state["einst_meldung"] = ("fehler", vorher + "Die Alarme sind nicht gespeichert: Der "
                                             "gespeicherte Stand ist nicht gelesen. Drück bitte Gespeicherten Stand "
                                             "neu laden.", basis.get("fehler") or None, kennung)
        return
    token = (_secret("GITHUB_TOKEN") or "").strip()
    if not token:
        st.session_state["einst_meldung"] = ("fehler", vorher + "Die Alarme sind nicht gespeichert.",
                                             "In den Streamlit-Secrets fehlt GITHUB_TOKEN.", kennung)
        return
    wann = datetime.now(ZoneInfo("Europe/Vienna")).strftime("%Y-%m-%d %H:%M")
    n_aus = len(neu["alarme_aus"])
    daten = {"message": f"{einstellungen.DATEI}: {n_aus} {'Alarm' if n_aus == 1 else 'Alarme'} abgewählt (über Heliot)",
             "content": base64.b64encode(einstellungen.schreiben(neu, geaendert=wann)).decode(), "branch": "main"}
    if basis.get("sha"):
        daten["sha"] = basis["sha"]
    try:
        r = requests.put(f"https://api.github.com/repos/{REPO}/contents/{einstellungen.DATEI}",
                         headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                         json=daten, timeout=30)
    except Exception as e:  # noqa
        st.session_state["einst_meldung"] = ("fehler", vorher + "Die Alarme sind nicht gespeichert; versuche es "
                                             "bitte später noch einmal.",
                                             f"GitHub war nicht erreichbar, {type(e).__name__}.", kennung)
        return
    if r.status_code in (409, 422):
        st.session_state["einst_meldung"] = ("fehler", vorher + "Die Alarme sind nicht gespeichert: Sie wurden "
                                             "inzwischen woanders gespeichert. Der Knopf Gespeicherten Stand neu "
                                             "laden holt den neuen Stand; die eigene Wahl ist danach neu zu treffen.",
                                             f"GitHub antwortete mit Code {r.status_code}.", kennung)
        return
    if r.status_code not in (200, 201):
        st.session_state["einst_meldung"] = ("fehler", vorher + "Die Alarme sind nicht gespeichert; versuche es "
                                             "bitte später noch einmal.",
                                             f"GitHub antwortete mit Code {r.status_code}.", kennung)
        return
    neu["geaendert"] = wann
    st.session_state["einst_basis"] = {"daten": neu, "sha": (r.json().get("content") or {}).get("sha"), "fehler": ""}
    st.session_state["einst_gespeichert"] = (time.time(), neu)
    _einstellungen_holen.clear()
    st.session_state["einst_meldung"] = ("ok", "Gespeichert. " + " ".join(saetze + eigen_saetze) + " Der Wächter "
                                         "übernimmt die Alarme binnen einer Minute"
                                         + ("; Aussehen und Ton gelten ab sofort in diesem Browser." if eigen_saetze
                                            else "."), None, kennung)


def _einst_wann(wann) -> str:
    wann = str(wann or "")
    if len(wann) >= 16:
        return f"{nachschlagen.datum_text(wann[:10])} um {wann[11:16]} Uhr Wiener Zeit"
    return ""


# Die Eintraege, deren Name eine Mehrzahl ist; ihr Erklaerungsknopf fragt "Was sind ...?".
EINST_MEHRZAHL = {"insider", "ausstiege", "gewinnzonen", "schlussnah", "beobachtungen", "sektor_morgen"}

if tab_einst is not None:
    with tab_einst:
        st.markdown("## Einstellungen", anchors=False)
        if not isinstance(st.session_state.get("einst_modell"), dict) or "einst_basis" not in st.session_state:
            _einst_laden()
        _eigen_modell_nachziehen()
        einst_basis = st.session_state["einst_basis"]
        einst_modell = st.session_state["einst_modell"]
        einst_darf = rolle == "voll" and not einst_basis["fehler"]
        # Berichtigung 18 und Antwort 96 vom 24.09.2026
        st.markdown("Hier legst du fest, welche Chartmuster, Strategien und Meldungen einen Alarm über ntfy auslösen, "
                    "wie die App aussieht und welcher Ton nach einer erfolgreich abgeschlossenen Aktion spielt. Die "
                    "Alarme gelten für alle, die die App benutzen; Aussehen und Ton gelten nur in diesem Browser. "
                    "Alles wirkt erst, wenn ganz unten Einstellungen speichern gedrückt ist.")
        if rolle != "voll":
            st.info("Die Alarme lassen sich nur mit vollem Zugang ändern; hier sind sie nur zu sehen. Aussehen und "
                    "Ton wählst du für diesen Browser selbst.")
        elif einst_basis["fehler"]:
            fehler("Der gespeicherte Stand der Alarme lässt sich gerade nicht lesen; deshalb lassen sich die Alarme "
                   "nicht speichern. Der Knopf Gespeicherten Stand neu laden ganz unten versucht es noch einmal.",
                   einst_basis["fehler"], kennung="einst_lesefehler_" + str(abs(hash(einst_basis["fehler"]))))

        st.markdown("### Alarme über ntfy", anchors=False)
        # Antworten 7, 9 und 83 vom 24.09.2026
        st.markdown("Angehakt heißt: Das Muster, die Strategie oder die Meldung geht über ntfy hinaus, und ein "
                    "Kaufsignal geht auch an den Handels-Bot. Abgewählt heißt nur: keine Meldung und kein Signal an "
                    "den Bot. Der Wächter prüft weiter und schreibt jeden Ausbruch ins Trigger-Logbuch, der "
                    "Nachtscan rechnet weiter, und die Kaufpunkte stehen weiter im Reiter Aktueller Scan. Auch die "
                    "Meldungen zu offenen Positionen lassen sich abwählen; abgewählt steht bei jeder eine Warnung.")
        einst_aus_namen = einstellungen.abgewaehlte_namen(einst_basis["daten"])
        # Berichtigung 19 vom 24.09.2026
        st.markdown(("Gespeichert abgewählt: " + "; ".join(einst_aus_namen) + ".") if einst_aus_namen
                    else "Gespeichert: Alle Alarme sind eingeschaltet.")
        for einst_g, einst_gname in einstellungen.GRUPPEN:
            einst_eintraege = [a for a in einstellungen.ALARME if a["gruppe"] == einst_g]
            einst_n = sum(1 for a in einst_eintraege if a["schluessel"] not in einst_modell["aus"])
            st.markdown(f"#### {einst_gname}", anchors=False)
            # Ueberall "N von M angehakt" (Antwort 15 vom 24.09.2026)
            if not st.checkbox(f"Gruppe {einst_gname} anzeigen, {einst_n} von {len(einst_eintraege)} angehakt",
                               key=f"einst_gruppe_{einst_g}"):
                continue
            if len(einst_eintraege) > 1:
                st.button("Alle dieser Gruppe einschalten", key=f"einst_alle_an_{einst_g}",
                          on_click=_einst_gruppe_setzen, args=(einst_g, True), disabled=rolle != "voll")
                st.button("Alle dieser Gruppe ausschalten", key=f"einst_alle_aus_{einst_g}",
                          on_click=_einst_gruppe_setzen, args=(einst_g, False), disabled=rolle != "voll")
            for a in einst_eintraege:
                einst_k = f"einst_alarm_{a['schluessel']}"
                st.session_state[einst_k] = a["schluessel"] not in einst_modell["aus"]
                st.checkbox(a["name"], key=einst_k, on_change=_einst_haken, args=(einst_k, a["schluessel"]),
                            disabled=rolle != "voll")
                # Die Warnung beim Abwaehlen (Antwort 7 vom 24.09.2026)
                if a.get("warnung") and a["schluessel"] in einst_modell["aus"]:
                    st.warning("Achtung: " + a["warnung"])
                _sc_erklaerung(f"alarm_{a['schluessel']}", a["name"], a["erklaerung"],
                               frage=f"Was sind {a['name']}?" if a["schluessel"] in EINST_MEHRZAHL else None)

        st.markdown("### Aussehen", anchors=False)
        if st.checkbox("Gruppe Aussehen anzeigen", key="einst_gruppe_aussehen"):
            einst_design_namen = dict(einstellungen.DESIGNS)
            einst_satz = f"Gewählt ist das Aussehen {einst_design_namen[einst_modell['design']]}."
            if einst_modell["design"] != _einst_eigen_basis()[0]:
                einst_satz += (" In diesem Browser gilt es schon als Vorschau; gespeichert wird es mit Einstellungen "
                               "speichern.")
            st.markdown(einst_satz)
            st.button("Zukunftsdesign ein- oder ausschalten", key="einst_design_knopf",
                      on_click=_einst_design_umschalten)
            st.caption("Das Zukunftsdesign ist für sehende Menschen gemacht: ein dunkler Sternenhimmel, "
                       "Leuchteffekte und Bewegung. Aufbau und Text der App bleiben gleich, ein Screenreader liest "
                       "dasselbe. Verlangt das Gerät weniger Bewegung, steht alles still. Das Aussehen gilt nur in "
                       "diesem Browser; Gäste sehen immer das Standard-Aussehen.")

        st.markdown("### Töne", anchors=False)
        if st.checkbox("Gruppe Töne anzeigen", key="einst_gruppe_toene"):
            einst_klaenge = {k: (n, b) for k, n, b in einstellungen.KLAENGE}
            st.session_state["einst_klang"] = einst_modell["klang"]
            st.radio("Ton nach einer erfolgreich abgeschlossenen Aktion", list(einst_klaenge), key="einst_klang",
                     format_func=lambda k: f"{einst_klaenge[k][0]}; {einst_klaenge[k][1][0].lower()}"
                                           f"{einst_klaenge[k][1][1:].rstrip('.')}",
                     on_change=_einst_klang_gewaehlt)
            if st.button("Gewählten Ton anhören", key="einst_klang_hoeren"):
                if einst_modell["klang"] == "aus":
                    st.info("Gewählt ist Kein Ton; zu hören ist deshalb nichts.")
                else:
                    klang(name=einst_modell["klang"])
            # Antworten 3 und 5 vom 24.09.2026
            st.caption("Der Ton spielt nach dem Anmelden, nach einem Scan und nach jedem Speichern, Hochladen, "
                       "Übergeben, Eintragen, Erzeugen und Anstoßen, das geklappt hat. Scheitert etwas, spielt immer "
                       "ein fester, tiefer Fehlerton. Der gewählte Ton gilt nur in diesem Browser; Gäste hören den "
                       "Ton Kristall. Der Browser gibt die Töne erst nach dem ersten Klick oder Tastendruck auf der "
                       "Seite frei.")

        st.markdown("### Speichern", anchors=False)
        einst_saetze = _einst_aenderungen(einst_basis["daten"], _einst_neu())
        einst_eigen_saetze = _einst_eigen_aenderungen()
        if einst_saetze or einst_eigen_saetze:
            st.markdown("Noch nicht gespeichert. " + " ".join(einst_saetze + einst_eigen_saetze))
            einst_neu_aus = set(einst_modell["aus"]) - set(einst_basis["daten"]["alarme_aus"])
            einst_warn = [a["name"] for a in einstellungen.ALARME if a.get("warnung") and a["schluessel"] in einst_neu_aus]
            if einst_warn:
                st.warning("Achtung: Abgewählt sind auch Meldungen zu offenen Positionen: " + "; ".join(einst_warn)
                           + ". Was dann fehlt, steht bei den Einträgen.")
        else:
            einst_wann = _einst_wann(einst_basis["daten"].get("geaendert"))
            st.markdown("Alles ist gespeichert" + (f"; die Alarme zuletzt geändert am {einst_wann}" if einst_wann
                                                  else "") + ".")
        einst_speicherbar = bool(einst_eigen_saetze) or (bool(einst_saetze) and einst_darf)
        st.button("Einstellungen speichern", key="einst_speichern", type="primary", on_click=_einst_speichern,
                  disabled=not einst_speicherbar)
        st.button("Änderungen verwerfen", key="einst_verwerfen", on_click=_einst_verwerfen,
                  disabled=not (einst_saetze or einst_eigen_saetze))
        st.button("Gespeicherten Stand neu laden", key="einst_neu_laden", on_click=_einst_laden)
        if (st.session_state.get(EIGEN_SCHLUESSEL) or {}).get("gespeichert") is False:
            st.caption("Dieser Browser lässt die App Aussehen und Ton nicht speichern; beim nächsten Öffnen gilt "
                       "wieder die Grundeinstellung.")
        einst_meldung = st.session_state.pop("einst_meldung", None)
        if einst_meldung:
            einst_art, einst_text, einst_technik, einst_kennung = (tuple(einst_meldung) + (None,) * 4)[:4]
            if einst_art == "ok":
                erfolg(einst_text, einst_kennung)
            else:
                fehler(einst_text, einst_technik, einst_kennung)


# Der Abmelden-Knopf am Seitenende (Antwort 25 vom 24.09.2026)
abmelden_zeigen()
