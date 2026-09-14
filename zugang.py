#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZUGANG — Anmeldung zur Heliot-App: festes Passwort und Gastpasswoerter
=====================================================================
Mathias, 13.09.2026: "Gerhard haette gern einen Testzugang auf das Portal
mit Passwort, Zeit eine Stunde, der keinen Zugang auf sensible Bereiche hat.
Wir moechten diese Testzugaenge mittels Generierung eines zufaellig
generierten Passwortes einbauen, das nur wir mit einem Knopf innerhalb des
Tools generieren koennen. Die Gastzugaenge duerfen keinerlei Aenderungen
vornehmen, Listen hochladen etc., nur Lesezugriff haben. Das Tool selbst soll
zuerst mit einem von uns festgelegten Passwort geschuetzt werden."

Entscheide vom selben Abend: Das Gastpasswort besteht aus Buchstaben statt
aus acht Ziffern ("ein Buchstabenpasswort, ohne PIN"); es gilt 60 Minuten;
Gaeste duerfen Einzelabfrage und Liste benutzen; das Passwort gibt weiter,
wer es erzeugt hat.

ZWEI STREAMLIT-SECRETS, beide traegt Mathias selbst ein, die Werte stehen
nie im Repo:
  * HELIOT_PASSWORT: das feste Passwort fuer den vollen Zugang. Mathias und
    Gerhard muessen es kennen. Gross- und Kleinschreibung zaehlt.
  * GAST_GEHEIMNIS: eine lange Zufallszeichenkette, aus der die
    Gastpasswoerter errechnet werden. Niemand muss sie sich merken. Wer sie
    aendert, macht alle ausgegebenen Gastpasswoerter sofort ungueltig.
  Warum nicht das feste Passwort als Schluessel: Wer ein Gastpasswort
  bekommt, koennte damit ein schwaches festes Passwort offline erraten.

WARUM GERECHNET UND NICHT GESPEICHERT: Die App hat keinen Speicher, der
einen Neustart ueberlebt, und im oeffentlichen Repo darf davon nichts stehen.
Das Gastpasswort ist deshalb ein HMAC aus dem Geheimnis und dem
Zehn-Minuten-Fenster der Erzeugung, umgeschrieben in fuenf Silben aus
Mitlaut und Selbstlaut: zehn Kleinbuchstaben, 70 hoch 5, also rund 1,7
Milliarden Moeglichkeiten. Geprueft wird gegen das laufende und die sechs
vorigen Fenster; ein Gastpasswort gilt damit mindestens 60 und hoechstens
70 Minuten. Wer innerhalb derselben zehn Minuten zweimal erzeugt, bekommt
dasselbe Passwort.

WARUM SILBEN: Das Passwort wird weitergesagt oder weitergeschickt und am
iPhone mit VoiceOver eingetippt. "kobelimanu" laesst sich hoeren und
schreiben, eine Zeichenfolge wie "qzkxwmtr" nicht. Gross- und
Kleinschreibung, Leerzeichen und Bindestriche zaehlen beim Gastpasswort
nicht.

DIE BREMSE gilt fuer die ganze App, nicht nur fuer eine Browsersitzung,
denn eine neue Sitzung kostet nur ein Neuladen der Seite:
  * je Sitzung nach fuenf Fehlversuchen hintereinander eine Minute Pause;
  * fuer alle zusammen nach 20 Fehlversuchen in zehn Minuten eine Sperre,
    bis der aelteste davon zehn Minuten alt ist. In dieser Zeit sind auch
    Mathias und Gerhard ausgesperrt; ein Rateangriff kommt dafuer auf
    hoechstens 2.880 Versuche am Tag, und die Chance, damit ein gueltiges
    Gastpasswort zu treffen, liegt unter einem Hunderttausendstel je Tag.

ANGEMELDET BLEIBEN (Mathias, 14.09.2026: "Füge bei unserem Webtool unbedingt
die Möglichkeit hinzu, angemeldet zu bleiben."). Streamlit merkt die
Anmeldung nur je Browsersitzung; nach dem Neuladen oder in einem neuen Tab
war sie weg. Wer beim Anmelden "Angemeldet bleiben" anhakt, bekommt deshalb
einen Eintrag im Speicher des eigenen Browsers (localStorage, Name
heliot_zugang):
  * Inhalt "v1.<rolle>.<ende>.<zufall>.<pruefwert>": Rolle voll oder gast,
    Ende als Unix-Zeit, zwoelf Zufallszeichen und ein HMAC-SHA256 darueber.
    Das Passwort steht NICHT darin, und der Eintrag laesst sich nicht
    faelschen oder verlaengern, ohne beide Secrets zu kennen.
  * Schluessel aus BEIDEN Secrets: Wer HELIOT_PASSWORT oder GAST_GEHEIMNIS
    aendert, meldet damit auf allen Geraeten ab. Ohne GAST_GEHEIMNIS gibt es
    kein Angemeldet-Bleiben; ein Pruefwert, der nur am festen Passwort
    haengt, liesse ein schwaches Passwort offline erraten.
  * Voller Zugang: 30 Tage ab dem letzten Oeffnen der App, jede neue
    Sitzung stellt den Eintrag neu aus. Gastzugang: nie laenger als das
    Gastpasswort gilt.
  * Safari auf dem iPhone loescht, was eine Seite selbst im Browser
    speichert, nach sieben Tagen ohne Besuch. Wer die App mindestens einmal
    in der Woche oeffnet, bleibt angemeldet; sonst wird einmal neu
    eingegeben.
  * Ein ungueltiger oder abgelaufener Eintrag zaehlt nicht als Fehlversuch;
    die App loescht ihn und zeigt das Anmeldefeld.
  * WARUM KEIN COOKIE MEHR (gemessen 14.09.2026): Die erste Fassung schrieb
    ein Cookie und las es ueber st.context.cookies. Lokal ging das, auf
    Streamlit Community Cloud kommt das Cookie aber nicht bei der App an:
    Ein ungueltiges Test-Cookie blieb dort stehen, und der Loesch-Baustein,
    den die App lokal in die Seite schreibt, fehlte in der Cloud ganz. Den
    Eintrag liest deshalb der Browser selbst und meldet ihn ueber eine
    unsichtbare Komponente (speicher_js) an die App. localStorage statt
    Cookie, weil ein Cookie bei jeder Anfrage mitgeschickt wuerde, obwohl
    der Server es gar nicht bekommt; ein Cookie der ersten Fassung wird beim
    Lesen uebernommen und geloescht.

Aufruf:
  python zugang.py --selbsttest
"""

import argparse
import hashlib
import hmac
import json
import re
import secrets
import string
import sys
import threading
from collections import deque
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

MITLAUTE = "bdfgklmnprstwz"
SELBSTLAUTE = "aeiou"
SILBEN = 5
FENSTER_S = 600            # ein Fenster sind zehn Minuten
FENSTER_GUELTIG = 7        # das laufende und sechs vorige: 60 bis 70 Minuten

SITZUNG_GRENZE = 5         # Fehlversuche hintereinander bis zur Pause
SITZUNG_PAUSE_S = 60
GESAMT_GRENZE = 20         # Fehlversuche aller Sitzungen im Zeitraum
GESAMT_ZEITRAUM_S = 600

BLEIBEN_NAME = "heliot_zugang"   # Name im Browserspeicher, auch das Cookie der ersten Fassung
BLEIBEN_TAGE = 30          # voller Zugang: so lange ab dem letzten Oeffnen
BLEIBEN_ROLLEN = ("voll", "gast")
_BLEIBEN_FORM = re.compile(r"v1\.(voll|gast)\.(\d{10})\.([A-Za-z0-9_-]{12})\.([0-9a-f]{32})")
_SPEICHER_ZEICHEN = re.compile(r"[A-Za-z0-9._-]*")
SPEICHER_AUFTRAEGE = ("lesen", "setzen", "loeschen", "ruhe")


def gast_passwort(geheimnis: str, fenster: int) -> str:
    """Das Gastpasswort eines Zehn-Minuten-Fensters: fuenf Silben aus
    Mitlaut und Selbstlaut, errechnet aus HMAC-SHA256 des Geheimnisses."""
    mac = hmac.new(geheimnis.encode("utf-8"),
                   f"heliot-gast|{fenster}".encode("ascii"),
                   hashlib.sha256).digest()
    zahl = int.from_bytes(mac[:8], "big")
    silben = []
    for _ in range(SILBEN):
        zahl, m = divmod(zahl, len(MITLAUTE))
        zahl, s = divmod(zahl, len(SELBSTLAUTE))
        silben.append(MITLAUTE[m] + SELBSTLAUTE[s])
    return "".join(silben)


def fenster_von(zeitpunkt: float) -> int:
    return int(zeitpunkt // FENSTER_S)


def erzeuge(geheimnis: str, jetzt: float) -> tuple:
    """(Gastpasswort, Ende der Gueltigkeit als Unix-Zeit) fuer jetzt."""
    f = fenster_von(jetzt)
    return gast_passwort(geheimnis, f), float((f + FENSTER_GUELTIG) * FENSTER_S)


def normalisiere_gast(eingabe: str) -> str:
    """Nur die Buchstaben a bis z zaehlen, klein geschrieben."""
    return "".join(z for z in (eingabe or "").lower() if z in string.ascii_lowercase)


def pruefe_gast(eingabe: str, geheimnis: str, jetzt: float):
    """Ende der Gueltigkeit, wenn die Eingabe ein gueltiges Gastpasswort
    ist, sonst None. Alle sieben Fenster werden immer verglichen."""
    if not geheimnis:
        return None
    kandidat = normalisiere_gast(eingabe).encode("ascii")
    if len(kandidat) != 2 * SILBEN:
        return None
    f = fenster_von(jetzt)
    ende = None
    for alter in range(FENSTER_GUELTIG):
        g = f - alter
        if hmac.compare_digest(kandidat, gast_passwort(geheimnis, g).encode("ascii")):
            ende = float((g + FENSTER_GUELTIG) * FENSTER_S)
    return ende


def pruefe_passwort(eingabe: str, passwort: str) -> bool:
    """Das feste Passwort. Gross- und Kleinschreibung zaehlt; nur Leerzeichen
    am Anfang und am Ende fallen weg, wie sie beim Kopieren entstehen."""
    if not passwort or not passwort.strip():
        return False
    return hmac.compare_digest((eingabe or "").strip().encode("utf-8"),
                               passwort.strip().encode("utf-8"))


def anmelden(eingabe: str, passwort: str, geheimnis: str, jetzt: float) -> tuple:
    """("voll", None), ("gast", Ende der Gueltigkeit) oder (None, None)."""
    if pruefe_passwort(eingabe, passwort):
        return "voll", None
    ende = pruefe_gast(eingabe, geheimnis, jetzt)
    if ende is not None:
        return "gast", ende
    return None, None


class Bremse:
    """Fehlversuche aller Sitzungen der App. Die Pause einer einzelnen
    Sitzung fuehrt die App selbst (sitzung_nach_fehlversuch)."""

    def __init__(self, grenze=GESAMT_GRENZE, zeitraum_s=GESAMT_ZEITRAUM_S):
        self.grenze = grenze
        self.zeitraum_s = zeitraum_s
        self._fehl = deque()
        self._schloss = threading.Lock()

    def _aufraeumen(self, jetzt):
        while self._fehl and self._fehl[0] <= jetzt - self.zeitraum_s:
            self._fehl.popleft()

    def gesperrt_bis(self, jetzt):
        """Unix-Zeit, bis zu der jede Anmeldung abgewiesen wird, sonst None."""
        with self._schloss:
            self._aufraeumen(jetzt)
            if len(self._fehl) >= self.grenze:
                return self._fehl[-self.grenze] + self.zeitraum_s
            return None

    def fehlversuch(self, jetzt) -> int:
        """Merkt einen Fehlversuch; liefert die Zahl im laufenden Zeitraum."""
        with self._schloss:
            self._aufraeumen(jetzt)
            self._fehl.append(jetzt)
            return len(self._fehl)


def sitzung_nach_fehlversuch(zaehler: int, jetzt: float) -> tuple:
    """(neuer Zaehler, Ende der Pause oder None) nach einem Fehlversuch."""
    zaehler += 1
    if zaehler >= SITZUNG_GRENZE:
        return 0, jetzt + SITZUNG_PAUSE_S
    return zaehler, None


def _bleiben_schluessel(passwort: str, geheimnis: str) -> bytes:
    return hashlib.sha256(b"heliot-sitzung|" + (geheimnis or "").encode("utf-8")
                          + b"|" + (passwort or "").strip().encode("utf-8")).digest()


def _bleiben_pruefwert(rumpf: str, passwort: str, geheimnis: str) -> str:
    return hmac.new(_bleiben_schluessel(passwort, geheimnis), rumpf.encode("ascii"),
                    hashlib.sha256).hexdigest()[:32]


def bleiben_moeglich(passwort: str, geheimnis: str) -> bool:
    """Angemeldet bleiben geht nur mit beiden Secrets."""
    return bool((passwort or "").strip()) and bool((geheimnis or "").strip())


def bleiben_ende(rolle: str, gast_bis, jetzt: float) -> float:
    """Bis wann der Eintrag gilt: voller Zugang 30 Tage, Gast bis zum Ablauf."""
    if rolle == "gast":
        return float(gast_bis)
    return float(jetzt + BLEIBEN_TAGE * 86400)


def bleiben_ausstellen(rolle: str, ende: float, passwort: str, geheimnis: str,
                       zufall: str = None) -> str:
    """Der Wert fuers Angemeldet-Bleiben fuer eine Rolle bis zum Ende (Unix-Zeit)."""
    if rolle not in BLEIBEN_ROLLEN:
        raise ValueError("unbekannte Rolle")
    if not bleiben_moeglich(passwort, geheimnis):
        raise ValueError("ohne beide Secrets gibt es kein Angemeldet-Bleiben")
    zufall = zufall or secrets.token_urlsafe(9)
    if not re.fullmatch(r"[A-Za-z0-9_-]{12}", zufall):
        raise ValueError("Zufallsteil hat nicht zwoelf erlaubte Zeichen")
    rumpf = f"v1.{rolle}.{int(ende):010d}.{zufall}"
    return rumpf + "." + _bleiben_pruefwert(rumpf, passwort, geheimnis)


def bleiben_pruefen(wert, passwort: str, geheimnis: str, jetzt: float) -> tuple:
    """(Rolle, Ende) fuer einen gueltigen, nicht abgelaufenen Wert,
    sonst (None, None). Wirft nie, auch nicht bei Unsinn."""
    if not isinstance(wert, str) or not bleiben_moeglich(passwort, geheimnis):
        return None, None
    wert = wert.strip()
    m = _BLEIBEN_FORM.fullmatch(wert)
    if not m:
        return None, None
    rolle, ende = m.group(1), float(m.group(2))
    rumpf = wert.rsplit(".", 1)[0]
    if not hmac.compare_digest(m.group(4), _bleiben_pruefwert(rumpf, passwort, geheimnis)):
        return None, None
    if jetzt >= ende:
        return None, None
    if rolle == "voll" and ende > jetzt + BLEIBEN_TAGE * 86400 + 60:
        return None, None
    return rolle, ende


_SPEICHER_JS = """export default function (component) {
  const data = component.data || {};
  const NAME = __NAME__;
  const ERLAUBT = /^[A-Za-z0-9._-]*$/;
  const auftrag = data.auftrag || "ruhe";

  function speicherLesen() {
    try { return window.localStorage.getItem(NAME) || ""; } catch (e) { return ""; }
  }
  function speicherSchreiben(wert) {
    try { window.localStorage.setItem(NAME, wert); return speicherLesen() === wert; } catch (e) { return false; }
  }
  function speicherLoeschen() {
    try { window.localStorage.removeItem(NAME); } catch (e) { }
  }
  function altesCookie() {
    let wert = "";
    try {
      const alle = document.cookie || "";
      for (const teil of alle.split(";")) {
        const t = teil.trim();
        if (t.indexOf(NAME + "=") === 0) { wert = t.slice(NAME.length + 1); break; }
      }
      if (alle.indexOf(NAME + "=") !== -1) {
        const sicher = window.location.protocol === "https:" ? "; Secure" : "";
        document.cookie = NAME + "=; Max-Age=0; Path=/; SameSite=Lax" + sicher;
      }
    } catch (e) { }
    return ERLAUBT.test(wert) ? wert : "";
  }

  if (auftrag === "setzen") {
    const wert = String(data.wert || "");
    if (wert && ERLAUBT.test(wert) && !speicherSchreiben(wert)) {
      component.setStateValue("gespeichert", false);
    }
    altesCookie();
    return;
  }
  if (auftrag === "loeschen") {
    speicherLoeschen();
    altesCookie();
    return;
  }
  if (auftrag === "lesen") {
    let wert = speicherLesen();
    const alt = altesCookie();
    if (!wert && alt) { wert = alt; speicherSchreiben(alt); }
    if (!ERLAUBT.test(wert)) { wert = ""; }
    if (wert !== data.bekannt) { component.setStateValue("wert", wert); }
  }
}
"""


def speicher_js(name: str = BLEIBEN_NAME) -> str:
    """Das JavaScript der unsichtbaren Komponente, die den Eintrag fuer das
    Angemeldet-Bleiben im Browser liest, schreibt und loescht
    (st.components.v2.component, laeuft ohne iframe in der Seite der App).

    Auftraege kommen ueber data (speicher_daten):
      * lesen: meldet den gespeicherten Wert als Zustand "wert", aber nur,
        wenn er sich von dem unterscheidet, was die App schon kennt
        ("bekannt"), sonst gaebe es bei jedem Lauf einen neuen. Ein Cookie
        der ersten Fassung wird uebernommen und geloescht.
      * setzen: schreibt den Wert; laesst der Browser das nicht zu, meldet
        er "gespeichert" = false.
      * loeschen: loescht den Eintrag und ein altes Cookie.
      * ruhe: tut nichts.
    Werte mit anderen Zeichen als Buchstaben, Ziffern, Punkt, Unterstrich und
    Bindestrich werden weder geschrieben noch gemeldet."""
    if not name or not _SPEICHER_ZEICHEN.fullmatch(name):
        raise ValueError("unerlaubtes Zeichen im Namen")
    return _SPEICHER_JS.replace("__NAME__", json.dumps(name))


def speicher_daten(auftrag: str, wert: str = "", bekannt=None) -> dict:
    """Die data fuer die Komponente aus speicher_js. Einen Wert gibt es nur
    beim Setzen; bekannt nur beim Lesen, damit sich data bei den anderen
    Auftraegen nicht von Lauf zu Lauf aendert."""
    if auftrag not in SPEICHER_AUFTRAEGE:
        raise ValueError("unbekannter Auftrag")
    wert = wert or ""
    if not isinstance(wert, str) or not _SPEICHER_ZEICHEN.fullmatch(wert):
        raise ValueError("unerlaubtes Zeichen im Wert")
    if auftrag != "setzen":
        wert = ""
    if auftrag != "lesen" or not (isinstance(bekannt, str) and _SPEICHER_ZEICHEN.fullmatch(bekannt)):
        bekannt = None
    return {"auftrag": auftrag, "wert": wert, "bekannt": bekannt}


def uhrzeit_wien(zeitpunkt: float) -> str:
    dt = datetime.fromtimestamp(zeitpunkt, tz=timezone.utc)
    if ZoneInfo is not None:
        try:
            dt = dt.astimezone(ZoneInfo("Europe/Vienna"))
        except Exception:  # noqa
            pass
    return f"{dt:%H:%M}"


def buchstabiert(passwort: str) -> str:
    """Zum Vorlesen: jeder Buchstabe einzeln, durch Leerzeichen getrennt."""
    return " ".join(passwort)


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

def selbsttest():
    fehler = []

    def p(name, ok, zusatz=""):
        print(f"  {'ok  ' if ok else 'FEHL'} {name}" + (f" — {zusatz}" if zusatz else ""))
        if not ok:
            fehler.append(name)

    print("Zugang, Selbsttest")
    g = "pruefgeheimnis-nur-fuer-den-selbsttest"
    f = 2982200                      # 13.09.2026, 17:20 UTC
    t0 = f * FENSTER_S               # erste Sekunde dieses Fensters

    pw = gast_passwort(g, f)
    p("Zehn Kleinbuchstaben", len(pw) == 10 and pw.isalpha() and pw.islower(), pw)
    p("Abwechselnd Mitlaut und Selbstlaut",
      all(pw[i] in MITLAUTE for i in range(0, 10, 2))
      and all(pw[i] in SELBSTLAUTE for i in range(1, 10, 2)), pw)
    p("Dasselbe Geheimnis und Fenster ergeben dasselbe Passwort", gast_passwort(g, f) == pw)
    p("Ein anderes Geheimnis ergibt ein anderes Passwort",
      all(gast_passwort(g + "x", f + k) != gast_passwort(g, f + k) for k in range(20)))
    viele = [gast_passwort(g, f + k) for k in range(2000)]
    p("2000 Fenster ergeben mindestens 1990 verschiedene Passwoerter",
      len(set(viele)) >= 1990, str(len(set(viele))))
    p("Alle 14 Mitlaute und 5 Selbstlaute kommen vor",
      set("".join(v[0::2] for v in viele)) == set(MITLAUTE)
      and set("".join(v[1::2] for v in viele)) == set(SELBSTLAUTE))

    code, ende = erzeuge(g, t0 + 123)
    p("Erzeugt wird das Passwort des laufenden Fensters", code == pw)
    p("Ende der Gueltigkeit: sieben Fenster nach Beginn des Erzeugungsfensters",
      ende == float((f + 7) * FENSTER_S), uhrzeit_wien(ende))
    p("Erzeugt in der ersten Sekunde: 70 Minuten gueltig", ende - t0 == 4200.0)
    p("Erzeugt in der letzten Sekunde: 60 Minuten und eine Sekunde gueltig",
      erzeuge(g, t0 + 599)[1] - (t0 + 599) == 3601.0)
    p("Gleich nach dem Erzeugen gueltig", pruefe_gast(pw, g, t0 + 1) == ende)
    p("Eine Sekunde vor dem Ende gueltig", pruefe_gast(pw, g, ende - 1) == ende)
    p("Am Ende nicht mehr gueltig", pruefe_gast(pw, g, ende) is None)
    p("Ein Passwort aus dem naechsten Fenster gilt noch nicht",
      pruefe_gast(gast_passwort(g, f + 1), g, t0 + 1) is None)
    p("Ein Passwort von vor sieben Fenstern gilt nicht mehr",
      pruefe_gast(gast_passwort(g, f - 7), g, t0 + 1) is None)
    p("Ein Passwort von vor sechs Fenstern gilt noch",
      pruefe_gast(gast_passwort(g, f - 6), g, t0 + 1) == float((f + 1) * FENSTER_S))

    p("Grossbuchstaben, Leerzeichen und Bindestriche zaehlen nicht",
      pruefe_gast(" " + pw[:4].upper() + " " + pw[4:7] + "-" + pw[7:] + " ", g, t0 + 5) == ende)
    p("Ein falscher Buchstabe wird abgewiesen",
      pruefe_gast(pw[:-1] + ("a" if pw[-1] != "a" else "e"), g, t0 + 5) is None)
    p("Zu kurz, leer und None werden abgewiesen",
      pruefe_gast(pw[:-2], g, t0) is None and pruefe_gast("", g, t0) is None
      and pruefe_gast(None, g, t0) is None)
    p("Umlaute und Sonderzeichen werfen keinen Fehler",
      pruefe_gast("kö be lima nu ß €", g, t0) is None)
    p("Ohne Geheimnis gibt es kein gueltiges Gastpasswort", pruefe_gast(pw, "", t0) is None)

    p("Festes Passwort: richtig", pruefe_passwort("Sonnenblume", "Sonnenblume"))
    p("Festes Passwort: Leerzeichen am Rand fallen weg", pruefe_passwort("  Sonnenblume ", "Sonnenblume"))
    p("Festes Passwort: Gross- und Kleinschreibung zaehlt",
      not pruefe_passwort("sonnenblume", "Sonnenblume"))
    p("Festes Passwort: mit Umlaut", pruefe_passwort("Grünkohl", "Grünkohl"))
    p("Festes Passwort: leeres Secret laesst nie hinein",
      not pruefe_passwort("", "") and not pruefe_passwort("  ", "  "))

    p("Anmelden mit dem festen Passwort", anmelden("Sonnenblume", "Sonnenblume", g, t0) == ("voll", None))
    p("Anmelden mit dem Gastpasswort", anmelden(pw, "Sonnenblume", g, t0 + 9) == ("gast", ende))
    p("Anmelden mit Falschem", anmelden("falsch", "Sonnenblume", g, t0) == (None, None))
    p("Ohne Geheimnis kein Gastzugang", anmelden(pw, "Sonnenblume", "", t0) == (None, None))

    b = Bremse()
    for k in range(19):
        b.fehlversuch(1000.0 + k)
    p("19 Fehlversuche in zehn Minuten sperren noch nicht", b.gesperrt_bis(1019.0) is None)
    b.fehlversuch(1019.0)
    p("Der 20. Fehlversuch sperrt bis zehn Minuten nach dem aeltesten",
      b.gesperrt_bis(1019.5) == 1600.0, str(b.gesperrt_bis(1019.5)))
    p("Kurz vor Ablauf noch gesperrt", b.gesperrt_bis(1599.9) == 1600.0)
    p("Danach wieder offen", b.gesperrt_bis(1600.0) is None)
    p("Alte Fehlversuche verfallen", b.fehlversuch(5000.0) == 1)

    z, pause = 0, None
    for k in range(4):
        z, pause = sitzung_nach_fehlversuch(z, 100.0)
    p("Vier Fehlversuche einer Sitzung: noch keine Pause", z == 4 and pause is None)
    z, pause = sitzung_nach_fehlversuch(z, 100.0)
    p("Der fuenfte: eine Minute Pause, Zaehler beginnt neu", z == 0 and pause == 160.0)

    sommer = datetime(2026, 9, 13, 19, 30, tzinfo=timezone.utc).timestamp()
    winter = datetime(2026, 12, 13, 19, 30, tzinfo=timezone.utc).timestamp()
    p("Uhrzeit in Wiener Sommerzeit", uhrzeit_wien(sommer) == "21:30", uhrzeit_wien(sommer))
    p("Uhrzeit in Wiener Winterzeit", uhrzeit_wien(winter) == "20:30", uhrzeit_wien(winter))
    p("Buchstabiert", buchstabiert("kobe") == "k o b e")

    # Angemeldet bleiben (14.09.2026)
    pw_s, g_s = "Pruefwort-nur-fuer-den-Selbsttest", g
    jetzt = 1789400000.0
    p("Ohne eines der Secrets kein Angemeldet-Bleiben",
      not bleiben_moeglich(pw_s, "") and not bleiben_moeglich("", g_s) and bleiben_moeglich(pw_s, g_s))
    ende_v = bleiben_ende("voll", None, jetzt)
    p("Voller Zugang gilt 30 Tage", ende_v - jetzt == 30 * 86400)
    p("Gast gilt bis zum Ablauf des Gastpassworts", bleiben_ende("gast", jetzt + 3000, jetzt) == jetzt + 3000)
    wert = bleiben_ausstellen("voll", ende_v, pw_s, g_s, zufall="abcDEF123_-x")
    p("Der Wert hat die Form v1.rolle.ende.zufall.pruefwert",
      bool(_BLEIBEN_FORM.fullmatch(wert)), wert[:30])
    p("Passwort und Geheimnis stehen nicht im Wert", pw_s not in wert and g_s not in wert)
    p("Gueltiger Wert wird erkannt", bleiben_pruefen(wert, pw_s, g_s, jetzt + 5) == ("voll", ende_v))
    p("Leerzeichen am Rand stoeren nicht", bleiben_pruefen(" " + wert + " ", pw_s, g_s, jetzt) == ("voll", ende_v))
    p("Abgelaufener Wert wird abgewiesen", bleiben_pruefen(wert, pw_s, g_s, ende_v) == (None, None))
    p("Anderes Passwort macht den Wert ungueltig", bleiben_pruefen(wert, pw_s + "x", g_s, jetzt) == (None, None))
    p("Anderes Geheimnis macht den Wert ungueltig", bleiben_pruefen(wert, pw_s, g_s + "x", jetzt) == (None, None))
    gefaelscht = wert.replace("v1.voll.", "v1.gast.")
    p("Umgeschriebene Rolle wird abgewiesen", bleiben_pruefen(gefaelscht, pw_s, g_s, jetzt) == (None, None))
    teile = wert.split(".")
    verlaengert = ".".join([teile[0], teile[1], str(int(teile[2]) + 86400), teile[3], teile[4]])
    p("Verlaengertes Ende wird abgewiesen", bleiben_pruefen(verlaengert, pw_s, g_s, jetzt) == (None, None))
    p("Unsinn wirft nicht und wird abgewiesen",
      all(bleiben_pruefen(x, pw_s, g_s, jetzt) == (None, None)
          for x in (None, "", "v1", 42, "v1.voll.1.x.y", "ä" * 70, wert + ".zusatz")))
    zu_lang = bleiben_ausstellen("voll", jetzt + 40 * 86400, pw_s, g_s, zufall="abcDEF123_-x")
    p("Ein voller Zugang ueber 30 Tage hinaus wird abgewiesen",
      bleiben_pruefen(zu_lang, pw_s, g_s, jetzt) == (None, None))
    gast_wert = bleiben_ausstellen("gast", jetzt + 3000, pw_s, g_s)
    p("Gast-Wert gilt bis zum Ablauf und nicht laenger",
      bleiben_pruefen(gast_wert, pw_s, g_s, jetzt + 2999) == ("gast", jetzt + 3000)
      and bleiben_pruefen(gast_wert, pw_s, g_s, jetzt + 3000) == (None, None))
    p("Jedes Ausstellen ergibt einen anderen Wert",
      len({bleiben_ausstellen("voll", ende_v, pw_s, g_s) for _ in range(50)}) == 50)
    js = speicher_js()
    p("Speicher-Skript ist ein Modul mit Standardfunktion", js.startswith("export default function (component) {"))
    p("Speicher-Skript liest, schreibt und loescht den Eintrag heliot_zugang",
      'const NAME = "heliot_zugang";' in js and "localStorage.getItem(NAME)" in js
      and "localStorage.setItem(NAME, wert)" in js and "localStorage.removeItem(NAME)" in js)
    p("Speicher-Skript meldet nur die zwei Zustaende gespeichert und wert",
      re.findall(r'setStateValue\("(\w+)"', js) == ["gespeichert", "wert"])
    p("Speicher-Skript meldet beim Lesen nur, was die App noch nicht kennt",
      "if (wert !== data.bekannt)" in js)
    p("Speicher-Skript prueft die Zeichen jedes Werts",
      js.count("ERLAUBT.test(") >= 3 and "/^[A-Za-z0-9._-]*$/" in js)
    p("Speicher-Skript holt nichts aus dem Netz und baut kein HTML",
      not any(x in js for x in ("fetch(", "XMLHttpRequest", "innerHTML", "eval(", "http:", "import(")))
    try:
        speicher_js('x"; alert(1); "')
        p("Speicher-Skript weist fremde Zeichen im Namen ab", False)
    except ValueError:
        p("Speicher-Skript weist fremde Zeichen im Namen ab", True)
    p("Daten: Lesen traegt nur das Bekannte",
      speicher_daten("lesen", wert, wert) == {"auftrag": "lesen", "wert": "", "bekannt": wert})
    p("Daten: Setzen traegt den Wert, nicht das Bekannte",
      speicher_daten("setzen", wert, wert) == {"auftrag": "setzen", "wert": wert, "bekannt": None})
    p("Daten: Loeschen und Ruhe tragen weder Wert noch Bekanntes",
      speicher_daten("loeschen", wert, wert) == {"auftrag": "loeschen", "wert": "", "bekannt": None}
      and speicher_daten("ruhe", "", "") == {"auftrag": "ruhe", "wert": "", "bekannt": None})
    p("Daten: noch nicht gemeldet heisst bekannt None, leer gemeldet heisst leer",
      speicher_daten("lesen", "", None)["bekannt"] is None and speicher_daten("lesen", "", "")["bekannt"] == "")
    p("Daten: fremde Zeichen im Bekannten gelten als nicht gemeldet",
      speicher_daten("lesen", "", "a b")["bekannt"] is None)
    abgewiesen = 0
    for argumente in (("schreiben", "", None), ("setzen", 'x"; alert(1); "', None), ("setzen", "ä", None)):
        try:
            speicher_daten(*argumente)
        except ValueError:
            abgewiesen += 1
    p("Daten: unbekannter Auftrag und fremde Zeichen im Wert werden abgewiesen", abgewiesen == 3)

    print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles bestanden.")
    return 1 if fehler else 0


def main():
    ap = argparse.ArgumentParser(description="Anmeldung zur Heliot-App")
    ap.add_argument("--selbsttest", action="store_true")
    args = ap.parse_args()
    if args.selbsttest:
        return selbsttest()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
