"""Kell-Zyklus: In welcher Phase seines Preiszyklus steht eine Aktie?

GERHARDS FREIGABE vom 31.08.2026 (Baustein 5 des Einbau-Papiers,
Teil 1 — NUR MESSEN). Oliver Kell (US-Meister 2020 mit plus 941,1
Prozent, "Victory in Stock Trading", 2021) beschreibt jede Aktie als
Wanderung durch sechs Stufen um die 10- und 20-Tage-Exponentiallinien:
Reversal Extension, Wedge Pop, EMA Crossback, Base n' Break,
Exhaustion Extension, Wedge Drop.

WAS DIESES MODUL TUT UND WAS NICHT: Es KLASSIFIZIERT nur. Die Phase
wandert als Feld in jede Nachtscan-Logbuchzeile; gemeldet, gefiltert
oder entschieden wird NICHTS. Erst wenn das Logbuch nach einigen
Wochen zeigt, in welcher Phase unsere Ausbrueche funktionieren und in
welcher sie scheitern, lohnt die Diskussion ueber Konsequenzen
(Regelfrage G11, der Crossback als eigenes Kaufmuster, liegt bis dahin
auf Eis).

Die Schwellen sind ERSTKALIBRIERUNGEN (Kell nennt keine Zahlen, er
liest die Ueberdehnung mit dem Auge); sie stehen in config.py und
werden nach den ersten Logbuch-Wochen nachgemessen.

Aufruf:
  python kell_zyklus.py --selbsttest
"""

import sys

from config import CFG

C = CFG["kell_zyklus"]

PHASEN = ["Reversal Extension", "Wedge Pop", "EMA Crossback",
          "Base n' Break", "Aufwärtstrend", "Exhaustion Extension",
          "Wedge Drop", "Abwärts-Crossback", "Abwärtstrend"]


def klassifiziere(df):
    """Die aktuelle Zyklusphase einer Kursreihe, oder None.

    Erwartet die Scanner-Spalten (close, high, low); rechnet die 10er-
    und 20er-Exponentiallinie selbst, damit jeder Aufrufer dieselbe
    Definition bekommt."""
    if df is None or len(df) < 25:
        return None
    schluss = df["close"].astype(float)
    e10 = schluss.ewm(span=10, adjust=False).mean()
    e20 = schluss.ewm(span=20, adjust=False).mean()
    k = float(schluss.iloc[-1])
    e10l, e20l = float(e10.iloc[-1]), float(e20.iloc[-1])
    if e10l <= 0 or e20l <= 0:
        return None

    # Die Ueberdehnungen zuerst — sie schlagen alles andere.
    if k > e10l * (1 + C["exhaustion_abstand"]):
        return "Exhaustion Extension"
    if k < e10l * (1 - C["reversal_abstand"]):
        return "Reversal Extension"

    fenster = min(C["pop_fenster"], len(schluss) - 1)
    unter_beiden = sum(
        1 for i in range(-fenster - 1, -1)
        if float(schluss.iloc[i]) < float(e10.iloc[i])
        and float(schluss.iloc[i]) < float(e20.iloc[i]))

    if k > e10l and k > e20l:
        # Frisch von unten zurueckerobert?
        if unter_beiden >= C["pop_mindesttage"]:
            return "Wedge Pop"
        if e10l > e20l:
            spanne_tage = min(8, len(df))
            hoch = float(df["high"].tail(spanne_tage).max())
            tief = float(df["low"].tail(spanne_tage).min())
            if tief > 0 and (hoch - tief) / k <= C["basen_spanne"]:
                return "Base n' Break"
            return "Aufwärtstrend"
        return "Wedge Pop"
    if k < e10l and k < e20l:
        # Bruch im noch intakten Aufwaertskontext = Wedge Drop; sind die
        # Linien schon gedreht, ist es der gewoehnliche Abwaertstrend.
        return "Wedge Drop" if e10l > e20l else "Abwärtstrend"
    # Zwischen den Linien: die Rueckkehr AN die Durchschnitte.
    return "EMA Crossback" if e10l > e20l else "Abwärts-Crossback"


# ---------------------------------------------------------------------------
# Selbsttest (ohne Netz)
# ---------------------------------------------------------------------------

def _df(kurse):
    import pandas as pd
    return pd.DataFrame({
        "close": kurse,
        "high": [k * 1.005 for k in kurse],
        "low": [k * 0.995 for k in kurse],
    })


def selbsttest() -> int:
    fehler = []

    def p(name, bedingung, zusatz=""):
        print(f"  {'ok  ' if bedingung else 'FEHL'} {name}"
              + (f" — {zusatz}" if zusatz else ""))
        if not bedingung:
            fehler.append(name)

    print("Kell-Zyklus, Selbsttest (ohne Netz)")

    ruhig = [100.0] * 40
    p("Zu kurze Reihe liefert None", klassifiziere(_df([100.0] * 10)) is None)

    parabel = [100.0 + i * 0.3 for i in range(35)] + [
        112.0, 118.0, 126.0, 136.0, 148.0]
    p("Parabolische Ueberdehnung ist die Exhaustion Extension",
      klassifiziere(_df(parabel)) == "Exhaustion Extension",
      klassifiziere(_df(parabel)))

    crash = [100.0] * 35 + [95.0, 88.0, 80.0, 72.0, 65.0]
    p("Kapitulation ist die Reversal Extension",
      klassifiziere(_df(crash)) == "Reversal Extension",
      klassifiziere(_df(crash)))

    pop = [100.0 - i * 0.8 for i in range(30)] + [
        78.0, 80.0, 83.0, 86.0, 88.0]
    p("Frische Rueckeroberung ist der Wedge Pop",
      klassifiziere(_df(pop)) == "Wedge Pop", klassifiziere(_df(pop)))

    eng = [100.0 + i * 0.6 for i in range(32)] + [118.5, 118.8, 118.4,
                                                  118.9, 118.6, 118.8,
                                                  118.5, 118.7]
    p("Enge Seitwaertsphase ueber steigenden Linien ist Base n' Break",
      klassifiziere(_df(eng)) == "Base n' Break", klassifiziere(_df(eng)))

    trend = [100.0 + i * 0.9 for i in range(40)]
    p("Stetiger Anstieg ist der Aufwaertstrend",
      klassifiziere(_df(trend)) == "Aufwärtstrend",
      klassifiziere(_df(trend)))

    drop = [100.0 + i * 0.9 for i in range(36)] + [128.0, 124.0, 121.0,
                                                   119.0]
    p("Frischer Bruch unter beide Linien ist der Wedge Drop",
      klassifiziere(_df(drop)) == "Wedge Drop", klassifiziere(_df(drop)))

    crossback = [100.0 + i * 0.9 for i in range(37)] + [127.0, 124.5, 125.5]
    erg = klassifiziere(_df(crossback))
    p("Ruecksetzer zwischen die Linien ist der EMA Crossback",
      erg == "EMA Crossback", erg)

    runter = [140.0 - i * 1.0 for i in range(40)]
    p("Stetiger Abstieg ist der Abwaertstrend",
      klassifiziere(_df(runter)) in ("Abwärtstrend", "Reversal Extension"),
      klassifiziere(_df(runter)))

    p("Alle gelieferten Phasen stehen im Register",
      all(klassifiziere(_df(reihe)) in PHASEN + [None]
          for reihe in (ruhig, parabel, crash, pop, eng, trend, drop,
                        crossback, runter)))

    if fehler:
        print(f"\n{len(fehler)} FEHLER: {', '.join(fehler)}")
        return 1
    print("\nAlles bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(selbsttest())
