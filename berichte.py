#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BERICHTE: der Reiter Berichte der App
=====================================
Gerhards Auftrag vom 29.09.2026, Teil 4 ("Alle Berichte nur noch in
Streamlit"), seine Zuordnung in der Nacht auf den 30.09.2026 (Fragen 6 bis
13) und seine Antworten vom 30.09.2026 abends (Antwort 14: Gelesen-Vermerk je
Geraet; je Berichtsart ein Unterreiter, daneben die Zahl der ungelesenen,
jeder Bericht von Hand auf gelesen setzbar).

WAS EIN BERICHT IST: alles, was eine Auskunft ist und kein Kaufsignal. Die
Kauf-Alarme samt uebersprungen mit Bot-Zeile, Red to Green, der Power-Gap am
Lueckentag und die technischen Stoerungsmeldungen bleiben auf ntfy; alles
andere steht ausschliesslich hier. Die Bot-Zeilen fuer Verkaeufe laufen
unveraendert weiter, nur die Meldung an den Menschen wandert in den Reiter.

ABLAGE: eine Datei im privaten Datenrepo heliot-daten, berichte/berichte.json,
gelesen und geschrieben ueber die GitHub-Schnittstelle mit DATEN_TOKEN, dem
Token, das genau dieses Repo lesen und beschreiben darf. Schreiben heisst:
lesen, anhaengen, mit der Kennung (sha) des gelesenen Stands zurueckschreiben;
hat inzwischen ein anderer Lauf geschrieben, lehnt GitHub ab, und es wird neu
gelesen und noch einmal geschrieben. So gehen zwei gleichzeitige Berichte nie
verloren.

LEERUNG (Teil 4): "Der Reiter wird jeden Morgen um 14:00 Uhr (oesterreichische
Zeit) geleert, vor dem ersten Bericht des Tages. Der Stand von gestern bleibt
also bis dahin lesbar, auch ueber das Wochenende." Geleert wird deshalb
Montag bis Freitag um 14:00 Wiener Zeit; ein Bericht vom Freitagabend oder aus
der Nacht auf Samstag steht bis Montag 14:00. Die App zeigt nur, was nach der
letzten Leerung abgelegt wurde, und jeder Schreiber wirft beim Ablegen weg,
was davor liegt. Das Leeren betrifft nur diesen Reiter, nichts aus Logbuch,
Wochenlisten oder Nachtscan-Daten.

GELESEN JE GERAET (Antwort 14): Welche Berichte gelesen sind, merkt sich der
Browser des Geraets (wie das Angemeldet-Bleiben, zugang.speicher_js), nicht
die Datei. Gespeichert werden die Kennungen der gelesenen Berichte als eine
Zeichenkette aus Kleinbuchstaben, Ziffern und Punkten.

Aufruf:
    python berichte.py --selbsttest
    python berichte.py --zeigen          was gerade im Reiter steht (Token aus DATEN_TOKEN)
"""

import base64
import hashlib
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    WIEN = ZoneInfo("Europe/Vienna")
except Exception:  # noqa: BLE001, ohne Zeitzonendaten gilt die Sommerzeit
    WIEN = timezone(timedelta(hours=2))

DATEN_REPO = "mat-schmuck/heliot-daten"
PFAD = "berichte/berichte.json"
TOKEN_ENV = "DATEN_TOKEN"
TROCKEN_ENV = "BERICHTE_TROCKEN"     # 1 = nur ausgeben, nichts ablegen (Probelaeufe)
LEERUNG_STUNDE = 14                  # Wiener Zeit, Montag bis Freitag
VERSUCHE = 6
FRIST = 20                           # Sekunden je Abruf

# DIE BERICHTSARTEN, je eine ein Unterreiter, in der Reihenfolge der Anzeige.
# Der Schluessel steht in der Datei, der Name im Unterreiter.
# Zuordnung nach Gerhard (30.09.2026 nachts): Verkaufssignale sind EXIT
# Tagesgeschaeft, Teilverkauf ab plus 20 Prozent und die Ausstiege im
# Schlussbefund (Frage 6); Zeitdeckel (7), Klimax (8), Insider-Kaeufe (9) und
# Power-Gap-Einstieg uebersprungen (11) je fuer sich; dazu Abendbericht,
# Sektor-Aufsteiger, Stufe 3, Zahlen voraus, Gewinnzonen und die Abweichungen
# der amtlichen Zahlen von der Pressemitteilung (Teil 4). Der Schlussbefund um
# 15:45 New Yorker Zeit verteilt sich nach seinen Arten auf diese Unterreiter.
ARTEN = [
    ("verkauf", "Verkaufssignale"),
    ("gapup", "Gap-Ups vorbörslich"),
    ("abend", "Abendbericht"),
    ("klimax", "Klimax"),
    ("zeitdeckel", "Zeitdeckel"),
    ("stufe3", "Stufe 3"),
    ("zahlen", "Zahlen voraus"),
    ("gewinnzonen", "Gewinnzonen"),
    ("sektor", "Sektor-Aufsteiger"),
    ("sektorradar", "Sektor-Radar"),
    ("insider", "Insider-Käufe"),
    ("amtlich", "Amtliche Zahlen"),
    ("powergap", "Power-Gap-Einstieg übersprungen"),
    ("ema8", "8-EMA-Hinweise"),
    ("weitere", "Weitere Auskünfte"),
]
ART_NAMEN = dict(ARTEN)

_KENNUNG = re.compile(r"^[0-9a-f]{12}$")

# Im Selbsttest ersetzbar, damit Ablage und Lesen ohne Netz geprueft werden.
_ABRUF = None


# ---------------------------------------------------------------------------
# Bausteine
# ---------------------------------------------------------------------------

def jetzt_utc() -> datetime:
    return datetime.now(timezone.utc)


def zeit_text(dt: datetime) -> str:
    """Ein Zeitpunkt, wie er in der Datei steht: UTC, auf die Sekunde."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def zeit_lesen(text) -> datetime | None:
    try:
        return datetime.strptime(str(text), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def uhrzeit_wien(text) -> str:
    """Datum und Uhrzeit eines Berichts in Wiener Zeit, wie die Anzeige sie
    nennt: '01.10.2026, 15:10 Uhr'."""
    dt = zeit_lesen(text)
    if dt is None:
        return "Zeit unbekannt"
    w = dt.astimezone(WIEN)
    return f"{w:%d.%m.%Y}, {w:%H:%M} Uhr"


def leerung_vor(jetzt: datetime | None = None) -> datetime:
    """Der letzte Leerungszeitpunkt bis jetzt: Montag bis Freitag 14:00
    Wiener Zeit. Zurueck kommt er in UTC."""
    jetzt = (jetzt or jetzt_utc()).astimezone(WIEN)
    tag = jetzt.date()
    for _ in range(8):
        punkt = datetime(tag.year, tag.month, tag.day, LEERUNG_STUNDE, 0, tzinfo=WIEN)
        if tag.weekday() < 5 and punkt <= jetzt:
            return punkt.astimezone(timezone.utc)
        tag = tag - timedelta(days=1)
    raise RuntimeError("keine Leerung in den letzten acht Tagen gefunden")


def kennung(art: str, zeit: str, titel: str, absaetze) -> str:
    """Zwoelf Hexziffern aus Art, Zeit, Titel und Text. Derselbe Bericht
    bekommt immer dieselbe Kennung; zweimal abgelegt, steht er einmal da."""
    roh = json.dumps([art, zeit, titel, list(absaetze or [])], ensure_ascii=False)
    return hashlib.sha1(roh.encode("utf-8")).hexdigest()[:12]


def bericht(art: str, titel: str, absaetze, zeit: datetime | None = None) -> dict:
    """Ein Bericht als Eintrag der Datei. absaetze ist eine Liste von Texten,
    je Absatz einer; Zeilenumbrueche innerhalb eines Absatzes bleiben."""
    if art not in ART_NAMEN:
        raise ValueError(f"unbekannte Berichtsart {art!r}")
    absaetze = [str(a) for a in (absaetze or []) if str(a).strip()]
    z = zeit_text(zeit or jetzt_utc())
    return {"id": kennung(art, z, titel, absaetze), "art": art, "titel": str(titel).strip(),
            "zeit": z, "absaetze": absaetze}


def gueltig(e) -> bool:
    return (isinstance(e, dict) and e.get("art") in ART_NAMEN and _KENNUNG.match(str(e.get("id") or ""))
            and zeit_lesen(e.get("zeit")) is not None and isinstance(e.get("absaetze"), list))


def sichtbar(berichte, jetzt: datetime | None = None) -> list:
    """Was der Reiter zeigt: gueltige Berichte seit der letzten Leerung,
    neueste oben, jede Kennung einmal."""
    grenze = leerung_vor(jetzt)
    gesehen, raus = set(), []
    for e in berichte or []:
        if not gueltig(e) or e["id"] in gesehen:
            continue
        if zeit_lesen(e["zeit"]) < grenze:
            continue
        gesehen.add(e["id"])
        raus.append(e)
    raus.sort(key=lambda e: (e["zeit"], e["id"]), reverse=True)
    return raus


def je_art(berichte) -> dict:
    """Die Berichte je Art, in der Reihenfolge von ARTEN."""
    raus = {k: [] for k, _ in ARTEN}
    for e in berichte or []:
        if e.get("art") in raus:
            raus[e["art"]].append(e)
    return raus


# ---------------------------------------------------------------------------
# Gelesen je Geraet (Antwort 14)
# ---------------------------------------------------------------------------

def gelesen_aus_wert(wert) -> set:
    """Die Kennungen aus dem Wert im Browser ('a1b2c3d4e5f6.0123456789ab')."""
    return {k for k in str(wert or "").split(".") if _KENNUNG.match(k)}


def gelesen_wert(kennungen, nur=None) -> str:
    """Der Wert fuer den Browser. Mit nur= bleiben allein Kennungen, die es
    noch gibt; so waechst der Eintrag nicht ueber die Leerungen hinaus."""
    ks = {k for k in (kennungen or ()) if _KENNUNG.match(str(k))}
    if nur is not None:
        ks &= set(nur)
    return ".".join(sorted(ks))


def ungelesen_je_art(berichte, gelesen) -> dict:
    gelesen = set(gelesen or ())
    zahl = {k: 0 for k, _ in ARTEN}
    for e in berichte or []:
        if e.get("art") in zahl and e.get("id") not in gelesen:
            zahl[e["art"]] += 1
    return zahl


def unterreiter_name(art: str, ungelesen: int) -> str:
    """Der Name eines Unterreiters, daneben die Zahl der ungelesenen, ohne
    Klammern (Mathias, 30.09.2026)."""
    name = ART_NAMEN.get(art, art)
    return f"{name}, {ungelesen} ungelesen" if ungelesen else name


def art_aus_unterreiter(beschriftung) -> str | None:
    """Gegenrichtung zu unterreiter_name."""
    text = str(beschriftung or "")
    for k, name in ARTEN:
        if text == name or text.startswith(name + ", "):
            return k
    return None


# ---------------------------------------------------------------------------
# Die Datei im Datenrepo
# ---------------------------------------------------------------------------

def _kopf(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}


def _abruf(methode: str, url: str, token: str, koerper=None):
    """(Status, JSON oder None). Wirft nie."""
    if _ABRUF is not None:
        return _ABRUF(methode, url, token, koerper)
    import urllib.error
    import urllib.request
    daten = json.dumps(koerper).encode("utf-8") if koerper is not None else None
    anfrage = urllib.request.Request(url, data=daten, method=methode, headers=_kopf(token))
    if daten is not None:
        anfrage.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(anfrage, timeout=FRIST) as a:
            return a.status, json.loads(a.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8") or "null")
        except Exception:  # noqa: BLE001
            return e.code, None
    except Exception:  # noqa: BLE001
        return 0, None


def _url() -> str:
    return f"https://api.github.com/repos/{DATEN_REPO}/contents/{PFAD}"


def datei_lesen(token: str) -> tuple:
    """(Liste der Berichte, sha oder None, Fehlertext). Eine fehlende Datei
    ist kein Fehler, sondern ein leerer Reiter."""
    status, j = _abruf("GET", _url(), token)
    if status == 404:
        return [], None, ""
    if status != 200 or not isinstance(j, dict):
        return [], None, f"GitHub antwortete mit Code {status}"
    try:
        inhalt = base64.b64decode(j.get("content") or "").decode("utf-8")
        daten = json.loads(inhalt) if inhalt.strip() else {}
    except Exception as e:  # noqa: BLE001
        return [], j.get("sha"), f"die Datei ist unlesbar ({type(e).__name__})"
    liste = daten.get("berichte") if isinstance(daten, dict) else None
    return [e for e in (liste or []) if isinstance(e, dict)], j.get("sha"), ""


def datei_text(berichte) -> str:
    return json.dumps({"berichte": berichte}, ensure_ascii=False, indent=1) + "\n"


def ablegen_eintrag(eintrag: dict, token: str | None = None, melder=print, jetzt=None) -> bool:
    """Einen fertigen Eintrag (bericht()) in die Datei; siehe ablegen_viele."""
    return ablegen_viele([eintrag], token=token, melder=melder, jetzt=jetzt)


def ablegen_viele(eintraege: list, token: str | None = None, melder=print, jetzt=None) -> bool:
    """Fertige Eintraege (bericht()) in EINEM Schreibgang in die Datei: alle
    oder keiner. Wirft nie; ein Fehlschlag wird laut genannt und mit False
    beantwortet."""
    eintraege = [e for e in (eintraege or []) if gueltig(e)]
    if not eintraege:
        return True
    namen = "; ".join(str(e.get("titel")) for e in eintraege)
    token = (token if token is not None else os.environ.get(TOKEN_ENV) or "").strip()
    if (os.environ.get(TROCKEN_ENV) or "").strip() == "1":
        for e in eintraege:
            melder(f"  (Trocken) Bericht {ART_NAMEN.get(e.get('art'))}: {e.get('titel')}")
        return True
    if not token:
        melder(f"  Bericht nicht abgelegt, weil {TOKEN_ENV} fehlt: {namen}")
        return False
    neue = {e["id"] for e in eintraege}
    letzter = ""
    for versuch in range(1, VERSUCHE + 1):
        liste, sha, fehler = datei_lesen(token)
        if fehler and sha is None:
            letzter = fehler
        else:
            grenze = leerung_vor(jetzt)
            behalten = [e for e in liste if gueltig(e) and zeit_lesen(e["zeit"]) >= grenze
                        and e["id"] not in neue]
            behalten.extend(eintraege)
            koerper = {"message": "Bericht: " + ", ".join(sorted({ART_NAMEN[e["art"]] for e in eintraege})),
                       "content": base64.b64encode(datei_text(behalten).encode("utf-8")).decode("ascii")}
            if sha:
                koerper["sha"] = sha
            status, _j = _abruf("PUT", _url(), token, koerper)
            if status in (200, 201):
                return True
            letzter = f"GitHub antwortete mit Code {status}"
            if status in (401, 403, 404):
                break                # kein Recht oder kein Repo: Wiederholen hilft nicht
        if versuch < VERSUCHE:
            time.sleep(1.0 + random.random() * 2.0)
    melder(f"  Bericht nicht abgelegt ({letzter}): {namen}")
    return False


def ablegen(art: str, titel: str, absaetze, zeit=None, token=None, melder=print) -> bool:
    """Einen Bericht in den Reiter legen."""
    return ablegen_eintrag(bericht(art, titel, absaetze, zeit), token=token, melder=melder)


# ---------------------------------------------------------------------------
# Selbsttest (ohne Netz)
# ---------------------------------------------------------------------------

def selbsttest() -> int:
    fehler = []

    def p(name, ok, zusatz=""):
        print(f"  {'ok  ' if ok else 'FEHL'} {name}" + (f"; {zusatz}" if zusatz else ""))
        if not ok:
            fehler.append(name)

    print("BERICHTE, Selbsttest")
    u = lambda *a: datetime(*a, tzinfo=timezone.utc)  # noqa: E731

    # 1. Leerung: Montag bis Freitag 14:00 Wien
    p("Leerung: Mittwoch 15:10 Wien, also 13:10 UTC, gilt die von 14:00 desselben Tags",
      leerung_vor(u(2026, 10, 7, 13, 10)) == u(2026, 10, 7, 12, 0))
    p("Leerung: Mittwoch 13:59 Wien gilt noch die vom Dienstag",
      leerung_vor(u(2026, 10, 7, 11, 59)) == u(2026, 10, 6, 12, 0))
    p("Leerung: Samstag und Sonntag gilt die vom Freitag",
      leerung_vor(u(2026, 10, 10, 9, 0)) == u(2026, 10, 9, 12, 0)
      and leerung_vor(u(2026, 10, 11, 21, 0)) == u(2026, 10, 9, 12, 0))
    p("Leerung: Montag 13:00 Wien gilt die vom Freitag, ab 14:00 die neue",
      leerung_vor(u(2026, 10, 12, 11, 0)) == u(2026, 10, 9, 12, 0)
      and leerung_vor(u(2026, 10, 12, 12, 0)) == u(2026, 10, 12, 12, 0))
    p("Leerung: im Winter 14:00 Wien ist 13:00 UTC",
      leerung_vor(u(2026, 11, 4, 14, 0)) == u(2026, 11, 4, 13, 0))

    # 2. Bericht und Kennung
    a = bericht("gapup", "Gap-Ups vorbörslich", ["1. AAA", "2. BBB"], u(2026, 10, 7, 13, 10, 5))
    p("Bericht: Felder und Zeit in UTC", a["art"] == "gapup" and a["zeit"] == "2026-10-07T13:10:05Z"
      and a["absaetze"] == ["1. AAA", "2. BBB"] and gueltig(a), str(a))
    p("Kennung: zwoelf Hexziffern, gleich bei gleichem Inhalt, anders bei anderem",
      _KENNUNG.match(a["id"]) and a["id"] == bericht("gapup", "Gap-Ups vorbörslich", ["1. AAA", "2. BBB"],
                                                     u(2026, 10, 7, 13, 10, 5))["id"]
      and a["id"] != bericht("gapup", "Gap-Ups vorbörslich", ["1. AAA"], u(2026, 10, 7, 13, 10, 5))["id"])
    try:
        bericht("unbekannt", "x", ["y"])
        p("Unbekannte Art wird abgewiesen", False)
    except ValueError:
        p("Unbekannte Art wird abgewiesen", True)
    p("Uhrzeit in Wiener Zeit", uhrzeit_wien("2026-10-07T13:10:05Z") == "07.10.2026, 15:10 Uhr",
      uhrzeit_wien("2026-10-07T13:10:05Z"))

    # 3. Sichtbar: seit der Leerung, neueste oben, jede Kennung einmal
    alt = bericht("abend", "Abendbericht", ["gestern"], u(2026, 10, 7, 11, 0))
    b = bericht("verkauf", "Verkaufssignale", ["AAA raus"], u(2026, 10, 7, 14, 0))
    s = sichtbar([alt, a, b, a, {"kaputt": 1}], u(2026, 10, 7, 15, 0))
    p("Sichtbar: nur seit der Leerung, neueste oben, ohne Doppel und Kaputtes",
      [e["id"] for e in s] == [b["id"], a["id"]], str([e["titel"] for e in s]))
    p("Sichtbar: vor 14:00 steht der Bericht von gestern Nachmittag noch da, ab 14:00 nicht mehr",
      [e["id"] for e in sichtbar([b], u(2026, 10, 8, 11, 0))] == [b["id"]]
      and sichtbar([b], u(2026, 10, 8, 12, 0)) == [])

    # 4. Gelesen je Geraet
    w = gelesen_wert({a["id"], b["id"], "kaputt"})
    p("Gelesen: Wert nur aus Kennungen, sortiert, mit Punkt getrennt",
      w == ".".join(sorted([a["id"], b["id"]])) and re.fullmatch(r"[A-Za-z0-9._-]*", w), w)
    p("Gelesen: zurueck aus dem Wert", gelesen_aus_wert(w) == {a["id"], b["id"]})
    p("Gelesen: nur noch vorhandene bleiben", gelesen_wert({a["id"], b["id"]}, nur={b["id"]}) == b["id"])
    z = ungelesen_je_art(s, {b["id"]})
    p("Ungelesen je Art", z["gapup"] == 1 and z["verkauf"] == 0 and set(z) == set(ART_NAMEN), str(z))
    p("Unterreiter: Zahl daneben, ohne Klammern; ohne Ungelesene nur der Name",
      unterreiter_name("gapup", 2) == "Gap-Ups vorbörslich, 2 ungelesen"
      and unterreiter_name("verkauf", 0) == "Verkaufssignale")
    p("Unterreiter: zurueck zur Art, auch mit Zahl",
      art_aus_unterreiter("Gap-Ups vorbörslich, 2 ungelesen") == "gapup"
      and art_aus_unterreiter("Verkaufssignale") == "verkauf" and art_aus_unterreiter("Unsinn") is None)
    p("Keine Klammer und kein Gedankenstrich in den Namen der Unterreiter",
      not any(re.search(r"[()–—|]", n) for _k, n in ARTEN))

    # 5. Ablage gegen eine nachgestellte GitHub-Schnittstelle
    global _ABRUF
    lager = {"inhalt": None, "sha": None, "puts": 0, "konflikte": 0}

    def nachgestellt(methode, url, token, koerper):
        if methode == "GET":
            if lager["inhalt"] is None:
                return 404, {"message": "Not Found"}
            return 200, {"content": base64.b64encode(lager["inhalt"].encode("utf-8")).decode("ascii"),
                         "sha": lager["sha"]}
        if methode == "PUT":
            lager["puts"] += 1
            if lager["konflikte"] > 0:
                lager["konflikte"] -= 1
                return 409, {"message": "conflict"}
            if koerper.get("sha") != lager["sha"]:
                return 409, {"message": "sha passt nicht"}
            lager["inhalt"] = base64.b64decode(koerper["content"]).decode("utf-8")
            lager["sha"] = hashlib.sha1(lager["inhalt"].encode("utf-8")).hexdigest()
            return 201, {"content": {"sha": lager["sha"]}}
        return 400, None

    altes = os.environ.pop(TROCKEN_ENV, None)
    _ABRUF = nachgestellt
    schlaf = time.sleep
    globals()["time"].sleep = lambda *_a: None
    try:
        gesagt = []
        ok1 = ablegen_eintrag(alt, token="pruef", melder=gesagt.append, jetzt=u(2026, 10, 7, 11, 30))
        ok2 = ablegen_eintrag(a, token="pruef", melder=gesagt.append, jetzt=u(2026, 10, 7, 13, 10))
        inhalt = json.loads(lager["inhalt"])["berichte"]
        p("Ablage: neue Datei angelegt, dann angehaengt; die Leerung wirft den alten Bericht weg",
          ok1 and ok2 and [e["id"] for e in inhalt] == [a["id"]], str([e["titel"] for e in inhalt]))
        lager["konflikte"] = 2
        ok3 = ablegen_eintrag(b, token="pruef", melder=gesagt.append, jetzt=u(2026, 10, 7, 14, 0))
        inhalt = json.loads(lager["inhalt"])["berichte"]
        p("Ablage: nach zwei Konflikten neu gelesen und geschrieben, nichts verloren",
          ok3 and [e["id"] for e in inhalt] == [a["id"], b["id"]] and not gesagt, str(gesagt))
        ok4 = ablegen_eintrag(b, token="pruef", melder=gesagt.append, jetzt=u(2026, 10, 7, 14, 1))
        inhalt = json.loads(lager["inhalt"])["berichte"]
        p("Ablage: derselbe Bericht zweimal steht einmal da", ok4 and len(inhalt) == 2)
        ok5 = ablegen_eintrag(b, token="", melder=gesagt.append)
        p("Ablage: ohne Token kein Absturz, sondern eine laute Zeile", ok5 is False and gesagt
          and "DATEN_TOKEN fehlt" in gesagt[-1], str(gesagt[-1:]))
        os.environ[TROCKEN_ENV] = "1"
        gesagt.clear()
        puts = lager["puts"]
        ok6 = ablegen("weitere", "Probe", ["nur Ausgabe"], token="pruef", melder=gesagt.append)
        p("Trocken: nichts abgelegt, nur ausgegeben", ok6 and lager["puts"] == puts and gesagt
          and gesagt[0].startswith("  (Trocken)"), str(gesagt))
        os.environ.pop(TROCKEN_ENV, None)
        liste, sha, f = datei_lesen("pruef")
        p("Lesen: Liste, sha und kein Fehler", len(liste) == 2 and sha == lager["sha"] and f == "")
        c1 = bericht("klimax", "Schlussnahe Befunde", ["1. KKK"], u(2026, 10, 7, 19, 45))
        c2 = bericht("stufe3", "Schlussnahe Befunde", ["1. SSS"], u(2026, 10, 7, 19, 45))
        puts = lager["puts"]
        ok7 = ablegen_viele([c1, c2, {"kaputt": 1}], token="pruef", melder=gesagt.append, jetzt=u(2026, 10, 7, 19, 45))
        inhalt = json.loads(lager["inhalt"])["berichte"]
        p("Sammelablage: zwei Berichte in einem Schreibgang, Kaputtes faellt weg",
          ok7 and lager["puts"] == puts + 1 and [e["id"] for e in inhalt][-2:] == [c1["id"], c2["id"]]
          and len(inhalt) == 4, str([e["titel"] for e in inhalt]))
    finally:
        _ABRUF = None
        globals()["time"].sleep = schlaf
        if altes is not None:
            os.environ[TROCKEN_ENV] = altes

    print("\nAlles bestanden." if not fehler else f"\n{len(fehler)} Fehler.")
    return 1 if fehler else 0


def zeigen() -> int:
    token = (os.environ.get(TOKEN_ENV) or "").strip()
    if not token:
        print(f"{TOKEN_ENV} fehlt.")
        return 1
    liste, _sha, fehler = datei_lesen(token)
    if fehler:
        print(fehler)
        return 1
    s = sichtbar(liste)
    print(f"{len(s)} Bericht(e) seit der Leerung {uhrzeit_wien(zeit_text(leerung_vor()))}:")
    for e in s:
        print(f"  {uhrzeit_wien(e['zeit'])}; {ART_NAMEN[e['art']]}; {e['titel']}")
    return 0


if __name__ == "__main__":
    if "--selbsttest" in sys.argv:
        sys.exit(selbsttest())
    if "--zeigen" in sys.argv:
        sys.exit(zeigen())
    print(__doc__)
