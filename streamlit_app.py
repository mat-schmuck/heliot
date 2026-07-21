#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CHART-SCREENING-TOOL — Web-Oberfläche
=====================================
Einzelticker oder Liste eingeben → alle 6 Muster werden sofort geprüft →
Kaufpunkte, Chart und Trend-Template-Check auf einen Blick.

Lokal starten:
  pip install streamlit pandas numpy scipy plotly requests openpyxl
  export TWELVE_DATA_API_KEY="dein_key"
  streamlit run streamlit_app.py

Auf Streamlit Community Cloud:
  1. streamlit_app.py + pattern_scanner.py + requirements.txt ins Repo
  2. share.streamlit.io → "New app" → Repo wählen → Main file: streamlit_app.py
  3. Advanced settings → Secrets → TWELVE_DATA_API_KEY = "dein_key"
"""

import io
import os
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st

import pattern_scanner as ps

st.set_page_config(page_title="Chart-Screening-Tool", page_icon="📈", layout="wide")


# ---------------------------------------------------------------------------
# Key + Datenabruf
# ---------------------------------------------------------------------------

def get_api_key() -> str | None:
    try:
        if "TWELVE_DATA_API_KEY" in st.secrets:
            return st.secrets["TWELVE_DATA_API_KEY"]
    except Exception:
        pass
    return os.environ.get("TWELVE_DATA_API_KEY")


@st.cache_data(ttl=900, show_spinner=False)
def hole_kurse(ticker: str, api_key: str) -> pd.DataFrame | None:
    """Kurshistorie holen — 15 Minuten gecacht, spart API-Calls."""
    limiter = ps.RateLimiter(60)  # im Web keine künstliche Bremse nötig
    return ps.fetch_history(ticker, api_key, limiter)


def analysiere(ticker: str, api_key: str):
    df = hole_kurse(ticker, api_key)
    if df is None:
        return None, None
    df_ind = ps.add_indicators(df)
    rs_roh = ps.rs_score(df_ind)
    # Ohne Vergleichsliste gibt es kein echtes Perzentil. Näherung über eine
    # tanh-Kennlinie: 0 (seitwärts) → 50, +0,8 (ca. +30 % p. a. stetig) → ~82,
    # stark negativ → ~15. Sanfter Verlauf statt harter Kappung bei 99.
    rs_schaetzung = None
    if rs_roh is not None:
        rs_schaetzung = float(np.clip(50 + 49 * np.tanh(rs_roh), 1, 99))
    res = ps.analyze(df_ind, rs_schaetzung)
    return df_ind, res


# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------

def zeichne_chart(df: pd.DataFrame, res: dict, ticker: str, tage: int = 180):
    try:
        import plotly.graph_objects as go
    except ImportError:
        st.info("Für Charts bitte plotly installieren (`pip install plotly`).")
        return

    sub = df.iloc[-tage:]
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=sub["datetime"], open=sub["open"], high=sub["high"],
        low=sub["low"], close=sub["close"], name=ticker,
        increasing_line_color="#26a69a", decreasing_line_color="#ef5350"))

    for ma, farbe in (("ma50", "#42a5f5"), ("ma150", "#ffa726"), ("ma200", "#ab47bc")):
        if ma in sub and not sub[ma].isna().all():
            fig.add_trace(go.Scatter(x=sub["datetime"], y=sub[ma], mode="lines",
                                     name=ma.upper(), line=dict(width=1.2, color=farbe)))

    farben = ["#00e676", "#ffee58", "#ff7043"]
    for i, p in enumerate(res["points"]):
        fig.add_hline(y=p["kaufpunkt"], line_dash="dash", line_color=farben[i],
                      line_width=1.5,
                      annotation_text=f"KP{i+1} {p['kaufpunkt']:.2f} — {p['strategie'][:22]}",
                      annotation_position="right",
                      annotation_font=dict(size=10, color=farben[i]))

    fig.update_layout(height=520, xaxis_rangeslider_visible=False,
                      margin=dict(l=10, r=10, t=30, b=10),
                      legend=dict(orientation="h", y=1.02, yanchor="bottom"),
                      template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Darstellung eines Ergebnisses
# ---------------------------------------------------------------------------

def zeige_ergebnis(ticker: str, df: pd.DataFrame, res: dict, mit_chart: bool = True):
    kurs = res["close"]
    abst_hoch = (kurs / res["hi52"] - 1) * 100
    ueber_tief = (kurs / res["lo52"] - 1) * 100

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Kurs", f"{kurs:.2f} $")
    c2.metric("52W-Hoch", f"{res['hi52']:.2f}", f"{abst_hoch:+.1f}%")
    c3.metric("52W-Tief", f"{res['lo52']:.2f}", f"{ueber_tief:+.1f}%")
    c4.metric("RS (geschätzt)", f"{res['rs']:.0f}" if res["rs"] is not None else "n/a")

    # Trend Template
    if res["tt_pass"]:
        st.success("✅ **Minervini Trend Template: 8/8 erfüllt** — Stage-2-Aufwärtstrend")
    else:
        st.warning(f"⚠️ **Trend Template: {res['tt_count']}/8** — nicht erfüllt")
        with st.expander("Welche Kriterien fehlen?"):
            for f in res["tt_failed"]:
                st.write(f"• {f}")

    # Muster
    echte = [p for p in res["points"] if not p["strategie"].startswith("Fallback")]
    if echte:
        st.success(f"🎯 **{len(echte)} aktives Chartmuster** gefunden: "
                   + ", ".join(p["strategie"] for p in echte))
    else:
        st.info("Kein aktives Chartmuster — die Kaufpunkte unten sind generische "
                "Orientierungslevel, keine Regelwerk-Signale.")

    if mit_chart:
        zeichne_chart(df, res, ticker)

    st.markdown("#### Kaufpunkte")
    for i, p in enumerate(res["points"], 1):
        ist_muster = not p["strategie"].startswith("Fallback")
        abstand = (p["kaufpunkt"] / kurs - 1) * 100
        risiko = (p["kaufpunkt"] / p["stop"] - 1) * 100 if p["stop"] else None
        with st.container(border=True):
            k1, k2 = st.columns([3, 2])
            with k1:
                st.markdown(f"**KP{i}: {'🎯' if ist_muster else '○'} {p['strategie']}**")
                st.caption(p["status"])
                st.caption(p["notiz"])
            with k2:
                st.markdown(f"**Kaufpunkt: {p['kaufpunkt']:.2f} $** ({abstand:+.1f}% "
                            f"{'entfernt' if abstand > 0 else 'unterschritten'})")
                zeile = f"Stop: {p['stop']:.2f} $"
                if risiko is not None:
                    zeile += f"  (Risiko {abs(risiko):.1f}%)"
                st.markdown(zeile)
                if p["ziel"]:
                    chance = (p["ziel"] / p["kaufpunkt"] - 1) * 100
                    st.markdown(f"Ziel: {p['ziel']:.2f} $  (+{chance:.1f}%)")
                    if risiko:
                        crv = chance / abs(risiko)
                        st.markdown(f"**CRV: {crv:.1f} : 1**")

    st.caption("⚠️ Kaufpunkt heißt nicht Kaufsignal: Alle Breakouts brauchen laut "
               "Regelwerk zusätzlich eine Volumen-Bestätigung am Ausbruchstag.")


# ---------------------------------------------------------------------------
# Oberfläche
# ---------------------------------------------------------------------------

st.title("📈 Chart-Screening-Tool")
st.caption("Darvas Box · Minervini Trend Template · VCP · Cup & Handle · "
           "Rectangle Top · High & Tight Flag")

api_key = get_api_key()
if not api_key:
    st.error("Kein API-Key gefunden. Lokal: `export TWELVE_DATA_API_KEY=...` — "
             "in der Streamlit Cloud: unter Settings → Secrets eintragen.")
    st.stop()

tab_einzel, tab_liste, tab_info = st.tabs(["🔍 Einzelabfrage", "📋 Liste / CSV", "ℹ️ Regelwerk"])

# --- Einzelabfrage ---------------------------------------------------------
with tab_einzel:
    col_a, col_b = st.columns([3, 1])
    ticker = col_a.text_input("Ticker", value="", placeholder="z. B. AAOI, NVDA, ETON",
                              key="einzel_ticker").strip().upper()
    col_b.write("")
    los = col_b.button("Analysieren", type="primary", use_container_width=True)

    if ticker and (los or st.session_state.get("letzter") == ticker):
        st.session_state["letzter"] = ticker
        with st.spinner(f"Hole Kursdaten für {ticker} …"):
            df, res = analysiere(ticker, api_key)
        if df is None:
            st.error(f"Keine Kursdaten für **{ticker}** gefunden. Ticker-Schreibweise "
                     "prüfen (US-Symbole ohne Börsenkürzel, z. B. `NVDA`).")
        else:
            zeige_ergebnis(ticker, df, res)

# --- Liste / CSV -----------------------------------------------------------
with tab_liste:
    st.write("Mehrere Ticker auf einmal prüfen — Finviz-CSV hochladen oder "
             "Ticker per Komma eintippen.")
    hoch = st.file_uploader("Finviz-CSV (Spalte 'Ticker')", type=["csv"])
    manuell = st.text_input("… oder Ticker kommagetrennt",
                            placeholder="AAOI, ETON, NVDA, LASR")

    tickers = []
    if hoch is not None:
        try:
            df_csv = pd.read_csv(hoch)
            spalte = next((c for c in df_csv.columns if c.strip().lower() == "ticker"), None)
            if spalte:
                tickers = [str(t).strip().upper() for t in df_csv[spalte].dropna()]
            else:
                st.error("Keine Spalte 'Ticker' in der CSV gefunden.")
        except Exception as e:
            st.error(f"CSV konnte nicht gelesen werden: {e}")
    elif manuell:
        tickers = [t.strip().upper() for t in manuell.replace(";", ",").split(",") if t.strip()]

    tickers = list(dict.fromkeys([t for t in tickers if t]))  # Duplikate raus

    if tickers:
        st.info(f"{len(tickers)} Ticker erkannt. Rechne mit ca. "
                f"{max(1, len(tickers) // 4)} Sekunden pro Ticker beim ersten Mal.")
        nur_treffer = st.checkbox("Nur Aktien mit aktivem Chartmuster anzeigen", value=True)
        if st.button("Liste durchrechnen", type="primary"):
            fortschritt = st.progress(0.0)
            status = st.empty()
            zeilen, fehler = [], []
            for i, t in enumerate(tickers, 1):
                status.text(f"[{i}/{len(tickers)}] {t} …")
                try:
                    df, res = analysiere(t, api_key)
                except Exception as e:
                    df, res = None, None
                if df is None:
                    fehler.append(t)
                else:
                    echte = [p for p in res["points"] if not p["strategie"].startswith("Fallback")]
                    if nur_treffer and not echte:
                        pass
                    else:
                        zeile = {
                            "Ticker": t,
                            "Kurs": round(res["close"], 2),
                            "52W-Hoch": round(res["hi52"], 2),
                            "Abst. Hoch": f"{(res['close']/res['hi52']-1)*100:+.1f}%",
                            "Trend Template": "✓ 8/8" if res["tt_pass"] else f"✗ {res['tt_count']}/8",
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
                st.dataframe(erg, use_container_width=True, hide_index=True)
                puffer = io.BytesIO()
                with pd.ExcelWriter(puffer, engine="openpyxl") as w:
                    erg.to_excel(w, sheet_name="Kaufpunkte", index=False)
                st.download_button("📥 Als Excel herunterladen", puffer.getvalue(),
                                   file_name=f"kaufpunkte_{datetime.now():%Y-%m-%d}.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument."
                                        "spreadsheetml.sheet")
            else:
                st.warning("Keine Treffer" + (" (Filter aktiv?)" if nur_treffer else "") + ".")
            if fehler:
                st.caption("Keine Daten für: " + ", ".join(fehler))

# --- Regelwerk -------------------------------------------------------------
with tab_info:
    st.markdown("""
#### Was das Tool prüft

**1. Darvas Box** — Neues 52-Wochen-Hoch, danach Box aus 3+3 Tagen. Kauf über Box-Top,
Stop unter Box-Bottom. Nur frische Boxen (Hoch nicht älter als 25 Tage) werden gemeldet.

**2. Minervini Trend Template** — Reiner UND-Filter über 8 Kriterien (MA-Struktur,
steigender MA200, ≥25 % über 52W-Tief, ≤25 % unter 52W-Hoch, RS ≥ 70). Liefert selbst
keinen Kaufpunkt, ist aber Voraussetzung fürs VCP.

**3. VCP** — Mindestens 2-3 Kontraktionen mit abnehmender Tiefe plus Volume Dry-Up.
Kauf über dem Pivot, Stop 8 % darunter (Minervini-Standard).

**4. Cup & Handle** — U-Form über quadratischen Fit geprüft (V-Formen fliegen raus),
Tiefe 12-50 %, Handle max. 1/3 der Cup-Höhe im oberen Drittel. Ergebnis als
Toleranz-Score, weil die Formerkennung naturgemäß unscharf ist. Ziel = Breakout + Cup-Höhe.

**5. Rectangle Top** — Mindestens 2 Berührungen oben und unten. Kauf 1 Cent über dem
Rechteck-Top, zusätzlich muss der Kurs über dem SMA21 liegen (Bulkowskis bestes Setup:
~75 % Trefferquote). Ziel = Ausbruch + Rechteckhöhe.

**6. High & Tight Flag** — Mast ≥ 90 % Anstieg in unter 42 Tagen, Tief ≥ 1 $,
Konsolidierung ≤ 35 Kalendertage und eng. Selten, aber stark.

---

#### Grenzen, die du kennen solltest

- **RS-Rank ist hier nur geschätzt.** Bei einer Einzelabfrage fehlt die Vergleichsgruppe,
deshalb rechnet das Tool aus dem gewichteten Momentum eine Schätzung. Der Batch-Scanner
(`pattern_scanner.py`) bildet echte Perzentile innerhalb deiner Liste — der ist genauer.
- **Kaufpunkt ≠ Kaufsignal.** Die Volumen-Bestätigung am Ausbruchstag prüft dieses Tool
nicht — dafür ist der Breakout-Wächter da.
- **Kursdaten sind 15 Minuten gecacht**, um API-Calls zu sparen.
    """)
