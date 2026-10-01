# -*- coding: utf-8 -*-
"""
BLACKLIST: gesperrte Aktien fuer das ganze System
=================================================
Gerhards Auftrag vom 30.09.2026 (ueber Mathias): "In Streamlit soll es einen
Reiter Blacklist geben mit einem Eingabefeld, in das das Kuerzel oder der
Firmenname einer Aktie eingegeben wird und, bei Bestaetigung, diese Aktie in
keinen Alarmen oder sonst wo je wieder auftaucht. Jede eingetragene Aktie soll
eine Checkbox bekommen, mit der man sie wieder abhaken kann, wobei bei Abhaken
eine Rueckfrage erfolgen soll. Ausserdem soll es einen Loesch-Button fuer jede
Aktie geben, um sie wieder entfernen zu koennen." Seine Antworten 8 und 13 vom
selben Abend: Die Blacklist sperrt ALLES, auch die Verkaufssignale einer
gehaltenen Aktie ("meine bewusste Entscheidung"); sie liegt im privaten
Datenrepo, dauerhaft, EINE Liste fuer Nachtscan, Waechter, Berichte und Bot; der
Gastzugang darf sie weder sehen noch aendern. Dazu: Haelt der Bot die Aktie
gerade, weist die App vor dem Speichern darauf hin.

ABLAGE: heliot-daten, blacklist/blacklist.json, ueber die GitHub-Schnittstelle
mit DATEN_TOKEN, wie die Berichte:
    {"eintraege": [{"ticker": "AAPL", "name": "Apple Inc.", "aktiv": true,
                    "seit": "2026-10-01T15:00:00Z", "geaendert": "..."}]}
aktiv false heisst abgehakt: Der Eintrag bleibt stehen und sperrt nichts.
Geschrieben wird mit der Kennung (sha) des gelesenen Stands; hat inzwischen ein
anderer geschrieben, wird neu gelesen und die Aenderung noch einmal angewandt.

FREIGABEN (Gerhard, 01.10.2026, Antwort 16: "Sofort ueberwachen. Der Waechter
rechnet ihre Kaufpunkte gleich selbst, wie bei einer einzeln ueberwachten
Aktie, und sie kann noch am selben Tag melden."): Der Nachtscan laesst
gesperrte Aktien aus, die Mappe hat fuer sie also keinen Kaufpunkt. Damit der
Waechter weiss, wem er sie selbst rechnen muss, steht neben den Eintraegen,
wann eine Aktie freigegeben wurde, abgehakt oder geloescht:
    "freigaben": [{"ticker": "AAPL", "zeit": "2026-10-01T15:00:00Z"}]
aendern() schreibt das selbst fort: Wer vorher gesperrt war und nachher nicht
mehr, kommt dazu; wer wieder gesperrt ist, faellt heraus, ebenso alles, was
aelter ist als FREIGABE_TAGE. freigegeben() liefert die Aktien dazu.

WIRKUNG: gesperrt(ticker) fragt jedes Werkzeug. Die Liste laedt beim ersten
Aufruf und danach hoechstens einmal je NACHLADEN_S Sekunden neu, damit eine
Sperre im laufenden Waechter binnen einer Minute greift. Ohne Token ist sie
leer, und fehler() sagt das. Faellt das Laden aus, gilt der letzte bekannte
Stand, und fehler() nennt den Grund.

NIE EIN KUERZEL INS PROTOKOLL: Die Protokolle der Ablaeufe im Repo heliot sind
oeffentlich, die Liste ist privat (der Gast darf sie nicht sehen). Wer die
Blacklist anwendet, schreibt nur Zahlen ins Protokoll.

Verglichen wird ohne Punkt, Bindestrich und Schraegstrich: BRK.B (Broker,
Nasdaq) und BRK-B (Yahoo) sind dieselbe Aktie. Ein Beobachtungsschluessel wie
RNG|FB zaehlt als RNG.

Aufruf:
    python blacklist.py --selbsttest
    python blacklist.py --zeigen        (braucht DATEN_TOKEN; nur von Hand, nie im Ablauf)
"""

import base64
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone

DATEN_REPO = "mat-schmuck/heliot-daten"
PFAD = "blacklist/blacklist.json"
TOKEN_ENV = "DATEN_TOKEN"
NACHLADEN_S = 60
VERSUCHE = 5
FREIGABE_TAGE = 7      # so lange steht eine Freigabe in der Datei; laenger als jede Luecke bis zum Nachtscan

# Der Stand dieses Prozesses: die gesperrten Schluessel und wann geladen.
_STAND = {"menge": set(), "eintraege": [], "freigaben": [], "zeit": 0.0, "fehler": "", "geladen": False}
_ABRUF = None          # im Selbsttest ersetzbar: (methode, url, token, koerper) -> (status, json)


def schluessel(ticker) -> str:
    """AAPL; BRKB fuer BRK.B und BRK-B; RNG fuer den Beobachtungsschluessel RNG|FB."""
    return re.sub(r"[^A-Z0-9]", "", str(ticker or "").split("|")[0].upper())


def _jetzt_text(jetzt=None) -> str:
    return (jetzt or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _url() -> str:
    return f"https://api.github.com/repos/{DATEN_REPO}/contents/{PFAD}"


def _abruf(methode, url, token, koerper=None):
    if _ABRUF is not None:
        return _ABRUF(methode, url, token, koerper)
    import berichte
    return berichte._abruf(methode, url, token, koerper)


def datei_lesen_ganz(token: str) -> tuple:
    """(Eintraege, Freigaben, sha oder None, Fehlertext). Eine fehlende Datei
    ist keine Stoerung, sondern eine leere Liste."""
    status, j = _abruf("GET", _url(), token)
    if status == 404:
        return [], [], None, ""
    if status != 200 or not isinstance(j, dict):
        return [], [], None, f"GitHub antwortete mit Code {status}"
    try:
        inhalt = base64.b64decode(j.get("content") or "").decode("utf-8")
        daten = json.loads(inhalt) if inhalt.strip() else {}
    except Exception as e:  # noqa: BLE001
        return [], [], j.get("sha"), f"die Datei ist unlesbar ({type(e).__name__})"
    liste = daten.get("eintraege") if isinstance(daten, dict) else None
    frei = daten.get("freigaben") if isinstance(daten, dict) else None
    return ([e for e in (liste or []) if isinstance(e, dict) and schluessel(e.get("ticker"))],
            [f for f in (frei or []) if isinstance(f, dict) and schluessel(f.get("ticker"))], j.get("sha"), "")


def datei_lesen(token: str) -> tuple:
    """(Eintraege, sha oder None, Fehlertext); die Freigaben liest datei_lesen_ganz."""
    liste, _frei, sha, fehler_text = datei_lesen_ganz(token)
    return liste, sha, fehler_text


def datei_text(eintraege, freigaben=None) -> str:
    return json.dumps({"eintraege": eintraege, "freigaben": list(freigaben or [])}, ensure_ascii=False,
                      indent=1) + "\n"


def _zeit_lesen(text):
    try:
        return datetime.strptime(str(text), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def freigaben_fortschreiben(alt, neu, freigaben, jetzt=None) -> list:
    """Die Freigaben nach einer Aenderung von alt zu neu: Wer gesperrt war und
    jetzt nicht mehr, kommt mit der Zeit dazu; wer wieder gesperrt ist, faellt
    heraus, ebenso alles, was aelter ist als FREIGABE_TAGE."""
    jetzt = jetzt or datetime.now(timezone.utc)
    gesperrt_neu = aktive(neu)
    frei_neu = aktive(alt) - gesperrt_neu
    grenze = jetzt.timestamp() - FREIGABE_TAGE * 86400
    raus = []
    for f in freigaben or []:
        k = schluessel(f.get("ticker"))
        z = _zeit_lesen(f.get("zeit"))
        if k in gesperrt_neu or k in frei_neu or z is None or z.timestamp() < grenze:
            continue
        raus.append({"ticker": str(f.get("ticker")), "zeit": f.get("zeit")})
    for e in alt or []:
        if schluessel(e.get("ticker")) in frei_neu:
            raus.append({"ticker": str(e.get("ticker")), "zeit": _jetzt_text(jetzt)})
    return sorted(raus, key=lambda f: schluessel(f.get("ticker")))


def aktive(eintraege) -> set:
    return {schluessel(e.get("ticker")) for e in eintraege or [] if e.get("aktiv", True)}


# ---------------------------------------------------------------------------
# Aenderungen (fuer die App); jede liefert die neue Liste
# ---------------------------------------------------------------------------

def finden(eintraege, ticker):
    k = schluessel(ticker)
    return next((e for e in eintraege or [] if schluessel(e.get("ticker")) == k), None)


def eintragen(eintraege, ticker, name="", jetzt=None) -> list:
    """Auf die Blacklist setzen; steht die Aktie schon darauf, gilt sie wieder."""
    z = _jetzt_text(jetzt)
    raus = [dict(e) for e in eintraege or []]
    e = finden(raus, ticker)
    if e is None:
        raus.append({"ticker": str(ticker).strip().upper(), "name": str(name or "").strip(), "aktiv": True,
                     "seit": z, "geaendert": z})
    else:
        e["aktiv"], e["geaendert"] = True, z
        if name and not e.get("name"):
            e["name"] = str(name).strip()
    return sorted(raus, key=lambda x: schluessel(x.get("ticker")))


def umschalten(eintraege, ticker, aktiv: bool, jetzt=None) -> list:
    """Den Haken setzen oder abnehmen; der Eintrag bleibt."""
    raus = [dict(e) for e in eintraege or []]
    e = finden(raus, ticker)
    if e is not None:
        e["aktiv"], e["geaendert"] = bool(aktiv), _jetzt_text(jetzt)
    return raus


def loeschen(eintraege, ticker) -> list:
    k = schluessel(ticker)
    return [dict(e) for e in eintraege or [] if schluessel(e.get("ticker")) != k]


def aendern(aenderung, token=None, nachricht="Blacklist", melder=print) -> tuple:
    """aenderung(eintraege) -> neue Liste, auf den frischen Stand angewandt
    und geschrieben. Liefert (ok, neue Liste, Fehlertext); wirft nie."""
    token = (token if token is not None else os.environ.get(TOKEN_ENV) or "").strip()
    if not token:
        return False, [], f"{TOKEN_ENV} fehlt"
    letzter = ""
    for versuch in range(1, VERSUCHE + 1):
        liste, frei, sha, fehler = datei_lesen_ganz(token)
        if fehler and sha is None:
            letzter = fehler
        else:
            neu = aenderung(liste)
            frei_neu = freigaben_fortschreiben(liste, neu, frei)
            koerper = {"message": nachricht,
                       "content": base64.b64encode(datei_text(neu, frei_neu).encode("utf-8")).decode("ascii")}
            if sha:
                koerper["sha"] = sha
            status, _j = _abruf("PUT", _url(), token, koerper)
            if status in (200, 201):
                _merken(neu, frei_neu)
                return True, neu, ""
            letzter = f"GitHub antwortete mit Code {status}"
            if status in (401, 403, 404):
                break
        if versuch < VERSUCHE:
            time.sleep(1.0 + random.random() * 2.0)
    melder(f"  Blacklist nicht gespeichert: {letzter}")
    return False, [], letzter


# ---------------------------------------------------------------------------
# Abfrage (fuer jedes Werkzeug)
# ---------------------------------------------------------------------------

def _merken(eintraege, freigaben=None):
    _STAND.update({"menge": aktive(eintraege), "eintraege": list(eintraege), "freigaben": list(freigaben or []),
                   "zeit": time.monotonic(), "fehler": "", "geladen": True})


def nachladen(token=None, zwingend=False) -> None:
    """Den Stand aus dem Datenrepo holen, hoechstens einmal je NACHLADEN_S."""
    token = (token if token is not None else os.environ.get(TOKEN_ENV) or "").strip()
    if not token:
        if not _STAND["geladen"]:
            _STAND["fehler"] = f"{TOKEN_ENV} fehlt"
        return
    if not zwingend and _STAND["geladen"] and time.monotonic() - _STAND["zeit"] < NACHLADEN_S:
        return
    if not zwingend and _STAND["fehler"] and time.monotonic() - _STAND["zeit"] < NACHLADEN_S:
        return                                 # nach einem Fehlschlag nicht in jeder Runde neu
    try:
        liste, frei, _sha, fehler = datei_lesen_ganz(token)
    except Exception as e:  # noqa: BLE001, ein Netzfehler darf kein Werkzeug stoppen
        liste, frei, fehler = [], [], f"{type(e).__name__}: {e}"
    if fehler:
        _STAND["fehler"] = fehler
        _STAND["zeit"] = time.monotonic()
        return
    _merken(liste, frei)


def gesperrt(ticker) -> bool:
    """Steht die Aktie auf der Blacklist (und ist angehakt)?"""
    nachladen()
    return schluessel(ticker) in _STAND["menge"]


def gesperrte() -> set:
    nachladen()
    return set(_STAND["menge"])


def freigegeben(jetzt=None) -> set:
    """Die Aktien (als schluessel), die in den letzten FREIGABE_TAGE Tagen
    freigegeben wurden und jetzt nicht gesperrt sind (Antwort 16)."""
    nachladen()
    grenze = (jetzt or datetime.now(timezone.utc)).timestamp() - FREIGABE_TAGE * 86400
    raus = set()
    for f in _STAND["freigaben"]:
        z = _zeit_lesen(f.get("zeit"))
        if z is not None and z.timestamp() >= grenze:
            raus.add(schluessel(f.get("ticker")))
    return raus - _STAND["menge"]


def fehler() -> str:
    """Warum die Liste zuletzt nicht geladen werden konnte, sonst leer."""
    return _STAND["fehler"]


def geladen() -> bool:
    """Ist in diesem Prozess schon einmal ein Stand angekommen?"""
    return _STAND["geladen"]


def ohne(eintraege, feld="ticker"):
    """Eine Liste ohne gesperrte Aktien: Texte, Paare (Kuerzel zuerst) oder
    dicts mit dem Kuerzel in feld."""
    menge = gesperrte()
    if not menge:
        return list(eintraege or [])

    def kuerzel(x):
        if isinstance(x, dict):
            return x.get(feld)
        if isinstance(x, (tuple, list)):
            return x[0] if x else ""
        return x
    return [x for x in eintraege or [] if schluessel(kuerzel(x)) not in menge]


def ohne_je_kuerzel(werte: dict) -> dict:
    """Ein dict {Kuerzel: ...} ohne die gesperrten Aktien."""
    menge = gesperrte()
    if not menge:
        return dict(werte or {})
    return {t: v for t, v in (werte or {}).items() if schluessel(t) not in menge}


def setzen(menge_oder_eintraege, freigaben=None) -> None:
    """Fuer Pruefungen: den Stand ohne Netz setzen (Kuerzel oder Eintraege);
    freigaben als Kuerzel, freigegeben gerade eben, oder als Eintraege."""
    eintraege = [e if isinstance(e, dict) else {"ticker": e, "aktiv": True} for e in menge_oder_eintraege or []]
    frei = [f if isinstance(f, dict) else {"ticker": f, "zeit": _jetzt_text()} for f in freigaben or []]
    _merken(eintraege, frei)


def zuruecksetzen() -> None:
    _STAND.update({"menge": set(), "eintraege": [], "freigaben": [], "zeit": 0.0, "fehler": "", "geladen": False})


# ---------------------------------------------------------------------------
# Selbsttest (ohne Netz)
# ---------------------------------------------------------------------------

def selbsttest() -> int:
    global _ABRUF
    fehler_liste = []

    def p(name, ok, zusatz=""):
        print(f"  {'OK    ' if ok else 'FEHLER'} {name}" + (f" ({zusatz})" if zusatz and not ok else ""))
        if not ok:
            fehler_liste.append(name)

    print("blacklist.py, Selbsttest")
    p("BRK.B und BRK-B sind dieselbe Aktie", schluessel("BRK.B") == schluessel("brk-b") == "BRKB")
    p("Ein Beobachtungsschluessel zaehlt als seine Aktie", schluessel("RNG|FB") == "RNG")
    z = datetime(2026, 10, 1, 13, 0, tzinfo=timezone.utc)
    l1 = eintragen([], "aapl", "Apple Inc.", z)
    p("Eintragen: Kuerzel gross, aktiv, mit Zeit", l1 == [{"ticker": "AAPL", "name": "Apple Inc.", "aktiv": True,
                                                         "seit": "2026-10-01T13:00:00Z",
                                                         "geaendert": "2026-10-01T13:00:00Z"}], str(l1))
    l2 = umschalten(eintragen(l1, "BRK.B", "Berkshire"), "AAPL", False)
    p("Abhaken laesst den Eintrag stehen und sperrt ihn nicht mehr", len(l2) == 2 and aktive(l2) == {"BRKB"})
    p("Wieder eintragen hakt ihn an", aktive(eintragen(l2, "AAPL")) == {"AAPL", "BRKB"})
    p("Loeschen entfernt ihn ganz", [e["ticker"] for e in loeschen(l2, "aapl")] == ["BRK.B"])
    # Abfrage und Filter
    zuruecksetzen()
    alt = os.environ.pop(TOKEN_ENV, None)
    try:
        p("Ohne Token ist die Liste leer und fragt kein Netz", gesperrt("AAPL") is False and not _STAND["geladen"])
        p("Ohne Token nennt fehler() den Grund", fehler() == f"{TOKEN_ENV} fehlt" and not geladen())
        setzen(["AAPL", "BRK-B", "RNG"])
        p("gesperrt: BRK.B auf der Liste als BRK-B", gesperrt("brk.b") and gesperrt("AAPL") and not gesperrt("MSFT"))
        p("gesperrt: eine Beobachtung RNG|FB", gesperrt("RNG|FB") and not gesperrt("RNGX|1"))
        p("ohne: Texte, Paare und dicts",
          ohne(["AAPL", "MSFT"]) == ["MSFT"] and ohne([("AAPL", "Apple"), ("NVDA", "Nvidia")]) == [("NVDA", "Nvidia")]
          and ohne([{"ticker": "BRK.B"}, {"ticker": "X"}]) == [{"ticker": "X"}])
        p("ohne_je_kuerzel: ein dict nach Kuerzel",
          ohne_je_kuerzel({"AAPL": 1, "MSFT": 2, "BRK.B": 3}) == {"MSFT": 2})
        p("Nach dem Setzen ist kein Fehler vermerkt", fehler() == "" and geladen())
        # Datei ueber eine nachgestellte Schnittstelle
        speicher = {"inhalt": None, "sha": None, "konflikt": 1}

        def abruf(methode, url, token, koerper=None):
            if methode == "GET":
                if speicher["inhalt"] is None:
                    return 404, {}
                return 200, {"content": base64.b64encode(speicher["inhalt"].encode()).decode(), "sha": speicher["sha"]}
            if speicher["konflikt"]:
                speicher["konflikt"] -= 1
                speicher["inhalt"], speicher["sha"] = datei_text([{"ticker": "TSLA", "aktiv": True}]), "s1"
                return 409, {}
            speicher["inhalt"], speicher["sha"] = base64.b64decode(koerper["content"]).decode(), "s2"
            return 200, {}
        _ABRUF = abruf
        ok, neu, f = aendern(lambda liste: eintragen(liste, "NVDA", "Nvidia"), token="t", melder=lambda *a: None)
        p("Aendern nach einem Konflikt: neu gelesen, die fremde Aenderung bleibt erhalten",
          ok and [e["ticker"] for e in neu] == ["NVDA", "TSLA"], f"{ok} {neu} {f}")
        zuruecksetzen()
        nachladen(token="t")
        p("Nachladen holt den gespeicherten Stand", _STAND["geladen"] and _STAND["menge"] == {"NVDA", "TSLA"})
        _ABRUF = lambda *a, **k: (500, {})  # noqa: E731
        nachladen(token="t", zwingend=True)
        p("Faellt das Laden aus, gilt der letzte Stand und der Grund steht da",
          _STAND["menge"] == {"NVDA", "TSLA"} and "500" in fehler())
        anrufe = []
        _ABRUF = lambda *a, **k: (anrufe.append(1), (500, {}))[1]  # noqa: E731
        nachladen(token="t")
        p("Nach einem Fehlschlag wird nicht in jeder Runde neu gefragt", not anrufe)
        ok, _neu, f = aendern(lambda liste: liste, token="", melder=lambda *a: None)
        p("Ohne Token wird nichts geschrieben", not ok and TOKEN_ENV in f)
        # Freigaben (Antwort 16 vom 01.10.2026)
        t0 = datetime(2026, 10, 1, 13, 0, tzinfo=timezone.utc)
        a = [{"ticker": "AAPL", "aktiv": True}, {"ticker": "BRK.B", "aktiv": True}, {"ticker": "X", "aktiv": False}]
        a1 = umschalten(a, "AAPL", False)
        f1 = freigaben_fortschreiben(a, a1, [], t0)
        p("Freigabe: abgehakt kommt mit der Zeit in die Freigaben",
          f1 == [{"ticker": "AAPL", "zeit": "2026-10-01T13:00:00Z"}], str(f1))
        a2 = loeschen(loeschen(a1, "BRK-B"), "X")
        f2 = freigaben_fortschreiben(a1, a2, f1, t0)
        p("Freigabe: geloescht zaehlt auch, ein schon abgehakter Eintrag nicht, die alte bleibt",
          [x["ticker"] for x in f2] == ["AAPL", "BRK.B"], str(f2))
        f3 = freigaben_fortschreiben(a2, umschalten(a2, "AAPL", True), f2, t0)
        p("Freigabe: wieder gesperrt faellt heraus", [x["ticker"] for x in f3] == ["BRK.B"], str(f3))
        spaeter = datetime(2026, 10, 9, 13, 0, tzinfo=timezone.utc)
        p("Freigabe: nach sieben Tagen faellt sie heraus",
          freigaben_fortschreiben(a2, a2, f2, spaeter) == [], str(freigaben_fortschreiben(a2, a2, f2, spaeter)))
        speicher.update({"inhalt": datei_text([{"ticker": "NVDA", "aktiv": True}]), "sha": "s3", "konflikt": 0})
        _ABRUF = abruf
        ok, neu, f = aendern(lambda liste: umschalten(liste, "NVDA", False), token="t", melder=lambda *a: None)
        ganz = json.loads(speicher["inhalt"])
        p("Aendern schreibt die Freigabe in die Datei und merkt sie sich",
          ok and [x["ticker"] for x in ganz["freigaben"]] == ["NVDA"] and freigegeben() == {"NVDA"}, str(ganz))
        ok, neu, f = aendern(lambda liste: umschalten(liste, "NVDA", True), token="t", melder=lambda *a: None)
        p("Wieder gesperrt: keine Freigabe mehr, in der Datei und im Stand",
          ok and json.loads(speicher["inhalt"])["freigaben"] == [] and freigegeben() == set())
        setzen(["AAPL"], freigaben=["MSFT", "AAPL"])
        p("freigegeben: nur, was jetzt nicht gesperrt ist", freigegeben() == {"MSFT"})
        alt_f = [{"ticker": "OLD", "zeit": "2026-01-01T00:00:00Z"}]
        setzen([], freigaben=alt_f)
        p("freigegeben: eine alte Freigabe zaehlt nicht mehr", freigegeben() == set())
    finally:
        _ABRUF = None
        zuruecksetzen()
        if alt is not None:
            os.environ[TOKEN_ENV] = alt
    print("Ergebnis:", "alles bestanden" if not fehler_liste else f"{len(fehler_liste)} Fehler")
    return 1 if fehler_liste else 0


def zeigen() -> int:
    token = (os.environ.get(TOKEN_ENV) or "").strip()
    if not token:
        print(f"{TOKEN_ENV} fehlt.")
        return 1
    if os.environ.get("GITHUB_ACTIONS"):
        print("Nicht im Ablauf: Das Protokoll ist oeffentlich, die Blacklist privat.")
        return 1
    liste, _sha, f = datei_lesen(token)
    if f:
        print("Nicht lesbar:", f)
        return 1
    for e in liste:
        print(f"{e.get('ticker')}, {e.get('name') or 'ohne Namen'}: {'gesperrt' if e.get('aktiv', True) else 'abgehakt'}")
    print(f"{len(aktive(liste))} von {len(liste)} gesperrt")
    return 0


if __name__ == "__main__":
    if "--selbsttest" in sys.argv:
        sys.exit(selbsttest())
    if "--zeigen" in sys.argv:
        sys.exit(zeigen())
    print(__doc__)
