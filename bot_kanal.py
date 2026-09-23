#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BOT-KANAL: die Signale des Waechters als JSON fuer den degirobot
=================================================================
Gerhards Regelwerk fuer den Trading-Bot vom 22.09.2026 (R15, R16) und
Mathias' Entscheide vom selben Abend ("Ausstiege gemaess den Meldungen
durchfuehren"). Der Vertrag steht in degirobot/KANAL.md; dieses Modul
haelt sich Zeichen fuer Zeichen daran.

WAS SICH FUER MATHIAS AENDERT: nichts. Die lesbaren Meldungen im
bisherigen Kanal bleiben unveraendert, samt Titel, Wortlaut,
Dringlichkeit und Klick-Adresse. Dieses Modul schickt DANEBEN je Signal
eine Maschinenzeile in einen eigenen Kanal, den nur der Bot liest.

ZWEI KANAELE, beide als Geheimnis:
    BOT_KAUFKANAL      eine Zeile je ausgeloestem Kaufpunkt
    BOT_VERKAUFSKANAL  eine Zeile je Ausstieg
Fehlt eine der zwei Umgebungsvariablen, geschieht fuer diesen Kanal gar
nichts; der Waechter verhaelt sich dann wie vor diesem Einbau.

DIE ZEILE IST DER GANZE RUMPF. Genau fuenf Felder beim Kauf, genau vier
beim Verkauf, in der Reihenfolge des Vertrags, kein Text davor oder
danach. Der Titel der Nachricht ist frei (der Bot liest nur den Rumpf)
und hilft Mathias beim Mitlesen in der ntfy-App.

EINE ZEILE JE KAUFPUNKT, nicht je Aktie (Vertrag): Zwei gerissene Marken
derselben Aktie sind zwei Nachrichten. Gesendet wird sofort beim
Ausloesen, nie gesammelt, weil dem Bot die Eingangszeit beim ntfy-Server
als Entstehungszeit gilt.

OHNE STOP KEIN KAUFSIGNAL: Der Bot legt nach der Ausfuehrung sofort eine
Stop-Loss-Order zum Stop; ohne Stop wuerde eine ungesicherte Position
entstehen. Fehlt der Stop, wird die Zeile NICHT gesendet und der
Fehlschlag laut genannt. In der Mappe ist der Stop gefuellt, und der
Waechter zieht den Zehn-Prozent-Deckel ohnehin ueber jeden Stop nach.

KUERZEL: Der Waechter rechnet mit Yahoo-Symbolen, dort trennt ein
Bindestrich die Aktienklasse (BRK-B). Der Broker schreibt sie mit Punkt
(BRK.B), und genau so verlangt es der Vertrag; broker_symbol() ist die
Gegenrichtung zu rs_universum.yahoo_symbol().

Aufruf:
    python bot_kanal.py --selbsttest
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date

KAUF = "kauf"
VERKAUF = "verkauf"

ENV = {KAUF: "BOT_KAUFKANAL", VERKAUF: "BOT_VERKAUFSKANAL"}
TROCKEN_ENV = "BOT_TROCKEN"        # 1 = nur ausgeben, nichts senden (Pruefung)
BASIS = "https://ntfy.sh/"
FRIST = 15                         # Sekunden je Versuch
PAUSE = 3.0                        # Sekunden vor dem zweiten Versuch
VERSUCHE = 2                       # Vertrag: bei Antwort ungleich 200 noch einmal

# Im Selbsttest ersetzbar, damit die Sendung ohne Netz geprueft werden kann.
_OEFFNER = urllib.request.urlopen


# ---------------------------------------------------------------------------
# Bausteine
# ---------------------------------------------------------------------------

def kanal(art: str) -> str | None:
    """Der Kanalname aus der Umgebung, oder None. Der Name selbst wird
    NIE ausgegeben oder protokolliert; er ist ein Geheimnis."""
    name = (os.environ.get(ENV.get(art, "")) or "").strip()
    return name or None


def trocken() -> bool:
    return (os.environ.get(TROCKEN_ENV) or "").strip() == "1"


def broker_symbol(sym) -> str:
    """Yahoo schreibt Klassen mit Bindestrich (BRK-B), der Broker mit
    Punkt (BRK.B). Gegenrichtung zu rs_universum.yahoo_symbol()."""
    return str(sym or "").strip().upper().replace("-", ".")


def iso_woche(tag=None) -> str:
    """Die ISO-Woche in der Form JJJJ-Wnn, zwei Ziffern, Montag beginnt
    die Woche. Uebergeben wird der NEW YORKER Handelstag; in Wien ist es
    beim Nachtlauf schon der naechste Tag."""
    tag = tag or date.today()
    jahr, woche, _wt = tag.isocalendar()
    return "%04d-W%02d" % (int(jahr), int(woche))


def betrag(wert) -> float | None:
    """Dollar als Zahl. Auf den Cent gerundet; unter einem Dollar auf vier
    Stellen, damit bei einem Pennywert nichts verlorengeht."""
    if wert is None:
        return None
    try:
        z = float(wert)
    except (TypeError, ValueError):
        return None
    if z != z or z <= 0:               # NaN oder unbrauchbar
        return None
    return round(z, 2 if z >= 1.0 else 4)


def anteil_fuer(aktion) -> float | None:
    """Welcher Anteil zu einer Ausstiegs-Aktion des Exit-Regelwerks gehoert.

    None heisst: kein Ausstieg fuer den Bot. Wedge Drop und Zeitdeckel
    lassen eine Wahl, INFORMATIONEN sind keine Ausstiege; beide kommen
    hier gar nicht vor und wuerden None ergeben."""
    ganz = ("stop_raus", "round_trip_raus", "trail_raus")
    if aktion in ganz:
        return 1
    if aktion == "teilverkauf":
        return 0.5
    return None


def _zeile(felder: dict) -> str:
    """Genau eine JSON-Zeile, ohne Leerzeichen, Umlaute unverstellt."""
    return json.dumps(felder, separators=(",", ":"), ensure_ascii=False)


def kauf_zeile(ticker, name, kaufpunkt, stop, tag=None) -> str | None:
    """Die fuenf Felder des Kaufkanals. None, wenn eine Angabe fehlt."""
    t = broker_symbol(ticker)
    kp, st = betrag(kaufpunkt), betrag(stop)
    if not t or kp is None or st is None:
        return None
    return _zeile({"ticker": t, "name": str(name or "").strip(),
                   "woche": iso_woche(tag), "kaufpunkt": kp, "stop": st})


def verkauf_zeile(ticker, name, anteil, tag=None) -> str | None:
    """Die vier Felder des Verkaufskanals. anteil 1 = ganze Position,
    0.5 = Teilverkauf; etwas anderes gibt es nicht."""
    t = broker_symbol(ticker)
    if not t:
        return None
    a = 1 if float(anteil) >= 1 else 0.5
    return _zeile({"ticker": t, "name": str(name or "").strip(),
                   "woche": iso_woche(tag), "anteil": a})


# ---------------------------------------------------------------------------
# Sendung
# ---------------------------------------------------------------------------

def senden(art: str, zeile: str, titel: str | None = None, melder=print) -> bool:
    """Eine Zeile in den Kanal. Bei einer Antwort ungleich 200 ein zweiter
    Versuch nach kurzer Pause; danach wird der Fehlschlag genannt.

    Wirft NIE: Der Waechter darf an der Bot-Sendung nicht abbrechen. Der
    Kanalname steht in keiner Meldung."""
    ziel = kanal(art)
    if not ziel:
        return False
    if trocken():
        melder(f"  (Trocken) {art}: {zeile}")
        return True
    kopf = {"Priority": "default"}
    if titel:
        kopf["Title"] = titel.encode("utf-8")
    letzter = ""
    for versuch in range(1, VERSUCHE + 1):
        try:
            anfrage = urllib.request.Request(BASIS + ziel, data=zeile.encode("utf-8"),
                                             headers=kopf, method="POST")
            with _OEFFNER(anfrage, timeout=FRIST) as antwort:
                code = getattr(antwort, "status", None) or antwort.getcode()
                if int(code) == 200:
                    return True
                letzter = f"Antwort {code}"
        except urllib.error.HTTPError as e:
            letzter = f"Antwort {e.code}"
        except Exception as e:                                  # noqa: BLE001
            letzter = f"{type(e).__name__}: {e}"
        if versuch < VERSUCHE:
            time.sleep(PAUSE)
    melder(f"  Bot-{art}kanal nicht erreicht ({letzter}); der Bot kann diese "
           f"Nachricht nicht ersetzen.")
    return False


def sende_kauf(treffer: list[dict], tag=None, melder=print,
               feld: str = "kaufpunkt") -> int:
    """Je Treffer eine Kaufzeile. Rueckgabe: Zahl der gesendeten Zeilen.

    `feld` sagt, welcher Wert der Kaufpunkt ist: beim Einstieg am Folgetag
    eines Lueckentags ist das der EINSTIEG, nicht die Marke aus der Mappe."""
    if not kanal(KAUF) or not treffer:
        return 0
    raus = 0
    for t in treffer:
        if t.get("alarm"):
            # DIE SECHS ALARM-MUSTER NICHT (Gerhard, 22.09.2026, O10): Sie
            # melden als Auskunft, nicht als Auftrag. Das steht hier als
            # Netz, damit es auch gilt, wenn ein Treffer je einmal ueber
            # einen anderen Sendeweg laeuft.
            continue
        zeile = kauf_zeile(t.get("ticker"), t.get("firma"),
                           t.get(feld, t.get("kaufpunkt")), t.get("stop"), tag)
        if zeile is None:
            melder(f"  Bot-Kaufkanal: {str(t.get('ticker') or '?')} ohne Stop "
                   f"oder Kaufpunkt, nicht gesendet.")
            continue
        if senden(KAUF, zeile, f"Kauf {broker_symbol(t.get('ticker'))}", melder):
            raus += 1
    return raus


def sende_verkauf(eintraege: list[dict], tag=None, melder=print) -> int:
    """Je Eintrag eine Verkaufszeile; erwartet ticker, firma und anteil."""
    if not kanal(VERKAUF) or not eintraege:
        return 0
    raus = 0
    for e in eintraege:
        zeile = verkauf_zeile(e.get("ticker"), e.get("firma"), e.get("anteil", 1), tag)
        if zeile is None:
            melder("  Bot-Verkaufskanal: Eintrag ohne Kürzel, nicht gesendet.")
            continue
        if senden(VERKAUF, zeile, f"Verkauf {broker_symbol(e.get('ticker'))}", melder):
            raus += 1
    return raus


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

def selbsttest() -> int:
    fehler = []
    alle = []

    def pruefe(name, bedingung, zusatz=""):
        print(f"  {'ok  ' if bedingung else 'FEHL'} {name}"
              + (f" — {zusatz}" if zusatz else ""))
        alle.append(name)
        if not bedingung:
            fehler.append(name)

    print("BOT-KANAL")
    tag = date(2026, 9, 23)                     # Mittwoch der Woche 2026-W39

    # 1. Kürzel und Woche
    pruefe("Kürzel: Bindestrich wird Punkt", broker_symbol("brk-b") == "BRK.B")
    pruefe("Kürzel: gewöhnliches bleibt", broker_symbol(" pvla ") == "PVLA")
    pruefe("Woche: zwei Ziffern", iso_woche(tag) == "2026-W39", iso_woche(tag))
    pruefe("Woche: einstellige Woche mit Null", iso_woche(date(2026, 1, 8)) == "2026-W02",
           iso_woche(date(2026, 1, 8)))
    pruefe("Woche: Montag gehört zur neuen Woche",
           iso_woche(date(2026, 9, 21)) == "2026-W39" and iso_woche(date(2026, 9, 20)) == "2026-W38")

    # 2. Beträge
    pruefe("Betrag: auf den Cent", betrag(158.0149) == 158.01, str(betrag(158.0149)))
    pruefe("Betrag: Pennywert vier Stellen", betrag(0.87654) == 0.8765, str(betrag(0.87654)))
    pruefe("Betrag: leer bleibt leer", betrag(None) is None)
    pruefe("Betrag: null oder negativ ist unbrauchbar",
           betrag(0) is None and betrag(-3) is None)
    pruefe("Betrag: Text ist unbrauchbar", betrag("viel") is None)

    # 3. Die Zeile, Zeichen für Zeichen wie im Vertrag
    soll = ('{"ticker":"PVLA","name":"Palvella Therapeutics Inc","woche":"2026-W39",'
            '"kaufpunkt":158.01,"stop":142.21}')
    ist = kauf_zeile("PVLA", "Palvella Therapeutics Inc", 158.01, 142.21, tag)
    pruefe("Kaufzeile: Wortlaut des Vertrags", ist == soll, str(ist))
    pruefe("Kaufzeile: eine einzige Zeile", "\n" not in (ist or "x"))
    pruefe("Kaufzeile: genau fünf Felder",
           list(json.loads(ist).keys()) == ["ticker", "name", "woche", "kaufpunkt", "stop"])
    pruefe("Kaufzeile: ohne Stop gar keine Zeile",
           kauf_zeile("PVLA", "P", 158.01, None, tag) is None)
    pruefe("Kaufzeile: ohne Kürzel gar keine Zeile",
           kauf_zeile("", "P", 158.01, 142.21, tag) is None)
    soll_v = '{"ticker":"PVLA","name":"Palvella Therapeutics Inc","woche":"2026-W39","anteil":1}'
    ist_v = verkauf_zeile("PVLA", "Palvella Therapeutics Inc", 1, tag)
    pruefe("Verkaufszeile: Wortlaut des Vertrags", ist_v == soll_v, str(ist_v))
    pruefe("Verkaufszeile: genau vier Felder",
           list(json.loads(ist_v).keys()) == ["ticker", "name", "woche", "anteil"])
    pruefe("Verkaufszeile: Teilverkauf ist 0.5",
           json.loads(verkauf_zeile("X", "", 0.5, tag))["anteil"] == 0.5)
    pruefe("Verkaufszeile: nur 1 oder 0.5",
           json.loads(verkauf_zeile("X", "", 0.3, tag))["anteil"] == 0.5
           and json.loads(verkauf_zeile("X", "", 2, tag))["anteil"] == 1)
    pruefe("Umlaut im Namen bleibt lesbar",
           '"name":"Müller & Söhne"' in verkauf_zeile("X", "Müller & Söhne", 1, tag))

    # 3b. Welche Ausstiege gelten
    pruefe("Ausstieg: Stop gerissen ist ganz raus", anteil_fuer("stop_raus") == 1)
    pruefe("Ausstieg: Gewinn verpufft ist ganz raus", anteil_fuer("round_trip_raus") == 1)
    pruefe("Ausstieg: Nachzieh-Linie ist ganz raus", anteil_fuer("trail_raus") == 1)
    pruefe("Ausstieg: Teilverkauf ist die Hälfte", anteil_fuer("teilverkauf") == 0.5)
    pruefe("Kein Ausstieg: Wedge Drop und Unbekanntes",
           anteil_fuer("wedge_drop") is None and anteil_fuer(None) is None
           and anteil_fuer("zeitdeckel") is None)

    # 4. Sendung mit eingesetztem Öffner
    echt = _OEFFNER
    umgebung = {k: os.environ.get(k) for k in (ENV[KAUF], ENV[VERKAUF], TROCKEN_ENV)}
    try:
        os.environ[ENV[KAUF]] = "pruefkanal-kauf"
        os.environ[ENV[VERKAUF]] = "pruefkanal-verkauf"
        os.environ.pop(TROCKEN_ENV, None)
        gesehen = []

        class Antwort:
            def __init__(self, code):
                self.status = code

            def getcode(self):
                return self.status

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def guter_oeffner(anfrage, timeout=None):
            gesehen.append({"url": anfrage.full_url, "rumpf": anfrage.data.decode("utf-8"),
                            "titel": anfrage.headers.get("Title"),
                            "methode": anfrage.get_method()})
            return Antwort(200)

        globals()["_OEFFNER"] = guter_oeffner
        raus = sende_kauf([{"ticker": "BRK-B", "firma": "Berkshire Hathaway",
                            "kaufpunkt": 512.345, "stop": 470.0}], tag, melder=lambda *_a: None)
        pruefe("Sendung: eine Zeile gesendet", raus == 1 and len(gesehen) == 1, str(raus))
        pruefe("Sendung: POST auf ntfy",
               gesehen and gesehen[0]["methode"] == "POST"
               and gesehen[0]["url"].startswith(BASIS))
        pruefe("Sendung: Rumpf ist die Zeile, Klasse mit Punkt",
               gesehen and json.loads(gesehen[0]["rumpf"])["ticker"] == "BRK.B"
               and json.loads(gesehen[0]["rumpf"])["kaufpunkt"] == 512.35)
        pruefe("Sendung: Titel nennt das Kürzel",
               gesehen and gesehen[0]["titel"] == "Kauf BRK.B".encode("utf-8"))

        gesehen.clear()
        raus = sende_kauf([{"ticker": "AAA", "firma": "A", "kaufpunkt": 10.0, "stop": 9.0},
                           {"ticker": "AAA", "firma": "A", "kaufpunkt": 12.0, "stop": 11.0}],
                          tag, melder=lambda *_a: None)
        pruefe("Zwei Marken derselben Aktie sind zwei Nachrichten",
               raus == 2 and len(gesehen) == 2)

        gesehen.clear()
        raus = sende_kauf([{"ticker": "DDD", "firma": "D", "kaufpunkt": 10.0,
                            "stop": 9.0, "alarm": True}], tag, melder=lambda *_a: None)
        pruefe("Alarm-Muster gehen NICHT in den Kaufkanal (O10)",
               raus == 0 and not gesehen)

        gesehen.clear()
        raus = sende_kauf([{"ticker": "BBB", "firma": "B", "einstieg": 20.0,
                            "kaufpunkt": 18.0, "stop": 17.0}], tag,
                          melder=lambda *_a: None, feld="einstieg")
        pruefe("Einstieg am Folgetag zählt als Kaufpunkt",
               gesehen and json.loads(gesehen[0]["rumpf"])["kaufpunkt"] == 20.0)

        gesehen.clear()
        raus = sende_verkauf([{"ticker": "CCC", "firma": "C", "anteil": 0.5}], tag,
                            melder=lambda *_a: None)
        pruefe("Verkauf: gesendet und halber Anteil",
               raus == 1 and json.loads(gesehen[0]["rumpf"])["anteil"] == 0.5)

        # Fehlschlag mit Wiederholung
        versuche = []

        def boeser_oeffner(anfrage, timeout=None):
            versuche.append(1)
            return Antwort(500)

        globals()["_OEFFNER"] = boeser_oeffner
        merk = PAUSE
        globals()["PAUSE"] = 0.0
        gesagt = []
        ok = senden(KAUF, '{"a":1}', "Kauf X", melder=gesagt.append)
        globals()["PAUSE"] = merk
        pruefe("Fehlschlag: zwei Versuche, dann ehrlich melden",
               ok is False and len(versuche) == 2 and len(gesagt) == 1, str(len(versuche)))
        pruefe("Fehlschlag: Meldung nennt den Kanalnamen nicht",
               gesagt and "pruefkanal" not in gesagt[0], str(gesagt[:1]))

        # Trockenlauf
        os.environ[TROCKEN_ENV] = "1"
        gesehen.clear()
        gesagt = []
        ok = senden(KAUF, '{"a":1}', "Kauf X", melder=gesagt.append)
        pruefe("Trockenlauf: nichts gesendet, nur ausgegeben",
               ok is True and not gesehen and len(gesagt) == 1)

        # Ohne Kanal geschieht nichts
        os.environ.pop(TROCKEN_ENV, None)
        os.environ.pop(ENV[KAUF], None)
        gesehen.clear()
        pruefe("Ohne Kanal: keine Sendung, kein Fehler",
               sende_kauf([{"ticker": "AAA", "firma": "A", "kaufpunkt": 10.0,
                            "stop": 9.0}], tag, melder=lambda *_a: None) == 0
               and not gesehen)
    finally:
        globals()["_OEFFNER"] = echt
        for k, v in umgebung.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    print(f"\n{len(alle) - len(fehler)} von {len(alle)} bestanden")
    return 1 if fehler else 0


if __name__ == "__main__":
    if "--selbsttest" in sys.argv:
        sys.exit(selbsttest())
    print(__doc__)
