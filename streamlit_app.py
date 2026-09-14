#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CHART-SCREENING-TOOL, Web-Oberflaeche
====================================
Oben "Aktie nachschlagen": Kuerzel oder Name eingeben, dann alle unsere
Zahlen als Text, alle Muster, die Kaufpunkte samt Chart und darunter der
Aktienchart mit Tages-, Monats- oder Jahreskerzen. Darunter die
Registerkarten Liste pruefen, Aktueller Scan, Wochenliste, Gastzugang und
Regelwerk.

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

import nachschlagen
import pattern_scanner as ps
import zugang

st.set_page_config(page_title="Chart-Screening-Tool", layout="wide")


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
        st.markdown("Für diese Darstellung kamen keine Kurse von Yahoo; bitte später noch einmal umschalten.")
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
    with st.expander("Die Kerzen dieses Charts als Text, die neueste zuerst"):
        for satz in nachschlagen.kerzen_saetze(k, art, anzahl=anzahl):
            st.markdown(satz)


# ---------------------------------------------------------------------------
# Oberflaeche
# ---------------------------------------------------------------------------

st.title("Chart-Screening-Tool")
st.caption("Darvas Box; Minervini Trend Template; VCP; Cup & Handle; Rectangle Top; High & Tight Flag; "
           "EMA Crossback")

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
        st.error("Die Zugangsdaten der App lassen sich nicht lesen. Bitte die "
                 "Streamlit-Secrets prüfen.")
        st.stop()
    if not passwort.strip():
        st.warning("Zugangsschutz noch nicht eingerichtet: In den Streamlit-Secrets "
                   "fehlt HELIOT_PASSWORT. Bis dahin ist die App ohne Anmeldung offen.")
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
        st.session_state["zugang_hinweis"] = (
            f"Der Gastzugang ist um {zugang.uhrzeit_wien(stand['bis'])} Uhr abgelaufen.")
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
    st.markdown("### Anmeldung")
    hinweis = st.session_state.pop("zugang_hinweis", "")
    if hinweis:
        st.info(hinweis)
    bleiben_geht = zugang.bleiben_moeglich(passwort, geheimnis)
    with st.form("anmeldung", clear_on_submit=True):
        eingabe = st.text_input("Passwort oder Gastpasswort", type="password")
        bleiben = False
        if bleiben_geht:
            bleiben = st.checkbox("Angemeldet bleiben, in diesem Browser 30 Tage ab dem letzten Öffnen",
                                  value=True)
        senden = st.form_submit_button("Anmelden", type="primary")
    if bleiben_geht:
        st.caption("Mit Gastpasswort bleibt der Browser nur so lange angemeldet, wie das Gastpasswort gilt. "
                   "Auf fremden Geräten den Haken bitte entfernen. Safari auf dem iPhone vergisst die "
                   "Anmeldung, wenn die App sieben Tage lang nicht geöffnet wurde.")
    if senden:
        bremse = _anmelde_bremse()
        gesperrt = bremse.gesperrt_bis(jetzt)
        pause = float(st.session_state.get("zugang_pause_bis") or 0)
        if not (eingabe or "").strip():
            st.error("Bitte ein Passwort eingeben.")
        elif gesperrt:
            st.error("Zu viele Fehlversuche in den letzten zehn Minuten. Die Anmeldung "
                     f"ist bis {zugang.uhrzeit_wien(gesperrt)} Uhr gesperrt.")
        elif jetzt < pause:
            st.error("Fünf Fehlversuche hintereinander. Bitte eine Minute warten "
                     "und dann erneut versuchen.")
        else:
            rolle_neu, bis = zugang.anmelden(eingabe, passwort, geheimnis, jetzt)
            if rolle_neu:
                _abmelden()
                st.session_state.pop("bleiben_verworfen", None)
                st.session_state["zugang"] = {"rolle": rolle_neu, "bis": bis,
                                              "bleiben": bool(bleiben and bleiben_geht)}
                st.rerun()
            anzahl = bremse.fehlversuch(jetzt)
            zaehler, pause_bis = zugang.sitzung_nach_fehlversuch(
                int(st.session_state.get("zugang_fehl") or 0), jetzt)
            st.session_state["zugang_fehl"] = zaehler
            if pause_bis:
                st.session_state["zugang_pause_bis"] = pause_bis
                st.error("Das Passwort stimmt nicht. Das war der fünfte Fehlversuch "
                         "hintereinander; bitte eine Minute warten.")
            else:
                st.error("Das Passwort stimmt nicht.")
            if anzahl >= zugang.GESAMT_GRENZE:
                print(f"Anmeldung: {anzahl} Fehlversuche in zehn Minuten, Sperre aktiv")
    st.stop()


rolle = anmeldung()
if rolle in ("voll", "gast"):
    stand_anzeige = st.session_state.get("zugang") or {}
    if rolle == "gast":
        zeile = ("Gastzugang zum Lesen, gültig bis "
                 f"{zugang.uhrzeit_wien(stand_anzeige['bis'])} Uhr Wiener Zeit.")
    else:
        zeile = "Angemeldet mit vollem Zugang."
    if stand_anzeige.get("bleiben") and st.session_state.get("bleiben_ende"):
        if (st.session_state.get(BLEIBEN_SCHLUESSEL) or {}).get("gespeichert") is False:
            zeile += (" Dieser Browser lässt die App die Anmeldung nicht speichern; beim nächsten "
                      "Öffnen ist das Passwort wieder einzugeben.")
        elif rolle == "gast":
            zeile += " Dieser Browser bleibt bis zum Ablauf angemeldet."
        else:
            zeile += (" Dieser Browser bleibt angemeldet; wird die App bis zum "
                      f"{_datum_wien(st.session_state['bleiben_ende'])} nicht mehr geöffnet, endet das.")
    st.write(zeile)
    st.button("Abmelden", key="abmelden", on_click=_abmelden_knopf)

# Kursdaten kommen seit der Umstellung von Yahoo und brauchen keinen
# Schlüssel. Twelve Data ist nur noch Rückfallebene — die App startet
# deshalb auch ohne. Früher stand hier st.stop(), was den Start ganz
# verhindert hätte.
api_key = get_api_key()
if not api_key and rolle != "gast":
    st.caption("Datenquelle: Yahoo, ohne Schlüssel. Für eine Rückfallebene "
               "könnte TWELVE_DATA_API_KEY in den Streamlit-Secrets hinterlegt werden.")


# --- Aktie nachschlagen (Mathias, 13.09.2026) -----------------------------
# GANZ OBEN, vor den Registerkarten: das Suchfeld, darunter alles als Text
# in eigenen Absaetzen mit Zwischenueberschriften, damit VoiceOver am
# iPhone von Ueberschrift zu Ueberschrift springen kann. Keine Tabellen,
# keine Spalten, keine Kennzahlkaesten. Die Zahlen kommen aus den
# Nachtdateien im Repo (RS, Ratings, Sektor-Rangliste, Volumenkurven) und
# live von Yahoo (Kurs, Volumen); gerechnet wird in nachschlagen.py, das
# ohne Netz pruefbar ist.


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


st.markdown("### Aktie nachschlagen")
# DAS FELD STEHT IN DER ADRESSE (Mathias, 14.09.2026): bind="query-params"
# schreibt die Eingabe als ?aktie=... in die Adresse der Seite und liest sie
# beim Oeffnen wieder. So fuehrt ein Verweis wie ?aktie=AAOI direkt zu den
# vollstaendigen Daten einer Aktie, und ein Lesezeichen merkt sich die Aktie.
nachschlag_eingabe = (st.text_input("Kürzel oder Firmenname eingeben, dann Eingabetaste", key="aktie",
                                    bind="query-params", placeholder="zum Beispiel AAOI oder Apple")
                      or "").strip()
if nachschlag_eingabe:
    nachschlag_daten = nachschlag_dateien()
    nachschlag_ticker, nachschlag_kandidaten = nachschlagen.finde(nachschlag_eingabe,
                                                                  nachschlag_daten.get("rs_universum.json"))
    if nachschlag_ticker is None:
        if nachschlag_kandidaten:
            st.markdown("Mehrere Aktien passen. Bitte das Kürzel eingeben:")
            for k, n in nachschlag_kandidaten:
                st.markdown(f"{k}, {n}")
        else:
            st.markdown("Nichts gefunden. Bitte Kürzel oder Namen prüfen.")
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
            # Die Muster laufen mit dem echten RS aus der Nachtdatei, nicht mit
            # einer Schaetzung (siehe analysiere).
            nachschlag_e = nachschlagen.eintraege(nachschlag_daten.get("rs_universum.json")).get(nachschlag_ticker, {})
            nachschlag_rs, nachschlag_rs_satz = nachschlagen.rs_fuer_muster(nachschlag_e)
            try:
                nachschlag_df, nachschlag_res = muster_fuer(nachschlag_ticker, api_key, nachschlag_rs)
            except Exception:
                nachschlag_df, nachschlag_res = None, None
        for ueberschrift, saetze in nachschlagen.bericht(
                nachschlag_ticker, nachschlag_daten.get("rs_universum.json"), nachschlag_daten.get("ibd_ratings.json"),
                nachschlag_daten.get("sektor_rangliste.json"), live=nachschlag_live_werte, kurve=nachschlag_k,
                kurve_quelle=nachschlag_kq, sektor_name=nachschlag_s, sektor_quelle=nachschlag_sq):
            st.markdown(f"#### {ueberschrift}")
            for satz in saetze:
                st.markdown(satz)

        # MUSTER, KAUFPUNKTE, CHARTS (Mathias, 14.09.2026). Diese Teile
        # stammen aus der frueheren Einzelabfrage, die damit entfaellt.
        st.markdown("#### Chartmuster und Trend Template")
        for satz in nachschlagen.muster_saetze(nachschlag_res, nachschlag_rs_satz if nachschlag_res else None):
            st.markdown(satz)
        st.markdown("#### Kaufpunkte")
        if nachschlag_res:
            for satz in nachschlagen.kaufpunkt_saetze(nachschlag_res):
                st.markdown(satz)
            st.caption("Der folgende Chart zeigt die letzten 180 Handelstage mit den Kaufpunkten als waagrechte "
                       "Linien; alle Werte stehen darüber als Text.")
            zeichne_kaufpunkt_chart(nachschlag_df, nachschlag_res, nachschlag_ticker)
        else:
            st.markdown("Ohne Kursdaten gibt es keine Kaufpunkte. Zwei mögliche Gründe: Die Schreibweise stimmt "
                        "nicht, oder die Kursquelle bremst gerade auf den geteilten Servern; dann in ein paar "
                        "Minuten noch einmal nachschlagen.")
        st.markdown("#### Aktienchart")
        aktienchart(nachschlag_ticker, nachschlag_df)

st.markdown("---")

# Gaeste bekommen weder die Wochenliste noch die Seite fuer Gastpasswoerter.
# Ohne eingerichtetes Passwort gibt es keine Gastpasswoerter, also auch die
# Seite dafuer nicht.
# DIE EINZELABFRAGE IST ENTFALLEN (Mathias, 14.09.2026): Sie zeigte Muster,
# Kaufpunkte und Chart einer Aktie mit einem geschaetzten RS. Muster,
# Kaufpunkte und Chart stehen jetzt beim Nachschlagen oben, mit dem echten RS.
tab_upload = tab_gast = None
if rolle == "gast":
    tab_liste, tab_scan, tab_info = st.tabs(["Liste prüfen", "Aktueller Scan", "Regelwerk"])
elif rolle == "voll":
    tab_liste, tab_scan, tab_upload, tab_gast, tab_info = st.tabs(
        ["Liste prüfen", "Aktueller Scan", "Wochenliste", "Gastzugang", "Regelwerk"])
else:
    tab_liste, tab_scan, tab_upload, tab_info = st.tabs(
        ["Liste prüfen", "Aktueller Scan", "Wochenliste", "Regelwerk"])


def tt_text(wert) -> str:
    """Die Spalte Trend Template einer Mappe in Worten: 'erfüllt, 8 von 8'
    oder '7 von 8'. Versteht die alte Schreibweise mit Haken und Kreuz."""
    m = re.search(r"(\d)\s*(?:/|von)\s*8", str(wert or ""))
    if not m:
        return nachschlagen.lesbar(wert) or "unbekannt"
    return ("erfüllt, " if m.group(1) == "8" else "") + f"{m.group(1)} von 8"


def mappe_text(wert) -> str:
    """Eine Zelle der Mappe in Worten: Haken und Kreuz der alten Schreibweise
    werden zu 'erfüllt' und 'nicht erfüllt', andere Bildzeichen fallen weg."""
    s = str(wert if wert is not None else "")
    s = s.replace("\u2713", "erfüllt ").replace("\u2717", "nicht erfüllt ")
    return nachschlagen.lesbar(s) or "unbekannt"


# --- Liste pruefen ---------------------------------------------------------
with tab_liste:
    st.write("Mehrere Aktien auf einmal prüfen: Finviz-CSV hochladen oder Kürzel mit Beistrich getrennt "
             "eintippen.")
    hoch = st.file_uploader("Finviz-CSV mit der Spalte Ticker", type=["csv"])
    manuell = st.text_input("oder Kürzel mit Beistrich getrennt", placeholder="AAOI, ETON, NVDA, LASR")

    tickers = []
    if hoch is not None:
        try:
            df_csv = pd.read_csv(hoch)
            spalte = next((c for c in df_csv.columns if c.strip().lower() == "ticker"), None)
            if spalte:
                tickers = [str(t).strip().upper() for t in df_csv[spalte].dropna()]
            else:
                st.error("Keine Spalte Ticker in der CSV gefunden.")
        except Exception as e:
            st.error(f"Die CSV ließ sich nicht lesen: {e}")
    elif manuell:
        tickers = [t.strip().upper() for t in manuell.replace(";", ",").split(",") if t.strip()]

    tickers = list(dict.fromkeys([t for t in tickers if t]))  # Duplikate raus

    if tickers:
        st.info(f"{len(tickers)} Kürzel erkannt. Für jede Aktie werden die Kurse von Yahoo geholt; "
                "bei vielen Aktien dauert das einige Minuten.")
        nur_treffer = st.checkbox("Nur Aktien mit aktivem Chartmuster anzeigen", value=True)
        if st.button("Liste durchrechnen", type="primary"):
            fortschritt = st.progress(0.0)
            status = st.empty()
            zeilen, fehler = [], []
            rs_eintraege = nachschlagen.eintraege(nachschlag_dateien().get("rs_universum.json"))
            for i, t in enumerate(tickers, 1):
                status.text(f"{i} von {len(tickers)}: {t}")
                rs_wert, _ = nachschlagen.rs_fuer_muster(rs_eintraege.get(t))
                try:
                    df, res = analysiere(t, api_key, rs_wert)
                except Exception:
                    df, res = None, None
                if df is None:
                    fehler.append(t)
                else:
                    echte = [p for p in res["points"] if not p["strategie"].startswith("Fallback")]
                    if not (nur_treffer and not echte):
                        zeile = {
                            "Ticker": t,
                            "Kurs": round(res["close"], 2),
                            "RS": int(rs_wert) if rs_wert is not None else "",
                            "52W-Hoch": round(res["hi52"], 2),
                            "Abst. Hoch": f"{(res['close'] / res['hi52'] - 1) * 100:+.1f}%",
                            "Trend Template": ("erfüllt, 8 von 8" if res["tt_pass"]
                                               else f"{res['tt_count']} von 8"),
                            "Muster": len(echte),
                        }
                        for n, p in enumerate(res["points"], 1):
                            zeile[f"KP{n} Strategie"] = p["strategie"]
                            zeile[f"KP{n} Preis"] = p["kaufpunkt"]
                            zeile[f"KP{n} Stop"] = p["stop"]
                            zeile[f"KP{n} Ziel"] = p["ziel"] if p["ziel"] else ""
                            zeile[f"KP{n} Status"] = p["status"]
                        zeilen.append(zeile)
                fortschritt.progress(i / len(tickers))
            status.empty()
            fortschritt.empty()

            if zeilen:
                erg = pd.DataFrame(zeilen).sort_values("Muster", ascending=False)
                st.success(f"{len(erg)} Treffer" + (f", {len(fehler)} ohne Daten" if fehler else ""))
                # ALS LISTE, nicht als Tabelle: Die Tabelle von Streamlit ist
                # eine Zeichenflaeche, die kein Screenreader lesen kann. Sie
                # steht zusaetzlich im Ausklapper darunter.
                for _, z in erg.iterrows():
                    teile = [f"{z['Ticker']}", f"Kurs {nachschlagen.zahl(z['Kurs'], 2)} Dollar"]
                    if z["RS"] != "":
                        teile.append(f"RS {z['RS']}")
                    teile.append(f"Trend Template {z['Trend Template']}")
                    kps = []
                    for n in (1, 2, 3):
                        s = z.get(f"KP{n} Strategie")
                        if isinstance(s, str) and s and not s.startswith("Fallback"):
                            kps.append(f"{nachschlagen.lesbar(s)} Kaufpunkt {nachschlagen.zahl(z[f'KP{n} Preis'], 2)}")
                    teile.append(("Muster: " + ", ".join(kps)) if kps else "kein Muster")
                    st.markdown("; ".join(teile) + ".")
                puffer = io.BytesIO()
                with pd.ExcelWriter(puffer, engine="openpyxl") as w:
                    erg.to_excel(w, sheet_name="Kaufpunkte", index=False)
                st.download_button("Als Excel herunterladen", puffer.getvalue(),
                                   file_name=f"kaufpunkte_{datetime.now():%Y-%m-%d}.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument."
                                        "spreadsheetml.sheet")
                with st.expander("Alle Werte als Tabelle, für das Auge"):
                    st.dataframe(erg, hide_index=True)
            else:
                st.warning("Keine Treffer" + (", nur Aktien mit Muster sind angehakt" if nur_treffer else "") + ".")
            if fehler:
                st.caption("Keine Daten für: " + ", ".join(fehler))

# --- Aktueller Scan --------------------------------------------------------
# Fenster auf die Nachtergebnisse (Mathias' Auftrag vom 23.07.2026): Der
# Scanner legt sein Ergebnis seit demselben Tag als kaufpunkte_aktuell.xlsx
# ins Repo (scanner.yml, Schritt 'Ergebnis für die Heliot-Anzeige
# veröffentlichen'). Diese Karte zeigt es gut vorlesbar an — als Liste,
# nicht als Tabelle (JAWS), die Tabelle gibt es zusätzlich im Ausklapper.

REPO = "mat-schmuck/heliot"
SCAN_DATEI = "kaufpunkte_aktuell.xlsx"


@st.cache_data(ttl=600, show_spinner=False)
def lade_nachtscan():
    """Liefert (DataFrame, Standtext, Rohbytes) — oder (None, Hinweis, None)."""
    import requests
    try:
        r = requests.get(
            f"https://raw.githubusercontent.com/{REPO}/main/{SCAN_DATEI}",
            timeout=20)
    except Exception as e:
        return None, f"Netzwerkfehler beim Laden: {e}", None
    if r.status_code == 404:
        return None, ("Noch kein Nachtscan abgelegt. Die Datei entsteht beim "
                      "nächsten Lauf des Scanners und liegt dann jeden Morgen "
                      "hier bereit."), None
    if r.status_code != 200:
        return None, f"GitHub antwortete mit Code {r.status_code}.", None
    try:
        df = pd.read_excel(io.BytesIO(r.content), sheet_name="Kaufpunkte")
    except Exception as e:
        return None, f"Die Ergebnisdatei ließ sich nicht lesen ({e}).", None
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
    return df, stand, r.content


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


with tab_scan:
    df_scan, scan_info, scan_roh = lade_nachtscan()
    if df_scan is None:
        st.info(scan_info)
    else:
        if scan_info:
            st.caption(f"Stand: {scan_info}.")
        # R1 bis R3 (Gerhard, 12.09.2026, ergaenzt am selben Abend): der
        # Bezug steht in der App. Die Spalte heisst aus Bestandsgruenden
        # weiter "RS Nasdaq", gerechnet wird gegen den ganzen US-Markt.
        st.caption("RS: relative Stärke gegen alle Stammaktien des US-Markts (Nasdaq, NYSE, "
                   "NYSE American, mindestens 253 Schlusskurse), jede Einzelrendite bei plus "
                   "50 Prozent gekappt; Entscheidungshilfe, kein Filter. Jüngere Titel ab 64 "
                   "Schlusskursen tragen ein vorläufiges RS aus den vorhandenen Quartalen. "
                   "RS-Rank dagegen ist das Perzentil innerhalb der Wochenliste.")

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
            # ist die Mappe leer, bis eine neue Wochenliste hochgeladen und
            # gescannt ist (wochenputz.py). Das ist gewollt, kein Fehler.
            st.info("Zurzeit gibt es keine Kaufpunkte: Der Wochenputz hat die "
                    "alte Woche geleert. Sobald eine neue Wochenliste hochgeladen "
                    "und gescannt ist, stehen hier wieder Kaufpunkte.")
        else:
            st.write(f"Geprüft wurden {len(df_scan)} Aktien. {len(treffer_zeilen)} "
                     f"davon tragen ein echtes Chartmuster, zusammen "
                     f"{anzahl_muster} Muster-Kaufpunkte. Genau diese überwachen "
                     "die TraderFox-Alarme und der Breakout-Wächter.")

        # Beste zuerst: volle Trend-Template-Punktzahl nach oben
        def _rang(paar):
            m = re.search(r"(\d)\s*(?:/|von)\s*8", str(paar[0].get("Trend Template", "")))
            return -(int(m.group(1)) if m else -1)

        for z, muster in sorted(treffer_zeilen, key=_rang):
            with st.container(border=True):
                st.markdown(f"**{z['Ticker']}, {nachschlagen.lesbar(z.get('Firma', ''))}**")
                st.write(f"Kurs {_zahl(z.get('Kurs'))} Dollar; "
                         f"RS {rs_mappe(z.get('RS Nasdaq'))}; "
                         f"Trend Template {tt_text(z.get('Trend Template'))}; "
                         f"Umsatzwachstum {mappe_text(z.get('Umsatzwachstum', '?'))}")
                for k, s in muster:
                    teile = [f"{nachschlagen.anzeige_text(s)}: Kaufpunkt {_zahl(z.get(f'KP{k} Preis'))} Dollar"]
                    if _zahl(z.get(f"KP{k} Stop")):
                        teile.append(f"Stop {_zahl(z.get(f'KP{k} Stop'))}")
                    if _zahl(z.get(f"KP{k} Ziel")):
                        teile.append(f"Ziel {_zahl(z.get(f'KP{k} Ziel'))}")
                    status = z.get(f"KP{k} Status")
                    if isinstance(status, str) and nachschlagen.anzeige_text(status):
                        teile.append(nachschlagen.anzeige_text(status))
                    st.write("; ".join(teile))

        if scan_roh:
            st.download_button("Nachtscan als Excel herunterladen", scan_roh,
                               file_name=SCAN_DATEI,
                               mime="application/vnd.openxmlformats-"
                                    "officedocument.spreadsheetml.sheet")
        with st.expander("Alle Werte als Tabelle, für das Auge"):
            st.dataframe(df_scan, hide_index=True)


# --- Regelwerk -------------------------------------------------------------
with tab_info:
    st.markdown("""
#### Was das Tool prüft

**1. Darvas Box.** Neues 52-Wochen-Hoch, danach eine Box aus drei plus drei Tagen. Kauf über der
Oberkante der Box, Stop unter ihrer Unterkante. Gemeldet werden nur frische Boxen, deren Hoch nicht
älter als 25 Tage ist.

**2. Minervini Trend Template.** Acht Bedingungen, die alle erfüllt sein müssen: Kurs über dem 150- und
dem 200-Tage-Durchschnitt, der 150er über dem 200er, der 200er steigt seit einem Monat, der 50er über
beiden, Kurs über dem 50er, mindestens 25 Prozent über dem 52-Wochen-Tief, höchstens 25 Prozent unter
dem 52-Wochen-Hoch und RS mindestens 70. Liefert selbst keinen Kaufpunkt, ist aber Voraussetzung für
den VCP.

**3. VCP.** Mindestens zwei bis drei Kontraktionen mit abnehmender Tiefe und austrocknendem Volumen.
Kauf über dem Pivot, Stop 8 Prozent darunter.

**4. Cup & Handle.** Die U-Form wird über eine quadratische Anpassung geprüft, V-Formen fallen weg;
Tiefe 12 bis 50 Prozent, der Henkel höchstens ein Drittel der Tassenhöhe im oberen Drittel. Das
Ergebnis ist eine Punktzahl, weil die Formerkennung unscharf ist. Ziel gleich Ausbruch plus Tassenhöhe.

**5. Rectangle Top.** Mindestens zwei Berührungen oben und unten. Kauf einen Cent über der Oberkante,
der Kurs muss zusätzlich über dem 21-Tage-Durchschnitt liegen. Ziel gleich Ausbruch plus Rechteckhöhe.

**6. High & Tight Flag.** Mast mit mindestens 90 Prozent Anstieg in unter 42 Tagen, Tief mindestens ein
Dollar, Konsolidierung höchstens 35 Kalendertage und eng. Selten, aber stark.

---

#### Grenzen, die du kennen solltest

- **RS gegen den ganzen US-Markt.** Aktie nachschlagen und Liste prüfen nehmen das RS aus der
Nachtdatei: das Perzentil gegen alle Stammaktien des US-Markts, jede Einzelrendite bei plus 50 Prozent
gekappt; an dreizehn öffentlichen IBD-Werten gemessen liegt es innerhalb von 5 Punkten. Junge Titel
tragen ein vorläufiges RS aus den vorhandenen Quartalen. Fehlt ein RS, gilt die RS-Bedingung des
Trend Templates als nicht erfüllt. Der Nachtscan prüft das Trend Template weiterhin mit dem RS-Rank
innerhalb der Wochenliste.
- **Kaufpunkt heißt nicht Kaufsignal.** Die Volumenbestätigung am Ausbruchstag prüft dieses Tool nicht,
dafür ist der Breakout-Wächter da.
- **Kursdaten sind 15 Minuten zwischengespeichert**, um Abrufe zu sparen.
    """)


# --- Ab hier nur mit vollem Zugang -----------------------------------------
# Gaeste sind hier fertig (Mathias, 13.09.2026): Die Wochenliste schreibt ueber
# den GitHub-Token ins Repo, und Gastpasswoerter erzeugt nur, wer das feste
# Passwort kennt. Fuer Gaeste gibt es tab_upload und tab_gast deshalb gar
# nicht, und der Lauf der Seite endet hier, bevor davon etwas gebaut wird.
# Die Gesamtpruefung (Block H) achtet darauf, dass das so bleibt.
if tab_upload is None:
    st.stop()


# --- Wochenliste -----------------------------------------------------------
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

LISTEN_DATEI = "finviz_3.csv"     # REPO ist oben beim Aktuellen Scan definiert
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
                           ziel: str = None) -> tuple:
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
            daten = {"message": f"{ziel}: {anzahl} Aktien (Upload über Heliot)",
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


with tab_upload:
    st.write("Hier lädt Gerhard seine wöchentlichen Aktienlisten hoch "
             "(CSV mit der Spalte 'Ticker'). Es sind ZWEI: die große Liste "
             "für alle Strategien und die Darvas-Liste. Auf der großen "
             "läuft alles außer Darvas, auf der Darvas-Liste läuft alles. "
             "Die neuen Listen gelten ab dem nächsten nächtlichen Scan.")

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
        st.warning("Der Upload ist noch nicht eingerichtet. In den "
                   "Streamlit-Secrets muss GITHUB_TOKEN hinterlegt sein; "
                   "bis dahin ist diese Seite nur Anzeige.")
    else:
        datei = st.file_uploader("CSV mit der Spalte 'Ticker'", type=["csv"],
                                 key="upload_datei")
        # Der Dateiname schlaegt die Liste vor, entschieden wird hier
        # sichtbar. Ein stiller Griff in die falsche Liste waere der
        # teuerste Fehler dieser Seite.
        vorschlag = liste_aus_dateiname(datei.name if datei else "")
        wahl = st.radio(
            "In welche Liste?",
            [f"Große Liste für alle Strategien außer Darvas ({LISTEN_DATEI})",
             f"Darvas-Liste, dort laufen ALLE Strategien ({DARVAS_DATEI})"],
            index=1 if vorschlag == DARVAS_DATEI else 0, key="upload_wahl")
        ziel_datei = DARVAS_DATEI if wahl.startswith("Darvas") else LISTEN_DATEI
        if datei is not None:
            st.caption(f"Aus dem Dateinamen {datei.name} geschlossen: "
                       f"{vorschlag}. Bitte oben prüfen.")
        if datei is not None and st.button(f"Liste {ziel_datei} übernehmen",
                                           type="primary"):
            roh = datei.getvalue()
            fehler, ticker = pruefe_wochenliste(roh)
            if fehler:
                st.error("NICHT übernommen: " + fehler)
            else:
                fehler, zweige = wochenliste_einspielen(
                    roh, github_token, len(ticker), ziel_datei)
                # Der Zaehler wird auch bei einem Teilerfolg geleert:
                # Auf mindestens einem Zweig steht die neue Liste.
                if zweige:
                    aktuelle_listengroesse.clear()
                if fehler:
                    st.error("Hochladen: " + fehler)
                else:
                    st.success(f"Übernommen in {ziel_datei} auf "
                               f"{zweige}: {len(ticker)} Aktien "
                               f"(die ersten: {', '.join(ticker[:5])}). "
                               "Ab dem nächsten nächtlichen Scan aktiv.")


# --- Gastzugang (Mathias, 13.09.2026) ---------------------------------------
# Nur mit dem festen Passwort. Das Gastpasswort wird gerechnet, nicht
# gespeichert (zugang.py): Es gilt fuer alle, die es bekommen, und laesst sich
# vor dem Ablauf nur zuruecknehmen, indem GAST_GEHEIMNIS geaendert wird.
if tab_gast is not None:
    with tab_gast:
        st.markdown("#### Gastpasswort erzeugen")
        st.write("Ein Gastpasswort öffnet die App für mindestens 60 Minuten zum Lesen: "
                 "Aktie nachschlagen, Liste prüfen, Aktueller Scan und Regelwerk. "
                 "Die Wochenliste und diese Seite sehen Gäste nicht, verändern können sie "
                 "nichts. Weitergegeben wird das Passwort von dem, der es erzeugt.")
        gast_geheimnis = _secret("GAST_GEHEIMNIS") or ""
        if not gast_geheimnis.strip():
            st.warning("Gastpasswörter sind noch nicht eingerichtet: In den "
                       "Streamlit-Secrets fehlt GAST_GEHEIMNIS.")
        else:
            if st.button("Gastpasswort erzeugen", type="primary", key="gast_erzeugen"):
                st.session_state["gast_erzeugt"] = zugang.erzeuge(gast_geheimnis, time.time())
            erzeugt = st.session_state.get("gast_erzeugt")
            if erzeugt and time.time() < erzeugt[1]:
                gast_pw, gast_bis = erzeugt
                st.markdown(f"Gastpasswort: **{gast_pw}**")
                st.write("Buchstabe für Buchstabe: " + zugang.buchstabiert(gast_pw))
                st.write(f"Gültig bis {zugang.uhrzeit_wien(gast_bis)} Uhr Wiener Zeit. "
                         "Groß- und Kleinschreibung spielt beim Gastpasswort keine Rolle.")
                st.code(gast_pw, language=None)
                st.caption("Wer innerhalb derselben zehn Minuten noch einmal erzeugt, "
                           "bekommt dasselbe Passwort. Vor dem Ablauf lassen sich alle "
                           "Gastpasswörter nur zurücknehmen, indem GAST_GEHEIMNIS in den "
                           "Streamlit-Secrets geändert wird.")
            elif erzeugt:
                st.info("Das zuletzt erzeugte Gastpasswort ist abgelaufen.")
