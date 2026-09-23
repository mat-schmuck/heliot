#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CHARTMUSTER, ETAPPE 1 (Gerhard, 20.09.2026)
===========================================
Gerhards Dokument "Chartmuster_14_und fragenfuer_Mathias" vom 20.09.2026
(Mathias am 21.09.2026: "arbeite es zuerst ab"). Wortlaut des Grundsatzes:
"Das sind Entscheidungshilfen, keine Filter. Kein Muster darf eine Aktie aus
einer Liste werfen. Sie werden zu einem Treffer dazugeschrieben ... Wenn ein
Muster passt, steht es dabei; wenn nicht, steht nichts dabei."

Etappe 1 sind die sieben Muster, die nur Tages- und Wochenkerzen brauchen, in
Gerhards Reihenfolge: B Inside Day, A Three Weeks Tight, D Pocket Pivot,
F Power Trend, G Flat Base, S Wick Play, T Shakeout am EMA 10. Gerechnet wird
in der Nachttabelle (scanner_daten.py) am letzten Handelstag; die App schreibt
die Funde zu jedem Scanner-Treffer (scanner_ansicht.muster_saetze). Nichts
davon filtert.

Danach, wie Gerhard es vorsieht ("Danach die Pivot-Erkennung, weil H und N
beide darauf sitzen"), die Erkennung von Hochs und Tiefs (pivots) und darauf
N Shakeout plus drei (Tageskerzen), gebaut am 21.09.2026. Auch N filtert nichts.

L IPO BASE, seit 22.09.2026: Gerhards sechs Alarm-Muster sind A, B, D, L, N und
S; L fehlte noch. Es braucht als einziges Muster die Erstnotiz je Aktie, und
die kommt aus der Kurshistorie selbst (erstnotiz, samt der Mantel-Regel aus
seiner Antwort O14).

DIE ALARME SIND EIN EIGENER WEG (Gerhard, 22.09.2026, Antworten O1 bis O10):
A, B, D, L, N und S rechnen ihre Kaufpunkte im Nachtscan mit und melden im
Handel ueber den Waechter, ohne je einen bestehenden Kaufpunkt zu verdraengen.
Dieses Modul erkennt nur die Muster; der Weg dorthin steht in alarm_muster.py.

H DOUBLE BOTTOM IST GESTRICHEN (Gerhard, 22.09.2026, Antwort auf O35 bis O37):
"H fliegt raus. Nicht nur als Alarm-Kandidat ausschliessen, sondern komplett,
aus dem Scanner, aus jeder Datei-Spalte und aus dem Nachschlagen." Weg sind
damit die Funktion double_bottom, die Spalten cm_h, die Zahlen zu H in QUELLE
und FESTLEGUNGEN und die Saetze in der App. Die Pivot-Erkennung bleibt, N sitzt
darauf.

M STUFENZAEHLUNG UND K BASE-ON-BASE, seit 23.09.2026 (Gerhards Antworten auf
die Fragen 2 und 3 vom selben Tag, Reihenfolge seine: "zuerst M
Stufenzaehlung, direkt danach K Base-on-Base"): nur Scanner, kein Alarm, kein
Filter. Eine Basis dauert mindestens fuenf Wochen, ist hoechstens 35 Prozent
tief vom linken Hoch zum tiefsten Tief und ist ausgebrochen mit einem
Tagesschluss ueber dem linken Hoch; zurueckgesetzt wird an einem Markttief,
beim Unterschreiten des Tiefs der letzten Basis und bei 20 Prozent Rueckgang
vom letzten Hoch. Seine bewusste Folge: Jede Basis, die tiefer als 20 Prozent
korrigiert, ist Stufe eins. Die Markttiefs kommen aus der Marktampel
(marktbreite.markttiefs); gezaehlt wird ueber die GANZE Kurshistorie, deshalb
rechnet nur die Nachttabelle M, K und Q (werte mit voll).

Q GREEN LINE BREAKOUT, seit 23.09.2026 (Stop nach seiner Antwort auf Frage 5):
O15, "erst nach bestaetigtem Monatsschluss anzeigen, keine Zwischenstufe". Ein
Tagesschluss ueber der Linie wird also NICHT gezeigt, auch nicht mit dem
Vermerk, dass der Monatsschluss noch aussteht.

V EPISODIC PIVOT, seit 23.09.2026 mit Gerhards Zahlen vom selben Tag: tote
Phase mindestens zwei Monate, mindestens 15 Prozent unter dem
Zweihundert-Tage-Hoch, Volumen mindestens das Dreifache des
Fuenfzig-Tage-Schnitts ueber die F(t)-Kurve. Der Ausloeser sind Zahlen am
Lueckentag oder am Handelstag davor laut Nasdaq-Kalender; eine Luecke ohne
erkannten Ausloeser steht nach O16 GETRENNT da, mit dem Vermerk "Luecke ohne
erkannten Ausloeser" (cm_vl). Zulassung, Auftrag und Uebernahme erkennt der
Scanner nicht, dafuer fehlt eine Nachrichtenquelle; solche Luecken stehen
deshalb ebenfalls als Luecke ohne erkannten Ausloeser da. Den
Eroeffnungsbereich (das Hoch der ersten fuenf Minuten) holt die Nachttabelle
aus Fuenf-Minuten-Kursen und setzt Einstieg und Stop danach
(episodic_einstieg).

UNSERE FESTLEGUNGEN: Gerhard: "jede Zahl, die nicht aus der Quelle stammt,
sondern von uns gesetzt wurde ... wird im Code und in der Ausgabe als unsere
eigene Festlegung gekennzeichnet." Alle solchen Zahlen stehen in FESTLEGUNGEN
und nur dort; was in QUELLE steht, kommt aus Gerhards Regeln. Die App nennt die
Festlegungen im Erklaertext des Scanners (festlegung_saetze), und bei S und T,
deren Kernschwellen von uns sind, steht es in der Trefferzeile selbst.

VOLUMEN: Gerhard: "Volumenbedingungen in diesen Regeln beziehen sich immer auf
unsere eigene Volumenformel mit der F(t)-Kurve je Aktie." Die Nachttabelle
rechnet nach Handelsschluss; dort ist F(t) gleich eins, die Hochrechnung auf
den ganzen Tag also das Tagesvolumen selbst. Dieses Modul vergleicht deshalb
ganze Tagesvolumina. Im laufenden Handel muesste dieselbe Bedingung ueber die
F(t)-Kurve laufen; das kommt erst mit den Alarm-Strategien.

WOCHEN: Wochenkerzen entstehen aus den Tageskerzen (Montag bis Freitag). A, G
und L rechnen nur mit ABGESCHLOSSENEN Wochen: Die letzte Woche zaehlt, wenn ihr
letzter Handelstag ein Freitag ist; faellt der Freitag auf einen Feiertag,
zaehlt sie ab dem ersten Handelstag der Folgewoche.

Aufruf:
    python chartmuster.py --selbsttest
"""

import argparse
import bisect
import sys

import numpy as np
import pandas as pd

# Zahlen aus Gerhards Regeln (Quelle: IBD, Minervini, Morales und Kacher,
# TraderLion, wie im Dokument vom 20.09.2026 angegeben)
QUELLE = {
    "a_eng": 0.015,               # A: Wochenschluss hoechstens 1,5 Prozent vom Vorwochenschluss
    "a_wochen_min": 3,            # A: drei enge Wochen, vier zaehlen genauso
    "a_wochen_max": 4,            # A: vier enge Wochen zaehlen auch, ab fuenf nicht mehr (Gerhard, 23.09.2026)
    "aufschlag": 0.10,            # A und G: Kaufpunkt Hoch plus 0,10 Dollar
    "d_fenster": 10,              # D: Abwaertstage der letzten zehn Handelstage
    "f_tage_ueber_ema": 10,       # F: seit zehn Handelstagen jedes Tief ueber dem EMA 21
    "f_sma50_steigt": 20,         # F: SMA 50 steigt seit zwanzig Tagen
    "g_wochen_min": 5,            # G: mindestens fuenf Wochen
    "g_tiefe_max": 0.15,          # G: hoechstens 15 Prozent tief
    "g_anstieg_min": 0.20,        # G: davor mindestens 20 Prozent Anstieg
    "l_wochen_min": 3,            # L: Basis schon nach drei bis vier Wochen statt der sonst geforderten fuenf bis sieben
    "l_tiefe_min": 0.20,          # L: Tiefe zwanzig bis fuenfzig Prozent (bei einer normalen Basis waere das zu viel)
    "l_tiefe_max": 0.50,
    "n_aufschlag": (0.05, 0.10),  # N: Einstieg Tief mal (1 + p), p zwischen 0,05 und 0,10; beide nebeneinander
    # M und K (Papier vom 20.09.2026, Zahlen vom 23.09.2026, Fragen 2 und 3)
    "m_kurs_min": 10.0,           # M: gezaehlt nur fuer Aktien ueber zehn Dollar
    "m_wochen_min": 5,            # M: eine Basis dauert mindestens fuenf Wochen
    "m_tiefe_max": 0.35,          # M: hoechstens 35 Prozent vom linken Hoch zum tiefsten Tief
    "m_korrektur": 0.20,          # M: 20 Prozent unter dem letzten Hoch setzt die Zaehlung zurueck
    "k_gewinn_min": 0.20,         # K: unter 20 Prozent Gewinn zwischen zwei Basen zaehlen beide als eine Stufe
    # Q (Papier vom 20.09.2026)
    "q_tage_ohne_hoch": 63,       # Q: seit dem Allzeithoch mindestens 63 Handelstage ohne neues Hoch
    # V (Papier vom 20.09.2026, Zahlen vom 23.09.2026, Frage 4)
    "v_luecke": 0.10,             # V: Open[t] durch Close[t-1] minus 1 ueber zehn Prozent
    "v_tote_tage": 42,            # V: tote Phase mindestens zwei Monate, gerechnet wie bei Q (drei Monate sind 63)
    "v_hoch_tage": 200,           # V: das Zweihundert-Tage-Hoch
    "v_abstand_200": 0.15,        # V: mindestens 15 Prozent darunter
    "v_vol_faktor": 3.0,          # V: Volumen mindestens das Dreifache ...
    "v_vol_tage": 50,             # V: ... des Fuenfzig-Tage-Schnitts
}

# UNSERE FESTLEGUNGEN (die Quelle nennt dazu keine Zahl)
FESTLEGUNGEN = {
    # A: "davor ein Ausbruch aus einer Basis oder ein Anstieg": mindestens 20
    # Prozent vom tiefsten Wochentief der zwoelf Wochen vor der engen Phase
    # bis zum Schluss der Woche davor (die 20 Prozent wie bei G).
    "a_anstieg_min": 0.20,
    "a_anstieg_wochen": 12,
    # A: Die Obergrenze der engen Wochen steht seit dem 23.09.2026 in QUELLE.
    # Gerhard, Antwort auf Frage 1: "vier enge Wochen zaehlen auch, ab fuenf
    # nicht mehr. Das ersetzt meine Antwort O19 mit den drei Wochen." Laenger
    # eng ist keine Pause nach einem Ausbruch, sondern ein festgenagelter Kurs;
    # gemessen am 21.09.2026 an 800 Aktien: SLAB 24 Wochen eng nach einem
    # Sprung, der typische Verlauf einer laufenden Uebernahme.
    # A: Der Anstieg muss IN die enge Phase fuehren: Der Schluss der Woche davor
    # liegt hoechstens 10 Prozent unter dem hoechsten Wochenschluss der zwoelf
    # Wochen davor. Gemessen am 21.09.2026: AAOI kam sonst mit drei engen
    # Wochen durch, die auf eine Woche mit minus 15 Prozent folgten, also eine
    # Pause nach einem Absturz und kein Halten nach einem Ausbruch.
    "a_nahe_hoch": 0.10,
    # D: "in oder knapp ueber einer Basis": Die 20 Handelstage vor dem
    # Pivot-Tag bewegen sich hoechstens 20 Prozent (Hoch zum Tief), und der
    # Pivot-Tag schliesst hoechstens 5 Prozent ueber ihrem Hoch. Ohne einen
    # einzigen Abwaertstag im Fenster gibt es keinen Vergleich und keinen Pivot.
    "d_basis_tage": 20,
    "d_basis_tiefe_max": 0.20,
    "d_basis_ueber_max": 0.05,
    # F: "nach dem letzten Tief mindestens ein Tag mit Schluss ueber Eroeffnung":
    # nach dem tiefsten Tief der zehn Tage, deren Tiefs ueber dem EMA 21 liegen.
    "f_tief_fenster": 10,
    # G: "davor ein Anstieg von mindestens zwanzig Prozent": gemessen vom
    # tiefsten Wochentief der 26 Wochen vor der Basis bis zu ihrem Hoch.
    "g_anstieg_wochen": 26,
    # L: "eine frisch notierte Aktie". Gerhard nennt keine Grenze, wie lange
    # eine Aktie frisch ist; IBD betrachtet IPO-Basen im ersten Jahr nach der
    # Erstnotiz. Unsere Festlegung: hoechstens 52 Wochen seit der Erstnotiz.
    "l_erstnotiz_wochen_max": 52,
    # L, BOERSENMANTEL (Gerhard, 22.09.2026, Antwort auf O14: "Ja", der erste
    # Handelstag nach der Uebernahme des Mantels gilt als Erstnotiz, "wenn der
    # Mantel so erkennbar ist; sonst steht an der Aktie, dass die Erstnotiz
    # unsicher ist"). Erkennbar heisst bei uns: Die Kurshistorie beginnt mit
    # mindestens 20 Handelstagen im Band 9 bis 11 Dollar, deren Spanne
    # hoechstens 5 Prozent betraegt, und danach verlaesst der Kurs das Band um
    # mindestens 20 Prozent. Dann gilt der erste Tag danach als Erstnotiz.
    # Sieht der Anfang nach Mantel aus, ohne diese Bedingungen zu erfuellen
    # (mindestens 5 Tage im Band), bleibt der erste Kurstag die Erstnotiz und
    # die Aktie traegt den Vermerk, dass sie unsicher ist.
    "l_mantel_von": 9.0,
    "l_mantel_bis": 11.0,
    "l_mantel_tage": 20,
    "l_mantel_tage_min": 5,
    "l_mantel_enge": 0.05,
    "l_mantel_sprung": 0.20,
    # S: Gerhards Startwerte, ausdruecklich unsere Festlegung: Docht mindestens
    # doppelt so lang wie der Koerper, Koerper hoechstens 30 Prozent der Spanne.
    # Gezaehlt wird der laengere Docht, oben oder unten ("eine Seite wurde
    # zurueckgeschlagen"). Markante Stelle: EMA 10, EMA 21, SMA 50 oder SMA 200,
    # das Hoch oder Tief der 20 Handelstage davor (Basisrand) oder das hoechste
    # Hoch des Jahres davor ohne den letzten Monat (altes Hoch), und zwar IM
    # DOCHT: Dort wurde die Seite zurueckgeschlagen. Gemessen am 21.09.2026 an
    # 800 Aktien: Genuegte es, dass die Stelle irgendwo in der Kerze liegt,
    # schlugen 40 Prozent aller Aktien an, weil eine schnelle Linie fast immer
    # in der Tagesspanne liegt. Gesucht wird bis drei Handelstage zurueck,
    # solange seither kein Schluss ueber dem Hoch der Kerze lag. Aufschlag wie
    # bei A und G.
    # Dazu "langer Docht" auch absolut: Die Tagesspanne der Kerze ist
    # mindestens so gross wie die durchschnittliche Tagesspanne (ATR) der 14
    # Handelstage davor; sonst genuegte ein winziger Koerper, um jeden
    # unauffaelligen Tag zum Wick Play zu machen. Gemessen am 21.09.2026 an
    # 800 Aktien: ohne diese Bedingung 29,6 Prozent Treffer, mit ihr 11,2.
    "s_docht_zu_koerper": 2.0,
    "s_koerper_max": 0.30,
    "s_spanne_atr": 1.0,
    "s_atr_tage": 14,
    "s_tage_zurueck": 3,
    "s_basis_tage": 20,
    "s_alt_von": 21,
    "s_alt_bis": 252,
    # T: Unterschreitung des EMA 10 hoechstens 3 Prozent (Gerhards Vorschlag,
    # ausdruecklich unsere Festlegung).
    "t_unterschreitung_max": 0.03,
    # HOCHS UND TIEFS (Pivots, fuer H und N): Ein Hoch ist das hoechste Hoch,
    # ein Tief das tiefste Tief von fuenf Kerzen, zwei davor und zwei danach;
    # bei gleichen Werten zaehlt die erste Kerze. Ein Tief gilt also erst, wenn
    # zwei Kerzen danach hoeher lagen. Bei N sind es Tageskerzen.
    "pivot_kerzen": 2,
    # N: "aus einem Hoch heraus": das hoechste Hoch der 63 Handelstage (drei
    # Monate) bis zu ihm. "scharfer Abverkauf": mindestens 10 Prozent vom Hoch
    # zum Tief in hoechstens 15 Handelstagen. Es zaehlt nur der ERSTE scharfe
    # Abverkauf nach dem Hoch (siehe shakeout_plus3). Gezeigt wird, solange das
    # Tief hoechstens 20 Handelstage zurueckliegt, seither nicht unterschritten
    # wurde und der Kurs den Einstieg bei 10 Prozent noch nicht erreicht hat.
    "n_hoch_tage": 63,
    "n_abverkauf_min": 0.10,
    "n_abverkauf_tage": 15,
    "n_tief_tage_max": 20,
    # Q: "Volumen deutlich ueber Schnitt": Der Schnitt je Handelstag im
    # Ausbruchsmonat betraegt mindestens das 1,4-Fache des Schnitts der 50
    # Handelstage vor diesem Monat. Die 50 Tage sind das Fenster des ganzen
    # Systems (IBD), die 1,4 das untere Ende von IBDs "40 bis 50 Prozent ueber
    # dem Durchschnitt", wie beim strengeren Ausbruchsvolumen der VCP.
    "q_vol_tage": 50,
    "q_vol_faktor": 1.4,
    # V: "flach oder fallend" heisst: Der Schluss vor der Luecke liegt
    # hoechstens 5 Prozent ueber dem Schluss zwei Monate davor.
    "v_tot_anstieg_max": 0.05,
    # V: gezeigt wird die juengste Luecke der letzten zehn Handelstage, der
    # Lueckentag eingeschlossen.
    "v_tage_max": 10,
    # V: der Eroeffnungsbereich ist das Hoch der ersten fuenf Minuten.
    "v_eroeffnung_minuten": 5,
}

SPALTEN = (
    "cm_b", "cm_b_steigend", "cm_b_vol_schrumpft", "cm_b_eng_kp", "cm_b_eng_stop", "cm_b_kons_kp",
    "cm_b_kons_stop",
    "cm_a", "cm_a_wochen", "cm_a_bis", "cm_a_anstieg_pct", "cm_a_kp", "cm_a_stop",
    "cm_d", "cm_d_vol_faktor", "cm_d_kp", "cm_d_stop",
    "cm_f", "cm_f_seit", "cm_f_tage",
    "cm_g", "cm_g_wochen", "cm_g_tiefe_pct", "cm_g_anstieg_pct", "cm_g_kp", "cm_g_stop",
    "cm_s", "cm_s_tag", "cm_s_seite", "cm_s_stelle", "cm_s_kp", "cm_s_stop",
    "cm_t", "cm_t_variante", "cm_t_unterschreitung_pct",
    "cm_n", "cm_n_tief_tag", "cm_n_abverkauf_pct", "cm_n_tage", "cm_n_kp5", "cm_n_kp10", "cm_n_kp5_erreicht",
    "cm_n_stop",
    "cm_l", "cm_l_wochen", "cm_l_tiefe_pct", "cm_l_seit_wochen", "cm_l_erstnotiz", "cm_l_mantel",
    "cm_l_unsicher", "cm_l_kp", "cm_l_stop",
    "cm_k", "cm_k_gewinn_pct", "cm_k_wochen", "cm_k_kp", "cm_k_stop",
    "cm_q", "cm_q_monat", "cm_q_linie", "cm_q_linie_tag", "cm_q_tage_ohne_hoch", "cm_q_vol_faktor",
    "cm_q_ausbruch_tag", "cm_q_kp", "cm_q_stop",
    "cm_m", "cm_m_stufe", "cm_m_status", "cm_m_wochen", "cm_m_tiefe_pct", "cm_m_seit", "cm_m_hoch",
    "cm_m_ausbruch", "cm_m_bob", "cm_m_gewinn_pct", "cm_m_neu_grund", "cm_m_neu_tag",
    "cm_v", "cm_vl", "cm_v_tag", "cm_v_ausloeser", "cm_v_luecke_pct", "cm_v_vol_faktor", "cm_v_abstand_pct",
    "cm_v_tot_pct", "cm_v_tief", "cm_v_kante", "cm_v_kp", "cm_v_stop",
)

MERKER = ("cm_b", "cm_a", "cm_d", "cm_g", "cm_s", "cm_t", "cm_n", "cm_l", "cm_k", "cm_q", "cm_m", "cm_v", "cm_vl")


def leer():
    """Alle Spalten ohne Fund: Merker 0, alles andere leer. Power Trend (cm_f)
    bleibt leer, bis genug Kurse da sind; 0 hiesse dort 'aus'."""
    raus = {s: None for s in SPALTEN}
    for s in MERKER:
        raus[s] = 0
    return raus


def _r(x, stellen=4):
    return None if x is None or not np.isfinite(x) else round(float(x), stellen)


def _deckel(kp, stop):
    """Der Zehn-Prozent-Deckel des ganzen Systems (exit_regeln.deckel_anwenden),
    hier wie bei jedem Musterfund: Gerhard, D: "Unser Zehn-Prozent-Deckel auf
    das Risiko gilt hier wie ueberall." """
    import exit_regeln
    punkt, _ = exit_regeln.deckel_anwenden({"kaufpunkt": float(kp), "stop": float(stop)})
    return punkt["stop"]


def vorbereiten(d):
    """Tageskerzen chronologisch, mit EMA 10, EMA 21, SMA 50 und SMA 200."""
    x = d[["datetime", "open", "high", "low", "close", "volume"]].copy()
    x["datetime"] = pd.to_datetime(x["datetime"])
    for s in ("open", "high", "low", "close", "volume"):
        x[s] = pd.to_numeric(x[s], errors="coerce").astype(float)
    x = x.dropna(subset=["open", "high", "low", "close"]).sort_values("datetime").reset_index(drop=True)
    c = x["close"]
    x["ema10"] = c.ewm(span=10, adjust=False).mean()
    x["ema21"] = c.ewm(span=21, adjust=False).mean()
    x["sma50"] = c.rolling(50).mean()
    x["sma200"] = c.rolling(200).mean()
    return x


def wochen(x):
    """Abgeschlossene Wochenkerzen: open, high, low, close, volume und der
    letzte Handelstag je Woche (Spalte bis)."""
    if x is None or len(x) == 0:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "bis"])
    w = x.set_index("datetime")
    w = w.assign(bis=w.index)
    wk = w.groupby(pd.Grouper(freq="W-FRI")).agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
        volume=("volume", "sum"), bis=("bis", "last")).dropna(subset=["close"]).reset_index(drop=True)
    if len(wk) and pd.Timestamp(wk["bis"].iloc[-1]).weekday() != 4:
        wk = wk.iloc[:-1]
    return wk.reset_index(drop=True)


# ---------------------------------------------------------------------------
# B  Inside Day, auch mit drei steigenden Tagen davor
# ---------------------------------------------------------------------------

def inside_day(x):
    """High[t] <= High[t-1] UND Low[t] >= Low[t-1]; Variante mit
    Close[t-3] < Close[t-2] < Close[t-1]. Bestaetigung, keine Pflicht:
    Volume[t] < Volume[t-1]. Beide Einstiege: eng ueber High[t] mit Stop unter
    Low[t], konservativ ueber High[t-1] mit Stop unter Low[t-1]."""
    if len(x) < 4:
        return {}
    h, lo, c, v = (x[s].to_numpy() for s in ("high", "low", "close", "volume"))
    t = len(x) - 1
    if not (h[t] <= h[t - 1] and lo[t] >= lo[t - 1]):
        return {}
    return {"cm_b": 1, "cm_b_steigend": bool(c[t - 3] < c[t - 2] < c[t - 1]),
            "cm_b_vol_schrumpft": bool(np.isfinite(v[t]) and np.isfinite(v[t - 1]) and v[t] < v[t - 1]),
            "cm_b_eng_kp": _r(h[t]), "cm_b_eng_stop": _r(_deckel(h[t], lo[t])),
            "cm_b_kons_kp": _r(h[t - 1]), "cm_b_kons_stop": _r(_deckel(h[t - 1], lo[t - 1]))}


# ---------------------------------------------------------------------------
# A  Three Weeks Tight
# ---------------------------------------------------------------------------

def three_weeks_tight(wk):
    """Fuer w in {t-2, t-1, t}: |Close_W(w) / Close_W(w-1) - 1| <= 0,015; vier
    enge Wochen zaehlen genauso, ab fuenf nicht mehr (Gerhard, 23.09.2026).
    Vorbedingung (unsere Festlegung):
    mindestens 20 Prozent Anstieg in den zwoelf Wochen vor der engen Phase.
    Kaufpunkt hoechstes Wochenhoch der engen Wochen plus 0,10 Dollar, Stop ihr
    tiefstes Wochentief. Der Anstieg muss in die enge Phase fuehren (unsere
    Festlegung, siehe FESTLEGUNGEN)."""
    n = len(wk)
    vorlauf = FESTLEGUNGEN["a_anstieg_wochen"]
    if n < QUELLE["a_wochen_min"] + vorlauf:
        return {}
    c, h, lo = (wk[s].to_numpy() for s in ("close", "high", "low"))
    eng = 0
    for i in range(n - 1, 0, -1):
        if abs(c[i] / c[i - 1] - 1.0) <= QUELLE["a_eng"]:
            eng += 1
        else:
            break
    if eng < QUELLE["a_wochen_min"] or eng > QUELLE["a_wochen_max"]:
        return {}
    bezug = n - 1 - eng                      # die Woche vor der engen Phase
    if bezug - vorlauf + 1 < 0:
        return {}
    tief_davor = float(np.nanmin(lo[bezug - vorlauf + 1:bezug + 1]))
    anstieg = c[bezug] / tief_davor - 1.0 if tief_davor > 0 else None
    if anstieg is None or anstieg < FESTLEGUNGEN["a_anstieg_min"]:
        return {}
    hoch_davor = float(np.nanmax(c[bezug - vorlauf + 1:bezug + 1]))
    if c[bezug] < hoch_davor * (1.0 - FESTLEGUNGEN["a_nahe_hoch"]):
        return {}
    kp = float(np.nanmax(h[n - eng:])) + QUELLE["aufschlag"]
    stop = float(np.nanmin(lo[n - eng:]))
    return {"cm_a": 1, "cm_a_wochen": int(eng), "cm_a_bis": pd.Timestamp(wk["bis"].iloc[-1]).strftime("%Y-%m-%d"),
            "cm_a_anstieg_pct": _r(anstieg * 100.0, 1), "cm_a_kp": _r(kp), "cm_a_stop": _r(_deckel(kp, stop))}


# ---------------------------------------------------------------------------
# D  Pocket Pivot
# ---------------------------------------------------------------------------

def pocket_pivot(x):
    """Close[t] > Close[t-1] UND Volume[t] groesser als das groesste Volumen
    eines Abwaertstags der zehn Handelstage davor; Zusatzbedingung der Autoren:
    ueber der SMA 50 und in oder knapp ueber einer Basis (unsere Festlegung,
    siehe FESTLEGUNGEN). Einstieg ueber dem Hoch des Pivot-Tages, Stop unter
    seinem Tief."""
    fenster, basis = QUELLE["d_fenster"], FESTLEGUNGEN["d_basis_tage"]
    if len(x) < max(fenster + 1, basis) + 1 or not np.isfinite(x["sma50"].iloc[-1]):
        return {}
    h, lo, c, v = (x[s].to_numpy() for s in ("high", "low", "close", "volume"))
    t = len(x) - 1
    if not (c[t] > c[t - 1] and c[t] > x["sma50"].iloc[-1]) or not np.isfinite(v[t]):
        return {}
    ab = [v[i] for i in range(t - fenster, t) if c[i] < c[i - 1] and np.isfinite(v[i])]
    if not ab or not v[t] > max(ab):
        return {}
    hoch, tief = float(np.nanmax(h[t - basis:t])), float(np.nanmin(lo[t - basis:t]))
    if hoch <= 0 or (hoch - tief) / hoch > FESTLEGUNGEN["d_basis_tiefe_max"]:
        return {}
    if c[t] > hoch * (1.0 + FESTLEGUNGEN["d_basis_ueber_max"]):
        return {}
    faktor = v[t] / max(ab) if max(ab) > 0 else None
    return {"cm_d": 1, "cm_d_vol_faktor": _r(faktor, 2), "cm_d_kp": _r(h[t]), "cm_d_stop": _r(_deckel(h[t], lo[t]))}


# ---------------------------------------------------------------------------
# F  Power Trend
# ---------------------------------------------------------------------------

def power_trend(x):
    """Ein, wenn alle vier gelten: seit mindestens zehn Handelstagen jedes Tief
    ueber dem EMA 21; EMA 21 ueber SMA 50; SMA 50 steigt seit mindestens
    zwanzig Tagen; nach dem letzten Tief ein Tag mit Schluss ueber Eroeffnung.
    Aus, sobald der EMA 21 unter die SMA 50 faellt oder der Schluss unter der
    SMA 50 liegt. Zurueck: {cm_f: 1 und seit wann, oder 0}; zu wenig Kurse
    lassen cm_f leer."""
    n_ema, n_steig = QUELLE["f_tage_ueber_ema"], QUELLE["f_sma50_steigt"]
    if len(x) < 50 + n_steig + n_ema:
        return {}
    o, lo, c = (x[s].to_numpy() for s in ("open", "low", "close"))
    ema21, sma50 = x["ema21"].to_numpy(), x["sma50"].to_numpy()
    tage = x["datetime"]
    fenster = FESTLEGUNGEN["f_tief_fenster"]
    an, seit = False, None
    for i in range(50 + n_steig, len(x)):
        if an:
            if ema21[i] < sma50[i] or c[i] < sma50[i]:
                an, seit = False, None
            continue
        if not all(lo[j] > ema21[j] for j in range(i - n_ema + 1, i + 1)):
            continue
        if not ema21[i] > sma50[i]:
            continue
        if not all(sma50[j] > sma50[j - 1] for j in range(i - n_steig + 1, i + 1)):
            continue
        k = i - fenster + 1 + int(np.argmin(lo[i - fenster + 1:i + 1]))
        if not any(c[j] > o[j] for j in range(k + 1, i + 1)):
            continue
        an, seit = True, i
    if not an:
        return {"cm_f": 0}
    return {"cm_f": 1, "cm_f_seit": pd.Timestamp(tage.iloc[seit]).strftime("%Y-%m-%d"),
            "cm_f_tage": int(len(x) - seit)}


# ---------------------------------------------------------------------------
# G  Flat Base
# ---------------------------------------------------------------------------

def flat_base(wk):
    """Eine Basis aus abgeschlossenen Wochen, die mit ihrem hoechsten Hoch
    beginnt (dem linken Hoch) und bis zur letzten Woche reicht: mindestens
    fuenf Wochen, Tiefe (max High_W - min Low_W) / max High_W <= 0,15, davor
    mindestens 20 Prozent Anstieg (Zeitraum unsere Festlegung: 26 Wochen).
    Gesucht wird die laengste solche Basis. Dass sie am linken Hoch beginnt,
    haelt den Schluss des vorangegangenen Anstiegs aus ihr heraus; sonst
    zaehlte jede Woche des Anstiegs, die noch keine 15 Prozent unter dem Hoch
    liegt, zur Basis. Kaufpunkt Basishoch plus 0,10 Dollar, Stop Basistief,
    gedeckelt."""
    n = len(wk)
    k_min, vorlauf = QUELLE["g_wochen_min"], FESTLEGUNGEN["g_anstieg_wochen"]
    if n < k_min + 1:
        return {}
    h, lo = wk["high"].to_numpy(), wk["low"].to_numpy()
    start = None
    for j in range(n - k_min, -1, -1):
        hoch = h[j]
        if not hoch > 0 or hoch < float(np.nanmax(h[j:])):
            continue                     # die Basis beginnt an ihrem Hoch
        if (hoch - float(np.nanmin(lo[j:]))) / hoch > QUELLE["g_tiefe_max"]:
            break                        # frueher beginnende Basen waeren noch tiefer
        start = j
    if start is None or start < 4:
        return {}
    hoch, tief = float(h[start]), float(np.nanmin(lo[start:]))
    tief_davor = float(np.nanmin(lo[max(0, start - vorlauf):start]))
    anstieg = hoch / tief_davor - 1.0 if tief_davor > 0 else None
    if anstieg is None or anstieg < QUELLE["g_anstieg_min"]:
        return {}
    kp = hoch + QUELLE["aufschlag"]
    return {"cm_g": 1, "cm_g_wochen": int(n - start), "cm_g_tiefe_pct": _r((hoch - tief) / hoch * 100.0, 1),
            "cm_g_anstieg_pct": _r(anstieg * 100.0, 1), "cm_g_kp": _r(kp), "cm_g_stop": _r(_deckel(kp, tief))}


# ---------------------------------------------------------------------------
# S  Wick Play
# ---------------------------------------------------------------------------

LINIEN = (("EMA 10", "ema10"), ("EMA 21", "ema21"), ("SMA 50", "sma50"), ("SMA 200", "sma200"))


def wick_play(x):
    """Eine Kerze mit langem Docht und kleinem Koerper an einer markanten Stelle
    (alle Schwellen und die markanten Stellen sind unsere Festlegung). Einstieg
    ueber dem Hoch der Kerze plus 0,10 Dollar, Stop unter ihrem Tief."""
    f = FESTLEGUNGEN
    if len(x) < f["s_basis_tage"] + f["s_tage_zurueck"] + 1:
        return {}
    o, h, lo, c = (x[s].to_numpy() for s in ("open", "high", "low", "close"))
    t = len(x) - 1
    vor = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.vstack([h - lo, np.abs(h - vor), np.abs(lo - vor)]), axis=0)
    for j in range(t, t - f["s_tage_zurueck"], -1):
        if j - max(f["s_basis_tage"], f["s_atr_tage"]) < 0:
            break
        spanne = h[j] - lo[j]
        if not spanne > 0:
            continue
        atr = float(np.nanmean(tr[j - f["s_atr_tage"]:j]))
        if not (np.isfinite(atr) and spanne >= f["s_spanne_atr"] * atr):
            continue
        koerper = abs(c[j] - o[j])
        oben, unten = h[j] - max(o[j], c[j]), min(o[j], c[j]) - lo[j]
        docht = max(oben, unten)
        if not (docht >= f["s_docht_zu_koerper"] * koerper and koerper <= f["s_koerper_max"] * spanne and docht > 0):
            continue
        if j < t and np.nanmax(c[j + 1:]) > h[j]:
            continue                     # schon ueber dem Hoch geschlossen: vorbei
        # Der Bereich des Dochts: unten vom Tief bis zum Koerper, oben vom
        # Koerper bis zum Hoch.
        von, bis = (lo[j], min(o[j], c[j])) if unten >= oben else (max(o[j], c[j]), h[j])

        def im_docht(wert):
            return wert is not None and np.isfinite(wert) and von <= wert <= bis

        stellen = [name for name, spalte in LINIEN if im_docht(float(x[spalte].iloc[j]))]
        rand_hoch = float(np.nanmax(h[j - f["s_basis_tage"]:j]))
        rand_tief = float(np.nanmin(lo[j - f["s_basis_tage"]:j]))
        if im_docht(rand_hoch) or im_docht(rand_tief):
            stellen.append("Basisrand")
        if j - f["s_alt_von"] > 0:
            alt = float(np.nanmax(h[max(0, j - f["s_alt_bis"]):j - f["s_alt_von"] + 1]))
            if im_docht(alt):
                stellen.append("altes Hoch")
        if not stellen:
            continue
        kp = h[j] + QUELLE["aufschlag"]
        return {"cm_s": 1, "cm_s_tag": pd.Timestamp(x["datetime"].iloc[j]).strftime("%Y-%m-%d"),
                "cm_s_seite": "unten" if unten >= oben else "oben", "cm_s_stelle": ", ".join(stellen),
                "cm_s_kp": _r(kp), "cm_s_stop": _r(_deckel(kp, lo[j]))}
    return {}


# ---------------------------------------------------------------------------
# T  Shakeout am gleitenden Durchschnitt
# ---------------------------------------------------------------------------

def shakeout_ema(x):
    """Im Aufwaertstrend (Close > SMA 50 > SMA 200) kurz unter den EMA 10 und
    wieder darueber: am selben Tag (Low[t] < EMA10[t] UND Close[t] > EMA10[t])
    oder ueber zwei Tage (Low[t-1] < EMA10[t-1], Close[t-1] < EMA10[t-1],
    Close[t] > EMA10[t-1]). Unterschreitung hoechstens 3 Prozent (unsere
    Festlegung)."""
    if len(x) < 201:
        return {}
    lo, c = x["low"].to_numpy(), x["close"].to_numpy()
    e, s50, s200 = x["ema10"].to_numpy(), x["sma50"].to_numpy(), x["sma200"].to_numpy()
    t = len(x) - 1
    if not (np.isfinite(s50[t]) and np.isfinite(s200[t]) and c[t] > s50[t] > s200[t]):
        return {}
    grenze = FESTLEGUNGEN["t_unterschreitung_max"]
    if lo[t] < e[t] < c[t]:
        u = (e[t] - lo[t]) / e[t]
        if u <= grenze:
            return {"cm_t": 1, "cm_t_variante": 1, "cm_t_unterschreitung_pct": _r(u * 100.0, 2)}
    if lo[t - 1] < e[t - 1] and c[t - 1] < e[t - 1] and c[t] > e[t - 1]:
        u = (e[t - 1] - lo[t - 1]) / e[t - 1]
        if u <= grenze:
            return {"cm_t": 1, "cm_t_variante": 2, "cm_t_unterschreitung_pct": _r(u * 100.0, 2)}
    return {}


# ---------------------------------------------------------------------------
# Hochs und Tiefs (Pivots), die Grundlage von H und N
# ---------------------------------------------------------------------------

def pivots(hoch, tief, ab=0):
    """Hochs und Tiefs (unsere Festlegung, siehe FESTLEGUNGEN): Stellen i,
    deren Hoch das hoechste bzw. deren Tief das tiefste der Kerzen i minus k
    bis i plus k ist (k = pivot_kerzen); bei gleichen Werten zaehlt die erste.
    Gesucht wird ab der Stelle ab. Zurueck: (Stellen der Hochs, der Tiefs)."""
    k = FESTLEGUNGEN["pivot_kerzen"]
    hoch, tief = np.asarray(hoch, dtype=float), np.asarray(tief, dtype=float)
    hochs, tiefs = [], []
    for i in range(max(k, int(ab)), len(hoch) - k):
        if np.isfinite(hoch[i]) and int(np.nanargmax(hoch[i - k:i + k + 1])) == k:
            hochs.append(i)
        if np.isfinite(tief[i]) and int(np.nanargmin(tief[i - k:i + k + 1])) == k:
            tiefs.append(i)
    return hochs, tiefs


# ---------------------------------------------------------------------------
# N  Shakeout plus drei
# ---------------------------------------------------------------------------

def shakeout_plus3(x):
    """Nach dem ersten scharfen Abverkauf aus einem Hoch heraus wird ueber dem
    Tief dieses Abverkaufs eingestiegen, mit Aufschlag: Tief mal 1,05 und mal
    1,10 nebeneinander, Stop unter dem Tief (Gerhard nach O'Neil). Das Tief
    ist ein Tief der Pivot-Erkennung auf Tageskerzen; was ein Hoch und was
    scharf ist, und wie lange der Einstieg gilt, ist unsere Festlegung (siehe
    FESTLEGUNGEN)."""
    f = FESTLEGUNGEN
    k, n = f["pivot_kerzen"], len(x)
    if n < f["n_hoch_tage"] + f["n_abverkauf_tage"] + 2 * k + 1:
        return {}
    h, lo = x["high"].to_numpy(dtype=float), x["low"].to_numpy(dtype=float)
    p5, p10 = QUELLE["n_aufschlag"]
    _, tiefs = pivots(h, lo, ab=n - 1 - f["n_tief_tage_max"] - f["n_abverkauf_tage"])
    for iT in reversed(tiefs):
        if n - 1 - iT > f["n_tief_tage_max"]:
            break
        if lo[iT] > np.nanmin(lo[iT:]):
            continue                              # seither unterschritten
        von = max(0, iT - f["n_abverkauf_tage"])
        iH = von + int(np.nanargmax(h[von:iT]))
        if h[iH] < np.nanmax(h[max(0, iH - f["n_hoch_tage"] + 1):iH + 1]):
            continue                              # kein Hoch der drei Monate bis dahin
        if lo[iT] > np.nanmin(lo[iH:iT + 1]):
            continue                              # das Tief des Abverkaufs liegt frueher
        abverkauf = 1.0 - lo[iT] / h[iH]
        if abverkauf < f["n_abverkauf_min"]:
            continue
        # "nach dem ERSTEN scharfen Abverkauf": Lag zwischen Hoch und Tief schon
        # ein Tief, das selbst scharf war und ueber das der Kurs danach um 10
        # Prozent stieg, war das der erste Abverkauf samt Einstieg, und das
        # jetzige Tief ist ein zweiter. Gemessen am 21.09.2026 an FTH: 17 Prozent
        # hinunter, 16 Prozent hinauf, dann ein neues Tief.
        if any(1.0 - lo[j] / h[iH] >= f["n_abverkauf_min"] and np.nanmax(h[j + 1:iT]) >= lo[j] * (1.0 + p10)
               for j in tiefs if iH < j < iT - 1):
            continue
        kp5, kp10 = lo[iT] * (1.0 + p5), lo[iT] * (1.0 + p10)
        seit = h[iT + 1:]
        if len(seit) and np.nanmax(seit) >= kp10:
            return {}                             # der Einstieg bei 10 Prozent war schon erreicht
        return {"cm_n": 1, "cm_n_tief_tag": pd.Timestamp(x["datetime"].iloc[iT]).strftime("%Y-%m-%d"),
                "cm_n_abverkauf_pct": _r(abverkauf * 100.0, 1), "cm_n_tage": int(iT - iH),
                "cm_n_kp5": _r(kp5), "cm_n_kp10": _r(kp10),
                "cm_n_kp5_erreicht": bool(len(seit) and np.nanmax(seit) >= kp5),
                "cm_n_stop": _r(_deckel(kp10, lo[iT]))}
    return {}


# ---------------------------------------------------------------------------
# L  IPO Base (Gerhard, 20.09.2026; Erstnotiz-Regel aus seiner Antwort O14)
# ---------------------------------------------------------------------------

def erstnotiz(x):
    """Der erste Handelstag der Aktie nach Gerhards Regel (O14), als
    (Stelle in den Tageskerzen, Mantel erkannt, Erstnotiz unsicher).

    Kam eine Firma ueber einen Boersenmantel an die Boerse, beginnt ihre
    Kurshistorie mit dem Mantel, der meist flach um 10 Dollar notiert. Ist er
    erkennbar (siehe FESTLEGUNGEN), gilt der erste Handelstag nach der
    Uebernahme als Erstnotiz; sieht der Anfang nur nach Mantel aus, bleibt der
    erste Kurstag die Erstnotiz und die Aktie traegt den Vermerk unsicher."""
    f = FESTLEGUNGEN
    c = x["close"].to_numpy(dtype=float)
    n = len(c)
    im_band = 0
    while im_band < n and f["l_mantel_von"] <= c[im_band] <= f["l_mantel_bis"]:
        im_band += 1
    if im_band < f["l_mantel_tage_min"] or im_band >= n:
        return 0, False, False
    band = c[:im_band]
    hoch, tief = float(np.nanmax(band)), float(np.nanmin(band))
    mitte = float(np.nanmean(band))
    eng = hoch > 0 and (hoch - tief) / hoch <= f["l_mantel_enge"]
    sprung = mitte > 0 and abs(c[im_band] / mitte - 1.0) >= f["l_mantel_sprung"]
    if im_band >= f["l_mantel_tage"] and eng and sprung:
        return im_band, True, False
    return 0, False, True


def ipo_base(x, wk):
    """Die erste Basis einer frisch notierten Aktie: Sie darf frueher und
    tiefer sein als bei einer etablierten (Gerhard: drei bis vier Wochen statt
    fuenf bis sieben, Tiefe zwanzig bis fuenfzig Prozent). Sie beginnt an
    ihrem hoechsten Wochenhoch, dem linken Hoch, und reicht bis zur letzten
    abgeschlossenen Woche; gesucht wird die laengste solche Basis. Kaufpunkt
    linkes Hoch plus 0,10 Dollar, Stop das Basistief, gedeckelt. Wie lange
    eine Aktie als frisch gilt, ist unsere Festlegung."""
    q, f = QUELLE, FESTLEGUNGEN
    n = len(wk)
    if n < q["l_wochen_min"] or x is None or len(x) == 0:
        return {}
    i0, mantel, unsicher = erstnotiz(x)
    tag0 = pd.Timestamp(x["datetime"].iloc[i0])
    bis = pd.to_datetime(wk["bis"])
    nach = [j for j in range(n) if bis.iloc[j] >= tag0]
    if not nach:
        return {}
    start_frueh = nach[0]
    seit = n - start_frueh                    # abgeschlossene Wochen seit der Erstnotiz
    if seit > f["l_erstnotiz_wochen_max"]:
        return {}
    h, lo = wk["high"].to_numpy(dtype=float), wk["low"].to_numpy(dtype=float)
    start = None
    for j in range(n - q["l_wochen_min"], start_frueh - 1, -1):
        hoch = h[j]
        if not hoch > 0 or hoch < float(np.nanmax(h[j:])):
            continue                          # die Basis beginnt an ihrem Hoch
        if (hoch - float(np.nanmin(lo[j:]))) / hoch > q["l_tiefe_max"]:
            break                             # frueher beginnende Basen waeren noch tiefer
        start = j
    if start is None:
        return {}
    hoch, tief = float(h[start]), float(np.nanmin(lo[start:]))
    tiefe = (hoch - tief) / hoch
    if not q["l_tiefe_min"] <= tiefe <= q["l_tiefe_max"]:
        return {}
    kp = hoch + q["aufschlag"]
    return {"cm_l": 1, "cm_l_wochen": int(n - start), "cm_l_tiefe_pct": _r(tiefe * 100.0, 1),
            "cm_l_seit_wochen": int(seit), "cm_l_erstnotiz": tag0.strftime("%Y-%m-%d"),
            "cm_l_mantel": bool(mantel), "cm_l_unsicher": bool(unsicher),
            "cm_l_kp": _r(kp), "cm_l_stop": _r(_deckel(kp, tief))}


# ---------------------------------------------------------------------------
# M  Stufenzaehlung der Basen, K Base-on-Base (Gerhard, 23.09.2026)
# ---------------------------------------------------------------------------

def _tagzahl(tage):
    """Kalendertage seit dem 01.01.1970 je Eintrag, als ganze Zahlen; ein Tag
    mit Zeitzone zaehlt nach seiner Ortszeit."""
    idx = pd.to_datetime(pd.Index(list(tage) if isinstance(tage, (set, frozenset)) else tage))
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    return idx.to_numpy().astype("datetime64[D]").astype(np.int64)


def _tag_iso(tagzahl):
    return str(np.datetime64(int(tagzahl), "D"))


def stufenzaehlung(x, markttiefs=None, verlauf=None):
    """M und K ueber die ganze Kurshistorie x (vorbereitete Tageskerzen).

    Gerhards Regeln (20.09.2026) mit seinen Zahlen vom 23.09.2026: Gezaehlt
    wird nur fuer Aktien ueber zehn Dollar. Eine BASIS dauert mindestens fuenf
    Wochen und ist hoechstens 35 Prozent tief, vom linken Hoch zum tiefsten
    Tief; ausgebrochen ist sie mit einem Tagesschluss ueber dem linken Hoch.
    Stufe eins ist die erste Basis nach einem Markttief oder nach einer
    eigenen Korrektur. Jede weitere Basis zaehlt eine Stufe hoeher, wenn die
    Aktie aus der vorigen ausgebrochen ist und dabei mindestens zwanzig
    Prozent gewonnen hat (vom Ausbruch der vorigen Basis bis zum linken Hoch
    der neuen); darunter ist es Base-on-Base (K), beide Basen zaehlen als eine
    Stufe. ZURUECK AUF NULL, und damit ist die naechste Basis wieder Stufe
    eins, geht die Zaehlung (1) an einem Markttief, (2) sobald der Kurs das
    Tief der letzten Basis unterschreitet, (3) sobald er zwanzig Prozent unter
    dem letzten Hoch liegt. Gerhards bewusste Folge aus (3): Jede Basis, die
    tiefer als zwanzig Prozent korrigiert, ist Stufe eins.

    DAS LINKE HOCH einer Basis ist das hoechste Hoch seit dem letzten
    Ausbruch: Jedes neue Hoch, bevor fuenf Wochen vergangen sind, laesst die
    Basis dort neu beginnen. Die Wochen sind Kalenderwochen von Montag bis
    Freitag, die Woche des linken Hochs zaehlt mit (wie bei der Flat Base).
    Faellt der Kurs mehr als 35 Prozent unter das linke Hoch, ist es keine
    Basis mehr; dann beginnt die naechste Basis erst am hoechsten Hoch nach
    dem tiefsten Tief dieses Rueckgangs, so dass eine blosse Erholung auf das
    alte Niveau nie als Basis zaehlt. Ebenso am Anfang der Kurshistorie.

    markttiefs: die Tage der Markttiefs (marktbreite.markttiefs, S&P 500 und
    Nasdaq nach den Regeln der Marktampel); ein Markttief setzt an seinem Tag
    zurueck. verlauf: eine Liste, in die jeder Ausbruch und jede
    Ruecksetzung kommt (zum Nachpruefen an echten Kursen).

    Zurueck: die Spalten cm_m und cm_k; ohne Basis seit der letzten
    Ruecksetzung nichts. Gezeigt wird die Basis, die sich gerade bildet,
    sobald sie fuenf Wochen alt ist; sonst die letzte, aus der die Aktie
    ausgebrochen ist."""
    q = QUELLE
    # Tage mit Null oder weniger (alte Yahoo-Daten) zaehlen nicht; sie wuerden
    # jede Tiefe unendlich machen.
    x = x[(x["high"] > 0) & (x["low"] > 0) & (x["close"] > 0)]
    n = len(x)
    if n < 2:
        return {}
    c_roh = x["close"].to_numpy(dtype=float)
    if not c_roh[-1] > q["m_kurs_min"]:
        return {}
    h = x["high"].to_numpy(dtype=float).tolist()
    lo = x["low"].to_numpy(dtype=float).tolist()
    c = c_roh.tolist()
    tz = _tagzahl(x["datetime"])
    woche = ((tz + 3) // 7).tolist()          # Kalenderwoche ab Montag
    tzl = tz.tolist()
    tiefs = sorted({int(z) for z in _tagzahl(markttiefs)}) if markttiefs else []
    ti = bisect.bisect_right(tiefs, tzl[0])
    w_min, t_max, korr, k_min = q["m_wochen_min"], q["m_tiefe_max"], q["m_korrektur"], q["k_gewinn_min"]
    stufe, letzte = 0, None
    neu = ("beginn", tzl[0])                  # warum und seit wann gezaehlt wird
    a, tief = 0, lo[0]                         # linkes Hoch der laufenden Basis, ihr tiefstes Tief
    gescheitert, boden, korr_an = True, lo[0], False
    for t in range(1, n):
        ht, lt, ct = h[t], lo[t], c[t]
        while ti < len(tiefs) and tiefs[ti] <= tzl[t]:
            if verlauf is not None and stufe:
                verlauf.append(("markttief", _tag_iso(tiefs[ti])))
            stufe, letzte, neu = 0, None, ("markttief", tiefs[ti])
            ti += 1
        if letzte is not None and lt < letzte["tief"]:
            stufe, letzte, neu = 0, None, ("basistief", tzl[t])
            if verlauf is not None:
                verlauf.append(("basistief", _tag_iso(tzl[t])))
        reif = woche[t] - woche[a] >= w_min
        if reif and ct > h[a]:
            ha = h[a]
            tiefe = 1.0 - tief / ha
            if tiefe <= t_max:
                gewinn = None if letzte is None else ha / letzte["pivot"] - 1.0
                bob = False
                if letzte is None:
                    stufe = 1
                elif gewinn >= k_min:
                    stufe += 1
                else:
                    bob = True
                letzte = {"pivot": ha, "tief": tief, "stufe": stufe, "bob": bob, "gewinn": gewinn,
                          "links": tzl[a], "ausbruch": tzl[t], "wochen": woche[t] - woche[a], "tiefe": tiefe}
                if verlauf is not None:
                    verlauf.append(("ausbruch", _tag_iso(tzl[t]), stufe, bob, round(ha, 2),
                                    round(tiefe * 100.0, 1), woche[t] - woche[a]))
                a, tief, gescheitert, korr_an = t, lt, False, False
                continue
        if ht > h[a] and not reif:
            a, tief, korr_an = t, lt, False
            continue
        if gescheitert and lt < boden:
            a, tief, boden, korr_an = t, lt, lt, False
            continue
        if lt < tief:
            tief = lt
        tiefe = 1.0 - tief / h[a]
        if tiefe >= korr and not korr_an:
            korr_an = True
            if verlauf is not None and stufe:
                verlauf.append(("korrektur", _tag_iso(tzl[t])))
            stufe, letzte, neu = 0, None, ("korrektur", tzl[t])
        if tiefe > t_max:
            gescheitert, a, tief, boden, korr_an = True, t, lt, lt, False

    t = n - 1
    freitag = (tzl[t] + 3) % 7 == 4
    basis_wochen = woche[t] - woche[a] + (1 if freitag else 0)
    zaehlung = {"cm_m_neu_grund": neu[0], "cm_m_neu_tag": _tag_iso(neu[1])}
    if basis_wochen >= w_min:
        ha = h[a]
        gewinn = None if letzte is None else ha / letzte["pivot"] - 1.0
        if letzte is None:
            s_b, bob = 1, False
        elif gewinn >= k_min:
            s_b, bob = letzte["stufe"] + 1, False
        else:
            s_b, bob = letzte["stufe"], True
        raus = {"cm_m": 1, "cm_m_stufe": int(s_b), "cm_m_status": "bildung", "cm_m_wochen": int(basis_wochen),
                "cm_m_tiefe_pct": _r((1.0 - tief / ha) * 100.0, 1), "cm_m_seit": _tag_iso(tzl[a]),
                "cm_m_hoch": _r(ha), "cm_m_ausbruch": None, "cm_m_bob": bool(bob),
                "cm_m_gewinn_pct": None if gewinn is None else _r(gewinn * 100.0, 1), **zaehlung}
        if bob:
            kp = ha + q["aufschlag"]
            raus.update({"cm_k": 1, "cm_k_gewinn_pct": _r(gewinn * 100.0, 1), "cm_k_wochen": int(basis_wochen),
                         "cm_k_kp": _r(kp), "cm_k_stop": _r(_deckel(kp, tief))})
        return raus
    if letzte is not None:
        return {"cm_m": 1, "cm_m_stufe": int(letzte["stufe"]), "cm_m_status": "ausbruch",
                "cm_m_wochen": int(letzte["wochen"]), "cm_m_tiefe_pct": _r(letzte["tiefe"] * 100.0, 1),
                "cm_m_seit": _tag_iso(letzte["links"]), "cm_m_hoch": _r(letzte["pivot"]),
                "cm_m_ausbruch": _tag_iso(letzte["ausbruch"]), "cm_m_bob": bool(letzte["bob"]),
                "cm_m_gewinn_pct": None if letzte["gewinn"] is None else _r(letzte["gewinn"] * 100.0, 1),
                **zaehlung}
    return {}


# ---------------------------------------------------------------------------
# Q  Green Line Breakout (Gerhard, 20.09.2026, Stop seit 23.09.2026)
# ---------------------------------------------------------------------------

def green_line(x):
    """Die gruene Linie ist das Allzeithoch; seit ihm mindestens 63
    Handelstage ohne neues Hoch. Signal: Der Schluss eines ABGESCHLOSSENEN
    Monats liegt ueber der Linie (O15: erst nach bestaetigtem Monatsschluss,
    keine Zwischenstufe), bei deutlich hoeherem Volumen (unsere Festlegung,
    siehe FESTLEGUNGEN). Gezeigt wird im Monat nach dem Ausbruchsmonat.
    Einstieg ueber der Linie; Stop am letzten Tief der Pivot-Erkennung vor
    dem Ausbruchstag, dem ersten Schluss ueber der Linie (Gerhard, 23.09.2026,
    Frage 5), mit dem Zehn-Prozent-Deckel.

    Ein Monat ist abgeschlossen, wenn der naechste Werktag in den naechsten
    Monat faellt; faellt der letzte Werktag eines Monats auf einen Feiertag,
    zaehlt der Monat ab dem ersten Kurstag des Folgemonats."""
    q, f = QUELLE, FESTLEGUNGEN
    n = len(x)
    if n < q["q_tage_ohne_hoch"] + 2:
        return {}
    tage = pd.to_datetime(x["datetime"]).reset_index(drop=True)
    monat = (tage.dt.year * 12 + tage.dt.month - 1).to_numpy()
    letzter = tage.iloc[-1]
    fertig = (letzter + pd.offsets.BDay(1)).month != letzter.month
    m_sig = monat[-1] if fertig else monat[-1] - 1
    idx = np.nonzero(monat == m_sig)[0]
    if len(idx) == 0 or idx[0] == 0:
        return {}
    i0, i1 = int(idx[0]), int(idx[-1])
    h, lo = x["high"].to_numpy(dtype=float), x["low"].to_numpy(dtype=float)
    c, v = x["close"].to_numpy(dtype=float), x["volume"].to_numpy(dtype=float)
    vor = h[:i0]
    if not np.isfinite(vor).any():
        return {}
    linie = float(np.nanmax(vor))
    j = int(i0 - 1 - int(np.nanargmax(vor[::-1])))          # der letzte Tag mit dem Allzeithoch
    if not c[i1] > linie:
        return {}
    k = i0 + int(np.nonzero(h[i0:i1 + 1] > linie)[0][0])    # der erste Tag mit neuem Hoch
    ohne = k - j - 1
    if ohne < q["q_tage_ohne_hoch"]:
        return {}
    fenster = f["q_vol_tage"]
    if i0 < fenster:
        return {}
    vol_monat, vol_davor = float(np.nanmean(v[i0:i1 + 1])), float(np.nanmean(v[i0 - fenster:i0]))
    if not (vol_davor > 0 and np.isfinite(vol_monat)):
        return {}
    faktor = vol_monat / vol_davor
    if faktor < f["q_vol_faktor"]:
        return {}
    b = i0 + int(np.nonzero(c[i0:i1 + 1] > linie)[0][0])    # Ausbruchstag: erster Schluss ueber der Linie
    kk = f["pivot_kerzen"]
    stop_roh = None
    for i in range(b - kk - 1, kk - 1, -1):
        if np.isfinite(lo[i]) and int(np.nanargmin(lo[i - kk:i + kk + 1])) == kk:
            stop_roh = float(lo[i])
            break
    if stop_roh is None:
        return {}
    y, m = divmod(int(m_sig), 12)
    return {"cm_q": 1, "cm_q_monat": f"{y:04d}-{m + 1:02d}", "cm_q_linie": _r(linie),
            "cm_q_linie_tag": pd.Timestamp(tage.iloc[j]).strftime("%Y-%m-%d"), "cm_q_tage_ohne_hoch": int(ohne),
            "cm_q_vol_faktor": _r(faktor, 2), "cm_q_ausbruch_tag": pd.Timestamp(tage.iloc[b]).strftime("%Y-%m-%d"),
            "cm_q_kp": _r(linie), "cm_q_stop": _r(_deckel(linie, stop_roh))}


# ---------------------------------------------------------------------------
# V  Episodic Pivot (Gerhard, 20.09.2026, Zahlen vom 23.09.2026)
# ---------------------------------------------------------------------------

def episodic_pivot(x, termine):
    """Eine grosse Eroeffnungsluecke nach einer toten Phase: Open[t] durch
    Close[t-1] minus 1 ueber zehn Prozent; davor mindestens zwei Monate flach
    oder fallend (was flach heisst, ist unsere Festlegung) und mindestens 15
    Prozent unter dem Zweihundert-Tage-Hoch; Volumen mindestens das Dreifache
    des Fuenfzig-Tage-Schnitts (in der Nacht ist F(t) eins). Gesucht wird die
    juengste solche Luecke der letzten zehn Handelstage (unsere Festlegung).

    termine: die Tage, an denen die Firma Zahlen gebracht hat (Nasdaq-Kalender
    der vergangenen Tage). Zahlen am Lueckentag oder am Handelstag davor sind
    der Ausloeser; der Kalender nennt fuer vergangene Tage keine Uhrzeit,
    deshalb zaehlen vor Eroeffnung und nach Schluss gleich. Ohne erkannten
    Ausloeser steht die Luecke GETRENNT da (O16: "Luecke ohne erkannten
    Ausloeser"): cm_vl statt cm_v.

    Einstieg und Stop kommen spaeter dazu (episodic_einstieg), weil der
    Eroeffnungsbereich Fuenf-Minuten-Kurse braucht; hier stehen das Tief des
    Lueckentags und die Lueckenunterkante (der Schluss davor)."""
    q, f = QUELLE, FESTLEGUNGEN
    n = len(x)
    bedarf = max(q["v_hoch_tage"], q["v_tote_tage"] + 1, q["v_vol_tage"]) + 1
    if n < bedarf + 1:
        return {}
    o, h, lo = x["open"].to_numpy(dtype=float), x["high"].to_numpy(dtype=float), x["low"].to_numpy(dtype=float)
    c, v = x["close"].to_numpy(dtype=float), x["volume"].to_numpy(dtype=float)
    tage = pd.to_datetime(x["datetime"]).reset_index(drop=True)
    for t in range(n - 1, max(n - 1 - f["v_tage_max"], bedarf - 1), -1):
        c1 = c[t - 1]
        if not (c1 > 0 and o[t] / c1 - 1.0 > q["v_luecke"]):
            continue
        schnitt = float(np.nanmean(v[t - q["v_vol_tage"]:t]))
        if not (schnitt > 0 and np.isfinite(v[t]) and v[t] >= q["v_vol_faktor"] * schnitt):
            continue
        hoch200 = float(np.nanmax(h[t - q["v_hoch_tage"]:t]))
        if not c1 <= hoch200 * (1.0 - q["v_abstand_200"]):
            continue
        vorher = c[t - 1 - q["v_tote_tage"]]
        if not (vorher > 0 and c1 <= vorher * (1.0 + f["v_tot_anstieg_max"])):
            continue
        tag = tage.iloc[t].strftime("%Y-%m-%d")
        vortag = tage.iloc[t - 1].strftime("%Y-%m-%d")
        zahlen = bool(termine) and (tag in termine or vortag in termine)
        return {"cm_v" if zahlen else "cm_vl": 1, "cm_v_tag": tag,
                "cm_v_ausloeser": "zahlen" if zahlen else None,
                "cm_v_luecke_pct": _r((o[t] / c1 - 1.0) * 100.0, 1), "cm_v_vol_faktor": _r(v[t] / schnitt, 1),
                "cm_v_abstand_pct": _r((1.0 - c1 / hoch200) * 100.0, 1),
                "cm_v_tot_pct": _r((c1 / vorher - 1.0) * 100.0, 1),
                "cm_v_tief": _r(lo[t]), "cm_v_kante": _r(c1)}
    return {}


def episodic_einstieg(eroeffnung, tief, kante):
    """Einstieg ueber dem Eroeffnungsbereich des Lueckentags (dem Hoch seiner
    ersten fuenf Minuten, unsere Festlegung). Stop nach Gerhard unter dem
    Tagestief oder unter der Lueckenunterkante, "je nachdem, was den
    Zehn-Prozent-Deckel einhaelt": erst das Tagestief; liegt es mehr als zehn
    Prozent unter dem Einstieg, die Lueckenunterkante, wenn sie den Deckel
    einhaelt (das ist sie nur, wenn die Luecke am Tag teilweise geschlossen
    wurde); sonst greift der Deckel. Rueckgabe (Einstieg, Stop) oder
    (None, None) ohne Eroeffnungsbereich."""
    if eroeffnung is None or not np.isfinite(eroeffnung) or eroeffnung <= 0:
        return None, None
    grenze = eroeffnung * 0.90
    if tief is not None and tief >= grenze:
        return _r(eroeffnung), _r(tief)
    if kante is not None and grenze <= kante < eroeffnung:
        return _r(eroeffnung), _r(kante)
    return _r(eroeffnung), _r(_deckel(eroeffnung, tief if tief is not None else grenze))


def werte(d, voll=None, markttiefs=None, termine=None):
    """Alle Muster fuer eine Aktie am letzten Handelstag der Kurse d (Spalten
    datetime, open, high, low, close, volume). Jedes Muster rechnet fuer sich;
    scheitert eines, bleiben nur seine Spalten leer.

    voll: die GANZE Kurshistorie derselben Aktie. Nur mit ihr rechnen Q (das
    Allzeithoch) und M samt K (die Zaehlung ueber Jahre); das tut allein die
    Nachttabelle. M und K brauchen dazu die Markttiefs der Nacht: Ohne sie
    waere die Zaehlung zu hoch, deshalb bleibt sie dann leer (None heisst
    nicht geholt, eine leere Liste heisst keine).

    termine: die Tage, an denen die Firma zuletzt Zahlen gebracht hat (die
    Nachttabelle holt sie aus dem Nasdaq-Kalender der vergangenen Tage). Nur
    mit ihnen rechnet V, der Episodic Pivot; None heisst nicht geholt."""
    raus = leer()
    if d is None or len(d) < 4:
        return raus
    x = vorbereiten(d)
    wk = wochen(x)
    for fn, args in ((inside_day, (x,)), (three_weeks_tight, (wk,)), (pocket_pivot, (x,)), (power_trend, (x,)),
                     (flat_base, (wk,)), (shakeout_plus3, (x,)), (wick_play, (x,)), (shakeout_ema, (x,)),
                     (ipo_base, (x, wk))):
        try:
            raus.update(fn(*args))
        except Exception:  # noqa: BLE001, ein Muster darf die anderen nie mitreissen
            pass
    if termine is not None:
        try:
            raus.update(episodic_pivot(x, termine))
        except Exception:  # noqa: BLE001
            pass
    if voll is None or len(voll) < 4:
        return raus
    try:
        xv = vorbereiten(voll)
    except Exception:  # noqa: BLE001
        return raus
    lange = [(green_line, (xv,))]
    if markttiefs is not None:
        lange.append((stufenzaehlung, (xv, markttiefs)))
    for fn, args in lange:
        try:
            raus.update(fn(*args))
        except Exception:  # noqa: BLE001
            pass
    return raus


# ---------------------------------------------------------------------------
# Selbsttest (ohne Netz, mit gebauten Kursreihen)
# ---------------------------------------------------------------------------

def _reihe(schluesse, start="2024-01-01", spanne=0.01, volumen=1_000_000.0, oeffnung=None):
    """Tageskerzen an Werktagen aus einer Liste von Schlusskursen."""
    tage = pd.bdate_range(start, periods=len(schluesse))
    c = np.asarray(schluesse, dtype=float)
    o = np.asarray(oeffnung, dtype=float) if oeffnung is not None else np.r_[c[0], c[:-1]]
    return pd.DataFrame({"datetime": tage, "open": o, "high": np.maximum(o, c) * (1 + spanne),
                         "low": np.minimum(o, c) * (1 - spanne), "close": c,
                         "volume": np.full(len(c), volumen)})


def selbsttest() -> int:
    fehler = []

    def p(name, bedingung, zusatz=""):
        print(f"  {'ok  ' if bedingung else 'FEHL'} {name}" + (f"; {zusatz}" if zusatz else ""))
        if not bedingung:
            fehler.append(name)

    # B Inside Day
    d = _reihe([10, 10.2, 10.5, 10.8, 10.9])
    d.loc[4, ["open", "high", "low", "close", "volume"]] = [10.85, 10.95, 10.75, 10.9, 500_000.0]
    d.loc[3, ["high", "low"]] = [11.0, 10.6]
    b = inside_day(vorbereiten(d))
    p("B: Inside Day nach steigenden Tagen, Volumen schrumpft, beide Einstiege",
      b.get("cm_b") == 1 and b["cm_b_steigend"] and b["cm_b_vol_schrumpft"] and b["cm_b_eng_kp"] == 10.95
      and b["cm_b_eng_stop"] == 10.75 and b["cm_b_kons_kp"] == 11.0 and b["cm_b_kons_stop"] == 10.6, str(b))
    d.loc[4, "high"] = 11.05
    p("B: Hoch ueber dem Vortag ist kein Inside Day", inside_day(vorbereiten(d)) == {})
    d = _reihe([10, 10.5, 10.2, 10.8, 10.9])
    d.loc[4, ["open", "high", "low", "close"]] = [10.85, 10.95, 10.75, 10.9]
    d.loc[3, ["high", "low"]] = [11.0, 10.6]
    b = inside_day(vorbereiten(d))
    p("B: ohne steigende Tage nur der schlichte Inside Day", b.get("cm_b") == 1 and not b["cm_b_steigend"])

    # A Three Weeks Tight: 12 Wochen Anstieg um 40 Prozent, dann drei enge Wochen
    schluesse = list(np.linspace(20, 28, 60)) + [28.1, 28.2, 28.15, 28.25, 28.3,
                                                 28.2, 28.3, 28.25, 28.35, 28.4,
                                                 28.3, 28.35, 28.45, 28.4, 28.45]
    x = vorbereiten(_reihe(schluesse, start="2026-06-01", spanne=0.005))
    wk = wochen(x)
    a = three_weeks_tight(wk)
    p("A: drei enge Wochen nach 40 Prozent Anstieg", a.get("cm_a") == 1 and a["cm_a_wochen"] >= 3
      and a["cm_a_kp"] == round(float(wk["high"].iloc[-a["cm_a_wochen"]:].max()) + 0.10, 4), str(a))
    p("A: Wochen enden am Freitag, die angebrochene zaehlt nicht",
      all(pd.Timestamp(b_).weekday() == 4 for b_ in wochen(vorbereiten(_reihe(schluesse[:-2], start="2026-06-01")))["bis"]))
    x2 = vorbereiten(_reihe([28] * 60 + schluesse[60:], start="2026-06-01", spanne=0.005))
    p("A: ohne Anstieg davor kein Three Weeks Tight", three_weeks_tight(wochen(x2)) == {})
    lang = schluesse[:60] + [28.1, 28.2, 28.15, 28.25, 28.3] * 6 + schluesse[70:]
    p("A: sieben enge Wochen sind festgenagelt, kein Three Weeks Tight",
      three_weeks_tight(wochen(vorbereiten(_reihe(lang, start="2026-06-01", spanne=0.005)))) == {})
    vier = schluesse[:60] + [28.1, 28.2, 28.15, 28.25, 28.3] * 4
    a4 = three_weeks_tight(wochen(vorbereiten(_reihe(vier, start="2026-06-01", spanne=0.005))))
    p("A: vier enge Wochen zaehlen (Gerhard, 23.09.2026, ersetzt O19)",
      a4.get("cm_a") == 1 and a4["cm_a_wochen"] == 4, str(a4))
    fuenf = schluesse[:60] + [28.1, 28.2, 28.15, 28.25, 28.3] * 5
    p("A: ab fuenf engen Wochen kein Three Weeks Tight mehr (Gerhard, 23.09.2026)",
      three_weeks_tight(wochen(vorbereiten(_reihe(fuenf, start="2026-06-01", spanne=0.005)))) == {})
    unruhig = schluesse[:60] + [28.1, 29.5, 28.0, 29.6, 28.2, 29.9, 28.1, 30.0, 28.3, 30.2, 28.4, 30.3, 28.5, 30.5, 28.6]
    absturz = list(np.linspace(15, 28, 55)) + [26.0, 25.0, 24.2, 24.0, 23.8] + [23.9, 23.95, 23.9, 24.0, 23.95] * 3
    x_ab = vorbereiten(_reihe(absturz, start="2026-06-01", spanne=0.005))
    alt_nahe = FESTLEGUNGEN["a_nahe_hoch"]
    FESTLEGUNGEN["a_nahe_hoch"] = 1.0             # Gegenprobe: ohne die Regel waere es ein Treffer
    ohne_regel = three_weeks_tight(wochen(x_ab)).get("cm_a") == 1
    FESTLEGUNGEN["a_nahe_hoch"] = alt_nahe
    p("A: Gegenprobe, ohne die Naehe zum Hoch haette der Absturz-Fall getroffen", ohne_regel)
    p("A: enge Wochen nach einem Absturz sind kein Three Weeks Tight (unsere Festlegung)",
      three_weeks_tight(wochen(vorbereiten(_reihe(absturz, start="2026-06-01", spanne=0.005)))) == {})
    p("A: weite Wochenschluesse sind nicht eng",
      three_weeks_tight(wochen(vorbereiten(_reihe(unruhig, start="2026-06-01")))) == {})

    # D Pocket Pivot: Seitwaertsphase ueber der SMA 50, Aufwaertstag mit mehr
    # Volumen als jeder Abwaertstag der zehn Tage davor
    basis = list(np.linspace(40, 50, 60)) + [50, 49.6, 50.2, 49.8, 50.4, 49.9, 50.3, 49.7, 50.1, 49.9,
                                              50.2, 49.8, 50.3, 49.9, 50.2, 49.8, 50.1, 49.9, 50.2, 49.8, 50.6]
    d = _reihe(basis, spanne=0.004, volumen=1_000_000.0)
    d.loc[len(d) - 1, "volume"] = 1_800_000.0
    d.loc[len(d) - 2, "volume"] = 1_500_000.0      # der Abwaertstag davor, mit viel Volumen
    dd = pocket_pivot(vorbereiten(d))
    p("D: Pocket Pivot, Faktor zum staerksten Abwaertstag", dd.get("cm_d") == 1 and dd["cm_d_vol_faktor"] == 1.2, str(dd))
    d.loc[len(d) - 1, "volume"] = 1_400_000.0
    p("D: weniger Volumen als der staerkste Abwaertstag ist keiner", pocket_pivot(vorbereiten(d)) == {})
    d.loc[len(d) - 1, ["volume", "close", "high"]] = [1_800_000.0, 56.0, 56.3]
    p("D: weit ueber der Basis zaehlt nicht (unsere Festlegung)", pocket_pivot(vorbereiten(d)) == {})

    # F Power Trend
    steigend = list(np.linspace(30, 60, 160))
    f = power_trend(vorbereiten(_reihe(steigend, spanne=0.002)))
    p("F: stetiger Anstieg schaltet den Power Trend ein", f.get("cm_f") == 1 and f["cm_f_tage"] >= 1, str(f))
    fallend = steigend + list(np.linspace(59, 40, 40))
    f = power_trend(vorbereiten(_reihe(fallend, spanne=0.002)))
    p("F: Schluss unter der SMA 50 schaltet ihn aus", f.get("cm_f") == 0, str(f))
    p("F: zu wenig Kurse lassen ihn leer", power_trend(vorbereiten(_reihe(steigend[:60]))) == {})

    # G Flat Base: 50 Prozent Anstieg, dann acht Wochen seitwaerts mit 10 Prozent Tiefe
    anstieg = list(np.linspace(20, 30, 130))
    seitwaerts = [30, 29, 28, 28.5, 29.5, 28.2, 27.5, 28.8, 29.6, 28.1] * 4
    x = vorbereiten(_reihe(anstieg + seitwaerts, start="2025-09-01", spanne=0.005))
    g = flat_base(wochen(x))
    p("G: Flat Base nach 50 Prozent Anstieg", g.get("cm_g") == 1 and g["cm_g_wochen"] >= 5
      and g["cm_g_tiefe_pct"] <= 15 and g["cm_g_anstieg_pct"] >= 20, str(g))
    x = vorbereiten(_reihe([30] * 130 + seitwaerts, start="2025-09-01", spanne=0.005))
    p("G: ohne Anstieg davor keine Flat Base", flat_base(wochen(x)) == {})
    tief = [30, 26, 24, 27, 29, 25, 23.5, 28, 29.5, 24] * 4
    x = vorbereiten(_reihe(anstieg + tief, start="2025-09-01", spanne=0.005))
    p("G: 25 Prozent tief ist keine Flat Base", flat_base(wochen(x)) == {})

    # S Wick Play: langer unterer Docht, der die SMA 50 beruehrt
    d = _reihe(list(np.linspace(30, 45, 80)) + [45.2, 45.1, 45.3], spanne=0.003)
    x = vorbereiten(d)
    t = len(x) - 1
    s50 = float(x["sma50"].iloc[t])
    x.loc[t, ["open", "close", "high"]] = [45.3, 45.4, 45.5]
    x.loc[t, "low"] = min(s50, 44.0) - 0.2
    s = wick_play(x)
    p("S: langer unterer Docht an der SMA 50", s.get("cm_s") == 1 and s["cm_s_seite"] == "unten"
      and "SMA 50" in s["cm_s_stelle"] and s["cm_s_kp"] == 45.6, str(s))
    for spalte in ("ema10", "ema21", "sma50", "sma200"):
        x.loc[t, spalte] = 45.35                # alle Linien im Koerper, keine im Docht
    s = wick_play(x)
    p("S: Linie nur im Koerper ist keine markante Stelle", "EMA" not in str(s.get("cm_s_stelle"))
      and "SMA" not in str(s.get("cm_s_stelle")), str(s))
    x.loc[t, ["open", "close", "high", "low", "sma50"]] = [45.30, 45.31, 45.36, 45.20, 45.25]
    s = wick_play(x)
    p("S: kleine Tagesspanne unter der ATR ist kein Wick Play (unsere Festlegung)",
      s.get("cm_s_tag") != x["datetime"].iloc[t].strftime("%Y-%m-%d"), str(s))
    x.loc[t, ["open", "close", "high", "low"]] = [41.0, 45.4, 45.5, 40.8]
    s = wick_play(x)
    p("S: grosser Koerper ist kein Wick Play", s.get("cm_s_tag") != x["datetime"].iloc[t].strftime("%Y-%m-%d"), str(s))

    # T Shakeout am EMA 10
    d = _reihe(list(np.linspace(20, 60, 260)), spanne=0.002)
    x = vorbereiten(d)
    t = len(x) - 1
    e = float(x["ema10"].iloc[t])
    x.loc[t, ["low", "close", "high"]] = [e * 0.99, e * 1.004, e * 1.01]
    tt = shakeout_ema(x)
    p("T: kurz unter den EMA 10 und darueber geschlossen", tt.get("cm_t") == 1 and tt["cm_t_variante"] == 1
      and tt["cm_t_unterschreitung_pct"] == 1.0, str(tt))
    x.loc[t, "low"] = e * 0.95
    p("T: 5 Prozent darunter ist ein Bruch (unsere Festlegung)", shakeout_ema(x) == {})
    e1 = float(x["ema10"].iloc[t - 1])
    x.loc[t - 1, ["low", "close"]] = [e1 * 0.985, e1 * 0.995]
    x.loc[t, ["low", "close", "high"]] = [e * 1.002, e * 1.01, e * 1.02]
    tt = shakeout_ema(x)
    p("T: Variante ueber zwei Tage", tt.get("cm_t") == 1 and tt["cm_t_variante"] == 2
      and tt["cm_t_unterschreitung_pct"] == 1.5, str(tt))
    x.loc[t, "close"] = e1 * 0.999
    p("T: Schluss unter dem EMA des Vortags ist noch kein Shakeout", shakeout_ema(x) == {})

    # Hochs und Tiefs: Spitze und Mulde mit je zwei Kerzen links und rechts,
    # gleiche Werte zaehlen an der ersten Stelle, der Rand zaehlt nicht
    ph, pt = pivots([1, 2, 5, 3, 2, 2, 4, 1, 0, 3, 3, 1], [1, 2, 5, 3, 2, 2, 4, 1, 0, 3, 3, 1])
    p("Pivots: Hochs bei 2, 6 und 9, Tiefs bei 4 und 8, gleiche Werte an der ersten Stelle",
      ph == [2, 6, 9] and pt == [4, 8], f"{ph} {pt}")
    p("Pivots: zu nah am Rand zaehlt nicht", pivots([3, 1, 2], [3, 1, 2]) == ([], []))

    # N Shakeout plus drei: 100 Tage Anstieg zum Hoch, dann in sechs Tagen 15
    # Prozent Abverkauf, drei Tage leichte Erholung
    def n_reihe(nach):
        return _reihe(list(np.linspace(50, 100, 100)) + list(np.linspace(97, 85, 5)) + nach, spanne=0.005)

    nn = shakeout_plus3(vorbereiten(n_reihe([86.0, 87.0, 88.0])))
    tief_roh = 85.0 * (1 - 0.005)
    p("N: Tief nach scharfem Abverkauf, Einstieg bei 5 und 10 Prozent, Stop am Tief",
      nn.get("cm_n") == 1 and nn["cm_n_kp5"] == round(tief_roh * 1.05, 4)
      and nn["cm_n_kp10"] == round(tief_roh * 1.10, 4) and nn["cm_n_stop"] == round(tief_roh, 4) and nn["cm_n_kp5_erreicht"] is False and nn["cm_n_tage"] == 5
      and 15.0 <= nn["cm_n_abverkauf_pct"] <= 16.0, str(nn))
    nn = shakeout_plus3(vorbereiten(n_reihe([86.0, 90.0, 88.0])))
    p("N: fuenf Prozent schon erreicht, zehn noch nicht", nn.get("cm_n") == 1 and nn["cm_n_kp5_erreicht"] is True, str(nn))
    p("N: der Einstieg bei zehn Prozent war schon erreicht, vorbei",
      shakeout_plus3(vorbereiten(n_reihe([86.0, 88.0, 94.0]))) == {})
    p("N: ein Tag nach dem Tief ist es noch nicht bestaetigt",
      shakeout_plus3(vorbereiten(n_reihe([86.0]))) == {})
    p("N: unter das Tief gefallen, keines bestaetigt",
      shakeout_plus3(vorbereiten(n_reihe([86.0, 87.0, 88.0, 84.0]))) == {})
    flach = _reihe(list(np.linspace(50, 100, 100)) + list(np.linspace(99, 94, 5)) + [95.0, 96.0, 96.5], spanne=0.005)
    p("N: sieben Prozent sind kein scharfer Abverkauf (unsere Festlegung)", shakeout_plus3(vorbereiten(flach)) == {})
    lang = _reihe(list(np.linspace(50, 100, 100)) + list(np.linspace(99.5, 85, 25)) + [86.0, 87.0, 88.0], spanne=0.005)
    p("N: 15 Prozent in 25 Tagen sind nicht scharf (unsere Festlegung)", shakeout_plus3(vorbereiten(lang)) == {})
    seit = _reihe([100.0] * 40 + list(np.linspace(100, 80, 60)) + list(np.linspace(79, 68, 5)) + [69.0, 70.0, 71.0],
                  spanne=0.005)
    p("N: im Abwaertstrend gibt es kein Hoch, keinen Shakeout plus drei (unsere Festlegung)",
      shakeout_plus3(vorbereiten(seit)) == {})
    auf = list(np.linspace(50, 100, 100))
    zweiter = _reihe(auf + list(np.linspace(97, 88, 3)) + list(np.linspace(91, 97, 3)) + list(np.linspace(94, 84, 3))
                     + [85.0, 86.0, 87.0], spanne=0.005)
    p("N: nach einem scharfen Tief samt 10 Prozent Erholung ist das neue Tief ein zweiter Abverkauf",
      shakeout_plus3(vorbereiten(zweiter)) == {})
    erster = _reihe(auf + list(np.linspace(97, 91.5, 3)) + list(np.linspace(94, 100, 3)) + list(np.linspace(94, 80, 4))
                    + [81.0, 82.0, 83.0], spanne=0.005)
    nn = shakeout_plus3(vorbereiten(erster))
    p("N: ein erstes Tief unter 10 Prozent war nicht scharf, das neue Tief ist der erste scharfe Abverkauf",
      nn.get("cm_n") == 1 and nn["cm_n_abverkauf_pct"] >= 20.0, str(nn))

    # L IPO Base: junge Aktie, sechs Wochen Anstieg, danach eine Basis, die an
    # ihrem Hoch beginnt und rund 25 Prozent tief ist
    def l_reihe(tief=0.75, basis_wochen=5, anstieg_tage=30, vorlauf=0, start="2026-05-04"):
        hoch = 40.0
        s = list(np.linspace(20, hoch, anstieg_tage))
        for _ in range(basis_wochen):
            s += [hoch * tief, hoch * (tief + 0.05), hoch * (tief + 0.10), hoch * (tief + 0.08), hoch * (tief + 0.12)]
        return [10.0] * vorlauf + s

    x_l = vorbereiten(_reihe(l_reihe(), start="2026-05-04", spanne=0.002))
    wk_l = wochen(x_l)
    ll = ipo_base(x_l, wk_l)
    kp_l = round(float(np.nanmax(wk_l["high"].to_numpy())) + 0.10, 4)
    p("L: junge Aktie mit Basis, Kaufpunkt am linken Hoch plus 0,10 Dollar",
      ll.get("cm_l") == 1 and ll["cm_l_kp"] == kp_l and ll["cm_l_wochen"] >= 3
      and 20.0 <= ll["cm_l_tiefe_pct"] <= 30.0 and ll["cm_l_mantel"] is False
      and ll["cm_l_unsicher"] is False, str(ll))
    p("L: der Stop traegt den Zehn-Prozent-Deckel", ll.get("cm_l_stop") is not None
      and 0.099 < (kp_l - ll["cm_l_stop"]) / kp_l <= 0.10, str(ll))
    p("L: eine Basis von zehn Prozent ist keine IPO Base (Gerhard: zwanzig bis fuenfzig Prozent)",
      ipo_base(*(lambda z: (z, wochen(z)))(vorbereiten(_reihe(l_reihe(tief=0.90), start="2026-05-04",
                                                              spanne=0.002)))) == {})
    tiefe_v = list(np.linspace(20, 40, 30)) + list(np.linspace(39, 16, 15)) + list(np.linspace(17, 38, 15))
    v_x = vorbereiten(_reihe(tiefe_v, start="2026-05-04", spanne=0.002))
    p("L: sechzig Prozent tief ist keine IPO Base (Gerhard: hoechstens fuenfzig)",
      ipo_base(v_x, wochen(v_x)) == {})
    alt = vorbereiten(_reihe(list(np.linspace(20, 40, 330)) + l_reihe(anstieg_tage=10)[10:],
                             start="2024-01-01", spanne=0.002))
    p("L: eine Aktie mit mehr als einem Jahr Kurshistorie ist nicht mehr frisch notiert (unsere Festlegung)",
      ipo_base(alt, wochen(alt)) == {})
    # Boersenmantel (O14): 25 Tage flach um 10 Dollar, dann die Uebernahme
    mantel_x = vorbereiten(_reihe([10.0, 10.1, 9.95, 10.05] * 6 + [10.0] + l_reihe(anstieg_tage=30),
                                  start="2025-09-01", spanne=0.002))
    i_m, m_erkannt, m_unsicher = erstnotiz(mantel_x)
    p("L: der Boersenmantel wird erkannt, die Erstnotiz ist der erste Tag danach (Gerhard, O14)",
      i_m == 25 and m_erkannt is True and m_unsicher is False, f"{i_m}, {m_erkannt}, {m_unsicher}")
    lm = ipo_base(mantel_x, wochen(mantel_x))
    p("L: mit der Mantel-Regel zaehlen nur die Wochen nach der Uebernahme",
      lm.get("cm_l") == 1 and lm["cm_l_mantel"] is True
      and lm["cm_l_erstnotiz"] == pd.Timestamp(mantel_x["datetime"].iloc[25]).strftime("%Y-%m-%d"), str(lm))
    kurz_x = vorbereiten(_reihe([10.0, 10.1, 9.95, 10.05, 10.0, 10.1] + l_reihe(anstieg_tage=30),
                                start="2026-04-01", spanne=0.002))
    i_k, k_erkannt, k_unsicher = erstnotiz(kurz_x)
    p("L: ein kurzer flacher Anfang ist kein sicherer Mantel, die Erstnotiz bleibt der erste Kurstag und gilt als unsicher",
      i_k == 0 and k_erkannt is False and k_unsicher is True, f"{i_k}, {k_erkannt}, {k_unsicher}")
    p("L: die unsichere Erstnotiz steht am Fund",
      ipo_base(kurz_x, wochen(kurz_x)).get("cm_l_unsicher") is True, str(ipo_base(kurz_x, wochen(kurz_x))))
    p("L: eine gewoehnliche Aktie ohne flachen Anfang hat keine Mantel-Vermutung",
      erstnotiz(x_l) == (0, False, False))

    # M Stufenzaehlung und K Base-on-Base (Gerhard, 23.09.2026). Die Reihen
    # beginnen an einem Montag; 60 Tage Anstieg auf 40 Dollar, dann Basen zu
    # je sechs Wochen (30 Handelstage).
    def m_x(*teile, start="2024-01-01", faktor=1.0):
        s = []
        for teil in teile:
            s += [v * faktor for v in teil]
        return vorbereiten(_reihe(s, start=start, spanne=0.005))

    anstieg = list(np.linspace(20, 40, 60))
    basis1 = [38, 37, 36.5, 37.5, 39] * 6
    lauf30 = list(np.linspace(41, 53, 20))
    basis2 = [50, 49, 48.5, 49.5, 51] * 6
    m2 = stufenzaehlung(m_x(anstieg, basis1, lauf30, basis2), [])
    p("M: zweite Basis nach mehr als 20 Prozent Gewinn ist Stufe 2, in Bildung",
      m2.get("cm_m") == 1 and m2["cm_m_stufe"] == 2 and m2["cm_m_status"] == "bildung" and m2["cm_m_wochen"] == 7
      and m2["cm_m_bob"] is False and m2["cm_m_gewinn_pct"] == 32.5 and "cm_k" not in m2
      and m2["cm_m_neu_grund"] == "beginn", str(m2))
    lauf3 = list(np.linspace(54, 66, 20))
    basis3 = [63, 62, 61.5, 62.5, 64] * 6
    m3 = stufenzaehlung(m_x(anstieg, basis1, lauf30, basis2, lauf3, basis3), [])
    p("M: dritte Basis ist Stufe 3", m3.get("cm_m_stufe") == 3 and m3["cm_m_status"] == "bildung", str(m3))
    m_aus = stufenzaehlung(m_x(anstieg, basis1, lauf30), [])
    x_aus = m_x(anstieg, basis1, lauf30)
    p("M: nach dem Ausbruch, solange keine neue Basis fuenf Wochen alt ist, steht die letzte",
      m_aus.get("cm_m_stufe") == 1 and m_aus["cm_m_status"] == "ausbruch"
      and m_aus["cm_m_ausbruch"] == x_aus["datetime"].iloc[90].strftime("%Y-%m-%d")
      and m_aus["cm_m_seit"] == x_aus["datetime"].iloc[59].strftime("%Y-%m-%d") and m_aus["cm_m_wochen"] == 7
      and m_aus["cm_m_hoch"] == round(40 * 1.005, 4), str(m_aus))
    klein = list(np.linspace(41, 44, 20))
    basis2k = [42, 41.5, 41, 41.8, 43] * 6
    mk = stufenzaehlung(m_x(anstieg, basis1, klein, basis2k), [])
    kp_k = round(44 * 1.005 + 0.10, 4)
    p("K: nur 10 Prozent Gewinn zwischen den Basen, Base-on-Base, beide sind Stufe 1",
      mk.get("cm_m_stufe") == 1 and mk["cm_m_bob"] is True and mk.get("cm_k") == 1 and mk["cm_k_gewinn_pct"] == 10.0
      and mk["cm_k_kp"] == kp_k and mk["cm_k_stop"] == round(41 * 0.995, 4) and mk["cm_k_wochen"] == 7, str(mk))
    tief2 = [48, 45, 42, 41, 43] * 6
    mkorr = stufenzaehlung(m_x(anstieg, basis1, lauf30, tief2), [])
    p("M: eine Basis mehr als 20 Prozent tief ist Stufe 1 (Gerhards bewusste Folge)",
      mkorr.get("cm_m_stufe") == 1 and mkorr["cm_m_status"] == "bildung" and mkorr["cm_m_neu_grund"] == "korrektur"
      and mkorr["cm_m_tiefe_pct"] > 20.0, str(mkorr))
    basis1f = [39.5, 39.2, 39.0, 39.4, 39.8] * 6
    bruch = [42, 40, 38.5, 38.4, 39.5] + [39.5, 40, 41, 40.5, 41.5] * 5
    mbruch = stufenzaehlung(m_x(anstieg, basis1f, klein, bruch), [])
    p("M: unter das Tief der letzten Basis gefallen, die Zaehlung beginnt neu",
      mbruch.get("cm_m_stufe") == 1 and mbruch["cm_m_neu_grund"] == "basistief" and mbruch["cm_m_bob"] is False
      and "cm_k" not in mbruch and mbruch["cm_m_tiefe_pct"] < 20.0, str(mbruch))
    x_mt = m_x(anstieg, basis1, lauf30, basis2)
    tag100 = x_mt["datetime"].iloc[100].strftime("%Y-%m-%d")
    mmt = stufenzaehlung(x_mt, ["2023-05-02", tag100])
    p("M: ein Markttief setzt an seinem Tag zurueck, ein Markttief vor der Kurshistorie zaehlt nicht",
      mmt.get("cm_m_stufe") == 1 and mmt["cm_m_neu_grund"] == "markttief" and mmt["cm_m_neu_tag"] == tag100, str(mmt))
    p("M: unter zehn Dollar wird nicht gezaehlt (Gerhard)",
      stufenzaehlung(m_x(anstieg, basis1, lauf30, basis2, faktor=0.15), []) == {})
    kurz = [38, 37, 36.5, 37.5, 39] * 3
    mkurz = stufenzaehlung(m_x(anstieg, kurz, lauf30, basis2), [])
    p("M: drei Wochen Pause sind keine Basis, die spaetere Basis ist Stufe 1",
      mkurz.get("cm_m_stufe") == 1 and mkurz["cm_m_status"] == "bildung", str(mkurz))
    absturz = list(np.linspace(39, 24, 30))
    erholung = list(np.linspace(25, 32, 20))
    basis_n = [31, 30, 29.5, 30.5, 31.5] * 6
    mabs = stufenzaehlung(m_x(anstieg, absturz, erholung, basis_n), [])
    p("M: mehr als 35 Prozent tief ist keine Basis, die neue Basis beginnt am Hoch der Erholung",
      mabs.get("cm_m_stufe") == 1 and mabs["cm_m_status"] == "bildung" and mabs["cm_m_neu_grund"] == "korrektur"
      and mabs["cm_m_hoch"] == round(32 * 1.005, 4), str(mabs))
    v_erholung = list(np.linspace(39, 25, 20)) + list(np.linspace(25.5, 42, 40))
    p("M: eine blosse Erholung auf das alte Niveau ist keine Basis",
      stufenzaehlung(m_x(anstieg, v_erholung), []) == {})
    x_null = m_x(anstieg, basis1, lauf30, basis2)
    x_null.loc[5, ["low", "high"]] = [0.0, 0.0]
    p("M: ein Kurstag mit Null in alten Daten bricht die Zaehlung nicht",
      stufenzaehlung(x_null, []).get("cm_m_stufe") == 2)

    # Q Green Line Breakout: Allzeithoch nach 100 Tagen, danach seitwaerts
    # darunter, Ausbruch im August 2026, der Kurs endet am 31.08.2026
    def q_x(seitwaerts, august, vol_august=2_000_000.0, ende="2026-08-31"):
        s = list(np.linspace(20, 50, 100)) + seitwaerts + august
        d = _reihe(s, spanne=0.005, volumen=1_000_000.0)
        d["datetime"] = pd.bdate_range(end=ende, periods=len(s))
        d.loc[len(s) - len(august):, "volume"] = vol_august
        return vorbereiten(d)

    seit_q = [44, 45, 46, 47, 48, 46, 45, 44, 45, 46] * 17 + [46, 45, 43.5, 44.8, 46.2, 46.8]
    aug = [47.2, 48, 49, 49.5, 51, 52, 52.5, 53] + [53] * 13
    qq = green_line(q_x(seit_q, aug))
    linie = round(50 * 1.005, 4)
    p("Q: Monatsschluss ueber dem Allzeithoch bei doppeltem Volumen, Stop am letzten Tief der Pivot-Erkennung, gedeckelt",
      qq.get("cm_q") == 1 and qq["cm_q_monat"] == "2026-08" and qq["cm_q_linie"] == linie and qq["cm_q_kp"] == linie
      and qq["cm_q_vol_faktor"] == 2.0 and qq["cm_q_tage_ohne_hoch"] >= 63
      and 0.099 < (linie - qq["cm_q_stop"]) / linie <= 0.10, str(qq))
    q_x_t = q_x(seit_q, aug)
    p("Q: Ausbruchstag ist der erste Schluss ueber der Linie, die Linie traegt ihren Tag",
      qq.get("cm_q_ausbruch_tag") == q_x_t["datetime"].iloc[100 + len(seit_q) + 4].strftime("%Y-%m-%d")
      and qq.get("cm_q_linie_tag") == q_x_t["datetime"].iloc[100].strftime("%Y-%m-%d"), str(qq))
    p("Q: zu wenig Volumen ist kein Green Line Breakout (unsere Festlegung)",
      green_line(q_x(seit_q, aug, vol_august=1_200_000.0)) == {})
    p("Q: ein Ausbruch im laufenden Monat zaehlt erst nach dem Monatsschluss (O15)",
      green_line(q_x(seit_q, aug[:14], ende="2026-08-20")) == {})
    p("Q: faellt der Monatsschluss unter die Linie zurueck, kein Signal",
      green_line(q_x(seit_q, aug[:10] + [49.0] * 11)) == {})
    frisch = seit_q[:-40] + list(np.linspace(46, 50.6, 10)) + [49, 48, 47.5, 47, 46.5] * 4
    frisch += [46, 45, 43.5, 44.8, 46.2, 46.8]
    p("Q: ein Hoch, das keine 63 Handelstage stand, ist keine gruene Linie",
      green_line(q_x(frisch, aug)) == {})

    # V Episodic Pivot: 100 Tage Anstieg auf 40, 60 Tage Abstieg auf 30, 60
    # Tage tot um 30, dann die Luecke mit vierfachem Volumen
    def v_x(tot=None, luecke=34.0, vol=4_000_000.0, danach=(35.0,), abstieg_bis=30.0):
        s = list(np.linspace(20, 40, 100)) + list(np.linspace(39.5, abstieg_bis, 60))
        s += tot if tot is not None else [30.2, 29.8, 30.1, 29.9, 30.0] * 12
        n_vor = len(s)
        s += list(danach)
        d = _reihe(s, start="2025-06-02", spanne=0.005, volumen=1_000_000.0)
        d.loc[n_vor, ["open", "high", "low", "volume"]] = [luecke, max(luecke, s[n_vor]) * 1.01,
                                                           min(luecke, s[n_vor]) * 0.99, vol]
        return vorbereiten(d), d["datetime"].iloc[n_vor].strftime("%Y-%m-%d"), \
            d["datetime"].iloc[n_vor - 1].strftime("%Y-%m-%d")

    xv, tag_v, vortag_v = v_x()
    ep = episodic_pivot(xv, {vortag_v})
    p("V: Luecke nach toter Phase mit Zahlen am Vortag ist ein Episodic Pivot",
      ep.get("cm_v") == 1 and "cm_vl" not in ep and ep["cm_v_tag"] == tag_v and ep["cm_v_ausloeser"] == "zahlen"
      and ep["cm_v_luecke_pct"] == round((34.0 / 30.0 - 1) * 100, 1) and ep["cm_v_vol_faktor"] == 4.0
      and ep["cm_v_kante"] == 30.0 and ep["cm_v_abstand_pct"] >= 15.0, str(ep))
    p("V: Zahlen am Lueckentag selbst zaehlen ebenso", episodic_pivot(xv, {tag_v}).get("cm_v") == 1)
    ohne = episodic_pivot(xv, set())
    p("V: ohne erkannten Ausloeser steht die Luecke getrennt da (O16)",
      ohne.get("cm_vl") == 1 and "cm_v" not in ohne and ohne["cm_v_ausloeser"] is None, str(ohne))
    p("V: zehn Tage spaeter noch gezeigt, danach nicht mehr (unsere Festlegung)",
      episodic_pivot(v_x(danach=[35.0] * 10)[0], set()).get("cm_vl") == 1
      and episodic_pivot(v_x(danach=[35.0] * 11)[0], set()) == {})
    p("V: doppeltes Volumen ist zu wenig (Gerhard: das Dreifache)",
      episodic_pivot(v_x(vol=2_000_000.0)[0], {vortag_v}) == {})
    p("V: acht Prozent Luecke sind zu wenig (Gerhard: ueber zehn)",
      episodic_pivot(v_x(luecke=32.4)[0], {vortag_v}) == {})
    p("V: nur acht Prozent unter dem 200-Tage-Hoch ist zu nah (Gerhard: mindestens 15)",
      episodic_pivot(v_x(abstieg_bis=37.0, tot=[37.2, 36.8, 37.1, 36.9, 37.0] * 12, luecke=41.5)[0], set()) == {})
    steigend = list(np.linspace(27, 33, 60))
    p("V: zwei Monate Anstieg vor der Luecke sind keine tote Phase (unsere Festlegung)",
      episodic_pivot(v_x(tot=steigend, luecke=37.0)[0], set()) == {})
    p("V: Einstieg ueber den ersten fuenf Minuten, Stop am Tagestief, wenn der Deckel haelt",
      episodic_einstieg(35.5, 33.0, 30.0) == (35.5, 33.0))
    p("V: Tagestief zu weit weg, die Lueckenunterkante haelt den Deckel",
      episodic_einstieg(35.5, 30.0, 32.0) == (35.5, 32.0))
    p("V: haelt keines den Deckel, greift der Deckel", episodic_einstieg(35.5, 30.0, 31.0) == (35.5, 31.95))
    p("V: ohne Eroeffnungsbereich kein Einstieg", episodic_einstieg(None, 30.0, 31.0) == (None, None))
    w_v = werte(xv.tail(300), termine={vortag_v})
    p("V: werte rechnet V nur mit den Zahlenterminen der Nacht",
      w_v["cm_v"] == 1 and werte(xv.tail(300))["cm_v"] == 0 and werte(xv.tail(300))["cm_vl"] == 0
      and set(w_v) == set(SPALTEN), str({k: w_v[k] for k in ("cm_v", "cm_vl", "cm_v_tag")}))

    # werte: die Stufenzaehlung und Q nur mit der ganzen Historie
    ganz = _reihe(anstieg + basis1 + lauf30 + basis2, start="2024-01-01", spanne=0.005)
    w_kurz = werte(ganz.tail(40))
    w_voll = werte(ganz.tail(40), voll=ganz, markttiefs=[])
    w_ohne_tiefs = werte(ganz.tail(40), voll=ganz)
    p("M: ohne ganze Kurshistorie keine Stufenzaehlung, mit ihr Stufe 2",
      w_kurz["cm_m"] == 0 and w_kurz["cm_q"] == 0 and w_voll["cm_m"] == 1 and w_voll["cm_m_stufe"] == 2
      and set(w_voll) == set(SPALTEN), str({k: w_voll[k] for k in ("cm_m", "cm_m_stufe")}))
    p("M: ohne Markttiefs der Nacht keine Stufenzaehlung (sie waere zu hoch)", w_ohne_tiefs["cm_m"] == 0)

    # Gesamt: werte liefert immer alle Spalten, auch bei Unsinn
    w = werte(_reihe(list(np.linspace(20, 60, 400)), spanne=0.004))
    p("Alle Spalten da, Merker ganze Zahlen", set(w) == set(SPALTEN)
      and all(isinstance(w[s], int) for s in MERKER))
    kaputt = _reihe([10, 11, 12, 13, 14])
    kaputt["close"] = ["x", None, 12, 13, 14]
    p("Unlesbare Kurse brechen nichts", set(werte(kaputt)) == set(SPALTEN))
    p("Leere Kurse", werte(None) == leer())
    p("Festlegungen und Quelle getrennt", not (set(QUELLE) & set(FESTLEGUNGEN)))

    print("\nAlles bestanden." if not fehler else f"\n{len(fehler)} Fehler.")
    return 1 if fehler else 0


def main():
    ap = argparse.ArgumentParser(description="Chartmuster der Etappe 1")
    ap.add_argument("--selbsttest", action="store_true")
    a = ap.parse_args()
    if a.selbsttest:
        sys.exit(selbsttest())
    ap.print_help()


if __name__ == "__main__":
    main()
