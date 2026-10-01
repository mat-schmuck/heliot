#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
INSIDER-KAUF-SCANNER — Bewertungslogik (Gerhards Kapitel vom 14.08.2026)
=========================================================================
Erkennt bedeutsame Insider-Kaeufe (SEC Form 4, Transaktionscode "P" =
echter Kauf am freien Markt, NICHT Zuteilung oder Optionsausuebung) ueber
den GESAMTEN US-Markt, ab 700 Mio $ Marktkapitalisierung (Gerhard,
01.10.2026, Antwort 4: einheitlich mit allen anderen Berichten; bis dahin
300 Mio $).

Eigenstaendiges Kapitel, kein Zusatz zu bestehenden Mustern. Diese Datei
ist die reine Rechnung und braucht kein Netz; die Datenbeschaffung steht
in insider_edgar.py.

ZWEI UNABHAENGIGE PFADE, jeder fuer sich ausreichend (Gerhards Entwurf,
Begruendung woertlich uebernommen):

  PFAD A, GROESSE: EIN einzelner Kauf reicht, wenn er gross genug ist —
  Kaufwert >= 5 Mio $ (Gerhard, 30.09.2026 abends, Antwort 9). Bis dahin
  galt min(5 % der Marktkap, 25 Mio $).

  PFAD B, CLUSTER: Mindestens 3 VERSCHIEDENE Insider kaufen innerhalb von
  14 Tagen, jeder fuer sich >= 250.000 $ (Antwort 9). Bis dahin 2 % der
  Marktkap je Person in 10 Handelstagen. Mehrere Kaeufe desselben
  Insiders werden addiert; die Einzelschwelle ist niedriger als bei Pfad
  A, weil hier die Anzahl das Signal traegt.

  "Die alten Schwellen (25 Millionen bzw. 2 % des Boersenwerts je Person)
  entfallen." Nur Kaeufe, keine Verkaeufe (Antwort 10).

  Beide zugleich = staerkste Kategorie.

WAS ICH GEGENUEBER SEINEM ENTWURF GEAENDERT HABE
  1. Die Parameter stehen in config.py und NUR dort, wie im ganzen
     System. Sein CFG_INSIDER bleibt als Vorgabe stehen, damit die
     Modulprobe auch ohne config laeuft.
  2. Das Cluster-Fenster rechnete vom 14.08. bis 30.09.2026 in ECHTEN
     Handelstagen. Seit Gerhards Antwort 9 sind es 14 Tage, also
     Kalendertage (fenster_start); wie viele Tagesindizes der Lauf dafuer
     lesen muss, rechnet fenster_handelstage() aus.
  3. status_text() und die Zeilen fuer die Meldung liegen hier, damit
     der Waechter sie nicht selbst zusammenbaut.

ALLE SCHWELLEN SIND STARTWERTE, keine gemessenen Optima — Gerhards
eigener Hinweis. Sie gehoeren mitgeschrieben und nachgeschaerft, bevor
irgendjemand darauf Geld setzt.
"""

import sys
from dataclasses import dataclass
from datetime import date, timedelta

try:
    import config
    CFG_INSIDER = config.CFG["insider"]
except Exception:                      # Modulprobe ohne config
    CFG_INSIDER = {
        "min_marktkap": 700_000_000,
        "pfad_a_dollar_min": 5_000_000,
        "pfad_b_dollar_pro_person": 250_000,
        "pfad_b_min_insider": 3,
        "cluster_fenster_kalendertage": 14,
    }


@dataclass
class InsiderKauf:
    insider: str
    wert_dollar: float
    datum: date
    transaktionscode: str = "P"        # nur "P" zaehlt
    rolle: str = ""

    def als_json(self):
        return {"insider": self.insider, "wert_dollar": self.wert_dollar,
                "datum": self.datum.isoformat(),
                "transaktionscode": self.transaktionscode, "rolle": self.rolle}

    @staticmethod
    def aus_json(d):
        return InsiderKauf(d["insider"], float(d["wert_dollar"]),
                           date.fromisoformat(d["datum"]),
                           d.get("transaktionscode", "P"), d.get("rolle", ""))


# ---------------------------------------------------------------------------
# Grundpruefungen
# ---------------------------------------------------------------------------

def firma_qualifiziert(marktkap, cfg=None):
    cfg = cfg or CFG_INSIDER
    return marktkap is not None and marktkap >= cfg["min_marktkap"]


def nur_echte_kaeufe(kaeufe):
    """Nur Transaktionscode 'P'. Zuteilungen (A), Optionsausuebungen (M),
    Schenkungen (G), Steuereinbehalte (F) und Verkaeufe (S) sind
    Verguetungsmechanik oder das Gegenteil eines Kaufsignals.

    Gemessen an einem echten Tag (13.08.2026, Stichprobe aus 1002
    Filings): S 81, M 11, A 11, P 10, F 10, G 3, C 3 — echte Kaeufe sind
    also rund jede zehnte Transaktion."""
    return [k for k in kaeufe if k.transaktionscode == "P"]


def handelstage_zurueck(stichtag, tage):
    """Das Datum, das 'tage' HANDELSTAGE vor dem Stichtag liegt.

    Gerhards Entwurf naeherte das mit 1,4 Kalendertagen je Handelstag an.
    Das geht bei einem langen Wochenende oder einem Feiertag daneben, und
    zwar immer in dieselbe Richtung: Das Fenster wird zu kurz und ein
    Cluster faellt auseinander. Hier wird schlicht rueckwaerts gezaehlt.
    Feiertage bleiben unberuecksichtigt — das macht das Fenster hoechstens
    ein wenig zu lang, und das ist die harmlose Richtung."""
    d = stichtag
    uebrig = tage
    while uebrig > 0:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            uebrig -= 1
    return d


def fenster_start(stichtag, cfg=None):
    """Der erste Tag des Cluster-Fensters: "innerhalb von 14 Tagen" (Gerhard,
    30.09.2026 abends, Antwort 9), gerechnet in Kalendertagen vor dem
    Stichtag."""
    cfg = cfg or CFG_INSIDER
    return stichtag - timedelta(days=int(cfg["cluster_fenster_kalendertage"]))


def fenster_handelstage(cfg=None) -> int:
    """Wie viele Handelstage das Fenster hoechstens umfasst, den Stichtag
    eingeschlossen: so viele Tagesindizes muss ein Lauf lesen, damit Pfad B
    das ganze Fenster sieht. Bei 14 Kalendertagen sind es 11."""
    cfg = cfg or CFG_INSIDER
    kt = int(cfg["cluster_fenster_kalendertage"])
    return kt // 7 * 5 + min(kt % 7, 5) + 1


def kaeufe_im_zeitfenster(kaeufe, stichtag, cfg=None):
    start = fenster_start(stichtag, cfg)
    return [k for k in kaeufe if start <= k.datum <= stichtag]


# ---------------------------------------------------------------------------
# Pfad A — Groesse
# ---------------------------------------------------------------------------

def pfad_a_schwelle(marktkap, cfg=None):
    """Der Schwellenwert in Dollar: seit 01.10.2026 ein fester Betrag
    (Antwort 9), unabhaengig vom Boersenwert."""
    cfg = cfg or CFG_INSIDER
    return float(cfg["pfad_a_dollar_min"])


def pruefe_pfad_a(kaeufe, marktkap, cfg=None):
    """Rueckgabe: (erfuellt, groesster_kauf, schwelle)."""
    cfg = cfg or CFG_INSIDER
    schwelle = pfad_a_schwelle(marktkap, cfg)
    echte = nur_echte_kaeufe(kaeufe)
    if not echte:
        return False, None, schwelle
    groesster = max(echte, key=lambda k: k.wert_dollar)
    return groesster.wert_dollar >= schwelle, groesster, schwelle


# ---------------------------------------------------------------------------
# Pfad B — Cluster
# ---------------------------------------------------------------------------

def pruefe_pfad_b(kaeufe, marktkap, cfg=None):
    """Rueckgabe: (erfuellt, {insider: summe}, schwelle_pro_person).

    Mehrere Kaeufe desselben Insiders werden addiert — er zaehlt als EINE
    Person mit der Summe seiner Kaeufe."""
    cfg = cfg or CFG_INSIDER
    schwelle = float(cfg["pfad_b_dollar_pro_person"])
    summe = {}
    for k in nur_echte_kaeufe(kaeufe):
        summe[k.insider] = summe.get(k.insider, 0.0) + k.wert_dollar
    qualifiziert = {n: s for n, s in summe.items() if s >= schwelle}
    return len(qualifiziert) >= cfg["pfad_b_min_insider"], qualifiziert, schwelle


# ---------------------------------------------------------------------------
# Beides zusammen
# ---------------------------------------------------------------------------

def pruefe_insider_signal(kaeufe, marktkap, stichtag=None, cfg=None):
    """Rueckgabe: dict mit status ('firma_zu_klein', 'kein_signal',
    'pfad_a', 'pfad_b', 'beide') und den Einzelheiten."""
    cfg = cfg or CFG_INSIDER
    if not firma_qualifiziert(marktkap, cfg):
        return {"status": "firma_zu_klein", "marktkap": marktkap}

    stichtag = stichtag or (max((k.datum for k in kaeufe), default=None)
                            or date.today())
    im_fenster = kaeufe_im_zeitfenster(kaeufe, stichtag, cfg)
    a_ok, a_kauf, a_schwelle = pruefe_pfad_a(im_fenster, marktkap, cfg)
    b_ok, b_insider, b_schwelle = pruefe_pfad_b(im_fenster, marktkap, cfg)

    status = ("beide" if a_ok and b_ok else "pfad_a" if a_ok
              else "pfad_b" if b_ok else "kein_signal")
    return {"status": status, "marktkap": marktkap, "stichtag": stichtag,
            "pfad_a": {"erfuellt": a_ok, "groesster_kauf": a_kauf,
                       "schwelle_dollar": a_schwelle},
            "pfad_b": {"erfuellt": b_ok, "qualifizierte_insider": b_insider,
                       "schwelle_dollar": b_schwelle}}


# ---------------------------------------------------------------------------
# Meldung
# ---------------------------------------------------------------------------

STATUS_TEXT = {"pfad_a": "Großkauf", "pfad_b": "Insider-Cluster",
               "beide": "Großkauf und Cluster"}


def _geld(betrag):
    """Betraege in Worten, die man vorgelesen versteht: '25,0 Mio $'
    statt '25000000'. Beistrich als Dezimalzeichen, kein Tausenderpunkt —
    eine Ziffernwueste liest kein Screenreader brauchbar vor."""
    if betrag is None:
        return "unbekannt"
    if betrag >= 1e9:
        return f"{betrag / 1e9:.1f} Mrd $".replace(".", ",")
    if betrag >= 1e6:
        return f"{betrag / 1e6:.1f} Mio $".replace(".", ",")
    return f"{betrag / 1e3:.0f} Tsd $"


def meldungszeilen(ticker, signal, firma="", rollen=None):
    """Die Meldung als Liste von Zeilen, nach den Regeln des Systems:
    Strichpunkt zwischen verschiedenen Angaben, Beistrich innerhalb
    zusammengehoeriger, kein Gedankenstrich."""
    rollen = rollen or {}
    kopf = f"{ticker} ({firma})" if firma else ticker
    zeilen = [f"{kopf}; {STATUS_TEXT[signal['status']]}; "
              f"Marktwert {_geld(signal['marktkap'])}"]
    if signal["pfad_a"]["erfuellt"]:
        k = signal["pfad_a"]["groesster_kauf"]
        rolle = rollen.get(k.insider) or k.rolle
        wer = f"{k.insider}, {rolle}" if rolle else k.insider
        zeilen.append(f"Größter Einzelkauf {_geld(k.wert_dollar)} am "
                      f"{k.datum:%d.%m.}; {wer}")
    if signal["pfad_b"]["erfuellt"]:
        leute = sorted(signal["pfad_b"]["qualifizierte_insider"].items(),
                       key=lambda x: -x[1])
        zeilen.append(f"{len(leute)} Insider über der Schwelle von "
                      f"{_geld(signal['pfad_b']['schwelle_dollar'])}:")
        for name, summe in leute:
            rolle = rollen.get(name, "")
            zeilen.append(f"  {name}" + (f", {rolle}" if rolle else "")
                          + f"; {_geld(summe)}")
    return zeilen


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

def selbsttest() -> int:
    fehler = []

    def p(name, bedingung, zusatz=""):
        print(f"  {'ok  ' if bedingung else 'FEHL'} {name}"
              + (f" — {zusatz}" if zusatz else ""))
        if not bedingung:
            fehler.append(name)

    heute = date(2026, 8, 10)          # ein Montag
    MRD = 1_000_000_000

    # --- Gerhards neun Testfaelle, in der Sache unveraendert ---
    r = pruefe_insider_signal([InsiderKauf("CEO", 50_000_000, heute)],
                              marktkap=100_000_000)
    p("Firma unter 700 Mio wird gar nicht bewertet",
      r["status"] == "firma_zu_klein", r["status"])

    # SEIT 01.10.2026 Gerhards neue Schwellen (Antwort 9): A ab 5 Mio Dollar,
    # B drei Insider in 14 Tagen je ab 250.000 Dollar.
    r = pruefe_insider_signal([InsiderKauf("CEO", 5_000_000, heute)],
                              marktkap=MRD)
    p("Ein Kauf von genau 5 Mio ergibt Pfad A", r["status"] == "pfad_a")
    p("Die Schwelle von Pfad A ist fest 5 Mio, unabhängig vom Börsenwert",
      r["pfad_a"]["schwelle_dollar"] == 5_000_000
      and pruefe_insider_signal([InsiderKauf("CEO", 5_000_000, heute)],
                                marktkap=500 * MRD)["status"] == "pfad_a",
      r["pfad_a"]["schwelle_dollar"])

    r = pruefe_insider_signal([InsiderKauf("CEO", 4_999_999, heute)],
                              marktkap=MRD)
    p("Ein Kauf knapp unter 5 Mio bleibt unauffällig",
      r["status"] == "kein_signal")

    cluster = [InsiderKauf("CEO", 300_000, heute - timedelta(days=1)),
               InsiderKauf("CFO", 260_000, heute - timedelta(days=3)),
               InsiderKauf("Direktor X", 250_000, heute)]
    r = pruefe_insider_signal(cluster, marktkap=MRD, stichtag=heute)
    p("Drei Insider je ab 250.000 Dollar ergeben Pfad B",
      r["status"] == "pfad_b" and r["pfad_b"]["schwelle_dollar"] == 250_000, r["status"])
    knapp = cluster[:2] + [InsiderKauf("Direktor X", 249_999, heute)]
    p("Einer knapp unter 250.000 Dollar: kein Cluster",
      pruefe_insider_signal(knapp, marktkap=MRD, stichtag=heute)["status"] == "kein_signal")
    p("Kein Einzelkauf erreicht dabei Pfad A",
      not r["pfad_a"]["erfuellt"])

    r = pruefe_insider_signal(cluster[:2], marktkap=MRD, stichtag=heute)
    p("Zwei Insider reichen bewusst nicht", r["status"] == "kein_signal")

    beide = [InsiderKauf("CEO", 100_000_000, heute)] + cluster[1:]
    r = pruefe_insider_signal(beide, marktkap=MRD, stichtag=heute)
    p("Großkauf UND Cluster ergibt die stärkste Kategorie",
      r["status"] == "beide", r["status"])

    r = pruefe_insider_signal(
        [InsiderKauf("CEO", 200_000_000, heute, transaktionscode="A")],
        marktkap=MRD, stichtag=heute)
    p("Zuteilung (Code A) ist kein Kaufsignal", r["status"] == "kein_signal")

    alt = [InsiderKauf("CEO", 300_000, heute - timedelta(days=60))] + cluster[1:]
    r = pruefe_insider_signal(alt, marktkap=MRD, stichtag=heute)
    p("Ein Kauf außerhalb des Fensters zählt nicht mit",
      r["status"] == "kein_signal")

    # --- Was bei uns dazukommt ---
    # 1. Das Fenster: 14 Kalendertage (Antwort 9). Am Rand: genau 14 Tage
    #    vor dem Stichtag zaehlt noch, 15 nicht mehr.
    p("Fensterbeginn 14 Kalendertage vor dem Stichtag",
      fenster_start(heute) == date(2026, 7, 27), fenster_start(heute))
    rand = [InsiderKauf("CEO", 300_000, heute - timedelta(days=14))] + cluster[1:]
    p("Ein Kauf genau 14 Tage vorher zählt mit",
      pruefe_insider_signal(rand, marktkap=MRD, stichtag=heute)["status"] == "pfad_b")
    raus = [InsiderKauf("CEO", 300_000, heute - timedelta(days=15))] + cluster[1:]
    p("Einer 15 Tage vorher zählt nicht mehr",
      pruefe_insider_signal(raus, marktkap=MRD, stichtag=heute)["status"] == "kein_signal")
    p("14 Kalendertage umfassen höchstens 11 Handelstage, so viele Indizes liest der Lauf",
      fenster_handelstage() == 11, fenster_handelstage())
    p("Ein Handelstag vor Montag ist der Freitag davor",
      handelstage_zurueck(date(2026, 8, 10), 1) == date(2026, 8, 7))

    # 2. Ein Insider mit MEHREREN kleinen Kaeufen zaehlt als eine Person
    #    mit der Summe (Gerhards Regel, hier ausdruecklich geprueft).
    viele = [InsiderKauf("CEO", 100_000, heute),
             InsiderKauf("CEO", 90_000, heute - timedelta(days=1)),
             InsiderKauf("CEO", 80_000, heute - timedelta(days=2)),
             InsiderKauf("CFO", 260_000, heute),
             InsiderKauf("Direktor X", 250_000, heute)]
    ok, qual, _ = pruefe_pfad_b(viele, MRD)
    p("Mehrere Käufe desselben Insiders werden addiert",
      ok and abs(qual.get("CEO", 0) - 270_000) < 1, qual.get("CEO"))

    # 3. Fehlende Marktkap darf nicht durchrutschen.
    p("Ohne Marktkapitalisierung gibt es kein Signal",
      pruefe_insider_signal([InsiderKauf("CEO", 1e9, heute)],
                            marktkap=None)["status"] == "firma_zu_klein")

    # 4. Die Meldung: Trennzeichen, kein Gedankenstrich, lesbare Betraege.
    r = pruefe_insider_signal(beide, marktkap=MRD, stichtag=heute)
    zeilen = meldungszeilen("BSPL", r, "Beispiel Corp",
                            {"CEO": "Chief Executive Officer"})
    text = "\n".join(zeilen)
    p("Meldung nennt Kürzel, Kategorie und Marktwert",
      "BSPL" in zeilen[0] and "Großkauf" in zeilen[0]
      and "Mrd" in zeilen[0], zeilen[0])
    p("Meldung enthält keinen Gedankenstrich",
      "—" not in text and "–" not in text)
    p("Beträge stehen in Millionen statt als Ziffernwüste",
      "100,0 Mio $" in text, [z for z in zeilen if "Einzelkauf" in z])
    p("Die Rolle des Käufers steht dabei",
      "Chief Executive Officer" in text)

    print("\n" + ("Alles bestanden." if not fehler
                  else f"{len(fehler)} FEHLER: " + ", ".join(fehler)))
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(selbsttest())
