#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DIE SECHS ALARM-MUSTER (Gerhard, 22.09.2026, Antworten O1 bis O10)
==================================================================
Gerhards Dokument vom 20.09.2026 nennt sechs seiner vierzehn Chartmuster
ausdruecklich "ALARM / STRATEGIE, pusht aktiv, sobald das Muster zuschlaegt":
A Three Weeks Tight, B Inside Day, D Pocket Pivot, L IPO Base, N Shakeout plus
drei und S Wick Play. Am 22.09.2026 hat er die Regeln dazu beantwortet; jede
steht hier an einer einzigen Stelle.

O1, EIGENER WEG: Die Alarm-Muster laufen NEBEN den bestehenden Strategien, mit
eigenen Kaufpunkten und eigenen Meldungen. Sie kommen nicht in die Rangfolge
des Nachtscans (pattern_scanner.PRIORITY) und verdraengen deshalb nie einen
bestehenden Kaufpunkt; die Mappe kaufpunkte_aktuell.xlsx bleibt, wie sie ist.
Ihre Kaufpunkte stehen in einer EIGENEN Datei (DATEI), die der Nachtscan
schreibt und der Waechter liest.

O2, UMFANG: nur die Aktien der beiden Wochenlisten und die einzeln
ueberwachten (listen.py). Ueber den ganzen Markt waeren es Hunderte Meldungen
am Tag; der Inside Day allein traf am 21.09.2026 1.039 von 5.349 Aktien.

O3, WANN: Der Nachtscan rechnet den Kaufpunkt aus dem Muster, der Waechter
meldet im Handel, sobald der Kurs ihn ueberschreitet. Genau wie bei den
bestehenden Strategien.

O4, POCKET PIVOT: erst am Folgetag, ueber dem Hoch des Pivot-Tages. Am Tag
selbst muesste der Waechter das Volumen hochrechnen und mit dem groessten
Abwaertstag der zehn Tage davor vergleichen; so eine Hochrechnung kann bis zum
Schluss kippen.

O5, MELDEREGELN: dieselben wie bei den bestehenden Strategien (Volumen ueber
dem 50-Tage-Schnitt, hochgerechnet ueber die F(t)-Kurve; bis 5 Prozent ueber
dem Einstieg, darueber uebersprungen; Totzone; je Muster einmal in der Woche).
Deshalb laufen die Alarm-Kaufpunkte im Waechter durch dieselbe Pruefung wie
jeder andere Kaufpunkt. Bei Three Weeks Tight sind es 40 Prozent ueber dem
Schnitt (IBD nennt diese Groessenordnung fuer den Ausbruchstag).

O6, INSIDE DAY: NUR die Fassung mit drei steigenden Tagen davor meldet.
Gerhards Antwort woertlich: "nur die Fassung mit drei steigenden Tagen davor
soll melden". Jeder Inside Day steht weiterhin im Scanner, aber ohne diese
Vorbedingung loest er keine Meldung aus; gemessen an der Wochenliste waeren es
sonst rund fuenf Meldungen am Tag statt rund einer.

O7, EINSTIEG BEIM INSIDE DAY: Der enge Einstieg ueber dem Hoch des Inside Day
loest aus, weil sein Stop naeher liegt; der konservative ueber dem Hoch des
Vortags steht in derselben Meldung daneben.

O8, SHAKEOUT PLUS DREI: Der Aufschlag von 10 Prozent loest aus, die 5 Prozent
stehen daneben.

O9, STOPS: Der Stop kommt aus dem Muster und traegt den Zehn-Prozent-Deckel
(chartmuster rechnet ihn schon so). Fuer Kaeufe aus diesen Mustern gelten
dieselben Ausstiegsregeln wie fuer die bestehenden Strategien.

O10, KEIN ALARM IN DER HANDELS-APP: Die Meldungen kommen vorerst NUR als
Meldung. Deshalb tragen sie die Vorsilbe INFORMATION, nennen den Einstieg
nicht "Kaufpunkt" und werden ohne die Klick-Adresse gesendet, aus der die
Handels-App eine Order baut. Erst wenn das Trigger-Logbuch nach einigen Wochen
zeigt, wie die Muster laufen, wird daraus ein Alarm.

Aufruf:
    python alarm_muster.py --selbsttest
"""

import argparse
import json
import os
import sys

# Die sechs Muster in Gerhards Reihenfolge (A, B, D, L, N, S), je mit dem
# Namen, der in Meldung, Logbuch und Volumentabelle steht.
NAMEN = {
    "a": "Three Weeks Tight",
    "b": "Inside Day",
    "d": "Pocket Pivot",
    "l": "IPO Base",
    "n": "Shakeout plus drei",
    "s": "Wick Play",
}

# O5: Bei Three Weeks Tight nennt Gerhards Quelle 40 Prozent ueber dem Schnitt
# am Ausbruchstag; alle uebrigen nehmen die Standard-Huerde des Systems. Die
# Zahlen selbst stehen in config.py (volumen.breakout_faktor*), hier steht nur,
# WELCHE gilt.
VOL_SCHLUESSEL = {
    "Three Weeks Tight": "breakout_faktor_vcp",
}
VOL_SCHLUESSEL_STANDARD = "breakout_faktor"

DATEI = "alarm_kaufpunkte.json"


def _zahl(x):
    try:
        w = float(x)
    except (TypeError, ValueError):
        return None
    return w if w == w and abs(w) != float("inf") else None


def _ja(w, spalte):
    return _zahl((w or {}).get(spalte)) == 1


def _wahr(x):
    return bool(x) and str(x).lower() not in ("false", "0", "nan", "none")


def dollar(x):
    """Ein Betrag, wie ihn die Meldungen schreiben: zwei Stellen, unter einem
    Dollar vier (dieselbe Regel wie im Scanner)."""
    w = _zahl(x)
    if w is None:
        return "unbekannt"
    return f"{w:.2f}" if abs(w) >= 1 else f"{w:.4f}"


def kaufpunkte(w):
    """Die Alarm-Kaufpunkte einer Aktie aus ihren Chartmuster-Werten
    (chartmuster.werte). Liefert eine Liste von Eintraegen mit Muster,
    Einstieg, Stop und einem Zusatzsatz fuer die Meldung; ohne Fund eine leere
    Liste. Die Reihenfolge ist Gerhards: A, B, D, L, N, S."""
    w = w or {}
    raus = []

    if _ja(w, "cm_a") and _zahl(w.get("cm_a_kp")) is not None:
        wochen = _zahl(w.get("cm_a_wochen"))
        raus.append({
            "muster": NAMEN["a"],
            "kaufpunkt": _zahl(w.get("cm_a_kp")),
            "stop": _zahl(w.get("cm_a_stop")),
            "zusatz": (f"{int(wochen)} enge Wochen" if wochen else "enge Wochen")
                      + " am Stück, Einstieg über ihrem höchsten Hoch",
        })

    # O6: nur die Fassung mit drei steigenden Tagen davor meldet.
    if _ja(w, "cm_b") and _wahr(w.get("cm_b_steigend")) and _zahl(w.get("cm_b_eng_kp")) is not None:
        kons = _zahl(w.get("cm_b_kons_kp"))
        zusatz = "drei steigende Tage, dann der Inside Day; enger Einstieg über seinem Hoch"
        if kons is not None:
            zusatz += (f", konservativ wäre über {dollar(kons)} mit Stop "
                       f"{dollar(w.get('cm_b_kons_stop'))}")
        raus.append({
            "muster": NAMEN["b"],
            "kaufpunkt": _zahl(w.get("cm_b_eng_kp")),
            "stop": _zahl(w.get("cm_b_eng_stop")),
            "zusatz": zusatz,
        })

    if _ja(w, "cm_d") and _zahl(w.get("cm_d_kp")) is not None:
        faktor = _zahl(w.get("cm_d_vol_faktor"))
        raus.append({
            "muster": NAMEN["d"],
            "kaufpunkt": _zahl(w.get("cm_d_kp")),
            "stop": _zahl(w.get("cm_d_stop")),
            "zusatz": ("Einstieg über dem Hoch des Pivot-Tages, also frühestens am Folgetag"
                       + (f"; Volumen war das {faktor:.1f}-Fache des stärksten Abwärtstags der zehn Tage davor"
                          if faktor is not None else "")),
        })

    if _ja(w, "cm_l") and _zahl(w.get("cm_l_kp")) is not None:
        seit = _zahl(w.get("cm_l_seit_wochen"))
        zusatz = "Einstieg über dem linken Hoch der ersten Basis"
        if seit is not None:
            zusatz += f", Erstnotiz vor {int(seit)} Wochen"
        if _wahr(w.get("cm_l_mantel")):
            zusatz += ", der Börsenmantel davor zählt nicht mit"
        if _wahr(w.get("cm_l_unsicher")):
            zusatz += ", die Erstnotiz ist unsicher"
        raus.append({
            "muster": NAMEN["l"],
            "kaufpunkt": _zahl(w.get("cm_l_kp")),
            "stop": _zahl(w.get("cm_l_stop")),
            "zusatz": zusatz,
        })

    # O8: die 10 Prozent loesen aus, die 5 Prozent stehen daneben.
    if _ja(w, "cm_n") and _zahl(w.get("cm_n_kp10")) is not None:
        ab, kp5 = _zahl(w.get("cm_n_abverkauf_pct")), _zahl(w.get("cm_n_kp5"))
        zusatz = "Einstieg 10 Prozent über dem Tief des Abverkaufs"
        if ab is not None:
            zusatz += f", der {ab:.1f} Prozent tief war"
        if kp5 is not None:
            zusatz += (f"; bei 5 Prozent wären es {dollar(kp5)}"
                       + (", schon erreicht" if _wahr(w.get("cm_n_kp5_erreicht")) else ""))
        raus.append({
            "muster": NAMEN["n"],
            "kaufpunkt": _zahl(w.get("cm_n_kp10")),
            "stop": _zahl(w.get("cm_n_stop")),
            "zusatz": zusatz,
        })

    if _ja(w, "cm_s") and _zahl(w.get("cm_s_kp")) is not None:
        seite, stelle = w.get("cm_s_seite"), str(w.get("cm_s_stelle") or "").strip()
        zusatz = "Einstieg über dem Hoch der Kerze"
        if seite:
            zusatz += f", Docht {seite}"
        if stelle:
            zusatz += f" an {stelle}"
        raus.append({
            "muster": NAMEN["s"],
            "kaufpunkt": _zahl(w.get("cm_s_kp")),
            "stop": _zahl(w.get("cm_s_stop")),
            "zusatz": zusatz,
        })

    return [e for e in raus if e["kaufpunkt"]]


def volumen_faktor(muster, faktoren):
    """Die Volumenhuerde eines Alarm-Musters aus der Konfiguration
    (CFG['volumen'])."""
    schluessel = VOL_SCHLUESSEL.get(muster, VOL_SCHLUESSEL_STANDARD)
    return float(faktoren.get(schluessel, faktoren.get(VOL_SCHLUESSEL_STANDARD, 1.0)))


def datei_schreiben(aktien, stand, pfad=DATEI):
    """Die Alarm-Kaufpunkte des Nachtscans ablegen. aktien ist eine Liste von
    {ticker, firma, kurs, punkte}; Aktien ohne Punkte fallen weg."""
    inhalt = {"stand": stand,
              "aktien": [a for a in aktien if a.get("punkte")]}
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(inhalt, f, ensure_ascii=False, indent=1)
    return sum(len(a["punkte"]) for a in inhalt["aktien"])


def datei_lesen(pfad=DATEI):
    """Was der letzte Nachtscan gerechnet hat, als (Stand, Liste der Aktien).
    Fehlt die Datei oder ist sie unlesbar, kommt ("", []) zurueck: Der
    Waechter laeuft dann Zeichen fuer Zeichen wie vor dem Einbau."""
    if not os.path.exists(pfad):
        return "", []
    try:
        with open(pfad, encoding="utf-8") as f:
            inhalt = json.load(f)
        return str(inhalt.get("stand") or ""), list(inhalt.get("aktien") or [])
    except Exception:  # noqa: BLE001, eine kaputte Datei darf den Waechter nie stoppen
        return "", []


def eintraege(aktien):
    """Aus den gelesenen Aktien die Eintraege, die der Waechter prueft: je
    Kaufpunkt einer, mit denselben Feldern wie ein Eintrag aus der Mappe."""
    raus = []
    for a in aktien or []:
        ticker = str(a.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        for nr, p in enumerate(a.get("punkte") or [], 1):
            kp = _zahl(p.get("kaufpunkt"))
            if kp is None:
                continue
            raus.append({
                "ticker": ticker,
                "firma": str(a.get("firma") or ""),
                "nr": nr,
                "strategie": str(p.get("muster") or "Alarm-Muster"),
                "kaufpunkt": kp,
                "kurs_scan": _zahl(a.get("kurs")),
                "stop": _zahl(p.get("stop")),
                "ziel": None,
                "zusatz": str(p.get("zusatz") or ""),
                "alarm": True,
            })
    return raus


# ---------------------------------------------------------------------------
# Die Meldung (O10: Meldung, kein Alarm in der Handels-App)
# ---------------------------------------------------------------------------

# Die Handels-App liest den Text einer Meldung und haelt sie fuer ein
# Kaufsignal, sobald darin eines dieser Woerter steht. Die Alarm-Meldungen
# vermeiden sie deshalb alle und tragen die Vorsilbe INFORMATION; gesendet
# werden sie ohne die Klick-Adresse, aus der die App eine Order baut.
KAUF_WOERTER = ("Kaufpunkt", "Einstiegsfenster", "Vol jetzt bestätigt", "Lücke", "Red-to-Green")
VORSILBE = "INFORMATION"
TITEL = "Alarm-Muster"


def meldung(t, kopf, vol_text, risiko=None):
    """Eine Alarm-Meldung als Text. kopf ist die Kopfzeile des Waechters
    (Kuerzel, Firma, Zusatz), vol_text seine Volumenzeile."""
    zeilen = [f"{VORSILBE}: {kopf}"]
    kurs, kp = _zahl(t.get("kurs")), _zahl(t.get("kaufpunkt"))
    ueber = _zahl(t.get("ueber_pct"))
    zeile = f"Einstieg über {dollar(kp)}"
    if kurs is not None:
        zeile += f", Kurs {dollar(kurs)}"
        if ueber is not None:
            zeile += f" (+{ueber:.1f}%)"
    if vol_text:
        zeile += f"; {vol_text}"
    zeilen.append(zeile)
    stop = _zahl(t.get("stop"))
    if stop is not None:
        zeilen.append(f"Stop {dollar(stop)}"
                      + (f", Risk {risiko:.1f}%" if risiko is not None else ""))
    if t.get("zusatz"):
        zeilen.append(str(t["zusatz"]))
    return "\n".join(zeilen)


def kein_kaufwort(text):
    """Enthaelt der Text ein Wort, aus dem die Handels-App ein Kaufsignal
    macht? Der Waechter prueft das vor dem Senden."""
    return [x for x in KAUF_WOERTER if x.lower() in str(text or "").lower()]


# ---------------------------------------------------------------------------
# Selbsttest (ohne Netz)
# ---------------------------------------------------------------------------

def selbsttest() -> int:
    fehler = []

    def p(name, ok, zusatz=""):
        (print if ok else print)(f"  {'ok  ' if ok else 'FEHL'} {name}" + (f"; {zusatz}" if zusatz else ""))
        if not ok:
            fehler.append(name)

    import chartmuster as cm

    leer = cm.leer()
    p("Ohne Fund keine Kaufpunkte", kaufpunkte(leer) == [] and kaufpunkte(None) == [] and kaufpunkte({}) == [])

    w = dict(leer, cm_b=1, cm_b_steigend=False, cm_b_eng_kp=41.89, cm_b_eng_stop=39.89,
             cm_b_kons_kp=42.5, cm_b_kons_stop=40.25)
    p("O6: ein Inside Day ohne drei steigende Tage meldet nicht", kaufpunkte(w) == [])
    w["cm_b_steigend"] = True
    kp = kaufpunkte(w)
    p("O6 und O7: mit drei steigenden Tagen loest der enge Einstieg aus, der konservative steht daneben",
      len(kp) == 1 and kp[0]["muster"] == "Inside Day" and kp[0]["kaufpunkt"] == 41.89
      and kp[0]["stop"] == 39.89 and "konservativ wäre über 42,50" in kp[0]["zusatz"].replace(".", ","),
      str(kp))

    w = dict(leer, cm_n=1, cm_n_kp5=31.36, cm_n_kp10=32.86, cm_n_stop=29.87, cm_n_abverkauf_pct=20.3,
             cm_n_kp5_erreicht=True)
    kp = kaufpunkte(w)
    p("O8: beim Shakeout plus drei loesen die 10 Prozent aus, die 5 stehen daneben",
      len(kp) == 1 and kp[0]["kaufpunkt"] == 32.86 and "5 Prozent wären es 31.36" in kp[0]["zusatz"]
      and "schon erreicht" in kp[0]["zusatz"], str(kp))

    w = dict(leer, cm_a=1, cm_a_kp=28.69, cm_a_stop=27.86, cm_a_wochen=3,
             cm_d=1, cm_d_kp=18.81, cm_d_stop=18.06, cm_d_vol_faktor=2.4,
             cm_l=1, cm_l_kp=40.18, cm_l_stop=36.17, cm_l_seit_wochen=11, cm_l_mantel=True,
             cm_s=1, cm_s_kp=12.6, cm_s_stop=11.34, cm_s_seite="unten", cm_s_stelle="EMA 21, Basisrand")
    kp = kaufpunkte(w)
    p("Mehrere Muster kommen in Gerhards Reihenfolge A, B, D, L, N, S",
      [e["muster"] for e in kp] == ["Three Weeks Tight", "Pocket Pivot", "IPO Base", "Wick Play"], str(
          [e["muster"] for e in kp]))
    alle = dict(w, cm_b=1, cm_b_steigend=True, cm_b_eng_kp=41.89, cm_b_eng_stop=39.89,
                cm_n=1, cm_n_kp10=32.86, cm_n_stop=29.87)
    p("Alle sechs Muster einer Aktie stehen in Gerhards Reihenfolge",
      [e["muster"] for e in kaufpunkte(alle)] == ["Three Weeks Tight", "Inside Day", "Pocket Pivot",
                                                  "IPO Base", "Shakeout plus drei", "Wick Play"],
      str([e["muster"] for e in kaufpunkte(alle)]))
    p("O4: beim Pocket Pivot steht der Folgetag in der Meldung",
      "frühestens am Folgetag" in [e for e in kp if e["muster"] == "Pocket Pivot"][0]["zusatz"])
    p("L: der Boersenmantel steht dabei",
      "Börsenmantel" in [e for e in kp if e["muster"] == "IPO Base"][0]["zusatz"])

    faktoren = {"breakout_faktor": 1.0, "breakout_faktor_vcp": 1.4}
    p("O5: Three Weeks Tight braucht 40 Prozent ueber dem Schnitt, die uebrigen den Schnitt",
      volumen_faktor("Three Weeks Tight", faktoren) == 1.4 and volumen_faktor("Inside Day", faktoren) == 1.0
      and volumen_faktor("IPO Base", faktoren) == 1.0)

    # Datei hin und zurueck
    import tempfile
    with tempfile.TemporaryDirectory() as ordner:
        pfad = os.path.join(ordner, "probe.json")
        anzahl = datei_schreiben([
            {"ticker": "aaa", "firma": "Alpha", "kurs": 41.0,
             "punkte": [{"muster": "Inside Day", "kaufpunkt": 41.89, "stop": 39.89, "zusatz": "x"}]},
            {"ticker": "BBB", "firma": "Beta", "kurs": 12.0, "punkte": []},
        ], "2026-09-22T00:07:00+02:00", pfad)
        stand, aktien = datei_lesen(pfad)
        e = eintraege(aktien)
        p("Datei: geschrieben, gelesen, Aktien ohne Punkte fallen weg",
          anzahl == 1 and stand.startswith("2026-09-22") and len(aktien) == 1 and len(e) == 1
          and e[0]["ticker"] == "AAA" and e[0]["alarm"] is True and e[0]["strategie"] == "Inside Day",
          str(e))
        p("Datei: eine fehlende Datei ist kein Fehler",
          datei_lesen(os.path.join(ordner, "gibtsnicht.json")) == ("", []))
        with open(pfad, "w", encoding="utf-8") as f:
            f.write("{kaputt")
        p("Datei: eine kaputte Datei stoppt den Waechter nicht", datei_lesen(pfad) == ("", []))

    t = {"ticker": "AAA", "kaufpunkt": 41.89, "kurs": 42.1, "ueber_pct": 0.5, "stop": 39.89,
         "zusatz": "drei steigende Tage, dann der Inside Day"}
    text = meldung(t, "AAA (Alpha); Alarm-Muster Inside Day", "Vol BESTÄTIGT, 132% des Schnitts", risiko=4.8)
    p("O10: die Meldung traegt die Vorsilbe INFORMATION und kein Wort, aus dem die Handels-App eine Order baut",
      text.startswith("INFORMATION: ") and not kein_kaufwort(text), text.replace("\n", " | "))
    p("Die Meldung nennt Einstieg, Kurs, Volumen, Stop und den Zusatz",
      "Einstieg über 41.89" in text and "Kurs 42.10 (+0.5%)" in text and "Vol BESTÄTIGT" in text
      and "Stop 39.89, Risk 4.8%" in text and "drei steigende Tage" in text, text.replace("\n", " | "))
    p("Der Waechter erkennt ein Kaufwort, falls je eines hineinruscht",
      kein_kaufwort("Kaufpunkt 12,00") == ["Kaufpunkt"])

    # DIE REGELN DER HANDELS-APP, nachgestellt (O10). Sie liest den Text einer
    # Meldung und macht daraus ein Kaufsignal, sobald eines der KAUF_WOERTER
    # darin steht; sonst ist es eine Auskunft. Die Vorsilbe INFORMATION ist
    # dieselbe, die die bestehenden Auskunfts-Meldungen tragen
    # (gewinnzonen_lauf.INFO), und die App schneidet sie ab.
    import re
    kopf = re.sub(r"^(INFORMATION|REGEL):\s*", "", text.splitlines()[0])
    treffer = re.match(r"^([A-Z][A-Z0-9.\-]{0,7})\s*(?:\(([^)]*)\))?\s*;?\s*(.*)$", kopf)
    p("O10: nach der Vorsilbe steht das Kuerzel, wie es die Handels-App erwartet",
      treffer is not None and treffer.group(1) == "AAA", kopf)
    p("O10: kein Wort der Meldung macht daraus ein Kaufsignal",
      not any(re.search(w, text, re.I) for w in KAUF_WOERTER))
    p("O10: ein Verkaufswort steht auch nicht darin",
      not re.search(r"EXIT|Exit-Linie|Stop unterschritten", text))

    print("\nAlles bestanden." if not fehler else f"\n{len(fehler)} Fehler.")
    return 1 if fehler else 0


def main():
    ap = argparse.ArgumentParser(description="Die sechs Alarm-Muster (Gerhard, 22.09.2026)")
    ap.add_argument("--selbsttest", action="store_true")
    a = ap.parse_args()
    if a.selbsttest:
        sys.exit(selbsttest())
    ap.print_help()


if __name__ == "__main__":
    main()
