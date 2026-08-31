"""EMA Crossback: Kaufmarke am Umkehrtag des ersten Ruecksetzers an die
10er/20er-Linie nach einer frischen Rueckeroberung (Oliver Kell).

GERHARDS ENTSCHEID vom 31.08.2026 abends (Regelfrage G11): "DOCH BAUEN
UND SCHARF SCHALTEN. Aber wichtig, und das ist die Bedingung: die
Ruecksetzer-Logik gilt AUSSCHLIESSLICH fuer dieses eine Kapitel. Sie
darf nicht auf andere Strategien abfaerben, das Regelwerk bleibt sonst
ueberall auf Ausbruch."

WIE DIE KAPSELUNG EINGEHALTEN WIRD, in zwei Ebenen:
1. Strukturell: Die AUSLOESUNG bleibt ein Ausbruch. Der Detektor setzt
   die Kaufmarke auf das HOCH des Umkehrtags plus 1 Cent — der Waechter
   meldet also erst, wenn der Kurs diese Marke nach OBEN reisst, mit
   exakt derselben Riss-, Fenster- und Volumenmechanik wie bei jedem
   anderen Muster. Die Ruecksetzer-Logik steckt allein in der FINDUNG
   der Marke im Nachtscan.
2. Organisatorisch: Die gesamte Ruecksetzer-Erkennung lebt in dieser
   einen Datei. Kein anderes Modul importiert sie; pattern_scanner
   ruft nur detect_ema_crossback(df) wie jeden anderen Detektor.

DAS MUSTER (Kell, Victory in Stock Trading, 2021; Stufe 3 seines Cycle
of Price Action): Nach dem Wedge Pop — der frischen Rueckeroberung der
10er- und 20er-Exponentiallinie von unten — setzt der Kurs oft noch
einmal AN die Linien zurueck und bestaetigt sie als Unterstuetzung.
Kell verlangt dabei sichtbares, stuetzendes Kaufverhalten statt blossen
Beruehrens; hier uebersetzt als Umkehrtag (Schluss ueber der
Eroeffnung oder im oberen Drittel der Tagesspanne). Der Einstieg ueber
dem Umkehrtag-Hoch ist sein Nachkauf-Punkt mit niedrigem Risiko.

Die Schwellen sind Erstkalibrierungen (Kell nennt keine Zahlen) und
stehen in config.py; Nachmessung nach den ersten Logbuch-Wochen.

Aufruf:
  python ema_crossback.py --selbsttest
"""

import sys

from config import CFG

C = CFG["ema_crossback"]

NAME = "EMA Crossback"


def detect_ema_crossback(df):
    """Die Kaufmarke im Format der uebrigen Detektoren, oder None.

    Vier Bedingungen, alle Pflicht:
    1. WEDGE POP binnen der letzten `pop_fenster_tage`: ein Tag, an dem
       der Schluss ueber BEIDE Linien kreuzte (Vortag darunter), und
       davor eine echte Abwaertsphase (mindestens `abwaerts_mindesttage`
       der zehn Tage vor der Kreuzung mit Schluss unter beiden Linien).
    2. Der Pop haelt: Seit der Kreuzung kein Schluss unter der
       20er-Linie — sonst ist die Rueckeroberung gescheitert und es
       gibt kein Crossback-Setup, nur einen Fehlversuch.
    3. RUECKSETZER-KONTAKT in den letzten `kontakt_fenster_tage`: ein
       Tagestief beruehrt oder unterschreitet die 10er-Linie (der Kurs
       ist AN den Durchschnitten, nicht weit darueber).
    4. UMKEHRTAG ist der letzte Tag: Schluss ueber der 20er-Linie und
       Schluss ueber der Eroeffnung oder im oberen Drittel der
       Tagesspanne (das stuetzende Kaufverhalten).

    Marke: Kaufpunkt = Hoch des Umkehrtags plus 1 Cent (die Ausloesung
    bleibt ein Ausbruch, siehe Kopfkommentar). Stop = tiefstes Tief der
    Kontakt-Tage minus 1 Cent; den Zehn-Prozent-Deckel legt der Scanner
    obendrauf. Kein Kursziel, Kapitel 12 bewirtschaftet."""
    if df is None or len(df) < C["min_historie"]:
        return None
    schluss = df["close"].astype(float)
    e10 = schluss.ewm(span=10, adjust=False).mean()
    e20 = schluss.ewm(span=20, adjust=False).mean()
    n = len(df)

    # 1. Den juengsten Wedge Pop finden. Der Pop-Tag ist der ERSTE Tag
    #    ueber BEIDEN Linien; sein Vortag lag noch unter mindestens
    #    einer. Bewusst NICHT "Vortag unter beiden": Die Kreuzung
    #    verlaeuft im Normalfall gestaffelt (erst ueber die schnellere
    #    10er-, Tage spaeter ueber die 20er-Linie), und die eigentliche
    #    Rueckeroberung ist erst mit der zweiten Linie vollzogen.
    pop_i = None
    for i in range(n - 1, max(n - 1 - C["pop_fenster_tage"], 10), -1):
        ueber = (schluss.iloc[i] > e10.iloc[i]
                 and schluss.iloc[i] > e20.iloc[i])
        vortag_nicht_ueber = (schluss.iloc[i - 1] <= e10.iloc[i - 1]
                              or schluss.iloc[i - 1] <= e20.iloc[i - 1])
        if not (ueber and vortag_nicht_ueber):
            continue
        davor_unter = sum(
            1 for j in range(max(0, i - 10), i)
            if schluss.iloc[j] < e10.iloc[j]
            and schluss.iloc[j] < e20.iloc[j])
        if davor_unter >= C["abwaerts_mindesttage"]:
            pop_i = i
            break
    if pop_i is None or pop_i >= n - 1:
        return None

    # 2. Der Pop muss halten: kein Schluss unter der 20er-Linie seither.
    for j in range(pop_i + 1, n):
        if schluss.iloc[j] < e20.iloc[j]:
            return None

    # 3. Ruecksetzer-Kontakt in den letzten Tagen (nach dem Pop).
    kontakt_von = max(pop_i + 1, n - C["kontakt_fenster_tage"])
    kontakte = [j for j in range(kontakt_von, n)
                if float(df["low"].iloc[j]) <= float(e10.iloc[j])]
    if not kontakte:
        return None

    # 4. Der letzte Tag als Umkehrtag.
    o = float(df["open"].iloc[-1])
    h = float(df["high"].iloc[-1])
    t = float(df["low"].iloc[-1])
    c = float(schluss.iloc[-1])
    if c <= float(e20.iloc[-1]):
        return None
    spanne = h - t
    oberes_drittel = spanne > 0 and (c - t) / spanne >= 2 / 3
    if not (c > o or oberes_drittel):
        return None

    stop_tief = min(float(df["low"].iloc[j]) for j in kontakte)
    return {
        "strategie": NAME,
        "kaufpunkt": round(h + 0.01, 2),
        "stop": round(stop_tief - 0.01, 2),
        "ziel": None,
        "status": (f"Rücksetzer an die 10er/20er-Linie, "
                   f"{n - 1 - pop_i} Tage nach der Rückeroberung"),
    }


# ---------------------------------------------------------------------------
# Selbsttest (ohne Netz)
# ---------------------------------------------------------------------------

def _df(kurse, opens=None, highs=None, lows=None):
    import pandas as pd
    return pd.DataFrame({
        "open": opens or [k * 0.998 for k in kurse],
        "close": kurse,
        "high": highs or [k * 1.006 for k in kurse],
        "low": lows or [k * 0.994 for k in kurse],
    })


def _basisfall():
    """Abwaertsphase, Pop, Ruecksetzer an die 10er-Linie, Umkehrtag."""
    kurse = [100.0 - i * 0.9 for i in range(31)]          # klare Abwaertsphase
    kurse += [75.0, 78.0, 81.0, 83.0, 84.5, 85.5]         # Pop ueber beide Linien
    kurse += [84.0, 82.5, 83.5]                           # Ruecksetzer + Umkehr
    d = _df(kurse)
    # Der Ruecksetzer beruehrt die 10er-Linie mit dem Tagestief.
    d.loc[len(d) - 2, "low"] = 80.4
    # Umkehrtag: eroeffnet unten, schliesst oben in der Spanne.
    d.loc[len(d) - 1, "open"] = 82.6
    d.loc[len(d) - 1, "high"] = 83.9
    d.loc[len(d) - 1, "low"] = 82.3
    return d


def selbsttest() -> int:
    fehler = []

    def p(name, bedingung, zusatz=""):
        print(f"  {'ok  ' if bedingung else 'FEHL'} {name}"
              + (f" — {zusatz}" if zusatz else ""))
        if not bedingung:
            fehler.append(name)

    print("EMA Crossback, Selbsttest (ohne Netz)")

    d = _basisfall()
    res = detect_ema_crossback(d)
    p("Sauberer Fall wird erkannt", res is not None)
    if res:
        p("Kaufpunkt liegt ueber dem Umkehrtag-Hoch (Ausloesung bleibt "
          "Ausbruch)", res["kaufpunkt"] == round(
              float(d["high"].iloc[-1]) + 0.01, 2), res["kaufpunkt"])
        p("Stop unter dem Kontakt-Tief", res["stop"] < 80.4, res["stop"])
        p("Status nennt die Rueckeroberung",
          "Rückeroberung" in res["status"])

    p("Zu kurze Historie liefert None",
      detect_ema_crossback(_df([100.0] * 20)) is None)

    trend = [100.0 + i * 0.9 for i in range(40)]
    p("Etablierter Trend OHNE frischen Pop liefert None (kein Abfaerben "
      "auf gewoehnliche Ruecksetzer)",
      detect_ema_crossback(_df(trend)) is None)

    gescheitert = _basisfall()
    gescheitert.loc[len(gescheitert) - 2, "close"] = 76.0
    gescheitert.loc[len(gescheitert) - 2, "low"] = 75.5
    p("Schluss unter der 20er-Linie nach dem Pop liefert None",
      detect_ema_crossback(gescheitert) is None)

    ohne_kontakt = _basisfall()
    ohne_kontakt.loc[len(ohne_kontakt) - 2, "low"] = 83.2
    p("Ohne Linien-Kontakt liefert None",
      detect_ema_crossback(ohne_kontakt) is None)

    schwach = _basisfall()
    schwach.loc[len(schwach) - 1, "open"] = 83.8
    schwach.loc[len(schwach) - 1, "close"] = 82.4
    schwach.loc[len(schwach) - 1, "low"] = 82.3
    schwach.loc[len(schwach) - 1, "high"] = 83.9
    p("Ohne Umkehrtag (schwacher Schluss) liefert None",
      detect_ema_crossback(schwach) is None)

    if fehler:
        print(f"\n{len(fehler)} FEHLER: {', '.join(fehler)}")
        return 1
    print("\nAlles bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(selbsttest())
