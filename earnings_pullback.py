"""Earnings-Pullback: Nach starken Quartalszahlen die erste ruhige
Konsolidierung kaufen, nicht den Sprung selbst.

GERHARDS FREIGABE vom 31.08.2026 (Baustein 2 des Einbau-Papiers,
einbau_strategien.md; die offenen Regelfragen G4 bis G7 sind nach
bestem Wissen entschieden und unten je Stelle vermerkt).

DIE LITERATUR DAHINTER, zweischichtig:
- Akademisch: Post-Earnings-Announcement Drift (Ball/Brown 1968,
  Bernard/Thomas 1989 und 1990): Nach positiven Gewinnueberraschungen
  driften Kurse ueber Wochen bis Monate weiter, weil der Markt die
  Tragweite der Zahl systematisch unterschaetzt. Die Long-Short-
  Umsetzung erzielte historisch rund 18 Prozent abnormale
  Jahresrendite; 25 bis 30 Prozent der Drift ballen sich um die
  NAECHSTEN Quartalstermine.
- Praktisch: Power Earnings Gap (TraderStewie) und Buyable Gap-Up
  (Morales/Kacher) kaufen nicht den Gap-Tag, sondern die erste enge
  Konsolidierung darueber; Episodic Pivot (Bonde) liefert die
  Anforderungen an Gap und Volumen.

UND DIE EIGENE MESSUNG: Die Forensik vom 30.08.2026 zeigte, dass
Einstiege VOR Zahlen die giftigsten des Logbuchs waren (minus 3,38
gegen minus 0,83 Prozent). Dieses Muster ist das Spiegelbild: erst die
Zahl, dann der Einstieg. Ein Kaufpunkt entsteht hier grundsaetzlich
NACH dem Termin — die Zahlen-Karenz und dieses Muster koennen sich
deshalb nie widersprechen.

ABGRENZUNG zu Gap and Go (Kapitel 7): Gap and Go handelt den Gap-TAG
selbst und fragt nicht nach dem Anlass. Der Earnings-Pullback verlangt
die Zahlen-Bindung und wartet auf die Konsolidierung; er ist der
geduldigere zweite Blick auf dasselbe Ereignis.
"""

from datetime import date, timedelta

import pandas as pd

from config import CFG

C = CFG["earnings_pullback"]

NAME = "Earnings-Pullback"


def _gap_tage(df):
    """Alle Gap-Kandidaten der letzten `suchfenster_tage`, juengster zuerst.

    Regelfrage G4, entschieden: Eroeffnung mindestens 8 Prozent ueber
    dem Vortagesschluss ODER Schluss mindestens 10 Prozent darueber,
    UND Tagesvolumen mindestens das Dreifache des 10-Tage-Schnitts der
    Tage DAVOR. Beide Wege, weil starke Zahlen-Reaktionen auch ohne
    Eroeffnungsluecke vorkommen (Intraday-Lauf nach Zahlen im Handel)."""
    kandidaten = []
    n = len(df)
    start = max(1, n - C["suchfenster_tage"])
    for i in range(n - C["min_konsolidierung"], start - 1, -1):
        if i < 11:
            break
        vortag = float(df["close"].iloc[i - 1])
        if vortag <= 0:
            continue
        o = float(df["open"].iloc[i])
        c = float(df["close"].iloc[i])
        vol = float(df["volume"].iloc[i])
        vol10 = float(df["volume"].iloc[i - 10:i].mean())
        gap_open = o / vortag - 1
        gap_close = c / vortag - 1
        if vol10 <= 0 or vol < C["vol_faktor"] * vol10:
            continue
        if gap_open >= C["min_gap_open"] or gap_close >= C["min_gap_close"]:
            kandidaten.append((i, max(gap_open, gap_close)))
    return kandidaten


def _konsolidierung(df, gap_i):
    """Die Tage NACH dem Gap-Tag als Konsolidierung pruefen.

    Regelfrage G6, entschieden: mindestens `min_konsolidierung`,
    hoechstens `max_konsolidierung` Handelstage; ALLE Tiefs bleiben
    ueber dem Tief des Gap-Tags (die Luecke haelt); die Spanne der
    Konsolidierung bleibt unter `max_spanne_anteil` der Gap-Tag-Spanne;
    und der letzte Schluss liegt noch UNTER dem Konsolidierungshoch —
    ist das Hoch schon gerissen, ist der Einstieg vorbei, nicht vor uns.
    """
    nach = df.iloc[gap_i + 1:]
    dauer = len(nach)
    if not C["min_konsolidierung"] <= dauer <= C["max_konsolidierung"]:
        return None
    gap_tief = float(df["low"].iloc[gap_i])
    gap_spanne = float(df["high"].iloc[gap_i]) - gap_tief
    if gap_spanne <= 0:
        return None
    if float(nach["low"].min()) <= gap_tief:
        return None
    spanne = float(nach["high"].max()) - float(nach["low"].min())
    if spanne > C["max_spanne_anteil"] * gap_spanne:
        return None
    hoch = float(nach["high"].max())
    if float(nach["close"].iloc[-1]) >= hoch:
        return None
    return {"hoch": hoch, "tief": float(nach["low"].min()),
            "dauer": dauer, "gap_tief": gap_tief}


def _termin_belegt(ticker, gap_datum, termine=None, kalender=None):
    """Lag am Gap-Tag (oder am Abend davor) der Quartalstermin?

    Regelfrage G5, GERHARDS ENTSCHEID vom 31.08.2026 abends: Der TERMIN
    GENUEGT, die Ueberraschung ist egal — auch eine negative lehnt
    nicht mehr ab (sein Wortlaut: "lieber mehr sehen und selbst
    filtern"; ein Gap nach oben trotz verfehlter Gewinnzahl kommt vom
    Ausblick, und genau solche Neubewertungen will er sehen). Die
    Zahlen-Bindung selbst bleibt PFLICHT — ohne belegten Termin kein
    Earnings-Pullback, fuer anlasslose Gaps gibt es Gap and Go.

    Zwei Quellen: die Termin-Historie von Yahoo (get_earnings_dates)
    und als Zweitquelle unser eigenes Terminmodul (kennt den Termin
    noch, wenn der Gap-Tag erst gestern war). `kalender` und `termine`
    sind injektierbar, damit der Selbsttest ohne Netz laeuft."""
    fenster = {gap_datum, gap_datum - timedelta(days=1),
               gap_datum - timedelta(days=3)}  # Montag nach Freitagabend
    if kalender is None:
        try:
            import yfinance as yf
            ed = yf.Ticker(ticker).get_earnings_dates(limit=12)
            kalender = []
            for stempel, zeile in ed.iterrows():
                surprise = zeile.get("Surprise(%)")
                kalender.append((stempel.date(),
                                 None if pd.isna(surprise)
                                 else float(surprise)))
        except Exception:
            kalender = []
    for tag, _surprise in kalender:
        if tag in fenster:
            return True
    try:
        import zahlen_termine
        t = (termine if termine is not None
             else zahlen_termine.lade()).get((ticker or "").upper())
        if t and str(t.get("datum", ""))[:10]:
            tag = date.fromisoformat(str(t["datum"])[:10])
            if tag in fenster:
                return True
    except Exception:
        pass
    return False


def detect_earnings_pullback(df, ticker, termine=None, kalender=None):
    """Der Detektor im Format der uebrigen Muster, oder None.

    Kaufpunkt = Konsolidierungshoch plus 1 Cent. Stop (Regelfrage G7,
    GERHARDS WORTLAUT vom 31.08.2026 abends: "4 Prozent Puffer unter
    dem Konsolidierungstief, weiter durch den Zehn-Prozent-Deckel
    begrenzt") = Konsolidierungstief mal 0,96; den Deckel legt wie
    ueberall der Scanner obendrauf. Der Puffer ist Morales' Porosity,
    damit ein Rauschen-Retest nicht sofort ausstoppt.

    FUER DIE AKTEN: Die zuerst gebaute Formel (das Hoehere aus
    Konsolidierungstief und Gap-Tag-Tief mal 0,96) war durch die
    Maximum-Bildung wirkungslos — das Konsolidierungstief liegt per
    Musterdefinition IMMER ueber dem Gap-Tag-Tief, der Puffer kam also
    nie zum Zug und der Stop klebte hart am Tief. Gerhards
    Bestaetigungs-Wortlaut hat den Fehler aufgedeckt; seine Fassung ist
    die gemeinte und die wirksame.

    Kein Kursziel: Die Bewirtschaftung uebernimmt Kapitel 12 in der
    Klasse zahlen_luecke (60 Tage Zeitdeckel, exakt die PEAD-Frist)."""
    if df is None or len(df) < 30:
        return None
    for gap_i, gap_pct in _gap_tage(df):
        kons = _konsolidierung(df, gap_i)
        if not kons:
            continue
        try:
            gap_datum = pd.Timestamp(df["datetime"].iloc[gap_i]).date()
        except (TypeError, ValueError):
            continue
        if not _termin_belegt(ticker, gap_datum, termine, kalender):
            continue
        kp = round(kons["hoch"] + 0.01, 2)
        stop = round(kons["tief"] * (1 - C["porosity"]), 2)
        return {
            "strategie": NAME,
            "kaufpunkt": kp,
            "stop": stop,
            "ziel": None,
            "status": (f"Zahlen-Gap +{gap_pct * 100:.0f}% am "
                       f"{gap_datum:%d.%m.}, {kons['dauer']} Tage "
                       f"Konsolidierung"),
        }
    return None


# ---------------------------------------------------------------------------
# Selbsttest (ohne Netz)
# ---------------------------------------------------------------------------

def _reihe(kurse, volumina, start="2026-07-01"):
    tage = pd.bdate_range(start, periods=len(kurse))
    return pd.DataFrame({
        "datetime": tage.astype(str),
        "open": [k * 0.995 for k in kurse],
        "high": [k * 1.01 for k in kurse],
        "low": [k * 0.99 for k in kurse],
        "close": kurse,
        "volume": volumina,
    })


def selbsttest() -> int:
    fehler = []

    def p(name, bedingung, zusatz=""):
        print(f"  {'ok  ' if bedingung else 'FEHL'} {name}"
              + (f" — {zusatz}" if zusatz else ""))
        if not bedingung:
            fehler.append(name)

    print("Earnings-Pullback, Selbsttest (ohne Netz)")

    # Basis: 30 ruhige Tage bei 100, dann Zahlen-Gap auf 115 mit WEITER
    # Tagesspanne (Tief 109 — der Gap-Tag laeuft von der Eroeffnung
    # hoch), dann enge Konsolidierung knapp unter dem Gap-Hoch. Die
    # pauschale _reihe setzt das Tief zu eng; der Gap-Tag bekommt es
    # deshalb ausdruecklich gesetzt, sonst prueft jeder Fall nur die
    # Luecken-Regel statt seines eigentlichen Gegenstands.
    kurse = [100.0] * 30 + [115.0] + [113.0, 113.5, 113.0, 113.5]
    vol = [1_000_000] * 30 + [5_000_000] + [1_500_000] * 4

    def bau(kursliste, volliste, gap_low=109.0):
        d = _reihe(kursliste, volliste)
        d.loc[30, "low"] = gap_low
        return d

    df = bau(kurse, vol)
    gap_datum = pd.Timestamp(df["datetime"].iloc[30]).date()
    kal_ok = [(gap_datum, 25.0)]
    kal_negativ = [(gap_datum, -12.0)]

    res = detect_earnings_pullback(df, "TST", kalender=kal_ok)
    p("Sauberer Fall wird erkannt", res is not None)
    if res:
        p("Kaufpunkt ueber dem Konsolidierungshoch",
          res["kaufpunkt"] > 113.5, res["kaufpunkt"])
        p("Stop unter der Konsolidierung, ueber dem Karenzbereich",
          res["stop"] < res["kaufpunkt"] * 0.99, res["stop"])
        p("Status nennt Gap und Dauer", "Zahlen-Gap" in res["status"])

    p("Ohne Termin-Beleg KEIN Signal (Gap and Go ist zustaendig)",
      detect_earnings_pullback(df, "TST", kalender=[]) is None)
    p("Negative Ueberraschung laesst durch (Gerhard, G5: Termin genuegt)",
      detect_earnings_pullback(df, "TST", kalender=kal_negativ) is not None)
    p("Fehlende Ueberraschungs-Angabe laesst durch (Ausblick-Gaps)",
      detect_earnings_pullback(df, "TST",
                               kalender=[(gap_datum, None)]) is not None)

    kurse_riss = kurse[:-1] + [117.5]
    p("Schon gerissenes Konsolidierungshoch ergibt kein Signal",
      detect_earnings_pullback(bau(kurse_riss, vol), "TST",
                               kalender=kal_ok) is None)

    df_bruch = bau(kurse, vol)
    df_bruch.loc[len(df_bruch) - 1, "low"] = 106.0
    p("Bruch des Gap-Tag-Tiefs ergibt kein Signal",
      detect_earnings_pullback(df_bruch, "TST", kalender=kal_ok) is None)

    vol_duenn = [1_000_000] * 30 + [1_400_000] + [1_500_000] * 4
    p("Gap ohne Volumen ergibt kein Signal",
      detect_earnings_pullback(bau(kurse, vol_duenn), "TST",
                               kalender=kal_ok) is None)

    kurse_breit = [100.0] * 30 + [115.0] + [113.0, 116.0, 111.0, 113.5]
    p("Zu breite Konsolidierung ergibt kein Signal",
      detect_earnings_pullback(bau(kurse_breit, vol), "TST",
                               kalender=kal_ok) is None)

    p("Zu kurze Konsolidierung (1 Tag) ergibt noch kein Signal",
      detect_earnings_pullback(
          bau(kurse[:32], vol[:32]), "TST", kalender=kal_ok) is None)

    zweitquelle = {"TST": {"datum": gap_datum.isoformat()}}
    p("Zweitquelle Terminmodul belegt den Termin",
      detect_earnings_pullback(df, "TST", termine=zweitquelle,
                               kalender=[]) is not None)

    if fehler:
        print(f"\n{len(fehler)} FEHLER: {', '.join(fehler)}")
        return 1
    print("\nAlles bestanden.")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(selbsttest())
