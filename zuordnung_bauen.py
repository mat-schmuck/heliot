#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EIGENE ZUORDNUNGSLISTE DER BRANCHEN (Etappe 6, Gerhards Entscheidung 10)
=======================================================================
Gerhard, 13.09.2026: "GRUNDREGEL: EODHD wird NICHT verwendet, ausser fuer den
Konsens. Keine laufende Nutzung, auch nicht intern, auch nicht ohne Anzeige.
DIE EINE AUSNAHME: EIN EINMALIGER ABZUG von Branche (GICS) und TYP je
Symbol, solange das Abo laeuft. [...] Danach haben wir eine eigene
Zuordnungsliste und sind von EODHD unabhaengig."

Dieses Skript baut genau diese Liste EINMAL aus dem, was der Vollabzug schon
abgelegt hat. Es fragt EODHD nicht an und braucht keinen EODHD-Schluessel:
  Typ      aus der abgelegten Symbolliste der aktiven US-Titel
           (eodhd_voll/listen/us_aktiv_JJJJ-MM-TT.json.gz), fuer alle Titel
           der Hauptboersen, also auch Fonds, ETFs und Vorzugsaktien.
  GICS     aus den Release-Archiven des Vollabzugs (je Symbol das Feld
           General): Sektor, Branchengruppe, Branche und Unterbranche, fuer
           die Titel der Stufe stock_boerse und aller weiteren aktiven Stufen,
           soweit der Vollabzug sie schon abgerufen hat.
Welche Archive es braucht, sagt das Register eodhd_voll/stand.json.

VOLLSTAENDIGKEIT: Die Liste wird erst gebaut, wenn der Vollabzug JEDEN Titel
der Stufe stock_boerse aus der Symbolliste erledigt hat (Register-Status ok,
leer oder unbekannt); sonst bricht das Skript mit Grund ab. Mit
--auch-unvollstaendig baut es trotzdem und vermerkt die Luecke in der Datei.

ABLAGE: zuordnung/branchen_JJJJ-MM-TT.json im PRIVATEN Datenrepo
heliot-daten. Lizenzierte Daten: Das Skript gibt nie einen Wert aus, nur
Zahlen; die Datei geht nie in das oeffentliche Repo.

EINORDNUNG DER STUFEN wie eodhd_voll.einordnen (Zweig fundament-phase1):
Typ "Common Stock" an einer Hauptboerse ist stock_boerse.

Aufruf:
  python zuordnung_bauen.py --archive-liste --daten DATENREPO
      gibt je benoetigtem Archiv eine Zeile "Release|Archiv" aus
  python zuordnung_bauen.py --bauen --daten DATENREPO --archive ORDNER [--auch-unvollstaendig]
  python zuordnung_bauen.py --selbsttest
"""

import argparse
import gzip
import json
import os
import sys
import tarfile
from collections import Counter, defaultdict
from datetime import datetime, timezone

ORDNER_VOLL = "eodhd_voll"
ORDNER_ZIEL = "zuordnung"
# Wie eodhd_voll.BOERSEN_HAUPT und TYP_STAMM (Zweig fundament-phase1).
BOERSEN_HAUPT = {"NYSE", "NASDAQ", "NYSE ARCA", "NYSE MKT", "NYSE AMERICAN", "AMEX", "BATS", "CBOE", "IEX"}
TYP_STAMM = {"common stock"}
GENERAL_FELDER = {"GicSector": "gics_sektor", "GicGroup": "gics_gruppe", "GicIndustry": "gics_branche",
                  "GicSubIndustry": "gics_unterbranche"}
ERLEDIGT = ("ok", "leer", "unbekannt")
LEER = {"", "NA", "N/A", "NONE", "NULL", "-"}


def _wert(w):
    if w is None:
        return None
    w = " ".join(str(w).split())
    return None if w.upper() in LEER else w


def juengste_symbolliste(daten):
    """(Pfad, Tag) der juengsten Liste aktiver US-Titel oder (None, None)."""
    ordner = os.path.join(daten, ORDNER_VOLL, "listen")
    if not os.path.isdir(ordner):
        return None, None
    namen = sorted(n for n in os.listdir(ordner) if n.startswith("us_aktiv_") and n.endswith(".json.gz"))
    if not namen:
        return None, None
    return os.path.join(ordner, namen[-1]), namen[-1][len("us_aktiv_"):-len(".json.gz")]


def symbolliste_lesen(pfad):
    with gzip.open(pfad, "rt", encoding="utf-8") as f:
        return json.load(f)


def titel_der_hauptboersen(liste):
    """{CODE: {"typ", "boerse", "stufe"}} aller aktiven Titel der Hauptboersen.
    Nur aktive Stufen: Ein delisteter Code kann inzwischen einer neuen Firma
    gehoeren, deshalb liest die Liste die delisteten Stufen nie."""
    raus = {}
    for e in liste or []:
        code = str(e.get("Code") or "").strip().upper()
        boerse = str(e.get("Exchange") or "").strip().upper()
        if not code or boerse not in BOERSEN_HAUPT:
            continue
        typ = _wert(e.get("Type"))
        t = (typ or "").lower()
        stufe = ("stock_boerse" if t in TYP_STAMM else "etf" if t == "etf" else
                 "fund" if t in ("fund", "mutual fund") else "sonstige")
        # Ein Code an zwei Hauptboersen: die Stammaktie gewinnt, sonst der erste.
        if code in raus and raus[code]["stufe"] == "stock_boerse":
            continue
        raus[code] = {"typ": typ, "boerse": boerse, "stufe": stufe}
    return raus


def register_lesen(daten):
    with open(os.path.join(daten, ORDNER_VOLL, "stand.json"), encoding="utf-8") as f:
        return json.load(f)


def vollstaendigkeit(titel, register):
    """Wie viele Titel der Stufe stock_boerse der Vollabzug schon erledigt hat.
    -> (erledigt, gesamt, offen-Liste der Codes)."""
    stamm = [c for c, e in titel.items() if e["stufe"] == "stock_boerse"]
    offen = [c for c in stamm if (register.get(f"stock_boerse:{c}") or {}).get("status") not in ERLEDIGT]
    return len(stamm) - len(offen), len(stamm), sorted(offen)


def benoetigte_archive(titel, register):
    """{(Release, Archiv): {Mitglied im Archiv: CODE}} fuer alle Titel mit
    Status ok in einer aktiven Stufe."""
    raus = defaultdict(dict)
    for code, e in titel.items():
        r = register.get(f"{e['stufe']}:{code}") or {}
        if r.get("status") != "ok" or not r.get("archiv") or not r.get("release") or not r.get("datei"):
            continue
        # Im Archiv liegt jede Datei unter der Stufe, mit der der Vollabzug sie geholt hat.
        raus[(r["release"], r["archiv"])][f"{r.get('stufe') or e['stufe']}/{r['datei']}"] = code
    return dict(raus)


def _archivteile(ordner, archiv):
    """Das Archiv und seine Teile, falls es beim Hochladen geteilt wurde
    (eodhd_voll.archive_bauen haengt dann _teilN an)."""
    basis = archiv[:-4] if archiv.endswith(".tar") else archiv
    namen = sorted(n for n in os.listdir(ordner) if n == archiv or (n.startswith(basis + "_teil") and n.endswith(".tar")))
    return [os.path.join(ordner, n) for n in namen]


def gics_aus_archiven(ordner, archive):
    """{CODE: {gics_*}} aus den heruntergeladenen Archiven; dazu Befund."""
    werte, befund = {}, Counter()
    for (_release, archiv), mitglieder in archive.items():
        pfade = _archivteile(ordner, archiv) if os.path.isdir(ordner) else []
        if not pfade:
            befund["archiv_fehlt"] += len(mitglieder)
            continue
        gefunden = set()
        for pfad in pfade:
            with tarfile.open(pfad) as tf:
                for m in tf.getmembers():
                    code = mitglieder.get(m.name)
                    if code is None or not m.isfile():
                        continue
                    try:
                        d = json.loads(gzip.decompress(tf.extractfile(m).read()))
                    except Exception:  # noqa  eine kaputte Datei darf die Liste nicht aufhalten
                        befund["unlesbar"] += 1
                        continue
                    g = (d.get("General") if isinstance(d, dict) else None) or {}
                    werte[code] = {ziel: _wert(g.get(quelle)) for quelle, ziel in GENERAL_FELDER.items()}
                    gefunden.add(m.name)
                    befund["gelesen"] += 1
        befund["im_archiv_fehlend"] += len(set(mitglieder) - gefunden)
    return werte, dict(befund)


def bauen(daten, archive_ordner, auch_unvollstaendig=False, jetzt=None):
    """Die ganze Liste als dict; wirft RuntimeError mit Grund, wenn sie noch
    nicht gebaut werden soll."""
    pfad_liste, tag_liste = juengste_symbolliste(daten)
    if not pfad_liste:
        raise RuntimeError("keine abgelegte Symbolliste der aktiven US-Titel im Datenrepo")
    titel = titel_der_hauptboersen(symbolliste_lesen(pfad_liste))
    register = register_lesen(daten)
    erledigt, gesamt, offen = vollstaendigkeit(titel, register)
    if offen and not auch_unvollstaendig:
        raise RuntimeError(f"der Vollabzug hat erst {erledigt} von {gesamt} Stammaktien der Hauptboersen erledigt")
    archive = benoetigte_archive(titel, register)
    gics, befund = gics_aus_archiven(archive_ordner, archive)
    eintraege = {}
    for code, e in sorted(titel.items()):
        eintraege[code] = {"typ": e["typ"], "boerse": e["boerse"],
                           **(gics.get(code) or dict.fromkeys(GENERAL_FELDER.values()))}
    jetzt = jetzt or datetime.now(timezone.utc)
    zahlen = {"titel": len(eintraege), "stammaktien": gesamt, "stammaktien_erledigt": erledigt,
              "mit_gics": sum(1 for e in eintraege.values() if any(e[z] for z in GENERAL_FELDER.values())),
              "mit_unterbranche": sum(1 for e in eintraege.values() if e["gics_unterbranche"]),
              "stammaktien_mit_unterbranche": sum(1 for c, e in eintraege.items()
                                                  if titel[c]["stufe"] == "stock_boerse" and e["gics_unterbranche"]),
              "typen": dict(Counter(e["typ"] or "ohne Typ" for e in eintraege.values())),
              "unterbranchen": len({e["gics_unterbranche"] for e in eintraege.values() if e["gics_unterbranche"]}),
              "archive": len(archive), **befund}
    return {"stand": jetzt.date().isoformat(), "gebaut_am": jetzt.isoformat(timespec="seconds"),
            "quelle": "EODHD, einmaliger Abzug laut Entscheidung 10: Typ aus der Symbolliste, GICS aus dem Feld "
                      "General der Fundamentals",
            "symbolliste": tag_liste, "vollstaendig": not offen, "offen": offen[:50], "zahlen": zahlen,
            "titel": eintraege}


# --- Selbsttest -------------------------------------------------------------------

def selbsttest() -> int:
    import tempfile
    fehler = []

    def p(name, ok, zusatz=""):
        print(f"  {'ok  ' if ok else 'FEHL'} {name}" + (f"; {zusatz}" if zusatz else ""))
        if not ok:
            fehler.append(name)

    print("Zuordnungsliste der Branchen, Selbsttest (ohne Netz)")
    with tempfile.TemporaryDirectory() as tmp:
        daten = os.path.join(tmp, "daten")
        listen = os.path.join(daten, ORDNER_VOLL, "listen")
        os.makedirs(listen)
        symbole = [{"Code": "AAA", "Exchange": "NASDAQ", "Type": "Common Stock"},
                   {"Code": "BRK-B", "Exchange": "NYSE", "Type": "Common Stock"},
                   {"Code": "FFF", "Exchange": "NYSE", "Type": "FUND"},
                   {"Code": "OTC1", "Exchange": "PINK", "Type": "Common Stock"},
                   {"Code": "CCC", "Exchange": "BATS", "Type": "Common Stock"},
                   {"Code": "NEU", "Exchange": "NASDAQ", "Type": "Common Stock"}]
        for tag, liste in (("2026-09-10", symbole[:2]), ("2026-09-12", symbole)):
            with gzip.open(os.path.join(listen, f"us_aktiv_{tag}.json.gz"), "wt", encoding="utf-8") as f:
                json.dump(liste, f)
        register = {"stock_boerse:AAA": {"stufe": "stock_boerse", "status": "ok", "archiv": "eodhd_stock_boerse_1.tar",
                                         "release": "eodhd-voll-1", "datei": "AAA.json.gz"},
                    "stock_boerse:BRK-B": {"stufe": "stock_boerse", "status": "ok",
                                           "archiv": "eodhd_stock_boerse_2.tar", "release": "eodhd-voll-2",
                                           "datei": "BRK-B.json.gz"},
                    "stock_boerse:CCC": {"stufe": "stock_boerse", "status": "leer"},
                    "delisted_stock:NEU": {"stufe": "delisted_stock", "status": "ok", "archiv": "x.tar",
                                           "release": "r", "datei": "NEU.json.gz"}}
        with open(os.path.join(daten, ORDNER_VOLL, "stand.json"), "w", encoding="utf-8") as f:
            json.dump(register, f)
        archive = os.path.join(tmp, "archive")
        os.makedirs(archive)

        def tar_mit(name, dateien):
            with tarfile.open(os.path.join(archive, name), "w") as tf:
                for mitglied, inhalt in dateien.items():
                    roh = gzip.compress(json.dumps(inhalt).encode("utf-8"))
                    info = tarfile.TarInfo(mitglied)
                    info.size = len(roh)
                    import io
                    tf.addfile(info, io.BytesIO(roh))

        tar_mit("eodhd_stock_boerse_1.tar", {"stock_boerse/AAA.json.gz": {"General": {
            "GicSector": "Information Technology", "GicGroup": "Semiconductors & Semiconductor Equipment",
            "GicIndustry": "Semiconductors & Semiconductor Equipment", "GicSubIndustry": "Semiconductors"}}})
        tar_mit("eodhd_stock_boerse_2_teil1.tar", {"stock_boerse/BRK-B.json.gz": {"General": {
            "GicSector": "Financials", "GicGroup": "Financial Services", "GicIndustry": "Financial Services",
            "GicSubIndustry": "NA"}}})

        pfad, tag = juengste_symbolliste(daten)
        p("Juengste Symbolliste wird genommen", tag == "2026-09-12")
        titel = titel_der_hauptboersen(symbolliste_lesen(pfad))
        p("Nur Hauptboersen, Stufen wie im Vollabzug", sorted(titel) == ["AAA", "BRK-B", "CCC", "FFF", "NEU"]
          and titel["FFF"]["stufe"] == "fund" and titel["CCC"]["stufe"] == "stock_boerse", str(titel))
        e, g, offen = vollstaendigkeit(titel, register)
        p("Vollstaendigkeit: NEU fehlt in der Stufe stock_boerse (delisted zaehlt nicht)",
          (e, g, offen) == (3, 4, ["NEU"]), str((e, g, offen)))
        try:
            bauen(daten, archive)
            p("Unvollstaendig: Abbruch mit Grund", False)
        except RuntimeError as err:
            p("Unvollstaendig: Abbruch mit Grund", "3 von 4" in str(err), str(err))
        liste = bauen(daten, archive, auch_unvollstaendig=True,
                      jetzt=datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc))
        t = liste["titel"]
        p("GICS aus dem Archiv, Typ aus der Liste", t["AAA"]["gics_unterbranche"] == "Semiconductors"
          and t["AAA"]["typ"] == "Common Stock" and t["AAA"]["boerse"] == "NASDAQ")
        p("Geteiltes Archiv wird gefunden, NA gilt als leer", t["BRK-B"]["gics_sektor"] == "Financials"
          and t["BRK-B"]["gics_unterbranche"] is None)
        p("Fonds mit Typ ohne GICS, leerer Abruf ohne GICS", t["FFF"]["typ"] == "FUND" and t["FFF"]["gics_sektor"] is None
          and t["CCC"]["gics_sektor"] is None)
        p("Delistete Stufe wird nie gelesen", t["NEU"]["gics_sektor"] is None)
        z = liste["zahlen"]
        p("Zahlen und Vermerke", liste["vollstaendig"] is False and liste["offen"] == ["NEU"] and liste["stand"] == "2026-09-16"
          and z["mit_gics"] == 2 and z["mit_unterbranche"] == 1 and z["stammaktien_mit_unterbranche"] == 1
          and z["gelesen"] == 2 and z["unterbranchen"] == 1, str(z))
        import kennzahlen_gruppen as kg
        pfad_z = os.path.join(tmp, "branchen.json")
        with open(pfad_z, "w", encoding="utf-8") as f:
            json.dump(liste, f)
        zl, bl = kg.zuordnung_lesen(pfad_z)
        p("Die Nachttabelle liest die Liste, Klassen als BRK.B", bl["status"] == "ok" and bl["stand"] == "2026-09-16"
          and kg.gruppe_aus(zl.get("AAA")) == "Semiconductors" and "BRK.B" in zl)
    quelle = open(__file__, encoding="utf-8").read()
    p("Kein EODHD-Abruf im Skript", all(x not in quelle for x in ("eodhd" + "historicaldata.com", "EODHD_" + "API_KEY",
                                                                     "api_" + "token")))
    print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles bestanden.")
    return 1 if fehler else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Eigene Zuordnungsliste der Branchen (Etappe 6, Entscheidung 10)")
    ap.add_argument("--selbsttest", action="store_true")
    ap.add_argument("--archive-liste", action="store_true", help="benoetigte Archive als Release|Archiv ausgeben")
    ap.add_argument("--bauen", action="store_true")
    ap.add_argument("--daten", default="daten", help="Arbeitskopie des privaten Datenrepos")
    ap.add_argument("--archive", default=os.path.join(".cache", "eodhd"), help="Ordner mit den heruntergeladenen Archiven")
    ap.add_argument("--auch-unvollstaendig", action="store_true")
    a = ap.parse_args()
    if a.selbsttest:
        return selbsttest()
    if a.archive_liste:
        pfad, _tag = juengste_symbolliste(a.daten)
        if not pfad:
            print("keine Symbolliste", file=sys.stderr)
            return 1
        titel = titel_der_hauptboersen(symbolliste_lesen(pfad))
        register = register_lesen(a.daten)
        erledigt, gesamt, offen = vollstaendigkeit(titel, register)
        print(f"Stammaktien der Hauptboersen erledigt: {erledigt} von {gesamt}", file=sys.stderr)
        for release, archiv in sorted(benoetigte_archive(titel, register)):
            print(f"{release}|{archiv}")
        return 0
    if a.bauen:
        try:
            liste = bauen(a.daten, a.archive, auch_unvollstaendig=a.auch_unvollstaendig)
        except RuntimeError as err:
            print(f"Zuordnungsliste nicht gebaut: {err}.")
            return 2
        ziel = os.path.join(a.daten, ORDNER_ZIEL, f"branchen_{liste['stand']}.json")
        os.makedirs(os.path.dirname(ziel), exist_ok=True)
        with open(ziel, "w", encoding="utf-8") as f:
            json.dump(liste, f, ensure_ascii=False, indent=0, sort_keys=False)
        z = liste["zahlen"]
        # Nur Zahlen, nie Werte: die Liste ist lizenziert und dieses Log oeffentlich.
        print(f"Zuordnungsliste {os.path.basename(ziel)}: {z['titel']} Titel, davon {z['stammaktien']} Stammaktien "
              f"({z['stammaktien_erledigt']} erledigt), {z['stammaktien_mit_unterbranche']} Stammaktien mit "
              f"GICS-Unterbranche, {z['unterbranchen']} Unterbranchen, {z['archive']} Archive, "
              f"gelesen {z.get('gelesen', 0)}, fehlend im Archiv {z.get('im_archiv_fehlend', 0)}, "
              f"Archiv fehlt {z.get('archiv_fehlt', 0)}, unlesbar {z.get('unlesbar', 0)}; "
              f"{'vollstaendig' if liste['vollstaendig'] else 'UNVOLLSTAENDIG'}")
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
