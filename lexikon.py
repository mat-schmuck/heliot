# -*- coding: utf-8 -*-
"""
LEXIKON: der Reiter Lexikon der App (Gerhard, 29.09.2026, Teil 3 b)
====================================================================
"Dort wird alles erklaert, was es im System gibt: alle Kennzahlen und Felder
des Scanners, alle Strategien und Muster, alle Templates bekannter Trader,
Marktampel, Relative Staerke, Volumenformel, Stop-Regeln, Wochenlisten,
Begriffe wie Kaufpunkt, Stop, Pivot, Basis.
  * Einfaches, klares Deutsch, jeweils mit kurzem Beispiel.
  * Nach Kapiteln geordnet und durchsuchbar.
  * Mit VoiceOver sauber bedienbar: echte Ueberschriften, klare Reihenfolge,
    keine reinen Bild-Elemente."

Dazu Teil 3 a: Die Erklaerungen der Scanner-Felder stehen nicht mehr im
Scanner, sondern nur noch hier. Woher die Eintraege kommen:
  * Begriffe ohne eigenes Register: lexikon_begriffe.py, von Hand, mit den
    Schwellen aus config.py und den Modulen;
  * Strategien, Fallbacks, Alarm-Muster und weitere Kaufsignale: das Register
    einstellungen.ALARME, dasselbe wie im Regelwerk und im Reiter Einstellungen,
    samt dem Satz zur Volumenhuerde mit dem Wert, der gerade gilt;
  * die Felder des Scanners: scanner_ansicht.FELDER mit ihren Erklaerungen;
  * die Templates: scanner_ansicht.template_regelwerk();
  * die Einstellungen des Scanners: oberflaeche.SCANNER_ERKLAERUNGEN und
    SEKTOR_ERKLAERUNGEN;
  * die Beispiele: lexikon_beispiele.py.
Eine neue Strategie, ein neues Feld oder ein neues Template steht damit von
selbst im Lexikon; der Selbsttest schlaegt an, solange sein Beispiel fehlt.

Aufruf:
    python lexikon.py --selbsttest
    python lexikon.py --zeigen [Suchbegriff]
"""

import re
import sys
import unicodedata

import chartmuster as cm
import einstellungen
import lexikon_begriffe
import lexikon_beispiele as lbsp
import oberflaeche
import scanner_ansicht as sa

KAPITEL = (
    ("grundlagen", "Grundlagen"),
    ("muster", "Chartmuster und Strategien"),
    ("volumen", "Volumen und Formel"),
    ("rs", "Relative Stärke und Marktampel"),
    ("stops", "Stops und Risiko"),
    ("meldungen", "Meldungen und Berichte"),
    ("scanner", "Scanner-Einstellungen"),
    ("kennzahlen", "Scanner-Kennzahlen"),
    ("templates", "Trader-Templates"),
)
KAPITEL_NAMEN = dict(KAPITEL)

# GAESTE (Gerhard, 01.10.2026, Antwort 8): "Gaeste sehen nur die Kapitel
# Scanner-Einstellungen und Scanner-Kennzahlen. Nicht sichtbar fuer Gaeste:
# Grundlagen, Chartmuster und Strategien, Volumen und Formel, Relative Staerke
# und Marktampel, Stops und Risiko, Meldungen und Berichte, Trader-Templates.
# Das Quiz sehen Gaeste weiterhin nicht."
GAST_KAPITEL = ("scanner", "kennzahlen")


def kapitel_fuer(rolle) -> tuple:
    """Die Kapitel, die eine Rolle sieht: Gaeste nur GAST_KAPITEL, alle
    anderen alle."""
    if rolle == "gast":
        return tuple(k for k in KAPITEL if k[0] in GAST_KAPITEL)
    return KAPITEL

# Die Gruppen des Registers, die Kaufsignale sind; die Meldungen zu offenen
# Positionen und die weiteren Auskuenfte erklaeren die Begriffe selbst.
STRATEGIE_GRUPPEN = ("kauf", "ausweich", "alarm", "weitere")

# Andere Namen, unter denen ein Begriff im System vorkommt (Suche und
# Selbsttest): der Name im Scanner, wenn er vom Begriff abweicht.
AUCH = {
    "Trend Template": ("Minervini Trend Template",),
    "RS-Linie auf dem 52-Wochen-Hoch": ("RS-Linie gegen SPY auf 52-Wochen-Hoch",),
    "Red to Green": ("Red to Green am letzten Handelstag",),
    "Power-Gap": ("Gap and Go", "Lückentag"),
    "Insider-Käufe": ("Insider",),
    "Vorläufiges RS": ("Junge Titel mit vorläufigem RS mitnehmen",),
    "Welche Aktien beim Zahlentermin": ("Welche Aktien",),
    "Toleranz": ("Wie genau das Muster passen muss",),
}


def _z(x, stellen=2) -> str:
    return lexikon_begriffe._z(x, stellen)


def _pz(x) -> str:
    return lexikon_begriffe._pz(x)


def _mal(x) -> str:
    """2 wird doppelt, 3 dreimal, sonst die Zahl mit -mal."""
    return {2: "doppelt", 3: "dreimal", 4: "viermal"}.get(int(x), f"{_z(x, 1)}-mal") if float(x).is_integer() \
        else f"{_z(x, 1)}-mal"


def _muster_zusatz() -> dict:
    """Die genauen Regeln der Alarm-Muster und des Power-Gap, mit den Zahlen
    aus chartmuster.py; im Register stehen sie nur in einem Satz."""
    q, f = cm.QUELLE, cm.FESTLEGUNGEN
    cent = _z(q["aufschlag"] * 100, 0)
    return {
        "a_3wt": (f"Eng heißt: Jeder Wochenschluss liegt höchstens {_pz(q['a_eng'])} Prozent vom Schluss der Vorwoche "
                  f"entfernt; es zählen {q['a_wochen_min']} oder {q['a_wochen_max']} enge Wochen. Davor steigt die "
                  f"Aktie mindestens {_pz(f['a_anstieg_min'])} Prozent in {f['a_anstieg_wochen']} Wochen. Kaufpunkt am "
                  f"höchsten Wochenhoch der engen Wochen plus {cent} Cent, Stop am tiefsten Wochentief."),
        "a_inside": ("Der enge Einstieg liegt am Hoch des Inside Day, Stop unter seinem Tief; der konservative Einstieg "
                     "am Hoch des Vortags, Stop unter dessen Tief, steht in der Meldung daneben."),
        "a_pocket": (f"Der Pivot-Tag schließt über dem Vortag und über der SMA 50; die {f['d_basis_tage']} Handelstage "
                     f"davor schwanken höchstens {_pz(f['d_basis_tiefe_max'])} Prozent, und er liegt höchstens "
                     f"{_pz(f['d_basis_ueber_max'])} Prozent über ihrem Hoch. Einstieg über dem Hoch des Pivot-Tages, "
                     "Stop unter seinem Tief."),
        "a_ipo": (f"Frisch notiert heißt höchstens {f['l_erstnotiz_wochen_max']} Wochen nach dem ersten Kurs; Kaufpunkt "
                  f"am linken Hoch plus {cent} Cent."),
        "a_shakeout3": (f"Aus einem Hoch heißt aus dem höchsten Hoch der {f['n_hoch_tage']} Handelstage davor; scharf "
                        f"heißt mindestens {_pz(f['n_abverkauf_min'])} Prozent vom Hoch zum Tief in höchstens "
                        f"{f['n_abverkauf_tage']} Handelstagen. Es zählt nur der erste scharfe Abverkauf. Gemeldet wird "
                        f"der Einstieg {_pz(q['n_aufschlag'][1])} Prozent über dem Tief, der bei "
                        f"{_pz(q['n_aufschlag'][0])} Prozent steht daneben."),
        "a_wick": (f"Der Docht ist mindestens {_mal(f['s_docht_zu_koerper'])} so lang wie der Körper, der Körper "
                   f"höchstens {_pz(f['s_koerper_max'])} Prozent der Tagesspanne, und die Spanne mindestens so groß "
                   f"wie die durchschnittliche der {f['s_atr_tage']} Tage davor. Die markante Stelle liegt im Docht: "
                   "EMA 10, EMA 21, SMA 50, SMA 200, Hoch oder Tief der 20 Tage davor oder ein altes Hoch. Einstieg "
                   f"über dem Hoch der Kerze plus {cent} Cent."),
        "gapgo": ("Das Tief des Lückentags bleibt über dem Vortagesschluss, und der Schluss liegt im oberen Fünftel der "
                  "Tagesspanne. Der Einstieg am Folgetag ist ein Tagesgeschäft."),
    }


def _ohne_klammern(text) -> str:
    """Die Namen der Nasdaq-Branchen tragen Klammern und abgesetzte
    Bindestriche aus der Quelle; im Lexikon stehen sie mit Beistrich, wie es
    die Schreibregeln der Oberflaeche verlangen. Die Suche findet beide."""
    t = re.sub(r"\s*\(([^)]*)\)", r", \1", str(text or ""))
    return re.sub(r"\s+-\s+", ", ", t).replace(",,", ",").replace(", .", ".")


def branchen_aus_stand(stand) -> list:
    """[(Name, Erklaerung, Beispiel)] je Nasdaq-Branche, die der Scanner zum
    Abwaehlen anbietet, mit dem Satz, den frueher ihr Erklaerungsknopf zeigte
    (scanner_ansicht.branche_erklaerung); ohne Stand der Tabelle nur die, die
    ein Template abwaehlt."""
    raus = []
    zahlen = {str(e.get("gruppe")): int(e.get("aktien") or 0) for e in ((stand or {}).get("branchen") or [])
              if isinstance(e, dict) and e.get("gruppe")}
    for name in sa.branchen_in(stand):
        n = zahlen.get(name, 0)
        beispiel = (f"Im Scanner abgewählt, fallen die {n} Aktien dieser Gruppe aus den Treffern." if n > 1 else
                    "Im Scanner abgewählt, fallen ihre Aktien aus den Treffern.")
        raus.append((_ohne_klammern(name), _ohne_klammern(sa.branche_erklaerung(name, stand)), beispiel))
    return raus


def _scanner_eintraege(einst, stand=None):
    """Die Einstellungen des Scanners selbst: Teil 1, Zahlentermine, Sektoren,
    Branchen, Schnellbox, Rating, Ergebnis und Grenzen. Jeder Eintrag steht in
    einer Gruppe, damit die Ueberschriften im Kapitel eine klare Ebene haben."""
    se, bs = oberflaeche.SCANNER_ERKLAERUNGEN, lbsp.SCANNER
    tol = sa.toleranz_prozent()
    raus = []
    g1 = "Teil 1 und Grundeinstellungen"

    def neu(begriff, text, beispiel, gruppe=g1):
        raus.append(("scanner", gruppe, begriff, text, beispiel))

    namen = [n.replace("Chart-Signal: ", "") for k, n in sa.AUSWAHL if k]
    # Listen aus Namen, die selbst einen Beistrich tragen koennen, trennt
    # der Strichpunkt (Cup & Handle; Cup & Handle, Wochenbasis).
    neu("Strategie oder Chart-Signal", se["strategie"] + " Zur Wahl stehen: " + "; ".join(namen) + ".",
        bs["strategie"])
    neu("Toleranz",
        f"Streng heißt, jede Regel des Musters ist erfüllt. Mit {tol} Prozent Toleranz dürfen Schwellen in Prozent, "
        "Verhältnisse und Dauern um diesen Anteil verfehlt werden, die Lage zu gleitenden Durchschnitten um diesen "
        "Anteil der mittleren Tagesschwankung; Zählregeln, Richtungen und feste Formbedingungen bleiben streng. Ein "
        f"Treffer nur mit Toleranz kostet {sa.SC['rating']['toleranz_abzug']} Punkte beim Rating. EMA Crossback und "
        "Power-Gap haben keine Toleranzstufe.", bs["toleranz"])
    neu("Nur handelbare Aktien",
        se["handelbar"].split(". ")[0] + ". Die Grenzen: " + sa.handelbar_text().split(": ", 1)[1] + ".",
        bs["handelbar"])
    neu("Langweilige Darvas-Boxen aussortieren",
        se["langweilig"] + " Die Grenzen: " + sa.langweile_text().split(": ", 1)[1] + ".", bs["langweilig"])
    neu("Vorläufiges RS", se["rs_vorlaeufig"], bs["rs_vorlaeufig"])
    gz = "Zahlentermine"
    neu("Nach Zahlenterminen filtern", se["termine"], bs["termine"], gz)
    for key, text, _plus, _lage in sa.TERMIN_TEILE:
        neu(f"Zahlen {text}", se[f"termine_{key}"], bs[f"termine_{key}"], gz)
    neu("Auch Termine während des Handels oder ohne bekannte Tageszeit", se["termine_ohne_zeit"],
        bs["termine_ohne_zeit"], gz)
    neu("Welche Aktien beim Zahlentermin", se["termine_umfang"], bs["termine_umfang"], gz)
    for s in list(sa.SEKTOREN) + [""]:
        name = f"Sektor {sa.sektor_name(s)}" if s else sa.OHNE_SEKTOR
        neu(name, oberflaeche.SEKTOR_ERKLAERUNGEN.get(s, ""), lbsp.SEKTOREN.get(s, ""), "Sektoren")
    neu("Nasdaq-Branchen",
        "Die Branchen, in die die Nasdaq jede Aktie einordnet, etwa Semiconductors oder Biotechnology. Im Scanner "
        "lässt sich jede abwählen; Aktien ohne Branchenangabe bleiben immer drin. Manche Gruppen fassen mehrere "
        "Nasdaq-Branchen zusammen.",
        "Wer die Branche Biotechnology abwählt, sieht keine Biotechfirmen mehr in den Treffern.",
        "Nasdaq-Branchen")
    for name, text, beispiel in branchen_aus_stand(stand):
        neu(f"Branche {name}", text, beispiel, "Nasdaq-Branchen")
    g2 = "Schnellbox, Rating und Vorlagen"
    neu("Schnellbox",
        "Die häufigsten Merkmale ganz oben im Scanner, gleich unter den Templates: "
        + "; ".join(n for _s, n in sa.SCHNELLBOX) + ". Es sind dieselben Merkmale wie in Teil 2; was hier eingestellt "
        "wird, gilt dort genauso.",
        "Wer in der Schnellbox beim RS ab 90 einträgt, findet denselben Wert in Teil 2 im Block Relative Stärke.",
        g2)
    neu("Rating",
        "Ein Wert von 0 bis 100 für die Treffer einer Strategie: relative Stärke, Nähe zum Hoch, Vorlauf, "
        "Jahresspanne, Tagesspanne, Liquidität, Austrocknen des Volumens, Enge, Nachfrage und die Qualität des "
        "Musters, gewichtet je Muster. Das Rating ordnet die Treffer, ein fehlendes Muster ersetzt es nie. Die drei "
        "stärksten und die zwei schwächsten Bausteine stehen als Begründung dabei.",
        "Zwei Treffer der Darvas Box: Der mit höherem RS und engerer Box bekommt 78 Punkte, der andere 52; beim "
        "Sortieren nach Rating steht der erste oben.", g2)
    neu("Vorlagen",
        "Eigene Einstellungen des Scanners lassen sich unter einem Namen speichern und mit einem Klick wieder laden, "
        "nur im vollen Zugang. Die Templates bekannter Trader sind dagegen fest und lassen sich weder überschreiben "
        "noch löschen.",
        "Man speichert seine Einstellungen als Minervini streng und lädt sie in der nächsten Woche wieder.", g2)
    neu("Sortieren nach",
        "Die Treffer lassen sich nach dem Rating der Strategie, nach RS, nach Marktkapitalisierung, nach Kürzel oder "
        "nach jedem eingestellten Merkmal sortieren; Umsortieren braucht keinen neuen Scan.",
        "Nach einem Scan mit dem Abstand zum 52-Wochen-Hoch lässt sich danach sortieren, kleinster Wert zuerst.",
        "Ergebnis")
    neu("Dateiformat",
        "Das Ergebnis lässt sich als Datei herunterladen: " + "; ".join(x[1] for x in sa.FORMATE) + ".",
        "Für Excel auf Deutsch passt CSV mit Strichpunkt und Dezimalbeistrich.", "Ergebnis")
    neu("Übergabe an die Wochenlisten",
        "Im vollen Zugang lassen sich die Treffer eines Scans direkt als eine der Wochenlisten übergeben: als große "
        "Liste, "
        "Darvas-Liste, dritte oder vierte Liste. Die gewählte Liste wird ersetzt; im Bearbeitungsmodus lassen sich "
        "einzelne Aktien vorher abwählen. Aktiv ist sie ab dem nächsten Nachtscan.",
        "Ein Scan findet 120 Aktien; man übergibt sie als dritte Liste, und ab dem nächsten Nachtscan rechnet das "
        "System für sie alle Strategien außer der Darvas Box.", "Ergebnis")
    neu("Grenzen des Scanners", " ".join(sa.grenzen_saetze()),
        "Am Nachmittag zeigt der Scanner noch den Red to Green von gestern; den heutigen meldet der Wächter.",
        "Was der Scanner nicht kann")
    return raus


def _einheit_satz(f) -> str:
    if f.art == "ja":
        return "Ein Kontrollfeld: Angehakt bleiben nur Aktien, die das erfüllen."
    return f"Von und Bis in {f.einheit}." if f.einheit else "Von und Bis als Zahl."


def _kennung(kapitel, begriff) -> str:
    return kapitel + "_" + re.sub(r"[^a-z0-9]+", "_", _norm(begriff)).strip("_")


def eintraege(einst=None, stand=None) -> list:
    """Alle Eintraege, in der Reihenfolge der Kapitel: je Eintrag ein dict mit
    kennung, kapitel, gruppe, begriff, text, beispiel und auch (andere
    Namen). einst: die geltenden Einstellungen der App, None die Vorgaben;
    stand: der Stand der Scanner-Tabelle, aus dem die Nasdaq-Branchen kommen."""
    roh = []
    begriffe = lexikon_begriffe.begriffe(einst)
    zusatz = _muster_zusatz()
    gruppen_namen = dict(einstellungen.GRUPPEN)
    for kap, _name in KAPITEL:
        if kap == "muster":
            for g in STRATEGIE_GRUPPEN:
                for a in einstellungen.ALARME:
                    if a["gruppe"] != g:
                        continue
                    teile = [a.get("regel") or a["erklaerung"], zusatz.get(a["schluessel"], ""),
                             "" if a["schluessel"] in einstellungen.OHNE_MELDUNG
                             else einstellungen.volumen_satz(einst, a["schluessel"])]
                    roh.append((kap, gruppen_namen.get(g, ""), a["name"], " ".join(t for t in teile if t),
                                lbsp.STRATEGIEN.get(a["schluessel"], "")))
            roh += [b for b in begriffe if b[0] == kap]
        elif kap == "scanner":
            roh += _scanner_eintraege(einst, stand)
        elif kap == "kennzahlen":
            gnamen = dict(sa.GRUPPEN)
            for f in sa.FELDER:
                roh.append((kap, gnamen.get(f.gruppe, ""), f.titel, f"{f.erklaerung} {_einheit_satz(f)}",
                            lbsp.feld_beispiel(f)))
        elif kap == "templates":
            roh.append((kap, "", "Templates bekannter Trader", " ".join(sa.template_einleitung()),
                        "Wer Kell: Gappers wählt, bekommt Kurs ab 20 Dollar, Volumen ab 500.000 Stück und eine "
                        "Eröffnungslücke ab 3 Prozent angehakt, sonst nichts."))
            for t, (name, text) in zip(sa.TEMPLATES, sa.template_regelwerk()):
                roh.append((kap, "", name, text, lbsp.TEMPLATES.get(t["id"], "")))
        else:
            roh += [b for b in begriffe if b[0] == kap]
    raus, gesehen = [], set()
    for kap, gruppe, begriff, text, beispiel in roh:
        k = _kennung(kap, begriff)
        n = 2
        while k in gesehen:
            k = f"{_kennung(kap, begriff)}_{n}"
            n += 1
        gesehen.add(k)
        raus.append({"kennung": k, "kapitel": kap, "gruppe": gruppe, "begriff": begriff, "text": text,
                     "beispiel": beispiel, "auch": AUCH.get(begriff, ())})
    return raus


def je_kapitel(liste) -> dict:
    """{Kapitel: [Eintraege]} in der Reihenfolge von KAPITEL."""
    raus = {k: [] for k, _n in KAPITEL}
    for e in liste:
        raus.setdefault(e["kapitel"], []).append(e)
    return raus


# ---------------------------------------------------------------------------
# Suche
# ---------------------------------------------------------------------------

def _norm(text) -> str:
    """Kleinschreibung ohne Umlaute und Satzzeichen: Ü und Ue werden u, ß wird
    ss; so findet uebersprungen, ubersprungen und Übersprungen dasselbe."""
    t = str(text or "").casefold().replace("ß", "ss")
    t = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))
    t = t.replace("ae", "a").replace("oe", "o").replace("ue", "u")
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def suchen(liste, begriff: str) -> list:
    """Die Eintraege, die alle Woerter des Suchbegriffs enthalten, im Namen,
    in einem anderen Namen, in der Erklaerung oder im Beispiel. Vorn steht,
    was im Namen trifft: erst der genaue Name, dann der Anfang, dann ein Wort
    im Namen, zuletzt Treffer nur im Text."""
    woerter = _norm(begriff).split()
    if not woerter:
        return []
    raus = []
    for i, e in enumerate(liste):
        namen = [_norm(e["begriff"])] + [_norm(x) for x in e.get("auch") or ()]
        name_alle = " ".join(namen)
        koerper = _norm(" ".join((e["text"], e["beispiel"], e["gruppe"])))
        heuhaufen = name_alle + " " + koerper
        ohne_leer = heuhaufen.replace(" ", "")
        if not all(w in heuhaufen or w in ohne_leer for w in woerter):
            continue
        frage = " ".join(woerter)
        if frage in namen:
            rang = 0
        elif any(n.startswith(frage) for n in namen):
            rang = 1
        elif all(w in name_alle for w in woerter):
            rang = 2
        else:
            rang = 3
        raus.append((rang, i, e))
    raus.sort(key=lambda x: (x[0], x[1]))
    return [e for _r, _i, e in raus]


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

def _gleich(a, b) -> bool:
    if isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)):
        return len(a) == len(b) and all(_gleich(x, y) for x, y in zip(a, b))
    try:
        return abs(float(a) - float(b)) < 1e-9
    except (TypeError, ValueError):
        return a == b


def beispiel_schwellen() -> list:
    """(Name, Ist, Soll): die Werte, auf denen die Beispiele von Lexikon und
    Quiz beruhen. Aendert sich einer, stimmen Zahlen in den Beispielen nicht
    mehr; der Selbsttest schlaegt dann an, und die Beispiele gehoeren
    nachgerechnet (die Erklaerungen selbst lesen die Werte ohnehin aus dem
    Code)."""
    from config import CFG
    import gapup_bericht
    import gewinn_zonen as gz
    import pattern_scanner as ps
    ex, b, g = CFG["exit"], CFG["betrieb"], gz.CFG_GEWINN
    q, f, hb = cm.QUELLE, cm.FESTLEGUNGEN, sa.SC["handelbar"]
    return [
        ("Zehn-Prozent-Deckel", ex["stop_deckel_pct"], 0.10),
        ("Einstiegsfenster", b["nachlauf_grenze"], 0.05),
        ("Wochen-Sperre", b["melde_neu_ab"], 0.02),
        ("Stop auf Einstand", (ex["breakeven_ab_r"], ex["breakeven_ab_pct"]), (2.0, 0.10)),
        ("Teilverkauf", (ex["teilverkauf_ab_pct"], ex["teilverkauf_anteil"]), (0.20, 0.50)),
        ("Halteregel", (ex["schnellstarter_pct"], ex["schnellstarter_tage"], ex["halteregel_tage"]), (0.20, 15, 40)),
        ("Nachzieh-Linie", (ex["trail_ma_schnell"], ex["trail_ma_langsam"], ex["trail_ruhig_atr_max_pct"]),
         (21, 50, 2.5)),
        ("Gewinnzonen", (g["zone_leicht_max_r"], g["zone_mittel_min_pct"], g["zone_stark_min_r"]), (2.0, 0.20, 3.0)),
        ("Klimax", (g["klimax_pct_min"], g["ma200_abstand_min"], g["ma200_abstand_max"]), (0.25, 0.70, 1.00)),
        ("Zeitdeckel", (g["zeitdeckel_tage_zahlen"], g["zeitdeckel_monate_insider"], g["zeitdeckel_monate_standard"]),
         (60, 6, 12)),
        ("Volumenhuerden der Vorgabe", (einstellungen.volumen_vorgabe("rechteck"), einstellungen.volumen_vorgabe(
            "fb_52w"), einstellungen.volumen_vorgabe("gapgo"), einstellungen.ruecksetzer_vorgabe("earnings")),
         (60, 100, 200, -50)),
        ("Toleranz des Scanners", (sa.SC["toleranz"], sa.SC["rating"]["toleranz_abzug"]), (0.05, 5)),
        ("Nur handelbare Aktien", (hb["kurs_min"], hb["dollarvolumen_min"], hb["historie_min_tage"]),
         (10.0, 10_000_000.0, 252)),
        ("Langweilige Darvas-Boxen", sa.SC["langeweile"]["jahresspanne_min"], 2.0),
        ("Cup & Handle Tiefe", (ps.CFG["cup_min_depth"], ps.CFG["cup_max_depth"]), (0.12, 0.50)),
        ("Aufschlag der Chartmuster", q["aufschlag"], 0.1),
        ("Three Weeks Tight", (q["a_eng"], q["a_wochen_min"], q["a_wochen_max"]), (0.015, 3, 4)),
        ("Shakeout plus drei", tuple(q["n_aufschlag"]), (0.05, 0.1)),
        ("IPO Base", (q["l_tiefe_min"], q["l_tiefe_max"]), (0.2, 0.5)),
        ("Flat Base", (q["g_tiefe_max"], q["g_anstieg_min"]), (0.15, 0.2)),
        ("Shakeout am EMA 10", f["t_unterschreitung_max"], 0.03),
        ("Wick Play", (f["s_docht_zu_koerper"], f["s_koerper_max"]), (2.0, 0.3)),
        ("Green Line Breakout", q["q_tage_ohne_hoch"], 63),
        ("Episodic Pivot", (q["v_luecke"], q["v_vol_faktor"], q["v_abstand_200"]), (0.1, 3.0, 0.15)),
        ("Gap-Up-Bericht", (gapup_bericht.GAP_MIN_PCT, gapup_bericht.VOL_MIN_ANTEIL, gapup_bericht.KURS_MIN,
                            gapup_bericht.MARKTKAP_MIN_MRD), (5.0, 0.05, 15.0, 0.7)),
        ("Sektor-Radar", (CFG["sektor_radar"]["ma_tage"], CFG["sektor_radar"]["vol_pct_schwelle"]), (10, 50.0)),
        ("Zahlen-Karenz", CFG["zahlen_karenz"]["handelstage"], 2),
        # Dazu die Werte, gegen die Antworten im Quiz stehen: Aenderte sich einer,
        # koennte eine falsche Antwort richtig werden (Alle 60 Sekunden und Jede
        # Minute, Ab 6 und Ab 1).
        ("Pruef-Takt des Waechters", b["pruef_takt_sekunden"], 2),
        ("Power-Gap", (CFG["gap_and_go"]["gap_min"], CFG["gap_and_go"]["einstieg_grenze"]), (0.07, 0.03)),
        ("Distribution Days und Follow-through Day",
         (CFG["marktbreite"]["dd_verlust_pct"], CFG["marktbreite"]["dd_druck_ab"], CFG["marktbreite"]["dd_korrektur_ab"],
          CFG["marktbreite"]["ftd_ab_tag"], CFG["marktbreite"]["ftd_gewinn_pct"]), (0.2, 4, 6, 4, 1.25)),
        ("Trend Template RS", ps.CFG["tt_rs_min"], 70),
    ]


VERBOTEN = re.compile(r"[()\u2013\u2014|\[\]{}]")
DATUM = re.compile(r"\b\d{1,2}\.\d{1,2}\.(?:\d{2,4})?\b")


def textfehler(text) -> list:
    """Was in einem Text des Lexikons nicht stehen darf: Klammern ausser in
    F(t), Gedankenstrich, senkrechter Strich, Namen, ein Datum."""
    t = str(text or "").replace("F(t)", "")
    fehler = []
    if VERBOTEN.search(t):
        fehler.append("Zeichen " + repr(VERBOTEN.search(t).group(0)))
    if " - " in t:
        fehler.append("Gedankenstrich als Bindestrich")
    for name in ("Gerhard", "Mathias"):
        if name in t:
            fehler.append("Name " + name)
    if DATUM.search(t):
        fehler.append("Datum " + DATUM.search(t).group(0))
    return fehler


def selbsttest() -> int:
    fehler = []

    def p(name, ok, info=""):
        print(("  OK    " if ok else "  FEHLER ") + name + (f" ({info})" if info and not ok else ""))
        if not ok:
            fehler.append(name)

    print("lexikon.py, Selbsttest")
    liste = eintraege()
    kap = je_kapitel(liste)
    p("Jedes Kapitel hat Eintraege", all(kap[k] for k, _n in KAPITEL),
      ", ".join(k for k, _n in KAPITEL if not kap[k]))
    p("Kennungen eindeutig", len({e["kennung"] for e in liste}) == len(liste))
    leer = [e["begriff"] for e in liste if not e["text"].strip() or not e["beispiel"].strip()]
    p("Jeder Eintrag hat Erklaerung und Beispiel", not leer, ", ".join(leer[:10]))
    schlecht = [(e["begriff"], f) for e in liste for f in textfehler(e["begriff"] + " " + e["text"] + " "
                                                                      + e["beispiel"])]
    p("Keine Klammern ausser F(t), kein Gedankenstrich, kein senkrechter Strich, keine Namen, kein Datum",
      not schlecht, str(schlecht[:6]))
    # Vollstaendigkeit gegen die Register
    ohne = [f.schluessel for f in sa.FELDER if not lbsp.feld_beispiel(f)]
    p(f"Jedes der {len(sa.FELDER)} Felder hat ein Beispiel", not ohne, ", ".join(ohne))
    fremd = sorted(set(lbsp.FELDER) - {f.schluessel for f in sa.FELDER})
    p("Kein Beispiel fuer ein Feld, das es nicht gibt", not fremd, ", ".join(fremd))
    strat = [a["schluessel"] for a in einstellungen.ALARME if a["gruppe"] in STRATEGIE_GRUPPEN]
    p("Jede Strategie des Registers hat ein Beispiel", all(lbsp.STRATEGIEN.get(s) for s in strat),
      ", ".join(s for s in strat if not lbsp.STRATEGIEN.get(s)))
    p("Kein Beispiel fuer eine Strategie, die es nicht gibt", not set(lbsp.STRATEGIEN) - set(strat),
      ", ".join(sorted(set(lbsp.STRATEGIEN) - set(strat))))
    tids = [t["id"] for t in sa.TEMPLATES]
    p(f"Jedes der {len(tids)} Templates hat ein Beispiel", all(lbsp.TEMPLATES.get(t) for t in tids),
      ", ".join(t for t in tids if not lbsp.TEMPLATES.get(t)))
    p("Kein Beispiel fuer ein Template, das es nicht gibt", not set(lbsp.TEMPLATES) - set(tids))
    p("Jede Erklaerung des Scanners hat ihr Beispiel",
      all(k in lbsp.SCANNER for k in oberflaeche.SCANNER_ERKLAERUNGEN),
      ", ".join(k for k in oberflaeche.SCANNER_ERKLAERUNGEN if k not in lbsp.SCANNER))
    p("Jeder Sektor hat sein Beispiel", all(s in lbsp.SEKTOREN for s in oberflaeche.SEKTOR_ERKLAERUNGEN))
    namen = {_norm(e["begriff"]) for e in liste} | {_norm(x) for e in liste for x in e["auch"]}
    scanner_namen = [n.replace("Chart-Signal: ", "") for k, n in sa.AUSWAHL if k]
    p("Jede Strategie und jedes Chart-Signal des Scanners steht im Lexikon",
      all(_norm(n) in namen for n in scanner_namen), ", ".join(n for n in scanner_namen if _norm(n) not in namen))
    alle_texte = " ".join(e["begriff"] + " " + e["text"] for e in liste)
    for wort in ("Kaufpunkt", "Stop", "Pivot", "Basis", "Marktampel", "Wochenlisten", "F(t)-Kurve",
                 "Relative Stärke", "Volumenhürden", "Zehn-Prozent-Deckel"):
        p(f"Gerhards Pflichtbegriff {wort} hat einen Eintrag oder steht darin", wort in alle_texte)
    import berichte
    p("Jede Berichtsart steht im Lexikon", all(n in alle_texte for _k, n in berichte.ARTEN),
      ", ".join(n for _k, n in berichte.ARTEN if n not in alle_texte))
    # Die Rechtschreibung der Revisionen (berichtigt 01.10.2026)
    p("Keine Revision fuer das laufendes Quartal", "für das laufendes" not in alle_texte
      and "für das nächstes" not in alle_texte)
    # Suche
    s = suchen(liste, "Kaufpunkt")
    p("Suche: Kaufpunkt findet den Eintrag Kaufpunkt zuerst", bool(s) and s[0]["begriff"] == "Kaufpunkt",
      s[0]["begriff"] if s else "nichts")
    for frage, erwartet in (("uebersprungen", "Übersprungen"), ("ubersprungen", "Übersprungen"),
                            ("F(t)", "F(t)-Kurve"), ("gap up", "Gap-Up-Bericht"), ("gapup", "Gap-Up-Bericht"),
                            ("minervini trend template", "Trend Template"), ("Inside Day", "Inside Day")):
        s = suchen(liste, frage)
        p(f"Suche: {frage} findet {erwartet} unter den ersten drei",
          any(e["begriff"] == erwartet for e in s[:3]), ", ".join(e["begriff"] for e in s[:3]))
    p("Suche: leerer Begriff findet nichts", suchen(liste, "  ") == [])
    p("Suche: Unsinn findet nichts", suchen(liste, "qxzvw") == [])
    # Die Volumenhuerde folgt den Einstellungen
    eigen = eintraege({"volumen_ueber": {"rechteck": 75}})
    rt = next(e for e in eigen if e["begriff"] == "Rectangle Top")
    p("Die Volumenhuerde im Lexikon folgt den Einstellungen", "plus 75 Prozent" in rt["text"], rt["text"][-160:])
    import gewinn_zonen as gz
    p("Klimax: die Grenzen im Text sind die, die der Code prueft, samt Spielraum nach oben",
      gz.klimax_zeichen_4_ma200_abstand(2.29, 1.0)[0] and not gz.klimax_zeichen_4_ma200_abstand(2.31, 1.0)[0]
      and not gz.klimax_zeichen_4_ma200_abstand(1.69, 1.0)[0]
      and gz.klimax_zeichen_1_klimaxlauf(100, 174, 10, 9)[0] and not gz.klimax_zeichen_1_klimaxlauf(100, 176, 10, 9)[0]
      and "25 bis 75 Prozent" in alle_texte and "70 bis 130 Prozent" in alle_texte)
    geaendert = [n for n, ist, soll in beispiel_schwellen() if not _gleich(ist, soll)]
    p("Die Beispiele beruhen auf den geltenden Schwellen; sonst die Beispiele nachrechnen", not geaendert,
      ", ".join(geaendert))
    # Die Nasdaq-Branchen aus dem Stand der Tabelle
    stand = {"branchen": [{"gruppe": "Semiconductors", "aktien": 42, "teile": ["Semiconductors"]},
                          {"gruppe": "Alpha", "aktien": 1, "teile": ["Alpha"]},
                          {"gruppe": "Beverages (Production/Distribution)", "aktien": 7,
                           "teile": ["Beverages (Production/Distribution)", "Bldg Contractors - Nonresidential"]}]}
    mit = eintraege(None, stand)
    halb = next((e for e in mit if e["begriff"] == "Branche Semiconductors"), None)
    p("Jede Branche aus dem Stand der Tabelle steht im Lexikon, samt Zahl ihrer Aktien",
      halb is not None and "42 Aktien" in halb["text"] and "42 Aktien" in halb["beispiel"]
      and any(e["begriff"] == "Branche Alpha" for e in mit), str(halb))
    getraenke = next((e for e in mit if e["begriff"].startswith("Branche Beverages")), None)
    p("Branchennamen ohne Klammern und abgesetzten Bindestrich, die Suche findet sie trotzdem",
      getraenke is not None and not textfehler(getraenke["begriff"] + " " + getraenke["text"])
      and bool(suchen(mit, "Beverages (Production/Distribution)")),
      str(getraenke and (getraenke["begriff"], getraenke["text"])))
    p("Ohne Stand stehen die Branchen, die ein Template abwaehlt",
      all(any(e["begriff"] == f"Branche {b}" for e in liste) for t in sa.TEMPLATES for b in t["branchen_aus"]))
    p("Im Kapitel Scanner-Einstellungen hat jeder Eintrag eine Gruppe",
      all(e["gruppe"] for e in liste if e["kapitel"] == "scanner"))
    p("Im Kapitel Chartmuster und Scanner-Kennzahlen hat jeder Eintrag eine Gruppe",
      all(e["gruppe"] for e in liste if e["kapitel"] in ("muster", "kennzahlen")))
    print(f"  {len(liste)} Eintraege in {len(KAPITEL)} Kapiteln: "
          + ", ".join(f"{n} {len(kap[k])}" for k, n in KAPITEL))
    print("Ergebnis:", "alles bestanden" if not fehler else f"{len(fehler)} Fehler")
    return 1 if fehler else 0


def zeigen(frage=""):
    liste = eintraege()
    treffer = suchen(liste, frage) if frage else liste
    for e in treffer:
        print(f"[{KAPITEL_NAMEN[e['kapitel']]}{', ' + e['gruppe'] if e['gruppe'] else ''}] {e['begriff']}")
        print("  " + e["text"])
        print("  Beispiel: " + e["beispiel"])


if __name__ == "__main__":
    if "--selbsttest" in sys.argv:
        sys.exit(selbsttest())
    if "--zeigen" in sys.argv:
        rest = sys.argv[sys.argv.index("--zeigen") + 1:]
        zeigen(" ".join(rest))
        sys.exit(0)
    print(__doc__)
