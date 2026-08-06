#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VOLUMEN — IBD "Volume % Change" mit Intraday-Hochrechnung
==========================================================
Gerhards Fassung vom 28.07.2026, verbindlich fuer das GANZE System:
Scanner, Waechter und Gap-and-Go rechnen ab jetzt hier und nirgends
sonst. Genau darum geht es ihm: Vorher rechnete der Scanner an einer
Stelle mit 20 Tagen, an anderer mit 10, der Waechter mit 10 — solche
stillen Uneinheitlichkeiten sollen weg.

    Volume%Change(t) = ( V_bisher(t) / F(t) / V50 − 1 ) × 100

    V_bisher(t)  heute bis jetzt gehandeltes Volumen
    F(t)         ueblicher Anteil des Tagesvolumens bis zu dieser Uhrzeit
    V50          Durchschnitt des GANZEN Tagesvolumens ueber die 50
                 abgeschlossenen Handelstage VOR heute (IBD-Standard)

Am Handelsschluss ist F(t) = 1, die Formel faellt dann von selbst auf
die reine IBD-Tagesformel zurueck. Ein Weg fuer beide Faelle, kein
Umschalten.

WAS SICH GEGENUEBER DER ALTEN RECHNUNG AENDERT
-----------------------------------------------
1. V50 statt Ø10. IBD-Standard. Gerhard hat das ausdruecklich als
   eigene Entscheidung neben der Formelkorrektur angeordnet — es
   widerruft seine eigene Festlegung vom Vormittag desselben Tages
   (damals 10 Tage, "einheitlich fuer Scanner UND Waechter").
2. F(t) im FUENF-Minuten-Raster aus echten Kursdaten statt der bisher
   fest hinterlegten 14 Stuetzstellen im Halbstundenraster. Der
   Unterschied zaehlt fast nur in der ersten halben Stunde — und genau
   dort entscheidet sich alles. Die alte Kurve stieg zwischen 09:30 und
   10:00 GERADLINIG von 0 auf 21,3 %; in Wahrheit ist der Sprung der
   Eroeffnungsauktion viel steiler. Wer in Minute 2 mit der geraden
   Linie hochrechnet, teilt durch einen viel zu kleinen Anteil und
   erzeugt Fantasiewerte.
3. Ausgegeben wird die IBD-Prozentzahl (+2025 %) statt eines
   Verhaeltnisses (21,3-fach). Verglichen wird weiterhin das
   Verhaeltnis — dieselbe Groesse, nur anders geschrieben, damit sich
   die Zahlen direkt gegen IBD halten lassen.
4. (06.08.2026) EIGENE KURVE JE AKTIE, KEIN RUECKGRIFF MEHR. Bis dahin
   diente EINE geliehene Kurve aus SPY, QQQ, AAPL, MSFT und AMD als
   Massstab fuer ALLE Aktien. Gerhards Begruendung fuer die Abschaffung:
   Eine volatile Nebenwerteaktie hat ein anderes untertaegiges
   Volumenmuster als ein ruhiger Grosswert. Jede Aktie bekommt jetzt
   ihre Kurve aus ihrer EIGENEN 50-Tage-Historie im Fuenf-Minuten-Raster.
   Reicht die nicht (unter 40 von 50 Tagen, etwa ein frischer
   Boersengang), gibt es KEINE Ersatzkurve mehr, sondern den eigenen
   Status 'nicht_verifizierbar'.

   DER DRITTE STATUS IST KEINE SPITZFINDIGKEIT. 'Nicht bestaetigt'
   heisst: geprueft und zu schwach. 'Nicht verifizierbar' heisst: es
   liess sich gar nicht pruefen. Wer beides in denselben Topf wirft,
   laesst eine Aktie ohne genug Historie lautlos in der falschen
   Kategorie verschwinden.

ZUM FEHLERBEFUND IM UEBERGABEPAPIER (wichtig fuer die Akten)
-------------------------------------------------------------
Gerhard beschreibt den KNSA-Fall so, dass das bestehende System OHNE
jede Hochrechnung vergleiche und deshalb -32 % statt +2000 % gezeigt
habe; sein Modul nennt das selbst "(vermutlich)". Nachgeprueft am
28.07.2026: In DIESEM Code stimmt das nicht — breakout_watcher.py
rechnet seit dem 23.07. mit tagesanteil() hoch. Mit der alten Kurve
haette KNSA rund +1815 % ergeben, nicht -32 %. Die -32 % lassen sich
hier nirgends reproduzieren.

Das entwertet die Korrektur NICHT: Die Fuenf-Minuten-Kurve ist in den
ersten Minuten deutlich genauer als die gerade Linie, V50 ist der
IBD-Standard, und die Vereinheitlichung ueber alle Module war
ueberfaellig. Es heisst nur: Es war eine Verbesserung, keine Reparatur
eines stillen Trade-Killers. Wer spaeter im Protokoll liest, soll das
richtig einordnen koennen.

Aufruf:
    python volumen.py                 Selbsttest (ohne Netzwerk)
    python volumen.py --bauen         Referenzkurve neu aus Kursdaten
"""

import json
import sys
from datetime import datetime

RASTER = 5                      # Minuten je Stuetzstelle
HANDELSMINUTEN = 390            # 09:30 bis 16:00 New Yorker Zeit
KURVEN_DATEI = "volumenkurven.json"      # eine Kurve JE AKTIE

# Ab wie vielen eigenen Handelstagen ist eine Kurve verwendbar? Gerhards
# Wert: 40 von angestrebten 50. Darunter 'nicht_verifizierbar'.
MIN_TAGE_FUER_EIGENE_KURVE = 40
TAGE_ZIEL = 50

# ENTFERNT am 06.08.2026 auf Gerhards ausdrueckliche Anweisung:
#   REFERENZ_TICKER = ["SPY", "QQQ", "AAPL", "MSFT", "AMD"]
#   RUECKFALL_KURVE = {0: 0.000, 30: 0.213, ...}
# Die eine geliehene Kurve fuer alle Aktien und die fest hinterlegte
# Halbstundenkurve als Rueckfall. Beides ist weg, und zwar ersatzlos:
# Eine Aktie wird NUR mit ihrer eigenen Historie bewertet oder gar nicht.
# Wer einen Rueckfall wieder einbaut, hebt genau die Entscheidung auf,
# um die es hier geht — ein stiller fremder Massstab ist schlimmer als
# ein ehrliches "nicht pruefbar".

_kurven = None                  # {ticker: {minute: anteil}}, einmal geladen


# ---------------------------------------------------------------------------
# Die Entscheidung: eigene Kurve oder gar keine
# ---------------------------------------------------------------------------

def entscheide_kurven_quelle(verfuegbare_tage, min_tage_noetig=None):
    """Reine Entscheidung, ohne Netz, deshalb direkt pruefbar.

    Rueckgabe: 'eigene_aktie' oder 'nicht_verifizierbar'. Einen dritten
    Ausgang gibt es nicht mehr."""
    schwelle = min_tage_noetig or MIN_TAGE_FUER_EIGENE_KURVE
    return ("eigene_aktie" if verfuegbare_tage >= schwelle
            else "nicht_verifizierbar")


# ---------------------------------------------------------------------------
# Kurven bauen (Netzwerk) — gehoert in den Nachtlauf, nicht in den Waechter
# ---------------------------------------------------------------------------

def _kurve_aus_kerzen(df):
    """Aus Fuenf-Minuten-Kerzen EINER Aktie die Kurve F(t) bauen.

    Rueckgabe: ({minute: anteil}, Zahl der verwendeten Handelstage).

    Drei Fallen, alle schon in der Fassung vom 28.07.2026 behandelt und
    hier unveraendert uebernommen:
    1. VERSCHIEBUNG UM EINE KERZE. Die Kerze mit Beginn 09:30 enthaelt
       den Umsatz BIS 09:35; ihre kumulierte Summe gehoert an Minute 5,
       nicht an Minute 0. Wer das verwechselt, rechnet frueh am Tag mit
       einem viel zu grossen Anteil — genau dort, wo es am meisten
       schadet. Bei Minute 0 steht per Definition 0.
    2. HALBE HANDELSTAGE. Vor Feiertagen schliesst die Boerse um 13:00.
       Dort sind 100 % nach 210 Minuten erreicht; mitteln wuerde die
       Kurve nach vorne verbiegen. Solche Tage fliegen raus.
    3. MEHRSTUFIGE SPALTEN von yfinance, auch bei einem einzelnen Ticker."""
    import pandas as pd

    if df is None or df.empty:
        return None, 0
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    try:
        df = df.tz_convert("America/New_York")
    except Exception:
        pass

    df = df[["Volume"]].dropna()
    if df.empty:
        return None, 0
    df = df.copy()
    df["minute"] = [(z.hour * 60 + z.minute) - (9 * 60 + 30)
                    for z in df.index.time]
    df["datum"] = df.index.date
    df = df[(df["minute"] >= 0) & (df["minute"] < HANDELSMINUTEN)]

    kurven = []
    for _, tag in df.groupby("datum"):
        tag = tag.sort_index()
        gesamt = float(tag["Volume"].sum())
        if gesamt <= 0:
            continue
        if int(tag["minute"].max()) < HANDELSMINUTEN - 40:
            continue                                   # halber Handelstag
        kum = tag["Volume"].cumsum() / gesamt
        punkte = {0: 0.0}
        for minute, wert in zip(tag["minute"].values, kum.values):
            punkte[int(minute) + RASTER] = float(wert)
        kurven.append(punkte)

    if not kurven:
        return None, 0

    raster = list(range(0, HANDELSMINUTEN + 1, RASTER))
    gemittelt = {}
    for m in raster:
        werte = sorted(k[m] for k in kurven if m in k)
        if werte:
            gemittelt[m] = werte[len(werte) // 2]      # Median, robust
    letzter = 0.0
    for m in raster:
        if m in gemittelt:
            letzter = gemittelt[m] = max(letzter, gemittelt[m])
    gemittelt[0] = 0.0
    gemittelt[HANDELSMINUTEN] = 1.0
    return gemittelt, len(kurven)


def baue_kurven(tickers, tage=TAGE_ZIEL, pfad=KURVEN_DATEI,
                bloecke=40, leise=False):
    """Fuer JEDE uebergebene Aktie ihre eigene Kurve bauen und ablegen.

    Gehoert in den NACHTLAUF, nicht in den Waechter. Gerhards Vorgabe
    lautet 'einmal pro Tag und Aktie, dann zwischenspeichern'; der
    Nachtscanner ist genau dieser eine Zeitpunkt. Der Waechter zur
    Eroeffnung haette sonst 366 Abrufe zu erledigen, waehrend jede
    Sekunde zaehlt.

    Abgerufen wird in BLOECKEN. Gemessen am 06.08.2026: ein einzelner
    Ticker braucht 0,3 bis 0,7 s, ein Sammelabruf ueber zehn Ticker
    ebenfalls 0,7 s — die Blockbildung ist also fast gratis."""
    import yfinance as yf

    tickers = sorted({t.upper() for t in tickers if t})
    ergebnis, ohne = {}, []
    for i in range(0, len(tickers), bloecke):
        block = tickers[i:i + bloecke]
        try:
            roh = yf.download(" ".join(block), period=f"{min(tage, 59)}d",
                              interval="5m", group_by="ticker",
                              progress=False, auto_adjust=False, threads=True)
        except Exception as e:
            if not leise:
                print(f"    Volumenkurven: Block {i//bloecke+1} fehlgeschlagen "
                      f"({type(e).__name__})")
            ohne.extend(block)
            continue
        for t in block:
            try:
                df = roh[t] if len(block) > 1 else roh
            except Exception:
                ohne.append(t)
                continue
            kurve, n_tage = _kurve_aus_kerzen(df)
            # Die Entscheidung faellt EINMAL, an genau einer Stelle.
            if entscheide_kurven_quelle(n_tage) != "eigene_aktie" or not kurve:
                ohne.append(t)
                continue
            ergebnis[t] = {"tage": n_tage, "quelle": "eigene_aktie",
                           "kurve": {str(m): round(a, 6)
                                     for m, a in sorted(kurve.items())}}

    try:
        from zoneinfo import ZoneInfo
        stempel = (datetime.now(ZoneInfo("Europe/Vienna"))
                   .strftime("%Y-%m-%d %H:%M") + " Wien")
    except Exception:
        stempel = datetime.now().strftime("%Y-%m-%d %H:%M") + " (Zone unbekannt)"

    inhalt = {"gebaut_am": stempel, "raster_minuten": RASTER,
              "min_tage": MIN_TAGE_FUER_EIGENE_KURVE,
              "nicht_verifizierbar": sorted(ohne), "aktien": ergebnis}
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(inhalt, f, ensure_ascii=False, indent=1)
    if not leise:
        print(f"  Volumenkurven: {len(ergebnis)} eigene Kurven gebaut, "
              f"{len(ohne)} nicht verifizierbar (unter "
              f"{MIN_TAGE_FUER_EIGENE_KURVE} eigenen Handelstagen) → {pfad}")
    setze_kurven(inhalt)
    return inhalt


def zaehle_verfuegbare_tage(ticker, tage=TAGE_ZIEL):
    """Wie viele eigene Handelstage mit Fuenf-Minuten-Daten gibt es?
    Braucht Netzwerk; im Betrieb faellt die Antwort schon beim Bauen an."""
    import yfinance as yf
    try:
        df = yf.download(ticker, period=f"{min(tage, 59)}d", interval="5m",
                         progress=False, auto_adjust=False)
    except Exception:
        return 0
    return 0 if df is None or df.empty else len(set(df.index.date))


def hole_f_kurve_fuer_aktie(ticker, tage=TAGE_ZIEL, min_tage_noetig=None,
                            pfad=KURVEN_DATEI):
    """Gerhards Hauptfunktion. Rueckgabe: (f_kurve, quelle).

    quelle ist 'eigene_aktie' oder 'nicht_verifizierbar'; im zweiten Fall
    ist f_kurve None, und der Aufrufer MUSS das als eigenen Status
    behandeln — nicht als 'Volumen nicht bestaetigt'.

    Zuerst wird der Tagesvorrat aus KURVEN_DATEI befragt (der Nachtlauf
    hat ihn gefuellt). Nur wenn dort nichts steht, wird live gebaut —
    das kostet Netzwerk und soll im Waechter nicht vorkommen."""
    if not ticker:
        return None, "nicht_verifizierbar"
    t = ticker.upper()
    vorrat = lade_kurven(pfad, leise=True)
    if t in vorrat:
        return vorrat[t], "eigene_aktie"

    import yfinance as yf
    try:
        df = yf.download(t, period=f"{min(tage, 59)}d", interval="5m",
                         progress=False, auto_adjust=False)
    except Exception:
        return None, "nicht_verifizierbar"
    kurve, n_tage = _kurve_aus_kerzen(df)
    if entscheide_kurven_quelle(n_tage, min_tage_noetig) != "eigene_aktie" \
            or not kurve:
        return None, "nicht_verifizierbar"
    return kurve, "eigene_aktie"


# ---------------------------------------------------------------------------
# Vorrat laden
# ---------------------------------------------------------------------------

def lade_kurven(pfad=KURVEN_DATEI, leise=False):
    """Alle gebauten Kurven. Fehlt die Datei, ist der Vorrat LEER — und
    damit jede Aktie 'nicht verifizierbar'. Genau so ist es gewollt: Ein
    Rueckfall auf irgendeinen Ersatzmassstab gibt es seit 06.08.2026
    nicht mehr."""
    global _kurven
    if _kurven is not None:
        return _kurven
    try:
        with open(pfad, encoding="utf-8") as f:
            roh = json.load(f)
        _kurven = {t: {int(m): float(a) for m, a in e["kurve"].items()}
                   for t, e in roh.get("aktien", {}).items()}
        if not leise:
            print(f"  Volumenkurven geladen: {len(_kurven)} Aktien mit eigener "
                  f"Kurve, gebaut am {roh.get('gebaut_am', 'unbekannt')}.")
    except Exception as e:
        _kurven = {}
        if not leise:
            print(f"  ⚠ Keine Volumenkurven ({type(e).__name__}) — jede Aktie "
                  f"gilt als nicht verifizierbar, bis der Nachtlauf sie baut.")
    return _kurven


def setze_kurven(inhalt):
    """Vorrat direkt setzen (Nachtlauf und Selbsttest)."""
    global _kurven
    roh = inhalt.get("aktien", inhalt) if isinstance(inhalt, dict) else {}
    _kurven = {}
    for ticker, eintrag in (roh or {}).items():
        punkte = eintrag.get("kurve", eintrag) if isinstance(eintrag, dict) else {}
        # Minuten IMMER auf int: aus JSON kommen sie als Zeichenketten,
        # und ein Vergleich int gegen str wirft mitten in der Rechnung.
        _kurven[str(ticker).upper()] = {int(m): float(a)
                                        for m, a in punkte.items()}
    return _kurven


def minute_seit_eroeffnung(jetzt=None):
    """Minuten seit 09:30 New Yorker Zeit. None ausserhalb des Handels
    und wenn die Zeitzone fehlt — dann wird nicht hochgerechnet."""
    try:
        from zoneinfo import ZoneInfo
        ny = ZoneInfo("America/New_York")
    except Exception:
        return None
    jetzt = (jetzt or datetime.now(ny)).astimezone(ny)
    m = jetzt.hour * 60 + jetzt.minute - (9 * 60 + 30)
    if m < 0 or m >= HANDELSMINUTEN:
        return None
    return m


def tagesanteil(minute=None, kurve=None):
    """F(t): Anteil des Tagesvolumens, der bis zu dieser Minute seit
    Handelsbeginn ueblicherweise schon gehandelt ist — nach der Kurve
    DIESER Aktie.

    None (vor Eroeffnung, nach Schluss) ergibt 1,0; dann ist der Tag
    komplett und es wird nichts hochgerechnet — dafuer braucht es auch
    keine Kurve (Gerhard: der reine EOD-Fall laeuft ohne).

    Ohne Kurve und MIT Uhrzeit gibt es None: nicht verifizierbar. Frueher
    stand hier ein Rueckgriff auf die geliehene Kurve."""
    if minute is None:
        return 1.0
    if not kurve:
        return None
    minute = max(0, min(HANDELSMINUTEN, int(minute)))
    stellen = sorted(kurve)
    if minute <= stellen[0]:
        return max(kurve[stellen[0]], 0.001)
    if minute >= stellen[-1]:
        return 1.0
    for i in range(1, len(stellen)):
        m0, m1 = stellen[i - 1], stellen[i]
        if minute <= m1:
            a0, a1 = kurve[m0], kurve[m1]
            spanne = m1 - m0
            anteil = a0 + (a1 - a0) * ((minute - m0) / spanne) if spanne else a1
            # Nie durch (fast) null teilen. 0,001 entspricht rund den
            # ersten Sekunden nach der Glocke.
            return max(anteil, 0.001)
    return 1.0


def kurve_fuer(ticker):
    """Die Kurve dieser Aktie aus dem Tagesvorrat, sonst None."""
    return lade_kurven(leise=True).get((ticker or "").upper())


def verhaeltnis(v_bisher, v50, minute=None, kurve=None):
    """Das Vielfache des ueblichen Volumens FUER DIESE UHRZEIT.
    1,0 heisst voellig normal, 21,3 heisst 21-faches Tempo.

    None heisst NICHT VERIFIZIERBAR — entweder fehlt der 50-Tage-Schnitt
    oder es gibt keine eigene Kurve fuer die Uhrzeit-Hochrechnung. Der
    Aufrufer muss das als eigenen Status behandeln und NICHT als
    'Volumen nicht bestaetigt' (Gerhard, 06.08.2026)."""
    if not v50 or v50 <= 0 or v_bisher is None:
        return None
    anteil = tagesanteil(minute, kurve)
    if anteil is None:
        return None
    return (v_bisher / anteil) / v50


def volume_pct_change(v_bisher, v50, f_kurve=None, minute_seit_open=None):
    """Die IBD-Zahl: +2025 % heisst das 21,25-fache des Ueblichen,
    -32 % heisst ein knappes Drittel unter dem Ueblichen.

    Reihenfolge und Namen der Parameter wie in Gerhards Fassung vom
    06.08.2026. Ohne Uhrzeit (EOD) braucht es keine Kurve; mit Uhrzeit
    und ohne Kurve kommt None zurueck statt einer Ersatzrechnung."""
    v = verhaeltnis(v_bisher, v50, minute_seit_open, f_kurve)
    return None if v is None else (v - 1.0) * 100.0


def text(v_bisher, v50, minute=None, kurve=None):
    """Einheitliche Schreibweise fuer Meldungen und Protokoll."""
    p = volume_pct_change(v_bisher, v50, kurve, minute)
    if p is None:
        return NICHT_VERIFIZIERBAR
    return f"{p:+.0f} % gegenüber dem 50-Tage-Schnitt"


# Der dritte Status, woertlich und an EINER Stelle — damit er nirgends
# als "nicht bestaetigt" umgedeutet wird.
NICHT_VERIFIZIERBAR = ("Volumen NICHT VERIFIZIERBAR, keine eigene "
                       "Volumenkurve (unter 40 Handelstagen Historie)")


# --- Schreibweise fuer Meldungen ------------------------------------------
# Am 28.07.2026 stand in einer echten Meldung "nötig +0 %". Rechnerisch
# richtig — die Huerde der meisten Muster ist der Faktor 1,0, also null
# Prozent UEBER dem Schnitt — aber es liest sich wie "keine Anforderung"
# oder wie ein Fehler. Mathias hat es sofort bemerkt. Deshalb wird der
# Faktor 1,0 ausgeschrieben statt als Prozentzahl dargestellt, und die
# Lage der Aktie in Worten statt mit Vorzeichen.

# HINWEIS FUER SPAETER (28.07.2026): Zwei weitere IBD-Volumenmasse wurden
# recherchiert, gebaut und auf Gerhards Ansage wieder VOLLSTAENDIG
# entfernt — das Up/Down Volume Ratio ueber 50 Handelstage und IBDs
# Liquiditaetsuntergrenzen (400.000 Stueck, 20 Millionen Dollar Umsatz).
# Grund: Beide beschreiben den Charakter einer Aktie ueber Wochen und
# sagen nichts darueber, ob der Ausbruch HEUTE gilt. Sie gehoeren in die
# Auswahl der Liste, nicht in den Waechter. Den FILTER haben sie nie
# beeinflusst. Der Code steht im Git-Verlauf unter 'IBD-Zusatzmasse'.


def huerde_text(faktor):
    """Was verlangt wird, in lesbarer Form."""
    if faktor <= 1.0:
        return "nötig wäre mindestens der Schnitt"
    return f"nötig {(faktor - 1) * 100:.0f} % darüber"


def lage_text(pct, fenster=50):
    """Wo die Aktie steht, ohne Vorzeichen-Rätsel."""
    if pct is None:
        return "Volumen nicht bewertbar"
    if pct >= 0:
        return f"{pct:.0f} % über Ø{fenster}"
    return f"{abs(pct):.0f} % unter Ø{fenster}"


# ---------------------------------------------------------------------------
# Selbsttest — ohne Netzwerk
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if "--bauen" in sys.argv:
        # Kurven fuer die Aktien aus einer CSV oder der Excel-Mappe bauen.
        import argparse
        ap = argparse.ArgumentParser()
        ap.add_argument("--bauen", action="store_true")
        ap.add_argument("--tickers", help="Komma-Liste; sonst aus kaufpunkte_aktuell.xlsx")
        a, _ = ap.parse_known_args()
        if a.tickers:
            liste = [t.strip() for t in a.tickers.split(",") if t.strip()]
        else:
            import pandas as pd
            liste = sorted(set(pd.read_excel("kaufpunkte_aktuell.xlsx")["Ticker"]
                               .astype(str).str.upper()))
        baue_kurven(liste)
        sys.exit(0)

    # Eine realistische Kurve von Hand, damit der Test ohne Netz laeuft:
    # steiler Eroeffnungsschub, ruhige Mitte, Schlussauktion.
    test_kurve = {0: 0.0, 5: 0.055, 10: 0.082, 15: 0.101, 30: 0.150,
                  60: 0.232, 120: 0.365, 195: 0.520, 270: 0.665,
                  330: 0.790, 375: 0.930, 390: 1.0}
    setze_kurven({"TEST": {"kurve": {str(m): a for m, a in test_kurve.items()}}})
    k = kurve_fuer("TEST")

    print("=" * 66)
    print("TEST 1: Am Handelsschluss muss die reine IBD-Tagesformel stehen")
    print("=" * 66)
    assert abs(volume_pct_change(1_100_000, 700_000) - 57.14) < 0.01
    assert abs(volume_pct_change(700_000, 700_000) - 0.0) < 1e-9
    print("  1,1 Mio gegen Ø50 700.000 → +57 %; genau am Schnitt → 0 %  ✓")
    print("  (ohne Uhrzeit braucht die Formel KEINE Kurve — Gerhards EOD-Fall)")

    print("\n" + "=" * 66)
    print("TEST 2: Eine Aktie im üblichen Tempo zeigt zu JEDER Uhrzeit ~0 %")
    print("=" * 66)
    for minute in (5, 30, 60, 195, 330):
        f = tagesanteil(minute, k)
        pct = volume_pct_change(f * 700_000, 700_000, k, minute)
        print(f"  Minute {minute:>3} (F={f:.3f}) → {pct:+.1f} %")
        assert abs(pct) < 1.0

    print("\n" + "=" * 66)
    print("TEST 3: Echte Auffälligkeit bleibt den ganzen Tag sichtbar")
    print("=" * 66)
    for minute in (5, 60, 195, 330):
        f = tagesanteil(minute, k)
        pct = volume_pct_change(f * 700_000 * 4.0, 700_000, k, minute)
        print(f"  Minute {minute:>3}: vierfaches Tempo → {pct:+.0f} %")
        assert 295 < pct < 305

    print("\n" + "=" * 66)
    print("TEST 4: Die Entscheidung eigene Kurve oder gar keine")
    print("=" * 66)
    faelle = [(50, None, "eigene_aktie", "volle Historie"),
              (40, None, "eigene_aktie", "genau an der Schwelle"),
              (39, None, "nicht_verifizierbar", "einen Tag zu wenig"),
              (15, None, "nicht_verifizierbar", "Börsengang vor drei Wochen"),
              (0, None, "nicht_verifizierbar", "Börsengang heute"),
              (25, 20, "eigene_aktie", "eigene, niedrigere Schwelle")]
    for tage, schwelle, erwartet, was in faelle:
        ist = entscheide_kurven_quelle(tage, schwelle)
        print(f"  {was}: {tage} Tage → {ist}")
        assert ist == erwartet, f"erwartet {erwartet}, war {ist}"
    print("  ✓ Nur zwei Ausgänge, kein Rückgriff auf eine fremde Kurve")

    print("\n" + "=" * 66)
    print("TEST 5: Ohne eigene Kurve — NICHT VERIFIZIERBAR, kein Absturz")
    print("=" * 66)
    # EOD ohne Kurve: geht, weil F(t)=1 keine Kurve braucht
    assert volume_pct_change(150_000, 100_000, None, None) is not None
    print("  EOD ohne Kurve: rechnet normal weiter  ✓")
    # Intraday ohne Kurve: None, KEINE Ersatzrechnung
    assert volume_pct_change(70_000, 100_000, None, 30) is None
    assert tagesanteil(30, None) is None
    assert verhaeltnis(70_000, 100_000, 30, None) is None
    print("  Intraday ohne Kurve: None  ✓")
    assert "NICHT VERIFIZIERBAR" in text(70_000, 100_000, 30, None)
    print(f"  Text dazu: „{text(70_000, 100_000, 30, None)}"
          f"“  ✓")
    print("  ✓ Das ist NICHT dasselbe wie 'nicht bestätigt' — dort wurde")
    print("    geprüft und für zu schwach befunden, hier gar nicht geprüft.")

    print("\n" + "=" * 66)
    print("TEST 6: Fehlender 50-Tage-Schnitt")
    print("=" * 66)
    assert volume_pct_change(500_000, 0) is None
    assert volume_pct_change(500_000, None) is None
    print("  Ohne Ø50 keine Zahl  ✓")

    print("\n" + "=" * 66)
    print("TEST 7: Der Vorrat kennt eine Aktie nicht")
    print("=" * 66)
    assert kurve_fuer("GIBTSNICHT") is None
    assert kurve_fuer(None) is None
    assert volume_pct_change(1_000, 500, kurve_fuer("GIBTSNICHT"), 30) is None
    print("  Unbekannte Aktie → keine Kurve → nicht verifizierbar  ✓")

    print("\n" + "=" * 66)
    print("TEST 8: Eine Kurve aus echten Kerzen bauen (ohne Netz)")
    print("=" * 66)
    import pandas as _pd
    # Zwei volle Handelstage im Fuenf-Minuten-Raster, U-foermig verteilt.
    zeilen, volumina = [], []
    for tag in ("2026-07-01", "2026-07-02"):
        for m in range(0, 390, 5):
            zeilen.append(_pd.Timestamp(f"{tag} 09:30", tz="America/New_York")
                          + _pd.Timedelta(minutes=m))
            x = m / 390
            volumina.append(1000 * (0.7 + 2.5 * (x - 0.5) ** 2))
    df = _pd.DataFrame({"Volume": volumina}, index=_pd.DatetimeIndex(zeilen))
    kurve, n = _kurve_aus_kerzen(df)
    assert n == 2, f"zwei Handelstage erwartet, {n} gezählt"
    assert kurve[0] == 0.0 and kurve[390] == 1.0
    assert all(kurve[a] <= kurve[b] for a, b in zip(sorted(kurve), sorted(kurve)[1:]))
    print(f"  {n} Tage, {len(kurve)} Stützstellen, monoton, 0 bis 1  ✓")
    # Halber Handelstag muss ausgeschieden werden
    halb = df[df.index.time < __import__("datetime").time(13, 0)]
    _, n_halb = _kurve_aus_kerzen(halb)
    assert n_halb == 0, f"halbe Tage müssen rausfallen, {n_halb} blieben"
    print("  Halbe Handelstage (Feiertagsschluss 13:00) fliegen raus  ✓")

    print("\nAlle Volumen-Tests bestanden (ohne Netzwerk).")
